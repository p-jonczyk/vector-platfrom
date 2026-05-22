# Raster → Wektor

A local, browser-accessible platform for converting raster images (PNG, JPG, BMP, TIFF, WEBP) into clean vector graphics (SVG, EPS). Optimised for plotter and vinyl-cutter workflows, but suitable for any raster-to-vector task.

---

## Features

- **Full browser UI** — upload, configure, preview, and save without touching the terminal
- **9 built-in presets** — Plotter/Cutter, Logo, Icon, Silhouette, Sketch, High-Fidelity, Compact, Stencil, Dark-on-Light
- **All parameters exposed** — every conversion setting is available with inline help (hover `?`)
- **Live SVG preview** — hover to zoom 4.4×, click for fullscreen; same for the input image
- **Staging workflow** — files are held in a temp folder until you explicitly save them
- **Native folder picker** — OS-level dialog for choosing the output directory
- **CLI mode** — `raster2vector.py` can also be used directly from the command line
- **Automatic cleanup** — staging directory is wiped on startup and on quit

---

## Requirements

- Python 3.14+
- Windows (uses tkinter for the native folder-picker dialog)

---

## Setup

```bash
# Create and activate the virtual environment
py -3.14 -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Running the web UI

```bash
venv\Scripts\activate
python app.py
```

Then open **http://localhost:5000** in your browser.

Click **Zakończ** in the top-right corner to shut the server down and clean up all temporary files.

---

## Workflow

1. **Upload** a PNG / JPG / BMP / TIFF / WEBP image (max 100 MB)
2. **Choose a preset** or tweak parameters manually
3. Click **Konwertuj** — the result appears as a live SVG preview
4. **Hover** the thumbnail to zoom in; **click** for fullscreen
5. Choose an output folder and click **Zapisz pliki**

If a file with the same name already exists in the target folder, the saved file gets an `_1`, `_2`, … suffix automatically.

---

## Presets

| Preset | Best for |
|---|---|
| **Ploter / Cutter** | Vinyl cutting, laser cutting, stickers — transparent background, clean cut paths |
| **Logo** | Monochrome logos and line art |
| **Ikona** | UI icons, pictograms — sharp corners preserved |
| **Sylwetka** | Silhouettes, posters — heavy smoothing |
| **Szkic** | Hand-drawn scans — polygon output, every wobble kept |
| **Wysoka jakość** | Offset print, large-format ads — 4× upscale, high coordinate precision |
| **Kompaktowy** | Inline SVG, web graphics — minimal file size |
| **Szablon** | Painting stencils, laser cutting — no interior holes |
| **Ciemne na jasnym** | Black logo on white background, stamps, text scans |

---

## Configuration parameters

All parameters are available in the UI and as CLI flags. The defaults are designed for general-purpose use; presets override only the relevant subset.

| Parameter | Default | Description |
|---|---|---|
| `channel` | `luma` | How colour is converted to greyscale (`luma`, `red`, `green`, `blue`, `max`, `min`) |
| `invert` | `false` | Treat darker regions as foreground (black-on-white input) |
| `threshold_mode` | `otsu` | Binarisation method: `otsu` (auto), `manual`, `adaptive_mean`, `adaptive_gaussian` |
| `threshold_value` | `128` | Manual threshold level (0–255) |
| `adaptive_block_size` | `31` | Window size for adaptive thresholding (odd, ≥ 3) |
| `adaptive_C` | `5` | Constant subtracted from local mean in adaptive thresholding |
| `upscale` | `2` | Integer upscale factor before tracing (1–4) |
| `upscale_method` | `cubic` | Interpolation: `nearest`, `linear`, `cubic`, `lanczos` |
| `pre_blur_sigma` | `1.2` | Gaussian blur σ before thresholding (0 = off) |
| `morph_open` | `0` | Erosion → dilation kernel (removes specks, 0 = off) |
| `morph_close` | `0` | Dilation → erosion kernel (fills gaps, 0 = off) |
| `dilate` | `0` | Extra dilation iterations (thickens foreground) |
| `erode` | `0` | Extra erosion iterations (thins foreground) |
| `min_area` | `4.0` | Minimum contour area in px² — smaller shapes are discarded |
| `include_holes` | `true` | Cut out interior holes (letter counters, even-odd fill) |
| `contour_sigma` | `2.0` | Periodic Gaussian smoothing on contour points |
| `resample_spacing` | `4.0` | Arc-length between resampled contour points (px) |
| `output_mode` | `bezier` | `bezier` = smooth Bézier curves, `polygon` = straight segments |
| `detect_corners` | `false` | Preserve sharp corners instead of rounding them |
| `corner_angle_deg` | `60.0` | Angle threshold (°) for corner detection |
| `foreground` | `#ffffff` | Shape fill colour (`#rrggbb`) |
| `background` | `#000000` | Document background colour, or `none` for transparent |
| `coord_precision` | `2` | Decimal places in output coordinates (0 = integer) |
| `formats` | `svg, eps` | Output formats (`svg`, `eps`, or both) |

---

## CLI usage

`raster2vector.py` can be used standalone, without the web app:

```bash
# Basic conversion (uses defaults)
python raster2vector.py logo.png

# Apply a preset
python raster2vector.py logo.png --preset ploter

# Override individual parameters
python raster2vector.py logo.png --upscale 4 --foreground "#000000" --background none

# Load settings from a JSON file
python raster2vector.py logo.png --config my_settings.json

# Print the effective config (useful for reproducing a result)
python raster2vector.py logo.png --preset logo --upscale 4 --dump-config

# List available presets
python raster2vector.py --list-presets
```

### Config JSON format

```json
{
  "channel": "luma",
  "upscale": 2,
  "foreground": "#000000",
  "background": null,
  "formats": ["svg", "eps"]
}
```

---

## Project structure

```
vector-platfrom/
├── app.py                  Flask web application
├── raster2vector.py        Core conversion engine + CLI
├── requirements.txt        Python dependencies
├── templates/
│   └── index.html          Single-page browser UI
└── staging/                Temporary conversion output (auto-cleaned, not committed)
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `opencv-python` | Image loading, resizing, thresholding, morphology, contour finding |
| `numpy` | Array operations throughout the pipeline |
| `scipy` | Periodic Gaussian smoothing of contour coordinates |
| `flask` | Local web server and REST API |

---

## License

MIT — see [LICENSE](LICENSE).
