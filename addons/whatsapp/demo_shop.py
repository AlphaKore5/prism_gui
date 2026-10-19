"""Sample answers for the Shop tab: the catalogue, orders, payments and refunds.

Answers POST /v1/whatsapp/p/commerce|catalog|orders|payments/* from memory in the shapes prism-wa returns (commerce.py, payments.py, ops_commerce.py), with the same money arithmetic
and the same order rules, so the Shop screens can be built, shown and tested offline. Reached only through demo_platform.handle (PRISM_WHATSAPP_DEMO=1, never in a frozen
build). Nothing is sent anywhere: "asking for payment" makes a payment that stays waiting until a person says (in the demo, through payments/check) that it was paid.

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
OPEN = ("created", "pending")


def _err(message: str, reason: str):
    raise PlatformError(message, reason, {})


def _wrap(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except M.MoneyError as why:
        _err(str(why), "bad_amount")


def _shop(p: dict) -> dict:
    if "shop" not in p:
        ago = lambda **k: ISO(NOW() - timedelta(**k))                                  # noqa: E731
        products = [
            {"id": "pr1", "retailer_id": "wall-6", "name": "Boundary wall panel", "description": "Precast, 6 ft", "price_paise": 129950, "sale_price_paise": None, "currency": "INR",
             "image_url": None, "url": None, "category": "Walls", "available": True, "meta_product_id": None, "synced_at": None, "created_at": ago(days=9), "updated_at": ago(days=9)},
            {"id": "pr2", "retailer_id": "gate-1", "name": "Main gate", "description": "Powder-coated steel", "price_paise": 800000, "sale_price_paise": 750000, "currency": "INR",
             "image_url": None, "url": None, "category": "Gates", "available": True, "meta_product_id": None, "synced_at": None, "created_at": ago(days=9), "updated_at": ago(days=9)},
            {"id": "pr3", "retailer_id": "paint-1", "name": "Weather paint (20 L)", "description": None, "price_paise": 220000, "sale_price_paise": None, "currency": "INR",
             "image_url": None, "url": None, "category": "Finish", "available": False, "meta_product_id": None, "synced_at": None, "created_at": ago(days=9), "updated_at": ago(days=9)}]
        p["shop"] = {
            "seq": 10,
            "config": {"catalog_id": "5551234567", "catalog_name": "Shakti shop", "currency": "INR", "tax_percent": 18.0, "shipping_paise": 5000, "order_expiry_hours": 48,
                       "gateway": "razorpay", "payment_configuration": None, "razorpay_key_id": "rzp_test_ABCDEFGH12345", "razorpay_secret_set": True, "razorpay_webhook_set": True,
                       "updated_at": ago(days=2)},
            "visible": {"catalog_visible": True, "cart_enabled": False},
            "products": products, "orders": [], "payments": [], "refunds": []}
        sh = p["shop"]
        sh["orders"] = [_make_order(sh, "k1", [{"retailer_id": "wall-6", "quantity": 4}], source="cart", created=ago(hours=3)),
                        _make_order(sh, "k2", [{"retailer_id": "gate-1", "quantity": 1}], source="agent", created=ago(hours=30)),
                        _make_order(sh, "k4", [{"retailer_id": "wall-6", "quantity": 2}, {"retailer_id": "gate-1", "quantity": 1}], source="manual", created=ago(days=3))]
        _request(sh, sh["orders"][1]["id"], at=ago(hours=29))
        paid = _request(sh, sh["orders"][2]["id"], at=ago(days=3))
        _apply(sh, paid["id"], "captured", method="upi", at=ago(days=3, hours=-1))
    return p["shop"]


def _next(sh: dict, prefix: str) -> str:
    sh["seq"] += 1
    return "%s%d" % (prefix, sh["seq"])


def _config(sh: dict, public_url: str = "https://licence.example") -> dict:
    c = dict(sh["config"])
    c["ready"] = _ready(c) is None
    c["webhook_url"] = "%s/v1/whatsapp/pay/razorpay/demo-workspace" % public_url
    return c


def _ready(c: dict):
    if c["gateway"] == "none":
        return "Choose how customers pay first (Shop → Settings)."
    if c["gateway"] == "meta" and not c.get("payment_configuration"):
        return "Add the payment configuration name from WhatsApp Manager first."
    if c["gateway"] == "razorpay" and not (c.get("razorpay_key_id") and c.get("razorpay_secret_set")):
        return "Add your Razorpay key id and secret first."
    return None


def _contact(s: dict, cid):
    return next((c for c in s["contacts"] if c["id"] == cid), None)


# ── products ─────────────────────────────────────────────────────────────────

def clean_product(sh: dict, d: dict) -> dict:
    name = str(d.get("name") or "").strip()
    if not name:
        _err("a product needs a name", "no_name")
    retailer = re.sub(r"[^A-Za-z0-9_\-.]", "", str(d.get("retailer_id") or "").strip())[:100] or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
    if d.get("price") is not None:
        price = _wrap(M.paise, d["price"], what="price")
    elif d.get("price_paise") is not None:
        price = int(d["price_paise"])
    else:
        _err("the price is not a number", "bad_amount")
    sale = _wrap(M.paise, d["sale_price"], what="sale price") if d.get("sale_price") not in (None, "") else None
    if sale is not None and sale > price:
        _err("the sale price cannot be more than the price", "bad_amount")
    for key in ("image_url", "url"):
        v = str(d.get(key) or "").strip()
        if v and not re.match(r"^https?://", v, re.I):
            _err("the %s must start with https://" % key.replace("_", " "), "bad_link")
    return {"retailer_id": retailer, "name": name[:150], "description": (str(d.get("description") or "").strip()[:5000]) or None, "price_paise": price, "sale_price_paise": sale,
            "currency": sh["config"]["currency"], "image_url": (d.get("image_url") or None), "url": (d.get("url") or None), "category": (str(d.get("category") or "").strip()[:100]) or None,
            "available": d.get("available") is not False}


def _by_retailer(sh: dict, rid: str):
    return next((x for x in sh["products"] if x["retailer_id"] == rid), None)


def _save_product(sh: dict, d: dict) -> dict:
    new = clean_product(sh, d)
    if d.get("id"):
        row = next((x for x in sh["products"] if x["id"] == d["id"]), None)
        if row is None:
            _err("that product is not in this workspace", "unknown_product")
        row.update(new, updated_at=ISO())
        return row
    row = _by_retailer(sh, new["retailer_id"])
    if row is not None:
        row.update(new, updated_at=ISO())
        return row
    row = {"id": _next(sh, "pr"), **new, "meta_product_id": None, "synced_at": None, "created_at": ISO(), "updated_at": ISO()}
    sh["products"].append(row)
    return row


# ── orders ───────────────────────────────────────────────────────────────────

def _items(sh: dict, raw) -> list:
    if not isinstance(raw, list) or not raw:
        _err("an order needs at least one item", "no_items")
    out = []
    for r in raw:
        try:
            qty = int(r["quantity"]) if r.get("quantity") not in (None, "") else 1
        except (TypeError, ValueError):
            _err("the quantity is a whole number", "bad_quantity")
        if not 1 <= qty <= 1000:
            _err("the quantity is between 1 and 1000", "bad_quantity")
        if r.get("retailer_id") and not r.get("name") and r.get("price") is None and r.get("unit_paise") is None:
            pr = _by_retailer(sh, str(r["retailer_id"]))
            if pr is None:
                _err("there is no product %r in this workspace" % r["retailer_id"], "unknown_product")
            unit, name = (pr["sale_price_paise"] if pr["sale_price_paise"] is not None else pr["price_paise"]), pr["name"]
        else:
            name = str(r.get("name") or "").strip()
            if not name:
                _err("each item needs a name", "bad_item")
            unit = int(r["unit_paise"]) if r.get("unit_paise") is not None else _wrap(M.paise, r.get("price"), what="price")
        out.append({"retailer_id": str(r.get("retailer_id") or ""), "name": name[:150], "quantity": qty, "unit_paise": unit, "line_paise": unit * qty})
    return out


def _make_order(sh: dict, contact_id, raw_items, *, source="manual", created=None, shipping=None, discount=None, note=None, reference=None) -> dict:
    cfg = sh["config"]
    items = _items(sh, raw_items)
    t = M.totals(items, tax_percent=cfg["tax_percent"], shipping_paise=cfg["shipping_paise"] if shipping is None else _wrap(M.paise, shipping, what="shipping charge"),
                 discount_paise=0 if discount is None else _wrap(M.paise, discount, what="discount"))
    o = {"id": _next(sh, "o"), "contact_id": contact_id, "conversation_id": None, "number_id": "n1", "reference_id": reference or "PR%X%s" % (int(NOW().timestamp()), "%03d" % (sh["seq"] % 1000)),
         "source": source, "status": "draft", "items": items, "currency": cfg["currency"], **t, "address": None, "note": note, "expires_at": None,
         "created_at": created or ISO(), "updated_at": created or ISO()}
    return o


def _order_view(sh: dict, s: dict, o: dict, with_payments: bool = True) -> dict:
    c = _contact(s, o["contact_id"])
    out = dict(o, contact_name=c["name"] if c else None, contact_phone=c["phone"] if c else None)
    if with_payments:
        out["payments"] = [{k: pay.get(k) for k in ("id", "provider", "status", "amount_paise", "refunded_paise", "method", "link_url", "created_at", "paid_at", "last_error")}
                           for pay in sorted((x for x in sh["payments"] if x["order_id"] == o["id"]), key=lambda x: x["created_at"], reverse=True)]
    return out


def _get_order(sh: dict, oid) -> dict:
    o = next((x for x in sh["orders"] if x["id"] == oid), None)
    if o is None:
        _err("that order is not in this workspace", "unknown_order")
    return o


def _set_status(sh: dict, o: dict, status: str) -> None:
    if status not in M.STATES:
        _err("an order is one of: %s" % ", ".join(M.STATES), "bad_status")
    if status == o["status"]:
        return
    if status not in M.NEXT[o["status"]]:
        _err("an order that is %s cannot become %s" % (o["status"].replace("_", " "), status.replace("_", " ")), "bad_move")
    o["status"], o["updated_at"] = status, ISO()


# ── payments ─────────────────────────────────────────────────────────────────

def _request(sh: dict, order_id, *, at=None, send: bool = True) -> dict:
    o = _get_order(sh, order_id)
    why = _ready(sh["config"])
    if why:
        _err(why, "not_ready")
    if o["status"] not in ("draft", "awaiting_payment", "failed"):
        _err("this order is %s, so it cannot be paid for" % o["status"].replace("_", " "), "order_locked")
    if o["total_paise"] <= 0:
        _err("the order has nothing to pay", "no_total")
    if not o["contact_id"]:
        _err("choose which customer this order is for", "no_contact")
    for old in sh["payments"]:
        if old["order_id"] == o["id"] and old["status"] in OPEN:
            old["status"] = "cancelled"
    provider = "meta" if sh["config"]["gateway"] == "meta" else "razorpay"
    pay = {"id": _next(sh, "p"), "order_id": o["id"], "reference_id": o["reference_id"], "provider": provider, "status": "pending", "amount_paise": o["total_paise"], "refunded_paise": 0,
           "currency": o["currency"], "method": None, "txn_id": None, "provider_ref": ("plink_%d" % sh["seq"]) if provider == "razorpay" else None,
           "link_url": ("https://rzp.io/i/demo%d" % sh["seq"]) if provider == "razorpay" else None, "wamid": None, "last_error": None, "checked_at": None, "paid_at": None,
           "created_at": at or ISO(), "updated_at": at or ISO(), "contact_id": o["contact_id"], "number_id": "n1", "order_total_paise": o["total_paise"], "refunds": []}
    sh["payments"].append(pay)
    o["status"], o["updated_at"] = "awaiting_payment", at or ISO()
    o["expires_at"] = ISO(NOW() + timedelta(hours=sh["config"]["order_expiry_hours"]))
    return pay


def _apply(sh: dict, payment_id, state: str, *, method=None, at=None) -> None:
    pay = next(x for x in sh["payments"] if x["id"] == payment_id)
    rank = {"created": 0, "pending": 1, "cancelled": 2, "expired": 2, "failed": 2, "captured": 3, "partially_refunded": 4, "refunded": 5}
    if rank[state] <= rank[pay["status"]] and not (state == "captured" and pay["status"] in ("failed", "expired", "cancelled")):
        return
    pay["status"], pay["updated_at"] = state, at or ISO()
    o = _get_order(sh, pay["order_id"])
    if state == "captured":
        pay["method"], pay["paid_at"], pay["txn_id"] = method or "upi", at or ISO(), "pay_%s" % pay["id"]
        if o["status"] in ("draft", "awaiting_payment", "failed"):
            o["status"], o["updated_at"] = "paid", at or ISO()
    elif state in ("failed", "expired") and o["status"] == "awaiting_payment":
        o["status"], o["updated_at"] = "failed", at or ISO()


def _payment_view(sh: dict, s: dict, pay: dict, brief: bool = False) -> dict:
    keys = ("id", "order_id", "reference_id", "provider", "status", "amount_paise", "refunded_paise", "currency", "method", "txn_id", "provider_ref", "link_url", "wamid", "last_error",
            "checked_at", "paid_at", "created_at", "updated_at")
    out = {k: pay.get(k) for k in keys}
    o = _get_order(sh, pay["order_id"])
    c = _contact(s, o["contact_id"])
    out["contact_name"], out["contact_phone"] = (c["name"], c["phone"]) if c else (None, None)
    if not brief:
        out.update(contact_id=o["contact_id"], number_id="n1", order_total_paise=o["total_paise"], refunds=list(pay.get("refunds") or []))
    return out


def _dashboard(sh: dict) -> dict:
    pays = sh["payments"]
    got = [x for x in pays if x["status"] in ("captured", "partially_refunded", "refunded")]
    refunded = sum(r["amount_paise"] for x in pays for r in x.get("refunds") or [])
    bucket = lambda st: {"count": sum(1 for x in pays if x["status"] == st), "paise": sum(x["amount_paise"] for x in pays if x["status"] == st)}   # noqa: E731
    settled = len(got) + sum(1 for x in pays if x["status"] in ("failed", "expired", "cancelled"))
    days = {}
    for x in got:
        d = (x["paid_at"] or x["created_at"])[:10]
        days.setdefault(d, [0, 0])
        days[d][0] += 1
        days[d][1] += x["amount_paise"]
    methods = {}
    for x in got:
        methods.setdefault(x["method"] or "unknown", [0, 0])
        methods[x["method"] or "unknown"][0] += 1
        methods[x["method"] or "unknown"][1] += x["amount_paise"]
    received = sum(x["amount_paise"] for x in got)
    return {"received_paise": received, "received_count": len(got), "refunded_paise": refunded, "net_paise": received - refunded,
            "average_paise": int(received / len(got)) if got else 0, "pending": bucket("pending"), "failed": bucket("failed"), "expired": bucket("expired"),
            "abandoned": sum(1 for x in pays if x["status"] in OPEN and x["created_at"] < ISO(NOW() - timedelta(hours=1))),
            "conversion_percent": round(100.0 * len(got) / settled, 1) if settled else 0.0, "orders": len(sh["orders"]), "ordered_paise": sum(o["total_paise"] for o in sh["orders"]),
            "days": [{"day": d, "count": c, "paise": a} for d, (c, a) in sorted(days.items())], "methods": [{"method": m, "count": c, "paise": a} for m, (c, a) in methods.items()],
            "since": ISO(NOW() - timedelta(days=30)), "until": ISO(NOW() + timedelta(days=1))}


# ── the router ───────────────────────────────────────────────────────────────

def handle(route: str, d: dict, p: dict, s: dict):
    area = route.split("/", 1)[0]
    if area not in ("commerce", "catalog", "orders", "payments"):
        return None
    sh = _shop(p)
    if route == "commerce/config/get":
        return {"config": _config(sh)}
    if route == "commerce/config/save":
        c = sh["config"]
        if "catalog_id" in d:
            cid = str(d["catalog_id"] or "").strip()
            if cid and not re.match(r"^[0-9]{5,25}$", cid):
                _err("a catalogue id is a number, shown in Commerce Manager", "bad_catalog")
            c["catalog_id"] = cid or None
        if "catalog_name" in d:
            c["catalog_name"] = (str(d["catalog_name"] or "").strip()[:100]) or None
        if "currency" in d:
            cur = str(d["currency"] or "INR").strip().upper()
            if not re.match(r"^[A-Z]{3}$", cur):
                _err("a currency is three letters, like INR", "bad_currency")
            c["currency"] = cur
        if "tax_percent" in d:
            try:
                tax = float(d["tax_percent"] or 0)
            except (TypeError, ValueError):
                _err("tax is a percentage, like 18", "bad_tax")
            if not 0 <= tax <= 100:
                _err("tax is a percentage between 0 and 100", "bad_tax")
            c["tax_percent"] = tax
        if "shipping" in d:
            c["shipping_paise"] = _wrap(M.paise, d["shipping"] or 0, what="shipping charge")
        if "order_expiry_hours" in d:
            try:
                hours = int(d["order_expiry_hours"]) if d["order_expiry_hours"] not in (None, "") else 48
            except (TypeError, ValueError):
                _err("the hours a payment request stays open is a whole number", "bad_expiry")
            if not 1 <= hours <= 720:
                _err("a payment request can stay open from 1 hour to 30 days", "bad_expiry")
            c["order_expiry_hours"] = hours
        if "gateway" in d:
            if d["gateway"] not in ("none", "meta", "razorpay"):
                _err("customers pay through Meta's payments or Razorpay links", "bad_gateway")
            c["gateway"] = d["gateway"]
        if "payment_configuration" in d:
            c["payment_configuration"] = (str(d["payment_configuration"] or "").strip()[:100]) or None
        if "razorpay_key_id" in d:
            key = (str(d["razorpay_key_id"] or "").strip()) or None
            if key and not re.match(r"^rzp_(test|live)_[A-Za-z0-9]{8,}$", key):
                _err("a Razorpay key id looks like rzp_live_… or rzp_test_…", "bad_key")
            c["razorpay_key_id"] = key
        if (d.get("razorpay_secret") or "").strip():
            c["razorpay_secret_set"] = True
        if (d.get("razorpay_webhook_secret") or "").strip():
            c["razorpay_webhook_set"] = True
        c["updated_at"] = ISO()
        return {"config": _config(sh)}

    if route == "catalog/list":
        rows = list(sh["products"])
        q = (d.get("q") or "").lower()
        if q:
            rows = [x for x in rows if q in x["name"].lower() or q in x["retailer_id"].lower() or q in (x["category"] or "").lower()]
        if d.get("category"):
            rows = [x for x in rows if x["category"] == d["category"]]
        if d.get("available") is not None:
            rows = [x for x in rows if x["available"] == d["available"]]
        rows.sort(key=lambda x: (x["name"].lower(), x["retailer_id"]))
        return {"products": [dict(x) for x in rows], "total": len(rows), "categories": sorted({x["category"] for x in sh["products"] if x["category"]})}
    if route == "catalog/save":
        return {"product": dict(_save_product(sh, d))}
    if route == "catalog/delete":
        n = len(sh["products"])
        sh["products"] = [x for x in sh["products"] if x["id"] != d.get("product_id")]
        return {"deleted": len(sh["products"]) < n}
    if route == "catalog/import":
        reader = csv.DictReader(io.StringIO(d.get("csv") or ""))
        heads = {h.strip().lower(): h for h in (reader.fieldnames or []) if h}
        if not ({"title", "name"} & set(heads)) or "price" not in heads:
            _err("the file needs at least a title (or name) column and a price column", "bad_file")
        added = updated = 0
        problems = []
        for n, row in enumerate(reader, start=2):
            pick = lambda *names: next((row[heads[x]] for x in names if x in heads and row.get(heads[x]) not in (None, "")), None)   # noqa: E731
            try:
                data = {"retailer_id": pick("id", "retailer_id", "sku"), "name": pick("title", "name"), "description": pick("description"),
                        "price": re.sub(r"(?i)\s*[A-Z]{3}$", "", str(pick("price") or "")).strip(), "sale_price": re.sub(r"(?i)\s*[A-Z]{3}$", "", str(pick("sale_price") or "")).strip() or None,
                        "category": pick("category", "product_type"), "available": str(pick("availability", "available") or "in stock").lower() in ("in stock", "true", "yes", "1", "available")}
                existed = _by_retailer(sh, clean_product(sh, data)["retailer_id"]) is not None
                _save_product(sh, data)
                updated += 1 if existed else 0
                added += 0 if existed else 1
            except PlatformError as why:
                problems.append({"row": n, "error": str(why)})
        return {"added": added, "updated": updated, "problems": problems[:50], "skipped": len(problems)}
    if route == "catalog/pull":
        if not sh["config"]["catalog_id"]:
            _err("add the catalogue id first", "no_catalog")
        if _by_retailer(sh, "chair-9") is None:
            sh["products"].append({"id": _next(sh, "pr"), "retailer_id": "chair-9", "name": "Garden bench", "description": None, "price_paise": 450000, "sale_price_paise": None,
                                   "currency": "INR", "image_url": None, "url": None, "category": "Furniture", "available": True, "meta_product_id": "m77", "synced_at": ISO(),
                                   "created_at": ISO(), "updated_at": ISO()})
            return {"added": 1, "updated": len(sh["products"]) - 1}
        return {"added": 0, "updated": len(sh["products"])}
    if route == "catalog/push":
        if not sh["config"]["catalog_id"]:
            _err("add the catalogue id first", "no_catalog")
        for x in sh["products"]:
            x["synced_at"] = ISO()
        return {"sent": len(sh["products"])}
    if route == "catalog/catalogs":
        return {"catalogs": [{"id": "5551234567", "name": "Shakti shop"}, {"id": "5559876543", "name": "Old catalogue"}]}
    if route == "catalog/visibility":
        return dict(sh["visible"])
    if route == "catalog/set_visibility":
        for key in ("catalog_visible", "cart_enabled"):
            if d.get(key) is not None:
                sh["visible"][key] = bool(d[key])
        return dict(sh["visible"])
    if route == "catalog/send":
        if not sh["config"]["catalog_id"]:
            _err("add the catalogue id first (Shop → Settings)", "no_catalog")
        if d.get("kind") == "product" and _by_retailer(sh, d.get("retailer_id") or "") is None:
            _err("there is no product %r in this workspace" % d.get("retailer_id"), "unknown_product")
        if d.get("kind") == "products":
            ids = [i for sec in d.get("sections") or [] for i in sec.get("retailer_ids") or []]
            if not 1 <= len(ids) <= 30:
                _err("a product list holds 1 to 30 products", "bad_sections")
        return {"queued": True}

    if route == "orders/list":
        rows = [o for o in sh["orders"] if (not d.get("status") or o["status"] == d["status"])]
        q = (d.get("q") or "").lower()
        if q:
            rows = [o for o in rows if q in o["reference_id"].lower() or q in ((_contact(s, o["contact_id"]) or {}).get("name") or "").lower()]
        counts = {}
        for o in sh["orders"]:
            counts[o["status"]] = counts.get(o["status"], 0) + 1
        rows.sort(key=lambda o: o["created_at"], reverse=True)
        return {"orders": [_order_view(sh, s, o, with_payments=False) for o in rows], "total": len(rows), "counts": counts}
    if route == "orders/get":
        return {"order": _order_view(sh, s, _get_order(sh, d.get("order_id")))}
    if route == "orders/create":
        if d.get("contact_id") and _contact(s, d["contact_id"]) is None:
            _err("that contact is not in this workspace", "unknown_contact")
        o = _make_order(sh, d.get("contact_id"), d.get("items"), source="agent", shipping=d.get("shipping") if d.get("shipping") not in (None, "") else None,
                        discount=d.get("discount") if d.get("discount") not in (None, "") else None, note=(str(d.get("note") or "").strip()[:1000]) or None,
                        reference=re.sub(r"[^A-Za-z0-9_\-]", "", d["reference_id"])[:35] if d.get("reference_id") else None)
        sh["orders"].append(o)
        return {"order": _order_view(sh, s, o)}
    if route == "orders/update":
        o = _get_order(sh, d.get("order_id"))
        if o["status"] not in ("draft", "failed"):
            _err("an order cannot be changed once a payment was asked for; cancel it and make a new one", "order_locked")
        items = _items(sh, d["items"]) if "items" in d else o["items"]
        t = M.totals(items, tax_percent=sh["config"]["tax_percent"], shipping_paise=_wrap(M.paise, d["shipping"]) if d.get("shipping") not in (None, "") else o["shipping_paise"],
                     discount_paise=_wrap(M.paise, d["discount"]) if d.get("discount") not in (None, "") else o["discount_paise"])
        o.update(items=items, **t, updated_at=ISO())
        if d.get("note") is not None:
            o["note"] = d["note"]
        return {"order": _order_view(sh, s, o)}
    if route == "orders/status":
        o = _get_order(sh, d.get("order_id"))
        _set_status(sh, o, d.get("status") or "")
        return {"order": _order_view(sh, s, o)}
    if route == "orders/cancel":
        o = _get_order(sh, d.get("order_id"))
        for pay in sh["payments"]:
            if pay["order_id"] == o["id"] and pay["status"] in OPEN:
                pay["status"] = "cancelled"
        _set_status(sh, o, "cancelled")
        return {"order": _order_view(sh, s, o)}

    if route == "payments/request":
        return {"payment": _payment_view(sh, s, _request(sh, d.get("order_id"), send=d.get("send") is not False))}
    if route == "payments/list":
        rows = [x for x in sh["payments"] if not d.get("status") or x["status"] == d["status"]]
        rows.sort(key=lambda x: x["created_at"], reverse=True)
        return {"payments": [_payment_view(sh, s, x, brief=True) for x in rows], "total": len(rows)}
    if route == "payments/get":
        pay = next((x for x in sh["payments"] if x["id"] == d.get("payment_id")), None)
        if pay is None:
            _err("that payment is not in this workspace", "unknown_payment")
        return {"payment": _payment_view(sh, s, pay)}
    if route == "payments/check":
        pay = next((x for x in sh["payments"] if x["id"] == d.get("payment_id")), None)
        if pay is None:
            _err("that payment is not in this workspace", "unknown_payment")
        if pay["status"] in OPEN:                                        # in the demo, the gateway says "paid" the first time it is asked
            _apply(sh, pay["id"], "captured", method="upi")
        pay["checked_at"] = ISO()
        return {"payment": _payment_view(sh, s, pay)}
    if route == "payments/refund":
        pay = next((x for x in sh["payments"] if x["id"] == d.get("payment_id")), None)
        if pay is None:
            _err("that payment is not in this workspace", "unknown_payment")
        if pay["status"] not in ("captured", "partially_refunded"):
            _err("only a payment that was received can be refunded", "not_refundable")
        left = pay["amount_paise"] - pay["refunded_paise"]
        amount = left if d.get("amount") in (None, "") else _wrap(M.paise, d["amount"], what="refund")
        if amount <= 0 or amount > left:
            _err("the refund must be between 0.01 and %s (what is left of this payment)" % M.rupees(left), "bad_amount")
        if not d.get("record_only") and not (sh["config"].get("razorpay_secret_set") and pay.get("txn_id")):
            _err("Prism cannot send this refund (no Razorpay credentials, or the gateway's payment id is not known yet). Refund it in your gateway dashboard, then record it here.",
                 "no_gateway_refund")
        pay.setdefault("refunds", []).append({"id": _next(sh, "rf"), "amount_paise": amount, "speed": d.get("speed") or "normal", "status": "recorded" if d.get("record_only") else "processed",
                                              "reason": (d.get("reason") or "")[:300] or None, "error": None, "created_at": ISO()})
        pay["refunded_paise"] += amount
        pay["status"] = "refunded" if pay["refunded_paise"] >= pay["amount_paise"] else "partially_refunded"
        if pay["status"] == "refunded":
            o = _get_order(sh, pay["order_id"])
            if o["status"] in ("paid", "processing", "shipped", "completed"):
                o["status"] = "refunded"
        return {"payment": _payment_view(sh, s, pay)}
    if route == "payments/dashboard":
        return _dashboard(sh)
    if route == "payments/retarget":
        out = []
        for o in sh["orders"]:
            if o["status"] not in ("failed", "awaiting_payment"):
                continue
            latest = next((x for x in sorted(sh["payments"], key=lambda x: x["created_at"], reverse=True) if x["order_id"] == o["id"]), None)
            c = _contact(s, o["contact_id"])
            if latest is None or c is None or c.get("opt_out"):
                continue
            out.append({"contact_id": o["contact_id"], "name": c["name"], "phone": c["phone"], "order_id": o["id"], "reference_id": o["reference_id"], "total_paise": o["total_paise"],
                        "currency": o["currency"], "payment_status": latest["status"], "last_try": latest["updated_at"]})
        return {"people": out}
    return None
