#!/usr/bin/env python3
"""
VaporRAM — Web UI Brand, Aesthetics & Mobile Layout Transformer
Replaces old Colibri branding, updates color palette to Cyber Cyan / Indigo, and adds mobile responsive layout styles.
"""
import os, sys, re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(HERE, "web", "dist")

def fix_js_bundle(js_path):
    print(f"[1/3] Processing JS bundle: {os.path.basename(js_path)}")
    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Exact case & localized pattern replacements
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

    # Case insensitive fallback for remaining colibri text
    content = re.sub(r"colibr[ìi]", "VaporRAM", content, flags=re.IGNORECASE)

    with open(js_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(" -> JS Bundle Branding Updated ✓")

def fix_css_bundle(css_path):
    print(f"[2/3] Processing CSS bundle & Adding Mobile Responsiveness: {os.path.basename(css_path)}")
    with open(css_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Color updates (Green -> Cyber Cyan & Indigo)
    content = content.replace("#4ed6a5", "#06b6d4")
    content = content.replace("#8abfa9", "#818cf8")
    content = content.replace("#052118", "#071927")

    # Mobile & Responsive small-screen CSS enhancements
    responsive_css = """
/* VaporRAM Small Screen & Mobile Layout Enhancements */
@media (max-width: 900px) {
  #root > div {
    flex-direction: column !important;
    height: 100vh !important;
    overflow-y: auto !important;
  }
  aside, div[class*="sidebar"] {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 100% !important;
    height: auto !important;
    max-height: 40vh !important;
    overflow-y: auto !important;
    border-right: none !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
  }
  main, div[class*="main"], div[class*="chat"] {
    flex: 1 !important;
    width: 100% !important;
    min-width: 100% !important;
  }
  div[class*="header"] {
    flex-wrap: wrap !important;
    gap: 0.5rem !important;
  }
}
"""
    if "VaporRAM Small Screen" not in content:
        content += "\n" + responsive_css

    with open(css_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(" -> CSS Bundle Responsive Styles Updated ✓")

def fix_index_html(html_path):
    print(f"[3/3] Processing index.html: {os.path.basename(html_path)}")
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("<title>VaporRAM Dashboard</title>", "<title>VaporRAM — Gemma 4 E4B-it Dashboard</title>")
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(" -> HTML Title Updated ✓")

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
