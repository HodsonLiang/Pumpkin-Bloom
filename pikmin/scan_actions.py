"""History/gallery and serialized manual device operations for ScanApp."""
from concurrent.futures import ThreadPoolExecutor
import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from .scan_engine import BASE, ScanDevice
from .target_history import validate_coords, read_history, path_key, trash_target


class ScanActions:
    def init_actions(self):
        self.manual_device = ScanDevice()
        self.manual_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='manual-gps')
        self.manual_busy = self.manual_active = False
        self.pending_teleport = None
        self.pending_start = self.pending_reset = False
        self.history_busy = False
        self.icons = {}
        self.known_paths = set()
        self.result_folder = BASE/'found_targets'

    def icon_for(self, target=None):
        if not target:
            return None
        key = Path(target).stem.casefold()
        if key not in self.icons:
            candidates = sorted((BASE/'mushroom_pics').glob('*.png'))
            path = next((p for p in candidates if p.stem.casefold() == key), None)
            self.icons[key] = None
            if path:
                try:
                    with Image.open(path) as source:
                        picture = source.convert('RGBA')
                        bounds = picture.getbbox()
                        if bounds:
                            picture = picture.crop(bounds)
                        picture.thumbnail((40, 40), Image.Resampling.LANCZOS)
                        self.icons[key] = ImageTk.PhotoImage(picture, master=self.root)
                except (OSError, ValueError):
                    pass
        return self.icons[key]

    def manual_bar(self, parent):
        bar = ttk.Frame(parent)
        bar.pack(fill='x', pady=(6, 0))
        ttk.Label(bar, text='手動傳送　緯度').pack(side='left')
        self.teleport_lat, self.teleport_lon = tk.StringVar(), tk.StringVar()
        ttk.Entry(bar, textvariable=self.teleport_lat, width=14).pack(side='left', padx=4)
        ttk.Label(bar, text='經度').pack(side='left')
        ttk.Entry(bar, textvariable=self.teleport_lon, width=14).pack(side='left', padx=4)
        ttk.Button(bar, text='傳送到輸入座標', command=self.teleport_input).pack(side='left', padx=4)
        ttk.Label(bar, text='掃描中會先停止收尾；裝置定位約 8 秒後更新。').pack(side='left', padx=8)

    def teleport_input(self):
        try:
            self.request_teleport(validate_coords(self.teleport_lat.get(), self.teleport_lon.get()))
        except ValueError as exc:
            messagebox.showerror('座標無效', str(exc))

    def teleport_selected(self):
        selection = self.table.selection()
        if len(selection) != 1:
            messagebox.showinfo('選擇目標', '請只選一個要傳送的目標。')
            return
        record = self.records[int(selection[0])]
        self.request_teleport((record['lat'], record['lon']))

    def request_teleport(self, point):
        if self.closing:
            return
        try:
            self.pending_teleport = validate_coords(*point)
        except ValueError as exc:
            messagebox.showerror('座標無效', str(exc))
            return
        self.pending_start = self.pending_reset = False
        if self.active:
            self.scanner.stop_event.set()
            self.status.set('先停止掃描並完成辨識收尾，接著傳送到指定位置…')
        elif not self.manual_busy:
            self.dispatch_teleport()

    def dispatch_teleport(self):
        point, self.pending_teleport = self.pending_teleport, None
        if point is not None:
            self.run_manual('set', point)

    def run_manual(self, operation, point=None):
        self.manual_busy = True
        if operation == 'set':
            self.manual_active = True  # A failed submission may still need cleanup.
        self.start_button.configure(state='disabled')
        self.resume_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.status.set('正在傳送定位…' if operation=='set' else '正在還原定位…')
        def work():
            error = None
            try:
                if operation == 'set':
                    self.manual_device.send(point)
                    # Detect early command import/connection failures; this is not GPS verification.
                    if self.manual_device.process:
                        try:
                            self.manual_device.process.wait(timeout=.4)
                        except subprocess.TimeoutExpired:
                            pass
                    self.manual_device.check()
                else:
                    self.manual_device.reset()
            except Exception as exc:
                error = str(exc)
            self.events.put(dict(kind='manual_done', operation=operation, point=point, error=error))
        self.manual_executor.submit(work)

    def handle_manual_done(self, event):
        self.manual_busy = False
        if event['operation'] == 'reset' and not event['error']:
            self.manual_active = False
        if event['error']:
            self.status.set('定位操作失敗，請查看執行紀錄')
            self.append_log(event['error'])
        elif event['operation'] == 'set':
            self.handle(dict(kind='position', point=event['point']))
            self.map_widget.set_position(max(-85, min(85, event['point'][0])), event['point'][1])
            self.status.set(f"已送出定位 {event['point'][0]:.6f}, {event['point'][1]:.6f} · 等待裝置更新")
        else:
            self.status.set('已送出還原定位指令')
        self.start_button.configure(state='normal')
        self.stop_button.configure(state='normal' if self.manual_active else 'disabled')
        if self.closing:
            if event['operation'] != 'reset':
                self.run_manual('reset')
            else:
                if event['error']:
                    messagebox.showwarning('定位還原失敗', event['error'])
                self.finish_close()
                return False
        elif self.pending_reset:
            self.pending_reset = False
            self.run_manual('reset')
        elif self.pending_teleport is not None:
            self.dispatch_teleport()
        elif self.pending_start:
            self.pending_start = False
            if not event['error']:
                self.start()
        else:
            self.start_button.configure(state='normal')
            self.stop_button.configure(state='normal' if self.manual_active else 'disabled')
            if self.next_index is not None and self.next_index < getattr(self, 'end_index', 0):
                self.resume_button.configure(state='normal')
        return True

    def finish_close(self):
        self.manual_executor.shutdown(wait=False)
        self.root.destroy()

    def add_record(self, record):
        key = path_key(record['path'])
        if key in self.known_paths:
            return
        self.known_paths.add(key)
        index = len(self.records)
        self.records.append(record)
        self.table.insert('', 'end', iid=str(index), values=(record['index'], record['target'], f"{record['lat']:.6f}, {record['lon']:.6f}", record['timestamp']))
        marker = self.map_widget.set_marker(max(-85, min(85, record['lat'])), record['lon'], text=f"#{record['index']} · {record['target']}",
            icon=self.icon_for(record['target']), icon_anchor='s', marker_color_outside='#338251',
            command=lambda _, i=index: self.marker_select(i))
        self.markers.append(marker)
        return index

    def load_history(self):
        if self.history_busy or self.closing:
            return
        self.history_busy = True
        self.load_button.configure(state='disabled')
        def work():
            try:
                records, skipped = read_history(self.result_folder)
                for begin in range(0, len(records), 50):
                    self.events.put(dict(kind='history', records=records[begin:begin+50]))
                self.events.put(dict(kind='history_done', text=f'歷史結果讀取 {len(records)} 筆；略過 {skipped} 個無法解析的檔案。重複結果不會重複加入。'))
            except Exception as exc:
                self.events.put(dict(kind='history_done', text=f'歷史結果讀取失敗：{exc}'))
        threading.Thread(target=work, daemon=True).start()

    def select_all(self):
        self.table.selection_set(self.table.get_children())

    def delete_selected(self):
        if self.history_busy:
            self.append_log('請等待歷史結果載入完成再刪除。')
            return
        selected = {int(i) for i in self.table.selection()}
        if not selected:
            return
        removed = set()
        for index in sorted(selected):
            record = self.records[index]
            try:
                trash_target(record['path'], self.result_folder)
                removed.add(index)
            except (OSError, ValueError) as exc:
                self.append_log(f"無法刪除 {Path(record['path']).name}：{exc}")
        if not removed:
            return
        remaining = [r for i, r in enumerate(self.records) if i not in removed]
        for marker in self.markers:
            marker.delete()
        self.markers.clear()
        self.records.clear()
        self.known_paths.clear()
        self.table.delete(*self.table.get_children())
        self.hit_preview.original = None
        self.hit_preview.title.set('命中截圖 · 點選下方結果')
        self.hit_preview.draw()
        for record in remaining:
            self.add_record(record)
        self.append_log(f'已刪除 {len(removed)} 筆目標；圖片移至 found_targets/.trash，可手動還原。')
