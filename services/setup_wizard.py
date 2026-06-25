import logging
from enum import Enum
from dataclasses import dataclass
from typing import List, Callable, Optional, Dict, Any

class SetupState(Enum):
    WELCOME = "welcome"
    DIAGNOSTICS = "diagnostics"
    INSTALLING = "installing"
    COMPLETED = "completed"
    FAILED = "failed"

class InvalidStateTransition(Exception):
    """Exception raised when an invalid state transition is attempted."""
    pass

@dataclass
class SetupStateChangedEvent:
    old_state: SetupState
    new_state: SetupState
    context: Dict[str, Any]

class SetupWizard:
    """
    SetupWizard acts as a state machine managing the startup setup pipeline.
    It coordinates checking/installing missing dependencies (adb, scrcpy, ffmpeg)
    and transitions through various SetupState values.
    """
    def __init__(
        self,
        first_launch_manager=None,
        runtime_installer=None,
        event_bus=None,
        logger=None
    ):
        self.state = SetupState.WELCOME
        self.first_launch_manager = first_launch_manager
        self.runtime_installer = runtime_installer
        self.event_bus = event_bus
        self.logger = logger or logging.getLogger("CameraStudio.setup_wizard")
        self.missing_dependencies: List[str] = []
        self.error_message: Optional[str] = None
        self._state_changed_callbacks: List[Callable[[SetupState, SetupState], None]] = []

    def register_callback(self, callback: Callable[[SetupState, SetupState], None]) -> None:
        """Registers a callback to be executed when the state transitions."""
        self._state_changed_callbacks.append(callback)

    def transition_to(self, new_state: SetupState, context: Optional[Dict[str, Any]] = None) -> None:
        """Public method to manually transition to a new state."""
        self._transition_to(new_state, context)

    def _transition_to(self, new_state: SetupState, context: Optional[Dict[str, Any]] = None) -> None:
        """Internal helper to validate transitions, set state, and notify listeners."""
        old_state = self.state
        if old_state == new_state:
            return

        # Validate transition
        valid = False
        if new_state == SetupState.WELCOME:
            valid = True  # Can transition/reset to WELCOME from any state
        elif old_state == SetupState.WELCOME:
            valid = (new_state == SetupState.DIAGNOSTICS)
        elif old_state == SetupState.DIAGNOSTICS:
            valid = (new_state in (SetupState.INSTALLING, SetupState.COMPLETED, SetupState.FAILED))
        elif old_state == SetupState.INSTALLING:
            valid = (new_state in (SetupState.COMPLETED, SetupState.FAILED))
        elif old_state == SetupState.FAILED:
            valid = (new_state == SetupState.DIAGNOSTICS)
        elif old_state == SetupState.COMPLETED:
            valid = False  # Completed is a terminal state

        if not valid:
            raise InvalidStateTransition(f"Cannot transition from {old_state.name} to {new_state.name}")

        self.state = new_state
        self.logger.info(f"SetupWizard: Transitioned from {old_state.name} to {new_state.name}")

        # Execute callbacks
        for callback in self._state_changed_callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                self.logger.error(f"Error in state change callback: {e}", exc_info=True)

        # Publish to event bus
        if self.event_bus:
            try:
                event = SetupStateChangedEvent(
                    old_state=old_state,
                    new_state=new_state,
                    context=context or {}
                )
                self.event_bus.publish(event)
            except Exception as e:
                self.logger.error(f"Error publishing state change event: {e}", exc_info=True)

    def start_diagnostics(self) -> None:
        """
        Transitions to DIAGNOSTICS, runs diagnostic check for dependencies,
        and transitions directly to COMPLETED if all are already satisfied.
        """
        if self.state not in (SetupState.WELCOME, SetupState.FAILED):
            raise InvalidStateTransition(f"Cannot start diagnostics from state {self.state.name}")

        # Transition to DIAGNOSTICS state first
        self._transition_to(SetupState.DIAGNOSTICS)

        try:
            # If not first launch, complete immediately
            if self.first_launch_manager and not self.first_launch_manager.is_first_launch():
                self.logger.info("Not first launch. Skipping wizard diagnostics.")
                self.missing_dependencies = []
                self._transition_to(SetupState.COMPLETED)
                return

            # Save initial diagnostics report if first_launch_manager is present
            if self.first_launch_manager:
                initial_report = self.first_launch_manager.generate_report()
                initial_report.save_to_file()
                self.logger.info("Saved initial first launch diagnostic report.")

            # Identify missing dependencies
            rm = None
            if self.runtime_installer and self.runtime_installer.runtime_manager:
                rm = self.runtime_installer.runtime_manager
            elif self.first_launch_manager and hasattr(self.first_launch_manager, 'runtime_installer') and self.first_launch_manager.runtime_installer:
                rm = self.first_launch_manager.runtime_installer.runtime_manager

            if rm:
                dependencies = ["adb", "scrcpy", "ffmpeg"]
                self.missing_dependencies = [
                    dep for dep in dependencies
                    if not rm.check_installed(dep)
                ]
            else:
                self.missing_dependencies = []

            self.logger.info(f"Diagnostics checked. Missing: {self.missing_dependencies}")

            if not self.missing_dependencies:
                # All ready! Mark complete and finish
                if self.first_launch_manager:
                    self.first_launch_manager.complete_first_launch()
                self._transition_to(SetupState.COMPLETED)

        except Exception as e:
            self.logger.error(f"Failed during setup diagnostics: {e}", exc_info=True)
            self.error_message = str(e)
            self._transition_to(SetupState.FAILED, context={"error": self.error_message})

    def start_installation(self, progress_callback=None, status_callback=None, async_mode: bool = False) -> None:
        """
        Transitions to INSTALLING, runs runtime installer to download and configure missing packages.
        If async_mode is True, runs the installer flow on a background thread.
        """
        if self.state != SetupState.DIAGNOSTICS:
            raise InvalidStateTransition(f"Cannot start installation from state {self.state.name}")

        self._transition_to(SetupState.INSTALLING)

        def run_install():
            try:
                installer = self.runtime_installer
                if not installer and self.first_launch_manager and hasattr(self.first_launch_manager, 'runtime_installer'):
                    installer = self.first_launch_manager.runtime_installer

                if not installer:
                    raise ValueError("RuntimeInstaller is not configured.")

                # Run installation
                results = installer.install_all_missing(
                    progress_callback=progress_callback,
                    status_callback=status_callback
                )
                self.logger.info(f"Dependency installation completed. Results: {results}")

                # Validate critical dependencies (adb and scrcpy)
                rm = installer.runtime_manager
                adb_ready = rm.check_installed("adb")
                scrcpy_ready = rm.check_installed("scrcpy")

                # Save final report if first_launch_manager is present
                if self.first_launch_manager:
                    final_report = self.first_launch_manager.generate_report()
                    final_report.save_to_file()
                    self.logger.info("Saved final first launch diagnostic report.")

                if adb_ready and scrcpy_ready:
                    if self.first_launch_manager:
                        self.first_launch_manager.complete_first_launch()
                    self._transition_to(SetupState.COMPLETED)
                else:
                    missing_critical = []
                    if not adb_ready:
                        missing_critical.append("adb")
                    if not scrcpy_ready:
                        missing_critical.append("scrcpy")
                    error_msg = f"Critical dependencies installation failed: {', '.join(missing_critical)}"
                    self.error_message = error_msg
                    self._transition_to(SetupState.FAILED, context={"error": error_msg})

            except Exception as e:
                self.logger.error(f"Installation process failed: {e}", exc_info=True)
                self.error_message = str(e)
                self._transition_to(SetupState.FAILED, context={"error": self.error_message})

        if async_mode:
            import threading
            threading.Thread(target=run_install, daemon=True).start()
        else:
            run_install()

    def retry(self) -> None:
        """Retries setup check/diagnostics from FAILED state."""
        if self.state != SetupState.FAILED:
            raise InvalidStateTransition(f"Cannot retry setup from state {self.state.name}")
        self.error_message = None
        self.start_diagnostics()

    def reset(self) -> None:
        """Resets the state machine back to WELCOME and clears diagnostics state."""
        self.missing_dependencies = []
        self.error_message = None
        self._transition_to(SetupState.WELCOME)
