from config import Config
from settings import SettingsManager
from logger import Logger
from adb_manager import ADBManager
from scrcpy_manager import ScrcpyManager
from installer_manager import InstallerManager
from ui import CameraStudioUI

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

def poll_devices(app, adb_manager, scrcpy_manager, settings):
    """Fungsi berkala untuk memperbarui list device setiap 2000ms (2 detik)."""
    devices = adb_manager.get_connected_devices()
    app.update_device_list(devices)

    target_serial = settings.get("target_device") or ""
    if target_serial and getattr(app, "_last_camera_scan_serial", None) != target_serial:
        app._last_camera_scan_serial = target_serial
        cameras = scrcpy_manager.list_cameras(target_serial)
        app.update_camera_options(cameras)
    elif not target_serial:
        app._last_camera_scan_serial = None
        app.update_camera_options([])
    
    # Daftarkan kembali fungsi ini untuk dipanggil 2 detik kemudian
    app.after(2000, lambda: poll_devices(app, adb_manager, scrcpy_manager, settings))

def poll_scrcpy_status(app, scrcpy_manager):
    """Fungsi berkala untuk memantau status proses scrcpy."""
    is_running = scrcpy_manager.is_running()
    # Asumsi UI memiliki method untuk update status UI jika scrcpy mati secara tiba-tiba
    if hasattr(app, 'update_scrcpy_status'):
        app.update_scrcpy_status(is_running)
    
    app.after(1000, lambda: poll_scrcpy_status(app, scrcpy_manager))

def main():
    logger = Logger()
    config = Config()
    settings = SettingsManager(logger)
    adb = ADBManager(logger)
    scrcpy = ScrcpyManager(logger)
    installer = InstallerManager(logger)

    app = CameraStudioUI()
    app.apply_theme(settings.get("theme"))
    logger.set_callback(app.append_log)
    logger.info("Memulai aplikasi Camera Studio...")

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

    app.after(500, lambda: check_all_dependencies(app, installer))
    app.after(1000, lambda: poll_devices(app, adb, scrcpy, settings))
    app.after(1500, lambda: poll_scrcpy_status(app, scrcpy))

    app.mainloop()
    
    # Memastikan proses scrcpy ikut mati jika jendela aplikasi di-close
    scrcpy.stop()

if __name__ == "__main__":
    main()
