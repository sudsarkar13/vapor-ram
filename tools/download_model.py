#!/usr/bin/env python3
"""
VaporRAM — GGUF Hugging Face Model Downloader for google/gemma-4-E4B-it
Downloads official GGUF quantized model file directly from Hugging Face:
- Repo: unsloth/gemma-4-E4B-it-GGUF
- File: gemma-4-E4B-it-Q4_K_M.gguf (~2.5 GB - 4.5 GB)

Features multi-stage download logic:
1. Python huggingface_hub / hf CLI (if installed)
2. Resumable curl -L -C - execution with progress callbacks
3. Pure Python urllib chunked downloader with HTTP Range header resume support
"""
import os, sys, json, time, subprocess, urllib.request

REPO_ID = "unsloth/gemma-4-E4B-it-GGUF"
FILENAME = "gemma-4-E4B-it-Q4_K_M.gguf"

PRIMARY_GGUF_URL = f"https://huggingface.co/{REPO_ID}/resolve/main/{FILENAME}"
FALLBACK_GGUF_URL = "https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/resolve/main/gemma-4-E4B_q4_0-it.gguf"
CONFIG_URL = "https://huggingface.co/google/gemma-4-E4B-it/resolve/main/config.json"

TARGET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "gemma-4-E4B-it")
TARGET_GGUF_PATH = os.path.join(TARGET_DIR, FILENAME)
TARGET_CONFIG_PATH = os.path.join(TARGET_DIR, "config.json")

def download_with_curl(url, target_path, progress_callback=None):
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    cmd = ["curl", "-L", "-C", "-", "--retry", "5", "--retry-delay", "3", "-o", target_path, url]
    
    if progress_callback:
        progress_callback(10, f"Starting resilient curl download from {url}...")

    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    
    while proc.poll() is None:
        if os.path.exists(target_path):
            size_bytes = os.path.getsize(target_path)
            size_mb = size_bytes / (1024 * 1024)
            if progress_callback:
                progress_callback(min(95, int(size_mb / 35.0)), f"Downloading GGUF Model via curl: {size_mb:.1f} MB downloaded...")
        time.sleep(1.5)

    proc.wait()
    if proc.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 1000000:
        return True
    return False

def download_with_python_resumable(url, target_path, progress_callback=None):
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    temp_path = target_path + ".tmp"
    existing_bytes = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0

    headers = {"User-Agent": "VaporRAM/1.0.2 GGUF Downloader"}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"

    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            total_size = int(resp.headers.get("Content-Length", 0)) + existing_bytes
            downloaded = existing_bytes
            chunk_size = 2048 * 1024 # 2MB chunks
            start_time = time.time()
            
            mode = "ab" if existing_bytes > 0 else "wb"
            with open(temp_path, mode) as out_f:
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
                        speed_mb = (mb_dn - (existing_bytes / (1024 * 1024))) / elapsed if elapsed > 0 else 0.0
                        msg = f"Downloading GGUF Model: {mb_dn:.1f}/{mb_tot:.1f} MB ({speed_mb:.1f} MB/s)"
                        progress_callback(pct, msg)
                        
        os.rename(temp_path, target_path)
        return True
    except Exception as e:
        print(f"[!] Resumable download error: {e}")
        return False

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

    # Check if GGUF model already exists
    if os.path.exists(TARGET_GGUF_PATH) and os.path.getsize(TARGET_GGUF_PATH) > 100000000:
        if progress_callback:
            progress_callback(100, f"GGUF model ready at {TARGET_GGUF_PATH}")
        return

    # 2. Try huggingface_hub Python library if installed
    try:
        from huggingface_hub import hf_hub_download
        if progress_callback:
            progress_callback(10, f"Downloading {FILENAME} via huggingface_hub...")
        hf_hub_download(repo_id=REPO_ID, filename=FILENAME, local_dir=TARGET_DIR)
        if os.path.exists(TARGET_GGUF_PATH):
            if progress_callback:
                progress_callback(100, f"Installation Complete! GGUF model ready at {TARGET_GGUF_PATH}")
            return
    except Exception:
        pass

    # 3. Try resilient curl download
    if shutil_which("curl"):
        success = download_with_curl(PRIMARY_GGUF_URL, TARGET_GGUF_PATH, progress_callback)
        if success:
            if progress_callback:
                progress_callback(100, f"Installation Complete! GGUF model ready at {TARGET_GGUF_PATH}")
            return

    # 4. Fallback to Python resumable HTTP downloader
    success = download_with_python_resumable(PRIMARY_GGUF_URL, TARGET_GGUF_PATH, progress_callback)
    if not success:
        download_with_python_resumable(FALLBACK_GGUF_URL, TARGET_GGUF_PATH, progress_callback)

    if progress_callback:
        progress_callback(100, f"Installation Complete! GGUF model ready at {TARGET_GGUF_PATH}")

def shutil_which(cmd):
    import shutil
    return shutil.which(cmd) is not None

if __name__ == "__main__":
    def log_cb(p, m):
        print(f"[{p}%] {m}")
    run_full_download(log_cb)
