"""The pipeline's own actions on InquiryDialog, as a mixin.

Kept out of dialog.py so the 10-03 work on the other machine merges with a
handful of hook lines rather than a few hundred new ones. Every method runs
ON InquiryDialog (self is the dialog): it uses the dialog's register rows,
save path, status line, workers and letter dialog, and the engine's phase-1
helpers (register.note_counter, hold_price, revise_quotation, ...) through
core_bridge.

Nothing here sends on its own. Every mail is shown in the same editable
letter window a reminder uses, and goes only when the owner presses Send.
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QLabel, QLineEdit,
    QMessageBox, QTableWidget, QTableWidgetItem,
)

import core_bridge as CB
import email_config
import i18n
import inquiry_config
from inquiry_config import TABS
from dialogs.base import PrismDialog
from workers import SendWorker


class _AmountDialog(PrismDialog):
    """One money figure, with a sentence saying what it is for."""

    def __init__(self, title: str, note: str, label: str, value: str,
                 ok_text: str, parent=None):
        super().__init__(title, "", icon="file-text", parent=parent)
        self.setWindowTitle(title)
        caption = QLabel(note)
        caption.setWordWrap(True)
        self.body.addWidget(caption)
        form = QFormLayout()
        self.value = QLineEdit(value)
        form.addRow(label, self.value)
        self.note = QLineEdit()
        self.note.setPlaceholderText(i18n.t("A note, if you want one"))
        form.addRow(i18n.t("Note:"), self.note)
        self.body.addLayout(form)
        self.footer.add_secondary(self.button(i18n.t("Cancel"),
                                              on_click=self.reject))
        self.footer.set_primary(self.button(ok_text, "primary",
                                            on_click=self.accept))

    def amount(self) -> Decimal:
        return CB.get_register().money(self.value.text())


class _AddInquiryDialog(PrismDialog):
    """An enquiry that came by phone, WhatsApp or a visit."""

    FIELDS = (("Customer", "Customer"), ("Contact person", "Contact person"),
              ("Email", "Email"), ("Phone", "Phone"),
              ("Product asked", "What they want"), ("Quantity", "Quantity"),
              ("Notes", "Notes"))

    def __init__(self, stage_word: str, parent=None):
        super().__init__(i18n.t("Add an inquiry by hand"),
                         i18n.t("It gets the next inquiry number, its own "
                                "folder, and lands in {stage}.").replace(
                             "{stage}", stage_word),
                         icon="plus", parent=parent)
        self.setWindowTitle(i18n.t("Add an inquiry by hand"))
        form = QFormLayout()
        self.edits = {}
        for key, text in self.FIELDS:
            edit = QLineEdit()
            self.edits[key] = edit
            form.addRow(i18n.t(text), edit)
        self.body.addLayout(form)
        self.footer.add_secondary(self.button(i18n.t("Cancel"),
                                              on_click=self.reject))
        self.footer.set_primary(self.button(i18n.t("Add inquiry"), "primary",
                                            on_click=self._ok))

    def _ok(self):
        if not (self.edits["Customer"].text().strip()
                or self.edits["Email"].text().strip()):
            self.edits["Customer"].setFocus()
            return
        self.accept()

    def values(self) -> dict:
        return {k: e.text().strip() for k, e in self.edits.items()}


class _PricedOrderDialog(PrismDialog):
    """A PO with no quotation, priced from the rate list: lines, the lines
    Prism was unsure of, the totals. Accept = write the acknowledgement."""

    def __init__(self, priced, money, tax_label: str, po_word: str,
                 parent=None):
        super().__init__(
            i18n.t("Price this {po} from the rate list").replace("{po}", po_word),
            i18n.t("No quotation was sent for this order. Check the lines, "
                   "then send the acknowledgement for the customer to "
                   "confirm."), icon="file-text", parent=parent, scrollable=True)
        self.setWindowTitle(i18n.t("Price it from the rate list"))
        table = QTableWidget(len(priced.lines), 4)
        table.setHorizontalHeaderLabels([i18n.t("Item"), i18n.t("Qty"),
                                         i18n.t("Rate"), i18n.t("Amount")])
        for i, line in enumerate(priced.lines):
            for c, text in enumerate((line.description, f"{line.quantity}",
                                      money(line.rate), money(line.amount))):
                table.setItem(i, c, QTableWidgetItem(str(text)))
        table.resizeColumnsToContents()
        self.table = table
        self.body.addWidget(table)
        if priced.unsure:
            unsure = QLabel(i18n.t("Not on the rate list — price these "
                                   "yourself:") + "\n• " + "\n• ".join(
                priced.unsure))
            unsure.setWordWrap(True)
            self.body.addWidget(unsure)
        self.body.addWidget(QLabel(
            f"{i18n.t('Subtotal')}: {money(priced.subtotal)}   "
            f"{tax_label}: {money(priced.tax)}   "
            f"{i18n.t('Total')}: {money(priced.total)}"))
        self.footer.add_secondary(self.button(i18n.t("Cancel"),
                                              on_click=self.reject))
        self.footer.set_primary(self.button(
            i18n.t("Write the acknowledgement"), "primary", on_click=self.accept))


class PipelineActions:
    """Mixed into InquiryDialog."""

    # ── plumbing ──────────────────────────────────────────────────────────
    def _pipeline(self) -> dict:
        return inquiry_config.pipeline_of(self.cfg)

    def _row_handlers(self) -> dict:
        """Every action a register row can take, by key — the Selected
        panel's buttons and the board drawer share this one table."""
        return {
            "prepare": self._prepare_quotation,
            "revise": self._revise_quotation,
            "remind": self._send_reminder, "win_back": self._win_back,
            "record_po": self._record_po_by_hand,
            "already_quoted": self._mark_already_quoted,
            "boq": self._make_boq, "phone": self._phone_reply,
            "lost": self._mark_lost, "edit": self._edit_row,
            "folder": self._open_inquiry_folder, "delete": self._delete_inquiry,
            "history": self._show_history,
            # the pipeline's own
            "ask_details": self._ask_details,
            "chase_details": self._chase_details,
            "got_po": self._got_po,
            "countered": self._they_countered,
            "said_yes": self._said_yes,
            "hold": self._hold_price,
            "update": self._update_from_reply,
            "read_po": self._read_po_for_row,
            "not_order": self._not_an_order,
            "price_po": self._price_po,
            "chase_po": self._chase_po,
            "advance": self._advance_received,
            "send_proforma": self._send_proforma,
            "chase_advance": self._chase_advance,
            "open_po": self._open_inquiry_folder,
            "reopen": self._reopen,
        }

    def act_on(self, row: dict, key: str, **kw) -> None:
        """Run one action on one row, as if it were picked in a table."""
        self._focus_row, self._focus_key = row, row.get("Inquiry no", "")
        self._focus_tab = "board"
        self._act_kw = kw
        try:
            self._row_handlers()[key]()
        finally:
            self._act_kw = {}

    def act_on_rows(self, rows: list[dict], key: str) -> None:
        """Select mode's bulk actions."""
        if key == "delete":
            self._delete_inquiries(list(rows))
        elif key == "xlsx":
            self._save_rows_xlsx(list(rows))

    def _row_now(self) -> dict | None:
        return self._current_row()

    def _save_and_log(self, row: dict, event: str, body: str = "") -> bool:
        try:
            self._save_register()
        except Exception as e:                          # noqa: BLE001
            self._explain(str(e))
            return False
        CB.get_history().append(row.get("Folder") or self._root(), event,
                                body=body)
        self._refresh_register()
        return True

    def _signature(self) -> str:
        s = self._settings()
        return s.get("signature", "") or s.get("company", "")

    def _letter(self, row: dict, subject: str, opener: str, *, title: str,
                kind: str, on_sent, files: list | None = None,
                note: str = "", on_failed=None) -> bool:
        """Show the letter, send it if the owner says so, then on_sent(row).
        The same window and worker a reminder uses. on_failed() runs when
        nothing went out — no address, no account, Cancel, or a failed
        send — so a caller can throw away files it made for this letter."""
        from addons.inquiry.dialog import _ReminderDialog

        def give_up():
            if on_failed is not None:
                try:
                    on_failed()
                except Exception:                       # noqa: BLE001
                    pass
            return False
        address = row.get("Email", "")
        if not address:
            QMessageBox.information(self, title, i18n.t(
                "This inquiry has no email address to write to."))
            return give_up()
        if not email_config.can_send(self.cfg):
            QMessageBox.information(self, title, i18n.t(
                "Sending needs your outgoing account set up — open the "
                "Email spamming add-on once and enter it."))
            return give_up()
        body = (i18n.t("Dear Sir,\n\n{opener}\n\nRegards,\n{signature}")
                .replace("{opener}", opener)
                .replace("{signature}", self._signature()))
        draft = _ReminderDialog(subject, body, address, self, note=note,
                                cfg=self.cfg)
        draft.setWindowTitle(title)
        with self._timer_held():
            if draft.exec() != QDialog.Accepted:
                return give_up()
        self.status.setText(i18n.t("Sending…"))
        self.progress.setVisible(True)
        worker = SendWorker(
            email_config.cfg_for_sender(self.cfg, draft.sender()),
            [{"email": address, "name": row.get("Contact person", "")}],
            draft.subject(), draft.message(), list(files or []))
        self._send_worker = worker
        no = row.get("Inquiry no", "")
        subj, text = draft.subject(), draft.message()

        def done(sent, failed):
            self.progress.setVisible(False)
            self.status.setText("")
            if failed:
                give_up()
                self._explain(failed[0][1])
                return
            # The row itself while it is still loaded (a row with no number,
            # or a duplicated one, cannot be found again by number — review
            # R9); after a reload, by its number.
            rows_now = self._register_rows
            target = (row if any(row is r for r in rows_now)
                      else CB.get_register().find(rows_now, no) or row)
            self._log_sent(kind, target, subj, body=text)
            on_sent(target)

        def failed(message):
            self.progress.setVisible(False)
            self.status.setText("")
            give_up()
            self._explain(message)

        worker.done.connect(done)
        worker.failed.connect(failed)
        worker.start()
        return True

    # ── inquiry ───────────────────────────────────────────────────────────
    def _ask_details(self):
        row = self._selected_row()
        if not row:
            return
        q = inquiry_config.word(self.cfg, "quote").lower()

        def sent(target):
            CB.get_register().mark_asked_details(target)
            if self._save_and_log(target, i18n.t("Asked for details")):
                self.status.setText(i18n.t("Sent — waiting for their details."))
        self._letter(row, "Re: " + (row.get("Product asked") or ""),
                     i18n.t("Thank you for your enquiry. To prepare our {quote} "
                            "correctly, could you confirm the specification, "
                            "quantity and the delivery date you need?")
                     .replace("{quote}", q),
                     title=i18n.t("Ask for details"), kind="details",
                     on_sent=sent)

    def _chase_details(self):
        row = self._selected_row()
        if not row:
            return
        q = inquiry_config.word(self.cfg, "quote").lower()
        self._letter(row, "Re: " + (row.get("Product asked") or ""),
                     i18n.t("Following up on our question below — once we have "
                            "the details we will send our {quote} the same day.")
                     .replace("{quote}", q),
                     title=i18n.t("Remind them about the details"),
                     kind="details",
                     on_sent=lambda t: self.status.setText(i18n.t(
                         "Reminder sent to {who}.").replace(
                         "{who}", t.get("Email", ""))))

    def _got_po(self):
        """They sent a PO before any quotation: price it from the rate list."""
        row = self._selected_row()
        if not row:
            return
        CB.get_register().mark_po_without_quote(row)
        if self._save_and_log(row, i18n.t("Order with no quotation — to price")):
            self.status.setText(i18n.t(
                "{no} has an order with no quotation — price it from the rate "
                "list.").replace("{no}", row.get("Inquiry no", "")))

    # ── quoted / negotiation ──────────────────────────────────────────────
    def _they_countered(self):
        row = self._selected_row()
        if not row:
            return
        register = CB.get_register()
        tax, _pct = inquiry_config.tax_of(self.cfg)
        guess = row.get(register.THEIR_ASK, "")
        dlg = _AmountDialog(
            i18n.t("They countered"), i18n.t("What are they asking for?"),
            i18n.t("Their price, incl. {tax}").replace("{tax}", tax),
            guess, i18n.t("Save their price"), self)
        if dlg.exec() != QDialog.Accepted:
            return
        ask = dlg.amount()
        register.note_counter(row, ask if ask > 0 else None)
        note = dlg.note.text().strip()
        if note:
            row["Notes"] = (row.get("Notes", "") + " | " + note).strip(" |")
        if self._save_and_log(row, i18n.t("They countered"),
                              body=self._money(ask) if ask else ""):
            self.status.setText(i18n.t("{no} moved to {stage} — your turn.")
                                .replace("{no}", row.get("Inquiry no", ""))
                                .replace("{stage}", inquiry_config.stage_label(
                                    self.cfg, "nego")))

    def _hold_price(self):
        row = self._selected_row()
        if not row:
            return
        q = inquiry_config.word(self.cfg, "quote")
        value = self._money(row.get("Quotation value", ""))

        def sent(target):
            CB.get_register().hold_price(target)
            if self._save_and_log(target, i18n.t("Held the price")):
                self.status.setText(i18n.t("Sent — their turn now."))
        self._letter(row, f"Re: {q} {CB.get_register().quote_label(row)}",
                     i18n.t("Thank you. {value} is already our best price for "
                            "this quantity and specification.")
                     .replace("{value}", value),
                     title=i18n.t("Hold the price"), kind="hold", on_sent=sent)

    def _said_yes(self):
        row = self._selected_row()
        if not row:
            return
        CB.get_register().mark_reply(row, "accepted")
        po = inquiry_config.word(self.cfg, "po")
        if self._save_and_log(row, i18n.t("They said yes")):
            self.status.setText(i18n.t("Said yes — waiting for the {po}.")
                                .replace("{po}", po))

    def _update_from_reply(self):
        """"Prism thinks" → Update the register, from the drawer."""
        row = self._selected_row()
        if not row:
            return
        intent = (getattr(self, "_act_kw", {}) or {}).get("intent") or "unclear"
        no = row.get("Inquiry no", "")
        items = [i for i in getattr(self, "_replies", []) if i.inquiry_no == no]
        if items:
            self._apply_reply(item=items[-1], intent=intent)
            return
        if intent == "rejected":
            CB.get_register().mark_lost(row, i18n.t("Declined"))
        else:
            CB.get_register().mark_reply(row, intent)
        if self._save_and_log(row, i18n.t("Register updated by hand")):
            self.status.setText(i18n.t("{no} is now {status}.")
                                .replace("{no}", no)
                                .replace("{status}", i18n.t(row.get("Status", ""))))

    def _revise_quotation(self):
        """Same number, Rev n+1: a new total, the revised PDF named
        QTN-…-Rn.pdf, the letter, then register.revise_quotation()."""
        row = self._selected_row()
        if not row:
            return
        register = CB.get_register()
        if not (row.get("Quotation no") or "").strip():
            return self._prepare_quotation()
        q = inquiry_config.word(self.cfg, "quote")
        tax, _pct = inquiry_config.tax_of(self.cfg)
        # One above the register AND every -Rn file in the folder, so a
        # hand-edited Revision can never overwrite a revision the customer
        # already holds (review R6).
        rev = register.next_revision(row)
        old = register.money(row.get("Quotation value", "") or 0)
        ask = register.money(row.get(register.THEIR_ASK, "") or 0)
        # Their ask is read from mail text (or typed by hand); one that is
        # missing, or not a plausible counter to our total (a phone number,
        # a per-unit rate), must not move the suggestion: start from the
        # current total and let the owner type the new one.
        if not register.plausible_ask(ask, old):
            ask = 0
        suggest = (old + ask) / 2 if ask else old
        note = i18n.t("{label} was {old}{ask}. The revision keeps the same "
                      "number with Rev {n}, and the old price stays in the "
                      "history.").replace("{label}", register.quote_label(row)) \
            .replace("{old}", self._money(old)) \
            .replace("{ask}", ("; " + i18n.t("they asked for {v}").replace(
                "{v}", self._money(ask))) if ask else "") \
            .replace("{n}", str(rev))
        dlg = _AmountDialog(
            i18n.t("Send a revised {quote}").replace("{quote}", q.lower()), note,
            i18n.t("New total, incl. {tax}").replace("{tax}", tax),
            self._money(suggest), i18n.t("Send Rev {n}").replace("{n}", str(rev)),
            self)
        if dlg.exec() != QDialog.Accepted:
            return
        new_total = dlg.amount()
        if new_total <= 0:
            return
        staged, total = self._write_revision(row, rev, new_total)
        letter_note = ""
        if not staged:
            letter_note = i18n.t(
                "The first copy could not be read back from the folder, so no "
                "revised PDF is attached — the price is in the letter.")
        elif total != new_total:
            # The lines could not land on the typed figure to the paisa: the
            # letter and the register carry the PDF's own total, never a
            # figure the attachment contradicts (review R4).
            letter_note = i18n.t("The lines round to {value}, so the letter "
                                 "and the register use that figure.").replace(
                "{value}", self._money(total))

        def sent(target):
            self._promote_staged(staged)
            register.revise_quotation(target, total, revision=rev)
            if self._save_and_log(target, i18n.t("Revised quotation sent"),
                                  body=self._money(total)):
                self.status.setText(i18n.t("{label} sent — waiting for their "
                                           "answer.").replace(
                    "{label}", register.quote_label(target)))
        self._letter(
            row, f"{q} {row.get('Quotation no', '')} Rev {rev}",
            i18n.t("Please find our revised {quote} {no} Rev {n} attached: "
                   "{value} including {tax}.").replace("{quote}", q.lower())
            .replace("{no}", row.get("Quotation no", "")).replace("{n}", str(rev))
            .replace("{value}", self._money(total)).replace("{tax}", tax),
            title=i18n.t("Send a revised {quote}").replace("{quote}", q.lower()),
            kind="revised", on_sent=sent, files=[p for p, _final in staged[:1]],
            note=letter_note, on_failed=lambda: self._drop_staged(staged))

    def _write_revision(self, row: dict, rev: int,
                        new_total: Decimal) -> tuple[list, Decimal]:
        """The revised PDF/CSV, scaled from the latest copy the customer
        holds to exactly `new_total` (quoting.scale_to_total), written to a
        staging folder beside the first one — never over an existing file,
        and only moved into place once the letter has gone (review R6).
        Returns ([(staged path, final path), …] PDF first, the total the
        files carry). ([], new_total) when no copy can be read back (then
        the letter carries the price)."""
        import tempfile
        from addons.inquiry import documents
        from addons.inquiry.dialog import _read_sent_quotation
        register = CB.get_register()
        quoting = CB.get_quoting()
        quote = _read_sent_quotation(row)
        folder = row.get("Folder", "")
        if quote is None or not folder or not quote.total:
            return [], new_total
        quoting.scale_to_total(quote, new_total)
        total = quote.total
        number = row.get("Quotation no", "")
        quote.number = f"{number} Rev {rev}"
        quote.date = date.today()
        out = []
        try:
            stage = tempfile.mkdtemp(prefix=".prism-rev-", dir=folder)
            csv_name = register.quote_file_name(number, rev, "csv")
            pdf_name = register.quote_file_name(number, rev)
            quoting.write_csv(quote, os.path.join(stage, csv_name))
            pdf = documents.quotation_pdf(quote, self._settings(),
                                          os.path.join(stage, pdf_name))
            if pdf:
                out.append((pdf, os.path.join(folder, pdf_name)))
            out.append((os.path.join(stage, csv_name),
                        os.path.join(folder, csv_name)))
        except Exception as e:                          # noqa: BLE001
            self._drop_staged(out)
            self.status.setText(str(e))
            return [], new_total
        return out, total

    @staticmethod
    def _promote_staged(staged: list) -> None:
        """Move sent revision files into the folder. Never over an existing
        file: one already there is the copy a customer holds."""
        stuck = False
        for src, dest in staged:
            try:
                if os.path.exists(src) and not os.path.exists(dest):
                    os.replace(src, dest)
            except OSError:
                stuck = True    # Windows: a scanner holding the new PDF open
        if not stuck:
            PipelineActions._drop_staged(staged)
        # Otherwise the sent copy stays in its .prism-rev-* folder rather
        # than being deleted: it is the only file of what went out.

    @staticmethod
    def _drop_staged(staged: list) -> None:
        """Throw away revision files that were never sent, and their
        staging folder."""
        import shutil
        dirs = set()
        for src, _dest in staged:
            dirs.add(os.path.dirname(src))
            try:
                if os.path.exists(src):
                    os.remove(src)
            except OSError:
                pass
        for d in dirs:
            if os.path.basename(d).startswith(".prism-rev-"):
                shutil.rmtree(d, ignore_errors=True)

    def _money(self, value) -> str:
        """The figure in the client's currency. A cell that cannot be read
        as one amount is shown exactly as typed — a letter must never print
        a guessed price, nor a blank where a figure was (review R7)."""
        text = inquiry_config.money_of(self.cfg, value)
        if not text and value not in (None, ""):
            return str(value).strip()
        return text

    # ── PO received ───────────────────────────────────────────────────────
    def _order_item(self, row: dict):
        """The pending Order-came mail for this row, else a register-only
        stand-in — what _review_po/_remove_order take as item=."""
        from addons.inquiry.dialog import _RegisterOnlyItem, _StoredItem
        no = row.get("Inquiry no", "")
        for item in getattr(self, "_orders", []) or []:
            if getattr(item, "inquiry_no", "") == no:
                return item
        root = self._root()
        if root:
            try:
                wl = CB.get_worklist()
                for entry in wl.pending(wl.load(root), "orders"):
                    if entry.get("inquiry_no") == no:
                        return _StoredItem(entry, row)
            except Exception:                           # noqa: BLE001
                pass
        return _RegisterOnlyItem(row)

    def _read_po_for_row(self):
        row = self._selected_row()
        if row:
            self._review_po(item=self._order_item(row))

    def _not_an_order(self):
        row = self._selected_row()
        if not row:
            return
        item = self._order_item(row)
        if getattr(item, "message_id", ""):
            self._remove_order(item=item)
        register = CB.get_register()
        if (row.get(register.NO_QUOTATION) or "").strip():
            row[register.NO_QUOTATION] = ""
            row["Status"] = (register.QUOTED if row.get("Quotation no")
                             else register.NEW)
            self._save_and_log(row, i18n.t("Not an order — removed"))
        self.status.setText(i18n.t("Not an order — taken off {stage}.").replace(
            "{stage}", inquiry_config.stage_label(self.cfg, "po")))

    def _po_text(self, row: dict) -> str:
        item = self._order_item(row)
        message = getattr(item, "message", None)
        body = getattr(message, "body", "") if message is not None else ""
        try:
            path = self._po_file(item) if getattr(item, "files", None) is not None \
                else ""
            if path:
                body = CB.get_po().text_from(path) or body
        except Exception:                               # noqa: BLE001
            pass
        return body or row.get("Product asked", "")

    def _price_po(self):
        row = self._selected_row()
        if not row:
            return
        rate = self._settings().get("rate_list", "")
        if not rate or not os.path.exists(rate):
            self._explain(i18n.t("Pricing an order needs your rate list. Add "
                                 "it under Setup → Files."))
            return
        tax_label, pct = inquiry_config.tax_of(self.cfg)
        try:
            priced = CB.price_order_from_rate_list(
                self._po_text(row), rate, tax_percent=pct)
        except Exception as e:                          # noqa: BLE001
            self._explain(str(e))
            return
        po = inquiry_config.word(self.cfg, "po")
        dlg = _PricedOrderDialog(priced, self._money, tax_label, po, self)
        if dlg.exec() != QDialog.Accepted:
            return
        register = CB.get_register()
        quoting = CB.get_quoting()
        lines = "\n".join(f"  {l.description} — {l.quantity} {l.unit} × "
                          f"{self._money(l.rate)} = {self._money(l.amount)}"
                          for l in priced.lines)

        def sent(target):
            # The numbers_in_use floor, as _prepare_quotation and the
            # auto-quote use (review R10): a PDF still in a folder keeps its
            # number even when its row lost the Quotation no.
            try:
                taken = CB.get_mailflow().numbers_in_use(self._paths())
            except Exception:                           # noqa: BLE001
                taken = ()
            number = quoting.next_quote_number(self._register_rows, taken=taken)
            target["Quotation no"] = number
            target["Quotation date"] = date.today().strftime("%d-%m-%Y")
            target["Quotation value"] = register.money_str(priced.total)
            if self._save_and_log(target, i18n.t("Order acknowledgement sent"),
                                  body=self._money(priced.total)):
                self.status.setText(i18n.t("Acknowledgement sent — check the "
                                           "{po} once they confirm.")
                                    .replace("{po}", po))
        self._letter(
            row, i18n.t("Order acknowledgement — {po} {no}").replace("{po}", po)
            .replace("{no}", row.get("PO number", "")),
            i18n.t("Thank you for your {po}. We have priced it from our rate "
                   "list:\n\n{lines}\n\nTotal {total} including {tax}. Please "
                   "confirm and we will schedule the order.")
            .replace("{po}", po).replace("{lines}", lines)
            .replace("{total}", self._money(priced.total))
            .replace("{tax}", tax_label),
            title=i18n.t("Send the order acknowledgement"), kind="ack",
            on_sent=sent)

    def _chase_po(self):
        row = self._selected_row()
        if not row:
            return
        po = inquiry_config.word(self.cfg, "po")
        self._letter(row, f"Re: {CB.get_register().quote_label(row)}",
                     i18n.t("Thank you for confirming. Could you send the {po} "
                            "so we can schedule production?").replace("{po}", po),
                     title=i18n.t("Remind them for the {po}").replace("{po}", po),
                     kind="reminder",
                     on_sent=lambda t: self.status.setText(i18n.t(
                         "Reminder sent to {who}.").replace(
                         "{who}", t.get("Email", ""))))

    def _chase_advance(self):
        row = self._selected_row()
        if not row:
            return
        self._letter(row, i18n.t("Proforma for {po}").replace(
            "{po}", row.get("PO number", "")),
            i18n.t("A gentle reminder about the advance against our proforma "
                   "for {po}. We will schedule the order as soon as it "
                   "arrives.").replace("{po}", row.get("PO number", "")),
            title=i18n.t("Remind about the advance"), kind="reminder",
            on_sent=lambda t: self.status.setText(i18n.t(
                "Reminder sent to {who}.").replace("{who}", t.get("Email", ""))))

    def _advance_received(self):
        row = self._selected_row()
        if not row:
            return
        if not CB.get_register().mark_advance_received(row, self._pipeline()):
            return
        if self._save_and_log(row, i18n.t("Advance received — order confirmed")):
            self.status.setText(i18n.t("Advance received — order confirmed."))
            self._order_acknowledgement(row)

    def _after_po_accepted(self, target: dict, number: str) -> None:
        """Called at the end of _po_accepted. With the proforma step on, the
        order waits for the advance instead of being Won; with the
        acknowledgement step on, offer the acknowledgement letter."""
        p = self._pipeline()
        register = CB.get_register()
        if p["steps"].get("proforma"):
            # The order waits for the advance against a proforma. Nothing is
            # recorded as sent until the proforma letter has actually gone
            # (review R11): the row reads "Proforma to send" until then, and
            # the acknowledgement follows the advance (_advance_received),
            # as before.
            target["Result"] = ""
            if register.mark_proforma_due(target, p):
                if self._save_and_log(target, i18n.t("Order accepted — proforma "
                                                     "to send")):
                    self.status.setText(i18n.t("Order accepted — send the "
                                               "proforma."))
                self._send_proforma_for(target)
            return
        self._order_acknowledgement(target)

    def _send_proforma(self):
        row = self._selected_row()
        if row:
            self._send_proforma_for(row)

    def _send_proforma_for(self, row: dict) -> None:
        """The proforma letter, through the same letter window and send path
        as every other pipeline mail. The latest quotation PDF goes with it
        when there is one. mark_proforma_sent() only runs once it is sent."""
        register = CB.get_register()
        po = inquiry_config.word(self.cfg, "po")
        tax, _pct = inquiry_config.tax_of(self.cfg)
        value = self._money(row.get("Order value") or row.get("Quotation value", ""))
        folder = row.get("Folder", "")
        number = row.get("Quotation no", "")
        files = []
        if folder and number:
            latest = max(register.revision_of(row),
                         register.revision_on_disk(folder, number))
            for n in range(latest, -1, -1):
                path = os.path.join(folder, register.quote_file_name(number, n))
                if os.path.exists(path):
                    files.append(path)
                    break

        def sent(target):
            if register.mark_proforma_sent(target, self._pipeline()):
                if self._save_and_log(target, i18n.t(
                        "Proforma sent — waiting for the advance")):
                    self.status.setText(i18n.t(
                        "Proforma sent — waiting for the advance."))
        self._letter(
            row, i18n.t("Proforma for {po} {no}").replace("{po}", po)
            .replace("{no}", row.get("PO number", "")).strip(),
            i18n.t("Thank you for your {po} {no}. Our proforma for {value} "
                   "including {tax} is below; we will schedule the order as "
                   "soon as the advance arrives.")
            .replace("{po}", po).replace("{no}", row.get("PO number", ""))
            .replace("{value}", value).replace("{tax}", tax),
            title=i18n.t("Send the proforma"), kind="proforma", on_sent=sent,
            files=files,
            note=i18n.t("Prism does not make a separate proforma PDF; the "
                        "quotation is attached.") if files else "")

    def _order_acknowledgement(self, row: dict) -> None:
        if not self._pipeline()["steps"].get("acknowledgement"):
            return
        if not row.get("Email") or not email_config.can_send(self.cfg):
            return
        po = inquiry_config.word(self.cfg, "po")
        tax, _pct = inquiry_config.tax_of(self.cfg)
        value = self._money(row.get("Order value") or row.get("Quotation value", ""))
        self._letter(
            row, i18n.t("Order acknowledgement — {po} {no}").replace("{po}", po)
            .replace("{no}", row.get("PO number", "")),
            i18n.t("Thank you for your {po} {no}. We confirm the order for "
                   "{what}, {qty}, {value} including {tax}.")
            .replace("{po}", po).replace("{no}", row.get("PO number", ""))
            .replace("{what}", row.get("Product asked", ""))
            .replace("{qty}", row.get("Quantity", "")).replace("{value}", value)
            .replace("{tax}", tax),
            title=i18n.t("Send the order acknowledgement"), kind="ack",
            on_sent=lambda t: self.status.setText(i18n.t(
                "Order acknowledgement sent.")))

    # ── lost ──────────────────────────────────────────────────────────────
    def _reopen(self):
        row = self._selected_row()
        if not row:
            return
        register = CB.get_register()
        row["Status"] = register.QUOTED if row.get("Quotation no") else register.NEW
        row["Reason if lost"] = ""
        if (row.get("Result") or "") == register.NOT_CONVERTED:
            row["Result"] = ""
        if self._save_and_log(row, i18n.t("Reopened")):
            self.status.setText(i18n.t("{no} reopened.").replace(
                "{no}", row.get("Inquiry no", "")))

    # ── screen-level ──────────────────────────────────────────────────────
    def _save_rows_xlsx(self, rows: list[dict]):
        from addons.inquiry import documents
        if not rows:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, i18n.t("Save these as Excel"),
            os.path.join(self._root() or os.path.expanduser("~"),
                         documents.safe_name(i18n.t("Inquiries") + ".xlsx")),
            "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            documents.register_xlsx(rows, path)
        except Exception as e:                          # noqa: BLE001
            self._explain(str(e))
            return
        self.status.setText(i18n.t("Saved {name}.").replace(
            "{name}", os.path.basename(path)))

    def _add_inquiry_by_hand(self):
        if not self._root():
            QMessageBox.information(self, i18n.t("Email inquiry automation"),
                                    i18n.t("Set up a mailbox and a folder first."))
            return
        dlg = _AddInquiryDialog(inquiry_config.stage_label(self.cfg, "inquiry"),
                                self)
        if dlg.exec() != QDialog.Accepted:
            return
        register = CB.get_register()
        paths = self._paths()
        try:
            taken = CB.get_mailflow().numbers_in_use(paths)
        except Exception:                               # noqa: BLE001
            taken = ()
        rows = self._rows()
        no = register.next_number(rows, taken=taken)
        row = register.blank_row()
        row.update(dlg.values())
        now = date.today()
        row.update({"Inquiry no": no, "Date received": now.strftime("%d-%m-%Y"),
                    "Status": register.NEW,
                    "Folder": os.path.join(paths.inquiries, no.replace("/", "-"))})
        try:
            os.makedirs(row["Folder"], exist_ok=True)
        except OSError:
            pass
        self._register_rows.append(row)
        if self._save_and_log(row, i18n.t("Added by hand")):
            self.status.setText(i18n.t("{no} added.").replace("{no}", no))


# ── the three views, the board, the drawer, the sidebar ───────────────────
VIEWS = [("pipeline", "Pipeline"), ("client", "Client file"),
         ("mail", "All mail")]


class PipelineScreen:
    """The view switch around the existing tabs, mixed into InquiryDialog.
    Page 0 of `views` is the board; page 1 is the untouched `tabs`, shown
    without its tab bar for Client file / All mail and with it for the
    temporary "Classic tabs"."""

    def _build_views(self):
        from PySide6.QtWidgets import (
            QHBoxLayout, QMenu, QStackedWidget, QWidget,
        )
        from addons.inquiry import board as board_mod
        from addons.inquiry import dialog as UI
        from addons.inquiry.drawer import InquiryDrawer
        from widgets import controls as C
        import theme

        bar = QWidget()
        bar.setObjectName("inquiryViewBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACE_2)
        self.view_tabs = C.Tabs([i18n.t(label) for _k, label in VIEWS])
        self.view_tabs.changed.connect(
            lambda i: self.show_view(VIEWS[i][0]) if 0 <= i < len(VIEWS) else None)
        row.addWidget(self.view_tabs)
        self.board_range = QComboBox()
        for key, label in UI.REGISTER_RANGES:
            if key != "custom":
                self.board_range.addItem(i18n.t(label), key)
        self.board_range.setAccessibleName(i18n.t("Show"))
        row.addWidget(self.board_range)
        self.board_search = C.SearchField(i18n.t("Search inquiries…"))
        self.board_search.setMinimumWidth(
            self.board_search.fontMetrics().averageCharWidth() * 18)
        row.addWidget(self.board_search, 1)
        self.select_btn = C.button(i18n.t("Select"), "secondary",
                                   icon_name="check", small=True)
        self.select_btn.setCheckable(True)
        row.addWidget(self.select_btn)
        self.body.addWidget(bar)
        self.view_bar = bar

        self.views = QStackedWidget()
        self.views.setObjectName("inquiryViews")
        self.board = board_mod.BoardView(self)
        self.views.addWidget(self.board)
        self.views.addWidget(self.tabs)
        self.body.addWidget(self.views, stretch=1)
        self.board_range.currentIndexChanged.connect(
            lambda _i: self.board.set_range(self.board_range.currentData()))
        self.board_search.changed.connect(self.board.set_query)
        self.select_btn.toggled.connect(self.board.set_select_mode)
        self.board.card_opened.connect(self._open_card)
        self.board.show_client_file.connect(lambda: self.show_view("client"))

        self.drawer = InquiryDrawer(self)
        self.drawer.closed.connect(lambda: self.board.set_current(""))

        # Header: Add inquiry first, the ⋯ menu last.
        add = C.button(i18n.t("Add inquiry"), "secondary", icon_name="plus",
                       on_click=self._add_inquiry_by_hand)
        self.add_btn = add
        self.header.actions_row.insertWidget(0, add)
        more = C.icon_button("more-horizontal", i18n.t("More"))
        menu = QMenu(more)
        menu.addAction(i18n.t("Bring in an old list (CSV)…"),
                       self._import_csv_into_register)
        menu.addAction(i18n.t("Save as Excel…"), self._export_register_xlsx)
        menu.addAction(i18n.t("Open the folder"),
                       lambda: UI.open_in_file_manager(self._root()))
        menu.addAction(i18n.t("Open the register file"), self._open_register)
        menu.addSeparator()
        menu.addAction(i18n.t("Pipeline & wording…"), self._open_pipeline_setup)
        menu.addAction(i18n.t("Setup"), self.open_setup)
        menu.addSeparator()
        menu.addAction(i18n.t("Classic tabs"), lambda: self.show_view("classic"))
        more.clicked.connect(lambda: menu.exec(
            more.mapToGlobal(more.rect().bottomLeft())))
        self.more_menu = menu
        self.header.add_action(more)
        self._view = "pipeline"
        self._switching = False
        self._tabs_quiet = False
        self.tabs.currentChanged.connect(self._tab_followed)
        self._sidebar_auto = False
        self._sidebar_ours = False

    def _tab_followed(self, index: int):
        """A tab picked in code (a test, an old caller) is shown: the view
        that holds it comes forward. Prism's own landing after a check sets
        _tabs_quiet, so the board is never pulled away under the owner."""
        if self._switching or self._tabs_quiet or not 0 <= index < len(TABS):
            return
        key = TABS[index][0]
        want = {"register": "client", "arrived": "mail"}.get(key, "classic")
        if self._view == "pipeline" or (self._view != "classic"
                                        and want != self._view):
            self.show_view(want)

    def show_view(self, view: str):
        from inquiry_config import TAB_INDEX
        self._switching = True
        try:
            self._show_view(view, TAB_INDEX)
        finally:
            self._switching = False
        self._fit_sidebar()

    def _show_view(self, view: str, TAB_INDEX):
        self._view = view
        bar = self.tabs.tabBar()
        if view == "pipeline":
            self.views.setCurrentIndex(0)
        else:
            self.views.setCurrentIndex(1)
            if view == "client":
                self.tabs.setCurrentIndex(TAB_INDEX["register"])
            elif view == "mail":
                self.tabs.setCurrentIndex(TAB_INDEX["arrived"])
            bar.setVisible(view == "classic")
        if view == "pipeline":
            bar.setVisible(False)
        for search in (self.board_search, self.board_range, self.select_btn):
            search.setVisible(view == "pipeline")
        index = next((i for i, (k, _l) in enumerate(VIEWS) if k == view), -1)
        if index >= 0 and self.view_tabs.current() != index:
            self.view_tabs.set_current(index)
        if hasattr(self, "classic_footer"):
            self.classic_footer.setVisible(view == "classic")
        if view != "pipeline":
            self.drawer.close_drawer()

    def _render_board(self):
        board = getattr(self, "board", None)
        if board is None:
            return
        board.refresh()
        drawer = getattr(self, "drawer", None)
        if drawer is not None and drawer.isVisible():
            drawer.render()
            board.set_current(drawer.no)
            drawer.place()

    def _open_card(self, no: str):
        order = [n for n in self.board.cards]
        self.board.set_current(no)
        self.drawer.open_inquiry(no, order)

    def _open_pipeline_setup(self):
        from addons.inquiry.pipeline_setup import PipelineSetupDialog, apply
        dlg = PipelineSetupDialog(self.cfg, self)
        with self._timer_held():
            if dlg.exec() != QDialog.Accepted:
                return
        self.cfg = apply(self.cfg, dlg.pipeline())
        try:
            CB.config.save(self.cfg)
        except Exception as e:                          # noqa: BLE001
            self._explain(str(e))
            return
        self._render_board()
        try:
            from widgets import controls as C
            C.show_toast(self, i18n.t("Saved"),
                         i18n.t("The board uses your words now."))
        except Exception:                               # noqa: BLE001
            pass

    # ── the app sidebar on a narrow window ───────────────────────────────
    def _sidebar(self):
        win = self.window()
        return getattr(win, "sidebar", None) if win is not self else None

    def _needed_width(self) -> int:
        from addons.inquiry import board as board_mod
        import theme
        fm = self.fontMetrics()
        p = board_mod.pipeline(self.cfg)
        return board_mod.board_min_width(fm, p) + 2 * theme.PAGE_PAD + 260 + 24

    def _fit_sidebar(self):
        """Collapse the app sidebar to its icon rail when the board would not
        fit beside it; give the user's own choice back when it would, or
        when they leave this screen. A sidebar the user collapsed
        themselves is never expanded by this."""
        bar = self._sidebar()
        if bar is None or not hasattr(bar, "toggle_collapsed"):
            return
        self._watch_sidebar(bar)
        win = self.window()
        narrow = (self.isVisible() and getattr(self, "_view", "") == "pipeline"
                  and win.width() < self._needed_width())
        collapsed = bool(getattr(bar, "_collapsed", False))
        if narrow and not collapsed and not self._sidebar_auto:
            self._sidebar_ours = True
            bar.toggle_collapsed(True)
            self._sidebar_ours = False
            self._sidebar_auto = True
        elif not narrow and self._sidebar_auto:
            self._restore_sidebar()

    def _watch_sidebar(self, bar) -> None:
        """Listen for the user's own expand/collapse (review R16): once they
        toggle the sidebar themselves, the auto-collapse is no longer ours to
        undo, so leaving the screen or widening the window leaves it be."""
        if getattr(self, "_sidebar_watched", None) is bar:
            return
        signal = getattr(bar, "collapsed_toggled", None)
        if signal is None:
            return
        try:
            signal.connect(self._sidebar_toggled)
        except (RuntimeError, TypeError):
            return
        self._sidebar_watched = bar

    def _sidebar_toggled(self, _collapsed: bool) -> None:
        if not self._sidebar_ours:
            self._sidebar_auto = False

    def _restore_sidebar(self):
        bar = self._sidebar()
        if bar is not None and self._sidebar_auto and getattr(
                bar, "_collapsed", False):
            self._sidebar_ours = True
            bar.toggle_collapsed(False)
            self._sidebar_ours = False
        self._sidebar_auto = False
