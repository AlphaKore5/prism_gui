"""AnswerDialog (dialogs/answer_dialog.py) — the popup an add-on's plain
question opens into, shown as real markdown instead of a few cramped lines
of plain text. Covers what makes it a real running conversation rather
than a single reply that gets silently overwritten: every turn (the
original question, each answer, each follow-up) stays in the thread, a
follow-up can be read back with whichever agent was actually chosen in
its own "Reply as" row, and a busy state is visible, not just inferred
from disabled buttons.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core_bridge  # noqa: F401,E402  (puts prism_terminal/core on sys.path)

from PySide6.QtWidgets import QApplication  # noqa: E402

from dialogs.answer_dialog import AnswerDialog  # noqa: E402

_app = QApplication.instance() or QApplication([])

MODEL_CHOICES = (
    ("Groq", "Groq (fast, in-house)"),
    ("ChatGPT", "ChatGPT"),
    ("Claude", "Claude"),
)


class TheThreadNeverSilentlyLosesAnEarlierTurn(unittest.TestCase):

    def test_opens_with_the_question_and_the_first_answer(self):
        dlg = AnswerDialog("STEP — Answer", "subtitle", "which material?",
                           "PP for cost.", "Groq")
        self.assertEqual(dlg._thread,
                         [("You asked", "which material?"),
                          ("Groq", "PP for cost.")])
        html = dlg.view.toPlainText()
        self.assertIn("which material?", html)
        self.assertIn("PP for cost.", html)

    def test_set_answer_appends_a_turn_instead_of_replacing(self):
        dlg = AnswerDialog("t", "s", "which material?", "PP for cost.",
                           "Groq")
        dlg.set_answer("Nylon 6 needs drying.", "Groq")
        self.assertEqual(dlg._thread, [
            ("You asked", "which material?"),
            ("Groq", "PP for cost."),
            ("Groq", "Nylon 6 needs drying."),
        ])
        # The earlier turn is still readable, not overwritten.
        text = dlg.view.toPlainText()
        self.assertIn("PP for cost.", text)
        self.assertIn("Nylon 6 needs drying.", text)

    def test_set_answer_records_a_switched_agent_too(self):
        dlg = AnswerDialog("t", "s", "which material?", "PP for cost.",
                           "Claude")
        dlg.set_answer("Switching to ChatGPT's view.", "ChatGPT")
        self.assertEqual(dlg._thread[-1],
                         ("ChatGPT", "Switching to ChatGPT's view."))
        self.assertEqual(dlg._raw, "Switching to ChatGPT's view.")


class BusyIsVisibleNotJustInferred(unittest.TestCase):

    def test_busy_shows_a_label_and_disables_the_followup_controls(self):
        dlg = AnswerDialog("t", "s", "q", "a", "Groq", allow_followup=True)
        self.assertFalse(dlg._busy_label.isVisibleTo(dlg))
        dlg.set_busy(True)
        self.assertTrue(dlg._busy_label.isVisibleTo(dlg))
        self.assertFalse(dlg.followup_btn.isEnabled())
        self.assertFalse(dlg.view.isEnabled())
        dlg.set_busy(False)
        self.assertFalse(dlg._busy_label.isVisibleTo(dlg))
        self.assertTrue(dlg.followup_btn.isEnabled())


class TheFollowUpBoxAndReplyAsPicker(unittest.TestCase):

    def test_no_followup_button_at_all_when_not_allowed(self):
        dlg = AnswerDialog("t", "s", "q", "a", "Groq", allow_followup=False)
        self.assertIsNone(dlg.followup_btn)

    def test_first_click_opens_the_box_second_click_on_empty_does_nothing(self):
        dlg = AnswerDialog("t", "s", "q", "a", "Groq", allow_followup=True)
        seen = []
        dlg.followup_requested.connect(lambda t, a: seen.append((t, a)))
        dlg._on_followup_clicked()
        self.assertTrue(dlg._followup_box.isVisibleTo(dlg))
        self.assertEqual(dlg.followup_btn.text(), "Send")
        dlg._followup_box.setPlainText("   ")   # blank
        dlg._on_followup_clicked()
        self.assertEqual(seen, [])
        self.assertTrue(dlg._followup_box.isVisibleTo(dlg),
                        "an empty send must not close the box")

    def test_sending_appends_the_question_and_emits_text_and_agent(self):
        dlg = AnswerDialog("t", "s", "q", "a", "Groq", allow_followup=True)
        seen = []
        dlg.followup_requested.connect(lambda t, a: seen.append((t, a)))
        dlg._on_followup_clicked()                       # open
        dlg._followup_box.setPlainText("what about Nylon 6?")
        dlg._on_followup_clicked()                        # send
        self.assertEqual(seen, [("what about Nylon 6?", "Groq")])
        self.assertEqual(dlg._thread[-1],
                         ("You followed up", "what about Nylon 6?"))
        self.assertFalse(dlg._followup_box.isVisibleTo(dlg))
        self.assertEqual(dlg.followup_btn.text(), "Follow up")

    def test_no_reply_as_row_without_model_choices(self):
        dlg = AnswerDialog("t", "s", "q", "a", "Groq", allow_followup=True)
        self.assertIsNone(dlg.agent_combo)

    def test_reply_as_defaults_to_whoever_answered_first(self):
        dlg = AnswerDialog("t", "s", "q", "a", "Claude", allow_followup=True,
                           model_choices=MODEL_CHOICES)
        self.assertEqual(dlg.agent_combo.currentData(), "Claude")

    def test_switching_reply_as_changes_what_the_signal_carries(self):
        dlg = AnswerDialog("t", "s", "q", "a", "Claude", allow_followup=True,
                           model_choices=MODEL_CHOICES)
        seen = []
        dlg.followup_requested.connect(lambda t, a: seen.append((t, a)))
        dlg._on_followup_clicked()
        idx = dlg.agent_combo.findData("ChatGPT")
        dlg.agent_combo.setCurrentIndex(idx)
        dlg._followup_box.setPlainText("what about Nylon 6?")
        dlg._on_followup_clicked()
        self.assertEqual(seen, [("what about Nylon 6?", "ChatGPT")])


class Copying(unittest.TestCase):

    def test_copy_copies_the_latest_answer_not_the_whole_thread(self):
        dlg = AnswerDialog("t", "s", "q", "a", "Groq")
        dlg.set_answer("the newer answer", "Groq")
        with mock.patch.object(QApplication, "clipboard") as clip:
            dlg._copy()
            clip.return_value.setText.assert_called_once_with(
                "the newer answer")


if __name__ == "__main__":
    unittest.main()
