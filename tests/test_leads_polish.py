"""Leads screen polish — what /polish found in real-window renders (12-Oct-2026).

Rendered through the real MainWindow and style.qss at 1920, 1536 (the owner's
own window) and 1366 wide, the Leads screen had these defects, each held here:

  · the floating Ask-Lumi pill sat on the right end of the bulk bar at every
    size — Find e-mails, More and the primary "Add to sequence" were under it;
    the bar now stops short of the pill (theme.LAUNCHER_REACH) and, when even
    that is too narrow, folds Remove and then "Clear selection" into More
    instead of letting Qt crush the labels to stubs;
  · the header's "?" button was 64x48 beside 34px buttons — the page header's
    own padding rule inflated it;
  · the page picker was 127x36 beside 27x28 previous/next buttons;
  · the Lists and Sessions tabs said "nothing yet" in bare grey text while
    Saved searches and People had a proper empty state;
  · Analytics' fourth stat tile (the only one with a caption) put its label and
    number on different rows from the other three.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt                                      # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow            # noqa: E402

import core_bridge  # noqa: F401,E402  (puts prism_terminal/core on sys.path)
import paths                                                       # noqa: E402
import theme                                                       # noqa: E402
from addons.leads import cockpit as CK                             # noqa: E402
from prospector.models import Dossier, Lead                        # noqa: E402

_app = QApplication.instance() or QApplication([])


def _dos(name, email="", check=""):
    lead = Lead(name=name, title="Owner", company=f"{name} Works", email=email,
                fit_score=70, fit_reason="matches automation")
    lead.extra = {"email_check": check} if check else {}
    return Dossier(lead=lead, verdict="warm", score=70)


def _cockpit(n=4):
    c = CK.LeadsCockpit()
    c.set_dossiers([_dos(f"P{i}", f"p{i}@x.com") for i in range(n)])
    return c


def _tick(c, rows=1):
    for r in range(rows):
        c._table.item(r, 0).setCheckState(Qt.Checked)


class TheBulkBarGivesWayToTheLauncher(unittest.TestCase):

    def setUp(self):
        self.c = _cockpit()
        # Tests never show a window, so "on screen" is the bar not being hidden.
        self.c._bulk.isVisible = lambda: not self.c._bulk.isHidden()
        _tick(self.c)

    def _fit(self, width, inset=0):
        c = self.c
        c._launcher_inset = lambda: inset
        c._bulk_bar_w.setFixedWidth(width)
        c._fit_bulk()

    def test_remove_folds_only_after_everything_else_has(self):
        actions = self.c._bulk_actions()
        remove = self.c._b_remove
        for level in (0, 1, 2, 3, 4):
            self.assertNotIn(remove, CK.LeadsCockpit._fold_set(level, actions), level)
        for level in (5, 6):
            self.assertIn(remove, CK.LeadsCockpit._fold_set(level, actions), level)

    def test_save_and_the_primary_never_fold(self):
        actions = self.c._bulk_actions()
        for level in range(0, 7):
            folded = CK.LeadsCockpit._fold_set(level, actions)
            self.assertNotIn(self.c._b_contact, folded, level)
            self.assertNotIn(self.c._b_seq, folded, level)

    def test_the_narrowest_bar_keeps_save_and_the_primary_and_lists_the_rest(self):
        c = self.c
        self._fit(c._bulk_need(6))
        self.assertFalse(c._b_contact.isHidden())          # Save
        self.assertFalse(c._b_seq.isHidden())              # the primary
        self.assertTrue(c._b_remove.isHidden())
        self.assertTrue(c._bulk_clear.isHidden())
        self.assertFalse(c._b_more.isHidden())
        self.assertIs(c._bulk_folded[0], c._bulk_clear)    # first in More's menu
        self.assertIn(c._b_remove, c._bulk_folded)

    def test_a_bar_with_room_keeps_clear_selection_and_remove_on_it(self):
        c = self.c
        self._fit(c._bulk_need(0))
        self.assertFalse(c._bulk_clear.isHidden())
        self.assertFalse(c._b_remove.isHidden())
        self.assertNotIn(c._bulk_clear, c._bulk_folded)

    def test_clear_selection_in_more_still_clears(self):
        c = self.c
        self._fit(c._bulk_need(6))
        self.assertTrue(c.selected())
        c._bulk_clear.click()                              # what More's menu entry triggers
        self.assertEqual(c.selected(), [])

    def test_the_inset_moves_the_bars_right_edge_in_and_back_out(self):
        c = self.c
        lay = c._bulk_bar_w.layout()
        self._fit(2000, inset=280)
        self.assertEqual(lay.contentsMargins().right(), theme.SPACE_4 + 280)
        self._fit(2000, inset=0)
        self.assertEqual(lay.contentsMargins().right(), theme.SPACE_4)

    def test_the_inset_costs_the_bar_room_and_so_folds_it_sooner(self):
        c = self.c
        width = c._bulk_need(0)                            # exactly enough for everything
        self._fit(width, inset=0)
        self.assertTrue(c._b_more.isHidden())              # nothing folded
        self._fit(width, inset=280)
        self.assertFalse(c._b_more.isHidden())             # the pill took 280px of it

    def test_what_the_pill_covers_is_its_reach_less_the_room_beside_the_bar(self):
        inset = CK.LeadsCockpit._inset_past_launcher
        self.assertEqual(inset(37), theme.LAUNCHER_REACH + theme.SPACE_2 - 37)
        self.assertEqual(inset(10_000), 0)                 # a bar nowhere near the pill

    def test_outside_the_main_window_there_is_no_pill_to_clear(self):
        self.assertEqual(CK.LeadsCockpit()._launcher_inset(), 0)

    def test_in_the_real_window_nothing_on_the_bar_reaches_the_pill(self):
        """A QMainWindow at the owner's laptop size, the cockpit its central
        widget, the bar open at the foot: every visible control ends left of
        the pill's reach, and the labels are not cut to stubs."""
        win = QMainWindow()
        c = _cockpit(8)
        win.setCentralWidget(c)
        win.resize(1366, 700)
        win.show()
        self.addCleanup(win.close)
        _tick(c, 3)
        c._fit_bulk()
        bar = c._bulk_bar_w
        bar.layout().activate()          # the layout pass an event loop would run next
        self.assertGreater(c._launcher_inset(), 0)
        limit = win.width() - theme.LAUNCHER_REACH
        for w in [c._sel_lbl, c._bulk_clear, c._b_more, *c._bulk_actions()]:
            if w.isHidden():
                continue
            right = w.mapTo(win, w.rect().topRight()).x()
            self.assertLessEqual(right, limit, w.text())
            self.assertGreaterEqual(w.width(), w.sizeHint().width(), w.text())
        self.assertGreater(bar.width(), 0)

    def test_the_theme_constants_are_the_pills_real_size(self):
        from widgets.lumi_card import LumiLauncherPill
        pill = LumiLauncherPill()
        self.addCleanup(pill.deleteLater)
        edge = 24                                          # LumiOverlay.reposition's edge
        self.assertEqual(theme.LAUNCHER_REACH, pill.maximumWidth() + edge)
        self.assertEqual(theme.LAUNCHER_BAND, pill.height() - pill._stage_h + edge)


class ThePagerControlsShareOneHeight(unittest.TestCase):

    def test_previous_page_picker_and_next_are_the_same_height(self):
        c = _cockpit()
        heights = {}
        for name in ("_prev_btn", "_page_box", "_next_btn"):
            w = getattr(c, name)
            w.ensurePolished()
            heights[name] = w.sizeHint().height()
        self.assertEqual(len(set(heights.values())), 1, heights)

    def test_the_page_picker_is_as_wide_as_a_page_number_needs(self):
        c = _cockpit()
        self.assertLessEqual(c._page_box.width(), 80)       # it was 127px for a "1"


class TheHeaderHelpButtonMatchesItsSiblings(unittest.TestCase):

    def test_it_is_a_34px_square_under_the_real_stylesheet(self):
        from addons.leads.panel import LeadsPanel
        with open(paths.resource("style.qss"), "r", encoding="utf-8") as f:
            qss = f.read().replace("%ASSETS%", paths.resource("assets").replace(os.sep, "/"))
        panel = LeadsPanel({})
        self.addCleanup(panel.deleteLater)
        panel.setStyleSheet(qss)
        btn = panel.help_btn
        btn.ensurePolished()
        self.assertEqual((btn.minimumWidth(), btn.maximumWidth()), (34, 34))
        self.assertEqual((btn.minimumHeight(), btn.maximumHeight()), (34, 34))


class TheTabsShareOneEmptyState(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sessions = tempfile.TemporaryDirectory()
        self.addCleanup(self.sessions.cleanup)

    def test_lists_shows_the_icon_state_until_a_sheet_exists(self):
        w = CK.LeadsWorkspace(leads_folder=self.tmp.name)
        lists = w._lists
        self.assertFalse(lists._empty.isHidden())
        self.assertTrue(lists._scroll.isHidden())
        with open(os.path.join(self.tmp.name, "Prism leads.csv"), "w") as f:
            f.write("a,b\n1,2\n")
        lists.refresh()
        self.assertTrue(lists._empty.isHidden())
        self.assertFalse(lists._scroll.isHidden())

    def test_sessions_shows_the_icon_state_when_there_are_none(self):
        w = CK.LeadsWorkspace(leads_folder=self.tmp.name, sessions_folder=self.sessions.name)
        sessions = w._sessions
        self.assertFalse(sessions._empty.isHidden())
        self.assertTrue(sessions._scroll.isHidden())

    def test_every_tab_uses_the_same_empty_state_widget(self):
        w = CK.LeadsWorkspace(leads_folder=self.tmp.name, sessions_folder=self.sessions.name)
        for tab in (w._lists, w._sessions, w._saved):
            self.assertEqual(type(tab._empty).__name__, "EmptyState")


class AStatTileKeepsItsRowsWithOrWithoutACaption(unittest.TestCase):

    def test_every_tile_ends_in_a_stretch_so_its_label_and_number_stay_on_top(self):
        for tile in (CK._stat_card("Qualified", "12"),
                     CK._stat_card("Reached to date", "0", "won't be re-contacted")):
            lay = tile.layout()
            self.assertIsNotNone(lay.itemAt(lay.count() - 1).spacerItem())


if __name__ == "__main__":
    unittest.main()
