"""Search checkpoints survive manual moves, cancellation and device changes."""
from pathlib import Path
import queue
import threading
import unittest
from unittest.mock import Mock, patch

from pikmin.scan_ui import ScanApp
from pikmin.scan_engine import ScanDevice


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class SearchStateTests(unittest.TestCase):
    def app(self):
        app = ScanApp.__new__(ScanApp)
        app.active = app.waiting_start = app.manual_busy = app.manual_active = False
        app.manual_preparing = app.pending_release = app.pending_reset = False
        app.pending_start = app.closing = False
        app.pending_teleport = None
        app.start_generation = 0
        app.next_index, app.end_index = 7, 11
        app.last_config = dict(waypoints=str(Path(__file__).resolve()), start_index=3,
                               max_points=8, timing='pipeline')
        app.fields = {key: Value(value) for key, value in app.last_config.items() if key != 'timing'}
        app.timing = Value('提前傳送（原流程）')
        app.status = Value('')
        app.device_session = Mock(prepared_id='phone-A')
        app.manual_device = ScanDevice(udid='phone-A')
        app.scanner = Mock(stop_event=threading.Event())
        app.refresh_search_buttons = Mock()
        app.append_log = Mock()
        return app

    def test_manual_location_resume_needs_one_click_and_preserves_range(self):
        app = self.app()
        app.manual_active = True
        app.run_manual = Mock()
        app.toggle_search()
        app.run_manual.assert_called_once_with('reset')
        self.assertTrue(app.pending_start)
        self.assertEqual(app.fields['start_index'].get(), 7)
        self.assertEqual(app.fields['max_points'].get(), 4)
        app.start = Mock()
        app.handle_manual_done(dict(operation='reset', point=None, error=None))
        app.start.assert_called_once()
        self.assertFalse(app.manual_active)

    def test_disconnect_stops_search_without_changing_checkpoint(self):
        app = self.app()
        app.active = True
        app.device_disconnected()
        self.assertTrue(app.scanner.stop_event.is_set())
        self.assertEqual(app.next_index, 7)
        self.assertIsNone(app.device_session.prepared_id)

    def test_disconnected_manual_location_only_releases_old_process(self):
        app = self.app()
        app.manual_active = True
        app.run_manual = Mock()
        app.device_disconnected()
        app.run_manual.assert_called_once_with('release')
        self.assertEqual(app.next_index, 7)

    def test_disconnect_during_manual_submission_cancels_follow_up(self):
        app = self.app()
        app.manual_busy = app.manual_active = True
        app.pending_teleport = (25, 121)
        app.pending_start = True
        app.run_manual = Mock()
        app.device_disconnected()
        app.handle_manual_done(dict(operation='set', point=(25, 121), error=None))
        app.run_manual.assert_called_once_with('release')
        self.assertIsNone(app.pending_teleport)
        self.assertFalse(app.pending_start)

    def test_cancelled_manual_connection_cannot_teleport_after_reconnect(self):
        app = self.app()
        app.run_manual = Mock()
        app.pending_teleport = (25, 121)
        app.dispatch_teleport()
        ready = app.device_session.ensure.call_args.args[0]
        self.assertTrue(app.manual_preparing)
        app.stop()
        ready()
        app.run_manual.assert_not_called()
        self.assertFalse(app.manual_preparing)

    def test_repeated_manual_moves_reuse_existing_device_process_owner(self):
        app = self.app()
        app.manual_active = True
        app.pending_teleport = (25, 121)
        app.run_manual = Mock()
        device = app.manual_device
        app.dispatch_teleport()
        app.device_session.ensure.call_args.args[0]()
        self.assertIs(app.manual_device, device)
        app.run_manual.assert_called_once_with('set', (25, 121))

    def test_reconnected_search_uses_saved_next_point(self):
        app = self.app()
        app.device_disconnected()
        app.start = Mock()
        app.toggle_search()
        app.start.assert_called_once()
        self.assertEqual(app.fields['start_index'].get(), 7)
        self.assertEqual(app.fields['max_points'].get(), 4)

    def test_completed_search_cannot_resume_with_zero_points(self):
        app = self.app()
        app.next_index = app.end_index
        app.start = Mock()
        app.resume()
        app.start.assert_not_called()

    def test_old_device_commands_are_explicitly_bound(self):
        device = ScanDevice(udid='phone-A')
        with patch('pikmin.fly_engine.subprocess.Popen') as spawn:
            device.send((25, 121))
        self.assertIn('phone-A', spawn.call_args.args[0])
        device.process = None
        with patch('pikmin.fly_engine.subprocess.run') as reset:
            device.reset()
        self.assertIn('phone-A', reset.call_args.args[0])

    def test_resuming_replaces_stopped_worker_before_refreshing_buttons(self):
        app = self.app()
        app.scanner.stop_event.set()
        app.device_session.prepared_id = 'phone-B'
        app.current_marker = app.sent_marker = None
        app.current_preview = Mock()
        app.events = queue.Queue()
        app.waypoint_picker = Mock()
        app.setting_widgets = []
        app.toggle_button, app.restart_button = Mock(), Mock()
        app.refresh_search_buttons = lambda: ScanApp.refresh_search_buttons(app)
        scanner = Mock(stop_event=threading.Event())
        config = {**app.last_config, 'start_index': 7, 'max_points': 4}
        with patch('pikmin.scan_ui.Scanner', return_value=scanner) as create:
            app.begin_scan(config, [(25, 121)] * 4)
        self.assertEqual(create.call_args.kwargs['device'].udid, 'phone-B')
        app.toggle_button.configure.assert_called_with(text='■ 停止', state='normal')
        self.assertEqual(app.next_index, 7)
        self.assertEqual(app.end_index, 11)

    def test_replacing_manual_device_releases_old_owner_first(self):
        app = self.app()
        app.manual_device.process = Mock()
        app.device_session.prepared_id = 'phone-B'
        app.pending_teleport = (25, 121)
        app.run_manual = Mock()
        app.dispatch_teleport()
        app.device_session.ensure.call_args.args[0]()
        app.run_manual.assert_called_once_with('release')
        self.assertEqual(app.manual_device.udid, 'phone-A')
        self.assertEqual(app.pending_teleport, (25, 121))

