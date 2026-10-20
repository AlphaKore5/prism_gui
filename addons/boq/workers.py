"""BOQ's own worker for the "Groq (in-house)" writer choice.

Every other writer in addons/boq/agents.py:WRITER is a browser-driven agent,
run through workers.AutomationWorker's custom_stages. Groq is the one
exception -- a direct API call (core.router.groq_chat), the same call STEP's
Ask already makes (addons/step/workers.py:StepAskWorker), using the one Groq
key the whole app shares (cfg["api_key"]). It cannot go through
AutomationWorker, which only knows how to drive a browser -- and it has no
file upload at all, so it is only ever started once the caller has checked
there is no template, notes file or attachment this particular prompt text
doesn't already cover (addons/boq/dialog.py's two "Groq ... can't read"
guards, for the initial write and for a follow-up/recheck respectively).

`stage` names the step this answer belongs to ("format" for the first
write-up, "recheck" or "followup" afterwards) -- whatever
addons/boq/dialog.py would have passed as the AutomationWorker custom_stages
key for the same call. done emits in the SAME (responses, links) shape
AutomationWorker.done does -- links always {}, since a direct API call has
no browser conversation to open -- so the dialog's _on_written/
_on_followed_up need no branching to consume either worker's result.
"""
from __future__ import annotations

from PySide6.QtCore import Signal

import core_bridge as CB
from workers import _Worker


class BoqGroqWorker(_Worker):
    done = Signal(dict, dict)
    failed = Signal(str)

    def __init__(self, cfg: dict, prompt: str, stage: str = "format"):
        super().__init__()
        self.cfg, self.prompt, self.stage = cfg, prompt, stage

    def run(self):
        try:
            text = CB.router.groq_chat(
                self.cfg.get("api_key", ""),
                self.cfg.get("model", "llama-3.3-70b-versatile"),
                self.prompt, temperature=0.4, timeout=90).strip()
            self.done.emit({self.stage: [text]}, {})
        except Exception as e:                            # noqa: BLE001
            self.failed.emit(str(e))
