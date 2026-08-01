# v1.0.6 — Stable Release

## 🔄 What's Changed (v1.0.5 ➔ v1.0.6)
- **Channel**: Stable Release
- **Target Model**: `google/gemma-4-E4B-it` (GGUF, RAM Ceiling < 1.5 GB)

### 🐛 Fixed Bugs & Issues
- **Linux Terminal Signal Shutdown (`CTRL+C`)**: Resolved socket polling and signal handling in `openai_server.py` so pressing `CTRL+C` in Linux terminals cleanly force-terminates the server process without hanging.
- **Output Token Truncation**: Expanded token generation ceiling from `2048` to **`8192` tokens** (`max_tokens=8192` & `n_ctx=8192`) to prevent long answers from cutting off midway.
- **`vapor run` GGUF Model Execution**: Fixed `./vapor run` and `./vapor chat` commands to route directly through the GGUF model execution engine.

### ✨ New Features & Enhancements
- **Cross-Platform `doctor` Inspector**: Added native macOS MacBook hardware identification (detecting Apple Silicon M1 through M5 series & A18 Pro) and ARM NEON / AMX matrix extension detection alongside Linux AVX2 SIMD checks.
- **Release Manager SOP Refactor**: Standardized semantic release channel naming (`Stable`, `Beta`, `Alpha`), version-specific release notes comparison, git tracking of compiled C binaries, and PyPI virtual environment upload commands.
