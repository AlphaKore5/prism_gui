"""Analytics, Plan and usage, Business profile, Blue tick, Links and QR, Webhooks, the numbers' limits and the Inbox's live updates.

Driven against the demo platform with a fake worker. No processEvents()/exec()/QEventLoop, and nothing touches the real ~/.prism.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core_bridge  # noqa: F401,E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

_app = QApplication.instance() or QApplication([])

from addons.whatsapp import demo, demo_media, demo_platform, media_lib, notify, qr, readstate, ui  # noqa: E402
from addons.whatsapp.license_client import PlatformError  # noqa: E402


class _Sig:
    def __init__(self):
        self._fns = []

    def connect(self, fn):
        self._fns.append(fn)

    def emit(self, *a):
        for fn in list(self._fns):
            fn(*a)


def _worker(calls, fail=None):
    class W:
        def __init__(self, route, data=None):
            self.route, self.data = route, dict(data or {})
            self.done, self.failed = _Sig(), _Sig()

        def start(self):
            calls.append((self.route, self.data))
            if fail and self.route in fail:
                self.failed.emit(fail[self.route], {})
                return
            try:
                reply = demo_platform.handle(self.route, self.data)
            except PlatformError as e:
                self.failed.emit(str(e), dict(e.detail, reason=e.reason))
            else:
                self.done.emit(reply)
    return W


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="prism-wa-usage-")
    readstate.reset_cache()
    media_lib._CACHE.clear()
    demo._state.clear()
    demo_platform._PAGE.clear()
    demo_media._BYTES.clear()
    monkeypatch.setattr(demo_platform.time, "sleep", lambda _s: None)
    monkeypatch.setattr(ui, "confirm", lambda *_a, **_k: True)
    with mock.patch("paths.user_dir", lambda *p: os.path.join(tmp, *p)):
        yield tmp
    media_lib._CACHE.clear()
    demo._state.clear()
    demo_platform._PAGE.clear()
    demo_media._BYTES.clear()


@pytest.fixture
def calls():
    return []


@pytest.fixture
def served(calls, monkeypatch):
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    return calls


def last(calls, route):
    return next(d for r, d in reversed(calls) if r == route)


def routes(calls):
    return [r for r, _d in calls]


def labels(widget) -> str:
    return " | ".join(lab.text() for lab in widget.findChildren(QLabel))


def buttons(widget) -> list:
    return [b.text() for b in widget.findChildren(QPushButton)]


def button(widget, text):
    return next(b for b in widget.findChildren(QPushButton) if b.text() == text)


# ── the pure helpers ─────────────────────────────────────────────────────────

def test_rupees_use_indian_grouping_and_words_not_the_sign():
    from addons.whatsapp.analytics_page import rupees
    assert [rupees(x) for x in (0, 999, 1000, 12345, 123456, 1234567, 12345678, -2500, 723.91, None)] == \
        ["Rs 0", "Rs 999", "Rs 1,000", "Rs 12,345", "Rs 1,23,456", "Rs 12,34,567", "Rs 1,23,45,678", "Rs -2,500", "Rs 724", "Rs 0"]


def test_durations_read_the_way_a_person_says_them():
    from addons.whatsapp.analytics_page import duration_text
    assert [duration_text(x) for x in (None, 45, 60, 95, 3600, 3660, 7325)] == ["—", "45 s", "1 min", "1 min 35 s", "1 h", "1 h 1 min", "2 h 2 min"]


def test_a_range_key_gives_the_days_it_names():
    from addons.whatsapp.analytics_page import range_for
    now = datetime(2026, 10, 18, 15, 30, tzinfo=timezone.utc)
    assert range_for("7", now) == ("2026-10-12T00:00:00Z", "2026-10-18T15:30:01Z")
    assert range_for("30", now)[0] == "2026-09-19T00:00:00Z" and range_for("90", now)[0] == "2026-07-21T00:00:00Z"
    assert range_for("month", now)[0] == "2026-10-01T00:00:00Z" and range_for("nonsense", now)[0] == "2026-09-19T00:00:00Z"


# ── Analytics ────────────────────────────────────────────────────────────────

@pytest.fixture
def analytics(served):
    from addons.whatsapp.analytics_page import AnalyticsPage
    page = AnalyticsPage({})
    page.resize(1300, 900)
    page.activate()
    yield page
    page.deactivate()


def test_the_page_loads_the_dashboard_for_thirty_days_and_fills_the_screen(analytics, calls):
    sent = last(calls, "reports/dashboard")
    assert sent["since"] < sent["until"] and "T" in sent["since"]
    t = demo_platform.handle("reports/dashboard", sent)["overview"]["totals"]
    assert analytics.k_sent.value.text() == "{:,}".format(t["sent"]) and analytics.k_delivered.value.text() == "%d%%" % round(t["delivered_rate"])
    assert analytics.k_read.value.text().endswith("%") and analytics.k_spend.value.text().startswith("Rs ")
    assert "with GST" in analytics.k_spend.detail.text() and len(analytics.chart._days) == 30
    assert "Marketing" in labels(analytics.spend_table) and "Utility" in labels(analytics.spend_table)
    assert "Bala" in labels(analytics.team_table) and "Diwali offer" in labels(analytics.campaign_table)
    assert analytics.note.text() == "" and " to " in analytics.sub.text()


def test_choosing_another_range_asks_for_it(analytics, calls):
    analytics.chips._pick("7")
    assert len(analytics.chart._days) == 7
    analytics.chips._pick("month")
    assert last(calls, "reports/dashboard")["since"].endswith("-01T00:00:00Z")


def test_an_answer_that_arrives_after_the_range_changed_is_ignored(analytics):
    old = analytics._token
    analytics.chips._pick("7")
    analytics._on_data(old, {"overview": {"totals": {"sent": 99999}, "days": []}, "usage": {}})
    assert analytics.k_sent.value.text() != "99,999"


def test_a_failed_load_is_said_in_words_and_a_later_one_clears_it(served, calls, monkeypatch):
    from addons.whatsapp.analytics_page import AnalyticsPage
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls, fail={"reports/dashboard": "The service is down"}))
    page = AnalyticsPage({})
    page.activate()
    assert "The service is down" in page.note.text() and "Couldn't load" in page.sub.text()
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls))
    page.activate()
    assert page.note.text() == ""


def test_the_spend_is_called_an_estimate_and_the_rates_can_be_corrected(analytics):
    assert "estimate" in labels(analytics).lower() and "Plan and usage" in labels(analytics)
    seen = []
    analytics.openSettings.connect(seen.append)
    analytics.rates_btn.click()
    assert seen == ["plan"]


def test_the_opt_in_card_and_the_team_table_say_what_happened(analytics):
    text = labels(analytics)
    assert " opted in" in text and " opted out" in text and "contacts can be messaged" in text and "7 chats are open" in text
    assert "1 min 35 s" in labels(analytics.team_table) or "min" in labels(analytics.team_table)


def test_a_report_downloads_as_a_csv_excel_opens_correctly(analytics, calls, monkeypatch, tmp_path):
    from addons.whatsapp import analytics_page as AP
    target = tmp_path / "overview.csv"
    monkeypatch.setattr(AP.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    analytics.download("overview")
    assert last(calls, "reports/download")["kind"] == "overview"
    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"Day,Sent,Delivered" in raw and raw.count(b"\n") >= 30


def test_a_cancelled_save_writes_nothing_and_a_plan_without_downloads_says_so(analytics, calls, monkeypatch, tmp_path):
    from addons.whatsapp import analytics_page as AP
    monkeypatch.setattr(AP.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    analytics.download("agents")
    assert list(tmp_path.iterdir()) == []
    demo_platform._state()["plan"] = "pro"
    analytics.activate()
    assert not analytics._can_download and "Premium" in analytics.download_btn.toolTip()
    analytics.download("agents")
    assert "not part of the Pro plan" in analytics.note.text()


def test_the_chart_draws_and_names_a_day_when_it_is_pointed_at(analytics, tmp_path):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent, Qt
    chart = analytics.chart
    chart.resize(700, 190)
    pm = chart.grab()
    assert not pm.isNull() and pm.toImage().pixelColor(300, 120) is not None
    area = chart._geometry()
    ev = QMouseEvent(QEvent.MouseMove, QPointF(area.left() + 5, area.top() + 10), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    chart.mouseMoveEvent(ev)
    first = chart._days[0]
    assert first["day"] in chart.toolTip() and "Sent" in chart.toolTip()
    chart.set_days([])
    assert not chart.grab().isNull()


def test_the_analytics_tab_is_part_of_the_workspace(served):
    from addons.whatsapp import workbench as W
    wb = W.WhatsAppWorkbench({})
    wb.show_tab(W._ANALYTICS)
    assert type(wb._pages[W._ANALYTICS]).__name__ == "AnalyticsPage" and wb._tab_buttons[W._ANALYTICS].text() == "Analytics"
    seen = []
    wb._open_settings_section = lambda key: seen.append(key)
    wb._pages[W._ANALYTICS].openSettings.emit("plan")
    assert seen == ["plan"]


# ── Plan and usage ───────────────────────────────────────────────────────────

@pytest.fixture
def plan(served):
    from addons.whatsapp.settings_plan import PlanSection
    s = PlanSection()
    s.activate()
    return s


def test_the_plan_is_shown_with_each_limit_against_what_is_used(plan):
    assert plan.plan_name.text() == "Premium" and "Unlimited" in plan.plan_next.text()
    text = labels(plan)
    assert "Team members" in text and "3 of 10" in text and "Tags" in text and "6 of 250" in text and "AI replies this month" in text and "212 of 1,000" in text
    assert "Media storage" in text and "up to 250" in text and "so far in" in text and "With 18% GST" in text


def test_the_usage_words_read_plainly():
    from addons.whatsapp.settings_plan import fraction, used_words
    assert used_words({"key": "tags", "used": 5, "limit": 10}) == "5 of 10" and used_words({"key": "tags", "used": 5, "limit": None}) == "5 · no limit"
    assert used_words({"key": "storage_mb", "used": 2048, "limit": 5120}) == "2.0 GB of 5.0 GB" and used_words({"key": "storage_mb", "used": 3, "limit": 1024}) == "3 MB of 1.0 GB"
    assert used_words({"key": "mps", "used": 0, "limit": 40}) == "up to 40" and used_words({"key": "mps", "used": 0, "limit": None}) == "no limit"
    assert fraction({"key": "tags", "used": 5, "limit": 10}) == 0.5 and fraction({"key": "tags", "used": 50, "limit": 10}) == 1.0
    assert fraction({"key": "tags", "used": 5, "limit": None}) == 0.0 and fraction({"key": "mps", "used": 1, "limit": 40}) == 0.0


def test_the_rate_card_starts_from_metas_rates_and_saves_what_was_charged(plan, calls):
    assert plan._spins["MARKETING"].value() == 0.8631 and plan._spins["UTILITY"].value() == 0.115
    plan._spins["MARKETING"].setValue(0.55)
    plan._save()
    assert last(calls, "usage/rates_save")["rates"]["MARKETING"] == 0.55 and "Saved" in plan.rates_note.text()
    assert demo_platform.handle("usage/rates", {})["rates"]["MARKETING"] == 0.55
    plan._reset()
    assert plan._spins["MARKETING"].value() == 0.8631 and plan.save_btn.isEnabled()


def test_a_basic_plan_says_where_it_ends(served):
    from addons.whatsapp.settings_plan import PlanSection
    demo_platform._state()["plan"] = "basic"
    s = PlanSection()
    s.activate()
    assert s.plan_name.text() == "Basic" and "Pro" in s.plan_next.text()


# ── Business profile ─────────────────────────────────────────────────────────

@pytest.fixture
def profile(served):
    from addons.whatsapp.settings_profile import ProfileSection
    s = ProfileSection()
    s.activate()
    return s


def test_the_profile_is_read_from_whatsapp(profile):
    assert profile.about.text().startswith("Compound walls") and profile.email.text() == "hello@patelconstructions.in"
    assert profile.site1.text() == "https://patelconstructions.in" and profile.site2.text() == "" and profile.vertical.currentData() == "PROF_SERVICES"
    assert profile.number.text() == "+91 98765 43210" and profile.about_count.text().endswith("/139") and profile.note.text() == ""


def test_changes_are_saved_with_the_photo_chosen_from_the_library(profile, calls):
    profile.about.setText("Walls, gates and sheds")
    profile.site2.setText("https://patel.in")
    profile.vertical.setCurrentIndex(profile.vertical.findData("RETAIL"))
    profile.photo.set_asset({"id": "m1", "kind": "image", "filename": "site-photo.png", "size": 100})
    profile._save()
    sent = last(calls, "profile/save")["profile"]
    assert sent["about"] == "Walls, gates and sheds" and sent["websites"] == ["https://patelconstructions.in", "https://patel.in"] and sent["vertical"] == "RETAIL"
    assert sent["picture_asset_id"] == "m1" and "Saved" in profile.note.text() and profile.photo.asset_id() is None and profile.save_btn.isEnabled()
    assert demo_platform.handle("profile/get", {})["profile"]["about"] == "Walls, gates and sheds"


def test_a_profile_whatsapp_would_refuse_is_explained(profile):
    profile.email.setText("not-an-email")
    profile.site1.setText("patel.in")
    profile._save()
    assert "email address" in profile.note.text() and "full address" in profile.note.text() and profile.save_btn.isEnabled()


def test_a_profile_that_could_not_be_read_fresh_says_it_is_old(served, calls, monkeypatch):
    from addons.whatsapp.settings_profile import ProfileSection
    s = ProfileSection()
    s._loaded({"profile": {"about": "Before"}, "number": "+91", "stale": True, "problem": "WhatsApp is down"})
    assert s.about.text() == "Before" and "last read" in s.note.text() and "WhatsApp is down" in s.note.text()


# ── Blue tick ────────────────────────────────────────────────────────────────

def test_the_blue_tick_checklist_reads_what_meta_reports():
    from addons.whatsapp.settings_profile import checklist
    ready = [{"tier": "TIER_10K", "quality": "GREEN", "name_status": "APPROVED"}]
    full = {"about": "a", "address": "b", "email": "c@d.e", "websites": ["https://x.in"]}
    rows = {k: st for k, _w, st, _h in checklist(ready, full, {})}
    assert rows == {"name": "yes", "quality": "yes", "volume": "yes", "profile": "yes", "verified": "manual", "known": "manual"}
    weak = {k: st for k, _w, st, _h in checklist([{"tier": "TIER_250", "quality": "YELLOW", "name_status": "PENDING_REVIEW"}], {"about": "a"}, {})}
    assert weak["name"] == "no" and weak["quality"] == "no" and weak["volume"] == "no" and weak["profile"] == "no"
    assert {k: st for k, _w, st, _h in checklist([], {}, {})}["volume"] == "no"
    assert "pending review" in [h for k, _w, _s, h in checklist([{"name_status": "PENDING_REVIEW"}], {}, {}) if k == "name"][0]


def test_the_blue_tick_screen_counts_what_is_in_place_and_remembers_what_you_confirmed(served, monkeypatch):
    from addons.whatsapp.settings_profile import BlueTickSection
    saved = []
    import core_bridge as CB
    monkeypatch.setattr(CB.config, "save", lambda cfg: saved.append(dict(cfg.get("whatsapp_blue_tick") or {})))
    cfg = {}
    s = BlueTickSection(cfg)
    s.activate()
    from PySide6.QtWidgets import QCheckBox
    assert s.verdict.text().startswith("4 of 6 are in place")                                # name, quality, volume and profile are true of the demo number
    boxes = s.findChildren(QCheckBox)
    assert len(boxes) == 2 and not any(b.isChecked() for b in boxes)
    boxes[0].setChecked(True)
    assert cfg["whatsapp_blue_tick"] == {"verified": True} and saved == [{"verified": True}]
    again = s.findChildren(QCheckBox)
    assert [b.isChecked() for b in again] == [True, False] and s.verdict.text().startswith("5 of 6 are in place")
    again[1].setChecked(True)
    assert s.verdict.text().startswith("Everything Meta looks at is in place")


# ── Links and QR ─────────────────────────────────────────────────────────────

def test_a_chat_link_carries_the_greeting_for_the_customer():
    from addons.whatsapp.settings_acquire import chat_link
    assert chat_link("+91 98765 43210") == "https://wa.me/919876543210"
    assert chat_link("+91 98765 43210", "Hello! I'd like a quote") == "https://wa.me/919876543210?text=Hello%21%20I%27d%20like%20a%20quote"
    assert chat_link("919876543210", "  ") == "https://wa.me/919876543210"
    for bad in ("", "abc", "12345"):
        with pytest.raises(ValueError):
            chat_link(bad)


def test_the_website_button_is_one_self_contained_snippet():
    from addons.whatsapp.settings_acquire import widget_snippet
    html = widget_snippet("https://wa.me/919876543210?text=Hi", label="Chat <with> us & more", colour="#112233", side="left")
    assert "https://wa.me/919876543210?text=Hi" in html and "left:20px" in html and "background:#112233" in html
    assert "Chat &lt;with&gt; us &amp; more" in html and "<script" not in html.lower() and html.count("<a ") == 1
    assert "background:#25D366" in widget_snippet("https://wa.me/1", colour="red; background:url(x)") and "right:20px" in widget_snippet("https://wa.me/1", side="top")


def test_the_qr_reads_back_as_the_link_at_every_size():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    det = cv2.QRCodeDetectorAruco() if hasattr(cv2, "QRCodeDetectorAruco") else cv2.QRCodeDetector()       # (the older detector gives up on the large sizes)
    for version in range(1, qr.MAX_VERSION + 1):
        text = ("https://wa.me/919876543210?text=" + "a" * qr.capacity(version))[:qr.capacity(version)]       # exactly what this version holds
        m = qr.matrix(text)
        assert len(m) == version * 4 + 17                                                  # and it is the smallest version that holds it
        img = np.pad(np.array([[0 if v else 255 for v in row] for row in m], dtype=np.uint8), 4, constant_values=255)
        img = cv2.resize(img, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
        assert det.detectAndDecode(img)[0] == text, version


def test_a_link_too_long_for_a_qr_is_refused_in_words():
    with pytest.raises(qr.QRError) as e:
        qr.matrix("x" * 300)
    assert "too long" in str(e.value) and "213" in str(e.value)


def test_the_png_and_svg_are_real_files():
    m = qr.matrix("https://wa.me/919876543210")
    data = qr.png(m, scale=4)
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data.endswith(b"IEND\xaeB`\x82")
    svg = qr.svg(m)
    assert svg.startswith("<svg") and "<path" in svg and svg.count("M") == sum(1 for row in m for v in row if v)


@pytest.fixture
def acquire(served):
    from addons.whatsapp.settings_acquire import AcquireSection
    s = AcquireSection()
    s.activate()
    return s


def test_the_section_builds_the_link_the_code_and_the_snippet_for_the_number(acquire):
    assert acquire.number.count() == 1 and acquire.link_edit.text().startswith("https://wa.me/919876543210?text=Hello")
    assert acquire.qr_label.pixmap() is not None and not acquire.qr_label.pixmap().isNull() and acquire.png_btn.isEnabled()
    assert acquire.link_edit.text() in acquire.code.toPlainText()
    acquire.greeting.setText("Namaste")
    assert acquire.link_edit.text().endswith("?text=Namaste") and acquire.link_edit.text() in acquire.code.toPlainText()
    acquire.greeting.setText("")
    assert acquire.link_edit.text() == "https://wa.me/919876543210"
    acquire.label.setText("Talk to us")
    acquire.side.setCurrentIndex(acquire.side.findData("left"))
    assert "Talk to us" in acquire.code.toPlainText() and "left:20px" in acquire.code.toPlainText()


def test_a_greeting_too_long_for_a_code_is_explained_and_the_link_still_works(acquire):
    acquire.greeting.setMaxLength(1000)
    acquire.greeting.setText("x" * 400)
    assert "too long" in acquire.note.text() and not acquire.png_btn.isEnabled() and acquire.link_edit.text().startswith("https://wa.me/")


def test_the_code_is_saved_as_a_picture_or_for_print(acquire, monkeypatch, tmp_path):
    from addons.whatsapp import settings_acquire as SA
    for kind in ("png", "svg"):
        target = tmp_path / ("code." + kind)
        monkeypatch.setattr(SA.QFileDialog, "getSaveFileName", staticmethod(lambda *a, t=target, **k: (str(t), "")))
        acquire._save(kind)
        assert target.exists() and target.stat().st_size > 100
    assert (tmp_path / "code.png").read_bytes()[:4] == b"\x89PNG" and (tmp_path / "code.svg").read_text().startswith("<svg")


def test_no_connected_number_says_so(served, calls, monkeypatch):
    from addons.whatsapp.settings_acquire import AcquireSection
    monkeypatch.setattr(demo_platform, "_state", demo_platform._state)
    s = AcquireSection()
    s._loaded({"numbers": []})
    assert "No number is connected" in s.note.text() and not s.png_btn.isEnabled() and s.link_edit.text() == ""


# ── Webhooks ─────────────────────────────────────────────────────────────────

@pytest.fixture
def hooks(served):
    from addons.whatsapp.settings_webhooks import WebhooksCard
    card = WebhooksCard()
    card.load()
    return card


def make_hook(card, monkeypatch, url="https://hooks.example.com/prism", events=("message.received",)):
    from addons.whatsapp import settings_webhooks as SW
    shown = []

    class Secret:
        def __init__(self, secret, parent=None):
            shown.append(secret)

        def exec(self):
            return 1
    monkeypatch.setattr(SW, "SecretDialog", Secret)
    dlg = SW.WebhookDialog(card._events, card)
    dlg.url.setText(url)
    for k, b in dlg._boxes.items():
        b.setChecked(k in events)
    dlg._go()
    assert dlg.created, dlg.note.text()
    card._new = lambda: None
    SW.SecretDialog(dlg.created["secret"]).exec()
    card.load()
    return shown


def test_a_new_webhook_is_made_and_its_secret_shown_once(hooks, monkeypatch):
    assert "No webhooks yet" in labels(hooks) and hooks._events["chat.handoff"] == "A chat needs a person"
    shown = make_hook(hooks, monkeypatch, events=("message.received", "chat.handoff"))
    assert len(shown) == 1 and shown[0].startswith("whsec_")
    text = labels(hooks)
    assert "https://hooks.example.com/prism" in text and "A customer sent a message, A chat needs a person" in text and "No webhooks yet" not in text
    assert "whsec_" not in text


def test_a_refused_address_is_explained_in_the_dialog(hooks):
    from addons.whatsapp import settings_webhooks as SW
    dlg = SW.WebhookDialog(hooks._events, hooks)
    dlg.url.setText("https://10.0.0.5/hook")
    dlg._go()
    assert dlg.created is None and "private network" in dlg.note.text() and dlg.go.isEnabled()
    dlg.url.setText("http://plain.example.com")
    dlg._go()
    assert "https" in dlg.note.text()
    for b in dlg._boxes.values():
        b.setChecked(False)
    assert not dlg.go.isEnabled() and dlg.chosen() == []


def test_a_plan_without_webhooks_says_so_and_a_full_one_says_how_many(hooks, monkeypatch):
    from addons.whatsapp import settings_webhooks as SW
    demo_platform._state()["plan"] = "pro"
    dlg = SW.WebhookDialog(hooks._events, hooks)
    dlg.url.setText("https://hooks.example.com/x")
    dlg._go()
    assert "not part of the Pro plan" in dlg.note.text()
    demo_platform._state()["plan"] = "premium"
    make_hook(hooks, monkeypatch)
    dlg2 = SW.WebhookDialog(hooks._events, hooks)
    dlg2.url.setText("https://hooks.example.com/second")
    dlg2._go()
    assert "allows 1 webhooks" in dlg2.note.text()


def test_a_webhook_can_be_tested_switched_off_given_a_new_secret_and_deleted(hooks, calls, monkeypatch):
    from addons.whatsapp import settings_webhooks as SW
    make_hook(hooks, monkeypatch)
    ep = demo_platform.handle("webhooks/list", {})["endpoints"][0]
    hooks._test(ep)
    assert last(calls, "webhooks/test") == {"endpoint_id": ep["id"]} and "test message is on its way" in hooks.note.text()
    hooks._toggle(ep)
    assert demo_platform.handle("webhooks/list", {})["endpoints"][0]["enabled"] is False and "Off" in labels(hooks)
    shown = []
    monkeypatch.setattr(SW, "SecretDialog", lambda secret, parent=None: type("S", (), {"exec": lambda self: shown.append(secret)})())
    hooks._rotate(ep)
    assert shown and shown[0].startswith("whsec_")
    hooks._delete(ep)
    assert "Deleted" in hooks.note.text() and "No webhooks yet" in labels(hooks)


def test_the_log_shows_deliveries_and_sends_one_again(hooks, monkeypatch):
    from addons.whatsapp import settings_webhooks as SW
    make_hook(hooks, monkeypatch)
    ep = demo_platform.handle("webhooks/list", {})["endpoints"][0]
    hooks._test(ep)
    dlg = SW.LogDialog(ep, hooks._events)
    assert "A test message" in labels(dlg) and "Delivered" in labels(dlg) and "1 try" in labels(dlg) and "answer 200" in labels(dlg)
    dlg._again(demo_platform.handle("webhooks/deliveries", {"endpoint_id": ep["id"]})["deliveries"][0])
    assert "Queued" in dlg.note.text() and len(demo_platform.handle("webhooks/deliveries", {"endpoint_id": ep["id"]})["deliveries"]) == 2


def test_an_empty_log_says_how_to_start_it(hooks, monkeypatch):
    from addons.whatsapp import settings_webhooks as SW
    make_hook(hooks, monkeypatch)
    ep = demo_platform.handle("webhooks/list", {})["endpoints"][0]
    assert "Nothing has been sent" in labels(SW.LogDialog(ep, hooks._events))


def test_developers_has_the_webhooks_beside_the_keys(served, calls):
    from addons.whatsapp.settings_developers import DevelopersSection
    s = DevelopersSection()
    s.activate()
    assert "webhooks/list" in routes(calls) and "api_keys/list" in routes(calls) and "Webhooks" in labels(s)


# ── the numbers' limits ──────────────────────────────────────────────────────

def test_a_number_shows_its_daily_limit_its_name_review_and_can_be_checked_with_meta(served, calls):
    from addons.whatsapp.settings import ConnectionSection
    s = ConnectionSection()
    s.load_numbers()
    text = labels(s)
    assert "May start chats with 1,000 people a day" in text and "next step: 10,000" in text and "Display name approved" in text and "Speed standard" in text
    s._ask_meta()
    assert "numbers/refresh" in routes(calls) and "Up to date" in s.numbers_note.text() and s.limits_btn.isEnabled()


def test_a_problem_asking_meta_is_shown_and_the_button_comes_back(served, calls, monkeypatch):
    from addons.whatsapp.settings import ConnectionSection
    monkeypatch.setattr(ui, "PlatformWorker", _worker(calls, fail={"numbers/refresh": "Meta did not answer"}))
    s = ConnectionSection()
    s._ask_meta()
    assert "Meta did not answer" in s.numbers_note.text() and s.limits_btn.isEnabled()


def test_the_settings_rail_scrolls_so_every_section_stays_reachable(served):
    from addons.whatsapp import settings as S
    page = S.SettingsPage({})
    assert len(page._buttons) == 17
    for key in ("profile", "plan", "acquire", "bluetick"):
        page.show_section(key)
        assert type(page._sections[key]).__name__ in ("ProfileSection", "PlanSection", "AcquireSection", "BlueTickSection")


# ── the Inbox, live ──────────────────────────────────────────────────────────

@pytest.fixture
def inbox(served, monkeypatch):
    from addons.whatsapp import inbox as I
    later = []
    monkeypatch.setattr(I.QTimer, "singleShot", lambda ms, fn: later.append((ms, fn)))
    monkeypatch.setattr(notify, "announce", lambda *a, **k: 0)
    page = I.InboxPage({})
    page.resize(1500, 800)
    page.later = later
    page.activate()
    yield page
    page.deactivate()


def test_the_inbox_asks_the_service_whether_anything_changed_and_keeps_one_question_open(inbox, calls):
    asked = [d for r, d in calls if r == "inbox/changes"]
    assert len(asked) == 1 and asked[0]["cursor"] == "" and asked[0]["wait"] == 12 and asked[0]["_timeout"] > 12
    assert inbox._cursor == "1" and not inbox._listening
    assert any(fn == inbox._listen for _ms, fn in inbox.later)                               # the next question is scheduled the moment one is answered
    inbox._listening = True                                                                  # one is still open (the service has not answered)
    inbox._listen()
    inbox._listen()
    assert len([r for r, _d in calls if r == "inbox/changes"]) == 1                          # so no second one is asked


def test_a_change_refreshes_the_list_and_the_open_chat_then_asks_again(inbox, calls):
    row = inbox._rows[0]
    inbox._current = row
    before = len([r for r, _d in calls if r in ("inbox/threads", "inbox/thread")])
    inbox._on_changes({"cursor": "9", "changed": True})
    assert inbox._cursor == "9" and len([r for r, _d in calls if r in ("inbox/threads", "inbox/thread")]) >= before + 2
    assert last(calls, "inbox/thread")["conversation_id"] == row["id"] and inbox.later[-1] == (0, inbox._listen)
    inbox.later.clear()
    inbox._on_changes({"cursor": "9", "changed": False})
    assert inbox.later == [(0, inbox._listen)]


def test_a_failed_question_backs_off_and_the_quiet_look_again_carries_on(inbox):
    inbox.later.clear()
    inbox._listening = True
    inbox._on_changes_failed("down", {})
    assert inbox._live_failures == 1 and inbox.later == [(5000, inbox._listen)] and not inbox._listening
    inbox._on_changes_failed("down", {})
    inbox._on_changes_failed("down", {})
    assert inbox.later[-1][0] == 15000
    for _ in range(10):
        inbox._on_changes_failed("down", {})
    assert inbox.later[-1][0] == 30000                                                       # never longer than thirty seconds
    inbox._on_changes({"cursor": "2", "changed": False})
    assert inbox._live_failures == 0 and inbox._timer.isActive()


def test_leaving_the_tab_stops_the_questions(inbox, calls):
    inbox.deactivate()
    inbox.later.clear()
    n = len([r for r, _d in calls if r == "inbox/changes"])
    inbox._on_changes({"cursor": "5", "changed": True})
    inbox._on_changes_failed("late", {})
    assert inbox.later == [] and len([r for r, _d in calls if r == "inbox/changes"]) == n and not inbox._timer.isActive()
    inbox._listen()
    assert len([r for r, _d in calls if r == "inbox/changes"]) == n


def test_a_message_that_is_still_travelling_is_not_redrawn_under_the_person(inbox, calls):
    inbox._current = inbox._rows[0]
    inbox._load_thread(inbox._current["id"])
    shown = []
    inbox.thread.set_messages = lambda messages: shown.append(len(messages)) or True
    inbox._inflight = 1
    inbox._on_changes({"cursor": "3", "changed": True})
    assert shown == []                                                                       # the chat is not redrawn while a send is mid-flight
    inbox._inflight = 0
    inbox._on_changes({"cursor": "4", "changed": True})
    assert shown and shown[-1] > 0


def test_the_qr_matches_an_independent_encoder_module_for_module():
    rl = pytest.importorskip("reportlab.graphics.barcode.qrencoder")
    for version in range(1, qr.MAX_VERSION + 1):
        text = ("https://wa.me/919876543210?text=" + "a" * 300)[:qr.capacity(version)]
        words = qr._codewords(text.encode(), version)
        theirs = rl.QRCode(version, rl.QRErrorCorrectLevel.M)
        theirs.addData(text)
        for mask in range(8):
            theirs.makeImpl(False, mask)
            g = qr._Grid(version)
            g.place(words)
            g.mask(mask)
            g.format_bits(mask)
            assert g.mod == [[bool(theirs.isDark(r, c)) for c in range(theirs.getModuleCount())] for r in range(theirs.getModuleCount())], (version, mask)
