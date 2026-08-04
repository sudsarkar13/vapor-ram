# v1.0.7-alpha.3 — Alpha Release

## 🔄 What's Changed (v1.0.7-alpha.2 ➔ v1.0.7-alpha.3)
- **Channel**: Alpha Release (Preview Channel)
- **Target Model**: `google/gemma-4-E4B-it` (GGUF, RAM Ceiling Target: 1.5 GB – 32.0 GB)

### ✨ New Features & Enhancements
- **PyPI Verified Details & Metadata Standardization**: Added standard project repository URLs (`Repository`, `Bug Tracker`, `Changelog`) and OSI license classifiers in `pyproject.toml` and `setup.py`.
- **OIDC PyPI Publishing Pipeline**: Introduced automated GitHub Actions workflow (`.github/workflows/publish-pypi.yml`) supporting OIDC Trusted Publisher authentication and PEP 740 cryptographic provenance attestations.
- **Cross-Platform Test & Packaging Safety**: Made C engine build step and unit test execution fault-tolerant on non-Linux platforms (e.g., macOS host environments).
