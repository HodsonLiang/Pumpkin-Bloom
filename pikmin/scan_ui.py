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
from .world_map import WorldMap
from .device_session import DeviceSession
from .waypoint_picker import WaypointPicker
from .scan_catalog import ScanCatalog
from tkinter import simpledialog
from tkinter import font as tkfont
import math
from .scan_engine import BASE, DEFAULTS, Scanner, prepare_config
from .scan_actions import ScanActions
from .ui_layout import Foldout


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


class ScanApp(ScanCatalog, ScanActions):
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
        self.recognition_seconds = None
        self.captured = self.processed = 0
        self.sent_point = None
        self.started = None
        self.elapsed = 0.
        self.active = False
        self.next_index = None
        self.init_actions()
        self.init_catalog()
        self.delay_seconds = 0
        self.waiting_start = False
        self.start_generation = 0
        root.title('Pikmin · 目標搜尋')
        root.geometry('1380x900')
        root.minsize(1000, 650)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Microsoft JhengHei UI', 10))
        style.configure('TButton', padding=(9, 6))
        style.configure('Title.TLabel', font=('Microsoft JhengHei UI', 22, 'bold'), foreground='#245a3d')
        outer = ttk.Frame(root, padding=10)
        outer.pack(fill='both', expand=True)
        head = ttk.Frame(outer)
        head.pack(fill='x')
        ttk.Label(head, text='目標搜尋', style='Title.TLabel').pack(side='left')
        self.status = tk.StringVar(value='待命 · 選擇座標檔後開始搜尋；可離線管理資料，開始搜尋時才檢查裝置')
        ttk.Label(head, textvariable=self.status, wraplength=1000).pack(side='left', padx=20)
        self.settings_panel = Foldout(outer, '搜尋設定 · 座標檔與等待時間')
        self.settings_panel.pack(fill='x', pady=4)
        settings = self.settings_panel.body
        values = {**DEFAULTS, **(config or {})}
        self.fields = {key: tk.StringVar(value=values[key]) for key in DEFAULTS}
        self.setting_widgets = []
        ttk.Label(settings, text='座標檔').grid(row=0, column=0, sticky='w')
        self.waypoint_picker = WaypointPicker(settings, self.fields['waypoints'])
        self.waypoint_picker.grid(row=0, column=1, columnspan=4, sticky='ew', padx=6)
        self.timing = tk.StringVar(value='逐點等待後截圖' if values['timing']=='sequential' else '提前傳送（原流程）')
        combo = ttk.Combobox(settings, textvariable=self.timing, values=['提前傳送（原流程）', '逐點等待後截圖'], width=23, state='readonly')
        combo.grid(row=0, column=5, padx=8, sticky='w')
        self.setting_widgets.append(combo)
        labels = [('起始點', 'start_index'), ('最多點數', 'max_points'), ('首次等待 秒', 'initial_wait'),
                  ('截圖等待 秒', 'screenshot_wait'), ('最短週期 秒', 'interval'), ('差異門檻', 'threshold')]
        for col, (label, key) in enumerate(labels):
            ttk.Label(settings, text=label).grid(row=1+col//3, column=(col%3)*2, pady=(8, 0), sticky='w')
            entry = ttk.Entry(settings, textvariable=self.fields[key], width=7)
            entry.grid(row=1+col//3, column=(col%3)*2+1, padx=(4, 12), pady=(8, 0))
            self.setting_widgets.append(entry)
        controls = ttk.Frame(outer)
        controls.pack(fill='x')
        self.toggle_button = ttk.Button(controls, text='▶ 開始', command=self.toggle_search)
        self.toggle_button.pack(side='left')
        self.restart_button = ttk.Button(controls, text='從頭開始搜尋', command=self.restart_search)
        self.restart_button.pack(side='left', padx=6)
        ttk.Button(controls, text='搜尋種類…', command=self.type_dialog).pack(side='left', padx=4)
        self.delay_button = ttk.Button(controls, text='倒數：立即', command=self.configure_delay)
        self.delay_button.pack(side='left')
        self.follow = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text='跟隨搜尋位置', variable=self.follow).pack(side='left', padx=12)
        ttk.Button(controls, text='回到搜尋位置', command=self.center).pack(side='left')
        ttk.Button(controls, text='結果資料夾', command=self.open_folder).pack(side='right')
        self.manual_panel = Foldout(outer, '輸入座標傳送')
        self.manual_panel.pack(fill='x', pady=4)
        self.manual_bar(self.manual_panel.body)
        ttk.Label(outer, textvariable=self.search_summary, wraplength=1200).pack(anchor='w', pady=(4, 0))
        self.stats = tk.StringVar(value='已掃描 0 / 0　命中 0　錯誤 0')
        ttk.Label(outer, textvariable=self.stats, font=('Microsoft JhengHei UI', 12, 'bold')).pack(anchor='w', pady=(8, 4))
        self.progress = ttk.Progressbar(outer)
        self.progress.pack(fill='x', pady=(0, 8))
        body = ttk.Panedwindow(outer, orient='vertical')
        body.pack(fill='both', expand=True)
        top = ttk.Panedwindow(body, orient='horizontal', height=350)
        body.add(top, weight=3)
        map_frame = ttk.Frame(top)
        top.add(map_frame, weight=3)
        self.map_widget = WorldMap(map_frame, width=500, height=310, corner_radius=8)
        self.map_widget.pack(fill='both', expand=True)
        self.map_widget.set_position(25.033964, 121.564468)
        self.map_widget.set_zoom(8)
        self.map_widget.add_right_click_menu_command(label='傳送到這裡（先停止掃描）', command=self.request_teleport, pass_coords=True)
        ttk.Label(map_frame, text='蘑菇：目標類型　藍字：搜尋點　橘字：送出定位；右鍵可傳送', wraplength=600).pack(anchor='w', pady=4)
        previews = ttk.Notebook(top)
        top.add(previews, weight=1)
        self.current_preview = Preview(previews, '目前截圖 · 等待搜尋')
        previews.add(self.current_preview, text='目前截圖')
        self.hit_preview = Preview(previews, '命中截圖 · 點選下方結果')
        previews.add(self.hit_preview, text='目標截圖')
        self.current_preview.canvas.bind('<Double-Button-1>', lambda _: self.open_image(self.current_path))
        self.hit_preview.canvas.bind('<Double-Button-1>', lambda _: self.open_selected())
        bottom = ttk.Notebook(body, height=160)
        body.add(bottom, weight=1)
        gallery = ttk.Frame(bottom, padding=6)
        logs = ttk.Frame(bottom)
        bottom.add(gallery, text='  找到的目標  ')
        bottom.add(logs, text='  執行紀錄  ')
        bar = ttk.Frame(gallery)
        bar.pack(fill='x', pady=(0, 4))
        ttk.Button(bar, text='傳送到選取目標', command=self.teleport_selected).pack(side='left')
        ttk.Button(bar, text='刪除選取目標', command=self.delete_selected).pack(side='left', padx=6)
        ttk.Button(bar, text='☆ / ★', command=self.toggle_bookmarks).pack(side='left')
        ttk.Button(bar, text='篩選顯示…', command=lambda: self.type_dialog(False)).pack(side='left', padx=4)
        self.load_button = ttk.Button(bar, text='載入歷史結果', command=self.load_history)
        self.load_button.pack(side='left', padx=6)
        actions = ttk.Menubutton(bar, text='目標操作 ▾')
        menu = self.target_menu(actions)
        actions.configure(menu=menu)
        actions.pack(side='left')
        table_frame = ttk.Frame(gallery)
        table_frame.pack(fill='both', expand=True)
        columns = ('bookmark', 'index', 'target', 'coords', 'time')
        self.table = ttk.Treeview(table_frame, columns=columns, show='headings', height=5, selectmode='extended')
        for key, title, width in zip(columns, ['書籤', '座標序號', '目標', '緯度, 經度', '截圖時間'], [50, 90, 160, 240, 180]):
            self.table.heading(key, text=title, command=lambda k=key: self.sort_targets(k))
            self.table.column(key, width=width)
        heading_font = tkfont.Font(root=root, font=style.lookup('Treeview.Heading', 'font') or ('Microsoft JhengHei UI', 10))
        star_width = heading_font.measure('書籤')+8
        self.table.column('bookmark', width=star_width, minwidth=star_width, stretch=False, anchor='center')
        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.table.pack(fill='both', expand=True)
        self.table.bind('<<TreeviewSelect>>', self.select_hit)
        self.table.bind('<Control-a>', lambda _: (self.select_all(), 'break')[-1])
        self.table.bind('<Button-3>', self.target_context)
        self.table.bind('<Button-1>', self.star_click)
        self.table.bind('<Delete>', lambda _: self.delete_selected())
        self.log = ScrolledText(logs, height=6, state='disabled', font=('Consolas', 10))
        self.log.pack(fill='both', expand=True)
        ttk.Label(outer, text='目前截圖是最近一次擷取，並非即時串流。提前傳送模式沿用原本延遲假設，標記為搜尋指定座標，並非手機 GPS 回讀。', wraplength=1320).pack(anchor='w', pady=(6, 0))
        self.device_session = DeviceSession(root, self.stop)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def refresh_search_buttons(self):
        busy = self.active or self.waiting_start or self.manual_busy or self.manual_active
        stopping = ((self.active and self.scanner is not None and self.scanner.stop_event.is_set())
                    or self.pending_reset)
        self.toggle_button.configure(text='■ 停止' if busy else '▶ 開始',
                                     state='disabled' if self.closing or stopping else 'normal')
        self.restart_button.configure(state='disabled' if self.closing or self.active or self.waiting_start or self.manual_busy else 'normal')

    def toggle_search(self):
        if self.closing:
            return
        if self.active or self.waiting_start or self.manual_busy or self.manual_active:
            self.stop()
            return
        same_file = (self.next_index is not None and
                     Path(self.fields['waypoints'].get()).resolve() == Path(self.last_config['waypoints']).resolve())
        if same_file:
            if self.next_index >= self.end_index:
                messagebox.showinfo('搜尋已完成', '這份座標已搜尋完畢；要重新搜尋請按「從頭開始搜尋」。')
            else:
                self.resume()
        else:
            self.start()

    def restart_search(self):
        if self.closing or self.active or self.waiting_start or self.manual_busy:
            return
        if (self.next_index is not None and
                Path(self.fields['waypoints'].get()).resolve() == Path(self.last_config['waypoints']).resolve()):
            self.fields['max_points'].set(getattr(self, 'initial_limit', self.last_config.get('max_points', self.fields['max_points'].get())))
        self.fields['start_index'].set(1)
        self.start()

    def set_busy(self, busy):
        self.active = busy
        self.waypoint_picker.set_enabled(not busy)
        self.refresh_search_buttons()
        for widget in self.setting_widgets:
            widget.configure(state='disabled' if busy else ('readonly' if isinstance(widget, ttk.Combobox) else 'normal'))

    def start(self):
        if self.active or self.waiting_start or self.closing or self.manual_busy:
            return
        if self.manual_active:
            self.pending_start = True
            self.run_manual('reset')
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
        if not self.search_types:
            messagebox.showerror('請選擇目標', '至少選一種搜尋目標。')
            return
        config['target_names'] = sorted(self.search_types)
        self.waiting_start = True
        self.refresh_search_buttons()
        self.start_generation += 1
        generation = self.start_generation
        deadline = time.monotonic()+self.delay_seconds
        def ready():
            if self.closing or generation != self.start_generation:
                return
            self.waiting_start = False
            config['target_names'] = sorted(self.search_types)
            self.begin_scan(config, points)
        def countdown():
            if self.closing or generation != self.start_generation:
                return
            remaining = math.ceil(deadline-time.monotonic())
            if remaining > 0:
                self.status.set(f'倒數 {remaining} 秒後開始搜尋')
                self.root.after(200, countdown)
            else:
                self.status.set('正在準備裝置連線…')
                self.device_session.ensure(ready, self.cancel_start)
        countdown()

    def configure_delay(self):
        value = simpledialog.askinteger('倒數搜尋', '按開始後等待幾秒？（0 為立即）', initialvalue=self.delay_seconds, minvalue=0, maxvalue=86400, parent=self.root)
        if value is not None:
            self.delay_seconds = value
            self.delay_button.configure(text=f'倒數：{value} 秒' if value else '倒數：立即')

    def cancel_start(self):
        self.start_generation += 1
        self.waiting_start = False
        self.device_session.cancel_pending()
        self.status.set('待命 · 已取消啟動')
        self.refresh_search_buttons()

    def begin_scan(self, config, points):
        if self.next_index is None or config['waypoints'] != getattr(self, 'last_config', {}).get('waypoints'):
            self.initial_limit = config['max_points']
        self.last_config = config
        self.end_index = config['start_index']+len(points)
        for marker in (self.current_marker, self.sent_marker):
            if marker:
                marker.delete()
        self.current_marker = self.sent_marker = None
        self.current_point = self.current_path = None
        for preview, title in ((self.current_preview, '目前截圖 · 等待搜尋'),):
            preview.original = None
            preview.title.set(title)
            preview.draw()
        self.completed = self.hits = self.errors = 0
        self.recognition_seconds = None
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
        if self.waiting_start:
            self.cancel_start()
        self.pending_teleport = None
        self.pending_start = False
        if self.active:
            self.scanner.stop_event.set()
            self.status.set('正在停止 · 等待目前指令結束並儲存辨識結果')
        elif self.manual_busy:
            self.pending_reset = True
        elif self.manual_active:
            self.run_manual('reset')
        self.refresh_search_buttons()

    def resume(self):
        if self.next_index is not None:
            if not Path(self.last_config['waypoints']).is_file():
                messagebox.showerror('無法繼續', '原搜尋座標檔已移動或刪除。請重新選檔後開始搜尋。')
                return
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
        return self.records[int(selection[0])] if selection and int(selection[0]) < len(self.records) else None

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
        if len(self.table.selection()) != 1:
            return
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
        if str(index) not in self.table.get_children():
            return
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
        if kind == 'manual_done':
            return self.handle_manual_done(event)
        elif kind == 'history':
            for record in event['records']:
                if Path(record['path']).is_file():
                    self.add_record(record, refresh=False)
            self.refresh_catalog()
        elif kind == 'history_done':
            self.history_busy = False
            self.load_button.configure(state='normal')
            self.append_log(event['text'])
        elif kind == 'session':
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
                    text_color='#287fba' if kind=='search' else '#d48b32',
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
                added_index = self.add_record(record)
                self.append_log(f"找到 {record['target']}：{record['lat']:.6f}, {record['lon']:.6f}")
                # Show first hit automatically; keep the user's later selection stable.
                if not self.table.selection() and added_index is not None:
                    self.marker_select(added_index)
        elif kind == 'progress':
            self.completed, self.total = event['completed'], event['total']
            self.captured = event['captured']
            self.next_index = event['next_index']
        elif kind == 'capture_error':
            self.errors = max(self.errors, event['errors'])
        elif kind == 'recognition':
            self.recognition_seconds = event['seconds']
        elif kind == 'log':
            self.append_log(event['text'])
        elif kind == 'done':
            if '失敗' in event['text'] and not self.closing:
                messagebox.showerror('搜尋失敗', event['text'])
            self.set_busy(False)
            self.status.set(event['text'])
            self.append_log(event['text'])
            self.hits, self.errors = event['hits'], event['errors']
            self.next_index = event['next_index']
            self.refresh_search_buttons()
            if self.closing:
                if '失敗' in event['text']:
                    messagebox.showwarning('關閉前請確認', event['text'])
                self.finish_close()
                return False
            elif self.pending_teleport is not None:
                self.dispatch_teleport()
        return True

    def poll(self):
        stop_file = os.environ.get('PIKMIN_STOP_FILE')
        if stop_file and Path(stop_file).exists() and not self.closing:
            self.close()
            if not self.root.winfo_exists():
                return
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
        recognition = f'{self.recognition_seconds:.2f} 秒' if self.recognition_seconds is not None else '—'
        self.stats.set(f'已掃描 {self.completed} / {self.total}　本次命中 {self.hits}　清單 {len(self.records)}　錯誤 {self.errors}　待辨識 {pending}　辨識 {recognition}　剩餘約 {eta}')
        self.progress.configure(maximum=max(1, self.total), value=self.completed)
        self.root.after(100, self.poll)

    def close(self):
        self.cancel_start()
        self.closing = True
        self.pending_teleport = None
        self.pending_start = False
        if self.active:
            self.stop()
        elif self.manual_busy:
            self.status.set('等待定位指令結束，接著還原定位…')
        elif self.manual_active:
            self.run_manual('reset')
        else:
            self.finish_close()


def main():
    os.chdir(BASE)
    config = json.loads(os.environ.get('PIKMIN_SCAN_CONFIG', '{}'))
    root = tk.Tk()
    ScanApp(root, config)
    root.mainloop()
