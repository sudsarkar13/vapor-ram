# v1.0.7 — Stable Release

## 🔄 What's Changed (v1.0.7-beta.3 ➔ v1.0.7)

This is the first stable release of the 1.0.7 line. Going stable meant auditing
what the project claims about itself, and the audit found claims the software
could not back. This release removes them.

### The benchmark was reporting a pass it had not earned

`vapor bench` invoked the C engine with `c/vapor_engine.o` — an object file —
as stand-in weights. The call failed every time. The tool then measured the
peak RSS of the process that had just failed to start, compared it to the
1.5 GB ceiling, and printed:

```
 Execution Status : FAIL
 RAM Status       : PASS (< 1.5 GB)
```

So the project's own advertised benchmark reported its headline RAM ceiling as
met, on the strength of a process that never loaded the model.

It now streams the model's real 42 block ranges through `O_DIRECT` and reports
what it measured:

```
 Throughput            : 974.7 MB/s
 Per block             : 60.0 ms mean (52.3–85.5 ms)
 Streaming all 42 blocks per token would cost
 2.54 s/token (0.39 tok/s) on this disk.
```

It no longer grades itself against the ceiling at all.

### The SIMD benchmark reported ~200,000 GFLOPS

About a thousand times what this class of CPU can produce. The results were
unused, so `-O3` deleted both timing loops outright; the "scalar" baseline was
auto-vectorised into the very instructions it was meant to be compared against;
and the pure function was hoisted out of the loop entirely. With a compiler
barrier, a genuinely scalar baseline and enough iterations to measure, it now
reports figures that are stable to three runs:

| | |
| :--- | ---: |
| Scalar | 2.76 GFLOPS |
| AVX2 + FMA | 14.13 GFLOPS |
| Speedup | **5.12x** |

It also called its vector dimension "Gemma hidden size" while using 3072 — this
model's is 2560 — and printed `OpenMP Threads : 16` while running
single-threaded. There is no `#pragma omp` anywhere in the C sources.

### Three more commands were grading themselves

`vapor bench` was not the only one. Two other user-facing commands printed
verdicts they had not established, and a third printed numbers it had not read.

- **`vapor plan`** reported `Plan Status : PASS` against the 1.5 GB ceiling
  from an estimate built entirely of hard-coded constants — a 140 MB layer size
  (real blocks average 61.7 MB), 32 layers (there are 42), 16 heads (there are
  8). Measured RSS at the time was over 7 GB. It now sizes the design from the
  file's real geometry and reports the running server's actual RSS.
- **`vapor inspect`** read only `config.json`, whose architecture keys are
  nested under `text_config` for this model. Every lookup missed, so its
  fallbacks were printed as the model's own: hidden size 3072 (really 2560),
  32 layers (42), 16 heads (8), vocab 256000 (262144). It ignored the GGUF
  sitting next to it and signed off with an unconditional readiness pass. It
  now reads the tensor directory and verifies it accounts for the file exactly.
- **`vapor doctor`** passed any machine with 1.5 GB free — the ceiling
  *target*, not the ~7.5 GB the engine actually needs — so a host that could
  never load the model was told it was ready.

And `tools/convert_gemma_safetensors.py`, a "weight converter", opened no
tensor at all: it wrote 4.4 GB of zeros and printed `[Success]`. Removed.

### Everything in the README is now measured

| | |
| :--- | ---: |
| Peak RSS, `n_ctx` 8192 | 7.27 GB |
| Peak RSS, `n_ctx` 16384 | 8.72 GB |
| Cost of doubling context | 1.45 GB |
| Throughput | 4.0–5.3 tok/s |
| Server start → ready | 9.5 s |
| `O_DIRECT` streaming | 974.7 MB/s |

Measured on an AMD Ryzen 7 5700U (8 cores / 16 threads, 15 GB RAM, NVMe) with
`gemma-4-E4B-it-Q4_K_M.gguf`. Reproduce them with `vapor bench`.

The README now opens with a table of what is true — including the plain
statement that **the 1.5 GB RAM ceiling is not met**, that llama.cpp
memory-maps the whole GGUF, that the C engine is a measurement tool rather than
an inference engine, and what reaching the ceiling would actually cost. The
ceiling stays as what it is: a research goal the project has now costed.

### Other claims corrected

- `/health` described the weights as `GGUF / Int4 SSD Stream`. They are a mixed
  K-quant (Q4_K/Q5_K/Q6_K, plus F32 and BF16), memory-mapped. The field is now
  read from the GGUF tensor directory.
- The package described itself as an "Ultra-Low RAM SSD Streaming Engine" on
  PyPI, in the CLI banner, in the dashboard and in the page title.
- The docs site claimed 32 transformer layers (there are 42), an "8B" model
  (7.52 B parameters), an int8 KV cache holding context under 250 MB, and a
  fabricated "RAM Budget Usage 9.5%" — while sitting on `v1.0.7-alpha.3` for
  eight releases because its sync job's regexes matched nothing.
- `quant_type: "int8_kv_int4_weights"` sat in the default config describing a
  scheme the project does not use. Nothing read it.

## 🐛 Fixed

- **The OpenAI API returned no `usage` block.** `completion_tokens` was
  hard-coded to `None`, so SDK clients saw zero tokens for every non-streaming
  call. Both paths now report real counts, taken from the tokenizer rather than
  inferred from yielded text pieces.
- **The config wizard wrote the API key to `vapor.json`**, which the server
  never reads — it loads keys only from `~/.vapor-ram/api_key`. A key entered
  there silently did nothing while reporting success. It also overwrote the
  config wholesale, discarding `n_ctx`, `enable_thinking` and
  `reasoning_effort`. Both fixed.
- **`vapor init-config` wrote to the current directory**, not where the server
  reads.
- **`vapor.json` was tracked in git** while the server writes to it, so a
  checkout could reset your settings. Now untracked, with
  `vapor.example.json` as the tracked reference and `VAPOR_CONFIG_PATH` to
  override the location.
- **`c/vapor_engine` and `c/simd_bench` were tracked binaries**, pushing one
  host's architecture at every other host. Both untracked; they are built at
  install time.

## ✅ Testing

**164 checks pass**, up from 139. The new group guards each corrected claim, so
the benchmark can never again print a pass against the RAM ceiling without a
test failing.

## 📦 Install

```bash
pip install vapor-ram==1.0.7
```
