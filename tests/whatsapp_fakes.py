"""Shared pieces for the WhatsApp screen tests: a worker that answers from the demo platform straight away, so nothing opens a socket, starts a thread or spins an event loop.

Rules the tests that use this follow: no processEvents()/exec()/QEventLoop (a dialog's exec is replaced by a method that just returns), and nothing touches the real ~/.prism.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from addons.whatsapp import demo_platform
from addons.whatsapp.license_client import PlatformError


class Sig:
    def __init__(self):
        self._fns = []

    def connect(self, fn):
        self._fns.append(fn)

    def emit(self, *a):
        for fn in list(self._fns):
            fn(*a)


def worker(calls, fail=None, answers=None):
    """A PlatformWorker stand-in. `fail` = {route: message} makes that route fail; `answers` = {route: reply or callable} replaces the demo's answer."""
    class W:
        def __init__(self, route, data=None):
            self.route, self.data = route, dict(data or {})
            self.done, self.failed = Sig(), Sig()

        def start(self):
            calls.append((self.route, self.data))
            if fail and self.route in fail:
                msg = fail[self.route]
                self.failed.emit(msg if isinstance(msg, str) else msg[0], {} if isinstance(msg, str) else msg[1])
                return
            if answers and self.route in answers:
                a = answers[self.route]
                self.done.emit(a(self.data) if callable(a) else a)
                return
            try:
                reply = demo_platform.handle(self.route, self.data)
            except PlatformError as e:
                self.failed.emit(str(e), dict(e.detail, reason=e.reason))
            else:
                self.done.emit(reply)
    return W


def routes(calls) -> list:
    return [r for r, _d in calls]


def last(calls, route):
    return [d for r, d in calls if r == route][-1]


def texts(widget) -> str:
    return " | ".join(lab.text() for lab in widget.findChildren(QLabel))
