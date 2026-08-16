import os, sys, json, time, subprocess, mimetypes, threading, re, signal, socket, hmac, secrets
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from . import paths

# Asset locations differ between a git checkout and an installed package;
# vapor_ram.paths resolves both. HERE stays the anchor for user-supplied
# relative paths so they mean the same thing however VaporRAM was installed.
HERE = paths.install_root()
WEB_DIST = paths.web_dist()
ENGINE_BIN = paths.engine_bin()
DEFAULT_MODEL_DIR = paths.default_model_dir()
VAPOR_CONFIG_PATH = paths.config_path()
PRESETS_DIR = paths.presets_dir()

# Gemma 4 E4B-it was trained with max_position_embeddings=131072 (sliding window 512).
# MODEL_MAX_CONTEXT is what the *architecture* allows; SAFE_GGUF_MAX_CONTEXT is what this
# engine will actually allocate. Anything above the safe cap is refused at the API boundary
# rather than silently clamped at generation time, so the value the UI shows is always the
# value the KV cache really uses.
MODEL_MAX_CONTEXT = 131072
SAFE_GGUF_MAX_CONTEXT = 16384
MIN_CONTEXT_WINDOW = 512
DEFAULT_CONTEXT_WINDOW = 8192

VERSION = "1.0.7"

# Reasoning is on by default: this model supports it natively and the answers
# are better for it. Operators can turn it off globally, and callers can
# override per request.
THINKING_ENABLED = True

# Set from the active GGUF: true when the model's own chat template understands
# the thinking channel. Without it, turning the switch on would do nothing.
THINKING_SUPPORTED = False

# How hard the model should think. The chat template has no effort parameter --
# it only takes a boolean -- so these are VaporRAM's own, and the mechanism is
# stated plainly rather than implied: `hint` is appended to the system turn and
# is what actually steers depth, while `soft_cap` is the reasoning-token budget
# used to keep room for an answer and to flag when a level is being overrun.
REASONING_LEVELS = {
    "low": {
        "label": "Low",
        "hint": "Think briefly: a few short steps, then answer.",
        "soft_cap": 256,
        "description": "A few quick steps. Fastest, best for simple questions.",
    },
    "medium": {
        "label": "Medium",
        "hint": "Think concisely, covering the main steps before answering.",
        "soft_cap": 768,
        "description": "Covers the main steps without labouring them.",
    },
    "high": {
        "label": "High",
        "hint": ("Think carefully. Work through the problem step by step and "
                 "check your reasoning before answering."),
        "soft_cap": 2048,
        "description": "Works through the problem and checks itself. Default.",
    },
    "xhigh": {
        "label": "Extra high",
        "hint": ("Think exhaustively. Consider alternative approaches, test your "
                 "assumptions, and verify each step before answering."),
        "soft_cap": 4096,
        "description": "Explores alternatives and verifies each step. Slowest.",
    },
}
DEFAULT_REASONING_EFFORT = "high"
REASONING_EFFORT = DEFAULT_REASONING_EFFORT


try:
    _cfg_effort = str(_vapor_cfg.get("reasoning_effort", DEFAULT_REASONING_EFFORT)).lower()
    if _cfg_effort in REASONING_LEVELS:
        REASONING_EFFORT = _cfg_effort
except Exception:
    pass


def resolve_effort(value):
    """Normalise an effort name, falling back to the configured default."""
    if isinstance(value, str):
        key = value.strip().lower()
        if key in REASONING_LEVELS:
            return key
    return REASONING_EFFORT if REASONING_EFFORT in REASONING_LEVELS else DEFAULT_REASONING_EFFORT
MODEL_ID = "google/gemma-4-E4B-it"

# --- Network sharing -------------------------------------------------------
# API_KEY is the shared secret for LAN/remote access. AUTH_REQUIRED is enabled
# automatically whenever the server binds a non-loopback interface, so making
# the engine reachable never silently makes it open.
API_KEY = None
AUTH_REQUIRED = False
BIND_HOST = "127.0.0.1"
BIND_PORT = 8000

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", ""}

# Reachable without a key: the dashboard bundle (it contains no secrets and
# must load before it can ask for one) and a deliberately thin /health.
PUBLIC_PREFIXES = ("/health",)


def generate_api_key():
    """A key that survives being retyped on a phone but is not guessable."""
    return "vr_" + secrets.token_urlsafe(18)


def load_persisted_api_key():
    """Read the key from ~/.vapor-ram/api_key, or None if it isn't set yet.

    Persisting it means a restart doesn't invalidate every client that was
    already configured against this server.
    """
    try:
        with open(paths.api_key_path()) as f:
            key = f.read().strip()
        return key or None
    except Exception:
        return None


def save_api_key(key):
    """Write the key 0600 so it isn't world-readable on a shared machine."""
    target = paths.api_key_path()
    try:
        with open(target, "w") as f:
            f.write(key + "\n")
        os.chmod(target, 0o600)
        return True
    except Exception as e:
        sys.stderr.write(f"[Share] Could not persist API key to {target}: {e}\n")
        return False


def rotate_api_key():
    """Issue a new key and persist it, invalidating every previously shared one."""
    key = generate_api_key()
    save_api_key(key)
    return key


def resolve_api_key(explicit=None):
    """Precedence: --api-key, then $VAPOR_API_KEY, then the persisted key,
    then a freshly generated one (which is persisted for next time)."""
    key = (explicit or os.environ.get("VAPOR_API_KEY") or "").strip()
    if key:
        return key
    key = load_persisted_api_key()
    if key:
        return key
    key = generate_api_key()
    save_api_key(key)
    return key


def is_loopback(host):
    return (host or "").strip().lower() in LOOPBACK_HOSTS


def get_local_ip():
    """LAN address other devices can reach, without sending any traffic."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))   # no packets sent for UDP connect
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def share_urls(host=None, port=None, api_key=None, auth_required=None):
    """Everything a client needs to connect, resolved for the active bind.

    Arguments default to the running server's state so the same function can
    describe a live server or answer `vapor share` before one is started.
    """
    host = BIND_HOST if host is None else host
    port = BIND_PORT if port is None else port
    key = API_KEY if api_key is None else api_key
    needs_key = AUTH_REQUIRED if auth_required is None else auth_required

    shared = not is_loopback(host)
    lan_ip = get_local_ip() if shared else "127.0.0.1"
    base = f"http://{lan_ip}:{port}"
    return {
        "host": host,
        "port": port,
        "lan_ip": lan_ip,
        "base_url": base,
        "api_base": f"{base}/v1",
        "chat_url": f"{base}/v1/chat/completions",
        # The key rides in the query string so the whole thing is one tappable
        # link — retyping a token on a phone keyboard is where sharing dies.
        "dashboard_url": (f"{base}/?key={key}" if needs_key and key else f"{base}/"),
        "api_key": key if needs_key else None,
        "auth_required": needs_key,
        "shared_on_lan": shared,
    }


def client_snippets(info):
    """Copy-paste clients for the two ways people actually connect."""
    auth = f' \\\n    -H "Authorization: Bearer {info["api_key"]}"' if info["auth_required"] else ""
    curl = (
        f'curl {info["chat_url"]} \\\n'
        f'    -H "Content-Type: application/json"{auth} \\\n'
        f"    -d '{{\"model\": \"{MODEL_ID}\", "
        f'"messages": [{{"role": "user", "content": "Hello!"}}]}}\''
    )
    key_line = info["api_key"] or "not-required"
    openai = (
        "from openai import OpenAI\n"
        f'client = OpenAI(base_url="{info["api_base"]}", api_key="{key_line}")\n'
        "resp = client.chat.completions.create(\n"
        f'    model="{MODEL_ID}",\n'
        '    messages=[{"role": "user", "content": "Hello!"}],\n'
        ")\nprint(resp.choices[0].message.content)"
    )
    return {"curl": curl, "openai_python": openai}


def format_share_block(info):
    """Terminal rendering shared by the startup banner and `vapor share`."""
    c = "\033[1;36m"; w = "\033[1;37m"; y = "\033[1;33m"; g = "\033[32m"; d = "\033[90m"; r = "\033[0m"
    lines = []
    if info["shared_on_lan"]:
        lines.append(f"  {g}\u279c{c}  Shared on LAN   : {w}{info['base_url']}{r}")
        lines.append(f"  {g}\u279c{c}  API for clients : {w}{info['api_base']}{r}")
    if info["auth_required"]:
        lines.append(f"  {g}\u279c{c}  API key         : {y}{info['api_key']}{r}")
        lines.append(f"  {g}\u279c{c}  One-tap link    : {w}{info['dashboard_url']}{r}")
        lines.append(f"  {d}   Other devices: send it as 'Authorization: Bearer <key>',{r}")
        lines.append(f"  {d}   'X-API-Key: <key>', or ?key=<key> on the URL.{r}")
    elif info["shared_on_lan"]:
        lines.append(f"  {y}\u279c{c}  API key         : {y}disabled (--no-auth) \u2014 anyone on this network can use the model{r}")
    return "\n".join(lines)


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
# Fallback only, used when no GGUF has been parsed yet. The real per-layer
# span is read from the tensor directory by measured_layer_buffer_mb().
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


def physical_core_count():
    """Physical cores, not SMT siblings.

    llama.cpp's matmul kernels saturate each core's vector units, so running
    one thread per hyperthread makes two threads fight over the same FPU and
    costs throughput instead of adding any. os.cpu_count() reports SMT
    siblings, which is why this is counted from the topology instead.
    """
    try:
        cores = {}
        with open("/proc/cpuinfo") as f:
            phys = core = None
            for line in f:
                if line.startswith("physical id"):
                    phys = line.split(":")[1].strip()
                elif line.startswith("core id"):
                    core = line.split(":")[1].strip()
                elif not line.strip() and phys is not None and core is not None:
                    cores[(phys, core)] = True
                    phys = core = None
        if cores:
            return len(cores)
    except Exception:
        pass
    try:
        import psutil
        count = psutil.cpu_count(logical=False)
        if count:
            return int(count)
    except Exception:
        pass
    logical = os.cpu_count() or 4
    return max(1, logical // 2)


def optimal_thread_count():
    """Threads for llama.cpp. VAPOR_N_THREADS overrides the detected value."""
    override = os.environ.get("VAPOR_N_THREADS", "").strip()
    if override:
        try:
            value = int(override)
            if value > 0:
                return value
        except ValueError:
            pass
    return max(1, physical_core_count())


def clamp_context(requested):
    """Single source of truth for context sizing. Returns (effective, was_clamped)."""
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return DEFAULT_CONTEXT_WINDOW, True
    effective = max(MIN_CONTEXT_WINDOW, min(value, SAFE_GGUF_MAX_CONTEXT))
    return effective, effective != value


try:
    from .config import load_config as _load_vapor_config
    _vapor_cfg = _load_vapor_config(VAPOR_CONFIG_PATH)
    n_ctx = int(_vapor_cfg.get("n_ctx", DEFAULT_CONTEXT_WINDOW))
    ram_ceiling_gb = float(_vapor_cfg.get("ram_ceiling_gb", 1.5))
except Exception:
    n_ctx = DEFAULT_CONTEXT_WINDOW
    ram_ceiling_gb = 1.5
n_ctx, _ = clamp_context(n_ctx)

try:
    THINKING_ENABLED = bool(_vapor_cfg.get("enable_thinking", True))
except Exception:
    THINKING_ENABLED = True

try:
    from . import doctor
except Exception:
    doctor = None

try:
    from . import cortex
except Exception:
    cortex = None

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
            "n_ctx": n_ctx,
            "enable_thinking": THINKING_ENABLED,
            "reasoning_effort": REASONING_EFFORT,
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


def weights_format(gguf_path=None):
    """Describe the weights the way they are actually stored and loaded.

    This used to be the hard-coded string "GGUF / Int4 SSD Stream", which was
    wrong twice over: the file is a mixed-precision K-quant (Q4_K/Q5_K/Q6_K),
    not int4, and llama.cpp memory-maps it rather than streaming it from SSD.
    The figure is now read from the GGUF tensor directory, so it cannot drift
    away from the file on disk.
    """
    try:
        report = cortex.layer_report(gguf_path)
        quants = report.get("quant_summary") or []
        if quants:
            names = ", ".join(q["type"] for q in quants[:3])
            return f"GGUF ({names}), memory-mapped"
    except Exception:
        pass
    return "GGUF, memory-mapped"


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
            # Measured from the GGUF tensor directory, not assumed. The old
            # constant claimed 140 MB per layer; the real span for
            # gemma-4-E4B-it-Q4_K_M is ~61 MB.
            "layer_buffer_mb": measured_layer_buffer_mb(),
        },
        "thinking_enabled": THINKING_ENABLED,
        "thinking_supported": THINKING_SUPPORTED,
        "reasoning_effort": REASONING_EFFORT,
        "reasoning_levels": [
            {"id": key, "label": v["label"], "description": v["description"],
             "soft_cap": v["soft_cap"]}
            for key, v in REASONING_LEVELS.items()
        ],
        "n_threads": optimal_thread_count(),
        "physical_cores": physical_core_count(),
        "logical_cores": os.cpu_count(),
        "ram_ceiling_gb": ram_ceiling_gb,
        "total_ram_gb": round(total, 2),
        "avail_ram_gb": round(avail, 2),
        "process_rss_mb": get_process_rss_mb(),
        "model_path": current_model_path,
        "model_available": weights_available(current_model_path),
        "model_state": state,
        "slots": _slot_snapshot(current_model_path),
    }


def detect_thinking_support(gguf_path=None):
    """True when the model's own chat template implements a thinking channel.

    Read from the GGUF rather than assumed: gemma-4-E4B-it's template takes an
    `enable_thinking` flag, injects <|think|> at the top of the first system
    turn, and emits reasoning inside <|channel>thought ... <channel|>. A model
    without that would ignore the token, so the switch is disabled rather than
    offered as a control that does nothing.
    """
    global THINKING_SUPPORTED
    if cortex is None:
        return THINKING_SUPPORTED
    try:
        path = gguf_path or find_gguf(current_model_path)
        if not path:
            return THINKING_SUPPORTED
        from .gguf import read_gguf
        template = read_gguf(path)["metadata"].get("tokenizer.chat_template") or ""
        THINKING_SUPPORTED = ("enable_thinking" in template
                              and THINK_TOKEN in template
                              and CHANNEL_OPEN in template)
    except Exception:
        pass
    return THINKING_SUPPORTED


def measured_layer_buffer_mb():
    """Largest real transformer-block span in the active GGUF, in MB."""
    if cortex is None:
        return LAYER_BUFFER_MB
    try:
        gguf = find_gguf(current_model_path)
        if not gguf:
            return LAYER_BUFFER_MB
        report = cortex.layer_report(gguf)
        if not report or not report.get("layers"):
            return LAYER_BUFFER_MB
        return round(max(l["nbytes"] for l in report["layers"]) / (1024 ** 2), 1)
    except Exception:
        return LAYER_BUFFER_MB


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
        paths.ensure_tools_importable()
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


# Control tokens verified against the GGUF vocabulary of gemma-4-E4B-it.
# The previously used <start_of_turn>/<end_of_turn> are NOT in this model's
# vocabulary at all -- they tokenised as literal text, so every prompt was
# malformed and the stop sequences never matched anything.
TURN_OPEN = "<|turn>"      # token 105
TURN_CLOSE = "<turn|>"     # token 106, also the EOS token
THINK_TOKEN = "<|think|>"  # token 98
CHANNEL_OPEN = "<|channel>"    # token 100
CHANNEL_CLOSE = "<channel|>"   # token 101
THOUGHT_CHANNEL = "thought"

STOP_SEQUENCES = [TURN_CLOSE, TURN_OPEN]


def strip_thinking(text):
    """Drop <|channel>...<channel|> blocks, mirroring the chat template's macro.

    Reasoning from earlier turns is not replayed into the prompt; the model's
    own template strips it, and feeding it back changes the distribution.
    """
    result = []
    for part in str(text).split(CHANNEL_CLOSE):
        if CHANNEL_OPEN in part:
            result.append(part.split(CHANNEL_OPEN)[0])
        else:
            result.append(part)
    return "".join(result).strip()


class ThinkingSplitter:
    """Splits a token stream into reasoning and answer text.

    With thinking enabled the model emits `<|channel>thought\n...\n<channel|>`
    before its reply. Markers can straddle chunk boundaries, so partial tails
    are held back rather than leaked into the visible answer.
    """

    def __init__(self):
        self.buffer = ""
        self.in_thought = False
        self.saw_thought = False

    def _longest_partial_suffix(self, text, marker):
        limit = min(len(text), len(marker) - 1)
        for size in range(limit, 0, -1):
            if marker.startswith(text[-size:]):
                return size
        return 0

    def feed(self, chunk):
        """Yield (channel, text) pairs, channel being 'thinking' or 'content'."""
        self.buffer += chunk
        out = []
        while self.buffer:
            if self.in_thought:
                idx = self.buffer.find(CHANNEL_CLOSE)
                if idx == -1:
                    hold = self._longest_partial_suffix(self.buffer, CHANNEL_CLOSE)
                    emit = self.buffer[:len(self.buffer) - hold] if hold else self.buffer
                    if emit:
                        out.append(("thinking", emit))
                    self.buffer = self.buffer[len(emit):]
                    break
                if idx:
                    out.append(("thinking", self.buffer[:idx]))
                self.buffer = self.buffer[idx + len(CHANNEL_CLOSE):]
                self.in_thought = False
                continue

            idx = self.buffer.find(CHANNEL_OPEN)
            if idx == -1:
                hold = self._longest_partial_suffix(self.buffer, CHANNEL_OPEN)
                emit = self.buffer[:len(self.buffer) - hold] if hold else self.buffer
                if emit:
                    out.append(("content", emit))
                self.buffer = self.buffer[len(emit):]
                break
            if idx:
                out.append(("content", self.buffer[:idx]))
            rest = self.buffer[idx + len(CHANNEL_OPEN):]
            # The channel name and its newline precede the reasoning body.
            newline = rest.find("\n")
            if newline == -1:
                # Name not fully arrived yet; wait for more input.
                self.buffer = self.buffer[idx:]
                break
            self.buffer = rest[newline + 1:]
            self.in_thought = True
            self.saw_thought = True
        return out

    def flush(self):
        """Emit anything still held once the stream ends."""
        if not self.buffer:
            return []
        channel = "thinking" if self.in_thought else "content"
        out = [(channel, self.buffer)]
        self.buffer = ""
        return out


def _as_bool(value, fallback):
    """Accept the several shapes clients use for a boolean flag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on", "enabled"):
            return True
        if lowered in ("0", "false", "no", "off", "disabled"):
            return False
    return fallback


def build_prompt(messages, preset, enable_thinking=None, effort=None):
    """Render the conversation in gemma-4-E4B-it's real instruction format.

    Structure comes from the chat template embedded in the GGUF:

        <|turn>system\n[<|think|>\n]{system}<turn|>\n
        <|turn>user\n{text}<turn|>\n
        <|turn>model\n{text}<turn|>\n
        <|turn>model\n

    This model has a real system turn, so the instruction is no longer folded
    into the first user message. Reasoning from earlier assistant turns is
    stripped, matching the template's own strip_thinking macro.
    """
    if enable_thinking is None:
        enable_thinking = THINKING_ENABLED
    level = REASONING_LEVELS[resolve_effort(effort)]

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
        if msg["role"] == "assistant":
            content = strip_thinking(content)
        if not content:
            continue
        role = "user" if msg["role"] == "user" else "model"
        block = f"{TURN_OPEN}{role}\n{content}{TURN_CLOSE}\n"
        if total + len(block) > char_budget and rendered:
            break
        total += len(block)
        rendered.append(block)
    rendered.reverse()

    # The system turn is emitted when there is an instruction to carry or when
    # thinking is on, because <|think|> belongs at the top of that turn.
    prefix = ""
    if enable_thinking or system_parts:
        prefix = f"{TURN_OPEN}system\n"
        if enable_thinking:
            prefix += f"{THINK_TOKEN}\n"
            # The depth hint sits with the thinking token, before any persona
            # instruction, so a preset cannot accidentally override it.
            system_parts.insert(0, level["hint"])
        if system_parts:
            prefix += "\n\n".join(p.strip() for p in system_parts)
        prefix += f"{TURN_CLOSE}\n"

    return prefix + "".join(rendered) + f"{TURN_OPEN}model\n"


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
    threads = optimal_thread_count()
    try:
        llm = Llama(model_path=gguf_file, n_ctx=target_ctx,
                    n_threads=threads, n_threads_batch=threads,
                    verbose=False)
        applied_ctx = target_ctx
    except Exception as alloc_err:
        fallback = max(MIN_CONTEXT_WINDOW, min(4096, target_ctx))
        sys.stderr.write(
            f"\033[33m[GGUF Engine] Context allocation failed ({alloc_err}); retrying at n_ctx={fallback}\033[0m\n")
        set_model_state("loading", f"Retrying {name} at reduced context {fallback}…",
                        path=gguf_file, ctx=fallback)
        try:
            llm = Llama(model_path=gguf_file, n_ctx=fallback,
                        n_threads=threads, n_threads_batch=threads,
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
    sys.stderr.write(f"\033[32m[GGUF Engine] {name} ready in {load_ms / 1000:.1f}s "
                     f"({threads} threads)\033[0m\n")
    return llm


def generate_tokens(messages, preset, sampling, max_tokens, enable_thinking=None,
                    effort=None, stats=None):
    """Yield generated text pieces as llama.cpp decodes them.

    This is a generator: the caller can forward each piece to the client immediately.

    `stats`, if given, is a dict this fills in with real token counts:
    `prompt_tokens` from the model's own tokenizer and `completion_tokens`
    counted one per llama.cpp chunk. Callers cannot derive the latter by
    counting yielded pieces, because ThinkingSplitter may split one token
    across several pieces or hold a partial control marker back.
    """
    gguf_file = find_gguf(current_model_path)
    if not gguf_file:
        raise EngineError(
            f"No .gguf weights found in '{current_model_path}'. "
            f"Download the model from the dashboard or run: ./vapor download")

    prompt = build_prompt(messages, preset, enable_thinking=enable_thinking,
                          effort=effort)

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
                # Real stop tokens for this model. The previous list used
                # <end_of_turn>/<start_of_turn>, which are not in its vocabulary.
                stop=STOP_SEQUENCES,
                stream=True,
            )
            if stats is not None:
                try:
                    stats["prompt_tokens"] = len(llm.tokenize(prompt.encode("utf-8")))
                except Exception:
                    stats["prompt_tokens"] = None
                stats["completion_tokens"] = 0

            splitter = ThinkingSplitter()
            for chunk in stream:
                piece = chunk["choices"][0].get("text", "")
                if not piece:
                    continue
                if stats is not None:
                    stats["completion_tokens"] += 1
                for channel, text in splitter.feed(piece):
                    if text:
                        yield channel, text
            for channel, text in splitter.flush():
                if text:
                    yield channel, text
            # Reasoning shares the max_tokens budget with the answer. On a hard
            # question it can consume all of it, which would otherwise surface
            # as an empty reply with no explanation.
            if splitter.in_thought:
                yield "truncated", ("Reasoning used the entire token budget before "
                                    "an answer was produced. Raise max_tokens, or "
                                    "turn reasoning off for this question.")
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
detect_thinking_support()


def generate_text(messages, preset_id=None, max_tokens=8192, on_chunk=None,
                  on_thinking=None, enable_thinking=None):
    """Blocking generation helper for the CLI.

    `messages` is a full OpenAI-style history. `on_chunk` receives each piece as it
    is produced so the terminal can stream just like the dashboard does.
    """
    preset = PRESETS.get(preset_id or "default", PRESETS["default"])
    sampling = {"temperature": preset["temperature"], "top_p": preset["top_p"]}
    parts = []
    for channel, piece in generate_tokens(messages, preset, sampling, max_tokens,
                                          enable_thinking=enable_thinking):
        if channel == "thinking":
            if on_thinking:
                on_thinking(piece)
            continue
        if channel == "truncated":
            piece = f"\n\n\u26a0\ufe0f {piece}"
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

        # Shared links carry ?key=<secret>. Logging it verbatim would write the
        # key into the terminal scrollback and any file the output is piped to.
        path = re.sub(r"([?&](?:api_)?key=)[^&]*", r"\1***", path)

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

    def _presented_key(self, parsed=None):
        """Pull the key out of whichever channel the client used.

        Three are accepted because they serve different clients: OpenAI-compatible
        SDKs send `Authorization: Bearer`, hand-written scripts reach for
        `X-API-Key`, and a browser opening a shared link can only carry `?key=`.
        """
        header = self.headers.get("Authorization", "").strip()
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
            if token:
                return token
        token = self.headers.get("X-API-Key", "").strip()
        if token:
            return token
        try:
            query = parse_qs((parsed or urlparse(self.path)).query)
            values = query.get("key") or query.get("api_key") or []
            if values and values[0].strip():
                return values[0].strip()
        except Exception:
            pass
        return ""

    def _check_auth(self, parsed=None):
        """True when the request may proceed.

        Compared with compare_digest so a wrong key can't be recovered one
        character at a time from response timings.
        """
        if not AUTH_REQUIRED or not API_KEY:
            return True
        presented = self._presented_key(parsed)
        if not presented:
            return False
        return hmac.compare_digest(presented, API_KEY)

    def _static_file_for(self, path):
        """Absolute path of the dashboard asset serving `path`, else None."""
        if path == "/":
            path = "/index.html"
        candidate = os.path.normpath(os.path.join(WEB_DIST, path.lstrip("/")))
        # normpath collapses any ../ before this check, so the prefix test is
        # what keeps a crafted path from escaping the dist directory.
        if candidate.startswith(WEB_DIST) and os.path.isfile(candidate):
            return candidate
        return None

    def _is_public(self, path):
        """Endpoints reachable without a key.

        The dashboard bundle is public because it has to load before it can ask
        the user for a key, and it contains no secrets. /health is public and
        deliberately thin so a phone can confirm it reached the right machine.
        Everything else — including every GET that reports paths, hardware or
        model state — needs the key.
        """
        if any(path.endswith(prefix) for prefix in PUBLIC_PREFIXES):
            return True
        return self._static_file_for(path) is not None

    def _authorize(self, path, parsed=None):
        """Guard for every request. Sends the 401 itself and returns False."""
        if self._is_public(path) or self._check_auth(parsed):
            return True
        info = share_urls()
        self._send_json({
            "error": "Unauthorized",
            "message": (
                "This VaporRAM server is shared on a network and requires an API key. "
                "Send it as 'Authorization: Bearer <key>', 'X-API-Key: <key>', or "
                "?key=<key>. Run `vapor share` on the host machine to see the key."
            ),
            "auth_required": True,
            "dashboard_url_hint": f"{info['base_url']}/?key=YOUR_KEY",
        }, status=401)
        return False

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

        # Previously only do_POST checked the key, so every GET below — including
        # /v1/system/progress (filesystem paths) and /v1/doctor (hardware) — was
        # readable by anyone who could reach the port.
        if not self._authorize(path, parsed):
            return

        if path.endswith("/health"):
            tele = telemetry_snapshot()
            gguf = find_gguf(current_model_path)
            payload = {
                "status": "ok",
                "engine": "VaporRAM",
                "version": VERSION,
                "model": MODEL_ID,
                "active_model": MODEL_ID,
                "format": weights_format(gguf),
                "connection": "CONNECTED" if tele["model_available"] else "NO_WEIGHTS",
            }
            # /health stays reachable without a key so a client can confirm it
            # found the right machine, but the telemetry block carries the host's
            # filesystem paths and RAM figures. Unauthenticated callers get the
            # identity only; the details need the key like every other endpoint.
            if self._check_auth(parsed):
                payload["gguf_file"] = os.path.basename(gguf) if gguf else None
                payload.update(tele)
            else:
                payload["auth_required"] = True
                payload["detail"] = "Provide the API key to read telemetry."
            return self._send_json(payload)

        # Connection details for other devices. Authenticated, because it hands
        # out the key it is protected by.
        if path.endswith("/share") or path.endswith("/system/share"):
            info = share_urls()
            return self._send_json({
                "status": "ok",
                "version": VERSION,
                "model": MODEL_ID,
                "share": info,
                "snippets": client_snippets(info),
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
            rss = tele["process_rss_mb"]

            # Layer data is read from the GGUF tensor directory, so every entry
            # is a real block with its real byte range and quantisation. The
            # previous version emitted MODEL_N_LAYERS identical rows carrying a
            # constant 140 MB "buffer_mb" that corresponded to nothing.
            gguf = find_gguf(current_model_path)
            layer_report = None
            layer_error = None
            if gguf and cortex is not None:
                try:
                    layer_report = cortex.layer_report(gguf)
                except Exception as e:
                    layer_error = str(e)

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
                "layer_report": layer_report,
                "layer_report_error": layer_error,
                "stream_benchmark": cortex.last_benchmark() if cortex else None,
                **tele,
            })

        # Serve static Web UI assets from web/dist
        file_path = self._static_file_for(path)
        if file_path:
            mime, _ = mimetypes.guess_type(file_path)
            with open(file_path, "rb") as f:
                content = f.read()
            try:
                self.send_response(200)
                self.send_header("Content-Type", mime or "application/octet-stream")
                self.send_header("Content-Length", str(len(content)))
                # No cache headers were sent at all, so browsers applied their
                # own heuristic caching to index.html and could keep serving a
                # previous dashboard build after an upgrade. Assets under
                # /_next/static/ carry a content hash in the filename and are
                # safe to cache forever; the HTML entry point must not be.
                if "/_next/static/" in path:
                    self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                else:
                    self.send_header("Cache-Control", "no-cache, must-revalidate")
                self.end_headers()
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        self._send_json({"error": "Not Found", "message": f"Endpoint {path} not found"}, status=404)

    def do_POST(self):
        global current_model_path, download_progress, n_ctx
        parsed = urlparse(self.path)
        path = clean_path(parsed.path)

        if not self._authorize(path, parsed):
            return

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

        # Stream the real layer byte ranges through the O_DIRECT reader and
        # measure them. Moves gigabytes, so it is an explicit action rather
        # than something a poll can trigger.
        if path.endswith("/cortex/benchmark") or path.endswith("/system/stream_benchmark"):
            if cortex is None:
                return self._send_json(
                    {"error": "Unavailable", "message": "cortex module failed to import"},
                    status=503)
            gguf = find_gguf(current_model_path)
            if not gguf:
                return self._send_json(
                    {"error": "No Weights",
                     "message": f"No .gguf found in {current_model_path}"}, status=404)
            result = cortex.run_stream_benchmark(gguf)
            if result.get("error"):
                return self._send_json(
                    {"error": result["error"], "message": result.get("message", "")},
                    status=503)
            return self._send_json({"status": "ok", "stream_benchmark": result})

        # Set custom system model path endpoint
        if path.endswith("/set_model_path") or path.endswith("/system/set_model_path"):
            ok, msg, resolved = apply_model_dir(payload.get("path", ""))
            if ok:
                detect_thinking_support()
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

            if any(k in payload for k in ("thinking", "enable_thinking")):
                global THINKING_ENABLED
                raw = payload.get("thinking", payload.get("enable_thinking"))
                new_value = _as_bool(raw, THINKING_ENABLED)
                if not THINKING_SUPPORTED and new_value:
                    warnings.append(
                        "The active model's chat template has no thinking channel; "
                        "enabling reasoning would have no effect.")
                elif new_value != THINKING_ENABLED:
                    THINKING_ENABLED = new_value
                    updated = True
                    msg_parts.append(
                        f"Reasoning {'enabled' if new_value else 'disabled'}")

            if any(k in payload for k in ("reasoning_effort", "thinking_level")):
                global REASONING_EFFORT
                requested = str(payload.get("reasoning_effort")
                                or payload.get("thinking_level") or "").strip().lower()
                if requested not in REASONING_LEVELS:
                    warnings.append(
                        f"Unknown reasoning level '{requested}'. "
                        f"Valid levels: {', '.join(REASONING_LEVELS)}.")
                elif requested != REASONING_EFFORT:
                    REASONING_EFFORT = requested
                    updated = True
                    msg_parts.append(
                        f"Reasoning effort set to {REASONING_LEVELS[requested]['label']}")

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
                paths.ensure_tools_importable()
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

        # Per-request override of the server default. `thinking` is the plain
        # name; `enable_thinking` matches the chat template's own variable and
        # `reasoning` matches what some OpenAI-compatible clients send.
        want_thinking = THINKING_ENABLED
        for key in ("thinking", "enable_thinking", "reasoning"):
            if key in payload:
                want_thinking = _as_bool(payload[key], THINKING_ENABLED)
                break

        want_effort = resolve_effort(
            payload.get("reasoning_effort") or payload.get("thinking_level"))

        response_id = f"gen-{int(time.time() * 1000)}"

        if stream_mode:
            return self._stream_completion(response_id, messages, preset, sampling,
                                           max_tokens, enable_thinking=want_thinking,
                                           effort=want_effort)

        started = time.perf_counter()
        gen_stats = {}
        try:
            reasoning_parts, answer_parts = [], []
            for channel, piece in generate_tokens(messages, preset, sampling,
                                                  max_tokens, enable_thinking=want_thinking,
                                                  effort=want_effort, stats=gen_stats):
                if channel == "truncated":
                    answer_parts.append(f"\n\n\u26a0\ufe0f {piece}")
                    continue
                (reasoning_parts if channel == "thinking" else answer_parts).append(piece)
            text = "".join(answer_parts)
            reasoning = "".join(reasoning_parts).strip() or None
        except EngineError as e:
            return self._send_json({"error": "Engine Error", "message": str(e)}, status=503)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        # Real counts from the tokenizer, not a guess from the yielded pieces.
        prompt_tokens = gen_stats.get("prompt_tokens")
        completion_tokens = gen_stats.get("completion_tokens", 0)
        timings = {
            "wall_time_ms": elapsed_ms,
            "completion_tokens": completion_tokens,
            "tokens_per_second": (
                round(completion_tokens / (elapsed_ms / 1000.0), 2) if elapsed_ms > 0 else None),
        }
        record_timings(**timings)
        # OpenAI clients read `usage`; without it the SDK reports zero tokens for
        # every non-streaming call. Absent until v1.0.7.
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": (prompt_tokens + completion_tokens)
            if isinstance(prompt_tokens, int) else completion_tokens,
        }

        if path.endswith("/responses"):
            return self._send_json({
                "id": response_id, "object": "response", "model": MODEL_ID,
                "response": text, "reasoning_content": reasoning,
                "created": int(time.time()),
                "preset": preset["id"], "kv_slots": n_ctx, "timings": timings,
                "usage": usage,
            })

        return self._send_json({
            "id": response_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": MODEL_ID,
            "preset": preset["id"],
            "kv_slots": n_ctx,
            "timings": timings,
            "usage": usage,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text,
                            "reasoning_content": reasoning},
                "finish_reason": "stop",
            }],
        })

    def _stream_completion(self, response_id, messages, preset, sampling, max_tokens,
                           enable_thinking=None, effort=None):
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
        reasoning_count = 0
        first_token_ms = None
        first_answer_ms = None
        truncated_note = None
        gen_stats = {}
        try:
            for channel, piece in generate_tokens(messages, preset, sampling,
                                                  max_tokens,
                                                  enable_thinking=enable_thinking,
                                                  effort=effort, stats=gen_stats):
                # Time to first token is when the user first sees output, which
                # is the first reasoning token when thinking is on. Counting
                # only answer tokens made a 19s reasoning pass read as
                # "0.22 tok/s with an 18s first token".
                if first_token_ms is None:
                    first_token_ms = round((time.perf_counter() - started) * 1000, 2)
                if channel == "truncated":
                    truncated_note = piece
                    continue
                if channel == "thinking":
                    # Reasoning rides its own delta field, so a client that does
                    # not know about it simply renders nothing extra rather than
                    # mixing the thought process into the answer.
                    reasoning_count += 1
                    emit(envelope({"reasoning_content": piece}))
                    continue
                if first_answer_ms is None:
                    first_answer_ms = round((time.perf_counter() - started) * 1000, 2)
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
        total_tokens = token_count + reasoning_count
        timings = {
            "wall_time_ms": elapsed_ms,
            "first_token_ms": first_token_ms,
            "first_answer_ms": first_answer_ms,
            "completion_tokens": token_count,
            "reasoning_tokens": reasoning_count,
            # Throughput covers everything the model produced; reporting only
            # answer tokens understates it whenever reasoning is on.
            "tokens_per_second": (
                round(total_tokens / (elapsed_ms / 1000.0), 2) if elapsed_ms > 0 else None),
        }
        record_timings(**timings)
        # Token counts straight from the tokenizer. token_count/reasoning_count
        # count yielded pieces, which is what the UI displays per channel, but
        # the splitter can emit several pieces for one token — so `usage` uses
        # the real count instead.
        prompt_tokens = gen_stats.get("prompt_tokens")
        generated_tokens = gen_stats.get("completion_tokens", total_tokens)
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": generated_tokens,
            "total_tokens": (prompt_tokens + generated_tokens)
            if isinstance(prompt_tokens, int) else generated_tokens,
        }
        try:
            emit(envelope(
                {"content": f"\n\n\u26a0\ufe0f {truncated_note}"} if truncated_note else {},
                finish_reason="length" if truncated_note else "stop",
                extra={"timings": timings, "usage": usage,
                       "reasoning_truncated": bool(truncated_note)}))
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
            return "".join(text for channel, text
                           in generate_tokens(messages, preset, sampling, max_tokens)
                           if channel in ("content", "truncated"))
        except EngineError as e:
            return f"[VaporRAM Error] {e}"


class VaporHTTPServer(ThreadingHTTPServer):
    """Threaded so a multi-minute generation can't stall /health, /progress or a
    second client. Generation itself is serialised by _generation_lock."""
    daemon_threads = True
    allow_reuse_address = True


# SIGQUIT (CTRL+\) and SIGHUP are included so there is more than one keystroke
# that can stop the server if SIGINT is being intercepted somewhere.
SHUTDOWN_SIGNALS = tuple(
    sig for sig in (
        getattr(signal, "SIGINT", None),
        getattr(signal, "SIGTERM", None),
        getattr(signal, "SIGQUIT", None),
        getattr(signal, "SIGHUP", None),
    )
    if sig is not None
)


def signals_blockable():
    """True when the sigwait() shutdown path is available on this platform."""
    return bool(
        SHUTDOWN_SIGNALS
        and hasattr(signal, "pthread_sigmask")
        and hasattr(signal, "sigwait")
    )


def block_shutdown_signals():
    """Block SIGINT/SIGTERM in the calling thread.

    Must run before any other thread is created. A process-directed signal is
    delivered to an arbitrary thread that does not block it, and threads
    inherit the mask of their creator -- so if anything is spawned before this
    (the browser opener in `vapor web`, an OpenMP pool, a llama.cpp worker),
    that thread can absorb the CTRL+C instead of sigwait() receiving it. The
    C-level handler then just sets a flag the main thread never gets around to
    processing, and the signal is lost.
    """
    if not signals_blockable():
        return False
    try:
        signal.pthread_sigmask(signal.SIG_BLOCK, SHUTDOWN_SIGNALS)
        return True
    except (OSError, ValueError):
        return False


def terminal_report():
    """Why CTRL+C might never reach this process.

    sigwait() cannot return for a signal the process never receives. Two
    situations produce that, and neither is visible from inside the server
    without asking the terminal directly:

      * the process is not in the terminal's foreground process group, so the
        tty driver sends SIGINT to some other process entirely;
      * the tty has ISIG cleared (something left it in raw mode), so ^C is
        delivered as the byte 0x03 instead of being turned into a signal.
    """
    report = {"stdin_tty": False, "fg_pgrp": None, "our_pgrp": None,
              "in_foreground": None, "isig": None}
    try:
        report["our_pgrp"] = os.getpgrp()
    except Exception:
        pass

    fd = None
    for candidate in (0, 1, 2):
        try:
            if os.isatty(candidate):
                fd = candidate
                break
        except Exception:
            continue
    if fd is None:
        return report

    report["stdin_tty"] = True
    try:
        report["fg_pgrp"] = os.tcgetpgrp(fd)
        report["in_foreground"] = report["fg_pgrp"] == report["our_pgrp"]
    except Exception:
        pass
    try:
        import termios
        attrs = termios.tcgetattr(fd)
        report["isig"] = bool(attrs[3] & termios.ISIG)
    except Exception:
        pass
    return report


def restore_terminal_signals():
    """Re-enable ISIG if something left the terminal unable to make signals."""
    try:
        import termios
    except Exception:
        return False
    for fd in (0, 1, 2):
        try:
            if not os.isatty(fd):
                continue
            attrs = termios.tcgetattr(fd)
            if attrs[3] & termios.ISIG:
                continue
            attrs[3] |= termios.ISIG
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            sys.stderr.write(
                "\033[33m[VaporRAM] Terminal had CTRL+C disabled (ISIG off); "
                "re-enabled it.\033[0m\n")
            return True
        except Exception:
            continue
    return False


def _console_watchdog():
    """Stop channel that does not depend on signals at all.

    When the tty turns ^C into SIGINT (the normal case) the keystroke never
    reaches stdin and this thread just blocks forever, costing nothing. When
    it does not -- raw mode, or a terminal that swallows the signal -- the
    0x03 byte lands here instead and stops the server. Typing `q` or `stop`
    and pressing Enter works either way.
    """
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return
    except Exception:
        return
    while True:
        try:
            data = os.read(sys.stdin.fileno(), 1024)
        except Exception:
            return
        if not data:
            return  # EOF: leave the server running, do not treat as a stop
        if b"\x03" in data or b"\x04" in data:
            shutdown_server("Server stopped via terminal (CTRL+C).")
            return
        word = data.strip().lower()
        if word in (b"q", b"quit", b"stop", b"exit"):
            shutdown_server("Server stopped from the console.")
            return


def _debug_signals(message):
    if os.environ.get("VAPOR_DEBUG_SIGNALS"):
        sys.stderr.write(f"\033[90m[signals] {message}\033[0m\n")
        sys.stderr.flush()


def shutdown_server(reason="Server stopped"):
    """Stop the HTTP server and exit, without hanging on in-flight work.

    The socket close runs on a helper thread with a bounded join: a generation
    stuck inside llama.cpp must not be able to prevent the process from exiting.
    """
    sys.stderr.write(f"\n\033[33m[VaporRAM] {reason}\033[0m\n")
    try:
        sys.stderr.flush()
    except Exception:
        pass

    def _close():
        try:
            if server_instance is not None:
                server_instance.shutdown()
        except Exception:
            pass
        try:
            if server_instance is not None:
                server_instance.server_close()
        except Exception:
            pass

    closer = threading.Thread(target=_close, daemon=True)
    closer.start()
    closer.join(timeout=3.0)
    # os._exit skips the interpreter's normal flush, so anything still sitting
    # in a block-buffered stdout would be discarded.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    os._exit(0)


def _serve_until_signal(server):
    """Block until SIGINT/SIGTERM, then shut down.

    Waits with sigwait() on a thread-blocked signal set rather than relying on
    a Python-level handler. A handler only runs when the *main thread* reaches
    the eval loop, which does not happen while llama.cpp is loading weights or
    decoding tokens -- so CTRL+C was silently ignored for the entire time the
    engine was actually busy, which is exactly when a user reaches for it.

    sigwait() is a blocking syscall that returns as soon as the signal is
    queued, so it is unaffected by interpreter-level starvation.
    """
    on_main = threading.current_thread() is threading.main_thread()
    usable = signals_blockable() and on_main

    if not usable:
        # Non-main thread (the test suite) or a platform without
        # pthread_sigmask. Install ordinary handlers so CTRL+C still stops the
        # process here, rather than leaving shutdown to an implicit
        # KeyboardInterrupt traceback.
        _debug_signals(
            f"sigwait unavailable (main_thread={on_main}, "
            f"blockable={signals_blockable()}); using handler fallback")
        _install_handler_fallback()
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            shutdown_server("Server stopped via terminal (CTRL+C).")
        return

    # Normally already blocked by block_shutdown_signals() before any thread
    # existed; repeating it is harmless and covers direct serve() callers.
    signal.pthread_sigmask(signal.SIG_BLOCK, SHUTDOWN_SIGNALS)
    _debug_signals(f"armed sigwait on pid {os.getpid()} for "
                   f"{[signal.Signals(x).name for x in SHUTDOWN_SIGNALS]}")

    # A terminal that cannot generate SIGINT will never satisfy sigwait, so
    # repair it where possible and report what was found.
    restore_terminal_signals()
    report = terminal_report()
    _debug_signals(f"terminal: {report}")
    if report["stdin_tty"] and report["in_foreground"] is False:
        sys.stderr.write(
            f"\033[33m[VaporRAM] This process (pgrp {report['our_pgrp']}) is not the "
            f"terminal's foreground group (pgrp {report['fg_pgrp']}), so CTRL+C is being "
            f"delivered elsewhere. Use `vapor stop`, or kill {os.getpid()}.\033[0m\n")

    # Independent of signals entirely: catches ^C arriving as a raw byte.
    threading.Thread(target=_console_watchdog, name="vapor-console",
                     daemon=True).start()

    worker = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.5},
        name="vapor-http",
        daemon=True,
    )
    worker.start()

    try:
        sig = signal.sigwait(SHUTDOWN_SIGNALS)
        name = signal.Signals(sig).name
    except (KeyboardInterrupt, InterruptedError):
        name = "SIGINT"
    except Exception:
        name = "signal"

    _debug_signals(f"sigwait returned {name}")
    reason = ("Server stopped via terminal (CTRL+C)."
              if name == "SIGINT" else f"Server stopped ({name}).")
    shutdown_server(reason)


def _install_handler_fallback():
    """Conventional signal handlers, for when sigwait() cannot be used."""
    def _handler(signum, _frame):
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = str(signum)
        shutdown_server("Server stopped via terminal (CTRL+C)."
                        if name == "SIGINT" else f"Server stopped ({name}).")

    for sig in SHUTDOWN_SIGNALS:
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass


def preload_model_async():
    """Load the weights at startup instead of on the first message.

    Loading is ~8s of mmap plus KV allocation. Doing it lazily meant the first
    chat paid that cost on top of its own generation, which reads as the server
    hanging. This runs on a background thread so the HTTP server and dashboard
    come up immediately -- model_state already reports "loading", so the UI
    shows real progress rather than an unexplained wait.
    """
    if not find_gguf(current_model_path):
        return None

    def _load():
        try:
            with _generation_lock:
                get_llama(find_gguf(current_model_path))
        except Exception as e:
            # A preload failure must not take the server down; the next request
            # will surface the real error through the normal path.
            sys.stderr.write(f"\033[33m[GGUF Engine] Preload failed: {e}\033[0m\n")

    thread = threading.Thread(target=_load, name="vapor-preload", daemon=True)
    thread.start()
    return thread


def configure_sharing(host, port, api_key=None, require_auth=None):
    """Decide the auth posture for this bind and return the share details.

    The rule: binding anything other than loopback makes the engine reachable
    by other machines, so a key is required unless the operator explicitly
    opts out with require_auth=False. Sharing therefore cannot be switched on
    by accident without also switching protection on.
    """
    global API_KEY, AUTH_REQUIRED, BIND_HOST, BIND_PORT

    BIND_HOST, BIND_PORT = host, port
    exposed = not is_loopback(host)

    if require_auth is None:
        AUTH_REQUIRED = exposed or bool(api_key) or bool(os.environ.get("VAPOR_API_KEY"))
    else:
        AUTH_REQUIRED = bool(require_auth)

    API_KEY = resolve_api_key(api_key) if AUTH_REQUIRED else None
    VaporRequestHandler.api_key = API_KEY
    return share_urls()


def serve(host="0.0.0.0", port=8000, api_key=None, require_auth=None, preload=True):
    global server_instance
    share = configure_sharing(host, port, api_key=api_key, require_auth=require_auth)
    server_instance = VaporHTTPServer((host, port), VaporRequestHandler)

    read_model_architecture(current_model_path)
    gguf = find_gguf(current_model_path)

    print("\033[1;36m")
    print(f"  \U0001f4a8 VaporRAM Web Engine v{VERSION}")
    print(f"  \033[32m\u279c\033[1;36m  Local Dashboard : \033[1;37mhttp://localhost:{port}/\033[1;36m")
    print(f"  \033[32m\u279c\033[1;36m  API Endpoint    : \033[1;37mhttp://localhost:{port}/v1\033[1;36m")
    print(f"  \033[32m\u279c\033[1;36m  Model Target    : \033[1;33m{MODEL_ID}\033[1;36m")
    if gguf:
        size_gb = os.path.getsize(gguf) / (1024 ** 3)
        print(f"  \033[32m\u279c\033[1;36m  Weights         : \033[1;37m{os.path.basename(gguf)} \033[90m({size_gb:.2f} GB)\033[1;36m")
    else:
        print(f"  \033[33m\u279c\033[1;36m  Weights         : \033[1;33mnot found in {current_model_path} \033[90m(use the dashboard to download)\033[1;36m")
    print(f"  \033[32m\u279c\033[1;36m  Context Window  : \033[1;37m{n_ctx} tokens \033[90m(engine max {SAFE_GGUF_MAX_CONTEXT})\033[1;36m")
    block = format_share_block(share)
    if block:
        print(block + "\033[1;36m")
    print(f"  \033[90m(Press CTRL+C or use the Web UI Stop button to control the server)\033[0m")
    print(f"  \033[90m PID {os.getpid()} \u2014 if CTRL+C ever fails, run: kill {os.getpid()}\033[0m")
    if gguf:
        print(f"  \033[32m\u279c\033[1;36m  Threads         : \033[1;37m{optimal_thread_count()} "
              f"\033[90m(physical cores; VAPOR_N_THREADS overrides)\033[1;36m")
    print()
    # stdout is block-buffered when it isn't a terminal, and shutdown ends in
    # os._exit(), which skips flushing. Without this the whole banner — API key
    # included — is lost whenever the server is piped to a file or supervisor.
    sys.stdout.flush()

    # Warm the engine before the first message rather than during it.
    if preload:
        preload_model_async()

    _serve_until_signal(server_instance)


if __name__ == "__main__":
    serve()
