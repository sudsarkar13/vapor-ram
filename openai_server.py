import os, sys, json, time, subprocess, mimetypes, threading, re, signal
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIST = os.path.join(HERE, "web", "dist")
ENGINE_BIN = os.path.join(HERE, "c", "vapor_engine")
DEFAULT_MODEL_DIR = os.path.join(HERE, "models", "gemma-4-E4B-it")
VAPOR_CONFIG_PATH = os.path.join(HERE, "vapor.json")
PRESETS_DIR = os.path.join(HERE, "presets")

# Gemma 4 E4B-it was trained with max_position_embeddings=131072 (sliding window 512).
# MODEL_MAX_CONTEXT is what the *architecture* allows; SAFE_GGUF_MAX_CONTEXT is what this
# engine will actually allocate. Anything above the safe cap is refused at the API boundary
# rather than silently clamped at generation time, so the value the UI shows is always the
# value the KV cache really uses.
MODEL_MAX_CONTEXT = 131072
SAFE_GGUF_MAX_CONTEXT = 16384
MIN_CONTEXT_WINDOW = 512
DEFAULT_CONTEXT_WINDOW = 8192

VERSION = "1.0.7-alpha.3"
MODEL_ID = "google/gemma-4-E4B-it"

# Architecture defaults match google/gemma-4-E4B-it's text_config. They are overwritten by
# read_model_architecture() when the active model directory ships a config.json, so the
# dashboard's KV-cache maths and the API's advertised shape come from one place.
MODEL_N_LAYERS = 42
MODEL_HIDDEN_DIM = 2560
MODEL_N_HEADS = 8
MODEL_N_KV_HEADS = 2
MODEL_HEAD_DIM = 256
MODEL_KV_SHARED_LAYERS = 18
MODEL_SLIDING_WINDOW = 512
LAYER_BUFFER_MB = 140

# Timings from the most recent generation. Empty until something has actually run —
# the dashboard renders "no data yet" rather than inventing numbers.
last_timings = {}
_timings_lock = threading.Lock()


def record_timings(**kwargs):
    with _timings_lock:
        last_timings.clear()
        last_timings.update(kwargs)


def read_model_architecture(model_dir):
    """Pull real layer/head counts from a HuggingFace config.json when present."""
    global MODEL_N_LAYERS, MODEL_HIDDEN_DIM, MODEL_N_HEADS, MODEL_N_KV_HEADS
    global MODEL_HEAD_DIM, MODEL_KV_SHARED_LAYERS, MODEL_SLIDING_WINDOW
    cfg_path = os.path.join(model_dir, "config.json") if os.path.isdir(model_dir) else None
    if not cfg_path or not os.path.exists(cfg_path):
        return False
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
    except Exception:
        return False
    text = cfg.get("text_config", cfg)
    MODEL_N_LAYERS = int(text.get("num_hidden_layers", MODEL_N_LAYERS))
    MODEL_HIDDEN_DIM = int(text.get("hidden_size", MODEL_HIDDEN_DIM))
    MODEL_N_HEADS = int(text.get("num_attention_heads", MODEL_N_HEADS))
    MODEL_N_KV_HEADS = int(text.get("num_key_value_heads", MODEL_N_KV_HEADS))
    MODEL_HEAD_DIM = int(text.get("head_dim", MODEL_HEAD_DIM))
    MODEL_KV_SHARED_LAYERS = int(text.get("num_kv_shared_layers", MODEL_KV_SHARED_LAYERS))
    MODEL_SLIDING_WINDOW = int(text.get("sliding_window", MODEL_SLIDING_WINDOW))
    return True


def clamp_context(requested):
    """Single source of truth for context sizing. Returns (effective, was_clamped)."""
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return DEFAULT_CONTEXT_WINDOW, True
    effective = max(MIN_CONTEXT_WINDOW, min(value, SAFE_GGUF_MAX_CONTEXT))
    return effective, effective != value


try:
    from config import load_config as _load_vapor_config
    _vapor_cfg = _load_vapor_config(VAPOR_CONFIG_PATH)
    n_ctx = int(_vapor_cfg.get("n_ctx", DEFAULT_CONTEXT_WINDOW))
    ram_ceiling_gb = float(_vapor_cfg.get("ram_ceiling_gb", 1.5))
except Exception:
    n_ctx = DEFAULT_CONTEXT_WINDOW
    ram_ceiling_gb = 1.5
n_ctx, _ = clamp_context(n_ctx)

try:
    import doctor
except Exception:
    doctor = None

current_model_path = DEFAULT_MODEL_DIR
download_progress = {"status": "idle", "percent": 0, "message": "Ready",
                     "downloaded_mb": 0.0, "total_mb": 0.0, "speed_mbps": 0.0}
completed_reset_timer = None
server_instance = None
llama_model_cache = {}
_n_ctx_lock = threading.Lock()

# llama.cpp holds one mutable context per model; generations must not interleave.
# Held only around token production, so /health and /progress polls stay responsive.
_generation_lock = threading.Lock()

# Lifecycle of the GGUF weights, polled by the dashboard so a 4.7 GB model load
# reads as "loading" instead of an indistinguishable hang.
model_state = {"status": "idle", "message": "No model loaded yet", "model_path": None, "n_ctx": None}
_model_state_lock = threading.Lock()


def set_model_state(status, message, path=None, ctx=None):
    with _model_state_lock:
        model_state["status"] = status
        model_state["message"] = message
        if path is not None:
            model_state["model_path"] = path
        if ctx is not None:
            model_state["n_ctx"] = ctx


def get_model_state():
    with _model_state_lock:
        return dict(model_state)


# Host RAM is re-read per request (cheap /proc/meminfo parse) but cached briefly so a
# 3-second dashboard poll from several tabs doesn't syscall-storm.
_ram_cache = {"ts": 0.0, "total": 16.0, "avail": 8.0}
_ram_cache_lock = threading.Lock()


def get_live_ram(max_age=1.0):
    now = time.monotonic()
    with _ram_cache_lock:
        if now - _ram_cache["ts"] < max_age:
            return _ram_cache["total"], _ram_cache["avail"]
    total, avail = 16.0, 8.0
    if doctor is not None:
        try:
            total, avail = doctor.get_ram_info()
        except Exception:
            pass
    with _ram_cache_lock:
        _ram_cache.update({"ts": now, "total": total, "avail": avail})
    return total, avail


def get_process_rss_mb():
    """Actual resident set size of this process. None when unavailable."""
    try:
        with open("/proc/self/statm") as f:
            pages = int(f.read().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024), 2)
    except Exception:
        pass
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports kilobytes, macOS reports bytes.
        divisor = 1024 if sys.platform != "darwin" else 1024 * 1024
        return round(peak / divisor, 2)
    except Exception:
        return None


def load_presets():
    """Read presets/*.json. These carry the system_instruction and sampling params
    that actually get applied to generation."""
    presets = {
        "default": {
            "id": "default",
            "name": "Default",
            "system_instruction": "",
            "temperature": 0.2,
            "top_p": 0.95,
        }
    }
    if os.path.isdir(PRESETS_DIR):
        for fname in sorted(os.listdir(PRESETS_DIR)):
            if not fname.endswith(".json"):
                continue
            pid = fname[:-5]
            try:
                with open(os.path.join(PRESETS_DIR, fname)) as f:
                    data = json.load(f)
                presets[pid] = {
                    "id": pid,
                    "name": data.get("name", pid.title()),
                    "system_instruction": data.get("system_instruction", ""),
                    "temperature": float(data.get("temperature", 0.2)),
                    "top_p": float(data.get("top_p", 0.95)),
                }
            except Exception as e:
                sys.stderr.write(f"[Presets] Skipping malformed {fname}: {e}\n")
    return presets


PRESETS = load_presets()

def portable_model_dir(path):
    """Store paths inside the install root as './relative' so a committed
    vapor.json stays valid on any machine; keep external paths absolute."""
    try:
        rel = os.path.relpath(path, HERE)
        if not rel.startswith(".."):
            return "./" + rel if not rel.startswith("./") else rel
    except ValueError:
        pass
    return path


def save_active_config():
    try:
        cfg = {
            "model_id": MODEL_ID,
            "model_dir": portable_model_dir(current_model_path),
            "ram_ceiling_gb": ram_ceiling_gb,
            "n_ctx": n_ctx
        }
        with open(VAPOR_CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        sys.stderr.write(f"[Config] Error saving {VAPOR_CONFIG_PATH}: {e}\n")

# Per-model slot accounting. VaporRAM runs in single-tenant dedicated mode,
# so each loaded model has exactly 1 KV-cache slot reserved for the active chat.
# n_parallel=1 is enforced by the 1.5 GB RAM ceiling; the counter increments
# while a generation is in flight and decrements when it returns.
slot_registry = {}
_slot_lock = threading.Lock()


def _slot_begin(model_id):
    with _slot_lock:
        entry = slot_registry.setdefault(model_id, {"active": 0, "total": 1})
        entry["active"] += 1
        return entry["active"], entry["total"]


def _slot_end(model_id):
    with _slot_lock:
        entry = slot_registry.setdefault(model_id, {"active": 0, "total": 1})
        entry["active"] = max(0, entry["active"] - 1)
        return entry["active"], entry["total"]


def _slot_snapshot(model_id):
    with _slot_lock:
        entry = slot_registry.setdefault(model_id, {"active": 0, "total": 1})
        return {"active": entry["active"], "total": entry["total"]}

def reset_progress_idle():
    global download_progress
    download_progress = {"status": "idle", "percent": 0, "message": "Ready"}

def clean_path(path_str):
    p = path_str.rstrip("/")
    if not p:
        return "/"
    while p.startswith("/v1/v1"):
        p = "/v1" + p[6:]
    return p

WEIGHT_SUFFIXES = (".gguf", ".safetensors", ".bin", ".json")


def weights_available(path):
    """True when `path` is a GGUF file or a directory holding recognisable weights."""
    if not path or not os.path.exists(path):
        return False
    if os.path.isfile(path):
        return path.endswith(".gguf")
    try:
        return any(f.endswith(WEIGHT_SUFFIXES) for f in os.listdir(path))
    except OSError:
        return False


def find_gguf(path):
    """Resolve a model path to a concrete .gguf file, or None."""
    if not path or not os.path.exists(path):
        return None
    if os.path.isfile(path):
        return path if path.endswith(".gguf") else None
    try:
        for f in sorted(os.listdir(path)):
            if f.endswith(".gguf"):
                return os.path.join(path, f)
    except OSError:
        pass
    return None


def telemetry_snapshot():
    """Shared live-metrics block. Every status endpoint returns the same shape so the
    dashboard reads one contract instead of four slightly different ones."""
    total, avail = get_live_ram()
    state = get_model_state()
    return {
        "n_ctx": n_ctx,
        "model_max_context": MODEL_MAX_CONTEXT,
        "safe_max_context": SAFE_GGUF_MAX_CONTEXT,
        "min_context": MIN_CONTEXT_WINDOW,
        "architecture": {
            "n_layers": MODEL_N_LAYERS,
            "hidden_dim": MODEL_HIDDEN_DIM,
            "n_heads": MODEL_N_HEADS,
            "n_kv_heads": MODEL_N_KV_HEADS,
            "head_dim": MODEL_HEAD_DIM,
            "kv_shared_layers": MODEL_KV_SHARED_LAYERS,
            "sliding_window": MODEL_SLIDING_WINDOW,
            "layer_buffer_mb": LAYER_BUFFER_MB,
        },
        "ram_ceiling_gb": ram_ceiling_gb,
        "total_ram_gb": round(total, 2),
        "avail_ram_gb": round(avail, 2),
        "process_rss_mb": get_process_rss_mb(),
        "model_path": current_model_path,
        "model_available": weights_available(current_model_path),
        "model_state": state,
        "slots": _slot_snapshot(current_model_path),
    }


def apply_model_dir(raw):
    """Validate and activate a model directory.

    Relative paths resolve against the install root, not the shell's CWD, so
    `vapor serve` behaves identically no matter where it is launched from.
    Returns (ok, message, resolved_path).
    """
    global current_model_path
    candidate = str(raw or "").strip()
    if not candidate:
        return False, "Model path is empty", current_model_path
    resolved = os.path.expanduser(candidate)
    if not os.path.isabs(resolved):
        resolved = os.path.abspath(os.path.join(HERE, resolved))
    if not os.path.exists(resolved):
        return False, f"Path '{resolved}' does not exist on the host", current_model_path
    if not weights_available(resolved):
        return False, f"'{resolved}' contains no .gguf/.safetensors weights", current_model_path

    previous = current_model_path
    current_model_path = resolved
    if resolved != previous:
        read_model_architecture(resolved)
        # A different directory means a different model; drop stale Llama handles.
        with _n_ctx_lock:
            llama_model_cache.clear()
        set_model_state("idle", "Model directory changed; loads on next request", path=resolved)
    gguf = find_gguf(resolved)
    detail = f" ({os.path.basename(gguf)})" if gguf else " (no .gguf yet)"
    return True, f"Model dir set to {resolved}{detail}", resolved


def apply_context(effective):
    """Set the active context window. Returns (changed, previous_value)."""
    global n_ctx
    with _n_ctx_lock:
        old = n_ctx
        if effective == old:
            return False, old
        n_ctx = effective
        for cached_path, cached_llm in list(llama_model_cache.items()):
            if getattr(cached_llm, "_vapor_ctx_size", None) != n_ctx:
                llama_model_cache.pop(cached_path, None)
    set_model_state("idle", f"Context changed to {effective}; reloads on next request", ctx=effective)
    return True, old


def restore_saved_model_dir():
    """Re-activate the model directory persisted in vapor.json.

    Previously the value was written on save but never read back, so a custom
    directory silently reverted to the default on every restart.
    """
    try:
        saved = _vapor_cfg.get("model_dir") if "_vapor_cfg" in globals() else None
    except Exception:
        saved = None
    if not saved:
        return
    ok, _msg, _resolved = apply_model_dir(saved)
    if not ok:
        sys.stderr.write(
            f"\033[33m[Config] Saved model_dir '{saved}' is unusable; "
            f"falling back to {current_model_path}\033[0m\n")


def download_default_repo():
    try:
        sys.path.insert(0, os.path.join(HERE, "tools"))
        import download_model  # type: ignore[import-not-found]
        return download_model.REPO_ID
    except Exception:
        return "unsloth/gemma-4-E4B-it-GGUF"


def scan_system_for_models():
    found = []
    search_paths = [
        DEFAULT_MODEL_DIR,
        os.path.expanduser("~/models/gemma-4-E4B-it"),
        os.path.expanduser("~/.cache/huggingface/hub/models--google--gemma-4-E4B-it"),
        os.path.expanduser("~/.cache/huggingface/hub/models--google--gemma-4-E4B-it-qat-q4_0-gguf"),
        os.path.expanduser("~/.cache/huggingface/hub/models--unsloth--gemma-4-E4B-it-GGUF"),
        os.path.expanduser("~/Downloads/gemma-4-E4B-it"),
        os.path.expanduser("~/Ubuntu-Owner/models")
    ]
    seen = set()
    for p in search_paths:
        if p in seen:
            continue
        seen.add(p)
        gguf = find_gguf(p)
        found.append({
            "path": p,
            "available": weights_available(p),
            "has_gguf": gguf is not None,
            "gguf_name": os.path.basename(gguf) if gguf else None,
            "size_gb": round(os.path.getsize(gguf) / (1024 ** 3), 2) if gguf else None,
            "is_active": os.path.abspath(p) == os.path.abspath(current_model_path),
        })
    return found

class EngineError(RuntimeError):
    """Raised when generation cannot proceed (no weights, load failure, backend missing)."""


def _as_float(value, fallback):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def resolve_preset(preset_id, messages):
    """Pick the active persona.

    Accepts an explicit `preset` field, and also tolerates the older client
    convention of smuggling the name in a `Preset: <id>` system message.
    """
    if preset_id and preset_id in PRESETS:
        return PRESETS[preset_id]
    for msg in messages:
        if msg.get("role") == "system":
            match = re.match(r"^\s*preset\s*:\s*(\S+)\s*$", str(msg.get("content", "")), re.I)
            if match and match.group(1).lower() in PRESETS:
                return PRESETS[match.group(1).lower()]
    return PRESETS["default"]


def build_prompt(messages, preset):
    """Render the full conversation into Gemma's instruction format.

    The whole history is included (trimmed to the newest turns that fit), so
    follow-up questions actually see what came before.
    """
    system_parts = []
    if preset.get("system_instruction"):
        system_parts.append(preset["system_instruction"])
    for msg in messages:
        if msg.get("role") == "system":
            content = str(msg.get("content", "")).strip()
            # Skip the "Preset: x" marker; it is routing metadata, not an instruction.
            if content and not re.match(r"^\s*preset\s*:\s*\S+\s*$", content, re.I):
                system_parts.append(content)

    turns = [m for m in messages if m.get("role") in ("user", "assistant")]

    # Reserve room for the reply: roughly 4 characters per token is a safe estimate.
    char_budget = max(1024, (n_ctx - 512) * 4)
    rendered = []
    total = sum(len(p) for p in system_parts)
    for msg in reversed(turns):
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        block = (f"<start_of_turn>user\n{content}<end_of_turn>\n"
                 if msg["role"] == "user" else
                 f"<start_of_turn>model\n{content}<end_of_turn>\n")
        if total + len(block) > char_budget and rendered:
            break
        total += len(block)
        rendered.append(block)
    rendered.reverse()

    prefix = ""
    if system_parts:
        prefix = "<start_of_turn>user\n" + "\n\n".join(system_parts) + "<end_of_turn>\n"
        if rendered and rendered[0].startswith("<start_of_turn>user\n"):
            # Fold the system instruction into the first user turn — Gemma has no
            # separate system role.
            body = rendered[0][len("<start_of_turn>user\n"):]
            rendered[0] = "<start_of_turn>user\n" + "\n\n".join(system_parts) + "\n\n" + body
            prefix = ""

    return prefix + "".join(rendered) + "<start_of_turn>model\n"


def get_llama(gguf_file):
    """Return a Llama handle for `gguf_file` at the current n_ctx, loading if needed.

    Publishes load state so the dashboard can distinguish "loading 4.7 GB of weights"
    from "generating" — previously both looked like an unexplained pause.
    """
    try:
        from llama_cpp import Llama
    except ImportError:
        set_model_state("loading", "Installing llama-cpp-python backend…")
        sys.stderr.write("\033[36m[VaporRAM Auto-Setup] Installing llama-cpp-python GGUF engine...\033[0m\n")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--break-system-packages", "llama-cpp-python"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            from llama_cpp import Llama
        except Exception as e:
            set_model_state("error", f"llama-cpp-python unavailable: {e}")
            raise EngineError(
                "llama-cpp-python is not installed and automatic installation failed. "
                "Install it with: pip install llama-cpp-python") from e

    target_ctx = n_ctx
    cached = llama_model_cache.get(gguf_file)
    if cached is not None and getattr(cached, "_vapor_ctx_size", None) == target_ctx:
        return cached

    name = os.path.basename(gguf_file)
    if cached is not None:
        set_model_state("loading",
                        f"Reallocating KV cache {getattr(cached, '_vapor_ctx_size', '?')} → {target_ctx}",
                        path=gguf_file, ctx=target_ctx)
        sys.stderr.write(f"\033[36m[GGUF Engine] Reallocating KV cache -> {target_ctx}\033[0m\n")
        llama_model_cache.pop(gguf_file, None)
    else:
        set_model_state("loading", f"Loading {name} (n_ctx={target_ctx})…",
                        path=gguf_file, ctx=target_ctx)
        sys.stderr.write(f"\033[36m[GGUF Engine] Loading {gguf_file} (n_ctx={target_ctx})\033[0m\n")

    started = time.perf_counter()
    try:
        llm = Llama(model_path=gguf_file, n_ctx=target_ctx, n_threads=os.cpu_count() or 4,
                    verbose=False)
        applied_ctx = target_ctx
    except Exception as alloc_err:
        fallback = max(MIN_CONTEXT_WINDOW, min(4096, target_ctx))
        sys.stderr.write(
            f"\033[33m[GGUF Engine] Context allocation failed ({alloc_err}); retrying at n_ctx={fallback}\033[0m\n")
        set_model_state("loading", f"Retrying {name} at reduced context {fallback}…",
                        path=gguf_file, ctx=fallback)
        try:
            llm = Llama(model_path=gguf_file, n_ctx=fallback, n_threads=os.cpu_count() or 4,
                        verbose=False)
            applied_ctx = fallback
        except Exception as e:
            set_model_state("error", f"Failed to load {name}: {e}", path=gguf_file)
            raise EngineError(f"Could not load GGUF model {name}: {e}") from e
        # Reflect the reduced window everywhere, rather than reporting the size we wanted.
        apply_context(fallback)

    llm._vapor_ctx_size = applied_ctx
    llama_model_cache[gguf_file] = llm
    load_ms = round((time.perf_counter() - started) * 1000, 2)
    set_model_state("ready", f"{name} ready (n_ctx={applied_ctx}, loaded in {load_ms / 1000:.1f}s)",
                    path=gguf_file, ctx=applied_ctx)
    sys.stderr.write(f"\033[32m[GGUF Engine] {name} ready in {load_ms / 1000:.1f}s\033[0m\n")
    return llm


def generate_tokens(messages, preset, sampling, max_tokens):
    """Yield generated text pieces as llama.cpp decodes them.

    This is a generator: the caller can forward each piece to the client immediately.
    """
    gguf_file = find_gguf(current_model_path)
    if not gguf_file:
        raise EngineError(
            f"No .gguf weights found in '{current_model_path}'. "
            f"Download the model from the dashboard or run: ./vapor download")

    prompt = build_prompt(messages, preset)

    # llama.cpp keeps one mutable context per model; concurrent generations would
    # corrupt it. Poll endpoints run on other threads and are unaffected.
    with _generation_lock:
        llm = get_llama(gguf_file)
        _slot_begin(gguf_file)
        try:
            stream = llm(
                prompt,
                max_tokens=max_tokens,
                temperature=sampling.get("temperature", 0.2),
                top_p=sampling.get("top_p", 0.95),
                stop=["<end_of_turn>", "<start_of_turn>", "<|endoftext|>"],
                stream=True,
            )
            for chunk in stream:
                piece = chunk["choices"][0].get("text", "")
                if piece:
                    yield piece
        except EngineError:
            raise
        except Exception as e:
            raise EngineError(f"Generation failed: {e}") from e
        finally:
            _slot_end(gguf_file)


# Restore persisted model directory and read the model's real geometry at import,
# so CLI entry points and the server agree without extra wiring.
restore_saved_model_dir()
read_model_architecture(current_model_path)


def generate_text(messages, preset_id=None, max_tokens=8192, on_chunk=None):
    """Blocking generation helper for the CLI.

    `messages` is a full OpenAI-style history. `on_chunk` receives each piece as it
    is produced so the terminal can stream just like the dashboard does.
    """
    preset = PRESETS.get(preset_id or "default", PRESETS["default"])
    sampling = {"temperature": preset["temperature"], "top_p": preset["top_p"]}
    parts = []
    for piece in generate_tokens(messages, preset, sampling, max_tokens):
        parts.append(piece)
        if on_chunk:
            on_chunk(piece)
    return "".join(parts)


class VaporRequestHandler(BaseHTTPRequestHandler):
    api_key = None

    def log_message(self, format, *args):
        """
        Vite / Next.js Style Clean Colored Console Logging
        Suppresses repetitive polling background telemetry, displaying only major events & colored errors.
        """
        path = getattr(self, "path", "")
        if any(p in path for p in ("/progress", "/health", "/stats", "/cortex", "/profile", "/assets/")):
            return

        code = args[1] if len(args) > 1 else "200"
        code = str(code) if code is not None else "???"
        method = self.command if hasattr(self, "command") else "GET"

        if code.startswith("2") or code.startswith("3"):
            color_code = "\033[32m" # Green
            color_method = "\033[36m" # Cyan
        else:
            color_code = "\033[31m" # Red
            color_method = "\033[35m" # Purple

        reset = "\033[0m"
        dim = "\033[90m"

        try:
            sys.stderr.write(f"{color_method}[{method}]{reset} {path} {color_code}{code}{reset} {dim}(vapor-engine v{VERSION})\033[0m\n")
            sys.stderr.flush()
        except (BrokenPipeError, ConnectionResetError, ValueError):
            pass

    def _send_json(self, data, status=200):
        try:
            body = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Client hung up before we finished flushing. Nothing useful we can do;
            # the request itself was handled and the response was on its way out.
            pass

    def _check_auth(self):
        if not VaporRequestHandler.api_key:
            return True
        auth_header = self.headers.get("Authorization", "")
        api_header = self.headers.get("X-API-Key", "")
        token = auth_header.replace("Bearer ", "").strip() or api_header.strip()
        return token == VaporRequestHandler.api_key

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.end_headers()

    def do_GET(self):
        global current_model_path, download_progress, completed_reset_timer
        parsed = urlparse(self.path)
        path = clean_path(parsed.path)

        if path.endswith("/health"):
            tele = telemetry_snapshot()
            gguf = find_gguf(current_model_path)
            return self._send_json({
                "status": "ok",
                "engine": "VaporRAM",
                "version": VERSION,
                "model": MODEL_ID,
                "active_model": MODEL_ID,
                "format": "GGUF / Int4 SSD Stream",
                "gguf_file": os.path.basename(gguf) if gguf else None,
                "connection": "CONNECTED" if tele["model_available"] else "NO_WEIGHTS",
                **tele,
            })

        if path.endswith("/presets"):
            return self._send_json({
                "object": "list",
                "data": list(PRESETS.values()),
            })

        if path.endswith("/doctor") or path.endswith("/system/doctor"):
            # Runs the same inspector as `./vapor doctor` — no hardcoded verdicts.
            if doctor is None:
                return self._send_json(
                    {"error": "Unavailable", "message": "doctor module failed to import"}, status=503)
            try:
                checks = doctor.run_doctor()
            except Exception as e:
                return self._send_json(
                    {"error": "Doctor Failed", "message": str(e)}, status=500)
            return self._send_json({
                "status": "ok",
                "version": VERSION,
                "checks": checks,
                "text": doctor.format_doctor(checks),
                **telemetry_snapshot(),
            })

        if path.endswith("/models"):
            tele = telemetry_snapshot()
            gguf = find_gguf(current_model_path)
            return self._send_json({
                "object": "list",
                "data": [{
                    "id": MODEL_ID,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "vapor-ram",
                    "architecture": "GemmaForCausalLM",
                    "version": VERSION,
                    "n_layers": MODEL_N_LAYERS,
                    "hidden_dim": MODEL_HIDDEN_DIM,
                    "n_heads": MODEL_N_HEADS,
                    "n_kv_heads": MODEL_N_KV_HEADS,
                    "head_dim": MODEL_HEAD_DIM,
                    "context_length": n_ctx,
                    "gguf_file": os.path.basename(gguf) if gguf else None,
                    "availability": "Ready (GGUF Model Installed)" if tele["model_available"] else "Download Required",
                    **tele,
                }]
            })

        # Config GET endpoint
        if path.endswith("/config") or path.endswith("/system/config"):
            return self._send_json({
                "status": "ok",
                "version": VERSION,
                **telemetry_snapshot(),
            })

        # Progress polling & system scan GET endpoints
        if path.endswith("/progress") or path.endswith("/system/progress") or path.endswith("/scan") or path.endswith("/system/scan"):
            res_prog = dict(download_progress)
            if res_prog.get("status") in ("completed", "error"):
                if completed_reset_timer is None or not completed_reset_timer.is_alive():
                    completed_reset_timer = threading.Timer(6.0, reset_progress_idle)
                    completed_reset_timer.start()

            scanned = scan_system_for_models()
            return self._send_json({
                "status": "ok",
                "version": VERSION,
                "message": f"Scanned {len(scanned)} directories for GGUF models.",
                "active_path": current_model_path,
                "scanned_models": scanned,
                "download_progress": res_prog,
                **telemetry_snapshot(),
            })

        # Brain Cortex & Profiling metrics endpoints
        if any(path.endswith(suffix) for suffix in ("/stats", "/cortex", "/profile")):
            tele = telemetry_snapshot()
            timings = dict(last_timings)
            layers_data = [{
                "layer": i,
                "status": "resident" if tele["model_available"] else "no_weights",
                "buffer_mb": LAYER_BUFFER_MB,
            } for i in range(1, MODEL_N_LAYERS + 1)]
            rss = tele["process_rss_mb"]
            return self._send_json({
                "status": "active",
                "version": VERSION,
                "model": MODEL_ID,
                "backend": "llama-cpp-python (GGUF, mmap)",
                "kv_slots": n_ctx,
                "ram_usage_percent": (
                    round(100.0 * rss / (tele["total_ram_gb"] * 1024), 2)
                    if rss and tele["total_ram_gb"] else None),
                "timings": timings,
                "layers": layers_data,
                **tele,
            })

        # Serve static Web UI assets from web/dist
        if path == "/":
            path = "/index.html"
        
        file_path = os.path.normpath(os.path.join(WEB_DIST, path.lstrip("/")))
        if os.path.exists(file_path) and os.path.isfile(file_path) and file_path.startswith(WEB_DIST):
            mime, _ = mimetypes.guess_type(file_path)
            with open(file_path, "rb") as f:
                content = f.read()
            try:
                self.send_response(200)
                self.send_header("Content-Type", mime or "application/octet-stream")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        self._send_json({"error": "Not Found", "message": f"Endpoint {path} not found"}, status=404)

    def do_POST(self):
        global current_model_path, download_progress, n_ctx
        if not self._check_auth():
            return self._send_json({"error": "Unauthorized API key", "message": "Unauthorized API key"}, status=401)

        parsed = urlparse(self.path)
        path = clean_path(parsed.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        # Interactive Server Control: Stop Server Endpoint
        if path.endswith("/stop") or path.endswith("/system/stop"):
            self._send_json({"status": "ok", "message": "VaporRAM Server stopping cleanly..."})
            def delayed_stop():
                time.sleep(0.5)
                sys.stderr.write("\033[33m[VaporRAM] Server stopped via Web UI command.\033[0m\n")
                os._exit(0)
            threading.Thread(target=delayed_stop, daemon=True).start()
            return

        # Interactive Server Control: Restart Server Endpoint
        if path.endswith("/restart") or path.endswith("/system/restart"):
            self._send_json({"status": "ok", "message": "Restarting VaporRAM server in-place..."})
            def delayed_restart():
                time.sleep(0.5)
                sys.stderr.write("\033[36m[VaporRAM] Restarting server process in same terminal window...\033[0m\n")
                os.execv(sys.executable, [sys.executable] + sys.argv)
            threading.Thread(target=delayed_restart, daemon=True).start()
            return

        # Set custom system model path endpoint
        if path.endswith("/set_model_path") or path.endswith("/system/set_model_path"):
            ok, msg, resolved = apply_model_dir(payload.get("path", ""))
            if not ok:
                return self._send_json({"error": "Invalid Model Path", "message": msg}, status=400)
            save_active_config()
            return self._send_json({"status": "ok", "active_path": resolved, "message": msg,
                                    **telemetry_snapshot()})

        # Update persistent server config (RAM ceiling, n_ctx, model_dir)
        if path.endswith("/config") or path.endswith("/system/config"):
            global ram_ceiling_gb
            updated = False
            msg_parts = []
            warnings = []

            if "ram_ceiling_gb" in payload:
                try:
                    new_ceiling = float(payload["ram_ceiling_gb"])
                    if 0.5 <= new_ceiling <= 128.0:
                        if new_ceiling != ram_ceiling_gb:
                            ram_ceiling_gb = new_ceiling
                            updated = True
                            msg_parts.append(f"RAM ceiling set to {ram_ceiling_gb:.1f} GB")
                    else:
                        warnings.append("ram_ceiling_gb must be between 0.5 and 128.0 GB")
                except (TypeError, ValueError):
                    warnings.append("ram_ceiling_gb must be a number")

            if "n_ctx" in payload:
                effective, was_clamped = clamp_context(payload["n_ctx"])
                if was_clamped:
                    warnings.append(
                        f"Requested n_ctx={payload['n_ctx']} exceeds this engine's safe "
                        f"limit; applied {effective} instead")
                changed, old_ctx = apply_context(effective)
                if changed:
                    updated = True
                    msg_parts.append(f"n_ctx adjusted {old_ctx} -> {effective}")

            # Only touch the model directory when the caller actually asked to. Previously
            # every config save re-sent model_dir and silently overwrote the active path.
            if payload.get("model_dir"):
                ok, msg, _ = apply_model_dir(payload["model_dir"])
                if ok:
                    updated = True
                    msg_parts.append(msg)
                else:
                    warnings.append(msg)

            if updated:
                save_active_config()

            return self._send_json({
                "status": "ok",
                "updated": updated,
                "warnings": warnings,
                "message": ". ".join(msg_parts) if msg_parts else (
                    "; ".join(warnings) if warnings else "No changes applied."),
                **telemetry_snapshot(),
            })

        # Adjust the active KV-cache context window at runtime. The next request
        # rebuilds the Llama instance if the new size doesn't match the cache.
        if path.endswith("/context") or path.endswith("/system/context"):
            if "n_ctx" not in payload:
                return self._send_json({"error": "Bad Request", "message": "n_ctx is required"}, status=400)
            try:
                requested = int(payload["n_ctx"])
            except (TypeError, ValueError):
                return self._send_json({"error": "Bad Request", "message": "n_ctx must be an integer"}, status=400)
            if requested < MIN_CONTEXT_WINDOW:
                return self._send_json({
                    "error": "Below Minimum",
                    "message": f"n_ctx must be at least {MIN_CONTEXT_WINDOW} tokens"}, status=400)
            if requested > SAFE_GGUF_MAX_CONTEXT:
                # Refuse loudly instead of accepting and quietly running something smaller.
                return self._send_json({
                    "error": "Above Safe Maximum",
                    "message": (
                        f"This engine allocates at most {SAFE_GGUF_MAX_CONTEXT} tokens of KV cache. "
                        f"The architecture supports {MODEL_MAX_CONTEXT}, but allocating that here "
                        f"would exceed available memory."),
                    "safe_max_context": SAFE_GGUF_MAX_CONTEXT,
                    "model_max_context": MODEL_MAX_CONTEXT,
                }, status=400)

            changed, old_ctx = apply_context(requested)
            if changed:
                save_active_config()
            return self._send_json({
                "status": "ok",
                "old_n_ctx": old_ctx,
                "changed": changed,
                "message": (
                    f"Context window adjusted {old_ctx} -> {n_ctx}. KV cache rebuilds on next request."
                    if changed else f"Context window already {n_ctx}."),
                **telemetry_snapshot(),
            })

        # Trigger model weight downloader for GGUF model from Hugging Face
        if any(path.endswith(suffix) for suffix in ("/download_model", "/system/download_model", "/models/download")):
            global download_progress
            if download_progress.get("status") == "downloading":
                return self._send_json({
                    "status": "already_running",
                    "message": "A download is already in progress.",
                    "download_progress": dict(download_progress),
                }, status=409)

            repo = (payload.get("repo") or "").strip() or None
            dest = (payload.get("dest") or "").strip() or None
            dest_abs = os.path.abspath(os.path.join(HERE, dest)) if dest and not os.path.isabs(dest) else dest

            # Publish "downloading" synchronously so the very next poll shows progress
            # instead of a window where the UI still reads idle.
            download_progress = {"status": "downloading", "percent": 0,
                                 "message": "Starting download…", "downloaded_mb": 0.0,
                                 "total_mb": 0.0, "speed_mbps": 0.0}

            def run_dl():
                global download_progress
                sys.path.insert(0, os.path.join(HERE, "tools"))
                try:
                    import download_model  # type: ignore[import-not-found]

                    def dl_cb(pct, msg, downloaded_mb=0.0, total_mb=0.0, speed_mbps=0.0):
                        global download_progress
                        download_progress = {
                            "status": "completed" if pct >= 100 else "downloading",
                            "percent": int(pct),
                            "message": msg,
                            "downloaded_mb": round(downloaded_mb, 1),
                            "total_mb": round(total_mb, 1),
                            "speed_mbps": round(speed_mbps, 2),
                        }

                    target = download_model.run_full_download(dl_cb, repo_id=repo, dest_dir=dest_abs)
                    if target and os.path.isdir(os.path.dirname(target)):
                        apply_model_dir(os.path.dirname(target))
                        save_active_config()
                except Exception as e:
                    download_progress = {"status": "error", "percent": 0,
                                         "message": f"Download failed: {e}",
                                         "downloaded_mb": 0.0, "total_mb": 0.0, "speed_mbps": 0.0}

            threading.Thread(target=run_dl, daemon=True).start()
            return self._send_json({
                "status": "ok",
                "message": f"Downloading GGUF weights from {repo or download_default_repo()}…",
                "download_progress": dict(download_progress),
            })

        if not any(path.endswith(suffix) for suffix in ("/chat/completions", "/completions", "/responses")):
            return self._send_json({"error": "Not Supported", "message": f"Endpoint {path} not supported"}, status=404)

        stream_mode = bool(payload.get("stream", False))
        max_tokens = payload.get("max_tokens", 8192)
        try:
            max_tokens = max(1, min(int(max_tokens), 8192))
        except (TypeError, ValueError):
            max_tokens = 8192

        messages = payload.get("messages") or []
        if not messages and payload.get("prompt"):
            messages = [{"role": "user", "content": str(payload["prompt"])}]
        if not messages:
            return self._send_json(
                {"error": "Bad Request", "message": "messages or prompt is required"}, status=400)

        preset = resolve_preset(payload.get("preset"), messages)
        sampling = {
            "temperature": _as_float(payload.get("temperature"), preset["temperature"]),
            "top_p": _as_float(payload.get("top_p"), preset["top_p"]),
        }

        response_id = f"gen-{int(time.time() * 1000)}"

        if stream_mode:
            return self._stream_completion(response_id, messages, preset, sampling, max_tokens)

        started = time.perf_counter()
        try:
            text = "".join(generate_tokens(messages, preset, sampling, max_tokens))
        except EngineError as e:
            return self._send_json({"error": "Engine Error", "message": str(e)}, status=503)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        timings = {"wall_time_ms": elapsed_ms, "completion_tokens": None}
        record_timings(**timings)

        if path.endswith("/responses"):
            return self._send_json({
                "id": response_id, "object": "response", "model": MODEL_ID,
                "response": text, "created": int(time.time()),
                "preset": preset["id"], "kv_slots": n_ctx, "timings": timings,
            })

        return self._send_json({
            "id": response_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": MODEL_ID,
            "preset": preset["id"],
            "kv_slots": n_ctx,
            "timings": timings,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }],
        })

    def _stream_completion(self, response_id, messages, preset, sampling, max_tokens):
        """Emit SSE deltas as llama.cpp produces them.

        Headers go out before generation starts, so the client sees the connection
        open immediately and each token arrives as it is decoded.
        """
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
            return

        def emit(payload_obj):
            self.wfile.write(f"data: {json.dumps(payload_obj)}\n\n".encode("utf-8"))
            self.wfile.flush()

        def envelope(delta, finish_reason=None, extra=None):
            body = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": MODEL_ID,
                "preset": preset["id"],
                "kv_slots": n_ctx,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
            }
            if extra:
                body.update(extra)
            return body

        started = time.perf_counter()
        token_count = 0
        first_token_ms = None
        try:
            for piece in generate_tokens(messages, preset, sampling, max_tokens):
                if first_token_ms is None:
                    first_token_ms = round((time.perf_counter() - started) * 1000, 2)
                token_count += 1
                emit(envelope({"content": piece}))
        except EngineError as e:
            try:
                emit(envelope({"content": f"\n\n⚠️ {e}"}, finish_reason="error"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True
            return
        except (BrokenPipeError, ConnectionResetError):
            # Client walked away mid-stream; stop decoding rather than finishing into a void.
            sys.stderr.write("\033[90m[Stream] Client disconnected; generation aborted.\033[0m\n")
            self.close_connection = True
            return

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        timings = {
            "wall_time_ms": elapsed_ms,
            "first_token_ms": first_token_ms,
            "completion_tokens": token_count,
            "tokens_per_second": (
                round(token_count / (elapsed_ms / 1000.0), 2) if elapsed_ms > 0 else None),
        }
        record_timings(**timings)
        try:
            emit(envelope({}, finish_reason="stop", extra={"timings": timings}))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def _generate_response(self, prompt, max_tokens=8192, preset_id=None):
        """Convenience wrapper used by the CLI (`vapor run` / `vapor chat`)."""
        preset = PRESETS.get(preset_id or "default", PRESETS["default"])
        messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": str(prompt)}]
        sampling = {"temperature": preset["temperature"], "top_p": preset["top_p"]}
        try:
            return "".join(generate_tokens(messages, preset, sampling, max_tokens))
        except EngineError as e:
            return f"[VaporRAM Error] {e}"


class VaporHTTPServer(ThreadingHTTPServer):
    """Threaded so a multi-minute generation can't stall /health, /progress or a
    second client. Generation itself is serialised by _generation_lock."""
    daemon_threads = True
    allow_reuse_address = True


def serve(host="0.0.0.0", port=8000, api_key=None):
    global server_instance
    VaporRequestHandler.api_key = api_key
    server_instance = VaporHTTPServer((host, port), VaporRequestHandler)

    def handle_signal(sig, frame):
        sys.stderr.write("\n\033[33m[VaporRAM] Server stopped via terminal (CTRL+C).\033[0m\n")
        try:
            server_instance.server_close()
        except Exception:
            pass
        os._exit(0)

    if threading.current_thread() is threading.main_thread():
        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
        except Exception:
            pass

    read_model_architecture(current_model_path)
    gguf = find_gguf(current_model_path)

    print("\033[1;36m")
    print(f"  💨 VaporRAM Web Engine v{VERSION}")
    print(f"  \033[32m➜\033[1;36m  Local Dashboard : \033[1;37mhttp://localhost:{port}/\033[1;36m")
    print(f"  \033[32m➜\033[1;36m  API Endpoint    : \033[1;37mhttp://localhost:{port}/v1\033[1;36m")
    print(f"  \033[32m➜\033[1;36m  Model Target    : \033[1;33m{MODEL_ID}\033[1;36m")
    if gguf:
        size_gb = os.path.getsize(gguf) / (1024 ** 3)
        print(f"  \033[32m➜\033[1;36m  Weights         : \033[1;37m{os.path.basename(gguf)} \033[90m({size_gb:.2f} GB)\033[1;36m")
    else:
        print(f"  \033[33m➜\033[1;36m  Weights         : \033[1;33mnot found in {current_model_path} \033[90m(use the dashboard to download)\033[1;36m")
    print(f"  \033[32m➜\033[1;36m  Context Window  : \033[1;37m{n_ctx} tokens \033[90m(engine max {SAFE_GGUF_MAX_CONTEXT})\033[1;36m")
    if api_key:
        print("  \033[32m➜\033[1;36m  Auth            : \033[1;37mAPI key required\033[1;36m")
    print("  \033[90m(Press CTRL+C or use Web UI Stop/Restart buttons to control server)\033[0m")
    print()

    try:
        server_instance.serve_forever(poll_interval=0.5)
    except (KeyboardInterrupt, SystemExit):
        handle_signal(None, None)

if __name__ == "__main__":
    serve()
