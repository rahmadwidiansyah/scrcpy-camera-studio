import os
import sys
import unittest
from unittest.mock import MagicMock

# Add project path to sys.path to import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.update_coordinator import UpdateCoordinator
from services.update_service import UpdateService, InstallPlan, UpdateCheckResult
from services.download_manager import DownloadManager, DownloadStatus
from services.event_bus import (
    EventBus, CheckStartedEvent, CheckFinishedEvent, UpdateAvailableEvent,
    UpdateNotAvailableEvent, DownloadStartedEvent, DownloadProgressEvent,
    DownloadPausedEvent, DownloadResumedEvent, DownloadFinishedEvent,
    DownloadFailedEvent, PrepareStartedEvent, PrepareFinishedEvent, InstallReadyEvent
)

class TestUpdateCoordinator(unittest.TestCase):
    def setUp(self):
        self.mock_service = MagicMock(spec=UpdateService)
        self.mock_service.cache_dir = "/tmp/mock_cache"
        self.mock_service.current_version = "1.0.0"
        
        self.event_bus = EventBus()
        self.coordinator = UpdateCoordinator(
            update_service=self.mock_service,
            event_bus=self.event_bus
        )
        self.published_events = []
        
        # Subscribe a generic handler to capture all published events
        # Since self.event_bus.publish publishes by exact type, we can subscribe to all individual types
        self.event_types = [
            CheckStartedEvent, CheckFinishedEvent, UpdateAvailableEvent,
            UpdateNotAvailableEvent, DownloadStartedEvent, DownloadProgressEvent,
            DownloadPausedEvent, DownloadResumedEvent, DownloadFinishedEvent,
            DownloadFailedEvent, PrepareStartedEvent, PrepareFinishedEvent, InstallReadyEvent
        ]
        for etype in self.event_types:
            self.event_bus.subscribe(etype, self._capture_event)

    def _capture_event(self, event):
        self.published_events.append(event)

    def test_check_delegation_and_events(self):
        expected_result = UpdateCheckResult(
            is_available=True,
            latest_version="1.2.0",
            download_url="http://example.com/update.zip",
            release_notes="New release notes"
        )
        self.mock_service.check_update.return_value = expected_result
        
        result = self.coordinator.check()
        
        self.mock_service.check_update.assert_called_once()
        self.assertEqual(result, expected_result)
        
        # Assert events were published
        event_types = [type(e) for e in self.published_events]
        self.assertIn(CheckStartedEvent, event_types)
        self.assertIn(CheckFinishedEvent, event_types)
        self.assertIn(UpdateAvailableEvent, event_types)
        
        # Check specific event values
        avail_event = next(e for e in self.published_events if isinstance(e, UpdateAvailableEvent))
        self.assertEqual(avail_event.latest_version, "1.2.0")
        self.assertEqual(avail_event.download_url, "http://example.com/update.zip")

    def test_check_not_available_event(self):
        expected_result = UpdateCheckResult(
            is_available=False,
            latest_version="1.0.0",
            download_url="http://example.com/update.zip",
            release_notes="Already current"
        )
        self.mock_service.check_update.return_value = expected_result
        
        self.coordinator.check()
        
        event_types = [type(e) for e in self.published_events]
        self.assertIn(CheckStartedEvent, event_types)
        self.assertIn(CheckFinishedEvent, event_types)
        self.assertIn(UpdateNotAvailableEvent, event_types)

    def test_download_delegation_and_events(self):
        self.mock_service.download_update.return_value = "/tmp/mock_cache/update_package.zip"
        
        # Mock status callback triggers inside coordinator download
        def mock_download_impl(download_url, progress_callback, status_callback):
            # Simulate a progress call
            mock_progress = MagicMock()
            progress_callback(mock_progress)
            # Simulate complete status
            status_callback(DownloadStatus.COMPLETED, None)
            return "/tmp/mock_cache/update_package.zip"
            
        self.mock_service.download_update.side_effect = mock_download_impl
        
        result = self.coordinator.download(download_url="http://example.com/update.zip")
        
        self.assertEqual(result, "/tmp/mock_cache/update_package.zip")
        
        event_types = [type(e) for e in self.published_events]
        self.assertIn(DownloadStartedEvent, event_types)
        self.assertIn(DownloadProgressEvent, event_types)
        self.assertIn(DownloadFinishedEvent, event_types)

    def test_prepare_delegation_and_events(self):
        self.mock_service.extract_update.return_value = "/tmp/mock_cache/extracted"
        self.mock_service.validate_payload.return_value = "/tmp/mock_cache/extracted/payload"
        
        expected_plan = InstallPlan(
            source_directory="/tmp/mock_cache/extracted/payload",
            target_directory="/app",
            updater_path="/app/updater.py",
            current_version="1.0.0",
            latest_version="1.2.0",
            release_notes="New release notes"
        )
        self.mock_service.prepare_install.return_value = expected_plan
        
        plan = self.coordinator.prepare("/tmp/mock_cache/update_package.zip")
        
        self.assertEqual(plan, expected_plan)
        
        event_types = [type(e) for e in self.published_events]
        self.assertIn(PrepareStartedEvent, event_types)
        self.assertIn(PrepareFinishedEvent, event_types)
        self.assertIn(InstallReadyEvent, event_types)
        
        ready_event = next(e for e in self.published_events if isinstance(e, InstallReadyEvent))
        self.assertEqual(ready_event.plan, expected_plan)

    def test_install_builds_correct_command(self):
        plan = InstallPlan(
            source_directory="/tmp/mock_cache/extracted/payload",
            target_directory="/app",
            updater_path="/app/updater.py",
            current_version="1.0.0",
            latest_version="1.2.0",
            release_notes="New release notes"
        )
        self.coordinator.current_plan = plan
        
        args = self.coordinator.install()
        
        # Normalize paths for platform independence in tests
        normalized_args = [os.path.normpath(arg) for arg in args]
        
        self.assertIn(os.path.normpath("/app/updater.py"), normalized_args)
        self.assertIn(os.path.normpath("/app"), normalized_args)
        self.assertIn(os.path.normpath("/tmp/mock_cache/update_package.zip"), normalized_args)
        self.assertIn("main.py", args)

    def test_download_controls_and_events(self):
        mock_downloader = MagicMock(spec=DownloadManager)
        self.mock_service.downloader = mock_downloader
        
        self.coordinator.pause()
        mock_downloader.pause.assert_called_once()
        
        self.coordinator.resume()
        mock_downloader.resume.assert_called_once()
        
        self.coordinator.cancel()
        mock_downloader.cancel.assert_called_once()
        
        event_types = [type(e) for e in self.published_events]
        self.assertIn(DownloadResumedEvent, event_types)


if __name__ == "__main__":
    unittest.main()
