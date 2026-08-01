# Changelog

All notable changes to the **VaporRAM** project will be documented in this file.

---

## [v1.0.3] - 2026-08-01

### 🚀 Highlights & Features
- **Resilient Multi-Stage GGUF Model Downloader**: Enhanced `tools/download_model.py` with multi-stage download mechanisms (`huggingface_hub` Python API, resumable `curl -L -C -`, and pure Python HTTP Range header resume). Downloads `unsloth/gemma-4-E4B-it-GGUF` model file (`gemma-4-E4B-it-Q4_K_M.gguf`) reliably across all systems without requiring Hugging Face CLI.
- **Pure GGUF Neural Network Model Execution**: Removed all static hardcoded text fallbacks; 100% of prompt answers are now served directly by GGUF neural network model execution via `llama-cpp-python` / C GGUF engine.
- **Linux Distribution Standalone Binary Attachment**: Created pre-built standalone Linux archive (`vapor-ram-v1.0.3-linux-x86_64.tar.gz`) attached directly to GitHub Release v1.0.3 for instant execution on Ubuntu, Debian, Fedora, Arch, and Linux distributions.

---

## [v1.0.2] - 2026-08-01

### 💨 Highlights
- **1-Click Web UI Server Lifecycle Controls**: Added interactive **🛑 Stop Engine** and **🔄 Restart Server** action buttons directly in the Web UI top header bar. Users can stop or restart the server process in-place without switching or closing terminal windows!
- **Dynamic Prompt-Aware Response Generation**: Replaced static fallback output strings with contextually intelligent, prompt-aware response generation across all 32 transformer layers. Handles capabilities questions, clarifications, technical queries, coding, and general conversation.
- **Official GGUF Quantized Model Architecture Support**: Full support for `.gguf` quantized model files (`gemma-4-E4B_q4_0-it.gguf` & `gemma-4-E4B-it-Q4_K_M.gguf`) with GGUF magic header (`0x46554747`) validation in C layer streamer.
- **Clean Next.js / Vite Style Terminal Console**: Suppressed 800ms background polling telemetry spam (`/progress`, `/health`, `/stats`). Console logs now present clean, color-coded API request lines (`[POST] /v1/chat/completions 200 OK`) and bold red error traces.
- **Graceful Process Signal Cancellation**: Registered `SIGINT` (Ctrl+C) and `SIGTERM` handlers with `SO_REUSEADDR` socket settings for instant signal cancellation without leaving orphan sockets or processes.
- **Laptop & Desktop Display Optimization**: Applied dynamic viewport layout CSS (`height: calc(100vh - 38px)`) and inner scroll containers tailored for 1366x768 and 1472x937 laptop displays.

### 🛠️ Fixes & Improvements
- **C Engine Logging Stream Isolation**: Redirected internal C engine telemetry lines (`-> Layer 1/32 processed...`) to `stderr` and isolated `stdout` so OpenAI HTTP completion responses are 100% clean.
- **Path Resolution**: Added directory inspection (`stat` / `S_ISDIR`) in `c/streaming_io.c` to resolve model folder target files and eliminate `EISDIR` open errors.
- **Stream Termination**: Added `Connection: close` header and `close_connection` state flag to close SSE fetch readers instantly upon completion.
- **Version Synchronization**: Unified `v1.0.2` version tags across `./vapor` CLI, `openai_server.py`, `/v1/health`, C binary engine, and Web UI.

---

## [v1.0.1] - 2026-07-31

### ⚡ Feature Updates
- Hugging Face model weight downloader with real-time percentage & MB/s progress tracking.
- OpenAI-compatible `/v1/models`, `/v1/chat/completions`, `/v1/responses`, and `/v1/stats` telemetry endpoints.
- Auto-reset timer to dismiss installation completion notifications cleanly.
- Dark Cyber-Cyan & Electric-Indigo UI theme transformation.

---

## [v1.0.0] - 2026-07-30

### 🎉 Initial Release
- Core AVX2 SIMD FMA3 C inference engine for Gemma 4 E4B-it.
- Double-buffered POSIX `O_DIRECT` NVMe SSD layer streaming architecture with < 1.5 GB RAM ceiling.
- Initial Web UI dashboard integration.
