import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import poll_devices_worker


class TestScrcpyCameraSelection(unittest.TestCase):
    def test_poll_devices_worker_uses_camera_device_for_camera_scan(self):
        app = MagicMock()
        app.winfo_exists.return_value = True

        adb_manager = MagicMock()
        adb_manager.get_connected_devices.return_value = []

        scrcpy_manager = MagicMock()
        scrcpy_manager.list_cameras.return_value = []

        settings = {"camera_device": "ABC123", "target_device": ""}

        with patch("time.sleep", side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                poll_devices_worker(app, adb_manager, scrcpy_manager, settings)

        scrcpy_manager.list_cameras.assert_called_once_with("ABC123")


if __name__ == "__main__":
    unittest.main()
