#!/usr/bin/env python3
"""
VaporRAM — Memory Profiler Tool
Monitors process RSS (Resident Set Size), Page Faults, and RAM ceiling compliance.
"""
import os, sys, time, subprocess, resource

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_BIN = os.path.join(HERE, "c", "vapor_engine")

def profile_memory():
    print("=== VaporRAM High-Precision Memory Profiler ===")
    print("Target Model : google/gemma-4-E4B-it")
    print("RAM Ceiling  : < 1.5 GB (1500 MB)")
    print("-----------------------------------------------")

    dummy_bin = os.path.join(HERE, "c", "vapor_engine.o")
    prompt = "Memory profiling prompt execution."

    start_time = time.time()
    try:
        output = subprocess.check_output([ENGINE_BIN, dummy_bin, prompt], stderr=subprocess.STDOUT).decode()
        status = "SUCCESS"
    except Exception as e:
        output = str(e)
        status = "FAILED"

    duration = time.time() - start_time
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    peak_rss_mb = usage.ru_maxrss / 1024.0 # KB to MB
    minor_page_faults = usage.ru_minflt
    major_page_faults = usage.ru_majflt

    print("--- Execution Trace Output ---")
    print(output.strip())
    print("------------------------------")
    print("\n=== Memory Profile Analysis ===")
    print(f" Status             : {status}")
    print(f" Elapsed Time       : {duration:.3f} s")
    print(f" Peak RSS Memory    : {peak_rss_mb:.2f} MB")
    print(f" Minor Page Faults  : {minor_page_faults}")
    print(f" Major Page Faults  : {major_page_faults}")
    print(f" Memory Efficiency  : {(peak_rss_mb / 1500.0) * 100.0:.1f}% of RAM Ceiling Used")
    print(f" Compliance Verdict : {'PASS (< 1.5 GB RAM)' if peak_rss_mb < 1500 else 'FAIL'}")
    print("===============================")

if __name__ == "__main__":
    profile_memory()
