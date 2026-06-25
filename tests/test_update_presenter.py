import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.event_bus import EventBus, UpdateAvailableEvent, UpdateNotAvailableEvent
from services.update_coordinator import UpdateCoordinator
from services.update_presenter import UpdatePresenter

class MockUIView:
    def __init__(self):
        self.update_result = None
        self.badge_visible = False
        self.badge_update = MagicMock()
        self.current_version = "1.0.0"

    def after(self, ms, callback):
        # Execute synchronously to make testing straightforward
        callback()

    def show_update_badge(self, show):
        self.badge_visible = show


class TestUpdatePresenter(unittest.TestCase):
    def setUp(self):
        self.event_bus = EventBus()
        self.mock_coordinator = MagicMock(spec=UpdateCoordinator)
        self.mock_view = MockUIView()
        self.presenter = UpdatePresenter(
            coordinator=self.mock_coordinator,
            event_bus=self.event_bus,
            ui_view=self.mock_view
        )

    def test_update_available_event_shows_badge(self):
        event = UpdateAvailableEvent(
            latest_version="1.2.0",
            download_url="http://example.com/update.zip",
            release_notes="Bug fixes and improvements"
        )
        
        self.event_bus.publish(event)
        
        # Verify view states
        self.assertTrue(self.mock_view.badge_visible)
        self.assertIsNotNone(self.mock_view.update_result)
        self.assertTrue(self.mock_view.update_result["is_update_available"])
        self.assertEqual(self.mock_view.update_result["latest_version"], "1.2.0")
        self.assertEqual(self.mock_view.update_result["download_url"], "http://example.com/update.zip")
        self.assertEqual(self.mock_view.update_result["release_notes"], "Bug fixes and improvements")

    def test_update_not_available_event_hides_badge(self):
        # Initialize as visible
        self.mock_view.badge_visible = True
        
        event = UpdateNotAvailableEvent(current_version="1.0.0")
        
        self.event_bus.publish(event)
        
        # Verify view states
        self.assertFalse(self.mock_view.badge_visible)
        self.assertIsNotNone(self.mock_view.update_result)
        self.assertFalse(self.mock_view.update_result["is_update_available"])
        self.assertEqual(self.mock_view.update_result["latest_version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
