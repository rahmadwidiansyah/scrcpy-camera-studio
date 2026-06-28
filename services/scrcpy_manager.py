import subprocess
import os
import re
import threading
import time
from enum import Enum
from config.config import Config


def get_clean_subprocess_env() -> dict:
    """Return an environment safe for launching bundled ELF/GTK apps.

    Required sanitation: remove dynamic-loader variables that can break
    fontconfig/pango symbol resolution inside child processes.

    Preserves PATH/HOME/GUI session variables.
    """
    env = os.environ.copy()
    for k in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH"):
        env.pop(k, None)

    # Explicitly preserve expected keys only if they are not None.
    # copy() already copies them if present, but this ensures we don't inject None.
    _preserve = (
        "PATH",
        "HOME",
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
        "TERM",
    )
    for k in _preserve:
        val = os.environ.get(k)
        if val is not None:
            env[k] = val
        else:
            env.pop(k, None)

    return env



class CameraState(Enum):
    STOPPED = 0
    STARTING = 1
    RUNNING = 2
    STOPPING = 3
    RESTARTING = 4


class ScrcpyManager:
    def __init__(self, logger):
        self.logger = logger
        self.processes = {}  # dict mapping mode (e.g., 'camera', 'mirror') to process
        self.scrcpy_path = None
        self._last_return_codes = {}
        self.process_logs = {"camera": [], "mirror": []}
        self._manual_stop = {"camera": False, "mirror": False}
        self._error_reported = {"camera": False, "mirror": False}

        # Thread-safety for process handles + camera state transitions.
        self._state_lock = threading.RLock()
        self._camera_state = CameraState.STOPPED

    def _resolve_scrcpy_path(self):
        """Resolve the active scrcpy binary each time so packaged builds pick up updated runtime installs."""
        if self.scrcpy_path and os.path.exists(self.scrcpy_path):
            return self.scrcpy_path

        resolved = Config.get_bin_path("scrcpy")
        # CRITICAL: Check if binary actually exists (not just the directory)
        if resolved and os.path.exists(resolved):
            self.scrcpy_path = resolved
            return resolved

        # Binary not found anywhere
        self.scrcpy_path = None
        return None

    def get_camera_state(self):
        with self._state_lock:
            return self._camera_state

    def is_camera_active(self):
        with self._state_lock:
            return self._camera_state in (CameraState.STARTING, CameraState.RUNNING, CameraState.STOPPING, CameraState.RESTARTING)

    def is_camera_available(self):
        # For camera enumeration safety: only safe while STOPPED.
        with self._state_lock:
            return self._camera_state == CameraState.STOPPED

    def start(self, settings_data, mode="camera", parent_window_id=None):
        with self._state_lock:
            if mode == "camera":
                if self._camera_state in (CameraState.STARTING, CameraState.RUNNING, CameraState.STOPPING, CameraState.RESTARTING):
                    self.logger.warning("Scrcpy camera session sedang aktif. Mengabaikan start.")
                    return
                self._camera_state = CameraState.STARTING
            else:
                if self.is_running(mode):
                    self.logger.warning(f"Scrcpy mode {mode} sudah berjalan. Mengabaikan perintah Start.")
                    return

        try:
            self._manual_stop[mode] = False
            self._error_reported[mode] = False
            self._last_return_codes[mode] = None
            self.process_logs[mode] = []

            scrcpy_path = self._resolve_scrcpy_path()
            if not scrcpy_path:
                self.logger.error("Tidak dapat menemukan scrcpy yang dapat dieksekusi.")
                return

            self.logger.info(f"Menyiapkan parameter scrcpy (mode: {mode})...")
            # Ensure scrcpy path is re-resolved in case runtime was updated
            scrcpy_path = self._resolve_scrcpy_path()
            if not scrcpy_path:
                self.logger.error("Tidak dapat menemukan scrcpy yang dapat dieksekusi setelah update. Mohon restart aplikasi.")
                return

            if mode == "mirror":
                args = [scrcpy_path]
                if parent_window_id:
                    args.append(f"--parent={parent_window_id}")
            else:
                args = [scrcpy_path, "--video-source=camera"]

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
            bitrate = settings_data.get("bitrate", "8M")
            if mode == "mirror":
                res = settings_data.get("mirror_resolution", settings_data.get("resolution", "Auto"))
                bitrate = settings_data.get("mirror_bitrate", settings_data.get("bitrate", "8M"))
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
            # Requirement: Treat "Auto" as "do not pass --video-bit-rate".
            if bitrate:
                br = str(bitrate).strip()
                if br and br.lower() != "auto":
                    args.append(f"--video-bit-rate={br}")


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
                # scrcpy 4.0 expects mirror as horizontal flip via `flip{rotation}`.
                # (Vertical flip vs horizontal flip are not distinguishable by our UI; this mapping matches scrcpy's accepted tokens.)
                mirror = settings_data.get("mirror", False)
                if mirror:
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
            # Use the centralized helper so all scrcpy/adb launches receive a sanitized
            # environment (no LD_* / PYTHON* contamination on Linux packaged builds).
            # Windows behavior is unchanged: the helper just returns os.environ.copy() there.
            env = get_clean_subprocess_env()
            self.logger.debug(
                "Launching %s with sanitized env: "
                "LD_LIBRARY_PATH=%s LD_PRELOAD=%s",
                scrcpy_path,
                env.get("LD_LIBRARY_PATH"),
                env.get("LD_PRELOAD"),
            )

            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
                env=env,
            )

            self.processes[mode] = process
            self._last_return_codes[mode] = None

            # Watcher: ensures camera state never stays RUNNING if scrcpy exits unexpectedly.
            threading.Thread(
                target=self._watch_process_exit,
                args=(process, mode),
                daemon=True
            ).start()

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
                if mode == "camera":
                    with self._state_lock:
                        self._camera_state = CameraState.STOPPED
                self.logger.error(f"scrcpy {mode} berhenti saat start. Exit code: {return_code}")
                return

            if mode == "camera":
                with self._state_lock:
                    self._camera_state = CameraState.RUNNING

            # Log informasi dengan tambahan target device jika ada
            self.logger.info(f"Kamera scrcpy ({mode}) berhasil dijalankan {'untuk device '+target_serial if target_serial else ''}.")

        except Exception as e:
            if mode == "camera":
                with self._state_lock:
                    self._camera_state = CameraState.STOPPED
            self.logger.error(f"Gagal menjalankan scrcpy {mode}: {e}")

    def list_cameras(self, target_serial=""):
        """Mengambil daftar kamera dari scrcpy --list-cameras.

        Contract: Must never execute while the camera session is in STARTING/RUNNING/STOPPING/RESTARTING.
        """
        with self._state_lock:
            if self._camera_state in (CameraState.STARTING, CameraState.RUNNING, CameraState.STOPPING, CameraState.RESTARTING):
                return []

        scrcpy_path = self._resolve_scrcpy_path()
        # Guard: path must exist on disk before passing to subprocess
        if not scrcpy_path or not os.path.exists(scrcpy_path):
            # Only log once to avoid spam when scrcpy is not installed yet
            self.logger.debug("list_cameras: scrcpy belum terpasang atau path tidak valid, skip.")
            return []

        args = [scrcpy_path]
        target_serial = (target_serial or "").strip()
        if target_serial:
            args.append(f"--serial={target_serial}")
        args.append("--list-cameras")

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        # Use the centralized sanitized environment helper.
        env = get_clean_subprocess_env()
        self.logger.debug(
            "Launching %s with sanitized env: "
            "LD_LIBRARY_PATH=%s LD_PRELOAD=%s",
            scrcpy_path,
            env.get("LD_LIBRARY_PATH"),
            env.get("LD_PRELOAD"),
        )

        try:
            result = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
                env=env,
                timeout=8
            )
        except FileNotFoundError:
            self.logger.error(f"scrcpy binary tidak ditemukan di path: {scrcpy_path}")
            return []
        except subprocess.TimeoutExpired:
            self.logger.warning("list_cameras: scrcpy --list-cameras timeout, skip.")
            return []
        except Exception as e:
            self.logger.error(f"Gagal membaca daftar kamera: {e}")
            return []

        if result.returncode != 0:
            # Non-zero exit is normal when no device is connected; log as debug not error
            self.logger.debug(f"list_cameras: scrcpy exited {result.returncode}: {result.stdout.strip()[:200]}")
            return []

        cameras = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # FIX: corrected regex — was r"(?:--)?camera-id=([^\\s]+)" (wrong: \\s matches literal backslash+s)
            match = re.search(r"(?:--)?camera-id=(\S+)", line)
            if not match:
                continue

            camera_id = match.group(1).strip(" ,")
            # FIX: corrected regex — was r"\\((.+)\\\\)" (wrong escaping)
            detail_match = re.search(r"\((.+)\)", line)
            detail = detail_match.group(1).strip() if detail_match else ""
            if not detail:
                detail = line.replace(match.group(0), "", 1).strip(" -")

            # FIX: corrected regex — was r"fps=\\\{([^}]+)\\\}" (wrong escaping)
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
            self.logger.debug("list_cameras: scrcpy tidak mengembalikan daftar kamera.")

        return cameras

    def _watch_process_exit(self, process, mode):
        """Wait for scrcpy process exit and reconcile camera state.

        Requirement:
        - If process exits unexpectedly while camera session is STARTING/RUNNING,
          transition camera to STOPPED immediately and remove process handles.
        - If stop() was invoked (manual), state reconciliation is allowed but should not
          trigger unexpected error handling.
        """
        try:
            rc = process.wait()
        except Exception:
            rc = None

        with self._state_lock:
            # Update last return code.
            if mode in self._last_return_codes:
                self._last_return_codes[mode] = rc

            # Remove handle if still present.
            if mode in self.processes and self.processes.get(mode) is process:
                try:
                    del self.processes[mode]
                except Exception:
                    pass

            if mode == "camera":
                # Only change state for camera transitions; STOPPED is always safe.
                # If this exit is the result of stop(), manual_stop will be True.
                # Otherwise, we must not remain in RUNNING.
                manual = bool(self._manual_stop.get("camera", False))
                self._camera_state = CameraState.STOPPED

                # Clear busy flags so subsequent starts are allowed.
                # IMPORTANT: only clear manual_stop after state reconciliation is done.
                self._manual_stop["camera"] = False

                if not manual:
                    self.logger.error(f"scrcpy camera exited unexpectedly (rc={rc}). Camera state forced to STOPPED.")


        # Note: UI is updated by existing poll_scrcpy_status() which queries is_running("camera").

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

        if mode == "camera":
            # Requirement: change state to STOPPING, wait for process termination,
            # then remove process handles, finally STOPPED.
            with self._state_lock:
                if self._camera_state in (CameraState.STOPPING, CameraState.STOPPED):
                    return
                self._camera_state = CameraState.STOPPING

                proc = self.processes.get(mode)
                if proc is None:
                    self._camera_state = CameraState.STOPPED
                    return

            # Terminate + wait (do not use async terminate thread for camera stop)
            try:
                self._manual_stop[mode] = True
                self.logger.info("Menghentikan proses scrcpy (camera)...")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            finally:
                with self._state_lock:
                    if mode in self.processes:
                        del self.processes[mode]
                    self._camera_state = CameraState.STOPPED
                    self.logger.info("Proses scrcpy (camera) dihentikan.")
            return

        # Mirror mode behavior remains unchanged (non-camera)
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
        scrcpy_path = self._resolve_scrcpy_path()
        if not scrcpy_path or not os.path.exists(scrcpy_path):
            return None
        try:
            startupinfo = None
            if os.name == 'nt':
                creationflags = subprocess.CREATE_NO_WINDOW
            else:
                creationflags = 0

            # Use centralized sanitized env helper for Linux packaged builds.
            env = get_clean_subprocess_env()
            self.logger.debug(
                "Launching %s with sanitized env: "
                "LD_LIBRARY_PATH=%s LD_PRELOAD=%s",
                scrcpy_path,
                env.get("LD_LIBRARY_PATH"),
                env.get("LD_PRELOAD"),
            )

            result = subprocess.run(
                [scrcpy_path, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
                env=env,
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
            import ssl

            # Create an SSL context that does not verify certificates
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(
                "https://api.github.com/repos/Genymobile/scrcpy/releases/latest",
                headers={"User-Agent": "Camera-Studio-UpdateChecker"}
            )
            with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
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
