"""All terminal coding agents in one list: Claude Code, OpenAI Codex CLI, Gemini CLI.

Each session: {agent, project, model, context, window, context_pct, busy, age, limit_pct}.
Formats checked against real files:
- Codex:  ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl, event_msg/token_count with last_token_usage,
          model_context_window and rate_limits.primary.used_percent
- Gemini: ~/.gemini/tmp/<project>/chats/session-*.jsonl, messages of type "gemini" with tokens.input
"""
import asyncio
import json
import time
from pathlib import Path

from sources import claude

name = "agents"
settings = {"active_minutes": 30, "gemini_context_window": 1000000}
interval = 5

CODEX = Path.home() / ".codex" / "sessions"
GEMINI = Path.home() / ".gemini" / "tmp"
_cache = {}


def _cached(path, parse):
    mtime = path.stat().st_mtime
    hit = _cache.get(path)
    if not hit or hit[0] != mtime:
        _cache[path] = hit = (mtime, parse(path))
    return hit[1]


def parse_codex(path: Path) -> dict:
    s = {"agent": "Codex", "project": "", "model": "", "context": 0, "window": 0, "limit_pct": None}
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            p = e.get("payload") or {}
            if e.get("type") == "session_meta" and p.get("cwd"):
                s["project"] = Path(p["cwd"]).name
            elif e.get("type") == "turn_context" and p.get("model"):
                s["model"] = p["model"]
            elif p.get("type") == "token_count":
                info = p.get("info") or {}
                last = info.get("last_token_usage") or {}
                s["context"] = last.get("input_tokens", s["context"])
                s["window"] = info.get("model_context_window") or s["window"]
                primary = (p.get("rate_limits") or {}).get("primary") or {}
                if isinstance(primary.get("used_percent"), (int, float)):
                    s["limit_pct"] = primary["used_percent"]
    return s


def parse_gemini(path: Path) -> dict:
    s = {"agent": "Gemini", "project": path.parent.parent.name, "model": "", "context": 0, "window": 0, "limit_pct": None}
    root = path.parent.parent / ".project_root"
    if root.exists():
        s["project"] = Path(root.read_text(encoding="utf-8").strip()).name or s["project"]

    def visit(m):
        if isinstance(m, dict) and m.get("type") == "gemini" and isinstance(m.get("tokens"), dict):
            s["model"] = m.get("model") or s["model"]
            s["context"] = m["tokens"].get("input", s["context"])
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            for m in (e.get("$set") or {}).get("messages", []) + ([e] if "tokens" in e else []):
                visit(m)
    return s


def collect(cfg):
    now = time.time()
    active = cfg.get("active_minutes", 30) * 60
    out = []
    for s in claude.collect({"active_minutes": cfg.get("active_minutes", 30)}):
        limit = ((s.get("rate_limits") or {}).get("five_hour") or {}).get("used_percentage")
        out.append({"agent": "Claude", "project": s["project"], "model": s["model_name"], "context": s["context"],
                    "window": s["window"], "context_pct": s["context_pct"], "busy": s["busy"], "age": s["age"],
                    "limit_pct": limit})
    for files, parse, window in ((CODEX.glob("*/*/*/*.jsonl"), parse_codex, 0),
                                 (GEMINI.glob("*/chats/*.jsonl"), parse_gemini, cfg.get("gemini_context_window", 1_000_000))):
        for p in files:
            age = now - p.stat().st_mtime
            if age > active:
                continue
            s = dict(_cached(p, parse), age=age, busy=age < 20)
            s["window"] = s["window"] or window or 200_000
            s["context_pct"] = s["context"] / s["window"] * 100 if s["window"] else 0
            if s["model"] or s["context"]:
                out.append(s)
    out.sort(key=lambda s: s["age"])
    return out


async def fetch(cfg):
    return await asyncio.to_thread(collect, cfg)
