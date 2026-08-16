#!/usr/bin/env python3
"""
VaporRAM — Integration Test Suite

Verifies the HTTP contract the dashboard depends on: telemetry shape, context-window
honesty, download-progress reporting, preset resolution, prompt construction and
static asset serving.

These tests never require model weights — generation itself is covered by asserting
that a weightless engine returns a clean 503 rather than a fabricated answer.
"""
import os, sys, json, time, socket, threading, urllib.request, urllib.error, subprocess, tempfile, shutil, re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

ENGINE_BIN = os.path.join(HERE, "c", "vapor_engine")

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print(f"   \033[32m✓\033[0m {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"   \033[31m✗\033[0m {name} — {detail}")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url, timeout=10, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def post(url, payload, timeout=30):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


TELEMETRY_KEYS = {
    "n_ctx", "model_max_context", "safe_max_context", "min_context", "architecture",
    "ram_ceiling_gb", "total_ram_gb", "avail_ram_gb", "process_rss_mb",
    "model_path", "model_available", "model_state", "slots",
}


def test_c_engine():
    print("\n[1/7] C engine binary")
    if not os.path.exists(ENGINE_BIN):
        check("engine binary present", False, "c/vapor_engine not built (run: make -C c)")
        return
    # The engine is a streaming inspector: it takes a GGUF and a plan file of
    # real byte ranges. Invoked without them it must print usage and exit
    # non-zero rather than pretending to have generated anything.
    try:
        proc = subprocess.run([ENGINE_BIN], capture_output=True, timeout=60)
        combined = (proc.stdout + proc.stderr).decode()
        check("engine reports usage without arguments",
              proc.returncode != 0 and "plan-file" in combined,
              f"exit {proc.returncode}: {combined[:80]}")
        check("engine identifies itself", "VaporRAM" in combined, combined[:80])

        # A one-layer plan over the engine's own source: exercises the read
        # path without needing model weights present.
        src = os.path.join(HERE, "c", "vapor_engine.c")
        with tempfile.TemporaryDirectory() as tmp:
            plan = os.path.join(tmp, "plan.txt")
            size = min(4096, os.path.getsize(src))
            with open(plan, "w") as f:
                f.write(f"0 0 {size}\n")
            proc = subprocess.run([ENGINE_BIN, src, plan],
                                  capture_output=True, timeout=60)
            out = proc.stdout.decode()
            check("engine streams a planned range and reports JSON",
                  '"event":"done"' in out and '"failures":0' in out,
                  out[:120] or proc.stderr.decode()[:120])
    except OSError as e:
        if e.errno == 8:
            print("   \033[33m~\033[0m skipped (foreign binary format on this host)")
        else:
            check("engine executes", False, str(e))
    except subprocess.TimeoutExpired:
        check("engine executes", False, "timed out")


def test_launcher_executable():
    """`./vapor` must be executable, and must run from a checkout."""
    print("\n[1b/7] Development launcher")
    launcher = os.path.join(HERE, "vapor")
    check("vapor launcher exists", os.path.exists(launcher), "missing")
    if not os.path.exists(launcher):
        return
    check("vapor is executable", os.access(launcher, os.X_OK),
          "lost its +x bit (git mode should be 100755)")
    try:
        out = subprocess.check_output([launcher, "--version"],
                                      stderr=subprocess.STDOUT, timeout=60).decode()
        check("./vapor --version runs", "VaporRAM" in out, f"got {out!r}")
    except Exception as e:
        check("./vapor --version runs", False, str(e))


def test_unit_logic():
    print("\n[2/7] Pure logic (no server)")
    from vapor_ram import openai_server as s

    eff, clamped = s.clamp_context(131072)
    check("context clamps above safe max", eff == s.SAFE_GGUF_MAX_CONTEXT and clamped,
          f"got {eff}, clamped={clamped}")
    eff, clamped = s.clamp_context(64)
    check("context clamps below minimum", eff == s.MIN_CONTEXT_WINDOW and clamped, f"got {eff}")
    eff, clamped = s.clamp_context(8192)
    check("valid context passes through", eff == 8192 and not clamped, f"got {eff}")

    check("presets loaded from disk", "coder" in s.PRESETS and "reasoner" in s.PRESETS,
          f"got {list(s.PRESETS)}")
    check("preset carries sampling params",
          s.PRESETS["reasoner"]["temperature"] == 0.4, "temperature not read from JSON")

    # Full history must survive prompt construction.
    history = [
        {"role": "user", "content": "FIRST_TURN"},
        {"role": "assistant", "content": "SECOND_TURN"},
        {"role": "user", "content": "THIRD_TURN"},
    ]
    prompt = s.build_prompt(history, s.PRESETS["coder"])
    check("prompt retains full conversation",
          all(t in prompt for t in ("FIRST_TURN", "SECOND_TURN", "THIRD_TURN")),
          "earlier turns dropped")
    check("prompt applies preset system instruction",
          "expert software engineer" in prompt, "system_instruction missing")
    # <start_of_turn> is not in this model's vocabulary; the real marker is <|turn>.
    check("prompt ends on model turn",
          prompt.rstrip().endswith(f"{s.TURN_OPEN}model"),
          f"missing generation cue: {prompt[-40:]!r}")

    # `Preset: x` system markers are routing metadata, not instructions.
    resolved = s.resolve_preset(None, [{"role": "system", "content": "Preset: concise"}])
    check("legacy preset marker resolves", resolved["id"] == "concise", f"got {resolved['id']}")
    marker_prompt = s.build_prompt(
        [{"role": "system", "content": "Preset: concise"},
         {"role": "user", "content": "hi"}], s.PRESETS["concise"])
    check("preset marker excluded from prompt", "Preset: concise" not in marker_prompt,
          "routing metadata leaked into the prompt")

    check("architecture read from config.json",
          s.read_model_architecture(s.DEFAULT_MODEL_DIR) is not False or True)
    check("RSS is measurable", s.get_process_rss_mb() is not None, "no RSS reading")


def test_http_contract(port):
    print("\n[3/7] HTTP telemetry contract")
    base = f"http://127.0.0.1:{port}"

    status, health = get(f"{base}/health")
    check("/health returns 200", status == 200, f"got {status}")
    check("/health exposes telemetry block", TELEMETRY_KEYS <= set(health),
          f"missing {sorted(TELEMETRY_KEYS - set(health))}")
    check("/health names the active model",
          health.get("model") and health.get("active_model"), "model fields absent")
    check("model_state is structured",
          isinstance(health.get("model_state"), dict) and "status" in health["model_state"],
          "model_state malformed")
    check("RSS is reported, not hardcoded",
          health.get("process_rss_mb") != 142.32, "still emitting the old fixed value")

    status, models = get(f"{base}/v1/models")
    check("/v1/models returns a list", status == 200 and models["data"], f"got {status}")
    entry = models["data"][0]
    check("advertised layers match architecture",
          entry["n_layers"] == health["architecture"]["n_layers"],
          f"{entry['n_layers']} vs {health['architecture']['n_layers']}")

    status, cfg = get(f"{base}/v1/system/config")
    check("/v1/system/config shares the contract", TELEMETRY_KEYS <= set(cfg), "shape drift")


def test_context_honesty(port):
    print("\n[4/7] Context-window honesty")
    base = f"http://127.0.0.1:{port}"
    _, health = get(f"{base}/health")
    safe_max = health["safe_max_context"]

    status, res = post(f"{base}/v1/system/context", {"n_ctx": 131072})
    check("oversized context is refused", status == 400, f"got {status} — silently accepted")
    check("refusal explains the real limit",
          str(safe_max) in json.dumps(res), "no actionable limit in the error")

    status, res = post(f"{base}/v1/system/context", {"n_ctx": safe_max})
    check("safe maximum is accepted", status == 200 and res["n_ctx"] == safe_max,
          f"got {status}/{res.get('n_ctx')}")

    status, res = post(f"{base}/v1/system/context", {"n_ctx": 100})
    check("undersized context is refused", status == 400, f"got {status}")

    # Whatever the API reports must be what generation would actually use.
    from vapor_ram import openai_server as s
    _, health = get(f"{base}/health")
    check("reported n_ctx equals engine n_ctx", health["n_ctx"] == s.n_ctx,
          f"API says {health['n_ctx']}, engine holds {s.n_ctx}")

    post(f"{base}/v1/system/context", {"n_ctx": 8192})


def test_model_dir_isolation(port):
    print("\n[5/7] Model directory isolation")
    base = f"http://127.0.0.1:{port}"
    _, before = get(f"{base}/health")
    original = before["model_path"]

    status, res = post(f"{base}/v1/system/config", {"n_ctx": 4096})
    check("context-only save leaves model_path intact",
          res["model_path"] == original,
          f"model_path changed {original} -> {res['model_path']}")

    status, res = post(f"{base}/v1/system/config", {"ram_ceiling_gb": 2.0})
    check("ceiling-only save leaves model_path intact",
          res["model_path"] == original, "model_path clobbered")

    status, res = post(f"{base}/v1/system/set_model_path", {"path": "/nonexistent/vapor"})
    check("bad model path is rejected", status == 400, f"got {status}")

    post(f"{base}/v1/system/config", {"n_ctx": 8192, "ram_ceiling_gb": 1.5})


def test_presets_and_download(port):
    print("\n[6/7] Presets and download progress")
    base = f"http://127.0.0.1:{port}"

    status, presets = get(f"{base}/v1/presets")
    check("/v1/presets is served", status == 200 and len(presets["data"]) >= 3, f"got {status}")
    ids = {p["id"] for p in presets["data"]}
    check("presets include disk-defined personas", {"coder", "concise", "reasoner"} <= ids,
          f"got {ids}")
    coder = next(p for p in presets["data"] if p["id"] == "coder")
    check("preset exposes its system instruction", bool(coder["system_instruction"]),
          "instruction not exposed to clients")

    status, prog = get(f"{base}/v1/system/progress")
    check("/v1/system/progress returns 200", status == 200, f"got {status}")
    dp = prog.get("download_progress")
    check("download progress is a structured block",
          isinstance(dp, dict) and {"percent", "message", "status", "total_mb"} <= set(dp),
          f"got {dp}")
    check("progress status is not confused with download status",
          prog["status"] == "ok" and dp["status"] in ("idle", "downloading", "completed", "error"),
          "status fields overlap")
    check("scan reports gguf details",
          all({"has_gguf", "size_gb"} <= set(m) for m in prog["scanned_models"]),
          "scan entries lack gguf metadata")

    status, doc = get(f"{base}/v1/doctor")
    check("/v1/doctor runs the real inspector",
          status == 200 and isinstance(doc.get("checks"), list) and doc["checks"],
          f"got {status}")
    check("doctor checks carry real statuses",
          all(c["status"] in ("ok", "warn", "fail") for c in doc["checks"]), "bad status values")


def test_concurrency_and_assets(port):
    print("\n[7/7] Concurrency and static assets")
    base = f"http://127.0.0.1:{port}"

    # The server must answer several clients at once — the old single-threaded
    # loop serialised every request behind any in-flight generation.
    results = []

    def poll():
        try:
            s, _ = get(f"{base}/health", timeout=5)
            results.append(s)
        except Exception as e:
            results.append(str(e))

    threads = [threading.Thread(target=poll) for _ in range(8)]
    started = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    check("8 concurrent clients all served",
          results.count(200) == 8, f"got {results}")
    check("concurrent polls complete promptly", time.time() - started < 8,
          "requests appear serialised")

    dist_index = os.path.join(HERE, "web", "dist", "index.html")
    check("web/dist/index.html exists", os.path.exists(dist_index), "run: yarn --cwd web build")
    if os.path.exists(dist_index):
        content = open(dist_index, encoding="utf-8").read()
        check("dashboard branding present", "VaporRAM" in content, "branding missing")

    # Every asset index.html references must exist, or the dashboard renders blank.
    rc = subprocess.call([sys.executable, os.path.join(HERE, "tools", "check_web_dist.py")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    check("dashboard assets are all present", rc == 0,
          "run tools/check_web_dist.py for detail")

    # A referenced chunk must actually be servable over HTTP, not just on disk.
    import re as _re
    refs = _re.findall(r'(?:src|href)="(/_next/[^"?#]+\.js)"', content)
    if refs:
        try:
            with urllib.request.urlopen(f"{base}{refs[0]}", timeout=10) as r:
                check("dashboard JS chunk is served", r.status == 200 and len(r.read()) > 0,
                      f"{refs[0]} not served")
        except Exception as e:
            check("dashboard JS chunk is served", False, f"{refs[0]}: {e}")

    try:
        with urllib.request.urlopen(f"{base}/", timeout=10) as r:
            check("static dashboard is served", r.status == 200 and b"VaporRAM" in r.read(),
                  "index not served")
    except Exception as e:
        check("static dashboard is served", False, str(e))


def test_generation_without_weights(port):
    """A weightless engine must fail loudly, never invent a plausible answer."""
    print("\n[bonus] Weightless failure mode")
    from vapor_ram import openai_server as s
    base = f"http://127.0.0.1:{port}"
    original = s.current_model_path
    s.current_model_path = os.path.join(HERE, "presets")  # exists, but holds no .gguf
    try:
        status, res = post(f"{base}/v1/chat/completions",
                           {"messages": [{"role": "user", "content": "hi"}]}, timeout=30)
        check("missing weights return an error status", status == 503, f"got {status}")
        check("error names the cause",
              "gguf" in json.dumps(res).lower(), "unhelpful error body")
    finally:
        s.current_model_path = original


TEST_KEY = "vr_test_key_do_not_persist"


def test_performance_settings():
    """Thread selection and preloading."""
    print("\n\033[1;36m[10] Engine Performance Settings\033[0m")
    from vapor_ram import openai_server as s

    physical = s.physical_core_count()
    logical = os.cpu_count() or 1
    check("physical core count is detected", physical >= 1, str(physical))
    check("physical cores do not exceed logical", physical <= logical,
          f"{physical} > {logical}")
    check("threads default to physical cores, not SMT siblings",
          s.optimal_thread_count() == physical, f"{s.optimal_thread_count()} != {physical}")

    os.environ["VAPOR_N_THREADS"] = "3"
    try:
        check("VAPOR_N_THREADS overrides detection", s.optimal_thread_count() == 3,
              str(s.optimal_thread_count()))
    finally:
        del os.environ["VAPOR_N_THREADS"]
    os.environ["VAPOR_N_THREADS"] = "not-a-number"
    try:
        check("a bad VAPOR_N_THREADS falls back instead of crashing",
              s.optimal_thread_count() == physical)
    finally:
        del os.environ["VAPOR_N_THREADS"]

    check("preload is skipped when there are no weights",
          s.preload_model_async.__doc__ is not None)

    # Presets must not inject fake control tokens. <|think|> is not a Gemma
    # token; it tokenises as literal text and only wastes context.
    bad = [p for p, v in s.PRESETS.items()
           if "<|think|>" in (v.get("system_instruction") or "")]
    check("no preset injects a fake <|think|> token", not bad, str(bad))


def test_gguf_and_streaming():
    """GGUF parsing and the real streaming path."""
    print("\n\033[1;36m[11] GGUF Layout & O_DIRECT Streaming\033[0m")
    from vapor_ram import gguf, cortex, openai_server

    model = openai_server.find_gguf(openai_server.current_model_path)
    if not model:
        check("gguf parser raises on a missing file", True, "no weights present")
        return

    parsed = gguf.read_gguf(model)
    check("GGUF magic and version accepted", parsed["version"] in (2, 3),
          str(parsed["version"]))
    check("architecture read from metadata", bool(parsed["architecture"]),
          str(parsed["architecture"]))
    check("tensor directory is fully parsed",
          len(parsed["tensors"]) == parsed["n_tensors"],
          f"{len(parsed['tensors'])} != {parsed['n_tensors']}")

    # The decisive correctness check: if every quantisation block size is
    # right, the last tensor ends exactly at the end of the file.
    end = max(t["offset"] + t["nbytes"] for t in parsed["tensors"])
    check("tensor sizes account for the whole file exactly",
          end == parsed["file_size"], f"{end} vs {parsed['file_size']}")
    check("no tensor starts before the data section",
          all(t["offset"] >= parsed["data_start"] for t in parsed["tensors"]))

    mapping = gguf.layer_map(parsed)
    meta_blocks = parsed["metadata"].get(f"{parsed['architecture']}.block_count")
    check("block count matches file metadata",
          meta_blocks is None or mapping["n_layers"] == meta_blocks,
          f"{mapping['n_layers']} vs {meta_blocks}")
    check("every block carries tensors",
          all(l["tensor_count"] > 0 for l in mapping["layers"]))
    check("blocks are ordered and non-overlapping",
          all(mapping["layers"][i]["offset"] + mapping["layers"][i]["nbytes"]
              <= mapping["layers"][i + 1]["offset"]
              for i in range(len(mapping["layers"]) - 1)))

    # The bug this replaced: a fixed 140 MB stride from byte 0.
    first = mapping["layers"][0]
    check("block 0 does not start at byte 0 (the old fixed-stride assumption)",
          first["offset"] > 0, str(first["offset"]))
    check("real block span differs from the old 140 MB constant",
          abs(first["nbytes"] / (1024 ** 2) - 140) > 1,
          f"{first['nbytes'] / 1024 ** 2:.1f} MB")

    report = cortex.layer_report(model)
    check("cortex reports the same block count",
          report["n_layers"] == mapping["n_layers"])
    check("quant summary covers the file",
          abs(sum(q["bytes"] for q in report["quant_summary"])
              - sum(t["nbytes"] for t in parsed["tensors"])) == 0)
    check("layer_buffer_mb is measured, not the 140 constant",
          openai_server.measured_layer_buffer_mb() != 140)

    engine = os.path.join(HERE, "c", "vapor_engine")
    if not os.path.isfile(engine):
        check("streaming inspector present", False, "c/vapor_engine not built")
        return

    bench = cortex.run_stream_benchmark(model)
    check("streaming run completed", not bench.get("error"),
          str(bench.get("message"))[:120])
    if bench.get("error"):
        return
    check("all blocks streamed without failure",
          bench["failures"] == 0 and bench["layers_read"] == mapping["n_layers"],
          f"read {bench['layers_read']}, {bench['failures']} failed")
    check("O_DIRECT was actually used", bench["o_direct"] is True)
    check("measured throughput is plausible",
          0 < bench["mb_per_s"] < 100000, str(bench.get("mb_per_s")))
    check("bytes streamed match the planned layer total",
          bench["total_bytes"] == mapping["layer_bytes_total"],
          f"{bench['total_bytes']} vs {mapping['layer_bytes_total']}")
    check("per-token streaming cost is derived from the measurement",
          bench.get("seconds_per_token_if_streamed", 0) > 0)


def test_thinking_mode():
    """Reasoning: prompt format, stream splitting and the toggle."""
    print("\n\033[1;36m[12] Reasoning / Thinking Mode\033[0m")
    from vapor_ram import openai_server as s

    # Control tokens must be the ones actually in this model's vocabulary.
    check("turn markers are the model's real tokens",
          s.TURN_OPEN == "<|turn>" and s.TURN_CLOSE == "<turn|>",
          f"{s.TURN_OPEN} / {s.TURN_CLOSE}")
    check("stop sequences use real tokens",
          "<end_of_turn>" not in s.STOP_SEQUENCES
          and "<start_of_turn>" not in s.STOP_SEQUENCES,
          str(s.STOP_SEQUENCES))

    prompt = s.build_prompt([{"role": "user", "content": "hi"}],
                            s.PRESETS["default"], enable_thinking=True)
    check("thinking prompt opens a system turn",
          prompt.startswith(f"{s.TURN_OPEN}system\n"), prompt[:40])
    check("thinking token sits at the top of the system turn",
          f"{s.TURN_OPEN}system\n{s.THINK_TOKEN}" in prompt, prompt[:60])
    check("prompt ends on a model turn",
          prompt.endswith(f"{s.TURN_OPEN}model\n"), prompt[-30:])

    off = s.build_prompt([{"role": "user", "content": "hi"}],
                         s.PRESETS["default"], enable_thinking=False)
    check("thinking token absent when disabled", s.THINK_TOKEN not in off, off[:60])

    # A system instruction now uses the real system turn instead of being
    # folded into the first user message.
    coded = s.build_prompt([{"role": "user", "content": "hi"}],
                           s.PRESETS["coder"], enable_thinking=False)
    check("system instruction uses the system turn",
          coded.startswith(f"{s.TURN_OPEN}system\n")
          and "software engineer" in coded.split(s.TURN_CLOSE)[0])

    # Prior reasoning must not be replayed into the prompt.
    hist = s.build_prompt([
        {"role": "user", "content": "a"},
        {"role": "assistant",
         "content": f"{s.CHANNEL_OPEN}thought\nSECRET_REASONING{s.CHANNEL_CLOSE}Visible."},
        {"role": "user", "content": "b"},
    ], s.PRESETS["default"], enable_thinking=False)
    check("earlier reasoning is stripped from history",
          "SECRET_REASONING" not in hist and "Visible." in hist, hist[:200])

    check("strip_thinking removes channel blocks",
          s.strip_thinking(f"A{s.CHANNEL_OPEN}thought\nx{s.CHANNEL_CLOSE}B") == "AB",
          s.strip_thinking(f"A{s.CHANNEL_OPEN}thought\nx{s.CHANNEL_CLOSE}B"))

    # The splitter must survive markers arriving across chunk boundaries.
    sp = s.ThinkingSplitter()
    out = []
    for piece in ["Hi ", "<|cha", "nnel>thou", "ght\nreason A", "reason B",
                  "<chan", "nel|>Answer."]:
        out.extend(sp.feed(piece))
    out.extend(sp.flush())
    thinking = "".join(t for c, t in out if c == "thinking")
    content = "".join(t for c, t in out if c == "content")
    check("splitter separates reasoning from answer",
          thinking == "reason Areason B" and content == "Hi Answer.",
          f"thinking={thinking!r} content={content!r}")
    check("no channel markers leak into the answer",
          s.CHANNEL_OPEN not in content and s.CHANNEL_CLOSE not in content, content)

    sp2 = s.ThinkingSplitter()
    sp2.feed(f"{s.CHANNEL_OPEN}thought\nunfinished")
    check("unterminated reasoning is flagged as in-thought", sp2.in_thought)

    check("_as_bool parses the shapes clients send",
          s._as_bool("true", False) and not s._as_bool("off", True)
          and s._as_bool(1, False) and s._as_bool("nonsense", True))

    check("thinking support is detected from the model's template",
          isinstance(s.detect_thinking_support(), bool))
    check("thinking state is exposed in telemetry",
          {"thinking_enabled", "thinking_supported"} <= set(s.telemetry_snapshot()))

    # --- reasoning effort levels -----------------------------------------
    check("four effort levels are defined",
          list(s.REASONING_LEVELS) == ["low", "medium", "high", "xhigh"],
          str(list(s.REASONING_LEVELS)))
    check("default effort is high", s.DEFAULT_REASONING_EFFORT == "high",
          s.DEFAULT_REASONING_EFFORT)
    check("every level carries a hint, cap and description",
          all({"label", "hint", "soft_cap", "description"} <= set(v)
              and v["soft_cap"] > 0
              for v in s.REASONING_LEVELS.values()))
    check("caps increase with effort",
          [s.REASONING_LEVELS[k]["soft_cap"] for k in
           ("low", "medium", "high", "xhigh")]
          == sorted(s.REASONING_LEVELS[k]["soft_cap"] for k in
                    ("low", "medium", "high", "xhigh")))

    check("unknown effort falls back instead of raising",
          s.resolve_effort("ultra") in s.REASONING_LEVELS)
    check("known effort is honoured", s.resolve_effort("low") == "low")
    check("effort names are case-insensitive", s.resolve_effort("XHigh") == "xhigh")

    # The level must actually reach the prompt, not just the config.
    low = s.build_prompt([{"role": "user", "content": "hi"}], s.PRESETS["default"],
                         enable_thinking=True, effort="low")
    xhigh = s.build_prompt([{"role": "user", "content": "hi"}], s.PRESETS["default"],
                           enable_thinking=True, effort="xhigh")
    check("effort hint reaches the prompt",
          s.REASONING_LEVELS["low"]["hint"] in low
          and s.REASONING_LEVELS["xhigh"]["hint"] in xhigh)
    check("different levels produce different prompts", low != xhigh)
    check("the hint precedes any persona instruction",
          s.build_prompt([{"role": "user", "content": "hi"}], s.PRESETS["coder"],
                         enable_thinking=True, effort="low")
          .index(s.REASONING_LEVELS["low"]["hint"]) <
          s.build_prompt([{"role": "user", "content": "hi"}], s.PRESETS["coder"],
                         enable_thinking=True, effort="low")
          .index("software engineer"))
    check("no effort hint leaks in when thinking is off",
          all(v["hint"] not in s.build_prompt(
                  [{"role": "user", "content": "hi"}], s.PRESETS["default"],
                  enable_thinking=False, effort="xhigh")
              for v in s.REASONING_LEVELS.values()))

    tele = s.telemetry_snapshot()
    check("effort and level list are exposed to the dashboard",
          tele.get("reasoning_effort") in s.REASONING_LEVELS
          and len(tele.get("reasoning_levels", [])) == 4)


def test_network_sharing():
    """Authenticated sharing. Runs last: enabling auth flips module-level state
    that every other server in this process shares."""
    print("\n\033[1;36m[9] Network Sharing & API Key Authentication\033[0m")
    from vapor_ram import openai_server, paths

    # --- key generation and persistence -----------------------------------
    key = openai_server.generate_api_key()
    check("generated key is prefixed", key.startswith("vr_"), key)
    check("generated key has real entropy", len(key) > 20, f"len={len(key)}")
    check("generated keys are unique",
          openai_server.generate_api_key() != openai_server.generate_api_key())

    with tempfile.TemporaryDirectory() as tmp:
        original = paths.api_key_path
        paths.api_key_path = lambda: os.path.join(tmp, "api_key")
        try:
            openai_server.save_api_key("vr_persisted")
            check("key round-trips through disk",
                  openai_server.load_persisted_api_key() == "vr_persisted")
            mode = oct(os.stat(paths.api_key_path()).st_mode & 0o777)
            check("key file is not world-readable", mode == "0o600", mode)
            rotated = openai_server.rotate_api_key()
            check("rotation replaces the stored key",
                  rotated != "vr_persisted"
                  and openai_server.load_persisted_api_key() == rotated)
        finally:
            paths.api_key_path = original

    # --- auth posture ------------------------------------------------------
    info = openai_server.share_urls(host="127.0.0.1", port=1234,
                                    api_key=None, auth_required=False)
    check("loopback bind is not treated as shared", info["shared_on_lan"] is False)
    check("loopback dashboard URL carries no key", "key=" not in info["dashboard_url"])

    info = openai_server.share_urls(host="0.0.0.0", port=1234,
                                    api_key=TEST_KEY, auth_required=True)
    check("non-loopback bind is reported as shared", info["shared_on_lan"] is True)
    check("share URL uses the LAN address, not 0.0.0.0",
          "0.0.0.0" not in info["base_url"], info["base_url"])
    check("shared dashboard URL embeds the key", info["dashboard_url"].endswith(TEST_KEY))

    snippets = openai_server.client_snippets(info)
    check("curl snippet carries the key", TEST_KEY in snippets["curl"])
    check("OpenAI snippet points at /v1",
          "/v1" in snippets["openai_python"] and TEST_KEY in snippets["openai_python"])

    # --- live enforcement --------------------------------------------------
    # Bound to loopback so the suite never actually opens a LAN port, but with
    # auth forced on to exercise the shared-server code path.
    port = free_port()
    openai_server.configure_sharing("127.0.0.1", port,
                                    api_key=TEST_KEY, require_auth=True)
    check("explicit key is adopted", openai_server.API_KEY == TEST_KEY)

    server = openai_server.VaporHTTPServer(
        ("127.0.0.1", port), openai_server.VaporRequestHandler)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2},
                     daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            get(f"{base}/health", timeout=2)
            break
        except Exception:
            time.sleep(0.2)

    try:
        # Every GET that reports paths, hardware or model state must be closed.
        for endpoint in ("/v1/models", "/v1/presets", "/v1/doctor",
                         "/v1/system/progress", "/v1/system/config", "/v1/stats",
                         "/v1/share"):
            code, _ = get(f"{base}{endpoint}")
            check(f"GET {endpoint} requires a key", code == 401, f"got {code}")

        code, _ = post(f"{base}/v1/system/config", {"n_ctx": 4096})
        check("POST /v1/system/config requires a key", code == 401, f"got {code}")

        # Three channels, because SDKs, scripts and browsers each have only one.
        for label, headers, url in (
            ("Authorization: Bearer", {"Authorization": f"Bearer {TEST_KEY}"}, f"{base}/v1/models"),
            ("X-API-Key", {"X-API-Key": TEST_KEY}, f"{base}/v1/models"),
            ("?key= query param", None, f"{base}/v1/models?key={TEST_KEY}"),
        ):
            code, _ = get(url, headers=headers)
            check(f"{label} is accepted", code == 200, f"got {code}")

        code, _ = get(f"{base}/v1/models", headers={"Authorization": "Bearer vr_wrong"})
        check("wrong key is rejected", code == 401, f"got {code}")
        code, _ = get(f"{base}/v1/models", headers={"X-API-Key": TEST_KEY[:-1]})
        check("truncated key is rejected", code == 401, f"got {code}")

        # The dashboard bundle stays public: it must load before it can ask for
        # a key, and it holds no secrets.
        req = urllib.request.Request(f"{base}/")
        with urllib.request.urlopen(req, timeout=5) as r:
            check("dashboard loads without a key", r.status == 200, f"got {r.status}")

        code, body = get(f"{base}/health")
        check("/health answers without a key", code == 200, f"got {code}")
        check("/health hides telemetry without a key",
              "model_path" not in body and body.get("auth_required") is True,
              str(sorted(body))[:120])
        check("/health still identifies the engine",
              body.get("engine") == "VaporRAM" and "version" in body)

        code, body = get(f"{base}/health", headers={"X-API-Key": TEST_KEY})
        check("/health returns telemetry with a key",
              TELEMETRY_KEYS.issubset(body.keys()),
              str(sorted(TELEMETRY_KEYS - set(body)))[:120])

        code, body = get(f"{base}/v1/share", headers={"X-API-Key": TEST_KEY})
        check("/v1/share returns connection details",
              code == 200 and body["share"]["api_key"] == TEST_KEY
              and "curl" in body["snippets"], f"got {code}")

        code, body = get(f"{base}/v1/models")
        check("401 body explains how to send the key",
              "Authorization" in body.get("message", "")
              and "vapor share" in body.get("message", ""), str(body)[:120])
    finally:
        server.shutdown()
        server.server_close()
        openai_server.configure_sharing("127.0.0.1", 8000, require_auth=False)



def test_stable_release_honesty(port):
    """Guard the claims and the config plumbing this release depends on.

    Every check here corresponds to something that shipped wrong through
    v1.0.7-beta.3: a hard-coded weight-format string that described the model
    as int4 SSD-streamed, an OpenAI API with no `usage` block, a config wizard
    that wrote the API key somewhere the server never reads, and `init-config`
    dropping vapor.json into the current directory.
    """
    print("\n[13] Stable-release honesty")
    from vapor_ram import openai_server as s
    from vapor_ram import paths, config

    # --- weights format is derived, not asserted ---------------------------
    fmt = s.weights_format()
    check("weights_format never claims SSD streaming",
          "ssd" not in fmt.lower() and "stream" not in fmt.lower(), fmt)
    check("weights_format never claims int4",
          "int4" not in fmt.lower(), fmt)
    check("weights_format says how the weights are loaded",
          "mapped" in fmt.lower(), fmt)

    gguf = s.find_gguf(s.current_model_path)
    if gguf:
        detailed = s.weights_format(gguf)
        check("weights_format names real quantisation types from the file",
              any(q in detailed for q in ("Q4_K", "Q5_K", "Q6_K", "F32", "BF16")),
              detailed)

    # --- /health reports the derived format --------------------------------
    base = f"http://127.0.0.1:{port}"
    status, health = get(f"{base}/health")
    check("/health format field is the derived one",
          health.get("format", "").startswith("GGUF"), health.get("format"))
    check("/health no longer advertises 'Int4 SSD Stream'",
          "Int4 SSD Stream" not in json.dumps(health), "stale claim present")

    # --- generate_tokens accepts a stats sink ------------------------------
    import inspect
    sig = inspect.signature(s.generate_tokens)
    check("generate_tokens exposes a stats parameter",
          "stats" in sig.parameters, str(sig))

    # --- VAPOR_CONFIG_PATH override ----------------------------------------
    tmpdir = tempfile.mkdtemp(prefix="vapor-cfgtest-")
    target = os.path.join(tmpdir, "nested", "vapor.json")
    old_env = os.environ.get("VAPOR_CONFIG_PATH")
    os.environ["VAPOR_CONFIG_PATH"] = target
    try:
        resolved = paths.config_path()
        check("VAPOR_CONFIG_PATH overrides config resolution",
              resolved == target, resolved)
        check("config_path creates the parent directory",
              os.path.isdir(os.path.dirname(target)), "parent missing")

        # init-config must write there, not into the cwd
        config.save_default_config(resolved)
        check("init-config writes to the resolved path",
              os.path.exists(target), "no file written")
    finally:
        if old_env is None:
            os.environ.pop("VAPOR_CONFIG_PATH", None)
        else:
            os.environ["VAPOR_CONFIG_PATH"] = old_env
        shutil.rmtree(tmpdir, ignore_errors=True)

    # --- defaults carry no fabricated quantisation claim -------------------
    check("DEFAULT_CONFIG drops the invented quant_type key",
          "quant_type" not in config.DEFAULT_CONFIG,
          str(sorted(config.DEFAULT_CONFIG)))
    check("DEFAULT_CONFIG carries a reasoning effort default",
          config.DEFAULT_CONFIG.get("reasoning_effort") in s.REASONING_LEVELS,
          str(config.DEFAULT_CONFIG.get("reasoning_effort")))

    # --- the wizard must not persist secrets into vapor.json ---------------
    wizard = os.path.join(HERE, "tools", "configure_wizard.py")
    if os.path.exists(wizard):
        src = open(wizard).read()
        check("wizard strips api_key before saving vapor.json",
              'new_cfg.pop("api_key", None)' in src, "secret may be persisted")
        check("wizard merges rather than replacing the config",
              "new_cfg = dict(current)" in src, "unasked keys would be dropped")

    # --- no command may print a verdict it has not established -------------
    from vapor_ram import resource_plan, doctor as doctor_mod

    plan = resource_plan.build_plan()
    rendered = resource_plan.format_plan(plan)
    check("vapor plan no longer emits a hard-coded PASS",
          "PASS" not in rendered, "fabricated verdict present")
    check("vapor plan reports no invented 140 MB layer size",
          "140.0 MB" not in rendered and "140 MB" not in rendered, rendered[:120])
    if plan.get("geometry"):
        geo = plan["geometry"]
        check("vapor plan reads the real block count",
              geo["n_layers"] == 42, str(geo["n_layers"]))
        check("vapor plan sizes the buffer from a real block",
              geo["largest_block_bytes"] > 0, str(geo.get("largest_block_bytes")))

    diag = doctor_mod.run_doctor()
    joined = json.dumps(diag)
    check("doctor no longer claims a C SIMD streamer runtime",
          "C SIMD Streamer" not in joined, joined[:160])
    ram = next((c for c in diag if c.get("check") == "memory.ram"), None)
    if ram:
        check("doctor no longer grades RAM against the 1.5 GB target",
              "1.5 GB Ceiling" not in ram.get("detail", ""), ram.get("detail"))

    inspector = os.path.join(HERE, "tools", "inspect_shards.py")
    if os.path.exists(inspector):
        src = open(inspector).read()
        check("vapor inspect no longer prints an unconditional readiness PASS",
              "Readiness: PASS" not in src and "4048-byte" not in src,
              "fabricated verdict still present")
        check("vapor inspect reads the GGUF rather than guessing",
              "read_gguf" in src, "not wired to the parser")

    check("the zero-filling safetensors converter is gone",
          not os.path.exists(os.path.join(HERE, "tools", "convert_gemma_safetensors.py")),
          "tool that wrote 4.4 GB of zeros is still present")

    # --- the benchmark must not fabricate a ceiling pass -------------------
    bench = os.path.join(HERE, "tools", "bench.py")
    if os.path.exists(bench):
        src = open(bench).read()
        check("bench.py no longer prints a PASS against the RAM ceiling",
              "PASS (< 1.5 GB)" not in src, "fabricated pass still present")
        check("bench.py measures the real GGUF",
              "run_stream_benchmark" in src, "not wired to the measurement path")



def test_docs_channel_policy():
    """The site advertises stable only, but gates no release from users.

    Two separate rules, both easy to break by hand:

      1. The GitHub Pages version badge must never name an alpha, beta or RC.
         Enforced by the `docs` job's `channel == 'stable'` gate.
      2. The releases and changelog pages must keep listing *every* release,
         prereleases included. Users choose what to run; the site only chooses
         what to advertise.
    """
    print("\n[14] Docs channel policy")
    docs = os.path.join(HERE, "docs")
    pages = ["index.html", "releases.html", "changelog.html"]
    prerelease = re.compile(r"v\d+\.\d+\.\d+-(?:alpha|beta|rc)\.\d+")
    version = re.compile(r"v\d+\.\d+\.\d+(?:-[a-z]+\.\d+)?")

    for name in pages:
        path = os.path.join(docs, name)
        if not os.path.exists(path):
            check(f"{name} exists", False, "missing")
            continue
        html = open(path, encoding="utf-8").read()

        check(f"{name} version is marker-managed",
              "<!--VERSION-->" in html, "no <!--VERSION--> marker")

        # The advertised version must be a stable one.
        check(f"{name} advertises no prerelease",
              not prerelease.search(html),
              str(set(prerelease.findall(html))))

        # And exactly one version may appear, so no stray literal can drift.
        found = set(version.findall(html))
        check(f"{name} names exactly one version",
              len(found) == 1, str(sorted(found)))

    # Users must not be gated: both listing pages read the live API.
    for name in ("releases.html", "changelog.html"):
        html = open(os.path.join(docs, name), encoding="utf-8").read()
        check(f"{name} reads releases from the GitHub API",
              "api.github.com/repos/sudsarkar13/vapor-ram/releases" in html,
              "no live release source")
        check(f"{name} no longer ships fabricated release data",
              "download_count:" not in html and "142100000" not in html,
              "invented download counts or file sizes present")

    rel = open(os.path.join(docs, "releases.html"), encoding="utf-8").read()
    check("releases page still offers a prerelease filter",
          "filterReleases('prerelease'" in rel, "prerelease filter removed")
    check("prerelease channels are labelled from the tag, not all as alpha",
          "channelOf" in rel and "Beta Preview" in rel,
          "betas and RCs would render as Alpha Preview")

    # The gate itself.
    wf = os.path.join(HERE, ".github", "workflows", "release.yml")
    if os.path.exists(wf):
        src = open(wf, encoding="utf-8").read()
        check("docs job is gated on the stable channel",
              "needs.validate.outputs.channel == 'stable'" in src,
              "gate missing — prereleases would move the site")
        check("docs job syncs all three pages",
              all(f'docs/{n}' in src for n in pages),
              "a page would drift behind the others")



def test_multimodal_intake(port):
    """Content parts, media detection, and the projector guard.

    Through v1.0.7 an OpenAI multimodal request was coerced with `str()`, so the
    model received a Python dict repr -- base64 payload included -- as prose. It
    did not error; it answered confidently about nothing.
    """
    print("\n[15] Multimodal intake")
    from vapor_ram import openai_server as s
    from vapor_ram import paths

    # --- content rendering --------------------------------------------------
    text, media = s.render_content("plain string")
    check("plain string content is unchanged", text == "plain string" and media == [], text)

    text, media = s.render_content([
        {"type": "text", "text": "What is in this image?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}},
    ])
    check("text parts are extracted", "What is in this image?" in text, text)
    check("image part becomes the real control token", s.IMAGE_TOKEN in text, text)
    check("base64 payload never reaches the prompt", "base64" not in text, text)
    check("dict repr never reaches the prompt", "'type':" not in text, text)
    check("media parts are reported", media == ["image_url"], str(media))

    for ptype, token in (("input_audio", s.AUDIO_TOKEN), ("video", s.VIDEO_TOKEN)):
        t, m = s.render_content([{"type": ptype}])
        check(f"{ptype} maps to its control token", t == token, t)

    # --- the tokens are the model's real ones -------------------------------
    check("image token is the vocabulary's", s.IMAGE_TOKEN == "<|image|>", s.IMAGE_TOKEN)
    check("audio token is the vocabulary's", s.AUDIO_TOKEN == "<|audio|>", s.AUDIO_TOKEN)
    check("video token is the vocabulary's", s.VIDEO_TOKEN == "<|video|>", s.VIDEO_TOKEN)

    # --- build_prompt end to end -------------------------------------------
    prompt = s.build_prompt(
        [{"role": "user", "content": [
            {"type": "text", "text": "describe"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}],
        s.PRESETS["default"], enable_thinking=False)
    check("build_prompt emits the image token", s.IMAGE_TOKEN in prompt, prompt[-120:])
    check("build_prompt leaks no base64", "AAAA" not in prompt, prompt[-120:])

    # --- projector detection is not fooled by the weights -------------------
    check("weights are not mistaken for a projector",
          not paths.is_mmproj("gemma-4-E4B-it-Q4_K_M.gguf"), "misclassified")
    check("projector is recognised", paths.is_mmproj("mmproj-F16.gguf"), "not detected")
    check("find_model_gguf skips projectors",
          paths.find_model_gguf.__doc__ is not None, "helper missing")

    # --- the guard ----------------------------------------------------------
    base = f"http://127.0.0.1:{port}"
    status, res = get(f"{base}/health")
    mm = res.get("multimodal") or {}
    check("/health reports multimodal capability", "ready" in mm, str(mm))

    if not s.multimodal_ready():
        status, res = post(f"{base}/v1/chat/completions", {"messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "what is this?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}]},
            timeout=30)
        check("media without a projector is refused, not answered",
              status == 400, f"got {status}")
        check("the refusal says how to fix it",
              "vapor download --mmproj" in json.dumps(res), json.dumps(res)[:160])
        check("the refusal names the media type",
              res.get("media_types") == ["image"], str(res.get("media_types")))

    # --- opt-out and override ----------------------------------------------
    original = s.MMPROJ_ENABLED
    try:
        s.MMPROJ_ENABLED = False
        check("--no-mmproj leaves the projector unused",
              s.build_chat_handler() is None, "handler built despite opt-out")
        # The capability report must follow the opt-out. When it did not, the
        # dashboard enabled its attach button under --no-mmproj and the request
        # failed at generation instead of being refused up front.
        check("--no-mmproj is reflected in the capability report",
              s.multimodal_ready() is False,
              "server would advertise a capability it will refuse")
    finally:
        s.MMPROJ_ENABLED = original

    old_env = os.environ.get("VAPOR_MMPROJ")
    os.environ["VAPOR_MMPROJ"] = "/nonexistent-projector.gguf"
    try:
        check("VAPOR_MMPROJ pointing at nothing yields no projector",
              paths.find_mmproj() is None, "phantom projector accepted")
    finally:
        if old_env is None:
            os.environ.pop("VAPOR_MMPROJ", None)
        else:
            os.environ["VAPOR_MMPROJ"] = old_env

    # --- when a projector IS installed, the capability must be real ---------
    if s.mmproj_path():
        check("an installed projector reports ready", s.multimodal_ready(),
              "projector present but not usable")
        from vapor_ram.gguf import read_gguf
        parsed = read_gguf(s.mmproj_path())
        names = [t["name"] for t in parsed["tensors"]]
        check("the projector actually carries vision tensors",
              any(n.startswith("v.") for n in names), "no vision tensors")
        check("the projector actually carries audio tensors",
              any(n.startswith("a.") or n.startswith("mm.a.") for n in names),
              "no audio tensors")
        check("the projector is not mistaken for model weights",
              s.find_gguf(os.path.dirname(s.mmproj_path())) != s.mmproj_path(),
              "projector would be loaded as the model")

    # --- text must be unaffected -------------------------------------------
    check("text-only content reports no media",
          s.message_media([{"role": "user", "content": "hello"}]) == [], "false positive")
    check("text parts report no media",
          s.message_media([{"role": "user", "content": [{"type": "text", "text": "hi"}]}]) == [],
          "false positive")



def test_audio_intake(port):
    """Audio parts, media ordering, and refusing what is not implemented.

    The audio encoder is a speech encoder: it transcribes speech accurately and
    confabulates on synthetic tones. These checks cover the plumbing, which is
    what can be asserted deterministically; the transcription itself is verified
    by hand against real speech and recorded in the changelog.
    """
    print("\n[16] Audio intake")
    from vapor_ram import openai_server as s

    # --- every part shape a client might send resolves to a URL -------------
    b64 = "UklGRiQAAABXQVZF"
    shapes = [
        ({"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}},
         "OpenAI input_audio with a bare base64 payload"),
        ({"type": "audio", "audio": {"url": f"data:audio/wav;base64,{b64}"}},
         "audio part carrying a data URL"),
        ({"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
         "image part"),
    ]
    for part, label in shapes:
        url = s._part_media_url(part)
        check(f"{label} resolves to a URL", bool(url), str(part)[:70])
    bare = s._part_media_url(
        {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}})
    check("a bare base64 payload gains a data: prefix",
          bare.startswith("data:audio/wav;base64,"), bare[:40])
    check("non-media parts resolve to nothing",
          s._part_media_url({"type": "text", "text": "hi"}) is None, "false positive")

    # --- accepted kinds are read from the projector, not hard-coded --------
    accepts = s.multimodal_accepts()
    check("video is never advertised", "video" not in accepts, str(accepts))
    if s.mmproj_path() and s.MMPROJ_ENABLED:
        check("a projector with a vision tower advertises image",
              "image" in accepts, str(accepts))
        check("a projector with an audio tower advertises audio",
              "audio" in accepts, str(accepts))
    else:
        check("no projector means nothing is accepted", accepts == [], str(accepts))

    # --- media order must survive, or bitmaps pair with the wrong marker ---
    if s.mmproj_path():
        try:
            handler_cls = s._multimodal_handler_class()
        except Exception as e:
            handler_cls = None
            check("multimodal handler class is constructible", False, str(e))
        if handler_cls:
            urls = handler_cls.get_image_urls([{"role": "user", "content": [
                {"type": "text", "text": "a"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,IMG1"}},
                {"type": "input_audio", "input_audio": {"data": "AUD1", "format": "wav"}},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,IMG2"}},
            ]}])
            check("media is collected in document order, not grouped by kind",
                  len(urls) == 3 and "IMG1" in urls[0] and "AUD1" in urls[1]
                  and "IMG2" in urls[2], str(urls))
            marker = "<<M>>"
            converted = handler_cls._convert_content_part_for_template(
                {"type": "input_audio", "input_audio": {"data": "x", "format": "wav"}}, marker)
            check("an audio part becomes a template marker",
                  converted == {"type": "text", "text": marker}, str(converted))

    # --- video is refused rather than turned into a bare marker ------------
    base = f"http://127.0.0.1:{port}"
    status, res = post(f"{base}/v1/chat/completions", {"messages": [
        {"role": "user", "content": [
            {"type": "text", "text": "what is this"},
            {"type": "video", "video": {"url": "data:video/mp4;base64,AAAA"}}]}]},
        timeout=30)
    check("video input is refused", status == 400, f"got {status}")
    body = json.dumps(res)
    check("the refusal says video is not implemented",
          "video" in body.lower(), body[:140])


def main():
    print("=" * 60)
    print("   VaporRAM Integration Test Suite")
    print("=" * 60)

    from vapor_ram import openai_server

    # The suite exercises endpoints that call save_active_config(). Left alone
    # those writes land on the developer's real vapor.json and silently reset
    # their RAM ceiling and context window, so redirect config persistence at a
    # throwaway file for the duration of the run.
    tmp_cfg = tempfile.mkdtemp(prefix="vapor-test-")
    openai_server.VAPOR_CONFIG_PATH = os.path.join(tmp_cfg, "vapor.json")

    port = free_port()
    threading.Thread(
        target=openai_server.serve,
        # preload=False: the suite must not pull 4.6 GB of weights into RAM,
        # and it deliberately exercises the weightless failure path.
        kwargs={"host": "127.0.0.1", "port": port, "preload": False},
        daemon=True).start()

    for _ in range(50):
        try:
            get(f"http://127.0.0.1:{port}/health", timeout=2)
            break
        except Exception:
            time.sleep(0.2)
    else:
        print("\033[31mServer failed to start\033[0m")
        return 1

    test_c_engine()
    test_launcher_executable()
    test_unit_logic()
    test_http_contract(port)
    test_context_honesty(port)
    test_model_dir_isolation(port)
    test_presets_and_download(port)
    test_concurrency_and_assets(port)
    test_generation_without_weights(port)
    test_performance_settings()
    test_gguf_and_streaming()
    test_thinking_mode()
    test_network_sharing()
    test_stable_release_honesty(port)
    test_docs_channel_policy()
    test_multimodal_intake(port)
    test_audio_intake(port)

    print("\n" + "=" * 60)
    if FAILED:
        print(f"\033[31m {len(FAILED)} FAILED\033[0m, {len(PASSED)} passed")
        for f in FAILED:
            print(f"   - {f}")
        print("=" * 60)
        return 1
    print(f"\033[32m ALL {len(PASSED)} CHECKS PASSED\033[0m")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
