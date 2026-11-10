"""Where code, bundled defaults and user data live.

User data goes to %APPDATA%\\TuringScreenStudio so the app also works when installed in Program Files.
Set TSS_DATA to use another folder (tests do this).
"""
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Turing Screen Studio"
FROZEN = getattr(sys, "frozen", False)
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))  # code and bundled files
DEFAULTS = ROOT / "defaults"
VENDOR = ROOT / "vendor"
DATA = Path(os.environ.get("TSS_DATA") or Path(os.environ.get("APPDATA", Path.home())) / "TuringScreenStudio")

CONFIG = DATA / "config.json"
LAYOUTS = DATA / "layouts"
ASSETS = LAYOUTS / "assets"
THEMES = DATA / "themes"
LOG = DATA / "studio.log"
PIDFILE = DATA / "studio.pid"
STOPFLAG = DATA / "stop.flag"
CONTROL = DATA / "control.json"   # one-shot commands from the settings window (e.g. show a page)
CLAUDE_DUMPS = DATA / "claude"    # JSON written by claude_statusline.py


def ensure_data():
    """Create the data folder on first run, seeded with the bundled defaults."""
    DATA.mkdir(parents=True, exist_ok=True)
    if not CONFIG.exists():
        shutil.copy(DEFAULTS / "config.json", CONFIG)
    for sub in ("layouts", "themes"):
        if not (DATA / sub).exists():
            shutil.copytree(DEFAULTS / sub, DATA / sub)
