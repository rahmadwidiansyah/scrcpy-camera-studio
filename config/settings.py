import json
import os

class SettingsManager:
    def __init__(self, logger, config_file="settings.json"):
        self.logger = logger
        
        # --- PENYESUAIAN SETTINGS.JSON AGAR DI SIMPAN DI APPDATA ---
        if not os.path.isabs(config_file):
            from config.config import Config
            config_file = os.path.join(Config.SETTINGS_DIR, config_file)
            
        self.config_file = config_file
        
        self.default_settings = {
            "last_camera": "",
            "resolution": "1080",
            "fps": 30,
            "bitrate": "8M",
            "mirror": False,
            "rotate": 0,
            "audio": False,
            "theme": "System",
            "preview_mode": "Normal Window",
            "target_device": ""  
        }
        
        self.current_settings = self.default_settings.copy()
        self.load()

    # ... [KODE BAWAHNYA TETAP SAMA] ...

    def load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    loaded_data = json.load(f)
                    for key in self.default_settings:
                        if key in loaded_data:
                            self.current_settings[key] = loaded_data[key]
                self.logger.info("Pengaturan berhasil dimuat dari settings.json.")
            except Exception as e:
                self.logger.error(f"Gagal memuat pengaturan: {e}")
        else:
            self.logger.info("File pengaturan tidak ditemukan. Membuat file baru...")
            self.save()

    def save(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.current_settings, f, indent=4)
            self.logger.info("Pengaturan berhasil disimpan otomatis.")
        except Exception as e:
            self.logger.error(f"Gagal menyimpan pengaturan: {e}")

    def get(self, key):
        return self.current_settings.get(key, self.default_settings.get(key))

    def set(self, key, value):
        if key in self.current_settings:
            # Cegah log spam jika nilainya sama
            if self.current_settings[key] != value:
                self.current_settings[key] = value
                self.logger.info(f"Setting diubah: {key} -> {value}")
                self.save()
