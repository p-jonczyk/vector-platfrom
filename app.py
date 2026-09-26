from __future__ import annotations
from flask import Flask, render_template, request, jsonify, send_file
from pathlib import Path
from dataclasses import asdict
import tempfile
import os
import base64
import uuid
import re
import shutil
import threading

from raster2vector import (Config, vectorize, analyze_image, ImageReadError,
                           PRESETS, FORMATS, CHANNELS)

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


# ── Uploads, form parsing, validation ────────────────────────────────────────

ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".bmp", ".tif", ".tiff", ".webp"}
THRESHOLD_MODES = ("otsu", "manual", "adaptive_mean", "adaptive_gaussian")
UPSCALE_METHODS = ("nearest", "linear", "cubic", "lanczos")
OUTPUT_MODES = ("bezier", "polygon")
NAMED_COLORS = ("black", "white", "red", "green", "blue", "gray")  # also understood by EPS/PDF
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
MSG_UNREADABLE = "Nie można odczytać obrazu — plik jest uszkodzony albo ma nieobsługiwany format."


def _error(msg: str, status: int = 400):
    return jsonify({"error": msg}), status


@app.errorhandler(413)
def _too_large(_exc):
    return _error("Plik jest za duży — maksymalnie 100 MB.", 413)


def _upload_problem(file) -> str | None:
    if not file or not file.filename:
        return "Nie przesłano pliku obrazu."
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return (f"Nieobsługiwany format pliku „{ext or 'bez rozszerzenia'}”. "
                "Obsługiwane: PNG, JPG, BMP, TIFF, WEBP.")
    return None


def _save_upload(file) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix.lower()) as tmp:
        file.save(tmp.name)
        return tmp.name


def _form_bool(form, key, default=False):
    v = form.get(key)
    return default if v is None else v.lower() in ("true", "on", "1", "yes")


def _form_int(form, key, default=0):
    try:
        return int(form.get(key, default))
    except (ValueError, TypeError):
        return default


def _form_float(form, key, default=0.0):
    try:
        return float(form.get(key, default))
    except (ValueError, TypeError):
        return default


def _form_str(form, key, default=""):
    return (form.get(key) or default).strip()


def _safe_stem(name: str) -> str | None:
    """File name without folders or characters Windows doesn't allow."""
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or None


def _color_ok(value: str) -> bool:
    return bool(_HEX_COLOR.match(value)) or value.lower() in NAMED_COLORS


def _validate(cfg: Config) -> list[str]:
    """Polish messages for settings the converter can't use (empty = all OK).
    Fields hidden in the UI for the current mode are not checked."""
    problems = []

    def need(ok, label, msg):
        if not ok:
            problems.append(f"Pole „{label}”: {msg}.")

    need(cfg.channel in CHANNELS, "Kanał koloru", "nieznana wartość")
    need(cfg.threshold_mode in THRESHOLD_MODES, "Tryb progowania", "nieznana wartość")
    if cfg.threshold_mode == "manual":
        need(0 <= cfg.threshold_value <= 255, "Wartość progu", "dozwolony zakres to 0–255")
    if cfg.threshold_mode.startswith("adaptive"):
        need(cfg.adaptive_block_size >= 3 and cfg.adaptive_block_size % 2 == 1,
             "Rozmiar bloku adaptacyjnego", "wymagana liczba nieparzysta, co najmniej 3")
    need(1 <= cfg.upscale <= 4, "Skalowanie w górę", "dozwolony zakres to 1–4")
    need(cfg.upscale_method in UPSCALE_METHODS, "Metoda skalowania", "nieznana wartość")
    for label, value in (("Rozmycie wstępne σ", cfg.pre_blur_sigma), ("Otwarcie", cfg.morph_open),
                         ("Zamknięcie", cfg.morph_close), ("Dylatacja", cfg.dilate),
                         ("Erozja", cfg.erode), ("Minimalna powierzchnia", cfg.min_area),
                         ("Wygładzanie σ", cfg.contour_sigma)):
        need(value >= 0, label, "wartość nie może być ujemna")
    need(cfg.resample_spacing > 0, "Odstęp próbkowania", "wartość musi być większa od 0")
    need(cfg.output_mode in OUTPUT_MODES, "Tryb wyjścia", "nieznana wartość")
    if cfg.output_mode == "bezier" and cfg.detect_corners:
        need(1 <= cfg.corner_angle_deg <= 179, "Kąt narożnika", "dozwolony zakres to 1–179")
    need(_color_ok(cfg.foreground), "Kolor wzoru",
         f"nieprawidłowy kolor „{cfg.foreground}”, użyj formatu #rrggbb")
    if cfg.background is not None:
        need(_color_ok(cfg.background), "Kolor tła",
             f"nieprawidłowy kolor „{cfg.background}”, użyj formatu #rrggbb lub none")
    need(0 <= cfg.coord_precision <= 6, "Precyzja współrzędnych", "dozwolony zakres to 0–6")
    need(cfg.dpi > 0, "Rozdzielczość (DPI)", "wartość musi być większa od 0")
    return problems


@app.route("/analyze", methods=["POST"])
def analyze():
    """Check run right after an image is chosen: size, DPI stored in the file
    and which `invert` setting keeps the background out of the trace."""
    file = request.files.get("image")
    problem = _upload_problem(file)
    if problem:
        return _error(problem)
    form = request.form
    cfg = Config(
        channel=_form_str(form, "channel", "luma"),
        threshold_mode=_form_str(form, "threshold_mode", "otsu"),
        threshold_value=_form_int(form, "threshold_value", 128),
        adaptive_block_size=_form_int(form, "adaptive_block_size", 31),
        adaptive_C=_form_int(form, "adaptive_C", 5),
        pre_blur_sigma=_form_float(form, "pre_blur_sigma", 1.2),
    )
    if _validate(cfg):  # unusable threshold settings: judge with the defaults instead
        cfg = Config(channel=cfg.channel if cfg.channel in CHANNELS else "luma")
    tmp_path = None
    try:
        tmp_path = _save_upload(file)
        return jsonify(analyze_image(tmp_path, cfg))
    except ImageReadError:
        return _error(MSG_UNREADABLE)
    except Exception as exc:
        return _error(f"Nie można przeanalizować obrazu: {exc}", 500)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.route("/convert", methods=["POST"])
def convert():
    file = request.files.get("image")
    problem = _upload_problem(file)
    if problem:
        return _error(problem)

    form = request.form
    bg = _form_str(form, "background", "#000000")
    if not bg or bg.lower() in ("none", "transparent"):
        bg = None
    chosen = [x for x in FORMATS if x in form.getlist("formats")] or ["svg"]
    # SVG is always written for the preview, but only offered for saving if chosen
    to_write = tuple(chosen) if "svg" in chosen else tuple(chosen) + ("svg",)

    cfg = Config(
        channel=_form_str(form, "channel", "luma"),
        invert=_form_bool(form, "invert"),
        threshold_mode=_form_str(form, "threshold_mode", "otsu"),
        threshold_value=_form_int(form, "threshold_value", 128),
        adaptive_block_size=_form_int(form, "adaptive_block_size", 31),
        adaptive_C=_form_int(form, "adaptive_C", 5),
        upscale=_form_int(form, "upscale", 2),
        upscale_method=_form_str(form, "upscale_method", "cubic"),
        pre_blur_sigma=_form_float(form, "pre_blur_sigma", 1.2),
        morph_open=_form_int(form, "morph_open", 0),
        morph_close=_form_int(form, "morph_close", 0),
        dilate=_form_int(form, "dilate", 0),
        erode=_form_int(form, "erode", 0),
        min_area=_form_float(form, "min_area", 4.0),
        include_holes=_form_bool(form, "include_holes", True),
        contour_sigma=_form_float(form, "contour_sigma", 2.0),
        resample_spacing=_form_float(form, "resample_spacing", 4.0),
        output_mode=_form_str(form, "output_mode", "bezier"),
        detect_corners=_form_bool(form, "detect_corners"),
        corner_angle_deg=_form_float(form, "corner_angle_deg", 60.0),
        foreground=_form_str(form, "foreground", "#ffffff"),
        background=bg,
        coord_precision=_form_int(form, "coord_precision", 2),
        dpi=_form_float(form, "dpi", 96.0),
        formats=to_write,
        # Fall back to original uploaded filename stem, never to the temp-file name
        output_name=(_safe_stem(_form_str(form, "output_name"))
                     or _safe_stem(Path(file.filename).stem) or "obraz"),
    )
    problems = _validate(cfg)
    if problems:
        return _error(" ".join(problems))

    session_id = str(uuid.uuid4())
    stage_dir = STAGING / session_id
    stage_dir.mkdir(parents=True, exist_ok=True)
    cfg.output_dir = str(stage_dir)

    tmp_path = None
    try:
        tmp_path = _save_upload(file)
        written = vectorize(tmp_path, cfg)

        svg = next((p for p in written if p.suffix == ".svg"), None)
        svg_b64 = base64.b64encode(svg.read_bytes()).decode() if svg else None
        if svg and "svg" not in chosen:
            svg.unlink(missing_ok=True)
            written = [p for p in written if p != svg]

        _sessions[session_id] = [str(p) for p in written]

        return jsonify({
            "success": True,
            "session_id": session_id,
            "files": [{"path": str(p), "name": p.name} for p in written],
            "svg_b64": svg_b64,
        })
    except ImageReadError:
        shutil.rmtree(stage_dir, ignore_errors=True)
        return _error(MSG_UNREADABLE)
    except Exception as exc:
        shutil.rmtree(stage_dir, ignore_errors=True)
        return _error(f"Konwersja nie powiodła się: {exc}", 500)
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
    except PermissionError:
        return _error("Brak uprawnień do zapisu w wybranym folderze.", 500)
    except (FileExistsError, NotADirectoryError):
        return _error("Wskazana ścieżka nie jest folderem.", 500)
    except OSError as exc:
        return _error(f"Nie można zapisać plików: {exc.strerror or exc}", 500)
    except Exception as exc:
        return _error(f"Nie można zapisać plików: {exc}", 500)


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
