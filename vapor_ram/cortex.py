"""
VaporRAM — layer inspection and streaming measurement.

Two things live here, and the distinction matters because the dashboard used
to blur it:

  * `layer_report` reads the GGUF tensor directory. It is cheap (header only,
    no weight I/O) and describes what is really in the file: every transformer
    block, its tensors, quantisation types and exact byte range.

  * `run_stream_benchmark` shells out to the C inspector, which streams those
    real byte ranges through O_DIRECT and reports what the device delivered.
    It moves gigabytes, so it runs on request, never on a poll.

Neither of these is the token path. Generation runs through llama.cpp.
"""
import json
import os
import subprocess
import threading
import time

from . import paths
from .gguf import read_gguf, layer_map, GGUFError

_cache_lock = threading.Lock()
_layer_cache = {}          # gguf path -> (mtime, report)
_last_benchmark = None     # most recent measured run
_benchmark_lock = threading.Lock()


def layer_report(gguf_path):
    """Real per-layer structure of a GGUF, cached on (path, mtime)."""
    if not gguf_path or not os.path.isfile(gguf_path):
        return None
    try:
        mtime = os.path.getmtime(gguf_path)
    except OSError:
        return None

    with _cache_lock:
        cached = _layer_cache.get(gguf_path)
        if cached and cached[0] == mtime:
            return cached[1]

    parsed = read_gguf(gguf_path)
    mapping = layer_map(parsed)

    meta = parsed["metadata"]
    arch = parsed["architecture"]
    report = {
        "file": os.path.basename(gguf_path),
        "path": gguf_path,
        "architecture": arch,
        "gguf_version": parsed["version"],
        "file_size": parsed["file_size"],
        "data_start": parsed["data_start"],
        "n_tensors": parsed["n_tensors"],
        "n_layers": mapping["n_layers"],
        "layer_bytes_total": mapping["layer_bytes_total"],
        "resident_bytes": mapping["resident_bytes"],
        "resident_tensors": mapping["resident_tensors"],
        "layers": mapping["layers"],
        "quant_summary": _quant_summary(parsed["tensors"]),
        "block_count_meta": meta.get(f"{arch}.block_count") if arch else None,
    }

    with _cache_lock:
        _layer_cache[gguf_path] = (mtime, report)
    return report


def _quant_summary(tensors):
    """Bytes and tensor counts per quantisation type across the whole file."""
    totals = {}
    for t in tensors:
        entry = totals.setdefault(t["type"], {"tensors": 0, "bytes": 0})
        entry["tensors"] += 1
        entry["bytes"] += t["nbytes"] or 0
    return [
        {"type": k, **v}
        for k, v in sorted(totals.items(), key=lambda kv: -kv[1]["bytes"])
    ]


def write_plan(report, plan_path, layers=None):
    """Emit the '<index> <offset> <length>' plan the C inspector consumes."""
    selected = report["layers"]
    if layers:
        wanted = set(layers)
        selected = [l for l in selected if l["layer"] in wanted]
    with open(plan_path, "w") as f:
        f.write("# layer_index byte_offset byte_length\n")
        for l in selected:
            f.write(f"{l['layer']} {l['offset']} {l['nbytes']}\n")
    return len(selected)


def run_stream_benchmark(gguf_path, layers=None, timeout=180):
    """Stream the real layer ranges through the C reader and measure them.

    Returns the parsed per-layer timings, or a dict with `error` set. The
    engine binary is optional in a source checkout, so its absence is reported
    plainly rather than raising.
    """
    global _last_benchmark

    engine = paths.engine_bin()
    if not os.path.isfile(engine) or not os.access(engine, os.X_OK):
        return {"error": "engine_missing",
                "message": f"Streaming inspector not built. Run `make -C c` to build {engine}."}

    report = layer_report(gguf_path)
    if not report:
        return {"error": "no_model", "message": "No GGUF file to stream."}

    plan_path = os.path.join(paths.state_dir(), "stream_plan.txt")
    count = write_plan(report, plan_path, layers)
    if not count:
        return {"error": "empty_plan", "message": "No layers selected."}

    started = time.time()
    try:
        proc = subprocess.run([engine, gguf_path, plan_path],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout",
                "message": f"Streaming did not finish within {timeout}s."}
    except Exception as e:
        return {"error": "spawn_failed", "message": str(e)}

    events = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    start = next((e for e in events if e.get("event") == "start"), {})
    done = next((e for e in events if e.get("event") == "done"), {})
    per_layer = [e for e in events if e.get("event") == "layer"]

    if not done:
        return {"error": "no_result",
                "message": (proc.stderr or "Inspector produced no summary.").strip()[:400]}

    result = {
        "measured_at": started,
        "o_direct": start.get("o_direct"),
        "layers": per_layer,
        "layers_read": done.get("layers_read"),
        "failures": done.get("failures"),
        "total_bytes": done.get("total_bytes"),
        "total_ms": done.get("total_ms"),
        "mb_per_s": done.get("mb_per_s"),
        "peak_buffer_bytes": done.get("peak_buffer_bytes"),
        "stderr": (proc.stderr or "").strip()[:400] or None,
    }
    ok = [l["ms"] for l in per_layer if l.get("ok") and "ms" in l]
    if ok:
        result["layer_ms_min"] = round(min(ok), 3)
        result["layer_ms_max"] = round(max(ok), 3)
        result["layer_ms_mean"] = round(sum(ok) / len(ok), 3)

    # What the measurement implies for the streaming design, stated in the
    # same units the rest of the dashboard uses. Streaming every layer per
    # token costs total_bytes at the measured rate; that is the number the
    # 1.5 GB ceiling would have to buy.
    if result.get("mb_per_s") and report["layer_bytes_total"]:
        per_token_mb = report["layer_bytes_total"] / (1024 ** 2)
        result["seconds_per_token_if_streamed"] = round(
            per_token_mb / result["mb_per_s"], 3)

    with _benchmark_lock:
        _last_benchmark = result
    return result


def last_benchmark():
    with _benchmark_lock:
        return _last_benchmark
