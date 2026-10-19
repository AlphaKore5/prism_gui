"""Settings → Business profile, and Blue tick.

Business profile is what a customer sees when they tap your name in a chat: a photo, a one-line About, an address, an email, up to two
websites and a category. It is read from and saved to WhatsApp itself (nothing is kept here), after the same checks Meta applies.

Blue tick is a checklist for asking Meta for the verified badge. Meta decides, and no one can buy it; what can be shown is which of the
things Meta looks at are already true of this number (from what Meta reports about it), and what is left for a person to confirm.
"""
from __future__ import annotations

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.media_lib import AssetField
from addons.whatsapp.settings import _COLUMN, _scrolled
from widgets import controls as C

ABOUT_MAX, ADDRESS_MAX, DESCRIPTION_MAX = 139, 256, 512


def vertical_choices() -> list:
    """(code, label) — Meta's business categories. Literal i18n.t calls, so the extractor sees every word."""
    return [("", i18n.t("Not set")), ("PROF_SERVICES", i18n.t("Professional services")), ("RETAIL", i18n.t("Retail")), ("EDU", i18n.t("Education")),
            ("HEALTH", i18n.t("Health and wellness")), ("AUTO", i18n.t("Automotive")), ("APPAREL", i18n.t("Clothing and apparel")), ("BEAUTY", i18n.t("Beauty and personal care")),
            ("FINANCE", i18n.t("Finance and banking")), ("GROCERY", i18n.t("Grocery")), ("HOTEL", i18n.t("Hotel and lodging")), ("TRAVEL", i18n.t("Travel")),
            ("RESTAURANT", i18n.t("Restaurant")), ("EVENT_PLAN", i18n.t("Event planning")), ("ENTERTAIN", i18n.t("Entertainment")), ("NONPROFIT", i18n.t("Non-profit")),
            ("GOVT", i18n.t("Government")), ("OTHER", i18n.t("Other"))]


class ProfileSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)

        card, cc = ui.card(i18n.t("Business profile"), i18n.t("What a customer sees when they tap your name in a chat. It lives at WhatsApp; saving here changes it there."), width=_COLUMN)
        self.number = C.label("", level="META", colour=theme.NEUTRAL[600])
        cc.addWidget(self.number)
        self.about = QLineEdit()
        self.about.setMaxLength(ABOUT_MAX)
        self.about.setMinimumHeight(38)
        self.about.setPlaceholderText(i18n.t("One line about your business"))
        self.about_count = C.label("", level="META", colour=theme.NEUTRAL[500])
        self.about.textChanged.connect(lambda t: self.about_count.setText("%d/%d" % (len(t), ABOUT_MAX)))
        cc.addWidget(ui.field(i18n.t("About"), self.about))
        cc.addWidget(self.about_count)
        self.description = QPlainTextEdit()
        self.description.setFixedHeight(84)
        self.description.setPlaceholderText(i18n.t("What you do, in a few sentences"))
        cc.addWidget(ui.field(i18n.t("Description"), self.description, i18n.t("Up to 512 characters.")))
        self.address = QLineEdit()
        self.address.setMinimumHeight(38)
        self.address.setMaxLength(ADDRESS_MAX)
        cc.addWidget(ui.field(i18n.t("Address"), self.address))
        self.email = QLineEdit()
        self.email.setMinimumHeight(38)
        self.email.setPlaceholderText("hello@example.com")
        cc.addWidget(ui.field(i18n.t("Email"), self.email))
        sites = QHBoxLayout()
        sites.setSpacing(theme.SPACE_3)
        self.site1, self.site2 = QLineEdit(), QLineEdit()
        for e, hint in ((self.site1, "https://example.com"), (self.site2, "https://")):
            e.setMinimumHeight(38)
            e.setPlaceholderText(hint)
        sites.addWidget(ui.field(i18n.t("Website"), self.site1), stretch=1)
        sites.addWidget(ui.field(i18n.t("Another website"), self.site2), stretch=1)
        cc.addLayout(sites)
        self.vertical = QComboBox()
        self.vertical.setMinimumHeight(38)
        for code, label in vertical_choices():
            self.vertical.addItem(label, code)
        cc.addWidget(ui.field(i18n.t("Category"), self.vertical))
        self.photo = AssetField(("image",), empty_text=i18n.t("Keep the current photo"))
        cc.addWidget(ui.field(i18n.t("Profile photo"), self.photo, i18n.t("A square JPG or PNG, at least 640 pixels wide. Choose one from your Media Library.")))
        row = QHBoxLayout()
        self.note = ui.note()
        row.addWidget(self.note, stretch=1)
        self.reload_btn = C.button(i18n.t("Read it again"), "tertiary", on_click=self.activate)
        row.addWidget(self.reload_btn)
        self.save_btn = C.button(i18n.t("Save to WhatsApp"), "primary", on_click=self._save)
        row.addWidget(self.save_btn)
        cc.addLayout(row)
        col.addWidget(card)
        col.addStretch(1)

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def activate(self):
        self.note.set(i18n.t("Reading your profile from WhatsApp…"), "quiet")
        ui.call(self, "profile/get", {}, done=self._loaded, failed=lambda m, _d: self.note.error(m))

    def deactivate(self):
        pass

    def _loaded(self, reply: dict):
        p = reply.get("profile") or {}
        self.number.setText(reply.get("number") or "")
        self.about.setText(p.get("about") or "")
        self.description.setPlainText(p.get("description") or "")
        self.address.setText(p.get("address") or "")
        self.email.setText(p.get("email") or "")
        sites = list(p.get("websites") or [])
        self.site1.setText(sites[0] if sites else "")
        self.site2.setText(sites[1] if len(sites) > 1 else "")
        self.vertical.setCurrentIndex(max(self.vertical.findData(p.get("vertical") or ""), 0))
        self.photo.clear()
        if reply.get("stale"):
            self.note.set(i18n.t("WhatsApp could not be reached just now, so this is what was last read. {e}").format(e=reply.get("problem") or ""), "warn")
        else:
            self.note.clear_note()

    def profile(self) -> dict:
        out = {"about": self.about.text().strip(), "description": self.description.toPlainText().strip(), "address": self.address.text().strip(),
               "email": self.email.text().strip(), "websites": [w for w in (self.site1.text().strip(), self.site2.text().strip()) if w],
               "vertical": self.vertical.currentData() or None}
        if self.photo.asset_id():
            out["picture_asset_id"] = self.photo.asset_id()
        return out

    def _save(self):
        self.save_btn.setEnabled(False)
        self.note.set(i18n.t("Saving…"), "quiet")
        ui.call(self, "profile/save", {"profile": self.profile()}, done=self._saved, failed=lambda m, _d: (self.save_btn.setEnabled(True), self.note.error(m)))

    def _saved(self, reply: dict):
        self.save_btn.setEnabled(True)
        self._loaded(reply)
        self.note.ok(i18n.t("Saved. Customers see it the next time they open your profile."))


# ── blue tick ────────────────────────────────────────────────────────────────

TIER_RANK = {"TIER_50": 0, "TIER_250": 1, "TIER_1K": 2, "TIER_2K": 3, "TIER_10K": 4, "TIER_100K": 5, "TIER_UNLIMITED": 6}


def checklist(numbers: list, profile: dict, confirmed: dict) -> list:
    """[(key, words, state, how)] — state is "yes", "no", or "manual" (a person ticks it when it is true: Meta has no way to tell us). Pure, so it can be tested."""
    n = (numbers or [{}])[0]
    p = profile or {}
    tier = TIER_RANK.get(n.get("tier"), -1)
    filled = bool((p.get("about") or "").strip() and (p.get("address") or "").strip() and (p.get("websites") or []) and (p.get("email") or "").strip())
    items = [
        ("name", i18n.t("Your display name is approved by Meta"), "yes" if n.get("name_status") == "APPROVED" else "no",
         i18n.t("Meta shows the status as {s}.").format(s=(n.get("name_status") or i18n.t("unknown")).replace("_", " ").lower())),
        ("quality", i18n.t("Your number's quality is high"), "yes" if n.get("quality") == "GREEN" else "no", i18n.t("Quality is a rating Meta gives from how customers react to your messages.")),
        ("volume", i18n.t("You can start at least 1,000 chats a day"), "yes" if tier >= TIER_RANK["TIER_1K"] else "no", i18n.t("Your daily limit grows as you send good messages.")),
        ("profile", i18n.t("Your business profile is complete"), "yes" if filled else "no", i18n.t("About, address, email and a website are all filled in.")),
        ("verified", i18n.t("Your business is verified in Meta Business Manager"), "manual",
         i18n.t("Meta checks your registration documents. Tick this once it shows Verified.")),
        ("known", i18n.t("People can find your business online"), "manual",
         i18n.t("Meta looks for news articles or a well-known website that mention you. Tick this when you have some.")),
    ]
    return items


class BlueTickSection(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg if isinstance(cfg, dict) else {}
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)
        card, cc = ui.card(i18n.t("Blue tick"), i18n.t("The verified badge next to your name. Meta decides who gets it and cannot be paid for it. This is what it looks at, and "
                                                       "where you stand on each."), width=_COLUMN)
        self.items = QVBoxLayout()
        self.items.setSpacing(theme.SPACE_3)
        cc.addLayout(self.items)
        self.verdict = C.label("", level="SUPPORT", weight=700, wrap=True)
        cc.addWidget(self.verdict)
        row = QHBoxLayout()
        self.note = ui.note()
        row.addWidget(self.note, stretch=1)
        row.addWidget(C.button(i18n.t("Check with Meta again"), "secondary", on_click=self._refresh_numbers))
        row.addWidget(C.button(i18n.t("Open Meta Business Suite"), "primary", on_click=lambda: QDesktopServices.openUrl(QUrl("https://business.facebook.com/"))))
        cc.addLayout(row)
        col.addWidget(card)
        col.addStretch(1)
        self._numbers: list = []
        self._profile: dict = {}

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def _confirmed(self) -> dict:
        return dict((self.cfg.get("whatsapp_blue_tick") or {}))

    def activate(self):
        ui.call(self, "numbers/limits", {}, done=lambda r: (setattr(self, "_numbers", r.get("numbers") or []), self._draw()), failed=lambda m, _d: self.note.error(m))
        ui.call(self, "profile/get", {}, done=lambda r: (setattr(self, "_profile", r.get("profile") or {}), self._draw()), failed=lambda _m, _d: None)

    def deactivate(self):
        pass

    def _refresh_numbers(self):
        self.note.set(i18n.t("Asking Meta…"), "quiet")
        ui.call(self, "numbers/refresh", {}, done=lambda r: (setattr(self, "_numbers", r.get("numbers") or []), self._draw(), self.note.ok(i18n.t("Updated."))),
                failed=lambda m, _d: self.note.error(m))

    def _tick(self, key: str, on: bool):
        store = self._confirmed()
        store[key] = bool(on)
        self.cfg["whatsapp_blue_tick"] = store
        try:
            import core_bridge as CB
            CB.config.save(self.cfg)
        except Exception:                                      # noqa: BLE001  (a checklist tick is a convenience: never break the screen over it)
            pass
        self._draw()

    def _draw(self):
        ui.clear(self.items)
        confirmed = self._confirmed()
        rows = checklist(self._numbers, self._profile, confirmed)
        for key, words, state, how in rows:
            line = QHBoxLayout()
            line.setSpacing(theme.SPACE_3)
            if state == "manual":
                box = QCheckBox()
                box.setAccessibleName(words)
                box.setChecked(bool(confirmed.get(key)))                    # set before the connection, so drawing never counts as a tick
                box.toggled.connect(lambda on, k=key: self._tick(k, on))
                line.addWidget(box)
            else:
                line.addWidget(C.Pill(i18n.t("Yes") if state == "yes" else i18n.t("Not yet"), "ok" if state == "yes" else "warn"))
            text = QVBoxLayout()
            text.setSpacing(0)
            text.addWidget(C.label(words, level="SUPPORT", weight=700))
            text.addWidget(C.label(how, level="META", colour=theme.NEUTRAL[600], wrap=True))
            line.addLayout(text, stretch=1)
            holder = QWidget()
            holder.setLayout(line)
            self.items.addWidget(holder)
        done = sum(1 for k, _w, st, _h in rows if st == "yes" or (st == "manual" and confirmed.get(k)))
        self.verdict.setText(i18n.t("Everything Meta looks at is in place. You can apply from Meta Business Suite.") if done == len(rows) else
                             i18n.t("{n} of {t} are in place. Apply once they all are — an early application is usually refused.").format(n=done, t=len(rows)))
