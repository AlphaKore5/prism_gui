"""Settings → Single sign-on: let the team sign in with their company account.

The owner enters the details of the company's sign-in provider (Google Workspace, Microsoft Entra, Okta and others that speak OpenID Connect), tests them, and optionally requires the team
to use it. A team member then signs in on the provider's own page — Prism never sees their password — and Prism learns only their e-mail and name. The e-mail is matched to a team member
(set it in Team and inbox). The workspace owner can always sign in with the licence, so a mistake here can never lock the owner out.

Needs the Enterprise plan. Only the owner can change these settings.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

import i18n
import theme
from addons.whatsapp import sso_state, ui
from addons.whatsapp.settings import _COLUMN, _scrolled
from dialogs.base import PrismDialog
from widgets import controls as C

POLL_MS = 2000
GIVE_UP = 450                                      # polls: fifteen minutes


def open_browser(url: str) -> None:
    """Open an address in the person's own browser. A function of its own so a test can stand in for the browser."""
    QDesktopServices.openUrl(QUrl(url))


class SignInDialog(PrismDialog):
    """Sign in with the company account: opens the provider in the browser and waits for the answer."""

    def __init__(self, parent=None, *, required: bool = False):
        super().__init__(i18n.t("Sign in with your company account"),
                         i18n.t("Your workspace asks everyone to sign in this way.") if required else i18n.t("You sign in on your company's own page. Prism never sees your password."),
                         icon="lock", parent=parent)
        self.state, self.url, self._polls = "", "", 0
        self.who = {}
        self.status = C.label(i18n.t("Getting ready…"), level="SUPPORT", colour=theme.NEUTRAL[700], wrap=True)
        self.body.addWidget(self.status)
        self.again_btn = C.button(i18n.t("Open the sign-in page again"), "secondary", on_click=self._open)
        self.again_btn.setVisible(False)
        self.body.addWidget(self.again_btn)
        self.error = ui.note()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self.footer.set_primary(self.button(i18n.t("Cancel"), "primary", on_click=self.reject))
        self.resize(480, 300)
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.poll)
        ui.call(self, "sso/start", {}, done=self._started, failed=lambda m, _d: self._start_failed(m))

    def say(self, message: str, error: bool = False):
        (self.error.error if error else self.error.ok)(message)

    def _start_failed(self, message: str):
        self.status.setText(i18n.t("Signing in with the company account is not available."))
        self.error.error(message)

    def _started(self, reply: dict):
        self.state, self.url = reply["state"], reply["url"]
        self.status.setText(i18n.t("Your company's sign-in page is opening in your browser. Sign in there, then come back — this window notices by itself."))
        self.again_btn.setVisible(True)
        self._open()
        self.timer.start()

    def _open(self):
        if self.url:
            open_browser(self.url)

    def done(self, result):
        self.timer.stop()
        super().done(result)

    def poll(self):
        self._polls += 1
        if self._polls > GIVE_UP:
            self.timer.stop()
            self.status.setText(i18n.t("That took too long. Close this and start again."))
            return
        ui.call(self, "sso/status", {"state": self.state}, done=self._status, failed=lambda m, _d: (self.timer.stop(), self.error.error(m)))

    def _status(self, reply: dict):
        st = reply.get("status")
        if st == "failed":
            self.timer.stop()
            self.status.setText(i18n.t("The sign-in did not work."))
            self.error.error(reply.get("error") or i18n.t("Try again."))
        elif st == "ready":
            self.timer.stop()
            self.who = reply.get("result") or {}
            sso_state.set_session(self.who)
            self.status.setText(i18n.t("Signed in as {n}.").format(n=self.who.get("name") or self.who.get("email") or ""))
            self.accept()
        elif st == "expired":
            self.timer.stop()
            self.status.setText(i18n.t("That sign-in ran out of time. Close this and start again."))


def _line(placeholder: str = "", text: str = "", secret: bool = False) -> QLineEdit:
    e = QLineEdit(text)
    e.setMinimumHeight(38)
    e.setPlaceholderText(placeholder)
    if secret:
        e.setEchoMode(QLineEdit.Password)
    return e


class SsoSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config: dict = {}
        outer, col = _scrolled(None)
        QVBoxLayout(self).addWidget(outer)
        self.layout().setContentsMargins(0, 0, 0, 0)
        card, cc = ui.card(i18n.t("Single sign-on"), i18n.t("Let your team sign in with their company account. Works with providers that support OpenID Connect: Google Workspace, "
                                                              "Microsoft Entra, Okta and others."), _COLUMN)
        head = QHBoxLayout()
        head.addStretch(1)
        self.pill = C.Pill("", "quiet")
        head.addWidget(self.pill)
        cc.addLayout(head)
        self.issuer = _line("https://login.yourcompany.com")
        self.issuer.setAccessibleName(i18n.t("Provider address"))
        cc.addWidget(ui.field(i18n.t("Provider address (issuer)"), self.issuer, i18n.t("Prism looks up the rest from this address.")))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.client_id = _line("")
        self.client_id.setAccessibleName(i18n.t("Client id"))
        self.client_secret = _line("", secret=True)
        self.client_secret.setAccessibleName(i18n.t("Client secret"))
        row.addWidget(ui.field(i18n.t("Client id"), self.client_id), 1, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Client secret"), self.client_secret, i18n.t("Stored encrypted. Leave blank to keep the one saved.")), 1, Qt.AlignTop)
        cc.addLayout(row)
        self.domains = _line("company.com, company.in")
        self.domains.setAccessibleName(i18n.t("Allowed e-mail domains"))
        cc.addWidget(ui.field(i18n.t("Only these e-mail domains"), self.domains, i18n.t("Optional. Leave empty to accept any account the provider vouches for.")))
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_3)
        self.role_claim = _line("groups")
        self.role_claim.setAccessibleName(i18n.t("Group claim"))
        self.role_map = QPlainTextEdit()
        self.role_map.setPlaceholderText("sales-leads = manager")
        self.role_map.setMinimumHeight(60)
        self.role_map.setMaximumHeight(90)
        self.role_map.setAccessibleName(i18n.t("Group to role"))
        row.addWidget(ui.field(i18n.t("Where the provider lists groups"), self.role_claim, i18n.t("Optional. The name of the field.")), 1, Qt.AlignTop)
        row.addWidget(ui.field(i18n.t("Group = role"), self.role_map, i18n.t("One per line: a group, then manager or agent. The owner is never changed.")), 1, Qt.AlignTop)
        cc.addLayout(row)
        self.default_role = QComboBox()
        self.default_role.setMinimumHeight(38)
        self.default_role.setAccessibleName(i18n.t("Role for everyone else"))
        self.default_role.addItem(i18n.t("Agent"), "agent")
        self.default_role.addItem(i18n.t("Manager"), "manager")
        cc.addWidget(ui.field(i18n.t("Role for anyone not in a group"), self.default_role))
        self.enabled = QCheckBox(i18n.t("Switch single sign-on on"))
        self.require = QCheckBox(i18n.t("Require it: team members must sign in this way (the owner always can with the licence)"))
        cc.addWidget(self.enabled)
        cc.addWidget(self.require)
        self.note = ui.note()
        cc.addWidget(self.note)
        buttons = QHBoxLayout()
        self.save_btn = C.button(i18n.t("Save"), "primary", on_click=self.save)
        self.test_btn = C.button(i18n.t("Test the provider"), "secondary", on_click=self.test)
        self.try_btn = C.button(i18n.t("Try signing in"), "secondary", on_click=self.try_sign_in)
        for b in (self.save_btn, self.test_btn, self.try_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        cc.addLayout(buttons)
        col.addWidget(card)
        col.addStretch(1)

    def say(self, message: str, error: bool = False):
        self.note.set(message, "error" if error else "ok")

    def activate(self):
        ui.call(self, "sso/config", {}, done=self._loaded, failed=self._failed)

    def deactivate(self):
        pass

    def _failed(self, message: str, detail: dict):
        if (detail or {}).get("reason") == "plan_feature":
            self.pill.setText(i18n.t("Enterprise plan"))
            self.pill.set_tone("warn")
            for w in (self.save_btn, self.test_btn, self.try_btn):
                w.setEnabled(False)
            self.note.set(i18n.t("Single sign-on is part of the Enterprise plan."), "warn")
        else:
            self.note.error(message)

    def _loaded(self, reply: dict):
        c = self.config = reply["config"]
        self.issuer.setText(c.get("issuer") or "")
        self.client_id.setText(c.get("client_id") or "")
        self.client_secret.clear()
        self.client_secret.setPlaceholderText(i18n.t("Saved — leave blank to keep") if c.get("client_secret_set") else "")
        self.domains.setText(", ".join(c.get("allowed_domains") or []))
        self.role_claim.setText(c.get("role_claim") or "")
        self.role_map.setPlainText("\n".join("%s = %s" % (k, v) for k, v in (c.get("role_map") or {}).items()))
        self.default_role.setCurrentIndex(max(self.default_role.findData(c.get("default_role") or "agent"), 0))
        self.enabled.setChecked(bool(c.get("enabled")))
        self.require.setChecked(bool(c.get("require_sso")))
        if c.get("require_sso"):
            self.pill.setText(i18n.t("Required"))
            self.pill.set_tone("ok")
        elif c.get("enabled"):
            self.pill.setText(i18n.t("On"))
            self.pill.set_tone("ok")
        else:
            self.pill.setText(i18n.t("Off"))
            self.pill.set_tone("quiet")

    def payload(self) -> dict:
        roles = {}
        for line in self.role_map.toPlainText().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip():
                    roles[k.strip()] = v.strip().lower()
        d = {"issuer": self.issuer.text().strip(), "client_id": self.client_id.text().strip(),
             "allowed_domains": [x.strip() for x in self.domains.text().replace(";", ",").split(",") if x.strip()], "role_claim": self.role_claim.text().strip(), "role_map": roles,
             "default_role": self.default_role.currentData(), "enabled": self.enabled.isChecked(), "require_sso": self.require.isChecked()}
        if self.client_secret.text().strip():
            d["client_secret"] = self.client_secret.text().strip()
        return d

    def save(self):
        self.save_btn.setEnabled(False)
        ui.call(self, "sso/save", self.payload(), done=self._saved, failed=self._save_failed)

    def _saved(self, reply: dict):
        self.save_btn.setEnabled(True)
        self._loaded(reply)
        self.say(i18n.t("Saved."))

    def _save_failed(self, message: str, _detail: dict):
        self.save_btn.setEnabled(True)
        self.say(message, error=True)

    def test(self):
        ui.call(self, "sso/test", {}, done=lambda r: self.say(i18n.t("The provider answered and published {n} signing key(s). Sign-in page: {u}").format(n=r.get("keys", 0), u=r.get("authorize_url", ""))))

    def try_sign_in(self):
        dlg = SignInDialog(self)
        if dlg.exec() and dlg.who:
            self.say(i18n.t("It works. You signed in as {n}.").format(n=dlg.who.get("name") or dlg.who.get("email")))
