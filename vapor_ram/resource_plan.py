#!/usr/bin/env python3
"""
VaporRAM — Resource Planning & RAM Ceiling Calculator

Reports two separate things and never conflates them:

  1. What the streaming design *would* need, computed from the real GGUF
     geometry of the model on disk.
  2. What the engine *actually* uses today, measured from a running server.

What this replaced
------------------
Every figure here used to be a hard-coded constant: a 140 MB layer size (the
real blocks average 61.7 MB), 32 layers (there are 42), 16 attention heads
(there are 8, with 2 KV heads), and flat 150 MB / 100 MB allowances. Those
summed to 786 MB, were compared against the 1.5 GB ceiling, and printed:

    Plan Status : PASS

The engine's measured RSS at the time was over 7 GB. The command reported the
project's headline goal as met, using numbers that described no software that
has ever run. There is no unconditional verdict here any more.
"""
import os
import sys

from . import paths


def _gguf_geometry():
    """Real geometry from the model on disk, or None if it is not present."""
    model_dir = paths.default_model_dir()
    if not os.path.isdir(model_dir):
        return None
    gguf = paths.find_model_gguf(model_dir)
    if not gguf:
        return None
    try:
        from .gguf import read_gguf
        from . import cortex
        parsed = read_gguf(gguf)
        report = cortex.layer_report(gguf)
    except Exception:
        return None

    md = parsed["metadata"]
    arch = md.get("general.architecture", "")

    def key(name, default=None):
        return md.get(f"{arch}.{name}", default)

    layers = report.get("layers") or []
    return {
        "file": os.path.basename(gguf),
        "file_bytes": os.path.getsize(gguf),
        "n_layers": key("block_count"),
        "n_kv_heads": key("attention.head_count_kv"),
        "key_length": key("attention.key_length"),
        "value_length": key("attention.value_length"),
        "largest_block_bytes": max((l["nbytes"] for l in layers), default=None),
        "mean_block_bytes": (sum(l["nbytes"] for l in layers) // len(layers)) if layers else None,
        "layer_bytes_total": report.get("layer_bytes_total"),
        "resident_bytes": report.get("resident_bytes"),
    }


def _live_rss_mb():
    """RSS of a running VaporRAM server on this machine, if one is reachable."""
    try:
        import json
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8000/v1/stats", timeout=2) as r:
            stats = json.loads(r.read().decode())
        return stats.get("process_rss_mb")
    except Exception:
        return None


def build_plan(ram_budget_gb=1.5, seq_len=2048):
    geo = _gguf_geometry()
    plan = {
        "model": "google/gemma-4-E4B-it",
        "ram_ceiling_target_gb": ram_budget_gb,
        "seq_len": seq_len,
        "geometry": geo,
        "measured_rss_mb": _live_rss_mb(),
        "streaming_mode": "O_DIRECT block streaming (measurement path; not used for generation)",
    }
    if not geo:
        return plan

    # The streaming design's floor: hold one block while prefetching the next.
    # Sized from the largest real block, since the buffer must fit the worst case.
    double_buffer_mb = (geo["largest_block_bytes"] * 2) / (1024 ** 2)

    # KV cache, stated with its formula so the estimate can be checked:
    #   layers x kv_heads x (key_length + value_length) x seq_len x 2 bytes (f16)
    # llama.cpp allocates a full-size SWA cache for this architecture, so this
    # is a floor rather than a precise figure.
    kv_mb = None
    if all(geo[k] for k in ("n_layers", "n_kv_heads", "key_length", "value_length")):
        kv_bytes = (geo["n_layers"] * geo["n_kv_heads"]
                    * (geo["key_length"] + geo["value_length"]) * seq_len * 2)
        kv_mb = kv_bytes / (1024 ** 2)

    plan["breakdown"] = {
        "layer_double_buffer_mb": round(double_buffer_mb, 1),
        "kv_cache_f16_mb": round(kv_mb, 1) if kv_mb else None,
        "resident_embeddings_mb": round(geo["resident_bytes"] / (1024 ** 2), 1),
    }
    return plan


def format_plan(plan):
    geo = plan.get("geometry")
    L = [f"=== VaporRAM Resource Plan ({plan['model']}) ===",
         f" RAM ceiling target : {plan['ram_ceiling_target_gb']} GB"]

    if not geo:
        L += ["",
              " No GGUF weights found, so there is no geometry to plan against.",
              " Fetch them with:  vapor download"]
        return "\n".join(L)

    b = plan["breakdown"]
    L += [f" Weights on disk    : {geo['file']} ({geo['file_bytes'] / 1e9:.2f} GB)",
          "",
          " Streaming design, sized from this file's real geometry:",
          f"   - Blocks                : {geo['n_layers']} "
          f"(mean {geo['mean_block_bytes'] / 1e6:.1f} MB, "
          f"largest {geo['largest_block_bytes'] / 1e6:.1f} MB)",
          f"   - Block double buffer   : {b['layer_double_buffer_mb']} MB"]
    if b["kv_cache_f16_mb"]:
        L.append(f"   - KV cache @ {plan['seq_len']} tokens : "
                 f"{b['kv_cache_f16_mb']} MB (f16, floor)")
    L += [f"   - Resident embeddings   : {b['resident_embeddings_mb']} MB",
          "",
          " These describe the streaming design, which is a measurement path.",
          " It is not how tokens are generated."]

    L += ["", " What actually runs today:"]
    rss = plan.get("measured_rss_mb")
    if rss:
        L += [f"   - Measured server RSS   : {rss:.0f} MB "
              f"({rss / 1024:.2f} GB), read from the running server",
              f"   - Against the target    : {rss / (plan['ram_ceiling_target_gb'] * 1024):.1f}x "
              f"the {plan['ram_ceiling_target_gb']} GB ceiling"]
    else:
        L += ["   - No server reachable on port 8000, so RSS was not measured.",
              "     Start one with `vapor serve` and run this again.",
              "     For reference, measured peak RSS on the reference machine is",
              "     7.27 GB at n_ctx 8192 — the ceiling is not met."]
    L += ["",
          " llama.cpp memory-maps the whole GGUF, so the resident weights dominate",
          " everything above. Reaching the ceiling means streaming them instead,",
          " which `vapor bench` costs out on your own disk."]
    return "\n".join(L)


if __name__ == "__main__":
    print(format_plan(build_plan()))
