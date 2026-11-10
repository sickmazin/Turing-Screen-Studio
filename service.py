"""Start/stop the screen app and run it at logon (used by the settings window and the tray)."""
import os
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path
from xml.sax.saxutils import escape

import psutil

import paths

TASK_NAME = paths.APP_NAME
NO_WINDOW = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
LEGACY_RUN = (r"Software\Microsoft\Windows\CurrentVersion\Run", "Schermetto")
EXE_NAME = "TuringScreenStudio.exe"


def _pythonw():
    venv = paths.ROOT / ".venv" / "Scripts" / "pythonw.exe"
    return str(venv if venv.exists() else Path(sys.executable).with_name("pythonw.exe"))


def command(settings=False):
    """How to launch the screen app (or the settings window), frozen or from source."""
    if paths.FROZEN:
        return [sys.executable] + (["--settings"] if settings else [])
    return [_pythonw(), str(paths.ROOT / ("settings.py" if settings else "main.py"))]


def running_pid():
    try:
        pid = int(paths.PIDFILE.read_text())
        p = psutil.Process(pid)
        try:
            args = p.cmdline()
            if any(a.endswith("main.py") for a in args) or (Path(args[0]).name == EXE_NAME and "--settings" not in args):
                return pid
        except psutil.AccessDenied:  # elevated process seen from a normal one: trust the pid file and the name
            if p.name().lower() in (EXE_NAME.lower(), "python.exe", "pythonw.exe"):
                return pid
    except (OSError, ValueError, IndexError, psutil.Error):
        pass
    return None


def start():
    if not running_pid():
        paths.STOPFLAG.unlink(missing_ok=True)
        subprocess.Popen(command(), cwd=paths.ROOT, creationflags=NO_WINDOW)


def stop(timeout=6.0):
    """Ask the app to quit (it switches the screen off); kill it if it does not answer."""
    pid = running_pid()
    if not pid:
        return
    paths.STOPFLAG.touch()
    try:
        p = psutil.Process(pid)
        p.wait(timeout)
    except psutil.TimeoutExpired:
        try:
            p.kill()
        except psutil.Error:
            pass
    except psutil.Error:
        pass
    paths.STOPFLAG.unlink(missing_ok=True)


def restart():
    stop()
    time.sleep(0.5)
    start()


def open_settings():
    subprocess.Popen(command(settings=True), cwd=paths.ROOT, creationflags=NO_WINDOW)


def is_admin() -> bool:
    import ctypes
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{user}</UserId><Delay>PT10S</Delay></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType>
    <RunLevel>{level}</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>{cmd}</Command><Arguments>{args}</Arguments>
    <WorkingDirectory>{cwd}</WorkingDirectory></Exec></Actions>
</Task>
"""


def _schtasks(*args):
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)


def get_autostart() -> bool:
    return _schtasks("/Query", "/TN", TASK_NAME).returncode == 0


def set_autostart(on: bool) -> str:
    """Logon task with the highest privileges when possible (sensors need admin). Returns an error message or ''."""
    _remove_legacy_run_key()
    if not on:
        _schtasks("/Delete", "/TN", TASK_NAME, "/F")
        return ""
    cmd = command()
    xml = TASK_XML.format(user=escape(f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}"),
                          level="HighestAvailable" if is_admin() else "LeastPrivilege",
                          cmd=escape(cmd[0]), args=escape(" ".join(f'"{a}"' for a in cmd[1:])), cwd=escape(str(paths.ROOT)))
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f:
        f.write(xml)
    try:
        r = _schtasks("/Create", "/F", "/TN", TASK_NAME, "/XML", f.name)
    finally:
        os.unlink(f.name)
    return "" if r.returncode == 0 else (r.stderr or r.stdout).strip()


def _remove_legacy_run_key():
    """Older versions used the registry Run key, which cannot start an elevated app."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, LEGACY_RUN[0], 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, LEGACY_RUN[1])
    except OSError:
        pass
