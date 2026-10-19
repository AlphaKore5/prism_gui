"""Desktop alerts for the Inbox: a toast and a sound when a chat needs a person or a new message arrives.

What a person wants differs — a front desk wants every message, a manager only the chats that need someone — so the three
choices live in the WhatsApp section of the app's own config (`cfg["whatsapp"]["notify"]`) and are edited in
Settings → Notifications. Reading them never fails: a missing or odd value is the default.
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

import i18n
from widgets import controls as C

DEFAULTS = {"toast": True, "sound": True, "only_requests": False}


def prefs(cfg: dict) -> dict:
    block = ((cfg or {}).get("whatsapp") or {}).get("notify")
    out = dict(DEFAULTS)
    if isinstance(block, dict):
        for k in DEFAULTS:
            if isinstance(block.get(k), bool):
                out[k] = block[k]
    return out


def store(cfg: dict, new: dict) -> dict:
    """Put the choices into `cfg` (not saved to disk: the caller saves) and return what was kept."""
    keep = {k: bool(new.get(k, DEFAULTS[k])) for k in DEFAULTS}
    wa = dict((cfg.get("whatsapp") or {}))
    wa["notify"] = keep
    cfg["whatsapp"] = wa
    return keep


def events(previous: dict, rows: list, unread_ids: set) -> list:
    """What is new since last time: [("request", row), ("message", row)]. `previous` is {"requesting": set, "unread": set} from
    the last look (empty on the first, so opening the app does not fire an alert for everything already waiting)."""
    if previous is None:
        return []
    out = []
    for r in rows:
        cid = r.get("id")
        if r.get("status") == "requesting" and cid not in previous.get("requesting", set()):
            out.append(("request", r))
        elif cid in unread_ids and cid not in previous.get("unread", set()) and r.get("status") != "requesting":
            out.append(("message", r))
    return out


def announce(parent, p: dict, items: list) -> int:
    """Show/sound the new events as the preferences allow. -> how many were announced."""
    shown = 0
    for kind, row in items:
        if p.get("only_requests") and kind != "request":
            continue
        who = row.get("contact_name") or row.get("contact_phone") or i18n.t("Someone")
        if p.get("toast"):
            C.show_toast(parent, i18n.t("{n} needs a person").format(n=who) if kind == "request" else i18n.t("New message from {n}").format(n=who),
                         (row.get("last_text") or "")[:80])
        shown += 1
    if shown and p.get("sound"):
        QApplication.beep()
    return shown
