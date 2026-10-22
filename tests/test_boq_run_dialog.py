"""addons/boq/run_dialog.py's BoqRunDialog, built straight -- not through
a mock. tests/test_boq_dialog.py's fallback-chain tests all stand this
widget up with _FakeRunDialog instead (a real, modal BoqRunDialog.exec()
would hang a test forever, since nothing would ever end it), which means
nothing exercises the real class's construction or state transitions
unless this file does.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication            # noqa: E402

from addons.boq.run_dialog import BoqRunDialog         # noqa: E402

_app = QApplication.instance() or QApplication([])


class BoqRunDialogBuildsAndTransitions(unittest.TestCase):

    def test_constructs_with_the_starting_agent_on_its_card(self):
        dlg = BoqRunDialog("Verifying against the drawing", "recheck", "ChatGPT")
        self.assertEqual(dlg.card.agent, "ChatGPT")
        self.assertEqual(dlg.card.state(), "running")

    def test_every_control_is_enabled_while_running_close_is_not(self):
        dlg = BoqRunDialog("x", "followup", "ChatGPT")
        self.assertTrue(dlg.skip_btn.isEnabled())
        self.assertTrue(dlg.fallback_btn.isEnabled())
        self.assertTrue(dlg.stop_btn.isEnabled())
        self.assertFalse(dlg.close_btn.isEnabled())

    def test_set_agent_reuses_the_one_card_rather_than_adding_another(self):
        dlg = BoqRunDialog("x", "followup", "ChatGPT")
        dlg.set_agent("Claude")
        self.assertEqual(dlg.card.agent, "Claude")
        self.assertEqual(dlg.card.state(), "running")
        # The failover note StageCard.set_agent writes on a real swap --
        # proof the SAME card tracked the handover, not a fresh one.
        self.assertIn("ChatGPT", dlg.card.note.text())
        self.assertIn("Claude", dlg.card.note.text())

    def test_finish_ok_marks_the_card_done_and_unlocks_close_only(self):
        dlg = BoqRunDialog("x", "followup", "ChatGPT")
        dlg.finish_ok(["1  Brick wall  12.00  m"], "https://example.test/chat")
        self.assertEqual(dlg.card.state(), "completed")
        self.assertFalse(dlg.skip_btn.isEnabled())
        self.assertFalse(dlg.fallback_btn.isEnabled())
        self.assertFalse(dlg.stop_btn.isEnabled())
        self.assertTrue(dlg.close_btn.isEnabled())

    def test_finish_error_not_exhausted_leaves_the_dialog_open_for_a_retry(self):
        dlg = BoqRunDialog("x", "followup", "ChatGPT")
        dlg.finish_error("ChatGPT ran out of memory", exhausted=False)
        self.assertEqual(dlg.card.state(), "failed")
        self.assertTrue(dlg.skip_btn.isEnabled())   # still running the chain
        self.assertFalse(dlg.close_btn.isEnabled())

    def test_finish_error_exhausted_locks_the_dialog(self):
        dlg = BoqRunDialog("x", "followup", "ChatGPT")
        dlg.finish_error("Nothing could answer", exhausted=True)
        self.assertFalse(dlg.skip_btn.isEnabled())
        self.assertTrue(dlg.close_btn.isEnabled())

    def test_finish_skipped_and_finish_cancelled_both_lock_the_dialog(self):
        for method, state in (("finish_skipped", "skipped"),
                              ("finish_cancelled", "cancelled")):
            with self.subTest(method=method):
                dlg = BoqRunDialog("x", "followup", "ChatGPT")
                getattr(dlg, method)()
                self.assertEqual(dlg.card.state(), state)
                self.assertTrue(dlg.close_btn.isEnabled())
                self.assertFalse(dlg.stop_btn.isEnabled())

    def test_closing_the_window_mid_run_asks_to_stop_not_silently(self):
        dlg = BoqRunDialog("x", "followup", "ChatGPT")
        seen = []
        dlg.stop_requested.connect(lambda: seen.append(True))
        dlg.close()
        self.assertEqual(seen, [True])

    def test_closing_after_it_finished_does_not_ask_to_stop_again(self):
        dlg = BoqRunDialog("x", "followup", "ChatGPT")
        dlg.finish_ok([], "")
        seen = []
        dlg.stop_requested.connect(lambda: seen.append(True))
        dlg.close()
        self.assertEqual(seen, [])


class RestartReusesTheWindowForTheNextJob(unittest.TestCase):
    """addons/boq/dialog.py now keeps ONE BoqRunDialog for a whole BOQ
    session and calls restart() for the next verify/follow-up instead of
    building a second window -- the owner's own report was "Verify and
    remake" opening a brand new one even right after an ordinary
    follow-up. restart() must undo a prior finish_*() lock and swap in a
    card for the new stage/agent, the same as a fresh construction would,
    since the person watching cannot otherwise tell the two apart."""

    def test_restart_after_finish_ok_reopens_the_controls_and_relocks_close(self):
        dlg = BoqRunDialog("x", "followup", "ChatGPT")
        dlg.finish_ok(["done"], "")
        self.assertTrue(dlg.close_btn.isEnabled())
        dlg.restart("Verifying against the drawing", "recheck", "Claude")
        self.assertTrue(dlg.skip_btn.isEnabled())
        self.assertTrue(dlg.fallback_btn.isEnabled())
        self.assertTrue(dlg.stop_btn.isEnabled())
        self.assertFalse(dlg.close_btn.isEnabled())

    def test_restart_swaps_in_a_fresh_card_for_the_new_stage_and_agent(self):
        dlg = BoqRunDialog("Carrying your follow-up on", "followup", "ChatGPT")
        dlg.finish_ok(["done"], "")
        dlg.restart("Verifying against the drawing", "recheck", "Claude")
        self.assertEqual(dlg.card.agent, "Claude")
        self.assertEqual(dlg.card.state(), "running")
        self.assertEqual(dlg._head.text(), "Verifying against the drawing")

    def test_restart_does_not_carry_over_the_previous_jobs_note(self):
        """A plain follow-up carries no duration note; a recheck right
        after one must show its own 20-minute note, not inherit silence
        (or an older note) from the job before it."""
        dlg = BoqRunDialog("x", "followup", "ChatGPT")
        dlg.restart("Verifying against the drawing", "recheck", "Claude",
                    note="Claude is reading the drawing itself — up to 20 minutes.")
        self.assertIn("20 minutes", dlg.card.note.text())

    def test_restart_can_finish_again_afterwards(self):
        """The reused window must behave exactly like a fresh one for the
        rest of its life -- finish_ok() after a restart() still locks it."""
        dlg = BoqRunDialog("x", "followup", "ChatGPT")
        dlg.finish_ok(["first answer"], "")
        dlg.restart("x", "recheck", "Claude")
        dlg.finish_ok(["second answer"], "")
        self.assertEqual(dlg.card.state(), "completed")
        self.assertTrue(dlg.close_btn.isEnabled())


if __name__ == "__main__":
    unittest.main()
