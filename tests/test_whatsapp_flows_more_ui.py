"""The flow builder's newer parts: files, map pins, calendar conditions, list headings, API tries, the pretend clock, results, writing a flow with
AI, the library by topic, links and QR codes, holidays, and telling Meta.

Driven with a fake worker that answers from the demo platform, so nothing opens a socket, starts a thread or spins an event loop. Rules this
file follows: no processEvents()/exec()/QEventLoop, and nothing touches the real ~/.prism.
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core_bridge  # noqa: F401,E402
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QPlainTextEdit, QPushButton  # noqa: E402

_app = QApplication.instance() or QApplication([])

from addons.whatsapp import demo, demo_flows, demo_platform, flow_model as M, flow_rules as R, readstate, ui  # noqa: E402
from addons.whatsapp.license_client import PlatformError  # noqa: E402


class _Sig:
    def __init__(self):
        self._fns = []

    def connect(self, fn):
        self._fns.append(fn)

    def emit(self, *a):
        for fn in list(self._fns):
            fn(*a)


def _worker(calls):
    class W:
        def __init__(self, route, data=None):
            self.route, self.data = route, dict(data or {})
            self.done, self.failed = _Sig(), _Sig()

        def start(self):
            calls.append((self.route, self.data))
            try:
                reply = demo_platform.handle(self.route, self.data)
            except PlatformError as e:
                self.failed.emit(str(e), dict(e.detail, reason=e.reason))
            else:
                self.done.emit(reply)
    return W


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="prism-wa-flows-more-")
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


# ── the plain-data model, with the newer steps ───────────────────────────────

def test_the_add_menu_groups_every_kind_once():
    groups = M.step_groups()
    kinds = [k for _g, ks in groups for k in ks]
    assert sorted(kinds) == sorted(k for k, _n, _h in M.step_types()) and len(kinds) == len(set(kinds)) == 23
    assert len(groups) == 7


@pytest.mark.parametrize("kind,expect", [("media", "Picture"), ("send_location", "Send a location"), ("location_request", "Ask for their location"),
                                         ("webhook", "https://"), ("capi_event", "Lead")])
def test_each_newer_step_starts_valid_enough_to_read_and_says_what_it_does(kind, expect):
    node = M.new_node(kind)
    assert node["type"] == kind and expect in M.describe_step(node) + M.type_name(kind) + (node.get("url") or "")


def test_the_words_for_a_file_step_say_its_kind_and_what_is_under_it():
    assert M.describe_step({"type": "media", "kind": "document", "caption": "Our rate card"}) == "Document — Our rate card"
    assert M.describe_step({"type": "media", "kind": "audio"}) == "Voice note"
    assert M.describe_step({"type": "send_location", "name": "Our showroom"}) == "Our showroom"
    assert M.describe_step({"type": "webhook", "url": "https://hook.example.com/x"}) == "hook.example.com/x"


def sectioned():
    return {"entry": "m", "order": ["m", "a", "b", "z"], "nodes": {
        "m": {"type": "list", "text": "Pick", "button_label": "Choose", "sections": [
            {"title": "One", "rows": [{"id": "r1", "title": "A", "next": "a"}]}, {"title": "Two", "rows": [{"id": "r2", "title": "B", "next": "b"}]}]},
        "a": {"type": "end"}, "b": {"type": "end"}, "z": {"type": "end"}}}


def test_a_list_with_headings_is_followed_into_each_of_its_rows():
    assert sorted(M.targets_of(sectioned()["nodes"]["m"])) == ["a", "b"]
    assert M.order_of({"entry": "m", "nodes": sectioned()["nodes"]})[:3] == ["m", "a", "b"]


def test_renaming_a_step_changes_the_rows_under_a_heading_too():
    g = sectioned()
    M.rename_node(g, "b", "bee")
    assert g["nodes"]["m"]["sections"][1]["rows"][0]["next"] == "bee"


def test_removing_a_step_leaves_no_row_under_a_heading_pointing_at_it():
    g = sectioned()
    M.remove_node(g, "a")
    assert g["nodes"]["m"]["sections"][0]["rows"][0]["next"] is None
    assert "next" not in M.clean_for_save(g)["nodes"]["m"]["sections"][0]["rows"][0]


def test_a_list_with_headings_counts_its_rows_across_them():
    assert [r["id"] for r in M.list_rows(sectioned()["nodes"]["m"])] == ["r1", "r2"]
    assert [r["id"] for r in M.list_rows({"rows": [{"id": "x"}]})] == ["x"]


# ── conditions on the day, the date and the time ─────────────────────────────

def rule(**kw):
    return {"field": "message", "op": "contains", "value": "", "next": None, **kw}


def test_a_weekday_condition_is_seven_buttons_and_stores_the_chosen_days():
    r = rule(field="weekday", op="in", value="sat,sun")
    ed = R.RuleEditor(r)
    assert ed.days.isHidden() is False and ed.value.isHidden() and [k for k, b in ed.day_buttons.items() if b.isChecked()] == ["sat", "sun"]
    ed.day_buttons["mon"].setChecked(True)
    assert r["value"] == "mon,sat,sun" and r["field"] == "weekday" and r["op"] == "in"


def test_choosing_the_day_of_the_week_starts_a_fresh_condition_with_no_days_chosen():
    r = rule(value="hello")
    ed = R.RuleEditor(r)
    ed.field.setCurrentIndex(ed.field.findData("weekday"))
    ed.field.activated.emit(ed.field.currentIndex())
    assert r["field"] == "weekday" and r["op"] == "in" and r["value"] == "" and ed.op.count() == 2


def test_a_date_condition_takes_a_day_or_today_and_two_days_for_between():
    r = rule(field="date", op="gt", value="2026-11-01")
    ed = R.RuleEditor(r)
    assert not ed.date_a.isHidden() and ed.date_b.isHidden()
    ed.date_a.today.setChecked(True)
    assert r["value"] == "today"
    ed.op.setCurrentIndex(ed.op.findData("between"))
    ed.op.activated.emit(ed.op.currentIndex())
    assert not ed.date_b.isHidden() and r["op"] == "between" and r["value"].startswith("today..") and len(r["value"].split("..")) == 2


def test_a_time_condition_is_a_clock_and_stores_hours_and_minutes():
    r = rule(field="time", op="between", value="09:30..18:00")
    ed = R.RuleEditor(r)
    assert ed.time_a.value() == "09:30" and ed.time_b.value() == "18:00" and not ed.time_b.isHidden()
    from PySide6.QtCore import QTime
    ed.time_b.setTime(QTime(20, 15))
    assert r["value"] == "09:30..20:15"


def test_a_holiday_condition_has_nothing_to_fill_in():
    r = rule(field="holiday", op="yes")
    ed = R.RuleEditor(r)
    assert ed.value.isHidden() and ed.days.isHidden() and ed.date_a.isHidden() and ed.time_a.isHidden()
    ed.op.setCurrentIndex(ed.op.findData("no"))
    ed.op.activated.emit(ed.op.currentIndex())
    assert r["op"] == "no" and r["value"] == ""


def test_an_attribute_condition_still_asks_for_the_name_and_the_value():
    r = rule(field="attr:City", op="eq", value="Surat")
    ed = R.RuleEditor(r)
    assert not ed.name.isHidden() and ed.name.text() == "City" and ed.value.text() == "Surat"
    ed.name.setText("Town")
    assert r["field"] == "attr:Town"


def test_opening_a_condition_changes_nothing_in_it():
    r = rule(field="weekday", op="ne", value="sun")
    before = copy.deepcopy(r)
    R.RuleEditor(r)
    assert r == before


# ── the step cards ───────────────────────────────────────────────────────────

class Ctx:
    def __init__(self, g):
        self.g = g

    def labels(self):
        return {nid: M.describe_step(self.g["nodes"][nid]) for nid in M.order_of(self.g)}

    def entry(self):
        return self.g.get("entry")

    def templates(self):
        return []

    def agents(self):
        return []

    def flows(self):
        return []

    def forms(self):
        return [{"id": "f1", "name": "Walls enquiry"}, {"id": "f2", "name": "Booking"}]

    def products(self):
        return [{"retailer_id": "wall-6", "name": "Wall panel"}, {"retailer_id": "gate-1", "name": "Main gate"}]


def card(kind, node=None):
    from addons.whatsapp.flow_steps import StepCard
    g = {"entry": "s1", "nodes": {"s1": node or M.new_node(kind), "t": {"type": "end"}}}
    c = StepCard("s1", g["nodes"]["s1"], Ctx(g))
    c.heard = []
    for sig in ("changed", "shape"):
        getattr(c, sig).connect(lambda *a, s=sig: c.heard.append(s))
    return c, g


def test_a_file_step_follows_the_kind_of_file_and_hides_the_words_for_a_voice_note():
    c, g = card("media")
    kinds = next(x for x in c.findChildren(QComboBox) if x.findData("audio") >= 0)
    assert not c.caption_box.isHidden()
    kinds.setCurrentIndex(kinds.findData("audio"))
    kinds.activated.emit(kinds.currentIndex())
    assert g["nodes"]["s1"]["kind"] == "audio" and c.caption_box.isHidden() and "caption" not in g["nodes"]["s1"] and c.asset.kinds == ("audio",)


def test_choosing_a_file_in_the_step_keeps_its_id_and_takes_its_kind():
    c, g = card("media")
    c.asset.set_asset({"id": "11111111-1111-1111-1111-111111111111", "kind": "video", "filename": "tour.mp4", "size": 1000})
    c.asset.changed.emit()
    assert g["nodes"]["s1"]["asset_id"] == "11111111-1111-1111-1111-111111111111" and g["nodes"]["s1"]["kind"] == "video"
    assert c.heard and "changed" in c.heard


def test_a_map_pin_step_splits_what_google_maps_copies_and_ignores_half_a_number():
    c, g = card("send_location")
    from PySide6.QtWidgets import QLineEdit
    lat, lng = [e for e in c.findChildren(QLineEdit) if e.accessibleName() in ("Latitude", "Longitude")]
    lat.setText("22.3072, 73.1812")
    assert (g["nodes"]["s1"]["latitude"], g["nodes"]["s1"]["longitude"]) == (22.3072, 73.1812)
    lat.setText("22.")
    assert g["nodes"]["s1"]["latitude"] is None
    lat.setText("not a number")
    assert g["nodes"]["s1"]["latitude"] is None


def test_asking_for_a_location_has_a_next_a_fallback_and_a_timeout():
    c, g = card("location_request")
    assert [k for _c, k in c.targets] == ["next", "fallback_next", "timeout_next"]


def test_telling_another_system_posts_by_default_and_reads_headers_from_lines():
    c, g = card("webhook")
    assert g["nodes"]["s1"]["method"] == "POST"
    edits = c.findChildren(QPlainTextEdit)
    edits[0].setPlainText("X-Key: abc\nbad line")
    assert g["nodes"]["s1"]["headers"] == {"X-Key": "abc"}
    edits[1].setPlainText('{"n": "{{name}}"}')
    assert g["nodes"]["s1"]["body"] == '{"n": "{{name}}"}'


def test_telling_meta_chooses_an_event_a_worth_and_a_currency():
    from PySide6.QtWidgets import QLineEdit
    c, g = card("capi_event")
    event = next(x for x in c.findChildren(QComboBox) if x.findData("Purchase") >= 0)
    event.setCurrentIndex(event.findData("Purchase"))
    event.activated.emit(event.currentIndex())
    assert g["nodes"]["s1"]["event"] == "Purchase"
    worth = next(e for e in c.findChildren(QLineEdit) if e.accessibleName() == "Worth")
    worth.setText("25000")
    assert g["nodes"]["s1"]["value"] == "25000"
    worth.setText("")
    assert "value" not in g["nodes"]["s1"]


def test_showing_products_offers_one_a_list_or_the_whole_catalogue_and_shows_only_what_fits():
    c, g = card("send_products")
    node = g["nodes"]["s1"]
    mode = next(x for x in c.findChildren(QComboBox) if x.findData("products") >= 0)
    assert node["mode"] == "catalog" and c.product_box.parentWidget().isHidden() and c.list_field.isHidden()
    mode.setCurrentIndex(mode.findData("product"))
    mode.activated.emit(mode.currentIndex())
    assert node["mode"] == "product" and not c.product_box.parentWidget().isHidden() and c.list_field.isHidden() and c.product_one.count() == 3
    c.product_one.setCurrentIndex(c.product_one.findData("gate-1"))
    c.product_one.activated.emit(c.product_one.currentIndex())
    assert node["retailer_id"] == "gate-1"
    mode.setCurrentIndex(mode.findData("products"))
    mode.activated.emit(mode.currentIndex())
    assert not c.list_field.isHidden() and c.product_box.parentWidget().isHidden()
    c.list_box.setPlainText("wall-6" + chr(10) + chr(10) + " gate-1 " + chr(10))
    assert node["retailer_ids"] == ["wall-6", "gate-1"]
    assert [k for _c, k in c.targets] == ["next"]


def test_sending_a_form_lists_the_published_forms_and_keeps_the_words_and_button():
    from PySide6.QtWidgets import QLineEdit
    c, g = card("send_form")
    node = g["nodes"]["s1"]
    assert c.form_combo.count() == 3 and node["button"] == "Open form"
    c.form_combo.setCurrentIndex(c.form_combo.findData("f2"))
    c.form_combo.activated.emit(c.form_combo.currentIndex())
    assert node["form_id"] == "f2"
    button = next(e for e in c.findChildren(QLineEdit) if e.accessibleName() == "Button words")
    button.setText("Fill in")
    assert node["button"] == "Fill in"


def test_a_form_that_is_no_longer_published_is_still_shown_so_the_problem_can_be_seen():
    c, g = card("send_form", {"type": "send_form", "form_id": "gone", "text": "", "button": "Open"})
    assert c.form_combo.currentData() == "gone" and "not published" in c.form_combo.currentText()


def test_asking_for_payment_says_what_to_do_when_there_is_no_cart():
    c, g = card("request_payment")
    box = c.findChildren(QPlainTextEdit)[0]
    box.setPlainText("Send me your cart first.")
    assert g["nodes"]["s1"]["empty_text"] == "Send me your cart first." and [k for _c, k in c.targets] == ["next"]


def test_the_selling_steps_have_their_own_group_in_the_menu_and_a_line_of_words_on_the_list():
    names = dict((g, ks) for g, ks in M.step_groups())
    assert names["Sell"] == ["send_products", "send_form", "request_payment"]
    assert M.describe_step({"type": "send_products", "mode": "products", "retailer_ids": ["a", "b"]}) == "2 products"
    assert M.describe_step({"type": "send_products", "mode": "catalog"}) == "The whole catalogue"
    assert M.describe_step({"type": "request_payment"}) == "Ask for payment"


def test_turning_on_headings_moves_the_rows_under_one_and_turning_them_off_brings_them_back():
    c, g = card("list")
    node = g["nodes"]["s1"]
    c.rows[0]._add()
    assert len(node["rows"]) == 2
    c.sections_toggle.setChecked(True)
    assert "rows" not in node and len(node["sections"]) == 1 and len(node["sections"][0]["rows"]) == 2
    c.sections_toggle.setChecked(False)
    assert "sections" not in node and len(node["rows"]) == 2


def test_headings_share_the_ten_rows_a_list_may_have():
    c, g = card("list")
    node = g["nodes"]["s1"]
    c.sections_toggle.setChecked(True)
    for _ in range(12):
        c.list_rows[0]._add()
    assert len(M.list_rows(node)) == 10 and c.list_rows[0].add_btn.isHidden()
    assert c.add_section_btn.isHidden()
    c._remove_section(node["sections"][0]) if len(node["sections"]) > 1 else None
    assert len(node["sections"]) == 1                                                  # the last heading is never removed


def test_a_second_heading_starts_with_one_empty_choice_and_can_go_again():
    c, g = card("list")
    node = g["nodes"]["s1"]
    c.sections_toggle.setChecked(True)
    c._add_section()
    assert len(node["sections"]) == 2 and len(node["sections"][1]["rows"]) == 1
    c._remove_section(node["sections"][1])
    assert len(node["sections"]) == 1


def test_trying_an_api_call_shows_the_answer_and_what_would_be_kept(served):
    c, g = card("api_request")
    g["nodes"]["s1"].update(url="https://crm.example.com/c", save={"city": "customer.city"})
    c._try_call()
    assert routes(served) == ["flows/test_request"]
    texts = " | ".join(lab.text() for lab in c.findChildren(QLabel))
    assert "It answered 200" in texts and "city = Surat" in texts and c.api_test_btn.isEnabled()


def test_trying_an_api_call_to_a_private_address_says_why_in_words(served):
    c, g = card("api_request")
    g["nodes"]["s1"]["url"] = "https://localhost/x"
    c._try_call()
    assert "cannot be called" in c.api_result.text()


# ── the demo platform's flow checker and walker ──────────────────────────────

def test_the_checker_asks_for_a_real_file_and_a_pin_and_a_secure_address():
    g = {"entry": "a", "nodes": {"a": {"type": "media", "kind": "image", "asset_id": "", "next": "b"}, "b": {"type": "send_location", "latitude": None, "longitude": None, "next": "c"},
                                 "c": {"type": "webhook", "url": "http://x.example.com", "next": "d"}, "d": {"type": "capi_event", "event": "Nope"}}}
    errors = {i["code"] for i in demo_flows.check_flow(g, {"type": "first_message"}) if i["severity"] == "error"}
    assert errors == {"bad_media", "bad_location", "bad_request", "bad_event"}


def test_an_example_file_in_a_ready_made_flow_cannot_be_published_until_replaced():
    item = next(i for i in demo_flows.LIBRARY if i["key"] == "catalogue_on_request")
    codes = {i["code"] for i in demo_flows.check_flow(item["graph"], item["trigger"])}
    assert "unknown_asset" in codes and item["needs_files"]


def test_every_demo_library_flow_passes_the_checker_except_for_its_example_files():
    for item in demo_flows.LIBRARY:
        errors = [i for i in demo_flows.check_flow(item["graph"], item["trigger"]) if i["severity"] == "error" and i["code"] != "unknown_asset"]
        assert errors == [], (item["key"], errors)


def walk(graph, inputs=("hi",), **kw):
    return demo_flows.walk_flow(graph, list(inputs), **kw)


def said(result):
    return [t.get("text") for t in result["transcript"] if t["from"] == "bot"]


def clock(day, hour=10):
    return datetime(2026, 11, day, hour, 0, tzinfo=demo_flows.IST)


def test_a_condition_on_the_day_sends_a_sunday_customer_a_different_way():
    g = {"entry": "c", "nodes": {"c": {"type": "condition", "rules": [{"field": "weekday", "op": "in", "value": "sun", "next": "closed"}], "else": "open"},
                                 "closed": {"type": "send_text", "text": "Closed today"}, "open": {"type": "send_text", "text": "Open today"}}}
    assert clock(1).weekday() == 6 and said(walk(g, local=clock(1))) == ["Closed today"]        # 1 Nov 2026 is a Sunday
    assert clock(2).weekday() == 0 and said(walk(g, local=clock(2))) == ["Open today"]


def test_a_condition_on_a_holiday_reads_the_holidays_it_is_given():
    g = {"entry": "c", "nodes": {"c": {"type": "condition", "rules": [{"field": "holiday", "op": "yes", "next": "yes"}], "else": "no"},
                                 "yes": {"type": "send_text", "text": "Holiday"}, "no": {"type": "send_text", "text": "Working day"}}}
    assert said(walk(g, local=clock(12), holidays=["2026-11-12"])) == ["Holiday"]
    assert said(walk(g, local=clock(13), holidays=["2026-11-12"])) == ["Working day"]


def test_a_condition_on_the_time_of_day_uses_the_pretend_clock():
    g = {"entry": "c", "nodes": {"c": {"type": "condition", "rules": [{"field": "time", "op": "between", "value": "09:00..18:00", "next": "in"}], "else": "out"},
                                 "in": {"type": "send_text", "text": "In hours"}, "out": {"type": "send_text", "text": "After hours"}}}
    assert said(walk(g, local=clock(3, 10))) == ["In hours"] and said(walk(g, local=clock(3, 21))) == ["After hours"]


def test_asking_for_a_location_waits_for_a_pin_and_keeps_where_it_is():
    g = {"entry": "a", "nodes": {"a": {"type": "location_request", "text": "Share your pin", "next": "b"}, "b": {"type": "send_text", "text": "Got {{var.location_lat}}"}}}
    out = walk(g, ["hi", "words not a pin"])
    assert out["state"] == "waiting" and out["waiting"] == "location_request"
    out = walk(g, ["hi", {"text": "", "location": {"latitude": 22.3, "longitude": 73.1}}])
    assert said(out)[-1] == "Got 22.3" and out["state"] == "done"


def test_a_file_and_a_pin_are_shown_in_what_the_bot_sent():
    g = {"entry": "a", "nodes": {"a": {"type": "media", "kind": "image", "asset_id": "11111111-1111-1111-1111-111111111111", "caption": "Hi {{first_name}}", "next": "b"},
                                 "b": {"type": "send_location", "latitude": 22.3, "longitude": 73.1, "name": "Showroom", "next": None}}}
    items = [t for t in walk(g, name="Asha Patel")["transcript"] if t["from"] == "bot"]
    assert items[0]["kind"] == "media" and items[0]["text"] == "Hi Asha" and items[1]["kind"] == "location" and items[1]["name"] == "Showroom"


def test_a_list_with_headings_is_walked_by_the_row_a_customer_picks():
    out = walk(sectioned(), ["hi", "B"])
    assert out["state"] == "done" and out["transcript"][1]["sections"][1]["title"] == "Two"


def test_the_pretend_clock_is_refused_when_it_makes_no_sense():
    with pytest.raises(PlatformError):
        demo_flows.test_route({"graph": sectioned(), "trigger": {"type": "first_message"}, "inputs": ["hi"], "local": "tomorrow-ish"})


def test_results_for_an_unpublished_flow_are_empty_and_for_a_published_one_fall_step_by_step(served):
    fid = demo_platform.handle("flows/from_library", {"key": "lead_capture"})["flow_id"]
    empty = demo_platform.handle("flows/analytics", {"flow_id": fid})
    assert empty["totals"]["started"] == 0 and empty["days"] == []
    demo_platform.handle("flows/publish", {"flow_id": fid})
    full = demo_platform.handle("flows/analytics", {"flow_id": fid})
    assert full["totals"]["started"] > 0 and len(full["days"]) == 30
    reached = [n["reached"] for n in full["nodes"]]
    assert reached == sorted(reached, reverse=True) and full["nodes"][0]["node"] == "greet"
    assert demo_platform.handle("flows/analytics", {"flow_id": fid}) == full                  # the same flow shows the same numbers


def test_writing_a_flow_with_ai_needs_a_real_description_and_returns_a_checked_draft():
    with pytest.raises(PlatformError):
        demo_platform.handle("flows/generate", {"description": "too short"})
    out = demo_platform.handle("flows/generate", {"description": "Book an appointment for a site visit and ask the day"})
    assert out["valid"] and out["graph"]["entry"] == "greet" and out["trigger"]["type"] == "keyword"


def test_the_conversions_api_card_needs_a_dataset_before_it_will_test(served):
    assert demo_platform.handle("capi/get", {})["settings"] == {"dataset_id": "", "test_code": "", "enabled": False}
    with pytest.raises(PlatformError):
        demo_platform.handle("capi/test", {})
    with pytest.raises(PlatformError):
        demo_platform.handle("capi/save", {"dataset_id": "abc"})
    demo_platform.handle("capi/save", {"dataset_id": "12345678", "test_code": "TEST1"})
    assert demo_platform.handle("capi/test", {})["events_received"] == 1


# ── the editor ───────────────────────────────────────────────────────────────

@pytest.fixture
def flows_section(served):
    from addons.whatsapp import flows_page as FP
    sec = FP.FlowsSection({})
    sec.activate()
    yield sec


def test_the_add_menu_has_seven_groups_and_each_step_in_one(flows_section):
    flows_section._blank()
    menu = flows_section.editor.add_menu()
    groups = [a for a in menu.actions() if a.menu() is not None]
    assert len(groups) == 7 and sum(len(a.menu().actions()) for a in groups) == 23


def test_adding_a_step_from_the_menu_builds_its_card(flows_section):
    flows_section._blank()
    ed = flows_section.editor
    for kind in ("media", "send_location", "location_request", "webhook", "capi_event"):
        ed.add_step(kind)
    assert len(ed.cards) == 6 and ed._timer.isActive()
    assert {n["type"] for n in ed.graph["nodes"].values()} >= {"media", "send_location", "location_request", "webhook", "capi_event"}


def test_the_screen_asks_for_the_holidays_once_when_it_opens(served):
    from addons.whatsapp import flows_page as FP
    demo_platform.handle("inbox/settings/save", {"settings": {"holidays": [{"date": "2026-11-12", "name": "Diwali"}]}})
    sec = FP.FlowsSection({})
    sec.activate()
    assert routes(served).count("inbox/settings/get") == 1 and sec.holidays == [{"date": "2026-11-12", "name": "Diwali"}]


def test_the_pretend_panel_sends_the_clock_the_open_hours_and_the_holidays(flows_section, served):
    flows_section.holidays = [{"date": "2026-11-12", "name": "Diwali"}]
    flows_section._blank()
    ed = flows_section.editor
    ed.graph["nodes"]["welcome"]["text"] = "Hello"
    console = ed.console
    console._toggle_pretend()
    assert not console.pretend.isHidden() and "1 holidays" in console.holiday_note.text()
    console.use_clock.setChecked(True)
    console.open_now.setChecked(False)
    del served[:]
    console._send("hi")
    sent = served[0][1]
    assert served[0][0] == "flows/test" and sent["open_now"] is False and sent["holidays"] == ["2026-11-12"] and len(sent["local"]) == 19


def test_without_the_pretend_clock_the_real_one_is_used(flows_section, served):
    flows_section._blank()
    ed = flows_section.editor
    ed.graph["nodes"]["welcome"]["text"] = "Hello"
    del served[:]
    ed.console._send("hi")
    assert "local" not in served[0][1] and served[0][1]["open_now"] is True


def test_a_location_request_offers_a_share_button_and_the_pin_goes_back_to_the_flow(flows_section, served):
    flows_section._blank()
    ed = flows_section.editor
    ed.graph["nodes"] = {"welcome": {"type": "location_request", "text": "Share your pin", "next": "thanks"}, "thanks": {"type": "send_text", "text": "Thanks, got it."}}
    ed.console._send("hi")
    share = next(b for b in ed.console.findChildren(QPushButton) if b.text() == "Share a location")
    share.click()
    texts = " | ".join(lab.text() for lab in ed.console.findChildren(QLabel))
    assert "Shared a location" in texts and "Thanks, got it." in texts and isinstance(ed.console.inputs[-1], dict)


def test_files_and_pins_the_bot_sends_are_shown_as_bubbles(flows_section, served):
    flows_section._blank()
    ed = flows_section.editor
    ed.graph["nodes"] = {"welcome": {"type": "media", "kind": "image", "asset_id": "11111111-1111-1111-1111-111111111111", "caption": "Our work", "next": "pin"},
                         "pin": {"type": "send_location", "latitude": 22.3, "longitude": 73.1, "name": "Showroom", "address": "Alkapuri"}}
    ed.console._send("hi")
    texts = " | ".join(lab.text() for lab in ed.console.findChildren(QLabel))
    assert "[Picture] Our work" in texts and "Map pin: Showroom Alkapuri" in texts


def test_the_results_tab_loads_only_when_it_is_opened(flows_section, served):
    fid = demo_platform.handle("flows/from_library", {"key": "lead_capture"})["flow_id"]
    demo_platform.handle("flows/publish", {"flow_id": fid})
    flows_section.open_flow(fid)
    ed = flows_section.editor
    assert "flows/analytics" not in routes(served)
    ed.view.set_current(1)
    assert routes(served).count("flows/analytics") == 1 and ed.right_stack.currentIndex() == 1
    assert ed.results.k_started.value.text() != "—"
    ed.view.set_current(0)
    assert ed.right_stack.currentIndex() == 0


def test_the_results_name_the_step_where_most_customers_stop(flows_section, served):
    from addons.whatsapp import flow_results as FR
    rows = FR.step_rows({"nodes": [{"node": "a", "kind": "buttons", "text": "x", "reached": 100, "stopped": 10, "stopped_pct": 10.0},
                                   {"node": "b", "kind": "ask", "text": "y", "reached": 90, "stopped": 45, "stopped_pct": 50.0}]})
    assert [r["node"] for r in rows] == ["a", "b"] and rows[0]["share"] == 1.0 and rows[1]["share"] == 0.9 and rows[1]["kind"] == "Ask a question"
    panel = FR.FlowResults("f1")
    panel._token = 1
    panel._shown(1, {"totals": {"started": 100, "done": 60, "handed_to_person": 20, "in_progress": 5, "completion_rate": 60.0, "avg_steps": 3.5},
                     "nodes": [{"node": "a", "kind": "buttons", "text": "x", "reached": 100, "stopped": 10, "stopped_pct": 10.0},
                               {"node": "b", "kind": "ask", "text": "y", "reached": 90, "stopped": 45, "stopped_pct": 50.0}], "days": [{"day": "2026-10-01", "runs": 4}]})
    texts = " | ".join(lab.text() for lab in panel.findChildren(QLabel))
    assert "45 stopped here (50%)" in texts and "100 reached it" in texts and panel.k_done.value.text() == "60"


def test_results_that_arrive_after_the_range_changed_are_ignored():
    from addons.whatsapp import flow_results as FR
    panel = FR.FlowResults("f1")
    panel._token = 5
    panel._shown(4, {"totals": {"started": 99}, "nodes": [], "days": []})
    assert panel.k_started.value.text() == "—"


# ── writing a flow with AI, and the library ──────────────────────────────────

def test_the_ai_dialog_waits_for_a_real_description(served):
    from addons.whatsapp.flow_ai_dialog import AIFlowDialog
    d = AIFlowDialog()
    assert not d.write_btn.isEnabled()
    d.what.setPlainText("book it")
    assert not d.write_btn.isEnabled()
    d.what.setPlainText("When someone asks for a quote, ask the city and pass them on")
    assert d.write_btn.isEnabled() and not d.use_btn.isEnabled()


def test_the_ai_dialog_shows_the_draft_and_its_checks_and_hands_it_back(served):
    from addons.whatsapp.flow_ai_dialog import AIFlowDialog
    d = AIFlowDialog()
    d.what.setPlainText("Book an appointment for a site visit and ask which day suits")
    d._write()
    assert routes(served) == ["flows/generate"] and served[0][1]["language"] == "English"
    texts = " | ".join(lab.text() for lab in d.draft_box.findChildren(QLabel))
    assert "Book an appointment" in texts and "It passes the checks." in texts and d.use_btn.isEnabled()
    d._use()
    assert d.result["graph"]["entry"] == "greet" and d.result["name"] == "Book an appointment"


def test_the_ai_dialog_says_why_when_the_writer_is_not_available(monkeypatch):
    from addons.whatsapp.flow_ai_dialog import AIFlowDialog

    class Down:
        def __init__(self, route, data=None):
            self.done, self.failed = _Sig(), _Sig()

        def start(self):
            self.failed.emit("AI writing is not set up on this server (WA_LLM_API_KEY).", {})
    monkeypatch.setattr(ui, "PlatformWorker", Down)
    d = AIFlowDialog()
    d.what.setPlainText("Collect the name and city of everyone who writes in")
    d._write()
    assert "not set up" in d.note.text() and d.write_btn.isEnabled() and not d.use_btn.isEnabled()


def test_a_new_flow_can_be_written_with_ai_and_opens_as_a_draft(flows_section, served):
    from addons.whatsapp import flows_page as FP
    from addons.whatsapp.flow_ai_dialog import AIFlowDialog

    def fake_exec(self):
        self.what.setPlainText("Collect a quote request: type of work, area and city")
        self._write()
        self._use()
        return 1
    with mock.patch.object(AIFlowDialog, "exec", fake_exec):
        flows_section._write_with_ai()
    assert "flows/create" in routes(served) and flows_section.editor.flow["name"] == "Get a quote" and flows_section.editor.version == 0
    assert isinstance(FP.AIFlowDialog, type)


def test_the_library_is_filtered_by_topic_and_by_a_word(served):
    from addons.whatsapp import flows_page as FP
    d = FP.LibraryDialog(demo_flows.get_library()["library"])
    allk = [i["key"] for i in d.shown()]
    assert len(allk) == len(demo_flows.LIBRARY) and "lead_capture" in allk
    d.chips.changed.emit("Retail")
    assert [i["key"] for i in d.shown()] == ["catalogue_on_request"]
    d.chips.changed.emit("")
    d.search.setText("clock")
    assert [i["key"] for i in d.shown()] == ["business_hours_router"]
    d.search.setText("zzzz")
    assert d.shown() == [] and "Nothing matches" in " ".join(lab.text() for lab in d.findChildren(QLabel))


def test_a_library_flow_that_needs_files_or_edits_says_so(served):
    from addons.whatsapp import flows_page as FP
    d = FP.LibraryDialog(demo_flows.get_library()["library"])
    pills = [p.text() for p in d.findChildren(__import__("widgets.controls", fromlist=["Pill"]).Pill)]
    assert "You add your own files" in pills and "Change the details" in pills


# ── a link and a QR code for a keyword ───────────────────────────────────────

def test_the_trigger_dialog_offers_a_link_only_for_a_keyword_that_has_a_word(served):
    from addons.whatsapp import flows_page as FP
    d = FP.TriggerDialog({"type": "keyword", "match": "exact", "keywords": ["price"]})
    assert not d.link_box.isHidden()
    d.keywords.setText("")
    assert d.link_box.isHidden()
    d.keywords.setText("quote, rate")
    assert not d.link_box.isHidden() and d._words() == ["quote", "rate"]
    d.kind.setCurrentIndex(d.kind.findData("first_message"))
    d.kind.activated.emit(d.kind.currentIndex())
    assert d.link_box.isHidden()


def test_the_link_dialog_puts_the_word_in_a_chat_link_and_draws_its_code(served):
    from addons.whatsapp.flow_link_dialog import FlowLinkDialog
    d = FlowLinkDialog(["price", "rate"])
    assert routes(served) == ["numbers/list"]
    link = d.link_edit.text()
    assert link.startswith("https://wa.me/") and link.endswith("?text=price") and d.qr_label.pixmap() is not None and d.copy_btn.isEnabled()
    d.word.setCurrentIndex(1)
    assert d.link_edit.text().endswith("?text=rate")


def test_the_link_dialog_says_so_when_no_number_is_connected(monkeypatch):
    from addons.whatsapp.flow_link_dialog import FlowLinkDialog

    class Empty:
        def __init__(self, route, data=None):
            self.done, self.failed = _Sig(), _Sig()

        def start(self):
            self.done.emit({"numbers": []})
    monkeypatch.setattr(ui, "PlatformWorker", Empty)
    d = FlowLinkDialog(["hi"])
    assert d.link_edit.text() == "" and not d.copy_btn.isEnabled() and "No number" in d.note.text()


# ── holidays ─────────────────────────────────────────────────────────────────

def test_holidays_are_kept_once_each_in_date_order_and_at_most_sixty():
    from addons.whatsapp import holidays as H
    rows = [{"date": "2026-11-12", "name": "Diwali"}, {"date": "2026-01-26", "name": ""}, {"date": "2026-11-12", "name": "again"}, {"date": "", "name": "x"}]
    assert H.clean(rows) == [{"date": "2026-01-26"}, {"date": "2026-11-12", "name": "Diwali"}]
    assert len(H.clean([{"date": "2026-%02d-%02d" % (1 + i // 28, 1 + i % 28)} for i in range(70)])) == 60


def test_the_national_days_still_to_come_are_the_ones_offered():
    from addons.whatsapp import holidays as H
    assert [d["date"] for d in H.national_days(date(2026, 3, 1))] == ["2026-08-15", "2026-10-02"]
    assert [d["date"] for d in H.national_days(date(2026, 10, 19))] == ["2027-01-26", "2027-08-15", "2027-10-02"]
    assert [d["date"] for d in H.national_days(date(2026, 1, 1))] == ["2026-01-26", "2026-08-15", "2026-10-02"]


def test_the_holiday_editor_adds_removes_and_reports_every_change():
    from addons.whatsapp import holidays as H
    ed = H.HolidaysEditor()
    heard = []
    ed.edited.connect(lambda: heard.append(1))
    assert not ed.empty.isHidden()
    ed.set_value([{"date": "2026-11-12", "name": "Diwali"}])
    assert ed.value() == [{"date": "2026-11-12", "name": "Diwali"}] and ed.empty.isHidden() and not heard
    ed.add("2026-12-25", "Christmas")
    assert [d["date"] for d in ed.value()] == ["2026-11-12", "2026-12-25"] and heard
    ed._rows[0].removed.emit(ed._rows[0])
    assert ed.value() == [{"date": "2026-12-25", "name": "Christmas"}]
    ed._national()
    assert len(ed.value()) == 4


def test_the_team_settings_load_and_save_the_holidays(served):
    from addons.whatsapp.settings_team import TeamSection
    demo_platform.handle("inbox/settings/save", {"settings": {"holidays": [{"date": "2026-11-12", "name": "Diwali"}]}})
    sec = TeamSection()
    sec.activate()
    assert sec.holidays.value() == [{"date": "2026-11-12", "name": "Diwali"}]
    sec.holidays.add("2026-12-25", "Christmas")
    del served[:]
    sec._save_rules()
    saved = next(d for r, d in served if r == "inbox/settings/save")
    assert [h["date"] for h in saved["settings"]["holidays"]] == ["2026-11-12", "2026-12-25"]
    assert [h["date"] for h in demo_platform.handle("inbox/settings/get", {})["settings"]["holidays"]] == ["2026-11-12", "2026-12-25"]


def test_a_holiday_that_is_not_a_date_is_refused_in_words(served):
    with pytest.raises(PlatformError) as why:
        demo_platform.handle("inbox/settings/save", {"settings": {"holidays": [{"date": "tomorrow"}]}})
    assert "date like 2026-11-12" in str(why.value)


# ── telling Meta ─────────────────────────────────────────────────────────────

def test_the_conversions_card_saves_then_sends_a_test_and_says_what_happened(served):
    from addons.whatsapp.settings_capi import CapiCard
    c = CapiCard()
    c.load()
    assert c.dataset.text() == "" and c.enabled.isChecked()
    c.dataset.setText("12ab")
    c.save()
    assert "only digits" in c.note.text() and "capi/save" not in routes(served)
    c.dataset.setText("12345678")
    c.test_code.setText("TEST42")
    c.send_test()
    assert routes(served)[-2:] == ["capi/save", "capi/test"] and "Meta received 1 test event" in c.note.text() and c.test_btn.isEnabled()


def test_the_conversions_card_explains_a_missing_test_code(served):
    from addons.whatsapp.settings_capi import CapiCard
    c = CapiCard()
    c.dataset.setText("12345678")
    c.send_test()
    assert "test code" in c.note.text().lower() and c.test_btn.isEnabled()


def test_the_developers_page_shows_the_conversions_card(served):
    from addons.whatsapp.settings_developers import DevelopersSection
    sec = DevelopersSection()
    sec.activate()
    assert "capi/get" in routes(served) and sec.capi.enabled.isChecked()
    assert isinstance(sec.capi.findChildren(QCheckBox)[0], QCheckBox)


# ── the picture of a flow ────────────────────────────────────────────────────

def small_flow():
    return {"entry": "ask", "nodes": {
        "ask": {"type": "buttons", "text": "Which?", "options": [{"id": "a", "title": "Quote", "next": "name"}, {"id": "b", "title": "Visit", "next": None}], "fallback_next": "name"},
        "name": {"type": "ask", "text": "Name?", "next": "route", "timeout_next": None},
        "route": {"type": "condition", "rules": [{"field": "weekday", "op": "in", "value": "sun", "next": "bye"}], "else": "bye"},
        "bye": {"type": "end"},
        "lonely": {"type": "send_text", "text": "Never reached"}}}


def test_every_way_out_of_a_step_is_listed_with_words_for_it():
    n = small_flow()["nodes"]
    assert [(b["label"], b["key"]) for b in M.branches(n["ask"])] == [("Quote", "next"), ("Visit", "next"), ("Something else", "fallback_next"), ("No answer", "timeout_next")]
    assert [b["label"] for b in M.branches(n["route"])] == ["Day sun", "Otherwise"]
    assert M.branches(n["bye"]) == [] and [b["key"] for b in M.branches(n["name"])] == ["next", "invalid_next", "timeout_next"]


def test_a_way_out_can_be_joined_to_a_step_and_cut_again():
    n = small_flow()["nodes"]
    visit = M.branches(n["ask"])[1]
    assert M.branch_target(visit) is None
    M.set_branch(visit, "bye")
    assert n["ask"]["options"][1]["next"] == "bye" and M.branch_target(visit) == "bye"
    M.set_branch(visit, None)
    assert M.branch_target(visit) is None


def test_every_kind_of_step_lists_only_exits_the_server_knows():
    for kind, _n, _h in M.step_types():
        exits = {b["key"] for b in M.branches(M.new_node(kind))}
        assert exits <= set(M.NEXT_KEYS), (kind, exits)
    assert [b["key"] for b in M.branches(M.new_node("api_request"))] == ["ok_next", "error_next"]
    assert M.branches(M.new_node("handoff")) == [] and M.branches(M.new_node("end")) == []


def test_steps_are_laid_out_in_columns_by_how_far_they_are_from_the_start():
    g = small_flow()
    lay = M.auto_layout(g)
    assert lay["ask"] == [0, 0] and lay["name"][0] == 300 and lay["route"][0] == 600 and lay["bye"][0] == 900
    assert lay["lonely"][0] == 1200                                                              # a step nothing leads to goes after the rest


def test_a_step_placed_by_hand_keeps_its_place_and_the_others_still_get_one():
    g = small_flow()
    g["layout"] = {"name": [50, 500], "gone": [1, 1]}
    lay = M.auto_layout(g)
    assert lay["name"] == [50, 500] and "gone" not in lay and set(lay) == set(g["nodes"])


def test_renaming_and_removing_a_step_keep_the_picture_in_step():
    g = small_flow()
    g["layout"] = {"name": [10, 20], "bye": [30, 40]}
    M.rename_node(g, "name", "who")
    assert g["layout"] == {"who": [10, 20], "bye": [30, 40]}
    M.remove_node(g, "bye")
    assert g["layout"] == {"who": [10, 20]}


def canvas(graph=None):
    from addons.whatsapp.flow_canvas import FlowCanvas
    c = FlowCanvas(graph or small_flow())
    c.heard = []
    c.edited.connect(lambda: c.heard.append("edited"))
    c.selected.connect(lambda n: c.heard.append("selected:" + n))
    return c


def test_the_picture_has_a_card_for_every_step_and_a_dot_for_every_way_out():
    c = canvas()
    assert set(c.items_) == {"ask", "name", "route", "bye", "lonely"}
    assert [len(c.items_[n].ports) for n in ("ask", "name", "route", "bye", "lonely")] == [4, 3, 2, 0, 1]
    assert c.items_["ask"].is_entry and not c.items_["name"].is_entry
    assert len(c.edges) == 5                                                   # ask to name twice, name to route, route to bye twice


def test_joining_two_steps_draws_the_line_and_cutting_it_takes_it_away():
    c = canvas()
    visit = c.items_["ask"].ports[1]
    c.join("ask", visit.branch, "bye")
    assert c.graph["nodes"]["ask"]["options"][1]["next"] == "bye" and len(c.edges) == 6 and c.heard == ["edited"]
    c.join("ask", visit.branch, "bye")                                          # the same again changes nothing
    assert c.heard == ["edited"]
    c.join("ask", visit.branch, None)
    assert c.graph["nodes"]["ask"]["options"][1]["next"] is None and len(c.edges) == 5


def test_letting_go_of_a_card_remembers_where_all_the_cards_are_but_a_click_does_not():
    c = canvas()
    c.placed(c.items_["name"])
    assert "layout" not in c.graph and c.heard == []                              # nothing moved
    c.items_["name"].setPos(123, 77)
    c.placed(c.items_["name"])
    assert c.graph["layout"]["name"] == [123, 77] and set(c.graph["layout"]) == set(c.graph["nodes"]) and c.heard == ["edited"]
    c.placed(c.items_["name"])
    assert c.heard == ["edited"]                                                  # let go again where it already is


def test_the_lines_follow_a_card_as_it_moves():
    c = canvas()
    edge = next(e for e in c.edges if e["to"] == "route")
    end = edge["item"].path().elementCount() - 1
    before = edge["item"].path().elementAt(end).x
    c.items_["route"].setPos(c.items_["route"].pos().x() + 200, c.items_["route"].pos().y())
    after = edge["item"].path().elementAt(end).x
    assert after == pytest.approx(before + 200)


def test_clicking_a_card_says_which_and_clicking_nothing_says_none():
    c = canvas()
    c.items_["name"].setSelected(True)
    c.scene_.clearSelection()
    assert c.heard == ["selected:name", "selected:"]
    c.select("route")
    assert c.current() == "route"


def test_a_step_with_a_problem_is_drawn_with_a_red_edge():
    c = canvas()
    c.set_issues([{"node": "name", "severity": "error", "message": "x"}, {"node": "bye", "severity": "warning", "message": "y"}])
    assert c.items_["name"].problem and not c.items_["bye"].problem


def test_tidy_up_forgets_where_cards_were_put_and_lays_them_out_again():
    c = canvas()
    c.graph["layout"] = {"name": [900, 900]}
    c.arrange()
    assert c.graph["layout"]["ask"] == [0, 0] and c.graph["layout"]["name"][1] != 900
    assert c.heard[-1] == "edited"


def test_the_picture_only_zooms_between_a_third_and_double():
    c = canvas()
    for _ in range(20):
        c.zoom(1.2)
    assert c.transform().m11() <= 2.0
    for _ in range(40):
        c.zoom(1 / 1.2)
    assert c.transform().m11() >= 0.3


def test_the_picture_is_drawn_without_error_for_every_kind_of_step():
    from PySide6.QtGui import QImage, QPainter
    g = {"entry": "s0", "nodes": {"s%d" % i: M.new_node(k) for i, (k, _n, _h) in enumerate(M.step_types())}}
    g["nodes"]["s0"] = {"type": "send_text", "text": "x " * 200, "next": "s1"}
    c = canvas(g)
    img = QImage(900, 700, QImage.Format_ARGB32)
    p = QPainter(img)
    c.scene_.render(p)
    p.end()
    assert len(c.items_) == 23


@pytest.fixture
def editor(flows_section):
    flows_section._blank()
    return flows_section.editor


def test_the_editor_switches_between_the_steps_and_the_picture_without_losing_anything(editor):
    editor.add_step("ask")
    editor.graph["nodes"]["welcome"]["text"] = "Hello"
    editor.mode.set_current(1)
    assert editor.left_stack.currentIndex() == 1 and editor.canvas_shown() and set(editor.canvas.items_) == set(editor.graph["nodes"])
    editor.mode.set_current(0)
    assert editor.left_stack.currentIndex() == 0 and set(editor.cards) == set(editor.graph["nodes"])
    assert editor.graph["nodes"]["welcome"]["text"] == "Hello"


def test_clicking_a_card_opens_that_step_below_the_picture_and_editing_it_edits_the_flow(editor):
    editor.mode.set_current(1)
    editor.canvas.select("welcome")
    assert list(editor.cards) == ["welcome"]
    edit = editor.cards["welcome"].findChildren(QPlainTextEdit)[0]
    edit.setPlainText("Typed in the picture")
    assert editor.graph["nodes"]["welcome"]["text"] == "Typed in the picture" and editor._timer.isActive()
    assert "Typed in the picture" in editor.canvas.items_["welcome"].toolTip()


def test_the_up_and_down_arrows_are_not_offered_in_the_picture(editor):
    editor.mode.set_current(1)
    editor.canvas.select("welcome")
    arrows = [b for b in editor.cards["welcome"].findChildren(QPushButton) if b.toolTip() in ("Move up", "Move down")]
    assert arrows == [] or all(b.isHidden() for b in arrows)


def test_adding_a_step_in_the_picture_selects_it_and_puts_it_after_the_open_one(editor):
    editor.mode.set_current(1)
    editor.canvas.select("welcome")
    editor.add_step("buttons")
    new = list(editor.graph["nodes"])[-1]
    assert new == "ask_with_buttons" and editor.canvas.current() == new and list(editor.cards) == [new] and list(editor.graph["nodes"]) == ["welcome", new]


def test_joining_in_the_picture_changes_the_open_cards_choices_and_saves(editor):
    editor.add_step("send_text")
    editor.mode.set_current(1)
    editor.canvas.select("welcome")
    port = editor.canvas.items_["welcome"].ports[0]
    editor.canvas.join("welcome", port.branch, "say_something")
    assert editor.graph["nodes"]["welcome"]["next"] == "say_something" and editor._timer.isActive()
    assert editor.cards["welcome"].targets[0][0].currentData() == "say_something"


def test_deleting_a_step_from_the_picture_removes_its_card_and_its_lines(editor):
    editor.add_step("send_text")
    editor.graph["nodes"]["welcome"]["next"] = "say_something"
    editor.mode.set_current(1)
    editor.canvas.select("say_something")
    with mock.patch.object(ui, "confirm", return_value=True):
        editor._remove("say_something")
    assert set(editor.canvas.items_) == {"welcome"} and "next" not in M.clean_for_save(editor.graph)["nodes"]["welcome"] and editor.cards == {}


def test_renaming_a_step_in_the_picture_renames_its_card_and_keeps_the_lines(editor):
    editor.add_step("send_text")
    editor.graph["nodes"]["welcome"]["next"] = "say_something"
    editor.mode.set_current(1)
    editor.canvas.select("say_something")
    card = editor.cards["say_something"]
    card.id_edit.setText("second")
    card.id_edit.editingFinished.emit()
    assert "second" in editor.graph["nodes"] and editor.graph["nodes"]["welcome"]["next"] == "second" and "second" in editor.canvas.items_


def test_where_cards_were_put_is_saved_with_the_flow(editor, served):
    editor.mode.set_current(1)
    editor.canvas.items_["welcome"].setPos(40, 60)
    editor.canvas.placed(editor.canvas.items_["welcome"])
    assert editor.payload()["graph"]["layout"]["welcome"] == [40, 60]
    del served[:]
    editor.save()
    assert served[0][0] == "flows/update" and served[0][1]["graph"]["layout"]["welcome"] == [40, 60]


def test_a_saved_layout_survives_a_reopen(flows_section, served):
    flows_section._blank()
    ed = flows_section.editor
    ed.mode.set_current(1)
    ed.canvas.items_["welcome"].setPos(11, 22)
    ed.canvas.placed(ed.canvas.items_["welcome"])
    ed.save()
    flows_section.open_flow(ed.flow["id"])
    again = flows_section.editor
    again.mode.set_current(1)
    assert again.canvas.position("welcome") == [11, 22]


def test_problems_found_on_a_save_are_marked_in_the_picture(editor):
    editor.mode.set_current(1)
    editor.show_issues([{"node": "welcome", "severity": "error", "message": "Needs its text.", "code": "bad_text"}])
    assert editor.canvas.items_["welcome"].problem
