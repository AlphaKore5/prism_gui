"""The Media Library on screen: the library grid, the picker, the one-file field, files in a chat (shown, attached, sent, retried),
a saved reply or auto-reply that carries a file, and a template or campaign header chosen from the library.

Driven against the demo platform with a fake worker. No processEvents()/exec()/QEventLoop, and nothing touches the real ~/.prism.
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core_bridge  # noqa: F401,E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

_app = QApplication.instance() or QApplication([])

from addons.whatsapp import demo, demo_media, demo_platform, media_lib, notify, readstate, ui  # noqa: E402
from addons.whatsapp.license_client import PlatformError  # noqa: E402


class _Sig:
    def __init__(self):
        self._fns = []

    def connect(self, fn):
        self._fns.append(fn)

    def emit(self, *a):
        for fn in list(self._fns):
            fn(*a)


def _worker(calls, fail=None):
    class W:
        def __init__(self, route, data=None):
            self.route, self.data = route, dict(data or {})
            self.done, self.failed = _Sig(), _Sig()

        def start(self):
            calls.append((self.route, self.data))
            if fail and self.route in fail:
                self.failed.emit(fail[self.route], {})
                return
            try:
                reply = demo_platform.handle(self.route, self.data)
            except PlatformError as e:
                self.failed.emit(str(e), dict(e.detail, reason=e.reason))
            else:
                self.done.emit(reply)
    return W


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="prism-wa-media-")
    readstate.reset_cache()
    media_lib._CACHE.clear()
    demo._state.clear()
    demo_platform._PAGE.clear()
    demo_media._BYTES.clear()
    monkeypatch.setattr(demo_platform.time, "sleep", lambda _s: None)
    monkeypatch.setattr(ui, "confirm", lambda *_a, **_k: True)
    with mock.patch("paths.user_dir", lambda *p: os.path.join(tmp, *p)):
        yield
    media_lib._CACHE.clear()
    demo._state.clear()
    demo_platform._PAGE.clear()
    demo_media._BYTES.clear()


@pytest.fixture
def calls():
    return []


@pytest.fixture
def served(calls, monkeypatch):
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    return calls


def routes(calls):
    return [r for r, _d in calls]


def last(calls, route):
    return next(d for r, d in reversed(calls) if r == route)


def texts(widget) -> str:
    return " | ".join(lab.text() for lab in widget.findChildren(QLabel))


def button(widget, text):
    return next(b for b in widget.findChildren(QPushButton) if b.text() == text)


def names(view):
    return [view.grid.item(i).data(0x0100)["filename"] for i in range(view.grid.count())]


def png(w=40, h=30) -> bytes:
    return demo_media._png(w, h, (10, 20, 30), (200, 210, 220))


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


# ── the library grid ─────────────────────────────────────────────────────────

def test_the_library_lists_what_the_workspace_holds_and_how_much_room_is_used(served):
    v = media_lib.LibraryView(manage=True)
    v.reload()
    assert names(v) == ["site-photo.png", "company-brochure.pdf"]                      # what customers sent is not listed
    assert "used" in v.quota_label.text() and "of 1.0 GB" in v.quota_label.text()
    assert not v.empty.isVisible() or v.empty.text() == ""


def test_the_kind_chips_and_the_search_narrow_the_list_on_the_server(served, calls):
    v = media_lib.LibraryView(manage=True)
    v.reload()
    v.chips._pick("document")
    assert last(calls, "media/list")["kind"] == "document" and names(v) == ["company-brochure.pdf"]
    v.chips._pick("")
    v.search.setText("photo")
    v._later.stop()
    v.reload()
    assert last(calls, "media/list")["search"] == "photo" and names(v) == ["site-photo.png"]
    v.search.setText("zzz")
    v.reload()
    assert names(v) == [] and "No file matches" in v.empty.text()


def test_a_picture_in_the_grid_gets_its_own_thumbnail(served):
    v = media_lib.LibraryView(manage=True)
    v.reload()
    item = next(v.grid.item(i) for i in range(v.grid.count()) if v.grid.item(i).data(0x0100)["kind"] == "image")
    assert not item.icon().isNull() and v.grid.iconSize().width() == media_lib.THUMB


def test_uploading_files_adds_them_and_says_which_were_refused(served, calls, tmp_path, monkeypatch):
    v = media_lib.LibraryView(manage=True)
    v.reload()
    good = write(tmp_path, "plan.png", png())
    bad = write(tmp_path, "archive.zip", b"PK\x03\x04 not for whatsapp")
    monkeypatch.setattr(media_lib, "pick_paths", lambda *_a, **_k: [good, bad])
    v._upload()
    sent = [d for r, d in calls if r == "media/upload"]
    assert [d["filename"] for d in sent] == ["plan.png", "archive.zip"] and sent[0]["mime"] == "image/png" and sent[0]["_timeout"] >= 60
    assert base64.b64decode(sent[0]["data"]) == png()
    assert "plan.png" in names(v)
    assert "archive.zip" in v.note.text() and "cannot send that kind" in v.note.text()
    assert v.upload_btn.isEnabled()


def test_the_same_file_uploaded_again_is_the_one_already_held(served, tmp_path, monkeypatch):
    v = media_lib.LibraryView(manage=True)
    path = write(tmp_path, "plan.png", png())
    monkeypatch.setattr(media_lib, "pick_paths", lambda *_a, **_k: [path])
    v._upload()
    v._upload()
    assert names(v).count("plan.png") == 1


def test_a_file_over_the_limit_is_refused_before_it_travels(served, calls, tmp_path, monkeypatch):
    v = media_lib.LibraryView(manage=True)
    big = write(tmp_path, "huge.pdf", b"%PDF" + b"0" * (media_lib.UPLOAD_CAP + 10))
    monkeypatch.setattr(media_lib, "pick_paths", lambda *_a, **_k: [big])
    v._upload()
    assert "media/upload" not in routes(calls) and "over 16 MB" in v.note.text()


def test_a_picture_over_five_megabytes_is_refused_by_the_service_in_words(served, tmp_path, monkeypatch):
    v = media_lib.LibraryView(manage=True)
    big = write(tmp_path, "big.png", b"\x89PNG" + b"0" * (6 * media_lib.MB))
    monkeypatch.setattr(media_lib, "pick_paths", lambda *_a, **_k: [big])
    v._upload()
    assert "big.png" in v.note.text() and "5 MB" in v.note.text()


def test_deleting_a_file_asks_first_and_removes_it(served, calls):
    v = media_lib.LibraryView(manage=True)
    v.reload()
    v.grid.setCurrentRow(0)
    assert v.delete_btn.isEnabled() and v.save_btn.isEnabled()
    v._delete()
    assert last(calls, "media/delete") == {"asset_id": "m1"} and names(v) == ["company-brochure.pdf"]
    assert not v.delete_btn.isEnabled()


def test_a_file_a_saved_reply_still_uses_cannot_be_deleted(served, calls):
    demo_platform.handle("inbox/canned/save", {"shortcut": "brochure", "body": "", "asset_id": "m2"})
    v = media_lib.LibraryView(manage=True)
    v.reload()
    v.grid.setCurrentRow(1)
    v._delete()
    assert "still used by a saved reply" in v.note.text() and "company-brochure.pdf" in names(v)


def test_a_folder_of_nothing_says_what_the_library_is_for(served):
    demo_platform.handle("media/delete", {"asset_id": "m1"})
    demo_platform.handle("media/delete", {"asset_id": "m2"})
    v = media_lib.LibraryView(manage=True)
    v.reload()
    assert names(v) == [] and "Upload a picture, video, voice note or document" in v.empty.text()


# ── choosing a file ──────────────────────────────────────────────────────────

def test_the_picker_dialog_offers_only_the_kinds_asked_for(served):
    dlg = media_lib.MediaLibraryDialog(("document",))
    assert names(dlg.view) == ["company-brochure.pdf"]
    assert not dlg.view.chips.isVisible()                                          # one kind: nothing to filter
    assert not dlg.use.isEnabled()
    dlg.view.grid.setCurrentRow(0)
    assert dlg.use.isEnabled()


def test_using_a_file_in_the_picker_hands_it_back(served):
    dlg = media_lib.MediaLibraryDialog()
    dlg.view.grid.setCurrentRow(1)
    dlg._use()
    assert dlg.asset["filename"] == "company-brochure.pdf" and dlg.result() == 1


def test_the_one_file_field_shows_the_name_and_size_and_can_be_cleared(served):
    f = media_lib.AssetField(empty_text="No file")
    assert f.name.text() == "No file" and f.asset_id() is None and f.pick.text() == "Choose file" and not f.remove.isVisibleTo(f)
    f.set_asset_id("m2")
    assert f.asset_id() == "m2" and "company-brochure.pdf" in f.name.text() and f.pick.text() == "Change" and f.remove.isVisibleTo(f)
    seen = []
    f.changed.connect(lambda: seen.append(1))
    f.clear()
    assert f.asset_id() is None and f.name.text() == "No file" and seen == [1]


def test_a_saved_file_that_has_since_been_deleted_shows_as_none(served):
    f = media_lib.AssetField()
    f.set_asset_id("gone")
    assert f.asset_id() is None and f.name.text() == "No file"


def test_choosing_in_the_field_opens_the_library(served, monkeypatch):
    f = media_lib.AssetField(("image",))
    shown = []

    class Fake:
        asset = {"id": "m1", "kind": "image", "filename": "site-photo.png", "size": 2000}

        def __init__(self, kinds=None, title="", parent=None):
            shown.append(kinds)

        def exec(self):
            return 1
    monkeypatch.setattr(media_lib, "MediaLibraryDialog", Fake)
    f._choose()
    assert shown == [("image",)] and f.asset_id() == "m1" and "site-photo.png" in f.name.text()


def test_sizes_read_in_the_unit_a_person_thinks_in():
    assert [media_lib.size_text(n) for n in (0, 900, 2048, 3 * media_lib.MB, 1024 * media_lib.MB)] == ["0 B", "900 B", "2 KB", "3.0 MB", "1.0 GB"]
    assert media_lib.safe_name('..\\evil/na:me?.png') == "na_me_.png" and media_lib.safe_name("") == "file"


# ── a chat ───────────────────────────────────────────────────────────────────

@pytest.fixture
def inbox(served, monkeypatch):
    from addons.whatsapp import inbox as I
    monkeypatch.setattr(I.QTimer, "singleShot", lambda *a, **k: None)
    monkeypatch.setattr(notify, "announce", lambda *a, **k: 0)
    page = I.InboxPage({})
    page.resize(1500, 800)
    page.activate()
    yield page
    page.deactivate()


def pick(page, name):
    row = next(i for i in range(page.list.count()) if page.list.item(i).data(0x0100)["contact_name"] == name)
    page.list.setCurrentRow(row)


def test_a_customers_file_is_shown_in_the_thread_not_as_the_word_image(inbox):
    pick(inbox, "Ravi Shah")
    bubbles = [b for b in inbox.thread._bubbles if b.media_block is not None]
    assert len(bubbles) == 1
    b = bubbles[0]
    assert b.media_block.picture is not None and not b.media_block.picture.pixmap().isNull()
    assert b.body.text() == "The site as it stands today."                              # the placeholder "[image]" is not shown


def test_a_document_is_a_tile_that_opens_and_saves(inbox):
    pick(inbox, "Asha Patel")
    doc = next(b for b in inbox.thread._bubbles if b.media_block is not None)
    assert any("enclosure-drawing-revB.pdf" in w.toolTip() for w in doc.media_block.findChildren(QLabel)) and "Open" in [x.text() for x in doc.media_block.findChildren(QPushButton)] and "Save a copy" in [x.text() for x in doc.media_block.findChildren(QPushButton)]
    assert not doc.body.isVisibleTo(doc) or doc.body.text() != "[document]"


def test_a_file_still_being_fetched_says_so(inbox):
    from addons.whatsapp.thread import Bubble
    b = Bubble({"direction": "in", "text": "[image]", "created_at": "2026-10-18T10:00:00Z", "media": {"id": None, "wa_id": "w1", "kind": "image", "ready": False}},
               tail=True)
    assert b.media_block is not None and "Fetching the file" in texts(b.media_block) and not b.body.isVisibleTo(b)


def test_opening_a_picture_shows_it_large(inbox, monkeypatch):
    from addons.whatsapp import thread as T
    pick(inbox, "Ravi Shah")
    block = next(b for b in inbox.thread._bubbles if b.media_block is not None).media_block
    shown = []
    monkeypatch.setattr(T.ImageViewer, "exec", lambda self: shown.append(self.windowTitle()) or 0)
    block._open_picture()
    assert shown == ["site-today.png"]


def test_the_paperclip_attaches_a_library_file_and_the_words_become_its_caption(inbox, monkeypatch):
    pick(inbox, "Asha Patel")
    c = inbox.composer
    assert c.attach_btn.isEnabled() and not c.chip.isVisibleTo(c) and not c.send_btn.isEnabled()

    class Fake:
        asset = {"id": "m2", "kind": "document", "filename": "company-brochure.pdf", "size": 300, "mime": "application/pdf"}

        def __init__(self, *a, **k):
            pass

        def exec(self):
            return 1
    import addons.whatsapp.media_lib as ML
    monkeypatch.setattr(ML, "MediaLibraryDialog", Fake)
    inbox._attach()
    assert c.chip.isVisibleTo(c) and "company-brochure.pdf" in c.chip_name.toolTip() and c.send_btn.isEnabled()      # a file alone is enough to send
    assert "caption" in c.edit.placeholderText().lower()
    c.clear_attachment()
    assert not c.chip.isVisibleTo(c) and not c.send_btn.isEnabled()


def test_sending_a_file_goes_out_with_its_caption_and_settles_to_sent(inbox, calls):
    pick(inbox, "Asha Patel")
    asset = {"id": "m2", "kind": "document", "filename": "company-brochure.pdf", "size": 300, "mime": "application/pdf"}
    inbox.composer.set_attachment(asset)
    inbox.composer.edit.setPlainText("Our brochure")
    inbox.composer._submit()
    sent = last(calls, "messages/send_media")
    assert sent["asset_id"] == "m2" and sent["caption"] == "Our brochure" and sent["conversation_id"] == "c1" and sent["client_ref"]
    bubble = inbox.thread._bubbles[-1]
    assert bubble.msg["status"] == "sent" and bubble.media_block is not None and bubble.body.text() == "Our brochure"
    assert inbox.composer.attachment() is None and inbox.composer.edit.toPlainText() == ""
    inbox._load_thread("c1")                                                           # the server's thread shows the same file
    assert any(b.media_block is not None and b.msg["media"]["id"] == "m2" for b in inbox.thread._bubbles)


def test_a_file_that_fails_to_send_can_be_retried_with_the_same_reference(inbox, calls, monkeypatch):
    pick(inbox, "Asha Patel")
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls, fail={"messages/send_media": "WhatsApp is down"}))
    inbox._send_media({"id": "m1", "kind": "image", "filename": "site-photo.png", "size": 10}, "")
    bubble = inbox.thread._bubbles[-1]
    ref = bubble.msg["client_ref"]
    assert bubble.msg["status"] == "failed" and "WhatsApp is down" in inbox.banner.text()
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    inbox.thread._on_retry(bubble)                                                      # a failed FILE retries as the file, not as its words
    again = [d for r, d in calls if r == "messages/send_media"][-1]
    assert again["asset_id"] == "m1" and again["client_ref"] == ref and bubble.msg["status"] == "sent"
    assert "messages/send_text" not in routes(calls)


def test_a_saved_reply_with_a_file_attaches_it_and_puts_its_words_in_the_box(inbox, calls):
    pick(inbox, "Asha Patel")
    demo_platform.handle("inbox/canned/save", {"shortcut": "catalogue", "body": "Hi {{first_name}}, our catalogue", "asset_id": "m2"})
    inbox.quick.load()
    pick_one = next(c for c in inbox.quick.canned if c["shortcut"] == "catalogue")
    assert pick_one["asset_name"] == "company-brochure.pdf"
    inbox.quick.contact_id = "k1"
    inbox.quick._pick(pick_one)
    assert inbox.composer.attachment()["id"] == "m2" and inbox.composer.edit.toPlainText() == "Hi Asha, our catalogue"


# ── settings that carry a file ───────────────────────────────────────────────

def test_a_quick_reply_can_carry_a_file_and_be_only_that(served, calls):
    from addons.whatsapp.settings_team import QuickRepliesSection
    s = QuickRepliesSection()
    s.activate()
    s.shortcut.setText("brochure")
    s.asset.set_asset_id("m2")
    s._save()
    assert last(calls, "inbox/canned/save") == {"shortcut": "brochure", "body": "", "asset_id": "m2"}
    assert "File: company-brochure.pdf" in texts(s) and s.asset.asset_id() is None and s.shortcut.text() == ""
    s._edit(next(c for c in demo_platform.handle("inbox/canned/list", {})["canned"] if c["shortcut"] == "brochure"))
    assert s.asset.asset_id() == "m2"


def test_a_quick_reply_with_neither_words_nor_file_is_refused(served):
    from addons.whatsapp.settings_team import QuickRepliesSection
    s = QuickRepliesSection()
    s.activate()
    s.shortcut.setText("empty")
    s._save()
    assert s.shortcut.text() == "empty"                                                  # nothing was saved, so nothing was cleared


def test_the_welcome_message_can_be_a_picture_with_words_under_it(served, calls):
    from addons.whatsapp.settings_team import TeamSection
    t = TeamSection()
    t.activate()
    t.welcome.switch.setChecked(True)
    t.welcome.text.setPlainText("Welcome to Patel Constructions")
    t.welcome.asset.set_asset_id("m1")
    t._save_rules()
    saved = last(calls, "inbox/settings/save")["settings"]["welcome"]
    assert saved["asset_id"] == "m1" and saved["template"] is None and saved["text"] == "Welcome to Patel Constructions" and saved["enabled"]
    t2 = TeamSection()
    t2.activate()
    assert t2.welcome.asset.asset_id() == "m1" and "site-photo.png" in t2.welcome.asset.name.text()


def test_an_auto_reply_can_be_an_approved_template_with_its_blanks_filled(served, calls):
    from addons.whatsapp.settings_team import TeamSection
    t = TeamSection()
    t.activate()
    t.off.mode.setCurrentIndex(t.off.mode.findData("template"))
    names_ = [t.off.picker.itemText(i) for i in range(t.off.picker.count())]
    assert names_ and all("PENDING" not in n and "REJECTED" not in n for n in names_)    # only approved templates are offered
    t.off.picker.setCurrentIndex(t.off.picker.findText("diwali_offer · en_US"))
    assert len(t.off._edits) == 2
    t.off._edits[0].setText("there")
    t.off._edits[1].setText("fabrication")
    t.off.switch.setChecked(True)
    t._save_rules()
    saved = last(calls, "inbox/settings/save")["settings"]["off_hours"]
    assert saved["template"] == {"name": "diwali_offer", "language": "en_US", "body": ["there", "fabrication"]} and saved["asset_id"] is None
    t2 = TeamSection()
    t2.activate()
    assert t2.off.mode.currentData() == "template" and t2.off.picker.currentData()["name"] == "diwali_offer" and t2.off._edits[0].text() == "there"


def test_an_auto_reply_with_nothing_to_send_is_refused_in_words(served):
    from addons.whatsapp.settings_team import TeamSection
    t = TeamSection()
    t.activate()
    t.welcome.switch.setChecked(True)
    t.welcome.text.setPlainText("   ")
    t._save_rules()
    assert "a file or a template" in t.rules_note.text()


def test_the_media_library_is_a_settings_section(served, calls):
    from addons.whatsapp import settings as S
    page = S.SettingsPage({})
    page.show_section("media")
    assert "media/list" in routes(calls) and names(page._sections["media"].view) == ["site-photo.png", "company-brochure.pdf"]


# ── headers: a template, a campaign ──────────────────────────────────────────

def test_a_template_with_a_picture_header_takes_it_from_the_library(served, calls):
    from addons.whatsapp.send_template_dialog import SendTemplateDialog
    dlg = SendTemplateDialog({"id": "k1", "name": "Asha"})
    tpl = {"id": "t9", "name": "offer_pic", "language": "en_US", "status": "APPROVED",
           "components": [{"type": "HEADER", "format": "IMAGE"}, {"type": "BODY", "text": "Hello {{1}}, see the picture.", "example": None}]}
    dlg._templates = [tpl]
    dlg.picker.clear()
    dlg.picker.addItem("offer_pic", tpl)
    dlg._build()
    assert dlg._header_file is not None and dlg._header_file.kinds == ("image",)
    dlg._header_file.set_asset_id("m1")
    dlg._edits[("body", 1)].setText("Asha")
    p = dlg.payload()
    assert p["header_asset_id"] == "m1" and p["body"] == ["Asha"]
    dlg._send()
    assert last(calls, "messages/send_template")["header_asset_id"] == "m1"


def test_a_campaign_header_is_a_library_file_or_a_web_address(served, calls):
    from addons.whatsapp import campaigns_page as CP
    with mock.patch.object(CP, "PlatformWorker", _worker(calls)):
        page = CP.CampaignsPage({})
        page.activate()
        page._templates.append({"name": "promo", "language": "en_US", "status": "APPROVED", "components": [
            {"type": "HEADER", "format": "IMAGE"}, {"type": "BODY", "text": "Our new range is in the shop today, come and see."}]})
        page.template_combo.addItem("promo", "promo")
        page.template_combo.setCurrentIndex(page.template_combo.findData("promo"))
        _c, edit, kind, picker = page._var_rows["header"]
        assert kind == "link" and picker.kinds == ("image",)                           # only pictures for a picture header
        edit.setText("https://x.in/a.jpg")
        assert page.variables() == {"header": {"link": "https://x.in/a.jpg"}}
        picker.set_asset_id("m1")
        assert page.variables() == {"header": {"asset_id": "m1"}}                       # a library file wins over an address
        picker.clear()
        assert page.variables() == {"header": {"link": "https://x.in/a.jpg"}}
        page.deactivate()


# ── the demo behaves like the service ────────────────────────────────────────

def test_the_demo_library_refuses_what_the_service_refuses(served):
    def up(name, mime, data):
        return demo_platform.handle("media/upload", {"filename": name, "mime": mime, "data": base64.b64encode(data).decode()})
    with pytest.raises(PlatformError) as e:
        up("a.zip", "application/zip", b"zz")
    assert e.value.reason == "unsupported_type"
    with pytest.raises(PlatformError) as e:
        up("big.png", "image/png", b"x" * (6 * media_lib.MB))
    assert e.value.reason == "too_big"
    with pytest.raises(PlatformError) as e:
        up("e.png", "image/png", b"")
    assert e.value.reason == "empty"
    one = up("a.png", "image/png", png())["asset"]
    assert up("renamed.png", "image/png", png())["asset"]["id"] == one["id"]            # the same bytes are one file
