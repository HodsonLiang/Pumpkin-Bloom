"""Stable gallery sorting, stars, and independent search/display type selection."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from .scan_engine import BASE


class ScanCatalog:
    def init_catalog(self):
        self.target_types = sorted(p.stem for p in (BASE/'mushroom_pics').glob('*.png'))
        self.search_types = set(self.target_types)
        self.search_summary = tk.StringVar(value='搜尋：'+ '、'.join(self.target_types))
        self.display_types = None
        self.sort_column, self.sort_reverse = 'index', False
        self.heading_titles = dict(bookmark='書籤', index='座標序號', target='目標', coords='緯度, 經度', time='截圖時間')

    def type_dialog(self, search=True):
        window = tk.Toplevel(self.root)
        window.title('搜尋目標種類' if search else '顯示目標篩選')
        window.geometry('+%d+%d' % (self.root.winfo_rootx()+70, self.root.winfo_rooty()+70))
        window.transient(self.root)
        window.grab_set()
        window.bind('<Escape>', lambda _: window.destroy())
        if search:
            ttk.Label(window, text='套用後從下一張尚未開始辨識的圖片生效；歷史結果不會移除。', wraplength=520).pack(padx=10, pady=8)
        names = self.target_types if search else sorted(set(self.target_types) | {Path(r['target']).stem for r in self.records})
        chosen = self.search_types if search else self.display_types
        variables = {}
        canvas = tk.Canvas(window, width=540, height=min(400, max(80, len(names)*50)))
        scroll = ttk.Scrollbar(window, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True)
        body = ttk.Frame(canvas, padding=12)
        canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        for row, name in enumerate(names):
            variable = variables[name] = tk.BooleanVar(value=chosen is None or name in chosen)
            ttk.Checkbutton(body, text=name, image=self.icon_for(name), compound='left', variable=variable).grid(row=row, column=0, sticky='w', pady=3)
        bar = ttk.Frame(window, padding=8)
        bar.pack(fill='x')
        ttk.Button(bar, text='全選', command=lambda: [v.set(True) for v in variables.values()]).pack(side='left')
        ttk.Button(bar, text='全不選', command=lambda: [v.set(False) for v in variables.values()]).pack(side='left')
        def apply():
            selected = {n for n, v in variables.items() if v.get()}
            if search:
                if not selected:
                    messagebox.showerror('請選擇目標', '至少選一種搜尋目標。', parent=window)
                    return
                self.apply_search_types(selected)
            else:
                self.display_types = None if selected == set(names) else selected
                self.refresh_catalog()
            window.destroy()
        ttk.Button(bar, text='套用', command=apply).pack(side='right')

    def apply_search_types(self, selected):
        if not selected or not set(selected) <= set(self.target_types):
            raise ValueError('請選擇至少一種存在的目標範本。')
        self.search_types = set(selected)
        self.search_summary.set('搜尋：'+'、'.join(sorted(selected)))
        if self.active and self.scanner:
            self.scanner.set_target_names(selected)
        self.append_log('搜尋種類已套用：'+'、'.join(sorted(selected)))

    def sort_targets(self, column):
        self.sort_reverse = not self.sort_reverse if self.sort_column == column else False
        self.sort_column = column
        self.refresh_catalog()

    def refresh_catalog(self):
        selected = self.table.selection()
        visible = []
        for index, record in enumerate(self.records):
            show = self.display_types is None or Path(record['target']).stem in self.display_types
            item = str(index)
            marker = self.markers[index]
            if show:
                visible.append(index)
                if marker is None:
                    self.markers[index] = self.make_target_marker(index, record)
            else:
                self.table.detach(item)
                if marker:
                    marker.delete()
                    self.markers[index] = None
        def key(index):
            record = self.records[index]
            return {'bookmark': self.bookmark_key(record) in self.bookmarks,
                    'index': int(record['index']), 'target': record['target'].casefold(),
                    'coords': (record['lat'], record['lon']), 'time': record['timestamp']}[self.sort_column]
        for index in sorted(visible, key=key, reverse=self.sort_reverse):
            self.table.move(str(index), '', 'end')
        visible_set = set(visible)
        retained = tuple(item for item in selected if int(item) in visible_set)
        if retained != selected:
            self.table.selection_set(retained)
        for column, label in self.heading_titles.items():
            # Keep the two-character bookmark heading within its fixed width.
            self.table.heading(column, text=label+(' ▼' if self.sort_reverse else ' ▲') if column == self.sort_column and column != 'bookmark' else label)

    def make_target_marker(self, index, record):
        star = '★ ' if self.bookmark_key(record) in self.bookmarks else ''
        return self.map_widget.set_marker(max(-85, min(85, record['lat'])), record['lon'],
            text=star+f"#{record['index']} · {record['target']}", icon=self.icon_for(record['target']),
            icon_anchor='s', marker_color_outside='#338251', command=lambda _, i=index: self.marker_select(i))

    def toggle_bookmarks(self):
        selected = self.table.selection()
        if selected:
            self.set_bookmarks(not all(self.bookmark_key(self.records[int(i)]) in self.bookmarks for i in selected))

    def star_click(self, event):
        if self.table.identify_region(event.x, event.y) == 'cell' and self.table.identify_column(event.x) == '#1':
            item = self.table.identify_row(event.y)
            if item:
                self.table.selection_set(item)
                self.toggle_bookmarks()
                return 'break'
