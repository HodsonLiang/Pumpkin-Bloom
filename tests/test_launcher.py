import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import queue
import threading
import launcher


class LauncherTests(unittest.TestCase):
    def test_coordinate_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'points.txt'
            path.write_text('\ufeff25.03,121.56\n\n-90,-180\n', encoding='utf-8')
            self.assertEqual(len(launcher.read_waypoints(path)), 2)
            for content in ('nan,12', '91,1', '1,181', 'bad', ''):
                path.write_text(content, encoding='utf-8')
                with self.assertRaises(ValueError):
                    launcher.read_waypoints(path)

    def controller(self):
        app = launcher.Launcher.__new__(launcher.Launcher)
        app.events = queue.Queue()
        app.cancel = threading.Event()
        app.process = app.tunnel = None
        return app

    def test_existing_single_device_service_is_reused(self):
        app = self.controller()
        app.spawn = Mock()
        with patch('launcher.tunnels', return_value={'device': [{}]}):
            self.assertTrue(app.connect())
        app.spawn.assert_not_called()

    def test_multiple_devices_are_rejected(self):
        app = self.controller()
        with patch('launcher.tunnels', return_value={'one': [{}], 'two': [{}]}):
            with self.assertRaises(RuntimeError):
                app.connect()

    def test_worker_failure_still_restores_location(self):
        app = self.controller()
        app.connect = Mock(return_value=True)
        worker = Mock(returncode=1)
        worker.poll.return_value = 1
        clear = Mock()
        clear.wait.return_value = 0
        app.spawn = Mock(side_effect=[worker, clear])
        with patch('launcher.kill_tree'):
            app.run(0, {'speed': 18}, {})
        self.assertEqual(app.spawn.call_args_list[1].args[0][-1], 'clear')
        events = list(app.events.queue)
        self.assertTrue(any(kind == 'done' and '失敗' in value for kind, value in events))

    def test_cancel_during_connect_does_not_launch_worker(self):
        app = self.controller()
        app.connect = Mock(return_value=False)
        app.spawn = Mock()
        app.cancel.set()
        with patch('launcher.kill_tree'):
            app.run(0, {'speed': 18}, {})
        app.spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
