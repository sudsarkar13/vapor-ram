#!/usr/bin/env python3
"""
VaporRAM — Distribution Release Packager
Compiles binaries, packages assets, and builds standalone distribution packages:
- Linux: vapor-ram-v{VERSION}-linux-x86_64.tar.gz
- macOS / MacBook: vapor-ram-v{VERSION}-macos.tar.gz
"""
import os, sys, shutil, tarfile, subprocess, platform

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "1.0.6"

def create_release():
    print(f"=== VaporRAM Release Packager v{VERSION} ===")
    print("1. Compiling C SIMD Engine Binaries...")
    try:
        subprocess.check_call(["make", "-C", os.path.join(HERE, "c")])
    except Exception as e:
        print(f"[!] Warning: C compilation failed ({e}), packaging Python and Web UI runtime...")

    dist_base = f"vapor-ram-v{VERSION}"
    
    # 2. Package Linux tar.gz
    linux_dist_name = f"{dist_base}-linux-x86_64"
    build_dir_linux = os.path.join(HERE, "dist_build", linux_dist_name)
    if os.path.exists(build_dir_linux):
        shutil.rmtree(build_dir_linux)
    os.makedirs(build_dir_linux)

    # 3. Package macOS tar.gz
    macos_dist_name = f"{dist_base}-macos"
    build_dir_macos = os.path.join(HERE, "dist_build", macos_dist_name)
    if os.path.exists(build_dir_macos):
        shutil.rmtree(build_dir_macos)
    os.makedirs(build_dir_macos)

    print("2. Copying scripts, LICENSE, presets, and Web UI assets...")
    root_files = ["vapor", "doctor.py", "resource_plan.py", "openai_server.py", "config.py", "version.py", "README.md", "LICENSE"]
    for f in root_files:
        src = os.path.join(HERE, f)
        if os.path.exists(src):
            shutil.copy(src, build_dir_linux)
            shutil.copy(src, build_dir_macos)

    for dir_name in ["c", "web", "tools", "presets"]:
        src_dir = os.path.join(HERE, dir_name)
        if os.path.exists(src_dir):
            shutil.copytree(src_dir, os.path.join(build_dir_linux, dir_name))
            shutil.copytree(src_dir, os.path.join(build_dir_macos, dir_name))

    print("3. Creating release tarball archives for Linux and macOS (.tar.gz)...")
    
    # Build Linux tarball
    linux_tar_path = os.path.join(HERE, f"{linux_dist_name}.tar.gz")
    with tarfile.open(linux_tar_path, "w:gz") as tar:
        tar.add(build_dir_linux, arcname=linux_dist_name)
    print(f" -> Created Linux release: {linux_tar_path} ({os.path.getsize(linux_tar_path)/(1024*1024):.2f} MB)")

    # Build macOS tarball (.tar.gz)
    macos_tar_path = os.path.join(HERE, f"{macos_dist_name}.tar.gz")
    with tarfile.open(macos_tar_path, "w:gz") as tar:
        tar.add(build_dir_macos, arcname=macos_dist_name)
    print(f" -> Created macOS MacBook release: {macos_tar_path} ({os.path.getsize(macos_tar_path)/(1024*1024):.2f} MB)")

    # Cleanup temp build dir
    shutil.rmtree(os.path.join(HERE, "dist_build"))

    print(f"\n[Success] Distribution packages created for Linux and macOS (.tar.gz)!")
    return [linux_tar_path, macos_tar_path]

if __name__ == "__main__":
    create_release()
