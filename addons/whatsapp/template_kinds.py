"""The kinds of template beyond plain text, as pieces the template window puts together.

    SamplePicker   a picture / video / document for Meta's reviewers to look at: chosen from the Media Library, then handed to Meta
                   (templates/upload_sample), which answers with the handle the template carries
    AuthPanel      an authentication template: one-time password with a copy-code, one-tap or zero-tap button, how long the code lives
    OfferPanel     a limited-time offer: its few words and whether it counts down
    CardsEditor    a carousel: two to ten cards, each a picture or video and a short text
    VALIDITY       how long Meta may keep trying to deliver a template, by category

Nothing here knows about the window around it: each piece reports `changed` and can give back the Meta components it stands for.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.media_lib import AssetField
from widgets import controls as C

# Template kinds, in the order they are offered. (key, label) — literal i18n.t calls, so the extractor sees every word.
def kinds() -> list:
    return [("text", i18n.t("Text")), ("image", i18n.t("Picture")), ("video", i18n.t("Video")), ("document", i18n.t("Document")),
            ("location", i18n.t("Location")), ("carousel", i18n.t("Carousel")), ("offer", i18n.t("Limited-time offer"))]


MEDIA_KINDS = ("image", "video", "document")


def validity_choices(category: str) -> list:
    """(seconds, label) for the message-validity list of a category; -1 is Meta's own default. Meta's ranges: marketing 12 hours to
    30 days, utility 30 seconds to 12 hours, authentication 30 seconds to 15 minutes."""
    base = [(-1, i18n.t("Meta's default"))]
    if category == "MARKETING":
        return base + [(12 * 3600, i18n.t("12 hours")), (24 * 3600, i18n.t("1 day")), (3 * 86400, i18n.t("3 days")), (7 * 86400, i18n.t("7 days")),
                       (14 * 86400, i18n.t("14 days")), (30 * 86400, i18n.t("30 days"))]
    if category == "UTILITY":
        return base + [(60, i18n.t("1 minute")), (5 * 60, i18n.t("5 minutes")), (30 * 60, i18n.t("30 minutes")), (3600, i18n.t("1 hour")),
                       (6 * 3600, i18n.t("6 hours")), (12 * 3600, i18n.t("12 hours"))]
    return base + [(30, i18n.t("30 seconds")), (60, i18n.t("1 minute")), (5 * 60, i18n.t("5 minutes")), (15 * 60, i18n.t("15 minutes"))]


def header_component(kind: str, handle: str = "", text: str = "", sample: str = "") -> dict | None:
    if kind in MEDIA_KINDS:
        part = {"type": "HEADER", "format": kind.upper()}
        if handle:
            part["example"] = {"header_handle": [handle]}
        return part
    if kind == "location":
        return {"type": "HEADER", "format": "LOCATION"}
    if text.strip():
        part = {"type": "HEADER", "format": "TEXT", "text": text.strip()}
        if "{{" in text and sample.strip():
            part["example"] = {"header_text": [sample.strip()]}
        return part
    return None


class SamplePicker(QWidget):
    """A sample file for a template. Choosing one sends it to Meta at once; `handle()` is Meta's answer, empty until it has one."""

    changed = Signal()

    def __init__(self, kind: str = "image", parent=None):
        super().__init__(parent)
        self._kind = kind if kind in MEDIA_KINDS else "image"
        self._handle = ""
        self._busy = False
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        self.field = AssetField((self._kind,), empty_text=i18n.t("Choose a sample from your Media Library"))
        self.field.changed.connect(self._chosen)
        col.addWidget(self.field)
        self.note = ui.note()
        col.addWidget(self.note)

    def kind(self) -> str:
        return self._kind

    def set_kind(self, kind: str):
        if kind in MEDIA_KINDS and kind != self._kind:
            self._kind = kind
            self.field.kinds = (kind,)
            self.field.clear()                      # a picture is no sample for a video header

    def handle(self) -> str:
        return self._handle

    def busy(self) -> bool:
        return self._busy

    def asset_id(self):
        return self.field.asset_id()

    def set_handle(self, handle: str):
        """A template read back from Meta already carries its handle: show it as ready without a file."""
        self._handle = handle or ""
        if handle:
            self.note.ok(i18n.t("Sample is with Meta."))

    def _chosen(self):
        self._handle = ""
        self.note.clear_note()
        asset = self.field.asset_id()
        if not asset:
            self.changed.emit()
            return
        self._busy = True
        self.note.set(i18n.t("Sending the sample to Meta…"), "quiet")
        self.changed.emit()
        ui.call(self, "templates/upload_sample", {"asset_id": asset, "format": self._kind}, done=self._uploaded, failed=self._failed)

    def _uploaded(self, reply: dict):
        self._busy = False
        self._handle = str(reply.get("handle") or "")
        self.note.ok(i18n.t("Sample is with Meta.") if self._handle else "")
        self.changed.emit()

    def _failed(self, message: str, _detail: dict):
        self._busy = False
        self._handle = ""
        self.note.error(message)
        self.changed.emit()


class OfferPanel(QWidget):
    """A limited-time offer: the few words shown on the offer, and whether it counts down to an end."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_2)
        self.text = QLineEdit()
        self.text.setMaxLength(16)
        self.text.setMinimumHeight(38)
        self.text.setPlaceholderText(i18n.t("e.g. Festival offer"))
        self.text.setAccessibleName(i18n.t("Offer text"))
        self.text.textChanged.connect(lambda _t: self.changed.emit())
        col.addWidget(ui.field(i18n.t("Offer text"), self.text, i18n.t("Up to 16 characters, shown on the offer.")))
        self.countdown = QCheckBox(i18n.t("Show a countdown to when the offer ends"))
        self.countdown.setChecked(True)
        self.countdown.toggled.connect(lambda _on: self.changed.emit())
        col.addWidget(self.countdown)
        col.addWidget(C.label(i18n.t("The end date is chosen when you send it. Add a Copy code and a Visit website button below for the coupon "
                                     "and the link."), level="META", colour=theme.NEUTRAL[500], wrap=True))

    def component(self) -> dict | None:
        text = self.text.text().strip()
        return {"type": "LIMITED_TIME_OFFER", "limited_time_offer": {"text": text, "has_expiration": self.countdown.isChecked()}}

    def fill(self, comp: dict):
        offer = (comp or {}).get("limited_time_offer") or {}
        self.text.setText(offer.get("text") or "")
        self.countdown.setChecked(bool(offer.get("has_expiration", True)))


class AuthPanel(QWidget):
    """The one-time-password template. Meta writes the words; the business chooses how the code gets from the message to the app."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_3)
        col.addWidget(C.label(i18n.t("Meta writes the message: “Your verification code is …”. You choose how the code reaches your app and how long "
                                     "it lives."), level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
        self.mode = QComboBox()
        self.mode.setMinimumHeight(38)
        self.mode.addItem(i18n.t("Copy code — the customer taps to copy it"), "COPY_CODE")
        self.mode.addItem(i18n.t("One-tap autofill — fills your Android app after one tap"), "ONE_TAP")
        self.mode.addItem(i18n.t("Zero-tap — fills your Android app with no tap"), "ZERO_TAP")
        self.mode.currentIndexChanged.connect(self._mode)
        col.addWidget(ui.field(i18n.t("How the code is entered"), self.mode))
        self.button_text = QLineEdit(i18n.t("Copy code"))
        self.button_text.setMaxLength(25)
        self.button_text.setMinimumHeight(38)
        col.addWidget(ui.field(i18n.t("Button text"), self.button_text))
        self.app_box = QWidget()
        ab = QVBoxLayout(self.app_box)
        ab.setContentsMargins(0, 0, 0, 0)
        ab.setSpacing(theme.SPACE_2)
        self.autofill = QLineEdit(i18n.t("Autofill"))
        self.autofill.setMaxLength(25)
        self.autofill.setMinimumHeight(38)
        ab.addWidget(ui.field(i18n.t("Autofill button text"), self.autofill))
        self.package = QLineEdit()
        self.package.setMinimumHeight(38)
        self.package.setPlaceholderText("com.example.app")
        ab.addWidget(ui.field(i18n.t("Android package name"), self.package))
        self.signature = QLineEdit()
        self.signature.setMinimumHeight(38)
        self.signature.setMaxLength(11)
        self.signature.setPlaceholderText("K8a/AX6ELnR")
        ab.addWidget(ui.field(i18n.t("App signature hash"), self.signature, i18n.t("The 11-character hash of the key your app is signed with.")))
        self.terms = QCheckBox(i18n.t("I accept Meta's zero-tap terms"))
        ab.addWidget(self.terms)
        col.addWidget(self.app_box)
        self.security = QCheckBox(i18n.t("Add “For your security, do not share this code”"))
        self.security.setChecked(True)
        col.addWidget(self.security)
        self.expires = QCheckBox(i18n.t("Add a code expiry"))
        self.expires.setChecked(True)
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 90)
        self.minutes.setValue(10)
        self.minutes.setSuffix(i18n.t(" minutes"))
        self.minutes.setMinimumHeight(36)
        row = QHBoxLayout()
        row.addWidget(self.expires)
        row.addWidget(self.minutes)
        row.addStretch(1)
        col.addLayout(row)
        self.expires.toggled.connect(self.minutes.setEnabled)
        for w in (self.button_text, self.autofill, self.package, self.signature):
            w.textChanged.connect(lambda _t: self.changed.emit())
        for w in (self.terms, self.security, self.expires):
            w.toggled.connect(lambda _on: self.changed.emit())
        self.minutes.valueChanged.connect(lambda _v: self.changed.emit())
        self._mode()

    def _mode(self, _i=None):
        self.app_box.setVisible(self.mode.currentData() != "COPY_CODE")
        self.terms.setVisible(self.mode.currentData() == "ZERO_TAP")
        self.changed.emit()

    def components(self) -> list:
        kind = self.mode.currentData()
        button = {"type": "OTP", "otp_type": kind, "text": self.button_text.text().strip()}
        if kind != "COPY_CODE":
            button.update(autofill_text=self.autofill.text().strip(), package_name=self.package.text().strip(),
                          signature_hash=self.signature.text().strip())
        if kind == "ZERO_TAP":
            button["zero_tap_terms_accepted"] = self.terms.isChecked()
        footer = {"type": "FOOTER"}
        if self.expires.isChecked():
            footer["code_expiration_minutes"] = self.minutes.value()
        out = [{"type": "BODY", "add_security_recommendation": self.security.isChecked()}]
        if self.expires.isChecked():
            out.append(footer)
        out.append({"type": "BUTTONS", "buttons": [button]})
        return out

    def fill(self, components: list):
        for c in components or []:
            if c.get("type") == "BODY":
                self.security.setChecked(bool(c.get("add_security_recommendation")))
            elif c.get("type") == "FOOTER":
                minutes = c.get("code_expiration_minutes")
                self.expires.setChecked(minutes is not None)
                if minutes:
                    self.minutes.setValue(int(minutes))
            elif c.get("type") == "BUTTONS":
                b = (c.get("buttons") or [{}])[0]
                self.mode.setCurrentIndex(max(self.mode.findData(b.get("otp_type")), 0))
                self.button_text.setText(b.get("text") or "")
                self.autofill.setText(b.get("autofill_text") or "")
                self.package.setText(b.get("package_name") or "")
                self.signature.setText(b.get("signature_hash") or "")
                self.terms.setChecked(bool(b.get("zero_tap_terms_accepted")))
        if not any(c.get("type") == "FOOTER" for c in components or []):
            self.expires.setChecked(False)


class _Card(QWidget):
    changed = Signal()

    def __init__(self, index: int, kind: str, parent=None):
        super().__init__(parent)
        self.setObjectName("waCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#waCard {{ background: rgba(255,255,255,0.5); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(self)
        col.setContentsMargins(12, 10, 12, 10)
        col.setSpacing(theme.SPACE_2)
        self.title = C.label(i18n.t("Card {n}").format(n=index + 1), level="SUPPORT", weight=700)
        col.addWidget(self.title)
        self.sample = SamplePicker(kind)
        self.sample.changed.connect(self.changed.emit)
        col.addWidget(self.sample)
        self.text = QLineEdit()
        self.text.setMaxLength(160)
        self.text.setMinimumHeight(38)
        self.text.setPlaceholderText(i18n.t("A short description (up to 160 characters)"))
        self.text.setAccessibleName(self.title.text())
        self.text.textChanged.connect(lambda _t: self.changed.emit())
        col.addWidget(self.text)


class CardsEditor(QWidget):
    """The cards of a carousel. Every card has the same kind of media and the same buttons (the window's buttons), so those are chosen once."""

    changed = Signal()
    MIN, MAX = 2, 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kind = "image"
        self._cards: list = []
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_2)
        self.kind_box = QComboBox()
        self.kind_box.setMinimumHeight(38)
        self.kind_box.addItem(i18n.t("Pictures"), "image")
        self.kind_box.addItem(i18n.t("Videos"), "video")
        self.kind_box.currentIndexChanged.connect(self._kind_changed)
        col.addWidget(ui.field(i18n.t("Media on every card"), self.kind_box))
        self.holder = QVBoxLayout()
        self.holder.setSpacing(theme.SPACE_2)
        col.addLayout(self.holder)
        row = QHBoxLayout()
        self.add_btn = C.button(i18n.t("Add a card"), "secondary", "plus", small=True, on_click=self.add_card)
        self.remove_btn = C.button(i18n.t("Remove the last card"), "tertiary", small=True, on_click=self.remove_last)
        row.addWidget(self.add_btn)
        row.addWidget(self.remove_btn)
        row.addStretch(1)
        col.addLayout(row)
        for _ in range(self.MIN):
            self.add_card(emit=False)
        self._buttons_state()

    def _kind_changed(self, _i=None):
        self._kind = self.kind_box.currentData()
        for card in self._cards:
            card.sample.set_kind(self._kind)
        self.changed.emit()

    def add_card(self, *, emit: bool = True):
        if len(self._cards) >= self.MAX:
            return
        card = _Card(len(self._cards), self._kind)
        card.changed.connect(self.changed.emit)
        self._cards.append(card)
        self.holder.addWidget(card)
        self._buttons_state()
        if emit:
            self.changed.emit()

    def remove_last(self):
        if len(self._cards) <= self.MIN:
            return
        ui.discard(self._cards.pop())
        self._buttons_state()
        self.changed.emit()

    def _buttons_state(self):
        self.add_btn.setEnabled(len(self._cards) < self.MAX)
        self.remove_btn.setEnabled(len(self._cards) > self.MIN)

    def busy(self) -> bool:
        return any(c.sample.busy() for c in self._cards)

    def missing_samples(self) -> bool:
        return any(not c.sample.handle() for c in self._cards)

    def count(self) -> int:
        return len(self._cards)

    def kind(self) -> str:
        return self._kind

    def card_texts(self) -> list:
        return [c.text.text() for c in self._cards]

    def component(self, buttons: list) -> dict:
        """The CAROUSEL component. `buttons` are the Meta button parts shared by every card."""
        cards = []
        for c in self._cards:
            comps = [header_component(self._kind, c.sample.handle()), {"type": "BODY", "text": c.text.text().strip()}]
            if buttons:
                comps.append({"type": "BUTTONS", "buttons": [dict(b) for b in buttons]})
            cards.append({"components": comps})
        return {"type": "CAROUSEL", "cards": cards}

    def fill(self, comp: dict):
        cards = (comp or {}).get("cards") or []
        while len(self._cards) < max(self.MIN, min(len(cards), self.MAX)):
            self.add_card(emit=False)
        while len(self._cards) > max(self.MIN, min(len(cards), self.MAX)):
            ui.discard(self._cards.pop())
        first = next((c for card in cards for c in card.get("components", []) if c.get("type") == "HEADER"), {})
        kind = "video" if first.get("format") == "VIDEO" else "image"
        self.kind_box.blockSignals(True)
        self.kind_box.setCurrentIndex(max(self.kind_box.findData(kind), 0))
        self.kind_box.blockSignals(False)
        self._kind = kind
        for ui_card, card in zip(self._cards, cards):
            ui_card.sample.set_kind(kind)
            for c in card.get("components", []):
                if c.get("type") == "BODY":
                    ui_card.text.setText(c.get("text") or "")
                elif c.get("type") == "HEADER":
                    ui_card.sample.set_handle(((c.get("example") or {}).get("header_handle") or [""])[0])
        self._buttons_state()
