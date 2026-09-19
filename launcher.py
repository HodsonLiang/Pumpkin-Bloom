"""Windows desktop controller. Run through Start.bat to request elevation."""
import ctypes
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import urllib.request

BASE = Path(__file__).resolve().parent
PYTHON = BASE / 'myenv/Scripts/python.exe'
SETTINGS = BASE / 'launcher_settings.json'
HIDDEN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def device_ids():
    result = subprocess.run([str(PYTHON), '-m', 'pymobiledevice3', 'usbmux', 'list', '--simple'],
                            capture_output=True, text=True, encoding='utf-8', errors='replace',
                            timeout=8, creationflags=HIDDEN, env={**os.environ, 'NO_COLOR': '1'})
    if result.returncode:
        raise RuntimeError('無法讀取 Apple 裝置服務；請安裝／修復 Apple Devices 或 iTunes 驅動。')
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
            raise ValueError()
    except ValueError:
        raise RuntimeError('裝置查詢失敗；請檢查 Apple 驅動、USB 與信任配對。') from None
    return sorted(set(data))


def read_waypoints(path):
    points = []
    with open(path, encoding='utf-8-sig') as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                lat, lon = map(float, line.strip().split(','))
                if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError()
                points.append((lat, lon))
            except ValueError:
                raise ValueError(f'第 {number} 行座標無效，格式須為「緯度,經度」。') from None
    if not points:
        raise ValueError('座標檔是空的。')
    return points


def tunnels():
    from pymobiledevice3.tunneld.api import TUNNELD_DEFAULT_ADDRESS
    host, port = TUNNELD_DEFAULT_ADDRESS
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://{host}:{port}/', timeout=2) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise ValueError('連線服務回傳格式錯誤')
    return data


def kill_tree(process):
    if process and process.poll() is None:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       capture_output=True, creationflags=HIDDEN, timeout=15)
        process.wait(timeout=5)


class Launcher:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.tunnel = None
        self.process = None
        self.busy = False
        self.closing = False
        self.device_connected = False
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
        ttk.Label(body, text='連接 iPhone → 選擇模式 → 一鍵啟動', padding=(0, 6)).pack(anchor='w')
        self.status = tk.StringVar(value='待命 · 請連接並解鎖 iPhone，確認已信任電腦及開啟開發者模式')
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
        defaults = dict(waypoints=str(BASE / 'waypoints.txt'), max_points='10000', initial_wait='12',
                        screenshot_wait='5', interval='10', threshold='0.058', speed='18',
                        countries='Norway, France, Germany, Argentina, Chile, Peru, Colombia, Brazil', source='世界城市')
        try:
            defaults.update(json.loads(SETTINGS.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            pass
        self.fields = {key: tk.StringVar(value=value) for key, value in defaults.items()}
        self.entry(scan, '座標檔', 'waypoints', 0, width=65)
        ttk.Button(scan, text='瀏覽…', command=self.browse).grid(row=0, column=2, padx=8)
        for row, (label, key) in enumerate([('最多掃描點數', 'max_points'), ('首次載入等待（秒）', 'initial_wait'),
                    ('傳送後截圖等待（秒）', 'screenshot_wait'), ('每點最短週期（秒）', 'interval'), ('辨識差異門檻（越小越嚴格）', 'threshold')], 1):
            self.entry(scan, label, key, row)
        ttk.Label(scan, text='啟動後開啟搜尋地圖與截圖介面，再按「開始搜尋」。可在搜尋介面切換原本提前傳送或逐點等待截圖。', wraplength=800).grid(row=6, column=0, columnspan=3, sticky='w', pady=8)
        self.entry(fly, '移動速度（km/h）', 'speed', 0)
        ttk.Label(fly, text='啟動後開啟地圖視窗。\n在地圖按右鍵加入標點，或匯入路線，再按「開始／繼續」。\n地圖內可隨時調整速度、傳送間隔與停留時間，並開啟循環移動。', wraplength=780).grid(row=1, column=0, columnspan=3, sticky='w', pady=16)
        ttk.Label(generate, text='資料來源').grid(row=0, column=0, sticky='w')
        ttk.Combobox(generate, textvariable=self.fields['source'], values=['世界城市', '印度村莊'], state='readonly').grid(row=0, column=1, sticky='w')
        self.entry(generate, '國家（英文，以逗號分隔）', 'countries', 1, width=60)
        ttk.Label(generate, text='使用「傳送與辨識」頁籤的點數上限。另存新檔後自動選用；印度資料沿用經度 +0.001 偏移。', wraplength=780).grid(row=2, column=0, columnspan=3, sticky='w', pady=12)
        bar = ttk.Frame(body)
        bar.pack(fill='x', pady=8)
        self.start_button = ttk.Button(bar, text='▶ 啟動所選模式', command=self.start, state='disabled')
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(bar, text='■ 停止並還原定位', command=self.stop, state='disabled')
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
        enabled = not self.busy and not self.closing and (self.device_connected or self.tabs.index(self.tabs.select()) == 2)
        self.start_button.configure(state='normal' if enabled else 'disabled')

    def monitor_devices(self):
        while not self.monitor_stop.is_set():
            try:
                ids = device_ids()
                connected = len(ids) == 1
                text = ('已偵測到 1 台 iOS 裝置 · 啟動時檢查信任、開發者模式與通道' if connected else
                        '未連接 iOS 裝置 · 請接上資料線並解鎖裝置' if not ids else
                        '連接多台裝置 · 請只保留要操作的一台')
            except Exception as exc:
                connected, text = False, str(exc)
            self.events.put(('device', (connected, text)))
            self.monitor_stop.wait(4)

    def entry(self, parent, label, key, row, width=18):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', pady=4, padx=(0, 16))
        ttk.Entry(parent, textvariable=self.fields[key], width=width).grid(row=row, column=1, sticky='w', pady=4)

    def browse(self):
        path = filedialog.askopenfilename(initialdir=BASE, filetypes=[('座標文字檔', '*.txt'), ('所有檔案', '*.*')])
        if path:
            self.fields['waypoints'].set(path)

    def results(self):
        folder = BASE / 'found_targets'
        folder.mkdir(exist_ok=True)
        os.startfile(folder)

    def emit(self, text):
        self.events.put(('log', text))

    def spawn(self, args, env=None):
        environment = os.environ.copy()
        environment.update(PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8', PATH=str(PYTHON.parent) + os.pathsep + environment.get('PATH', ''))
        environment.update(env or {})
        process = subprocess.Popen([str(PYTHON), '-u', *args], cwd=BASE, env=environment,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     encoding='utf-8', errors='replace', creationflags=HIDDEN)
        def read():
            for line in process.stdout:
                if '"GET / HTTP/1.1" 200 OK' not in line:
                    self.emit(line.rstrip())
            process.stdout.close()
        threading.Thread(target=read, daemon=True).start()
        return process

    def start(self):
        if self.busy:
            return
        mode = self.tabs.index(self.tabs.select())
        if mode != 2 and not self.device_connected:
            self.status.set('請先連接一台 iOS 裝置，再啟動。')
            return
        values = {key: value.get() for key, value in self.fields.items()}
        try:
            maximum = int(values['max_points'])
            if maximum < 1:
                raise ValueError('點數上限須大於 0。')
            config = dict(waypoints=values['waypoints'], max_points=maximum)
            for key in ('initial_wait', 'screenshot_wait', 'interval', 'threshold', 'speed'):
                config[key] = float(values[key])
                if not math.isfinite(config[key]) or config[key] <= 0:
                    raise ValueError('等待時間、速度及門檻須為大於 0 的數字。')
            if config['threshold'] > 1:
                raise ValueError('辨識門檻須介於 0 與 1。')
            if mode == 0:
                count = len(read_waypoints(config['waypoints']))
                if not list((BASE / 'mushroom_pics').glob('*.png')):
                    raise ValueError('mushroom_pics 資料夾沒有 PNG 範本。')
                self.emit(f'已驗證 {count} 個座標，本次掃描 {min(count, maximum)} 個。')
            if mode == 2:
                output = filedialog.asksaveasfilename(initialdir=BASE, initialfile='waypoints_new.txt', defaultextension='.txt')
                if not output:
                    return
                values['output'] = output
            SETTINGS.write_text(json.dumps({k: v.get() for k, v in self.fields.items()}, ensure_ascii=False, indent=2), encoding='utf-8')
        except (ValueError, OSError) as exc:
            messagebox.showerror('請檢查設定', str(exc))
            return
        self.busy = True
        self.cancel.clear()
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.status.set('準備啟動…')
        threading.Thread(target=self.run, args=(mode, config, values), daemon=True).start()

    def connect(self):
        ids = device_ids()
        if len(ids) != 1:
            raise RuntimeError('未連接裝置或連接多台裝置；請只連接一台 iOS 裝置後重試。')
        self.events.put(('status', '準備開發者映像 · 請解鎖裝置並確認信任與開發者模式'))
        mount = self.spawn(['-m', 'pymobiledevice3', 'mounter', 'auto-mount'])
        deadline = time.monotonic() + 90
        try:
            while mount.poll() is None:
                if self.cancel.wait(.2):
                    return False
                if time.monotonic() >= deadline:
                    raise RuntimeError('開發者映像準備逾時；請檢查網路、解鎖與信任配對後重試。')
            if mount.returncode:
                raise RuntimeError('開發者映像掛載失敗；請確認已信任電腦、開啟開發者模式，並查看上方錯誤。')
        finally:
            kill_tree(mount)
        if self.cancel.is_set():
            return False
        try:
            data = tunnels()
            self.emit('使用已存在的連線服務。')
        except Exception:
            self.emit('正在啟動裝置連線服務…')
            self.tunnel = self.spawn(['-m', 'pymobiledevice3', 'remote', 'tunneld'])
        deadline = time.monotonic() + 30
        while not self.cancel.is_set() and time.monotonic() < deadline:
            if self.tunnel and self.tunnel.poll() is not None:
                raise RuntimeError('連線服務已退出，請查看執行紀錄。')
            try:
                data = tunnels()
            except Exception:
                data = {}
            connected = [key for key, details in data.items() if details]
            if len(connected) > 1:
                raise RuntimeError('目前連接多台裝置，請只保留要操作的一台。')
            if len(connected) == 1:
                if connected[0] != ids[0]:
                    raise RuntimeError('連線通道與目前裝置不符，請重啟 tunneld 後重試。')
                self.emit('裝置通道已就緒。')
                return True
            self.events.put(('status', '等待 iPhone · 請解鎖、信任電腦並開啟開發者模式'))
            self.cancel.wait(1)
        if self.cancel.is_set():
            return False
        raise RuntimeError('30 秒內未建立裝置通道。請檢查 USB、信任與開發者模式；若剛掛載映像，可重啟 tunneld 後重試。')

    def run(self, mode, config, values):
        used_device = False
        outcome = '已完成'
        try:
            if mode == 2:
                self.process = self.spawn(['-m', 'pikmin.coordinate_job'], {'PIKMIN_GENERATE_CONFIG': json.dumps(values)})
            else:
                if not self.connect() or self.cancel.is_set():
                    return
                used_device = True
                self.process = self.spawn(['main.py' if mode == 0 else 'fly.py'],
                    {'PIKMIN_SCAN_CONFIG': json.dumps(config), 'PIKMIN_SPEED': str(config['speed'])})
            self.events.put(('status', '執行中 · ' + ['傳送與辨識', '請在地圖視窗操作', '產生座標'][mode]))
            while self.process.poll() is None:
                if self.cancel.wait(0.2):
                    kill_tree(self.process)
                    break
                if used_device and self.tunnel and self.tunnel.poll() is not None:
                    raise RuntimeError('裝置連線服務中斷。')
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
                if used_device:
                    self.events.put(('status', '正在還原定位…'))
                    clear = self.spawn(['-m', 'pymobiledevice3', 'developer', 'dvt', 'simulate-location', 'clear'])
                    try:
                        code = clear.wait(timeout=20)
                        if code:
                            outcome += ' · 定位還原失敗'
                        else:
                            self.emit('已送出還原定位指令。')
                    except subprocess.TimeoutExpired:
                        kill_tree(clear)
                        outcome += ' · 定位還原逾時'
            except Exception as exc:
                outcome += ' · 清理失敗'
                self.emit(str(exc))
            finally:
                try:
                    kill_tree(self.tunnel)
                except Exception as exc:
                    self.emit(f'連線服務關閉失敗：{exc}')
                self.process = self.tunnel = None
                self.events.put(('done', '已停止' if self.cancel.is_set() and outcome == '已完成' else outcome))

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
                self.device_connected, text = value
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
