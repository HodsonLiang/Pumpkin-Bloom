import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock
from PIL import Image
from pikmin.scan_engine import DEFAULTS, Scanner, prepare_config


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        (self.base/'mushroom_pics').mkdir()
        Image.new('RGBA', (2, 2), 'green').save(self.base/'mushroom_pics/target.png')
        self.events = queue.Queue()
        self.device = Mock()
        self.actions = []
        self.device.send.side_effect = lambda point: self.actions.append(('send', point))
        def capture(path):
            self.actions.append(('capture', path.name))
            Image.new('RGB', (8, 16), 'blue').save(path)
        self.device.capture.side_effect = capture

    def scanner(self, *, timing='pipeline', recognizer=None):
        config = {**DEFAULTS, 'timing': timing}
        scanner = Scanner(config, [(25, 121), (26, 122)], self.events, base=self.base,
                          device=self.device, recognizer=recognizer or Mock(return_value=(False, None)))
        scanner.wait = lambda _: not scanner.stop_event.is_set()
        return scanner

    def test_pipeline_order_and_hit_persistence(self):
        scanner = self.scanner(recognizer=Mock(side_effect=[(True, 'target.png'), (False, None)]))
        scanner.run()
        self.assertEqual([a[0] for a in self.actions], ['send', 'send', 'capture', 'capture'])
        self.assertEqual(scanner.hits, 1)
        events = list(self.events.queue)
        hits = [e['record'] for e in events if e['kind']=='result' and e['record']['found']]
        self.assertEqual((hits[0]['lat'], hits[0]['lon']), (25, 121))
        self.assertTrue(Path(hits[0]['path']).is_file())
        screenshots = [e for e in events if e['kind']=='screenshot']
        self.assertTrue(all(e['content'].startswith(b'\x89PNG') for e in screenshots))
        self.assertFalse((scanner.folder/'capture_2.png').exists())
        self.assertTrue((scanner.folder/'latest.png').exists())
        records = [json.loads(line) for line in (scanner.folder/'results.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len(records), 2)
        self.device.reset.assert_called_once()

    def test_sequential_captures_before_sending_next_point(self):
        scanner = self.scanner(timing='sequential')
        scanner.run()
        self.assertEqual([a[0] for a in self.actions], ['send', 'capture', 'send', 'capture'])

    def test_stop_during_wait_keeps_resume_index(self):
        scanner = self.scanner()
        def stop_wait(_):
            scanner.stop_event.set()
            return False
        scanner.wait = stop_wait
        scanner.run()
        self.device.capture.assert_not_called()
        self.device.reset.assert_called_once()
        self.assertEqual(scanner.next_index, 1)
        self.assertEqual(list(self.events.queue)[-1]['text'], '已停止掃描')

    def test_stop_after_capture_drains_result_and_resumes_next(self):
        scanner = self.scanner(recognizer=Mock(return_value=(True, 'target.png')))
        capture = self.device.capture.side_effect
        def stop_capture(path):
            capture(path)
            scanner.stop_event.set()
        self.device.capture.side_effect = stop_capture
        scanner.run()
        self.assertEqual(scanner.next_index, 2)
        self.assertEqual(scanner.hits, 1)
        self.assertEqual(scanner.processed, 1)

    def test_capture_failure_is_counted_without_deadlock(self):
        scanner = self.scanner()
        self.device.capture.side_effect = OSError('screenshot failed')
        scanner.run()
        self.assertEqual(scanner.errors, 2)
        self.assertEqual(scanner.captured, 0)
        self.assertEqual(scanner.processed, 0)
        self.assertEqual(list(self.events.queue)[-1]['kind'], 'done')

    def test_recognition_failure_retains_capture(self):
        scanner = self.scanner(recognizer=Mock(side_effect=ValueError('bad template')))
        scanner.run()
        self.assertEqual(scanner.errors, 2)
        self.assertTrue((scanner.folder/'capture_1.png').is_file())
        self.assertEqual(scanner.processed, 2)

    def test_restore_failure_is_reported(self):
        scanner = self.scanner()
        self.device.reset.side_effect = OSError('offline')
        scanner.run()
        self.assertIn('定位還原失敗', list(self.events.queue)[-1]['text'])

    def test_config_validates_and_slices(self):
        path = self.base/'points.txt'
        path.write_text('\ufeff25,121\n26,122\n27,123\n', encoding='utf-8')
        config, points = prepare_config(dict(waypoints=str(path), start_index='2', max_points='1'))
        self.assertEqual(points, [(26, 122)])
        for invalid in ({'interval':'nan'}, {'start_index':'9'}, {'threshold':'2'}, {'max_points':'0'}):
            with self.assertRaises(ValueError):
                prepare_config(dict(waypoints=str(path), **invalid))
        path.write_text('91,12', encoding='utf-8')
        with self.assertRaises(ValueError):
            prepare_config(dict(waypoints=str(path)))


if __name__ == '__main__':
    unittest.main()
