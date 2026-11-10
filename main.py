"""Turing Screen Studio: shows pages on the Turing Smart Screen 3.5".

Run with a console: python main.py   ·   without one: pythonw main.py   ·   frozen: TuringScreenStudio.exe
Changes to config.json, to the active theme and to layouts are applied live.
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

import keyboard
import serial
from PIL import Image, ImageChops, ImageDraw

import i18n
import layout
import pages
import paths
import service
import sources
import ui
from screen import Screen

log = logging.getLogger("studio")
USB_ALERT_AFTER = 30  # seconds without the screen before the tray shows a notification


def load(pkg) -> dict:
    """Import every module of a package: adding a page or source = adding a file."""
    mods = (importlib.import_module(f"{pkg.__name__}.{m.name}") for m in pkgutil.iter_modules(pkg.__path__))
    return {m.name: m for m in mods}


def load_pages() -> dict:
    """Code pages (pages/*.py) + layout pages (layouts/*.json)."""
    return {**load(pages), **layout.load_layouts()}


def load_config() -> dict:
    return json.loads(paths.CONFIG.read_text(encoding="utf-8"))


def save_config(cfg: dict):
    tmp = paths.CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(paths.CONFIG)  # atomic: readers never see a half-written file


def is_locked() -> bool:
    """True when Windows shows the lock screen: SwitchDesktop fails if the input desktop is not ours."""
    user32 = ctypes.windll.user32
    h = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
    if not h:
        return True
    try:
        return not user32.SwitchDesktop(h)
    finally:
        user32.CloseDesktop(h)


def _mtime(p):
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
        self.pages = []   # pages in config order
        self.view = []    # pages as shown: per-agent layouts expanded to one page per session
        self.screen = Screen()
        self.idx = 0
        self.last_switch = time.monotonic()
        self.was_playing = False
        self.screen_off = False
        self.running = True
        self.stamp = None
        self.prev = None
        self.hotkeys = []
        self.history = layout.HistoryRecorder()
        self.history_view = {}
        self.missing_since = None
        self.alerted = False
        self.icon = None
        self.wake = asyncio.Event()
        self.loop = None

    # --- configuration --------------------------------------------------
    def section(self, name: str) -> dict:
        """Settings of a source or page: module defaults + config.json."""
        mod = self.all_sources.get(name) or self.all_pages.get(name)
        return {**getattr(mod, "settings", {}), **self.cfg.get(name, {})}

    def _stamp(self):
        return (_mtime(paths.CONFIG), _mtime(paths.THEMES / self.cfg.get("theme", "dark") / "theme.json"), layout.stamp())

    def check_reload(self):
        stamp = self._stamp()
        if stamp == self.stamp:
            return
        try:
            cfg = load_config()
        except (OSError, ValueError) as e:
            log.warning("config.json unreadable, keeping the previous one: %s", e)
            self.stamp = stamp
            return
        self.apply(cfg)
        self.stamp = self._stamp()
        log.info("configuration applied")

    def apply(self, cfg: dict):
        self.cfg = cfg
        i18n.set_language(cfg.get("language", "it"))
        ui.load_theme(cfg.get("theme", "dark"))
        self.all_pages = load_pages()
        names = cfg.get("pages") or []
        unknown = [n for n in names if n not in self.all_pages]
        if unknown:
            log.warning("unknown pages ignored: %s", unknown)
        current = self.view[self.idx].name if self.idx < len(self.view) else None
        self.pages = [self.all_pages[n] for n in names if n in self.all_pages] or list(self.all_pages.values())[:1]
        self.view = []
        self.refresh_view(current)

        needed = {n for p in self.pages for n in p.needs if n in self.all_sources}
        for n in set(self.tasks) - needed:
            self.tasks.pop(n).cancel()
        for n in needed - set(self.tasks):
            self.tasks[n] = asyncio.create_task(self.poll(n))

        s = self.screen
        port, orient, bright = cfg.get("port", "AUTO"), cfg.get("orientation", "portrait"), cfg.get("brightness", 40)
        if (port, orient) != (s.port, s.orientation):
            s.port, s.orientation, s.brightness = port, orient, bright
            s.close()  # reopened on the next tick with the new parameters
        elif bright != s.brightness:
            s.brightness = bright
            if s.ser and not self.screen_off:
                try:
                    s.set_brightness(bright)
                except (serial.SerialException, OSError):
                    s.close()
        self.prev = None

        for h in self.hotkeys:  # keyboard.unhook_all_hotkeys() crashes when none are registered
            keyboard.remove_hotkey(h)
        self.hotkeys = []
        for key, default, step in (("key_next", "ctrl+shift+right", 1), ("key_prev", "ctrl+shift+left", -1)):
            try:
                self.hotkeys.append(keyboard.add_hotkey(cfg.get(key, default), self.go, args=(step,)))
            except ValueError as e:
                log.warning("invalid hotkey %s: %s", key, e)
        if self.icon:
            self.icon.menu = tray_menu(self)

    def refresh_view(self, current=None):
        """Recompute the shown pages (sessions come and go) while staying on the page being shown."""
        if current is None and self.idx < len(self.view):
            current = self.view[self.idx].name
        view = layout.expand_pages(self.pages, self.state, int(self.cfg.get("max_agent_pages", 4)))
        names = [p.name for p in view]
        if names == [p.name for p in self.view]:
            return
        self.view = view
        if current in names:
            self.idx = names.index(current)
        else:  # e.g. the session of this page ended: stay on the same layout
            base = (current or "").split("#")[0]
            self.idx = next((i for i, n in enumerate(names) if n.split("#")[0] == base), min(self.idx, len(view) - 1))
        if self.icon:
            self.icon.menu = tray_menu(self)

    # --- navigation (callable from other threads: keyboard, tray) -------
    def call(self, fn):
        def run():
            fn()
            self.wake.set()
        self.loop.call_soon_threadsafe(run)

    def go(self, step: int):
        def _go():
            self.idx = (self.idx + step) % len(self.view)
            self.last_switch = time.monotonic()
        self.call(_go)

    def go_to(self, name: str):
        def _go():
            for i, p in enumerate(self.view):
                if p.name == name:
                    self.idx, self.last_switch = i, time.monotonic()
        self.call(_go)

    def set_brightness(self, pct: int):
        cfg = dict(self.cfg, brightness=pct)
        save_config(cfg)  # persisted, and picked up by check_reload like any other change

    def quit(self):
        def _quit():
            self.running = False
        self.call(_quit)

    def auto_switch(self):
        media = self.state.get("media")
        playing = bool(media and media["playing"])
        if self.cfg.get("media_focus", True) and playing and not self.was_playing:
            for i, p in enumerate(self.view):
                if p.name == "media":
                    self.idx, self.last_switch = i, time.monotonic()
        self.was_playing = playing
        rotate = self.cfg.get("rotate_seconds", 0)
        if rotate and time.monotonic() - self.last_switch >= rotate:
            self.idx = (self.idx + 1) % len(self.view)
            self.last_switch = time.monotonic()

    def read_control(self):
        """One-shot commands written by the settings window."""
        if not paths.CONTROL.exists():
            return
        try:
            cmd = json.loads(paths.CONTROL.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cmd = {}
        paths.CONTROL.unlink(missing_ok=True)
        page = cmd.get("show")
        if page in self.all_pages:
            if page not in [p.name for p in self.pages]:
                self.pages.append(self.all_pages[page])  # shown until the next config change
                self.refresh_view()
            self.idx = next(i for i, p in enumerate(self.view) if p.name.split("#")[0] == page)
            self.last_switch = time.monotonic()

    # --- main loop ------------------------------------------------------
    async def poll(self, name: str):
        src = self.all_sources[name]
        while True:
            scfg = self.section(name)
            try:
                self.state[name] = await src.fetch(scfg)
            except Exception as e:  # network down, app closed, ...: keep the last good data
                log.warning("source %s: %r", name, e)
            await asyncio.sleep(scfg.get("interval", src.interval))

    async def tick(self):
        if not self.screen.ser:
            await asyncio.to_thread(self.screen.open)
            log.info("screen connected on %s", self.screen.ser.port)
            self.prev, self.screen_off, self.missing_since, self.alerted = None, False, None, False
        if self.cfg.get("off_when_locked", True) and is_locked():
            if not self.screen_off:
                self.screen.power(False)
                self.screen_off = True
            return
        if self.screen_off:
            self.screen.power(True)
            self.screen_off, self.prev = False, None
        self.refresh_view()
        self.auto_switch()
        page = self.view[self.idx]
        try:
            if isinstance(page, (layout.LayoutPage, layout.AgentPage)):
                img = page.render(self.state, self.screen.size, {}, self.history_view)
            else:
                img = page.render(layout.with_clock(self.state, self.history_view), self.screen.size, self.section(page.name))
        except Exception:
            log.exception("error in page %s", page.name)
            return
        # send only the changed rectangle: a full frame costs ~2 s, a clock ~40 ms
        box = (0, 0, *img.size) if self.prev is None else ImageChops.difference(img, self.prev).getbbox()
        if box:
            await asyncio.to_thread(self.screen.show, img.crop(box), box[0], box[1])
        self.prev = img

    def screen_missing(self):
        self.missing_since = self.missing_since or time.monotonic()
        if not self.alerted and time.monotonic() - self.missing_since > USB_ALERT_AFTER and self.icon:
            self.alerted = True
            try:
                self.icon.notify(i18n._("Screen not found: check the USB cable."), paths.APP_NAME)
            except Exception:
                pass

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.check_reload()
        last_history = 0.0
        while self.running:
            if paths.STOPFLAG.exists():
                paths.STOPFLAG.unlink(missing_ok=True)
                break
            self.check_reload()
            self.read_control()
            if time.monotonic() - last_history >= 1:
                self.history_view = self.history.record(self.pages, self.state)
                last_history = time.monotonic()
            try:
                await self.tick()
            except (serial.SerialException, OSError) as e:
                log.warning("screen not available (%s), retrying in 3 s", e)
                self.screen.close()
                self.screen_missing()
                await asyncio.sleep(3)
                continue
            page = self.view[self.idx]
            animated = hasattr(page, "animated") and page.animated(self.screen.size) and not self.screen_off
            fps = max(1, min(15, int(self.cfg.get("animation_fps", 8))))
            timeout = 1 / fps if animated else 1 - time.time() % 1  # one tick per second, aligned for clocks
            self.wake.clear()
            try:
                await asyncio.wait_for(self.wake.wait(), timeout)
            except TimeoutError:
                pass
        try:
            if self.screen.ser:
                self.screen.power(False)
        except (serial.SerialException, OSError):
            pass
        self.screen.close()


def tray_icon_image():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 2, 56, 62), 8, fill=(110, 170, 255))
    d.rectangle((14, 8, 50, 50), fill=(12, 14, 20))
    d.rectangle((20, 30, 26, 44), fill=(80, 210, 130))
    d.rectangle((30, 22, 36, 44), fill=(250, 190, 70))
    d.rectangle((40, 14, 46, 44), fill=(110, 170, 255))
    return img


def tray_menu(app: App):
    import pystray
    _ = i18n._
    def page_item(p):  # pystray counts the action's arguments, so no default-argument lambdas
        text = p.label(app.state) if isinstance(p, layout.AgentPage) else getattr(p, "title", p.name)
        return pystray.MenuItem(text, lambda icon, item: app.go_to(p.name),
                                checked=lambda item: app.idx < len(app.view) and app.view[app.idx].name == p.name, radio=True)

    def bright_item(v):
        return pystray.MenuItem(f"{v}%", lambda icon, item: app.set_brightness(v),
                                checked=lambda item: app.cfg.get("brightness") == v, radio=True)
    page_items = [page_item(p) for p in app.view] or [pystray.MenuItem("-", None, enabled=False)]
    bright_items = [bright_item(v) for v in (10, 25, 40, 60, 80, 100)]
    return pystray.Menu(
        pystray.MenuItem(_("Settings"), lambda: service.open_settings(), default=True),
        pystray.MenuItem(_("Page"), pystray.Menu(*page_items)),
        pystray.MenuItem(_("Next page"), lambda: app.go(1)),
        pystray.MenuItem(_("Brightness"), pystray.Menu(*bright_items)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(_("Quit"), lambda: app.quit()),
    )


def main():
    paths.ensure_data()
    handlers = [RotatingFileHandler(paths.LOG, maxBytes=1_000_000, backupCount=1, encoding="utf-8")]
    if sys.stderr:  # pythonw / the frozen exe have no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)
    other = service.running_pid()
    if other and other != os.getpid():
        log.info("already running (pid %s)", other)
        return
    paths.PIDFILE.write_text(str(os.getpid()))
    app = App()

    async def run():
        import pystray
        app.loop = asyncio.get_running_loop()
        i18n.set_language(load_config().get("language", "it"))
        app.icon = pystray.Icon("turing-screen-studio", tray_icon_image(), paths.APP_NAME, tray_menu(app))
        app.icon.run_detached()
        await app.run()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    finally:
        if app.icon:
            app.icon.stop()
        paths.PIDFILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
