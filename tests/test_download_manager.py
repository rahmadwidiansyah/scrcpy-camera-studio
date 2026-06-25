import os
import sys
import unittest
import threading
import time
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer

# Add project path to sys.path to import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.download_manager import (
    DownloadManager, DownloadStatus, DownloadProgress, DownloadError, ChecksumError
)

# Custom HTTP request handler to serve test files and support Range requests
class TestHTTPHandler(BaseHTTPRequestHandler):
    FILE_CONTENT = b"A" * 1024 * 100  # 100 KB test content
    
    def log_message(self, format, *args):
        # Suppress logging to keep unittest output clean
        pass
        
    def do_GET(self):
        if self.path == "/error":
            self.send_response(500)
            self.end_headers()
            return
            
        if self.path == "/content":
            content = self.FILE_CONTENT
            
            # Check for HTTP Range header
            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                try:
                    byte_range = range_header.split("=")[1]
                    start = int(byte_range.split("-")[0])
                    
                    self.send_response(206)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(content) - start))
                    self.send_header("Content-Range", f"bytes {start}-{len(content)-1}/{len(content)}")
                    self.end_headers()
                    self.wfile.write(content[start:])
                    return
                except Exception as e:
                    pass
            
            # Normal full content request
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)


class TestDownloadManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start a local HTTP server in a separate thread
        cls.server = HTTPServer(("127.0.0.1", 0), TestHTTPHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        
        # Paths for temporary files
        cls.temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_test")
        os.makedirs(cls.temp_dir, exist_ok=True)
        cls.dest_path = os.path.join(cls.temp_dir, "test_download.bin")
        
        # Calculate correct SHA-256 and MD5 hashes of test content
        cls.correct_sha256 = hashlib.sha256(TestHTTPHandler.FILE_CONTENT).hexdigest()
        cls.correct_md5 = hashlib.md5(TestHTTPHandler.FILE_CONTENT).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        # Clean up temp directory
        if os.path.exists(cls.dest_path):
            os.remove(cls.dest_path)
        if os.path.exists(cls.temp_dir):
            os.rmdir(cls.temp_dir)

    def setUp(self):
        # Make sure target file is removed before each test
        if os.path.exists(self.dest_path):
            os.remove(self.dest_path)

    def test_full_download_success(self):
        progresses = []
        statuses = []
        
        def progress_cb(progress):
            progresses.append(progress)
            
        def status_cb(status, error):
            statuses.append(status)

        url = f"http://127.0.0.1:{self.port}/content"
        manager = DownloadManager(
            url=url,
            dest_path=self.dest_path,
            checksum=self.correct_sha256,
            checksum_algo="sha256",
            chunk_size=4096,  # small chunk to trigger multiple callback calls
            progress_callback=progress_cb,
            status_callback=status_cb
        )
        
        manager.download()
        
        self.assertEqual(manager.status, DownloadStatus.COMPLETED)
        self.assertTrue(os.path.exists(self.dest_path))
        self.assertEqual(os.path.getsize(self.dest_path), len(TestHTTPHandler.FILE_CONTENT))
        self.assertGreater(len(progresses), 0)
        self.assertEqual(progresses[-1].downloaded_bytes, len(TestHTTPHandler.FILE_CONTENT))
        self.assertEqual(progresses[-1].percentage, 100.0)
        self.assertIn(DownloadStatus.DOWNLOADING, statuses)
        self.assertIn(DownloadStatus.COMPLETED, statuses)

    def test_checksum_verification_fail(self):
        url = f"http://127.0.0.1:{self.port}/content"
        bad_checksum = "0" * 64
        
        manager = DownloadManager(
            url=url,
            dest_path=self.dest_path,
            checksum=bad_checksum,
            checksum_algo="sha256"
        )
        
        with self.assertRaises(ChecksumError):
            manager.download()
            
        self.assertEqual(manager.status, DownloadStatus.FAILED)
        self.assertIsInstance(manager.error, ChecksumError)

    def test_pause_and_resume(self):
        url = f"http://127.0.0.1:{self.port}/content"
        
        # Create a manager instance
        manager = DownloadManager(
            url=url,
            dest_path=self.dest_path,
            checksum=self.correct_sha256,
            chunk_size=4096
        )
        
        # Pause hook inside progress callback
        def progress_cb_with_pause(progress):
            if progress.downloaded_bytes > 20000:
                manager.pause()
                
        manager.progress_callback = progress_cb_with_pause
        
        # Start download. It should pause during the process.
        manager.download()
        
        self.assertEqual(manager.status, DownloadStatus.PAUSED)
        self.assertTrue(os.path.exists(self.dest_path))
        partial_size = os.path.getsize(self.dest_path)
        self.assertGreater(partial_size, 0)
        self.assertLess(partial_size, len(TestHTTPHandler.FILE_CONTENT))
        
        # Now remove the callback pause condition and resume
        manager.progress_callback = None
        manager.resume()
        self.assertEqual(manager.status, DownloadStatus.IDLE)
        
        # Continue downloading
        manager.download()
        
        self.assertEqual(manager.status, DownloadStatus.COMPLETED)
        self.assertEqual(os.path.getsize(self.dest_path), len(TestHTTPHandler.FILE_CONTENT))

    def test_cancel_removes_file(self):
        url = f"http://127.0.0.1:{self.port}/content"
        
        manager = DownloadManager(
            url=url,
            dest_path=self.dest_path,
            chunk_size=1024
        )
        
        def progress_cb_with_cancel(progress):
            if progress.downloaded_bytes > 5000:
                manager.cancel()
                
        manager.progress_callback = progress_cb_with_cancel
        
        manager.download()
        
        self.assertEqual(manager.status, DownloadStatus.CANCELLED)
        # Verify file is deleted upon cancellation
        self.assertFalse(os.path.exists(self.dest_path))

    def test_retry_after_failure(self):
        url = f"http://127.0.0.1:{self.port}/error"
        
        manager = DownloadManager(
            url=url,
            dest_path=self.dest_path,
            max_retries=0  # Fail fast
        )
        
        # Should raise DownloadError on HTTP 500
        with self.assertRaises(DownloadError):
            manager.download()
            
        self.assertEqual(manager.status, DownloadStatus.FAILED)
        
        # Correct the URL to target successful path and retry
        manager.url = f"http://127.0.0.1:{self.port}/content"
        manager.checksum = self.correct_md5
        manager.checksum_algo = "md5"
        
        # retry() resets state and executes download synchronously
        manager.retry()
        
        self.assertEqual(manager.status, DownloadStatus.COMPLETED)
        self.assertEqual(os.path.getsize(self.dest_path), len(TestHTTPHandler.FILE_CONTENT))


if __name__ == "__main__":
    unittest.main()
