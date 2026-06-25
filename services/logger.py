import logging
from logging.handlers import RotatingFileHandler
import os
import sys

class Logger:
    def __init__(self, log_file="app.log"):
        self.log_callback = None
        
        from config.config import Config
        if not os.path.isabs(log_file):
            log_file = os.path.join(Config.LOGS_DIR, log_file)
        self.log_file = log_file

        # Ambil root logger untuk Camera Studio
        self.logger = logging.getLogger("CameraStudio")
        self.logger.setLevel(logging.INFO)

        # Format logs profesional
        formatter = logging.Formatter(
            fmt='[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )

        # Mencegah duplikasi handler pada root logger
        if not self.logger.handlers:
            # 1. Root file handler (app.log) - menyimpan semua log dari semua level
            file_handler = RotatingFileHandler(
                self.log_file, 
                maxBytes=1024 * 1024, 
                backupCount=5, 
                encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

            # 2. Handler untuk exception.log (hanya untuk ERROR ke atas, merekam traceback lengkap)
            exception_file = os.path.join(Config.LOGS_DIR, "exception.log")
            exception_handler = RotatingFileHandler(
                exception_file,
                maxBytes=1024 * 1024,
                backupCount=5,
                encoding="utf-8"
            )
            exception_handler.setLevel(logging.ERROR)
            exception_formatter = logging.Formatter(
                fmt='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            exception_handler.setFormatter(exception_formatter)
            self.logger.addHandler(exception_handler)

            # 3. StreamHandler ke stdout (untuk dev debug)
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            # 4. Custom UI Handler
            self.ui_handler = UICallbackHandler(self)
            self.logger.addHandler(self.ui_handler)

        # Inisialisasi sub-loggers untuk kategori spesifik
        categories = ["startup", "download", "update", "scrcpy", "adb"]
        for cat in categories:
            cat_logger = logging.getLogger(f"CameraStudio.{cat}")
            cat_logger.setLevel(logging.INFO)
            
            # Mencegah duplikasi handler pada child loggers
            if not cat_logger.handlers:
                cat_file = os.path.join(Config.LOGS_DIR, f"{cat}.log")
                cat_handler = RotatingFileHandler(
                    cat_file,
                    maxBytes=1024 * 1024,
                    backupCount=5,
                    encoding="utf-8"
                )
                cat_handler.setFormatter(formatter)
                cat_logger.addHandler(cat_handler)

    def get_logger(self, category):
        """Mendapatkan child logger khusus untuk kategori tertentu."""
        return logging.getLogger(f"CameraStudio.{category}")

    def set_callback(self, callback):
        """Menghubungkan logger dengan fungsi pembaruan UI."""
        self.log_callback = callback

    def info(self, message):
        # Fallback ke logger startup
        self.get_logger("startup").info(message)

    def warning(self, message):
        # Fallback ke logger startup
        self.get_logger("startup").warning(message)

    def error(self, message):
        # Fallback ke logger startup dengan logging otomatis exc_info jika ada exception aktif
        target_logger = self.get_logger("startup")
        if sys.exc_info()[0] is not None:
            target_logger.error(message, exc_info=True)
        else:
            target_logger.error(message)

    def exception(self, message):
        # Fallback ke logger startup
        self.get_logger("startup").exception(message)


class UICallbackHandler(logging.Handler):
    def __init__(self, parent_logger):
        super().__init__()
        self.parent_logger = parent_logger
        self.setFormatter(logging.Formatter(
            fmt='[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        ))

    def emit(self, record):
        if self.parent_logger.log_callback:
            try:
                # Format pesan. Jika record berisi exc_info (traceback),
                # buat salinan record tanpa exc_info khusus untuk UI agar traceback tidak tampil di GUI.
                if record.exc_info:
                    import copy
                    clean_record = copy.copy(record)
                    clean_record.exc_info = None
                    clean_record.exc_text = None
                    msg = self.format(clean_record)
                else:
                    msg = self.format(record)
                
                self.parent_logger.log_callback(msg)
            except Exception:
                pass
