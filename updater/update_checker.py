import json
import urllib.request
import threading
from packaging.version import parse as parse_version
from config.version import current_version

from config.app_info import AppInfo

class UpdateChecker:
    def __init__(self, logger=None):
        self.logger = logger
        self.repo = AppInfo.REPO_NAME
        self.api_url = f"https://api.github.com/repos/{self.repo}/releases/latest"

    def check_for_updates_async(self, callback):
        """Menjalankan pengecekan update di thread terpisah agar tidak memblokir UI."""
        thread = threading.Thread(target=self._check, args=(callback,), daemon=True)
        thread.start()

    def _check(self, callback):
        result = {
            "latest_version": None,
            "release_notes": "",
            "download_url": "",
            "is_update_available": False
        }
        try:
            if self.logger:
                self.logger.info("Memeriksa pembaruan aplikasi di GitHub...")

            # Buat request dengan User-Agent agar tidak diblokir GitHub API
            req = urllib.request.Request(
                self.api_url,
                headers={"User-Agent": "Camera-Studio-UpdateChecker"}
            )
            
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                
                # Mengambil tag_name (misal: "v1.1.0" atau "1.1.0")
                tag_name = data.get("tag_name", "").strip()
                latest_ver_str = tag_name.lstrip("v")
                
                release_notes = data.get("body", "")
                
                # Mencari download url dari asset jika ada, fallback ke html_url rilis
                download_url = data.get("html_url", "")
                assets = data.get("assets", [])
                if assets:
                    download_url = assets[0].get("browser_download_url", download_url)

                result["latest_version"] = latest_ver_str
                result["release_notes"] = release_notes
                result["download_url"] = download_url

                if latest_ver_str:
                    try:
                        is_newer = parse_version(latest_ver_str) > parse_version(current_version)
                        result["is_update_available"] = is_newer
                        if self.logger:
                            if is_newer:
                                self.logger.info(f"Pembaruan tersedia! Versi terbaru: v{latest_ver_str}")
                            else:
                                self.logger.info("Aplikasi sudah menggunakan versi terbaru.")
                    except Exception as ver_err:
                        if self.logger:
                            self.logger.error(f"Gagal membandingkan versi: {ver_err}")
                else:
                    if self.logger:
                        self.logger.warning("Tag versi tidak ditemukan pada rilis terbaru GitHub.")

        except Exception as e:
            if self.logger:
                self.logger.error(f"Gagal memeriksa pembaruan: {e}")
        
        # Panggil callback dengan hasil pengecekan
        if callback:
            try:
                callback(result)
            except Exception as cb_err:
                if self.logger:
                    self.logger.error(f"Gagal mengeksekusi callback pembaruan: {cb_err}")
