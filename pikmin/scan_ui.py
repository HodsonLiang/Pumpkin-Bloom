"""Live scanning map and screenshot gallery."""
import csv
import io
import json
import os
from pathlib import Path
import queue
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from PIL import Image, ImageTk, ImageOps
import tkintermapview
from .scan_engine import BASE, DEFAULTS, Scanner, prepare_config


class Preview(ttk.Frame):
    def __init__(self, parent, title):
        super().__init__(parent, padding=8)
        self.original = self.photo = None
        self.title = tk.StringVar(value=title)
        ttk.Label(self, textvariable=self.title, wraplength=270).pack(fill='x')
        self.canvas = tk.Canvas(self, background='#182820', highlightthickness=0, width=220, height=260)
        self.canvas.pack(fill='both', expand=True, pady=5)
        self.canvas.bind('<Configure>', lambda _: self.draw())

    def load(self, source):
        with Image.open(io.BytesIO(source) if isinstance(source, bytes) else source) as picture:
            self.original = ImageOps.exif_transpose(picture).convert('RGB')
        self.draw()

    def draw(self):
        self.canvas.delete('all')
        if self.original is None:
            self.canvas.create_text(max(1, self.canvas.winfo_width())/2, max(1, self.canvas.winfo_height())/2,
                                    text='等待截圖', fill='#acbfb3')
            return
        picture = self.original.copy()
        picture.thumbnail((max(1, self.canvas.winfo_width()-12), max(1, self.canvas.winfo_height()-12)), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(picture)
        self.canvas.create_image(self.canvas.winfo_width()/2, self.canvas.winfo_height()/2, image=self.photo)


class ScanApp:
    def __init__(self, root, config=None):
        self.root = root
        self.events = queue.Queue()
        self.scanner = None
        self.closing = False
        self.records = []
        self.markers = []
        self.current_marker = self.sent_marker = None
        self.current_point = None
        self.current_path = None
        self.session_folder = None
        self.completed = self.total = self.hits = self.errors = 0
        self.captured = self.processed = 0
        self.sent_point = None
        self.started = None
        self.elapsed = 0.
        self.active = False
        self.next_index = None
        root.title('Pikmin · 目標搜尋')
        root.geometry('1380x900')
        root.minsize(1100, 760)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Microsoft JhengHei UI', 10))
        style.configure('TButton', padding=(9, 6))
        style.configure('Title.TLabel', font=('Microsoft JhengHei UI', 22, 'bold'), foreground='#245a3d')
        outer = ttk.Frame(root, padding=14)
        outer.pack(fill='both', expand=True)
        head = ttk.Frame(outer)
        head.pack(fill='x')
        ttk.Label(head, text='目標搜尋', style='Title.TLabel').pack(side='left')
        self.status = tk.StringVar(value='待命 · 選擇座標檔後開始搜尋；需先建立 iPhone 連線')
        ttk.Label(head, textvariable=self.status, wraplength=1000).pack(side='left', padx=20)
        settings = ttk.LabelFrame(outer, text='搜尋設定', padding=8)
        settings.pack(fill='x', pady=8)
        values = {**DEFAULTS, **(config or {})}
        self.fields = {key: tk.StringVar(value=values[key]) for key in DEFAULTS}
        self.setting_widgets = []
        ttk.Label(settings, text='座標檔').grid(row=0, column=0, sticky='w')
        entry = ttk.Entry(settings, textvariable=self.fields['waypoints'], width=58)
        entry.grid(row=0, column=1, columnspan=5, sticky='ew', padx=6)
        self.setting_widgets.append(entry)
        button = ttk.Button(settings, text='瀏覽…', command=self.browse)
        button.grid(row=0, column=6)
        self.setting_widgets.append(button)
        self.timing = tk.StringVar(value='逐點等待後截圖' if values['timing']=='sequential' else '提前傳送（原流程）')
        combo = ttk.Combobox(settings, textvariable=self.timing, values=['提前傳送（原流程）', '逐點等待後截圖'], width=23, state='readonly')
        combo.grid(row=0, column=7, columnspan=5, padx=8, sticky='w')
        self.setting_widgets.append(combo)
        labels = [('起始點', 'start_index'), ('最多點數', 'max_points'), ('首次等待 秒', 'initial_wait'),
                  ('截圖等待 秒', 'screenshot_wait'), ('最短週期 秒', 'interval'), ('差異門檻', 'threshold')]
        for col, (label, key) in enumerate(labels):
            ttk.Label(settings, text=label).grid(row=1, column=col*2, pady=(8, 0), sticky='w')
            entry = ttk.Entry(settings, textvariable=self.fields[key], width=7)
            entry.grid(row=1, column=col*2+1, padx=(4, 12), pady=(8, 0))
            self.setting_widgets.append(entry)
        controls = ttk.Frame(outer)
        controls.pack(fill='x')
        self.start_button = ttk.Button(controls, text='▶ 開始搜尋', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(controls, text='■ 停止並還原定位', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=6)
        self.resume_button = ttk.Button(controls, text='從中斷點繼續', command=self.resume, state='disabled')
        self.resume_button.pack(side='left')
        self.follow = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text='跟隨搜尋位置', variable=self.follow).pack(side='left', padx=12)
        ttk.Button(controls, text='回到搜尋位置', command=self.center).pack(side='left')
        ttk.Button(controls, text='結果資料夾', command=self.open_folder).pack(side='right')
        self.stats = tk.StringVar(value='已掃描 0 / 0　命中 0　錯誤 0')
        ttk.Label(outer, textvariable=self.stats, font=('Microsoft JhengHei UI', 12, 'bold')).pack(anchor='w', pady=(8, 4))
        self.progress = ttk.Progressbar(outer)
        self.progress.pack(fill='x', pady=(0, 8))
        body = ttk.Panedwindow(outer, orient='vertical')
        body.pack(fill='both', expand=True)
        top = ttk.Frame(body)
        body.add(top, weight=3)
        top.columnconfigure(0, weight=3)
        top.columnconfigure(1, weight=1)
        top.columnconfigure(2, weight=1)
        top.rowconfigure(0, weight=1)
        map_frame = ttk.Frame(top)
        map_frame.grid(row=0, column=0, sticky='nsew')
        self.map_widget = tkintermapview.TkinterMapView(map_frame, width=500, height=310, corner_radius=8)
        self.map_widget.pack(fill='both', expand=True)
        self.map_widget.set_position(25.033964, 121.564468)
        self.map_widget.set_zoom(8)
        ttk.Label(map_frame, text='藍：搜尋點　橘：最後送出定位　綠：命中（可點選）', wraplength=600).pack(anchor='w', pady=4)
        self.current_preview = Preview(top, '目前截圖 · 等待搜尋')
        self.current_preview.grid(row=0, column=1, sticky='nsew')
        self.hit_preview = Preview(top, '命中截圖 · 點選下方結果')
        self.hit_preview.grid(row=0, column=2, sticky='nsew')
        self.current_preview.canvas.bind('<Double-Button-1>', lambda _: self.open_image(self.current_path))
        self.hit_preview.canvas.bind('<Double-Button-1>', lambda _: self.open_selected())
        bottom = ttk.Notebook(body)
        body.add(bottom, weight=1)
        gallery = ttk.Frame(bottom, padding=6)
        logs = ttk.Frame(bottom)
        bottom.add(gallery, text='  本次命中結果  ')
        bottom.add(logs, text='  執行紀錄  ')
        bar = ttk.Frame(gallery)
        bar.pack(fill='x', pady=(0, 4))
        ttk.Button(bar, text='開啟原始截圖', command=self.open_selected).pack(side='left')
        ttk.Button(bar, text='複製選取座標', command=self.copy_coords).pack(side='left', padx=6)
        ttk.Button(bar, text='匯出命中 CSV', command=self.export).pack(side='left')
        ttk.Label(bar, text='雙擊圖片可開原圖；新搜尋會清空畫面，已儲存結果會保留。').pack(side='left', padx=10)
        table_frame = ttk.Frame(gallery)
        table_frame.pack(fill='both', expand=True)
        columns = ('index', 'target', 'coords', 'time')
        self.table = ttk.Treeview(table_frame, columns=columns, show='headings', height=5, selectmode='browse')
        for key, title, width in zip(columns, ['座標序號', '目標', '緯度, 經度', '截圖時間'], [90, 200, 260, 200]):
            self.table.heading(key, text=title)
            self.table.column(key, width=width)
        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.table.pack(fill='both', expand=True)
        self.table.bind('<<TreeviewSelect>>', self.select_hit)
        self.log = ScrolledText(logs, height=6, state='disabled', font=('Consolas', 10))
        self.log.pack(fill='both', expand=True)
        ttk.Label(outer, text='目前截圖是最近一次擷取，並非即時串流。提前傳送模式沿用原本延遲假設，標記為搜尋指定座標，並非手機 GPS 回讀。', wraplength=1320).pack(anchor='w', pady=(6, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def browse(self):
        path = filedialog.askopenfilename(initialdir=BASE, filetypes=[('座標文字檔', '*.txt')])
        if path:
            self.fields['waypoints'].set(path)

    def set_busy(self, busy):
        self.active = busy
        self.start_button.configure(state='disabled' if busy else 'normal')
        self.stop_button.configure(state='normal' if busy else 'disabled')
        self.resume_button.configure(state='disabled')
        for widget in self.setting_widgets:
            widget.configure(state='disabled' if busy else ('readonly' if isinstance(widget, ttk.Combobox) else 'normal'))

    def start(self):
        if self.active or self.closing:
            return
        try:
            values = {key: var.get() for key, var in self.fields.items()}
            values['timing'] = 'pipeline' if self.timing.get().startswith('提前') else 'sequential'
            config, points = prepare_config(values)
            if not list((BASE/'mushroom_pics').glob('*.png')):
                raise ValueError('mushroom_pics 資料夾沒有 PNG 範本。')
        except (OSError, ValueError) as exc:
            messagebox.showerror('請檢查設定', str(exc))
            return
        self.last_config = config
        self.end_index = config['start_index']+len(points)
        self.records.clear()
        for marker in self.markers:
            marker.delete()
        self.markers.clear()
        for marker in (self.current_marker, self.sent_marker):
            if marker:
                marker.delete()
        self.current_marker = self.sent_marker = None
        self.current_point = self.current_path = None
        self.table.delete(*self.table.get_children())
        for preview, title in ((self.current_preview, '目前截圖 · 等待搜尋'), (self.hit_preview, '命中截圖 · 點選下方結果')):
            preview.original = None
            preview.title.set(title)
            preview.draw()
        self.completed = self.hits = self.errors = 0
        self.captured = self.processed = 0
        self.sent_point = None
        self.total = len(points)
        self.next_index = config['start_index']
        self.started = time.monotonic()
        self.elapsed = 0.
        self.set_busy(True)
        self.scanner = Scanner(config, points, self.events)
        self.scanner.start()
        self.status.set('正在啟動搜尋…')

    def stop(self):
        if self.active:
            self.scanner.stop_event.set()
            self.stop_button.configure(state='disabled')
            self.status.set('正在停止 · 等待目前指令結束並儲存辨識結果')

    def resume(self):
        if self.next_index is not None:
            for key, value in self.last_config.items():
                if key in self.fields:
                    self.fields[key].set(value)
            self.fields['start_index'].set(self.next_index)
            self.fields['max_points'].set(self.end_index-self.next_index)
            self.timing.set('提前傳送（原流程）' if self.last_config['timing']=='pipeline' else '逐點等待後截圖')
            self.start()

    def center(self):
        if self.current_point:
            self.map_widget.set_position(max(-85, min(85, self.current_point[0])), self.current_point[1])

    def open_folder(self):
        folder = BASE/'found_targets'
        folder.mkdir(exist_ok=True)
        os.startfile(folder)

    def open_image(self, path):
        if path:
            try:
                os.startfile(str(path))
            except OSError as exc:
                messagebox.showerror('無法開啟圖片', str(exc))

    def selected(self):
        selection = self.table.selection()
        return self.records[int(selection[0])] if selection else None

    def open_selected(self):
        record = self.selected()
        if record:
            self.open_image(record['path'])

    def copy_coords(self):
        record = self.selected()
        if record:
            self.root.clipboard_clear()
            self.root.clipboard_append(f"{record['lat']:.7f},{record['lon']:.7f}")

    def select_hit(self, _event=None):
        record = self.selected()
        if not record:
            return
        try:
            self.hit_preview.load(record['path'])
            self.hit_preview.title.set(f"{record['target']} · 第 {record['index']} 點\n{record['lat']:.6f}, {record['lon']:.6f}")
            self.map_widget.set_position(max(-85, min(85, record['lat'])), record['lon'])
        except (OSError, ValueError) as exc:
            self.append_log(f'圖片無法讀取：{exc}')

    def marker_select(self, index):
        self.table.selection_set(str(index))
        self.table.see(str(index))
        self.select_hit()

    def export(self):
        if not self.records:
            messagebox.showinfo('沒有結果', '本次尚未找到目標。')
            return
        path = filedialog.asksaveasfilename(defaultextension='.csv', initialfile='scan_hits.csv')
        if path:
            try:
                fields = ['index', 'target', 'lat', 'lon', 'timestamp', 'path', 'timing', 'session']
                with open(path, 'w', newline='', encoding='utf-8-sig') as output:
                    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
                    writer.writeheader()
                    for row in self.records:
                        safe = {k: ("'"+v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v) for k, v in row.items()}
                        writer.writerow(safe)
            except OSError as exc:
                messagebox.showerror('匯出失敗', str(exc))

    def append_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text+'\n')
        if int(self.log.index('end-1c').split('.')[0]) > 1500:
            self.log.delete('1.0', '301.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def handle(self, event):
        kind = event['kind']
        if kind == 'session':
            self.session_folder = event['folder']
            self.append_log(f"本次紀錄：{self.session_folder}")
        elif kind == 'status':
            self.status.set(event['text'])
        elif kind in ('search', 'position'):
            point = event['point']
            if kind == 'position':
                self.sent_point = point
                if point == self.current_point:
                    if self.sent_marker:
                        self.sent_marker.delete()
                        self.sent_marker = None
                    return True
            elif point == self.sent_point and self.sent_marker:
                self.sent_marker.delete()
                self.sent_marker = None
            attribute = 'current_marker' if kind == 'search' else 'sent_marker'
            marker = getattr(self, attribute)
            if marker:
                marker.delete()
            # Web Mercator cannot draw the poles; retain exact coordinates in records.
            label = f"搜尋 #{event['index']}" if kind=='search' else '最後送出定位'
            setattr(self, attribute, self.map_widget.set_marker(max(-85, min(85, point[0])), point[1], text=label,
                    marker_color_outside='#287fba' if kind=='search' else '#d48b32'))
            if kind == 'search':
                self.current_point = point
                if self.follow.get():
                    self.center()
        elif kind == 'screenshot':
            try:
                self.current_preview.load(event['content'])
                self.current_path = event['path']
                self.current_preview.title.set(f"目前截圖 · 第 {event['index']} 點\n{event['point'][0]:.6f}, {event['point'][1]:.6f}\n{event['timestamp']}")
            except (OSError, ValueError) as exc:
                self.append_log(f'截圖預覽失敗：{exc}')
        elif kind == 'result':
            self.hits, self.errors = event['hits'], max(self.errors, event['errors'])
            self.processed = event['processed']
            record = event['record']
            if record['found']:
                index = len(self.records)
                self.records.append(record)
                self.table.insert('', 'end', iid=str(index), values=(record['index'], record['target'], f"{record['lat']:.6f}, {record['lon']:.6f}", record['timestamp']))
                marker = self.map_widget.set_marker(max(-85, min(85, record['lat'])), record['lon'], text=f"命中 #{record['index']} · {record['target']}",
                    marker_color_outside='#338251', command=lambda _, i=index: self.marker_select(i))
                self.markers.append(marker)
                self.append_log(f"找到 {record['target']}：{record['lat']:.6f}, {record['lon']:.6f}")
                # Show first hit automatically; keep the user's later selection stable.
                if not self.table.selection():
                    self.marker_select(index)
        elif kind == 'progress':
            self.completed, self.total = event['completed'], event['total']
            self.captured = event['captured']
            self.next_index = event['next_index']
        elif kind == 'capture_error':
            self.errors = max(self.errors, event['errors'])
        elif kind == 'log':
            self.append_log(event['text'])
        elif kind == 'done':
            self.set_busy(False)
            self.status.set(event['text'])
            self.append_log(event['text'])
            self.hits, self.errors = event['hits'], event['errors']
            self.next_index = event['next_index']
            if self.next_index < self.end_index:
                self.resume_button.configure(state='normal')
            if self.closing:
                if '失敗' in event['text']:
                    messagebox.showwarning('關閉前請確認', event['text'])
                self.root.destroy()
                return False
        return True

    def poll(self):
        for _ in range(50):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if not self.handle(event):
                return
        pending = max(0, self.captured-self.processed)
        if self.active and self.started:
            self.elapsed = time.monotonic()-self.started
        eta = f'{self.elapsed/self.completed*(self.total-self.completed)/60:.1f} 分' if self.completed and self.active else '—'
        self.stats.set(f'已掃描 {self.completed} / {self.total}　命中 {self.hits}　錯誤 {self.errors}　待辨識 {pending}　已用 {self.elapsed/60:.1f} 分　掃描剩餘約 {eta}')
        self.progress.configure(maximum=max(1, self.total), value=self.completed)
        self.root.after(100, self.poll)

    def close(self):
        if self.active:
            self.closing = True
            self.stop()
        else:
            self.root.destroy()


def main():
    os.chdir(BASE)
    config = json.loads(os.environ.get('PIKMIN_SCAN_CONFIG', '{}'))
    root = tk.Tk()
    ScanApp(root, config)
    root.mainloop()
