"""Enter moves the task on, as well as the buttons.

"Make a plan" and "Start the work" could only be pressed with the mouse. The
composer now sends on Enter (Shift+Enter breaks the line), and the plan screen
starts on Enter (tests/test_gates.py::EnterMovesTheTaskOn, which needs a real
window). This file pins the two parts that do not.
"""
from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core_bridge  # noqa: F401,E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])

from widgets import controls as C  # noqa: E402
from widgets.input_panel import InputPanel  # noqa: E402


class TheSubmitBox(unittest.TestCase):
    def setUp(self):
        self.box = C.SubmitTextEdit()
        self.sent = []
        self.box.submitted.connect(lambda: self.sent.append(self.box.toPlainText()))

    def test_enter_sends_and_adds_no_line(self):
        self.box.setPlainText("Write a tender reply")
        QTest.keyClick(self.box, Qt.Key_Return)
        QTest.keyClick(self.box, Qt.Key_Enter)                   # the keypad's
        self.assertEqual(self.sent, ["Write a tender reply"] * 2)
        self.assertEqual(self.box.toPlainText(), "Write a tender reply")

    def test_control_enter_sends_too(self):
        self.box.setPlainText("x")
        QTest.keyClick(self.box, Qt.Key_Return, Qt.ControlModifier)
        self.assertEqual(self.sent, ["x"])

    def test_shift_enter_breaks_the_line_and_sends_nothing(self):
        self.box.setPlainText("one")
        cursor = self.box.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.box.setTextCursor(cursor)
        QTest.keyClick(self.box, Qt.Key_Return, Qt.ShiftModifier)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.box.toPlainText(), "one\n")

    def test_a_read_only_recap_does_not_send(self):
        """The plan screen shows the task as a read-only recap; an Enter there
        has to reach the window and start the work, not plan again."""
        self.box.setPlainText("recap")
        self.box.setReadOnly(True)
        QTest.keyClick(self.box, Qt.Key_Return)
        self.assertEqual(self.sent, [])

    def test_the_other_free_text_boxes_still_take_a_new_line(self):
        plain = C.PlainPasteTextEdit()
        QTest.keyClick(plain, Qt.Key_Return)
        self.assertEqual(plain.toPlainText(), "\n")


class TheComposer(unittest.TestCase):
    def setUp(self):
        self.panel = InputPanel()
        self.planned, self.cancelled = [], []
        self.panel.route_clicked.connect(self.planned.append)
        self.panel.cancel_route_clicked.connect(lambda: self.cancelled.append(1))

    def test_enter_makes_the_plan_from_what_was_typed(self):
        self.panel.text.setPlainText("Make a reel about our new press")
        self.assertTrue(self.panel.route_btn.isEnabled())
        QTest.keyClick(self.panel.text, Qt.Key_Return)
        self.assertEqual(self.planned, ["Make a reel about our new press"])

    def test_enter_on_an_empty_box_does_nothing(self):
        QTest.keyClick(self.panel.text, Qt.Key_Return)
        self.assertEqual((self.planned, self.cancelled), ([], []))

    def test_enter_never_cancels_a_plan_in_progress(self):
        self.panel.text.setPlainText("Something")
        self.panel.set_busy(True)               # the button now reads Cancel
        QTest.keyClick(self.panel.text, Qt.Key_Return)
        self.assertEqual((self.planned, self.cancelled), ([], []))

    def test_the_button_tells_you_about_enter_except_while_it_reads_cancel(self):
        self.assertIn("Enter", self.panel.route_btn.toolTip())
        self.panel.set_busy(True)
        self.assertNotIn("Enter", self.panel.route_btn.toolTip())
        self.panel.set_busy(False)
        self.assertIn("Enter", self.panel.route_btn.toolTip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
