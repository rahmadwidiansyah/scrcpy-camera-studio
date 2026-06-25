import sys
import os
from services.update_service import UpdateService, InstallPlan, UpdateCheckResult
from services.event_bus import (
    EventBus, CheckStartedEvent, CheckFinishedEvent, UpdateAvailableEvent,
    UpdateNotAvailableEvent, DownloadStartedEvent, DownloadProgressEvent,
    DownloadPausedEvent, DownloadResumedEvent, DownloadFinishedEvent,
    DownloadFailedEvent, PrepareStartedEvent, PrepareFinishedEvent, InstallReadyEvent
)

class UpdateCoordinator:
    def __init__(self, update_service: UpdateService = None, event_bus: EventBus = None):
        """Initializes the UpdateCoordinator.
        Uses dependency injection to accept UpdateService and EventBus instances.
        """
        self.update_service = update_service or UpdateService()
        self.event_bus = event_bus or EventBus()
        self.current_plan = None

    def check(self) -> UpdateCheckResult:
        """Checks for application updates.
        Publishes CHECK_STARTED, CHECK_FINISHED, and either UPDATE_AVAILABLE or UPDATE_NOT_AVAILABLE.
        """
        self.event_bus.publish(CheckStartedEvent())
        try:
            result = self.update_service.check_update()
            self.event_bus.publish(CheckFinishedEvent(result=result))
            
            if result.is_available:
                self.event_bus.publish(UpdateAvailableEvent(
                    latest_version=result.latest_version,
                    download_url=result.download_url,
                    release_notes=result.release_notes
                ))
            else:
                self.event_bus.publish(UpdateNotAvailableEvent(
                    current_version=self.update_service.current_version
                ))
            return result
        except Exception as e:
            # Re-raise to conform to "melempar exception yang jelas"
            raise

    def download(self, download_url: str, progress_callback=None, status_callback=None) -> str:
        """Downloads the update package synchronously.
        Publishes DOWNLOAD_STARTED, DOWNLOAD_PROGRESS, DOWNLOAD_PAUSED, DOWNLOAD_FINISHED, and DOWNLOAD_FAILED.
        """
        self.event_bus.publish(DownloadStartedEvent(download_url=download_url))

        def progress_cb(progress):
            self.event_bus.publish(DownloadProgressEvent(progress=progress))
            if progress_callback:
                try:
                    progress_callback(progress)
                except Exception:
                    pass

        def status_cb(status, error):
            from services.download_manager import DownloadStatus
            if status == DownloadStatus.PAUSED:
                self.event_bus.publish(DownloadPausedEvent())
            elif status == DownloadStatus.CANCELLED:
                self.event_bus.publish(DownloadFailedEvent(error_message="Download cancelled by user."))
            elif status == DownloadStatus.FAILED:
                self.event_bus.publish(DownloadFailedEvent(error_message=str(error)))
                
            if status_callback:
                try:
                    status_callback(status, error)
                except Exception:
                    pass

        try:
            zip_path = self.update_service.download_update(
                download_url=download_url,
                progress_callback=progress_cb,
                status_callback=status_cb
            )
            self.event_bus.publish(DownloadFinishedEvent(zip_path=zip_path))
            return zip_path
        except Exception as e:
            self.event_bus.publish(DownloadFailedEvent(error_message=str(e)))
            raise

    def prepare(self, zip_path: str) -> InstallPlan:
        """Extracts, validates, and prepares the installation.
        Publishes PREPARE_STARTED, PREPARE_FINISHED, and INSTALL_READY.
        """
        self.event_bus.publish(PrepareStartedEvent(zip_path=zip_path))
        try:
            extract_dir = self.update_service.extract_update(zip_path)
            source_dir = self.update_service.validate_payload(extract_dir)
            self.event_bus.publish(PrepareFinishedEvent(extract_dir=extract_dir))
            
            plan = self.update_service.prepare_install(source_dir)
            self.current_plan = plan
            self.event_bus.publish(InstallReadyEvent(plan=plan))
            return plan
        except Exception as e:
            raise

    def install(self, plan: InstallPlan = None) -> list:
        """Prepares the command-line arguments to launch the standalone updater script."""
        target_plan = plan or self.current_plan
        if not target_plan:
            raise ValueError("No installation plan available to install.")

        # Re-derive archive path from cache directory
        archive_path = os.path.join(self.update_service.cache_dir, "update_package.zip")

        # Build arguments for updater.py
        args = [
            sys.executable,
            target_plan.updater_path,
            "--app-dir", target_plan.target_directory,
            "--archive", archive_path,
            "--main-script", "main.py",
            "--parent-pid", str(os.getpid())
        ]
        return args

    def pause(self):
        """Pauses the active download."""
        if self.update_service.downloader:
            self.update_service.downloader.pause()

    def resume(self):
        """Prepares the active download to resume.
        Publishes DOWNLOAD_RESUMED.
        """
        if self.update_service.downloader:
            self.update_service.downloader.resume()
            self.event_bus.publish(DownloadResumedEvent())

    def cancel(self):
        """Cancels the active download."""
        if self.update_service.downloader:
            self.update_service.downloader.cancel()
