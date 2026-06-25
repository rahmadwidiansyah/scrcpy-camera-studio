import os
import zipfile
import shutil
from dataclasses import dataclass
from packaging.version import parse as parse_version

from services.github_service import GitHubService
from services.download_manager import DownloadManager
from config.app_info import AppInfo
from config.version import VersionManager
from config.config import Config

@dataclass
class UpdateCheckResult:
    is_available: bool
    latest_version: str
    download_url: str
    release_notes: str

@dataclass
class InstallPlan:
    source_directory: str
    target_directory: str
    updater_path: str
    current_version: str
    latest_version: str
    release_notes: str

class UpdateServiceError(Exception):
    """Base exception for all UpdateService errors."""
    pass

class UpdateCheckError(UpdateServiceError):
    """Exception raised when checking for updates fails."""
    pass

class ExtractionError(UpdateServiceError):
    """Exception raised when extracting update files fails."""
    pass

class ValidationError(UpdateServiceError):
    """Exception raised when the update payload validation fails."""
    pass


class UpdateService:
    def __init__(self, repo: str = None, current_version: str = None, cache_dir: str = None, app_dir: str = None):
        self.repo = repo or AppInfo.REPO_NAME
        self.current_version = current_version or VersionManager.CURRENT_VERSION
        self.cache_dir = cache_dir or Config.CACHE_DIR
        self.app_dir = app_dir or Config.APP_DIR
        
        self.github_service = GitHubService()
        self.downloader = None
        self.latest_release_info = None

    def check_update(self) -> UpdateCheckResult:
        """Checks GitHub for the latest release and compares version strings.
        Returns an UpdateCheckResult dataclass.
        """
        try:
            release_info = self.github_service.check_latest_release(self.repo)
        except Exception as e:
            raise UpdateCheckError(f"Failed to check release from GitHub: {e}") from e

        if not release_info:
            raise UpdateCheckError("GitHub check returned no release data.")

        latest_ver_str = release_info.get("version", "").strip()
        download_url = release_info.get("download_url", "")
        
        # Prefer the first asset's download URL if assets exist
        assets = release_info.get("assets", [])
        if assets:
            download_url = assets[0].get("browser_download_url", download_url)

        is_available = False
        if latest_ver_str:
            try:
                is_available = parse_version(latest_ver_str) > parse_version(self.current_version)
            except Exception as parse_err:
                raise UpdateCheckError(f"Failed to parse release versions: {parse_err}") from parse_err

        self.latest_release_info = UpdateCheckResult(
            is_available=is_available,
            latest_version=latest_ver_str,
            download_url=download_url,
            release_notes=release_info.get("release_notes", "")
        )
        return self.latest_release_info

    def download_update(self, download_url: str, progress_callback=None, status_callback=None) -> str:
        """Synchronously downloads the update package from download_url.
        Returns the path of the downloaded file.
        """
        filename = "update_package.zip"
        dest_path = os.path.join(self.cache_dir, filename)
        
        self.downloader = DownloadManager(
            url=download_url,
            dest_path=dest_path,
            progress_callback=progress_callback,
            status_callback=status_callback
        )
        
        try:
            self.downloader.download()
        except Exception as e:
            raise UpdateServiceError(f"Failed to download update: {e}") from e
            
        return dest_path

    def extract_update(self, zip_path: str) -> str:
        """Extracts the update zip file to a temporary directory.
        Returns the path of the extraction directory.
        """
        if not os.path.exists(zip_path):
            raise ExtractionError(f"Update package not found at: {zip_path}")

        extract_dir = os.path.join(self.cache_dir, "temp_extracted_update")
        try:
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)
            os.makedirs(extract_dir, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
        except Exception as e:
            raise ExtractionError(f"Failed to extract update package: {e}") from e

        return extract_dir

    def validate_payload(self, extract_dir: str) -> str:
        """Generically validates the extracted payload.
        Resolves nested folders and verifies contents are not empty.
        Returns the resolved source root path.
        """
        if not os.path.exists(extract_dir) or not os.path.isdir(extract_dir):
            raise ValidationError(f"Extraction directory does not exist: {extract_dir}")

        items = os.listdir(extract_dir)
        if not items:
            raise ValidationError("Extracted update directory is empty.")

        # Resolve GitHub release zip nesting (typically repo-tag/ folder)
        source_root = extract_dir
        if len(items) == 1:
            nested_path = os.path.join(extract_dir, items[0])
            if os.path.isdir(nested_path):
                source_root = nested_path
                items = os.listdir(source_root)
                if not items:
                    raise ValidationError(f"Nested update folder {items[0]} is empty.")

        return source_root

    def prepare_install(self, source_directory: str) -> InstallPlan:
        """Generates the InstallPlan dataclass containing directories and versions.
        Ensures the standalone updater script is present.
        """
        updater_script_path = os.path.join(self.app_dir, "updater.py")
        if not os.path.exists(updater_script_path):
            raise ValidationError(f"Standalone updater.py not found at: {updater_script_path}")

        if not self.latest_release_info:
            raise UpdateServiceError("Cannot prepare installation plan: check_update() must be called first.")

        return InstallPlan(
            source_directory=source_directory,
            target_directory=self.app_dir,
            updater_path=updater_script_path,
            current_version=self.current_version,
            latest_version=self.latest_release_info.latest_version,
            release_notes=self.latest_release_info.release_notes
        )
