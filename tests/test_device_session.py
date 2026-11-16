import unittest
from unittest.mock import Mock, patch
from pikmin.device_session import DeviceSession


class SessionTests(unittest.TestCase):
    def test_resume_queued_behind_cancelled_check_is_not_cancelled_by_old_result(self):
        session = self.session()
        session.prepared_id = 'phone'
        old_ready, old_failed, new_ready = Mock(), Mock(), Mock()
        with patch('pikmin.device_backend.device_ids', return_value=['phone']), patch('pikmin.device_backend.tunnels', return_value={'phone': [{}]}):
            session.ensure(old_ready, old_failed)
            session.worker.join(3)
            session.cancel_pending()
            session.ensure(new_ready)
            session.poll()
            session.worker.join(3)
            session.poll()
        old_ready.assert_not_called()
        old_failed.assert_not_called()
        new_ready.assert_called_once()
        self.assertEqual(session.prepared_id, 'phone')

    def test_cancel_signals_preparation_and_drops_queued_action(self):
        session = self.session()
        session.queued = (Mock(), Mock())
        session.cancel_pending()
        self.assertTrue(session.prepare_cancel.is_set())
        self.assertIsNone(session.queued)

    def test_device_change_during_preparation_never_runs_action(self):
        session = self.session()
        session.prepared_id = 'phone-A'
        ready, failed = Mock(), Mock()
        with patch('pikmin.device_backend.device_ids', side_effect=[['phone-A'], ['phone-B']]), patch('pikmin.device_backend.tunnels', return_value={'phone-A': [{}]}):
            session.ensure(ready, failed)
            session.worker.join(3)
        with patch('pikmin.device_session.messagebox.showerror'):
            session.poll()
        ready.assert_not_called()
        failed.assert_called_once()

    def test_preparation_progress_is_forwarded_to_view(self):
        session = self.session()
        session.backend = Mock()
        import queue
        session.backend.events = queue.Queue()
        session.backend.events.put(('status', '準備開發者映像'))
        session.backend.events.put(('log', '下載進度'))
        session.pending = True
        session.request_generation = session.generation
        session.on_event = Mock()
        with patch('builtins.print'):
            session.poll()
        self.assertEqual([call.args[0] for call in session.on_event.call_args_list], [
            {'kind': 'status', 'text': '準備開發者映像'},
            {'kind': 'log', 'text': '下載進度'}])

    def session(self):
        with patch('pikmin.device_session.threading.Thread'):
            return DeviceSession(Mock(), Mock())

    def test_missing_device_reports_without_starting_services(self):
        session = self.session()
        ready, failed = Mock(), Mock()
        with patch('pikmin.device_backend.device_ids', return_value=[]), patch('pikmin.device_backend.DeviceBackend') as backend:
            session.ensure(ready, failed)
            session.worker.join(3)
            self.assertFalse(session.worker.is_alive())
            with patch('pikmin.device_session.messagebox.showerror') as error:
                session.poll()
                error.assert_called_once()
            backend.assert_not_called()
        ready.assert_not_called()
        failed.assert_called_once()
        self.assertFalse(session.pending)

    def test_cancelled_preparation_cannot_run_stale_action(self):
        session = self.session()
        session.prepared_id = 'phone'
        ready, failed = Mock(), Mock()
        with patch('pikmin.device_backend.device_ids', return_value=['phone']), patch('pikmin.device_backend.tunnels', return_value={'phone': [{}]}):
            session.ensure(ready, failed)
            session.worker.join(3)
        session.cancel_pending()
        session.poll()
        ready.assert_not_called()
        failed.assert_not_called()

    def test_ready_callback_runs_on_poll_and_transitions_popup_once(self):
        session = self.session()
        session.prepared_id = 'phone'
        ready = Mock()
        with patch('pikmin.device_backend.device_ids', return_value=['phone']), patch('pikmin.device_backend.tunnels', return_value={'phone': [{}]}):
            session.ensure(ready)
            session.worker.join(3)
        ready.assert_not_called()
        session.poll()
        ready.assert_called_once()
        session.events.put(('devices', ('phone',)))
        session.events.put(('devices', ()))
        session.events.put(('devices', ()))
        with patch('pikmin.device_session.messagebox.showinfo') as info:
            session.poll()
            info.assert_called_once()
        session.disconnected.assert_called_once()
        self.assertIsNone(session.prepared_id)
