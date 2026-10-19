"""Ads → Audiences and Suggestions.

Audiences are lists of people in your Meta ad account, made from a Prism segment (only people who have opted in, and only a scrambled form of their phone number leaves
Prism — never the number) or from another list ("look-alikes": people like them, in one country, as close as you choose). An ad can be shown to a list, or can leave one out.

Suggestions are "pause this" and "put more into that", worked out from the last seven days' numbers by plain rules, each with its reason. Nothing happens until you say yes.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.chat import short_time
from dialogs.base import PrismDialog
from widgets import controls as C


class FromSegmentDialog(PrismDialog):
    def __init__(self, segments: list, parent=None):
        super().__init__(i18n.t("Make a people list from a segment"), i18n.t("Only people who opted in are sent, and only as a scrambled code — never their numbers."), icon="users", parent=parent)
        self.segment = QComboBox()
        self.segment.setMinimumHeight(38)
        self.segment.setAccessibleName(i18n.t("Segment"))
        self.segment.addItem(i18n.t("Choose a segment"), None)
        for s in segments:
            self.segment.addItem("%s%s" % (s.get("name") or "", (" · %s" % s["size"]) if s.get("size") else ""), s.get("id"))
        self.body.addWidget(ui.field(i18n.t("Segment"), self.segment, i18n.t("Meta needs at least 100 people with a phone number to use a list.")))
        self.name = QLineEdit()
        self.name.setMinimumHeight(38)
        self.name.setAccessibleName(i18n.t("Name"))
        self.name.setPlaceholderText(i18n.t("A name for the list, optional"))
        self.body.addWidget(ui.field(i18n.t("Name"), self.name))
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.button(i18n.t("Send the list to Meta"), "primary", on_click=self._go))
        self.resize(480, 380)

    def _go(self):
        if not self.segment.currentData():
            self.error.error(i18n.t("Choose a segment first."))
            return
        self.accept()


class LookalikeDialog(PrismDialog):
    def __init__(self, source_name: str, parent=None):
        super().__init__(i18n.t("People like “{n}”").format(n=source_name), i18n.t("Meta finds people who resemble the people in the list, in one country."), icon="users", parent=parent)
        self.country = QLineEdit("IN")
        self.country.setMinimumHeight(38)
        self.country.setMaxLength(2)
        self.country.setAccessibleName(i18n.t("Country"))
        self.body.addWidget(ui.field(i18n.t("Country"), self.country, i18n.t("A two-letter country code, like IN.")))
        self.ratio = QDoubleSpinBox()
        self.ratio.setRange(1, 20)
        self.ratio.setValue(1)
        self.ratio.setSuffix(" %")
        self.ratio.setDecimals(0)
        self.ratio.setMinimumHeight(38)
        self.ratio.setAccessibleName(i18n.t("Closeness"))
        self.body.addWidget(ui.field(i18n.t("How wide"), self.ratio, i18n.t("1% is the people most like your list; 20% is a much bigger, looser group.")))
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.button(i18n.t("Make it"), "primary", on_click=self._go))
        self.resize(460, 380)

    def value(self) -> dict:
        return {"country": self.country.text().strip().upper(), "ratio": round(self.ratio.value() / 100.0, 2)}

    def _go(self):
        if len(self.value()["country"]) != 2:
            self.error.error(i18n.t("A country is two letters, like IN."))
            return
        self.accept()


def _row(title: str) -> tuple:
    line = QFrame()
    line.setObjectName("waAdRow")
    line.setAttribute(Qt.WA_StyledBackground, True)
    line.setStyleSheet(f"#waAdRow {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
    col = QVBoxLayout(line)
    col.setContentsMargins(14, 10, 10, 10)
    col.setSpacing(2)
    top = QHBoxLayout()
    top.addWidget(C.label(title, level="SUPPORT", weight=700, wrap=True), 1)
    col.addLayout(top)
    return line, col, top


class AudiencesView(QWidget):
    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.audiences: list = []
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_2)
        row = QHBoxLayout()
        row.addWidget(C.label(i18n.t("Lists of people your ads can be shown to — or kept away from."), level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True), 1)
        self.make_btn = C.button(i18n.t("From a segment"), "primary", icon_name="plus", on_click=self.from_segment)
        row.addWidget(self.make_btn)
        col.addLayout(row)
        self.note = ui.note()
        col.addWidget(self.note)
        self.list_col = QVBoxLayout()
        self.list_col.setSpacing(theme.SPACE_2)
        col.addLayout(self.list_col)
        col.addStretch(1)

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def load(self):
        ui.call(self, "audiences/list", {}, done=self._loaded, failed=lambda m, _d: self.note.error(m))

    def _loaded(self, reply: dict):
        self.audiences = list(reply.get("audiences") or [])
        ui.clear(self.list_col)
        if not self.audiences:
            self.list_col.addWidget(C.label(i18n.t("No lists yet. Make one from a segment of your contacts."), level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
        for a in self.audiences:
            line, col, top = _row(a.get("name") or "")
            top.addWidget(C.Pill(i18n.t("People like a list") if a.get("kind") == "lookalike" else i18n.t("From a segment"), "neutral"))
            if a.get("kind") == "segment":
                top.addWidget(C.button(i18n.t("Find people like them"), "tertiary", small=True, on_click=lambda _=False, x=a: self.lookalike(x)))
            top.addWidget(C.icon_button("trash", i18n.t("Remove this list"), on_click=lambda _=False, x=a: self.remove(x), colour=theme.ERR_INK))
            src = a.get("source") or {}
            facts = []
            if a.get("size"):
                facts.append(i18n.t("{n} people sent").format(n="{:,}".format(int(a["size"]))))
            if a.get("kind") == "lookalike":
                facts.append(i18n.t("{c}, {r}% wide").format(c=src.get("country"), r=round(float(src.get("ratio") or 0) * 100)))
            facts.append(i18n.t("made {t}").format(t=short_time(a.get("created_at") or "")))
            col.addWidget(C.label("  ·  ".join(facts), level="META", colour=theme.NEUTRAL[600]))
            self.list_col.addWidget(line)

    def from_segment(self):
        account = self.page.account_id()
        if not account:
            self.say(i18n.t("Connect an ad account first."), error=True)
            return
        ui.call(self, "segments/list", {}, done=lambda r: self._pick(r, account), failed=lambda m, _d: self.say(m, error=True))

    def _pick(self, reply: dict, account: str):
        dlg = FromSegmentDialog(list(reply.get("segments") or []), self.page)
        if dlg.exec():
            self.make_btn.setEnabled(False)
            ui.call(self, "audiences/from_segment", {"account_id": account, "segment_id": dlg.segment.currentData(), "name": dlg.name.text().strip()},
                    done=lambda r: (self.make_btn.setEnabled(True), self.say(i18n.t("Sent {n} people to Meta. It can take a while before Meta can use the list.").format(n=r.get("sent", 0))), self.load()),
                    failed=lambda m, _d: (self.make_btn.setEnabled(True), self.say(m, error=True)))

    def lookalike(self, audience: dict):
        dlg = LookalikeDialog(audience.get("name") or "", self.page)
        if dlg.exec():
            ui.call(self, "audiences/lookalike", {"account_id": audience["account_id"], "audience_id": audience["id"], **dlg.value()},
                    done=lambda r: (self.say(i18n.t("Made “{n}”.").format(n=r.get("name"))), self.load()), failed=lambda m, _d: self.say(m, error=True))

    def remove(self, audience: dict):
        if ui.confirm(self, i18n.t("Remove this list"), i18n.t("Remove “{n}” from Prism and from your Meta ad account? Ads that use it will lose it.").format(n=audience.get("name"))):
            ui.call(self, "audiences/delete", {"audience_id": audience["id"]}, done=lambda r: (self.say(i18n.t("Removed.")), self.load()), failed=lambda m, _d: self.say(m, error=True))


class SuggestionsView(QWidget):
    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.items: list = []
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_2)
        row = QHBoxLayout()
        row.addWidget(C.label(i18n.t("What to change, from the last seven days. Nothing happens until you say yes."), level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True), 1)
        self.look_btn = C.button(i18n.t("Look at my ads now"), "secondary", on_click=self.look)
        row.addWidget(self.look_btn)
        col.addLayout(row)
        self.note = ui.note()
        col.addWidget(self.note)
        self.list_col = QVBoxLayout()
        self.list_col.setSpacing(theme.SPACE_2)
        col.addLayout(self.list_col)
        col.addStretch(1)

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def load(self):
        ui.call(self, "ads/suggestions", {}, done=lambda r: self._shown(r.get("suggestions") or []), failed=lambda m, _d: self.note.error(m))

    def look(self):
        self.look_btn.setEnabled(False)
        ui.call(self, "ads/suggest", {}, done=lambda r: (self.look_btn.setEnabled(True), self._shown(r.get("suggestions") or []),
                                                        self.say(i18n.t("Looked at your running ads.") if r.get("suggestions") else i18n.t("Nothing to change right now."))),
                failed=lambda m, _d: (self.look_btn.setEnabled(True), self.say(m, error=True)))

    def _shown(self, items: list):
        self.items = list(items)
        self.page.suggestion_count(len(self.items))
        ui.clear(self.list_col)
        if not self.items:
            self.list_col.addWidget(C.label(i18n.t("No suggestions. Press “Look at my ads now” after an ad has been running for a few days."), level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
        for s in self.items:
            title = {"pause": i18n.t("Pause “{n}”"), "budget_up": i18n.t("Spend more on “{n}”"), "budget_down": i18n.t("Spend less on “{n}”"),
                     "new_creative": i18n.t("Try a new picture or first line for “{n}”")}.get(s.get("kind"), "{n}").format(n=s.get("ad_name"))
            line, col, top = _row(title)
            yes = {"pause": i18n.t("Pause it"), "budget_up": i18n.t("Raise the budget"), "budget_down": i18n.t("Lower the budget"), "new_creative": i18n.t("Done")}.get(s.get("kind"), i18n.t("Yes"))
            top.addWidget(C.button(yes, "secondary", small=True, on_click=lambda _=False, x=s: self.decide(x, True)))
            top.addWidget(C.button(i18n.t("Not now"), "tertiary", small=True, on_click=lambda _=False, x=s: self.decide(x, False)))
            col.addWidget(C.label(s.get("reason") or "", level="META", colour=theme.NEUTRAL[700], wrap=True))
            if s.get("kind") in ("budget_up", "budget_down") and s.get("params"):
                col.addWidget(C.label(i18n.t("A day: Rs {a} to Rs {b}").format(a="{:,.0f}".format(s["params"]["from"] / 100), b="{:,.0f}".format(s["params"]["to"] / 100)), level="META", colour=theme.NEUTRAL[600]))
            self.list_col.addWidget(line)

    def decide(self, s: dict, apply: bool):
        ui.call(self, "ads/decide", {"suggestion_id": s["id"], "apply": apply}, done=lambda r: (self.say(i18n.t("Done.") if apply else i18n.t("Left as it is.")), self.load(), self.page.activate_ads()),
                failed=lambda m, _d: self.say(m, error=True))
