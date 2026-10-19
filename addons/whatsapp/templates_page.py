"""The Templates tab — what Meta has approved, what it is still reading, what it turned down.

A business can start a WhatsApp conversation only with an approved template, so this is the
screen people wait on. It lists every template with its review status in plain words, says WHY one
was rejected (Meta gives a one-word code; this turns it into what to change), lets you write a new
one, fix and resubmit a rejected one, copy one, or delete one, and picks up Meta's decisions by
itself while any template is still in review.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QMessageBox, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp.template_editor import discard, fields_from
from addons.whatsapp import ui
from addons.whatsapp.workers import PlatformWorker
from widgets import controls as C

POLL_MS = 30_000                       # how often to look again while a template is in review


def _status_words() -> dict:
    return {"APPROVED": (i18n.t("Approved"), "ok"), "PENDING": (i18n.t("In review"), "info"),
            "REJECTED": (i18n.t("Rejected"), "err"), "PAUSED": (i18n.t("Paused"), "warn"),
            "DISABLED": (i18n.t("Disabled"), "err"), "IN_APPEAL": (i18n.t("In appeal"), "info"),
            "DRAFT": (i18n.t("Not sent yet"), "quiet")}


def reject_reason_words(code: str) -> str:
    """Meta's one-word rejection code, as what to change."""
    table = {
        "INVALID_FORMAT": i18n.t("Meta found a formatting problem — usually a variable at the very start or end, "
                                 "variables out of order, or a sample value missing."),
        "ABUSIVE_CONTENT": i18n.t("Meta read the wording as abusive or threatening. Soften it and send it again."),
        "TAG_CONTENT_MISMATCH": i18n.t("The category did not match the content — a promotion sent as Utility. "
                                       "Send it again as Marketing."),
        "SCAM": i18n.t("Meta flagged the wording as looking like a scam — avoid urgency, prizes and requests for money."),
    }
    return table.get((code or "").upper(), "")


def kind_words(components: list) -> str:
    """What the template carries above its words, as a short label ("" for plain text)."""
    kind = fields_from(components)["kind"]
    return {"image": i18n.t("Picture"), "video": i18n.t("Video"), "document": i18n.t("Document"), "location": i18n.t("Location"),
            "carousel": i18n.t("Carousel"), "offer": i18n.t("Limited-time offer")}.get(kind, "")


def category_words(category: str) -> str:
    return {"MARKETING": i18n.t("Marketing"), "UTILITY": i18n.t("Utility"), "AUTHENTICATION": i18n.t("Authentication")}.get(category or "", category or "")


def validity_words(seconds) -> str:
    """"Valid for 6 hours" — how long Meta keeps trying to deliver it; empty when it is Meta's default."""
    if not seconds:
        return ""
    for unit, size in ((i18n.t("days"), 86400), (i18n.t("hours"), 3600), (i18n.t("minutes"), 60)):
        if seconds >= size and seconds % size == 0:
            return i18n.t("Valid for {n} {u}").format(n=seconds // size, u=unit)
    return i18n.t("Valid for {n} seconds").format(n=seconds)


def stats_words(stat: dict) -> str:
    """"182 sent · 61% read · 12 clicks" — only once something has been sent."""
    if not stat or not int(stat.get("sent") or 0):
        return ""
    out = [i18n.t("{n} sent").format(n=stat["sent"]), i18n.t("{p}% read").format(p=round(float(stat.get("read_rate") or 0)))]
    if int(stat.get("clicks") or 0):
        out.append(i18n.t("{n} clicks").format(n=stat["clicks"]))
    if int(stat.get("failed") or 0):
        out.append(i18n.t("{n} failed").format(n=stat["failed"]))
    return "  ·  ".join(out)


def preview_of(components: list, limit: int = 160) -> str:
    for comp in components or []:
        if comp.get("type") == "BODY":
            text = " ".join(str(comp.get("text", "")).split())
            return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"
    return ""


def summary_of(rows: list) -> str:
    """"4 templates · 2 approved · 1 in review · 1 rejected" — only the parts that are not zero."""
    if not rows:
        return ""
    by = {}
    for t in rows:
        by[str(t.get("status") or "").upper()] = by.get(str(t.get("status") or "").upper(), 0) + 1
    parts = [i18n.t("{n} templates").format(n=len(rows)) if len(rows) != 1 else i18n.t("1 template")]
    for key, text in (("APPROVED", i18n.t("{n} approved")), ("PENDING", i18n.t("{n} in review")),
                      ("REJECTED", i18n.t("{n} rejected"))):
        if by.get(key):
            parts.append(text.format(n=by[key]))
    return "  ·  ".join(parts)


class _Row(QFrame):
    use = Signal(dict)
    edit = Signal(dict)
    duplicate = Signal(dict)
    delete = Signal(dict)
    fix = Signal(dict)

    def __init__(self, t: dict, stat: dict = None, parent=None):
        super().__init__(parent)
        self.t = t
        self.setObjectName("waTemplate")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#waTemplate {{ background: rgba(255,255,255,0.55);"
            f" border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
        status = str(t.get("status") or "").upper()
        words, tone = _status_words().get(status, (status.capitalize() or "—", "quiet"))
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 12, 14, 10)
        col.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(theme.SPACE_2)
        top.addWidget(C.label(t.get("name", ""), level="SUPPORT", weight=700), stretch=1)
        carries = kind_words(t.get("components"))
        if carries:
            top.addWidget(C.Pill(carries, "quiet"))
        top.addWidget(C.Pill(category_words(t.get("category")), "neutral"))
        top.addWidget(C.Pill(words, tone))
        col.addLayout(top)
        text = preview_of(t.get("components"))
        if not text and t.get("category") == "AUTHENTICATION":
            text = i18n.t("A one-time password message. Meta writes the words.")
        if text:
            col.addWidget(C.label(text, level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True))
        if status == "REJECTED":
            why = reject_reason_words(t.get("reject_reason") or "") or i18n.t("Meta did not say why. Check the wording, then send it again.")
            col.addWidget(C.label(why, level="META", colour=theme.ERR_INK, wrap=True))
        elif status == "PENDING":
            col.addWidget(C.label(i18n.t("Meta is reading it — usually within a day. This page updates by itself."),
                                  level="META", colour=theme.NEUTRAL[600], wrap=True))
        # what it is, and what can be done with it, on one line
        meta = [str(t.get("language") or ""), validity_words(t.get("ttl_seconds")), stats_words(stat)]
        quality = str(t.get("quality") or "").upper()
        if quality:
            meta.append(i18n.t("Quality: {q}").format(q={"GREEN": i18n.t("high"), "YELLOW": i18n.t("medium"),
                                                         "RED": i18n.t("low")}.get(quality, quality.lower())))
        bottom = QHBoxLayout()
        bottom.setSpacing(theme.SPACE_1)
        bottom.addWidget(C.label("  ·  ".join(m for m in meta if m), level="META", colour=theme.NEUTRAL[600]), stretch=1)
        if status == "APPROVED":
            bottom.addWidget(C.button(i18n.t("Use in a campaign"), "tertiary", on_click=lambda: self.use.emit(t)))
        elif status in ("REJECTED", "DRAFT"):
            if status == "REJECTED":
                bottom.addWidget(C.button(i18n.t("Fix with AI"), "tertiary", on_click=lambda: self.fix.emit(t)))
            bottom.addWidget(C.button(i18n.t("Edit and resubmit"), "tertiary", on_click=lambda: self.edit.emit(t)))
        bottom.addWidget(C.icon_button("copy", i18n.t("Make a copy to change"), on_click=lambda: self.duplicate.emit(t)))
        bottom.addWidget(C.icon_button("trash", i18n.t("Delete this template"), on_click=lambda: self.delete.emit(t),
                                       colour=theme.ERR_INK))
        col.addLayout(bottom)


class TemplatesPage(QWidget):
    useTemplate = Signal(str)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self._rows: list = []
        self._stats: dict = {}
        self._filter = "ALL"
        self._loaded = False
        self._failed = ""
        self._busy = False
        self._active = False
        self._note_is_error = False

        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SPACE_4, theme.SPACE_4, theme.SPACE_4, theme.SPACE_4)
        root.setSpacing(theme.SPACE_3)

        head = QHBoxLayout()
        head.setSpacing(theme.SPACE_2)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(C.label(i18n.t("Message templates"), level="CARD_TITLE"))
        self.summary = C.label(i18n.t("Only an approved template can start a conversation."),
                               level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True)
        titles.addWidget(self.summary)
        head.addLayout(titles, stretch=1)
        self.sync_btn = C.button(i18n.t("Update from Meta"), "secondary", on_click=self._sync)
        self.sync_btn.setToolTip(i18n.t("Ask Meta for the latest decision on every template"))
        head.addWidget(self.sync_btn)
        self.library_btn = C.button(i18n.t("Library"), "secondary", "book", on_click=self._library)
        self.library_btn.setToolTip(i18n.t("Ready-made templates by industry"))
        head.addWidget(self.library_btn)
        self.ai_btn = C.button(i18n.t("Write with AI"), "secondary", "sparkles", on_click=self._write_with_ai)
        head.addWidget(self.ai_btn)
        self.new_btn = C.button(i18n.t("New template"), "primary", icon_name="plus", on_click=self._new)
        head.addWidget(self.new_btn)
        root.addLayout(head)

        tools = QHBoxLayout()
        tools.setSpacing(theme.SPACE_3)
        self.chips = C.FilterChips([("ALL", i18n.t("All")), ("APPROVED", i18n.t("Approved")),
                                    ("PENDING", i18n.t("In review")), ("REJECTED", i18n.t("Rejected"))], current="ALL")
        self.chips.changed.connect(self._set_filter)
        tools.addWidget(self.chips, stretch=1)
        self.category_box = QComboBox()
        self.category_box.setMinimumHeight(36)
        self.category_box.setAccessibleName(i18n.t("Category"))
        for key, label in (("", i18n.t("All categories")), ("MARKETING", i18n.t("Marketing")), ("UTILITY", i18n.t("Utility")),
                           ("AUTHENTICATION", i18n.t("Authentication"))):
            self.category_box.addItem(label, key)
        self.category_box.currentIndexChanged.connect(lambda _i: self._render())
        tools.addWidget(self.category_box)
        self.search = C.SearchField(i18n.t("Search templates"))
        self.search.setFixedWidth(260)
        self.search.changed.connect(lambda _t: self._render())
        tools.addWidget(self.search)
        root.addLayout(tools)

        self.note = C.label("", level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True)
        self.note.hide()
        root.addWidget(self.note)

        self.stack = QStackedWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        host = QWidget()
        ui.see_through(host)
        self.list_col = QVBoxLayout(host)
        self.list_col.setContentsMargins(0, 0, theme.SPACE_2, 0)
        self.list_col.setSpacing(theme.SPACE_2)
        scroll.setWidget(host)
        self.stack.addWidget(scroll)                         # 0: the list
        self.state = C.EmptyState("message", "", "", i18n.t("Try again"))
        self.state.clicked.connect(self._state_action)
        self.stack.addWidget(self.state)                     # 1: loading / empty / failed
        root.addWidget(self.stack, stretch=1)

        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self._load)
        self._show_state("loading")

    # ── lifecycle ────────────────────────────────────────────────────────────
    def activate(self):
        self._active = True
        self._load()

    def deactivate(self):
        self._active = False
        self._poll.stop()

    # ── loading ──────────────────────────────────────────────────────────────
    def _load(self):
        w = PlatformWorker("templates/list")
        w.done.connect(self._on_list)
        w.failed.connect(self._on_load_failed)
        self._w_list = w
        w.start()
        sw = PlatformWorker("templates/stats")
        sw.done.connect(self._on_stats)
        sw.failed.connect(lambda _m, _d: None)               # numbers are a bonus: the list stands without them
        self._w_stats = sw
        sw.start()

    def _on_stats(self, reply: dict):
        self._stats = {(r.get("name"), r.get("language")): r for r in reply.get("stats") or []}
        if self._loaded:
            self._render()

    def _on_list(self, reply: dict):
        self._rows = list(reply.get("templates") or [])
        self._loaded = True
        self._failed = ""
        if self._note_is_error:                              # a good answer clears a load error, never a "Submitted" message
            self._say("")
        self.summary.setText(summary_of(self._rows) or i18n.t("Only an approved template can start a conversation."))
        waiting = any(str(t.get("status") or "").upper() == "PENDING" for t in self._rows)
        if waiting and self._active:
            self._poll.start()
        else:
            self._poll.stop()
        self._render()

    def _on_load_failed(self, message: str, _detail: dict):
        if self._loaded:                                     # a failed refresh must not wipe a good list
            self._say(message, error=True)
            return
        self._failed = message
        self._render()

    def _say(self, text: str, *, error: bool = False):
        self._note_is_error = error and bool(text)
        self.note.setText(text)
        self.note.setStyleSheet(f"color: {theme.ERR_INK if error else theme.NEUTRAL[600]};")
        self.note.setVisible(bool(text))

    # ── showing ──────────────────────────────────────────────────────────────
    def _set_filter(self, key: str):
        self._filter = key
        self._render()

    def visible_rows(self) -> list:
        needle = self.search.text().strip().lower()
        out = []
        for t in self._rows:
            if self._filter != "ALL" and str(t.get("status") or "").upper() != self._filter:
                continue
            if self.category_box.currentData() and t.get("category") != self.category_box.currentData():
                continue
            if needle and needle not in str(t.get("name", "")).lower() and needle not in preview_of(t.get("components"), 400).lower():
                continue
            out.append(t)
        return out

    def _show_state(self, kind: str, message: str = ""):
        """kind: loading | failed | none (no templates yet) | nomatch (a filter found nothing)"""
        title, body, action = {
            "loading": (i18n.t("Loading your templates…"), "", None),
            "failed": (i18n.t("Couldn't load your templates"), message, i18n.t("Try again")),
            "none": (i18n.t("No templates yet"),
                     i18n.t("Write your first one, or start from a ready-made template for quotations, site visits and festival greetings."),
                     i18n.t("New template")),
            "nomatch": (i18n.t("No template matches"), i18n.t("Try another word, or choose All."), None),
        }[kind]
        self.state.set_text(title, body)
        if self.state.action is not None:
            self.state.action.setText(action or "")
            self.state.action.setVisible(bool(action))
        self._state_kind = kind
        self.stack.setCurrentIndex(1)

    def _state_action(self):
        if getattr(self, "_state_kind", "") == "failed":
            self._show_state("loading")
            self._load()
        else:
            self._new()

    def _render(self):
        if self._failed and not self._loaded:
            self._show_state("failed", self._failed)
            return
        if not self._loaded:
            self._show_state("loading")
            return
        shown = self.visible_rows()
        if not shown:
            self._show_state("nomatch" if self._rows else "none")
            return
        while self.list_col.count():
            item = self.list_col.takeAt(0)
            if item.widget() is not None:
                discard(item.widget())
        for t in shown:
            row = _Row(t, self._stats.get((t.get("name"), t.get("language"))))
            row.fix.connect(self._fix)
            row.use.connect(lambda tt: self.useTemplate.emit(str(tt.get("name", ""))))
            row.edit.connect(lambda tt: self._open_editor(tt, "resubmit"))
            row.duplicate.connect(lambda tt: self._open_editor(tt, "duplicate"))
            row.delete.connect(self._delete)
            self.list_col.addWidget(row)
        self.list_col.addStretch(1)
        self.stack.setCurrentIndex(0)

    # ── actions ──────────────────────────────────────────────────────────────
    def _new(self):
        self._open_editor(None, "new")

    def _open_editor(self, template, mode: str):
        from addons.whatsapp.template_editor import TemplateEditor
        dlg = TemplateEditor(self, prefill=template, mode=mode)
        if dlg.exec():
            self._say(i18n.t("Submitted. Meta is reading it — this page updates by itself when it decides."))
            self._load()

    def _library(self):
        from addons.whatsapp.template_dialogs import TemplateLibraryDialog
        dlg = TemplateLibraryDialog(parent=self)
        if dlg.exec() and dlg.chosen:
            self._open_editor(dlg.chosen, "new")

    def _write_with_ai(self):
        from addons.whatsapp.template_dialogs import TemplateAIDialog
        dlg = TemplateAIDialog(parent=self)
        if dlg.exec() and dlg.chosen:
            self._open_editor(dlg.chosen, "new")

    def _fix(self, t: dict):
        """Meta refused it: say why and offer a rewrite; if one is taken, the editor opens with it, ready to resubmit."""
        from addons.whatsapp.template_dialogs import TemplateAIDialog
        dlg = TemplateAIDialog(parent=self, rewrite=t)
        if dlg.exec() and dlg.chosen:
            self._open_editor({**t, "components": dlg.chosen["components"], "category": dlg.chosen.get("category") or t.get("category")}, "resubmit")

    def _delete(self, t: dict):
        name = t.get("name", "")
        live = str(t.get("status") or "").upper() == "APPROVED"
        question = (i18n.t("Delete “{n}”? It is removed from your WhatsApp account too, so it can no longer be sent. "
                           "This can't be undone.") if live else
                    i18n.t("Delete “{n}”? This can't be undone.")).format(n=name)
        if QMessageBox.question(self, i18n.t("Delete template"), question) != QMessageBox.Yes:
            return
        w = PlatformWorker("templates/delete", {"template_id": t.get("id")})
        w.done.connect(lambda _r: (self._say(i18n.t("Deleted “{n}”.").format(n=name)), self._load()))
        w.failed.connect(lambda m, _d: self._say(m, error=True))
        self._w_del = w
        w.start()

    def _sync(self):
        if self._busy:
            return
        self._busy = True
        self.sync_btn.setText(i18n.t("Updating…"))
        self.sync_btn.setEnabled(False)
        w = PlatformWorker("templates/sync")
        w.done.connect(self._synced)
        w.failed.connect(self._sync_failed)
        self._w_sync = w
        w.start()

    def _sync_done(self):
        self._busy = False
        self.sync_btn.setText(i18n.t("Update from Meta"))
        self.sync_btn.setEnabled(True)

    def _synced(self, _reply: dict):
        self._sync_done()
        self._load()

    def _sync_failed(self, message: str, _detail: dict):
        self._sync_done()
        self._say(message, error=True)
