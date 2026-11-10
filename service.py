"""Avvio/arresto dell'app dello schermo e avvio automatico al login (usato da settings.py e dalla tray)."""
import subprocess
import sys
import time
import winreg
from pathlib import Path

import psutil

ROOT = Path(__file__).parent
PIDFILE = ROOT / "schermetto.pid"
STOPFLAG = ROOT / "stop.flag"
LOG = ROOT / "schermetto.log"
_pyw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
PYTHONW = str(_pyw if _pyw.exists() else Path(sys.executable).with_name("pythonw.exe"))
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Schermetto"
NO_WINDOW = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP


def running_pid():
    try:
        pid = int(PIDFILE.read_text())
        if any(a.endswith("main.py") for a in psutil.Process(pid).cmdline()):
            return pid
    except (OSError, ValueError, psutil.Error):
        pass
    return None


def start():
    if not running_pid():
        STOPFLAG.unlink(missing_ok=True)
        subprocess.Popen([PYTHONW, str(ROOT / "main.py")], cwd=ROOT, creationflags=NO_WINDOW)


def stop(timeout=6.0):
    """Chiede all'app di chiudersi (spegne lo schermo); se non risponde la termina."""
    pid = running_pid()
    if not pid:
        return
    STOPFLAG.touch()
    try:
        p = psutil.Process(pid)
        p.wait(timeout)
    except psutil.TimeoutExpired:
        p.kill()
    except psutil.Error:
        pass
    STOPFLAG.unlink(missing_ok=True)


def restart():
    stop()
    time.sleep(0.5)
    start()


def open_settings():
    subprocess.Popen([PYTHONW, str(ROOT / "settings.py")], cwd=ROOT, creationflags=NO_WINDOW)


def autostart_command():
    return f'"{PYTHONW}" "{ROOT / "main.py"}"'


def get_autostart() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, RUN_NAME)[0] == autostart_command()
    except OSError:
        return False


def set_autostart(on: bool):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass
