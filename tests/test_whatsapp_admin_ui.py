"""Settings (team, quick replies, stores, API keys, numbers), Ads, AI agents, the inbox's team actions, and the campaign
extras (a test to your own phone, repeating, local send time) — driven against the demo platform with a fake worker.

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
from PySide6.QtCore import Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QWidget  # noqa: E402

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
    tmp = tempfile.mkdtemp(prefix="prism-wa-admin-")
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


def button(widget, text):
    return next(b for b in widget.findChildren(QPushButton) if b.text() == text)


# ── Settings: the shell and the connection ───────────────────────────────────

def test_the_settings_page_has_its_sections_and_builds_each_only_when_opened(served):
    from addons.whatsapp import settings as S
    page = S.SettingsPage({})
    assert [b.text() for b in page._buttons.values()] == ["Connection", "Test message", "Team and inbox", "Quick replies", "Media library", "Tags and attributes", "Opt-in and opt-out", "Notifications", "Business profile", "Plan and usage", "Links and QR", "Blue tick", "Stores", "Developers", "Audit log", "Single sign-on", "Branding and resellers"]
    assert list(page._sections) == ["connection"]
    page.show_section("stores")
    assert set(page._sections) == {"connection", "stores"}


def test_the_test_section_keeps_following_the_panels_config(served):
    from addons.whatsapp import settings as S
    page = S.SettingsPage({"whatsapp": {"token": "a"}})
    page.show_section("test")
    page.cfg = {"whatsapp": {"token": "b"}}
    assert page._sections["test"].cfg == {"whatsapp": {"token": "b"}}


@pytest.fixture
def connection(served):
    from addons.whatsapp import settings as S
    sec = S.ConnectionSection()
    yield sec


def test_the_numbers_on_the_workspace_are_listed_with_their_state(connection):
    connection.load_numbers()
    assert "+91 98765 43210" in texts(connection) and "Connected" in texts(connection) and "Quality: high" in texts(connection)


def test_a_workspace_with_no_number_says_so(connection):
    demo_platform._state()["numbers"] = []
    connection.load_numbers()
    assert "No number is connected yet." in texts(connection)


def test_a_server_that_cannot_list_numbers_says_why(calls, monkeypatch):
    from addons.whatsapp import settings as S
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls, fail={"numbers/list": "The WhatsApp add-on isn't set up on the server yet."}))
    sec = S.ConnectionSection()
    sec.load_numbers()
    assert "isn't set up" in sec.numbers_note.text() and sec.numbers_col.count() == 0


def test_connecting_a_number_opens_metas_window_and_keeps_the_link_to_copy(connection):
    from addons.whatsapp import settings as S
    with mock.patch.object(S.QDesktopServices, "openUrl") as opened, mock.patch.object(S.demo, "enabled", return_value=False):
        connection._connect()
    assert opened.call_args[0][0].toString() == "https://example.com/onboarding?state=demo"
    assert not connection.link_row.isHidden() and connection.link_edit.text().startswith("https://")
    assert "press Refresh" in connection.numbers_note.text() and connection.connect_btn.isEnabled()


def test_a_missing_link_is_explained_not_ignored(connection, monkeypatch):
    from addons.whatsapp import settings as S
    monkeypatch.setattr(ui, "PlatformWorker", _worker([], fail={}))
    with mock.patch.object(demo_platform, "handle", lambda route, data: {"state": "x", "path": "/onboarding"}), mock.patch.object(S.QDesktopServices, "openUrl") as opened:
        connection._connect()
    assert not opened.called and "did not give a link" in connection.numbers_note.text()


# ── Settings: team ───────────────────────────────────────────────────────────

@pytest.fixture
def team(served):
    from addons.whatsapp import settings_team as T
    sec = T.TeamSection()
    sec.activate()
    return sec


def test_the_team_is_listed_with_how_many_chats_wait(team):
    names = [r.agent["name"] for r in team.findChildren(type(team.agents_col.itemAt(0).widget()))]
    assert names == ["You", "Bala", "Meera"]
    assert "open chats" in team.monitor.text() and "waiting for a person" in team.monitor.text()


def test_changing_a_teammates_role_saves_at_once(team, calls):
    row = team.agents_col.itemAt(1).widget()                     # Bala
    row.role.setCurrentIndex(row.role.findData("manager"))
    row.role.activated.emit(row.role.currentIndex())
    assert ("inbox/agents/update", {"agent_id": "a2", "changes": {"role": "manager"}}) in calls
    assert row.agent["role"] == "manager" and team.team_note.text() == "Saved."


def test_a_refused_change_is_explained_and_the_control_goes_back(team):
    row = team.agents_col.itemAt(0).widget()                     # the only owner
    row.role.setCurrentIndex(row.role.findData("agent"))
    row.role.activated.emit(row.role.currentIndex())
    assert "at least one owner" in team.team_note.text() and row.role.currentData() == "owner"


def test_availability_and_hidden_numbers_are_toggles_that_save(team, calls):
    row = team.agents_col.itemAt(1).widget()
    row.available.setChecked(False)
    row.masked.setChecked(True)
    assert ("inbox/agents/update", {"agent_id": "a2", "changes": {"available": False}}) in calls
    assert ("inbox/agents/update", {"agent_id": "a2", "changes": {"masked": True}}) in calls


def test_working_hours_are_edited_as_days_and_times(served):
    from addons.whatsapp import settings_team as T
    h = T.HoursEditor()
    assert h.value() is None
    h.always.setChecked(False)
    v = h.value()
    assert v["tz"] == "Asia/Kolkata" and sorted(v["days"]) == ["fri", "mon", "sat", "thu", "tue", "wed"] and v["days"]["mon"] == [["09:00", "18:00"]]
    h.rows["sat"][0].setChecked(False)
    assert "sat" not in h.value()["days"]
    h2 = T.HoursEditor()
    h2.set_value({"tz": "Asia/Dubai", "days": {"mon": [["08:30", "17:00"]]}})
    assert h2.value() == {"tz": "Asia/Dubai", "days": {"mon": [["08:30", "17:00"]]}}
    h2.set_value(None)
    assert h2.value() is None


def test_the_inbox_rules_load_and_save_together(team, calls):
    team.routing.setCurrentIndex(team.routing.findData("round_robin"))
    team.sla.setValue(30)
    team.welcome_on.setChecked(True)
    team.welcome_text.setPlainText("Hello! How can we help?")
    team._save_rules()
    route, data = [c for c in calls if c[0] == "inbox/settings/save"][0]
    s = data["settings"]
    assert s["routing"] == "round_robin" and s["sla_minutes"] == 30 and s["welcome"] == {"enabled": True, "text": "Hello! How can we help?", "once_per_hours": 24, "asset_id": None, "template": None}
    assert team.rules_note.text() == "Saved."
    team2 = type(team)()
    team2.activate()
    assert team2.routing.currentData() == "round_robin" and team2.welcome_on.isChecked()


# ── Settings: quick replies ──────────────────────────────────────────────────

@pytest.fixture
def replies(served):
    from addons.whatsapp import settings_team as T
    sec = T.QuickRepliesSection()
    sec.activate()
    return sec


def test_saved_replies_are_listed_with_their_slash_names(replies):
    assert "/thanks" in texts(replies) and "/hours" in texts(replies)


def test_a_reply_is_added_changed_and_deleted(replies, calls):
    replies.shortcut.setText("/Directions")
    replies.body.setPlainText("Our office is at Alkapuri.")
    replies._save()
    assert ("inbox/canned/save", {"shortcut": "/Directions", "body": "Our office is at Alkapuri.", "asset_id": None}) in calls
    assert "/directions" in texts(replies) and replies.shortcut.text() == ""
    replies._edit({"shortcut": "hours", "body": "x"})
    assert replies.shortcut.text() == "hours"
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        replies._delete({"shortcut": "directions"})
    assert "/directions" not in texts(replies)


def test_a_bad_name_is_explained(replies):
    replies.shortcut.setText("two words")
    replies.body.setPlainText("x")
    replies._save()
    assert "lowercase letters" in replies.note.text()


# ── Settings: stores ─────────────────────────────────────────────────────────

APPROVED = [{"name": "order_update", "language": "en_US", "status": "APPROVED",
             "components": [{"type": "BODY", "text": "Hello {{1}}, your order {{2}} has shipped and will reach you tomorrow."}]}]


def test_a_store_connection_is_built_from_what_is_ticked(served):
    from addons.whatsapp import settings_stores as ST
    d = ST.StoreDialog(APPROVED)
    d.name.setText("Main shop")
    d.secret.setText("whsec_abcdefgh")
    box = d.boxes["order_created"]
    box.on.setChecked(True)
    box.rows["2"][0].setCurrentIndex(box.rows["2"][0].findData("order.name"))
    cfg = d.config()
    assert cfg["events"]["order_created"] == {"template": "order_update", "language": "en_US", "enabled": True,
                                              "variables": {"1": "customer.first_name", "2": "order.name"}}
    assert "order_fulfilled" not in cfg["events"] and cfg["default_country"] == "91" and cfg["consent_attested"] is False


def test_a_fixed_text_blank_is_stored_with_an_equals_sign(served):
    from addons.whatsapp import settings_stores as ST
    d = ST.StoreDialog(APPROVED)
    box = d.boxes["order_created"]
    box.on.setChecked(True)
    combo, edit = box.rows["1"]
    combo.setCurrentIndex(combo.findData(ST.FIXED))
    edit.setText("Customer")
    assert d.config()["events"]["order_created"]["variables"]["1"] == "=Customer"


def test_an_abandoned_cart_asks_how_long_to_wait(served):
    from addons.whatsapp import settings_stores as ST
    d = ST.StoreDialog(APPROVED)
    box = d.boxes["abandoned_cart"]
    box.on.setChecked(True)
    box.delay.setValue(120)
    assert d.config()["events"]["abandoned_cart"]["delay_minutes"] == 120


def test_an_event_cannot_be_ticked_without_an_approved_template(served):
    from addons.whatsapp import settings_stores as ST
    d = ST.StoreDialog([])
    assert not d.boxes["order_created"].on.isEnabled() and d.config()["events"] == {}


def test_a_store_needs_a_name_a_secret_and_one_event(served, calls):
    from addons.whatsapp import settings_stores as ST
    d = ST.StoreDialog(APPROVED)
    d._go()
    assert "name" in d.error.text().lower()
    d.name.setText("Shop")
    d._go()
    assert "secret" in d.error.text().lower()
    d.secret.setText("whsec_abcdefgh")
    d._go()
    assert "at least one" in d.error.text() and "integrations/create" not in routes(calls)


def test_connecting_a_store_shows_where_to_paste_the_address(served):
    from addons.whatsapp import settings_stores as ST
    sec = ST.StoresSection()
    sec.activate()
    d = ST.StoreDialog(sec._templates)
    d.name.setText("Shop")
    d.secret.setText("whsec_abcdefgh")
    d.boxes["order_created"].on.setChecked(True)
    with mock.patch.object(ST.StoreDialog, "exec", lambda self: (self._go(), 1)[1]), mock.patch.object(ST, "StoreDialog", lambda *a, **k: d):
        sec._new()
    assert "https://example.com/hooks/shopify/" in sec.howto_text.text() and not sec.howto[0].isHidden()
    assert "Shop" in texts(sec) and "An order is placed".lower() in texts(sec).lower()


def test_a_store_can_be_paused_changed_and_disconnected(served, calls):
    from addons.whatsapp import settings_stores as ST
    demo_platform.handle("integrations/create", {"kind": "woocommerce", "name": "Blog shop", "secret": "abcdefgh12",
                                                  "config": {"events": {"order_created": {"template": "order_update", "variables": {"1": "customer.name"}}}}})
    sec = ST.StoresSection()
    sec.activate()
    row = sec.list_col.itemAt(0).widget()
    row.findChildren(type(ST.C.ToggleSwitch()))[0].setChecked(False)
    assert any(r == "integrations/update" and d["enabled"] is False for r, d in calls)
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        sec._delete({"id": demo_platform._state()["auto"]["integrations"][0]["id"], "name": "Blog shop"})
    assert "No store is connected yet." in texts(sec)


def test_a_refused_connection_shows_the_servers_reason_in_the_window(calls, monkeypatch):
    from addons.whatsapp import settings_stores as ST
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls, fail={"integrations/create": "Store integrations are not part of the Basic plan."}))
    d = ST.StoreDialog(APPROVED)
    d.name.setText("Shop")
    d.secret.setText("whsec_abcdefgh")
    d.boxes["order_created"].on.setChecked(True)
    d._go()
    assert "not part of the Basic plan" in d.error.text() and d.go.isEnabled()


# ── Settings: developers ─────────────────────────────────────────────────────

def test_scopes_are_shown_as_what_they_let_a_key_do():
    from addons.whatsapp.settings_developers import scope_words
    assert scope_words("messages:send") == "Send messages" and scope_words("contacts:write") == "Add and change contacts"
    assert scope_words("new:thing") == "new:thing"


def test_a_key_needs_a_name_and_a_permission_and_its_secret_is_shown_once(served, calls):
    from addons.whatsapp import settings_developers as D
    sec = D.DevelopersSection()
    sec.activate()
    assert "https://example.com/api/v1" in sec.base.text() and "No keys yet." in texts(sec)
    d = D.NewKeyDialog(sec._scopes)
    d._go()
    assert "name" in d.error.text().lower()
    d.name.setText("Website form")
    d._go()
    assert "at least one" in d.error.text()
    d.boxes["contacts:write"].setChecked(True)
    d.rate.setValue(30)
    d._go()
    key = d.created
    assert key["secret"].startswith("pk_live_") and key["scopes"] == ["contacts:write"] and key["rate_limit_per_minute"] == 30
    sd = D.SecretDialog(key)
    assert sd.secret == key["secret"]
    sec.activate()
    assert "Website form" in texts(sec)
    assert key["secret"] not in texts(sec)                          # listed by its prefix only


def test_a_key_is_revoked_after_asking(served, calls):
    from addons.whatsapp import settings_developers as D
    made = demo_platform.handle("api_keys/create", {"name": "Zap", "scopes": ["messages:send"]})["key"]
    sec = D.DevelopersSection()
    sec.activate()
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No):
        sec._revoke(made)
    assert "api_keys/revoke" not in routes(calls)
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        sec._revoke(made)
    assert "Revoked" in texts(sec)


# ── Ads ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def ads(served):
    from addons.whatsapp import ads_page as AP
    page = AP.AdsPage({})
    page.activate()
    return page


def test_without_an_ad_account_the_page_asks_to_connect_one(ads):
    assert ads.state.title.text() == "Connect your ad account" and ads.state.action.text() == "Connect ad account"
    assert not ads.new_btn.isEnabled()


def test_connecting_an_account_then_asking_for_a_first_ad(ads, calls):
    from addons.whatsapp import ads_page as AP
    d = AP.ConnectAccountDialog()
    d.acct.setText("act_1234567890")
    d.page.setText("987654321")
    d.token.setText("EAAB-ads-token-that-is-long-enough")
    d._go()
    assert "ads/connect" in routes(calls)
    ads.activate()
    assert ads.state.title.text() == "No ads yet" and ads.new_btn.isEnabled()


def test_bad_account_details_are_explained_in_the_window(ads):
    from addons.whatsapp import ads_page as AP
    d = AP.ConnectAccountDialog()
    d.acct.setText("not a number")
    d._go()
    assert "number shown in Ads Manager" in d.error.text() and d.go.isEnabled()


def make_account():
    demo_platform.handle("ads/connect", {"ad_account_id": "1234567890", "page_id": "987654321", "token": "EAAB-ads-token-that-is-long-enough", "name": "Main"})


def test_a_new_ad_is_made_paused_with_the_budget_in_paise(served, calls):
    from addons.whatsapp import ads_page as AP
    make_account()
    page = AP.AdsPage({})
    page.activate()
    d = AP.NewAdDialog(page._accounts, "919800000000")
    d.name.setText("Diwali visits")
    d.message.setPlainText("Free site visit this week")
    d.budget.setValue(750)
    d.countries.setText("in, ae")
    d.breakers.setPlainText("Get a quote\nBook a visit\n\n")
    data = d.payload()
    assert data["daily_budget"] == 75000 and data["targeting"]["geo_locations"]["countries"] == ["IN", "AE"]
    assert data["ice_breakers"] == ["Get a quote", "Book a visit"] and data["whatsapp_number"] == "919800000000" and "image_hash" not in data
    d._go()
    page.activate()
    assert "Diwali visits" in texts(page) and "Paused" in texts(page)


def test_turning_an_ad_on_asks_first_and_says_it_spends(served, calls):
    from addons.whatsapp import ads_page as AP
    make_account()
    demo_platform.handle("ads/create", {"account_id": demo_platform._state()["auto"]["ad_accounts"][0]["id"], "name": "A", "whatsapp_number": "919800000000",
                                        "daily_budget": 50000, "targeting": {"geo_locations": {"countries": ["IN"]}}, "message": "x"})
    page = AP.AdsPage({})
    page.activate()
    ad = page.list_col.itemAt(0).widget().ad
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No) as q:
        page.activate_ad(ad)
    assert "ads/activate" not in routes(calls) and "start spending" in q.call_args[0][2]
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        page.activate_ad(ad)
    assert ("ads/activate", {"ad_id": ad["id"], "confirm": True}) in calls and "In review at Meta" in texts(page)       # Meta looks at it first; the screen says so
    page.check_status(ad)
    assert "Running" in texts(page) and "Meta says: Running" in page.note.text()
    page.pause_ad(ad)
    assert "Paused" in texts(page)


def test_results_are_shown_as_lines_in_rupees():
    from addons.whatsapp import ads_page as AP
    lines = dict(AP.insight_lines({"reach": 900, "impressions": 1200, "clicks": 40, "spend": 250.5, "conversations": 10, "cost_per_conversation": 25.05}))
    assert lines["Spent so far"] == "₹250.50" and lines["Chats started"] == "10" and lines["Cost per chat"] == "₹25.05" and lines["Times shown"] == "1,200"
    assert AP.rupees_to_paise(499.99) == 49999


def test_a_failed_load_says_why_and_offers_another_try(calls, monkeypatch):
    from addons.whatsapp import ads_page as AP
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls, fail={"ads/accounts": "The WhatsApp add-on isn't set up on the server yet."}))
    page = AP.AdsPage({})
    page.activate()
    assert page.state.title.text() == "Couldn't load your ads" and "isn't set up" in page.state.body.text() and page.state.action.text() == "Try again"


# ── AI agents ────────────────────────────────────────────────────────────────

@pytest.fixture
def agents(served):
    from addons.whatsapp import agents_page as AG
    sec = AG.AgentsSection({})
    sec.activate()
    return sec


def test_with_no_agent_the_page_invites_a_first_one(agents):
    assert agents.state.title.text() == "No AI agent yet" and agents.state.action.text() == "New agent"


def test_a_new_agent_opens_in_the_editor(agents, calls):
    agents._new()
    assert agents.editor is not None and agents.editor.agent["name"] == "New agent" and agents.stack.currentIndex() == 1
    assert "ai/agents/create" in routes(calls) and "New agent" in texts(agents)


def test_an_agents_behaviour_is_saved_from_the_form(agents, calls):
    agents._new()
    ed = agents.editor
    ed.name.setText("Aria")
    ed.instructions.setPlainText("Be warm and brief.")
    ed.words.setText("human, refund , ")
    ed.max.setValue(5)
    ed.closed_only.setChecked(True)
    ed.save()
    route, data = [c for c in calls if c[0] == "ai/agents/update"][0]
    assert {k: data["changes"][k] for k in ("name", "instructions", "handoff_words", "max_replies", "business_hours_only")} == {
        "name": "Aria", "instructions": "Be warm and brief.", "handoff_words": ["human", "refund"], "max_replies": 5, "business_hours_only": True}
    assert set(data["changes"]) == {"name", "instructions", "handoff_words", "max_replies", "business_hours_only", "profile", "voice", "skills", "actions", "settings"}   # the whole draft goes
    assert ed.saved.text() == "Saved."


def test_switching_an_agent_on_and_making_it_the_default(agents):
    agents._new()
    ed = agents.editor
    ed.on.setChecked(True)
    assert ed.agent["enabled"] and ed.status.text() == "On — only when a flow hands over"
    ed.default.setChecked(True)
    assert ed.agent["is_default"] and ed.status.text() == "Answering"
    ed.on.setChecked(False)
    assert not ed.default.isChecked() and ed.status.text() == "Off"


def test_making_an_agent_that_is_off_the_default_is_refused_and_the_box_goes_back(agents):
    agents._new()
    ed = agents.editor
    ed.default.setChecked(True)
    assert not ed.default.isChecked() and "Switch the agent on first" in ed.note.text()


def test_knowledge_is_added_as_text_a_question_a_page_and_listed(agents, calls):
    from addons.whatsapp import agents_page as AG
    agents._new()
    ed = agents.editor
    aid = ed.agent["id"]
    d = AG.KnowledgeDialog(aid, "text")
    d.title.setText("Delivery")
    d.text.setPlainText("We deliver within fifty kilometres.")
    d._go()
    f = AG.KnowledgeDialog(aid, "faq")
    f.title.setText("When do you open?")
    f.answer.setPlainText("At ten every day.")
    f._go()
    u = AG.KnowledgeDialog(aid, "url")
    u.url.setText("https://example.com/contact")
    u._go()
    ed.load_knowledge()
    t = texts(ed)
    assert "Delivery" in t and "When do you open?" in t and "https://example.com/contact" in t and "Q & A" in t and "Web page" in t


def test_a_bad_page_address_is_explained_in_the_window(agents):
    from addons.whatsapp import agents_page as AG
    agents._new()
    u = AG.KnowledgeDialog(agents.editor.agent["id"], "url")
    u.url.setText("http://insecure.example")
    u._go()
    assert "https://" in u.error.text() and u.go.isEnabled()


def test_forgetting_something_asks_first(agents, calls):
    from addons.whatsapp import agents_page as AG
    agents._new()
    ed = agents.editor
    d = AG.KnowledgeDialog(ed.agent["id"], "text")
    d.title.setText("Old")
    d.text.setPlainText("Outdated information here.")
    d._go()
    ed.load_knowledge()
    doc = demo_platform._state()["auto"]["kb"][ed.agent["id"]][0]
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No):
        ed._forget(doc)
    assert "ai/knowledge/delete" not in routes(calls)
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        ed._forget(doc)
    assert "It has not been taught anything yet." in texts(ed)


def test_trying_an_agent_shows_the_answer_and_which_note_it_used(agents):
    from addons.whatsapp import agents_page as AG
    agents._new()
    ed = agents.editor
    d = AG.KnowledgeDialog(ed.agent["id"], "faq")
    d.title.setText("When do you open?")
    d.answer.setPlainText("At ten every day.")
    d._go()
    ed.try_it.edit.setText("when do you open")
    ed.try_it._send()
    assert "At ten every day." in texts(ed.try_it) and "Used: When do you open?" in texts(ed.try_it)
    ed.try_it.edit.setText("I need a human")
    ed.try_it._send()
    assert "hand this chat to your team" in texts(ed.try_it)
    assert len(ed.try_it.messages) == 4
    ed.try_it.reset()
    assert ed.try_it.messages == []


def test_an_unreachable_model_is_explained_and_the_message_is_not_kept(calls, monkeypatch):
    from addons.whatsapp import agents_page as AG
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls, fail={"ai/test": "AI replies are not switched on for this server yet."}))
    sec = AG.AgentsSection({})
    sec.activate()
    sec._new()
    ed = sec.editor
    ed.try_it.edit.setText("hello")
    ed.try_it._send()
    assert "not switched on" in ed.try_it.note.text() and ed.try_it.messages == [] and ed.try_it.send.isEnabled()


def test_the_monthly_allowance_is_shown_and_an_unconfigured_server_is_explained(agents):
    agents._new()
    ed = agents.editor
    assert "0 of 1000 AI replies used this month." in ed.usage_text.text()
    ed.show_usage({"replies": 5, "limit": None, "configured": True})
    assert "no limit on your plan" in ed.usage_text.text()
    ed.show_usage({"replies": 0, "limit": 1000, "configured": False})
    assert "not switched on for this server" in ed.usage_text.text()


def test_deleting_an_agent_asks_first(agents):
    agents._new()
    ed = agents.editor
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        ed._delete()
    assert agents.editor is None and agents.state.title.text() == "Choose an agent"


def test_files_are_read_as_text(tmp_path):
    from addons.whatsapp import agents_page as AG
    t = tmp_path / "notes.txt"
    t.write_text("We deliver in fifty kilometres.", encoding="utf-8")
    assert AG.read_document(str(t)) == "We deliver in fifty kilometres."
    c = tmp_path / "rates.csv"
    c.write_text("Item,Rate\nBoundary wall,450\n", encoding="utf-8")
    assert "Boundary wall · 450" in AG.read_document(str(c))
    w = tmp_path / "cp.txt"
    w.write_bytes("Café ₹5".encode("cp1252", errors="ignore"))
    assert "Caf" in AG.read_document(str(w))


def test_a_word_file_is_read(tmp_path):
    docx = pytest.importorskip("docx")
    from addons.whatsapp import agents_page as AG
    d = docx.Document()
    d.add_paragraph("Our hours are nine to six.")
    table = d.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Visit"
    table.rows[0].cells[1].text = "Free"
    path = tmp_path / "info.docx"
    d.save(str(path))
    out = AG.read_document(str(path))
    assert "nine to six" in out and "Visit · Free" in out


def test_files_that_cannot_be_read_say_why(tmp_path):
    from addons.whatsapp import agents_page as AG
    with pytest.raises(ValueError, match="not there"):
        AG.read_document(str(tmp_path / "nope.txt"))
    p = tmp_path / "x.exe"
    p.write_bytes(b"MZ")
    with pytest.raises(ValueError, match="can read"):
        AG.read_document(str(p))
    big = tmp_path / "big.txt"
    big.write_bytes(b"a" * (AG.MAX_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="6 MB"):
        AG.read_document(str(big))
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 not really")
    with pytest.raises(ValueError):
        AG.read_document(str(pdf))


def test_choosing_a_file_fills_the_window(agents, tmp_path):
    from addons.whatsapp import agents_page as AG
    agents._new()
    t = tmp_path / "price-list.txt"
    t.write_text("Wall: 450 per sq ft.", encoding="utf-8")
    d = AG.KnowledgeDialog(agents.editor.agent["id"], "file")
    d.load(str(t))
    assert d.title.text() == "price-list" and "characters read" in d.file_label.text()
    d._go()
    docs = demo_platform._state()["auto"]["kb"][agents.editor.agent["id"]]
    assert docs[0]["kind"] == "file" and docs[0]["source"] == "price-list.txt"
    empty = AG.KnowledgeDialog(agents.editor.agent["id"], "file")
    empty._go()
    assert "Choose a file first" in empty.error.text()


# ── the inbox's team actions ─────────────────────────────────────────────────

def test_a_chats_state_is_put_in_words():
    from addons.whatsapp.inbox_actions import state_words
    team = [{"id": "a1", "name": "You"}, {"id": "a2", "name": "Bala"}]
    assert state_words({"status": "active"}, team, "a1") == ("Not taken", "quiet")
    assert state_words({"status": "requesting"}, team, "a1") == ("Needs a person", "warn")
    assert state_words({"status": "intervened", "assignee_id": "a2"}, team, "a1") == ("With Bala", "info")
    assert state_words({"status": "intervened", "assignee_id": "a1"}, team, "a1") == ("With you", "info")
    assert state_words({"status": "closed"}, team, "a1") == ("Resolved", "quiet")


@pytest.fixture
def bar(served):
    from addons.whatsapp.inbox_actions import ConversationBar
    b = ConversationBar()
    b.agents = [{"id": "a1", "name": "You", "available": True}, {"id": "a2", "name": "Bala", "available": False}]
    b.row = {"id": "c1", "contact_name": "Asha Patel"}
    return b


def show(bar, status, assignee=None):
    bar.show_for(bar.row, {"status": status, "assignee_id": assignee}, bar.agents, "a1")


def names(bar):
    return [b.text() for b in bar.findChildren(QPushButton)]


def test_an_untaken_chat_offers_take_over_and_resolve(bar):
    show(bar, "active")
    assert not bar.isHidden() and bar.pill.text() == "Not taken" and names(bar) == ["Take over", "Resolve", "Notes"]


def test_a_chat_that_needs_a_person_says_so(bar):
    show(bar, "requesting")
    assert bar.pill.text() == "Needs a person" and "Take over" in names(bar)


def test_a_chat_someone_has_offers_handing_back_passing_on_and_resolving(bar):
    show(bar, "intervened", "a1")
    assert bar.pill.text() == "With you" and names(bar) == ["Hand back to the bot", "Transfer…", "Resolve", "Notes"]


def test_a_resolved_chat_offers_only_notes(bar):
    show(bar, "closed")
    assert names(bar) == ["Notes"]


def test_each_action_is_one_call_and_tells_the_page_to_refresh(bar, calls):
    heard = []
    bar.changed.connect(lambda: heard.append(1))
    show(bar, "active")
    button(bar, "Take over").click()
    button(bar, "Resolve").click()
    assert ("inbox/intervene", {"conversation_id": "c1"}) in calls and ("inbox/resolve", {"conversation_id": "c1"}) in calls and len(heard) == 2
    show(bar, "intervened", "a1")
    button(bar, "Hand back to the bot").click()
    assert ("inbox/hand_back", {"conversation_id": "c1"}) in calls


def test_passing_a_chat_on_names_the_teammate_and_marks_the_away(bar, calls):
    from addons.whatsapp import inbox_actions as IA
    show(bar, "intervened", "a1")
    picked = []

    class FakeMenu:
        def __init__(self, parent=None):
            self.items = []

        def addAction(self, label):
            picked.append(label)
            act = mock.Mock()
            self.items.append(act)
            return act

        def exec(self, pos):
            self.items[0].triggered.connect.call_args[0][0]()

    with mock.patch.object(IA, "QMenu", FakeMenu):
        bar._transfer()
    assert picked == ["Bala (away)"] and ("inbox/transfer", {"conversation_id": "c1", "to_agent_id": "a2"}) in calls


def test_nobody_to_pass_it_to_is_said_in_words(bar):
    show(bar, "intervened", "a1")
    bar.agents = [{"id": "a1", "name": "You"}]
    said = []
    bar.problem.connect(said.append)
    bar._transfer()
    assert said == ["There is nobody else on your team to give it to."]


def test_a_refusal_from_the_server_goes_to_the_page(bar, monkeypatch):
    monkeypatch.setattr(ui, "PlatformWorker", _worker([], fail={"inbox/intervene": "Another teammate already has this chat."}))
    said = []
    bar.problem.connect(said.append)
    show(bar, "active")
    button(bar, "Take over").click()
    assert said == ["Another teammate already has this chat."]


def test_notes_are_listed_and_added(served, calls):
    from addons.whatsapp.inbox_actions import NotesDialog
    d = NotesDialog("c1", "Asha Patel")
    assert "No notes yet." in texts(d)
    d.edit.setPlainText("Wants a quote by Friday")
    d._add()
    assert "Wants a quote by Friday" in texts(d) and d.edit.toPlainText() == "" and "You" in texts(d)
    d._add()                                                             # nothing written: nothing sent
    assert routes(calls).count("inbox/notes/add") == 1


def test_a_saved_reply_is_filled_in_for_the_person_and_put_in_the_box(served):
    from addons.whatsapp.inbox_actions import QuickReplyButton
    q = QuickReplyButton()
    q.load()
    q.contact_id = "k1"
    got = []
    q.chosen.connect(lambda text, asset: got.append((text, asset)))
    q._pick(q.canned[1])
    assert got == [("Thanks Asha! We'll get back to you shortly.", None)]


def test_the_menu_of_saved_replies_lists_them_by_slash_name(served):
    from addons.whatsapp import inbox_actions as IA
    q = IA.QuickReplyButton()
    q.load()
    labels = []

    class FakeMenu:
        def __init__(self, parent=None):
            pass

        def addAction(self, label):
            labels.append(label)
            return mock.Mock()

        def exec(self, pos):
            pass

    with mock.patch.object(IA, "QMenu", FakeMenu):
        q._menu()
    assert labels[0].startswith("/hours") and labels[1].startswith("/thanks")


# (the Inbox's own tests, including the team bar, live in test_whatsapp_inbox_ui.py)


# ── campaigns: a test to your own phone, repeating, local time ───────────────

@pytest.fixture
def campaigns(calls, monkeypatch):
    from addons.whatsapp import campaigns_page as CP
    monkeypatch.setattr(CP, "PlatformWorker", _worker(calls))
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    page = CP.CampaignsPage({})
    page.activate()
    return page


def yes():
    return mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes)


def test_a_repeat_rule_reads_as_a_sentence():
    from addons.whatsapp.campaigns_page import rule_words
    assert rule_words({"freq": "daily", "time": "10:00"}) == "Every day at 10:00"
    assert rule_words({"freq": "weekly", "time": "10:00", "days": ["mon"]}) == "Every Monday at 10:00"
    assert rule_words({"freq": "weekly", "time": "09:30", "days": ["mon", "thu"]}) == "Every Monday and Thursday at 09:30"
    assert rule_words({"freq": "weekly", "time": "09:30", "days": ["mon", "wed", "fri"]}) == "Every Monday, Wednesday and Friday at 09:30"
    assert rule_words({"freq": "monthly", "time": "10:00", "day": 1, "until": "2027-03-31"}) == "On day 1 of every month at 10:00, until 2027-03-31"
    assert rule_words(None) == ""


def test_choosing_repeat_shows_how_often_and_changes_the_button(campaigns):
    assert campaigns.repeat_box.isHidden() and campaigns.send_btn.text() == "Send"
    campaigns.when_combo.setCurrentIndex(campaigns.when_combo.findData("repeat"))
    assert not campaigns.repeat_box.isHidden() and campaigns.send_btn.text() == "Start repeating"
    assert not campaigns.days_row.isHidden() and campaigns.month_row.isHidden()
    campaigns.freq.setCurrentIndex(campaigns.freq.findData("monthly"))
    assert campaigns.days_row.isHidden() and not campaigns.month_row.isHidden()


def test_the_rule_on_screen_is_what_would_be_saved(campaigns):
    assert campaigns.rule() is None
    campaigns.when_combo.setCurrentIndex(campaigns.when_combo.findData("repeat"))
    campaigns.day_boxes["thu"].setChecked(True)
    campaigns.until_on.setChecked(True)
    r = campaigns.rule()
    assert r["freq"] == "weekly" and r["days"] == ["mon", "thu"] and r["time"] == "10:00" and r["tz"] == "Asia/Kolkata" and "until" in r


def test_a_weekly_repeat_needs_a_day(campaigns):
    campaigns.when_combo.setCurrentIndex(campaigns.when_combo.findData("repeat"))
    campaigns.day_boxes["mon"].setChecked(False)
    campaigns._check()
    assert "Choose the days of the week." in texts(campaigns.verdict) and campaigns.check_btn.isEnabled()


def test_a_repeat_is_checked_like_any_campaign_then_started_as_a_schedule(campaigns, calls):
    campaigns.when_combo.setCurrentIndex(campaigns.when_combo.findData("repeat"))
    campaigns._check()
    assert campaigns.send_btn.isEnabled()
    draft = campaigns._draft
    with yes():
        campaigns._send()
    route, data = [c for c in calls if c[0] == "schedules/create"][0]
    assert data["rule"]["freq"] == "weekly" and "schedule_at" not in data["config"] and data["config"]["template_name"] == "diwali_offer"
    assert ("campaigns/cancel", {"campaign_id": draft}) in calls and "campaigns/launch" not in routes(calls)
    assert "It will repeat" in campaigns.note.text() and "Every Monday at 10:00" in texts(campaigns)


def test_a_repeat_can_be_paused_and_stopped_from_the_list(campaigns, calls):
    campaigns.when_combo.setCurrentIndex(campaigns.when_combo.findData("repeat"))
    campaigns._check()
    with yes():
        campaigns._send()
    row = campaigns.repeat_col.itemAt(0).widget()
    from widgets.controls import ToggleSwitch
    row.findChildren(ToggleSwitch)[0].setChecked(False)
    assert any(r == "schedules/set_enabled" and d["enabled"] is False for r, d in calls) and "paused" in texts(campaigns)
    sc = demo_platform._state()["auto"]["schedules"][0]
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        campaigns._delete_schedule(sc)
    assert campaigns.repeat_title.isHidden()


def test_changing_the_rule_after_a_check_asks_for_another(campaigns):
    campaigns.when_combo.setCurrentIndex(campaigns.when_combo.findData("repeat"))
    campaigns._check()
    assert campaigns.send_btn.isEnabled()
    campaigns.day_boxes["fri"].setChecked(True)
    assert not campaigns.send_btn.isEnabled()


def test_a_local_time_is_sent_with_the_campaign_and_counts_as_a_change(campaigns, calls):
    campaigns._check()
    assert campaigns.send_btn.isEnabled()
    campaigns.local_on.setChecked(True)
    assert not campaigns.local_field.isHidden() and not campaigns.send_btn.isEnabled()
    campaigns.local_time.setTime(campaigns.local_time.time().__class__(9, 30))
    campaigns._check()
    data = [d for r, d in calls if r == "campaigns/create"][-1]
    assert data["local_time"] == "09:30" and data["timezone"] == "Asia/Kolkata"


def test_a_test_goes_to_your_phone_and_the_number_is_remembered(campaigns, calls):
    from addons.whatsapp import campaigns_page as CP
    campaigns.test_phone.setText("98123 45678")
    with mock.patch("core_bridge.config.save") as save:
        campaigns._send_test()
    route, data = [c for c in calls if c[0] == "campaigns/test"][0]
    assert data["to"] == "98123 45678" and data["template_name"] == "diwali_offer" and set(data["variables"]) == {"1", "2"}
    assert "arrive on 98123 45678" in campaigns.test_note.text() and campaigns.test_btn.isEnabled()
    assert campaigns.cfg["whatsapp"]["test_phone"] == "98123 45678" and save.called


def test_a_test_needs_a_phone_and_a_template_and_a_refusal_is_explained(campaigns, calls, monkeypatch):
    campaigns._send_test()
    assert "Type your own phone number" in campaigns.test_note.text() and "campaigns/test" not in routes(calls)
    from addons.whatsapp import campaigns_page as CP
    campaigns.test_phone.setText("12")
    campaigns._send_test()
    assert "not a phone number" in campaigns.test_note.text() and campaigns.test_btn.isEnabled()


# ── the tabs ─────────────────────────────────────────────────────────────────

class _FakeInbox(QWidget):
    unreadChanged = Signal(int)
    statusChanged = Signal(str, bool)
    orderRequested = Signal(dict)
    formRequested = Signal(dict)

    def __init__(self, cfg):
        super().__init__()

    def activate(self):
        pass

    def deactivate(self):
        pass


def test_automations_and_ads_are_tabs_built_only_when_opened(served):
    from addons.whatsapp import workbench as W
    with mock.patch("addons.whatsapp.inbox.InboxPage", _FakeInbox):
        wb = W.WhatsAppWorkbench({})
        assert W._tab_names()[W._AUTOMATIONS] == "Automations" and W._tab_names()[W._ADS] == "Ads"
        assert W._AUTOMATIONS not in wb._pages and W._ADS not in wb._pages
        wb.show_tab(W._AUTOMATIONS)
        assert type(wb._pages[W._AUTOMATIONS]).__name__ == "AutomationsPage"
        wb.show_tab(W._ADS)
        assert type(wb._pages[W._ADS]).__name__ == "AdsPage"
        wb.show_tab(W._SETTINGS)
        assert type(wb._pages[W._SETTINGS]).__name__ == "SettingsPage"


def test_the_automations_page_switches_between_flows_and_agents(served):
    from addons.whatsapp.automations_page import AutomationsPage
    page = AutomationsPage({})
    page.activate()
    assert list(page._sections) == ["flows"]
    page.show_section("agents")
    assert list(page._sections) == ["flows", "agents"] and page.chips.current() == "agents"
    page.deactivate()
