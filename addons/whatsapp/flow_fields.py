"""The small controls every kind of flow step is made of, kept apart so the step cards and the canvas can share them.

  TargetCombo   where a step goes next: "End the flow" or one of the steps (never a name that is not there)
  text_edit     a multi-line box that reports every change
  line          a one-line box that reports every change
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit

import i18n


class TargetCombo(QComboBox):
    """Where to go next: End the flow, or one of the steps."""
    chosen = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(34)
        self.setAccessibleName(i18n.t("Next step"))
        self.activated.connect(lambda _i: self.chosen.emit(self.currentData()))

    def set_targets(self, labels: dict, current: Optional[str], exclude: str = ""):
        self.blockSignals(True)
        self.clear()
        self.addItem(i18n.t("End the flow"), None)
        for nid, text in labels.items():
            if nid != exclude:
                self.addItem("%s  ·  %s" % (nid, text) if text else nid, nid)
        i = self.findData(current)
        if current and i < 0:
            self.addItem(i18n.t("(missing) {n}").format(n=current), current)
            i = self.count() - 1
        self.setCurrentIndex(max(i, 0))
        self.blockSignals(False)

    def value(self) -> Optional[str]:
        return self.currentData()


def text_edit(value: str, on_change, height: int = 72, placeholder: str = "", name: str = "") -> QPlainTextEdit:
    e = QPlainTextEdit(value or "")
    e.setFixedHeight(height)
    if placeholder:
        e.setPlaceholderText(placeholder)
    if name:
        e.setAccessibleName(name)
    e.textChanged.connect(lambda: on_change(e.toPlainText()))
    return e


def line(value: str, on_change, placeholder: str = "", name: str = "") -> QLineEdit:
    e = QLineEdit(value or "")
    e.setMinimumHeight(34)
    if placeholder:
        e.setPlaceholderText(placeholder)
    if name:
        e.setAccessibleName(name)
    e.textChanged.connect(on_change)
    return e
