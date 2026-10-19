"""The Forms tab: the list, starting points, the editor, checking, publishing, sending and the answers.

Driven with a fake worker that answers from the demo platform, so nothing opens a socket, starts a thread or spins an event loop. No processEvents()/exec()/QEventLoop (a dialog's
exec is replaced by a method that returns); nothing touches the real ~/.prism.
"""
from __future__ import annotations

import os
import sys
import tempfile
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core_bridge  # noqa: F401,E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

_app = QApplication.instance() or QApplication([])

from addons.whatsapp import demo, demo_forms, demo_platform, readstate, ui  # noqa: E402
from whatsapp_fakes import last, routes, texts, worker  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="prism-wa-forms-")
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
    monkeypatch.setattr(ui, "PlatformWorker", worker(calls))
    return calls


@pytest.fixture
def page(served):
    from addons.whatsapp.forms_page import FormsPage
    p = FormsPage({})
    p.activate()
    return p


def st():
    return demo_forms._forms(demo_platform._state())


def buttons(widget) -> str:
    return " | ".join(b.text() for b in widget.findChildren(QPushButton))


def the(name):
    return [f for f in st()["forms"] if f["name"] == name][0]


def editor_for(page, name):
    f = the(name)
    page.edit(f)
    return page.editor


# ── the list ─────────────────────────────────────────────────────────────────

def test_forms_are_listed_with_their_state_size_answers_and_what_can_be_done(page, calls):
    t = texts(page)
    assert "Walls enquiry" in t and "Published" in t and "3 answers" in t and "Book an appointment" in t and "Not published" in t and "Live times" in t
    b = buttons(page)
    assert "Send…" in b and "Answers" in b and "Retire" in b and "Edit" in b and "Delete" in b and "Copy" in b
    assert page.stack.currentIndex() == 0


def test_with_no_forms_the_page_offers_to_start_one(page, calls):
    st()["forms"].clear()
    page.load()
    assert page.stack.currentIndex() == 1


def test_a_form_meta_turned_down_shows_what_it_said_on_the_list(page, calls):
    the("Book an appointment")["problems"] = [{"where": "Meta", "message": "Property label is too long."}]
    page.load()
    assert "Meta said: Property label is too long." in texts(page)


# ── starting a form ──────────────────────────────────────────────────────────

def test_the_starting_points_are_offered_and_one_can_be_chosen(page, calls, monkeypatch):
    from addons.whatsapp.forms_page import NewFormDialog
    monkeypatch.setattr(NewFormDialog, "exec", lambda self: 0)
    page.new()
    assert "forms/templates" in routes(calls)
    templates = demo_platform.handle("forms/templates", {})["templates"]
    d = NewFormDialog(templates, page)
    t = texts(d)
    assert "Lead capture" in t and "Book an appointment" in t and "Feedback" in t and "Quotation request" in t and "Basic details" in t and "Site visit request" in t
    assert "Live times" in t and "Use this" in buttons(d) and "Start empty" in buttons(d)
    d.pick("feedback")
    assert d.chosen == "feedback"


def test_choosing_a_starting_point_makes_the_form_and_opens_the_editor(page, calls, monkeypatch):
    from addons.whatsapp.forms_page import NewFormDialog
    monkeypatch.setattr(NewFormDialog, "exec", lambda self: (setattr(self, "chosen", "quotation"), 1)[1])
    page.new()
    assert last(calls, "forms/create") == {"template": "quotation"}
    assert page.editor is not None and page.editor.name.text() == "Quotation request" and len(page.editor.cards) == 2 and not page.new_btn.isVisibleTo(page)


def test_starting_empty_makes_a_form_with_one_blank_screen(page, calls, monkeypatch):
    from addons.whatsapp.forms_page import NewFormDialog
    monkeypatch.setattr(NewFormDialog, "exec", lambda self: (setattr(self, "chosen", ""), 1)[1])
    page.new()
    assert page.editor.name.text() == "New form" and len(page.editor.cards) == 1 and page.editor.cards[0].cards == []


def test_cancelling_the_picker_changes_nothing(page, calls, monkeypatch):
    from addons.whatsapp.forms_page import NewFormDialog
    monkeypatch.setattr(NewFormDialog, "exec", lambda self: 0)
    page.new()
    assert "forms/create" not in routes(calls) and page.editor is None


# ── the editor ───────────────────────────────────────────────────────────────

def test_the_editor_shows_the_screens_and_fields_of_the_form(page, calls):
    ed = editor_for(page, "Walls enquiry")
    assert ed.name.text() == "Walls enquiry" and ed.status.text() == "Published" and len(ed.cards) == 1
    card = ed.cards[0]
    assert card.title.text() == "Tell us about you" and card.button.text() == "Send" and [c.label.text() for c in card.cards] == ["Your name", "Phone number", "Email", "What do you need?", "Anything to add?"]
    need = card.cards[3]
    assert need.kind.currentData() == "dropdown" and need.options.toPlainText().splitlines() == ["Boundary wall", "Gate", "Painting", "Something else"] and not need.options_box.isHidden()
    assert card.cards[0].options_box.isHidden() and card.cards[0].required.isChecked() and not card.cards[2].required.isChecked()
    assert ed.publish_btn.text() == "Save and publish a new version"


def test_where_an_answer_is_saved_is_shown_on_the_field(page, calls):
    ed = editor_for(page, "Walls enquiry")
    name, _phone, email, need, _note = ed.cards[0].cards
    assert name.save_to.currentData() == "@name" and email.save_to.currentData() == "@email"
    assert need.save_to.currentData() == "__detail__" and need.detail.text() == "Interest" and not need.detail.parentWidget().isHidden() and name.detail.parentWidget().isHidden()


def test_typing_a_label_makes_its_code_name_until_the_name_is_edited_by_hand(page, calls):
    ed = editor_for(page, "Walls enquiry")
    card = ed.cards[0]
    card.add_kind("text")
    f = card.cards[-1]
    f.label.setText("Site address")
    f.label.textEdited.emit("Site address")
    assert f.name.text() == "site_address"
    f.name.setText("addr")
    f.name.textEdited.emit("addr")
    f.label.setText("Site address 2")
    f.label.textEdited.emit("Site address 2")
    assert f.name.text() == "addr"


def test_a_new_field_gets_a_free_code_name_and_choices_to_start_from(page, calls):
    ed = editor_for(page, "Walls enquiry")
    card = ed.cards[0]
    card.add_kind("radio")
    card.add_kind("radio")
    a, b = card.cards[-2:]
    assert a.name.text() != b.name.text() and a.options.toPlainText().splitlines() == ["One", "Two"]


def test_fields_can_be_moved_and_removed(page, calls):
    ed = editor_for(page, "Walls enquiry")
    card = ed.cards[0]
    first, second = card.cards[:2]
    card._move_field(first, 1)
    assert card.cards[:2] == [second, first] and card.fields.itemAt(0).widget() is second
    card._remove_field(second)
    assert len(card.cards) == 4 and second not in card.cards


def test_the_menu_for_adding_a_field_lists_every_kind(page, calls, monkeypatch):
    ed = editor_for(page, "Walls enquiry")
    seen = {}
    monkeypatch.setattr(ed, "_pop_up", lambda menu, below: seen.setdefault("items", [a.text() for a in menu.actions()]))
    ed.cards[0]._menu()
    assert seen["items"] == ["Short answer", "E-mail address", "Phone number", "Number", "Long answer", "Date", "Pick from a list", "Pick one", "Pick several", "Tick to agree"]


def test_screens_are_added_moved_and_removed_without_losing_what_was_typed(page, calls):
    ed = editor_for(page, "Walls enquiry")
    ed.cards[0].title.setText("My own title")
    ed.add_screen()
    assert len(ed.cards) == 2 and ed.cards[0].title.text() == "My own title" and ed.form["screens"][1]["id"] == "SCREEN_A"
    ed.cards[1].title.setText("Second")
    ed._move_screen(ed.cards[1], -1)
    assert [c.title.text() for c in ed.cards] == ["Second", "My own title"]
    ed._remove_screen(ed.cards[0])
    assert len(ed.cards) == 1 and ed.cards[0].title.text() == "My own title"
    ed._remove_screen(ed.cards[0])
    assert len(ed.cards) == 1 and "at least one screen" in ed.note.text()


def test_collect_reads_the_whole_form_back_as_the_server_wants_it(page, calls):
    ed = editor_for(page, "Walls enquiry")
    ed.name.setText("Enquiry 2")
    ed.tag.setText("hot")
    ed.thanks.setText("Thanks!")
    ed.category.setCurrentIndex(ed.category.findData("SURVEY"))
    d = ed.collect()
    assert d["name"] == "Enquiry 2" and d["categories"] == ["SURVEY"] and d["tag_on_submit"] == "hot" and d["settings"] == {"thank_you": "Thanks!"} and d["endpoint"] is False
    assert d["mapping"] == {"name": "@name", "email": "@email", "need": "Interest"}
    s = d["screens"][0]
    assert s["id"] == "ENQUIRY" and [f["name"] for f in s["fields"]] == ["name", "phone", "email", "need", "note"] and s["fields"][3]["options"][1] == {"id": "gate", "title": "Gate"}
    assert s["texts"] == [{"style": "body", "text": "We will call you back within a day."}]


def test_checking_names_what_is_wrong_and_where(page, calls):
    ed = editor_for(page, "Walls enquiry")
    ed.cards[0].cards[1].name.setText("name")                                  # the same code name as the first field
    ed.cards[0].cards[0].label.setText("A label that is much too long")
    ed.check()
    assert "forms/check" in routes(calls) and "things to fix" in ed.note.text() and ed.note.tone == "error"
    t = texts(ed)
    assert "Two fields are called" in t and "up to 20 characters" in t and "Screen 1" in t


def test_a_form_that_is_fine_says_so(page, calls):
    ed = editor_for(page, "Walls enquiry")
    ed.check()
    assert "Nothing wrong" in ed.note.text() and ed.note.tone == "ok"


def test_saving_sends_the_form_and_keeps_the_editor_in_step(page, calls):
    ed = editor_for(page, "Walls enquiry")
    ed.name.setText("Walls enquiry 2")
    ed.save()
    assert last(calls, "forms/update")["name"] == "Walls enquiry 2" and last(calls, "forms/update")["form_id"] == "f1" and ed.note.text() == "Saved." and ed.save_btn.isEnabled()
    assert the("Walls enquiry 2")["id"] == "f1"


def test_publishing_saves_first_then_publishes_and_the_state_changes(page, calls):
    ed = editor_for(page, "Book an appointment")
    assert ed.status.text() == "Not published" and ed.publish_btn.text() == "Save and publish"
    ed.publish()
    assert routes(calls).index("forms/publish") > routes(calls).index("forms/update")
    assert ed.status.text() == "Published" and "Published. You can now send it" in ed.note.text() and ed.publish_btn.isEnabled()
    assert the("Book an appointment")["meta_flow_id"] and st()["key"]["has_key"] is True


def test_publishing_a_form_with_problems_shows_them_and_does_not_publish(page, calls):
    ed = editor_for(page, "Walls enquiry")
    ed.cards[0].title.setText("")
    ed.publish()
    assert "not ready" in ed.note.text() and ed.note.tone == "error" and ed.publish_btn.isEnabled()
    assert "Give the screen a title" in texts(ed) and the("Walls enquiry")["version"] == 1


def test_publishing_a_changed_form_makes_a_new_version(page, calls):
    ed = editor_for(page, "Walls enquiry")
    ed.name.setText("Walls enquiry v2")
    ed.publish()
    assert the("Walls enquiry v2")["version"] == 2 and ed.form["status"] == "published"


def test_the_code_for_meta_can_be_looked_at(page, calls, monkeypatch):
    from addons.whatsapp import forms_page
    ed = editor_for(page, "Walls enquiry")
    from PySide6.QtWidgets import QPlainTextEdit
    seen = []
    monkeypatch.setattr(forms_page.CodeDialog, "exec", lambda self: seen.append(self.findChildren(QPlainTextEdit)[0].toPlainText()) or 0)
    ed.preview()
    assert '"version": "6.3"' in seen[0] and '"ENQUIRY"' in seen[0]


# ── a form with live times ───────────────────────────────────────────────────

def test_a_live_form_shows_its_opening_hours_and_the_key_note(page, calls):
    ed = editor_for(page, "Book an appointment")
    assert ed.live.isChecked() and ed.hours is not None and not ed.key_line.isHidden()
    assert [b.isChecked() for b in ed.hours.days] == [True, True, True, True, True, True, False] and ed.hours.start.text() == "10:00" and ed.hours.slot.value() == 60
    slot = ed.cards[0].cards[2]
    assert slot.kind.currentData() == "dropdown" and slot.options_box.isHidden() and not slot.live_note.isHidden()


def test_the_opening_hours_are_read_back_with_the_day_and_time_fields_named(page, calls):
    ed = editor_for(page, "Book an appointment")
    ed.hours.days[5].setChecked(False)
    ed.hours.days[6].setChecked(True)
    ed.hours.capacity.setValue(3)
    ed.hours.end.setText("18:30")
    a = ed.collect()["settings"]["availability"]
    assert a["weekdays"] == [0, 1, 2, 3, 4, 6] and a["capacity"] == 3 and a["end"] == "18:30" and a["date_field"] == "date" and a["slot_field"] == "slot"
    ed.save()
    assert the("Book an appointment")["settings"]["availability"]["capacity"] == 3


def test_bad_opening_hours_are_refused_in_words(page, calls):
    ed = editor_for(page, "Book an appointment")
    ed.hours.start.setText("18:00")
    ed.hours.end.setText("09:00")
    ed.save()
    assert "opening time must be before the closing time" in ed.note.text() and ed.save_btn.isEnabled()


def test_a_plain_form_has_no_opening_hours(page, calls):
    ed = editor_for(page, "Walls enquiry")
    assert ed.hours is None and ed.key_line.isHidden()
    ed.live.setChecked(True)
    assert not ed.key_line.isHidden() and ed.hours is None                       # no field offers live times, so there is nothing to open


# ── sending, answers, and tidying ────────────────────────────────────────────

def test_a_published_form_is_sent_to_a_chosen_person_only(page, calls):
    from addons.whatsapp.forms_page import SendFormDialog
    d = SendFormDialog(the("Walls enquiry"), page)
    d._go()
    assert "Choose who to send it to" in d.error.text() and "forms/send" not in routes(calls)
    d.who.search.setText("Ravi")
    d.who.search_now()
    d.button_words.setText("Fill in")
    d._go()
    sent = last(calls, "forms/send")
    assert sent["form_id"] == "f1" and sent["contact_id"] == "k2" and sent["button"] == "Fill in" and sent["body"] == "Please fill in this short form."


def test_a_form_that_is_not_published_cannot_be_sent_and_the_reason_is_shown(page, calls):
    from addons.whatsapp.forms_page import SendFormDialog
    d = SendFormDialog(the("Book an appointment"), page)
    d.who.search.setText("Ravi")
    d.who.search_now()
    d._go()
    assert "publish the form before sending it" in d.error.text() and d.go.isEnabled()


def test_the_answers_are_listed_with_who_gave_them(page, calls):
    from addons.whatsapp.forms_page import ResponsesDialog
    d = ResponsesDialog(the("Walls enquiry"), page)
    t = texts(d)
    assert d.count == 3 and "Asha Patel" in t and "need:  gate" in t and "Meena Joshi" in t
    empty = ResponsesDialog(the("Book an appointment"), page)
    assert "Nobody has filled this in yet" in texts(empty)


def test_the_answers_download_as_a_file(page, calls, monkeypatch, tmp_path):
    from addons.whatsapp import forms_page
    from addons.whatsapp.forms_page import ResponsesDialog
    out = tmp_path / "answers.csv"
    monkeypatch.setattr(forms_page.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    d = ResponsesDialog(the("Walls enquiry"), page)
    d.export()
    text = out.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("received,contact,phone,name,phone,email,need") and "asha@shakti.example" in text and "Saved." in d.error.text()


def test_copying_retiring_and_deleting_a_form(page, calls, monkeypatch):
    page.duplicate(the("Walls enquiry"))
    assert the("Walls enquiry (copy)")["status"] == "draft" and "Copied." in page.note.text()
    monkeypatch.setattr(ui, "confirm", lambda *a: False)
    page.retire(the("Walls enquiry"))
    page.delete(the("Walls enquiry (copy)"))
    assert "forms/retire" not in routes(calls) and "forms/delete" not in routes(calls)
    monkeypatch.setattr(ui, "confirm", lambda *a: True)
    page.retire(the("Walls enquiry"))
    assert the("Walls enquiry")["status"] == "deprecated" and "Retired." in page.note.text()
    page.delete(the("Walls enquiry (copy)"))
    assert not any(f["name"] == "Walls enquiry (copy)" for f in st()["forms"])


def test_closing_the_editor_goes_back_to_the_list(page, calls):
    ed = editor_for(page, "Walls enquiry")
    ed.closed.emit()
    assert page.editor is None and page.new_btn.isVisibleTo(page) and page.stack.currentIndex() == 0


def test_the_workbench_opens_the_forms_tab(page):
    from addons.whatsapp import workbench as W
    wb = W.WhatsAppWorkbench({})
    wb.show_tab(W._FORMS)
    assert type(wb._pages[W._FORMS]).__name__ == "FormsPage"


# ── from a chat or a contact ─────────────────────────────────────────────────

def test_a_form_from_a_chat_asks_which_published_form_then_whom_is_already_chosen(page, calls, monkeypatch):
    from addons.whatsapp import forms_page
    seen = {}
    monkeypatch.setattr(forms_page.PickFormDialog, "exec", lambda self: (seen.setdefault("offered", [self.choice.itemText(i) for i in range(self.choice.count())]), 1)[1])
    monkeypatch.setattr(forms_page.SendFormDialog, "exec", lambda self: (seen.setdefault("who", self.who.contact_id()), 0)[1])
    page.send_to({"id": "k2", "name": "Ravi Shah"})
    assert seen["offered"] == ["Walls enquiry"] and seen["who"] == "k2"


def test_with_no_published_form_the_chat_action_says_so(page, calls, monkeypatch):
    from addons.whatsapp import forms_page
    for f in st()["forms"]:
        f["status"] = "draft"
    monkeypatch.setattr(forms_page.PickFormDialog, "exec", lambda self: 1)
    page.send_to({"id": "k2", "name": "Ravi Shah"})
    assert "No form is published yet" in page.note.text() and page.note.tone == "error"


def test_the_workbench_hands_a_person_to_the_forms_tab(served, monkeypatch):
    from addons.whatsapp import forms_page
    from addons.whatsapp import workbench as W
    got = []
    monkeypatch.setattr(forms_page.FormsPage, "send_to", lambda self, c: got.append(c))
    wb = W.WhatsAppWorkbench({})
    wb._form_for({"id": "k4", "name": "Kunal Desai"})
    assert wb._current == W._FORMS and got == [{"id": "k4", "name": "Kunal Desai"}]
