"""Settings → Stores: a Shopify or WooCommerce order becomes a WhatsApp message.

You connect a store once: give it a name and the signing secret the store uses, say which events should send a message
(an order placed, an order shipped, a cart left behind) and which approved template each one uses, and what goes in the
template's blanks. Prism gives you the address to paste into the store's webhook settings.

Consent matters here. A store message is Prism messaging a customer first, so the person must have agreed to hear from
you. If your checkout asks for that, tick the box and every message records that they did; if it does not, only people
who have already agreed are messaged.
"""
from __future__ import annotations


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLineEdit, QSpinBox, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.settings import _COLUMN, _scrolled
from addons.whatsapp.template_editor import variables_of
from dialogs.base import PrismDialog
from widgets import controls as C

FIXED = "="                                                      # "=text" in a mapping is a fixed string


def _events() -> list:
    # (key, what it sends on, hint)
    return [("order_created", i18n.t("An order is placed"), i18n.t("Thank them and confirm the order.")),
            ("order_fulfilled", i18n.t("An order is shipped"), i18n.t("Tell them it is on its way, with tracking.")),
            ("abandoned_cart", i18n.t("A cart is left behind"), i18n.t("Remind them after a while — not if they order meanwhile."))]


def _fields() -> list:
    return [("customer.first_name", i18n.t("Customer's first name")), ("customer.name", i18n.t("Customer's full name")),
            ("customer.phone", i18n.t("Customer's phone")), ("order.name", i18n.t("Order number, like #1001")),
            ("order.id", i18n.t("Order id")), ("order.total", i18n.t("Order total")), ("order.currency", i18n.t("Currency")),
            ("order.status_url", i18n.t("Order status link")), ("tracking.number", i18n.t("Tracking number")),
            ("tracking.url", i18n.t("Tracking link")), ("tracking.company", i18n.t("Courier")),
            ("checkout.url", i18n.t("Link back to the cart")), ("checkout.total", i18n.t("Cart total")),
            (FIXED, i18n.t("The same text every time…"))]


class _EventBox(QFrame):
    def __init__(self, key: str, title: str, hint: str, templates: list, parent=None):
        super().__init__(parent)
        self.key, self.templates = key, templates
        self.setObjectName("waEvent")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#waEvent {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 12, 14, 12)
        col.setSpacing(theme.SPACE_2)
        self.on = QCheckBox(i18n.t("Send a message when {what}").format(what=title.lower()))
        self.on.toggled.connect(self._toggled)
        col.addWidget(self.on)
        col.addWidget(C.label(hint, level="META", colour=theme.NEUTRAL[500], wrap=True))
        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(theme.SPACE_2)
        self.template = QComboBox()
        self.template.setMinimumHeight(36)
        self.template.setAccessibleName(i18n.t("Template for {what}").format(what=title.lower()))
        for t in templates:
            self.template.addItem("%s · %s" % (t.get("name"), t.get("language")), t)
        self.template.currentIndexChanged.connect(self._rebuild)
        bl.addWidget(self.template)
        self.vars_col = QVBoxLayout()
        self.vars_col.setSpacing(theme.SPACE_1)
        bl.addLayout(self.vars_col)
        self.delay = None
        if key == "abandoned_cart":
            self.delay = QSpinBox()
            self.delay.setRange(5, 24 * 60)
            self.delay.setValue(60)
            self.delay.setSuffix(i18n.t(" min"))
            self.delay.setMinimumHeight(34)
            bl.addWidget(ui.field(i18n.t("Wait before reminding"), self.delay))
        col.addWidget(self.body)
        self.rows: dict = {}
        self.body.hide()
        if not templates:
            self.on.setEnabled(False)
            col.addWidget(C.label(i18n.t("You need an approved template first — write one in the Templates tab."), level="META", colour=theme.WARN_INK, wrap=True))

    def _toggled(self, on: bool):
        self.body.setVisible(on)

    def current_template(self) -> dict:
        return self.template.currentData() or {}

    def _rebuild(self, *_):
        old = {n: (c.currentData(), e.text()) for n, (c, e) in self.rows.items()}
        ui.clear(self.vars_col)
        self.rows = {}
        text = ""
        for comp in self.current_template().get("components") or []:
            if comp.get("type") == "BODY":
                text = comp.get("text", "")
        for n in variables_of(text):
            row = QHBoxLayout()
            tag = C.label("{{%d}}" % n, level="SUPPORT", weight=700)
            tag.setMinimumWidth(48)
            row.addWidget(tag)
            combo = QComboBox()
            combo.setMinimumHeight(34)
            for value, label in _fields():
                combo.addItem(label, value)
            edit = QLineEdit()
            edit.setMinimumHeight(34)
            edit.setPlaceholderText(i18n.t("The text"))
            combo.currentIndexChanged.connect(lambda _i, c=combo, e=edit: e.setVisible(c.currentData() == FIXED))
            if str(n) in old:
                combo.setCurrentIndex(max(combo.findData(old[str(n)][0]), 0))
                edit.setText(old[str(n)][1])
            edit.setVisible(combo.currentData() == FIXED)
            row.addWidget(combo, 2)
            row.addWidget(edit, 2)
            box = QWidget()
            box.setLayout(row)
            self.vars_col.addWidget(box)
            self.rows[str(n)] = (combo, edit)

    def value(self):
        if not self.on.isChecked() or not self.current_template():
            return None
        t = self.current_template()
        variables = {}
        for n, (combo, edit) in self.rows.items():
            variables[n] = ("=" + edit.text().strip()) if combo.currentData() == FIXED else combo.currentData()
        out = {"template": t.get("name"), "language": t.get("language") or "en_US", "variables": variables, "enabled": True}
        if self.delay is not None:
            out["delay_minutes"] = self.delay.value()
        return out

    def set_value(self, spec: dict):
        self.on.setChecked(bool(spec))
        if not spec:
            return
        i = next((k for k in range(self.template.count()) if self.template.itemData(k).get("name") == spec.get("template")), -1)
        if i >= 0:
            self.template.setCurrentIndex(i)
        self._rebuild()
        for n, value in (spec.get("variables") or {}).items():
            if n in self.rows:
                combo, edit = self.rows[n]
                if str(value).startswith(FIXED):
                    combo.setCurrentIndex(combo.findData(FIXED))
                    edit.setText(str(value)[1:])
                else:
                    combo.setCurrentIndex(max(combo.findData(value), 0))
        if self.delay is not None and spec.get("delay_minutes"):
            self.delay.setValue(int(spec["delay_minutes"]))


class StoreDialog(PrismDialog):
    def __init__(self, templates: list, store: dict = None, parent=None):
        editing = bool(store)
        store = store or {}
        super().__init__(i18n.t("Change store connection") if editing else i18n.t("Connect a store"),
                         i18n.t("Orders in your store become WhatsApp messages to your customers."), icon="globe", parent=parent, scrollable=True)
        self.editing = editing
        self.store = store
        self.kind = QComboBox()
        self.kind.setMinimumHeight(38)
        self.kind.addItem("Shopify", "shopify")
        self.kind.addItem("WooCommerce", "woocommerce")
        if editing:
            self.kind.setCurrentIndex(max(self.kind.findData(store.get("kind")), 0))
            self.kind.setEnabled(False)
        self.body.addWidget(ui.field(i18n.t("Store type"), self.kind))
        self.name = QLineEdit(store.get("name", "") if editing else "")
        self.name.setPlaceholderText(i18n.t("e.g. Main shop"))
        self.name.setMinimumHeight(38)
        self.body.addWidget(ui.field(i18n.t("Name"), self.name))
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.Password)
        self.secret.setMinimumHeight(38)
        self.secret.setPlaceholderText(i18n.t("Leave empty to keep the current secret") if editing else i18n.t("The secret your store signs its messages with"))
        self.body.addWidget(ui.field(i18n.t("Signing secret"), self.secret,
                                     i18n.t("Shopify: Settings, then Notifications, then Webhooks. WooCommerce: the webhook's Secret field.")))
        config = store.get("config") or {}
        self.boxes: dict = {}
        for key, title, hint in _events():
            box = _EventBox(key, title, hint, templates)
            box._rebuild()
            box.set_value((config.get("events") or {}).get(key))
            self.boxes[key] = box
            self.body.addWidget(box)
        self.consent = QCheckBox(i18n.t("My checkout asks customers to agree to WhatsApp messages"))
        self.consent.setChecked(bool(config.get("consent_attested")))
        self.body.addWidget(self.consent)
        self.body.addWidget(C.label(i18n.t("Tick this only if it is true. Each message then records their agreement with the order as proof. "
                                           "Without it, only people who have already agreed are messaged."), level="META", colour=theme.NEUTRAL[600], wrap=True))
        self.country = QLineEdit(str(config.get("default_country") or "91"))
        self.country.setMaximumWidth(120)
        self.country.setMinimumHeight(36)
        self.body.addWidget(ui.field(i18n.t("Country code for numbers without one"), self.country))
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.go = self.button(i18n.t("Save") if editing else i18n.t("Connect"), "primary", on_click=self._go)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.go)
        self.resize(660, 780)

    def config(self) -> dict:
        events = {k: v for k, v in ((k, b.value()) for k, b in self.boxes.items()) if v}
        return {"events": events, "consent_attested": self.consent.isChecked(), "default_country": self.country.text().strip() or "91"}

    def _go(self):
        if not self.name.text().strip():
            self.error.error(i18n.t("Give the connection a name."))
            return
        if not self.editing and len(self.secret.text().strip()) < 8:
            self.error.error(i18n.t("Paste the store's signing secret."))
            return
        if not self.config()["events"]:
            self.error.error(i18n.t("Choose at least one thing to send a message about."))
            return
        data = {"name": self.name.text().strip(), "config": self.config()}
        if self.editing:
            data["integration_id"] = self.store["id"]
            if self.secret.text().strip():
                data["secret"] = self.secret.text().strip()
            route = "integrations/update"
        else:
            data.update(kind=self.kind.currentData(), secret=self.secret.text().strip())
            route = "integrations/create"
        self.go.setEnabled(False)
        ui.call(self, route, data, done=self._done, failed=self._failed)

    def _failed(self, message: str, _detail: dict):
        self.go.setEnabled(True)
        self.error.error(message)

    def _done(self, reply: dict):
        self.created = reply.get("integration")
        self.accept()


class StoresSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self._templates: list = []
        card, cc = ui.card(i18n.t("Connected stores"),
                           i18n.t("When an order is placed, shipped or abandoned in your store, the customer gets a WhatsApp message."), width=_COLUMN)
        self.list_col = QVBoxLayout()
        self.list_col.setSpacing(theme.SPACE_2)
        cc.addLayout(self.list_col)
        self.note = ui.note()
        cc.addWidget(self.note)
        row = QHBoxLayout()
        row.addWidget(C.button(i18n.t("Connect a store"), "primary", icon_name="plus", on_click=self._new))
        row.addStretch(1)
        cc.addLayout(row)
        col.addWidget(card)
        self.howto = ui.card(i18n.t("Finish in your store"), "", width=_COLUMN)
        self.howto[0].hide()
        self.howto_text = C.label("", level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True)
        self.howto[1].addWidget(self.howto_text)
        col.addWidget(self.howto[0])
        col.addStretch(1)

    def say(self, text: str, error: bool = False):
        self.note.set(text, "error" if error else "ok")

    def activate(self):
        ui.call(self, "templates/list", done=lambda r: setattr(self, "_templates", [t for t in r.get("templates") or [] if str(t.get("status")).upper() == "APPROVED"]),
                failed=lambda m, _d: None)
        ui.call(self, "integrations/list", done=self._loaded, failed=lambda m, _d: self._failed(m))

    def _failed(self, message: str):
        ui.clear(self.list_col)
        self.say(message, error=True)

    def _loaded(self, reply: dict):
        self.say("")
        ui.clear(self.list_col)
        rows = reply.get("integrations") or []
        if not rows:
            self.list_col.addWidget(C.label(i18n.t("No store is connected yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for s in rows:
            self.list_col.addWidget(self._row(s))

    def _row(self, s: dict) -> QWidget:
        line = QFrame()
        line.setObjectName("waStore")
        line.setAttribute(Qt.WA_StyledBackground, True)
        line.setStyleSheet(f"#waStore {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(line)
        col.setContentsMargins(14, 12, 14, 10)
        col.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(C.label(s.get("name") or "", level="SUPPORT", weight=700), stretch=1)
        top.addWidget(C.Pill("Shopify" if s.get("kind") == "shopify" else "WooCommerce", "neutral"))
        sw = C.ToggleSwitch()
        sw.setChecked(bool(s.get("enabled")))
        sw.setToolTip(i18n.t("Pause or resume this connection"))
        sw.toggled.connect(lambda on, x=s: ui.call(self, "integrations/update", {"integration_id": x["id"], "enabled": on},
                                                   done=lambda r: self.say(i18n.t("Saved.")), failed=lambda m, _d: (self.say(m, error=True), self.activate())))
        top.addWidget(sw)
        col.addLayout(top)
        names = {key: title for key, title, _h in _events()}
        on = [names[k] for k in (s.get("config") or {}).get("events", {}) if k in names]
        col.addWidget(C.label(i18n.t("Messages on: {e}").format(e=", ".join(on).lower() or "—"), level="META", colour=theme.NEUTRAL[600], wrap=True))
        url = s.get("url") or s.get("path") or ""
        if url:
            link = QHBoxLayout()
            edit = QLineEdit(url)
            edit.setReadOnly(True)
            edit.setMinimumHeight(32)
            edit.setAccessibleName(i18n.t("Webhook address"))
            link.addWidget(edit, 1)
            link.addWidget(C.button(i18n.t("Copy address"), "tertiary", on_click=lambda _=False, u=url: ui.copy_text(self, u, i18n.t("Paste it into your store's webhook settings"))))
            col.addLayout(link)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(C.button(i18n.t("Change"), "tertiary", on_click=lambda _=False, x=s: self._edit(x)))
        actions.addWidget(C.icon_button("trash", i18n.t("Disconnect this store"), on_click=lambda _=False, x=s: self._delete(x), colour=theme.ERR_INK))
        col.addLayout(actions)
        return line

    def _new(self):
        dlg = StoreDialog(self._templates, None, self)
        if dlg.exec():
            made = getattr(dlg, "created", None) or {}
            if made.get("url") or made.get("path"):
                self.howto[0].show()
                self.howto_text.setText(i18n.t("Paste this address into your store's webhook settings, with the same signing secret you just gave: {u}").format(
                    u=made.get("url") or made.get("path")))
            self.activate()

    def _edit(self, s: dict):
        if StoreDialog(self._templates, s, self).exec():
            self.say(i18n.t("Saved."))
            self.activate()

    def _delete(self, s: dict):
        if ui.confirm(self, i18n.t("Disconnect store"), i18n.t("Disconnect “{n}”? Orders there will stop sending messages.").format(n=s.get("name"))):
            ui.call(self, "integrations/delete", {"integration_id": s["id"]}, done=lambda r: self.activate())
