"""Settings → Team & inbox, and Quick replies.

Team & inbox is where the owner decides how the inbox is run: who works it and with what role, who is available,
how a chat that needs a person is routed, what is said automatically when nobody is there, and when the business is
open. Changes to a teammate save the moment they are made; the inbox rules save together, with a Save button.

Only an owner or manager may change any of it — the server says so in words when someone else tries, and this screen
shows that message and puts the control back as it was.
"""
from __future__ import annotations

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.auto_reply import AutoReplyBlock
from addons.whatsapp.holidays import HolidaysEditor
from addons.whatsapp.media_lib import AssetField
from addons.whatsapp.settings import _COLUMN, _scrolled
from dialogs.base import PrismDialog
from widgets import controls as C

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ZONES = ("Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York", "Australia/Sydney", "UTC")


def _days() -> list:
    return [("mon", i18n.t("Monday")), ("tue", i18n.t("Tuesday")), ("wed", i18n.t("Wednesday")), ("thu", i18n.t("Thursday")),
            ("fri", i18n.t("Friday")), ("sat", i18n.t("Saturday")), ("sun", i18n.t("Sunday"))]


def _roles() -> list:
    return [("owner", i18n.t("Owner")), ("manager", i18n.t("Manager")), ("agent", i18n.t("Agent"))]


class HoursEditor(QWidget):
    """Working hours: which days, from when to when, in which time zone. `value()` is what the server stores."""

    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_2)
        self.always = QCheckBox(i18n.t("Always open"))
        self.always.setChecked(True)
        self.always.toggled.connect(self._toggled)
        col.addWidget(self.always)
        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(theme.SPACE_1)
        self.rows: dict = {}
        for key, label in _days():
            row = QHBoxLayout()
            on = QCheckBox(label)
            on.setMinimumWidth(130)
            start, end = QTimeEdit(QTime(9, 0)), QTimeEdit(QTime(18, 0))
            for t in (start, end):
                t.setDisplayFormat("HH:mm")
                t.setMinimumHeight(32)
            on.setChecked(key not in ("sun",))
            on.toggled.connect(lambda c, s=start, e=end: (s.setEnabled(c), e.setEnabled(c)))
            row.addWidget(on)
            row.addWidget(start)
            row.addWidget(C.label(i18n.t("to"), level="SUPPORT", colour=theme.NEUTRAL[600]))
            row.addWidget(end)
            row.addStretch(1)
            bl.addLayout(row)
            self.rows[key] = (on, start, end)
            start.setEnabled(on.isChecked())
            end.setEnabled(on.isChecked())
        self.tz = QComboBox()
        self.tz.setEditable(True)
        self.tz.addItems(ZONES)
        self.tz.setMinimumHeight(34)
        bl.addWidget(ui.field(i18n.t("Time zone"), self.tz))
        col.addWidget(self.body)
        self.body.hide()

    def _toggled(self, always: bool):
        self.body.setVisible(not always)

    def value(self):
        if self.always.isChecked():
            return None
        days = {}
        for key, (on, start, end) in self.rows.items():
            if on.isChecked():
                days[key] = [[start.time().toString("HH:mm"), end.time().toString("HH:mm")]]
        return {"tz": self.tz.currentText().strip() or "Asia/Kolkata", "days": days}

    def set_value(self, hours):
        self.always.setChecked(not hours)
        if not hours:
            return
        self.tz.setCurrentText(hours.get("tz") or "Asia/Kolkata")
        for key, (on, start, end) in self.rows.items():
            ranges = (hours.get("days") or {}).get(key) or []
            on.setChecked(bool(ranges))
            if ranges:
                start.setTime(QTime.fromString(ranges[0][0], "HH:mm"))
                end.setTime(QTime.fromString(ranges[0][1], "HH:mm"))


class HoursDialog(PrismDialog):
    def __init__(self, name: str, hours, parent=None):
        super().__init__(i18n.t("Working hours"), i18n.t("When {n} can be given new chats.").format(n=name), icon="clock", parent=parent)
        self.editor = HoursEditor()
        self.editor.set_value(hours)
        self.body.addWidget(self.editor)
        self.body.addStretch(1)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.button(i18n.t("Save"), "primary", on_click=self.accept))
        self.resize(480, 560)


class EmailDialog(PrismDialog):
    """The company e-mail a team member signs in with (single sign-on matches the provider's answer to it)."""

    def __init__(self, name: str, email: str, parent=None):
        super().__init__(i18n.t("Company e-mail"), i18n.t("{n}: the address they use to sign in with their company account.").format(n=name), icon="user", parent=parent)
        self.edit = QLineEdit(email)
        self.edit.setMinimumHeight(38)
        self.edit.setPlaceholderText("name@company.com")
        self.edit.setAccessibleName(i18n.t("Company e-mail"))
        self.body.addWidget(ui.field(i18n.t("E-mail"), self.edit, i18n.t("Leave empty to remove it.")))
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.button(i18n.t("Save"), "primary", on_click=self.accept))
        self.resize(440, 260)

    def value(self) -> str:
        return self.edit.text().strip().lower()


class AgentRulesDialog(PrismDialog):
    """Which chats an agent is given. With no rule they take any unassigned chat; with rules, only the ones that match one."""

    def __init__(self, name: str, rules, parent=None):
        super().__init__(i18n.t("Agent rules"), i18n.t("{n} is only given new chats that match one of these. With no rule, any chat can be given to them.").format(n=name),
                         icon="sliders", parent=parent, scrollable=True)
        self._start = [r for r in (rules or []) if isinstance(r, dict)]
        self._editors: list = []
        self._defs: dict = {}
        self._tags: list = []
        self.holder = QVBoxLayout()
        self.holder.setSpacing(theme.SPACE_3)
        self.body.addLayout(self.holder)
        self.add_btn = C.button(i18n.t("Add a rule"), "secondary", icon_name="plus", small=True, on_click=lambda: self._add({}))
        self.body.addWidget(self.add_btn, alignment=Qt.AlignLeft)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.button(i18n.t("Save"), "primary", on_click=self._save))
        self.resize(720, 560)
        self.holder.addWidget(C.label(i18n.t("Loading…"), level="SUPPORT", colour=theme.NEUTRAL[600]))
        ui.call(self, "attributes/list", {}, done=self._got_defs, failed=lambda m, _d: self._ready())
        ui.call(self, "tags/list", {}, done=lambda r: setattr(self, "_tags", [t["name"] for t in r.get("tags") or []]), failed=lambda m, _d: None)

    def _got_defs(self, reply: dict):
        self._defs = {a["key"]: {"type": a.get("type"), "options": a.get("options")} for a in reply.get("attributes") or []}
        self._ready()

    def _ready(self):
        ui.clear(self.holder)
        for r in self._start:
            self._add(r)

    def _add(self, rule: dict):
        from addons.whatsapp.filter_builder import FilterEditor
        card, col = ui.card("", "")
        ed = FilterEditor(self._defs, self._tags)
        ed.set_filter(rule or None)
        if not ed._rows and ed._custom is None:
            ed.add_row(silent=True)
        col.addWidget(ed)
        col.addWidget(C.button(i18n.t("Remove this rule"), "tertiary", small=True, on_click=lambda _=False, c=card, e=ed: self._remove(c, e)), alignment=Qt.AlignLeft)
        self._editors.append(ed)
        self.holder.addWidget(card)

    def _remove(self, card, ed):
        self._editors.remove(ed)
        ui.discard(card)

    def rules(self) -> list:
        from addons.whatsapp import filter_model as FM
        out = []
        for ed in self._editors:
            flt = ed.filter()
            if not FM.is_empty(flt):
                out.append(flt)
        return out

    def _save(self):
        if any(not ed.complete() for ed in self._editors):
            self.error.error(i18n.t("Finish or remove the rule that is still empty."))
            return
        self.accept()


class _AgentRow(QFrame):
    def __init__(self, agent: dict, page: "TeamSection"):
        super().__init__()
        self.agent, self.page = agent, page
        self.setObjectName("waAgent")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#waAgent {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(theme.SPACE_3)
        row.addWidget(C.Avatar(agent.get("name") or "?", 34, theme.NEUTRAL[400]))
        who = QVBoxLayout()
        who.setSpacing(0)
        who.addWidget(C.label(agent.get("name") or "", level="SUPPORT", weight=700))
        self.email_line = C.button("", "tertiary", small=True, on_click=self._email)           # the address (or "Add e-mail"): press it to change it
        self.email_line.setStyleSheet("QPushButton { text-align: left; padding: 0px; border: none; background: transparent; font-size: 11px; color: %s; }"
                                      "QPushButton:hover { color: %s; }" % (theme.NEUTRAL[600], theme.TEXT))
        who.addWidget(self.email_line)
        self._show_email(agent.get("email"))
        row.addLayout(who, stretch=1)
        self.role = QComboBox()
        self.role.setMinimumHeight(34)
        self.role.setAccessibleName(i18n.t("Role of {n}").format(n=agent.get("name")))
        for key, label in _roles():
            self.role.addItem(label, key)
        self.role.setCurrentIndex(max(self.role.findData(agent.get("role")), 0))
        self.role.activated.connect(lambda _i: self._save({"role": self.role.currentData()}, revert=lambda: self.role.setCurrentIndex(max(self.role.findData(self.agent.get("role")), 0))))
        row.addWidget(self.role)
        row.addWidget(C.label(i18n.t("Available"), level="META", colour=theme.NEUTRAL[600]))
        self.available = C.ToggleSwitch()
        self.available.setChecked(bool(agent.get("available")))
        self.available.toggled.connect(lambda on: self._save({"available": on}, revert=lambda: self.available.setChecked(bool(self.agent.get("available")))))
        row.addWidget(self.available)
        row.addWidget(C.label(i18n.t("Hide numbers"), level="META", colour=theme.NEUTRAL[600]))
        self.masked = C.ToggleSwitch()
        self.masked.setChecked(bool(agent.get("masked")))
        self.masked.toggled.connect(lambda on: self._save({"masked": on}, revert=lambda: self.masked.setChecked(bool(self.agent.get("masked")))))
        row.addWidget(self.masked)
        row.addWidget(C.button(i18n.t("Hours"), "tertiary", on_click=self._hours))
        row.addWidget(C.button(i18n.t("Rules"), "tertiary", on_click=self._rules))

    def _save(self, changes: dict, revert):
        ui.call(self.page, "inbox/agents/update", {"agent_id": self.agent["id"], "changes": changes},
                done=lambda r, c=changes: (self.agent.update(c), self.page.say(i18n.t("Saved."), error=False)),
                failed=lambda m, _d: (self.page.say(m, error=True), self._silently(revert)))

    def _silently(self, fn):
        for w in (self.role, self.available, self.masked):
            w.blockSignals(True)
        fn()
        for w in (self.role, self.available, self.masked):
            w.blockSignals(False)

    def _rules(self):
        dlg = AgentRulesDialog(self.agent.get("name") or "", self.agent.get("rules"), self)
        if dlg.exec():
            rules = dlg.rules()
            self._save({"rules": rules}, revert=lambda: None)
            self.agent["rules"] = rules

    def _show_email(self, email):
        """The address, shortened so the row keeps its room (the whole address is the tooltip)."""
        text = email or i18n.t("Add e-mail")
        self.email_line.setText(text if len(text) <= 20 else text[:19] + "…")
        self.email_line.setToolTip(email or i18n.t("The company e-mail this person signs in with"))

    def _email(self):
        dlg = EmailDialog(self.agent.get("name") or "", self.agent.get("email") or "", self)
        if dlg.exec():
            value = dlg.value()
            ui.call(self.page, "inbox/agents/update", {"agent_id": self.agent["id"], "changes": {"email": value}},
                    done=lambda r, v=value: (self.agent.update(email=v or None), self._show_email(v), self.page.say(i18n.t("Saved."), error=False)),
                    failed=lambda m, _d: self.page.say(m, error=True))

    def _hours(self):
        dlg = HoursDialog(self.agent.get("name") or "", self.agent.get("working_hours"), self)
        if dlg.exec():
            self._save({"working_hours": dlg.editor.value()}, revert=lambda: None)
            self.agent["working_hours"] = dlg.editor.value()


class TeamSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self._rules_loaded = False

        card, tc = ui.card(i18n.t("Your team"), i18n.t("Everyone who works the inbox. Owners and managers see every chat; an agent sees "
                                                       "the chats given to them and the ones nobody has taken."), width=_COLUMN)
        self.monitor = C.label("", level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True)
        tc.addWidget(self.monitor)
        self.agents_col = QVBoxLayout()
        self.agents_col.setSpacing(theme.SPACE_2)
        tc.addLayout(self.agents_col)
        self.team_note = ui.note()
        tc.addWidget(self.team_note)
        col.addWidget(card)

        card, rc = ui.card(i18n.t("Routing and auto-replies"), width=_COLUMN)
        self.routing = QComboBox()
        self.routing.setMinimumHeight(38)
        self.routing.addItem(i18n.t("Give it to the teammate with the fewest open chats"), "least_busy")
        self.routing.addItem(i18n.t("Take turns"), "round_robin")
        self.routing.addItem(i18n.t("Nobody — people pick up chats themselves"), "manual")
        rc.addWidget(ui.field(i18n.t("When a chat needs a person"), self.routing))
        nums = QHBoxLayout()
        nums.setSpacing(theme.SPACE_4)
        self.sla = QSpinBox()
        self.sla.setRange(1, 24 * 60)
        self.sla.setSuffix(i18n.t(" min"))
        self.sla.setMinimumHeight(36)
        nums.addWidget(ui.field(i18n.t("Reply within"), self.sla, i18n.t("Chats left longer are flagged to the manager.")))
        self.resolve = QSpinBox()
        self.resolve.setRange(0, 24 * 30)
        self.resolve.setSuffix(i18n.t(" h"))
        self.resolve.setMinimumHeight(36)
        nums.addWidget(ui.field(i18n.t("Close quiet chats after"), self.resolve, i18n.t("0 means never.")))
        nums.addStretch(1)
        rc.addLayout(nums)
        self.hours = HoursEditor()
        rc.addWidget(ui.field(i18n.t("Business hours"), self.hours))
        self.holidays = HolidaysEditor()
        rc.addWidget(ui.field(i18n.t("Holidays"), self.holidays, i18n.t("Days you are closed. A flow can check “Is today a holiday?” and answer differently.")))
        self.welcome = AutoReplyBlock(self, i18n.t("Welcome message"), i18n.t("Sent to someone new while you are open."))
        rc.addWidget(self.welcome)
        self.off = AutoReplyBlock(self, i18n.t("Closed message"), i18n.t("Sent when someone writes outside your business hours."))
        rc.addWidget(self.off)
        self.welcome_on, self.welcome_text, self.welcome_every = self.welcome.switch, self.welcome.text, self.welcome.every
        self.off_on, self.off_text, self.off_every = self.off.switch, self.off.text, self.off.every
        row = QHBoxLayout()
        self.rules_note = ui.note()
        row.addWidget(self.rules_note, stretch=1)
        row.addWidget(C.button(i18n.t("Save"), "primary", on_click=self._save_rules))
        rc.addLayout(row)
        col.addWidget(card)
        col.addStretch(1)

    def say(self, text: str, error: bool = False):
        self.team_note.set(text, "error" if error else "ok")

    # ── loading ──────────────────────────────────────────────────────────────
    def activate(self):
        ui.call(self, "inbox/agents/list", done=self._agents)
        ui.call(self, "inbox/monitor", done=self._monitor, failed=lambda m, _d: self.monitor.setText(""))
        ui.call(self, "inbox/settings/get", done=self._settings, failed=lambda m, _d: self.rules_note.error(m))

    def _agents(self, reply: dict):
        ui.clear(self.agents_col)
        for a in reply.get("agents") or []:
            self.agents_col.addWidget(_AgentRow(a, self))

    def _monitor(self, reply: dict):
        m = reply.get("monitor") or {}
        states = m.get("by_state") or {}
        open_n = sum(states.get(k, 0) for k in ("active", "requesting", "intervened", "human_takeover", "new"))
        self.monitor.setText(i18n.t("{open} open chats  ·  {wait} waiting for a person  ·  {late} past the reply time").format(
            open=open_n, wait=m.get("unassigned_requests", 0), late=m.get("sla_breaches", 0)))

    def _settings(self, reply: dict):
        st = reply.get("settings") or {}
        self.routing.setCurrentIndex(max(self.routing.findData(st.get("routing")), 0))
        self.sla.setValue(int(st.get("sla_minutes") or 15))
        self.resolve.setValue(int(st.get("auto_resolve_hours") or 0))
        self.hours.set_value(st.get("business_hours"))
        self.holidays.set_value(st.get("holidays"))
        self.welcome.set_value(st.get("welcome"))
        self.off.set_value(st.get("off_hours"))
        self._rules_loaded = True

    def rules(self) -> dict:
        return {"routing": self.routing.currentData(), "sla_minutes": self.sla.value(), "auto_resolve_hours": self.resolve.value(),
                "business_hours": self.hours.value(), "holidays": self.holidays.value(),
                "welcome": self.welcome.value(), "off_hours": self.off.value()}

    def _save_rules(self):
        ui.call(self, "inbox/settings/save", {"settings": self.rules()},
                done=lambda r: self.rules_note.ok(i18n.t("Saved.")), failed=lambda m, _d: self.rules_note.error(m))


class QuickRepliesSection(QWidget):
    """Saved answers a teammate inserts into a chat by typing / and a short name."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)
        card, cc = ui.card(i18n.t("Quick replies"),
                           i18n.t("Answers you give again and again. In a chat, choose Quick replies and pick one — {{first_name}} "
                                  "and {{name}} are filled in for the person you are talking to."), width=_COLUMN)
        self.list_col = QVBoxLayout()
        self.list_col.setSpacing(theme.SPACE_2)
        cc.addLayout(self.list_col)
        col.addWidget(card)

        card, fc = ui.card(i18n.t("Add or change a quick reply"), width=_COLUMN)
        self.shortcut = QLineEdit()
        self.shortcut.setPlaceholderText(i18n.t("A short name, like thanks or hours"))
        self.shortcut.setMinimumHeight(38)
        self.shortcut.setMaxLength(31)
        fc.addWidget(ui.field(i18n.t("Name"), self.shortcut, i18n.t("Lowercase letters, numbers, - and _.")))
        self.body = QPlainTextEdit()
        self.body.setPlaceholderText(i18n.t("The message"))
        self.body.setFixedHeight(96)
        fc.addWidget(ui.field(i18n.t("Message"), self.body))
        self.asset = AssetField(empty_text=i18n.t("No file — words only"))
        fc.addWidget(ui.field(i18n.t("File"), self.asset, i18n.t("A picture, video, voice note or document sent with it. With a file, the words are its caption.")))
        row = QHBoxLayout()
        self.note = ui.note()
        row.addWidget(self.note, stretch=1)
        self.save_btn = C.button(i18n.t("Save quick reply"), "primary", on_click=self._save)
        row.addWidget(self.save_btn)
        fc.addLayout(row)
        col.addWidget(card)
        col.addStretch(1)

    def say(self, text: str, error: bool = False):
        self.note.set(text, "error" if error else "ok")

    def activate(self):
        ui.call(self, "inbox/canned/list", done=self._loaded)

    def _loaded(self, reply: dict):
        ui.clear(self.list_col)
        rows = reply.get("canned") or []
        if not rows:
            self.list_col.addWidget(C.label(i18n.t("Nothing saved yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for c in rows:
            line = QFrame()
            line.setObjectName("waCanned")
            line.setAttribute(Qt.WA_StyledBackground, True)
            line.setStyleSheet(f"#waCanned {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
            rl = QHBoxLayout(line)
            rl.setContentsMargins(14, 10, 10, 10)
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(C.label("/" + c["shortcut"], level="SUPPORT", weight=700))
            if c.get("body"):
                text.addWidget(C.label(c["body"], level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True))
            if c.get("asset_name"):
                text.addWidget(C.label(i18n.t("File: {n}").format(n=c["asset_name"]), level="META", colour=theme.NEUTRAL[600]))
            rl.addLayout(text, stretch=1)
            rl.addWidget(C.button(i18n.t("Edit"), "tertiary", on_click=lambda _=False, x=c: self._edit(x)))
            rl.addWidget(C.icon_button("trash", i18n.t("Delete this quick reply"), on_click=lambda _=False, x=c: self._delete(x), colour=theme.ERR_INK))
            self.list_col.addWidget(line)

    def _edit(self, c: dict):
        self.shortcut.setText(c["shortcut"])
        self.body.setPlainText(c["body"])
        self.asset.set_asset_id(c.get("asset_id"))
        self.body.setFocus()

    def _save(self):
        ui.call(self, "inbox/canned/save", {"shortcut": self.shortcut.text(), "body": self.body.toPlainText(), "asset_id": self.asset.asset_id()},
                done=lambda r: (self.say(i18n.t("Saved."), False), self.shortcut.clear(), self.body.clear(), self.asset.clear(), self.activate()))

    def _delete(self, c: dict):
        if ui.confirm(self, i18n.t("Delete quick reply"), i18n.t("Delete /{s}?").format(s=c["shortcut"])):
            ui.call(self, "inbox/canned/delete", {"shortcut": c["shortcut"]}, done=lambda r: self.activate())
