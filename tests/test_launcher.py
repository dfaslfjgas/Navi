"""Process lifecycle tests for the combined Navi launcher."""

import subprocess
import unittest
from unittest.mock import Mock, patch

import app as launcher


class LauncherTests(unittest.TestCase):
    def test_qt_exit_always_stops_fastapi(self):
        process = Mock()
        with (
            patch.object(launcher, "start_server", return_value=process),
            patch.object(launcher, "gui_main", return_value=7),
            patch.object(launcher, "stop_server") as stop_server,
        ):
            self.assertEqual(launcher.main(), 7)
        stop_server.assert_called_once_with(process)

    def test_qt_error_still_stops_fastapi(self):
        process = Mock()
        with (
            patch.object(launcher, "start_server", return_value=process),
            patch.object(launcher, "gui_main", side_effect=RuntimeError("Qt failed")),
            patch.object(launcher, "stop_server") as stop_server,
        ):
            with self.assertRaisesRegex(RuntimeError, "Qt failed"):
                launcher.main()
        stop_server.assert_called_once_with(process)

    def test_unresponsive_fastapi_is_killed_and_reaped(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("server", 0.01), 0]

        launcher.stop_server(process, timeout=0.01)

        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertEqual(process.wait.call_count, 2)


if __name__ == "__main__":
    unittest.main()
