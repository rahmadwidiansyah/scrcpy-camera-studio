import os
import platform
import json
import shutil
from datetime import datetime, timezone
from services.directory_manager import DirectoryManager
from services.runtime_manager import RuntimeManager

class FirstLaunchReport:
    """
    FirstLaunchReport collects system metrics, folder permissions, and dependency 
    statuses at the first run of the application to identify setup requirements.
    """
    def __init__(self, data=None):
        if data is None:
            self.data = self._generate_report()
        else:
            self.data = data

    def _generate_report(self) -> dict:
        """Gathers system information and prerequisite statuses."""
        # Get directories status
        dirs_info = {}
        for name, path in [
            ("bin", DirectoryManager.BIN_DIR),
            ("cache", DirectoryManager.CACHE_DIR),
            ("logs", DirectoryManager.LOGS_DIR),
            ("settings", DirectoryManager.SETTINGS_DIR),
        ]:
            exists = os.path.exists(path)
            writable = os.access(path, os.W_OK) if exists else False
            dirs_info[name] = {
                "path": os.path.abspath(path),
                "exists": exists,
                "writable": writable
            }

        # Initialize RuntimeManager to check installed versions
        rm = RuntimeManager()
        
        # Check dependencies status
        deps_info = {}
        for dep in ["adb", "scrcpy", "ffmpeg", "sdl2"]:
            installed = rm.check_installed(dep)
            path = rm.get_bin_path(dep)
            version = rm.get_installed_version(dep) if installed else None
            
            deps_info[dep] = {
                "installed": installed,
                "path": os.path.abspath(path) if path else None,
                "version": version
            }

        # Determine if required components are ready
        is_ready = deps_info["adb"]["installed"] and deps_info["scrcpy"]["installed"]

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "os": {
                "platform": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "architecture": platform.machine()
            },
            "directories": dirs_info,
            "dependencies": deps_info,
            "is_system_ready": is_ready
        }
        return report

    def to_dict(self) -> dict:
        """Returns the raw dictionary of the report."""
        return self.data

    def save_to_file(self, filepath=None):
        """Saves the report content to a JSON file."""
        if filepath is None:
            filepath = os.path.join(DirectoryManager.LOGS_DIR, "first_launch_report.json")
        
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)

    @classmethod
    def load_from_file(cls, filepath):
        """Loads a report from a JSON file and returns a FirstLaunchReport instance."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Report file not found at: {filepath}")
            
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data=data)
