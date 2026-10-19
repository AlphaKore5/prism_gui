"""Sample answers for the AI agent screens: the structured agent, its draft and published copies, what it knows and the state of each source, the questions it could
not answer, its numbers, a profile drafted from a website, and trying one of its actions.

Answers POST /v1/whatsapp/p/ai/* from memory in the shapes prism-wa returns (ai_agent.py, ai_profile.py, ai_knowledge.py, ai_insights.py, ops_ai.py), so the screens built
on them can be built, shown and tested offline. Reached only through demo_platform.handle, which is switched on with PRISM_WHATSAPP_DEMO=1 and never in a frozen build.

The "model" here is a small look-alike: it answers from the first note that shares a word with the question, collects the details a skill asks for when a word in the
customer's message looks like one, and hands over when asked. A website "takes a moment" to be read: the first listing shows it processing, the next shows it ready.

STDLIB ONLY.
"""
from __future__ import annotations

import copy
import re
import time
from datetime import datetime, timedelta, timezone

from addons.whatsapp.license_client import PlatformError

NOW = lambda: datetime.now(timezone.utc)                                              # noqa: E731
ISO = lambda d=None: (d or NOW()).strftime("%Y-%m-%dT%H:%M:%SZ")                      # noqa: E731
TONES = ("friendly", "professional", "casual", "formal", "enthusiastic", "empathetic")
LENGTHS = ("short", "medium", "detailed")
SKILL_KINDS = ("faq", "support", "handoff", "lead", "booking", "enquiry", "feedback", "custom")
CONFIG = ("instructions", "handoff_words", "max_replies", "business_hours_only", "profile", "voice", "skills", "actions", "settings")
MASK = "••••"
HANDOFF = "Let me bring in a colleague who can help with this. They will reply here shortly."


def _err(message: str, reason: str, detail: dict = None):
    raise PlatformError(message, reason, detail or {})


def _next(a: dict, prefix: str) -> str:
    a["seq"] += 1
    return "%s%d" % (prefix, a["seq"])


def _state(a: dict) -> dict:
    return a.setdefault("ai_extra", {"gaps": [], "events": [], "profile_draft": None, "listed": {}})


# ── checks (the same words the server uses) ──────────────────────────────────

def _text(value, name: str, maximum: int, required: bool = False) -> str:
    s = "" if value is None else str(value).strip()
    if required and not s:
        _err("%s is needed." % name.replace("_", " ").capitalize(), "bad_" + name)
    if len(s) > maximum:
        _err("%s is up to %d characters." % (name.replace("_", " ").capitalize(), maximum), "bad_" + name)
    return s


def _https(value, name: str) -> str:
    s = _text(value, name, 500)
    if s and not s.startswith("https://"):
        _err("%s must start with https://" % name.replace("_", " ").capitalize(), "bad_" + name)
    return s


def _slug(item: dict, taken: set, fallback: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", str(item.get("id") or item.get("name") or fallback).lower()).strip("_")[:26] or fallback
    out, n = base, 2
    while out in taken:
        out, n = "%s_%d" % (base, n), n + 1
    taken.add(out)
    return out


def clean(key: str, value):
    v = value if isinstance(value, dict) or isinstance(value, list) else ({} if key in ("profile", "voice", "settings") else [])
    if key == "profile":
        rules = v.get("ground_rules") or []
        if len(rules) > 10:
            _err("Up to 10 ground rules.", "bad_rules")
        return {"business_name": _text(v.get("business_name"), "business_name", 80), "website": _https(v.get("website"), "website"),
                "description": _text(v.get("description"), "description", 1500), "greeting": _text(v.get("greeting"), "greeting", 300),
                "ground_rules": [_text(r, "ground_rule", 200) for r in rules if str(r or "").strip()]}
    if key == "voice":
        tone, length = v.get("tone") or "friendly", v.get("length") or "short"
        if tone not in TONES:
            _err("Tone is one of: %s." % ", ".join(TONES), "bad_tone")
        if length not in LENGTHS:
            _err("Answer length is one of: %s." % ", ".join(LENGTHS), "bad_length")
        return {"tone": tone, "length": length, "language": (_text(v.get("language") or "match", "language", 20) or "match").lower()}
    if key == "skills":
        taken, out = set(), []
        for s in v[:12]:
            if s.get("kind", "custom") not in SKILL_KINDS:
                _err("A skill is one of: %s." % ", ".join(SKILL_KINDS), "bad_skill")
            names = set()
            variables = []
            for x in (s.get("variables") or [])[:8]:
                name = str(x.get("name") or "").strip().lower()
                if not re.match(r"^[a-z][a-z0-9_]{0,29}$", name) or name in names:
                    _err("Each detail needs its own short name (letters, numbers, underscores).", "bad_variable")
                names.add(name)
                variables.append({"name": name, "label": _text(x.get("label"), "label", 60) or name.capitalize(), "description": _text(x.get("description"), "description", 200),
                                  "required": bool(x.get("required", True)), "attribute": _text(x.get("attribute"), "attribute", 40) or name})
            done = s.get("on_complete") if isinstance(s.get("on_complete"), dict) else {}
            out.append({"id": _slug(s, taken, "skill"), "kind": s.get("kind", "custom"), "name": _text(s.get("name"), "name", 60, True), "enabled": bool(s.get("enabled", True)),
                        "when": _text(s.get("when"), "when", 400), "instructions": _text(s.get("instructions"), "instructions", 1000), "variables": variables,
                        "on_complete": {"tag": _text(done.get("tag"), "tag", 40), "handoff": bool(done.get("handoff")), "reason": _text(done.get("reason"), "reason", 120)}})
        return out
    if key == "actions":
        taken, out = set(), []
        for x in v[:10]:
            method = str(x.get("method") or "GET").upper()
            if method not in ("GET", "POST"):
                _err("An action uses GET or POST.", "bad_action")
            url = _https(x.get("url"), "url")
            if not url:
                _err("An action needs the web address it calls (https://...).", "bad_url")
            out.append({"id": _slug(x, taken, "action"), "name": _text(x.get("name"), "name", 60, True), "enabled": bool(x.get("enabled", True)),
                        "description": _text(x.get("description"), "description", 300, True), "method": method, "url": url,
                        "headers": {str(k): _text(val, "header", 300) for k, val in (x.get("headers") or {}).items()}, "body": _text(x.get("body"), "body", 2000),
                        "parameters": [{"name": str(p.get("name") or "").strip().lower(), "description": _text(p.get("description"), "description", 200), "required": bool(p.get("required", True))}
                                       for p in (x.get("parameters") or [])[:6]], "response_path": _text(x.get("response_path"), "response_path", 120)})
        return out
    hook = v.get("handoff_webhook") if isinstance(v.get("handoff_webhook"), dict) else {}
    tests = [re.sub(r"\D", "", str(n)) for n in (v.get("test_numbers") or []) if re.sub(r"\D", "", str(n))]
    if len(tests) > 3 or any(not 8 <= len(n) <= 15 for n in tests):
        _err("Up to 3 test numbers, each a full phone number with its country code.", "bad_test_numbers")
    hook_url = _https(hook.get("url"), "handoff_webhook")
    return {"fallback_text": _text(v.get("fallback_text"), "fallback_text", 400), "handoff_message": _text(v.get("handoff_message"), "handoff_message", 400),
            "handoff_webhook": {"url": hook_url, "headers": {str(k): str(val) for k, val in (hook.get("headers") or {}).items()}} if hook_url else None,
            "test_numbers": tests, "numbers": [str(n) for n in (v.get("numbers") or [])]}


def _mask(v: str) -> str:
    return MASK if len(v) <= 4 else v[:3] + MASK


def _unmask(headers: dict, before: dict) -> dict:
    return {k: (before.get(k, v) if str(v).endswith(MASK) else v) for k, v in (headers or {}).items()}


def _config(ag: dict) -> dict:
    return copy.deepcopy({k: ag[k] for k in CONFIG})


def _shown(ag: dict) -> dict:
    out = {k: v for k, v in ag.items() if k != "live"}
    out["status"] = "published" if ag["live"] is not None else ("paused" if ag["published_version"] else "draft")
    out["unpublished_changes"] = ag["live"] is None or ag["live"] != _config(ag)
    out["actions"] = [{**x, "headers": {k: _mask(v) for k, v in x["headers"].items()}} for x in copy.deepcopy(ag["actions"])]
    hook = copy.deepcopy(ag["settings"]).get("handoff_webhook")
    out["settings"] = {**copy.deepcopy(ag["settings"]), **({"handoff_webhook": {**hook, "headers": {k: _mask(v) for k, v in hook["headers"].items()}}} if hook else {})}
    return out


def new_agent(a: dict, name: str, instructions: str = "", handoff_words=None, max_replies: int = 12, business_hours_only: bool = False) -> dict:
    aid = _next(a, "ag")
    ag = {"id": aid, "name": name, "enabled": False, "is_default": False, "instructions": instructions,
          "handoff_words": handoff_words or ["human", "agent", "person", "complaint", "refund"], "max_replies": max_replies, "business_hours_only": business_hours_only,
          "profile": {}, "voice": {}, "skills": [], "actions": [], "settings": {}, "live": None, "published_at": None, "published_version": 0, "updated_at": ISO()}
    a["ai"][aid] = ag
    return ag


def _publish(ag: dict) -> dict:
    ag["live"] = _config(ag)
    ag["published_version"] += 1
    ag["published_at"] = ISO()
    warnings = []
    if not ag["instructions"].strip() and not ag["profile"].get("description"):
        warnings.append("The agent has not been told what the business does. Add a description or some instructions.")
    return {"version": ag["published_version"], "warnings": warnings}


# ── the router ───────────────────────────────────────────────────────────────

def _agent(a: dict, agent_id: str) -> dict:
    ag = a["ai"].get(agent_id)
    if ag is None:
        _err("That AI agent is not in this workspace.", "unknown_agent")
    return ag


def _source_state(a: dict, ag: dict, doc: dict) -> dict:
    """A website 'takes a moment': the first listing shows its root processing; after that it and its pages are ready."""
    seen = _state(a)["listed"]
    if doc.get("status") == "processing" and seen.get(doc["id"]):
        doc["status"] = "ready"
        if doc.get("pages_pending"):
            for i, (title, text) in enumerate(doc.pop("pages_pending")):
                ag_docs = a["kb"].setdefault(ag["id"], [])
                ag_docs.insert(0, {"id": _next(a, "kn"), "title": title, "kind": "url", "source": doc["source"] + "/page-%d" % (i + 1), "body": text, "characters": len(text),
                                   "created_at": ISO(), "status": "ready", "error": None, "group_id": doc["group_id"], "refreshed_at": ISO(), "chunks": 1, "embedded": 0})
    seen[doc["id"]] = True
    return doc


def handle(route: str, d: dict, p: dict, s: dict, a: dict):
    """The routes this module answers (everything under ai/), or None."""
    if not route.startswith("ai/"):
        return None
    action = route.split("/", 1)[1]
    st = _state(a)
    if action == "status":
        return {"usage": {"replies": a["ai_used"], "tokens_in": a["ai_used"] * 600, "tokens_out": a["ai_used"] * 80, "limit": 1000, "configured": True, "month": NOW().strftime("%Y-%m")},
                "included": True}
    if action == "agents/list":
        return {"agents": [{"id": x["id"], "name": x["name"], "enabled": x["enabled"], "is_default": x["is_default"], "max_replies": x["max_replies"], "business_hours_only": x["business_hours_only"],
                            "updated_at": x["updated_at"], "documents": len(a["kb"].get(x["id"], [])), "published_version": x["published_version"], "is_live": x["live"] is not None,
                            "status": "published" if x["live"] is not None else ("paused" if x["published_version"] else "draft"),
                            "open_gaps": len([g for g in st["gaps"] if g["agent_id"] == x["id"] and g["status"] == "open"])} for x in a["ai"].values()]}
    if action == "agents/create":
        name = (d.get("name") or "").strip()
        if not 1 <= len(name) <= 60:
            _err("Give the agent a name (up to 60 characters).", "bad_name")
        return {"agent_id": new_agent(a, name, d.get("instructions") or "", d.get("handoff_words"), int(d.get("max_replies") or 12), bool(d.get("business_hours_only")))["id"]}
    if action == "agents/draft_profile":
        url = str(d.get("url") or "").strip()
        if not url.startswith("https://"):
            _err("Give a web address starting with https://", "bad_url")
        host = re.sub(r"^https://(www\.)?", "", url).split("/")[0]
        name = host.split(".")[0].replace("-", " ").title()
        return {"profile": {"business_name": name, "website": url, "description": "%s builds and renovates homes and boundary walls across Gujarat, and quotes after a free site visit." % name,
                            "greeting": "Namaste! Welcome to %s. How can we help you today?" % name, "ground_rules": ["Never promise a date or a discount.", "Do not discuss other builders."]}}
    if action == "gaps/answer" or action == "gaps/ignore":
        g = next((x for x in st["gaps"] if x["id"] == d.get("gap_id")), None)
        if g is None:
            _err("That question is not in this workspace.", "unknown_gap")
        if action == "gaps/ignore":
            g["status"] = "ignored"
            return {}
        if not (d.get("answer") or "").strip():
            _err("A question and its answer are both needed.", "empty")
        body = "Q: %s\nA: %s" % (g["question"], d["answer"])
        doc = {"id": _next(a, "kn"), "title": g["question"][:120], "kind": "faq", "source": None, "body": body, "characters": len(body), "created_at": ISO(), "status": "ready",
               "error": None, "group_id": None, "refreshed_at": None, "chunks": 1, "embedded": 0}
        a["kb"].setdefault(g["agent_id"], []).insert(0, doc)
        g["status"] = "answered"
        return {"knowledge_id": doc["id"]}
    if action == "knowledge/refresh":
        for docs in a["kb"].values():
            for x in docs:
                if x["id"] == d.get("knowledge_id"):
                    if x["kind"] != "url":
                        _err("Only a web page can be read again. Delete this note and add it afresh.", "not_a_page")
                    x["status"] = "processing"
                    st["listed"].pop(x["id"], None)
                    return {}
        _err("That source is not in this workspace.", "unknown_source")
    if action == "knowledge/delete":
        for docs in a["kb"].values():
            for x in list(docs):
                if x["id"] == d["knowledge_id"]:
                    docs.remove(x)
                    return {"deleted": True}
        return {"deleted": False}
    if action == "actions/test":
        act = d.get("action") or {}
        url = str(act.get("url") or "")
        if not url.startswith("https://") or "localhost" in url:
            return {"ok": False, "ran": False, "status": 0, "text": "", "error": "that address cannot be called from a flow"}
        missing = [p["name"] for p in act.get("parameters") or [] if p.get("required", True) and not str((d.get("args") or {}).get(p["name"], "")).strip()]
        if missing:
            return {"ok": False, "ran": False, "status": 0, "text": "", "error": "missing: " + ", ".join(missing)}
        return {"ok": True, "ran": True, "status": 200, "text": "Packed, ships tomorrow.", "error": ""}
    ag = _agent(a, d["agent_id"]) if d.get("agent_id") else None
    if action.startswith("knowledge/") and ag is not None:
        docs = a["kb"].setdefault(ag["id"], [])
        if action == "knowledge/list":
            return {"knowledge": [{k: v for k, v in _source_state(a, ag, x).items() if k not in ("body", "pages_pending")} for x in docs]}
        if action == "knowledge/add_site":
            url = str(d.get("url") or "")
            if not url.startswith("https://"):
                _err("Give a web address starting with https://", "bad_url")
            group = _next(a, "grp")
            doc = {"title": d.get("title") or url[:100], "kind": "url", "source": url, "body": url, "status": "processing", "error": None, "group_id": group, "refreshed_at": None,
                   "chunks": 1, "embedded": 0, "pages_pending": [("About us", "We are a family business with twenty years of experience in construction."),
                                                                ("Services", "Boundary walls, house construction and renovation work."), ("Contact", "Our office is in Alkapuri, Vadodara.")][:max(0, int(d.get("max_pages") or 15) - 1)]}
        elif action == "knowledge/add_faq":
            if not (d.get("question") and d.get("answer")):
                _err("A question and its answer are both needed.", "empty")
            doc = {"title": d["question"][:120], "kind": "faq", "source": None, "body": "Q: %s\nA: %s" % (d["question"], d["answer"])}
        elif action == "knowledge/add_url":
            if not str(d.get("url") or "").startswith("https://"):
                _err("Give a web address starting with https://", "bad_url")
            doc = {"title": d.get("title") or d["url"][:100], "kind": "url", "source": d["url"], "body": "Page content of %s" % d["url"]}
        else:
            if not (d.get("body") or "").strip():
                _err("There is nothing to learn from that.", "empty")
            doc = {"title": (d.get("title") or "").strip() or "Untitled", "kind": d.get("kind") or "text", "source": d.get("source"), "body": d["body"]}
        doc.setdefault("status", "ready")
        doc.setdefault("error", None)
        doc.setdefault("group_id", None)
        doc.setdefault("refreshed_at", None)
        doc.setdefault("chunks", 1)
        doc.setdefault("embedded", 0)
        doc.update(id=_next(a, "kn"), characters=len(doc["body"]), created_at=ISO())
        docs.insert(0, doc)
        return {"knowledge_id": doc["id"], **({"group_id": doc["group_id"]} if action == "knowledge/add_site" else {})}
    if ag is None:
        return None
    if action == "agents/get":
        docs = a["kb"].get(ag["id"], [])
        return {"agent": {**_shown(ag), "documents": len(docs), "characters": sum(x["characters"] for x in docs)}}
    if action == "agents/update":
        ch = d.get("changes") or {}
        for k, v in ch.items():
            if k in ("name", "instructions", "handoff_words", "max_replies", "business_hours_only"):
                ag[k] = v
            elif k == "actions":
                before = {x["id"]: x["headers"] for x in ag["actions"]}
                v = [{**x, "headers": _unmask(x.get("headers"), before.get(x.get("id"), {}))} for x in (v or [])]
                ag[k] = clean(k, v)
            elif k == "settings":
                hook = (v or {}).get("handoff_webhook")
                if isinstance(hook, dict):
                    hook["headers"] = _unmask(hook.get("headers"), ((ag["settings"].get("handoff_webhook") or {}).get("headers") or {}))
                ag[k] = clean(k, v)
            elif k in ("profile", "voice", "skills"):
                ag[k] = clean(k, v)
            else:
                _err("cannot change: %s" % k, "bad_field")
        ag["updated_at"] = ISO()
        return {"agent": _shown(ag)}
    if action == "agents/publish":
        return _publish(ag)
    if action == "agents/unpublish":
        ag["live"] = None
        return {}
    if action == "agents/delete":
        del a["ai"][ag["id"]]
        return {"deleted": True}
    if action == "agents/set_enabled":
        ag["enabled"] = bool(d.get("enabled"))
        if ag["enabled"] and not ag["published_version"]:
            _publish(ag)
        if not ag["enabled"]:
            ag["is_default"] = False
        return {}
    if action == "agents/set_default":
        if d.get("default", True):
            if not ag["enabled"]:
                _err("Switch the agent on first.", "not_enabled")
            for x in a["ai"].values():
                x["is_default"] = False
        ag["is_default"] = bool(d.get("default", True))
        return {}
    if action == "gaps/list":
        status = d.get("status") or "open"
        return {"gaps": [{k: v for k, v in g.items() if k != "agent_id"} for g in sorted(st["gaps"], key=lambda g: -g["times"]) if g["agent_id"] == ag["id"] and g["status"] == status]}
    if action == "analytics":
        return _analytics(a, ag)
    if action == "test":
        return _test(a, ag, list(d.get("messages") or []))
    raise KeyError(route)


def _analytics(a: dict, ag: dict) -> dict:
    st = _state(a)
    live = ag["published_version"] > 0
    chats, handed = (46, 11) if live else (0, 0)
    end = NOW().date()
    days = [{"day": str(end - timedelta(days=29 - i)), "replies": 2 + (i * 7 + len(ag["name"])) % 9} for i in range(30)] if live else []
    return {"range": {"since": ISO(NOW() - timedelta(days=30)), "until": ISO()},
            "totals": {"replies": sum(x["replies"] for x in days), "chats": chats, "handed_over": handed, "settled": chats - handed,
                       "settled_rate": round(100.0 * (chats - handed) / chats, 1) if chats else 0.0, "handover_rate": round(100.0 * handed / chats, 1) if chats else 0.0,
                       "actions": 9 if live and ag["actions"] else 0, "skills_finished": 14 if live and ag["skills"] else 0, "tests": 5, "tokens_in": 52000 if live else 0, "tokens_out": 6100 if live else 0},
            "reasons": ([{"reason": "not in the knowledge", "count": 6}, {"reason": "the customer asked for a person", "count": 4}, {"reason": "the agent had no answer", "count": 1}] if live else []),
            "days": days, "gaps": [{k: v for k, v in g.items() if k != "agent_id"} for g in sorted(st["gaps"], key=lambda g: -g["times"]) if g["agent_id"] == ag["id"] and g["status"] == "open"][:10]}


def _test(a: dict, ag: dict, msgs: list) -> dict:
    if not msgs:
        _err("Write a message to try.", "empty")
    last = str(msgs[-1].get("text") or "")
    hand = (ag["settings"].get("handoff_message") or HANDOFF)
    if any(w in last.lower() for w in ag["handoff_words"]):
        return {"answer": {"reply": hand, "handoff": True, "reason": "the customer asked for a person", "sources": [], "tokens": {}, "collected": {}, "ran_action": None, "unknown": False}}
    words = {w for w in re.findall(r"\w+", last.lower()) if len(w) > 2}
    out = {"collected": {}, "ran_action": None, "unknown": False, "tokens": {"tokens_in": 420, "tokens_out": 40}}
    skills = [x for x in ag["skills"] if x.get("enabled", True) and x.get("variables")]
    for sk in skills:
        for v in sk["variables"]:
            m = re.search(r"\b(?:in|from|at)\s+([A-Z][a-z]+)", last) if v["name"] in ("city", "location", "area") else None
            if m:
                out["collected"][v["name"]] = m.group(1)
    for act in ag["actions"]:
        if act.get("enabled", True) and words & set(re.findall(r"\w+", (act["name"] + " " + act["description"]).lower())):
            safe = act["method"] == "GET"
            out["ran_action"] = {"id": act["id"], "name": act["name"], "ok": safe, "ran": safe, "note": "" if safe else "(not run in a test: it would change something)"}
            out["reply"], out["handoff"], out["reason"], out["sources"] = ("Your order is packed and ships tomorrow." if safe else "I would book that for you.", False, "", [])
            time.sleep(0.05)
            return {"answer": out}
    hit = next((x for x in a["kb"].get(ag["id"], []) if x.get("status", "ready") == "ready" and words & set(re.findall(r"\w+", x["body"].lower()))), None)
    time.sleep(0.05)
    if hit is None:
        out.update(reply="I'm not sure about that — let me ask a colleague to help.", handoff=True, reason="not in the knowledge", sources=[], unknown=True)
        return {"answer": out}
    reply = hit["body"].split("A:", 1)[-1].strip()[:300]
    if out["collected"]:
        reply += " " + (ag["skills"][0]["variables"][-1]["label"] + "?" if ag["skills"] else "")
    out.update(reply=reply.strip(), handoff=False, reason="", sources=[hit["title"]])
    return {"answer": out}


def seed_gaps(a: dict, agent_id: str, questions: list) -> None:
    """Questions the agent could not answer, for the screens and tests to show."""
    st = _state(a)
    for q, times in questions:
        st["gaps"].append({"id": _next(a, "gp"), "agent_id": agent_id, "question": q, "reason": "not in the knowledge", "times": times, "status": "open",
                           "first_at": ISO(NOW() - timedelta(days=9)), "last_at": ISO(NOW() - timedelta(days=1))})
