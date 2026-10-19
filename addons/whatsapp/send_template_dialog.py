"""Send one approved template to one person — how a chat is started, or restarted once its 24 hours are over.

Pick a template, fill the blanks, see the message as they will, send. Only approved templates are offered; a person who has
opted out is refused by the server, with the reason shown here.
"""
from __future__ import annotations

import re

from PySide6.QtWidgets import QComboBox, QLineEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.media_lib import AssetField
from dialogs.base import PrismDialog
from widgets import controls as C

_VAR = re.compile(r"\{\{\s*(\d+)\s*\}\}")


def parts(components: list) -> dict:
    """What a template needs from the sender: {'body': [1, 2], 'header': [1], 'header_media': 'image'|None, 'url': [1], 'text': '...'}."""
    out = {"body": [], "header": [], "header_media": None, "url": [], "text": "", "footer": ""}
    for c in components or []:
        kind = c.get("type")
        if kind == "BODY":
            out["text"] = c.get("text") or ""
            out["body"] = sorted({int(v) for v in _VAR.findall(out["text"])})
        elif kind == "HEADER":
            if c.get("format") == "TEXT":
                out["header"] = sorted({int(v) for v in _VAR.findall(c.get("text") or "")})
            elif c.get("format") in ("IMAGE", "VIDEO", "DOCUMENT"):
                out["header_media"] = c["format"].lower()
        elif kind == "FOOTER":
            out["footer"] = c.get("text") or ""
        elif kind == "BUTTONS":
            for i, b in enumerate(c.get("buttons") or []):
                if b.get("type") == "URL" and _VAR.search(b.get("url") or ""):
                    out["url"].append(i)
    return out


def render(text: str, values: dict) -> str:
    return _VAR.sub(lambda m: (values.get(int(m.group(1))) or "").strip() or "{{%s}}" % m.group(1), text)


class SendTemplateDialog(PrismDialog):
    def __init__(self, contact: dict, parent=None):
        who = contact.get("name") or contact.get("phone") or ""
        super().__init__(i18n.t("Send a template"), i18n.t("To {n}. Only a template Meta has approved can start a chat.").format(n=who),
                         icon="send", parent=parent, scrollable=True)
        self.contact = contact
        self._templates: list = []
        self._edits: dict = {}
        self._header_file = None
        self.picker = QComboBox()
        self.picker.setMinimumHeight(38)
        self.picker.setAccessibleName(i18n.t("Template"))
        self.picker.currentIndexChanged.connect(self._build)
        self.body.addWidget(ui.field(i18n.t("Template"), self.picker))
        self.blanks = QVBoxLayout()
        self.blanks.setSpacing(theme.SPACE_3)
        self.body.addLayout(self.blanks)
        self.preview = C.label("", level="SUPPORT", wrap=True)
        card, col = ui.card(i18n.t("How it will look"))
        col.addWidget(self.preview)
        self.body.addWidget(card)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.go = self.button(i18n.t("Send"), "primary", on_click=self._send)
        self.go.setEnabled(False)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.go)
        self.resize(560, 620)
        ui.call(self, "templates/list", {}, done=self._loaded, failed=lambda m, _d: self.error.error(m))

    def _loaded(self, reply: dict):
        self._templates = [t for t in reply.get("templates") or [] if t.get("status") == "APPROVED"]
        self.picker.blockSignals(True)
        self.picker.clear()
        for t in self._templates:
            self.picker.addItem("%s · %s" % (t["name"], t.get("language") or ""), t)
        self.picker.blockSignals(False)
        if not self._templates:
            self.error.error(i18n.t("There is no approved template yet. Create one in Templates and wait for Meta to approve it."))
            return
        self._build()

    def _build(self, _i=None):
        ui.clear(self.blanks)
        self._edits = {}
        self._header_file = None
        t = self.picker.currentData()
        if not t:
            return
        need = parts(t.get("components"))
        if need["header_media"]:
            self._header_file = AssetField((need["header_media"],), empty_text=i18n.t("Choose from your Media Library"))
            self.blanks.addWidget(ui.field(i18n.t("The {k} in the header").format(k=need["header_media"]), self._header_file))
            self._edit("header_link", i18n.t("or a web address of the {k}").format(k=need["header_media"]), "https://…")
        for n in need["header"]:
            self._edit(("header", n), i18n.t("Header value {n}").format(n=n))
        for n in need["body"]:
            self._edit(("body", n), i18n.t("Value {n}").format(n=n))
        for i in need["url"]:
            self._edit(("url", i), i18n.t("End of the link for button {n}").format(n=i + 1))
        self.go.setEnabled(True)
        self._refresh()

    def _edit(self, key, label: str, hint: str = ""):
        e = QLineEdit()
        e.setMinimumHeight(38)
        e.setPlaceholderText(hint)
        e.textChanged.connect(lambda _t: self._refresh())
        self._edits[key] = e
        self.blanks.addWidget(ui.field(label, e))

    def _refresh(self):
        t = self.picker.currentData()
        if not t:
            self.preview.setText("")
            return
        values = {k[1]: e.text() for k, e in self._edits.items() if isinstance(k, tuple) and k[0] == "body"}
        self.preview.setText(render(parts(t.get("components"))["text"], values))

    def payload(self) -> dict:
        t = self.picker.currentData() or {}
        need = parts(t.get("components"))
        get = lambda key: self._edits[key].text().strip() if key in self._edits else ""            # noqa: E731
        return {"contact_id": self.contact.get("id"), "template_name": t.get("name"), "language": t.get("language") or "en_US",
                "body": [get(("body", n)) for n in need["body"]], "header": [get(("header", n)) for n in need["header"]],
                "header_link": get("header_link"), "header_asset_id": self._header_file.asset_id() if self._header_file is not None else None,
                "buttons": {str(i): get(("url", i)) for i in need["url"]}}

    def _send(self):
        self.go.setEnabled(False)
        self.error.clear_note()
        ui.call(self, "messages/send_template", self.payload(), done=lambda _r: self.accept(),
                failed=lambda m, _d: (self.go.setEnabled(True), self.error.error(m)))
