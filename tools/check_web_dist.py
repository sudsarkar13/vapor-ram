#!/usr/bin/env python3
"""
VaporRAM — Dashboard Asset Integrity Check

`web/dist` is committed and served directly by openai_server.py, so a partial
commit ships an index.html that references JavaScript nobody can load — the
dashboard renders blank with no server-side error.

This verifies that every asset index.html references actually exists on disk.

It deliberately does NOT compare against a fresh `next build`: Turbopack chunk
filenames are content-addressed per build and are not reproducible run-to-run,
so an equality check would fail even when nothing changed.

Usage:
    python3 tools/check_web_dist.py
"""
import os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(HERE, "web", "dist")
INDEX = os.path.join(DIST, "index.html")

# src="/_next/...", href="/_next/...", and preload targets.
ASSET_RE = re.compile(r'(?:src|href)="(/_next/[^"?#]+)"')


def main():
    if not os.path.isdir(DIST):
        print(f"\033[31m[FAIL]\033[0m {DIST} does not exist.")
        print("  Build it with: yarn --cwd web build")
        return 1

    if not os.path.exists(INDEX):
        print(f"\033[31m[FAIL]\033[0m web/dist/index.html is missing.")
        return 1

    html = open(INDEX, encoding="utf-8").read()
    if "VaporRAM" not in html:
        print("\033[31m[FAIL]\033[0m index.html does not contain VaporRAM branding.")
        return 1

    referenced = sorted(set(ASSET_RE.findall(html)))
    if not referenced:
        print("\033[31m[FAIL]\033[0m index.html references no /_next assets — "
              "this is not a valid Next.js static export.")
        return 1

    missing = []
    for ref in referenced:
        path = os.path.join(DIST, ref.lstrip("/"))
        if not os.path.exists(path):
            missing.append(ref)

    js = [r for r in referenced if r.endswith(".js")]
    css = [r for r in referenced if r.endswith(".css")]

    print(f"=== Dashboard Asset Integrity ===")
    print(f"  index.html references : {len(referenced)} assets "
          f"({len(js)} js, {len(css)} css)")
    print(f"  files present in dist : {sum(1 for _, _, f in os.walk(DIST) for _ in f)}")

    if missing:
        print(f"\n\033[31m[FAIL]\033[0m {len(missing)} referenced asset(s) missing from web/dist:")
        for m in missing[:20]:
            print(f"    - {m}")
        print("\n  The committed dashboard is incomplete. Rebuild and commit all of web/dist:")
        print("    yarn --cwd web build && git add web/dist")
        return 1

    if not js:
        print("\n\033[31m[FAIL]\033[0m No JavaScript chunks referenced — "
              "the dashboard would render blank.")
        return 1

    print(f"\n\033[32m[OK]\033[0m All {len(referenced)} referenced assets are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
