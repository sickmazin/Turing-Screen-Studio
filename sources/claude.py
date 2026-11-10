"""Active Claude Code sessions, read from the transcripts in ~/.claude/projects.

If claude_statusline.py is configured as Claude Code's status line, cost, real context window size and plan
limits are added from the JSON Claude Code passes to it (saved in <data>/claude/<session>.json).
"""
import asyncio
import json
import time
from pathlib import Path

import psutil

import paths

name = "claude"
settings = {"active_minutes": 30, "context_window": 200000}  # defaults, editable in the Data tab
interval = 3

PROJECTS = Path.home() / ".claude" / "projects"
SESSIONS = Path.home() / ".claude" / "sessions"
_cache = {}  # path -> (mtime, result): a transcript is parsed again only when it changes


def parse_transcript(path: Path) -> dict:
    s = {"session_id": path.stem, "project": path.parent.name, "model": "", "context": 0,
         "output_tokens": 0, "turns": 0, "cwd": "", "started": None}
    seen = set()
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("isSidechain"):
                continue  # subagents have their own context
            s["started"] = s["started"] or e.get("timestamp")
            s["cwd"] = s["cwd"] or e.get("cwd", "")  # folder where the session started
            t = e.get("type")
            if t == "user" and isinstance(e.get("message", {}).get("content"), str):
                s["turns"] += 1
            if t != "assistant":
                continue
            m = e.get("message", {})
            u = m.get("usage") or {}
            if not u:
                continue
            s["model"] = m.get("model", s["model"])
            # context = all the input of the latest request, cached part included
            s["context"] = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                            + u.get("cache_creation_input_tokens", 0))
            if m.get("id") not in seen:  # one message can span several lines with the same usage
                seen.add(m.get("id"))
                s["output_tokens"] += u.get("output_tokens", 0)
    if s["cwd"]:
        s["project"] = Path(s["cwd"]).name
    return s


def merge_statusline(s: dict, window_default: int):
    s["window"] = window_default
    dump = paths.CLAUDE_DUMPS / f"{s['session_id']}.json"
    if not dump.exists():
        return
    try:
        d = json.loads(dump.read_text(encoding="utf-8"))
    except ValueError:
        return
    ctx = d.get("context_window") or {}
    s["window"] = ctx.get("context_window_size") or window_default
    if isinstance(ctx.get("used_percentage"), (int, float)):
        s["context_pct"] = ctx["used_percentage"]
    cost = d.get("cost") or {}
    s["cost"] = cost.get("total_cost_usd")
    s["lines"] = (cost.get("total_lines_added"), cost.get("total_lines_removed"))
    s["model_name"] = (d.get("model") or {}).get("display_name")
    s["rate_limits"] = d.get("rate_limits")


def live_sessions():
    """sessionId -> status ("busy", ...) of Claude Code processes still running, from ~/.claude/sessions/<pid>.json.

    None when that folder does not exist (older Claude Code): callers fall back to "recently written"."""
    if not SESSIONS.is_dir():
        return None
    out = {}
    for f in SESSIONS.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("sessionId") and "claude" in psutil.Process(int(d["pid"])).name().lower():  # pid not reused
                out[d["sessionId"]] = d.get("status", "")
        except (OSError, ValueError, KeyError, psutil.Error):
            continue  # stale file of a closed session
    return out


def collect(cfg):
    now = time.time()
    active = cfg.get("active_minutes", 30) * 60
    live = live_sessions()
    out = []
    for p in PROJECTS.glob("*/*.jsonl"):
        if live is not None and p.stem not in live:
            continue  # session closed (or a subagent transcript)
        mtime = p.stat().st_mtime
        if live is None and now - mtime > active:
            continue
        hit = _cache.get(p)
        if not hit or hit[0] != mtime:
            _cache[p] = hit = (mtime, parse_transcript(p))
        s = dict(hit[1], age=now - mtime)
        if not s["model"]:
            continue
        window = cfg.get("context_window", 200_000)
        # without the status line the window is a guess: if the context is bigger, the model has the 1M one
        merge_statusline(s, window if s["context"] <= window else 1_000_000)
        s.setdefault("context_pct", s["context"] / s["window"] * 100)
        s["model_name"] = s.get("model_name") or s["model"]
        # Claude Code's own status when known, else "written to in the last seconds"
        s["busy"] = live[p.stem] == "busy" if live and live.get(p.stem) else s["age"] < 20
        out.append(s)
    out.sort(key=lambda s: s["age"])
    return out


async def fetch(cfg):
    return await asyncio.to_thread(collect, cfg)
