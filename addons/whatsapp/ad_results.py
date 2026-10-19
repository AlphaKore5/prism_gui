"""What an ad did, day by day: money spent, how many saw it, clicked, started a chat or left their details — and what each result cost.

The numbers are Meta's own, asked for over a range you choose. Spend is in the ad account's currency; the cost of each result is worked out here from the spend and the
results Meta reports, never guessed. An ad Meta has not shown yet has nothing to report, and the screen says that instead of drawing zeros as if they were results.
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.analytics_page import count_text, range_choices
from dialogs.base import PrismDialog
from widgets import controls as C


def money(amount) -> str:
    return "Rs {:,.0f}".format(float(amount or 0)) if float(amount or 0) >= 100 else "Rs {:,.2f}".format(float(amount or 0))


def result_words(kind: str) -> tuple:
    """(what a result is called in plural, singular, the key in the numbers)."""
    return {"ctwa": (i18n.t("Chats started"), i18n.t("chat"), "conversations"), "leadform": (i18n.t("Leads"), i18n.t("lead"), "leads")}.get(kind, (i18n.t("Link clicks"), i18n.t("click"), "outbound_clicks"))


def range_dates(key: str, today=None) -> tuple:
    from datetime import timedelta
    today = today or datetime.now(timezone.utc).date()
    days = {"7": 7, "30": 30, "90": 90}.get(key)
    if key == "month":
        return today.replace(day=1).isoformat(), today.isoformat()
    return (today - timedelta(days=(days or 30) - 1)).isoformat(), today.isoformat()


class SpendChart(QWidget):
    """Money spent each day as a column, with the results drawn over it. Hover a day to read its numbers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._days: list = []
        self._noun = ""
        self.setMinimumHeight(170)
        self.setMouseTracking(True)

    def set_days(self, days: list, noun: str = ""):
        self._days, self._noun = list(days or []), noun
        self.update()

    def _area(self) -> QRectF:
        return QRectF(44, 8, max(self.width() - 52, 10), max(self.height() - 30, 10))

    def mouseMoveEvent(self, event):
        area, n = self._area(), len(self._days)
        if n and area.contains(event.position()):
            d = self._days[min(n - 1, int((event.position().x() - area.left()) / (area.width() / n)))]
            self.setToolTip(i18n.t("{day}\nSpent {s} · Shown {i} · Clicks {c} ({r}%) · {noun} {n}").format(
                day=d["day"], s=money(d["spend"]), i=count_text(d["impressions"]), c=count_text(d["clicks"]), r=d["ctr"], noun=self._noun, n=d.get("results", 0)))
        super().mouseMoveEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        area, n = self._area(), len(self._days)
        font = QFont(theme.FONT_BODY)
        font.setPixelSize(10)
        p.setFont(font)
        top = max([d["spend"] for d in self._days] + [1])
        step = max(1, int(-(-top // 4)))
        ceiling = step * 4
        p.setPen(QPen(theme.c(theme.HAIRLINE), 1))
        for k in range(5):
            y = area.bottom() - area.height() * k / 4
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QPen(theme.c(theme.NEUTRAL[500])))
            p.drawText(QRectF(0, y - 8, area.left() - 6, 16), Qt.AlignRight | Qt.AlignVCenter, str(step * k))
            p.setPen(QPen(theme.c(theme.HAIRLINE), 1))
        if not n:
            return
        slot = area.width() / n
        bar = max(2.0, min(slot * 0.7, 22.0))
        best = max([d.get("results", 0) for d in self._days] + [1])
        every = max(1, int(round(n / 7)))
        for i, d in enumerate(self._days):
            x = area.left() + slot * i + (slot - bar) / 2
            h = area.height() * d["spend"] / ceiling
            p.setPen(Qt.NoPen)
            p.setBrush(theme.c(theme.NEUTRAL[300]))
            p.drawRoundedRect(QRectF(x, area.bottom() - h, bar, h), 2, 2)
            r = area.height() * 0.5 * d.get("results", 0) / best
            p.setBrush(theme.c(theme.ACCENT))
            p.drawRoundedRect(QRectF(x + bar * 0.25, area.bottom() - r, bar * 0.5, r), 2, 2)
            if i % every == 0 or i == n - 1:
                p.setPen(QPen(theme.c(theme.NEUTRAL[500])))
                p.drawText(QRectF(x - 20 + bar / 2, area.bottom() + 4, 40, 14), Qt.AlignCenter, d["day"][5:])


class AdResultsDialog(PrismDialog):
    def __init__(self, ad: dict, parent=None):
        super().__init__(ad.get("name") or i18n.t("Ad"), i18n.t("What Meta reports for this ad. It can take a few hours after an ad starts."), icon="chart", parent=parent, scrollable=True)
        self.ad, self._range, self._token = ad, "30", 0
        self.plural, self.singular, self.key = result_words(ad.get("kind"))
        self.chips = C.FilterChips(range_choices()[:3], "30")
        self.chips.setMinimumWidth(340)
        self.chips.changed.connect(self._set_range)
        self.body.addWidget(self.chips)
        self.note = ui.note()
        self.body.addWidget(self.note)
        grid = QGridLayout()
        grid.setSpacing(theme.SPACE_2)
        self.k_spend = C.MetricCard(i18n.t("Spent"), "—", icon="chart")
        self.k_results = C.MetricCard(self.plural, "—", icon="chat")
        self.k_cost = C.MetricCard(i18n.t("Each {r} cost").format(r=self.singular), "—", icon="send")
        self.k_shown = C.MetricCard(i18n.t("Times shown"), "—", icon="eye")
        self.k_clicks = C.MetricCard(i18n.t("Clicks"), "—", icon="send")
        self.k_ctr = C.MetricCard(i18n.t("Clicked after seeing it"), "—", icon="check")
        for i, k in enumerate((self.k_spend, self.k_results, self.k_cost, self.k_shown, self.k_clicks, self.k_ctr)):
            grid.addWidget(k, i // 3, i % 3)
        self.body.addLayout(grid)
        self.body.addWidget(C.label(i18n.t("Spent each day"), level="SUPPORT", weight=700))
        self.chart = SpendChart()
        self.body.addWidget(self.chart)
        self.explain = C.label("", level="META", colour=theme.NEUTRAL[600], wrap=True)
        self.body.addWidget(self.explain)
        self.body.addStretch(1)
        self.footer.set_primary(self.button(i18n.t("Close"), "primary", on_click=self.accept))
        self.resize(660, 640)
        self.load()

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def _set_range(self, key: str):
        self._range = key
        self.load()

    def load(self):
        self._token += 1
        token = self._token
        since, until = range_dates(self._range)
        ui.call(self, "ads/report", {"ad_id": self.ad["id"], "since": since, "until": until}, done=lambda r, t=token: self._shown(t, r), failed=lambda m, _d, t=token: self._failed(t, m))

    def _failed(self, token: int, message: str):
        if token == self._token:
            self.note.error(message)

    def _shown(self, token: int, reply: dict):
        if token != self._token:
            return
        self.note.clear_note()
        days = list(reply.get("days") or [])
        for d in days:
            d["results"] = d.get(self.key, 0)
        t = reply.get("totals") or {}
        if not days:
            for k in (self.k_spend, self.k_results, self.k_cost, self.k_shown, self.k_clicks, self.k_ctr):
                k.set_value("—")
            self.chart.set_days([], self.plural)
            self.explain.setText(i18n.t("Meta has nothing to report for these days yet. An ad that has not run has no numbers."))
            return
        results = t.get(self.key, 0)
        cost = {"ctwa": t.get("cost_per_conversation"), "leadform": t.get("cost_per_lead")}.get(self.ad.get("kind"), t.get("cpc"))
        self.k_spend.set_value(money(t.get("spend")))
        self.k_results.set_value(count_text(results))
        self.k_cost.set_value(money(cost) if cost else "—")
        self.k_shown.set_value(count_text(t.get("impressions")), i18n.t("{n} people").format(n=count_text(t.get("reach"))))
        self.k_clicks.set_value(count_text(t.get("clicks")), i18n.t("{n} went to the destination").format(n=count_text(t.get("outbound_clicks"))))
        self.k_ctr.set_value("%s%%" % t.get("ctr", 0), i18n.t("each click cost {c}").format(c=money(t["cpc"])) if t.get("cpc") else "")
        self.chart.set_days(days, self.plural)
        self.explain.setText(i18n.t("Grey is what was spent each day; the blue is the {r}s that day.").format(r=self.singular))
