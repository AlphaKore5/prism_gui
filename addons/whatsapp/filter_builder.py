"""Build an audience filter on screen: "Tags has any of vip, builder  AND  Last wrote in the last 30 days".

One editor, used by Contacts (filter the table), Campaigns (who gets it) and the Inbox (find chats). It
speaks prism-wa's segment filter language through `filter_model`, shows how many people match as you
build, and can save the result as a named segment.

    FilterEditor   the rows; `filter()` is the language, `changed` fires on every edit
    FilterDialog   the editor in a window with a live count and Save-as-segment
    SegmentsDialog the saved segments: apply, rename-by-resave, delete
"""
from __future__ import annotations

from PySide6.QtCore import QDate, QTimer, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDateEdit, QFrame, QHBoxLayout, QInputDialog, QLineEdit, QSpinBox, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import filter_model as FM
from addons.whatsapp import ui
from dialogs.base import PrismDialog
from widgets import controls as C


def _combo(items: list, current=None) -> QComboBox:
    box = QComboBox()
    box.setMinimumHeight(34)
    for value, label in items:
        box.addItem(label, value)
    if current is not None:
        i = box.findData(current)
        if i >= 0:
            box.setCurrentIndex(i)
    return box


class _Row(QFrame):
    changed = Signal()
    removed = Signal(object)

    def __init__(self, defs: dict, leaf: dict | None = None, tag_names=(), parent=None):
        super().__init__(parent)
        self.defs = defs
        self.tag_names = list(tag_names)
        self._fields = FM.fields(defs)
        self._value = QWidget()
        self._value_lay = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.SPACE_2)
        self.field = _combo([(f["key"], f["label"]) for f in self._fields], (leaf or {}).get("field", "tags"))
        self.field.setMinimumWidth(150)
        self.field.setAccessibleName(i18n.t("Filter on"))
        self.op = QComboBox()
        self.op.setMinimumHeight(34)
        self.op.setMinimumWidth(150)
        self.op.setAccessibleName(i18n.t("How it compares"))
        self.slot = QHBoxLayout()
        self.slot.setContentsMargins(0, 0, 0, 0)
        self.slot.setSpacing(theme.SPACE_2)
        self.edit_a = self.edit_b = None
        self.warn = C.label("", level="META", colour=theme.ERR_INK)
        lay.addWidget(self.field)
        lay.addWidget(self.op)
        lay.addLayout(self.slot, stretch=1)
        x = C.icon_button("x", i18n.t("Remove this condition"), colour=theme.NEUTRAL[600])
        x.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(x)
        self._leaf = leaf or {}
        self._fill_ops(self._leaf.get("op"))
        self._build_value(self._leaf.get("value"))
        self.field.currentIndexChanged.connect(self._field_changed)
        self.op.currentIndexChanged.connect(self._op_changed)

    # ── pieces ───────────────────────────────────────────────────────────────
    def meta(self) -> dict:
        return next(f for f in self._fields if f["key"] == self.field.currentData())

    def _fill_ops(self, current=None):
        self.op.blockSignals(True)
        self.op.clear()
        for op, label in self.meta()["ops"]:
            self.op.addItem(label, op)
        if current is not None:
            i = self.op.findData(current)
            if i >= 0:
                self.op.setCurrentIndex(i)
        self.op.blockSignals(False)

    def _clear_slot(self):
        while self.slot.count():
            item = self.slot.takeAt(0)
            if item.widget() is not None:
                ui.discard(item.widget())
        self.edit_a = self.edit_b = None

    def _line(self, text: str = "", hint: str = "") -> QLineEdit:
        e = QLineEdit(text)
        e.setMinimumHeight(34)
        e.setPlaceholderText(hint)
        e.textChanged.connect(lambda _t: self.changed.emit())
        return e

    def _build_value(self, value=None):
        self._clear_slot()
        meta, op = self.meta(), self.op.currentData()
        kind = meta["kind"]
        if not FM.needs_value(op):
            self.slot.addStretch(1)
            return
        if kind in ("text",):
            self.edit_a = self._line("" if value is None else str(value), i18n.t("a word or number"))
        elif kind == "words":
            text = ", ".join(value) if isinstance(value, list) else ("" if value is None else str(value))
            self.edit_a = self._line(text, i18n.t("separate several with commas, e.g. vip, builder"))
            if meta["key"] == "tags" and self.tag_names:
                from PySide6.QtWidgets import QCompleter
                comp = QCompleter(self.tag_names, self.edit_a)
                comp.setCaseSensitivity(Qt.CaseInsensitive)
                self.edit_a.setCompleter(comp)
        elif kind in ("flag", "boolflag"):
            self.edit_a = _combo([(True, i18n.t("yes")), (False, i18n.t("no"))],
                                 True if value is None else (value is True or str(value).lower() in ("yes", "true", "1")))
            self.edit_a.currentIndexChanged.connect(lambda _i: self.changed.emit())
        elif kind == "state":
            self.edit_a = _combo(FM.states(), value)
            self.edit_a.currentIndexChanged.connect(lambda _i: self.changed.emit())
        elif kind == "choice":
            self.edit_a = _combo([(o, str(o)) for o in meta.get("options") or []], value)
            self.edit_a.currentIndexChanged.connect(lambda _i: self.changed.emit())
        elif kind == "time":
            if op in ("within_days", "older_than_days"):
                self.edit_a = QSpinBox()
                self.edit_a.setRange(0, 36500)
                self.edit_a.setValue(int(value) if str(value or "").isdigit() else 30)
                self.edit_a.setMinimumHeight(34)
                self.edit_a.valueChanged.connect(lambda _v: self.changed.emit())
                self.slot.addWidget(self.edit_a)
                self.slot.addWidget(C.label(i18n.t("days"), level="SUPPORT", colour=theme.NEUTRAL[600]))
                self.slot.addStretch(1)
                return
            self.edit_a = self._date(value)
        elif kind == "date":
            if op == "between":
                lo, hi = (value if isinstance(value, list) and len(value) == 2 else (None, None))
                self.edit_a, self.edit_b = self._date(lo), self._date(hi)
                self.slot.addWidget(self.edit_a)
                self.slot.addWidget(C.label(i18n.t("and"), level="SUPPORT", colour=theme.NEUTRAL[600]))
                self.slot.addWidget(self.edit_b)
                self.slot.addStretch(1)
                return
            self.edit_a = self._date(value)
        elif kind == "number":
            if op == "between":
                lo, hi = (value if isinstance(value, list) and len(value) == 2 else ("", ""))
                self.edit_a, self.edit_b = self._line(str(lo)), self._line(str(hi))
                self.slot.addWidget(self.edit_a)
                self.slot.addWidget(C.label(i18n.t("and"), level="SUPPORT", colour=theme.NEUTRAL[600]))
                self.slot.addWidget(self.edit_b)
                self.slot.addStretch(1)
                return
            self.edit_a = self._line("" if value is None else str(value), i18n.t("a number"))
        self.slot.addWidget(self.edit_a, stretch=1)

    def _date(self, value) -> QDateEdit:
        d = QDateEdit()
        d.setCalendarPopup(True)
        d.setDisplayFormat("dd MMM yyyy")
        d.setMinimumHeight(34)
        parsed = QDate.fromString(str(value or "")[:10], "yyyy-MM-dd")
        d.setDate(parsed if parsed.isValid() else QDate.currentDate())
        d.dateChanged.connect(lambda _d: self.changed.emit())
        return d

    def _field_changed(self, _i):
        self._fill_ops()
        self._build_value(None)
        self.changed.emit()

    def _op_changed(self, _i):
        self._build_value(None)
        self.changed.emit()

    # ── the leaf ─────────────────────────────────────────────────────────────
    def leaf(self) -> dict:
        meta, op = self.meta(), self.op.currentData()
        out = {"field": meta["key"], "op": op}
        if not FM.needs_value(op):
            return out
        kind, a, b = meta["kind"], self.edit_a, self.edit_b
        if kind == "words":
            out["value"] = [w.strip() for w in a.text().split(",") if w.strip()]
        elif kind in ("flag",):
            out["value"] = bool(a.currentData())
        elif kind == "boolflag":
            out["value"] = "yes" if a.currentData() else "no"
        elif kind in ("state", "choice"):
            out["value"] = a.currentData()
        elif kind == "time":
            out["value"] = a.value() if op in ("within_days", "older_than_days") else a.date().toString("yyyy-MM-dd")
        elif kind == "date":
            out["value"] = [a.date().toString("yyyy-MM-dd"), b.date().toString("yyyy-MM-dd")] if op == "between" else a.date().toString("yyyy-MM-dd")
        elif kind == "number":
            out["value"] = [a.text().strip(), b.text().strip()] if op == "between" else a.text().strip()
        else:
            out["value"] = a.text().strip()
        return out


class FilterEditor(QWidget):
    changed = Signal()

    def __init__(self, defs: dict = None, tag_names=(), parent=None):
        super().__init__(parent)
        self.defs = defs or {}
        self.tag_names = list(tag_names)
        self._rows: list = []
        self.match = "all"
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_3)
        head = QHBoxLayout()
        head.addWidget(C.label(i18n.t("Show people who match"), level="SUPPORT", colour=theme.NEUTRAL[600]))
        self.chips = C.FilterChips([("all", i18n.t("all of these")), ("any", i18n.t("any of these"))], current="all")
        self.chips.changed.connect(self._match_changed)
        self.chips.setMinimumWidth(260)                                  # or the two chips wrap onto separate lines
        head.addWidget(self.chips)
        head.addStretch(1)
        col.addLayout(head)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(theme.SPACE_2)
        col.addLayout(self.rows_box)
        self.add_btn = C.button(i18n.t("Add a condition"), "secondary", icon_name="plus", small=True, on_click=lambda: self.add_row())
        col.addWidget(self.add_btn, alignment=Qt.AlignLeft)
        self.note = C.label("", level="META", colour=theme.WARN_INK, wrap=True)
        self.note.hide()
        col.addWidget(self.note)
        self._custom = None

    # ── rows ─────────────────────────────────────────────────────────────────
    def add_row(self, leaf: dict | None = None, silent: bool = False) -> _Row:
        row = _Row(self.defs, leaf or {"field": "tags", "op": "has_any", "value": []}, self.tag_names)
        row.changed.connect(self.changed)
        row.removed.connect(self._remove)
        self._rows.append(row)
        self.rows_box.addWidget(row)
        if not silent:
            self.changed.emit()
        return row

    def _remove(self, row):
        self._rows.remove(row)
        ui.discard(row)
        self.changed.emit()

    def _match_changed(self, value: str):
        self.match = value
        self.changed.emit()

    def clear(self):
        for row in list(self._rows):
            ui.discard(row)
        self._rows.clear()
        self.changed.emit()

    # ── in and out ───────────────────────────────────────────────────────────
    def set_filter(self, flt) -> None:
        for row in list(self._rows):
            ui.discard(row)
        self._rows.clear()
        parsed = FM.rows_of(flt)
        self._custom = None
        self.note.hide()
        if parsed is None:
            self._custom = flt                                       # nested beyond what the editor draws: kept as it is
            self.note.setText(i18n.t("This filter is more complex than this editor can show. It stays as it is until you add or clear something."))
            self.note.show()
            self.changed.emit()
            return
        match, leaves = parsed
        self.match = match
        self.chips.set_current(match)
        for leaf in leaves:
            self.add_row(leaf, silent=True)
        self.changed.emit()

    def leaves(self) -> list:
        return [r.leaf() for r in self._rows]

    def complete(self) -> bool:
        return all(FM.complete(l, self.defs) for l in self.leaves())

    def filter(self) -> dict:
        if self._custom is not None and not self._rows:
            return self._custom
        return FM.build(self.match, [l for l in self.leaves() if FM.complete(l, self.defs)])


class FilterDialog(PrismDialog):
    """The editor in a window, with how many people match as you build, and Save as segment."""

    def __init__(self, flt=None, defs: dict = None, tag_names=(), parent=None, opted_in_only: bool = False):
        super().__init__(i18n.t("Filter people"), i18n.t("Narrow the list to the people you mean. Nothing here changes anyone."),
                         icon="sliders", parent=parent, scrollable=True)
        self.defs = defs or {}
        self._opted_in_only = opted_in_only
        self.editor = FilterEditor(defs, tag_names)
        self.body.addWidget(self.editor)
        self.count = C.label("", level="SUPPORT", colour=theme.NEUTRAL[600])
        self.body.addWidget(self.count)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(350)
        self._debounce.timeout.connect(self._ask_count)
        self.editor.changed.connect(self._debounce.start)
        self.apply_btn = self.button(i18n.t("Apply"), "primary", on_click=self.accept)
        self.clear_btn = self.button(i18n.t("Clear"), on_click=self._clear)
        self.save_btn = self.button(i18n.t("Save as segment"), on_click=self._save)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.add_secondary(self.clear_btn)
        self.footer.add_secondary(self.save_btn)
        self.footer.set_primary(self.apply_btn)
        self.resize(760, 520)
        self.editor.set_filter(flt)
        if not self.editor._rows and self.editor._custom is None:
            self.editor.add_row(silent=True)
        self._ask_count()

    def filter(self) -> dict:
        return self.editor.filter()

    def _clear(self):
        self.editor.set_filter(None)
        self.editor.add_row(silent=True)
        self._ask_count()

    def _ask_count(self):
        if not self.editor.complete():
            self.count.setText(i18n.t("Finish the condition that is still empty to see who matches."))
            return
        self.count.setText(i18n.t("Counting…"))
        ui.call(self, "segments/count", {"filter": self.editor.filter(), "opted_in_only": self._opted_in_only}, done=self._counted,
                failed=lambda m, _d: (self.count.setText(""), self.error.error(m)))

    def _counted(self, reply: dict):
        self.error.clear_note()
        n = int(reply.get("count") or 0)
        self.count.setText(i18n.t("{n} people match.").format(n=n) if n != 1 else i18n.t("1 person matches."))

    def _save(self):
        if not self.editor.complete() or not self.editor.leaves():
            self.error.error(i18n.t("Build a filter first."))
            return
        name, ok = QInputDialog.getText(self, i18n.t("Save as segment"), i18n.t("Name this segment:"))
        name = (name or "").strip()
        if not ok or not name:
            return
        ui.call(self, "segments/save", {"name": name, "filter": self.editor.filter()},
                done=lambda _r: self.error.ok(i18n.t("Saved the segment “{n}”.").format(n=name)),
                failed=lambda m, _d: self.error.error(m))


class SegmentsDialog(PrismDialog):
    """Saved segments: pick one to use, or delete it."""

    def __init__(self, defs: dict = None, parent=None):
        super().__init__(i18n.t("Saved segments"), i18n.t("Groups of people you have saved. A segment follows your contacts: "
                                                         "someone who starts to match is in it from then on."),
                         icon="users", parent=parent, scrollable=True)
        self.defs = defs or {}
        self.chosen = None
        self.list = QVBoxLayout()
        self.list.setSpacing(theme.SPACE_2)
        self.body.addLayout(self.list)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.set_primary(self.button(i18n.t("Close"), "primary", on_click=self.reject))
        self.resize(620, 480)
        self.reload()

    def reload(self):
        ui.clear(self.list)
        self.list.addWidget(C.label(i18n.t("Loading…"), level="SUPPORT", colour=theme.NEUTRAL[600]))
        ui.call(self, "segments/list", {}, done=self._loaded, failed=lambda m, _d: (ui.clear(self.list), self.error.error(m)))

    def _loaded(self, reply: dict):
        ui.clear(self.list)
        items = reply.get("segments") or []
        if not items:
            self.list.addWidget(C.label(i18n.t("No segments yet. Build a filter and choose Save as segment."), level="SUPPORT",
                                        colour=theme.NEUTRAL[600], wrap=True))
            return
        for seg in items:
            card, col = ui.card("", "")
            row = QHBoxLayout()
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(C.label(seg.get("name") or "", level="SUPPORT", weight=700))
            text.addWidget(C.label(FM.describe(seg.get("filter"), self.defs) or i18n.t("Everyone"), level="META", colour=theme.NEUTRAL[600], wrap=True))
            row.addLayout(text, stretch=1)
            row.addWidget(C.button(i18n.t("Use"), "secondary", small=True, on_click=lambda _=False, s=seg: self._use(s)))
            row.addWidget(C.button(i18n.t("Delete"), "tertiary", small=True, on_click=lambda _=False, s=seg: self._delete(s)))
            col.addLayout(row)
            self.list.addWidget(card)

    def _use(self, seg: dict):
        self.chosen = seg
        self.accept()

    def _delete(self, seg: dict):
        if not ui.confirm(self, i18n.t("Delete segment?"), i18n.t("Delete “{n}”? Contacts and their tags are not affected.").format(n=seg.get("name"))):
            return
        ui.call(self, "segments/delete", {"segment_id": seg.get("id")}, done=lambda _r: self.reload(), failed=lambda m, _d: self.error.error(m))
