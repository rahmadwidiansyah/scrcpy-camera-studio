import os
import sys
import platform
from typing import Dict, Any

# Ensure correct imports
from config.version import VersionManager
from config.app_info import AppInfo
try:
    from config import build_info
except ImportError:
    build_info = None

class BuildInfo:
    """Provides structured build information details."""
    @staticmethod
    def get_build_date() -> str:
        return getattr(build_info, "BUILD_DATE", "unknown")

    @staticmethod
    def get_commit() -> str:
        return getattr(build_info, "BUILD_COMMIT", "unknown")

    @staticmethod
    def get_branch() -> str:
        return getattr(build_info, "BUILD_BRANCH", "unknown")

    @staticmethod
    def is_dirty() -> bool:
        return getattr(build_info, "IS_DIRTY", False)


class AboutService:
    """
    AboutService coordinates software attributes including VersionManager,
    BuildInfo, and RuntimeManager to serve system and metadata info to the application.
    """
    def __init__(self, runtime_manager=None):
        self.runtime_manager = runtime_manager

    def get_about_info(self) -> Dict[str, Any]:
        """Returns details about the application version, build, system platform, and dependency runtimes."""
        info = {
            "app_name": AppInfo.APP_NAME,
            "version": VersionManager.CURRENT_VERSION,
            "build_number": VersionManager.BUILD_NUMBER,
            "release_channel": VersionManager.RELEASE_CHANNEL,
            "version_string": VersionManager.get_version_string(),
            "build_date": BuildInfo.get_build_date(),
            "commit": BuildInfo.get_commit(),
            "branch": BuildInfo.get_branch(),
            "is_dirty": BuildInfo.is_dirty(),
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "runtimes": {}
        }

        if self.runtime_manager:
            for runtime_name in ["adb", "scrcpy", "ffmpeg"]:
                installed = self.runtime_manager.check_installed(runtime_name)
                version = self.runtime_manager.get_installed_version(runtime_name) if installed else None
                info["runtimes"][runtime_name] = {
                    "installed": installed,
                    "version": version or "unknown"
                }

        return info
