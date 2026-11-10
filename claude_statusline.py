"""Claude Code status line: saves the session JSON for the screen and prints a short line.

In ~/.claude/settings.json:  "statusLine": {"type": "command", "command": "<python> <this file>"}
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

data = json.loads(sys.stdin.buffer.read() or b"{}")
sid = "".join(c for c in str(data.get("session_id", "unknown")) if c.isalnum() or c in "-_") or "unknown"
paths.CLAUDE_DUMPS.mkdir(parents=True, exist_ok=True)
tmp = paths.CLAUDE_DUMPS / f"{sid}.tmp"
tmp.write_text(json.dumps(data), encoding="utf-8")
os.replace(tmp, paths.CLAUDE_DUMPS / f"{sid}.json")  # atomic: the screen never reads half a file

ctx = data.get("context_window") or {}
pct = ctx.get("used_percentage")
model = (data.get("model") or {}).get("display_name", "")
line = f"{model} · ctx {pct:.0f}%" if isinstance(pct, (int, float)) else model
flag = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / ".ponytail-active"
if flag.exists():  # badge of the ponytail plugin, which would otherwise need its own status line
    mode = flag.read_text(encoding="utf-8").strip()
    line = f"\x1b[38;5;108m[PONYTAIL{'' if mode in ('', 'full') else ':' + mode.upper()}]\x1b[0m {line}"
print(line)
