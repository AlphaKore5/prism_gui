"""Shop → Orders: what customers asked to buy, and where each order stands.

A customer's cart from your catalogue arrives here as a *Cart* (a draft). You can also make an order by hand for someone. From an order you ask the customer to pay (a payment
request in the chat, or just a link to send yourself), watch it go from waiting to paid, then mark it being prepared, shipped and done — the customer is told each step in the chat.
Money is shown in rupees and kept in whole paise; the total on screen is worked out the same way the server does it, so it never differs by a paisa.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLineEdit, QPlainTextEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import shop_money as M
from addons.whatsapp import ui
from addons.whatsapp.contact_picker import ContactChoice
from dialogs.base import PrismDialog
from widgets import controls as C

def status_choices() -> list:
    """Literal i18n.t calls so the string extractor sees every word."""
    return [("", i18n.t("All orders")), ("draft", i18n.t("Carts")), ("awaiting_payment", i18n.t("Waiting for payment")), ("paid", i18n.t("Paid")), ("processing", i18n.t("Being prepared")),
            ("shipped", i18n.t("Shipped")), ("completed", i18n.t("Done")), ("failed", i18n.t("Payment failed")), ("cancelled", i18n.t("Cancelled")), ("refunded", i18n.t("Refunded"))]


def state_pill(status: str) -> "C.Pill":
    words = {"draft": i18n.t("Cart"), "awaiting_payment": i18n.t("Waiting for payment"), "paid": i18n.t("Paid"), "processing": i18n.t("Being prepared"), "shipped": i18n.t("Shipped"),
             "completed": i18n.t("Done"), "cancelled": i18n.t("Cancelled"), "failed": i18n.t("Payment failed"), "refunded": i18n.t("Refunded")}
    return C.Pill(words.get(status, status), M.state_words(status)[1])


def payment_pill(status: str) -> "C.Pill":
    words = {"created": i18n.t("Not sent"), "pending": i18n.t("Waiting"), "captured": i18n.t("Received"), "failed": i18n.t("Failed"), "expired": i18n.t("Ran out of time"),
             "cancelled": i18n.t("Cancelled"), "refunded": i18n.t("Refunded"), "partially_refunded": i18n.t("Part refunded")}
    return C.Pill(words.get(status, status), M.payment_words(status)[1])


def short_when(iso: str) -> str:
    return (iso or "")[:16].replace("T", " ")


def items_line(order: dict) -> str:
    return ", ".join("%d × %s" % (i["quantity"], i["name"]) for i in order.get("items") or [])[:140]


class RefundDialog(PrismDialog):
    """Give some or all of a payment back. Prism sends it through Razorpay when it can; otherwise it can note a refund you made yourself."""

    def __init__(self, payment: dict, parent=None):
        super().__init__(i18n.t("Give money back"), i18n.t("Received {a} for order {r}.").format(a=M.money_text(payment["amount_paise"], payment.get("currency")),
                                                                                                   r=payment["reference_id"]), icon="send", parent=parent)
        self.payment = payment
        self.left = payment["amount_paise"] - payment.get("refunded_paise", 0)
        self.amount = QLineEdit(M.rupees(self.left).replace(",", ""))
        self.amount.setMinimumHeight(38)
        self.amount.setAccessibleName(i18n.t("Amount to give back"))
        self.body.addWidget(ui.field(i18n.t("Amount (Rs)"), self.amount, i18n.t("Up to {a}, what is left of this payment.").format(a=M.money_text(self.left, payment.get("currency")))))
        self.speed = QComboBox()
        self.speed.setMinimumHeight(38)
        self.speed.setAccessibleName(i18n.t("Speed"))
        self.speed.addItem(i18n.t("Normal (about 5 to 7 days)"), "normal")
        self.speed.addItem(i18n.t("Instant, when the bank allows it"), "instant")
        self.body.addWidget(ui.field(i18n.t("How fast"), self.speed))
        self.reason = QLineEdit()
        self.reason.setMinimumHeight(38)
        self.reason.setAccessibleName(i18n.t("Reason"))
        self.body.addWidget(ui.field(i18n.t("Reason"), self.reason, i18n.t("For your records.")))
        self.elsewhere = C.label(i18n.t("If you already refunded this in your Razorpay dashboard, record it here instead:"), level="META", colour=theme.NEUTRAL[600], wrap=True)
        self.body.addWidget(self.elsewhere)
        self.record_btn = C.button(i18n.t("I refunded it elsewhere — just record it"), "tertiary", on_click=lambda: self._go(True))
        row = QHBoxLayout()
        row.addWidget(self.record_btn)
        row.addStretch(1)
        self.body.addLayout(row)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.go = self.button(i18n.t("Give money back"), "primary", on_click=lambda: self._go(False))
        self.footer.set_primary(self.go)
        self.resize(500, 520)

    def say(self, message: str, error: bool = False):
        (self.error.error if error else self.error.ok)(message)

    def _go(self, record_only: bool):
        try:
            paise = M.paise(self.amount.text(), what="amount")
        except M.MoneyError as why:
            self.error.error(str(why))
            return
        if paise <= 0 or paise > self.left:
            self.error.error(i18n.t("Give back between 0.01 and {a}.").format(a=M.rupees(self.left)))
            return
        self.go.setEnabled(False)
        ui.call(self, "payments/refund", {"payment_id": self.payment["id"], "amount": self.amount.text().strip(), "speed": self.speed.currentData(), "reason": self.reason.text().strip(),
                                          "record_only": record_only}, done=lambda _r: self.accept(), failed=self._failed)

    def _failed(self, message: str, _detail: dict):
        self.go.setEnabled(True)
        self.error.error(message)


class OrderDialog(PrismDialog):
    """One order: what is in it, what it costs, its payments, and what can be done next."""

    def __init__(self, order: dict, parent=None):
        super().__init__(order["reference_id"], i18n.t("Order"), icon="list", parent=parent, scrollable=True)
        self.order = order
        self.changed = False
        self.head = QHBoxLayout()
        self.who = C.label("", level="SUPPORT", weight=700)
        self.head.addWidget(self.who, 1)
        self.pill_holder = QHBoxLayout()
        self.head.addLayout(self.pill_holder)
        self.body.addLayout(self.head)
        self.items = QVBoxLayout()
        self.items.setSpacing(2)
        self.body.addLayout(self.items)
        self.sums = QVBoxLayout()
        self.sums.setSpacing(2)
        self.body.addLayout(self.sums)
        self.payments = QVBoxLayout()
        self.payments.setSpacing(theme.SPACE_1)
        self.body.addWidget(C.label(i18n.t("Payments"), level="SUPPORT", weight=700))
        self.body.addLayout(self.payments)
        self.message = QLineEdit()
        self.message.setMinimumHeight(38)
        self.message.setPlaceholderText(i18n.t("Optional words for the customer, like a tracking number"))
        self.message.setAccessibleName(i18n.t("Message for the customer"))
        self.body.addWidget(ui.field(i18n.t("Tell the customer"), self.message))
        self.actions = QVBoxLayout()
        self.actions.setSpacing(theme.SPACE_1)
        self.body.addLayout(self.actions)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.set_primary(self.button(i18n.t("Close"), "primary", on_click=self.accept))
        self.resize(620, 700)
        self.show_order(order)

    def say(self, message: str, error: bool = False):
        (self.error.error if error else self.error.ok)(message)

    def reload(self):
        ui.call(self, "orders/get", {"order_id": self.order["id"]}, done=lambda r: self.show_order(r["order"]))

    def show_order(self, o: dict):
        self.order = o
        for lay in (self.pill_holder, self.items, self.sums, self.payments, self.actions):
            ui.clear(lay)
        who = o.get("contact_name") or i18n.t("No customer chosen")
        self.who.setText("%s  ·  %s" % (who, o.get("contact_phone") or "") if o.get("contact_phone") else who)
        self.pill_holder.addWidget(state_pill(o["status"]))
        for i in o["items"]:
            self.items.addWidget(C.label("%d × %s     %s" % (i["quantity"], i["name"], M.money_text(i["line_paise"], o["currency"])), level="SUPPORT"))
        for label, key in ((i18n.t("Items"), "subtotal_paise"), (i18n.t("Discount"), "discount_paise"), (i18n.t("Tax"), "tax_paise"), (i18n.t("Shipping"), "shipping_paise")):
            if o[key] or key == "subtotal_paise":
                self.sums.addWidget(C.label("%s     %s" % (label, M.money_text(-o[key] if key == "discount_paise" else o[key], o["currency"])), level="META", colour=theme.NEUTRAL[600]))
        self.sums.addWidget(C.label("%s     %s" % (i18n.t("Total"), M.money_text(o["total_paise"], o["currency"])), level="SUPPORT", weight=700))
        if o.get("note"):
            self.sums.addWidget(C.label(i18n.t("Note: {n}").format(n=o["note"]), level="META", colour=theme.NEUTRAL[600], wrap=True))
        pays = o.get("payments") or []
        if not pays:
            self.payments.addWidget(C.label(i18n.t("No payment asked for yet."), level="META", colour=theme.NEUTRAL[600]))
        for p in pays:
            self.payments.addWidget(_PaymentLine(p, self))
        self._actions(o, pays)

    def _actions(self, o: dict, pays: list):
        a = self.actions
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        a.addLayout(row)
        status = o["status"]
        if status in ("draft", "failed", "awaiting_payment") and o.get("contact_id"):
            self.ask_btn = C.button(i18n.t("Ask again in the chat") if status == "awaiting_payment" else i18n.t("Ask the customer to pay"), "primary", on_click=lambda: self.ask(True))
            row.addWidget(self.ask_btn)
            self.link_btn = C.button(i18n.t("Make a link only"), "secondary", on_click=lambda: self.ask(False))
            row.addWidget(self.link_btn)
        elif status in ("draft", "failed") and not o.get("contact_id"):
            row.addWidget(C.label(i18n.t("Choose a customer for this order before asking for payment."), level="META", colour=theme.NEUTRAL[600], wrap=True))
        moves = [s for s in M.NEXT.get(status, ()) if s in ("processing", "shipped", "completed")]
        for s in moves:
            word = {"processing": i18n.t("Being prepared"), "shipped": i18n.t("Shipped"), "completed": i18n.t("Done")}[s]
            btn = C.button(i18n.t("Mark: {w}").format(w=word), "secondary", on_click=lambda _=False, s=s: self.move(s))
            setattr(self, "move_%s_btn" % s, btn)
            row.addWidget(btn)
        row.addStretch(1)
        if status not in ("cancelled", "refunded", "completed"):
            self.cancel_btn = C.button(i18n.t("Cancel order"), "tertiary", on_click=self.cancel)
            row.addWidget(self.cancel_btn)

    def ask(self, send: bool):
        ui.call(self, "payments/request", {"order_id": self.order["id"], "send": send}, done=lambda r: self._asked(r["payment"], send))

    def _asked(self, payment: dict, send: bool):
        self.changed = True
        self.say(i18n.t("Asked in the chat.") if send else i18n.t("Link made. Copy it from the payment below."))
        self.reload()

    def move(self, status: str):
        ui.call(self, "orders/status", {"order_id": self.order["id"], "status": status, "note": self.message.text().strip()}, done=self._moved)

    def _moved(self, reply: dict):
        self.changed = True
        self.message.clear()
        self.say(i18n.t("Updated. The customer was told in the chat."))
        self.show_order(reply["order"])

    def cancel(self):
        if not ui.confirm(self, i18n.t("Cancel order"), i18n.t("Cancel order {r}? Any open payment request is cancelled too.").format(r=self.order["reference_id"])):
            return
        ui.call(self, "orders/cancel", {"order_id": self.order["id"]}, done=self._moved)

    def check(self, payment: dict):
        ui.call(self, "payments/check", {"payment_id": payment["id"]}, done=lambda _r: (setattr(self, "changed", True), self.reload()))

    def refund(self, payment: dict):
        ui.call(self, "payments/get", {"payment_id": payment["id"]}, done=lambda r: self._refund_dialog(r["payment"]))

    def _refund_dialog(self, payment: dict):
        if RefundDialog(payment, self).exec():
            self.changed = True
            self.say(i18n.t("Recorded."))
            self.reload()


class _PaymentLine(QFrame):
    def __init__(self, p: dict, dlg: OrderDialog):
        super().__init__()
        self.p = p
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(theme.SPACE_2)
        how = {"razorpay": i18n.t("Payment link"), "meta": i18n.t("Pay in WhatsApp")}.get(p["provider"], p["provider"])
        facts = [how, M.money_text(p["amount_paise"], p.get("currency"))]
        if p.get("method"):
            facts.append(p["method"].upper())
        if p.get("refunded_paise"):
            facts.append(i18n.t("{a} given back").format(a=M.money_text(p["refunded_paise"], p.get("currency"))))
        when = short_when(p.get("paid_at") or p.get("created_at"))
        if when:
            facts.append(when)
        row.addWidget(C.label("  ·  ".join(facts), level="META", colour=theme.NEUTRAL[700], wrap=True), 1)
        row.addWidget(payment_pill(p["status"]))
        if p.get("last_error") and p["status"] in ("failed", "expired"):
            self.setToolTip(p["last_error"])
        if p["status"] in ("created", "pending"):
            if p.get("link_url"):
                row.addWidget(C.button(i18n.t("Copy link"), "tertiary", small=True, on_click=lambda: ui.copy_text(dlg, p["link_url"], i18n.t("Payment link"))))
            row.addWidget(C.button(i18n.t("Check"), "tertiary", small=True, on_click=lambda: dlg.check(p)))
        if p["status"] in ("captured", "partially_refunded"):
            row.addWidget(C.button(i18n.t("Give money back…"), "tertiary", small=True, on_click=lambda: dlg.refund(p)))


class _LineEdit(QFrame):
    """One line of a new order: a product (or something else) and how many."""

    def __init__(self, products: list, dlg: "NewOrderDialog"):
        super().__init__()
        self.dlg = dlg
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACE_2)
        self.what = QComboBox()
        self.what.setMinimumHeight(38)
        self.what.setAccessibleName(i18n.t("Product"))
        self.what.addItem(i18n.t("— choose —"), None)
        for p in products:
            self.what.addItem("%s  ·  %s" % (p["name"], M.money_text(p["sale_price_paise"] if p.get("sale_price_paise") is not None else p["price_paise"], p.get("currency"))), p["retailer_id"])
        self.what.addItem(i18n.t("Something else…"), "__custom__")
        self.what.currentIndexChanged.connect(self._kind)
        row.addWidget(self.what, 3)
        self.name = QLineEdit()
        self.name.setMinimumHeight(38)
        self.name.setPlaceholderText(i18n.t("What it is"))
        self.name.setAccessibleName(i18n.t("Item name"))
        self.price = QLineEdit()
        self.price.setMinimumHeight(38)
        self.price.setPlaceholderText(i18n.t("Price"))
        self.price.setAccessibleName(i18n.t("Item price"))
        for w in (self.name, self.price):
            w.setVisible(False)
            w.textChanged.connect(lambda _t: dlg.recalculate())
        row.addWidget(self.name, 2)
        row.addWidget(self.price, 1)
        self.qty = QSpinBox()
        self.qty.setRange(1, 1000)
        self.qty.setMinimumHeight(38)
        self.qty.setAccessibleName(i18n.t("How many"))
        self.qty.valueChanged.connect(lambda _v: dlg.recalculate())
        row.addWidget(self.qty)
        row.addWidget(C.button(i18n.t("Remove"), "tertiary", small=True, on_click=lambda: dlg.remove_line(self)))
        self.products = {p["retailer_id"]: p for p in products}

    def _kind(self, _i):
        custom = self.what.currentData() == "__custom__"
        self.name.setVisible(custom)
        self.price.setVisible(custom)
        self.dlg.recalculate()

    def item(self):
        """The line as the server wants it, or None if nothing is chosen. Raises MoneyError for a bad price."""
        key = self.what.currentData()
        if key is None:
            return None
        if key == "__custom__":
            if not self.name.text().strip():
                return None
            return {"name": self.name.text().strip(), "price": self.price.text().strip(), "quantity": self.qty.value()}
        return {"retailer_id": key, "quantity": self.qty.value()}

    def priced(self):
        """(unit paise, name) for the screen's own total, or None."""
        key = self.what.currentData()
        if key in (None,):
            return None
        if key == "__custom__":
            try:
                return M.paise(self.price.text(), what="price"), self.name.text().strip()
            except M.MoneyError:
                return None
        p = self.products[key]
        return (p["sale_price_paise"] if p.get("sale_price_paise") is not None else p["price_paise"]), p["name"]


class NewOrderDialog(PrismDialog):
    def __init__(self, config: dict, products: list, contact: dict = None, parent=None):
        super().__init__(i18n.t("New order"), i18n.t("Choose the customer and what they are buying."), icon="list", parent=parent, scrollable=True)
        self.config, self.products = config, products
        self.who = ContactChoice()
        if contact:
            self.who.set_contact(contact["id"], contact.get("name") or "")
        self.body.addWidget(ui.field(i18n.t("Customer"), self.who))
        self.lines = QVBoxLayout()
        self.lines.setSpacing(theme.SPACE_2)
        self.body.addWidget(C.label(i18n.t("Items").upper(), level="LABEL", colour=theme.NEUTRAL[500]))
        self.body.addLayout(self.lines)
        self.add_btn = C.button(i18n.t("Add another item"), "tertiary", icon_name="plus", on_click=self.add_line)
        row = QHBoxLayout()
        row.addWidget(self.add_btn)
        row.addStretch(1)
        self.body.addLayout(row)
        charges = QHBoxLayout()
        charges.setSpacing(theme.SPACE_3)
        self.shipping = QLineEdit(M.rupees(config.get("shipping_paise", 0)).replace(",", ""))
        self.shipping.setMinimumHeight(38)
        self.shipping.setAccessibleName(i18n.t("Shipping"))
        self.discount = QLineEdit("0")
        self.discount.setMinimumHeight(38)
        self.discount.setAccessibleName(i18n.t("Discount"))
        for w in (self.shipping, self.discount):
            w.textChanged.connect(lambda _t: self.recalculate())
        charges.addWidget(ui.field(i18n.t("Shipping (Rs)"), self.shipping), 1)
        charges.addWidget(ui.field(i18n.t("Discount (Rs)"), self.discount), 1)
        self.body.addLayout(charges)
        self.note = QPlainTextEdit()
        self.note.setMinimumHeight(56)
        self.note.setMaximumHeight(72)
        self.note.setAccessibleName(i18n.t("Note"))
        self.body.addWidget(ui.field(i18n.t("Note"), self.note))
        self.summary = C.label("", level="SUPPORT", weight=700, wrap=True)
        self.body.addWidget(self.summary)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.go = self.button(i18n.t("Make the order"), "primary", on_click=self._go)
        self.footer.set_primary(self.go)
        self.resize(660, 720)
        self.add_line()
        self.recalculate()
        self.created = None

    def say(self, message: str, error: bool = False):
        (self.error.error if error else self.error.ok)(message)

    def add_line(self):
        self.lines.addWidget(_LineEdit(self.products, self))
        self.recalculate()

    def remove_line(self, line):
        if self.lines.count() > 1:
            self.lines.removeWidget(line)
            ui.discard(line)
            self.recalculate()

    def _all(self) -> list:
        return [self.lines.itemAt(i).widget() for i in range(self.lines.count())]

    def recalculate(self):
        items = []
        for line in self._all():
            got = line.priced()
            if got:
                items.append({"line_paise": got[0] * line.qty.value()})
        try:
            ship = M.paise(self.shipping.text() or 0, what="shipping")
            disc = M.paise(self.discount.text() or 0, what="discount")
        except M.MoneyError:
            self.summary.setText("")
            return
        t = M.totals(items, tax_percent=self.config.get("tax_percent", 0), shipping_paise=ship, discount_paise=disc)
        self.summary.setText(i18n.t("Items {a}  ·  Tax {t}  ·  Shipping {s}  ·  Total {x}").format(a=M.money_text(t["subtotal_paise"]), t=M.money_text(t["tax_paise"]),
                                                                                                s=M.money_text(t["shipping_paise"]), x=M.money_text(t["total_paise"])))

    def payload(self) -> dict:
        items = [i for i in (line.item() for line in self._all()) if i]
        d = {"contact_id": self.who.contact_id(), "items": items, "shipping": self.shipping.text().strip() or "0", "discount": self.discount.text().strip() or "0"}
        if self.note.toPlainText().strip():
            d["note"] = self.note.toPlainText().strip()
        return d

    def _go(self):
        d = self.payload()
        if not d["items"]:
            self.error.error(i18n.t("Add at least one item."))
            return
        self.go.setEnabled(False)
        ui.call(self, "orders/create", d, done=self._done, failed=self._failed)

    def _failed(self, message: str, _detail: dict):
        self.go.setEnabled(True)
        self.error.error(message)

    def _done(self, reply: dict):
        self.created = reply["order"]
        self.accept()


class _OrderRow(QFrame):
    def __init__(self, order: dict, view: "OrdersView"):
        super().__init__()
        self.order = order
        self.setObjectName("waOrder")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#waOrder {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 12, 14, 10)
        col.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(theme.SPACE_2)
        who = order.get("contact_name") or i18n.t("No customer yet")
        top.addWidget(C.label("%s  ·  %s" % (who, M.money_text(order["total_paise"], order["currency"])), level="SUPPORT", weight=700), stretch=1)
        if order["source"] == "cart":
            top.addWidget(C.Pill(i18n.t("From WhatsApp cart"), "info"))
        top.addWidget(state_pill(order["status"]))
        col.addLayout(top)
        col.addWidget(C.label("  ·  ".join([items_line(order), order["reference_id"], short_when(order["created_at"])]), level="META", colour=theme.NEUTRAL[600], wrap=True))
        actions = QHBoxLayout()
        actions.addStretch(1)
        if order["status"] in ("draft", "failed") and order.get("contact_id"):
            actions.addWidget(C.button(i18n.t("Ask to pay"), "secondary", on_click=lambda: view.open(order)))
        actions.addWidget(C.button(i18n.t("Open"), "tertiary", on_click=lambda: view.open(order)))
        col.addLayout(actions)


class OrdersView(QWidget):
    def __init__(self, shop, parent=None):
        super().__init__(parent)
        self.shop = shop
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(theme.SPACE_3)
        bar = QHBoxLayout()
        bar.setSpacing(theme.SPACE_2)
        self.search = QLineEdit()
        self.search.setMinimumHeight(38)
        self.search.setPlaceholderText(i18n.t("Search by reference or customer"))
        self.search.setAccessibleName(i18n.t("Search orders"))
        self.search.returnPressed.connect(self.load)
        bar.addWidget(self.search, 1)
        self.status = QComboBox()
        self.status.setMinimumHeight(38)
        self.status.setAccessibleName(i18n.t("Show"))
        for key, label in status_choices():
            self.status.addItem(label, key)
        self.status.activated.connect(lambda _i: self.load())
        bar.addWidget(self.status)
        self.new_btn = C.button(i18n.t("New order"), "primary", icon_name="plus", on_click=self.new)
        bar.addWidget(self.new_btn)
        root.addLayout(bar)
        self.counts = C.label("", level="META", colour=theme.NEUTRAL[600], wrap=True)
        root.addWidget(self.counts)
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
        self.empty = C.EmptyState("list", i18n.t("No orders yet"), i18n.t("A customer's cart from your catalogue shows up here, or make an order yourself."), i18n.t("New order"))
        self.empty.clicked.connect(self.new)
        self.empty.setVisible(False)
        root.addWidget(self.empty, 1)

    def say(self, message: str, error: bool = False):
        self.shop.say(message, error)

    def load(self):
        ui.call(self, "orders/list", {"status": self.status.currentData() or "", "q": self.search.text().strip()}, done=self._loaded)

    def _loaded(self, reply: dict):
        rows = list(reply.get("orders") or [])
        ui.clear(self.rows)
        for o in rows:
            self.rows.addWidget(_OrderRow(o, self))
        self.rows.addStretch(1)
        counts = reply.get("counts") or {}
        names = dict(status_choices())
        self.counts.setText("  ·  ".join("%s %d" % (names.get(k, k), n) for k, n in counts.items()))
        filtered = bool(self.status.currentData() or self.search.text().strip())
        self.empty.setVisible(not rows and not filtered)
        if not rows and filtered:
            self.rows.insertWidget(0, C.label(i18n.t("No orders match."), level="SUPPORT", colour=theme.NEUTRAL[600]))

    def new(self, contact: dict = None):
        contact = contact if isinstance(contact, dict) else None
        ui.call(self, "commerce/config/get", {}, done=lambda c: ui.call(self, "catalog/list", {"available": True}, done=lambda r: self._new_dialog(c["config"], r.get("products") or [], contact)))

    def _new_dialog(self, config: dict, products: list, contact):
        dlg = NewOrderDialog(config, products, contact, self)
        if dlg.exec() and dlg.created:
            self.say(i18n.t("Order {r} made.").format(r=dlg.created["reference_id"]))
            self.load()
            self.open(dlg.created)

    def open(self, order: dict):
        ui.call(self, "orders/get", {"order_id": order["id"]}, done=lambda r: self._open(r["order"]))

    def _open(self, order: dict):
        dlg = OrderDialog(order, self)
        dlg.exec()
        if dlg.changed:
            self.load()
