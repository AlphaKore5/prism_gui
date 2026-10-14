"""STEP add-on — measure a 3D model, then draft, ask or edit. No AI sees it.

The GUI face of the terminal's /step, /step-auto and /step-ask, on the same
rule as Gerber: the customer's STEP file is their product, and it never
leaves this machine. core.stepfile measures it here; the only things that
ever reach an AI are the measured NUMBERS and Prism's own plain render of
the parts (a PNG Prism drew, not the model). The three actions:

    Draft  — measure, then the image tool draws a dimensioned drawing sheet
             FROM THE NUMBERS (auto_brief) — the model stays here.
    Ask    — measure, then Groq suggests improvements from the numbers and
             the question. That answer IS the deliverable — nothing is
             planned, nothing is built, no page opens.
    Edit   — measure, get Groq's suggestions, then a reviewing agent turns
             them into an exact change plan shown on a review page; after
             the person confirms against that page, the plan is applied to
             a COPY of the model, locally, and the copy is re-measured so
             the After column is real, not predicted.

Several models can be attached at once; each is measured into its own
folder, named after it, under the folder the person chose (asked once, the
first time, and kept in cfg["step_out_dir"]). Every file inside carries the
model's own name — see core.stepfile.names().
"""
from __future__ import annotations

import json
import os
import shutil

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QProgressBar, QRadioButton, QTextBrowser, QVBoxLayout, QWidget,
)

import core_bridge as CB
import i18n
import theme
from dialogs.answer_dialog import AnswerDialog
from dialogs.base import PrismDialog
from workers import AutomationWorker
from addons.step.workers import (StepApplyWorker, StepAskWorker,
                                 StepMeasureWorker)
from widgets import icons
from widgets.ask_panel import AskPanel

MODEL_EXTS = (".step", ".stp")

# (key, label, what it does) — the order they are offered in.
ACTIONS = (
    ("draft", "Draft",
     "Measure and draw the dimensioned sheet here — flat pattern, "
     "isometric, every hole sized and placed on the drawing itself — no "
     "AI. ChatGPT drawing a second, styled copy is optional (below); "
     "compared against Prism's own sheet it turned out to just trace the "
     "picture it was shown, text and all, worse — it is not an "
     "independent check on the numbers, only a different look."),
    ("ask", "Ask",
     "Measure, then get suggestions for the part from the numbers and your "
     "question. Just the answer — nothing is planned, built or opened."),
    ("edit", "Edit",
     "Measure, get suggestions, then review an exact change plan and — "
     "once you confirm — apply it to a COPY of the model, here, and "
     "re-measure it. The original is never touched."),
)

# What the footer's one button says and does, per selected action — so the
# single button a person must press always names the actual result ("Make
# the Changes", not a generic "Generate") instead of making them trust a
# separate radio choice they might not remember making.
ACTION_BUTTON = {
    "draft": ("Measure and Draw", "grid"),
    "ask": ("Get the Answer", "chat"),
    "edit": ("Make the Changes", "pencil"),
}

# (cfg value, label) — who answers Ask/Edit's question. Groq is a direct,
# near-instant API call; the other three are the SAME background-Chrome
# automation Draft and Edit's plan stage already use to reach a tool —
# slower (roughly 10-60s), but a stronger model than the small one Groq
# runs here.
MODEL_CHOICES = (
    ("Groq", "Groq (fast, in-house)"),
    ("ChatGPT", "ChatGPT"),
    ("Claude", "Claude"),
)

# Deliberately no Gemini. "Google Gemini" is registered in agents._MAKES as
# an image generator — core.automation._maker_brief() wraps EVERY stage
# routed to that name with "what I need from you is generated images...
# build it here", regardless of what the stage's own prompt says, by
# design (it exists specifically to override a text-shaped ask). A plain
# Q&A prompt sent to it comes back as a refused image request, not an
# answer — confirmed live. Fixable only by giving Gemini a second,
# non-maker agent identity in the engine; out of scope here, so it is left
# out rather than shipped broken.
#
# If the chosen model can't answer, retry in this fixed, quality-ordered
# chain — never silently back to Groq, which is the thing being upgraded
# away from. Whichever was already tried as the primary pick is skipped.
FALLBACK_ORDER = ("ChatGPT", "Claude")


class PlanReviewDialog(PrismDialog):
    """The review page, shown inside Prism instead of a separate browser
    tab. Opening an external page and then immediately asking Yes/No in a
    native popup used to race for focus — the browser usually won, so the
    confirm sat there unseen behind it, and a build that looked declined
    was really just never answered. Loading the SAME generated HTML here
    removes the race outright: nothing can end up behind anything else."""

    def __init__(self, title: str, subtitle: str, review_path: str,
                can_build: bool, parent=None):
        super().__init__(title, subtitle, icon="pencil", parent=parent)
        self.resize(880, 680)
        self.setMinimumSize(560, 420)
        self.review_path = review_path

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.setSource(QUrl.fromLocalFile(review_path))
        self.body.addWidget(self.view, stretch=1)

        self.footer.add_utility(self.button(
            i18n.t("Open as a file"), on_click=self._open_file))
        if can_build:
            self.footer.add_secondary(self.button(
                i18n.t("Cancel"), on_click=self.reject))
            self.footer.set_primary(self.button(
                i18n.t("Build it"), "primary", on_click=self.accept))
        else:
            self.footer.set_primary(self.button(
                i18n.t("Close"), "primary", on_click=self.accept))

    def _open_file(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.review_path))


class StepDialog(PrismDialog):
    def __init__(self, cfg: dict, attachments: list, parent=None):
        super().__init__(
            i18n.t("STEP"),
            i18n.t("Attach a 3D model. It is measured here, on this machine "
                   "— no AI ever sees the STEP file."),
            icon="grid", parent=parent, closable=False, scrollable=True)
        self.setWindowTitle("STEP — 3D model measurement")
        self.resize(820, 820)
        self.setMinimumSize(620, 520)
        self.cfg = cfg
        self.sf = CB.get_stepfile()

        self.paths: list[str] = []
        # Once measured: [{"path", "report", "out_dir", "drawn", "xlsx"}]
        self.models: list[dict] = []
        self._queue: list[dict] = []      # models still waiting for the action
        self._current: dict | None = None
        self._worker = None
        self._agent_worker = None
        self._ask_worker = None
        self._apply_worker = None
        self._followup_ask_worker = None
        self._followup_agent_worker = None
        self._built_from_popup = False
        self._links: dict = {}
        self._responses: dict = {}
        self._stage_agents_map: dict = {}
        self._model_chain: list[str] = []
        self._made_files: list = []
        self._notes: list[str] = []

        root = self.body
        root.setSpacing(theme.ROW_GAP)

        # ── 1 · the model first ────────────────────────────────────────
        # The file comes before the question, in that order on screen: the
        # question and the choice of action only appear once a model is
        # attached, because nothing below makes sense without one.
        title = QLabel(i18n.t("1 · Attach the STEP model"))
        title.setObjectName("h4")
        root.addWidget(title)
        hint = QLabel(i18n.t("Add the .step / .stp file — several at once "
                             "is fine. What to do with it comes next."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.NEUTRAL[700]}; font-size: 12.5px;")
        root.addWidget(hint)

        self.ask = AskPanel(
            "For Ask and Edit, say what you want — e.g. \"how do I make "
            "this lighter?\" or \"fit M8 bolts instead of M6\". Draft needs "
            "no text.")
        self.ask.files_added.connect(self._on_files_added)
        self.ask.file_removed.connect(self._on_file_removed)
        root.addWidget(self.ask)

        # The confidentiality promise, stated as a real notice — same as
        # Gerber, because it is the same promise and the reason this sells.
        lock = QFrame()
        lock.setObjectName("stepLock")
        lock.setAttribute(Qt.WA_StyledBackground, True)
        lock.setStyleSheet(
            f"#stepLock {{ background: {theme.OK_BG};"
            f" border: 1px solid {theme.OK};"
            f" border-radius: {theme.R_CONTROL}px; }}")
        lock_row = QHBoxLayout(lock)
        lock_row.setContentsMargins(theme.SPACE_3, theme.SPACE_3,
                                    theme.SPACE_3, theme.SPACE_3)
        lock_row.setSpacing(theme.SPACE_3)
        glyph = QLabel()
        glyph.setPixmap(icons.pixmap("lock", 17, theme.OK_INK))
        glyph.setAlignment(Qt.AlignTop)
        lock_row.addWidget(glyph)
        lock_text = QLabel(
            "The STEP file never leaves this machine. Draft, Ask and Edit "
            "show an AI only the measured NUMBERS and Prism's own plain "
            "render of the parts — never the model, never a path. Edits are "
            "made here, on a copy.")
        lock_text.setWordWrap(True)
        lock_text.setStyleSheet(f"color: {theme.OK_INK}; font-size: 13px;")
        lock_row.addWidget(lock_text, stretch=1)
        root.addWidget(lock)

        # ── options: material, and where the files go ──────────────────
        opt_box = QGroupBox(i18n.t("Options"))
        opt_v = QVBoxLayout(opt_box)
        opt_v.setSpacing(theme.SPACE_2)
        mat_row = QHBoxLayout()
        mat_row.addWidget(QLabel(i18n.t("Material")))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(list(self.sf.MODES))
        self.mode_combo.setCurrentText(self.cfg.get("step_mode") or "metal")
        mat_row.addWidget(self.mode_combo)
        mat_note = QLabel(i18n.t("— sheet metal reads thickness and weight "
                                 "in steel; plastic reads wall and ABS/PP/PC"))
        mat_note.setStyleSheet(
            f"color: {theme.NEUTRAL[700]}; font-size: 12.5px;")
        mat_row.addWidget(mat_note)
        mat_row.addStretch(1)
        opt_v.addLayout(mat_row)

        # The bend-allowance K-factor a flat pattern is unfolded with —
        # theirs if they know it, Prism's own default if they don't. Never
        # asked before every model; kept in cfg like everything else here,
        # and the drawing sheet always states which one was actually used
        # (core.stepfile.analyse's own warning), so a blank box quietly
        # becoming the default is never mistaken for a confirmed shop value.
        k_row = QHBoxLayout()
        k_row.addWidget(QLabel(i18n.t("Bend K-factor")))
        self.k_edit = QLineEdit()
        self.k_edit.setPlaceholderText(f"default {self.sf._DEFAULT_K_FACTOR:g}")
        self.k_edit.setMaximumWidth(90)
        self.k_edit.setText(str(self.cfg.get("step_k_factor") or ""))
        k_row.addWidget(self.k_edit)
        k_note = QLabel(i18n.t("— only for a metal flat pattern; leave "
                               "blank unless your shop gives you one"))
        k_note.setStyleSheet(f"color: {theme.NEUTRAL[700]}; font-size: 12.5px;")
        k_row.addWidget(k_note)
        k_row.addStretch(1)
        opt_v.addLayout(k_row)

        # Where everything for a model goes. Asked ONCE, the first time
        # Generate is pressed (see _ensure_root), and shown here so the
        # answer is never a mystery and can be changed at any time.
        dir_row = QHBoxLayout()
        self.root_label = QLabel(self._root_caption())
        self.root_label.setWordWrap(True)
        dir_row.addWidget(self.root_label, stretch=1)
        dir_row.addWidget(self.button(i18n.t("Change folder…"), "secondary",
                                      small=True, on_click=self._pick_root))
        self.root_default_btn = self.button(i18n.t("Use the Desktop"),
                                            "secondary", small=True,
                                            on_click=self._use_default_root)
        self.root_default_btn.setVisible(bool(self.cfg.get("step_out_dir")))
        dir_row.addWidget(self.root_default_btn)
        opt_v.addLayout(dir_row)
        root.addWidget(opt_box)

        # ── 2 · then what to do with it ────────────────────────────────
        # Hidden until a model is attached. The question box and the Speak
        # button are the AskPanel's own, reparented down here so the page
        # reads top to bottom: the file, then the ask, then the action.
        self.step2 = QWidget()
        step2_v = QVBoxLayout(self.step2)
        step2_v.setContentsMargins(0, 0, 0, 0)
        step2_v.setSpacing(theme.ROW_GAP)
        title2 = QLabel(i18n.t("2 · What do you want done with it?"))
        title2.setObjectName("h4")
        step2_v.addWidget(title2)
        step2_v.addWidget(self.ask.edit)
        mic_row = QHBoxLayout()
        mic_row.addWidget(self.ask.mic_btn)
        mic_row.addStretch(1)
        step2_v.addLayout(mic_row)
        act_box = QGroupBox(i18n.t("What to do"))
        act_v = QVBoxLayout(act_box)
        act_v.setSpacing(theme.SPACE_2)
        self._action_group = QButtonGroup(self)
        self._action_buttons: dict[str, QRadioButton] = {}
        for key, label, blurb in ACTIONS:
            row = QWidget()
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(theme.SPACE_2)
            radio = QRadioButton(i18n.t(label))
            radio.setProperty("action", key)
            self._action_group.addButton(radio)
            self._action_buttons[key] = radio
            row_l.addWidget(radio)
            note = QLabel(i18n.t(blurb))
            note.setWordWrap(True)
            note.setStyleSheet(
                f"color: {theme.NEUTRAL[700]}; font-size: 12.5px;")
            row_l.addWidget(note, stretch=1)
            act_v.addWidget(row)
        self._action_buttons["draft"].setChecked(True)

        # Off by default: checked against Prism's own drawing, ChatGPT's
        # "styled" copy just traced it, worse — same numbers, garbled
        # text (see ACTIONS' own note above). Not deleted, because a
        # differently-styled picture for sending to someone outside the
        # shop is still a real, if occasional, reason to want one; it is
        # just no longer something Draft spends a minute on unasked.
        self.ai_draft_cb = QCheckBox(i18n.t(
            "Also ask ChatGPT to draw a styled copy (optional — not an "
            "independent check; see above)"))
        self.ai_draft_cb.setChecked(bool(self.cfg.get("step_ai_draft")))
        indent = QWidget()
        indent_l = QHBoxLayout(indent)
        indent_l.setContentsMargins(28, 0, 0, 0)
        indent_l.addWidget(self.ai_draft_cb)
        act_v.addWidget(indent)
        step2_v.addWidget(act_box)

        # Who answers Ask/Edit's question — only matters once a question is
        # actually asked, but shown alongside the action so the choice is
        # made before pressing Generate, not discovered after.
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel(i18n.t("Answer with:")))
        self.model_combo = QComboBox()
        for key, label in MODEL_CHOICES:
            self.model_combo.addItem(i18n.t(label), key)
        saved_model = self.cfg.get("step_ask_model", "Groq")
        idx = self.model_combo.findData(saved_model)
        self.model_combo.setCurrentIndex(idx if idx >= 0 else 0)
        model_row.addWidget(self.model_combo)
        model_row.addStretch(1)
        step2_v.addLayout(model_row)
        model_hint = QLabel(i18n.t(
            "Groq answers in seconds. ChatGPT and Claude are stronger but "
            "slower — driven in a background Chrome window. If the one "
            "you pick can't answer, Prism tries the other one."))
        model_hint.setWordWrap(True)
        model_hint.setStyleSheet(
            f"color: {theme.NEUTRAL[700]}; font-size: 12.5px;")
        step2_v.addWidget(model_hint)

        self.step2.setVisible(False)
        root.addWidget(self.step2)

        # Only appears once a model has actually been measured.
        self.meas_box = QGroupBox(i18n.t("Measured — not by an AI"))
        meas_l = QVBoxLayout(self.meas_box)
        self.meas_view = QPlainTextEdit()
        self.meas_view.setReadOnly(True)
        self.meas_view.setMinimumHeight(220)
        meas_l.addWidget(self.meas_view)
        self.files_label = QLabel("")
        self.files_label.setWordWrap(True)
        self.files_label.setStyleSheet(
            f"color: {theme.OK_INK}; background: {theme.OK_BG};"
            f" border-radius: {theme.R_CONTROL}px;"
            f" padding: {theme.SPACE_2}px {theme.SPACE_3}px;"
            f" font-size: 13px;")
        meas_l.addWidget(self.files_label)
        self.meas_box.setVisible(False)
        root.addWidget(self.meas_box, stretch=1)

        # Back-solve the K-factor: the shop already knows the true flat
        # size of a part they've cut before (from a past job, or a
        # fabricator's own reference sheet) — this turns that one known
        # number into the K-factor that reproduces it, instead of asking
        # them to guess-and-check against Prism's default. Only appears
        # once something has actually been measured and unfolded.
        self.kfit_box = QGroupBox(i18n.t(
            "Know a part's real flat size? Back-solve the K-factor"))
        kfit_v = QVBoxLayout(self.kfit_box)
        kfit_v.setSpacing(theme.SPACE_2)
        kfit_note = QLabel(i18n.t(
            "Pick the part, say which side you know (from a past job or "
            "the fabricator's own sheet) and its true length — Prism works "
            "out the K-factor that would have produced exactly that."))
        kfit_note.setWordWrap(True)
        kfit_note.setStyleSheet(f"color: {theme.NEUTRAL[700]}; font-size: 12.5px;")
        kfit_v.addWidget(kfit_note)
        kfit_row = QHBoxLayout()
        self.kfit_part_combo = QComboBox()
        kfit_row.addWidget(self.kfit_part_combo, stretch=1)
        self.kfit_axis_combo = QComboBox()
        self.kfit_axis_combo.addItem(i18n.t("Width"), "w")
        self.kfit_axis_combo.addItem(i18n.t("Height"), "h")
        kfit_row.addWidget(self.kfit_axis_combo)
        self.kfit_target_edit = QLineEdit()
        self.kfit_target_edit.setPlaceholderText(i18n.t("true size, mm"))
        self.kfit_target_edit.setMaximumWidth(110)
        kfit_row.addWidget(self.kfit_target_edit)
        kfit_row.addWidget(self.button(i18n.t("Solve"), "secondary",
                                       small=True, on_click=self._kfit_solve))
        kfit_v.addLayout(kfit_row)
        result_row = QHBoxLayout()
        self.kfit_result = QLabel("")
        self.kfit_result.setWordWrap(True)
        result_row.addWidget(self.kfit_result, stretch=1)
        self.kfit_use_btn = self.button(i18n.t("Use this K-factor"),
                                        "secondary", small=True,
                                        on_click=self._kfit_apply)
        self.kfit_use_btn.setVisible(False)
        result_row.addWidget(self.kfit_use_btn)
        kfit_v.addLayout(result_row)
        self._kfit_solved: float | None = None
        self.kfit_box.setVisible(False)
        root.addWidget(self.kfit_box)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setPlaceholderText(
            i18n.t("What the AI drew, suggested or planned appears here."))
        self.result.setMinimumHeight(120)
        root.addWidget(self.result)

        self.folder_btn = self.button(i18n.t("Open folder"), "secondary",
                                      icon_name="folder", small=True,
                                      on_click=self._open_folder)
        self.folder_btn.setEnabled(False)
        self.footer.add_utility(self.folder_btn)
        self.open_btn = self.button(i18n.t("Open in browser"), "secondary",
                                    icon_name="external", small=True,
                                    on_click=self._open_link)
        self.open_btn.setEnabled(False)
        self.footer.add_utility(self.open_btn)
        self.footer.add_secondary(
            self.button(i18n.t("Close"), on_click=self.reject))
        draft_label, draft_icon = ACTION_BUTTON["draft"]
        self.generate_btn = self.button(i18n.t(draft_label), "primary",
                                        icon_name=draft_icon,
                                        on_click=self._generate)
        self.generate_btn.setEnabled(False)
        self.generate_btn.setToolTip(i18n.t("Attach a model first"))
        self.footer.set_primary(self.generate_btn)
        # The one button a person must press always names the action it is
        # about to take — never a generic "Generate" they have to trust a
        # radio choice above it to interpret correctly.
        for radio in self._action_buttons.values():
            radio.toggled.connect(
                lambda checked: self._sync_generate_label() if checked
                else None)

        if attachments:
            self._on_files_added([a["path"] for a in attachments])

    # ── where the files go ───────────────────────────────────────────────

    def _root(self) -> str:
        return self.cfg.get("step_out_dir") or self.sf.DEFAULT_OUT_ROOT

    def _root_caption(self) -> str:
        return (i18n.t("Files go to {folder} — a folder per model, every "
                       "file named after the model.")
                .replace("{folder}", self._root()))

    def _pick_root(self) -> bool:
        path = QFileDialog.getExistingDirectory(
            self, i18n.t("Where should Prism keep the files for your STEP "
                         "models?"), self._root())
        if not path:
            return False
        self.cfg["step_out_dir"] = path
        CB.config.save(self.cfg)
        self.root_label.setText(self._root_caption())
        self.root_default_btn.setVisible(True)
        return True

    def _use_default_root(self):
        self.cfg["step_out_dir"] = ""
        CB.config.save(self.cfg)
        self.root_label.setText(self._root_caption())
        self.root_default_btn.setVisible(False)

    def _ensure_root(self) -> bool:
        """The question the owner asked for: where do all the files for a
        model go? Asked once — the answer is kept in cfg — and only at the
        moment it matters, the first Generate. Choosing the Desktop stores
        the default explicitly, so the question is not asked again."""
        if self.cfg.get("step_out_dir"):
            return True
        box = QMessageBox(self)
        box.setWindowTitle(i18n.t("STEP"))
        box.setIcon(QMessageBox.Question)
        box.setText(i18n.t("Where should Prism keep the files for your STEP "
                           "models?"))
        box.setInformativeText(i18n.t(
            "Prism makes a folder named after each model inside it, and every "
            "file in that folder carries the model's name. You can change "
            "this any time from the Options box."))
        choose = box.addButton(i18n.t("Choose a folder…"),
                               QMessageBox.AcceptRole)
        desktop = box.addButton(i18n.t("Use the Desktop"),
                                QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(choose)
        box.exec()
        clicked = box.clickedButton()
        if clicked is choose:
            return self._pick_root()
        if clicked is desktop:
            self.cfg["step_out_dir"] = self.sf.DEFAULT_OUT_ROOT
            CB.config.save(self.cfg)
            self.root_label.setText(self._root_caption())
            self.root_default_btn.setVisible(True)
            return True
        return False

    # ── files ───────────────────────────────────────────────────────────

    def _on_files_added(self, paths: list):
        models, other = [], []
        for p in paths:
            if p and p.lower().endswith(MODEL_EXTS):
                if p not in self.paths:
                    models.append(p)
            elif p:
                other.append(os.path.basename(p))
        skipped = (i18n.t("Only .step / .stp models are measured — skipped: ")
                   + ", ".join(other)) if other else ""
        if not models:
            if skipped:
                self.status.setText(skipped)
            return
        self.paths += models
        self.ask.add_paths(models, emit=False)
        self.step2.setVisible(True)      # the file is in; now the ask
        self.generate_btn.setEnabled(True)
        self.generate_btn.setToolTip("")
        n = len(self.paths)
        self.status.setText(
            (i18n.t("{n} models attached. ").format(n=n) if n > 1
             else i18n.t("Model attached. "))
            + i18n.t("Now say what you want done with it, then press "
                     "Generate.")
            + (f"  {skipped}" if skipped else ""))

    def _on_file_removed(self, path: str):
        """The chip's own 'x' only ever touched AskPanel's private list —
        this keeps the dialog's real one (what Generate actually measures)
        in step with what the person sees attached."""
        if path in self.paths:
            self.paths.remove(path)
        self.step2.setVisible(bool(self.paths))
        self.generate_btn.setEnabled(bool(self.paths))
        n = len(self.paths)
        self.status.setText(
            i18n.t("{n} models attached.").format(n=n) if n else
            i18n.t("No model attached yet."))

    def _action(self) -> str:
        for key, radio in self._action_buttons.items():
            if radio.isChecked():
                return key
        return "draft"

    def _sync_generate_label(self):
        label, icon = ACTION_BUTTON[self._action()]
        self.generate_btn.setText(i18n.t(label))
        icons.button_icon(self.generate_btn, icon, 15, theme.CARD)

    def _mode(self) -> str:
        return self.mode_combo.currentText().strip() or "metal"

    def _chosen_model(self) -> str:
        return self.model_combo.currentData() or "Groq"

    def _k_factor(self) -> float:
        """0.0 means "use Prism's default" — a blank box, or anything
        that doesn't parse as a plausible K-factor (0 to 1; it is a
        fraction of the sheet's thickness, never more than one whole
        thickness), falls back to that rather than silently unfolding
        with whatever a typo left in the box."""
        text = self.k_edit.text().strip()
        if not text:
            return 0.0
        try:
            k = float(text)
        except ValueError:
            return 0.0
        return k if 0.0 < k < 1.0 else 0.0

    # ── generate: measure, then the chosen action per model ────────────

    def _agents(self) -> dict:
        return CB.config.active_agents(self.cfg) or {}

    # Draft is ChatGPT's job, full stop. Not "the configured visual tool",
    # not a fallback to whichever image model answers: its image model is
    # the one that draws a dimension sheet well from a numbers-only brief,
    # and a second, differently-wrong sheet from another tool is not a
    # rescue. The stage runs with failover off for the same reason.
    ARTIST = "ChatGPT"

    def _artist(self) -> str:
        return self.ARTIST

    def _planner(self) -> str:
        agents = self._agents()
        return next((agents[s] for s in ("brains", "content", "research")
                     if agents.get(s)), "")

    def _generate(self):
        if not self.paths:
            return
        action = self._action()
        question = self.ask.text().strip()
        if action in ("ask", "edit"):
            if not question:
                QMessageBox.warning(self, "STEP", i18n.t(
                    "Say what you want to know or change — type the "
                    "question in the box above."))
                return
            if self._chosen_model() == "Groq" and not self.cfg.get("api_key"):
                QMessageBox.warning(self, "STEP", i18n.t(
                    "Groq needs your key — add it in Settings, or pick "
                    "ChatGPT or Claude above instead."))
                return
        if action == "edit" and not self._planner():
            QMessageBox.warning(self, "STEP", i18n.t(
                "Edit needs a reasoning tool to review the plan — open "
                "Agents and pick one for Reasoning first."))
            return
        if not self._ensure_root():
            return

        self.cfg["step_mode"] = self._mode()
        self.cfg["step_k_factor"] = self.k_edit.text().strip()
        self.cfg["step_ai_draft"] = self.ai_draft_cb.isChecked()
        self.cfg["step_ask_model"] = self._chosen_model()
        try:
            CB.config.save(self.cfg)
        except Exception:                               # noqa: BLE001
            pass
        self.models = []
        self._responses, self._links, self._notes = {}, {}, []
        self.meas_view.clear()
        self.result.clear()
        self._set_busy(True, i18n.t(
            "Measuring — the model never leaves this machine…"))
        self._worker = StepMeasureWorker(list(self.paths), self._mode(),
                                         self._root(), self._k_factor())
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_measured)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, line: str):
        self.meas_view.appendPlainText(f"   {line}")

    def _on_measured(self, results: list):
        self.models = results
        blocks, files = [], []
        for m in results:
            report = m["report"]
            heading = (f"═══ {report['file']} ═══\n" if len(results) > 1
                       else "")
            blocks.append(heading + self.sf.report_text(report))
            files.append(m["out_dir"])
            drawn = m.get("drawn") or {}
            deliverables = [m.get("xlsx"), drawn.get("png"),
                            *drawn.get("flats", {}).values()]
            for path in deliverables:
                if path and os.path.exists(path):
                    try:
                        CB.config.save_artifact(path, os.path.basename(path),
                                                kind="step",
                                                task=report["file"])
                    except Exception:                   # noqa: BLE001
                        pass
        self.meas_view.setPlainText("\n\n".join(blocks))
        self.files_label.setText(
            i18n.t("Saved so every number can be checked → ")
            + "; ".join(files))
        self.meas_box.setVisible(True)
        self.folder_btn.setEnabled(True)
        self._fill_kfit_parts(results)
        self._queue = list(results)
        self._next()

    def _fill_kfit_parts(self, results: list):
        """Only the parts that actually unfolded to a flat pattern can
        have their K-factor back-solved — nothing to invert for a part
        with no flat size in the first place."""
        self.kfit_part_combo.clear()
        self.kfit_result.setText("")
        multi = len(results) > 1
        for i, m in enumerate(results):
            report = m["report"]
            for p in report["parts"]:
                if not p.get("flat"):
                    continue
                label = (f"{report['file']} — {p['name']}" if multi
                         else p["name"])
                self.kfit_part_combo.addItem(label, (i, p["name"]))
        self.kfit_box.setVisible(self.kfit_part_combo.count() > 0)

    def _kfit_solve(self):
        self.kfit_use_btn.setVisible(False)
        self._kfit_solved = None
        if self.kfit_part_combo.count() == 0:
            return
        idx = self.kfit_part_combo.currentIndex()
        model_i, part_name = self.kfit_part_combo.itemData(idx)
        axis = self.kfit_axis_combo.currentData()
        text = self.kfit_target_edit.text().strip()
        try:
            target = float(text)
        except ValueError:
            self.kfit_result.setText(i18n.t(
                "Enter the true size in millimetres first."))
            return
        report = self.models[model_i]["report"]
        k = self.sf.solve_k_factor(report, part_name, target, axis=axis)
        if k is None:
            self.kfit_result.setText(i18n.t(
                "That figure doesn't fit this part's own geometry — check "
                "the part, the side (width/height) and the number."))
            return
        self._kfit_solved = k
        self.kfit_result.setText(i18n.t(
            "K-factor {k} reproduces that size exactly.").replace(
            "{k}", f"{k:g}"))
        self.kfit_use_btn.setVisible(True)

    def _kfit_apply(self):
        if self._kfit_solved is None:
            return
        self.k_edit.setText(f"{self._kfit_solved:g}")
        self.kfit_result.setText(self.kfit_result.text() + "  " + i18n.t(
            "— now set as the Bend K-factor above; press Generate again to "
            "re-draw with it."))
        self.kfit_use_btn.setVisible(False)

    def _next(self):
        """The chosen action, one model at a time — an AI stage per model,
        in order, then the run is saved once."""
        if not self._queue:
            self._finish()
            return
        self._current = self._queue.pop(0)
        {"draft": self._draft, "ask": self._ask,
         "edit": self._ask}[self._action()](self._current)

    # ── draft ───────────────────────────────────────────────────────────

    def _draft(self, m: dict):
        report = m["report"]
        if not self.ai_draft_cb.isChecked():
            # Prism's own drawing sheet was already made in _on_measured —
            # that IS the deliverable now (Round 42: flat pattern + hole
            # positions marked on the drawing itself). Nothing left for an
            # AI to add unless the person actually asked for its copy.
            self._notes.append(f"{report['file']}: Prism's own drawing "
                               "sheet stands — ChatGPT's copy wasn't asked "
                               "for")
            self._next()
            return
        artist = self._artist()
        # Only Prism's OWN render travels — never the model. With no PNG
        # (no browser engine) the numbers in the brief carry it alone.
        files = []
        png = (m.get("drawn") or {}).get("png")
        if png and os.path.exists(png):
            try:
                files.append(CB.files.attach(png))
            except Exception:                           # noqa: BLE001
                pass
        self._made_files = []
        self._set_busy(True, i18n.t(
            "{agent} is drawing the dimensioned sheet for {file} — from "
            "the measured numbers only; the model stays here…")
            .replace("{agent}", artist).replace("{file}", report["file"]))
        self._agent_worker = AutomationWorker(
            {}, self.cfg, files, f"STEP — draft sheet for {report['file']}",
            custom_stages=[("visual", artist, [self.sf.auto_brief(report)])],
            chatgpt_analysis=False, files_out=self._made_files,
            # A picture is the point: the engine's full image budget — and
            # ChatGPT only, no hand-off to another tool if it stumbles.
            image_stages={"visual"}, failover=False)
        self._agent_worker.done.connect(self._on_drafted)
        self._agent_worker.failed.connect(self._on_failed)
        self._agent_worker.start()

    def _on_drafted(self, responses: dict, links: dict):
        m = self._current
        report, out_dir = m["report"], m["out_dir"]
        self._links.update({f"{k} · {report['stem']}": v
                            for k, v in links.items()})
        kept = []
        for rec in self._made_files:
            src = rec.get("path", "") if isinstance(rec, dict) else str(rec)
            if not src or not os.path.exists(src):
                continue
            dest = os.path.join(out_dir, self.sf.ai_sheet_name(
                report["stem"], len(kept) + 1, os.path.splitext(src)[1]))
            try:
                shutil.copyfile(src, dest)
                kept.append(dest)
                CB.config.save_artifact(dest, os.path.basename(dest),
                                        kind="step", task=report["file"])
            except Exception:                           # noqa: BLE001
                pass
        texts = [t for t in (responses.get("visual") or []) if t.strip()]
        self._responses[f"draft · {report['stem']}"] = texts
        self._stage_agents_map[f"draft · {report['stem']}"] = self._artist()
        if kept:
            self._notes.append(f"{report['file']}: AI drawing sheet → "
                               + "; ".join(kept))
            self.result.appendPlainText(
                f"{report['file']} — AI drawing sheet saved:\n  "
                + "\n  ".join(kept))
        elif texts:
            self._notes.append(f"{report['file']}: no image came back — "
                               "the agent's words are saved with the run")
            self.result.appendPlainText(f"{report['file']} — {texts[0]}")
        else:
            self._notes.append(f"{report['file']}: the agent returned "
                               "nothing; Prism's own measured sheet stands")
        self._next()

    # ── ask / edit ──────────────────────────────────────────────────────

    def _ask(self, m: dict):
        report = m["report"]
        model = self._chosen_model()
        if model != "Groq":
            # Chosen over Groq's fast in-house call. If it can't answer,
            # retry the rest of FALLBACK_ORDER — never silently fall back
            # TO Groq, which is the thing being upgraded away from.
            self._model_chain = [model] + [t for t in FALLBACK_ORDER
                                           if t != model]
            self._ask_via_chain(m)
            return
        self._set_busy(True, i18n.t(
            "Asking Groq about {file} — the measured numbers and your "
            "question only; the model stays here…")
            .replace("{file}", report["file"]))
        self._ask_worker = StepAskWorker(self.cfg, report,
                                         self.ask.text().strip())
        self._ask_worker.done.connect(self._on_suggested)
        self._ask_worker.failed.connect(self._on_failed)
        self._ask_worker.start()

    def _ask_via_chain(self, m: dict):
        report = m["report"]
        if not self._model_chain:
            self._on_failed(i18n.t(
                "Neither ChatGPT nor Claude could answer for "
                "{file}.").replace("{file}", report["file"]))
            return
        tool = self._model_chain.pop(0)
        self._set_busy(True, i18n.t(
            "Asking {tool} about {file} — the measured numbers and your "
            "question only; the model stays here…")
            .replace("{tool}", tool).replace("{file}", report["file"]))
        self._agent_worker = AutomationWorker(
            {}, self.cfg, [], f"STEP — ask {tool} about {report['file']}",
            custom_stages=[("ask", tool, [self.sf.ask_prompt(
                report, self.ask.text().strip())])],
            chatgpt_analysis=False, failover=False)
        self._agent_worker.done.connect(
            lambda responses, links, m=m, tool=tool:
                self._on_asked_by_tool(m, tool, responses, links))
        self._agent_worker.failed.connect(lambda _e, m=m: self._ask_via_chain(m))
        self._agent_worker.start()

    def _on_asked_by_tool(self, m: dict, tool: str, responses: dict,
                          links: dict):
        texts = [t for t in (responses.get("ask") or []) if t.strip()]
        if not texts:
            self._ask_via_chain(m)
            return
        if links.get("ask"):
            self._links[f"ask · {m['report']['stem']}"] = links["ask"]
        self._model_chain = []
        self._on_suggested(texts[0], agent=tool)

    # ── the conversation, saved to one file per model ──────────────────────
    # "ask · stem" is already scoped to the model, not the exact question —
    # every Ask/Edit on the same attached model, and every follow-up inside
    # each one, is one running conversation about THAT PART, the same way a
    # chatbot thread would be. Saved as plain JSON reads back as a list of
    # [speaker, text] pairs with nothing else to parse.
    #
    # Deliberately NOT inside m["out_dir"]: core.stepfile.output_dir() gives
    # every fresh measurement of the same model its own numbered sibling
    # folder ("PET CORE (2)", "(3)", …) so a re-measure never overwrites the
    # last one's sheet — which means that folder is a NEW path on every
    # single run, never the same twice. A conversation file written there
    # would never be found again; caught live, by actually simulating a
    # second session rather than trusting the first one's save. The stable
    # thing is the root the person chose (_root()) plus the model's own
    # stem, so it sits beside every numbered run folder rather than inside
    # any one of them.
    def _conversation_path(self, m: dict) -> str:
        stem = m["report"]["stem"]
        return os.path.join(self._root(), self.sf.names(stem)["conversation"])

    def _load_conversation(self, m: dict) -> list:
        path = self._conversation_path(m)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [(s, t) for s, t in data] if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save_conversation(self, m: dict, thread: list):
        try:
            with open(self._conversation_path(m), "w", encoding="utf-8") as f:
                json.dump(thread, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _on_suggested(self, suggestions: str, agent: str = "Groq"):
        m = self._current
        report = m["report"]
        key = f"ask · {report['stem']}"
        self._responses[key] = [suggestions]
        self._stage_agents_map[key] = agent
        is_edit = self._action() == "edit"
        answer_dlg = AnswerDialog(
            i18n.t("STEP — Answer"),
            i18n.t("{file} · answered by {agent}").replace(
                "{file}", report["file"]).replace("{agent}", agent),
            self.ask.text().strip(), suggestions, agent, self,
            allow_followup=True, model_choices=MODEL_CHOICES,
            allow_build=is_edit,
            prior_thread=self._load_conversation(m),
            on_change=lambda thread, m=m: self._save_conversation(m, thread))
        answer_dlg.followup_requested.connect(
            lambda text, chosen, m=m, key=key, dlg=answer_dlg:
                self._on_answer_followup(dlg, m, key, chosen, text))
        # "Build this" — the person may click it any number of times
        # before closing (each follow-up's answer is a fresh thing worth
        # being able to build), so this does NOT close the popup itself.
        answer_dlg.build_requested.connect(
            lambda m=m, key=key, dlg=answer_dlg:
                self._build_plan_for(m, key, dlg))
        answer_dlg.exec()
        # self._responses[key] is the latest version — the original answer,
        # or whatever a follow-up replaced it with while the popup was open.
        suggestions = self._responses[key][0]
        self.result.appendPlainText(
            f"═══ {report['file']} — suggestions from {agent} (from the "
            f"measured figures) ═══\n{suggestions}\n")
        if not is_edit:
            # Ask's whole deliverable is the answer above — no plan, no
            # review page, nothing opened, ever, automatically. Only Edit
            # builds, and only on request (the "Build this" button above,
            # or automatically once, below, for a fresh Edit's own first
            # answer) — never a follow-up read back later and assumed.
            self._notes.append(f"{report['file']}: suggestions only — "
                               "choose Edit to turn this into a change "
                               "plan")
            self._next()
            return
        if self._built_from_popup:
            # "Build this" already ran the plan/build cycle (maybe more
            # than once) while the popup was open — the queue moves on
            # without doing it a second time, automatically, on the
            # original answer.
            self._built_from_popup = False
            self._next()
            return
        # The ordinary, first-time path: a fresh Edit's own answer, never
        # followed up on, builds automatically once the popup closes —
        # unchanged from before "Build this" existed.
        self._build_plan_for(m, key, None)

    def _build_plan_for(self, m: dict, key: str, popup: "AnswerDialog | None"):
        """Turn whatever is CURRENTLY saved at `key` into a plan, then (if
        confirmed) a build — the same pipeline a fresh Edit's own first
        answer already ran automatically, now reachable on demand from
        any follow-up too, including one on a conversation reopened long
        after the original build finished and its popup closed."""
        report = m["report"]
        suggestions = self._responses[key][0]
        if popup is not None:
            # "Build this" clicked from WITHIN the popup, while
            # _on_suggested's own .exec() call is still on the stack —
            # mark it so that call's own continuation (the automatic,
            # first-time build) skips running a second time once the
            # popup finally closes.
            self._built_from_popup = True
            popup.set_busy(True)
        planner = self._planner()
        if not planner:
            msg = i18n.t("Edit needs a reasoning tool to review the plan "
                         "— open Agents and pick one for Reasoning first.")
            if popup is not None:
                popup.set_busy(False)
                QMessageBox.warning(self, "STEP", msg)
            else:
                self._notes.append(f"{report['file']}: suggestions only — "
                                   "no reasoning tool set up to plan "
                                   "changes")
            return
        files = []
        png = (m.get("drawn") or {}).get("png")
        if png and os.path.exists(png):
            try:
                files.append(CB.files.attach(png))
            except Exception:                           # noqa: BLE001
                pass
        if popup is not None:
            popup.set_busy(True)
        else:
            self._set_busy(True, i18n.t(
                "{agent} is reviewing the suggestions into an exact change "
                "plan for {file}…")
                .replace("{agent}", planner).replace("{file}", report["file"]))
        self._agent_worker = AutomationWorker(
            {}, self.cfg, files,
            f"STEP — review and plan CAD changes for {report['file']}",
            custom_stages=[("plan", planner, [self.sf.plan_prompt(
                report, self.ask.text().strip(), suggestions)])],
            chatgpt_analysis=False)
        self._agent_worker.done.connect(
            lambda responses, links, m=m, popup=popup:
                self._on_planned(responses, links, m=m, popup=popup))
        self._agent_worker.failed.connect(
            lambda err, popup=popup: self._on_build_failed(err, popup))
        self._agent_worker.start()

    def _on_build_failed(self, error: str, popup):
        if popup is not None:
            popup.set_busy(False)
            QMessageBox.warning(self, "STEP", error)
        else:
            self._on_failed(error)

    # ── a follow-up typed inside the answer popup ─────────────────────────

    def _on_answer_followup(self, dlg: AnswerDialog, m: dict, key: str,
                            agent: str, text: str):
        """`agent` is whatever was selected in the popup's own "Reply as"
        picker when Send was pressed — the same one that answered first,
        by default, but the person may have switched it."""
        report = m["report"]
        dlg.set_busy(True)
        if agent == "Groq":
            composed = (
                "(This is a follow-up to a question already answered "
                f"above.) Earlier question: {self.ask.text().strip()}\n\n"
                f"Your earlier answer:\n{self._responses[key][0]}\n\n"
                f"Follow-up: {text}")
            self._followup_ask_worker = StepAskWorker(
                self.cfg, report, composed)
            self._followup_ask_worker.done.connect(
                lambda answer, dlg=dlg, key=key:
                    self._on_answer_followup_done(dlg, key, answer))
            self._followup_ask_worker.failed.connect(
                lambda err, dlg=dlg: self._on_answer_followup_failed(
                    dlg, err))
            self._followup_ask_worker.start()
            return
        # A real chat already exists for THIS agent — resume IT rather than
        # starting a fresh one, so it answers with the earlier turn as
        # context instead of being re-sent the whole job from scratch. If
        # the person switched to a DIFFERENT agent than the one that
        # answered before, there is no chat of theirs to resume — give it
        # the same context Groq's follow-up gets instead, in the prompt.
        same_agent = self._stage_agents_map.get(key) == agent
        resume = ({"ask": self._links[key]}
                 if same_agent and self._links.get(key) else None)
        prompt = text if resume else (
            "(This is a follow-up to a question a different tool already "
            f"answered.) Earlier question: {self.ask.text().strip()}\n\n"
            f"The earlier answer was:\n{self._responses[key][0]}\n\n"
            f"Follow-up: {text}")
        self._followup_agent_worker = AutomationWorker(
            {}, self.cfg, [],
            f"STEP — follow-up with {agent} on {report['file']}",
            custom_stages=[("ask", agent, [prompt])], chatgpt_analysis=False,
            failover=False, resume_urls=resume, followup=True)
        self._followup_agent_worker.done.connect(
            lambda responses, links, dlg=dlg, key=key, agent=agent:
                self._on_answer_followup_agent_done(
                    dlg, key, agent, responses, links))
        self._followup_agent_worker.failed.connect(
            lambda err, dlg=dlg: self._on_answer_followup_failed(dlg, err))
        self._followup_agent_worker.start()

    def _on_answer_followup_done(self, dlg: AnswerDialog, key: str,
                                 answer: str):
        self._responses[key] = [answer]
        self._stage_agents_map[key] = "Groq"
        dlg.set_busy(False)
        dlg.set_answer(answer, "Groq")

    def _on_answer_followup_agent_done(self, dlg: AnswerDialog, key: str,
                                       agent: str, responses: dict,
                                       links: dict):
        texts = [t for t in (responses.get("ask") or []) if t.strip()]
        if not texts:
            self._on_answer_followup_failed(
                dlg, i18n.t("{agent} didn't answer the follow-up.")
                .replace("{agent}", agent))
            return
        if links.get("ask"):
            self._links[key] = links["ask"]
        self._responses[key] = [texts[0]]
        self._stage_agents_map[key] = agent
        dlg.set_busy(False)
        dlg.set_answer(texts[0], agent)

    def _on_answer_followup_failed(self, dlg: AnswerDialog, error: str):
        dlg.set_busy(False)
        QMessageBox.warning(self, "STEP", error)

    def _on_planned(self, responses: dict, links: dict, m: dict = None,
                    popup=None):
        """`popup` is the AnswerDialog this plan was requested from, or
        None for the original automatic path (a fresh Edit's own first
        answer, which drives the model queue via `self._next()`).
        "Build this" clicked from a popup — possibly reopened long after
        the original run finished — never touches the queue: the popup
        just stays open, built or not, for as long as the person wants
        it."""
        m = m or self._current
        report, out_dir = m["report"], m["out_dir"]
        self._links.update({f"{k} · {report['stem']}": v
                            for k, v in links.items()})
        texts = [t for t in (responses.get("plan") or []) if t.strip()]
        self._responses[f"plan · {report['stem']}"] = texts
        self._stage_agents_map[f"plan · {report['stem']}"] = self._planner()
        plan, why = self.sf.parse_plan(texts)
        if plan is None:
            if popup is not None:
                popup.set_busy(False)
                QMessageBox.warning(self, "STEP", why)
                return
            self._notes.append(f"{report['file']}: {why}")
            self.result.appendPlainText(f"{report['file']} — {why}")
            self._next()
            return
        m["plan"] = plan
        lines = []
        for ch in plan["changes"]:
            what = (f"Ø{ch['dia_mm']:g} → Ø{ch['new_dia_mm']:g} on {ch['part']}"
                    if ch["op"] == "enlarge_hole"
                    else f"scale {ch['part']} x {ch['factor']:g}")
            lines.append(f"  ▸ {what}" + (f" — {ch['why']}" if ch["why"] else ""))
        for a in plan["advice"]:
            lines.append(f"  • (for the designer) {a}")
        question = self.ask.text().strip()
        review = self.sf.review_html(report, plan, out_dir, question=question)
        self.result.appendPlainText(
            f"{report['file']} — the plan (review page → {review}):\n"
            + ("\n".join(lines) if lines else "  nothing Prism can apply by "
                                             "itself — the advice is the "
                                             "deliverable") + "\n")
        can_build = bool(plan["changes"])
        out = self.sf.names(report)
        if popup is not None:
            popup.set_busy(False)
        review_dlg = PlanReviewDialog(
            i18n.t("STEP — Review the plan") if can_build
            else i18n.t("STEP — The plan"),
            (i18n.t("{file} — confirm here and Prism builds a new copy. "
                    "The original file is never touched.")
             .replace("{file}", report["file"]) if can_build else
             i18n.t("{file} — nothing Prism can apply by itself; the "
                    "advice above is the deliverable")
             .replace("{file}", report["file"])),
            review, can_build, self)
        built = bool(review_dlg.exec())
        if not can_build:
            self._notes.append(f"{report['file']}: plan reviewed → {review}")
            if popup is None:
                self._next()
            return
        if not built:
            self._notes.append(f"{report['file']}: not built — the review "
                               "page stays as the record of the plan")
            if popup is None:
                self._next()
            return
        if popup is not None:
            popup.set_busy(True)
        else:
            self._set_busy(True, i18n.t(
                "Building a copy and re-measuring it…"))
        self._apply_worker = StepApplyWorker(
            m["path"], plan, report, self._mode(), out_dir, question,
            self._k_factor())
        self._apply_worker.done.connect(
            lambda result, m=m, popup=popup: self._on_applied(result, m, popup))
        self._apply_worker.failed.connect(
            lambda err, popup=popup: self._on_build_failed(err, popup))
        self._apply_worker.start()

    def _on_applied(self, result: dict, m: dict = None, popup=None):
        m = m or self._current
        report = m["report"]
        m["modified"] = result["out"]
        self.result.appendPlainText(
            f"{report['file']} — built {os.path.basename(result['out'])}:\n  "
            + "\n  ".join(result["log"]) + "\n\n"
            + self.sf.report_text(result["after"]) + "\n")
        self._notes.append(f"{report['file']}: modified model → "
                           f"{result['out']}")
        try:
            CB.config.save_artifact(result["out"],
                                    os.path.basename(result["out"]),
                                    kind="step", task=report["file"])
        except Exception:                               # noqa: BLE001
            pass
        if popup is not None:
            popup.set_busy(False)
        QDesktopServices.openUrl(QUrl.fromLocalFile(result["review"]))
        if popup is None:
            self._next()

    # ── finishing ───────────────────────────────────────────────────────

    def _finish(self):
        action = self._action()
        label = {"draft": "Draft", "ask": "Ask", "edit": "Edit"}[action]
        self._set_busy(False, i18n.t("Done. ") + (
            " ".join(self._notes) if self._notes
            else i18n.t("Measured from the geometry itself — not by an AI.")))
        self.open_btn.setEnabled(bool(self._links))
        names = ", ".join(m["report"]["file"] for m in self.models)
        question = self.ask.text().strip()
        self._task_name = f"STEP — {label}: {question or names}"
        try:
            CB.config.save_run({
                "query": self._task_name,
                "responses": self._responses, "links": self._links,
                "step": {
                    "action": action, "mode": self._mode(),
                    "question": question,
                    "models": [{"file": m["report"]["file"],
                                "out_dir": m["out_dir"],
                                "modified": m.get("modified", ""),
                                "conversation": self._conversation_path(m)}
                               for m in self.models],
                },
            })
        except Exception:                               # noqa: BLE001
            pass

    def _on_failed(self, error: str):
        self._set_busy(False, "")
        QMessageBox.warning(self, "STEP", error)
        # A failure on one model must not strand the rest of the queue.
        if self._queue:
            self._next()

    def _set_busy(self, busy: bool, message: str):
        self.progress.setVisible(busy)
        self.generate_btn.setEnabled(not busy and bool(self.paths))
        self.status.setText(message)

    def _open_folder(self):
        for m in self.models[:1]:
            QDesktopServices.openUrl(QUrl.fromLocalFile(m["out_dir"]))

    def _open_link(self):
        import webbrowser
        for url in self._links.values():
            if url:
                webbrowser.open(url)
                break

    def closeEvent(self, event):
        """Same reasoning as Gerber: a QThread destroyed mid-run aborts the
        whole process, so ask each worker to stop and wait for it."""
        for worker in (self._worker, self._agent_worker, self._ask_worker,
                       self._apply_worker, self._followup_ask_worker,
                       self._followup_agent_worker):
            if worker is None or not worker.isRunning():
                continue
            if hasattr(worker, "stop"):
                worker.stop()
            if not worker.wait(8000):
                worker.terminate()
                worker.wait(1000)
        super().closeEvent(event)
