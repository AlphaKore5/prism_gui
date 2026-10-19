"""The Forms tab — forms that open inside a WhatsApp chat.

A customer taps a button in the chat, a form opens over it, and what they fill in comes back to you as a tidy list — and, if you want, onto the contact itself. Good for enquiries,
booking a visit (with times that cannot be double-booked), feedback and quotations. Start from one of six ready forms or from nothing; check it; publish it to Meta; send it to a chat.

Everything goes through Prism's licence server. A form is only ever sent to people inside the 24 hours after they last wrote to you.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLineEdit, QPlainTextEdit, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.contact_picker import ContactChoice
from addons.whatsapp.form_editor import FormEditor
from dialogs.base import PrismDialog
from widgets import controls as C


def size_words(screens: int, fields: int) -> str:
    """"1 screen, 5 fields" — the singular where there is one."""
    return "%s, %s" % ((i18n.t("{n} screen") if screens == 1 else i18n.t("{n} screens")).format(n=screens), (i18n.t("{n} field") if fields == 1 else i18n.t("{n} fields")).format(n=fields))


def answers_words(n: int) -> str:
    return (i18n.t("{n} answer") if n == 1 else i18n.t("{n} answers")).format(n=n)


def status_pill(status: str) -> "C.Pill":
    words = {"draft": i18n.t("Not published"), "published": i18n.t("Published"), "deprecated": i18n.t("Retired"), "throttled": i18n.t("Slowed by Meta"), "blocked": i18n.t("Blocked by Meta")}
    tone = {"published": "ok", "draft": "quiet", "deprecated": "quiet", "throttled": "warn", "blocked": "err"}
    return C.Pill(words.get(status, status), tone.get(status, "quiet"))


class CodeDialog(PrismDialog):
    """The code Meta is given for a form, for people who want to see it."""

    def __init__(self, text: str, parent=None):
        super().__init__(i18n.t("The form as Meta sees it"), i18n.t("You never need to touch this."), icon="code", parent=parent)
        box = QPlainTextEdit(text)
        box.setReadOnly(True)
        box.setMinimumHeight(360)
        box.setAccessibleName(i18n.t("Form code"))
        self.body.addWidget(box)
        self.footer.add_secondary(self.button(i18n.t("Copy"), on_click=lambda: ui.copy_text(self, text, i18n.t("Form code"))))
        self.footer.set_primary(self.button(i18n.t("Close"), "primary", on_click=self.accept))
        self.resize(640, 560)


class NewFormDialog(PrismDialog):
    """Pick a starting point."""

    def __init__(self, templates: list, parent=None):
        super().__init__(i18n.t("New form"), i18n.t("Start from a ready form and change what you like, or start empty."), icon="file", parent=parent, scrollable=True)
        self.chosen = None
        self.rows = {}
        for t in templates:
            row = QFrame()
            row.setObjectName("waTemplate")
            row.setAttribute(Qt.WA_StyledBackground, True)
            row.setStyleSheet(f"#waTemplate {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
            col = QVBoxLayout(row)
            col.setContentsMargins(14, 10, 14, 10)
            col.setSpacing(2)
            top = QHBoxLayout()
            top.addWidget(C.label(t["name"], level="SUPPORT", weight=700), 1)
            if t.get("live"):
                top.addWidget(C.Pill(i18n.t("Live times"), "info"))
            top.addWidget(C.button(i18n.t("Use this"), "secondary", small=True, on_click=lambda _=False, k=t["key"]: self.pick(k)))
            col.addLayout(top)
            col.addWidget(C.label(t["about"], level="META", colour=theme.NEUTRAL[600], wrap=True))
            col.addWidget(C.label(size_words(t["screens"], t["fields"]), level="META", colour=theme.NEUTRAL[500]))
            self.body.addWidget(row)
            self.rows[t["key"]] = row
        self.body.addStretch(1)
        self.empty_btn = self.button(i18n.t("Start empty"), on_click=lambda: self.pick(""))
        self.footer.add_secondary(self.empty_btn)
        self.footer.set_primary(self.button(i18n.t("Cancel"), "primary", on_click=self.reject))
        self.resize(560, 640)

    def pick(self, key: str):
        self.chosen = key
        self.accept()


class PickFormDialog(PrismDialog):
    """Which published form to send."""

    def __init__(self, forms: list, who: str = "", parent=None):
        super().__init__(i18n.t("Send a form"), i18n.t("To {n}.").format(n=who) if who else "", icon="file", parent=parent)
        from PySide6.QtWidgets import QComboBox
        self.choice = QComboBox()
        self.choice.setMinimumHeight(38)
        self.choice.setAccessibleName(i18n.t("Form"))
        for f in forms:
            self.choice.addItem(f["name"], f)
        self.body.addWidget(ui.field(i18n.t("Which form"), self.choice))
        self.body.addStretch(1)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.button(i18n.t("Next"), "primary", on_click=self.accept))
        self.resize(440, 260)

    def form(self) -> dict:
        return self.choice.currentData()


class SendFormDialog(PrismDialog):
    def __init__(self, form: dict, parent=None, contact: dict = None):
        super().__init__(i18n.t("Send “{n}”").format(n=form["name"]), i18n.t("Works inside the 24 hours after the customer last wrote."), icon="send", parent=parent)
        self.form = form
        self.who = ContactChoice()
        if contact:
            self.who.set_contact(contact["id"], contact.get("name") or "")
        self.body.addWidget(ui.field(i18n.t("To"), self.who))
        self.message = QLineEdit()
        self.message.setMinimumHeight(38)
        self.message.setText(i18n.t("Please fill in this short form."))
        self.message.setAccessibleName(i18n.t("Words with it"))
        self.body.addWidget(ui.field(i18n.t("Words above the button"), self.message))
        self.button_words = QLineEdit()
        self.button_words.setMinimumHeight(38)
        self.button_words.setMaxLength(30)
        self.button_words.setText(i18n.t("Open form"))
        self.button_words.setAccessibleName(i18n.t("Button words"))
        self.body.addWidget(ui.field(i18n.t("Button words"), self.button_words))
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.go = self.button(i18n.t("Send"), "primary", on_click=self._go)
        self.footer.set_primary(self.go)
        self.resize(500, 440)

    def say(self, message: str, error: bool = False):
        (self.error.error if error else self.error.ok)(message)

    def payload(self) -> dict:
        return {"form_id": self.form["id"], "contact_id": self.who.contact_id(), "body": self.message.text().strip(), "button": self.button_words.text().strip()}

    def _go(self):
        if not self.who.contact_id():
            self.error.error(i18n.t("Choose who to send it to."))
            return
        self.go.setEnabled(False)
        ui.call(self, "forms/send", self.payload(), done=lambda _r: self.accept(), failed=self._failed)

    def _failed(self, message: str, _detail: dict):
        self.go.setEnabled(True)
        self.error.error(message)


class ResponsesDialog(PrismDialog):
    """What customers filled in."""

    def __init__(self, form: dict, parent=None):
        super().__init__(i18n.t("Answers to “{n}”").format(n=form["name"]), "", icon="list", parent=parent, scrollable=True)
        self.form = form
        self.rows = QVBoxLayout()
        self.rows.setSpacing(theme.SPACE_2)
        self.body.addLayout(self.rows)
        self.body.addStretch(1)
        self.footer.add_secondary(self.button(i18n.t("Download as a spreadsheet"), on_click=self.export))
        self.footer.set_primary(self.button(i18n.t("Close"), "primary", on_click=self.accept))
        self.resize(640, 620)
        self.error = ui.note()
        self.body.addWidget(self.error)
        ui.call(self, "forms/responses", {"form_id": form["id"]}, done=self._loaded)

    def say(self, message: str, error: bool = False):
        (self.error.error if error else self.error.ok)(message)

    def _loaded(self, reply: dict):
        ui.clear(self.rows)
        rows = list(reply.get("responses") or [])
        self.count = len(rows)
        if not rows:
            self.rows.addWidget(C.label(i18n.t("Nobody has filled this in yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for r in rows:
            card = QFrame()
            card.setObjectName("waAnswer")
            card.setAttribute(Qt.WA_StyledBackground, True)
            card.setStyleSheet(f"#waAnswer {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
            col = QVBoxLayout(card)
            col.setContentsMargins(14, 10, 14, 10)
            col.setSpacing(2)
            who = r.get("contact_name") or (r.get("answers") or {}).get("name") or i18n.t("Unknown")
            col.addWidget(C.label("%s  ·  %s" % (who, (r.get("created_at") or "")[:16].replace("T", " ")), level="SUPPORT", weight=700))
            for k, v in (r.get("answers") or {}).items():
                col.addWidget(C.label("%s:  %s" % (k, ", ".join(v) if isinstance(v, list) else v), level="META", colour=theme.NEUTRAL[700], wrap=True))
            self.rows.addWidget(card)

    def export(self):
        ui.call(self, "forms/export", {"form_id": self.form["id"]}, done=self._export)

    def _export(self, reply: dict):
        path, _ = QFileDialog.getSaveFileName(self, i18n.t("Save the answers"), "answers.csv", "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(reply["csv"])
            self.say(i18n.t("Saved."))


class _FormRow(QFrame):
    def __init__(self, f: dict, page: "FormsPage"):
        super().__init__()
        self.form = f
        self.setObjectName("waForm")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#waForm {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 12, 14, 10)
        col.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(theme.SPACE_2)
        top.addWidget(C.label(f["name"], level="SUPPORT", weight=700), 1)
        if f.get("endpoint"):
            top.addWidget(C.Pill(i18n.t("Live times"), "info"))
        top.addWidget(status_pill(f["status"]))
        col.addLayout(top)
        facts = [size_words(f["screens_count"], f["fields_count"]), answers_words(f.get("responses", 0))]
        col.addWidget(C.label("  ·  ".join(facts), level="META", colour=theme.NEUTRAL[600]))
        if f.get("problems"):
            col.addWidget(C.label(i18n.t("Meta said: {m}").format(m=f["problems"][0].get("message", "")), level="META", colour=theme.ERR_INK, wrap=True))
        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACE_1)
        actions.addStretch(1)
        if f["status"] == "published":
            actions.addWidget(C.button(i18n.t("Send…"), "secondary", on_click=lambda: page.send(f)))
            actions.addWidget(C.button(i18n.t("Answers"), "tertiary", on_click=lambda: page.answers(f)))
            actions.addWidget(C.button(i18n.t("Retire"), "tertiary", on_click=lambda: page.retire(f)))
        elif f.get("responses"):
            actions.addWidget(C.button(i18n.t("Answers"), "tertiary", on_click=lambda: page.answers(f)))
        actions.addWidget(C.button(i18n.t("Copy"), "tertiary", on_click=lambda: page.duplicate(f)))
        actions.addWidget(C.button(i18n.t("Edit"), "secondary", on_click=lambda: page.edit(f)))
        actions.addWidget(C.button(i18n.t("Delete"), "tertiary", on_click=lambda: page.delete(f)))
        col.addLayout(actions)


class FormsPage(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.editor: FormEditor = None
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SPACE_4, theme.SPACE_4, theme.SPACE_4, theme.SPACE_4)
        root.setSpacing(theme.SPACE_3)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(C.label(i18n.t("Forms"), level="CARD_TITLE"))
        titles.addWidget(C.label(i18n.t("A form opens inside the chat. Customers fill it in without leaving WhatsApp, and you get their answers as a tidy list."), level="SUPPORT",
                                 colour=theme.NEUTRAL[600], wrap=True))
        head.addLayout(titles, 1)
        self.new_btn = C.button(i18n.t("New form"), "primary", icon_name="plus", on_click=self.new)
        head.addWidget(self.new_btn)
        root.addLayout(head)
        self.note = ui.note()
        root.addWidget(self.note)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        host = QWidget()
        ui.see_through(host)
        self.rows = QVBoxLayout(host)
        self.rows.setContentsMargins(0, 0, theme.SPACE_2, 0)
        self.rows.setSpacing(theme.SPACE_2)
        scroll.setWidget(host)
        self.stack.addWidget(scroll)
        self.empty = C.EmptyState("file", i18n.t("No forms yet"), i18n.t("Start from a ready form: enquiries, booking a visit, feedback, a quotation."), i18n.t("New form"))
        self.empty.clicked.connect(self.new)
        self.stack.addWidget(self.empty)
        self.state_kind = "loading"

    def say(self, text: str, error: bool = False):
        self.note.set(text, "error" if error else "ok")

    # ── lifecycle ────────────────────────────────────────────────────────────
    def activate(self):
        if self.editor is None:
            self.load()

    def deactivate(self):
        pass

    def load(self):
        ui.call(self, "forms/list", {}, done=self._loaded, failed=self._load_failed)

    def _load_failed(self, message: str, _detail: dict):
        self.say(message, error=True)

    def _loaded(self, reply: dict):
        forms = list(reply.get("forms") or [])
        ui.clear(self.rows)
        for f in forms:
            self.rows.addWidget(_FormRow(f, self))
        self.rows.addStretch(1)
        self.stack.setCurrentIndex(0 if forms else 1)
        self.forms = forms

    # ── actions ──────────────────────────────────────────────────────────────
    def new(self):
        ui.call(self, "forms/templates", {}, done=lambda r: self._pick(r["templates"]))

    def _pick(self, templates: list):
        dlg = NewFormDialog(templates, self)
        if not dlg.exec() or dlg.chosen is None:
            return
        data = {"template": dlg.chosen} if dlg.chosen else {"name": i18n.t("New form"), "screens": [{"id": "SCREEN_A", "title": i18n.t("Your details"), "button": i18n.t("Send"), "texts": [], "fields": []}]}
        ui.call(self, "forms/create", data, done=lambda r: (self.load(), self.edit(r["form"])))

    def edit(self, form: dict):
        ui.call(self, "forms/get", {"form_id": form["id"]}, done=lambda r: self._edit(r["form"]))

    def _edit(self, form: dict):
        if self.editor is not None:
            self._close_editor()
        self.editor = FormEditor(form, self)
        self.editor.closed.connect(self._close_editor)
        self.editor.saved.connect(lambda _f: self.load())
        self.stack.addWidget(self.editor)
        self.stack.setCurrentWidget(self.editor)
        self.new_btn.setVisible(False)

    def _close_editor(self):
        if self.editor is not None:
            self.stack.removeWidget(self.editor)
            ui.discard(self.editor)
            self.editor = None
        self.new_btn.setVisible(True)
        self.load()

    def send(self, form: dict, contact: dict = None):
        if SendFormDialog(form, self, contact).exec():
            self.say(i18n.t("Sent."))

    def send_to(self, contact: dict):
        """From a chat or a contact: choose among the published forms, then send the one chosen to that person."""
        ui.call(self, "forms/list", {}, done=lambda r: self._pick_to_send([f for f in r.get("forms") or [] if f.get("status") == "published"], contact))

    def _pick_to_send(self, forms: list, contact: dict):
        if not forms:
            self.say(i18n.t("No form is published yet. Publish one first."), error=True)
            return
        dlg = PickFormDialog(forms, contact.get("name") or "", self)
        if dlg.exec() and dlg.form():
            self.send(dlg.form(), contact)

    def answers(self, form: dict):
        ResponsesDialog(form, self).exec()

    def duplicate(self, form: dict):
        ui.call(self, "forms/duplicate", {"form_id": form["id"]}, done=lambda r: (self.say(i18n.t("Copied.")), self.load()))

    def retire(self, form: dict):
        if not ui.confirm(self, i18n.t("Retire form"), i18n.t("Retire “{n}”? It can no longer be sent. Answers already received are kept.").format(n=form["name"])):
            return
        ui.call(self, "forms/retire", {"form_id": form["id"]}, done=lambda _r: (self.say(i18n.t("Retired.")), self.load()))

    def delete(self, form: dict):
        if not ui.confirm(self, i18n.t("Delete form"), i18n.t("Delete “{n}”? Its answers are deleted with it.").format(n=form["name"])):
            return
        ui.call(self, "forms/delete", {"form_id": form["id"]}, done=lambda _r: (self.say(i18n.t("Deleted.")), self.load()))
