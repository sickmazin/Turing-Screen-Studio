"""Layout pages: layouts/<id>.json = {"name": ..., "portrait": [widget...], "landscape": [widget...]}.

They are created and edited in the settings window; the screen app reloads them live.
"""
import copy
import json
import logging
import time
import zipfile
from collections import deque
from datetime import datetime
from pathlib import Path

import paths
import ui
from i18n import _, dates
from widgets import FIELD, WIDGETS, draw_all

PAGE_EXT = ".tss-page"
SIZES = {"portrait": (320, 480), "landscape": (480, 320)}
SCALED_PROPS = ("size", "thickness", "radius", "row")
log = logging.getLogger("studio")


def orientation_of(size):
    return "landscape" if size[0] > size[1] else "portrait"


def scale_widgets(widgets, src: str, dst: str):
    """Starting point for the other orientation: positions stretched, text scaled uniformly."""
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


def with_clock(state, history=None):
    """Data for rendering: sources + current time, date words in the UI language and value history."""
    now = datetime.now()
    names = dates()
    return {**state, "now": now, "_t": time.time(), "_history": history or {},
            "date": {"weekday": names["weekdays"][now.weekday()], "day": now.day,
                     "month": names["months"][now.month - 1], "year": now.year}}


class LayoutPage:
    """Behaves like a pages/ module: name, needs, settings, render()."""
    settings = {}

    def __init__(self, page_id: str, data: dict):
        self.name, self.data = page_id, data
        needs, history = set(), set()
        for o in SIZES:
            for w in data.get(o) or []:
                cls = WIDGETS.get(w.get("type"))
                needs.update(cls.needs if cls else ())
                for k, v in w.items():
                    if isinstance(v, str):
                        found = [m.group(1) for m in FIELD.finditer(v)] + ([v] if k in ("field", "max") else [])
                        needs.update(p.strip().split(".")[0] for p in found)
                if w.get("type") == "history" and w.get("field"):
                    history.add(w["field"].strip())
        self.needs = sorted(needs)
        self.history_fields = history

    @property
    def title(self):
        return _(self.data.get("name", self.name))

    def widgets_for(self, size):
        o = orientation_of(size)
        if self.data.get(o):
            return self.data[o]
        other = "portrait" if o == "landscape" else "landscape"
        return scale_widgets(self.data.get(other) or [], other, o)

    def animated(self, size) -> bool:
        return any(WIDGETS[w["type"]].is_animated(w) for w in self.widgets_for(size) if w.get("type") in WIDGETS)

    def render(self, state, size, cfg, history=None):
        img = ui.canvas(size, self.name)
        draw_all(img, self.widgets_for(size), with_clock(state, history),
                 on_error=lambda w, e: log.warning("widget %s in %s: %r", w.get("type"), self.name, e))
        return img


class HistoryRecorder:
    """Keeps the last hour of every numeric field used by a history widget, one sample per call."""

    def __init__(self, seconds=3600):
        self.data, self.maxlen = {}, seconds

    def record(self, pages, state):
        from widgets import get
        t = time.time()
        for page in pages:
            for field in getattr(page, "history_fields", ()):
                v = get(state, field)
                if isinstance(v, (int, float)):
                    self.data.setdefault(field, deque(maxlen=self.maxlen)).append((t, float(v)))
        return {k: list(v) for k, v in self.data.items()}


def load_layouts() -> dict:
    out = {}
    for f in sorted(paths.LAYOUTS.glob("*.json")):
        try:
            out[f.stem] = LayoutPage(f.stem, json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:
            log.warning("invalid layout %s: %s", f.name, e)
    return out


def save_layout(page_id: str, data: dict):
    paths.LAYOUTS.mkdir(parents=True, exist_ok=True)
    tmp = paths.LAYOUTS / f"{page_id}.json.tmp"
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(paths.LAYOUTS / f"{page_id}.json")


def stamp():
    """Changes when a layout is saved, created or deleted."""
    files = list(paths.LAYOUTS.glob("*.json"))
    return len(files), max((f.stat().st_mtime for f in files), default=0)


def page_assets(data):
    return sorted({w["file"] for o in SIZES for w in data.get(o) or [] if w.get("type") == "image" and w.get("file")})


def export_page(page_id: str, dest: Path):
    data = json.loads((paths.LAYOUTS / f"{page_id}.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("page.json", json.dumps(data, indent=1, ensure_ascii=False))
        for name in page_assets(data):
            if (paths.ASSETS / name).is_file():
                z.write(paths.ASSETS / name, name)


def import_page(src: Path, existing) -> str:
    """Import a .tss-page from someone else: same checks as themes, images go to the shared assets folder."""
    with zipfile.ZipFile(src) as z:
        if "page.json" not in z.namelist():
            raise ValueError("page.json missing")
        data = json.loads(z.read("page.json"))
        if not isinstance(data, dict) or not all(isinstance(data.get(o, []), list) for o in SIZES):
            raise ValueError("invalid page.json")
        for o in SIZES:
            data[o] = [w for w in data.get(o, []) if isinstance(w, dict) and w.get("type") in WIDGETS
                       and all(isinstance(w.get(k), (int, float)) for k in ("x", "y", "w", "h"))]
        for w in (w for o in SIZES for w in data[o] if w.get("type") == "image"):
            w["file"] = Path(str(w.get("file", ""))).name  # no paths outside the assets folder
        ui.safe_extract(z, paths.ASSETS, skip={"page.json"})
    base = "".join(c for c in Path(src).stem.lower() if c.isalnum() or c in "-_") or "page"
    page_id, n = base, 2
    while page_id in existing:
        page_id, n = f"{base}{n}", n + 1
    save_layout(page_id, data)
    return page_id
