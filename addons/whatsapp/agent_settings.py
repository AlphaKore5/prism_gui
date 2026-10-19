"""An AI agent's settings: what it says when it cannot help, who is told when it hands over, who can talk to the unpublished draft, and which numbers it covers.

    Fallback           what it says when it cannot read what was sent or cannot answer
    Hand-over          what it says when it passes the chat to a person, and an address of yours told about every hand-over (with your own headers, such as a key)
    Test numbers       up to three phone numbers that talk to the DRAFT on WhatsApp itself, so you can try changes with a real phone before customers see them
    Numbers            which of your WhatsApp numbers it answers on (none ticked = all of them)
"""
from __future__ import annotations

import re

from PySide6.QtWidgets import QCheckBox, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.agent_actions import lines_to_headers
from widgets import controls as C


class AgentSettingsSection(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        s = editor.draft["settings"]
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_4)

        card, fc = ui.card(i18n.t("When it cannot help"), i18n.t("In your own words, so a customer never sees a stock sentence."))
        self.fallback = QPlainTextEdit(s.get("fallback_text") or "")
        self.fallback.setFixedHeight(64)
        self.fallback.setAccessibleName(i18n.t("Fallback message"))
        self.fallback.setPlaceholderText(i18n.t("Sorry, I can't help with that here. A person from our team will reply shortly."))
        self.fallback.textChanged.connect(lambda: self._set("fallback_text", self.fallback.toPlainText().strip()))
        fc.addWidget(ui.field(i18n.t("Fallback message"), self.fallback, i18n.t("Said when it cannot answer, cannot read a picture or a voice note, or the AI service is down. Then the chat goes to your team.")))
        self.handoff_message = QPlainTextEdit(s.get("handoff_message") or "")
        self.handoff_message.setFixedHeight(64)
        self.handoff_message.setAccessibleName(i18n.t("Hand-over message"))
        self.handoff_message.setPlaceholderText(i18n.t("Let me bring in a colleague who can help with this. They will reply here shortly."))
        self.handoff_message.textChanged.connect(lambda: self._set("handoff_message", self.handoff_message.toPlainText().strip()))
        fc.addWidget(ui.field(i18n.t("Hand-over message"), self.handoff_message, i18n.t("Said when a customer asks for a person, or the agent decides one is needed.")))
        col.addWidget(card)

        card, wc = ui.card(i18n.t("Tell your system about hand-overs"), i18n.t("Each time the agent passes a chat to a person, Prism posts the details to this address. Part of the Premium plan's webhooks."))
        hook = s.get("handoff_webhook") or {}
        self.hook_url = QLineEdit(hook.get("url") or "")
        self.hook_url.setMinimumHeight(38)
        self.hook_url.setPlaceholderText("https://example.com/prism-handover")
        self.hook_url.setAccessibleName(i18n.t("Hand-over address"))
        self.hook_url.textChanged.connect(lambda _t: self._hook())
        wc.addWidget(ui.field(i18n.t("Address"), self.hook_url, i18n.t("Leave empty to turn it off. It must start with https://")))
        headers = "\n".join("%s: %s" % (k, v) for k, v in (hook.get("headers") or {}).items())
        self.hook_headers = QPlainTextEdit(headers)
        self.hook_headers.setFixedHeight(60)
        self.hook_headers.setAccessibleName(i18n.t("Hand-over headers"))
        self.hook_headers.setPlaceholderText("Authorization: Bearer …")
        self.hook_headers.textChanged.connect(self._hook)
        wc.addWidget(ui.field(i18n.t("Headers"), self.hook_headers, i18n.t("One per line, e.g. a key your system checks. Stored safely and shown hidden once saved.")))
        col.addWidget(card)

        card, tc = ui.card(i18n.t("Test numbers"), i18n.t("Phones that talk to the draft you are editing, on real WhatsApp. Everyone else meets the published version."))
        self.tests = []
        have = list(s.get("test_numbers") or [])
        for i in range(3):
            e = QLineEdit(have[i] if i < len(have) else "")
            e.setMinimumHeight(36)
            e.setPlaceholderText(i18n.t("A phone number with its country code, e.g. 919876543210"))
            e.setAccessibleName(i18n.t("Test number {n}").format(n=i + 1))
            e.textChanged.connect(lambda _t: self._tests())
            self.tests.append(e)
            tc.addWidget(e)
        self.tests_note = ui.note()
        tc.addWidget(self.tests_note)
        col.addWidget(card)

        card, nc = ui.card(i18n.t("Which numbers it answers on"), i18n.t("If you tick none, it answers on every WhatsApp number you have."))
        self.numbers_col = QVBoxLayout()
        self.numbers_col.setSpacing(theme.SPACE_1)
        nc.addLayout(self.numbers_col)
        self.numbers_boxes: dict = {}
        col.addWidget(card)
        col.addStretch(1)

    def _set(self, key, value):
        self.editor.draft["settings"][key] = value
        self.editor.edited()

    def _hook(self, *_):
        url = self.hook_url.text().strip()
        self.editor.draft["settings"]["handoff_webhook"] = {"url": url, "headers": lines_to_headers(self.hook_headers.toPlainText())} if url else None
        self.editor.edited()

    def _tests(self):
        numbers = [re.sub(r"\D", "", e.text()) for e in self.tests if re.sub(r"\D", "", e.text())]
        bad = [n for n in numbers if not 8 <= len(n) <= 15]
        if bad:
            self.tests_note.error(i18n.t("A test number is a full phone number with its country code."))
        else:
            self.tests_note.clear_note()
        self.editor.draft["settings"]["test_numbers"] = numbers[:3]
        self.editor.edited()

    # ── the workspace's numbers ──────────────────────────────────────────────
    def load_numbers(self):
        ui.call(self.editor, "numbers/list", {}, done=self._numbers, failed=lambda m, _d: None)

    def _numbers(self, reply: dict):
        ui.clear(self.numbers_col)
        self.numbers_boxes = {}
        chosen = set(self.editor.draft["settings"].get("numbers") or [])
        rows = list(reply.get("numbers") or [])
        if not rows:
            self.numbers_col.addWidget(C.label(i18n.t("No number is connected yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for n in rows:
            box = QCheckBox(str(n.get("display") or n.get("id")))
            box.setChecked(str(n.get("id")) in chosen)
            box.toggled.connect(lambda _on: self._numbers_changed())
            self.numbers_boxes[str(n.get("id"))] = box
            self.numbers_col.addWidget(box)

    def _numbers_changed(self):
        self.editor.draft["settings"]["numbers"] = [k for k, b in self.numbers_boxes.items() if b.isChecked()]
        self.editor.edited()
