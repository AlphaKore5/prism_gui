"""Sample answers for the Ads tab: ad accounts (pasted or signed in with Facebook), ads of three kinds, targeting search, people lists, Meta's review state, numbers over time and
suggestions.

Answers POST /v1/whatsapp/p/ads/* and audiences/* from memory in the shapes prism-wa returns (ads.py, ads_build.py, ads_targeting.py, ads_insights.py, ads_connect.py), so the
Ads screens can be built, shown and tested offline. Reached only through demo_platform.handle, which is switched on with PRISM_WHATSAPP_DEMO=1 and never in a frozen build.

Nothing here spends anything. An ad starts paused; a "review" takes one look to finish; the numbers are the same for the same ad so a screen does not shimmer.

STDLIB ONLY.
"""
from __future__ import annotations

import re
import zlib
from datetime import date, datetime, timedelta, timezone

from addons.whatsapp.license_client import PlatformError

NOW = lambda: datetime.now(timezone.utc)                                              # noqa: E731
ISO = lambda d=None: (d or NOW()).strftime("%Y-%m-%dT%H:%M:%SZ")                      # noqa: E731
KINDS = ("ctwa", "website", "leadform")
WEBSITE_CTAS = ("LEARN_MORE", "SHOP_NOW", "SIGN_UP", "CONTACT_US", "GET_QUOTE", "BOOK_TRAVEL", "APPLY_NOW", "DOWNLOAD", "ORDER_NOW", "SUBSCRIBE", "GET_OFFER")
LEAD_CTAS = ("SIGN_UP", "LEARN_MORE", "GET_QUOTE", "APPLY_NOW", "SUBSCRIBE", "CONTACT_US")
PUBLISHERS = ("facebook", "instagram", "audience_network", "messenger")
STATUS_WORDS = {"ACTIVE": ("running", "Running"), "PAUSED": ("paused", "Paused"), "PENDING_REVIEW": ("review", "In review at Meta"), "DISAPPROVED": ("rejected", "Turned down by Meta")}

PLACES = [{"key": "2418", "name": "Vadodara", "type": "city", "detail": "Gujarat, India", "country": "IN"}, {"key": "2419", "name": "Surat", "type": "city", "detail": "Gujarat, India", "country": "IN"},
          {"key": "2000", "name": "Gujarat", "type": "region", "detail": "India", "country": "IN"}, {"key": "IN", "name": "India", "type": "country", "detail": "", "country": "IN"},
          {"key": "AE", "name": "United Arab Emirates", "type": "country", "detail": "", "country": "AE"}]
INTERESTS = [{"id": "6003", "name": "Interior design", "type": "interests", "detail": "Interests > Home", "size": [1500000, 2200000]},
             {"id": "6005", "name": "Real estate", "type": "interests", "detail": "Interests > Business", "size": [3000000, 4500000]},
             {"id": "6006", "name": "Home improvement", "type": "interests", "detail": "Interests > Home", "size": [2100000, 3000000]}]
BEHAVIOURS = [{"id": "6101", "name": "Small business owners", "type": "behaviors", "detail": "Behaviours > Business", "size": [800000, 1200000]},
              {"id": "6102", "name": "Recently moved", "type": "behaviors", "detail": "Behaviours > Life events", "size": [400000, 700000]}]


def _err(message: str, reason: str, detail: dict = None):
    raise PlatformError(message, reason, detail or {})


def _next(a: dict, prefix: str) -> str:
    a["seq"] += 1
    return "%s%d" % (prefix, a["seq"])


def _st(a: dict) -> dict:
    return a.setdefault("ads_extra", {"audiences": [], "suggestions": [], "connect": {}, "pictures": {}})


# ── checks ───────────────────────────────────────────────────────────────────

def clean_targeting(t) -> dict:
    if not isinstance(t, dict):
        _err("choose who should see it", "bad_targeting")
    geo = t.get("geo_locations") if isinstance(t.get("geo_locations"), dict) else {}
    countries = [str(c).upper() for c in geo.get("countries") or []]
    if any(not re.match(r"^[A-Z]{2}$", c) for c in countries):
        _err("a country is a two-letter code like IN", "bad_targeting")
    out_geo = {}
    if countries:
        out_geo["countries"] = countries
    for kind in ("regions", "cities"):
        keys = [{"key": str((i if isinstance(i, dict) else {"key": i}).get("key"))} for i in geo.get(kind) or []]
        if any(not re.match(r"^[0-9]{1,15}$", k["key"]) for k in keys):
            _err("%s must be chosen from the search results" % ("a city" if kind == "cities" else "a region"), "bad_targeting")
        if keys:
            out_geo[kind] = keys
    if not out_geo:
        _err("choose where to show it: targeting.geo_locations needs countries or cities", "bad_targeting")
    out = {"geo_locations": out_geo}
    lo, hi = t.get("age_min"), t.get("age_max")
    for key, v in (("age_min", lo), ("age_max", hi)):
        if v is not None:
            if not (isinstance(v, int) and not isinstance(v, bool) and 13 <= v <= 65):
                _err("ages are from 13 to 65", "bad_targeting")
            out[key] = v
    if lo is not None and hi is not None and lo > hi:
        _err("the youngest age cannot be above the oldest", "bad_targeting")
    for key in ("genders", "interests", "behaviors", "custom_audiences", "excluded_custom_audiences", "publisher_platforms"):
        if t.get(key):
            out[key] = t[key]
    return out


def _link(url, what="link") -> str:
    url = (url or "").strip()
    if not re.match(r"^https?://[^\s/]+\.[^\s/]+", url):
        _err("the %s must be a full web address starting with https://" % what, "bad_link")
    return url


def build(d: dict) -> dict:
    kind = d.get("kind") or "ctwa"
    if kind not in KINDS:
        _err("an ad is a chat on WhatsApp, a visit to a website, or a lead form", "bad_kind")
    targeting = clean_targeting(d.get("targeting") or {})
    if not str(d.get("name") or "").strip():
        _err("give the ad a name", "name_required")
    if kind == "ctwa" and not 8 <= len(re.sub(r"\D", "", d.get("whatsapp_number") or "")) <= 15:
        _err("the WhatsApp number must include its country code", "bad_number")
    if not str(d.get("message") or "").strip():
        _err("write the ad's main text", "message_required")
    spec = {"kind": kind, "name": d["name"].strip(), "targeting": targeting, "message": d["message"].strip(), "headline": (d.get("headline") or "").strip(),
            "image_hash": d.get("image_hash") or "", "start_time": d.get("start_time") or "", "end_time": d.get("end_time") or ""}
    if d.get("lifetime_budget") is not None:
        if not (isinstance(d["lifetime_budget"], int) and d["lifetime_budget"] >= 100):
            _err("the total budget is a whole number of the smallest currency unit (paise)", "bad_budget")
        if not spec["end_time"]:
            _err("a total budget needs an end date: it is spent between the start and the end", "bad_budget")
        spec["lifetime_budget"] = d["lifetime_budget"]
    else:
        if not (isinstance(d.get("daily_budget"), int) and not isinstance(d.get("daily_budget"), bool) and d["daily_budget"] >= 100):
            _err("the daily budget is a whole number of the smallest currency unit (paise)", "bad_budget")
        spec["daily_budget"] = d["daily_budget"]
    if kind == "ctwa":
        spec["whatsapp_number"] = re.sub(r"\D", "", d["whatsapp_number"])
    elif kind == "website":
        spec["link"] = _link(d.get("link"))
        spec["cta"] = d.get("cta") or "LEARN_MORE"
        if spec["cta"] not in WEBSITE_CTAS:
            _err("the button is one of: %s" % ", ".join(WEBSITE_CTAS), "bad_cta")
    else:
        spec["cta"] = d.get("cta") or "SIGN_UP"
        if spec["cta"] not in LEAD_CTAS:
            _err("the button is one of: %s" % ", ".join(LEAD_CTAS), "bad_cta")
        form = d.get("form") if isinstance(d.get("form"), dict) else {}
        if not form.get("id"):
            qs = form["questions"] if "questions" in form else ["FULL_NAME", "PHONE"]
            if not any((q if isinstance(q, str) else q.get("type")) in ("PHONE", "EMAIL") for q in qs):
                _err("ask for a phone number or an email address, or you cannot reach the people who fill it in", "bad_form")
            _link(form.get("privacy_url"), "privacy policy address")
        spec["form"] = form
    return spec


# ── state ────────────────────────────────────────────────────────────────────

def _account(a: dict, account_id: str) -> dict:
    acct = next((x for x in a["ad_accounts"] if x["id"] == account_id), None)
    if acct is None:
        _err("that ad account is not connected to this workspace", "unknown_account")
    return acct


def _ad(a: dict, ad_id: str) -> dict:
    ad = next((x for x in a["ads"] if x["id"] == ad_id), None)
    if ad is None:
        _err("that ad is not in this workspace", "unknown_ad")
    return ad


def _shown(ad: dict) -> dict:
    spec = ad.get("spec") or {}
    out = {k: v for k, v in ad.items() if k != "spec"}
    out["budget"] = {"daily": spec.get("daily_budget"), "lifetime": spec.get("lifetime_budget"), "start": spec.get("start_time") or None, "end": spec.get("end_time") or None}
    return out


def _numbers(ad: dict, day: date) -> dict:
    """Believable numbers for a day, the same for the same ad and day."""
    seed = zlib.crc32(("%s|%s" % (ad["id"], day.isoformat())).encode())
    spend = 150 + seed % 260
    impressions = spend * (18 + seed % 9)
    clicks = max(1, int(impressions * (0.011 + (seed % 15) / 1000.0)))
    results = clicks // (6 + seed % 5)
    return {"impressions": impressions, "reach": int(impressions * 0.62), "clicks": clicks, "outbound_clicks": clicks // 2, "spend": float(spend), "results": results}


def _day(ad: dict, day: date) -> dict:
    n = _numbers(ad, day)
    kind = ad["kind"]
    out = {"day": day.isoformat(), "impressions": n["impressions"], "reach": n["reach"], "clicks": n["clicks"], "outbound_clicks": n["outbound_clicks"], "spend": n["spend"],
           "conversations": n["results"] if kind == "ctwa" else 0, "leads": n["results"] if kind == "leadform" else 0,
           "ctr": round(100.0 * n["clicks"] / n["impressions"], 2), "cpc": round(n["spend"] / n["clicks"], 2)}
    out["cost_per_conversation"] = round(n["spend"] / out["conversations"], 2) if out["conversations"] else None
    out["cost_per_lead"] = round(n["spend"] / out["leads"], 2) if out["leads"] else None
    return out


def _totals(days: list) -> dict:
    t = {k: sum(d[k] for d in days) for k in ("impressions", "clicks", "outbound_clicks", "conversations", "leads")}
    t["spend"] = round(sum(d["spend"] for d in days), 2)
    t["reach"] = max([d["reach"] for d in days] + [0])
    t["ctr"] = round(100.0 * t["clicks"] / t["impressions"], 2) if t["impressions"] else 0.0
    t["cpc"] = round(t["spend"] / t["clicks"], 2) if t["clicks"] else None
    t["cost_per_conversation"] = round(t["spend"] / t["conversations"], 2) if t["conversations"] else None
    t["cost_per_lead"] = round(t["spend"] / t["leads"], 2) if t["leads"] else None
    return t


# ── the router ───────────────────────────────────────────────────────────────

def handle(route: str, d: dict, p: dict, s: dict, a: dict):
    if not (route.startswith("ads/") or route.startswith("audiences/")):
        return None
    area, action = route.split("/", 1)
    st = _st(a)
    if route == "ads/accounts":
        return {"accounts": [{**x, "connected_via": x.get("connected_via", "manual"), "pixel_id": x.get("pixel_id"), "currency": x.get("currency")} for x in a["ad_accounts"]]}
    if route == "ads/connect":
        acct = re.sub(r"^act_", "", (d.get("ad_account_id") or "").strip())
        if not re.match(r"^[0-9]{5,20}$", acct):
            _err("The ad account id is the number shown in Ads Manager.", "bad_account")
        if not re.match(r"^[0-9]{5,25}$", (d.get("page_id") or "").strip()):
            _err("The Page id is a number.", "bad_page")
        if len((d.get("token") or "").strip()) < 20:
            _err("Paste the access token for this ad account.", "bad_token")
        a["ad_accounts"] = [x for x in a["ad_accounts"] if x["ad_account_id"] != acct] + [
            {"id": _next(a, "x"), "ad_account_id": acct, "page_id": d["page_id"].strip(), "name": d.get("name") or None, "created_at": ISO(), "connected_via": "manual"}]
        return {"account_id": a["ad_accounts"][-1]["id"]}
    if route == "ads/connect_start":
        state = "demo-state-%d" % (len(st["connect"]) + 1)
        st["connect"][state] = {"status": "waiting", "polls": 0}
        return {"state": state, "url": "https://www.facebook.com/v25.0/dialog/oauth?state=" + state}
    if route == "ads/connect_status":
        c = st["connect"].get(d.get("state"))
        if c is None:
            _err("that sign-in was not started here, or it was already used", "unknown_state")
        c["polls"] += 1
        if c["polls"] >= 2 and c["status"] == "waiting":                          # the person came back from Facebook
            c["status"] = "ready"
        options = {"user": "Asha Patel", "accounts": [{"id": "1234567890", "name": "Main account", "currency": "INR"}, {"id": "555000111", "name": "Old account", "currency": "USD"}],
                   "pages": [{"id": "987654321", "name": "Shakti Builders"}]}
        return {"status": c["status"], "error": None, "options": options if c["status"] == "ready" else None}
    if route == "ads/connect_choose":
        c = st["connect"].get(d.get("state"))
        if c is None or c["status"] != "ready":
            _err("that sign-in is not ready to choose from", "wrong_state")
        if re.sub(r"^act_", "", d.get("ad_account_id") or "") not in ("1234567890", "555000111") or d.get("page_id") != "987654321":
            _err("choose one of the ad accounts and Pages Meta showed you", "bad_choice")
        acct = re.sub(r"^act_", "", d["ad_account_id"])
        a["ad_accounts"] = [x for x in a["ad_accounts"] if x["ad_account_id"] != acct] + [
            {"id": _next(a, "x"), "ad_account_id": acct, "page_id": d["page_id"], "name": "Main account" if acct == "1234567890" else "Old account", "created_at": ISO(),
             "connected_via": "facebook", "currency": "INR" if acct == "1234567890" else "USD"}]
        c["status"] = "done"
        return {"account_id": a["ad_accounts"][-1]["id"]}
    if route == "ads/list":
        return {"ads": [_shown(x) for x in a["ads"]]}
    if route == "ads/create":
        spec = build(d)
        _account(a, d.get("account_id"))
        ad = {"id": _next(a, "ad"), "name": spec["name"], "status": "PAUSED", "meta_ids": {"campaign": "123", "adset": "789", "ad": "456"}, "created_at": ISO(), "last_error": None,
              "kind": spec["kind"], "meta_status": None, "review": None, "synced_at": None, "spec": spec, "reviewed": False}
        a["ads"].insert(0, ad)
        return {"ad": {"id": ad["id"], "meta_ids": ad["meta_ids"], "status": "PAUSED", "kind": spec["kind"]}}
    if route == "ads/search":
        _account(a, d.get("account_id"))
        q = str(d.get("q") or "").strip().lower()
        if len(q) < 2:
            _err("type at least two letters", "bad_search")
        pool = {"geo": PLACES, "interests": INTERESTS, "behaviors": BEHAVIOURS, "demographics": []}.get(d.get("kind"))
        if pool is None:
            _err("search for geo, interests, behaviors, demographics", "bad_search")
        return {"results": [dict(x) for x in pool if q in x["name"].lower()][:int(d.get("limit") or 12)]}
    if route == "ads/estimate":
        _account(a, d.get("account_id"))
        t = clean_targeting(d.get("targeting") or {})
        base = 40000 if (t["geo_locations"].get("cities") or t["geo_locations"].get("regions")) else 900000
        narrow = 0.55 if t.get("interests") or t.get("behaviors") else 1.0
        dau = int(base * narrow * ((min(t.get("age_max", 65), 65) - max(t.get("age_min", 18), 18) + 1) / 48.0))
        return {"estimate": {"ready": True, "daily_low": dau, "daily_high": dau, "monthly_low": dau * 22, "monthly_high": dau * 30}}
    if route == "ads/upload_image":
        _account(a, d.get("account_id"))
        if not d.get("asset_id"):
            _err("choose a picture from your Media Library", "bad_image")
        return {"hash": "demohash%d" % (zlib.crc32(str(d["asset_id"]).encode()) % 100000), "filename": "picture.jpg"}
    if route == "ads/copy":
        if not str(d.get("offer") or "").strip():
            _err("offer is required", "bad_request")
        offer = d["offer"].strip()[:60]
        return {"variants": [{"message": "%s. Message us on WhatsApp for a free visit." % offer, "headline": "Free visit", "description": "Talk to us today"},
                             {"message": "Thinking about it? %s — ask us anything." % offer, "headline": "Ask us anything", "description": "We reply fast"},
                             {"message": "%s. This week only, see it for yourself." % offer, "headline": "See it this week", "description": "Book a time"}]}
    if route == "ads/suggestions":
        return {"suggestions": [x for x in st["suggestions"] if x["state"] == (d.get("state") or "open")]}
    if route == "ads/suggest":
        if not st["suggestions"] and any(x["status"] == "ACTIVE" for x in a["ads"]):
            ad = next(x for x in a["ads"] if x["status"] == "ACTIVE")
            st["suggestions"].append({"id": _next(a, "sg"), "ad_id": ad["id"], "ad_name": ad["name"], "kind": "pause", "state": "open", "created_at": ISO(), "params": {},
                                      "reason": "It spent Rs 2,000 in the last seven days and got no chats."})
        return {"suggestions": [x for x in st["suggestions"] if x["state"] == "open"]}
    if route == "ads/decide":
        sg = next((x for x in st["suggestions"] if x["id"] == d.get("suggestion_id")), None)
        if sg is None:
            _err("that suggestion is not in this workspace", "unknown_suggestion")
        if sg["state"] != "open":
            _err("that suggestion was already dealt with", "wrong_state")
        if d.get("apply") is True and sg["kind"] == "pause":
            _ad(a, sg["ad_id"])["status"] = "PAUSED"
        sg["state"] = "applied" if d.get("apply") is True else "dismissed"
        return {"state": sg["state"]}
    if area == "audiences":
        if action == "list":
            return {"audiences": [dict(x) for x in st["audiences"]]}
        if action == "from_segment":
            _account(a, d.get("account_id"))
            seg = next((x for x in s["segments"] if x["id"] == d.get("segment_id")), None)
            if seg is None:
                _err("that segment is not in this workspace", "unknown_segment")
            tags = set(seg["filter"].get("tags") or [])
            people = [c for c in s["contacts"] if not c["opt_out"] and (not tags or tags & set(c["tags"]))]
            if len(people) < 3:                                                   # the real minimum is 100; the demo has ten contacts
                _err("Meta needs at least 100 people with a phone number who have opted in; this segment has %d." % len(people), "too_few")
            aud = {"id": _next(a, "aud"), "account_id": d["account_id"], "name": (d.get("name") or "").strip() or "Prism · %s" % seg["name"], "kind": "segment", "meta_id": "238%d" % (len(st["audiences"]) + 1),
                   "segment_id": seg["id"], "source": {"sent": len(people)}, "size": len(people), "created_at": ISO()}
            st["audiences"].insert(0, aud)
            return {"id": aud["id"], "meta_id": aud["meta_id"], "sent": len(people), "name": aud["name"]}
        if action == "lookalike":
            origin = next((x for x in st["audiences"] if x["id"] == d.get("audience_id")), None)
            if origin is None:
                _err("that people list is not in this workspace", "unknown_audience")
            country, ratio = str(d.get("country") or "").upper(), d.get("ratio", 0.01)
            if not re.match(r"^[A-Z]{2}$", country):
                _err("a country is a two-letter code like IN", "bad_country")
            if not (isinstance(ratio, (int, float)) and 0.01 <= ratio <= 0.2):
                _err("closeness is from 1% (very like them) to 20% (wider)", "bad_ratio")
            aud = {"id": _next(a, "aud"), "account_id": d["account_id"], "name": (d.get("name") or "").strip() or "%s · look-alike %d%% %s" % (origin["name"], round(ratio * 100), country),
                   "kind": "lookalike", "meta_id": "238%d" % (len(st["audiences"]) + 1), "segment_id": None, "source": {"of": origin["meta_id"], "country": country, "ratio": ratio}, "size": None,
                   "created_at": ISO()}
            st["audiences"].insert(0, aud)
            return {"id": aud["id"], "meta_id": aud["meta_id"], "name": aud["name"]}
        if action == "delete":
            before = len(st["audiences"])
            st["audiences"] = [x for x in st["audiences"] if x["id"] != d.get("audience_id")]
            return {"deleted": len(st["audiences"]) < before}
        raise KeyError(route)
    ad = _ad(a, d.get("ad_id"))
    if action == "activate":
        if d.get("confirm") is not True:
            _err("Turning an ad on starts spending. Confirm to continue.", "confirm_required")
        if ad["status"] != "PAUSED":
            _err("only a paused ad can be turned on", "wrong_state")
        ad["status"], ad["meta_status"] = "ACTIVE", "PENDING_REVIEW"
        return {"status": "ACTIVE"}
    if action == "pause":
        ad["status"], ad["meta_status"] = "PAUSED", "PAUSED"
        return {"status": "PAUSED"}
    if action == "status":
        if ad["status"] == "ACTIVE":
            reasons = []
            if "free money" in (ad["spec"].get("message") or "").lower():
                ad["meta_status"], reasons = "DISAPPROVED", ["Misleading claims: the ad promises something it cannot keep"]
            else:
                ad["meta_status"] = "ACTIVE"
        else:
            reasons = []
            ad["meta_status"] = ad["meta_status"] or "PAUSED"
        ad["review"] = {"reasons": reasons} if reasons else None
        ad["synced_at"] = ISO()
        state, words = STATUS_WORDS.get(ad["meta_status"], ("unknown", ad["meta_status"]))
        return {"meta_status": ad["meta_status"], "state": state, "words": words, "reasons": reasons}
    if action == "insights":
        days = [_day(ad, NOW().date() - timedelta(days=i)) for i in range(7)]
        t = _totals(days)
        return {"insights": {"impressions": t["impressions"], "reach": t["reach"], "clicks": t["clicks"], "spend": t["spend"], "conversations_started": t["conversations"],
                             "cost_per_conversation": t["cost_per_conversation"]}}
    if action == "report":
        try:
            since = date.fromisoformat(d["since"]) if d.get("since") else NOW().date() - timedelta(days=29)
            until = date.fromisoformat(d["until"]) if d.get("until") else NOW().date()
        except ValueError:
            _err("dates look like 2026-10-01", "bad_range")
        if since > until or (until - since).days > 365:
            _err("choose a range of up to a year, oldest first", "bad_range")
        days = [_day(ad, since + timedelta(days=i)) for i in range((until - since).days + 1)] if ad["status"] == "ACTIVE" or ad.get("meta_status") else []
        return {"range": {"since": since.isoformat(), "until": until.isoformat()}, "days": days, "totals": _totals(days)}
    raise KeyError(route)
