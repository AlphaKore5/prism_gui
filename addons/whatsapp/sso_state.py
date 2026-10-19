"""Where the app keeps the proof that this person signed in with their company account.

The server hands over a session token once, when the sign-in finishes; it lives here, in memory only (closing Prism means signing in again), and `license_client.platform()` adds it to
every call. When the server says a workspace requires company sign-in and there is no live token, it answers `sso_required`; the worker announces that here and the workbench opens the
sign-in window. Nothing about the token is written to disk.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class _Notifier(QObject):
    required = Signal()          # the server wants a company sign-in
    signed_in = Signal(dict)     # it worked: {name, email, role}


NOTIFY = _Notifier()
_token: str = ""
_who: dict = {}


def token() -> str:
    return _token


def who() -> dict:
    return dict(_who)


def set_session(result: dict) -> None:
    global _token, _who
    _token = str(result.get("token") or "")
    _who = {k: result.get(k) for k in ("name", "email", "role", "agent_id")}
    NOTIFY.signed_in.emit(dict(_who))


def clear() -> None:
    global _token, _who
    _token, _who = "", {}


def announce_required() -> None:
    """Called from a worker thread when a call is refused for want of a sign-in (a queued signal, so the window opens on the UI thread)."""
    clear()
    NOTIFY.required.emit()
