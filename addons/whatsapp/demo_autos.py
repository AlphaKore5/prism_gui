"""Sample answers for the automatic messages screens: birthdays, reminders and drips.

Answers POST /v1/whatsapp/p/autos/* from memory in the shapes prism-wa returns (autos.py, ops_autos.py), so the screens built on them can be built, shown and tested
offline. Reached only through demo_platform.handle, which is switched on with PRISM_WHATSAPP_DEMO=1 and never in a frozen build.

The preview reads the demo contacts' real dates (the Birthday detail in demo_book), so it shows who would be reached the way the server would. Nothing is ever sent.

STDLIB ONLY.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from addons.whatsapp.license_client import PlatformError

NOW = lambda: datetime.now(timezone.utc)                                              # noqa: E731
ISO = lambda d=None: (d or NOW()).strftime("%Y-%m-%dT%H:%M:%SZ")                      # noqa: E731
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_STEPS = 10
MAX_AUTOS = 30


def _err(message: str, reason: str):
    raise PlatformError(message, reason, {})


def _autos(a: dict) -> dict:
    return a.setdefault("autos", {"seq": 0, "items": {}})


def _template(spec) -> dict:
    spec = spec if isinstance(spec, dict) else {}
    if not str(spec.get("name") or "").strip():
        _err("Choose the template to send.", "bad_template")
    for key, v in (spec.get("variables") or {}).items():
        if isinstance(v, dict) and v.get("source") == "tracked_link":
            _err("Variable %s: A tracked link needs a campaign. Use a plain web address here." % key, "bad_template")
    return {"name": str(spec["name"]).strip(), "language": str(spec.get("language") or "en_US"), "variables": spec.get("variables") or {}}


def clean(p: dict, kind: str, config) -> dict:
    from addons.whatsapp import demo_book
    config = config if isinstance(config, dict) else {}
    if kind == "date":
        attribute = str(config.get("attribute") or "").strip()
        defs = {x["key"]: x for x in demo_book._book(p)["attrs"]}
        if attribute not in defs or defs[attribute]["type"] != "date":
            _err("Choose a contact detail that holds a date (add one in Contacts, Attributes, of the type Date).", "bad_attribute")
        match = config.get("match") or "yearly"
        if match not in ("yearly", "once"):
            _err("A date comes round every year, or happens once.", "bad_match")
        offset = config.get("offset_days", 0)
        if not (isinstance(offset, int) and not isinstance(offset, bool) and -60 <= offset <= 60):
            _err("Send it on the day, or up to 60 days before or after.", "bad_offset")
        time_ = str(config.get("time") or "10:00")
        if not TIME_RE.match(time_):
            _err("The time must look like 10:00.", "bad_time")
        tags = [str(t).strip() for t in (config.get("tags") or []) if str(t).strip()]
        if len(tags) > 5:
            _err("Limit it to up to 5 tags, each up to 40 characters.", "bad_tags")
        return {"attribute": attribute, "match": match, "offset_days": offset, "time": time_, "tz": str(config.get("tz") or "Asia/Kolkata"),
                "template": _template(config.get("template")), "tags": tags}
    if kind != "drip":
        _err("An automatic message is a date message or a drip.", "bad_kind")
    trigger = config.get("trigger") if isinstance(config.get("trigger"), dict) else {}
    ttype = trigger.get("type") or "manual"
    if ttype not in ("tag", "opt_in", "manual"):
        _err("A drip starts when someone gets a tag, opts in, or when you add them.", "bad_trigger")
    if ttype == "tag" and not str(trigger.get("tag") or "").strip():
        _err("Name the tag that starts the drip.", "bad_trigger")
    steps = config.get("steps")
    if not (isinstance(steps, list) and 1 <= len(steps) <= MAX_STEPS):
        _err("A drip has 1 to %d messages." % MAX_STEPS, "bad_steps")
    out_steps = []
    for s in steps:
        delay = (s or {}).get("delay_minutes", 0)
        if not (isinstance(delay, int) and not isinstance(delay, bool) and 0 <= delay <= 90 * 24 * 60):
            _err("Wait from 0 minutes to 90 days between messages.", "bad_delay")
        out_steps.append({"delay_minutes": delay, "template": _template((s or {}).get("template"))})
    stop = config.get("stop") if isinstance(config.get("stop"), dict) else {}
    quiet = config.get("quiet") if isinstance(config.get("quiet"), dict) else None
    if quiet and not (TIME_RE.match(str(quiet.get("from") or "")) and TIME_RE.match(str(quiet.get("to") or "")) and quiet["from"] != quiet["to"]):
        _err("Send between two different times, like 09:00 and 20:00.", "bad_quiet")
    out = {"trigger": {"type": ttype, **({"tag": str(trigger["tag"]).strip()} if ttype == "tag" else {})}, "steps": out_steps,
           "stop": {"on_reply": bool(stop.get("on_reply", True)), "tags": [str(t).strip() for t in (stop.get("tags") or []) if str(t).strip()][:5]},
           "tz": str(config.get("tz") or "Asia/Kolkata"), "include_existing": bool(config.get("include_existing"))}
    if quiet:
        out["quiet"] = {"from": quiet["from"], "to": quiet["to"]}
    return out


def _shown(x: dict) -> dict:
    out = {k: v for k, v in x.items() if k not in ("log", "people")}
    log = x.get("log") or []
    out.update(sent=len([e for e in log if e["state"] == "sent"]), skipped=len([e for e in log if e["state"] == "skipped"]), failed=0,
               active=x.get("active", 0), done=x.get("done", 0), stopped=x.get("stopped", 0), stopped_why=x.get("stopped_why", []))
    return out


def _item(a: dict, auto_id: str) -> dict:
    x = _autos(a)["items"].get(auto_id)
    if x is None:
        _err("That automatic message is not in this workspace.", "unknown_auto")
    return x


def _due_on(p: dict, s: dict, cfg: dict, day: date) -> list:
    """Names of the demo contacts whose date lands on `day` after the offset."""
    from addons.whatsapp import demo_book
    target = day - timedelta(days=cfg["offset_days"])
    b = demo_book._book(p)
    names = []
    for c in s["contacts"]:
        v = str(b["values"].get(c["id"], {}).get(cfg["attribute"], ""))
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            continue
        if (v[5:] == target.isoformat()[5:]) if cfg["match"] == "yearly" else (v == target.isoformat()):
            if not c.get("opt_out") and (not cfg.get("tags") or set(cfg["tags"]) & set(c.get("tags") or [])):
                names.append(c["name"])
    return sorted(names)


def handle(route: str, d: dict, p: dict, s: dict, a: dict):
    if not route.startswith("autos/"):
        return None
    action = route.split("/", 1)[1]
    st = _autos(a)
    if action == "list":
        return {"autos": [_shown(x) for x in st["items"].values()]}
    if action == "create":
        name = (d.get("name") or "").strip()
        if not 1 <= len(name) <= 80:
            _err("Give it a name (up to 80 characters).", "bad_name")
        cfg = clean(p, d.get("kind"), d.get("config"))
        if len(st["items"]) >= MAX_AUTOS:
            _err("A workspace can have up to %d automatic messages." % MAX_AUTOS, "too_many")
        st["seq"] += 1
        aid = "au%d" % st["seq"]
        st["items"][aid] = {"id": aid, "kind": d["kind"], "name": name, "enabled": False, "config": cfg, "next_run_at": None, "last_run_at": None, "runs": 0, "last_error": None,
                            "created_at": ISO(), "updated_at": ISO(), "log": [], "active": 0, "done": 0, "stopped": 0}
        return {"auto_id": aid}
    if action == "preview":
        config = dict(d.get("config") or {})
        if not (config.get("template") or {}).get("name"):
            config["template"] = {"name": "preview"}
        cfg = clean(p, "date", config)
        today = NOW().astimezone(timezone(timedelta(hours=5, minutes=30))).date()
        days = []
        for i in range(max(1, min(int(d.get("days") or 7), 31))):
            names = _due_on(p, s, cfg, today + timedelta(days=i))
            days.append({"date": (today + timedelta(days=i)).isoformat(), "count": len(names), "names": names[:3]})
        return {"days": days, "total": sum(x["count"] for x in days)}
    x = _item(a, d["auto_id"]) if d.get("auto_id") else None
    if x is None:
        return None
    if action == "get":
        return {"auto": {**_shown(x)}}
    if action == "update":
        if d.get("name") is not None:
            name = d["name"].strip()
            if not 1 <= len(name) <= 80:
                _err("Give it a name (up to 80 characters).", "bad_name")
            x["name"] = name
        if d.get("config") is not None:
            x["config"] = clean(p, x["kind"], d["config"])
        x["updated_at"] = ISO()
        return {"auto": _shown(x)}
    if action == "delete":
        del st["items"][x["id"]]
        return {"deleted": True}
    if action == "set_enabled":
        if d.get("enabled"):
            specs = [x["config"]["template"]] if x["kind"] == "date" else [step["template"] for step in x["config"]["steps"]]
            tmpl = {(t["name"], t["language"]): t for t in p["templates"]}
            for spec in specs:
                t = tmpl.get((spec["name"], spec["language"]))
                if t is None:
                    _err("The template “%s” is not known for this account. Sync your templates first." % spec["name"], "template_unknown")
                if t["status"] != "APPROVED":
                    _err("The template “%s” is %s, so it cannot be sent yet." % (spec["name"], t["status"].lower()), "template_not_approved")
            x["enabled"] = True
            x["next_run_at"] = ISO(NOW() + timedelta(hours=14)) if x["kind"] == "date" else None
            if x["kind"] == "drip" and not x["log"]:
                x["active"], x["done"], x["stopped"] = 3, 1, 1
                x["stopped_why"] = [{"reason": "replied", "count": 1}]
                x["log"] = [{"id": 1, "name": "Asha Patel", "phone": "919800000001", "occasion": "step-0", "state": "sent", "reason": None, "at": ISO(NOW() - timedelta(hours=5))},
                            {"id": 2, "name": "Bala Rao", "phone": "919800000002", "occasion": "step-0", "state": "sent", "reason": None, "at": ISO(NOW() - timedelta(hours=4))}]
        else:
            x["enabled"], x["next_run_at"] = False, None
        return {"auto": _shown(x)}
    if action == "enrol":
        if x["kind"] != "drip":
            _err("Only a drip can have people added to it.", "not_a_drip")
        n = len([c for c in s["contacts"] if not c.get("opt_out")][:5])
        x["active"] += n
        return {"enrolled": n, "already_in": 0, "left_out": len([c for c in s["contacts"] if c.get("opt_out")])}
    if action == "log":
        return {"log": list(reversed(x["log"]))[:int(d.get("limit") or 50)], "stats": {k: v for k, v in _shown(x).items() if k in ("sent", "skipped", "failed", "active", "done", "stopped", "stopped_why")}}
    raise KeyError(route)
