"""Schermetto: mostra pagine sul Turing Smart Screen 3.5".

Avvio con finestra: .venv\\Scripts\\python main.py   ·   senza finestra: .venv\\Scripts\\pythonw main.py
Le modifiche a config.json e al tema attivo vengono applicate dal vivo.
"""
import asyncio
import ctypes
import importlib
import json
import logging
import os
import pkgutil
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import keyboard
import serial
from PIL import Image, ImageChops, ImageDraw

import layout
import pages
import service
import sources
import ui
from screen import Screen

ROOT = Path(__file__).parent
CONFIG = ROOT / "config.json"
log = logging.getLogger("schermetto")


def load(pkg) -> dict:
    """Importa ogni file del package: aggiungere una pagina = aggiungere un file."""
    mods = (importlib.import_module(f"{pkg.__name__}.{m.name}") for m in pkgutil.iter_modules(pkg.__path__))
    return {m.name: m for m in mods}


def load_pages() -> dict:
    """Pagine in codice (pages/*.py) + pagine a layout (layouts/*.json)."""
    return {**load(pages), **layout.load_layouts()}


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def is_locked() -> bool:
    """True se Windows è sul blocco schermo: SwitchDesktop fallisce quando il desktop di input non è il nostro."""
    user32 = ctypes.windll.user32
    h = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
    if not h:
        return True
    try:
        return not user32.SwitchDesktop(h)
    finally:
        user32.CloseDesktop(h)


def _mtime(p: Path):
    try:
        return p.stat().st_mtime
    except OSError:
        return None


class App:
    def __init__(self):
        self.cfg = {}
        self.state = {}
        self.tasks = {}
        self.all_pages = load_pages()
        self.all_sources = load(sources)
        self.pages = []
        self.screen = Screen()
        self.idx = 0
        self.last_switch = time.monotonic()
        self.was_playing = False
        self.screen_off = False
        self.running = True
        self.stamp = None
        self.prev = None
        self.wake = asyncio.Event()
        self.loop = None

    # --- configurazione -------------------------------------------------
    def section(self, name: str) -> dict:
        """Impostazioni di una pagina/source: predefiniti della pagina + config.json."""
        mod = self.all_sources.get(name) or self.all_pages.get(name)
        defaults = getattr(mod, "settings", {})
        return {**defaults, **self.cfg.get(name, {})}

    def _stamp(self):
        return (_mtime(CONFIG), _mtime(ui.THEMES / self.cfg.get("theme", "scuro") / "theme.json"), layout.stamp())

    def check_reload(self):
        stamp = self._stamp()
        if stamp == self.stamp:
            return
        try:
            cfg = load_config()
        except (OSError, ValueError) as e:
            log.warning("config.json non leggibile, tengo la precedente: %s", e)
            self.stamp = stamp
            return
        self.apply(cfg)
        self.stamp = self._stamp()
        log.info("configurazione applicata")

    def apply(self, cfg: dict):
        self.cfg = cfg
        ui.load_theme(cfg.get("theme", "scuro"))
        self.all_pages = load_pages()
        names = cfg.get("pages") or ["clock"]
        unknown = [n for n in names if n not in self.all_pages]
        if unknown:
            log.warning("pagine sconosciute ignorate: %s", unknown)
        self.pages = [self.all_pages[n] for n in names if n in self.all_pages] or list(self.all_pages.values())[:1]
        self.idx = min(self.idx, len(self.pages) - 1)

        needed = {n for p in self.pages for n in p.needs if n in self.all_sources}
        for n in set(self.tasks) - needed:
            self.tasks.pop(n).cancel()
        for n in needed - set(self.tasks):
            self.tasks[n] = asyncio.create_task(self.poll(n))

        s = self.screen
        port, orient, bright = cfg.get("port", "AUTO"), cfg.get("orientation", "portrait"), cfg.get("brightness", 40)
        if (port, orient) != (s.port, s.orientation):
            s.port, s.orientation, s.brightness = port, orient, bright
            s.close()  # si riapre al prossimo giro con i nuovi parametri
        elif bright != s.brightness:
            s.brightness = bright
            if s.ser and not self.screen_off:
                try:
                    s.set_brightness(bright)
                except (serial.SerialException, OSError):
                    s.close()
        self.prev = None

        for h in getattr(self, "hotkeys", []):  # unhook_all_hotkeys() di keyboard crasha se non ce ne sono
            keyboard.remove_hotkey(h)
        self.hotkeys = []
        for key, default, step in (("key_next", "ctrl+shift+right", 1), ("key_prev", "ctrl+shift+left", -1)):
            try:
                self.hotkeys.append(keyboard.add_hotkey(cfg.get(key, default), self.go, args=(step,)))
            except ValueError as e:
                log.warning("scorciatoia non valida %s: %s", key, e)

    # --- navigazione ----------------------------------------------------
    def go(self, step: int):
        """Chiamabile da altri thread (tastiera, tray)."""
        def _go():
            self.idx = (self.idx + step) % len(self.pages)
            self.last_switch = time.monotonic()
            self.wake.set()
        self.loop.call_soon_threadsafe(_go)

    def quit(self):
        def _quit():
            self.running = False
            self.wake.set()
        self.loop.call_soon_threadsafe(_quit)

    def auto_switch(self):
        media = self.state.get("media")
        playing = bool(media and media["playing"])
        if self.cfg.get("media_focus", True) and playing and not self.was_playing:
            for i, p in enumerate(self.pages):
                if p.name == "media":
                    self.idx, self.last_switch = i, time.monotonic()
        self.was_playing = playing
        rotate = self.cfg.get("rotate_seconds", 0)
        if rotate and time.monotonic() - self.last_switch >= rotate:
            self.idx = (self.idx + 1) % len(self.pages)
            self.last_switch = time.monotonic()

    # --- ciclo principale -----------------------------------------------
    async def poll(self, name: str):
        src = self.all_sources[name]
        while True:
            scfg = self.section(name)
            try:
                self.state[name] = await src.fetch(scfg)
            except Exception as e:  # rete giù, app chiusa, ecc.: tengo l'ultimo dato buono
                log.warning("source %s: %r", name, e)
            await asyncio.sleep(scfg.get("interval", src.interval))

    async def tick(self):
        if not self.screen.ser:
            await asyncio.to_thread(self.screen.open)
            log.info("schermo connesso su %s", self.screen.ser.port)
            self.prev, self.screen_off = None, False
        if self.cfg.get("off_when_locked", True) and is_locked():
            if not self.screen_off:
                self.screen.power(False)
                self.screen_off = True
            return
        if self.screen_off:
            self.screen.power(True)
            self.screen_off, self.prev = False, None
        self.auto_switch()
        page = self.pages[self.idx]
        try:
            img = page.render(self.state, self.screen.size, self.section(page.name))
        except Exception:
            log.exception("errore nella pagina %s", page.name)
            return
        # invio solo il rettangolo cambiato: un frame intero costa ~2 s, un orologio ~40 ms
        box = (0, 0, *img.size) if self.prev is None else ImageChops.difference(img, self.prev).getbbox()
        if box:
            await asyncio.to_thread(self.screen.show, img.crop(box), box[0], box[1])
        self.prev = img

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.check_reload()
        while self.running:
            if service.STOPFLAG.exists():
                service.STOPFLAG.unlink(missing_ok=True)
                break
            self.check_reload()
            try:
                await self.tick()
            except (serial.SerialException, OSError) as e:
                log.warning("schermo non disponibile (%s), riprovo tra 3 s", e)
                self.screen.close()
                await asyncio.sleep(3)
                continue
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), 1 - time.time() % 1)  # un giro al secondo, allineato
            except TimeoutError:
                pass
        try:
            if self.screen.ser:
                self.screen.power(False)
        except (serial.SerialException, OSError):
            pass
        self.screen.close()


def start_tray(app: App):
    import pystray
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 2, 56, 62), 8, fill=(110, 170, 255))
    d.rectangle((14, 8, 50, 50), fill=(12, 14, 20))
    menu = pystray.Menu(
        pystray.MenuItem("Impostazioni", lambda: service.open_settings(), default=True),
        pystray.MenuItem("Pagina successiva", lambda: app.go(1)),
        pystray.MenuItem("Pagina precedente", lambda: app.go(-1)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Esci", lambda: app.quit()),
    )
    icon = pystray.Icon("schermetto", img, "Schermetto", menu)
    icon.run_detached()
    return icon


def main():
    handlers = [RotatingFileHandler(service.LOG, maxBytes=1_000_000, backupCount=1, encoding="utf-8")]
    if sys.stderr:  # con pythonw non c'è console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)
    other = service.running_pid()
    if other and other != os.getpid():
        log.info("già in esecuzione (pid %s)", other)
        return
    service.PIDFILE.write_text(str(os.getpid()))
    app = App()
    icon = None
    try:
        async def run():
            nonlocal icon
            app.loop = asyncio.get_running_loop()
            icon = start_tray(app)
            await app.run()
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    finally:
        if icon:
            icon.stop()
        service.PIDFILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
