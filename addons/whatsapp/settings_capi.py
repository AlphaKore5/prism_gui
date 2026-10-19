"""Settings → Developers → Telling Meta what your ads earned (the Conversions API).

A customer who clicks one of your click-to-WhatsApp ads carries an invisible click id into their first message. When a flow (or you) decides that
person became a lead or bought something, Prism tells Meta, with that click id, and Meta's ad system learns which ads bring real customers and
shows them to more people like them. Nothing is sent for a customer who did not come from an ad, and nothing is sent until a dataset is set up.

You need the dataset id from Meta's Events Manager. Before real events count, send a test event with Meta's test code and see it arrive.
"""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from widgets import controls as C


class CapiCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        card, cc = ui.card(i18n.t("Tell Meta what your ads earned"), i18n.t("When someone who came from your ad becomes a lead or a customer, tell Meta, so your ads find more people like them."), width=720)
        self.dataset = QLineEdit()
        self.dataset.setMinimumHeight(38)
        self.dataset.setPlaceholderText(i18n.t("The number from Events Manager"))
        self.dataset.setAccessibleName(i18n.t("Dataset id"))
        cc.addWidget(ui.field(i18n.t("Dataset id"), self.dataset, i18n.t("In Meta Events Manager, open your dataset: the id is the long number under its name.")))
        self.test_code = QLineEdit()
        self.test_code.setMinimumHeight(38)
        self.test_code.setPlaceholderText("TEST12345")
        self.test_code.setAccessibleName(i18n.t("Test event code"))
        cc.addWidget(ui.field(i18n.t("Test event code (only for trying it)"), self.test_code, i18n.t("Events Manager, Test events. A test event shows there and never counts toward your ads.")))
        self.enabled = QCheckBox(i18n.t("Send events to Meta"))
        self.enabled.setChecked(True)
        cc.addWidget(self.enabled)
        self.note = ui.note()
        cc.addWidget(self.note)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        self.save_btn = C.button(i18n.t("Save"), "primary", on_click=self.save)
        self.test_btn = C.button(i18n.t("Send a test event"), "secondary", on_click=self.send_test)
        row.addWidget(self.save_btn)
        row.addWidget(self.test_btn)
        row.addStretch(1)
        cc.addLayout(row)
        col.addWidget(card)

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def load(self):
        ui.call(self, "capi/get", {}, done=self._loaded, failed=lambda m, _d: self.note.error(m))

    def _loaded(self, reply: dict):
        s = reply.get("settings") or {}
        self.dataset.setText(s.get("dataset_id") or "")
        self.test_code.setText(s.get("test_code") or "")
        self.enabled.setChecked(bool(s.get("enabled", True)) if s.get("dataset_id") else True)
        self.note.clear_note()

    def values(self) -> dict:
        return {"dataset_id": self.dataset.text().strip(), "test_code": self.test_code.text().strip(), "enabled": self.enabled.isChecked()}

    def save(self, then=None):
        v = self.values()
        if v["dataset_id"] and not v["dataset_id"].isdigit():
            self.note.error(i18n.t("The dataset id is only digits — copy the number from Events Manager."))
            return
        ui.call(self, "capi/save", v, done=lambda r: (self.say(i18n.t("Saved.") if v["dataset_id"] else i18n.t("Saved. Nothing is sent until you add a dataset id.")),
                                                       then() if callable(then) else None),
                failed=lambda m, _d: self.note.error(m))

    def send_test(self):
        self.test_btn.setEnabled(False)
        self.note.clear_note()
        self.save(then=lambda: ui.call(self, "capi/test", {}, done=self._tested, failed=lambda m, _d: self._test_failed(m)))

    def _test_failed(self, message: str):
        self.test_btn.setEnabled(True)
        self.note.error(message)

    def _tested(self, reply: dict):
        self.test_btn.setEnabled(True)
        n = int(reply.get("events_received") or 0)
        self.note.ok(i18n.t("Meta received {n} test event. Open Events Manager, Test events, to see it.").format(n=n) if n else
                     i18n.t("Meta did not report receiving it. Check the dataset id and the test code."))
