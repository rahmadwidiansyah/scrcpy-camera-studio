import os
import sys
from config.app_info import AppInfo

class DirectoryManager:
    # APP_DIR menunjuk ke direktori instalasi atau script utama
    if getattr(sys, 'frozen', False):
        APP_DIR = os.path.dirname(sys.executable)
    else:
        # directory_manager.py berada di dalam folder services/
        APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Menentukan direktori data dinamis di AppData/Local untuk menghindari write-permission block di Program Files
    if os.name == 'nt':
        local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
        DATA_DIR = os.path.join(local_appdata, AppInfo.APP_NAME)
    else:
        DATA_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", AppInfo.APP_NAME)

    # Path folder dinamis untuk data runtime
    BIN_DIR = os.path.join(DATA_DIR, "runtime")
    CACHE_DIR = os.path.join(DATA_DIR, "cache")
    LOGS_DIR = os.path.join(DATA_DIR, "logs")
    SETTINGS_DIR = os.path.join(DATA_DIR, "settings")

    @classmethod
    def ensure_directories(cls):
        """Membuat seluruh folder runtime otomatis jika belum ada."""
        os.makedirs(cls.BIN_DIR, exist_ok=True)
        os.makedirs(cls.CACHE_DIR, exist_ok=True)
        os.makedirs(cls.LOGS_DIR, exist_ok=True)
        os.makedirs(cls.SETTINGS_DIR, exist_ok=True)

# Pastikan folder-folder terbuat saat modul diimpor pertama kali
DirectoryManager.ensure_directories()
