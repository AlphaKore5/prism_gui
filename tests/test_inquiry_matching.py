"""
[9] A picture read badly, and a guess shown as certain.

Real case (owner's data, sent 2026-10-02): an inquiry whose mail said only
"this product, 10 nos" was quoted against a rate-list row at ₹1,10,000 a
piece, ₹12,98,000 in all, with the window showing "Confident match". The
words "this" and "product" matched, and so did the quantity's "10". These
pin the matcher changes (core/quoting.py) and the window's confidence rule
(addons/inquiry/quotation.py) that stop that.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

import core_bridge as CB  # noqa: E402,F401
from core import mailflow, ocr, quoting, register  # noqa: E402
from addons.inquiry import quotation as Q  # noqa: E402

_app = QApplication.instance() or QApplication([])

LOCKERS = [
    quoting.RateItem(code="KJP 6", description="SS Locker 6 Comp",
                     rate=Decimal("62000")),
    quoting.RateItem(code="KJP 8", description="SS Locker 8 Comp",
                     rate=Decimal("78000")),
    quoting.RateItem(code="KJP 10", description="SS Locker 10 Comp",
                     rate=Decimal("110000")),
    quoting.RateItem(code="KJP 12", description="Steel cabinet 4 shelf",
                     rate=Decimal("24000")),
]


class TheWordsThatCount(unittest.TestCase):

    def test_this_product_is_not_a_product(self):
        self.assertEqual(quoting.tokens("this product, 10 nos"), ["10"])
        for word in ("this", "that", "these", "those", "item", "items",
                     "piece", "pieces", "pc", "product", "products"):
            self.assertEqual(quoting.tokens(word), [], word)

    def test_a_lone_digit_is_kept(self):
        """"8 Comp" is what tells the 8-compartment locker from the 6."""
        self.assertEqual(quoting.tokens("SS Locker 8 Comp"),
                         ["ss", "locker", "8", "comp"])

    def test_a_digit_glued_to_its_unit_is_not_a_lone_digit(self):
        """Keeping the 2 of "2mm" made every 2 mm spring look alike, and an
        exact spec stopped reading as confident."""
        self.assertEqual(quoting.tokens("2mm wire"), ["mm", "wire"])
        self.assertEqual(quoting.tokens("Locker (8 Comp)"), ["locker", "8", "comp"])
        items = [quoting.RateItem(code=c, description=d) for c, d in (
            ("CS-201", "Compression spring 2mm wire 25 OD"),
            ("CS-202", "Compression spring 2mm wire 30 OD"),
            ("CS-203", "Compression spring 3mm wire 25 OD"))]
        exact = quoting.match_item("compression spring 2mm wire 30 od", items)
        self.assertEqual(exact[0].item.code, "CS-202")
        self.assertTrue(quoting.is_confident(exact))

    def test_a_lone_letter_is_still_noise(self):
        self.assertEqual(quoting.tokens("a b 2 mm"), ["2", "mm"])


class PickingTheRow(unittest.TestCase):

    def test_8_comp_picks_the_8_comp_locker(self):
        matches = quoting.match_item("SS Locker 8 Comp", LOCKERS)
        self.assertEqual(matches[0].item.code, "KJP 8")
        self.assertTrue(Q.confident_match(matches))

    def test_a_codes_digits_do_not_count_unless_the_code_is_named(self):
        """"8 Comp" must not pull in the row whose code is "KJP 8" on the
        strength of the 8 alone — here the 4-shelf cabinet would be, if its
        code were KJP 8."""
        items = [quoting.RateItem(code="KJP 8", description="Steel cabinet 4 shelf"),
                 quoting.RateItem(code="KJP 12", description="SS Locker 8 Comp")]
        matches = quoting.match_item("Locker 8 Comp", items)
        self.assertEqual([m.item.code for m in matches], ["KJP 12"])

    def test_a_named_code_still_matches_on_its_digits(self):
        matches = quoting.match_item("KJP 8 please", LOCKERS)
        self.assertEqual(matches[0].item.code, "KJP 8")
        self.assertIn("8", matches[0].matched)


class NeverConfidentOnAGuess(unittest.TestCase):

    def test_this_product_10_nos_is_never_a_confident_match(self):
        """The real ₹12,98,000 case."""
        matches = quoting.match_item("this product, 10 nos", LOCKERS)
        self.assertFalse(Q.confident_match(matches))

    def test_a_number_alone_is_not_enough_even_with_a_clear_margin(self):
        items = [quoting.RateItem(code="A", description="Locker 10 Comp"),
                 quoting.RateItem(code="B", description="Almirah heavy duty "
                                  "steel 10 shelf 2000mm powder coated")]
        matches = quoting.match_item("10 nos", items)
        self.assertTrue(matches)
        self.assertFalse(Q.confident_match(matches))

    def test_one_generic_word_on_a_lone_candidate_is_not_enough(self):
        matches = quoting.match_item("locker", LOCKERS[3:] + [
            quoting.RateItem(code="Z", description="Locker")])
        self.assertEqual(len(matches), 1)
        self.assertFalse(Q.confident_match(matches))

    def test_nothing_matched_is_not_confident(self):
        self.assertFalse(Q.confident_match([]))


class TheQuotationWindow(unittest.TestCase):
    """The same rule, where the owner actually sees it."""

    def setUp(self):
        from addons.inquiry import dialog as UI
        self.UI = UI
        self.folder = tempfile.mkdtemp()
        self.cfg = {"api_key": "", "inquiry": {
            "folder": self.folder, "company": "Acme",
            "terms": {"gst_percent": 18, "validity_days": 15,
                      "payment": "", "delivery": ""},
            "knowledge": {}, "local_only": True}}
        self.inquiry = os.path.join(self.folder, "inquiries", "INQ-26-27-0008")
        os.makedirs(self.inquiry)
        self.row = register.blank_row()
        self.row.update({"Inquiry no": "INQ/26-27/0008", "Status": register.NEW,
                         "Email": "buyer@kj.in", "Folder": self.inquiry,
                         "Product asked": "this product, 10 nos"})
        register.save([self.row], mailflow.Paths(self.folder).register_csv)
        self.parent = UI.InquiryDialog(self.cfg)
        self.parent._refresh_register()

    def _window(self):
        return self.UI.QuotationDialog(self.cfg, self.parent._register_rows[0],
                                       LOCKERS, self.parent)

    def test_the_real_case_asks_the_owner_to_check(self):
        window = self._window()
        self.assertFalse(window._confident)

    def test_the_picture_text_is_matched_too(self):
        """"this product" in the mail, "SS Locker (8 Comp)" in the photo:
        one request, and the photo is what names the row."""
        ocr.remember(self.inquiry, "[IMG_2041.jpeg]\nSS Locker (8 Comp)\nKJ Pharmatech\n")
        window = self._window()
        self.assertEqual(window.matches[0].item.code, "KJP 8")

    def test_the_file_name_line_of_the_picture_text_is_not_matched(self):
        ocr.remember(self.inquiry, "[Locker-10-comp.jpeg]\nSS Locker (8 Comp)\n")
        window = self._window()
        self.assertEqual(window.matches[0].item.code, "KJP 8")


if __name__ == "__main__":
    unittest.main()
