import os
import re
import shutil
import zipfile
import subprocess
import platform
from services.directory_manager import DirectoryManager
from services.github_service import GitHubService
from services.download_manager import DownloadManager

class RuntimeManager:
    @staticmethod
    def check_dependency(name):
        """
        Mengecek ketersediaan dependency dengan aturan prioritas:
        1. Cek folder lokal bin/ (dan subfolder scrcpy/) terlebih dahulu.
        2. Jika tidak ada, baru cek di PATH sistem.
        """
        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        exe_name = f"{name}.exe" if os.name == 'nt' else name
        bin_path = os.path.join(DirectoryManager.BIN_DIR, exe_name)
        bin_path_scrcpy = os.path.join(DirectoryManager.BIN_DIR, "scrcpy", exe_name)

        # Prioritas 1: Cek di folder bin/ lokal dan subfolder scrcpy/
        if os.path.exists(bin_path) or os.path.exists(bin_path_scrcpy):
            return True

        # Prioritas 2: Cek di System PATH (Global)
        if shutil.which(name):
            return True

        # Penanganan khusus untuk SDL2 (bawaan scrcpy)
        if name.lower() == "sdl2":
            sdl_lib = "SDL2.dll" if os.name == 'nt' else "libSDL2.so"
            if os.path.exists(os.path.join(DirectoryManager.BIN_DIR, sdl_lib)):
                return True
            if os.path.exists(os.path.join(DirectoryManager.BIN_DIR, "scrcpy", sdl_lib)):
                return True
            # Jika scrcpy global tersedia, asumsikan SDL2 juga aman di sistem
            if shutil.which("scrcpy"):
                return True

        return False

    @staticmethod
    def get_bin_path(name):
        """
        Mendapatkan path executable yang valid dengan aturan prioritas:
        1. Gunakan binary yang ada di folder bin/ lokal jika tersedia.
        2. Jika tidak ditemukan, cari dan gunakan path dari PATH sistem.
        3. Fallback ke default path jika tidak ditemukan di keduanya.
        """
        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        exe_name = f"{name}.exe" if os.name == 'nt' else name
        bin_path = os.path.join(DirectoryManager.BIN_DIR, exe_name)
        bin_path_scrcpy = os.path.join(DirectoryManager.BIN_DIR, "scrcpy", exe_name)

        # Prioritas 1: Gunakan biner dari folder bin/ lokal (atau subfolder scrcpy/) jika ada
        if os.path.exists(bin_path):
            return os.path.abspath(bin_path)
        if os.path.exists(bin_path_scrcpy):
            return os.path.abspath(bin_path_scrcpy)

        # Prioritas 2: Cari di PATH sistem jika tidak ditemukan di folder bin/
        system_path = shutil.which(name)
        if system_path:
            return system_path

        # Fallback terakhir jika benar-benar tidak ditemukan di mana pun
        return bin_path_scrcpy if os.path.exists(os.path.join(DirectoryManager.BIN_DIR, "scrcpy")) else bin_path

    # --- ADVANCED RUNTIME MANAGEMENT INSTANCE METHODS ---
    def __init__(self, github_service: GitHubService = None):
        self.github_service = github_service or GitHubService()
        self.downloaders = {}

    def check_installed(self, name: str) -> bool:
        """Verifies if the specified runtime is installed locally or globally."""
        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        return self.check_dependency(name)

    def get_install_directory(self, name: str) -> str:
        """Returns the installation directory for the specified runtime."""
        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        path = self.get_bin_path(name)
        if path and os.path.exists(path):
            return os.path.dirname(path)
        # Fallback to local default path under BIN_DIR
        return os.path.join(DirectoryManager.BIN_DIR, name)

    def is_update_available(self, name: str) -> bool:
        """Checks if there is an update available for the specified runtime."""
        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        local_ver = self.get_installed_version(name)
        if not local_ver:
            return True
        latest_ver = self.check_latest(name)
        if not latest_ver or latest_ver == "Unknown":
            return False
        from packaging.version import parse as parse_version
        try:
            return parse_version(latest_ver) > parse_version(local_ver)
        except Exception:
            return False

    def get_installed_version(self, name: str) -> str:
        """Runs the binary with version flags and parses output to return version string."""
        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        path = self.get_bin_path(name)
        if not path or not os.path.exists(path):
            return None

        # Determine CLI arguments
        args = [path]
        if name == "ffmpeg":
            args.append("-version")
        else:
            args.append("--version")

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            # Centralized sanitized env: avoids LD_*/PYTHON* contamination on Linux.
            # On Windows the helper just returns os.environ.copy().
            from services.scrcpy_manager import get_clean_subprocess_env
            env = get_clean_subprocess_env()
            result = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
                env=env,
                timeout=3
            )
            output = result.stdout + result.stderr
            return self._parse_version_output(name, output)
        except Exception:
            return None

    def check_latest(self, name: str) -> str:
        """Queries release details from GitHub (or mock fallback) to get the latest online version."""
        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        if name == "scrcpy":
            release = self.github_service.check_latest_release("Genymobile/scrcpy")
            if release:
                return release.get("version")
        elif name == "adb":
            # ADB (platform-tools) fallback latest stable version
            return "34.0.4"
        elif name == "ffmpeg":
            return "6.0"
        return "Unknown"

    def download(self, name: str, progress_callback=None, status_callback=None) -> str:
        """Synchronously downloads the runtime package using DownloadManager."""
        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        url = self._get_download_url(name)
        if not url:
            raise ValueError(f"No download URL configured for runtime '{name}' on platform '{platform.system()}'.")

        dest_path = os.path.join(DirectoryManager.CACHE_DIR, f"{name}_runtime.zip")

        downloader = DownloadManager(
            url=url,
            dest_path=dest_path,
            progress_callback=progress_callback,
            status_callback=status_callback
        )
        self.downloaders[name] = downloader
        downloader.download()
        return dest_path

    def update(self, name: str, zip_path: str):
        """Extracts and overwrites local files inside runtime directory with the new payload."""
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"Zip archive not found at: {zip_path}")

        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        temp_dir = os.path.join(DirectoryManager.CACHE_DIR, f"temp_{name}_extract")
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Resolve target directory
            target_dir = os.path.join(DirectoryManager.BIN_DIR, name)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            os.makedirs(target_dir, exist_ok=True)

            # Look for nested folder inside zip extraction
            items = os.listdir(temp_dir)
            source_root = temp_dir
            if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
                source_root = os.path.join(temp_dir, items[0])

            for item in os.listdir(source_root):
                shutil.move(os.path.join(source_root, item), os.path.join(target_dir, item))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def remove(self, name: str):
        """Deletes the local installation folder or specific binaries for the runtime."""
        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        target_dir = os.path.join(DirectoryManager.BIN_DIR, name)
        if os.path.exists(target_dir) and os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
            return

        # Standalone binary cleanup
        exe_name = f"{name}.exe" if os.name == 'nt' else name
        paths_to_check = [
            os.path.join(DirectoryManager.BIN_DIR, exe_name),
            os.path.join(DirectoryManager.BIN_DIR, "scrcpy", exe_name)
        ]
        for p in paths_to_check:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def _parse_version_output(self, name: str, text: str) -> str:
        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        if name == "scrcpy":
            # Match "scrcpy v2.4" or "scrcpy 2.4"
            match = re.search(r"scrcpy\s+v?(\d+\.\d+(?:\.\d+)?)", text, re.IGNORECASE)
            if match:
                return match.group(1)
        elif name == "adb":
            # Match "Android Debug Bridge version 1.0.41" or "version 34.0.4"
            match = re.search(r"(?:Android Debug Bridge version|version)\s+(\d+\.\d+(?:\.\d+)?)", text, re.IGNORECASE)
            if match:
                return match.group(1)
        elif name == "ffmpeg":
            # Match "ffmpeg version v6.0" or "ffmpeg version 6.0"
            match = re.search(r"ffmpeg\s+version\s+v?(\d+\.\d+(?:\.\d+)?)", text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _get_download_url(self, name: str) -> str:
        name = name.lower()
        if name == "platform-tools":
            name = "adb"
        sys_os = platform.system()
        if name == "scrcpy":
            if sys_os == "Windows":
                # Queries github releases asset win64.zip
                release = self.github_service.check_latest_release("Genymobile/scrcpy")
                if release:
                    for asset in release.get("assets", []):
                        asset_name = asset.get("name", "")
                        if "win64" in asset_name and asset_name.endswith(".zip"):
                            return asset.get("browser_download_url")
            return None
        elif name == "adb":
            if sys_os == "Windows":
                return "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
            elif sys_os == "Linux":
                return "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
            elif sys_os == "Darwin":
                return "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
        elif name == "ffmpeg":
            if sys_os == "Windows":
                return "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        return None
