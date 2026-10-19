"""Automatic messages: a message on a date and a drip — choosing the template and its blanks, the timing, who it would reach, saving, switching on, and what it did.

Driven with a fake worker that answers from the demo platform, so nothing opens a socket, starts a thread or spins an event loop. Rules this file follows: no
processEvents()/exec()/QEventLoop, and nothing touches the real ~/.prism.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core_bridge  # noqa: F401,E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox  # noqa: E402

_app = QApplication.instance() or QApplication([])

from addons.whatsapp import demo, demo_book, demo_platform, readstate, ui  # noqa: E402
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
    tmp = tempfile.mkdtemp(prefix="prism-wa-autos-")
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


def define_birthday():
    """A date detail with dates on two of the demo contacts: one tomorrow (India time), one the day after."""
    demo_platform.handle("attributes/define", {"key": "Birthday", "type": "date"})
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    b = demo_book._book(demo_platform._state())
    b["values"].setdefault("k1", {})["Birthday"] = (today + timedelta(days=1)).replace(year=1990).isoformat() if (today + timedelta(days=1)).month != 2 or (today + timedelta(days=1)).day != 29 else "1990-03-01"
    b["values"].setdefault("k2", {})["Birthday"] = (today + timedelta(days=2)).replace(year=1985).isoformat() if (today + timedelta(days=2)).month != 2 or (today + timedelta(days=2)).day != 29 else "1985-03-01"


@pytest.fixture
def section(served):
    from addons.whatsapp import autos_page as AU
    sec = AU.AutosSection({})
    sec.activate()
    return sec


# ── the page ─────────────────────────────────────────────────────────────────

def test_the_automations_page_has_a_third_section(served):
    from addons.whatsapp.automations_page import AutomationsPage
    page = AutomationsPage({})
    page.activate()
    page.show_section("auto")
    assert list(page._sections) == ["flows", "auto"] and type(page._sections["auto"]).__name__ == "AutosSection" and page.chips.current() == "auto"


def test_with_nothing_made_the_page_invites_a_first_one(section):
    assert section.state.title.text() == "Nothing automatic yet" and section.state.action.text() == "New"


def test_every_way_to_begin_is_offered_with_what_it_does():
    from addons.whatsapp import autos_page as AU
    keys = [k for k, *_ in AU.presets()]
    assert keys == ["birthday", "anniversary", "appointment", "payment_due", "payment_late", "welcome", "followup"]
    cfg = {k: c for k, _kind, _n, _h, c in AU.presets()}
    assert cfg["appointment"]["offset_days"] == -1 and cfg["payment_late"]["offset_days"] == 3 and cfg["birthday"]["match"] == "yearly"
    assert len(cfg["welcome"]["steps"]) == 3 and cfg["followup"]["trigger"]["type"] == "manual"


def test_words_for_the_timing_and_the_waits():
    from addons.whatsapp import autos_page as AU
    assert AU.timing_words({"offset_days": 0}) == "On the day" and AU.timing_words({"offset_days": -3}) == "3 days before" and AU.timing_words({"offset_days": 2}) == "2 days after"
    assert AU.delay_words(0) == "Right away" and AU.delay_words(2880) == "After 2 days" and AU.delay_words(180) == "After 3 hours" and AU.delay_words(95) == "After 95 minutes"


# ── a message on a date ──────────────────────────────────────────────────────

def test_beginning_a_birthday_message_shows_an_editor_that_is_not_saved_yet(section, calls):
    define_birthday()
    section.activate()
    section.start("birthday")
    ed = section.editor
    assert ed.auto["id"] is None and ed.status.text() == "Not saved yet" and not ed.on.isEnabled() and not ed.delete_btn.isVisibleTo(ed)
    assert ed.name.text() == "Birthday message" and ed.body.attribute.currentData() == "Birthday" and ed.body.when.currentData() == "on" and ed.body.match.currentData() == "yearly"
    assert "autos/create" not in routes(calls)


def test_the_timing_is_a_day_a_number_of_days_before_or_a_number_of_days_after(section):
    define_birthday()
    section.activate()
    section.start("appointment")
    b = section.editor.body
    assert b.when.currentData() == "before" and b.days.value() == 1 and b.value()["offset_days"] == -1 and b.match.currentData() == "once"
    b.when.setCurrentIndex(b.when.findData("after"))
    b.when.activated.emit(b.when.currentIndex())
    b.days.setValue(4)
    assert b.value()["offset_days"] == 4
    b.when.setCurrentIndex(b.when.findData("on"))
    b.when.activated.emit(b.when.currentIndex())
    assert b.value()["offset_days"] == 0 and b.days.isHidden()


def test_saving_makes_it_and_then_it_can_be_switched_on(section, calls):
    define_birthday()
    section.activate()
    section.start("birthday")
    ed = section.editor
    ed.body.template.combo.setCurrentIndex(ed.body.template.combo.findText("diwali_offer · en_US"))
    ed.body.template.combo.activated.emit(ed.body.template.combo.currentIndex())
    ed.save()
    assert "autos/create" in routes(calls)
    ed = section.editor
    assert ed.auto["id"] and ed.status.text() == "Off" and ed.on.isEnabled() and ed.delete_btn.isVisibleTo(ed)
    ed.on.setChecked(True)
    assert ed.auto["enabled"] and ed.status.text() == "On" and "Switched on" in ed.note.text() and "Birthday message" in texts(section)


def test_a_date_message_without_a_template_says_what_to_do(section):
    define_birthday()
    section.activate()
    section.start("birthday")
    section.editor.save()
    assert "Choose the template to send" in section.editor.note.text() and section.editor.auto["id"] is None


def test_without_a_date_detail_it_says_so_and_one_can_be_made_on_the_spot(section, calls):
    section.start("birthday")
    b = section.editor.body
    assert b.attribute.itemText(0) == "No date details yet — add one" and b.attribute.currentData() is None
    from addons.whatsapp import autos_page as AU
    with mock.patch.object(AU.NewDetailDialog, "exec", return_value=1), mock.patch.object(AU.NewDetailDialog, "key", lambda self: "Birthday"):
        b.new_detail()
    assert "attributes/define" in routes(calls) and b.attribute.currentData() == "Birthday" and "Added the detail" in section.editor.note.text()


def test_a_new_detail_needs_a_proper_name():
    from addons.whatsapp import autos_page as AU
    d = AU.NewDetailDialog()
    d.name.setText("9 lives")
    d._go()
    assert "starts with a letter" in d.error.text()
    d.name.setText("Next visit")
    assert d.key() == "Next_visit"


def test_the_preview_says_who_would_be_reached_on_the_coming_days(section):
    define_birthday()
    section.activate()
    section.start("birthday")
    b = section.editor.body
    b.preview()
    t = texts(b)
    assert "1 people" in t and "Asha Patel" in t and "Ravi Shah" in t and b.preview_btn.isEnabled()


def test_a_preview_with_nobody_says_to_check_the_dates(section):
    demo_platform.handle("attributes/define", {"key": "Birthday", "type": "date"})
    section.activate()
    section.start("birthday")
    section.editor.body.preview()
    assert "Nobody in the next seven days" in texts(section.editor.body)


def test_a_message_the_server_refuses_is_explained_and_nothing_is_lost(section):
    define_birthday()
    section.activate()
    section.start("birthday")
    ed = section.editor
    ed.body.template.combo.setCurrentIndex(ed.body.template.combo.findText("diwali_offer · en_US"))
    ed.body.template.combo.activated.emit(ed.body.template.combo.currentIndex())
    ed.body.tags.setText("a, b, c, d, e, f")
    ed.save()
    assert "up to 5 tags" in ed.note.text() and ed.dirty and ed.auto["id"] is None


def test_switching_on_with_a_template_that_is_not_approved_is_refused_and_the_switch_goes_back(section):
    define_birthday()
    section.activate()
    demo_platform.handle("autos/create", {"kind": "date", "name": "Old", "config": {"attribute": "Birthday", "template": {"name": "quotation_followup", "language": "en_US"}}})
    section.refresh_list()
    section.open_auto(section.autos[0]["id"])
    ed = section.editor
    ed.on.setChecked(True)
    assert not ed.on.isChecked() and "pending" in ed.note.text() and not ed.auto["enabled"]


def test_an_edit_is_saved_with_the_button_and_the_button_says_when_there_is_nothing_to_save(section, calls):
    define_birthday()
    section.activate()
    demo_platform.handle("autos/create", {"kind": "date", "name": "Birthday", "config": {"attribute": "Birthday", "template": {"name": "diwali_offer", "language": "en_US"}}})
    section.refresh_list()
    section.open_auto(section.autos[0]["id"])
    ed = section.editor
    assert not ed.save_btn.isEnabled()
    ed.name.setText("Birthdays")
    assert ed.save_btn.isEnabled() and ed.dirty
    ed.save()
    assert calls[-2][0] == "autos/update" and calls[-2][1]["name"] == "Birthdays" and not ed.dirty and ed.note.text() == "Saved."


def test_opening_one_shows_its_settings_and_what_it_has_done(section):
    define_birthday()
    section.activate()
    aid = demo_platform.handle("autos/create", {"kind": "date", "name": "Reminder", "config": {"attribute": "Birthday", "match": "once", "offset_days": -2, "time": "08:30",
                                                                                          "tags": ["vip"], "template": {"name": "diwali_offer", "language": "en_US"}}})["auto_id"]
    section.open_auto(aid)
    b = section.editor.body
    assert b.attribute.currentData() == "Birthday" and b.match.currentData() == "once" and b.when.currentData() == "before" and b.days.value() == 2
    assert b.time.time().toString("HH:mm") == "08:30" and b.tags.text() == "vip" and b.template.value()["name"] == "diwali_offer"
    assert "0 sent" in section.editor.stats.text()


def test_deleting_asks_first(section):
    define_birthday()
    section.activate()
    aid = demo_platform.handle("autos/create", {"kind": "date", "name": "Old", "config": {"attribute": "Birthday", "template": {"name": "diwali_offer", "language": "en_US"}}})["auto_id"]
    section.open_auto(aid)
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No):
        section.editor._delete()
    assert section.editor is not None
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        section.editor._delete()
    assert section.editor is None and section.state.title.text() == "Choose one"


# ── choosing a template and filling its blanks ───────────────────────────────

def test_only_approved_templates_can_be_chosen_and_their_blanks_are_mapped():
    from addons.whatsapp.template_choice import TemplateChoice
    tc = TemplateChoice()
    heard = []
    tc.changed.connect(lambda: heard.append(1))
    tc.set_templates(demo_platform.handle("templates/list", {})["templates"])
    names = [tc.combo.itemText(i) for i in range(tc.combo.count())]
    assert "diwali_offer · en_US" in names and "quotation_followup · en_US" not in names and "big_sale · en_US" not in names
    tc.combo.setCurrentIndex(tc.combo.findText("diwali_offer · en_US"))
    tc.combo.activated.emit(tc.combo.currentIndex())
    v = tc.value()
    assert v["name"] == "diwali_offer" and set(v["variables"]) == {"1", "2"} and v["variables"]["1"]["source"] == "field" and heard
    assert "our Diwali offer" in tc.preview.text()


def test_a_blank_can_be_fixed_words_or_a_detail_and_a_tracked_link_is_not_offered():
    from addons.whatsapp.template_choice import TemplateChoice
    from PySide6.QtWidgets import QComboBox, QLineEdit
    tc = TemplateChoice()
    tc.set_templates(demo_platform.handle("templates/list", {})["templates"])
    tc.set_value({"name": "diwali_offer", "language": "en_US", "variables": {"1": {"source": "field", "field": "first_name"}, "2": {"source": "static", "value": "boundary walls"}}})
    sources = [c for c in tc.findChildren(QComboBox) if c is not tc.combo]
    assert all(c.findData("tracked_link") < 0 for c in sources)
    edits = [e for e in tc.findChildren(QLineEdit) if e.text()]
    assert [e.text() for e in edits] == ["boundary walls"]
    edits[0].setText("houses")
    assert tc.value()["variables"]["2"] == {"source": "static", "value": "houses"}


def test_a_template_that_was_chosen_and_is_not_approved_any_more_is_still_shown_and_flagged():
    from addons.whatsapp.template_choice import TemplateChoice
    tc = TemplateChoice()
    tc.set_templates([t for t in demo_platform.handle("templates/list", {})["templates"] if t["name"] == "order_update"])
    tc.set_value({"name": "diwali_offer", "language": "en_US", "variables": {}})
    assert "diwali_offer (not approved)" in [tc.combo.itemText(i) for i in range(tc.combo.count())] and not tc.note.isHidden()
    assert tc.value()["name"] == "diwali_offer"


# ── a drip ───────────────────────────────────────────────────────────────────

def test_a_welcome_series_starts_with_three_messages_and_stops_on_a_reply(section):
    section.start("welcome")
    b = section.editor.body
    assert [r.minutes() for r in b.rows] == [0, 2880, 7200] and b.trigger.currentData() == "tag" and b.tag.text() == "new-lead" and b.on_reply.isChecked()
    assert [r.title.text() for r in b.rows] == ["Message 1", "Message 2", "Message 3"]
    assert b.rows[0].hint.text() == "Sent when they start." and "after the message before" in b.rows[1].hint.text()


def test_each_message_of_a_drip_has_its_own_wait_in_the_unit_that_suits_it(section):
    section.start("welcome")
    b = section.editor.body
    assert b.rows[1].amount.value() == 2 and b.rows[1].unit.currentData() == "d"
    b.rows[1].unit.setCurrentIndex(b.rows[1].unit.findData("h"))
    b.rows[1].unit.activated.emit(b.rows[1].unit.currentIndex())
    assert b.rows[1].minutes() == 120 and b.value()["steps"][1]["delay_minutes"] == 120


def test_messages_are_added_up_to_ten_and_removed_down_to_one(section):
    section.start("welcome")
    b = section.editor.body
    for _ in range(12):
        b.add_step({"delay_minutes": 60})
    assert len(b.rows) == 10 and b.add_btn.isHidden()
    for r in list(b.rows)[1:]:
        b.remove_step(r)
    b.remove_step(b.rows[0])
    assert len(b.rows) == 1 and b.rows[0].remove_btn.isHidden() and not b.add_btn.isHidden()


def test_only_the_fields_of_the_chosen_start_are_shown(section):
    section.start("welcome")
    b = section.editor.body
    assert not b.tag_box.isHidden() and b.enrol_box.isHidden() and b.optin_note.isHidden()
    b.trigger.setCurrentIndex(b.trigger.findData("manual"))
    b.trigger.activated.emit(b.trigger.currentIndex())
    assert b.tag_box.isHidden() and not b.enrol_box.isHidden() and b.existing.isHidden()
    b.trigger.setCurrentIndex(b.trigger.findData("opt_in"))
    b.trigger.activated.emit(b.trigger.currentIndex())
    assert not b.optin_note.isHidden() and b.value()["trigger"] == {"type": "opt_in"}


def test_quiet_hours_are_sent_only_when_switched_on(section):
    section.start("welcome")
    b = section.editor.body
    assert "quiet" not in b.value() and not b.quiet_box.isEnabled()
    b.quiet_on.setChecked(True)
    b.quiet_from.setTime(b.quiet_from.time().fromString("08:30", "HH:mm"))
    assert b.quiet_box.isEnabled() and b.value()["quiet"] == {"from": "08:30", "to": "20:00"}


def test_stopping_on_tags_and_the_old_tags_checkbox(section):
    section.start("welcome")
    b = section.editor.body
    b.stop_tags.setText("customer, do-not-disturb")
    b.existing.setChecked(True)
    v = b.value()
    assert v["stop"] == {"on_reply": True, "tags": ["customer", "do-not-disturb"]} and v["include_existing"] is True
    b.trigger.setCurrentIndex(b.trigger.findData("manual"))
    b.trigger.activated.emit(b.trigger.currentIndex())
    assert b.value()["include_existing"] is False


def test_saving_a_drip_needs_a_template_in_every_message_and_then_it_runs_through(section, calls):
    section.start("followup")
    ed = section.editor
    ed.save()
    assert "Choose the template to send" in ed.note.text() and ed.auto["id"] is None
    for r in ed.body.rows:
        r.template.combo.setCurrentIndex(r.template.combo.findText("order_update · en_US"))
        r.template.combo.activated.emit(r.template.combo.currentIndex())
    ed.save()
    ed = section.editor
    assert ed.auto["id"] and ed.auto["kind"] == "drip"
    ed.on.setChecked(True)
    assert ed.auto["enabled"] and "3 still in it" in ed.stats.text() and "2 sent" in ed.stats.text()


def test_people_are_added_to_a_drip_by_hand_from_a_segment_or_a_tag(section, calls):
    from addons.whatsapp import autos_page as AU
    section.start("followup")
    ed = section.editor
    for r in ed.body.rows:
        r.template.combo.setCurrentIndex(r.template.combo.findText("order_update · en_US"))
        r.template.combo.activated.emit(r.template.combo.currentIndex())
    with mock.patch.object(AU.EnrolDialog, "exec", return_value=1), mock.patch.object(AU.EnrolDialog, "audience", lambda self: {"tags": ["vip"]}):
        ed.body.enrol()
    assert "autos/enrol" in routes(calls) and "Added" in ed.note.text()


def test_the_enrol_window_wants_a_segment_or_a_tag():
    from addons.whatsapp import autos_page as AU
    d = AU.EnrolDialog([{"id": "s1", "name": "Hot leads"}])
    d._go()
    assert "Choose a segment or write a tag" in d.error.text()
    d.tags.setText("vip, hot lead")
    assert d.audience() == {"tags": ["vip", "hot lead"]}
    d.segment.setCurrentIndex(1)
    assert d.audience() == {"segment_id": "s1"}


def test_the_list_shows_what_each_one_is_and_how_it_is_doing(section):
    define_birthday()
    section.activate()
    a = demo_platform.handle("autos/create", {"kind": "date", "name": "Birthdays", "config": {"attribute": "Birthday", "template": {"name": "diwali_offer", "language": "en_US"}}})["auto_id"]
    d = demo_platform.handle("autos/create", {"kind": "drip", "name": "Welcome", "config": {"trigger": {"type": "tag", "tag": "new-lead"},
                                                                                         "steps": [{"delay_minutes": 0, "template": {"name": "order_update", "language": "en_US"}}]}})["auto_id"]
    demo_platform.handle("autos/set_enabled", {"auto_id": d, "enabled": True})
    section.refresh_list()
    t = texts(section)
    assert "Birthdays" in t and "Welcome" in t and "On a date · Birthday · On the day · every year" in t and "When someone gets “new-lead” · 1 messages" in t and "3 in it now" in t
    assert a


# ── the demo platform's rules ────────────────────────────────────────────────

@pytest.mark.parametrize("config,fragment", [
    ({"attribute": "Nope"}, "contact detail that holds a date"), ({"attribute": "Birthday", "match": "weekly"}, "comes round every year"),
    ({"attribute": "Birthday", "offset_days": 90}, "up to 60 days"), ({"attribute": "Birthday", "time": "10am"}, "look like 10:00"),
    ({"attribute": "Birthday", "template": {}}, "Choose the template"),
])
def test_the_demo_refuses_what_the_server_refuses_in_the_same_words(config, fragment):
    demo_platform.handle("attributes/define", {"key": "Birthday", "type": "date"})
    with pytest.raises(PlatformError) as why:
        demo_platform.handle("autos/create", {"kind": "date", "name": "x", "config": {"template": {"name": "diwali_offer"}, **config}})
    assert fragment in str(why.value)


@pytest.mark.parametrize("config,fragment", [
    ({"trigger": {"type": "tag"}}, "Name the tag"), ({"steps": []}, "1 to 10 messages"), ({"steps": [{"delay_minutes": -1, "template": {"name": "x"}}]}, "Wait from 0 minutes"),
    ({"quiet": {"from": "09:00", "to": "09:00"}}, "two different times"),
])
def test_the_demo_refuses_a_bad_drip_in_the_same_words(config, fragment):
    base = {"trigger": {"type": "manual"}, "steps": [{"delay_minutes": 0, "template": {"name": "order_update"}}]}
    with pytest.raises(PlatformError) as why:
        demo_platform.handle("autos/create", {"kind": "drip", "name": "x", "config": {**base, **config}})
    assert fragment in str(why.value)
