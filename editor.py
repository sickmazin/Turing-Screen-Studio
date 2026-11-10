"""Layout page editor (Pages tab of the settings window).

Drag a widget from the palette onto the screen, move it with the mouse, resize it from the square in the
bottom-right corner, edit its properties on the right.
Mouse: Shift/Ctrl+click adds to the selection, a grouped widget selects its whole group (Alt+click: only it).
Keys: arrows (Shift = 8 px), Del, Ctrl+D duplicate, Ctrl+Z undo, Ctrl+A select all, Ctrl+G group, Ctrl+Shift+G ungroup.
"""
import copy
import json
import shutil
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

import layout
import paths
from i18n import _
from widgets import COLOR_CHOICES, WIDGETS

ORIENT_LABELS = {"portrait": "Portrait", "landscape": "Landscape"}
GRID = 8
HANDLE = 8
SNAP = 5          # pixels within which an edge snaps to a guide
GUIDE_COLOR = "#ff3df2"
SELECT_COLOR = "#ffcc00"


def field_paths(obj, prefix="", depth=0):
    """Every data field available, for the drop-down menus."""
    if depth > 5:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not str(k).startswith("_"):
                yield from field_paths(v, f"{prefix}{k}.", depth + 1)
    elif isinstance(obj, list) and obj and not all(isinstance(v, (int, float)) for v in obj):
        for i, v in enumerate(obj[:5]):
            yield from field_paths(v, f"{prefix}{i}.", depth + 1)
    elif prefix:
        yield prefix[:-1]


def new_page_id(name, existing):
    base = "".join(c for c in name.lower() if c.isalnum() or c in "-_") or "page"
    pid, n = base, 2
    while pid in existing:
        pid, n = f"{base}{n}", n + 1
    return pid


def bbox(widgets):
    return (min(w["x"] for w in widgets), min(w["y"] for w in widgets),
            max(w["x"] + w["w"] for w in widgets), max(w["y"] + w["h"] for w in widgets))


class PageEditor(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.layouts = layout.load_layouts()
        self.page_id = None
        self.orient = "landscape" if "landscape" in app.cfg.get("orientation", "portrait") else "portrait"
        self.widgets = []
        self.sel = []          # selected widget indices
        self.undo = []
        self.drag = None
        self.guides = []
        self.palette_type = None
        self._redraw_job = None
        self._updating = False
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

    # --- pages column ---------------------------------------------------
    def build_pages_column(self):
        f = ttk.Frame(self)
        ttk.Label(f, text=_("Pages on the screen")).pack(anchor="w")
        self.active = tk.Listbox(f, height=9, exportselection=False, width=22)
        self.active.pack(fill="x")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=4)
        for text, cmd in (("▲", lambda: self.move_page(-1)), ("▼", lambda: self.move_page(1)), (_("Hide"), self.hide_page)):
            ttk.Button(row, text=text, width=6 if len(text) > 1 else 3, command=cmd).pack(side="left", padx=(0, 4))
        ttk.Label(f, text=_("Other pages")).pack(anchor="w", pady=(8, 0))
        self.hidden = tk.Listbox(f, height=5, exportselection=False, width=22)
        self.hidden.pack(fill="x")
        ttk.Button(f, text=_("▲ Show on the screen"), command=self.show_page).pack(fill="x", pady=4)
        ttk.Separator(f).pack(fill="x", pady=8)
        for text, cmd in (("New page", self.new_page), ("Duplicate page", self.duplicate_page),
                          ("Rename page", self.rename_page), ("Delete page", self.delete_page),
                          ("Import page…", self.import_page), ("Export page…", self.export_page)):
            ttk.Button(f, text=_(text), command=cmd).pack(fill="x", pady=2)
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
        s = lb.curselection()
        if s:
            self.open_page(ids[s[0]])

    def move_page(self, step):
        order = self.app.cfg["pages"]
        if self.page_id in order:
            i = order.index(self.page_id)
            if 0 <= i + step < len(order):
                order[i], order[i + step] = order[i + step], order[i]
                self.app.save()
                self.refresh_page_lists()

    def hide_page(self):
        order = self.app.cfg["pages"]
        if self.page_id in order:
            if len(order) == 1:
                messagebox.showinfo(_("Pages"), _("At least one page must stay on the screen."))
                return
            order.remove(self.page_id)
            self.app.save()
            self.refresh_page_lists()

    def show_page(self):
        if self.page_id and self.page_id not in self.app.cfg["pages"]:
            self.app.cfg["pages"].append(self.page_id)
            self.app.save()
            self.refresh_page_lists()

    def add_layout(self, pid, data):
        layout.save_layout(pid, data)
        self.layouts[pid] = layout.LayoutPage(pid, data)
        self.app.cfg["pages"].append(pid)
        self.app.save()
        self.open_page(pid)

    def new_page(self, data=None):
        name = simpledialog.askstring(_("New page"), _("Page name:"), parent=self)
        if name:
            data = copy.deepcopy(data) if data else {"portrait": [], "landscape": []}
            data["name"] = name
            self.add_layout(new_page_id(name, set(self.layouts) | set(self.app.all_pages)), data)

    def duplicate_page(self):
        if self.page_id:
            self.flush()
            self.new_page(self.layouts[self.page_id].data)

    def rename_page(self):
        if not self.page_id:
            return
        data = self.layouts[self.page_id].data
        name = simpledialog.askstring(_("Rename"), _("New name:"), initialvalue=self.layouts[self.page_id].title, parent=self)
        if name:
            data["name"] = name
            self.save_now()
            self.refresh_page_lists()

    def delete_page(self):
        if not self.page_id:
            return
        if len(self.layouts) == 1:
            messagebox.showinfo(_("Pages"), _("It is the last page left."))
            return
        if not messagebox.askyesno(_("Delete page"), _("Delete this page?") + f"\n{self.layouts[self.page_id].title}"):
            return
        (paths.LAYOUTS / f"{self.page_id}.json").unlink(missing_ok=True)
        del self.layouts[self.page_id]
        if self.page_id in self.app.cfg["pages"]:
            self.app.cfg["pages"].remove(self.page_id)
            self.app.save()
        self.page_id = None
        self.open_page(next(iter(self.layouts)))

    def export_page(self):
        if not self.page_id:
            return
        self.flush()
        path = filedialog.asksaveasfilename(parent=self, defaultextension=layout.PAGE_EXT,
                                            initialfile=self.layouts[self.page_id].title + layout.PAGE_EXT,
                                            filetypes=[(_("Screen page"), "*" + layout.PAGE_EXT)])
        if path:
            layout.export_page(self.page_id, Path(path))

    def import_page(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[(_("Screen page"), "*" + layout.PAGE_EXT)])
        if not path:
            return
        try:
            pid = layout.import_page(Path(path), set(self.layouts) | set(self.app.all_pages))
        except Exception as e:
            messagebox.showerror(_("Import page"), _("Invalid file: ") + str(e))
            return
        self.layouts = layout.load_layouts()
        self.app.cfg["pages"].append(pid)
        self.app.save()
        self.open_page(pid)

    # --- canvas column --------------------------------------------------
    def build_canvas_column(self):
        f = ttk.Frame(self)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(0, 6))
        self.orient_var = tk.StringVar(value=self.orient)
        for o, text in ORIENT_LABELS.items():
            ttk.Radiobutton(bar, text=_(text), value=o, variable=self.orient_var,
                            command=lambda: self.set_orient(self.orient_var.get())).pack(side="left")
        ttk.Button(bar, text=_("Copy from the other orientation"), command=self.copy_other).pack(side="left", padx=8)
        self.snap = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text=_("Grid"), variable=self.snap).pack(side="left")
        self.use_guides = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text=_("Guides"), variable=self.use_guides).pack(side="left", padx=(6, 0))
        self.canvas = tk.Canvas(f, highlightthickness=1, highlightbackground="#888", cursor="arrow")
        self.canvas.pack()
        tools = ttk.Frame(f)
        tools.pack(fill="x", pady=6)
        for text, cmd in (("Undo", self.do_undo), ("Duplicate", self.duplicate_widget), ("Delete", self.delete_widget),
                          ("Bring forward", lambda: self.restack(1)), ("Send backward", lambda: self.restack(-1)),
                          ("Show on screen", self.show_on_screen)):
            ttk.Button(tools, text=_(text), command=cmd).pack(side="left", padx=(0, 4))
        self.hint = ttk.Label(f, foreground="gray", text=_(
            "Drag a widget from the palette onto the screen. Shift+click: multiple selection. Ctrl+G: group."))
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
        c.bind("<Control-a>", lambda e: self.select(list(range(len(self.widgets)))))
        c.bind("<Control-g>", lambda e: self.group())
        c.bind("<Control-G>", lambda e: self.ungroup())  # Ctrl+Shift+G
        return f

    def set_orient(self, o):
        self.flush()
        self.orient = o
        self.open_page(self.page_id)

    def copy_other(self):
        other = "landscape" if self.orient == "portrait" else "portrait"
        src = self.layouts[self.page_id].data.get(other) or []
        if not src:
            messagebox.showinfo(_("Copy"), _("The other orientation is empty."))
            return
        if self.widgets and not messagebox.askyesno(_("Copy"), _("Replace this layout with the adapted one?")):
            return
        self.snapshot()
        self.widgets[:] = layout.scale_widgets(src, other, self.orient)
        self.select([])
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
            # starting point: the other orientation adapted (it becomes this one's at the first edit)
            data[self.orient] = layout.scale_widgets(data.get(other) or [], other, self.orient)
        self.widgets = data[self.orient]
        w, h = layout.SIZES[self.orient]
        self.canvas.configure(width=int(w * self.zoom), height=int(h * self.zoom))
        self.sel = []
        self.refresh_page_lists()
        self.refresh_layers()
        self.build_props()
        self.redraw()

    def show_on_screen(self):
        """Ask the running screen app to jump to this page."""
        if self.page_id:
            self.flush()
            paths.CONTROL.write_text(json.dumps({"show": self.page_id}), encoding="utf-8")

    # --- drawing --------------------------------------------------------
    def redraw_later(self):
        if not self._redraw_job:
            self._redraw_job = self.after(30, self.redraw)

    def redraw(self):
        self._redraw_job = None
        if not self.page_id or not self.canvas.winfo_exists():
            return
        size = layout.SIZES[self.orient]
        page = layout.LayoutPage(self.page_id, {self.orient: self.widgets})
        img = page.render(self.app.data, size, {}, self.app.history_view)
        if self.zoom != 1:
            img = img.resize((int(size[0] * self.zoom), int(size[1] * self.zoom)), Image.Resampling.BILINEAR)
        self._photo = ImageTk.PhotoImage(img)
        c, z = self.canvas, self.zoom
        c.delete("all")
        c.create_image(0, 0, image=self._photo, anchor="nw")
        for i in self.sel:
            x0, y0, x1, y1 = (v * z for v in self.box(self.widgets[i]))
            c.create_rectangle(x0, y0, x1, y1, outline=SELECT_COLOR, dash=(4, 2), width=2)
        if len(self.sel) == 1:
            x0, y0, x1, y1 = (v * z for v in self.box(self.widgets[self.sel[0]]))
            c.create_rectangle(x1 - HANDLE, y1 - HANDLE, x1, y1, fill=SELECT_COLOR, outline="")
        elif len(self.sel) > 1:
            x0, y0, x1, y1 = (v * z for v in bbox([self.widgets[i] for i in self.sel]))
            c.create_rectangle(x0 - 2, y0 - 2, x1 + 2, y1 + 2, outline=SELECT_COLOR, width=1)
        for axis, v in self.guides:
            if axis == "x":
                c.create_line(v * z, 0, v * z, size[1] * z, fill=GUIDE_COLOR, dash=(2, 2))
            else:
                c.create_line(0, v * z, size[0] * z, v * z, fill=GUIDE_COLOR, dash=(2, 2))

    @staticmethod
    def box(w):
        return w["x"], w["y"], w["x"] + w["w"], w["y"] + w["h"]

    # --- mouse ----------------------------------------------------------
    def to_screen(self, e):
        return e.x / self.zoom, e.y / self.zoom

    @staticmethod
    def inside(w, x, y):
        return w["x"] <= x <= w["x"] + w["w"] and w["y"] <= y <= w["y"] + w["h"]

    def hit(self, x, y):
        for i in reversed(self.sel):  # the selection wins: big widgets can be moved too
            if self.inside(self.widgets[i], x, y):
                return i
        for i in range(len(self.widgets) - 1, -1, -1):
            if self.inside(self.widgets[i], x, y):
                return i
        return None

    def group_of(self, i):
        g = self.widgets[i].get("group")
        return [j for j, w in enumerate(self.widgets) if g and w.get("group") == g] or [i]

    def on_press(self, e):
        self.canvas.focus_set()
        x, y = self.to_screen(e)
        if len(self.sel) == 1:
            w = self.widgets[self.sel[0]]
            tol = HANDLE / self.zoom + 2
            if abs(x - (w["x"] + w["w"])) <= tol and abs(y - (w["y"] + w["h"])) <= tol:
                self.drag = {"mode": "resize", "x": x, "y": y, "orig": copy.deepcopy(self.widgets), "moved": False}
                return
        i = self.hit(x, y)
        additive = bool(e.state & 0x0005)   # Shift or Ctrl
        single = bool(e.state & 0x20000)    # Alt: ignore groups
        if i is None:
            if not additive:
                self.select([])
            self.drag = None
            return
        targets = [i] if single else self.group_of(i)
        if additive:
            sel = [j for j in self.sel if j not in targets] if i in self.sel else self.sel + targets
            self.select(sel)
        elif i not in self.sel:
            self.select(targets)
        self.drag = {"mode": "move", "x": x, "y": y, "orig": copy.deepcopy(self.widgets), "moved": False}

    def snapv(self, v):
        return round(v / GRID) * GRID if self.snap.get() else round(v)

    def guide_delta(self, box, axis):
        """Offset that aligns the moving box's edges/centre with another widget or the screen; None if far."""
        lo, hi = (box[0], box[2]) if axis == "x" else (box[1], box[3])
        mine = [lo, (lo + hi) / 2, hi]
        size = layout.SIZES[self.orient][0 if axis == "x" else 1]
        lines = [0, size / 2, size]
        for j, w in enumerate(self.widgets):
            if j not in self.sel:
                a, b = (w["x"], w["x"] + w["w"]) if axis == "x" else (w["y"], w["y"] + w["h"])
                lines += [a, (a + b) / 2, b]
        best = None
        for m in mine:
            for line in lines:
                if abs(line - m) <= SNAP and (best is None or abs(line - m) < abs(best[0])):
                    best = (line - m, line)
        return best

    def on_motion(self, e):
        if not self.drag or not self.sel:
            return
        d = self.drag
        if not d["moved"]:
            self.undo.append((self.page_id, self.orient, json.dumps(d["orig"])))
            del self.undo[:-50]
            d["moved"] = True
        x, y = self.to_screen(e)
        dx, dy = x - d["x"], y - d["y"]
        orig = d["orig"]
        self.guides = []
        if d["mode"] == "resize":
            i = self.sel[0]
            self.widgets[i]["w"] = max(4, self.snapv(orig[i]["w"] + dx))
            self.widgets[i]["h"] = max(2, self.snapv(orig[i]["h"] + dy))
        else:
            ox0, oy0, ox1, oy1 = bbox([orig[i] for i in self.sel])
            nx, ny = self.snapv(ox0 + dx) - ox0, self.snapv(oy0 + dy) - oy0
            if self.use_guides.get():
                for axis in ("x", "y"):
                    raw = dx if axis == "x" else dy
                    box = (ox0 + raw, oy0, ox1 + raw, oy1) if axis == "x" else (ox0, oy0 + raw, ox1, oy1 + raw)
                    hit = self.guide_delta(box, axis)
                    if hit:  # a guide beats the grid on that axis
                        if axis == "x":
                            nx = round(raw + hit[0])
                        else:
                            ny = round(raw + hit[0])
                        self.guides.append((axis, hit[1]))
            sw, sh = layout.SIZES[self.orient]
            nx = max(-ox1 + 8, min(sw - 8 - ox0, nx))
            ny = max(-oy1 + 8, min(sh - 8 - oy0, ny))
            for i in self.sel:
                self.widgets[i]["x"] = orig[i]["x"] + nx
                self.widgets[i]["y"] = orig[i]["y"] + ny
        self.update_geometry_fields()
        self.redraw_later()

    def on_release(self, e):
        moved = self.drag and self.drag["moved"]
        self.drag = None
        self.guides = []
        if moved:
            self.changed()
        else:
            self.redraw()

    def nudge(self, dx, dy, step):
        if not self.sel:
            return
        self.snapshot()
        for i in self.sel:
            self.widgets[i]["x"] += dx * step
            self.widgets[i]["y"] += dy * step
        self.update_geometry_fields()
        self.changed()

    # --- palette (drag & drop) ------------------------------------------
    def build_side_column(self):
        f = ttk.Frame(self)
        ttk.Label(f, text=_("Palette (drag onto the screen)")).pack(anchor="w")
        pal = ttk.Frame(f)
        pal.pack(fill="x")
        self.palette = tk.Listbox(pal, height=10, exportselection=False, width=34)
        sb = ttk.Scrollbar(pal, orient="vertical", command=self.palette.yview)
        self.palette.configure(yscrollcommand=sb.set)
        self.palette.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")
        self.palette_ids = sorted(WIDGETS, key=lambda t: _(WIDGETS[t].label))
        for t in self.palette_ids:
            self.palette.insert("end", _(WIDGETS[t].label))
        self.palette.bind("<ButtonPress-1>", lambda e: setattr(self, "palette_type", self.palette_ids[self.palette.nearest(e.y)]))
        self.palette.bind("<B1-Motion>", lambda e: self.palette.configure(cursor="plus") if self.palette_type else None)
        self.palette.bind("<ButtonRelease-1>", self.palette_drop)
        self.palette.bind("<Double-Button-1>", lambda e: self.add_widget(self.palette_ids[self.palette.nearest(e.y)]))

        ttk.Label(f, text=_("Layers (top = front)")).pack(anchor="w", pady=(10, 0))
        self.layers = tk.Listbox(f, height=7, exportselection=False, width=34, selectmode="extended")
        self.layers.pack(fill="x")
        self.layers.bind("<<ListboxSelect>>", self.layer_pick)

        self.props = ttk.LabelFrame(f, text=_("Properties"), padding=6)
        self.props.pack(fill="both", expand=True, pady=(10, 0))
        return f

    def palette_drop(self, e):
        self.palette.configure(cursor="")
        t, self.palette_type = self.palette_type, None
        if not t:
            return
        px, py = self.winfo_pointerxy()
        if self.winfo_containing(px, py) is not self.canvas:
            return
        self.add_widget(t, (px - self.canvas.winfo_rootx()) / self.zoom, (py - self.canvas.winfo_rooty()) / self.zoom)

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
        self.select([len(self.widgets) - 1])
        self.changed()

    # --- layers ---------------------------------------------------------
    def describe(self, w):
        cls = WIDGETS.get(w["type"])
        extra = _(w.get("text") or "") or w.get("field") or w.get("char") or w.get("file") or ""
        extra = f" · {extra}" if extra else (f" #{w['index']}" if "index" in w else "")
        group = " [G]" if w.get("group") else ""
        return (_(cls.label) if cls else w["type"]) + group + extra[:28]

    def refresh_layers(self):
        self.layers.delete(0, "end")
        for w in reversed(self.widgets):
            self.layers.insert("end", self.describe(w))
        for i in self.sel:
            self.layers.selection_set(len(self.widgets) - 1 - i)

    def layer_pick(self, e):
        n = len(self.widgets)
        self.select(sorted(n - 1 - s for s in self.layers.curselection()), from_layers=True)

    def select(self, indices, from_layers=False):
        self.sel = [i for i in indices if 0 <= i < len(self.widgets)]
        if not from_layers:
            self.layers.selection_clear(0, "end")
            for i in self.sel:
                self.layers.selection_set(len(self.widgets) - 1 - i)
        self.build_props()
        self.redraw()

    def restack(self, step):
        if len(self.sel) != 1:
            return
        i, j = self.sel[0], self.sel[0] + step
        if 0 <= j < len(self.widgets):
            self.snapshot()
            self.widgets[i], self.widgets[j] = self.widgets[j], self.widgets[i]
            self.sel = [j]
            self.changed()

    def duplicate_widget(self):
        if not self.sel:
            return
        self.snapshot()
        groups = {}
        start = len(self.widgets)
        for i in self.sel:
            w = copy.deepcopy(self.widgets[i])
            w["x"] += GRID * 2
            w["y"] += GRID * 2
            if w.get("group"):  # the copy of a group is a new group
                w["group"] = groups.setdefault(w["group"], uuid.uuid4().hex[:8])
            self.widgets.append(w)
        self.select(list(range(start, len(self.widgets))))
        self.changed()

    def delete_widget(self):
        if not self.sel:
            return
        self.snapshot()
        for i in sorted(self.sel, reverse=True):
            self.widgets.pop(i)
        self.select([])
        self.changed()

    def group(self):
        if len(self.sel) > 1:
            self.snapshot()
            g = uuid.uuid4().hex[:8]
            for i in self.sel:
                self.widgets[i]["group"] = g
            self.changed()
            self.build_props()

    def ungroup(self):
        if self.sel:
            self.snapshot()
            for i in self.sel:
                self.widgets[i].pop("group", None)
            self.changed()
            self.build_props()

    def align(self, how):
        if len(self.sel) < 2:
            return
        self.snapshot()
        x0, y0, x1, y1 = bbox([self.widgets[i] for i in self.sel])
        for i in self.sel:
            w = self.widgets[i]
            if how == "left":
                w["x"] = x0
            elif how == "right":
                w["x"] = x1 - w["w"]
            elif how == "hcenter":
                w["x"] = round((x0 + x1 - w["w"]) / 2)
            elif how == "top":
                w["y"] = y0
            elif how == "bottom":
                w["y"] = y1 - w["h"]
            elif how == "vcenter":
                w["y"] = round((y0 + y1 - w["h"]) / 2)
        self.changed()

    # --- properties -----------------------------------------------------
    def build_props(self):
        for child in self.props.winfo_children():
            child.destroy()
        self.geo_vars = {}
        if not self.sel:
            ttk.Label(self.props, text=_("Select a widget on the screen."), foreground="gray").grid()
            return
        if len(self.sel) > 1:
            self.props.configure(text=_("Properties"))
            ttk.Label(self.props, text=f"{len(self.sel)} {_('widgets selected')}").grid(row=0, column=0, columnspan=3, sticky="w")
            for r, row in enumerate(((("Align left", "left"), ("Centre", "hcenter"), ("Align right", "right")),
                                     (("Align top", "top"), ("Middle", "vcenter"), ("Align bottom", "bottom"))), start=1):
                for c, (text, how) in enumerate(row):
                    ttk.Button(self.props, text=_(text), command=lambda h=how: self.align(h)).grid(row=r, column=c, sticky="we", pady=2)
            ttk.Button(self.props, text=_("Group (Ctrl+G)"), command=self.group).grid(row=3, column=0, sticky="we", pady=(8, 0))
            ttk.Button(self.props, text=_("Ungroup"), command=self.ungroup).grid(row=3, column=1, sticky="we", pady=(8, 0))
            return
        w = self.widgets[self.sel[0]]
        cls = WIDGETS.get(w["type"])
        self.props.configure(text=f"{_('Properties')}: {_(cls.label) if cls else w['type']}")
        geo = ttk.Frame(self.props)
        geo.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        for i, k in enumerate(("x", "y", "w", "h")):
            ttk.Label(geo, text=k).grid(row=0, column=i * 2, padx=(0 if i == 0 else 6, 2))
            v = tk.StringVar(value=str(w[k]))
            ttk.Spinbox(geo, from_=-500, to=1000, textvariable=v, width=5).grid(row=0, column=i * 2 + 1)
            v.trace_add("write", lambda *a, k=k, v=v: self.set_geo(k, v))
            self.geo_vars[k] = v
        if w.get("group"):
            ttk.Button(geo, text=_("Ungroup"), command=self.ungroup).grid(row=0, column=9, padx=(10, 0))
        fields = sorted(set(field_paths(layout.with_clock(self.app.data))))
        for r, (key, kind, default, label) in enumerate(cls.props if cls else [], start=1):
            ttk.Label(self.props, text=_(label)).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 6))
            value = w.get(key, default)
            if kind == "bool":
                var = tk.BooleanVar(value=bool(value))
                ttk.Checkbutton(self.props, variable=var, command=lambda k=key, v=var: self.set_prop(k, v.get())).grid(
                    row=r, column=1, sticky="w")
            elif kind in ("int", "float"):
                var = tk.StringVar(value=str(value))
                ttk.Spinbox(self.props, from_=0, to=2000 if kind == "int" else 1, increment=1 if kind == "int" else 0.05,
                            textvariable=var, width=8).grid(row=r, column=1, sticky="w")
                var.trace_add("write", lambda *a, k=key, v=var, t=kind: self.set_number(k, v, t))
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
                ttk.Button(self.props, text=value or _("Choose…"), command=lambda k=key: self.pick_file(k)).grid(
                    row=r, column=1, sticky="w")
            else:  # text / field
                cb = ttk.Combobox(self.props, values=fields if kind == "field" else [], width=30)
                cb.set(value)
                cb.grid(row=r, column=1, columnspan=2, sticky="we")
                commit = lambda e, k=key, c=cb: self.set_prop(k, c.get())
                for ev in ("<Return>", "<FocusOut>", "<<ComboboxSelected>>"):
                    cb.bind(ev, commit)
                if kind == "text" and key == "text":
                    ins = ttk.Combobox(self.props, values=fields, width=16)
                    ins.set(_("+ field"))
                    ins.grid(row=r, column=3, sticky="w", padx=(4, 0))
                    ins.bind("<<ComboboxSelected>>", lambda e, c=cb, i=ins: (
                        c.insert("insert", "{" + i.get() + "}"), i.set(_("+ field")), self.set_prop("text", c.get())))
        ttk.Label(self.props, foreground="gray", wraplength=340, justify="left", text=_(
            "Formats: {field:.0f} {field:mmss} {field:human} {field:bytes} {field:gb} {field:hm} {field:weather} "
            "{field:weekday} {field:reset} {now:%H:%M}. Colours: level = green/yellow/red, sign = green if positive.")).grid(
            row=99, column=0, columnspan=4, sticky="w", pady=(8, 0))

    def update_geometry_fields(self):
        if len(self.sel) != 1 or not self.geo_vars:
            return
        w = self.widgets[self.sel[0]]
        self._updating = True
        for k, v in self.geo_vars.items():
            if v.get() != str(w[k]):
                v.set(str(w[k]))
        self._updating = False

    def set_geo(self, k, var):
        if self._updating or len(self.sel) != 1:
            return
        try:
            value = int(var.get())
        except ValueError:
            return
        w = self.widgets[self.sel[0]]
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
        if len(self.sel) != 1:
            return
        w = self.widgets[self.sel[0]]
        if w.get(k) != value:
            self.snapshot()
            w[k] = value
            self.changed()

    def pick_color(self, k, cb):
        _rgb, hexcolor = colorchooser.askcolor(cb.get() if cb.get().startswith("#") else None, parent=self)
        if hexcolor:
            cb.set(hexcolor)
            self.set_prop(k, hexcolor)

    def pick_file(self, k):
        path = filedialog.askopenfilename(parent=self, filetypes=[(_("Images"), "*.png *.jpg *.jpeg *.bmp *.webp *.gif *.apng")])
        if not path:
            return
        paths.ASSETS.mkdir(parents=True, exist_ok=True)
        name = Path(path).name
        if not (paths.ASSETS / name).exists():
            shutil.copy(path, paths.ASSETS / name)
        self.set_prop(k, name)
        self.build_props()

    # --- undo and saving ------------------------------------------------
    def snapshot(self):
        self.undo.append((self.page_id, self.orient, json.dumps(self.widgets)))
        del self.undo[:-50]

    def do_undo(self):
        while self.undo:
            pid, orient, state = self.undo.pop()
            if (pid, orient) == (self.page_id, self.orient):
                self.widgets[:] = json.loads(state)
                self.select([])
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
        """Save pending changes right away (before switching page or orientation)."""
        self.app.run_now("layout")
