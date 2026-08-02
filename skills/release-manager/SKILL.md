---
name: release-manager
description: Standard operating procedure for version bumping, Web UI asset transformation, C engine compilation, binary staging, version-specific release notes generation (version diff comparison & bug fix summary), clean release channel tagging (Stable/Beta/Alpha), GitHub Release publishing, PyPI distribution via virtualenv twine, and GitHub Pages synchronization. ONLY activate this skill when the user explicitly requests or initiates a new version release or version bump.
---

# Release Manager Skill

> **IMPORTANT ACTIVATION RULE**: This skill MUST ONLY be activated when the maintainer explicitly requests or initiates a new version release, release update, or version bump from their side. Do NOT auto-trigger this skill for minor edits or routine bug fixes.

This skill defines the mandatory, step-by-step workflow for cutting new version releases for **VaporRAM** across Git, GitHub Releases, PyPI packages, and GitHub Pages.

---

## 📌 Release Naming & Versioning Rules

### 1. Release Channel Categorization
Every version release MUST be categorized into one of three official channels:
- **Stable Release**: `vX.Y.Z — Stable Release` (Default production release)
- **Beta Release**: `vX.Y.Z-beta.N — Beta Release` (Testing release with feature-complete additions)
- **Alpha Release**: `vX.Y.Z-alpha.N — Alpha Release` (Early preview release)

> **Do NOT** add custom verbose titles like `v1.0.4 Release — Standalone OS Builds`. Keep titles clean, standardized, and professional.

### 2. Version-Specific Release Notes (NO Full Historical Changelog)
When publishing a GitHub Release, **DO NOT** attach the entire `CHANGELOG.md` file. The GitHub Release notes MUST be **strictly limited to the delta between the Previous Version and the New Version**.

Every release note MUST contain:
1. **Comparison Header**: `What's Changed from v<PREVIOUS> to v<NEW>`
2. **Release Channel**: `Channel: Stable` (or `Beta` / `Alpha`)
3. **Fixed Bugs & Resolved Issues**: Exact bulleted list of bugs fixed in this update.
4. **New Features & Enhancements**: Exact bulleted list of features/improvements introduced.

---

## 📋 Standard Operating Procedure (SOP)

### 1. Version Bumping Across All Manifests
Update the target version string `X.Y.Z` (or `X.Y.Z-beta.N`) consistently in all target manifest files:

- `version.py`: `__version__ = "X.Y.Z"`
- `setup.py`: `version="X.Y.Z"`
- `pyproject.toml`: `version = "X.Y.Z"`
- `openai_server.py`: `VERSION = "X.Y.Z"`
- `vapor`: `💨 VaporRAM vX.Y.Z`
- `c/vapor_engine.c`: `VaporRAM Engine vX.Y.Z`
- `tools/package_release.py`: `VERSION = "X.Y.Z"`
- `tools/download_model.py`: `User-Agent: VaporRAM/X.Y.Z`
- `tools/fix_webui.py`: UI Header badge `💨 VaporRAM vX.Y.Z`
- `CHANGELOG.md`: Prepend new section `## [vX.Y.Z] - YYYY-MM-DD`.

---

### 2. Web UI Transformation & C Binary Re-compilation
Re-build static Web UI build assets and recompile C SIMD layer streaming binary:

```bash
# 1. Update static Web UI HTML/CSS layout and version badge
python3 tools/fix_webui.py

# 2. Recompile C binary engine with OpenMP + AVX2 acceleration
gcc -O3 -mavx2 -mfma -fopenmp c/vapor_engine.c c/streaming_io.c c/kv_cache.c -o c/vapor_engine -lm
```

---

### 3. Integration Testing
Run full integration test suite to verify 100% test passage across C binary execution, multi-endpoint HTTP server, static assets, and memory budgets:

```bash
python3 tests/test_engine.py
```

---

### 4. Build OS Distribution Tarballs & Dynamic Documentation Data
Run the release packager script to compile binaries, update dynamic docs datasets (`changelog.json` & `releases.json`), and build standalone distribution packages:

```bash
python3 tools/update_docs_data.py
python3 tools/package_release.py
```
# Output generated:
# - vapor-ram-vX.Y.Z-linux-x86_64.tar.gz
# - vapor-ram-vX.Y.Z-macos.tar.gz
```
*Note: OS distribution tarballs (`vapor-ram-v*.tar.gz`) are attached directly to the GitHub Release via `gh release create`. They are ignored by Git and must NOT be committed to the repository.*

---

### 5. Build PyPI Source & Wheel Distributions
Generate PyPI package distributions:

```bash
python3 setup.py sdist bdist_wheel
# Output generated in ./dist/:
# - dist/vapor_ram-X.Y.Z.tar.gz
# - dist/vapor_ram-X.Y.Z-py3-none-any.whl
```

---

### 6. Generate Version-Specific Notes & Publish GitHub Release
1. Write version-specific notes comparing Previous Version vs New Version into `RELEASE_NOTES.md`:

```markdown
# vX.Y.Z — Stable Release

## 🔄 What's Changed (v<PREVIOUS> ➔ v<NEW>)
- **Channel**: Stable Release

### 🐛 Fixed Bugs & Issues
- Bullet list of exact bugs fixed in this release

### ✨ New Features & Enhancements
- Bullet list of new features added in this release
```

2. Commit modified source files **AND the compiled `c/vapor_engine` binary**:

```bash
# Stage source files AND compiled c/vapor_engine binary
git add version.py setup.py pyproject.toml openai_server.py vapor c/vapor_engine c/vapor_engine.c tools/package_release.py tools/fix_webui.py web/ CHANGELOG.md .gitignore
git commit -m "Release vX.Y.Z: Stable Release — <Highlights Summary>"

# Push main branch
TOKEN=$(gh auth token)
git push https://sudsarkar13:${TOKEN}@github.com/sudsarkar13/vapor-ram.git main

# Create & push tag
git tag -a vX.Y.Z -m "vX.Y.Z — Stable Release"
git push https://sudsarkar13:${TOKEN}@github.com/sudsarkar13/vapor-ram.git vX.Y.Z

# Publish GitHub Release with version-specific notes ONLY (NOT full CHANGELOG.md)
# For Stable Release:
gh release create vX.Y.Z vapor-ram-vX.Y.Z-linux-x86_64.tar.gz vapor-ram-vX.Y.Z-macos.tar.gz \
  --title "vX.Y.Z — Stable Release" \
  --notes-file RELEASE_NOTES.md \
  --repo sudsarkar13/vapor-ram

# For Alpha / Beta Pre-Releases, add --prerelease flag:
# gh release create vX.Y.Z-beta.1 ... --prerelease --title "vX.Y.Z-beta.1 — Beta Release" ...
```

---

### 7. GitHub Pages Documentation Synchronization
Update [docs/index.html](file:///home/sudeepta/Ubuntu-Owner/GitHub/vapor-ram/docs/index.html) to keep GitHub Pages documentation (`https://sudsarkar13.github.io/vapor-ram/`) in sync:

- Brand Version Tag: `vX.Y.Z`
- Standalone Tarball Button URL: `https://github.com/sudsarkar13/vapor-ram/releases/tag/vX.Y.Z`
- Footer Release Link: `vX.Y.Z Release`

Commit and push `docs/index.html` to trigger GitHub Pages deployment:

```bash
git add docs/index.html
git commit -m "Update GitHub Pages site docs/index.html to vX.Y.Z"
git push https://sudsarkar13:${TOKEN}@github.com/sudsarkar13/vapor-ram.git main
```

---

### 8. PyPI Package Upload Command (via Virtual Environment)
Upload built distributions (`.whl` and `.tar.gz`) to PyPI by activating the Python virtual environment (`~/.venv`) and using `twine`:

```bash
# 1. Activate virtual environment containing twine
source ~/.venv/bin/activate

# 2. Upload wheel and source distributions to PyPI
twine upload dist/vapor_ram-X.Y.Z*
```
