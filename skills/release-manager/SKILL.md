---
name: release-manager
description: Standard operating procedure for version bumping, Web UI asset transformation, C engine compilation, standalone Linux packaging, GitHub Release tagging with binary attachments, PyPI distribution publishing, and GitHub Pages documentation synchronization.
---

# Release Manager Skill

This skill defines the mandatory, step-by-step workflow for cutting new version releases for **VaporRAM** across Git, GitHub Releases, PyPI packages, and GitHub Pages.

---

## 📋 Standard Operating Procedure (SOP)

### 1. Version Bumping Across All Manifests
Update the target version string `X.Y.Z` consistently in all 10 target files:

- `version.py`: `__version__ = "X.Y.Z"`
- `setup.py`: `version="X.Y.Z"`
- `pyproject.toml`: `version = "X.Y.Z"`
- `openai_server.py`: `VERSION = "X.Y.Z"`
- `vapor`: `💨 VaporRAM vX.Y.Z`
- `c/vapor_engine.c`: `VaporRAM Engine vX.Y.Z`
- `tools/package_release.py`: `VERSION = "X.Y.Z"`
- `tools/download_model.py`: `User-Agent: VaporRAM/X.Y.Z`
- `tools/fix_webui.py`: UI Header badge `💨 VaporRAM vX.Y.Z`
- `CHANGELOG.md`: Prepend new section `## [vX.Y.Z] - YYYY-MM-DD` detailing highlights and fixes.

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

### 4. Build Standalone Linux Release Tarball
Package standalone binary archive attachment for Ubuntu / Debian / Fedora / Arch distributions:

```bash
python3 tools/package_release.py
# Output generated: vapor-ram-vX.Y.Z-linux-x86_64.tar.gz
```

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

### 6. Git Commit, Tagging, and GitHub Release Publishing
Commit modified source files, create annotated release tag, push to main, and publish GitHub Release with standalone Linux archive attached:

```bash
# 1. Stage and commit source files
git add version.py setup.py pyproject.toml openai_server.py vapor c/vapor_engine.c tools/package_release.py tools/fix_webui.py web/ CHANGELOG.md
git commit -m "Release vX.Y.Z: <Highlights Summary>"

# 2. Push main branch
TOKEN=$(gh auth token)
git push https://sudsarkar13:${TOKEN}@github.com/sudsarkar13/vapor-ram.git main

# 3. Create & push tag
git tag -a vX.Y.Z -m "vX.Y.Z Release — Standalone Linux Build"
git push https://sudsarkar13:${TOKEN}@github.com/sudsarkar13/vapor-ram.git vX.Y.Z

# 4. Create GitHub release with standalone Linux tarball attached
gh release create vX.Y.Z vapor-ram-vX.Y.Z-linux-x86_64.tar.gz \
  --title "vX.Y.Z — <Title>" \
  --notes-file CHANGELOG.md \
  --repo sudsarkar13/vapor-ram
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

### 8. PyPI Package Upload Command
Upload distributions to PyPI using `twine`:

```bash
python3 -m pip install --upgrade twine
python3 -m twine upload dist/vapor_ram-X.Y.Z*
```
