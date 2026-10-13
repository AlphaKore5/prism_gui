"""
The Email inquiries pipeline, phase 1: the engine and the settings.

Plan: artifacts/inquiry-pipeline-build-plan-2026-10-13.md. The board reads
every card's place from register.stage_of(), so these tests pin the promises
the board will be built on:

  1. A register from before the pipeline opens unchanged, and saving it only
     appends the new columns — the owner's own columns do not move.
  2. Stage meanings are fixed; optional steps a client switched off fold the
     way the approved design folds them.
  3. A revised quotation keeps its number, and -Rn files never move the
     numbering floor.
  4. A counter-offer's price is read only when it can be read safely.
  5. A PO with no quotation becomes an order to price, not a new inquiry,
     and is priced from the rate list without anything being sent.
  6. Each client's words, steps, currency and tax come from config that may
     be missing or half-written.

Nothing here touches the real ~/.prism or ~/Prism Inquiries: every file is in
a temporary folder, and the mailbox is faked.
"""
from __future__ import annotations

import csv
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from email.message import EmailMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core_bridge  # noqa: E402  (puts prism_terminal/core on sys.path)
import inquiry_config as IC  # noqa: E402
from core import inbox, mailflow, quoting, register, triage  # noqa: E402

TODAY = date(2026, 10, 13)
OLD_HEADER = [c for c in register.COLUMNS if c not in register.PIPELINE_COLUMNS]


def mail(subject="Enquiry", body="Please quote for 5000 compression springs.",
         sender="Mr Patel <purchase@shaktiauto.in>", message_id="<a1@shaktiauto.in>",
         reply_to="", attachments=()):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "sales@acme.co.in"
    msg["Date"] = "Mon, 12 Oct 2026 09:14:00 +0530"
    msg["Message-ID"] = message_id
    if reply_to:
        msg["In-Reply-To"] = reply_to
        msg["References"] = reply_to
    msg.set_content(body)
    for name, data, mime in attachments:
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return inbox.parse_message(msg.as_bytes(), uid=1)


def row(**fields) -> dict:
    out = register.blank_row()
    out.update({"Inquiry no": "INQ/26-27/0001", "Status": register.NEW})
    out.update(fields)
    return out


class _TempDir(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="prism-pipeline-")
        self.addCleanup(shutil.rmtree, self.dir, True)


# ── 1. register columns ──────────────────────────────────────────────────────

class OldRegistersStillWork(_TempDir):

    def _write_old(self, extra=("Salesman",)):
        path = os.path.join(self.dir, register.FILENAME)
        header = OLD_HEADER + list(extra)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerow(["INQ/26-27/0001", "01-10-2026", "10:00", "Acme",
                        "", "a@acme.in", "", "Hinges", "10", "No", "Quoted",
                        "QTN/26-27/0001", "02-10-2026", "1000.00", "1", "",
                        "", "", "", "", "", "", "a note", "<m1>", "Ravi"])
        return path, header

    def test_the_new_columns_are_appended_after_the_old_ones(self):
        self.assertEqual(register.COLUMNS[:len(OLD_HEADER)], OLD_HEADER)
        self.assertEqual(register.PIPELINE_COLUMNS,
                         ["Revision", "Price history", "Their ask", "Turn",
                          "No quotation", "Proforma"])

    def test_an_old_register_loads_unchanged(self):
        path, header = self._write_old()
        rows = register.load(path)
        self.assertEqual(list(rows[0]), header)
        self.assertEqual(rows[0]["Salesman"], "Ravi")
        self.assertEqual(rows[0]["Notes"], "a note")
        self.assertEqual(register.stage_of(rows[0]), ("quoted", ""))

    def test_saving_back_only_appends_the_empty_columns(self):
        path, header = self._write_old()
        rows = register.load(path)
        register.save(rows, path)
        with open(path, encoding="utf-8-sig", newline="") as f:
            written = list(csv.reader(f))
        self.assertEqual(written[0], header + register.PIPELINE_COLUMNS,
                         "the owner's Salesman column moved")
        self.assertEqual(written[1][:len(header)],
                         [rows[0][c] for c in header])
        self.assertEqual(written[1][len(header):], [""] * 6)
        # And it stays put on the next save.
        register.save(register.load(path), path)
        with open(path, encoding="utf-8-sig", newline="") as f:
            self.assertEqual(next(csv.reader(f)), written[0])

    def test_save_merged_keeps_a_row_added_since_with_the_new_columns(self):
        path, _ = self._write_old()
        mine = register.load(path)
        known = register.row_keys(mine)
        theirs = register.load(path)
        theirs.append(row(**{"Inquiry no": "INQ/26-27/0002", "Turn": "them"}))
        register.save(theirs, path)
        mine[0][register.REVISION] = "1"
        register.save_merged(mine, path, known)
        back = register.load(path)
        self.assertEqual([r["Inquiry no"] for r in back],
                         ["INQ/26-27/0001", "INQ/26-27/0002"])
        self.assertEqual(back[0]["Revision"], "1")
        self.assertEqual(back[1]["Turn"], "them")
        self.assertFalse(os.path.exists(path + ".lock"))

    def test_save_changes_applies_only_the_new_column_it_changed(self):
        path, _ = self._write_old()
        rows = register.load(path)
        before = register.snapshot(rows)
        # Meanwhile the owner edits Notes on screen.
        other = register.load(path)
        other[0]["Notes"] = "owner's note"
        register.save(other, path)
        register.note_counter(rows[0], Decimal("900"), TODAY)
        register.save_changes(rows, path, before)
        back = register.load(path)[0]
        self.assertEqual(back["Status"], register.NEGOTIATING)
        self.assertEqual(back["Their ask"], "900.00")
        self.assertEqual(back["Turn"], "you")
        self.assertEqual(back["Notes"], "owner's note")
        self.assertFalse(os.path.exists(path + ".lock"))

    def test_an_imported_csv_still_maps_including_the_new_headers(self):
        path = os.path.join(self.dir, "old-sheet.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Inquiry No.", "Email ID", "Qty", "their ask", "TURN"])
            w.writerow(["INQ/26-27/0042", "b@b.in", "5", "1200", "them"])
        got = register.load(path)[0]
        self.assertEqual(got["Inquiry no"], "INQ/26-27/0042")
        self.assertEqual(got["Email"], "b@b.in")
        self.assertEqual(got["Quantity"], "5")
        self.assertEqual(got["Their ask"], "1200")
        self.assertEqual(got["Turn"], "them")

    def test_a_blank_row_has_every_column(self):
        self.assertTrue(set(register.PIPELINE_COLUMNS) <= set(register.blank_row()))


# ── 2. stage_of ──────────────────────────────────────────────────────────────

OFF = {"steps": {"negotiation": False, "details": False, "proforma": False}}
ON = {"steps": {"negotiation": True, "details": True, "proforma": True}}


class StageOf(unittest.TestCase):

    def test_every_status(self):
        q = {"Quotation no": "QTN/26-27/0001"}
        cases = [
            (row(), ("inquiry", "you")),
            (row(Status=register.QUOTED, **q), ("quoted", "")),
            (row(Status=register.FOLLOWING_UP, **q), ("quoted", "")),
            (row(Status=register.NEGOTIATING, **q), ("nego", "")),
            (row(Status=register.ACCEPTED, **q), ("po", "yes")),
            (row(Status=register.CONVERTED, **q), ("won", "")),
            (row(Status=register.NOT_CONVERTED), ("lost", "")),
        ]
        for r, want in cases:
            self.assertEqual(register.stage_of(r), want, r["Status"])

    def test_inquiry_turn(self):
        self.assertEqual(register.stage_of(row(Turn="them")), ("inquiry", "them"))
        self.assertEqual(register.stage_of(row(Turn="you")), ("inquiry", "you"))
        self.assertEqual(register.stage_of(row(Turn="them"), OFF),
                         ("inquiry", "you"))

    def test_negotiation_switched_off_reads_as_countered(self):
        r = row(Status=register.NEGOTIATING, **{"Quotation no": "Q/26-27/1"})
        self.assertEqual(register.stage_of(r, ON), ("nego", ""))
        self.assertEqual(register.stage_of(r, OFF), ("quoted", "countered"))

    def test_po_sub_states(self):
        acc = dict(Status=register.ACCEPTED)
        q = {"Quotation no": "QTN/26-27/0001"}
        self.assertEqual(register.stage_of(row(**acc, **q)), ("po", "yes"))
        self.assertEqual(register.stage_of(row(**acc, **q, **{"PO number": "P1"})),
                         ("po", "check"))
        self.assertEqual(register.stage_of(row(**acc, **{"No quotation": "yes"})),
                         ("po", "nopo"))
        # Once priced and acknowledged it has a number of its own.
        self.assertEqual(register.stage_of(row(**acc, **q, **{"No quotation": "yes"})),
                         ("po", "yes"))
        proforma = row(**acc, **q, **{"PO number": "P1", "Proforma": "sent"})
        self.assertEqual(register.stage_of(proforma, ON), ("po", "proforma"))
        self.assertEqual(register.stage_of(proforma, OFF), ("won", ""))
        self.assertEqual(register.stage_of(proforma), ("won", ""),
                         "proforma is off by default")

    def test_hand_kept_rows_are_never_dropped(self):
        self.assertEqual(register.stage_of(row(Status="")), ("inquiry", "you"))
        self.assertEqual(register.stage_of(row(Status="On hold",
                                               **{"Quotation no": "Q1"})),
                         ("quoted", ""))
        self.assertEqual(register.stage_of({}), ("inquiry", "you"))

    def test_steps_tolerate_junk(self):
        for junk in (None, {}, {"steps": "x"}, {"steps": {"negotiation": None}}, "x"):
            self.assertTrue(register.step_on(junk, "negotiation"))
            self.assertFalse(register.step_on(junk, "proforma"))
        self.assertFalse(register.step_on({"steps": {"negotiation": "off"}},
                                          "negotiation"))

    def test_core_bridge_exposes_it(self):
        self.assertEqual(core_bridge.inquiry_stage(row(Turn="them")),
                         ("inquiry", "them"))
        self.assertEqual(core_bridge.inquiry_stage(
            row(Status=register.NEGOTIATING),
            IC.pipeline_of({"inquiry": {"pipeline": {"steps": {"negotiation": False}}}})),
            ("quoted", "countered"))


# ── 3. revisions ─────────────────────────────────────────────────────────────

class Revisions(unittest.TestCase):

    def quoted(self):
        r = row()
        register.mark_quoted(r, "QTN/26-27/0101", Decimal("125000"), TODAY)
        r["Reminders sent"] = "2"
        return r

    def test_a_revision_keeps_the_number_and_the_history(self):
        r = self.quoted()
        register.note_counter(r, Decimal("110000"), TODAY)
        register.revise_quotation(r, Decimal("118000"), TODAY)
        self.assertEqual(r["Quotation no"], "QTN/26-27/0101")
        self.assertEqual(r["Revision"], "1")
        self.assertEqual(r["Price history"], "125000.00")
        self.assertEqual(r["Quotation value"], "118000.00")
        self.assertEqual(r["Status"], register.QUOTED)
        self.assertEqual(r["Their ask"], "")
        self.assertEqual(r["Reminders sent"], "0")
        self.assertEqual(register.stage_of(r), ("quoted", ""))
        register.revise_quotation(r, "1,15,000", TODAY)
        self.assertEqual(r["Revision"], "2")
        self.assertEqual(r["Price history"], "125000.00; 118000.00")
        self.assertEqual(register.price_history(r),
                         [Decimal("125000.00"), Decimal("118000.00")])
        self.assertEqual(register.quote_label(r), "QTN/26-27/0101 Rev 2")

    def test_nothing_to_revise_is_an_error_not_an_invention(self):
        with self.assertRaises(ValueError):
            register.revise_quotation(row(), 100)

    def test_history_skips_junk(self):
        self.assertEqual(register.price_history(
            row(**{"Price history": "1000.00; abc;; 900"})),
            [Decimal("1000.00"), Decimal("900")])
        self.assertEqual(register.revision_of(row(Revision="x")), 0)

    def test_file_names(self):
        self.assertEqual(register.quote_file_name("QTN/26-27/0101"),
                         "QTN-26-27-0101.pdf")
        self.assertEqual(register.quote_file_name("QTN/26-27/0101", 1),
                         "QTN-26-27-0101-R1.pdf")
        self.assertEqual(register.quote_file_name("QTN/26-27/0101", 12, ".csv"),
                         "QTN-26-27-0101-R12.csv")


class TheFloorIgnoresRevisions(_TempDir):

    def test_rn_files_are_the_same_number(self):
        paths = mailflow.Paths(self.dir)
        folder = paths.folder_for("INQ/26-27/0007")
        os.makedirs(folder)
        for name in ("QTN-26-27-0101-R1.pdf", "QTN-26-27-0101-R12.pdf"):
            open(os.path.join(folder, name), "wb").close()
        taken = mailflow.numbers_in_use(paths)
        self.assertIn("QTN-26-27-0101-R12.pdf", taken,
                      "a folder holding only the revision lost its floor")
        self.assertEqual(quoting.next_quote_number([], when=TODAY, taken=taken),
                         "QTN/26-27/0102")

    def test_a_revision_typed_into_the_register_is_the_same_number(self):
        rows = [{"Quotation no": "QTN/26-27/0101 Rev 1"},
                {"Quotation no": "QTN/26-27/0100-R3"}]
        self.assertEqual(quoting.next_quote_number(rows, when=TODAY),
                         "QTN/26-27/0102")


# ── 4. counter-offers ────────────────────────────────────────────────────────

class ReadingTheirAsk(unittest.TestCase):

    def test_what_it_reads(self):
        for text in ("Can you do ₹1,10,000?", "Rs. 110000/-", "$110,000 please",
                     "our budget is 1.1 lakh", "110k and we order today",
                     "price 1,10,000", "₹1.1L final", "INR 110000"):
            self.assertEqual(register.read_ask(text, 125000), Decimal("110000.00"),
                             text)

    def test_unsure_is_blank(self):
        for text in ("Please reduce the price.", "best price for 5000 nos",
                     "reduce by ₹10,000", "10% discount please",
                     "between 1 lakh and 1.05 lakh", "our budget is 1,1000",
                     "we need 5 l of it", "QTN/26-27/0101 is high",
                     "₹1,25,000 is our budget", "Call me at 9876543210",
                     "delivery at 380015", "upto 75000 per kg",
                     "Best rate for 100k units?", "at 2026 rates",
                     "can you do 1,10,000"):
            self.assertIsNone(register.read_ask(text, 125000), text)
        self.assertIsNone(register.read_ask("best price please. Call me at 9876543210"),
                          "phone with no quoted total is not an ask")

    def test_our_own_price_quoted_back_is_not_their_ask(self):
        text = "Your ₹1,25,000 is high, we can do ₹1,10,000"
        self.assertEqual(register.read_ask(text, "125000.00"), Decimal("110000.00"))
        self.assertIsNone(register.read_ask(text), "without our price, two figures is unsure")

    def test_hold_the_price_is_their_turn(self):
        r = row(Status=register.NEGOTIATING, Turn="you")
        register.hold_price(r, TODAY)
        self.assertEqual(r["Turn"], "them")
        self.assertEqual(r["Status"], register.NEGOTIATING)

    def test_applying_a_negotiating_reply_by_hand_is_your_turn(self):
        r = row(Status=register.QUOTED, Turn="them", **{"Their ask": "900.00"})
        register.mark_reply(r, "negotiating", TODAY)
        self.assertEqual((r["Status"], r["Turn"], r["Their ask"]),
                         (register.NEGOTIATING, "you", "900.00"))
        register.mark_reply(r, "negotiating", TODAY, ask=Decimal("850"))
        self.assertEqual(r["Their ask"], "850.00")


class _Loop(_TempDir):
    """mailflow.check() against a faked mailbox, as test_mailflow does."""

    def setUp(self):
        super().setUp()
        self.paths = mailflow.Paths(self.dir)
        self.cfg = {"api_key": "", "inbox": {"address": "sales@acme.co.in",
                                             "password": "p", "host": "mail.acme.co.in"}}
        self.known = triage.Knowledge(customers={"shaktiauto.in"})

    def run_check(self, messages, category=None):
        def fake_fetch(cfg, state, **_kw):
            return messages, inbox.State(1, 99), ""

        def fake_classify(msgs, api_key, **_kw):
            return [triage.Verdict(category=category, source="rule") for _ in msgs]

        real_fetch, real_classify = inbox.fetch_new, triage.classify
        inbox.fetch_new = fake_fetch
        if category:
            triage.classify = fake_classify
        try:
            return mailflow.check(self.cfg, self.paths, local_only=True,
                                  knowledge=self.known, today=TODAY)
        finally:
            inbox.fetch_new, triage.classify = real_fetch, real_classify

    def rows(self):
        return register.load(self.paths.register_csv)

    def quote_first(self, value="125000"):
        self.run_check([mail()])
        rows = self.rows()
        register.mark_quoted(rows[0], "QTN/26-27/0101", Decimal(value), TODAY)
        register.save(rows, self.paths.register_csv)

    def reply(self, body, n=2):
        return mail(subject="Re: Enquiry", body=body,
                    message_id=f"<b{n}@shaktiauto.in>", reply_to="<a1@shaktiauto.in>")


class CounterOffersFromTheMailCheck(_Loop):

    def test_a_better_rate_reply_moves_it_to_negotiation_with_their_ask(self):
        self.quote_first()
        result = self.run_check([self.reply(
            "Your rate is too high. Can you do Rs. 1,10,000?")])
        self.assertEqual(result.replies[0].intent, mailflow.NEGOTIATING)
        r = self.rows()[0]
        self.assertEqual(r["Status"], register.NEGOTIATING)
        self.assertEqual(r["Turn"], "you")
        self.assertEqual(r["Their ask"], "110000.00")
        self.assertEqual(register.stage_of(r), ("nego", ""))

    def test_an_unsure_amount_is_left_blank(self):
        self.quote_first()
        self.run_check([self.reply("Your rate is too high, please revise the rate.")])
        r = self.rows()[0]
        self.assertEqual((r["Status"], r["Turn"], r["Their ask"]),
                         (register.NEGOTIATING, "you", ""))

    def test_better_rate_on_an_unquoted_inquiry_stays_an_inquiry(self):
        self.run_check([mail()])
        self.run_check([self.reply("Please send your best price.")])
        self.assertEqual(self.rows()[0]["Status"], register.NEW)

    def test_an_answer_to_our_question_is_your_turn_again(self):
        self.run_check([mail()])
        rows = self.rows()
        register.mark_asked_details(rows[0], TODAY)
        register.save(rows, self.paths.register_csv)
        self.assertEqual(register.stage_of(self.rows()[0]), ("inquiry", "them"))
        self.run_check([self.reply("Grade SS 304, 2 mm wire, 25 OD.")])
        self.assertEqual(register.stage_of(self.rows()[0]), ("inquiry", "you"))


# ── 5. a PO with no quotation ────────────────────────────────────────────────

PO_PDF = [("PO-0112.pdf", b"%PDF-1.4", "application/pdf")]


class POWithoutAQuotation(_Loop):

    def test_a_new_correspondents_order_is_an_order_to_price(self):
        result = self.run_check([mail(subject="Purchase order",
                                      body="PO No. SP/0112 attached, please dispatch.",
                                      attachments=PO_PDF)], triage.ORDER)
        self.assertEqual(len(result.orders), 1)
        r = self.rows()[0]
        self.assertEqual(r["Status"], register.ACCEPTED)
        self.assertEqual(r["No quotation"], "yes")
        self.assertEqual(r["PO number"], "SP/0112")
        self.assertEqual(register.stage_of(r), ("po", "nopo"))

    def test_an_order_on_an_unquoted_inquiry_is_nopo(self):
        self.run_check([mail()])
        po = mail(subject="Re: Enquiry", body="Our PO No. SP/0112 is attached.",
                  message_id="<b3@shaktiauto.in>", reply_to="<a1@shaktiauto.in>",
                  attachments=PO_PDF)
        self.run_check([po], triage.ORDER)
        self.assertEqual(register.stage_of(self.rows()[0]), ("po", "nopo"))

    def test_an_order_on_a_quoted_inquiry_is_left_for_the_owner(self):
        self.quote_first()
        po = mail(subject="Re: Enquiry", body="Our PO is attached.",
                  message_id="<b3@shaktiauto.in>", reply_to="<a1@shaktiauto.in>",
                  attachments=PO_PDF)
        self.run_check([po], triage.ORDER)
        r = self.rows()[0]
        self.assertEqual(r["Status"], register.QUOTED)
        self.assertEqual(r["No quotation"], "")

    def test_the_helper_keeps_a_typed_po_number(self):
        r = row(**{"PO number": "TYPED"})
        register.mark_po_without_quote(r, "", TODAY)
        self.assertEqual(r["PO number"], "TYPED")
        register.mark_po_without_quote(r, "SP/0112", TODAY)
        self.assertEqual((r["PO number"], r["PO date"]), ("SP/0112", "13-10-2026"))


RATES = [
    quoting.RateItem(code="KJP-8", description="SS locker 8 compartments",
                     rate=Decimal("8500")),
    quoting.RateItem(code="KJP-6", description="SS locker 6 compartments",
                     rate=Decimal("7000")),
    quoting.RateItem(code="TR-3", description="Mobile trolley 3 shelf",
                     rate=Decimal("6200"),
                     slabs=[(Decimal("10"), Decimal("6000"))]),
]


class PricingFromTheRateList(_TempDir):

    def test_codes_are_priced_with_tax(self):
        p = quoting.price_order("Please supply KJP-8 x 10 nos", RATES)
        self.assertEqual([(l.description, l.quantity, l.rate) for l in p.lines],
                         [("SS locker 8 compartments", Decimal("10"), Decimal("8500"))])
        self.assertEqual((p.subtotal, p.tax, p.total),
                         (Decimal("85000.00"), Decimal("15300.00"), Decimal("100300.00")))
        self.assertEqual(p.unsure, [])

    def test_words_and_slabs_and_another_tax(self):
        p = quoting.price_order("SS locker 8 compartments - 2 nos\n"
                                "Mobile trolley 3 shelf 10 nos", RATES, tax_percent=5)
        self.assertEqual([l.amount for l in p.lines],
                         [Decimal("17000.00"), Decimal("60000.00")])
        self.assertEqual(p.total, Decimal("80850.00"))

    def test_quantity_from_the_register(self):
        p = quoting.price_order("SS locker 8 compartments", RATES, quantity="10 nos")
        self.assertEqual(p.total, Decimal("100300.00"))

    def test_what_it_cannot_price_is_left_for_a_person(self):
        p = quoting.price_order("Something odd 4 nos", RATES)
        self.assertEqual((p.lines, p.unsure), ([], ["Something odd 4 nos"]))
        p = quoting.price_order("SS locker", RATES, quantity="4")
        self.assertEqual(p.lines, [], "6 and 8 compartments are both 'SS locker'")
        self.assertEqual(p.unsure, ["SS locker"])

    def test_through_core_bridge_from_a_rate_file(self):
        path = os.path.join(self.dir, "rates.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Code", "Description", "Unit", "Rate"])
            w.writerow(["KJP-8", "SS locker 8 compartments", "nos", "8500"])
        p = core_bridge.price_order_from_rate_list("KJP-8 x 10 nos", path,
                                                   tax_percent=18)
        self.assertEqual(p.total, Decimal("100300.00"))
        with self.assertRaises(quoting.RateFileError):
            core_bridge.price_order_from_rate_list("x", os.path.join(self.dir, "no.csv"))


# ── 6. proforma ──────────────────────────────────────────────────────────────

class Proforma(unittest.TestCase):

    def accepted(self):
        return row(Status=register.ACCEPTED, **{"Quotation no": "QTN/26-27/0101",
                                                "Quotation value": "100.00",
                                                "PO number": "P1", "PO date": "01-10-2026"})

    def test_off_means_no_change(self):
        r = self.accepted()
        before = dict(r)
        self.assertFalse(register.mark_proforma_sent(r, None, TODAY))
        self.assertFalse(register.mark_advance_received(r, OFF, None, TODAY))
        self.assertEqual(r, before)

    def test_on_sent_then_paid(self):
        r = self.accepted()
        self.assertTrue(register.mark_proforma_sent(r, ON, TODAY))
        self.assertEqual(register.stage_of(r, ON), ("po", "proforma"))
        self.assertTrue(register.mark_advance_received(r, ON, None, TODAY))
        self.assertEqual((r["Status"], r["Result"], r["Proforma"]),
                         (register.CONVERTED, register.CONVERTED, "paid"))
        self.assertEqual((r["PO number"], r["PO date"], r["Order value"]),
                         ("P1", "01-10-2026", "100.00"))
        self.assertEqual(register.stage_of(r, ON), ("won", ""))


# ── 7. settings ──────────────────────────────────────────────────────────────

class PipelineSettings(unittest.TestCase):

    def test_defaults_reproduce_today(self):
        p = IC.pipeline_of({})
        self.assertEqual(p["labels"], {"inquiry": "Inquiry", "quoted": "Quoted",
                                       "nego": "Negotiation", "po": "PO received",
                                       "won": "Won"})
        self.assertEqual(p["words"], {"quote": "Quotation", "po": "PO"})
        self.assertEqual(p["steps"], {"negotiation": True, "details": True,
                                      "acknowledgement": True, "proforma": False})
        self.assertEqual((p["remind_days"], p["max_reminders"]), (2, 3))
        self.assertEqual((p["currency"], p["tax_label"], p["tax_percent"]),
                         ("₹", "GST", 18))

    def test_engine_and_settings_agree_on_step_defaults(self):
        self.assertEqual(IC.PIPELINE_DEFAULTS["steps"], register.STEP_DEFAULTS)

    def test_partial_config_falls_back_key_by_key(self):
        cfg = {"inquiry": {"followup_days": 5, "max_reminders": 4,
                           "terms": {"gst_percent": 12},
                           "pipeline": {"labels": {"won": "Booked", "po": ""},
                                        "words": {"quote": "Offer"},
                                        "steps": {"proforma": True}}}}
        p = IC.pipeline_of(cfg)
        self.assertEqual(p["labels"]["won"], "Booked")
        self.assertEqual(p["labels"]["po"], "PO received")
        self.assertEqual((p["words"]["quote"], p["words"]["po"]), ("Offer", "PO"))
        self.assertTrue(p["steps"]["proforma"] and p["steps"]["negotiation"])
        self.assertEqual((p["remind_days"], p["max_reminders"], p["tax_percent"]),
                         (5, 4, 12), "the settings Prism already had must count")
        self.assertEqual(IC.stage_label(cfg, "won"), "Booked")
        self.assertEqual(IC.stage_label(cfg, "lost"), "Lost")
        self.assertEqual(IC.word(cfg, "quote"), "Offer")
        self.assertTrue(IC.step_enabled(cfg, "proforma"))
        self.assertEqual(IC.remind_days(cfg), 5)
        self.assertEqual(IC.max_reminders(cfg), 4)

    def test_junk_config_is_the_defaults(self):
        for cfg in ({"inquiry": {"pipeline": "x"}},
                    {"inquiry": {"pipeline": {"labels": [], "steps": None,
                                              "remind_days": "soon",
                                              "max_reminders": -1,
                                              "tax_percent": 500,
                                              "currency": "  "}}},
                    {"inquiry": None}):
            self.assertEqual(IC.pipeline_of(cfg), IC.pipeline_of({}), cfg)

    def test_another_clients_money(self):
        cfg = {"inquiry": {"pipeline": {"currency": "€", "tax_label": "VAT",
                                        "tax_percent": "20"}}}
        self.assertEqual(IC.currency_of(cfg), "€")
        self.assertEqual(IC.tax_of(cfg), ("VAT", 20))
        self.assertEqual(IC.money_of(cfg, 1234567), "€1,234,567")
        self.assertEqual(IC.money_of({}, 1234567), "₹12,34,567")

    def test_format_money(self):
        cases = [((110000, "₹"), "₹1,10,000"), (("125000.00", "₹"), "₹1,25,000"),
                 ((999, "₹"), "₹999"), ((110000.5, "AED"), "AED 110,000.50"),
                 ((110000, "$"), "$110,000"), ((-1234567, "₹"), "-₹12,34,567"),
                 ((Decimal("1000.005"), "Rs"), "Rs 1,000.01"),
                 (("abc", "₹"), ""), ((None, "₹"), ""), (("", "$"), "")]
        for (value, cur), want in cases:
            self.assertEqual(IC.format_money(value, cur), want, (value, cur))
        # The same lakh grouping as the engine's own quotations.
        self.assertEqual(IC.format_money(Decimal("14250012.34"), "₹"),
                         "₹" + quoting.indian_currency(Decimal("14250012.34")))



# ── review R1 (2026-10-13): a heuristic order never moves a row ──────────────

SIGNATURE = ("\n\nRegards,\nR. Patel, Purchase\nShakti Auto Components\n"
             "P.O. Box 1234, Vatva GIDC, Ahmedabad 382445\n")
DRAWING = [("GA-drawing-rev2.pdf", b"%PDF-1.4 drawing", "application/pdf")]


def mail_with_inline_logo(body, name="po-logo.png"):
    msg = EmailMessage()
    msg["Subject"] = "Re: Enquiry"
    msg["From"] = "Mr Patel <purchase@shaktiauto.in>"
    msg["To"] = "sales@acme.co.in"
    msg["Date"] = "Mon, 12 Oct 2026 09:14:00 +0530"
    msg["Message-ID"] = "<b5@shaktiauto.in>"
    msg["In-Reply-To"] = msg["References"] = "<a1@shaktiauto.in>"
    msg.set_content(body)
    msg.add_attachment(b"\x89PNG" + b"0" * 2000, maintype="image", subtype="png",
                       filename=name, disposition="inline")
    return inbox.parse_message(msg.as_bytes(), uid=1)


class POWords(unittest.TestCase):
    """triage's order words and PO numbers are word-bounded, and a P.O. Box or
    a post-office address is never a purchase order."""

    def test_not_an_order(self):
        for text in ("P.O. Box 1234", "PO Box 12", "p.o box 7",
                     "Vasna P.O., Ahmedabad", "P.O. Box No. 1234",
                     "expo no 5 hall B", "tempo now arriving", "repo number 5",
                     "send PO soon", "Kindly quote 20 nos gate valve"):
            self.assertFalse(triage._has_po_words(text), text)
            self.assertEqual(triage.po_number(text), "", text)

    def test_reads_as_an_order(self):
        for text in ("PO No. 4512", "P.O. # PO/26/118", "our PO is attached",
                     "Purchase Order No: 77-A", "please find our P.O. enclosed"):
            self.assertTrue(triage._has_po_words(text), text)

    def test_po_number_needs_a_digit(self):
        self.assertEqual(triage.po_number("PO No. 4512 dated 12-10"), "4512")
        self.assertEqual(triage.po_number("P.O. # PO/26/118."), "PO/26/118")
        self.assertEqual(triage.po_number("Purchase Order No: 77-A"), "77-A")
        self.assertEqual(triage.po_number("PO number please"), "")

    def test_a_signature_does_not_make_a_known_customer_an_order(self):
        known = triage.Knowledge(customers={"shaktiauto.in"})
        v = triage.rules_pass(mail(body="Kindly quote 20 nos gate valve." + SIGNATURE),
                              known)
        self.assertEqual(v.category, triage.INQUIRY)

    def test_inline_and_small_images_are_not_attachments(self):
        m = mail_with_inline_logo("Thanks.", name="po-logo.png")
        self.assertEqual(triage.real_attachments(m), [])
        self.assertFalse(triage._po_attachment(m))
        small = mail(attachments=[("PO-stamp.png", b"\x89PNG" + b"0" * 900, "image/png")])
        self.assertFalse(triage._po_attachment(small))
        logo = mail(attachments=[("image001.png", b"\x89PNG" + b"0" * 90000, "image/png")])
        self.assertEqual(triage.real_attachments(logo), [])
        self.assertTrue(triage._po_attachment(mail(attachments=PO_PDF)))


class HeuristicOrdersStayInquiries(_Loop):
    """Review R1 scenarios A and B, with the sorter's real rules and with an
    AI that said ORDER: the row stays where it is, flagged "maybe"."""

    def assert_flagged_inquiry(self, r):
        self.assertEqual(r["Status"], register.NEW)
        self.assertEqual(r["No quotation"], register.MAYBE)
        self.assertTrue(register.maybe_po(r))
        self.assertEqual(register.stage_of(r)[0], "inquiry")

    def test_a_reply_with_a_drawing_from_a_po_box_customer(self):     # A
        self.run_check([mail(body="Please quote for 5000 springs." + SIGNATURE)])
        reply = mail(subject="Re: Enquiry", body="Drawing attached." + SIGNATURE,
                     message_id="<b2@shaktiauto.in>", reply_to="<a1@shaktiauto.in>",
                     attachments=DRAWING)
        self.run_check([reply])
        r = self.rows()[0]
        self.assertEqual((r["Status"], r["No quotation"]), (register.NEW, ""))
        self.run_check([reply], triage.ORDER)        # an AI that said ORDER
        self.assertEqual(self.rows()[0]["Status"], register.NEW)

    def test_an_order_word_reply_without_a_po_number_is_flagged(self):
        self.run_check([mail()])
        reply = mail(subject="Re: Enquiry", body="Our purchase order is attached.",
                     message_id="<b2@shaktiauto.in>", reply_to="<a1@shaktiauto.in>",
                     attachments=PO_PDF)
        self.run_check([reply], triage.ORDER)
        self.assert_flagged_inquiry(self.rows()[0])

    def test_a_fresh_enquiry_from_a_po_box_customer(self):              # B
        result = self.run_check([mail(body="Kindly quote 20 nos gate valve." + SIGNATURE)])
        self.assertEqual((len(result.new_inquiries), len(result.orders)), (1, 0))
        r = self.rows()[0]
        self.assertEqual((r["Status"], r["No quotation"]), (register.NEW, ""))

    def test_a_fresh_mail_the_ai_called_an_order_is_a_flagged_inquiry(self):
        # Still LISTED as an order (test_mailflow: a new correspondent's
        # first ORDER is an order), but the row is a New inquiry, flagged.
        result = self.run_check([mail(body="Please supply 20 nos. PO to follow.",
                                      attachments=PO_PDF)], triage.ORDER)
        self.assertEqual(len(result.orders), 1)
        self.assert_flagged_inquiry(self.rows()[0])

    def test_expo_no_is_not_a_po_number(self):
        result = self.run_check([mail(body="Met you at expo no. 4 last week, "
                                           "please quote 20 nos.",
                                      attachments=PO_PDF)], triage.ORDER)
        self.assertEqual(len(result.orders), 1)
        self.assert_flagged_inquiry(self.rows()[0])

    def test_po_no_inside_words_is_not_a_po_number(self):
        for body in ("Repo number 4512 for our records.", "Tempo no. 4512 will collect."):
            self.assertEqual(triage.po_number(body), "", body)
        self.run_check([mail(body="Tempo no. 4512 will collect.",
                             attachments=PO_PDF)], triage.ORDER)
        self.assert_flagged_inquiry(self.rows()[0])

    def test_an_inline_logo_is_not_order_evidence(self):
        self.run_check([mail()])
        m = mail_with_inline_logo("PO No. 4512 — please confirm the rate.")
        self.run_check([m], triage.ORDER)
        r = self.rows()[0]
        self.assertEqual(r["Status"], register.NEW)
        self.assertNotEqual(r["No quotation"], register.YES)

    def test_a_real_po_with_its_number_and_pdf_is_an_order(self):
        self.run_check([mail()])
        po = mail(subject="Re: Enquiry", body="Please find PO No. SP/0112 attached."
                  + SIGNATURE, message_id="<b3@shaktiauto.in>",
                  reply_to="<a1@shaktiauto.in>", attachments=PO_PDF)
        self.run_check([po], triage.ORDER)
        r = self.rows()[0]
        self.assertEqual((r["Status"], r["No quotation"], r["PO number"]),
                         (register.ACCEPTED, "yes", "SP/0112"))

    def test_a_mail_naming_our_quotation_number_is_certain(self):
        rows = [row(**{"Quotation no": "QTN/26-27/0101"})]
        m = mail(body="Go ahead against your QTN-26-27-0101, order follows.")
        self.assertTrue(mailflow._order_is_certain(m, rows))
        self.assertFalse(mailflow._order_is_certain(
            mail(body="Go ahead against QTN-26-27-0999."), rows))

    def test_the_owner_confirms_a_flagged_row(self):
        r = row()
        register.flag_maybe_po(r)
        self.assertEqual(register.stage_of(r), ("inquiry", "you"))
        register.mark_po_without_quote(r, "", TODAY)
        self.assertEqual(register.stage_of(r), ("po", "nopo"))
        register.flag_maybe_po(r)                       # never weakens a yes
        self.assertEqual(r["No quotation"], "yes")


# ── review R2 (2026-10-13): their ask is never a phone, pincode or unit rate ─

class TheirAskIsNotAPhoneOrAPincode(unittest.TestCase):

    def test_review_strings(self):
        for text, quoted in (
                ("best price please. Call me at 9876543210", None),
                ("best price please. Call me at 9876543210", "125000"),
                ("best price please. Call me at 98765 43210", "50000"),
                ("please revise, delivery at 380015", "500000"),
                ("for best price contact purchase desk, delivery at 380015", "500000"),
                ("pincode 380015", "500000"),
                ("upto 75000 per kg", "100000"),
                ("Can you do 95,000 per unit?", "100000"),
                ("rate 95,000 @ 3 pcs", "100000"),
                ("price 90000 each", "100000"),
                ("rate 900/unit", "1000"),
                ("quote at 2026 rates", None),
                ("quote at 2026 rates", "5000"),
                ("Best rate for 100k units?", None),
                ("Best rate for 100k units?", "200000"),
                ("can you do 95,000?", None),
                ("at 90,000", "100000")):
            self.assertIsNone(register.read_ask(text, quoted), (text, quoted))

    def test_true_positives(self):
        for text, quoted, want in (
                ("Can you do ₹1,10,000?", "125000", "110000.00"),
                ("Can you do ₹1,10,000?", None, "110000.00"),
                ("our budget is Rs. 2.1 lakh", "250000", "210000.00"),
                ("our budget is Rs. 2.1 lakh", None, "210000.00"),
                ("best we can pay is 95,000/-", "100000", "95000.00"),
                ("best we can pay is 95,000/-", None, "95000.00")):
            self.assertEqual(register.read_ask(text, quoted), Decimal(want), text)

    def test_plausible_ask(self):
        self.assertTrue(register.plausible_ask("110000", "125000"))
        for ask in ("0", "", "9876543210", "380015", "900", "125000"):
            self.assertFalse(register.plausible_ask(ask, "125000"), ask)
        self.assertFalse(register.plausible_ask("110000", ""))



# ── review round 2 (R3–R16), engine side ─────────────────────────────────────

def _quote(lines, freight=0, discount=0, gst=18):
    return quoting.Quotation(
        lines=[quoting.QuoteLine(f"item {i}", Decimal(q), "nos", Decimal(r), "")
               for i, (q, r) in enumerate(lines)],
        terms=quoting.Terms(gst_percent=Decimal(gst), freight=Decimal(freight),
                            discount_percent=Decimal(discount)))


class R3MixedCodeAndWordPO(unittest.TestCase):
    ITEMS = [quoting.RateItem(code="1128K", description="Compression spring 1128K",
                              rate=Decimal("12")),
             quoting.RateItem(code="GV50", description="Gate valve 50 NB cast iron",
                              rate=Decimal("4500")),
             quoting.RateItem(code="BV25", description="Ball valve 25 NB brass",
                              rate=Decimal("900"))]

    def test_word_lines_are_priced_or_listed_never_dropped(self):
        po = ("Purchase Order PO-778\n1128K x 40 nos\n"
              "Gate valve 50 NB cast iron - 10 nos\n"
              "Ball valve 25NB brass - 6 nos\n"
              "Something we do not sell at all - 3 nos\n"
              "Delivery at 380015")
        priced = quoting.price_order(po, self.ITEMS)
        described = [l.description for l in priced.lines]
        self.assertIn("Compression spring 1128K", described)
        self.assertIn("Gate valve 50 NB cast iron", described)
        self.assertIn("Ball valve 25 NB brass", described)
        self.assertTrue(any("do not sell" in u for u in priced.unsure), priced.unsure)
        self.assertEqual(priced.subtotal, Decimal("480") + 45000 + 5400)


class R4RevisionTotalIsExact(unittest.TestCase):

    def test_freight_discount_and_gst(self):
        q = _quote([(1, 100000)], freight=5000, discount=5)
        self.assertTrue(quoting.scale_to_total(q, "110000"))
        self.assertEqual(q.total, Decimal("110000.00"))
        self.assertEqual(q.terms.freight, Decimal(5000))       # never touched

    def test_rounding_paise_land_on_a_line(self):
        for lines, target in (([(10, 9000), (3, 1234)], "110000"),
                              ([(7, 333), (13, 1000)], "12345.67")):
            q = _quote(lines, freight=500, discount=2)
            self.assertTrue(quoting.scale_to_total(q, target), lines)
            self.assertEqual(q.total, Decimal(target))

    def test_unreachable_says_so(self):
        q = _quote([(40, 12)])
        self.assertFalse(quoting.scale_to_total(q, "500"))
        self.assertNotEqual(q.total, Decimal("500"))           # caller prints q.total
        self.assertFalse(quoting.scale_to_total(_quote([(1, 100)], freight=5000), "100"))


class R6RevisionNumbers(_TempDir):

    def test_hand_typed_revisions(self):
        for cell, want in (("", 0), ("1", 1), ("Rev 1", 1), ("R2", 2), ("2.0", 2),
                           (" 3 ", 3), ("x", 0)):
            self.assertEqual(register.revision_of(row(Revision=cell)), want, cell)

    def test_never_reuses_a_file_on_disk(self):
        r = row(**{"Quotation no": "QTN/26-27/0001", "Revision": "Rev 1",
                   "Folder": self.dir})
        for name in ("QTN-26-27-0001.pdf", "QTN-26-27-0001-R1.pdf",
                     "QTN-26-27-0001-R2.csv"):
            open(os.path.join(self.dir, name), "w").close()
        self.assertEqual(register.revision_on_disk(self.dir, "QTN/26-27/0001"), 2)
        self.assertEqual(register.next_revision(r), 3)
        register.revise_quotation(r, "100000", TODAY, revision=3)
        self.assertEqual(r["Revision"], "3")


class R8HandTypedStatuses(unittest.TestCase):

    def test_case_and_aliases(self):
        q = {"Quotation no": "QTN/26-27/0001"}
        for status, want in (("converted", "won"), ("Won", "won"), ("WON", "won"),
                             ("order received", "won"), ("not converted", "lost"),
                             ("Not Converted", "lost"), ("Lost", "lost"),
                             ("  quoted ", "quoted"), ("negotiation", "nego"),
                             ("accepted", "po")):
            self.assertEqual(register.stage_of(row(Status=status, **q))[0], want, status)
            self.assertEqual(register.stage_of(row(Status=status))[0], want, status)

    def test_one_reader_for_board_and_colours(self):
        from addons.inquiry import documents
        for text in ("won", "Lost", "follow up", "", "quote sent", "whatever"):
            self.assertEqual(documents.status_key(text), register.normalise_status(text))


class R11ProformaIsNotSentUntilSent(unittest.TestCase):

    def test_due_then_sent(self):
        p = IC.pipeline_of({"inquiry": {"pipeline": {"steps": {"proforma": True}}}})
        r = row(**{"Quotation no": "QTN/26-27/0001", "PO number": "PO-1"})
        self.assertTrue(register.mark_proforma_due(r, p))
        self.assertEqual((r["Status"], r["Proforma"]), (register.ACCEPTED, "to send"))
        self.assertTrue(register.proforma_due(r))
        self.assertEqual(register.stage_of(r, p), ("po", "proforma"))
        self.assertTrue(register.mark_proforma_sent(r, p))
        self.assertFalse(register.proforma_due(r))
        off = IC.pipeline_of({})
        self.assertFalse(register.mark_proforma_due(row(), off))


class R13PriceHistory(unittest.TestCase):

    def test_commas_and_negatives(self):
        for cell, want in (("125000.00; 118000.00", ["125000.00", "118000.00"]),
                           ("125000, 118000", ["125000", "118000"]),
                           ("1,25,000; 1,18,000", ["125000", "118000"]),
                           ("Rs 1,25,000 | 1,18,000", ["125000", "118000"]),
                           ("-500; abc; 0", [])):
            self.assertEqual(register.price_history(row(**{"Price history": cell})),
                             [Decimal(w) for w in want], cell)

    def test_a_revision_never_shrinks_what_was_typed(self):
        r = row(**{"Quotation no": "QTN/26-27/0001", "Quotation value": "110000",
                   "Price history": "125000, 118000"})
        register.revise_quotation(r, "100000", TODAY)
        self.assertEqual(r["Price history"], "125000.00; 118000.00; 110000.00")
        odd = row(**{"Quotation no": "QTN/26-27/0001", "Quotation value": "110000",
                     "Price history": "125000; first offer by phone"})
        register.revise_quotation(odd, "100000", TODAY)
        self.assertEqual(odd["Price history"],
                         "125000; first offer by phone; 110000.00")


if __name__ == "__main__":
    unittest.main()
