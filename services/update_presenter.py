import os
import sys
import threading
import subprocess
from services.event_bus import (
    EventBus, UpdateAvailableEvent, UpdateNotAvailableEvent,
    DownloadProgressEvent, DownloadPausedEvent, DownloadResumedEvent,
    DownloadFinishedEvent, DownloadFailedEvent, InstallReadyEvent
)
from services.update_coordinator import UpdateCoordinator
from services.update_dialog import UpdateDialog

class UpdatePresenter:
    def __init__(self, coordinator: UpdateCoordinator, event_bus: EventBus, ui_view):
        """Initializes the UpdatePresenter.
        Subscribes to update events and maps them to UI state changes.
        """
        self.coordinator = coordinator
        self.event_bus = event_bus
        self.ui_view = ui_view
        self.dialog = None

        # Subscribe to update events
        self.event_bus.subscribe(UpdateAvailableEvent, self.handle_update_available)
        self.event_bus.subscribe(UpdateNotAvailableEvent, self.handle_update_not_available)
        self.event_bus.subscribe(DownloadProgressEvent, self.handle_download_progress)
        self.event_bus.subscribe(DownloadPausedEvent, self.handle_download_paused)
        self.event_bus.subscribe(DownloadResumedEvent, self.handle_download_resumed)
        self.event_bus.subscribe(DownloadFailedEvent, self.handle_download_failed)
        self.event_bus.subscribe(InstallReadyEvent, self.handle_install_ready)
        self.event_bus.subscribe(DownloadFinishedEvent, self.handle_download_finished)

        # Bind the update badge click handler dynamically
        self.ui_view.badge_update.bind("<Button-1>", lambda e: self.on_badge_clicked())

    def handle_update_available(self, event: UpdateAvailableEvent):
        """Translates UpdateAvailableEvent into showing the update badge."""
        result = {
            "is_update_available": True,
            "latest_version": event.latest_version,
            "download_url": event.download_url,
            "release_notes": event.release_notes
        }
        try:
            self.ui_view.after(0, lambda: self._apply_update_result(result, True))
        except Exception:
            pass

    def handle_update_not_available(self, event: UpdateNotAvailableEvent):
        """Translates UpdateNotAvailableEvent into hiding the update badge."""
        result = {
            "is_update_available": False,
            "latest_version": event.current_version,
            "download_url": "",
            "release_notes": ""
        }
        try:
            self.ui_view.after(0, lambda: self._apply_update_result(result, False))
        except Exception:
            pass

    def _apply_update_result(self, result: dict, show: bool):
        self.ui_view.update_result = result
        self.ui_view.show_update_badge(show)

    def on_badge_clicked(self):
        """Triggered when the user clicks the Update badge on the toolbar.
        Opens the modern update dialog window.
        """
        result = getattr(self.ui_view, "update_result", None)
        if not result or not result.get("is_update_available"):
            return

        # Prepare callbacks for dialog interactions
        callbacks = {
            "on_update": self.start_download,
            "on_pause": self.coordinator.pause,
            "on_resume": self.coordinator.resume,
            "on_cancel": self.cancel_download,
            "on_install": self.start_installation,
            "on_close": self.close_dialog
        }

        self.dialog = UpdateDialog(
            parent=self.ui_view,
            current_version=self.ui_view.current_version,
            latest_version=result.get("latest_version"),
            release_notes=result.get("release_notes"),
            callbacks=callbacks
        )

    def start_download(self):
        """Starts the download process in a background thread."""
        result = self.ui_view.update_result
        if not result:
            return

        download_url = result.get("download_url")
        if not download_url:
            return

        if self.dialog:
            self.dialog.show_download_progress()

        # Run download in a background thread
        threading.Thread(
            target=self._run_download_thread,
            args=(download_url,),
            daemon=True
        ).start()

    def _run_download_thread(self, download_url):
        try:
            self.coordinator.download(download_url)
        except Exception:
            # Errors are handled via DownloadFailedEvent
            pass

    def cancel_download(self):
        """Cancels download and closes the dialog."""
        self.coordinator.cancel()
        self.close_dialog()

    def start_installation(self):
        """Prepares commands, executes updater, and closes main app."""
        try:
            args = self.coordinator.install()
            if os.name == 'nt':
                DETACHED_PROCESS = 0x00000008
                subprocess.Popen(args, creationflags=DETACHED_PROCESS, close_fds=True)
            else:
                subprocess.Popen(args, start_new_session=True, close_fds=True)
        except Exception:
            pass
        finally:
            self.close_dialog()
            self.ui_view.destroy()
            sys.exit(0)

    def close_dialog(self):
        """Closes the dialog safely."""
        if self.dialog:
            try:
                self.dialog.destroy()
            except Exception:
                pass
            self.dialog = None

    # Event Bus Subscription Handlers
    def handle_download_progress(self, event: DownloadProgressEvent):
        """Updates progress on the dialog in real-time."""
        if self.dialog and self.dialog.winfo_exists():
            prog = event.progress
            mb_downloaded = prog.downloaded_bytes / (1024 * 1024)
            mb_total = prog.total_bytes / (1024 * 1024)
            mb_speed = prog.speed / (1024 * 1024)
            
            try:
                self.ui_view.after(0, lambda: self.dialog.update_progress_ui(
                    percentage=prog.percentage,
                    downloaded_mb=mb_downloaded,
                    total_mb=mb_total,
                    speed_mb=mb_speed,
                    eta=prog.eta
                ))
            except Exception:
                pass

    def handle_download_paused(self, event: DownloadPausedEvent):
        # UI state transitions are handled internally in UpdateDialog toggle_pause
        pass

    def handle_download_resumed(self, event: DownloadResumedEvent):
        # Spawns a new download thread to resume Range download
        result = self.ui_view.update_result
        if result and result.get("download_url"):
            threading.Thread(
                target=self._run_download_thread,
                args=(result.get("download_url"),),
                daemon=True
            ).start()

    def handle_download_finished(self, event: DownloadFinishedEvent):
        """Triggers extract and payload validation in background thread."""
        threading.Thread(
            target=self._run_prepare_thread,
            args=(event.zip_path,),
            daemon=True
        ).start()

    def _run_prepare_thread(self, zip_path):
        try:
            self.coordinator.prepare(zip_path)
        except Exception as e:
            self.event_bus.publish(DownloadFailedEvent(error_message=str(e)))

    def handle_install_ready(self, event: InstallReadyEvent):
        """Renders installation confirmation on dialog."""
        if self.dialog and self.dialog.winfo_exists():
            try:
                self.ui_view.after(0, self.dialog.show_install_ready)
            except Exception:
                pass

    def handle_download_failed(self, event: DownloadFailedEvent):
        """Renders error screen on dialog."""
        if self.dialog and self.dialog.winfo_exists():
            try:
                self.ui_view.after(0, lambda: self.dialog.show_error(event.error_message))
            except Exception:
                pass
