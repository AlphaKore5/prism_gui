"""The licence must not vanish for a moment and send an activated customer to
the activation screen — most often on the first launch after an update.

Reported 2026-10-17: "after every update it asks for the licence key even
though it was added in a previous update". The startup gate fired the renewal
thread (which rewrites license.json) and THEN read the licence; on Windows a
read that lands while the file is replaced or scanned raises PermissionError,
which read_json used to turn into "no licence"."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from licensing import device, store  # noqa: E402


class AReadThatFailsOnceIsRetried(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="prism-lic-")
        self.file = os.path.join(self.dir, "license.json")
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump({"token": "T", "license_id": "L"}, f)

    def test_a_momentary_permission_error_still_finds_the_licence(self):
        real_open = open
        calls = {"n": 0}

        def flaky(path, *a, **k):
            if str(path) == self.file and calls["n"] < 2:
                calls["n"] += 1
                raise PermissionError(13, "being replaced")
            return real_open(path, *a, **k)

        with mock.patch("builtins.open", flaky), mock.patch("time.sleep"):
            data = store.read_json(self.file, {"token": ""})
        self.assertEqual(data["token"], "T")
        self.assertEqual(calls["n"], 2)

    def test_a_truncated_file_that_is_then_whole_is_read_whole(self):
        real_open = open
        state = {"n": 0}

        def half_then_whole(path, *a, **k):
            if str(path) == self.file and state["n"] == 0:
                state["n"] += 1
                import io
                return io.StringIO('{"token": "T", "licen')
            return real_open(path, *a, **k)

        with mock.patch("builtins.open", half_then_whole), mock.patch("time.sleep"):
            data = store.read_json(self.file, {"token": ""})
        self.assertEqual(data["token"], "T")

    def test_a_file_that_really_is_missing_is_still_just_no_licence(self):
        os.remove(self.file)
        self.assertEqual(store.read_json(self.file, {"token": ""})["token"], "")

    def test_a_file_that_stays_unreadable_gives_up_after_three_tries(self):
        real_open = open
        tries = []

        def locked(path, *a, **k):
            if str(path) == self.file:
                tries.append(1)
                raise PermissionError(13, "locked")
            return real_open(path, *a, **k)

        with mock.patch("builtins.open", locked), mock.patch("time.sleep"), \
                mock.patch.object(store, "_log_read_failure"):
            data = store.read_json(self.file, {"token": ""})
        self.assertEqual(data["token"], "")
        self.assertEqual(len(tries), 3)


class TheMacIdSurvivesALeanPath(unittest.TestCase):
    def test_ioreg_is_found_by_its_absolute_path_when_path_has_no_usr_sbin(self):
        out = '  "IOPlatformUUID" = "ABCD-1234"\n'
        calls = []

        def run(argv, **k):
            calls.append(argv[0])
            if argv[0] == "ioreg":
                raise FileNotFoundError("ioreg")
            return mock.Mock(stdout=out)

        with mock.patch("subprocess.run", run):
            self.assertEqual(device._macos_id(), "ABCD-1234")
        self.assertEqual(calls[0], "/usr/sbin/ioreg")

    def test_it_falls_back_to_the_bare_name(self):
        out = '  "IOPlatformUUID" = "ABCD-1234"\n'

        def run(argv, **k):
            if argv[0] == "/usr/sbin/ioreg":
                raise FileNotFoundError(argv[0])
            return mock.Mock(stdout=out)

        with mock.patch("subprocess.run", run):
            self.assertEqual(device._macos_id(), "ABCD-1234")


class TheGateReadsBeforeItRenews(unittest.TestCase):
    def test_state_is_read_before_the_renewal_thread_is_started(self):
        import inspect
        import main
        src = inspect.getsource(main._licence_gate)
        # (the docstring also mentions refresh(); match the call line itself)
        self.assertLess(src.index("\n    state = licensing.state()\n"),
                        src.index("\n    licensing.refresh()\n"))


if __name__ == "__main__":
    unittest.main()
