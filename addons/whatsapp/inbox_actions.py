"""What a teammate can do with one chat: see who has it, take it, hand it back to the bot, pass it on, resolve it, keep notes.

A chat is in one of four states (the server decides which; this only shows it and asks for changes):

    not taken     the customer is chatting and nobody has stepped in — a flow or AI agent may be answering
    needs a person  the customer, or a bot, asked for someone and nobody has picked it up yet
    with someone  a teammate owns it; the bots stay out of it
    resolved      closed; a new message from the customer reopens it

Every button is one call to the server, and the server is the one that says no — an agent cannot take a chat another agent has,
and the reason is shown in words. The bar disappears quietly on a server that does not have the team inbox, so the plain inbox
keeps working.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMenu, QPlainTextEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.chat import short_time
from dialogs.base import PrismDialog
from widgets import controls as C

OPEN_STATES = ("new", "active", "requesting", "intervened", "human_takeover")
OWNED = ("intervened", "human_takeover")


def state_words(state: dict, agents: list, me: str) -> tuple:
    """(words, tone) for a chat's state."""
    status = (state or {}).get("status") or "active"
    if status in OWNED:
        owner = next((a for a in agents if str(a.get("id")) == str((state or {}).get("assignee_id"))), None)
        who = i18n.t("you") if owner and str(owner.get("id")) == str(me) else ((owner or {}).get("name") or i18n.t("a teammate"))
        return i18n.t("With {who}").format(who=who), "info"
    if status == "requesting":
        return i18n.t("Needs a person"), "warn"
    if status == "closed":
        return i18n.t("Resolved"), "quiet"
    return i18n.t("Not taken"), "quiet"


class NotesDialog(PrismDialog):
    """Private notes on a chat. Customers never see them."""

    def __init__(self, conversation_id: str, who: str, parent=None):
        super().__init__(i18n.t("Notes"), i18n.t("About {w}. Only your team sees these.").format(w=who), icon="file-text", parent=parent, scrollable=True)
        self.cid = conversation_id
        self.list = QVBoxLayout()
        self.list.setSpacing(theme.SPACE_2)
        self.body.addLayout(self.list)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText(i18n.t("Write a note for your team"))
        self.edit.setFixedHeight(90)
        self.edit.setAccessibleName(i18n.t("New note"))
        self.body.addWidget(self.edit)
        self.note = ui.note()
        self.body.addWidget(self.note)
        self.body.addStretch(1)
        self.add_btn = self.button(i18n.t("Add note"), "primary", on_click=self._add)
        self.footer.add_secondary(self.button(i18n.t("Close"), on_click=self.accept))
        self.footer.set_primary(self.add_btn)
        self.resize(480, 560)
        self.count = 0
        self.load()

    def say(self, text: str, error: bool = False):
        self.note.set(text, "error" if error else "quiet")

    def load(self):
        ui.call(self, "inbox/notes/list", {"conversation_id": self.cid}, done=self._loaded)

    def _loaded(self, reply: dict):
        ui.clear(self.list)
        notes = reply.get("notes") or []
        self.count = len(notes)
        if not notes:
            self.list.addWidget(C.label(i18n.t("No notes yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for n in notes:
            box = QFrame()
            box.setObjectName("waNote")
            box.setAttribute(Qt.WA_StyledBackground, True)
            box.setStyleSheet(f"#waNote {{ background: {theme.WARN_BG}; border-radius: {theme.R_CONTROL}px; }}")
            col = QVBoxLayout(box)
            col.setContentsMargins(12, 10, 12, 10)
            col.setSpacing(2)
            col.addWidget(C.label(n.get("text") or "", level="SUPPORT", wrap=True))
            col.addWidget(C.label("%s · %s" % (n.get("agent") or i18n.t("Someone"), short_time(n.get("at") or "")), level="META", colour=theme.NEUTRAL[600]))
            self.list.addWidget(box)

    def _add(self):
        text = self.edit.toPlainText().strip()
        if not text:
            return
        self.add_btn.setEnabled(False)
        ui.call(self, "inbox/notes/add", {"conversation_id": self.cid, "text": text},
                done=lambda r: (self.edit.clear(), self.add_btn.setEnabled(True), self.load()),
                failed=lambda m, _d: (self.add_btn.setEnabled(True), self.say(m, error=True)))


class ConversationBar(QFrame):
    """The strip under a chat's header."""
    changed = Signal()                  # an action finished: refresh the chat and the list
    problem = Signal(str)               # the server said no: show it where the page shows messages

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("waConvBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#waConvBar {{ border-bottom: 1px solid {theme.HAIRLINE}; background: rgba(0,0,0,0.02); }}")
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(theme.SPACE_5, theme.SPACE_2, theme.SPACE_4, theme.SPACE_2)
        self.row.setSpacing(theme.SPACE_2)
        self.pill = C.Pill("", "quiet")
        self.row.addWidget(self.pill)
        self.row.addStretch(1)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(theme.SPACE_1)
        self.row.addLayout(self.buttons)
        self.cid, self.who, self.notes_btn = "", "", None
        self.agents: list = []
        self.me = ""
        self.hide()

    def show_for(self, row: dict, state: dict, agents: list, me: str):
        self.cid, self.who = str(row.get("id") or ""), row.get("contact_name") or row.get("contact_phone") or ""
        self.agents, self.me = agents, me
        words, tone = state_words(state, agents, me)
        self.pill.setText(words)
        self.pill.set_tone(tone)
        ui.clear(self.buttons)
        status = (state or {}).get("status") or "active"
        quiet = not (state or {}).get("window_open", True) and status in ("new", "active")      # History: nothing to take over
        if quiet:
            pass
        elif status in ("new", "active", "requesting"):
            self.buttons.addWidget(C.button(i18n.t("Take over"), "secondary", small=True, on_click=lambda: self._act("inbox/intervene", i18n.t("You have this chat."))))
            self.buttons.addWidget(C.button(i18n.t("Resolve"), "tertiary", on_click=lambda: self._act("inbox/resolve", i18n.t("Resolved."))))
        elif status in OWNED:
            self.buttons.addWidget(C.button(i18n.t("Hand back to the bot"), "secondary", small=True, on_click=lambda: self._act("inbox/hand_back", i18n.t("The bot has this chat again."))))
            self.buttons.addWidget(C.button(i18n.t("Transfer…"), "tertiary", on_click=self._transfer))
            self.buttons.addWidget(C.button(i18n.t("Resolve"), "tertiary", on_click=lambda: self._act("inbox/resolve", i18n.t("Resolved."))))
        self.notes_btn = C.button(i18n.t("Notes"), "tertiary", icon_name="file-text", on_click=self._notes)
        self.buttons.addWidget(self.notes_btn)
        self.show()

    def _act(self, route: str, done_text: str, extra: dict = None):
        data = {"conversation_id": self.cid, **(extra or {})}
        ui.call(self, route, data, done=lambda r: self.changed.emit(), failed=lambda m, _d: self.problem.emit(m))

    def _transfer(self):
        menu = QMenu(self)
        others = [a for a in self.agents if str(a.get("id")) != str(self.me) and a.get("active", True)]
        if not others:
            self.problem.emit(i18n.t("There is nobody else on your team to give it to."))
            return
        for a in others:
            label = a.get("name") or i18n.t("A teammate")
            if not a.get("available", True):
                label += i18n.t(" (away)")
            menu.addAction(label).triggered.connect(lambda _=False, x=a: self._act("inbox/transfer", "", {"to_agent_id": x["id"]}))
        menu.exec(self.mapToGlobal(self.rect().bottomRight()))

    def _notes(self):
        NotesDialog(self.cid, self.who, self).exec()

    def say(self, text: str, error: bool = False):
        if error:
            self.problem.emit(text)


class QuickReplyButton(QWidget):
    """A button beside the composer that offers the saved replies and puts the chosen one in the box."""
    chosen = Signal(str, object)                # the words, and the file it carries (a dict) or None

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.btn = C.icon_button("sparkles", i18n.t("Quick replies"), on_click=self._menu, colour=theme.NEUTRAL[600])
        lay.addWidget(self.btn)
        self.canned: list = []
        self.contact_id = ""

    def load(self):
        ui.call(self, "inbox/canned/list", done=lambda r: setattr(self, "canned", r.get("canned") or []), failed=lambda m, _d: None)

    def _menu(self):
        menu = QMenu(self)
        if not self.canned:
            a = menu.addAction(i18n.t("No quick replies yet — add them in Settings"))
            a.setEnabled(False)
        for c in self.canned:
            body = " ".join((c.get("body") or "").split()) or (c.get("asset_name") or "")
            act = menu.addAction("/%s   %s" % (c["shortcut"], body[:60] + ("…" if len(body) > 60 else "")))
            act.triggered.connect(lambda _=False, x=c: self._pick(x))
        menu.exec(self.btn.mapToGlobal(self.btn.rect().topLeft()))

    def _pick(self, canned: dict):
        ui.call(self, "inbox/canned/expand", {"shortcut": canned["shortcut"], "contact_id": self.contact_id},
                done=lambda r: self.chosen.emit(r.get("text") or "", r.get("asset") or None),
                failed=lambda m, _d: self.chosen.emit(canned.get("body") or "", None))
