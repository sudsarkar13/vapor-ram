#!/usr/bin/env python3
"""
VaporRAM — GGUF Hugging Face Model Downloader for google/gemma-4-E4B-it

Downloads the official GGUF quantised weights from Hugging Face:
- Repo: unsloth/gemma-4-E4B-it-GGUF
- File: gemma-4-E4B-it-Q4_K_M.gguf (~2.5 GB - 4.5 GB)

Progress is reported from the real transferred byte count against the real
Content-Length, so the percentage shown in the dashboard reflects the actual
transfer rather than an assumed file size.

Download strategy, in order:
1. Resumable pure-Python urllib downloader (HTTP Range resume, true progress)
2. curl -L -C - with a size-probed progress watcher
3. huggingface_hub (no incremental progress, reported as indeterminate)
"""
import os, sys, json, time, shutil, subprocess, urllib.request, urllib.error

REPO_ID = "unsloth/gemma-4-E4B-it-GGUF"
FILENAME = "gemma-4-E4B-it-Q4_K_M.gguf"

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_DIR = os.path.join(HERE, "models", "gemma-4-E4B-it")

FALLBACK_REPO = "google/gemma-4-E4B-it-qat-q4_0-gguf"
FALLBACK_FILENAME = "gemma-4-E4B_q4_0-it.gguf"
CONFIG_URL = "https://huggingface.co/google/gemma-4-E4B-it/resolve/main/config.json"

USER_AGENT = "VaporRAM/1.0.7 GGUF Downloader"
MIN_VALID_GGUF_BYTES = 100 * 1024 * 1024  # a real quantised Gemma file is >> 100 MB


def resolve_url(repo_id, filename):
    return f"https://huggingface.co/{repo_id}/resolve/main/{filename}"


def _emit(cb, pct, msg, downloaded_mb=0.0, total_mb=0.0, speed_mbps=0.0):
    """Call the progress callback, tolerating older 2-argument callbacks."""
    if not cb:
        return
    try:
        cb(pct, msg, downloaded_mb, total_mb, speed_mbps)
    except TypeError:
        cb(pct, msg)


def probe_remote_size(url):
    """Ask the CDN how big the file is, following redirects. 0 when unknown."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(resp.headers.get("Content-Length", 0))
    except Exception:
        return 0


def download_resumable(url, target_path, progress_callback=None):
    """Chunked download with HTTP Range resume and true byte-accurate progress."""
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    temp_path = target_path + ".part"
    existing = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0

    headers = {"User-Agent": USER_AGENT}
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if existing > 0 and resp.status == 200:
                # Server ignored the Range header — restart cleanly.
                existing = 0
            total = int(resp.headers.get("Content-Length", 0)) + existing
            downloaded = existing
            chunk_size = 4 * 1024 * 1024
            start = time.time()
            last_report = 0.0

            mode = "ab" if existing > 0 else "wb"
            with open(temp_path, mode) as out:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_report >= 0.5:
                        last_report = now
                        elapsed = now - start
                        moved_mb = (downloaded - existing) / (1024 * 1024)
                        speed = moved_mb / elapsed if elapsed > 0 else 0.0
                        dn_mb = downloaded / (1024 * 1024)
                        tot_mb = total / (1024 * 1024) if total else 0.0
                        pct = int(downloaded * 100 / total) if total else 0
                        eta = ((total - downloaded) / (1024 * 1024) / speed) if speed > 0 and total else 0
                        msg = (f"{dn_mb:.0f} / {tot_mb:.0f} MB  ·  {speed:.1f} MB/s"
                               + (f"  ·  ~{int(eta // 60)}m {int(eta % 60)}s left" if eta else ""))
                        _emit(progress_callback, min(pct, 99), msg, dn_mb, tot_mb, speed)

        if os.path.getsize(temp_path) < MIN_VALID_GGUF_BYTES:
            raise IOError(
                f"downloaded file is only {os.path.getsize(temp_path) / 1e6:.1f} MB — "
                f"the remote returned an error page rather than weights")
        os.replace(temp_path, target_path)
        return True
    except Exception as e:
        sys.stderr.write(f"[!] Resumable download error: {e}\n")
        _emit(progress_callback, 0, f"Transfer interrupted: {e}")
        return False


def download_with_curl(url, target_path, progress_callback=None):
    """curl handles flaky CDNs well; we watch the file grow for real progress."""
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    total_bytes = probe_remote_size(url)
    total_mb = total_bytes / (1024 * 1024) if total_bytes else 0.0

    cmd = ["curl", "-L", "-C", "-", "--retry", "5", "--retry-delay", "3",
           "-A", USER_AGENT, "-o", target_path, url]
    _emit(progress_callback, 0, "Starting curl transfer…", 0.0, total_mb, 0.0)

    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    start = time.time()
    while proc.poll() is None:
        if os.path.exists(target_path):
            dn_mb = os.path.getsize(target_path) / (1024 * 1024)
            elapsed = time.time() - start
            speed = dn_mb / elapsed if elapsed > 0 else 0.0
            pct = int(dn_mb * 100 / total_mb) if total_mb else 0
            msg = (f"{dn_mb:.0f} / {total_mb:.0f} MB  ·  {speed:.1f} MB/s" if total_mb
                   else f"{dn_mb:.0f} MB transferred  ·  {speed:.1f} MB/s")
            _emit(progress_callback, min(pct, 99), msg, dn_mb, total_mb, speed)
        time.sleep(1.0)

    proc.wait()
    return (proc.returncode == 0 and os.path.exists(target_path)
            and os.path.getsize(target_path) > MIN_VALID_GGUF_BYTES)


def download_with_hf_hub(repo_id, filename, dest_dir, progress_callback=None):
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return None
    _emit(progress_callback, 0, f"Downloading {filename} via huggingface_hub…")
    try:
        path = hf_hub_download(repo_id=repo_id, filename=filename, local_dir=dest_dir)
        return path if os.path.exists(path) else None
    except Exception as e:
        sys.stderr.write(f"[!] huggingface_hub download failed: {e}\n")
        return None


def fetch_config_json(dest_dir, progress_callback=None):
    target = os.path.join(dest_dir, "config.json")
    if os.path.exists(target):
        return
    try:
        _emit(progress_callback, 0, "Fetching model metadata (config.json)…")
        req = urllib.request.Request(CONFIG_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp, open(target, "wb") as f:
            f.write(resp.read())
    except Exception as e:
        sys.stderr.write(f"[!] Warning fetching config.json: {e}\n")


def run_full_download(progress_callback=None, repo_id=None, dest_dir=None, filename=None):
    """Download GGUF weights. Returns the final .gguf path, or None on failure.

    repo_id / dest_dir / filename override the defaults so the dashboard's
    requested repository and destination are actually honoured.
    """
    repo_id = repo_id or REPO_ID
    dest_dir = os.path.abspath(dest_dir or TARGET_DIR)
    filename = filename or (FILENAME if repo_id == REPO_ID else None)

    os.makedirs(dest_dir, exist_ok=True)
    fetch_config_json(dest_dir, progress_callback)

    # Already have usable weights?
    for existing in sorted(os.listdir(dest_dir)):
        if existing.endswith(".gguf"):
            full = os.path.join(dest_dir, existing)
            if os.path.getsize(full) > MIN_VALID_GGUF_BYTES:
                size_mb = os.path.getsize(full) / (1024 * 1024)
                _emit(progress_callback, 100, f"GGUF model already present: {existing}",
                      size_mb, size_mb, 0.0)
                return full

    attempts = []
    if filename:
        attempts.append((repo_id, filename))
    else:
        attempts.append((repo_id, FILENAME))
    if (repo_id, filename) != (FALLBACK_REPO, FALLBACK_FILENAME):
        attempts.append((FALLBACK_REPO, FALLBACK_FILENAME))

    for attempt_repo, attempt_file in attempts:
        url = resolve_url(attempt_repo, attempt_file)
        target_path = os.path.join(dest_dir, attempt_file)
        _emit(progress_callback, 0, f"Resolving {attempt_repo}/{attempt_file}…")

        if download_resumable(url, target_path, progress_callback):
            size_mb = os.path.getsize(target_path) / (1024 * 1024)
            _emit(progress_callback, 100, f"Download complete: {attempt_file}",
                  size_mb, size_mb, 0.0)
            return target_path

        if shutil.which("curl") and download_with_curl(url, target_path, progress_callback):
            size_mb = os.path.getsize(target_path) / (1024 * 1024)
            _emit(progress_callback, 100, f"Download complete: {attempt_file}",
                  size_mb, size_mb, 0.0)
            return target_path

        hub_path = download_with_hf_hub(attempt_repo, attempt_file, dest_dir, progress_callback)
        if hub_path:
            size_mb = os.path.getsize(hub_path) / (1024 * 1024)
            _emit(progress_callback, 100, f"Download complete: {os.path.basename(hub_path)}",
                  size_mb, size_mb, 0.0)
            return hub_path

    _emit(progress_callback, 0, "All download strategies failed — check network connectivity")
    return None


def download_model(repo, dest):
    """CLI entry point used by `./vapor download`."""
    def log_cb(pct, msg, dn=0.0, tot=0.0, speed=0.0):
        bar_width = 32
        filled = int(bar_width * pct / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        sys.stdout.write(f"\r  [{bar}] {pct:3d}%  {msg[:60]:<60}")
        sys.stdout.flush()

    print(f"=== VaporRAM Model Downloader ===\n  Repo: {repo}\n  Dest: {dest}\n")
    result = run_full_download(log_cb, repo_id=repo if repo != "google/gemma-4-E4B-it" else None,
                               dest_dir=dest)
    print()
    if result:
        print(f"\n[✓] Weights ready at {result}")
        return 0
    print("\n[!] Download failed.")
    return 1


if __name__ == "__main__":
    sys.exit(download_model(REPO_ID, TARGET_DIR))
