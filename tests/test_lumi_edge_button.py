"""Lumi's launcher as an Android-style edge button (14-Oct-2026).

The owner: "Lumi is getting in between a lot, so make it like an accessibility
bar, just like Android has in the bottom-right corner." The old launcher was a
260-285 px dark pill with a standing mascot over it, floating over cards, table
rows and footer buttons. Held here:

  · it is a small round button (sized from the font, 40-46 px) docked to the
    right edge, and never takes more of a content area than its own footprint;
  · its "Ask Lumi" label slides out on hover/focus without the button growing;
  · it drags up and down the edge only, clamped inside the window, snapping
    back to the edge; dragged into the edge it tucks into a slim tab, and a
    click on the tab brings it back;
  · position and tucked state persist in the user's own Prism folder;
  · click, Enter and Space ask for Lumi through the same signal as before, and
    LumiOverlay opens the card beside it rather than on top of it.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt   # noqa: E402
from PySide6.QtGui import QEnterEvent, QKeyEvent, QMouseEvent   # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget             # noqa: E402

import paths                                                    # noqa: E402
import theme                                                    # noqa: E402
from widgets import lumi_card as L                              # noqa: E402

_app = QApplication.instance() or QApplication([])


class _Base(unittest.TestCase):
    """Every test gets its own ~/.prism so persistence is real but never the
    developer's."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patch = mock.patch.object(
            paths, "user_dir",
            lambda *parts: os.path.join(self._tmp.name, ".prism", *parts))
        patch.start()
        self.addCleanup(patch.stop)

    def host(self, w=1078, h=900):
        host = QWidget()
        host.resize(w, h)
        self.addCleanup(host.deleteLater)
        return host

    def button(self, host=None, persist=True):
        host = host or self.host()
        b = L.LumiEdgeButton(host, persist=persist)
        return b

    def prefs_file(self):
        return os.path.join(self._tmp.name, ".prism", L._PREFS_FILE)


def _mouse(kind, pos, button=Qt.LeftButton, buttons=None):
    buttons = Qt.LeftButton if buttons is None else buttons
    if kind == QEvent.MouseButtonRelease:
        buttons = Qt.NoButton
    return QMouseEvent(kind, QPointF(pos), QPointF(pos), button, buttons,
                       Qt.NoModifier)


class SmallAndDockedToTheEdge(_Base):

    def test_it_is_a_small_round_button(self):
        b = self.button()
        self.assertEqual(b.width(), b.height())
        self.assertGreaterEqual(b.width(), theme.LUMI_BUTTON_MIN)
        self.assertLessEqual(b.width(), theme.LUMI_BUTTON_MAX)

    def test_it_sits_against_the_right_edge_above_a_footer_row(self):
        host = self.host()
        b = self.button(host)
        self.assertEqual(b.geometry().right() + 1,
                         host.width() - theme.LUMI_EDGE_GAP)
        self.assertEqual(host.height() - (b.geometry().bottom() + 1),
                         theme.LUMI_REST_FROM_BOTTOM)

    def test_it_never_covers_content_beyond_its_own_footprint(self):
        """A page's content runs to PAGE_PAD from the right edge. The button
        overlaps only a strip of it no wider than the button, no taller than
        the button — at both of the owner's window sizes."""
        for w, h in ((1078, 900), (1536, 1024), (1366, 700)):
            host = self.host(w, h)
            b = self.button(host)
            content = QRect(theme.PAGE_PAD, theme.PAGE_PAD,
                            w - 2 * theme.PAGE_PAD, h - 2 * theme.PAGE_PAD)
            hit = b.geometry().intersected(content)
            self.assertLessEqual(hit.width(),
                                 b.width() + theme.LUMI_EDGE_GAP - theme.PAGE_PAD)
            self.assertLessEqual(hit.height(), b.height())
            # The footer band (a tall button on PAGE_PAD) is clear of it.
            footer = QRect(0, h - theme.PAGE_PAD - theme.BTN_HEIGHT_LG,
                           w, theme.BTN_HEIGHT_LG)
            self.assertFalse(b.geometry().intersects(footer), (w, h))

    def test_hover_shows_the_label_beside_it_and_the_button_does_not_grow(self):
        host = self.host()
        b = self.button(host)
        before = b.geometry()
        b.enterEvent(QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
        label = b.label_widget()
        self.assertFalse(label.isHidden())
        self.assertEqual(label.text(), "Ask Lumi")
        self.assertEqual(b.geometry(), before)
        self.assertLessEqual(label.geometry().right(), b.x())   # to its left
        b.leaveEvent(QEvent(QEvent.Leave))
        self.assertTrue(label.isHidden())

    def test_it_stays_inside_the_window_when_the_window_shrinks(self):
        host = self.host(1536, 1024)
        b = self.button(host)
        b._from_bottom = 900
        b.reposition()
        host.resize(800, 300)
        b.reposition()
        self.assertTrue(host.rect().contains(b.geometry()))
        self.assertEqual(b.geometry().right() + 1, 800 - theme.LUMI_EDGE_GAP)


class Accessible(_Base):

    def test_name_tooltip_and_focus(self):
        b = self.button()
        self.assertEqual(b.accessibleName(), "Ask Lumi")
        self.assertTrue(b.toolTip())
        self.assertEqual(b.focusPolicy(), Qt.StrongFocus)

    def test_click_asks_for_lumi(self):
        host = self.host()
        b = self.button(host)
        seen = []
        b.toggle_requested.connect(lambda: seen.append(1))
        centre = QPoint(b.width() // 2, b.height() // 2)
        b.mousePressEvent(_mouse(QEvent.MouseButtonPress, centre))
        b.mouseReleaseEvent(_mouse(QEvent.MouseButtonRelease, centre))
        self.assertEqual(seen, [1])

    def test_enter_and_space_ask_for_lumi(self):
        b = self.button()
        seen = []
        b.toggle_requested.connect(lambda: seen.append(1))
        for key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            b.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))
        self.assertEqual(len(seen), 3)


class DragAndTuck(_Base):

    def test_drag_moves_it_vertically_only_and_clamps_inside(self):
        host = self.host()
        b = self.button(host)
        x0 = b.x()
        b.drag_to(QPoint(b.x() + 10, b.y() + 10))          # press
        b.drag_to(QPoint(b.x() + 30, b.y() - 300))         # up, a little sideways
        self.assertEqual(b.x(), x0)
        b.drag_to(QPoint(b.x() + 10, -5000))               # far above the window
        self.assertEqual(b.y(), theme.LUMI_EDGE_GAP)
        b.drag_to(QPoint(b.x() + 10, 99999))               # far below it
        self.assertEqual(b.geometry().bottom() + 1,
                         host.height() - theme.LUMI_EDGE_GAP)
        b.end_drag()
        self.assertEqual(b.x(), x0)                        # snapped to the edge
        self.assertFalse(b.is_tucked())

    def test_a_drag_does_not_count_as_a_click(self):
        b = self.button()
        seen = []
        b.toggle_requested.connect(lambda: seen.append(1))
        b.drag_to(QPoint(b.x() + 5, b.y() + 5))
        b.drag_to(QPoint(b.x() + 5, b.y() - 120))
        b.end_drag()
        self.assertEqual(seen, [])

    def test_dragged_into_the_edge_it_tucks_and_a_click_brings_it_back(self):
        host = self.host()
        b = self.button(host)
        seen = []
        b.toggle_requested.connect(lambda: seen.append(1))
        start = QPoint(b.x() + 5, b.y() + 5)
        b.drag_to(start)
        b.drag_to(start + QPoint(b.diameter(), 0))         # pulled right, into the edge
        b.end_drag()
        self.assertTrue(b.is_tucked())
        self.assertEqual(b.width(), theme.LUMI_TAB_W)
        self.assertEqual(b.geometry().right() + 1, host.width())
        b.activate()                                       # a click on the tab
        self.assertFalse(b.is_tucked())
        self.assertEqual(seen, [])                         # brought back, not opened
        b.activate()
        self.assertEqual(seen, [1])

    def test_the_menu_tucks_and_moves_it_to_the_bottom(self):
        b = self.button()
        actions = {a.text(): a for a in b.context_menu().actions()}
        self.assertIn("Tuck away", actions)
        self.assertIn("Move to bottom", actions)
        actions["Tuck away"].trigger()
        self.assertTrue(b.is_tucked())
        actions = {a.text(): a for a in b.context_menu().actions()}
        self.assertIn("Bring Lumi back", actions)
        b._from_bottom = 400
        actions["Move to bottom"].trigger()
        self.assertFalse(b.is_tucked())
        self.assertEqual(b.from_bottom(), theme.LUMI_REST_FROM_BOTTOM)


class RemembersWhereItWasLeft(_Base):

    def test_position_and_tucked_state_survive_a_restart(self):
        host = self.host()
        b = self.button(host)
        b.drag_to(QPoint(b.x() + 5, b.y() + 5))
        b.drag_to(QPoint(b.x() + 5, b.y() - 200))
        b.end_drag()
        b.set_tucked(True)
        saved = b.from_bottom()
        with open(self.prefs_file(), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["from_bottom"], saved)
        self.assertTrue(data["tucked"])

        again = self.button(self.host())
        self.assertTrue(again.is_tucked())
        self.assertEqual(again.from_bottom(), saved)

    def test_a_mangled_file_is_the_default_spot(self):
        os.makedirs(os.path.dirname(self.prefs_file()), exist_ok=True)
        with open(self.prefs_file(), "w", encoding="utf-8") as f:
            f.write('{"from_bottom": "high", "tucked": "yes"')
        b = self.button()
        self.assertFalse(b.is_tucked())
        self.assertEqual(b.from_bottom(), theme.LUMI_REST_FROM_BOTTOM)

    def test_it_writes_only_its_own_file_in_the_user_folder(self):
        b = self.button()
        b.set_tucked(True)
        folder = os.path.join(self._tmp.name, ".prism")
        self.assertEqual(os.listdir(folder), [L._PREFS_FILE])

    def test_offscreen_there_is_no_welcome_pulse_and_no_write(self):
        b = self.button()
        b.welcome_once()
        self.assertFalse(os.path.exists(self.prefs_file()))


class TheOverlayOpensLumiBesideIt(_Base):

    def overlay(self, w=1078, h=900):
        from widgets.support_panel import SupportPanel
        host = self.host(w, h)
        host.show()                     # the card's isVisible() needs a shown host
        self.addCleanup(host.close)
        panel = SupportPanel({})
        self.addCleanup(panel.deleteLater)
        return host, L.LumiOverlay(host, panel)

    def test_a_click_opens_and_a_second_click_closes(self):
        _host, ov = self.overlay()
        b = ov.button
        b.activate()
        self.assertTrue(ov.is_open())
        b.activate()
        self.assertFalse(ov.is_open())

    def test_the_card_never_covers_the_button(self):
        for w, h in ((1078, 900), (1536, 1024)):
            host, ov = self.overlay(w, h)
            ov.open()
            card = ov._card.geometry()
            self.assertFalse(card.intersects(ov.button.geometry()), (w, h))
            self.assertTrue(host.rect().contains(card), (w, h))
            ov.close()

    def test_the_old_pill_is_gone(self):
        self.assertFalse(hasattr(L, "LumiLauncherPill"))


if __name__ == "__main__":
    unittest.main()
