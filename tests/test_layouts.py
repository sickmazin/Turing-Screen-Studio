"""Every bundled layout must render cleanly in both orientations with realistic data:
no widget errors, every widget inside the screen, no truncated text."""
import json
import unittest
from datetime import date, timedelta

from PIL import Image, ImageDraw

import i18n
import layout
import paths
import ui
from widgets import FIELD, WIDGETS, Text, font, template

DEFAULTS = paths.DEFAULTS / "layouts"
# free text of any length: an ellipsis is the expected behaviour, numbers and labels must fit
FREE_TEXT = ("name", "project", "title", "artist", "album", "city", "model", "model_name")


def sample_state():
    today = date.today()
    cover = Image.linear_gradient("L").resize((300, 300)).convert("RGB")
    session = {"project": "turing-screen-studio", "model_name": "Opus 5.5", "context": 218_000, "window": 1_000_000,
               "context_pct": 21.8, "output_tokens": 126_000, "turns": 12, "cost": 12.34, "busy": True, "age": 3,
               "rate_limits": {"five_hour": {"used_percentage": 42, "resets_at": 1999999999},
                               "seven_day": {"used_percentage": 64, "resets_at": 1999999999}}}
    return {
        "system": {"cpu": 100, "cores": [10.0] * 24, "ram": 100, "ram_used": 31.9 * 2**30, "ram_total": 31.9 * 2**30,
                   "disk": 100, "down": 999e6, "up": 999e6, "uptime": 99 * 3600 + 59 * 60},
        "hardware": {"cpu": {"name": "AMD Ryzen 9 7900X", "load": 100, "temp": 95, "power": 230, "clock": 5600},
                     "gpu": {"name": "NVIDIA GeForce RTX 4070 SUPER", "load": 100, "temp": 85, "hotspot": 99, "power": 220,
                             "clock": 2800, "vram_used": 12000, "vram_total": 12282, "mem_load": 90}},
        "media": {"title": "Bohemian Rhapsody", "artist": "Queen", "album": "A Night at the Opera",
                  "position": 3599, "duration": 3599, "playing": True, "cover": cover},
        "claude": [session, dict(session, project="another-project", busy=False)],
        "agents": [{"agent": "Claude", "project": "turing-screen-studio", "model": "claude-opus-5-5", "context_pct": 21.8,
                    "busy": True, "limit_pct": 42}, {"agent": "Codex", "project": "Blockchain-GNN", "model": "gpt-6-luna",
                                                     "context_pct": 40.5, "busy": False, "limit_pct": 72}],
        "weather": {"city": "Milano", "temp": -10, "feels": -14, "humidity": 100, "wind": 120, "code": 95, "is_day": True,
                    "days": [{"date": str(today + timedelta(days=i)), "code": 61, "max": -10, "min": -20, "rain": 100}
                             for i in range(5)]},
        "stocks": [{"symbol": s, "price": 74_333.65, "prev": 70_000, "change": -12.34, "currency": "USD",
                    "series": [1, 3, 2, 5, 4]} for s in ("AAPL", "NVDA", "MSFT", "BTC-USD", "^GSPC")],
        "calendar": [{"title": "Riunione di progetto", "when": "Domani 14:30"}] * 3,
        "notifications": [{"app": "Telegram", "title": "Mario", "body": "Ci vediamo alle otto?", "time": "18:42"}] * 3,
    }


class DefaultLayouts(unittest.TestCase):
    def setUp(self):
        ui.load_theme("dark")
        self.state = sample_state()
        self.files = sorted(DEFAULTS.glob("*.json"))
        self.assertTrue(self.files)

    def each(self):
        for f in self.files:
            data = json.loads(f.read_text(encoding="utf-8"))
            for orient, size in layout.SIZES.items():
                yield f.stem, orient, size, data, data.get(orient) or []

    def test_every_widget_type_exists_and_draws_without_errors(self):
        errors = []
        for lang in ("it", "en"):
            i18n.set_language(lang)
            for name, orient, size, data, widgets in self.each():
                for w in widgets:
                    self.assertIn(w["type"], WIDGETS, f"{name}/{orient}")
                page = layout.LayoutPage(name, data)
                page.render(self.state, size, {})  # warnings are logged, collect them through draw_all instead
                img = ui.canvas(size, name)
                from widgets import draw_all
                draw_all(img, widgets, layout.with_clock(self.state),
                         on_error=lambda w, e, n=name, o=orient: errors.append(f"{n}/{o} {w['type']}: {e!r}"))
        i18n.set_language("it")
        self.assertEqual(errors, [])

    def test_widgets_stay_inside_the_screen(self):
        out = [f"{name}/{orient} {w['type']} {w['x']},{w['y']} {w['w']}x{w['h']}"
               for name, orient, (sw, sh), _d, widgets in self.each() for w in widgets
               if w["x"] < 0 or w["y"] < 0 or w["x"] + w["w"] > sw or w["y"] + w["h"] > sh]
        self.assertEqual(out, [])

    def test_texts_fit_with_long_values(self):
        d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        out = []
        for lang in ("it", "en"):
            i18n.set_language(lang)
            ctx = layout.with_clock(self.state)
            for name, orient, size, _d, widgets in self.each():
                for w in widgets:
                    if w["type"] != "text":
                        continue
                    fields = [m.group(1).split(".")[-1] for m in FIELD.finditer(Text.p(w, "text"))]
                    if any(f in FREE_TEXT for f in fields):
                        continue
                    text, _first = template(ctx, Text.p(w, "text"))
                    text = text if text is not None else i18n._(Text.p(w, "fallback"))
                    f = font(int(Text.p(w, "size")), bool(Text.p(w, "bold")))
                    if text and d.textlength(text, font=f) > w["w"] + 1:
                        out.append(f"[{lang}] {name}/{orient}: '{text}' needs {d.textlength(text, font=f):.0f}px, has {w['w']}")
        i18n.set_language("it")
        self.assertEqual(out, [])

    def test_animated_pages(self):
        pages = {f.stem: layout.LayoutPage(f.stem, json.loads(f.read_text(encoding="utf-8"))) for f in self.files}
        self.assertTrue(pages["weather"].animated((320, 480)))
        self.assertTrue(pages["media"].animated((480, 320)))
        self.assertFalse(pages["clock"].animated((320, 480)))


if __name__ == "__main__":
    unittest.main()
