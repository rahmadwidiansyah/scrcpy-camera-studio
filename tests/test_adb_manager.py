import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.adb_manager import ADBManager


class TestADBManager(unittest.TestCase):
    def test_test_adb_connection_runs_start_server_then_devices(self):
        manager = ADBManager(logger=MagicMock())
        manager.adb_path = "/usr/bin/adb"

        results = [
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout="List of devices attached\n"),
        ]

        with patch.object(manager, "_run_adb", side_effect=results) as mock_run:
            callback_calls = []
            manager.test_adb_connection(on_done=lambda ok, msg: callback_calls.append((ok, msg)))

        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(mock_run.call_args_list[0].args[0], ["start-server"])
        self.assertEqual(mock_run.call_args_list[1].args[0], ["devices"])
        self.assertEqual(callback_calls[0][0], True)
        self.assertIn("List of devices", callback_calls[0][1])


if __name__ == "__main__":
    unittest.main()
