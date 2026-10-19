"""The days the business is closed, as a list the Team settings edit and a flow's “Whether today is a holiday” condition reads.

Stored with the inbox rules as [{"date": "2026-11-12", "name": "Diwali"}] — at most 60, each day once, in date order — and sent back to the server
sorted. The only holidays this adds for you are the three that fall on the same date every year; festivals move, so you type those yourself.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import QDateEdit, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from widgets import controls as C

MAXIMUM = 60


def national_days(today: date = None) -> list:
    """The fixed-date national holidays that are still to come this year, or next year's once this year's have passed."""
    today = today or date.today()
    days = [(1, 26, i18n.t("Republic Day")), (8, 15, i18n.t("Independence Day")), (10, 2, i18n.t("Gandhi Jayanti"))]
    year = today.year if any(date(today.year, m, d) >= today for m, d, _n in days) else today.year + 1
    return [{"date": date(year, m, d).isoformat(), "name": n} for m, d, n in days if date(year, m, d) >= today or year != today.year]


def clean(rows: list) -> list:
    """What goes to the server: valid days only, each once, oldest first."""
    seen, out = set(), []
    for r in rows or []:
        day = str((r or {}).get("date") or "").strip()
        if not day or day in seen:
            continue
        seen.add(day)
        name = str((r or {}).get("name") or "").strip()[:60]
        out.append({"date": day, "name": name} if name else {"date": day})
    return sorted(out, key=lambda x: x["date"])[:MAXIMUM]


class _Row(QWidget):
    removed = Signal(object)
    edited = Signal()

    def __init__(self, day: str, name: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACE_2)
        self.date = QDateEdit(QDate.currentDate())
        d = QDate.fromString(day or "", "yyyy-MM-dd")
        if d.isValid():
            self.date.setDate(d)
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("ddd d MMM yyyy")
        self.date.setMinimumHeight(34)
        self.date.setMinimumWidth(170)
        self.date.setAccessibleName(i18n.t("Holiday date"))
        self.date.dateChanged.connect(lambda _d: self.edited.emit())
        self.name = QLineEdit(name or "")
        self.name.setMinimumHeight(34)
        self.name.setMaxLength(60)
        self.name.setPlaceholderText(i18n.t("What it is, e.g. Diwali"))
        self.name.setAccessibleName(i18n.t("Holiday name"))
        self.name.textChanged.connect(lambda _t: self.edited.emit())
        row.addWidget(self.date)
        row.addWidget(self.name, 1)
        row.addWidget(C.icon_button("trash", i18n.t("Remove this day"), on_click=lambda: self.removed.emit(self), colour=theme.NEUTRAL[600]))

    def value(self) -> dict:
        return {"date": self.date.date().toString("yyyy-MM-dd"), "name": self.name.text().strip()}


class HolidaysEditor(QWidget):
    edited = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list = []
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_1)
        self.rows_col = QVBoxLayout()
        self.rows_col.setSpacing(theme.SPACE_1)
        col.addLayout(self.rows_col)
        self.empty = C.label(i18n.t("No holidays. Add the days you are closed and a flow can answer differently on them."), level="META", colour=theme.NEUTRAL[600], wrap=True)
        col.addWidget(self.empty)
        buttons = QHBoxLayout()
        self.add_btn = C.button(i18n.t("Add a day"), "tertiary", icon_name="plus", on_click=lambda: self.add("", ""))
        self.national_btn = C.button(i18n.t("Add national holidays"), "tertiary", on_click=self._national)
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.national_btn)
        buttons.addStretch(1)
        col.addLayout(buttons)

    def set_value(self, rows: list):
        for r in list(self._rows):
            self._discard(r)
        for r in clean(rows):
            self.add(r["date"], r.get("name", ""), announce=False)
        self._sync()

    def value(self) -> list:
        return clean([r.value() for r in self._rows])

    def add(self, day: str, name: str, announce: bool = True):
        if len(self._rows) >= MAXIMUM:
            return
        row = _Row(day, name)
        row.removed.connect(lambda r: (self._discard(r), self._sync(), self.edited.emit()))
        row.edited.connect(self.edited.emit)
        self._rows.append(row)
        self.rows_col.addWidget(row)
        self._sync()
        if announce:
            self.edited.emit()

    def _discard(self, row):
        if row in self._rows:
            self._rows.remove(row)
        ui.discard(row)

    def _national(self):
        have = {r.value()["date"] for r in self._rows}
        for h in national_days():
            if h["date"] not in have:
                self.add(h["date"], h["name"], announce=False)
        self._sync()
        self.edited.emit()

    def _sync(self):
        self.empty.setVisible(not self._rows)
        self.add_btn.setVisible(len(self._rows) < MAXIMUM)
