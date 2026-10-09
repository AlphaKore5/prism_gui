"""Open login tabs always says what happened, and never freezes the window.

The owner, 09-Oct-2026, on a fresh Windows 10 Pro install: "when i click the
prism's open login tabs.. it doesn't do anything". The button called the
engine on the UI thread: the window froze while Chrome's profile was copied,
and whatever it raised went to the stdout a windowed build does not have.
The likeliest raise is the copy itself — a running Chrome holds
Network\\Cookies open, and shutil.copytree raises after copying the rest.

These tests hold both halves: every screen's button goes through one helper
that opens the tabs on a worker and reports the result or the real error, and
the engine keeps a partly copied profile instead of failing the press.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

import core_bridge as CB                                    # noqa: E402
import workers                                              # noqa: E402
from widgets import login_tabs as LT                        # noqa: E402

_app = QApplication.instance() or QApplication([])

_AGENTS = {"research": "Perplexity", "writing": "ChatGPT"}
_URLS = ["https://www.perplexity.ai/", "https://chatgpt.com/"]


class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in list(self.slots):
            slot(*args)


class _FakeWorker:
    made: list = []

    def __init__(self, urls, parent=None):
        self.urls, self.parent, self.started = list(urls), parent, False
        self.done, self.failed = _Signal(), _Signal()
        _FakeWorker.made.append(self)

    def start(self):
        self.started = True

    def isRunning(self):
        return self.started


class EveryPressIsAnswered(unittest.TestCase):

    def setUp(self):
        _FakeWorker.made = []
        self.parent = QWidget()
        self.addCleanup(self.parent.deleteLater)
        for target, value in ((workers, "LoginTabsWorker"),):
            patcher = mock.patch.object(target, value, _FakeWorker)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(CB, "automation_available", return_value=(True, ""))
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(CB, "login_tab_urls", return_value=list(_URLS))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_tabs_open_on_a_worker_and_the_caller_hears_how_many(self):
        opened = []
        self.assertTrue(LT.open_login_tabs(self.parent, _AGENTS, on_opened=opened.append))
        worker = _FakeWorker.made[0]
        self.assertTrue(worker.started)
        self.assertEqual(worker.urls, _URLS)
        worker.done.emit(2)
        self.assertEqual(opened, [2])

    def test_a_failure_is_said_in_a_box_with_the_real_error(self):
        LT.open_login_tabs(self.parent, _AGENTS)
        with mock.patch.object(QMessageBox, "warning") as warned:
            _FakeWorker.made[0].failed.emit(
                "Error: [('Default\\\\Network\\\\Cookies', 'Permission denied')]")
        self.assertEqual(warned.call_count, 1)
        said = warned.call_args[0][2]
        self.assertIn("couldn't open the login tabs", said)
        self.assertIn("Cookies", said)

    def test_a_second_press_while_the_first_is_opening_starts_nothing(self):
        LT.open_login_tabs(self.parent, _AGENTS)
        self.assertFalse(LT.open_login_tabs(self.parent, _AGENTS))
        self.assertEqual(len(_FakeWorker.made), 1)

    def test_no_tools_picked_says_so(self):
        with mock.patch.object(QMessageBox, "information") as told:
            self.assertFalse(LT.open_login_tabs(self.parent, {}))
        self.assertIn("open Setup first", told.call_args[0][2])
        self.assertEqual(_FakeWorker.made, [])

    def test_tools_with_no_sign_in_page_say_so(self):
        with mock.patch.object(CB, "login_tab_urls", return_value=[]), \
                mock.patch.object(QMessageBox, "information") as told:
            self.assertFalse(LT.open_login_tabs(self.parent, _AGENTS))
        self.assertIn("sign-in page", told.call_args[0][2])
        self.assertEqual(_FakeWorker.made, [])

    def test_missing_automation_says_so(self):
        with mock.patch.object(CB, "automation_available",
                               return_value=(False, "No module named 'selenium'")), \
                mock.patch.object(QMessageBox, "warning") as warned:
            self.assertFalse(LT.open_login_tabs(self.parent, _AGENTS))
        self.assertIn("selenium", warned.call_args[0][2])
        self.assertEqual(_FakeWorker.made, [])


class TheWorkerReportsEitherWay(unittest.TestCase):
    """LoginTabsWorker.run, called inline: no thread, no Chrome."""

    def _run(self, engine):
        worker = workers.LoginTabsWorker(list(_URLS))
        got = {"done": [], "failed": []}
        worker.done.connect(got["done"].append)
        worker.failed.connect(got["failed"].append)
        with mock.patch.object(CB, "get_automation", return_value=engine):
            worker.run()
        return got

    def test_tabs_asked_for_is_done(self):
        engine = mock.Mock()
        got = self._run(engine)
        engine.open_login_tabs.assert_called_once_with(_URLS)
        self.assertEqual(got, {"done": [2], "failed": []})

    def test_whatever_the_engine_raises_comes_back_as_failed(self):
        engine = mock.Mock()
        engine.open_login_tabs.side_effect = PermissionError("Cookies is in use")
        got = self._run(engine)
        self.assertEqual(got["done"], [])
        self.assertEqual(got["failed"], ["PermissionError: Cookies is in use"])


class APartlyCopiedProfileIsKept(unittest.TestCase):
    """seed_profile with a Chrome that holds a file open: everything else is
    copied, the press goes on, and nothing is raised."""

    def test_a_locked_file_does_not_fail_the_copy(self):
        from core import automation as AU
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        real = os.path.join(root, "User Data")
        os.makedirs(os.path.join(real, "Default", "Network"))
        for name in ("Preferences", os.path.join("Network", "Cookies")):
            with open(os.path.join(real, "Default", name), "w") as f:
                f.write("x")
        prism = os.path.join(root, "chrome_profile")
        copytree = shutil.copytree

        def chrome_open(src, dst, *a, ignore=None, **k):
            # What copytree does when a file is locked: copies everything
            # else, then raises shutil.Error listing what it could not copy.
            def skip(folder, names):
                held = {n for n in names if n == "Cookies"}
                return (set(ignore(folder, names)) if ignore else set()) | held
            with mock.patch.object(AU.shutil, "copytree", copytree):   # its own walk
                copytree(src, dst, *a, ignore=skip, **k)
            raise shutil.Error([(os.path.join(src, "Network", "Cookies"),
                                 os.path.join(dst, "Network", "Cookies"),
                                 "[Errno 13] Permission denied")])

        warned = []
        with mock.patch.object(AU, "PROFILE_DIR", prism), \
                mock.patch.object(AU, "user_chrome_dir", return_value=real), \
                mock.patch.object(AU.shutil, "copytree", chrome_open), \
                mock.patch.object(AU.ui, "warn", warned.append):
            self.assertTrue(AU.seed_profile())
        self.assertTrue(os.path.exists(os.path.join(prism, "Default", "Preferences")))
        self.assertFalse(os.path.exists(os.path.join(prism, "Default", "Network", "Cookies")))
        self.assertTrue(any("Chrome had open" in w for w in warned))


if __name__ == "__main__":
    unittest.main()
