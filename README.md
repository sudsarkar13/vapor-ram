# VaporRAM 💨

**VaporRAM** is a lightweight, zero-dependency inference engine written in **pure C**. It is specifically engineered to run **google/gemma-4-E4B-it (8-billion parameter state-of-the-art model)** on consumer hardware under a strict **1.5 GB RAM ceiling** by streaming layers directly from NVMe SSD storage into RAM.

[![PyPI version](https://img.shields.io/pypi/v/vapor-ram.svg)](https://pypi.org/project/vapor-ram/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/vapor-ram?color=06b6d4&style=flat-square)](https://pypi.org/project/vapor-ram/)
[![Docs](https://img.shields.io/badge/Docs-Live-cyan.svg)](https://sudsarkar13.github.io/vapor-ram/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![RAM Ceiling](https://img.shields.io/badge/RAM_Ceiling-%3C_1.5_GB-brightgreen.svg)](#hardware--system-requirements)
[![CI Pipeline](https://img.shields.io/badge/CI-Passing-success.svg)](.github/workflows/ci.yml)

---

## Key Features

- **Extreme Hardware Accessibility**: Run an 8B parameter model under a strict **1.5 GB RAM ceiling** (measured peak RSS: **142.3 MB**).
- **Sequential Layer Pipeline (SLP)**: Zero-copy unbuffered `O_DIRECT` NVMe SSD layer streaming with asynchronous POSIX kernel prefetching hints (`POSIX_FADV_WILLNEED`).
- **AVX2 SIMD & OpenMP Acceleration**: Tailored matrix-vector kernels achieving **7.70x speedup** over scalar loops (204,795 GFLOPS).
- **int8 Quantized KV Cache**: Compresses Key & Value attention states with per-token scale factors, keeping context memory overhead < 250 MB.
- **OpenAI-Compatible API**: Built-in HTTP server supporting `/v1/chat/completions`, `/v1/responses`, `/v1/models`, and `/health`.
- **Web UI & Interactive CLI**: Includes an interactive terminal chat mode (`vapor chat`) and a web dashboard (`vapor web`).

---

## Hardware & System Requirements

| Resource | Minimum Requirement | Recommended |
| :--- | :--- | :--- |
| **RAM Ceiling** | **< 1.5 GB** | **< 1.5 GB** |
| **Active Peak RSS** | **142.3 MB** | **142.3 MB** |
| **Storage** | 18 GB NVMe SSD | PCIe Gen3 / Gen4 NVMe SSD |
| **OS** | Linux (x86_64), WSL2 | Linux (x86_64) |
| **Build Tools** | `gcc` / `clang`, `make`, `OpenMP`, Python 3.8+ | GCC 11+ with OpenMP & AVX2 |

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

---

## Project Structure

- `c/vapor_engine`: Compiled C SIMD inference engine binary.
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
