"""Builds the exe without ever leaving dist/ half-replaced. Run: python tools/build.py

PyInstaller deletes the old folder before copying the new one, so a running TuringScreenStudio.exe (often the
settings window) leaves dist/ broken. Here the build goes to build/fresh first, and dist/ is swapped only if
nothing is using it; otherwise the new build stays in build/fresh and dist/ keeps working.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "TuringScreenStudio"
FRESH = ROOT / "build" / "fresh"
OLD = ROOT / "dist" / "TuringScreenStudio-old"


def main():
    if FRESH.exists():
        shutil.rmtree(FRESH)
    subprocess.run([sys.executable, "-m", "PyInstaller", str(ROOT / "TuringScreenStudio.spec"), "--noconfirm",
                    "--distpath", str(FRESH)], cwd=ROOT, check=True)
    if OLD.exists():
        shutil.rmtree(OLD, ignore_errors=True)
    try:
        if DIST.exists():
            DIST.rename(OLD)  # fails while any file inside is open
    except OSError:
        print(f"dist is in use (close TuringScreenStudio.exe): the new build is in {FRESH / 'TuringScreenStudio'}")
        return 1
    (FRESH / "TuringScreenStudio").rename(DIST)
    shutil.rmtree(OLD, ignore_errors=True)
    print(f"built {DIST / 'TuringScreenStudio.exe'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
