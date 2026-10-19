"""Settings → Tags and attributes, and Opt-in and opt-out words.

Tags are labels you put on people; attributes are details you keep about them (a city, a budget). Both are what a campaign
or a filter aims at, so this is where they are made, renamed and removed. An attribute can also be workspace-wide: one value
for everyone (your company name), usable wherever a per-person detail is.

The opt-in and opt-out words are what a customer may type to stop or start hearing from you. WhatsApp restricts accounts
people report, so the words and the confirmation reply are yours to set, within reason.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QInputDialog, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.settings import _COLUMN, _scrolled
from widgets import controls as C


def _type_names() -> list:
    return [("string", i18n.t("Text")), ("number", i18n.t("Number")), ("date", i18n.t("Date")), ("bool", i18n.t("Yes or no")), ("enum", i18n.t("One of a list"))]


class TagsAttributesSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)

        card, cc = ui.card(i18n.t("Tags"), i18n.t("Labels you put on people, like vip or builder. A campaign can aim at a tag, and a filter can narrow by one."), width=_COLUMN)
        self.tags_col = QVBoxLayout()
        self.tags_col.setSpacing(theme.SPACE_2)
        cc.addLayout(self.tags_col)
        row = QHBoxLayout()
        self.new_tag = QLineEdit()
        self.new_tag.setPlaceholderText(i18n.t("A new tag"))
        self.new_tag.setMinimumHeight(38)
        self.new_tag.returnPressed.connect(self._add_tag)
        row.addWidget(self.new_tag, stretch=1)
        row.addWidget(C.button(i18n.t("Add tag"), "primary", on_click=self._add_tag))
        cc.addLayout(row)
        self.tag_note = ui.note()
        cc.addWidget(self.tag_note)
        col.addWidget(card)

        card, ac = ui.card(i18n.t("Attributes"), i18n.t("Details you keep about a person. They can fill a message's blanks and narrow a filter."), width=_COLUMN)
        self.attrs_col = QVBoxLayout()
        self.attrs_col.setSpacing(theme.SPACE_2)
        ac.addLayout(self.attrs_col)
        form = QHBoxLayout()
        self.attr_key = QLineEdit()
        self.attr_key.setPlaceholderText(i18n.t("A name, like City"))
        self.attr_key.setMinimumHeight(38)
        form.addWidget(self.attr_key, stretch=1)
        self.attr_type = QComboBox()
        self.attr_type.setMinimumHeight(38)
        for v, label in _type_names():
            self.attr_type.addItem(label, v)
        form.addWidget(self.attr_type)
        ac.addLayout(form)
        self.attr_options = QLineEdit()
        self.attr_options.setPlaceholderText(i18n.t("The choices, separated by commas"))
        self.attr_options.setMinimumHeight(38)
        self.attr_options.hide()
        self.attr_type.currentIndexChanged.connect(lambda _i: self.attr_options.setVisible(self.attr_type.currentData() == "enum"))
        ac.addWidget(self.attr_options)
        self.attr_global = QCheckBox(i18n.t("One value for the whole workspace (like your company name)"))
        ac.addWidget(self.attr_global)
        ac.addWidget(C.button(i18n.t("Add attribute"), "primary", on_click=self._add_attr), alignment=Qt.AlignLeft)
        self.attr_note = ui.note()
        ac.addWidget(self.attr_note)
        col.addWidget(card)
        col.addStretch(1)

    def say(self, message: str, error: bool = False):
        (self.attr_note.error if error else self.attr_note.ok)(message)

    def activate(self):
        self._load()

    def deactivate(self):
        pass

    def _load(self):
        ui.call(self, "tags/list", {}, done=self._tags, failed=lambda m, _d: self.tag_note.error(m))
        ui.call(self, "attributes/list", {}, done=self._attrs, failed=lambda m, _d: self.attr_note.error(m))

    # ── tags ─────────────────────────────────────────────────────────────────
    def _tags(self, reply: dict):
        ui.clear(self.tags_col)
        items = reply.get("tags") or []
        if not items:
            self.tags_col.addWidget(C.label(i18n.t("No tags yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        for t in items:
            row = QHBoxLayout()
            row.addWidget(C.label(t["name"], level="SUPPORT", weight=700), stretch=1)
            n = int(t.get("contacts") or 0)
            row.addWidget(C.label(i18n.t("{n} people").format(n=n) if n != 1 else i18n.t("1 person"), level="META", colour=theme.NEUTRAL[600]))
            row.addWidget(C.button(i18n.t("Rename"), "tertiary", small=True, on_click=lambda _=False, x=t: self._rename(x)))
            row.addWidget(C.button(i18n.t("Delete"), "tertiary", small=True, on_click=lambda _=False, x=t: self._delete_tag(x)))
            holder = QWidget()
            holder.setLayout(row)
            self.tags_col.addWidget(holder)

    def _add_tag(self):
        name = self.new_tag.text().strip()
        if not name:
            return
        ui.call(self, "tags/create", {"name": name}, done=lambda _r: (self.new_tag.clear(), self.tag_note.ok(i18n.t("Added.")), self._load()),
                failed=lambda m, _d: self.tag_note.error(m))

    def _rename(self, tag: dict):
        new, ok = QInputDialog.getText(self, i18n.t("Rename tag"), i18n.t("New name for “{t}”:").format(t=tag["name"]), text=tag["name"])
        new = (new or "").strip()
        if ok and new and new != tag["name"]:
            ui.call(self, "tags/rename", {"old": tag["name"], "new": new}, done=lambda _r: (self.tag_note.ok(i18n.t("Renamed.")), self._load()),
                    failed=lambda m, _d: self.tag_note.error(m))

    def _delete_tag(self, tag: dict):
        n = int(tag.get("contacts") or 0)
        if not ui.confirm(self, i18n.t("Delete tag"), i18n.t("Delete “{t}”? It is taken off {n} people. They are not deleted.").format(t=tag["name"], n=n)):
            return
        ui.call(self, "tags/delete", {"name": tag["name"]}, done=lambda _r: (self.tag_note.ok(i18n.t("Deleted.")), self._load()),
                failed=lambda m, _d: self.tag_note.error(m))

    # ── attributes ───────────────────────────────────────────────────────────
    def _attrs(self, reply: dict):
        ui.clear(self.attrs_col)
        items = reply.get("attributes") or []
        if not items:
            self.attrs_col.addWidget(C.label(i18n.t("No attributes yet."), level="SUPPORT", colour=theme.NEUTRAL[600]))
        kinds = dict(_type_names())
        for a in items:
            row = QHBoxLayout()
            text = QVBoxLayout()
            text.setSpacing(0)
            text.addWidget(C.label(a["key"], level="SUPPORT", weight=700))
            sub = kinds.get(a.get("type"), "")
            if a.get("global"):
                sub += " · " + i18n.t("whole workspace") + (": %s" % a["value"] if a.get("value") not in (None, "") else "")
            else:
                n = int(a.get("filled") or 0)
                sub += " · " + (i18n.t("{n} people have it").format(n=n) if n != 1 else i18n.t("1 person has it"))
            text.addWidget(C.label(sub, level="META", colour=theme.NEUTRAL[600]))
            row.addLayout(text, stretch=1)
            if a.get("global"):
                row.addWidget(C.button(i18n.t("Set value"), "secondary", small=True, on_click=lambda _=False, x=a: self._set_global(x)))
            row.addWidget(C.button(i18n.t("Delete"), "tertiary", small=True, on_click=lambda _=False, x=a: self._delete_attr(x)))
            holder = QWidget()
            holder.setLayout(row)
            self.attrs_col.addWidget(holder)

    def _add_attr(self):
        key = self.attr_key.text().strip()
        if not key:
            return
        options = [o.strip() for o in self.attr_options.text().split(",") if o.strip()] if self.attr_type.currentData() == "enum" else None
        ui.call(self, "attributes/define", {"key": key, "type": self.attr_type.currentData(), "global": self.attr_global.isChecked(), "options": options},
                done=lambda _r: (self.attr_key.clear(), self.attr_options.clear(), self.attr_global.setChecked(False), self.attr_note.ok(i18n.t("Added.")), self._load()),
                failed=lambda m, _d: self.attr_note.error(m))

    def _set_global(self, attr: dict):
        text, ok = QInputDialog.getText(self, i18n.t("Workspace-wide value"), i18n.t("The value of {k} for everyone:").format(k=attr["key"]),
                                        text="" if attr.get("value") is None else str(attr["value"]))
        if ok and text.strip():
            ui.call(self, "attributes/set_global", {"key": attr["key"], "value": text.strip()},
                    done=lambda _r: (self.attr_note.ok(i18n.t("Saved.")), self._load()), failed=lambda m, _d: self.attr_note.error(m))

    def _delete_attr(self, attr: dict):
        if not ui.confirm(self, i18n.t("Delete attribute"), i18n.t("Delete {k}? Its value is removed from everyone who has one.").format(k=attr["key"])):
            return
        ui.call(self, "attributes/delete", {"key": attr["key"]}, done=lambda _r: (self.attr_note.ok(i18n.t("Deleted.")), self._load()),
                failed=lambda m, _d: self.attr_note.error(m))


class ComplianceSection(QWidget):
    """The words a customer may send to stop or start hearing from you, and what you reply."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)
        card, cc = ui.card(i18n.t("Opt-in and opt-out words"),
                           i18n.t("When someone sends one of these words, Prism records it and stops or starts your messages to them. "
                                  "At most five of each, separated by commas."), width=_COLUMN)
        self.out_words = QLineEdit()
        self.out_words.setMinimumHeight(38)
        cc.addWidget(ui.field(i18n.t("To stop messages"), self.out_words, i18n.t("e.g. stop, unsubscribe, cancel")))
        self.in_words = QLineEdit()
        self.in_words.setMinimumHeight(38)
        cc.addWidget(ui.field(i18n.t("To start messages again"), self.in_words, i18n.t("e.g. start, subscribe")))
        self.confirm = QCheckBox(i18n.t("Reply to confirm"))
        cc.addWidget(self.confirm)
        self.out_reply = QPlainTextEdit()
        self.out_reply.setFixedHeight(72)
        cc.addWidget(ui.field(i18n.t("Reply when someone opts out"), self.out_reply))
        self.in_reply = QPlainTextEdit()
        self.in_reply.setFixedHeight(72)
        cc.addWidget(ui.field(i18n.t("Reply when someone opts in"), self.in_reply))
        row = QHBoxLayout()
        self.note = ui.note()
        row.addWidget(self.note, stretch=1)
        self.save_btn = C.button(i18n.t("Save"), "primary", on_click=self._save)
        row.addWidget(self.save_btn)
        cc.addLayout(row)
        col.addWidget(card)
        col.addStretch(1)

    def say(self, message: str, error: bool = False):
        (self.note.error if error else self.note.ok)(message)

    def activate(self):
        ui.call(self, "consent/get", {}, done=self._loaded, failed=lambda m, _d: self.note.error(m))

    def deactivate(self):
        pass

    def _loaded(self, reply: dict):
        s = reply.get("settings") or {}
        self.out_words.setText(", ".join(s.get("opt_out_keywords") or []))
        self.in_words.setText(", ".join(s.get("opt_in_keywords") or []))
        self.confirm.setChecked(bool(s.get("confirm", True)))
        self.out_reply.setPlainText(s.get("opt_out_reply") or "")
        self.in_reply.setPlainText(s.get("opt_in_reply") or "")

    def settings(self) -> dict:
        words = lambda e: [w.strip() for w in e.text().split(",") if w.strip()]                 # noqa: E731
        return {"opt_out_keywords": words(self.out_words), "opt_in_keywords": words(self.in_words), "confirm": self.confirm.isChecked(),
                "opt_out_reply": self.out_reply.toPlainText().strip(), "opt_in_reply": self.in_reply.toPlainText().strip()}

    def _save(self):
        self.save_btn.setEnabled(False)
        ui.call(self, "consent/save", {"settings": self.settings()}, done=lambda r: (self.save_btn.setEnabled(True), self._loaded(r), self.note.ok(i18n.t("Saved."))),
                failed=lambda m, _d: (self.save_btn.setEnabled(True), self.note.error(m)))


class NotificationsSection(QWidget):
    """What the Inbox tells you when it is not the screen you are looking at: a pop-up and a sound, for every message or only
    for a chat that needs a person. Saved to this computer's own settings: each person sets their own."""

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg if isinstance(cfg, dict) else {}
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)
        card, cc = ui.card(i18n.t("Notifications"), i18n.t("How the Inbox gets your attention while you work in another part of Prism. "
                                                          "These are for this computer only."), width=_COLUMN)
        from addons.whatsapp import notify
        p = notify.prefs(self.cfg)
        self.toast = QCheckBox(i18n.t("Show a pop-up"))
        self.toast.setChecked(p["toast"])
        self.sound = QCheckBox(i18n.t("Play a sound"))
        self.sound.setChecked(p["sound"])
        self.only = QCheckBox(i18n.t("Only when a chat needs a person"))
        self.only.setChecked(p["only_requests"])
        for box in (self.toast, self.sound, self.only):
            box.toggled.connect(lambda _on: self._save())
            cc.addWidget(box)
        row = QHBoxLayout()
        row.addWidget(C.button(i18n.t("Try it"), "secondary", on_click=self._try), alignment=Qt.AlignLeft)
        row.addStretch(1)
        cc.addLayout(row)
        self.note = ui.note()
        cc.addWidget(self.note)
        col.addWidget(card)
        col.addStretch(1)

    def activate(self):
        pass

    def deactivate(self):
        pass

    def _save(self):
        import core_bridge as CB
        from addons.whatsapp import notify
        notify.store(self.cfg, {"toast": self.toast.isChecked(), "sound": self.sound.isChecked(), "only_requests": self.only.isChecked()})
        try:
            CB.config.save(self.cfg)
            self.note.ok(i18n.t("Saved."))
        except Exception as e:                                   # noqa: BLE001
            self.note.error(i18n.t("Couldn't save: {e}").format(e=e))

    def _try(self):
        from addons.whatsapp import notify
        p = {"toast": self.toast.isChecked(), "sound": self.sound.isChecked(), "only_requests": False}
        notify.announce(self, p, [("request", {"contact_name": i18n.t("A customer"), "last_text": i18n.t("Can I speak to someone?")})])
