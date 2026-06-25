import subprocess
import os
from config.config import Config
from services.device import AndroidDevice

class ADBManager:
    def __init__(self, logger=None):
        self.logger = logger
        self.adb_path = Config.get_bin_path("adb")
        self._last_error = None

    def get_connected_devices(self):
        """Menjalankan 'adb devices' dan mengembalikan list objek AndroidDevice."""
        devices = []
        try:
            # Jalankan perintah adb devices
            # creationflags digunakan agar tidak memunculkan popup cmd hitam di Windows
            startupinfo = None
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NO_WINDOW
            else:
                creationflags = 0

            result = subprocess.run(
                [self.adb_path, "devices"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
                timeout=2
            )

            if result.returncode != 0:
                error_text = result.stderr.strip() or "ADB mengembalikan status gagal tanpa pesan error."
                self._log_error_once(f"Gagal membaca daftar device ADB: {error_text}")
                return devices
            
            lines = result.stdout.splitlines()
            for line in lines:
                if not line.strip() or line.startswith("List of devices"):
                    continue
                
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    status = parts[1]
                    
                    # Logika penentuan nama dan pesan status
                    if status == "device":
                        name = self._get_device_model(serial)
                    elif status == "unauthorized":
                        name = "Unknown Device"
                    else:
                        name = "Android Device"
                        
                    devices.append(AndroidDevice(serial, status, name))
                    
        except Exception as e:
            self._log_error_once(f"Gagal membaca daftar device ADB: {e}")
            
        return devices

    def _get_device_model(self, serial):
        """Mengambil nama asli model handphone menggunakan getprop."""
        try:
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NO_WINDOW
            else:
                creationflags = 0

            result = subprocess.run(
                [self.adb_path, "-s", serial, "shell", "getprop", "ro.product.model"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
                timeout=1
            )
            if result.returncode != 0:
                error_text = result.stderr.strip() or "ADB getprop gagal tanpa pesan error."
                self._log_error_once(f"Gagal membaca model device {serial}: {error_text}")
                return "Generic Android Device"

            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception as e:
            self._log_error_once(f"Gagal membaca model device {serial}: {e}")
        return "Generic Android Device"

    def _log_error_once(self, message):
        if message == self._last_error:
            return
        self._last_error = message
        if self.logger:
            self.logger.error(message)
