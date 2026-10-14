"""The STEP add-on's window — the GUI face of /step, /step-auto and
/step-ask, tested the way test_gerber_dialog.py tests Gerber's: intercept
AutomationWorker rather than open a browser, and read what it was given.

The one rule that must never break is the same as Gerber's: the customer's
model is their product. Draft, Ask and Edit may hand an AI the measured
numbers and Prism's OWN render of the parts — never the STEP file, never
its path. If a future edit ever attaches the model to a stage, the security
tests below fail immediately, in CI, before it ships.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PRISM_LICENSE_OFFLINE_DEV", "1")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "prism_terminal"))

import core_bridge as CB  # noqa: E402
import plans  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sample_jobs  # noqa: E402
from test_gates import GateTest  # noqa: E402
from addons.step import dialog as SD  # noqa: E402
from addons.step.dialog import StepDialog  # noqa: E402
from dialogs.answer_dialog import AnswerDialog  # noqa: E402
from core import stepfile as SF  # noqa: E402

_app = QApplication.instance() or QApplication([])
HAVE_CAD = SF.available()[0]
EVERYTHING = tuple(plans.FEATURES)


class _Sig:
    def connect(self, *_):
        pass


def _dialog(cfg=None, root=None):
    """A dialog whose folder question is already answered — cfg carries a
    scratch step_out_dir — so no modal can open in a headless run. Every
    test that wants the question itself clears the key on purpose."""
    root = root or tempfile.mkdtemp(prefix="prism-test-step-")
    if cfg is None:
        cfg = {"agents": {"visual": "ChatGPT", "brains": "Claude"},
               "api_key": "gsk_test", "step_out_dir": root}
    return StepDialog(cfg, [], None)


def _box_step(path: str):
    """A 60 x 40 x 8 mm block with one Ø5 hole — every figure known."""
    import cadquery as cq
    part = (cq.Workplane("XY").box(60, 40, 8)
            .faces(">Z").workplane().hole(5))
    cq.exporters.export(part, path)


def _fake_measured(dlg, stem="block", out_dir=None):
    """A measured model without cadquery: the shape _on_measured builds."""
    out_dir = out_dir or os.path.join(dlg._root(), stem)
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, SF.names(stem)["png"])
    open(png, "wb").write(b"png")
    report = {"file": f"{stem}.step", "stem": stem, "mode": "plastic",
              "path": f"/secret/place/{stem}.step",
              "overall_mm": (60.0, 40.0, 8.0),
              "parts": [{"name": "p", "size_mm": (60.0, 40.0, 8.0),
                         "thickness_mm": 6.0, "volume_cm3": 38.0,
                         "holes": [{"dia_mm": 5.0, "count": 1}]}],
              "warnings": []}
    m = {"path": f"/secret/place/{stem}.step", "report": report,
         "out_dir": out_dir, "drawn": {"png": png, "html": ""}, "xlsx": ""}
    dlg.paths = [m["path"]]
    return m


class _CaptureWorker:
    """Stands in for AutomationWorker: records the call, never starts."""
    seen: dict = {}

    def __init__(self, *a, **kw):
        _CaptureWorker.seen = {"args": a, "kwargs": kw}
        self.done = self.failed = _Sig()

    def start(self):
        _CaptureWorker.seen["started"] = True


class TheDoorIsShutUntilAModelIsAttached(unittest.TestCase):

    def test_generate_waits_for_a_model(self):
        dlg = _dialog()
        self.assertFalse(dlg.generate_btn.isEnabled())
        dlg._on_files_added(["/nowhere/Assem1.STEP"])
        self.assertTrue(dlg.generate_btn.isEnabled())

    def test_only_step_files_are_taken(self):
        """A PDF or a DWG dropped here is not a model; it is named in the
        status line and left out, rather than measured and failing later."""
        dlg = _dialog()
        dlg._on_files_added(["/nowhere/quote.pdf", "/nowhere/housing.stp"])
        self.assertEqual([os.path.basename(p) for p in dlg.paths],
                         ["housing.stp"])
        self.assertIn("quote.pdf", dlg.status.text())

    def test_the_same_model_is_not_attached_twice(self):
        dlg = _dialog()
        dlg._on_files_added(["/nowhere/a.step"])
        dlg._on_files_added(["/nowhere/a.step"])
        self.assertEqual(len(dlg.paths), 1)

    def test_removing_a_chip_actually_removes_the_model(self):
        """The chip's own 'x' used to only clear AskPanel's private copy —
        dlg.paths (what Generate really measures) kept the file, so a
        mis-picked model was measured and answered anyway even after it
        looked removed. file_removed must keep the two in step."""
        dlg = _dialog()
        dlg._on_files_added(["/nowhere/Assem1.STEP"])
        dlg._on_files_added(["/nowhere/PET CORE 02 06.STEP"])
        self.assertEqual(len(dlg.paths), 2)
        dlg.ask.remove_path(os.path.abspath("/nowhere/Assem1.STEP"))
        self.assertEqual([os.path.basename(p) for p in dlg.paths],
                         ["PET CORE 02 06.STEP"])
        self.assertTrue(dlg.generate_btn.isEnabled())
        dlg.ask.remove_path(os.path.abspath("/nowhere/PET CORE 02 06.STEP"))
        self.assertEqual(dlg.paths, [])
        self.assertFalse(dlg.generate_btn.isEnabled())

    def test_the_file_is_asked_for_before_the_question(self):
        """The question box and the choice of action stay out of sight
        until a model is attached — the file first, then what to do."""
        dlg = _dialog()
        self.assertTrue(dlg.step2.isHidden())
        self.assertIs(dlg.ask.edit.parentWidget(), dlg.step2)
        dlg._on_files_added(["/nowhere/quote.pdf"])
        self.assertTrue(dlg.step2.isHidden(), "a non-model must not open it")
        dlg._on_files_added(["/nowhere/Assem1.STEP"])
        self.assertFalse(dlg.step2.isHidden())

    def test_the_three_actions_are_offered_and_draft_is_the_default(self):
        dlg = _dialog()
        self.assertEqual(set(dlg._action_buttons), {"draft", "ask", "edit"})
        self.assertEqual(dlg._action(), "draft")
        dlg._action_buttons["edit"].setChecked(True)
        self.assertEqual(dlg._action(), "edit")

    def test_the_one_button_always_names_what_it_will_do(self):
        """One shared button for Draft/Ask/Edit used to always just say
        'Generate' — the person had to trust whichever radio they'd picked,
        and a stale selection meant a click landed on the wrong action.
        The button's own label is now the only thing that has to be read."""
        dlg = _dialog()
        self.assertEqual(dlg.generate_btn.text(), "Measure and Draw")
        dlg._action_buttons["ask"].setChecked(True)
        self.assertEqual(dlg.generate_btn.text(), "Get the Answer")
        dlg._action_buttons["edit"].setChecked(True)
        self.assertEqual(dlg.generate_btn.text(), "Make the Changes")
        dlg._action_buttons["draft"].setChecked(True)
        self.assertEqual(dlg.generate_btn.text(), "Measure and Draw")


class TheFolderQuestionIsAskedOnceThenKept(unittest.TestCase):
    """The owner's ask: the person says where all the files for a model go.
    Asked at the first Generate, remembered in cfg, changeable from the
    Options box — and never asked again once answered."""

    def test_an_answered_question_is_not_asked_again(self):
        dlg = _dialog()
        with mock.patch.object(SD, "QMessageBox") as box:
            self.assertTrue(dlg._ensure_root())
            box.assert_not_called()

    def test_choosing_the_desktop_stores_the_default_explicitly(self):
        cfg = {"agents": {}, "api_key": "", "step_out_dir": ""}
        dlg = StepDialog(cfg, [], None)
        fake = mock.MagicMock()
        fake.return_value.clickedButton.return_value = "desktop-btn"
        fake.return_value.addButton.side_effect = ["choose-btn", "desktop-btn",
                                                   "cancel-btn"]
        with mock.patch.object(SD, "QMessageBox", fake), \
                mock.patch.object(CB.config, "save") as save:
            self.assertTrue(dlg._ensure_root())
            save.assert_called_once()
        self.assertEqual(cfg["step_out_dir"], SF.DEFAULT_OUT_ROOT)
        self.assertIn("Prism Step", dlg.root_label.text())

    def test_choosing_a_folder_keeps_it(self):
        cfg = {"agents": {}, "api_key": "", "step_out_dir": ""}
        dlg = StepDialog(cfg, [], None)
        chosen = tempfile.mkdtemp(prefix="prism-test-step-root-")
        fake = mock.MagicMock()
        fake.return_value.clickedButton.return_value = "choose-btn"
        fake.return_value.addButton.side_effect = ["choose-btn", "desktop-btn",
                                                   "cancel-btn"]
        with mock.patch.object(SD, "QMessageBox", fake), \
                mock.patch.object(SD.QFileDialog, "getExistingDirectory",
                                  return_value=chosen), \
                mock.patch.object(CB.config, "save"):
            self.assertTrue(dlg._ensure_root())
        self.assertEqual(cfg["step_out_dir"], chosen)
        self.assertIn(chosen, dlg.root_label.text())

    def test_cancelling_the_question_generates_nothing(self):
        cfg = {"agents": {}, "api_key": "", "step_out_dir": ""}
        dlg = StepDialog(cfg, [], None)
        fake = mock.MagicMock()
        fake.return_value.clickedButton.return_value = "something-else"
        fake.return_value.addButton.side_effect = ["choose-btn", "desktop-btn",
                                                   "cancel-btn"]
        with mock.patch.object(SD, "QMessageBox", fake):
            self.assertFalse(dlg._ensure_root())
        self.assertEqual(cfg["step_out_dir"], "")

    def test_the_root_reaches_the_measuring_worker(self):
        """What was chosen is what the worker is given — the folder per
        model is made under it (core.stepfile.output_dir)."""
        dlg = _dialog()
        dlg._on_files_added(["/nowhere/Assem1.STEP"])
        seen = {}

        class FakeMeasure:
            def __init__(self, paths, mode, root, k_factor=0.0):
                seen.update(paths=paths, mode=mode, root=root, k_factor=k_factor)
                self.progress = self.done = self.failed = _Sig()

            def start(self):
                seen["started"] = True

        with mock.patch.object(SD, "StepMeasureWorker", FakeMeasure), \
                mock.patch.object(CB.config, "save"):
            dlg._generate()
        self.assertEqual(seen["root"], dlg.cfg["step_out_dir"])
        self.assertEqual(seen["mode"], "metal")
        self.assertTrue(seen["started"])


class AnAgentOnlyEverSeesTheNumbersAndPrismsOwnRender(unittest.TestCase):
    """The standing rule, enforced at the calls that could break it."""

    def _draft_call(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        # The AI draft is opt-in (Round 42) — these tests are about what
        # it is given WHEN it runs, so switch it on explicitly.
        dlg.ai_draft_cb.setChecked(True)
        with mock.patch.object(SD, "AutomationWorker", _CaptureWorker):
            dlg._current = m
            dlg._draft(m)
        return dlg, m, _CaptureWorker.seen

    def test_draft_attaches_prisms_render_and_never_the_model(self):
        dlg, m, seen = self._draft_call()
        attachments = seen["args"][2]
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["path"], m["drawn"]["png"])
        for a in attachments:
            self.assertFalse(a["path"].lower().endswith((".step", ".stp")))

    def test_the_draft_prompt_carries_the_numbers_not_the_path(self):
        dlg, m, seen = self._draft_call()
        prompt = seen["kwargs"]["custom_stages"][0][2][0]
        self.assertIn("60.00 x 40.00 x 8.00", prompt)
        self.assertIn("MEASURED OFFLINE", prompt)
        self.assertNotIn("/secret/place", prompt)
        self.assertNotIn("/secret/place", seen["args"][3])

    def test_draft_asks_for_the_returned_files(self):
        """The image the agent draws comes back through files_out — without
        it the sheet exists only in the tool's tab."""
        dlg, m, seen = self._draft_call()
        self.assertIs(seen["kwargs"]["files_out"], dlg._made_files)

    def test_draft_promises_a_picture_so_the_wait_is_long_enough(self):
        dlg, m, seen = self._draft_call()
        self.assertEqual(seen["kwargs"]["image_stages"], {"visual"})

    def test_the_ai_draft_is_off_by_default_and_skips_chatgpt_entirely(self):
        """Round 42: checked against Prism's own drawing, ChatGPT's
        'styled' copy just traced it, worse — not an independent check,
        only a different look. Draft's job (Prism's own sheet) is already
        done by the time this runs; ChatGPT is opt-in from here."""
        dlg = _dialog()
        m = _fake_measured(dlg)
        self.assertFalse(dlg.ai_draft_cb.isChecked())
        _CaptureWorker.seen = {}          # not reset between tests otherwise
        # Skipping the AI stage means _draft falls straight through to
        # _next() -> _finish(), which saves the run for real unless mocked
        # (tests/conftest.py fails the suite on a write to the real
        # ~/.prism, by design).
        with mock.patch.object(SD, "AutomationWorker", _CaptureWorker), \
                mock.patch.object(CB.config, "save_run"):
            dlg._current = m
            dlg._draft(m)
        self.assertEqual(_CaptureWorker.seen, {},
                         "AutomationWorker (ChatGPT) must not be built at all")

    def test_draft_is_chatgpt_only_with_no_fallback(self):
        """Not the configured visual tool, and no hand-off to another
        image model if ChatGPT stumbles — a second, differently-wrong sheet
        is not a rescue."""
        dlg = _dialog(cfg={"agents": {"visual": "Gamma.app",
                                      "media": "Canva"},
                           "api_key": "k",
                           "step_out_dir": tempfile.mkdtemp()})
        m = _fake_measured(dlg)
        dlg.ai_draft_cb.setChecked(True)
        with mock.patch.object(SD, "AutomationWorker", _CaptureWorker):
            dlg._current = m
            dlg._draft(m)
        seen = _CaptureWorker.seen
        self.assertEqual(seen["kwargs"]["custom_stages"][0][1], "ChatGPT")
        self.assertIs(seen["kwargs"]["failover"], False)

    def test_the_plan_stage_gets_numbers_advice_and_the_question(self):
        # Only Edit reaches the plan stage now — Ask stops at the answer.
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.ask.set_text("make it lighter")
        dlg._current = m
        dlg._action_buttons["edit"].setChecked(True)
        with mock.patch.object(SD, "AutomationWorker", _CaptureWorker), \
                mock.patch.object(SD, "AnswerDialog") as answer:
            dlg._on_suggested("1) thin the wall")
        answer.return_value.exec.assert_called_once()
        seen = _CaptureWorker.seen
        prompt = seen["kwargs"]["custom_stages"][0][2][0]
        self.assertEqual(seen["kwargs"]["custom_stages"][0][1], "Claude")
        self.assertIn("make it lighter", prompt)
        self.assertIn("thin the wall", prompt)
        self.assertIn("60.00 x 40.00 x 8.00", prompt)
        self.assertNotIn("/secret/place", prompt)
        for a in seen["args"][2]:
            self.assertFalse(a["path"].lower().endswith((".step", ".stp")))

    def test_the_groq_question_carries_numbers_and_confidentiality(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        p = SF.ask_prompt(m["report"], "make it lighter")
        self.assertIn("cannot be shown to you", p)
        self.assertNotIn("/secret/place", p)

    def test_ask_shows_only_the_answer_no_plan_and_no_page(self):
        """Ask's whole deliverable is the suggestion text — it must never
        reach the planning stage, so no AutomationWorker is built, no
        review page is written, and nothing is opened. (Round: a plain
        question used to always get reviewed into a change plan — hole
        enlarges, scale factors — and a webpage popped open even when
        nothing was asked to change; that's Edit's job now, not Ask's.)"""
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.ask.set_text("which material fits best?")
        dlg._current = m
        dlg._action_buttons["ask"].setChecked(True)
        _CaptureWorker.seen = {}          # not reset between tests otherwise
        with mock.patch.object(SD.QDesktopServices, "openUrl") as opened, \
                mock.patch.object(SD, "AutomationWorker", _CaptureWorker), \
                mock.patch.object(SD, "AnswerDialog") as answer, \
                mock.patch.object(CB.config, "save_run"):
            dlg._on_suggested("PP for cost, ABS for a balance of cost "
                              "and strength.")
        answer.return_value.exec.assert_called_once()
        opened.assert_not_called()
        self.assertEqual(_CaptureWorker.seen, {},
                         "Ask must never start the plan stage")
        self.assertIn("PP for cost", dlg.result.toPlainText())
        self.assertTrue(any("choose Edit" in n for n in dlg._notes))

    def test_edit_reviews_the_plan_then_asks_before_building(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.ask.set_text("fit 6mm")
        dlg._current = m
        dlg._action_buttons["edit"].setChecked(True)
        plan = ('{"changes": [{"op": "enlarge_hole", "part": "p", '
                '"dia_mm": 5, "new_dia_mm": 6, "why": "M6"}], "advice": []}')
        built = {}

        class FakeApply:
            def __init__(self, *a, **kw):
                built["args"] = a
                self.done = self.failed = _Sig()

            def start(self):
                built["started"] = True

        with mock.patch.object(SD, "StepApplyWorker", FakeApply), \
                mock.patch.object(SD, "PlanReviewDialog") as review_dlg:
            review_dlg.return_value.exec.return_value = 1   # Accepted
            dlg._on_planned({"plan": [plan]}, {})
            review_dlg.return_value.exec.assert_called_once()
            self.assertTrue(built["started"])
            # The worker is handed the ORIGINAL path to read, and writes the
            # copy under the model's own name in the model's own folder.
            self.assertEqual(built["args"][0], m["path"])
            self.assertEqual(built["args"][4], m["out_dir"])
            self.assertTrue(os.path.exists(
                os.path.join(m["out_dir"], SF.names(m["report"])["review"])))

    def test_a_no_answer_builds_nothing(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.ask.set_text("fit 6mm")
        dlg._current = m
        dlg._action_buttons["edit"].setChecked(True)
        plan = ('{"changes": [{"op": "scale", "part": "all", "factor": 2, '
                '"why": ""}], "advice": []}')
        with mock.patch.object(CB.config, "save_run"), \
                mock.patch.object(SD, "StepApplyWorker") as apply_w, \
                mock.patch.object(SD, "PlanReviewDialog") as review_dlg:
            review_dlg.return_value.exec.return_value = 0   # Rejected
            dlg._on_planned({"plan": [plan]}, {})
            apply_w.assert_not_called()
        self.assertTrue(any("not built" in n for n in dlg._notes))


class ChoosingAStrongerModelThanGroq(unittest.TestCase):
    """Groq is the default, fast, in-house path (unchanged — covered
    elsewhere). Picking ChatGPT or Claude instead routes through the same
    background-Chrome AutomationWorker Draft/Edit's plan stage already
    uses, with a fixed ChatGPT -> Claude fallback if the chosen one can't
    answer. No Gemini option — see MODEL_CHOICES' own comment: it is
    registered engine-wide as an image-only tool, so any text prompt
    routed to it comes back as a refused image request, not an answer."""

    def _pick(self, dlg, label_value: str):
        idx = dlg.model_combo.findData(label_value)
        self.assertGreaterEqual(idx, 0, f"{label_value} not offered")
        dlg.model_combo.setCurrentIndex(idx)

    def test_a_chosen_model_builds_the_ask_stage_with_no_engine_failover(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.ask.set_text("which material fits best?")
        dlg._current = m
        self._pick(dlg, "Claude")
        _CaptureWorker.seen = {}
        with mock.patch.object(SD, "AutomationWorker", _CaptureWorker):
            dlg._ask(m)
        seen = _CaptureWorker.seen
        stage_key, tool, prompts = seen["kwargs"]["custom_stages"][0]
        self.assertEqual((stage_key, tool), ("ask", "Claude"))
        self.assertIn("which material fits best?", prompts[0])
        self.assertIs(seen["kwargs"]["failover"], False)
        # Claude was already tried as the primary pick — the remaining
        # chain is the fixed order with it taken out.
        self.assertEqual(dlg._model_chain, ["ChatGPT"])

    def test_a_silent_tool_falls_through_to_the_next_in_the_fixed_order(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.ask.set_text("which material fits best?")
        dlg._current = m
        self._pick(dlg, "Claude")
        with mock.patch.object(SD, "AutomationWorker", _CaptureWorker):
            dlg._ask(m)                                  # tries Claude first
            _CaptureWorker.seen = {}
            dlg._on_asked_by_tool(m, "Claude", {}, {})    # Claude said nothing
            seen = _CaptureWorker.seen
        stage_key, tool, _prompts = seen["kwargs"]["custom_stages"][0]
        self.assertEqual((stage_key, tool), ("ask", "ChatGPT"))
        self.assertEqual(dlg._model_chain, [])

    def test_exhausting_the_chain_fails_cleanly_not_silently_to_groq(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg._current = m
        dlg._model_chain = []
        with mock.patch.object(SD.QMessageBox, "warning") as warn, \
                mock.patch.object(SD, "StepAskWorker") as groq:
            dlg._ask_via_chain(m)
            warn.assert_called_once()
            groq.assert_not_called()

    def test_a_real_answer_stops_the_chain_and_records_its_agent(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.ask.set_text("which material fits best?")
        dlg._current = m
        dlg._action_buttons["ask"].setChecked(True)
        dlg._model_chain = ["ChatGPT"]   # would be tried next if this failed
        # This flows on into _on_suggested -> _next() -> _finish(), which
        # saves the run for real unless mocked (conftest fails the suite on
        # a write to the developer's own ~/.prism).
        with mock.patch.object(SD, "AnswerDialog") as answer, \
                mock.patch.object(CB.config, "save_run"):
            dlg._on_asked_by_tool(
                m, "Claude", {"ask": ["PP for cost, ABS for a balance."]},
                {"ask": "https://claude.ai/chat/x"})
        answer.return_value.exec.assert_called_once()
        self.assertEqual(dlg._model_chain, [],
                         "a real answer must stop the fallback chain")
        key = f"ask · {m['report']['stem']}"
        self.assertEqual(dlg._responses[key],
                         ["PP for cost, ABS for a balance."])
        self.assertEqual(dlg._stage_agents_map[key], "Claude")
        self.assertEqual(dlg._links[key], "https://claude.ai/chat/x")

    def test_groq_still_needs_its_own_key_but_the_others_do_not(self):
        dlg = _dialog(cfg={"agents": {"brains": "Claude"},
                           "step_out_dir": tempfile.mkdtemp()})   # no api_key
        dlg._on_files_added(["/nowhere/a.step"])
        dlg._action_buttons["ask"].setChecked(True)
        dlg.ask.set_text("which material?")
        with mock.patch.object(SD.QMessageBox, "warning") as warn, \
                mock.patch.object(SD, "StepMeasureWorker") as worker:
            dlg._generate()
            warn.assert_called_once()
            worker.assert_not_called()
        self._pick(dlg, "Claude")
        with mock.patch.object(SD.QMessageBox, "warning") as warn, \
                mock.patch.object(SD, "StepMeasureWorker") as worker, \
                mock.patch.object(CB.config, "save"):
            dlg._generate()
            warn.assert_not_called()
            worker.assert_called_once()


class TheFinishedRunCarriesWhatTheFollowUpNeeds(unittest.TestCase):
    """main_window offers the ordinary post-completion follow-up (the one
    every routed run gets) by reading _task_name/_responses/
    _stage_agents_map/_links off a closed dialog. STEP never set any of
    these — there was no follow-up option on STEP at all. _finish() must
    leave them in the same shape BOQ's dialog already does."""

    def test_finish_sets_the_task_name_the_followup_reads(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.models = [m]
        dlg.ask.set_text("which material fits best?")
        dlg._action_buttons["ask"].setChecked(True)
        dlg._responses = {"ask · block": ["PP for cost."]}
        dlg._stage_agents_map = {"ask · block": "Claude"}
        with mock.patch.object(CB.config, "save_run"):
            dlg._finish()
        self.assertEqual(dlg._task_name,
                         "STEP — Ask: which material fits best?")
        self.assertEqual(dlg._responses, {"ask · block": ["PP for cost."]})
        self.assertEqual(dlg._stage_agents_map, {"ask · block": "Claude"})


class TheConversationIsSavedToOneFilePerModel(unittest.TestCase):
    """A chatbot-style memory: closing the popup, closing Prism, even
    reattaching the file next week — the conversation about THIS part is
    read back off a plain JSON file sitting beside its other outputs, not
    lost the moment the popup closes."""

    def test_round_trips_through_the_real_file(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        thread = [["You asked", "which material?"], ["Groq", "PP."]]
        dlg._save_conversation(m, thread)
        path = dlg._conversation_path(m)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith("block - conversation.json"))
        self.assertEqual(dlg._load_conversation(m),
                         [("You asked", "which material?"), ("Groq", "PP.")])

    def test_loading_before_any_conversation_exists_is_just_empty(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        self.assertEqual(dlg._load_conversation(m), [])

    def test_on_suggested_seeds_the_popup_from_the_saved_file(self):
        """The whole point: a SECOND Ask on the same model must not start
        from blank — it continues the file the first one wrote."""
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg._current = m
        dlg.ask.set_text("question two")
        dlg._save_conversation(m, [["You asked", "question one"],
                                   ["Groq", "answer one"]])
        with mock.patch.object(SD, "AnswerDialog") as answer, \
                mock.patch.object(CB.config, "save_run"):
            dlg._on_suggested("answer two")
        kwargs = answer.call_args.kwargs
        self.assertEqual(kwargs["prior_thread"],
                         [("You asked", "question one"),
                          ("Groq", "answer one")])
        self.assertTrue(callable(kwargs["on_change"]))

    def test_an_end_to_end_run_actually_writes_the_whole_thread(self):
        """The real AnswerDialog this time (only its own .exec() stubbed
        out, so the popup never actually blocks in a headless run) — this
        proves the save actually fires end to end, not just that the
        right callback was handed over."""
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg._current = m
        dlg.ask.set_text("which material fits best?")
        with mock.patch.object(SD.AnswerDialog, "exec", return_value=1), \
                mock.patch.object(CB.config, "save_run"):
            dlg._on_suggested("PP for cost.")
        path = dlg._conversation_path(m)
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            saved = json.load(f)
        self.assertEqual(saved, [["You asked", "which material fits best?"],
                                 ["Groq", "PP for cost."]])
        # Re-attaching the same model and asking again must pick this up.
        dlg._current = m
        dlg.ask.set_text("question two")
        with mock.patch.object(SD, "AnswerDialog") as answer, \
                mock.patch.object(CB.config, "save_run"):
            dlg._on_suggested("answer two")
        self.assertEqual(
            answer.call_args.kwargs["prior_thread"],
            [("You asked", "which material fits best?"),
             ("Groq", "PP for cost.")])


class AFollowUpTypedInsideTheAnswerPopup(unittest.TestCase):
    """The popup's own "Follow up" button (beside Copy/Close) — a note
    typed there re-asks whichever agent answered the first time, not a
    fresh one, and the popup's own content is what gets updated."""

    def test_groq_gets_the_earlier_answer_as_context(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.ask.set_text("which material fits best?")
        key = f"ask · {m['report']['stem']}"
        dlg._responses[key] = ["PP for cost."]
        fake_dlg = mock.MagicMock()
        with mock.patch.object(SD, "StepAskWorker") as worker_cls:
            dlg._on_answer_followup(fake_dlg, m, key, "Groq",
                                    "what about Nylon 6?")
        fake_dlg.set_busy.assert_called_once_with(True)
        prompt = worker_cls.call_args[0][2]
        self.assertIn("PP for cost.", prompt)
        self.assertIn("what about Nylon 6?", prompt)
        worker_cls.return_value.start.assert_called_once()

    def test_a_successful_groq_followup_updates_the_response_and_popup(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        key = f"ask · {m['report']['stem']}"
        dlg._responses[key] = ["PP for cost."]
        fake_dlg = mock.MagicMock()
        dlg._on_answer_followup_done(fake_dlg, key, "Nylon 6 needs drying.")
        self.assertEqual(dlg._responses[key], ["Nylon 6 needs drying."])
        self.assertEqual(dlg._stage_agents_map[key], "Groq")
        fake_dlg.set_busy.assert_called_once_with(False)
        fake_dlg.set_answer.assert_called_once_with(
            "Nylon 6 needs drying.", "Groq")

    def test_an_agent_followup_resumes_the_same_chat_not_a_fresh_one(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.ask.set_text("which material fits best?")
        key = f"ask · {m['report']['stem']}"
        dlg._responses[key] = ["PP for cost."]
        dlg._links[key] = "https://claude.ai/chat/abc"
        dlg._stage_agents_map[key] = "Claude"   # Claude answered first
        _CaptureWorker.seen = {}
        with mock.patch.object(SD, "AutomationWorker", _CaptureWorker):
            dlg._on_answer_followup(mock.MagicMock(), m, key, "Claude",
                                    "what about Nylon 6?")
        seen = _CaptureWorker.seen
        stage_key, tool, prompts = seen["kwargs"]["custom_stages"][0]
        self.assertEqual((stage_key, tool), ("ask", "Claude"))
        self.assertEqual(prompts, ["what about Nylon 6?"])
        self.assertEqual(seen["kwargs"]["resume_urls"],
                         {"ask": "https://claude.ai/chat/abc"})
        self.assertIs(seen["kwargs"]["followup"], True)
        self.assertIs(seen["kwargs"]["failover"], False)

    def test_switching_agent_on_a_followup_does_not_resume_the_old_chat(self):
        """Claude answered first; the person picks ChatGPT in the popup's
        own "Reply as" row for the follow-up. There is no ChatGPT chat of
        theirs to resume, so it must start fresh — with the earlier Q&A
        folded into the prompt instead, the same way Groq's follow-up
        carries context, not with Claude's chat link."""
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.ask.set_text("which material fits best?")
        key = f"ask · {m['report']['stem']}"
        dlg._responses[key] = ["PP for cost."]
        dlg._links[key] = "https://claude.ai/chat/abc"
        dlg._stage_agents_map[key] = "Claude"
        _CaptureWorker.seen = {}
        with mock.patch.object(SD, "AutomationWorker", _CaptureWorker):
            dlg._on_answer_followup(mock.MagicMock(), m, key, "ChatGPT",
                                    "what about Nylon 6?")
        seen = _CaptureWorker.seen
        stage_key, tool, prompts = seen["kwargs"]["custom_stages"][0]
        self.assertEqual((stage_key, tool), ("ask", "ChatGPT"))
        self.assertIn("PP for cost.", prompts[0])
        self.assertIn("what about Nylon 6?", prompts[0])
        self.assertIsNone(seen["kwargs"]["resume_urls"])

    def test_a_successful_agent_followup_updates_response_link_and_agent(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        key = f"ask · {m['report']['stem']}"
        dlg._responses[key] = ["PP for cost."]
        dlg._stage_agents_map[key] = "Claude"
        fake_dlg = mock.MagicMock()
        dlg._on_answer_followup_agent_done(
            fake_dlg, key, "Claude", {"ask": ["Nylon 6 needs drying."]},
            {"ask": "https://claude.ai/chat/def"})
        self.assertEqual(dlg._responses[key], ["Nylon 6 needs drying."])
        self.assertEqual(dlg._links[key], "https://claude.ai/chat/def")
        self.assertEqual(dlg._stage_agents_map[key], "Claude")
        fake_dlg.set_answer.assert_called_once_with(
            "Nylon 6 needs drying.", "Claude")

    def test_a_silent_agent_followup_warns_instead_of_updating(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        key = f"ask · {m['report']['stem']}"
        dlg._responses[key] = ["PP for cost."]
        fake_dlg = mock.MagicMock()
        with mock.patch.object(SD.QMessageBox, "warning") as warn:
            dlg._on_answer_followup_agent_done(
                fake_dlg, key, "Claude", {}, {})
        warn.assert_called_once()
        fake_dlg.set_answer.assert_not_called()
        self.assertEqual(dlg._responses[key], ["PP for cost."])


class BuildThisWorksFromAnyFollowUpEvenReopenedOnes(unittest.TestCase):
    """Round: a follow-up typed into a REOPENED Answer popup (the file was
    already built once, that popup was closed, the person reattached the
    file and asked again) ran all the way through — ChatGPT even answered
    — but nothing ever got built, because the automatic plan/build only
    ever ran once, immediately after the very FIRST popup of a fresh Edit
    closed. A follow-up's refined answer had no way to become a build at
    all. "Build this" is that way, reachable from any popup at any time,
    not just the first one."""

    def test_the_button_only_exists_when_the_action_was_edit(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg._current = m
        dlg.ask.set_text("q")
        with mock.patch.object(SD, "AnswerDialog") as answer, \
                mock.patch.object(CB.config, "save_run"):
            dlg._action_buttons["ask"].setChecked(True)
            dlg._on_suggested("a")
            self.assertFalse(answer.call_args.kwargs["allow_build"])
            dlg._action_buttons["edit"].setChecked(True)
            dlg._on_suggested("a")
            self.assertTrue(answer.call_args.kwargs["allow_build"])

    def test_clicking_build_this_does_not_close_the_popup(self):
        dlg = AnswerDialog("t", "s", "q", "a", "Groq", allow_build=True)
        seen = []
        dlg.build_requested.connect(lambda: seen.append(1))
        dlg.build_btn.click()
        self.assertEqual(seen, [1])
        self.assertFalse(dlg.isHidden() and dlg.result())  # never accepted

    def test_build_this_runs_the_plan_stage_without_touching_the_queue(self):
        """The real scenario: a conversation reopened long after the
        first build finished. _current is whatever the fresh re-measure
        set it to; build_requested must plan from THAT model, and must
        never call _next() — there is no in-flight queue to advance."""
        dlg = _dialog(cfg={"agents": {"brains": "Claude"}})
        m = _fake_measured(dlg)
        dlg._current = m
        dlg.ask.set_text("enlarge the hole")
        key = f"ask · {m['report']['stem']}"
        dlg._responses[key] = ["enlarge the Ø8.1mm hole to Ø8.6mm"]
        fake_popup = mock.MagicMock()
        _CaptureWorker.seen = {}
        with mock.patch.object(SD, "AutomationWorker", _CaptureWorker):
            dlg._build_plan_for(m, key, fake_popup)
        fake_popup.set_busy.assert_called_with(True)
        seen = _CaptureWorker.seen
        stage_key, tool, prompts = seen["kwargs"]["custom_stages"][0]
        self.assertEqual((stage_key, tool), ("plan", "Claude"))
        self.assertIn("enlarge the Ø8.1mm hole to Ø8.6mm", prompts[0])

    def test_on_planned_from_a_popup_opens_the_review_but_never_advances_the_queue(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg.ask.set_text("fit 6mm")
        dlg._queue = [{"report": {"file": "someone-else.step"}}]  # must stay put
        plan = ('{"changes": [{"op": "enlarge_hole", "part": "p", '
                '"dia_mm": 8.1, "new_dia_mm": 8.6, "why": "test"}], '
                '"advice": []}')
        fake_popup = mock.MagicMock()
        with mock.patch.object(SD, "PlanReviewDialog") as review_dlg:
            review_dlg.return_value.exec.return_value = 0   # declined
            dlg._on_planned({"plan": [plan]}, {}, m=m, popup=fake_popup)
        fake_popup.set_busy.assert_any_call(False)
        self.assertEqual(len(dlg._queue), 1,
                         "a popup-triggered build must never touch the queue")

    def test_on_applied_from_a_popup_clears_busy_and_leaves_the_queue_alone(self):
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg._queue = [{"report": {"file": "someone-else.step"}}]
        fake_popup = mock.MagicMock()
        with mock.patch.object(SD.QDesktopServices, "openUrl"), \
                mock.patch.object(CB.config, "save_artifact"):
            dlg._on_applied(
                {"out": "/x/modified 2026-10-14 0700.step", "log": [],
                 "after": {"file": "Assem1.step", "parts": [],
                          "mode": "plastic", "overall_mm": (0, 0, 0),
                          "warnings": []},
                 "review": "/x/review.html"},
                m=m, popup=fake_popup)
        fake_popup.set_busy.assert_called_with(False)
        self.assertEqual(len(dlg._queue), 1)

    def test_on_applied_shows_the_green_banner_with_the_built_path(self):
        """Round: the same green "saved" confirmation _on_measured shows
        for the measurement folder went missing for a completed BUILD once
        "Build this" and the follow-up path were added — a build finished
        with no visible sign of where the modified file actually landed."""
        dlg = _dialog()
        m = _fake_measured(dlg)
        with mock.patch.object(SD.QDesktopServices, "openUrl"), \
                mock.patch.object(CB.config, "save_artifact"):
            dlg._on_applied(
                {"out": "/x/PET CORE - modified 2026-10-14 0700.step",
                 "log": [],
                 "after": {"file": "Assem1.step", "parts": [],
                          "mode": "plastic", "overall_mm": (0, 0, 0),
                          "warnings": []},
                 "review": "/x/review.html"},
                m=m, popup=mock.MagicMock())
        self.assertIn("PET CORE - modified 2026-10-14 0700.step",
                      dlg.files_label.text())
        self.assertTrue(dlg.meas_box.isVisibleTo(dlg))

    def test_the_automatic_first_build_still_advances_the_queue_exactly_once(self):
        """The ordinary, unchanged path: a fresh Edit's own first answer,
        never followed up on, still builds automatically (popup=None) and
        still finishes the run — this must not regress."""
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg._current = m
        dlg._queue = []
        dlg.ask.set_text("fit 6mm")
        dlg._action_buttons["edit"].setChecked(True)
        with mock.patch.object(SD, "AnswerDialog") as answer, \
                mock.patch.object(SD, "AutomationWorker", _CaptureWorker):
            dlg._on_suggested("enlarge the hole")
        answer.return_value.exec.assert_called_once()
        self.assertFalse(dlg._built_from_popup,
                         "the button was never clicked — only the "
                         "automatic path ran")
        stage_key, _tool, _prompts = _CaptureWorker.seen["kwargs"]["custom_stages"][0]
        self.assertEqual(stage_key, "plan")
        # Finish the chain by hand, as the real worker's `done` signal
        # would — _on_planned's default (m=None, popup=None) is exactly
        # this automatic path, and it must still reach _finish() once.
        # PlanReviewDialog must be mocked here too: _on_planned opens one
        # regardless of popup, and an unmocked one calls a real .exec()
        # that blocks forever with nothing to click it closed.
        with mock.patch.object(CB.config, "save_run") as saved, \
                mock.patch.object(SD, "PlanReviewDialog") as review_dlg:
            review_dlg.return_value.exec.return_value = 0   # Rejected/Close
            dlg._on_planned({"plan": ['{"changes": [], "advice": []}']}, {})
        saved.assert_called_once()

    def test_build_this_clicked_inside_the_first_popup_is_not_built_twice(self):
        """The bug this flag exists to prevent: "Build this" clicked
        during a fresh Edit's own first popup must not ALSO trigger the
        automatic build once that popup closes — that would plan and
        build the same request twice."""
        dlg = _dialog()
        m = _fake_measured(dlg)
        dlg._current = m
        dlg._queue = []
        dlg.ask.set_text("fit 6mm")
        key = f"ask · {m['report']['stem']}"
        dlg._responses[key] = ["enlarge the hole"]
        dlg._action_buttons["edit"].setChecked(True)
        fake_popup = mock.MagicMock()
        with mock.patch.object(SD, "AnswerDialog", return_value=fake_popup), \
                mock.patch.object(SD, "AutomationWorker", _CaptureWorker):
            # Simulate clicking "Build this" while the popup is open —
            # _build_plan_for sets the flag before .exec() ever returns.
            fake_popup.exec.side_effect = (
                lambda: dlg._build_plan_for(m, key, fake_popup))
            with mock.patch.object(CB.config, "save_run") as saved:
                dlg._on_suggested("enlarge the hole")
        # _on_suggested's own continuation must have taken the "already
        # built" branch — straight to _next()/_finish(), no second plan
        # stage queued.
        self.assertFalse(dlg._built_from_popup, "must be cleared after use")
        saved.assert_called_once()


class TheGuardsSpeakBeforeAnythingRuns(unittest.TestCase):
    """Real QMessageBox.warning calls, patched so a headless run does not
    block — the guard itself is what is being proven."""

    def test_ask_without_a_question_is_refused(self):
        dlg = _dialog()
        dlg._on_files_added(["/nowhere/a.step"])
        dlg._action_buttons["ask"].setChecked(True)
        with mock.patch.object(SD.QMessageBox, "warning") as warn, \
                mock.patch.object(SD, "StepMeasureWorker") as worker:
            dlg._generate()
            warn.assert_called_once()
            worker.assert_not_called()

    def test_draft_needs_no_configured_image_tool(self):
        """Draft is ChatGPT's job regardless of what Agents says, so a cfg
        with no visual tool at all still measures and drafts."""
        dlg = _dialog(cfg={"agents": {"brains": "Claude"}, "api_key": "k",
                           "step_out_dir": tempfile.mkdtemp()})
        dlg._on_files_added(["/nowhere/a.step"])
        with mock.patch.object(SD.QMessageBox, "warning") as warn, \
                mock.patch.object(SD, "StepMeasureWorker") as worker, \
                mock.patch.object(CB.config, "save"):
            dlg._generate()
            warn.assert_not_called()
            worker.assert_called_once()

    def test_edit_without_a_reasoning_tool_is_refused(self):
        dlg = _dialog(cfg={"agents": {"visual": "ChatGPT"}, "api_key": "k",
                           "step_out_dir": tempfile.mkdtemp()})
        dlg._on_files_added(["/nowhere/a.step"])
        dlg.ask.set_text("fit 6mm")
        dlg._action_buttons["edit"].setChecked(True)
        with mock.patch.object(SD.QMessageBox, "warning") as warn, \
                mock.patch.object(SD, "StepMeasureWorker") as worker:
            dlg._generate()
            warn.assert_called_once()
            worker.assert_not_called()


@unittest.skipUnless(HAVE_CAD, "cadquery not installed")
class ARealModelLandsWhereItWasSent(unittest.TestCase):
    """One real measurement through the dialog's own worker: the folder is
    named after the model, under the chosen root, and every file inside
    carries the model's name."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="prism-test-step-root-")
        src = tempfile.mkdtemp()
        cls.model = os.path.join(src, "Bracket A.step")
        _box_step(cls.model)
        cls.dlg = _dialog(root=cls.root)
        cls.dlg._on_files_added([cls.model])
        cls.dlg.mode_combo.setCurrentText("plastic")
        # Draft is the default action; the AI stage is opt-in since Round
        # 42, and this class's own test below wants it ON so it can check
        # what that stage is handed. Checking it also stops the queue at
        # the measurement by intercepting the AI stage.
        cls.dlg.ai_draft_cb.setChecked(True)
        #
        # The measuring worker runs SYNCHRONOUSLY — start() replaced by
        # run() on the calling thread, so its signals deliver straight into
        # the dialog's slots with no event loop. Spinning processEvents()
        # here to wait for a real thread is what aborted the whole suite:
        # it delivered a zero-delay modal leaked by an inquiry-dialog test
        # that ran earlier, with nobody to click it.
        with mock.patch.object(SD, "AutomationWorker", _CaptureWorker), \
                mock.patch.object(SD.StepMeasureWorker, "start",
                                  lambda worker: worker.run()), \
                mock.patch.object(CB.config, "save"), \
                mock.patch.object(CB.config, "save_artifact"):
            cls.dlg._generate()
        if not cls.dlg.models:
            raise unittest.SkipTest("measuring did not finish")

    def test_the_folder_is_named_after_the_model_under_the_root(self):
        m = self.dlg.models[0]
        self.assertEqual(m["out_dir"], os.path.join(self.root, "Bracket A"))

    def test_every_file_carries_the_models_name(self):
        m = self.dlg.models[0]
        files = os.listdir(m["out_dir"])
        self.assertTrue(files)
        for f in files:
            self.assertTrue(f.startswith("Bracket A - "), f)
        self.assertIn("Bracket A - dimensions.xlsx", files)
        self.assertIn("Bracket A - drawing sheet.png", files)

    def test_the_numbers_are_on_screen_and_the_folder_is_named(self):
        text = self.dlg.meas_view.toPlainText()
        self.assertIn("60.00 x 40.00 x 8.00", text)
        self.assertIn("plastic moulding", text)
        self.assertIn(self.dlg.models[0]["out_dir"], self.dlg.files_label.text())
        self.assertTrue(self.dlg.folder_btn.isEnabled())

    def test_the_draft_stage_was_handed_prisms_render_only(self):
        seen = _CaptureWorker.seen
        self.assertTrue(seen.get("started"))
        for a in seen["args"][2]:
            self.assertFalse(a["path"].lower().endswith((".step", ".stp")))
            self.assertTrue(a["path"].startswith(self.root))


@unittest.skipUnless(HAVE_CAD, "OCP/CadQuery not installed")
class KnowingARealFlatSizeSolvesTheKFactor(unittest.TestCase):
    """The shop-floor-facing side of solve_k_factor: pick a part, say
    which side and the true figure, get the K-factor back — checked
    against the same real, customer-verified job as
    TheFlatPatternOfTheCustomersEnclosure in test_stepfile.py, not a
    synthetic box. No worker, no event loop needed — the box only ever
    reads report["_shapes"], already sitting in self.models once a
    measurement has completed."""

    @classmethod
    def setUpClass(cls):
        real = sample_jobs.path("step_file_demo", "Assem1.STEP")
        cls.report = SF.analyse(real, mode="metal")
        cls.dlg = _dialog()
        cls.dlg.models = [{"report": cls.report}]
        cls.dlg._fill_kfit_parts(cls.dlg.models)

    def test_only_parts_with_a_flat_pattern_are_offered(self):
        offered = {cls_data[1] for cls_data in
                   (self.dlg.kfit_part_combo.itemData(i)
                    for i in range(self.dlg.kfit_part_combo.count()))}
        for name in ("top", "bottom", "side"):
            self.assertIn(name, offered)

    def test_the_true_width_this_part_was_measured_at_solves_back_to_it(self):
        bottom = next(p for p in self.report["parts"] if p["name"] == "bottom")
        true_w = bottom["flat"]["flat_size_mm"][0]
        idx = next(i for i in range(self.dlg.kfit_part_combo.count())
                  if self.dlg.kfit_part_combo.itemData(i)[1] == "bottom")
        self.dlg.kfit_part_combo.setCurrentIndex(idx)
        self.dlg.kfit_axis_combo.setCurrentIndex(0)     # width
        self.dlg.kfit_target_edit.setText(f"{true_w:.2f}")
        self.dlg._kfit_solve()
        self.assertIn("reproduces that size exactly", self.dlg.kfit_result.text())
        self.assertIsNotNone(self.dlg._kfit_solved)
        solved = self.dlg._kfit_solved
        self.dlg._kfit_apply()
        self.assertEqual(self.dlg.k_edit.text(), f"{solved:g}")

    def test_a_figure_that_cannot_be_this_part_says_so_plainly(self):
        idx = 0
        self.dlg.kfit_part_combo.setCurrentIndex(idx)
        self.dlg.kfit_target_edit.setText("999999")
        self.dlg._kfit_solve()
        self.assertIn("doesn't fit", self.dlg.kfit_result.text())
        self.assertIsNone(self.dlg._kfit_solved)


class ItIsOnTheShelfAndInHistory(unittest.TestCase):
    """Everything the shell knows about STEP it reads off the manifest --
    the rail row, the Home card, History's run attribution and the licence
    gate. These pin that the manifest says what the dialog does."""

    def test_it_is_registered_and_gated_on_its_own_key(self):
        from addons import registry
        a = registry.by_key("step")
        self.assertIsNotNone(a)
        self.assertEqual(a.label, "STEP")
        self.assertEqual(a.feature, "step")
        self.assertEqual(a.screen, "step")
        self.assertEqual(a.engine, ("stepfile",))

    def test_it_is_on_the_rail_with_a_real_icon(self):
        from widgets import icons, sidebar
        entry = next(e for e in sidebar.ADDONS if e[0] == "step")
        self.assertEqual(entry[1], "STEP")
        self.assertEqual(entry[4], "step")
        self.assertIn(entry[2], set(icons._STROKED) | set(icons._FILLED))

    def test_history_recognises_its_runs(self):
        from addons import registry
        from widgets.panel_base import _kind_of, ADDONS
        self.assertEqual(registry.kind_of("STEP — Draft: Assem1.STEP"), "step")
        self.assertEqual(_kind_of("STEP — Draft: Assem1.STEP"), "step")
        self.assertEqual(_kind_of("/step-ask plastic x.stp q"), "step")
        self.assertEqual(_kind_of("/step-auto plastic x.stp"), "step")
        self.assertEqual(ADDONS["step"], "STEP")

    def test_the_front_door_names_its_tools(self):
        from addons.step.panel import StepPanel
        panel = StepPanel({"agents": {"visual": "ChatGPT", "brains": "Claude"}})
        roles = panel.tool_roles()
        self.assertEqual([r[3] for r in roles], ["ChatGPT", "Claude"])
        self.assertEqual(panel.KIND, "step")

    def test_the_offer_takes_plain_paths(self):
        """The intent contract: paths in, and the dialog does its own
        shaping -- only models are kept, and a caller by intent needs to
        know nothing about what a model is."""
        from addons import names, registry
        owner, handler = registry.offering(names.MEASURE_MODEL)
        self.assertEqual(owner.key, "step")
        opened = {}

        class FakeDialog:
            def __init__(self, cfg, attachments, parent):
                opened["attachments"] = attachments
                self.paths = []

            def _on_files_added(self, paths):
                opened["paths"] = paths

            def exec(self):
                opened["shown"] = True

        with mock.patch.object(SD, "StepDialog", FakeDialog):
            registry.resolve(handler)(None, {}, ["/x/a.step", "/x/q.pdf"])
        self.assertEqual(opened["paths"], ["/x/a.step", "/x/q.pdf"])
        self.assertEqual(opened["attachments"], [])
        self.assertTrue(opened["shown"])


class TheWindowRoutesIt(GateTest):
    """The route from the rail to the screen, and from the screen's button
    to the dialog, asserted on a real window -- not by reading source."""

    def test_the_rail_key_lands_on_the_step_screen(self):
        import main_window
        self.grant(EVERYTHING)
        win = self._window()
        # The gate itself is a network round trip on a worker thread --
        # tests/test_addon_gates.py proves the gate; this proves the route
        # behind it, so the gate is stepped over here the same way.
        with mock.patch.object(main_window.MainWindow, "_authorized_then",
                               lambda self, feature, action, then: then()):
            win._handle_command("step")
        self.assertEqual(win.screens.currentIndex(),
                         main_window.SCREEN_INDEX["step"])
        self.assertIs(win.screens.currentWidget(), win.step_panel)

    def test_the_screens_button_opens_the_dialog_when_cadquery_is_there(self):
        import main_window
        self.grant(EVERYTHING)
        win = self._window()
        with mock.patch.object(CB, "step_available", return_value=(True, "")), \
                mock.patch.object(main_window, "StepDialog") as dlg, \
                mock.patch.object(main_window.MainWindow,
                                  "_offer_followup_for_dialog") as offered:
            win.step_panel.opened.emit()
        dlg.assert_called_once_with(win.cfg, win.attachments, win)
        dlg.return_value.exec.assert_called_once()
        # Deliberately NOT offered: that generic follow-up can only ever
        # save a refined TEXT answer, never actually build a file — a
        # customer hit that dead end twice (here and via History's own
        # "Follow up" button, the identical code). STEP's own Answer
        # popup is the one place a follow-up can become a real build now
        # ("Build this" — tests/test_answer_dialog.py,
        # BuildThisWorksFromAnyFollowUpEvenReopenedOnes below), so this
        # door is closed rather than left open and misleading.
        offered.assert_not_called()

    def test_without_cadquery_it_says_so_and_opens_nothing(self):
        import main_window
        self.grant(EVERYTHING)
        win = self._window()
        with mock.patch.object(CB, "step_available",
                               return_value=(False, "no cadquery")), \
                mock.patch.object(main_window, "StepDialog") as dlg, \
                mock.patch.object(main_window.QMessageBox, "information") as box:
            win.step_panel.opened.emit()
        dlg.assert_not_called()
        self.assertIn("cadquery", box.call_args[0][2])

    def test_it_is_paywalled_without_its_feature(self):
        """Also covered by tests/test_addon_gates.py; kept here so the
        add-on's own file says what it costs."""
        self.grant([f for f in EVERYTHING if f != "step"])
        win = self._window()
        with mock.patch.object(type(win), "_show_screen") as shown:
            win._handle_command("step")
        self.assertIn("step", self.paywalled)
        shown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
