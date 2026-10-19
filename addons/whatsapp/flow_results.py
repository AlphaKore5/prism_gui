"""Automations → Flows → Results: how one flow is doing.

How many customers started it, how many finished, how many it handed to a person, and — step by step — how many reached each step and where
people stopped answering. It reads `flows/analytics`, which counts what the server already records for every run; nothing is guessed. A step with
a high "stopped" share is where customers give up: the question that is too long, the form that asks too much.
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import flow_model as M
from addons.whatsapp import ui
from addons.whatsapp.analytics_page import count_text, range_choices, range_for
from widgets import controls as C

WARN_LINE = "rgba(202, 138, 4, 0.40)"


class RunsChart(QWidget):
    """Customers who started the flow, a column for each day. Hover a day to read its number."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._days: list = []
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    def set_days(self, days: list):
        self._days = list(days or [])
        self.update()

    def _area(self) -> QRectF:
        return QRectF(30, 6, max(self.width() - 36, 10), max(self.height() - 26, 10))

    def mouseMoveEvent(self, event):
        area, n = self._area(), len(self._days)
        if n and area.contains(event.position()):
            d = self._days[min(n - 1, int((event.position().x() - area.left()) / (area.width() / n)))]
            self.setToolTip(i18n.t("{day}: {n} started").format(day=d["day"], n=d["runs"]))
        super().mouseMoveEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        area, n = self._area(), len(self._days)
        font = QFont(theme.FONT_BODY)
        font.setPixelSize(10)
        p.setFont(font)
        top = max([d["runs"] for d in self._days] + [1])
        step = max(1, -(-top // 3))
        p.setPen(QPen(theme.c(theme.HAIRLINE), 1))
        for k in range(4):
            y = area.bottom() - area.height() * k / 3
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QPen(theme.c(theme.NEUTRAL[500])))
            p.drawText(QRectF(0, y - 8, area.left() - 4, 16), Qt.AlignRight | Qt.AlignVCenter, str(step * k))
            p.setPen(QPen(theme.c(theme.HAIRLINE), 1))
        if not n:
            return
        slot = area.width() / n
        bar = max(2.0, min(slot * 0.7, 18.0))
        every = max(1, int(round(n / 5)))
        for i, d in enumerate(self._days):
            x = area.left() + slot * i + (slot - bar) / 2
            h = area.height() * d["runs"] / (step * 3)
            p.setPen(Qt.NoPen)
            p.setBrush(theme.c(theme.ACCENT))
            p.drawRoundedRect(QRectF(x, area.bottom() - h, bar, h), 2, 2)
            if i % every == 0 or i == n - 1:
                p.setPen(QPen(theme.c(theme.NEUTRAL[500])))
                p.drawText(QRectF(x - 20 + bar / 2, area.bottom() + 3, 40, 14), Qt.AlignCenter, d["day"][5:])


def percent(part, whole) -> str:
    return "%d%%" % round(100.0 * part / whole) if whole else "0%"


def step_rows(reply: dict) -> list:
    """What the table shows for each step: (name, kind words, snippet, reached, share of the first step that reached it, stopped, stopped %)."""
    nodes = reply.get("nodes") or []
    first = max([n.get("reached", 0) for n in nodes] + [0])
    out = []
    for n in nodes:
        out.append({"node": n["node"], "kind": M.type_name(n.get("kind")), "text": n.get("text") or "", "reached": int(n.get("reached", 0)),
                    "share": (n.get("reached", 0) / first) if first else 0.0, "stopped": int(n.get("stopped", 0)), "stopped_pct": float(n.get("stopped_pct", 0.0))})
    return out


class _StepBar(QFrame):
    """One step of the flow: how many reached it as a bar, and how many gave up there."""

    def __init__(self, row: dict, worst: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("waFlowStepBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        line = WARN_LINE if worst else theme.HAIRLINE
        self.setStyleSheet(f"#waFlowStepBar {{ background: rgba(255,255,255,0.55); border: 1px solid {line}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(self)
        col.setContentsMargins(12, 8, 12, 8)
        col.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(theme.SPACE_2)
        top.addWidget(C.label(row["node"], level="SUPPORT", weight=700), 1)
        top.addWidget(C.label(row["kind"], level="META", colour=theme.NEUTRAL[500]))
        col.addLayout(top)
        if row["text"]:
            col.addWidget(C.label(row["text"], level="META", colour=theme.NEUTRAL[600], wrap=True))
        self.bar = C.ProgressBar(row["share"])
        col.addWidget(self.bar)
        nums = QHBoxLayout()
        nums.addWidget(C.label(i18n.t("{n} reached it").format(n=count_text(row["reached"])), level="META", colour=theme.NEUTRAL[700]), 1)
        if row["stopped"]:
            nums.addWidget(C.label(i18n.t("{n} stopped here ({p}%)").format(n=count_text(row["stopped"]), p=round(row["stopped_pct"])), level="META",
                                   colour=theme.WARN_INK if worst else theme.NEUTRAL[600], weight=700 if worst else 400))
        col.addLayout(nums)
        self.setToolTip(i18n.t("{n} customers reached this step, and {s} of them were still here — waiting, failed or cancelled — when the flow stopped.").format(
            n=row["reached"], s=row["stopped"]))


class FlowResults(QWidget):
    """The Results view of one flow."""

    def __init__(self, flow_id: str, parent=None):
        super().__init__(parent)
        self.flow_id = flow_id
        self._range = "30"
        self._token = 0
        self.data: dict = {}
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_2)
        top = QHBoxLayout()
        top.addWidget(C.label(i18n.t("Results"), level="CARD_TITLE"), stretch=1)
        col.addLayout(top)
        self.chips = C.FilterChips(range_choices()[:3], "30")
        self.chips.setMinimumWidth(300)
        self.chips.changed.connect(self._set_range)
        col.addWidget(self.chips)
        self.note = ui.note()
        col.addWidget(self.note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        host = QWidget()
        ui.see_through(host)
        self.body = QVBoxLayout(host)
        self.body.setContentsMargins(0, 0, 4, 0)
        self.body.setSpacing(theme.SPACE_2)
        scroll.setWidget(host)
        col.addWidget(scroll, 1)

        grid = QGridLayout()
        grid.setSpacing(theme.SPACE_2)
        self.k_started = C.MetricCard(i18n.t("Started"), "—", icon="play")
        self.k_done = C.MetricCard(i18n.t("Finished"), "—", icon="check")
        self.k_person = C.MetricCard(i18n.t("Handed to a person"), "—", icon="user")
        self.k_steps = C.MetricCard(i18n.t("Steps each"), "—", icon="list")
        for i, k in enumerate((self.k_started, self.k_done, self.k_person, self.k_steps)):
            grid.addWidget(k, i // 2, i % 2)
        self.body.addLayout(grid)
        self.body.addWidget(C.label(i18n.t("Started each day"), level="SUPPORT", weight=700))
        self.chart = RunsChart()
        self.body.addWidget(self.chart)
        self.body.addWidget(C.label(i18n.t("Step by step"), level="SUPPORT", weight=700))
        self.steps_col = QVBoxLayout()
        self.steps_col.setSpacing(theme.SPACE_1)
        self.body.addLayout(self.steps_col)
        self.empty = C.label("", level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True)
        self.body.addWidget(self.empty)
        self.body.addStretch(1)

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def load(self):
        self._token += 1
        token = self._token
        since, until = range_for(self._range, datetime.now(timezone.utc))
        ui.call(self, "flows/analytics", {"flow_id": self.flow_id, "since": since, "until": until},
                done=lambda r, t=token: self._shown(t, r), failed=lambda m, _d, t=token: self._failed(t, m))

    def _set_range(self, key: str):
        self._range = key
        self.load()

    def _failed(self, token: int, message: str):
        if token == self._token:
            self.note.error(message)

    def _shown(self, token: int, reply: dict):
        if token != self._token:
            return
        self.data = reply
        self.note.clear_note()
        t = reply.get("totals") or {}
        started = int(t.get("started", 0))
        self.k_started.set_value(count_text(started), i18n.t("{n} still in it").format(n=count_text(t.get("in_progress", 0))))
        self.k_done.set_value(count_text(t.get("done", 0)), i18n.t("{p}% of those who started").format(p=round(float(t.get("completion_rate", 0)))))
        self.k_person.set_value(count_text(t.get("handed_to_person", 0)), percent(t.get("handed_to_person", 0), started))
        self.k_steps.set_value("%.1f" % float(t.get("avg_steps", 0)), i18n.t("on average"))
        self.chart.set_days(reply.get("days") or [])
        ui.clear(self.steps_col)
        rows = step_rows(reply)
        worst = max(rows, key=lambda r: (r["stopped_pct"] if r["reached"] >= 5 else 0.0), default=None)
        for r in rows:
            self.steps_col.addWidget(_StepBar(r, worst is not None and r is worst and r["stopped_pct"] >= 15.0))
        if not started:
            self.empty.setText(i18n.t("Nobody has been through this flow in this time. Publish it and switch it on, and the results appear here."))
        else:
            self.empty.setText(i18n.t("A step with many “stopped here” is where customers give up. Shorten its question or give them buttons."))
