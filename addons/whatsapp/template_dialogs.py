"""Two ways to start a template that are not a blank form.

    TemplateLibraryDialog   the ready-made templates, by industry, with the message shown as the customer will see it
    TemplateAIDialog        describe what you want and have templates written (checked against Meta's rules before you see them);
                            or, for a template Meta refused, what Meta most likely objected to and a rewrite

Both end with `.chosen`, a template dict (name, language, category, components) for the editor to fill itself from.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QListWidget, QListWidgetItem, QPlainTextEdit, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.template_editor import LANGUAGES, TemplatePreview, fields_from
from dialogs.base import PrismDialog
from widgets import controls as C

_CATEGORY_NAMES = {"MARKETING": "Marketing", "UTILITY": "Utility", "AUTHENTICATION": "Authentication"}


def category_name(category: str) -> str:
    return {"MARKETING": i18n.t("Marketing"), "UTILITY": i18n.t("Utility"), "AUTHENTICATION": i18n.t("Authentication")}.get(category or "", category or "")


def show_template(preview: TemplatePreview, item: dict) -> None:
    """The message as the customer will see it."""
    comps = item.get("components") or []
    f = fields_from(comps)
    extra = {"image": i18n.t("A picture goes here"), "video": i18n.t("A video goes here"), "document": i18n.t("A document goes here"),
             "location": i18n.t("A map location goes here"), "offer": i18n.t("Limited-time offer"),
             "carousel": i18n.t("Cards, side by side")}.get(f["kind"], "")
    body = f["body"]
    if item.get("category") == "AUTHENTICATION":
        body = i18n.t("123456 is your verification code. For your security, do not share this code.")
    preview.set_extra(extra)
    preview.set_content(f["header"], body, f["footer"], f["buttons"], f["samples"], f["header_sample"])


def needs_text(item: dict) -> str:
    """What the person must still provide for this template, in words."""
    need = item.get("needs_media")
    if need:
        return i18n.t("You will choose a sample {k} when you edit it.").format(k={"image": i18n.t("picture"), "video": i18n.t("video"),
                                                                                   "document": i18n.t("document")}.get(need, need))
    if item.get("needs_app"):
        return i18n.t("You will enter your Android app's package name and signature hash.")
    return ""


class _Chooser(PrismDialog):
    """A list on the left, the chosen message on the right, and a button that takes it."""

    def __init__(self, title: str, subtitle: str, icon: str, use_text: str, parent=None):
        super().__init__(title, subtitle, icon=icon, parent=parent)
        self.chosen = None
        self._items: list = []
        cols = QHBoxLayout()
        cols.setSpacing(theme.SPACE_5)
        self.body.addLayout(cols, stretch=1)
        self.left = QVBoxLayout()
        self.left.setSpacing(theme.SPACE_3)
        left_wrap = QWidget()
        left_wrap.setLayout(self.left)
        left_wrap.setMinimumWidth(340)
        cols.addWidget(left_wrap, stretch=5)
        self.list = QListWidget()
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setSpacing(2)
        self.list.setStyleSheet("QListWidget { background: transparent; } QListWidget::item { padding: 8px 10px; border-radius: 8px; }"
                                f" QListWidget::item:selected {{ background: {theme.NEUTRAL[100]}; color: {theme.TEXT}; }}")
        self.list.currentItemChanged.connect(lambda cur, _p: self._select(cur.data(Qt.UserRole) if cur is not None else None))
        self.list.itemDoubleClicked.connect(lambda _i: self._use())
        right = QVBoxLayout()
        right.setSpacing(theme.SPACE_3)
        self.preview = TemplatePreview()
        right.addWidget(self.preview, stretch=1)
        self.facts = C.label("", level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True)
        right.addWidget(self.facts)
        self.note = ui.note()
        right.addWidget(self.note)
        right_wrap = QWidget()
        right_wrap.setLayout(right)
        right_wrap.setMinimumWidth(300)
        right_wrap.setMaximumWidth(400)
        cols.addWidget(right_wrap, stretch=3)
        self.use = self.button(use_text, "primary", on_click=self._use)
        self.use.setEnabled(False)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.use)
        self.setMinimumSize(860, 560)
        self.resize(960, 660)

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def set_items(self, items: list, label=None):
        self._items = list(items)
        self.list.blockSignals(True)
        self.list.clear()
        for it in self._items:
            row = QListWidgetItem("%s\n%s" % ((label or (lambda x: x.get("title") or x.get("name") or ""))(it),
                                              category_name(it.get("category")) + (" · " + it["industry"] if it.get("industry") else "")))
            row.setData(Qt.UserRole, it)
            self.list.addItem(row)
        self.list.blockSignals(False)
        if self._items:
            self.list.setCurrentRow(0)
        else:
            self._select(None)

    def _select(self, item):
        self.use.setEnabled(item is not None)
        if item is None:
            self.preview.set_extra("")
            self.preview.set_content("", "", "", [], {}, "")
            self.facts.setText("")
            return
        show_template(self.preview, item)
        self.facts.setText(self.describe(item))

    def describe(self, item: dict) -> str:
        return needs_text(item)

    def _use(self):
        item = self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() is not None else None
        if item is not None:
            self.chosen = item
            self.accept()


class TemplateLibraryDialog(_Chooser):
    def __init__(self, parent=None):
        super().__init__(i18n.t("Template library"), i18n.t("Ready to submit. Pick one, change the words if you like, and send it to Meta."),
                         "book", i18n.t("Use this template"), parent)
        self._all: list = []
        self.search = C.SearchField(i18n.t("Search the library"))
        self.search.changed.connect(lambda _t: self._filter())
        self.left.addWidget(self.search)
        self.chips = C.FilterChips([("", i18n.t("All"))], "")
        self.chips.changed.connect(lambda _k: self._filter())
        self.left.addWidget(self.chips)
        self.left.addWidget(self.list, stretch=1)
        self.count = C.label("", level="META", colour=theme.NEUTRAL[500])
        self.left.addWidget(self.count)
        ui.call(self, "templates/library", {}, done=self._loaded, failed=lambda m, _d: self.say(m, True))

    def _loaded(self, reply: dict):
        self._all = list(reply.get("library") or [])
        industries = list(reply.get("industries") or sorted({i.get("industry") for i in self._all if i.get("industry")}))
        old = self.chips
        self.chips = C.FilterChips([("", i18n.t("All"))] + [(x, x) for x in industries], "")
        self.chips.changed.connect(lambda _k: self._filter())
        self.left.replaceWidget(old, self.chips)
        ui.discard(old)
        self._filter()

    def _filter(self):
        industry, term = self.chips.current(), self.search.text().strip().lower()
        rows = []
        for it in self._all:
            if industry and it.get("industry") != industry:
                continue
            text = (it.get("title", "") + " " + " ".join(str(c.get("text") or "") for c in it.get("components") or [])).lower()
            if term and term not in text:
                continue
            rows.append(it)
        self.set_items(rows)
        self.count.setText(i18n.t("{n} templates").format(n=len(rows)) if len(rows) != 1 else i18n.t("1 template"))


class TemplateAIDialog(_Chooser):
    """Writes templates from a description, or fixes one Meta refused (when `rewrite` is that template)."""

    def __init__(self, parent=None, rewrite: dict = None):
        super().__init__(i18n.t("Fix this template") if rewrite else i18n.t("Write a template with AI"),
                         i18n.t("What Meta most likely objected to, and a rewrite that keeps your meaning.") if rewrite
                         else i18n.t("Say what the message is for. Each suggestion is checked against Meta's rules before you see it."),
                         "sparkles", i18n.t("Use this template"), parent)
        if rewrite:
            self.hints = C.label("", level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True)
            self.left.addWidget(self.hints)
            self.left.addWidget(self.list, stretch=1)
            self.say_busy(i18n.t("Reading Meta's reason…"))
            ui.call(self, "templates/rewrite", {"template_id": rewrite.get("id")}, done=self._rewritten, failed=lambda m, _d: self.say(m, True))
            return
        self.idea = QPlainTextEdit()
        self.idea.setFixedHeight(84)
        self.idea.setPlaceholderText(i18n.t("e.g. Tell customers their site visit is confirmed, with the date and a way to reschedule"))
        self.idea.setAccessibleName(i18n.t("What the message is for"))
        self.left.addWidget(ui.field(i18n.t("What is it for?"), self.idea))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        self.category = QComboBox()
        self.category.setMinimumHeight(36)
        self.category.addItem(i18n.t("Let AI choose"), "")
        self.category.addItem(i18n.t("Marketing"), "MARKETING")
        self.category.addItem(i18n.t("Utility"), "UTILITY")
        self.tone = QComboBox()
        self.tone.setMinimumHeight(36)
        for key, label in (("friendly", i18n.t("Friendly")), ("formal", i18n.t("Formal")), ("warm", i18n.t("Warm")), ("urgent", i18n.t("Urgent")),
                           ("playful", i18n.t("Playful"))):
            self.tone.addItem(label, key)
        self.goal = QComboBox()
        self.goal.setMinimumHeight(36)
        for key, label in (("replies", i18n.t("Get replies")), ("clicks", i18n.t("Get clicks")), ("reads", i18n.t("Be read")), ("conversions", i18n.t("Get orders"))):
            self.goal.addItem(label, key)
        row.addWidget(ui.field(i18n.t("Category"), self.category), stretch=1)
        row.addWidget(ui.field(i18n.t("Tone"), self.tone), stretch=1)
        row.addWidget(ui.field(i18n.t("Goal"), self.goal), stretch=1)
        self.left.addLayout(row)
        self.language = QComboBox()
        self.language.setMinimumHeight(36)
        for code, name in LANGUAGES:
            self.language.addItem(name, code)
        self.left.addWidget(ui.field(i18n.t("Language"), self.language))
        self.write_btn = C.button(i18n.t("Write templates"), "primary", "sparkles", on_click=self._write)
        self.left.addWidget(self.write_btn)
        self.left.addWidget(self.list, stretch=1)

    def say_busy(self, text: str):
        self.note.set(text, "quiet")

    # ── writing ──────────────────────────────────────────────────────────────
    def _write(self):
        about = self.idea.toPlainText().strip()
        if len(about) < 8:
            self.say(i18n.t("Describe what the message is for, in a sentence."), True)
            return
        self.write_btn.setEnabled(False)
        self.say_busy(i18n.t("Writing…"))
        ui.call(self, "templates/generate", {"description": about, "category": self.category.currentData(), "tone": self.tone.currentData(),
                                             "goal": self.goal.currentData(), "language": self.language.currentData(), "count": 3},
                done=self._written, failed=self._write_failed)

    def _written(self, reply: dict):
        self.write_btn.setEnabled(True)
        self.note.clear_note()
        self.set_items(list(reply.get("templates") or []), label=lambda t: t.get("name") or "")

    def _write_failed(self, message: str, _detail: dict):
        self.write_btn.setEnabled(True)
        self.say(message, True)

    # ── fixing ───────────────────────────────────────────────────────────────
    def _rewritten(self, reply: dict):
        self.note.clear_note()
        self.hints.setText("\n".join(reply.get("hints") or []))
        suggestion = reply.get("suggestion")
        if suggestion:
            self.set_items([suggestion], label=lambda t: i18n.t("Suggested rewrite"))
        else:
            self.set_items([])
            self.say(i18n.t("AI is not available here, so only Meta's likely reason is shown.") if not reply.get("ai")
                     else i18n.t("AI could not write a better version just now. The note above still applies."), False)

    def describe(self, item: dict) -> str:
        issues = item.get("issues") or []
        errors = [i for i in issues if i.get("severity") == "error"]
        if not issues:
            return i18n.t("Nothing Meta is known to refuse.")
        lines = ["• " + str(i.get("message")) for i in errors + [x for x in issues if x not in errors]]
        return (i18n.t("Needs a fix before Meta will take it:") + "\n" if errors else i18n.t("Worth a look:") + "\n") + "\n".join(lines[:4])
