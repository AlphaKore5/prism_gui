"""Sample answers for the Forms tab: forms that open inside a chat, built from starting points, checked, "published", sent, and their answers.

Answers POST /v1/whatsapp/p/forms/* from memory in the shapes prism-wa returns (forms.py, ops_forms.py), with a small copy of its checks and of the Flow JSON it makes, so the Forms
screens can be built, shown and tested offline. Reached only through demo_platform.handle (PRISM_WHATSAPP_DEMO=1, never in a frozen build). Nothing goes to Meta: "publishing"
only runs the checks and gives the form an id.

The real rules live in prism-wa (forms.py); this copy is deliberately the same size as what the screens need.

STDLIB ONLY.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone

from addons.whatsapp.license_client import PlatformError

NOW = lambda: datetime.now(timezone.utc)                                              # noqa: E731
ISO = lambda d=None: (d or NOW()).strftime("%Y-%m-%dT%H:%M:%SZ")                      # noqa: E731
FLOW_VERSION = "6.3"
CATEGORIES = ("SIGN_UP", "SIGN_IN", "APPOINTMENT_BOOKING", "LEAD_GENERATION", "CONTACT_US", "CUSTOMER_SUPPORT", "SURVEY", "OTHER")
KINDS = {"text": "text", "email": "email", "phone": "phone", "number": "number", "paragraph": None, "date": None, "dropdown": None, "radio": None, "checkbox": None, "opt_in": None}
CHOICE = ("dropdown", "radio", "checkbox")
OPTION_MAX = {"dropdown": 200, "radio": 20, "checkbox": 20}
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
SCREEN_RE = re.compile(r"^[A-Z][A-Z_]{0,39}$")


def _err(message: str, reason: str, problems=None):
    raise PlatformError(message, reason, {"problems": problems or []})


def _choices(*titles) -> list:
    return [{"id": re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")[:30] or "x", "title": t} for t in titles]


AVAIL = {"weekdays": [0, 1, 2, 3, 4, 5], "start": "10:00", "end": "17:00", "slot_minutes": 60, "capacity": 1, "min_notice_hours": 2, "window_days": 21, "tz": "Asia/Kolkata",
         "date_field": "date", "slot_field": "slot"}
TEMPLATES = {
    "lead_capture": {"name": "Lead capture", "categories": ["LEAD_GENERATION"], "endpoint": False, "tag_on_submit": "form-lead",
                     "about": "A short form for new enquiries: name, phone and what they need.",
                     "screens": [{"id": "ENQUIRY", "title": "Tell us about you", "texts": [{"style": "body", "text": "We will call you back within a day."}], "button": "Send", "fields": [
                         {"kind": "text", "name": "name", "label": "Your name", "required": True}, {"kind": "phone", "name": "phone", "label": "Phone number", "required": True},
                         {"kind": "email", "name": "email", "label": "Email", "required": False},
                         {"kind": "dropdown", "name": "need", "label": "What do you need?", "required": True, "options": _choices("Boundary wall", "Gate", "Painting", "Something else")},
                         {"kind": "paragraph", "name": "note", "label": "Anything to add?", "required": False}]}],
                     "mapping": {"name": "@name", "email": "@email", "need": "Interest"}, "settings": {"thank_you": "Thank you! We will be in touch soon."}},
    "appointment": {"name": "Book an appointment", "categories": ["APPOINTMENT_BOOKING"], "endpoint": True, "tag_on_submit": "booked",
                    "about": "Pick a day and a free time. Prism shows only the times that are still free and will not double-book one.",
                    "screens": [{"id": "BOOK", "title": "Book a visit", "texts": [{"style": "body", "text": "Choose a day, then a time."}], "button": "Book", "fields": [
                        {"kind": "text", "name": "name", "label": "Your name", "required": True}, {"kind": "date", "name": "date", "label": "Day", "required": True, "live": "date"},
                        {"kind": "dropdown", "name": "slot", "label": "Time", "required": True, "live": "slots", "options": []},
                        {"kind": "paragraph", "name": "note", "label": "Anything to know?", "required": False}]}],
                    "mapping": {"name": "@name", "date": "Visit_date", "slot": "Visit_time"}, "settings": {"thank_you": "Booked! We will remind you before the visit.", "availability": AVAIL}},
    "feedback": {"name": "Feedback", "categories": ["SURVEY"], "endpoint": False, "tag_on_submit": "feedback-given", "about": "Ask how it went: a rating, what they liked and a comment.",
                 "screens": [{"id": "FEEDBACK", "title": "How did we do?", "texts": [], "button": "Send feedback", "fields": [
                     {"kind": "radio", "name": "rating", "label": "Your rating", "required": True, "options": [{"id": "5", "title": "5 - Excellent"}, {"id": "4", "title": "4 - Good"},
                                                                                                             {"id": "3", "title": "3 - Okay"}, {"id": "2", "title": "2 - Poor"},
                                                                                                             {"id": "1", "title": "1 - Very poor"}]},
                     {"kind": "checkbox", "name": "liked", "label": "What went well?", "required": False, "options": _choices("The work", "The price", "The team", "On time")},
                     {"kind": "paragraph", "name": "comment", "label": "Comments", "required": False}]}],
                 "mapping": {"rating": "Last_rating"}, "settings": {"thank_you": "Thank you for telling us."}},
    "site_visit": {"name": "Site visit request", "categories": ["APPOINTMENT_BOOKING"], "endpoint": False, "tag_on_submit": "visit-requested",
                   "about": "Ask where and when they would like someone to come. A person confirms the time.",
                   "screens": [{"id": "VISIT", "title": "Request a site visit", "texts": [], "button": "Request visit", "fields": [
                       {"kind": "text", "name": "name", "label": "Your name", "required": True}, {"kind": "phone", "name": "phone", "label": "Phone number", "required": True},
                       {"kind": "paragraph", "name": "address", "label": "Site address", "required": True}, {"kind": "date", "name": "date", "label": "Preferred day", "required": True},
                       {"kind": "dropdown", "name": "period", "label": "Preferred time", "required": True, "options": _choices("Morning", "Afternoon", "Evening")}]}],
                   "mapping": {"name": "@name", "address": "Site_address", "date": "Visit_date"}, "settings": {"thank_you": "Thank you. We will confirm the visit shortly."}},
    "quotation": {"name": "Quotation request", "categories": ["LEAD_GENERATION"], "endpoint": False, "tag_on_submit": "quote-requested", "about": "Two steps: what they want built, then how to reach them.",
                  "screens": [{"id": "PROJECT", "title": "Your project", "texts": [], "button": "Next", "fields": [
                      {"kind": "dropdown", "name": "project", "label": "Type of work", "required": True, "options": _choices("Boundary wall", "Gate", "Painting", "Repair", "Other")},
                      {"kind": "number", "name": "area", "label": "Area in sq ft", "required": False}, {"kind": "text", "name": "city", "label": "City", "required": True}]},
                              {"id": "CONTACT", "title": "How do we reach you?", "texts": [], "button": "Get my quote", "fields": [
                                  {"kind": "text", "name": "name", "label": "Your name", "required": True}, {"kind": "phone", "name": "phone", "label": "Phone number", "required": True},
                                  {"kind": "email", "name": "email", "label": "Email", "required": False}, {"kind": "opt_in", "name": "consent", "label": "OK to message me", "required": True}]}],
                  "mapping": {"name": "@name", "email": "@email", "city": "City", "project": "Interest"}, "settings": {"thank_you": "Thank you! Your quotation is on its way."}},
    "kyc_lite": {"name": "Basic details", "categories": ["SIGN_UP"], "endpoint": False, "tag_on_submit": "details-given",
                 "about": "Name, date of birth, city and only the last four digits of an ID. Never ask for a whole ID number here.",
                 "screens": [{"id": "DETAILS", "title": "Your details", "texts": [{"style": "caption", "text": "Only the last four digits of your ID. Never send the whole number in a chat."}],
                              "button": "Submit", "fields": [
                                  {"kind": "text", "name": "name", "label": "Full name", "required": True}, {"kind": "date", "name": "dob", "label": "Date of birth", "required": True},
                                  {"kind": "text", "name": "city", "label": "City", "required": True},
                                  {"kind": "dropdown", "name": "id_type", "label": "ID type", "required": True, "options": _choices("Aadhaar", "PAN", "Driving licence", "Voter ID")},
                                  {"kind": "text", "name": "id_last4", "label": "Last 4 digits", "required": True, "helper": "Only the last four digits"},
                                  {"kind": "opt_in", "name": "consent", "label": "I agree", "required": True}]}],
                 "mapping": {"name": "@name", "dob": "Date_of_birth", "city": "City"}, "settings": {"thank_you": "Thank you. Your details are saved."}},
}


# ── cleaning and checking (a small copy of prism-wa's forms.py) ──────────────

def clean_screens(raw) -> list:
    if not isinstance(raw, list):
        _err("a form is a list of screens", "bad_screens")
    out = []
    for s in raw:
        if not isinstance(s, dict):
            _err("each screen is a title, some text and some fields", "bad_screens")
        fields = []
        for f in s.get("fields") or []:
            kind = str(f.get("kind") or "text")
            options = []
            for o in f.get("options") or []:
                if isinstance(o, dict):
                    options.append({"id": str(o.get("id") or o.get("title") or "")[:30], "title": str(o.get("title") or o.get("id") or "")[:60]})
                elif str(o).strip():
                    options.append({"id": re.sub(r"[^a-z0-9]+", "_", str(o).lower()).strip("_")[:30] or "x", "title": str(o)[:60]})
            field = {"kind": kind, "name": str(f.get("name") or "").strip().lower()[:60], "label": str(f.get("label") or "").strip()[:80], "required": f.get("required") is not False}
            if f.get("helper"):
                field["helper"] = str(f["helper"]).strip()[:80]
            if kind in CHOICE:
                field["options"] = options
            if f.get("live") in ("date", "slots"):
                field["live"] = f["live"]
            fields.append(field)
        texts = [{"style": t.get("style") if t.get("style") in ("heading", "subheading", "body", "caption") else "body", "text": str(t.get("text") or "").strip()[:600]}
                 for t in (s.get("texts") or []) if isinstance(t, dict) and str(t.get("text") or "").strip()]
        out.append({"id": str(s.get("id") or "").strip().upper().replace(" ", "_")[:40], "title": str(s.get("title") or "").strip()[:60], "texts": texts,
                    "button": str(s.get("button") or "Continue").strip()[:60], "fields": fields})
    return out


def clean_settings(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = {"thank_you": str(raw.get("thank_you") or "").strip()[:600]}
    a = raw.get("availability")
    if isinstance(a, dict):
        try:
            weekdays = sorted({int(x) for x in a.get("weekdays") or [] if 0 <= int(x) <= 6})
            ints = {k: (int(a[k]) if a.get(k) not in (None, "") else default) for k, default in (("slot_minutes", 60), ("capacity", 1), ("min_notice_hours", 2), ("window_days", 21))}
        except (TypeError, ValueError):
            _err("days, slot length, capacity and notice are whole numbers", "bad_availability")
        start, end = str(a.get("start") or "10:00"), str(a.get("end") or "17:00")
        hhmm = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
        if not (hhmm.match(start) and hhmm.match(end)) or start >= end:
            _err("the opening time must be before the closing time (like 10:00 and 17:00)", "bad_availability")
        if not weekdays:
            _err("choose at least one day of the week", "bad_availability")
        if not 10 <= ints["slot_minutes"] <= 480 or not 1 <= ints["capacity"] <= 100 or not 0 <= ints["min_notice_hours"] <= 720 or not 1 <= ints["window_days"] <= 120:
            _err("a slot is 10 minutes to 8 hours, a slot can take 1 to 100 people, notice is up to 30 days, and booking opens up to 120 days ahead", "bad_availability")
        out["availability"] = {"weekdays": weekdays, "start": start, "end": end, **ints, "tz": str(a.get("tz") or "Asia/Kolkata"), "date_field": str(a.get("date_field") or "date")[:40],
                               "slot_field": str(a.get("slot_field") or "slot")[:40]}
    return out


def check(form: dict) -> list:
    problems = []

    def bad(where, message):
        problems.append({"where": where, "message": message})

    screens = form.get("screens") or []
    if not (form.get("name") or "").strip():
        bad("Form", "Give the form a name.")
    if not screens:
        bad("Form", "Add at least one screen.")
    if len(screens) > 8:
        bad("Form", "A form can have up to 8 screens.")
    ids, names = set(), {}
    for n, s in enumerate(screens, start=1):
        here = "Screen %d" % n
        if not SCREEN_RE.match(s["id"] or ""):
            bad(here, "The screen's id uses capital letters and underscores only (like BOOK_VISIT).")
        elif s["id"] in ids:
            bad(here, "Two screens are called %s." % s["id"])
        ids.add(s["id"])
        if s["id"] == "SUCCESS" and form.get("endpoint"):
            bad(here, "SUCCESS is kept for the thank-you screen of a live form; choose another id.")
        if not s["title"]:
            bad(here, "Give the screen a title.")
        if not s["fields"] and not s["texts"]:
            bad(here, "A screen needs at least a field or some text.")
        if len(s["fields"]) > 20:
            bad(here, "A screen holds up to 20 fields; move some to the next screen.")
        if not s["button"] or len(s["button"]) > 35:
            bad(here, "The button needs a label of up to 35 characters.")
        for f in s["fields"]:
            where = "%s · %s" % (here, f["label"] or f["name"] or "a field")
            if f["kind"] not in KINDS:
                bad(where, "%r is not a kind of field." % f["kind"])
                continue
            if not NAME_RE.match(f["name"]):
                bad(where, "The field's name uses lowercase letters, numbers and underscores, and starts with a letter.")
            elif f["name"] in names:
                bad(where, "Two fields are called %r (screen %d and screen %d)." % (f["name"], names[f["name"]], n))
            names[f["name"]] = n
            if not f["label"]:
                bad(where, "Give the field a label.")
            elif len(f["label"]) > (30 if f["kind"] == "opt_in" else 20):
                bad(where, "The label is up to %d characters; use the helper text for more." % (30 if f["kind"] == "opt_in" else 20))
            if f["kind"] in CHOICE:
                if not f["options"] and f.get("live") != "slots":
                    bad(where, "Add at least one choice.")
                if len(f["options"]) > OPTION_MAX[f["kind"]]:
                    bad(where, "A %s can have up to %d choices." % (f["kind"], OPTION_MAX[f["kind"]]))
                if any(len(o["title"]) > 30 or not o["title"] for o in f["options"]):
                    bad(where, "Each choice needs a title of up to 30 characters.")
                if len({o["id"] for o in f["options"]}) != len(f["options"]):
                    bad(where, "Two choices share an id.")
    if form.get("endpoint") and any(f.get("live") == "slots" for s in screens for f in s["fields"]):
        a = (form.get("settings") or {}).get("availability")
        if not a:
            bad("Form", "A form that offers live times needs opening days and hours.")
        else:
            for key in ("date_field", "slot_field"):
                if a[key] not in names:
                    bad("Form", "The %s field %r is not in the form." % ("day" if key == "date_field" else "time", a[key]))
    for field, target in (form.get("mapping") or {}).items():
        if field not in names:
            bad("Contact details", "%r is saved to %s but is not a field of the form." % (field, target))
    if not form.get("categories"):
        bad("Form", "Choose at least one category.")
    elif any(c not in CATEGORIES for c in form["categories"]):
        bad("Form", "Choose categories from: %s." % ", ".join(CATEGORIES))
    return problems


def to_flow_json(form: dict) -> dict:
    screens, endpoint = form["screens"], bool(form.get("endpoint"))
    out, carried, routing = [], [], {}
    for n, s in enumerate(screens):
        last = n == len(screens) - 1
        data = {c: {"type": "string", "__example__": ""} for c in carried}
        slots = any(f.get("live") == "slots" for f in s["fields"])
        if slots:
            data["slots"] = {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "title": {"type": "string"}}}, "__example__": [{"id": "10:00", "title": "10:00 AM"}]}
        payload = {c: "${data.%s}" % c for c in carried}
        payload.update({f["name"]: "${form.%s}" % f["name"] for f in s["fields"]})
        children = [{"type": {"heading": "TextHeading", "subheading": "TextSubheading", "body": "TextBody", "caption": "TextCaption"}[t["style"]], "text": t["text"]} for t in s["texts"]]
        comps = []
        for f in s["fields"]:
            base = {"name": f["name"], "label": f["label"], "required": bool(f["required"])}
            if f["kind"] in ("text", "email", "phone", "number"):
                comps.append({"type": "TextInput", "input-type": KINDS[f["kind"]], **base})
            elif f["kind"] == "paragraph":
                comps.append({"type": "TextArea", **base})
            elif f["kind"] == "date":
                comps.append({"type": "DatePicker", **base})
            elif f["kind"] == "opt_in":
                comps.append({"type": "OptIn", **base})
            else:
                comps.append({"type": {"dropdown": "Dropdown", "radio": "RadioButtonsGroup", "checkbox": "CheckboxGroup"}[f["kind"]],
                              "data-source": "${data.slots}" if f.get("live") == "slots" else [{"id": o["id"], "title": o["title"]} for o in f["options"]], **base})
        if last and not endpoint:
            action = {"name": "complete", "payload": payload}
        elif last:
            action = {"name": "data_exchange", "payload": {"step": "submit", **payload}}
        else:
            action = {"name": "navigate", "next": {"type": "screen", "name": screens[n + 1]["id"]}, "payload": payload}
        comps.append({"type": "Footer", "label": s["button"], "on-click-action": action})
        children.append({"type": "Form", "name": "form", "children": comps})
        screen = {"id": s["id"], "title": s["title"], "data": data, "layout": {"type": "SingleColumnLayout", "children": children}}
        if last and not endpoint:
            screen["terminal"], screen["success"] = True, True
        out.append(screen)
        routing[s["id"]] = [screens[n + 1]["id"]] if not last else (["SUCCESS"] if endpoint else [])
        carried += [f["name"] for f in s["fields"]]
    if endpoint:
        out.append({"id": "SUCCESS", "title": "Done", "terminal": True, "success": True, "data": {}, "layout": {"type": "SingleColumnLayout", "children": [
            {"type": "TextHeading", "text": "Done"}, {"type": "TextBody", "text": (form.get("settings") or {}).get("thank_you") or "Thank you."},
            {"type": "Footer", "label": "Close", "on-click-action": {"name": "complete", "payload": {}}}]}})
        routing["SUCCESS"] = []
    flow = {"version": FLOW_VERSION, "screens": out}
    if endpoint:
        flow["data_api_version"], flow["routing_model"] = "3.0", routing
    return flow


# ── the state ────────────────────────────────────────────────────────────────

def _forms(p: dict) -> dict:
    if "forms" not in p:
        def make(key, fid, status, responses, name=None):
            t = json.loads(json.dumps(TEMPLATES[key]))
            return {"id": fid, "name": name or t["name"], "template": key, "categories": t["categories"], "screens": clean_screens(t["screens"]), "flow_json": None,
                    "meta_flow_id": ("FLOW" + fid[1:]) if status == "published" else None, "status": status, "version": 1, "endpoint": t["endpoint"], "mapping": t["mapping"],
                    "tag_on_submit": t["tag_on_submit"], "settings": clean_settings(t["settings"]), "problems": [], "responses": responses,
                    "published_at": ISO(NOW() - timedelta(days=5)) if status == "published" else None, "created_at": ISO(NOW() - timedelta(days=6)), "updated_at": ISO(NOW() - timedelta(days=5))}
        f1, f2 = make("lead_capture", "f1", "published", 3, "Walls enquiry"), make("appointment", "f2", "draft", 0)
        p["forms"] = {"seq": 10, "forms": [f1, f2], "key": {"has_key": False, "uploaded_at": None, "created_at": None},
                      "responses": [{"id": "r1", "form_id": "f1", "form": "Walls enquiry", "contact_id": "k1", "contact_name": None, "contact_phone": None,
                                     "answers": {"name": "Asha Shah", "phone": "9800000001", "email": "asha@shakti.example", "need": "gate", "note": "Corner plot"},
                                     "created_at": ISO(NOW() - timedelta(days=2))},
                                    {"id": "r2", "form_id": "f1", "form": "Walls enquiry", "contact_id": "k2", "contact_name": None, "contact_phone": None,
                                     "answers": {"name": "Ravi Patel", "phone": "9800000002", "need": "boundary_wall"}, "created_at": ISO(NOW() - timedelta(days=1))},
                                    {"id": "r3", "form_id": "f1", "form": "Walls enquiry", "contact_id": None, "contact_name": None, "contact_phone": None,
                                     "answers": {"name": "Meena Joshi", "phone": "9800000003", "need": "painting"}, "created_at": ISO(NOW() - timedelta(hours=5))}]}
    return p["forms"]


def _view(f: dict) -> dict:
    out = dict(f)
    out["problems_now"] = check(f)
    return out


def _get(st: dict, fid) -> dict:
    f = next((x for x in st["forms"] if x["id"] == fid), None)
    if f is None:
        _err("that form is not in this workspace", "unknown_form")
    return f


def handle(route: str, d: dict, p: dict, s: dict):
    if not route.startswith("forms/"):
        return None
    st = _forms(p)
    action = route.split("/", 1)[1]
    if action == "templates":
        return {"templates": [{"key": k, "name": t["name"], "about": t["about"], "categories": t["categories"], "live": t["endpoint"], "screens": len(t["screens"]),
                               "fields": sum(len(x["fields"]) for x in t["screens"])} for k, t in TEMPLATES.items()]}
    if action == "list":
        rows = []
        for f in st["forms"]:
            g = {k: v for k, v in f.items() if k != "flow_json"}
            g["screens_count"], g["fields_count"] = len(f["screens"]), sum(len(x["fields"]) for x in f["screens"])
            rows.append(g)
        return {"forms": rows}
    if action == "get":
        return {"form": _view(_get(st, d.get("form_id")))}
    if action == "create":
        base = {}
        if d.get("template"):
            if d["template"] not in TEMPLATES:
                _err("there is no starting point called %r" % d["template"], "unknown_template")
            base = json.loads(json.dumps(TEMPLATES[d["template"]]))
        screens = clean_screens(d["screens"] if "screens" in d else base.get("screens", []))
        name = str(d.get("name") or base.get("name") or "").strip()[:100]
        if not name:
            _err("give the form a name", "no_name")
        st["seq"] += 1
        f = {"id": "f%d" % st["seq"], "name": name, "template": d.get("template"), "categories": d.get("categories") or base.get("categories") or ["LEAD_GENERATION"], "screens": screens,
             "flow_json": None, "meta_flow_id": None, "status": "draft", "version": 1, "endpoint": bool(d["endpoint"]) if "endpoint" in d else bool(base.get("endpoint")),
             "mapping": dict(d.get("mapping", base.get("mapping")) or {}), "tag_on_submit": (d.get("tag_on_submit", base.get("tag_on_submit")) or None),
             "settings": clean_settings(d.get("settings", base.get("settings"))), "problems": [], "responses": 0, "published_at": None, "created_at": ISO(), "updated_at": ISO()}
        st["forms"].insert(0, f)
        return {"form": _view(f)}
    if action == "update":
        f = _get(st, d.get("form_id"))
        if "screens" in d:
            f["screens"] = clean_screens(d["screens"])
        for key in ("name", "categories", "endpoint", "mapping", "tag_on_submit"):
            if key in d:
                f[key] = d[key]
        if "settings" in d:
            f["settings"] = clean_settings(d["settings"])
        f["name"] = str(f["name"] or "").strip()[:100]
        if not f["name"]:
            _err("give the form a name", "no_name")
        f["updated_at"] = ISO()
        return {"form": _view(f)}
    if action == "duplicate":
        f = _get(st, d.get("form_id"))
        st["seq"] += 1
        g = json.loads(json.dumps(f))
        g.update(id="f%d" % st["seq"], name=(f["name"] + " (copy)")[:100], meta_flow_id=None, status="draft", version=1, responses=0, published_at=None, problems=[], created_at=ISO(), updated_at=ISO())
        st["forms"].insert(0, g)
        return {"form": _view(g)}
    if action == "delete":
        f = _get(st, d.get("form_id"))
        st["forms"].remove(f)
        return {"deleted": True}
    if action == "check":
        if d.get("form_id"):
            f = json.loads(json.dumps(_get(st, d["form_id"])))
            for key, fn in (("screens", clean_screens), ("settings", clean_settings)):
                if key in d:
                    f[key] = fn(d[key])
            for key in ("endpoint", "name", "mapping", "categories"):
                if key in d:
                    f[key] = d[key]
        else:
            f = {"name": d.get("name") or "x", "screens": clean_screens(d.get("screens") or []), "endpoint": bool(d.get("endpoint")), "mapping": d.get("mapping") or {},
                 "settings": clean_settings(d.get("settings")), "categories": d.get("categories") or ["LEAD_GENERATION"]}
        return {"problems": check(f)}
    if action == "preview":
        return {"flow_json": to_flow_json(_get(st, d.get("form_id")))}
    if action == "publish":
        f = _get(st, d.get("form_id"))
        problems = check(f)
        if problems:
            _err("The form is not ready: %s" % problems[0]["message"], "form_invalid", problems)
        if f["endpoint"]:
            st["key"].update(has_key=True, uploaded_at=ISO(), created_at=st["key"]["created_at"] or ISO())
        old = f["status"] == "published"
        st["seq"] += 1
        f.update(meta_flow_id="FLOW%d" % st["seq"], status="published", problems=[], version=f["version"] + (1 if old else 0), published_at=ISO(), flow_json=to_flow_json(f), updated_at=ISO())
        return {"form": _view(f)}
    if action == "retire":
        f = _get(st, d.get("form_id"))
        if f["status"] != "published":
            _err("only a published form can be retired", "not_published")
        f["status"] = "deprecated"
        return {"form": _view(f)}
    if action == "sync":
        return {"changed": 0}
    if action == "send":
        f = _get(st, d.get("form_id"))
        if f["status"] != "published":
            _err("publish the form before sending it", "not_published")
        if not any(c["id"] == d.get("contact_id") for c in s["contacts"]):
            _err("that contact is not in this workspace", "unknown_contact")
        return {"queued": True}
    if action == "responses":
        rows = [dict(r) for r in st["responses"] if not d.get("form_id") or r["form_id"] == d["form_id"]]
        for r in rows:
            c = next((x for x in s["contacts"] if x["id"] == r["contact_id"]), None)
            r["contact_name"], r["contact_phone"] = (c["name"], c["phone"]) if c else (r.get("contact_name"), r.get("contact_phone"))
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return {"responses": rows, "total": len(rows)}
    if action == "export":
        f = _get(st, d.get("form_id"))
        names = [x["name"] for sc in f["screens"] for x in sc["fields"]]
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["received", "contact", "phone"] + names)
        for r in st["responses"]:
            if r["form_id"] == f["id"]:
                w.writerow([r["created_at"], r.get("contact_name") or "", r.get("contact_phone") or ""] + [str(r["answers"].get(n, "")) for n in names])
        return {"csv": out.getvalue()}
    if action == "key_status":
        return dict(st["key"])
    if action == "upload_key":
        st["key"].update(has_key=True, uploaded_at=ISO(), created_at=st["key"]["created_at"] or ISO())
        return {"uploaded": 1}
    return None
