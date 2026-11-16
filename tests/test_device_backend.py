import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pikmin.device_backend import DeviceBackend, developer_image_mounted, device_ids


class DeveloperImageTests(unittest.TestCase):
    def query(self, images):
        return patch('pikmin.device_backend.subprocess.run', return_value=SimpleNamespace(
            returncode=0, stdout=json.dumps(images), stderr=''))

    def test_mounted_developer_image_is_detected(self):
        with self.query([{'IsMounted': True, 'MountPath': '/System/Developer'}]):
            self.assertTrue(developer_image_mounted())

    def test_other_or_unmounted_images_do_not_skip_preparation(self):
        for images in ([], [{'IsMounted': True, 'MountPath': '/other'}],
                       [{'IsMounted': False, 'MountPath': '/System/Developer'}]):
            with self.subTest(images=images), self.query(images):
                self.assertFalse(developer_image_mounted())

    def test_invalid_query_cannot_be_treated_as_ready(self):
        with self.query({'error': 'failed'}), self.assertRaises(RuntimeError):
            developer_image_mounted()
        with patch('pikmin.device_backend.subprocess.run', side_effect=subprocess.TimeoutExpired('mounter', 10)):
            with self.assertRaises(subprocess.TimeoutExpired):
                developer_image_mounted()

    def test_ready_image_and_tunnel_do_not_launch_auto_mount(self):
        backend = DeviceBackend()
        with patch('pikmin.device_backend.device_ids', return_value=['phone']), \
             patch('pikmin.device_backend.developer_image_mounted', return_value=True), \
             patch('pikmin.device_backend.tunnels', return_value={'phone': [{}]}), \
             patch.object(backend, 'spawn') as spawn:
            self.assertTrue(backend.connect())
            spawn.assert_not_called()


class DeviceConnectionTests(unittest.TestCase):
    def test_existing_single_device_service_is_reused(self):
        app = DeviceBackend()
        app.spawn = Mock(return_value=Mock(returncode=0))
        with patch('pikmin.device_backend.device_ids', return_value=['device']), patch('pikmin.device_backend.kill_tree'), patch('pikmin.device_backend.tunnels', return_value={'device': [{}]}), patch('pikmin.device_backend.developer_image_mounted', side_effect=[False, True]):
            self.assertTrue(app.connect())
        self.assertEqual(app.spawn.call_args.args[0][-2:], ['mounter', 'auto-mount'])

    def test_multiple_devices_are_rejected(self):
        app = DeviceBackend()
        with patch('pikmin.device_backend.device_ids', return_value=['one', 'two']):
            with self.assertRaises(RuntimeError):
                app.connect()

    def test_missing_device_never_starts_tunnel(self):
        app = DeviceBackend()
        app.spawn = Mock()
        with patch('pikmin.device_backend.device_ids', return_value=[]):
            with self.assertRaises(RuntimeError):
                app.connect()
        app.spawn.assert_not_called()

    def test_mount_failure_prevents_tunnel_start(self):
        app = DeviceBackend()
        app.spawn = Mock(return_value=Mock(returncode=1))
        with patch('pikmin.device_backend.device_ids', return_value=['device']), patch('pikmin.device_backend.kill_tree'), patch('pikmin.device_backend.developer_image_mounted', return_value=False):
            with self.assertRaises(RuntimeError):
                app.connect()
        self.assertEqual(app.spawn.call_count, 1)

    def test_device_query_deduplicates_and_rejects_bad_data(self):
        with patch('pikmin.device_backend.subprocess.run', return_value=Mock(returncode=0, stdout='["one", "one"]')):
            self.assertEqual(device_ids(), ['one'])
        with patch('pikmin.device_backend.subprocess.run', return_value=Mock(returncode=0, stdout='error')):
            with self.assertRaises(RuntimeError):
                device_ids()

