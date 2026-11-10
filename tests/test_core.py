import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image

import layout
import paths
import ui
from screen import pack, to_rgb565le
from sources import agents, claude, ical

paths.ensure_data()


class Protocol(unittest.TestCase):
    def test_pack_matches_reference_formula(self):
        self.assertEqual(pack(197, 0, 0, 319, 479), bytes([0, 0, 4, 0xFD, 0xDF, 197]))
        self.assertEqual(pack(197, 50, 300, 149, 329), bytes([12, 0x92, 0xC2, 0x55, 0x49, 197]))

    def test_rgb565_little_endian(self):
        self.assertEqual(to_rgb565le(Image.new("RGB", (1, 1), (255, 0, 0))), b"\x00\xf8")
        self.assertEqual(to_rgb565le(Image.new("RGB", (1, 1), (0, 255, 0))), b"\xe0\x07")
        self.assertEqual(to_rgb565le(Image.new("RGB", (1, 1), (0, 0, 255))), b"\x1f\x00")


def write_jsonl(lines):
    d = tempfile.mkdtemp()
    p = Path(d) / "x.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n", encoding="utf-8")
    return p


class Transcripts(unittest.TestCase):
    def test_claude_counts_once_and_skips_subagents(self):
        usage = {"input_tokens": 10, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 90, "output_tokens": 50}
        p = write_jsonl([
            {"type": "user", "cwd": "C:\\PROJECT\\demo", "message": {"content": "hi"}},
            {"type": "assistant", "message": {"id": "a", "model": "m", "usage": usage}},
            {"type": "assistant", "message": {"id": "a", "model": "m", "usage": usage}},
            {"type": "assistant", "isSidechain": True, "message": {"id": "s", "model": "m", "usage": dict(usage, output_tokens=999)}},
        ])
        s = claude.parse_transcript(p)
        self.assertEqual((s["context"], s["output_tokens"], s["turns"], s["project"]), (1100, 50, 1, "demo"))

    def test_codex_reads_context_window_and_limits(self):
        p = write_jsonl([
            {"type": "session_meta", "payload": {"cwd": "C:\\PROJECT\\gnn"}},
            {"type": "turn_context", "payload": {"model": "gpt-x"}},
            {"type": "event_msg", "payload": {"type": "task_started"}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "last_token_usage": {"input_tokens": 1000}, "total_token_usage": {"output_tokens": 77},
                "model_context_window": 4000},
                "rate_limits": {"primary": {"used_percent": 72.0, "window_minutes": 43200}}}},
            {"type": "event_msg", "payload": {"type": "task_complete"}},
            {"type": "event_msg", "payload": {"type": "task_started"}},
        ])
        s = agents.parse_codex(p)
        self.assertEqual((s["project"], s["model"], s["context"], s["window"], s["output_tokens"]), ("gnn", "gpt-x", 1000, 4000, 77))
        self.assertEqual(s["limits"], [{"label": "30 d", "pct": 72.0, "resets_at": None}])
        self.assertEqual((s["turns"], s["working"]), (2, True))  # second task still running


class Liveness(unittest.TestCase):
    def test_keeps_newest_sessions_per_running_process(self):
        from collections import Counter
        sessions = [{"cwd": "C:/Work/A", "age": 5, "id": 1}, {"cwd": "c:/work/a", "age": 1, "id": 2},
                    {"cwd": "C:/Work/A", "age": 9, "id": 3}, {"cwd": "C:/Work/B", "age": 2, "id": 4}]
        import os
        kept = list(agents.keep_live(sessions, Counter({os.path.normcase("C:/Work/A"): 2})))
        self.assertEqual([x["id"] for x in kept], [2, 1])  # two processes in A, none in B

    def test_closed_or_reused_pids_are_not_live(self):
        import os
        import psutil
        me = os.getpid()
        filetime = int((psutil.Process(me).create_time() + 11644473600) * 1e7)
        d = Path(tempfile.mkdtemp())
        files = {"1": {"pid": 999_999_9, "sessionId": "gone"},
                 "2": {"pid": me, "sessionId": "reused-pid", "procStart": str(filetime - 10**8)},  # started 10 s apart
                 "3": {"pid": me, "sessionId": "npm-install", "procStart": str(filetime), "status": "busy"},
                 "4": {"pid": me, "sessionId": "old-file-format", "procStartFt": str(filetime)}}
        for n, data in files.items():
            (d / f"{n}.json").write_text(json.dumps(data), encoding="utf-8")
        (d / "5.json").write_text("not json", encoding="utf-8")
        old, claude.SESSIONS = claude.SESSIONS, d
        try:  # this test runs as python.exe: the start time, not the name, must decide
            self.assertEqual(claude.live_sessions(), {"npm-install": "busy", "old-file-format": ""})
            claude.SESSIONS = d / "missing"
            self.assertIsNone(claude.live_sessions())  # older Claude Code: fall back to recent files
        finally:
            claude.SESSIONS = old


    def test_codex_launcher_and_child_count_as_one_session(self):
        import os
        from collections import Counter
        from unittest import mock

        class Proc:
            def __init__(self, pid, name, ppid, cwd, cmd=()):
                self.pid, self.info, self._cwd, self._cmd = pid, {"name": name, "ppid": ppid}, cwd, list(cmd)

            def cwd(self):
                return self._cwd

            def cmdline(self):
                return self._cmd

        procs = [Proc(10, "node.exe", 1, "C:/Work/A", ["node", "C:\\npm\\node_modules\\@openai\\codex\\bin\\codex.js"]),
                 Proc(11, "codex.exe", 10, "C:/Work/A"),       # native child of the launcher above
                 Proc(12, "codex.exe", 11, "C:/Work/A", ["codex.exe", "app-server", "--managed-daemon"]),
                 Proc(13, "codex.exe", 1, "C:/Users/me", ["codex.exe", "app-server", "daemon"]),  # outlived its chat
                 Proc(20, "codex.exe", 1, "C:/Work/B"),        # a second, separate session
                 Proc(30, "node.exe", 1, "C:/Work/C", ["node", "server.js"])]  # unrelated node app
        with mock.patch("psutil.process_iter", return_value=procs):
            live = agents.live_cwds()
        self.assertEqual(live, Counter({os.path.normcase("C:/Work/A"): 1, os.path.normcase("C:/Work/B"): 1}))


class MascotImage(unittest.TestCase):
    def test_own_image_replaces_the_pixel_icon_for_that_agent_only(self):
        from widgets import CLAUDE_ORANGE, draw_all
        paths.ASSETS.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (40, 40), (255, 0, 255)).save(paths.ASSETS / "logo.png")
        w = {"type": "mascot", "x": 0, "y": 0, "w": 60, "h": 60, "codex_image": "logo.png"}
        for agent, expected in (("Codex", (255, 0, 255)), ("Claude", CLAUDE_ORANGE)):
            img = Image.new("RGB", (60, 60))
            draw_all(img, [w], {"agent": {"agent": agent, "busy": False}, "_t": 1.0})
            self.assertIn(expected, {c for _n, c in img.getcolors(4096)}, agent)


class MediaTransitions(unittest.TestCase):
    def test_cover_follows_late_thumbnail_and_gap_is_held(self):
        import io as _io
        from sources import media

        def png(color):
            buf = _io.BytesIO()
            Image.new("RGB", (4, 4), color).save(buf, "PNG")
            return buf.getvalue()
        old, new = png((255, 0, 0)), png((0, 0, 255))
        media._cover.update(key=None, changed_at=0.0)
        first = media.update_cover(("A", "x"), old, 0.0)
        self.assertEqual(media._cover["changed_at"], 0.0)  # first song at start-up: not a skip
        skipped = media.update_cover(("B", "y"), old, 10.0)   # Windows still serves the old thumbnail
        self.assertIs(skipped, first)
        late = media.update_cover(("B", "y"), new, 11.0)      # the real one arrives a second later
        self.assertEqual(late.getpixel((0, 0)), (0, 0, 255))
        self.assertIs(media.update_cover(("B", "y"), new, 12.0), late)  # same bytes: same object, caches stay valid
        song = {"title": "B"}
        self.assertIs(media.hold(song, 100.0), song)
        self.assertIs(media.hold(None, 103.0), song)          # brief "nothing playing" between songs
        self.assertIsNone(media.hold(None, 100.0 + media.GAP_HOLD + 1))


    def test_position_runs_on_and_restarts_after_a_skip(self):
        from sources.media import live_position
        self.assertEqual(live_position(30, 1000, 200, True, 900, 1010), 40)    # 10 s played since the report
        self.assertEqual(live_position(30, 1000, 200, False, 900, 1010), 30)   # paused: stays
        self.assertEqual(live_position(180, 1000, 200, True, 1005, 1010), 5)   # report older than the skip: from 0
        self.assertEqual(live_position(195, 1000, 200, True, 900, 1100), 200)  # never past the end


class Logos(unittest.TestCase):
    def test_sources_per_kind_of_symbol(self):
        import logos
        self.assertTrue(logos.urls("AAPL")[0].endswith("ticker_icons/AAPL.png"))  # US: the transparent repo first
        self.assertTrue(logos.urls("BRK-B")[0].endswith("ticker_icons/BRKA.png"))
        self.assertEqual(len(logos.urls("ENI.MI")), 1)                          # European listing: only the fallback
        self.assertTrue(logos.urls("BTC-USD")[0].endswith("crypto_icons/BTC.png"))
        self.assertTrue(logos.urls("EURUSD=X")[0].endswith("forex_icons/EURUSD.png"))
        self.assertEqual((logos.urls("GC=F"), logos.urls("^GSPC")), ([], []))   # emoji / country badge instead
        self.assertEqual((logos.urls("GLD"), logos.EMOJI["GLD"]), ([], "🥇"))  # gold ETF: emoji, not a blank bar

    def test_only_transparent_grey_logos_are_recoloured(self):
        import logos
        black = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        black.paste((10, 10, 10, 255), (2, 2, 8, 8))
        red = black.copy()
        red.paste((220, 30, 30, 255), (2, 2, 8, 8))
        opaque = Image.new("RGBA", (10, 10), (0, 0, 0, 255))
        self.assertEqual([logos.is_monochrome(i) for i in (black, red, opaque)], [True, False, False])


class Calendar(unittest.TestCase):
    def test_recurring_events_are_expanded(self):
        now = datetime.now().astimezone()
        start = (now + timedelta(hours=2)).strftime("%Y%m%dT%H%M%S")
        ics = ("BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:1\nDTSTART:" + start + "\nDTEND:" + start +
               "\nRRULE:FREQ=DAILY\nSUMMARY:Standup\nEND:VEVENT\nEND:VCALENDAR\n").encode()
        events = list(ical.events_from(ics, now, now + timedelta(days=3)))
        self.assertGreaterEqual(len(events), 3)
        self.assertEqual(events[0]["title"], "Standup")


class SharedFiles(unittest.TestCase):
    def test_theme_roundtrip_and_hostile_zip(self):
        ui.save_theme("a", {"name": "A", "colors": {"bg": "#ff0000"}})
        dest = Path(tempfile.mkdtemp())
        ui.export_theme("a", dest / "copy.tss-theme")
        new_id = ui.import_theme(dest / "copy.tss-theme")
        self.assertEqual(ui.read_theme(new_id)["colors"]["bg"], "#ff0000")
        self.assertEqual(ui.read_theme(new_id)["colors"]["fg"], ui.DEFAULT_THEME["colors"]["fg"])  # missing = default
        evil = dest / "evil.tss-theme"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("theme.json", "{}")
            z.writestr("../../escaped.txt", "x")
        evil_id = ui.import_theme(evil)
        self.assertFalse((paths.THEMES.parent / "escaped.txt").exists())
        self.assertTrue((paths.THEMES / evil_id / "escaped.txt").exists())

    def test_page_import_drops_bad_widgets_and_paths(self):
        src = Path(tempfile.mkdtemp()) / "mine.tss-page"
        page = {"name": "Mine", "portrait": [
            {"type": "image", "x": 0, "y": 0, "w": 10, "h": 10, "file": "..\\..\\secret.png"},
            {"type": "no-such-widget", "x": 0, "y": 0, "w": 1, "h": 1},
            {"type": "text", "x": "bad", "y": 0, "w": 1, "h": 1}], "landscape": []}
        with zipfile.ZipFile(src, "w") as z:
            z.writestr("page.json", json.dumps(page))
            z.writestr("../evil.png", b"x")
        pid = layout.import_page(src, set())
        data = json.loads((paths.LAYOUTS / f"{pid}.json").read_text(encoding="utf-8"))
        self.assertEqual([w["type"] for w in data["portrait"]], ["image"])
        self.assertEqual(data["portrait"][0]["file"], "secret.png")
        self.assertTrue((paths.ASSETS / "evil.png").exists())
        self.assertFalse((paths.LAYOUTS / "evil.png").exists())


class History(unittest.TestCase):
    def test_records_only_numeric_fields_used_by_history_widgets(self):
        page = layout.LayoutPage("p", {"portrait": [{"type": "history", "x": 0, "y": 0, "w": 10, "h": 10, "field": "system.cpu"}]})
        rec = layout.HistoryRecorder()
        rec.record([page], {"system": {"cpu": 5}})
        view = rec.record([page], {"system": {"cpu": "n/a"}})
        self.assertEqual([v for t, v in view["system.cpu"]], [5.0])


if __name__ == "__main__":
    unittest.main()
