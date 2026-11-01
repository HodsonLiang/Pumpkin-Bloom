import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from pikmin import geoapify, storage
from pikmin.fly_engine import Route, Controller
import queue


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_versioned_files_and_legacy_import_preserve_original(self):
        source = self.folder/'old.txt'
        source.write_text('1,179.9\n2,-179.9\n', encoding='utf-8')
        with patch.object(storage, 'WAYPOINTS', self.folder/'library'):
            destination = storage.import_waypoints(source)
            self.assertEqual(storage.import_waypoints(source), destination)
            self.assertTrue(source.exists())
            self.assertEqual(storage.read_points(destination), [(1., 179.9), (2., -179.9)])
        for data in ({'format': 'pikmin.scan', 'version': 2, 'points': [[1, 2]]},
                     {'format': 'pikmin.scan', 'version': 1},
                     {'format': 'pikmin.scan', 'version': 1, 'points': [[None, 2]]}):
            destination.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(ValueError):
                storage.read_points(destination)

    def archive(self):
        path = self.folder/'ad.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('ad/place_city.ndjson', '{"location":[179.9,1]}\n{"location":[2,3]}\n')
            z.writestr('ad/place-village.ndjson', '{"location":[-179.9,2]}\n{"location":[179.9,1]}\nbad\n')
            z.writestr('ad/place-hamlet.ndjson', '{"location":[10,20]}\n')
            z.writestr('unrelated.ndjson', '{"location":[30,40]}\n')
        return path

    def test_geoapify_selection_cache_coordinates_and_deduplication(self):
        archive = self.archive()
        with patch('pikmin.geoapify.requests.get') as download:
            self.assertEqual(geoapify.get_archive('ad', self.folder, Mock()), archive)
            download.assert_not_called()
        output = self.folder/'points.pikscan'
        points = geoapify.generate(['AD'], ['city', 'village'], 99, output,
                                  cache=self.folder, progress=Mock(), rng=random.Random(1))
        self.assertEqual(set(points), {(1., 179.9), (3., 2.), (2., -179.9)})
        self.assertEqual(storage.read_points(output), points)
        self.assertEqual(json.loads(output.read_text())['locality_types'], ['city', 'village'])
        limited = geoapify.generate('ad', ['city', 'village'], 2, output,
                                   cache=self.folder, progress=Mock(), rng=random.Random(1))
        self.assertEqual(len(limited), 2)

    def test_download_failure_does_not_leave_partial_or_replace_cache(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = [b'not a zip']
        with patch('pikmin.geoapify.requests.get', return_value=response):
            with self.assertRaises(zipfile.BadZipFile):
                geoapify.get_archive('tw', self.folder, Mock())
        self.assertFalse((self.folder/'tw.zip').exists())
        self.assertFalse((self.folder/'tw.zip.part').exists())

    def test_unknown_start_teleports_first_then_moves(self):
        route = Route()
        self.assertIsNone(route.position)
        route.add((1., 179.9))
        route.add((1., -179.9))
        route.start()
        send = Mock()
        route.tick(route.interval, send)
        send.assert_called_once_with((1., 179.9))
        self.assertEqual(route.position, (1., 179.9))
        self.assertEqual(route.index, 1)
        self.assertLess(route.remaining()[0], 23000)

    def test_offline_close_does_not_touch_device(self):
        controller = Controller(queue.Queue(), queue.Queue())
        with patch.object(controller.device, 'reset') as reset:
            controller.command('close', None)
            reset.assert_not_called()

    def test_route_load_replaces_points_without_reusing_ids_or_moving(self):
        controller = Controller(queue.Queue(), queue.Queue())
        controller.command('add', [(1., 2.)])
        controller.command('start', None)
        with patch.object(controller.device, 'send') as send:
            controller.command('load', [(3., 4.), (5., 6.)])
            send.assert_not_called()
        self.assertEqual([uid for uid, _ in controller.route.points], [2, 3])
        self.assertFalse(controller.route.running)
        self.assertIsNone(controller.route.position)
