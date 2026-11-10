"""Window to choose the Markets symbols: catalog with search and categories, chosen list in order, custom symbols."""
import tkinter as tk
from tkinter import ttk

from i18n import _
from stock_catalog import CATALOG, NAMES


class StockPicker(tk.Toplevel):
    def __init__(self, master, selected, on_done):
        super().__init__(master)
        self.title(_("Choose stocks"))
        self.transient(master)
        self.chosen = list(selected)
        self.on_done = on_done
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, padding=10)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(1, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text=_("Search")).grid(row=0, column=0, sticky="w")
        self.query = tk.StringVar()
        search = ttk.Entry(left, textvariable=self.query, width=28)
        search.grid(row=0, column=1, sticky="we", padx=6)
        self.groups = ["All"] + list(CATALOG)
        self.group = ttk.Combobox(left, values=[_(g) for g in self.groups], state="readonly", width=22)
        self.group.current(0)
        self.group.grid(row=0, column=2, sticky="e")
        self.tree = ttk.Treeview(left, columns=("on", "symbol", "name", "group"), show="headings", height=18)
        for col, text, width in (("on", "", 30), ("symbol", "Symbol", 110), ("name", "Name", 260), ("group", "Category", 150)):
            self.tree.heading(col, text=_(text) if text else "")
            self.tree.column(col, width=width, anchor="center" if col == "on" else "w", stretch=col == "name")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=8)
        sb.grid(row=1, column=3, sticky="ns", pady=8)
        row = ttk.Frame(left)
        row.grid(row=2, column=0, columnspan=3, sticky="we")
        ttk.Button(row, text=_("Add →"), command=self.add_selected).pack(side="left")
        ttk.Label(row, text=_("Other Yahoo symbol:")).pack(side="left", padx=(16, 4))
        self.custom = ttk.Entry(row, width=14)
        self.custom.pack(side="left")
        ttk.Button(row, text=_("Add"), command=self.add_custom).pack(side="left", padx=4)
        self.custom.bind("<Return>", lambda e: self.add_custom())

        right = ttk.Frame(self, padding=10)
        right.grid(row=0, column=1, sticky="ns")
        self.count = ttk.Label(right)
        self.count.pack(anchor="w")
        self.list = tk.Listbox(right, height=20, width=34, exportselection=False)
        self.list.pack(fill="y", expand=True, pady=6)
        btns = ttk.Frame(right)
        btns.pack(fill="x")
        for text, cmd in (("▲", lambda: self.move(-1)), ("▼", lambda: self.move(1)), (_("Remove"), self.remove)):
            ttk.Button(btns, text=text, width=3 if len(text) == 1 else 10, command=cmd).pack(side="left", padx=(0, 4))
        ttk.Label(right, foreground="gray", wraplength=240, justify="left",
                  text=_("With more than 5 stocks the page becomes a grid of cards.")).pack(anchor="w", pady=8)
        end = ttk.Frame(right)
        end.pack(fill="x", side="bottom")
        ttk.Button(end, text=_("Cancel"), command=self.destroy).pack(side="right")
        ttk.Button(end, text="OK", command=self.done).pack(side="right", padx=6)

        self.query.trace_add("write", lambda *a: self.refresh())
        self.group.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self.tree.bind("<Double-1>", lambda e: self.add_selected())
        self.list.bind("<Delete>", lambda e: self.remove())
        self.refresh()
        self.refresh_list()
        search.focus_set()
        self.grab_set()

    def refresh(self):
        q = self.query.get().strip().lower()
        group = self.groups[self.group.current()]
        self.tree.delete(*self.tree.get_children())
        for g, items in CATALOG.items():
            if group not in ("All", g):
                continue
            for symbol, name in items:
                if q in symbol.lower() or q in name.lower():
                    self.tree.insert("", "end", iid=symbol, values=("✓" if symbol in self.chosen else "", symbol, name, _(g)))

    def refresh_list(self, select=None):
        self.list.delete(0, "end")
        for s in self.chosen:
            self.list.insert("end", f"{s}  ·  {NAMES.get(s, '')}".rstrip(" ·"))
        if select is not None and 0 <= select < len(self.chosen):
            self.list.selection_set(select)
            self.list.see(select)
        self.count.configure(text=f"{_('Chosen')}: {len(self.chosen)}")

    def add(self, symbol):
        if symbol and symbol not in self.chosen:
            self.chosen.append(symbol)
            if self.tree.exists(symbol):
                self.tree.set(symbol, "on", "✓")
            self.refresh_list(len(self.chosen) - 1)

    def add_selected(self):
        for symbol in self.tree.selection():
            self.add(symbol)

    def add_custom(self):
        self.add(self.custom.get().strip().upper())
        self.custom.delete(0, "end")

    def move(self, step):
        sel = self.list.curselection()
        if sel and 0 <= sel[0] + step < len(self.chosen):
            i = sel[0]
            self.chosen[i], self.chosen[i + step] = self.chosen[i + step], self.chosen[i]
            self.refresh_list(i + step)

    def remove(self):
        for i in sorted(self.list.curselection(), reverse=True):
            symbol = self.chosen.pop(i)
            if self.tree.exists(symbol):
                self.tree.set(symbol, "on", "")
        self.refresh_list()

    def done(self):
        self.on_done(list(self.chosen))
        self.destroy()
