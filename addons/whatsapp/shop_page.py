"""The Shop tab — sell inside the chat.

    Products   what you sell, sent to customers as cards, and kept in step with your Meta catalogue
    Orders     carts customers sent from WhatsApp and orders you make; ask for payment, then follow each one to done
    Payments   money received, money given back, what is still waiting, who to remind
    Settings   your catalogue, tax and shipping, and how customers pay (Razorpay links or Meta's payments)

Each section is built the first time it is opened. Everything goes through Prism's licence server; nothing here needs to be configured in the app itself.
"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from widgets import controls as C

SECTIONS = ("products", "orders", "payments", "settings")


class ShopPage(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self._section = "products"
        self._views: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SPACE_4, theme.SPACE_4, theme.SPACE_4, theme.SPACE_4)
        root.setSpacing(theme.SPACE_3)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(C.label(i18n.t("Shop"), level="CARD_TITLE"))
        titles.addWidget(C.label(i18n.t("Show products in the chat, take a cart, ask for payment and follow each order — without leaving WhatsApp."), level="SUPPORT",
                                 colour=theme.NEUTRAL[600], wrap=True))
        head.addLayout(titles, 1)
        root.addLayout(head)
        self.note = ui.note()
        root.addWidget(self.note)
        self.chips = C.FilterChips([("products", i18n.t("Products")), ("orders", i18n.t("Orders")), ("payments", i18n.t("Payments")), ("settings", i18n.t("Settings"))], "products")
        self.chips.setMinimumWidth(400)
        self.chips.changed.connect(self.show_section)
        root.addWidget(self.chips)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        for key in SECTIONS:
            self._view(key)

    def say(self, text: str, error: bool = False):
        self.note.set(text, "error" if error else "ok")

    def _view(self, key: str) -> QWidget:
        if key not in self._views:
            if key == "products":
                from addons.whatsapp.shop_products import ProductsView
                w = ProductsView(self)
            elif key == "orders":
                from addons.whatsapp.shop_orders import OrdersView
                w = OrdersView(self)
            elif key == "payments":
                from addons.whatsapp.shop_payments import PaymentsView
                w = PaymentsView(self)
            else:
                from addons.whatsapp.shop_settings import ShopSettingsView
                w = ShopSettingsView(self)
            self._views[key] = w
            self.stack.addWidget(w)
        return self._views[key]

    # ── lifecycle ────────────────────────────────────────────────────────────
    def activate(self):
        self.show_section(self._section)

    def deactivate(self):
        pass

    def show_section(self, key: str):
        self._section = key
        self.chips.set_current(key)
        view = self._view(key)
        self.stack.setCurrentWidget(view)
        view.load()

    def open_order(self, order_id: str):
        """From Payments: jump to the order a payment belongs to."""
        self.show_section("orders")
        self._view("orders").open({"id": order_id})

    def start_order_for(self, contact: dict):
        """From the Inbox or Contacts: begin an order for this person."""
        self.show_section("orders")
        self._view("orders").new(contact)
