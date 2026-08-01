#!/usr/bin/env python3
"""
VaporRAM — Web UI Brand, Aesthetics, Model Detection, Server Lifecycle & Screen Optimization Transformer
Replaces old Colibri branding, updates color palette, adds Stop/Restart server buttons, and optimizes screen layout.
"""
import os, sys, re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(HERE, "web", "dist")

MODEL_DETECTION_UI_HTML = """
<!-- VaporRAM Model Detection & Connection Bar -->
<div id="vapor-model-bar" style="position:sticky;top:0;left:0;width:100%;background:#071018;border-bottom:1px solid rgba(6,182,212,0.2);padding:0.4rem 1rem;font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#f9fafb;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;z-index:9999;box-sizing:border-box;">
  <div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;">
    <span style="font-weight:700;font-size:0.85rem;color:#06b6d4;letter-spacing:0.02em;">💨 VaporRAM v1.0.2</span>
    <span id="model-status-badge" style="background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.3);font-size:0.72rem;padding:0.2rem 0.5rem;border-radius:5px;font-weight:600;">● Weights Loaded (google/gemma-4-E4B-it)</span>
    <span id="model-conn-badge" style="background:rgba(99,102,241,0.15);color:#818cf8;border:1px solid rgba(99,102,241,0.3);font-size:0.72rem;padding:0.2rem 0.5rem;border-radius:5px;font-weight:600;">NVMe O_DIRECT GGUF Streaming (RAM Ceiling < 1.5 GB)</span>
  </div>

  <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
    <input id="model-path-input" type="text" value="./models/gemma-4-E4B-it" placeholder="Locate system model path..." style="background:#0d1825;color:#f9fafb;border:1px solid rgba(255,255,255,0.15);padding:0.25rem 0.6rem;border-radius:5px;font-size:0.75rem;width:190px;" />
    <button id="btn-set-path" onclick="window.vaporSetModelPath()" style="background:#06b6d4;color:#000;border:none;padding:0.28rem 0.65rem;border-radius:5px;font-size:0.75rem;font-weight:600;cursor:pointer;">Locate & Load</button>
    <button id="btn-scan" onclick="window.vaporScanModels()" style="background:rgba(255,255,255,0.1);color:#fff;border:1px solid rgba(255,255,255,0.2);padding:0.28rem 0.65rem;border-radius:5px;font-size:0.75rem;cursor:pointer;">Scan System</button>
    <button id="btn-download" onclick="window.vaporDownloadModel()" style="background:linear-gradient(135deg,#06b6d4,#6366f1);color:#fff;border:none;padding:0.28rem 0.75rem;border-radius:5px;font-size:0.75rem;font-weight:600;cursor:pointer;">Download GGUF</button>
    <button id="btn-restart-server" onclick="window.vaporRestartServer()" style="background:rgba(234,179,8,0.15);color:#eab308;border:1px solid rgba(234,179,8,0.3);padding:0.28rem 0.65rem;border-radius:5px;font-size:0.75rem;font-weight:600;cursor:pointer;">🔄 Restart</button>
    <button id="btn-stop-server" onclick="window.vaporStopServer()" style="background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.3);padding:0.28rem 0.65rem;border-radius:5px;font-size:0.75rem;font-weight:600;cursor:pointer;">🛑 Stop Engine</button>
  </div>
</div>

<!-- Realtime Installation & Loading Progress Bar -->
<div id="vapor-progress-container" style="display:none;background:#0b1522;border-bottom:1px solid rgba(6,182,212,0.3);padding:0.4rem 1rem;font-family:-apple-system,BlinkMacSystemFont,sans-serif;">
  <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.75rem;margin-bottom:0.25rem;">
    <span id="vapor-progress-msg" style="color:#06b6d4;font-weight:600;">Initializing installation...</span>
    <span id="vapor-progress-pct" style="color:#f9fafb;font-weight:700;font-family:monospace;">0%</span>
  </div>
  <div style="width:100%;height:6px;background:#152436;border-radius:3px;overflow:hidden;">
    <div id="vapor-progress-fill" style="height:100%;width:0%;background:linear-gradient(90deg,#06b6d4,#6366f1);transition:width 0.4s ease;"></div>
  </div>
</div>

<script>
window.vaporProgressHandled = false;

window.vaporCheckStatus = async function() {
  try {
    const res = await fetch('/v1/health');
    const data = await res.json();
    const statusBadge = document.getElementById('model-status-badge');
    const connBadge = document.getElementById('model-conn-badge');
    const pathInput = document.getElementById('model-path-input');

    if (data.model_path && pathInput) pathInput.value = data.model_path;
    if (data.model_available) {
      if (statusBadge) {
        statusBadge.style.background = 'rgba(16,185,129,0.15)';
        statusBadge.style.color = '#10b981';
        statusBadge.innerText = '● GGUF Loaded (google/gemma-4-E4B-it)';
      }
      if (connBadge) connBadge.innerText = 'NVMe O_DIRECT GGUF Streaming (RAM Ceiling < 1.5 GB)';
    } else {
      if (statusBadge) {
        statusBadge.style.background = 'rgba(245,158,11,0.15)';
        statusBadge.style.color = '#f59e0b';
        statusBadge.innerText = '⚠️ GGUF Weights Required (Click Download GGUF)';
      }
      if (connBadge) connBadge.innerText = 'Simulation Mode (< 1.5 GB RAM)';
    }
  } catch (e) {}
};

window.vaporPollProgress = async function() {
  try {
    const res = await fetch('/v1/system/progress');
    const data = await res.json();
    const progress = data.download_progress;
    const container = document.getElementById('vapor-progress-container');
    const msg = document.getElementById('vapor-progress-msg');
    const pct = document.getElementById('vapor-progress-pct');
    const fill = document.getElementById('vapor-progress-fill');

    if (progress && progress.status === 'downloading') {
      window.vaporProgressHandled = false;
      if (container) container.style.display = 'block';
      if (msg) msg.innerText = progress.message;
      if (pct) pct.innerText = progress.percent + '%';
      if (fill) fill.style.width = progress.percent + '%';
    } else if (progress && progress.status === 'completed') {
      if (!window.vaporProgressHandled) {
        window.vaporProgressHandled = true;
        if (container) container.style.display = 'block';
        if (msg) msg.innerText = progress.message;
        if (pct) pct.innerText = '100%';
        if (fill) fill.style.width = '100%';
        setTimeout(() => {
          if (container) container.style.display = 'none';
          window.vaporCheckStatus();
        }, 3000);
      }
    } else {
      if (window.vaporProgressHandled && container) {
        container.style.display = 'none';
      }
    }
  } catch (e) {}
};

window.vaporRestartServer = async function() {
  if (confirm('Restart VaporRAM server in-place in the terminal?')) {
    try {
      await fetch('/v1/system/restart', {method: 'POST'});
      alert('Restarting server process... Please wait 2 seconds.');
      setTimeout(() => { window.location.reload(); }, 2000);
    } catch (e) { alert('Restart failed: ' + e); }
  }
};

window.vaporStopServer = async function() {
  if (confirm('Stop VaporRAM server process cleanly?')) {
    try {
      await fetch('/v1/system/stop', {method: 'POST'});
      alert('VaporRAM server stopped cleanly.');
    } catch (e) { alert('Server stopped.'); }
  }
};

window.vaporSetModelPath = async function() {
  const inputEl = document.getElementById('model-path-input');
  const path = inputEl ? inputEl.value : '';
  try {
    const res = await fetch('/v1/system/set_model_path', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({path: path})
    });
    const data = await res.json();
    if (data.error) alert(data.error);
    else {
      alert(data.message);
      window.vaporCheckStatus();
    }
  } catch (e) { alert('Failed to update model path: ' + e); }
};

window.vaporScanModels = async function() {
  try {
    const res = await fetch('/v1/system/scan');
    const data = await res.json();
    let msg = "System Model Scan Results:\\n\\n";
    if (data.scanned_models) {
      data.scanned_models.forEach(function(m) {
        msg += "- " + m.path + " : " + (m.available ? "AVAILABLE" : "Not Found") + "\\n";
      });
    }
    alert(msg);
  } catch (e) { alert('Failed to scan system: ' + e); }
};

window.vaporDownloadModel = async function() {
  if (confirm('Start downloading official google/gemma-4-E4B_q4_0-it.gguf model from Hugging Face?')) {
    window.vaporProgressHandled = false;
    try {
      const res = await fetch('/v1/system/download_model', {method: 'POST'});
      const data = await res.json();
      alert(data.message);
      window.vaporPollProgress();
    } catch (e) { alert('Download failed to start: ' + e); }
  }
};

window.addEventListener('DOMContentLoaded', () => {
  window.vaporCheckStatus();
  setInterval(window.vaporCheckStatus, 5000);
  setInterval(window.vaporPollProgress, 800);
});
</script>
""".replace("\\n", "\\\\n")

def fix_js_bundle(js_path):
    print(f"[1/3] Processing JS bundle: {os.path.basename(js_path)}")
    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()

    replacements = {
        r"COLIBRÌ ENGINE": "VaporRAM ENGINE",
        r"MOTORE COLIBRÌ": "MOTORE VaporRAM",
        r"COLIBRÌ 引擎": "VaporRAM 引擎",
        r"colibrì": "VaporRAM",
        r"Colibrì": "VaporRAM",
        r"COLIBRI": "VaporRAM",
        r"colibri": "VaporRAM",
        r"Colibri": "VaporRAM",
        r"Ask the giant\. Keep the machine yours\.": "Zero Memory Pressure. Stream Gemma 4 E4B-it under 1.5 GB RAM.",
        r"向巨人提问。": "零内存压力。在 1.5 GB RAM limit 下运行 Gemma 4 8B。",
        r"Connect to a local VaporRAM server and stream responses directly from your hardware\. Nothing leaves the endpoint you choose\.": "Connect to a local VaporRAM engine and stream google/gemma-4-E4B-it directly under 1.5 GB RAM.",
        r"EXPERT CORTEX": "LAYER STREAMER — RAM CEILING < 1.5 GB",
        r"Explain how expert routing works": "Explain how sequential layer streaming works",
        r"Write a small C benchmark": "Write an AVX2 SIMD matrix-vector benchmark",
        r"Compare RAM and VRAM caching": "Analyze RAM ceiling usage under 1.5 GB",
        r"LOCAL GIANT, TINY FOOTPRINT": "ULTRA-LOW RAM SSD STREAMING ENGINE",
        r"#4ed6a5": "#06b6d4",
        r"#8abfa9": "#818cf8",
        r"#052118": "#071927",
    }

    for old_pat, new_str in replacements.items():
        content = re.sub(old_pat, new_str, content)

    content = re.sub(r"colibr[ìi]", "VaporRAM", content, flags=re.IGNORECASE)

    with open(js_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(" -> JS Bundle Branding Updated ✓")

def fix_css_bundle(css_path):
    print(f"[2/3] Processing CSS bundle & Adding Laptop Screen Layout Optimization: {os.path.basename(css_path)}")
    with open(css_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("#4ed6a5", "#06b6d4")
    content = content.replace("#8abfa9", "#818cf8")
    content = content.replace("#052118", "#071927")

    responsive_css = """
/* VaporRAM Screen Layout Optimization for Laptops & Desktops */
html, body {
  height: 100vh !important;
  max-height: 100vh !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
  box-sizing: border-box !important;
}

#root {
  height: calc(100vh - 38px) !important;
  max-height: calc(100vh - 38px) !important;
  display: flex !important;
  flex-direction: column !important;
  overflow: hidden !important;
}

#root > div {
  height: 100% !important;
  max-height: 100% !important;
  overflow: hidden !important;
}

aside, div[class*="sidebar"] {
  height: 100% !important;
  overflow-y: auto !important;
}

main, div[class*="main"], div[class*="chat"] {
  height: 100% !important;
  max-height: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  overflow-y: hidden !important;
}

div[class*="messages"], div[class*="chat-messages"] {
  flex: 1 !important;
  overflow-y: auto !important;
}

@media (max-width: 1024px) {
  #root > div {
    flex-direction: row !important;
  }
  aside, div[class*="sidebar"] {
    width: 220px !important;
    min-width: 220px !important;
  }
}

@media (max-width: 768px) {
  #root > div {
    flex-direction: column !important;
  }
  aside, div[class*="sidebar"] {
    width: 100% !important;
    min-width: 100% !important;
    max-height: 35vh !important;
  }
}
"""
    if "VaporRAM Screen Layout Optimization" not in content:
        content += "\n" + responsive_css

    with open(css_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(" -> CSS Bundle Layout Styles Updated ✓")

def fix_index_html(html_path):
    print(f"[3/3] Processing index.html: {os.path.basename(html_path)}")
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("<title>VaporRAM Dashboard</title>", "<title>VaporRAM — Gemma 4 E4B-it Dashboard</title>")
    
    if "vapor-model-bar" not in content:
        content = content.replace("<body>", "<body>\n" + MODEL_DETECTION_UI_HTML)
    else:
        content = re.sub(r"<!-- VaporRAM Model Detection & Connection Bar -->.*?</script>", MODEL_DETECTION_UI_HTML, content, flags=re.DOTALL)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(" -> HTML Title & Model Progress Bar UI Updated ✓")

def run():
    print("=== VaporRAM Web UI Transformer ===")
    assets_dir = os.path.join(DIST_DIR, "assets")
    for f in os.listdir(assets_dir):
        if f.endswith(".js"):
            fix_js_bundle(os.path.join(assets_dir, f))
        elif f.endswith(".css"):
            fix_css_bundle(os.path.join(assets_dir, f))
    fix_index_html(os.path.join(DIST_DIR, "index.html"))
    print("===================================")

if __name__ == "__main__":
    run()
