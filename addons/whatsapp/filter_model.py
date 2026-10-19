"""The filter a person builds on screen, and the segment filter language prism-wa understands.

Pure and Qt-free, so it is tested without a window. A screen's rows ARE leaves of the language
(`{"field": "tags", "op": "has_any", "value": ["vip"]}`); a filter is one leaf, or `{"all"|"any": [leaves]}`.

    fields(defs)             what can be filtered on, each with its operators, in words
    build(match, leaves)     rows -> the filter prism-wa takes
    rows_of(filter)          the filter -> (match, rows), or None when it is too nested for the on-screen editor
    describe(filter, defs)   the filter in a sentence, for the chip under a table
"""
from __future__ import annotations

import i18n

# A "kind" picks the value editor: text, words (a comma list), flag, time, state, number, date, choice, boolflag.


def t(en: str) -> str:
    """The wrapper the string extractor looks for: every literal passed to it joins the translatable catalogue."""
    return i18n.t(en)


def states() -> list:
    return [("active", t("With the bot")), ("requesting", t("Needs a person")), ("intervened", t("With an agent")), ("closed", t("Resolved"))]


def _text_ops() -> list:
    return [("contains", t("contains")), ("eq", t("is")), ("ne", t("is not")), ("starts_with", t("starts with")),
            ("is_set", t("is filled in")), ("is_not_set", t("is empty"))]


def _time_ops() -> list:
    return [("within_days", t("in the last")), ("older_than_days", t("more than … ago")), ("before", t("is before")), ("after", t("is after"))]


def fields(defs: dict = None) -> list:
    """[{key, label, kind, ops: [(op, label)], options?}] — the built-ins, then one per attribute the workspace defined."""
    out = [
        {"key": "name", "label": t("Name"), "kind": "text", "ops": _text_ops()},
        {"key": "mobile", "label": t("Mobile number"), "kind": "text",
         "ops": [("contains", t("contains")), ("starts_with", t("starts with")), ("eq", t("is"))]},
        {"key": "email", "label": t("Email"), "kind": "text", "ops": _text_ops()},
        {"key": "tags", "label": t("Tags"), "kind": "words",
         "ops": [("has_any", t("has any of")), ("has_all", t("has all of")), ("has_none", t("has none of"))]},
        {"key": "source", "label": t("Source"), "kind": "words", "ops": [("in", t("is any of"))]},
        {"key": "first_msg_tag", "label": t("First message"), "kind": "text", "ops": _text_ops()},
        {"key": "opted_in", "label": t("Opted in"), "kind": "flag", "ops": [("is", t("is"))]},
        {"key": "opted_out", "label": t("Opted out"), "kind": "flag", "ops": [("is", t("is"))]},
        {"key": "blocked", "label": t("Blocked"), "kind": "flag", "ops": [("is", t("is"))]},
        {"key": "created", "label": t("Added"), "kind": "time", "ops": _time_ops()},
        {"key": "last_seen", "label": t("Last wrote"), "kind": "time", "ops": _time_ops()},
        {"key": "conversation_status", "label": t("Chat state"), "kind": "state", "ops": [("eq", t("is"))]},
    ]
    for key, d in sorted((defs or {}).items()):
        kind = (d or {}).get("type") or "string"
        out.append({"key": "attr:" + key, "label": key, "kind": {"number": "number", "date": "date", "bool": "boolflag", "enum": "choice"}.get(kind, "text"),
                    "ops": _attr_ops(kind), "options": list((d or {}).get("options") or [])})
    return out


def _attr_ops(kind: str) -> list:
    if kind == "number":
        return [("eq", t("is")), ("gt", t("is more than")), ("lt", t("is less than")), ("between", t("is between")),
                ("is_set", t("is filled in")), ("is_not_set", t("is empty"))]
    if kind == "date":
        return [("eq", t("is on")), ("gt", t("is after")), ("lt", t("is before")), ("between", t("is between")),
                ("is_set", t("is filled in")), ("is_not_set", t("is empty"))]
    if kind == "bool":
        return [("eq", t("is"))]
    if kind == "enum":
        return [("eq", t("is")), ("ne", t("is not")), ("is_set", t("is filled in")), ("is_not_set", t("is empty"))]
    return _text_ops()


def field_for(key: str, defs: dict = None):
    return next((f for f in fields(defs) if f["key"] == key), None)


def needs_value(op: str) -> bool:
    return op not in ("is_set", "is_not_set")


def complete(leaf: dict, defs: dict = None) -> bool:
    """Is this row finished enough to send? (A row waiting for its value should not turn the table empty.)"""
    f = field_for(leaf.get("field"), defs)
    if f is None or leaf.get("op") not in [o for o, _ in f["ops"]]:
        return False
    if not needs_value(leaf["op"]):
        return True
    v = leaf.get("value")
    if f["kind"] == "flag":
        return isinstance(v, bool)
    if leaf["op"] == "between":
        return isinstance(v, list) and len(v) == 2 and all(str(x).strip() for x in v)
    if isinstance(v, list):
        return bool(v)
    if isinstance(v, bool):
        return True
    return v is not None and str(v).strip() != ""


def build(match: str, leaves: list) -> dict:
    leaves = [dict(x) for x in leaves]
    if not leaves:
        return {"all": []}
    if len(leaves) == 1:
        return leaves[0]
    return {"any" if match == "any" else "all": leaves}


def rows_of(flt) -> tuple | None:
    """(match, [leaf...]) when the on-screen editor can hold this filter, else None."""
    if not flt:
        return "all", []
    if not isinstance(flt, dict):
        return None
    if "field" in flt:
        return "all", [dict(flt)]
    for key in ("all", "any"):
        if key in flt and isinstance(flt[key], list) and all(isinstance(x, dict) and "field" in x for x in flt[key]):
            return key, [dict(x) for x in flt[key]]
    if "tags" in flt and isinstance(flt["tags"], list):                         # the oldest saved shape
        return "all", ([{"field": "tags", "op": "has_any", "value": list(flt["tags"])}] if flt["tags"] else [])
    return None


def describe_leaf(leaf: dict, defs: dict = None) -> str:
    f = field_for(leaf.get("field"), defs)
    if f is None:
        return str(leaf.get("field") or "")
    op = dict(f["ops"]).get(leaf.get("op"), str(leaf.get("op")))
    v = leaf.get("value")
    if not needs_value(leaf.get("op")):
        return "%s %s" % (f["label"], op)
    if f["kind"] == "flag" or f["kind"] == "boolflag":
        yes = v is True or str(v).lower() in ("yes", "true", "1")
        return "%s %s" % (f["label"], t("yes") if yes else t("no"))
    if f["kind"] == "state":
        v = dict(states()).get(v, v)
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v) if leaf.get("op") != "between" else " – ".join(str(x) for x in v)
    if f["kind"] == "time" and leaf.get("op") in ("within_days", "older_than_days"):
        v = "%s %s" % (v, t("days"))
    return "%s %s %s" % (f["label"], op, v)


def describe(flt, defs: dict = None) -> str:
    parsed = rows_of(flt)
    if parsed is None:
        return t("A custom filter")
    match, rows = parsed
    if not rows:
        return ""
    glue = t(" and ") if match == "all" else t(" or ")
    return glue.join(describe_leaf(r, defs) for r in rows)


def is_empty(flt) -> bool:
    parsed = rows_of(flt)
    return parsed is not None and not parsed[1]
