import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import poll_devices_worker
from services.scrcpy_manager import ScrcpyManager


class TestScrcpyCameraSelection(unittest.TestCase):
    def test_poll_devices_worker_uses_camera_device_for_camera_scan(self):
        app = MagicMock()
        app.winfo_exists.return_value = True

        adb_manager = MagicMock()
        adb_manager.get_connected_devices.return_value = []

        scrcpy_manager = MagicMock()
        scrcpy_manager.is_camera_active.return_value = False
        scrcpy_manager.list_cameras.return_value = []

        settings = {"camera_device": "ABC123", "target_device": ""}

        with patch("time.sleep", side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                poll_devices_worker(app, adb_manager, scrcpy_manager, settings)

        scrcpy_manager.list_cameras.assert_called_once_with("ABC123")

    def test_scrcpy_manager_uses_runtime_path_for_list_cameras(self):
        manager = ScrcpyManager(logger=MagicMock())
        manager.scrcpy_path = "/tmp/fake-scrcpy"

        with patch("subprocess.run") as mock_run, \
             patch("os.path.exists", return_value=True):
            mock_run.return_value = MagicMock(returncode=0, stdout="--camera-id=0 (back camera)\n")
            cameras = manager.list_cameras("ABC123")

        self.assertEqual(cameras[0]["id"], "0")
        self.assertIn("--serial=ABC123", mock_run.call_args.args[0])
        self.assertEqual(mock_run.call_args.args[0][0], "/tmp/fake-scrcpy")

    def test_scrcpy_manager_refreshes_path_when_runtime_changes(self):
        manager = ScrcpyManager(logger=MagicMock())
        manager.scrcpy_path = "/tmp/old-scrcpy"

        with patch("services.scrcpy_manager.Config.get_bin_path", return_value="/tmp/new-scrcpy"), \
             patch("os.path.exists", side_effect=lambda path: path == "/tmp/new-scrcpy"):
            resolved_path = manager._resolve_scrcpy_path()

        self.assertEqual(resolved_path, "/tmp/new-scrcpy")
        self.assertEqual(manager.scrcpy_path, "/tmp/new-scrcpy")

    def test_poll_devices_worker_retries_camera_scan_when_none_found(self):
        app = MagicMock()
        app.winfo_exists.return_value = True
        app._last_camera_scan_serial = "ABC123"
        app._last_camera_scan_had_cameras = False

        adb_manager = MagicMock()
        adb_manager.get_connected_devices.return_value = []

        scrcpy_manager = MagicMock()
        scrcpy_manager.is_camera_active.return_value = False
        scrcpy_manager.list_cameras.side_effect = [[], [{"id": "0", "label": "Camera 0", "fps": []}]]

        settings = {"camera_device": "ABC123", "target_device": ""}

        with patch("time.sleep", side_effect=[None, RuntimeError("stop")]):
            with self.assertRaises(RuntimeError):
                poll_devices_worker(app, adb_manager, scrcpy_manager, settings)

        self.assertEqual(scrcpy_manager.list_cameras.call_count, 2)


if __name__ == "__main__":
    unittest.main()
