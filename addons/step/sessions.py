"""STEP chats: every run on one part, and its edited versions, as ONE thread.

A person attaches A.step, drafts it, asks about it, edits it — then comes back
a week later. That is one conversation about one part, not five unrelated runs,
and what they come back to is two files to carry on from: the original and the
edited one. This module only groups and words what past runs recorded; the
screen decides what to do with it. Pure functions, no Qt, no engine.

A "lineage" is the part's own name with any " - modified <date>" stamped on by
an Edit taken off, so A.step and "A - modified 2026-10-15 201121.step" belong
to the same chat.
"""
from __future__ import annotations

import os
import re
import time

# Runs on one part closer together than this belong to one sitting.
LEGACY_GAP = 2 * 3600

_MODIFIED = re.compile(r"\s*-\s*modified\b.*$", re.IGNORECASE)


def lineage(name: str) -> str:
    """The part a file belongs to: its name without extension and without an
    Edit's ' - modified …' stamp."""
    stem = os.path.splitext(os.path.basename(name or ""))[0]
    return _MODIFIED.sub("", stem).strip() or stem


def _models(rec: dict) -> list:
    return list(((rec or {}).get("step") or {}).get("models") or [])


def chat_id(rec: dict) -> str:
    """The chat a run belongs to: the id it was saved with, or — for runs
    saved before chats had ids — the part's own name."""
    info = (rec or {}).get("step") or {}
    if info.get("chat"):
        return str(info["chat"])
    models = _models(rec)
    name = lineage(models[0].get("file", "")) if models else ""
    return "lin:" + name if name else ""


def build_sessions(records: list) -> list:
    """Group STEP run records into chats, newest first.

    A chat starts when a file is attached and holds every run done in it —
    and its edited copies. Attach the same file again later and that is a NEW
    chat; reopen one from History and you carry on in it.

    `records` are {"path", "stamp", "rec"} dicts (rec = the run's JSON).
    Returns [{"key", "name", "runs", "stamp", "actions"}], each chat's runs
    oldest first.
    """
    groups: dict[str, list] = {}
    legacy: dict[str, list] = {}
    for item in records:
        rec = item.get("rec") or {}
        info = rec.get("step") or {}
        if not info:
            continue
        if info.get("chat"):
            groups.setdefault(str(info["chat"]), []).append(item)
            continue
        name = chat_id(rec)               # "lin:<part>"
        if name:
            legacy.setdefault(name, []).append(item)
    # Runs saved before chats had ids: one chat per sitting. Runs on the same
    # part more than LEGACY_GAP apart are different chats — lumping two days
    # of work on one part into a single chat made "13 runs" of what was really
    # several separate pieces of work.
    for name, items in legacy.items():
        items.sort(key=lambda r: r.get("stamp", 0))
        chunk: list = []
        for item in items:
            if chunk and item.get("stamp", 0) - chunk[-1].get("stamp", 0) > LEGACY_GAP:
                groups[f"{name}@{int(chunk[0].get('stamp', 0))}"] = chunk
                chunk = []
            chunk.append(item)
        if chunk:
            groups[f"{name}@{int(chunk[0].get('stamp', 0))}"] = chunk
    sessions = []
    for key, runs in groups.items():
        runs.sort(key=lambda r: r.get("stamp", 0))
        first_models = _models(runs[0]["rec"])
        name = lineage(first_models[0].get("file", "")) if first_models else key
        sessions.append({
            "key": key,
            "name": name,
            "runs": runs,
            "stamp": runs[-1].get("stamp", 0),
            "started": runs[0].get("stamp", 0),
            "actions": [(r["rec"].get("step") or {}).get("action", "")
                        for r in runs],
        })
    sessions.sort(key=lambda s: s["stamp"], reverse=True)
    return sessions


def versions_of(session: dict, exists=None) -> list:
    """The files a chat can carry on from, oldest first: the original and each
    edited copy — only those still on disk.

    [{"path", "label", "kind"}] with kind "original" or "edited"."""
    exists = exists or os.path.exists
    seen: dict[str, dict] = {}
    for item in session.get("runs", []):
        stamp = item.get("stamp", 0)
        for m in _models(item["rec"]):
            for field, kind in (("path", None), ("modified", "edited")):
                path = m.get(field) or ""
                if not path or not exists(path):
                    continue
                key = os.path.normcase(os.path.abspath(path))
                if key in seen:
                    continue
                base = os.path.basename(path)
                edited = kind == "edited" or bool(_MODIFIED.search(
                    os.path.splitext(base)[0]))
                seen[key] = {"path": os.path.abspath(path), "stamp": stamp,
                             "kind": "edited" if edited else "original",
                             "label": base}
    out = sorted(seen.values(), key=lambda v: (v["kind"] == "edited", v["stamp"]))
    return out


def _when(stamp: float) -> str:
    try:
        return time.strftime("%d %b %H:%M", time.localtime(stamp))
    except (OverflowError, OSError, ValueError):
        return ""


def _day(stamp: float) -> str:
    try:
        return time.strftime("%d %b %Y", time.localtime(stamp))
    except (OverflowError, OSError, ValueError):
        return ""


def _time(stamp: float) -> str:
    try:
        return time.strftime("%H:%M", time.localtime(stamp))
    except (OverflowError, OSError, ValueError):
        return ""


def chat_text(session: dict) -> str:
    """The whole chat as readable text: what was done, what was asked, what
    came back, what was built — in the order it happened."""
    blocks = []
    for item in session.get("runs", []):
        rec = item["rec"]
        info = rec.get("step") or {}
        action = (info.get("action") or "").capitalize() or "Run"
        models = _models(rec)
        on = models[0].get("file", "") if models else ""
        head = f"━━ {_when(item.get('stamp', 0))} · {action}" + (f" · {on}" if on else "")
        lines = [head]
        question = (info.get("question") or "").strip()
        if question:
            lines.append(f"YOU\n{question}")
        stem = os.path.splitext(on)[0]
        answers = (rec.get("responses") or {}).get(f"ask · {stem}") or []
        body = "\n\n".join(a for a in answers if a and a.strip())
        if body:
            lines.append(f"PRISM\n{body}")
        elif action == "Draft":
            lines.append("PRISM\nMeasured and drew the dimensioned sheet.")
        for m in models:
            if m.get("modified"):
                lines.append("BUILT\n" + os.path.basename(m["modified"]))
        blocks.append("\n\n".join(lines))
    return "\n\n\n".join(blocks)


_RULE = re.compile(r"^\s*[-–—_━─=]{3,}\s*$")
_TABLE_RULE = re.compile(r"^\s*\|[\s|:\-–—_━─=]+\|\s*$")


def normalize_markdown(text: str) -> str:
    """Make an AI answer render as Markdown. Models write pipe tables whose
    rule row is en-dashes or em-dashes, and divider lines of dashes; neither
    is Markdown, so tables showed as raw pipes. Rewrites those two shapes and
    puts a blank line before a table (Markdown needs one)."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    for i, line in enumerate(lines):
        if _TABLE_RULE.match(line):
            cols = max(line.count("|") - 1, 1)
            line = "|" + "---|" * cols
        elif _RULE.match(line):
            line = "---"
        starts = line.lstrip().startswith("|")
        prev = out[-1] if out else ""
        if starts and prev.strip() and not prev.lstrip().startswith("|"):
            out.append("")
        out.append(line)
    return "\n".join(out)


def _sheet_in(out_dir: str) -> str:
    try:
        for name in sorted(os.listdir(out_dir)):
            low = name.lower()
            if low.endswith(".png") and "drawing sheet" in low and "after" not in low:
                return os.path.join(out_dir, name)
    except OSError:
        pass
    return ""


def _styled_in(out_dir: str) -> list:
    """ChatGPT's styled copies of the sheet saved beside the model's files."""
    try:
        return [os.path.join(out_dir, n) for n in sorted(os.listdir(out_dir))
                if "ai drawing sheet" in n.lower()]
    except OSError:
        return []


def chat_turns(session: dict) -> list:
    """The chat as structured turns, oldest first — what the screen draws as
    cards: {"path", "when", "stamp", "action", "file", "question", "answer",
    "built": [paths], "sheet"}."""
    turns = []
    for item in session.get("runs", []):
        rec = item["rec"]
        info = rec.get("step") or {}
        models = _models(rec)
        first = models[0] if models else {}
        on = first.get("file", "")
        stem = os.path.splitext(on)[0]
        answers = (rec.get("responses") or {}).get(f"ask · {stem}") or []
        turns.append({
            "path": item.get("path", ""),
            "stamp": item.get("stamp", 0),
            "when": _when(item.get("stamp", 0)),
            "day": _day(item.get("stamp", 0)),
            "time": _time(item.get("stamp", 0)),
            "action": (info.get("action") or "").capitalize() or "Run",
            "file": on,
            "edited": bool(_MODIFIED.search(stem)),
            "question": (info.get("question") or "").strip(),
            "answer": "\n\n".join(a for a in answers if a and a.strip()),
            "built": [m["modified"] for m in models if m.get("modified")],
            "followups": list(info.get("followups") or []),
            "sheet": _sheet_in(first.get("out_dir", "")) if first else "",
            "styled": (_styled_in(first.get("out_dir", ""))
                       if first and (info.get("action") or "") == "draft" else []),
        })
    return turns


def live_turn(action: str, file: str, question: str, answer: str = "",
              built: list | None = None, followups: list | None = None) -> dict:
    """A turn for a run still in progress — shown in the chat before the run
    is saved, so what you just asked never waits for the end to appear."""
    now = time.time()
    return {"path": "", "stamp": now, "when": _when(now), "day": _day(now),
            "time": _time(now), "action": action.capitalize(), "file": file,
            "edited": bool(_MODIFIED.search(os.path.splitext(file)[0])),
            "question": question, "answer": answer, "built": list(built or []),
            "followups": list(followups or []), "sheet": "",
            "styled": []}
