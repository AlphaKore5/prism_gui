"""The flow builder: the plain-data model, the step cards, the editor, the try-it console, and the flows list.

Driven with a fake worker that answers from the demo platform, so nothing opens a socket, starts a thread or spins an event
loop. Rules this file follows: no processEvents()/exec()/QEventLoop, and nothing touches the real ~/.prism.
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core_bridge  # noqa: F401,E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

_app = QApplication.instance() or QApplication([])

from addons.whatsapp import demo, demo_platform, flow_model as M, readstate, ui  # noqa: E402
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
    tmp = tempfile.mkdtemp(prefix="prism-wa-flows-")
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
    """Every platform call made through ui.call is answered by the demo platform."""
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    return calls


def routes(calls):
    return [r for r, _d in calls]


# ── the plain-data model ─────────────────────────────────────────────────────

def graph():
    return {"entry": "a", "order": ["a", "b", "c"], "nodes": {
        "a": {"type": "buttons", "text": "Pick", "options": [{"id": "x", "title": "X", "next": "b"}, {"id": "y", "title": "Y", "next": "c"}], "fallback_next": "b"},
        "b": {"type": "ask", "text": "Name?", "next": "c", "invalid_next": "a"},
        "c": {"type": "end"}}}


def test_every_kind_of_step_can_be_made():
    for kind, name, _hint in M.step_types():
        node = M.new_node(kind)
        assert node["type"] == kind and name
    assert len(M.step_types()) == 23
    assert {k for g, ks in M.step_groups() for k in ks} == {k for k, _n, _h in M.step_types()}      # every kind is in exactly one menu group


def test_a_new_step_is_given_a_name_nobody_has():
    assert M.unique_id("Say something", []) == "Say_something"
    assert M.unique_id("welcome", ["welcome", "welcome_2"]) == "welcome_3"
    assert M.unique_id("!!!", []) == "step"


def test_adding_a_step_puts_it_after_another_and_the_first_becomes_the_entry():
    g = {}
    first = M.add_node(g, "send_text", name="hello")
    assert g["entry"] == first and g["order"] == [first]
    second = M.add_node(g, "end", after=first)
    third = M.add_node(g, "send_text", after=first, name="between")
    assert g["order"] == [first, third, second]


def test_renaming_a_step_changes_every_place_that_points_at_it():
    g = graph()
    M.rename_node(g, "b", "ask_name")
    assert "b" not in g["nodes"] and g["order"] == ["a", "ask_name", "c"]
    assert g["nodes"]["a"]["options"][0]["next"] == "ask_name" and g["nodes"]["a"]["fallback_next"] == "ask_name"
    M.rename_node(g, "a", "start")
    assert g["entry"] == "start" and g["nodes"]["ask_name"]["invalid_next"] == "start"


def test_a_rename_to_a_taken_or_bad_name_is_refused():
    g = graph()
    with pytest.raises(ValueError):
        M.rename_node(g, "a", "b")
    with pytest.raises(ValueError):
        M.rename_node(g, "a", "has space")
    M.rename_node(g, "a", "a")                                  # the same name: nothing to do


def test_removing_a_step_ends_whatever_led_to_it_and_never_leaves_a_dangling_pointer():
    g = graph()
    M.remove_node(g, "c")
    assert "c" not in g["nodes"] and g["order"] == ["a", "b"]
    assert g["nodes"]["a"]["options"][1].get("next") is None
    assert "next" not in g["nodes"]["b"]
    assert all(t in g["nodes"] for n in g["nodes"].values() for t in M.targets_of(n))


def test_removing_the_entry_moves_it_to_what_came_next():
    g = graph()
    M.remove_node(g, "a")
    assert g["entry"] == "b"
    M.remove_node(g, "b")
    M.remove_node(g, "c")
    assert g["entry"] is None and g["nodes"] == {}


def test_steps_move_up_and_down_and_stop_at_the_ends():
    g = graph()
    M.move_node(g, "c", -1)
    assert g["order"] == ["a", "c", "b"]
    M.move_node(g, "a", -5)
    assert g["order"][0] == "a"
    M.move_node(g, "b", 5)
    assert g["order"][-1] == "b"


def test_a_flow_with_no_saved_order_is_shown_in_the_order_it_is_walked():
    g = graph()
    del g["order"]
    assert M.order_of(g) == ["a", "b", "c"]
    g["nodes"]["z"] = {"type": "end"}                          # unreachable: still shown, last
    assert M.order_of(g)[-1] == "z"


def test_what_is_saved_has_no_empty_targets():
    g = graph()
    g["nodes"]["a"]["options"][1]["next"] = None
    g["nodes"]["b"]["next"] = None
    out = M.clean_for_save(g)
    assert "next" not in out["nodes"]["a"]["options"][1] and "next" not in out["nodes"]["b"]
    assert g["nodes"]["b"]["next"] is None                      # the copy was cleaned, not the original


def test_a_trigger_and_a_step_read_as_a_sentence():
    assert "contains" in M.trigger_words({"type": "keyword", "match": "contains", "keywords": ["price", "rate"]})
    assert M.trigger_words({"type": "first_message"}) == "A new customer's first message"
    assert M.trigger_words({}) == "Not chosen yet"
    assert M.describe_step({"type": "send_text", "text": "Hello there"}) == "Hello there"
    assert M.describe_step({"type": "delay", "minutes": 30}) == "30 minutes"
    assert M.describe_step({"type": "add_tag", "tag": "hot"}) == "hot"
    assert M.describe_step({"type": "end"}) == "End"
    long = M.describe_step({"type": "send_text", "text": "x" * 90})
    assert len(long) == 61 and long.endswith("…")


def test_issues_are_grouped_by_the_step_they_name():
    by = M.issues_by_node([{"node": "a", "code": "x"}, {"node": "a", "code": "y"}, {"node": "", "code": "z"}])
    assert len(by["a"]) == 2 and len(by[""]) == 1


# ── the step cards ───────────────────────────────────────────────────────────

class Ctx:
    def __init__(self, g):
        self.g = g
        self.agents_list, self.flows_list = [{"id": "ag1", "name": "Aria"}], [{"id": "f9", "name": "Other flow"}]
        self.tmpls = [{"name": "diwali_offer", "language": "en_US", "components": [{"type": "BODY", "text": "Hello {{1}}, offer on {{2}} ends soon."}]}]

    def labels(self):
        return {nid: M.describe_step(self.g["nodes"][nid]) for nid in M.order_of(self.g)}

    def entry(self):
        return self.g.get("entry")

    def templates(self):
        return self.tmpls

    def forms(self):
        return [{"id": "f1", "name": "Walls enquiry"}]

    def products(self):
        return [{"retailer_id": "wall-6", "name": "Wall panel"}]

    def agents(self):
        return self.agents_list

    def flows(self):
        return self.flows_list


def card(kind, g=None, nid="s1", node=None):
    from addons.whatsapp.flow_steps import StepCard
    g = g or {"entry": "s1", "nodes": {"s1": node or M.new_node(kind), "t": {"type": "end"}}}
    ctx = Ctx(g)
    c = StepCard(nid, g["nodes"][nid], ctx)
    c.heard = []
    for sig in ("changed", "shape"):
        getattr(c, sig).connect(lambda *a, s=sig: c.heard.append(s))
    return c, g


@pytest.mark.parametrize("kind", [k for k, _n, _h in M.step_types()])
def test_every_kind_of_step_builds_a_card(kind):
    c, g = card(kind)
    assert c.node["type"] == kind and c.id_edit.text() == "s1"


def test_a_say_step_writes_its_text_and_picks_where_to_go(served):
    c, g = card("send_text")
    from PySide6.QtWidgets import QPlainTextEdit
    c.findChildren(QPlainTextEdit)[0].setPlainText("Hello!")
    assert g["nodes"]["s1"]["text"] == "Hello!" and "changed" in c.heard
    combo = c.targets[0][0]
    assert [combo.itemData(i) for i in range(combo.count())] == [None, "t"]                # End the flow, then the other step
    combo.setCurrentIndex(1)
    combo.chosen.emit(combo.value())
    assert g["nodes"]["s1"]["next"] == "t" and "shape" in c.heard


def test_a_step_cannot_lead_to_itself_as_a_choice():
    c, g = card("send_text")
    combo = c.targets[0][0]
    assert "s1" not in [combo.itemData(i) for i in range(combo.count())]


def test_a_target_that_no_longer_exists_is_shown_not_hidden():
    c, g = card("send_text", node={"type": "send_text", "text": "x", "next": "gone"})
    combo = c.targets[0][0]
    assert combo.currentData() == "gone" and "missing" in combo.currentText()


def test_a_buttons_step_adds_up_to_three_and_keeps_at_least_one():
    c, g = card("buttons")
    rows = c.rows[0]
    assert len(g["nodes"]["s1"]["options"]) == 2
    rows._add()
    assert len(g["nodes"]["s1"]["options"]) == 3 and rows.add_btn.isHidden()
    rows._remove(g["nodes"]["s1"]["options"][0])
    rows._remove(g["nodes"]["s1"]["options"][0])
    rows._remove(g["nodes"]["s1"]["options"][0])
    assert len(g["nodes"]["s1"]["options"]) == 1


def test_a_new_button_gets_its_own_id():
    c, g = card("buttons")
    c.rows[0]._add()
    ids = [o["id"] for o in g["nodes"]["s1"]["options"]]
    assert len(set(ids)) == 3


def test_a_list_step_takes_up_to_ten_rows():
    c, g = card("list")
    rows = c.rows[0]
    for _ in range(12):
        rows._add()
    assert len(g["nodes"]["s1"]["rows"]) == 10 and rows.add_btn.isHidden()


def test_an_ask_step_shows_only_the_extra_field_its_check_needs():
    from PySide6.QtWidgets import QComboBox
    c, g = card("ask")
    combos = c.findChildren(QComboBox)
    validator = next(x for x in combos if x.findData("regex") >= 0)
    validator.setCurrentIndex(validator.findData("regex"))
    validator.activated.emit(validator.currentIndex())
    assert g["nodes"]["s1"]["validator"] == "regex"
    validator.setCurrentIndex(validator.findData("number"))
    validator.activated.emit(validator.currentIndex())
    assert g["nodes"]["s1"]["validator"] == "number"


def test_an_ask_step_keeps_the_answer_under_a_name():
    from PySide6.QtWidgets import QComboBox, QLineEdit
    c, g = card("ask")
    where = next(x for x in c.findChildren(QComboBox) if x.findData("attr") >= 0)
    where.setCurrentIndex(where.findData("attr"))
    where.activated.emit(where.currentIndex())
    name = next(x for x in c.findChildren(QLineEdit) if x.placeholderText().startswith("Name"))
    name.setText("City")
    assert g["nodes"]["s1"]["save_as"] == "attr:City"
    where.setCurrentIndex(0)
    where.activated.emit(0)
    assert "save_as" not in g["nodes"]["s1"]


def test_a_delay_is_stored_in_minutes_whatever_unit_it_is_shown_in():
    from PySide6.QtWidgets import QComboBox, QSpinBox
    c, g = card("delay", node={"type": "delay", "minutes": 120})
    n = c.findChildren(QSpinBox)[0]
    unit = next(x for x in c.findChildren(QComboBox) if x.findData("h") >= 0)
    assert unit.currentData() == "h" and n.value() == 2                   # 120 minutes reads as 2 hours
    unit.setCurrentIndex(unit.findData("d"))
    unit.activated.emit(unit.currentIndex())
    assert g["nodes"]["s1"]["minutes"] == 2 * 1440 and "seconds" not in g["nodes"]["s1"]
    n.setValue(100)
    assert g["nodes"]["s1"]["minutes"] == 7 * 1440                         # capped at a week


def test_a_template_step_lists_the_blanks_and_maps_each():
    from PySide6.QtWidgets import QComboBox
    c, g = card("template", node={"type": "template", "name": "diwali_offer", "language": "en_US", "variables": {}})
    assert sorted(g["nodes"]["s1"]["variables"]) == ["1", "2"]
    assert g["nodes"]["s1"]["variables"]["1"] == {"source": "field", "field": "first_name"}


def test_a_condition_step_edits_its_rules():
    c, g = card("condition")
    rows = c.rows[0]
    rule = g["nodes"]["s1"]["rules"][0]
    assert rule["field"] == "message" and rule["op"] == "contains"
    rows._add()
    assert len(g["nodes"]["s1"]["rules"]) == 2


def test_an_api_step_reads_headers_and_saved_values_from_lines():
    from PySide6.QtWidgets import QPlainTextEdit
    c, g = card("api_request")
    edits = c.findChildren(QPlainTextEdit)
    edits[0].setPlainText("Authorization: Bearer abc\nX-Id: 7")
    assert g["nodes"]["s1"]["headers"] == {"Authorization": "Bearer abc", "X-Id": "7"}
    edits[2].setPlainText("status = order.status\nnot a line")
    assert g["nodes"]["s1"]["save"] == {"status": "order.status"}


def test_a_handover_agent_and_flow_jump_choose_from_what_exists():
    from PySide6.QtWidgets import QComboBox
    c, g = card("agent")
    combo = c.findChildren(QComboBox)[0]
    combo.setCurrentIndex(combo.findData("ag1"))
    combo.activated.emit(combo.currentIndex())
    assert g["nodes"]["s1"]["agent_id"] == "ag1"
    combo.setCurrentIndex(0)
    combo.activated.emit(0)
    assert "agent_id" not in g["nodes"]["s1"]
    c2, g2 = card("jump_flow")
    combo2 = c2.findChildren(QComboBox)[0]
    combo2.setCurrentIndex(combo2.findData("f9"))
    combo2.activated.emit(combo2.currentIndex())
    assert g2["nodes"]["s1"]["flow_id"] == "f9"


def test_renaming_a_step_on_its_card_announces_it_and_a_bad_name_is_put_back():
    c, g = card("send_text")
    heard = []
    c.renamed.connect(lambda a, b: heard.append((a, b)))
    c.id_edit.setText("greeting")
    c.id_edit.editingFinished.emit()
    assert heard == [("s1", "greeting")]
    c.id_edit.setText("has space")
    c.id_edit.editingFinished.emit()
    assert c.id_edit.text() == "greeting" and heard == [("s1", "greeting")]
    c.id_edit.setText("t")                                               # another step already has it
    c.id_edit.editingFinished.emit()
    assert c.id_edit.text() == "greeting"


def test_a_card_marks_the_first_step_and_offers_to_make_another_first():
    c, g = card("send_text")
    assert not c.entry_pill.isHidden() and c.entry_btn.isHidden()
    other, _ = card("end", g=g, nid="t")
    assert other.entry_pill.isHidden() and not other.entry_btn.isHidden()
    heard = []
    other.make_entry.connect(heard.append)
    other.entry_btn.click()
    assert heard == ["t"]


def test_problems_are_shown_on_the_step_they_belong_to():
    c, g = card("send_text")
    c.set_issues([{"severity": "error", "message": "Needs its text."}, {"severity": "warning", "message": "Fine but odd."}])
    from PySide6.QtWidgets import QLabel
    texts = [lab.text() for lab in c.findChildren(QLabel)]
    assert any("Needs its text." in t for t in texts) and any("Fine but odd." in t for t in texts)
    c.set_issues([])
    assert not [lab for lab in c.findChildren(QLabel) if "Needs its text." in lab.text()]


# ── the editor ───────────────────────────────────────────────────────────────

def open_flow(section, flow_id):
    section.open_flow(flow_id)
    return section.editor


@pytest.fixture
def flows_section(served):
    from addons.whatsapp import flows_page as FP
    sec = FP.FlowsSection({})
    sec.activate()
    yield sec


def make_library_flow(key="lead_capture"):
    return demo_platform.handle("flows/from_library", {"key": key})["flow_id"]


def test_with_no_flows_the_screen_invites_a_first_one(flows_section):
    assert flows_section.stack.currentIndex() == 0 and flows_section.state.title.text() == "No flows yet"
    assert flows_section.state.action.text() == "New flow"


def test_a_first_load_failure_is_explained_with_a_retry(calls, monkeypatch):
    from addons.whatsapp import flows_page as FP
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls, fail={"flows/list": "The WhatsApp add-on isn't set up on the server yet."}))
    sec = FP.FlowsSection({})
    sec.activate()
    assert sec.state.title.text() == "Couldn't load your flows" and "isn't set up" in sec.state.body.text() and sec.state.action.text() == "Try again"


def test_the_list_shows_each_flow_and_opens_the_first(served):
    from addons.whatsapp import flows_page as FP
    fid = make_library_flow()
    make_library_flow("faq_menu")
    sec = FP.FlowsSection({})
    sec.activate()
    assert [f["name"] for f in sec.flows] == ["Capture a new enquiry", "Answer common questions"]
    assert sec.editor is not None and sec.editor.flow["id"] == fid and sec.stack.currentIndex() == 1


def test_a_blank_flow_starts_with_one_empty_say_step(flows_section):
    flows_section._blank()
    ed = flows_section.editor
    assert ed.flow["name"] == "New flow" and list(ed.graph["nodes"]) == ["welcome"] and ed.graph["entry"] == "welcome"
    assert ed.trigger == {"type": "keyword", "match": "contains", "keywords": ["hello"]}


def test_a_ready_made_flow_is_chosen_from_the_library(flows_section, monkeypatch):
    from addons.whatsapp import flows_page as FP
    with mock.patch.object(FP.LibraryDialog, "exec", lambda self: (setattr(self, "key", "feedback"), 1)[1]):
        flows_section._library()
    assert flows_section.editor.flow["name"] == "Ask for feedback"


def test_the_editor_shows_every_step_in_order_and_what_starts_it(flows_section):
    flows_section._blank()
    flows_section.editor.add_step("buttons")
    ed = flows_section.editor
    assert len(ed.cards) == 2 and list(ed.cards)[0] == "welcome"
    assert ed.trigger_btn.text().startswith("A message contains")


def test_an_edit_saves_itself_with_the_order_and_no_empty_targets(flows_section, calls):
    flows_section._blank()
    ed = flows_section.editor
    ed.add_step("send_text")
    del calls[:]
    ed.name.setText("Greeting")
    assert ed.saved.text().startswith("Unsaved") and ed._timer.isActive()
    ed.save()
    route, data = [c for c in calls if c[0] == "flows/update"][0]
    assert data["name"] == "Greeting" and data["graph"]["order"] == list(ed.graph["order"])
    assert all("next" not in n or n["next"] for n in data["graph"]["nodes"].values())
    assert ed.saved.text() == "Saved"


def test_the_checks_come_back_with_every_save_and_are_listed(flows_section):
    flows_section._blank()
    ed = flows_section.editor
    ed.save()
    from PySide6.QtWidgets import QLabel
    texts = " | ".join(lab.text() for lab in ed.findChildren(QLabel))
    assert "problem" in texts and "needs its text" in texts.lower()
    assert any(i["severity"] == "error" for i in ed.issues)


def test_a_flow_with_a_problem_cannot_be_published_and_the_reasons_are_shown(flows_section, calls):
    flows_section._blank()
    ed = flows_section.editor
    ed.publish()
    assert "flows/publish" in routes(calls) and ed.version == 0
    assert ed.publish_btn.isEnabled() and "needs its text" in ed.note.text().lower()


def test_a_good_flow_publishes_and_can_then_be_switched_on(served):
    from addons.whatsapp import flows_page as FP
    fid = make_library_flow()
    sec = FP.FlowsSection({})
    sec.activate()
    ed = sec.editor
    assert ed.status.text() == "Draft"
    ed.publish()
    assert ed.version == 1 and "Published as version 1" in ed.note.text() and ed.status.text() == "Off · v1"
    ed.switch.setChecked(True)
    assert ed.enabled is True and ed.status.text() == "Live · v1"


def test_switching_on_before_publishing_is_refused_and_the_switch_goes_back(served):
    from addons.whatsapp import flows_page as FP
    make_library_flow()
    sec = FP.FlowsSection({})
    sec.activate()
    ed = sec.editor
    ed.switch.setChecked(True)
    assert ed.enabled is False and not ed.switch.isChecked() and "Publish the flow" in ed.note.text()


def test_an_earlier_version_can_be_brought_back(served):
    from addons.whatsapp import flows_page as FP
    make_library_flow()
    sec = FP.FlowsSection({})
    sec.activate()
    ed = sec.editor
    ed.publish()
    ed.add_step("send_text")
    ed.graph["nodes"][M.order_of(ed.graph)[-1]]["text"] = "One more thing"
    ed.save()
    ed.publish()
    assert ed.version == 2
    with mock.patch.object(FP.VersionsDialog, "exec", lambda self: (setattr(self, "choice", 1), 1)[1]):
        ed._versions()
    assert sec.editor is not ed                                   # the flow was reopened from the server
    assert sec.editor.version == 3


def test_deleting_a_flow_asks_first(served):
    from addons.whatsapp import flows_page as FP
    make_library_flow()
    sec = FP.FlowsSection({})
    sec.activate()
    ed = sec.editor
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.No):
        ed._delete()
    assert sec.editor is ed
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        ed._delete()
    assert sec.editor is None and sec.state.title.text() == "Choose a flow" and sec.flows == []


def test_steps_are_added_moved_renamed_and_removed_from_the_editor(flows_section):
    flows_section._blank()
    ed = flows_section.editor
    ed.add_step("end")
    names = list(M.order_of(ed.graph))
    assert len(names) == 2
    ed._move(names[1], -1)
    assert M.order_of(ed.graph) == [names[1], names[0]]
    ed._rename(names[0], "first_thing")
    assert "first_thing" in ed.graph["nodes"] and "first_thing" in ed.cards
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        ed._remove("first_thing")
    assert "first_thing" not in ed.graph["nodes"]


def test_making_another_step_the_first_moves_the_marker(flows_section):
    flows_section._blank()
    ed = flows_section.editor
    ed.add_step("end")
    second = M.order_of(ed.graph)[1]
    ed._entry(second)
    assert ed.graph["entry"] == second and not ed.cards[second].entry_pill.isHidden() and ed.cards["welcome"].entry_pill.isHidden()


def test_the_trigger_dialog_builds_each_kind_of_trigger(served):
    from addons.whatsapp import flows_page as FP
    d = FP.TriggerDialog({"type": "keyword", "match": "exact", "keywords": ["price", "rate"]})
    assert d.value() == {"type": "keyword", "match": "exact", "keywords": ["price", "rate"]}
    d.kind.setCurrentIndex(d.kind.findData("regex"))
    d.pattern.setText(r"^\d{6}$")
    assert d.value() == {"type": "regex", "pattern": r"^\d{6}$"}
    d.kind.setCurrentIndex(d.kind.findData("ad"))
    d.ads.setText("77, 78 ,")
    assert d.value() == {"type": "ad", "ad_ids": ["77", "78"]}
    d.kind.setCurrentIndex(d.kind.findData("button"))
    d.payload.setText("go")
    assert d.value() == {"type": "button", "payload": "go"}
    d.kind.setCurrentIndex(d.kind.findData("first_message"))
    assert d.value() == {"type": "first_message"}


def test_the_trigger_dialog_shows_only_the_fields_of_the_chosen_kind(served):
    from addons.whatsapp import flows_page as FP
    d = FP.TriggerDialog({"type": "regex", "pattern": "x"})
    assert not d.pattern_box.isHidden() and d.kw_box.isHidden() and d.ads_box.isHidden()
    d.kind.setCurrentIndex(d.kind.findData("keyword"))
    d.kind.activated.emit(d.kind.currentIndex())
    assert d.pattern_box.isHidden() and not d.kw_box.isHidden()


def test_changing_the_trigger_updates_the_button_and_saves(flows_section, calls):
    from addons.whatsapp import flows_page as FP
    flows_section._blank()
    ed = flows_section.editor
    with mock.patch.object(FP.TriggerDialog, "exec", return_value=1), \
            mock.patch.object(FP.TriggerDialog, "value", lambda self: {"type": "first_message"}):
        ed._trigger()
    assert ed.trigger_btn.text() == "A new customer's first message" and ed._timer.isActive()


# ── try it ───────────────────────────────────────────────────────────────────

def test_trying_a_flow_walks_it_as_a_customer_without_saving_anything(served, calls):
    from addons.whatsapp import flows_page as FP
    make_library_flow()
    sec = FP.FlowsSection({})
    sec.activate()
    ed = sec.editor
    del calls[:]
    ed.console._send("hi")
    assert routes(calls) == ["flows/test"]
    from PySide6.QtWidgets import QLabel, QPushButton
    texts = " | ".join(lab.text() for lab in ed.console.findChildren(QLabel))
    assert "What do you need today?" in texts
    assert "Get a quote" in [b.text() for b in ed.console.findChildren(QPushButton)]       # the buttons are offered as chips


def test_tapping_a_button_chip_continues_the_conversation(served, calls):
    from addons.whatsapp import flows_page as FP
    make_library_flow()
    sec = FP.FlowsSection({})
    sec.activate()
    ed = sec.editor
    ed.console._send("hi")
    ed.console._send("Get a quote")
    ed.console._send("Asha Patel")
    ed.console._send("Vadodara")
    assert ed.console.inputs == ["hi", "Get a quote", "Asha Patel", "Vadodara"]
    from PySide6.QtWidgets import QLabel
    texts = " | ".join(lab.text() for lab in ed.console.findChildren(QLabel))
    assert "Thank you Asha Patel" in texts and "The flow has finished" in ed.console.note.text()


def test_trying_an_unfinished_flow_says_to_fix_the_problems_first(flows_section):
    flows_section._blank()
    ed = flows_section.editor
    ed.console._send("hello")
    assert "Fix the problems" in ed.console.note.text() and ed.issues


def test_starting_again_clears_the_conversation(served):
    from addons.whatsapp import flows_page as FP
    make_library_flow()
    sec = FP.FlowsSection({})
    sec.activate()
    ed = sec.editor
    ed.console._send("hi")
    ed.console.reset()
    assert ed.console.inputs == []
