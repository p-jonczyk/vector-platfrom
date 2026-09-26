"""
raster2vector.py — Configurable raster-to-vector conversion.

Output formats: SVG, EPS, PDF and PLT (HPGL). The `dpi` setting gives every
format the same physical size: size_mm = pixels / dpi * 25.4.
Transparent PNG / WEBP / TIFF images are placed on a background that contrasts
with their visible content before tracing.

Configuration sources, applied in order (later wins):
    1. Defaults (in Config dataclass)
    2. Named preset (--preset NAME or `preset=...`)
    3. Config file (--config FILE.json)
    4. Explicit CLI flags / function arguments

Run `--dump-config` to print the effective config (handy for reproducibility).
Run `--list-presets` to see available presets.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path
from typing import Optional, Tuple, List
import argparse
import json
import math
import sys
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d


# ============================================================================
# CONFIG
# ============================================================================

@dataclass
class Config:
    # ---- 1. Input / channel ------------------------------------------------
    channel: str = "luma"
    """How to convert color input to grayscale.
       'luma'  : standard luminance (default)
       'red'   : red channel only
       'green' : green channel only
       'blue'  : blue channel only
       'max'   : per-pixel max of R,G,B (good for white-on-color)
       'min'   : per-pixel min of R,G,B (good for dark-on-color)"""

    invert: bool = False
    """If True, treat foreground as the *darker* region (e.g. black-on-white)."""

    # ---- 2. Threshold ------------------------------------------------------
    threshold_mode: str = "otsu"
    """'otsu' (auto), 'manual' (uses threshold_value),
       'adaptive_mean', 'adaptive_gaussian'."""

    threshold_value: int = 128
    """Used only when threshold_mode='manual'. Range 0–255."""

    adaptive_block_size: int = 31
    """Window size for adaptive thresholding. Must be odd, >= 3."""

    adaptive_C: int = 5
    """Constant subtracted from local mean in adaptive thresholding."""

    # ---- 3. Pre-trace smoothing -------------------------------------------
    upscale: int = 2
    """Integer upscale factor before tracing. 1 = none, 2 = good, 4 = max quality."""

    upscale_method: str = "cubic"
    """'nearest', 'linear', 'cubic', 'lanczos'."""

    pre_blur_sigma: float = 1.2
    """Gaussian blur σ applied to source before thresholding. 0 = none."""

    # ---- 4. Morphological cleanup ----------------------------------------
    morph_open: int = 0
    """Kernel size for opening (erode + dilate). Removes specks. 0 = off."""

    morph_close: int = 0
    """Kernel size for closing (dilate + erode). Fills small gaps. 0 = off."""

    dilate: int = 0
    """Extra dilation iterations (thickens foreground). 0 = off."""

    erode: int = 0
    """Extra erosion iterations (thins foreground). 0 = off."""

    # ---- 5. Contour selection --------------------------------------------
    min_area: float = 4.0
    """Minimum contour area (in original-image px) to keep. Filters specks."""

    include_holes: bool = True
    """If True, cut out interior holes (letter counters etc.). evenodd fill."""

    # ---- 6. Contour smoothing --------------------------------------------
    contour_sigma: float = 2.0
    """Periodic Gaussian σ on contour coordinates. Higher = smoother."""

    resample_spacing: float = 4.0
    """Arclength (px) between resampled contour points. Lower = more detail."""

    # ---- 7. Curve fitting ------------------------------------------------
    output_mode: str = "bezier"
    """'bezier' = cubic Bézier curves (smooth), 'polygon' = straight lines."""

    detect_corners: bool = False
    """If True, preserve sharp corners (don't round them with curves)."""

    corner_angle_deg: float = 60.0
    """Angle change (degrees) above which a point is considered a corner."""

    # ---- 8. Output formatting --------------------------------------------
    foreground: str = "#ffffff"
    """Foreground fill color as hex (#rrggbb) or name."""

    background: Optional[str] = "#000000"
    """Background fill color, or None / 'none' / 'transparent' for none."""

    coord_precision: int = 2
    """Decimal places in emitted coordinates. 0 = integer, 2 = default.
       Applies in each format's own unit: px (SVG), pt (EPS, PDF).
       PLT always uses integer plotter units (0.025 mm)."""

    dpi: float = 96.0
    """Source image resolution in pixels per inch. Sets the physical size of
       the output in every format: size_mm = pixels / dpi * 25.4.
       Only scales the result; the traced shape is unchanged.
       96 = CSS/SVG reference resolution (default)."""

    # ---- 9. File output --------------------------------------------------
    formats: Tuple[str, ...] = ("svg", "eps")
    """Which formats to write. Subset of FORMATS: {'svg', 'eps', 'pdf', 'plt'}."""

    output_dir: str = "."
    output_name: Optional[str] = None
    """Output filename stem. Defaults to input stem."""

    # ---- helpers ---------------------------------------------------------
    def merged_with(self, overrides: dict) -> "Config":
        """Return a copy with `overrides` applied (skipping None values)."""
        valid = {f.name for f in fields(self)}
        clean = {k: v for k, v in overrides.items() if k in valid and v is not None}
        return Config(**{**asdict(self), **clean})

    def to_json(self, indent: int = 2) -> str:
        d = asdict(self)
        d["formats"] = list(d["formats"])  # tuples aren't JSON
        return json.dumps(d, indent=indent)

    @classmethod
    def from_json(cls, text: str) -> "Config":
        d = json.loads(text)
        if "formats" in d:
            d["formats"] = tuple(d["formats"])
        return cls(**{k: v for k, v in d.items() if k in {f.name for f in fields(cls)}})


# ============================================================================
# PRESETS
# ============================================================================

PRESETS = {
    "logo": {
        # current default — clean monochrome logo / line-art
    },
    "icon": {
        # smaller, geometric, sharp corners matter
        "contour_sigma": 1.0,
        "resample_spacing": 2.0,
        "detect_corners": True,
        "corner_angle_deg": 50.0,
    },
    "silhouette": {
        # heavy smoothing, soft / poster-like
        "contour_sigma": 4.0,
        "resample_spacing": 8.0,
        "pre_blur_sigma": 2.0,
    },
    "sketch": {
        # preserve every wobble, polygon output
        "output_mode": "polygon",
        "contour_sigma": 0.5,
        "resample_spacing": 2.0,
        "pre_blur_sigma": 0.5,
    },
    "high_fidelity": {
        # max quality for print, large files
        "upscale": 4,
        "contour_sigma": 3.0,
        "resample_spacing": 2.0,
        "coord_precision": 3,
    },
    "compact": {
        # minimize file size, still vector
        "resample_spacing": 10.0,
        "contour_sigma": 2.5,
        "coord_precision": 1,
        "min_area": 16.0,
    },
    "stencil": {
        # binary stencil — clean, no interior holes preserved
        "include_holes": False,
        "morph_open": 3,
        "morph_close": 3,
        "contour_sigma": 2.5,
    },
    "dark_on_light": {
        # for black-on-white inputs
        "invert": True,
        "background": "#ffffff",
        "foreground": "#000000",
    },
}


# ============================================================================
# OUTPUT UNITS
# ============================================================================

FORMATS = ("svg", "eps", "pdf", "plt")

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0            # PostScript / PDF point
HPGL_UNITS_PER_INCH = 1016.0  # HPGL plotter unit = 0.025 mm (40 per mm)
HPGL_FLATTEN_TOL = 2.0        # max curve-to-chord deviation in PLT, plotter
                              # units (2 = 0.05 mm, below cutter precision)


def _fmt_len(v: float) -> str:
    """Physical length / colour component: up to 3 decimals, no trailing zeros."""
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def _subpath_array(beziers, h: int, k: float) -> np.ndarray:
    """Bézier segments of one subpath as an (n, 4, 2) array in a y-up space:
    image px scaled by `k`, origin at the bottom-left (PostScript, PDF, HPGL)."""
    s = np.asarray(beziers, dtype=np.float64)
    out = s * k
    out[..., 1] = (h - s[..., 1]) * k
    return out


# ============================================================================
# COLOR HELPERS
# ============================================================================

_INTERP = {
    "nearest": cv2.INTER_NEAREST,
    "linear":  cv2.INTER_LINEAR,
    "cubic":   cv2.INTER_CUBIC,
    "lanczos": cv2.INTER_LANCZOS4,
}

def _hex_to_rgb01(s: Optional[str]):
    if s is None or s.lower() in ("none", "transparent"):
        return None
    s = s.strip()
    if s.startswith("#"):
        s = s[1:]
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        return r / 255, g / 255, b / 255
    named = {"black": (0, 0, 0), "white": (1, 1, 1), "red": (1, 0, 0),
             "green": (0, 0.5, 0), "blue": (0, 0, 1), "gray": (0.5, 0.5, 0.5)}
    if s.lower() in named:
        return named[s.lower()]
    raise ValueError(f"Unrecognised color: {s!r}")


# ============================================================================
# PIPELINE
# ============================================================================

CHANNELS = ("luma", "red", "green", "blue", "max", "min")


class ImageReadError(ValueError):
    """The file could not be decoded as an image (unsupported format or damaged)."""


def _decode(data: np.ndarray, flags: int, image_path) -> np.ndarray:
    img = cv2.imdecode(data, flags) if data.size else None
    if img is None:
        raise ImageReadError(f"Cannot read image (unsupported format or damaged file): {image_path}")
    return img


def _may_have_alpha(data: np.ndarray) -> bool:
    """PNG, WEBP and TIFF can carry transparency (JPEG can't; BMP alpha is unreliable)."""
    head = data[:12].tobytes()
    return (head.startswith(b"\x89PNG") or head[:4] in (b"II*\x00", b"MM\x00*")
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))


def _flatten_transparency(data: np.ndarray) -> Optional[np.ndarray]:
    """For an image with real transparency, return it as BGR placed on a
    background that contrasts with its visible content: white behind dark
    content, black behind light content. Transparent areas then behave like
    the background of an ordinary image. Returns None if there's no transparency."""
    if not _may_have_alpha(data):
        return None
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None or img.ndim != 3 or img.shape[2] not in (2, 4):
        return None
    if img.dtype == np.uint16:
        img = (img >> 8).astype(np.uint8)
    elif img.dtype != np.uint8:
        return None
    alpha = img[..., -1]
    if alpha.min() == 255 or alpha.max() == 0:  # fully opaque, or alpha unused
        return None
    color = img[..., :-1]
    bgr = cv2.cvtColor(color[..., 0], cv2.COLOR_GRAY2BGR) if color.shape[2] == 1 else color
    visible = alpha >= 128
    dark = visible.any() and cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)[visible].mean() < 128
    bg = 255.0 if dark else 0.0
    a = alpha.astype(np.float32)[..., None] / 255.0
    return np.clip(bgr.astype(np.float32) * a + bg * (1.0 - a) + 0.5, 0, 255).astype(np.uint8)


def to_grayscale(image_path: Path, channel: str) -> np.ndarray:
    """Load an image as 8-bit grayscale using the given channel.
    Reads through a byte buffer so non-ASCII paths work on Windows."""
    if channel not in CHANNELS:
        raise ValueError(f"Bad channel: {channel}")
    data = np.fromfile(str(image_path), dtype=np.uint8)
    flat = _flatten_transparency(data)
    if channel == "luma":
        if flat is not None:
            return cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY)
        return _decode(data, cv2.IMREAD_GRAYSCALE, image_path)
    bgr = flat if flat is not None else _decode(data, cv2.IMREAD_COLOR, image_path)
    b, g, r = cv2.split(bgr)
    if channel == "red":   return r
    if channel == "green": return g
    if channel == "blue":  return b
    if channel == "max":   return np.maximum(np.maximum(r, g), b)
    return np.minimum(np.minimum(r, g), b)


def threshold_image(gray: np.ndarray, cfg: Config) -> np.ndarray:
    mode = cfg.threshold_mode
    if mode == "otsu":
        _, b = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif mode == "manual":
        _, b = cv2.threshold(gray, cfg.threshold_value, 255, cv2.THRESH_BINARY)
    elif mode == "adaptive_mean":
        b = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY,
                                  cfg.adaptive_block_size, cfg.adaptive_C)
    elif mode == "adaptive_gaussian":
        b = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY,
                                  cfg.adaptive_block_size, cfg.adaptive_C)
    else:
        raise ValueError(f"Unknown threshold_mode: {mode}")
    return cv2.bitwise_not(b) if cfg.invert else b


def preprocess(image_path: Path, cfg: Config):
    gray = to_grayscale(image_path, cfg.channel)
    h, w = gray.shape
    if cfg.upscale != 1:
        gray = cv2.resize(gray, (w * cfg.upscale, h * cfg.upscale),
                          interpolation=_INTERP[cfg.upscale_method])
    if cfg.pre_blur_sigma > 0:
        gray = cv2.GaussianBlur(gray, (0, 0), sigmaX=cfg.pre_blur_sigma)
    binary = threshold_image(gray, cfg)
    return binary, w, h


def morphology(binary: np.ndarray, cfg: Config) -> np.ndarray:
    out = binary
    if cfg.morph_open > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                      (cfg.morph_open, cfg.morph_open))
        out = cv2.morphologyEx(out, cv2.MORPH_OPEN, k)
    if cfg.morph_close > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                      (cfg.morph_close, cfg.morph_close))
        out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, k)
    if cfg.dilate > 0:
        out = cv2.dilate(out, np.ones((3, 3), np.uint8), iterations=cfg.dilate)
    if cfg.erode > 0:
        out = cv2.erode(out, np.ones((3, 3), np.uint8), iterations=cfg.erode)
    return out


def find_chains(binary: np.ndarray, cfg: Config):
    min_area_scaled = cfg.min_area * (cfg.upscale ** 2)
    # Without holes only the outermost contours count: shapes inside a hole are
    # covered by the solid outer shape (with even-odd fill they'd become holes).
    mode = cv2.RETR_CCOMP if cfg.include_holes else cv2.RETR_EXTERNAL
    contours, hierarchy = cv2.findContours(binary, mode, cv2.CHAIN_APPROX_NONE)
    if hierarchy is None:
        return []
    hierarchy = hierarchy[0]
    chains = []
    for i, cnt in enumerate(contours):
        if hierarchy[i][3] != -1:
            continue
        if cv2.contourArea(cnt) < min_area_scaled:
            continue
        outer = cnt.reshape(-1, 2).astype(np.float64)
        holes = []
        if cfg.include_holes:
            child = hierarchy[i][2]
            while child != -1:
                hc = contours[child]
                if cv2.contourArea(hc) >= min_area_scaled:
                    holes.append(hc.reshape(-1, 2).astype(np.float64))
                child = hierarchy[child][0]
        chains.append([outer] + holes)
    return chains


def smooth_periodic(pts: np.ndarray, sigma: float) -> np.ndarray:
    if len(pts) < 4 or sigma <= 0:
        return pts
    x = gaussian_filter1d(pts[:, 0], sigma=sigma, mode="wrap")
    y = gaussian_filter1d(pts[:, 1], sigma=sigma, mode="wrap")
    return np.column_stack([x, y])


def resample_uniform(pts: np.ndarray, spacing: float) -> np.ndarray:
    if len(pts) < 4:
        return pts
    closed = np.vstack([pts, pts[:1]])
    diffs = np.diff(closed, axis=0)
    seg_lens = np.sqrt((diffs * diffs).sum(axis=1))
    cum = np.concatenate([[0.0], np.cumsum(seg_lens)])
    total = cum[-1]
    if total <= 0:
        return pts
    n = max(8, int(round(total / spacing)))
    ts = np.linspace(0.0, total, n, endpoint=False)
    sx = np.interp(ts, cum, closed[:, 0])
    sy = np.interp(ts, cum, closed[:, 1])
    return np.column_stack([sx, sy])


def detect_corner_indices(pts: np.ndarray, angle_thresh_deg: float) -> List[int]:
    """Return indices of points that look like sharp corners (closed curve)."""
    if len(pts) < 4:
        return []
    n = len(pts)
    v_in  = pts - np.roll(pts, 1, axis=0)
    v_out = np.roll(pts, -1, axis=0) - pts
    # Normalise
    n_in  = np.linalg.norm(v_in, axis=1) + 1e-12
    n_out = np.linalg.norm(v_out, axis=1) + 1e-12
    cosang = (v_in * v_out).sum(axis=1) / (n_in * n_out)
    cosang = np.clip(cosang, -1.0, 1.0)
    ang = np.degrees(np.arccos(cosang))  # 0 = straight, 180 = U-turn
    return [i for i in range(n) if ang[i] > angle_thresh_deg]


# --- Bézier conversion ------------------------------------------------------

def bspline_to_beziers(pts: np.ndarray):
    """Uniform periodic cubic B-spline → list of (B0,B1,B2,B3). C2-continuous."""
    n = len(pts)
    if n < 3:
        return []
    out = []
    for i in range(n):
        Pm = pts[(i - 1) % n]
        P0 = pts[i]
        P1 = pts[(i + 1) % n]
        P2 = pts[(i + 2) % n]
        B0 = (Pm + 4*P0 + P1) / 6.0
        B1 = (2*P0 + P1) / 3.0
        B2 = (P0 + 2*P1) / 3.0
        B3 = (P0 + 4*P1 + P2) / 6.0
        out.append((B0, B1, B2, B3))
    return out


def catmull_rom_segment(P: List[np.ndarray]):
    """Open Catmull-Rom through points P[0..k] → list of Bézier segments.
    Curve passes through every P[i]. Endpoints get one-sided tangents."""
    n = len(P)
    if n < 2:
        return []
    out = []
    for i in range(n - 1):
        P0 = P[i]; P1 = P[i + 1]
        # incoming tangent at P0
        if i == 0:
            t_in = P1 - P0
        else:
            t_in = (P1 - P[i - 1]) * 0.5
        # outgoing tangent at P1
        if i + 1 == n - 1:
            t_out = P1 - P0
        else:
            t_out = (P[i + 2] - P0) * 0.5
        B0 = P0
        B1 = P0 + t_in / 3.0
        B2 = P1 - t_out / 3.0
        B3 = P1
        out.append((B0, B1, B2, B3))
    return out


def contour_to_beziers_with_corners(pts: np.ndarray, corner_idx: List[int]):
    """Split closed contour at corner indices, Catmull-Rom each open segment."""
    n = len(pts)
    if not corner_idx:
        return bspline_to_beziers(pts)
    corner_idx = sorted(set(corner_idx))
    out = []
    for k in range(len(corner_idx)):
        a = corner_idx[k]
        b = corner_idx[(k + 1) % len(corner_idx)]
        # collect points from a..b (inclusive), wrapping around
        if b > a:
            segment = [pts[j] for j in range(a, b + 1)]
        else:
            segment = [pts[j] for j in range(a, n)] + [pts[j] for j in range(0, b + 1)]
        out.extend(catmull_rom_segment(segment))
    return out


# --- Polygon "fake bezier" for uniform emit path ---------------------------

def polygon_as_beziers(pts: np.ndarray):
    """Emit straight segments as degenerate cubic Béziers."""
    n = len(pts)
    out = []
    for i in range(n):
        P0 = pts[i]
        P1 = pts[(i + 1) % n]
        out.append((P0, P0, P1, P1))
    return out


def chains_to_beziers(chains, cfg: Config):
    out = []
    for chain in chains:
        bchain = []
        for pts in chain:
            sm = smooth_periodic(pts, sigma=cfg.contour_sigma * cfg.upscale)
            rs = resample_uniform(sm, spacing=cfg.resample_spacing * cfg.upscale)
            rs = rs / cfg.upscale
            if len(rs) < 4:
                bchain.append(polygon_as_beziers(rs))
                continue
            if cfg.output_mode == "polygon":
                bchain.append(polygon_as_beziers(rs))
            elif cfg.output_mode == "bezier":
                if cfg.detect_corners:
                    corners = detect_corner_indices(rs, cfg.corner_angle_deg)
                    bchain.append(contour_to_beziers_with_corners(rs, corners))
                else:
                    bchain.append(bspline_to_beziers(rs))
            else:
                raise ValueError(f"Unknown output_mode: {cfg.output_mode}")
        out.append(bchain)
    return out


# ============================================================================
# EMITTERS
# ============================================================================

def _fmt(precision: int):
    if precision <= 0:
        return lambda v: f"{int(round(v))}"
    return lambda v: f"{v:.{precision}f}"


def write_svg(path: Path, w: int, h: int, bezier_chains, cfg: Config):
    f = _fmt(cfg.coord_precision)
    parts = []
    for chain in bezier_chains:
        for beziers in chain:
            if not beziers:
                continue
            s = np.asarray(beziers, dtype=np.float64)
            # Straight segments are stored as degenerate cubics: write them as L
            is_line = (s[:, 1] == s[:, 0]).all(axis=1) & (s[:, 2] == s[:, 3]).all(axis=1)
            parts.append(f"M{f(s[0, 0, 0])},{f(s[0, 0, 1])}")
            for (_, c1, c2, p3), line in zip(s, is_line):
                if line:
                    parts.append(f"L{f(p3[0])},{f(p3[1])}")
                else:
                    parts.append(
                        f"C{f(c1[0])},{f(c1[1])} "
                        f"{f(c2[0])},{f(c2[1])} "
                        f"{f(p3[0])},{f(p3[1])}"
                    )
            parts.append("Z")
    d = "".join(parts)
    bg_rect = ""
    if cfg.background and cfg.background.lower() not in ("none", "transparent"):
        bg_rect = f'<rect width="{w}" height="{h}" fill="{cfg.background}"/>'
    # Physical size in mm (from dpi); path coordinates stay in image pixels.
    mm = MM_PER_INCH / cfg.dpi
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w} {h}" '
        f'width="{_fmt_len(w * mm)}mm" height="{_fmt_len(h * mm)}mm">'
        f'{bg_rect}'
        f'<path d="{d}" fill="{cfg.foreground}" fill-rule="evenodd"/>'
        f'</svg>'
    )
    path.write_text(svg, encoding="utf-8")


def write_eps(path: Path, w: int, h: int, bezier_chains, cfg: Config):
    f = _fmt(cfg.coord_precision)
    k = PT_PER_INCH / cfg.dpi          # image px -> PostScript points
    W, H = w * k, h * k
    lines = [
        "%!PS-Adobe-3.0 EPSF-3.0",
        f"%%BoundingBox: 0 0 {math.ceil(W)} {math.ceil(H)}",
        f"%%HiResBoundingBox: 0 0 {_fmt_len(W)} {_fmt_len(H)}",
        "%%Pages: 1",
        "%%EndComments",
        "%%Page: 1 1",
        "gsave",
    ]
    bg = _hex_to_rgb01(cfg.background)
    if bg is not None:
        lines += [f"{bg[0]} {bg[1]} {bg[2]} setrgbcolor",
                  f"0 0 {_fmt_len(W)} {_fmt_len(H)} rectfill"]
    fg = _hex_to_rgb01(cfg.foreground) or (1, 1, 1)
    lines += [f"{fg[0]} {fg[1]} {fg[2]} setrgbcolor", "newpath"]
    for chain in bezier_chains:
        for beziers in chain:
            if not beziers:
                continue
            s = _subpath_array(beziers, h, k)
            lines.append(f"{f(s[0, 0, 0])} {f(s[0, 0, 1])} moveto")
            for _, c1, c2, p3 in s:
                lines.append(
                    f"{f(c1[0])} {f(c1[1])} "
                    f"{f(c2[0])} {f(c2[1])} "
                    f"{f(p3[0])} {f(p3[1])} curveto"
                )
            lines.append("closepath")
    lines += ["eofill", "grestore", "showpage", "%%EOF"]
    path.write_text("\n".join(lines), encoding="ascii")


def write_pdf(path: Path, w: int, h: int, bezier_chains, cfg: Config):
    """Single-page vector PDF. Page size = physical output size (from dpi).
    Straight segments are written as lines, curves as cubic Béziers,
    filled with the even-odd rule like SVG/EPS."""
    f = _fmt(cfg.coord_precision)
    k = PT_PER_INCH / cfg.dpi          # image px -> PDF points
    W, H = w * k, h * k

    def rgb(c):
        return " ".join(_fmt_len(v) for v in c)

    ops = []
    bg = _hex_to_rgb01(cfg.background)
    if bg is not None:
        ops.append(f"{rgb(bg)} rg 0 0 {_fmt_len(W)} {_fmt_len(H)} re f")
    fg = _hex_to_rgb01(cfg.foreground) or (1, 1, 1)
    ops.append(f"{rgb(fg)} rg")
    has_path = False
    for chain in bezier_chains:
        for beziers in chain:
            if not beziers:
                continue
            s = _subpath_array(beziers, h, k)
            is_line = (s[:, 1] == s[:, 0]).all(axis=1) & (s[:, 2] == s[:, 3]).all(axis=1)
            ops.append(f"{f(s[0, 0, 0])} {f(s[0, 0, 1])} m")
            for (_, c1, c2, p3), line in zip(s, is_line):
                if line:
                    ops.append(f"{f(p3[0])} {f(p3[1])} l")
                else:
                    ops.append(f"{f(c1[0])} {f(c1[1])} {f(c2[0])} {f(c2[1])} "
                               f"{f(p3[0])} {f(p3[1])} c")
            ops.append("h")
            has_path = True
    if has_path:
        ops.append("f*")
    content = "\n".join(ops).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_fmt_len(W)} {_fmt_len(H)}] "
         f"/Resources << >> /Contents 4 0 R >>").encode("ascii"),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Producer (raster2vector) >>",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R /Info 5 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, xref_at))
    path.write_bytes(bytes(out))


def _flatten_cubics(s: np.ndarray, tol: float) -> np.ndarray:
    """Flatten a chain of cubic Béziers (n, 4, 2) into a polyline whose
    deviation from the curves is <= tol. Segments per curve from Wang's
    formula; straight (degenerate) segments stay a single step."""
    d1 = s[:, 0] - 2 * s[:, 1] + s[:, 2]
    d2 = s[:, 1] - 2 * s[:, 2] + s[:, 3]
    m = np.maximum(np.hypot(d1[:, 0], d1[:, 1]), np.hypot(d2[:, 0], d2[:, 1]))
    n = np.maximum(1, np.ceil(np.sqrt(0.75 * m / tol))).astype(np.int64)
    seg = np.repeat(np.arange(len(s)), n)
    step = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n) + 1
    t = (step / n[seg])[:, None]
    u = 1.0 - t
    p = s[seg]
    pts = u**3 * p[:, 0] + 3 * u**2 * t * p[:, 1] + 3 * u * t**2 * p[:, 2] + t**3 * p[:, 3]
    return np.vstack([s[:1, 0], pts])


def write_plt(path: Path, w: int, h: int, bezier_chains, cfg: Config):
    """HPGL cut file for plotters / vinyl cutters (.plt).
    Units: 40 per mm, origin bottom-left, size from dpi. Holds cut paths
    only: colours and background are not written. Curves are flattened
    to straight segments (HPGL_FLATTEN_TOL). Holes are cut before their
    outer contour so the shape doesn't shift on the material."""
    k = HPGL_UNITS_PER_INCH / cfg.dpi  # image px -> plotter units
    cmds = ["IN;", "PA;", "SP1;"]
    for chain in bezier_chains:
        for beziers in chain[1:] + chain[:1]:  # holes first, outer contour last
            if not beziers:
                continue
            pts = np.rint(_flatten_cubics(_subpath_array(beziers, h, k),
                                          HPGL_FLATTEN_TOL)).astype(np.int64)
            keep = np.ones(len(pts), dtype=bool)
            keep[1:] = (pts[1:] != pts[:-1]).any(axis=1)
            pts = pts[keep]
            if (pts[0] != pts[-1]).any():
                pts = np.vstack([pts, pts[:1]])
            if len(pts) < 4:  # collapsed below plotter resolution
                continue
            cmds.append(f"PU{pts[0, 0]},{pts[0, 1]};")
            for i in range(1, len(pts), 64):
                cmds.append("PD" + ",".join(f"{x},{y}" for x, y in pts[i:i + 64]) + ";")
    cmds += ["PU0,0;", "SP0;"]
    path.write_text("\n".join(cmds) + "\n", encoding="ascii")


_WRITERS = {"svg": write_svg, "eps": write_eps, "pdf": write_pdf, "plt": write_plt}


# ============================================================================
# PUBLIC API
# ============================================================================

def vectorize(input_path, cfg: Optional[Config] = None, **overrides):
    """Vectorize an image with the given config.

    Examples:
        vectorize("logo.png")
        vectorize("logo.png", Config(output_mode="polygon"))
        vectorize("logo.png", smoothness=1.5, foreground="#ff0000")  # via overrides
    """
    cfg = (cfg or Config()).merged_with(overrides)
    if not cfg.dpi or cfg.dpi <= 0:
        raise ValueError(f"dpi must be greater than 0, got {cfg.dpi!r}")
    input_path = Path(input_path)
    out_dir = Path(cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = cfg.output_name or input_path.stem

    binary, w, h = preprocess(input_path, cfg)
    binary = morphology(binary, cfg)
    chains = find_chains(binary, cfg)
    bezier_chains = chains_to_beziers(chains, cfg)

    n_sub = sum(len(c) for c in bezier_chains)
    n_seg = sum(len(b) for c in bezier_chains for b in c)
    mm = MM_PER_INCH / cfg.dpi
    print(f"[{stem}] {len(bezier_chains)} shapes, {n_sub} subpaths, {n_seg} segments, "
          f"{w * mm:.1f} x {h * mm:.1f} mm @ {cfg.dpi:g} dpi")

    written = []
    for fmt in FORMATS:
        if fmt in cfg.formats:
            p = out_dir / f"{stem}.{fmt}"
            _WRITERS[fmt](p, w, h, bezier_chains, cfg); written.append(p)
            print(f"  → {p}")
    return written


def read_dpi(image_path) -> Optional[float]:
    """Resolution stored in the image file (PNG pHYs, JPEG JFIF/EXIF, TIFF, BMP).
    None when absent or implausible, or when Pillow isn't installed."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(str(image_path)) as im:
            dpi = im.info.get("dpi")
        x = float(dpi[0] if isinstance(dpi, (tuple, list)) else dpi)
    except Exception:
        return None
    return round(x, 1) if 10 <= x <= 20000 else None


def analyze_image(image_path, cfg: Optional[Config] = None) -> dict:
    """Quick check for the web UI before converting.

    Returns the image size as the converter sees it, the DPI stored in the
    file, and `suggest_invert`: the `invert` setting that keeps the image
    border (the background) out of the trace. None when the border is mixed,
    e.g. photos or designs that run off the edge."""
    cfg = (cfg or Config()).merged_with({"invert": False, "upscale": 1})
    binary, w, h = preprocess(Path(image_path), cfg)
    b = max(1, round(min(w, h) * 0.02))
    border = np.concatenate([binary[:b].ravel(), binary[-b:].ravel(),
                             binary[:, :b].ravel(), binary[:, -b:].ravel()]) > 0
    ratio = float(border.mean())  # share of the border traced without invert
    suggest = True if ratio > 0.75 else False if ratio < 0.25 else None
    return {"width": w, "height": h, "dpi": read_dpi(image_path), "suggest_invert": suggest}


# ============================================================================
# CLI
# ============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Configurable raster → vector (SVG, EPS, PDF, PLT) converter.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("input", nargs="?", help="Input raster file (.png/.jpg/...)")
    p.add_argument("--config", help="Path to JSON config file")
    p.add_argument("--preset", choices=list(PRESETS.keys()),
                   help="Apply a named preset before other overrides")
    p.add_argument("--list-presets", action="store_true",
                   help="List built-in presets and exit")
    p.add_argument("--dump-config", action="store_true",
                   help="Print effective config as JSON and exit")

    # Add one flag per Config field so everything is overridable from CLI.
    for f in fields(Config):
        flag = "--" + f.name.replace("_", "-")
        if f.type == "bool" or isinstance(f.default, bool):
            p.add_argument(flag, dest=f.name, action=argparse.BooleanOptionalAction,
                           default=None, help=f.__doc__ or "")
        elif f.name == "formats":
            p.add_argument(flag, dest=f.name, nargs="+",
                           choices=list(FORMATS), default=None,
                           help="Output formats")
        elif f.type in ("int",) or isinstance(f.default, int):
            p.add_argument(flag, dest=f.name, type=int, default=None)
        elif f.type in ("float",) or isinstance(f.default, float):
            p.add_argument(flag, dest=f.name, type=float, default=None)
        else:
            p.add_argument(flag, dest=f.name, type=str, default=None)
    return p


def resolve_config(args) -> Config:
    cfg = Config()
    if args.preset:
        cfg = cfg.merged_with(PRESETS[args.preset])
    if args.config:
        cfg = cfg.merged_with(json.loads(Path(args.config).read_text()))
    # CLI overrides (only non-None)
    cli_over = {f.name: getattr(args, f.name, None) for f in fields(Config)}
    cfg = cfg.merged_with(cli_over)
    return cfg


def main(argv=None):
    args = build_arg_parser().parse_args(argv)

    if args.list_presets:
        print("Available presets:")
        for name, vals in PRESETS.items():
            print(f"  {name:15s}  {vals or '(defaults)'}")
        return 0

    cfg = resolve_config(args)

    if args.dump_config:
        print(cfg.to_json())
        return 0

    if not args.input:
        print("error: input file required (or use --list-presets / --dump-config)",
              file=sys.stderr)
        return 2

    vectorize(args.input, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
