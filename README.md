# VaporRAM 💨

**VaporRAM** is a local inference server, CLI and web dashboard for **google/gemma-4-E4B-it**, packaged for consumer hardware.

It gives you an OpenAI-compatible HTTP API, a terminal chat client, network sharing behind an API key, and a dashboard that shows only values it has measured. Token generation runs on **llama.cpp**.

The project's research goal is to run the model under a **1.5 GB RAM ceiling** by streaming transformer blocks from NVMe instead of keeping them resident. That goal is **not met**, and this README says what is true instead.

[![PyPI version](https://img.shields.io/pypi/v/vapor-ram.svg)](https://pypi.org/project/vapor-ram/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/vapor-ram?color=06b6d4&style=flat-square)](https://pypi.org/project/vapor-ram/)
[![Docs](https://img.shields.io/badge/Docs-Live-cyan.svg)](https://sudsarkar13.github.io/vapor-ram/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-stable-brightgreen.svg)](CHANGELOG.md)
[![CI Pipeline](https://img.shields.io/badge/CI-Passing-success.svg)](.github/workflows/ci.yml)

---

## What is actually true

Every figure below was measured on the machine described under
[Performance](#performance), with `gemma-4-E4B-it-Q4_K_M.gguf`. Reproduce them
yourself with `vapor bench`, `vapor doctor` and the dashboard's Profiling tab.

| Claim | Reality |
| :--- | :--- |
| RAM ceiling | **Target 1.5 GB. Not met.** Measured peak RSS is **7.27 GB** at `n_ctx` 8192 and **8.72 GB** at 16384. |
| How weights are loaded | llama.cpp **memory-maps** the whole GGUF. Nothing is streamed during generation. |
| Weight format | Mixed K-quant: **Q4_K, Q5_K, Q6_K**, plus F32 and BF16 tensors. Not int4. |
| Throughput | **4.0–5.3 tok/s** on the reference machine, reasoning on or off. |
| The C engine | A **measurement tool**. It streams real byte ranges and reports timings. It does not generate tokens. |
| SIMD kernels | A **standalone microbenchmark** (`vapor bench --simd`). Not on the token path — llama.cpp does the arithmetic. |
| KV cache | llama.cpp's own **f16** cache. The int8 code in `c/kv_cache.c` is not on the token path. |

If streaming ever did serve generation, this is what it would cost — also
measured, on this machine's NVMe:

> **974.7 MB/s** under `O_DIRECT`, **60.0 ms** per block (52.3–85.5 ms).
> Streaming all 42 blocks for every token = **2.54 s/token (0.39 tok/s)**,
> against **~5 tok/s** with the weights resident: roughly **13x slower**.
>
> That is the price of the 1.5 GB ceiling. It is a costed research goal, not a
> feature that is nearly finished.

---
## Key Features

- **OpenAI-compatible API** — `/v1/chat/completions` (streaming and not), `/v1/responses`, `/v1/models`, `/health`. Point any OpenAI SDK at it by changing `base_url`. Responses carry a real `usage` block.
- **Reasoning you can read** — `gemma-4-E4B-it` reasons natively. The dashboard shows the thought process as it streams, in a block you can expand and read, with four effort levels.
- **Network sharing behind an API key** — one command exposes the model to your LAN; the key is generated on first use and stored outside the repo at `~/.vapor-ram/api_key` (mode `0600`).
- **Measured telemetry** — the dashboard reports the server's real RSS, host RAM, the GGUF's actual tensor layout, and the throughput of your last generation. If a figure cannot be measured, it is not shown.
- **GGUF introspection** — a from-scratch parser reads the tensor directory, so the Brain Cortex tab shows byte ranges from the file rather than estimates.
- **Streaming measurement path** — a C reader streams the model's real block ranges with `O_DIRECT` and reports per-block timings, so the streaming design can be costed on your own SSD.
- **Cross-platform** — Linux (x86_64) and macOS (Apple Silicon and Intel). Tested in CI on both.
- **Terminal client** — `vapor chat` for an interactive session, `vapor run` for one-shot prompts.

---

## Hardware & System Requirements

The 1.5 GB target does not describe what the software needs today. These are
the real requirements for running it as it currently works:

| Resource | Minimum | Recommended |
| :--- | :--- | :--- |
| **RAM** | **8 GB** — measured peak RSS is 7.27 GB at `n_ctx` 8192 | **16 GB**, and more if you want `n_ctx` 16384 alongside a browser |
| **Storage** | **6 GB** for the Q4_K_M weights (4.98 GB) plus room to download | NVMe SSD |
| **CPU** | x86_64 with AVX2, or Apple Silicon | 8+ physical cores |
| **OS** | Linux (x86_64, WSL2), macOS (Apple Silicon or Intel) | — |
| **Python** | 3.9+ | 3.12 |
| **Build tools** | `gcc`/`clang`, `make` — only needed for the optional C measurement tools | — |

> On a 16 GB machine, `n_ctx` 16384 leaves little headroom. Once the host
> starts swapping, throughput falls much further than the figures below.

---
## Installation

### Option 1: PyPI (recommended)

```bash
pip install vapor-ram
```

### Option 2: Prebuilt release

Download the tarball for your platform from the
[latest release](https://github.com/sudsarkar13/vapor-ram/releases/latest):

```bash
tar xzf vapor-ram-v<version>-linux-x86_64.tar.gz
cd vapor-ram-v<version>
```

Pre-release builds (alpha, beta, rc) are published alongside stable and are
listed on the [releases page](https://sudsarkar13.github.io/vapor-ram/releases.html).
Nothing is gated — take whichever you want.

### Option 3: From source

```bash
git clone https://github.com/sudsarkar13/vapor-ram.git
cd vapor-ram
pip install -e .
make -C c          # optional: builds the streaming inspector and SIMD microbenchmark
```

### Then get the weights

The model is **not** bundled — it is 4.98 GB, downloaded separately:

```bash
vapor download
```

---

## Usage Guide

Installed from PyPI the command is `vapor`; from a checkout, `./vapor`.

### 1. Diagnostics

```bash
vapor doctor        # hardware, dependencies, weights
vapor plan          # memory budget against the RAM ceiling target
vapor inspect       # GGUF tensor layout
```

### 2. Terminal chat

```bash
vapor chat --preset coder
```

### 3. One-shot prompt

```bash
vapor run "Explain quantum computing in simple terms."
```

### 4. OpenAI-compatible server

```bash
vapor serve --host 0.0.0.0 --port 8000
```

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-4-E4B-it",
    "messages": [{"role": "user", "content": "Hello! What can you do?"}]
  }'
```

### 5. Web dashboard

```bash
vapor web
```

`vapor web` binds `127.0.0.1` — reachable from this machine only. Add
`--share` to open it to the network.

---
### 6. Sharing across devices

`vapor serve` binds every interface, so any device on the same network can
talk to the model. Because that also means anyone on that network can, the
server requires an API key whenever it is not bound to loopback. The key is
generated on first use and stored in `~/.vapor-ram/api_key` (mode `0600`), so
clients configured once keep working across restarts.

```bash
vapor serve            # shared on the LAN, key required
vapor share            # print the URL, key and ready-to-paste clients
```

`vapor share` prints something like:

```
  ➜  Shared on LAN   : http://192.168.1.24:8000
  ➜  API for clients : http://192.168.1.24:8000/v1
  ➜  API key         : vr_8ZqK1sT4bN0pWm7xVhQrLdY2
  ➜  One-tap link    : http://192.168.1.24:8000/?key=vr_8ZqK1sT4bN0pWm7xVhQrLdY2
```

Clients may present the key three ways — pick whichever your client supports:

| Channel | Example | Best for |
| :--- | :--- | :--- |
| `Authorization: Bearer` | `-H "Authorization: Bearer vr_..."` | OpenAI-compatible SDKs |
| `X-API-Key` | `-H "X-API-Key: vr_..."` | scripts and `curl` |
| `?key=` query param | `http://host:8000/?key=vr_...` | opening the dashboard on a phone |

Any OpenAI client works by pointing `base_url` at the shared address:

```python
from openai import OpenAI
client = OpenAI(base_url="http://192.168.1.24:8000/v1", api_key="vr_...")
```

Opening the one-tap link on another device loads the dashboard, stores the key
in that browser, and strips it from the address bar. Visiting the bare host
instead prompts for the key.

**Key management**

| Command | Effect |
| :--- | :--- |
| `vapor serve --api-key mykey` | use a specific key instead of the generated one |
| `vapor serve --new-key` | issue a new key, revoking the old one |
| `vapor serve --no-auth` | serve with no key at all — everyone on the network gets access |
| `VAPOR_API_KEY=...` | set the key from the environment |

**Access from outside the network**

The LAN address only works locally. To reach the model from anywhere, put a
TLS tunnel in front of the server rather than forwarding the port on your
router — plain HTTP would send the API key across the internet in cleartext:

```bash
cloudflared tunnel --url http://localhost:8000
tailscale serve 8000            # private to your tailnet
ssh -R 8000:localhost:8000 user@your-vps
```

Then use the `https://` address the tunnel prints as the base URL, with the
same API key.

---

## Configuration & Commands

| Command | Description |
| :--- | :--- |
| `vapor config` | Interactive configuration wizard |
| `vapor init-config` | Write a default `vapor.json` |
| `vapor profile` | High-precision RSS memory profiler |
| `vapor inspect` | Inspect model weights and tensor layout |
| `vapor bench` | Measure `O_DIRECT` streaming throughput on the real model blocks |
| `vapor bench --simd` | Standalone AVX2/NEON dot-product microbenchmark (measures the CPU, not the model) |
| `vapor presets` | List persona presets (`coder`, `reasoner`, `concise`) |
| `vapor share` | Show URL, API key and client snippets for other devices |
| `vapor stop` | Stop a running server from another terminal |
| `vapor lan` | Show this machine's LAN address |

Settings live in `vapor.json`, written by the server whenever you change
something in the dashboard or CLI. `vapor.example.json` is the tracked
reference copy; `vapor.json` itself is deliberately **not** tracked in git so
the repository cannot overwrite your settings. Set `VAPOR_CONFIG_PATH` to keep
several independent configurations.

### Reasoning

`gemma-4-E4B-it` supports reasoning natively: its chat template takes an
`enable_thinking` flag, injects `<|think|>` at the top of the system turn, and
emits the thought process inside `<|channel>thought … <channel|>` before the
answer. VaporRAM enables it by default when the active model's template
supports it, detected by reading the template out of the GGUF rather than
assuming.

In the dashboard, reasoning appears above each reply in a **Thinking** block
that animates while it streams and is **open by default**, so the working-out
can be read as it arrives. Collapsing it is opt-in.

Four effort levels are available. The model's template has no effort
parameter — it takes only a boolean — so these are VaporRAM's own: each level
contributes a depth instruction placed with the thinking token at the top of
the system turn, plus a reasoning-token budget shown in the UI.

| Level | Behaviour | Budget |
| :--- | :--- | ---: |
| Low | A few quick steps. Fastest, best for simple questions. | ~256 tokens |
| Medium | Covers the main steps without labouring them. | ~768 tokens |
| **High** | Works through the problem and checks itself. **Default.** | ~2,048 tokens |
| Extra high | Explores alternatives and verifies each step. Slowest. | ~4,096 tokens |

```bash
vapor serve --no-think              # reasoning off for this server
vapor serve --think-level low       # or pick a level
vapor run --think "..."             # reasoning for one prompt
vapor chat                          # /think toggles mid-session
```

Per request, send `{"thinking": false}` or `{"reasoning_effort": "medium"}`.
Over the API, reasoning streams on its own `delta.reasoning_content` field, so
a client that does not know about it renders the answer alone rather than
mixing the two.

Two things worth knowing. Reasoning shares the `max_tokens` budget with the
answer, and on a hard question it can consume all of it — VaporRAM detects
that and says so rather than returning an empty reply. And the model decides
whether a question warrants reasoning: simple prompts are answered directly.

---
## Weight Layout

The **Brain Cortex** tab reads the GGUF tensor directory directly, so every
figure it shows is a value in the file rather than an estimate. The parser is
validated by construction: the last tensor must end at exactly the file size,
and for this model it does — byte 4,977,171,584 of a 4,977,171,584-byte file.

For `gemma-4-E4B-it-Q4_K_M.gguf`:

| | |
| :--- | ---: |
| File size | 4,977,171,584 bytes (4.98 GB) |
| Parameters | 7.52 B, at 5.28 bits/parameter |
| Tensors | 720 |
| Transformer blocks | 42 (matches the file's own `block_count`) |
| Hidden size | 2,560 |
| Attention heads | 8 (2 KV heads, 18 layers sharing KV) |
| Model max context | 131,072 tokens |
| Block data begins at | byte 2,386,145,088 |
| Per-block span | 56.9–71.7 MB (mean 61.7 MB) |
| Streamable (all blocks) | 2.59 GB |
| Resident (embeddings, norms) | 2.37 GB |

Weights by quantisation type, as bytes in the file:

| Type | Tensors | Share |
| :--- | ---: | ---: |
| Q4_K | 253 | 45.8% |
| Q5_K | 1 | 39.1% |
| Q6_K | 42 | 9.6% |
| F32 | 423 | 4.5% |
| BF16 | 1 | 1.1% |

---

## Performance

Reference machine: **AMD Ryzen 7 5700U** (8 physical cores / 16 threads),
15 GB RAM, NVMe SSD, Linux. Weights `gemma-4-E4B-it-Q4_K_M.gguf`. Reproduce
with `vapor bench` and the dashboard's Profiling tab.

### Memory and startup

| `n_ctx` | RSS before weights | RSS with weights | Peak during generation | Server start → ready |
| ---: | ---: | ---: | ---: | ---: |
| 8,192 | 0.99 GB | 7.24 GB | **7.27 GB** | 9.5 s |
| 16,384 | — | 8.69 GB | **8.72 GB** | 15.2 s |

Doubling the context window costs **1.45 GB** and does not change decode
speed. Pick the smallest window your conversations actually need.

Because llama.cpp memory-maps the weights, RSS is not a fixed number: under
memory pressure the kernel evicts mapped pages and RSS falls without the
server misbehaving. The figures above are peaks with memory available.

### Throughput

256-token generations, temperature 0:

| `n_ctx` | Reasoning off | Low | Medium | High |
| ---: | ---: | ---: | ---: | ---: |
| 8,192 | 4.38–5.30 tok/s | 4.09 | 4.38 | 4.31 |
| 16,384 | 4.08–5.18 tok/s | 4.38 | 4.04 | 4.04 |

**4.0–5.3 tok/s** across every configuration. Run-to-run variation on an
idle laptop is larger than the difference between reasoning levels, so treat
these as one range rather than a ranking. Reasoning does not slow generation
down; it produces more tokens, so a reply takes longer to finish.

Thread count is the setting that matters. llama.cpp's kernels already saturate
each core's vector units, so one thread per hyperthread is substantially slower
than one per physical core. VaporRAM defaults to physical cores;
`VAPOR_N_THREADS` overrides it.

Weights are preloaded at startup, so the first message does not pay the load
cost on top of its own generation.

### Streaming (`vapor bench`)

Streaming all 42 blocks through `O_DIRECT`, bypassing the page cache:

| | |
| :--- | ---: |
| Throughput | **974.7 MB/s** |
| Per block | 60.0 ms mean (52.3–85.5 ms) |
| Bytes streamed | 2.59 GB in 2.54 s |
| Peak reader buffer | 143.4 MB |
| **If every block were streamed per token** | **2.54 s/token (0.39 tok/s)** |

That last row is the cost of the 1.5 GB ceiling on this hardware: roughly
**13x slower** than the ~5 tok/s achieved with the weights resident. Reaching
the ceiling means paying it, and writing a full inference engine to do it.

### SIMD microbenchmark (`vapor bench --simd`)

A single-threaded dot product at the model's hidden size (2,560 floats),
200,000 iterations:

| | |
| :--- | ---: |
| Scalar | 2.76 GFLOPS |
| AVX2 + FMA | 14.13 GFLOPS |
| Speedup | **5.12x** |

This measures the CPU, not the model. Token generation runs on llama.cpp and
does not use this kernel.

---

## Stopping the Server

CTRL+C stops the server, including mid-generation. CTRL+\ works too. If
neither reaches the process — some terminals do not deliver the signal to the
foreground process group — stop it from anywhere with:

```bash
vapor stop                 # same path as the dashboard's Stop button
```

You can also type `q` and press Enter in the server's own terminal, or use the
PID printed in the startup banner. Run with `VAPOR_DEBUG_SIGNALS=1` to see
which shutdown path is armed and whether the terminal can generate signals at
all.

---

## Project Structure

| Path | What it is |
| :--- | :--- |
| [vapor](vapor) | CLI entry point |
| [vapor_ram/openai_server.py](vapor_ram/openai_server.py) | HTTP API server, prompt building, generation, telemetry |
| [vapor_ram/cli.py](vapor_ram/cli.py) | Subcommand definitions and dispatch |
| [vapor_ram/gguf.py](vapor_ram/gguf.py) | GGUF container parser — tensor directory, shapes, quantisation, byte ranges |
| [vapor_ram/cortex.py](vapor_ram/cortex.py) | Resolves real layer ranges and drives the streaming inspector |
| [vapor_ram/doctor.py](vapor_ram/doctor.py) | Hardware and installation diagnostics |
| [vapor_ram/resource_plan.py](vapor_ram/resource_plan.py) | Memory budget planner |
| [vapor_ram/paths.py](vapor_ram/paths.py) | Asset resolution for checkout and installed layouts |
| [c/vapor_engine.c](c/vapor_engine.c) | Streaming inspector. Given a GGUF and a plan of byte ranges, streams them through `O_DIRECT` and reports per-block timings as JSON. **Does not generate tokens.** |
| [c/streaming_io.c](c/streaming_io.c) | `O_DIRECT` reader with alignment handling and kernel prefetch hints |
| [c/kv_cache.c](c/kv_cache.c) | int8 KV quantisation. **Not on the token path** — llama.cpp uses its own f16 cache |
| [tools/simd_bench.c](tools/simd_bench.c) | Standalone AVX2/NEON dot-product microbenchmark |
| [web/](web/) | Next.js dashboard; `web/dist` is the committed static export the server serves |
| [docs/](docs/) | GitHub Pages site |
| [tests/test_engine.py](tests/test_engine.py) | Integration suite — 164 checks |

---

## License

Apache 2.0. See [LICENSE](LICENSE).
