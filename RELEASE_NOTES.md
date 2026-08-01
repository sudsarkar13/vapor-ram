# v1.0.7-alpha.1 — Alpha Release

## 🔄 What's Changed (v1.0.6 ➔ v1.0.7-alpha.1)
- **Channel**: Alpha Release (Preview Channel)
- **Target Model**: `google/gemma-4-E4B-it` (GGUF, RAM Ceiling < 1.5 GB)

### ✨ New Features & Enhancements
- **Next.js + shadcn/ui Dashboard**: Rebuilt the Web UI using Next.js, TypeScript, Tailwind CSS, and shadcn/ui featuring real-time SSE streaming, `react-markdown` code highlighting, memory telemetry gauge, and zero end-user Node.js dependencies.
- **Dynamic Context Adjustment (`/system/context`)**: Added runtime endpoint to dynamically scale context length (`n_ctx`) between 512 and 8,192 tokens with automatic KV cache re-allocation.
- **Concurrent Slot Guarding & Connection Resilience**: Added slot locks (`_slot_begin` / `_slot_end`) and graceful `BrokenPipeError` / `ConnectionResetError` handling when client SSE streams disconnect.

### 🐛 Fixed Bugs & Issues
- **SSE Stream Abort Handling**: Server cleanly halts token iteration when the browser disconnects or navigates away.
- **Config Persistence**: Fixed settings synchronization in `config.py` for persistent user options.
