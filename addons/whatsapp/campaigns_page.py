"""The Campaigns tab — an approved template, to a chosen audience, checked before it goes.

A campaign is cheap to start and impossible to recall, so the order here is deliberate:

  · Pick an APPROVED template (nothing else can be sent), see the message as the customer will
    read it, and say what goes in each blank.
  · Pick who it reaches — everyone opted in, a saved group, people with a tag, or people who did
    or didn't react to an earlier campaign. The number of people is on screen as you choose.
  · Press Check. The server counts the people, leaves out anyone opted out or unreachable,
    estimates the Meta charge, and lists anything that would stop the send, in plain words.
  · Send is only offered once Check passed for exactly what is on screen; change anything and
    it must be checked again. The last click is a confirmation that says how many and how much.

Right-hand side is the history: what went, how it was received, pause / cancel / change the time
while it runs, and a results view that can aim the next campaign at the people who didn't read it.
The history refreshes by itself while something is sending.
"""
from __future__ import annotations

import json

from PySide6.QtCore import QDate, QDateTime, QTime, Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QFrame, QHBoxLayout, QInputDialog,
                               QLineEdit, QMessageBox, QScrollArea, QSpinBox, QStackedWidget, QTimeEdit,
                               QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp import filter_model as FM
from addons.whatsapp.campaign_detail import (ApiCampaignsDialog, CampaignReport, CampaignSettingsDialog, quick_replies_of,
                                             retarget_filter)
from addons.whatsapp.chat import short_time
from addons.whatsapp.media_lib import AssetField
from addons.whatsapp.template_editor import TemplatePreview, discard, fields_from, variables_of
from addons.whatsapp.workers import PlatformWorker
from dialogs.base import PrismDialog
from widgets import controls as C

_TZ = "Asia/Kolkata"
POLL_MS = 6_000                                   # how often the history looks again while something is sending
COUNT_MS = 400                                    # how long to wait after a keystroke before counting the audience

_EVERYONE, _TAGS, _SEGMENT, _RETARGET = "everyone", "tags", "segment:", "retarget:"
_FILTER, _PICKED, _FILE = "filter", "picked", "file"
FALLBACK_SOURCES = ("first_name", "name", "attribute")
_ACTIVE = ("sending",)


# ── the pure pieces ──────────────────────────────────────────────────────────

def _sources() -> list:
    # (key, label, needs a text box, placeholder)
    return [("first_name", i18n.t("Their first name"), False, ""),
            ("name", i18n.t("Their full name"), False, ""),
            ("mobile", i18n.t("Their mobile number"), False, ""),
            ("attribute", i18n.t("A saved detail about them"), True, i18n.t("The detail's name, e.g. City")),
            ("static", i18n.t("The same text for everyone"), True, i18n.t("e.g. Diwali")),
            ("tracked_link", i18n.t("A link whose clicks are counted"), True, "https://")]


def variable_spec(source: str, text: str, fallback: str = "") -> dict:
    """What the server wants for one blank, from the choice made on screen. `fallback` is what to say for a person who has no
    value (no first name, no City saved) — without one, the server says "there" for a name and "-" for a detail."""
    text = (text or "").strip()
    fallback = (fallback or "").strip()
    if source in ("first_name", "name", "mobile"):
        spec = {"source": "field", "field": source}
        return dict(spec, default=fallback) if fallback and source != "mobile" else spec
    if source == "attribute":
        spec = {"source": "attribute", "key": text}
        return dict(spec, default=fallback) if fallback else spec
    if source == "tracked_link":
        return {"source": "tracked_link", "target": text}
    return {"source": "static", "value": text}


def template_variable_numbers(template: dict) -> list:
    nums: list = []
    for comp in (template or {}).get("components") or []:
        if comp.get("type") in ("BODY", "HEADER") and comp.get("format", "TEXT") == "TEXT":
            for n in variables_of(comp.get("text", "")):
                if n not in nums:
                    nums.append(n)
    return nums


def template_blanks(template: dict) -> list:
    """Everything the sender must supply for this template: [(key, label, kind)], kind 'text' or 'link'.
    The numbered blanks of the message, a value for each website button that ends in {{1}}, and the file
    link for an image, video or document header."""
    out = [(str(n), "{{%d}}" % n, "text") for n in template_variable_numbers(template)]
    for comp in (template or {}).get("components") or []:
        if comp.get("type") == "BUTTONS":
            for i, b in enumerate(comp.get("buttons") or []):
                if b.get("type") == "URL" and variables_of(b.get("url", "")):
                    out.append((str(100 + i), i18n.t("Button {n}").format(n=i + 1), "text"))
        elif comp.get("type") == "HEADER" and str(comp.get("format", "")).upper() in ("IMAGE", "VIDEO", "DOCUMENT"):
            out.append(("header", i18n.t("Header {kind}").format(kind=str(comp["format"]).lower()), "link"))
    return out


def sample_for(spec: dict) -> str:
    """A believable stand-in for what one blank will hold, for the preview."""
    spec = spec or {}
    source = spec.get("source")
    if source == "field":
        return {"first_name": "Asha", "name": "Asha Patel", "last_name": "Patel", "mobile": "+91 98765 43210"}.get(spec.get("field"), "")
    if source == "attribute":
        return "‹%s›" % (spec.get("key") or i18n.t("detail"))
    if source == "static":
        return spec.get("value") or ""
    if source == "tracked_link":
        return spec.get("target") or ""
    return ""


def rule_words(rule: dict) -> str:
    """A repeat rule, as a sentence: "Every Monday and Thursday at 10:00"."""
    if not rule:
        return ""
    at = rule.get("time") or ""
    names = {"mon": i18n.t("Monday"), "tue": i18n.t("Tuesday"), "wed": i18n.t("Wednesday"), "thu": i18n.t("Thursday"),
             "fri": i18n.t("Friday"), "sat": i18n.t("Saturday"), "sun": i18n.t("Sunday")}
    if rule.get("freq") == "daily":
        words = i18n.t("Every day at {t}").format(t=at)
    elif rule.get("freq") == "weekly":
        days = [names.get(d, d) for d in rule.get("days") or []]
        joined = days[0] if len(days) == 1 else ", ".join(days[:-1]) + i18n.t(" and ") + days[-1] if days else ""
        words = i18n.t("Every {d} at {t}").format(d=joined, t=at)
    else:
        words = i18n.t("On day {n} of every month at {t}").format(n=rule.get("day"), t=at)
    if rule.get("until"):
        words += i18n.t(", until {d}").format(d=rule["until"])
    return words


def _money(value) -> str:
    try:
        return "₹{:,.2f}".format(float(value))
    except (TypeError, ValueError):
        return "—"


def _card(title: str, sub: str = "") -> tuple:
    card = C.Card()
    col = card.body((theme.SPACE_5, theme.SPACE_5, theme.SPACE_5, theme.SPACE_5), theme.SPACE_3)
    col.addWidget(C.label(title, level="CARD_TITLE"))
    if sub:
        col.addWidget(C.label(sub, level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
    return card, col


def _status_words() -> dict:
    return {"draft": (i18n.t("Draft"), "quiet"), "scheduled": (i18n.t("Scheduled"), "info"),
            "sending": (i18n.t("Sending"), "info"), "paused": (i18n.t("Paused"), "warn"),
            "done": (i18n.t("Sent"), "ok"), "cancelled": (i18n.t("Cancelled"), "quiet"),
            "failed": (i18n.t("Failed"), "err")}


def history_rows(rows: list) -> list:
    """What the history shows. A Check makes a draft on the server, and a re-Check cancels the old one, so
    drafts and never-started cancelled campaigns are this screen's scaffolding, not history."""
    out = []
    for c in rows:
        status = str(c.get("status") or "").lower()
        if status == "draft":
            continue
        if status == "cancelled" and not int(c.get("total") or 0):
            continue
        out.append(c)
    return out


class RescheduleDialog(PrismDialog):
    def __init__(self, campaign: dict, parent=None):
        super().__init__(i18n.t("Change the time"), i18n.t("When should “{n}” go out?").format(n=campaign.get("name", "")),
                         icon="calendar", parent=parent)
        self._campaign_id = campaign.get("id")
        self.when = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("dd MMM yyyy, hh:mm")
        self.when.setMinimumHeight(40)
        self.body.addWidget(self.when)
        self.error = C.label("", level="SUPPORT", colour=theme.ERR_INK, wrap=True)
        self.error.hide()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.save_btn = self.button(i18n.t("Save the new time"), "primary", on_click=self._save)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.save_btn)
        self.resize(420, 260)

    def _save(self):
        self.save_btn.setEnabled(False)
        w = PlatformWorker("campaigns/reschedule", {"campaign_id": self._campaign_id, "timezone": _TZ,
                                                    "schedule_at": self.when.dateTime().toString("yyyy-MM-ddTHH:mm:ss")})
        w.done.connect(lambda _r: self.accept())
        w.failed.connect(self._failed)
        self._w = w
        w.start()

    def _failed(self, message: str, _detail: dict):
        self.save_btn.setEnabled(True)
        self.error.setText(message)
        self.error.show()


# ── the history row ──────────────────────────────────────────────────────────

class _CampaignRow(QFrame):
    act = Signal(str, str)                       # action, campaign id

    def __init__(self, row: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("waCampaign")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#waCampaign {{ background: rgba(255,255,255,0.55);"
            f" border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        cid = str(row.get("id", ""))
        total = int(row.get("total") or 0)
        sent = int(row.get("sent") or 0)
        failed = int(row.get("failed") or 0)
        status = (row.get("status") or "").lower()
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 12, 14, 10)
        col.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(C.label(row.get("name") or row.get("template_name") or i18n.t("Untitled"),
                              level="SUPPORT", weight=700, wrap=True), stretch=1)
        words, tone = _status_words().get(status, (status.capitalize() or "—", "quiet"))
        if row.get("kind") == "api":
            top.addWidget(C.Pill(i18n.t("API"), "accent"))
            words, tone = (i18n.t("On"), "ok") if status == "sending" else (i18n.t("Off"), "quiet")
        top.addWidget(C.Pill(words, tone))
        col.addLayout(top)
        when = row.get("schedule_at") if status == "scheduled" else row.get("created_at")
        meta = [str(row.get("template_name") or "")]
        stamp = short_time(when or "")
        if stamp:
            meta.append((i18n.t("goes {t}") if status == "scheduled" else "{t}").format(t=stamp))
        col.addWidget(C.label("  ·  ".join(m for m in meta if m), level="META", colour=theme.NEUTRAL[600], wrap=True))
        if row.get("pause_reason") == "category_change":
            col.addWidget(C.label(i18n.t("Stopped because Meta changed this template from Utility to Marketing. Check the template, then start it again."),
                                  level="META", colour=theme.WARN_INK, wrap=True))
        if total and row.get("kind") != "api":
            col.addWidget(C.ProgressBar((sent + failed) / total, hue=theme.OK if not failed else theme.WARN))
            line = i18n.t("{s} of {t} sent").format(s=sent, t=total)
            if failed:
                line += i18n.t("  ·  {f} failed").format(f=failed)
            col.addWidget(C.label(line, level="META", colour=theme.NEUTRAL[600], wrap=True))
        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACE_1)
        actions.addStretch(1)
        if status == "sending" and row.get("kind") != "api":
            actions.addWidget(C.button(i18n.t("Pause"), "tertiary", on_click=lambda: self.act.emit("pause", cid)))
        if status == "paused":
            actions.addWidget(C.button(i18n.t("Resume"), "tertiary", on_click=lambda: self.act.emit("resume", cid)))
        if status == "scheduled":
            actions.addWidget(C.button(i18n.t("Change time"), "tertiary", on_click=lambda: self.act.emit("reschedule", cid)))
        if status in ("sending", "paused", "scheduled") and row.get("kind") != "api":
            actions.addWidget(C.button(i18n.t("Cancel"), "tertiary", on_click=lambda: self.act.emit("cancel", cid)))
        if status in ("done", "sending", "paused", "failed") and sent:
            actions.addWidget(C.button(i18n.t("Results"), "tertiary", on_click=lambda: self.act.emit("report", cid)))
        if actions.count() > 1:
            col.addLayout(actions)


# ── the page ─────────────────────────────────────────────────────────────────

class CampaignsPage(QWidget):
    openTemplates = Signal()

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self._templates: list = []
        self._numbers: list = []
        self._segments: list = []
        self._history: list = []
        self._var_rows: dict = {}                 # blank key -> (source combo or None, text edit, kind)
        self._checked: tuple = ()                 # (fingerprint, campaign id, preflight report)
        self._draft = ""                          # the server-side draft the last Check made
        self._busy = False
        self._active = False
        self._loaded = False
        self._preselect = ""
        self._note_is_error = False
        self._count_token = 0
        self._aud_filter: dict = {}               # the filter built with "People who match a filter…" (or from a file's tag)
        self._picked: dict = {}                   # people chosen in Contacts: {"contact_ids": [...]} or {"filter": {...}}
        self._attr_defs: dict = {}
        self._tag_names: list = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.state = C.EmptyState("send", i18n.t("Loading…"), "", i18n.t("Try again"))
        self.state.clicked.connect(self.activate)
        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(theme.SPACE_4, theme.SPACE_4, theme.SPACE_4, theme.SPACE_4)
        root.setSpacing(theme.SPACE_4)
        self.stack.addWidget(body)                # 0: the screen
        self.stack.addWidget(self.state)          # 1: could not load / not set up
        self.stack.setCurrentIndex(1)
        self.state.action.hide()

        # ── left: the composer ───────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        host = QWidget()
        ui.see_through(host)
        left = QVBoxLayout(host)
        left.setContentsMargins(0, 0, theme.SPACE_2, 0)
        left.setSpacing(theme.SPACE_4)
        scroll.setWidget(host)
        root.addWidget(scroll, stretch=3)

        card, col = _card(i18n.t("Message"), i18n.t("Only templates Meta has approved can be sent."))
        self.template_combo = QComboBox()
        self.template_combo.setMinimumHeight(38)
        self.template_combo.setAccessibleName(i18n.t("Template"))
        self.template_combo.currentIndexChanged.connect(self._template_changed)
        col.addWidget(self.template_combo)
        self.no_templates = QWidget()
        nl = QVBoxLayout(self.no_templates)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(theme.SPACE_2)
        nl.addWidget(C.label(i18n.t("You have no approved template yet. Write one — Meta usually decides within a day."),
                             level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True))
        goto = QHBoxLayout()
        goto.addWidget(C.button(i18n.t("Go to Templates"), "secondary", on_click=self.openTemplates.emit))
        goto.addStretch(1)
        nl.addLayout(goto)
        self.no_templates.hide()
        col.addWidget(self.no_templates)
        self.number_combo = QComboBox()
        self.number_combo.setMinimumHeight(38)
        self.number_combo.setAccessibleName(i18n.t("Send from"))
        self.number_combo.currentIndexChanged.connect(self._dirty)
        self.number_combo.hide()
        col.addWidget(self.number_combo)
        self.preview = TemplatePreview()
        self.preview.setMaximumWidth(460)
        col.addWidget(self.preview)
        left.addWidget(card)

        self.vars_card, self.vars_col = _card(i18n.t("What goes in the blanks"),
                                              i18n.t("Each {{number}} in the message is filled in separately for every person."))
        left.addWidget(self.vars_card)

        card, col = _card(i18n.t("Who gets it"), i18n.t("People who opted out are always left out."))
        self.audience_combo = QComboBox()
        self.audience_combo.setMinimumHeight(38)
        self.audience_combo.setAccessibleName(i18n.t("Audience"))
        self.audience_combo.addItem(i18n.t("Everyone who has opted in"), _EVERYONE)
        self.audience_combo.addItem(i18n.t("People with a tag…"), _TAGS)
        self.audience_combo.addItem(i18n.t("People who match a filter…"), _FILTER)
        self.audience_combo.addItem(i18n.t("People from a file…"), _FILE)
        self.audience_combo.currentIndexChanged.connect(self._audience_changed)
        col.addWidget(self.audience_combo)
        self.filter_row = QWidget()
        fr = QHBoxLayout(self.filter_row)
        fr.setContentsMargins(0, 0, 0, 0)
        fr.setSpacing(theme.SPACE_2)
        self.filter_text = C.label("", level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True)
        fr.addWidget(self.filter_text, stretch=1)
        self.filter_edit_btn = C.button(i18n.t("Choose who"), "secondary", small=True, on_click=self._edit_filter)
        fr.addWidget(self.filter_edit_btn)
        self.filter_row.hide()
        col.addWidget(self.filter_row)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText(i18n.t("Tags, separated by commas — e.g. vip, builder"))
        self.tags_edit.setMinimumHeight(38)
        self.tags_edit.textChanged.connect(self._tags_changed)
        self.tags_edit.hide()
        col.addWidget(self.tags_edit)
        reach = QHBoxLayout()
        reach.setSpacing(theme.SPACE_2)
        self.reach = C.label("", level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True)
        self.reach.hide()
        reach.addWidget(self.reach, stretch=1)
        self.save_group_btn = C.button(i18n.t("Save as a group"), "tertiary", on_click=self._save_group)
        self.save_group_btn.setToolTip(i18n.t("Keep this set of tags so you can pick it again with one click"))
        self.save_group_btn.hide()
        reach.addWidget(self.save_group_btn)
        col.addLayout(reach)
        left.addWidget(card)

        card, col = _card(i18n.t("When"))
        self.when_combo = QComboBox()
        self.when_combo.setMinimumHeight(38)
        self.when_combo.setAccessibleName(i18n.t("When"))
        self.when_combo.addItem(i18n.t("Send now"), "now")
        self.when_combo.addItem(i18n.t("Send later"), "later")
        self.when_combo.addItem(i18n.t("Repeat"), "repeat")
        self.when_combo.currentIndexChanged.connect(self._when_changed)
        col.addWidget(self.when_combo)
        self.when_edit = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.when_edit.setCalendarPopup(True)
        self.when_edit.setDisplayFormat("dd MMM yyyy, hh:mm")
        self.when_edit.setMinimumHeight(38)
        self.when_edit.dateTimeChanged.connect(self._dirty)
        self.when_edit.hide()
        col.addWidget(self.when_edit)
        self.repeat_box = QWidget()
        rl = QVBoxLayout(self.repeat_box)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(theme.SPACE_2)
        self.freq = QComboBox()
        self.freq.setMinimumHeight(38)
        self.freq.setAccessibleName(i18n.t("How often"))
        self.freq.addItem(i18n.t("Every day"), "daily")
        self.freq.addItem(i18n.t("Every week"), "weekly")
        self.freq.addItem(i18n.t("Every month"), "monthly")
        self.freq.setCurrentIndex(1)
        self.freq.currentIndexChanged.connect(self._freq_changed)
        rl.addWidget(self.freq)
        self.repeat_time = QTimeEdit(QTime(10, 0))
        self.repeat_time.setDisplayFormat("HH:mm")
        self.repeat_time.setMinimumHeight(36)
        self.repeat_time.timeChanged.connect(self._dirty)
        rl.addWidget(ui.field(i18n.t("At"), self.repeat_time))
        self.day_boxes: dict = {}
        self.days_row = QWidget()
        dl = QHBoxLayout(self.days_row)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(theme.SPACE_2)
        for key, label in (("mon", i18n.t("Mon")), ("tue", i18n.t("Tue")), ("wed", i18n.t("Wed")), ("thu", i18n.t("Thu")),
                           ("fri", i18n.t("Fri")), ("sat", i18n.t("Sat")), ("sun", i18n.t("Sun"))):
            b = QCheckBox(label)
            b.setChecked(key == "mon")
            b.toggled.connect(self._dirty)
            self.day_boxes[key] = b
            dl.addWidget(b)
        dl.addStretch(1)
        rl.addWidget(self.days_row)
        self.month_day = QSpinBox()
        self.month_day.setRange(1, 28)
        self.month_day.setValue(1)
        self.month_day.setMinimumHeight(36)
        self.month_day.valueChanged.connect(self._dirty)
        self.month_row = ui.field(i18n.t("On day of the month"), self.month_day)
        rl.addWidget(self.month_row)
        self.until_on = QCheckBox(i18n.t("Stop repeating on"))
        self.until_on.toggled.connect(self._dirty)
        self.until_edit = QDateEdit(QDate.currentDate().addMonths(3))
        self.until_edit.setCalendarPopup(True)
        self.until_edit.setDisplayFormat("dd MMM yyyy")
        self.until_edit.setMinimumHeight(36)
        self.until_edit.dateChanged.connect(self._dirty)
        until = QHBoxLayout()
        until.addWidget(self.until_on)
        until.addWidget(self.until_edit)
        until.addStretch(1)
        rl.addLayout(until)
        self.repeat_box.hide()
        col.addWidget(self.repeat_box)
        self.local_on = QCheckBox(i18n.t("Send at the same time of day in each person's own time zone"))
        self.local_on.setToolTip(i18n.t("Worked out from the country code. A message for someone in Dubai goes at their 10:00, not yours."))
        self.local_on.toggled.connect(self._when_changed)
        col.addWidget(self.local_on)
        self.local_time = QTimeEdit(QTime(10, 0))
        self.local_time.setDisplayFormat("HH:mm")
        self.local_time.setMinimumHeight(36)
        self.local_time.timeChanged.connect(self._dirty)
        self.local_field = ui.field(i18n.t("Their local time"), self.local_time)
        self.local_field.hide()
        col.addWidget(self.local_field)
        self.retry_on = QCheckBox(i18n.t("Try again for messages that fail"))
        self.retry_on.setToolTip(i18n.t("A message can fail for a passing reason, such as Meta limiting how many marketing messages one person gets in a day. "
                                        "Prism tries those again, up to three times, within a day."))
        self.retry_on.toggled.connect(self._retry_changed)
        col.addWidget(self.retry_on)
        self.retry_box = QWidget()
        rr = QHBoxLayout(self.retry_box)
        rr.setContentsMargins(0, 0, 0, 0)
        rr.setSpacing(theme.SPACE_2)
        self.retry_times = QSpinBox()
        self.retry_times.setRange(1, 3)
        self.retry_times.setValue(3)
        self.retry_times.setSuffix(i18n.t(" times"))
        self.retry_times.setMinimumHeight(36)
        self.retry_times.valueChanged.connect(self._dirty)
        self.retry_gap = QSpinBox()
        self.retry_gap.setRange(5, 24 * 60)
        self.retry_gap.setValue(60)
        self.retry_gap.setSuffix(i18n.t(" min apart"))
        self.retry_gap.setMinimumHeight(36)
        self.retry_gap.valueChanged.connect(self._dirty)
        rr.addWidget(self.retry_times)
        rr.addWidget(self.retry_gap)
        rr.addStretch(1)
        self.retry_box.hide()
        col.addWidget(self.retry_box)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(i18n.t("Name this campaign (optional)"))
        self.name_edit.setMinimumHeight(38)
        self.name_edit.setAccessibleName(i18n.t("Campaign name"))
        self.name_edit.textChanged.connect(self._dirty)
        col.addWidget(self.name_edit)
        left.addWidget(card)

        card, col = _card(i18n.t("Check, then send"))
        self.verdict = QFrame()
        self.verdict.setObjectName("waVerdict")
        self.verdict.setAttribute(Qt.WA_StyledBackground, True)
        self.verdict_col = QVBoxLayout(self.verdict)
        self.verdict_col.setContentsMargins(theme.SPACE_4, theme.SPACE_3, theme.SPACE_4, theme.SPACE_3)
        self.verdict_col.setSpacing(4)
        self.verdict.hide()
        col.addWidget(self.verdict)
        trow = QHBoxLayout()
        trow.setSpacing(theme.SPACE_2)
        self.test_phone = QLineEdit(str((self.cfg.get("whatsapp") or {}).get("test_phone") or ""))
        self.test_phone.setPlaceholderText(i18n.t("Your phone, with country code — e.g. 919812345678"))
        self.test_phone.setMinimumHeight(36)
        self.test_phone.setAccessibleName(i18n.t("Phone to send a test to"))
        trow.addWidget(self.test_phone, 1)
        self.test_btn = C.button(i18n.t("Send me a test"), "tertiary", on_click=self._send_test)
        self.test_btn.setToolTip(i18n.t("One message, to this phone only, built exactly as the campaign would. Billed like any template message."))
        trow.addWidget(self.test_btn)
        col.addLayout(trow)
        self.test_note = ui.note()
        col.addWidget(self.test_note)
        buttons = QHBoxLayout()
        buttons.setSpacing(theme.SPACE_2)
        self.check_btn = C.button(i18n.t("Check"), "secondary", on_click=self._check)
        self.send_btn = C.button(i18n.t("Send"), "primary", on_click=self._send)
        self.send_btn.setEnabled(False)
        buttons.addWidget(self.check_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.send_btn)
        col.addLayout(buttons)
        left.addWidget(card)
        left.addStretch(1)

        # ── right: history ───────────────────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(theme.SPACE_3)
        self.repeat_title = C.label(i18n.t("Repeating"), level="CARD_TITLE")
        self.repeat_title.hide()
        right.addWidget(self.repeat_title)
        self.repeat_col = QVBoxLayout()
        self.repeat_col.setSpacing(theme.SPACE_2)
        right.addLayout(self.repeat_col)
        head = QHBoxLayout()
        head.addWidget(C.label(i18n.t("Your campaigns"), level="CARD_TITLE"), stretch=1)
        head.addWidget(C.button(i18n.t("API campaigns"), "secondary", small=True, on_click=self._api_campaigns))
        head.addWidget(C.button(i18n.t("Settings"), "tertiary", small=True, on_click=self._campaign_settings))
        right.addLayout(head)
        self.note = C.label("", level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True)
        self.note.hide()
        right.addWidget(self.note)
        hscroll = QScrollArea()
        hscroll.setWidgetResizable(True)
        hscroll.setFrameShape(QFrame.NoFrame)
        hscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hscroll.viewport().setAutoFillBackground(False)
        hhost = QWidget()
        ui.see_through(hhost)
        self.history_col = QVBoxLayout(hhost)
        self.history_col.setContentsMargins(0, 0, theme.SPACE_2, 0)
        self.history_col.setSpacing(theme.SPACE_2)
        hscroll.setWidget(hhost)
        right.addWidget(hscroll, stretch=1)
        root.addLayout(right, stretch=2)

        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.setInterval(COUNT_MS)
        self._count_timer.timeout.connect(self._count)
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self._reload_history)

        self._template_changed()
        self._show_history_loading()

    # ── lifecycle ────────────────────────────────────────────────────────────
    def activate(self):
        self._active = True
        if not self._loaded:
            self.stack.setCurrentIndex(1)
            self.state.set_text(i18n.t("Loading…"), "")
            self.state.action.hide()
        ui.call(self, "attributes/list", {}, done=lambda r: setattr(self, "_attr_defs", {a["key"]: {"type": a.get("type"), "options": a.get("options")}
                                                                                         for a in r.get("attributes") or []}), failed=lambda m, _d: None)
        ui.call(self, "tags/list", {}, done=lambda r: setattr(self, "_tag_names", [t["name"] for t in r.get("tags") or []]), failed=lambda m, _d: None)
        for route, done, attr in (("templates/list", self._on_templates, "_w_t"),
                                  ("numbers/list", self._on_numbers, "_w_n"),
                                  ("segments/list", self._on_segments, "_w_s"),
                                  ("campaigns/list", self._on_history, "_w_h"),
                                  ("schedules/list", self._on_schedules, "_w_r")):
            w = PlatformWorker(route)
            w.done.connect(done)
            w.failed.connect(self._on_load_failed if route == "templates/list" else
                             (lambda m, _d, r=route: self._say(m, error=True) if r != "schedules/list" else None))
            setattr(self, attr, w)
            w.start()

    def deactivate(self):
        self._active = False
        self._poll.stop()

    def choose_template(self, name: str):
        """Called when the Templates tab's 'Use in a campaign' is pressed."""
        self._preselect = name
        i = self.template_combo.findData(name)
        if i >= 0:
            self.template_combo.setCurrentIndex(i)

    def add_retarget(self, campaign_id: str, name: str, action: str, negate: bool, button: int | None = None):
        """Aim this campaign at the people who did, or didn't, react to an earlier one."""
        label = {("read", True): i18n.t("Didn't read “{n}”"), ("read", False): i18n.t("Read “{n}”"),
                 ("replied", False): i18n.t("Replied to “{n}”"), ("clicked", False): i18n.t("Clicked in “{n}”"),
                 ("button", False): i18n.t("Pressed a button in “{n}”")}.get((action, negate), i18n.t("Reacted to “{n}”")).format(n=name)
        data = "%s%s:%s:%d%s" % (_RETARGET, campaign_id, action, 1 if negate else 0, (":%d" % button) if button is not None else "")
        i = self.audience_combo.findData(data)
        if i < 0:
            self.audience_combo.addItem(label, data)
            i = self.audience_combo.count() - 1
        self.audience_combo.setCurrentIndex(i)

    # ── loading ──────────────────────────────────────────────────────────────
    def _say(self, text: str, *, error: bool = False):
        self._note_is_error = error and bool(text)
        self.note.setText(text)
        self.note.setStyleSheet(f"color: {theme.ERR_INK if error else theme.NEUTRAL[600]};")
        self.note.setVisible(bool(text))

    def _on_load_failed(self, message: str, _detail: dict):
        if self._loaded:
            self._say(message, error=True)
            return
        self.state.set_text(i18n.t("Couldn't load your campaigns"), message)
        self.state.action.setText(i18n.t("Try again"))
        self.state.action.show()
        self.stack.setCurrentIndex(1)

    def _on_templates(self, reply: dict):
        self._loaded = True
        self.stack.setCurrentIndex(0)
        self._templates = [t for t in reply.get("templates") or [] if str(t.get("status", "")).upper() == "APPROVED"]
        keep = self.template_combo.currentData() or self._preselect
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        for t in self._templates:
            self.template_combo.addItem("%s  ·  %s" % (t.get("name", ""), t.get("language", "")), t.get("name"))
        self.template_combo.setVisible(bool(self._templates))
        self.no_templates.setVisible(not self._templates)
        i = self.template_combo.findData(keep) if keep else 0
        self.template_combo.setCurrentIndex(max(i, 0))
        self.template_combo.blockSignals(False)
        self._template_changed()

    def _on_numbers(self, reply: dict):
        self._numbers = list(reply.get("numbers") or [])
        keep = self.number_combo.currentData()
        self.number_combo.blockSignals(True)
        self.number_combo.clear()
        if len(self._numbers) > 1:
            self.number_combo.addItem(i18n.t("Choose the number to send from"), "")
            for n in self._numbers:
                self.number_combo.addItem(str(n.get("display") or n.get("id")), str(n.get("id")))
            i = self.number_combo.findData(keep) if keep else 0
            self.number_combo.setCurrentIndex(max(i, 0))
        self.number_combo.blockSignals(False)
        self.number_combo.setVisible(len(self._numbers) > 1)

    def _on_segments(self, reply: dict):
        self._segments = list(reply.get("segments") or [])
        keep = self.audience_combo.currentData()
        self.audience_combo.blockSignals(True)
        for i in reversed(range(self.audience_combo.count())):
            if str(self.audience_combo.itemData(i)).startswith(_SEGMENT):
                self.audience_combo.removeItem(i)
        for s in self._segments:
            self.audience_combo.addItem(i18n.t("Saved group: {n}").format(n=s.get("name", "")), _SEGMENT + str(s.get("id")))
        self.audience_combo.setCurrentIndex(max(self.audience_combo.findData(keep), 0))
        self.audience_combo.blockSignals(False)
        self._audience_changed()

    def _show_history_loading(self):
        self._clear_history()
        self.history_col.addWidget(C.label(i18n.t("Loading…"), level="SUPPORT", colour=theme.NEUTRAL[600]))
        self.history_col.addStretch(1)

    def _clear_history(self):
        while self.history_col.count():
            item = self.history_col.takeAt(0)
            if item.widget() is not None:
                discard(item.widget())

    def _on_history(self, reply: dict):
        self._history = list(reply.get("campaigns") or [])
        if self._note_is_error:                   # a good answer clears a load error, never a "Started" message
            self._say("")
        self._clear_history()
        shown = history_rows(self._history)
        for c in shown:
            row = _CampaignRow(c)
            row.act.connect(self._row_action)
            self.history_col.addWidget(row)
        if not shown:
            self.history_col.addWidget(C.label(i18n.t("Nothing sent yet. Your first campaign will appear here."),
                                               level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
        self.history_col.addStretch(1)
        if self._active and any(str(c.get("status") or "").lower() in _ACTIVE for c in shown):
            self._poll.start()
        else:
            self._poll.stop()

    # ── the form ─────────────────────────────────────────────────────────────
    def current_template(self) -> dict:
        name = self.template_combo.currentData()
        return next((t for t in self._templates if t.get("name") == name), {})

    def _template_changed(self, *_):
        self.vars_card.setVisible(bool(self.current_template()))
        self._rebuild_blanks(template_blanks(self.current_template()))
        self._refresh_preview()
        self._dirty()

    def _rebuild_blanks(self, blanks: list):
        keys = [b[0] for b in blanks]
        if list(self._var_rows) == keys and (self._var_rows or not blanks):
            return
        old = {k: (row[0].currentData() if row[0] is not None else None, row[1].text(),
                   row[3].text() if len(row) > 3 and row[3] is not None and hasattr(row[3], "text") else "")
               for k, row in self._var_rows.items()}
        old_assets = {k: row[3].asset() for k, row in self._var_rows.items() if row[2] == "link" and row[3] is not None}
        # keep the card's heading and sub line; drop the rows after them
        while self.vars_col.count() > 2:
            item = self.vars_col.takeAt(2)
            if item.widget() is not None:
                discard(item.widget())
        self._var_rows = {}
        if not blanks:
            self.vars_col.addWidget(C.label(i18n.t("This message has no blanks — it reads the same for everyone."),
                                            level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
            return
        for key, label, kind in blanks:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(theme.SPACE_2)
            tag = C.label(label, level="SUPPORT", weight=700)
            tag.setMinimumWidth(52)
            rl.addWidget(tag)
            edit = QLineEdit()
            edit.setMinimumHeight(36)
            edit.textChanged.connect(self._blank_changed)
            if kind == "link":
                # the file comes from the Media Library (uploaded to WhatsApp once, however many get it); a web address still works
                format_kind = {"IMAGE": "image", "VIDEO": "video", "DOCUMENT": "document"}.get(
                    next((str(c.get("format", "")).upper() for c in (self.current_template().get("components") or []) if c.get("type") == "HEADER"), ""), None)
                picker = AssetField((format_kind,) if format_kind else None, empty_text=i18n.t("Choose from your Media Library"))
                picker.changed.connect(self._blank_changed)
                if old_assets.get(key):
                    picker.set_asset(old_assets[key])
                edit.setPlaceholderText(i18n.t("or a web address (https://…) of the file"))
                edit.setAccessibleName(label)
                if key in old:
                    edit.setText(old[key][1])
                box = QVBoxLayout()
                box.setSpacing(theme.SPACE_1)
                box.addWidget(picker)
                box.addWidget(edit)
                rl.addLayout(box, stretch=1)
                self._var_rows[key] = (None, edit, kind, picker)
            else:
                combo = QComboBox()
                combo.setMinimumHeight(36)
                combo.setAccessibleName(i18n.t("Fill {label} with").format(label=label))
                for k, text, _needs, _ph in _sources():
                    combo.addItem(text, k)
                fallback = QLineEdit()
                fallback.setMinimumHeight(36)
                fallback.setPlaceholderText(i18n.t("If they have none, say…"))
                fallback.setAccessibleName(i18n.t("What to say when {label} is empty").format(label=label))
                fallback.textChanged.connect(self._blank_changed)
                combo.currentIndexChanged.connect(lambda _i, c=combo, e=edit, f=fallback: self._source_changed(c, e, f))
                if key in old and old[key][0]:
                    combo.setCurrentIndex(max(combo.findData(old[key][0]), 0))
                    edit.setText(old[key][1])
                    fallback.setText(old[key][2])
                rl.addWidget(combo, stretch=2)
                rl.addWidget(edit, stretch=2)
                rl.addWidget(fallback, stretch=2)
                self._source_changed(combo, edit, fallback, quiet=True)
                self._var_rows[key] = (combo, edit, kind, fallback)
            self.vars_col.addWidget(row)

    def _source_changed(self, combo: QComboBox, edit: QLineEdit, fallback: QLineEdit = None, quiet: bool = False):
        needs, placeholder = next(((nd, ph) for k, _t, nd, ph in _sources() if k == combo.currentData()), (False, ""))
        if fallback is not None:
            fallback.setVisible(combo.currentData() in FALLBACK_SOURCES)
        edit.setVisible(needs)
        edit.setPlaceholderText(placeholder)
        edit.setAccessibleName(placeholder or combo.currentText())
        if not quiet:
            self._blank_changed()

    def _blank_changed(self, *_):
        self._refresh_preview()
        self._dirty()

    def variables(self) -> dict:
        out = {}
        for key, (combo, edit, kind, fallback) in self._var_rows.items():
            if kind == "link":
                out[key] = {"asset_id": fallback.asset_id()} if fallback is not None and fallback.asset_id() else {"link": edit.text().strip()}
            else:
                out[key] = variable_spec(combo.currentData(), edit.text(), fallback.text() if fallback is not None else "")
        return out

    def _refresh_preview(self):
        t = self.current_template()
        f = fields_from(t.get("components") or [])
        samples = {}
        for key, spec in self.variables().items():
            if key.isdigit() and int(key) < 100:
                samples[int(key)] = sample_for(spec)
        self.preview.set_content(f["header"], f["body"], f["footer"], f["buttons"], samples, samples.get(1, ""))
        self.preview.setVisible(bool(f["body"]))

    # ── audience ─────────────────────────────────────────────────────────────
    def _audience_changed(self, *_):
        choice = self.audience_combo.currentData() or _EVERYONE
        self.tags_edit.setVisible(choice == _TAGS)
        self.save_group_btn.setVisible(choice == _TAGS)
        self.filter_row.setVisible(choice in (_FILTER, _PICKED, _FILE))
        if choice == _FILTER:
            self.filter_text.setText(FM.describe(self._aud_filter, self._attr_defs) or i18n.t("Everyone — add a condition to narrow it."))
            self.filter_edit_btn.setText(i18n.t("Choose who"))
            self.filter_edit_btn.setVisible(True)
        elif choice == _PICKED:
            n = len(self._picked.get("contact_ids") or [])
            self.filter_text.setText((i18n.t("{n} people you chose in Contacts.") if n != 1 else i18n.t("1 person you chose in Contacts.")).format(n=n)
                                     if "contact_ids" in self._picked else i18n.t("The people you chose in Contacts: {f}").format(f=FM.describe(self._picked.get("filter"), self._attr_defs)))
            self.filter_edit_btn.setVisible(False)
        elif choice == _FILE:
            self.filter_text.setText(FM.describe(self._aud_filter, self._attr_defs) if self._aud_filter else i18n.t("Choose a spreadsheet of people to send to."))
            self.filter_edit_btn.setText(i18n.t("Choose a file…"))
            self.filter_edit_btn.setVisible(True)
        self._dirty()
        self._count_timer.start()

    def _edit_filter(self):
        choice = self.audience_combo.currentData()
        if choice == _FILE:
            self._pick_file()
            return
        from addons.whatsapp.filter_builder import FilterDialog
        dlg = FilterDialog(self._aud_filter, self._attr_defs, self._tag_names, self, opted_in_only=True)
        if dlg.exec():
            self._aud_filter = dlg.filter()
            self._audience_changed()

    def _pick_file(self):
        """A spreadsheet of people: import it (tagged for this campaign), then aim the campaign at that tag."""
        from addons.whatsapp.import_dialog import ImportContactsDialog
        tag = "campaign-%s" % QDateTime.currentDateTime().toString("yyyyMMdd-hhmm")
        dlg = ImportContactsDialog(self)
        dlg.tags_edit.setText(tag)
        if dlg.exec():
            self._aud_filter = {"field": "tags", "op": "has", "value": [tag]}
            self._audience_changed()

    def use_audience(self, target: dict):
        """'Broadcast' on a selection in Contacts: this campaign goes to exactly those people."""
        self._picked = dict(target or {})
        i = self.audience_combo.findData(_PICKED)
        if i < 0:
            self.audience_combo.addItem(i18n.t("People I chose in Contacts"), _PICKED)
            i = self.audience_combo.count() - 1
        self.audience_combo.setCurrentIndex(i)
        self._audience_changed()

    def _reach(self, text: str):
        self.reach.setText(text)
        self.reach.setVisible(bool(text))

    def _tags_changed(self, *_):
        self._dirty()
        self._count_timer.start()

    def _tags(self) -> list:
        return [x.strip() for x in self.tags_edit.text().split(",") if x.strip()]

    def audience(self) -> dict:
        """The audience in the shape campaigns/create takes."""
        choice = self.audience_combo.currentData() or _EVERYONE
        if choice.startswith(_SEGMENT):
            value = choice[len(_SEGMENT):]
            seg = next((s for s in self._segments if str(s.get("id")) == value), {})
            return {"segment_id": value, "segment_name": seg.get("name", "")}
        if choice.startswith(_RETARGET):
            parts = choice[len(_RETARGET):].split(":")
            cid, action, negate = parts[0], parts[1], parts[2]
            button = int(parts[3]) if len(parts) > 3 else None
            return {"filter": retarget_filter(cid, action, negate == "1", button), "segment_name": self.audience_combo.currentText()}
        if choice == _PICKED:
            return dict(self._picked, segment_name=self.audience_combo.currentText())
        if choice in (_FILTER, _FILE):
            return {"filter": self._aud_filter or {"all": []}, "segment_name": self.audience_combo.currentText()}
        if choice == _TAGS:
            return {"tags": self._tags()}
        return {"tags": []}

    def _count_filter(self):
        """The same audience as a segment filter, for counting; None when there is nothing to count yet."""
        a = self.audience()
        if "contact_ids" in a:
            return {"__ids__": a["contact_ids"]}
        if "segment_id" in a:
            return {"field": "segment", "op": "in", "value": a["segment_id"]}
        if "filter" in a:
            return a["filter"]
        if self.audience_combo.currentData() == _TAGS:
            return {"field": "tags", "op": "has_any", "value": a["tags"]} if a["tags"] else None
        return {"all": []}

    def _count(self):
        flt = self._count_filter()
        if flt is None:
            self._reach(i18n.t("Type a tag to see how many people have it."))
            return
        if "__ids__" in flt:                                              # chosen by hand: the number is what was chosen
            n = len(flt["__ids__"])
            self._reach((i18n.t("{n} people chosen. Anyone opted out is left out when you press Check.") if n != 1
                         else i18n.t("1 person chosen. Anyone opted out is left out when you press Check.")).format(n=n))
            return
        self._count_token += 1
        token = self._count_token
        w = PlatformWorker("segments/count", {"filter": flt})
        w.done.connect(lambda r, t=token: self._counted(t, r))
        w.failed.connect(lambda _m, _d, t=token: self._reach("") if t == self._count_token else None)
        self._w_count = w
        w.start()

    def _counted(self, token: int, reply: dict):
        if token != self._count_token:
            return
        n = int(reply.get("count") or 0)
        self._reach(i18n.t("{n} people can be messaged right now.").format(n=n) if n != 1
                           else i18n.t("1 person can be messaged right now."))

    def _save_group(self):
        tags = self._tags()
        if not tags:
            self._reach(i18n.t("Type at least one tag first."))
            return
        name, ok = QInputDialog.getText(self, i18n.t("Save as a group"), i18n.t("Name for this group"),
                                        text=", ".join(tags))
        if not ok or not name.strip():
            return
        w = PlatformWorker("segments/save", {"name": name.strip(), "filter": {"field": "tags", "op": "has_any", "value": tags}})
        w.done.connect(lambda r, n=name.strip(): self._group_saved(r, n))
        w.failed.connect(lambda m, _d: self._say(m, error=True))
        self._w_save = w
        w.start()

    def _group_saved(self, reply: dict, name: str):
        self._say(i18n.t("Saved the group “{n}”.").format(n=name))
        w = PlatformWorker("segments/list")
        w.done.connect(lambda r, sid=str(reply.get("segment_id") or ""): (
            self._on_segments(r),
            self.audience_combo.setCurrentIndex(max(self.audience_combo.findData(_SEGMENT + sid), 0))))
        self._w_seg2 = w
        w.start()

    # ── when, and the whole form ─────────────────────────────────────────────
    def _when_changed(self, *_):
        mode = self.when_combo.currentData()
        self.when_edit.setVisible(mode == "later")
        self.repeat_box.setVisible(mode == "repeat")
        self._freq_changed()
        self.local_field.setVisible(self.local_on.isChecked())
        self.send_btn.setText({"later": i18n.t("Schedule"), "repeat": i18n.t("Start repeating")}.get(mode, i18n.t("Send")))
        self._dirty()

    def _retry_changed(self, *_):
        self.retry_box.setVisible(self.retry_on.isChecked())
        self._dirty()

    def retry(self) -> dict:
        """What to do about failures: nothing, or try again N times, this many minutes apart."""
        if not self.retry_on.isChecked():
            return {"max": 0}
        return {"max": self.retry_times.value(), "delay_minutes": min(self.retry_gap.value(), 24 * 60)}

    def _freq_changed(self, *_):
        freq = self.freq.currentData()
        self.days_row.setVisible(freq == "weekly")
        self.month_row.setVisible(freq == "monthly")
        self._dirty()

    def rule(self):
        """The repeat rule on screen, or None when this is not a repeating campaign."""
        if self.when_combo.currentData() != "repeat":
            return None
        rule = {"freq": self.freq.currentData(), "time": self.repeat_time.time().toString("HH:mm"), "tz": _TZ}
        if rule["freq"] == "weekly":
            rule["days"] = [k for k, b in self.day_boxes.items() if b.isChecked()]
        if rule["freq"] == "monthly":
            rule["day"] = self.month_day.value()
        if self.until_on.isChecked():
            rule["until"] = self.until_edit.date().toString("yyyy-MM-dd")
        return rule

    def collect(self) -> dict:
        """Everything on screen, in the shape the server's campaigns/create takes."""
        t = self.current_template()
        data = {"name": self.name_edit.text().strip() or "%s · %s" % (t.get("name", ""), QDateTime.currentDateTime().toString("dd MMM hh:mm")),
                "template_name": t.get("name", ""), "language": t.get("language") or "en_US",
                "audience": self.audience(), "variables": self.variables(), "retry": self.retry()}
        if len(self._numbers) > 1 and self.number_combo.currentData():
            data["number_id"] = self.number_combo.currentData()
        if self.when_combo.currentData() == "later":
            data["schedule_at"] = self.when_edit.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
            data["timezone"] = _TZ
        if self.local_on.isChecked() and self.when_combo.currentData() != "repeat":
            data["local_time"] = self.local_time.time().toString("HH:mm")
            data.setdefault("timezone", _TZ)
        return data

    def config_for_repeat(self) -> dict:
        """What a repeating campaign remembers: the recipe, without a date (the rule times it) and without a name."""
        data = {k: v for k, v in self.collect().items() if k not in ("name", "schedule_at")}
        if self.local_on.isChecked():
            data["local_time"] = self.local_time.time().toString("HH:mm")
        return data

    def _print(self) -> str:
        """What a Check vouches for: everything that decides what is sent, to whom and when (not the campaign's name)."""
        return json.dumps({"c": {k: v for k, v in self.collect().items() if k != "name"}, "r": self.rule(),
                           "l": self.local_time.time().toString("HH:mm") if self.local_on.isChecked() else None}, sort_keys=True)

    def _dirty(self, *_):
        """Any change on screen means the last Check no longer describes it."""
        if self._checked and self._checked[0] != self._print():
            self._checked = ()
            self.send_btn.setEnabled(False)
            self.verdict.hide()

    # ── check ────────────────────────────────────────────────────────────────
    def _block(self, message: str):
        self._show_verdict({"ok": False, "blocking": [{"message": message}], "warnings": [], "recipients": 0, "cost": {}})

    def _check(self):
        if self._busy:
            return
        if not self.current_template():
            self._block(i18n.t("Choose an approved template first."))
            return
        if len(self._numbers) > 1 and not self.number_combo.currentData():
            self._block(i18n.t("You have more than one WhatsApp number. Choose which one sends this campaign."))
            return
        data = self.collect()
        self._busy = True
        self.check_btn.setEnabled(False)
        self.check_btn.setText(i18n.t("Checking…"))
        if self.when_combo.currentData() == "repeat":
            if not self.rule()["freq"] or (self.rule()["freq"] == "weekly" and not self.rule().get("days")):
                self._done_checking()
                self._block(i18n.t("Choose the days of the week."))
                return
            data = {k: v for k, v in self.config_for_repeat().items()}
            data["name"] = self.name_edit.text().strip() or i18n.t("Repeating check")
        self._pending = data
        if self._draft:
            w0 = PlatformWorker("campaigns/cancel", {"campaign_id": self._draft})      # a stale draft: tidy it away
            self._w_tidy = w0
            w0.start()
            self._draft = ""
        self._checked = ()
        w = PlatformWorker("campaigns/create", data)
        w.done.connect(self._created)
        w.failed.connect(self._check_failed)
        self._w_create = w
        w.start()

    def _created(self, reply: dict):
        cid = reply.get("campaign_id")
        w = PlatformWorker("campaigns/preflight", {"campaign_id": cid})
        w.done.connect(lambda r, c=cid: self._preflighted(c, r))
        w.failed.connect(self._check_failed)
        self._w_pre = w
        w.start()

    def _preflighted(self, cid: str, reply: dict):
        report = reply.get("preflight") or {}
        self._draft = cid
        self._checked = (self._print(), cid, report)
        self._done_checking()
        self._show_verdict(report)
        self.send_btn.setEnabled(bool(report.get("ok")))

    def _check_failed(self, message: str, detail: dict):
        self._done_checking()
        self._block(message)

    def _done_checking(self):
        self._busy = False
        self.check_btn.setEnabled(True)
        self.check_btn.setText(i18n.t("Check"))

    def _show_verdict(self, report: dict):
        while self.verdict_col.count():
            discard(self.verdict_col.takeAt(0).widget())
        blocking, warnings = report.get("blocking") or [], report.get("warnings") or []
        if blocking:
            bg, line, ink = theme.ERR_BG, theme.ERR_LINE, theme.ERR_INK
            self.verdict_col.addWidget(C.label(i18n.t("This can't be sent yet"), level="SUPPORT", weight=700, colour=ink))
        else:
            bg, line, ink = theme.OK_BG, theme.OK, theme.OK_INK
            n = int(report.get("recipients") or 0)
            self.verdict_col.addWidget(C.label(i18n.t("Ready — this reaches {n} people").format(n=n),
                                               level="SUPPORT", weight=700, colour=ink))
            cost = report.get("cost") or {}
            if cost:
                self.verdict_col.addWidget(C.label(
                    i18n.t("About {amount} in Meta's charges, including GST. This is an estimate — Meta bills the exact amount.")
                    .format(amount=_money(cost.get("total"))), level="SUPPORT", colour=ink, wrap=True))
        for item in blocking:
            self.verdict_col.addWidget(C.label("•  " + str(item.get("message", "")), level="SUPPORT", colour=theme.ERR_INK, wrap=True))
        for item in warnings:
            self.verdict_col.addWidget(C.label("•  " + str(item.get("message", "")), level="SUPPORT", colour=theme.WARN_INK, wrap=True))
        self.verdict.setStyleSheet(
            f"#waVerdict {{ background: {bg}; border: 1px solid {line}; border-radius: {theme.R_CONTROL}px; }}")
        self.verdict.show()

    # ── send ─────────────────────────────────────────────────────────────────
    def _send(self):
        if self._busy or not self._checked:
            return
        fingerprint, cid, report = self._checked
        if fingerprint != self._print():
            self._dirty()
            return
        n = int(report.get("recipients") or 0)
        cost = _money((report.get("cost") or {}).get("total"))
        if self.when_combo.currentData() == "repeat":
            self._start_repeat(n, cost, cid)
            return
        later = self.when_combo.currentData() == "later"
        question = (i18n.t("Schedule this for {n} people on {when}? It can be cancelled or moved until then.")
                    .format(n=n, when=self.when_edit.dateTime().toString("dd MMM, hh:mm")) if later else
                    i18n.t("Send this to {n} people now? A sent message can't be recalled. About {cost} in Meta's charges.")
                    .format(n=n, cost=cost))
        if QMessageBox.question(self, i18n.t("Send campaign"), question) != QMessageBox.Yes:
            return
        self._busy = True
        self.send_btn.setEnabled(False)
        w = PlatformWorker("campaigns/launch", {"campaign_id": cid})
        w.done.connect(self._sent)
        w.failed.connect(self._send_failed)
        self._w_launch = w
        w.start()

    def _start_repeat(self, n: int, cost: str, draft_id: str):
        rule = self.rule()
        question = i18n.t("{when}, send this to everyone who fits at that moment (about {n} people now, around {cost} each time). "
                          "A new campaign is made and checked each time, and you can stop it whenever you like. Start repeating?").format(
            when=rule_words(rule), n=n, cost=cost)
        if QMessageBox.question(self, i18n.t("Repeat this campaign"), question) != QMessageBox.Yes:
            return
        self._busy = True
        self.send_btn.setEnabled(False)
        name = self.name_edit.text().strip() or "%s · %s" % (self.current_template().get("name", ""), rule_words(rule))
        ui.call(self, "schedules/create", {"name": name[:80], "config": self.config_for_repeat(), "rule": rule},
                done=lambda r, d=draft_id: self._repeat_started(d), failed=self._send_failed)

    def _repeat_started(self, draft_id: str):
        self._busy = False
        self._checked = ()
        if self._draft:                                           # the draft was only for checking
            ui.call(self, "campaigns/cancel", {"campaign_id": self._draft}, failed=lambda m, _d: None)
            self._draft = ""
        self.verdict.hide()
        self._say(i18n.t("It will repeat — {w}.").format(w=rule_words(self.rule())))
        self._load_schedules()

    def _sent(self, reply: dict):
        self._busy = False
        self._checked = ()
        self._draft = ""                          # launched: no longer a draft to tidy
        self.verdict.hide()
        queued = reply.get("queued")
        self._say(i18n.t("Started — {n} messages are being sent.").format(n=queued) if queued is not None
                  else i18n.t("Started."))
        self._reload_history()

    def _send_failed(self, message: str, detail: dict):
        self._busy = False
        report = detail.get("preflight")
        if report:
            self._show_verdict(report)
        else:
            self._block(message)

    def _load_schedules(self):
        ui.call(self, "schedules/list", done=self._on_schedules, failed=lambda m, _d: None)

    def _on_schedules(self, reply: dict):
        ui.clear(self.repeat_col)
        rows = reply.get("schedules") or []
        self.repeat_title.setVisible(bool(rows))
        for sc in rows:
            self.repeat_col.addWidget(self._schedule_row(sc))

    def _schedule_row(self, sc: dict) -> QWidget:
        line = QFrame()
        line.setObjectName("waSchedule")
        line.setAttribute(Qt.WA_StyledBackground, True)
        line.setStyleSheet(f"#waSchedule {{ background: rgba(255,255,255,0.55); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(line)
        col.setContentsMargins(14, 10, 14, 10)
        col.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(C.label(sc.get("name") or "", level="SUPPORT", weight=700, wrap=True), stretch=1)
        sw = C.ToggleSwitch()
        sw.setChecked(bool(sc.get("enabled")))
        sw.setToolTip(i18n.t("Pause or resume this repeat"))
        sw.toggled.connect(lambda on, x=sc: ui.call(self, "schedules/set_enabled", {"schedule_id": x["id"], "enabled": on},
                                                    done=lambda r: self._load_schedules(), failed=lambda m, _d: (self._say(m, error=True), self._load_schedules())))
        top.addWidget(sw)
        top.addWidget(C.icon_button("trash", i18n.t("Stop and delete this repeat"), on_click=lambda _=False, x=sc: self._delete_schedule(x), colour=theme.ERR_INK))
        col.addLayout(top)
        col.addWidget(C.label(rule_words(sc.get("rule") or {}), level="META", colour=theme.NEUTRAL[600], wrap=True))
        nxt = short_time(sc.get("next_run_at") or "")
        runs = int(sc.get("runs") or 0)
        bits = [i18n.t("next {t}").format(t=nxt)] if sc.get("enabled") and nxt else [i18n.t("paused")]
        bits.append(i18n.t("{n} sent so far").format(n=runs))
        col.addWidget(C.label("  ·  ".join(bits), level="META", colour=theme.NEUTRAL[600]))
        if sc.get("last_error"):
            col.addWidget(C.label(i18n.t("The last time it could not run: {e}").format(e=sc["last_error"]), level="META", colour=theme.ERR_INK, wrap=True))
        return line

    def _delete_schedule(self, sc: dict):
        if QMessageBox.question(self, i18n.t("Stop repeating"), i18n.t("Stop “{n}”? Campaigns already sent stay in your history.").format(n=sc.get("name"))) == QMessageBox.Yes:
            ui.call(self, "schedules/delete", {"schedule_id": sc["id"]}, done=lambda r: self._load_schedules(), failed=lambda m, _d: self._say(m, error=True))

    def _send_test(self):
        t = self.current_template()
        if not t:
            self.test_note.error(i18n.t("Choose an approved template first."))
            return
        phone = self.test_phone.text().strip()
        if not phone:
            self.test_note.error(i18n.t("Type your own phone number first."))
            return
        data = {"template_name": t.get("name"), "language": t.get("language") or "en_US", "variables": self.variables(), "to": phone}
        if len(self._numbers) > 1 and self.number_combo.currentData():
            data["number_id"] = self.number_combo.currentData()
        self.test_btn.setEnabled(False)
        self.test_note.clear_note()
        ui.call(self, "campaigns/test", data, done=lambda r, p=phone: self._test_sent(p), failed=self._test_failed)

    def _test_failed(self, message: str, _detail: dict):
        self.test_btn.setEnabled(True)
        self.test_note.error(message)

    def _test_sent(self, phone: str):
        self.test_btn.setEnabled(True)
        self.test_note.ok(i18n.t("Sent. It should arrive on {p} in a moment.").format(p=phone))
        block = dict(self.cfg.get("whatsapp") or {})
        if block.get("test_phone") != phone:
            block["test_phone"] = phone
            self.cfg["whatsapp"] = block
            try:
                import core_bridge as CB
                CB.config.save(self.cfg)
            except Exception:                                    # noqa: BLE001  (remembering the number is a nicety)
                pass

    def _api_campaigns(self):
        ApiCampaignsDialog(self._templates, self).exec()
        self._reload_history()

    def _campaign_settings(self):
        CampaignSettingsDialog(self).exec()

    def _reload_history(self):
        w = PlatformWorker("campaigns/list")
        w.done.connect(self._on_history)
        w.failed.connect(lambda m, _d: self._say(m, error=True))
        self._w_h2 = w
        w.start()

    # ── history actions ──────────────────────────────────────────────────────
    def _row_action(self, action: str, cid: str):
        row = next((c for c in self._history if str(c.get("id")) == cid), {})
        if action == "report":
            tpl = next((t for t in self._templates if t.get("name") == row.get("template_name") and t.get("language", "en_US") == row.get("language", t.get("language"))), {})
            CampaignReport(cid, row.get("name") or "", self, quick_replies=quick_replies_of(tpl),
                           on_retarget=lambda c, a, n, b=None, nm=row.get("name") or "": self.add_retarget(c, nm, a, n, b)).exec()
            return
        if action == "reschedule":
            if RescheduleDialog(row, self).exec():
                self._say(i18n.t("Moved to the new time."))
                self._reload_history()
            return
        if action == "cancel" and QMessageBox.question(
                self, i18n.t("Cancel campaign"),
                i18n.t("Stop this campaign? Messages not yet sent will not go out.")) != QMessageBox.Yes:
            return
        w = PlatformWorker("campaigns/" + action, {"campaign_id": cid})
        w.done.connect(lambda _r: self._reload_history())
        w.failed.connect(lambda m, _d: self._say(m, error=True))
        self._w_act = w
        w.start()
