"""The Email inquiries pipeline board, its drawer, and Pipeline & wording.

Where a card sits comes from the engine (register.stage_of); these tests
pin that the board puts each stage/sub-state in the right column, folds the
optional steps the way the approved design does, counts its KPI tiles from
the same placement, relabels in the client's words, and that every drawer
button reaches a real handler through InquiryDialog.act_on.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRect, QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

import core_bridge as CB  # noqa: E402
from core import mailflow, register  # noqa: E402
from addons.inquiry import board as BOARD  # noqa: E402
from addons.inquiry import dialog as UI  # noqa: E402
from addons.inquiry import drawer as DRAWER  # noqa: E402
from addons.inquiry import pipeline_setup as SETUP  # noqa: E402

_app = QApplication.instance() or QApplication([])

_REAL_SAVE = CB.config.save


def setUpModule():
    CB.config.save = lambda cfg: None


def tearDownModule():
    CB.config.save = _REAL_SAVE


def cfg_for(folder: str, pipeline: dict | None = None) -> dict:
    inquiry = {"account": {}, "accounts": [], "folder": folder,
               "rate_list": "", "cost_sheet": "", "company": "Acme",
               "signature": "Sales", "terms": {"gst_percent": 18},
               "followup_days": 2, "max_reminders": 3, "local_only": True,
               "auto_minutes": 0,
               "knowledge": {"own_domains": [], "customers": [], "vendors": [],
                             "learned": {}}, "state": {}}
    if pipeline is not None:
        inquiry["pipeline"] = pipeline
    return {"api_key": "", "inquiry": inquiry}


def row(no: int, status: str, **extra) -> dict:
    r = register.blank_row()
    r.update({"Inquiry no": f"INQ/26-27/{no:04d}", "Customer": f"Customer {no}",
              "Email": f"b{no}@example.com", "Product asked": "Pass box",
              "Quantity": "10 nos", "Date received": "10-10-2026",
              "Status": status, "Last contact": "12-10-2026"})
    r.update(extra)
    return r


Q = {"Quotation no": "QTN/26-27/0101", "Quotation date": "11-10-2026",
     "Quotation value": "125000"}

# (row, expected stage, expected sub) with the default pipeline.
CASES = [
    (row(1, "New"), "inquiry", "you"),
    (row(2, "New", Turn="them"), "inquiry", "them"),
    (row(3, "Quoted", **Q), "quoted", ""),
    (row(4, "Following up", **Q, **{"Reminders sent": "3"}), "quoted", ""),
    (row(5, "Negotiating", **Q, **{"Their ask": "110000", "Turn": "you"}),
     "nego", ""),
    (row(6, "Accepted", **Q, **{"PO number": "PO-1"}), "po", "check"),
    (row(7, "Accepted", **Q), "po", "yes"),
    (row(8, "Accepted", **{"No quotation": "yes"}), "po", "nopo"),
    (row(10, "Converted", **Q, **{"PO number": "PO-9", "Order value": "90000"}),
     "won", ""),
    (row(11, "Not converted", **Q, **{"Reason if lost": "Price"}), "lost", ""),
]


def make_dialog(rows, pipeline=None):
    folder = tempfile.mkdtemp()
    register.save([dict(r) for r in rows], mailflow.Paths(folder).register_csv)
    return UI.InquiryDialog(cfg_for(folder, pipeline))


def column_of(dialog, no: str) -> str:
    for stage, col in dialog.board.column_widgets.items():
        for card in col.findChildren(BOARD.BoardCard):
            if card.inquiry_no == no:
                return stage
    return ""


class LooksLikeAPO(unittest.TestCase):
    """Review R1: a row the mail check only suspects is a PO stays in the
    Inquiry column with a "Looks like a PO" pill, and the drawer offers
    "They sent a PO" first; a narrow card's quote bubble never widens it."""

    def test_pill_column_and_drawer_order(self):
        flagged = row(1, "New", **{"No quotation": register.MAYBE})
        dialog = make_dialog([flagged, row(2, "New")])
        dialog.show_view("pipeline")
        self.assertEqual(column_of(dialog, "INQ/26-27/0001"), "inquiry")
        pills = {c.inquiry_no: [p.text() for p in c.findChildren(BOARD.TonePill)]
                 for c in dialog.board.column_widgets["inquiry"]
                 .findChildren(BOARD.BoardCard)}
        self.assertIn("LOOKS LIKE A PO", " ".join(pills["INQ/26-27/0001"]).upper())
        self.assertFalse(any("LIKE" in t.upper() for t in pills["INQ/26-27/0002"]))
        p = BOARD.pipeline({})
        acts = DRAWER.drawer_actions("inquiry", "you", flagged, p)
        self.assertEqual(acts["secondary"][0], "got_po")
        plain = DRAWER.drawer_actions("inquiry", "you", row(2, "New"), p)
        self.assertNotEqual(plain["secondary"][0], "got_po")

    def test_quote_bubble_does_not_set_a_minimum_width(self):
        card = BOARD.BoardCard(row(1, "New"), head="INQ/26-27/0001",
                               pill=("Better rate?", "negotiating"),
                               product="Compression spring", tone="new",
                               said=("Parth", "We are Shreeji Auto Components "
                                              "Pvt Ltd, Rajkot, 5000 nos monthly"))
        self.assertLess(card.minimumSizeHint().width(), 200)


Q1 = dict(Q, **{"Quotation no": "QTN/26-27/0001"})


class Round2(unittest.TestCase):
    """Review round 2 (R5, R6, R7, R9, R10, R11, R12, R14, R15, R16)."""

    def _quoted_folder(self):
        from decimal import Decimal
        quoting = CB.get_quoting()
        folder = tempfile.mkdtemp()
        q = quoting.Quotation(number="QTN/26-27/0001", lines=[
            quoting.QuoteLine("Pass box", Decimal(1), "nos", Decimal(100000), "")],
            terms=quoting.Terms(gst_percent=Decimal(18), freight=Decimal(5000),
                                discount_percent=Decimal(5)))
        quoting.write_csv(q, os.path.join(folder, "QTN-26-27-0001.csv"))
        return folder, q

    def test_r5_the_latest_revision_is_read(self):
        from decimal import Decimal
        folder, q = self._quoted_folder()
        quoting = CB.get_quoting()
        quoting.scale_to_total(q, "110000")
        quoting.write_csv(q, os.path.join(folder, "QTN-26-27-0001-R1.csv"))
        r = row(1, "Quoted", Folder=folder, Revision="1", **Q1)
        self.assertEqual(UI._read_sent_quotation(r).total, Decimal("110000.00"))
        r["Revision"] = ""                         # hand-cleared: disk still wins
        self.assertEqual(UI._read_sent_quotation(r).total, Decimal("110000.00"))

    def test_r4_r6_revision_files_are_staged_exact_and_never_overwrite(self):
        from decimal import Decimal
        folder, _q = self._quoted_folder()
        r = row(1, "Quoted", Folder=folder, **Q1)
        dialog = make_dialog([r])
        staged, total = dialog._write_revision(r, 1, Decimal("110000"))
        self.assertEqual(total, Decimal("110000.00"))
        self.assertTrue(staged)
        final = [dest for _src, dest in staged]
        self.assertFalse(any(os.path.exists(d) for d in final), "written before Send")
        dialog._drop_staged(staged)                # Cancel / failed send
        self.assertFalse(any(os.path.exists(src) for src, _d in staged))
        self.assertEqual([n for n in os.listdir(folder) if n.startswith(".prism-rev")], [])
        staged, total = dialog._write_revision(r, 1, Decimal("110000"))
        open(final[0], "w").write("the copy the customer holds")
        dialog._promote_staged(staged)
        self.assertEqual(open(final[0]).read(), "the copy the customer holds")
        self.assertEqual(UI._read_sent_quotation(
            dict(r, Revision="1")).total, Decimal("110000.00"))

    def test_r7_letters_never_print_a_wrong_figure(self):
        import inquiry_config as IC
        dialog = make_dialog([row(1, "New")])
        for cell, want in (("Rs. 1,25,000", "₹1,25,000"), ("Rs.5000", "₹5,000"),
                           ("1,25,000/-", "₹1,25,000"), ("INR 1,25,000", "₹1,25,000")):
            self.assertEqual(dialog._money(cell), want, cell)
        for cell in ("1e6", "abc", float("nan"), float("inf")):
            self.assertEqual(IC.format_money(cell), "", cell)
        self.assertEqual(dialog._money("1e6"), "1e6")       # as typed, never a guess

    def test_r9_rows_without_or_sharing_a_number_act_alone(self):
        rows = [row(1, "New", **{"Inquiry no": ""}),
                row(2, "New", **{"Inquiry no": ""}),
                row(3, "New", **{"Inquiry no": "INQ/26-27/0007"}),
                row(4, "New", **{"Inquiry no": "INQ/26-27/0007"}),
                row(5, "New")]
        dialog = make_dialog(rows)
        dialog.show_view("pipeline")
        board = dialog.board
        keys = list(board.cards)
        self.assertEqual(len(keys), 5)
        blank = [k for k in keys if k.startswith("#")]
        self.assertEqual(len(blank), 4)
        dialog._open_card(blank[0])
        self.assertTrue(dialog.drawer.isVisible() or dialog.drawer.no == blank[0])
        self.assertIs(dialog.drawer.row(), board.row_for(blank[0]))
        dialog.drawer.close_drawer()
        board.set_select_mode(True)
        board._card_clicked(blank[0])
        board._card_clicked(blank[3])
        picked = board.picked_rows()
        self.assertEqual(len(picked), 2)
        self.assertIs(picked[0], board.row_for(blank[0]))
        with mock.patch.object(type(dialog), "_delete_inquiries") as fake:
            board._delete_picked()
        self.assertEqual(len(fake.call_args[0][0]), 2)

    def test_r10_price_po_uses_the_numbers_in_use_floor(self):
        src = open(os.path.join(os.path.dirname(UI.__file__),
                                "pipeline_actions.py"), encoding="utf-8").read()
        body = src[src.index("    def _price_po(self):"):src.index("    def _chase_po(")]
        self.assertIn("numbers_in_use", body)
        self.assertIn("taken=taken", body)

    def test_an_order_with_no_priceable_line_sends_no_zero_acknowledgement(self):
        """Found live 2026-10-15: a PO whose text names no rate-list code
        priced to zero lines, and the acknowledgement still went out as a
        quotation for 0.00 with a new quotation number."""
        import csv
        folder = tempfile.mkdtemp()
        rates = os.path.join(folder, "rates.csv")
        with open(rates, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([["Code", "Description", "Unit", "Rate"],
                                     ["KJP 3", "SS Locker (8 Comp)", "nos", "18000"]])
        nopo = row(1, "Accepted", **{"No quotation": "yes"})
        nopo["Product asked"] = "something the rate list does not name"
        register.save([nopo], mailflow.Paths(folder).register_csv)
        cfg = cfg_for(folder)
        cfg["inquiry"]["rate_list"] = rates
        dialog = UI.InquiryDialog(cfg)
        dialog.act_on = dialog.act_on
        letters, said = [], []
        dialog._letter = lambda *a, **k: letters.append(a)
        dialog._explain = said.append
        dialog.act_on(dialog._rows()[0], "price_po")
        self.assertEqual(letters, [])
        self.assertTrue(said)
        self.assertEqual(dialog._rows()[0].get("Quotation no", ""), "")

    def test_r11_a_due_proforma_offers_send_first(self):
        p = BOARD.pipeline({"inquiry": {"pipeline": {"steps": {"proforma": True}}}})
        r = row(1, "Accepted", Proforma="to send", **Q, **{"PO number": "PO-1"})
        self.assertEqual(CB.inquiry_stage(r, p), ("po", "proforma"))
        acts = DRAWER.drawer_actions("po", "proforma", r, p)
        self.assertEqual(acts["primary"], "send_proforma")
        sent = dict(r, Proforma="sent")
        self.assertEqual(DRAWER.drawer_actions("po", "proforma", sent, p)["primary"],
                         "advance")
        dialog = make_dialog([r])
        self.assertIn("send_proforma", dialog._row_handlers())

    def test_r12_long_labels_are_capped_and_elided(self):
        import inquiry_config as IC
        long = "Enquiries received from all our dealers and direct customers " * 3
        p = IC.pipeline_of({"inquiry": {"pipeline": {"labels": {"inquiry": long},
                                                     "words": {"quote": long}}}})
        self.assertLessEqual(len(p["labels"]["inquiry"]), IC.LABEL_MAX)
        self.assertLessEqual(len(p["words"]["quote"]), IC.LABEL_MAX)
        col = BOARD.Column("inquiry", 1, long, "sub", 3)
        self.assertLess(col.minimumSizeHint().width(), 300)
        dlg = SETUP.PipelineSetupDialog(cfg_for(tempfile.mkdtemp()))
        self.assertEqual(dlg.labels["inquiry"].maxLength(), IC.LABEL_MAX)

    def test_r14_offered_words_are_copy_and_translated(self):
        import inquiry_config as IC
        sys.path.insert(0, os.path.join(os.path.dirname(CB.__file__), "devtools"))
        import extract_strings
        self.assertTrue({"WORDS", "TAXES"} <= extract_strings.COPY_TABLES)
        with mock.patch("i18n.t", side_effect=lambda s: "«" + s + "»"):
            self.assertEqual(BOARD.word_text({"words": {"quote": "Offer"}}, "quote"),
                             "«Offer»")
            self.assertEqual(BOARD.word_text({"words": {"quote": "Bid"}}, "quote"),
                             "Bid")
        self.assertIn("Offer", IC.WORDS["quote"])

    def test_r15_register_colours_follow_the_palette(self):
        src = open(UI.__file__, encoding="utf-8").read()
        body = src[src.index("class InquiryDialog("):]
        code = "\n".join(l.split("#", 1)[0] for l in body.splitlines())
        self.assertNotIn("STATUS_COLOURS", code)

    def test_r16_a_hand_toggle_takes_the_sidebar_back(self):
        from PySide6.QtCore import QObject, Signal

        class _Bar(QObject):
            collapsed_toggled = Signal(bool)

            def __init__(self):
                super().__init__()
                self._collapsed = False
                self.calls = []

            def toggle_collapsed(self, collapsed=None):
                self._collapsed = bool(collapsed)
                self.calls.append(collapsed)
                self.collapsed_toggled.emit(self._collapsed)

        dialog = make_dialog([r for r, _s, _u in CASES])
        win = _Window(dialog)
        win.sidebar = _Bar()
        win.resize(1078, 900)
        win.show()
        dialog.show_view("pipeline")
        self.assertTrue(win.sidebar._collapsed)          # auto-collapsed
        win.sidebar.toggle_collapsed(False)              # the user: expand
        win.sidebar.toggle_collapsed(True)               # the user: collapse
        calls = len(win.sidebar.calls)
        win.resize(1900, 900)
        dialog._fit_sidebar()
        dialog.on_leave()
        self.assertTrue(win.sidebar._collapsed)
        self.assertEqual(len(win.sidebar.calls), calls)
        win.hide()


class StageToColumn(unittest.TestCase):

    def test_every_sub_state_lands_in_its_column(self):
        placed = BOARD.place([r for r, _s, _u in CASES], BOARD.pipeline({}))
        for r, stage, sub in CASES:
            self.assertIn((r, sub), placed[stage], r["Inquiry no"])

    def test_the_board_draws_each_card_in_that_column(self):
        dialog = make_dialog([r for r, _s, _u in CASES])
        dialog.show_view("pipeline")
        for r, stage, _sub in CASES:
            if stage == "lost":
                self.assertEqual(column_of(dialog, r["Inquiry no"]), "")
            else:
                self.assertEqual(column_of(dialog, r["Inquiry no"]), stage,
                                 r["Inquiry no"])
        self.assertIn("1 lost", dialog.board.lost_label.text())

    def test_proforma_needs_its_step(self):
        r = row(9, "Accepted", **Q, **{"PO number": "PO-2", "Proforma": "sent"})
        on = BOARD.pipeline({"inquiry": {"pipeline": {"steps": {"proforma": True}}}})
        self.assertIn((r, "proforma"), BOARD.place([r], on)["po"])
        self.assertIn((r, ""), BOARD.place([r], BOARD.pipeline({}))["won"])


class OptionalStepsFold(unittest.TestCase):

    def test_negotiation_off_leaves_four_columns_and_folds_into_quoted(self):
        rows = [r for r, _s, _u in CASES]
        dialog = make_dialog(rows, {"steps": {"negotiation": False}})
        dialog.show_view("pipeline")
        self.assertEqual(list(dialog.board.column_widgets),
                         ["inquiry", "quoted", "po", "won"])
        self.assertEqual(column_of(dialog, "INQ/26-27/0005"), "quoted")
        self.assertEqual(len(dialog.board.kpis), 4)

    def test_details_off_puts_their_turn_back_in_yours(self):
        p = BOARD.pipeline({"inquiry": {"pipeline": {"steps": {"details": False}}}})
        r = row(2, "New", Turn="them")
        self.assertIn((r, "you"), BOARD.place([r], p)["inquiry"])


class KpisAndRelabel(unittest.TestCase):

    def test_kpi_counts_equal_column_counts(self):
        dialog = make_dialog([r for r, _s, _u in CASES])
        board = dialog.board
        for stage, col in board.column_widgets.items():
            self.assertEqual(board.kpis[stage].value.text(), col.count.text(),
                             stage)
        k = dict((s, (n, d)) for s, n, d in BOARD.kpis(
            board._placed, BOARD.pipeline(dialog.cfg)))
        self.assertEqual(k["po"][0], 3)
        self.assertIn("2 to check", k["po"][1])       # the nopo + check rows

    def test_the_clients_words_relabel_the_board_and_the_buttons(self):
        rows = [r for r, _s, _u in CASES]
        dialog = make_dialog(rows)
        dialog.show_view("pipeline")
        with mock.patch.object(SETUP.PipelineSetupDialog, "exec",
                               return_value=1), \
             mock.patch.object(SETUP.PipelineSetupDialog, "pipeline",
                               return_value={"labels": {"inquiry": "Enquiry"},
                                             "words": {"quote": "Offer"}}):
            dialog._open_pipeline_setup()
        self.assertIn("Enquiry", dialog.board.column_widgets["inquiry"].title.text())
        self.assertIn("Enquiry", dialog.board.kpis["inquiry"].title.full_text())
        p = BOARD.pipeline(dialog.cfg)
        self.assertEqual(DRAWER.action_text("prepare", p, rows[0]),
                         "Prepare a offer")

    def test_setup_keeps_a_default_label_as_the_default(self):
        dlg = SETUP.PipelineSetupDialog(cfg_for(tempfile.mkdtemp()))
        dlg.labels["won"].setText("Order booked")
        dlg.nego_switch.setChecked(False)
        out = dlg.pipeline()
        self.assertEqual(out["labels"]["inquiry"], "Inquiry")
        self.assertEqual(out["labels"]["won"], "Order booked")
        self.assertFalse(out["steps"]["negotiation"])


class DrawerActions(unittest.TestCase):

    EXPECT = {
        ("inquiry", "you"): "prepare", ("inquiry", "them"): "chase_details",
        ("quoted", ""): "remind", ("nego", ""): "revise",
        ("quoted", "countered"): "revise", ("po", "check"): "read_po",
        ("po", "nopo"): "price_po", ("po", "yes"): "record_po",
        ("po", "proforma"): "advance", ("won", ""): "open_po",
        ("lost", ""): "win_back",
    }

    def test_primary_per_stage_matches_the_design(self):
        p = BOARD.pipeline({})
        for (stage, sub), key in self.EXPECT.items():
            acts = DRAWER.drawer_actions(stage, sub, row(1, "New"), p)
            self.assertEqual(acts["primary"], key, (stage, sub))
        nego = DRAWER.drawer_actions("nego", "", row(1, "New"), p)
        self.assertTrue(nego["pricebox"] and nego["think"])
        self.assertEqual(nego["secondary"],
                         ["hold", "said_yes", "phone", "win_back", "lost"])

    def test_three_reminders_says_call_them(self):
        p = BOARD.pipeline({})
        r = row(4, "Following up", **Q, **{"Reminders sent": "3"})
        acts = DRAWER.drawer_actions("quoted", "", r, p)
        self.assertTrue(acts["warn"])
        self.assertEqual(acts["primary"], "phone")

    def test_every_drawer_key_reaches_a_handler_through_act_on(self):
        dialog = make_dialog([r for r, _s, _u in CASES])
        handlers = dialog._row_handlers()
        p = BOARD.pipeline({})
        keys = set(DRAWER.MORE_KEYS) | {"update"}
        for stage, sub in self.EXPECT:
            a = DRAWER.drawer_actions(stage, sub, row(1, "New"), p, True)
            keys |= {a["primary"], *a["secondary"]}
        self.assertFalse(keys - set(handlers), keys - set(handlers))
        target = dialog._register_rows[0]
        for key in sorted(keys):
            name = handlers[key].__name__
            with mock.patch.object(type(dialog), name) as fake:
                dialog.act_on(target, key)
                fake.assert_called_once()
            self.assertIs(dialog._current_row(), target)
            self.assertEqual(dialog._picked_register_rows(), [target])

    def test_old_buttons_still_click_with_keyword_only_overrides(self):
        dialog = make_dialog([row(1, "New")])
        with mock.patch.object(UI.QMessageBox, "information") as info:
            dialog.po_btn.click()
        info.assert_called_once()

    def test_drawer_opens_on_a_card_and_esc_closes_it(self):
        rows = [r for r, _s, _u in CASES]
        dialog = make_dialog(rows)
        dialog.resize(1100, 800)
        dialog.show()
        dialog.show_view("pipeline")
        dialog._open_card("INQ/26-27/0005")
        self.assertTrue(dialog.drawer.isVisible())
        self.assertEqual(dialog.drawer.actions["primary"], "revise")
        titles = [t[0] for t in dialog.drawer.price_tiles]
        self.assertTrue(any("They ask" in t for t in titles))
        ask = [t for t in dialog.drawer.price_tiles if "They ask" in t[0]][0]
        self.assertIn("12% lower", ask[2])
        # refresh swaps the row dicts; the drawer re-anchors by number
        dialog._refresh_register()
        self.assertTrue(dialog.drawer.isVisible())
        self.assertIs(dialog.drawer.row(), register.find(
            dialog._register_rows, "INQ/26-27/0005"))
        dialog.drawer._esc.activated.emit()
        self.assertFalse(dialog.drawer.isVisible())
        dialog.hide()


class SelectMode(unittest.TestCase):

    def test_bulk_delete_goes_through_the_dialogs_delete(self):
        dialog = make_dialog([r for r, _s, _u in CASES])
        board = dialog.board
        board.set_select_mode(True)
        board._card_clicked("INQ/26-27/0001")
        board._card_clicked("INQ/26-27/0003")
        self.assertIn("2", board.bulk_delete.text())
        with mock.patch.object(type(dialog), "_delete_inquiries") as fake:
            board._delete_picked()
        rows = fake.call_args[0][0]
        self.assertEqual(sorted(r["Inquiry no"] for r in rows),
                         ["INQ/26-27/0001", "INQ/26-27/0003"])


class _FakeSidebar:
    def __init__(self, collapsed=False):
        self._collapsed = collapsed
        self.calls = []

    def toggle_collapsed(self, collapsed=None):
        self._collapsed = bool(collapsed)
        self.calls.append(collapsed)


class _Window(QWidget):
    def __init__(self, dialog, collapsed=False):
        super().__init__()
        self.sidebar = _FakeSidebar(collapsed)
        QVBoxLayout(self).addWidget(dialog)


class NarrowWindow(unittest.TestCase):

    def test_the_sidebar_collapses_when_narrow_and_comes_back(self):
        dialog = make_dialog([r for r, _s, _u in CASES])
        win = _Window(dialog)
        win.resize(1078, 900)
        win.show()
        dialog.show_view("pipeline")
        self.assertTrue(win.sidebar._collapsed)
        win.resize(1900, 900)
        dialog._fit_sidebar()
        self.assertFalse(win.sidebar._collapsed)
        win.resize(1078, 900)
        dialog._fit_sidebar()
        self.assertTrue(win.sidebar._collapsed)
        dialog.on_leave()
        self.assertFalse(win.sidebar._collapsed)
        win.hide()

    def test_a_sidebar_the_user_collapsed_stays_collapsed(self):
        dialog = make_dialog([row(1, "New")])
        win = _Window(dialog, collapsed=True)
        win.resize(1900, 900)
        win.show()
        dialog.show_view("pipeline")
        dialog.on_leave()
        self.assertEqual(win.sidebar.calls, [])
        win.hide()

    def test_no_overlap_at_1078_by_900(self):
        dialog = make_dialog([r for r, _s, _u in CASES])
        # The page beside a collapsed rail (72px) in a 1078px window.
        dialog.resize(1078 - 72, 900)
        dialog.show()
        dialog.show_view("pipeline")
        dialog.layout().activate()
        board = dialog.board
        board.strip.layout().activate()
        cols = list(board.column_widgets.values())
        fm = board.fontMetrics()
        for a, b in zip(cols, cols[1:]):
            self.assertLessEqual(a.geometry().right(), b.geometry().left(),
                                 (a.stage, b.stage))
        for col in cols:
            self.assertGreaterEqual(
                col.width(), int(BOARD.min_column_width(fm) *
                                 (0.8 if col.stage == "won" else 1)) - 1)
        kp = list(board.kpis.values())
        for a, b in zip(kp, kp[1:]):
            ra = QRect(a.mapTo(board, QPoint(0, 0)), a.size())
            rb = QRect(b.mapTo(board, QPoint(0, 0)), b.size())
            self.assertFalse(ra.intersects(rb))
        dialog.hide()


if __name__ == "__main__":
    unittest.main()


class OpeningTheScreen(unittest.TestCase):
    """1.6.2 shipped a screen that crashed on open: main_window passed
    enter() a keyword the screen did not take
    (TypeError: enter() got an unexpected keyword argument 'view')."""

    def test_enter_takes_every_keyword_main_window_passes(self):
        import ast
        import inspect
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "main_window.py")
        tree = ast.parse(open(path, encoding="utf-8").read())
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "enter"
                 and isinstance(n.func.value, ast.Attribute)
                 and n.func.value.attr == "inquiry_work_panel"]
        self.assertTrue(calls, "main_window no longer opens the inquiry screen")
        accepted = set(inspect.signature(UI.InquiryDialog.enter).parameters)
        for call in calls:
            for kw in call.keywords:
                self.assertIn(kw.arg, accepted)

    def test_opening_the_screen_the_way_main_window_does(self):
        dialog = make_dialog([row(1, "New"), row(2, "Quoted", **Q)])
        dialog.enter(tab=0, auto_check=False, view="auto")
        self.assertIsNotNone(dialog.board)
