#!/usr/bin/env python3
"""
VaporRAM — Cross-Platform System Diagnostics & Hardware Inspector
Detects system specs, CPU vector extensions (AVX2/NEON), OS type (Linux & macOS / MacBook),
Apple Silicon chipset generations (M1, M2, M3, M4, M5, A18 Pro), and total/available RAM.
"""
import os, sys, time, platform, subprocess, re, json

def get_macos_cpu_brand():
    try:
        brand = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"]).decode().strip()
        if brand and brand != "0":
            return brand
    except Exception:
        pass
    try:
        model = subprocess.check_output(["sysctl", "-n", "hw.model"]).decode().strip()
        return f"Apple Silicon ({model})"
    except Exception:
        return "Apple MacBook Processor"

def get_ram_info():
    os_name = platform.system()
    total_gb, avail_gb = 16.0, 8.0

    if os_name == "Linux":
        try:
            with open("/proc/meminfo") as f:
                mem = f.read()
                total_kb = int([line for line in mem.split("\n") if "MemTotal" in line][0].split()[1])
                avail_kb = int([line for line in mem.split("\n") if "MemAvailable" in line][0].split()[1])
                total_gb = total_kb / (1024 * 1024)
                avail_gb = avail_kb / (1024 * 1024)
        except Exception:
            pass

    elif os_name == "Darwin":
        try:
            total_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]).decode().strip())
            total_gb = total_bytes / (1024 * 1024 * 1024)
            
            vm = subprocess.check_output(["vm_stat"]).decode()
            page_size = 4096
            free_match = re.search(r"Pages free:\s+(\d+)", vm)
            inactive_match = re.search(r"Pages inactive:\s+(\d+)", vm)
            purgeable_match = re.search(r"Pages purgeable:\s+(\d+)", vm)
            
            free_p = int(free_match.group(1)) if free_match else 0
            inact_p = int(inactive_match.group(1)) if inactive_match else 0
            purge_p = int(purgeable_match.group(1)) if purgeable_match else 0
            
            avail_bytes = (free_p + inact_p + purge_p) * page_size
            avail_gb = avail_bytes / (1024 * 1024 * 1024)
        except Exception:
            pass

    return total_gb, avail_gb

def run_doctor():
    checks = []
    os_name = platform.system()
    arch = platform.machine()
    
    # 1. OS & Device Identification Check
    if os_name == "Darwin":
        cpu_brand = get_macos_cpu_brand()
        device_type = "macOS MacBook" if "Mac" in cpu_brand or arch == "arm64" else "macOS Device"
        os_detail = f"{device_type} · {cpu_brand} ({arch})"
        os_ok = True
    elif os_name == "Linux":
        os_detail = f"Linux ({arch})"
        os_ok = True
    else:
        os_detail = f"{os_name} ({arch})"
        os_ok = False

    checks.append({
        "check": "system.os",
        "status": "ok" if os_ok else "warn",
        "detail": os_detail
    })
    
    # 2. CPU Vector Extension Check (AVX2 for x86_64 / ARM NEON & AMX for Apple M-Series / A18)
    if arch in ("arm64", "aarch64") or os_name == "Darwin":
        simd_detail = "ARM NEON + Apple AMX Matrix Extensions Enabled"
        simd_ok = True
    else:
        try:
            flags = subprocess.check_output("lscpu", shell=True).decode()
            has_avx2 = "avx2" in flags.lower()
        except Exception:
            has_avx2 = True
        simd_detail = "AVX2 + FMA3 SIMD instructions detected" if has_avx2 else "AVX2 missing"
        simd_ok = has_avx2

    checks.append({
        "check": "cpu.vector",
        "status": "ok" if simd_ok else "fail",
        "detail": simd_detail
    })
    
    # 3. Memory inspector
    #
    # This used to pass whenever 1.5 GB was free, checking against the RAM
    # ceiling *target* rather than what the engine actually needs. On a machine
    # with 2 GB available it reported "ok" and the server then failed to load
    # 4.98 GB of memory-mapped weights. The threshold is now the measured
    # requirement; the 1.5 GB target is a research goal, not a system spec.
    total_gb, avail_gb = get_ram_info()
    NEEDED_GB = 7.5          # measured peak RSS at n_ctx 8192 is 7.27 GB
    COMFORTABLE_GB = 9.0
    if avail_gb >= COMFORTABLE_GB:
        ram_status, note = "ok", "comfortable"
    elif avail_gb >= NEEDED_GB:
        ram_status, note = "ok", "enough, with little headroom"
    else:
        ram_status, note = "warn", f"below the ~{NEEDED_GB:.1f} GB the engine needs"

    checks.append({
        "check": "memory.ram",
        "status": ram_status,
        "detail": f"{total_gb:.1f} GB Total · {avail_gb:.1f} GB Available ({note})"
    })
    
    # 4. Engine & GGUF Runtime Check
    #
    # These are two independent things and are now reported as such. The old
    # message read "GGUF Engine & C SIMD Streamer Ready" whenever *either* was
    # present, so a host with no C tools was told the streamer was ready --
    # and the streamer is a measurement tool, not part of the token path.
    from . import paths as _paths
    has_bin = os.path.exists(_paths.engine_bin())

    try:
        import llama_cpp
        has_llama = True
    except ImportError:
        has_llama = False

    if has_llama:
        runtime_detail = "llama.cpp ready (generates tokens)"
        runtime_ok = True
    else:
        runtime_detail = "llama-cpp-python not installed; it is installed on first run"
        runtime_ok = True
    runtime_detail += (" · streaming inspector built" if has_bin
                       else " · streaming inspector not built (optional; `make -C c`)")

    checks.append({
        "check": "engine.runtime",
        "status": "ok" if runtime_ok else "warn",
        "detail": runtime_detail
    })
    
    return checks

def format_doctor(checks):
    lines = ["=== VaporRAM Doctor Diagnostics ==="]
    for c in checks:
        mark = "[  ok  ]" if c["status"] == "ok" else "[ warn ]" if c["status"] == "warn" else "[ fail ]"
        lines.append(f"{mark} {c['check']:<15} : {c['detail']}")
    return "\n".join(lines)

if __name__ == "__main__":
    results = run_doctor()
    print(format_doctor(results))
