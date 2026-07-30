# VaporRAM — Manual Screenshot & Asset Capture Guide 📸

Follow these steps to capture and replace the actual Web UI dashboard screenshot with a high-resolution, transparent PNG image.

---

## Step 1: Launch the Local Web UI Dashboard

Run the following command in your terminal to launch the server and open the browser interface:

```bash
cd ~/Ubuntu-Owner/GitHub/vapor-ram
./vapor web
```

This will start the local HTTP server on `http://localhost:8000/` and open your default web browser.

---

## Step 2: Capture a High-Resolution PNG Screenshot

### Method A: Browser Developer Tools Component Screenshot (Clean & Transparent)
1. In Chrome/Firefox, press `F12` or `Ctrl+Shift+I` to open Developer Tools.
2. Select the main app container element (e.g., `#app` or `.dashboard-container`).
3. Press `Ctrl+Shift+P` (Command Palette in DevTools).
4. Type `Capture node screenshot` and press Enter.
5. Save the resulting clean PNG image.

### Method B: OS Screenshot Tool (Gnome Screenshot / Flameshot)
1. On Ubuntu Linux, press `Shift+PrtScn` or launch **Flameshot** / **Gnome Screenshot**.
2. Select the Web UI interface region.
3. Save the image as a `.png` file.

---

## Step 3: Save and Replace the Asset

1. Move your captured screenshot image into the project assets directory:
   ```bash
   cp /path/to/your/screenshot.png ~/Ubuntu-Owner/GitHub/vapor-ram/docs/assets/dashboard.png
   ```

2. Verify that the asset exists at:
   `~/Ubuntu-Owner/GitHub/vapor-ram/docs/assets/dashboard.png`

3. Commit and push to GitHub:
   ```bash
   cd ~/Ubuntu-Owner/GitHub/vapor-ram
   git add docs/assets/dashboard.png
   git commit -m "Update actual transparent Web UI dashboard screenshot"
   git push origin main
   ```

---

## 🎨 Asset Guidelines

| Asset | Path | Description | Recommended Specs |
| :--- | :--- | :--- | :--- |
| **Logo** | `docs/assets/logo.png` | Main project logo icon | 512x512 PNG / SVG |
| **Favicon** | `docs/assets/favicon.svg` | Browser tab icon | Vector SVG / 32x32 PNG |
| **Dashboard** | `docs/assets/dashboard.png` | Web UI interface screenshot | 1920x1080 Transparent PNG |
