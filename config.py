import os
import shutil

class Config:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

    # Path folder lokal untuk binary pihak ketiga
    BIN_DIR = os.path.join(APP_DIR, "bin")

    @staticmethod
    def check_dependency(name):
        """
        Mengecek ketersediaan dependency dengan aturan prioritas:
        1. Cek folder lokal bin/ terlebih dahulu.
        2. Jika tidak ada, baru cek di PATH sistem.
        """
        exe_name = f"{name}.exe" if os.name == 'nt' else name
        bin_path = os.path.join(Config.BIN_DIR, exe_name)
        
        # Prioritas 1: Cek di folder bin/ lokal
        if os.path.exists(bin_path):
            return True
            
        # Prioritas 2: Cek di System PATH (Global)
        if shutil.which(name):
            return True
            
        # Penanganan khusus untuk SDL2 (bawaan scrcpy)
        if name.lower() == "sdl2":
            sdl_lib = "SDL2.dll" if os.name == 'nt' else "libSDL2.so"
            if os.path.exists(os.path.join(Config.BIN_DIR, sdl_lib)):
                return True
            # Jika scrcpy global tersedia, asumsikan SDL2 juga aman di sistem
            if shutil.which("scrcpy"):
                return True

        return False

    @staticmethod
    def get_bin_path(name):
        """
        Mendapatkan path executable yang valid dengan aturan prioritas:
        1. Gunakan binary yang ada di folder bin/ lokal jika tersedia.
        2. Jika tidak ditemukan, cari dan gunakan path dari PATH sistem.
        3. Fallback ke default path jika tidak ditemukan di keduanya.
        """
        exe_name = f"{name}.exe" if os.name == 'nt' else name
        bin_path = os.path.join(Config.BIN_DIR, exe_name)
        
        # Prioritas 1: Gunakan biner dari folder bin/ lokal jika ada
        if os.path.exists(bin_path):
            return os.path.abspath(bin_path)
            
        # Prioritas 2: Cari di PATH sistem jika tidak ditemukan di folder bin/
        system_path = shutil.which(name)
        if system_path:
            return system_path
            
        # Fallback terakhir jika benar-benar tidak ditemukan di mana pun
        return bin_path
