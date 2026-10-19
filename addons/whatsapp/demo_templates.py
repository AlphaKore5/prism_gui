"""Sample answers for the Templates tab's own routes, in the shapes prism-wa's ops_templates.py and templates.py return: the library
by industry, lint (every kind of template), create with a validity, a sample file for a media header, the AI writer, the rejection
helper and per-template stats.

Reached only through demo_platform.handle (PRISM_WHATSAPP_DEMO=1, never in a frozen build). The rules mirror prism-wa's templates.py,
written out again here because the app never imports the service.

STDLIB ONLY.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from addons.whatsapp.license_client import PlatformError

_ROUTES = ("templates/library", "templates/lint", "templates/create", "templates/upload_sample", "templates/generate",
           "templates/rewrite", "templates/stats", "templates/list")
VARIABLE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
TTL_RANGES = {"MARKETING": (12 * 3600, 30 * 86400), "UTILITY": (30, 12 * 3600), "AUTHENTICATION": (30, 900)}
PROMO = re.compile(r"\b(offers?|discounts?|sales?|\d+\s*%\s*off|coupons?|limited[- ]time|buy now|deals?|cashback|special price|hurry|book now|shop now)\b", re.I)
HINTS = {"INVALID_FORMAT": "Meta found the format wrong. Check that the variables are {{1}}, {{2}} in order with a sample for each, and that none sits at "
                           "the very start or end of the message.",
         "TAG_CONTENT_MISMATCH": "The words do not match the category you chose. A Utility message must be about something the customer is already doing "
                                 "and must not sell. If it reads as a promotion, make it Marketing.",
         "NONE": "Meta gave no reason. The usual causes are variables at the start or end, too many variables for the number of words, or a category "
                 "that does not match the content."}


def _body(text: str, *samples: str) -> dict:
    return {"type": "BODY", "text": text, "example": {"body_text": [list(samples)]}} if samples else {"type": "BODY", "text": text}


def _entry(key, title, industry, category, text, *samples, buttons=(), header_media="", needs_media=""):
    comps = ([{"type": "HEADER", "format": header_media}] if header_media else []) + [_body(text, *samples)]
    if buttons:
        comps.append({"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": b} for b in buttons]})
    item = {"key": key, "title": title, "industry": industry, "category": category, "language": "en_US", "components": comps}
    if needs_media:
        item["needs_media"] = needs_media
    return item


LIBRARY = [
    _entry("quotation_sent", "Quotation sent", "Construction", "UTILITY",
           "Hello {{1}}, thank you for your enquiry. We have prepared quotation {{2}} for your project and sent it to your email. Please reply here "
           "if you would like to go through it together.", "Asha", "Q-2041"),
    _entry("site_visit_confirmation", "Site visit confirmation", "Construction", "UTILITY",
           "Hello {{1}}, your site visit is confirmed for {{2}}. Our engineer will meet you at the project location. Please keep the drawings ready "
           "if you have them.", "Asha", "Saturday 10 AM", buttons=("Confirm", "Reschedule")),
    _entry("site_progress_update", "Site progress update", "Construction", "UTILITY",
           "Hello {{1}}, here is the progress update for {{2}}: about {{3}} of the planned work is complete. Our site engineer can share photos if you "
           "would like to see them.", "Asha", "the boundary wall", "60%"),
    _entry("order_shipped", "Order shipped", "Retail and e-commerce", "UTILITY",
           "Hello {{1}}, your order {{2}} has been shipped with {{3}}. You can track it from the link we have sent to your email.", "Asha", "ORD-1042", "Delhivery"),
    _entry("abandoned_cart", "Items left in the cart", "Retail and e-commerce", "MARKETING",
           "Hello {{1}}, you left {{2}} in your cart. They are still available, and checking out takes just a minute.", "Asha", "two items",
           buttons=("Complete my order", "Stop messages")),
    _entry("fee_reminder", "Fee reminder", "Education", "UTILITY",
           "Hello {{1}}, this is a reminder that the fee of {{2}} for {{3}} is due on {{4}}. Please ignore this message if you have already paid.",
           "Asha", "Rs 12,000", "the second term", "10 November"),
    _entry("demo_class_invite", "Free demo class invite", "Education", "MARKETING",
           "Hello {{1}}, we are running a demo class for {{2}} on {{3}}. Come and see how our teaching works before you decide.", "Asha",
           "the engineering entrance course", "Sunday at 10 AM", buttons=("Reserve a seat", "Stop messages")),
    _entry("appointment_confirmation_clinic", "Appointment confirmed", "Healthcare and clinics", "UTILITY",
           "Hello {{1}}, your appointment with {{2}} is confirmed for {{3}}. Please arrive ten minutes early and carry your previous reports.",
           "Asha", "Dr Mehta", "Friday at 4 PM", buttons=("Confirm", "Reschedule")),
    _entry("site_visit_invite", "Site visit invitation", "Real estate", "MARKETING",
           "Hello {{1}}, you can see {{2}} in person this weekend. Choose a time that suits you and our team will take you around.", "Asha",
           "our new apartments", buttons=("Saturday", "Sunday", "Stop messages")),
    _entry("brochure_share", "Project brochure", "Real estate", "MARKETING",
           "Hello {{1}}, here is the brochure for {{2}} that you asked about. Let us know if you would like to visit the site.", "Asha",
           "Shreeji Heights", header_media="DOCUMENT", needs_media="document", buttons=("Plan a visit", "Stop messages")),
    _entry("table_booking_confirmation", "Table booking confirmed", "Restaurants and food", "UTILITY",
           "Hello {{1}}, your table for {{2}} is booked for {{3}}. Please let us know if your plans change.", "Asha", "four people", "Saturday at 8 PM"),
    _entry("hotel_booking_confirmed", "Hotel booking confirmed", "Travel and hospitality", "UTILITY",
           "Hello {{1}}, your stay at {{2}} from {{3}} to {{4}} is confirmed. We look forward to hosting you.", "Asha", "Hotel Surya", "12 November",
           "14 November"),
    _entry("emi_reminder", "EMI reminder", "Finance and insurance", "UTILITY",
           "Hello {{1}}, your EMI of {{2}} for loan account {{3}} is due on {{4}}. Please keep enough balance in your account.", "Asha", "Rs 8,450",
           "LN-5521", "5 November"),
    _entry("salon_reminder", "Appointment reminder", "Salon and wellness", "UTILITY",
           "Hello {{1}}, a reminder of your {{2}} appointment tomorrow at {{3}}. Please tell us if you cannot make it.", "Asha", "facial", "5 PM"),
    _entry("service_due", "Service due", "Automobile", "UTILITY",
           "Hello {{1}}, your {{2}} is due for its regular service on or before {{3}}. Reply to book a convenient slot at our workshop.", "Asha",
           "Honda City", "15 November", buttons=("Book service", "Remind me later")),
    _entry("event_reminder", "Event reminder", "Events", "UTILITY",
           "Hello {{1}}, {{2}} starts tomorrow at {{3}}. Please arrive early to avoid the queue at the entrance.", "Asha", "the construction expo", "10 AM"),
    _entry("payment_received_generic", "Payment received", "General", "UTILITY",
           "Hello {{1}}, we have received your payment of {{2}} for {{3}}. Thank you. A receipt will be sent to your email.", "Asha", "Rs 18,000",
           "invoice INV-330"),
    _entry("festival_greeting", "Festival greeting", "General", "MARKETING",
           "Hello {{1}}, wishing you and your family a very happy {{2}} from all of us. Thank you for being with us this year.", "Asha", "Diwali",
           buttons=("Stop messages",)),
    _entry("product_launch_picture", "Product launch with a picture", "General", "MARKETING",
           "Hello {{1}}, meet {{2}}, our newest addition. Reply to see all the details and the price.", "Asha", "the compact work bench",
           header_media="IMAGE", needs_media="image", buttons=("Tell me more", "Stop messages")),
    {"key": "festival_limited_offer", "title": "Limited-time festival offer", "industry": "General", "category": "MARKETING", "language": "en_US",
     "needs_media": "image",
     "components": [{"type": "HEADER", "format": "IMAGE"},
                    _body("Hello {{1}}, our festival offer is on for a short time only. Use the code below at the time of ordering to claim it.", "Asha"),
                    {"type": "LIMITED_TIME_OFFER", "limited_time_offer": {"text": "Festival offer", "has_expiration": True}},
                    {"type": "BUTTONS", "buttons": [{"type": "COPY_CODE", "text": "Copy offer code", "example": "FEST25"}]}]},
    {"key": "carousel_new_arrivals", "title": "Carousel of new arrivals", "industry": "General", "category": "MARKETING", "language": "en_US",
     "needs_media": "image",
     "components": [_body("Hello {{1}}, here are this week's new arrivals. Swipe through them and tap the one you like.", "Asha"),
                    {"type": "CAROUSEL", "cards": [
                        {"components": [{"type": "HEADER", "format": "IMAGE"}, {"type": "BODY", "text": "Compact work bench in powder-coated steel"},
                                        {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Tell me more"}]}]},
                        {"components": [{"type": "HEADER", "format": "IMAGE"}, {"type": "BODY", "text": "Heavy duty storage rack with six shelves"},
                                        {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Tell me more"}]}]}]}]},
    {"key": "otp_copy_code", "title": "One-time password (copy code)", "industry": "Authentication", "category": "AUTHENTICATION", "language": "en_US",
     "components": [{"type": "BODY", "add_security_recommendation": True}, {"type": "FOOTER", "code_expiration_minutes": 10},
                    {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE", "text": "Copy code"}]}]},
    {"key": "otp_one_tap", "title": "One-time password (one-tap autofill)", "industry": "Authentication", "category": "AUTHENTICATION", "language": "en_US",
     "needs_app": True,
     "components": [{"type": "BODY", "add_security_recommendation": True}, {"type": "FOOTER", "code_expiration_minutes": 10},
                    {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "ONE_TAP", "text": "Copy code", "autofill_text": "Autofill",
                                                     "package_name": "com.example.app", "signature_hash": "K8a/AX6ELnR"}]}]},
]
INDUSTRIES = sorted({i["industry"] for i in LIBRARY})


def _vars(text) -> list:
    return [m.group(1) for m in VARIABLE.finditer(text or "")]


def _span(seconds: int) -> str:
    for unit, size in (("days", 86400), ("hours", 3600), ("minutes", 60)):
        if seconds >= size and seconds % size == 0:
            return "%d %s" % (seconds // size, unit)
    return "%d seconds" % seconds


def lint(d: dict) -> list:
    out = []
    err = lambda code, msg, where="": out.append({"severity": "error", "code": code, "message": msg, "where": where, "meta_code": None})     # noqa: E731
    warn = lambda code, msg, where="": out.append({"severity": "warning", "code": code, "message": msg, "where": where, "meta_code": None})   # noqa: E731
    category = d.get("category")
    if not re.match(r"^[a-z0-9_]{1,512}$", d.get("name") or ""):
        err("bad_name", "The name may only use lowercase letters, numbers and underscores.", "name")
    if category not in ("MARKETING", "UTILITY", "AUTHENTICATION"):
        err("bad_category", "The category must be MARKETING, UTILITY or AUTHENTICATION.", "category")
    by = {c.get("type"): c for c in d.get("components") or [] if isinstance(c, dict)}
    body = by.get("BODY")
    ttl = d.get("ttl_seconds")
    if ttl not in (None, -1):
        low, high = TTL_RANGES.get(category, (0, 0))
        if isinstance(ttl, bool) or not isinstance(ttl, int) or not low <= ttl <= high:
            err("bad_ttl", "Message validity for %s must be between %s and %s, or left on Meta's default." % (str(category).title(), _span(low), _span(high)), "ttl")
    if category == "AUTHENTICATION":
        buttons = (by.get("BUTTONS") or {}).get("buttons") or []
        if not any(b.get("type") == "OTP" for b in buttons):
            err("auth_needs_otp_button", "An authentication template needs a one-tap, zero-tap or copy-code button.", "BUTTONS")
        for b in buttons:
            if b.get("type") == "OTP" and b.get("otp_type") in ("ONE_TAP", "ZERO_TAP"):
                if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$", b.get("package_name") or ""):
                    err("bad_package", "Give the Android app's package name, like com.example.app.", "BUTTONS")
                if len(b.get("signature_hash") or "") != 11:
                    err("bad_signature_hash", "The app signature hash is 11 characters.", "BUTTONS")
                if b["otp_type"] == "ONE_TAP" and not (b.get("autofill_text") or "").strip():
                    err("autofill_text_empty", "A one-tap button needs the text of its autofill button.", "BUTTONS")
                if b["otp_type"] == "ZERO_TAP" and b.get("zero_tap_terms_accepted") is not True:
                    err("zero_tap_terms", "Zero-tap needs your agreement to Meta's zero-tap terms.", "BUTTONS")
        minutes = (by.get("FOOTER") or {}).get("code_expiration_minutes")
        if minutes is not None and (isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 90):
            err("bad_code_expiry", "The code expiry must be from 1 to 90 minutes.", "FOOTER")
        if "HEADER" in by:
            err("auth_no_header", "An authentication template cannot have a header.", "HEADER")
        return out
    text = (body or {}).get("text") or ""
    if not text.strip():
        err("empty_body", "The body cannot be empty.", "BODY")
    if len(text) > 1024:
        err("body_too_long", "The body is %d characters; the limit is 1024." % len(text), "BODY")
    variables = _vars(text)
    if variables and re.match(r"^\s*\{\{", text):
        err("variable_at_start", "The body cannot start with a variable.", "BODY")
    if variables and re.search(r"\}\}\s*$", text):
        err("variable_at_end", "The body cannot end with a variable.", "BODY")
    samples = ((body or {}).get("example") or {}).get("body_text") or [[]]
    if variables and len(samples[0]) != len(variables):
        err("missing_example", "Give a sample value for each of the %d variables." % len(variables), "BODY")
    if category == "UTILITY" and PROMO.search(text):
        warn("looks_promotional", "This reads like a promotion. Meta is likely to re-categorise a Utility message like this as Marketing, which is billed "
                                  "at the Marketing rate. Make it Marketing now, or take the offer wording out.", "BODY")
    head = by.get("HEADER") or {}
    if head.get("format") in ("IMAGE", "VIDEO", "DOCUMENT") and not (head.get("example") or {}).get("header_handle"):
        err("missing_example", "A %s header needs a sample file." % head["format"].lower(), "HEADER")
    if "LIMITED_TIME_OFFER" in by:
        offer = by["LIMITED_TIME_OFFER"].get("limited_time_offer") or {}
        if category != "MARKETING":
            err("offer_is_marketing", "A limited-time offer is a Marketing template.", "LIMITED_TIME_OFFER")
        if not (offer.get("text") or "").strip():
            err("offer_text_empty", "Say what the offer is, in a few words.", "LIMITED_TIME_OFFER")
        elif len(offer["text"]) > 16:
            err("offer_text_too_long", "The offer text is %d characters; the limit is 16." % len(offer["text"]), "LIMITED_TIME_OFFER")
        if head.get("format") not in ("IMAGE", "VIDEO"):
            err("offer_needs_media", "A limited-time offer needs an image or video header.", "HEADER")
    if "CAROUSEL" in by:
        cards = by["CAROUSEL"].get("cards") or []
        if not 2 <= len(cards) <= 10:
            err("bad_card_count", "A carousel needs 2 to 10 cards.", "CAROUSEL")
        for i, card in enumerate(cards):
            comps = {c.get("type"): c for c in card.get("components", [])}
            if (comps.get("HEADER") or {}).get("format") not in ("IMAGE", "VIDEO"):
                err("card_needs_media", "Every card needs an image or video header.", "CAROUSEL[%d]" % i)
            elif not ((comps["HEADER"].get("example") or {}).get("header_handle")):
                err("missing_example", "Card %d needs a sample picture or video." % (i + 1), "CAROUSEL[%d]" % i)
            if len((comps.get("BODY") or {}).get("text") or "") > 160:
                err("card_body_too_long", "Card %d's text is over 160 characters." % (i + 1), "CAROUSEL[%d]" % i)
    return out


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _checked(name: str, category: str, body: str, samples: list, buttons: list) -> dict:
    comps = [{"type": "BODY", "text": body, "example": {"body_text": [samples]}} if samples else {"type": "BODY", "text": body}]
    if buttons:
        comps.append({"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": b} for b in buttons]})
    issues = lint({"name": name, "category": category, "components": comps})
    return {"name": name, "language": "en_US", "category": category, "components": comps, "issues": issues,
            "valid": not any(i["severity"] == "error" for i in issues)}


def handle(route: str, d: dict, p: dict, s: dict):
    if route not in _ROUTES:
        return None
    if route == "templates/list":
        return {"templates": [{"ttl_seconds": None, **t} for t in p["templates"]]}
    if route == "templates/library":
        return {"library": list(LIBRARY), "industries": list(INDUSTRIES)}
    if route == "templates/lint":
        issues = lint(d)
        return {"issues": issues, "valid": not any(i["severity"] == "error" for i in issues)}
    if route == "templates/create":
        issues = lint(d)
        if any(i["severity"] == "error" for i in issues):
            raise PlatformError("That template has problems.", "template_invalid", {"issues": issues})
        if d.get("ttl_seconds") not in (None, -1, 0) and p.get("plan", "premium") == "basic":
            raise PlatformError("Setting how long a template stays valid needs the Premium plan.", "plan_feature", {})
        p["templates"] = [t for t in p["templates"] if (t["name"], t["language"]) != (d["name"], d.get("language", "en_US"))]
        p["seq"] = p.get("seq", 10) + 1
        ttl = d.get("ttl_seconds")
        p["templates"].append({"id": "t%d" % p["seq"], "name": d["name"], "language": d.get("language", "en_US"), "category": d["category"],
                               "status": "PENDING", "quality": None, "reject_reason": None, "components": d["components"],
                               "ttl_seconds": None if ttl in (None, -1, 0) else ttl})
        return {"id": "t%d" % p["seq"], "status": "PENDING", "issues": issues}
    if route == "templates/upload_sample":
        from addons.whatsapp import demo_media
        found = demo_media.asset(p, d.get("asset_id"))
        want = {"image": "image", "video": "video", "document": "document"}.get(str(d.get("format") or "").lower())
        if want and found["kind"] != want:
            raise PlatformError("that file is a %s, but this template's header is a %s" % (found["kind"], want), "bad_request", {})
        if found["kind"] not in ("image", "video", "document"):
            raise PlatformError("a template header can show a picture, a video or a document", "bad_request", {})
        return {"handle": "4::demo-%s" % found["id"], "asset_id": found["id"], "kind": found["kind"]}
    if route == "templates/generate":
        about = (d.get("description") or "").strip()
        if len(about) < 8:
            raise PlatformError("describe what the message is for, in a sentence", "bad_request", {})
        category = (d.get("category") or "").upper() or ("MARKETING" if re.search(r"offer|discount|sale|launch|festival|new", about, re.I) else "UTILITY")
        topic = re.sub(r"\s+", " ", about)[:40].rstrip(" .,")
        base = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")[:30] or "message"
        tone = {"urgent": "Please reply today", "formal": "We would be glad to assist you", "playful": "We cannot wait to hear from you"}.get(d.get("tone"), "Just reply to this message")
        stop = ["Stop messages"] if category == "MARKETING" else []
        out = [_checked(base, category, "Hello {{1}}, this is a message from us about %s. %s and we will take care of the rest." % (topic.lower(), tone), ["Asha"],
                        ["Tell me more"] + stop),
               _checked(base + "_2", category, "Hello {{1}}, a quick note on %s from our team. We are here whenever you want to talk it through." % topic.lower(),
                        ["Asha"], ["Call me"] + stop),
               _checked(base + "_3", category, "Hello {{1}}, thank you for your interest in %s. Reply to this message and our team will help you with the next step." % topic.lower(),
                        ["Asha"], stop)]
        return {"templates": out[:max(1, min(int(d.get("count") or 3), 5))], "tokens": {"tokens_in": 120, "tokens_out": 260}}
    if route == "templates/rewrite":
        t = next((x for x in p["templates"] if x["id"] == d.get("template_id")), None)
        if t is None:
            raise PlatformError("that template is not in this workspace", "not_available", {})
        reason = (t.get("reject_reason") or "NONE").upper()
        body = next((c.get("text") for c in t["components"] if c.get("type") == "BODY"), "")
        category = "MARKETING" if reason in ("TAG_CONTENT_MISMATCH", "PROMOTIONAL") else t["category"]
        fixed = re.sub(r"\{\{1\}\}\s*(?=[a-z])", "{{1}}, ", body)
        if variables := _vars(body):
            fixed = "Hello {{1}}, " + re.sub(r"^\s*\{\{1\}\}[,\s]*", "", fixed).rstrip(" .{}0123456789") + ". Reply here if you have any questions."
        sug = _checked(t["name"], category, fixed, ["Asha"] + ["sample"] * (len(variables) - 1) if _vars(fixed) else [], [])
        return {"reason": reason, "hints": [HINTS.get(reason, HINTS["NONE"])], "suggestion": sug, "ai": True}
    # templates/stats
    rows = {}
    for c in p["campaigns"]:
        r = rows.setdefault(c["template_name"], {"name": c["template_name"], "language": "en_US", "sent": 0, "delivered": 0, "read": 0, "failed": 0,
                                                 "clicks": 0, "last_sent": c.get("created_at")})
        r["sent"] += c["sent"]
        r["delivered"] += int(c["sent"] * .94)
        r["read"] += int(c["sent"] * .6)
        r["failed"] += c["failed"]
        r["clicks"] += int(c["sent"] * .07)
    out = sorted(rows.values(), key=lambda r: r["name"])
    for r in out:
        r["read_rate"] = round(100.0 * r["read"] / r["sent"], 1) if r["sent"] else 0.0
    return {"stats": out}
