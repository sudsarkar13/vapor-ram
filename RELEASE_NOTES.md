# v1.0.7-alpha.4 — Alpha Release

## 🔄 What's Changed (v1.0.7-alpha.3 ➔ v1.0.7-alpha.4)

- **Channel**: Alpha Release (Preview Channel)
- **Target Model**: `google/gemma-4-E4B-it` (GGUF)

This release repairs the installable package, reconnects the dashboard to the
engine, and replaces reported metrics that were hardcoded rather than measured.

### ⚠️ Read this first

Two long-standing claims were wrong and are now corrected in the documentation:

- **`pip install vapor-ram` never worked.** The console entry point pointed at a
  module that does not exist, so the installed `vapor` command failed instantly
  with `ModuleNotFoundError`. The wheel also shipped without the dashboard,
  presets or engine binary. Both are fixed and verified from a clean install.
- **The 1.5 GB RAM ceiling is not yet achieved.** Generation runs through
  llama.cpp, which memory-maps the full GGUF; measured RSS is around **6 GB**,
  not the **142.3 MB** previously advertised. That figure was a hardcoded
  constant in the API response, never a measurement. The C layer streamer is
  built but not yet wired into the token path — that remains the primary work.

### 🐛 Fixed Bugs & Issues

- **Installed package was unusable**: broken `vapor:main` entry point; wheel
  contained 12 files and no runtime assets.
- **Dashboard read fields the server never sent**: the Doctor tab rendered the
  literal string `undefined`, and the download-status check compared against a
  value that could never match, so it never fired.
- **Download progress was invisible**: percentage, transferred bytes and rate
  were all served but nothing rendered them.
- **Context window was reported dishonestly**: values up to 131072 were accepted
  and persisted while generation silently clamped to 16384.
- **Model directory was clobbered**: every settings save rewrote `model_dir`, so
  changing the context window overwrote the active model path. The saved value
  was also never restored on restart.
- **Streaming was a replay animation**: the full response was generated before
  the first byte was sent, then re-chunked with a fixed delay.
- **Server was single-threaded**: any generation froze the whole dashboard.
- **Chat had no memory**: only the last message reached the model.
- **Presets did nothing**: the persona name was sent as a system message and
  discarded server-side; `temperature` and `top_p` were never applied.
- **`--api-key` was inert**: the key was never assigned to the request handler.
- **Committed dashboard was incomplete**: an over-broad `dist/` ignore rule
  excluded the JavaScript chunks, so a clean checkout shipped a blank UI.
- **Release tarballs bundled `node_modules`** (~700 MB); now 1.2 MB.

### ✨ New Features & Enhancements

- **Real telemetry**: measured process RSS and per-request host RAM, replacing
  frozen and fabricated constants. Unmeasured values report as unavailable.
- **Model architecture read from `config.json`** instead of three conflicting
  hardcoded sets (42 layers / 2 KV heads / 18 shared for gemma-4-E4B-it).
- **Model lifecycle state** so a multi-second weight load is visible.
- **Download meter** with byte-accurate progress, rate, ETA and resume.
- **New endpoints**: `/v1/presets` and `/v1/doctor`.
- **Model directory picker** driven by the server-side scan.
- **Generation metrics**: tokens/second and time-to-first-token.
- **CLI parity**: `vapor chat` keeps history, streams tokens and applies presets;
  added `vapor --version`.
- **CI/CD**: matrix CI (Linux/macOS × Python 3.9/3.12), version-consistency and
  packaging gates, and a tag-driven release pipeline with automatic
  Stable/Beta/Alpha/RC channel handling and OIDC PyPI publishing.
- **Tests**: expanded from 4 smoke assertions to 47 contract checks.

### 📦 Layout change for contributors

Python modules now live in `vapor_ram/`. Update imports from
`import openai_server` to `from vapor_ram import openai_server`. `./vapor` still
works unchanged from a checkout.
