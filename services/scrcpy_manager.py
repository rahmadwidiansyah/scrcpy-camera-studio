import subprocess
import os
import re
import threading
import time
from config.config import Config

class ScrcpyManager:
    def __init__(self, logger):
        self.logger = logger
        self.processes = {}  # dict mapping mode (e.g., 'camera', 'mirror') to process
        self.scrcpy_path = Config.get_bin_path("scrcpy")
        self._last_return_codes = {}
        self.process_logs = {"camera": [], "mirror": []}
        self._manual_stop = {"camera": False, "mirror": False}
        self._error_reported = {"camera": False, "mirror": False}

    def start(self, settings_data, mode="camera", parent_window_id=None):
        if self.is_running(mode):
            self.logger.warning(f"Scrcpy mode {mode} sudah berjalan. Mengabaikan perintah Start.")
            return
            
        try:
            self._manual_stop[mode] = False
            self._error_reported[mode] = False
            self._last_return_codes[mode] = None
            self.process_logs[mode] = []
            
            self.logger.info(f"Menyiapkan parameter scrcpy (mode: {mode})...")
            if mode == "mirror":
                args = [self.scrcpy_path]
                if parent_window_id:
                    args.append(f"--parent={parent_window_id}")
            else:
                args = [self.scrcpy_path, "--video-source=camera"]

            # --- IMPLEMENTASI TARGET MULTI-DEVICE ---
            target_serial = settings_data.get("target_device", "").strip()
            if target_serial:
                args.append(f"--serial={target_serial}")

            # Konfigurasi Kamera
            cam_id = settings_data.get("last_camera", "").strip()
            if cam_id and mode == "camera":
                args.append(f"--camera-id={cam_id}")

            # Konfigurasi Resolusi & Camera Size
            # PENTING: scrcpy 4.0 tidak boleh memakai --camera-size DAN --camera-ar bersamaan.
            # Strategi:
            #   - AR != Auto  → gunakan --camera-ar saja (scrcpy hitung size sendiri)
            #   - AR == Auto  → gunakan --camera-size (hitung dari resolusi)
            res = settings_data.get("resolution", "1080")
            if mode == "camera":
                ar = settings_data.get("aspect_ratio", "Auto")
                if ar and ar.lower() != "auto":
                    # Biarkan scrcpy menentukan ukuran; kita hanya set aspect ratio
                    args.append(f"--camera-ar={ar}")
                    # Tetap set FPS melalui --camera-fps; resolusi diabaikan
                elif res and res.lower() != "auto":
                    # Tidak ada AR override → set camera-size
                    std_map = {
                        "720":  (1280, 720),
                        "1080": (1920, 1080),
                        "1920": (1920, 1080),
                    }
                    if res in std_map:
                        w, h = std_map[res]
                        args.append(f"--camera-size={w}x{h}")
                    elif "x" in res.lower():
                        args.append(f"--camera-size={res}")
                    elif res.isdigit():
                        h = int(res)
                        w = (int(h * 16 / 9) // 2) * 2
                        args.append(f"--camera-size={w}x{h}")
                    else:
                        args.append(f"--max-size={res}")
            elif res and res.lower() != "auto":
                # Mirror mode
                args.append(f"--max-size={res}")


            # Konfigurasi FPS
            fps = settings_data.get("fps", 30)
            if fps:
                if mode == "camera":
                    args.append(f"--camera-fps={fps}")
                else:
                    args.append(f"--max-fps={fps}")

            # Konfigurasi Bitrate
            bitrate = settings_data.get("bitrate", "8M")
            if bitrate:
                args.append(f"--video-bit-rate={bitrate}")

            # Konfigurasi Audio
            # scrcpy >= 2.0 mendukung --audio-source=mic atau --audio-source=playback
            audio_source = settings_data.get("audio_source", "Playback") # Playback, Mic, Both, Off
            if audio_source == "Off":
                args.append("--no-audio")
            elif audio_source == "Mic":
                args.append("--audio-source=mic")
            elif audio_source == "Playback":
                args.append("--audio-source=playback")
            # Jika "Both", maka scrcpy tidak mendukung input dua source sekaligus via satu parameter secara native, tapi default scrcpy adalah playback (media out). 
            # Jika user memilih "Both", kita biarkan default (playback) atau biarkan kosong jika scrcpy default playback.
            # Mari kita set explicit --audio-source=playback untuk Both/Playback agar aman.

            # Konfigurasi Rotasi dan Mirror/Flip.
            # Hanya berlaku untuk mode camera.
            if mode == "camera":
                rotate = settings_data.get("rotate", 0)
                rotation_map = {0: "0", 1: "90", 2: "180", 3: "270", "0": "0", "1": "90", "2": "180", "3": "270"}
                orientation = rotation_map.get(rotate, str(rotate))
                if settings_data.get("mirror", False):
                    orientation = f"flip{orientation}"
                args.append(f"--capture-orientation={orientation}")

            # Implementasi Preview Mode
            # Hanya berlaku untuk mode camera.
            if mode == "camera":
                preview_mode = settings_data.get("preview_mode", "Normal Window")
                if preview_mode == "Borderless":
                    args.append("--window-borderless")
                elif preview_mode == "Always On Top":
                    args.append("--always-on-top")
                elif preview_mode == "Hidden Preview":
                    args.append("--no-window")
                # Jika "Normal Window", kita tidak perlu menambahkan argumen apa pun (default scrcpy)
            elif mode == "mirror":
                # Gunakan title custom agar mudah dikenali tetapi biarkan window frame OS standar agar bisa di-close/drag
                args.extend(["--window-title=scrcpy_mirror"])

            # Menyembunyikan jendela console bawaan di Windows
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            
            self.logger.info(f"Menjalankan: {' '.join(args)}")

            # Menjalankan proses scrcpy
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags
            )
            self.processes[mode] = process
            self._last_return_codes[mode] = None

            threading.Thread(
                target=self._forward_process_output,
                args=(process, mode),
                daemon=True
            ).start()

            time.sleep(0.3)
            if process.poll() is not None:
                return_code = process.returncode
                self._last_return_codes[mode] = return_code
                if mode in self.processes:
                    del self.processes[mode]
                self.logger.error(f"scrcpy {mode} berhenti saat start. Exit code: {return_code}")
                return
            
            # Log informasi dengan tambahan target device jika ada
            self.logger.info(f"Kamera scrcpy ({mode}) berhasil dijalankan {'untuk device '+target_serial if target_serial else ''}.")
            
        except Exception as e:
            self.logger.error(f"Gagal menjalankan scrcpy {mode}: {e}")

    def list_cameras(self, target_serial=""):
        """Mengambil daftar kamera dari scrcpy --list-cameras."""
        args = [self.scrcpy_path]
        target_serial = (target_serial or "").strip()
        if target_serial:
            args.append(f"--serial={target_serial}")
        args.append("--list-cameras")

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        try:
            result = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
                timeout=8
            )
        except Exception as e:
            self.logger.error(f"Gagal membaca daftar kamera: {e}")
            return []

        if result.returncode != 0:
            self.logger.error(f"Gagal membaca daftar kamera scrcpy: {result.stdout.strip()}")
            return []

        cameras = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            match = re.search(r"(?:--)?camera-id=([^\s]+)", line)
            if not match:
                continue

            camera_id = match.group(1).strip(" ,")
            detail_match = re.search(r"\((.+)\)", line)
            detail = detail_match.group(1).strip() if detail_match else ""
            if not detail:
                detail = line.replace(match.group(0), "", 1).strip(" -")

            fps_match = re.search(r"fps=\{([^}]+)\}", detail)
            fps_values = []
            if fps_match:
                fps_values = [value.strip() for value in fps_match.group(1).split(",")]

            label = f"Camera {camera_id}"
            if detail:
                label = f"{label} ({detail})"

            cameras.append({
                "id": camera_id,
                "label": label,
                "fps": fps_values
            })

        if cameras:
            self.logger.info(f"Daftar kamera ditemukan: {len(cameras)} kamera.")
        else:
            self.logger.warning("scrcpy tidak mengembalikan daftar kamera.")

        return cameras

    def _forward_process_output(self, process, mode):
        """Meneruskan output scrcpy ke log aplikasi agar error tidak tersembunyi."""
        if process.stdout is None:
            return
        if mode not in self.process_logs:
            self.process_logs[mode] = []
        try:
            for line in process.stdout:
                message = line.strip()
                if message:
                    self.logger.info(f"scrcpy ({mode}): {message}")
                    self.process_logs[mode].append(message)
                    if len(self.process_logs[mode]) > 30:
                        self.process_logs[mode].pop(0)
        except Exception:
            pass

    def stop(self, mode=None):
        if mode is None:
            # Hentikan semua session jika mode tidak ditentukan
            modes = list(self.processes.keys())
            for m in modes:
                self.stop(m)
            return

        if self.is_running(mode):
            self._manual_stop[mode] = True
            self.logger.info(f"Menghentikan proses scrcpy ({mode})...")
            proc = self.processes[mode]
            del self.processes[mode]
            
            def terminate_worker():
                try:
                    proc.terminate()
                    # Wait up to 3 seconds for graceful terminate, fallback to kill
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                except Exception as e:
                    self.logger.error(f"Error terminating scrcpy ({mode}) process: {e}")
                    
            threading.Thread(target=terminate_worker, daemon=True).start()
            self.logger.info(f"Proses scrcpy ({mode}) dihentikan.")

    def is_running(self, mode=None):
        """Mengecek apakah proses scrcpy saat ini sedang berjalan."""
        if mode is None:
            # Jika mode tidak dispesifikasikan, return True jika ada session berjalan
            return any(self.is_running(m) for m in list(self.processes.keys()))

        if mode not in self.processes:
            return False
            
        process = self.processes[mode]
        # poll() mengembalikan None jika proses masih berjalan
        # Jika mengembalikan angka (return code), berarti proses sudah berhenti
        if process.poll() is not None:
            self._last_return_codes[mode] = process.returncode
            if mode in self.processes:
                del self.processes[mode] # Bersihkan referensi proses yang sudah mati
            return False
            
        return True

    def get_local_version(self):
        """Membaca versi scrcpy lokal dengan menjalankan 'scrcpy --version'."""
        scrcpy_path = Config.get_bin_path("scrcpy")
        if not scrcpy_path or not os.path.exists(scrcpy_path):
            return None
        try:
            startupinfo = None
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NO_WINDOW
            else:
                creationflags = 0

            result = subprocess.run(
                [scrcpy_path, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
                timeout=3
            )
            for line in result.stdout.splitlines():
                if "scrcpy" in line.lower():
                    parts = line.split()
                    for part in parts:
                        if part and part[0].isdigit():
                            return part.strip()
        except Exception as e:
            self.logger.error(f"Gagal mendeteksi versi scrcpy lokal: {e}")
        return None

    def get_latest_online_version(self):
        """Mengambil info rilis terbaru dari repo Genymobile/scrcpy di GitHub API."""
        try:
            import urllib.request
            import json
            req = urllib.request.Request(
                "https://api.github.com/repos/Genymobile/scrcpy/releases/latest",
                headers={"User-Agent": "Camera-Studio-UpdateChecker"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                tag_name = data.get("tag_name", "").strip()
                latest_ver = tag_name.lstrip("v")
                
                # Cari URL download zip 64-bit untuk Windows
                download_url = None
                assets = data.get("assets", [])
                for asset in assets:
                    name = asset.get("name", "")
                    if "win64" in name and name.endswith(".zip"):
                        download_url = asset.get("browser_download_url")
                        break
                        
                return latest_ver, download_url
        except Exception as e:
            self.logger.error(f"Gagal mengambil versi scrcpy terbaru dari GitHub: {e}")
        return None, None
