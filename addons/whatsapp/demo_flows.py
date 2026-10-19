"""Sample answers for the chatbot builder: the checks, the "try it" walk, the ready-made library, results, "write a flow with AI", and
the Conversions API.

Answers POST /v1/whatsapp/p/<route> from memory in the shapes prism-wa returns (flows.py, flow_engine.py, flow_ai.py, capi.py, ops_flows.py), so
the Automations screens can be built, shown and tested offline. Reached only through demo_platform.handle, which is switched on with
PRISM_WHATSAPP_DEMO=1 and never in a frozen build.

The checker and the walker are deliberately smaller look-alikes of the server's: enough to show how the screens behave with questions, buttons,
files, map pins, a clock and holidays. The real rules live in prism-wa.

STDLIB ONLY.
"""
from __future__ import annotations

import re
import zlib
from datetime import datetime, timedelta, timezone

from addons.whatsapp.license_client import PlatformError

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
TARGET_KEYS = ("next", "else", "timeout_next", "fallback_next", "invalid_next", "ok_next", "error_next")
WAITING = ("buttons", "list", "ask", "delay", "location_request")
EVENTS = ("Lead", "Purchase", "ViewContent", "CompleteRegistration", "Contact", "Schedule", "SubmitApplication", "AddToCart", "InitiateCheckout",
          "Subscribe", "StartTrial")
PLACEHOLDER_ASSET = "00000000-0000-0000-0000-000000000000"
IST = timezone(timedelta(hours=5, minutes=30))


def _iso(d=None) -> str:
    return (d or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _err(message: str, reason: str, detail: dict = None):
    raise PlatformError(message, reason, detail or {})


# ── the ready-made flows ─────────────────────────────────────────────────────

def _item(key, title, description, topic, trigger, nodes, entry, **flags):
    return {"key": key, "title": title, "description": description, "topic": topic, "trigger": trigger,
            "graph": {"entry": entry, "order": list(nodes), "nodes": nodes}, **flags}


LIBRARY = [
    _item("lead_capture", "Capture a new enquiry", "Greets a new customer, asks what they need, takes their name and city, and passes them to your team.", "General",
          {"type": "first_message"}, {
              "greet": {"type": "buttons", "text": "Hello {{first_name}}! What do you need today?",
                        "options": [{"id": "quote", "title": "Get a quote", "next": "ask_name"}, {"id": "visit", "title": "Book a site visit", "next": "ask_name"}]},
              "ask_name": {"type": "ask", "text": "What is your name?", "save_as": "attr:FullName", "next": "ask_city"},
              "ask_city": {"type": "ask", "text": "Which city is the project in?", "save_as": "attr:City", "next": "done"},
              "done": {"type": "handoff", "text": "Thank you {{attr.FullName}}. Our team will message you shortly.", "reason": "new enquiry"}}, "greet"),
    _item("faq_menu", "Answer common questions", "A menu of the questions customers ask most.", "General",
          {"type": "keyword", "match": "exact", "keywords": ["menu", "help"]}, {
              "menu": {"type": "list", "text": "What would you like to know?", "button_label": "Choose a topic",
                       "sections": [{"title": "About us", "rows": [{"id": "hours", "title": "Opening hours", "next": "hours"}, {"id": "where", "title": "Where are you?", "next": "where"}]},
                                    {"title": "Talk to us", "rows": [{"id": "person", "title": "Speak to a person", "next": "person"}]}]},
              "hours": {"type": "send_text", "text": "We are open Monday to Saturday, 10 am to 6 pm.", "next": "menu"},
              "where": {"type": "send_location", "latitude": 22.3072, "longitude": 73.1812, "name": "Our office", "address": "12 Alkapuri Road, Vadodara", "next": "menu"},
              "person": {"type": "handoff", "text": "Connecting you to our team now.", "reason": "asked for a person"}}, "menu", needs_edit=True),
    _item("feedback", "Ask for feedback", "Asks how it went; a poor rating goes to a person straight away.", "General",
          {"type": "keyword", "match": "exact", "keywords": ["feedback"]}, {
              "rate": {"type": "buttons", "text": "How was your experience with us?", "options": [
                  {"id": "great", "title": "Great", "next": "thanks"}, {"id": "bad", "title": "Not good", "next": "person"}]},
              "thanks": {"type": "send_text", "text": "Thank you for telling us!"},
              "person": {"type": "handoff", "text": "We are sorry. A manager will contact you today.", "reason": "unhappy customer"}}, "rate"),
    _item("business_hours_router", "Answer by the clock", "Open: carries on. Closed, on a holiday or on a Sunday: says when you will reply.", "General",
          {"type": "first_message"}, {
              "holiday": {"type": "condition", "rules": [{"field": "holiday", "op": "yes", "value": "", "next": "closed"}, {"field": "weekday", "op": "in", "value": "sun", "next": "closed"},
                                                         {"field": "hours", "op": "closed", "value": "", "next": "closed"}], "else": "open"},
              "closed": {"type": "send_text", "text": "Thanks {{first_name}}. We are closed right now and will reply when we open."},
              "open": {"type": "handoff", "text": "Connecting you to our team.", "reason": "new chat"}}, "holiday"),
    _item("request_customer_location", "Ask where they are", "Asks for a map pin and tells your team the nearest branch to call from.", "General",
          {"type": "keyword", "match": "contains", "keywords": ["nearest", "branch"]}, {
              "ask": {"type": "location_request", "text": "Please share your location and we will find the nearest branch.", "timeout_minutes": 30, "timeout_next": "sorry", "next": "thanks"},
              "thanks": {"type": "handoff", "text": "Thanks! Our team will reply with the nearest branch.", "reason": "location shared"},
              "sorry": {"type": "send_text", "text": "No problem. Write your area and we will help."}}, "ask"),
    _item("catalogue_on_request", "Send the catalogue", "Sends your catalogue PDF when someone asks for it.", "Retail",
          {"type": "keyword", "match": "contains", "keywords": ["catalogue", "catalog", "brochure"]}, {
              "hello": {"type": "send_text", "text": "Here is our latest catalogue, {{first_name}}.", "next": "file"},
              "file": {"type": "media", "kind": "document", "asset_id": PLACEHOLDER_ASSET, "caption": "Catalogue", "next": "ask"},
              "ask": {"type": "buttons", "text": "Would you like a callback?", "options": [{"id": "yes", "title": "Yes please", "next": "person"}, {"id": "no", "title": "No thanks", "next": "bye"}]},
              "person": {"type": "handoff", "text": "We will call you soon.", "reason": "catalogue callback"},
              "bye": {"type": "send_text", "text": "Thank you!"}}, "hello", needs_files=True),
    _item("ad_lead_to_meta", "Qualify an ad lead and tell Meta", "Asks two questions of someone from your ad and reports the lead to Meta, so the ad finds more like them.", "Marketing",
          {"type": "first_message"}, {
              "need": {"type": "ask", "text": "What are you looking for?", "save_as": "attr:Need", "next": "city"},
              "city": {"type": "ask", "text": "Which city?", "save_as": "attr:City", "next": "tell"},
              "tell": {"type": "capi_event", "event": "Lead", "next": "done"},
              "done": {"type": "handoff", "text": "Thanks {{first_name}}! We will contact you shortly.", "reason": "ad lead"}}, "need"),
    _item("lead_to_your_crm", "Send every lead to your system", "Saves the answers and posts them to your own server.", "Marketing",
          {"type": "keyword", "match": "contains", "keywords": ["enquiry"]}, {
              "name": {"type": "ask", "text": "Your name?", "save_as": "var:fullname", "next": "need"},
              "need": {"type": "ask", "text": "What do you need?", "save_as": "var:need", "next": "post"},
              "post": {"type": "webhook", "method": "POST", "url": "https://example.com/leads", "body": "{\"name\": \"{{var.fullname}}\", \"need\": \"{{var.need}}\", \"phone\": \"{{mobile}}\"}", "next": "thanks"},
              "thanks": {"type": "send_text", "text": "Thank you {{var.fullname}}, we have your details."}}, "name", needs_edit=True),
]


def get_library() -> dict:
    topics = sorted({i["topic"] for i in LIBRARY})
    return {"library": [dict(i) for i in LIBRARY], "topics": topics}


# ── the checks ───────────────────────────────────────────────────────────────

def _targets(node: dict) -> list:
    out = [node[k] for k in TARGET_KEYS if isinstance(node.get(k), str) and node[k]]
    for key in ("options", "rows", "rules"):
        out += [i["next"] for i in node.get(key) or [] if isinstance(i, dict) and i.get("next")]
    for sec in node.get("sections") or []:
        out += [r["next"] for r in (sec.get("rows") or []) if isinstance(r, dict) and r.get("next")]
    return out


def list_rows(node: dict) -> list:
    if node.get("sections"):
        return [r for s in node["sections"] for r in (s.get("rows") or [])]
    return list(node.get("rows") or [])


def check_flow(graph: dict, trigger: dict) -> list:
    issues = []

    def add(sev, code, msg, node=""):
        issues.append({"severity": sev, "code": code, "message": msg, "node": node})
    if not (trigger or {}).get("type"):
        add("error", "bad_trigger", "Choose what starts this flow.", "trigger")
    nodes = (graph or {}).get("nodes") or {}
    if not nodes:
        add("error", "empty", "The flow has no steps yet.")
        return issues
    if graph.get("entry") not in nodes:
        add("error", "no_entry", "Choose which step the flow starts with.")
    for nid, n in nodes.items():
        kind = n.get("type")
        if kind in ("send_text", "buttons", "list", "ask", "location_request") and not str(n.get("text") or "").strip():
            add("error", "bad_text", "Step \"%s\" needs its text (1 to 1024 characters)." % nid, nid)
        if kind == "buttons" and not (1 <= len(n.get("options") or []) <= 3):
            add("error", "bad_options", "Step \"%s\" needs 1 to 3 buttons." % nid, nid)
        if kind == "list" and not (1 <= len(list_rows(n)) <= 10):
            add("error", "bad_options", "A list in \"%s\" needs 1 to 10 rows in all." % nid, nid)
        if kind == "media" and not re.match(r"^[0-9a-f-]{36}$", str(n.get("asset_id") or "")):
            add("error", "bad_media", "Step \"%s\" needs a file from your Media Library." % nid, nid)
        if kind == "media" and n.get("asset_id") == PLACEHOLDER_ASSET:
            add("error", "unknown_asset", "Step \"%s\": choose one of your own files — that one is only an example." % nid, nid)
        if kind == "send_location" and not all(isinstance(n.get(k), (int, float)) for k in ("latitude", "longitude")):
            add("error", "bad_location", "Step \"%s\" needs a latitude (-90 to 90) and a longitude (-180 to 180)." % nid, nid)
        if kind in ("webhook", "api_request") and not str(n.get("url") or "").startswith("https://"):
            add("error", "bad_request", "Step \"%s\": the address must start with https:// (up to 500 characters)." % nid, nid)
        if kind == "send_form" and not re.match(r"^[0-9a-f-]{36}$", str(n.get("form_id") or "")) and not str(n.get("form_id") or "").startswith("f"):
            add("error", "bad_form", "Step \"%s\" needs the form to send." % nid, nid)
        if kind == "send_products":
            if n.get("mode") not in ("product", "products", "catalog"):
                add("error", "bad_products", "Step \"%s\": choose one product, a list of products, or the whole catalogue." % nid, nid)
            elif n["mode"] == "product" and not str(n.get("retailer_id") or "").strip():
                add("error", "bad_products", "Step \"%s\" needs the product to send." % nid, nid)
            elif n["mode"] == "products" and not (1 <= len(n.get("retailer_ids") or []) <= 30):
                add("error", "bad_products", "Step \"%s\" needs 1 to 30 products." % nid, nid)
        if kind == "capi_event" and n.get("event") not in EVENTS:
            add("error", "bad_event", "Step \"%s\": choose one of %s." % (nid, ", ".join(EVENTS)), nid)
        if kind == "condition":
            for rule in n.get("rules") or []:
                problem = _rule_problem(rule)
                if problem:
                    add("error", "bad_rules", "A condition in \"%s\": %s." % (nid, problem), nid)
            if not n.get("else"):
                add("warning", "no_else", "Step \"%s\" has nowhere to go when no condition fits; the flow will end there." % nid, nid)
        for t in _targets(n):
            if t not in nodes:
                add("error", "dangling", "Step \"%s\" leads to \"%s\", which does not exist." % (nid, t), nid)
    seen, stack = set(), [graph.get("entry")]
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in nodes:
            continue
        seen.add(cur)
        stack.extend(_targets(nodes[cur]))
    for nid in nodes:
        if nid not in seen and graph.get("entry") in nodes:
            add("warning", "unreachable", "Step \"%s\" can never be reached." % nid, nid)
    return issues


def _rule_problem(rule: dict):
    field, op, value = rule.get("field"), rule.get("op"), str(rule.get("value") or "").strip()
    if field == "weekday" and (op not in ("in", "ne", "eq") or not value or any(d.strip() not in WEEKDAYS for d in value.split(","))):
        return "choose days from %s" % ", ".join(WEEKDAYS)
    if field == "date":
        parts = value.split("..") if op == "between" else [value]
        if op not in ("eq", "gt", "lt", "between") or (op == "between" and len(parts) != 2) or any(not (p == "today" or re.match(r"^\d{4}-\d{2}-\d{2}$", p)) for p in parts):
            return "write dates like 2026-11-01, or today (and two dates with .. between them)"
    if field == "time":
        parts = value.split("..") if op == "between" else [value]
        if op not in ("gt", "lt", "between") or (op == "between" and len(parts) != 2) or any(not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", p) for p in parts):
            return "write times like 09:30 (and two times with .. between them)"
    if field == "holiday" and op not in ("yes", "no"):
        return "a holiday condition is yes or no"
    return None


# ── the walk ─────────────────────────────────────────────────────────────────

def _interp(text: str, name: str, attrs: dict, kept: dict) -> str:
    first = (name.split() or [""])[0] or "there"

    def sub(m):
        token = m.group(1)
        if token in ("name", "first_name", "mobile"):
            return {"name": name, "first_name": first, "mobile": "919800000000"}[token]
        if token.startswith("attr."):
            return str(attrs.get(token[5:], ""))
        if token.startswith("var."):
            return str(kept.get(token[4:], ""))
        return ""
    return re.sub(r"\{\{\s*([A-Za-z_.]+)\s*\}\}", sub, text or "")


def _holds(rule: dict, text: str, attrs: dict, kept: dict, tags: set, local: datetime, holidays: set, open_now: bool) -> bool:
    field, op, want = rule.get("field", ""), rule.get("op", ""), str(rule.get("value") or "")
    day = local.date().isoformat()
    if field == "holiday":
        return (day in holidays) == (op == "yes")
    if field == "hours":
        return open_now == (op == "open")
    if field == "weekday":
        names = [w.strip().lower() for w in want.split(",") if w.strip()]
        today = WEEKDAYS[local.weekday()]
        return (today not in names) if op == "ne" else (today in names)
    if field == "date":
        parts = [day if p.strip() == "today" else p.strip() for p in want.split("..")]
        if op == "between":
            return len(parts) == 2 and parts[0] <= day <= parts[1]
        return {"eq": day == parts[0], "gt": day > parts[0], "lt": day < parts[0]}.get(op, False)
    if field == "time":
        now_t, parts = local.strftime("%H:%M"), [p.strip() for p in want.split("..")]
        if op == "between":
            return len(parts) == 2 and parts[0] <= now_t < parts[1]
        return now_t > parts[0] if op == "gt" else now_t < parts[0]
    if field == "tag":
        has = want.strip().lower() in {t.lower() for t in tags}
        return {"exists": bool(tags), "not_exists": not tags, "ne": not has}.get(op, has)
    have = text if field == "message" else (attrs.get(field[5:]) if field.startswith("attr:") else kept.get(field[4:]))
    have_s = "" if have is None else str(have)
    if op == "exists":
        return bool(have_s)
    if op == "not_exists":
        return not have_s
    return {"eq": have_s.lower() == want.lower(), "ne": have_s.lower() != want.lower(), "contains": want.lower() in have_s.lower(),
            "starts_with": have_s.lower().startswith(want.lower())}.get(op, False)


def walk_flow(graph: dict, inputs: list, name: str = "Test customer", attrs: dict = None, open_now: bool = True, local=None, holidays=()) -> dict:
    nodes, transcript = graph["nodes"], []
    attrs, kept, tags = dict(attrs or {}), {}, set()
    local = local or datetime.now(IST)
    holidays = set(holidays or ())
    state = {"waiting": None, "steps": 0}

    def bot(item):
        transcript.append({"from": "bot", **item})

    def note(text, who="system"):
        transcript.append({"from": who, "kind": "note", "text": text})

    def finish(st, handoff=None):
        return {"transcript": transcript, "state": st, "waiting": None, "node": None, "error": None, "handoff": handoff, "agent": None, "issues": []}

    def run(nid, text=""):
        while nid and state["steps"] < 60:
            state["steps"] += 1
            n = nodes[nid]
            kind = n["type"]
            say = lambda t: _interp(t, name, attrs, kept)                                                              # noqa: E731
            if kind == "send_text":
                bot({"kind": "text", "text": say(n["text"])})
            elif kind == "buttons":
                bot({"kind": "buttons", "text": say(n["text"]), "options": [{"id": o["id"], "title": o["title"]} for o in n["options"]]})
                state["waiting"] = (nid, "choice")
                return None
            elif kind == "list":
                item = {"kind": "list", "text": say(n["text"]), "button": n.get("button_label"),
                        "rows": [{"id": r["id"], "title": r["title"], "description": r.get("description", "")} for r in list_rows(n)]}
                if n.get("sections"):
                    item["sections"] = [{"title": s["title"], "rows": [r["id"] for r in s["rows"]]} for s in n["sections"]]
                bot(item)
                state["waiting"] = (nid, "choice")
                return None
            elif kind == "ask":
                bot({"kind": "text", "text": say(n["text"])})
                state["waiting"] = (nid, "ask")
                return None
            elif kind == "location_request":
                bot({"kind": "location_request", "text": say(n["text"])})
                state["waiting"] = (nid, "location")
                return None
            elif kind == "media":
                bot({"kind": "media", "media": n.get("kind", "image"), "text": say(n.get("caption") or ""), "asset_id": str(n.get("asset_id"))})
            elif kind == "send_location":
                bot({"kind": "location", "latitude": n.get("latitude"), "longitude": n.get("longitude"), "name": say(n.get("name") or ""), "address": say(n.get("address") or "")})
            elif kind == "template":
                bot({"kind": "template", "name": n.get("name"), "language": n.get("language")})
            elif kind == "condition":
                nid = next((r.get("next") for r in n.get("rules") or [] if _holds(r, text, attrs, kept, tags, local, holidays, open_now)), n.get("else"))
                continue
            elif kind == "handoff":
                if n.get("text"):
                    bot({"kind": "text", "text": say(n["text"])})
                note("handed to a person")
                return finish("done", handoff=n.get("reason") or "asked for a person")
            elif kind == "delay":
                note("time passes", "clock")
            elif kind == "set_attribute":
                attrs[n["key"]] = say(n.get("value", ""))
                note("saved %s = %s" % (n["key"], attrs[n["key"]]))
            elif kind == "add_tag":
                tags.add(n["tag"])
                note("added the tag %s" % n["tag"])
            elif kind == "remove_tag":
                tags.discard(n["tag"])
                note("removed the tag %s" % n["tag"])
            elif kind == "api_request":
                note("would call %s (not called in a test)" % n.get("url"))
                nid = n.get("ok_next") or n.get("next")
                continue
            elif kind == "webhook":
                note("would send the details to %s (not sent in a test)" % n.get("url"))
            elif kind == "capi_event":
                note("would tell Meta about a %s (not sent in a test)" % n.get("event"))
            elif kind == "send_form":
                bot({"kind": "form", "form_id": str(n.get("form_id")), "text": say(n.get("text") or ""), "button": n.get("button") or ""})
            elif kind == "send_products":
                bot({"kind": "products", "mode": n.get("mode"), "text": say(n.get("text") or ""), "retailer_id": n.get("retailer_id"), "retailer_ids": list(n.get("retailer_ids") or [])})
            elif kind == "request_payment":
                bot({"kind": "payment_request", "text": say(n.get("empty_text") or "")})
            elif kind == "agent":
                note("handed to the AI agent")
                return finish("done")
            elif kind in ("end", "jump_flow"):
                return finish("done")
            nid = n.get("next")
        return finish("done") if not state["waiting"] else None

    result = None
    for i, raw in enumerate(inputs):
        item = {"text": raw} if isinstance(raw, str) else dict(raw or {})
        text = item.get("text", "")
        transcript.append({"from": "customer", "kind": "text", "text": text or item.get("payload_id", "")})
        if i == 0:
            result = run(graph["entry"], text)
        elif state["waiting"]:
            nid, kind = state["waiting"]
            n = nodes[nid]
            if kind == "choice":
                pick = next((o for o in (n.get("options") or list_rows(n)) if o["title"].lower() == text.strip().lower() or o["id"] == item.get("payload_id", text.strip())), None)
                if pick:
                    state["waiting"] = None
                    result = run(pick.get("next"), text)
                else:
                    bot({"kind": "text", "text": "Please choose one of the options."})
            elif kind == "location":
                where = item.get("location") or {}
                if where.get("latitude") is not None:
                    kept.update(location_lat=str(where["latitude"]), location_lng=str(where["longitude"]))
                    state["waiting"] = None
                    result = run(n.get("next"), text)
                else:
                    bot({"kind": "location_request", "text": n["text"]})
            else:
                save = n.get("save_as", "")
                if save.startswith("attr:"):
                    attrs[save[5:]] = text
                elif save.startswith("var:"):
                    kept[save[4:]] = text
                state["waiting"] = None
                result = run(n.get("next"), text)
        if result:
            return result
    w = state["waiting"]
    return {"transcript": transcript, "state": "waiting" if w else "done", "waiting": ({"choice": "buttons", "ask": "ask", "location": "location_request"}[w[1]] if w else None),
            "node": w[0] if w else None, "error": None, "handoff": None, "agent": None, "issues": []}


def test_route(d: dict) -> dict:
    issues = check_flow(d.get("graph") or {}, d.get("trigger") or {})
    if [i for i in issues if i["severity"] == "error"]:
        return {"transcript": [], "state": "invalid", "issues": issues}
    local = None
    if d.get("local"):
        try:
            local = datetime.fromisoformat(str(d["local"]).replace("Z", "+00:00"))
        except ValueError:
            _err("that date and time do not look right", "bad_request")
        local = local if local.tzinfo else local.replace(tzinfo=IST)
    holidays = [str(h.get("date") if isinstance(h, dict) else h) for h in d.get("holidays") or []]
    out = walk_flow(d["graph"], list(d.get("inputs") or []), d.get("name") or "Test customer", d.get("attrs") or {}, bool(d.get("open_now", True)), local, holidays)
    out["issues"] = issues
    return out


# ── results ──────────────────────────────────────────────────────────────────

def _order(graph: dict) -> list:
    nodes = graph.get("nodes") or {}
    seen, queue = [], [graph.get("entry")]
    while queue:
        cur = queue.pop(0)
        if cur in seen or cur not in nodes:
            continue
        seen.append(cur)
        queue.extend(_targets(nodes[cur]))
    return seen + [n for n in nodes if n not in seen]


def analytics(flow: dict, since=None, until=None) -> dict:
    """Believable numbers that fall step by step, the same for the same flow so a screen does not shimmer."""
    seed = zlib.crc32(flow["id"].encode())
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=29)
    days = [{"day": str(start + timedelta(days=i)), "runs": 3 + ((seed >> (i % 16)) + i * 7) % 9} for i in range(30)]
    started = sum(d["runs"] for d in days) if flow.get("version") else 0
    graph, nodes = flow["graph"], []
    reach = started
    for i, nid in enumerate(_order(graph)):
        node = graph["nodes"][nid]
        seen = max(0, reach if node.get("type") != "end" else int(reach * 0.9)) if started else 0
        gone = int(seen * (0.12 + ((seed >> i) % 7) / 50.0)) if node.get("type") in WAITING and started else 0
        text = " ".join(str(node.get("text") or node.get("name") or node.get("tag") or node.get("url") or "").split())
        nodes.append({"node": nid, "kind": node.get("type"), "text": text if len(text) <= 70 else text[:69].rstrip() + "…", "reached": seen, "stopped": gone,
                      "stopped_pct": round(100.0 * gone / seen, 1) if seen else 0.0})
        reach = max(0, seen - gone)
    done = int(started * 0.68)
    return {"flow": {"id": flow["id"], "name": flow["name"], "version": flow.get("version", 0)}, "range": {"since": str(start), "until": str(end)},
            "totals": {"started": started, "done": done, "failed": int(started * 0.02), "cancelled": int(started * 0.04), "in_progress": int(started * 0.06),
                       "handed_to_person": int(started * 0.21), "completion_rate": round(100.0 * done / started, 1) if started else 0.0, "avg_steps": 4.2 if started else 0.0},
            "nodes": nodes, "days": days if started else []}


# ── write a flow with AI ─────────────────────────────────────────────────────

def generate(d: dict) -> dict:
    text = str(d.get("description") or "").strip()
    if len(text) < 12:
        _err("describe what the bot should do, in a sentence or two", "bad_request")
    low = text.lower()
    topic = "appointment" if any(w in low for w in ("appoint", "book", "visit", "slot")) else "quote" if any(w in low for w in ("quote", "price", "rate", "estimate")) else "support"
    first = {"appointment": "Happy to book that. What is your name?", "quote": "Happy to help with a quote. What is your name?",
             "support": "Sorry to hear that. What is your name?"}[topic]
    nodes = {
        "greet": {"type": "send_text", "text": "Hello {{first_name}}! Thanks for writing to us.", "next": "name"},
        "name": {"type": "ask", "text": first, "validator": "text", "save_as": "attr:FullName", "max_tries": 2, "next": "need"},
        "need": {"type": "ask", "text": "Tell us a little about what you need.", "validator": "text", "save_as": "var:need", "max_tries": 2, "next": "tag"},
        "tag": {"type": "add_tag", "tag": "ai-" + topic, "next": "done"},
        "done": {"type": "handoff", "text": "Thank you {{attr.FullName}}. Our team will reply shortly.", "reason": "new %s" % topic}}
    graph = {"entry": "greet", "order": list(nodes), "nodes": nodes}
    trigger = {"type": "keyword", "match": "contains", "keywords": {"appointment": ["book", "appointment"], "quote": ["quote", "price"], "support": ["help", "problem"]}[topic]}
    issues = check_flow(graph, trigger)
    return {"name": {"appointment": "Book an appointment", "quote": "Get a quote", "support": "Help a customer"}[topic], "trigger": trigger, "graph": graph,
            "issues": issues, "valid": not [i for i in issues if i["severity"] == "error"], "repairs": 0, "tokens": {"tokens_in": 640, "tokens_out": 380}}


# ── telling Meta what an ad earned ───────────────────────────────────────────

def _capi(p: dict) -> dict:
    return p.setdefault("capi", {"dataset_id": "", "test_code": "", "enabled": False})


def _shown(st: dict) -> dict:
    return {"dataset_id": st["dataset_id"], "test_code": st["test_code"], "enabled": bool(st["dataset_id"]) and st["enabled"]}


def capi(route: str, d: dict, p: dict):
    st = _capi(p)
    if route == "capi/get":
        return {"settings": _shown(st), "events": list(EVENTS)}
    if route == "capi/save":
        ds = str(d.get("dataset_id") or "").strip()
        if ds and not ds.isdigit():
            _err("The dataset id is the number from Meta's Events Manager.", "bad_request")
        st.update(dataset_id=ds, test_code=str(d.get("test_code") or "").strip(), enabled=bool(d.get("enabled", True)))
        return {"settings": _shown(st)}
    if route == "capi/test":
        if not st["dataset_id"]:
            _err("Add your dataset id first.", "capi_not_ready")
        if not st["test_code"]:
            _err("Add the test code from Events Manager first; Meta shows a test event only against it.", "capi_not_ready")
        return {"events_received": 1, "fbtrace_id": "demo-trace-1"}
    if route == "capi/send":
        if not st["dataset_id"] or not st["enabled"]:
            _err("Events are not switched on. Add your dataset id in Settings, Developers.", "capi_not_ready")
        return {"events_received": 1, "fbtrace_id": "demo-trace-2"}
    return None


# ── the router ───────────────────────────────────────────────────────────────

def handle(route: str, data: dict, p: dict, s: dict):
    """The routes this module answers, or None when the route is somebody else's."""
    if route == "flows/test":
        return test_route(data)
    if route == "flows/library":
        return get_library()
    if route == "flows/generate":
        return generate(data)
    if route == "flows/analytics":
        from addons.whatsapp import demo_automation
        a = demo_automation._auto(p)
        f = a["flows"].get(data.get("flow_id"))
        if f is None:
            _err("That flow is not in this workspace.", "unknown_flow")
        return analytics(f, data.get("since"), data.get("until"))
    if route == "flows/test_request":
        url = str((data.get("node") or {}).get("url") or "")
        if not url.startswith("https://") or "localhost" in url or "127.0." in url:
            return {"ok": False, "error": "that address cannot be called from a flow", "url": url}
        kept = {k: ("Surat" if "city" in str(v).lower() else "gold") for k, v in ((data.get("node") or {}).get("save") or {}).items()}
        return {"ok": True, "status": 200, "url": url, "body": '{"customer": {"city": "Surat", "tier": "gold"}}', "json": True, "kept": kept}
    if route.startswith("capi/"):
        return capi(route, data, p)
    return None
