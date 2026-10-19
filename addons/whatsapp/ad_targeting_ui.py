"""Choosing who an ad is shown to: places and interests found by searching Meta's own directory, and where on Facebook and Instagram it may appear.

    SearchPicker   type a word, press Search, add what you want from the answers; what is chosen stays on screen as small removable tags
    Placements     which of Facebook, Instagram, Audience Network and Messenger, and the spots in each — or leave it to Meta, which is the default and usually cheapest

Nothing here invents an id: a place or an interest can only be added from a search result, which is what Meta needs (a typed name is not accepted).
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from widgets import controls as C

PUBLISHERS = ("facebook", "instagram", "audience_network", "messenger")
FACEBOOK_POSITIONS = ("feed", "story", "video_feeds", "marketplace", "search", "reels")
INSTAGRAM_POSITIONS = ("stream", "story", "explore", "reels", "shop")


def kind_words(kind: str) -> str:
    return {"city": i18n.t("City"), "region": i18n.t("State or region"), "country": i18n.t("Country"), "interests": i18n.t("Interest"), "behaviors": i18n.t("Behaviour")}.get(kind, kind or "")


def size_words(size) -> str:
    if not size or size[0] is None:
        return ""
    lo, hi = size
    short = lambda n: ("%.1fM" % (n / 1_000_000)) if n >= 1_000_000 else ("%dK" % (n // 1000)) if n >= 1000 else str(n)           # noqa: E731
    return i18n.t("{lo} to {hi} people").format(lo=short(lo), hi=short(hi)) if hi and hi != lo else i18n.t("{lo} people").format(lo=short(lo))


class SearchPicker(QWidget):
    """A search box over one kind of thing Meta knows about. `items()` is what is chosen, as the dicts the search returned."""
    changed = Signal()

    def __init__(self, owner, kind: str, placeholder: str, parent=None):
        super().__init__(parent)
        self.owner, self.kind = owner, kind
        self._chosen: list = []
        self._results: list = []
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_1)
        self.chosen_col = QVBoxLayout()
        self.chosen_col.setSpacing(2)
        col.addLayout(self.chosen_col)
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_2)
        self.edit = QLineEdit()
        self.edit.setMinimumHeight(36)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setAccessibleName(placeholder)
        self.edit.returnPressed.connect(self.search)
        row.addWidget(self.edit, 1)
        self.search_btn = C.button(i18n.t("Search"), "secondary", on_click=self.search)
        row.addWidget(self.search_btn)
        col.addLayout(row)
        self.note = ui.note()
        col.addWidget(self.note)
        self.results_col = QVBoxLayout()
        self.results_col.setSpacing(2)
        col.addLayout(self.results_col)
        self.render()

    def items(self) -> list:
        return [dict(x) for x in self._chosen]

    def set_items(self, items: list):
        self._chosen = [dict(x) for x in items or []]
        self.render()

    def _key(self, x: dict) -> str:
        return str(x.get("key") or x.get("id"))

    def render(self):
        ui.clear(self.chosen_col)
        for x in self._chosen:
            row = QHBoxLayout()
            row.addWidget(C.label("%s · %s" % (x.get("name") or self._key(x), kind_words(x.get("type") or self.kind)), level="SUPPORT"), 1)
            row.addWidget(C.icon_button("x", i18n.t("Remove {n}").format(n=x.get("name") or ""), on_click=lambda _=False, y=x: self.remove(y), colour=theme.NEUTRAL[600]))
            box = QWidget()
            box.setLayout(row)
            self.chosen_col.addWidget(box)

    def search(self):
        q = self.edit.text().strip()
        if len(q) < 2:
            self.note.error(i18n.t("Type at least two letters."))
            return
        account = self.owner.account_id()
        if not account:
            self.note.error(i18n.t("Choose the ad account first."))
            return
        self.search_btn.setEnabled(False)
        self.note.set(i18n.t("Searching…"), "quiet")
        ui.call(self, "ads/search", {"account_id": account, "kind": self.kind, "q": q, "limit": 10}, done=self._found, failed=lambda m, _d: self._failed(m))

    def _failed(self, message: str):
        self.search_btn.setEnabled(True)
        self.note.error(message)

    def _found(self, reply: dict):
        self.search_btn.setEnabled(True)
        self._results = list(reply.get("results") or [])
        self.note.clear_note()
        ui.clear(self.results_col)
        if not self._results:
            self.note.set(i18n.t("Nothing found. Try another word."), "quiet")
        for x in self._results:
            row = QHBoxLayout()
            text = "%s%s" % (x.get("name") or "", ("  ·  " + x["detail"]) if x.get("detail") else "")
            row.addWidget(C.label(text, level="SUPPORT", wrap=True), 1)
            if x.get("size"):
                row.addWidget(C.label(size_words(x["size"]), level="META", colour=theme.NEUTRAL[500]))
            row.addWidget(C.label(kind_words(x.get("type") or self.kind), level="META", colour=theme.NEUTRAL[500]))
            row.addWidget(C.button(i18n.t("Add"), "tertiary", small=True, on_click=lambda _=False, y=x: self.add(y)))
            box = QWidget()
            box.setLayout(row)
            self.results_col.addWidget(box)

    def add(self, item: dict):
        if any(self._key(x) == self._key(item) for x in self._chosen):
            return
        self._chosen.append(dict(item))
        self.render()
        self.changed.emit()

    def remove(self, item: dict):
        self._chosen = [x for x in self._chosen if self._key(x) != self._key(item)]
        self.render()
        self.changed.emit()


class Placements(QWidget):
    """Where on Facebook and Instagram the ad may appear. Left alone, Meta chooses (it finds the cheapest places); choose your own only if you must."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE_1)
        self.auto = QCheckBox(i18n.t("Let Meta choose the places (recommended)"))
        self.auto.setChecked(True)
        self.auto.toggled.connect(self._toggled)
        col.addWidget(self.auto)
        self.box = QWidget()
        bl = QVBoxLayout(self.box)
        bl.setContentsMargins(theme.SPACE_4, 0, 0, 0)
        bl.setSpacing(2)
        self.platforms = {}
        words = {"facebook": i18n.t("Facebook"), "instagram": i18n.t("Instagram"), "audience_network": i18n.t("Audience Network (other apps)"), "messenger": i18n.t("Messenger")}
        for k in PUBLISHERS:
            b = QCheckBox(words[k])
            b.setChecked(k in ("facebook", "instagram"))
            b.toggled.connect(lambda _on: self.changed.emit())
            self.platforms[k] = b
            bl.addWidget(b)
        col.addWidget(self.box)
        self.box.setVisible(False)

    def _toggled(self, on: bool):
        self.box.setVisible(not on)
        self.changed.emit()

    def value(self) -> dict:
        if self.auto.isChecked():
            return {}
        chosen = [k for k, b in self.platforms.items() if b.isChecked()]
        return {"publisher_platforms": chosen} if chosen else {}

    def set_value(self, t: dict):
        chosen = (t or {}).get("publisher_platforms")
        self.auto.setChecked(not chosen)
        for k, b in self.platforms.items():
            b.setChecked(k in (chosen or ("facebook", "instagram")))
