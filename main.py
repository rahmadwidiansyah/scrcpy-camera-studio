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

            target_serial = settings.get("target_device") or ""
            if target_serial and getattr(app, "_last_camera_scan_serial", None) != target_serial:
                app._last_camera_scan_serial = target_serial
                cameras = scrcpy_manager.list_cameras(target_serial)
                app.after(0, lambda c=cameras: app.update_camera_options(c))
            elif not target_serial:
                app._last_camera_scan_serial = None
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

    is_running = scrcpy_manager.is_running()
    # Asumsi UI memiliki method untuk update status UI jika scrcpy mati secara tiba-tiba
    if hasattr(app, 'update_scrcpy_status'):
        try:
            app.update_scrcpy_status(is_running)
        except Exception:
            return
    
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

        if not is_scrcpy_installed or not os.path.exists(scrcpy_dir):
            logger.info("scrcpy belum terpasang. Mengambil URL rilis terbaru...")
            latest_ver, download_url = scrcpy_manager.get_latest_online_version()
            if download_url:
                installer.scrcpy_win_url = download_url
                logger.info(f"Mengunduh scrcpy versi terbaru secara otomatis: {latest_ver}")
            # Jalankan instalasi otomatis di UI
            app.after(0, lambda: app._on_install_clicked())
            return

        # Cek versi lokal scrcpy
        local_ver = scrcpy_manager.get_local_version()
        if not local_ver:
            logger.warning("Gagal mendeteksi versi lokal scrcpy.")
            return

        logger.info(f"Versi scrcpy lokal: v{local_ver}")

        # Ambil versi terbaru di GitHub API
        latest_ver, download_url = scrcpy_manager.get_latest_online_version()
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
    app.apply_theme(settings.get("theme"))
    logger.set_callback(app.append_log)
    logger.info(f"Memulai aplikasi Camera Studio v{current_version} (Build {build_number}) [{release_channel}]...")

    app.load_settings_to_ui(settings.current_settings)

    # Callback ketika instalasi (di thread terpisah) selesai
    def on_install_done(status):
        if status == "Success":
            # app.after(0) memastikan update UI dieksekusi di main thread secara aman
            app.after(0, lambda: app.btn_install.configure(
                text="Install Complete! Please Restart App.", 
                fg_color="#28a745"
            ))
        else:
            app.after(0, lambda: app.btn_install.configure(
                text="Install Failed! Check Log.", 
                fg_color="#dc3545"
            ))

    app.set_callbacks(
        start_cb=lambda: scrcpy.start(settings.current_settings),
        stop_cb=scrcpy.stop,
        setting_change_cb=settings.set,
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
