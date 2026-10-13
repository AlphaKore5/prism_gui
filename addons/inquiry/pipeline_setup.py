"""Pipeline & wording: the client's names for the five stages, which
optional steps they use, their words for a quotation and a PO, the reminder
clock, and their currency and tax.

The stage MEANINGS are fixed (that is how Prism moves a card when mail
arrives); only the words and the optional steps are the client's. Saved to
cfg["inquiry"]["pipeline"] through the same config save every other inquiry
setting uses; the board relabels the moment it is saved.

A label still at Prism's default is shown translated (i18n.t) and saved as
the default — so a Hindi UI keeps translating it. A label the client typed
is stored verbatim.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QVBoxLayout, QWidget,
)

import i18n
import inquiry_config
import theme
from dialogs.base import PrismDialog
from widgets import controls as C

# What each stage means, under its name. COPY so extract_strings scans it.
COPY = {
    "inquiry": "a new enquiry arrives",
    "quoted": "your quotation went out",
    "nego": "they countered or asked to talk price",
    "po": "they said yes, or a PO arrived",
    "won": "order confirmed",
}

# Optional steps and their sentence. STEPS is in COPY_TABLES.
STEPS = [
    ("details", "Ask for details before quoting — shows “their turn” under "
                "the first stage"),
    ("acknowledgement", "Send an order acknowledgement when you accept a PO"),
    ("proforma", "Proforma and advance payment before the order is confirmed"),
]

# The offered words and currency/tax pairs live in inquiry_config (WORDS,
# TAXES — copy tables, so they are catalogued; review R14).
QUOTE_WORDS = inquiry_config.WORDS["quote"]
PO_WORDS = inquiry_config.WORDS["po"]
MONEY = inquiry_config.TAXES


def _shown(value: str, default: str) -> str:
    return i18n.t(default) if value == default else value


def _stored(text: str, default: str) -> str:
    text = (text or "").strip()
    return default if not text or text == i18n.t(default) else text


class PipelineSetupDialog(PrismDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(
            i18n.t("Pipeline & wording"),
            i18n.t("The five stages mean the same thing for every business — "
                   "that is how Prism moves cards when mail arrives. Rename "
                   "them in your own words and switch off the steps you do "
                   "not use."),
            icon="sliders", parent=parent, scrollable=True)
        self.setWindowTitle(i18n.t("Pipeline & wording"))
        self.cfg = cfg
        p = inquiry_config.pipeline_of(cfg)
        d = inquiry_config.PIPELINE_DEFAULTS
        self.p = p
        fm = self.fontMetrics()
        self.resize(max(560, fm.averageCharWidth() * 80),
                    max(520, fm.height() * 34))

        self.body.addWidget(self._heading(i18n.t("Stages")))
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.SPACE_2)
        grid.setVerticalSpacing(theme.SPACE_1)
        self.labels: dict[str, QLineEdit] = {}
        self.nego_switch = None
        for i, key in enumerate(("inquiry", "quoted", "nego", "po", "won")):
            grid.addWidget(QLabel(str(i + 1)), i, 0)
            edit = QLineEdit(_shown(p["labels"][key], d["labels"][key]))
            edit.setMaxLength(inquiry_config.LABEL_MAX)
            edit.setMinimumWidth(fm.averageCharWidth() * 16)
            edit.setAccessibleName(i18n.t("Name of stage {n}").replace(
                "{n}", str(i + 1)))
            self.labels[key] = edit
            grid.addWidget(edit, i, 1)
            hint = C.label(i18n.t(COPY[key]), "meta", wrap=True)
            grid.addWidget(hint, i, 2)
            if key == "nego":
                sw = C.ToggleSwitch()
                sw.setChecked(bool(p["steps"].get("negotiation", True)))
                sw.setAccessibleName(i18n.t("Use the negotiation stage"))
                self.nego_switch = sw
                grid.addWidget(sw, i, 3)
            else:
                grid.addWidget(C.label(i18n.t("always on"), "meta"), i, 3)
        grid.setColumnStretch(2, 1)
        self.body.addLayout(grid)

        self.body.addWidget(self._heading(i18n.t("Optional steps")))
        self.switches: dict[str, C.ToggleSwitch] = {}
        for key, text in STEPS:
            row = QHBoxLayout()
            sw = C.ToggleSwitch()
            sw.setChecked(bool(p["steps"].get(key, False)))
            sw.setAccessibleName(i18n.t(text))
            self.switches[key] = sw
            row.addWidget(sw, 0, Qt.AlignTop)
            row.addWidget(C.label(i18n.t(text), wrap=True), 1)
            self.body.addLayout(row)

        self.body.addWidget(self._heading(i18n.t("Your words")))
        words = QGridLayout()
        words.addWidget(QLabel(i18n.t("What you call a quotation")), 0, 0)
        words.addWidget(QLabel(i18n.t("What you call a purchase order")), 0, 1)
        self.quote_word = self._word_box(QUOTE_WORDS, p["words"]["quote"],
                                         d["words"]["quote"])
        self.po_word = self._word_box(PO_WORDS, p["words"]["po"], d["words"]["po"])
        words.addWidget(self.quote_word, 1, 0)
        words.addWidget(self.po_word, 1, 1)
        self.body.addLayout(words)

        self.body.addWidget(self._heading(i18n.t("Follow-up and money")))
        money = QGridLayout()
        money.addWidget(QLabel(i18n.t("Remind after (days)")), 0, 0)
        money.addWidget(QLabel(i18n.t("Reminders, then call")), 0, 1)
        money.addWidget(QLabel(i18n.t("Currency and tax")), 0, 2)
        self.remind = QSpinBox()
        self.remind.setRange(1, 365)
        self.remind.setValue(int(p["remind_days"]))
        self.max_rem = QSpinBox()
        self.max_rem.setRange(0, 50)
        self.max_rem.setValue(int(p["max_reminders"]))
        self.money = QComboBox()
        current = (p["currency"], p["tax_label"], p["tax_percent"])
        options = list(MONEY)
        if not any(o[0] == current[0] and o[1] == current[1] for o in options):
            options.insert(0, current)
        for cur, tax, pct in options:
            self.money.addItem(f"{cur} · {i18n.t(tax)}" + (f" {pct}%" if pct else ""),
                               (cur, tax, pct))
            if cur == current[0] and tax == current[1]:
                self.money.setCurrentIndex(self.money.count() - 1)
        money.addWidget(self.remind, 1, 0)
        money.addWidget(self.max_rem, 1, 1)
        money.addWidget(self.money, 1, 2)
        self.body.addLayout(money)

        self.footer.add_secondary(self.button(i18n.t("Cancel"),
                                              on_click=self.reject))
        self.footer.set_primary(self.button(i18n.t("Save"), "primary",
                                            on_click=self.accept))

    def _heading(self, text: str) -> QWidget:
        lab = C.label(text.upper(), "meta", weight=700)
        lab.setContentsMargins(0, theme.SPACE_2, 0, 0)
        return lab

    def _word_box(self, options, value, default) -> QComboBox:
        box = QComboBox()
        box.setEditable(True)
        box.lineEdit().setMaxLength(inquiry_config.LABEL_MAX)
        for o in options:
            box.addItem(i18n.t(o), o)
        shown = _shown(value, default)
        i = box.findText(shown)
        if i < 0:
            box.addItem(value, value)
            i = box.count() - 1
        box.setCurrentIndex(i)
        return box

    def _word_value(self, box: QComboBox, default: str) -> str:
        text = box.currentText().strip()
        data = box.currentData()
        if data and text == i18n.t(data):
            return data
        return _stored(text, default)

    def pipeline(self) -> dict:
        """What to save at cfg["inquiry"]["pipeline"]."""
        d = inquiry_config.PIPELINE_DEFAULTS
        cur, tax, pct = self.money.currentData()
        steps = {k: sw.isChecked() for k, sw in self.switches.items()}
        steps["negotiation"] = bool(self.nego_switch and self.nego_switch.isChecked())
        return {
            "labels": {k: _stored(e.text(), d["labels"][k])
                       for k, e in self.labels.items()},
            "words": {"quote": self._word_value(self.quote_word, d["words"]["quote"]),
                      "po": self._word_value(self.po_word, d["words"]["po"])},
            "steps": steps,
            "remind_days": self.remind.value(),
            "max_reminders": self.max_rem.value(),
            "currency": cur, "tax_label": tax, "tax_percent": pct,
        }


def apply(cfg: dict, pipeline: dict) -> dict:
    """cfg with the pipeline settings stored — a fresh inquiry dict, the
    rest of cfg untouched."""
    out = dict(cfg)
    inquiry = dict(out.get("inquiry") or {})
    inquiry["pipeline"] = pipeline
    out["inquiry"] = inquiry
    return out
