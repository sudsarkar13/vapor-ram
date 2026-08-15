#!/usr/bin/env python3
"""
VaporRAM — Version Consistency Checker

The release SOP requires the same version string in every manifest. This verifies
that mechanically, so a half-applied bump fails CI instead of shipping.

Usage:
    python3 tools/check_version.py            # verify all manifests agree
    python3 tools/check_version.py --set X.Y.Z  # rewrite every manifest to X.Y.Z
    python3 tools/check_version.py --expect X.Y.Z  # additionally assert an exact value
"""
import os, re, sys, argparse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (relative path, regex with a single capture group for the version, template for --set)
TARGETS = [
    ("vapor_ram/version.py",   r'__version__\s*=\s*"([^"]+)"',                 '__version__ = "{v}"'),
    ("setup.py",                r'version\s*=\s*"([^"]+)"',                     'version="{v}"'),
    ("pyproject.toml",          r'^version\s*=\s*"([^"]+)"',                    'version = "{v}"'),
    ("vapor_ram/openai_server.py", r'^VERSION\s*=\s*"([^"]+)"',                    'VERSION = "{v}"'),
    
    ("c/vapor_engine.c",        r'VaporRAM Engine v([0-9][^\s\\]*)',            'VaporRAM Engine v{v}'),
    ("tools/package_release.py", r'^VERSION\s*=\s*"([^"]+)"',                   'VERSION = "{v}"'),
    ("tools/download_model.py", r'USER_AGENT\s*=\s*"VaporRAM/([^\s"]+)',        'USER_AGENT = "VaporRAM/{v}'),
]

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$")


def channel_for(version):
    """Map a version string to its release channel."""
    if "-alpha." in version:
        return "alpha"
    if "-beta." in version:
        return "beta"
    if "-rc." in version:
        return "rc"
    return "stable"


def read_versions():
    found = {}
    missing = []
    for rel, pattern, _tmpl in TARGETS:
        path = os.path.join(HERE, rel)
        if not os.path.exists(path):
            missing.append(rel)
            continue
        text = open(path, encoding="utf-8").read()
        match = re.search(pattern, text, re.M)
        if not match:
            missing.append(f"{rel} (no version pattern matched)")
            continue
        found[rel] = match.group(1)
    return found, missing


def set_versions(new_version):
    changed = []
    for rel, pattern, template in TARGETS:
        path = os.path.join(HERE, rel)
        if not os.path.exists(path):
            print(f"  skip   {rel} (missing)")
            continue
        text = open(path, encoding="utf-8").read()
        match = re.search(pattern, text, re.M)
        if not match:
            print(f"  \033[33mskip\033[0m   {rel} (pattern not found)")
            continue
        if match.group(1) == new_version:
            print(f"  ok     {rel}")
            continue
        replacement = template.format(v=new_version)
        text = text[: match.start()] + replacement + text[match.end():]
        open(path, "w", encoding="utf-8").write(text)
        changed.append(rel)
        print(f"  \033[32mbump\033[0m   {rel}: {match.group(1)} -> {new_version}")
    return changed


def main():
    parser = argparse.ArgumentParser(description="Check or set VaporRAM version strings")
    parser.add_argument("--set", dest="new_version", help="Rewrite all manifests to this version")
    parser.add_argument("--expect", help="Assert the resolved version equals this exact string")
    args = parser.parse_args()

    if args.new_version:
        if not SEMVER.match(args.new_version):
            print(f"\033[31m[FAIL]\033[0m '{args.new_version}' is not a valid version "
                  f"(expected X.Y.Z, X.Y.Z-alpha.N, X.Y.Z-beta.N or X.Y.Z-rc.N)")
            return 1
        print(f"=== Setting version to {args.new_version} "
              f"({channel_for(args.new_version)} channel) ===")
        set_versions(args.new_version)
        print("\nDone. Review the diff, update CHANGELOG.md, then commit.")
        return 0

    print("=== VaporRAM Version Consistency ===")
    found, missing = read_versions()

    for rel, version in found.items():
        print(f"  {version:<22} {rel}")

    if missing:
        print("\n\033[31m[FAIL]\033[0m Could not read a version from:")
        for m in missing:
            print(f"  - {m}")
        return 1

    distinct = set(found.values())
    if len(distinct) != 1:
        print(f"\n\033[31m[FAIL]\033[0m Version mismatch across manifests: {sorted(distinct)}")
        print("  Fix with: python3 tools/check_version.py --set <version>")
        return 1

    version = distinct.pop()
    if not SEMVER.match(version):
        print(f"\n\033[31m[FAIL]\033[0m '{version}' is not a valid semantic version")
        return 1

    if args.expect and version != args.expect:
        print(f"\n\033[31m[FAIL]\033[0m Expected {args.expect} but manifests declare {version}")
        return 1

    print(f"\n\033[32m[OK]\033[0m All manifests agree: v{version} "
          f"({channel_for(version)} channel)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
