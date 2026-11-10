"""Writes the bundled default layouts to defaults/layouts/. Run: python tools/default_layouts.py

Texts are in English; the screen shows them in the UI language through i18n.IT.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "defaults" / "layouts"


def W(t, x, y, w, h, **p):
    return {"type": t, "x": x, "y": y, "w": w, "h": h, **p}


def T(x, y, w, h, text, size=16, bold=False, color="fg", align="left", fallback=""):
    return W("text", x, y, w, h, text=text, size=size, bold=bold, color=color, align=align, fallback=fallback)


def header(title, width, right=None):
    out = [T(16, 4, width - 32, 24, title, 15, True, "muted")]
    if right:
        out.append(T(width // 2, 4, width // 2 - 16, 24, right, 15, color="muted", align="right"))
    return out


def group(name, items):
    for w in items:
        w["group"] = name
    return items


# --- clock
clock = {"name": "Clock",
 "portrait": [T(0, 150, 320, 110, "{now:%H:%M}", 96, True, align="center"),
              T(0, 252, 320, 40, "{now:%S}", 28, color="accent", align="center"),
              T(0, 300, 320, 40, "{date.weekday} {date.day} {date.month}", 22, color="muted", align="center")],
 "landscape": [T(0, 60, 480, 140, "{now:%H:%M}", 120, True, align="center"),
               T(0, 196, 480, 36, "{now:%S}", 26, color="accent", align="center"),
               T(0, 240, 480, 40, "{date.weekday} {date.day} {date.month}", 24, color="muted", align="center")]}


# --- system
def metric(x, y, w, label, field, extra=None, source="system"):
    out = [T(x, y, 120, 20, label, 16, True, "muted"),
           T(x + w - 90, y - 8, 90, 36, "{%s.%s:.0f}%%" % (source, field), 30, True, align="right"),
           W("bar", x, y + 42, w, 12, field=f"{source}.{field}", max="100", color="level", bg="card")]
    if extra:
        out.append(T(x, y + 20, w - 96, 18, extra, 13, color="muted"))
    return group(f"{source}-{field}", out)


RAM = "{system.ram_used:gb} / {system.ram_total:gb} GB"
system = {"name": "System",
 "portrait": [*header("SYSTEM", 320), *metric(16, 50, 288, "CPU", "cpu"), *metric(16, 130, 288, "RAM", "ram", RAM),
              *metric(16, 210, 288, "DISK", "disk"), T(16, 290, 120, 20, "CORES", 16, True, "muted"),
              W("cores", 16, 316, 288, 60, color="accent", bg="card"),
              T(16, 392, 150, 24, "↓ {system.down:bytes}/s", 18),
              T(154, 392, 150, 24, "↑ {system.up:bytes}/s", 18, align="right"),
              T(16, 446, 288, 20, "up for {system.uptime:hm}", 14, color="muted")],
 "landscape": [*header("SYSTEM", 480), *metric(16, 44, 216, "CPU", "cpu"), *metric(16, 120, 216, "RAM", "ram", RAM),
               *metric(16, 196, 216, "DISK", "disk"), T(256, 36, 120, 20, "CORES", 16, True, "muted"),
               W("cores", 256, 62, 208, 120, color="accent", bg="card"),
               T(256, 200, 208, 26, "↓ {system.down:bytes}/s", 18), T(256, 230, 208, 26, "↑ {system.up:bytes}/s", 18),
               T(256, 284, 208, 20, "up for {system.uptime:hm}", 14, color="muted")]}


# --- hardware (LibreHardwareMonitor)
def gauge(x, y, s, label, value, field, unit, maxv):
    return group(f"hw-{label}", [
        W("ring", x, y, s, s, field=field, max=str(maxv), thickness=12, color="level", bg="card"),
        T(x, y + s // 2 - 18, s, 30, value + unit, 24, True, align="center", fallback="–"),
        T(x, y + s // 2 + 10, s, 18, label, 12, color="muted", align="center")])


def hw_rows(x, y, w):
    rows = [("GPU", "{hardware.gpu.name}"), ("Hot spot", "{hardware.gpu.hotspot:.0f}°C"),
            ("VRAM", "{hardware.gpu.vram_used:.0f} / {hardware.gpu.vram_total:.0f} MB"),
            ("GPU power", "{hardware.gpu.power:.0f} W"), ("GPU clock", "{hardware.gpu.clock:.0f} MHz"),
            ("CPU power", "{hardware.cpu.power:.0f} W")]
    out = []
    for i, (label, value) in enumerate(rows):
        out += [T(x, y + i * 26, 72, 22, label, 13, color="muted"),
                T(x + 72, y + i * 26, w - 72, 22, value, 14, True, align="right", fallback="–")]
    return out


hardware = {"name": "Hardware",
 "portrait": [*header("HARDWARE", 320),
              *gauge(16, 40, 136, "CPU temp", "{hardware.cpu.temp:.0f}", "hardware.cpu.temp", "°", 100),
              *gauge(168, 40, 136, "GPU temp", "{hardware.gpu.temp:.0f}", "hardware.gpu.temp", "°", 100),
              *gauge(16, 186, 136, "CPU load", "{hardware.cpu.load:.0f}", "hardware.cpu.load", "%", 100),
              *gauge(168, 186, 136, "GPU load", "{hardware.gpu.load:.0f}", "hardware.gpu.load", "%", 100),
              *hw_rows(16, 324, 288)],
 "landscape": [*header("HARDWARE", 480),
               *gauge(12, 36, 112, "CPU temp", "{hardware.cpu.temp:.0f}", "hardware.cpu.temp", "°", 100),
               *gauge(130, 36, 112, "GPU temp", "{hardware.gpu.temp:.0f}", "hardware.gpu.temp", "°", 100),
               *gauge(12, 158, 112, "CPU load", "{hardware.cpu.load:.0f}", "hardware.cpu.load", "%", 100),
               *gauge(130, 158, 112, "GPU load", "{hardware.gpu.load:.0f}", "hardware.gpu.load", "%", 100),
               *hw_rows(260, 44, 204),
               W("history", 260, 212, 204, 92, field="hardware.gpu.load", seconds=120, min="0", max="100",
                 color="accent", fill=True, bg="card")]}


# --- media: big cover, title and artist, tiny progress line
def media_bits(x, y, w):
    return group("progress", [W("bar", x, y, w, 3, field="media.position", max="media.duration", color="fg", bg="muted"),
                              T(x, y + 6, 50, 14, "{media.position:mmss}", 11, color="muted"),
                              T(x + w - 50, y + 6, 50, 14, "{media.duration:mmss}", 11, color="muted", align="right"),
                              W("play", x + w // 2 - 5, y + 8, 10, 10, color="muted")])


def title(x, y, w, size, align):
    return W("marquee", x, y, w, size + 14, text="{media.title}", size=size, bold=True, color="fg", speed=40,
             align=align, fallback="Nothing playing")


media = {"name": "Media",
 "portrait": [W("backdrop", 0, 0, 320, 480, blur=18, dim=0.55), W("cover", 24, 20, 272, 272, radius=20),
              title(16, 306, 288, 26, "center"),
              T(16, 346, 288, 30, "{media.artist}", 20, color="muted", align="center"),
              T(16, 376, 288, 22, "{media.album}", 14, color="muted", align="center"),
              *media_bits(48, 440, 224)],
 "landscape": [W("backdrop", 0, 0, 480, 320, blur=18, dim=0.55), W("cover", 16, 16, 288, 288, radius=20),
               title(320, 96, 148, 24, "left"),
               T(320, 138, 148, 30, "{media.artist}", 19, color="muted"),
               T(320, 168, 148, 22, "{media.album}", 14, color="muted"),
               *media_bits(320, 278, 144)]}


# --- coding agent: one copy of this page per active session (Claude Code, Codex)
def stats(x, y, cw):
    cells = [("{agent.output_tokens:human}", "output"), ("{agent.turns}", "turns"),
             ("${agent.cost:.2f}", "cost{agent.cost:hide}")]
    out = []
    for i, (v, lab) in enumerate(cells):
        out += [T(x + i * cw, y, cw, 26, v, 20, True, align="center"),
                T(x + i * cw, y + 26, cw, 16, lab, 12, color="muted", align="center")]
    return group("stats", out)


def limits(x, y, w):
    out = []
    for i in range(2):
        f = f"agent.limits.{i}"
        yy = y + i * 38
        out += group(f"limit-{i}", [
            T(x, yy, w - 110, 20, "Limit {" + f + ".label}  {" + f + ".pct:.0f}%", 13, True),
            T(x + w - 110, yy, 110, 20, "reset {" + f + ".resets_at:reset}", 12, color="muted", align="right"),
            W("bar", x, yy + 22, w, 8, field=f + ".pct", max="100", color="level", bg="card")])
    return out


def ring(x, y, s):
    return group("context", [
        W("ring", x, y, s, s, field="agent.context_pct", max="100", thickness=14, color="level", bg="card"),
        T(x, y + s // 2 - 30, s, 44, "{agent.context_pct:.0f}%", 38, True, align="center"),
        T(x, y + s // 2 + 14, s, 20, "{agent.context:human} / {agent.window:human}", 13, color="muted", align="center"),
        T(x, y + s + 4, s, 18, "context", 13, color="muted", align="center")])


def who(x, w):
    return group("who", [T(x, 36, w, 28, "{agent.project}", 20, True, fallback="No active session"),
                         T(x, 64, w, 20, "{agent.model}", 13, color="muted")])


agent = {"name": "Agent", "per_agent": True,
 "portrait": [*header("{agent.title}", 320), W("mascot", 12, 34, 116, 68, agent="agent.agent", busy="agent.busy", color="auto"),
              *who(136, 168), *ring(88, 110, 144), *stats(16, 284, 96), *limits(16, 332, 288),
              W("agents", 12, 410, 296, 66, start=0, row=34)],
 "landscape": [*header("{agent.title}", 480), W("mascot", 10, 32, 108, 64, agent="agent.agent", busy="agent.busy", color="auto"),
               *who(126, 338), *ring(24, 104, 140), *stats(200, 92, 88), *limits(200, 142, 264),
               W("agents", 200, 222, 264, 92, start=0, row=30)]}

# --- weather with animation
DET = "Feels like {weather.feels:.0f}° · Humidity {weather.humidity}% · Wind {weather.wind:.0f} km/h"
weather = {"name": "Weather",
 "portrait": [*header("WEATHER", 320),
              W("weather_anim", 56, 34, 208, 116, field="weather.code", intensity=22),
              T(0, 150, 178, 80, "{weather.temp:.0f}°", 64, True, align="right", fallback="Waiting for data…"),
              *group("city", [W("emoji", 186, 179, 22, 22, char="📍"),
                              T(212, 172, 102, 36, "{weather.city}", 17, True)]),
              T(0, 222, 320, 30, "{weather.code:weather}", 20, color="accent", align="center"),
              T(0, 256, 320, 20, DET, 12, color="muted", align="center"),
              *[W("forecast", 16 + i * 73, 290, 69, 174, index=i + 1, radius=10) for i in range(4)]],
 "landscape": [*header("WEATHER", 480),
               W("weather_anim", 16, 30, 150, 110, field="weather.code", intensity=20),
               T(156, 36, 140, 76, "{weather.temp:.0f}°", 60, True, align="right", fallback="Waiting for data…"),
               *group("city", [W("emoji", 302, 63, 22, 22, char="📍"),
                               T(328, 56, 140, 36, "{weather.city}", 17, True)]),
               T(180, 106, 288, 28, "{weather.code:weather}", 19, color="accent"),
               T(24, 144, 432, 18, DET, 12, color="muted", align="center"),
               *[W("forecast", 16 + i * 113, 168, 108, 140, index=i + 1, radius=10) for i in range(4)]]}

# --- stocks
stocks = {"name": "Markets",
 "portrait": [*header("MARKETS", 320), W("markets", 12, 36, 296, 436, list_up_to=5, max=12, gap=8, radius=10)],
 "landscape": [*header("MARKETS", 480), W("markets", 12, 32, 456, 282, list_up_to=5, max=12, gap=6, radius=10)]}

# --- calendar and notifications
agenda = {"name": "Agenda",
 "portrait": [*header("CALENDAR", 320, "{date.day} {date.month}"), W("agenda", 12, 40, 296, 432, start=0, row=52)],
 "landscape": [*header("CALENDAR", 480, "{date.weekday} {date.day} {date.month}"),
               W("agenda", 12, 36, 456, 276, start=0, row=40)]}
notifications = {"name": "Notifications",
 "portrait": [*header("NOTIFICATIONS", 320), W("notifications", 12, 40, 296, 432, row=62)],
 "landscape": [*header("NOTIFICATIONS", 480), W("notifications", 12, 36, 456, 276, row=56)]}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for page_id, data in dict(clock=clock, system=system, hardware=hardware, media=media, claude=agent,
                              weather=weather, stocks=stocks, agenda=agenda, notifications=notifications).items():
        (OUT / f"{page_id}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print("written", len(list(OUT.glob("*.json"))), "layouts to", OUT)
