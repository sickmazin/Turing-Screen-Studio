"""Renders every page of the current setup with live data into one PNG per orientation, without the screen.

Run: python tools/preview.py [output folder]   (animated widgets are shown at the current instant)
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

import i18n  # noqa: E402
import layout  # noqa: E402
import paths  # noqa: E402
import ui  # noqa: E402
from main import App, load_config  # noqa: E402


async def collect(app):
    for name, src in app.all_sources.items():
        try:
            app.state[name] = await src.fetch(app.section(name))
        except Exception as e:
            print(f"source {name}: {e!r}")


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "preview"
    out.mkdir(parents=True, exist_ok=True)
    paths.ensure_data()
    app = App()
    app.cfg = load_config()
    i18n.set_language(app.cfg.get("language", "it"))
    ui.load_theme(app.cfg.get("theme", "dark"))
    asyncio.run(collect(app))
    names = [n for n in app.cfg.get("pages", []) if n in app.all_pages]
    for orient, size in layout.SIZES.items():
        cols = 5
        sheet = Image.new("RGB", (cols * (size[0] + 10), -(-len(names) // cols) * (size[1] + 10)), "white")
        for i, n in enumerate(names):
            img = app.all_pages[n].render(app.state, size, {})
            sheet.paste(img, ((i % cols) * (size[0] + 10), (i // cols) * (size[1] + 10)))
        sheet.save(out / f"{orient}.png")
        print("saved", out / f"{orient}.png")


if __name__ == "__main__":
    main()
