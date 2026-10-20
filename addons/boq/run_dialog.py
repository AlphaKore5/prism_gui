"""BOQ's own live-progress window for a verify or follow-up call.

Modelled on Prism core's own Run screen (widgets/output_panel.py's
RunHeader + StageCard) so a BOQ customer sees the same language the rest
of the app already uses for "who is working on this right now" — not a
new, one-off look. It reuses StageCard directly rather than reinventing
its status badges, timeline dot and live elapsed clock.

Not the full OutputPanel: that widget is sized and wired for the main
multi-stage pipeline (a back button into Home, a step counter across many
stages, "next problem" navigation across a whole run). BOQ's call is
always exactly one job — write it up, verify it, or carry a follow-up on
— so this is a small dialog around ONE StageCard, reused in place (via
its own set_agent()) when the work hands over to a fallback tool, the
same way a real failover reuses a card in the real Run screen rather than
stacking a second one.

Skip and Stop call straight through to the real, already-working
workers.AutomationWorker.skip()/.stop() -- generic, stage-name-independent
primitives the engine already polls inside every wait, custom_stages or
not (see main_window.py's own _skip_step/_stop_run for the identical
pattern). "Use fallback" deliberately does NOT call
AutomationWorker.use_fallback(): that path resolves its candidate through
core.agents.alternatives_for(stage, ...), which looks a stage's
candidates up by CATEGORY, and BOQ's stage keys ("format", "recheck",
"followup") are not categories — it would set the flag, the engine would
look up nothing, and the button would silently do nothing. Instead this
dialog only emits intent (skip_requested / fallback_requested /
stop_requested); addons/boq/dialog.py owns the actual worker and walks
its own flat addons/boq/agents.py:FALLBACK_ORDER chain, same shape as
addons/step/dialog.py's FALLBACK_ORDER + _ask_via_chain.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

import i18n
import theme
from widgets import controls as C
from widgets.output_panel import StageCard


class BoqRunDialog(QDialog):
    """One StageCard, a few controls. This dialog never talks to a worker
    itself -- it only emits intent (the three signals below) and is driven
    back by the caller through set_agent()/finish_ok()/finish_error()/
    finish_skipped()/finish_cancelled()."""

    skip_requested = Signal()
    fallback_requested = Signal()
    stop_requested = Signal()

    def __init__(self, title: str, stage: str, agent: str, parent=None,
                 note: str = ""):
        super().__init__(parent)
        self.setWindowTitle(i18n.t("Working"))
        self.setModal(True)
        self.setMinimumWidth(560)
        self._done = False

        root = QVBoxLayout(self)
        root.setContentsMargins(theme.CARD_PAD, theme.CARD_PAD,
                                theme.CARD_PAD, theme.CARD_PAD)
        root.setSpacing(theme.SPACE_3)

        root.addWidget(C.kicker(i18n.t("Working now")))
        head = QLabel(title)
        head.setObjectName("h4")
        head.setWordWrap(True)
        root.addWidget(head)

        self.card = StageCard(stage, agent, index=1)
        self.card.set_state("running")
        # An honest expectation up front — the owner's own report was a
        # recheck reading up to ~20 minutes with nothing on screen saying
        # that was normal, which read as stuck rather than working. Only a
        # real failover note (set_agent, below) replaces this.
        if note:
            self.card.set_note(note)
        root.addWidget(self.card)

        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        self.skip_btn = C.button(
            i18n.t("Skip this step"), "secondary", "play", small=True,
            on_click=self.skip_requested.emit)
        self.skip_btn.setToolTip(i18n.t(
            "Give up on this answer and keep whatever was already shown "
            "before you asked."))
        self.fallback_btn = C.button(
            i18n.t("Use fallback"), "secondary", small=True,
            on_click=self.fallback_requested.emit)
        self.fallback_btn.setToolTip(i18n.t(
            "Stop waiting for this tool and hand the question to the next "
            "one in the fallback order now, instead of only on failure."))
        self.stop_btn = C.button(
            i18n.t("Stop the run"), "destructive", "stop", small=True,
            on_click=self.stop_requested.emit)
        row.addWidget(self.skip_btn)
        row.addWidget(self.fallback_btn)
        row.addStretch(1)
        row.addWidget(self.stop_btn)
        root.addLayout(row)

        self.close_btn = C.button(i18n.t("Close"), "primary",
                                  on_click=self.accept)
        self.close_btn.setEnabled(False)
        root.addWidget(self.close_btn)

    # ── inbound state -- the caller drives the card from worker signals ────
    def set_agent(self, agent: str):
        """A fallback attempt is starting: reuse the one card, the same way
        a real failover in the core Run screen does, so the elapsed clock
        and the "tried" history stay with the step, not with the tool."""
        self.card.set_agent(agent)
        self.card.set_state("running")

    def finish_ok(self, texts: list[str], url: str = ""):
        self.card.set_done(texts, url)
        self._lock()

    def finish_error(self, error: str, exhausted: bool = True):
        """exhausted=False means a fallback attempt is about to start —
        the card stays open for the retry note set_agent() adds next, so
        this does NOT lock the dialog. exhausted=True is the real end: no
        more agents left to try."""
        self.card.set_error(error)
        if exhausted:
            self._lock()

    def finish_skipped(self, reason: str = ""):
        self.card.set_skipped(reason)
        self._lock()

    def finish_cancelled(self, note: str = ""):
        self.card.set_cancelled(note)
        self._lock()

    def _lock(self):
        self._done = True
        for w in (self.skip_btn, self.fallback_btn, self.stop_btn):
            w.setEnabled(False)
        self.close_btn.setEnabled(True)

    def closeEvent(self, event):
        # The window's own [x] must not look like it cancelled a run that
        # is still going — the same reasoning BoqDialog's own closeEvent
        # already follows for its worker.
        if not self._done:
            self.stop_requested.emit()
        super().closeEvent(event)
