"""Settings → Links and QR: ways for people to start a chat with you.

    a link       https://wa.me/<number>?text=<greeting> — for a bio, an email signature, a message
    a QR code    the same link as a picture for print: a signboard, a visiting card, a brochure, a delivery box
    a website button   a snippet that puts a "Chat with us" button on every page of a website

None of this needs Meta's approval or the service: a WhatsApp link is just a web address. The greeting is typed for the customer, so they only
press send; when they do, the chat opens in your Inbox like any other.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import qr, ui
from addons.whatsapp.settings import _COLUMN, _scrolled
from widgets import controls as C

DEFAULT_GREETING = "Hello! I would like to know more."
WIDGET_ICON = ("M12 2a10 10 0 0 0-8.6 15l-1.4 5 5.1-1.3A10 10 0 1 0 12 2zm5.3 14.1c-.2.6-1.3 1.2-1.8 1.2-.5.1-1 .2-3.3-.7-2.8-1.1-4.5-3.9-4.7-4.1-.1-.2-1.1"
               "-1.5-1.1-2.8s.7-2 1-2.3c.2-.3.5-.3.7-.3h.5c.2 0 .4 0 .6.5l.8 1.9c.1.1.1.3 0 .5l-.3.4-.4.5c-.1.1-.3.3-.1.6.2.3.7 1.2 1.5 1.9 1 .9 1.8 1.2 2.1 1.3.3."
               "1.4.1.6-.1l.8-1c.2-.2.4-.2.6-.1l1.8.9c.3.1.4.2.5.3.1.2.1.7-.1 1.2z")
COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")


def digits_of(number: str) -> str:
    return re.sub(r"\D", "", number or "")


def chat_link(number: str, greeting: str = "") -> str:
    """The wa.me link for a number, with the customer's first message already typed. Raises ValueError if the number has no digits."""
    d = digits_of(number)
    if not 8 <= len(d) <= 15:
        raise ValueError(i18n.t("That number does not look right. Connect it in Connection first."))
    text = (greeting or "").strip()
    return "https://wa.me/%s%s" % (d, ("?text=" + quote(text, safe="")) if text else "")


def widget_snippet(link: str, *, label: str = "Chat with us", colour: str = "#25D366", side: str = "right") -> str:
    """A self-contained button for a website: paste it once, before </body>. No script, no outside files."""
    colour = colour if COLOUR.match(colour or "") else "#25D366"
    side = "left" if side == "left" else "right"
    safe_label = (label or "Chat with us").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:40]
    safe_link = link.replace('"', "%22")
    return ('<!-- WhatsApp chat button: paste before </body> -->\n'
            '<a href="%s" target="_blank" rel="noopener" aria-label="%s"\n'
            ' style="position:fixed;bottom:20px;%s:20px;z-index:9999;display:flex;align-items:center;gap:8px;background:%s;color:#fff;padding:12px 18px;'
            'border-radius:999px;font:600 15px/1 system-ui,sans-serif;text-decoration:none;box-shadow:0 4px 14px rgba(0,0,0,.25)">\n'
            ' <svg width="22" height="22" viewBox="0 0 24 24" fill="#fff" aria-hidden="true"><path d="%s"/></svg>\n'
            ' <span>%s</span>\n</a>\n' % (safe_link, safe_label, side, colour, WIDGET_ICON, safe_label))


def qr_pixmap(link: str, size: int = 220) -> QPixmap:
    """The QR code as a picture: dark modules on white, with the quiet zone a scanner needs."""
    m = qr.matrix(link)
    n = len(m) + 8
    cell = max(2, size // n)
    img = QImage(n * cell, n * cell, QImage.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#000000"))
    for y, row in enumerate(m):
        for x, v in enumerate(row):
            if v:
                p.drawRect((x + 4) * cell, (y + 4) * cell, cell, cell)
    p.end()
    return QPixmap.fromImage(img)


class AcquireSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self._numbers: list = []
        self._link = ""

        card, cc = ui.card(i18n.t("Chat link and QR code"), i18n.t("Anyone who opens the link, or scans the code, starts a chat with this number — with your greeting already typed."),
                           width=_COLUMN)
        self.number = QComboBox()
        self.number.setMinimumHeight(38)
        self.number.currentIndexChanged.connect(self._rebuild)
        cc.addWidget(ui.field(i18n.t("Number"), self.number))
        self.greeting = QLineEdit(DEFAULT_GREETING)
        self.greeting.setMinimumHeight(38)
        self.greeting.setMaxLength(160)
        self.greeting.textChanged.connect(lambda _t: self._rebuild())
        cc.addWidget(ui.field(i18n.t("First message"), self.greeting, i18n.t("What the customer's message says before they press send. Leave it empty for none.")))
        self.link_edit = QLineEdit()
        self.link_edit.setReadOnly(True)
        self.link_edit.setMinimumHeight(38)
        cc.addWidget(ui.field(i18n.t("Link"), self.link_edit))
        row = QHBoxLayout()
        row.addWidget(C.button(i18n.t("Copy the link"), "secondary", "copy", small=True, on_click=lambda: ui.copy_text(self, self._link, i18n.t("the link"))))
        row.addStretch(1)
        cc.addLayout(row)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumHeight(240)
        cc.addWidget(self.qr_label)
        row = QHBoxLayout()
        self.png_btn = C.button(i18n.t("Save QR as picture"), "primary", "download", on_click=lambda: self._save("png"))
        self.svg_btn = C.button(i18n.t("Save for print (SVG)"), "secondary", on_click=lambda: self._save("svg"))
        row.addWidget(self.png_btn)
        row.addWidget(self.svg_btn)
        row.addStretch(1)
        cc.addLayout(row)
        self.note = ui.note()
        cc.addWidget(self.note)
        col.addWidget(card)

        card, wc = ui.card(i18n.t("Website button"), i18n.t("A \"Chat with us\" button on every page of your website. Paste the snippet once, just before </body>."), width=_COLUMN)
        opts = QHBoxLayout()
        opts.setSpacing(theme.SPACE_3)
        self.label = QLineEdit(i18n.t("Chat with us"))
        self.label.setMinimumHeight(38)
        self.label.setMaxLength(40)
        self.label.textChanged.connect(lambda _t: self._snippet())
        opts.addWidget(ui.field(i18n.t("Button text"), self.label), stretch=2)
        self.colour = QLineEdit("#25D366")
        self.colour.setMinimumHeight(38)
        self.colour.setMaxLength(7)
        self.colour.textChanged.connect(lambda _t: self._snippet())
        opts.addWidget(ui.field(i18n.t("Colour"), self.colour), stretch=1)
        self.side = QComboBox()
        self.side.setMinimumHeight(38)
        self.side.addItem(i18n.t("Bottom right"), "right")
        self.side.addItem(i18n.t("Bottom left"), "left")
        self.side.currentIndexChanged.connect(lambda _i: self._snippet())
        opts.addWidget(ui.field(i18n.t("Position"), self.side), stretch=1)
        wc.addLayout(opts)
        self.code = QPlainTextEdit()
        self.code.setReadOnly(True)
        self.code.setFixedHeight(170)
        self.code.setLineWrapMode(QPlainTextEdit.NoWrap)
        wc.addWidget(self.code)
        row = QHBoxLayout()
        row.addWidget(C.button(i18n.t("Copy the snippet"), "primary", "copy", on_click=lambda: ui.copy_text(self, self.code.toPlainText(), i18n.t("the snippet"))))
        row.addStretch(1)
        wc.addLayout(row)
        col.addWidget(card)
        col.addStretch(1)

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def activate(self):
        ui.call(self, "numbers/list", {}, done=self._loaded, failed=lambda m, _d: self.note.error(m))

    def deactivate(self):
        pass

    def _loaded(self, reply: dict):
        self._numbers = list(reply.get("numbers") or [])
        keep = self.number.currentData()
        self.number.blockSignals(True)
        self.number.clear()
        for n in self._numbers:
            self.number.addItem(str(n.get("display") or i18n.t("A WhatsApp number")), n.get("display"))
        i = self.number.findData(keep)
        self.number.setCurrentIndex(max(i, 0))
        self.number.blockSignals(False)
        if not self._numbers:
            self.note.error(i18n.t("No number is connected yet. Connect one in Connection."))
        self._rebuild()

    def _rebuild(self):
        try:
            self._link = chat_link(self.number.currentData() or "", self.greeting.text())
        except ValueError as exc:
            self._link = ""
            self.link_edit.setText("")
            self.qr_label.clear()
            self.png_btn.setEnabled(False)
            self.svg_btn.setEnabled(False)
            if self._numbers:
                self.note.error(str(exc))
            self.code.setPlainText("")
            return
        self.link_edit.setText(self._link)
        try:
            self.qr_label.setPixmap(qr_pixmap(self._link))
            self.png_btn.setEnabled(True)
            self.svg_btn.setEnabled(True)
            self.note.clear_note()
        except qr.QRError as exc:
            self.qr_label.clear()
            self.png_btn.setEnabled(False)
            self.svg_btn.setEnabled(False)
            self.note.error(str(exc))
        self._snippet()

    def _snippet(self):
        if self._link:
            self.code.setPlainText(widget_snippet(self._link, label=self.label.text(), colour=self.colour.text(), side=self.side.currentData()))

    def _save(self, kind: str):
        if not self._link:
            return
        name = "whatsapp-qr." + kind
        target, _f = QFileDialog.getSaveFileName(self, i18n.t("Save the QR code"), name, "PNG (*.png)" if kind == "png" else "SVG (*.svg)")
        if not target:
            return
        try:
            m = qr.matrix(self._link)
            if kind == "png":
                with open(target, "wb") as fh:
                    fh.write(qr.png(m, scale=10))
            else:
                with open(target, "w", encoding="utf-8") as fh:
                    fh.write(qr.svg(m))
            C.show_toast(self, i18n.t("Saved"), target)
        except (OSError, qr.QRError) as exc:
            self.note.error(i18n.t("Couldn't save it: {e}").format(e=exc))
