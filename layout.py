"""Pagine a layout: layouts/<id>.json = {"name": ..., "portrait": [widget...], "landscape": [widget...]}.

Si creano e modificano dall'editor in settings.py; main.py le ricarica dal vivo.
"""
import copy
import json
import logging
from datetime import datetime
from pathlib import Path

import ui
from widgets import FIELD, WIDGETS, draw_all

LAYOUTS = Path(__file__).parent / "layouts"
SIZES = {"portrait": (320, 480), "landscape": (480, 320)}
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
SCALED_PROPS = ("size", "thickness", "radius", "row")
log = logging.getLogger("schermetto")


def orientation_of(size):
    return "landscape" if size[0] > size[1] else "portrait"


def scale_widgets(widgets, src: str, dst: str):
    """Punto di partenza per l'altro orientamento: posizioni stirate, testi scalati in modo uniforme."""
    (sw, sh), (dw, dh) = SIZES[src], SIZES[dst]
    fx, fy = dw / sw, dh / sh
    k = min(fx, fy)
    out = []
    for w in copy.deepcopy(widgets):
        w["x"], w["w"] = round(w["x"] * fx), max(4, round(w["w"] * fx))
        w["y"], w["h"] = round(w["y"] * fy), max(4, round(w["h"] * fy))
        for p in SCALED_PROPS:
            if isinstance(w.get(p), (int, float)):
                w[p] = max(1, round(w[p] * k))
        out.append(w)
    return out


def with_clock(state):
    now = datetime.now()
    return {**state, "now": now,
            "date": {"weekday": GIORNI[now.weekday()], "day": now.day, "month": MESI[now.month - 1], "year": now.year}}


class LayoutPage:
    """Si comporta come un modulo di pages/: name, needs, settings, render()."""
    settings = {}

    def __init__(self, page_id: str, data: dict):
        self.name, self.data = page_id, data
        self.title = data.get("name", page_id)
        needs = set()
        for o in SIZES:
            for w in data.get(o) or []:
                cls = WIDGETS.get(w.get("type"))
                needs.update(cls.needs if cls else ())
                for k, v in w.items():
                    if isinstance(v, str):
                        paths = [m.group(1) for m in FIELD.finditer(v)] + ([v] if k in ("field", "max") else [])
                        needs.update(p.strip().split(".")[0] for p in paths)
        self.needs = sorted(needs)

    def widgets_for(self, size):
        o = orientation_of(size)
        if self.data.get(o):
            return self.data[o]
        other = "portrait" if o == "landscape" else "landscape"
        return scale_widgets(self.data.get(other) or [], other, o)

    def render(self, state, size, cfg):
        img = ui.canvas(size, self.name)
        draw_all(img, self.widgets_for(size), with_clock(state),
                 on_error=lambda w, e: log.warning("widget %s in %s: %r", w.get("type"), self.name, e))
        return img


def load_layouts() -> dict:
    out = {}
    for f in sorted(LAYOUTS.glob("*.json")):
        try:
            out[f.stem] = LayoutPage(f.stem, json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            log.warning("layout %s non valido: %s", f.name, e)
    return out


def save_layout(page_id: str, data: dict):
    LAYOUTS.mkdir(exist_ok=True)
    tmp = LAYOUTS / f"{page_id}.json.tmp"
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LAYOUTS / f"{page_id}.json")


def stamp():
    """Cambia quando un layout viene salvato, creato o eliminato."""
    files = list(LAYOUTS.glob("*.json"))
    return len(files), max((f.stat().st_mtime for f in files), default=0)
