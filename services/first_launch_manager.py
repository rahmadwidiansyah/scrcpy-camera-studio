import os
import logging
from services.directory_manager import DirectoryManager
from services.first_launch_report import FirstLaunchReport
from services.runtime_installer import RuntimeInstaller

class FirstLaunchManager:
    """
    FirstLaunchManager determines if it's the application's first launch,
    manages the launch state flag, generates diagnostics reports, and
    orchestrates installation of missing dependencies on first run.
    """
    def __init__(self, flag_file_path=None, runtime_installer=None, logger=None):
        self.logger = logger or logging.getLogger("CameraStudio.startup")
        self.flag_file_path = flag_file_path or os.path.join(DirectoryManager.SETTINGS_DIR, ".first_launch_complete")
        self.runtime_installer = runtime_installer or RuntimeInstaller(logger=self.logger)

    def is_first_launch(self) -> bool:
        """Checks if the first launch flag file is missing."""
        return not os.path.exists(self.flag_file_path)

    def complete_first_launch(self) -> None:
        """Creates the flag file to mark first launch setup as complete."""
        try:
            os.makedirs(os.path.dirname(self.flag_file_path), exist_ok=True)
            with open(self.flag_file_path, "w", encoding="utf-8") as f:
                f.write("complete")
            self.logger.info("First launch completed and flag file created.")
        except Exception as e:
            self.logger.error(f"Failed to create first launch flag file: {e}")

    def generate_report(self) -> FirstLaunchReport:
        """Generates and returns a FirstLaunchReport diagnostics object."""
        return FirstLaunchReport()

    def run_first_launch_setup(self, progress_callback=None, status_callback=None) -> bool:
        """
        Runs the first-time startup wizard/setup pipeline:
        1. Checks if it's the first launch (if not, returns True immediately).
        2. Generates and saves an initial FirstLaunchReport.
        3. Installs missing dependencies (adb, scrcpy, ffmpeg) using RuntimeInstaller.
        4. Verifies if critical dependencies are present.
        5. Saves final FirstLaunchReport, marks first launch complete, and returns success status.
        """
        if not self.is_first_launch():
            self.logger.info("Not a first launch. Skipping setup orchestration.")
            return True

        self.logger.info("Initiating first launch setup process...")

        # Step 2: Initial diagnostics report
        initial_report = self.generate_report()
        initial_report.save_to_file()
        self.logger.info("Saved initial first launch diagnostic report.")

        # Step 3: Run runtime installation for missing components
        self.logger.info("Installing missing dependencies...")
        results = self.runtime_installer.install_all_missing(
            progress_callback=progress_callback,
            status_callback=status_callback
        )
        self.logger.info(f"Dependency installation results: {results}")

        # Step 4: Validate required dependencies (adb and scrcpy)
        # Note: we check via the runtime manager directly to ensure actual status is updated
        rm = self.runtime_installer.runtime_manager
        adb_ready = rm.check_installed("adb")
        scrcpy_ready = rm.check_installed("scrcpy")

        # Step 5: Save post-install report
        final_report = self.generate_report()
        final_report.save_to_file()
        self.logger.info("Saved final first launch diagnostic report.")

        if adb_ready and scrcpy_ready:
            self.complete_first_launch()
            self.logger.info("First launch setup completed successfully.")
            return True
        else:
            self.logger.error(
                f"First launch setup failed: Missing critical dependencies (ADB ready: {adb_ready}, scrcpy ready: {scrcpy_ready})"
            )
            return False
