# v1.0.7-alpha.5 — Alpha Release

## 🔄 What's Changed (v1.0.7-alpha.4 ➔ v1.0.7-alpha.5)

This release makes the model usable from other devices, makes the server
stoppable, and makes it roughly **28× faster** in the configuration it shipped
with.

### Network sharing

The model can now be reached from any device on your network. A key is required
whenever the server binds a non-loopback interface, so exposing the engine
cannot silently leave it open — `--no-auth` is the explicit opt-out and the
banner says so. Keys live in `~/.vapor-ram/api_key` (mode `0600`), never in the
tracked `vapor.json`.

```bash
vapor serve     # shared on the LAN, key required and printed
vapor share     # URL, key, and paste-ready client snippets
```

Clients present the key as `Authorization: Bearer`, `X-API-Key`, or `?key=` —
the last so a phone can open one tappable link.

**Security fix:** authentication was previously only enforced on POST. Every GET
was open to anyone who could reach the port even with `--api-key` set, including
`/v1/system/progress` (filesystem paths) and `/v1/doctor` (hardware).

### Performance

`n_threads` used `os.cpu_count()`, running one thread per hyperthread. On a
Ryzen 7 5700U that costs **3.4×** throughput, because llama.cpp's kernels
already saturate each core's vector units.

| Threads | `n_ctx` | Decode | Peak RSS |
| ---: | ---: | ---: | ---: |
| 16 (old) | 16384 | 1.96 tok/s | 8.07 GB |
| **8 (new)** | 16384 | 6.49 tok/s | 8.07 GB |
| **8 (new)** | 4096 | **6.42–6.77 tok/s** | 6.80 GB |

Context size does not affect decode speed at all — only memory. Weights are now
preloaded at startup, so the first message no longer pays the load on top of its
own generation.

### Stopping the server

CTRL+C was ignored while llama.cpp was loading or decoding, because a Python
signal handler only runs when the main thread reaches the eval loop. Shutdown
now waits in `sigwait()`, with signals blocked before any thread is created.
For terminals that never deliver the signal at all, the foreground process group
and `ISIG` state are detected and reported, `ISIG` is repaired when cleared, and
a console watchdog reads `^C` as a raw byte. `vapor stop` works from anywhere.

### Dashboard

Headings on Brain Cortex, Profiling and Doctor rendered in Playfair Display, a
serif whose hairlines are close to invisible at the 11–12px uppercase sizes
those headings use. They now share the body sans.

The KV cache figure was **8× low** — 216 MB reported against ~1.7 GB actually
allocated. It counted K but not V, assumed int8 where llama.cpp defaults to f16,
and excluded the shared-KV layers despite llama.cpp allocating a full-size SWA
cache. Now within 13% of measured.

### Removed

VaporRAM has no thinking mode. The `coder` and `reasoner` presets prefixed their
system instruction with `<|think|>` — not a Gemma control token, tokenised as
literal text, consuming context for nothing. An `enable_thinking` config flag no
code read is gone too.

## ⚠️ Known Limitations

- **The 1.5 GB RAM ceiling is not met.** llama.cpp memory-maps the full GGUF;
  measured RSS is 6.8–8.1 GB depending on context size. The ceiling is a
  planning target, not an enforced limit.
- The `O_DIRECT` layer streamer in `c/streaming_io.c` builds but is not wired
  into the token path, so per-layer streaming state is not reported.
- Per-kernel attribution (attention vs. matmul vs. LM head) is not instrumented.

## 📦 Install

```bash
pip install --pre vapor-ram==1.0.7a5
```
