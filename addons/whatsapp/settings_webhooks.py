"""Settings → Developers → Webhooks: tell your own systems when something happens here.

You give an address and choose what to hear about (a customer's message, a delivery, a chat that needs a person, a finished campaign...).
Each time it happens Prism posts a small signed JSON message to the address, tries again if it is down, and keeps a log you can read and
replay. The secret that signs the messages is shown once, when the webhook is made: copy it into your own system so it can check that a
message really came from Prism.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.chat import short_time
from dialogs.base import PrismDialog
from widgets import controls as C


def event_words(event: str, catalogue: dict) -> str:
    return (catalogue or {}).get(event) or (i18n.t("A test message") if event == "ping" else event)


def state_words(state: str) -> tuple:
    return {"delivered": (i18n.t("Delivered"), "ok"), "pending": (i18n.t("Waiting"), "info"), "failed": (i18n.t("Failed"), "err")}.get(state, (state, "quiet"))


class WebhookDialog(PrismDialog):
    """Make a webhook: an address, a note, and what to be told about."""

    def __init__(self, events: dict, parent=None):
        super().__init__(i18n.t("New webhook"), i18n.t("Prism will post to this address each time one of the things you choose happens."), icon="code", parent=parent, scrollable=True)
        self.created = None
        self._boxes: dict = {}
        self.url = QLineEdit()
        self.url.setMinimumHeight(38)
        self.url.setPlaceholderText("https://example.com/prism-webhook")
        self.url.setAccessibleName(i18n.t("Address"))
        self.body.addWidget(ui.field(i18n.t("Address"), self.url, i18n.t("It must start with https:// and be reachable from the internet.")))
        self.desc = QLineEdit()
        self.desc.setMinimumHeight(38)
        self.desc.setPlaceholderText(i18n.t("e.g. Our CRM"))
        self.body.addWidget(ui.field(i18n.t("A name for it (optional)"), self.desc))
        self.body.addWidget(C.label(i18n.t("Tell me when…").upper(), level="LABEL", colour=theme.NEUTRAL[500]))
        for key, words in (events or {}).items():
            box = QCheckBox(words)
            box.setChecked(key in ("message.received", "message.status"))
            box.toggled.connect(lambda _on: self._check())
            self._boxes[key] = box
            self.body.addWidget(box)
        self.note = ui.note()
        self.body.addWidget(self.note)
        self.body.addStretch(1)
        self.go = self.button(i18n.t("Add webhook"), "primary", on_click=self._go)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.go)
        self.resize(560, 640)

    def chosen(self) -> list:
        return [k for k, b in self._boxes.items() if b.isChecked()]

    def _check(self):
        self.go.setEnabled(bool(self.chosen()))

    def _go(self):
        self.go.setEnabled(False)
        self.note.clear_note()
        ui.call(self, "webhooks/create", {"url": self.url.text().strip(), "events": self.chosen(), "description": self.desc.text().strip()},
                done=self._done, failed=lambda m, _d: (self.go.setEnabled(True), self.note.error(m)))

    def _done(self, reply: dict):
        self.created = reply
        self.accept()


class SecretDialog(PrismDialog):
    """The one time the signing secret is shown."""

    def __init__(self, secret: str, parent=None):
        super().__init__(i18n.t("Your signing secret"), i18n.t("Copy it now. This is the only time it is shown."), icon="key", parent=parent)
        self.secret = secret
        edit = QLineEdit(secret)
        edit.setReadOnly(True)
        edit.setMinimumHeight(40)
        edit.setAccessibleName(i18n.t("The signing secret"))
        edit.selectAll()
        self.body.addWidget(edit)
        row = QHBoxLayout()
        row.addWidget(C.button(i18n.t("Copy secret"), "primary", on_click=lambda: ui.copy_text(self, secret, i18n.t("signing secret"))))
        row.addStretch(1)
        self.body.addLayout(row)
        self.body.addWidget(C.label(i18n.t("Each message carries X-Prism-Signature: v1=<HMAC-SHA256 of timestamp.body with this secret>, and X-Prism-Timestamp. Check the "
                                           "signature before you trust a message, and ignore ones whose timestamp is more than a few minutes old."),
                                    level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
        self.body.addStretch(1)
        self.footer.set_primary(self.button(i18n.t("I've copied it"), "primary", on_click=self.accept))
        self.resize(560, 360)


class LogDialog(PrismDialog):
    """The last deliveries to one webhook, with a way to send one again."""

    def __init__(self, endpoint: dict, events: dict, parent=None):
        super().__init__(i18n.t("Delivery log"), endpoint.get("url") or "", icon="list", parent=parent, scrollable=True)
        self.endpoint, self.events = endpoint, events
        self.col = QVBoxLayout()
        self.col.setSpacing(theme.SPACE_2)
        self.body.addLayout(self.col)
        self.note = ui.note()
        self.body.addWidget(self.note)
        self.body.addStretch(1)
        self.footer.set_primary(self.button(i18n.t("Close"), "primary", on_click=self.accept))
        self.resize(620, 560)
        self.load()

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def load(self):
        ui.call(self, "webhooks/deliveries", {"endpoint_id": self.endpoint["id"], "limit": 50}, done=self._loaded, failed=lambda m, _d: self.note.error(m))

    def _loaded(self, reply: dict):
        ui.clear(self.col)
        rows = reply.get("deliveries") or []
        if not rows:
            self.col.addWidget(C.label(i18n.t("Nothing has been sent to this address yet. Use Send a test to try it."), level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
        for d in rows:
            line = QFrame()
            line.setObjectName("waDelivery")
            line.setAttribute(Qt.WA_StyledBackground, True)
            line.setStyleSheet(f"#waDelivery {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
            lc = QVBoxLayout(line)
            lc.setContentsMargins(12, 8, 12, 8)
            lc.setSpacing(2)
            top = QHBoxLayout()
            top.addWidget(C.label(event_words(d.get("event"), self.events), level="SUPPORT", weight=700), stretch=1)
            words, tone = state_words(d.get("state"))
            top.addWidget(C.Pill(words, tone))
            top.addWidget(C.button(i18n.t("Send again"), "tertiary", small=True, on_click=lambda _=False, x=d: self._again(x)))
            lc.addLayout(top)
            facts = [short_time(d.get("created_at") or ""), i18n.t("{n} tries").format(n=d.get("attempts") or 0) if (d.get("attempts") or 0) != 1 else i18n.t("1 try")]
            if d.get("response_status"):
                facts.append(i18n.t("answer {n}").format(n=d["response_status"]))
            lc.addWidget(C.label("  ·  ".join(f for f in facts if f), level="META", colour=theme.NEUTRAL[600]))
            if d.get("error"):
                lc.addWidget(C.label(str(d["error"]), level="META", colour=theme.ERR_INK, wrap=True))
            self.col.addWidget(line)

    def _again(self, d: dict):
        ui.call(self, "webhooks/replay", {"delivery_id": d["id"]}, done=lambda _r: (self.say(i18n.t("Queued. It goes out within a few seconds.")), self.load()),
                failed=lambda m, _d: self.say(m, True))


class WebhooksCard(QWidget):
    """The card in Developers. `say` and the note belong to it, so the section around it stays about keys."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events: dict = {}
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        card, cc = ui.card(i18n.t("Webhooks"), i18n.t("Tell your own systems when something happens here. Part of the Premium plan."), width=720)
        self.list_col = QVBoxLayout()
        self.list_col.setSpacing(theme.SPACE_2)
        cc.addLayout(self.list_col)
        self.note = ui.note()
        cc.addWidget(self.note)
        row = QHBoxLayout()
        self.add_btn = C.button(i18n.t("New webhook"), "primary", icon_name="plus", on_click=self._new)
        row.addWidget(self.add_btn)
        row.addStretch(1)
        cc.addLayout(row)
        col.addWidget(card)

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def load(self):
        ui.call(self, "webhooks/list", {}, done=self._loaded, failed=lambda m, _d: (ui.clear(self.list_col), self.note.error(m)))

    def _loaded(self, reply: dict):
        self._events = dict(reply.get("events") or {})
        ui.clear(self.list_col)
        rows = reply.get("endpoints") or []
        if not rows:
            self.list_col.addWidget(C.label(i18n.t("No webhooks yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for e in rows:
            self.list_col.addWidget(self._row(e))

    def _row(self, e: dict) -> QWidget:
        line = QFrame()
        line.setObjectName("waHook")
        line.setAttribute(Qt.WA_StyledBackground, True)
        line.setStyleSheet(f"#waHook {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(line)
        col.setContentsMargins(14, 12, 14, 10)
        col.setSpacing(4)
        top = QHBoxLayout()
        title = e.get("description") or e.get("url") or ""
        top.addWidget(C.label(title, level="SUPPORT", weight=700), stretch=1)
        top.addWidget(C.Pill(i18n.t("On") if e.get("enabled") else i18n.t("Off"), "ok" if e.get("enabled") else "quiet"))
        col.addLayout(top)
        if e.get("description"):
            col.addWidget(C.label(e.get("url") or "", level="META", colour=theme.NEUTRAL[600]))
        col.addWidget(C.label(", ".join(event_words(k, self._events) for k in e.get("events") or []), level="META", colour=theme.NEUTRAL[700], wrap=True))
        if e.get("disabled_reason"):
            col.addWidget(C.label(e["disabled_reason"], level="META", colour=theme.ERR_INK, wrap=True))
        elif e.get("last_error"):
            col.addWidget(C.label(i18n.t("Last problem: {e}").format(e=e["last_error"]), level="META", colour=theme.WARN_INK, wrap=True))
        elif e.get("last_delivery_at"):
            col.addWidget(C.label(i18n.t("Last sent {t}").format(t=short_time(e["last_delivery_at"])), level="META", colour=theme.NEUTRAL[600]))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_1)
        row.addStretch(1)
        row.addWidget(C.button(i18n.t("Send a test"), "tertiary", on_click=lambda _=False, x=e: self._test(x)))
        row.addWidget(C.button(i18n.t("Log"), "tertiary", on_click=lambda _=False, x=e: self._log(x)))
        row.addWidget(C.button(i18n.t("Turn off") if e.get("enabled") else i18n.t("Turn on"), "tertiary", on_click=lambda _=False, x=e: self._toggle(x)))
        row.addWidget(C.button(i18n.t("New secret"), "tertiary", on_click=lambda _=False, x=e: self._rotate(x)))
        row.addWidget(C.icon_button("trash", i18n.t("Delete this webhook"), on_click=lambda _=False, x=e: self._delete(x), colour=theme.ERR_INK))
        col.addLayout(row)
        return line

    def _new(self):
        dlg = WebhookDialog(self._events, self)
        if dlg.exec() and dlg.created:
            SecretDialog(dlg.created.get("secret") or "", self).exec()
            self.load()

    def _test(self, e: dict):
        ui.call(self, "webhooks/test", {"endpoint_id": e["id"]}, done=lambda _r: self.note.ok(i18n.t("A test message is on its way. Open the log to see what your server answered.")),
                failed=lambda m, _d: self.note.error(m))

    def _log(self, e: dict):
        LogDialog(e, self._events, self).exec()
        self.load()

    def _toggle(self, e: dict):
        ui.call(self, "webhooks/update", {"endpoint_id": e["id"], "changes": {"enabled": not e.get("enabled")}}, done=lambda _r: self.load(), failed=lambda m, _d: self.note.error(m))

    def _rotate(self, e: dict):
        if ui.confirm(self, i18n.t("New secret"), i18n.t("Make a new signing secret? Your server must use the new one, or it will refuse every message.")):
            ui.call(self, "webhooks/rotate_secret", {"endpoint_id": e["id"]}, done=lambda r: SecretDialog(r.get("secret") or "", self).exec(), failed=lambda m, _d: self.note.error(m))

    def _delete(self, e: dict):
        if ui.confirm(self, i18n.t("Delete webhook"), i18n.t("Delete this webhook and its log? Nothing more is sent to it.")):
            ui.call(self, "webhooks/delete", {"endpoint_id": e["id"]}, done=lambda _r: (self.note.ok(i18n.t("Deleted.")), self.load()), failed=lambda m, _d: self.note.error(m))
