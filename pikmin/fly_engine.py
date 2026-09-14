"""Single-owner route state and serialized device commands; no Tk calls here."""
import math
import queue
import subprocess
import sys
import threading
import time


def validate_point(lat, lon):
    if not (math.isfinite(lat) and math.isfinite(lon) and -85 <= lat <= 85 and -180 <= lon <= 180):
        raise ValueError('地圖座標範圍：緯度 -85～85、經度 -180～180。')
    return lat, lon


def distance(a, b):
    p, q = map(math.radians, (a[0], b[0]))
    h = math.sin((q-p)/2)**2 + math.cos(p)*math.cos(q)*math.sin(math.radians(b[1]-a[1])/2)**2
    return 12742000 * math.asin(math.sqrt(min(1, max(0, h))))


def advance(a, b, meters):
    length = distance(a, b)
    if length <= meters or length < 0.001:
        return b
    angle = length / 6371000
    if abs(math.sin(angle)) < 1e-10:
        raise ValueError('兩點互為對跖點，請加入中途標點。')
    fraction = meters / length
    weights = math.sin((1-fraction)*angle)/math.sin(angle), math.sin(fraction*angle)/math.sin(angle)
    xyz = [0., 0., 0.]
    for point, weight in zip((a, b), weights):
        lat, lon = map(math.radians, point)
        xyz[0] += weight*math.cos(lat)*math.cos(lon)
        xyz[1] += weight*math.cos(lat)*math.sin(lon)
        xyz[2] += weight*math.sin(lat)
    return math.degrees(math.atan2(xyz[2], math.hypot(*xyz[:2]))), math.degrees(math.atan2(xyz[1], xyz[0]))


class Route:
    def __init__(self):
        self.position = (25.033964, 121.564468)
        self.points = []
        self.next_id = 1
        self.index = self.laps = 0
        self.running = self.loop = False
        self.speed, self.interval, self.dwell = 18., 2., 8.
        self.wait = self.elapsed = 0.

    def add(self, point):
        validate_point(*point)
        self.points.append((self.next_id, point))
        self.next_id += 1

    def clear(self):
        self.running = False
        self.points.clear()
        self.index = self.laps = 0
        self.wait = self.elapsed = 0.
        # Position and monotonically increasing IDs survive clearing.

    def start(self):
        if not self.points:
            raise ValueError('請先新增路線標點。')
        if self.index >= len(self.points):
            self.index = 0
            self.wait = self.elapsed = 0.
        self.running = True

    def arrive(self):
        self.index += 1
        self.wait = self.dwell
        if self.index == len(self.points):
            self.laps += 1
            if self.loop:
                self.index = 0
            else:
                self.running = False
                self.wait = 0.

    def tick(self, dt, send):
        if not self.running:
            return
        if self.wait > 0:
            used = min(dt, self.wait)
            self.wait -= used
            dt -= used
        self.elapsed += dt
        if self.wait > 0 or self.elapsed + 1e-9 < self.interval:
            return
        target = self.points[self.index][1]
        point = advance(self.position, target, self.speed/3.6*self.interval)
        send(point)
        self.position = point
        self.elapsed = 0.
        if distance(point, target) < 0.001:
            self.arrive()

    def remaining(self):
        if self.index >= len(self.points):
            return 0., 0.
        points = [self.position] + [p for _, p in self.points[self.index:]]
        lengths = [distance(a, b) for a, b in zip(points, points[1:])]
        steps = sum(max(1, math.ceil(length/(self.speed/3.6*self.interval))) for length in lengths)
        seconds = max(0, steps*self.interval-self.elapsed) + self.wait + max(0, len(lengths)-1)*self.dwell
        return sum(lengths), seconds


class Device:
    def __init__(self):
        self.process = None
        self.flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

    def release(self):
        if self.process:
            try:
                self.process.communicate(input=b'\n', timeout=0.5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
            self.process = None

    def send(self, point):
        self.release()
        self.process = subprocess.Popen([sys.executable, '-m', 'pymobiledevice3', 'developer', 'dvt',
            'simulate-location', 'set', '--', *map(str, point)], stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=self.flags)

    def reset(self):
        self.release()
        subprocess.run([sys.executable, '-m', 'pymobiledevice3', 'developer', 'dvt', 'simulate-location', 'clear'],
            check=True, capture_output=True, timeout=20, creationflags=self.flags)


class Controller(threading.Thread):
    def __init__(self, commands, updates):
        super().__init__(daemon=True)
        self.commands, self.updates = commands, updates
        self.route = Route()
        self.device = Device()
        self.status = '待命 · 地圖起點為台北預設座標，並非手機實際位置'
        self.closed = False

    def command(self, kind, value):
        r = self.route
        if kind == 'settings':
            speed, interval, dwell, loop = value
            if not all(map(math.isfinite, (speed, interval, dwell))) or not (0 < speed <= 1000 and 0.2 <= interval <= 3600 and 0 <= dwell <= 3600):
                raise ValueError('速度：大於 0～1000；間隔：0.2～3600；停留：0～3600。')
            r.speed, r.interval, r.dwell, r.loop = value
            r.elapsed = 0.
            r.wait = min(r.wait, r.dwell)
        elif kind == 'add':
            for point in value:
                r.add(point)
        elif kind == 'start':
            r.start()
            self.status = '移動中'
        elif kind == 'pause':
            r.running = False
            self.status = '已暫停 · 維持最後送出的定位'
        elif kind == 'clear':
            r.clear()
            self.status = '路線已清除 · 停留目前位置，等待新增標點'
        elif kind == 'teleport':
            r.running = False
            if r.index >= len(r.points):
                raise ValueError('沒有下一個標點。')
            point = r.points[r.index][1]
            self.device.send(point)
            r.position = point
            r.elapsed = 0.
            r.arrive()
            self.status = '已跳至下一點 · 按開始繼續移動'
        elif kind in ('reset', 'close'):
            r.running = False
            try:
                self.device.reset()
                self.status = '已送出還原定位指令 · 地圖仍顯示最後模擬座標'
            finally:
                if kind == 'close':
                    self.closed = True

    def snapshot(self):
        r = self.route
        length, seconds = r.remaining()
        return dict(position=r.position, points=list(r.points), index=r.index, running=r.running,
                    loop=r.loop, laps=r.laps, wait=r.wait, distance=length, seconds=seconds, status=self.status)

    def run(self):
        previous = time.monotonic()
        while not self.closed:
            try:
                processed = False
                while True:
                    try:
                        kind, value = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    self.command(kind, value)
                    processed = True
                    if self.closed:
                        break
                now = time.monotonic()
                dt = 0 if processed else min(now-previous, 1.)
                previous = now
                if not self.closed:
                    was_running = self.route.running
                    self.route.tick(dt, self.device.send)
                    if was_running and not self.route.running:
                        self.status = '本次路線已完成 · 定位停留終點'
                    if self.device.process and self.device.process.poll() is not None:
                        code = self.device.process.returncode
                        self.device.process = None
                        raise RuntimeError(f'定位指令已退出（代碼 {code}），請檢查連線服務。')
            except Exception as exc:
                self.route.running = False
                self.status = f'已停止：{exc}'
                print(self.status, flush=True)
            self.updates.put(self.snapshot())
            if not self.closed:
                time.sleep(0.05)
        self.updates.put({'closed': True, 'status': self.status})
