import os
import urllib.request
import zipfile
import threading
import shutil
import platform
from config import Config

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
        """Memulai proses instalasi sungguhan di thread terpisah agar UI tidak hang."""
        # Pengecekan OS: Saat ini skrip download difokuskan untuk Windows (Prioritas Utama)
        if platform.system() != "Windows":
            self.logger.error("Instalasi otomatis saat ini hanya mendukung OS Windows.")
            self.logger.info("Untuk pengguna Linux, silakan buka terminal dan jalankan: sudo apt install scrcpy adb")
            if on_complete_callback:
                on_complete_callback("OS Not Supported")
            return

        self.logger.info("--- [INSTALLER MANAGER] ---")
        self.logger.info("Memulai proses instalasi dependency di latar belakang...")
        
        # Jalankan unduhan di thread terpisah (Daemon thread akan mati jika aplikasi utama ditutup)
        install_thread = threading.Thread(target=self._download_and_extract, args=(on_complete_callback,))
        install_thread.daemon = True
        install_thread.start()

    def _download_and_extract(self, on_complete_callback):
        try:
            bin_dir = Config.BIN_DIR
            if not os.path.exists(bin_dir):
                os.makedirs(bin_dir)

            zip_path = os.path.join(bin_dir, "scrcpy_temp.zip")
            extract_dir = os.path.join(bin_dir, "temp_extract")

            # Langkah 1: Download
            self.logger.info("Langkah 1: Mengunduh paket resmi scrcpy (sekitar 5MB-10MB)...")
            urllib.request.urlretrieve(self.scrcpy_win_url, zip_path)
            self.logger.info("Unduhan selesai.")

            # Langkah 2: Extract
            self.logger.info("Langkah 2: Mengekstrak file ZIP...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Langkah 3: Memindahkan biner ke folder bin/
            self.logger.info("Langkah 3: Memindahkan biner ke folder utama bin/...")
            extracted_items = os.listdir(extract_dir)
            
            # Scrcpy biasanya diekstrak dalam satu folder utama (misal: scrcpy-win64-v2.4)
            # Kita ingin isinya yang dipindah, bukan foldernya.
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(extract_dir, extracted_items[0])):
                inner_dir = os.path.join(extract_dir, extracted_items[0])
                for item in os.listdir(inner_dir):
                    src = os.path.join(inner_dir, item)
                    dst = os.path.join(bin_dir, item)
                    # Hapus file lama jika ada agar tidak bentrok
                    if os.path.exists(dst):
                        if os.path.isdir(dst): shutil.rmtree(dst)
                        else: os.remove(dst)
                    shutil.move(src, dst)
            else:
                # Fallback jika struktur direktori ZIP berubah di masa depan
                for item in extracted_items:
                    src = os.path.join(extract_dir, item)
                    dst = os.path.join(bin_dir, item)
                    if os.path.exists(dst):
                        if os.path.isdir(dst): shutil.rmtree(dst)
                        else: os.remove(dst)
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