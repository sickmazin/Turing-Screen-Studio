"""Widget delle pagine a layout.

Un widget nel layout è un dict: {"type": "text", "x": 16, "y": 20, "w": 200, "h": 30, ...proprietà}.
I testi possono contenere campi dei dati: "{system.cpu:.0f}%", "{media.position:mmss}", "{now:%H:%M}".
Se un campo manca (dato non ancora arrivato, sessione assente, ...) il widget non viene disegnato,
oppure mostra la sua proprietà "fallback".

Aggiungere un widget = una classe con @widget, `props` e `draw()`.
"""
import re
import time
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageOps

import ui
from ui import fit, font, human, level_color, paste_emoji

ASSETS = Path(__file__).parent / "layouts" / "assets"
MISSING = None
FIELD = re.compile(r"\{([^{}:]+)(?::([^{}]*))?\}")
COLOR_CHOICES = ["fg", "muted", "accent", "card", "bg", "good", "warn", "bad", "level", "sign"]

GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
WEATHER = [
    ((0,), "☀️", "Sereno"), ((1,), "🌤️", "Poco nuvoloso"), ((2,), "⛅", "Parz. nuvoloso"), ((3,), "☁️", "Coperto"),
    ((45, 48), "🌫️", "Nebbia"), ((51, 53, 55, 56, 57), "🌦️", "Pioviggine"),
    ((61, 63, 65, 66, 67, 80, 81, 82), "🌧️", "Pioggia"), ((71, 73, 75, 77, 85, 86), "❄️", "Neve"),
    ((95, 96, 99), "⛈️", "Temporale"),
]


def weather(code):
    for codes, icon, text in WEATHER:
        if code in codes:
            return icon, text
    return "❔", "?"


# --- dati ---------------------------------------------------------------
def get(state, path):
    """'stocks.0.price' -> valore, oppure None se manca qualcosa lungo il percorso."""
    cur = state
    for part in str(path).strip().split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, (list, tuple)) and part.lstrip("-").isdigit() and -len(cur) <= int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return MISSING
        if cur is None or cur == "":
            return MISSING
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
    return f"{secs // 86400}g {secs % 86400 // 3600}h" if secs >= 86400 else f"{secs // 3600}h {secs % 3600 // 60:02d}m"


SPECS = {
    "mmss": lambda v: f"{int(v) // 60}:{int(v) % 60:02d}",
    "hm": lambda v: f"{int(v) // 3600}h {int(v) % 3600 // 60:02d}m",
    "human": lambda v: human(float(v)),
    "bytes": lambda v: human(float(v)) + "B",
    "gb": lambda v: f"{float(v) / 2**30:.1f}",
    "meteo": lambda v: weather(v)[1],
    "giorno": lambda v: GIORNI[date.fromisoformat(str(v)).weekday()],
    "reset": _reset_in,
    "hide": lambda v: "",  # mostra il testo solo se il campo esiste
}


def fmt(value, spec):
    try:
        return SPECS[spec](value) if spec in SPECS else format(value, spec or "")
    except (ValueError, TypeError, KeyError, IndexError):
        return str(value)


def template(state, text):
    """Testo con i campi sostituiti, e il valore del primo campo (per i colori level/sign). None se manca un campo."""
    values = []

    def sub(m):
        v = get(state, m.group(1))
        values.append(v)
        return "" if v is MISSING else fmt(v, m.group(2))
    out = FIELD.sub(sub, str(text))
    if MISSING in values:
        return None, None
    return out, values[0] if values else None


def number(state, spec, default=0.0):
    """Un numero scritto (\"100\") oppure il percorso di un campo (\"media.duration\")."""
    try:
        return float(spec)
    except (TypeError, ValueError):
        v = get(state, spec)
        try:
            return float(v)
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


# --- registro -----------------------------------------------------------
WIDGETS = {}


def widget(cls):
    WIDGETS[cls.type] = cls
    return cls


class Widget:
    """props: (chiave, tipo, predefinito, etichetta). Tipi: text, int, float, bool, color, field, choice:a|b, file."""
    type = ""
    label = ""
    size = (120, 40)
    needs = ()
    props = []

    @classmethod
    def new(cls, x, y):
        return {"type": cls.type, "x": x, "y": y, "w": cls.size[0], "h": cls.size[1],
                **{k: d for k, _, d, _ in cls.props}}

    @staticmethod
    def draw(img, d, box, p, state):
        raise NotImplementedError


def prop(p, cls, key):
    return p.get(key, next(dv for k, _, dv, _ in cls.props if k == key))


@widget
class Text(Widget):
    type, label, size = "text", "Testo / valore", (200, 32)
    props = [("text", "text", "Testo", "Testo ({campo:formato})"), ("size", "int", 20, "Dimensione"),
             ("bold", "bool", False, "Grassetto"), ("color", "color", "fg", "Colore"),
             ("align", "choice:left|center|right", "left", "Allineamento"), ("fallback", "text", "", "Se mancano dati")]

    @staticmethod
    def draw(img, d, box, p, state):
        g = lambda k: prop(p, Text, k)
        text, first = template(state, g("text"))
        if text is None:
            text = g("fallback")
        if not text:
            return
        x0, y0, x1, y1 = box
        f = font(int(g("size")), bool(g("bold")))
        text = fit(d, text, f, x1 - x0)
        align = g("align")
        x, anchor = {"left": (x0, "lm"), "center": ((x0 + x1) // 2, "mm"), "right": (x1, "rm")}.get(align, (x0, "lm"))
        d.text((x, (y0 + y1) // 2), text, font=f, fill=color(g("color"), first), anchor=anchor)


@widget
class Bar(Widget):
    type, label, size = "bar", "Barra", (240, 12)
    props = [("field", "field", "system.cpu", "Valore"), ("max", "field", "100", "Massimo (numero o campo)"),
             ("color", "color", "level", "Colore"), ("bg", "color", "card", "Sfondo")]

    @staticmethod
    def draw(img, d, box, p, state):
        v = get(state, prop(p, Bar, "field"))
        if not isinstance(v, (int, float)):
            return
        mx = number(state, prop(p, Bar, "max"), 100) or 100
        pct = v / mx * 100
        ui.bar(d, box, pct, color=color(prop(p, Bar, "color"), pct), bg=color(prop(p, Bar, "bg")))


@widget
class Ring(Widget):
    type, label, size = "ring", "Anello", (140, 140)
    props = [("field", "field", "system.cpu", "Valore"), ("max", "field", "100", "Massimo (numero o campo)"),
             ("thickness", "int", 14, "Spessore"), ("color", "color", "level", "Colore"), ("bg", "color", "card", "Sfondo")]

    @staticmethod
    def draw(img, d, box, p, state):
        x0, y0, x1, y1 = box
        r = min(x1 - x0, y1 - y0) // 2
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        sq = (cx - r, cy - r, cx + r, cy + r)
        t = int(prop(p, Ring, "thickness"))
        d.arc(sq, 0, 360, fill=color(prop(p, Ring, "bg")), width=t)
        v = get(state, prop(p, Ring, "field"))
        if isinstance(v, (int, float)):
            pct = max(0.0, min(100.0, v / (number(state, prop(p, Ring, "max"), 100) or 100) * 100))
            if pct > 0:
                d.arc(sq, -90, -90 + 3.6 * pct, fill=color(prop(p, Ring, "color"), pct), width=t)


@widget
class Rect(Widget):
    type, label, size = "rect", "Riquadro", (200, 100)
    props = [("fill", "color", "card", "Colore"), ("radius", "int", 10, "Arrotondamento")]

    @staticmethod
    def draw(img, d, box, p, state):
        d.rounded_rectangle(box, int(prop(p, Rect, "radius")), fill=color(prop(p, Rect, "fill")))


@widget
class Dot(Widget):
    type, label, size = "dot", "Pallino di stato", (12, 12)
    props = [("field", "field", "claude.0.busy", "Acceso se (campo)"),
             ("on", "color", "#d97757", "Colore acceso"), ("off", "color", "good", "Colore spento")]

    @staticmethod
    def draw(img, d, box, p, state):
        field = prop(p, Dot, "field")
        on = bool(get(state, field)) if field else True
        d.ellipse(box, fill=color(prop(p, Dot, "on" if on else "off")))


@widget
class Emoji(Widget):
    type, label, size = "emoji", "Emoji", (48, 48)
    props = [("char", "text", "⭐", "Emoji")]

    @staticmethod
    def draw(img, d, box, p, state):
        x0, y0, x1, y1 = box
        paste_emoji(img, ((x0 + x1) // 2, (y0 + y1) // 2), prop(p, Emoji, "char"), max(8, min(x1 - x0, y1 - y0)))


@widget
class WeatherIcon(Widget):
    type, label, size, needs = "weather_icon", "Icona meteo", (90, 90), ("weather",)
    props = [("field", "field", "weather.code", "Codice meteo")]

    @staticmethod
    def draw(img, d, box, p, state):
        code = get(state, prop(p, WeatherIcon, "field"))
        if code is MISSING:
            return
        x0, y0, x1, y1 = box
        paste_emoji(img, ((x0 + x1) // 2, (y0 + y1) // 2), weather(code)[0], max(8, min(x1 - x0, y1 - y0)))


@lru_cache(maxsize=32)
def _asset(name, size, mode):
    im = Image.open(ASSETS / name).convert("RGBA")
    return ImageOps.fit(im, size, Image.Resampling.LANCZOS) if mode == "cover" else ImageOps.contain(im, size)


def _rounded_paste(img, im, xy, radius):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius, fill=255)
    if im.mode == "RGBA":
        mask = Image.composite(im.getchannel("A"), mask, mask)  # rispetta anche la trasparenza del PNG
    img.paste(im.convert("RGB"), xy, mask)


@widget
class Picture(Widget):
    type, label, size = "image", "Immagine", (120, 120)
    props = [("file", "file", "", "File"), ("fit", "choice:cover|contain", "cover", "Adattamento"),
             ("radius", "int", 0, "Arrotondamento")]

    @staticmethod
    def draw(img, d, box, p, state):
        name = prop(p, Picture, "file")
        if not name:
            d.rectangle(box, outline=ui.MUTED)
            return
        x0, y0, x1, y1 = box
        try:
            im = _asset(name, (x1 - x0, y1 - y0), prop(p, Picture, "fit"))
        except OSError:
            return
        _rounded_paste(img, im, (x0 + (x1 - x0 - im.width) // 2, y0 + (y1 - y0 - im.height) // 2),
                       int(prop(p, Picture, "radius")))


@widget
class Cover(Widget):
    type, label, size, needs = "cover", "Copertina brano", (220, 220), ("media",)
    props = [("radius", "int", 18, "Arrotondamento")]

    @staticmethod
    def draw(img, d, box, p, state):
        x0, y0, x1, y1 = box
        r = int(prop(p, Cover, "radius"))
        cover = get(state, "media.cover")
        if cover is MISSING:
            d.rounded_rectangle(box, r, fill=ui.CARD)
            d.text(((x0 + x1) // 2, (y0 + y1) // 2), "♪", font=font(max(10, (y1 - y0) // 3)), fill=ui.MUTED, anchor="mm")
            return
        _rounded_paste(img, ImageOps.fit(cover, (x1 - x0, y1 - y0), Image.Resampling.LANCZOS), (x0, y0), r)


@widget
class Backdrop(Widget):
    type, label, size, needs = "backdrop", "Sfondo da copertina", (320, 480), ("media",)
    props = [("blur", "int", 18, "Sfocatura"), ("dim", "float", 0.55, "Oscuramento (0-1)")]

    @staticmethod
    def draw(img, d, box, p, state):
        cover = get(state, "media.cover")
        if cover is MISSING:
            return
        x0, y0, x1, y1 = box
        bg = ImageOps.fit(cover, (x1 - x0, y1 - y0)).filter(ImageFilter.GaussianBlur(int(prop(p, Backdrop, "blur"))))
        img.paste(Image.blend(bg.convert("RGB"), Image.new("RGB", bg.size, (0, 0, 0)), float(prop(p, Backdrop, "dim"))), (x0, y0))


@widget
class Spark(Widget):
    type, label, size, needs = "sparkline", "Grafico a linea", (120, 40), ()
    props = [("field", "field", "stocks.0.series", "Serie di valori"), ("width", "int", 2, "Spessore"),
             ("color", "color", "sign", "Colore")]

    @staticmethod
    def draw(img, d, box, p, state):
        series = get(state, prop(p, Spark, "field"))
        if not isinstance(series, list) or len(series) < 2:
            return
        x0, y0, x1, y1 = box
        lo, hi = min(series), max(series)
        span = (hi - lo) or 1
        pts = [(x0 + (x1 - x0) * i / (len(series) - 1), y1 - (y1 - y0) * (v - lo) / span) for i, v in enumerate(series)]
        d.line(pts, fill=color(prop(p, Spark, "color"), series[-1] - series[0]), width=int(prop(p, Spark, "width")))


@widget
class Cores(Widget):
    type, label, size, needs = "cores", "Carico per core", (288, 60), ("system",)
    props = [("color", "color", "accent", "Colore"), ("bg", "color", "card", "Sfondo")]

    @staticmethod
    def draw(img, d, box, p, state):
        cores = get(state, "system.cores")
        if not isinstance(cores, list) or not cores:
            return
        x0, y0, x1, y1 = box
        cw = (x1 - x0) / len(cores)
        for i, c in enumerate(cores):
            x = x0 + i * cw
            d.rectangle((x + 1, y0, x + cw - 2, y1), fill=color(prop(p, Cores, "bg")))
            d.rectangle((x + 1, y1 - (y1 - y0) * c / 100, x + cw - 2, y1), fill=color(prop(p, Cores, "color")))


@widget
class Play(Widget):
    type, label, size, needs = "play", "Play / pausa", (20, 20), ("media",)
    props = [("color", "color", "fg", "Colore")]

    @staticmethod
    def draw(img, d, box, p, state):
        x0, y0, x1, y1 = box
        c = color(prop(p, Play, "color"))
        if get(state, "media.playing"):
            d.polygon([(x0, y0), (x1, (y0 + y1) / 2), (x0, y1)], fill=c)
        else:
            bw = (x1 - x0) / 3
            d.rectangle((x0, y0, x0 + bw, y1), fill=c)
            d.rectangle((x1 - bw, y0, x1, y1), fill=c)


@widget
class Ticker(Widget):
    """Riquadro di un titolo: su una riga se è basso (orizzontale), su due se è alto."""
    type, label, size, needs = "ticker", "Titolo di borsa", (296, 76), ("stocks",)
    props = [("index", "int", 0, "Numero titolo (0 = primo)"), ("radius", "int", 10, "Arrotondamento")]

    @staticmethod
    def draw(img, d, box, p, state):
        x0, y0, x1, y1 = box
        d.rounded_rectangle(box, int(prop(p, Ticker, "radius")), fill=ui.CARD)
        q = get(state, f"stocks.{int(prop(p, Ticker, 'index'))}")
        if not isinstance(q, dict):
            return
        w, h = x1 - x0, y1 - y0
        c = ui.GOOD if q["change"] >= 0 else ui.BAD
        change = f"{q['change']:+.2f}%"
        price = f"{q['price']:,.2f}"
        big, small = font(18, True), font(16)
        cw = d.textlength(change, font=big)
        if h >= 64:  # due righe: nome sopra, prezzo sotto, grafico a destra
            d.text((x0 + 12, y0 + 10), fit(d, q["symbol"], big, w // 2 - 12), font=big, fill=ui.FG)
            d.text((x0 + 12, y0 + 36), price, font=small, fill=ui.MUTED)
            spark = (x0 + w // 2, y0 + 40, x1 - 12, y1 - 10)
        else:  # una riga: nome, prezzo accanto, grafico, variazione a destra
            cy = (y0 + y1) // 2
            name = fit(d, q["symbol"], big, int(w * 0.3))
            d.text((x0 + 12, cy), name, font=big, fill=ui.FG, anchor="lm")
            px = x0 + 12 + d.textlength(name, font=big) + 10
            d.text((px, cy), price, font=small, fill=ui.MUTED, anchor="lm")
            spark = (px + d.textlength(price, font=small) + 12, y0 + 10, x1 - cw - 24, y1 - 10)
        d.text((x1 - 12, (y0 + y1) // 2) if h < 64 else (x1 - 12, y0 + 10), change, font=big, fill=c,
               anchor="rm" if h < 64 else "ra")
        if spark[2] - spark[0] > 20:
            Spark.draw(img, d, spark, {"field": f"stocks.{int(prop(p, Ticker, 'index'))}.series",
                                       "color": "good" if q["change"] >= 0 else "bad"}, state)


@widget
class Forecast(Widget):
    type, label, size, needs = "forecast", "Giorno di previsione", (70, 160), ("weather",)
    props = [("index", "int", 1, "Giorno (0 = oggi)"), ("radius", "int", 10, "Arrotondamento")]

    @staticmethod
    def draw(img, d, box, p, state):
        x0, y0, x1, y1 = box
        d.rounded_rectangle(box, int(prop(p, Forecast, "radius")), fill=ui.CARD)
        day = get(state, f"weather.days.{int(prop(p, Forecast, 'index'))}")
        if not isinstance(day, dict):
            return
        w, h = x1 - x0, y1 - y0
        cx = (x0 + x1) // 2
        name = fmt(day["date"], "giorno")
        icon = weather(day["code"])[0]
        if h >= w:  # colonna
            step = h / 6
            d.text((cx, y0 + step * 0.7), name, font=font(15, True), fill=ui.FG, anchor="mm")
            paste_emoji(img, (cx, int(y0 + step * 2)), icon, int(min(w * 0.45, step * 1.3)))
            d.text((cx, y0 + step * 3.3), f"{day['max']:.0f}°", font=font(18, True), fill=ui.FG, anchor="mm")
            d.text((cx, y0 + step * 4.2), f"{day['min']:.0f}°", font=font(15), fill=ui.MUTED, anchor="mm")
            d.text((cx, y0 + step * 5.2), f"{day['rain']}%", font=font(12), fill=ui.ACCENT, anchor="mm")
        else:  # riga
            cy = (y0 + y1) // 2
            d.text((x0 + 10, cy), name, font=font(15, True), fill=ui.FG, anchor="lm")
            paste_emoji(img, (x0 + 10 + int(w * 0.3), cy), icon, int(h * 0.6))
            d.text((x1 - 10, cy), f"{day['max']:.0f}° / {day['min']:.0f}°  {day['rain']}%", font=font(14),
                   fill=ui.FG, anchor="rm")


@widget
class Sessions(Widget):
    type, label, size, needs = "sessions", "Altre sessioni Claude", (296, 90), ("claude",)
    props = [("start", "int", 1, "Dalla sessione numero"), ("row", "int", 30, "Altezza riga")]

    @staticmethod
    def draw(img, d, box, p, state):
        x0, y0, x1, y1 = box
        sessions = get(state, "claude")
        if not isinstance(sessions, list):
            return
        row = max(16, int(prop(p, Sessions, "row")))
        y = y0
        for s in sessions[int(prop(p, Sessions, "start")):]:
            if y + row - 4 > y1:
                break
            d.rounded_rectangle((x0, y, x1, y + row - 4), 8, fill=ui.CARD)
            cy = y + (row - 4) // 2
            d.ellipse((x0 + 8, cy - 4, x0 + 16, cy + 4), fill=(217, 119, 87) if s["busy"] else ui.GOOD)
            f = font(14)
            d.text((x0 + 24, cy), fit(d, s["project"], f, x1 - x0 - 90), font=f, fill=ui.FG, anchor="lm")
            d.text((x1 - 8, cy), f"{s['context_pct']:.0f}%", font=font(14, True), fill=level_color(s["context_pct"]), anchor="rm")
            y += row


def draw_all(img, widgets, state, on_error=None):
    d = ImageDraw.Draw(img)
    for w in widgets:
        cls = WIDGETS.get(w.get("type"))
        if not cls:
            continue
        box = (int(w["x"]), int(w["y"]), int(w["x"]) + max(1, int(w["w"])), int(w["y"]) + max(1, int(w["h"])))
        try:
            cls.draw(img, d, box, w, state)
        except Exception as e:  # un widget rotto non deve far sparire la pagina
            if on_error:
                on_error(w, e)
