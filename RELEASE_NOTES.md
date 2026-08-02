# v1.0.7-alpha.2 — Alpha Release

## 🔄 What's Changed (v1.0.7-alpha.1 ➔ v1.0.7-alpha.2)
- **Channel**: Alpha Release (Preview Channel)
- **Target Model**: `google/gemma-4-E4B-it` (GGUF, RAM Ceiling Target: 1.5 GB – 32.0 GB)

### ✨ New Features & Enhancements
- **Customizable RAM Ceiling Target Selector**: Added an interactive selector in the Web UI allowing users to dynamically configure their target RAM ceiling (`1.5 GB`, `2.0 GB`, `3.0 GB`, `4.0 GB`, `8.0 GB`, `16.0 GB`, `32.0 GB`).
- **Host System RAM Auto-Detection**: Integrated hardware inspector (`doctor.py`) into the server to detect Total Installed RAM and Available Free RAM.
- **Persistent Server Settings (`vapor.json`)**: Added `/v1/system/config` GET/POST endpoints and automatic config saving. Settings persist across server restarts (`./vapor serve`, `./vapor web`).
- **Dark Obsidian Select Popover Theme**: Overhauled dropdown select components to maintain consistent dark slate glassmorphic styling.
