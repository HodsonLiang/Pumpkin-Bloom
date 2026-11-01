"""Horizontal world wrapping for TkinterMapView, including markers and paths."""
import tkintermapview
from tkinter import ttk
from PIL import Image, ImageTk
import io
import sqlite3
import math
import threading
import time
import webbrowser
from .map_tiles import TileClient, TileError, TILE_URL
from .storage import DATA
from tkintermapview.canvas_position_marker import CanvasPositionMarker
from tkintermapview.canvas_path import CanvasPath


def longitude(value):
    return (value+180) % 360-180


def near(value, reference):
    return reference+longitude(value-reference)


class WorldMarker(CanvasPositionMarker):
    def delete(self):
        # The upstream method calls canvas.update(), re-entering event handlers
        # in the middle of a gallery filter/delete operation.
        if self in self.map_widget.canvas_marker_list:
            self.map_widget.canvas_marker_list.remove(self)
        for attribute in ('polygon', 'big_circle', 'canvas_text', 'canvas_icon', 'canvas_image'):
            item = getattr(self, attribute)
            if item is not None:
                self.map_widget.canvas.delete(item)
            setattr(self, attribute, None)
        self.deleted = True

    def get_canvas_pos(self, position):
        return super().get_canvas_pos((position[0], near(position[1], self.map_widget.center_longitude())))


class WorldPath(CanvasPath):
    def draw(self, move=False):
        # Unwrap successive segments; a 179 -> -179 route is two degrees long.
        original = self.position_list
        reference = self.map_widget.center_longitude()
        unwrapped = []
        for lat, lon in original:
            reference = near(lon, reference)
            unwrapped.append((lat, reference))
        self.position_list = unwrapped
        try:
            super().draw(move=False)
        finally:
            self.position_list = original


class WorldMap(tkintermapview.TkinterMapView):
    def __init__(self, *args, **kwargs):
        self.tile_client = TileClient(DATA/'cache'/'maps'/'osm.sqlite3')
        self.loader_lock = threading.Lock()
        self.network_visible = False
        self.tile_error = ''
        super().__init__(*args, **kwargs)
        self.tile_server = TILE_URL
        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, sticky='ew')
        credit = ttk.Label(bar, text='© OpenStreetMap contributors', cursor='hand2')
        credit.pack(side='right')
        credit.bind('<Button-1>', lambda _: webbrowser.open('https://www.openstreetmap.org/copyright'))
        self.map_status = ttk.Label(bar, text='', wraplength=440)
        self.map_status.pack(side='left', fill='x', expand=True)
        ttk.Button(bar, text='重試地圖', command=self.retry_tiles).pack(side='right', padx=4)

    def pre_cache(self):
        # OSM permits viewport requests, not the upstream 17x17 prefetch area.
        return

    def retry_tiles(self):
        self.tile_client.retry()
        self.tile_error = ''
        self.tile_image_cache.clear()
        self.draw_initial_array()

    def visible_task(self, zoom, x, y, tile):
        return (self.network_visible and zoom == round(self.zoom)
                and tile.tile_name_position == (x, y)
                and math.floor(self.upper_left_tile_pos[0]) <= x <= math.floor(self.lower_right_tile_pos[0])
                and math.floor(self.upper_left_tile_pos[1]) <= y <= math.floor(self.lower_right_tile_pos[1]))

    def load_images_background(self):
        # The upstream constructor starts 25 threads; retain only one consumer.
        if not self.loader_lock.acquire(blocking=False):
            return
        try:
            while self.running:
                if not self.image_load_queue_tasks or not self.network_visible:
                    time.sleep(.05)
                    continue
                try:
                    task, tile = self.image_load_queue_tasks.pop()
                except IndexError:
                    continue
                zoom, x, y = task
                if not self.visible_task(zoom, x, y, tile):
                    continue
                image = self.request_image(zoom, x, y)
                self.image_load_queue_results.append((task, tile, image))
        finally:
            self.loader_lock.release()

    def update_canvas_tile_images(self):
        self.network_visible = bool(self.winfo_viewable())
        while self.image_load_queue_results and self.running:
            (zoom, x, y), tile, content = self.image_load_queue_results.pop(0)
            if not self.visible_task(zoom, x, y, tile):
                continue
            if isinstance(content, bytes):
                with Image.open(io.BytesIO(content)) as source:
                    picture = ImageTk.PhotoImage(source, master=self)
                self.tile_image_cache[(zoom, x % (2**zoom), y)] = picture
            else:
                picture = self.empty_tile_image
            tile.set_image(picture)
            while len(self.tile_image_cache) > 512:
                self.tile_image_cache.pop(next(iter(self.tile_image_cache)))
        if hasattr(self, 'map_status'):
            self.map_status.configure(text=self.tile_error)
        if self.running:
            self.after(50, self.update_canvas_tile_images)

    def center_longitude(self):
        return ((self.upper_left_tile_pos[0]+self.lower_right_tile_pos[0])/2)/(2**round(self.zoom))*360-180

    def check_map_border_crossing(self):
        # Only the latitude limits apply. Tile X is allowed outside one world.
        shift = max(0, -self.upper_left_tile_pos[1])
        shift -= max(0, self.lower_right_tile_pos[1]-2**round(self.zoom))
        self.upper_left_tile_pos = self.upper_left_tile_pos[0], self.upper_left_tile_pos[1]+shift
        self.lower_right_tile_pos = self.lower_right_tile_pos[0], self.lower_right_tile_pos[1]+shift

    def request_image(self, zoom, x, y, db_cursor=None):
        if self.use_database_only or not 0 <= y < 2**zoom:
            return None
        try:
            return self.tile_client.fetch(zoom, x, y)
        except (TileError, OSError, sqlite3.Error) as exc:
            self.tile_error = '地圖載入失敗：'+str(exc)
            return None

    def get_tile_image_from_cache(self, zoom, x, y):
        return self.tile_image_cache.get((zoom, x % (2**zoom), y), False)

    def convert_canvas_coords_to_decimal_coords(self, x, y):
        lat, lon = super().convert_canvas_coords_to_decimal_coords(x, y)
        return lat, longitude(lon)

    def set_position(self, deg_x, deg_y, **kwargs):
        return super().set_position(deg_x, near(deg_y, self.center_longitude()), **kwargs)

    def set_marker(self, deg_x, deg_y, text=None, **kwargs):
        marker = WorldMarker(self, (deg_x, longitude(deg_y)), text=text, **kwargs)
        marker.draw()
        self.canvas_marker_list.append(marker)
        return marker

    def set_path(self, position_list, **kwargs):
        path = WorldPath(self, position_list, **kwargs)
        path.draw()
        self.canvas_path_list.append(path)
        return path
