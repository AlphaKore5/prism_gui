"""The Ads tab — Facebook and Instagram ads that open a WhatsApp chat, take people to your website, or collect their details on Facebook itself.

Safety comes first on this screen, because an ad spends money:
  · every ad is made PAUSED — nothing is spent until you turn it on yourself;
  · turning one on asks first and says how much it may spend a day;
  · the first ad of a new account should be looked at in Meta's own Ads Manager before it is turned on;
  · Meta looks at every ad before it runs and may turn it down — the screen says where each ad stands and, when Meta refuses one, why.

Connecting an ad account is done by signing in with Facebook, or — if that is not set up — by pasting an access token. The token is stored encrypted on Prism's server and
never shown again. Below the ads are Audiences (lists of people to show ads to, made from your segments) and Suggestions (what to change, from the numbers, only when you say yes).
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateTimeEdit, QDoubleSpinBox, QFrame, QHBoxLayout, QLineEdit, QMenu, QPlainTextEdit, QRadioButton, QScrollArea,
                               QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.ad_audiences import AudiencesView, SuggestionsView
from addons.whatsapp.ad_connect import FacebookConnectDialog
from addons.whatsapp.ad_results import AdResultsDialog
from addons.whatsapp.ad_targeting_ui import Placements, SearchPicker
from addons.whatsapp.chat import short_time
from addons.whatsapp.media_lib import AssetField
from dialogs.base import PrismDialog
from widgets import controls as C

KINDS = ("ctwa", "website", "leadform")
QUESTIONS = ("FULL_NAME", "PHONE", "EMAIL", "CITY", "COMPANY_NAME")
MIN_BUDGET_RUPEES = 1


def kind_choices() -> list:
    """(kind, name, what it does)."""
    return [("ctwa", i18n.t("A chat on WhatsApp"), i18n.t("People tap the ad and a WhatsApp chat with you opens.")),
            ("website", i18n.t("Visits to my website"), i18n.t("People tap the ad and your web page opens.")),
            ("leadform", i18n.t("Leads on Facebook"), i18n.t("People fill in a short form without leaving Facebook; their details come to you."))]


def kind_name(kind: str) -> str:
    return next((n for k, n, _h in kind_choices() if k == kind), kind or "")


def cta_choices(kind: str) -> list:
    words = {"LEARN_MORE": i18n.t("Learn more"), "SHOP_NOW": i18n.t("Shop now"), "SIGN_UP": i18n.t("Sign up"), "CONTACT_US": i18n.t("Contact us"), "GET_QUOTE": i18n.t("Get a quote"),
             "BOOK_TRAVEL": i18n.t("Book now"), "APPLY_NOW": i18n.t("Apply now"), "DOWNLOAD": i18n.t("Download"), "ORDER_NOW": i18n.t("Order now"), "SUBSCRIBE": i18n.t("Subscribe"),
             "GET_OFFER": i18n.t("Get offer")}
    keys = ("LEARN_MORE", "SHOP_NOW", "SIGN_UP", "CONTACT_US", "GET_QUOTE", "BOOK_TRAVEL", "APPLY_NOW", "DOWNLOAD", "ORDER_NOW", "SUBSCRIBE", "GET_OFFER") if kind == "website" else \
        ("SIGN_UP", "LEARN_MORE", "GET_QUOTE", "APPLY_NOW", "SUBSCRIBE", "CONTACT_US")
    return [(k, words[k]) for k in keys]


def question_words() -> dict:
    return {"FULL_NAME": i18n.t("Full name"), "PHONE": i18n.t("Phone number"), "EMAIL": i18n.t("Email address"), "CITY": i18n.t("City"), "COMPANY_NAME": i18n.t("Company name")}


def state_words(ad: dict) -> tuple:
    """(words, tone, state) for where an ad stands — Meta's own state when it has been read, else ours."""
    meta = str(ad.get("meta_status") or "").upper()
    table = {"ACTIVE": (i18n.t("Running"), "ok", "running"), "PAUSED": (i18n.t("Paused"), "quiet", "paused"), "PENDING_REVIEW": (i18n.t("In review at Meta"), "info", "review"),
             "IN_PROCESS": (i18n.t("Meta is processing it"), "info", "review"), "DISAPPROVED": (i18n.t("Turned down by Meta"), "err", "rejected"),
             "WITH_ISSUES": (i18n.t("Running with problems"), "warn", "issues"), "CAMPAIGN_PAUSED": (i18n.t("Its campaign is paused"), "quiet", "paused"),
             "ADSET_PAUSED": (i18n.t("Its audience is paused"), "quiet", "paused"), "ARCHIVED": (i18n.t("Archived"), "quiet", "archived"), "DELETED": (i18n.t("Removed"), "quiet", "archived"),
             "PENDING_BILLING_INFO": (i18n.t("Meta needs payment details"), "warn", "issues")}
    if meta in table:
        return table[meta]
    status = str(ad.get("status") or "").upper()
    return {"PAUSED": (i18n.t("Paused"), "quiet", "paused"), "ACTIVE": (i18n.t("Running"), "ok", "running"), "FAILED": (i18n.t("Problem"), "err", "failed"),
            "ERROR": (i18n.t("Problem"), "err", "failed"), "DELETED": (i18n.t("Removed"), "quiet", "archived"), "ARCHIVED": (i18n.t("Archived"), "quiet", "archived")}.get(
        status, (status.capitalize() or "—", "quiet", "unknown"))


def rupees_to_paise(value: float) -> int:
    return int(round(float(value) * 100))


def budget_words(budget: dict) -> str:
    b = budget or {}
    if b.get("lifetime"):
        return i18n.t("Rs {n} in all").format(n="{:,.0f}".format(b["lifetime"] / 100))
    if b.get("daily"):
        return i18n.t("Rs {n} a day").format(n="{:,.0f}".format(b["daily"] / 100))
    return ""


def insight_lines(ins: dict) -> list:
    """What Meta reported for an ad, as lines to show."""
    out = [(i18n.t("People who saw it"), "{:,}".format(int(ins.get("reach") or 0))), (i18n.t("Times shown"), "{:,}".format(int(ins.get("impressions") or 0))),
           (i18n.t("Clicks"), "{:,}".format(int(ins.get("clicks") or 0))), (i18n.t("Spent so far"), "₹{:,.2f}".format(float(ins.get("spend") or 0)))]
    conv = int(ins.get("conversations_started", ins.get("conversations")) or 0)
    out.append((i18n.t("Chats started"), "{:,}".format(conv)))
    if ins.get("cost_per_conversation"):
        out.append((i18n.t("Cost per chat"), "₹{:,.2f}".format(float(ins["cost_per_conversation"]))))
    return out


class ConnectAccountDialog(PrismDialog):
    def __init__(self, parent=None):
        super().__init__(i18n.t("Connect your ad account"), i18n.t("Prism makes ads in this account on your behalf. Every ad starts paused."),
                         icon="globe", parent=parent)
        self.acct = QLineEdit()
        self.acct.setPlaceholderText(i18n.t("The number shown in Ads Manager, e.g. 1234567890"))
        self.acct.setMinimumHeight(38)
        self.body.addWidget(ui.field(i18n.t("Ad account number"), self.acct))
        self.page = QLineEdit()
        self.page.setPlaceholderText(i18n.t("The Facebook Page your ads run as"))
        self.page.setMinimumHeight(38)
        self.body.addWidget(ui.field(i18n.t("Page number"), self.page))
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setMinimumHeight(38)
        self.body.addWidget(ui.field(i18n.t("Access token"), self.token,
                                     i18n.t("From Meta: a token that may manage ads and Pages. It is stored encrypted and not shown again.")))
        self.name = QLineEdit()
        self.name.setPlaceholderText(i18n.t("A name for you, optional"))
        self.name.setMinimumHeight(38)
        self.body.addWidget(ui.field(i18n.t("Name"), self.name))
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.go = self.button(i18n.t("Connect"), "primary", on_click=self._go)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.set_primary(self.go)
        self.resize(520, 560)

    def _go(self):
        self.go.setEnabled(False)
        ui.call(self, "ads/connect", {"ad_account_id": self.acct.text(), "page_id": self.page.text(), "token": self.token.text(), "name": self.name.text()},
                done=lambda r: self.accept(), failed=self._failed)

    def _failed(self, message: str, _detail: dict):
        self.go.setEnabled(True)
        self.error.error(message)


class CopyDialog(PrismDialog):
    """Three ways of writing the ad, from a few facts. Pick one and it fills the ad's words; change it as you like."""

    def __init__(self, goal: str = "", parent=None):
        super().__init__(i18n.t("Write the ad for me"), i18n.t("Tell it about the offer. You get three versions to choose from and change."), icon="sparkles", parent=parent, scrollable=True)
        self.chosen = None
        self.offer = QPlainTextEdit()
        self.offer.setFixedHeight(84)
        self.offer.setAccessibleName(i18n.t("The offer"))
        self.offer.setPlaceholderText(i18n.t("What you sell or offer, and what makes it worth a look. Only facts you want in the ad."))
        self.body.addWidget(ui.field(i18n.t("The offer"), self.offer))
        self.audience = QLineEdit()
        self.audience.setMinimumHeight(38)
        self.audience.setAccessibleName(i18n.t("Who it is for"))
        self.audience.setPlaceholderText(i18n.t("e.g. people building a house in Vadodara"))
        self.body.addWidget(ui.field(i18n.t("Who it is for (optional)"), self.audience))
        self.language = QComboBox()
        self.language.setMinimumHeight(38)
        for lang in ("English", "Hindi", "Gujarati", "Marathi"):
            self.language.addItem(lang, lang)
        self.language.setAccessibleName(i18n.t("Language"))
        self.body.addWidget(ui.field(i18n.t("Language"), self.language))
        self.write_btn = C.button(i18n.t("Write three versions"), "secondary", on_click=self._write)
        row = QHBoxLayout()
        row.addWidget(self.write_btn)
        row.addStretch(1)
        self.body.addLayout(row)
        self.note = ui.note()
        self.body.addWidget(self.note)
        self.results_col = QVBoxLayout()
        self.results_col.setSpacing(theme.SPACE_2)
        self.body.addLayout(self.results_col)
        self.body.addStretch(1)
        self._goal = goal
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.resize(560, 640)

    def _write(self):
        if len(self.offer.toPlainText().strip()) < 8:
            self.note.error(i18n.t("Say a little more about the offer first."))
            return
        self.write_btn.setEnabled(False)
        self.note.set(i18n.t("Writing…"), "quiet")
        ui.call(self, "ads/copy", {"goal": self._goal, "offer": self.offer.toPlainText().strip(), "audience": self.audience.text().strip(), "language": self.language.currentData()},
                done=self._written, failed=lambda m, _d: (self.write_btn.setEnabled(True), self.note.error(m)))

    def _written(self, reply: dict):
        self.write_btn.setEnabled(True)
        self.note.clear_note()
        ui.clear(self.results_col)
        for v in reply.get("variants") or []:
            card = QFrame()
            card.setObjectName("waCopy")
            card.setAttribute(Qt.WA_StyledBackground, True)
            card.setStyleSheet(f"#waCopy {{ background: rgba(255,255,255,0.6); border: 1px solid {theme.HAIRLINE}; border-radius: {theme.R_CONTROL}px; }}")
            col = QVBoxLayout(card)
            col.setContentsMargins(14, 12, 14, 12)
            col.setSpacing(4)
            col.addWidget(C.label(v.get("message", ""), level="SUPPORT", wrap=True))
            if v.get("headline"):
                col.addWidget(C.label(i18n.t("Headline: {h}").format(h=v["headline"]), level="META", colour=theme.NEUTRAL[600]))
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(C.button(i18n.t("Use this one"), "secondary", small=True, on_click=lambda _=False, x=v: self._pick(x)))
            col.addLayout(row)
            self.results_col.addWidget(card)

    def _pick(self, variant: dict):
        self.chosen = variant
        self.accept()


class NewAdDialog(PrismDialog):
    """Make an ad in four steps — what it should do, who sees it, the ad itself, the budget — and it is made paused."""

    def __init__(self, accounts: list, number: str = "", parent=None):
        super().__init__(i18n.t("New ad"), i18n.t("It is made paused — you turn it on yourself."), icon="message", parent=parent)
        self.accounts = accounts
        self._audiences: list = []
        self._estimate_token = 0
        self.steps = C.Tabs([i18n.t("1  What it does"), i18n.t("2  Who sees it"), i18n.t("3  The ad"), i18n.t("4  Budget")], 0)
        self.steps.changed.connect(self._step)
        self.body.addWidget(self.steps)
        self.stack = QStackedWidget()
        self.body.addWidget(self.stack, 1)
        self._build_goal(number)
        self._build_audience()
        self._build_ad()
        self._build_budget()
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.back_btn = self.button(i18n.t("Back"), on_click=lambda: self.steps.set_current(self.steps.current() - 1))
        self.next_btn = self.button(i18n.t("Next"), "secondary", on_click=lambda: self.steps.set_current(self.steps.current() + 1))
        self.go = self.button(i18n.t("Make the ad (paused)"), "primary", on_click=self._go)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.add_secondary(self.back_btn)
        self.footer.add_secondary(self.next_btn)
        self.footer.set_primary(self.go)
        self.resize(660, 760)
        self._kind_changed()
        self._step(0)
        ui.call(self, "audiences/list", {}, done=self._audiences_loaded, failed=lambda m, _d: None)

    # ── the four steps ───────────────────────────────────────────────────────
    def _page(self) -> tuple:
        host = QWidget()
        col = QVBoxLayout(host)
        col.setContentsMargins(0, theme.SPACE_2, 0, 0)
        col.setSpacing(theme.SPACE_3)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        ui.see_through(host)
        scroll.setWidget(host)
        self.stack.addWidget(scroll)
        return host, col

    def _build_goal(self, number: str):
        _host, col = self._page()
        self.account = QComboBox()
        self.account.setMinimumHeight(38)
        self.account.setAccessibleName(i18n.t("Ad account"))
        for a in self.accounts:
            self.account.addItem("%s  ·  %s" % (a.get("name") or i18n.t("Ad account"), a.get("ad_account_id")), a.get("id"))
        col.addWidget(ui.field(i18n.t("Ad account"), self.account))
        self.name = QLineEdit()
        self.name.setPlaceholderText(i18n.t("A name for you, e.g. Diwali site visits"))
        self.name.setMinimumHeight(38)
        self.name.setAccessibleName(i18n.t("Ad name"))
        col.addWidget(ui.field(i18n.t("Ad name"), self.name))
        col.addWidget(C.label(i18n.t("What should the ad do?").upper(), level="LABEL", colour=theme.NEUTRAL[500]))
        self.kind_buttons: dict = {}
        for k, n, hint in kind_choices():
            b = QRadioButton(n)
            b.setToolTip(hint)
            b.setChecked(k == "ctwa")
            b.toggled.connect(lambda on, kk=k: on and self._kind_changed())
            self.kind_buttons[k] = b
            col.addWidget(b)
            col.addWidget(C.label(hint, level="META", colour=theme.NEUTRAL[600], wrap=True))
        # WhatsApp
        self.wa_box = QWidget()
        wl = QVBoxLayout(self.wa_box)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(theme.SPACE_2)
        self.number = QLineEdit(number)
        self.number.setPlaceholderText(i18n.t("With country code, e.g. 919812345678"))
        self.number.setMinimumHeight(38)
        self.number.setAccessibleName(i18n.t("The WhatsApp number it opens"))
        wl.addWidget(ui.field(i18n.t("The WhatsApp number it opens"), self.number))
        self.welcome = QLineEdit()
        self.welcome.setPlaceholderText(i18n.t("What they see when the chat opens, optional"))
        self.welcome.setMinimumHeight(38)
        self.welcome.setAccessibleName(i18n.t("Welcome message"))
        wl.addWidget(ui.field(i18n.t("Welcome message"), self.welcome))
        self.breakers = QPlainTextEdit()
        self.breakers.setPlaceholderText(i18n.t("One quick question per line, up to four — e.g. Get a quote"))
        self.breakers.setFixedHeight(84)
        self.breakers.setAccessibleName(i18n.t("Quick questions"))
        wl.addWidget(ui.field(i18n.t("Quick questions"), self.breakers))
        col.addWidget(self.wa_box)
        # website
        self.web_box = QWidget()
        bl = QVBoxLayout(self.web_box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(theme.SPACE_2)
        self.link = QLineEdit()
        self.link.setPlaceholderText("https://…")
        self.link.setMinimumHeight(38)
        self.link.setAccessibleName(i18n.t("Web address"))
        bl.addWidget(ui.field(i18n.t("The page people land on"), self.link))
        self.pixel = QLineEdit()
        self.pixel.setPlaceholderText(i18n.t("Optional — your Meta Pixel number"))
        self.pixel.setMinimumHeight(38)
        self.pixel.setAccessibleName(i18n.t("Pixel number"))
        bl.addWidget(ui.field(i18n.t("Meta Pixel"), self.pixel, i18n.t("With a pixel on your site, Meta can aim for people who actually load the page.")))
        self.landing = QCheckBox(i18n.t("Aim for people who load the page, not just click"))
        bl.addWidget(self.landing)
        col.addWidget(self.web_box)
        # lead form
        self.lead_box = QWidget()
        ll = QVBoxLayout(self.lead_box)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(theme.SPACE_2)
        ll.addWidget(C.label(i18n.t("What the form asks").upper(), level="LABEL", colour=theme.NEUTRAL[500]))
        self.question_boxes: dict = {}
        for k, label in question_words().items():
            b = QCheckBox(label)
            b.setChecked(k in ("FULL_NAME", "PHONE"))
            self.question_boxes[k] = b
            ll.addWidget(b)
        self.custom_q = QLineEdit()
        self.custom_q.setPlaceholderText(i18n.t("Your own question, optional — e.g. Which city is the project in?"))
        self.custom_q.setMinimumHeight(36)
        self.custom_q.setAccessibleName(i18n.t("Your own question"))
        ll.addWidget(self.custom_q)
        self.privacy = QLineEdit()
        self.privacy.setPlaceholderText("https://…")
        self.privacy.setMinimumHeight(38)
        self.privacy.setAccessibleName(i18n.t("Privacy policy address"))
        ll.addWidget(ui.field(i18n.t("Your privacy policy"), self.privacy, i18n.t("Facebook requires one for a form that collects details.")))
        self.thanks = QLineEdit()
        self.thanks.setPlaceholderText(i18n.t("Optional — a page to show after they send it"))
        self.thanks.setMinimumHeight(38)
        self.thanks.setAccessibleName(i18n.t("Thank-you address"))
        ll.addWidget(ui.field(i18n.t("After they send it"), self.thanks))
        col.addWidget(self.lead_box)
        col.addStretch(1)

    def _build_audience(self):
        _host, col = self._page()
        self.countries = QLineEdit("IN")
        self.countries.setMinimumHeight(38)
        self.countries.setAccessibleName(i18n.t("Countries"))
        col.addWidget(ui.field(i18n.t("Show it in"), self.countries, i18n.t("Two-letter country codes, separated by commas: IN, AE, US. Add cities below to narrow it.")))
        self.places = SearchPicker(self, "geo", i18n.t("Search a city or state, e.g. Vadodara"))
        self.places.changed.connect(self._targeting_changed)
        col.addWidget(ui.field(i18n.t("Or only these places"), self.places))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_4)
        self.age_min = QSpinBox()
        self.age_min.setRange(18, 65)
        self.age_min.setValue(25)
        self.age_min.setMinimumHeight(36)
        self.age_min.setAccessibleName(i18n.t("Youngest"))
        row.addWidget(ui.field(i18n.t("Youngest"), self.age_min))
        self.age_max = QSpinBox()
        self.age_max.setRange(18, 65)
        self.age_max.setValue(60)
        self.age_max.setMinimumHeight(36)
        self.age_max.setAccessibleName(i18n.t("Oldest"))
        row.addWidget(ui.field(i18n.t("Oldest"), self.age_max))
        self.gender = QComboBox()
        self.gender.setMinimumHeight(36)
        self.gender.addItem(i18n.t("Everyone"), None)
        self.gender.addItem(i18n.t("Men"), 1)
        self.gender.addItem(i18n.t("Women"), 2)
        self.gender.setAccessibleName(i18n.t("Who"))
        row.addWidget(ui.field(i18n.t("Who"), self.gender))
        row.addStretch(1)
        col.addLayout(row)
        self.interests = SearchPicker(self, "interests", i18n.t("Search an interest, e.g. interior design"))
        self.interests.changed.connect(self._targeting_changed)
        col.addWidget(ui.field(i18n.t("Interests"), self.interests, i18n.t("People who show an interest in these. Leave it empty for everyone.")))
        self.behaviours = SearchPicker(self, "behaviors", i18n.t("Search a behaviour, e.g. small business owners"))
        self.behaviours.changed.connect(self._targeting_changed)
        col.addWidget(ui.field(i18n.t("Behaviours"), self.behaviours))
        self.lists_col = QVBoxLayout()
        self.lists_col.setSpacing(2)
        self.lists_box = QWidget()
        self.lists_box.setLayout(self.lists_col)
        col.addWidget(ui.field(i18n.t("Your people lists"), self.lists_box, i18n.t("Show it to a list, or tick “keep away” to leave a list out (people who are already customers, say).")))
        self.placements = Placements()
        col.addWidget(ui.field(i18n.t("Where it appears"), self.placements))
        est = QHBoxLayout()
        self.estimate_btn = C.button(i18n.t("How many people is that?"), "secondary", on_click=self.estimate)
        est.addWidget(self.estimate_btn)
        est.addStretch(1)
        col.addLayout(est)
        self.estimate_text = C.label("", level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True)
        col.addWidget(self.estimate_text)
        col.addStretch(1)

    def _build_ad(self):
        _host, col = self._page()
        self.message = QPlainTextEdit()
        self.message.setPlaceholderText(i18n.t("The main text people read in the ad"))
        self.message.setFixedHeight(96)
        self.message.setAccessibleName(i18n.t("Ad text"))
        col.addWidget(ui.field(i18n.t("Ad text"), self.message))
        self.headline = QLineEdit()
        self.headline.setPlaceholderText(i18n.t("A short line, optional"))
        self.headline.setMinimumHeight(38)
        self.headline.setAccessibleName(i18n.t("Headline"))
        col.addWidget(ui.field(i18n.t("Headline"), self.headline))
        self.description = QLineEdit()
        self.description.setPlaceholderText(i18n.t("A few more words under the headline, optional"))
        self.description.setMinimumHeight(38)
        self.description.setAccessibleName(i18n.t("Description"))
        self.description_box = ui.field(i18n.t("Description"), self.description)
        col.addWidget(self.description_box)
        self.cta = QComboBox()
        self.cta.setMinimumHeight(38)
        self.cta.setAccessibleName(i18n.t("Button"))
        self._cta_picked = False                               # only a button the person chose themselves is kept when the kind of ad changes
        self.cta.activated.connect(lambda _i: setattr(self, "_cta_picked", True))
        self.cta_box = ui.field(i18n.t("Button on the ad"), self.cta)
        col.addWidget(self.cta_box)
        self.picture = AssetField(kinds=["image"], empty_text=i18n.t("No picture — choose one from your Media Library"))
        col.addWidget(ui.field(i18n.t("Picture"), self.picture, i18n.t("Square pictures work best (1080 by 1080). It is sent to Meta when you make the ad.")))
        self.write_btn = C.button(i18n.t("Write the ad for me"), "secondary", icon_name="sparkles", on_click=self.write_for_me)
        row = QHBoxLayout()
        row.addWidget(self.write_btn)
        row.addStretch(1)
        col.addLayout(row)
        col.addStretch(1)

    def _build_budget(self):
        _host, col = self._page()
        self.daily_radio = QRadioButton(i18n.t("A most per day"))
        self.total_radio = QRadioButton(i18n.t("A total for the whole run (needs an end date)"))
        self.daily_radio.setChecked(True)
        self.daily_radio.toggled.connect(lambda _on: self._budget_changed())
        col.addWidget(self.daily_radio)
        col.addWidget(self.total_radio)
        self.budget = QDoubleSpinBox()
        self.budget.setRange(MIN_BUDGET_RUPEES, 1_000_000)
        self.budget.setValue(500)
        self.budget.setPrefix("₹ ")
        self.budget.setDecimals(0)
        self.budget.setMinimumHeight(36)
        self.budget.setAccessibleName(i18n.t("Most it may spend a day"))
        self.budget.valueChanged.connect(lambda _v: self._budget_changed())
        self.budget_box = ui.field(i18n.t("Most it may spend a day"), self.budget)
        col.addWidget(self.budget_box)
        self.total = QDoubleSpinBox()
        self.total.setRange(MIN_BUDGET_RUPEES, 10_000_000)
        self.total.setValue(5000)
        self.total.setPrefix("₹ ")
        self.total.setDecimals(0)
        self.total.setMinimumHeight(36)
        self.total.setAccessibleName(i18n.t("Most it may spend in all"))
        self.total.valueChanged.connect(lambda _v: self._budget_changed())
        self.total_box = ui.field(i18n.t("Most it may spend in all"), self.total)
        col.addWidget(self.total_box)
        self.start_now = QCheckBox(i18n.t("Start as soon as it is turned on"))
        self.start_now.setChecked(True)
        self.start_now.toggled.connect(lambda _on: self._budget_changed())
        col.addWidget(self.start_now)
        from PySide6.QtCore import QDateTime
        self.start = QDateTimeEdit(QDateTime.currentDateTime().addDays(1))
        self.start.setCalendarPopup(True)
        self.start.setDisplayFormat("ddd d MMM yyyy  HH:mm")
        self.start.setMinimumHeight(36)
        self.start.setAccessibleName(i18n.t("Start"))
        self.start_box = ui.field(i18n.t("Starts"), self.start)
        col.addWidget(self.start_box)
        self.end_on = QCheckBox(i18n.t("Stop on a date"))
        self.end_on.toggled.connect(lambda _on: self._budget_changed())
        col.addWidget(self.end_on)
        self.end = QDateTimeEdit(QDateTime.currentDateTime().addDays(8))
        self.end.setCalendarPopup(True)
        self.end.setDisplayFormat("ddd d MMM yyyy  HH:mm")
        self.end.setMinimumHeight(36)
        self.end.setAccessibleName(i18n.t("End"))
        self.end_box = ui.field(i18n.t("Stops"), self.end)
        col.addWidget(self.end_box)
        self.summary = C.label("", level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True)
        col.addWidget(self.summary)
        col.addStretch(1)
        self._budget_changed()

    # ── showing the right fields ─────────────────────────────────────────────
    def kind(self) -> str:
        return next((k for k, b in self.kind_buttons.items() if b.isChecked()), "ctwa")

    def _kind_changed(self):
        k = self.kind()
        self.wa_box.setVisible(k == "ctwa")
        self.web_box.setVisible(k == "website")
        self.lead_box.setVisible(k == "leadform")
        self.description_box.setVisible(k != "ctwa")
        self.cta_box.setVisible(k != "ctwa")
        keep = self.cta.currentData() if self._cta_picked else None
        self.cta.clear()
        for key, label in cta_choices(k) if k != "ctwa" else []:
            self.cta.addItem(label, key)
        self.cta.setCurrentIndex(max(self.cta.findData(keep), 0))
        self.welcome.setVisible(k == "ctwa")

    def _step(self, index: int):
        self.stack.setCurrentIndex(index)
        last = index == 3
        self.back_btn.setVisible(index > 0)
        self.next_btn.setVisible(not last)
        self.go.setVisible(last)
        if last:
            self._budget_changed()

    def _budget_changed(self):
        total = self.total_radio.isChecked()
        self.budget_box.setVisible(not total)
        self.total_box.setVisible(total)
        self.start_box.setVisible(not self.start_now.isChecked())
        self.end_box.setVisible(total or self.end_on.isChecked())
        if total:
            self.summary.setText(i18n.t("It will spend up to Rs {n} between the start and the stop date, and no more.").format(n="{:,.0f}".format(self.total.value())))
        else:
            per = self.budget.value()
            self.summary.setText(i18n.t("It will spend up to Rs {d} a day — at most about Rs {m} in a 30-day month.").format(d="{:,.0f}".format(per), m="{:,.0f}".format(per * 30.4)))

    def account_id(self):
        return self.account.currentData()

    def _audiences_loaded(self, reply: dict):
        self._audiences = list(reply.get("audiences") or [])
        ui.clear(self.lists_col)
        self.show_boxes, self.hide_boxes = {}, {}
        if not self._audiences:
            self.lists_col.addWidget(C.label(i18n.t("You have no lists yet. Make one in the Audiences section."), level="META", colour=theme.NEUTRAL[600]))
        for a in self._audiences:
            row = QHBoxLayout()
            show = QCheckBox(a.get("name") or "")
            show.toggled.connect(lambda _on: self._targeting_changed())
            hide = QCheckBox(i18n.t("keep away"))
            hide.toggled.connect(lambda _on: self._targeting_changed())
            self.show_boxes[a["meta_id"]], self.hide_boxes[a["meta_id"]] = show, hide
            row.addWidget(show, 1)
            row.addWidget(hide)
            box = QWidget()
            box.setLayout(row)
            self.lists_col.addWidget(box)

    # ── what is sent ─────────────────────────────────────────────────────────
    def targeting(self) -> dict:
        countries = [c.strip().upper() for c in self.countries.text().split(",") if c.strip()]
        places = self.places.items()
        geo: dict = {}
        if places:                                           # chosen places replace the whole-country default
            for kind, key in (("city", "cities"), ("region", "regions")):
                found = [{"key": p["key"]} for p in places if p.get("type") == kind]
                if found:
                    geo[key] = found
            picked_countries = [p["key"] for p in places if p.get("type") == "country"]
            if picked_countries:
                geo["countries"] = picked_countries
        else:
            geo["countries"] = countries
        t = {"geo_locations": geo, "age_min": self.age_min.value(), "age_max": self.age_max.value()}
        if self.gender.currentData():
            t["genders"] = [self.gender.currentData()]
        if self.interests.items():
            t["interests"] = [{"id": x["id"], "name": x.get("name", "")} for x in self.interests.items()]
        if self.behaviours.items():
            t["behaviors"] = [{"id": x["id"], "name": x.get("name", "")} for x in self.behaviours.items()]
        shown = [m for m, b in getattr(self, "show_boxes", {}).items() if b.isChecked()]
        hidden = [m for m, b in getattr(self, "hide_boxes", {}).items() if b.isChecked()]
        if shown:
            t["custom_audiences"] = [{"id": m} for m in shown]
        if hidden:
            t["excluded_custom_audiences"] = [{"id": m} for m in hidden]
        t.update(self.placements.value())
        return t

    def _targeting_changed(self):
        self.estimate_text.setText("")

    def estimate(self):
        if not self.account_id():
            self.estimate_text.setText(i18n.t("Connect an ad account first."))
            return
        self.estimate_btn.setEnabled(False)
        self.estimate_text.setText(i18n.t("Asking Meta…"))
        ui.call(self, "ads/estimate", {"account_id": self.account_id(), "targeting": self.targeting(), "kind": self.kind()},
                done=self._estimated, failed=lambda m, _d: (self.estimate_btn.setEnabled(True), self.estimate_text.setText(m)))

    def _estimated(self, reply: dict):
        self.estimate_btn.setEnabled(True)
        e = reply.get("estimate") or {}
        if not e.get("ready", True) or e.get("daily_low") is None:
            self.estimate_text.setText(i18n.t("Meta cannot say yet for this audience."))
            return
        self.estimate_text.setText(i18n.t("About {d} people a day, {lo} to {hi} a month.").format(d="{:,}".format(int(e["daily_low"])), lo="{:,}".format(int(e.get("monthly_low") or 0)),
                                                                                                 hi="{:,}".format(int(e.get("monthly_high") or 0))))

    def write_for_me(self):
        dlg = CopyDialog(kind_name(self.kind()), self)
        if dlg.exec() and dlg.chosen:
            self.message.setPlainText(dlg.chosen.get("message", ""))
            self.headline.setText(dlg.chosen.get("headline", ""))
            self.description.setText(dlg.chosen.get("description", ""))

    def _times(self) -> dict:
        out = {}
        if self.total_radio.isChecked() or self.end_on.isChecked():
            out["end_time"] = self.end.dateTime().toString("yyyy-MM-ddTHH:mm:ss") + "+0530"
        if not self.start_now.isChecked():
            out["start_time"] = self.start.dateTime().toString("yyyy-MM-ddTHH:mm:ss") + "+0530"
        return out

    def payload(self) -> dict:
        k = self.kind()
        data = {"kind": k, "account_id": self.account.currentData(), "name": self.name.text().strip(), "targeting": self.targeting(),
                "message": self.message.toPlainText().strip(), "headline": self.headline.text().strip(), **self._times()}
        if self.total_radio.isChecked():
            data["lifetime_budget"] = rupees_to_paise(self.total.value())
        else:
            data["daily_budget"] = rupees_to_paise(self.budget.value())
        if k == "ctwa":
            data.update(whatsapp_number=self.number.text().strip(), welcome_text=self.welcome.text().strip(),
                        ice_breakers=[b.strip() for b in self.breakers.toPlainText().splitlines() if b.strip()][:4])
        elif k == "website":
            data.update(link=self.link.text().strip(), cta=self.cta.currentData() or "LEARN_MORE", description=self.description.text().strip())
            if self.pixel.text().strip():
                data["pixel_id"] = self.pixel.text().strip()
                if self.landing.isChecked():
                    data["optimize_for"] = "landing_page_views"
        else:
            questions = [{"type": q} for q, b in self.question_boxes.items() if b.isChecked()]
            if self.custom_q.text().strip():
                questions.append({"type": "CUSTOM", "label": self.custom_q.text().strip()})
            data.update(cta=self.cta.currentData() or "SIGN_UP", description=self.description.text().strip(),
                        form={"questions": questions, "privacy_url": self.privacy.text().strip(), "thank_you_url": self.thanks.text().strip()})
        return data

    def _go(self):
        if not self.account.currentData():
            self.error.error(i18n.t("Connect an ad account first."))
            return
        self.go.setEnabled(False)
        self.error.clear_note()
        if self.picture.asset_id():
            ui.call(self, "ads/upload_image", {"account_id": self.account_id(), "asset_id": self.picture.asset_id()}, done=lambda r: self._create(r.get("hash")),
                    failed=self._failed)
        else:
            self._create(None)

    def _create(self, image_hash):
        data = self.payload()
        if image_hash:
            data["image_hash"] = image_hash
        ui.call(self, "ads/create", data, done=lambda r: self.accept(), failed=self._failed)

    def _failed(self, message: str, _detail: dict):
        self.go.setEnabled(True)
        self.error.error(message)


class InsightsDialog(AdResultsDialog):
    """Kept under its old name: the numbers for one ad."""


class _AdRow(QFrame):
    def __init__(self, ad: dict, page: "AdsPage"):
        super().__init__()
        self.ad, self.page = ad, page
        self.setObjectName("waAd")
        self.setAttribute(Qt.WA_StyledBackground, True)
        words, tone, state = state_words(ad)
        line = theme.ERR_LINE if state == "rejected" else theme.HAIRLINE
        self.setStyleSheet(f"#waAd {{ background: rgba(255,255,255,0.55); border: 1px solid {line}; border-radius: {theme.R_CONTROL}px; }}")
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 12, 14, 10)
        col.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(theme.SPACE_2)
        top.addWidget(C.label(ad.get("name") or "", level="SUPPORT", weight=700), stretch=1)
        top.addWidget(C.Pill(kind_name(ad.get("kind") or "ctwa"), "neutral"))
        self.pill = C.Pill(words, tone)
        top.addWidget(self.pill)
        col.addLayout(top)
        facts = [budget_words(ad.get("budget"))]
        when = short_time(ad.get("created_at") or "")
        if when:
            facts.append(i18n.t("Made {t}").format(t=when))
        col.addWidget(C.label("  ·  ".join(f for f in facts if f), level="META", colour=theme.NEUTRAL[600]))
        reasons = ((ad.get("review") or {}).get("reasons")) or []
        for r in reasons[:3]:
            col.addWidget(C.label("•  " + str(r), level="META", colour=theme.ERR_INK, wrap=True))
        if ad.get("last_error"):
            col.addWidget(C.label(str(ad["last_error"]), level="META", colour=theme.ERR_INK, wrap=True))
        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACE_1)
        actions.addStretch(1)
        actions.addWidget(C.button(i18n.t("Results"), "tertiary", on_click=lambda: page.insights(ad)))
        if str(ad.get("status") or "").upper() in ("ACTIVE", "PAUSED"):
            actions.addWidget(C.button(i18n.t("Check with Meta"), "tertiary", on_click=lambda: page.check_status(ad)))
        status = str(ad.get("status") or "").upper()
        if status == "PAUSED":
            actions.addWidget(C.button(i18n.t("Turn on…"), "secondary", on_click=lambda: page.activate_ad(ad)))
        elif status == "ACTIVE":
            actions.addWidget(C.button(i18n.t("Pause"), "secondary", on_click=lambda: page.pause_ad(ad)))
        col.addLayout(actions)


class AdsPage(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self._accounts: list = []
        self._number = ""
        self._loaded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SPACE_4, theme.SPACE_4, theme.SPACE_4, theme.SPACE_4)
        root.setSpacing(theme.SPACE_3)
        head = QHBoxLayout()
        head.setSpacing(theme.SPACE_2)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(C.label(i18n.t("Ads"), level="CARD_TITLE"))
        titles.addWidget(C.label(i18n.t("Ads on Facebook and Instagram that open a WhatsApp chat, take people to your website, or collect their details. Every ad is made "
                                        "paused — nothing is spent until you turn it on."), level="SUPPORT", colour=theme.NEUTRAL[600], wrap=True))
        head.addLayout(titles, stretch=1)
        self.connect_btn = C.button(i18n.t("Connect ad account"), "secondary", on_click=self._connect_menu)
        head.addWidget(self.connect_btn)
        self.new_btn = C.button(i18n.t("New ad"), "primary", icon_name="plus", on_click=self._new)
        head.addWidget(self.new_btn)
        root.addLayout(head)
        self.note = ui.note()
        root.addWidget(self.note)
        self.chips = C.FilterChips([("ads", i18n.t("Ads")), ("audiences", i18n.t("Audiences")), ("suggestions", i18n.t("Suggestions"))], "ads")
        self.chips.setMinimumWidth(330)
        self.chips.changed.connect(self.show_section)
        root.addWidget(self.chips)

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
        self.stack.addWidget(scroll)
        self.state = C.EmptyState("globe", i18n.t("Loading…"), "", i18n.t("Try again"))
        self.state.clicked.connect(self._state_action)
        self.stack.addWidget(self.state)
        self.audiences = AudiencesView(self)
        self.suggestions = SuggestionsView(self)
        for w in (self.audiences, self.suggestions):
            holder = QScrollArea()
            holder.setWidgetResizable(True)
            holder.setFrameShape(QFrame.NoFrame)
            holder.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            holder.viewport().setAutoFillBackground(False)
            inner = QWidget()
            ui.see_through(inner)
            lay = QVBoxLayout(inner)
            lay.setContentsMargins(0, 0, theme.SPACE_2, 0)
            lay.addWidget(w)
            holder.setWidget(inner)
            self.stack.addWidget(holder)
        root.addWidget(self.stack, stretch=1)
        self._state_kind = "loading"
        self._section = "ads"
        self._show_state("loading")

    def say(self, text: str, error: bool = False):
        self.note.set(text, "error" if error else "ok")

    # ── lifecycle ────────────────────────────────────────────────────────────
    def activate(self):
        ui.call(self, "numbers/list", done=lambda r: setattr(self, "_number", re.sub(r"\D", "", str(((r.get("numbers") or [{}])[0]).get("display") or ""))),
                failed=lambda m, _d: None)
        ui.call(self, "ads/accounts", done=self._accounts_loaded, failed=self._load_failed)

    activate_ads = activate

    def deactivate(self):
        pass

    def account_id(self):
        return self._accounts[0]["id"] if self._accounts else None

    def _load_failed(self, message: str, _detail: dict):
        if not self._loaded:
            self._show_state("failed", message)
        else:
            self.say(message, error=True)

    def _accounts_loaded(self, reply: dict):
        self._accounts = list(reply.get("accounts") or [])
        ui.call(self, "ads/list", done=self._ads, failed=self._load_failed)

    def _ads(self, reply: dict):
        self._loaded = True
        self.new_btn.setEnabled(bool(self._accounts))
        ads = list(reply.get("ads") or [])
        ui.clear(self.list_col)
        if not self._accounts:
            self._show_state("no_account")
            return
        if not ads:
            self._show_state("no_ads")
            return
        for ad in ads:
            self.list_col.addWidget(_AdRow(ad, self))
        self.list_col.addStretch(1)
        if self._section == "ads":
            self.stack.setCurrentIndex(0)

    def show_section(self, key: str):
        self._section = key
        self.chips.set_current(key)
        if key == "ads":
            self.stack.setCurrentIndex(0 if self._accounts and self.list_col.count() else 1)
        elif key == "audiences":
            self.stack.setCurrentIndex(2)
            self.audiences.load()
        else:
            self.stack.setCurrentIndex(3)
            self.suggestions.load()

    def suggestion_count(self, n: int):
        button = self.chips._buttons.get("suggestions")
        if button is not None:
            button.setText(i18n.t("Suggestions ({n})").format(n=n) if n else i18n.t("Suggestions"))

    def _show_state(self, kind: str, message: str = ""):
        title, body, action = {
            "loading": (i18n.t("Loading…"), "", None),
            "failed": (i18n.t("Couldn't load your ads"), message, i18n.t("Try again")),
            "no_account": (i18n.t("Connect your ad account"), i18n.t("Ads are made in your own Meta ad account. Connect it once, then make your first ad."),
                           i18n.t("Connect ad account")),
            "no_ads": (i18n.t("No ads yet"), i18n.t("Make your first ad. It is created paused."), i18n.t("New ad")),
        }[kind]
        self.state.set_text(title, body)
        if self.state.action is not None:
            self.state.action.setText(action or "")
            self.state.action.setVisible(bool(action))
        self._state_kind = kind
        if self._section == "ads":
            self.stack.setCurrentIndex(1)

    def _state_action(self):
        {"failed": self.activate, "no_account": self._connect_menu, "no_ads": self._new}.get(self._state_kind, lambda: None)()

    # ── actions ──────────────────────────────────────────────────────────────
    def _connect_menu(self):
        menu = QMenu(self)
        menu.addAction(i18n.t("Continue with Facebook")).triggered.connect(self.connect_facebook)
        menu.addAction(i18n.t("Paste an access token")).triggered.connect(self._connect)
        self._pop_up(menu)

    def _pop_up(self, menu):
        """Show a menu under the Connect button. A method of its own so a test can read the menu without opening it."""
        menu.exec(self.connect_btn.mapToGlobal(self.connect_btn.rect().bottomLeft()))

    def connect_facebook(self):
        dlg = FacebookConnectDialog(self)
        dlg.paste_instead.connect(self._connect)
        if dlg.exec():
            self.say(i18n.t("Connected."))
            self.activate()

    def _connect(self):
        if ConnectAccountDialog(self).exec():
            self.say(i18n.t("Connected."))
            self.activate()

    def _new(self):
        if not self._accounts:
            self._connect_menu()
            return
        if NewAdDialog(self._accounts, self._number, self).exec():
            self.say(i18n.t("The ad was made and is paused. Look at it in Meta's Ads Manager, then turn it on here."))
            self.activate()

    def insights(self, ad: dict):
        AdResultsDialog(ad, self).exec()

    def check_status(self, ad: dict):
        ui.call(self, "ads/status", {"ad_id": ad["id"]}, done=lambda r: (self.say(i18n.t("Meta says: {w}.").format(w=r.get("words"))
                                                                                 + ((" " + "; ".join(r["reasons"])) if r.get("reasons") else "")), self.activate()),
                failed=lambda m, _d: self.say(m, error=True))

    def activate_ad(self, ad: dict):
        if not ui.confirm(self, i18n.t("Turn on this ad?"),
                          i18n.t("“{n}” will start running and Meta will start spending from your ad account, up to the daily limit you set. "
                                 "You can pause it at any time.").format(n=ad.get("name"))):
            return
        ui.call(self, "ads/activate", {"ad_id": ad["id"], "confirm": True}, done=lambda r: (self.say(i18n.t("It is running.")), self.activate()))

    def pause_ad(self, ad: dict):
        ui.call(self, "ads/pause", {"ad_id": ad["id"]}, done=lambda r: (self.say(i18n.t("Paused.")), self.activate()))
