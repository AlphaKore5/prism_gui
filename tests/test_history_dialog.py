"""History must tolerate records written by older Prism versions."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core_bridge  # noqa: F401,E402
from dialogs.history_dialog import HistoryDialog  # noqa: E402


class ReadingOlderRunRecords(unittest.TestCase):

    def test_a_string_routing_prompt_does_not_crash_history(self):
        """Older records stored routing[stage] as text, not a mapping."""
        renderer = HistoryDialog.__new__(HistoryDialog)
        html = renderer._render({
            "query": "Research EV incentives",
            "routing": {"research": "Research the current EV incentives."},
            "responses": {"research": ["The subsidy changed in 2026."]},
            "links": {},
        }, "run_1.json")
        self.assertIn("Research the current EV incentives.", html)
        self.assertIn("The subsidy changed in 2026.", html)


class AStepConversationReadsAsAnActualBackAndForth(unittest.TestCase):
    """Round: History showed a STEP run's own response key ("ask ·
    PET CORE 02 06") as a generic pipeline stage, dumping the single
    latest saved answer with no "you asked" / "it answered" structure —
    and, separately, visibly duplicated text from how a follow-up
    re-send restates the earlier answer. Fixed by reading the same
    structured conversation file the Answer popup itself writes."""

    def _conv_file(self, thread):
        path = os.path.join(tempfile.mkdtemp(), "conv.json")
        with open(path, "w") as f:
            json.dump(thread, f)
        return path

    def test_renders_each_turn_labelled_not_as_a_raw_dump(self):
        conv = self._conv_file([
            ["You asked", "Which material fits this part best?"],
            ["Groq", "PP for cost, ABS for a balance."],
            ["You followed up", "What about Nylon 6?"],
            ["Groq", "Nylon 6 needs drying before moulding."],
        ])
        renderer = HistoryDialog.__new__(HistoryDialog)
        html = renderer._render({
            "query": "STEP — Ask: Which material fits this part best?",
            "responses": {"ask · PET CORE 02 06": ["Nylon 6 needs drying before moulding."]},
            "links": {}, "step": {"action": "ask", "models": [
                {"file": "PET CORE 02 06.STEP", "out_dir": "/x",
                 "conversation": conv}]},
        }, "run_1.json")
        self.assertIn("Which material fits this part best?", html)
        self.assertIn("PP for cost, ABS for a balance.", html)
        self.assertIn("What about Nylon 6?", html)
        self.assertIn("Nylon 6 needs drying before moulding.", html)
        self.assertIn("You asked", html)
        self.assertIn("Groq", html)

    def test_both_turn_colours_are_solid_not_an_rgba_bgcolor_broke_this(self):
        """bgcolor is an HTML attribute, not CSS — it cannot parse the
        rgba() values the low ACCENT_RAMP steps carry. Using one there
        once rendered as plain black with near-black text on top, not a
        tint. Every bgcolor='...' this method writes must be a real solid
        colour (hex, or at minimum not literally starting with 'rgba')."""
        conv = self._conv_file([
            ["You asked", "q"], ["Claude", "a"],
        ])
        renderer = HistoryDialog.__new__(HistoryDialog)
        html = renderer._render({
            "query": "STEP — Ask: q",
            "responses": {"ask · PET CORE 02 06": ["a"]},
            "links": {}, "step": {"action": "ask", "models": [
                {"file": "PET CORE 02 06.STEP", "out_dir": "/x",
                 "conversation": conv}]},
        }, "run_1.json")
        for m in re.finditer(r"bgcolor='([^']*)'", html):
            self.assertFalse(m.group(1).strip().lower().startswith("rgba"),
                             f"bgcolor got an rgba() value, which HTML "
                             f"cannot render: {m.group(1)!r}")

    def test_does_not_also_show_the_raw_generic_stage_dump(self):
        """The structured conversation replaces the generic one — it must
        not show up twice, once structured and once as a raw block titled
        after the response key itself."""
        conv = self._conv_file([
            ["You asked", "Which material fits this part best?"],
            ["Groq", "PP for cost, ABS for a balance."],
        ])
        renderer = HistoryDialog.__new__(HistoryDialog)
        html = renderer._render({
            "query": "STEP — Ask: Which material fits this part best?",
            "responses": {"ask · PET CORE 02 06": ["PP for cost, ABS for a balance."]},
            "links": {}, "step": {"action": "ask", "models": [
                {"file": "PET CORE 02 06.STEP", "out_dir": "/x",
                 "conversation": conv}]},
        }, "run_1.json")
        self.assertEqual(html.count("PP for cost, ABS for a balance."), 1)

    def test_a_run_saved_before_this_existed_still_shows_its_old_answer(self):
        """No "conversation" key at all (an old saved run) — must fall
        back to the old raw dump rather than silently showing nothing."""
        renderer = HistoryDialog.__new__(HistoryDialog)
        html = renderer._render({
            "query": "STEP — Ask: Which material fits this part best?",
            "responses": {"ask · PET CORE 02 06": ["PP for cost."]},
            "links": {}, "step": {"action": "ask", "models": [
                {"file": "PET CORE 02 06.STEP", "out_dir": "/x"}]},
        }, "run_1.json")
        self.assertIn("PP for cost.", html)

    def test_a_missing_conversation_file_falls_back_too(self):
        renderer = HistoryDialog.__new__(HistoryDialog)
        html = renderer._render({
            "query": "STEP — Ask: Which material fits this part best?",
            "responses": {"ask · PET CORE 02 06": ["PP for cost."]},
            "links": {}, "step": {"action": "ask", "models": [
                {"file": "PET CORE 02 06.STEP", "out_dir": "/x",
                 "conversation": "/nowhere/missing.json"}]},
        }, "run_1.json")
        self.assertIn("PP for cost.", html)


if __name__ == "__main__":
    unittest.main()
