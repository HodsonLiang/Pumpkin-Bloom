"""Lazy connection preparation and Tk-safe device transition notifications."""
import queue
import threading
from tkinter import messagebox


class DeviceSession:
    def __init__(self, root, disconnected=lambda: None, on_event=lambda event: None):
        self.root, self.disconnected = root, disconnected
        self.on_event = on_event
        self.events = queue.Queue()
        self.closed = threading.Event()
        self.backend = None
        self.pending = False
        self.request_generation = None
        self.queued = None
        self.prepare_cancel = threading.Event()
        self.generation = 0
        self.last = None
        self.prepared_id = None
        threading.Thread(target=self.monitor, daemon=True).start()
        root.after(200, self.poll)

    def monitor(self):
        from .device_backend import device_ids
        while not self.closed.is_set():
            try:
                ids = tuple(device_ids())
            except Exception:
                ids = ()
            self.events.put(('devices', ids))
            self.closed.wait(4)

    def ensure(self, callback, failed=lambda: None):
        if self.closed.is_set():
            return
        if self.pending:
            if self.request_generation != self.generation:
                self.queued = (callback, failed)
                return
            failed()
            messagebox.showinfo('連線準備中', '前一個連線檢查尚未結束，請稍候再試。', parent=self.root)
            return
        self.pending = True
        generation = self.generation
        self.request_generation = generation
        self.prepare_cancel = threading.Event()
        def work():
            from .device_backend import DeviceBackend, device_ids, tunnels
            try:
                ids = device_ids()
                if len(ids) != 1:
                    raise RuntimeError('請連接一台 iOS 裝置、解鎖並信任電腦後再操作。')
                try:
                    ready = [key for key, value in tunnels().items() if value] == ids
                except Exception:
                    ready = False
                if not ready or self.prepared_id != ids[0]:
                    if self.backend is None:
                        self.backend = DeviceBackend(self.prepare_cancel)
                    else:
                        self.backend.cancel = self.prepare_cancel
                    if not self.backend.connect():
                        raise RuntimeError('裝置連線已取消。')
                if device_ids() != ids:
                    raise RuntimeError('準備期間裝置已變更，請重新開始。')
                self.events.put(('ready', (generation, callback, failed, None, ids[0])))
            except Exception as exc:
                self.events.put(('ready', (generation, callback, failed, str(exc), None)))
        self.worker = threading.Thread(target=work)
        self.worker.start()

    def cancel_pending(self):
        self.generation += 1
        self.queued = None
        self.prepare_cancel.set()

    def poll(self):
        if self.closed.is_set():
            return
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'devices':
                if self.last is not None and value != self.last:
                    self.prepared_id = None
                    if self.last:
                        self.cancel_pending()
                        self.disconnected()
                    messagebox.showinfo('裝置連接狀態', '已連接裝置。' if len(value) == 1 else
                                        '裝置已斷開，或目前連接多台裝置。', parent=self.root)
                self.last = value
            else:
                generation, callback, failed, error, identifier = value
                self.pending = False
                if generation != self.generation:
                    # A cancelled request must never cancel a newer search.
                    queued, self.queued = self.queued, None
                    if queued:
                        self.ensure(*queued)
                    continue
                if error:
                    failed()
                    messagebox.showerror('裝置尚未就緒', error, parent=self.root)
                else:
                    self.prepared_id = identifier
                    self.last = (identifier,)
                    callback()
        if self.backend:
            # Keep the original diagnostic output available in the parent launcher.
            while not self.backend.events.empty():
                kind, text = self.backend.events.get_nowait()
                if kind == 'log':
                    print(text, flush=True)
                    self.on_event(dict(kind='log', text=text))
                elif kind == 'status' and self.pending and self.request_generation == self.generation:
                    self.on_event(dict(kind='status', text=text))
        self.root.after(200, self.poll)

    def close(self):
        self.closed.set()
        self.cancel_pending()
        def cleanup():
            from .device_backend import kill_tree
            worker = getattr(self, 'worker', None)
            if worker:
                worker.join()
            if self.backend:
                kill_tree(self.backend.tunnel)
        threading.Thread(target=cleanup).start()
