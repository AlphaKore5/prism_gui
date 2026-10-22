"""HVAC_DRAWING_RULES.md rule 1: a duct, pipe or cable tray is very often
drawn as its two edges (its real width, to scale), not one centreline.

Found 22 Oct 2026 on a real client HVAC test file: Prism's own measurement
said the supply duct was 78.82 m. The real route is 38.80 m (confirmed
independently, by giving an AI the actual drawing — the thing Prism's own
"the drawing never touches an AI" design exists specifically to avoid
needing). Root cause, traced in the raw DXF: the duct was drawn as two
parallel lines 800 mm apart; `core.boq.measure()` summed every line on the
layer, so it counted both edges as if they were two separate ducts.

The drawing here is built with ezdxf in a temp folder; nothing real is read
and nothing is sent anywhere.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core_bridge as CB  # noqa: E402

boq = CB.get_boq()

try:
    import ezdxf
except ImportError:                                   # pragma: no cover
    ezdxf = None


def _dxf(path: str, build):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4          # millimeters, same as the real file
    msp = doc.modelspace()
    build(msp)
    doc.saveas(path)


def _tmp() -> str:
    return os.path.join(tempfile.mkdtemp(prefix="prism-duct-"), "d.dxf")


@unittest.skipUnless(ezdxf, "ezdxf not installed")
class ADoubleLineDuctIsOneRunNotTwo(unittest.TestCase):

    def test_two_parallel_equal_edges_count_as_one_run(self):
        """The simple case: one straight duct run, 4000 mm long, 600 mm
        wide, both edges plus the two end caps that close it visually."""
        path = _tmp()

        def build(msp):
            msp.add_line((0, 0), (4000, 0), dxfattribs={"layer": "M-DUCT"})
            msp.add_line((0, 600), (4000, 600), dxfattribs={"layer": "M-DUCT"})
            msp.add_line((0, 0), (0, 600), dxfattribs={"layer": "M-DUCT"})
            msp.add_line((4000, 0), (4000, 600), dxfattribs={"layer": "M-DUCT"})

        _dxf(path, build)
        q = boq.measure(path, hvac=True)
        # Not 8000 (both edges) and not 9200 (both edges + both caps) —
        # one run's length, the caps excluded as closing geometry.
        self.assertAlmostEqual(q["lengths_by_layer"]["M-DUCT"], 4000.0, delta=1)
        self.assertTrue(any("M-DUCT" in n and "one run" in n for n in q["notes"]))

    def test_the_real_client_drawing_measures_correctly(self):
        """The exact branched supply-duct geometry from the real 22 Oct
        2026 test file (trunk + four branches + two end caps per branch,
        plus the tapering reducer piece at the trunk's far end) —
        reconstructed here so the fix this bug needs is pinned for good,
        without keeping a client's real file in the test suite. Prism's
        own buggy reading was 78,819.8 mm; an AI reading the real drawing
        directly measured 38.80 m."""
        path = _tmp()

        def build(msp):
            L = "M-DUCT-SUPPLY"
            # trunk, two edges 800 apart
            for y in (7400, 6600):
                msp.add_line((4000, y), (7800, y), dxfattribs={"layer": L})
                msp.add_line((8200, y), (12800, y), dxfattribs={"layer": L})
                msp.add_line((13200, y), (15000, y), dxfattribs={"layer": L})
            msp.add_line((15500, 7300), (17800, 7300), dxfattribs={"layer": L})
            msp.add_line((15500, 6700), (17800, 6700), dxfattribs={"layer": L})
            # the tapering reducer at the trunk's far end -- NOT parallel
            # (the two sides converge), so this must stay unpaired
            msp.add_line((15000, 7400), (15500, 7300), dxfattribs={"layer": L})
            msp.add_line((15000, 6600), (15500, 6700), dxfattribs={"layer": L})
            # four branches, two edges 400 apart, plus their end caps
            for x0, x1, y0, y1 in ((7800, 8200, 7400, 11500),
                                   (7800, 8200, 6600, 2500),
                                   (12800, 13200, 7400, 11500),
                                   (12800, 13200, 6600, 2500)):
                msp.add_line((x0, y0), (x0, y1), dxfattribs={"layer": L})
                msp.add_line((x1, y0), (x1, y1), dxfattribs={"layer": L})
                msp.add_line((x0, y1), (x1, y1), dxfattribs={"layer": L})
            # the fifth branch, 400 wider (17800/18200)
            for y0, y1 in ((7300, 11500), (6700, 2500)):
                msp.add_line((17800, y0), (17800, y1), dxfattribs={"layer": L})
                msp.add_line((18200, y0), (18200, y1), dxfattribs={"layer": L})
                msp.add_line((17800, y1), (18200, y1), dxfattribs={"layer": L})

        _dxf(path, build)
        q = boq.measure(path, hvac=True)
        length = q["lengths_by_layer"]["M-DUCT-SUPPLY"]
        # Within a metre of the AI's own independent reading of the real
        # drawing (38.80 m) -- nowhere near the old, buggy 78.82 m, and
        # nowhere near half of it either (the reducer's two sides are
        # correctly left unpaired, each counted at its own full length).
        self.assertAlmostEqual(length, 38320, delta=100)
        self.assertLess(length, 50000)


class ASingleLineRunIsUntouched(unittest.TestCase):
    """The ordinary, far more common case: one centreline, no second edge
    to find -- must measure exactly as it always did."""

    def test_one_line_on_its_own_layer_keeps_its_full_length(self):
        path = _tmp()

        def build(msp):
            msp.add_line((0, 0), (22000, 1000), dxfattribs={"layer": "M-DUCT-RETURN"})

        _dxf(path, build)
        q = boq.measure(path, hvac=True)
        self.assertAlmostEqual(
            q["lengths_by_layer"]["M-DUCT-RETURN"],
            boq._dist((0, 0), (22000, 1000)), delta=0.01)
        self.assertEqual(q["notes"], [])


class TwoSeparatePipesOnSeparateLayersAreNeverMergedIntoOne(unittest.TestCase):
    """A flow pipe and a return pipe are often the same length and run
    close together, parallel, right beside each other -- exactly what a
    duct's two edges look like. The only thing telling them apart is that
    the drawing puts them on two different layers, which is also the
    convention every other part of this module already relies on."""

    def test_same_length_parallel_lines_on_different_layers_both_count_in_full(self):
        path = _tmp()

        def build(msp):
            msp.add_line((-3000, 6400), (1000, 6400),
                        dxfattribs={"layer": "M-PIPE-CHW-S"})
            msp.add_line((-3000, 7600), (1000, 7600),
                        dxfattribs={"layer": "M-PIPE-CHW-R"})

        _dxf(path, build)
        q = boq.measure(path, hvac=True)
        self.assertAlmostEqual(q["lengths_by_layer"]["M-PIPE-CHW-S"], 4000.0, delta=1)
        self.assertAlmostEqual(q["lengths_by_layer"]["M-PIPE-CHW-R"], 4000.0, delta=1)
        self.assertEqual(q["notes"], [])


class ARoomsOppositeWallsAreNeverReadAsOneDuct(unittest.TestCase):
    """Caught live building the real fix: a 24 m x 14 m room's opposite
    walls are a similar length and a similar distance apart too (ratio
    14/24 = 0.58), and very nearly got read as one 24 m "duct" before the
    offset/length threshold was tightened from 0.6 to 0.5. A wall is a
    thin strip only in the sense that it has thickness; it is never close
    to as wide as a room is long, which a genuine duct/pipe/tray always
    is."""

    def test_a_large_rectangular_room_keeps_its_real_perimeter(self):
        path = _tmp()

        def build(msp):
            msp.add_line((0, 0), (24000, 0), dxfattribs={"layer": "A-WALL"})
            msp.add_line((24000, 0), (24000, 14000), dxfattribs={"layer": "A-WALL"})
            msp.add_line((24000, 14000), (0, 14000), dxfattribs={"layer": "A-WALL"})
            msp.add_line((0, 14000), (0, 0), dxfattribs={"layer": "A-WALL"})

        _dxf(path, build)
        q = boq.measure(path, hvac=True)
        self.assertAlmostEqual(q["lengths_by_layer"]["A-WALL"], 76000.0, delta=1)
        self.assertEqual(q["notes"], [])


class TheRuleOnlyAppliesWhenHvacIsAskedFor(unittest.TestCase):
    """The owner's own instruction, 22 Oct 2026: HVAC_DRAWING_RULES.md's
    rules are trade-specific, verified against HVAC drawings specifically
    -- apply them only when the person's own request actually says "HVAC",
    never by default and never by guessing from the drawing's own layer
    names. `measure(..., hvac=False)` (the default) must behave exactly
    as it did before rule 1 existed, double-counted duct and all; only
    `hvac=True` turns the rule on."""

    def _duct_dxf(self) -> str:
        path = _tmp()

        def build(msp):
            msp.add_line((0, 0), (4000, 0), dxfattribs={"layer": "M-DUCT"})
            msp.add_line((0, 600), (4000, 600), dxfattribs={"layer": "M-DUCT"})

        _dxf(path, build)
        return path

    def test_hvac_false_the_default_keeps_the_old_un_collapsed_reading(self):
        q = boq.measure(self._duct_dxf())
        self.assertAlmostEqual(q["lengths_by_layer"]["M-DUCT"], 8000.0, delta=1)
        self.assertEqual(q["notes"], [])

    def test_hvac_true_applies_rule_1(self):
        q = boq.measure(self._duct_dxf(), hvac=True)
        self.assertAlmostEqual(q["lengths_by_layer"]["M-DUCT"], 4000.0, delta=1)
        self.assertTrue(q["notes"])

    # The BoqDialog-level wiring ("hvac" typed in the ask box turns this
    # on, nothing else does) is tested in tests/test_boq_dialog.py::
    # TheHvacFlagComesOnlyFromTheAskBox -- that file already has the
    # QApplication + BoqDialog setup this needs.


if __name__ == "__main__":
    unittest.main()
