"""Shop → Products: what you sell, as customers see it in the chat.

Products live here and, if you want, in your Meta catalogue too: "Get from Meta" reads it in, "Send to Meta" writes ours out. A product can be sent to a chat as a card, and a
customer who builds a cart from your catalogue arrives under Orders. Prices are in rupees; the screen turns them into whole paise before anything is saved.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.contact_picker import ContactChoice
from addons.whatsapp.shop_money import money_text
from dialogs.base import PrismDialog
from widgets import controls as C


def _line(placeholder: str = "", text: str = "") -> QLineEdit:
    e = QLineEdit(text)
    e.setMinimumHeight(38)
    e.setPlaceholderText(placeholder)
    return e


class ProductDialog(PrismDialog):
    def __init__(self, product: dict = None, parent=None):
        self.product = product or {}
        super().__init__(i18n.t("Edit product") if product else i18n.t("New product"), i18n.t("What a customer sees when you send it in a chat."), icon="list", parent=parent, scrollable=True)
        p = self.product
        self.name = _line(i18n.t("Boundary wall panel"), p.get("name") or "")
        self.name.setAccessibleName(i18n.t("Name"))
        self.body.addWidget(ui.field(i18n.t("Name"), self.name))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.price = _line("1299.50", ("%.2f" % (p["price_paise"] / 100.0)) if p.get("price_paise") is not None else "")
        self.price.setAccessibleName(i18n.t("Price"))
        self.sale = _line(i18n.t("optional"), ("%.2f" % (p["sale_price_paise"] / 100.0)) if p.get("sale_price_paise") is not None else "")
        self.sale.setAccessibleName(i18n.t("Sale price"))
        row.addWidget(ui.field(i18n.t("Price (Rs)"), self.price), 1)
        row.addWidget(ui.field(i18n.t("Sale price (Rs)"), self.sale, i18n.t("Shown instead of the price when set.")), 1)
        self.body.addLayout(row)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.retailer = _line(i18n.t("made from the name"), p.get("retailer_id") or "")
        self.retailer.setAccessibleName(i18n.t("Product code"))
        self.category = _line(i18n.t("Walls"), p.get("category") or "")
        self.category.setAccessibleName(i18n.t("Group"))
        row.addWidget(ui.field(i18n.t("Product code"), self.retailer, i18n.t("Your own code for it. Meta calls it the retailer id.")), 1)
        row.addWidget(ui.field(i18n.t("Group"), self.category), 1)
        self.body.addLayout(row)
        self.description = QPlainTextEdit(p.get("description") or "")
        self.description.setMinimumHeight(80)
        self.description.setAccessibleName(i18n.t("Description"))
        self.body.addWidget(ui.field(i18n.t("Description"), self.description))
        self.image = _line("https://", p.get("image_url") or "")
        self.image.setAccessibleName(i18n.t("Picture address"))
        self.link = _line("https://", p.get("url") or "")
        self.link.setAccessibleName(i18n.t("Page address"))
        self.body.addWidget(ui.field(i18n.t("Picture address"), self.image, i18n.t("A web address of a picture. Meta needs one to show the product in its catalogue.")))
        self.body.addWidget(ui.field(i18n.t("Page address"), self.link))
        self.available = QCheckBox(i18n.t("Available to order"))
        self.available.setChecked(p.get("available") is not False)
        self.body.addWidget(self.available)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.save_btn = self.button(i18n.t("Save"), "primary", on_click=self._go)
        self.footer.set_primary(self.save_btn)
        self.resize(560, 640)

    def say(self, message: str, error: bool = False):
        (self.error.error if error else self.error.ok)(message)

    def payload(self) -> dict:
        d = {"name": self.name.text().strip(), "price": self.price.text().strip(), "retailer_id": self.retailer.text().strip(), "category": self.category.text().strip(),
             "description": self.description.toPlainText().strip(), "image_url": self.image.text().strip(), "url": self.link.text().strip(), "available": self.available.isChecked()}
        if self.sale.text().strip():
            d["sale_price"] = self.sale.text().strip()
        if self.product.get("id"):
            d["id"] = self.product["id"]
        return d

    def _go(self):
        if not self.name.text().strip():
            self.error.error(i18n.t("Give the product a name."))
            return
        self.save_btn.setEnabled(False)
        ui.call(self, "catalog/save", self.payload(), done=lambda _r: self.accept(), failed=self._failed)

    def _failed(self, message: str, _detail: dict):
        self.save_btn.setEnabled(True)
        self.error.error(message)


class ImportProductsDialog(PrismDialog):
    def __init__(self, parent=None):
        super().__init__(i18n.t("Import products"), i18n.t("From a spreadsheet saved as CSV. Meta's own catalogue file works as it is."), icon="upload", parent=parent)
        self.body.addWidget(C.label(i18n.t("Columns it understands: title (or name), price, id, description, category, sale_price, availability."), level="SUPPORT",
                                    colour=theme.NEUTRAL[600], wrap=True))
        self.text = QPlainTextEdit()
        self.text.setMinimumHeight(180)
        self.text.setPlaceholderText("id,title,price,category\nwall-6,Boundary wall panel,1299.50,Walls")
        self.text.setAccessibleName(i18n.t("CSV text"))
        self.body.addWidget(self.text)
        self.file_btn = C.button(i18n.t("Choose a file…"), "secondary", icon_name="file", on_click=self._choose)
        row = QHBoxLayout()
        row.addWidget(self.file_btn)
        row.addStretch(1)
        self.body.addLayout(row)
        self.report = ui.note()
        self.body.addWidget(self.report)
        self.footer.add_secondary(self.button(i18n.t("Close"), on_click=self.accept))
        self.go = self.button(i18n.t("Import"), "primary", on_click=self._go)
        self.footer.set_primary(self.go)
        self.resize(560, 520)
        self.imported = False

    def say(self, message: str, error: bool = False):
        (self.report.error if error else self.report.ok)(message)

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, i18n.t("Choose a CSV file"), "", "CSV (*.csv *.txt)")
        if path:
            try:
                with open(path, "r", encoding="utf-8-sig") as fh:
                    self.text.setPlainText(fh.read())
            except OSError as why:
                self.report.error(str(why))

    def _go(self):
        if not self.text.toPlainText().strip():
            self.report.error(i18n.t("Paste the spreadsheet's text or choose a file first."))
            return
        self.go.setEnabled(False)
        ui.call(self, "catalog/import", {"csv": self.text.toPlainText()}, done=self._done, failed=self._failed)

    def _failed(self, message: str, _detail: dict):
        self.go.setEnabled(True)
        self.report.error(message)

    def _done(self, r: dict):
        self.go.setEnabled(True)
        self.imported = True
        words = i18n.t("{a} added, {u} updated.").format(a=r.get("added", 0), u=r.get("updated", 0))
        problems = r.get("problems") or []
        if problems:
            words += "  " + i18n.t("{n} rows were skipped:").format(n=r.get("skipped", len(problems))) + "  " + "; ".join(
                i18n.t("row {n}: {e}").format(n=x["row"], e=x["error"]) for x in problems[:3])
        self.report.set(words, "warn" if problems else "ok")


class SendProductDialog(PrismDialog):
    """Put a product card, a list of products, or the whole catalogue in front of one customer."""

    def __init__(self, product: dict = None, parent=None):
        super().__init__(i18n.t("Send to a chat"), i18n.t("Works inside the 24 hours after the customer last wrote."), icon="send", parent=parent)
        self.product = product
        self.what = QComboBox()
        self.what.setMinimumHeight(38)
        self.what.setAccessibleName(i18n.t("What to send"))
        if product:
            self.what.addItem(i18n.t("This product: {n}").format(n=product["name"]), "product")
        self.what.addItem(i18n.t("The whole catalogue"), "catalog")
        self.body.addWidget(ui.field(i18n.t("Send"), self.what))
        self.who = ContactChoice()
        self.body.addWidget(ui.field(i18n.t("To"), self.who))
        self.message = _line(i18n.t("Have a look at this."))
        self.message.setAccessibleName(i18n.t("Message"))
        self.body.addWidget(ui.field(i18n.t("Words with it"), self.message))
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.go = self.button(i18n.t("Send"), "primary", on_click=self._go)
        self.footer.set_primary(self.go)
        self.resize(500, 460)

    def say(self, message: str, error: bool = False):
        (self.error.error if error else self.error.ok)(message)

    def payload(self) -> dict:
        kind = self.what.currentData()
        d = {"kind": kind, "contact_id": self.who.contact_id(), "body": self.message.text().strip()}
        if kind == "product":
            d["retailer_id"] = self.product["retailer_id"]
        return d

    def _go(self):
        if not self.who.contact_id():
            self.error.error(i18n.t("Choose who to send it to."))
            return
        self.go.setEnabled(False)
        ui.call(self, "catalog/send", self.payload(), done=lambda _r: self.accept(), failed=self._failed)

    def _failed(self, message: str, _detail: dict):
        self.go.setEnabled(True)
        self.error.error(message)


class _ProductRow(QFrame):
    def __init__(self, product: dict, view: "ProductsView"):
        super().__init__()
        self.product = product
        self.setObjectName("waProduct")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#waProduct {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 12, 14, 10)
        col.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(theme.SPACE_2)
        top.addWidget(C.label(product["name"], level="SUPPORT", weight=700), stretch=1)
        if product.get("category"):
            top.addWidget(C.Pill(product["category"], "neutral"))
        top.addWidget(C.Pill(i18n.t("Available") if product["available"] else i18n.t("Not available"), "ok" if product["available"] else "quiet"))
        col.addLayout(top)
        price = money_text(product["price_paise"], product.get("currency"))
        if product.get("sale_price_paise") is not None:
            price = i18n.t("{s} (was {p})").format(s=money_text(product["sale_price_paise"], product.get("currency")), p=price)
        facts = [price, i18n.t("Code {c}").format(c=product["retailer_id"])]
        facts.append(i18n.t("In your Meta catalogue") if product.get("synced_at") else i18n.t("Not sent to Meta yet"))
        col.addWidget(C.label("  ·  ".join(facts), level="META", colour=theme.NEUTRAL[600]))
        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACE_1)
        actions.addStretch(1)
        actions.addWidget(C.button(i18n.t("Send to a chat…"), "tertiary", on_click=lambda: view.send(product)))
        actions.addWidget(C.button(i18n.t("Edit"), "secondary", on_click=lambda: view.edit(product)))
        actions.addWidget(C.button(i18n.t("Delete"), "tertiary", on_click=lambda: view.delete(product)))
        col.addLayout(actions)


class ProductsView(QWidget):
    def __init__(self, shop, parent=None):
        super().__init__(parent)
        self.shop = shop
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(theme.SPACE_3)
        bar = QHBoxLayout()
        bar.setSpacing(theme.SPACE_2)
        self.search = _line(i18n.t("Search by name, code or group"))
        self.search.setAccessibleName(i18n.t("Search products"))
        self.search.returnPressed.connect(self.load)
        bar.addWidget(self.search, 1)
        self.group = QComboBox()
        self.group.setMinimumHeight(38)
        self.group.setAccessibleName(i18n.t("Group"))
        self.group.addItem(i18n.t("All groups"), "")
        self.group.activated.connect(lambda _i: self.load())
        bar.addWidget(self.group)
        self.add_btn = C.button(i18n.t("Add product"), "primary", icon_name="plus", on_click=self.add)
        bar.addWidget(self.add_btn)
        self.import_btn = C.button(i18n.t("Import…"), "secondary", icon_name="upload", on_click=self.import_csv)
        bar.addWidget(self.import_btn)
        self.pull_btn = C.button(i18n.t("Get from Meta"), "tertiary", on_click=self.pull)
        bar.addWidget(self.pull_btn)
        self.push_btn = C.button(i18n.t("Send to Meta"), "tertiary", on_click=self.push)
        bar.addWidget(self.push_btn)
        root.addLayout(bar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        host = QWidget()
        ui.see_through(host)
        self.rows = QVBoxLayout(host)
        self.rows.setContentsMargins(0, 0, theme.SPACE_2, 0)
        self.rows.setSpacing(theme.SPACE_2)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)
        self.empty = C.EmptyState("list", i18n.t("No products yet"), i18n.t("Add one, import a spreadsheet, or get your Meta catalogue."), i18n.t("Add product"))
        self.empty.clicked.connect(self.add)
        self.empty.setVisible(False)
        root.addWidget(self.empty, 1)
        self.total = 0

    def say(self, message: str, error: bool = False):
        self.shop.say(message, error)

    def load(self):
        ui.call(self, "catalog/list", {"q": self.search.text().strip(), "category": self.group.currentData() or ""}, done=self._loaded)

    def _loaded(self, reply: dict):
        rows = list(reply.get("products") or [])
        self.total = reply.get("total", len(rows))
        keep = self.group.currentData()
        self.group.blockSignals(True)
        self.group.clear()
        self.group.addItem(i18n.t("All groups"), "")
        for c in reply.get("categories") or []:
            self.group.addItem(c, c)
        self.group.setCurrentIndex(max(self.group.findData(keep), 0))
        self.group.blockSignals(False)
        ui.clear(self.rows)
        for p in rows:
            self.rows.addWidget(_ProductRow(p, self))
        self.rows.addStretch(1)
        searching = bool(self.search.text().strip() or self.group.currentData())
        self.empty.setVisible(not rows and not searching)
        if not rows and searching:
            self.rows.insertWidget(0, C.label(i18n.t("Nothing matches that."), level="SUPPORT", colour=theme.NEUTRAL[600]))

    def add(self):
        if ProductDialog(parent=self).exec():
            self.say(i18n.t("Saved."))
            self.load()

    def edit(self, product: dict):
        if ProductDialog(product, self).exec():
            self.say(i18n.t("Saved."))
            self.load()

    def delete(self, product: dict):
        if not ui.confirm(self, i18n.t("Delete product"), i18n.t("Delete “{n}”? Past orders keep their copy of it.").format(n=product["name"])):
            return
        ui.call(self, "catalog/delete", {"product_id": product["id"]}, done=lambda _r: (self.say(i18n.t("Deleted.")), self.load()))

    def send(self, product: dict):
        if SendProductDialog(product, self).exec():
            self.say(i18n.t("Sent."))

    def import_csv(self):
        dlg = ImportProductsDialog(self)
        dlg.exec()
        if dlg.imported:
            self.load()

    def pull(self):
        ui.call(self, "catalog/pull", {}, done=lambda r: (self.say(i18n.t("From Meta: {a} new, {u} updated.").format(a=r.get("added", 0), u=r.get("updated", 0))), self.load()))

    def push(self):
        ui.call(self, "catalog/push", {}, done=lambda r: (self.say(i18n.t("Sent {n} products to Meta.").format(n=r.get("sent", 0))), self.load()))
