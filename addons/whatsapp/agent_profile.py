"""An AI agent's business, voice and behaviour — the first three things the owner tells it.

    The business   its name, website, description, the hello it opens with and the rules it must never break; "Fill from my website" drafts them from the site
    Voice          the tone and length of an answer and the language
    Behaviour      when to hand over, how many replies a chat gets, whether it only covers the closed hours, and whether it answers chats no flow takes

Everything edits the editor's DRAFT (the agent customers meet changes only when it is published), except "answer chats that no flow takes", which is how the whole
workspace is wired and takes effect at once.
"""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QSpinBox, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from widgets import controls as C

TONES = ("friendly", "professional", "casual", "formal", "enthusiastic", "empathetic")
LENGTHS = ("short", "medium", "detailed")
LANGUAGES = ("match", "english", "hindi", "gujarati", "marathi", "tamil", "telugu", "bengali", "kannada", "malayalam", "punjabi", "urdu")


def tone_choices() -> list:
    return [("friendly", i18n.t("Friendly")), ("professional", i18n.t("Professional")), ("casual", i18n.t("Casual")), ("formal", i18n.t("Formal")),
            ("enthusiastic", i18n.t("Enthusiastic")), ("empathetic", i18n.t("Empathetic"))]


def length_choices() -> list:
    return [("short", i18n.t("Short — one or two sentences")), ("medium", i18n.t("Medium — three or four sentences")), ("detailed", i18n.t("Detailed — a full answer"))]


def language_choices() -> list:
    return [("match", i18n.t("Whatever the customer writes in")), ("english", i18n.t("English")), ("hindi", i18n.t("Hindi")), ("gujarati", i18n.t("Gujarati")),
            ("marathi", i18n.t("Marathi")), ("tamil", i18n.t("Tamil")), ("telugu", i18n.t("Telugu")), ("bengali", i18n.t("Bengali")), ("kannada", i18n.t("Kannada")),
            ("malayalam", i18n.t("Malayalam")), ("punjabi", i18n.t("Punjabi")), ("urdu", i18n.t("Urdu"))]


class ProfileSection(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        draft = editor.draft
        profile, voice = draft["profile"], draft["voice"]
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_4)

        card, bc = ui.card(i18n.t("The business"), i18n.t("What the agent says about you. Keep it true: it will repeat this to your customers."))
        self.business = QLineEdit(profile.get("business_name") or "")
        self.business.setMinimumHeight(38)
        self.business.setMaxLength(80)
        self.business.setAccessibleName(i18n.t("Business name"))
        self.business.textChanged.connect(lambda t: self._set("profile", "business_name", t.strip()))
        bc.addWidget(ui.field(i18n.t("Business name"), self.business))
        site = QHBoxLayout()
        site.setSpacing(theme.SPACE_2)
        self.website = QLineEdit(profile.get("website") or "")
        self.website.setMinimumHeight(38)
        self.website.setPlaceholderText("https://…")
        self.website.setAccessibleName(i18n.t("Website"))
        self.website.textChanged.connect(lambda t: self._set("profile", "website", t.strip()))
        site.addWidget(self.website, 1)
        self.draft_btn = C.button(i18n.t("Fill from my website"), "secondary", icon_name="sparkles", on_click=self.fill_from_website)
        site.addWidget(self.draft_btn)
        bc.addWidget(ui.field(i18n.t("Website"), site, i18n.t("Prism reads the page and drafts the rest of this card for you. You read it and change it before it is saved.")))
        self.description = QPlainTextEdit(profile.get("description") or "")
        self.description.setFixedHeight(96)
        self.description.setPlaceholderText(i18n.t("What you do, for whom, where, and how a customer starts."))
        self.description.setAccessibleName(i18n.t("About the business"))
        self.description.textChanged.connect(lambda: self._set("profile", "description", self.description.toPlainText().strip()))
        bc.addWidget(ui.field(i18n.t("About the business"), self.description))
        self.greeting = QLineEdit(profile.get("greeting") or "")
        self.greeting.setMinimumHeight(38)
        self.greeting.setMaxLength(300)
        self.greeting.setPlaceholderText(i18n.t("Namaste! Welcome to Patel Constructions. How can we help?"))
        self.greeting.setAccessibleName(i18n.t("Greeting"))
        self.greeting.textChanged.connect(lambda t: self._set("profile", "greeting", t.strip()))
        bc.addWidget(ui.field(i18n.t("Its first hello"), self.greeting, i18n.t("Used when a new customer just says hello.")))
        self.rules = QPlainTextEdit("\n".join(profile.get("ground_rules") or []))
        self.rules.setFixedHeight(84)
        self.rules.setPlaceholderText(i18n.t("One rule per line, e.g. Never promise a date or a discount."))
        self.rules.setAccessibleName(i18n.t("Ground rules"))
        self.rules.textChanged.connect(self._rules_changed)
        bc.addWidget(ui.field(i18n.t("Ground rules"), self.rules, i18n.t("Things it must never do or say. Up to 10, one per line.")))
        self.instructions = QPlainTextEdit(draft.get("instructions") or "")
        self.instructions.setPlaceholderText(i18n.t("Anything else it should know about how to behave. E.g. We do not do plumbing."))
        self.instructions.setFixedHeight(96)
        self.instructions.setAccessibleName(i18n.t("Instructions"))
        self.instructions.textChanged.connect(lambda: self._set(None, "instructions", self.instructions.toPlainText()))
        bc.addWidget(ui.field(i18n.t("Other instructions"), self.instructions, i18n.t("Up to 4000 characters. It always answers only from this and what you teach it.")))
        self.profile_note = ui.note()
        bc.addWidget(self.profile_note)
        col.addWidget(card)

        card, vc = ui.card(i18n.t("Voice"), i18n.t("How it sounds. The same words come out warmer or crisper."))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_4)
        self.tone = QComboBox()
        self.tone.setMinimumHeight(38)
        for k, label in tone_choices():
            self.tone.addItem(label, k)
        self.tone.setCurrentIndex(max(self.tone.findData(voice.get("tone") or "friendly"), 0))
        self.tone.setAccessibleName(i18n.t("Tone"))
        self.tone.activated.connect(lambda _i: self._set("voice", "tone", self.tone.currentData()))
        row.addWidget(ui.field(i18n.t("Tone"), self.tone), 1)
        self.length = QComboBox()
        self.length.setMinimumHeight(38)
        for k, label in length_choices():
            self.length.addItem(label, k)
        self.length.setCurrentIndex(max(self.length.findData(voice.get("length") or "short"), 0))
        self.length.setAccessibleName(i18n.t("Answer length"))
        self.length.activated.connect(lambda _i: self._set("voice", "length", self.length.currentData()))
        row.addWidget(ui.field(i18n.t("Answer length"), self.length), 1)
        vc.addLayout(row)
        self.language = QComboBox()
        self.language.setMinimumHeight(38)
        for k, label in language_choices():
            self.language.addItem(label, k)
        self.language.setCurrentIndex(max(self.language.findData(voice.get("language") or "match"), 0))
        self.language.setAccessibleName(i18n.t("Language"))
        self.language.activated.connect(lambda _i: self._set("voice", "language", self.language.currentData()))
        vc.addWidget(ui.field(i18n.t("Language it answers in"), self.language))
        col.addWidget(card)

        card, hc = ui.card(i18n.t("Behaviour"))
        self.default = QCheckBox(i18n.t("Answer chats that no flow takes"))
        self.default.setChecked(bool(editor.agent.get("is_default")))
        self.default.toggled.connect(editor.set_default)
        hc.addWidget(self.default)
        self.words = QLineEdit(", ".join(draft.get("handoff_words") or []))
        self.words.setMinimumHeight(36)
        self.words.setAccessibleName(i18n.t("Hand-over words"))
        self.words.textChanged.connect(lambda t: self._set(None, "handoff_words", [w.strip() for w in t.split(",") if w.strip()]))
        hc.addWidget(ui.field(i18n.t("Hand over when the customer says"), self.words, i18n.t("Words that mean they want a person, separated by commas.")))
        mrow = QHBoxLayout()
        mrow.setSpacing(theme.SPACE_4)
        self.max = QSpinBox()
        self.max.setRange(1, 100)
        self.max.setValue(int(draft.get("max_replies") or 12))
        self.max.setMinimumHeight(36)
        self.max.valueChanged.connect(lambda v: self._set(None, "max_replies", v))
        mrow.addWidget(ui.field(i18n.t("Replies in one chat before asking your team"), self.max))
        mrow.addStretch(1)
        hc.addLayout(mrow)
        self.closed_only = QCheckBox(i18n.t("Only answer when we are closed"))
        self.closed_only.setChecked(bool(draft.get("business_hours_only")))
        self.closed_only.toggled.connect(lambda on: self._set(None, "business_hours_only", bool(on)))
        hc.addWidget(self.closed_only)
        col.addWidget(card)
        col.addStretch(1)

    def _set(self, group, key, value):
        if group:
            self.editor.draft[group][key] = value
        else:
            self.editor.draft[key] = value
        self.editor.edited()

    def _rules_changed(self):
        self._set("profile", "ground_rules", [ln.strip() for ln in self.rules.toPlainText().splitlines() if ln.strip()][:10])

    # ── drafting the business from its website ───────────────────────────────
    def fill_from_website(self):
        url = self.website.text().strip()
        if not url.startswith("https://"):
            self.profile_note.error(i18n.t("Write your website address first, starting with https://"))
            return
        self.draft_btn.setEnabled(False)
        self.profile_note.set(i18n.t("Reading your website…"), "quiet")
        ui.call(self.editor, "ai/agents/draft_profile", {"url": url}, done=self._drafted, failed=lambda m, _d: self._draft_failed(m))

    def _draft_failed(self, message: str):
        self.draft_btn.setEnabled(True)
        self.profile_note.error(message)

    def _drafted(self, reply: dict):
        self.draft_btn.setEnabled(True)
        p = reply.get("profile") or {}
        self.business.setText(p.get("business_name") or self.business.text())
        self.description.setPlainText(p.get("description") or self.description.toPlainText())
        self.greeting.setText(p.get("greeting") or self.greeting.text())
        if p.get("ground_rules"):
            self.rules.setPlainText("\n".join(p["ground_rules"]))
        self.profile_note.ok(i18n.t("Drafted from your website. Read it, change what is not right, and it saves itself."))
