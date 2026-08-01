#!/usr/bin/env python3
"""
VaporRAM — Distribution Release Packager
Compiles binaries, packages assets, and builds a standalone distribution tarball.
"""
import os, sys, shutil, tarfile, subprocess

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "1.0.2"
DIST_NAME = f"vapor-ram-v{VERSION}-linux-x86_64"
OUTPUT_TAR = f"{DIST_NAME}.tar.gz"

def create_release():
    print(f"=== VaporRAM Release Packager v{VERSION} ===")
    print("1. Compiling C SIMD Engine Binaries...")
    subprocess.check_call(["make", "-C", os.path.join(HERE, "c")])

    build_dir = os.path.join(HERE, "dist_build", DIST_NAME)
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir)

    print("2. Copying Linux build binaries, scripts, LICENSE, and Web UI assets...")
    # Copy root files
    for f in ["vapor", "doctor.py", "resource_plan.py", "openai_server.py", "config.py", "version.py", "README.md", "LICENSE"]:
        src = os.path.join(HERE, f)
        if os.path.exists(src):
            shutil.copy(src, build_dir)

    # Copy directories (including compiled C binary in c/)
    shutil.copytree(os.path.join(HERE, "c"), os.path.join(build_dir, "c"))
    shutil.copytree(os.path.join(HERE, "web"), os.path.join(build_dir, "web"))
    shutil.copytree(os.path.join(HERE, "tools"), os.path.join(build_dir, "tools"))
    shutil.copytree(os.path.join(HERE, "presets"), os.path.join(build_dir, "presets"))

    print("3. Creating release tarball archive...")
    tar_path = os.path.join(HERE, OUTPUT_TAR)
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(build_dir, arcname=DIST_NAME)

    shutil.rmtree(os.path.join(HERE, "dist_build"))

    print(f"\n[Success] Distribution package created: {OUTPUT_TAR}")
    print(f"[File Size] {os.path.getsize(tar_path) / (1024*1024):.2f} MB")
    return tar_path

if __name__ == "__main__":
    create_release()
