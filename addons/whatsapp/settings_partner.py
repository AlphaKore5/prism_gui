"""Settings → Branding and resellers.

Branding: the name, colour, logo and support address shown to your customers instead of Prism's. If you are a customer of a reseller, theirs is shown until you set your own.
Resellers: a customer workspace gives you a one-time code; you paste it here to link it. You see how busy each customer is (messages and contacts — never what is in them) and keep a
simple monthly record of the commission you earn from each. Needs the Unlimited or Enterprise plan; only the owner can link, unlink or record commission.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import shop_money as M
from addons.whatsapp import ui
from addons.whatsapp.media_lib import AssetField
from addons.whatsapp.settings import _COLUMN, _scrolled
from widgets import controls as C


def _line(placeholder: str = "", text: str = "") -> QLineEdit:
    e = QLineEdit(text)
    e.setMinimumHeight(38)
    e.setPlaceholderText(placeholder)
    return e


class PartnerSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.customers: list = []
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)

        card, bc = ui.card(i18n.t("Branding"), i18n.t("Your name and colours, shown to your customers where they would otherwise see Prism's."), _COLUMN)
        self.from_label = C.label("", level="META", colour=theme.NEUTRAL[600], wrap=True)
        bc.addWidget(self.from_label)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.name = _line(i18n.t("BuildDesk"))
        self.name.setAccessibleName(i18n.t("Brand name"))
        self.colour = _line("#1A7F4B")
        self.colour.setAccessibleName(i18n.t("Brand colour"))
        row.addWidget(ui.field(i18n.t("Name"), self.name), 2, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Colour"), self.colour, i18n.t("Six digits after a #.")), 1, Qt.AlignTop)
        bc.addLayout(row)
        self.logo = AssetField(kinds=["image"], empty_text=i18n.t("No logo — choose one from your Media Library"))
        bc.addWidget(ui.field(i18n.t("Logo"), self.logo))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.email = _line("help@yourbrand.com")
        self.email.setAccessibleName(i18n.t("Support e-mail"))
        self.url = _line("https://yourbrand.com/help")
        self.url.setAccessibleName(i18n.t("Support page"))
        row.addWidget(ui.field(i18n.t("Support e-mail"), self.email), 1, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Support page"), self.url), 1, Qt.AlignTop)
        bc.addLayout(row)
        self.domain = _line("app.yourbrand.com")
        self.domain.setAccessibleName(i18n.t("Your own address"))
        bc.addWidget(ui.field(i18n.t("Your own web address"), self.domain, i18n.t("Saved for you. Pointing this address at Prism is arranged with Prism's team.")))
        self.hide_vendor = QCheckBox(i18n.t("Don't mention Prism in pages my customers see"))
        bc.addWidget(self.hide_vendor)
        self.brand_note = ui.note()
        bc.addWidget(self.brand_note)
        row = QHBoxLayout()
        self.brand_save = C.button(i18n.t("Save branding"), "primary", on_click=self.save_branding)
        row.addWidget(self.brand_save)
        row.addStretch(1)
        bc.addLayout(row)
        col.addWidget(card)

        card, rc = ui.card(i18n.t("Your reseller"), i18n.t("If a reseller looks after you, give them this code to link your workspace. It works once, for three days."), _COLUMN)
        self.reseller_line = C.label("", level="SUPPORT", wrap=True)
        rc.addWidget(self.reseller_line)
        row = QHBoxLayout()
        self.invite_btn = C.button(i18n.t("Make a code for my reseller"), "secondary", on_click=self.invite)
        self.unlink_me_btn = C.button(i18n.t("End the link"), "tertiary", on_click=self.unlink_me)
        row.addWidget(self.invite_btn)
        row.addWidget(self.unlink_me_btn)
        row.addStretch(1)
        rc.addLayout(row)
        self.code_line = C.label("", level="CARD_TITLE")
        self.code_line.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rc.addWidget(self.code_line)
        col.addWidget(card)

        card, cc = ui.card(i18n.t("Your customers"), i18n.t("Customer workspaces linked to you. You see how busy they are, never what is in them."), _COLUMN)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        self.code = _line("XXXX-XXXX-XXXX-XXXX")
        self.code.setAccessibleName(i18n.t("Customer's code"))
        self.percent = _line("20")
        self.percent.setAccessibleName(i18n.t("Commission percent"))
        self.percent.setMaximumWidth(90)
        self.link_btn = C.button(i18n.t("Link a customer"), "secondary", on_click=self.link)
        row.addWidget(ui.field(i18n.t("Code from your customer"), self.code), 3, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Your commission (%)"), self.percent), 1, Qt.AlignTop)
        row.addWidget(self.link_btn)
        cc.addLayout(row)
        self.list = QVBoxLayout()
        self.list.setSpacing(theme.SPACE_2)
        cc.addLayout(self.list)
        self.partner_note = ui.note()
        cc.addWidget(self.partner_note)
        col.addWidget(card)

        card, lc = ui.card(i18n.t("Commission"), i18n.t("Add what a customer paid you for a month; Prism works out your share."), _COLUMN)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        self.who = QComboBox()
        self.who.setMinimumHeight(38)
        self.who.setAccessibleName(i18n.t("Customer"))
        self.period = _line("2026-10")
        self.period.setAccessibleName(i18n.t("Month"))
        self.period.setMaximumWidth(110)
        self.base = _line("4999")
        self.base.setAccessibleName(i18n.t("Amount the customer paid you"))
        self.add_btn = C.button(i18n.t("Add"), "secondary", on_click=self.add_commission)
        row.addWidget(ui.field(i18n.t("Customer"), self.who), 2, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Month"), self.period), 1, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Paid you (Rs)"), self.base), 1, Qt.AlignTop)
        row.addWidget(self.add_btn)
        lc.addLayout(row)
        self.owed = C.label("", level="SUPPORT", weight=700)
        lc.addWidget(self.owed)
        self.ledger = QVBoxLayout()
        self.ledger.setSpacing(2)
        lc.addLayout(self.ledger)
        self.ledger_note = ui.note()
        lc.addWidget(self.ledger_note)
        col.addWidget(card)
        col.addStretch(1)
        self._gate = [self.brand_save, self.link_btn, self.add_btn]

    def say(self, message: str, error: bool = False):
        self.brand_note.set(message, "error" if error else "ok")

    # ── loading ──────────────────────────────────────────────────────────────
    def activate(self):
        ui.call(self, "partner/branding/get", {}, done=self._branding, failed=self._plan_or_error)
        ui.call(self, "partner/reseller", {}, done=self._reseller, failed=lambda m, _d: None)
        ui.call(self, "partner/customers", {}, done=self._customers, failed=self._plan_or_error)
        ui.call(self, "partner/ledger/list", {}, done=self._ledger, failed=lambda m, _d: None)

    def deactivate(self):
        pass

    def _plan_or_error(self, message: str, detail: dict):
        if (detail or {}).get("reason") == "plan_feature":
            for w in self._gate:
                w.setEnabled(False)
            self.brand_note.set(i18n.t("Branding and reseller tools are part of the Unlimited and Enterprise plans."), "warn")
        else:
            self.brand_note.error(message)

    def _branding(self, reply: dict):
        b = reply["branding"]
        self.name.setText(b.get("name") or "")
        self.colour.setText(b.get("colour") or "")
        self.email.setText(b.get("support_email") or "")
        self.url.setText(b.get("support_url") or "")
        self.domain.setText(b.get("custom_domain") or "")
        self.hide_vendor.setChecked(bool(b.get("hide_vendor")))
        if b.get("logo_asset_id"):
            self.logo.set_asset_id(b["logo_asset_id"])
        eff = reply.get("effective") or {}
        self.from_label.setText({"own": i18n.t("Showing your own branding."), "reseller": i18n.t("Showing your reseller's branding ({n}) until you set your own.").format(n=eff.get("name") or ""),
                                 "none": i18n.t("No branding set: Prism's own is shown.")}.get(eff.get("from"), ""))

    def branding_payload(self) -> dict:
        return {"name": self.name.text().strip(), "colour": self.colour.text().strip(), "support_email": self.email.text().strip(), "support_url": self.url.text().strip(),
                "custom_domain": self.domain.text().strip(), "logo_asset_id": self.logo.asset_id() or "", "hide_vendor": self.hide_vendor.isChecked()}

    def save_branding(self):
        self.brand_save.setEnabled(False)
        ui.call(self, "partner/branding/save", self.branding_payload(), done=self._branding_saved, failed=self._branding_failed)

    def _branding_saved(self, _reply: dict):
        self.brand_save.setEnabled(True)
        self.say(i18n.t("Saved."))
        self.activate()

    def _branding_failed(self, message: str, _detail: dict):
        self.brand_save.setEnabled(True)
        self.say(message, error=True)

    # ── the link to a reseller ───────────────────────────────────────────────
    def _reseller(self, reply: dict):
        r = reply.get("reseller")
        self.unlink_me_btn.setVisible(bool(r))
        self.invite_btn.setVisible(not r)
        self.reseller_line.setText(i18n.t("Linked to {n}.").format(n=r.get("name") or i18n.t("your reseller")) if r else i18n.t("Not linked to a reseller."))

    def invite(self):
        ui.call(self, "partner/invite", {}, done=lambda r: self.code_line.setText(r["code"]), failed=lambda m, _d: self.brand_note.error(m))

    def unlink_me(self):
        if ui.confirm(self, i18n.t("End the link"), i18n.t("End the link to your reseller? They stop seeing how busy this workspace is.")):
            ui.call(self, "partner/unlink", {}, done=lambda _r: self.activate())

    # ── customers ────────────────────────────────────────────────────────────
    def link(self):
        if not self.code.text().strip():
            self.partner_note.error(i18n.t("Paste the code your customer gave you."))
            return
        ui.call(self, "partner/redeem", {"code": self.code.text().strip(), "commission_percent": self.percent.text().strip() or "0"},
                done=lambda _r: (self.code.clear(), self.partner_note.ok(i18n.t("Linked.")), self.activate()), failed=lambda m, _d: self.partner_note.error(m))

    def _customers(self, reply: dict):
        self.customers = list(reply.get("customers") or [])
        ui.clear(self.list)
        self.who.clear()
        if not self.customers:
            self.list.addWidget(C.label(i18n.t("No customers linked yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for c in self.customers:
            self.who.addItem(c["name"] or i18n.t("Customer"), c["child_tenant_id"])
            row = QHBoxLayout()
            row.setSpacing(theme.SPACE_2)
            row.addWidget(C.label(c["name"] or i18n.t("Customer"), level="SUPPORT", weight=700), 2)
            row.addWidget(C.label(i18n.t("{s} sent · {r} received · {n} contacts").format(s=c["sent"], r=c["received"], n=c["contacts"]), level="META", colour=theme.NEUTRAL[600]), 3)
            row.addWidget(C.Pill("%g%%" % c["commission_percent"], "neutral"))
            row.addWidget(C.button(i18n.t("Unlink"), "tertiary", small=True, on_click=lambda _=False, k=c["child_tenant_id"]: self.unlink(k)))
            holder = QWidget()
            holder.setLayout(row)
            row.setContentsMargins(0, 2, 0, 2)
            self.list.addWidget(holder)

    def unlink(self, child_id: str):
        if ui.confirm(self, i18n.t("Unlink customer"), i18n.t("Unlink this customer? You stop seeing how busy it is. Commission already recorded is kept.")):
            ui.call(self, "partner/unlink", {"child_tenant_id": child_id}, done=lambda _r: self.activate())

    # ── commission ───────────────────────────────────────────────────────────
    def add_commission(self):
        if self.who.currentData() is None:
            self.ledger_note.error(i18n.t("Link a customer first."))
            return
        try:
            M.paise(self.base.text(), what="amount")
        except M.MoneyError as why:
            self.ledger_note.error(str(why))
            return
        ui.call(self, "partner/ledger/add", {"child_tenant_id": self.who.currentData(), "period": self.period.text().strip(), "base": self.base.text().strip()},
                done=lambda r: (self.ledger_note.ok(i18n.t("Your share: {a}").format(a=M.money_text(r["amount_paise"]))), self.activate()), failed=lambda m, _d: self.ledger_note.error(m))

    def _ledger(self, reply: dict):
        ui.clear(self.ledger)
        self.owed.setText(i18n.t("Owed to you: {o}   ·   Paid: {p}").format(o=M.money_text(reply.get("owed_paise", 0)), p=M.money_text(reply.get("paid_paise", 0))))
        names = {c["child_tenant_id"]: c["name"] for c in self.customers}
        for e in reply.get("entries") or []:
            row = QHBoxLayout()
            row.setSpacing(theme.SPACE_2)
            row.addWidget(C.label("%s  ·  %s" % (e["period"], names.get(e["child_tenant_id"]) or i18n.t("Customer")), level="META", colour=theme.NEUTRAL[700]), 2)
            row.addWidget(C.label(i18n.t("{b} × {p}% = {a}").format(b=M.money_text(e["base_paise"]), p="%g" % e["percent"], a=M.money_text(e["amount_paise"])), level="META", colour=theme.NEUTRAL[600]), 3)
            if e["status"] == "accrued":
                row.addWidget(C.button(i18n.t("Mark paid"), "tertiary", small=True, on_click=lambda _=False, i=e["id"]: self.mark_paid(i)))
            else:
                row.addWidget(C.Pill(i18n.t("Paid"), "ok"))
            holder = QWidget()
            holder.setLayout(row)
            row.setContentsMargins(0, 2, 0, 2)
            self.ledger.addWidget(holder)

    def mark_paid(self, entry_id):
        ui.call(self, "partner/ledger/paid", {"entry_id": entry_id}, done=lambda _r: self.activate())
