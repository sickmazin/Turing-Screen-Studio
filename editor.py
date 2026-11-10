"""Editor delle pagine a layout (scheda Pagine di settings.py).

Trascina un widget dalla tavolozza sullo schermo, spostalo col mouse, ridimensionalo dal quadratino in basso
a destra, modifica le proprietà a destra. Tasti: frecce (Shift = 8 px), Canc, Ctrl+D duplica, Ctrl+Z annulla.
"""
import copy
import json
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

import layout
from widgets import ASSETS, COLOR_CHOICES, WIDGETS

ORIENT_LABELS = {"portrait": "Verticale", "landscape": "Orizzontale"}
GRID = 8
HANDLE = 8


def field_paths(obj, prefix="", depth=0):
    """Elenco dei campi disponibili nei dati, per i menu a tendina."""
    if depth > 5:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from field_paths(v, f"{prefix}{k}.", depth + 1)
    elif isinstance(obj, list) and obj and not all(isinstance(v, (int, float)) for v in obj):
        for i, v in enumerate(obj[:5]):
            yield from field_paths(v, f"{prefix}{i}.", depth + 1)
    elif prefix:
        yield prefix[:-1]


def new_page_id(name, existing):
    base = "".join(c for c in name.lower() if c.isalnum() or c in "-_") or "pagina"
    pid, n = base, 2
    while pid in existing:
        pid, n = f"{base}{n}", n + 1
    return pid


class PageEditor(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.layouts = layout.load_layouts()
        self.page_id = None
        self.orient = "landscape" if "landscape" in app.cfg.get("orientation", "portrait") else "portrait"
        self.widgets = []
        self.sel = None
        self.undo = []
        self.drag = None
        self.palette_type = None
        self._redraw_job = None
        sh = app.winfo_screenheight()
        self.zoom = 1.5 if sh >= 1300 else 1.25 if sh >= 1000 else 1.0

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.build_pages_column().grid(row=0, column=0, sticky="ns", padx=(0, 10))
        self.build_canvas_column().grid(row=0, column=1, sticky="n")
        self.build_side_column().grid(row=0, column=2, sticky="ns", padx=(10, 0))
        self.refresh_page_lists()
        first = next((p for p in app.cfg.get("pages", []) if p in self.layouts), next(iter(self.layouts), None))
        if first:
            self.open_page(first)

    # --- colonna pagine -------------------------------------------------
    def build_pages_column(self):
        f = ttk.Frame(self)
        ttk.Label(f, text="Pagine sullo schermo").pack(anchor="w")
        self.active = tk.Listbox(f, height=9, exportselection=False, width=22)
        self.active.pack(fill="x")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=4)
        for text, cmd in (("▲", lambda: self.move_page(-1)), ("▼", lambda: self.move_page(1)), ("Togli", self.hide_page)):
            ttk.Button(row, text=text, width=5 if len(text) > 1 else 3, command=cmd).pack(side="left", padx=(0, 4))
        ttk.Label(f, text="Altre pagine").pack(anchor="w", pady=(8, 0))
        self.hidden = tk.Listbox(f, height=5, exportselection=False, width=22)
        self.hidden.pack(fill="x")
        ttk.Button(f, text="▲ Mostra sullo schermo", command=self.show_page).pack(fill="x", pady=4)
        ttk.Separator(f).pack(fill="x", pady=8)
        for text, cmd in (("Nuova pagina", self.new_page), ("Duplica pagina", self.duplicate_page),
                          ("Rinomina pagina", self.rename_page), ("Elimina pagina", self.delete_page)):
            ttk.Button(f, text=text, command=cmd).pack(fill="x", pady=2)
        self.active.bind("<<ListboxSelect>>", lambda e: self.pick_from(self.active, self.active_ids))
        self.hidden.bind("<<ListboxSelect>>", lambda e: self.pick_from(self.hidden, self.hidden_ids))
        return f

    def refresh_page_lists(self):
        order = self.app.cfg.setdefault("pages", [])
        self.active_ids = [p for p in order if p in self.layouts]
        self.hidden_ids = sorted(set(self.layouts) - set(self.active_ids))
        for lb, ids in ((self.active, self.active_ids), (self.hidden, self.hidden_ids)):
            lb.delete(0, "end")
            for pid in ids:
                lb.insert("end", self.layouts[pid].title)
            if self.page_id in ids:
                lb.selection_set(ids.index(self.page_id))

    def pick_from(self, lb, ids):
        sel = lb.curselection()
        if sel:
            self.open_page(ids[sel[0]])

    def move_page(self, step):
        order = self.app.cfg["pages"]
        if self.page_id not in order:
            return
        i = order.index(self.page_id)
        if 0 <= i + step < len(order):
            order[i], order[i + step] = order[i + step], order[i]
            self.app.save()
            self.refresh_page_lists()

    def hide_page(self):
        order = self.app.cfg["pages"]
        if self.page_id in order:
            if len(order) == 1:
                messagebox.showinfo("Pagine", "Serve almeno una pagina sullo schermo.")
                return
            order.remove(self.page_id)
            self.app.save()
            self.refresh_page_lists()

    def show_page(self):
        if self.page_id and self.page_id not in self.app.cfg["pages"]:
            self.app.cfg["pages"].append(self.page_id)
            self.app.save()
            self.refresh_page_lists()

    def new_page(self, data=None):
        name = simpledialog.askstring("Nuova pagina", "Nome della pagina:", parent=self)
        if not name:
            return
        pid = new_page_id(name, set(self.layouts) | set(self.app.all_pages))
        data = copy.deepcopy(data) if data else {"portrait": [], "landscape": []}
        data["name"] = name
        layout.save_layout(pid, data)
        self.layouts[pid] = layout.LayoutPage(pid, data)
        self.app.cfg["pages"].append(pid)
        self.app.save()
        self.open_page(pid)

    def duplicate_page(self):
        if self.page_id:
            self.flush()
            self.new_page(self.layouts[self.page_id].data)

    def rename_page(self):
        if not self.page_id:
            return
        data = self.layouts[self.page_id].data
        name = simpledialog.askstring("Rinomina", "Nuovo nome:", initialvalue=data.get("name", ""), parent=self)
        if name:
            data["name"] = name
            self.layouts[self.page_id].title = name
            self.save_now()
            self.refresh_page_lists()

    def delete_page(self):
        if not self.page_id:
            return
        if len(self.layouts) == 1:
            messagebox.showinfo("Pagine", "È l'ultima pagina rimasta.")
            return
        if not messagebox.askyesno("Elimina pagina", f"Eliminare la pagina “{self.layouts[self.page_id].title}”?"):
            return
        (layout.LAYOUTS / f"{self.page_id}.json").unlink(missing_ok=True)
        del self.layouts[self.page_id]
        if self.page_id in self.app.cfg["pages"]:
            self.app.cfg["pages"].remove(self.page_id)
            self.app.save()
        self.page_id = None
        self.open_page(next(iter(self.layouts)))

    # --- colonna canvas -------------------------------------------------
    def build_canvas_column(self):
        f = ttk.Frame(self)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(0, 6))
        self.orient_var = tk.StringVar(value=self.orient)
        for o, text in ORIENT_LABELS.items():
            ttk.Radiobutton(bar, text=text, value=o, variable=self.orient_var,
                            command=lambda: self.set_orient(self.orient_var.get())).pack(side="left")
        ttk.Button(bar, text="Copia dall'altro orientamento", command=self.copy_other).pack(side="left", padx=8)
        self.snap = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Griglia", variable=self.snap).pack(side="left")
        self.canvas = tk.Canvas(f, highlightthickness=1, highlightbackground="#888", cursor="arrow")
        self.canvas.pack()
        tools = ttk.Frame(f)
        tools.pack(fill="x", pady=6)
        for text, cmd in (("Annulla", self.do_undo), ("Duplica widget", self.duplicate_widget),
                          ("Elimina widget", self.delete_widget), ("Porta avanti", lambda: self.restack(1)),
                          ("Porta indietro", lambda: self.restack(-1))):
            ttk.Button(tools, text=text, command=cmd).pack(side="left", padx=(0, 4))
        self.hint = ttk.Label(f, foreground="gray", text="Trascina un widget dalla tavolozza sullo schermo.")
        self.hint.pack(anchor="w")
        c = self.canvas
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_motion)
        c.bind("<ButtonRelease-1>", self.on_release)
        for key, dx, dy in (("Left", -1, 0), ("Right", 1, 0), ("Up", 0, -1), ("Down", 0, 1)):
            c.bind(f"<{key}>", lambda e, dx=dx, dy=dy: self.nudge(dx, dy, 1))
            c.bind(f"<Shift-{key}>", lambda e, dx=dx, dy=dy: self.nudge(dx, dy, GRID))
        c.bind("<Delete>", lambda e: self.delete_widget())
        c.bind("<Control-d>", lambda e: self.duplicate_widget())
        c.bind("<Control-z>", lambda e: self.do_undo())
        return f

    def set_orient(self, o):
        self.flush()
        self.orient = o
        self.open_page(self.page_id)

    def copy_other(self):
        other = "landscape" if self.orient == "portrait" else "portrait"
        src = self.layouts[self.page_id].data.get(other) or []
        if not src:
            messagebox.showinfo("Copia", "L'altro orientamento è vuoto.")
            return
        if self.widgets and not messagebox.askyesno("Copia", "Sostituire il layout attuale con quello adattato?"):
            return
        self.snapshot()
        self.widgets[:] = layout.scale_widgets(src, other, self.orient)
        self.select(None)
        self.changed()

    def open_page(self, pid):
        if pid is None:
            return
        if pid != self.page_id:
            self.flush()
            self.undo.clear()
        self.page_id = pid
        data = self.layouts[pid].data
        if not data.get(self.orient):
            other = "landscape" if self.orient == "portrait" else "portrait"
            # punto di partenza: l'altro orientamento adattato (diventa suo alla prima modifica)
            data[self.orient] = layout.scale_widgets(data.get(other) or [], other, self.orient)
        self.widgets = data[self.orient]
        w, h = layout.SIZES[self.orient]
        self.canvas.configure(width=int(w * self.zoom), height=int(h * self.zoom))
        self.sel = None
        self.refresh_page_lists()
        self.refresh_layers()
        self.build_props()
        self.redraw()

    # --- disegno --------------------------------------------------------
    def redraw_later(self):
        if not self._redraw_job:
            self._redraw_job = self.after(30, self.redraw)

    def redraw(self):
        self._redraw_job = None
        if not self.page_id:
            return
        size = layout.SIZES[self.orient]
        page = layout.LayoutPage(self.page_id, {self.orient: self.widgets})
        img = page.render(self.app.data, size, {})
        if self.zoom != 1:
            img = img.resize((int(size[0] * self.zoom), int(size[1] * self.zoom)), Image.Resampling.BILINEAR)
        self._photo = ImageTk.PhotoImage(img)
        c = self.canvas
        c.delete("all")
        c.create_image(0, 0, image=self._photo, anchor="nw")
        if self.sel is not None and self.sel < len(self.widgets):
            x0, y0, x1, y1 = (v * self.zoom for v in self.box(self.widgets[self.sel]))
            c.create_rectangle(x0, y0, x1, y1, outline="#ffcc00", dash=(4, 2), width=2)
            c.create_rectangle(x1 - HANDLE, y1 - HANDLE, x1, y1, fill="#ffcc00", outline="")

    @staticmethod
    def box(w):
        return w["x"], w["y"], w["x"] + w["w"], w["y"] + w["h"]

    # --- mouse ----------------------------------------------------------
    def to_screen(self, e):
        return e.x / self.zoom, e.y / self.zoom

    def hit(self, x, y):
        if self.sel is not None and self.inside(self.widgets[self.sel], x, y):
            return self.sel  # il selezionato ha la precedenza: si possono spostare anche i widget grandi
        for i in range(len(self.widgets) - 1, -1, -1):
            if self.inside(self.widgets[i], x, y):
                return i
        return None

    @staticmethod
    def inside(w, x, y):
        return w["x"] <= x <= w["x"] + w["w"] and w["y"] <= y <= w["y"] + w["h"]

    def on_press(self, e):
        self.canvas.focus_set()
        x, y = self.to_screen(e)
        if self.sel is not None:
            w = self.widgets[self.sel]
            if abs(x - (w["x"] + w["w"])) <= HANDLE / self.zoom + 2 and abs(y - (w["y"] + w["h"])) <= HANDLE / self.zoom + 2:
                self.drag = ("resize", x, y, dict(w), False)
                return
        i = self.hit(x, y)
        self.select(i)
        self.drag = ("move", x, y, dict(self.widgets[i]), False) if i is not None else None

    def snapv(self, v):
        return round(v / GRID) * GRID if self.snap.get() else round(v)

    def on_motion(self, e):
        if not self.drag or self.sel is None:
            return
        mode, sx, sy, orig, pushed = self.drag
        if not pushed:
            self.snapshot(orig_index=self.sel, orig=orig)
            self.drag = (mode, sx, sy, orig, True)
        x, y = self.to_screen(e)
        w = self.widgets[self.sel]
        sw, sh = layout.SIZES[self.orient]
        if mode == "move":
            w["x"] = max(-w["w"] + 8, min(sw - 8, self.snapv(orig["x"] + x - sx)))
            w["y"] = max(-w["h"] + 8, min(sh - 8, self.snapv(orig["y"] + y - sy)))
        else:
            w["w"] = max(4, self.snapv(orig["w"] + x - sx))
            w["h"] = max(2, self.snapv(orig["h"] + y - sy))
        self.update_geometry_fields()
        self.redraw_later()

    def on_release(self, e):
        if self.drag and self.drag[4]:
            self.changed()
        self.drag = None

    def nudge(self, dx, dy, step):
        if self.sel is None:
            return
        self.snapshot()
        w = self.widgets[self.sel]
        w["x"] += dx * step
        w["y"] += dy * step
        self.update_geometry_fields()
        self.changed()

    # --- tavolozza (drag & drop) ----------------------------------------
    def build_side_column(self):
        f = ttk.Frame(self)
        ttk.Label(f, text="Tavolozza (trascina sullo schermo)").pack(anchor="w")
        self.palette = tk.Listbox(f, height=9, exportselection=False, width=34)
        self.palette.pack(fill="x")
        self.palette_ids = list(WIDGETS)
        for t in self.palette_ids:
            self.palette.insert("end", WIDGETS[t].label)
        self.palette.bind("<ButtonPress-1>", self.palette_press)
        self.palette.bind("<B1-Motion>", lambda e: self.palette.configure(cursor="plus") if self.palette_type else None)
        self.palette.bind("<ButtonRelease-1>", self.palette_drop)
        self.palette.bind("<Double-Button-1>", lambda e: self.add_widget(self.palette_ids[self.palette.nearest(e.y)]))

        ttk.Label(f, text="Livelli (in alto = davanti)").pack(anchor="w", pady=(10, 0))
        self.layers = tk.Listbox(f, height=7, exportselection=False, width=34)
        self.layers.pack(fill="x")
        self.layers.bind("<<ListboxSelect>>", self.layer_pick)

        self.props = ttk.LabelFrame(f, text="Proprietà", padding=6)
        self.props.pack(fill="both", expand=True, pady=(10, 0))
        return f

    def palette_press(self, e):
        self.palette_type = self.palette_ids[self.palette.nearest(e.y)]

    def palette_drop(self, e):
        self.palette.configure(cursor="")
        t, self.palette_type = self.palette_type, None
        if not t:
            return
        px, py = self.winfo_pointerxy()
        if self.winfo_containing(px, py) is not self.canvas:
            return
        x = (px - self.canvas.winfo_rootx()) / self.zoom
        y = (py - self.canvas.winfo_rooty()) / self.zoom
        self.add_widget(t, x, y)

    def add_widget(self, t, x=None, y=None):
        if not self.page_id:
            return
        cls = WIDGETS[t]
        sw, sh = layout.SIZES[self.orient]
        ww, wh = min(cls.size[0], sw), min(cls.size[1], sh)
        x = sw / 2 if x is None else x
        y = sh / 2 if y is None else y
        self.snapshot()
        w = cls.new(self.snapv(max(0, min(sw - ww, x - ww / 2))), self.snapv(max(0, min(sh - wh, y - wh / 2))))
        w["w"], w["h"] = ww, wh
        self.widgets.append(w)
        self.select(len(self.widgets) - 1)
        self.changed()

    # --- livelli --------------------------------------------------------
    def describe(self, w):
        cls = WIDGETS.get(w["type"])
        extra = w.get("text") or w.get("field") or w.get("char") or w.get("file") or ""
        extra = f" · {extra}" if extra else (f" #{w['index']}" if "index" in w else "")
        return (cls.label if cls else w["type"]) + extra[:28]

    def refresh_layers(self):
        self.layers.delete(0, "end")
        for w in reversed(self.widgets):
            self.layers.insert("end", self.describe(w))
        if self.sel is not None:
            self.layers.selection_set(len(self.widgets) - 1 - self.sel)

    def layer_pick(self, e):
        s = self.layers.curselection()
        if s:
            self.select(len(self.widgets) - 1 - s[0], from_layers=True)

    def select(self, i, from_layers=False):
        self.sel = i
        if not from_layers:
            self.layers.selection_clear(0, "end")
            if i is not None:
                self.layers.selection_set(len(self.widgets) - 1 - i)
        self.build_props()
        self.redraw()

    def restack(self, step):
        if self.sel is None:
            return
        j = self.sel + step
        if 0 <= j < len(self.widgets):
            self.snapshot()
            self.widgets[self.sel], self.widgets[j] = self.widgets[j], self.widgets[self.sel]
            self.sel = j
            self.changed()

    def duplicate_widget(self):
        if self.sel is None:
            return
        self.snapshot()
        w = copy.deepcopy(self.widgets[self.sel])
        w["x"] += GRID * 2
        w["y"] += GRID * 2
        self.widgets.append(w)
        self.select(len(self.widgets) - 1)
        self.changed()

    def delete_widget(self):
        if self.sel is None:
            return
        self.snapshot()
        self.widgets.pop(self.sel)
        self.select(None)
        self.changed()

    # --- proprietà ------------------------------------------------------
    def build_props(self):
        for child in self.props.winfo_children():
            child.destroy()
        self.geo_vars = {}
        if self.sel is None:
            ttk.Label(self.props, text="Seleziona un widget sullo schermo.", foreground="gray").grid()
            return
        w = self.widgets[self.sel]
        cls = WIDGETS.get(w["type"])
        self.props.configure(text=f"Proprietà: {cls.label if cls else w['type']}")
        geo = ttk.Frame(self.props)
        geo.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        for i, k in enumerate(("x", "y", "w", "h")):
            ttk.Label(geo, text=k).grid(row=0, column=i * 2, padx=(0 if i == 0 else 6, 2))
            v = tk.StringVar(value=str(w[k]))
            sp = ttk.Spinbox(geo, from_=-500, to=1000, textvariable=v, width=5)
            sp.grid(row=0, column=i * 2 + 1)
            v.trace_add("write", lambda *_, k=k, v=v: self.set_geo(k, v))
            self.geo_vars[k] = v
        fields = sorted(set(field_paths(layout.with_clock(self.app.data))))
        for r, (key, kind, default, label) in enumerate(cls.props if cls else [], start=1):
            ttk.Label(self.props, text=label).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 6))
            value = w.get(key, default)
            if kind == "bool":
                var = tk.BooleanVar(value=bool(value))
                ttk.Checkbutton(self.props, variable=var, command=lambda k=key, v=var: self.set_prop(k, v.get())).grid(
                    row=r, column=1, sticky="w")
            elif kind in ("int", "float"):
                var = tk.StringVar(value=str(value))
                ttk.Spinbox(self.props, from_=0, to=2000 if kind == "int" else 1, increment=1 if kind == "int" else 0.05,
                            textvariable=var, width=8).grid(row=r, column=1, sticky="w")
                var.trace_add("write", lambda *_, k=key, v=var, t=kind: self.set_number(k, v, t))
            elif kind.startswith("choice:"):
                cb = ttk.Combobox(self.props, values=kind[7:].split("|"), state="readonly", width=12)
                cb.set(value)
                cb.grid(row=r, column=1, sticky="w")
                cb.bind("<<ComboboxSelected>>", lambda e, k=key, c=cb: self.set_prop(k, c.get()))
            elif kind == "color":
                cb = ttk.Combobox(self.props, values=COLOR_CHOICES, width=12)
                cb.set(value)
                cb.grid(row=r, column=1, sticky="w")
                cb.bind("<<ComboboxSelected>>", lambda e, k=key, c=cb: self.set_prop(k, c.get()))
                cb.bind("<Return>", lambda e, k=key, c=cb: self.set_prop(k, c.get()))
                ttk.Button(self.props, text="…", width=3, command=lambda k=key, c=cb: self.pick_color(k, c)).grid(row=r, column=2)
            elif kind == "file":
                ttk.Button(self.props, text=value or "Scegli…", command=lambda k=key: self.pick_file(k)).grid(
                    row=r, column=1, sticky="w")
            else:  # text / field
                cb = ttk.Combobox(self.props, values=fields if kind == "field" else [], width=30)
                cb.set(value)
                cb.grid(row=r, column=1, columnspan=2, sticky="we")
                commit = lambda e, k=key, c=cb: self.set_prop(k, c.get())
                cb.bind("<Return>", commit)
                cb.bind("<FocusOut>", commit)
                cb.bind("<<ComboboxSelected>>", commit)
                if kind == "text" and key == "text":
                    r2 = ttk.Frame(self.props)
                    r2.grid(row=r, column=3, sticky="w", padx=(4, 0))
                    ins = ttk.Combobox(r2, values=fields, width=16)
                    ins.set("+ campo")
                    ins.pack()
                    ins.bind("<<ComboboxSelected>>", lambda e, c=cb, i=ins: (c.insert("insert", "{" + i.get() + "}"),
                                                                             i.set("+ campo"), self.set_prop("text", c.get())))
        ttk.Label(self.props, foreground="gray", wraplength=330, justify="left", text=(
            "Formati: {campo:.0f} {campo:mmss} {campo:human} {campo:bytes} {campo:gb} {campo:hm} "
            "{campo:meteo} {campo:giorno} {campo:reset} {now:%H:%M}. Colori: level = verde/giallo/rosso, "
            "sign = verde se positivo.")).grid(row=99, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def update_geometry_fields(self):
        if self.sel is None:
            return
        w = self.widgets[self.sel]
        self._updating = True
        for k, v in self.geo_vars.items():
            if v.get() != str(w[k]):
                v.set(str(w[k]))
        self._updating = False

    def set_geo(self, k, var):
        if getattr(self, "_updating", False) or self.sel is None:
            return
        try:
            value = int(var.get())
        except ValueError:
            return
        w = self.widgets[self.sel]
        if w[k] != value:
            self.snapshot()
            w[k] = value
            self.changed(layers=False)

    def set_number(self, k, var, kind):
        try:
            value = int(var.get()) if kind == "int" else float(var.get().replace(",", "."))
        except ValueError:
            return
        self.set_prop(k, value)

    def set_prop(self, k, value):
        if self.sel is None:
            return
        w = self.widgets[self.sel]
        if w.get(k) == value:
            return
        self.snapshot()
        w[k] = value
        self.changed()

    def pick_color(self, k, cb):
        start = cb.get() if cb.get().startswith("#") else None
        _, hexcolor = colorchooser.askcolor(start, parent=self)
        if hexcolor:
            cb.set(hexcolor)
            self.set_prop(k, hexcolor)

    def pick_file(self, k):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Immagini", "*.png *.jpg *.jpeg *.bmp *.webp *.gif")])
        if not path:
            return
        ASSETS.mkdir(parents=True, exist_ok=True)
        name = Path(path).name
        if not (ASSETS / name).exists():
            shutil.copy(path, ASSETS / name)
        self.set_prop(k, name)
        self.build_props()

    # --- annulla e salvataggio --------------------------------------------
    def snapshot(self, orig_index=None, orig=None):
        state = copy.deepcopy(self.widgets)
        if orig_index is not None:
            state[orig_index] = copy.deepcopy(orig)
        self.undo.append((self.page_id, self.orient, json.dumps(state)))
        del self.undo[:-50]

    def do_undo(self):
        while self.undo:
            pid, orient, state = self.undo.pop()
            if (pid, orient) == (self.page_id, self.orient):
                self.widgets[:] = json.loads(state)
                self.select(None)
                self.changed()
                return

    def changed(self, layers=True):
        if layers:
            self.refresh_layers()
        self.redraw_later()
        self.app.later("layout", self.save_now, 400)

    def save_now(self):
        if self.page_id in self.layouts:
            data = self.layouts[self.page_id].data
            layout.save_layout(self.page_id, data)
            self.layouts[self.page_id] = layout.LayoutPage(self.page_id, data)

    def flush(self):
        """Salva subito eventuali modifiche in attesa (prima di cambiare pagina o orientamento)."""
        self.app.run_now("layout")
