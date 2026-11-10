"""Downloads LibreHardwareMonitorLib (MPL-2.0) from the official GitHub release into vendor/lhm.

Run once after cloning: python tools/fetch_lhm.py
"""
import io
import shutil
import sys
import zipfile
from pathlib import Path

import requests

VERSION = "v0.9.6"
URL = f"https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/{VERSION}/LibreHardwareMonitor.zip"
DEST = Path(__file__).resolve().parent.parent / "vendor" / "lhm"
SKIP = ("Aga.", "OxyPlot")  # GUI-only libraries of the LibreHardwareMonitor app


def main():
    if (DEST / "LibreHardwareMonitorLib.dll").exists() and "--force" not in sys.argv:
        print(f"already present in {DEST} (use --force to download again; close the app first)")
        return
    r = requests.get(URL, timeout=120)
    r.raise_for_status()
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for info in z.infolist():
            name = Path(info.filename).name
            if name.endswith(".dll") and "/" not in info.filename.strip("/") and not name.startswith(SKIP):
                (DEST / name).write_bytes(z.read(info))
    print(f"{len(list(DEST.glob('*.dll')))} DLLs from LibreHardwareMonitor {VERSION} in {DEST}")


if __name__ == "__main__":
    sys.exit(main())
