"""A link and a QR code that start a flow.

A flow that starts on a keyword starts when a customer sends that word. This puts the word in a WhatsApp chat link
(https://wa.me/<number>?text=<word>) and a QR code, so a signboard, a visiting card or an Instagram bio can start the flow with one tap. Nothing here
needs Meta's approval: a chat link is only a web address. The number is the one connected in Connection.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit

import i18n
from addons.whatsapp import qr, ui
from addons.whatsapp.settings_acquire import chat_link, qr_pixmap
from dialogs.base import PrismDialog
from widgets import controls as C


class FlowLinkDialog(PrismDialog):
    def __init__(self, keywords: list, parent=None):
        super().__init__(i18n.t("Link and QR code for this flow"), i18n.t("Whoever opens the link or scans the code starts a chat with your first message already typed."),
                         icon="link", parent=parent)
        self._numbers: list = []
        self._link = ""
        self.word = QComboBox()
        self.word.setMinimumHeight(38)
        for k in keywords or []:
            self.word.addItem(k, k)
        self.word.currentIndexChanged.connect(lambda _i: self._rebuild())
        self.body.addWidget(ui.field(i18n.t("The word they send"), self.word, i18n.t("The flow starts when this is the customer's first message.")))
        self.number = QComboBox()
        self.number.setMinimumHeight(38)
        self.number.currentIndexChanged.connect(lambda _i: self._rebuild())
        self.body.addWidget(ui.field(i18n.t("Number"), self.number))
        self.link_edit = QLineEdit()
        self.link_edit.setReadOnly(True)
        self.link_edit.setMinimumHeight(38)
        self.body.addWidget(ui.field(i18n.t("Link"), self.link_edit))
        row = QHBoxLayout()
        self.copy_btn = C.button(i18n.t("Copy the link"), "secondary", "copy", small=True, on_click=lambda: ui.copy_text(self, self._link, i18n.t("the link")))
        row.addWidget(self.copy_btn)
        self.save_btn = C.button(i18n.t("Save QR as picture"), "secondary", "download", small=True, on_click=self._save)
        row.addWidget(self.save_btn)
        row.addStretch(1)
        self.body.addLayout(row)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumHeight(230)
        self.body.addWidget(self.qr_label)
        self.note = ui.note()
        self.body.addWidget(self.note)
        self.body.addStretch(1)
        self.footer.set_primary(self.button(i18n.t("Done"), "primary", on_click=self.accept))
        self.resize(480, 600)
        self._rebuild()
        ui.call(self, "numbers/list", {}, done=self._loaded, failed=lambda m, _d: self.note.error(m))

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def _loaded(self, reply: dict):
        self._numbers = list(reply.get("numbers") or [])
        self.number.blockSignals(True)
        self.number.clear()
        for n in self._numbers:
            self.number.addItem(str(n.get("display") or i18n.t("A WhatsApp number")), n.get("display"))
        self.number.blockSignals(False)
        if not self._numbers:
            self.note.error(i18n.t("No number is connected yet. Connect one in Connection."))
        self._rebuild()

    def _rebuild(self):
        self._link = ""
        self.qr_label.clear()
        self.link_edit.setText("")
        self.copy_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        if not self.number.count() or not self.word.count():
            return
        try:
            self._link = chat_link(self.number.currentData() or "", self.word.currentData() or "")
            self.qr_label.setPixmap(qr_pixmap(self._link))
        except (ValueError, qr.QRError) as exc:
            self._link = ""
            self.note.error(str(exc))
            return
        self.note.clear_note()
        self.link_edit.setText(self._link)
        self.copy_btn.setEnabled(True)
        self.save_btn.setEnabled(True)

    def _save(self):
        if not self._link:
            return
        target, _f = QFileDialog.getSaveFileName(self, i18n.t("Save the QR code"), "whatsapp-qr.png", "PNG (*.png)")
        if not target:
            return
        try:
            with open(target, "wb") as fh:
                fh.write(qr.png(qr.matrix(self._link), scale=10))
            C.show_toast(self, i18n.t("Saved"), target)
        except (OSError, qr.QRError) as exc:
            self.note.error(i18n.t("Couldn't save it: {e}").format(e=exc))
