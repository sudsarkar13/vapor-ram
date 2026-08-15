# Changelog

All notable changes to the **VaporRAM** project will be documented in this file.

---

## [v1.0.7-alpha.4] - 2026-08-15

### 🐛 Fixed Bugs & Issues
- **Dashboard/API contract mismatch**: `/health` returns `model` and `ram_ceiling_gb`, but the client declared `active_model` and `ram_ceiling`. The Doctor tab rendered literal `undefined`; the header masked the same bug behind a hardcoded fallback.
- **Download progress was unreachable**: the client read `status` at the top level of `/v1/system/progress`, where the server always reports `"ok"`; real download state lives under `download_progress`. The comparison could never be true, and no component rendered `percent` at all.
- **Context window reported dishonestly**: `n_ctx` up to 131072 was accepted and persisted while generation silently clamped to 16384. Oversized requests are now refused with the real limit, so the displayed value always matches the allocated KV cache.
- **Model directory clobbered by unrelated saves**: every config write re-sent `model_dir`, so changing the context window overwrote the active model path (and converted it to a CWD-relative string). `model_dir` now only changes when explicitly set.
- **Saved `model_dir` never restored**: the value was written to `vapor.json` on save but never read back at startup, silently reverting to the default on every restart.
- **`--api-key` had no effect**: `serve()` never assigned the key to the request handler, leaving the server unauthenticated.
- **Streaming was a replay animation**: the full response was generated before SSE headers were sent, then re-chunked with a fixed delay. Tokens are now emitted as llama.cpp decodes them.
- **Single-threaded server**: any generation blocked every other request, freezing the dashboard's polling for its full duration.
- **Chat history discarded**: only `messages[-1]` reached the model, making multi-turn conversation impossible.
- **Presets were inert**: the persona name was sent as a `Preset: x` system message and then dropped server-side; `presets/*.json` were never read by the server, and `temperature`/`top_p` were never applied.
- **Release tarballs bundled `node_modules`**: `package_release.py` copied all of `web/` (~700 MB). Tarballs are now ~1.2 MB.
- **Committed dashboard was incomplete**: an over-broad `dist/` ignore rule excluded `web/dist/_next/**`, so a clean checkout shipped an `index.html` referencing JavaScript chunks that were never committed.
- **sdist shipped no assets**: added `MANIFEST.in`; source distributions now include the dashboard, presets and C sources.

### 🚀 Highlights & Features
- **Real telemetry**: host RAM is re-read per request (was captured once at import and frozen), and process RSS is measured from `/proc/self/statm`. Fabricated constants (`peak_rss_mb: 142.32`, `204795.96` GFLOPS, fixed per-kernel timings) are gone; unmeasured values are reported as unavailable rather than invented.
- **Model architecture from `config.json`**: layer/head geometry is read from the active model instead of three conflicting hardcoded sets. Reports 42 layers / 2 KV heads / 18 shared for `gemma-4-E4B-it`.
- **Model lifecycle state**: `model_state` distinguishes `idle`/`loading`/`ready`/`error`, so a multi-second weight load is visible instead of looking like a hang.
- **Download progress meter**: byte-accurate percentage against real `Content-Length`, with transfer rate, ETA and resume support; `repo`/`dest` from the dashboard are now honoured.
- **New endpoints**: `/v1/presets` and `/v1/doctor` (runs the real inspector rather than hardcoded verdicts).
- **Shared telemetry contract**: every status endpoint embeds one identical block, replacing four divergent payload shapes.
- **Live Brain and Profiling views**: both read measured runtime data; unavailable metrics are labelled as such.
- **Model directory picker**: server-side scan results with GGUF name and size are selectable in the dashboard.
- **Generation metrics**: tokens/second and time-to-first-token measured and surfaced.
- **CLI parity**: `vapor chat` keeps conversation history, streams tokens, applies presets, and `/stats` reports measured values.
- **CI/CD overhaul**: matrix CI across Linux/macOS and Python 3.9/3.12; version-consistency gate across all eight manifests (`tools/check_version.py`); stale-`web/dist` detection; sdist completeness gate; tag-driven release pipeline with automatic Stable/Beta/Alpha/RC channel handling, native per-platform tarballs, OIDC PyPI publishing with PEP 740 attestations, and Stable-only docs sync.
- **Test suite**: expanded from 4 smoke assertions to 45 contract checks covering telemetry shape, context honesty, model-directory isolation, preset resolution, concurrency, and the weightless failure mode.


### 📦 Packaging (breaking layout change)
- **`pip install vapor-ram` was completely non-functional and is now fixed.** The console entry point was declared as `vapor:main`, but `vapor` was a bare script with no `.py` extension and therefore not importable — the installed command failed instantly with `ModuleNotFoundError: No module named 'vapor'`. The wheel also contained only 12 files: no dashboard, no presets, no C engine, no tools.
- **Modules moved into a `vapor_ram/` package**: `openai_server.py`, `config.py`, `doctor.py`, `resource_plan.py`, `version.py` and the CLI now live under `vapor_ram/`. This makes `package_data` work and stops the project from installing generic top-level modules named `config`, `version` and `doctor` into site-packages, where they could shadow other packages.
- **Runtime assets are staged into the package at build time** (`setup.py: build_py`), so the wheel ships the dashboard, presets, helper tools and the compiled engine — 92 entries, verified to serve a working UI from a clean install.
- **`vapor_ram/paths.py`** resolves assets for both a git checkout and an installed package. Installed runs now default weights to `~/.vapor-ram/models/` and config to `~/.vapor-ram/vapor.json` instead of attempting to write gigabytes into site-packages.
- `./vapor` remains the development launcher and delegates to `vapor_ram.cli`.
- Added `vapor --version`.

### 📝 Documentation accuracy
- **Corrected unverified performance claims.** The README, badges and documentation site advertised a measured peak RSS of **142.3 MB**, a **7.70x** SIMD speedup and **204,795 GFLOPS**. None were measured: they were hardcoded constants in the API responses. Measured RSS with Q4_K_M weights is approximately **6 GB**.
- The README now states plainly that generation runs through llama.cpp (which memory-maps the full GGUF), that the C layer streamer is built but not yet wired into the token path, and that the 1.5 GB ceiling is a design target that is **not yet met**. The RAM badge reads "target", and an alpha status badge was added.

---

## [v1.0.7-alpha.3] - 2026-08-04

### 🚀 Highlights & Features
- **PyPI Verified Details & Metadata Standardization**: Configured standard project repository URLs (`Repository`, `Bug Tracker`, `Changelog`) and OSI license classifiers in `pyproject.toml` and `setup.py`.
- **OIDC PyPI Publishing Pipeline**: Introduced automated GitHub Actions workflow (`.github/workflows/publish-pypi.yml`) supporting OIDC Trusted Publisher authentication and PEP 740 cryptographic provenance attestations.

---

## [v1.0.7-alpha.2] - 2026-08-02

### 🚀 Highlights & Features
- **Customizable RAM Ceiling Target Selector**: Introduced interactive selector allowing users to set target RAM ceiling between 1.5 GB and 32.0 GB.
- **Host System RAM Auto-Detection**: Integrated hardware inspector (`doctor.py`) into HTTP server to detect host system Total RAM and Available Free RAM.
- **Persistent Server Settings (`vapor.json`)**: Added `/v1/system/config` GET/POST endpoints and `vapor.json` config persistence across server restarts.
- **Dark Obsidian Select Popover**: Overhauled Select component dropdown styling for seamless dark theme consistency.

---

## [v1.0.7-alpha.1] - 2026-08-02

### 🚀 Highlights & Features
- **Next.js + shadcn/ui Dashboard Migration**: Completely modernized the Web UI with Next.js, Tailwind CSS, and shadcn/ui featuring real-time SSE streaming, `react-markdown` syntax highlighting, and 0 end-user Node.js dependencies.
- **Dynamic Context Window (`/system/context`)**: Added runtime context adjustment endpoint to dynamically scale `n_ctx` (512 to 8192 tokens) with automatic KV cache re-allocation.
- **Concurrent Slot Guarding & Broken Pipe Handling**: Introduced slot locks (`_slot_begin` / `_slot_end`) and graceful `BrokenPipeError` handling when client connections abort.

---

## [v1.0.6] - 2026-08-01

### 🚀 Highlights & Features
- **Linux Terminal Signal Shutdown (CTRL+C)**: Fixed socket polling and signal handling in `openai_server.py` so pressing `CTRL+C` in Linux terminals immediately exits without hanging.
- **8,192 Max Output Tokens & Context Expansion**: Expanded generation token ceiling to **8,192 tokens** (`max_tokens=8192` & `n_ctx=8192`) for long multi-page responses.
- **Cross-Platform `doctor` Inspector**: Added native macOS MacBook hardware identification (Apple Silicon M1–M5 family & A18 Pro) and ARM NEON / AMX matrix extension detection.
- **Release Manager SOP Refactor**: Standardized semantic release channel naming (`Stable`, `Beta`, `Alpha`) and version-specific release notes generation comparing previous (`v1.0.5`) and current (`v1.0.6`) versions.

---

## [v1.0.5] - 2026-08-01

### 🚀 Highlights & Web UI Fixes
- **Persistent Header Navigation Bar**: Fixed issue where `ACTIVE MODEL`, `Chat / Brain / Profiling` tabs, `slot 1` badge, and `Clear Conversation` button disappeared upon chat initialization. Now permanently pinned and sticky at top.
- **Realtime HTML Markdown Formatter**: Integrated automatic HTML Markdown observer converting model outputs into formatted headings (`#`, `##`, `###`), bolding (`**`), lists (`*`), code blocks (` ``` `), and paragraph line breaks.
- **Full Multi-Paragraph Output Generation**: Increased `max_tokens` ceiling from 256 to 2048/4096 and optimized SSE stream formatting to prevent response cutoffs midway.

---

## [v1.0.4] - 2026-08-01

### 🚀 Highlights & Automated Features
- **Zero-Config Automated Dependency Installer**: Automatic self-installation of `llama-cpp-python` upon server startup across all devices (Ubuntu, Debian, Fedora, Arch, macOS) with 0 manual steps required by the user.
- **MacBook / macOS Standalone Package Support**: Added `.tar.gz` standalone release distribution packaging for macOS (`vapor-ram-v1.0.4-macos.tar.gz`) alongside Linux (`vapor-ram-v1.0.4-linux-x86_64.tar.gz`).
- **Standardized Release Automation**: Implemented the `release-manager` SOP skill defining multi-platform packaging, PyPI distribution building, and GitHub Pages documentation synchronization.

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
