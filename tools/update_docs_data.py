#!/usr/bin/env python3
"""
VaporRAM Docs Data Generator
Generates docs/assets/changelog.json and docs/assets/releases.json dynamically from CHANGELOG.md and git tags.
"""

import os
import re
import json

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_ASSETS = os.path.join(HERE, "docs", "assets")
CHANGELOG_PATH = os.path.join(HERE, "CHANGELOG.md")

os.makedirs(DOCS_ASSETS, exist_ok=True)

def parse_changelog():
    if not os.path.exists(CHANGELOG_PATH):
        return []

    with open(CHANGELOG_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by version headers: ## [v1.0.X] - YYYY-MM-DD
    version_blocks = re.split(r'\n(?=##\s+\[v)', content)
    entries = []

    for block in version_blocks:
        block = block.strip()
        match = re.match(r'##\s+\[(v[^\]]+)\]\s*-\s*(\d{4}-\d{2}-\d{2})', block)
        if not match:
            continue

        version = match.group(1)
        date = match.group(2)
        is_stable = "alpha" not in version and "beta" not in version

        # Extract subsections (### 🚀 Highlights, etc.)
        subsections = []
        sub_blocks = re.split(r'\n(?=###\s+)', block)
        body_text = sub_blocks[0]

        for sb in sub_blocks[1:]:
            sb_match = re.match(r'###\s+([^\n]+)', sb)
            if sb_match:
                section_title = sb_match.group(1).strip()
                # Extract bullet points
                bullets = [line.strip().lstrip('-').strip() for line in sb.split('\n') if line.strip().startswith('-')]
                subsections.append({
                    "title": section_title,
                    "bullets": bullets
                })

        entries.append({
            "version": version,
            "date": date,
            "channel": "stable" if is_stable else ("alpha" if "alpha" in version else "beta"),
            "is_stable": is_stable,
            "subsections": subsections,
            "raw": block
        })

    return entries

def build_releases_data(changelog_entries):
    releases = []
    for entry in changelog_entries:
        ver = entry["version"]
        clean_ver = ver.lstrip('v')
        channel = entry["channel"]
        is_stable = entry["is_stable"]

        summary = ""
        if entry["subsections"]:
            summary = entry["subsections"][0]["bullets"][0] if entry["subsections"][0]["bullets"] else ""

        releases.append({
            "version": ver,
            "clean_version": clean_ver,
            "date": entry["date"],
            "channel": channel,
            "channel_label": "Stable Release" if is_stable else ("Alpha Preview" if channel == "alpha" else "Beta Release"),
            "is_stable": is_stable,
            "summary": summary,
            "subsections": entry["subsections"],
            "downloads": {
                "linux": {
                    "os": "Linux x86_64",
                    "arch": "AVX2 + FMA3 SIMD",
                    "filename": f"vapor-ram-{ver}-linux-x86_64.tar.gz",
                    "url": f"https://github.com/sudsarkar13/vapor-ram/releases/download/{ver}/vapor-ram-{ver}-linux-x86_64.tar.gz",
                    "size": "135.5 MB"
                },
                "macos": {
                    "os": "macOS Apple Silicon",
                    "arch": "ARM NEON + AMX",
                    "filename": f"vapor-ram-{ver}-macos.tar.gz",
                    "url": f"https://github.com/sudsarkar13/vapor-ram/releases/download/{ver}/vapor-ram-{ver}-macos.tar.gz",
                    "size": "135.5 MB"
                }
            }
        })

    return releases

def main():
    print("=== VaporRAM Docs Data Generator ===")
    changelog_entries = parse_changelog()
    releases_entries = build_releases_data(changelog_entries)

    changelog_file = os.path.join(DOCS_ASSETS, "changelog.json")
    releases_file = os.path.join(DOCS_ASSETS, "releases.json")

    with open(changelog_file, "w", encoding="utf-8") as f:
        json.dump(changelog_entries, f, indent=2)

    with open(releases_file, "w", encoding="utf-8") as f:
        json.dump(releases_entries, f, indent=2)

    print(f" -> Generated {changelog_file} ({len(changelog_entries)} entries)")
    print(f" -> Generated {releases_file} ({len(releases_entries)} entries)")

if __name__ == "__main__":
    main()
