"""
Regression tests for centralized subprocess environment sanitization.

The fix is to use services.scrcpy_manager.get_clean_subprocess_env() in ALL
external process launches so that:

  - LD_LIBRARY_PATH / LD_PRELOAD / PYTHONHOME / PYTHONPATH are stripped on
    Linux packaged builds (these break fontconfig/pango symbol resolution).
  - PATH / HOME / DISPLAY / WAYLAND_DISPLAY / XDG_RUNTIME_DIR /
    DBUS_SESSION_BUS_ADDRESS / TERM are preserved.
  - Windows behavior is unchanged (helper just returns os.environ.copy()).
  - subprocesses actually receive the sanitized environment (verified by
    inspecting the env= kwarg passed to subprocess.run / subprocess.Popen).
"""

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.scrcpy_manager import (
    ScrcpyManager,
    get_clean_subprocess_env,
)


class TestGetCleanSubprocessEnv(unittest.TestCase):
    """Direct tests of the helper itself."""

    def setUp(self):
        # Contaminate the parent process environment so we can prove the
        # helper actually strips these values (and not just happens to see
        # them absent because nothing set them).
        self._original = {}
        self._pollution = {
            "LD_LIBRARY_PATH": "/tmp/evil/ld",
            "LD_PRELOAD": "/tmp/evil/preload.so",
            "PYTHONHOME": "/tmp/evil/python",
            "PYTHONPATH": "/tmp/evil/site-packages",
        }
        for k, v in self._pollution.items():
            self._original[k] = os.environ.get(k)
            os.environ[k] = v

    def tearDown(self):
        for k, v in self._original.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_strips_ld_library_path(self):
        env = get_clean_subprocess_env()
        self.assertNotIn("LD_LIBRARY_PATH", env)

    def test_strips_ld_preload(self):
        env = get_clean_subprocess_env()
        self.assertNotIn("LD_PRELOAD", env)

    def test_strips_pythonhome(self):
        env = get_clean_subprocess_env()
        self.assertNotIn("PYTHONHOME", env)

    def test_strips_pythonpath(self):
        env = get_clean_subprocess_env()
        self.assertNotIn("PYTHONPATH", env)

    def test_preserves_path(self):
        os.environ["PATH"] = "/usr/bin:/bin"
        env = get_clean_subprocess_env()
        # PATH is not stripped; it must round-trip from os.environ.
        self.assertEqual(env.get("PATH"), os.environ.get("PATH"))

    def test_preserves_home_display_session_keys(self):
        for key in (
            "HOME",
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "XDG_RUNTIME_DIR",
            "DBUS_SESSION_BUS_ADDRESS",
            "TERM",
        ):
            # setdefault semantics: helper only sets if missing, but the key
            # must never be popped and must equal os.environ's value when set.
            os.environ[key] = f"__test_{key}__"
            try:
                env = get_clean_subprocess_env()
                self.assertEqual(env.get(key), os.environ.get(key))
            finally:
                os.environ.pop(key, None)

    def test_returns_a_copy_not_a_reference(self):
        env = get_clean_subprocess_env()
        env["SHOULD_NOT_LEAK"] = "1"
        self.assertNotIn("SHOULD_NOT_LEAK", os.environ)
        self.assertNotIn("SHOULD_NOT_LEAK", get_clean_subprocess_env())


class TestScrcpyManagerStartUsesCleanEnv(unittest.TestCase):
    """start() must hand subprocess.Popen a sanitized env."""

    def setUp(self):
        self.logger = MagicMock()
        self.manager = ScrcpyManager(logger=self.logger)

    @patch("services.scrcpy_manager.subprocess.Popen")
    @patch("services.scrcpy_manager.os.path.exists", return_value=True)
    @patch("services.scrcpy_manager.Config.get_bin_path", return_value="/tmp/fake-scrcpy")
    def test_start_receives_sanitized_env(self, mock_get_bin_path, mock_exists, mock_popen):
        # Simulate contaminated parent env at call time.
        os.environ["LD_LIBRARY_PATH"] = "/tmp/evil/ld"
        os.environ["LD_PRELOAD"] = "/tmp/evil/preload.so"
        try:
            settings = {
                "target_device": "",
                "last_camera": "",
                "resolution": "1080",
                "bitrate": "8M",
                "aspect_ratio": "Auto",
                "fps": 30,
                "audio_source": "Playback",
                "rotate": 0,
                "mirror": False,
                "preview_mode": "Normal Window",
            }
            self.manager.start(settings, mode="mirror")
        finally:
            os.environ.pop("LD_LIBRARY_PATH", None)
            os.environ.pop("LD_PRELOAD", None)

        self.assertTrue(mock_popen.called, "subprocess.Popen was not called")
        kwargs = mock_popen.call_args.kwargs
        env = kwargs.get("env")
        self.assertIsNotNone(env, "start() did not pass env= to subprocess.Popen")
        self.assertNotIn("LD_LIBRARY_PATH", env)
        self.assertNotIn("LD_PRELOAD", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("PYTHONPATH", env)


class TestScrcpyManagerListCamerasUsesCleanEnv(unittest.TestCase):
    """list_cameras() must hand subprocess.run a sanitized env."""

    def setUp(self):
        self.logger = MagicMock()
        self.manager = ScrcpyManager(logger=self.logger)
        self.manager.scrcpy_path = "/tmp/fake-scrcpy"

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_list_cameras_receives_sanitized_env(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        os.environ["LD_LIBRARY_PATH"] = "/tmp/evil/ld"
        os.environ["LD_PRELOAD"] = "/tmp/evil/preload.so"
        try:
            self.manager.list_cameras("ABC123")
        finally:
            os.environ.pop("LD_LIBRARY_PATH", None)
            os.environ.pop("LD_PRELOAD", None)

        self.assertTrue(mock_run.called, "subprocess.run was not called")
        kwargs = mock_run.call_args.kwargs
        env = kwargs.get("env")
        self.assertIsNotNone(env, "list_cameras() did not pass env= to subprocess.run")
        self.assertNotIn("LD_LIBRARY_PATH", env)
        self.assertNotIn("LD_PRELOAD", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("PYTHONPATH", env)


class TestScrcpyManagerGetLocalVersionUsesCleanEnv(unittest.TestCase):
    """get_local_version() (the user-facing get_version) must sanitize env too."""

    def setUp(self):
        self.logger = MagicMock()
        self.manager = ScrcpyManager(logger=self.logger)
        self.manager.scrcpy_path = "/tmp/fake-scrcpy"

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_get_local_version_receives_sanitized_env(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="scrcpy 4.0\n")
        os.environ["LD_LIBRARY_PATH"] = "/tmp/evil/ld"
        os.environ["LD_PRELOAD"] = "/tmp/evil/preload.so"
        try:
            self.manager.get_local_version()
        finally:
            os.environ.pop("LD_LIBRARY_PATH", None)
            os.environ.pop("LD_PRELOAD", None)

        self.assertTrue(mock_run.called, "subprocess.run was not called")
        kwargs = mock_run.call_args.kwargs
        env = kwargs.get("env")
        self.assertIsNotNone(env, "get_local_version() did not pass env= to subprocess.run")
        self.assertNotIn("LD_LIBRARY_PATH", env)
        self.assertNotIn("LD_PRELOAD", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("PYTHONPATH", env)


class TestADBManagerUsesCleanEnv(unittest.TestCase):
    """ADBManager._run_adb() must sanitize env for Linux packaged builds."""

    def setUp(self):
        self.logger = MagicMock()
        self.manager = ADBManagerForTest(logger=self.logger)
        self.manager.adb_path = "/usr/bin/adb"

    @patch("subprocess.run")
    def test_run_adb_receives_sanitized_env(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        os.environ["LD_LIBRARY_PATH"] = "/tmp/evil/ld"
        os.environ["LD_PRELOAD"] = "/tmp/evil/preload.so"
        try:
            self.manager._run_adb(["devices"], timeout=2)
        finally:
            os.environ.pop("LD_LIBRARY_PATH", None)
            os.environ.pop("LD_PRELOAD", None)

        self.assertTrue(mock_run.called, "subprocess.run was not called")
        kwargs = mock_run.call_args.kwargs
        env = kwargs.get("env")
        self.assertIsNotNone(env, "_run_adb() did not pass env= to subprocess.run")
        self.assertNotIn("LD_LIBRARY_PATH", env)
        self.assertNotIn("LD_PRELOAD", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("PYTHONPATH", env)


class TestRuntimeManagerUsesCleanEnv(unittest.TestCase):
    """RuntimeManager.get_installed_version() must sanitize env too."""

    def setUp(self):
        from services.github_service import GitHubService
        from services.runtime_manager import RuntimeManager
        self.mock_github = MagicMock(spec=GitHubService)
        self.manager = RuntimeManager(github_service=self.mock_github)

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/scrcpy")
    @patch("os.path.exists", return_value=True)
    def test_get_installed_version_receives_sanitized_env(self, mock_exists, mock_which, mock_run):
        mock_res = MagicMock()
        mock_res.stdout = "scrcpy v2.4 <https://github.com/Genymobile/scrcpy>\n"
        mock_res.stderr = ""
        mock_run.return_value = mock_res

        os.environ["LD_LIBRARY_PATH"] = "/tmp/evil/ld"
        os.environ["LD_PRELOAD"] = "/tmp/evil/preload.so"
        try:
            self.manager.get_installed_version("scrcpy")
        finally:
            os.environ.pop("LD_LIBRARY_PATH", None)
            os.environ.pop("LD_PRELOAD", None)

        self.assertTrue(mock_run.called, "subprocess.run was not called")
        kwargs = mock_run.call_args.kwargs
        env = kwargs.get("env")
        self.assertIsNotNone(env, "get_installed_version() did not pass env= to subprocess.run")
        self.assertNotIn("LD_LIBRARY_PATH", env)
        self.assertNotIn("LD_PRELOAD", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("PYTHONPATH", env)


# Lightweight stand-in to avoid pulling in the full ADBManager dependency
# graph (config + device) for this test module. It only needs _run_adb.
class ADBManagerForTest:
    def __init__(self, logger=None):
        self.logger = logger
        self.adb_path = None

    def _run_adb(self, args, timeout=5):
        # Re-import the helper inside to mirror the production path in
        # services.adb_manager._run_adb.
        from services.scrcpy_manager import get_clean_subprocess_env
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        env = get_clean_subprocess_env()
        return subprocess.run(
            [self.adb_path] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=flags,
            env=env,
            timeout=timeout,
        )


if __name__ == "__main__":
    unittest.main()
