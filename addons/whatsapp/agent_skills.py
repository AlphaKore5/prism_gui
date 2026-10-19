"""An AI agent's skills: the jobs it knows how to do.

A skill says WHEN it applies and what to do. A skill can also collect details — a name, a city, a day — which the agent asks for in the chat and keeps on the contact
as a detail of their own (so a flow, a campaign segment or a teammate can use it). When every needed detail is in, the skill can tag the contact and/or pass the chat
to a person. Ready-made starting points: answer questions, help with a problem, hand over, qualify a lead, book an appointment, take a bulk enquiry, ask for feedback.
"""
from __future__ import annotations

import copy
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QHBoxLayout, QLineEdit, QMenu, QPlainTextEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from dialogs.base import PrismDialog
from widgets import controls as C

MAX_SKILLS = 12
MAX_DETAILS = 8


def kinds() -> list:
    """(kind, name, what it is for) — in the order the Add a skill menu shows them."""
    return [("faq", i18n.t("Answer questions"), i18n.t("Answer from what it knows.")), ("support", i18n.t("Help with a problem"), i18n.t("Take the details of a problem, then pass it on.")),
            ("handoff", i18n.t("Hand over to a person"), i18n.t("Know when a human should take over.")), ("lead", i18n.t("Qualify a lead"), i18n.t("Find out what they need and where.")),
            ("booking", i18n.t("Book an appointment"), i18n.t("Take a day and a time.")), ("enquiry", i18n.t("Take a bulk enquiry"), i18n.t("Product, quantity and city.")),
            ("feedback", i18n.t("Ask for feedback"), i18n.t("A rating and a comment.")), ("custom", i18n.t("Something else"), i18n.t("Describe your own."))]


def kind_name(kind: str) -> str:
    return next((n for k, n, _h in kinds() if k == kind), kind)


def _detail(name, label, required=True, description=""):
    return {"name": name, "label": label, "description": description, "required": required, "attribute": ""}


def preset(kind: str) -> dict:
    """A skill with sensible starting words — every one is the owner's to change."""
    base = {"kind": kind, "name": kind_name(kind), "enabled": True, "when": "", "instructions": "", "variables": [], "on_complete": {"tag": "", "handoff": False, "reason": ""}}
    if kind == "faq":
        base.update(when=i18n.t("the customer asks about the business, its prices, timings or how things work"),
                    instructions=i18n.t("Answer from what you know. If it is not there, say you will ask a colleague."))
    elif kind == "support":
        base.update(when=i18n.t("the customer has a problem with an order or a service"), instructions=i18n.t("Be sorry for the trouble, then find out exactly what went wrong."),
                    variables=[_detail("issue", i18n.t("The problem"), True, i18n.t("what went wrong, in their words")), _detail("order", i18n.t("Order or bill number"), False)],
                    on_complete={"tag": "needs-support", "handoff": True, "reason": i18n.t("a support request is ready for a person")})
    elif kind == "handoff":
        base.update(when=i18n.t("the customer is upset, asks for a person, or raises a complaint or a refund"),
                    instructions=i18n.t("Say a colleague will reply shortly, and hand the chat over."))
    elif kind == "lead":
        base.update(when=i18n.t("the customer wants a quote or wants to buy"), instructions=i18n.t("Ask one or two things at a time and keep it friendly."),
                    variables=[_detail("name", i18n.t("Name")), _detail("city", i18n.t("City")), _detail("requirement", i18n.t("What they need"), True, i18n.t("the kind of work or product")),
                               _detail("budget", i18n.t("Budget"), False)],
                    on_complete={"tag": "qualified-lead", "handoff": True, "reason": i18n.t("a qualified lead is ready")})
    elif kind == "booking":
        base.update(when=i18n.t("the customer wants a visit, a demo or an appointment"), instructions=i18n.t("Offer to note a day and time; a person will confirm it."),
                    variables=[_detail("name", i18n.t("Name")), _detail("day", i18n.t("Preferred day")), _detail("time", i18n.t("Preferred time"))],
                    on_complete={"tag": "booking-request", "handoff": True, "reason": i18n.t("a booking request needs confirming")})
    elif kind == "enquiry":
        base.update(when=i18n.t("the customer asks for a large or repeat order"), variables=[_detail("product", i18n.t("Product")), _detail("quantity", i18n.t("Quantity")),
                                                                                           _detail("city", i18n.t("Delivery city"))],
                    on_complete={"tag": "bulk-enquiry", "handoff": True, "reason": i18n.t("a bulk enquiry is ready")})
    elif kind == "feedback":
        base.update(when=i18n.t("the customer is giving feedback, or it is time to ask for it"), instructions=i18n.t("Ask for a rating from 1 to 5, then an optional comment."),
                    variables=[_detail("rating", i18n.t("Rating (1 to 5)")), _detail("comment", i18n.t("Comment"), False)], on_complete={"tag": "gave-feedback", "handoff": False, "reason": ""})
    return base


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:30]


class SkillDialog(PrismDialog):
    """Make or change one skill. `.value()` is the skill once accepted."""

    def __init__(self, skill: dict, new: bool = False, parent=None):
        super().__init__(i18n.t("New skill") if new else i18n.t("Change this skill"), i18n.t("Say when the agent uses it and what it should do. It may also collect details."),
                         icon="sparkles", parent=parent, scrollable=True)
        self.skill = copy.deepcopy(skill)
        self._new = new
        self.name = QLineEdit(self.skill.get("name") or "")
        self.name.setMinimumHeight(38)
        self.name.setMaxLength(60)
        self.name.setAccessibleName(i18n.t("Skill name"))
        self.body.addWidget(ui.field(i18n.t("Name"), self.name))
        self.when = QLineEdit(self.skill.get("when") or "")
        self.when.setMinimumHeight(38)
        self.when.setMaxLength(400)
        self.when.setAccessibleName(i18n.t("When to use it"))
        self.when.setPlaceholderText(i18n.t("the customer wants a quote"))
        self.body.addWidget(ui.field(i18n.t("Use it when"), self.when, i18n.t("Finish the sentence: the agent uses this skill when…")))
        self.instructions = QPlainTextEdit(self.skill.get("instructions") or "")
        self.instructions.setFixedHeight(84)
        self.instructions.setAccessibleName(i18n.t("What to do"))
        self.instructions.setPlaceholderText(i18n.t("What it should do or say, in a sentence or two."))
        self.body.addWidget(ui.field(i18n.t("What to do"), self.instructions))

        self.body.addWidget(C.label(i18n.t("Details to collect").upper(), level="LABEL", colour=theme.NEUTRAL[500]))
        self.body.addWidget(C.label(i18n.t("The agent asks for these in the chat, one or two at a time, and keeps each one on the contact under the name you choose."),
                                    level="META", colour=theme.NEUTRAL[600], wrap=True))
        self.rows_col = QVBoxLayout()
        self.rows_col.setSpacing(theme.SPACE_1)
        self.body.addLayout(self.rows_col)
        self.rows: list = []
        self.add_btn = C.button(i18n.t("Add a detail"), "tertiary", icon_name="plus", on_click=lambda: self.add_detail({}))
        add = QHBoxLayout()
        add.addWidget(self.add_btn)
        add.addStretch(1)
        self.body.addLayout(add)
        for v in self.skill.get("variables") or []:
            self.add_detail(v)

        self.body.addWidget(C.label(i18n.t("When every needed detail is in").upper(), level="LABEL", colour=theme.NEUTRAL[500]))
        done = self.skill.get("on_complete") or {}
        self.tag = QLineEdit(done.get("tag") or "")
        self.tag.setMinimumHeight(38)
        self.tag.setMaxLength(40)
        self.tag.setAccessibleName(i18n.t("Tag to add"))
        self.tag.setPlaceholderText(i18n.t("e.g. qualified-lead"))
        self.body.addWidget(ui.field(i18n.t("Tag the contact"), self.tag))
        self.handoff = QCheckBox(i18n.t("Then hand the chat to a person"))
        self.handoff.setChecked(bool(done.get("handoff")))
        self.handoff.toggled.connect(lambda on: self.reason.setEnabled(on))
        self.body.addWidget(self.handoff)
        self.reason = QLineEdit(done.get("reason") or "")
        self.reason.setMinimumHeight(36)
        self.reason.setMaxLength(120)
        self.reason.setAccessibleName(i18n.t("Note for your team"))
        self.reason.setPlaceholderText(i18n.t("Note for your team, e.g. a qualified lead is ready"))
        self.reason.setEnabled(self.handoff.isChecked())
        self.body.addWidget(self.reason)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.button(i18n.t("Save skill"), "primary", on_click=self._go))
        self.resize(600, 720)

    def add_detail(self, v: dict):
        if len(self.rows) >= MAX_DETAILS:
            return
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        label = QLineEdit(v.get("label") or "")
        label.setMinimumHeight(34)
        label.setPlaceholderText(i18n.t("What to ask for, e.g. City"))
        label.setAccessibleName(i18n.t("Detail"))
        attribute = QLineEdit(v.get("attribute") or "")
        attribute.setMinimumHeight(34)
        attribute.setPlaceholderText(i18n.t("Saved on the contact as…"))
        attribute.setAccessibleName(i18n.t("Saved as"))
        required = QCheckBox(i18n.t("Needed"))
        required.setChecked(bool(v.get("required", True)))
        box = QWidget()
        box.setLayout(row)
        entry = {"label": label, "attribute": attribute, "required": required, "name": v.get("name") or "", "description": v.get("description") or "", "box": box}
        remove = C.icon_button("trash", i18n.t("Remove this detail"), on_click=lambda _=False, e=entry: self._remove(e), colour=theme.NEUTRAL[600])
        for w, s in ((label, 3), (attribute, 3), (required, 0), (remove, 0)):
            row.addWidget(w, s)
        self.rows.append(entry)
        self.rows_col.addWidget(box)
        self.add_btn.setVisible(len(self.rows) < MAX_DETAILS)

    def _remove(self, entry: dict):
        self.rows.remove(entry)
        ui.discard(entry["box"])
        self.add_btn.setVisible(True)

    def value(self) -> dict:
        names, details = set(), []
        for e in self.rows:
            label = e["label"].text().strip()
            if not label:
                continue
            name = e["name"] or slug(label) or "detail"
            base, n = name, 2
            while name in names:
                name, n = "%s_%d" % (base[:26], n), n + 1
            names.add(name)
            details.append({"name": name, "label": label, "description": e["description"], "required": e["required"].isChecked(),
                            "attribute": re.sub(r"[^A-Za-z0-9_]+", "_", e["attribute"].text().strip()).strip("_")[:40] or ""})
        out = dict(self.skill)
        out.update(name=self.name.text().strip(), when=self.when.text().strip(), instructions=self.instructions.toPlainText().strip(), variables=details,
                   on_complete={"tag": self.tag.text().strip(), "handoff": self.handoff.isChecked(), "reason": self.reason.text().strip()})
        return out

    def _go(self):
        if not self.name.text().strip():
            self.error.error(i18n.t("Give the skill a name."))
            return
        self.accept()


class SkillsSection(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        card, sc = ui.card(i18n.t("Skills"), i18n.t("The jobs the agent knows how to do. A skill can ask the customer for details and keep them on the contact."))
        self.list_col = QVBoxLayout()
        self.list_col.setSpacing(theme.SPACE_2)
        sc.addLayout(self.list_col)
        row = QHBoxLayout()
        self.add_btn = C.button(i18n.t("Add a skill"), "primary", icon_name="plus", on_click=self._add_menu)
        row.addWidget(self.add_btn)
        row.addStretch(1)
        sc.addLayout(row)
        col.addWidget(card)
        col.addStretch(1)
        self.render()

    @property
    def skills(self) -> list:
        return self.editor.draft["skills"]

    def render(self):
        ui.clear(self.list_col)
        if not self.skills:
            self.list_col.addWidget(C.label(i18n.t("No skills yet. Without any, it just answers questions from what it knows."), level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
        for s in self.skills:
            self.list_col.addWidget(self._row(s))
        self.add_btn.setVisible(len(self.skills) < MAX_SKILLS)

    def _row(self, s: dict) -> QWidget:
        line = QFrame()
        line.setObjectName("waSkill")
        line.setAttribute(Qt.WA_StyledBackground, True)
        line.setStyleSheet(f"#waSkill {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(line)
        col.setContentsMargins(14, 10, 10, 10)
        col.setSpacing(2)
        top = QHBoxLayout()
        top.addWidget(C.label(s.get("name") or "", level="SUPPORT", weight=700), 1)
        top.addWidget(C.Pill(kind_name(s.get("kind")), "neutral"))
        switch = C.ToggleSwitch()
        switch.setChecked(bool(s.get("enabled", True)))
        switch.setToolTip(i18n.t("On or off"))
        switch.toggled.connect(lambda on, x=s: (x.__setitem__("enabled", bool(on)), self.editor.edited()))
        top.addWidget(switch)
        top.addWidget(C.button(i18n.t("Change"), "tertiary", small=True, on_click=lambda _=False, x=s: self.change(x)))
        top.addWidget(C.icon_button("trash", i18n.t("Delete this skill"), on_click=lambda _=False, x=s: self.remove(x), colour=theme.ERR_INK))
        col.addLayout(top)
        if s.get("when"):
            col.addWidget(C.label(i18n.t("Used when {w}").format(w=s["when"]), level="META", colour=theme.NEUTRAL[700], wrap=True))
        if s.get("variables"):
            col.addWidget(C.label(i18n.t("Collects: {d}").format(d=", ".join(v.get("label") or v["name"] for v in s["variables"])), level="META", colour=theme.NEUTRAL[600], wrap=True))
        done = s.get("on_complete") or {}
        after = [i18n.t("tags “{t}”").format(t=done["tag"])] if done.get("tag") else []
        if done.get("handoff"):
            after.append(i18n.t("hands the chat to a person"))
        if after and s.get("variables"):
            col.addWidget(C.label(i18n.t("When complete it {a}").format(a=" and ".join(after)), level="META", colour=theme.NEUTRAL[600], wrap=True))
        return line

    def _add_menu(self):
        menu = QMenu(self)
        for kind, name, hint in kinds():
            act = menu.addAction(name)
            act.setToolTip(hint)
            act.triggered.connect(lambda _=False, k=kind: self.add(k))
        menu.exec(self.add_btn.mapToGlobal(self.add_btn.rect().bottomLeft()))

    def add(self, kind: str, dialog: bool = True):
        skill = preset(kind)
        if dialog:
            dlg = SkillDialog(skill, new=True, parent=self.editor)
            if not dlg.exec():
                return
            skill = dlg.value()
        self.skills.append(skill)
        self.render()
        self.editor.edited()

    def change(self, skill: dict):
        dlg = SkillDialog(skill, parent=self.editor)
        if dlg.exec():
            skill.clear()
            skill.update(dlg.value())
            self.render()
            self.editor.edited()

    def remove(self, skill: dict):
        if ui.confirm(self.editor, i18n.t("Delete skill"), i18n.t("Delete “{n}”?").format(n=skill.get("name"))):
            self.skills.remove(skill)
            self.render()
            self.editor.edited()
