"""Every bundled layout must render cleanly in both orientations with realistic data:
no widget errors, every widget inside the screen, no truncated text."""
import json
import time
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
        "agents": [dict(agent="Claude", key="Claude:1", title="CLAUDE CODE", model="claude-opus-5-5",
                        limits=[{"label": "5 h", "pct": 42, "resets_at": 1999999999},
                                {"label": "7 d", "pct": 64, "resets_at": 1999999999}], limit_pct=42, **{
                            k: session[k] for k in ("project", "context", "window", "context_pct", "output_tokens",
                                                    "turns", "cost", "busy", "age")}),
                   {"agent": "Codex", "key": "Codex:2", "title": "CODEX", "project": "Blockchain-GNN", "model": "gpt-6-luna",
                    "context": 104_000, "window": 258_400, "context_pct": 40.5, "output_tokens": 24_000, "turns": 8,
                    "cost": None, "busy": False, "age": 60, "limit_pct": 72,
                    "limits": [{"label": "30 d", "pct": 72, "resets_at": 1999999999}]}],
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
        self.assertTrue(pages["claude"].animated((320, 480)))  # the mascot
        self.assertFalse(pages["clock"].animated((320, 480)))


class MarketsGrid(unittest.TestCase):
    def test_grid_shape_follows_count_and_orientation(self):
        from widgets import grid_shape
        self.assertEqual([grid_shape(n, 296, 436) for n in (6, 9, 12)], [(2, 3), (3, 3), (3, 4)])  # portrait
        self.assertEqual([grid_shape(n, 456, 282) for n in (6, 9, 12)], [(3, 2), (3, 3), (4, 3)])  # landscape

    def test_rows_up_to_five_then_cards(self):
        from widgets import draw_all
        quotes = sample_state()["stocks"]
        w = {"type": "markets", "x": 0, "y": 0, "w": 296, "h": 436, "list_up_to": 5}
        for n in (5, 6):
            errors = []
            img = Image.new("RGB", (296, 436))
            draw_all(img, [w], {"stocks": (quotes * 2)[:n]}, on_error=lambda w, e: errors.append(e))
            self.assertEqual(errors, [])
            # a grid leaves a vertical gap between the two card columns at the centre; the list does not
            column = {img.getpixel((148, y)) for y in range(60, 400)}
            self.assertEqual(len(column) == 1, n == 6, n)


    def test_tiny_widget_draws_nothing_instead_of_failing(self):
        from widgets import draw_all
        errors = []
        draw_all(Image.new("RGB", (100, 100)), [{"type": "markets", "x": 0, "y": 0, "w": 100, "h": 80}],
                 {"stocks": sample_state()["stocks"] * 3}, on_error=lambda w, e: errors.append(e))
        self.assertEqual(errors, [])

    def test_emptied_list_stays_empty(self):
        import asyncio
        from sources import stocks
        self.assertEqual(asyncio.run(stocks.fetch({"tickers": []})), [])  # no request, no defaults coming back


class StockPickerCustomSymbol(unittest.TestCase):
    def test_typo_is_refused_and_no_network_is_accepted(self):
        import tkinter as tk
        from unittest import mock
        import requests
        import stock_picker
        root = tk.Tk()
        root.geometry("10x10+0+0")
        try:
            picker = stock_picker.StockPicker(root, [], lambda chosen: None)
            not_found = requests.HTTPError(response=mock.Mock(status_code=404))
            for typed, error, expected in (("APPL", not_found, []), ("ENEL.MI", requests.ConnectionError(), ["ENEL.MI"])):
                picker.custom.delete(0, "end")
                picker.custom.insert(0, typed)
                with mock.patch.object(stock_picker, "_get", side_effect=error),                         mock.patch.object(stock_picker.messagebox, "showwarning") as warn:
                    picker.add_custom()
                    for _i in range(300):  # let the check thread finish and post its result
                        root.update()
                        if warn.called or picker.chosen:
                            break
                        time.sleep(0.01)
                self.assertEqual(picker.chosen, expected, typed)
                self.assertEqual(warn.called, not expected, typed)
        finally:
            root.destroy()


class AgentPages(unittest.TestCase):
    def test_one_page_per_session_and_one_when_none(self):
        data = json.loads((DEFAULTS / "claude.json").read_text(encoding="utf-8"))
        page = layout.LayoutPage("claude", data)
        clock = layout.LayoutPage("clock", {"portrait": []})
        state = sample_state()
        view = layout.expand_pages([clock, page], state)
        self.assertEqual([p.name for p in view], ["clock", "claude#Claude:1", "claude#Codex:2"])
        self.assertEqual(view[2].session(state)["agent"], "Codex")
        self.assertEqual([p.name for p in layout.expand_pages([page], {})], ["claude"])
        self.assertEqual(len(layout.expand_pages([page], state, limit=1)), 1)

    def test_page_follows_its_session_when_the_list_reorders(self):
        page = layout.LayoutPage("claude", json.loads((DEFAULTS / "claude.json").read_text(encoding="utf-8")))
        state = sample_state()
        codex = layout.expand_pages([page], state)[1]
        state["agents"].reverse()
        self.assertEqual(codex.session(state)["agent"], "Codex")
        img = codex.render(state, (320, 480), {})
        self.assertEqual(img.size, (320, 480))


if __name__ == "__main__":
    unittest.main()
