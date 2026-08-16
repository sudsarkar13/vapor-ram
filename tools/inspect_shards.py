#!/usr/bin/env python3
"""
VaporRAM — Model Inspector

Reports what is actually in the model directory, reading GGUF geometry from the
file's own tensor directory.

What this replaced
------------------
Through v1.0.7-beta.3 this command read only `config.json` and printed
`cfg.get(key, <default>)` for each architecture field. For gemma-4-E4B-it those
keys are nested under `text_config`, so every lookup missed and the command
printed its fallbacks as though they were the model's:

    Hidden Dim : 3072   (really 2560)
    Num Layers : 32     (really 42)
    Heads      : 16     (really 8)
    Vocab Size : 256000 (really 262144)

It then closed with an unconditional "Alignment & Streaming Readiness" line
declaring a pass, printed no matter what was on disk, and quoting an NVMe
block size that does not exist (real logical blocks are 512 or 4096 bytes).

Nothing here prints a verdict it has not established.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from vapor_ram import paths

C = {"dim": "\033[90m", "cyan": "\033[36m", "amber": "\033[33m",
     "red": "\033[31m", "bold": "\033[1m", "off": "\033[0m"}


def inspect_shards(model_dir=None):
    model_dir = model_dir or paths.default_model_dir()
    print(f"{C['bold']}=== VaporRAM Model Inspector ==={C['off']}")
    print(f" Directory : {model_dir}")
    print("-" * 46)

    if not os.path.isdir(model_dir):
        print(f"{C['amber']}[Notice]{C['off']} '{model_dir}' does not exist yet.")
        print("         Fetch the weights with:  vapor download")
        return False

    entries = [f for f in sorted(os.listdir(model_dir))
               if os.path.isfile(os.path.join(model_dir, f))]
    gguf = [f for f in entries if f.endswith(".gguf")]
    safetensors = [f for f in entries if f.endswith(".safetensors")]
    total = sum(os.path.getsize(os.path.join(model_dir, f)) for f in entries)

    print(f" Files     : {len(entries)}  ({len(gguf)} gguf, {len(safetensors)} safetensors)")
    print(f" Disk size : {total / 1e9:.2f} GB")

    if not gguf:
        print()
        print(f"{C['amber']}No .gguf file here.{C['off']} VaporRAM generates tokens from GGUF"
              " weights;\nsafetensors alone cannot be served. Run:  vapor download")
        return False

    from vapor_ram.gguf import read_gguf
    from vapor_ram import cortex

    for name in gguf:
        path = os.path.join(model_dir, name)
        size = os.path.getsize(path)
        print()
        print(f"{C['bold']} {name}{C['off']}")
        try:
            parsed = read_gguf(path)
        except Exception as e:
            print(f"   {C['red']}Could not parse: {e}{C['off']}")
            continue

        md = parsed["metadata"]
        arch = md.get("general.architecture", "unknown")

        def geom(*keys, default=None):
            """Architecture keys are namespaced by architecture, e.g. gemma4.block_count."""
            for k in keys:
                full = f"{arch}.{k}"
                if full in md:
                    return md[full]
            return default

        report = cortex.layer_report(path)
        params = sum(math.prod(t["dims"]) for t in parsed["tensors"])
        tensor_bytes = sum(t["nbytes"] for t in parsed["tensors"])

        rows = [
            ("Architecture", arch),
            ("File size", f"{size:,} bytes ({size / 1e9:.2f} GB)"),
            ("Tensors", f"{len(parsed['tensors']):,}"),
            ("Parameters", f"{params / 1e9:.2f} B"),
            ("Bits / parameter", f"{8 * tensor_bytes / params:.2f}"),
            ("Transformer blocks", geom("block_count", default="?")),
            ("Hidden size", geom("embedding_length", default="?")),
            ("Attention heads", geom("attention.head_count", default="?")),
            ("KV heads", geom("attention.head_count_kv", default="?")),
            ("Max context", f"{geom('context_length', default=0):,}"),
            ("Block data begins", f"byte {report['layers'][0]['offset']:,}"
                                  if report.get("layers") else "n/a"),
            ("Streamable bytes", f"{report['layer_bytes_total'] / 1e9:.2f} GB"),
            ("Resident bytes", f"{report['resident_bytes'] / 1e9:.2f} GB"),
        ]
        for label, value in rows:
            print(f"   {label:<20}: {value}")

        quants = report.get("quant_summary") or []
        if quants:
            print(f"   {'Quantisation':<20}:")
            tot = sum(q["bytes"] for q in quants) or 1
            for q in quants:
                print(f"     {q['type']:<8} {q['tensors']:>4} tensors  "
                      f"{100 * q['bytes'] / tot:5.1f}%")

        # A real integrity statement: the tensor directory must account for the
        # whole file. If it does not, the parse is wrong or the file is damaged.
        end = max(t["offset"] + t["nbytes"] for t in parsed["tensors"])
        if end == size:
            print(f"   {'Integrity':<20}: tensor directory accounts for the "
                  f"file exactly ({end:,} bytes)")
        else:
            print(f"   {C['red']}{'Integrity':<20}: last tensor ends at {end:,} "
                  f"but the file is {size:,} bytes{C['off']}")
    return True


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(0 if inspect_shards(target) else 1)
