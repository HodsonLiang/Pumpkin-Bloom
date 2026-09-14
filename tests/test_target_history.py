from pathlib import Path
import tempfile
import unittest
from pikmin.target_history import read_history, trash_target, validate_coords
from pikmin.fly_engine import Route


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'found_targets'
        self.root.mkdir()

    def test_old_and_new_filenames_and_invalid_files(self):
        for name in ['electric.png_-12.5_123.0_1789306568.png', 'special_type_25.123456_-121.123456_20260914_194714_b290a61a_233.png', 'unknown.png', 'fire_95.0_121.0_1789306568.png']:
            (self.root/name).touch()
        records, skipped = read_history(self.root)
        self.assertEqual(len(records), 2)
        self.assertEqual(skipped, 2)
        self.assertEqual(records[0]['lat'], -12.5)
        self.assertEqual(records[1]['target'], 'special_type.png')
        self.assertEqual(records[1]['index'], 233)

    def test_trash_is_reversible_and_not_loaded(self):
        source = self.root/'fire_25.0_121.0_1789306568.png'
        source.write_bytes(b'original screenshot')
        destination = trash_target(source, self.root)
        self.assertFalse(source.exists())
        self.assertEqual(destination.read_bytes(), b'original screenshot')
        self.assertEqual(read_history(self.root), ([], 0))
        self.assertIsNone(trash_target(source, self.root))

    def test_cannot_move_template_or_outside_file(self):
        outside = self.root.parent/'template.png'
        outside.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            trash_target(outside, self.root)
        self.assertTrue(outside.exists())

    def test_invalid_manual_coordinates(self):
        for point in [(float('nan'), 0), (0, float('inf')), (91, 0), (0, -181)]:
            with self.assertRaises(ValueError):
                validate_coords(*point)
        self.assertEqual(validate_coords('25.03', '121.56'), (25.03, 121.56))


class DeleteWaypointTests(unittest.TestCase):
    def test_delete_completed_point_keeps_current_target(self):
        r = Route()
        for point in [(25, 121), (26, 122), (27, 123)]:
            r.add(point)
        r.index, r.running, r.wait = 1, True, 3.
        before = r.position
        self.assertTrue(r.remove(1))
        self.assertEqual(r.points[r.index][0], 2)
        self.assertEqual(r.wait, 3)
        self.assertEqual(r.position, before)
        self.assertFalse(r.running)

    def test_delete_current_point_and_last_point(self):
        r = Route()
        r.add((25, 121))
        r.add((26, 122))
        r.start()
        r.remove(1)
        self.assertEqual(r.points[r.index][0], 2)
        r.remove(2)
        self.assertEqual(r.remaining(), (0, 0))
        self.assertFalse(r.running)
        r.add((27, 123))
        self.assertEqual(r.points[0][0], 3)

    def test_stale_delete_does_not_interrupt_running(self):
        r = Route()
        r.add((25, 121))
        r.start()
        self.assertFalse(r.remove(999))
        self.assertTrue(r.running)
