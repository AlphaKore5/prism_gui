"""Bring contacts in from a spreadsheet, or take them out again.

The window shows the file before anything is imported — its first rows, and whether it has the one
column that is required (a mobile number) — so a wrong file is caught on screen, not in a report.

It also insists on the question of consent. WhatsApp will restrict a business whose messages people
did not ask for, so a list may only be messaged if the owner says — and records where — the people
agreed. Leave that box empty and the people are still saved (and can message you first), but no
campaign will reach them.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
                               QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.workers import PlatformWorker
from dialogs.base import PrismDialog
from widgets import controls as C

MAX_BYTES = 8 * 1024 * 1024
PREVIEW_ROWS = 5
PREVIEW_COLS = 6

# The headers the importer recognises (prism-wa's contacts.py has the same lists; this is only for showing the
# owner, before they import, whether the file will be understood).
MOBILE_HEADERS = {"mobile", "mobile number", "phone", "phone number", "whatsapp", "whatsapp number",
                  "number", "contact number", "mobileno", "mobile no"}
NAME_HEADERS = {"name", "full name", "customer name", "contact name", "fullname"}
EMAIL_HEADERS = {"email", "email address", "e-mail"}
TAG_HEADERS = {"tags", "tag"}
OPT_IN_HEADERS = {"opt in", "opt_in", "optin", "consent"}
SOURCE_HEADERS = {"source", "lead source", "origin"}


def guess_role(header: str) -> str:
    """What a column is most likely to be, by its heading (the same lists prism-wa reads without being told)."""
    h = header.strip().lower()
    for role, names in (("name", NAME_HEADERS), ("mobile", MOBILE_HEADERS), ("email", EMAIL_HEADERS), ("tags", TAG_HEADERS),
                        ("opt_in", OPT_IN_HEADERS), ("source", SOURCE_HEADERS)):
        if h in names:
            return role
    return "attr" if h else "ignore"


def attribute_key(header: str) -> str:
    """The detail name a column becomes: letters, numbers and underscores, starting with a letter."""
    key = re.sub(r"[^A-Za-z0-9_]+", "_", header.strip()).strip("_")
    return key if re.match(r"^[A-Za-z][A-Za-z0-9_]{0,39}$", key) else ""


def column_roles() -> list:
    return [("name", i18n.t("Name")), ("mobile", i18n.t("Mobile number")), ("email", i18n.t("Email")), ("tags", i18n.t("Tags")),
            ("source", i18n.t("Source")), ("opt_in", i18n.t("Agreed to messages")), ("attr", i18n.t("A detail (keep it as an attribute)")),
            ("ignore", i18n.t("Skip this column"))]


def mapping_for(headers: list, roles: dict) -> dict:
    """{header: role} in the form prism-wa takes: attr becomes `attr:<Key>`; a heading with no usable key is skipped."""
    out = {}
    for h in headers:
        role = roles.get(h, guess_role(h))
        if role == "attr":
            key = attribute_key(h)
            out[h] = "attr:" + key if key else "ignore"
        else:
            out[h] = role
    return out

SAMPLE_CSV = ("Name,Mobile,Email,Tags,City\n"
              "Asha Patel,9812345678,asha@example.com,vip|builder,Vadodara\n"
              "Ravi Shah,9898989898,,architect,Surat\n")


def decode_text(raw: bytes) -> str:
    """Bytes as text, whatever Excel or Notepad saved them as. UTF-16 is only believed when the file says so with its marker
    — without one, almost any even run of bytes decodes as UTF-16, as nonsense."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_csv_text(path: str) -> str:
    """The file as text, whatever Excel saved it as."""
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError(i18n.t("That file is larger than 8 MB. Split it into smaller files and import them one by one."))
    return decode_text(raw)


def glance(text: str) -> tuple:
    """(row count, header names) for the file chosen — enough to see it is the right one."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return 0, []
    return max(len(rows) - 1, 0), [h.strip() for h in rows[0] if h.strip()]


def first_rows(text: str, count: int = PREVIEW_ROWS) -> list:
    """The header and the first few rows, each cut to the columns that fit on screen."""
    out = []
    for i, row in enumerate(csv.reader(io.StringIO(text))):
        out.append([c.strip() for c in row[:PREVIEW_COLS]])
        if i >= count:
            break
    return out


def has_mobile_column(headers: list) -> bool:
    return any(h.strip().lower() in MOBILE_HEADERS for h in headers)


def headers_of(text: str) -> list:
    rows = list(csv.reader(io.StringIO(text), strict=False))
    return [h.strip() for h in rows[0]] if rows else []


class ImportContactsDialog(PrismDialog):
    def __init__(self, parent=None):
        super().__init__(i18n.t("Import contacts"),
                         i18n.t("From a spreadsheet saved as CSV. It needs a Mobile column; Name, Email and Tags are used when present, "
                                "and any other column becomes a detail you can put in a message."),
                         icon="upload", parent=parent, scrollable=True)
        self._text = ""
        self._path = ""
        self._busy = False
        self._done = False
        self._combos: dict = {}
        self.setAcceptDrops(True)

        self.form = QWidget()                      # everything to fill in; a finished import replaces it with the report
        form = QVBoxLayout(self.form)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(theme.CARD_GAP)
        self.body.addWidget(self.form)

        self.drop = QFrame()
        self.drop.setObjectName("waDrop")
        self.drop.setAttribute(Qt.WA_StyledBackground, True)
        self.drop.setStyleSheet(
            f"#waDrop {{ background: {theme.NEUTRAL[100]}; border: 1px dashed {theme.NEUTRAL[300]};"
            f" border-radius: {theme.R_CONTROL}px; }}")
        dl = QVBoxLayout(self.drop)
        dl.setContentsMargins(theme.SPACE_4, theme.SPACE_4, theme.SPACE_4, theme.SPACE_4)
        dl.setSpacing(theme.SPACE_2)
        self.file_label = C.label(i18n.t("Drop a CSV file here"), level="SUPPORT", weight=700, wrap=True)
        dl.addWidget(self.file_label)
        self.glance = C.label(i18n.t("or choose one from your computer."), level="META", colour=theme.NEUTRAL[600], wrap=True)
        dl.addWidget(self.glance)
        pick = QHBoxLayout()
        pick.setSpacing(theme.SPACE_2)
        pick.addWidget(C.button(i18n.t("Choose file…"), "secondary", on_click=self._choose))
        pick.addWidget(C.button(i18n.t("Download a sample file"), "tertiary", on_click=self._save_sample))
        pick.addStretch(1)
        dl.addLayout(pick)
        form.addWidget(self.drop)

        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setFixedHeight(190)
        self.table.setAccessibleName(i18n.t("The first rows of the file"))
        self.table.hide()
        form.addWidget(self.table)
        self.problem = C.label("", level="SUPPORT", colour=theme.ERR_INK, wrap=True)
        self.problem.hide()
        form.addWidget(self.problem)

        self.columns_box = QWidget()
        cl = QVBoxLayout(self.columns_box)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(theme.SPACE_2)
        cl.addWidget(C.label(i18n.t("What is in each column?").upper(), level="LABEL", colour=theme.NEUTRAL[500]))
        cl.addWidget(C.label(i18n.t("We guessed from the headings. Change any that are wrong — nothing is saved until you choose Import."),
                             level="META", colour=theme.NEUTRAL[600], wrap=True))
        self.columns_form = QVBoxLayout()
        self.columns_form.setSpacing(theme.SPACE_2)
        cl.addLayout(self.columns_form)
        self.columns_box.hide()
        form.addWidget(self.columns_box)

        form.addWidget(C.label(i18n.t("Tags to add to everyone (optional)").upper(), level="LABEL", colour=theme.NEUTRAL[500]))
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText(i18n.t("e.g. diwali-list, builders"))
        self.tags_edit.setMinimumHeight(38)
        self.tags_edit.setAccessibleName(i18n.t("Tags to add to everyone"))
        form.addWidget(self.tags_edit)

        self.attest = QCheckBox(i18n.t("These people agreed to get WhatsApp messages from my business"))
        self.attest.toggled.connect(self._attest_changed)
        form.addWidget(self.attest)
        self.attest_help = C.label(
            i18n.t("Tick this only if it is true — Meta restricts accounts people report. If you leave it empty, they are saved "
                   "but no campaign will reach them until they message you or agree."),
            level="META", colour=theme.NEUTRAL[600], wrap=True)
        form.addWidget(self.attest_help)
        self.evidence_edit = QLineEdit()
        self.evidence_edit.setPlaceholderText(i18n.t("Where did they agree? e.g. enquiry form, shop counter, site visit register"))
        self.evidence_edit.setMinimumHeight(38)
        self.evidence_edit.setAccessibleName(i18n.t("Where they agreed"))
        self.evidence_edit.setEnabled(False)
        form.addWidget(self.evidence_edit)

        self.result = QVBoxLayout()
        self.result.setSpacing(theme.SPACE_2)
        self.body.addLayout(self.result)
        self.error = C.label("", level="SUPPORT", colour=theme.ERR_INK, wrap=True)
        self.error.hide()
        self.body.addWidget(self.error)
        self.body.addStretch(1)

        self.go = self.button(i18n.t("Import"), "primary", on_click=self._go)
        self.go.setEnabled(False)
        self.cancel = self.button(i18n.t("Cancel"), on_click=self.reject)
        self.footer.add_secondary(self.cancel)
        self.footer.set_primary(self.go)
        self.resize(680, 760)

    # ── choosing ─────────────────────────────────────────────────────────────
    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, i18n.t("Choose a CSV file"), "", i18n.t("CSV files (*.csv);;All files (*)"))
        if path:
            self.load(path)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(u.toLocalFile().lower().endswith((".csv", ".txt")) for u in urls):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for u in event.mimeData().urls():
            if u.toLocalFile().lower().endswith((".csv", ".txt")):
                self.load(u.toLocalFile())
                break

    def _save_sample(self):
        path, _ = QFileDialog.getSaveFileName(self, i18n.t("Save a sample file"), "sample-contacts.csv", i18n.t("CSV files (*.csv)"))
        if path:
            try:
                Path(path).write_text(SAMPLE_CSV, encoding="utf-8-sig", newline="")
            except OSError as e:
                self._fail(str(e))

    def load(self, path: str):
        try:
            self._text = read_csv_text(path)
        except (OSError, ValueError) as e:
            self._text = ""
            self._fail(str(e))
            self._update()
            return
        self.error.hide()
        self._path = path
        rows, header = glance(self._text)
        self.file_label.setText(Path(path).name)
        self.glance.setText(i18n.t("{n} rows").format(n=rows))
        self._fill_table(first_rows(self._text))
        self._fill_columns(headers_of(self._text))
        if not header:
            self._problem(i18n.t("That file is empty."))
        else:
            self._check_mobile()
        self._update()

    def _fill_columns(self, headers: list):
        ui.clear(self.columns_form)
        self._combos = {}
        for h in headers:
            if not h:
                continue
            row = QHBoxLayout()
            row.addWidget(C.label(h, level="SUPPORT", weight=600), stretch=1)
            box = QComboBox()
            box.setMinimumHeight(34)
            box.setMinimumWidth(240)
            box.setAccessibleName(i18n.t("What column {c} holds").format(c=h))
            for value, label in column_roles():
                box.addItem(label, value)
            box.setCurrentIndex(max(box.findData(guess_role(h)), 0))
            box.currentIndexChanged.connect(lambda _i: (self._check_mobile(), self._update()))
            self._combos[h] = box
            row.addWidget(box)
            holder = QWidget()
            holder.setLayout(row)
            self.columns_form.addWidget(holder)
        self.columns_box.setVisible(bool(self._combos))

    def roles(self) -> dict:
        return {h: box.currentData() for h, box in self._combos.items()}

    def _check_mobile(self):
        if any(r == "mobile" for r in self.roles().values()):
            self.problem.hide()
        else:
            self._problem(i18n.t("None of the columns is marked as the mobile number. Choose which one holds the numbers."))

    def _fill_table(self, rows: list):
        self.table.clear()
        if not rows:
            self.table.hide()
            return
        head, body = rows[0], rows[1:]
        self.table.setColumnCount(len(head))
        self.table.setRowCount(len(body))
        self.table.setHorizontalHeaderLabels(head)
        for r, row in enumerate(body):
            for c, cell in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(cell))
        self.table.show()

    def _problem(self, text: str):
        self.problem.setText(text)
        self.problem.show()

    def _attest_changed(self, on: bool):
        self.evidence_edit.setEnabled(on)

    def _update(self):
        ready = bool(self._text.strip()) and self.problem.isHidden() and not self._busy and not self._done
        self.go.setEnabled(ready)

    def _fail(self, message: str):
        self.error.setText(message)
        self.error.show()

    # ── importing ────────────────────────────────────────────────────────────
    def payload(self) -> dict:
        data = {"csv": self._text, "source": "IMPORT", "attest_consent": self.attest.isChecked(), "file_name": Path(self._path).name if self._path else "",
                "mapping": mapping_for(list(self._combos), self.roles()),
                "evidence": self.evidence_edit.text().strip() if self.attest.isChecked() else ""}
        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        if tags:
            data["tags"] = tags
        return data

    def _go(self):
        if self._busy:
            return
        if self.attest.isChecked() and not self.evidence_edit.text().strip():
            self._fail(i18n.t("Say where they agreed — it is kept as your record if anyone asks."))
            self.evidence_edit.setFocus()
            return
        self._busy = True
        self.error.hide()
        self.go.setText(i18n.t("Importing…"))
        self._update()
        w = PlatformWorker("contacts/import", self.payload())
        w.done.connect(self._imported)
        w.failed.connect(self._failed)
        self._w = w
        w.start()

    def _failed(self, message: str, _detail: dict):
        self._busy = False
        self.go.setText(i18n.t("Import"))
        self._fail(message)
        self._update()

    def _imported(self, reply: dict):
        self._busy = False
        self._done = True
        rep = reply.get("report") or {}
        lines = [(i18n.t("Added"), rep.get("created", 0)), (i18n.t("Updated"), rep.get("updated", 0)),
                 (i18n.t("Skipped — not valid"), rep.get("invalid", 0)),
                 (i18n.t("Marked as having agreed"), rep.get("consent_recorded", 0)),
                 (i18n.t("Kept opted out"), rep.get("kept_opted_out", 0))]
        self.form.hide()
        added = int(rep.get("created", 0)) + int(rep.get("updated", 0))
        self.result.addWidget(C.label(i18n.t("Imported {n} contacts").format(n=added) if added != 1 else i18n.t("Imported 1 contact"),
                                      level="CARD_TITLE", colour=theme.OK_INK if added else theme.WARN_INK))
        for left, right in lines:
            row = QHBoxLayout()
            row.addWidget(C.label(left, level="SUPPORT"), stretch=1)
            row.addWidget(C.label(str(right), level="SUPPORT", weight=700))
            box = QWidget()
            box.setLayout(row)
            self.result.addWidget(box)
        for e in (rep.get("errors") or [])[:10]:
            self.result.addWidget(C.label(i18n.t("Row {r}: {e}").format(r=e.get("row"), e=e.get("error")),
                                          level="META", colour=theme.ERR_INK, wrap=True))
        for w_ in rep.get("warnings") or []:
            self.result.addWidget(C.label(str(w_), level="META", colour=theme.WARN_INK, wrap=True))
        self.columns_box.hide()
        self.go.setText(i18n.t("Done"))
        self.go.setEnabled(True)
        self.go.clicked.disconnect()
        self.go.clicked.connect(self.accept)
        self.cancel.hide()
        self.setProperty("report", rep)


def export_contacts(parent, tags=None, target: dict | None = None):
    """Ask the server for the list (everyone, some tags, or `target`: selected ids / a filter) and offer it as a file. Fire and forget."""
    data = dict(target or {})
    if tags:
        data["tags"] = list(tags)
    w = PlatformWorker("contacts/export", data)

    def got(reply: dict):
        path, _ = QFileDialog.getSaveFileName(parent, i18n.t("Save contacts"), "contacts.csv", i18n.t("CSV files (*.csv)"))
        if not path:
            return
        try:
            Path(path).write_text(reply.get("csv", ""), encoding="utf-8-sig", newline="")
        except OSError as e:
            QMessageBox.warning(parent, i18n.t("Couldn't save"), str(e))
            return
        C.show_toast(parent, i18n.t("Contacts saved"), Path(path).name)

    w.done.connect(got)
    w.failed.connect(lambda m, _d: QMessageBox.warning(parent, i18n.t("Couldn't export"), m))
    parent._export_worker = w
    w.start()
    return w
