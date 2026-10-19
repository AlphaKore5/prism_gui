"""Results: how an AI agent is doing, and what it could not answer.

The numbers are what the server counted while the agent was live — replies, the chats it took, how many of those it settled without a person, how many it handed over and
why. "Settled without a person" is not "the customer was happy": it only means nobody had to step in. The list underneath is the useful part: every question the
agent could not answer, most asked first. Write the answer and it becomes a question-and-answer note the agent uses from then on.
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.analytics_page import count_text, range_choices, range_for
from addons.whatsapp.chat import short_time
from addons.whatsapp.flow_results import RunsChart
from dialogs.base import PrismDialog
from widgets import controls as C


class TeachDialog(PrismDialog):
    """Write the answer to a question the agent could not answer."""

    def __init__(self, question: str, parent=None):
        super().__init__(i18n.t("Teach it the answer"), i18n.t("This becomes a question and its answer the agent uses from now on."), icon="sparkles", parent=parent)
        self.body.addWidget(C.label(question, level="SUPPORT", weight=700, wrap=True))
        self.answer = QPlainTextEdit()
        self.answer.setFixedHeight(130)
        self.answer.setAccessibleName(i18n.t("Answer"))
        self.answer.setPlaceholderText(i18n.t("The answer you want given"))
        self.body.addWidget(ui.field(i18n.t("The answer"), self.answer))
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.button(i18n.t("Teach it"), "primary", on_click=self._go))
        self.resize(520, 380)

    def _go(self):
        if not self.answer.toPlainText().strip():
            self.error.error(i18n.t("Write the answer first."))
            return
        self.accept()


class ResultsSection(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self._range = "30"
        self._token = 0
        self.data: dict = {}
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_3)

        # the allowance (kept under the names the rest of the screen knows it by)
        self.usage_card, uc = ui.card(i18n.t("This month"))
        self.usage_text = C.label("", level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True)
        uc.addWidget(self.usage_text)
        self.usage_bar = C.ProgressBar(0.0, hue=theme.ACCENT)
        uc.addWidget(self.usage_bar)
        col.addWidget(self.usage_card)

        head = QHBoxLayout()
        head.addWidget(C.label(i18n.t("How it is doing"), level="CARD_TITLE"), stretch=1)
        col.addLayout(head)
        self.chips = C.FilterChips(range_choices()[:3], "30")
        self.chips.setMinimumWidth(340)
        self.chips.changed.connect(self._set_range)
        col.addWidget(self.chips)
        self.note = ui.note()
        col.addWidget(self.note)
        grid = QGridLayout()
        grid.setSpacing(theme.SPACE_2)
        self.k_replies = C.MetricCard(i18n.t("Replies"), "—", icon="send")
        self.k_chats = C.MetricCard(i18n.t("Chats it took"), "—", icon="chat")
        self.k_settled = C.MetricCard(i18n.t("Settled without a person"), "—", icon="check")
        self.k_handed = C.MetricCard(i18n.t("Handed to a person"), "—", icon="user")
        self.k_actions = C.MetricCard(i18n.t("Actions run"), "—", icon="code")
        self.k_skills = C.MetricCard(i18n.t("Skills finished"), "—", icon="sparkles")
        for i, k in enumerate((self.k_replies, self.k_chats, self.k_settled, self.k_handed, self.k_actions, self.k_skills)):
            grid.addWidget(k, i // 3, i % 3)
        col.addLayout(grid)
        self.explain = C.label("", level="META", colour=theme.NEUTRAL[600], wrap=True)
        col.addWidget(self.explain)
        col.addWidget(C.label(i18n.t("Replies each day"), level="SUPPORT", weight=700))
        self.chart = RunsChart()
        col.addWidget(self.chart)
        col.addWidget(C.label(i18n.t("Why chats were handed over"), level="SUPPORT", weight=700))
        self.reasons_col = QVBoxLayout()
        self.reasons_col.setSpacing(2)
        col.addLayout(self.reasons_col)

        card, gc = ui.card(i18n.t("Questions it could not answer"), i18n.t("The ones customers asked most come first. Teach it, or ignore the ones that do not matter."))
        self.gaps_col = QVBoxLayout()
        self.gaps_col.setSpacing(theme.SPACE_2)
        gc.addLayout(self.gaps_col)
        self.gaps_note = ui.note()
        gc.addWidget(self.gaps_note)
        col.addWidget(card)
        col.addStretch(1)

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def show_usage(self, usage: dict):
        if not usage:
            self.usage_card.hide()
            return
        self.usage_card.show()
        used, limit = int(usage.get("replies") or 0), usage.get("limit")
        if not usage.get("configured"):
            self.usage_text.setText(i18n.t("AI replies are not switched on for this server yet, so an agent hands every chat to your team. Ask Alphakore to switch them on."))
            self.usage_bar.hide()
            return
        self.usage_bar.show()
        if limit:
            self.usage_text.setText(i18n.t("{u} of {l} AI replies used this month.").format(u=used, l=limit))
            self.usage_bar.set_fraction(min(used / limit, 1.0))
        else:
            self.usage_text.setText(i18n.t("{u} AI replies this month — no limit on your plan.").format(u=used))
            self.usage_bar.hide()

    # ── loading ──────────────────────────────────────────────────────────────
    def load(self):
        self._token += 1
        token = self._token
        since, until = range_for(self._range, datetime.now(timezone.utc))
        ui.call(self.editor, "ai/analytics", {"agent_id": self.editor.agent["id"], "since": since, "until": until},
                done=lambda r, t=token: self._shown(t, r), failed=lambda m, _d, t=token: self._failed(t, m))

    def _set_range(self, key: str):
        self._range = key
        self.load()

    def _failed(self, token: int, message: str):
        if token == self._token:
            self.note.error(message)

    def _shown(self, token: int, reply: dict):
        if token != self._token:
            return
        self.data = reply
        self.note.clear_note()
        t = reply.get("totals") or {}
        chats = int(t.get("chats", 0))
        self.k_replies.set_value(count_text(t.get("replies", 0)), i18n.t("{n} test messages").format(n=t.get("tests", 0)))
        self.k_chats.set_value(count_text(chats))
        self.k_settled.set_value("%d%%" % round(float(t.get("settled_rate", 0))), i18n.t("{n} chats").format(n=count_text(t.get("settled", 0))))
        self.k_handed.set_value("%d%%" % round(float(t.get("handover_rate", 0))), i18n.t("{n} chats").format(n=count_text(t.get("handed_over", 0))))
        self.k_actions.set_value(count_text(t.get("actions", 0)))
        self.k_skills.set_value(count_text(t.get("skills_finished", 0)))
        self.explain.setText(i18n.t("“Settled without a person” only means nobody had to step in. It does not say the customer was happy.") if chats else
                             i18n.t("No customer has chatted with this agent in this time. Publish it, switch it on, and the numbers appear here."))
        self.chart.set_days([{"day": d["day"], "runs": d["replies"]} for d in reply.get("days") or []])
        ui.clear(self.reasons_col)
        for r in reply.get("reasons") or []:
            self.reasons_col.addWidget(C.label("•  %s — %s" % (r["reason"], i18n.t("{n} times").format(n=r["count"])), level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True))
        if not reply.get("reasons"):
            self.reasons_col.addWidget(C.label(i18n.t("None in this time."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        self.show_gaps(reply.get("gaps") or [])

    # ── what it could not answer ─────────────────────────────────────────────
    def load_gaps(self):
        ui.call(self.editor, "ai/gaps/list", {"agent_id": self.editor.agent["id"]}, done=lambda r: self.show_gaps(r.get("gaps") or []), failed=lambda m, _d: self.gaps_note.error(m))

    def show_gaps(self, gaps: list):
        self.gaps = list(gaps)
        ui.clear(self.gaps_col)
        if not gaps:
            self.gaps_col.addWidget(C.label(i18n.t("Nothing right now. When a customer asks something it does not know, it shows up here."), level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
        for g in gaps:
            line = QFrame()
            line.setObjectName("waGap")
            line.setAttribute(Qt.WA_StyledBackground, True)
            line.setStyleSheet(f"#waGap {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
            row = QHBoxLayout(line)
            row.setContentsMargins(12, 8, 8, 8)
            text = QVBoxLayout()
            text.setSpacing(0)
            text.addWidget(C.label(g.get("question") or "", level="SUPPORT", weight=600, wrap=True))
            text.addWidget(C.label(i18n.t("Asked {n} times · last {t}").format(n=g.get("times", 1), t=short_time(g.get("last_at") or "")), level="META", colour=theme.NEUTRAL[500]))
            row.addLayout(text, 1)
            row.addWidget(C.button(i18n.t("Teach it"), "secondary", small=True, on_click=lambda _=False, x=g: self.teach(x)))
            row.addWidget(C.button(i18n.t("Ignore"), "tertiary", small=True, on_click=lambda _=False, x=g: self.ignore(x)))
            self.gaps_col.addWidget(line)

    def teach(self, gap: dict):
        dlg = TeachDialog(gap.get("question") or "", self.editor)
        if dlg.exec():
            ui.call(self.editor, "ai/gaps/answer", {"gap_id": gap["id"], "answer": dlg.answer.toPlainText().strip()},
                    done=lambda r: (self.gaps_note.ok(i18n.t("Learned. It will use that from now on.")), self.load_gaps(), self.editor.knowledge.load(), self.editor.owner.refresh_list()),
                    failed=lambda m, _d: self.gaps_note.error(m))

    def ignore(self, gap: dict):
        ui.call(self.editor, "ai/gaps/ignore", {"gap_id": gap["id"]}, done=lambda r: (self.load_gaps(), self.editor.owner.refresh_list()), failed=lambda m, _d: self.gaps_note.error(m))
