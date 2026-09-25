from __future__ import annotations
from flask import Flask, render_template, request, jsonify, send_file
from pathlib import Path
from dataclasses import asdict
import tempfile
import os
import base64
import uuid
import shutil
import threading

from raster2vector import Config, vectorize, PRESETS

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

DESKTOP = Path.home() / "Desktop"
STAGING = Path(__file__).parent / "staging"

# Clean up any leftover staging files from a previous (possibly crashed) run
if STAGING.exists():
    shutil.rmtree(STAGING, ignore_errors=True)
STAGING.mkdir(exist_ok=True)

PRESET_INFO = {
    "ploter": {
        "label": "Ploter / Cutter",
        "icon": "bi-pen-fill",
        "desc": "Zoptymalizowany pod wycinanie na ploterze. Czarne kształty, przezroczyste tło, czyste kontury cięcia.",
        "example": "Naklejki, folia, wycinanie vinylowe, laser",
        "badge": "Zalecany",
    },
    "logo": {
        "label": "Logo",
        "icon": "bi-award",
        "desc": "Domyślne ustawienia dla czystego, monochromatycznego logo i grafiki liniowej.",
        "example": "Logo firmy, znak firmowy, ikona aplikacji",
    },
    "icon": {
        "label": "Ikona",
        "icon": "bi-grid-3x3",
        "desc": "Mniejszy odstęp próbkowania i wykrywanie narożników — zachowuje ostre krawędzie geometrycznych kształtów.",
        "example": "Ikony UI, piktogramy, symbole",
    },
    "silhouette": {
        "label": "Sylwetka",
        "icon": "bi-person-fill",
        "desc": "Mocne wygładzanie dla efektu plakatu. Duże, miękkie kształty bez drobnych szczegółów.",
        "example": "Sylwetki postaci, plakaty, cienie, clipart",
    },
    "sketch": {
        "label": "Szkic",
        "icon": "bi-pencil",
        "desc": "Wyjście jako wielokąty — zachowuje każde drżenie linii ręcznego rysunku bez zaokrąglania.",
        "example": "Skany rysunków ołówkowych, szkice odręczne",
    },
    "high_fidelity": {
        "label": "Wysoka jakość",
        "icon": "bi-gem",
        "desc": "Czterokrotne skalowanie i wysoka precyzja współrzędnych — maksymalna jakość do druku, duże pliki.",
        "example": "Druk offsetowy, reklamy wielkoformatowe",
    },
    "compact": {
        "label": "Kompaktowy",
        "icon": "bi-file-zip",
        "desc": "Minimalizuje rozmiar pliku przy zachowaniu wektorowej struktury. Uproszczone kształty.",
        "example": "Grafiki webowe, ikony SVG inline w stronach",
    },
    "stencil": {
        "label": "Szablon",
        "icon": "bi-scissors",
        "desc": "Binarny szablon bez otworów wewnętrznych. Czysty, bryłowy kształt bez konturów dziur.",
        "example": "Szablony do malowania, wycinanie laserowe",
    },
    "dark_on_light": {
        "label": "Ciemne na jasnym",
        "icon": "bi-moon-stars-fill",
        "desc": "Dla czarnego lub ciemnego wzoru na jasnym tle — odwraca progi i kolory.",
        "example": "Skany czarnego logo na białym tle, stemple, tekst",
    },
}

EXTRA_PRESETS = {
    "ploter": {
        "foreground": "#000000",
        "background": None,
        "invert": False,
        "upscale": 2,
        "upscale_method": "cubic",
        "pre_blur_sigma": 1.0,
        "threshold_mode": "otsu",
        "contour_sigma": 1.5,
        "resample_spacing": 3.0,
        "morph_open": 2,
        "morph_close": 2,
        "include_holes": True,
        "detect_corners": False,
        "output_mode": "bezier",
        "formats": ("svg", "eps"),
        "coord_precision": 2,
    }
}

ALL_PRESETS = {**EXTRA_PRESETS, **PRESETS}

# session_id → list of staging file paths
_sessions: dict[str, list[str]] = {}


@app.route("/")
def index():
    return render_template(
        "index.html",
        presets=list(ALL_PRESETS.keys()),
        preset_info=PRESET_INFO,
        default=asdict(Config()),
        desktop=str(DESKTOP),
    )


@app.route("/preset/<name>")
def get_preset(name):
    if name not in ALL_PRESETS:
        return jsonify({"error": "Nieznany preset"}), 404
    merged = {**asdict(Config()), **ALL_PRESETS[name]}
    if merged.get("formats"):
        merged["formats"] = list(merged["formats"])
    return jsonify(merged)


@app.route("/pick-dir")
def pick_dir():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        folder = filedialog.askdirectory(initialdir=str(DESKTOP), title="Wybierz folder docelowy")
        root.destroy()
        return jsonify({"path": folder or ""})
    except Exception as exc:
        return jsonify({"error": str(exc), "path": ""}), 500


@app.route("/convert", methods=["POST"])
def convert():
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "Nie przesłano pliku obrazu."}), 400

    form = request.form

    def b(key, default=False):
        v = form.get(key)
        return default if v is None else v.lower() in ("true", "on", "1", "yes")

    def i(key, default=0):
        try:
            return int(form.get(key, default))
        except (ValueError, TypeError):
            return default

    def f(key, default=0.0):
        try:
            return float(form.get(key, default))
        except (ValueError, TypeError):
            return default

    def s(key, default=""):
        return (form.get(key) or default).strip()

    formats = form.getlist("formats") or ["svg"]
    bg = s("background", "#000000")
    if not bg or bg.lower() in ("none", "transparent"):
        bg = None

    session_id = str(uuid.uuid4())
    stage_dir = STAGING / session_id
    stage_dir.mkdir(parents=True, exist_ok=True)

    cfg = Config(
        channel=s("channel", "luma"),
        invert=b("invert"),
        threshold_mode=s("threshold_mode", "otsu"),
        threshold_value=i("threshold_value", 128),
        adaptive_block_size=i("adaptive_block_size", 31),
        adaptive_C=i("adaptive_C", 5),
        upscale=i("upscale", 2),
        upscale_method=s("upscale_method", "cubic"),
        pre_blur_sigma=f("pre_blur_sigma", 1.2),
        morph_open=i("morph_open", 0),
        morph_close=i("morph_close", 0),
        dilate=i("dilate", 0),
        erode=i("erode", 0),
        min_area=f("min_area", 4.0),
        include_holes=b("include_holes", True),
        contour_sigma=f("contour_sigma", 2.0),
        resample_spacing=f("resample_spacing", 4.0),
        output_mode=s("output_mode", "bezier"),
        detect_corners=b("detect_corners"),
        corner_angle_deg=f("corner_angle_deg", 60.0),
        foreground=s("foreground", "#ffffff"),
        background=bg,
        coord_precision=i("coord_precision", 2),
        dpi=f("dpi", 96.0),
        formats=tuple(formats),
        output_dir=str(stage_dir),
        # Fall back to original uploaded filename stem, never to the temp-file name
        output_name=s("output_name") or Path(file.filename).stem or None,
    )

    suffix = Path(file.filename).suffix or ".png"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        written = vectorize(tmp_path, cfg)

        svg_b64 = None
        for p in written:
            if p.suffix == ".svg":
                svg_b64 = base64.b64encode(p.read_bytes()).decode()
                break

        _sessions[session_id] = [str(p) for p in written]

        return jsonify({
            "success": True,
            "session_id": session_id,
            "files": [{"path": str(p), "name": p.name} for p in written],
            "svg_b64": svg_b64,
        })
    except Exception as exc:
        shutil.rmtree(stage_dir, ignore_errors=True)
        return jsonify({"error": str(exc)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _unique_path(p: Path) -> Path:
    """Return p, or p with _1/_2/... suffix if a file already exists there."""
    if not p.exists():
        return p
    stem, suffix, parent = p.stem, p.suffix, p.parent
    n = 1
    while True:
        candidate = parent / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


@app.route("/save", methods=["POST"])
def save():
    data = request.get_json(force=True)
    session_id = data.get("session_id", "")
    dest = (data.get("dest") or "").strip()

    if not session_id or session_id not in _sessions:
        return jsonify({"error": "Nieznana sesja — wykonaj najpierw konwersję."}), 400
    if not dest:
        return jsonify({"error": "Nie podano katalogu docelowego."}), 400

    dest_path = Path(dest)
    try:
        dest_path.mkdir(parents=True, exist_ok=True)
        saved = []
        for src in _sessions[session_id]:
            src_p = Path(src)
            if src_p.exists():
                dst = _unique_path(dest_path / src_p.name)
                shutil.copy2(src_p, dst)
                saved.append({"path": str(dst), "name": dst.name})
        return jsonify({"success": True, "saved": saved})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/download")
def download():
    path = request.args.get("path", "")
    if not path or not os.path.isfile(path):
        return "Plik nie istnieje.", 404
    return send_file(path, as_attachment=True)


@app.route("/quit", methods=["POST"])
def quit_app():
    # Wipe staging — only temp conversion artefacts live here
    shutil.rmtree(STAGING, ignore_errors=True)
    # Delay shutdown slightly so the JSON response can be flushed first
    threading.Timer(0.4, lambda: os._exit(0)).start()
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("Platforma dostępna pod adresem:  http://localhost:5000")
    app.run(debug=True, port=5000)
