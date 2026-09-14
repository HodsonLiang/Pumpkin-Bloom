"""Desktop map UI. Route state and device I/O are owned by fly_engine."""
import math
import os
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkintermapview
from .fly_engine import Controller, validate_point


def duration(seconds):
    hours, rest = divmod(max(0, math.ceil(seconds)), 3600)
    minutes, seconds = divmod(rest, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


class FakeGPSApp:
    def __init__(self, root):
        self.root = root
        root.title('Pikmin · 路徑移動')
        root.geometry('1220x820')
        root.minsize(1000, 820)
        self.commands, self.updates = queue.Queue(), queue.Queue()
        self.controller = Controller(self.commands, self.updates)
        self.snapshot = self.controller.snapshot()
        self.markers = {}
        self.path = None
        self.route_signature = None
        self.closing = False
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Microsoft JhengHei UI', 10))
        style.configure('TButton', padding=(10, 7))
        style.configure('Title.TLabel', font=('Microsoft JhengHei UI', 21, 'bold'), foreground='#245a3d')
        outer = ttk.Frame(root, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='路徑移動', style='Title.TLabel').pack(anchor='w')
        self.status = tk.StringVar(value=self.snapshot['status'])
        ttk.Label(outer, textvariable=self.status, wraplength=1100).pack(anchor='w', pady=(4, 12))
        self.stats = tk.StringVar()
        ttk.Label(outer, textvariable=self.stats, font=('Microsoft JhengHei UI', 13, 'bold')).pack(anchor='w', pady=(0, 12))
        content = ttk.Frame(outer)
        content.pack(fill='both', expand=True)
        side = ttk.Frame(content, padding=(0, 0, 16, 0))
        side.pack(side='left', fill='y')
        self.speed = tk.StringVar(value=os.environ.get('PIKMIN_SPEED', '18'))
        self.interval, self.dwell = tk.StringVar(value='2'), tk.StringVar(value='8')
        self.loop, self.follow = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
        settings = ttk.LabelFrame(side, text='移動設定 · 執行中也可調整', padding=12)
        settings.pack(fill='x')
        for row, (label, variable) in enumerate([('速度（km/h）', self.speed), ('座標傳送間隔（秒）', self.interval), ('抵達標點停留（秒）', self.dwell)]):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky='w', pady=4)
            ttk.Entry(settings, textvariable=variable, width=9).grid(row=row, column=1, padx=8)
        ttk.Checkbutton(settings, text='循環路線：終點 → 第一點', variable=self.loop, command=self.apply_settings).grid(row=3, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Button(settings, text='套用速度與間隔', command=self.apply_settings).grid(row=4, column=0, columnspan=2, sticky='ew')
        controls = ttk.Frame(side)
        controls.pack(fill='x', pady=10)
        for i, (label, command) in enumerate([('▶ 開始／繼續', lambda: self.send('start')), ('Ⅱ 暫停原地', lambda: self.send('pause')),
                ('跳至下一點', lambda: self.send('teleport')), ('清空路線・停原地', lambda: self.send('clear'))]):
            ttk.Button(controls, text=label, command=command).grid(row=i//2, column=i%2, sticky='ew', padx=2, pady=3)
        add = ttk.LabelFrame(side, text='新增標點', padding=10)
        add.pack(fill='x')
        self.lat, self.lon = tk.StringVar(), tk.StringVar()
        for row, (label, variable) in enumerate([('緯度', self.lat), ('經度', self.lon)]):
            ttk.Label(add, text=label).grid(row=row, column=0)
            ttk.Entry(add, textvariable=variable, width=23).grid(row=row, column=1, padx=8, pady=3)
        ttk.Button(add, text='加入路線', command=self.add_input).grid(row=2, column=0, columnspan=2, sticky='ew', pady=4)
        files = ttk.Frame(side)
        files.pack(fill='x', pady=8)
        ttk.Button(files, text='匯入路線', command=self.load_route).pack(side='left', expand=True, fill='x')
        ttk.Button(files, text='匯出路線', command=self.save_route).pack(side='left', expand=True, fill='x', padx=4)
        self.listbox = tk.Listbox(side, height=6, font=('Consolas', 10), exportselection=False)
        self.listbox.pack(fill='both', expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.focus_point)
        self.listbox.bind('<Button-3>', self.list_context)
        ttk.Button(side, text='還原真實定位', command=lambda: self.send('reset')).pack(fill='x', pady=(10, 0))
        right = ttk.Frame(content)
        right.pack(side='left', fill='both', expand=True)
        toolbar = ttk.Frame(right)
        toolbar.pack(fill='x', pady=(0, 8))
        ttk.Button(toolbar, text='回到目前位置', command=self.center).pack(side='left')
        ttk.Button(toolbar, text='複製目前座標', command=self.copy_position).pack(side='left', padx=6)
        ttk.Checkbutton(toolbar, text='跟隨位置', variable=self.follow).pack(side='left')
        self.map_widget = tkintermapview.TkinterMapView(right, corner_radius=8)
        self.map_widget.pack(fill='both', expand=True)
        self.map_widget.set_position(*self.snapshot['position'])
        self.map_widget.set_zoom(15)
        self.current_marker = self.map_widget.set_marker(*self.snapshot['position'], text='目前模擬位置', marker_color_outside='#245a3d')
        self.map_widget.add_right_click_menu_command(label='加入路線標點', command=self.add_map, pass_coords=True)
        self.map_widget.canvas.bind('<Button-3>', self.map_context)
        ttk.Label(right, text='右鍵新增標點；點左側清單可定位。ETA 包含傳送間隔與中途停留，未含裝置延遲。', wraplength=650).pack(anchor='w', pady=8)
        self.position_label = tk.StringVar()
        ttk.Label(right, textvariable=self.position_label).pack(anchor='w')
        self.apply_settings()
        self.controller.start()
        root.protocol('WM_DELETE_WINDOW', self.on_closing)
        root.after(100, self.poll)

    def send(self, kind, value=None):
        if not self.closing:
            self.commands.put((kind, value))

    def map_context(self, event):
        canvas = self.map_widget.canvas
        nearby = set(canvas.find_overlapping(event.x-4, event.y-4, event.x+4, event.y+4))
        uid = next((identifier for identifier, marker in self.markers.items()
                    if nearby.intersection({marker.polygon, marker.big_circle, marker.canvas_text, marker.canvas_icon})), None)
        if uid is None:
            self.map_widget.mouse_right_click(event)
            return 'break'
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label=f'刪除標點 {uid}（暫停原地）', command=lambda: self.send('remove', uid))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def list_context(self, event):
        index = self.listbox.nearest(event.y)
        if not 0 <= index < len(self.snapshot['points']):
            return 'break'
        bounds = self.listbox.bbox(index)
        if not bounds or not bounds[1] <= event.y <= bounds[1]+bounds[3]:
            return 'break'
        uid = self.snapshot['points'][index][0]
        self.listbox.selection_clear(0, 'end')
        self.listbox.selection_set(index)
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label=f'刪除標點 {uid}（暫停原地）', command=lambda: self.send('remove', uid))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def apply_settings(self):
        try:
            speed, interval, dwell = map(float, (self.speed.get(), self.interval.get(), self.dwell.get()))
            if not all(map(math.isfinite, (speed, interval, dwell))) or not (0 < speed <= 1000 and 0.2 <= interval <= 3600 and 0 <= dwell <= 3600):
                raise ValueError('速度：大於 0～1000 km/h；間隔：0.2～3600 秒；停留：0～3600 秒。')
            self.send('settings', (speed, interval, dwell, self.loop.get()))
        except ValueError as exc:
            messagebox.showerror('設定無效', str(exc))

    def add_map(self, point):
        try:
            self.send('add', [validate_point(*point)])
        except ValueError as exc:
            messagebox.showerror('座標無效', str(exc))

    def add_input(self):
        try:
            point = validate_point(float(self.lat.get()), float(self.lon.get()))
            self.send('add', [point])
            self.lat.set('')
            self.lon.set('')
        except ValueError as exc:
            messagebox.showerror('座標無效', str(exc))

    def load_route(self):
        path = filedialog.askopenfilename(filetypes=[('座標檔', '*.txt')])
        if not path:
            return
        try:
            points = []
            for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
                if line.strip():
                    lat, lon = map(float, line.split(','))
                    points.append(validate_point(lat, lon))
            if not points:
                raise ValueError('檔案沒有座標。')
            if len(points) + len(self.snapshot['points']) > 2000:
                raise ValueError('地圖路線最多匯入至 2000 點，請選用較小的路線檔。')
            self.send('add', points)
        except (OSError, ValueError) as exc:
            messagebox.showerror('匯入失敗', str(exc))

    def save_route(self):
        if not self.snapshot['points']:
            return
        path = filedialog.asksaveasfilename(defaultextension='.txt', initialfile='fly_route.txt')
        if path:
            try:
                Path(path).write_text(''.join(f'{p[0]:.7f},{p[1]:.7f}\n' for _, p in self.snapshot['points']), encoding='utf-8')
            except OSError as exc:
                messagebox.showerror('匯出失敗', str(exc))

    def center(self):
        self.map_widget.set_position(*self.snapshot['position'])

    def copy_position(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(','.join(f'{n:.7f}' for n in self.snapshot['position']))

    def focus_point(self, _event):
        selected = self.listbox.curselection()
        if selected and selected[0] < len(self.snapshot['points']):
            self.map_widget.set_position(*self.snapshot['points'][selected[0]][1])

    def render(self, state):
        old = self.snapshot
        self.snapshot = state
        self.status.set(state['status'] if not self.closing else '正在關閉並還原定位，請稍候…')
        eta_label = '本圈剩餘' if state['loop'] else '預估剩餘'
        self.stats.set(f"{eta_label}  {duration(state['seconds'])}     剩餘 {state['distance']/1000:.2f} km     已完成 {state['laps']} 趟" + ('   ∞ 循環' if state['loop'] else ''))
        self.position_label.set(f"最後送出／預設座標：{state['position'][0]:.7f}, {state['position'][1]:.7f}" + (f"   停留 {state['wait']:.1f} 秒" if state['wait'] else ''))
        self.current_marker.set_position(*state['position'])
        if self.follow.get() and old['position'] != state['position']:
            self.center()
        signature = (tuple(state['points']), state['index'], state['loop'])
        if signature != self.route_signature:
            self.route_signature = signature
            for marker in self.markers.values():
                marker.delete()
            self.markers.clear()
            self.listbox.delete(0, 'end')
            for index, (uid, point) in enumerate(state['points']):
                label = '→' if index == state['index'] else ('✓' if index < state['index'] else ' ')
                self.listbox.insert('end', f'{label} #{uid}  {point[0]:.5f}, {point[1]:.5f}')
                self.markers[uid] = self.map_widget.set_marker(*point, text=f'標點 {uid}', marker_color_outside='#9aaca0' if index < state['index'] else '#cf7944')
        path_points = [state['position']] + [p for _, p in state['points'][state['index']:]]
        if state['loop'] and state['points']:
            path_points += [p for _, p in state['points'][:state['index']+1]]
        if len(path_points) < 2:
            if self.path:
                self.path.delete()
                self.path = None
        elif self.path:
            self.path.set_position_list(path_points)
        else:
            self.path = self.map_widget.set_path(path_points, color='#357b56', width=4)

    def poll(self):
        latest = None
        while True:
            try:
                latest = self.updates.get_nowait()
            except queue.Empty:
                break
        if latest:
            if latest.get('closed'):
                if latest['status'].startswith('已停止'):
                    messagebox.showwarning('定位還原失敗', latest['status'])
                self.root.destroy()
                return
            self.render(latest)
        self.root.after(100, self.poll)

    def on_closing(self):
        if not self.closing:
            self.send('close')
            self.closing = True
            self.status.set('正在關閉並還原定位，請稍候…')
