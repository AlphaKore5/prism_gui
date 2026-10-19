"""Connect an ad account by signing in with Facebook, instead of pasting an access token.

Prism opens Facebook in your browser. You say yes there; Facebook sends you to a page of Alphakore's that hands Prism the answer (that page never shows a token and says only
whether it worked). This window is waiting for that — it asks every couple of seconds — and, when it is ready, shows the ad accounts and Pages you can use so you can pick.
Nothing is connected until you pick one. If signing in with Facebook is not set up on this server yet, it says so and offers the older way, pasting a token.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox

import i18n
import theme
from addons.whatsapp import ui
from dialogs.base import PrismDialog
from widgets import controls as C

POLL_MS = 2000
GIVE_UP = 450                                      # polls: fifteen minutes


def open_browser(url: str) -> None:
    """Open an address in the person's own browser. A function of its own so a test can stand in for the browser."""
    QDesktopServices.openUrl(QUrl(url))


class FacebookConnectDialog(PrismDialog):
    paste_instead = Signal()

    def __init__(self, parent=None):
        super().__init__(i18n.t("Connect with Facebook"), i18n.t("You sign in on Facebook's own page. Prism never sees your password."), icon="globe", parent=parent)
        self.state, self.url, self._polls = "", "", 0
        self.account_id = ""
        self.status = C.label(i18n.t("Getting ready…"), level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True)
        self.body.addWidget(self.status)
        self.again_btn = C.button(i18n.t("Open Facebook again"), "secondary", on_click=self._open)
        self.again_btn.setVisible(False)
        self.body.addWidget(self.again_btn)
        self.accounts = QComboBox()
        self.accounts.setMinimumHeight(38)
        self.accounts.setAccessibleName(i18n.t("Ad account"))
        self.pages = QComboBox()
        self.pages.setMinimumHeight(38)
        self.pages.setAccessibleName(i18n.t("Page"))
        self.choose_box = ui.field(i18n.t("Ad account to make ads in"), self.accounts)
        self.page_box = ui.field(i18n.t("Facebook Page the ads run as"), self.pages)
        self.body.addWidget(self.choose_box)
        self.body.addWidget(self.page_box)
        self.choose_box.setVisible(False)
        self.page_box.setVisible(False)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.paste_btn = self.button(i18n.t("Paste a token instead"), on_click=self._paste)
        self.paste_btn.setVisible(False)
        self.footer.add_secondary(self.button(i18n.t("Cancel"), on_click=self.reject))
        self.footer.add_secondary(self.paste_btn)
        self.go = self.button(i18n.t("Use this account"), "primary", on_click=self._choose)
        self.go.setVisible(False)
        self.footer.set_primary(self.go)
        self.resize(500, 420)
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.poll)
        ui.call(self, "ads/connect_start", {}, done=self._started, failed=lambda m, _d: self._start_failed(m))

    def say(self, message: str, error: bool = False):
        (self.error.error if error else self.error.ok)(message)

    def _start_failed(self, message: str):
        self.status.setText(i18n.t("Signing in with Facebook is not available."))
        self.error.error(message)
        self.paste_btn.setVisible(True)

    def _started(self, reply: dict):
        self.state, self.url = reply["state"], reply["url"]
        self.status.setText(i18n.t("Facebook is opening in your browser. Say yes there, then come back here — this window notices by itself."))
        self.again_btn.setVisible(True)
        self._open()
        self.timer.start()

    def _open(self):
        if self.url:
            open_browser(self.url)

    def _paste(self):
        self.timer.stop()
        self.paste_instead.emit()
        self.reject()

    def done(self, result):
        self.timer.stop()
        super().done(result)

    def poll(self):
        self._polls += 1
        if self._polls > GIVE_UP:
            self.timer.stop()
            self.status.setText(i18n.t("That took too long. Close this and start again."))
            return
        ui.call(self, "ads/connect_status", {"state": self.state}, done=self._status, failed=lambda m, _d: self._poll_failed(m))

    def _poll_failed(self, message: str):
        self.timer.stop()
        self.error.error(message)

    def _status(self, reply: dict):
        st = reply.get("status")
        if st == "failed":
            self.timer.stop()
            self.status.setText(i18n.t("Facebook did not connect."))
            self.error.error(reply.get("error") or i18n.t("Try again, or paste a token instead."))
            self.paste_btn.setVisible(True)
        elif st == "ready":
            self.timer.stop()
            o = reply.get("options") or {}
            self.status.setText(i18n.t("Signed in as {n}. Choose where the ads go.").format(n=o.get("user") or ""))
            self.again_btn.setVisible(False)
            self.accounts.clear()
            for a in o.get("accounts") or []:
                self.accounts.addItem("%s  ·  %s  ·  %s" % (a.get("name") or i18n.t("Ad account"), a.get("id"), a.get("currency") or ""), a.get("id"))
            self.pages.clear()
            for p in o.get("pages") or []:
                self.pages.addItem(p.get("name") or p.get("id"), p.get("id"))
            if not self.accounts.count() or not self.pages.count():
                self.error.error(i18n.t("That Facebook login has no ad account or no Page it can use. Add one in Meta Business Suite, or paste a token instead."))
                self.paste_btn.setVisible(True)
                return
            self.choose_box.setVisible(True)
            self.page_box.setVisible(True)
            self.go.setVisible(True)

    def _choose(self):
        self.go.setEnabled(False)
        ui.call(self, "ads/connect_choose", {"state": self.state, "ad_account_id": self.accounts.currentData(), "page_id": self.pages.currentData()},
                done=self._chosen, failed=lambda m, _d: self._choose_failed(m))

    def _choose_failed(self, message: str):
        self.go.setEnabled(True)
        self.error.error(message)

    def _chosen(self, reply: dict):
        self.account_id = reply.get("account_id") or ""
        self.accept()
