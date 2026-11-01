import unittest
from unittest.mock import Mock, patch
from pikmin.device_session import DeviceSession


class SessionTests(unittest.TestCase):
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
        failed.assert_called_once()

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
