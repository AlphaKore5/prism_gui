"""Sample answers for the enterprise and reseller screens: the audit log, single sign-on, branding, resellers and commission, and coexistence with the WhatsApp Business app.

Answers POST /v1/whatsapp/p/audit|sso|partner|coexistence/* from memory in the shapes prism-wa returns (audit.py, sso.py, partner.py, coexistence.py, ops_partner.py), so the Settings
sections can be built, shown and tested offline. Reached only through demo_platform.handle (PRISM_WHATSAPP_DEMO=1, never in a frozen build). The demo workspace is an Enterprise one,
and "the company provider" answers after two looks, with the team member whose e-mail is asha@shakti.example.

STDLIB ONLY.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone

from addons.whatsapp import shop_money as M
from addons.whatsapp.license_client import PlatformError

NOW = lambda: datetime.now(timezone.utc)                                              # noqa: E731
ISO = lambda d=None: (d or NOW()).strftime("%Y-%m-%dT%H:%M:%SZ")                      # noqa: E731
COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
DEMO_CODE = "DEMO0000CODE0001"


def _err(message: str, reason: str):
    raise PlatformError(message, reason, {})


def _ent(p: dict) -> dict:
    if "ent" not in p:
        ago = lambda **k: ISO(NOW() - timedelta(**k))                                  # noqa: E731
        rows = [("team.update", "team member", "Changed a team member", "You (owner)", ago(days=6)), ("templates.create", "template", "Submitted a template: diwali_offer", "Meera (manager)", ago(days=5)),
                ("campaigns.launch", "campaign", "Launched a campaign", "Meera (manager)", ago(days=5, hours=-1)), ("api.key_create", "API key", "Made an API key: Zapier", "You (owner)", ago(days=3)),
                ("shop.settings", "shop settings", "Changed the shop settings", "You (owner)", ago(days=2)), ("shop.refund", "payment", "Gave money back", "Meera (manager)", ago(days=1)),
                ("contacts.export", "contacts", "Downloaded contacts", "You (owner)", ago(hours=7)), ("sso.login", "", "Asha Shah signed in with the company account", "Asha Shah (agent)", ago(hours=2))]
        p["ent"] = {"seq": 100, "audit": [{"id": i + 1, "at": at, "actor_id": None, "actor": who, "source": "sso" if action.startswith("sso") else "app", "action": action, "target_kind": kind,
                                           "target_id": None, "summary": words, "detail": None} for i, (action, kind, words, who, at) in enumerate(rows)],
                    "sso": {"enabled": False, "issuer": None, "client_id": None, "client_secret_set": False, "authorize_url": None, "token_url": None, "jwks_url": None, "allowed_domains": [],
                            "role_claim": None, "role_map": {}, "default_role": "agent", "require_sso": False, "updated_at": None, "ready": False}, "sso_states": {},
                    "branding": {"name": None, "colour": None, "logo_asset_id": None, "support_email": None, "support_url": None, "custom_domain": None, "hide_vendor": False, "updated_at": None},
                    "customers": [], "ledger": [], "reseller": None, "invite": None,
                    "numbers": [{"id": "n1", "phone_number_id": "109876543210987", "display": "+91 98765 43210", "status": "connected", "coexistence": False, "state": None}]}
    return p["ent"]


def _record(e: dict, action: str, kind: str, words: str) -> None:
    e["seq"] += 1
    e["audit"].append({"id": e["seq"], "at": ISO(), "actor_id": "a1", "actor": "You (owner)", "source": "app", "action": action, "target_kind": kind, "target_id": None, "summary": words, "detail": None})


def handle(route: str, d: dict, p: dict, s: dict):
    area = route.split("/", 1)[0]
    if area not in ("audit", "sso", "partner", "coexistence"):
        return None
    e = _ent(p)
    action = route.split("/", 1)[1]

    if area == "audit":
        rows = list(e["audit"])
        if d.get("action"):
            rows = [r for r in rows if r["action"].startswith(d["action"])]
        if d.get("actor"):
            rows = [r for r in rows if d["actor"].lower() in (r["actor"] or "").lower()]
        if d.get("q"):
            rows = [r for r in rows if d["q"].lower() in (r["summary"] or "").lower()]
        rows.sort(key=lambda r: (r["at"], r["id"]), reverse=True)
        if action == "export":
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(["when", "who", "through", "action", "kind", "target", "what happened"])
            for r in reversed(rows):
                w.writerow([r["at"], r["actor"], r["source"], r["action"], r["target_kind"] or "", r["target_id"] or "", r["summary"]])
            return {"csv": out.getvalue()}
        lim, off = int(d.get("limit") or 100), int(d.get("offset") or 0)
        return {"entries": rows[off:off + lim], "total": len(rows), "areas": sorted({r["action"].split(".")[0] for r in e["audit"]})}

    if area == "sso":
        c = e["sso"]
        if action == "config":
            return {"config": dict(c)}
        if action == "save":
            for key, what in (("issuer", "The issuer"), ("authorize_url", "The sign-in address"), ("token_url", "The token address"), ("jwks_url", "The keys address")):
                if key in d:
                    v = str(d[key] or "").strip()
                    if v and not v.startswith("https://"):
                        _err("%s must start with https://" % what, "bad_url")
                    c[key] = v.rstrip("/") or None
            if "client_id" in d:
                c["client_id"] = (str(d["client_id"] or "").strip()[:200]) or None
            if "allowed_domains" in d:
                doms = []
                for x in d["allowed_domains"] or []:
                    x = str(x).strip().lower().lstrip("@")
                    if x and not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", x):
                        _err("%r is not an e-mail domain (like company.com)" % x, "bad_domain")
                    if x and x not in doms:
                        doms.append(x)
                c["allowed_domains"] = doms
            if "role_claim" in d:
                c["role_claim"] = (str(d["role_claim"] or "").strip()[:60]) or None
            if "role_map" in d:
                for v in (d["role_map"] or {}).values():
                    if v not in ("agent", "manager"):
                        _err("A provider group can map to: agent, manager. (Owners are never set by the provider.)", "bad_role")
                c["role_map"] = dict(d["role_map"] or {})
            if "default_role" in d:
                if d["default_role"] not in ("agent", "manager"):
                    _err("The default role is one of: agent, manager.", "bad_role")
                c["default_role"] = d["default_role"]
            if (d.get("client_secret") or "").strip():
                c["client_secret_set"] = True
            for flag in ("enabled", "require_sso"):
                if flag in d:
                    c[flag] = bool(d[flag])
            c["ready"] = bool(c["issuer"] and c["client_id"] and c["client_secret_set"])
            if (c["enabled"] or c["require_sso"]) and not c["ready"]:
                c["enabled"] = c["require_sso"] = False
                _err("Add the issuer, client id and client secret before switching single sign-on on.", "not_ready")
            if c["require_sso"] and not c["enabled"]:
                c["require_sso"] = False
                _err("Switch single sign-on on before requiring it.", "not_ready")
            c["updated_at"] = ISO()
            _record(e, "sso.settings", "single sign-on", "Changed the single sign-on settings")
            return {"config": dict(c)}
        if action == "test":
            if not (c["issuer"] or c["authorize_url"]):
                _err("Enter the issuer address first.", "not_ready")
            return {"authorize_url": (c["issuer"] or "https://login.example") + "/authorize", "token_url": (c["issuer"] or "https://login.example") + "/token", "keys": 2,
                    "has_secret": c["client_secret_set"]}
        if action == "start":
            if not (c["enabled"] and c["ready"]):
                _err("Single sign-on is not switched on for this workspace.", "not_enabled")
            e["seq"] += 1
            state = "demo-sso-%d" % e["seq"]
            e["sso_states"][state] = {"polls": 0, "done": False}
            return {"state": state, "url": "%s/authorize?state=%s" % (c["issuer"], state)}
        if action == "status":
            st = e["sso_states"].get(d.get("state"))
            if st is None:
                _err("That sign-in was not started here, or was already used.", "unknown_state")
            if st["done"]:
                return {"status": "used"}
            st["polls"] += 1
            if st["polls"] < 2:
                return {"status": "waiting"}
            st["done"] = True
            _record(e, "sso.login", "", "Asha Shah signed in with the company account")
            return {"status": "ready", "result": {"agent_id": "a2", "name": "Asha Shah", "email": "asha@shakti.example", "role": "agent", "token": "demo-sso-token", "expires_hours": 12}}
        return None

    if area == "partner":
        if action == "branding/get" or action == "branding/effective":
            b = dict(e["branding"])
            if action == "branding/effective":
                return {"branding": {**b, "from": "own" if b["name"] else "none"}}
            return {"branding": b, "effective": {**b, "from": "own" if b["name"] else "none"}}
        if action == "branding/save":
            b = e["branding"]
            if "name" in d:
                b["name"] = (str(d["name"] or "").strip()[:60]) or None
            if "colour" in d:
                col = str(d["colour"] or "").strip()
                if col and not COLOUR.match(col):
                    _err("A colour is six hex digits after a #, like #1A7F4B.", "bad_colour")
                b["colour"] = col.upper() or None
            if "support_email" in d:
                m = str(d["support_email"] or "").strip()
                if m and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", m):
                    _err("That support e-mail address is not valid.", "bad_email")
                b["support_email"] = m or None
            if "support_url" in d:
                u = str(d["support_url"] or "").strip()
                if u and not re.match(r"^https://\S+$", u):
                    _err("The support page address must start with https://", "bad_url")
                b["support_url"] = u or None
            if "custom_domain" in d:
                dom = str(d["custom_domain"] or "").strip().lower()
                if dom and not re.match(r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", dom):
                    _err("That is not a domain name (like app.yourbrand.com).", "bad_domain")
                b["custom_domain"] = dom or None
            if "hide_vendor" in d:
                b["hide_vendor"] = bool(d["hide_vendor"])
            b["updated_at"] = ISO()
            _record(e, "partner.branding", "branding", "Changed the branding")
            return {"branding": dict(b)}
        if action == "invite":
            if e["reseller"]:
                _err("This workspace already has a reseller. Unlink it first.", "already_linked")
            e["invite"] = DEMO_CODE
            return {"code": "-".join(DEMO_CODE[i:i + 4] for i in range(0, 16, 4)), "hours": 72}
        if action == "redeem":
            code = re.sub(r"[^A-Za-z0-9]", "", d.get("code") or "").upper()
            try:
                pct = float(d.get("commission_percent") if d.get("commission_percent") not in (None, "") else 0)
            except (TypeError, ValueError):
                _err("The commission is a percentage, like 20.", "bad_percent")
            if not 0 <= pct <= 100:
                _err("The commission is between 0 and 100 percent.", "bad_percent")
            if code != DEMO_CODE or any(c["child_tenant_id"] == "t-customer" for c in e["customers"]):
                _err("That code is not valid, or it has expired or been used. Ask the customer for a new one.", "bad_code")
            e["customers"].append({"child_tenant_id": "t-customer", "name": "Customer Traders", "commission_percent": pct, "note": (d.get("note") or None), "linked_at": ISO(),
                                   "sent": 412, "received": 389, "contacts": 96})
            _record(e, "partner.link", "customer workspace", "Linked a customer workspace")
            return {"child_tenant_id": "t-customer"}
        if action == "unlink":
            n = len(e["customers"])
            e["customers"] = [c for c in e["customers"] if c["child_tenant_id"] != d.get("child_tenant_id")] if d.get("child_tenant_id") else e["customers"]
            if not d.get("child_tenant_id"):
                gone, e["reseller"] = e["reseller"] is not None, None
                return {"unlinked": gone}
            _record(e, "partner.unlink", "customer workspace", "Unlinked a customer workspace")
            return {"unlinked": len(e["customers"]) < n}
        if action == "customers":
            return {"customers": [dict(c) for c in e["customers"]]}
        if action == "reseller":
            return {"reseller": e["reseller"]}
        if action == "set_percent":
            c = next((x for x in e["customers"] if x["child_tenant_id"] == d.get("child_tenant_id")), None)
            if c is None:
                _err("That customer is not linked to this workspace.", "unknown_customer")
            pct = float(d["commission_percent"])
            if not 0 <= pct <= 100:
                _err("The commission is between 0 and 100 percent.", "bad_percent")
            c["commission_percent"] = pct
            return {"saved": True}
        if action == "ledger/add":
            c = next((x for x in e["customers"] if x["child_tenant_id"] == d.get("child_tenant_id")), None)
            if c is None:
                _err("That customer is not linked to this workspace.", "unknown_customer")
            if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", d.get("period") or ""):
                _err("A period is a month like 2026-10.", "bad_period")
            try:
                base = M.paise(d.get("base"), what="base amount")
            except M.MoneyError as why:
                _err(str(why), "bad_amount")
            amount = int(base * c["commission_percent"] / 100.0 + 0.5)
            old = next((x for x in e["ledger"] if x["child_tenant_id"] == c["child_tenant_id"] and x["period"] == d["period"]), None)
            if old and old["status"] == "paid":
                _err("The commission for %s was already paid and cannot be changed." % d["period"], "already_paid")
            if old:
                old.update(base_paise=base, percent=c["commission_percent"], amount_paise=amount, note=d.get("note") or None)
                return {"id": old["id"], "base_paise": base, "percent": c["commission_percent"], "amount_paise": amount}
            e["seq"] += 1
            e["ledger"].append({"id": e["seq"], "child_tenant_id": c["child_tenant_id"], "period": d["period"], "base_paise": base, "percent": c["commission_percent"], "amount_paise": amount,
                                "status": "accrued", "note": d.get("note") or None, "created_at": ISO()})
            return {"id": e["seq"], "base_paise": base, "percent": c["commission_percent"], "amount_paise": amount}
        if action == "ledger/list":
            rows = sorted(e["ledger"], key=lambda r: (r["period"], r["id"]), reverse=True)
            return {"entries": [dict(r) for r in rows], "owed_paise": sum(r["amount_paise"] for r in rows if r["status"] == "accrued"),
                    "paid_paise": sum(r["amount_paise"] for r in rows if r["status"] == "paid")}
        if action == "ledger/paid":
            r = next((x for x in e["ledger"] if x["id"] == d.get("entry_id") and x["status"] == "accrued"), None)
            if r is not None:
                r["status"] = "paid"
            return {"paid": r is not None}
        return None

    if area == "coexistence":
        if action == "numbers":
            return {"numbers": [dict(n) for n in e["numbers"]]}
        n = next((x for x in e["numbers"] if x["id"] == d.get("number_id")), None)
        if action in ("sync", "mark") and n is None:
            _err("that number is not in this workspace", "unknown_number")
        if action == "mark":
            n["coexistence"] = d.get("enabled") is not False
            n["state"] = ({"contacts": "requested", "history": "importing", "history_progress": 40, "history_messages": 128, "contacts_imported": 31, "last_echo_at": ISO()}
                          if n["coexistence"] else None)
            return {"numbers": [dict(x) for x in e["numbers"]]}
        if action == "sync":
            if not n["coexistence"]:
                _err("this number was not connected alongside the WhatsApp Business app", "not_coexistence")
            n["state"] = dict(n["state"] or {}, requested_at=ISO(), contacts="requested", history_request="requested")
            return {"contacts": "requested", "history": "requested"}
    return None
