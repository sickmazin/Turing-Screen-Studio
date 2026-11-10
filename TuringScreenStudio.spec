# PyInstaller spec: pyinstaller TuringScreenStudio.spec --noconfirm  ->  dist/TuringScreenStudio/TuringScreenStudio.exe
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
sys.path.insert(0, str(ROOT))
BUILD = ROOT / "build"
BUILD.mkdir(exist_ok=True)

# icon = the tray icon, drawn by the app itself
from main import tray_icon_image  # noqa: E402
ICON = BUILD / "icon.ico"
tray_icon_image().save(ICON, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

if not (ROOT / "vendor" / "lhm" / "LibreHardwareMonitorLib.dll").exists():
    raise SystemExit("run python tools/fetch_lhm.py first")

hidden = (collect_submodules("sources") + collect_submodules("pages")  # loaded with pkgutil at runtime
          + ["pystray._win32", "clr", "settings", "main", "editor"])
datas = [(str(ROOT / "defaults"), "defaults"), (str(ROOT / "vendor" / "lhm"), "vendor/lhm")]
datas += collect_data_files("icalendar") + collect_data_files("recurring_ical_events")

a = Analysis([str(ROOT / "app.py")], pathex=[str(ROOT)], hiddenimports=hidden, datas=datas,
             excludes=["pytest", "unittest.mock", "pydoc"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TuringScreenStudio", console=False,
          icon=str(ICON), uac_admin=True, version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="TuringScreenStudio")
