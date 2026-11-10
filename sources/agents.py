"""Terminal coding agents in one list: Claude Code, OpenAI Codex CLI, Gemini CLI. Newest activity first.

Every session has the same shape, so one page layout works for all of them:
  {key, agent, title, project, model, context, window, context_pct, busy, age,
   output_tokens, turns, cost, limits: [{label, pct, resets_at}], limit_pct}
Formats checked against real files:
- Codex:  ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl: session_meta (cwd), turn_context (model),
          event_msg task_started/task_complete (turns, working), token_count (context, window, rate limits)
- Gemini: ~/.gemini/tmp/<project>/chats/session-*.jsonl: messages of type "user" / "gemini" with tokens
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
settings = {"active_minutes": 30, "gemini_context_window": 1000000}
interval = 3

CODEX = Path.home() / ".codex" / "sessions"
GEMINI = Path.home() / ".gemini" / "tmp"
TITLES = {"Claude": "CLAUDE CODE", "Codex": "CODEX", "Gemini": "GEMINI CLI"}
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
    s = {"agent": "Codex", "project": "", "model": "", "context": 0, "window": 0, "output_tokens": 0, "turns": 0,
         "limits": [], "working": False}
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


def parse_gemini(path: Path) -> dict:
    s = {"agent": "Gemini", "project": path.parent.parent.name, "model": "", "context": 0, "window": 0,
         "output_tokens": 0, "turns": 0, "limits": []}
    root = path.parent.parent / ".project_root"
    if root.exists():
        s["cwd"] = root.read_text(encoding="utf-8").strip()
        s["project"] = Path(s["cwd"]).name or s["project"]
    messages = {}
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            for m in (e.get("$set") or {}).get("messages", []) + ([e] if "type" in e and "id" in e else []):
                if isinstance(m, dict):
                    messages[m.get("id") or id(m)] = m  # the file rewrites the whole list: keep each message once
    for m in messages.values():
        if m.get("type") == "user":
            s["turns"] += 1
        elif m.get("type") == "gemini" and isinstance(m.get("tokens"), dict):
            s["model"] = m.get("model") or s["model"]
            s["context"] = m["tokens"].get("input", s["context"])
            s["output_tokens"] += m["tokens"].get("output", 0)
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


def live_cwds():
    """Working folders of running Codex / Gemini CLI processes, counted once per session (not per child process)."""
    found = {}
    for p in psutil.process_iter(["name", "cmdline", "ppid"]):
        name = (p.info["name"] or "").lower()
        args = " ".join(p.info["cmdline"] or []).lower().replace("\\", "/") if name.startswith("node") else ""
        agent = ("Codex" if name.startswith("codex") or "@openai/codex" in args else
                 "Gemini" if name.startswith("gemini") or "gemini-cli" in args else None)
        if agent:
            try:
                found[p.pid] = (agent, os.path.normcase(p.cwd()), p.info["ppid"])
            except psutil.Error:
                pass
    out = {"Codex": Counter(), "Gemini": Counter()}
    for agent, cwd, ppid in found.values():
        if ppid not in found:  # the npm "node" launcher and its native child are one session
            out[agent][cwd] += 1
    return out


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
    minutes = cfg.get("active_minutes", 30)
    out = [from_claude(c) for c in claude.collect({**claude.settings, **cfg.get("claude", {}), "active_minutes": minutes})]
    live = live_cwds()
    for agent, files, parse, window in (("Codex", CODEX.glob("*/*/*/*.jsonl"), parse_codex, 0),
                                        ("Gemini", GEMINI.glob("*/chats/*.jsonl"), parse_gemini,
                                         cfg.get("gemini_context_window", 1_000_000))):
        if not live[agent]:
            continue  # no process running: nothing to show (and no files to parse)
        found = []
        for p in files:
            age = now - p.stat().st_mtime
            if age > 7 * 86400:
                continue  # an open session has written in the last week; skips parsing the whole history
            s = dict(_cached(p, parse), age=age, session_id=p.stem)
            if not (s["model"] or s["context"]):
                continue
            s["window"] = s["window"] or window or 200_000
            s["context_pct"] = s["context"] / s["window"] * 100
            s["busy"] = s.pop("working", False) and age < 600 or age < 20
            s.setdefault("cost", None)
            found.append(s)
        out.extend(keep_live(found, live[agent]))
    for s in out:
        s["key"] = f"{s['agent']}:{s['session_id']}"
        s["title"] = TITLES.get(s["agent"], s["agent"].upper())
        s["limit_pct"] = s["limits"][0]["pct"] if s["limits"] else None
    out.sort(key=lambda s: s["age"])
    return out


async def fetch(cfg):
    return await asyncio.to_thread(collect, cfg)
