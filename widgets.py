"""Widgets for layout pages.

A widget in a layout is a dict: {"type": "text", "x": 16, "y": 20, "w": 200, "h": 30, ...props}.
Texts may contain data fields: "{system.cpu:.0f}%", "{media.position:mmss}", "{now:%H:%M}".
If a field is missing (data not arrived yet, no session, ...) the widget is not drawn, or it shows its
"fallback" prop. Widgets with `animated = True` make the page redraw several times per second.

Adding a widget = a class decorated with @widget, with `props` and `draw()`.
"""
import math
import re
import time
from datetime import date, datetime
from functools import lru_cache

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageOps, ImageSequence

import paths
import ui
from i18n import _, dates
from ui import fit, font, human, level_color, paste_emoji

FIELD = re.compile(r"\{([^{}:]+)(?::([^{}]*))?\}")
COLOR_CHOICES = ["fg", "muted", "accent", "card", "bg", "good", "warn", "bad", "level", "sign"]
CLAUDE_ORANGE = (217, 119, 87)
AGENT_COLORS = {"Claude": CLAUDE_ORANGE, "Codex": (16, 163, 127), "Gemini": (66, 133, 244)}

# Open-Meteo WMO codes -> (emoji, description, animation kind)
WEATHER = [
    ((0,), "☀️", "Clear", "clear"), ((1,), "🌤️", "Mostly clear", "partly"), ((2,), "⛅", "Partly cloudy", "partly"),
    ((3,), "☁️", "Overcast", "cloudy"), ((45, 48), "🌫️", "Fog", "fog"),
    ((51, 53, 55, 56, 57), "🌦️", "Drizzle", "drizzle"), ((61, 63, 65, 66, 67, 80, 81, 82), "🌧️", "Rain", "rain"),
    ((71, 73, 75, 77, 85, 86), "❄️", "Snow", "snow"), ((95, 96, 99), "⛈️", "Thunderstorm", "storm"),
]


def weather(code):
    for codes, icon, text, kind in WEATHER:
        if code in codes:
            return icon, _(text), kind
    return "❔", "?", "cloudy"


# --- data ---------------------------------------------------------------
def get(state, path):
    """'stocks.0.price' -> value, or None if anything along the path is missing."""
    cur = state
    for part in str(path).strip().split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, (list, tuple)) and part.lstrip("-").isdigit() and -len(cur) <= int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
        if cur is None or cur == "":
            return None
    return cur


def _reset_in(ts):
    try:
        if isinstance(ts, (int, float)):
            secs = ts - time.time()
        else:
            secs = (datetime.fromisoformat(str(ts).replace("Z", "+00:00")) - datetime.now().astimezone()).total_seconds()
    except (TypeError, ValueError):
        return str(ts)
    secs = max(0, int(secs))
    return f"{secs // 86400}d {secs % 86400 // 3600}h" if secs >= 86400 else f"{secs // 3600}h {secs % 3600 // 60:02d}m"


SPECS = {
    "mmss": lambda v: f"{int(v) // 60}:{int(v) % 60:02d}",
    "hm": lambda v: f"{int(v) // 3600}h {int(v) % 3600 // 60:02d}m",
    "human": lambda v: human(float(v)),
    "bytes": lambda v: human(float(v)) + "B",
    "gb": lambda v: f"{float(v) / 2**30:.1f}",
    "weather": lambda v: weather(v)[1],
    "weekday": lambda v: dates()["short"][date.fromisoformat(str(v)[:10]).weekday()],
    "reset": _reset_in,
    "hide": lambda v: "",  # shows the text only when the field exists
}
SPECS["meteo"], SPECS["giorno"] = SPECS["weather"], SPECS["weekday"]  # names used by older layouts


def fmt(value, spec):
    try:
        return SPECS[spec](value) if spec in SPECS else format(value, spec or "")
    except (ValueError, TypeError, KeyError, IndexError):
        return str(value)


def template(state, text):
    """Text with fields filled in, plus the first field's value (for level/sign colours). None if a field is missing."""
    values = []

    def sub(m):
        v = get(state, m.group(1))
        values.append(v)
        return "" if v is None else fmt(v, m.group(2))
    out = FIELD.sub(sub, _(str(text)))
    if None in values:
        return None, None
    return out, values[0] if values else None


def number(state, spec, default=0.0):
    """A literal number ("100") or a field path ("media.duration")."""
    try:
        return float(spec)
    except (TypeError, ValueError):
        try:
            return float(get(state, spec))
        except (TypeError, ValueError):
            return default


def color(spec, value=None):
    spec = str(spec or "fg")
    if spec == "level":
        return level_color(value if isinstance(value, (int, float)) else 0)
    if spec == "sign":
        return ui.GOOD if isinstance(value, (int, float)) and value >= 0 else ui.BAD
    if spec.startswith("#"):
        try:
            return ImageColor.getrgb(spec)[:3]
        except ValueError:
            return ui.FG
    return getattr(ui, spec.upper(), None) or ui.FG


def mix(a, b, k):
    return tuple(int(x * (1 - k) + y * k) for x, y in zip(a, b))


def now(state):
    return state.get("_t") or time.time()


# --- registry -----------------------------------------------------------
WIDGETS = {}


def widget(cls):
    WIDGETS[cls.type] = cls
    return cls


class Widget:
    """props: (key, kind, default, label). Kinds: text, int, float, bool, color, field, choice:a|b, file."""
    type = ""
    label = ""
    size = (120, 40)
    needs = ()
    props = []
    animated = False

    @classmethod
    def new(cls, x, y):
        return {"type": cls.type, "x": x, "y": y, "w": cls.size[0], "h": cls.size[1],
                **{k: d for k, _k, d, _l in cls.props}}

    @classmethod
    def is_animated(cls, w):
        return cls.animated

    @classmethod
    def p(cls, w, key):
        return w.get(key, next(dv for k, _k, dv, _l in cls.props if k == key))

    @staticmethod
    def draw(img, d, box, w, state):
        raise NotImplementedError


def text_at(d, box, text, f, fill, align):
    x0, y0, x1, y1 = box
    x, anchor = {"left": (x0, "lm"), "center": ((x0 + x1) // 2, "mm"), "right": (x1, "rm")}.get(align, (x0, "lm"))
    d.text((x, (y0 + y1) // 2), fit(d, text, f, x1 - x0), font=f, fill=fill, anchor=anchor)


@widget
class Text(Widget):
    type, label, size = "text", "Text / value", (200, 32)
    props = [("text", "text", "Text", "Text ({field:format})"), ("size", "int", 20, "Size"),
             ("bold", "bool", False, "Bold"), ("color", "color", "fg", "Colour"),
             ("align", "choice:left|center|right", "left", "Alignment"), ("fallback", "text", "", "When data is missing")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        text, first = template(state, cls.p(w, "text"))
        if text is None:
            text = _(cls.p(w, "fallback"))
        if text:
            text_at(d, box, text, font(int(cls.p(w, "size")), bool(cls.p(w, "bold"))),
                    color(cls.p(w, "color"), first), cls.p(w, "align"))


@lru_cache(maxsize=64)
def _text_strip(text, size, bold, fill):
    f = font(size, bold)
    strip = Image.new("RGBA", (int(f.getlength(text)) + 4, size * 2), (0, 0, 0, 0))
    ImageDraw.Draw(strip).text((0, size), text, font=f, fill=fill, anchor="lm")
    return strip


@widget
class Marquee(Widget):
    """Text that scrolls when it does not fit (long song titles, notifications)."""
    type, label, size, animated = "marquee", "Scrolling text", (240, 32), True
    props = [("text", "text", "{media.title}", "Text ({field:format})"), ("size", "int", 20, "Size"),
             ("bold", "bool", True, "Bold"), ("color", "color", "fg", "Colour"),
             ("speed", "int", 40, "Speed (px/s)"), ("align", "choice:left|center|right", "center", "Alignment when it fits"),
             ("fallback", "text", "", "When data is missing")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        text, first = template(state, cls.p(w, "text"))
        text = text if text is not None else _(cls.p(w, "fallback"))
        if not text:
            return
        size, bold = int(cls.p(w, "size")), bool(cls.p(w, "bold"))
        fill = color(cls.p(w, "color"), first)
        f = font(size, bold)
        x0, y0, x1, y1 = box
        if d.textlength(text, font=f) <= x1 - x0:
            return text_at(d, box, text, f, fill, cls.p(w, "align"))
        strip = _text_strip(text, size, bold, fill)
        period = strip.width + max(40, size * 2)
        off = int(now(state) * int(cls.p(w, "speed"))) % period
        region = img.crop(box)
        cy = (y1 - y0) // 2 - size
        region.paste(strip, (-off, cy), strip)
        region.paste(strip, (-off + period, cy), strip)
        img.paste(region, box[:2])


@widget
class Bar(Widget):
    type, label, size = "bar", "Bar", (240, 12)
    props = [("field", "field", "system.cpu", "Value"), ("max", "field", "100", "Maximum (number or field)"),
             ("color", "color", "level", "Colour"), ("bg", "color", "card", "Background")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        v = get(state, cls.p(w, "field"))
        if not isinstance(v, (int, float)):
            return
        pct = v / (number(state, cls.p(w, "max"), 100) or 100) * 100
        ui.bar(d, box, pct, color=color(cls.p(w, "color"), pct), bg=color(cls.p(w, "bg")))


@widget
class Ring(Widget):
    type, label, size = "ring", "Ring", (140, 140)
    props = [("field", "field", "system.cpu", "Value"), ("max", "field", "100", "Maximum (number or field)"),
             ("thickness", "int", 14, "Thickness"), ("color", "color", "level", "Colour"), ("bg", "color", "card", "Background")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        x0, y0, x1, y1 = box
        r = min(x1 - x0, y1 - y0) // 2
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        sq = (cx - r, cy - r, cx + r, cy + r)
        t = int(cls.p(w, "thickness"))
        d.arc(sq, 0, 360, fill=color(cls.p(w, "bg")), width=t)
        v = get(state, cls.p(w, "field"))
        if isinstance(v, (int, float)):
            pct = max(0.0, min(100.0, v / (number(state, cls.p(w, "max"), 100) or 100) * 100))
            if pct > 0:
                d.arc(sq, -90, -90 + 3.6 * pct, fill=color(cls.p(w, "color"), pct), width=t)


@widget
class Rect(Widget):
    type, label, size = "rect", "Box", (200, 100)
    props = [("fill", "color", "card", "Colour"), ("radius", "int", 10, "Corner radius")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        d.rounded_rectangle(box, int(cls.p(w, "radius")), fill=color(cls.p(w, "fill")))


@widget
class Dot(Widget):
    type, label, size = "dot", "Status dot", (12, 12)
    props = [("field", "field", "claude.0.busy", "On when (field)"),
             ("on", "color", "#d97757", "Colour when on"), ("off", "color", "good", "Colour when off")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        field = cls.p(w, "field")
        on = bool(get(state, field)) if field else True
        d.ellipse(box, fill=color(cls.p(w, "on" if on else "off")))


@widget
class Emoji(Widget):
    type, label, size = "emoji", "Emoji", (48, 48)
    props = [("char", "text", "⭐", "Emoji")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        x0, y0, x1, y1 = box
        paste_emoji(img, ((x0 + x1) // 2, (y0 + y1) // 2), cls.p(w, "char"), max(8, min(x1 - x0, y1 - y0)))


@widget
class WeatherIcon(Widget):
    type, label, size, needs = "weather_icon", "Weather icon", (90, 90), ("weather",)
    props = [("field", "field", "weather.code", "Weather code")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        code = get(state, cls.p(w, "field"))
        if code is not None:
            x0, y0, x1, y1 = box
            paste_emoji(img, ((x0 + x1) // 2, (y0 + y1) // 2), weather(code)[0], max(8, min(x1 - x0, y1 - y0)))


def _frac(i, k=0.6180339887):
    """Deterministic pseudo-random number in [0, 1) for particle i."""
    return (i * k) % 1.0


def _darker(tile, k=0.65):
    r, g, b, a = tile.split()
    return Image.merge("RGBA", (*(c.point(lambda v: int(v * k)) for c in (r, g, b)), a))


@widget
class WeatherAnim(Widget):
    """Animated weather: turning sun, drifting clouds, rain, snow, lightning, fog."""
    type, label, size, needs, animated = "weather_anim", "Animated weather", (140, 120), ("weather",), True
    props = [("field", "field", "weather.code", "Weather code"), ("intensity", "int", 24, "Drops / flakes")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        code = get(state, cls.p(w, "field"))
        if code is None:
            return
        kind = weather(code)[2]
        day = get(state, "weather.is_day") is not False
        t = now(state)
        x0, y0, x1, y1 = box
        bw, bh = x1 - x0, y1 - y0
        s = min(bw, bh)
        region = img.crop(box).convert("RGBA")
        rd = ImageDraw.Draw(region)

        def sun(cx, cy, size):
            if day:
                tile = ui.emoji_tile("☀️", int(size))
                if tile:
                    rot = tile.rotate(-(t * 25) % 360, resample=Image.Resampling.BICUBIC)
                    region.alpha_composite(rot, (int(cx - rot.width / 2), int(cy - rot.height / 2)))
                return
            for i in range(6):  # twinkling stars around the moon
                a = 0.5 + 0.5 * math.sin(t * 2 + i * 1.7)
                sx, sy = _frac(i + 1) * bw, _frac(i + 3, 0.414) * bh * 0.6
                rd.ellipse((sx - 1.5, sy - 1.5, sx + 1.5, sy + 1.5), fill=mix(ui.BG, (255, 255, 230), a) + (255,))
            tile = ui.emoji_tile("🌙", int(size * 0.8))
            if tile:
                region.alpha_composite(tile, (int(cx - tile.width / 2), int(cy - tile.height / 2)))

        def clouds(n, y, size, speed, dark=False):
            for i in range(n):
                tile = ui.emoji_tile("☁️", int(size * (0.8 + 0.3 * _frac(i + 2))))
                if not tile:
                    continue
                tile = _memo(_darker, tile) if dark else tile
                span = bw + tile.width
                x = (_frac(i) * span + t * speed * (1 + 0.3 * i)) % span - tile.width
                region.alpha_composite(tile, (int(x), int(y + i * size * 0.18 - tile.height / 2)))

        def drops(n, top, speed, length, col, flakes=False):
            fall = bh - top
            for i in range(n):
                x = _frac(i) * bw
                y = top + (_frac(i, 0.7548) * fall + t * speed * (0.8 + 0.4 * _frac(i, 0.37))) % fall
                if flakes:
                    x += math.sin(t * 1.5 + i) * 4
                    rd.ellipse((x - 2, y - 2, x + 2, y + 2), fill=col)
                else:
                    rd.line((x, y, x - 2, y + length), fill=col, width=2)

        n = int(cls.p(w, "intensity"))
        if kind == "clear":
            sun(bw / 2, bh / 2, s * 0.62)
        elif kind == "partly":
            sun(bw * 0.38, bh * 0.4, s * 0.5)
            clouds(1, bh * 0.62, s * 0.5, 6)
        elif kind == "cloudy":
            clouds(3, bh * 0.4, s * 0.5, 8)
        elif kind == "fog":
            clouds(2, bh * 0.3, s * 0.4, 5)
            for i in range(4):
                y = bh * (0.55 + i * 0.1)
                x = (t * (10 + i * 4)) % (bw * 0.5) - bw * 0.25
                rd.rounded_rectangle((x, y, x + bw * 0.9, y + 4), 2, fill=mix(ui.BG, ui.MUTED, 0.7) + (255,))
        elif kind in ("drizzle", "rain", "storm"):
            drops(n // 2 if kind == "drizzle" else n, bh * 0.35, 120, 7 if kind == "drizzle" else 11, (120, 170, 255, 255))
            clouds(2, bh * 0.25, s * 0.48, 7, dark=kind == "storm")
            if kind == "storm" and (t % 3.5) < 0.18:
                tile = ui.emoji_tile("⚡", int(s * 0.35))
                if tile:
                    region.alpha_composite(tile, (int(bw * 0.55), int(bh * 0.4)))
        elif kind == "snow":
            drops(n, bh * 0.3, 35, 0, (245, 248, 255, 255), flakes=True)
            clouds(2, bh * 0.22, s * 0.45, 5)
        img.paste(region.convert("RGB"), box[:2])


@lru_cache(maxsize=16)
def _frames(name):
    """All frames of an image file with their duration in seconds (one frame for still images)."""
    im = Image.open(paths.ASSETS / name)
    frames, durations = [], []
    for fr in ImageSequence.Iterator(im):
        frames.append(fr.convert("RGBA"))
        durations.append(max(0.02, fr.info.get("duration", 100) / 1000))
    return frames, durations


@lru_cache(maxsize=64)
def _fitted(name, index, size, mode):
    im = _frames(name)[0][index]
    return ImageOps.fit(im, size, Image.Resampling.LANCZOS) if mode == "cover" else ImageOps.contain(im, size)


def _rounded_paste(img, im, xy, radius):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius, fill=255)
    if im.mode == "RGBA":
        mask = Image.composite(im.getchannel("A"), mask, mask)  # keeps PNG transparency too
    img.paste(im.convert("RGB"), xy, mask)


@widget
class Picture(Widget):
    """Still or animated image (GIF, APNG, animated WebP: e.g. animated emoji)."""
    type, label, size = "image", "Image / animated GIF", (120, 120)
    props = [("file", "file", "", "File"), ("fit", "choice:cover|contain", "contain", "Fit"),
             ("radius", "int", 0, "Corner radius")]

    @classmethod
    def is_animated(cls, w):
        try:
            return bool(w.get("file")) and len(_frames(w["file"])[0]) > 1
        except OSError:
            return False

    @classmethod
    def draw(cls, img, d, box, w, state):
        name = cls.p(w, "file")
        if not name:
            d.rectangle(box, outline=ui.MUTED)
            return
        try:
            frames, durations = _frames(name)
        except OSError:
            return
        index = 0
        if len(frames) > 1:
            pos = now(state) % sum(durations)
            while pos >= durations[index]:
                pos -= durations[index]
                index += 1
        x0, y0, x1, y1 = box
        im = _fitted(name, index, (x1 - x0, y1 - y0), cls.p(w, "fit"))
        _rounded_paste(img, im, (x0 + (x1 - x0 - im.width) // 2, y0 + (y1 - y0 - im.height) // 2), int(cls.p(w, "radius")))


_image_cache = {}


def _memo(fn, cover, *args):
    """Cache keyed on the cover object (PIL images are not hashable); the media source keeps one per song."""
    key = (fn.__name__, id(cover), args)
    if key not in _image_cache:
        if len(_image_cache) > 16:
            _image_cache.clear()
        _image_cache[key] = (cover, fn(cover, *args))  # holding cover keeps its id from being reused
    return _image_cache[key][1]


def _cover_fit(cover, size):
    return ImageOps.fit(cover, size, Image.Resampling.LANCZOS)


def _backdrop(cover, size, blur, dim):
    bg = ImageOps.fit(cover, size).filter(ImageFilter.GaussianBlur(blur)).convert("RGB")
    return Image.blend(bg, Image.new("RGB", size, (0, 0, 0)), dim)


@widget
class Cover(Widget):
    type, label, size, needs = "cover", "Song cover", (220, 220), ("media",)
    props = [("radius", "int", 18, "Corner radius")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        x0, y0, x1, y1 = box
        r = int(cls.p(w, "radius"))
        cover = get(state, "media.cover")
        if cover is None:
            d.rounded_rectangle(box, r, fill=ui.CARD)
            d.text(((x0 + x1) // 2, (y0 + y1) // 2), "♪", font=font(max(10, (y1 - y0) // 3)), fill=ui.MUTED, anchor="mm")
            return
        _rounded_paste(img, _memo(_cover_fit, cover, (x1 - x0, y1 - y0)), (x0, y0), r)


@widget
class Backdrop(Widget):
    type, label, size, needs = "backdrop", "Background from cover", (320, 480), ("media",)
    props = [("blur", "int", 18, "Blur"), ("dim", "float", 0.55, "Darken (0-1)")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        cover = get(state, "media.cover")
        if cover is not None:
            x0, y0, x1, y1 = box
            img.paste(_memo(_backdrop, cover, (x1 - x0, y1 - y0), int(cls.p(w, "blur")), float(cls.p(w, "dim"))), (x0, y0))


def polyline(d, box, series, col, width, fill=None, lo=None, hi=None):
    x0, y0, x1, y1 = box
    lo = min(series) if lo is None else lo
    hi = max(series) if hi is None else hi
    span = (hi - lo) or 1
    pts = [(x0 + (x1 - x0) * i / (len(series) - 1), y1 - (y1 - y0) * (min(max(v, lo), hi) - lo) / span)
           for i, v in enumerate(series)]
    if fill:
        d.polygon([(x0, y1), *pts, (x1, y1)], fill=fill)
    d.line(pts, fill=col, width=width)


@widget
class Spark(Widget):
    type, label, size = "sparkline", "Line chart", (120, 40)
    props = [("field", "field", "stocks.0.series", "Series of values"), ("width", "int", 2, "Thickness"),
             ("color", "color", "sign", "Colour")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        series = get(state, cls.p(w, "field"))
        if isinstance(series, list) and len(series) >= 2:
            polyline(d, box, series, color(cls.p(w, "color"), series[-1] - series[0]), int(cls.p(w, "width")))


@widget
class History(Widget):
    """Chart of how a value changed in the last N seconds (recorded while the app runs)."""
    type, label, size = "history", "History chart", (288, 70)
    props = [("field", "field", "system.cpu", "Value"), ("seconds", "int", 120, "Time span (s)"),
             ("min", "text", "0", "Minimum (empty = auto)"), ("max", "text", "100", "Maximum (empty = auto)"),
             ("color", "color", "accent", "Colour"), ("fill", "bool", True, "Fill below"), ("bg", "color", "card", "Background")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        if cls.p(w, "bg"):
            d.rounded_rectangle(box, 6, fill=color(cls.p(w, "bg")))
        samples = (state.get("_history") or {}).get(str(cls.p(w, "field")).strip()) or []
        horizon = now(state) - int(cls.p(w, "seconds"))
        values = [v for t, v in samples if t >= horizon]
        if len(values) < 2:
            return
        try:
            lo = float(cls.p(w, "min")) if str(cls.p(w, "min")).strip() else None
            hi = float(cls.p(w, "max")) if str(cls.p(w, "max")).strip() else None
        except ValueError:
            lo = hi = None
        col = color(cls.p(w, "color"), values[-1])
        x0, y0, x1, y1 = box
        polyline(d, (x0 + 2, y0 + 4, x1 - 2, y1 - 2), values, col, 2,
                 fill=mix(ui.BG, col, 0.3) if cls.p(w, "fill") else None, lo=lo, hi=hi)


@widget
class Cores(Widget):
    type, label, size, needs = "cores", "Per-core load", (288, 60), ("system",)
    props = [("color", "color", "accent", "Colour"), ("bg", "color", "card", "Background")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        cores = get(state, "system.cores")
        if not isinstance(cores, list) or not cores:
            return
        x0, y0, x1, y1 = box
        cw = (x1 - x0) / len(cores)
        for i, c in enumerate(cores):
            x = x0 + i * cw
            d.rectangle((x + 1, y0, x + cw - 2, y1), fill=color(cls.p(w, "bg")))
            d.rectangle((x + 1, y1 - (y1 - y0) * c / 100, x + cw - 2, y1), fill=color(cls.p(w, "color")))


@widget
class Play(Widget):
    type, label, size, needs = "play", "Play / pause", (20, 20), ("media",)
    props = [("color", "color", "fg", "Colour")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        x0, y0, x1, y1 = box
        c = color(cls.p(w, "color"))
        if get(state, "media.playing"):
            d.polygon([(x0, y0), (x1, (y0 + y1) / 2), (x0, y1)], fill=c)
        else:
            bw = (x1 - x0) / 3
            d.rectangle((x0, y0, x0 + bw, y1), fill=c)
            d.rectangle((x1 - bw, y0, x1, y1), fill=c)


@widget
class Ticker(Widget):
    """Card for one stock: one line when short (landscape), two lines when tall."""
    type, label, size, needs = "ticker", "Stock", (296, 76), ("stocks",)
    props = [("index", "int", 0, "Stock number (0 = first)"), ("radius", "int", 10, "Corner radius")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        x0, y0, x1, y1 = box
        d.rounded_rectangle(box, int(cls.p(w, "radius")), fill=ui.CARD)
        q = get(state, f"stocks.{int(cls.p(w, 'index'))}")
        if not isinstance(q, dict):
            return
        width, height = x1 - x0, y1 - y0
        c = ui.GOOD if q["change"] >= 0 else ui.BAD
        change, price = f"{q['change']:+.2f}%", f"{q['price']:,.2f}"
        big, small = font(18, True), font(16)
        cw = d.textlength(change, font=big)
        if height >= 64:  # two lines: name above price, chart on the right
            d.text((x0 + 12, y0 + 10), fit(d, q["symbol"], big, width // 2 - 12), font=big, fill=ui.FG)
            d.text((x0 + 12, y0 + 36), price, font=small, fill=ui.MUTED)
            d.text((x1 - 12, y0 + 10), change, font=big, fill=c, anchor="ra")
            spark = (x0 + width // 2, y0 + 40, x1 - 12, y1 - 10)
        else:  # one line: name, price next to it, chart, change on the right
            cy = (y0 + y1) // 2
            name = fit(d, q["symbol"], big, int(width * 0.3))
            d.text((x0 + 12, cy), name, font=big, fill=ui.FG, anchor="lm")
            px = x0 + 12 + d.textlength(name, font=big) + 10
            d.text((px, cy), price, font=small, fill=ui.MUTED, anchor="lm")
            d.text((x1 - 12, cy), change, font=big, fill=c, anchor="rm")
            spark = (px + d.textlength(price, font=small) + 12, y0 + 10, x1 - cw - 24, y1 - 10)
        if spark[2] - spark[0] > 20 and len(q.get("series") or []) >= 2:
            polyline(d, spark, q["series"], c, 2)


@widget
class Forecast(Widget):
    type, label, size, needs = "forecast", "Forecast day", (70, 160), ("weather",)
    props = [("index", "int", 1, "Day (0 = today)"), ("radius", "int", 10, "Corner radius")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        x0, y0, x1, y1 = box
        d.rounded_rectangle(box, int(cls.p(w, "radius")), fill=ui.CARD)
        day = get(state, f"weather.days.{int(cls.p(w, 'index'))}")
        if not isinstance(day, dict):
            return
        width, height = x1 - x0, y1 - y0
        cx = (x0 + x1) // 2
        name, icon = fmt(day["date"], "weekday"), weather(day["code"])[0]
        if height >= width:  # column
            step = height / 6
            d.text((cx, y0 + step * 0.7), name, font=font(15, True), fill=ui.FG, anchor="mm")
            paste_emoji(img, (cx, int(y0 + step * 2)), icon, int(min(width * 0.45, step * 1.3)))
            d.text((cx, y0 + step * 3.3), f"{day['max']:.0f}°", font=font(18, True), fill=ui.FG, anchor="mm")
            d.text((cx, y0 + step * 4.2), f"{day['min']:.0f}°", font=font(15), fill=ui.MUTED, anchor="mm")
            d.text((cx, y0 + step * 5.2), f"{day['rain']}%", font=font(12), fill=ui.ACCENT, anchor="mm")
        else:  # row
            cy = (y0 + y1) // 2
            d.text((x0 + 10, cy), name, font=font(15, True), fill=ui.FG, anchor="lm")
            paste_emoji(img, (x0 + 10 + int(width * 0.3), cy), icon, int(height * 0.6))
            d.text((x1 - 10, cy), f"{day['max']:.0f}° / {day['min']:.0f}°  {day['rain']}%", font=font(14),
                   fill=ui.FG, anchor="rm")


def rows(d, box, items, row, draw_row, empty=""):
    """Draw a vertical list of cards, as many as fit in the box."""
    x0, y0, x1, y1 = box
    if not items:
        if empty:
            d.text(((x0 + x1) // 2, (y0 + y1) // 2), _(empty), font=font(14), fill=ui.MUTED, anchor="mm")
        return
    y = y0
    for item in items:
        if y + row - 4 > y1:
            break
        d.rounded_rectangle((x0, y, x1, y + row - 4), 8, fill=ui.CARD)
        draw_row((x0, y, x1, y + row - 4), item)
        y += row


@widget
class Sessions(Widget):
    type, label, size, needs = "sessions", "Other Claude sessions", (296, 90), ("claude",)
    props = [("start", "int", 1, "From session number"), ("row", "int", 30, "Row height")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        sessions = get(state, "claude")
        if not isinstance(sessions, list):
            return

        def one(b, s):
            x0, y0, x1, y1 = b
            cy = (y0 + y1) // 2
            d.ellipse((x0 + 8, cy - 4, x0 + 16, cy + 4), fill=CLAUDE_ORANGE if s["busy"] else ui.GOOD)
            d.text((x0 + 24, cy), fit(d, s["project"], font(14), x1 - x0 - 90), font=font(14), fill=ui.FG, anchor="lm")
            d.text((x1 - 8, cy), f"{s['context_pct']:.0f}%", font=font(14, True), fill=level_color(s["context_pct"]), anchor="rm")
        rows(d, box, sessions[int(cls.p(w, "start")):], max(16, int(cls.p(w, "row"))), one)


@widget
class Agents(Widget):
    """Terminal agents (Claude Code, Codex, Gemini CLI): one row per active session."""
    type, label, size, needs = "agents", "Agent sessions", (296, 200), ("agents",)
    props = [("start", "int", 0, "From session number"), ("row", "int", 46, "Row height")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        def one(b, s):
            x0, y0, x1, y1 = b
            d.rounded_rectangle((x0, y0, x0 + 5, y1), 2, fill=AGENT_COLORS.get(s["agent"], ui.ACCENT))
            two = y1 - y0 >= 38
            top = y0 + (y1 - y0) // 2 - (9 if two else 0)
            d.ellipse((x0 + 12, top - 4, x0 + 20, top + 4), fill=CLAUDE_ORANGE if s["busy"] else ui.GOOD)
            d.text((x0 + 28, top), fit(d, f"{s['agent']} · {s['project']}", font(15, True), x1 - x0 - 96),
                   font=font(15, True), fill=ui.FG, anchor="lm")
            d.text((x1 - 10, top), f"{s['context_pct']:.0f}%", font=font(15, True), fill=level_color(s["context_pct"]), anchor="rm")
            if two:
                extra = s["model"]
                if s.get("limit_pct") is not None:
                    extra += f"  ·  limit {s['limit_pct']:.0f}%"
                d.text((x0 + 28, top + 18), fit(d, extra, font(12), x1 - x0 - 40), font=font(12), fill=ui.MUTED, anchor="lm")
        agents = get(state, "agents")
        rows(d, box, (agents if isinstance(agents, list) else [])[int(cls.p(w, "start")):], max(20, int(cls.p(w, "row"))),
             one, empty="No agents running" if isinstance(agents, list) else "")


@widget
class Agenda(Widget):
    type, label, size, needs = "agenda", "Calendar events", (296, 220), ("calendar",)
    props = [("start", "int", 0, "From event number"), ("row", "int", 46, "Row height")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        def one(b, e):
            x0, y0, x1, y1 = b
            d.rounded_rectangle((x0, y0, x0 + 5, y1), 2, fill=ui.ACCENT)
            cy = (y0 + y1) // 2
            if y1 - y0 >= 38:
                d.text((x0 + 14, cy - 9), fit(d, e["title"], font(15, True), x1 - x0 - 24), font=font(15, True), fill=ui.FG, anchor="lm")
                d.text((x0 + 14, cy + 10), e["when"], font=font(12), fill=ui.MUTED, anchor="lm")
            else:
                when = d.textlength(e["when"], font=font(12))
                d.text((x0 + 14, cy), fit(d, e["title"], font(14, True), int(x1 - x0 - when - 34)), font=font(14, True),
                       fill=ui.FG, anchor="lm")
                d.text((x1 - 10, cy), e["when"], font=font(12), fill=ui.MUTED, anchor="rm")
        events = get(state, "calendar")
        rows(d, box, (events if isinstance(events, list) else [])[int(cls.p(w, "start")):],
             max(20, int(cls.p(w, "row"))), one, empty="No upcoming events" if isinstance(events, list) else "")


@widget
class Notifications(Widget):
    type, label, size, needs = "notifications", "Windows notifications", (296, 220), ("notifications",)
    props = [("row", "int", 54, "Row height")]

    @classmethod
    def draw(cls, img, d, box, w, state):
        def one(b, n):
            x0, y0, x1, y1 = b
            cy = (y0 + y1) // 2
            d.text((x0 + 10, y0 + 6), fit(d, n["app"], font(11), x1 - x0 - 70), font=font(11), fill=ui.MUTED)
            d.text((x1 - 10, y0 + 6), n["time"], font=font(11), fill=ui.MUTED, anchor="ra")
            d.text((x0 + 10, cy + 2), fit(d, n["title"], font(14, True), x1 - x0 - 20), font=font(14, True), fill=ui.FG)
            if y1 - y0 >= 50 and n["body"]:
                d.text((x0 + 10, cy + 18), fit(d, n["body"], font(12), x1 - x0 - 20), font=font(12), fill=ui.MUTED)
        items = get(state, "notifications")
        rows(d, box, items if isinstance(items, list) else [], max(24, int(cls.p(w, "row"))), one,
             empty="No notifications" if isinstance(items, list) else "")


def draw_all(img, widgets, state, on_error=None):
    d = ImageDraw.Draw(img)
    for w in widgets:
        cls = WIDGETS.get(w.get("type"))
        if not cls:
            continue
        box = (int(w["x"]), int(w["y"]), int(w["x"]) + max(1, int(w["w"])), int(w["y"]) + max(1, int(w["h"])))
        try:
            cls.draw(img, d, box, w, state)
        except Exception as e:  # one broken widget must not blank the page
            if on_error:
                on_error(w, e)
