"""Sample answers for the Media Library and for sending a file in a chat, in the shapes prism-wa's ops_media.py returns.

Reached only through demo_platform.handle (PRISM_WHATSAPP_DEMO=1, never in a frozen build). The files themselves are kept in memory:
two start in the library (a picture and a PDF), so the library, the picker and a chat's media bubbles have something to show.

STDLIB ONLY.
"""
from __future__ import annotations

import base64
import binascii
import struct
import threading
import zlib
from datetime import datetime, timedelta, timezone

from addons.whatsapp.license_client import PlatformError

MB = 1024 * 1024
UPLOAD_CAP = 16 * MB
STORAGE = 1024 * MB
KIND_MAX = {"image": 5 * MB, "video": 16 * MB, "audio": 16 * MB, "document": 16 * MB, "sticker": 500 * 1024}
MIME_KIND = {"image/jpeg": "image", "image/png": "image", "image/webp": "sticker", "video/mp4": "video", "video/3gpp": "video",
             "audio/aac": "audio", "audio/mp4": "audio", "audio/mpeg": "audio", "audio/amr": "audio", "audio/ogg": "audio",
             "application/pdf": "document", "text/plain": "document", "application/msword": "document",
             "application/vnd.ms-excel": "document", "application/vnd.ms-powerpoint": "document",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "document",
             "application/vnd.openxmlformats-officedocument.presentationml.presentation": "document"}
_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".mp4": "video/mp4", ".3gp": "video/3gpp",
        ".aac": "audio/aac", ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".amr": "audio/amr", ".ogg": "audio/ogg", ".pdf": "application/pdf",
        ".txt": "text/plain", ".doc": "application/msword", ".xls": "application/vnd.ms-excel", ".ppt": "application/vnd.ms-powerpoint",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}
_BYTES: dict = {}
_GUARD = threading.RLock()                   # the screens call the demo from several worker threads at once


def _png(w: int, h: int, top: tuple, bottom: tuple) -> bytes:
    """A small gradient picture, made without any imaging library."""
    rows = b"".join(b"\x00" + bytes(c for x in range(w) for c in (
        top[0] + (bottom[0] - top[0]) * y // h, top[1] + (bottom[1] - top[1]) * y // h, top[2] + (bottom[2] - top[2]) * y // h)) for y in range(h))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def _pdf() -> bytes:
    return (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lib(p: dict) -> dict:
    with _GUARD:
        return _lib_locked(p)


def _lib_locked(p: dict) -> dict:
    if "media" not in p:
        photo, brochure = _png(320, 200, (35, 90, 140), (180, 205, 225)), _pdf()
        site, drawing = _png(480, 300, (120, 98, 70), (214, 196, 160)), _pdf() + b"% drawing rev B\n"
        p["media"] = {"seq": 4, "assets": [
            # what customers sent: kept, shown in their chats, never listed in the library
            {"id": "m3", "kind": "document", "mime": "application/pdf", "filename": "enclosure-drawing-revB.pdf", "size": len(drawing),
             "source": "inbound", "created_at": _now()},
            {"id": "m4", "kind": "image", "mime": "image/png", "filename": "site-today.png", "size": len(site), "source": "inbound",
             "created_at": _now()},
            {"id": "m1", "kind": "image", "mime": "image/png", "filename": "site-photo.png", "size": len(photo), "source": "upload",
             "created_at": _now()},
            {"id": "m2", "kind": "document", "mime": "application/pdf", "filename": "company-brochure.pdf", "size": len(brochure),
             "source": "upload", "created_at": _now()}]}
        _BYTES.update({"m1": photo, "m2": brochure, "m3": drawing, "m4": site})
    return p["media"]


def seed_threads(p: dict, s: dict) -> None:
    """A customer's drawing in Asha's chat and a picture of the site in Ravi's, so the thread shows both kinds."""
    with _GUARD:
        lib = _lib(p)
        if lib.get("threads_seeded"):
            return
        lib["threads_seeded"] = True
        _seed_threads(lib, s)


def _seed_threads(lib: dict, s: dict) -> None:
    now = datetime.now(timezone.utc)
    iso = lambda delta: (now - delta).strftime("%Y-%m-%dT%H:%M:%SZ")                         # noqa: E731

    def carried(asset_id: str) -> dict:
        a = next(x for x in lib["assets"] if x["id"] == asset_id)
        return {"id": a["id"], "wa_id": "wa-" + a["id"], "mime_type": a["mime"], "kind": a["kind"], "filename": a["filename"], "size": a["size"],
                "ready": True}
    plan = (("c1", 5, "Asha Patel", "[document] Enclosure drawing, revision B", timedelta(minutes=8), "m3"),
            ("c2", 2, "Ravi Shah", "[image] The site as it stands today.", timedelta(hours=2, minutes=5), "m4"))
    for cid, at, sender, text, ago, asset_id in plan:
        thread = s["threads"].get(cid)
        if thread is None:
            continue
        thread.insert(min(at, len(thread)), {"direction": "in", "sender": sender, "text": text, "created_at": iso(ago), "status": "",
                                              "msg_type": carried(asset_id)["kind"], "media": carried(asset_id)})


def asset(p: dict, asset_id) -> dict:
    found = next((a for a in _lib(p)["assets"] if a["id"] == asset_id), None)
    if found is None:
        raise PlatformError("That file is not in this workspace.", "unknown_asset", {})
    return found


def _quota(p: dict) -> dict:
    rows = _lib(p)["assets"]
    return {"used": sum(a["size"] for a in rows), "count": len(rows), "limit": STORAGE}


def _kind_for(mime: str, filename: str) -> tuple:
    mime = (mime or "").split(";")[0].strip().lower()
    if mime not in MIME_KIND:
        dot = (filename or "").lower().rfind(".")
        guessed = _EXT.get((filename or "").lower()[dot:] if dot >= 0 else "", "")
        mime = guessed or mime
    if mime not in MIME_KIND:
        raise PlatformError("WhatsApp cannot send that kind of file. Use a JPG or PNG picture, an MP4 video, an MP3 / OGG / AAC voice file, "
                            "or a PDF, Word, Excel or PowerPoint document.", "unsupported_type", {})
    return MIME_KIND[mime], mime


def references(a: dict, p: dict, asset_id) -> list:
    out = []
    if any(c.get("asset_id") == asset_id for c in a["canned"]):
        out.append("a saved reply")
    if any((a["inbox_settings"].get(k) or {}).get("asset_id") == asset_id for k in ("welcome", "off_hours")):
        out.append("an auto-reply")
    if any((c.get("header_media") or {}).get("asset_id") == asset_id and c.get("status") in ("draft", "scheduled", "sending", "paused")
           for c in p.get("campaigns", [])):
        out.append("a campaign that has not finished")
    return out


def handle(route: str, d: dict, p: dict, s: dict):
    if not (route.startswith("media/") or route == "messages/send_media"):
        return None
    from addons.whatsapp import demo_automation
    a = demo_automation._auto(p)
    lib = _lib(p)
    seed_threads(p, s)

    if route == "media/upload":
        try:
            data = base64.b64decode(d.get("data") or "", validate=True)
        except (binascii.Error, ValueError):
            raise PlatformError("the file did not arrive intact (it is not valid base64)", "bad_request", {}) from None
        name = (d.get("filename") or "file").replace("\\", "/").split("/")[-1].strip()[:150] or "file"
        kind, mime = _kind_for(d.get("mime"), name)
        if not data:
            raise PlatformError("That file is empty.", "empty", {})
        limit = min(UPLOAD_CAP, KIND_MAX[kind])
        if len(data) > limit:
            raise PlatformError("That %s is %.1f MB; the most that can be sent is %d MB." % (kind, len(data) / MB, limit // MB), "too_big", {})
        twin = next((x for x in lib["assets"] if _BYTES.get(x["id"]) == data and x["kind"] == kind), None)
        if twin is not None:
            return {"asset": dict(twin), "quota": _quota(p)}
        if _quota(p)["used"] + len(data) > STORAGE:
            raise PlatformError("Your media storage is full. Delete files you no longer use.", "storage_full", {})
        lib["seq"] += 1
        new = {"id": "m%d" % lib["seq"], "kind": kind, "mime": mime, "filename": name, "size": len(data), "source": "upload", "created_at": _now()}
        _BYTES[new["id"]] = data
        lib["assets"].insert(0, new)
        return {"asset": dict(new), "quota": _quota(p)}

    if route == "media/list":
        rows = [x for x in lib["assets"] if x["source"] != "inbound"]
        if d.get("kind"):
            rows = [x for x in rows if x["kind"] == d["kind"]]
        term = (d.get("search") or "").strip().lower()
        if term:
            rows = [x for x in rows if term in x["filename"].lower()]
        lim, off = int(d.get("limit") or 60), int(d.get("offset") or 0)
        return {"assets": [dict(x) for x in rows[off:off + lim]], "total": len(rows), "quota": _quota(p)}

    if route == "media/get":
        found = asset(p, d.get("asset_id"))
        data = _BYTES.get(found["id"], b"")
        if len(data) > min(int(d.get("max_bytes") or 12 * MB), 12 * MB):
            return {"asset": dict(found), "data": None, "too_big": True}
        return {"asset": dict(found), "data": base64.b64encode(data).decode("ascii"), "too_big": False}

    if route == "media/delete":
        asset(p, d.get("asset_id"))
        used = references(a, p, d["asset_id"])
        if used:
            raise PlatformError("That file is still used by %s. Remove it from there first." % " and ".join(used), "in_use", {})
        lib["assets"] = [x for x in lib["assets"] if x["id"] != d["asset_id"]]
        _BYTES.pop(d["asset_id"], None)
        return {"deleted": True}

    if route == "media/usage":
        return {"quota": _quota(p)}

    # messages/send_media
    found = asset(p, d.get("asset_id"))
    from addons.whatsapp import demo_inbox
    c = next((x for x in s["conversations"] if x["id"] == d.get("conversation_id") or x["contact_id"] == d.get("contact_id")), None)
    if c is None:
        raise PlatformError("that chat is not in this workspace", "unknown_conversation", {})
    me = d.get("agent_id") or d.get("by_agent_id") or "a1"
    agent = next((x for x in a["agents"] if x["id"] == me), a["agents"][0])
    if not demo_inbox._row(c, p, s, a, me, False)["window_open"]:
        raise PlatformError("the 24-hour window is closed; send an approved template", "window_closed", {})
    ref = str(d.get("client_ref") or "")
    sent = a.setdefault("_sent_refs", {})
    if ref and ref in sent:
        return {"queued": True, "outbox_id": sent[ref]}
    caption = (d.get("caption") or "").strip()
    s["threads"][c["id"]].append({
        "direction": "out", "sender": agent["name"], "text": ("[%s] %s" % (found["kind"], caption)).strip(), "created_at": _now(), "status": "sent",
        "msg_type": found["kind"], "media": {"id": found["id"], "wa_id": None, "mime_type": found["mime"], "kind": found["kind"],
                                             "filename": found["filename"], "size": found["size"], "ready": True}})
    st = a["conv"].setdefault(c["id"], {"status": "active", "assignee_id": None})
    if st["status"] != "closed":
        st.update(status="intervened", assignee_id=me)
    key = ref or str(len(sent))
    sent[key] = "o%d" % (len(sent) + 1)
    return {"queued": True, "outbox_id": sent[key]}
