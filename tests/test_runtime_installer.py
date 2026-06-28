import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.runtime_installer import RuntimeInstaller


class TestRuntimeInstaller(unittest.TestCase):
    @patch("subprocess.run")
    @patch("shutil.which")
    @patch("platform.system")
    def test_install_dependency_scrcpy_on_linux_installs_fontconfig_and_pango(self, mock_platform, mock_which, mock_run):
        mock_platform.return_value = "Linux"
        mock_which.side_effect = lambda name: "/usr/bin/pacman" if name == "pacman" else None
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        installer = RuntimeInstaller(runtime_manager=MagicMock(), logger=MagicMock())
        success = installer.install_dependency("scrcpy")

        self.assertTrue(success)
        cmd = mock_run.call_args.args[0]
        self.assertIn("pacman", cmd)
        self.assertIn("fontconfig", cmd)
        self.assertIn("pango", cmd)


if __name__ == "__main__":
    unittest.main()
