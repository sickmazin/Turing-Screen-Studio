"""Renderizza tutte le pagine attive in preview/<pagina>.png senza bisogno dello schermo."""
import asyncio

import ui
from main import ROOT, App, load_config
from screen import Screen


async def main():
    app = App()
    app.cfg = load_config()
    ui.load_theme(app.cfg.get("theme", "scuro"))
    names = [n for n in app.cfg["pages"] if n in app.all_pages]
    for n in {s for p in names for s in app.all_pages[p].needs}:
        try:
            app.state[n] = await app.all_sources[n].fetch(app.section(n))
        except Exception as e:
            print(f"source {n}: {e!r}")
    size = Screen(orientation=app.cfg.get("orientation", "portrait")).size
    out = ROOT / "preview"
    out.mkdir(exist_ok=True)
    for n in names:
        app.all_pages[n].render(app.state, size, app.section(n)).save(out / f"{n}.png")
        print("ok", n)


asyncio.run(main())
