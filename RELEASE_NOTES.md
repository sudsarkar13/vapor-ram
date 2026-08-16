# v1.0.7-alpha.6 — Alpha Release

## 🔄 What's Changed (v1.0.7-alpha.5 ➔ v1.0.7-alpha.6)

This release makes the Brain Cortex report real data, and answers the question
the tab existed to ask.

### The streamer was reading the wrong bytes

`streaming_io.c` read at a fixed `layer_idx × 140 MB` stride from byte 0. That
corresponds to nothing in a GGUF container: in `gemma-4-E4B-it-Q4_K_M` the
first transformer block starts 2.37 GB into the file, after the token-embedding
tables, and spans ~61 MB. At layer 10 the old code read byte 1,468,006,400
where `blk.10` actually begins at 2,989,328,704. It was streaming embeddings
and metadata and reporting them as layers.

`vapor_engine.c` compounded it — a hardcoded 32 layers against a 42-layer
model, `avx2_vec_dot(x, x, 8) * 0.001f` over a zeroed buffer, and a fixed
`printf` presented as model output.

### What replaces it

`vapor_ram/gguf.py` parses the GGUF tensor directory: names, shapes,
quantisation types and exact byte ranges, with block-aware sizing for every
ggml type. The check that matters — the last tensor ends at 4,977,171,584,
exactly the file size.

| | |
| --- | ---: |
| Transformer blocks | 42 (matches the file's `block_count`) |
| Tensors | 720 |
| Block data begins at | byte 2,386,145,088 |
| Per-block span | ~61 MB |
| Streamable | 2.41 GB |
| Resident (embeddings, norms) | 2.21 GB |

`vapor_engine` is now a streaming inspector: real byte ranges in, measured JSON
timings out. It does not claim to generate anything.

### The measurement

Press **Measure** in Brain Cortex. On NVMe this reports **~990 MB/s** under
`O_DIRECT` and **~59 ms per block**.

Which gives the number worth having: streaming all 42 blocks for every token
would cost **~2.5 s/token (~0.4 tok/s)**, against **6.8 tok/s** with the
weights resident. **Trading roughly 17× throughput is what the 1.5 GB ceiling
would cost on this hardware.**

### Dashboard fixes

- **Generation state survived nothing.** The chat view unmounts when another
  tab is selected, taking `isGenerating`, the timings and the `AbortController`
  with it: the stop button vanished mid-reply, the run could no longer be
  cancelled, and the token/timing footer never appeared — while the stream kept
  running. Generation now lives outside React and is read through
  `useSyncExternalStore`.
- **Profiling never sent the API key**, so on a shared server it answered 401
  and rendered empty while every other tab worked.
- **"KV cache slots" displayed `n_ctx`.** Those are tokens; the slot count is 1
  in single-tenant mode. Split apart, and joined by threads-in-use (with the
  topology behind it) and measured streaming bandwidth.

## ⚠️ Known Limitations

- **The 1.5 GB RAM ceiling is not met.** llama.cpp memory-maps the full GGUF;
  measured RSS is 6.8–8.1 GB depending on context size.
- **The streaming path is a measurement path, not the token path.** Generation
  runs through llama.cpp. Routing generation through the C streamer means
  writing GGUF tensor loading, Q4_K/Q6_K dequantisation, RMSNorm, RoPE, GQA
  attention, SwiGLU, sampling and a tokenizer — and the measurement above
  suggests what it would cost.
- Per-kernel attribution (attention vs. matmul vs. LM head) is not
  instrumented, so it is omitted rather than estimated.

## 📦 Install

```bash
pip install --pre vapor-ram==1.0.7a6
```
