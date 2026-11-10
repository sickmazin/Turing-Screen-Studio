"""Terminal coding agents in one list: Claude Code and OpenAI Codex CLI, newest activity first.

Every session has the same shape, so one page layout works for both:
  {key, agent, title, project, model, context, window, context_pct, busy, age,
   output_tokens, turns, cost, limits: [{label, pct, resets_at}], limit_pct}
Only sessions still open are listed: Claude Code through ~/.claude/sessions, Codex through its running processes.
Codex format checked against real files: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl with session_meta (cwd),
turn_context (model), event_msg task_started/task_complete (turns, working), token_count (context, window, limits).
"""
import asyncio
import json
import os
import time
from collections import Counter
from pathlib import Path

import psutil

from sources import claude

name = "agents"
settings = {"active_minutes": 30}  # used only with Claude Code versions that do not report open sessions
interval = 3

CODEX = Path.home() / ".codex" / "sessions"
TITLES = {"Claude": "CLAUDE CODE", "Codex": "CODEX"}
_cache = {}


def _cached(path, parse):
    mtime = path.stat().st_mtime
    hit = _cache.get(path)
    if not hit or hit[0] != mtime:
        _cache[path] = hit = (mtime, parse(path))
    return hit[1]


def window_label(minutes):
    if not minutes:
        return ""
    return f"{minutes // 1440} d" if minutes >= 1440 else f"{minutes // 60} h" if minutes >= 60 else f"{minutes} min"


def parse_codex(path: Path) -> dict:
    s = {"agent": "Codex", "project": "", "cwd": "", "model": "", "context": 0, "window": 0, "output_tokens": 0,
         "turns": 0, "limits": [], "working": False}
    started = completed = 0
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            p = e.get("payload") or {}
            kind = p.get("type")
            if e.get("type") == "session_meta" and p.get("cwd"):
                s["project"], s["cwd"] = Path(p["cwd"]).name, p["cwd"]
            elif e.get("type") == "turn_context" and p.get("model"):
                s["model"] = p["model"]
            elif kind == "task_started":
                started += 1
            elif kind == "task_complete":
                completed += 1
            elif kind == "token_count":
                info = p.get("info") or {}
                s["context"] = (info.get("last_token_usage") or {}).get("input_tokens", s["context"])
                s["output_tokens"] = (info.get("total_token_usage") or {}).get("output_tokens", s["output_tokens"])
                s["window"] = info.get("model_context_window") or s["window"]
                rl = p.get("rate_limits") or {}
                limits = [{"label": window_label(w.get("window_minutes")), "pct": w["used_percent"], "resets_at": w.get("resets_at")}
                          for w in (rl.get("primary"), rl.get("secondary"))
                          if isinstance(w, dict) and isinstance(w.get("used_percent"), (int, float))]
                s["limits"] = limits or s["limits"]
    s["turns"], s["working"] = started, started > completed
    return s


def from_claude(c: dict) -> dict:
    rl = c.get("rate_limits") or {}
    limits = [{"label": label, "pct": rl[k]["used_percentage"], "resets_at": rl[k].get("resets_at")}
              for k, label in (("five_hour", "5 h"), ("seven_day", "7 d"))
              if isinstance(rl.get(k), dict) and isinstance(rl[k].get("used_percentage"), (int, float))]
    return {"agent": "Claude", "session_id": c["session_id"], "project": c["project"], "model": c["model_name"],
            "context": c["context"], "window": c["window"], "context_pct": c["context_pct"], "busy": c["busy"],
            "age": c["age"], "output_tokens": c["output_tokens"], "turns": c["turns"], "cost": c.get("cost"),
            "limits": limits}


def live_cwds() -> Counter:
    """Working folders of running Codex processes, counted once per session (not per child process).

    Tree seen on Windows: node (codex.js) -> codex.exe -> codex.exe app-server (background daemon, may outlive the chat)."""
    found = {}
    for p in psutil.process_iter(["name", "ppid"]):
        name = (p.info["name"] or "").lower()
        if not name.startswith(("codex", "node")):
            continue  # command lines are slow to read on Windows: only for the candidates
        try:
            cmd = " ".join(p.cmdline()).lower().replace("\\", "/")
            if "app-server" not in cmd and (name.startswith("codex") or "@openai/codex" in cmd):
                found[p.pid] = (os.path.normcase(p.cwd()), p.info["ppid"])
        except psutil.Error:
            pass
    return Counter(cwd for cwd, ppid in found.values() if ppid not in found)  # launcher + native child = one


def keep_live(sessions, counts):
    """Newest sessions first; keep as many per folder as there are processes running in it."""
    left = Counter(counts)
    for s in sorted(sessions, key=lambda s: s["age"]):
        cwd = os.path.normcase(s.get("cwd") or "")
        if left[cwd] > 0:
            left[cwd] -= 1
            yield s


def collect(cfg):
    now = time.time()
    out = [from_claude(c) for c in claude.collect({"active_minutes": cfg.get("active_minutes", 30)})]
    live = live_cwds()
    if live:  # no Codex process running: nothing to show and no files to parse
        found = []
        for p in CODEX.glob("*/*/*/*.jsonl"):
            age = now - p.stat().st_mtime
            if age > 7 * 86400:
                continue  # an open session has written in the last week; skips parsing the whole history
            s = dict(_cached(p, parse_codex), age=age, session_id=p.stem)
            if not (s["model"] or s["context"]):
                continue
            s["window"] = s["window"] or 200_000
            s["context_pct"] = s["context"] / s["window"] * 100
            s["busy"] = s.pop("working") and age < 600 or age < 20
            s["cost"] = None
            found.append(s)
        out.extend(keep_live(found, live))
    for s in out:
        s["key"] = f"{s['agent']}:{s['session_id']}"
        s["title"] = TITLES.get(s["agent"], s["agent"].upper())
        s["limit_pct"] = s["limits"][0]["pct"] if s["limits"] else None
    out.sort(key=lambda s: s["age"])
    return out


async def fetch(cfg):
    return await asyncio.to_thread(collect, cfg)
