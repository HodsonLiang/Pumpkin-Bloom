"""Identified, cached, bounded requests to the OSM raster tile service."""
import sqlite3
from contextlib import closing
import threading
import time
from pathlib import Path
import requests
from PIL import Image
import io

TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
USER_AGENT = 'Pumpkin-Bloom/1.0 (+https://github.com/HodsonLiang/Pumpkin-Bloom)'
TTL = 7*24*3600


class TileError(RuntimeError):
    pass


class TileClient:
    def __init__(self, cache, session=None):
        self.cache = Path(cache)
        self.session = session or requests.Session()
        self.lock = threading.Lock()
        self.blocked = False
        self.retry_after = 0.

    def fetch(self, z, x, y):
        url = TILE_URL.format(z=z, x=x % (2**z), y=y)
        with self.lock:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.cache, timeout=10)) as db, db:
                db.execute('CREATE TABLE IF NOT EXISTS tiles (url TEXT PRIMARY KEY, body BLOB, fetched REAL, etag TEXT, modified TEXT)')
                row = db.execute('SELECT body, fetched, etag, modified FROM tiles WHERE url=?', (url,)).fetchone()
                if row and time.time()-row[1] < TTL:
                    return row[0]
                if self.blocked:
                    if row:
                        return row[0]
                    raise TileError('地圖服務拒絕存取，已停止下載。請稍後按「重試地圖」。')
                if time.time() < self.retry_after:
                    if row:
                        return row[0]
                    raise TileError('地圖連線暫時無法使用，稍後可重試。')
                headers = {'User-Agent': USER_AGENT}
                if row:
                    if row[2]:
                        headers['If-None-Match'] = row[2]
                    if row[3]:
                        headers['If-Modified-Since'] = row[3]
                try:
                    with self.session.get(url, headers=headers, timeout=(5, 15)) as response:
                        if response.status_code in (403, 429):
                            self.blocked = True
                            raise TileError(f'地圖服務回傳 {response.status_code}，已停止下載；不會將錯誤圖片當作地圖。')
                        if response.status_code == 304 and row:
                            db.execute('UPDATE tiles SET fetched=? WHERE url=?', (time.time(), url))
                            return row[0]
                        response.raise_for_status()
                        content = response.content
                        with Image.open(io.BytesIO(content)) as picture:
                            if picture.size != (256, 256):
                                raise TileError('圖磚尺寸不正確。')
                            picture.verify()
                        db.execute('INSERT OR REPLACE INTO tiles VALUES (?,?,?,?,?)',
                                   (url, content, time.time(), response.headers.get('ETag'), response.headers.get('Last-Modified')))
                        return content
                except (requests.RequestException, OSError, ValueError, TileError) as exc:
                    self.retry_after = time.time()+60
                    if row:
                        return row[0]
                    raise TileError(str(exc)) from exc

    def retry(self):
        self.blocked = False
        self.retry_after = 0.
