"""Choose one person from the contact book: type a name or number, pick from what is found.

Used wherever a screen needs "which customer": a new order, sending a product or a form to a chat. The search runs a moment after typing stops (or at once through
`search_now()`); nothing is chosen until the person picks from the list, and `contact_id()` is empty until then.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QComboBox, QLineEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from widgets import controls as C


class ContactChoice(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_1)
        self.search = QLineEdit()
        self.search.setMinimumHeight(38)
        self.search.setPlaceholderText(i18n.t("Type a name or a number"))
        self.search.setAccessibleName(i18n.t("Find a customer"))
        self.search.textEdited.connect(self._typed)
        col.addWidget(self.search)
        self.results = QComboBox()
        self.results.setMinimumHeight(38)
        self.results.setAccessibleName(i18n.t("Customer"))
        self.results.currentIndexChanged.connect(lambda _i: self.changed.emit())
        col.addWidget(self.results)
        self.note = ui.note()
        col.addWidget(self.note)
        self._calls = []
        self._token = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.search_now)
        self._reset()

    def say(self, message: str, error: bool = False):
        self.note.set(message, "error" if error else "quiet")

    def _reset(self):
        self.results.clear()
        self.results.addItem(i18n.t("— nobody chosen —"), None)

    def _typed(self, _text: str):
        self._timer.start()

    def search_now(self):
        text = self.search.text().strip()
        self._token += 1
        token = self._token
        if len(text) < 2:
            self._reset()
            self.note.clear_note()
            self.changed.emit()
            return
        ui.call(self, "contacts/list", {"search": text, "limit": 20}, done=lambda r, t=token: self._found(t, r), failed=lambda m, _d, t=token: self._failed(t, m))

    def _failed(self, token: int, message: str):
        if token == self._token:
            self.note.error(message)

    def _found(self, token: int, reply: dict):
        if token != self._token:
            return
        rows = list(reply.get("contacts") or [])
        self._reset()
        for c in rows:
            self.results.addItem("%s  ·  %s" % (c.get("name") or i18n.t("No name"), c.get("phone") or ""), {"id": c["id"], "name": c.get("name") or "", "phone": c.get("phone") or ""})
        if rows:
            self.results.setCurrentIndex(1)
            self.note.clear_note()
        else:
            self.note.set(i18n.t("Nobody found. Add them in Contacts first."), "quiet")
        self.changed.emit()

    def chosen(self) -> dict:
        return self.results.currentData() or {}

    def contact_id(self) -> str:
        return self.chosen().get("id") or ""

    def contact_name(self) -> str:
        return self.chosen().get("name") or ""

    def set_contact(self, contact_id: str, name: str = ""):
        self._reset()
        self.results.addItem(name or contact_id, {"id": contact_id, "name": name, "phone": ""})
        self.results.setCurrentIndex(1)
        self.search.setText(name)
