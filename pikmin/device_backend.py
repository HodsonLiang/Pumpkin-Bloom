"""Shared Windows device discovery and bounded tunnel preparation."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import urllib.request
BASE = Path(__file__).resolve().parent.parent
PYTHON = Path(sys.executable)
HIDDEN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

def device_ids():
    result = subprocess.run([str(PYTHON), '-m', 'pikmin.device_cli', 'usbmux', 'list', '--simple'],
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


def tunnels():
    from pymobiledevice3.tunneld.api import TUNNELD_DEFAULT_ADDRESS
    host, port = TUNNELD_DEFAULT_ADDRESS
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://{host}:{port}/', timeout=2) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise ValueError('連線服務回傳格式錯誤')
    return data


def developer_image_mounted():
    result = subprocess.run([str(PYTHON), '-m', 'pikmin.device_cli', 'mounter', 'list'],
                            capture_output=True, text=True, encoding='utf-8', errors='replace',
                            timeout=10, creationflags=HIDDEN)
    if result.returncode:
        raise RuntimeError('無法檢查開發者映像：'+(result.stderr or result.stdout)[-600:])
    try:
        images = json.loads(result.stdout)
        if not isinstance(images, list):
            raise ValueError()
        return any(image.get('IsMounted') is True and
                   (image.get('MountPath') == '/System/Developer' or
                    image.get('PersonalizedImageType') == 'DeveloperDiskImage' or
                    image.get('DiskImageType') == 'Developer') for image in images)
    except (ValueError, AttributeError):
        raise RuntimeError('開發者映像查詢回傳格式錯誤。') from None


def kill_tree(process):
    if process and process.poll() is None:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       capture_output=True, creationflags=HIDDEN, timeout=15)
        process.wait(timeout=5)


class ProcessRunner:
    """Shared child-process output handling for the launcher and device setup."""
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


class DeviceBackend(ProcessRunner):
    def __init__(self, cancel=None):
        self.events = queue.Queue()
        self.cancel = cancel or threading.Event()
        self.process = self.tunnel = None

    def connect(self):
        ids = device_ids()
        if len(ids) != 1:
            raise RuntimeError('未連接裝置或連接多台裝置；請只連接一台 iOS 裝置後重試。')
        self.events.put(('status', '檢查已掛載的開發者映像…'))
        if developer_image_mounted():
            self.emit('開發者映像已掛載，略過下載與重複掛載。')
        else:
            self.events.put(('status', '準備開發者映像 · 可能需要下載，最長等待 90 秒'))
            mount = self.spawn(['-m', 'pikmin.device_cli', 'mounter', 'auto-mount'])
            deadline = time.monotonic() + 90
            try:
                while mount.poll() is None:
                    if self.cancel.wait(.2):
                        return False
                    if time.monotonic() >= deadline:
                        raise RuntimeError('開發者映像準備逾時；請檢查網路、解鎖與信任配對後重試。')
                if mount.returncode or not developer_image_mounted():
                    raise RuntimeError('開發者映像準備失敗；請查看原始錯誤，並檢查網路、解鎖與信任配對。')
            finally:
                kill_tree(mount)
        if self.cancel.is_set():
            return False
        try:
            data = tunnels()
            self.emit('使用已存在的連線服務。')
        except Exception:
            self.emit('正在啟動裝置連線服務…')
            self.tunnel = self.spawn(['-m', 'pikmin.device_cli', 'remote', 'tunneld'])
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

