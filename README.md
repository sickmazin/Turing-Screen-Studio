# Turing Screen Studio

A replacement for the stock *UsbMonitor / TURZX* software of the **Turing Smart Screen 3.5"** (USB `1A86:5722`,
serial `USB35INCHIPSV2`), written in Python. Pages are layouts of widgets you build with a drag & drop editor:
clock, system, hardware sensors, media player, Claude Code / Codex / Gemini sessions, weather, markets, calendar,
Windows notifications, or anything you compose yourself.

## Features

- **Pages made of widgets**, edited with drag & drop: move, resize, multi-select, group, alignment guides,
  undo, separate portrait and landscape layouts, "show on screen".
- **Live data sources**: system (psutil), hardware sensors (LibreHardwareMonitor), media (Windows SMTC, with cover),
  weather (Open-Meteo), stocks (Yahoo), iCal calendars, Windows notifications, Claude Code, Codex CLI, Gemini CLI.
- **Light animations**: animated weather (turning sun, drifting clouds, rain, snow, lightning, fog),
  scrolling text, animated GIF / APNG / WebP (e.g. animated emoji).
- **Themes** (colours, fonts, per-page backgrounds) and **pages** can be exported and shared as
  `.tss-theme` / `.tss-page` files.
- **Italian and English UI** (`i18n.py`; add a language by adding a table).
- Everything applies **live**: the screen app watches config, theme and layout files.
- Tray icon (pages, brightness, settings), start at sign-in, screen off when the PC is locked,
  notification when the USB screen is missing.

## Running from source

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python tools\fetch_lhm.py      # LibreHardwareMonitorLib into vendor\lhm
.venv\Scripts\python main.py                 # screen app (tray icon)
.venv\Scripts\python settings.py             # settings window
.venv\Scripts\python -m unittest discover -s tests -t .
```

Close `UsbMonitor.exe` first: only one program can use the screen. CPU temperatures need administrator rights
(LibreHardwareMonitor's driver); everything else works without.

## Building the .exe

```powershell
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\pyinstaller TuringScreenStudio.spec --noconfirm
```

Output: `dist\TuringScreenStudio\TuringScreenStudio.exe` (one folder, asks for administrator rights).
`TuringScreenStudio.exe --settings` opens the settings window.

## Where things are

| Path | What |
|---|---|
| `main.py` | screen app: loop, live reload, partial updates, tray |
| `screen.py` | serial protocol of the rev. A screen (6-byte commands, RGB565 little-endian) |
| `layout.py`, `widgets.py` | layout pages and the widget library |
| `sources/*.py` | data sources; each one is `name`, `settings`, `interval`, `async fetch(cfg)` |
| `pages/*.py` | optional pages written in Python (`name`, `needs`, `render(state, size, cfg)`) |
| `settings.py`, `editor.py` | settings window and page editor (Tkinter) |
| `i18n.py` | translations |
| `defaults/` | config, layouts and themes copied to the data folder on first run |
| `%APPDATA%\TuringScreenStudio` | user data: `config.json`, `layouts/`, `themes/`, `studio.log` |
| `tools/` | default layout generator, preview renderer, LHM downloader, translation checker |

### Data fields

Widget texts use `{path:format}`: `{system.cpu:.0f}%`, `{hardware.gpu.temp:.0f}°`, `{stocks.0.price:,.2f}`,
`{claude.0.context_pct:.0f}%`, `{agents.0.project}`, `{now:%H:%M}`. Extra formats: `mmss`, `hm`, `human`,
`bytes`, `gb`, `weather`, `weekday`, `reset`, `hide`. The editor lists every field available with live data.

### Claude Code status line (optional)

Cost, real context size and plan limits come from Claude Code's status line. In `~/.claude/settings.json`:

```json
"statusLine": {"type": "command", "command": "<path>\\.venv\\Scripts\\python.exe <path>\\claude_statusline.py"}
```

## Performance notes

The screen accepts about 157 KB/s. A full frame (320×480×2 bytes) takes ~2 s, so only the changed rectangle
is sent each tick: a clock costs ~40 ms. Animations are as smooth as their area allows (a 200×110 weather
animation runs at ~3–4 fps).

## Roadmap

- [ ] **Page rules**: show a page when a condition holds (e.g. Claude page while a session is working,
      weather only in the morning, lower brightness in the evening, media page only while playing).
- [ ] **Tablet / smartphone as a screen**: a network display backend next to `screen.py` (local web server,
      frames pushed over WebSocket to a browser page, no app to install), chosen in the settings; layouts
      rendered with a scale factor for the device resolution; swipe to change page; optionally USB screen and
      tablet together. No USB bandwidth limit, so animations could run at 20–30 fps.
- [ ] Temperature of disks and fan curves on the hardware page (sensors are already in `hardware.sensors`).
- [ ] Installer (Inno Setup) on top of the PyInstaller folder.
- [ ] More languages.

## Licences

LibreHardwareMonitorLib is MPL-2.0 and is downloaded from its official release, not stored in this repository.
The screen protocol was reimplemented from the documented behaviour of
[turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python) (GPL-3.0); no code is copied.
