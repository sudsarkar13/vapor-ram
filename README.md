# VaporRAM 💨

**VaporRAM** is an ultra-lightweight C/C++ inference engine specifically engineered for **google/gemma-4-E4B-it**. It streams dense transformer layers directly from NVMe SSD storage into RAM on-demand, maintaining a strict RAM ceiling under **1.5 GB** (vaporizing memory pressure).

---

## Key Features

- **Ultra-Low Memory Footprint**: Runs Gemma 4 E4B-it under a strict **1.5 GB RAM ceiling**.
- **Sequential Layer Pipeline (SLP)**: Double-buffered `O_DIRECT` NVMe SSD layer streaming.
- **AVX2 & OpenMP Acceleration**: Tailored SIMD kernels for AMD Ryzen and Intel CPUs.
- **Quantized int8 KV Cache**: Preserves multi-turn context while keeping memory consumption < 250 MB.
- **Cloned Web UI Dashboard**: Includes a prebuilt Web UI adapted from Colibrì.
- **Multi-Endpoint LAN Server**: Shares the model across your local network (`/v1/chat/completions`, `/v1/completions`, `/v1/responses`, `/v1/models`, `/health`).

---

## Directory Structure

```
vapor-ram/
├── c/
│   ├── vapor_engine.c        # Main SIMD C execution runtime
│   ├── streaming_io.c        # Unbuffered O_DIRECT NVMe layer streamer
│   ├── kv_cache.c            # Quantized int8 KV cache manager
│   └── Makefile              # Fast AVX2 build configuration
├── web/
│   └── dist/                 # Cloned Web UI dashboard assets
├── vapor                     # Main CLI launcher
├── doctor.py                 # System & NVMe speed diagnostics
├── openai_server.py          # Multi-endpoint LAN HTTP API server
└── resource_plan.py          # Memory allocation calculator
```

---

## Quick Start

### 1. Build the Engine
```bash
make -C c
```

### 2. System Diagnostics & Resource Plan
```bash
./vapor doctor
./vapor plan
```

### 3. Interactive Terminal Chat
```bash
./vapor chat
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
Access from any laptop or mobile device on your local Wi-Fi / network via:
- `http://<YOUR_LOCAL_IP>:8000/v1/chat/completions`
- `http://<YOUR_LOCAL_IP>:8000/v1/responses`

---

## License

Apache 2.0 License.
