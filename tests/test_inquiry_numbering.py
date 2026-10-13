"""
Every inquiry gets its own number, and a number is never handed out twice.

Owner's report (2026-10-03): "every inquiry gets the same inquiry number, and
the register isn't the same for every inquiry". Two causes, both reproduced
against the real engine before this file was written:

  1. A second, fresh-subject enquiry from a customer with an open inquiry was
     folded into that customer's first row — same number, same folder, and
     its product written over the first one's.
  2. The next number was counted only from the rows currently in the CSV,
     so anything that dropped a row (a stale save, a hand edit) handed its
     number out again, into a folder that already held another job's files.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from email.message import EmailMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core_bridge  # noqa: F401,E402  (puts prism_terminal/core on sys.path)
from core import inbox, mailflow, register, triage  # noqa: E402


def mail(subject, body="Dear Sir, please quote 5000 compression springs.",
         sender="Owner <owner@gmail.com>", message_id="<1@x>", reply_to="",
         date="Mon, 12 Oct 2026 09:14:00 +0530", attachments=()):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "sales@acme.co.in"
    msg["Date"] = date
    msg["Message-ID"] = message_id
    if reply_to:
        msg["In-Reply-To"] = reply_to
        msg["References"] = reply_to
    msg.set_content(body)
    for name, data, mime in attachments:
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return inbox.parse_message(msg.as_bytes(), uid=1)


SPRINGS = ("Enquiry for springs",
           "Dear Sir, please quote 5000 compression springs 2mm wire 25 OD.")
LOCKERS = ("Enquiry for lockers", "Dear Sir, please quote 200 SS Locker 8 Comp.")
TENSION = ("RFQ tension springs",
           "Dear Sir, please send rate for 50 nos tension springs 1.5mm.")


class _Checks(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.paths = mailflow.Paths(self.root)
        self.cfg = {"api_key": "", "inbox": {"address": "sales@acme.co.in",
                                             "password": "p", "host": "h"}}
        self.known = triage.Knowledge(customers={"gmail.com", "patel.in"})

    def check(self, messages):
        real = inbox.fetch_new
        inbox.fetch_new = lambda cfg, state, **_kw: (messages, inbox.State(1, 99), "")
        try:
            return mailflow.check(self.cfg, self.paths, knowledge=self.known,
                                  local_only=True)
        finally:
            inbox.fetch_new = real

    def rows(self):
        return register.load(self.paths.register_csv)


class AFreshEnquiryIsItsOwnInquiry(_Checks):
    """A customer with an open inquiry who writes a brand-new enquiry gets a
    second number — the owner's decision, 2026-10-13."""

    def test_three_fresh_subjects_from_one_sender_are_three_numbers(self):
        for n, (subject, body) in enumerate((SPRINGS, LOCKERS, TENSION), 1):
            result = self.check([mail(subject, body, message_id=f"<1{n}@x>")])
            self.assertEqual(len(result.new_inquiries), 1, subject)
            self.assertEqual(len(result.replies), 0, subject)
        rows = self.rows()
        self.assertEqual([r["Inquiry no"] for r in rows],
                         ["INQ/26-27/0001", "INQ/26-27/0002", "INQ/26-27/0003"])
        self.assertEqual(len({r["Folder"] for r in rows}), 3)
        self.assertIn("springs", rows[0]["Product asked"].lower())
        self.assertIn("locker", rows[1]["Product asked"].lower())

    def test_the_same_in_one_check(self):
        self.check([mail(*SPRINGS, message_id="<21@x>"),
                    mail(*LOCKERS, message_id="<22@x>")])
        self.assertEqual(len(self.rows()), 2)

    def test_a_fresh_enquiry_with_a_quotation_open_is_still_new(self):
        self.check([mail(*SPRINGS, message_id="<31@x>")])
        rows = self.rows()
        register.mark_quoted(rows[0], "QTN/26-27/0001", 1000)
        register.save(rows, self.paths.register_csv)
        result = self.check([mail(*LOCKERS, message_id="<32@x>")])
        self.assertEqual(len(result.new_inquiries), 1)
        self.assertEqual(len(self.rows()), 2)

    def test_the_first_rows_product_is_not_overwritten(self):
        """What made the register "not the same for every inquiry"."""
        self.check([mail(*SPRINGS, message_id="<41@x>")])
        self.check([mail(*LOCKERS, message_id="<42@x>")])
        first = register.find(self.rows(), "INQ/26-27/0001")
        self.assertNotIn("locker", first["Product asked"].lower())
        self.assertNotIn("Wrote again", first.get("Notes", ""))


class ARealReplyStillJoins(_Checks):

    def test_a_threaded_reply_joins_its_row(self):
        self.check([mail(*SPRINGS, message_id="<51@x>")])
        result = self.check([mail("Re: Enquiry for springs", "10 pieces please",
                                  message_id="<52@x>", reply_to="<51@x>")])
        self.assertEqual(len(result.replies), 1)
        self.assertEqual(len(self.rows()), 1)

    def test_a_re_subject_without_headers_joins(self):
        """Some phone clients keep the Re: and drop the headers."""
        self.check([mail(*SPRINGS, message_id="<61@x>")])
        result = self.check([mail("Re: Enquiry for springs", "10 pieces please",
                                  message_id="<62@x>")])
        self.assertEqual(len(result.replies), 1)
        self.assertEqual(len(self.rows()), 1)

    def test_naming_the_inquiry_number_joins(self):
        self.check([mail(*SPRINGS, message_id="<71@x>")])
        result = self.check([mail("Enquiry INQ/26-27/0001 — drawing",
                                  "Drawing for our enquiry attached.",
                                  message_id="<72@x>")])
        self.assertEqual(len(result.replies), 1)
        self.assertEqual(len(self.rows()), 1)

    def test_naming_the_quotation_number_in_folder_spelling_joins(self):
        self.check([mail(*SPRINGS, message_id="<81@x>")])
        rows = self.rows()
        register.mark_quoted(rows[0], "QTN/26-27/0004", 1000)
        register.save(rows, self.paths.register_csv)
        result = self.check([mail("Enquiry revised",
                                  "About QTN-26-27-0004: can you do 4mm?",
                                  message_id="<82@x>")])
        self.assertEqual(len(result.replies), 1)

    def test_a_number_inside_a_longer_one_does_not_count(self):
        row = {"Inquiry no": "INQ/26-27/0001", "Email": "owner@gmail.com",
               "Status": register.NEW}
        other = mail("Enquiry", "Our ref INQ/26-27/00011", message_id="<91@x>")
        self.assertIsNone(register.find_by_thread([row], other))

    def test_an_unthreaded_answer_to_a_quotation_is_a_new_number(self):
        """Round 1's "phone-style answer" rule is dropped (owner, review F3).
        tests/test_mailflow.py pins the same case at the unit level."""
        self.check([mail(*SPRINGS, message_id="<101@x>")])
        rows = self.rows()
        register.mark_quoted(rows[0], "QTN/26-27/0001", 1000)
        register.save(rows, self.paths.register_csv)
        result = self.check([mail("best price?", "Can you do better?",
                                  message_id="<102@x>")])
        self.assertEqual(len(result.replies), 0)
        self.assertEqual(len(result.new_inquiries), 1)

    def test_a_re_of_a_mail_we_sent_joins(self):
        """Our quotation mail's subject, answered from a client that drops
        the headers and the number."""
        row = {"Inquiry no": "INQ/26-27/0001", "Email": "owner@gmail.com",
               "Status": register.QUOTED, "Product asked": "compression springs"}
        sent = {"INQ/26-27/0001": ["Our offer for your springs"]}
        reply = mail("Re: Our offer for your springs", "ok", message_id="<103@x>")
        self.assertIs(register.find_by_thread([row], reply, sent), row)
        self.assertIsNone(register.find_by_thread([row], reply))

    def test_nothing_was_sent_on_a_new_row_so_an_unthreaded_mail_is_new(self):
        row = {"Inquiry no": "INQ/26-27/0001", "Email": "owner@gmail.com",
               "Status": register.NEW}
        self.assertIsNone(register.find_by_thread(
            [row], mail("best price?", "?", message_id="<111@x>")))

    def test_another_senders_row_is_never_joined(self):
        row = {"Inquiry no": "INQ/26-27/0001", "Email": "someone@patel.in",
               "Status": register.QUOTED}
        self.assertIsNone(register.find_by_thread(
            [row], mail("Re: Enquiry", "ok", message_id="<121@x>")))


class WritingAgainOnAnUnquotedInquiry(_Checks):
    """The owner's refresh of a New row (mailflow._refresh_unquoted_row) only
    runs for mail that genuinely belongs to that row."""

    def test_a_real_follow_up_updates_what_was_asked(self):
        self.check([mail("Enquiry", "Please send more information.",
                         message_id="<131@x>")])
        result = self.check([mail("Re: Enquiry",
                                  "I want SS Locker 8 Comp, 10 nos.",
                                  message_id="<132@x>", reply_to="<131@x>")])
        self.assertEqual(len(result.replies), 1)
        row = self.rows()[0]
        self.assertIn("Locker", row["Product asked"])
        self.assertIn("10 nos", row["Quantity"])
        self.assertIn("Wrote again", row["Notes"])

    def test_a_new_enquiry_does_not_rewrite_the_older_row(self):
        self.check([mail("Enquiry", "Please send more information.",
                         message_id="<141@x>")])
        self.check([mail(*LOCKERS, message_id="<142@x>")])
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Quantity"], "")
        self.assertNotIn("Locker", rows[0]["Product asked"])

    def test_a_quoted_row_is_not_rewritten(self):
        self.check([mail(*SPRINGS, message_id="<151@x>")])
        rows = self.rows()
        register.mark_quoted(rows[0], "QTN/26-27/0001", 1000)
        register.save(rows, self.paths.register_csv)
        before = rows[0]["Product asked"]
        self.check([mail("Re: Enquiry for springs", "Make it 20 nos of lockers.",
                         message_id="<152@x>", reply_to="<151@x>")])
        self.assertEqual(self.rows()[0]["Product asked"], before)


class ANumberIsNeverHandedOutTwice(_Checks):

    def test_an_existing_folder_is_a_floor(self):
        """The row went (a stale save, a hand edit); its folder did not."""
        os.makedirs(os.path.join(self.paths.inquiries, "INQ-26-27-0007"))
        self.check([mail(*SPRINGS, message_id="<201@x>")])
        self.assertEqual(self.rows()[0]["Inquiry no"], "INQ/26-27/0008")

    def test_a_dropped_row_does_not_reissue_its_number_into_its_folder(self):
        self.check([mail(*SPRINGS, message_id="<211@x>")])
        self.check([mail(*LOCKERS, sender="B <b@patel.in>", message_id="<212@x>")])
        rows = self.rows()
        register.save(rows[:1], self.paths.register_csv)    # 0002 dropped
        self.check([mail(*TENSION, sender="C <c@patel.in>", message_id="<213@x>")])
        numbers = [r["Inquiry no"] for r in self.rows()]
        self.assertEqual(numbers, ["INQ/26-27/0001", "INQ/26-27/0003"])

    def test_other_years_and_prefixes_do_not_count(self):
        taken = ["INQ-25-26-0090", "QTN-26-27-0040.csv", "notes.txt", "KJP-0045"]
        self.assertEqual(register.next_number([], "INQ", self._october(), taken),
                         "INQ/26-27/0001")

    def test_quotation_numbers_count_files_and_sent_subjects(self):
        from core import quoting, worklist
        folder = os.path.join(self.paths.inquiries, "INQ-26-27-0001")
        os.makedirs(folder)
        open(os.path.join(folder, "QTN-26-27-0003.csv"), "w").close()
        open(os.path.join(folder, "QTN-26-27-0099 from customer.pdf"), "w").close()
        worklist.log_sent(self.root, "quotation", to="x@y.in",
                          subject="Quotation QTN/26-27/0005 — springs",
                          inquiry_no="INQ/26-27/0001")
        taken = mailflow.numbers_in_use(self.paths)
        self.assertEqual(quoting.next_quote_number([], "QTN", self._october(), taken),
                         "QTN/26-27/0006")

    def test_the_floor_never_breaks_a_check(self):
        self.paths.ensure()
        os.makedirs(os.path.join(self.paths.inquiries, "INQ-26-27-0002"))
        open(os.path.join(self.paths.worklist_dir + ".bad"), "w").close()
        self.assertIsInstance(mailflow.numbers_in_use(self.paths), list)
        self.assertEqual(mailflow.numbers_in_use(mailflow.Paths(
            os.path.join(self.root, "missing"))), [])

    @staticmethod
    def _october():
        from datetime import date
        return date(2026, 10, 12)


class AStaleCopyCannotEraseANewRow(_Checks):

    def test_a_row_added_since_the_read_survives_the_save(self):
        self.check([mail(*SPRINGS, message_id="<301@x>")])
        stale = register.load(self.paths.register_csv)
        seen = register.row_keys(stale)
        self.check([mail(*LOCKERS, sender="B <b@patel.in>", message_id="<302@x>")])
        register.mark_lost(stale[0], "price")
        added = register.save_merged(stale, self.paths.register_csv, seen)
        rows = self.rows()
        self.assertEqual([r["Inquiry no"] for r in rows],
                         ["INQ/26-27/0001", "INQ/26-27/0002"])
        self.assertEqual(rows[0]["Status"], register.NOT_CONVERTED)
        self.assertEqual(len(added), 1)

    def test_a_deleted_row_stays_deleted(self):
        self.check([mail(*SPRINGS, message_id="<311@x>"),
                    mail(*LOCKERS, sender="B <b@patel.in>", message_id="<312@x>")])
        rows = register.load(self.paths.register_csv)
        seen = register.row_keys(rows)
        register.save_merged(rows[1:], self.paths.register_csv, seen)
        self.assertEqual([r["Inquiry no"] for r in self.rows()], ["INQ/26-27/0002"])

    def test_without_a_record_of_what_was_read_it_is_a_plain_save(self):
        self.check([mail(*SPRINGS, message_id="<321@x>")])
        register.save_merged([], self.paths.register_csv, None)
        self.assertEqual(self.rows(), [])


class AnImportedSheetKeepsItsNumbers(unittest.TestCase):

    def _load(self, text):
        path = os.path.join(tempfile.mkdtemp(), "old.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return register.load(path)

    def test_inquiry_no_dot_is_read_as_the_number(self):
        rows = self._load("Inquiry No.,Customer,Email ID\nOLD-1,X,x@a.in\nOLD-2,Y,y@b.in\n")
        self.assertEqual([r["Inquiry no"] for r in rows], ["OLD-1", "OLD-2"])
        self.assertEqual(rows[0]["Email"], "x@a.in")

    def test_prisms_own_header_wins_over_a_look_alike(self):
        rows = self._load("Inquiry no,Enq No,Customer\nINQ/26-27/0001,45,X\n")
        self.assertEqual(rows[0]["Inquiry no"], "INQ/26-27/0001")
        self.assertEqual(rows[0]["Enq No"], "45")

    def test_a_hand_added_column_is_left_alone(self):
        rows = self._load("Inquiry no,Salesman\nINQ/26-27/0001,Ravi\n")
        self.assertEqual(rows[0]["Salesman"], "Ravi")

    def test_a_blank_number_finds_nothing_and_gets_no_shared_folder(self):
        self.assertIsNone(register.find([{"Inquiry no": ""}], ""))
        paths = mailflow.Paths(tempfile.mkdtemp())
        self.assertNotEqual(os.path.normpath(paths.folder_for("")),
                            os.path.normpath(paths.inquiries))

    def test_a_reply_on_an_unnumbered_row_gives_it_a_number(self):
        root = tempfile.mkdtemp()
        paths = mailflow.Paths(root)
        row = register.blank_row()
        row.update({"Email": "owner@gmail.com", "Status": register.QUOTED,
                    "Customer": "Owner", "Thread": "<400@x>"})
        register.save([row], paths.register_csv)
        real = inbox.fetch_new
        inbox.fetch_new = lambda cfg, state, **_kw: (
            [mail("Re: Quotation", "ok", message_id="<401@x>", reply_to="<400@x>")],
            inbox.State(1, 99), "")
        try:
            result = mailflow.check({"api_key": "", "inbox": {}}, paths,
                                    knowledge=triage.Knowledge(customers={"gmail.com"}),
                                    local_only=True)
        finally:
            inbox.fetch_new = real
        self.assertEqual(len(result.replies), 1)
        saved = register.load(paths.register_csv)[0]
        self.assertEqual(saved["Inquiry no"], "INQ/26-27/0001")
        self.assertTrue(result.replies[0].folder.endswith("INQ-26-27-0001"))


class ACheckDoesNotUndoTheScreen(_Checks):
    """Review F1: the owner keeps working while a check runs (the automatic
    one runs in the background). The check's save used to write back its own
    copy of the register, read before its AI calls."""

    def _while_checking(self, gui_edit, messages):
        real = mailflow.extract_details

        def edit_then_extract(*a, **k):
            gui_edit()
            return real(*a, **k)
        mailflow.extract_details = edit_then_extract
        try:
            return self.check(messages)
        finally:
            mailflow.extract_details = real

    def test_a_delete_and_a_lost_mark_made_mid_check_survive(self):
        """The reviewer's R1, as it was reproduced."""
        self.check([mail(*SPRINGS, message_id="<501@x>"),
                    mail(*LOCKERS, sender="B <b@patel.in>", message_id="<502@x>")])

        def gui():
            rows = register.load(self.paths.register_csv)
            seen = register.row_keys(rows)
            rows = [r for r in rows if r["Inquiry no"] != "INQ/26-27/0001"]
            register.mark_lost(rows[0], "price")
            register.save_merged(rows, self.paths.register_csv, seen)
        self._while_checking(gui, [mail(*TENSION, sender="C <c@patel.in>",
                                         message_id="<503@x>")])
        self.assertEqual([(r["Inquiry no"], r["Status"]) for r in self.rows()],
                         [("INQ/26-27/0002", register.NOT_CONVERTED),
                          ("INQ/26-27/0003", register.NEW)])

    def test_a_quotation_recorded_mid_check_is_kept(self):
        self.check([mail(*SPRINGS, message_id="<511@x>")])

        def gui():
            rows = register.load(self.paths.register_csv)
            seen = register.row_keys(rows)
            register.mark_quoted(rows[0], "QTN/26-27/0001", 1000)
            register.save_merged(rows, self.paths.register_csv, seen)
        self._while_checking(gui, [mail(*TENSION, sender="C <c@patel.in>",
                                         message_id="<512@x>")])
        first = register.find(self.rows(), "INQ/26-27/0001")
        self.assertEqual(first["Status"], register.QUOTED)
        self.assertEqual(first["Quotation no"], "QTN/26-27/0001")

    def test_the_checks_own_changes_land_on_the_owners_edits(self):
        """A reply's thread ids and note are applied to the row as it is on
        disk; the owner's own note typed meanwhile is kept beside it."""
        self.check([mail("Enquiry", "Please send more information.",
                         message_id="<521@x>")])

        def gui():
            rows = register.load(self.paths.register_csv)
            seen = register.row_keys(rows)
            rows[0]["Notes"] = "Called him"
            rows[0]["Customer"] = "Patel Springs"
            register.save_merged(rows, self.paths.register_csv, seen)
        self._while_checking(gui, [mail("Re: Enquiry", "I want SS Locker 8 Comp, 10 nos.",
                                        message_id="<522@x>", reply_to="<521@x>")])
        row = self.rows()[0]
        self.assertEqual(row["Customer"], "Patel Springs")
        self.assertTrue(row["Notes"].startswith("Called him | Wrote again"), row["Notes"])
        self.assertIn("<522@x>", row["Thread"])
        self.assertIn("Locker", row["Product asked"])

    def test_a_reply_on_a_row_deleted_mid_check_does_not_bring_it_back(self):
        self.check([mail(*SPRINGS, message_id="<531@x>")])

        def gui():
            register.save_merged([], self.paths.register_csv,
                                 register.row_keys(register.load(self.paths.register_csv)))
        self._while_checking(gui, [mail("Re: Enquiry for springs", "send drawing",
                                        message_id="<532@x>", reply_to="<531@x>"),
                                   mail(*TENSION, sender="C <c@patel.in>",
                                        message_id="<533@x>")])
        self.assertEqual([r["Inquiry no"] for r in self.rows()], ["INQ/26-27/0002"])


class AForwardIsNotAReply(_Checks):
    """Review F2: purchase departments forward plant requirements as new
    enquiries. "Fwd:" alone does not make a mail part of an open inquiry."""

    def test_a_forwarded_fresh_enquiry_gets_its_own_number(self):
        """The reviewer's R2."""
        self.check([mail(*SPRINGS, message_id="<601@x>")])
        result = self.check([mail("Fwd: Enquiry for SS lockers",
                                  "Please see below, our plant needs 20 SS lockers 8 comp",
                                  message_id="<602@x>")])
        self.assertEqual((len(result.new_inquiries), len(result.replies)), (1, 0))
        rows = self.rows()
        self.assertIn("springs", rows[0]["Product asked"].lower())
        self.assertIn("locker", rows[1]["Product asked"].lower())

    def test_fw_and_wg_too(self):
        row = {"Inquiry no": "INQ/26-27/0001", "Email": "owner@gmail.com",
               "Status": register.NEW, "Product asked": "Enquiry for springs"}
        for subject in ("FW: RFQ hinges", "WG: Anfrage Scharniere", "Re: Price list",
                        "Re:", "Fwd: "):
            self.assertIsNone(register.find_by_thread(
                [row], mail(subject, "x", message_id="<603@x>")), subject)

    def test_a_forward_of_the_same_enquiry_joins_but_does_not_rewrite_it(self):
        self.check([mail(*SPRINGS, message_id="<611@x>")])
        before = self.rows()[0]["Product asked"]
        result = self.check([mail("Fwd: Enquiry for springs",
                                  "Also need 20 SS lockers 8 comp", message_id="<612@x>")])
        self.assertEqual(len(result.replies), 1)
        row = self.rows()[0]
        self.assertEqual(row["Product asked"], before)
        self.assertNotIn("Wrote again", row.get("Notes", ""))

    def test_a_forward_naming_the_number_joins_and_refreshes(self):
        self.check([mail("Enquiry", "Please send more information.",
                         message_id="<621@x>")])
        result = self.check([mail("Fwd: our requirement",
                                  "Ref INQ/26-27/0001: we need SS Locker 8 Comp, 10 nos.",
                                  message_id="<622@x>")])
        self.assertEqual(len(result.replies), 1)
        self.assertIn("Locker", self.rows()[0]["Product asked"])

    def test_a_reply_header_that_points_nowhere_is_not_enough(self):
        row = {"Inquiry no": "INQ/26-27/0001", "Email": "owner@gmail.com",
               "Status": register.NEW, "Product asked": "Enquiry for springs",
               "Thread": "<1@x>"}
        other = mail("Enquiry for lockers", "x", message_id="<631@x>",
                     reply_to="<somewhere-else@x>")
        self.assertIsNone(register.find_by_thread([row], other))


class AFreshSubjectIsNeverAnAnswer(unittest.TestCase):
    """Review F3, the owner's rule: "phone-style answer" joining is dropped.
    A mail with no reply markers joins only on its thread headers or a
    number it names — even when the sender has a quotation open."""

    ROW = {"Inquiry no": "INQ/26-27/0001", "Email": "buyer@shaktiauto.in",
           "Status": register.QUOTED, "Product asked": "compression springs",
           "Thread": "<0@x>"}

    def _mail(self, subject, body, reply_to=""):
        return mail(subject, body, sender="Buyer <buyer@shaktiauto.in>",
                    message_id="<99@x>", reply_to=reply_to)

    def test_the_reviewers_subjects_get_new_numbers(self):
        for subject, body in (("SS Locker 8 Comp", "Need 20 nos SS locker 8 comp"),
                              ("", "Please send your best rate for 100 nos springs"),
                              ("Need 50 lockers", "Kindly quote"),
                              ("Price list", "Send price list of your SS products"),
                              ("Urgent", "Need drawing attached item 200 nos")):
            self.assertIsNone(register.find_by_thread([dict(self.ROW)],
                                                      self._mail(subject, body)),
                              repr(subject))

    def test_an_empty_subject_joins_only_on_its_thread(self):
        row = dict(self.ROW)
        self.assertIs(register.find_by_thread(
            [row], self._mail("", "ok go ahead", reply_to="<0@x>")), row)

    def test_naming_the_quotation_still_joins(self):
        row = dict(self.ROW, **{"Quotation no": "QTN/26-27/0004"})
        self.assertIs(register.find_by_thread(
            [row], self._mail("Urgent", "About QTN/26-27/0004, can you do 4mm?")), row)


class TwoWritersTakeTurns(unittest.TestCase):
    """The lock file around every read-modify-write of the register."""

    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "inquiries.csv")
        self.wait = register.LOCK_WAIT

    def tearDown(self):
        register.LOCK_WAIT = self.wait

    def test_the_lock_is_gone_after_a_save(self):
        register.save([dict(register.blank_row(), **{"Inquiry no": "INQ/26-27/0001"})],
                      self.path)
        self.assertFalse(os.path.exists(self.path + ".lock"))
        self.assertEqual(len(register.load(self.path)), 1)

    def test_a_held_lock_refuses_plainly_and_keeps_the_file(self):
        register.save([dict(register.blank_row(), **{"Inquiry no": "INQ/26-27/0001"})],
                      self.path)
        open(self.path + ".lock", "w").close()
        register.LOCK_WAIT = 0.2
        with self.assertRaises(register.RegisterLocked) as caught:
            register.save([], self.path)
        self.assertIn("Try again", str(caught.exception))
        self.assertEqual(len(register.load(self.path)), 1)

    def test_a_lock_left_by_a_crash_is_taken_over(self):
        import time
        lock = self.path + ".lock"
        open(lock, "w").close()
        old = time.time() - register.LOCK_STALE - 5
        os.utime(lock, (old, old))
        register.save([], self.path)
        self.assertFalse(os.path.exists(lock))


class ANumberedRowIsNotDuplicated(unittest.TestCase):
    """Review F12: a hand-kept row with no number, numbered by a check while
    the screen still holds it unnumbered."""

    def test_the_screens_copy_takes_the_number_instead_of_doubling(self):
        path = os.path.join(tempfile.mkdtemp(), "inquiries.csv")
        row = dict(register.blank_row(), **{"Email": "x@a.in",
                                            "Date received": "01-10-2026",
                                            "Product asked": "springs",
                                            "Status": register.QUOTED})
        register.save([row], path)
        screen = register.load(path)
        seen = register.row_keys(screen)
        disk = register.load(path)
        disk[0]["Inquiry no"] = "INQ/26-27/0003"
        disk[0]["Folder"] = "/somewhere/INQ-26-27-0003"
        register.save(disk, path)
        screen[0]["Notes"] = "called"
        register.save_merged(screen, path, seen)
        rows = register.load(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Inquiry no"], "INQ/26-27/0003")
        self.assertEqual(rows[0]["Notes"], "called")

    def test_deleted_on_screen_stays_deleted_after_it_was_numbered(self):
        path = os.path.join(tempfile.mkdtemp(), "inquiries.csv")
        row = dict(register.blank_row(), **{"Email": "x@a.in",
                                            "Date received": "01-10-2026",
                                            "Product asked": "springs"})
        register.save([row], path)
        seen = register.row_keys(register.load(path))
        disk = register.load(path)
        disk[0]["Inquiry no"] = "INQ/26-27/0003"
        register.save(disk, path)
        register.save_merged([], path, seen)
        self.assertEqual(register.load(path), [])


if __name__ == "__main__":
    unittest.main()
