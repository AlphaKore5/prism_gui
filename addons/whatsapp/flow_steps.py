"""One step of a flow, as a card you fill in.

Each kind of step shows only the fields it has. Edits go straight into the step's dict (the editor above owns the dict and
saves it), and anything that changes the SHAPE of the flow — a step's name, which step comes next — is announced so the other
cards can refresh the choices they offer.

Where a step "goes next" is always chosen from the steps that exist, or "End the flow": there is no way to type a step that is
not there, so a flow cannot be saved leading nowhere by a slip of the keyboard.
"""
from __future__ import annotations

import re
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLineEdit, QSpinBox, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import flow_model as M
from addons.whatsapp import ui
from addons.whatsapp.campaigns_page import _sources, variable_spec
from addons.whatsapp.flow_fields import TargetCombo, line, text_edit
from addons.whatsapp.flow_rules import RuleEditor
from addons.whatsapp.flow_steps_more import MoreSteps
from addons.whatsapp.template_editor import variables_of
from widgets import controls as C

VALIDATORS = (("text", "Anything"), ("number", "A number"), ("email", "An email address"), ("phone", "A phone number"),
              ("date", "A date"), ("options", "One of my options"), ("regex", "A pattern I write"))


_text_edit = text_edit
_line = line


class _Rows(QWidget):
    """A list of small rows (buttons, list choices, conditions) inside one step."""
    structure = Signal()
    edited = Signal()

    def __init__(self, card: "StepCard", node: dict, key: str, maximum: int, add_text: str, with_description: bool = False, kind: str = "choice"):
        super().__init__()
        self.card, self.node, self.key, self.max, self.with_description, self.kind = card, node, key, maximum, with_description, kind
        self.max = maximum if callable(maximum) else (lambda m=maximum: m)
        self.col = QVBoxLayout(self)
        self.col.setContentsMargins(0, 0, 0, 0)
        self.col.setSpacing(theme.SPACE_1)
        self.rows_col = QVBoxLayout()
        self.rows_col.setSpacing(theme.SPACE_1)
        self.col.addLayout(self.rows_col)
        self.add_btn = C.button(add_text, "tertiary", icon_name="plus", on_click=self._add)
        add = QHBoxLayout()
        add.addWidget(self.add_btn)
        add.addStretch(1)
        self.col.addLayout(add)
        self.combos: list = []
        self.render()

    def items(self) -> list:
        return self.node.setdefault(self.key, [])

    def render(self):
        ui.clear(self.rows_col)
        self.combos = []
        for i, item in enumerate(self.items()):
            row = QHBoxLayout()
            row.setSpacing(theme.SPACE_2)
            if self.kind == "rule":
                row.addWidget(C.label(i18n.t("then"), level="META", colour=theme.NEUTRAL[600]))
            else:
                title = _line(item.get("title", ""), lambda t, it=item: (it.__setitem__("title", t), self.edited.emit()),
                              i18n.t("What the customer sees"), i18n.t("Choice {n}").format(n=i + 1))
                title.setMaxLength(20 if self.key == "options" else 24)
                row.addWidget(title, 3)
                if self.with_description:
                    desc = _line(item.get("description", ""), lambda t, it=item: (it.__setitem__("description", t), self.edited.emit()), i18n.t("Small text under it (optional)"))
                    desc.setMaxLength(72)
                    row.addWidget(desc, 3)
            combo = TargetCombo()
            combo.chosen.connect(lambda v, it=item: (it.__setitem__("next", v), self.structure.emit()))
            self.combos.append((combo, item))
            row.addWidget(combo, 3 if self.kind != "rule" else 1)
            row.addWidget(C.icon_button("trash", i18n.t("Remove"), on_click=lambda _=False, it=item: self._remove(it), colour=theme.NEUTRAL[600]))
            box = QWidget()
            if self.kind == "rule":                                  # what to check on one line, where it leads on the next
                stack = QVBoxLayout(box)
                stack.setContentsMargins(0, 0, 0, theme.SPACE_1)
                stack.setSpacing(theme.SPACE_1)
                editor = RuleEditor(item)
                editor.edited.connect(self.edited.emit)
                stack.addWidget(editor)
                stack.addLayout(row)
            else:
                box.setLayout(row)
            self.rows_col.addWidget(box)
        self.add_btn.setVisible(len(self.items()) < self.max())
        self.refresh_targets()

    def refresh_targets(self):
        for combo, item in self.combos:
            combo.set_targets(self.card.ctx.labels(), item.get("next"), self.card.nid)

    def _add(self):
        items = self.items()
        if len(items) >= self.max():
            return
        if self.kind == "rule":
            items.append({"field": "message", "op": "contains", "value": "", "next": None})
        else:
            taken = {i.get("id") for i in items}
            items.append({"id": M.slug("choice", taken), "title": "", "next": None, **({"description": ""} if self.with_description else {})})
        self.render()
        self.structure.emit()

    def _remove(self, item: dict):
        items = self.items()
        if len(items) <= 1:
            return
        items.remove(item)
        self.render()
        self.structure.emit()


class StepCard(MoreSteps, QFrame):
    changed = Signal()                 # a field was edited: save soon
    shape = Signal()                   # the flow's shape changed: other cards refresh their choices
    renamed = Signal(str, str)
    removed = Signal(str)
    moved = Signal(str, int)
    make_entry = Signal(str)

    def __init__(self, nid: str, node: dict, ctx, parent=None):
        super().__init__(parent)
        self.nid, self.node, self.ctx = nid, node, ctx
        self.setObjectName("waStep")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._paint(False)
        self.targets: list = []             # [(combo, key)]
        self.rows: list = []
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 12, 14, 12)
        col.setSpacing(theme.SPACE_2)

        head = QHBoxLayout()
        head.setSpacing(theme.SPACE_2)
        head.addWidget(C.Pill(M.type_name(node.get("type")), "neutral"))
        self.id_edit = QLineEdit(nid)
        self.id_edit.setMaximumWidth(190)
        self.id_edit.setMinimumHeight(30)
        self.id_edit.setAccessibleName(i18n.t("Step name"))
        self.id_edit.setToolTip(i18n.t("The step's name — used to point other steps at it"))
        self.id_edit.editingFinished.connect(self._rename)
        head.addWidget(self.id_edit)
        self.entry_pill = C.Pill(i18n.t("Starts here"), "ok")
        head.addWidget(self.entry_pill)
        head.addStretch(1)
        self.entry_btn = C.button(i18n.t("Start here"), "tertiary", on_click=lambda: self.make_entry.emit(self.nid))
        head.addWidget(self.entry_btn)
        head.addWidget(C.icon_button("arrow-up", i18n.t("Move up"), on_click=lambda: self.moved.emit(self.nid, -1), colour=theme.NEUTRAL[600]))
        head.addWidget(C.icon_button("chevron-down", i18n.t("Move down"), on_click=lambda: self.moved.emit(self.nid, 1), colour=theme.NEUTRAL[600]))
        head.addWidget(C.icon_button("trash", i18n.t("Delete this step"), on_click=lambda: self.removed.emit(self.nid), colour=theme.ERR_INK))
        col.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(theme.SPACE_2)
        col.addLayout(self.body)
        getattr(self, "_build_" + node["type"], self._build_end)()

        self.issue_col = QVBoxLayout()
        self.issue_col.setSpacing(2)
        col.addLayout(self.issue_col)
        self.refresh_targets()

    # ── look ─────────────────────────────────────────────────────────────────
    def _paint(self, problem: bool):
        line = theme.ERR_LINE if problem else theme.HAIRLINE
        self.setStyleSheet(f"#waStep {{ background: rgba(255,255,255,0.6); border: 1px solid {line}; border-radius: {theme.R_CONTROL}px; }}")

    def set_issues(self, issues: list):
        ui.clear(self.issue_col)
        self._paint(any(i.get("severity") == "error" for i in issues))
        for i in issues:
            tone = theme.ERR_INK if i.get("severity") == "error" else theme.WARN_INK
            self.issue_col.addWidget(C.label("•  " + str(i.get("message", "")), level="META", colour=tone, wrap=True))

    def refresh_targets(self):
        labels = self.ctx.labels()
        for combo, key in self.targets:
            combo.set_targets(labels, self.node.get(key), self.nid)
        for r in self.rows:
            r.refresh_targets()
        is_entry = self.ctx.entry() == self.nid
        self.entry_pill.setVisible(is_entry)
        self.entry_btn.setVisible(not is_entry)

    def _rename(self):
        new = self.id_edit.text().strip()
        if new == self.nid:
            return
        if not M.ID_RE.match(new) or new in self.ctx.labels():
            self.id_edit.setText(self.nid)
            self.id_edit.setToolTip(i18n.t("A step's name uses letters, numbers and underscores, and no other step has it."))
            return
        old, self.nid = self.nid, new
        self.renamed.emit(old, new)

    # ── fields ───────────────────────────────────────────────────────────────
    def _field(self, label: str, widget, hint: str = ""):
        self.body.addWidget(ui.field(label, widget, hint))

    def _set(self, key: str):
        def fn(value, key=key):
            self.node[key] = value
            self.changed.emit()
        return fn

    def _next(self, key: str = "next", label: str = ""):
        combo = TargetCombo()
        combo.chosen.connect(lambda v, k=key: (self.node.__setitem__(k, v), self.shape.emit(), self.changed.emit()))
        self.targets.append((combo, key))
        self._field(label or i18n.t("Then"), combo)

    def _timeout(self, hint: str = ""):
        row = QHBoxLayout()
        spin = QSpinBox()
        spin.setRange(0, 7 * 24 * 60)
        spin.setSpecialValueText(i18n.t("Wait for ever"))
        spin.setSuffix(i18n.t(" min"))
        spin.setMinimumHeight(34)
        spin.setValue(int(self.node.get("timeout_minutes") or 0))
        spin.valueChanged.connect(lambda v: (self.node.__setitem__("timeout_minutes", v) if v else self.node.pop("timeout_minutes", None), self.changed.emit()))
        row.addWidget(spin)
        row.addStretch(1)
        self._field(i18n.t("If they don't answer in"), row)
        self._next("timeout_next", i18n.t("…then"))

    def _build_send_text(self):
        self._field(i18n.t("What to say"), _text_edit(self.node.get("text"), self._set("text"), 84, i18n.t("Hello {{first_name}}! …"), i18n.t("What to say")),
                    i18n.t("{{first_name}}, {{name}}, {{attr.City}} and {{var.x}} are filled in for each customer."))
        self._next()

    def _choices(self, key: str, maximum: int, add_text: str, with_description: bool):
        rows = _Rows(self, self.node, key, maximum, add_text, with_description)
        rows.structure.connect(lambda: (self.shape.emit(), self.changed.emit()))
        rows.edited.connect(self.changed.emit)
        self.rows.append(rows)
        self._field(i18n.t("Choices"), rows)

    def _build_buttons(self):
        self._field(i18n.t("The question"), _text_edit(self.node.get("text"), self._set("text"), 72, "", i18n.t("The question")))
        self._choices("options", 3, i18n.t("Add a button"), False)
        self._next("fallback_next", i18n.t("If they write something else"))
        self._timeout()

    def _build_list(self):
        self._field(i18n.t("The question"), _text_edit(self.node.get("text"), self._set("text"), 72, "", i18n.t("The question")))
        self._field(i18n.t("Button that opens the list"), _line(self.node.get("button_label"), self._set("button_label"), i18n.t("e.g. Choose one"), i18n.t("List button")))
        self.sections_toggle = QCheckBox(i18n.t("Group the choices under headings"))
        self.sections_toggle.setChecked(bool(self.node.get("sections")))
        self.sections_toggle.toggled.connect(self._sections_toggled)
        self.body.addWidget(self.sections_toggle)
        self.choices_holder = QVBoxLayout()
        self.choices_holder.setSpacing(theme.SPACE_2)
        self.body.addLayout(self.choices_holder)
        self.list_rows: list = []
        self._render_choices()
        self._next("fallback_next", i18n.t("If they write something else"))
        self._timeout()

    def _sections_toggled(self, on: bool):
        node = self.node
        if on and not node.get("sections"):
            node["sections"] = [{"title": i18n.t("Choices"), "rows": node.pop("rows", None) or []}]
        elif not on and node.get("sections"):
            node["rows"] = M.list_rows(node)[:10]
            node.pop("sections", None)
        self._render_choices()
        self.shape.emit()
        self.changed.emit()

    def _total_rows(self) -> int:
        return len(M.list_rows(self.node))

    def _render_choices(self):
        """The list's choices — one block, or one block under each heading. Ten in all, whichever way they are grouped."""
        ui.clear(self.choices_holder)
        for r in getattr(self, "list_rows", []):
            if r in self.rows:
                self.rows.remove(r)
        self.list_rows = []
        node = self.node

        def made(rows: "_Rows"):
            rows.structure.connect(lambda: (self._render_choices(), self.shape.emit(), self.changed.emit()))
            rows.edited.connect(self.changed.emit)
            self.rows.append(rows)
            self.list_rows.append(rows)
            return rows
        if not node.get("sections"):
            self.choices_holder.addWidget(ui.field(i18n.t("Choices"), made(_Rows(self, node, "rows", 10, i18n.t("Add a choice"), True))))
            self.refresh_targets()
            return
        for n, section in enumerate(node["sections"]):
            head = QHBoxLayout()
            head.setSpacing(theme.SPACE_2)
            title = _line(section.get("title", ""), lambda t, sec=section: (sec.__setitem__("title", t), self.changed.emit()), i18n.t("Heading, e.g. Services"),
                          i18n.t("Heading {n}").format(n=n + 1))
            title.setMaxLength(24)
            head.addWidget(title, 1)
            head.addWidget(C.icon_button("trash", i18n.t("Remove this heading and its choices"), colour=theme.NEUTRAL[600],
                                         on_click=lambda _=False, sec=section: self._remove_section(sec)))
            box = QWidget()
            box.setLayout(head)
            self.choices_holder.addWidget(box)
            room = lambda sec=section: 10 - (self._total_rows() - len(sec.get("rows") or []))                 # noqa: E731
            self.choices_holder.addWidget(made(_Rows(self, section, "rows", room, i18n.t("Add a choice"), True)))
        add = QHBoxLayout()
        self.add_section_btn = C.button(i18n.t("Add a heading"), "tertiary", icon_name="plus", on_click=self._add_section)
        add.addWidget(self.add_section_btn)
        add.addStretch(1)
        self.choices_holder.addLayout(add)
        self.add_section_btn.setVisible(len(node["sections"]) < 10 and self._total_rows() < 10)
        self.refresh_targets()

    def _add_section(self):
        if len(self.node["sections"]) >= 10 or self._total_rows() >= 10:
            return
        taken = {r.get("id") for r in M.list_rows(self.node)}
        self.node["sections"].append({"title": "", "rows": [{"id": M.slug("choice", taken), "title": "", "next": None, "description": ""}]})
        self._render_choices()
        self.shape.emit()
        self.changed.emit()

    def _remove_section(self, section: dict):
        if len(self.node["sections"]) <= 1:
            return
        self.node["sections"].remove(section)
        self._render_choices()
        self.shape.emit()
        self.changed.emit()

    def _build_ask(self):
        self._field(i18n.t("The question"), _text_edit(self.node.get("text"), self._set("text"), 72, "", i18n.t("The question")))
        row = QHBoxLayout()
        v = QComboBox()
        v.setMinimumHeight(34)
        for k, label in VALIDATORS:
            v.addItem(i18n.t(label), k)
        v.setCurrentIndex(max(v.findData(self.node.get("validator", "text")), 0))
        row.addWidget(v)
        row.addStretch(1)
        self._field(i18n.t("An answer is"), row)
        extra = QWidget()
        el = QVBoxLayout(extra)
        el.setContentsMargins(0, 0, 0, 0)
        pattern = _line(self.node.get("pattern", ""), self._set("pattern"), i18n.t("A pattern, e.g. ^[0-9]{6}$"), i18n.t("Pattern"))
        options = _text_edit("\n".join(str(o) for o in self.node.get("options") or []),
                             lambda t: (self.node.__setitem__("options", [x.strip() for x in t.splitlines() if x.strip()]), self.changed.emit()), 72,
                             i18n.t("One allowed answer per line"), i18n.t("Allowed answers"))
        el.addWidget(pattern)
        el.addWidget(options)
        self.body.addWidget(extra)

        def show(*_):
            kind = v.currentData()
            self.node["validator"] = kind
            pattern.setVisible(kind == "regex")
            options.setVisible(kind == "options")
            extra.setVisible(kind in ("regex", "options"))
            self.changed.emit()
        v.activated.connect(show)
        pattern.setVisible(v.currentData() == "regex")
        options.setVisible(v.currentData() == "options")
        extra.setVisible(v.currentData() in ("regex", "options"))
        # where the answer is kept
        save = self.node.get("save_as") or ""
        where, _, key = save.partition(":")
        srow = QHBoxLayout()
        sw = QComboBox()
        sw.setMinimumHeight(34)
        sw.addItem(i18n.t("Don't keep it"), "")
        sw.addItem(i18n.t("A detail on the contact"), "attr")
        sw.addItem(i18n.t("A note for this flow only"), "var")
        sw.setCurrentIndex(max(sw.findData(where), 0))
        sk = _line(key, lambda t: None, i18n.t("Name, e.g. City"), i18n.t("Name to keep it under"))
        srow.addWidget(sw, 2)
        srow.addWidget(sk, 2)

        def keep(*_):
            w = sw.currentData()
            sk.setVisible(bool(w))
            if w and re.match(r"^[A-Za-z][A-Za-z0-9_]{0,39}$", sk.text().strip()):
                self.node["save_as"] = "%s:%s" % (w, sk.text().strip())
            elif not w:
                self.node.pop("save_as", None)
            self.changed.emit()
        sw.activated.connect(keep)
        sk.textChanged.connect(keep)
        sk.setVisible(bool(where))
        self._field(i18n.t("Keep the answer as"), srow)
        self._field(i18n.t("If the answer is not right, say"), _line(self.node.get("retry_text", ""), self._set("retry_text"),
                                                                       i18n.t("Sorry, I didn't get that. …"), i18n.t("Retry message")))
        tries = QSpinBox()
        tries.setRange(1, 5)
        tries.setValue(int(self.node.get("max_tries", 2)))
        tries.setMinimumHeight(34)
        tries.valueChanged.connect(lambda n: (self.node.__setitem__("max_tries", n), self.changed.emit()))
        trow = QHBoxLayout()
        trow.addWidget(tries)
        trow.addStretch(1)
        self._field(i18n.t("Tries"), trow)
        self._next("invalid_next", i18n.t("If they keep getting it wrong"))
        self._next()
        self._timeout()

    def _build_condition(self):
        rows = _Rows(self, self.node, "rules", 10, i18n.t("Add a condition"), kind="rule")
        rows.structure.connect(lambda: (self.shape.emit(), self.changed.emit()))
        rows.edited.connect(self.changed.emit)
        self.rows.append(rows)
        self._field(i18n.t("The first one that fits is followed"), rows)
        self._next("else", i18n.t("If none fits"))

    def _build_set_attribute(self):
        self._field(i18n.t("Detail name"), _line(self.node.get("key"), self._set("key"), i18n.t("e.g. Segment"), i18n.t("Detail name")))
        self._field(i18n.t("Value"), _line(self.node.get("value"), self._set("value"), i18n.t("A value, or {{var.x}}"), i18n.t("Value")))
        self._next()

    def _build_add_tag(self):
        self._field(i18n.t("Tag"), _line(self.node.get("tag"), self._set("tag"), i18n.t("e.g. hot-lead"), i18n.t("Tag")))
        self._next()

    _build_remove_tag = _build_add_tag

    def _build_delay(self):
        minutes = int(self.node.get("minutes") or max(1, int(self.node.get("seconds") or 60) // 60))
        unit, amount = (("d", minutes // 1440) if minutes % 1440 == 0 else ("h", minutes // 60) if minutes % 60 == 0 else ("m", minutes))
        row = QHBoxLayout()
        n = QSpinBox()
        n.setRange(1, 10000)
        n.setValue(max(amount, 1))
        n.setMinimumHeight(34)
        u = QComboBox()
        u.setMinimumHeight(34)
        for k, label in (("m", i18n.t("minutes")), ("h", i18n.t("hours")), ("d", i18n.t("days"))):
            u.addItem(label, k)
        u.setCurrentIndex(u.findData(unit))

        def sync(*_):
            total = n.value() * {"m": 1, "h": 60, "d": 1440}[u.currentData()]
            self.node["minutes"] = min(total, 7 * 1440)
            self.node.pop("seconds", None)
            self.changed.emit()
        n.valueChanged.connect(sync)
        u.activated.connect(sync)
        row.addWidget(n)
        row.addWidget(u)
        row.addStretch(1)
        self._field(i18n.t("Wait for"), row, i18n.t("Up to 7 days. A plain message can only follow within 24 hours of the customer's last message — after that use a template."))
        self._next()

    def _build_template(self):
        combo = QComboBox()
        combo.setMinimumHeight(34)
        combo.addItem(i18n.t("Choose a template"), None)
        for t in self.ctx.templates():
            combo.addItem("%s · %s" % (t.get("name"), t.get("language")), t)
        i = next((k for k in range(1, combo.count()) if combo.itemData(k).get("name") == self.node.get("name")), 0)
        combo.setCurrentIndex(i)
        self._field(i18n.t("Template"), combo)
        holder = QVBoxLayout()
        holder.setSpacing(theme.SPACE_1)
        self.body.addLayout(holder)

        def rebuild(*_):
            t = combo.currentData() or {}
            ui.clear(holder)
            if t:
                self.node["name"], self.node["language"] = t.get("name"), t.get("language") or "en_US"
            text = ""
            for comp in t.get("components") or []:
                if comp.get("type") == "BODY":
                    text = comp.get("text", "")
            mapping = self.node.setdefault("variables", {})
            for n in variables_of(text):
                row = QHBoxLayout()
                tag = C.label("{{%d}}" % n, level="SUPPORT", weight=700)
                tag.setMinimumWidth(48)
                row.addWidget(tag)
                src = QComboBox()
                src.setMinimumHeight(34)
                for k, label, _needs, _ph in _sources():
                    src.addItem(label, k)
                edit = _line("", lambda t: None, i18n.t("The text"))
                spec = mapping.get(str(n)) or {}
                current = {"field": spec.get("field"), "attribute": "attribute", "static": "static", "tracked_link": "tracked_link"}.get(spec.get("source"), "first_name")
                src.setCurrentIndex(max(src.findData(spec.get("field") if spec.get("source") == "field" else current), 0))
                edit.setText(str(spec.get("key") or spec.get("value") or spec.get("target") or ""))

                def sync(*_, n=n, src=src, edit=edit):
                    needs = next((nd for k, _l, nd, _p in _sources() if k == src.currentData()), False)
                    edit.setVisible(needs)
                    mapping[str(n)] = variable_spec(src.currentData(), edit.text())
                    self.changed.emit()
                src.activated.connect(sync)
                edit.textChanged.connect(sync)
                edit.setVisible(next((nd for k, _l, nd, _p in _sources() if k == src.currentData()), False))
                mapping.setdefault(str(n), variable_spec(src.currentData(), edit.text()))
                row.addWidget(src, 2)
                row.addWidget(edit, 2)
                box = QWidget()
                box.setLayout(row)
                holder.addWidget(box)
            self.changed.emit()
        combo.activated.connect(rebuild)
        rebuild()
        self._next()

    def _build_api_request(self):
        row = QHBoxLayout()
        method = QComboBox()
        method.setMinimumHeight(34)
        method.addItems(["GET", "POST"])
        method.setCurrentText(self.node.get("method", "GET"))
        method.activated.connect(lambda _i: (self.node.__setitem__("method", method.currentText()), self.changed.emit()))
        row.addWidget(method)
        row.addWidget(_line(self.node.get("url"), self._set("url"), "https://…", i18n.t("Address")), 1)
        self._field(i18n.t("Ask this address"), row, i18n.t("Only secure (https) public addresses. {{message}}, {{attr.City}} and {{var.x}} can be used in it."))
        headers = "\n".join("%s: %s" % (k, v) for k, v in (self.node.get("headers") or {}).items())
        self._field(i18n.t("Headers"), _text_edit(headers, lambda t: (self.node.__setitem__("headers", dict((ln.split(":", 1)[0].strip(), ln.split(":", 1)[1].strip())
                                                                                                         for ln in t.splitlines() if ":" in ln)), self.changed.emit()),
                                                  60, "Authorization: Bearer …", i18n.t("Headers")))
        self._field(i18n.t("Body (for POST)"), _text_edit(self.node.get("body", ""), lambda t: (self.node.__setitem__("body", t) if t else self.node.pop("body", None), self.changed.emit()),
                                                         60, '{"order": "{{message}}"}', i18n.t("Body")))
        save = "\n".join("%s = %s" % (k, v) for k, v in (self.node.get("save") or {}).items())
        self._field(i18n.t("Keep from the answer"), _text_edit(save, lambda t: (self.node.__setitem__("save", dict((ln.split("=", 1)[0].strip(), ln.split("=", 1)[1].strip())
                                                                                                               for ln in t.splitlines() if "=" in ln)), self.changed.emit()),
                                                               60, i18n.t("name = path.in.answer"), i18n.t("Values to keep")),
                    i18n.t("One per line. city = customer.city keeps it for this flow as {{var.city}}; attr:City = customer.city puts it on the contact."))
        self._api_test_row()
        self._next("ok_next", i18n.t("If it works"))
        self._next("error_next", i18n.t("If it fails"))

    def _build_handoff(self):
        self._field(i18n.t("Tell the customer"), _text_edit(self.node.get("text"), self._set("text"), 72, i18n.t("A colleague will reply shortly."), i18n.t("Hand-over message")))
        self._field(i18n.t("Note for your team"), _line(self.node.get("reason"), self._set("reason"), i18n.t("Why this chat needs a person"), i18n.t("Note for your team")))

    def _build_agent(self):
        combo = QComboBox()
        combo.setMinimumHeight(34)
        combo.addItem(i18n.t("The default AI agent"), None)
        for a in self.ctx.agents():
            combo.addItem(a.get("name"), a.get("id"))
        combo.setCurrentIndex(max(combo.findData(self.node.get("agent_id")), 0))
        combo.activated.connect(lambda _i: (self.node.__setitem__("agent_id", combo.currentData()) if combo.currentData() else self.node.pop("agent_id", None), self.changed.emit()))
        self._field(i18n.t("Which agent"), combo)

    def _build_jump_flow(self):
        combo = QComboBox()
        combo.setMinimumHeight(34)
        combo.addItem(i18n.t("Choose a flow"), "")
        for f in self.ctx.flows():
            combo.addItem(f.get("name"), f.get("id"))
        combo.setCurrentIndex(max(combo.findData(self.node.get("flow_id")), 0))
        combo.activated.connect(lambda _i: (self.node.__setitem__("flow_id", combo.currentData()), self.changed.emit()))
        self._field(i18n.t("Continue in"), combo)

    def _build_end(self):
        self.body.addWidget(C.label(i18n.t("The flow finishes here."), level="SUPPORT", colour=theme.NEUTRAL[600]))
