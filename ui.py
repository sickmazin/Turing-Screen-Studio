"""Active theme and drawing helpers shared by pages and widgets.

Pages read colours as ui.BG, ui.FG, ... at render time, so a theme change applies immediately.
A theme is a folder themes/<id>/ holding theme.json plus optional images and fonts; it is shared as a
.tss-theme file (a flat zip of that folder).
"""
import copy
import json
import zipfile
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

import paths

THEME_EXT = ".tss-theme"
COLOR_KEYS = ["bg", "card", "fg", "muted", "accent", "good", "warn", "bad"]
DEFAULT_THEME = {
    "name": "Dark",
    "colors": {"bg": "#0c0e14", "card": "#1c202c", "fg": "#ebeef5", "muted": "#8c94a5",
               "accent": "#6eaaff", "good": "#50d282", "warn": "#fabe46", "bad": "#f05a5a"},
    "font": {"regular": "segoeui.ttf", "bold": "segoeuib.ttf", "scale": 1.0},
    "backgrounds": {},        # page id -> image file inside the theme folder
    "background_dim": 0.55,   # how much to darken backgrounds (0 = full image, 1 = plain colour)
}
MAX_IMPORT = 50 * 2**20

BG = CARD = FG = MUTED = ACCENT = GOOD = WARN = BAD = None
theme, theme_dir = DEFAULT_THEME, paths.THEMES


def merge_defaults(t: dict) -> dict:
    out = copy.deepcopy(DEFAULT_THEME)
    for k, v in t.items():
        out[k] = {**out[k], **v} if isinstance(out.get(k), dict) and isinstance(v, dict) else v
    return out


def apply_theme(t: dict, folder: Path):
    global theme, theme_dir, BG, CARD, FG, MUTED, ACCENT, GOOD, WARN, BAD
    theme, theme_dir = merge_defaults(t), Path(folder)
    rgb = {}
    for k in COLOR_KEYS:
        try:
            rgb[k] = ImageColor.getrgb(theme["colors"][k])[:3]
        except ValueError:
            rgb[k] = ImageColor.getrgb(DEFAULT_THEME["colors"][k])
    BG, CARD, FG, MUTED, ACCENT, GOOD, WARN, BAD = (rgb[k] for k in COLOR_KEYS)
    font.cache_clear()
    _background.cache_clear()


def list_themes() -> dict:
    """Theme folder id -> display name."""
    out = {}
    for f in sorted(paths.THEMES.glob("*/theme.json")):
        try:
            out[f.parent.name] = json.loads(f.read_text(encoding="utf-8")).get("name", f.parent.name)
        except ValueError:
            pass
    return out


def read_theme(theme_id: str) -> dict:
    return merge_defaults(json.loads((paths.THEMES / theme_id / "theme.json").read_text(encoding="utf-8")))


def save_theme(theme_id: str, t: dict):
    folder = paths.THEMES / theme_id
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "theme.json.tmp"
    tmp.write_text(json.dumps(t, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(folder / "theme.json")


def load_theme(theme_id: str):
    try:
        apply_theme(read_theme(theme_id), paths.THEMES / theme_id)
    except (OSError, ValueError):
        apply_theme(DEFAULT_THEME, paths.THEMES)


def export_theme(theme_id: str, dest: Path):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in (paths.THEMES / theme_id).iterdir():
            if f.is_file():
                z.write(f, f.name)


def unique_dir(parent: Path, base: str) -> Path:
    base = "".join(c for c in base if c.isalnum() or c in "-_ ").strip() or "item"
    folder, n = parent / base, 2
    while folder.exists():
        folder, n = parent / f"{base} {n}", n + 1
    return folder


def safe_extract(z: zipfile.ZipFile, dest: Path, skip=()):
    """Extract a zip that came from someone else: flat files only, no paths, limited size."""
    files = [i for i in z.infolist() if not i.is_dir()]
    if sum(i.file_size for i in files) > MAX_IMPORT:
        raise ValueError("file too large (max 50 MB)")
    dest.mkdir(parents=True, exist_ok=True)
    for i in files:
        name = Path(i.filename).name  # drops any folder or ".." in the name
        if name and not name.startswith(".") and name not in skip:
            (dest / name).write_bytes(z.read(i))


def import_theme(src: Path) -> str:
    with zipfile.ZipFile(src) as z:
        if "theme.json" not in z.namelist():
            raise ValueError("theme.json missing")
        t = json.loads(z.read("theme.json"))
        if not isinstance(t, dict):
            raise ValueError("invalid theme.json")
        folder = unique_dir(paths.THEMES, Path(src).stem)
        safe_extract(z, folder)
    return folder.name


def _font_path(name: str):
    local = theme_dir / name
    return str(local) if local.is_file() else name  # file in the theme, otherwise a system font


@lru_cache(maxsize=None)
def font(size: int, bold=False):
    f = theme["font"]
    px = max(6, round(size * float(f.get("scale", 1.0))))
    for name in (f["bold" if bold else "regular"], "segoeuib.ttf" if bold else "segoeui.ttf"):
        try:
            return ImageFont.truetype(_font_path(name), px)
        except OSError:
            continue
    return ImageFont.load_default(px)


@lru_cache(maxsize=None)
def emoji(size: int):
    """Windows colour emoji font: use with d.text(..., embedded_color=True)."""
    return ImageFont.truetype("seguiemj.ttf", size)


@lru_cache(maxsize=256)
def emoji_tile(char: str, size: int):
    """Emoji rendered once and cropped to its pixels (Pillow's anchor is wrong for colour glyphs)."""
    tile = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((size // 2, size // 2), char, font=emoji(size), embedded_color=True)
    box = tile.getbbox()
    return tile.crop(box) if box else None


def paste_emoji(img, center, char: str, size: int):
    tile = emoji_tile(char, max(4, int(size)))
    if tile:
        img.paste(tile, (int(center[0]) - tile.width // 2, int(center[1]) - tile.height // 2), tile)


@lru_cache(maxsize=32)
def _background(size, page: str):
    name = theme["backgrounds"].get(page)
    solid = Image.new("RGB", size, BG)
    if not name:
        return solid
    try:
        img = ImageOps.fit(Image.open(theme_dir / name).convert("RGB"), size, Image.Resampling.LANCZOS)
    except OSError:
        return solid
    return Image.blend(img, solid, float(theme.get("background_dim", 0.55)))


def canvas(size, page: str) -> Image.Image:
    """Starting image of a page: theme background colour or image."""
    return _background(tuple(size), page).copy()


def level_color(pct: float):
    return GOOD if pct < 60 else WARN if pct < 85 else BAD


def bar(d: ImageDraw.ImageDraw, xy, pct: float, color=None, bg=None):
    x0, y0, x1, y1 = xy
    r = (y1 - y0) // 2
    d.rounded_rectangle(xy, r, fill=bg or CARD)
    w = int((x1 - x0) * max(0.0, min(pct, 100.0)) / 100)
    if w > 2 * r:
        d.rounded_rectangle((x0, y0, x0 + w, y1), r, fill=color or level_color(pct))


def fit(d: ImageDraw.ImageDraw, text: str, f, max_w: int) -> str:
    """Truncate text with an ellipsis so it fits in max_w pixels."""
    text = str(text)
    if d.textlength(text, font=f) <= max_w:
        return text
    while text and d.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return text + "…"


def human(n: float) -> str:
    for unit in ("", "k", "M", "B"):
        if abs(n) < 1000:
            return f"{n:.0f}{unit}" if unit == "" or n >= 100 else f"{n:.1f}{unit}"
        n /= 1000
    return f"{n:.1f}T"


apply_theme(DEFAULT_THEME, paths.THEMES)
