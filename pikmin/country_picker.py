"""Searchable country checklist; saved settings retain stable ISO codes."""
import tkinter as tk
from tkinter import ttk, messagebox
from .countries import COUNTRIES
from .geoapify import country_codes


class CountryPicker(ttk.Frame):
    def __init__(self, parent, variable):
        super().__init__(parent)
        self.variable = variable
        self.summary = tk.StringVar()
        ttk.Button(self, text='勾選國家…', command=self.open).pack(side='left')
        ttk.Label(self, textvariable=self.summary, wraplength=450).pack(side='left', padx=8)
        variable.trace_add('write', lambda *_: self.refresh())
        self.refresh()

    def selected(self):
        try:
            return set(country_codes(self.variable.get()))
        except ValueError:
            return set()

    def refresh(self):
        selected = self.selected()
        names = [zh for code, zh, _ in COUNTRIES if code in selected]
        self.summary.set('、'.join(names[:4])+ (f' 等 {len(names)} 個國家' if len(names)>4 else '') if names else '尚未選擇國家')

    def open(self):
        window = tk.Toplevel(self)
        window.title('勾選搜尋國家／地區')
        window.geometry('690x570')
        window.transient(self.winfo_toplevel())
        window.grab_set()
        window.bind('<Escape>', lambda _: window.destroy())
        search = tk.StringVar()
        top = ttk.Frame(window, padding=10)
        top.pack(fill='x')
        ttk.Label(top, text='搜尋中文、英文或代碼').pack(side='left')
        entry = ttk.Entry(top, textvariable=search)
        entry.pack(side='left', fill='x', expand=True, padx=8)
        count = tk.StringVar()
        ttk.Label(window, textvariable=count).pack(anchor='w', padx=10)
        area = ttk.Frame(window)
        area.pack(fill='both', expand=True)
        canvas = tk.Canvas(area, highlightthickness=0)
        scrollbar = ttk.Scrollbar(area, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True)
        body = ttk.Frame(canvas, padding=10)
        canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        variables = {c: tk.BooleanVar(value=c in self.selected()) for c, _, _ in COUNTRIES}
        def update_count():
            count.set(f'已勾選 {sum(v.get() for v in variables.values())} 個國家／地區')
        rows = []
        for code, zh, en in COUNTRIES:
            button = ttk.Checkbutton(body, text=f'{zh} · {en} ({code.upper()})', variable=variables[code], command=update_count)
            rows.append((code, (code+' '+zh+' '+en).casefold(), button))
            button.bind('<MouseWheel>', lambda e: canvas.yview_scroll(-int(e.delta/120), 'units'))
        def filter_rows(*_):
            query = search.get().strip().casefold()
            for _, text, button in rows:
                button.pack_forget()
                if query in text:
                    button.pack(anchor='w', pady=2)
            canvas.yview_moveto(0)
        search.trace_add('write', filter_rows)
        canvas.bind('<MouseWheel>', lambda e: canvas.yview_scroll(-int(e.delta/120), 'units'))
        def select_visible(enabled):
            query = search.get().strip().casefold()
            for code, text, _ in rows:
                if query in text:
                    variables[code].set(enabled)
            update_count()
        def apply():
            selected = [c for c, _, _ in COUNTRIES if variables[c].get()]
            if not selected:
                messagebox.showerror('請選擇國家', '至少勾選一個國家。', parent=window)
                return
            self.variable.set(','.join(selected))
            window.destroy()
        bar = ttk.Frame(window, padding=10)
        bar.pack(fill='x')
        ttk.Button(bar, text='勾選搜尋結果', command=lambda: select_visible(True)).pack(side='left')
        ttk.Button(bar, text='取消搜尋結果', command=lambda: select_visible(False)).pack(side='left', padx=6)
        ttk.Button(bar, text='套用', command=apply).pack(side='right')
        ttk.Button(bar, text='取消', command=window.destroy).pack(side='right', padx=6)
        filter_rows()
        update_count()
        entry.focus_set()
