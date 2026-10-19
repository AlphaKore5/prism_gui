"""Sample answers for the contact book: the Contacts table, the chat profile, tags and attributes, imports.

Answers POST /v1/whatsapp/p/<route> from memory in the shapes prism-wa's ops_book.py returns, so the Contacts and
profile screens run and are tested offline. Reached only through demo_platform.handle (PRISM_WHATSAPP_DEMO=1, never in a
frozen build). The contacts themselves are the demo's own (demo.py); what is added here lives in demo_platform._PAGE["book"].

The filter matcher below is a small look-alike of prism-wa's segments.py: enough operators to behave like the real one on
the screens. The real rules live in prism-wa.

STDLIB ONLY.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone

from addons.whatsapp.license_client import PlatformError

NOW = lambda: datetime.now(timezone.utc)                                              # noqa: E731
ISO = lambda d=None: (d or NOW()).strftime("%Y-%m-%dT%H:%M:%SZ")                      # noqa: E731


def _ago(delta: timedelta) -> str:
    return ISO(NOW() - delta)




def _err(message: str, reason: str):
    raise PlatformError(message, reason, {})


def _book(p: dict) -> dict:
    if "book" not in p:
        p["book"] = {"seq": 100, "tags": {}, "attrs": [
            {"key": "City", "type": "string", "global": False, "options": None, "value": None},
            {"key": "Budget", "type": "number", "global": False, "options": None, "value": None}],
            "values": {"k1": {"City": "Vadodara", "Budget": 450000}, "k2": {"City": "Surat"}, "k4": {"City": "Vadodara"}},
            "events": {}, "imports": [], "meta": {}}
    return p["book"]


def _meta(b: dict, c: dict) -> dict:
    """What the demo contacts do not carry on their own: source, consent, window, when they were added."""
    n = int(re.sub(r"\D", "", c["id"]) or 0)
    return b["meta"].setdefault(c["id"], {
        "source": "ORGANIC" if n % 3 else "IMPORT", "opted_in": not c.get("opt_out"), "blocked": False,
        "first_msg_tag": "Website" if n % 4 == 0 else "", "created_at": _ago(timedelta(days=3 * n + 2)),
        "last_seen": _ago(timedelta(hours=2 * n)) if n % 5 else None})


def _row(c: dict, p: dict, s: dict) -> dict:
    from addons.whatsapp import demo_automation
    b = _book(p)
    m = _meta(b, c)
    conv = next((cv for cv in s["conversations"] if cv["contact_id"] == c["id"]), None)
    state = demo_automation._auto(p)["conv"].get(conv["id"], {}).get("status", "active") if conv else None
    last = m["last_seen"]
    if conv is not None:                                         # who wrote last is whatever the chat says, so the two screens agree
        stamps = [x["created_at"] for x in s["threads"].get(conv["id"], []) if x.get("direction") == "in"]
        last = max(stamps) if stamps else None
    window = False
    if last:
        window = NOW() - datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) < timedelta(hours=24)
    return {"id": c["id"], "name": c["name"], "phone": c["phone"], "email": c.get("email") or "", "company": c.get("company") or "",
            "tags": list(c["tags"]), "source": m["source"], "opted_in": bool(m["opted_in"] and not c.get("opt_out")),
            "opted_out": bool(c.get("opt_out")), "blocked": bool(m["blocked"]), "first_msg_tag": m["first_msg_tag"],
            "last_seen": last, "created_at": m["created_at"], "state": state, "window_open": window,
            "attrs": dict(b["values"].get(c["id"], {}))}


# ── the filter ───────────────────────────────────────────────────────────────

def _when(value) -> datetime:
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None


def matches(row: dict, flt, defs: dict, p: dict = None, s: dict = None) -> bool:
    if not flt:
        return True
    if "all" in flt:
        return all(matches(row, f, defs, p, s) for f in flt["all"])
    if "any" in flt:
        return any(matches(row, f, defs, p, s) for f in flt["any"])
    if "not" in flt:
        return not matches(row, flt["not"], defs, p, s)
    if "tags" in flt and "field" not in flt:
        return not flt["tags"] or bool(set(flt["tags"]) & set(row["tags"]))
    field, op, value = flt.get("field"), flt.get("op"), flt.get("value")
    low = lambda x: str(x or "").lower()                                                # noqa: E731
    if field in ("name", "email", "first_msg_tag"):
        have = low(row[field])
        return {"is_set": have != "", "is_not_set": have == "", "eq": have == low(value), "ne": have != low(value),
                "contains": low(value) in have, "starts_with": have.startswith(low(value))}.get(op, False)
    if field == "mobile":
        have, want = re.sub(r"\D", "", row["phone"]), re.sub(r"\D", "", str(value or ""))
        return {"eq": have.endswith(want) and len(want) >= 10, "starts_with": have.startswith(want), "contains": want in have}.get(op, False)
    if field == "tags":
        have, want = set(row["tags"]), set(value if isinstance(value, list) else [value])
        return {"has": bool(have & want), "has_any": bool(have & want), "has_all": want <= have, "has_none": not (have & want)}.get(op, False)
    if field == "source":
        return row["source"] in (value if isinstance(value, list) else [value])
    if field in ("opted_in", "opted_out", "blocked"):
        return bool(row[field]) is bool(value)
    if field in ("created", "last_seen"):
        have = row["created_at" if field == "created" else "last_seen"]
        if op in ("within_days", "older_than_days"):
            cutoff = NOW() - timedelta(days=int(value))
            ts = _when(have) if have else None
            if op == "within_days":
                return bool(ts and ts >= cutoff)
            return ts is None or ts < cutoff
        ts = _when(have) if have else None
        return bool(ts and (ts < _when(value) if op == "before" else ts >= _when(value)))
    if field == "conversation_status":
        return row["state"] in (value if isinstance(value, list) else [value])
    if field == "campaign":
        return row["id"] in ("k1", "k2", "k4")
    if field and field.startswith("attr:"):
        key = field[5:]
        have = row["attrs"].get(key)
        if op == "is_set":
            return have is not None
        if op == "is_not_set":
            return have is None
        if have is None:
            return op == "ne"
        kind = (defs.get(key) or {}).get("type", "string")
        if kind == "number":
            h = _num(have)
            if op == "between":
                lo, hi = (_num(x) for x in (value if isinstance(value, list) and len(value) == 2 else (None, None)))
                return h is not None and lo is not None and hi is not None and lo <= h <= hi
            v = _num(value)
            if h is None or v is None:
                return False
            return {"eq": h == v, "ne": h != v, "gt": h > v, "gte": h >= v, "lt": h < v, "lte": h <= v}.get(op, False)
        h = low(have)
        if isinstance(value, list):
            return h in [low(x) for x in value] if op == "in" else (str(value[0]) <= str(have) <= str(value[1]) if op == "between" else False)
        v = low(value)
        return {"eq": h == v, "ne": h != v, "contains": v in h, "starts_with": h.startswith(v), "in": h == v,
                "gt": str(have) > str(value), "lt": str(have) < str(value)}.get(op, False)
    return True


def _defs(b: dict) -> dict:
    return {a["key"]: a for a in b["attrs"]}


def _filtered(p: dict, s: dict, flt, search: str = "") -> list:
    b = _book(p)
    defs = _defs(b)
    term = (search or "").strip().lower()
    out = []
    for c in s["contacts"]:
        r = _row(c, p, s)
        if term and term not in (r["name"] + " " + r["phone"] + " " + r["email"] + " " + r["company"]).lower():
            continue
        if matches(r, flt, defs, p, s):
            out.append(r)
    return out


def _event(b: dict, cid: str, kind: str, who: str = "You", detail: dict = None):
    b["events"].setdefault(cid, []).append({"kind": kind, "who": who, "detail": detail or {}, "at": ISO()})


# ── the routes ───────────────────────────────────────────────────────────────

def handle(route: str, d: dict, p: dict, s: dict):
    """The answer, or None when this route is not the contact book's."""
    b = _book(p)
    if route == "contacts/list":
        rows = _filtered(p, s, d.get("filter"), d.get("search") or "")
        key = {"name": lambda r: r["name"].lower(), "created": lambda r: r["created_at"], "last_seen": lambda r: r["last_seen"] or "",
               "source": lambda r: r["source"], "phone": lambda r: r["phone"], "tags": lambda r: len(r["tags"])}.get(d.get("sort") or "created",
                                                                                                                      lambda r: r["created_at"])
        rows.sort(key=key, reverse=(d.get("direction") or "desc") != "asc")
        off, lim = int(d.get("offset") or 0), int(d.get("limit") or 50)
        return {"contacts": rows[off:off + lim], "total": len(rows), "attribute_keys": sorted(_defs(b))}
    if route == "contacts/get":
        c = next((x for x in s["contacts"] if x["id"] == d.get("contact_id")), None)
        if c is None:
            _err("That person is not in this workspace.", "unknown_contact")
        row = _row(c, p, s)
        row["assignee_id"], row["assignee_name"] = None, None
        row["counts"] = {"template_messages": 2 if row["opted_in"] else 0, "session_messages": len(s["threads"].get("c" + c["id"][1:], [])),
                         "unresolved_queries": 1 if row["state"] == "requesting" else 0}
        row["campaigns"] = [{"id": "c1", "name": "Diwali offer", "template": "diwali_offer", "status": "sent", "at": _ago(timedelta(days=2))}] \
            if c["id"] in ("k1", "k2", "k4") else []
        row["consent"] = [{"action": "opt_in", "source": "csv_import", "evidence": "attested at import", "at": row["created_at"]}] if row["opted_in"] else []
        return {"contact": row}
    if route == "contacts/journey":
        cid = d.get("contact_id")
        c = next((x for x in s["contacts"] if x["id"] == cid), None)
        if c is None:
            _err("That person is not in this workspace.", "unknown_contact")
        events = list(b["events"].get(cid, []))
        events.append({"kind": "created", "who": None, "detail": {"source": _meta(b, c)["source"]}, "at": _meta(b, c)["created_at"]})
        if cid in ("k1", "k2", "k4"):
            events.append({"kind": "campaign_sent", "who": None, "detail": {"campaign": "Diwali offer", "status": "sent"}, "at": _ago(timedelta(days=2))})
        events.sort(key=lambda e: e["at"], reverse=True)
        return {"journey": events}
    if route == "contacts/create":
        digits = re.sub(r"\D", "", str(d.get("phone") or ""))
        if len(digits) == 10:
            digits = "91" + digits
        if len(digits) < 11:
            _err("%r is not a valid phone number. Use the country code, e.g. 919812345678." % (d.get("phone"),), "bad_phone")
        existing = next((c for c in s["contacts"] if c["phone"] == digits), None)
        if existing is None:
            b["seq"] += 1
            existing = {"id": "k%d" % b["seq"], "name": (d.get("name") or "").strip() or digits, "phone": digits, "email": d.get("email") or "",
                        "company": "", "tags": [], "opt_out": False}
            s["contacts"].append(existing)
            created = True
        else:
            created = False
            if d.get("name"):
                existing["name"] = d["name"].strip()
        existing["tags"] = sorted(set(existing["tags"]) | {t for t in (d.get("tags") or []) if t})
        for t in existing["tags"]:
            pass
        for k, v in (d.get("attributes") or {}).items():
            if v not in (None, ""):
                b["values"].setdefault(existing["id"], {})[k] = v
        _meta(b, existing).update(source=d.get("source") or "MANUAL", opted_in=bool(d.get("attest_consent")) or _meta(b, existing)["opted_in"])
        _event(b, existing["id"], "created" if created else "updated")
        return {"contact_id": existing["id"], "created": created}
    if route == "contacts/update":
        c = next((x for x in s["contacts"] if x["id"] == d.get("contact_id")), None)
        if c is None:
            _err("That person is not in this workspace.", "unknown_contact")
        ch = d.get("changes") or {}
        for key in ("name", "email", "company"):
            if key in ch:
                if key == "name" and not (ch[key] or "").strip():
                    _err("A contact needs a name.", "bad_name")
                c[key] = (ch[key] or "").strip()
        for k, v in (ch.get("attributes") or {}).items():
            if k not in _defs(b):
                _err("%s: there is no attribute called %r" % (k, k), "bad_attribute")
            if v in (None, ""):
                b["values"].get(c["id"], {}).pop(k, None)
            else:
                b["values"].setdefault(c["id"], {})[k] = v
                _event(b, c["id"], "attribute_set", detail={"key": k, "value": v})
        return {"contact": _row(c, p, s)}
    if route in ("contacts/block", "contacts/delete", "contacts/tags/set"):
        ids = d.get("contact_ids") or [r["id"] for r in _filtered(p, s, d.get("filter"))]
        if not ids:
            raise PlatformError("choose at least one person", "bad_request", {})
        if route == "contacts/block":
            for c in s["contacts"]:
                if c["id"] in ids:
                    _meta(b, c)["blocked"] = bool(d.get("blocked", True))
                    _event(b, c["id"], "blocked" if d.get("blocked", True) else "unblocked")
            return {"changed": len(ids)}
        if route == "contacts/delete":
            s["contacts"] = [c for c in s["contacts"] if c["id"] not in ids]
            return {"deleted": len(ids)}
        add, remove = [t.strip() for t in d.get("add") or [] if t.strip()], set(d.get("remove") or [])
        if not (add or remove):
            raise PlatformError("say which tags to add or remove", "bad_request", {})
        changed = 0
        for c in s["contacts"]:
            if c["id"] in ids:
                new = sorted((set(c["tags"]) | set(add)) - remove)
                if new != sorted(c["tags"]):
                    changed += 1
                    _event(b, c["id"], "tag_added" if add else "tag_removed", detail={"tags": add or sorted(remove)})
                c["tags"] = new
        return {"changed": changed}
    if route == "contacts/consent":
        c = next((x for x in s["contacts"] if x["id"] == d.get("contact_id")), None)
        if c is None:
            _err("That person is not in this workspace.", "unknown_contact")
        if d.get("action") not in ("opt_in", "opt_out"):
            raise PlatformError("action must be opt_in or opt_out", "bad_request", {})
        out = d["action"] == "opt_out"
        changed = bool(c.get("opt_out")) != out
        c["opt_out"] = out
        _meta(b, c)["opted_in"] = not out
        _event(b, c["id"], d["action"], detail={"source": "manual"})
        return {"changed": changed, "opted_in": not out, "opted_out": out}
    if route == "contacts/export":
        rows = _filtered(p, s, d.get("filter")) if d.get("filter") else [_row(c, p, s) for c in s["contacts"]]
        if d.get("contact_ids"):
            rows = [r for r in rows if r["id"] in d["contact_ids"]] if d.get("filter") else [_row(c, p, s) for c in s["contacts"] if c["id"] in d["contact_ids"]]
        keys = sorted(_defs(b))
        lines = ["Name,Mobile,Email,Tags,Opted in,Opted out,Source" + "".join("," + k for k in keys)]
        for r in rows:
            lines.append(",".join([r["name"], r["phone"], r["email"], "|".join(r["tags"]), "yes" if r["opted_in"] else "no",
                                   "yes" if r["opted_out"] else "no", r["source"]] + [str(r["attrs"].get(k, "")) for k in keys]))
        return {"csv": "\n".join(lines) + "\n"}
    if route == "messages/send_template":
        tpl = next((t for t in p["templates"] if t["name"] == d.get("template_name")), None)
        if tpl is None:
            _err("That template is not known for this account. Update your templates from Meta first.", "unknown_template")
        if tpl["status"] != "APPROVED":
            _err("The template is %s; only an approved template can be sent." % tpl["status"].lower(), "template_not_approved")
        c = next((x for x in s["contacts"] if x["id"] == d.get("contact_id")), None)
        if c is None:
            _err("That person is not in this workspace.", "unknown_contact")
        if c.get("opt_out"):
            _err("this contact has opted out of business-initiated messages", "opted_out")
        body = [v for v in d.get("body") or [] if str(v).strip()]
        needed = len(set(re.findall(r"\{\{\s*(\d+)\s*\}\}", (tpl["components"][0] or {}).get("text", ""))))
        if len(body) != needed:
            _err("Fill in all %d values for the message." % needed, "missing_value")
        _event(b, c["id"], "campaign_sent", detail={"campaign": "Template “%s”" % tpl["name"], "status": "sent"})
        return {"queued": True, "outbox_id": "o1"}
    if route == "contacts/imports":
        return {"imports": [dict(i) for i in reversed(b["imports"])]}
    if route == "contacts/imports/get":
        got = next((i for i in b["imports"] if i["id"] == d.get("import_id")), None)
        if got is None:
            _err("That import is not in this workspace.", "unknown_import")
        csv_text = "Row,Why it did not import\n" + "\n".join("%s,%s" % (e["row"], e["error"]) for e in got["report"].get("errors", []))
        return {"report": got["report"], "file_name": got["file_name"], "at": got["at"], "failures_csv": csv_text + "\n"}
    if route == "contacts/import":
        return _import(d, b, s, p)

    if route == "tags/list":
        used = {}
        for c in s["contacts"]:
            for t in c["tags"]:
                used[t] = used.get(t, 0) + 1
        names = sorted(set(used) | set(b["tags"]), key=str.lower)
        return {"tags": [{"name": n, "color": b["tags"].get(n), "contacts": used.get(n, 0), "registered": n in b["tags"]} for n in names]}
    if route == "tags/create":
        name = (d.get("name") or "").strip()
        if not name or len(name) > 60 or re.search(r"[|;,]", name):
            _err("A tag is 1 to 60 characters and cannot contain a comma, | or ;.", "bad_tag")
        if name in b["tags"]:
            _err("There is already a tag called %r." % name, "tag_exists")
        b["tags"][name] = d.get("color")
        return {"name": name}
    if route == "tags/rename":
        old, new = d.get("old"), (d.get("new") or "").strip()
        known = {t for c in s["contacts"] for t in c["tags"]} | set(b["tags"])
        if old not in known:
            _err("There is no tag called %r." % old, "unknown_tag")
        if new in known and new != old:
            _err("There is already a tag called %r. Delete or merge that one first." % new, "tag_exists")
        n = 0
        for c in s["contacts"]:
            if old in c["tags"]:
                c["tags"] = sorted({new if t == old else t for t in c["tags"]})
                n += 1
        if old in b["tags"]:
            b["tags"][new] = b["tags"].pop(old)
        return {"changed": n}
    if route == "tags/delete":
        n = 0
        for c in s["contacts"]:
            if d.get("name") in c["tags"]:
                c["tags"] = [t for t in c["tags"] if t != d["name"]]
                n += 1
        b["tags"].pop(d.get("name"), None)
        return {"removed_from": n}

    if route == "attributes/list":
        return {"attributes": [dict(a, filled=sum(1 for v in b["values"].values() if a["key"] in v)) for a in b["attrs"]]}
    if route == "attributes/define":
        key = (d.get("key") or "").strip()
        if not re.match(r"^[A-Za-z][A-Za-z0-9_]{0,39}$", key):
            _err("an attribute name starts with a letter and uses letters, numbers and underscores (40 at most)", "bad_attribute")
        if not any(a["key"] == key for a in b["attrs"]):
            b["attrs"].append({"key": key, "type": d.get("type") or "string", "global": bool(d.get("global")), "options": d.get("options"), "value": None})
        return {"attribute": dict(next(a for a in b["attrs"] if a["key"] == key), filled=0)}
    if route == "attributes/delete":
        before = len(b["attrs"])
        b["attrs"] = [a for a in b["attrs"] if a["key"] != d.get("key")]
        for v in b["values"].values():
            v.pop(d.get("key"), None)
        return {"deleted": len(b["attrs"]) < before}
    if route == "attributes/set_global":
        a = next((x for x in b["attrs"] if x["key"] == d.get("key")), None)
        if a is None:
            _err("There is no attribute called %r." % d.get("key"), "unknown_attribute")
        if not a["global"]:
            _err("%r is a per-person attribute. Make it a workspace-wide one first." % a["key"], "not_global")
        a["value"] = d.get("value")
        return {}

    if route == "consent/get":
        return {"settings": dict(b.setdefault("consent", {"opt_out_keywords": ["stop", "unsubscribe", "cancel"], "opt_in_keywords": ["start", "subscribe"],
                                                         "confirm": True, "opt_out_reply": "You have been unsubscribed and will not receive further messages from us. Reply START to subscribe again.",
                                                         "opt_in_reply": "Thank you, you are subscribed again. Reply STOP at any time to opt out."}))}
    if route == "consent/save":
        cur = b.setdefault("consent", {})
        new = dict(cur, **(d.get("settings") or {}))
        for key in ("opt_out_keywords", "opt_in_keywords"):
            if not new.get(key) or len(new[key]) > 5:
                _err("Choose between 1 and 5 keywords.", "bad_settings")
        cur.update(new)
        return {"settings": dict(cur)}
    if route == "segments/count":
        return {"count": len([r for r in _filtered(p, s, d.get("filter")) if not d.get("opted_in_only", True) or (r["opted_in"] and not r["blocked"])])}
    return None


def _import(d: dict, b: dict, s: dict, p: dict) -> dict:
    mapping = d.get("mapping")
    reader = csv.reader(io.StringIO((d.get("csv") or "").lstrip("﻿")))
    try:
        header = next(reader)
    except StopIteration:
        raise PlatformError("The file is empty.", "bad_file", {})
    roles = {}
    for i, raw in enumerate(header):
        if mapping is not None:
            role = (mapping.get(raw) or "ignore").strip()
        else:
            h = raw.strip().lower()
            role = ("name" if h in ("name", "full name", "customer name") else "mobile" if h in ("mobile", "phone", "whatsapp", "number", "mobile number")
                    else "email" if h in ("email",) else "tags" if h in ("tags", "tag") else "source" if h in ("source",) else "attr:" + raw.strip() if h else "ignore")
        if role != "ignore":
            roles.setdefault(role, i)
    if "mobile" not in roles:
        raise PlatformError("The file needs a Mobile column (Mobile, Phone or WhatsApp).", "bad_file", {})
    rep = {"rows": 0, "created": 0, "updated": 0, "invalid": 0, "consent_recorded": 0, "kept_opted_out": 0, "errors": [], "warnings": []}
    for n, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        rep["rows"] += 1
        digits = re.sub(r"\D", "", row[roles["mobile"]] if roles["mobile"] < len(row) else "")
        if len(digits) == 10:
            digits = "91" + digits
        if len(digits) < 11:
            rep["invalid"] += 1
            rep["errors"].append({"row": n, "error": "%r is not a valid phone number" % (row[roles["mobile"]] if roles["mobile"] < len(row) else "")})
            continue
        found = next((c for c in s["contacts"] if c["phone"] == digits), None)
        if found is None:
            b["seq"] += 1
            found = {"id": "k%d" % b["seq"], "name": "", "phone": digits, "email": "", "company": "", "tags": [], "opt_out": False}
            s["contacts"].append(found)
            rep["created"] += 1
        else:
            rep["updated"] += 1
        cell = lambda role: (row[roles[role]].strip() if role in roles and roles[role] < len(row) else "")            # noqa: E731
        found["name"] = cell("name") or found["name"] or digits
        found["email"] = cell("email") or found["email"]
        found["tags"] = sorted(set(found["tags"]) | {t.strip() for t in re.split(r"[|;]", cell("tags")) if t.strip()} | set(d.get("tags") or []))
        _meta(b, found)["source"] = cell("source") or d.get("source") or "IMPORT"
        if d.get("attest_consent"):
            _meta(b, found)["opted_in"] = True
            rep["consent_recorded"] += 1
        for role, i in roles.items():
            if role.startswith("attr:") and i < len(row) and row[i].strip():
                key = role[5:]
                if not any(a["key"] == key for a in b["attrs"]):
                    b["attrs"].append({"key": key, "type": "string", "global": False, "options": None, "value": None})
                b["values"].setdefault(found["id"], {})[key] = row[i].strip()
    b["seq"] += 1
    rep["import_id"] = "i%d" % b["seq"]
    b["imports"].append({"id": rep["import_id"], "file_name": d.get("file_name") or "", "source": d.get("source") or "IMPORT", "by_name": "You",
                         "rows": rep["rows"], "created": rep["created"], "updated": rep["updated"], "invalid": rep["invalid"], "at": ISO(), "report": rep})
    return {"report": rep}
