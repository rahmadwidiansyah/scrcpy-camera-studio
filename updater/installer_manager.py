import os
import urllib.request
import zipfile
import threading
import shutil
import platform
from config.config import Config

class InstallerManager:
    def __init__(self, logger):
        self.logger = logger
        self.required_deps = ["adb", "scrcpy"]
        # URL rilis resmi scrcpy untuk Windows 64-bit (v2.4 - Stabil)
        self.scrcpy_win_url = "https://github.com/Genymobile/scrcpy/releases/download/v2.4/scrcpy-win64-v2.4.zip"

    def get_missing_dependencies(self):
        missing = []
        for dep in self.required_deps:
            if not Config.check_dependency(dep):
                missing.append(dep)
        return missing

    def start_install(self, on_complete_callback=None):
        """Memulai proses instalasi dependency di latar belakang."""
        sys_os = platform.system()
        if sys_os != "Windows" and sys_os != "Linux":
            self.logger.error(f"Instalasi otomatis tidak didukung untuk OS {sys_os}.")
            if on_complete_callback:
                on_complete_callback("OS Not Supported")
            return

        self.logger.info("--- [INSTALLER MANAGER] ---")
        self.logger.info("Memulai proses instalasi dependency di latar belakang...")
        
        # Jalankan unduhan di thread terpisah
        install_thread = threading.Thread(target=self._download_and_extract_or_install_linux, args=(on_complete_callback,))
        install_thread.daemon = True
        install_thread.start()

    def _download_and_extract_or_install_linux(self, on_complete_callback):
        sys_os = platform.system()
        if sys_os == "Linux":
            self._install_linux_packages(on_complete_callback)
        else:
            self._download_and_extract(on_complete_callback)

    def _install_linux_packages(self, on_complete_callback):
        import subprocess
        self.logger.info("Mendeteksi distribusi Linux untuk instalasi paket...")
        
        # Deteksi apt-get (Ubuntu/Debian) atau pacman (Arch Linux)
        if shutil.which("pkexec"):
            # Use policykit GUI prompt to ask for password
            if shutil.which("pacman"):
                cmd = ["pkexec", "pacman", "-S", "--noconfirm", "scrcpy", "android-tools"]
                self.logger.info(f"Menggunakan Pacman dengan GUI pkexec: {' '.join(cmd)}")
            elif shutil.which("apt-get"):
                cmd = "pkexec apt-get update && pkexec apt-get install -y scrcpy adb"
                self.logger.info(f"Menggunakan APT dengan GUI pkexec: {cmd}")
        else:
            # Fallback to standard terminal sudo
            if shutil.which("pacman"):
                cmd = ["sudo", "pacman", "-S", "--noconfirm", "scrcpy", "android-tools"]
                self.logger.info(f"Menggunakan Pacman (Arch Linux): {' '.join(cmd)}")
            elif shutil.which("apt-get"):
                cmd = "sudo apt-get update && sudo apt-get install -y scrcpy adb"
                self.logger.info(f"Menggunakan APT (Ubuntu/Debian): {cmd}")
            else:
                self.logger.error("PackageManager tidak dikenal. Silakan pasang 'scrcpy' dan 'adb' secara manual.")
                if on_complete_callback:
                    on_complete_callback("Unsupported Linux Distro")
                return

        try:
            self.logger.info("Menjalankan perintah instalasi (Mungkin memerlukan kata sandi sudo)...")
            shell_mode = isinstance(cmd, str)
            result = subprocess.run(
                cmd,
                shell=shell_mode,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180
            )
            if result.returncode == 0:
                self.logger.info("Instalasi dependensi Linux berhasil diselesaikan.")
                if on_complete_callback:
                    on_complete_callback("Success")
            else:
                err_msg = result.stderr or result.stdout
                self.logger.error(f"Gagal memasang paket Linux (Exit code {result.returncode}): {err_msg}")
                if on_complete_callback:
                    on_complete_callback(f"Failure: {err_msg}")
        except Exception as e:
            self.logger.error(f"Gagal menjalankan instalasi paket Linux: {e}")
            if on_complete_callback:
                on_complete_callback(str(e))

    def _download_and_extract(self, on_complete_callback):
        try:
            bin_dir = Config.BIN_DIR
            cache_dir = Config.CACHE_DIR
            if not os.path.exists(bin_dir):
                os.makedirs(bin_dir)
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)

            zip_path = os.path.join(cache_dir, "scrcpy_temp.zip")
            extract_dir = os.path.join(cache_dir, "temp_extract")

            # Langkah 1: Download
            self.logger.info("Langkah 1: Mengunduh paket resmi scrcpy (sekitar 5MB-10MB)...")
            urllib.request.urlretrieve(self.scrcpy_win_url, zip_path)
            self.logger.info("Unduhan selesai.")

            # Langkah 2: Extract
            self.logger.info("Langkah 2: Mengekstrak file ZIP...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Langkah 3: Memindahkan biner ke folder scrcpy/ lokal
            self.logger.info("Langkah 3: Memindahkan biner ke folder scrcpy/...")
            scrcpy_dir = os.path.join(bin_dir, "scrcpy")
            if os.path.exists(scrcpy_dir):
                shutil.rmtree(scrcpy_dir)
            os.makedirs(scrcpy_dir, exist_ok=True)

            extracted_items = os.listdir(extract_dir)
            
            # Scrcpy biasanya diekstrak dalam satu folder utama (misal: scrcpy-win64-v2.4)
            # Kita ingin isinya yang dipindah, bukan foldernya.
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(extract_dir, extracted_items[0])):
                inner_dir = os.path.join(extract_dir, extracted_items[0])
                for item in os.listdir(inner_dir):
                    src = os.path.join(inner_dir, item)
                    dst = os.path.join(scrcpy_dir, item)
                    shutil.move(src, dst)
            else:
                # Fallback jika struktur direktori ZIP berubah di masa depan
                for item in extracted_items:
                    src = os.path.join(extract_dir, item)
                    dst = os.path.join(scrcpy_dir, item)
                    shutil.move(src, dst)

            # Langkah 4: Cleanup
            self.logger.info("Langkah 4: Membersihkan file sementara...")
            os.remove(zip_path)
            shutil.rmtree(extract_dir)

            self.logger.info("Proses instalasi SELESAI. Semua dependensi siap.")
            self.logger.info("---------------------------")
            
            # Panggil callback agar UI tahu instalasi sudah selesai
            if on_complete_callback:
                on_complete_callback("Success")

        except Exception as e:
            self.logger.error(f"Gagal melakukan instalasi: {e}")
            if on_complete_callback:
                on_complete_callback("Error")


class UpdateDownloader:
    def __init__(self, url, logger=None):
        self.url = url
        self.logger = logger
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.is_paused = False
        self.is_cancelled = False
        self.is_completed = False
        self.error = None
        
        # Tentukan path file di folder cache
        import urllib.parse
        parsed_url = urllib.parse.urlparse(url)
        filename = os.path.basename(parsed_url.path) or "update.zip"
        self.dest_path = os.path.join(Config.CACHE_DIR, filename)

        self._thread = None
        self._lock = threading.Lock()

    def start(self, progress_callback=None, completion_callback=None):
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self):
        with self._lock:
            self.is_paused = True
            if self.logger:
                self.logger.info("Unduhan ditangguhkan (paused).")

    def resume(self):
        with self._lock:
            self.is_paused = False
            if self.logger:
                self.logger.info("Unduhan dilanjutkan (resumed).")

    def cancel(self):
        with self._lock:
            self.is_cancelled = True
            if self.logger:
                self.logger.info("Unduhan dibatalkan (cancelled).")

    def _run(self):
        import time
        try:
            if not os.path.exists(Config.CACHE_DIR):
                os.makedirs(Config.CACHE_DIR)

            mode = "wb"
            while not self.is_cancelled and not self.is_completed:
                if self.is_paused:
                    time.sleep(0.1)
                    continue

                req = urllib.request.Request(
                    self.url,
                    headers={"User-Agent": "Camera-Studio-Updater"}
                )
                
                # Jika sudah terunduh sebagian, kirimkan Range request
                if self.downloaded_bytes > 0:
                    req.add_header("Range", f"bytes={self.downloaded_bytes}-")
                    mode = "ab"
                else:
                    mode = "wb"

                try:
                    with urllib.request.urlopen(req, timeout=10) as response:
                        if self.downloaded_bytes == 0:
                            self.total_bytes = int(response.headers.get('content-length', 0))
                        
                        with open(self.dest_path, mode) as f:
                            chunk_size = 16384
                            while not self.is_cancelled and not self.is_paused:
                                chunk = response.read(chunk_size)
                                if not chunk:
                                    self.is_completed = True
                                    break
                                f.write(chunk)
                                self.downloaded_bytes += len(chunk)
                                if self.progress_callback:
                                    self.progress_callback(self.downloaded_bytes, self.total_bytes)
                except Exception as stream_err:
                    if self.is_paused:
                        continue
                    else:
                        raise stream_err

            if self.is_cancelled:
                if os.path.exists(self.dest_path):
                    try:
                        os.remove(self.dest_path)
                    except Exception:
                        pass
                if self.completion_callback:
                    self.completion_callback("Cancelled", self.dest_path)
            elif self.is_completed:
                if self.completion_callback:
                    self.completion_callback("Success", self.dest_path)

        except Exception as e:
            self.error = str(e)
            if self.logger:
                self.logger.error(f"Gagal mengunduh update: {e}")
            if os.path.exists(self.dest_path):
                try:
                    os.remove(self.dest_path)
                except Exception:
                    pass
            if self.completion_callback:
                self.completion_callback(f"Error: {e}", self.dest_path)