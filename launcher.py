"""Windows desktop controller. Run through Start.bat to request elevation."""
import ctypes
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pikmin.storage import WAYPOINTS, write_json
from pikmin.waypoint_picker import WaypointPicker
from pikmin.country_picker import CountryPicker
from pikmin.geoapify import KINDS, country_codes
from tkinter.scrolledtext import ScrolledText
from pikmin.device_backend import ProcessRunner, device_ids, kill_tree

BASE = Path(__file__).resolve().parent
SETTINGS = BASE / 'launcher_settings.json'


class Launcher(ProcessRunner):
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.tunnel = None
        self.process = None
        self.busy = False
        self.closing = False
        self.device_connected = False
        self.last_devices = None
        self.monitor_stop = threading.Event()
        root.title('Pikmin · 裝置控制台')
        root.geometry('960x760')
        root.minsize(820, 650)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Microsoft JhengHei UI', 10))
        style.configure('TButton', padding=(12, 8))
        style.configure('Title.TLabel', font=('Microsoft JhengHei UI', 23, 'bold'), foreground='#245a3d')
        body = ttk.Frame(root, padding=24)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Pikmin 裝置控制台', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='可離線規劃與管理資料；搜尋、傳送及移動時才需要連接 iOS 裝置', padding=(0, 6)).pack(anchor='w')
        self.status = tk.StringVar(value='待命 · 可在沒有裝置的情況下開啟所有介面')
        ttk.Label(body, textvariable=self.status, wraplength=850, padding=(0, 10)).pack(anchor='w')
        self.device_status = tk.StringVar(value='裝置連接狀態：檢查中…')
        ttk.Label(body, textvariable=self.device_status, wraplength=850).pack(anchor='w')
        self.tabs = ttk.Notebook(body)
        self.tabs.pack(fill='x', pady=8)
        scan = ttk.Frame(self.tabs, padding=16)
        fly = ttk.Frame(self.tabs, padding=16)
        generate = ttk.Frame(self.tabs, padding=16)
        self.tabs.add(scan, text='  傳送與辨識  ')
        self.tabs.add(fly, text='  路徑移動  ')
        self.tabs.add(generate, text='  產生座標  ')
        defaults = dict(waypoints=str(WAYPOINTS/'waypoints.pikscan'), max_points='10000', initial_wait='12',
                        screenshot_wait='5', interval='10', threshold='0.058', speed='18',
                        countries='tw', start_position='')
        try:
            saved = json.loads(SETTINGS.read_text(encoding='utf-8'))
            defaults.update({k: v for k, v in saved.items() if k in defaults})
            if 'source' in saved:
                defaults['countries'] = 'tw'
        except (OSError, ValueError, AttributeError):
            pass
        self.fields = {key: tk.StringVar(value=value) for key, value in defaults.items()}
        ttk.Label(scan, text='搜尋座標').grid(row=0, column=0)
        self.waypoint_picker = WaypointPicker(scan, self.fields['waypoints'])
        self.waypoint_picker.grid(row=0, column=1, columnspan=2, sticky='ew')
        for row, (label, key) in enumerate([('最多掃描點數', 'max_points'), ('首次載入等待（秒）', 'initial_wait'),
                    ('傳送後截圖等待（秒）', 'screenshot_wait'), ('每點最短週期（秒）', 'interval'), ('辨識差異門檻（越小越嚴格）', 'threshold')], 1):
            self.entry(scan, label, key, row)
        ttk.Label(scan, text='啟動後開啟搜尋地圖與截圖介面，再按「開始搜尋」。可在搜尋介面切換原本提前傳送或逐點等待截圖。', wraplength=800).grid(row=6, column=0, columnspan=3, sticky='w', pady=8)
        self.entry(fly, '移動速度（km/h）', 'speed', 0)
        self.entry(fly, '起始緯度,經度（可留空）', 'start_position', 1, width=40)
        ttk.Label(fly, text='啟動後開啟地圖視窗。\n在地圖按右鍵加入標點，或匯入路線，再按「開始／繼續」。\n地圖內可隨時調整速度、傳送間隔與停留時間，並開啟循環移動。', wraplength=780).grid(row=2, column=0, columnspan=3, sticky='w', pady=16)
        ttk.Label(generate, text='搜尋國家／地區').grid(row=0, column=0, sticky='w')
        self.country_picker = CountryPicker(generate, self.fields['countries'])
        self.country_picker.grid(row=0, column=1, columnspan=2, sticky='ew')
        self.entry(generate, '最多產生點數', 'max_points', 1)
        self.locality_types = {kind: tk.BooleanVar(value=True) for kind in KINDS}
        types = ttk.Frame(generate)
        types.grid(row=2, column=0, columnspan=3, sticky='w')
        for kind, label in KINDS.items():
            ttk.Checkbutton(types, text=label, variable=self.locality_types[kind]).pack(side='left')
        ttk.Label(generate, text='Geoapify / OpenStreetMap：首次下載該國 ZIP，之後使用本地快取。', wraplength=780).grid(row=3, column=0, columnspan=3, pady=8)
        bar = ttk.Frame(body)
        bar.pack(fill='x', pady=8)
        self.start_button = ttk.Button(bar, text='▶ 啟動所選模式', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(bar, text='■ 關閉所選程式', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=10)
        ttk.Button(bar, text='開啟辨識結果', command=self.results).pack(side='right')
        ttk.Label(body, text='執行紀錄').pack(anchor='w')
        self.log = ScrolledText(body, height=12, state='disabled', background='#15271e', foreground='#e3f1e7', font=('Consolas', 10))
        self.log.pack(fill='both', expand=True, pady=(6, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)
        self.tabs.bind('<<NotebookTabChanged>>', lambda _: self.update_start_state())
        threading.Thread(target=self.monitor_devices, daemon=True).start()

    def update_start_state(self):
        enabled = not self.busy and not self.closing
        self.start_button.configure(state='normal' if enabled else 'disabled')

    def monitor_devices(self):
        while not self.monitor_stop.is_set():
            try:
                ids = device_ids()
                connected = len(ids) == 1
                text = ('已偵測到 1 台 iOS 裝置 · 實際使用定位功能時準備連線' if connected else
                        '未連接 iOS 裝置 · 請接上資料線並解鎖裝置' if not ids else
                        '連接多台裝置 · 請只保留要操作的一台')
            except Exception as exc:
                ids, text = [], str(exc)
            self.events.put(('device', (tuple(ids), text)))
            self.monitor_stop.wait(4)

    def entry(self, parent, label, key, row, width=18):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', pady=4, padx=(0, 16))
        ttk.Entry(parent, textvariable=self.fields[key], width=width).grid(row=row, column=1, sticky='w', pady=4)

    def results(self):
        folder = BASE / 'found_targets'
        folder.mkdir(exist_ok=True)
        os.startfile(folder)

    def start(self):
        if self.busy:
            return
        mode = self.tabs.index(self.tabs.select())
        values = {key: value.get() for key, value in self.fields.items()}
        try:
            config = dict(waypoints=values['waypoints'], speed=18)
            if mode in (0, 2):
                maximum = int(values['max_points'])
                if maximum < 1:
                    raise ValueError('點數上限須大於 0。')
                config['max_points'] = maximum
            keys = ('initial_wait', 'screenshot_wait', 'interval', 'threshold') if mode == 0 else ('speed',) if mode == 1 else ()
            for key in keys:
                config[key] = float(values[key])
                if not math.isfinite(config[key]) or config[key] <= 0:
                    raise ValueError('等待時間、速度及門檻須為大於 0 的數字。')
            if config.get('threshold', 0) > 1:
                raise ValueError('辨識門檻須介於 0 與 1。')
            if config['speed'] > 1000:
                raise ValueError('移動速度最多 1000 km/h。')
            if mode == 1 and values['start_position'].strip():
                from pikmin.fly_engine import validate_point
                config['start_position'] = validate_point(*map(float, values['start_position'].split(',')))
            if mode == 2:
                values['countries'] = country_codes(values['countries'])
                values['kinds'] = [k for k, v in self.locality_types.items() if v.get()]
                if not values['kinds']:
                    raise ValueError('請至少選擇一種聚落類型。')
                WAYPOINTS.mkdir(parents=True, exist_ok=True)
                output = filedialog.asksaveasfilename(initialdir=WAYPOINTS, initialfile='new.pikscan', defaultextension='.pikscan', filetypes=[('搜尋座標', '*.pikscan')])
                if not output:
                    return
                if Path(output).parent.resolve() != WAYPOINTS.resolve():
                    raise ValueError('請儲存在 data/waypoints 資料夾，供下拉選單選用。')
                values['output'] = output
            write_json(SETTINGS, {k: v.get() for k, v in self.fields.items()})
        except (ValueError, TypeError, OSError) as exc:
            messagebox.showerror('請檢查設定', str(exc))
            return
        self.busy = True
        self.cancel.clear()
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.status.set('準備啟動…')
        threading.Thread(target=self.run, args=(mode, config, values), daemon=True).start()

    def run(self, mode, config, values):
        import uuid
        from pikmin.storage import DATA
        stop_file = DATA/'runtime'/(uuid.uuid4().hex+'.stop')
        outcome = '已完成'
        try:
            if self.cancel.is_set():
                return
            if mode == 2:
                self.process = self.spawn(['-m', 'pikmin.coordinate_job'], {'PIKMIN_GENERATE_CONFIG': json.dumps(values)})
            else:
                self.process = self.spawn(['main.py' if mode == 0 else 'fly.py'],
                    {'PIKMIN_SCAN_CONFIG': json.dumps(config), 'PIKMIN_SPEED': str(config['speed']),
                     'PIKMIN_START_POSITION': json.dumps(config.get('start_position')),
                     'PIKMIN_STOP_FILE': str(stop_file)})
            self.events.put(('status', '執行中 · '+['傳送與辨識', '請在地圖視窗操作', '產生座標'][mode]))
            while self.process.poll() is None:
                if self.cancel.wait(.2):
                    if mode != 2:
                        stop_file.parent.mkdir(parents=True, exist_ok=True)
                        stop_file.touch()
                        try:
                            self.process.wait(timeout=45)
                        except subprocess.TimeoutExpired:
                            self.emit('程式未及時結束，強制關閉；請確認手機定位已還原。')
                    kill_tree(self.process)
                    break
            if self.cancel.is_set():
                outcome = '已停止'
            elif self.process.returncode:
                raise RuntimeError(f'程式異常結束（代碼 {self.process.returncode}），請查看紀錄。')
            elif mode == 2:
                self.events.put(('waypoints', values['output']))
        except Exception as exc:
            outcome = '執行失敗 · 請查看紀錄'
            self.emit(str(exc))
        finally:
            try:
                kill_tree(self.process)
            finally:
                stop_file.unlink(missing_ok=True)
                self.process = None
                self.events.put(('done', outcome))

    def stop(self):
        self.cancel.set()
        self.stop_button.configure(state='disabled')
        self.status.set('正在停止，請稍候…')

    def close(self):
        self.monitor_stop.set()
        if self.busy:
            self.closing = True
            self.stop()
        else:
            self.root.destroy()

    def poll(self):
        for _ in range(250):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'log':
                self.log.configure(state='normal')
                self.log.insert('end', value + '\n')
                if int(self.log.index('end-1c').split('.')[0]) > 2500:
                    self.log.delete('1.0', '501.0')
                self.log.see('end')
                self.log.configure(state='disabled')
            elif kind == 'waypoints':
                self.fields['waypoints'].set(value)
            elif kind == 'status':
                self.status.set(value)
            elif kind == 'device':
                ids, text = value
                if self.last_devices is not None and ids != self.last_devices and not self.closing:
                    messagebox.showinfo('裝置連接狀態', text, parent=self.root)
                self.last_devices = ids
                self.device_connected = len(ids) == 1
                self.device_status.set('裝置連接狀態：'+text)
                self.update_start_state()
            elif kind == 'done':
                self.busy = False
                self.status.set(value)
                self.update_start_state()
                self.stop_button.configure(state='disabled')
                if self.closing:
                    self.root.destroy()
                    return
        self.root.after(100, self.poll)


if __name__ == '__main__':
    os.chdir(BASE)
    root = tk.Tk()
    if os.name == 'nt' and not ctypes.windll.shell32.IsUserAnAdmin():
        root.withdraw()
        messagebox.showerror('需要管理員權限', '請雙擊 Start.bat 並接受 Windows 管理員授權。')
        root.destroy()
    else:
        Launcher(root)
        root.mainloop()
