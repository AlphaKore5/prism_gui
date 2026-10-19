"""The Analytics tab — what went out, what it cost, who answered, who opted in, how the campaigns did.

One screen, one request (`reports/dashboard`), for a range you choose. Every figure comes from what the service already stores; the spend is
an ESTIMATE from Meta's own pricing on each delivered message and a rate card you can correct in Settings → Plan and usage, and the page
says so. Premium workspaces can download any of it as a spreadsheet-ready CSV.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import QFileDialog, QFrame, QGridLayout, QHBoxLayout, QMenu, QScrollArea, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from widgets import controls as C

RANGES = (("7", 7), ("30", 30), ("90", 90), ("month", 0))


def range_choices() -> list:
    """Literal i18n.t calls, so the extractor sees each word."""
    return [("7", i18n.t("Last 7 days")), ("30", i18n.t("Last 30 days")), ("90", i18n.t("Last 90 days")), ("month", i18n.t("This month"))]


def range_for(key: str, now: datetime = None) -> tuple:
    """(since, until) ISO strings for a range key. Until is a second past now, so today is included."""
    now = now or datetime.now(timezone.utc)
    until = now + timedelta(seconds=1)
    if key == "month":
        since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        days = dict(RANGES).get(key, 30)
        since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return since.strftime("%Y-%m-%dT%H:%M:%SZ"), until.strftime("%Y-%m-%dT%H:%M:%SZ")


def rupees(amount) -> str:
    """"Rs 12,345" — Indian digit grouping, and words rather than the ₹ sign so it always draws."""
    n = int(round(float(amount or 0)))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return "Rs %s%s" % ("-" if n < 0 else "", s)


def count_text(n) -> str:
    n = int(n or 0)
    return "{:,}".format(n)


def duration_text(seconds) -> str:
    if seconds is None:
        return "—"
    s = int(round(float(seconds)))
    if s < 60:
        return i18n.t("{n} s").format(n=s)
    m, s = divmod(s, 60)
    if m < 60:
        return i18n.t("{m} min {s} s").format(m=m, s=s) if s else i18n.t("{m} min").format(m=m)
    h, m = divmod(m, 60)
    return i18n.t("{h} h {m} min").format(h=h, m=m) if m else i18n.t("{h} h").format(h=h)


def category_name(category: str) -> str:
    return {"MARKETING": i18n.t("Marketing"), "UTILITY": i18n.t("Utility"), "AUTHENTICATION": i18n.t("Authentication"), "SERVICE": i18n.t("Service (free)"),
            "UNKNOWN": i18n.t("Not yet priced")}.get(category, category.title())


class DayChart(QWidget):
    """Messages by day: a column for what was sent, with the share that was read drawn over it. Hover a day to read its numbers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._days: list = []
        self.setMinimumHeight(190)
        self.setMouseTracking(True)

    def set_days(self, days: list):
        self._days = list(days or [])
        self.update()

    def _geometry(self):
        left, right, top, bottom = 38, 8, 8, 24
        return QRectF(left, top, max(self.width() - left - right, 10), max(self.height() - top - bottom, 10))

    def mouseMoveEvent(self, event):
        area, n = self._geometry(), len(self._days)
        if n and area.contains(event.position()):
            i = min(n - 1, int((event.position().x() - area.left()) / (area.width() / n)))
            d = self._days[i]
            self.setToolTip(i18n.t("{day}\nSent {s} · Delivered {d} · Read {r} · Failed {f}").format(day=d["day"], s=d["sent"], d=d["delivered"], r=d["read"], f=d["failed"]))
        super().mouseMoveEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        area = self._geometry()
        font = QFont(theme.FONT_BODY)
        font.setPixelSize(11)
        p.setFont(font)
        n = len(self._days)
        top = max([d["sent"] for d in self._days] + [1])
        ceiling = max(top, 1)
        step = max(1, -(-ceiling // 4))
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
        bar = max(2.0, min(slot * 0.7, 26.0))
        every = max(1, int(round(n / 8)))
        for i, d in enumerate(self._days):
            x = area.left() + slot * i + (slot - bar) / 2
            h = area.height() * d["sent"] / ceiling
            p.setPen(Qt.NoPen)
            p.setBrush(theme.c(theme.NEUTRAL[300]))
            p.drawRoundedRect(QRectF(x, area.bottom() - h, bar, h), 2, 2)
            hr = area.height() * d["read"] / ceiling
            p.setBrush(theme.c(theme.ACCENT))
            p.drawRoundedRect(QRectF(x, area.bottom() - hr, bar, hr), 2, 2)
            if i % every == 0 or i == n - 1:
                p.setPen(QPen(theme.c(theme.NEUTRAL[500])))
                p.drawText(QRectF(x - 20 + bar / 2, area.bottom() + 4, 40, 16), Qt.AlignCenter, d["day"][5:])


class _Table(QWidget):
    """A small read-only table: a header line, then a hairline between rows."""

    def __init__(self, headers: list, aligns: list = None, parent=None):
        super().__init__(parent)
        self._headers = headers
        self._aligns = aligns or [Qt.AlignLeft] + [Qt.AlignRight] * (len(headers) - 1)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(theme.SPACE_4)
        self._grid.setVerticalSpacing(0)
        self.set_rows([])

    def set_rows(self, rows: list, empty: str = ""):
        ui.clear(self._grid)
        for c, h in enumerate(self._headers):
            lab = C.label(h.upper(), level="LABEL", colour=theme.NEUTRAL[500])
            lab.setAlignment(self._aligns[c] | Qt.AlignVCenter)
            self._grid.addWidget(lab, 0, c)
        for r, row in enumerate(rows, start=1):
            for c, v in enumerate(row):
                lab = C.label(str(v), level="SUPPORT", weight=700 if c == 0 else 400, colour=theme.TEXT if c == 0 else theme.NEUTRAL[700])
                lab.setAlignment(self._aligns[c] | Qt.AlignVCenter)
                lab.setMinimumHeight(30)
                self._grid.addWidget(lab, r, c)
        if not rows and empty:
            note = C.label(empty, level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True)
            self._grid.addWidget(note, 1, 0, 1, len(self._headers))
        self._grid.setColumnStretch(0, 1)


class AnalyticsPage(QWidget):
    openSettings = Signal(str)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self._range = "30"
        self._data = None
        self._token = 0
        self._can_download = False

        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SPACE_4, theme.SPACE_4, theme.SPACE_4, theme.SPACE_4)
        root.setSpacing(theme.SPACE_3)

        head = QHBoxLayout()
        head.setSpacing(theme.SPACE_3)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(C.label(i18n.t("Analytics"), level="CARD_TITLE"))
        self.sub = C.label(i18n.t("How your WhatsApp number is doing."), level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True)
        titles.addWidget(self.sub)
        head.addLayout(titles, stretch=1)
        self.chips = C.FilterChips(range_choices(), "30")
        self.chips.setMinimumWidth(440)                          # chips wrap onto lines when a row gives them no width of their own
        self.chips.changed.connect(self._set_range)
        head.addWidget(self.chips)
        self.download_btn = C.button(i18n.t("Download"), "secondary", "download", on_click=self._menu)
        head.addWidget(self.download_btn)
        root.addLayout(head)

        self.note = ui.note()
        root.addWidget(self.note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        host = QWidget()
        ui.see_through(host)
        col = QVBoxLayout(host)
        col.setContentsMargins(0, 0, theme.SPACE_2, 0)
        col.setSpacing(theme.SPACE_3)
        scroll.setWidget(host)
        root.addWidget(scroll, stretch=1)

        kpis = QHBoxLayout()
        kpis.setSpacing(theme.SPACE_3)
        self.k_sent = C.MetricCard(i18n.t("Messages sent"), "—", icon="send")
        self.k_delivered = C.MetricCard(i18n.t("Delivered"), "—", icon="check")
        self.k_read = C.MetricCard(i18n.t("Read"), "—", icon="eye")
        self.k_received = C.MetricCard(i18n.t("Received"), "—", icon="inbox")
        self.k_chats = C.MetricCard(i18n.t("New chats"), "—", icon="chat")
        self.k_spend = C.MetricCard(i18n.t("Meta spend (estimate)"), "—", icon="chart")
        for k in (self.k_sent, self.k_delivered, self.k_read, self.k_received, self.k_chats, self.k_spend):
            kpis.addWidget(k, stretch=1)
        col.addLayout(kpis)

        card, cc = ui.card(i18n.t("Messages by day"), i18n.t("Grey is what you sent; the darker part is what was read."))
        self.chart = DayChart()
        cc.addWidget(self.chart)
        col.addWidget(card)

        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        card, sc = ui.card(i18n.t("Where the spend goes"), i18n.t("An estimate from Meta's own pricing on each delivered message. Meta's invoice is the real figure."))
        self.spend_table = _Table([i18n.t("Category"), i18n.t("Messages"), i18n.t("Billed"), i18n.t("Rate"), i18n.t("Cost")])
        sc.addWidget(self.spend_table)
        self.spend_note = C.label("", level="META", colour=theme.NEUTRAL[500], wrap=True)
        sc.addWidget(self.spend_note)
        self.rates_btn = C.button(i18n.t("Correct the rates"), "tertiary", on_click=lambda: self.openSettings.emit("plan"))
        sc.addWidget(self.rates_btn, alignment=Qt.AlignLeft)
        row.addWidget(card, stretch=3)
        card, oc = ui.card(i18n.t("Opt-ins and opt-outs"), "")
        self.opt_in = C.label("", level="CARD_TITLE")
        self.opt_out = C.label("", level="SUPPORT", colour=theme.NEUTRAL[700])
        self.opt_now = C.label("", level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True)
        for w in (self.opt_in, self.opt_out, self.opt_now):
            oc.addWidget(w)
        self.handoffs = C.label("", level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True)
        oc.addWidget(self.handoffs)
        oc.addStretch(1)
        row.addWidget(card, stretch=2)
        col.addLayout(row)

        card, tc = ui.card(i18n.t("Team"), i18n.t("What each person did in this range."))
        self.team_table = _Table([i18n.t("Name"), i18n.t("Replies"), i18n.t("Chats"), i18n.t("Resolved"), i18n.t("Open now"), i18n.t("Average reply")])
        tc.addWidget(self.team_table)
        col.addWidget(card)

        card, mc = ui.card(i18n.t("Latest campaigns"), "")
        self.campaign_table = _Table([i18n.t("Campaign"), i18n.t("Sent"), i18n.t("Delivered"), i18n.t("Read"), i18n.t("Replied"), i18n.t("Clicked"), i18n.t("Spend")])
        mc.addWidget(self.campaign_table)
        col.addWidget(card)
        col.addStretch(1)

    # ── lifecycle ────────────────────────────────────────────────────────────
    def activate(self):
        self._load()

    def deactivate(self):
        self._token += 1                                      # an answer that arrives after we left is not for anyone

    # ── loading ──────────────────────────────────────────────────────────────
    def _set_range(self, key: str):
        self._range = key
        self._load()

    def _load(self):
        self._token += 1
        token = self._token
        since, until = range_for(self._range)
        self.sub.setText(i18n.t("Loading…"))
        ui.call(self, "reports/dashboard", {"since": since, "until": until}, done=lambda r, t=token: self._on_data(t, r),
                failed=lambda m, _d, t=token: self._on_failed(t, m))

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def _on_failed(self, token: int, message: str):
        if token != self._token:
            return
        self.sub.setText(i18n.t("Couldn't load your numbers."))
        self.note.error(message)

    def _on_data(self, token: int, reply: dict):
        if token != self._token:
            return
        self._data = reply
        self.note.clear_note()
        o, u = reply.get("overview") or {}, reply.get("usage") or {}
        t, days = o.get("totals") or {}, o.get("days") or []
        self.sub.setText(i18n.t("{a} to {b}").format(a=(days[0]["day"] if days else "—"), b=(days[-1]["day"] if days else "—")))
        self.k_sent.set_value(count_text(t.get("sent")), i18n.t("{n} failed").format(n=count_text(t.get("failed"))))
        self.k_delivered.set_value("%s%%" % round(t.get("delivered_rate") or 0), i18n.t("{n} delivered").format(n=count_text(t.get("delivered"))))
        self.k_read.set_value("%s%%" % round(t.get("read_rate") or 0), i18n.t("{n} read").format(n=count_text(t.get("read"))))
        self.k_received.set_value(count_text(t.get("received")), i18n.t("{n} asked for a person").format(n=count_text(t.get("handoffs"))))
        self.k_chats.set_value(count_text(t.get("new_chats")), i18n.t("{n} new contacts").format(n=count_text(t.get("new_contacts"))))
        ut = u.get("totals") or {}
        self.k_spend.set_value(rupees(ut.get("cost")), i18n.t("{c} with GST").format(c=rupees(ut.get("cost_with_gst"))))
        self.chart.set_days(days)
        self.spend_table.set_rows([[category_name(c["category"]), count_text(c["messages"]), count_text(c["billable"]), ("Rs %.2f" % c["rate"]) if c.get("rate") else "—",
                                    rupees(c["cost"])] for c in u.get("by_category") or []], i18n.t("Nothing has been billed in this range."))
        self.spend_note.setText(i18n.t("Estimated at the rates in Settings, Plan and usage, plus 18% GST."))
        optins = reply.get("optins") or {}
        ot = optins.get("totals") or {}
        self.opt_in.setText(i18n.t("{n} opted in").format(n=count_text(ot.get("opt_in"))))
        self.opt_out.setText(i18n.t("{n} opted out").format(n=count_text(ot.get("opt_out"))))
        now = optins.get("now") or {}
        self.opt_now.setText(i18n.t("Right now {a} of your {b} contacts can be messaged and {c} have opted out.").format(
            a=count_text(now.get("opted_in")), b=count_text(now.get("contacts")), c=count_text(now.get("opted_out"))))
        self.handoffs.setText(i18n.t("{n} chats are open right now.").format(n=count_text(reply.get("open_chats"))))
        self.team_table.set_rows([[a["name"], count_text(a["replies"]), count_text(a["chats"]), count_text(a["resolved"]), count_text(a["open_now"]),
                                   duration_text(a.get("avg_reply_seconds"))] for a in reply.get("agents") or []], i18n.t("No one has replied in this range."))
        self.campaign_table.set_rows([[c["name"], count_text(c["sent"]), "%s%%" % round((c.get("rates") or {}).get("delivered", 0)), "%s%%" % round((c.get("rates") or {}).get("read", 0)),
                                       count_text(c.get("replied")), count_text(c.get("clicked")), rupees(c.get("spend"))] for c in reply.get("campaigns") or []],
                                     i18n.t("No campaign was created in this range."))
        self._can_download = bool(reply.get("can_download"))
        self.download_btn.setToolTip("" if self._can_download else i18n.t("Downloading reports is part of the Premium plan."))

    # ── downloads ────────────────────────────────────────────────────────────
    def _menu(self):
        menu = QMenu(self)
        for kind, label in (("overview", i18n.t("Messages by day")), ("usage", i18n.t("Spend by day")), ("campaigns", i18n.t("Campaigns")),
                            ("agents", i18n.t("Team")), ("optins", i18n.t("Opt-ins and opt-outs"))):
            menu.addAction(label).triggered.connect(lambda _=False, k=kind: self.download(k))
        menu.exec(self.download_btn.mapToGlobal(self.download_btn.rect().bottomLeft()))

    def download(self, kind: str):
        since, until = range_for(self._range)
        ui.call(self, "reports/download", {"kind": kind, "since": since, "until": until}, done=self._save_csv, failed=lambda m, _d: self.note.error(m))

    def _save_csv(self, reply: dict):
        target, _f = QFileDialog.getSaveFileName(self, i18n.t("Save the report"), reply.get("filename") or "report.csv", "CSV (*.csv)")
        if not target:
            return
        try:
            with open(target, "w", encoding="utf-8-sig", newline="") as fh:              # the sign Excel looks for, so Hindi and Gujarati names open correctly
                fh.write(reply.get("csv") or "")
            C.show_toast(self, i18n.t("Saved"), target)
        except OSError as exc:
            self.note.error(i18n.t("Couldn't save it: {e}").format(e=exc))
