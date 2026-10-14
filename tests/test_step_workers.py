"""addons/step/workers.py — the three background workers behind STEP's
Draft/Ask/Edit. Covers the one thing that was silently wrong before: the
file an Edit actually writes.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import core_bridge as CB  # noqa: E402

from addons.step.workers import StepApplyWorker  # noqa: E402


class TheBuiltFileGetsAStampedNameNotTheFlatOne(unittest.TestCase):
    """Round: every Edit wrote "<stem> - modified.step" — the exact same
    literal name on every build, in its own numbered sibling folder, so
    two different requests' results were indistinguishable by name alone,
    especially once moved out of their folder. The actual write must use
    core.stepfile.modified_name() (stamped with when it was built), never
    names()['modified'] (the flat, un-stamped base used only for the
    pre-build "about to write X" message)."""

    def test_apply_plan_is_called_with_the_stamped_path(self):
        fake_sf = mock.MagicMock()
        fake_sf.names.return_value = {
            "xlsx_after": "x.xlsx", "after_dir": "after", "png_after": "x.png"}
        fake_sf.modified_name.return_value = "Assem1 - modified 2026-10-14 063501.step"
        fake_sf.apply_plan.return_value = {"log": []}
        fake_sf.analyse.return_value = {}
        fake_sf.render_sheet.return_value = {}
        fake_sf.review_html.return_value = "/x/review.html"

        with mock.patch.object(CB, "get_stepfile", return_value=fake_sf):
            worker = StepApplyWorker(
                "/x/Assem1.STEP", {"changes": []}, {"file": "Assem1.STEP"},
                "metal", "/x/Assem1 (2)", "enlarge the hole", 0.0)
            worker.run()

        fake_sf.modified_name.assert_called_once_with({"file": "Assem1.STEP"})
        out_path = fake_sf.apply_plan.call_args[0][2]
        self.assertEqual(
            out_path,
            os.path.join("/x/Assem1 (2)",
                         "Assem1 - modified 2026-10-14 063501.step"))
        # names()['modified'] (the flat base) must not be what got written.
        self.assertNotIn("Assem1 - modified.step", out_path)


class AnEngineWithoutModifiedNameStillEdits(unittest.TestCase):
    """1.6.3 was cut against an engine on GitHub that has no
    core.stepfile.modified_name, so every Edit failed at its first line with
    "module 'core.stepfile' has no attribute 'modified_name'". The GUI makes
    the same stamped name itself when the engine cannot."""

    class _OldEngine:
        @staticmethod
        def names(report):
            return {"modified": "Assem1 - modified.step"}

    def test_the_name_is_stamped_and_is_not_the_flat_one(self):
        from addons.step.workers import _modified_name
        got = _modified_name(self._OldEngine, {"file": "Assem1.STEP"})
        self.assertTrue(got.startswith("Assem1 - modified "), got)
        self.assertTrue(got.endswith(".step"), got)
        self.assertNotEqual(got, "Assem1 - modified.step")
        self.assertNotRegex(got, r'[<>:"/\\|?*]')       # legal on Windows too

    def test_two_builds_a_second_apart_get_different_names(self):
        import datetime
        from addons.step import workers
        from addons.step.workers import _modified_name
        with mock.patch.object(workers, "_dt") as dt_mod:
            dt_mod.datetime.now.return_value = datetime.datetime(2026, 10, 14, 6, 35, 1)
            first = _modified_name(self._OldEngine, {})
            dt_mod.datetime.now.return_value = datetime.datetime(2026, 10, 14, 6, 35, 2)
            second = _modified_name(self._OldEngine, {})
        self.assertEqual(first, "Assem1 - modified 2026-10-14 063501.step")
        self.assertNotEqual(first, second)

    def test_the_engines_own_name_wins_when_it_has_one(self):
        from addons.step.workers import _modified_name
        sf = mock.MagicMock()
        sf.modified_name.return_value = "from the engine.step"
        self.assertEqual(_modified_name(sf, {"file": "x.step"}), "from the engine.step")

    def test_an_edit_runs_end_to_end_against_the_old_engine(self):
        sf = mock.MagicMock(spec=["names", "apply_plan", "analyse", "write_xlsx",
                                  "render_sheet", "review_html"])
        sf.names.return_value = {
            "modified": "Assem1 - modified.step", "xlsx_after": "x.xlsx",
            "after_dir": "after", "png_after": "x.png"}
        sf.apply_plan.return_value = {"log": []}
        sf.analyse.return_value = {}
        sf.render_sheet.return_value = {}
        sf.review_html.return_value = "/x/review.html"
        done, failed = [], []
        with mock.patch.object(CB, "get_stepfile", return_value=sf):
            worker = StepApplyWorker(
                "/x/Assem1.STEP", {"changes": []}, {"file": "Assem1.STEP"},
                "metal", "/x/Assem1 (2)", "enlarge the hole", 0.0)
            worker.done.connect(done.append)
            worker.failed.connect(failed.append)
            worker.run()
        self.assertEqual(failed, [])
        self.assertEqual(len(done), 1)
        self.assertRegex(os.path.basename(done[0]["out"]),
                         r"^Assem1 - modified \d{4}-\d\d-\d\d \d{6}\.step$")


if __name__ == "__main__":
    unittest.main()
