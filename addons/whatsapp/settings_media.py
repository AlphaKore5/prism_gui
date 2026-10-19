"""Settings -> Media library.

Every picture, video, voice note and document the workspace sends lives here once. A saved reply, an auto-reply, a template's
picture, a campaign and a chat's paperclip all choose from it, so a file is uploaded to WhatsApp once however many people get it.
The storage a plan allows is shown, and a file that something still uses cannot be deleted from under it.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import ui
from addons.whatsapp.media_lib import LibraryView
from addons.whatsapp.settings import _COLUMN


class MediaSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card, col = ui.card(i18n.t("Media library"), i18n.t("Pictures, videos, voice notes and documents you send. Upload once, then attach them in a chat, a "
                                                            "quick reply, an auto-reply or a campaign. Pictures up to 5 MB, videos and audio up to 16 MB."),
                            width=_COLUMN)
        self.view = LibraryView(manage=True)
        col.addWidget(self.view, stretch=1)
        outer.addWidget(card, 1, Qt.AlignHCenter)
        outer.setContentsMargins(theme.SPACE_4, theme.SPACE_4, theme.SPACE_4, theme.SPACE_4)

    def say(self, message: str, error: bool = False):
        self.view.say(message, error)

    def activate(self):
        self.view.reload()

    def deactivate(self):
        pass
