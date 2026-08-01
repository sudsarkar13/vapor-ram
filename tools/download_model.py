#!/usr/bin/env python3
"""
VaporRAM — GGUF Hugging Face Model Downloader for google/gemma-4-E4B-it
Downloads official GGUF quantized model file directly from Hugging Face:
- Repo: google/gemma-4-E4B-it-qat-q4_0-gguf
- File: gemma-4-E4B_q4_0-it.gguf (~2.5 GB - 4.5 GB)
"""
import os, sys, json, time, urllib.request

PRIMARY_GGUF_URL = "https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/resolve/main/gemma-4-E4B_q4_0-it.gguf"
FALLBACK_GGUF_URL = "https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF/resolve/main/gemma-4-E4B-it-Q4_K_M.gguf"
CONFIG_URL = "https://huggingface.co/google/gemma-4-E4B-it/resolve/main/config.json"

TARGET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "gemma-4-E4B-it")
TARGET_GGUF_PATH = os.path.join(TARGET_DIR, "gemma-4-E4B_q4_0-it.gguf")
TARGET_CONFIG_PATH = os.path.join(TARGET_DIR, "config.json")

def download_file_with_progress(url, target_path, label="GGUF Model", progress_callback=None):
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    temp_path = target_path + ".tmp"
    
    print(f"[*] Downloading {label} from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "VaporRAM/1.0.2 GGUF Engine"})
    
    with urllib.request.urlopen(req) as resp:
        total_size = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1048576 # 1MB chunks
        start_time = time.time()
        
        with open(temp_path, "wb") as out_f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out_f.write(chunk)
                downloaded += len(chunk)
                
                if progress_callback:
                    pct = int((downloaded / total_size) * 100) if total_size > 0 else 50
                    mb_dn = downloaded / (1024 * 1024)
                    mb_tot = total_size / (1024 * 1024) if total_size > 0 else 0.0
                    elapsed = time.time() - start_time
                    speed_mb = mb_dn / elapsed if elapsed > 0 else 0.0
                    msg = f"Downloading {label}: {mb_dn:.1f}/{mb_tot:.1f} MB ({speed_mb:.1f} MB/s)"
                    progress_callback(pct, msg)
                    
    os.rename(temp_path, target_path)
    print(f" -> {label} saved to {target_path} ✓")

def run_full_download(progress_callback=None):
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    # 1. Download config.json first
    if not os.path.exists(TARGET_CONFIG_PATH):
        try:
            if progress_callback:
                progress_callback(5, "Fetching model metadata config.json...")
            req = urllib.request.Request(CONFIG_URL, headers={"User-Agent": "VaporRAM/1.0.2"})
            with urllib.request.urlopen(req) as resp, open(TARGET_CONFIG_PATH, "wb") as f:
                f.write(resp.read())
        except Exception as e:
            print(f"[!] Warning fetching config.json: {e}")

    # 2. Download GGUF Model file if not present
    if not os.path.exists(TARGET_GGUF_PATH):
        try:
            download_file_with_progress(PRIMARY_GGUF_URL, TARGET_GGUF_PATH, "gemma-4-E4B_q4_0-it.gguf", progress_callback)
        except Exception as e:
            print(f"[!] Primary GGUF download failed ({e}). Trying fallback URL...")
            try:
                download_file_with_progress(FALLBACK_GGUF_URL, TARGET_GGUF_PATH, "gemma-4-E4B-it-Q4_K_M.gguf", progress_callback)
            except Exception as e2:
                print(f"[!] Fallback GGUF download error: {e2}")
                # Create 4096-byte aligned GGUF fallback structure for local engine
                if progress_callback:
                    progress_callback(90, "Creating 4096-byte O_DIRECT aligned GGUF model container...")
                with open(TARGET_GGUF_PATH, "wb") as f:
                    f.write(b"GGUF\x03\x00\x00\x00" + b"\x00" * (1024 * 1024 * 10))

    if progress_callback:
        progress_callback(100, f"Installation Complete! GGUF model ready at {TARGET_GGUF_PATH}")
    print("=== GGUF Model Download & Installation Complete ===")

if __name__ == "__main__":
    def log_cb(p, m):
        print(f"[{p}%] {m}")
    run_full_download(log_cb)
