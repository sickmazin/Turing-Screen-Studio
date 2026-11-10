"""Statusline di Claude Code: salva il JSON di sessione per lo schermetto e stampa una riga breve.

In ~/.claude/settings.json:  "statusLine": {"type": "command", "command": "<venv python> <questo file>"}
"""
import json
import os
import sys
from pathlib import Path

OUT = Path.home() / ".schermetto" / "claude"

data = json.loads(sys.stdin.buffer.read() or b"{}")
sid = data.get("session_id", "unknown")
OUT.mkdir(parents=True, exist_ok=True)
tmp = OUT / f"{sid}.tmp"
tmp.write_text(json.dumps(data), encoding="utf-8")
os.replace(tmp, OUT / f"{sid}.json")  # scrittura atomica: lo schermetto non legge mai file a metà

ctx = data.get("context_window") or {}
pct = ctx.get("used_percentage")
model = (data.get("model") or {}).get("display_name", "")
line = f"{model} · ctx {pct:.0f}%" if isinstance(pct, (int, float)) else model
flag = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / ".ponytail-active"
if flag.exists():  # badge del plugin ponytail, che altrimenti avrebbe una sua statusline
    mode = flag.read_text(encoding="utf-8").strip()
    line = f"\x1b[38;5;108m[PONYTAIL{'' if mode in ('', 'full') else ':' + mode.upper()}]\x1b[0m {line}"
print(line)
