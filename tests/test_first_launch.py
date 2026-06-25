import os
import sys
import unittest
import shutil
import json
from unittest.mock import MagicMock, patch

# Ensure app directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.directory_manager import DirectoryManager
from services.first_launch_report import FirstLaunchReport
from services.runtime_installer import RuntimeInstaller
from services.first_launch_manager import FirstLaunchManager
from services.runtime_manager import RuntimeManager

class TestFirstLaunch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a temporary sandbox directory for file checks and saves
        cls.temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_first_launch_test")
        os.makedirs(cls.temp_dir, exist_ok=True)
        
        # Keep original directory manager folders to restore later
        cls.orig_bin = DirectoryManager.BIN_DIR
        cls.orig_cache = DirectoryManager.CACHE_DIR
        cls.orig_logs = DirectoryManager.LOGS_DIR
        cls.orig_settings = DirectoryManager.SETTINGS_DIR
        
        # Redirect folders to sandbox
        DirectoryManager.BIN_DIR = os.path.join(cls.temp_dir, "bin")
        DirectoryManager.CACHE_DIR = os.path.join(cls.temp_dir, "cache")
        DirectoryManager.LOGS_DIR = os.path.join(cls.temp_dir, "logs")
        DirectoryManager.SETTINGS_DIR = os.path.join(cls.temp_dir, "settings")
        
        os.makedirs(DirectoryManager.BIN_DIR, exist_ok=True)
        os.makedirs(DirectoryManager.CACHE_DIR, exist_ok=True)
        os.makedirs(DirectoryManager.LOGS_DIR, exist_ok=True)
        os.makedirs(DirectoryManager.SETTINGS_DIR, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        # Restore directory manager folders
        DirectoryManager.BIN_DIR = cls.orig_bin
        DirectoryManager.CACHE_DIR = cls.orig_cache
        DirectoryManager.LOGS_DIR = cls.orig_logs
        DirectoryManager.SETTINGS_DIR = cls.orig_settings
        
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)

    def test_first_launch_report_generation(self):
        # Generate report
        report = FirstLaunchReport()
        data = report.to_dict()
        
        # Verify structure
        self.assertIn("timestamp", data)
        self.assertIn("os", data)
        self.assertIn("directories", data)
        self.assertIn("dependencies", data)
        self.assertIn("is_system_ready", data)
        
        # Verify directory mapping details
        self.assertIn("bin", data["directories"])
        self.assertEqual(data["directories"]["bin"]["path"], os.path.abspath(DirectoryManager.BIN_DIR))
        
        # Verify file persistence
        report_path = os.path.join(DirectoryManager.LOGS_DIR, "test_report.json")
        if os.path.exists(report_path):
            os.remove(report_path)
            
        report.save_to_file(report_path)
        self.assertTrue(os.path.exists(report_path))
        
        # Verify loaded data match
        loaded = FirstLaunchReport.load_from_file(report_path)
        self.assertEqual(loaded.to_dict()["timestamp"], data["timestamp"])

    @patch("platform.system", return_value="Windows")
    def test_runtime_installer_success(self, mock_system):
        mock_rm = MagicMock(spec=RuntimeManager)
        mock_rm.download.return_value = os.path.join(DirectoryManager.CACHE_DIR, "dummy.zip")
        
        # Create dummy file to mimic a download payload
        dummy_zip = os.path.join(DirectoryManager.CACHE_DIR, "dummy.zip")
        with open(dummy_zip, "w") as f:
            f.write("dummy package content")
            
        installer = RuntimeInstaller(runtime_manager=mock_rm)
        result = installer.install_dependency("scrcpy")
        
        self.assertTrue(result)
        mock_rm.download.assert_called_once_with("scrcpy", progress_callback=None, status_callback=None)
        mock_rm.update.assert_called_once_with("scrcpy", dummy_zip)
        # Check cleanup of downloaded ZIP
        self.assertFalse(os.path.exists(dummy_zip))

    @patch("platform.system", return_value="Windows")
    def test_runtime_installer_failure(self, mock_system):
        mock_rm = MagicMock(spec=RuntimeManager)
        mock_rm.download.side_effect = Exception("Network timeout")
        
        installer = RuntimeInstaller(runtime_manager=mock_rm)
        result = installer.install_dependency("scrcpy")
        
        self.assertFalse(result)

    @patch("platform.system", return_value="Windows")
    def test_runtime_installer_install_all_missing(self, mock_system):
        mock_rm = MagicMock(spec=RuntimeManager)
        # Mock: adb is already installed, but scrcpy and ffmpeg are missing
        mock_rm.check_installed.side_effect = lambda name: name == "adb"
        
        dummy_zip_scrcpy = os.path.join(DirectoryManager.CACHE_DIR, "scrcpy_zip")
        dummy_zip_ffmpeg = os.path.join(DirectoryManager.CACHE_DIR, "ffmpeg_zip")
        
        def mock_download(name, progress_callback=None, status_callback=None):
            if name == "scrcpy":
                with open(dummy_zip_scrcpy, "w") as f: f.write("scrcpy content")
                return dummy_zip_scrcpy
            elif name == "ffmpeg":
                with open(dummy_zip_ffmpeg, "w") as f: f.write("ffmpeg content")
                return dummy_zip_ffmpeg
            raise ValueError(f"Unexpected download call for {name}")
            
        mock_rm.download.side_effect = mock_download
        
        installer = RuntimeInstaller(runtime_manager=mock_rm)
        results = installer.install_all_missing()
        
        self.assertEqual(results, {"adb": True, "scrcpy": True, "ffmpeg": True})
        mock_rm.update.assert_any_call("scrcpy", dummy_zip_scrcpy)
        mock_rm.update.assert_any_call("ffmpeg", dummy_zip_ffmpeg)
        self.assertFalse(os.path.exists(dummy_zip_scrcpy))
        self.assertFalse(os.path.exists(dummy_zip_ffmpeg))

    def test_first_launch_manager_detection_and_completion(self):
        flag_file = os.path.join(DirectoryManager.SETTINGS_DIR, "test_first_launch_flag")
        if os.path.exists(flag_file):
            os.remove(flag_file)
            
        manager = FirstLaunchManager(flag_file_path=flag_file)
        self.assertTrue(manager.is_first_launch())
        
        manager.complete_first_launch()
        self.assertFalse(manager.is_first_launch())
        self.assertTrue(os.path.exists(flag_file))
        
        # Cleanup
        os.remove(flag_file)

    def test_run_first_launch_setup_not_first(self):
        flag_file = os.path.join(DirectoryManager.SETTINGS_DIR, "test_first_launch_flag")
        with open(flag_file, "w") as f:
            f.write("complete")
            
        mock_installer = MagicMock(spec=RuntimeInstaller)
        manager = FirstLaunchManager(flag_file_path=flag_file, runtime_installer=mock_installer)
        
        result = manager.run_first_launch_setup()
        
        self.assertTrue(result)
        mock_installer.install_all_missing.assert_not_called()
        
        # Cleanup
        os.remove(flag_file)

    def test_run_first_launch_setup_success(self):
        flag_file = os.path.join(DirectoryManager.SETTINGS_DIR, "test_first_launch_flag")
        if os.path.exists(flag_file):
            os.remove(flag_file)
            
        mock_installer = MagicMock(spec=RuntimeInstaller)
        mock_rm = MagicMock(spec=RuntimeManager)
        # Mock both adb and scrcpy checking as installed at completion validation
        mock_rm.check_installed.return_value = True
        mock_installer.runtime_manager = mock_rm
        
        manager = FirstLaunchManager(flag_file_path=flag_file, runtime_installer=mock_installer)
        result = manager.run_first_launch_setup()
        
        self.assertTrue(result)
        mock_installer.install_all_missing.assert_called_once()
        self.assertFalse(manager.is_first_launch())
        self.assertTrue(os.path.exists(flag_file))
        
        # Verify reports are written
        initial_report_path = os.path.join(DirectoryManager.LOGS_DIR, "first_launch_report.json")
        self.assertTrue(os.path.exists(initial_report_path))
        
        # Cleanup
        os.remove(flag_file)

    def test_run_first_launch_setup_failure(self):
        flag_file = os.path.join(DirectoryManager.SETTINGS_DIR, "test_first_launch_flag")
        if os.path.exists(flag_file):
            os.remove(flag_file)
            
        mock_installer = MagicMock(spec=RuntimeInstaller)
        mock_rm = MagicMock(spec=RuntimeManager)
        # Mock dependencies check failed (not installed)
        mock_rm.check_installed.return_value = False
        mock_installer.runtime_manager = mock_rm
        
        manager = FirstLaunchManager(flag_file_path=flag_file, runtime_installer=mock_installer)
        result = manager.run_first_launch_setup()
        
        self.assertFalse(result)
        mock_installer.install_all_missing.assert_called_once()
        self.assertTrue(manager.is_first_launch())
        self.assertFalse(os.path.exists(flag_file))

if __name__ == "__main__":
    unittest.main()
