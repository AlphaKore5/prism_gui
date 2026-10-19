"""Settings → Audit log: who changed what, and when.

Every change that matters (a setting, someone's access, a template, a campaign, an ad, money, a key) leaves one line. The log never holds a secret, a message or a phone number.
It is kept for 400 days. Reading and downloading it is part of the Enterprise plan; owners and managers only.
"""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.settings import _COLUMN, _scrolled
from widgets import controls as C


def area_names() -> dict:
    """Literal i18n.t calls so the string extractor sees each word."""
    return {"ads": i18n.t("Ads"), "ai": i18n.t("AI agents"), "api": i18n.t("API"), "autos": i18n.t("Automatic messages"), "campaigns": i18n.t("Campaigns"), "capi": i18n.t("Conversions"),
            "consent": i18n.t("Opt-in and opt-out"), "contacts": i18n.t("Contacts"), "flows": i18n.t("Chatbot flows"), "forms": i18n.t("Forms"), "inbox": i18n.t("Inbox"),
            "integrations": i18n.t("Stores"), "media": i18n.t("Media library"), "partner": i18n.t("Resellers"), "profile": i18n.t("Business profile"), "shop": i18n.t("Shop"),
            "sso": i18n.t("Sign-in"), "team": i18n.t("Team"), "templates": i18n.t("Templates"), "usage": i18n.t("Plan and usage"), "webhooks": i18n.t("Webhooks")}


class AuditSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)
        card, cc = ui.card(i18n.t("Audit log"), i18n.t("Who changed what, and when. It never holds a secret, a message or a phone number, and lines are kept for 400 days."), _COLUMN)
        bar = QHBoxLayout()
        bar.setSpacing(theme.SPACE_2)
        self.search = QLineEdit()
        self.search.setMinimumHeight(38)
        self.search.setPlaceholderText(i18n.t("Search what happened"))
        self.search.setAccessibleName(i18n.t("Search the log"))
        self.search.returnPressed.connect(self.load)
        bar.addWidget(self.search, 1)
        self.area = QComboBox()
        self.area.setMinimumHeight(38)
        self.area.setAccessibleName(i18n.t("Area"))
        self.area.addItem(i18n.t("Everything"), "")
        self.area.activated.connect(lambda _i: self.load())
        bar.addWidget(self.area)
        self.download_btn = C.button(i18n.t("Download"), "secondary", icon_name="download", on_click=self.download)
        bar.addWidget(self.download_btn)
        cc.addLayout(bar)
        self.note = ui.note()
        cc.addWidget(self.note)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(theme.SPACE_1)
        cc.addLayout(self.rows)
        self.more = C.label("", level="META", colour=theme.NEUTRAL[500])
        cc.addWidget(self.more)
        col.addWidget(card)
        col.addStretch(1)
        self._loaded = False

    def say(self, message: str, error: bool = False):
        self.note.set(message, "error" if error else "ok")

    def activate(self):
        self.load()

    def deactivate(self):
        pass

    def load(self):
        d = {"q": self.search.text().strip(), "action": self.area.currentData() or "", "limit": 100}
        ui.call(self, "audit/list", d, done=self._shown, failed=self._failed)

    def _failed(self, message: str, detail: dict):
        self._loaded = True
        ui.clear(self.rows)
        if (detail or {}).get("reason") == "plan_feature":
            self.download_btn.setEnabled(False)
            self.note.set(i18n.t("The audit log is part of the Enterprise plan."), "warn")
        else:
            self.note.error(message)

    def _shown(self, reply: dict):
        self._loaded = True
        self.note.clear_note()
        names = area_names()
        keep = self.area.currentData()
        self.area.blockSignals(True)
        self.area.clear()
        self.area.addItem(i18n.t("Everything"), "")
        for a in reply.get("areas") or []:
            self.area.addItem(names.get(a, a.title()), a)
        self.area.setCurrentIndex(max(self.area.findData(keep), 0))
        self.area.blockSignals(False)
        ui.clear(self.rows)
        entries = list(reply.get("entries") or [])
        if not entries:
            self.rows.addWidget(C.label(i18n.t("Nothing yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for e in entries:
            line = QHBoxLayout()
            line.setSpacing(theme.SPACE_3)
            line.addWidget(C.label((e.get("at") or "")[:16].replace("T", " "), level="META", colour=theme.NEUTRAL[500]))
            line.addWidget(C.label(e.get("summary") or "", level="SUPPORT", wrap=True), 1)
            line.addWidget(C.label(e.get("actor") or i18n.t("System"), level="META", colour=theme.NEUTRAL[600]))
            holder = QWidget()
            holder.setLayout(line)
            line.setContentsMargins(0, 3, 0, 3)
            self.rows.addWidget(holder)
        total = reply.get("total", len(entries))
        self.more.setText(i18n.t("Showing the latest {n} of {t}. Download the log for all of it.").format(n=len(entries), t=total) if total > len(entries) else "")

    def download(self):
        ui.call(self, "audit/export", {}, done=self._download)

    def _download(self, reply: dict):
        path, _ = QFileDialog.getSaveFileName(self, i18n.t("Save the audit log"), "audit-log.csv", "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(reply["csv"])
            self.say(i18n.t("Saved."))
