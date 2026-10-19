"""An AI agent's actions: your own web addresses it may call to look something up or do something — an order's status, the free slots this week, a booking.

You write the address once, with the details it needs in {{double braces}}; the agent can only ask for an action by name and fill in those details from what the
customer said — it can never make up an address. The call is made by Prism, to your https address only. "Try it" makes a real call with values you type, so use a
safe address. Your headers (such as an Authorization key) are stored and shown hidden.
"""
from __future__ import annotations

import copy
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from dialogs.base import PrismDialog
from widgets import controls as C

MAX_ACTIONS = 10
MAX_PARAMS = 6
TOKEN = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
BUILT_IN = ("name", "mobile")


def details_in(*texts) -> list:
    """The {{details}} written in an address or a body, in the order they first appear, without the two Prism fills in itself."""
    out = []
    for t in texts:
        for m in TOKEN.findall(t or ""):
            if m not in out and m not in BUILT_IN:
                out.append(m)
    return out


def lines_to_headers(text: str) -> dict:
    out = {}
    for ln in (text or "").splitlines():
        if ":" in ln:
            k, v = ln.split(":", 1)
            if k.strip():
                out[k.strip()] = v.strip()
    return out


class ActionDialog(PrismDialog):
    def __init__(self, action: dict, new: bool = False, agent_id: str = "", parent=None):
        super().__init__(i18n.t("New action") if new else i18n.t("Change this action"), i18n.t("An address of yours the agent may call."), icon="code", parent=parent, scrollable=True)
        self.action = copy.deepcopy(action)
        self.agent_id = agent_id
        self.name = QLineEdit(self.action.get("name") or "")
        self.name.setMinimumHeight(38)
        self.name.setMaxLength(60)
        self.name.setAccessibleName(i18n.t("Action name"))
        self.name.setPlaceholderText(i18n.t("Order status"))
        self.body.addWidget(ui.field(i18n.t("Name"), self.name))
        self.description = QLineEdit(self.action.get("description") or "")
        self.description.setMinimumHeight(38)
        self.description.setMaxLength(300)
        self.description.setAccessibleName(i18n.t("What it is for"))
        self.description.setPlaceholderText(i18n.t("Look up where an order is, from its number"))
        self.body.addWidget(ui.field(i18n.t("What it is for"), self.description, i18n.t("The agent reads this to decide when to use it.")))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        self.method = QComboBox()
        self.method.setMinimumHeight(38)
        self.method.addItems(["GET", "POST"])
        self.method.setCurrentText(self.action.get("method") or "GET")
        self.method.setAccessibleName(i18n.t("Method"))
        row.addWidget(self.method)
        self.url = QLineEdit(self.action.get("url") or "https://")
        self.url.setMinimumHeight(38)
        self.url.setAccessibleName(i18n.t("Address"))
        self.url.setPlaceholderText("https://shop.example.com/orders/{{order}}")
        row.addWidget(self.url, 1)
        self.body.addWidget(ui.field(i18n.t("Call this address"), row, i18n.t("Write the details it needs in double braces, like {{order}}. {{name}} and {{mobile}} are the customer's own.")))
        headers = "\n".join("%s: %s" % (k, v) for k, v in (self.action.get("headers") or {}).items())
        self.headers = QPlainTextEdit(headers)
        self.headers.setFixedHeight(60)
        self.headers.setAccessibleName(i18n.t("Headers"))
        self.headers.setPlaceholderText("Authorization: Bearer …")
        self.body.addWidget(ui.field(i18n.t("Headers"), self.headers, i18n.t("One per line. Stored safely and shown hidden once saved.")))
        self.payload = QPlainTextEdit(self.action.get("body") or "")
        self.payload.setFixedHeight(72)
        self.payload.setAccessibleName(i18n.t("What to send"))
        self.payload.setPlaceholderText('{"order": "{{order}}", "who": "{{name}}"}')
        self.body.addWidget(ui.field(i18n.t("What to send (POST)"), self.payload))
        self.path = QLineEdit(self.action.get("response_path") or "")
        self.path.setMinimumHeight(36)
        self.path.setAccessibleName(i18n.t("Answer path"))
        self.path.setPlaceholderText("order.status")
        self.body.addWidget(ui.field(i18n.t("Use only this part of the answer"), self.path, i18n.t("Optional. If the answer is JSON, name the part the agent should read, like order.status.")))

        self.body.addWidget(C.label(i18n.t("Details the agent must have first").upper(), level="LABEL", colour=theme.NEUTRAL[500]))
        self.params_col = QVBoxLayout()
        self.params_col.setSpacing(theme.SPACE_1)
        self.body.addLayout(self.params_col)
        self.params: list = []
        add = QHBoxLayout()
        self.add_btn = C.button(i18n.t("Add a detail"), "tertiary", icon_name="plus", on_click=lambda: self.add_param({}))
        add.addWidget(self.add_btn)
        self.find_btn = C.button(i18n.t("Find them in the address"), "tertiary", on_click=self.find_params)
        add.addWidget(self.find_btn)
        add.addStretch(1)
        self.body.addLayout(add)

        self.body.addWidget(C.label(i18n.t("Try it").upper(), level="LABEL", colour=theme.NEUTRAL[500]))
        self.try_col = QVBoxLayout()
        self.try_col.setSpacing(theme.SPACE_1)
        self.body.addLayout(self.try_col)
        self.try_values: dict = {}
        for p in self.action.get("parameters") or []:
            self.add_param(p)
        self.try_btn = C.button(i18n.t("Make this call now"), "secondary", on_click=self.try_it)
        trow = QHBoxLayout()
        trow.addWidget(self.try_btn)
        trow.addStretch(1)
        self.body.addLayout(trow)
        self.result = C.label("", level="META", colour=theme.NEUTRAL[700], wrap=True)
        self.result.setVisible(False)
        self.body.addWidget(self.result)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.button(i18n.t("Save action"), "primary", on_click=self._go))
        self.resize(620, 780)
        self._refresh_try()

    # ── the details it needs ─────────────────────────────────────────────────
    def add_param(self, p: dict):
        if len(self.params) >= MAX_PARAMS:
            return
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        name = QLineEdit(p.get("name") or "")
        name.setMinimumHeight(34)
        name.setMaxLength(30)
        name.setPlaceholderText(i18n.t("order"))
        name.setAccessibleName(i18n.t("Detail name"))
        about = QLineEdit(p.get("description") or "")
        about.setMinimumHeight(34)
        about.setMaxLength(200)
        about.setPlaceholderText(i18n.t("the order number the customer gave"))
        about.setAccessibleName(i18n.t("Detail meaning"))
        need = QCheckBox(i18n.t("Needed"))
        need.setChecked(bool(p.get("required", True)))
        box = QWidget()
        box.setLayout(row)
        entry = {"name": name, "about": about, "need": need, "box": box}
        remove = C.icon_button("trash", i18n.t("Remove this detail"), on_click=lambda _=False, e=entry: self._remove(e), colour=theme.NEUTRAL[600])
        for w, s in ((name, 2), (about, 4), (need, 0), (remove, 0)):
            row.addWidget(w, s)
        name.textChanged.connect(lambda _t: self._refresh_try())
        self.params.append(entry)
        self.params_col.addWidget(box)
        self.add_btn.setVisible(len(self.params) < MAX_PARAMS)
        self._refresh_try()

    def _remove(self, entry: dict):
        self.params.remove(entry)
        ui.discard(entry["box"])
        self.add_btn.setVisible(True)
        self._refresh_try()

    def find_params(self):
        have = {e["name"].text().strip().lower() for e in self.params}
        for d in details_in(self.url.text(), self.payload.toPlainText()):
            if d not in have:
                self.add_param({"name": d, "description": "", "required": True})

    def parameters(self) -> list:
        out, seen = [], set()
        for e in self.params:
            n = re.sub(r"[^a-z0-9_]+", "_", e["name"].text().strip().lower()).strip("_")[:30]
            if n and n not in seen and re.match(r"^[a-z]", n):
                seen.add(n)
                out.append({"name": n, "description": e["about"].text().strip(), "required": e["need"].isChecked()})
        return out

    # ── trying it ────────────────────────────────────────────────────────────
    def _refresh_try(self):
        keep = {k: w.text() for k, w in self.try_values.items()}
        ui.clear(self.try_col)
        self.try_values = {}
        for p in self.parameters():
            w = QLineEdit(keep.get(p["name"], ""))
            w.setMinimumHeight(34)
            w.setAccessibleName(i18n.t("Try with {n}").format(n=p["name"]))
            w.setPlaceholderText(i18n.t("A value for {n}").format(n=p["name"]))
            self.try_values[p["name"]] = w
            self.try_col.addWidget(w)

    def value(self) -> dict:
        out = dict(self.action)
        out.update(name=self.name.text().strip(), description=self.description.text().strip(), method=self.method.currentText(), url=self.url.text().strip(),
                   headers=lines_to_headers(self.headers.toPlainText()), body=self.payload.toPlainText().strip(), response_path=self.path.text().strip(),
                   parameters=self.parameters())
        out.setdefault("enabled", True)
        return out

    def try_it(self):
        self.try_btn.setEnabled(False)
        self.result.setVisible(True)
        self.result.setText(i18n.t("Calling…"))
        data = {"action": self.value(), "args": {k: w.text() for k, w in self.try_values.items()}}
        if self.agent_id:
            data["agent_id"] = self.agent_id
        ui.call(self, "ai/actions/test", data, done=self._tried, failed=lambda m, _d: self._try_failed(m))

    def _try_failed(self, message: str):
        self.try_btn.setEnabled(True)
        self.result.setStyleSheet("color: %s; font-size: 12px;" % theme.ERR_INK)
        self.result.setText(message)

    def _tried(self, reply: dict):
        self.try_btn.setEnabled(True)
        good = bool(reply.get("ok"))
        self.result.setStyleSheet("color: %s; font-size: 12px;" % (theme.OK_INK if good else theme.ERR_INK))
        if reply.get("error"):
            self.result.setText(i18n.t("It did not work: {e}").format(e=reply["error"]))
        else:
            text = (reply.get("text") or "").strip().replace("\n", " ")
            self.result.setText(i18n.t("It answered {n}.").format(n=reply.get("status")) + ((" " + text[:300]) if text else ""))

    def _go(self):
        v = self.value()
        if not v["name"] or not v["description"]:
            self.error.error(i18n.t("Give the action a name and say what it is for."))
            return
        if not v["url"].startswith("https://") or len(v["url"]) < 9:
            self.error.error(i18n.t("The address must start with https://"))
            return
        self.accept()


class ActionsSection(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        card, ac = ui.card(i18n.t("Actions"), i18n.t("Addresses of yours the agent may call — to look an order up, check a slot, make a booking. It never calls anything you did not add here."))
        self.list_col = QVBoxLayout()
        self.list_col.setSpacing(theme.SPACE_2)
        ac.addLayout(self.list_col)
        row = QHBoxLayout()
        self.add_btn = C.button(i18n.t("Add an action"), "primary", icon_name="plus", on_click=self.add)
        row.addWidget(self.add_btn)
        row.addStretch(1)
        ac.addLayout(row)
        col.addWidget(card)
        col.addStretch(1)
        self.render()

    @property
    def actions(self) -> list:
        return self.editor.draft["actions"]

    def render(self):
        ui.clear(self.list_col)
        if not self.actions:
            self.list_col.addWidget(C.label(i18n.t("No actions yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for a in self.actions:
            self.list_col.addWidget(self._row(a))
        self.add_btn.setVisible(len(self.actions) < MAX_ACTIONS)

    def _row(self, a: dict) -> QWidget:
        line = QFrame()
        line.setObjectName("waAction")
        line.setAttribute(Qt.WA_StyledBackground, True)
        line.setStyleSheet(f"#waAction {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(line)
        col.setContentsMargins(14, 10, 10, 10)
        col.setSpacing(2)
        top = QHBoxLayout()
        top.addWidget(C.label(a.get("name") or "", level="SUPPORT", weight=700), 1)
        top.addWidget(C.Pill(a.get("method") or "GET", "neutral"))
        switch = C.ToggleSwitch()
        switch.setChecked(bool(a.get("enabled", True)))
        switch.setToolTip(i18n.t("On or off"))
        switch.toggled.connect(lambda on, x=a: (x.__setitem__("enabled", bool(on)), self.editor.edited()))
        top.addWidget(switch)
        top.addWidget(C.button(i18n.t("Change"), "tertiary", small=True, on_click=lambda _=False, x=a: self.change(x)))
        top.addWidget(C.icon_button("trash", i18n.t("Delete this action"), on_click=lambda _=False, x=a: self.remove(x), colour=theme.ERR_INK))
        col.addLayout(top)
        col.addWidget(C.label(a.get("description") or "", level="META", colour=theme.NEUTRAL[700], wrap=True))
        col.addWidget(C.label(a.get("url") or "", level="META", colour=theme.NEUTRAL[500]))
        if (a.get("method") or "GET") != "GET":
            col.addWidget(C.label(i18n.t("This one changes something, so it is not run when you try the agent out."), level="META", colour=theme.WARN_INK, wrap=True))
        return line

    def add(self):
        blank = {"name": "", "description": "", "method": "GET", "url": "https://", "headers": {}, "body": "", "parameters": [], "response_path": "", "enabled": True}
        dlg = ActionDialog(blank, new=True, agent_id=self.editor.agent["id"], parent=self.editor)
        if dlg.exec():
            self.actions.append(dlg.value())
            self.render()
            self.editor.edited()

    def change(self, action: dict):
        dlg = ActionDialog(action, agent_id=self.editor.agent["id"], parent=self.editor)
        if dlg.exec():
            action.clear()
            action.update(dlg.value())
            self.render()
            self.editor.edited()

    def remove(self, action: dict):
        if ui.confirm(self.editor, i18n.t("Delete action"), i18n.t("Delete “{n}”?").format(n=action.get("name"))):
            self.actions.remove(action)
            self.render()
            self.editor.edited()
