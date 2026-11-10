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

    def test_gemini_reads_last_input_tokens(self):
        d = Path(tempfile.mkdtemp()) / "proj" / "chats"
        d.mkdir(parents=True)
        p = d / "session.jsonl"
        p.write_text("\n".join(json.dumps(x) for x in [
            {"sessionId": "x"},
            {"$set": {"messages": [{"type": "gemini", "model": "gemini-3", "tokens": {"input": 500}},
                                   {"type": "gemini", "model": "gemini-3", "tokens": {"input": 800}}]}}]), encoding="utf-8")
        s = agents.parse_gemini(p)
        self.assertEqual((s["project"], s["model"], s["context"]), ("proj", "gemini-3", 800))


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
        d = Path(tempfile.mkdtemp())
        (d / "1.json").write_text(json.dumps({"pid": 999_999_9, "sessionId": "gone"}), encoding="utf-8")
        (d / "2.json").write_text(json.dumps({"pid": os.getpid(), "sessionId": "python-not-claude"}), encoding="utf-8")
        (d / "3.json").write_text("not json", encoding="utf-8")
        old, claude.SESSIONS = claude.SESSIONS, d
        try:
            self.assertEqual(claude.live_sessions(), {})
            claude.SESSIONS = d / "missing"
            self.assertIsNone(claude.live_sessions())  # older Claude Code: fall back to recent files
        finally:
            claude.SESSIONS = old


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
