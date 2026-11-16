import unittest
from unittest.mock import patch, Mock
import queue
import threading
import launcher


class LauncherTests(unittest.TestCase):
    def controller(self):
        app = launcher.Launcher.__new__(launcher.Launcher)
        app.events = queue.Queue()
        app.cancel = threading.Event()
        app.process = app.tunnel = None
        return app

    def test_all_modes_open_without_device(self):
        app = self.controller()
        app.busy = app.closing = app.device_connected = False
        app.tabs = Mock()
        app.start_button = Mock()
        for mode, connected, busy, expected in [(0, False, False, 'normal'),
                                               (1, False, False, 'normal'),
                                               (2, False, False, 'normal'),
                                               (0, True, False, 'normal'),
                                               (0, True, True, 'disabled')]:
            app.tabs.index.return_value = mode
            app.device_connected, app.busy = connected, busy
            app.update_start_state()
            app.start_button.configure.assert_called_with(state=expected)

    def test_child_owns_device_cleanup(self):
        app = self.controller()
        worker = Mock(returncode=1)
        worker.poll.return_value = 1
        app.spawn = Mock(return_value=worker)
        with patch('launcher.kill_tree'), patch('pikmin.device_backend.kill_tree'):
            app.run(0, {'speed': 18}, {})
        self.assertEqual(app.spawn.call_count, 1)
        events = list(app.events.queue)
        self.assertTrue(any(kind == 'done' and '失敗' in value for kind, value in events))

    def test_cancel_before_start_does_not_launch_worker(self):
        app = self.controller()
        app.spawn = Mock()
        app.cancel.set()
        with patch('launcher.kill_tree'), patch('pikmin.device_backend.kill_tree'):
            app.run(0, {'speed': 18}, {})
        app.spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
