"""The Automations tab — the things that answer customers when nobody is typing.

    Flows                a chatbot you draw: questions, buttons, menus, hand-overs
    AI agents            an assistant that answers from what you have taught it
    Automatic messages   a message on a birthday or before an appointment, and drips sent after something happens

A flow takes a message first (when its trigger fits); an AI agent answers what no flow takes; and a person always wins — the
moment a teammate steps into a chat, both stay quiet.
"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

import i18n
import theme
from widgets import controls as C


class AutomationsPage(QWidget):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self._sections: dict = {}
        self._current = "flows"

        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SPACE_4, theme.SPACE_4, theme.SPACE_4, theme.SPACE_4)
        root.setSpacing(theme.SPACE_3)
        head = QHBoxLayout()
        head.setSpacing(theme.SPACE_3)
        self.chips = C.FilterChips([("flows", i18n.t("Flows")), ("agents", i18n.t("AI agents")), ("auto", i18n.t("Automatic messages"))], current="flows")
        self.chips.changed.connect(self.show_section)
        self.chips.setMinimumWidth(430)                                  # or the chips wrap onto separate lines
        head.addWidget(self.chips)
        head.addWidget(C.label(i18n.t("A flow answers first, an AI agent answers what no flow takes, and a person always wins."), level="SUPPORT",
                               colour=theme.NEUTRAL[600], wrap=True), stretch=1)
        root.addLayout(head)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.show_section("flows")

    def _section(self, key: str) -> QWidget:
        if key not in self._sections:
            if key == "flows":
                from addons.whatsapp.flows_page import FlowsSection
                w = FlowsSection(self.cfg)
            elif key == "agents":
                from addons.whatsapp.agents_page import AgentsSection
                w = AgentsSection(self.cfg)
            else:
                from addons.whatsapp.autos_page import AutosSection
                w = AutosSection(self.cfg)
            self._sections[key] = w
            self.stack.addWidget(w)
        return self._sections[key]

    def show_section(self, key: str):
        prev = self._sections.get(self._current)
        if prev is not None and self._current != key:
            prev.deactivate()
        self._current = key
        w = self._section(key)
        self.stack.setCurrentWidget(w)
        self.chips.set_current(key)
        w.activate()

    def activate(self):
        self.show_section(self._current)

    def deactivate(self):
        w = self._sections.get(self._current)
        if w is not None:
            w.deactivate()
