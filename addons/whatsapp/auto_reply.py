"""One automatic reply — the welcome message, or the one sent outside business hours.

What goes out can be words, words with a picture / video / document under them (the words become its caption), or an approved
template. Which of the three is one choice; the file and the template each come from where they already live (the Media Library,
Templates), so nothing is typed in twice.
"""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QSpinBox, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.media_lib import AssetField
from addons.whatsapp.send_template_dialog import parts
from widgets import controls as C


class AutoReplyBlock(QWidget):
    def __init__(self, owner, title: str, hint: str, parent=None):
        super().__init__(parent)
        self._owner = owner
        self._templates: list = []
        self._edits: list = []
        self._wanted: dict = {}
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_2)
        head = QHBoxLayout()
        head.addWidget(C.label(title, level="SUPPORT", weight=700), stretch=1)
        self.switch = C.ToggleSwitch()
        head.addWidget(self.switch)
        col.addLayout(head)
        col.addWidget(C.label(hint, level="META", colour=theme.NEUTRAL[500], wrap=True))

        self.mode = QComboBox()
        self.mode.setMinimumHeight(36)
        self.mode.setAccessibleName(i18n.t("What is sent"))
        self.mode.addItem(i18n.t("Words, and a file if you like"), "text")
        self.mode.addItem(i18n.t("An approved template"), "template")
        self.mode.currentIndexChanged.connect(self._mode)
        col.addWidget(self.mode)

        self.words = QWidget()
        wc = QVBoxLayout(self.words)
        wc.setContentsMargins(0, 0, 0, 0)
        wc.setSpacing(theme.SPACE_2)
        self.text = QPlainTextEdit()
        self.text.setFixedHeight(72)
        self.text.setAccessibleName(title)
        wc.addWidget(self.text)
        self.asset = AssetField(empty_text=i18n.t("No file — words only"))
        wc.addWidget(ui.field(i18n.t("File under the words"), self.asset, i18n.t("With a file, the words become its caption.")))
        col.addWidget(self.words)

        self.tpl = QWidget()
        tc = QVBoxLayout(self.tpl)
        tc.setContentsMargins(0, 0, 0, 0)
        tc.setSpacing(theme.SPACE_2)
        self.picker = QComboBox()
        self.picker.setMinimumHeight(36)
        self.picker.setAccessibleName(i18n.t("Template"))
        self.picker.currentIndexChanged.connect(lambda _i: self._blanks())
        tc.addWidget(ui.field(i18n.t("Template"), self.picker))
        self.blanks = QVBoxLayout()
        self.blanks.setSpacing(theme.SPACE_2)
        tc.addLayout(self.blanks)
        col.addWidget(self.tpl)
        self.tpl.hide()

        self.every = QSpinBox()
        self.every.setRange(1, 24 * 30)
        self.every.setSuffix(i18n.t(" h"))
        self.every.setMinimumHeight(34)
        col.addWidget(ui.field(i18n.t("At most once every"), self.every))

    def say(self, message: str, error: bool = False):
        if hasattr(self._owner, "say"):
            self._owner.say(message, error)

    # ── the template choice ──────────────────────────────────────────────────
    def load_templates(self):
        ui.call(self, "templates/list", {}, done=self._loaded, failed=lambda _m, _d: None)

    def _loaded(self, reply: dict):
        self._templates = [t for t in reply.get("templates") or [] if str(t.get("status")).upper() == "APPROVED"]
        self.picker.blockSignals(True)
        self.picker.clear()
        for t in self._templates:
            self.picker.addItem("%s · %s" % (t["name"], t.get("language") or ""), t)
        want = self._wanted.get("name")
        if want:
            i = next((k for k in range(self.picker.count()) if (self.picker.itemData(k) or {}).get("name") == want), -1)
            if i >= 0:
                self.picker.setCurrentIndex(i)
        self.picker.blockSignals(False)
        self._blanks()

    def _blanks(self):
        ui.clear(self.blanks)
        self._edits = []
        t = self.picker.currentData()
        if not t:
            return
        need = parts(t.get("components"))
        saved = list(self._wanted.get("body") or []) if self._wanted.get("name") == t.get("name") else []
        for k, n in enumerate(need["body"]):
            e = QLineEdit()
            e.setMinimumHeight(36)
            e.setText(saved[k] if k < len(saved) else "")
            e.setPlaceholderText(i18n.t("What to put for value {n}").format(n=n))
            self._edits.append(e)
            self.blanks.addWidget(ui.field(i18n.t("Value {n}").format(n=n), e))

    def _mode(self, _i=None):
        template = self.mode.currentData() == "template"
        self.words.setVisible(not template)
        self.tpl.setVisible(template)
        if template and not self._templates:
            self.load_templates()

    # ── value ────────────────────────────────────────────────────────────────
    def set_value(self, block: dict):
        block = block or {}
        self.switch.setChecked(bool(block.get("enabled")))
        self.text.setPlainText(block.get("text") or "")
        self.every.setValue(int(block.get("once_per_hours") or 12))
        self.asset.set_asset_id(block.get("asset_id"))
        tpl = block.get("template")
        self._wanted = dict(tpl) if tpl else {}
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(1 if tpl else 0)
        self.mode.blockSignals(False)
        self._mode()
        if tpl and self._templates:
            self._loaded({"templates": self._templates})

    def value(self) -> dict:
        out = {"enabled": self.switch.isChecked(), "once_per_hours": self.every.value(), "text": self.text.toPlainText().strip(),
               "asset_id": None, "template": None}
        if self.mode.currentData() == "template":
            t = self.picker.currentData()
            if t:
                out["template"] = {"name": t["name"], "language": t.get("language") or "en_US", "body": [e.text().strip() for e in self._edits]}
        else:
            out["asset_id"] = self.asset.asset_id()
        return out
