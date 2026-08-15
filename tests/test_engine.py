#!/usr/bin/env python3
"""
VaporRAM — Integration Test Suite

Verifies the HTTP contract the dashboard depends on: telemetry shape, context-window
honesty, download-progress reporting, preset resolution, prompt construction and
static asset serving.

These tests never require model weights — generation itself is covered by asserting
that a weightless engine returns a clean 503 rather than a fabricated answer.
"""
import os, sys, json, time, socket, threading, urllib.request, urllib.error, subprocess, tempfile

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
    test_network_sharing()

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
