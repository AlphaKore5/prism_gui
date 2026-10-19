"""Sample answers for the team inbox, stores, API keys, ads, chatbot flows, AI agents and repeating campaigns.

Answers POST /v1/whatsapp/p/<route> from memory in the shapes the real service returns (prism-wa's ops.py), so the
screens built on them can be built, shown and tested offline. Reached only through demo_platform.handle, which is
switched on with PRISM_WHATSAPP_DEMO=1 and never in a frozen build. State lives in demo_platform._PAGE["auto"], so the
same reset that clears the other demo data clears this.

The flow checker and test console here are deliberately small look-alikes of the server's: enough to show how the screens
behave with errors, questions and button replies. The real rules live in prism-wa (flows.py, flow_engine.py).

STDLIB ONLY.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone

from addons.whatsapp.demo_flows import LIBRARY, check_flow
from addons.whatsapp.license_client import PlatformError

NOW = lambda: datetime.now(timezone.utc)                                              # noqa: E731
ISO = lambda d=None: (d or NOW()).strftime("%Y-%m-%dT%H:%M:%SZ")                      # noqa: E731


def _auto(p: dict) -> dict:
    if "auto" not in p:
        p["auto"] = {
            "seq": 100,
            "agents": [
                {"id": "a1", "seat_key": "me", "name": "You", "role": "owner", "active": True, "available": True, "masked": False,
                 "working_hours": None, "rules": [], "created_at": ISO()},
                {"id": "a2", "seat_key": "bala", "name": "Bala", "role": "agent", "active": True, "available": True, "masked": False,
                 "working_hours": None, "rules": [], "created_at": ISO()},
                {"id": "a3", "seat_key": "meera", "name": "Meera", "role": "manager", "active": True, "available": False, "masked": False,
                 "working_hours": None, "rules": [], "created_at": ISO()}],
            "inbox_settings": {"routing": "least_busy", "auto_resolve_hours": 24, "sla_minutes": 15, "business_hours": None, "holidays": [],
                               "welcome": {"enabled": False, "text": "Hello! Thanks for messaging us. How can we help you today?", "once_per_hours": 24,
                                           "asset_id": None, "template": None},
                               "off_hours": {"enabled": False, "once_per_hours": 12, "asset_id": None, "template": None,
                                             "text": "Thanks for your message. We are closed right now and will reply as soon as we open."}},
            "canned": [{"shortcut": "thanks", "body": "Thanks {{first_name}}! We'll get back to you shortly."},
                       {"shortcut": "hours", "body": "We are open Monday to Saturday, 10 am to 6 pm."}],
            "conv": {}, "notes": {},
            "keys": [], "scopes": ["contacts:read", "contacts:write", "messages:read", "messages:send", "template_messages:send", "templates:read",
                                   "campaigns:read", "campaigns:write"],
            "integrations": [],
            "ad_accounts": [], "ads": [],
            "flows": {}, "ai": {}, "kb": {}, "schedules": [],
            "ai_used": 0}
    return p["auto"]


def _next(a: dict, prefix: str) -> str:
    a["seq"] += 1
    return "%s%d" % (prefix, a["seq"])


def _err(message: str, reason: str, detail: dict = None):
    raise PlatformError(message, reason, detail or {})


# ── flows: the checker, the walker and the library are in demo_flows.py ───────


# ── the router ───────────────────────────────────────────────────────────────

def handle(route: str, data: dict, p: dict, s: dict) -> dict:
    a = _auto(p)
    area = route.split("/", 1)[0]
    return {"inbox": _inbox, "api_keys": _keys, "integrations": _integrations, "ads": _ads, "flows": _flows, "ai": _ai, "autos": _autos_route, "audiences": _ads,
            "schedules": _schedules, "campaigns": _campaign_extras, "onboarding": _onboarding, "numbers": _numbers}[area](route, data, a, s, p)


def _numbers(route, d, a, s, p):
    return {"numbers": list(p.setdefault("numbers", [{"id": "n1", "display": "+91 98765 43210", "status": "CONNECTED", "quality": "GREEN"}]))}


def _onboarding(route, d, a, s, p):
    return {"state": "demo", "path": "/onboarding?state=demo", "url": "https://example.com/onboarding?state=demo"}


# ── the team inbox ───────────────────────────────────────────────────────────

def _conv(a: dict, cid: str) -> dict:
    return a["conv"].setdefault(cid, {"status": "active", "assignee_id": None})


def _agent(a: dict, agent_id: str) -> dict:
    found = next((x for x in a["agents"] if x["id"] == agent_id), None)
    if found is None:
        _err("That teammate is not in this workspace.", "unknown_agent")
    return found


def _inbox(route, d, a, s, p):
    action = route.split("/", 1)[1]
    me = d.get("agent_id") or "a1"
    if action == "agents/list":
        return {"agents": [dict(x) for x in a["agents"] if x["active"]], "me": d.get("agent_id") or "a1"}
    if action == "agents/update":
        agent = _agent(a, d["agent_id"])
        for key, value in (d.get("changes") or {}).items():
            if key == "role" and value != agent["role"]:
                if agent["role"] == "owner" and sum(1 for x in a["agents"] if x["role"] == "owner") <= 1:
                    _err("A workspace needs at least one owner.", "last_owner")
            agent[key] = value
        return {"agent": dict(agent)}
    if action == "conversations":
        out = []
        for c in s["conversations"]:
            st = _conv(a, c["id"])
            contact = next((k for k in s["contacts"] if k["id"] == c["contact_id"]), {})
            out.append({"id": c["id"], "contact_id": c["contact_id"], "status": st["status"], "assignee_id": st["assignee_id"],
                        "last_active_at": ISO(), "contact_name": contact.get("name"), "contact_phone": contact.get("phone")})
        return {"conversations": out}
    if action in ("request_human", "intervene", "hand_back", "resolve", "transfer"):
        st = _conv(a, d["conversation_id"])
        if action == "request_human":
            st.update(status="requesting", assignee_id=None)
            return {"assigned_to": None}
        if action == "intervene":
            if st["assignee_id"] and st["assignee_id"] != me and _agent(a, me)["role"] == "agent":
                _err("Another teammate already has this chat.", "taken")
            st.update(status="intervened", assignee_id=me)
        elif action == "hand_back":
            st.update(status="active", assignee_id=None)
        elif action == "resolve":
            st.update(status="closed", assignee_id=None)
        else:
            _agent(a, d["to_agent_id"])
            st.update(status="intervened", assignee_id=d["to_agent_id"])
        return {}
    if action == "notes/add":
        a["notes"].setdefault(d["conversation_id"], []).append({"id": _next(a, "n"), "text": d["text"], "at": ISO(), "agent": _agent(a, me)["name"]})
        return {}
    if action == "notes/list":
        return {"notes": list(a["notes"].get(d["conversation_id"], []))}
    if action == "canned/list":
        from addons.whatsapp import demo_media
        out = []
        for c in sorted(a["canned"], key=lambda c: c["shortcut"]):
            f = next((x for x in demo_media._lib(p)["assets"] if x["id"] == c.get("asset_id")), None)
            out.append({"shortcut": c["shortcut"], "body": c["body"], "asset_id": c.get("asset_id"),
                        "asset_kind": f["kind"] if f else None, "asset_name": f["filename"] if f else None})
        return {"canned": out}
    if action == "canned/save":
        shortcut = str(d["shortcut"]).strip().lower().lstrip("/")
        if not re.match(r"^[a-z0-9_-]{1,30}$", shortcut):
            _err("A shortcut uses lowercase letters, numbers, - and _ (30 at most).", "bad_shortcut")
        body, asset_id = (d.get("body") or "").strip(), d.get("asset_id") or None
        if not (body or asset_id):
            _err("A saved reply needs 1 to 1000 characters, or a file.", "bad_canned")
        if asset_id:
            from addons.whatsapp import demo_media
            demo_media.asset(p, asset_id)
        a["canned"] = [c for c in a["canned"] if c["shortcut"] != shortcut] + [{"shortcut": shortcut, "body": body, "asset_id": asset_id}]
        a["canned"].sort(key=lambda c: c["shortcut"])
        return {}
    if action == "canned/delete":
        n = len(a["canned"])
        a["canned"] = [c for c in a["canned"] if c["shortcut"] != str(d["shortcut"]).lstrip("/")]
        return {"deleted": len(a["canned"]) < n}
    if action == "canned/expand":
        c = next((x for x in a["canned"] if x["shortcut"] == str(d["shortcut"]).lstrip("/")), None)
        if c is None:
            _err("There is no saved reply called /%s." % d["shortcut"], "unknown_shortcut")
        contact = next((k for k in s["contacts"] if k["id"] == d.get("contact_id")), {"name": ""})
        first = (contact["name"].split() or [""])[0]
        from addons.whatsapp import demo_media
        f = demo_media.asset(p, c["asset_id"]) if c.get("asset_id") else None
        return {"text": c["body"].replace("{{first_name}}", first).replace("{{name}}", contact["name"]), "asset": dict(f) if f else None}
    if action == "settings/get":
        return {"settings": a["inbox_settings"]}
    if action == "settings/save":
        patch = d.get("settings") or {}
        cur = a["inbox_settings"]
        for k, v in patch.items():
            if k in ("welcome", "off_hours") and isinstance(v, dict):
                if not (v.get("text") or "").strip() and not v.get("asset_id") and not v.get("template"):
                    _err("%s needs a message of up to 1000 characters, a file or a template" % k.replace("_", " "), "bad_settings")
                if v.get("asset_id"):
                    from addons.whatsapp import demo_media
                    demo_media.asset(p, v["asset_id"])
            cur[k] = {**cur[k], **v} if k in ("welcome", "off_hours") and isinstance(v, dict) else v
        if cur["routing"] not in ("least_busy", "round_robin", "manual"):
            _err("Routing must be one of: least_busy, round_robin, manual.", "bad_settings")
        days = cur.get("holidays") or []
        if not isinstance(days, list) or len(days) > 60:
            _err("holidays is a list of up to 60 days", "bad_settings")
        for h in days:
            day = str((h or {}).get("date") if isinstance(h, dict) else h or "")
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
                _err("a holiday needs a date like 2026-11-12 (got %r)" % day[:20], "bad_settings")
        cur["holidays"] = sorted({(h.get("date") if isinstance(h, dict) else h): h if isinstance(h, dict) else {"date": h} for h in days}.values(), key=lambda x: x["date"])
        return {"settings": cur}
    if action == "monitor":
        counts = {}
        for c in s["conversations"]:
            counts[_conv(a, c["id"])["status"]] = counts.get(_conv(a, c["id"])["status"], 0) + 1
        return {"monitor": {"by_state": counts, "unassigned_requests": counts.get("requesting", 0), "sla_breaches": 0,
                            "per_agent": [{"id": x["id"], "name": x["name"], "role": x["role"], "available": x["available"],
                                           "open": sum(1 for c in a["conv"].values() if c["assignee_id"] == x["id"])} for x in a["agents"]]}}
    raise KeyError(route)


# ── API keys ─────────────────────────────────────────────────────────────────

def _keys(route, d, a, s, p):
    action = route.split("/", 1)[1]
    if action == "list":
        return {"keys": [dict(k) for k in a["keys"]], "scopes": list(a["scopes"]), "base_url": "https://example.com/api/v1"}
    if action == "create":
        name = (d.get("name") or "").strip()
        if not name:
            _err("Give the key a name of 1 to 80 characters.", "bad_name")
        if not d.get("scopes"):
            _err("Choose what this key may do.", "no_scopes")
        secret = "pk_live_" + __import__("uuid").uuid4().hex
        key = {"id": _next(a, "k"), "name": name, "prefix": secret[:12], "scopes": sorted(d["scopes"]),
               "rate_limit_per_minute": int(d.get("rate_limit_per_minute") or 60), "created_at": ISO(), "last_used_at": None, "revoked_at": None}
        a["keys"].insert(0, key)
        return {"key": {**key, "secret": secret}}
    if action == "revoke":
        k = next((x for x in a["keys"] if x["id"] == d["key_id"]), None)
        if k:
            k["revoked_at"] = ISO()
        return {"revoked": bool(k)}
    raise KeyError(route)


# ── stores ───────────────────────────────────────────────────────────────────

def _clean_config(config: dict) -> dict:
    events = {}
    for key, spec in (config.get("events") or {}).items():
        if key not in ("order_created", "order_fulfilled", "abandoned_cart"):
            _err("Unknown event %r." % key, "bad_config")
        if not str((spec or {}).get("template") or "").strip():
            _err("%s needs a template name." % key, "bad_config")
        events[key] = {"template": spec["template"].strip(), "language": spec.get("language") or "en_US", "variables": dict(spec.get("variables") or {}),
                       "enabled": bool(spec.get("enabled", True)), **({"delay_minutes": int(spec.get("delay_minutes") or 60)} if key == "abandoned_cart" else {})}
    return {"events": events, "consent_attested": bool(config.get("consent_attested")), "default_country": str(config.get("default_country") or "91")}


def _integrations(route, d, a, s, p):
    action = route.split("/", 1)[1]
    if action == "list":
        return {"integrations": [dict(i) for i in a["integrations"]]}
    if action == "create":
        if d.get("kind") not in ("shopify", "woocommerce"):
            _err("Kind must be shopify or woocommerce.", "bad_kind")
        if len((d.get("secret") or "").strip()) < 8:
            _err("Paste the store's webhook signing secret.", "bad_secret")
        token = "tok%d" % a["seq"]
        item = {"id": _next(a, "i"), "kind": d["kind"], "name": (d.get("name") or "").strip() or d["kind"].title(), "token": token,
                "config": _clean_config(d.get("config") or {}), "enabled": True, "created_at": ISO(), "last_event_at": None,
                "path": "/hooks/%s/%s" % (d["kind"], token), "url": "https://example.com/hooks/%s/%s" % (d["kind"], token)}
        a["integrations"].append(item)
        return {"integration": dict(item)}
    item = next((i for i in a["integrations"] if i["id"] == d.get("integration_id")), None)
    if item is None:
        _err("That connection is not in this workspace.", "unknown_integration")
    if action == "update":
        if d.get("name") is not None:
            item["name"] = d["name"]
        if d.get("config") is not None:
            item["config"] = _clean_config(d["config"])
        if d.get("enabled") is not None:
            item["enabled"] = bool(d["enabled"])
        return {}
    if action == "delete":
        a["integrations"].remove(item)
        return {"deleted": True}
    raise KeyError(route)


# ── ads ──────────────────────────────────────────────────────────────────────

def _ads(route, d, a, s, p):
    from addons.whatsapp import demo_ads
    return demo_ads.handle(route, d, p, s, a)


# ── chatbot flows ────────────────────────────────────────────────────────────

def _flow(a: dict, flow_id: str) -> dict:
    f = a["flows"].get(flow_id)
    if f is None:
        _err("That flow is not in this workspace.", "unknown_flow")
    return f


def _flows(route, d, a, s, p):
    action = route.split("/", 1)[1]
    if action == "list":
        return {"flows": [{"id": f["id"], "name": f["name"], "enabled": f["enabled"], "trigger": f["trigger"], "version": f["version"],
                           "published_at": f["published_at"], "updated_at": f["updated_at"], "live": f.get("live", 0), "total_runs": f.get("runs", 0)}
                          for f in a["flows"].values()]}
    if action in ("create", "from_library"):
        if action == "from_library":
            item = next((x for x in LIBRARY if x["key"] == d.get("key")), None)
            if item is None:
                _err("There is no ready-made flow called %r." % d.get("key"), "bad_request")
            name, trigger, graph = d.get("name") or item["title"], item["trigger"], item["graph"]
        else:
            name, trigger, graph = (d.get("name") or "").strip(), d.get("trigger") or {}, d.get("graph") or {}
            if not name:
                _err("Give the flow a name (up to 80 characters).", "bad_name")
        if len(a["flows"]) >= 5:
            _err("The Pro plan allows 5 flows; Premium allows more.", "plan_limit")
        fid = _next(a, "f")
        a["flows"][fid] = {"id": fid, "name": name, "enabled": False, "trigger": dict(trigger), "graph": __import__("copy").deepcopy(graph), "version": 0,
                           "published_at": None, "updated_at": ISO(), "created_at": ISO(), "versions": []}
        return {"flow_id": fid}
    f = _flow(a, d["flow_id"])
    if action == "get":
        return {"flow": {k: v for k, v in f.items() if k != "versions"}, "issues": check_flow(f["graph"], f["trigger"])}
    if action == "update":
        for key in ("name", "trigger", "graph"):
            if d.get(key) is not None:
                f[key] = d[key]
        f["updated_at"] = ISO()
        return {"issues": check_flow(f["graph"], f["trigger"])}
    if action == "delete":
        del a["flows"][f["id"]]
        return {"deleted": True}
    if action == "check":
        issues = check_flow(f["graph"], f["trigger"])
        return {"issues": issues, "valid": not [i for i in issues if i["severity"] == "error"]}
    if action == "publish":
        issues = check_flow(f["graph"], f["trigger"])
        errors = [i for i in issues if i["severity"] == "error"]
        if errors:
            _err("; ".join(i["message"] for i in errors), "flow_invalid", {"issues": issues})
        f["version"] += 1
        f["published_at"] = ISO()
        f["versions"].insert(0, {"version": f["version"], "published_at": f["published_at"], "graph": __import__("copy").deepcopy(f["graph"]), "trigger": dict(f["trigger"])})
        return {"version": f["version"], "issues": issues}
    if action == "versions":
        return {"versions": [{"version": v["version"], "published_at": v["published_at"]} for v in f["versions"]]}
    if action == "rollback":
        v = next((x for x in f["versions"] if x["version"] == int(d["version"])), None)
        if v is None:
            _err("That version was never published.", "unknown_version")
        f["graph"], f["trigger"] = __import__("copy").deepcopy(v["graph"]), dict(v["trigger"])
        f["version"] += 1
        f["published_at"] = ISO()
        f["versions"].insert(0, {"version": f["version"], "published_at": f["published_at"], "graph": v["graph"], "trigger": v["trigger"]})
        return {"version": f["version"]}
    if action == "set_enabled":
        if d.get("enabled") and f["version"] < 1:
            _err("Publish the flow before switching it on.", "not_published")
        f["enabled"] = bool(d.get("enabled"))
        return {}
    if action == "runs":
        return {"runs": []}
    raise KeyError(route)


def _autos_route(route, d, a, s, p):
    from addons.whatsapp import demo_autos
    return demo_autos.handle(route, d, p, s, a)


# ── AI agents: see demo_agents.py ────────────────────────────────────────────


def _ai(route, d, a, s, p):
    from addons.whatsapp import demo_agents
    return demo_agents.handle(route, d, p, s, a)


# ── repeating campaigns and test sends ───────────────────────────────────────

def _schedules(route, d, a, s, p):
    action = route.split("/", 1)[1]
    if action == "list":
        return {"schedules": [dict(x) for x in a["schedules"]]}
    if action == "create":
        rule = d.get("rule") or {}
        if rule.get("freq") not in ("daily", "weekly", "monthly"):
            _err("Choose how often: daily, weekly or monthly.", "bad_rule")
        if rule["freq"] == "weekly" and not rule.get("days"):
            _err("Choose the days of the week.", "bad_rule")
        if not (d.get("config") or {}).get("template_name"):
            _err("Choose a template and an audience.", "bad_config")
        item = {"id": _next(a, "sc"), "name": (d.get("name") or "").strip() or "Repeating campaign", "config": d["config"], "rule": rule, "enabled": True,
                "next_run_at": ISO(NOW() + timedelta(days=1)), "last_run_at": None, "runs": 0, "failures": 0, "last_error": None, "created_at": ISO()}
        a["schedules"].append(item)
        return {"schedule_id": item["id"]}
    item = next((x for x in a["schedules"] if x["id"] == d.get("schedule_id")), None)
    if item is None:
        _err("That repeating campaign is not in this workspace.", "unknown_schedule")
    if action == "set_enabled":
        item["enabled"] = bool(d.get("enabled"))
        item["next_run_at"] = ISO(NOW() + timedelta(days=1)) if item["enabled"] else None
        item["failures"], item["last_error"] = 0, None
        return {"schedule": dict(item)}
    if action == "delete":
        a["schedules"].remove(item)
        return {"deleted": True}
    raise KeyError(route)


def _campaign_extras(route, d, a, s, p):
    if route != "campaigns/test":
        raise KeyError(route)
    digits = "".join(ch for ch in str(d.get("to") or "") if ch.isdigit())
    if len(digits) < 10:
        _err("That is not a phone number; write it with the country code, like 919812345678.", "bad_number")
    tmpl = next((t for t in p["templates"] if t["name"] == d.get("template_name")), None)
    if tmpl is None or tmpl["status"] != "APPROVED":
        _err("Only an approved template can be sent.", "template_not_approved")
    for v in sorted(set(re.findall(r"\{\{\s*(\d+)\s*\}\}", tmpl["components"][0].get("text", "")))):
        if v not in (d.get("variables") or {}):
            _err("Template variable {{%s}} has no value." % v, "variable_unmapped")
    return {"result": {"outbox_id": _next(a, "o"), "to": digits, "contact_id": "k-test"}}
