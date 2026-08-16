# v1.0.7-beta.1 — First Beta

The code here is identical to `v1.0.7-alpha.6`. What changes is the claim the
project makes about itself.

## What beta means for VaporRAM

**The inference server is feature-complete and tested.** That is what this beta
covers:

- OpenAI-compatible HTTP API with real token streaming
- Network sharing behind an API key, enforced on every endpoint, with LAN and
  tunnel-based remote access
- Terminal chat with history, persona presets, model download with byte-accurate
  progress, runtime context control
- A dashboard where every figure is measured — RSS from the process, threads
  from the CPU topology, KV geometry and layer layout from the GGUF itself,
  throughput from real generations
- 112 automated checks, matrix-tested on Linux and macOS

**The 1.5 GB RAM ceiling is not met, and this release stops implying it is
imminent.** Generation runs on llama.cpp, which memory-maps the full GGUF;
measured RSS is 6.8–8.1 GB depending on context size.

That is now a costed trade rather than an open question. At a measured
**~990 MB/s** under `O_DIRECT`, streaming all 42 transformer blocks for every
token would cost **~2.5 s/token (~0.4 tok/s)**, against **6.8 tok/s** with the
weights resident — roughly **17×**. Reaching the ceiling means accepting that,
and writing a full inference engine (GGUF tensor loading, Q4_K/Q6_K
dequantisation, RMSNorm, RoPE, GQA attention, SwiGLU, sampling, tokenizer) to
get there.

The dashboard measures both numbers on your own hardware. The README now leads
with what VaporRAM is, and states the ceiling as a goal whose price is known.

## ⚠️ Known Limitations

- **RAM ceiling unmet**: 6.8–8.1 GB measured, against a 1.5 GB target.
- **The C streamer is a measurement path, not the token path.**
- Per-kernel attribution (attention vs. matmul vs. LM head) is not
  instrumented, so it is omitted rather than estimated.
- First install compiles `llama-cpp-python` from source and can take several
  minutes.

## 📦 Install

```bash
pip install --pre vapor-ram==1.0.7b1
```

## Upgrading from alpha

No migration needed. Your `~/.vapor-ram/api_key` and `vapor.json` are
unchanged. If you are coming from before `alpha.5`, note that `vapor web` now
binds loopback by default — use `vapor web --share` to expose it.
