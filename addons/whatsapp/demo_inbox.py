"""Sample answers for the Inbox's own routes: the list of chats with its tab counts, one thread, and a typed reply.

Answers POST /v1/whatsapp/p/<route> from memory in the shapes prism-wa's ops_chat.py returns. Reached only through
demo_platform.handle (PRISM_WHATSAPP_DEMO=1, never in a frozen build). Chats, messages and contacts are the demo's own
(demo.py); who has which chat lives in demo_automation (the team inbox), so the buttons there move chats between the tabs here.

STDLIB ONLY.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from addons.whatsapp.license_client import PlatformError

NOW = lambda: datetime.now(timezone.utc)                                              # noqa: E731
ISO = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")                                      # noqa: E731
_ROUTES = ("inbox/threads", "inbox/thread", "messages/send_text")


def _ts(text: str):
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _seed(a: dict):
    """A few chats start in states other than 'with the bot', so the tabs have something in them."""
    if a.get("_inbox_seeded"):
        return
    a["_inbox_seeded"] = True
    a["conv"].setdefault("c4", {"status": "requesting", "assignee_id": None})
    a["conv"].setdefault("c2", {"status": "intervened", "assignee_id": "a2"})
    a["conv"].setdefault("c3", {"status": "closed", "assignee_id": None})


def _last_in(thread: list):
    stamps = [_ts(m.get("created_at")) for m in thread if m.get("direction") == "in"]
    stamps = [x for x in stamps if x]
    return max(stamps) if stamps else None


def _row(c: dict, p: dict, s: dict, a: dict, me: str, masked: bool) -> dict:
    thread = s["threads"].get(c["id"]) or []
    contact = next((k for k in s["contacts"] if k["id"] == c["contact_id"]), {})
    st = a["conv"].setdefault(c["id"], {"status": "active", "assignee_id": None})
    last = thread[-1] if thread else {}
    last_in = _last_in(thread)
    assignee = next((x for x in a["agents"] if x["id"] == st["assignee_id"]), None)
    phone = contact.get("phone") or ""
    return {"id": c["id"], "contact_id": c["contact_id"], "status": st["status"], "assignee_id": st["assignee_id"],
            "assignee_name": (assignee or {}).get("name"), "last_active_at": last.get("created_at", ""),
            "last_inbound_at": ISO(last_in) if last_in else None, "requested_at": None, "contact_name": contact.get("name") or "",
            "contact_phone": ("*" * max(len(phone) - 4, 0) + phone[-4:]) if masked else phone, "opt_out": bool(contact.get("opt_out")),
            "blocked": False, "tags": list(contact.get("tags") or []), "last_text": last.get("text", ""),
            "last_direction": last.get("direction", ""), "last_type": "text",
            "window_open": bool(last_in and NOW() - last_in < timedelta(hours=24)), "channel": "whatsapp"}


def _visible(row: dict, role: str, me: str) -> bool:
    return role != "agent" or row["assignee_id"] in (me, None)


def _window_ok(row: dict, window) -> bool:
    wanted = row["status"] in ("requesting", "intervened", "human_takeover")
    return {"open": row["window_open"], "closed": not row["window_open"], "live": row["window_open"] or wanted,
            "history": not row["window_open"] and not wanted}.get(window, True)


def _state_ok(row: dict, state, me: str) -> bool:
    st = row["status"]
    return {None: True, "": True, "requesting": st == "requesting", "mine": row["assignee_id"] == me and st != "closed",
            "unassigned": row["assignee_id"] is None and st != "closed", "bot": st in ("new", "active", "open"),
            "intervened": st in ("intervened", "human_takeover"), "closed": st == "closed"}.get(state, True)


def handle(route: str, d: dict, p: dict, s: dict):
    if route not in _ROUTES:
        return None
    from addons.whatsapp import demo_automation, demo_book
    a = demo_automation._auto(p)
    _seed(a)
    from addons.whatsapp import demo_media
    demo_media.seed_threads(p, s)
    me = d.get("agent_id") or d.get("by_agent_id") or "a1"
    agent = next((x for x in a["agents"] if x["id"] == me), a["agents"][0])
    masked = bool(agent.get("masked") and agent["role"] == "agent")

    if route == "inbox/threads":
        rows = [_row(c, p, s, a, me, masked) for c in s["conversations"]]
        rows = [r for r in rows if _visible(r, agent["role"], me) and _window_ok(r, d.get("window"))]
        term = (d.get("search") or "").strip().lower()
        if term:
            rows = [r for r in rows if term in (r["contact_name"] + " " + r["contact_phone"] + " " + r["last_text"]).lower()]
        if d.get("filter"):
            keep = {x["id"] for x in demo_book._filtered(p, s, d["filter"])}
            rows = [r for r in rows if r["contact_id"] in keep]
        counts = {"all": len(rows), "requesting": 0, "mine": 0, "unassigned": 0, "bot": 0, "intervened": 0, "closed": 0}
        for r in rows:
            for k in counts:
                if k != "all" and _state_ok(r, k, me):
                    counts[k] += 1
        shown = [r for r in rows if _state_ok(r, d.get("state"), me)]
        shown.sort(key=lambda r: r["last_active_at"], reverse=True)
        lim, off = int(d.get("limit") or 100), int(d.get("offset") or 0)
        return {"conversations": shown[off:off + lim], "counts": counts, "total": len(shown)}

    if route == "inbox/thread":
        c = next((x for x in s["conversations"] if x["id"] == d.get("conversation_id")), None)
        if c is None:
            raise PlatformError("that chat is not in this workspace", "unknown_conversation", {})
        row = _row(c, p, s, a, me, masked)
        if agent["role"] == "agent" and row["assignee_id"] not in (me, None):
            raise PlatformError("this chat belongs to another agent", "not_yours", {})
        msgs = []
        for i, m in enumerate(s["threads"].get(c["id"], [])):
            msgs.append({"id": "%s-%d" % (c["id"], i), "direction": m["direction"], "sender": m.get("sender"), "text": m.get("text", ""),
                         "created_at": m.get("created_at"), "status": m.get("status") or None, "msg_type": m.get("msg_type") or "text",
                         "media": m.get("media"), "error": None, "reply_to": None})
        return {"conversation": row, "messages": msgs}

    # messages/send_text
    text = (d.get("text") or "").strip()
    if not text:
        raise PlatformError("there is nothing to send", "empty", {})
    c = next((x for x in s["conversations"] if x["id"] == d.get("conversation_id") or x["contact_id"] == d.get("contact_id")), None)
    if c is None:
        raise PlatformError("that chat is not in this workspace", "unknown_conversation", {})
    if not _row(c, p, s, a, me, False)["window_open"]:
        raise PlatformError("the 24-hour window is closed; send an approved template", "window_closed", {})
    ref = str(d.get("client_ref") or "")
    sent = a.setdefault("_sent_refs", {})
    if ref and ref in sent:
        return {"queued": True, "outbox_id": sent[ref]}
    s["threads"][c["id"]].append({"direction": "out", "sender": agent["name"], "text": text, "created_at": ISO(NOW()), "status": "sent"})
    st = a["conv"].setdefault(c["id"], {"status": "active", "assignee_id": None})
    if st["status"] != "closed":
        st.update(status="intervened", assignee_id=me)
    key = ref or str(len(sent))
    sent[key] = "o%d" % (len(sent) + 1)
    return {"queued": True, "outbox_id": sent[key]}
