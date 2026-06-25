import os
import sys
import unittest
import time
from unittest.mock import MagicMock, patch

# Ensure app directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.setup_wizard import SetupWizard, SetupState, InvalidStateTransition, SetupStateChangedEvent
from services.first_launch_manager import FirstLaunchManager
from services.runtime_installer import RuntimeInstaller
from services.runtime_manager import RuntimeManager
from services.event_bus import EventBus

class TestSetupWizard(unittest.TestCase):
    def setUp(self):
        self.mock_flm = MagicMock(spec=FirstLaunchManager)
        self.mock_installer = MagicMock(spec=RuntimeInstaller)
        self.mock_rm = MagicMock(spec=RuntimeManager)
        self.mock_installer.runtime_manager = self.mock_rm
        self.mock_flm.runtime_installer = self.mock_installer
        self.mock_event_bus = MagicMock(spec=EventBus)
        
        self.wizard = SetupWizard(
            first_launch_manager=self.mock_flm,
            runtime_installer=self.mock_installer,
            event_bus=self.mock_event_bus
        )

    def test_initial_state(self):
        self.assertEqual(self.wizard.state, SetupState.WELCOME)
        self.assertEqual(self.wizard.missing_dependencies, [])
        self.assertIsNone(self.wizard.error_message)

    def test_valid_transitions(self):
        # WELCOME -> DIAGNOSTICS
        self.wizard.transition_to(SetupState.DIAGNOSTICS)
        self.assertEqual(self.wizard.state, SetupState.DIAGNOSTICS)

        # DIAGNOSTICS -> INSTALLING
        self.wizard.transition_to(SetupState.INSTALLING)
        self.assertEqual(self.wizard.state, SetupState.INSTALLING)

        # INSTALLING -> COMPLETED
        self.wizard.transition_to(SetupState.COMPLETED)
        self.assertEqual(self.wizard.state, SetupState.COMPLETED)

    def test_invalid_transitions(self):
        # WELCOME -> INSTALLING should fail
        with self.assertRaises(InvalidStateTransition):
            self.wizard.transition_to(SetupState.INSTALLING)

        # WELCOME -> COMPLETED should fail
        with self.assertRaises(InvalidStateTransition):
            self.wizard.transition_to(SetupState.COMPLETED)

        # Move to DIAGNOSTICS
        self.wizard.transition_to(SetupState.DIAGNOSTICS)
        # DIAGNOSTICS -> WELCOME should succeed (reset/transition to WELCOME is always valid)
        self.wizard.transition_to(SetupState.WELCOME)
        self.assertEqual(self.wizard.state, SetupState.WELCOME)

        # Move to DIAGNOSTICS, then FAILED
        self.wizard.transition_to(SetupState.DIAGNOSTICS)
        self.wizard.transition_to(SetupState.FAILED)
        self.assertEqual(self.wizard.state, SetupState.FAILED)

        # FAILED -> INSTALLING should fail
        with self.assertRaises(InvalidStateTransition):
            self.wizard.transition_to(SetupState.INSTALLING)

        # FAILED -> DIAGNOSTICS should succeed
        self.wizard.transition_to(SetupState.DIAGNOSTICS)
        self.assertEqual(self.wizard.state, SetupState.DIAGNOSTICS)

        # Move to COMPLETED (terminal state)
        self.wizard.transition_to(SetupState.COMPLETED)
        # COMPLETED -> WELCOME should succeed (as transition to WELCOME is always allowed)
        self.wizard.transition_to(SetupState.WELCOME)
        self.assertEqual(self.wizard.state, SetupState.WELCOME)

        # Move back to DIAGNOSTICS then INSTALLING then FAILED
        self.wizard.transition_to(SetupState.DIAGNOSTICS)
        self.wizard.transition_to(SetupState.INSTALLING)
        self.wizard.transition_to(SetupState.FAILED)
        self.assertEqual(self.wizard.state, SetupState.FAILED)

    def test_callbacks_are_called(self):
        callback = MagicMock()
        self.wizard.register_callback(callback)

        self.wizard.transition_to(SetupState.DIAGNOSTICS)
        callback.assert_called_once_with(SetupState.WELCOME, SetupState.DIAGNOSTICS)

    def test_event_bus_publishing(self):
        self.wizard.transition_to(SetupState.DIAGNOSTICS, context={"foo": "bar"})
        
        self.mock_event_bus.publish.assert_called_once()
        event = self.mock_event_bus.publish.call_args[0][0]
        self.assertIsInstance(event, SetupStateChangedEvent)
        self.assertEqual(event.old_state, SetupState.WELCOME)
        self.assertEqual(event.new_state, SetupState.DIAGNOSTICS)
        self.assertEqual(event.context, {"foo": "bar"})

    def test_start_diagnostics_not_first_launch(self):
        self.mock_flm.is_first_launch.return_value = False

        self.wizard.start_diagnostics()

        self.assertEqual(self.wizard.state, SetupState.COMPLETED)
        self.mock_flm.is_first_launch.assert_called_once()
        self.mock_flm.generate_report.assert_not_called()

    def test_start_diagnostics_first_launch_all_dependencies_present(self):
        self.mock_flm.is_first_launch.return_value = True
        self.mock_rm.check_installed.return_value = True

        self.wizard.start_diagnostics()

        self.assertEqual(self.wizard.state, SetupState.COMPLETED)
        self.mock_flm.generate_report.assert_called_once()
        self.mock_flm.complete_first_launch.assert_called_once()
        self.assertEqual(self.wizard.missing_dependencies, [])

    def test_start_diagnostics_first_launch_dependencies_missing(self):
        self.mock_flm.is_first_launch.return_value = True
        # Mock check_installed: adb is installed, scrcpy and ffmpeg are missing
        self.mock_rm.check_installed.side_effect = lambda name: name == "adb"

        self.wizard.start_diagnostics()

        self.assertEqual(self.wizard.state, SetupState.DIAGNOSTICS)
        self.assertEqual(self.wizard.missing_dependencies, ["scrcpy", "ffmpeg"])
        self.mock_flm.complete_first_launch.assert_not_called()

    def test_start_diagnostics_exception_handling(self):
        self.mock_flm.is_first_launch.return_value = True
        self.mock_flm.generate_report.side_effect = RuntimeError("Disk full")

        self.wizard.start_diagnostics()

        self.assertEqual(self.wizard.state, SetupState.FAILED)
        self.assertEqual(self.wizard.error_message, "Disk full")

    def test_start_installation_wrong_state(self):
        # Initial state is WELCOME, start_installation is not allowed
        with self.assertRaises(InvalidStateTransition):
            self.wizard.start_installation()

    def test_start_installation_success(self):
        # Set state to DIAGNOSTICS first
        self.wizard.state = SetupState.DIAGNOSTICS
        
        self.mock_installer.install_all_missing.return_value = {"scrcpy": True, "ffmpeg": True}
        # Both critical dependencies are now ready
        self.mock_rm.check_installed.side_effect = lambda name: name in ("adb", "scrcpy")

        self.wizard.start_installation()

        self.assertEqual(self.wizard.state, SetupState.COMPLETED)
        self.mock_flm.complete_first_launch.assert_called_once()
        self.mock_flm.generate_report.assert_called_once()

    def test_start_installation_failure_missing_critical(self):
        # Set state to DIAGNOSTICS first
        self.wizard.state = SetupState.DIAGNOSTICS
        
        self.mock_installer.install_all_missing.return_value = {"scrcpy": False, "ffmpeg": True}
        # Critical dependency scrcpy is still missing, adb is installed
        self.mock_rm.check_installed.side_effect = lambda name: name == "adb"

        self.wizard.start_installation()

        self.assertEqual(self.wizard.state, SetupState.FAILED)
        self.assertIn("Critical dependencies installation failed", self.wizard.error_message)
        self.mock_flm.complete_first_launch.assert_not_called()

    def test_start_installation_exception(self):
        self.wizard.state = SetupState.DIAGNOSTICS
        self.mock_installer.install_all_missing.side_effect = RuntimeError("Network down")

        self.wizard.start_installation()

        self.assertEqual(self.wizard.state, SetupState.FAILED)
        self.assertEqual(self.wizard.error_message, "Network down")

    def test_start_installation_async(self):
        self.wizard.state = SetupState.DIAGNOSTICS
        self.mock_installer.install_all_missing.return_value = {"scrcpy": True}
        self.mock_rm.check_installed.return_value = True

        self.wizard.start_installation(async_mode=True)
        
        # Wait a tiny amount of time for background thread to execute
        timeout = 2.0
        start_time = time.time()
        while self.wizard.state == SetupState.INSTALLING and time.time() - start_time < timeout:
            time.sleep(0.05)

        self.assertEqual(self.wizard.state, SetupState.COMPLETED)

    def test_retry(self):
        self.wizard.state = SetupState.FAILED
        self.wizard.error_message = "Some error"
        
        self.mock_flm.is_first_launch.return_value = True
        self.mock_rm.check_installed.return_value = True

        self.wizard.retry()

        self.assertEqual(self.wizard.state, SetupState.COMPLETED)
        self.assertIsNone(self.wizard.error_message)

    def test_retry_wrong_state(self):
        with self.assertRaises(InvalidStateTransition):
            self.wizard.retry()

    def test_reset(self):
        self.wizard.state = SetupState.FAILED
        self.wizard.missing_dependencies = ["scrcpy"]
        self.wizard.error_message = "Failed setup"

        self.wizard.reset()

        self.assertEqual(self.wizard.state, SetupState.WELCOME)
        self.assertEqual(self.wizard.missing_dependencies, [])
        self.assertIsNone(self.wizard.error_message)

if __name__ == "__main__":
    unittest.main()
