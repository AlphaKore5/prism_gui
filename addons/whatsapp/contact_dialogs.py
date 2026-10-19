"""Small windows of the Contacts tab: add one person, edit one, tag many at once, look back at past imports.

Each calls the platform itself (ui.call) and closes only when the server accepted the change, so a dialog that closed
means the change is saved.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QCompleter, QFileDialog, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from dialogs.base import PrismDialog
from widgets import controls as C


def _line(hint: str = "", text: str = "") -> QLineEdit:
    e = QLineEdit(text)
    e.setMinimumHeight(38)
    e.setPlaceholderText(hint)
    return e


def _words(text: str) -> list:
    return [w.strip() for w in (text or "").split(",") if w.strip()]


def _tag_line(hint: str, names) -> QLineEdit:
    e = _line(hint)
    if names:
        comp = QCompleter(list(names), e)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        e.setCompleter(comp)
    return e


class AddContactDialog(PrismDialog):
    def __init__(self, tag_names=(), attributes=(), parent=None):
        super().__init__(i18n.t("Add a contact"), i18n.t("One person, without a spreadsheet."), icon="user", parent=parent, scrollable=True)
        self.created = None
        self.name = _line(i18n.t("Their name"))
        self.phone = _line(i18n.t("With country code, e.g. 919812345678"))
        self.email = _line(i18n.t("Optional"))
        self.tags = _tag_line(i18n.t("Optional — separate several with commas"), tag_names)
        self.body.addWidget(ui.field(i18n.t("Name"), self.name))
        self.body.addWidget(ui.field(i18n.t("Mobile number"), self.phone))
        self.body.addWidget(ui.field(i18n.t("Email"), self.email))
        self.body.addWidget(ui.field(i18n.t("Tags"), self.tags))
        self.attr_edits = {}
        for a in attributes:
            if a.get("global"):
                continue
            e = _line(i18n.t("Optional"))
            self.attr_edits[a["key"]] = e
            self.body.addWidget(ui.field(a["key"], e))
        self.attest = QCheckBox(i18n.t("This person agreed to get WhatsApp messages from my business"))
        self.body.addWidget(self.attest)
        self.evidence = _line(i18n.t("Where did they agree? e.g. shop counter, enquiry form"))
        self.evidence.setEnabled(False)
        self.attest.toggled.connect(self.evidence.setEnabled)
        self.body.addWidget(self.evidence)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.save_btn = self.button(i18n.t("Add contact"), "primary", on_click=self._save)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.save_btn)
        self.resize(560, 640)

    def payload(self) -> dict:
        data = {"name": self.name.text().strip(), "phone": self.phone.text().strip(), "email": self.email.text().strip(),
                "tags": _words(self.tags.text()), "attributes": {k: e.text().strip() for k, e in self.attr_edits.items() if e.text().strip()},
                "attest_consent": self.attest.isChecked(), "evidence": self.evidence.text().strip() if self.attest.isChecked() else ""}
        return data

    def _save(self):
        d = self.payload()
        if not d["phone"]:
            self.error.error(i18n.t("Enter their mobile number."))
            return
        if d["attest_consent"] and not d["evidence"]:
            self.error.error(i18n.t("Say where they agreed — it is kept as your record if anyone asks."))
            return
        self.save_btn.setEnabled(False)
        self.error.clear_note()
        ui.call(self, "contacts/create", d, done=self._done, failed=self._failed)

    def _failed(self, message: str, _detail: dict):
        self.save_btn.setEnabled(True)
        self.error.error(message)

    def _done(self, reply: dict):
        self.created = reply
        self.accept()


class EditContactDialog(PrismDialog):
    def __init__(self, contact: dict, attributes=(), parent=None):
        super().__init__(i18n.t("Edit contact"), contact.get("name") or contact.get("phone") or "", icon="pencil", parent=parent, scrollable=True)
        self.contact = contact
        self.name = _line("", contact.get("name") or "")
        self.email = _line("", contact.get("email") or "")
        self.company = _line("", contact.get("company") or "")
        self.body.addWidget(ui.field(i18n.t("Name"), self.name))
        self.body.addWidget(ui.field(i18n.t("Email"), self.email))
        self.body.addWidget(ui.field(i18n.t("Company"), self.company))
        self.attr_edits = {}
        have = contact.get("attrs") or {}
        for a in attributes:
            if a.get("global"):
                continue
            e = _line(i18n.t("empty"), "" if have.get(a["key"]) is None else str(have.get(a["key"])))
            self.attr_edits[a["key"]] = e
            self.body.addWidget(ui.field(a["key"], e, i18n.t("Leave empty to clear it.") if a is attributes[0] else ""))
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.save_btn = self.button(i18n.t("Save"), "primary", on_click=self._save)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.save_btn)
        self.resize(520, 560)

    def changes(self) -> dict:
        have = self.contact.get("attrs") or {}
        attrs = {k: e.text().strip() for k, e in self.attr_edits.items() if e.text().strip() != ("" if have.get(k) is None else str(have.get(k)))}
        return {"name": self.name.text().strip(), "email": self.email.text().strip(), "company": self.company.text().strip(), "attributes": attrs}

    def _save(self):
        ch = self.changes()
        if not ch["name"]:
            self.error.error(i18n.t("A contact needs a name."))
            return
        self.save_btn.setEnabled(False)
        ui.call(self, "contacts/update", {"contact_id": self.contact.get("id"), "changes": ch}, done=lambda _r: self.accept(),
                failed=lambda m, _d: (self.save_btn.setEnabled(True), self.error.error(m)))


class ManageTagsDialog(PrismDialog):
    """Add and remove tags for everyone selected — or everyone matching the filter."""

    def __init__(self, target: dict, count: int, tag_names=(), parent=None):
        super().__init__(i18n.t("Manage tags"), (i18n.t("For {n} people.") if count != 1 else i18n.t("For 1 person.")).format(n=count),
                         icon="list-plus", parent=parent)
        self.target = dict(target)
        self.add = _tag_line(i18n.t("Tags to add — separate several with commas"), tag_names)
        self.remove = _tag_line(i18n.t("Tags to take off — separate several with commas"), tag_names)
        self.body.addWidget(ui.field(i18n.t("Add"), self.add))
        self.body.addWidget(ui.field(i18n.t("Remove"), self.remove))
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.go = self.button(i18n.t("Apply"), "primary", on_click=self._go)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.go)
        self.resize(520, 380)

    def _go(self):
        add, remove = _words(self.add.text()), _words(self.remove.text())
        if not (add or remove):
            self.error.error(i18n.t("Type at least one tag to add or remove."))
            return
        self.go.setEnabled(False)
        ui.call(self, "contacts/tags/set", dict(self.target, add=add, remove=remove), done=lambda _r: self.accept(),
                failed=lambda m, _d: (self.go.setEnabled(True), self.error.error(m)))


class ImportHistoryDialog(PrismDialog):
    def __init__(self, parent=None):
        super().__init__(i18n.t("Import history"), i18n.t("Every file you have imported, and the rows that did not make it."),
                         icon="upload", parent=parent, scrollable=True)
        self.list = QVBoxLayout()
        self.list.setSpacing(theme.SPACE_2)
        self.body.addLayout(self.list)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.set_primary(self.button(i18n.t("Close"), "primary", on_click=self.reject))
        self.resize(640, 520)
        self.list.addWidget(C.label(i18n.t("Loading…"), level="SUPPORT", colour=theme.NEUTRAL[600]))
        ui.call(self, "contacts/imports", {}, done=self._loaded, failed=lambda m, _d: (ui.clear(self.list), self.error.error(m)))

    def _loaded(self, reply: dict):
        ui.clear(self.list)
        items = reply.get("imports") or []
        if not items:
            self.list.addWidget(C.label(i18n.t("No imports yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
            return
        for it in items:
            card, col = ui.card("", "")
            row = QHBoxLayout()
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(C.label(it.get("file_name") or i18n.t("A pasted list"), level="SUPPORT", weight=700))
            summary = i18n.t("{c} added · {u} updated · {i} did not import").format(c=it.get("created", 0), u=it.get("updated", 0), i=it.get("invalid", 0))
            text.addWidget(C.label("%s  ·  %s" % (summary, str(it.get("at") or "")[:16].replace("T", " ")), level="META", colour=theme.NEUTRAL[600]))
            row.addLayout(text, stretch=1)
            if int(it.get("invalid") or 0):
                row.addWidget(C.button(i18n.t("Download the rows that failed"), "secondary", small=True,
                                       on_click=lambda _=False, i=it: self._download(i)))
            col.addLayout(row)
            self.list.addWidget(card)

    def _download(self, item: dict):
        ui.call(self, "contacts/imports/get", {"import_id": item.get("id")}, done=lambda r, i=item: self._save(r, i),
                failed=lambda m, _d: self.error.error(m))

    def _save(self, reply: dict, item: dict):
        stem = Path(item.get("file_name") or "import").stem
        path, _ = QFileDialog.getSaveFileName(self, i18n.t("Save the rows that failed"), "%s-failed.csv" % stem, i18n.t("CSV files (*.csv)"))
        if not path:
            return
        try:
            Path(path).write_text(reply.get("failures_csv", ""), encoding="utf-8-sig", newline="")
        except OSError as e:
            self.error.error(str(e))
            return
        C.show_toast(self, i18n.t("Saved"), Path(path).name)
