"""Interruptible scanning and background recognition, independent of Tk."""
from datetime import datetime
import json
import math
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from .fly_engine import Device
from .vision import check_image_has_target

BASE = Path(__file__).resolve().parent.parent
DEFAULTS = dict(waypoints=str(BASE/'waypoints.txt'), max_points=10000, start_index=1,
                initial_wait=12., screenshot_wait=5., interval=10., threshold=.058,
                timing='pipeline')


def prepare_config(values):
    config = {**DEFAULTS, **values}
    for key in ('max_points', 'start_index'):
        config[key] = int(str(config[key]))
        if config[key] < 1:
            raise ValueError('起始點與掃描點數須為正整數。')
    for key in ('initial_wait', 'screenshot_wait', 'interval', 'threshold'):
        config[key] = float(config[key])
        if not math.isfinite(config[key]) or config[key] <= 0:
            raise ValueError('等待時間、週期及辨識門檻須大於 0。')
    if config['threshold'] > 1:
        raise ValueError('辨識門檻不可大於 1。')
    if config['timing'] not in ('pipeline', 'sequential'):
        raise ValueError('截圖時序無效。')
    path = Path(config['waypoints']).expanduser()
    if not path.is_absolute():
        path = BASE/path
    points = []
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        try:
            lat, lon = map(float, line.split(','))
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError()
        except ValueError:
            raise ValueError(f'座標檔第 {number} 行無效，格式須為緯度,經度。') from None
        points.append((lat, lon))
    begin = config['start_index']-1
    if begin >= len(points):
        raise ValueError('起始點超出座標檔範圍，或檔案沒有座標。')
    config['waypoints'] = str(path.resolve())
    return config, points[begin:begin+config['max_points']]


class ScanDevice(Device):
    def check(self):
        if self.process and self.process.poll() is not None:
            code = self.process.returncode
            raise RuntimeError(f'定位指令已退出（代碼 {code}）。請確認 tunneld 與 iPhone 連線。')

    def capture(self, path):
        self.check()
        try:
            subprocess.run([sys.executable, '-m', 'pymobiledevice3', 'developer', 'dvt', 'screenshot', str(path)],
                           check=True, capture_output=True, timeout=15, creationflags=self.flags)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(exc.stderr.decode('utf-8', errors='replace')[-600:] or '截圖失敗') from exc
        if not path.is_file():
            raise RuntimeError('截圖指令未產生檔案。')


class Scanner(threading.Thread):
    def __init__(self, config, points, events, *, base=BASE, device=None, recognizer=None):
        super().__init__(daemon=True)
        self.config, self.points, self.events = config, points, events
        self.base = Path(base)
        self.device = device if device is not None else ScanDevice()
        self.recognizer = recognizer or check_image_has_target
        self.stop_event = threading.Event()
        self.tasks = queue.Queue(maxsize=3)
        self.session = datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8]
        self.folder = self.base/'scan_sessions'/self.session
        self.hits = self.processed = self.errors = 0
        self.captured = 0
        self.next_index = config['start_index']

    def emit(self, kind, **data):
        self.events.put(dict(kind=kind, **data))

    def wait(self, seconds):
        # Check failed GPS processes during loading, rather than blindly capturing.
        end = time.monotonic()+seconds
        while not self.stop_event.is_set():
            self.device.check()
            remaining = end-time.monotonic()
            if remaining <= 0:
                return True
            self.stop_event.wait(min(.2, remaining))
        return False

    def send_position(self, point):
        self.device.check()
        self.device.send(point)
        self.emit('position', point=point)

    def recognize(self):
        while True:
            task = self.tasks.get()
            if task is None:
                self.tasks.task_done()
                return
            path, point, index, stamp = task
            record = dict(index=index, lat=point[0], lon=point[1], timestamp=stamp,
                          timing=self.config['timing'], session=self.session)
            recognition_started = time.perf_counter()
            try:
                found, name = self.recognizer(str(path), str(self.base/'mushroom_pics'), threshold=self.config['threshold'])
                record.update(found=bool(found), target=name or '', path='')
                if found:
                    safe_name = Path(name or 'target').stem
                    destination = self.base/'found_targets'/f'{safe_name}_{point[0]:.6f}_{point[1]:.6f}_{self.session}_{index}.png'
                    path.replace(destination)
                    record['path'] = str(destination)
                    self.hits += 1
                else:
                    path.unlink(missing_ok=True)
            except Exception as exc:
                self.errors += 1
                record.update(found=False, target='', error=str(exc), path=str(path))
                self.emit('log', text=f'第 {index} 點辨識失敗，保留截圖：{exc}')
            record['recognition_seconds'] = round(time.perf_counter()-recognition_started, 3)
            self.emit('recognition', seconds=record['recognition_seconds'])
            if record['recognition_seconds'] >= self.config['interval']:
                self.emit('log', text=f"第 {index} 點辨識耗時 {record['recognition_seconds']:.2f} 秒，已達截圖週期；留意待辨識數是否持續增加。")
            try:
                with (self.folder/'results.jsonl').open('a', encoding='utf-8') as output:
                    output.write(json.dumps(record, ensure_ascii=False)+'\n')
            except OSError as exc:
                self.errors += 1
                self.emit('log', text=f'結果紀錄寫入失敗：{exc}')
            self.processed += 1
            self.emit('result', record=record, processed=self.processed, hits=self.hits, errors=self.errors)
            self.tasks.task_done()

    def run(self):
        worker = None
        outcome = '掃描完成'
        touched = False
        try:
            self.folder.mkdir(parents=True)
            (self.base/'found_targets').mkdir(exist_ok=True)
            (self.folder/'config.json').write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding='utf-8')
            if not list((self.base/'mushroom_pics').glob('*.png')):
                raise ValueError('mushroom_pics 沒有 PNG 辨識範本。')
            worker = threading.Thread(target=self.recognize, daemon=True)
            worker.start()
            self.emit('session', folder=str(self.folder), total=len(self.points))
            if self.stop_event.is_set():
                return
            touched = True
            self.emit('search', point=self.points[0], index=self.config['start_index'], ordinal=1)
            self.send_position(self.points[0])
            self.emit('status', text='等待第一個位置載入…')
            if not self.wait(self.config['initial_wait']):
                return
            for offset, point in enumerate(self.points):
                if self.stop_event.is_set():
                    break
                index = self.config['start_index']+offset
                start = time.monotonic()
                self.emit('search', point=point, index=index, ordinal=offset+1)
                self.emit('status', text=f'搜尋第 {index} 點 · 等待畫面載入')
                if self.config['timing'] == 'pipeline':
                    if offset+1 < len(self.points):
                        self.send_position(self.points[offset+1])
                elif offset:
                    self.send_position(point)
                if not self.wait(self.config['screenshot_wait']):
                    break
                path = self.folder/f'capture_{index}.png'
                stamp = datetime.now().isoformat(timespec='seconds')
                self.emit('status', text=f'第 {index} 點 · 截圖中')
                try:
                    self.device.capture(path)
                    # Immutable bytes let the UI display screenshots even after rename/delete.
                    content = path.read_bytes()
                    shutil.copyfile(path, self.folder/'latest.png')
                    self.emit('screenshot', content=content, point=point, index=index, timestamp=stamp,
                              path=str(self.folder/'latest.png'))
                    task = (path, point, index, stamp)
                    # Bounded backlog: no unbounded screenshots or image memory growth.
                    while True:
                        try:
                            self.tasks.put(task, timeout=.2)
                            self.captured += 1
                            break
                        except queue.Full:
                            if not worker.is_alive():
                                raise RuntimeError('辨識執行緒已停止。')
                except Exception as exc:
                    self.errors += 1
                    self.emit('log', text=f'第 {index} 點截圖失敗：{exc}')
                    self.emit('capture_error', index=index, errors=self.errors)
                self.next_index = index+1
                self.emit('progress', completed=offset+1, total=len(self.points), next_index=self.next_index, captured=self.captured)
                if offset+1 < len(self.points) and not self.wait(max(0, self.config['interval']-(time.monotonic()-start))):
                    break
        except Exception as exc:
            outcome = f'掃描失敗：{exc}'
            self.emit('log', text=outcome)
        finally:
            if self.stop_event.is_set() and outcome == '掃描完成':
                outcome = '已停止掃描'
            # Clear location before draining potentially expensive recognition work.
            if touched:
                self.emit('status', text='停止移動並還原定位…')
                try:
                    self.device.reset()
                except Exception as exc:
                    outcome += ' · 定位還原失敗'
                    self.emit('log', text=f'定位還原失敗：{exc}')
            if worker:
                self.emit('status', text='等待已截取圖片辨識完成…')
                self.tasks.put(None)
                worker.join()
            self.emit('done', text=outcome, next_index=self.next_index, hits=self.hits, errors=self.errors)
