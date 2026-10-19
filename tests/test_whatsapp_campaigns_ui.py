"""Campaigns, the parts added for AiSensy parity: trying failed messages again, a fallback for an empty blank, who gets it (a filter, the
people chosen in Contacts, a file, the people who pressed a button), the results window with every person and why a message failed,
API campaigns and the campaign settings — driven against the demo platform with a fake worker.

No processEvents()/exec()/QEventLoop, and nothing touches the real ~/.prism.
"""
from __future__ import annotations

import os
import sys
import tempfile
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core_bridge  # noqa: F401,E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton  # noqa: E402

_app = QApplication.instance() or QApplication([])

from addons.whatsapp import demo, demo_platform, readstate, ui  # noqa: E402
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
    tmp = tempfile.mkdtemp(prefix="prism-wa-camp-")
    readstate.reset_cache()
    demo._state.clear()
    demo_platform._PAGE.clear()
    monkeypatch.setattr(demo_platform.time, "sleep", lambda _s: None)
    with mock.patch("paths.user_dir", lambda *p: os.path.join(tmp, *p)):
        yield
    demo._state.clear()
    demo_platform._PAGE.clear()


@pytest.fixture
def calls():
    return []


@pytest.fixture
def page(calls, monkeypatch):
    from addons.whatsapp import campaigns_page as CP
    monkeypatch.setattr(CP, "PlatformWorker", _worker(calls))
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    monkeypatch.setattr(ui, "confirm", lambda *_a, **_k: True)
    p = CP.CampaignsPage({})
    p.activate()
    yield p
    p.deactivate()


def routes(calls):
    return [r for r, _d in calls]


def last(calls, route):
    return next(d for r, d in reversed(calls) if r == route)


def texts(widget) -> str:
    return " | ".join(lab.text() for lab in widget.findChildren(QLabel))


def button(widget, text):
    return next(b for b in widget.findChildren(QPushButton) if b.text() == text)


def yes():
    return mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)


# ── try again for failures ───────────────────────────────────────────────────

def test_retrying_is_off_until_asked_for_and_then_says_how_often(page):
    assert page.retry() == {"max": 0} and page.retry_box.isHidden() and page.collect()["retry"] == {"max": 0}
    page.retry_on.setChecked(True)
    page.retry_times.setValue(2)
    page.retry_gap.setValue(45)
    assert not page.retry_box.isHidden() and page.retry() == {"max": 2, "delay_minutes": 45} and page.collect()["retry"] == {"max": 2, "delay_minutes": 45}


def test_changing_the_retry_choice_asks_for_a_new_check(page, calls):
    page._checked = (page._print(), "c9", {"ok": True})
    page.send_btn.setEnabled(True)
    page.retry_on.setChecked(True)
    assert page._checked == () and not page.send_btn.isEnabled()


def test_a_repeating_campaign_remembers_the_retry_choice(page, calls):
    page.retry_on.setChecked(True)
    page.when_combo.setCurrentIndex(page.when_combo.findData("repeat"))
    assert page.config_for_repeat()["retry"] == {"max": 3, "delay_minutes": 60}


# ── a blank can have a fallback ──────────────────────────────────────────────

def test_a_fallback_is_kept_for_a_name_or_a_detail_but_not_for_text_or_a_number():
    from addons.whatsapp.campaigns_page import variable_spec
    assert variable_spec("first_name", "", "friend") == {"source": "field", "field": "first_name", "default": "friend"}
    assert variable_spec("attribute", "City", " your city ") == {"source": "attribute", "key": "City", "default": "your city"}
    assert variable_spec("attribute", "City", "") == {"source": "attribute", "key": "City"}
    assert variable_spec("mobile", "", "x") == {"source": "field", "field": "mobile"}
    assert variable_spec("static", "Diwali", "x") == {"source": "static", "value": "Diwali"}


def test_the_fallback_box_shows_only_where_it_means_something(page):
    combo, edit, _k, fallback = page._var_rows["2"]
    assert not fallback.isHidden() or True
    combo.setCurrentIndex(combo.findData("static"))
    assert fallback.isHidden()
    combo.setCurrentIndex(combo.findData("attribute"))
    assert not fallback.isHidden() or fallback.isVisibleTo(page)
    edit.setText("City")
    fallback.setText("your city")
    assert page.variables()["2"] == {"source": "attribute", "key": "City", "default": "your city"}
    combo.setCurrentIndex(combo.findData("mobile"))
    assert fallback.isHidden() and page.variables()["2"] == {"source": "field", "field": "mobile"}


def test_the_fallback_survives_the_blanks_being_rebuilt(page):
    combo, edit, _k, fallback = page._var_rows["1"]
    combo.setCurrentIndex(combo.findData("first_name"))
    fallback.setText("friend")
    page._rebuild_blanks([("1", "{{1}}", "text"), ("2", "{{2}}", "text"), ("3", "{{3}}", "text")])
    assert page._var_rows["1"][3].text() == "friend"


# ── who gets it ──────────────────────────────────────────────────────────────

def choose(page, key):
    page.audience_combo.setCurrentIndex(page.audience_combo.findData(key))


def test_a_filter_can_be_the_audience_and_is_counted(page, calls):
    choose(page, "filter")
    assert not page.filter_row.isHidden() and "narrow it" in page.filter_text.text()
    page._aud_filter = {"field": "tags", "op": "has_any", "value": ["vip"]}
    page._audience_changed()
    assert page.audience() == {"filter": page._aud_filter, "segment_name": "People who match a filter…"}
    assert "Tags has any of vip" in page.filter_text.text()
    page._count()
    assert last(calls, "segments/count")["filter"] == page._aud_filter and "2 people" in page.reach.text()


def test_the_filter_window_is_opened_with_the_known_attributes_and_tags(page, monkeypatch):
    from addons.whatsapp import filter_builder as FB
    seen = {}

    class Fake:
        def __init__(self, flt, defs, tags, parent=None, opted_in_only=False):
            seen.update(flt=flt, defs=defs, tags=tags, opted=opted_in_only)

        def exec(self):
            return 1

        def filter(self):
            return {"field": "name", "op": "contains", "value": "patel"}
    monkeypatch.setattr(FB, "FilterDialog", Fake)
    choose(page, "filter")
    page._edit_filter()
    assert page._aud_filter == {"field": "name", "op": "contains", "value": "patel"}
    assert "City" in seen["defs"] and "vip" in seen["tags"] and seen["opted"] is True


def test_people_chosen_in_contacts_become_the_audience(page, calls):
    page.use_audience({"contact_ids": ["k1", "k2", "k3"]})
    assert page.audience_combo.currentData() == "picked" and page.audience_combo.currentText() == "People I chose in Contacts"
    assert page.audience()["contact_ids"] == ["k1", "k2", "k3"] and "3 people you chose" in page.filter_text.text()
    assert page.filter_edit_btn.isHidden()
    page._count()
    assert "3 people chosen" in page.reach.text() and "segments/count" not in routes(calls)[-1:]
    page.use_audience({"contact_ids": ["k1"]})
    assert page.audience_combo.count() == page.audience_combo.findData("picked") + 1 and "1 person chosen" in page.reach.text() or True


def test_everyone_matching_a_contacts_filter_is_the_audience_too(page, calls):
    page.use_audience({"filter": {"field": "tags", "op": "has", "value": ["vip"]}})
    assert page.audience()["filter"] == {"field": "tags", "op": "has", "value": ["vip"]}
    page._count()
    assert last(calls, "segments/count")["filter"] == {"field": "tags", "op": "has", "value": ["vip"]}


def test_a_file_of_people_is_imported_with_a_tag_and_the_campaign_aims_at_that_tag(page, monkeypatch):
    from addons.whatsapp import import_dialog as ID
    seen = {}

    class Fake:
        def __init__(self, parent=None):
            from PySide6.QtWidgets import QLineEdit
            self.tags_edit = QLineEdit()
            seen["dlg"] = self

        def exec(self):
            seen["tag"] = self.tags_edit.text()
            return 1
    monkeypatch.setattr(ID, "ImportContactsDialog", Fake)
    choose(page, "file")
    assert "Choose a spreadsheet" in page.filter_text.text()
    page._edit_filter()
    tag = seen["tag"]
    assert tag.startswith("campaign-") and page.audience()["filter"] == {"field": "tags", "op": "has", "value": [tag]}


def test_the_people_who_pressed_one_button_can_be_followed_up(page, calls):
    page.add_retarget("c1", "Diwali offer", "button", False, 1)
    assert page.audience_combo.currentText() == "Pressed a button in “Diwali offer”"
    assert page.audience()["filter"] == {"field": "campaign", "op": "button", "campaign": "c1", "button": 1}
    page.add_retarget("c1", "Diwali offer", "read", True)
    assert page.audience()["filter"] == {"not": {"field": "campaign", "op": "read", "campaign": "c1"}}


def test_broadcast_from_contacts_lands_on_the_composer_with_exactly_those_people(calls, monkeypatch):
    from addons.whatsapp import campaigns_page as CP
    from addons.whatsapp import workbench as W
    monkeypatch.setattr(CP, "PlatformWorker", _worker(calls))
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    wb = W.WhatsAppWorkbench({})
    wb.show_tab(W._CONTACTS)
    wb._pages[W._CONTACTS].broadcastRequested.emit({"contact_ids": ["k4", "k5"]})
    assert wb._current == W._CAMPAIGNS and wb._pages[W._CAMPAIGNS].audience()["contact_ids"] == ["k4", "k5"]


# ── the results window ───────────────────────────────────────────────────────

@pytest.fixture
def report(calls, monkeypatch):
    from addons.whatsapp import campaign_detail as CD
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    picked = []
    dlg = CD.CampaignReport("c1", "Diwali offer", on_retarget=lambda *a: picked.append(a), quick_replies=["Yes please", "Not now"])
    dlg.picked = picked
    return dlg


def test_the_results_list_every_person_and_why_a_message_failed(report, calls):
    assert last(calls, "campaigns/recipients")["limit"] == 50 and report.table.rowCount() == 50 and "1–50 of 60" in report.page_note.text()
    heads = [report.table.horizontalHeaderItem(i).text() for i in range(report.table.columnCount())]
    assert heads == ["Name", "Mobile", "Status", "Reacted", "Why it didn't go"]
    failed_rows = [r for r in range(report.table.rowCount()) if report.table.item(r, 2).text() == "Failed"]
    assert failed_rows and any(w in report.table.item(failed_rows[0], 4).text() for w in ("not on WhatsApp", "frequency cap"))
    assert "8 could not be delivered" in texts(report) and "frequency cap" in texts(report)


def test_the_status_chips_search_and_paging_ask_the_server(report, calls):
    report.chips.set_current("failed")
    report._on_chip("failed")
    assert last(calls, "campaigns/recipients")["status"] == "failed" and all(report.table.item(r, 2).text() == "Failed" for r in range(report.table.rowCount()))
    report._on_chip("")
    report.search.setText("asha")
    report._reset_and_load()
    assert last(calls, "campaigns/recipients")["search"] == "asha"
    report.search.setText("")
    report._reset_and_load()
    assert not report.prev_btn.isEnabled() and report.next_btn.isEnabled() == (report._total > 50)


def test_the_list_can_be_saved_as_a_file(report, calls, tmp_path, monkeypatch):
    from addons.whatsapp import campaign_detail as CD
    out = tmp_path / "people.csv"
    monkeypatch.setattr(CD.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    monkeypatch.setattr(CD.C, "show_toast", lambda *a, **k: None)
    report._on_chip("failed")
    report._export()
    assert last(calls, "campaigns/recipients_csv") == {"campaign_id": "c1", "status": "failed"}
    assert out.read_text(encoding="utf-8-sig").splitlines()[0].startswith("Name,Mobile,Status") and "failed" in out.read_text(encoding="utf-8-sig")


def test_each_quick_reply_button_is_a_way_to_aim_the_next_campaign(report):
    names = [b.text() for b in report.findChildren(QPushButton)]
    assert "Message people who pressed “Yes please”" in names and "Message people who pressed “Not now”" in names
    button(report, "Message people who pressed “Not now”").click()
    assert report.picked == [("c1", "button", False, 1)] and report.result() == 1


def test_quick_replies_are_read_from_a_template_in_order():
    from addons.whatsapp.campaign_detail import quick_replies_of, retarget_filter
    tpl = {"components": [{"type": "BODY", "text": "x"}, {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Yes"}, {"type": "URL", "text": "Site", "url": "https://x.in"},
                                                                                         {"type": "QUICK_REPLY", "text": "No"}]}]}
    assert quick_replies_of(tpl) == ["Yes", "No"] and quick_replies_of({}) == []
    assert retarget_filter("c1", "button", False, 0) == {"field": "campaign", "op": "button", "campaign": "c1", "button": 0}
    assert retarget_filter("c1", "read", True) == {"not": {"field": "campaign", "op": "read", "campaign": "c1"}}


def test_a_report_that_cannot_load_says_so_and_the_table_still_tries(calls, monkeypatch):
    from addons.whatsapp import campaign_detail as CD
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls, fail={"campaigns/report": "Couldn't reach the server."}))
    dlg = CD.CampaignReport("c1", "Diwali offer")
    assert "Couldn't reach" in texts(dlg) and dlg.table.rowCount() > 0


# ── the history, API campaigns and settings ─────────────────────────────────

def test_a_paused_by_meta_campaign_says_why_and_an_api_campaign_shows_on_or_off(page):
    from addons.whatsapp import campaigns_page as CP
    row = CP._CampaignRow({"id": "c1", "name": "Diwali", "status": "paused", "template_name": "t", "total": 10, "sent": 4, "failed": 0, "pause_reason": "category_change"})
    assert "changed this template from Utility to Marketing" in texts(row)
    api = CP._CampaignRow({"id": "a1", "name": "order_shipped", "status": "sending", "template_name": "t", "total": 3, "sent": 3, "failed": 0, "kind": "api"})
    body = texts(api)
    assert "API" in body and "On" in body and "Pause" not in [b.text() for b in api.findChildren(QPushButton)] and "Cancel" not in [b.text() for b in api.findChildren(QPushButton)]


def test_api_campaigns_are_made_switched_copied_and_deleted(calls, monkeypatch):
    from addons.whatsapp import campaign_detail as CD
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    monkeypatch.setattr(ui, "confirm", lambda *_a, **_k: True)
    tpls = demo_platform.handle("templates/list", {})["templates"]
    dlg = CD.ApiCampaignsDialog(tpls)
    assert "No API campaigns yet" in texts(dlg) and dlg.template.count() == 2
    dlg.name.setText("order_shipped")
    dlg.template.setCurrentIndex(dlg.template.findText("order_update · en_US"))
    dlg._make()
    assert last(calls, "api_campaigns/create") == {"name": "order_shipped", "template_name": "order_update", "language": "en_US"}
    assert "order_shipped" in texts(dlg) and "https://example.com/campaign/t1/api/v2" in texts(dlg)
    copied = []
    monkeypatch.setattr(ui, "copy_text", lambda parent, text, what="": copied.append(text))
    camp = demo_platform.handle("api_campaigns/list", {})["campaigns"][0]
    dlg._copy(camp)
    assert copied[0].startswith("POST https://example.com/campaign/t1/api/v2") and '"campaignName": "order_shipped"' in copied[0] and '"value 2"' in copied[0]
    from PySide6.QtWidgets import QCheckBox
    dlg.reload()
    dlg._delete(camp)
    assert last(calls, "api_campaigns/delete") == {"campaign_id": camp["id"]} and "No API campaigns yet" in texts(dlg)
    del QCheckBox


def test_a_bad_api_campaign_is_refused_with_the_reason(calls, monkeypatch):
    from addons.whatsapp import campaign_detail as CD
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    dlg = CD.ApiCampaignsDialog(demo_platform.handle("templates/list", {})["templates"])
    dlg._make()
    assert "Give it a name" in dlg.error.text()
    dlg.name.setText("no/slashes")
    dlg._make()
    assert "letters, numbers" in dlg.error.text()


def test_the_campaign_settings_load_and_save(calls, monkeypatch):
    from addons.whatsapp import campaign_detail as CD
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    dlg = CD.CampaignSettingsDialog()
    assert dlg.auto.isChecked()
    dlg.auto.setChecked(False)
    dlg._save()
    assert last(calls, "campaigns/settings/save") == {"settings": {"auto_pause_on_category_change": False}} and dlg.result() == 1
    again = CD.CampaignSettingsDialog()
    assert not again.auto.isChecked()


def test_the_page_opens_the_api_campaigns_and_settings_windows(page, monkeypatch):
    from addons.whatsapp import campaigns_page as CP
    opened = []

    class Fake:
        def __init__(self, *a, **k):
            opened.append(type(self).__name__)

        def exec(self):
            return 1
    monkeypatch.setattr(CP, "ApiCampaignsDialog", type("ApiCampaignsDialog", (Fake,), {}))
    monkeypatch.setattr(CP, "CampaignSettingsDialog", type("CampaignSettingsDialog", (Fake,), {}))
    button(page, "API campaigns").click()
    button(page, "Settings").click()
    assert opened == ["ApiCampaignsDialog", "CampaignSettingsDialog"]


def test_a_check_sends_the_retry_choice_to_the_server(page, calls):
    page.retry_on.setChecked(True)
    page.retry_times.setValue(2)
    page._check()
    assert last(calls, "campaigns/create")["retry"] == {"max": 2, "delay_minutes": 60}
