"""Impostazioni dello schermetto. Ogni modifica viene salvata subito e l'app dello schermo la applica dal vivo.

Avvio: .venv\\Scripts\\pythonw settings.py  (oppure dalla tray: Impostazioni)
"""
import asyncio
import json
import os
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

import requests
from PIL import ImageTk
from serial.tools.list_ports import comports

import service
import sources
import ui
from editor import PageEditor
from main import CONFIG, load, load_config, load_pages
from screen import Screen

ORIENT = {"portrait": "Verticale", "reverse_portrait": "Verticale capovolto",
          "landscape": "Orizzontale", "reverse_landscape": "Orizzontale capovolto"}
COLOR_LABELS = {"bg": "Sfondo", "card": "Riquadri", "fg": "Testo", "muted": "Testo secondario",
                "accent": "Accento", "good": "Positivo / OK", "warn": "Attenzione", "bad": "Negativo / critico"}
SOURCE_LABELS = {"weather": "Meteo", "stocks": "Borsa", "claude": "Claude Code", "system": "Sistema", "media": "Media"}
FONTS_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
IMAGE_TYPES = [("Immagini", "*.png *.jpg *.jpeg *.bmp *.webp")]
FONT_TYPES = [("Font", "*.ttf *.otf *.ttc")]


def safe_id(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_ ").strip() or "tema"


class Settings(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Schermetto: impostazioni")
        self.cfg = load_config()
        self._written = json.dumps(self.cfg, sort_keys=True)
        self.all_pages = load_pages()
        self.all_sources = load(sources)
        self.data = {}  # dati veri per anteprima ed editor
        ui.load_theme(self.cfg.get("theme", "scuro"))
        self._jobs = {}

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        for title, build in (("Generale", self.build_general), ("Pagine", self.build_pages), ("Dati", self.build_data),
                             ("Tema", self.build_theme), ("Servizio", self.build_service)):
            frame = ttk.Frame(nb, padding=12)
            nb.add(frame, text=title)
            build(frame)
        threading.Thread(target=self.fetch_data, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- salvataggio ----------------------------------------------------
    def later(self, key, fn, ms=300):
        """Raggruppa modifiche ravvicinate (es. trascinare uno slider) in un solo salvataggio."""
        if key in self._jobs:
            self.after_cancel(self._jobs[key][0])
        self._jobs[key] = (self.after(ms, lambda: (self._jobs.pop(key, None), fn())), fn)

    def run_now(self, key):
        """Esegue subito un salvataggio in attesa."""
        job = self._jobs.pop(key, None)
        if job:
            self.after_cancel(job[0])
            job[1]()

    def on_close(self):
        for key in list(self._jobs):  # niente modifiche perse chiudendo la finestra
            self.run_now(key)
        self.destroy()

    def save(self):
        self.later("config", self._write_config)

    def _write_config(self):
        text = json.dumps(self.cfg, sort_keys=True)
        if text == self._written:
            return
        tmp = CONFIG.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CONFIG)  # atomico: lo schermo non legge mai un file a metà
        self._written = text

    def section(self, name):
        return {**getattr(self.all_sources.get(name), "settings", {}), **self.cfg.get(name, {})}

    # --- Pagine (editor) ------------------------------------------------
    def build_pages(self, f):
        self.editor = PageEditor(f, self)
        self.editor.pack(fill="both", expand=True)

    # --- Generale -------------------------------------------------------
    def build_general(self, f):
        f.columnconfigure(1, weight=1)
        row = 0

        def label(text):
            nonlocal row
            ttk.Label(f, text=text).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 16))
            row += 1
            return row - 1

        r = label("Porta")
        ports = ["AUTO"] + [p.device for p in comports()]
        port = ttk.Combobox(f, values=ports, width=12)
        port.set(self.cfg.get("port", "AUTO"))
        port.grid(row=r, column=1, sticky="w")
        port.bind("<<ComboboxSelected>>", lambda e: self.set("port", port.get()))
        port.bind("<FocusOut>", lambda e: self.set("port", port.get().strip() or "AUTO"))

        r = label("Orientamento")
        orient = ttk.Combobox(f, values=list(ORIENT.values()), state="readonly", width=22)
        orient.set(ORIENT.get(self.cfg.get("orientation", "portrait")))
        orient.grid(row=r, column=1, sticky="w")
        orient.bind("<<ComboboxSelected>>", lambda e: (
            self.set("orientation", {v: k for k, v in ORIENT.items()}[orient.get()]), self.render_preview()))

        r = label("Luminosità")
        bright = tk.IntVar(value=self.cfg.get("brightness", 40))
        box = ttk.Frame(f)
        box.grid(row=r, column=1, sticky="we")
        ttk.Scale(box, from_=0, to=100, variable=bright, length=300,
                  command=lambda v: bright.set(round(float(v)))).pack(side="left")
        ttk.Label(box, textvariable=bright, width=4).pack(side="left", padx=8)
        bright.trace_add("write", lambda *_: self.set("brightness", bright.get()))

        r = label("Cambio pagina automatico (s, 0 = mai)")
        rot = tk.StringVar(value=str(self.cfg.get("rotate_seconds", 0)))
        ttk.Spinbox(f, from_=0, to=3600, increment=5, textvariable=rot, width=8).grid(row=r, column=1, sticky="w")
        rot.trace_add("write", lambda *_: rot.get().isdigit() and self.set("rotate_seconds", int(rot.get())))

        for key, text in (("media_focus", "Passa alla pagina media quando parte un brano"),
                          ("off_when_locked", "Spegni lo schermo quando il PC è bloccato")):
            var = tk.BooleanVar(value=self.cfg.get(key, True))
            ttk.Checkbutton(f, text=text, variable=var).grid(row=row, column=0, columnspan=2, sticky="w", pady=4)
            var.trace_add("write", lambda *_, k=key, v=var: self.set(k, v.get()))
            row += 1

        for key, text, default in (("key_next", "Scorciatoia pagina successiva", "ctrl+shift+right"),
                                   ("key_prev", "Scorciatoia pagina precedente", "ctrl+shift+left")):
            r = label(text)
            e = ttk.Entry(f, width=24)
            e.insert(0, self.cfg.get(key, default))
            e.grid(row=r, column=1, sticky="w")
            e.bind("<FocusOut>", lambda ev, k=key, w=e: self.set(k, w.get().strip()))
            e.bind("<Return>", lambda ev, k=key, w=e: self.set(k, w.get().strip()))

    def set(self, key, value):
        self.cfg[key] = value
        self.save()

    # --- Dati -----------------------------------------------------------
    def build_data(self, f):
        ttk.Label(f, foreground="gray", text="Impostazioni delle fonti di dati usate dai widget.").pack(anchor="w", pady=(0, 8))
        for name in sorted(self.all_sources):
            if self.section(name):
                box = ttk.LabelFrame(f, text=SOURCE_LABELS.get(name, name), padding=8)
                box.pack(fill="x", pady=(0, 10))
                self.fill_form(box, name)

    def fill_form(self, box, name):
        for w in box.winfo_children():
            w.destroy()
        values = self.section(name)
        for r, (key, value) in enumerate(values.items()):
            ttk.Label(box, text=key).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 12))
            if isinstance(value, bool):
                var = tk.BooleanVar(value=value)
                ttk.Checkbutton(box, variable=var).grid(row=r, column=1, sticky="w")
                var.trace_add("write", lambda *_, k=key, v=var: self.set_source(name, k, v.get()))
                continue
            e = ttk.Entry(box, width=50)
            e.insert(0, ", ".join(map(str, value)) if isinstance(value, list) else str(value))
            e.grid(row=r, column=1, sticky="we")
            commit = lambda ev, k=key, w=e, t=type(value): self.commit_field(name, k, w, t)
            e.bind("<FocusOut>", commit)
            e.bind("<Return>", commit)
        if name == "weather":
            r = len(values)
            city = ttk.Entry(box, width=24)
            city.grid(row=r, column=0, sticky="w", pady=(8, 0))
            ttk.Button(box, text="Cerca città e imposta coordinate",
                       command=lambda: self.geocode(city.get(), box)).grid(row=r, column=1, sticky="w", pady=(8, 0))

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
                                 params={"name": query, "count": 1, "language": "it"}, timeout=10)
                hit = (r.json().get("results") or [None])[0]
            except (requests.RequestException, ValueError):
                hit = None
            self.after(0, lambda: done(hit))

        def done(hit):
            if not hit:
                messagebox.showwarning("Meteo", f"Città non trovata: {query}")
                return
            self.cfg.setdefault("weather", {}).update(city=hit["name"], lat=round(hit["latitude"], 4),
                                                      lon=round(hit["longitude"], 4))
            self.save()
            self.fill_form(box, "weather")
        threading.Thread(target=work, daemon=True).start()

    # --- Tema -----------------------------------------------------------
    def build_theme(self, f):
        f.columnconfigure(0, weight=1)
        left = ttk.Frame(f)
        left.grid(row=0, column=0, sticky="nsew")
        right = ttk.LabelFrame(f, text="Anteprima", padding=8)
        right.grid(row=0, column=1, sticky="ns", padx=(16, 0))

        top = ttk.Frame(left)
        top.pack(fill="x")
        ttk.Label(top, text="Tema").pack(side="left")
        self.theme_box = ttk.Combobox(top, state="readonly", width=22)
        self.theme_box.pack(side="left", padx=8)
        self.theme_box.bind("<<ComboboxSelected>>", lambda e: self.select_theme(self.theme_ids[self.theme_box.current()]))
        for text, cmd in (("Duplica", self.new_theme), ("Rinomina", self.rename_theme), ("Elimina", self.delete_theme),
                          ("Importa…", self.import_theme), ("Esporta…", self.export_theme)):
            ttk.Button(top, text=text, command=cmd).pack(side="left", padx=2)

        colors = ttk.LabelFrame(left, text="Colori", padding=8)
        colors.pack(fill="x", pady=10)
        self.swatches = {}
        for i, k in enumerate(ui.COLOR_KEYS):
            cell = ttk.Frame(colors)
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=3)
            sw = tk.Button(cell, width=4, relief="groove", command=lambda k=k: self.pick_color(k))
            sw.pack(side="left")
            ttk.Label(cell, text=COLOR_LABELS[k], width=18).pack(side="left", padx=6)
            self.swatches[k] = sw

        fonts = ttk.LabelFrame(left, text="Font", padding=8)
        fonts.pack(fill="x")
        self.font_boxes = {}
        for r, (k, text) in enumerate((("regular", "Normale"), ("bold", "Grassetto"))):
            ttk.Label(fonts, text=text).grid(row=r, column=0, sticky="w")
            cb = ttk.Combobox(fonts, width=30)
            cb.grid(row=r, column=1, padx=6, pady=3)
            cb.bind("<<ComboboxSelected>>", lambda e, k=k, c=cb: self.set_theme_font(k, c.get()))
            ttk.Button(fonts, text="Da file…", command=lambda k=k: self.font_from_file(k)).grid(row=r, column=2)
            self.font_boxes[k] = cb
        ttk.Label(fonts, text="Scala testo").grid(row=2, column=0, sticky="w")
        self.scale_var = tk.StringVar()
        ttk.Spinbox(fonts, from_=0.6, to=1.6, increment=0.05, textvariable=self.scale_var, width=6).grid(
            row=2, column=1, sticky="w", padx=6)
        self.scale_var.trace_add("write", lambda *_: self.set_scale())

        bgs = ttk.LabelFrame(left, text="Sfondi per pagina", padding=8)
        bgs.pack(fill="x", pady=10)
        self.bg_page = ttk.Combobox(bgs, values=sorted(self.all_pages), state="readonly", width=14)
        self.bg_page.grid(row=0, column=0)
        self.bg_page.bind("<<ComboboxSelected>>", lambda e: (self.preview_page.set(self.bg_page.get()),
                                                             self.refresh_bg_label(), self.render_preview()))
        ttk.Button(bgs, text="Scegli immagine…", command=self.pick_background).grid(row=0, column=1, padx=6)
        ttk.Button(bgs, text="Rimuovi", command=self.remove_background).grid(row=0, column=2)
        self.bg_label = ttk.Label(bgs, text="", foreground="gray")
        self.bg_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(bgs, text="Oscuramento").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.dim_var = tk.DoubleVar()
        ttk.Scale(bgs, from_=0, to=1, variable=self.dim_var, length=200,
                  command=lambda v: self.set_theme("background_dim", round(float(v), 2))).grid(
            row=2, column=1, columnspan=2, sticky="w", pady=(6, 0))

        self.preview_page = ttk.Combobox(right, values=sorted(self.all_pages), state="readonly", width=14)
        self.preview_page.pack()
        self.preview_page.set(self.cfg.get("pages", ["clock"])[0])
        self.preview_page.bind("<<ComboboxSelected>>", lambda e: self.render_preview())
        self.preview_label = ttk.Label(right)
        self.preview_label.pack(pady=8)

        self.load_theme_list(self.cfg.get("theme", "scuro"))
        self.tick_preview()

    def load_theme_list(self, select):
        themes = ui.list_themes()
        if not themes:
            ui.save_theme("scuro", ui.DEFAULT_THEME)
            themes = ui.list_themes()
        self.theme_ids = list(themes)
        self.theme_box["values"] = [themes[i] for i in self.theme_ids]
        self.select_theme(select if select in themes else self.theme_ids[0])

    def select_theme(self, theme_id):
        self.theme_id = theme_id
        self.theme = ui.read_theme(theme_id)
        self.theme_box.current(self.theme_ids.index(theme_id))
        self.set("theme", theme_id)
        for k, sw in self.swatches.items():
            sw.configure(bg=self.theme["colors"][k], activebackground=self.theme["colors"][k])
        folder = ui.THEMES / theme_id
        own = sorted(p.name for p in folder.iterdir() if p.suffix.lower() in (".ttf", ".otf", ".ttc"))
        system = sorted(p.name for p in FONTS_DIR.glob("*") if p.suffix.lower() in (".ttf", ".otf", ".ttc"))
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
        _, hexcolor = colorchooser.askcolor(self.theme["colors"][k], parent=self, title=COLOR_LABELS[k])
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
            shutil.copy(path, ui.THEMES / self.theme_id / Path(path).name)  # dentro il tema: viaggia con l'export
            self.select_theme(self.theme_id)
            self.font_boxes[k].set(Path(path).name)
            self.set_theme_font(k, Path(path).name)

    def set_scale(self):
        try:
            v = float(self.scale_var.get().replace(",", "."))
        except ValueError:
            return
        if 0.5 <= v <= 2:
            self.theme["font"]["scale"] = round(v, 2)
            self.save_theme()

    def refresh_bg_label(self):
        page = self.bg_page.get()
        name = self.theme["backgrounds"].get(page) if page else None
        self.bg_label.configure(text=f"{page}: {name}" if name else (f"{page}: nessuno sfondo" if page else
                                                                     "Scegli una pagina"))

    def pick_background(self):
        page = self.bg_page.get()
        if not page:
            messagebox.showinfo("Sfondi", "Scegli prima la pagina.")
            return
        path = filedialog.askopenfilename(parent=self, filetypes=IMAGE_TYPES)
        if not path:
            return
        name = f"bg_{page}{Path(path).suffix.lower()}"
        shutil.copy(path, ui.THEMES / self.theme_id / name)
        self.theme["backgrounds"][page] = name
        self.save_theme()
        self.refresh_bg_label()

    def remove_background(self):
        page = self.bg_page.get()
        name = self.theme["backgrounds"].pop(page, None)
        if name:
            (ui.THEMES / self.theme_id / name).unlink(missing_ok=True)
            self.save_theme()
            self.refresh_bg_label()

    def new_theme(self):
        name = simpledialog.askstring("Nuovo tema", "Nome del nuovo tema:", parent=self)
        if not name:
            return
        new_id, n = safe_id(name), 2
        while (ui.THEMES / new_id).exists():
            new_id, n = f"{safe_id(name)} {n}", n + 1
        ui.save_theme(self.theme_id, self.theme)
        shutil.copytree(ui.THEMES / self.theme_id, ui.THEMES / new_id)
        ui.save_theme(new_id, {**self.theme, "name": name})
        self.load_theme_list(new_id)

    def rename_theme(self):
        name = simpledialog.askstring("Rinomina", "Nuovo nome:", initialvalue=self.theme["name"], parent=self)
        if name:
            self.theme["name"] = name
            ui.save_theme(self.theme_id, self.theme)
            self.load_theme_list(self.theme_id)

    def delete_theme(self):
        if len(self.theme_ids) == 1:
            messagebox.showinfo("Tema", "È l'unico tema rimasto.")
            return
        if not messagebox.askyesno("Elimina tema", f"Eliminare il tema “{self.theme['name']}” e i suoi file?"):
            return
        shutil.rmtree(ui.THEMES / self.theme_id)
        self.load_theme_list(next(i for i in self.theme_ids if i != self.theme_id))

    def export_theme(self):
        ui.save_theme(self.theme_id, self.theme)
        path = filedialog.asksaveasfilename(parent=self, defaultextension=ui.THEME_EXT,
                                            initialfile=self.theme["name"] + ui.THEME_EXT,
                                            filetypes=[("Tema schermetto", "*" + ui.THEME_EXT)])
        if path:
            ui.export_theme(self.theme_id, Path(path))

    def import_theme(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Tema schermetto", "*" + ui.THEME_EXT)])
        if not path:
            return
        try:
            self.load_theme_list(ui.import_theme(Path(path)))
        except Exception as e:
            messagebox.showerror("Importa tema", f"File non valido: {e}")

    # --- anteprima ------------------------------------------------------
    def fetch_data(self):
        """Thread: aggiorna i dati veri per anteprima ed editor ogni 5 secondi."""
        async def run():
            while True:
                for n, src in self.all_sources.items():
                    try:
                        self.data[n] = await src.fetch(self.section(n))
                    except Exception:
                        pass
                try:
                    self.after(0, self.on_data)
                except RuntimeError:  # finestra chiusa
                    return
                await asyncio.sleep(5)
        asyncio.run(run())

    def on_data(self):
        self.render_preview()
        if self.editor.drag is None:
            self.editor.redraw()

    def render_preview(self):
        if not hasattr(self, "preview_label"):
            return
        page = self.all_pages.get(self.preview_page.get())
        if not page:
            return
        ui.apply_theme(self.theme, ui.THEMES / self.theme_id)
        size = Screen(orientation=self.cfg.get("orientation", "portrait")).size
        try:
            img = page.render(self.data, size, self.section(page.name))
        except Exception as e:
            self.preview_label.configure(image="", text=f"Errore: {e}")
            return
        self._photo = ImageTk.PhotoImage(img)
        self.preview_label.configure(image=self._photo, text="")

    def tick_preview(self):
        self.render_preview()
        self.after(2000, self.tick_preview)

    # --- Servizio -------------------------------------------------------
    def build_service(self, f):
        self.status = ttk.Label(f, font=("Segoe UI", 12, "bold"))
        self.status.pack(anchor="w", pady=(0, 12))
        btns = ttk.Frame(f)
        btns.pack(anchor="w")
        for text, cmd in (("Avvia", service.start), ("Ferma", service.stop), ("Riavvia", service.restart)):
            ttk.Button(btns, text=text, command=lambda c=cmd: self.run_service(c)).pack(side="left", padx=(0, 6))
        self.autostart = tk.BooleanVar(value=service.get_autostart())
        ttk.Checkbutton(f, text="Avvia lo schermetto all'accesso a Windows", variable=self.autostart,
                        command=lambda: service.set_autostart(self.autostart.get())).pack(anchor="w", pady=12)
        ttk.Button(f, text="Apri log", command=lambda: service.LOG.exists() and os.startfile(service.LOG)).pack(anchor="w")
        ttk.Label(f, foreground="gray", wraplength=600, justify="left", text=(
            "Le modifiche si applicano subito, senza riavviare. Lo schermetto e UsbMonitor.exe non possono "
            "funzionare insieme: chiudi UsbMonitor e togli il suo avvio automatico.")).pack(anchor="w", pady=16)
        self.poll_status()

    def run_service(self, cmd):
        self.status.configure(text="…")
        threading.Thread(target=lambda: (cmd(), self.after(0, self.refresh_status)), daemon=True).start()

    def refresh_status(self):
        pid = service.running_pid()
        self.status.configure(text=f"● In esecuzione (pid {pid})" if pid else "○ Fermo",
                              foreground="green" if pid else "gray")

    def poll_status(self):
        self.refresh_status()
        self.after(2000, self.poll_status)


if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # testo nitido con lo scaling di Windows
    except (AttributeError, OSError):
        pass
    Settings().mainloop()
