import os
import sys
import shutil
import time
import zipfile
import argparse
import subprocess

# Ensure app directory is in sys.path to find config and services packages
app_dir_path = os.path.dirname(os.path.abspath(__file__))
if app_dir_path not in sys.path:
    sys.path.insert(0, app_dir_path)

try:
    from services.directory_manager import DirectoryManager
except Exception:
    DirectoryManager = None

try:
    # Mengambil APP_NAME dari AppInfo untuk menjaga kekonsistenan path satu tempat
    from config.app_info import AppInfo
    APP_NAME = AppInfo.APP_NAME
except Exception:
    APP_NAME = "CameraStudio"

def log(msg):
    print(f"[Updater] {msg}", flush=True)
    try:
        if DirectoryManager:
            log_dir = DirectoryManager.LOGS_DIR
        else:
            # Fallback to local logs directory if DirectoryManager is not available
            app_dir = os.path.dirname(os.path.abspath(__file__))
            log_dir = os.path.join(app_dir, "logs")
            
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "update.log")
        
        # Rotasi log manual jika ukuran berkas melebihi 1MB
        if os.path.exists(log_file) and os.path.getsize(log_file) > 1024 * 1024:
            try:
                for i in range(4, 0, -1):
                    src = f"{log_file}.{i}"
                    dst = f"{log_file}.{i+1}"
                    if os.path.exists(src):
                        shutil.move(src, dst)
                shutil.move(log_file, f"{log_file}.1")
            except Exception:
                pass
                
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def wait_for_parent(pid, timeout=10):
    log(f"Menunggu proses utama (PID: {pid}) untuk selesai...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not is_process_running(pid):
            log("Proses utama telah berhenti.")
            return True
        time.sleep(0.5)
    log("Timeout menunggu proses utama berhenti.")
    return False

def is_process_running(pid):
    if pid <= 0:
        return False
    try:
        if os.name == 'nt':
            import ctypes
            PROCESS_QUERY_INFORMATION = 0x0400
            SYNCHRONIZE = 0x0010
            process = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | SYNCHRONIZE, False, pid)
            if process:
                exit_code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(process)
                return exit_code.value == 259 # STILL_ACTIVE
            return False
        else:
            os.kill(pid, 0)
            return True
    except OSError:
        return False

def perform_update(app_dir, archive_path):
    if DirectoryManager:
        cache_dir = DirectoryManager.CACHE_DIR
    else:
        # Fallback if DirectoryManager is not available
        if os.name == 'nt':
            local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
            data_dir = os.path.join(local_appdata, APP_NAME)
        else:
            data_dir = os.path.join(os.path.expanduser("~"), ".local", "share", APP_NAME)
        cache_dir = os.path.join(data_dir, "cache")
    
    backup_dir = os.path.join(cache_dir, "backup_old_version")
    extract_dir = os.path.join(cache_dir, "temp_extracted")

    # Bersihkan folder sisa backup/extract jika ada
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)

    os.makedirs(backup_dir, exist_ok=True)
    os.makedirs(extract_dir, exist_ok=True)

    # File/direktori yang diabaikan agar tidak dibackup atau diganti
    ignored_items = {".git", ".venv", "cache", "logs", "updater.py", "settings.json", "__pycache__"}
    items_to_backup = []
    for item in os.listdir(app_dir):
        if item not in ignored_items:
            items_to_backup.append(item)

    log(f"Membuat backup untuk item: {items_to_backup}...")
    try:
        for item in items_to_backup:
            src = os.path.join(app_dir, item)
            dst = os.path.join(backup_dir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        log("Backup berhasil dibuat.")
    except Exception as e:
        log(f"Gagal membuat backup: {e}")
        return False

    # Ekstrak arsip baru
    log(f"Mengekstrak file update: {archive_path}...")
    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        log("Ekstraksi selesai.")
    except Exception as e:
        log(f"Gagal mengekstrak file update: {e}")
        shutil.rmtree(extract_dir, ignore_errors=True)
        return False

    # Timpa file lama dengan yang baru
    log("Mengganti file aplikasi dengan versi baru...")
    try:
        src_root = extract_dir
        extracted_items = os.listdir(extract_dir)
        # Jika arsip dibungkus subfolder utama (misalnya dari release zip github)
        if len(extracted_items) == 1 and os.path.isdir(os.path.join(extract_dir, extracted_items[0])):
            src_root = os.path.join(extract_dir, extracted_items[0])

        # Hapus file lama sebelum menyalin file baru
        for item in items_to_backup:
            target_path = os.path.join(app_dir, item)
            if os.path.exists(target_path):
                if os.path.isdir(target_path):
                    shutil.rmtree(target_path)
                else:
                    os.remove(target_path)

        # Salin file baru ke direktori utama
        for item in os.listdir(src_root):
            if item in ignored_items:
                continue
            src = os.path.join(src_root, item)
            dst = os.path.join(app_dir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        
        log("Aplikasi berhasil diperbarui.")
        
        # Bersihkan direktori backup dan ekstraksi
        shutil.rmtree(backup_dir, ignore_errors=True)
        shutil.rmtree(extract_dir, ignore_errors=True)
        # Hapus file arsip
        try:
            os.remove(archive_path)
        except Exception:
            pass
        return True

    except Exception as e:
        log(f"Gagal mengganti file aplikasi: {e}. Memulai pemulihan (restore) dari backup...")
        try:
            # Kembalikan file dari folder backup
            for item in os.listdir(backup_dir):
                dst = os.path.join(app_dir, item)
                if os.path.exists(dst):
                    if os.path.isdir(dst): shutil.rmtree(dst)
                    else: os.remove(dst)
                
                src = os.path.join(backup_dir, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
            log("Restore backup selesai dilakukan secara otomatis.")
        except Exception as restore_err:
            log(f"CRITICAL: Gagal memulihkan backup! Aplikasi mungkin dalam kondisi korup: {restore_err}")
        
        shutil.rmtree(extract_dir, ignore_errors=True)
        shutil.rmtree(backup_dir, ignore_errors=True)
        return False

def restart_app(app_dir, main_script):
    log("Merestart aplikasi...")
    python_exe = sys.executable

    try:
        if os.name == 'nt':
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen([python_exe, main_script], cwd=app_dir, creationflags=DETACHED_PROCESS)
        else:
            subprocess.Popen(
                [python_exe, main_script],
                cwd=app_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True
            )
        log("Aplikasi berhasil direstart.")
    except Exception as e:
        log(f"Gagal merestart aplikasi: {e}")

def main():
    parser = argparse.ArgumentParser(description="Updater Independen untuk Camera Studio")
    parser.add_argument("--app-dir", required=True, help="Direktori root aplikasi")
    parser.add_argument("--archive", required=True, help="Path ke file update ZIP")
    parser.add_argument("--main-script", default="main.py", help="Entry point script utama")
    parser.add_argument("--parent-pid", type=int, required=True, help="PID dari aplikasi utama")

    args = parser.parse_args()

    # Tunggu sejenak agar proses pemanggil sempat keluar
    time.sleep(0.5)

    if not wait_for_parent(args.parent_pid):
        log("Proses utama tidak kunjung mati. Membatalkan update.")
        sys.exit(1)

    success = perform_update(args.app_dir, args.archive)
    if success:
        log("Update sukses.")
    else:
        log("Update gagal.")

    restart_app(args.app_dir, args.main_script)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
