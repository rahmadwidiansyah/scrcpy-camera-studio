import subprocess
import os
from config.config import Config
from services.device import AndroidDevice


class ADBManager:
    def __init__(self, logger=None):
        self.logger = logger
        self.adb_path = Config.get_bin_path("adb")
        self._last_error = None

    # ── public ───────────────────────────────────────────────
    def get_connected_devices(self):
        """Menjalankan 'adb devices' dan mengembalikan list objek AndroidDevice."""
        devices = []
        try:
            # Ensure adb path is re-resolved in case runtime was updated
            self.adb_path = Config.get_bin_path("adb")
            if not self.adb_path:
                self._log_error_once("ADB binary path not found. Please install ADB runtime.")
                return devices

            result = self._run_adb(["devices"], timeout=2)
            if result is None or result.returncode != 0:
                return devices

            for line in result.stdout.splitlines():
                if not line.strip() or line.startswith("List of devices"):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    status = parts[1]
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

    def test_adb_connection(self, on_done=None):
        """Run adb start-server and adb devices to verify ADB is available."""
        try:
            start_result = self._run_adb(["start-server"], timeout=15)  # Increased timeout
            if start_result is None:
                if on_done:
                    on_done(False, "ADB start-server timed out.")
                return

            devices_result = self._run_adb(["devices"], timeout=15)  # Increased timeout
            if devices_result is None:
                if on_done:
                    on_done(False, "ADB devices timed out.")
                return

            output = (devices_result.stdout or "").strip()
            if devices_result.returncode == 0:
                if on_done:
                    on_done(True, output or "ADB is responding. No devices detected yet.")
            else:
                if on_done:
                    on_done(False, output or "ADB devices command failed.")
        except Exception as e:
            if on_done:
                on_done(False, str(e))

    def restart_adb(self, on_done=None):
        """Restart ADB server by killing and starting it again."""
        try:
            kill_result = self._run_adb(["kill-server"], timeout=10)  # Increased timeout
            if kill_result is None:
                if on_done:
                    on_done(False, "ADB kill-server timed out.")
                return

            start_result = self._run_adb(["start-server"], timeout=15)  # Increased timeout
            if start_result is None:
                if on_done:
                    on_done(False, "ADB restart timed out.")
                return

            devices_result = self._run_adb(["devices"], timeout=15)  # Increased timeout
            if devices_result is None:
                if on_done:
                    on_done(False, "ADB devices timed out after restart.")
                return

            output = (devices_result.stdout or "").strip()
            if devices_result.returncode == 0:
                if on_done:
                    on_done(True, output or "ADB server restarted successfully.")
            else:
                if on_done:
                    on_done(False, output or "ADB restart failed.")
        except Exception as e:
            if on_done:
                on_done(False, str(e))

    def enable_wifi_adb(self, serial: str, on_done=None):
        """
        Aktifkan ADB over WiFi untuk device `serial`.

        Langkah:
          1. adb -s SERIAL tcpip 5555
          2. Ambil IP device via `adb -s SERIAL shell ip route`
          3. adb connect IP:5555

        Panggil on_done(success: bool, message: str) saat selesai.
        Metode ini dirancang untuk dipanggil dari thread terpisah.
        """
        try:
            # Step 1: set port TCP
            r1 = self._run_adb(["-s", serial, "tcpip", "5555"], timeout=5)
            if r1 is None or r1.returncode != 0:
                msg = r1.stderr.strip() if r1 else "ADB tcpip failed"
                if on_done:
                    on_done(False, f"tcpip failed: {msg}")
                return

            # Step 2: dapatkan IP device
            ip = self._get_device_ip(serial)
            if not ip:
                if on_done:
                    on_done(False, "Could not determine device IP address.\n"
                                   "Make sure device and PC are on the same network.")
                return

            # Step 3: connect
            import time
            time.sleep(1.0)   # beri waktu device untuk menerapkan tcpip
            target = f"{ip}:5555"
            r2 = self._run_adb(["connect", target], timeout=8)
            if r2 is None:
                if on_done:
                    on_done(False, "ADB connect timed out.")
                return

            output = r2.stdout.strip()
            if "connected" in output.lower():
                if on_done:
                    on_done(True, f"Connected via WiFi  {target}")
            else:
                if on_done:
                    on_done(False, f"Connect failed: {output}")

        except Exception as e:
            if on_done:
                on_done(False, str(e))

    def disconnect_wifi(self, serial: str, on_done=None):
        """Putuskan koneksi WiFi ADB untuk device berformat IP:PORT."""
        try:
            r = self._run_adb(["disconnect", serial], timeout=5)
            output = (r.stdout.strip() if r else "") or ""
            if on_done:
                on_done(True, f"Disconnected: {output}")
        except Exception as e:
            if on_done:
                on_done(False, str(e))

    def get_device_ip_only(self, serial: str) -> str:
        """Hanya ambil IP address device tanpa melakukan koneksi."""
        return self._get_device_ip(serial)

    def enable_wifi_adb_with_ip_callback(self, serial: str, on_ip_found=None):
        """
        Fase 1 dari 2-fase WiFi ADB:
          1. adb -s SERIAL tcpip 5555
          2. Kumpulkan semua IP device dengan prioritas interface WiFi
          3. Panggil on_ip_found(ip_list: list[dict], error: str)
             - ip_list adalah list of dict: {ip, iface, label, priority}
               sorted by priority (terbaik di index 0)
             - error string bila gagal, '' bila sukses
        UI menampilkan dialog seleksi (jika >1 IP), lalu memanggil connect_wireless().
        """
        try:
            import time
            r1 = self._run_adb(["-s", serial, "tcpip", "5555"], timeout=6)
            if r1 is None or r1.returncode != 0:
                err = (r1.stderr.strip() if r1 else "") or "adb tcpip failed"
                if on_ip_found:
                    on_ip_found([], err)
                return
            time.sleep(0.8)
            ip_list = self._get_all_device_ips(serial)
            if on_ip_found:
                if ip_list:
                    on_ip_found(ip_list, "")
                else:
                    on_ip_found([], "Device IP not found. Ensure the device is connected to Wi-Fi.")
        except Exception as e:
            if on_ip_found:
                on_ip_found([], str(e))


    def connect_wireless(self, ip: str, port: int = 5555, on_done=None):
        """
        Jalankan 'adb connect IP:PORT'.
        Panggil on_done(success: bool, message: str) saat selesai.
        """
        try:
            target = f"{ip}:{port}"
            r = self._run_adb(["connect", target], timeout=10)
            if r is None:
                if on_done:
                    on_done(False, "Connection timed out.")
                return
            output = r.stdout.strip()
            if "connected" in output.lower():
                if on_done:
                    on_done(True, f"Connected via WiFi  {target}")
            else:
                if on_done:
                    on_done(False, output or "Connection failed. Enable Wireless Debugging on the device.")
        except Exception as e:
            if on_done:
                on_done(False, str(e))

    def reconnect_wifi(self, serial: str, on_done=None):
        """Disconnect lalu reconnect device WiFi (IP:PORT)."""
        try:
            self._run_adb(["disconnect", serial], timeout=5)
            import time; time.sleep(0.5)
            r = self._run_adb(["connect", serial], timeout=10)
            output = (r.stdout.strip() if r else "") or ""
            if "connected" in output.lower():
                if on_done:
                    on_done(True, f"Reconnected: {serial}")
            else:
                if on_done:
                    on_done(False, f"Reconnect failed: {output}")
        except Exception as e:
            if on_done:
                on_done(False, str(e))

    def get_device_brand(self, serial: str) -> str:
        """Ambil ro.product.brand dari device."""
        result = self._run_adb(["-s", serial, "shell", "getprop", "ro.product.brand"], timeout=2)
        if result and result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().title()
        return ""

    # ── internal helpers ───────────────────────────────────────
    def _run_adb(self, args: list, timeout: int = 5):
        """Jalankan perintah ADB dan kembalikan CompletedProcess, atau None jika timeout."""
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            # Centralized sanitized env: no LD_*/PYTHON* contamination on Linux packaged builds.
            # Windows behavior is unchanged (helper just returns os.environ.copy()).
            from services.scrcpy_manager import get_clean_subprocess_env
            env = get_clean_subprocess_env()
            return subprocess.run(
                [self.adb_path] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=flags,
                env=env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            self._log_error_once(f"ADB command timed out: {args}")
            return None
        except Exception as e:
            self._log_error_once(f"ADB error: {e}")
            return None

    def _get_device_model(self, serial: str) -> str:
        """Ambil ro.product.model dari device."""
        result = self._run_adb(["-s", serial, "shell", "getprop", "ro.product.model"], timeout=2)
        if result and result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return "Generic Android Device"

    # ── Interfaces to ignore (virtual / cellular / VPN) ───────────
    _IGNORE_PREFIXES = (
        "lo", "dummy", "rmnet", "ccmni", "tun", "vpn", "docker",
        "virbr", "veth", "br-", "pdp", "seth", "uwb",
    )
    # Preferred WiFi interface names
    _WIFI_IFACES = ("wlan", "wifi", "wlp", "ap")

    @classmethod
    def _iface_priority(cls, iface: str) -> int:
        """
        Return sort priority (lower = better).
          0  → wlan0 / wifi0 (best: real WiFi)
          1  → other WiFi-like interface
          2  → other physical interface (eth, etc.)
          99 → ignored/virtual (caller should filter these out)
        """
        low = iface.lower()
        for pfx in cls._IGNORE_PREFIXES:
            if low.startswith(pfx):
                return 99
        for pfx in cls._WIFI_IFACES:
            if low.startswith(pfx):
                return 0 if low in ("wlan0", "wifi0") else 1
        return 2

    @staticmethod
    def _ip_subnet_priority(ip: str) -> int:
        """
        Return sort priority for IP subnet (lower = better LAN match).
          0  → 192.168.x.x  (typical home/office WiFi)
          1  → 172.16-31.x.x (RFC1918 medium)
          2  → 10.x.x.x     (RFC1918 broad — also used by mobile data!)
          9  → other / public
        """
        import re
        parts = ip.split(".")
        if len(parts) != 4:
            return 9
        try:
            a, b = int(parts[0]), int(parts[1])
        except ValueError:
            return 9
        if a == 192 and b == 168:
            return 0
        if a == 172 and 16 <= b <= 31:
            return 1
        if a == 10:
            return 2
        return 9

    def _get_all_device_ips(self, serial: str) -> list:
        """
        Kumpulkan semua IP address dari device dengan deteksi interface yang akurat.
        Kembalikan list of dict:
          [{ip, iface, label, iface_prio, subnet_prio}]
        Sorted: WiFi interfaces first (wlan0 > wifi0 > others),
                then 192.168 > 172.16 > 10.x inside each group.
        Interface virtual (rmnet, tun, lo, ccmni, dll.) diabaikan.
        """
        import re
        candidates = {}  # key=ip: dict

        # ── Method 1: ip addr show wlan0 / wifi0 (most reliable for WiFi) ──
        for iface in ("wlan0", "wifi0", "wlan1"):
            r = self._run_adb(["-s", serial, "shell", "ip", "addr", "show", iface], timeout=3)
            if r and r.returncode == 0:
                for m in re.finditer(
                    r"inet\s+(\d{1,3}(?:\.\d{1,3}){3})(?:/\d+)?",
                    r.stdout
                ):
                    ip = m.group(1)
                    if ip not in candidates:
                        iface_prio  = self._iface_priority(iface)
                        subnet_prio = self._ip_subnet_priority(ip)
                        candidates[ip] = {
                            "ip": ip, "iface": iface,
                            "iface_prio": iface_prio,
                            "subnet_prio": subnet_prio,
                        }

        # ── Method 2: ip addr (all interfaces) ───────────────────────
        r2 = self._run_adb(["-s", serial, "shell", "ip", "addr"], timeout=4)
        if r2 and r2.returncode == 0:
            current_iface = ""
            for line in r2.stdout.splitlines():
                # interface line: "2: wlan0: <...>"
                iface_m = re.match(r"^\d+:\s+(\S+):", line)
                if iface_m:
                    current_iface = iface_m.group(1).rstrip(":@")
                    continue
                # IP line: "    inet 192.168.1.5/24 ..."
                ip_m = re.search(
                    r"inet\s+(\d{1,3}(?:\.\d{1,3}){3})(?:/\d+)?",
                    line
                )
                if ip_m and current_iface:
                    ip = ip_m.group(1)
                    iface_prio = self._iface_priority(current_iface)
                    if iface_prio == 99:
                        continue   # skip virtual/ignored interfaces
                    if ip not in candidates:
                        subnet_prio = self._ip_subnet_priority(ip)
                        candidates[ip] = {
                            "ip": ip, "iface": current_iface,
                            "iface_prio": iface_prio,
                            "subnet_prio": subnet_prio,
                        }

        # ── Method 3: ip route (src field) ─────────────────────────
        r3 = self._run_adb(["-s", serial, "shell", "ip", "route"], timeout=3)
        if r3 and r3.returncode == 0:
            for line in r3.stdout.splitlines():
                # "192.168.1.0/24 dev wlan0 proto kernel scope link src 192.168.1.5"
                dev_m = re.search(r"dev\s+(\S+)", line)
                src_m = re.search(r"src\s+(\d{1,3}(?:\.\d{1,3}){3})", line)
                if dev_m and src_m:
                    iface = dev_m.group(1)
                    ip    = src_m.group(1)
                    iface_prio = self._iface_priority(iface)
                    if iface_prio == 99:
                        continue
                    if ip not in candidates:
                        subnet_prio = self._ip_subnet_priority(ip)
                        candidates[ip] = {
                            "ip": ip, "iface": iface,
                            "iface_prio": iface_prio,
                            "subnet_prio": subnet_prio,
                        }

        # ── Method 4: ifconfig (fallback for older Android) ─────────
        r4 = self._run_adb(["-s", serial, "shell", "ifconfig"], timeout=3)
        if r4 and r4.returncode == 0:
            current_iface = ""
            for line in r4.stdout.splitlines():
                # "wlan0     Link encap:..."
                iface_m = re.match(r"^(\S+)\s", line)
                if iface_m:
                    current_iface = iface_m.group(1)
                ip_m = re.search(r"inet addr:(\d{1,3}(?:\.\d{1,3}){3})", line)
                if ip_m and current_iface:
                    ip = ip_m.group(1)
                    iface_prio = self._iface_priority(current_iface)
                    if iface_prio == 99:
                        continue
                    if ip not in candidates:
                        subnet_prio = self._ip_subnet_priority(ip)
                        candidates[ip] = {
                            "ip": ip, "iface": current_iface,
                            "iface_prio": iface_prio,
                            "subnet_prio": subnet_prio,
                        }

        # ── Method 5: getprop dhcp (last resort) ─────────────────
        for prop_iface in ("wlan0", "wifi0"):
            r5 = self._run_adb(
                ["-s", serial, "shell", "getprop", f"dhcp.{prop_iface}.ipaddress"], timeout=2
            )
            if r5 and r5.returncode == 0:
                ip = r5.stdout.strip()
                if ip and re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", ip):
                    if ip not in candidates:
                        iface_prio  = self._iface_priority(prop_iface)
                        subnet_prio = self._ip_subnet_priority(ip)
                        candidates[ip] = {
                            "ip": ip, "iface": prop_iface,
                            "iface_prio": iface_prio,
                            "subnet_prio": subnet_prio,
                        }

        if not candidates:
            return []

        # Build labels and sort: iface_prio ASC, subnet_prio ASC
        result = []
        for entry in candidates.values():
            iface = entry["iface"]
            low   = iface.lower()
            if any(low.startswith(p) for p in self._WIFI_IFACES):
                label = f"WiFi ({iface})"
            elif low.startswith("eth"):
                label = f"Ethernet ({iface})"
            else:
                label = f"Network ({iface})"
            entry["label"] = label
            result.append(entry)

        result.sort(key=lambda e: (e["iface_prio"], e["subnet_prio"]))
        return result

    def _get_device_ip(self, serial: str) -> str:
        """Compatibility wrapper — returns best single IP string or ''."""
        ips = self._get_all_device_ips(serial)
        return ips[0]["ip"] if ips else ""

    def _log_error_once(self, message: str):
        if message == self._last_error:
            return
        self._last_error = message
        if self.logger:
            self.logger.error(message)
