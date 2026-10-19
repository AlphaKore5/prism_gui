"""Shop → Payments: money in, money back, what is still waiting, and who to remind.

Everything is counted from the payments Prism asked for: a payment is *received* only when the gateway (Razorpay, or Meta's payments) says so, never because a customer said they
paid. Money is shown in rupees and kept in whole paise.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import shop_money as M
from addons.whatsapp import ui
from addons.whatsapp.shop_orders import RefundDialog, payment_pill, short_when
from widgets import controls as C


def status_choices() -> list:
    return [("", i18n.t("All payments")), ("pending", i18n.t("Waiting")), ("captured", i18n.t("Received")), ("failed", i18n.t("Failed")), ("expired", i18n.t("Ran out of time")),
            ("cancelled", i18n.t("Cancelled")), ("partially_refunded", i18n.t("Part refunded")), ("refunded", i18n.t("Refunded"))]


class MoneyChart(QWidget):
    """Money received each day as a column. Hover a day to read it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._days: list = []
        self.setMinimumHeight(150)
        self.setMouseTracking(True)

    def set_days(self, days: list):
        self._days = list(days or [])
        self.update()

    def _area(self) -> QRectF:
        return QRectF(52, 8, max(self.width() - 60, 10), max(self.height() - 30, 10))

    def mouseMoveEvent(self, event):
        area, n = self._area(), len(self._days)
        if n and area.contains(event.position()):
            d = self._days[min(n - 1, int((event.position().x() - area.left()) / (area.width() / n)))]
            self.setToolTip(i18n.t("{day}\nReceived {a} in {n} payments").format(day=d["day"], a=M.money_text(d["paise"]), n=d["count"]))
        super().mouseMoveEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        area, n = self._area(), len(self._days)
        font = QFont(theme.FONT_BODY)
        font.setPixelSize(10)
        p.setFont(font)
        top = max([d["paise"] for d in self._days] + [100])
        ceiling = top
        p.setPen(QPen(theme.c(theme.HAIRLINE), 1))
        for k in range(5):
            y = area.bottom() - area.height() * k / 4
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QPen(theme.c(theme.NEUTRAL[500])))
            p.drawText(QRectF(0, y - 8, area.left() - 6, 16), Qt.AlignRight | Qt.AlignVCenter, "{:,.0f}".format(ceiling * k / 4 / 100.0))
            p.setPen(QPen(theme.c(theme.HAIRLINE), 1))
        if not n:
            return
        slot = area.width() / n
        bar = max(2.0, min(slot * 0.7, 26.0))
        every = max(1, int(round(n / 7)))
        for i, d in enumerate(self._days):
            x = area.left() + slot * i + (slot - bar) / 2
            h = area.height() * d["paise"] / ceiling
            p.setPen(Qt.NoPen)
            p.setBrush(theme.c(theme.ACCENT))
            p.drawRoundedRect(QRectF(x, area.bottom() - h, bar, h), 2, 2)
            if i % every == 0 or i == n - 1:
                p.setPen(QPen(theme.c(theme.NEUTRAL[500])))
                p.drawText(QRectF(x - 20 + bar / 2, area.bottom() + 4, 40, 14), Qt.AlignCenter, d["day"][5:])


class _PayRow(QFrame):
    def __init__(self, p: dict, view: "PaymentsView"):
        super().__init__()
        self.setObjectName("waPay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#waPay {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(theme.SPACE_2)
        how = {"razorpay": i18n.t("Payment link"), "meta": i18n.t("Pay in WhatsApp")}.get(p["provider"], p["provider"])
        facts = [p.get("contact_name") or i18n.t("Unknown"), M.money_text(p["amount_paise"], p.get("currency")), p["reference_id"], how]
        if p.get("method"):
            facts.append(p["method"].upper())
        facts.append(short_when(p.get("paid_at") or p.get("created_at")))
        row.addWidget(C.label("  ·  ".join(f for f in facts if f), level="META", colour=theme.NEUTRAL[700], wrap=True), 1)
        row.addWidget(payment_pill(p["status"]))
        if p["status"] in ("created", "pending"):
            row.addWidget(C.button(i18n.t("Check"), "tertiary", small=True, on_click=lambda: view.check(p)))
        if p["status"] in ("captured", "partially_refunded"):
            row.addWidget(C.button(i18n.t("Give money back…"), "tertiary", small=True, on_click=lambda: view.refund(p)))


class PaymentsView(QWidget):
    def __init__(self, shop, parent=None):
        super().__init__(parent)
        self.shop = shop
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        outer.addWidget(scroll)
        host = QWidget()
        ui.see_through(host)
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, theme.SPACE_2, 0)
        col.setSpacing(theme.SPACE_3)
        scroll.setWidget(host)
        grid = QGridLayout()
        grid.setSpacing(theme.SPACE_2)
        self.k_in = C.MetricCard(i18n.t("Received"), "—", icon="check")
        self.k_back = C.MetricCard(i18n.t("Given back"), "—", icon="send")
        self.k_net = C.MetricCard(i18n.t("Kept"), "—", icon="chart")
        self.k_wait = C.MetricCard(i18n.t("Waiting"), "—", icon="clock")
        self.k_fail = C.MetricCard(i18n.t("Failed or ran out"), "—", icon="alert")
        self.k_rate = C.MetricCard(i18n.t("Paid after asking"), "—", icon="activity")
        for i, k in enumerate((self.k_in, self.k_back, self.k_net, self.k_wait, self.k_fail, self.k_rate)):
            grid.addWidget(k, i // 3, i % 3)
        col.addLayout(grid)
        col.addWidget(C.label(i18n.t("Received each day (Rs)"), level="SUPPORT", weight=700))
        self.chart = MoneyChart()
        col.addWidget(self.chart)
        self.methods = C.label("", level="META", colour=theme.NEUTRAL[600], wrap=True)
        col.addWidget(self.methods)
        col.addWidget(C.label(i18n.t("People to remind"), level="SUPPORT", weight=700))
        col.addWidget(C.label(i18n.t("Their payment failed, ran out of time or was left open, and they have not paid since. Open the order to ask again."), level="META",
                              colour=theme.NEUTRAL[600], wrap=True))
        self.remind = QVBoxLayout()
        self.remind.setSpacing(theme.SPACE_1)
        col.addLayout(self.remind)
        head = QHBoxLayout()
        head.addWidget(C.label(i18n.t("Payments"), level="SUPPORT", weight=700), 1)
        self.status = QComboBox()
        self.status.setMinimumHeight(34)
        self.status.setAccessibleName(i18n.t("Show"))
        for key, label in status_choices():
            self.status.addItem(label, key)
        self.status.activated.connect(lambda _i: self.load_list())
        head.addWidget(self.status)
        col.addLayout(head)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(theme.SPACE_2)
        col.addLayout(self.rows)
        col.addStretch(1)

    def say(self, message: str, error: bool = False):
        self.shop.say(message, error)

    def load(self):
        ui.call(self, "payments/dashboard", {}, done=self._dashboard)
        ui.call(self, "payments/retarget", {}, done=self._remind)
        self.load_list()

    def load_list(self):
        ui.call(self, "payments/list", {"status": self.status.currentData() or ""}, done=self._list)

    def _dashboard(self, d: dict):
        self.k_in.set_value(M.money_text(d["received_paise"]), (i18n.t("{n} payment") if d["received_count"] == 1 else i18n.t("{n} payments")).format(n=d["received_count"]))
        self.k_back.set_value(M.money_text(d["refunded_paise"]))
        self.k_net.set_value(M.money_text(d["net_paise"]), i18n.t("{a} on average").format(a=M.money_text(d["average_paise"])) if d["received_count"] else "")
        self.k_wait.set_value(str(d["pending"]["count"]), i18n.t("{n} left open over an hour").format(n=d["abandoned"]) if d.get("abandoned") else M.money_text(d["pending"]["paise"]))
        self.k_fail.set_value(str(d["failed"]["count"] + d["expired"]["count"]), M.money_text(d["failed"]["paise"] + d["expired"]["paise"]))
        self.k_rate.set_value("%s%%" % d["conversion_percent"])
        self.chart.set_days(d.get("days") or [])
        self.methods.setText("  ·  ".join("%s %s (%d)" % (m["method"].upper(), M.money_text(m["paise"]), m["count"]) for m in d.get("methods") or []) or
                             i18n.t("Nothing received in this period yet."))

    def _remind(self, reply: dict):
        ui.clear(self.remind)
        people = list(reply.get("people") or [])
        if not people:
            self.remind.addWidget(C.label(i18n.t("Nobody to remind."), level="META", colour=theme.NEUTRAL[600]))
        for person in people:
            self.remind.addWidget(_RemindRow(person, self))

    def _list(self, reply: dict):
        ui.clear(self.rows)
        rows = list(reply.get("payments") or [])
        if not rows:
            self.rows.addWidget(C.label(i18n.t("No payments yet. Ask a customer to pay from an order."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for p in rows:
            self.rows.addWidget(_PayRow(p, self))

    def check(self, p: dict):
        ui.call(self, "payments/check", {"payment_id": p["id"]}, done=lambda _r: (self.say(i18n.t("Checked with the gateway.")), self.load()))

    def refund(self, p: dict):
        ui.call(self, "payments/get", {"payment_id": p["id"]}, done=lambda r: self._refund(r["payment"]))

    def _refund(self, payment: dict):
        if RefundDialog(payment, self).exec():
            self.say(i18n.t("Recorded."))
            self.load()

    def open_order(self, order_id: str):
        self.shop.open_order(order_id)


class _RemindRow(QFrame):
    def __init__(self, person: dict, view: PaymentsView):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(theme.SPACE_2)
        words = {"failed": i18n.t("failed"), "expired": i18n.t("ran out of time"), "cancelled": i18n.t("was cancelled"), "pending": i18n.t("still open"), "created": i18n.t("not sent")}
        row.addWidget(C.label(i18n.t("{n}  ·  {a}  ·  payment {w}").format(n=person.get("name") or person.get("phone") or i18n.t("Unknown"), a=M.money_text(person["total_paise"], person.get("currency")),
                                                                         w=words.get(person["payment_status"], person["payment_status"])), level="META", colour=theme.NEUTRAL[700], wrap=True), 1)
        row.addWidget(C.button(i18n.t("Open order"), "tertiary", small=True, on_click=lambda: view.open_order(person["order_id"])))
