# Raster → Wektor

A local, browser-accessible platform for converting raster images (PNG, JPG, BMP, TIFF, WEBP) into clean vector graphics (SVG, EPS, PDF, PLT). Optimised for plotter and vinyl-cutter workflows, but suitable for any raster-to-vector task.

**Version 1.1** · see [CHANGELOG.md](CHANGELOG.md) for what's new.

---

## Features

- **Full browser UI** — upload, configure, preview, and save without touching the terminal
- **9 built-in presets** — Plotter/Cutter, Logo, Icon, Silhouette, Sketch, High-Fidelity, Compact, Stencil, Dark-on-Light
- **All parameters exposed** — every conversion setting is available with inline help (hover `?`)
- **4 output formats** — SVG, EPS, PDF and PLT (HPGL), e.g. for SignMaster and other cutter software
- **Physical size (DPI)** — every format gets the same real-world size in millimetres
- **Live SVG preview** — hover to zoom 4.4×, click for fullscreen; same for the input image
- **Helpful hints** — warns when the background would be traced or cut as a frame, with a one-click fix
- **Transparent images** — transparent PNG, WEBP and TIFF files are handled automatically
- **Paste from clipboard** — Ctrl+V loads a copied image
- **Works offline** — styling, icons and scripts are bundled with the app
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

1. **Upload** a PNG / JPG / BMP / TIFF / WEBP image (max 100 MB), or paste one with Ctrl+V. If a hint appears under the preview, click its button
2. **Choose a preset** or tweak parameters manually
3. **Tick the output formats** and set **Rozdzielczość (DPI)** — the line under the field shows the final size in mm
4. Click **Konwertuj** — the result appears as a live SVG preview
5. **Hover** the thumbnail to zoom in; **click** for fullscreen
6. Choose an output folder and click **Zapisz pliki**

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

Presets change the tracing settings only. The chosen output formats and DPI stay as you set them.

---

## Output formats

| Format | Best for |
|---|---|
| **SVG** | Inkscape, browsers, most cutter software |
| **EPS** | Older cutter drivers, Adobe Illustrator, CorelDRAW |
| **PDF** | SignMaster V5 and any PDF-capable software; page size is the physical output size |
| **PLT** | HPGL cut file for plotters and vinyl cutters; cut paths only (no fill, no background), curves flattened to segments within 0.05 mm, holes cut before outer contours |

All formats share the same physical size, set by `dpi`: size in mm = pixels ÷ dpi × 25.4. For example, a 1200 px wide image is 101.6 mm wide at 300 dpi and 317.5 mm at the default 96 dpi. DPI only scales the result; it does not change the traced shape. The web UI fills in DPI automatically when the image file stores its resolution.

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
| `dpi` | `96` | Source image resolution (pixels per inch); sets the physical output size |
| `formats` | `svg, eps` | Output formats, any combination of `svg`, `eps`, `pdf`, `plt` |

---

## CLI usage

`raster2vector.py` can be used standalone, without the web app:

```bash
# Basic conversion (uses defaults)
python raster2vector.py logo.png

# Apply a preset (the "Ploter / Cutter" preset is available in the web UI only)
python raster2vector.py logo.png --preset dark_on_light

# Override individual parameters
python raster2vector.py logo.png --upscale 4 --foreground "#000000" --background none

# PDF + PLT for cutter software, scanned at 300 dpi (sets the physical size)
python raster2vector.py logo.png --formats pdf plt --dpi 300

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
  "background": "none",
  "dpi": 96,
  "formats": ["svg", "eps", "pdf", "plt"]
}
```

---

## Project structure

```
vector-platfrom/
├── app.py                  Flask web application
├── raster2vector.py        Core conversion engine + CLI
├── requirements.txt        Python dependencies
├── run.bat                 Windows launcher (update, set up, start)
├── example_config.json     Example settings file for the CLI (--config)
├── templates/
│   └── index.html          Single-page browser UI
├── static/vendor/          Bootstrap and Bootstrap Icons, bundled for offline use
├── CHANGELOG.md            Version history
├── README.md
├── LICENSE
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
| `pillow` | Reads the resolution (DPI) stored in image files |

---

## Quick start

This project can be started manually or by using the included `run.bat` file on Windows.

The `run.bat` script is a simple launcher that automatically updates the project with `git pull`, creates the Python virtual environment if it does not exist, installs or updates dependencies from `requirements.txt`, and starts the local web application with `python app.py`.

After it starts, open:

```text
http://localhost:5000
```


## License

MIT — see [LICENSE](LICENSE).
