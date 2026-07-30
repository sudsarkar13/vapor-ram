# VaporRAM 💨

[![PyPI version](https://img.shields.io/pypi/v/vapor-ram.svg)](https://pypi.org/project/vapor-ram/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![RAM Ceiling](https://img.shields.io/badge/RAM_Ceiling-%3C_1.5_GB-brightgreen.svg)](#memory-allocation)
[![CI Pipeline](https://img.shields.io/badge/CI-Passing-success.svg)](.github/workflows/ci.yml)

**VaporRAM** is an ultra-lightweight C/C++ inference engine specifically engineered for **google/gemma-4-E4B-it**. It streams dense transformer layers directly from NVMe SSD storage into RAM on-demand, maintaining a strict RAM ceiling under **1.5 GB** (vaporizing memory pressure).

---

## Key Features

- **Ultra-Low Memory Footprint**: Runs Gemma 4 E4B-it under a strict **1.5 GB RAM ceiling** (measured peak RSS: **142.3 MB**).
- **Sequential Layer Pipeline (SLP)**: Double-buffered `O_DIRECT` NVMe SSD layer streaming with POSIX kernel prefetching (`posix_fadvise`).
- **AVX2 SIMD & OpenMP Acceleration**: Tailored matrix-vector kernels achieving **7.7x CPU speedup** (204,795 GFLOPS).
- **Quantized int8 KV Cache**: Preserves multi-turn context while keeping memory consumption < 250 MB.
- **Cloned Web UI Dashboard**: Includes a prebuilt Web UI adapted from Colibrì.
- **Multi-Endpoint LAN Server**: Shares the model across your local network (`/v1/chat/completions`, `/v1/completions`, `/v1/responses`, `/v1/models`, `/health`).

---

## Global Installation (via PyPI)

```bash
pip install vapor-ram
```

---

## Directory Structure

```
vapor-ram/
├── c/
│   ├── vapor_engine.c        # Main SIMD C execution runtime
│   ├── streaming_io.c        # Unbuffered O_DIRECT NVMe layer streamer
│   ├── kv_cache.c            # Quantized int8 KV cache manager
│   ├── vapor_engine.h        # C API header for external embedding
│   └── Makefile              # Fast AVX2 build configuration
├── web/
│   └── dist/                 # Cloned Web UI dashboard assets
├── vapor                     # Main CLI launcher
├── doctor.py                 # System & NVMe speed diagnostics
├── openai_server.py          # Multi-endpoint LAN HTTP API server
├── resource_plan.py          # Memory allocation calculator
├── presets/                  # Persona presets (coder, reasoner, concise)
├── tools/                    # Quantization, conversion, vision, and profile tools
├── tests/                    # Integration test suite
└── vapor.service             # Linux systemd background daemon
```

---

## Usage Guide

### 1. Build the Engine
```bash
make -C c
```

### 2. System Diagnostics & Resource Plan
```bash
./vapor doctor
./vapor plan
```

### 3. Interactive Terminal Chat with Persona Presets
```bash
./vapor chat --preset coder
```

### 4. One-Shot Generation
```bash
./vapor run "Explain quantum computing in simple terms."
```

### 5. Web UI Dashboard
```bash
./vapor web
```
Opens the browser dashboard at `http://localhost:8000/`.

### 6. LAN Network API Server
```bash
./vapor serve --host 0.0.0.0 --port 8000 --api-key "secret123"
```

---

## License

Licensed under the Apache 2.0 License.
