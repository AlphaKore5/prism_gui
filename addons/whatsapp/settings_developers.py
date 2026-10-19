"""Settings → Developers: API keys for your own software.

A key lets another program (your billing system, a website form) send WhatsApp messages or read contacts through
Prism's API. You choose exactly what each key may do, so a form on your website can add a contact without being
able to read your chats. The secret is shown ONCE when the key is made — Prism keeps only a fingerprint of it — so
copy it then; a lost key is revoked and replaced, never recovered.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLineEdit, QSpinBox, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.chat import short_time
from addons.whatsapp.settings import _COLUMN, _scrolled
from addons.whatsapp.settings_capi import CapiCard
from addons.whatsapp.settings_webhooks import WebhooksCard
from dialogs.base import PrismDialog
from widgets import controls as C


def scope_words(scope: str) -> str:
    """A permission, as what it lets the key do."""
    table = {"messages:send": i18n.t("Send messages"), "messages:read": i18n.t("Read messages"),
             "template_messages:send": i18n.t("Send template messages"), "contacts:read": i18n.t("Read contacts"),
             "contacts:write": i18n.t("Add and change contacts"), "templates:read": i18n.t("Read templates"),
             "campaigns:read": i18n.t("Read campaigns"), "campaigns:write": i18n.t("Create and send campaigns")}
    return table.get(scope, scope)


class NewKeyDialog(PrismDialog):
    def __init__(self, scopes: list, parent=None):
        super().__init__(i18n.t("New API key"), i18n.t("Choose what this key may do. You can't change it later — make a new key instead."),
                         icon="key", parent=parent, scrollable=True)
        self.name = QLineEdit()
        self.name.setPlaceholderText(i18n.t("What it is for, e.g. Website contact form"))
        self.name.setMinimumHeight(38)
        self.body.addWidget(ui.field(i18n.t("Name"), self.name))
        self.boxes: dict = {}
        holder = QVBoxLayout()
        holder.setSpacing(theme.SPACE_1)
        for scope in scopes:
            b = QCheckBox(scope_words(scope))
            b.setToolTip(scope)
            self.boxes[scope] = b
            holder.addWidget(b)
        self.body.addWidget(ui.field(i18n.t("It may"), holder))
        self.rate = QSpinBox()
        self.rate.setRange(1, 6000)
        self.rate.setValue(60)
        self.rate.setSuffix(i18n.t(" a minute"))
        self.rate.setMinimumHeight(36)
        self.body.addWidget(ui.field(i18n.t("Limit"), self.rate, i18n.t("Calls beyond this in a minute are refused.")))
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.go = self.button(i18n.t("Create key"), "primary", on_click=self._go)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.go)
        self.resize(520, 620)
        self.created = None

    def scopes(self) -> list:
        return [s for s, b in self.boxes.items() if b.isChecked()]

    def _go(self):
        if not self.name.text().strip():
            self.error.error(i18n.t("Give the key a name."))
            return
        if not self.scopes():
            self.error.error(i18n.t("Choose at least one thing it may do."))
            return
        self.go.setEnabled(False)
        ui.call(self, "api_keys/create", {"name": self.name.text().strip(), "scopes": self.scopes(), "rate_limit_per_minute": self.rate.value()},
                done=self._done, failed=self._failed)

    def _failed(self, message: str, _detail: dict):
        self.go.setEnabled(True)
        self.error.error(message)

    def _done(self, reply: dict):
        self.created = reply.get("key") or {}
        self.accept()


class SecretDialog(PrismDialog):
    """The one time the secret is shown."""

    def __init__(self, key: dict, parent=None):
        super().__init__(i18n.t("Your new key"), i18n.t("Copy it now. This is the only time it is shown."), icon="key", parent=parent)
        self.secret = key.get("secret") or ""
        edit = QLineEdit(self.secret)
        edit.setReadOnly(True)
        edit.setMinimumHeight(40)
        edit.setAccessibleName(i18n.t("The API key"))
        edit.selectAll()
        self.body.addWidget(edit)
        row = QHBoxLayout()
        row.addWidget(C.button(i18n.t("Copy key"), "primary", on_click=lambda: ui.copy_text(self, self.secret, i18n.t("API key"))))
        row.addStretch(1)
        self.body.addLayout(row)
        self.body.addWidget(C.label(i18n.t("Send it with each request as the header  Authorization: Bearer <key>.  Keep it out of web pages and "
                                           "shared files — anyone who has it can do what you allowed."), level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
        self.body.addStretch(1)
        self.footer.set_primary(self.button(i18n.t("I've copied it"), "primary", on_click=self.accept))
        self.resize(520, 340)


class DevelopersSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self._scopes: list = []
        card, cc = ui.card(i18n.t("API keys"), i18n.t("Let your own software use WhatsApp through Prism."), width=_COLUMN)
        self.base = C.label("", level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True)
        cc.addWidget(self.base)
        self.list_col = QVBoxLayout()
        self.list_col.setSpacing(theme.SPACE_2)
        cc.addLayout(self.list_col)
        self.note = ui.note()
        cc.addWidget(self.note)
        row = QHBoxLayout()
        row.addWidget(C.button(i18n.t("New API key"), "primary", icon_name="plus", on_click=self._new))
        row.addStretch(1)
        cc.addLayout(row)
        col.addWidget(card)
        self.hooks = WebhooksCard()
        col.addWidget(self.hooks)
        self.capi = CapiCard()
        col.addWidget(self.capi)
        col.addStretch(1)

    def say(self, text: str, error: bool = False):
        self.note.set(text, "error" if error else "ok")

    def activate(self):
        ui.call(self, "api_keys/list", done=self._loaded, failed=lambda m, _d: (ui.clear(self.list_col), self.say(m, error=True)))
        self.hooks.load()
        self.capi.load()

    def _loaded(self, reply: dict):
        self.say("")
        self._scopes = list(reply.get("scopes") or [])
        base = reply.get("base_url") or ""
        self.base.setText(i18n.t("Address: {b}").format(b=base) if base else "")
        ui.clear(self.list_col)
        keys = reply.get("keys") or []
        if not keys:
            self.list_col.addWidget(C.label(i18n.t("No keys yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for k in keys:
            self.list_col.addWidget(self._row(k))

    def _row(self, k: dict) -> QWidget:
        revoked = bool(k.get("revoked_at"))
        line = QFrame()
        line.setObjectName("waKey")
        line.setAttribute(Qt.WA_StyledBackground, True)
        line.setStyleSheet(f"#waKey {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(line)
        col.setContentsMargins(14, 12, 14, 10)
        col.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(C.label(k.get("name") or "", level="SUPPORT", weight=700), stretch=1)
        top.addWidget(C.Pill(i18n.t("Revoked") if revoked else i18n.t("Active"), "quiet" if revoked else "ok"))
        col.addLayout(top)
        used = short_time(k.get("last_used_at") or "")
        col.addWidget(C.label("%s…  ·  %s" % (k.get("prefix") or "", i18n.t("last used {t}").format(t=used) if used else i18n.t("never used")),
                              level="META", colour=theme.NEUTRAL[600]))
        col.addWidget(C.label(", ".join(scope_words(s) for s in k.get("scopes") or []), level="META", colour=theme.NEUTRAL[700], wrap=True))
        if not revoked:
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(C.button(i18n.t("Revoke"), "tertiary", on_click=lambda _=False, x=k: self._revoke(x)))
            col.addLayout(row)
        return line

    def _new(self):
        dlg = NewKeyDialog(self._scopes, self)
        if dlg.exec() and dlg.created:
            SecretDialog(dlg.created, self).exec()
            self.activate()

    def _revoke(self, k: dict):
        if ui.confirm(self, i18n.t("Revoke key"), i18n.t("Revoke “{n}”? Anything using it stops working at once. This can't be undone.").format(n=k.get("name"))):
            ui.call(self, "api_keys/revoke", {"key_id": k["id"]}, done=lambda r: (self.say(i18n.t("Revoked.")), self.activate()))
