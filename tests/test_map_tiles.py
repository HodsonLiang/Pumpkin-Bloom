import io
from pathlib import Path
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import Mock, MagicMock
from PIL import Image
from pikmin.map_tiles import TileClient, TileError, USER_AGENT, TTL


class TileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Mock()
        self.cache = Path(self.temp.name)/'tiles.sqlite3'
        self.client = TileClient(self.cache, self.session)
        stream = io.BytesIO()
        Image.new('RGB', (256, 256), 'green').save(stream, format='PNG')
        self.png = stream.getvalue()

    def response(self, status=200):
        response = MagicMock(status_code=status, content=self.png)
        response.headers = {'ETag': 'one', 'Last-Modified': 'Wed, 01 Jan 2025 00:00:00 GMT'}
        response.__enter__.return_value = response
        self.session.get.return_value = response
        return response

    def test_identified_canonical_url_wraps_and_reuses_disk_cache(self):
        self.response()
        self.assertEqual(self.client.fetch(2, -1, 1), self.png)
        args, kwargs = self.session.get.call_args
        self.assertEqual(args[0], 'https://tile.openstreetmap.org/2/3/1.png')
        self.assertEqual(kwargs['headers']['User-Agent'], USER_AGENT)
        self.assertEqual(TileClient(self.cache, self.session).fetch(2, 3, 1), self.png)
        self.session.get.assert_called_once()

    def test_error_png_is_not_displayed_or_cached_and_stops_requests(self):
        for code in (403, 429):
            self.client.retry()
            self.response(code)
            with self.assertRaises(TileError):
                self.client.fetch(0, 0, 0)
            count = self.session.get.call_count
            with self.assertRaises(TileError):
                self.client.fetch(1, 0, 0)
            self.assertEqual(self.session.get.call_count, count)
            with closing(sqlite3.connect(self.cache)) as db, db:
                self.assertEqual(db.execute('SELECT count(*) FROM tiles').fetchone()[0], 0)

    def test_expired_cache_sends_conditional_headers_and_accepts_304(self):
        self.response()
        self.client.fetch(0, 0, 0)
        with closing(sqlite3.connect(self.cache)) as db, db:
            db.execute('UPDATE tiles SET fetched=fetched-?', (TTL+1,))
        self.response(304)
        self.assertEqual(self.client.fetch(0, 0, 0), self.png)
        headers = self.session.get.call_args.kwargs['headers']
        self.assertEqual(headers['If-None-Match'], 'one')
        self.assertIn('If-Modified-Since', headers)

    def test_invalid_image_is_not_cached(self):
        response = self.response()
        response.content = b'not an image'
        with self.assertRaises(TileError):
            self.client.fetch(0, 0, 0)
        with closing(sqlite3.connect(self.cache)) as db, db:
            self.assertEqual(db.execute('SELECT count(*) FROM tiles').fetchone()[0], 0)
