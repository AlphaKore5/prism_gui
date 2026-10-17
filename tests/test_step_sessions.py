"""STEP chats: one part and its edited copies, as one thread."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from addons.step import sessions as S  # noqa: E402


def run(path, stamp, action, question, model, modified="", on=None, answer=""):
    stem = os.path.splitext(model)[0]
    return {"path": path, "stamp": stamp, "rec": {
        "step": {"action": action, "question": question,
                 "models": [{"file": model, "path": on or "", "modified": modified,
                             "out_dir": "/x"}]},
        "responses": {f"ask · {stem}": [answer]} if answer else {}}}


class Lineage(unittest.TestCase):
    def test_an_edited_copy_belongs_to_the_part_it_came_from(self):
        self.assertEqual(S.lineage("A.step"), "A")
        self.assertEqual(S.lineage("/x/A - modified 2026-10-15 201121.step"), "A")
        self.assertEqual(S.lineage("PET CORE 02 06.STEP"), "PET CORE 02 06")
        self.assertEqual(S.lineage("PET CORE 02 06 - modified 2026-10-14 144425.step"),
                         "PET CORE 02 06")

    def test_a_part_with_modified_in_its_own_name_still_has_one(self):
        self.assertEqual(S.lineage("modified bracket.step"), "modified bracket")


class Sessions(unittest.TestCase):
    def test_runs_on_a_part_and_its_edit_are_one_chat_oldest_first(self):
        recs = [run("/3", 300, "ask", "again", "A - modified 2026-10-15 201121.step"),
                run("/1", 100, "draft", "", "A.step"),
                run("/2", 200, "edit", "holes", "A.step"),
                run("/9", 50, "draft", "", "B.step")]
        sessions = S.build_sessions(recs)
        self.assertEqual([s["name"] for s in sessions], ["A", "B"])
        self.assertEqual([r["path"] for r in sessions[0]["runs"]], ["/1", "/2", "/3"])
        self.assertEqual(sessions[0]["actions"], ["draft", "edit", "ask"])

    def test_a_chat_id_groups_runs_whatever_file_they_were_on(self):
        a = run("/1", 100, "draft", "", "A.step")
        b = run("/2", 200, "ask", "q", "A.step")
        c = run("/3", 300, "draft", "", "A.step")        # same file, a NEW chat
        a["rec"]["step"]["chat"] = "one"
        b["rec"]["step"]["chat"] = "one"
        c["rec"]["step"]["chat"] = "two"
        sessions = S.build_sessions([a, b, c])
        self.assertEqual([(s["key"], len(s["runs"])) for s in sessions],
                         [("two", 1), ("one", 2)])

    def test_runs_saved_before_chats_had_ids_group_by_part_and_sitting(self):
        hour = 3600
        sessions = S.build_sessions([
            run("/1", 1000, "draft", "", "A.step"),
            run("/2", 1000 + hour, "ask", "q", "A.step"),           # same sitting
            run("/3", 1000 + 30 * hour, "edit", "x", "A.step")])   # next day
        self.assertEqual(sorted(len(s["runs"]) for s in sessions), [1, 2])
        self.assertEqual(len(sessions), 2)

    def test_two_days_of_work_on_one_part_is_not_one_chat(self):
        day = 24 * 3600
        recs = [run(f"/{i}", i * 600, "ask", "q", "PET.step") for i in range(5)]
        recs += [run(f"/b{i}", day + i * 600, "ask", "q", "PET.step") for i in range(3)]
        self.assertEqual([len(s["runs"]) for s in S.build_sessions(recs)], [3, 5])

    def test_records_that_are_not_step_runs_are_ignored(self):
        self.assertEqual(S.build_sessions([{"path": "/1", "stamp": 1,
                                            "rec": {"query": "BOQ"}}]), [])


class Versions(unittest.TestCase):
    def test_the_original_and_the_edited_copy_are_both_offered(self):
        with tempfile.TemporaryDirectory() as d:
            orig = os.path.join(d, "A.step")
            edited = os.path.join(d, "A - modified 2026-10-15 201121.step")
            open(orig, "w").close()
            open(edited, "w").close()
            sess = S.build_sessions([
                run("/1", 100, "draft", "", "A.step", on=orig),
                run("/2", 200, "edit", "holes", "A.step", modified=edited, on=orig)])[0]
            versions = S.versions_of(sess)
        self.assertEqual([(v["label"], v["kind"]) for v in versions],
                         [("A.step", "original"),
                          ("A - modified 2026-10-15 201121.step", "edited")])

    def test_a_file_that_has_gone_is_not_offered(self):
        sess = S.build_sessions([run("/1", 100, "edit", "x", "A.step",
                                     modified="/nowhere/A - modified 1.step",
                                     on="/nowhere/A.step")])[0]
        self.assertEqual(S.versions_of(sess), [])


class TheChat(unittest.TestCase):
    def test_it_reads_in_the_order_things_happened(self):
        sess = S.build_sessions([
            run("/1", 100, "draft", "", "A.step"),
            run("/2", 200, "ask", "lighter?", "A.step", answer="Thinner stock."),
            run("/3", 300, "edit", "bigger holes", "A.step", answer="Do it.",
                modified="/x/A - modified 2026-10-15 201121.step")])[0]
        text = S.chat_text(sess)
        self.assertLess(text.index("Draft"), text.index("lighter?"))
        self.assertLess(text.index("lighter?"), text.index("bigger holes"))
        self.assertIn("Thinner stock.", text)
        self.assertIn("A - modified 2026-10-15 201121.step", text)


class StyledCopiesShowOnTheDraftCard(unittest.TestCase):
    def test_the_styled_copy_in_the_models_folder_is_listed_on_the_draft_turn(self):
        import tempfile
        d = tempfile.mkdtemp()
        styled = os.path.join(d, "A - AI drawing sheet 1.png")
        open(styled, "wb").write(b"x")
        open(os.path.join(d, "A - drawing sheet.png"), "wb").write(b"x")
        rec = {"path": "/r/1.json", "stamp": 1, "rec": {"step": {
            "action": "draft", "chat": "c",
            "models": [{"file": "A.step", "out_dir": d}]}}}
        turns = S.chat_turns(S.build_sessions([rec])[0])
        self.assertEqual(turns[0]["styled"], [styled])

    def test_an_ask_turn_never_lists_styled_copies(self):
        rec = {"path": "/r/1.json", "stamp": 1, "rec": {"step": {
            "action": "ask", "chat": "c",
            "models": [{"file": "A.step", "out_dir": "/nowhere"}]}}}
        self.assertEqual(S.chat_turns(S.build_sessions([rec])[0])[0]["styled"], [])


if __name__ == "__main__":
    unittest.main()
