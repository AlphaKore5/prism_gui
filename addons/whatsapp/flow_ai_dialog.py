"""Write a flow with AI: describe what the bot should do, read the draft, use it.

The server asks the language model for a whole flow, checks it against the same rules every flow must pass before publishing, and asks the
model to repair what failed (up to two more tries). What comes back is shown as plain steps with the checks beside it — nothing is created
until the person says "Use this flow", and then it is an ordinary draft they can change. The model may be wrong; the checks are what make the
result safe to publish, not the model.
"""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import flow_model as M
from addons.whatsapp import ui
from dialogs.base import PrismDialog
from widgets import controls as C

LANGUAGES = ("English", "Hindi", "Gujarati", "Marathi", "Tamil", "Telugu", "Bengali", "Kannada", "Malayalam", "Punjabi", "Urdu")
MIN_WORDS = 12


class AIFlowDialog(PrismDialog):
    """`.result` is {"name", "trigger", "graph"} once the person has chosen to use a draft."""

    def __init__(self, business: str = "", parent=None):
        super().__init__(i18n.t("Write a flow with AI"), i18n.t("Say what the bot should do. You get a draft to read and change before anything goes live."),
                         icon="sparkles", parent=parent, scrollable=True)
        self.result = None
        self._draft = None
        self.what = QPlainTextEdit()
        self.what.setPlaceholderText(i18n.t("When someone asks for a quote, ask the type of work, the area and the city, then pass them to my team."))
        self.what.setFixedHeight(96)
        self.what.setAccessibleName(i18n.t("What the bot should do"))
        self.what.textChanged.connect(self._ready)
        self.body.addWidget(ui.field(i18n.t("What should the bot do?"), self.what, i18n.t("A sentence or two is enough. Say who it talks to and when it hands over to a person.")))
        self.business = QLineEdit(business)
        self.business.setMinimumHeight(38)
        self.business.setPlaceholderText(i18n.t("e.g. We build boundary walls and houses in Vadodara"))
        self.body.addWidget(ui.field(i18n.t("About your business (optional)"), self.business))
        self.language = QComboBox()
        self.language.setMinimumHeight(38)
        for lang in LANGUAGES:
            self.language.addItem(lang, lang)
        self.body.addWidget(ui.field(i18n.t("Language of the messages"), self.language))
        self.note = ui.note()
        self.body.addWidget(self.note)
        self.draft_box = QWidget()
        self.draft_col = QVBoxLayout(self.draft_box)
        self.draft_col.setContentsMargins(0, 0, 0, 0)
        self.draft_col.setSpacing(theme.SPACE_1)
        self.body.addWidget(self.draft_box)
        self.draft_box.setVisible(False)
        self.body.addStretch(1)

        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.write_btn = self.button(i18n.t("Write the flow"), "secondary", on_click=self._write)
        self.footer.add_secondary(self.write_btn)
        self.use_btn = self.button(i18n.t("Use this flow"), "primary", on_click=self._use)
        self.use_btn.setEnabled(False)
        self.footer.set_primary(self.use_btn)
        self.resize(600, 700)
        self._ready()

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def _ready(self):
        words = len(self.what.toPlainText().split())
        self.write_btn.setEnabled(words >= 3 and len(self.what.toPlainText().strip()) >= MIN_WORDS)

    def _write(self):
        self.write_btn.setEnabled(False)
        self.use_btn.setEnabled(False)
        self.write_btn.setText(i18n.t("Writing…"))
        self.note.clear_note()
        ui.call(self, "flows/generate", {"description": self.what.toPlainText().strip(), "business": self.business.text().strip(), "language": self.language.currentData()},
                done=self._written, failed=lambda m, _d: self._failed(m))

    def _failed(self, message: str):
        self.write_btn.setText(i18n.t("Write the flow"))
        self._ready()
        self.note.error(message)

    def _written(self, reply: dict):
        self.write_btn.setText(i18n.t("Write it again"))
        self._ready()
        self._draft = {"name": reply.get("name") or i18n.t("New flow"), "trigger": reply.get("trigger") or {}, "graph": reply.get("graph") or {}}
        issues = reply.get("issues") or []
        errors = [i for i in issues if i.get("severity") == "error"]
        ui.clear(self.draft_col)
        self.draft_box.setVisible(True)
        self.draft_col.addWidget(C.label(self._draft["name"], level="CARD_TITLE"))
        self.draft_col.addWidget(C.label(i18n.t("Starts when: {t}").format(t=M.trigger_words(self._draft["trigger"])), level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True))
        nodes = self._draft["graph"].get("nodes") or {}
        for n, nid in enumerate(M.order_of(self._draft["graph"]), start=1):
            self.draft_col.addWidget(C.label("%d.  %s — %s" % (n, M.type_name(nodes[nid].get("type")), M.describe_step(nodes[nid])), level="SUPPORT",
                                             colour=theme.NEUTRAL[700], wrap=True))
        if errors:
            self.draft_col.addWidget(C.label(i18n.t("{n} things still need fixing — you can fix them in the editor:").format(n=len(errors)), level="SUPPORT", weight=700, colour=theme.ERR_INK))
            for i in errors[:5]:
                self.draft_col.addWidget(C.label("•  " + str(i.get("message", "")), level="META", colour=theme.ERR_INK, wrap=True))
        else:
            fixed = int(reply.get("repairs") or 0)
            tail = (" " + i18n.t("It needed {n} repairs to pass.").format(n=fixed)) if fixed else ""
            self.draft_col.addWidget(C.label(i18n.t("It passes the checks.") + tail, level="SUPPORT", weight=700, colour=theme.OK_INK, wrap=True))
        self.draft_col.addWidget(C.label(i18n.t("Read every message before you publish it. The checks catch mistakes in the shape of the flow, not in what it says."),
                                         level="META", colour=theme.NEUTRAL[600], wrap=True))
        self.use_btn.setEnabled(bool(nodes))

    def _use(self):
        if self._draft:
            self.result = self._draft
            self.accept()
