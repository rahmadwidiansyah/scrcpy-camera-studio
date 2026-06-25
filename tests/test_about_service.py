import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure app directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.about_service import AboutService, BuildInfo
from services.runtime_manager import RuntimeManager
from config.version import VersionManager
from config.app_info import AppInfo

class TestAboutServiceAndBuildInfo(unittest.TestCase):
    def test_build_info_methods(self):
        # BuildInfo returns default attributes if build_info.py doesn't have them
        self.assertIsNotNone(BuildInfo.get_build_date())
        self.assertIsNotNone(BuildInfo.get_commit())
        self.assertIsNotNone(BuildInfo.get_branch())
        self.assertIsInstance(BuildInfo.is_dirty(), bool)

    def test_about_service_without_runtime_manager(self):
        service = AboutService()
        info = service.get_about_info()
        
        self.assertEqual(info["app_name"], AppInfo.APP_NAME)
        self.assertEqual(info["version"], VersionManager.CURRENT_VERSION)
        self.assertEqual(info["build_number"], VersionManager.BUILD_NUMBER)
        self.assertEqual(info["release_channel"], VersionManager.RELEASE_CHANNEL)
        self.assertEqual(info["version_string"], VersionManager.get_version_string())
        self.assertEqual(info["runtimes"], {})

    def test_about_service_with_runtime_manager(self):
        mock_rm = MagicMock(spec=RuntimeManager)
        
        # Setup mock behavior
        mock_rm.check_installed.side_effect = lambda name: name in ["adb", "scrcpy"]
        mock_rm.get_installed_version.side_effect = lambda name: "1.0.41" if name == "adb" else ("2.4" if name == "scrcpy" else None)

        service = AboutService(runtime_manager=mock_rm)
        info = service.get_about_info()

        self.assertTrue(info["runtimes"]["adb"]["installed"])
        self.assertEqual(info["runtimes"]["adb"]["version"], "1.0.41")
        self.assertTrue(info["runtimes"]["scrcpy"]["installed"])
        self.assertEqual(info["runtimes"]["scrcpy"]["version"], "2.4")
        self.assertFalse(info["runtimes"]["ffmpeg"]["installed"])
        self.assertEqual(info["runtimes"]["ffmpeg"]["version"], "unknown")

if __name__ == "__main__":
    unittest.main()
