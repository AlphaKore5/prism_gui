"""Sample answers for a campaign in detail, the campaign settings and API campaigns.

Answers POST /v1/whatsapp/p/<route> from memory in the shapes prism-wa's ops_campaigns.py returns. Reached only through
demo_platform.handle (PRISM_WHATSAPP_DEMO=1, never in a frozen build). The people in a campaign's table are the demo contacts, dealt
a believable spread of outcomes so the table, its filters and the failure reasons have something to show.

STDLIB ONLY.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from addons.whatsapp.license_client import PlatformError

_ROUTES = ("campaigns/recipients", "campaigns/recipients_csv", "campaigns/failures", "campaigns/settings/get", "campaigns/settings/save",
           "api_campaigns/create", "api_campaigns/list", "api_campaigns/set_live", "api_campaigns/delete", "campaigns/list", "campaigns/report")
_REASONS = {131026: ("This number is not on WhatsApp, or cannot get messages from a business.", "Take it off your list."),
            131049: ("Meta chose not to deliver this marketing message, to keep the person's chats from filling with promotions (its frequency cap). "
                     "Your account is not penalised.", "Try again in a day or two, and send fewer marketing messages to the same people.")}
_CYCLE = ("read", "delivered", "sent", "read", "failed", "delivered", "failed", "read", "sent", "delivered")


def _err(message: str, reason: str, status: int = 400):
    raise PlatformError(message, reason, {})


def _state(p: dict) -> dict:
    return p.setdefault("camp2", {"settings": {"auto_pause_on_category_change": True}, "api": [], "seq": 200})


def _people(c: dict, p: dict, s: dict) -> list:
    """The people a campaign went to, with how far each message got — derived, so the table agrees with the counts."""
    n = max(int(c.get("total") or 0), 0)
    contacts = s["contacts"]
    rows = []
    failed_left = int(c.get("failed") or 0)
    for i in range(min(n, 60)):
        who = contacts[i % len(contacts)]
        status = _CYCLE[i % len(_CYCLE)]
        if status == "failed":
            if failed_left <= 0:
                status = "sent"
            else:
                failed_left -= 1
        code = (131026 if i % 2 else 131049) if status == "failed" else None
        reason = _REASONS.get(code, ("", ""))
        rows.append({"id": "r%d" % i, "contact_id": who["id"], "name": who["name"] if i < len(contacts) else "%s %d" % (who["name"], i // len(contacts) + 1),
                     "phone": who["phone"], "status": status, "replied": status == "read" and i % 3 == 0, "clicked": status == "read" and i % 4 == 0,
                     "at": (datetime.now(timezone.utc) - timedelta(days=1, minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "reason": reason[0] or None, "advice": reason[1] or None, "code": code})
    return rows


def _match(row: dict, status: str) -> bool:
    return {"": True, None: True, "sent": row["status"] in ("sent", "delivered", "read"), "delivered": row["status"] in ("delivered", "read"),
            "read": row["status"] == "read", "replied": row["replied"], "clicked": row["clicked"], "failed": row["status"] == "failed",
            "skipped": row["status"] == "skipped", "pending": row["status"] == "pending"}.get(status, True)


def handle(route: str, d: dict, p: dict, s: dict):
    if route not in _ROUTES:
        return None
    st = _state(p)
    if route in ("campaigns/recipients", "campaigns/recipients_csv", "campaigns/failures"):
        c = next((x for x in p["campaigns"] if x["id"] == d.get("campaign_id")), None)
        if c is None:
            _err("that campaign is not in this workspace", "unknown_campaign")
        rows = [r for r in _people(c, p, s) if _match(r, d.get("status") or "")]
        term = (d.get("search") or "").strip().lower()
        if term:
            rows = [r for r in rows if term in (r["name"] + r["phone"]).lower()]
        if route == "campaigns/failures":
            out = {}
            for r in _people(c, p, s):
                if r["status"] == "failed":
                    out.setdefault(r["code"], {"code": r["code"], "reason": r["reason"], "advice": r["advice"], "count": 0})["count"] += 1
            return {"failures": sorted(out.values(), key=lambda x: -x["count"])}
        if route == "campaigns/recipients_csv":
            lines = ["Name,Mobile,Status,Replied,Clicked,Why it did not go,What to do,When"]
            for r in rows:
                lines.append(",".join([r["name"], r["phone"], r["status"], "yes" if r["replied"] else "no", "yes" if r["clicked"] else "no",
                                       (r["reason"] or "").replace(",", ";"), (r["advice"] or "").replace(",", ";"), r["at"]]))
            return {"csv": "\n".join(lines) + "\n"}
        lim, off = int(d.get("limit") or 100), int(d.get("offset") or 0)
        return {"recipients": rows[off:off + lim], "total": len(rows)}

    if route == "campaigns/report":
        c = next((x for x in p["campaigns"] if x["id"] == d.get("campaign_id")), p["campaigns"][0])
        sent = c["sent"]
        out = {"campaign": {"id": c["id"], "name": c["name"], "status": c["status"], "template": c["template_name"]},
               "counts": {"recipients": c["total"], "queued": 0, "skipped": 0, "sent": sent, "delivered": int(sent * .94), "read": int(sent * .61),
                          "replied": int(sent * .12), "clicked": int(sent * .09), "clicks": int(sent * .11), "failed": c["failed"]},
               "rates": {"delivered": 94.0, "read": 61.0, "replied": 12.0, "clicked": 9.0}, "billable": {"marketing": sent},
               "spend_estimate": {"inr": round(sent * 0.8631 * 1.18, 2), "is_estimate": True},
               "failures": handle("campaigns/failures", {"campaign_id": c["id"]}, p, s)["failures"] if c["failed"] else []}
        return {"report": out}

    if route == "campaigns/settings/get":
        return {"settings": dict(st["settings"])}
    if route == "campaigns/settings/save":
        st["settings"].update({k: bool(v) for k, v in (d.get("settings") or {}).items() if k in st["settings"]})
        return {"settings": dict(st["settings"])}

    if route == "campaigns/list":
        base = sorted(p["campaigns"], key=lambda c: c["created_at"], reverse=True)
        extra = [{"id": a["id"], "name": a["name"], "status": "sending" if a["live"] else "paused", "template_name": a["template_name"], "language": a["language"],
                  "total": a["sent"], "sent": a["sent"], "failed": 0, "schedule_at": None, "created_at": a["created_at"], "kind": "api", "pause_reason": None}
                 for a in st["api"]]
        return {"campaigns": [dict(c, kind=c.get("kind", "broadcast"), pause_reason=c.get("pause_reason")) for c in base] + extra}

    if route == "api_campaigns/list":
        return {"campaigns": [dict(a, live=a["live"], status="sending" if a["live"] else "paused", total=a["sent"], failed=0) for a in st["api"]],
                "endpoint": "https://example.com/campaign/t1/api/v2"}
    if route == "api_campaigns/create":
        name = (d.get("name") or "").strip()
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$", name):
            _err("Name it with letters, numbers, spaces, - _ or . (80 characters at most).", "bad_name")
        tpl = next((t for t in p["templates"] if t["name"] == d.get("template_name")), None)
        if tpl is None:
            _err("That template is not known for this account. Update your templates from Meta first.", "unknown_template")
        if tpl["status"] != "APPROVED":
            _err("The template is %s; only an approved template can be sent." % tpl["status"].lower(), "template_not_approved")
        if any(a["name"] == name for a in st["api"]):
            _err("You already have an API campaign called %r." % name, "name_taken")
        st["seq"] += 1
        st["api"].append({"id": "a%d" % st["seq"], "name": name, "template_name": tpl["name"], "language": tpl.get("language", "en_US"), "live": True, "sent": 0,
                          "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        return {"campaign_id": st["api"][-1]["id"]}
    if route == "api_campaigns/set_live":
        a = next((x for x in st["api"] if x["id"] == d.get("campaign_id")), None)
        if a is None:
            _err("That API campaign is not in this workspace.", "unknown_campaign")
        a["live"] = bool(d.get("live"))
        return {}
    # api_campaigns/delete
    n = len(st["api"])
    st["api"] = [a for a in st["api"] if a["id"] != d.get("campaign_id")]
    return {"deleted": len(st["api"]) < n}
