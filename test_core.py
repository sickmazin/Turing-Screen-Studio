"""Self-check: .venv\\Scripts\\python test_core.py"""
import json
import tempfile
from pathlib import Path

from PIL import Image

from screen import pack, to_rgb565le
from sources.claude import parse_transcript

# comando: formula del driver di riferimento, coordinate a 10 bit
assert pack(197, 0, 0, 319, 479) == bytes([0, 0, 4, 0xFD, 0xDF, 197])
assert pack(197, 50, 300, 149, 329) == bytes([12, 0x92, 0xC2, 0x55, 0x49, 197])

# RGB565 little-endian
assert to_rgb565le(Image.new("RGB", (1, 1), (255, 0, 0))) == b"\x00\xf8"
assert to_rgb565le(Image.new("RGB", (1, 1), (0, 255, 0))) == b"\xe0\x07"
assert to_rgb565le(Image.new("RGB", (1, 1), (0, 0, 255))) == b"\x1f\x00"

# transcript: niente doppio conteggio per messaggi su più righe, subagent ignorati
usage = {"input_tokens": 10, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 90, "output_tokens": 50}
lines = [
    {"type": "user", "cwd": "C:\\PROJECT\\demo", "message": {"content": "ciao"}},
    {"type": "assistant", "message": {"id": "a", "model": "m", "usage": usage}},
    {"type": "assistant", "message": {"id": "a", "model": "m", "usage": usage}},
    {"type": "assistant", "isSidechain": True, "message": {"id": "s", "model": "m", "usage": dict(usage, output_tokens=999)}},
]
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "x.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\nnon json\n", encoding="utf-8")
    s = parse_transcript(p)
assert (s["context"], s["output_tokens"], s["turns"], s["project"]) == (1100, 50, 1, "demo"), s
print("ok")

# temi: export/import, e un file malevolo non può scrivere fuori dalla cartella del tema
import zipfile
import ui

with tempfile.TemporaryDirectory() as d:
    old = ui.THEMES
    ui.THEMES = Path(d) / "themes"
    try:
        ui.save_theme("a", {"name": "A", "colors": {"bg": "#ff0000"}})
        ui.export_theme("a", Path(d) / "copia.schermetto-theme")
        new_id = ui.import_theme(Path(d) / "copia.schermetto-theme")
        assert new_id == "copia" and ui.read_theme("copia")["colors"]["bg"] == "#ff0000"
        assert ui.read_theme("copia")["colors"]["fg"] == ui.DEFAULT_THEME["colors"]["fg"]  # campi mancanti = predefiniti
        evil = Path(d) / "evil.schermetto-theme"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("theme.json", "{}")
            z.writestr("../../escaped.txt", "x")
        ui.import_theme(evil)
        assert not (Path(d) / "escaped.txt").exists() and (ui.THEMES / "evil" / "escaped.txt").exists()
    finally:
        ui.THEMES = old
print("ok temi")
