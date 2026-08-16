#!/usr/bin/env python3
"""
VaporRAM — Streaming Benchmark

Measures how fast this machine can stream the model's real transformer blocks
off disk with unbuffered O_DIRECT reads, and states what that would cost per
token if generation were served from the stream rather than from RAM.

What this replaced, and why it mattered
---------------------------------------
Through v1.0.7-beta.3 this tool invoked the C engine with `c/vapor_engine.o`
as stand-in "weights" — an object file, not a model. The call failed every
time, and the tool then printed the peak RSS of the process that had just
failed to start against the 1.5 GB ceiling and reported:

    Execution Status : FAIL
    RAM Status       : PASS

...reporting the headline 1.5 GB RAM ceiling as met, on the strength of a
process that had just failed to start and therefore never loaded the model.

Nothing here grades itself against the ceiling any more. It reports what it
measured and what that measurement implies, and leaves the conclusion to the
reader.
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from vapor_ram import cortex, paths

C = {"dim": "\033[90m", "cyan": "\033[36m", "green": "\033[32m",
     "amber": "\033[33m", "red": "\033[31m", "bold": "\033[1m", "off": "\033[0m"}


def _find_gguf():
    """Model weights only — a projector is not something to stream-benchmark."""
    return paths.find_model_gguf(paths.default_model_dir())


def run_benchmark():
    print(f"{C['bold']}=== VaporRAM Streaming Benchmark ==={C['off']}")

    gguf = _find_gguf()
    if not gguf:
        print(f"{C['red']}No .gguf weights found in {paths.default_model_dir()}.{C['off']}")
        print("Download them first:  vapor download")
        return 1

    report = cortex.layer_report(gguf)
    print(f" Model file   : {os.path.basename(gguf)}")
    print(f" Blocks       : {report['n_layers']}  ({report['n_tensors']} tensors)")
    print(f" Streamable   : {report['layer_bytes_total'] / 1e9:.2f} GB across all blocks")
    print(f" Resident     : {report['resident_bytes'] / 1e9:.2f} GB (embeddings, norms)")
    print(f"{C['dim']} Streaming every block through O_DIRECT, bypassing the page cache."
          f"{C['off']}")
    print()

    result = cortex.run_stream_benchmark(gguf)
    if result.get("error"):
        print(f"{C['red']}Benchmark did not run: {result['message']}{C['off']}")
        return 1

    rate = result.get("mb_per_s")
    print(f"{C['bold']} Measured{C['off']}")
    print(f"   O_DIRECT              : {'yes' if result.get('o_direct') else 'no (fell back to buffered reads)'}")
    print(f"   Blocks read           : {result.get('layers_read')}")
    if result.get("failures"):
        print(f"   {C['amber']}Failures              : {result['failures']}{C['off']}")
    print(f"   Bytes streamed        : {(result.get('total_bytes') or 0) / 1e9:.2f} GB")
    print(f"   Wall time             : {(result.get('total_ms') or 0) / 1000:.2f} s")
    print(f"   {C['cyan']}Throughput            : {rate:.1f} MB/s{C['off']}")
    if result.get("layer_ms_mean") is not None:
        print(f"   Per block             : {result['layer_ms_mean']:.1f} ms mean "
              f"({result['layer_ms_min']:.1f}–{result['layer_ms_max']:.1f} ms)")
    if result.get("peak_buffer_bytes"):
        print(f"   Peak reader buffer    : {result['peak_buffer_bytes'] / 1e6:.1f} MB")
    print()

    spt = result.get("seconds_per_token_if_streamed")
    if spt:
        print(f"{C['bold']} What this implies{C['off']}")
        print(f"   Streaming all {report['n_layers']} blocks for every token would cost")
        print(f"   {C['amber']}{spt:.2f} s/token ({1 / spt:.2f} tok/s){C['off']} on this disk.")
        print(f"{C['dim']}   That is the price of the 1.5 GB RAM target, and the reason")
        print(f"   generation currently runs from memory-mapped weights instead.{C['off']}")
    print()
    print(f"{C['dim']} This measures disk streaming, not token generation. For decode")
    print(f" throughput, generate something and read the dashboard's Profiling tab.{C['off']}")
    return 0


if __name__ == "__main__":
    sys.exit(run_benchmark())
