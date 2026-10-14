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


if __name__ == "__main__":
    unittest.main()
