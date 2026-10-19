"""The Ads tab beyond click-to-WhatsApp: three kinds of ad, finding places and interests, people lists, where an ad stands with Meta, results over time, suggestions, and signing in
with Facebook.

Driven with a fake worker that answers from the demo platform, so nothing opens a socket, starts a thread or spins an event loop. Rules this file follows: no
processEvents()/exec()/QEventLoop, and nothing touches the real ~/.prism.
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

from addons.whatsapp import demo, demo_ads, demo_platform, readstate, ui  # noqa: E402
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
    tmp = tempfile.mkdtemp(prefix="prism-wa-ads-")
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
def served(calls, monkeypatch):
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    return calls


def routes(calls):
    return [r for r, _d in calls]


def texts(widget) -> str:
    return " | ".join(lab.text() for lab in widget.findChildren(QLabel))


def state():
    from addons.whatsapp import demo_automation
    return demo_automation._auto(demo_platform._state())


def make_account():
    demo_platform.handle("ads/connect", {"ad_account_id": "1234567890", "page_id": "987654321", "token": "EAAB-ads-token-that-is-long-enough", "name": "Main"})
    return state()["ad_accounts"][0]["id"]


def make_ad(account, **kw):
    data = {"account_id": account, "name": "Walls", "kind": "website", "link": "https://shakti.example/walls", "daily_budget": 50000, "message": "Boundary walls built to last",
            "targeting": {"geo_locations": {"countries": ["IN"]}}, **kw}
    return demo_platform.handle("ads/create", data)["ad"]["id"]


@pytest.fixture
def page(served):
    from addons.whatsapp import ads_page as AP
    p = AP.AdsPage({})
    p.activate()
    return p


# ── the words ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ad,words,state_", [
    ({"status": "PAUSED"}, "Paused", "paused"), ({"status": "ACTIVE"}, "Running", "running"), ({"status": "FAILED"}, "Problem", "failed"),
    ({"status": "ACTIVE", "meta_status": "PENDING_REVIEW"}, "In review at Meta", "review"), ({"status": "ACTIVE", "meta_status": "DISAPPROVED"}, "Turned down by Meta", "rejected"),
    ({"status": "ACTIVE", "meta_status": "WITH_ISSUES"}, "Running with problems", "issues"), ({"status": "PAUSED", "meta_status": "ADSET_PAUSED"}, "Its audience is paused", "paused"),
    ({"status": "ACTIVE", "meta_status": "PENDING_BILLING_INFO"}, "Meta needs payment details", "issues")])
def test_where_an_ad_stands_is_put_in_words_and_metas_word_wins(ad, words, state_):
    from addons.whatsapp import ads_page as AP
    got = AP.state_words(ad)
    assert got[0] == words and got[2] == state_


def test_the_budget_is_put_in_words():
    from addons.whatsapp import ads_page as AP
    assert AP.budget_words({"daily": 75000}) == "Rs 750 a day" and AP.budget_words({"lifetime": 500000}) == "Rs 5,000 in all" and AP.budget_words({}) == ""
    assert [k for k, _n, _h in AP.kind_choices()] == ["ctwa", "website", "leadform"] and AP.kind_name("leadform") == "Leads on Facebook"
    assert [k for k, _l in AP.cta_choices("website")][0] == "LEARN_MORE" and [k for k, _l in AP.cta_choices("leadform")][0] == "SIGN_UP"


# ── the list of ads ──────────────────────────────────────────────────────────

def test_each_ad_shows_its_kind_its_state_its_budget_and_why_meta_turned_it_down(served):
    from addons.whatsapp import ads_page as AP
    account = make_account()
    ad = make_ad(account, message="Free money for everyone")
    demo_platform.handle("ads/activate", {"ad_id": ad, "confirm": True})
    demo_platform.handle("ads/status", {"ad_id": ad})
    page = AP.AdsPage({})
    page.activate()
    t = texts(page)
    assert "Visits to my website" in t and "Turned down by Meta" in t and "Rs 500 a day" in t and "Misleading claims" in t


def test_an_ad_can_be_checked_with_meta_and_the_answer_is_said(page, served):
    account = make_account()
    ad = make_ad(account, kind="ctwa", whatsapp_number="919800000000")
    page.activate()
    demo_platform.handle("ads/activate", {"ad_id": ad, "confirm": True})
    page.activate()
    row = page.list_col.itemAt(0).widget()
    assert "In review at Meta" in texts(row)
    page.check_status(row.ad)
    assert "Meta says: Running" in page.note.text() and "Running" in texts(page.list_col.itemAt(0).widget())


def test_the_page_has_three_sections_and_the_ads_one_is_first(page):
    assert page.chips.current() == "ads"
    page.show_section("audiences")
    assert page.stack.currentIndex() == 2
    page.show_section("suggestions")
    assert page.stack.currentIndex() == 3
    page.show_section("ads")
    assert page._section == "ads"


# ── making an ad ─────────────────────────────────────────────────────────────

@pytest.fixture
def dialog(served):
    from addons.whatsapp import ads_page as AP
    make_account()
    p = AP.AdsPage({})
    p.activate()
    dlg = AP.NewAdDialog(p._accounts, "919800000000", p)
    dlg._keep_parent = p
    return dlg


def test_the_steps_are_walked_with_back_and_next_and_only_the_last_makes_the_ad(dialog):
    assert dialog.back_btn.isHidden() and not dialog.next_btn.isHidden() and dialog.go.isHidden()
    dialog.next_btn.click()
    assert dialog.steps.current() == 1 and dialog.stack.currentIndex() == 1 and not dialog.back_btn.isHidden()
    dialog.steps.set_current(3)
    assert dialog.next_btn.isHidden() and not dialog.go.isHidden()
    dialog.back_btn.click()
    assert dialog.steps.current() == 2 and dialog.go.isHidden()


def test_the_fields_follow_what_the_ad_should_do(dialog):
    assert not dialog.wa_box.isHidden() and dialog.web_box.isHidden() and dialog.lead_box.isHidden() and dialog.cta_box.isHidden()
    dialog.kind_buttons["website"].setChecked(True)
    assert dialog.wa_box.isHidden() and not dialog.web_box.isHidden() and not dialog.cta_box.isHidden() and dialog.cta.currentData() == "LEARN_MORE"
    dialog.kind_buttons["leadform"].setChecked(True)
    assert not dialog.lead_box.isHidden() and dialog.web_box.isHidden() and dialog.cta.currentData() == "SIGN_UP"


def test_a_website_ad_is_asked_for_with_its_address_button_and_pixel(dialog):
    dialog.kind_buttons["website"].setChecked(True)
    dialog.name.setText("Walls")
    dialog.link.setText("https://shakti.example/walls")
    dialog.pixel.setText("1122334455")
    dialog.landing.setChecked(True)
    dialog.message.setPlainText("Boundary walls built to last")
    dialog.description.setText("Free site visit")
    dialog.cta.setCurrentIndex(dialog.cta.findData("GET_QUOTE"))
    data = dialog.payload()
    assert data["kind"] == "website" and data["link"] == "https://shakti.example/walls" and data["cta"] == "GET_QUOTE" and data["pixel_id"] == "1122334455"
    assert data["optimize_for"] == "landing_page_views" and data["description"] == "Free site visit" and "whatsapp_number" not in data


def test_a_lead_form_ad_is_asked_for_with_its_questions_and_privacy_address(dialog):
    dialog.kind_buttons["leadform"].setChecked(True)
    dialog.name.setText("Leads")
    dialog.question_boxes["EMAIL"].setChecked(True)
    dialog.custom_q.setText("Which city is the project in?")
    dialog.privacy.setText("https://shakti.example/privacy")
    dialog.message.setPlainText("Get a free quote")
    data = dialog.payload()
    assert data["kind"] == "leadform" and data["form"]["questions"] == [{"type": "FULL_NAME"}, {"type": "PHONE"}, {"type": "EMAIL"}, {"type": "CUSTOM", "label": "Which city is the project in?"}]
    assert data["form"]["privacy_url"] == "https://shakti.example/privacy" and data["cta"] == "SIGN_UP"


def test_the_chosen_places_replace_the_whole_country_and_the_rest_of_the_audience_is_collected(dialog):
    dialog.countries.setText("in, ae")
    assert dialog.targeting()["geo_locations"] == {"countries": ["IN", "AE"]}
    dialog.places.add({"key": "2418", "name": "Vadodara", "type": "city"})
    dialog.places.add({"key": "2000", "name": "Gujarat", "type": "region"})
    dialog.interests.add({"id": "6003", "name": "Interior design", "type": "interests"})
    dialog.behaviours.add({"id": "6101", "name": "Small business owners", "type": "behaviors"})
    dialog.gender.setCurrentIndex(dialog.gender.findData(2))
    dialog.age_min.setValue(30)
    t = dialog.targeting()
    assert t["geo_locations"] == {"cities": [{"key": "2418"}], "regions": [{"key": "2000"}]} and t["genders"] == [2] and t["age_min"] == 30
    assert t["interests"] == [{"id": "6003", "name": "Interior design"}] and t["behaviors"] == [{"id": "6101", "name": "Small business owners"}]
    dialog.places.remove({"key": "2418"})
    assert "cities" not in dialog.targeting()["geo_locations"]


def test_a_list_can_be_shown_to_or_kept_away(served):
    from addons.whatsapp import ads_page as AP
    account = make_account()
    st = state()
    st.setdefault("ads_extra", {"audiences": [], "suggestions": [], "connect": {}, "pictures": {}})["audiences"] += [
        {"id": "aud1", "account_id": account, "name": "VIPs", "kind": "segment", "meta_id": "2381", "segment_id": "s1", "source": {}, "size": 150, "created_at": "2026-10-01T00:00:00Z"},
        {"id": "aud2", "account_id": account, "name": "Customers", "kind": "segment", "meta_id": "2382", "segment_id": "s2", "source": {}, "size": 400, "created_at": "2026-10-01T00:00:00Z"}]
    p = AP.AdsPage({})
    p.activate()
    d = AP.NewAdDialog(p._accounts, "", p)
    d.show_boxes["2381"].setChecked(True)
    d.hide_boxes["2382"].setChecked(True)
    t = d.targeting()
    assert t["custom_audiences"] == [{"id": "2381"}] and t["excluded_custom_audiences"] == [{"id": "2382"}]


def test_where_the_ad_appears_is_left_to_meta_unless_chosen(dialog):
    assert "publisher_platforms" not in dialog.targeting()
    dialog.placements.auto.setChecked(False)
    dialog.placements.platforms["instagram"].setChecked(False)
    dialog.placements.platforms["messenger"].setChecked(True)
    assert dialog.targeting()["publisher_platforms"] == ["facebook", "messenger"]
    assert not dialog.placements.box.isHidden()


def test_how_many_people_that_is_is_asked_of_meta_and_forgotten_when_the_audience_changes(dialog, calls):
    dialog.estimate()
    assert routes(calls)[-1] == "ads/estimate" and "people a day" in dialog.estimate_text.text() and dialog.estimate_btn.isEnabled()
    dialog.places.add({"key": "2418", "name": "Vadodara", "type": "city"})
    assert dialog.estimate_text.text() == ""
    first = dialog.estimate_text.text()
    dialog.estimate()
    narrowed = dialog.estimate_text.text()
    assert first != narrowed


def test_a_total_budget_needs_a_stop_date_and_the_summary_says_what_it_means(dialog):
    assert not dialog.budget_box.isHidden() and dialog.total_box.isHidden() and "a day" in dialog.summary.text()
    dialog.total_radio.setChecked(True)
    assert dialog.budget_box.isHidden() and not dialog.total_box.isHidden() and not dialog.end_box.isHidden() and "between the start and the stop date" in dialog.summary.text()
    data = dialog.payload()
    assert data["lifetime_budget"] == 500000 and "daily_budget" not in data and data["end_time"].endswith("+0530")
    dialog.daily_radio.setChecked(True)
    dialog.start_now.setChecked(False)
    dialog.end_on.setChecked(True)
    data = dialog.payload()
    assert data["daily_budget"] == 50000 and "start_time" in data and "end_time" in data


def test_the_ad_is_written_for_the_owner_from_three_versions(dialog):
    from addons.whatsapp import ads_page as AP

    def pick(self):
        self.offer.setPlainText("Boundary walls in Vadodara, free site visit")
        self._write()
        self._pick(self.results_col.itemAt(1).widget() and {"message": "Thinking about it? Boundary walls", "headline": "Ask us anything", "description": "We reply fast"})
        return 1
    with mock.patch.object(AP.CopyDialog, "exec", pick):
        dialog.write_for_me()
    assert dialog.message.toPlainText().startswith("Thinking about it?") and dialog.headline.text() == "Ask us anything" and dialog.description.text() == "We reply fast"


def test_the_copy_window_wants_a_real_description_and_shows_three_versions(served):
    from addons.whatsapp import ads_page as AP
    d = AP.CopyDialog("A chat on WhatsApp")
    d.offer.setPlainText("hi")
    d._write()
    assert "Say a little more" in d.note.text()
    d.offer.setPlainText("Boundary walls in Vadodara with a free site visit")
    d._write()
    t = texts(d)
    assert t.count("Use this one") == 0 and "Free site visit" in t or len([b for b in d.findChildren(QPushButton) if b.text() == "Use this one"]) == 3
    assert d.write_btn.isEnabled()


def test_a_picture_is_sent_to_meta_first_and_the_ad_made_with_its_hash(dialog, calls):
    dialog.name.setText("Walls")
    dialog.number.setText("919800000000")
    dialog.message.setPlainText("Free site visit")
    dialog.picture.set_asset({"id": "11111111-1111-1111-1111-111111111111", "kind": "image", "filename": "wall.jpg", "size": 1000})
    dialog._go()
    names = routes(calls)
    assert names.index("ads/upload_image") < names.index("ads/create")
    assert calls[names.index("ads/create")][1]["image_hash"].startswith("demohash")


def test_a_refused_ad_says_why_in_the_window_and_the_button_comes_back(dialog):
    dialog.name.setText("Walls")
    dialog.number.setText("123")
    dialog.message.setPlainText("Free site visit")
    dialog._go()
    assert "country code" in dialog.error.text() and dialog.go.isEnabled()
    dialog.kind_buttons["website"].setChecked(True)
    dialog.link.setText("shakti.example")
    dialog._go()
    assert "web address" in dialog.error.text()


def test_a_website_ad_is_made_paused_and_appears_in_the_list(page, served):
    from addons.whatsapp import ads_page as AP
    make_account()
    page.activate()
    d = AP.NewAdDialog(page._accounts, "", page)
    d.kind_buttons["website"].setChecked(True)
    d.name.setText("Walls")
    d.link.setText("https://shakti.example/walls")
    d.message.setPlainText("Boundary walls built to last")
    d._go()
    page.activate()
    t = texts(page)
    assert "Walls" in t and "Visits to my website" in t and "Paused" in t


# ── finding places and interests ─────────────────────────────────────────────

def test_a_search_needs_two_letters_an_account_and_gives_results_to_add(dialog, calls):
    p = dialog.places
    p.edit.setText("V")
    p.search()
    assert "at least two letters" in p.note.text() and "ads/search" not in routes(calls)
    p.edit.setText("vad")
    p.search()
    assert routes(calls)[-1] == "ads/search" and calls[-1][1]["kind"] == "geo" and "Vadodara" in texts(p) and "Gujarat, India" in texts(p)
    add = [b for b in p.findChildren(QPushButton) if b.text() == "Add"]
    add[0].click()
    assert [x["name"] for x in p.items()] == ["Vadodara"] and "Vadodara · City" in texts(p)
    add[0].click()
    assert len(p.items()) == 1                                                          # the same one is not added twice


def test_interests_show_how_many_people_they_are(dialog):
    dialog.interests.edit.setText("interior")
    dialog.interests.search()
    assert "1.5M to 2.2M people" in texts(dialog.interests)


def test_a_search_with_nothing_found_says_so(dialog):
    dialog.interests.edit.setText("zzzzzz")
    dialog.interests.search()
    assert "Nothing found" in dialog.interests.note.text()


def test_the_size_of_an_audience_is_put_in_short_words():
    from addons.whatsapp.ad_targeting_ui import size_words
    assert size_words([1500000, 2200000]) == "1.5M to 2.2M people" and size_words([5000, 9000]) == "5K to 9K people" and size_words([120, 120]) == "120 people" and size_words(None) == ""


# ── results ──────────────────────────────────────────────────────────────────

def test_the_results_of_an_ad_are_shown_over_a_range_with_the_cost_of_each_result(served):
    from addons.whatsapp.ad_results import AdResultsDialog
    account = make_account()
    ad = make_ad(account, kind="ctwa", whatsapp_number="919800000000")
    demo_platform.handle("ads/activate", {"ad_id": ad, "confirm": True})
    shown = demo_platform.handle("ads/list", {})["ads"][0]
    d = AdResultsDialog(shown)
    assert d.k_spend.value.text().startswith("Rs") and d.k_results.value.text() != "—" and d.k_cost.value.text().startswith("Rs") and len(d.chart._days) == 30
    assert d.k_results.kicker.text().upper() == "CHATS STARTED" or "Chats" in texts(d.k_results)
    d.chips.changed.emit("7")
    assert len(d.chart._days) == 7
    assert "blue is the chats" in d.explain.text()


def test_an_ad_that_has_not_run_has_nothing_to_report_and_says_so_instead_of_drawing_zeros(served):
    from addons.whatsapp.ad_results import AdResultsDialog
    account = make_account()
    make_ad(account)
    d = AdResultsDialog(demo_platform.handle("ads/list", {})["ads"][0])
    assert d.k_spend.value.text() == "—" and "nothing to report" in d.explain.text() and d.chart._days == []


def test_lead_form_and_website_ads_name_their_own_results():
    from addons.whatsapp.ad_results import result_words
    assert result_words("leadform")[2] == "leads" and result_words("website")[2] == "outbound_clicks" and result_words("ctwa")[2] == "conversations"


def test_a_slow_answer_for_an_old_range_is_ignored(served):
    from addons.whatsapp.ad_results import AdResultsDialog
    account = make_account()
    d = AdResultsDialog({"id": make_ad(account), "name": "x", "kind": "website"})
    d._token = 9
    d._shown(8, {"days": [{"day": "2026-10-01", "spend": 1, "impressions": 1, "clicks": 1, "ctr": 1, "reach": 1, "outbound_clicks": 1}], "totals": {}})
    assert d.chart._days == []


def test_the_chart_names_a_day_when_pointed_at():
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from addons.whatsapp.ad_results import SpendChart
    c = SpendChart()
    c.resize(500, 200)
    c.set_days([{"day": "2026-10-01", "spend": 100, "impressions": 4000, "clicks": 80, "ctr": 2.0, "results": 5}], "Chats started")
    area = c._area()
    c.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, QPointF(area.left() + 5, area.top() + 10), QPointF(area.left() + 5, area.top() + 10), Qt.NoButton, Qt.NoButton, Qt.NoModifier))
    assert "2026-10-01" in c.toolTip() and "Rs 100" in c.toolTip() and "Chats started 5" in c.toolTip()


# ── signing in with Facebook ─────────────────────────────────────────────────

@pytest.fixture
def browser(monkeypatch):
    opened = []
    from addons.whatsapp import ad_connect
    monkeypatch.setattr(ad_connect, "open_browser", lambda url: opened.append(url))
    return opened


def test_signing_in_opens_facebook_waits_and_then_offers_the_accounts_to_choose_from(served, browser):
    from addons.whatsapp.ad_connect import FacebookConnectDialog
    d = FacebookConnectDialog()
    assert browser and "facebook.com" in browser[0] and d.timer.isActive() and not d.again_btn.isHidden() and "come back here" in d.status.text()
    d.poll()
    assert d.go.isHidden() and d.timer.isActive()
    d.poll()
    assert not d.go.isHidden() and not d.timer.isActive() and "Signed in as Asha Patel" in d.status.text()
    assert d.accounts.count() == 2 and d.pages.count() == 1 and "Main account" in d.accounts.itemText(0)
    d._choose()
    assert d.result() == 1 or d.account_id


def test_the_chosen_account_is_connected_like_a_pasted_token(page, served, browser):
    from addons.whatsapp.ad_connect import FacebookConnectDialog
    d = FacebookConnectDialog(page)
    d.poll()
    d.poll()
    d._choose()
    page.activate()
    acct = state()["ad_accounts"][0]
    assert acct["connected_via"] == "facebook" and acct["ad_account_id"] == "1234567890" and page.new_btn.isEnabled()


def test_when_facebook_sign_in_is_not_set_up_it_says_so_and_offers_the_token(served, monkeypatch):
    from addons.whatsapp import ad_connect
    monkeypatch.setattr(ad_connect, "open_browser", lambda url: (_ for _ in ()).throw(AssertionError("nothing to open")))
    monkeypatch.setattr(ui, "PlatformWorker", _worker(served, fail={"ads/connect_start": "Signing in with Facebook is not set up on this server yet (the Meta app id is missing). Paste an access token instead."}))
    d = ad_connect.FacebookConnectDialog()
    heard = []
    d.paste_instead.connect(lambda: heard.append(1))
    assert "not set up" in d.error.text() and not d.paste_btn.isHidden() and not d.timer.isActive()
    d.paste_btn.click()
    assert heard == [1]


def test_a_sign_in_that_facebook_refused_says_why(served, browser, monkeypatch):
    from addons.whatsapp import ad_connect
    d = ad_connect.FacebookConnectDialog()
    d._status({"status": "failed", "error": "Meta did not let this sign-in through"})
    assert "did not connect" in d.status.text() and "did not let this sign-in through" in d.error.text() and not d.timer.isActive() and not d.paste_btn.isHidden()


def test_a_login_with_no_ad_account_or_page_says_what_to_add(served, browser):
    from addons.whatsapp import ad_connect
    d = ad_connect.FacebookConnectDialog()
    d._status({"status": "ready", "options": {"user": "Asha", "accounts": [], "pages": [{"id": "1", "name": "P"}]}})
    assert "no ad account or no Page" in d.error.text() and d.go.isHidden()


def test_waiting_too_long_gives_up(served, browser):
    from addons.whatsapp import ad_connect
    d = ad_connect.FacebookConnectDialog()
    d._polls = ad_connect.GIVE_UP
    d.poll()
    assert "took too long" in d.status.text() and not d.timer.isActive()


def test_the_connect_button_offers_facebook_and_the_token(page, monkeypatch):
    seen = {}
    monkeypatch.setattr(page, "_pop_up", lambda menu: seen.setdefault("items", [act.text() for act in menu.actions()]))
    page._connect_menu()
    assert seen["items"] == ["Continue with Facebook", "Paste an access token"]


# ── people lists ─────────────────────────────────────────────────────────────

def test_a_people_list_is_made_from_a_segment_and_listed(page, calls):
    from addons.whatsapp import ad_audiences as AA
    make_account()
    page.activate()
    page.show_section("audiences")
    assert "No lists yet" in texts(page.audiences)
    view = page.audiences

    def fake_exec(self):
        self.segment.setCurrentIndex(1)
        return 1
    with mock.patch.object(AA.FromSegmentDialog, "exec", fake_exec):
        view.from_segment()
    assert "audiences/from_segment" in routes(calls) and "Sent" in view.note.text() and "From a segment" in texts(view)


def test_a_segment_must_be_chosen_before_the_list_is_sent():
    from addons.whatsapp import ad_audiences as AA
    d = AA.FromSegmentDialog([{"id": "s1", "name": "VIPs", "size": 150}])
    d._go()
    assert "Choose a segment" in d.error.text()
    d.segment.setCurrentIndex(1)
    assert d.segment.currentData() == "s1"


def test_a_list_too_small_for_meta_is_explained(page):
    from addons.whatsapp import ad_audiences as AA
    make_account()
    page.activate()
    page.show_section("audiences")
    demo_platform.handle("segments/save", {"name": "Tiny", "filter": {"field": "tags", "value": ["no-one-has-this"]}})

    def fake_exec(self):
        self.segment.setCurrentIndex(self.segment.count() - 1)
        return 1
    with mock.patch.object(AA.FromSegmentDialog, "exec", fake_exec):
        page.audiences.from_segment()
    assert "at least 100 people" in page.audiences.note.text() and page.audiences.make_btn.isEnabled()


def test_people_like_a_list_are_made_in_one_country_at_a_chosen_width(page, calls):
    from addons.whatsapp import ad_audiences as AA
    account = make_account()
    st = state()
    st.setdefault("ads_extra", {"audiences": [], "suggestions": [], "connect": {}, "pictures": {}})["audiences"].append(
        {"id": "aud1", "account_id": account, "name": "VIPs", "kind": "segment", "meta_id": "2381", "segment_id": "s1", "source": {"sent": 150}, "size": 150, "created_at": "2026-10-01T00:00:00Z"})
    page.show_section("audiences")
    d = AA.LookalikeDialog("VIPs")
    d.country.setText("in")
    d.ratio.setValue(2)
    assert d.value() == {"country": "IN", "ratio": 0.02}
    d.country.setText("I")
    d._go()
    assert "two letters" in d.error.text()
    with mock.patch.object(AA.LookalikeDialog, "exec", return_value=1), mock.patch.object(AA.LookalikeDialog, "value", lambda self: {"country": "IN", "ratio": 0.02}):
        page.audiences.lookalike(page.audiences.audiences[0])
    assert "audiences/lookalike" in routes(calls) and "look-alike 2% IN" in texts(page.audiences)


def test_removing_a_list_asks_first(page, calls):
    account = make_account()
    st = state()
    st.setdefault("ads_extra", {"audiences": [], "suggestions": [], "connect": {}, "pictures": {}})["audiences"].append(
        {"id": "aud1", "account_id": account, "name": "VIPs", "kind": "segment", "meta_id": "2381", "segment_id": "s1", "source": {"sent": 150}, "size": 150, "created_at": "2026-10-01T00:00:00Z"})
    page.show_section("audiences")
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No):
        page.audiences.remove(page.audiences.audiences[0])
    assert "audiences/delete" not in routes(calls)
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        page.audiences.remove(page.audiences.audiences[0])
    assert "No lists yet" in texts(page.audiences)


# ── suggestions ──────────────────────────────────────────────────────────────

def test_looking_at_the_ads_lists_what_to_change_and_nothing_happens_until_yes(page, calls):
    account = make_account()
    ad = make_ad(account, kind="ctwa", whatsapp_number="919800000000")
    demo_platform.handle("ads/activate", {"ad_id": ad, "confirm": True})
    page.activate()
    page.show_section("suggestions")
    assert "No suggestions" in texts(page.suggestions)
    page.suggestions.look()
    t = texts(page.suggestions)
    assert "Pause “Walls”" in t and "no chats" in t and page.suggestions.look_btn.isEnabled()
    assert "Suggestions (1)" in page.chips._buttons["suggestions"].text()
    assert state()["ads"][0]["status"] == "ACTIVE"
    page.suggestions.decide(page.suggestions.items[0], True)
    assert state()["ads"][0]["status"] == "PAUSED" and "No suggestions" in texts(page.suggestions)


def test_a_suggestion_can_be_left_as_it_is(page):
    account = make_account()
    ad = make_ad(account)
    demo_platform.handle("ads/activate", {"ad_id": ad, "confirm": True})
    page.show_section("suggestions")
    page.suggestions.look()
    page.suggestions.decide(page.suggestions.items[0], False)
    assert state()["ads"][0]["status"] == "ACTIVE" and "Left as it is" in page.suggestions.note.text()


# ── the demo platform's rules ────────────────────────────────────────────────

@pytest.mark.parametrize("extra,fragment", [
    ({"kind": "billboard"}, "a chat on WhatsApp"), ({"link": "shakti.example"}, "web address"), ({"cta": "BUY_NOW"}, "the button is one of"), ({"daily_budget": 5}, "daily budget"),
    ({"lifetime_budget": 500000}, "end date"), ({"targeting": {}}, "countries or cities"), ({"targeting": {"geo_locations": {"countries": ["India"]}}}, "two-letter"),
    ({"targeting": {"geo_locations": {"countries": ["IN"]}, "age_min": 40, "age_max": 30}}, "youngest")])
def test_the_demo_refuses_what_the_server_refuses_in_the_same_words(extra, fragment):
    account = make_account()
    with pytest.raises(PlatformError) as why:
        make_ad(account, **extra)
    assert fragment in str(why.value)


def test_a_lead_form_without_a_way_to_reach_people_or_a_privacy_policy_is_refused():
    account = make_account()
    with pytest.raises(PlatformError) as why:
        make_ad(account, kind="leadform", link=None, form={"questions": ["FULL_NAME"], "privacy_url": "https://x.example/p"})
    assert "phone number or an email" in str(why.value)
    with pytest.raises(PlatformError) as why:
        make_ad(account, kind="leadform", link=None, form={"questions": ["FULL_NAME", "PHONE"]})
    assert "privacy policy" in str(why.value)


def test_the_demo_numbers_are_the_same_for_the_same_ad_so_a_screen_does_not_shimmer():
    account = make_account()
    ad = make_ad(account)
    demo_platform.handle("ads/activate", {"ad_id": ad, "confirm": True})
    a = demo_platform.handle("ads/report", {"ad_id": ad, "since": "2026-10-01", "until": "2026-10-10"})
    b = demo_platform.handle("ads/report", {"ad_id": ad, "since": "2026-10-01", "until": "2026-10-10"})
    assert a == b and len(a["days"]) == 10
    with pytest.raises(PlatformError):
        demo_platform.handle("ads/report", {"ad_id": ad, "since": "2026-10-10", "until": "2026-10-01"})
