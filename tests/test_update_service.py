import os
import sys
import unittest
import threading
import zipfile
import shutil
from unittest.mock import MagicMock
from http.server import BaseHTTPRequestHandler, HTTPServer

# Add project path to sys.path to import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.update_service import (
    UpdateService, UpdateCheckResult, InstallPlan, UpdateServiceError,
    UpdateCheckError, ExtractionError, ValidationError
)

# Custom HTTP request handler to serve our mock update zip file
class TestHTTPHandler(BaseHTTPRequestHandler):
    MOCK_ZIP_DATA = b""
    
    def log_message(self, format, *args):
        pass
        
    def do_GET(self):
        if self.path == "/update.zip":
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(self.MOCK_ZIP_DATA)))
            self.end_headers()
            self.wfile.write(self.MOCK_ZIP_DATA)
            return
            
        self.send_response(404)
        self.end_headers()


class TestUpdateService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up temporary testing directory
        cls.temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_update_test")
        os.makedirs(cls.temp_dir, exist_ok=True)
        
        cls.cache_dir = os.path.join(cls.temp_dir, "cache")
        cls.app_dir = os.path.join(cls.temp_dir, "app")
        os.makedirs(cls.cache_dir, exist_ok=True)
        os.makedirs(cls.app_dir, exist_ok=True)
        
        # Create a mock updater.py in the app directory to satisfy check requirements
        cls.mock_updater_path = os.path.join(cls.app_dir, "updater.py")
        with open(cls.mock_updater_path, "w") as f:
            f.write("# Mock updater script")
            
        # Generate a valid mock ZIP archive in memory/bytes
        cls.zip_file_path = os.path.join(cls.temp_dir, "content.zip")
        with zipfile.ZipFile(cls.zip_file_path, "w") as z:
            # Create GitHub-like nested layout
            z.writestr("camera-studio-1.1.0/manifest.json", '{"name": "CameraStudio", "version": "1.1.0"}')
            z.writestr("camera-studio-1.1.0/assets/some_config.json", "{}")
            
        with open(cls.zip_file_path, "rb") as f:
            TestHTTPHandler.MOCK_ZIP_DATA = f.read()
            
        # Start local HTTP server
        cls.server = HTTPServer(("127.0.0.1", 0), TestHTTPHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        # Clean up temporary test files
        if os.path.exists(cls.zip_file_path):
            os.remove(cls.zip_file_path)
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)

    def test_check_update_available(self):
        service = UpdateService(
            repo="dummy/repo",
            current_version="1.0.0",
            cache_dir=self.cache_dir,
            app_dir=self.app_dir
        )
        
        # Mock GitHubService's response to simulate update available (1.1.0 > 1.0.0)
        service.github_service.check_latest_release = MagicMock(return_value={
            "tag_name": "v1.1.0",
            "version": "1.1.0",
            "release_notes": "First major update",
            "download_url": f"http://127.0.0.1:{self.port}/update.zip",
            "assets": []
        })
        
        result = service.check_update()
        
        self.assertIsInstance(result, UpdateCheckResult)
        self.assertTrue(result.is_available)
        self.assertEqual(result.latest_version, "1.1.0")
        self.assertEqual(result.download_url, f"http://127.0.0.1:{self.port}/update.zip")
        self.assertEqual(result.release_notes, "First major update")

    def test_check_update_not_available(self):
        service = UpdateService(
            repo="dummy/repo",
            current_version="1.1.0",
            cache_dir=self.cache_dir,
            app_dir=self.app_dir
        )
        
        # Mock GitHubService's response to simulate same version (1.1.0 == 1.1.0)
        service.github_service.check_latest_release = MagicMock(return_value={
            "tag_name": "v1.1.0",
            "version": "1.1.0",
            "release_notes": "Already up to date",
            "download_url": f"http://127.0.0.1:{self.port}/update.zip",
            "assets": []
        })
        
        result = service.check_update()
        
        self.assertFalse(result.is_available)
        self.assertEqual(result.latest_version, "1.1.0")

    def test_full_update_flow(self):
        service = UpdateService(
            repo="dummy/repo",
            current_version="1.0.0",
            cache_dir=self.cache_dir,
            app_dir=self.app_dir
        )
        
        service.github_service.check_latest_release = MagicMock(return_value={
            "tag_name": "v1.1.0",
            "version": "1.1.0",
            "release_notes": "Awesome features",
            "download_url": f"http://127.0.0.1:{self.port}/update.zip",
            "assets": [
                {
                    "name": "update.zip",
                    "browser_download_url": f"http://127.0.0.1:{self.port}/update.zip",
                    "size": len(TestHTTPHandler.MOCK_ZIP_DATA)
                }
            ]
        })
        
        # 1. Check Update
        check_res = service.check_update()
        self.assertTrue(check_res.is_available)
        
        # 2. Download Update
        zip_path = service.download_update(check_res.download_url)
        self.assertTrue(os.path.exists(zip_path))
        self.assertEqual(os.path.getsize(zip_path), len(TestHTTPHandler.MOCK_ZIP_DATA))
        
        # 3. Extract Update
        extract_dir = service.extract_update(zip_path)
        self.assertTrue(os.path.exists(extract_dir))
        self.assertTrue(os.path.isdir(extract_dir))
        
        # 4. Validate Payload (handles nested directory in zip)
        source_dir = service.validate_payload(extract_dir)
        self.assertTrue(os.path.exists(os.path.join(source_dir, "manifest.json")))
        self.assertTrue(os.path.exists(os.path.join(source_dir, "assets", "some_config.json")))
        
        # 5. Prepare Install
        plan = service.prepare_install(source_dir)
        self.assertIsInstance(plan, InstallPlan)
        self.assertEqual(plan.source_directory, source_dir)
        self.assertEqual(plan.target_directory, self.app_dir)
        self.assertEqual(plan.updater_path, self.mock_updater_path)
        self.assertEqual(plan.current_version, "1.0.0")
        self.assertEqual(plan.latest_version, "1.1.0")
        self.assertEqual(plan.release_notes, "Awesome features")

    def test_validate_payload_empty_fails(self):
        service = UpdateService(
            repo="dummy/repo",
            current_version="1.0.0",
            cache_dir=self.cache_dir,
            app_dir=self.app_dir
        )
        
        empty_dir = os.path.join(self.temp_dir, "empty_dir")
        os.makedirs(empty_dir, exist_ok=True)
        
        with self.assertRaises(ValidationError):
            service.validate_payload(empty_dir)
            
        shutil.rmtree(empty_dir)

    def test_prepare_install_without_check_fails(self):
        service = UpdateService(
            repo="dummy/repo",
            current_version="1.0.0",
            cache_dir=self.cache_dir,
            app_dir=self.app_dir
        )
        
        with self.assertRaises(UpdateServiceError):
            service.prepare_install(self.cache_dir)

    def test_missing_updater_fails(self):
        # Point to a different folder where updater.py is missing
        missing_updater_app_dir = os.path.join(self.temp_dir, "missing_updater_app")
        os.makedirs(missing_updater_app_dir, exist_ok=True)
        
        service = UpdateService(
            repo="dummy/repo",
            current_version="1.0.0",
            cache_dir=self.cache_dir,
            app_dir=missing_updater_app_dir
        )
        
        service.github_service.check_latest_release = MagicMock(return_value={
            "tag_name": "v1.1.0",
            "version": "1.1.0",
            "release_notes": "Awesome features",
            "download_url": f"http://127.0.0.1:{self.port}/update.zip",
            "assets": []
        })
        
        service.check_update()
        
        with self.assertRaises(ValidationError):
            service.prepare_install(self.cache_dir)
            
        shutil.rmtree(missing_updater_app_dir)


if __name__ == "__main__":
    unittest.main()
