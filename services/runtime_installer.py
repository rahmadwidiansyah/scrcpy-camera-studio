import os
import logging
from services.runtime_manager import RuntimeManager

class RuntimeInstaller:
    """
    RuntimeInstaller orchestrates downloading, extracting, and installing
    individual runtime dependencies using RuntimeManager.
    """
    def __init__(self, runtime_manager=None, logger=None):
        self.runtime_manager = runtime_manager or RuntimeManager()
        self.logger = logger or logging.getLogger("CameraStudio.download")

    def install_dependency(self, name: str, progress_callback=None, status_callback=None) -> bool:
        """
        Downloads, extracts, and configures a runtime dependency, or installs natively on Linux.
        """
        name = name.lower()
        if name == "platform-tools":
            name = "adb"

        import platform
        import shutil
        import subprocess

        if platform.system() == "Linux":
            self.logger.info(f"Linux detected. Installing dependency {name} natively...")
            pkg_map = {
                "adb": {"pacman": ["android-tools"], "apt": ["adb"]},
                "scrcpy": {"pacman": ["scrcpy", "fontconfig", "pango"], "apt": ["scrcpy", "libpango-1.0-0", "libpangocairo-1.0-0", "fontconfig"]},
                "ffmpeg": {"pacman": ["ffmpeg"], "apt": ["ffmpeg"]}
            }
            
            pkg_info = pkg_map.get(name)
            if not pkg_info:
                return False

            if shutil.which("pkexec"):
                if shutil.which("pacman"):
                    cmd = ["pkexec", "pacman", "-S", "--noconfirm"] + pkg_info["pacman"]
                else:
                    cmd = f"pkexec apt-get update && pkexec apt-get install -y {' '.join(pkg_info['apt'])}"
            elif shutil.which("pacman"):
                cmd = ["sudo", "pacman", "-S", "--noconfirm"] + pkg_info["pacman"]
            elif shutil.which("apt-get"):
                cmd = f"sudo apt-get update && sudo apt-get install -y {' '.join(pkg_info['apt'])}"
            else:
                self.logger.error("Supported package manager (pacman/apt) not found.")
                return False

            try:
                shell_mode = isinstance(cmd, str)
                result = subprocess.run(
                    cmd,
                    shell=shell_mode,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=120
                )
                if result.returncode == 0:
                    self.logger.info(f"Natively installed {name} on Linux.")
                    return True
                else:
                    self.logger.error(f"Failed to install {name} via package manager: {result.stderr or result.stdout}")
                    return False
            except Exception as e:
                self.logger.error(f"Exception during Linux package install: {e}")
                return False

        try:
            self.logger.info(f"Starting installation of dependency: {name}")
            
            # Download zip package
            zip_path = self.runtime_manager.download(
                name, 
                progress_callback=progress_callback, 
                status_callback=status_callback
            )
            
            self.logger.info(f"Downloaded {name} to {zip_path}. Extracting zip...")
            
            # Extract and update local files
            self.runtime_manager.update(name, zip_path)
            
            # Clean up the temporary download zip
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                    self.logger.info(f"Cleaned up temporary file: {zip_path}")
                except Exception as cleanup_err:
                    self.logger.warning(f"Could not remove temporary ZIP file {zip_path}: {cleanup_err}")
            
            self.logger.info(f"Dependency {name} successfully installed.")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to install dependency {name}: {e}", exc_info=True)
            return False

    def install_all_missing(self, progress_callback=None, status_callback=None) -> dict:
        """
        Checks for missing dependencies ('adb', 'scrcpy', 'ffmpeg') and installs them.
        Returns a dictionary mapping each dependency name to its installation result.
        """
        dependencies = ["adb", "scrcpy", "ffmpeg"]
        results = {}
        
        for dep in dependencies:
            if self.runtime_manager.check_installed(dep):
                self.logger.info(f"Dependency {dep} is already installed. Skipping.")
                results[dep] = True
                continue
                
            self.logger.info(f"Dependency {dep} is missing. Triggering installation...")
            success = self.install_dependency(dep, progress_callback, status_callback)
            results[dep] = success
            
        return results
