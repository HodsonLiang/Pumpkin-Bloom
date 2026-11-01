import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from pikmin.device_cli import validate_with_local


class PairingTests(unittest.IsolatedAsyncioTestCase):
    def client(self):
        return SimpleNamespace(identifier='device', pairing_records_cache_folder='cache', pair_record={'id': 'system'})

    async def test_valid_system_pairing_is_kept(self):
        client, local = self.client(), Mock()
        self.assertTrue(await validate_with_local(client, AsyncMock(return_value=True), local))
        local.assert_not_called()

    async def test_local_record_must_pass_device_validation(self):
        client = self.client()
        validate = AsyncMock(side_effect=[False, True])
        self.assertTrue(await validate_with_local(client, validate, Mock(return_value={'id': 'local'})))
        self.assertEqual(client.pair_record, {'id': 'local'})
        self.assertEqual(validate.await_count, 2)

    async def test_invalid_local_restores_original_record(self):
        client = self.client()
        self.assertFalse(await validate_with_local(client, AsyncMock(return_value=False), Mock(return_value={'id': 'local'})))
        self.assertEqual(client.pair_record, {'id': 'system'})

    async def test_missing_local_does_not_skip_pairing(self):
        validate = AsyncMock(return_value=False)
        self.assertFalse(await validate_with_local(self.client(), validate, Mock(return_value=None)))
        self.assertEqual(validate.await_count, 1)
