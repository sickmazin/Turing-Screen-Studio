"""Settings window. Every change is saved immediately and the screen app applies it live.

Run: pythonw settings.py  (or from the tray: Settings; frozen: TuringScreenStudio.exe --settings)
"""
import asyncio
import json
import os
import shutil
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

import requests
from PIL import ImageTk
from serial.tools.list_ports import comports

import i18n
import layout
import paths
import service
import sources
import ui
from editor import PageEditor
from i18n import _
from main import load, load_config, load_pages, save_config
from screen import Screen

ORIENTATIONS = ["portrait", "reverse_portrait", "landscape", "reverse_landscape"]
ORIENT_LABELS = {"portrait": "Portrait", "reverse_portrait": "Portrait (upside down)",
                 "landscape": "Landscape", "reverse_landscape": "Landscape (upside down)"}
COLOR_LABELS = {"bg": "Background", "card": "Cards", "fg": "Text", "muted": "Secondary text",
                "accent": "Accent", "good": "Positive / OK", "warn": "Warning", "bad": "Negative / critical"}
SOURCE_LABELS = {"weather": "Weather", "stocks": "Markets", "claude": "Claude Code", "system": "System",
                 "media": "Media", "agents": "Agents", "calendar": "Calendar", "notifications": "Notifications",
                 "hardware": "Hardware"}
FONTS_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
IMAGE_TYPES = [("Images", "*.png *.jpg *.jpeg *.bmp *.webp")]
FONT_TYPES = [("Fonts", "*.ttf *.otf *.ttc")]


class Settings(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        i18n.set_language(self.cfg.get("language", "it"))
        self._written = json.dumps(self.cfg, sort_keys=True)
        self.all_pages = load_pages()
        self.all_sources = load(sources)
        self.data = {}  # real data for the previews and the editor
        self.history = layout.HistoryRecorder()
        self.history_view = {}
        self._jobs = {}
        ui.load_theme(self.cfg.get("theme", "dark"))
        from main import tray_icon_image
        self._icon = ImageTk.PhotoImage(tray_icon_image())
        self.iconphoto(True, self._icon)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build_ui()
        threading.Thread(target=self.fetch_data, daemon=True).start()

    def build_ui(self):
        self.title(f"{paths.APP_NAME}: {_('settings')}")
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)
        for title, build in (("General", self.build_general), ("Pages", self.build_pages), ("Data", self.build_data),
                             ("Theme", self.build_theme), ("Service", self.build_service)):
            frame = ttk.Frame(self.nb, padding=12)
            self.nb.add(frame, text=_(title))
            build(frame)

    def rebuild_ui(self):
        """After a language change: save pending work and draw the window again."""
        for key in list(self._jobs):
            self.run_now(key)
        self.nb.destroy()
        self.build_ui()

    # --- saving ---------------------------------------------------------
    def later(self, key, fn, ms=300):
        """Group quick changes (e.g. dragging a slider) into one save."""
        if key in self._jobs:
            self.after_cancel(self._jobs[key][0])
        self._jobs[key] = (self.after(ms, lambda: (self._jobs.pop(key, None), fn())), fn)

    def run_now(self, key):
        job = self._jobs.pop(key, None)
        if job:
            self.after_cancel(job[0])
            job[1]()

    def on_close(self):
        for key in list(self._jobs):  # nothing lost when closing the window
            self.run_now(key)
        self.destroy()

    def save(self):
        self.later("config", self._write_config)

    def _write_config(self):
        text = json.dumps(self.cfg, sort_keys=True)
        if text != self._written:
            save_config(self.cfg)
            self._written = text

    def section(self, name):
        return {**getattr(self.all_sources.get(name), "settings", {}), **self.cfg.get(name, {})}

    def set(self, key, value):
        self.cfg[key] = value
        self.save()

    # --- General --------------------------------------------------------
    def build_general(self, f):
        f.columnconfigure(1, weight=1)
        row = 0

        def label(text):
            nonlocal row
            ttk.Label(f, text=_(text)).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 16))
            row += 1
            return row - 1

        r = label("Language")
        lang = ttk.Combobox(f, values=list(i18n.LANGUAGES.values()), state="readonly", width=14)
        lang.set(i18n.LANGUAGES[i18n.language()])
        lang.grid(row=r, column=1, sticky="w")

        def change_language(e):
            code = list(i18n.LANGUAGES)[lang.current()]
            if code != i18n.language():
                i18n.set_language(code)
                self.set("language", code)
                self.after(10, self.rebuild_ui)
        lang.bind("<<ComboboxSelected>>", change_language)

        r = label("Port")
        port = ttk.Combobox(f, values=["AUTO"] + [p.device for p in comports()], width=12,
                            postcommand=lambda: port.configure(values=["AUTO"] + [p.device for p in comports()]))
        port.set(self.cfg.get("port", "AUTO"))
        port.grid(row=r, column=1, sticky="w")
        port.bind("<<ComboboxSelected>>", lambda e: self.set("port", port.get()))
        port.bind("<FocusOut>", lambda e: self.set("port", port.get().strip() or "AUTO"))

        r = label("Orientation")
        orient = ttk.Combobox(f, values=[_(ORIENT_LABELS[o]) for o in ORIENTATIONS], state="readonly", width=26)
        current = self.cfg.get("orientation", "portrait")
        orient.current(ORIENTATIONS.index(current) if current in ORIENTATIONS else 0)
        orient.grid(row=r, column=1, sticky="w")
        orient.bind("<<ComboboxSelected>>", lambda e: (self.set("orientation", ORIENTATIONS[orient.current()]),
                                                       self.render_preview()))

        r = label("Brightness")
        bright = tk.IntVar(value=self.cfg.get("brightness", 40))
        box = ttk.Frame(f)
        box.grid(row=r, column=1, sticky="we")
        ttk.Scale(box, from_=0, to=100, variable=bright, length=300,
                  command=lambda v: bright.set(round(float(v)))).pack(side="left")
        ttk.Label(box, textvariable=bright, width=4).pack(side="left", padx=8)
        bright.trace_add("write", lambda *a: self.set("brightness", bright.get()))

        for key, text, default, lo, hi in (("rotate_seconds", "Automatic page change (s, 0 = never)", 0, 0, 3600),
                                           ("animation_fps", "Animation frames per second", 8, 1, 15)):
            r = label(text)
            var = tk.StringVar(value=str(self.cfg.get(key, default)))
            ttk.Spinbox(f, from_=lo, to=hi, increment=1, textvariable=var, width=8).grid(row=r, column=1, sticky="w")
            var.trace_add("write", lambda *a, k=key, v=var, lo=lo, hi=hi: v.get().isdigit()
                          and self.set(k, max(lo, min(hi, int(v.get())))))

        for key, text in (("media_focus", "Switch to the media page when a song starts"),
                          ("off_when_locked", "Turn the screen off when the PC is locked")):
            var = tk.BooleanVar(value=self.cfg.get(key, True))
            ttk.Checkbutton(f, text=_(text), variable=var).grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
            var.trace_add("write", lambda *a, k=key, v=var: self.set(k, v.get()))
            row += 1

        for key, text, default in (("key_next", "Next page shortcut", "ctrl+shift+right"),
                                   ("key_prev", "Previous page shortcut", "ctrl+shift+left")):
            r = label(text)
            e = ttk.Entry(f, width=24)
            e.insert(0, self.cfg.get(key, default))
            e.grid(row=r, column=1, sticky="w")
            e.bind("<FocusOut>", lambda ev, k=key, w=e: self.set(k, w.get().strip()))
            e.bind("<Return>", lambda ev, k=key, w=e: self.set(k, w.get().strip()))

    # --- Pages (editor) -------------------------------------------------
    def build_pages(self, f):
        self.editor = PageEditor(f, self)
        self.editor.pack(fill="both", expand=True)

    # --- Data -----------------------------------------------------------
    def build_data(self, f):
        canvas = tk.Canvas(f, highlightthickness=0)
        scroll = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set, width=760, height=560)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-e.delta // 120, "units"))
        ttk.Label(inner, foreground="gray", text=_("Settings of the data sources used by the widgets.")).pack(anchor="w", pady=(0, 8))
        admin = service.is_admin()
        ttk.Label(inner, foreground="green" if admin else "#b06000", text=_(
            "Hardware sensors: complete (running as administrator)." if admin else
            "Hardware sensors: CPU temperatures need the app to run as administrator.")).pack(anchor="w", pady=(0, 8))
        for name in sorted(self.all_sources, key=lambda n: _(SOURCE_LABELS.get(n, n))):
            if self.section(name):
                box = ttk.LabelFrame(inner, text=_(SOURCE_LABELS.get(name, name)), padding=8)
                box.pack(fill="x", pady=(0, 10))
                self.fill_form(box, name)

    def fill_form(self, box, name):
        for w in box.winfo_children():
            w.destroy()
        values = self.section(name)
        for r, (key, value) in enumerate(values.items()):
            ttk.Label(box, text=_(key)).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 12))
            if isinstance(value, bool):
                var = tk.BooleanVar(value=value)
                ttk.Checkbutton(box, variable=var).grid(row=r, column=1, sticky="w")
                var.trace_add("write", lambda *a, k=key, v=var: self.set_source(name, k, v.get()))
                continue
            e = ttk.Entry(box, width=70)
            e.insert(0, ", ".join(map(str, value)) if isinstance(value, list) else str(value))
            e.grid(row=r, column=1, sticky="we")
            commit = lambda ev, k=key, w=e, t=type(value): self.commit_field(name, k, w, t)
            e.bind("<FocusOut>", commit)
            e.bind("<Return>", commit)
        if name == "weather":
            r = len(values)
            city = ttk.Entry(box, width=24)
            city.grid(row=r, column=0, sticky="w", pady=(8, 0))
            ttk.Button(box, text=_("Find city and set coordinates"),
                       command=lambda: self.geocode(city.get(), box)).grid(row=r, column=1, sticky="w", pady=(8, 0))
        if name == "calendar":
            ttk.Label(box, foreground="gray", wraplength=640, justify="left", text=_(
                "Paste the secret iCal address of your calendars, separated by commas. Google Calendar: "
                "Settings > calendar > Integrate calendar > Secret address in iCal format. Outlook: "
                "Settings > Calendar > Shared calendars > Publish a calendar > ICS.")).grid(
                row=len(values), column=0, columnspan=2, sticky="w", pady=(6, 0))

    def commit_field(self, name, key, entry, typ):
        text = entry.get().strip()
        try:
            value = [s.strip() for s in text.split(",") if s.strip()] if typ is list else typ(text)
        except ValueError:
            entry.configure(foreground="red")
            return
        entry.configure(foreground="")
        self.set_source(name, key, value)

    def set_source(self, name, key, value):
        if self.section(name).get(key) != value:
            self.cfg.setdefault(name, {})[key] = value
            self.save()

    def geocode(self, query, box):
        if not query.strip():
            return

        def work():
            try:
                r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                                 params={"name": query, "count": 1, "language": i18n.language()}, timeout=10)
                hit = (r.json().get("results") or [None])[0]
            except (requests.RequestException, ValueError):
                hit = None
            self.after(0, lambda: done(hit))

        def done(hit):
            if not hit:
                messagebox.showwarning(_("Weather"), _("City not found: ") + query)
                return
            self.cfg.setdefault("weather", {}).update(city=hit["name"], lat=round(hit["latitude"], 4),
                                                      lon=round(hit["longitude"], 4))
            self.save()
            self.fill_form(box, "weather")
        threading.Thread(target=work, daemon=True).start()

    # --- Theme ----------------------------------------------------------
    def build_theme(self, f):
        f.columnconfigure(0, weight=1)
        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="nsew")
        right = ttk.LabelFrame(f, text=_("Preview"), padding=8)
        right.grid(row=0, column=1, sticky="ns", padx=(16, 0))

        top = ttk.Frame(left)
        top.pack(fill="x")
        ttk.Label(top, text=_("Theme")).pack(side="left")
        self.theme_box = ttk.Combobox(top, state="readonly", width=22)
        self.theme_box.pack(side="left", padx=8)
        self.theme_box.bind("<<ComboboxSelected>>", lambda e: self.select_theme(self.theme_ids[self.theme_box.current()]))
        for text, cmd in (("Duplicate", self.new_theme), ("Rename", self.rename_theme), ("Delete", self.delete_theme),
                          ("Import…", self.import_theme), ("Export…", self.export_theme)):
            ttk.Button(top, text=_(text), command=cmd).pack(side="left", padx=2)

        colors = ttk.LabelFrame(left, text=_("Colours"), padding=8)
        colors.pack(fill="x", pady=10)
        self.swatches = {}
        for i, k in enumerate(ui.COLOR_KEYS):
            cell = ttk.Frame(colors)
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=3)
            sw = tk.Button(cell, width=4, relief="groove", command=lambda k=k: self.pick_color(k))
            sw.pack(side="left")
            ttk.Label(cell, text=_(COLOR_LABELS[k]), width=20).pack(side="left", padx=6)
            self.swatches[k] = sw

        fonts = ttk.LabelFrame(left, text=_("Font"), padding=8)
        fonts.pack(fill="x")
        self.font_boxes = {}
        for r, (k, text) in enumerate((("regular", "Regular"), ("bold", "Bold"))):
            ttk.Label(fonts, text=_(text)).grid(row=r, column=0, sticky="w")
            cb = ttk.Combobox(fonts, width=30)
            cb.grid(row=r, column=1, padx=6, pady=3)
            cb.bind("<<ComboboxSelected>>", lambda e, k=k, c=cb: self.set_theme_font(k, c.get()))
            ttk.Button(fonts, text=_("From file…"), command=lambda k=k: self.font_from_file(k)).grid(row=r, column=2)
            self.font_boxes[k] = cb
        ttk.Label(fonts, text=_("Text scale")).grid(row=2, column=0, sticky="w")
        self.scale_var = tk.StringVar()
        ttk.Spinbox(fonts, from_=0.6, to=1.6, increment=0.05, textvariable=self.scale_var, width=6).grid(
            row=2, column=1, sticky="w", padx=6)
        self.scale_var.trace_add("write", lambda *a: self.set_scale())

        bgs = ttk.LabelFrame(left, text=_("Page backgrounds"), padding=8)
        bgs.pack(fill="x", pady=10)
        self.bg_page = ttk.Combobox(bgs, values=sorted(self.all_pages), state="readonly", width=14)
        self.bg_page.grid(row=0, column=0)
        self.bg_page.bind("<<ComboboxSelected>>", lambda e: (self.preview_page.set(self.bg_page.get()),
                                                             self.refresh_bg_label(), self.render_preview()))
        ttk.Button(bgs, text=_("Choose image…"), command=self.pick_background).grid(row=0, column=1, padx=6)
        ttk.Button(bgs, text=_("Remove"), command=self.remove_background).grid(row=0, column=2)
        self.bg_label = ttk.Label(bgs, text="", foreground="gray")
        self.bg_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(bgs, text=_("Darken")).grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.dim_var = tk.DoubleVar()
        ttk.Scale(bgs, from_=0, to=1, variable=self.dim_var, length=200,
                  command=lambda v: self.set_theme("background_dim", round(float(v), 2))).grid(
            row=2, column=1, columnspan=2, sticky="w", pady=(6, 0))

        self.preview_page = ttk.Combobox(right, values=sorted(self.all_pages), state="readonly", width=14)
        self.preview_page.pack()
        self.preview_page.set((self.cfg.get("pages") or sorted(self.all_pages))[0])
        self.preview_page.bind("<<ComboboxSelected>>", lambda e: self.render_preview())
        self.preview_label = ttk.Label(right)
        self.preview_label.pack(pady=8)

        self.load_theme_list(self.cfg.get("theme", "dark"))
        self.tick_preview()

    def load_theme_list(self, select):
        themes = ui.list_themes()
        if not themes:
            ui.save_theme("dark", ui.DEFAULT_THEME)
            themes = ui.list_themes()
        self.theme_ids = list(themes)
        self.theme_box["values"] = [_(themes[i]) for i in self.theme_ids]
        self.select_theme(select if select in themes else self.theme_ids[0])

    def select_theme(self, theme_id):
        self.theme_id = theme_id
        self.theme = ui.read_theme(theme_id)
        self.theme_box.current(self.theme_ids.index(theme_id))
        self.set("theme", theme_id)
        for k, sw in self.swatches.items():
            sw.configure(bg=self.theme["colors"][k], activebackground=self.theme["colors"][k])
        folder = paths.THEMES / theme_id
        exts = (".ttf", ".otf", ".ttc")
        own = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in exts)
        system = sorted(p.name for p in FONTS_DIR.glob("*") if p.suffix.lower() in exts)
        for k, cb in self.font_boxes.items():
            cb["values"] = own + system
            cb.set(self.theme["font"][k])
        self.scale_var.set(str(self.theme["font"].get("scale", 1.0)))
        self.dim_var.set(self.theme.get("background_dim", 0.55))
        self.refresh_bg_label()
        self.render_preview()

    def save_theme(self):
        self.later("theme", lambda: ui.save_theme(self.theme_id, self.theme))
        self.render_preview()

    def set_theme(self, key, value):
        self.theme[key] = value
        self.save_theme()

    def pick_color(self, k):
        _rgb, hexcolor = colorchooser.askcolor(self.theme["colors"][k], parent=self, title=_(COLOR_LABELS[k]))
        if hexcolor:
            self.theme["colors"][k] = hexcolor
            self.swatches[k].configure(bg=hexcolor, activebackground=hexcolor)
            self.save_theme()

    def set_theme_font(self, k, name):
        self.theme["font"][k] = name
        self.save_theme()

    def font_from_file(self, k):
        path = filedialog.askopenfilename(parent=self, filetypes=FONT_TYPES)
        if path:
            shutil.copy(path, paths.THEMES / self.theme_id / Path(path).name)  # inside the theme: travels with exports
            self.select_theme(self.theme_id)
            self.font_boxes[k].set(Path(path).name)
            self.set_theme_font(k, Path(path).name)

    def set_scale(self):
        try:
            v = float(self.scale_var.get().replace(",", "."))
        except ValueError:
            return
        if 0.5 <= v <= 2 and round(v, 2) != self.theme["font"].get("scale"):  # filling the field is not a change
            self.theme["font"]["scale"] = round(v, 2)
            self.save_theme()

    def refresh_bg_label(self):
        page = self.bg_page.get()
        name = self.theme["backgrounds"].get(page) if page else None
        self.bg_label.configure(text=f"{page}: {name}" if name else (f"{page}: {_('no background')}" if page else
                                                                     _("Choose a page")))

    def pick_background(self):
        page = self.bg_page.get()
        if not page:
            messagebox.showinfo(_("Backgrounds"), _("Choose the page first."))
            return
        path = filedialog.askopenfilename(parent=self, filetypes=IMAGE_TYPES)
        if not path:
            return
        name = f"bg_{page}{Path(path).suffix.lower()}"
        shutil.copy(path, paths.THEMES / self.theme_id / name)
        self.theme["backgrounds"][page] = name
        self.save_theme()
        self.refresh_bg_label()

    def remove_background(self):
        name = self.theme["backgrounds"].pop(self.bg_page.get(), None)
        if name:
            (paths.THEMES / self.theme_id / name).unlink(missing_ok=True)
            self.save_theme()
            self.refresh_bg_label()

    def new_theme(self):
        name = simpledialog.askstring(_("New theme"), _("Name of the new theme:"), parent=self)
        if not name:
            return
        ui.save_theme(self.theme_id, self.theme)
        folder = ui.unique_dir(paths.THEMES, name)
        shutil.copytree(paths.THEMES / self.theme_id, folder)
        ui.save_theme(folder.name, {**self.theme, "name": name})
        self.load_theme_list(folder.name)

    def rename_theme(self):
        name = simpledialog.askstring(_("Rename"), _("New name:"), initialvalue=_(self.theme["name"]), parent=self)
        if name:
            self.theme["name"] = name
            ui.save_theme(self.theme_id, self.theme)
            self.load_theme_list(self.theme_id)

    def delete_theme(self):
        if len(self.theme_ids) == 1:
            messagebox.showinfo(_("Theme"), _("It is the only theme left."))
            return
        if not messagebox.askyesno(_("Delete theme"), _("Delete the theme and its files?") + f"\n{_(self.theme['name'])}"):
            return
        shutil.rmtree(paths.THEMES / self.theme_id)
        self.load_theme_list(next(i for i in self.theme_ids if i != self.theme_id))

    def export_theme(self):
        ui.save_theme(self.theme_id, self.theme)
        path = filedialog.asksaveasfilename(parent=self, defaultextension=ui.THEME_EXT,
                                            initialfile=_(self.theme["name"]) + ui.THEME_EXT,
                                            filetypes=[(_("Screen theme"), "*" + ui.THEME_EXT)])
        if path:
            ui.export_theme(self.theme_id, Path(path))

    def import_theme(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[(_("Screen theme"), "*" + ui.THEME_EXT)])
        if not path:
            return
        try:
            self.load_theme_list(ui.import_theme(Path(path)))
        except Exception as e:
            messagebox.showerror(_("Import theme"), _("Invalid file: ") + str(e))

    # --- preview data ---------------------------------------------------
    def fetch_data(self):
        """Thread: refresh real data for previews and editor every few seconds."""
        last = {}

        async def run():
            while True:
                for n, src in self.all_sources.items():
                    every = max(3, self.section(n).get("interval", src.interval))
                    if time.monotonic() - last.get(n, -1e9) < every:
                        continue  # each source keeps its own pace (calendars every 15 min, not every 3 s)
                    last[n] = time.monotonic()
                    try:
                        self.data[n] = await src.fetch(self.section(n))
                    except Exception:
                        pass
                try:
                    self.after(0, self.on_data)
                except RuntimeError:  # window closed
                    return
                await asyncio.sleep(3)
        asyncio.run(run())

    def on_data(self):
        self.history_view = self.history.record(self.all_pages.values(), self.data)
        self.render_preview()
        if self.editor.drag is None:
            self.editor.redraw()

    def render_preview(self):
        if not hasattr(self, "preview_label") or not self.preview_label.winfo_exists():
            return
        page = self.all_pages.get(self.preview_page.get())
        if not page:
            return
        ui.apply_theme(self.theme, paths.THEMES / self.theme_id)
        size = Screen(orientation=self.cfg.get("orientation", "portrait")).size
        try:
            if isinstance(page, layout.LayoutPage):
                img = page.render(self.data, size, {}, self.history_view)
            else:
                img = page.render(layout.with_clock(self.data), size, self.section(page.name))
        except Exception as e:
            self.preview_label.configure(image="", text=f"{_('Error')}: {e}")
            return
        self._photo = ImageTk.PhotoImage(img)
        self.preview_label.configure(image=self._photo, text="")

    def tick_preview(self):
        if self.preview_label.winfo_exists():
            self.render_preview()
            self.after(2000, self.tick_preview)

    # --- Service --------------------------------------------------------
    def build_service(self, f):
        self.status = ttk.Label(f, font=("Segoe UI", 12, "bold"))
        self.status.pack(anchor="w", pady=(0, 12))
        btns = ttk.Frame(f)
        btns.pack(anchor="w")
        for text, cmd in (("Start", service.start), ("Stop", service.stop), ("Restart", service.restart)):
            ttk.Button(btns, text=_(text), command=lambda c=cmd: self.run_service(c)).pack(side="left", padx=(0, 6))
        self.autostart = tk.BooleanVar(value=service.get_autostart())
        ttk.Checkbutton(f, text=_("Start the screen when I sign in to Windows"), variable=self.autostart,
                        command=self.toggle_autostart).pack(anchor="w", pady=12)
        row = ttk.Frame(f)
        row.pack(anchor="w")
        ttk.Button(row, text=_("Open log"), command=lambda: paths.LOG.exists() and os.startfile(paths.LOG)).pack(side="left")
        ttk.Button(row, text=_("Open data folder"), command=lambda: os.startfile(paths.DATA)).pack(side="left", padx=6)
        ttk.Label(f, foreground="gray", wraplength=640, justify="left", text=_(
            "Changes apply immediately, without restarting. This app and UsbMonitor.exe cannot run together: "
            "close UsbMonitor and remove it from startup.")).pack(anchor="w", pady=16)
        self.poll_status()

    def toggle_autostart(self):
        err = service.set_autostart(self.autostart.get())
        if err:
            self.autostart.set(service.get_autostart())
            messagebox.showerror(_("Startup"), err)
        elif self.autostart.get() and not service.is_admin():
            messagebox.showinfo(_("Startup"), _("Enabled without administrator rights: CPU temperatures will not be "
                                                "available. Open the settings as administrator and enable it again."))

    def run_service(self, cmd):
        self.status.configure(text="…")
        threading.Thread(target=lambda: (cmd(), self.after(0, self.refresh_status)), daemon=True).start()

    def refresh_status(self):
        if not self.status.winfo_exists():
            return
        pid = service.running_pid()
        self.status.configure(text=f"● {_('Running')} (pid {pid})" if pid else f"○ {_('Stopped')}",
                              foreground="green" if pid else "gray")

    def poll_status(self):
        if self.status.winfo_exists():
            self.refresh_status()
            self.after(2000, self.poll_status)


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text with Windows display scaling
    except (AttributeError, OSError):
        pass
    paths.ensure_data()
    Settings().mainloop()


if __name__ == "__main__":
    main()
