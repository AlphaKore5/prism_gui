"""The one loader: what it answers, and that every screen that waits uses it."""
from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from widgets.loader import (  # noqa: E402
    Loader, LoadingDialog, Skeleton, busy_button, elapsed_text)

_app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TheProgressBarSurface(unittest.TestCase):
    """Screens swapped a QProgressBar for this and kept their code."""

    def test_no_range_means_unknown_and_a_range_gives_a_fraction(self):
        bar = Loader("stages", ["a", "b"])
        bar.setRange(0, 0)
        self.assertIsNone(bar.fraction)
        bar.setRange(0, 8)
        bar.setValue(2)
        self.assertEqual(bar.fraction, 0.25)
        self.assertEqual(bar.maximum(), 8)

    def test_value_is_clamped_into_the_range(self):
        bar = Loader("ring")
        bar.setRange(0, 4)
        bar.setValue(99)
        self.assertEqual(bar.fraction, 1.0)

    def test_the_clock_starts_when_it_is_shown(self):
        bar = Loader("ring")
        self.assertEqual(bar.elapsed(), 0.0)
        bar.setVisible(True)
        self.assertGreaterEqual(bar.elapsed(), 0.0)
        bar.setVisible(False)

    def test_elapsed_text(self):
        self.assertEqual(elapsed_text(0), "0:00")
        self.assertEqual(elapsed_text(75), "1:15")

    def test_an_unknown_mode_falls_back_to_stages(self):
        self.assertEqual(Loader("sparkle").mode, "stages")

    def test_stop_is_offered_only_when_asked_for(self):
        bar = Loader("stages", stoppable=True)
        got = []
        bar.stop_requested.connect(lambda: got.append(1))
        bar.stop_btn.click()
        self.assertEqual(got, [1])

    def test_every_mode_paints(self):
        for mode in ("stages", "ring", "orb"):
            for compact in (False, True):
                bar = Loader(mode, ["x", "y"], compact=compact)
                bar.resize(300, bar.sizeHint().height())
                bar.set_message("working")
                bar.setVisible(True)
                self.assertFalse(bar.grab().isNull(), (mode, compact))
                bar.setVisible(False)


class TheButtonThatStartedTheWork(unittest.TestCase):
    def test_it_is_disabled_and_says_what_it_is_doing_then_gets_its_label_back(self):
        btn = QPushButton("Send")
        busy_button(btn, True, "Sending")
        self.assertFalse(btn.isEnabled())
        self.assertIn("Sending", btn.text())
        busy_button(btn, False)
        self.assertTrue(btn.isEnabled())
        self.assertEqual(btn.text(), "Send")

    def test_turning_it_off_twice_is_harmless(self):
        btn = QPushButton("Go")
        busy_button(btn, False)
        busy_button(btn, False)
        self.assertEqual(btn.text(), "Go")


class AListThatIsLoading(unittest.TestCase):
    def test_the_skeleton_animates_only_while_shown(self):
        sk = Skeleton(3)
        self.assertFalse(sk._tick.isActive())
        sk.setVisible(True)
        self.assertTrue(sk._tick.isActive())
        sk.setVisible(False)
        self.assertFalse(sk._tick.isActive())


class TheRunHeaderAndTheSmallWaits(unittest.TestCase):
    def test_the_header_bar_has_one_segment_per_step_and_stops_when_idle(self):
        bar = Loader("stages", bare=True)
        bar.setRange(0, 5)
        bar.setValue(2)
        bar.setVisible(True)
        self.assertEqual(bar._segments(), 5)
        self.assertTrue(bar._tick.isActive())
        bar.set_active(False)
        self.assertFalse(bar._tick.isActive())
        self.assertFalse(bar.grab().isNull())
        bar.setVisible(False)

    def test_more_than_twelve_steps_become_one_continuous_bar(self):
        bar = Loader("stages", bare=True)
        bar.setRange(0, 40)
        bar.setValue(10)
        self.assertEqual(bar._segments(), 1)
        self.assertEqual(bar.fraction, 0.25)

    def test_the_loading_dialog_answers_what_the_progress_dialog_did(self):
        box = LoadingDialog("Update", "Checking…", True)
        box.setMaximum(10)
        box.setValue(4)
        box.setLabelText("Downloading 4/10")
        self.assertEqual(box.loader.fraction, 0.4)
        self.assertFalse(box.wasCanceled())
        got = []
        box.canceled.connect(lambda: got.append(1))
        box.cancel_btn.click()
        self.assertTrue(box.wasCanceled())
        self.assertEqual(got, [1])

    def test_an_uncancellable_wait_has_no_cancel_button(self):
        box = LoadingDialog("Reel", "Downloading…", False)
        self.assertTrue(box.cancel_btn.isHidden())


class EveryWaitingScreenUsesIt(unittest.TestCase):
    """One look everywhere: a stock QProgressBar creeping back in is the
    regression this stops."""

    SCREENS = ("addons/step/dialog.py", "addons/reel/dialog.py",
               "addons/motion/dialog.py", "addons/boq/dialog.py",
               "addons/gerber/dialog.py", "addons/inquiry/dialog.py",
               "widgets/output_panel.py")

    def test_no_screen_builds_a_stock_progress_bar(self):
        for rel in self.SCREENS:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
                src = f.read()
            self.assertNotIn("QProgressBar()", src, rel)
            self.assertNotIn("WaveDotsProgress(", src, rel)
            self.assertIn("Loader(", src, rel)


if __name__ == "__main__":
    unittest.main()


class TheMailCheckTellsTheScreenHowFarItIs(unittest.TestCase):
    def test_the_worker_forwards_engine_progress_as_a_signal(self):
        from unittest import mock
        from workers import InboxCheckWorker
        worker = InboxCheckWorker({}, "/nowhere")
        got = []
        worker.progress.connect(lambda *a: got.append(a))
        fake = mock.Mock()
        fake.Paths = lambda root: root

        def check(cfg, paths, **kw):
            kw["progress"]("file", 3, 75)
            return "result"
        fake.check = check
        done = []
        worker.done.connect(done.append)
        with mock.patch("workers.CB.get_mailflow", return_value=fake):
            worker.run()
        self.assertEqual(got, [("file", 3, 75)])
        self.assertEqual(done, ["result"])


class TheTestsCannotTouchTheRealConfig(unittest.TestCase):
    def test_saving_a_config_in_a_test_lands_in_a_temp_file(self):
        import core_bridge  # noqa: F401
        from core import config
        real = os.path.join(os.path.expanduser("~"), ".prism", "config.json")
        self.assertNotEqual(os.path.abspath(config.CONFIG_PATH), os.path.abspath(real))


class SavingASettingIsSeen(unittest.TestCase):
    """2026-10-17: Settings is a modal over the window, so the status-bar
    "Saved." was hidden behind it — a Save looked like nothing happened."""

    def _panel(self):
        from unittest import mock
        from widgets.settings_panel import SettingsPanel
        with mock.patch("widgets.settings_panel.CB.config.save"):
            return SettingsPanel({"api_key": ""}), mock

    def test_a_save_shows_a_toast_inside_the_dialog(self):
        panel, mock = self._panel()
        panel.show()
        with mock.patch("widgets.settings_panel.CB.config.save"):
            panel._after_save("Saved.")
        self.assertTrue(panel._toast.isVisible())
        self.assertIn("Saved.", panel._toast.text())

    def test_a_key_is_checked_with_groq_and_the_answer_is_shown(self):
        panel, mock = self._panel()
        panel.show()
        key = "gsk_" + "x" * 30
        field = mock.MagicMock()
        field.text.return_value = key
        with mock.patch("widgets.settings_panel.CB.config.save"), \
                mock.patch("workers.GroqKeyWorker") as worker:
            panel._save_key(field)
        worker.assert_called_once()
        done = worker.return_value.done.connect.call_args[0][0]
        done("")
        self.assertIn("accepts", panel._toast.text())
        done("Groq rejected this key. Make a new one…")
        self.assertIn("Saved, but groq rejected", panel._toast.text())

    def test_the_default_dashboard_is_plain_white(self):
        from unittest import mock
        import main_window
        with mock.patch.object(main_window.CB.config, "load", return_value={}):
            central = main_window.DashboardCentral()
        self.assertIsNone(central._bg_orig)
