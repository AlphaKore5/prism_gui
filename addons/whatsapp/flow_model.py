"""The flow a person edits, as plain data — no Qt, so every rule here is tested on its own.

A flow is {"entry": id, "nodes": {id: node}, "order": [id, ...]}. The server stores and walks `entry` and `nodes`;
`order` is only for this screen: a database keeps an object's keys in its own order, so without it the steps would shuffle
every time the flow was saved and loaded.

The functions here make a step, give it a name nobody else has, rename it everywhere it is mentioned, remove it without
leaving anything pointing at nothing, and put a flow's steps in the order a person reads them.
"""
from __future__ import annotations

import copy
import re
from typing import Optional

import i18n

NEXT_KEYS = ("next", "else", "timeout_next", "fallback_next", "invalid_next", "ok_next", "error_next")
ID_RE = re.compile(r"^[A-Za-z0-9_]{1,40}$")
WAITING = ("buttons", "list", "ask", "delay", "location_request")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MEDIA_KINDS = ("image", "video", "audio", "document")
CAPI_EVENTS = ("Lead", "Purchase", "ViewContent", "CompleteRegistration", "Contact", "Schedule", "SubmitApplication", "AddToCart",
               "InitiateCheckout", "Subscribe", "StartTrial")


def step_types() -> list:
    """(type, name, what it does) in the order the Add step menu shows them."""
    return [("send_text", i18n.t("Say something"), i18n.t("Send a message.")),
            ("buttons", i18n.t("Ask with buttons"), i18n.t("Up to three buttons the customer taps.")),
            ("list", i18n.t("Ask with a list"), i18n.t("A menu of up to ten choices.")),
            ("ask", i18n.t("Ask a question"), i18n.t("Wait for an answer, check it and keep it.")),
            ("condition", i18n.t("Choose a path"), i18n.t("Go one way or another depending on what you know.")),
            ("set_attribute", i18n.t("Save a detail"), i18n.t("Write something on the contact.")),
            ("add_tag", i18n.t("Add a tag"), i18n.t("Tag the contact.")),
            ("remove_tag", i18n.t("Remove a tag"), i18n.t("Take a tag off the contact.")),
            ("delay", i18n.t("Wait"), i18n.t("Pause before the next step.")),
            ("template", i18n.t("Send a template"), i18n.t("An approved template message.")),
            ("api_request", i18n.t("Call another system"), i18n.t("Ask your own server and use its answer.")),
            ("handoff", i18n.t("Hand over to a person"), i18n.t("Stop the bot and ask your team.")),
            ("agent", i18n.t("Hand over to the AI agent"), i18n.t("Let an AI agent carry on.")),
            ("jump_flow", i18n.t("Go to another flow"), i18n.t("Continue in a different flow.")),
            ("end", i18n.t("End"), i18n.t("Finish the flow.")),
            ("media", i18n.t("Send a file"), i18n.t("A picture, video, voice note or document from your Media Library.")),
            ("send_location", i18n.t("Send a location"), i18n.t("A map pin with a name and address.")),
            ("location_request", i18n.t("Ask for their location"), i18n.t("Ask the customer to share a map pin, and keep it.")),
            ("webhook", i18n.t("Tell another system"), i18n.t("Send the details to your server and carry on without waiting.")),
            ("capi_event", i18n.t("Tell Meta about a result"), i18n.t("Report a lead or a sale from an ad to Meta, so your ads learn.")),
            ("send_products", i18n.t("Show products"), i18n.t("A product card, a list of products, or your whole catalogue.")),
            ("send_form", i18n.t("Send a form"), i18n.t("A form that opens inside the chat, like a booking or an enquiry.")),
            ("request_payment", i18n.t("Ask for payment"), i18n.t("Ask the customer to pay the cart they just sent."))]


def step_groups() -> list:
    """(group name, [step kinds]) for the Add step menu — twenty kinds in one list is too many to scan."""
    return [(i18n.t("Say something"), ["send_text", "media", "send_location", "template"]),
            (i18n.t("Ask the customer"), ["buttons", "list", "ask", "location_request"]),
            (i18n.t("Decide"), ["condition", "delay"]),
            (i18n.t("Remember"), ["set_attribute", "add_tag", "remove_tag"]),
            (i18n.t("Sell"), ["send_products", "send_form", "request_payment"]),
            (i18n.t("Connect"), ["api_request", "webhook", "capi_event", "jump_flow"]),
            (i18n.t("Hand over"), ["handoff", "agent", "end"])]


def type_name(kind: str) -> str:
    return next((n for k, n, _d in step_types() if k == kind), kind)


def new_node(kind: str) -> dict:
    """A step with sensible starting values, valid enough to read (it may still need the person's own words)."""
    base = {
        "send_text": {"type": "send_text", "text": ""},
        "buttons": {"type": "buttons", "text": "", "options": [{"id": "yes", "title": "Yes", "next": None}, {"id": "no", "title": "No", "next": None}]},
        "list": {"type": "list", "text": "", "button_label": "Choose one", "rows": [{"id": "one", "title": "First choice", "next": None}]},
        "ask": {"type": "ask", "text": "", "validator": "text", "max_tries": 2},
        "condition": {"type": "condition", "rules": [{"field": "message", "op": "contains", "value": "", "next": None}]},
        "set_attribute": {"type": "set_attribute", "key": "", "value": ""},
        "add_tag": {"type": "add_tag", "tag": ""},
        "remove_tag": {"type": "remove_tag", "tag": ""},
        "delay": {"type": "delay", "minutes": 30},
        "template": {"type": "template", "name": "", "language": "en_US", "variables": {}},
        "api_request": {"type": "api_request", "method": "GET", "url": "https://", "headers": {}, "save": {}},
        "handoff": {"type": "handoff", "text": "", "reason": ""},
        "agent": {"type": "agent"},
        "jump_flow": {"type": "jump_flow", "flow_id": ""},
        "end": {"type": "end"},
        "media": {"type": "media", "kind": "image", "asset_id": "", "caption": ""},
        "location_request": {"type": "location_request", "text": ""},
        "send_location": {"type": "send_location", "latitude": None, "longitude": None, "name": "", "address": ""},
        "webhook": {"type": "webhook", "method": "POST", "url": "https://", "headers": {}, "body": ""},
        "capi_event": {"type": "capi_event", "event": "Lead"},
        "send_products": {"type": "send_products", "mode": "catalog", "text": ""},
        "send_form": {"type": "send_form", "form_id": "", "text": "", "button": "Open form"},
        "request_payment": {"type": "request_payment", "empty_text": ""},
    }[kind]
    return copy.deepcopy(base)


def unique_id(base: str, existing) -> str:
    stem = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_")[:30] or "step"
    taken = set(existing)
    if stem not in taken:
        return stem
    n = 2
    while "%s_%d" % (stem, n) in taken:
        n += 1
    return "%s_%d" % (stem, n)


def targets_of(node: dict) -> list:
    out = [node[k] for k in NEXT_KEYS if isinstance(node.get(k), str) and node[k]]
    out += [i["next"] for i in choice_items(node) if i.get("next")]
    return out


def choice_items(node: dict) -> list:
    """Every button, list row and condition of a step that can lead somewhere — whether a list keeps its rows in sections or not."""
    items = []
    for key in ("options", "rows", "rules"):
        items += [i for i in node.get(key) or [] if isinstance(i, dict)]
    for section in node.get("sections") or []:
        items += [i for i in (section.get("rows") if isinstance(section, dict) else None) or [] if isinstance(i, dict)]
    return items


def list_rows(node: dict) -> list:
    """The rows of a list step, from its sections when it has them."""
    if node.get("sections"):
        return [r for s in node["sections"] if isinstance(s, dict) for r in (s.get("rows") or []) if isinstance(r, dict)]
    return [r for r in (node.get("rows") or []) if isinstance(r, dict)]


def _retarget(node: dict, fn) -> None:
    for k in NEXT_KEYS:
        if isinstance(node.get(k), str) and node[k]:
            node[k] = fn(node[k])
    for item in choice_items(node):
        if item.get("next"):
            item["next"] = fn(item["next"])


def order_of(graph: dict) -> list:
    """The steps in the order to show them: the saved order, then anything not in it by walking from the entry."""
    nodes = graph.get("nodes") or {}
    out = [i for i in graph.get("order") or [] if i in nodes]
    rest = [i for i in nodes if i not in out]
    if rest:
        seen, stack, walked = set(out), [graph.get("entry")], []
        while stack:
            cur = stack.pop(0)
            if cur in nodes and cur not in seen:
                seen.add(cur)
                walked.append(cur)
                stack.extend(targets_of(nodes[cur]))
        out += walked + [i for i in rest if i not in walked]
    return out


def add_node(graph: dict, kind: str, after: Optional[str] = None, name: str = "") -> str:
    graph.setdefault("nodes", {})
    order = order_of(graph)                                     # before the step exists, so it is not already in it
    nid = unique_id(name or type_name(kind).lower(), graph["nodes"])
    graph["nodes"][nid] = new_node(kind)
    order.insert(order.index(after) + 1 if after in order else len(order), nid)
    graph["order"] = order
    if not graph.get("entry"):
        graph["entry"] = nid
    return nid


def rename_node(graph: dict, old: str, new: str) -> None:
    nodes = graph["nodes"]
    if old not in nodes or old == new:
        return
    if not ID_RE.match(new) or new in nodes:
        raise ValueError("that name is not available")
    nodes[new] = nodes.pop(old)
    if isinstance(graph.get("layout"), dict) and old in graph["layout"]:
        graph["layout"][new] = graph["layout"].pop(old)
    for node in nodes.values():
        _retarget(node, lambda t: new if t == old else t)
    if graph.get("entry") == old:
        graph["entry"] = new
    graph["order"] = [new if i == old else i for i in graph.get("order") or []]


def remove_node(graph: dict, nid: str) -> None:
    """Take a step out. Anything that led to it now ends the flow instead, and the entry moves on if it was this step."""
    nodes = graph["nodes"]
    successor = next(iter(targets_of(nodes.get(nid, {}))), None)
    nodes.pop(nid, None)
    if isinstance(graph.get("layout"), dict):
        graph["layout"].pop(nid, None)
    for node in nodes.values():
        _retarget(node, lambda t: None if t == nid else t)
        # a None must not stay as a key the server would read as a step called "None"
        for k in NEXT_KEYS:
            if k in node and not node[k]:
                node.pop(k)
        for item in choice_items(node):
            if not item.get("next"):
                item["next"] = None
    graph["order"] = [i for i in graph.get("order") or [] if i != nid]
    if graph.get("entry") == nid:
        graph["entry"] = successor if successor in nodes else (order_of(graph)[0] if nodes else None)


def move_node(graph: dict, nid: str, delta: int) -> None:
    order = order_of(graph)
    if nid not in order:
        return
    i = order.index(nid)
    j = max(0, min(len(order) - 1, i + delta))
    order.insert(j, order.pop(i))
    graph["order"] = order


def clean_for_save(graph: dict) -> dict:
    """What goes to the server: no empty targets (a None is a missing `next`, which ends the flow)."""
    out = copy.deepcopy(graph)
    for node in (out.get("nodes") or {}).values():
        for k in NEXT_KEYS:
            if k in node and not node[k]:
                node.pop(k)
        for item in choice_items(node):
            if not item.get("next"):
                item.pop("next", None)
    return out


def slug(title: str, taken) -> str:
    return unique_id(re.sub(r"[^a-z0-9]+", "_", (title or "").lower()) or "choice", taken)


# ── words for the screen ─────────────────────────────────────────────────────

def trigger_words(trigger: dict) -> str:
    t = (trigger or {}).get("type")
    if t == "keyword":
        words = ", ".join("“%s”" % w for w in (trigger.get("keywords") or [])[:3])
        how = {"exact": i18n.t("is exactly"), "contains": i18n.t("contains"), "starts_with": i18n.t("starts with")}.get(trigger.get("match"), "")
        return i18n.t("A message {how} {words}").format(how=how, words=words)
    if t == "regex":
        return i18n.t("A message matching {p}").format(p=trigger.get("pattern"))
    if t == "first_message":
        return i18n.t("A new customer's first message")
    if t == "default":
        return i18n.t("Any message no other flow answers")
    if t == "ad":
        return i18n.t("A click on one of {n} ads").format(n=len(trigger.get("ad_ids") or []))
    if t == "button":
        return i18n.t("The button “{p}” is pressed").format(p=trigger.get("payload"))
    return i18n.t("Not chosen yet")


def describe_step(node: dict) -> str:
    """One line saying what a step does, for lists and problem messages."""
    kind = node.get("type")
    text = (node.get("text") or "").strip().replace("\n", " ")
    if kind in ("send_text", "ask", "buttons", "list", "handoff") and text:
        return text[:60] + ("…" if len(text) > 60 else "")
    if kind == "delay":
        m = node.get("minutes")
        return i18n.t("{n} minutes").format(n=m) if m else i18n.t("{n} seconds").format(n=node.get("seconds"))
    if kind in ("add_tag", "remove_tag"):
        return node.get("tag") or ""
    if kind == "set_attribute":
        return "%s = %s" % (node.get("key"), node.get("value"))
    if kind == "template":
        return node.get("name") or ""
    if kind == "media":
        words = (node.get("caption") or "").strip().replace("\n", " ")
        return "%s%s" % (media_kind_name(node.get("kind")), (" — " + words[:40]) if words else "")
    if kind == "location_request" and text:
        return text[:60] + ("…" if len(text) > 60 else "")
    if kind == "send_location":
        return (node.get("name") or "").strip() or type_name(kind)
    if kind == "webhook":
        return (node.get("url") or "").replace("https://", "")[:50]
    if kind == "capi_event":
        return node.get("event") or ""
    if kind == "send_products":
        return {"product": node.get("retailer_id") or "", "products": i18n.t("{n} products").format(n=len(node.get("retailer_ids") or [])),
                "catalog": i18n.t("The whole catalogue")}.get(node.get("mode"), "")
    if kind == "send_form":
        return (node.get("text") or "").strip()[:50]
    return type_name(kind)


def media_kind_name(kind) -> str:
    return {"image": i18n.t("Picture"), "video": i18n.t("Video"), "audio": i18n.t("Voice note"), "document": i18n.t("Document")}.get(kind, i18n.t("File"))


def issues_by_node(issues: list) -> dict:
    out: dict = {}
    for i in issues or []:
        out.setdefault(i.get("node") or "", []).append(i)
    return out


# ── the picture of a flow: where a step goes, drawn ──────────────────────────

# the ways out of a step that the picture always shows, even when nothing is joined to them yet
EXPECTED = {
    "send_text": ("next",), "set_attribute": ("next",), "add_tag": ("next",), "remove_tag": ("next",), "delay": ("next",), "template": ("next",),
    "media": ("next",), "send_location": ("next",), "webhook": ("next",), "capi_event": ("next",), "send_products": ("next",), "send_form": ("next",), "request_payment": ("next",),
    "buttons": ("fallback_next", "timeout_next"), "list": ("fallback_next", "timeout_next"),
    "ask": ("next", "invalid_next", "timeout_next"), "location_request": ("next", "fallback_next", "timeout_next"),
    "condition": ("else",), "api_request": ("ok_next", "error_next"),
}


def key_words(key: str) -> str:
    return {"next": "", "else": i18n.t("Otherwise"), "timeout_next": i18n.t("No answer"), "fallback_next": i18n.t("Something else"),
            "invalid_next": i18n.t("Wrong answer"), "ok_next": i18n.t("It works"), "error_next": i18n.t("It fails")}.get(key, key)


def rule_words(rule: dict) -> str:
    field = str(rule.get("field") or "")
    base = field.split(":", 1)[0]
    value = str(rule.get("value") or "")
    names = {"message": i18n.t("Message"), "tag": i18n.t("Tag"), "hours": i18n.t("Hours"), "weekday": i18n.t("Day"), "date": i18n.t("Date"), "time": i18n.t("Time"),
             "holiday": i18n.t("Holiday"), "attr": field.split(":", 1)[1] if ":" in field else i18n.t("Detail"), "var": field.split(":", 1)[1] if ":" in field else i18n.t("Saved")}
    return ("%s %s" % (names.get(base, base), value)).strip()[:22]


def branches(node: dict) -> list:
    """Every way out of a step, in the order the picture lists them: [{"label", "key", "holder"}]. `holder[key]` is where it goes (None = the flow ends).
    The choices of a button or list step and the conditions of a "Choose a path" step come first, then the step's own exits."""
    kind = node.get("type")
    out = []
    if kind == "buttons":
        out += [{"label": i.get("title") or i.get("id") or "", "key": "next", "holder": i} for i in node.get("options") or [] if isinstance(i, dict)]
    elif kind == "list":
        out += [{"label": i.get("title") or i.get("id") or "", "key": "next", "holder": i} for i in list_rows(node)]
    elif kind == "condition":
        out += [{"label": rule_words(i), "key": "next", "holder": i} for i in node.get("rules") or [] if isinstance(i, dict)]
    out += [{"label": key_words(k), "key": k, "holder": node} for k in EXPECTED.get(kind, ())]
    return out


def branch_target(b: dict):
    t = b["holder"].get(b["key"])
    return t if isinstance(t, str) and t else None


def set_branch(b: dict, target) -> None:
    b["holder"][b["key"]] = target or None


def reachable_from(graph: dict, start) -> set:
    nodes = graph.get("nodes") or {}
    seen, stack = set(), [start]
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in nodes:
            continue
        seen.add(cur)
        stack.extend(targets_of(nodes[cur]))
    return seen


def auto_layout(graph: dict, across: int = 300, down: int = 40, height=None) -> dict:
    """Where every step sits, left to right in the order a customer meets them. A step already placed by hand keeps its place; the rest are put in columns
    by how far they are from the start, one under another. `height(nid)` is how tall a step is drawn (default 110)."""
    nodes = graph.get("nodes") or {}
    placed = {k: list(v) for k, v in (graph.get("layout") or {}).items() if k in nodes and isinstance(v, (list, tuple)) and len(v) == 2}
    depth, queue = {}, [graph.get("entry")] if graph.get("entry") in nodes else []
    if queue:
        depth[queue[0]] = 0
    while queue:
        cur = queue.pop(0)
        for t in targets_of(nodes[cur]):
            if t in nodes and t not in depth:
                depth[t] = depth[cur] + 1
                queue.append(t)
    tail = max(depth.values(), default=-1) + 1
    for nid in order_of(graph):
        depth.setdefault(nid, tail)
    height = height or (lambda _n: 110)
    columns: dict = {}
    for nid in order_of(graph):
        columns.setdefault(depth[nid], []).append(nid)
    out = {}
    for d, ids in sorted(columns.items()):
        y = 0
        for nid in ids:
            out[nid] = placed.get(nid) or [d * across, y]
            y += height(nid) + down
    return out
