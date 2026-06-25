import os
import time
import hashlib
from enum import Enum, auto
from dataclasses import dataclass
import requests

class DownloadStatus(Enum):
    IDLE = auto()
    DOWNLOADING = auto()
    PAUSED = auto()
    CANCELLED = auto()
    COMPLETED = auto()
    FAILED = auto()

@dataclass
class DownloadProgress:
    downloaded_bytes: int
    total_bytes: int
    percentage: float
    speed: float  # bytes per second
    eta: float    # remaining seconds
    status: DownloadStatus

class DownloadError(Exception):
    """Exception raised for general download errors."""
    pass

class ChecksumError(DownloadError):
    """Exception raised when the downloaded file's checksum does not match."""
    pass

class DownloadManager:
    def __init__(
        self,
        url: str,
        dest_path: str,
        checksum: str = None,
        checksum_algo: str = "sha256",
        chunk_size: int = 16384,
        max_retries: int = 3,
        timeout: int = 10,
        progress_callback=None,
        status_callback=None
    ):
        self.url = url
        self.dest_path = dest_path
        self.checksum = checksum
        self.checksum_algo = checksum_algo.lower()
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.timeout = timeout
        
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        
        self.session = requests.Session()
        
        self._is_paused = False
        self._is_cancelled = False
        self._status = DownloadStatus.IDLE
        self.error = None
        
        self.downloaded_bytes = 0
        self.total_bytes = 0

    @property
    def status(self) -> DownloadStatus:
        return self._status

    @status.setter
    def status(self, new_status: DownloadStatus):
        if self._status != new_status:
            self._status = new_status
            if self.status_callback:
                try:
                    self.status_callback(self._status, self.error)
                except Exception:
                    pass

    def pause(self):
        """Pauses the active download stream."""
        self._is_paused = True

    def resume(self):
        """Resets pause/cancel flags so download can be run again."""
        self._is_paused = False
        self._is_cancelled = False
        self.error = None
        self.status = DownloadStatus.IDLE

    def cancel(self):
        """Cancels the active download and schedules cleanup."""
        self._is_cancelled = True

    def retry(self):
        """Resets download manager state and runs download again."""
        self.resume()
        self.download()

    def verify_checksum(self) -> bool:
        """Verifies the checksum of the downloaded file.
        Raises ChecksumError if it doesn't match the expected value.
        """
        if not self.checksum:
            return True
            
        if not os.path.exists(self.dest_path):
            raise DownloadError(f"Destination file {self.dest_path} not found.")

        try:
            h = hashlib.new(self.checksum_algo)
        except ValueError as e:
            raise DownloadError(f"Unsupported checksum algorithm: {self.checksum_algo}") from e

        try:
            with open(self.dest_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    h.update(chunk)
            calculated = h.hexdigest().lower()
            expected = self.checksum.lower()
            if calculated != expected:
                raise ChecksumError(
                    f"Checksum verification failed for {self.dest_path}.\n"
                    f"Expected: {expected} ({self.checksum_algo})\n"
                    f"Calculated: {calculated}"
                )
            return True
        except ChecksumError:
            raise
        except Exception as e:
            raise DownloadError(f"Error reading file for checksum: {e}") from e

    def download(self):
        """Starts or resumes the download process synchronously.
        Implements automatic retries with exponential backoff on connection drops.
        """
        self._is_paused = False
        self._is_cancelled = False
        self.error = None
        self.status = DownloadStatus.DOWNLOADING
        
        attempt = 0
        while attempt <= self.max_retries:
            try:
                self._download_loop()
                if self.status == DownloadStatus.COMPLETED:
                    return
                elif self.status in (DownloadStatus.PAUSED, DownloadStatus.CANCELLED):
                    return
            except ChecksumError as e:
                self.error = e
                self.status = DownloadStatus.FAILED
                raise
            except (requests.RequestException, IOError, DownloadError) as e:
                attempt += 1
                if attempt > self.max_retries or self._is_paused or self._is_cancelled:
                    self.error = e
                    self.status = DownloadStatus.FAILED
                    raise DownloadError(f"Download failed after {attempt} attempts: {e}") from e
                
                # Exponential backoff (1s, 2s, 4s, 8s...)
                time.sleep(min(2 ** attempt, 10))

    def _download_loop(self):
        existing_bytes = 0
        if os.path.exists(self.dest_path):
            existing_bytes = os.path.getsize(self.dest_path)
            
        headers = {}
        if existing_bytes > 0:
            headers["Range"] = f"bytes={existing_bytes}-"

        if self._is_cancelled:
            self._handle_cancel()
            return

        try:
            response = self.session.get(self.url, headers=headers, stream=True, timeout=self.timeout)
        except requests.RequestException as e:
            # Fallback if range request gets rejected upfront
            if existing_bytes > 0:
                existing_bytes = 0
                response = self.session.get(self.url, stream=True, timeout=self.timeout)
            else:
                raise e

        # Handle 416 Range Not Satisfiable
        if response.status_code == 416:
            if self.checksum:
                try:
                    self.verify_checksum()
                    self.status = DownloadStatus.COMPLETED
                    return
                except ChecksumError:
                    pass
            # Start over from scratch
            if os.path.exists(self.dest_path):
                os.remove(self.dest_path)
            existing_bytes = 0
            response = self.session.get(self.url, stream=True, timeout=self.timeout)

        if response.status_code not in (200, 206):
            raise DownloadError(f"Server returned unexpected HTTP status: {response.status_code}")

        # Determine writing mode and offset
        if response.status_code == 206:
            write_mode = "ab"
            self.downloaded_bytes = existing_bytes
            content_length = int(response.headers.get("content-length", 0))
            self.total_bytes = content_length + existing_bytes
        else:
            write_mode = "wb"
            self.downloaded_bytes = 0
            self.total_bytes = int(response.headers.get("content-length", 0))

        dest_dir = os.path.dirname(self.dest_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)

        session_start_time = time.time()
        session_downloaded = 0

        cancelled_mid_download = False
        paused_mid_download = False

        try:
            with open(self.dest_path, write_mode) as f:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if self._is_cancelled:
                        cancelled_mid_download = True
                        break
                        
                    if self._is_paused:
                        paused_mid_download = True
                        break
                        
                    if chunk:
                        f.write(chunk)
                        session_downloaded += len(chunk)
                        self.downloaded_bytes = existing_bytes + session_downloaded
                        
                        elapsed = time.time() - session_start_time
                        speed = session_downloaded / elapsed if elapsed > 0 else 0.0
                        
                        if self.total_bytes > 0:
                            percentage = (self.downloaded_bytes / self.total_bytes) * 100.0
                            remaining_bytes = self.total_bytes - self.downloaded_bytes
                            eta = remaining_bytes / speed if speed > 0 else 0.0
                        else:
                            percentage = 0.0
                            eta = 0.0
                            
                        if self.progress_callback:
                            progress = DownloadProgress(
                                downloaded_bytes=self.downloaded_bytes,
                                total_bytes=self.total_bytes,
                                percentage=percentage,
                                speed=speed,
                                eta=eta,
                                status=DownloadStatus.DOWNLOADING
                            )
                            try:
                                self.progress_callback(progress)
                            except Exception:
                                pass
        finally:
            pass

        if cancelled_mid_download:
            self._handle_cancel()
            return
        if paused_mid_download:
            self.status = DownloadStatus.PAUSED
            return

        # Download completed, run verification
        if self.checksum:
            try:
                self.verify_checksum()
            except ChecksumError as e:
                self.error = e
                self.status = DownloadStatus.FAILED
                raise e
                
        self.status = DownloadStatus.COMPLETED

    def _handle_cancel(self):
        self.status = DownloadStatus.CANCELLED
        if os.path.exists(self.dest_path):
            try:
                os.remove(self.dest_path)
            except Exception:
                pass

    def close(self):
        """Closes the HTTP session to release resources."""
        self.session.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
