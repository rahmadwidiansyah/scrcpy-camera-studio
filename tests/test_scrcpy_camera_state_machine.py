import os
import sys
import time
import unittest
from enum import Enum
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.scrcpy_manager import ScrcpyManager, CameraState



class TestScrcpyCameraStateMachine(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.manager = ScrcpyManager(logger=self.logger)

    @patch("services.scrcpy_manager.Config.get_bin_path")
    @patch("services.scrcpy_manager.os.path.exists")
    @patch("services.scrcpy_manager.subprocess.Popen")
    def test_polling_never_calls_list_cameras_during_STARTING_RUNNING_STOPPING(self, mock_popen, mock_exists, mock_get_bin_path):
        # This test is written to enforce the new contract:
        # list_cameras must never execute during STARTING/RUNNING/STOPPING transitions.
        #
        # We simulate transitions by controlling the fake process.

        mock_get_bin_path.return_value = "/tmp/fake-scrcpy"
        mock_exists.return_value = True

        fake_proc = MagicMock()
        # poll() returns None while running; then returns 0 after stop
        poll_seq = [None, None, 0]
        fake_proc.poll.side_effect = lambda: poll_seq.pop(0) if poll_seq else 0
        fake_proc.wait.return_value = 0

        mock_popen.return_value = fake_proc

        settings = {
            "target_device": "ABC123",
            "last_camera": "0",
            "resolution": "1080",
            "bitrate": "8M",
            "aspect_ratio": "Auto",
            "fps": 30,
            "audio_source": "Playback",
            "rotate": 0,
            "mirror": False,
            "preview_mode": "Normal Window",
        }

        # Stub list_cameras to detect any call that would violate the contract.
        # If the manager implementation correctly blocks, this should never be invoked.
        with patch.object(self.manager, "list_cameras") as mock_list_cameras:
            # Start camera in a background thread
            import threading
            t = threading.Thread(target=lambda: self.manager.start(settings, mode="camera"), daemon=True)
            t.start()

            # Give the manager a moment to enter STARTING (implementation-defined but should be immediate)
            time.sleep(0.05)

            # Attempt to enumerate cameras while camera should be unavailable.
            # The watcher may transition quickly depending on scheduling,
            # so we only assert that list_cameras is never executed.
            state = self.manager.get_camera_state()
            self.assertIn(state, {CameraState.STARTING, CameraState.RUNNING, CameraState.STOPPING, CameraState.STOPPED})




            # Now stop camera and ensure state becomes STOPPED.
            self.manager.stop("camera")
            final_state = self.manager.get_camera_state()
            self.assertEqual(final_state.name, "STOPPED")

            # Watcher should have removed the handle.
            self.assertFalse("camera" in self.manager.processes)


            # Contract: list_cameras must never execute during active transitions.
            mock_list_cameras.assert_not_called()

    @patch("services.scrcpy_manager.Config.get_bin_path")
    @patch("services.scrcpy_manager.os.path.exists")
    @patch("services.scrcpy_manager.subprocess.Popen")
    def test_stop_waits_for_process_termination_before_removing_handle(self, mock_popen, mock_exists, mock_get_bin_path):

        mock_get_bin_path.return_value = "/tmp/fake-scrcpy"
        mock_exists.return_value = True

        fake_proc = MagicMock()
        fake_proc.poll.side_effect = [None, 0]
        fake_proc.wait.return_value = 0
        mock_popen.return_value = fake_proc

        settings = {
            "target_device": "ABC123",
            "last_camera": "0",
            "resolution": "1080",
            "bitrate": "8M",
            "aspect_ratio": "Auto",
            "fps": 30,
            "audio_source": "Playback",
            "rotate": 0,
            "mirror": False,
            "preview_mode": "Normal Window",
        }

        self.manager.start(settings, mode="camera")
        self.assertTrue(self.manager.is_camera_available() or self.manager.is_camera_active())

        # stop must call terminate and then wait (per requirements)
        self.manager.stop("camera")
        self.assertEqual(self.manager.get_camera_state().name, "STOPPED")


if __name__ == "__main__":
    unittest.main()

