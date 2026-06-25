import datetime
import os

class Logger:
    def __init__(self, log_file="app.log"):
        self.log_callback = None
        if not os.path.isabs(log_file):
            log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), log_file)
        self.log_file = log_file

    def set_callback(self, callback):
        """Menghubungkan logger dengan fungsi pembaruan UI."""
        self.log_callback = callback

    def _log(self, level, message):
        """Format dasar log dan pengiriman ke callback."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] [{level}] {message}"

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(formatted_message + "\n")
        except Exception:
            pass
        
        # Kirim ke UI jika callback sudah di-set
        if self.log_callback:
            try:
                self.log_callback(formatted_message)
            except Exception:
                pass

    def info(self, message):
        self._log("INFO", message)

    def warning(self, message):
        self._log("WARNING", message)

    def error(self, message):
        self._log("ERROR", message)
