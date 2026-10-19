"""A campaign in detail: how it was received, who got what and why a message failed; API campaigns; campaign settings.

    CampaignReport       the results window — the funnel, the failure reasons in words, and a table of every person with how far
                         their message got, searchable, filterable, exportable; and the buttons that aim the next campaign at
                         the people who did (or did not) read, reply, click or press a particular button
    ApiCampaignsDialog   named campaigns other software sends through (a shop's order system, Zapier) — the address and a sample
    CampaignSettingsDialog   what Prism does on its own (stop a campaign when Meta re-labels its template)
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLineEdit,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.chat import short_time
from dialogs.base import PrismDialog
from widgets import controls as C

PAGE = 50


def _money(value) -> str:
    try:
        return "₹{:,.2f}".format(float(value))
    except (TypeError, ValueError):
        return "—"


def status_choices() -> list:
    return [("", i18n.t("Everyone")), ("sent", i18n.t("Sent")), ("delivered", i18n.t("Delivered")), ("read", i18n.t("Read")),
            ("replied", i18n.t("Replied")), ("clicked", i18n.t("Clicked")), ("failed", i18n.t("Failed")), ("skipped", i18n.t("Left out"))]


def status_words(status: str) -> str:
    return {"read": i18n.t("Read"), "delivered": i18n.t("Delivered"), "sent": i18n.t("Sent"), "failed": i18n.t("Failed"),
            "skipped": i18n.t("Left out"), "pending": i18n.t("Waiting")}.get(status or "", status or "")


def retarget_filter(campaign_id: str, action: str, negate: bool, button: int | None = None) -> dict:
    """"Everyone who <action> in that campaign" — or who did not. `button` aims at the people who pressed one quick-reply button."""
    leaf = {"field": "campaign", "op": action, "campaign": str(campaign_id)}
    if action == "button" and button is not None:
        leaf["button"] = int(button)
    return {"not": leaf} if negate else leaf


def quick_replies_of(template: dict) -> list:
    """The texts of a template's quick-reply buttons, in order (their position is how a press is recognised)."""
    out = []
    for comp in (template or {}).get("components") or []:
        if comp.get("type") == "BUTTONS":
            for b in comp.get("buttons") or []:
                if b.get("type") == "QUICK_REPLY":
                    out.append(b.get("text") or "")
    return out


class CampaignReport(PrismDialog):
    """Overview on top; below it, every person."""

    def __init__(self, campaign_id: str, name: str, parent=None, on_retarget=None, quick_replies=()):
        super().__init__(name or i18n.t("Campaign"), i18n.t("How it was received, and who got what."), icon="chart", parent=parent, scrollable=True)
        self._on_retarget = on_retarget
        self._campaign_id = campaign_id
        self._quick = list(quick_replies or [])
        self._status = ""
        self._offset = 0
        self._total = 0
        self._sent = 0
        self._request = 0
        self.grid = QVBoxLayout()
        self.grid.setSpacing(theme.SPACE_3)
        self.body.addLayout(self.grid)

        self.people_title = C.label(i18n.t("People").upper(), level="LABEL", colour=theme.NEUTRAL[500])
        self.body.addWidget(self.people_title)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        self.search = C.SearchField(i18n.t("Search name or number"))
        self.search.changed.connect(lambda _t: self._reset_and_load())
        row.addWidget(self.search, stretch=1)
        row.addWidget(C.button(i18n.t("Export"), "secondary", small=True, on_click=self._export))
        self.body.addLayout(row)
        self.chips = C.FilterChips(status_choices(), current="")
        self.chips.changed.connect(self._on_chip)
        self.chips.setMinimumWidth(620)
        self.body.addWidget(self.chips)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([i18n.t("Name"), i18n.t("Mobile"), i18n.t("Status"), i18n.t("Reacted"), i18n.t("Why it didn't go")])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setMinimumHeight(240)
        self.table.setAccessibleName(i18n.t("Everyone this campaign was meant for"))
        self.body.addWidget(self.table)
        pager = QHBoxLayout()
        self.page_note = C.label("", level="META", colour=theme.NEUTRAL[500])
        pager.addWidget(self.page_note, stretch=1)
        self.prev_btn = C.button(i18n.t("Previous"), "tertiary", small=True, on_click=lambda: self._page(-1))
        self.next_btn = C.button(i18n.t("Next"), "tertiary", small=True, on_click=lambda: self._page(1))
        pager.addWidget(self.prev_btn)
        pager.addWidget(self.next_btn)
        self.body.addLayout(pager)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.set_primary(self.button(i18n.t("Close"), "primary", on_click=self.accept))
        self.resize(760, 860)
        self._show_text(i18n.t("Loading…"))
        ui.call(self, "campaigns/report", {"campaign_id": campaign_id}, done=self._on_report, failed=lambda m, _d: self._show_text(m, error=True))
        self._load_people()

    # ── the overview ─────────────────────────────────────────────────────────
    def _show_text(self, text: str, *, error: bool = False):
        ui.clear(self.grid)
        self.grid.addWidget(C.label(text, level="SUPPORT", colour=theme.ERR_INK if error else theme.NEUTRAL[600], wrap=True))

    def _step(self, label: str, count: int, of: int, rate=None):
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(C.label(label, level="SUPPORT"), stretch=1)
        text = str(count) if rate is None else "%s  ·  %g%%" % (count, rate)
        top.addWidget(C.label(text, level="SUPPORT", weight=700))
        col.addLayout(top)
        col.addWidget(C.ProgressBar((count / of) if of else 0.0, hue=theme.ACCENT))
        self.grid.addWidget(box)

    def _on_report(self, reply: dict):
        rep = reply.get("report") or {}
        counts, rates = rep.get("counts") or {}, rep.get("rates") or {}
        sent = int(counts.get("sent") or 0)
        self._sent = sent
        ui.clear(self.grid)
        self.grid.addWidget(C.label(i18n.t("{r} people were meant to get this; {s} were sent.").format(r=counts.get("recipients", 0), s=sent),
                                    level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
        self._step(i18n.t("Delivered"), int(counts.get("delivered") or 0), sent, rates.get("delivered"))
        self._step(i18n.t("Read"), int(counts.get("read") or 0), sent, rates.get("read"))
        self._step(i18n.t("Replied"), int(counts.get("replied") or 0), sent, rates.get("replied"))
        if counts.get("clicked") or counts.get("clicks"):
            self._step(i18n.t("Clicked a link"), int(counts.get("clicked") or 0), sent, rates.get("clicked"))
        failures = rep.get("failures") or []
        if counts.get("failed"):
            self.grid.addWidget(C.label(i18n.t("{n} could not be delivered.").format(n=counts["failed"]), level="SUPPORT", weight=700, colour=theme.ERR_INK, wrap=True))
            for f in failures[:4]:
                self.grid.addWidget(C.label("•  %d × %s  %s" % (f.get("count", 0), f.get("reason", ""), f.get("advice") or ""), level="META", colour=theme.NEUTRAL[700], wrap=True))
        est = rep.get("spend_estimate") or {}
        if est:
            self.grid.addWidget(C.label(i18n.t("About {amount} in Meta's charges, including GST — an estimate; Meta bills the exact amount.").format(amount=_money(est.get("inr"))),
                                        level="META", colour=theme.NEUTRAL[600], wrap=True))
        if self._on_retarget and sent:
            self.grid.addWidget(C.hairline())
            self.grid.addWidget(C.label(i18n.t("Follow up"), level="CARD_TITLE"))
            for text, action, negate in ((i18n.t("Message people who didn't read it"), "read", True), (i18n.t("Message people who read it"), "read", False),
                                         (i18n.t("Message people who replied"), "replied", False), (i18n.t("Message people who clicked"), "clicked", False)):
                self.grid.addWidget(C.button(text, "secondary", on_click=lambda _=False, a=action, n=negate: self._retarget(a, n)))
            for i, label in enumerate(self._quick):
                self.grid.addWidget(C.button(i18n.t("Message people who pressed “{b}”").format(b=label), "secondary",
                                             on_click=lambda _=False, k=i: self._retarget("button", False, k)))

    def _retarget(self, action: str, negate: bool, button: int | None = None):
        self.accept()
        self._on_retarget(self._campaign_id, action, negate, button)

    # ── the people ───────────────────────────────────────────────────────────
    def _on_chip(self, value: str):
        self._status = value
        self._reset_and_load()

    def _reset_and_load(self):
        self._offset = 0
        self._load_people()

    def _page(self, step: int):
        self._offset = max(0, self._offset + step * PAGE)
        self._load_people()

    def _load_people(self):
        self._request += 1
        rid = self._request
        data = {"campaign_id": self._campaign_id, "limit": PAGE, "offset": self._offset, "search": self.search.text().strip()}
        if self._status:
            data["status"] = self._status
        ui.call(self, "campaigns/recipients", data, done=lambda r, i=rid: self._people(i, r),
                failed=lambda m, _d, i=rid: self.error.error(m) if i == self._request else None)

    def _people(self, rid: int, reply: dict):
        if rid != self._request:
            return
        self.error.clear_note()
        rows = reply.get("recipients") or []
        self._total = int(reply.get("total") or 0)
        t = self.table
        t.setRowCount(len(rows))
        for r, p in enumerate(rows):
            reacted = ", ".join(x for x, on in ((i18n.t("replied"), p.get("replied")), (i18n.t("clicked"), p.get("clicked"))) if on)
            why = p.get("reason") or ""
            if p.get("advice"):
                why += "  " + p["advice"]
            for c, text in enumerate((p.get("name") or "", ("+" + p["phone"]) if p.get("phone") and not str(p["phone"]).startswith("*") else (p.get("phone") or ""),
                                      status_words(p.get("status")), reacted, why)):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if p.get("status") == "failed" and c == 2:
                    item.setForeground(Qt.red)
                t.setItem(r, c, item)
        for c, w in enumerate((160, 130, 90, 110)):
            t.setColumnWidth(c, w)
        start = self._offset + 1 if rows else 0
        self.page_note.setText(i18n.t("{a}–{b} of {n}").format(a=start, b=self._offset + len(rows), n=self._total) if rows else i18n.t("No one here."))
        self.prev_btn.setEnabled(self._offset > 0)
        self.next_btn.setEnabled(self._offset + PAGE < self._total)

    def _export(self):
        data = {"campaign_id": self._campaign_id}
        if self._status:
            data["status"] = self._status
        ui.call(self, "campaigns/recipients_csv", data, done=self._save, failed=lambda m, _d: self.error.error(m))

    def _save(self, reply: dict):
        path, _ = QFileDialog.getSaveFileName(self, i18n.t("Save this list"), "campaign-people.csv", i18n.t("CSV files (*.csv)"))
        if not path:
            return
        try:
            Path(path).write_text(reply.get("csv", ""), encoding="utf-8-sig", newline="")
        except OSError as e:
            self.error.error(str(e))
            return
        C.show_toast(self, i18n.t("Saved"), Path(path).name)


class CampaignSettingsDialog(PrismDialog):
    def __init__(self, parent=None):
        super().__init__(i18n.t("Campaign settings"), i18n.t("What Prism does on its own while a campaign runs."), icon="settings", parent=parent)
        self.auto = QCheckBox(i18n.t("Stop a campaign if Meta changes its template from Utility to Marketing"))
        self.body.addWidget(self.auto)
        self.body.addWidget(C.label(i18n.t("Marketing messages cost more. Meta sometimes re-labels a template while a campaign is running; with this on, a running campaign "
                                           "is paused and a scheduled one cancelled, so nothing is billed at the higher price without you knowing. If Meta changes it back, "
                                           "a campaign paused for this reason starts again."), level="META", colour=theme.NEUTRAL[600], wrap=True))
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.save_btn = self.button(i18n.t("Save"), "primary", on_click=self._save)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.save_btn)
        self.resize(540, 340)
        ui.call(self, "campaigns/settings/get", {}, done=lambda r: self.auto.setChecked(bool((r.get("settings") or {}).get("auto_pause_on_category_change", True))),
                failed=lambda m, _d: self.error.error(m))

    def _save(self):
        self.save_btn.setEnabled(False)
        ui.call(self, "campaigns/settings/save", {"settings": {"auto_pause_on_category_change": self.auto.isChecked()}}, done=lambda _r: self.accept(),
                failed=lambda m, _d: (self.save_btn.setEnabled(True), self.error.error(m)))


class ApiCampaignsDialog(PrismDialog):
    """Named campaigns other software sends through. Make one, switch it on, paste its address and sample into that software."""

    def __init__(self, templates=(), parent=None):
        super().__init__(i18n.t("API campaigns"), i18n.t("A named campaign your own software (a shop, a CRM, Zapier) sends messages through, one person at a time."),
                         icon="send", parent=parent, scrollable=True)
        self._templates = [t for t in templates if str(t.get("status", "")).upper() == "APPROVED"]
        self._endpoint = ""
        self.list = QVBoxLayout()
        self.list.setSpacing(theme.SPACE_2)
        self.body.addLayout(self.list)
        self.body.addWidget(C.hairline())
        self.body.addWidget(C.label(i18n.t("New API campaign").upper(), level="LABEL", colour=theme.NEUTRAL[500]))
        form = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setMinimumHeight(38)
        self.name.setPlaceholderText(i18n.t("A name, like order_shipped"))
        form.addWidget(self.name, stretch=1)
        self.template = QComboBox()
        self.template.setMinimumHeight(38)
        self.template.setAccessibleName(i18n.t("Template"))
        for t in self._templates:
            self.template.addItem("%s · %s" % (t.get("name"), t.get("language")), t)
        form.addWidget(self.template, stretch=1)
        self.body.addLayout(form)
        self.body.addWidget(C.button(i18n.t("Make it"), "primary", on_click=self._make), alignment=Qt.AlignLeft)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.set_primary(self.button(i18n.t("Close"), "primary", on_click=self.accept))
        self.resize(680, 640)
        self.reload()

    def reload(self):
        ui.call(self, "api_campaigns/list", {}, done=self._loaded, failed=lambda m, _d: self.error.error(m))

    def _loaded(self, reply: dict):
        self._endpoint = reply.get("endpoint") or ""
        ui.clear(self.list)
        items = reply.get("campaigns") or []
        if not items:
            self.list.addWidget(C.label(i18n.t("No API campaigns yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for c in items:
            card, col = ui.card("", "")
            top = QHBoxLayout()
            text = QVBoxLayout()
            text.setSpacing(0)
            text.addWidget(C.label(c.get("name") or "", level="SUPPORT", weight=700))
            text.addWidget(C.label(i18n.t("{t} · {n} sent").format(t=c.get("template_name"), n=c.get("sent", 0)), level="META", colour=theme.NEUTRAL[600]))
            top.addLayout(text, stretch=1)
            sw = C.ToggleSwitch()
            sw.setChecked(bool(c.get("live")))
            sw.setToolTip(i18n.t("On: it sends. Off: requests are refused."))
            sw.toggled.connect(lambda on, x=c: ui.call(self, "api_campaigns/set_live", {"campaign_id": x["id"], "live": on}, done=lambda _r: self.reload(),
                                                       failed=lambda m, _d: (self.error.error(m), self.reload())))
            top.addWidget(sw)
            top.addWidget(C.button(i18n.t("Copy sample"), "secondary", small=True, on_click=lambda _=False, x=c: self._copy(x)))
            top.addWidget(C.icon_button("trash", i18n.t("Delete this API campaign"), on_click=lambda _=False, x=c: self._delete(x), colour=theme.ERR_INK))
            col.addLayout(top)
            self.list.addWidget(card)
        if items and self._endpoint:
            self.list.addWidget(C.label(i18n.t("Address: {a}").format(a=self._endpoint), level="META", colour=theme.NEUTRAL[600], wrap=True))

    def sample(self, campaign: dict) -> str:
        t = next((x for x in self._templates if x.get("name") == campaign.get("template_name")), {})
        n = 0
        for comp in t.get("components") or []:
            if comp.get("type") == "BODY":
                import re
                n = len({int(v) for v in re.findall(r"\{\{\s*(\d+)\s*\}\}", comp.get("text", ""))})
        body = {"apiKey": "<your API key>", "campaignName": campaign.get("name"), "destination": "919812345678", "userName": "Customer name",
                "templateParams": ["value %d" % (i + 1) for i in range(n)], "tags": [], "attributes": {}}
        return "POST %s\n%s" % (self._endpoint, json.dumps(body, indent=2))

    def _copy(self, campaign: dict):
        ui.copy_text(self, self.sample(campaign), i18n.t("the address and a sample request"))

    def _make(self):
        name = self.name.text().strip()
        t = self.template.currentData()
        if not name or not t:
            self.error.error(i18n.t("Give it a name and choose an approved template."))
            return
        ui.call(self, "api_campaigns/create", {"name": name, "template_name": t.get("name"), "language": t.get("language") or "en_US"},
                done=lambda _r: (self.name.clear(), self.error.ok(i18n.t("Made. It is on.")), self.reload()), failed=lambda m, _d: self.error.error(m))

    def _delete(self, campaign: dict):
        if not ui.confirm(self, i18n.t("Delete API campaign"), i18n.t("Delete “{n}”? Software that still sends to it will get an error.").format(n=campaign.get("name"))):
            return
        ui.call(self, "api_campaigns/delete", {"campaign_id": campaign["id"]}, done=lambda _r: self.reload(), failed=lambda m, _d: self.error.error(m))
