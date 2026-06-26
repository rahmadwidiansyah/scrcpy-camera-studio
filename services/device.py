import re


class AndroidDevice:
    """Merepresentasikan satu Android device yang terdeteksi oleh ADB."""

    def __init__(self, serial: str, status: str, model_name: str):
        self.serial     = serial       # e.g. "ABC123" atau "192.168.1.5:5555"
        self.status     = status       # "device" | "unauthorized" | "offline"
        self.model_name = model_name   # e.g. "Samsung S20 FE"

    # ── connection type detection ─────────────────────────────
    @property
    def connection_type(self) -> str:
        """Kembalikan 'WiFi' jika serial berupa IP:PORT, else 'USB'."""
        # pola IP:port → WiFi ADB
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}:\d+$", self.serial):
            return "WiFi"
        return "USB"

    @property
    def ip_address(self) -> str:
        """Kembalikan IP address (tanpa port) untuk device WiFi, atau '' jika USB."""
        if self.connection_type == "WiFi":
            return self.serial.split(":")[0]
        return ""

    # ── display helpers ──────────────────────────────────────
    @property
    def conn_icon(self) -> str:
        """Emoji indikator koneksi."""
        if self.status != "device":
            return "🔴"
        return "🟠" if self.connection_type == "WiFi" else "🟢"

    @property
    def display_label(self) -> str:
        """Label singkat untuk dropdown: 'Samsung S20 FE  [USB] 🟢'."""
        conn = self.connection_type
        if conn == "WiFi":
            label = f"{self.model_name}  [WiFi {self.ip_address}]"
        else:
            label = f"{self.model_name}  [USB]"
        return label

    def __repr__(self):
        return (
            f"AndroidDevice(serial={self.serial!r}, status={self.status!r}, "
            f"model={self.model_name!r}, conn={self.connection_type})"
        )