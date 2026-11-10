"""Sessioni Claude Code attive, lette dai transcript in ~/.claude/projects.

Se è configurata claude_statusline.py, aggiunge anche costo, dimensione del contesto e limiti del piano
dal JSON che Claude Code passa alla statusline (~/.schermetto/claude/<session>.json).
"""
import asyncio
import json
import time
from pathlib import Path

name = "claude"
settings = {"active_minutes": 30, "context_window": 200000}  # valori predefiniti, modificabili da settings.py (scheda Dati)
interval = 3

PROJECTS = Path.home() / ".claude" / "projects"
DUMPS = Path.home() / ".schermetto" / "claude"
_cache = {}  # path -> (mtime, risultato): rileggo un transcript solo se è cambiato


def parse_transcript(path: Path) -> dict:
    s = {"session_id": path.stem, "project": path.parent.name, "model": "", "context": 0,
         "output_tokens": 0, "turns": 0, "last_role": "", "cwd": "", "started": None}
    seen = set()
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("isSidechain"):
                continue  # i subagent hanno il loro contesto
            s["started"] = s["started"] or e.get("timestamp")
            s["cwd"] = s["cwd"] or e.get("cwd", "")  # cartella dove è partita la sessione
            t = e.get("type")
            if t == "user" and isinstance(e.get("message", {}).get("content"), str):
                s["turns"] += 1
            if t in ("user", "assistant"):
                s["last_role"] = t
            if t != "assistant":
                continue
            m = e.get("message", {})
            u = m.get("usage") or {}
            if not u:
                continue
            s["model"] = m.get("model", s["model"])
            # contesto = tutto l'input dell'ultima richiesta (anche la parte in cache)
            s["context"] = (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                            + u.get("cache_creation_input_tokens", 0))
            if m.get("id") not in seen:  # un messaggio può comparire su più righe con lo stesso usage
                seen.add(m.get("id"))
                s["output_tokens"] += u.get("output_tokens", 0)
    if s["cwd"]:
        s["project"] = Path(s["cwd"]).name
    return s


def _merge_statusline(s: dict, window_default: int):
    s["window"] = window_default
    dump = DUMPS / f"{s['session_id']}.json"
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


def _collect(cfg):
    now = time.time()
    active = cfg.get("active_minutes", 30) * 60
    out = []
    for p in PROJECTS.glob("*/*.jsonl"):
        mtime = p.stat().st_mtime
        if now - mtime > active:
            continue
        hit = _cache.get(p)
        if not hit or hit[0] != mtime:
            _cache[p] = hit = (mtime, parse_transcript(p))
        s = dict(hit[1], age=now - mtime)
        if not s["model"]:
            continue
        window = cfg.get("context_window", 200_000)
        # senza statusline la finestra è una stima: se il contesto la supera, il modello ha quella da 1M
        _merge_statusline(s, window if s["context"] <= window else 1_000_000)
        s.setdefault("context_pct", s["context"] / s["window"] * 100)
        s["model_name"] = s.get("model_name") or s["model"]
        # sta lavorando se il transcript è stato scritto da poco e l'ultimo turno non è chiuso
        s["busy"] = s["age"] < 20
        out.append(s)
    out.sort(key=lambda s: s["age"])
    return out


async def fetch(cfg):
    return await asyncio.to_thread(_collect, cfg)


if __name__ == "__main__":
    for s in _collect({}):
        print({k: v for k, v in s.items()})
