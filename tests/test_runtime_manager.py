import os
import sys
import unittest
import shutil
import zipfile
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.runtime_manager import RuntimeManager
from services.github_service import GitHubService
from services.directory_manager import DirectoryManager

class TestRuntimeManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up a clean temporary BIN_DIR and CACHE_DIR specifically for runtime testing
        cls.temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_runtime_test")
        os.makedirs(cls.temp_dir, exist_ok=True)
        
        # Override DirectoryManager directories to point to our sandbox
        cls.orig_bin = DirectoryManager.BIN_DIR
        cls.orig_cache = DirectoryManager.CACHE_DIR
        
        DirectoryManager.BIN_DIR = os.path.join(cls.temp_dir, "bin")
        DirectoryManager.CACHE_DIR = os.path.join(cls.temp_dir, "cache")
        os.makedirs(DirectoryManager.BIN_DIR, exist_ok=True)
        os.makedirs(DirectoryManager.CACHE_DIR, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        # Restore original paths
        DirectoryManager.BIN_DIR = cls.orig_bin
        DirectoryManager.CACHE_DIR = cls.orig_cache
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)

    def setUp(self):
        self.mock_github = MagicMock(spec=GitHubService)
        self.manager = RuntimeManager(github_service=self.mock_github)

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_get_installed_version_scrcpy(self, mock_which, mock_run):
        # Setup mock paths and search result
        mock_which.return_value = "/usr/bin/scrcpy"
        
        # Mock subprocess execution result for scrcpy --version
        mock_res = MagicMock()
        mock_res.stdout = "scrcpy v2.4 <https://github.com/Genymobile/scrcpy>\n"
        mock_res.stderr = ""
        mock_run.return_value = mock_res
        
        with patch("os.path.exists", return_value=True):
            version = self.manager.get_installed_version("scrcpy")
        
        self.assertEqual(version, "2.4")
        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_get_installed_version_adb(self, mock_which, mock_run):
        mock_which.return_value = "/usr/bin/adb"
        
        mock_res = MagicMock()
        mock_res.stdout = "Android Debug Bridge version 1.0.41\nVersion 34.0.4-10411375\n"
        mock_res.stderr = ""
        mock_run.return_value = mock_res
        
        with patch("os.path.exists", return_value=True):
            version = self.manager.get_installed_version("adb")
        
        self.assertEqual(version, "1.0.41")

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_get_installed_version_ffmpeg(self, mock_which, mock_run):
        mock_which.return_value = "/usr/bin/ffmpeg"
        
        mock_res = MagicMock()
        mock_res.stdout = "ffmpeg version 6.0 Copyright (c) 2000-2023 the FFmpeg developers\n"
        mock_res.stderr = ""
        mock_run.return_value = mock_res
        
        with patch("os.path.exists", return_value=True):
            version = self.manager.get_installed_version("ffmpeg")
        
        self.assertEqual(version, "6.0")

    def test_check_latest_scrcpy(self):
        self.mock_github.check_latest_release.return_value = {
            "version": "2.4",
            "tag_name": "v2.4",
            "release_notes": "",
            "download_url": "",
            "assets": []
        }
        
        latest = self.manager.check_latest("scrcpy")
        
        self.assertEqual(latest, "2.4")
        self.mock_github.check_latest_release.assert_called_once_with("Genymobile/scrcpy")

    def test_check_latest_adb_fallback(self):
        latest = self.manager.check_latest("adb")
        self.assertEqual(latest, "34.0.4")

    def test_remove_and_update(self):
        # 1. Create a dummy ZIP update package
        zip_path = os.path.join(DirectoryManager.CACHE_DIR, "dummy_runtime.zip")
        with zipfile.ZipFile(zip_path, 'w') as z:
            z.writestr("scrcpy/scrcpy.exe", "binary contents")
            z.writestr("scrcpy/SDL2.dll", "sdl contents")
            
        # 2. Call update
        self.manager.update("scrcpy", zip_path)
        
        # Verify files were extracted and moved into bin/scrcpy
        target_dir = os.path.join(DirectoryManager.BIN_DIR, "scrcpy")
        self.assertTrue(os.path.exists(target_dir))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "scrcpy.exe")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "SDL2.dll")))
        
        # 3. Test removal
        self.manager.remove("scrcpy")
        self.assertFalse(os.path.exists(target_dir))
        
        # Cleanup zip
        os.remove(zip_path)

    def test_get_install_directory(self):
        # Stub get_bin_path to return None to trigger fallback under BIN_DIR
        with patch.object(self.manager, "get_bin_path", return_value=None):
            dir_path = self.manager.get_install_directory("platform-tools")
            self.assertTrue(dir_path.endswith("adb"))
        
        # Test directory of an existing bin path
        with patch.object(self.manager, "get_bin_path", return_value="/mock/bin/scrcpy/scrcpy"):
            with patch("os.path.exists", return_value=True):
                dir_path = self.manager.get_install_directory("scrcpy")
                self.assertEqual(dir_path, "/mock/bin/scrcpy")

    def test_is_update_available(self):
        # 1. Update available: installed < latest
        with patch.object(self.manager, "get_installed_version", return_value="1.0.0"):
            with patch.object(self.manager, "check_latest", return_value="2.0.0"):
                self.assertTrue(self.manager.is_update_available("scrcpy"))
                
        # 2. Up to date: installed == latest
        with patch.object(self.manager, "get_installed_version", return_value="2.0.0"):
            with patch.object(self.manager, "check_latest", return_value="2.0.0"):
                self.assertFalse(self.manager.is_update_available("scrcpy"))

        # 3. Not installed locally: returns True
        with patch.object(self.manager, "get_installed_version", return_value=None):
            self.assertTrue(self.manager.is_update_available("scrcpy"))

    def test_platform_tools_normalization(self):
        # Test that platform-tools normalizes to adb for get_installed_version
        with patch.object(self.manager, "get_bin_path") as mock_bin_path:
            mock_bin_path.return_value = None
            self.manager.get_installed_version("platform-tools")
            mock_bin_path.assert_called_with("adb")


if __name__ == "__main__":
    unittest.main()
