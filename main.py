import threading
from config.config import Config
from config.settings import SettingsManager
from services.logger import Logger
from services.adb_manager import ADBManager
from services.scrcpy_manager import ScrcpyManager
from updater.installer_manager import InstallerManager
from services.ui import CameraStudioUI
from config.version import current_version, build_number, release_channel
from updater.update_checker import UpdateChecker
from services.event_bus import EventBus
from services.update_service import UpdateService
from services.update_coordinator import UpdateCoordinator
from services.update_presenter import UpdatePresenter

def check_all_dependencies(app, installer):
    """Mengecek semua dependensi dan memicu alur installer jika ada yang hilang."""
    deps = [
        ("adb", False),
        ("scrcpy", False),
        ("SDL2", False),
        ("ffmpeg", True)
    ]
    for dep_name, is_optional in deps:
        is_found = Config.check_dependency(dep_name)
        app.update_dependency_status(dep_name, is_found, is_optional)

    # --- Pemicu Installer Manager ---
    missing_deps = installer.get_missing_dependencies()
    if missing_deps:
        installer.logger.warning(f"Sistem kehilangan komponen inti: {', '.join(missing_deps)}.")
        app.show_installer_flow(True)  # Tampilkan tombol Install
    else:
        app.show_installer_flow(False) # Sembunyikan tombol Install

def poll_devices_worker(app, adb_manager, scrcpy_manager, settings):
    """Pekerja latar belakang (background thread) untuk memperbarui list device setiap 2 detik secara non-blocking."""
    import time
    import logging
    exception_logger = logging.getLogger("CameraStudio.exception")

    while True:
        try:
            # Periksa apakah window aplikasi masih aktif
            if not app.winfo_exists():
                break
        except Exception:
            break

        try:
            # Panggilan subprocess ADB & scrcpy (blocking, aman dijalankan di thread ini)
            devices = adb_manager.get_connected_devices()
            app.after(0, lambda d=devices: app.update_device_list(d))

            camera_serial = (settings.get("camera_device") or settings.get("target_device") or "").strip()
            last_serial = getattr(app, "_last_camera_scan_serial", None)
            last_had_cameras = getattr(app, "_last_camera_scan_had_cameras", None)
            if camera_serial:
                # CRITICAL: Do not trigger list_cameras if scrcpy is actively running, as it will lock/interrupt the camera resource.
                if (last_serial != camera_serial or last_had_cameras is False) and not scrcpy_manager.is_camera_active():
                    app._last_camera_scan_serial = camera_serial
                    cameras = scrcpy_manager.list_cameras(camera_serial)
                    app._last_camera_scan_had_cameras = bool(cameras)
                    app.after(0, lambda c=cameras: app.update_camera_options(c))
            else:
                app._last_camera_scan_serial = None
                app._last_camera_scan_had_cameras = None
                app.after(0, lambda: app.update_camera_options([]))
        except Exception as e:
            exception_logger.error(f"Error in poll_devices_worker: {e}", exc_info=True)

        time.sleep(2.0)

def poll_scrcpy_status(app, scrcpy_manager):
    """Fungsi berkala untuk memantau status proses scrcpy."""
    try:
        if not app.winfo_exists():
            return
    except Exception:
        return

    statuses = {
        "camera": scrcpy_manager.is_running("camera"),
        "mirror": scrcpy_manager.is_running("mirror")
    }
    if hasattr(app, 'update_scrcpy_status'):
        try:
            app.update_scrcpy_status(statuses)
        except Exception:
            return

    # Check for unexpected crashes
    for mode in ["camera", "mirror"]:
        if not statuses[mode]:
            ret_code = scrcpy_manager._last_return_codes.get(mode)
            if ret_code is not None and ret_code != 0 and not scrcpy_manager._manual_stop.get(mode, False) and not scrcpy_manager._error_reported.get(mode, False):
                scrcpy_manager._error_reported[mode] = True
                logs = scrcpy_manager.process_logs.get(mode, [])
                if hasattr(app, 'show_scrcpy_error_dialog'):
                    app.after(0, lambda m=mode, c=ret_code, l=logs: app.show_scrcpy_error_dialog(m, c, l))
    
    try:
        app.after(1000, lambda: poll_scrcpy_status(app, scrcpy_manager))
    except Exception:
        pass

def check_scrcpy_updates_async(app, scrcpy_manager, installer, logger):
    """Cek versi scrcpy secara asinkron setelah startup."""
    def run_check():
        import os
        from config.config import Config
        from packaging.version import parse as parse_version

        scrcpy_dir = os.path.join(Config.BIN_DIR, "scrcpy")
        is_scrcpy_installed = Config.check_dependency("scrcpy")

        min_required_ver = "4.0"
        default_url = "https://github.com/Genymobile/scrcpy/releases/download/v4.0/scrcpy-win64-v4.0.zip"

        if not is_scrcpy_installed or not os.path.exists(scrcpy_dir):
            logger.info("scrcpy belum terpasang. Mengambil URL rilis terbaru...")
            latest_ver, download_url = scrcpy_manager.get_latest_online_version()
            if download_url:
                installer.scrcpy_win_url = download_url
                logger.info(f"Mengunduh scrcpy versi terbaru secara otomatis: {latest_ver}")
            else:
                installer.scrcpy_win_url = default_url
                logger.info(f"Mengunduh scrcpy versi minimal secara otomatis: {min_required_ver}")
            # Jalankan instalasi otomatis di UI
            app.after(0, lambda: app._on_install_clicked())
            return

        # Cek versi lokal scrcpy
        local_ver = scrcpy_manager.get_local_version()
        if not local_ver:
            logger.warning("Gagal mendeteksi versi lokal scrcpy.")
            return

        logger.info(f"Versi scrcpy lokal: v{local_ver}")

        # Cek apakah versi lokal di bawah versi minimal v4.0
        is_below_min = False
        try:
            if parse_version(local_ver) < parse_version(min_required_ver):
                is_below_min = True
                logger.info(f"Versi lokal ({local_ver}) di bawah versi minimal ({min_required_ver}). Menawarkan update ke v{min_required_ver}...")
        except Exception as e:
            logger.error(f"Gagal memeriksa versi minimal scrcpy: {e}")

        # Ambil versi terbaru di GitHub API
        latest_ver, download_url = scrcpy_manager.get_latest_online_version()
        
        target_ver = latest_ver if latest_ver else min_required_ver
        target_url = download_url if download_url else default_url

        if is_below_min:
            app.after(0, lambda: app.show_scrcpy_update_prompt(local_ver, target_ver, target_url, installer))
            return

        if not latest_ver or not download_url:
            logger.warning("Gagal mendeteksi versi scrcpy terbaru di internet.")
            return

        logger.info(f"Versi scrcpy terbaru di internet: v{latest_ver}")

        try:
            if parse_version(latest_ver) > parse_version(local_ver):
                logger.info(f"Pembaruan scrcpy tersedia: v{local_ver} -> v{latest_ver}")
                app.after(0, lambda: app.show_scrcpy_update_prompt(local_ver, latest_ver, download_url, installer))
            else:
                logger.info("scrcpy sudah menggunakan versi terbaru.")
        except Exception as e:
            logger.error(f"Gagal membandingkan versi scrcpy: {e}")

    threading.Thread(target=run_check, daemon=True).start()

def main():
    logger = Logger()
    config = Config()
    settings = SettingsManager(logger.get_logger("startup"))
    adb = ADBManager(logger.get_logger("adb"))
    scrcpy = ScrcpyManager(logger.get_logger("scrcpy"))
    installer = InstallerManager(logger.get_logger("download"))
    update_checker = UpdateChecker(logger.get_logger("update"))

    app = CameraStudioUI()
    app.logger = logger.get_logger("startup")
    app._adb_manager = adb   # expose so Devices page can call WiFi ADB helpers
    app.apply_theme(settings.get("theme"))
    logger.set_callback(app.append_log)
    app._ensure_log_textbox()   # create txt_log before any log messages
    logger.info(f"Memulai aplikasi Camera Studio v{current_version} (Build {build_number}) [{release_channel}]...")

    app.load_settings_to_ui(settings.current_settings)

    # Callback ketika instalasi (di thread terpisah) selesai
    def on_install_done(status):
        if status == "Success":
            # app.after(0) memastikan update UI dieksekusi di main thread secara aman
            app.after(0, lambda: app.btn_install.configure(
                text="Install Complete! Please Restart App.", 
                fg_color="#2ECC71"
            ))
        else:
            app.after(0, lambda: app.btn_install.configure(
                text="Install Failed! Check Log.", 
                fg_color="#E74C3C"
            ))

    def on_scrcpy_start(mode="camera"):
        # Buat salinan settings dan inject serial yang tepat per mode
        import copy
        s = copy.deepcopy(settings.current_settings)
        if mode == "mirror":
            # Mirror gunakan mirror_device; fallback ke target_device (legacy)
            serial = s.get("mirror_device") or s.get("target_device", "")
            s["target_device"] = serial
            from services.ui import MirrorControlCenter
            control_center = MirrorControlCenter(app, scrcpy)
            app.mirror_control_center = control_center
            def start_worker():
                scrcpy.start(s, mode="mirror")
            threading.Thread(target=start_worker, daemon=True).start()
        else:
            # Camera gunakan camera_device; fallback ke target_device (legacy)
            serial = s.get("camera_device") or s.get("target_device", "")
            s["target_device"] = serial
            threading.Thread(target=lambda: scrcpy.start(s, mode="camera"), daemon=True).start()

    def on_setting_change_intercept(key, value):
        settings.set(key, value)
        if key in ("rotate", "mirror", "resolution", "fps", "bitrate",
                   "audio_source", "preview_mode", "aspect_ratio"):
            if scrcpy.is_running("camera"):
                logger.info(f"Pengaturan '{key}' diubah. Memuat ulang kamera secara otomatis...")
                def restart_worker():
                    scrcpy.stop("camera")
                    import time
                    time.sleep(0.5)
                    import copy
                    s = copy.deepcopy(settings.current_settings)
                    serial = s.get("camera_device") or s.get("target_device", "")
                    s["target_device"] = serial
                    scrcpy.start(s, mode="camera")
                threading.Thread(target=restart_worker, daemon=True).start()

    app.set_callbacks(
        start_cb=on_scrcpy_start,
        stop_cb=scrcpy.stop,
        setting_change_cb=on_setting_change_intercept,
        # Arahkan ke start_install sungguhan dan lemparkan callback on_install_done
        install_cb=lambda: installer.start_install(on_complete_callback=on_install_done)
    )

    # Initialize Update Coordinator & Presenter
    event_bus = EventBus()
    update_service = UpdateService(app_dir=Config.APP_DIR)
    update_coordinator = UpdateCoordinator(update_service=update_service, event_bus=event_bus)
    update_presenter = UpdatePresenter(coordinator=update_coordinator, event_bus=event_bus, ui_view=app)

    def run_coordinator_update_check():
        def check_worker():
            try:
                update_coordinator.check()
            except Exception as e:
                logger.get_logger("update").error(f"Error checking updates via coordinator: {e}")
        threading.Thread(target=check_worker, daemon=True).start()

    app.after(500, lambda: check_all_dependencies(app, installer))
    
    # Jalankan polling perangkat di background thread agar UI tidak memblokir (non-blocking)
    threading.Thread(
        target=poll_devices_worker,
        args=(app, adb, scrcpy, settings),
        daemon=True
    ).start()
    
    app.after(1500, lambda: poll_scrcpy_status(app, scrcpy))
    app.after(2000, run_coordinator_update_check)
    app.after(2500, lambda: check_scrcpy_updates_async(app, scrcpy, installer, logger.get_logger("update")))

    app.mainloop()
    
    # Memastikan proses scrcpy ikut mati jika jendela aplikasi di-close
    scrcpy.stop()

if __name__ == "__main__":
    main()
