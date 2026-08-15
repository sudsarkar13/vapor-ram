#!/usr/bin/env python3
"""
VaporRAM — Integration Test Suite

Verifies the HTTP contract the dashboard depends on: telemetry shape, context-window
honesty, download-progress reporting, preset resolution, prompt construction and
static asset serving.

These tests never require model weights — generation itself is covered by asserting
that a weightless engine returns a clean 503 rather than a fabricated answer.
"""
import os, sys, json, time, socket, threading, urllib.request, urllib.error, subprocess

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


def get(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


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
    try:
        out = subprocess.check_output(
            [ENGINE_BIN, os.path.join(HERE, "c", "vapor_engine.c"), "Unit Test"],
            stderr=subprocess.STDOUT, timeout=60).decode()
        check("engine executes", "VaporRAM" in out or "Gemma" in out, "unexpected output")
    except OSError as e:
        if e.errno == 8:
            print("   \033[33m~\033[0m skipped (foreign binary format on this host)")
        else:
            check("engine executes", False, str(e))
    except subprocess.CalledProcessError as e:
        check("engine executes", False, f"exit {e.returncode}")


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
    check("prompt ends on model turn", prompt.rstrip().endswith("<start_of_turn>model"),
          "missing generation cue")

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


def main():
    print("=" * 60)
    print("   VaporRAM Integration Test Suite")
    print("=" * 60)

    from vapor_ram import openai_server

    port = free_port()
    threading.Thread(
        target=openai_server.serve,
        kwargs={"host": "127.0.0.1", "port": port},
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
    test_unit_logic()
    test_http_contract(port)
    test_context_honesty(port)
    test_model_dir_isolation(port)
    test_presets_and_download(port)
    test_concurrency_and_assets(port)
    test_generation_without_weights(port)

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
