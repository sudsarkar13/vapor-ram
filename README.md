# VaporRAM 💨

**VaporRAM** is a local inference server, CLI and web dashboard for **google/gemma-4-E4B-it**, packaged for consumer hardware.

It provides an OpenAI-compatible HTTP API, a terminal chat client, network sharing behind an API key, and a dashboard that reports only measured values. Token generation runs on **llama.cpp**.

Its research goal is to run the model under a **1.5 GB RAM ceiling** by streaming transformer layers from NVMe rather than keeping them resident. The streaming reader — unbuffered `O_DIRECT` reads with aligned double buffers and kernel prefetch hints — is implemented in pure C under [`c/`](c/), and now reads the real byte ranges of each block resolved from the GGUF tensor directory. It is a measurement path, not the token path.

> **Current status (beta):** the server, CLI, sharing and dashboard are feature-complete and tested. The **RAM ceiling is not met** — llama.cpp memory-maps the full GGUF, so measured RSS with the Q4_K_M weights is 6.8–8.1 GB depending on context size.
>
> That is now a measured trade rather than an open question. At **~990 MB/s** under `O_DIRECT`, streaming all 42 blocks for every token would cost **~2.5 s/token (~0.4 tok/s)**, against **6.8 tok/s** with the weights resident — roughly **17x**. Reaching the ceiling means paying that, and writing a full inference engine to do it. The dashboard measures both numbers on your own hardware; treat the ceiling as a goal the project has costed, not a feature that is nearly done.

[![PyPI version](https://img.shields.io/pypi/v/vapor-ram.svg)](https://pypi.org/project/vapor-ram/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/vapor-ram?color=06b6d4&style=flat-square)](https://pypi.org/project/vapor-ram/)
[![Docs](https://img.shields.io/badge/Docs-Live-cyan.svg)](https://sudsarkar13.github.io/vapor-ram/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![RAM Ceiling](https://img.shields.io/badge/RAM_Ceiling-target_1.5_GB-yellow.svg)](#hardware--system-requirements)
[![Status](https://img.shields.io/badge/Status-alpha-orange.svg)](CHANGELOG.md)
[![CI Pipeline](https://img.shields.io/badge/CI-Passing-success.svg)](.github/workflows/ci.yml)

---

## Key Features

- **Live Memory Telemetry**: The dashboard and `/v1/stats` report the engine's **actual measured RSS**, host RAM and KV-cache projections — no estimated or placeholder figures.
- **Cross-Platform Engine**: Full native support for **Linux** (x86_64) and **macOS MacBooks** (Apple Silicon M1/M2/M3/M4 & Intel).
- **Sequential Layer Pipeline (SLP)**: Zero-copy unbuffered `O_DIRECT` NVMe SSD layer streaming with asynchronous POSIX kernel prefetching hints (`POSIX_FADV_WILLNEED`).
- **AVX2 SIMD & ARM NEON Kernels**: Hand-written matrix-vector kernels in the C engine, with an OpenMP build (`make -C c`). Benchmark them on your own hardware with `./vapor bench`.
- **int8 Quantized KV Cache**: Compresses Key & Value attention states with per-token scale factors (implemented in [`c/kv_cache.c`](c/kv_cache.c); used by the C engine path).
- **OpenAI-Compatible API**: Built-in HTTP server supporting `/v1/chat/completions`, `/v1/responses`, `/v1/models`, and `/health`.
- **Web UI & Interactive CLI**: Includes an interactive terminal chat mode (`vapor chat`) and a web dashboard (`vapor web`).

---

## Hardware & System Requirements

| Resource | Minimum Requirement | Recommended |
| :--- | :--- | :--- |
| **RAM Ceiling** | design target: **1.5 GB** (not yet met — see status above) | — |
| **Actual RSS today** | ~**6 GB** with Q4_K_M weights via llama.cpp | 8 GB+ system RAM |
| **Storage** | 18 GB NVMe SSD | PCIe Gen3 / Gen4 NVMe SSD |
| **Supported OS** | **Linux** (x86_64, WSL2), **macOS** (MacBooks M1–M4 & Intel) | Linux (x86_64), macOS (Apple Silicon) |
| **Build Tools** | `gcc` / `clang` / Apple Clang, `make`, Python 3.9+ | GCC 11+ / Apple Clang with OpenMP |

---

## Installation

### Option 1: Install via PyPI (Recommended)

```bash
pip install vapor-ram
```

### Option 2: Prebuilt Release

Download and extract the latest prebuilt binary tarball:

```bash
mkdir vapor-ram && cd vapor-ram
tar xzf vapor-ram-v1.0.1-linux-x86_64.tar.gz
```

### Option 3: Build from Source

Clone the repository and compile using `make`:

```bash
git clone https://github.com/sudsarkar13/vapor-ram.git
cd vapor-ram
make -C c
```

---

## Usage Guide

The project includes a CLI launcher called `vapor` (`./vapor` or `python3 vapor`).

### 1. System Diagnostics & Resource Planning

Run diagnostics to check system capabilities and memory budget compliance:

```bash
# Run hardware diagnostic checks
./vapor doctor

# View RAM ceiling budget breakdown (< 1.5 GB)
./vapor plan
```

### 2. Interactive Terminal Chat

Launch an interactive chat session:

```bash
./vapor chat --preset coder
```

### 3. One-Shot Prompt Generation

Execute a quick single prompt generation from the command line:

```bash
./vapor run "Explain quantum computing in simple terms."
```

### 4. OpenAI-Compatible API Server

Start an HTTP server supporting OpenAI endpoints (`/v1/chat/completions`):

```bash
./vapor serve --host 0.0.0.0 --port 8000
```

Query the API using `curl`:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-4-E4B-it",
    "messages": [{"role": "user", "content": "Hello! What can you do?"}]
  }'
```

### 5. Web Interface

Start the server and automatically launch the Web UI in your default browser:

```bash
./vapor web
```

`vapor web` binds `127.0.0.1` — the dashboard is reachable from this machine
only. Add `--share` to open it to the rest of the network.

### 6. Sharing the Model Across Devices

`vapor serve` binds every interface, so any device on the same network can
talk to the model. Because that also means anyone on that network can, the
server requires an API key whenever it is not bound to loopback. The key is
generated on first use and stored in `~/.vapor-ram/api_key` (mode `0600`), so
clients configured once keep working across restarts.

```bash
./vapor serve            # shared on the LAN, key required
./vapor share            # print the URL, key and ready-to-paste clients
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
| `./vapor serve --api-key mykey` | use a specific key instead of the generated one |
| `./vapor serve --new-key` | issue a new key, revoking the old one |
| `./vapor serve --no-auth` | serve with no key at all — everyone on the network gets access |
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

## Configuration & Preset Flags

You can customize execution using presets or flags:

| Subcommand / Flag | Description |
| :--- | :--- |
| `./vapor config` | Interactive terminal configuration wizard |
| `./vapor profile` | High-precision RSS memory profiler |
| `./vapor inspect` | Inspect model weight files and tensor layout |
| `./vapor bench` | Run AVX2 SIMD core throughput benchmark |
| `./vapor presets` | List available persona presets (`coder`, `reasoner`, `concise`) |
| `./vapor share` | Show the URL, API key and client snippets for other devices |
| `./vapor stop` | Stop a running server from another terminal |
| `./vapor lan` | Show this machine's LAN address |

### Reasoning

`gemma-4-E4B-it` supports reasoning natively: its chat template takes an
`enable_thinking` flag, injects `<|think|>` at the top of the system turn, and
emits the thought process inside `<|channel>thought … <channel|>` before the
answer. VaporRAM enables it by default when the active model's template
supports it, and detects that by reading the template out of the GGUF rather
than assuming.

In the dashboard, reasoning appears above each reply as a collapsed
**Thinking** block that animates while it streams; click it to read the
working-out. The sidebar has a switch, and the CLI has flags:

```bash
vapor serve --no-think          # reasoning off for this server
vapor run --think "..."         # reasoning for one prompt
vapor chat                      # /think toggles mid-session
```

Per request, send `{"thinking": false}` in the body. Over the API, reasoning
streams on its own `delta.reasoning_content` field, so a client that does not
know about it renders the answer alone rather than mixing the two.

Two things worth knowing. Reasoning shares the `max_tokens` budget with the
answer, and on a hard question it can consume all of it — VaporRAM detects that
and says so rather than returning an empty reply. And the model decides whether
a question warrants reasoning: simple prompts are answered directly.

### Weight Layout & Streaming

The **Brain Cortex** tab reads the GGUF tensor directory directly, so every
figure it shows is a value in the file rather than an estimate. For
`gemma-4-E4B-it-Q4_K_M`:

| | |
| --- | ---: |
| Transformer blocks | 42 (matches the file's own `block_count`) |
| Tensors | 720 |
| Block data begins at | byte 2,386,145,088 |
| Per-block span | ~61 MB |
| Streamable (all blocks) | 2.41 GB |
| Resident (embeddings, norms) | 2.21 GB |

Press **Measure** to stream those real ranges through `O_DIRECT`, bypassing the
page cache. On an NVMe SSD this reports ~990 MB/s and ~59 ms per block.

### Performance

Measured on a Ryzen 7 5700U (8 physical cores / 16 threads, 15 GB RAM) with
`gemma-4-E4B-it-Q4_K_M.gguf`, 32 decoded tokens per run:

| Threads | `n_ctx` | Decode | Peak RSS |
| ---: | ---: | ---: | ---: |
| 16 | 16384 | 1.96 tok/s | 8.07 GB |
| 16 | 4096 | 1.88 tok/s | 7.18 GB |
| **8** | 16384 | 6.49 tok/s | 8.07 GB |
| **8** | 4096 | **6.42–6.77 tok/s** | 6.80 GB |
| 6 | 4096 | 6.69–6.79 tok/s | 7.18 GB |
| 4 | 4096 | 6.25 tok/s | 7.18 GB |

Two things follow:

- **Thread count dominates.** One thread per hyperthread is ~3.4x slower than
  one per physical core, because llama.cpp's kernels already saturate each
  core's vector units. VaporRAM now defaults to physical cores; 4, 6 and 8 are
  within noise of each other, so there is little to gain by tuning further.
  `VAPOR_N_THREADS` overrides it.
- **Context size costs memory, not speed.** Decode throughput is unchanged
  between 4096 and 16384, but the KV cache grows ~1.3 GB. Pick the smallest
  window your conversations need — on a 16 GB machine, 16384 leaves little
  room for a browser and an editor, and once the host starts swapping,
  throughput falls much further than these figures suggest.

The weights are preloaded when the server starts, so the first message does not
pay the ~5-9s load on top of its own generation.

### Stopping the Server

CTRL+C stops the server, including while the engine is mid-generation.
CTRL+\ works too. If neither reaches the process — some terminals do not
deliver the signal to the foreground process — stop it from anywhere with:

```bash
./vapor stop                 # same path as the dashboard's Stop button
```

You can also type `q` and press Enter in the server's own terminal, or use the
PID printed in the startup banner. Run with `VAPOR_DEBUG_SIGNALS=1` to see
which shutdown path is armed and whether the terminal can generate signals at
all.

---

## Project Structure

- `c/vapor_engine`: Streaming inspector. Given a GGUF and a plan of byte ranges, streams them through the `O_DIRECT` reader and reports measured per-block timings as JSON. It does not generate tokens.
- `vapor_ram/gguf.py`: GGUF container parser — tensor directory, shapes, quantisation types and exact byte ranges.
- `vapor_ram/cortex.py`: Resolves real layer ranges from the GGUF and drives the inspector.
- [vapor](file:///home/sudeepta/Ubuntu-Owner/GitHub/vapor-ram/vapor): Main Python CLI frontend launcher.
- [doctor.py](file:///home/sudeepta/Ubuntu-Owner/GitHub/vapor-ram/doctor.py): Installation and hardware diagnostic script.
- [openai_server.py](file:///home/sudeepta/Ubuntu-Owner/GitHub/vapor-ram/openai_server.py): OpenAI-compatible HTTP API server implementation.
- [resource_plan.py](file:///home/sudeepta/Ubuntu-Owner/GitHub/vapor-ram/resource_plan.py): Dynamic memory budget calculation planner.
- [version.py](file:///home/sudeepta/Ubuntu-Owner/GitHub/vapor-ram/version.py): Engine version information.
- `web/`: Frontend dashboard UI static assets.
- `docs/`: GitHub Pages documentation website and screenshot guides.

---

## License

This project is licensed under the Apache 2.0 License. See the [LICENSE](file:///home/sudeepta/Ubuntu-Owner/GitHub/vapor-ram/LICENSE) file for details.
