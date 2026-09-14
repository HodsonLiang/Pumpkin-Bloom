"""Catch transitive-dependency API breaks that pip check cannot detect."""
import unittest
from pikmin.preflight import COMMANDS, check_command


class DeviceCLICompatibilityTests(unittest.TestCase):
    def test_real_command_imports_without_device_access(self):
        for command in COMMANDS:
            with self.subTest(command=command):
                check_command(command)


if __name__ == '__main__':
    unittest.main()
