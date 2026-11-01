"""Project coordinate library selector, with explicit legacy import."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .storage import WAYPOINTS, waypoint_files, import_waypoints


class WaypointPicker(ttk.Frame):
    def __init__(self, parent, variable):
        super().__init__(parent)
        self.variable = variable
        self.name = tk.StringVar()
        self.combo = ttk.Combobox(self, textvariable=self.name, state='readonly', width=35)
        self.combo.pack(side='left', fill='x', expand=True)
        self.combo.bind('<<ComboboxSelected>>', lambda _: variable.set(str(WAYPOINTS/self.name.get())))
        self.refresh_button = ttk.Button(self, text='↻', width=3, command=self.refresh)
        self.refresh_button.pack(side='left')
        self.import_button = ttk.Button(self, text='匯入…', command=self.import_file)
        self.import_button.pack(side='left')
        old = Path(variable.get())
        if old.is_file() and old.parent.resolve() != WAYPOINTS.resolve():
            try:
                variable.set(str(import_waypoints(old)))
            except (OSError, ValueError):
                pass
        variable.trace_add('write', lambda *_: self.refresh())
        self.refresh()

    def refresh(self):
        files = waypoint_files()
        self.combo.configure(values=[p.name for p in files])
        current = Path(self.variable.get())
        self.name.set(current.name if current in files else '')
        if not self.name.get() and files:
            self.name.set(files[0].name)
            self.variable.set(str(files[0]))

    def set_enabled(self, enabled):
        self.combo.configure(state='readonly' if enabled else 'disabled')
        for button in (self.refresh_button, self.import_button):
            button.configure(state='normal' if enabled else 'disabled')

    def import_file(self):
        path = filedialog.askopenfilename(initialdir=WAYPOINTS, filetypes=[('搜尋座標', '*.pikscan *.txt')])
        if path:
            try:
                self.variable.set(str(import_waypoints(path)))
            except (ValueError, OSError) as exc:
                messagebox.showerror('匯入失敗', str(exc))
