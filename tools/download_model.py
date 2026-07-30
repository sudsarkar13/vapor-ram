#!/usr/bin/env python3
"""
VaporRAM — Automated Model Downloader
Downloads google/gemma-4-E4B-it model weights from Hugging Face into ./models/
"""
import os, sys, subprocess

def download_model(repo_id="google/gemma-4-E4B-it", dest_dir="./models/gemma-4-E4B-it"):
    print(f"=== VaporRAM Model Downloader ===")
    print(f" Repository : {repo_id}")
    print(f" Destination: {dest_dir}")
    print("---------------------------------")
    
    os.makedirs(dest_dir, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download
        print(f"Downloading model files from Hugging Face Hub...")
        snapshot_download(repo_id=repo_id, local_dir=dest_dir, local_dir_use_symlinks=False)
        print(f"\n[Success] Model downloaded successfully to {dest_dir}")
        return True
    except ImportError:
        print("[Notice] 'huggingface_hub' not installed. Falling back to git lfs...")
        try:
            subprocess.check_call(["git", "lfs", "install"])
            subprocess.check_call(["git", "clone", f"https://huggingface.co/{repo_id}", dest_dir])
            print(f"\n[Success] Model cloned successfully to {dest_dir}")
            return True
        except Exception as e:
            print(f"[Error] Download failed: {e}")
            print("Install huggingface_hub:  pip install huggingface_hub")
            return False

if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "google/gemma-4-E4B-it"
    dest = sys.argv[2] if len(sys.argv) > 2 else "./models/gemma-4-E4B-it"
    download_model(repo, dest)
