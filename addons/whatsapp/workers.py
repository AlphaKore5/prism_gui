"""Off-thread workers for the WhatsApp add-on.

Per-addon workers, like addons/leads/workers.py. Each subclasses the shared
`workers._Worker` (which anchors a running QThread against GC, so a dialog can
close mid-send without a native crash), and imports its client lazily inside
run() so importing this module never reaches for the network or drags anything
heavy onto the UI thread.

Every worker below but WhatsAppSendWorker talks to Prism's own licence server
(addons.whatsapp.license_client), never Supabase or n8n directly — see that
module's docstring. None of them take a base URL or a key any more: the
licence server already knows which seat is calling.
"""
from __future__ import annotations

from PySide6.QtCore import Signal

from workers import _Worker


class WhatsAppSendWorker(_Worker):
    """Send one WhatsApp message off the UI thread.

    A Cloud API call is a network round trip and blocks; `done` carries the
    wamid Meta assigned, so the dialog can show it and, later, match a delivery
    receipt back to the message that earned it."""

    done = Signal(str)          # wamid
    failed = Signal(str)

    def __init__(self, phone_number_id: str, token: str, to: str, body: str = "",
                 *, template: str = "", language: str = "en_US", api_version: str = "v21.0"):
        super().__init__()
        self.phone_number_id = phone_number_id
        self.token = token
        self.to = to
        self.body = body
        self.template = template
        self.language = language
        self.api_version = api_version

    def run(self):
        try:
            if self.template:
                from addons.whatsapp.cloud_api import send_template
                wamid = send_template(self.phone_number_id, self.token, self.to,
                                      self.template, language=self.language, api_version=self.api_version)
            else:
                from addons.whatsapp.cloud_api import send_text
                wamid = send_text(self.phone_number_id, self.token, self.to,
                                  self.body, api_version=self.api_version)
            self.done.emit(wamid)
        except Exception as e:                          # noqa: BLE001
            self.failed.emit(str(e))


class PlatformWorker(_Worker):
    """One call to the WhatsApp platform (templates, campaigns, segments, contacts,
    inbox actions...) off the UI thread. `done` carries the reply; `failed` carries
    the message and the server's detail (reason code, preflight report, issues)."""

    done = Signal(dict)
    failed = Signal(str, dict)

    def __init__(self, route: str, data: dict = None):
        super().__init__()
        self.route = route
        self.data = dict(data or {})

    def run(self):
        try:
            from addons.whatsapp import license_client as lc
            self.done.emit(lc.platform(self.route, **self.data))
        except Exception as e:                          # noqa: BLE001
            detail = dict(getattr(e, "detail", None) or {})
            detail.setdefault("reason", getattr(e, "reason", ""))
            if detail.get("reason") == "sso_required":                 # the workspace wants a company sign-in first
                from addons.whatsapp import sso_state
                sso_state.announce_required()
            self.failed.emit(str(e), detail)
