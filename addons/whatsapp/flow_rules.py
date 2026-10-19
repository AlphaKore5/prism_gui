"""One condition of a "Choose a path" step: what to look at, how to compare it, and what to compare it with.

The server keeps a condition as {"field", "op", "value"} — field is `message`, `tag`, `hours`, `weekday`, `date`, `time`, `holiday`,
`attr:Name` or `var:name`. This editor shows only the controls the chosen field needs: days of the week as seven buttons, dates and
times as pickers, nothing at all for "is today a holiday". It writes straight into the rule's dict and says `edited` when it does.

No Qt in the rules about what is valid — only in how they are asked for — so a condition that could never work cannot be typed.
"""
from __future__ import annotations

from PySide6.QtCore import QDate, QTime, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDateEdit, QHBoxLayout, QLineEdit, QPushButton, QTimeEdit, QWidget

import i18n
import theme

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def fields() -> list:
    return [("message", i18n.t("What they just wrote")), ("attr", i18n.t("A detail on the contact")), ("tag", i18n.t("A tag on the contact")),
            ("var", i18n.t("Something the flow saved")), ("hours", i18n.t("Whether you are open")), ("weekday", i18n.t("The day of the week")),
            ("date", i18n.t("The date")), ("time", i18n.t("The time of day")), ("holiday", i18n.t("Whether today is a holiday"))]


def day_names() -> dict:
    return {"mon": i18n.t("Mon"), "tue": i18n.t("Tue"), "wed": i18n.t("Wed"), "thu": i18n.t("Thu"), "fri": i18n.t("Fri"), "sat": i18n.t("Sat"), "sun": i18n.t("Sun")}


def ops_for(family: str) -> list:
    """(op, words) for a field. Literal i18n.t calls so the extractor sees every word."""
    if family == "tag":
        return [("eq", i18n.t("is on the contact")), ("ne", i18n.t("is not on the contact")), ("exists", i18n.t("the contact has a tag")),
                ("not_exists", i18n.t("the contact has no tags"))]
    if family == "hours":
        return [("open", i18n.t("open now")), ("closed", i18n.t("closed now"))]
    if family == "weekday":
        return [("in", i18n.t("is one of")), ("ne", i18n.t("is none of"))]
    if family == "date":
        return [("eq", i18n.t("is")), ("gt", i18n.t("is after")), ("lt", i18n.t("is before")), ("between", i18n.t("is between"))]
    if family == "time":
        return [("gt", i18n.t("is after")), ("lt", i18n.t("is before")), ("between", i18n.t("is between"))]
    if family == "holiday":
        return [("yes", i18n.t("is a holiday")), ("no", i18n.t("is not a holiday"))]
    return [("eq", i18n.t("is")), ("ne", i18n.t("is not")), ("contains", i18n.t("contains")), ("starts_with", i18n.t("starts with")),
            ("exists", i18n.t("is filled in")), ("not_exists", i18n.t("is empty")), ("gt", i18n.t("is more than")), ("lt", i18n.t("is less than")),
            ("regex", i18n.t("matches the pattern"))]


def family_of(field: str) -> str:
    base = (field or "message").split(":", 1)[0]
    return base if base in ("tag", "hours", "weekday", "date", "time", "holiday") else "text"


def base_of(field: str) -> str:
    return (field or "message").split(":", 1)[0]


def no_value(family: str, op: str) -> bool:
    return family in ("hours", "holiday") or op in ("exists", "not_exists")


class _DateBox(QWidget):
    """A day, or "today" (whatever day the customer writes on)."""
    edited = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACE_1)
        self.today = QCheckBox(i18n.t("Today"))
        self.edit = QDateEdit(QDate.currentDate())
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("yyyy-MM-dd")
        self.edit.setMinimumHeight(34)
        d = QDate.fromString(text or "", "yyyy-MM-dd")
        if d.isValid():
            self.edit.setDate(d)
        self.today.setChecked(text == "today")
        self.edit.setEnabled(text != "today")
        self.today.toggled.connect(lambda on: (self.edit.setEnabled(not on), self.edited.emit()))
        self.edit.dateChanged.connect(lambda _d: self.edited.emit())
        row.addWidget(self.edit)
        row.addWidget(self.today)

    def value(self) -> str:
        return "today" if self.today.isChecked() else self.edit.date().toString("yyyy-MM-dd")


class _TimeBox(QTimeEdit):
    edited = Signal()

    def __init__(self, text: str, parent=None):
        t = QTime.fromString(text or "", "HH:mm")
        super().__init__(t if t.isValid() else QTime(9, 0), parent)
        self.setDisplayFormat("HH:mm")
        self.setMinimumHeight(34)
        self.timeChanged.connect(lambda _t: self.edited.emit())

    def value(self) -> str:
        return self.time().toString("HH:mm")


class RuleEditor(QWidget):
    """Edits one rule dict in place."""
    edited = Signal()

    def __init__(self, rule: dict, parent=None):
        super().__init__(parent)
        self.rule = rule
        self._loading = True
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACE_2)
        self.field = QComboBox()
        self.field.setMinimumHeight(34)
        for k, label in fields():
            self.field.addItem(label, k)
        self.name = QLineEdit()
        self.name.setMinimumHeight(34)
        self.name.setPlaceholderText(i18n.t("Name"))
        self.op = QComboBox()
        self.op.setMinimumHeight(34)
        self.value = QLineEdit()
        self.value.setMinimumHeight(34)
        self.value.setPlaceholderText(i18n.t("Value"))
        self.days = QWidget()
        dl = QHBoxLayout(self.days)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(2)
        self.day_buttons: dict = {}
        for key, label in day_names().items():
            b = QPushButton(label)
            b.setCheckable(True)
            b.setMinimumHeight(30)
            b.setMinimumWidth(40)
            b.setAccessibleName(label)
            b.toggled.connect(self._changed)
            self.day_buttons[key] = b
            dl.addWidget(b)
        self.date_a, self.date_b = _DateBox(""), _DateBox("")
        self.time_a, self.time_b = _TimeBox(""), _TimeBox("")
        for w, s in ((self.field, 3), (self.name, 2), (self.op, 3), (self.value, 2), (self.days, 0), (self.date_a, 0), (self.date_b, 0), (self.time_a, 0), (self.time_b, 0)):
            row.addWidget(w, s)
        self.field.activated.connect(self._field_chosen)
        self.op.activated.connect(self._changed)
        self.name.textChanged.connect(self._changed)
        self.value.textChanged.connect(self._changed)
        for w in (self.date_a, self.date_b, self.time_a, self.time_b):
            w.edited.connect(self._changed)
        self._load()
        self._loading = False
        self._show()

    # ── reading and writing the rule ─────────────────────────────────────────
    def _load(self):
        field = self.rule.get("field", "message")
        self.field.setCurrentIndex(max(self.field.findData(base_of(field)), 0))
        self.name.setText(field.split(":", 1)[1] if ":" in field else "")
        self._fill_ops(family_of(field), self.rule.get("op", "eq"))
        value = str(self.rule.get("value") or "")
        fam = family_of(field)
        if fam == "weekday":
            on = {d.strip().lower() for d in value.split(",") if d.strip()}
            for k, b in self.day_buttons.items():
                b.setChecked(k in on)
        elif fam in ("date", "time"):
            first, _, second = value.partition("..")
            box_a, box_b = (self.date_a, self.date_b) if fam == "date" else (self.time_a, self.time_b)
            self._set_box(box_a, first)
            self._set_box(box_b, second)
        else:
            self.value.setText(value)

    @staticmethod
    def _set_box(box, text: str):
        if isinstance(box, _DateBox):
            d = QDate.fromString(text, "yyyy-MM-dd")
            box.today.setChecked(text == "today")
            if d.isValid():
                box.edit.setDate(d)
        else:
            t = QTime.fromString(text, "HH:mm")
            if t.isValid():
                box.setTime(t)

    def _fill_ops(self, family: str, current: str):
        self.op.blockSignals(True)
        self.op.clear()
        for k, label in ops_for(family):
            self.op.addItem(label, k)
        self.op.setCurrentIndex(max(self.op.findData(current), 0))
        self.op.blockSignals(False)

    def _field_chosen(self, _i=None):
        fam = family_of(self.field.currentData())
        self._fill_ops(fam, "")
        if fam == "weekday":
            for b in self.day_buttons.values():
                b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(False)
        else:
            self.value.blockSignals(True)
            self.value.clear()
            self.value.blockSignals(False)
        self._changed()

    def _changed(self, *_):
        if self._loading:
            return
        base = self.field.currentData()
        fam = family_of(base)
        op = self.op.currentData()
        self.rule["field"] = ("%s:%s" % (base, self.name.text().strip())) if base in ("attr", "var") else base
        self.rule["op"] = op
        if no_value(fam, op):
            self.rule["value"] = ""
        elif fam == "weekday":
            self.rule["value"] = ",".join(k for k, b in self.day_buttons.items() if b.isChecked())
        elif fam in ("date", "time"):
            a, b = (self.date_a, self.date_b) if fam == "date" else (self.time_a, self.time_b)
            self.rule["value"] = "%s..%s" % (a.value(), b.value()) if op == "between" else a.value()
        else:
            self.rule["value"] = self.value.text()
        self._show()
        self.edited.emit()

    def _show(self):
        base = self.field.currentData()
        fam = family_of(base)
        op = self.op.currentData()
        between = op == "between"
        self.name.setVisible(base in ("attr", "var"))
        self.value.setVisible(fam in ("text", "tag") and not no_value(fam, op))
        self.value.setPlaceholderText(i18n.t("The tag") if fam == "tag" else i18n.t("Value"))
        self.days.setVisible(fam == "weekday")
        self.date_a.setVisible(fam == "date")
        self.date_b.setVisible(fam == "date" and between)
        self.time_a.setVisible(fam == "time")
        self.time_b.setVisible(fam == "time" and between)
