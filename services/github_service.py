import os
import json
import ssl
import urllib.request
import logging

class GitHubService:
    def __init__(self):
        # Logger menggunakan kategori update/download
        self.logger = logging.getLogger("CameraStudio.update")

    def check_latest_release(self, repo):
        """
        Memeriksa rilis terbaru dari repositori GitHub tertentu.
        Mengembalikan dictionary berisi metadata rilis atau None jika gagal.
        """
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        try:
            self.logger.info(f"GitHubService: Memeriksa rilis terbaru untuk {repo}...")
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "Camera-Studio-GitHubService"}
            )
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=8, context=ctx) as response:
                data = json.loads(response.read().decode("utf-8"))
                
                tag_name = data.get("tag_name", "").strip()
                body = data.get("body", "")
                html_url = data.get("html_url", "")
                
                # Mengumpulkan daftar asset rilis
                assets = []
                for asset in data.get("assets", []):
                    assets.append({
                        "name": asset.get("name"),
                        "browser_download_url": asset.get("browser_download_url"),
                        "size": asset.get("size")
                    })
                
                return {
                    "tag_name": tag_name,
                    "version": tag_name.lstrip("v"),
                    "release_notes": body,
                    "download_url": html_url,
                    "assets": assets
                }
        except Exception as e:
            self.logger.error(f"GitHubService: Gagal memeriksa rilis untuk {repo}: {e}")
            return None

    def download_release(self, repo, tag, dest_dir):
        """
        Mengunduh arsip zip source code dari rilis (tag) tertentu ke dest_dir.
        Mengembalikan path file zip hasil unduhan atau None jika gagal.
        """
        zipball_url = f"https://api.github.com/repos/{repo}/zipball/{tag}"
        try:
            os.makedirs(dest_dir, exist_ok=True)
            repo_name_only = repo.split("/")[-1]
            dest_path = os.path.join(dest_dir, f"{repo_name_only}-{tag}.zip")
            
            self.logger.info(f"GitHubService: Mengunduh source code rilis {tag} dari {zipball_url}...")
            req = urllib.request.Request(
                zipball_url,
                headers={"User-Agent": "Camera-Studio-GitHubService"}
            )
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
                with open(dest_path, "wb") as f:
                    chunk_size = 16384
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        
            self.logger.info(f"GitHubService: Source code berhasil diunduh ke {dest_path}")
            return dest_path
        except Exception as e:
            self.logger.error(f"GitHubService: Gagal mengunduh source code rilis {tag}: {e}")
            return None

    def download_asset(self, asset_url, dest_path, progress_callback=None):
        """
        Mengunduh aset rilis tertentu dari asset_url ke dest_path.
        Mendukung progress_callback(downloaded_bytes, total_bytes).
        Mengembalikan path file hasil unduhan atau None jika gagal.
        """
        try:
            dest_dir = os.path.dirname(dest_path)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
                
            self.logger.info(f"GitHubService: Mengunduh asset dari {asset_url} ke {dest_path}...")
            req = urllib.request.Request(
                asset_url,
                headers={"User-Agent": "Camera-Studio-GitHubService"}
            )
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
                total_bytes = int(response.headers.get('content-length', 0))
                downloaded_bytes = 0
                chunk_size = 16384
                
                with open(dest_path, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
                        if progress_callback:
                            try:
                                progress_callback(downloaded_bytes, total_bytes)
                            except Exception:
                                pass
                                
            self.logger.info(f"GitHubService: Asset berhasil diunduh ke {dest_path}")
            return dest_path
        except Exception as e:
            self.logger.error(f"GitHubService: Gagal mengunduh asset: {e}")
            return None
