"""Shop → Settings: your catalogue, your prices, and how customers pay.

Two ways to be paid inside a chat. *Razorpay payment links* need only a Razorpay account: Prism makes a link for the order and sends it as a button, and Razorpay tells Prism when
it is paid. *Pay inside WhatsApp* needs Meta's payments set up in WhatsApp Manager first (it takes Meta's approval); then the customer pays by UPI without leaving the chat.
The gateway's secret is stored encrypted on the server and is never shown again.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import shop_money as M
from addons.whatsapp import ui
from addons.whatsapp.settings import _COLUMN, _scrolled
from widgets import controls as C


def _line(placeholder: str = "", text: str = "", secret: bool = False) -> QLineEdit:
    e = QLineEdit(text)
    e.setMinimumHeight(38)
    e.setPlaceholderText(placeholder)
    if secret:
        e.setEchoMode(QLineEdit.Password)
    return e


class ShopSettingsView(QWidget):
    def __init__(self, shop, parent=None):
        super().__init__(parent)
        self.shop = shop
        self.config: dict = {}
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)

        card, cc = ui.card(i18n.t("Your catalogue"), i18n.t("The products customers browse and put in a cart inside WhatsApp. Make one in Meta's Commerce Manager and connect it to your number."), _COLUMN)
        self.catalog_id = _line("5551234567")
        self.catalog_id.setAccessibleName(i18n.t("Catalogue number"))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        row.addWidget(self.catalog_id, 1)
        self.find_btn = C.button(i18n.t("Find mine"), "secondary", on_click=self.find_catalogs)
        row.addWidget(self.find_btn)
        cc.addWidget(ui.field(i18n.t("Catalogue number"), row, i18n.t("The number shown for your catalogue in Commerce Manager.")))
        self.found = QComboBox()
        self.found.setMinimumHeight(38)
        self.found.setAccessibleName(i18n.t("Your catalogues"))
        self.found.setVisible(False)
        self.found.activated.connect(self._picked)
        cc.addWidget(self.found)
        self.catalog_name = _line(i18n.t("Shakti shop"))
        self.catalog_name.setAccessibleName(i18n.t("Catalogue name"))
        cc.addWidget(ui.field(i18n.t("Name"), self.catalog_name))
        self.show_catalog = QCheckBox(i18n.t("Show the catalogue button at the top of every chat"))
        self.cart = QCheckBox(i18n.t("Let customers add products to a cart"))
        cc.addWidget(self.show_catalog)
        cc.addWidget(self.cart)
        vis = QHBoxLayout()
        self.visibility_btn = C.button(i18n.t("Apply to my number"), "secondary", on_click=self.save_visibility)
        vis.addWidget(self.visibility_btn)
        vis.addStretch(1)
        cc.addLayout(vis)
        col.addWidget(card)

        card, pc = ui.card(i18n.t("Prices"), i18n.t("Used for every new order. Tax is worked out on the price after any discount."), _COLUMN)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.currency = _line("INR")
        self.currency.setMaxLength(3)
        self.currency.setAccessibleName(i18n.t("Currency"))
        self.tax = _line("18")
        self.tax.setAccessibleName(i18n.t("Tax percent"))
        self.shipping = _line("50")
        self.shipping.setAccessibleName(i18n.t("Shipping charge"))
        self.expiry = _line("48")
        self.expiry.setAccessibleName(i18n.t("Hours a payment request stays open"))
        row.addWidget(ui.field(i18n.t("Currency"), self.currency), 1, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Tax (%)"), self.tax), 1, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Shipping (Rs)"), self.shipping), 1, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Request open (hours)"), self.expiry), 1, Qt.AlignTop)
        pc.addLayout(row)
        col.addWidget(card)

        card, gc = ui.card(i18n.t("How customers pay"), "", _COLUMN)
        head = QHBoxLayout()
        self.ready = C.Pill("", "quiet")
        head.addStretch(1)
        head.addWidget(self.ready)
        gc.addLayout(head)
        self.gateway = QComboBox()
        self.gateway.setMinimumHeight(38)
        self.gateway.setAccessibleName(i18n.t("Way of paying"))
        self.gateway.addItem(i18n.t("Not set up yet"), "none")
        self.gateway.addItem(i18n.t("Razorpay payment links"), "razorpay")
        self.gateway.addItem(i18n.t("Pay inside WhatsApp (Meta payments)"), "meta")
        self.gateway.currentIndexChanged.connect(self._gateway_changed)
        gc.addWidget(ui.field(i18n.t("Way of paying"), self.gateway))
        self.razorpay_box = QWidget()
        rc = QVBoxLayout(self.razorpay_box)
        rc.setContentsMargins(0, 0, 0, 0)
        rc.setSpacing(theme.SPACE_3)
        self.key_id = _line("rzp_live_…")
        self.key_id.setAccessibleName(i18n.t("Razorpay key id"))
        self.key_secret = _line("", secret=True)
        self.key_secret.setAccessibleName(i18n.t("Razorpay key secret"))
        self.hook_secret = _line("", secret=True)
        self.hook_secret.setAccessibleName(i18n.t("Razorpay webhook secret"))
        rc.addWidget(ui.field(i18n.t("Key id"), self.key_id, i18n.t("From Razorpay → Account & Settings → API keys.")))
        rc.addWidget(ui.field(i18n.t("Key secret"), self.key_secret, i18n.t("Stored encrypted; leave blank to keep the one saved.")))
        rc.addWidget(ui.field(i18n.t("Webhook secret"), self.hook_secret, i18n.t("Make up a long secret, put it here and in Razorpay's webhook settings.")))
        self.hook_url = _line()
        self.hook_url.setReadOnly(True)
        self.hook_url.setAccessibleName(i18n.t("Webhook address"))
        hook_row = QHBoxLayout()
        hook_row.setSpacing(theme.SPACE_2)
        hook_row.addWidget(self.hook_url, 1)
        self.copy_btn = C.button(i18n.t("Copy"), "secondary", on_click=lambda: ui.copy_text(self, self.hook_url.text(), i18n.t("Webhook address")))
        hook_row.addWidget(self.copy_btn)
        rc.addWidget(ui.field(i18n.t("Webhook address"), hook_row, i18n.t("In Razorpay → Webhooks, add this address and tick: payment_link.paid, payment_link.expired, "
                                                                      "payment_link.cancelled, payment.failed.")))
        gc.addWidget(self.razorpay_box)
        self.meta_box = QWidget()
        mc = QVBoxLayout(self.meta_box)
        mc.setContentsMargins(0, 0, 0, 0)
        self.payment_config = _line("shakti-upi")
        self.payment_config.setAccessibleName(i18n.t("Payment configuration name"))
        mc.addWidget(ui.field(i18n.t("Payment configuration name"), self.payment_config,
                              i18n.t("The name of the payment setup in WhatsApp Manager → Payments. It needs Meta's approval first, and the customer's phone must support it.")))
        gc.addWidget(self.meta_box)
        col.addWidget(card)

        self.note = ui.note()
        col.addWidget(self.note)
        row = QHBoxLayout()
        self.save_btn = C.button(i18n.t("Save"), "primary", on_click=self.save)
        row.addWidget(self.save_btn)
        row.addStretch(1)
        col.addLayout(row)
        col.addStretch(1)
        self._gateway_changed()

    def say(self, message: str, error: bool = False):
        self.note.set(message, "error" if error else "ok")

    def load(self):
        ui.call(self, "commerce/config/get", {}, done=self._loaded)
        ui.call(self, "catalog/visibility", {}, done=self._visible, failed=lambda m, _d: None)

    def _visible(self, r: dict):
        self.show_catalog.setChecked(bool(r.get("catalog_visible")))
        self.cart.setChecked(bool(r.get("cart_enabled")))

    def _loaded(self, reply: dict):
        c = self.config = reply["config"]
        self.catalog_id.setText(c.get("catalog_id") or "")
        self.catalog_name.setText(c.get("catalog_name") or "")
        self.currency.setText(c.get("currency") or "INR")
        self.tax.setText(("%g" % c.get("tax_percent", 0)))
        self.shipping.setText(M.rupees(c.get("shipping_paise", 0)).replace(",", ""))
        self.expiry.setText(str(c.get("order_expiry_hours", 48)))
        self.gateway.setCurrentIndex(max(self.gateway.findData(c.get("gateway") or "none"), 0))
        self.key_id.setText(c.get("razorpay_key_id") or "")
        self.key_secret.clear()
        self.hook_secret.clear()
        self.key_secret.setPlaceholderText(i18n.t("Saved — leave blank to keep") if c.get("razorpay_secret_set") else "")
        self.hook_secret.setPlaceholderText(i18n.t("Saved — leave blank to keep") if c.get("razorpay_webhook_set") else "")
        self.payment_config.setText(c.get("payment_configuration") or "")
        self.hook_url.setText(c.get("webhook_url") or "")
        self._gateway_changed()
        self._pill()

    def _pill(self):
        if self.config.get("ready"):
            self.ready.setText(i18n.t("Ready to take payments"))
            self.ready.set_tone("ok")
        else:
            self.ready.setText(i18n.t("Not ready to take payments"))
            self.ready.set_tone("warn")

    def _gateway_changed(self, *_):
        kind = self.gateway.currentData()
        self.razorpay_box.setVisible(kind == "razorpay")
        self.meta_box.setVisible(kind == "meta")

    def find_catalogs(self):
        ui.call(self, "catalog/catalogs", {}, done=self._catalogs)

    def _catalogs(self, reply: dict):
        rows = list(reply.get("catalogs") or [])
        self.found.clear()
        for c in rows:
            self.found.addItem("%s  ·  %s" % (c.get("name") or i18n.t("Catalogue"), c["id"]), c)
        self.found.setVisible(bool(rows))
        if rows:
            self._picked()
        else:
            self.say(i18n.t("Meta shows no catalogue connected to your number. Connect one in Commerce Manager."), error=True)

    def _picked(self, *_):
        c = self.found.currentData()
        if c:
            self.catalog_id.setText(str(c["id"]))
            self.catalog_name.setText(c.get("name") or "")

    def payload(self) -> dict:
        d = {"catalog_id": self.catalog_id.text().strip(), "catalog_name": self.catalog_name.text().strip(), "currency": self.currency.text().strip() or "INR",
             "tax_percent": self.tax.text().strip() or "0", "shipping": self.shipping.text().strip() or "0", "order_expiry_hours": self.expiry.text().strip() or "48",
             "gateway": self.gateway.currentData(), "payment_configuration": self.payment_config.text().strip(), "razorpay_key_id": self.key_id.text().strip()}
        if self.key_secret.text().strip():
            d["razorpay_secret"] = self.key_secret.text().strip()
        if self.hook_secret.text().strip():
            d["razorpay_webhook_secret"] = self.hook_secret.text().strip()
        return d

    def save(self):
        self.save_btn.setEnabled(False)
        ui.call(self, "commerce/config/save", self.payload(), done=self._saved, failed=self._save_failed)

    def _saved(self, reply: dict):
        self.save_btn.setEnabled(True)
        self._loaded(reply)
        self.say(i18n.t("Saved.") if reply["config"].get("ready") else i18n.t("Saved. Customers can't be asked to pay yet — finish the way of paying above."))

    def _save_failed(self, message: str, _detail: dict):
        self.save_btn.setEnabled(True)
        self.say(message, error=True)

    def save_visibility(self):
        ui.call(self, "catalog/set_visibility", {"catalog_visible": self.show_catalog.isChecked(), "cart_enabled": self.cart.isChecked()},
                done=lambda r: (self._visible(r), self.say(i18n.t("Your number now shows these in chats."))))
