"""Two layout defects found by walking every screen of the real app at its
default width (1 Oct 2026), pinned here.

  · PageHeader's subtitle did not wrap, so on Inquiry, Email, Gerber, STEP, BOM
    and Leads it was cut mid-word ("...not gue") and the buttons beside it were
    squeezed ("Export shee").
  · FilterChips was a one-line row. AI tools gives it eleven categories, which
    reported a 742 px minimum width, forced the page's scroll content wider than
    its viewport and clipped the right-hand column of cards (horizontal scroll
    is off by design).
"""
from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

import widgets.controls as C  # noqa: E402

_app = QApplication.instance() or QApplication([])


class PageHeaderSubtitle(unittest.TestCase):
    def test_a_long_subtitle_wraps_instead_of_forcing_its_whole_width(self):
        long = ("Find, qualify and reach the right people — Prism drafts, "
                "you send. " * 4)
        header = C.PageHeader("Leads & Outreach", long, [C.button("Export sheets")])
        self.assertTrue(header.subtitle.wordWrap())
        # The minimum width must not be the whole sentence.
        self.assertLess(header.minimumSizeHint().width(), 600)


class FilterChipsFit(unittest.TestCase):
    def test_many_chips_do_not_demand_one_long_row(self):
        names = ["All", "Research", "Leads", "Reasoning", "Writing", "Audio",
                 "Images", "Video", "Apps", "Decks", "Final summary"]
        chips = C.FilterChips([(n.lower(), n) for n in names], "all")
        self.assertLess(chips.minimumSizeHint().width(), 400,
                        "eleven chips must wrap, not set a 700px minimum")

    def test_selection_still_works_after_wrapping(self):
        chips = C.FilterChips([("a", "A"), ("b", "B"), ("c", "C")], "a")
        seen = []
        chips.changed.connect(seen.append)
        chips._buttons["b"].click()
        self.assertEqual(chips.current(), "b")
        self.assertEqual(seen, ["b"])


class RoomForTheLumiLauncher(unittest.TestCase):
    """The floating Ask-Lumi widget (a 56 px pill with the mascot on top) sat on
    top of "Discard" and half of "Start the work", which are pinned to the foot
    of the workbench, and on the last row of scrolling pages (1 Oct 2026), so
    every screen reserved 120 px under its last row for it. On 14 Oct 2026 the
    owner asked for an Android-style edge button instead ("Lumi is getting in
    between a lot"): a ~44 px face docked to the right edge, resting above a
    footer row. The contract is now the other way round — the button stays out
    of the content, and the screens stop reserving room for it."""

    def test_the_button_is_small_and_lives_in_the_right_gutter(self):
        import theme
        self.assertLessEqual(theme.LUMI_BUTTON_MAX, 48)
        # At most this much of a page's content column is ever under it.
        reach = theme.LUMI_BUTTON_MAX + theme.LUMI_EDGE_GAP - theme.PAGE_PAD
        self.assertLessEqual(reach, theme.CARD_PAD + 4)

    def test_it_rests_above_a_footer_row(self):
        """Next, "Start the work" and Discard sit PAGE_PAD (or 32) off the
        bottom and are at most a tall button high."""
        import theme
        self.assertGreaterEqual(theme.LUMI_REST_FROM_BOTTOM,
                                max(theme.PAGE_PAD, 32) + theme.BTN_HEIGHT_LG
                                + theme.SPACE_2)

    def test_pages_no_longer_reserve_room_under_their_last_row(self):
        import theme
        from widgets.panel_base import Page

        class _P(Page):
            TITLE = "t"
            def build(self):
                pass
        page = _P({})
        margins = page._scroll.widget().layout().contentsMargins()
        self.assertEqual(margins.bottom(), theme.PAGE_PAD)

    def test_home_no_longer_reserves_room_either(self):
        """Home built its own scroll column, and once reserved
        LAUNCHER_CLEARANCE under it. Built against a temporary home so the
        panel cannot read the developer's own runs."""
        import tempfile
        from unittest import mock
        import paths
        import theme
        from widgets.home_panel import HomePanel
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(paths, "user_dir", lambda *a, **k: tmp):
            panel = HomePanel({})
            margins = panel._col.contentsMargins()
            self.assertEqual(margins.bottom(), theme.PAGE_PAD)
            self.assertFalse(hasattr(panel, "_lumi"))   # one launcher, the window's
            panel.deleteLater()

    def test_the_setup_wizard_keeps_next_clear_of_the_button(self):
        """The wizard's pinned Back/Next row sat under the old pill, so Next
        (and "Start using Prism") was covered on first run (9 Oct 2026). The
        row now ends below where the button rests, and its pages still
        scroll so a short laptop screen does not clip them."""
        import theme
        from PySide6.QtWidgets import QScrollArea
        from widgets.wizard_panel import WizardPanel
        panel = WizardPanel({})
        root = panel.layout()
        footer = root.itemAt(root.count() - 1).layout()
        bottom = footer.contentsMargins().bottom()
        self.assertEqual(bottom, theme.PAGE_PAD)
        self.assertLessEqual(bottom + panel.next_btn.sizeHint().height(),
                             theme.LUMI_REST_FROM_BOTTOM)
        for i in range(panel.stack.count()):
            self.assertIsInstance(panel.stack.widget(i), QScrollArea)
        panel.deleteLater()


class EmailSetupFieldsAreTallEnough(unittest.TestCase):
    """The Email account dialog clipped the bottom of every field's text
    (22 px fields for 18 px text with 6 px padding): it has no explicit size,
    so it was sized before the stylesheet padding applied. Seen in the real
    window, 1 Oct 2026."""

    def test_each_field_has_a_real_minimum_height(self):
        import theme
        from addons.email.dialog import EmailSetupDialog
        dlg = EmailSetupDialog({"email": {}}, None)
        for edit in (dlg.addr_edit, dlg.pass_edit, dlg.host_edit, dlg.port_edit):
            self.assertGreaterEqual(edit.minimumHeight(), theme.BTN_HEIGHT_MD)
        dlg.reject()


class InquiryTablesShareTheSlack(unittest.TestCase):
    """The to-quote table sized "Qty" to its longest value
    ("5000 nos (monthly, ongoing)") and left Customer cut to "Shreeji A…".
    Seen in the real window, 1 Oct 2026."""

    def test_several_columns_stretch_and_a_long_one_is_capped(self):
        from PySide6.QtWidgets import QHeaderView
        from addons.inquiry.dialog import InquiryDialog
        t = InquiryDialog._make_table(["No", "Customer", "What", "Qty"],
                                      stretch=(1, 2), fit=(0,), fixed={3: 120})
        head = t.horizontalHeader()
        self.assertEqual(head.sectionResizeMode(1), QHeaderView.Stretch)
        self.assertEqual(head.sectionResizeMode(2), QHeaderView.Stretch)
        self.assertEqual(head.sectionResizeMode(0), QHeaderView.ResizeToContents)
        self.assertEqual(head.sectionResizeMode(3), QHeaderView.Interactive)
        self.assertEqual(head.sectionSize(3), 120)

    def test_a_single_stretch_column_still_works(self):
        from PySide6.QtWidgets import QHeaderView
        from addons.inquiry.dialog import InquiryDialog
        t = InquiryDialog._make_table(["a", "b"], stretch=1)
        self.assertEqual(t.horizontalHeader().sectionResizeMode(1), QHeaderView.Stretch)


if __name__ == "__main__":
    unittest.main()
