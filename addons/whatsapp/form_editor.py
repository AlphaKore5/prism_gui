"""The form editor: screens, fields, what to do with the answers, and — for a booking form — the opening hours.

A form is a few screens a customer taps through inside the chat. Each screen has a title, a button, some words and fields (a name box, a date, a choice). The editor keeps the whole form
in one dictionary (`self.form`, the shape the server uses) and rebuilds the cards from it when the structure changes; `collect()` reads the widgets back before any save or check.
Problems are shown in words, with where they are, from the same checks the server runs before it will give a form to Meta.
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLineEdit, QMenu, QPlainTextEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import ui
from widgets import controls as C

KIND_NAMES = ("text", "email", "phone", "number", "paragraph", "date", "dropdown", "radio", "checkbox", "opt_in")
CHOICE = ("dropdown", "radio", "checkbox")
WEEKDAYS = (0, 1, 2, 3, 4, 5, 6)


def kind_choices() -> list:
    """Literal i18n.t calls so the string extractor sees each word."""
    return [("text", i18n.t("Short answer")), ("email", i18n.t("E-mail address")), ("phone", i18n.t("Phone number")), ("number", i18n.t("Number")), ("paragraph", i18n.t("Long answer")),
            ("date", i18n.t("Date")), ("dropdown", i18n.t("Pick from a list")), ("radio", i18n.t("Pick one")), ("checkbox", i18n.t("Pick several")), ("opt_in", i18n.t("Tick to agree"))]


def category_choices() -> list:
    return [("LEAD_GENERATION", i18n.t("Getting enquiries")), ("APPOINTMENT_BOOKING", i18n.t("Booking a visit")), ("SURVEY", i18n.t("Asking for feedback")), ("SIGN_UP", i18n.t("Collecting details")),
            ("CONTACT_US", i18n.t("Contact us")), ("CUSTOMER_SUPPORT", i18n.t("Customer support")), ("SIGN_IN", i18n.t("Signing in")), ("OTHER", i18n.t("Something else"))]


def weekday_names() -> list:
    return [i18n.t("Mon"), i18n.t("Tue"), i18n.t("Wed"), i18n.t("Thu"), i18n.t("Fri"), i18n.t("Sat"), i18n.t("Sun")]


def machine_name(label: str, taken: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")[:30] or "field"
    if not base[0].isalpha():
        base = "f_" + base
    name, n = base, 2
    while name in taken:
        name = "%s_%d" % (base, n)
        n += 1
    return name


def _line(text: str = "", placeholder: str = "") -> QLineEdit:
    e = QLineEdit(text)
    e.setMinimumHeight(36)
    e.setPlaceholderText(placeholder)
    return e


class _Card(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("waFormCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#waFormCard {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        self.col = QVBoxLayout(self)
        self.col.setContentsMargins(14, 12, 14, 12)
        self.col.setSpacing(theme.SPACE_2)


class FieldCard(_Card):
    """One field of a screen."""
    removed = Signal(object)
    moved = Signal(object, int)

    def __init__(self, field: dict, mapping: str, editor: "FormEditor"):
        super().__init__()
        self.field, self.editor = dict(field), editor
        self.name_edited = bool(field.get("name"))
        live = field.get("live")
        top = QHBoxLayout()
        top.setSpacing(theme.SPACE_2)
        self.kind = QComboBox()
        self.kind.setMinimumHeight(36)
        self.kind.setAccessibleName(i18n.t("Kind of field"))
        for key, label in kind_choices():
            self.kind.addItem(label, key)
        self.kind.setCurrentIndex(max(self.kind.findData(field.get("kind") or "text"), 0))
        self.kind.currentIndexChanged.connect(self._kind_changed)
        top.addWidget(self.kind, 2)
        self.label = _line(field.get("label") or "", i18n.t("What the customer sees"))
        self.label.setAccessibleName(i18n.t("Label"))
        self.label.setMaxLength(80)
        self.label.textEdited.connect(self._label_typed)
        top.addWidget(self.label, 3)
        self.required = QCheckBox(i18n.t("Required"))
        self.required.setChecked(field.get("required") is not False)
        top.addWidget(self.required)
        top.addWidget(C.button(i18n.t("Up"), "tertiary", small=True, on_click=lambda: self.moved.emit(self, -1)))
        top.addWidget(C.button(i18n.t("Down"), "tertiary", small=True, on_click=lambda: self.moved.emit(self, 1)))
        top.addWidget(C.button(i18n.t("Remove"), "tertiary", small=True, on_click=lambda: self.removed.emit(self)))
        self.col.addLayout(top)
        more = QHBoxLayout()
        more.setSpacing(theme.SPACE_2)
        self.name = _line(field.get("name") or "", i18n.t("code name"))
        self.name.setAccessibleName(i18n.t("Code name"))
        self.name.textEdited.connect(lambda _t: setattr(self, "name_edited", True))
        more.addWidget(ui.field(i18n.t("Code name"), self.name, i18n.t("Lowercase letters, numbers and _. Used in the answers.")), 2)
        self.helper = _line(field.get("helper") or "", "")
        self.helper.setAccessibleName(i18n.t("Hint"))
        more.addWidget(ui.field(i18n.t("Hint under it"), self.helper), 3)
        self.col.addLayout(more)
        self.options = QPlainTextEdit("\n".join(o["title"] for o in field.get("options") or []))
        self.options.setMinimumHeight(70)
        self.options.setMaximumHeight(110)
        self.options.setAccessibleName(i18n.t("Choices"))
        self.options_box = ui.field(i18n.t("Choices"), self.options, i18n.t("One per line, up to 30 characters each."))
        self.col.addWidget(self.options_box)
        self.live_note = C.label(i18n.t("The free times are worked out live from your opening hours when the customer picks a day."), level="META", colour=theme.NEUTRAL[600], wrap=True)
        self.col.addWidget(self.live_note)
        save = QHBoxLayout()
        save.setSpacing(theme.SPACE_2)
        self.save_to = QComboBox()
        self.save_to.setMinimumHeight(36)
        self.save_to.setAccessibleName(i18n.t("Save the answer to"))
        self.save_to.addItem(i18n.t("Don't save on the contact"), "")
        self.save_to.addItem(i18n.t("The contact's name"), "@name")
        self.save_to.addItem(i18n.t("The contact's e-mail"), "@email")
        self.save_to.addItem(i18n.t("A detail called…"), "__detail__")
        self.detail = _line("", i18n.t("Detail name, like City"))
        self.detail.setAccessibleName(i18n.t("Detail name"))
        if mapping in ("@name", "@email"):
            self.save_to.setCurrentIndex(self.save_to.findData(mapping))
        elif mapping:
            self.save_to.setCurrentIndex(self.save_to.findData("__detail__"))
            self.detail.setText(mapping)
        self.save_to.currentIndexChanged.connect(self._save_changed)
        save.addWidget(ui.field(i18n.t("Save the answer to"), self.save_to), 2)
        save.addWidget(ui.field(i18n.t("Detail name"), self.detail), 2)
        self.col.addLayout(save)
        self.live = live
        self._save_changed()
        self._kind_changed()

    def _label_typed(self, text: str):
        if not self.name_edited:
            taken = {c.name.text() for c in self.editor.all_field_cards() if c is not self}
            self.name.setText(machine_name(text, taken))

    def _kind_changed(self, *_):
        kind = self.kind.currentData()
        self.options_box.setVisible(kind in CHOICE and self.live != "slots")
        self.live_note.setVisible(self.live == "slots" or self.live == "date")
        self.live_note.setText(i18n.t("The free times are worked out live from your opening hours when the customer picks a day.") if self.live == "slots" else
                               i18n.t("When a day is picked, the form asks Prism which times are free."))

    def _save_changed(self, *_):
        self.detail.parentWidget().setVisible(self.save_to.currentData() == "__detail__")

    def read(self) -> tuple:
        """-> (field dict, mapping target or '')"""
        kind = self.kind.currentData()
        f = {"kind": kind, "name": self.name.text().strip().lower(), "label": self.label.text().strip(), "required": self.required.isChecked()}
        if self.helper.text().strip():
            f["helper"] = self.helper.text().strip()
        if kind in CHOICE:
            f["options"] = [] if self.live == "slots" else [{"id": re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")[:30] or "x", "title": t.strip()}
                                                              for t in self.options.toPlainText().splitlines() if t.strip()]
        if self.live:
            f["live"] = self.live
        target = self.save_to.currentData()
        if target == "__detail__":
            target = self.detail.text().strip()
        return f, target or ""


class ScreenCard(_Card):
    removed = Signal(object)
    moved = Signal(object, int)

    def __init__(self, screen: dict, number: int, mapping: dict, editor: "FormEditor"):
        super().__init__()
        self.editor = editor
        top = QHBoxLayout()
        top.setSpacing(theme.SPACE_2)
        top.addWidget(C.label(i18n.t("Screen {n}").format(n=number), level="SUPPORT", weight=700), 1)
        top.addWidget(C.button(i18n.t("Up"), "tertiary", small=True, on_click=lambda: self.moved.emit(self, -1)))
        top.addWidget(C.button(i18n.t("Down"), "tertiary", small=True, on_click=lambda: self.moved.emit(self, 1)))
        self.remove_btn = C.button(i18n.t("Remove screen"), "tertiary", small=True, on_click=lambda: self.removed.emit(self))
        top.addWidget(self.remove_btn)
        self.col.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.title = _line(screen.get("title") or "", i18n.t("Tell us about you"))
        self.title.setAccessibleName(i18n.t("Screen title"))
        self.title.setMaxLength(60)
        self.button = _line(screen.get("button") or "Continue", "")
        self.button.setAccessibleName(i18n.t("Button words"))
        self.button.setMaxLength(35)
        self.sid = screen.get("id") or ""
        row.addWidget(ui.field(i18n.t("Title"), self.title), 3, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Button"), self.button), 2, Qt.AlignTop)
        self.col.addLayout(row)
        self.text = QPlainTextEdit("\n\n".join(t["text"] for t in screen.get("texts") or []))
        self.text.setMinimumHeight(54)
        self.text.setMaximumHeight(90)
        self.text.setAccessibleName(i18n.t("Words on the screen"))
        self.col.addWidget(ui.field(i18n.t("Words above the fields"), self.text, i18n.t("Optional. Leave a blank line between paragraphs.")))
        self.fields = QVBoxLayout()
        self.fields.setSpacing(theme.SPACE_2)
        self.col.addLayout(self.fields)
        self.cards: list = []
        for f in screen.get("fields") or []:
            self.add_field_card(f, mapping.get(f.get("name") or "", ""))
        add_row = QHBoxLayout()
        self.add_btn = C.button(i18n.t("Add a field"), "secondary", icon_name="plus", on_click=self._menu)
        add_row.addWidget(self.add_btn)
        add_row.addStretch(1)
        self.col.addLayout(add_row)

    def add_field_card(self, field: dict, mapping: str = "") -> FieldCard:
        card = FieldCard(field, mapping, self.editor)
        card.removed.connect(self._remove_field)
        card.moved.connect(self._move_field)
        self.fields.addWidget(card)
        self.cards.append(card)
        return card

    def _menu(self):
        menu = QMenu(self)
        for key, label in kind_choices():
            menu.addAction(label).triggered.connect(lambda _=False, k=key: self.add_kind(k))
        self.editor._pop_up(menu, self.add_btn)

    def add_kind(self, kind: str):
        taken = {c.name.text() for c in self.editor.all_field_cards()}
        label = {"opt_in": "I agree"}.get(kind, "")
        card = self.add_field_card({"kind": kind, "name": machine_name(label or kind, taken), "label": label, "required": True,
                                    "options": [{"id": "one", "title": "One"}, {"id": "two", "title": "Two"}] if kind in CHOICE else None})
        card.name_edited = False
        self.editor.changed.emit()

    def _remove_field(self, card):
        self.cards.remove(card)
        self.fields.removeWidget(card)
        ui.discard(card)
        self.editor.changed.emit()

    def _move_field(self, card, step: int):
        i = self.cards.index(card)
        j = i + step
        if 0 <= j < len(self.cards):
            self.cards[i], self.cards[j] = self.cards[j], self.cards[i]
            self.fields.removeWidget(card)
            self.fields.insertWidget(j, card)

    def read(self) -> tuple:
        """-> (screen dict, {field name: mapping target})"""
        fields, mapping = [], {}
        for c in self.cards:
            f, target = c.read()
            fields.append(f)
            if target:
                mapping[f["name"]] = target
        texts = [{"style": "body", "text": t.strip()} for t in re.split(r"\n\s*\n", self.text.toPlainText()) if t.strip()]
        return {"id": self.sid, "title": self.title.text().strip(), "texts": texts, "button": self.button.text().strip() or "Continue", "fields": fields}, mapping


class HoursCard(_Card):
    """Opening days and hours for a form that offers live times."""

    def __init__(self, availability: dict):
        super().__init__()
        a = availability or {"weekdays": [0, 1, 2, 3, 4, 5], "start": "10:00", "end": "17:00", "slot_minutes": 60, "capacity": 1, "min_notice_hours": 2, "window_days": 21,
                             "tz": "Asia/Kolkata", "date_field": "date", "slot_field": "slot"}
        self.a = dict(a)
        self.col.addWidget(C.label(i18n.t("Opening days and hours"), level="SUPPORT", weight=700))
        self.col.addWidget(C.label(i18n.t("The customer picks a day, then one of the times still free. A time that is taken is never offered again."), level="META", colour=theme.NEUTRAL[600], wrap=True))
        days = QHBoxLayout()
        days.setSpacing(theme.SPACE_2)
        self.days = []
        for i, name in zip(WEEKDAYS, weekday_names()):
            box = QCheckBox(name)
            box.setChecked(i in a.get("weekdays", []))
            self.days.append(box)
            days.addWidget(box)
        days.addStretch(1)
        self.col.addLayout(days)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.start = _line(a["start"])
        self.start.setAccessibleName(i18n.t("Opens"))
        self.end = _line(a["end"])
        self.end.setAccessibleName(i18n.t("Closes"))
        self.slot = QSpinBox()
        self.slot.setRange(10, 480)
        self.slot.setSuffix(i18n.t(" min"))
        self.slot.setValue(int(a["slot_minutes"]))
        self.slot.setMinimumHeight(36)
        self.slot.setAccessibleName(i18n.t("Length of a visit"))
        self.capacity = QSpinBox()
        self.capacity.setRange(1, 100)
        self.capacity.setValue(int(a["capacity"]))
        self.capacity.setMinimumHeight(36)
        self.capacity.setAccessibleName(i18n.t("People per time"))
        for label, w in ((i18n.t("Opens"), self.start), (i18n.t("Closes"), self.end), (i18n.t("Each visit"), self.slot), (i18n.t("People per time"), self.capacity)):
            row.addWidget(ui.field(label, w), 1, Qt.AlignTop)
        self.col.addLayout(row)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.notice = QSpinBox()
        self.notice.setRange(0, 720)
        self.notice.setSuffix(i18n.t(" hours"))
        self.notice.setValue(int(a["min_notice_hours"]))
        self.notice.setMinimumHeight(36)
        self.notice.setAccessibleName(i18n.t("Notice needed"))
        self.window = QSpinBox()
        self.window.setRange(1, 120)
        self.window.setSuffix(i18n.t(" days"))
        self.window.setValue(int(a["window_days"]))
        self.window.setMinimumHeight(36)
        self.window.setAccessibleName(i18n.t("How far ahead"))
        self.tz = _line(a.get("tz") or "Asia/Kolkata")
        self.tz.setAccessibleName(i18n.t("Time zone"))
        row.addWidget(ui.field(i18n.t("Notice needed"), self.notice), 1, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Booking opens up to"), self.window), 1, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Time zone"), self.tz), 1, Qt.AlignTop)
        self.col.addLayout(row)

    def read(self, date_field: str, slot_field: str) -> dict:
        return {"weekdays": [i for i, box in zip(WEEKDAYS, self.days) if box.isChecked()], "start": self.start.text().strip(), "end": self.end.text().strip(), "slot_minutes": self.slot.value(),
                "capacity": self.capacity.value(), "min_notice_hours": self.notice.value(), "window_days": self.window.value(), "tz": self.tz.text().strip() or "Asia/Kolkata",
                "date_field": date_field, "slot_field": slot_field}


class FormEditor(QWidget):
    changed = Signal()
    saved = Signal(dict)
    closed = Signal()

    def __init__(self, form: dict, parent=None):
        super().__init__(parent)
        self.form = form
        self.cards: list = []
        self.hours: HoursCard = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(theme.SPACE_3)
        bar = QHBoxLayout()
        bar.setSpacing(theme.SPACE_2)
        self.back_btn = C.button(i18n.t("Back to forms"), "tertiary", on_click=self.closed.emit)
        bar.addWidget(self.back_btn)
        self.status = C.Pill("", "quiet")
        bar.addWidget(self.status)
        bar.addStretch(1)
        self.check_btn = C.button(i18n.t("Check"), "secondary", on_click=self.check)
        bar.addWidget(self.check_btn)
        self.preview_btn = C.button(i18n.t("See the code"), "tertiary", on_click=self.preview)
        bar.addWidget(self.preview_btn)
        self.save_btn = C.button(i18n.t("Save"), "secondary", on_click=lambda: self.save())
        bar.addWidget(self.save_btn)
        self.publish_btn = C.button(i18n.t("Save and publish"), "primary", on_click=self.publish)
        bar.addWidget(self.publish_btn)
        root.addLayout(bar)
        self.note = ui.note()
        root.addWidget(self.note)
        self.problems = QVBoxLayout()
        self.problems.setSpacing(2)
        root.addLayout(self.problems)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        host = QWidget()
        ui.see_through(host)
        self.col = QVBoxLayout(host)
        self.col.setContentsMargins(0, 0, theme.SPACE_2, 0)
        self.col.setSpacing(theme.SPACE_3)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        about = _Card()
        about.col.addWidget(C.label(i18n.t("About this form"), level="SUPPORT", weight=700))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.name = _line(form.get("name") or "", i18n.t("Walls enquiry"))
        self.name.setAccessibleName(i18n.t("Form name"))
        self.category = QComboBox()
        self.category.setMinimumHeight(36)
        self.category.setAccessibleName(i18n.t("What it is for"))
        for key, label in category_choices():
            self.category.addItem(label, key)
        cats = form.get("categories") or ["LEAD_GENERATION"]
        self.category.setCurrentIndex(max(self.category.findData(cats[0]), 0))
        row.addWidget(ui.field(i18n.t("Name"), self.name, i18n.t("Only you see this.")), 3, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("What it is for"), self.category, i18n.t("Meta asks.")), 2, Qt.AlignTop)
        about.col.addLayout(row)
        self.live = QCheckBox(i18n.t("Live form — Prism answers while the customer fills it in (free times, no double bookings)"))
        self.live.setChecked(bool(form.get("endpoint")))
        self.live.toggled.connect(lambda _v: self._live_changed())
        about.col.addWidget(self.live)
        self.key_line = C.label("", level="META", colour=theme.NEUTRAL[600], wrap=True)
        about.col.addWidget(self.key_line)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.tag = _line(form.get("tag_on_submit") or "", i18n.t("walls-enquiry"))
        self.tag.setAccessibleName(i18n.t("Tag when filled in"))
        self.thanks = _line((form.get("settings") or {}).get("thank_you") or "", i18n.t("Thank you! We will be in touch."))
        self.thanks.setAccessibleName(i18n.t("Thank-you words"))
        row.addWidget(ui.field(i18n.t("Tag the contact"), self.tag, i18n.t("Added when they finish.")), 2, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Thank-you words"), self.thanks, i18n.t("Sent in the chat after they finish.")), 3, Qt.AlignTop)
        about.col.addLayout(row)
        self.col.addWidget(about)

        self.screens_col = QVBoxLayout()
        self.screens_col.setSpacing(theme.SPACE_3)
        self.col.addLayout(self.screens_col)
        add = QHBoxLayout()
        self.add_screen_btn = C.button(i18n.t("Add a screen"), "secondary", icon_name="plus", on_click=self.add_screen)
        add.addWidget(self.add_screen_btn)
        add.addStretch(1)
        self.col.addLayout(add)
        self.hours_holder = QVBoxLayout()
        self.col.addLayout(self.hours_holder)
        self.col.addStretch(1)
        self.render()

    def say(self, message: str, error: bool = False):
        self.note.set(message, "error" if error else "ok")

    def _pop_up(self, menu: QMenu, below: QWidget):
        """Show a menu under a button. A method of its own so a test can read the menu without opening it."""
        menu.exec(below.mapToGlobal(below.rect().bottomLeft()))

    def all_field_cards(self) -> list:
        return [c for sc in self.cards for c in sc.cards]

    # ── drawing the form ─────────────────────────────────────────────────────
    def render(self):
        ui.clear(self.screens_col)
        self.cards = []
        mapping = self.form.get("mapping") or {}
        for n, s in enumerate(self.form.get("screens") or [], start=1):
            card = ScreenCard(s, n, mapping, self)
            card.removed.connect(self._remove_screen)
            card.moved.connect(self._move_screen)
            self.screens_col.addWidget(card)
            self.cards.append(card)
        self._status()
        self._live_changed()

    def _status(self):
        words = {"draft": i18n.t("Not published"), "published": i18n.t("Published"), "deprecated": i18n.t("Retired"), "throttled": i18n.t("Slowed by Meta"), "blocked": i18n.t("Blocked by Meta")}
        self.status.setText(words.get(self.form.get("status"), self.form.get("status") or ""))
        self.status.set_tone({"published": "ok", "draft": "quiet", "deprecated": "quiet", "throttled": "warn", "blocked": "err"}.get(self.form.get("status"), "quiet"))
        self.publish_btn.setText(i18n.t("Save and publish") if self.form.get("status") != "published" else i18n.t("Save and publish a new version"))
        self.show_problems(self.form.get("problems") or [])

    def _live_changed(self):
        live = self.live.isChecked()
        slots = live and any(f.get("live") == "slots" for s in self.form.get("screens") or [] for f in s["fields"])
        ui.clear(self.hours_holder)
        self.hours = None
        if slots:
            a = (self.form.get("settings") or {}).get("availability")
            self.hours = HoursCard(a)
            self.hours_holder.addWidget(self.hours)
        self.key_line.setVisible(live)
        if live:
            self.key_line.setText(i18n.t("A live form needs a key that lets Meta send Prism the customer's choices safely. Prism makes it and sends it to Meta when you publish."))

    def show_problems(self, problems: list):
        ui.clear(self.problems)
        for p in problems[:8]:
            self.problems.addWidget(C.label("•  %s — %s" % (p.get("where") or "", p.get("message") or ""), level="META", colour=theme.ERR_INK, wrap=True))
        if len(problems) > 8:
            self.problems.addWidget(C.label(i18n.t("…and {n} more.").format(n=len(problems) - 8), level="META", colour=theme.ERR_INK))

    # ── structure ────────────────────────────────────────────────────────────
    def collect(self) -> dict:
        screens, mapping = [], {}
        for card in self.cards:
            s, m = card.read()
            screens.append(s)
            mapping.update(m)
        date_field = next((f["name"] for s in screens for f in s["fields"] if f.get("live") == "date"), "date")
        slot_field = next((f["name"] for s in screens for f in s["fields"] if f.get("live") == "slots"), "slot")
        settings = {"thank_you": self.thanks.text().strip()}
        if self.hours is not None:
            settings["availability"] = self.hours.read(date_field, slot_field)
        elif (self.form.get("settings") or {}).get("availability") and self.live.isChecked():
            settings["availability"] = self.form["settings"]["availability"]
        return {"name": self.name.text().strip(), "categories": [self.category.currentData()], "endpoint": self.live.isChecked(), "tag_on_submit": self.tag.text().strip(),
                "mapping": mapping, "settings": settings, "screens": screens}

    def _sync_model(self):
        self.form.update(self.collect())

    def _unique_screen_id(self) -> str:
        taken = {c.sid for c in self.cards}
        n = 1
        while "SCREEN_%s" % "ABCDEFGHIJ"[n - 1] in taken:
            n += 1
        return "SCREEN_%s" % "ABCDEFGHIJ"[n - 1]

    def add_screen(self):
        self._sync_model()
        self.form["screens"].append({"id": self._unique_screen_id(), "title": "", "texts": [], "button": "Continue", "fields": []})
        self.render()
        self.changed.emit()

    def _remove_screen(self, card):
        if len(self.cards) <= 1:
            self.say(i18n.t("A form needs at least one screen."), error=True)
            return
        self._sync_model()
        self.form["screens"].pop(self.cards.index(card))
        self.render()
        self.changed.emit()

    def _move_screen(self, card, step: int):
        self._sync_model()
        i = self.cards.index(card)
        j = i + step
        if 0 <= j < len(self.cards):
            screens = self.form["screens"]
            screens[i], screens[j] = screens[j], screens[i]
            self.render()
            self.changed.emit()

    # ── talking to the server ────────────────────────────────────────────────
    def check(self):
        self._sync_model()
        d = self.collect()
        d["form_id"] = self.form["id"]
        ui.call(self, "forms/check", d, done=lambda r: self._checked(r["problems"]))

    def _checked(self, problems: list):
        self.show_problems(problems)
        self.say(i18n.t("Nothing wrong. It is ready to publish.") if not problems else i18n.t("{n} things to fix before it can be published.").format(n=len(problems)), error=bool(problems))

    def save(self, then=None):
        self._sync_model()
        d = self.collect()
        d["form_id"] = self.form["id"]
        self.save_btn.setEnabled(False)
        ui.call(self, "forms/update", d, done=lambda r: self._saved(r["form"], then), failed=self._failed)

    def _saved(self, form: dict, then):
        self.save_btn.setEnabled(True)
        self.form = form
        self.saved.emit(form)
        if then is not None:
            then()
        else:
            self.say(i18n.t("Saved."))
            self.show_problems(form.get("problems_now") or [])

    def _failed(self, message: str, detail: dict):
        self.save_btn.setEnabled(True)
        self.publish_btn.setEnabled(True)
        self.say(message, error=True)
        if detail.get("problems"):
            self.show_problems(detail["problems"])

    def publish(self):
        self.publish_btn.setEnabled(False)
        self.save(then=self._publish_now)

    def _publish_now(self):
        ui.call(self, "forms/publish", {"form_id": self.form["id"]}, done=self._published, failed=self._failed)

    def _published(self, reply: dict):
        self.publish_btn.setEnabled(True)
        self.form = reply["form"]
        self.saved.emit(self.form)
        self._status()
        self.say(i18n.t("Published. You can now send it in a chat."))

    def preview(self):
        ui.call(self, "forms/preview", {"form_id": self.form["id"]}, done=self._previewed)

    def _previewed(self, reply: dict):
        import json
        from addons.whatsapp.forms_page import CodeDialog
        CodeDialog(json.dumps(reply["flow_json"], indent=2), self).exec()
