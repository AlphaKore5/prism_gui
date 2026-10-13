"""Lumi Help Center & Floating Assistant.

Recreates the Lumi Help Center card popup and its edge launcher, featuring:
  • Sprite-animated Lumi axolotl (8-frame spritesheet with waving and idle loops)
  • Welcome View with mint-gradient banner, wavy cloud, pill search bar, and 3 action cards
  • Conversational Chat View with rich markdown rendering, action chips, and back navigation
  • LumiEdgeButton: a small round launcher docked to the window's right edge
    (Android-style accessibility button) — drag along the edge, tuck away
"""
from __future__ import annotations

import json
import math
import os
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer,
    QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QTransform,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit,
    QMenu, QPushButton, QScrollArea, QSizePolicy, QStackedLayout, QVBoxLayout, QWidget,
)

import i18n
import paths
import theme
from widgets import controls as C
from widgets import icons
from widgets.markdown import render_markdown


# ── SPRITE ANIMATION FOR LUMI ────────────────────────────────────────────────
class LumiSpriteWidget(QWidget):
    """Animated Lumi axolotl using the 8-frame spritesheet.

    Row 0 (frames 0-3): Idle swaying, blinking, happy sparkling.
    Row 1 (frames 4-7): Waving hand animation.
    """

    def __init__(self, mode: str = "waving", size: QSize = QSize(160, 160), parent=None):
        super().__init__(parent)
        self.setFixedSize(size)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)

        self._frames: list[QPixmap] = []
        self._mode = mode
        self._current_seq_idx = 0
        self._load_spritesheet()

        # Animation sequence index lists
        self._waving_seq = [4, 5, 6, 7, 6, 5, 4, 5, 6, 7]
        self._idle_seq = [0, 1, 2, 3, 2, 1]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)
        self._timer.start(160)

    def _load_spritesheet(self):
        sheet_path = paths.resource("assets", "lumi", "lumi_spritesheet.png")
        if not os.path.exists(sheet_path):
            return

        sheet = QPixmap(sheet_path)
        if sheet.isNull():
            return

        fw = sheet.width() // 4
        fh = sheet.height() // 2
        for r in range(2):
            for c in range(4):
                frame = sheet.copy(c * fw, r * fh, fw, fh)
                self._frames.append(frame)

    def _next_frame(self):
        seq = self._waving_seq if self._mode == "waving" else self._idle_seq
        if not seq:
            return
        self._current_seq_idx = (self._current_seq_idx + 1) % len(seq)
        self.update()

    def set_mode(self, mode: str):
        if self._mode != mode:
            self._mode = mode
            self._current_seq_idx = 0
            self._timer.setInterval(160 if mode == "waving" else 220)
            self.update()

    def enterEvent(self, event):
        self.set_mode("waving")
        super().enterEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        if not self._frames:
            # Fallback to static character if spritesheet is missing
            fallback = QPixmap(paths.resource("assets", "lumi", "lumi_character.png"))
            if not fallback.isNull():
                scaled = fallback.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = (self.width() - scaled.width()) // 2
                y = (self.height() - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
            return

        seq = self._waving_seq if self._mode == "waving" else self._idle_seq
        frame_idx = seq[self._current_seq_idx % len(seq)]
        frame = self._frames[frame_idx]

        scaled = frame.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (self.width() - scaled.width()) // 2
        y = self.height() - scaled.height()
        painter.drawPixmap(x, y, scaled)


# ── ACTION CARD WIDGET ───────────────────────────────────────────────────────
class _QuickCard(QFrame):
    """One of the 3 cards below the input bar (Ask assistant / Book meeting / Contact)."""

    clicked = Signal()

    def __init__(self, title: str, subtitle: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("lumiQuickCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(124)
        self.setStyleSheet(
            "QFrame#lumiQuickCard {"
            "  background: #ffffff;"
            "  border: 1px solid #e2e8f0;"
            "  border-radius: 18px;"
            "}"
            "QFrame#lumiQuickCard:hover {"
            "  background: #f0fdfa;"
            "  border-color: #2dd4bf;"
            "}"
        )

        box = QVBoxLayout(self)
        box.setContentsMargins(12, 12, 12, 12)
        box.setSpacing(5)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(icons.pixmap(icon_name, 28, "#0d9488", stroke=2.0))
        icon_lbl.setStyleSheet("background: transparent; border: none; padding: 0;")
        box.addWidget(icon_lbl, alignment=Qt.AlignLeft)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #0f172a; background: transparent; border: none; padding: 0;"
        )
        t_lbl.setWordWrap(True)
        box.addWidget(t_lbl)

        s_lbl = QLabel(subtitle)
        s_lbl.setStyleSheet(
            "font-size: 11.5px; color: #64748b; font-weight: 500; line-height: 125%; background: transparent; border: none; padding: 0;"
        )
        s_lbl.setWordWrap(True)
        box.addWidget(s_lbl)
        box.addStretch(1)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


# ── WELCOME VIEW HEADER WITH WAVES, MASCOT, AND CLOUD SHELF ───────────────────
class LumiWelcomeHeader(QWidget):
    """Header with flowing waves, sparkles, animated Lumi mascot, and fluffy cloud shelf."""

    minimize_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(230)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.ArrowCursor)

        self._frames: list[QPixmap] = []
        self._mode = "waving"
        self._current_seq_idx = 0
        self._load_spritesheet()

        self._waving_seq = [4, 5, 6, 7, 6, 5, 4, 5, 6, 7]
        self._idle_seq = [0, 1, 2, 3, 2, 1]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)
        self._timer.start(160)

        # Child layouts for window controls and header text
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(24, 16, 24, 0)
        vbox.setSpacing(4)

        # Top Bar
        top_bar = QHBoxLayout()
        top_bar.addStretch(1)

        min_btn = QPushButton()
        min_btn.setFixedSize(26, 26)
        min_btn.setCursor(Qt.PointingHandCursor)
        min_btn.setToolTip(i18n.t("Minimize"))
        icons.button_icon(min_btn, "minus", 14, "#1e293b")
        min_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0; }"
            "QPushButton:hover { background: rgba(0,0,0,0.06); border-radius: 6px; }"
        )
        min_btn.clicked.connect(self.minimize_requested.emit)
        top_bar.addWidget(min_btn)

        close_btn = QPushButton()
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip(i18n.t("Close"))
        icons.button_icon(close_btn, "x", 14, "#1e293b")
        close_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0; }"
            "QPushButton:hover { background: rgba(0,0,0,0.06); border-radius: 6px; }"
        )
        close_btn.clicked.connect(self.close_requested.emit)
        top_bar.addWidget(close_btn)
        vbox.addLayout(top_bar)

        # Header Text
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 6, 0, 0)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)
        text_col.addStretch(1)

        title = QLabel(i18n.t("Hi, I’m Lumi"))
        title.setStyleSheet(
            f"font-family: '{theme.FONT_HEADING}'; font-size: 30px; font-weight: 800; color: #0f172a; background: transparent; border: none; padding: 0;"
        )
        text_col.addWidget(title)

        sub = QLabel(i18n.t("I can answer questions, find docs, and\nconnect you to support."))
        sub.setStyleSheet(
            "font-size: 13.5px; color: #334155; font-weight: 500; line-height: 135%; background: transparent; border: none; padding: 0;"
        )
        sub.setWordWrap(True)
        text_col.addWidget(sub)
        text_col.addStretch(1)

        content_row.addLayout(text_col, stretch=5)
        content_row.addSpacing(210)  # Space reserved for animated mascot on the right
        vbox.addLayout(content_row)

    def _load_spritesheet(self):
        sheet_path = paths.resource("assets", "lumi", "lumi_spritesheet.png")
        if not os.path.exists(sheet_path):
            return
        sheet = QPixmap(sheet_path)
        if sheet.isNull():
            return
        fw = sheet.width() // 4
        fh = sheet.height() // 2
        for r in range(2):
            for c in range(4):
                frame = sheet.copy(c * fw, r * fh, fw, fh)
                self._frames.append(frame)

    def _next_frame(self):
        seq = self._waving_seq if self._mode == "waving" else self._idle_seq
        if not seq:
            return
        self._current_seq_idx = (self._current_seq_idx + 1) % len(seq)
        self.update()

    def set_mode(self, mode: str):
        if self._mode != mode:
            self._mode = mode
            self._current_seq_idx = 0
            self._timer.setInterval(160 if mode == "waving" else 220)
            self.update()

    def enterEvent(self, event):
        self.set_mode("waving")
        super().enterEvent(event)

    def _draw_star(self, painter: QPainter, cx: float, cy: float, r_outer: float, r_inner: float, color: QColor):
        path = QPainterPath()
        for i in range(8):
            angle = i * math.pi / 4.0
            r = r_outer if i % 2 == 0 else r_inner
            px = cx + r * math.cos(angle)
            py = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)
        path.closeSubpath()
        painter.fillPath(path, color)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        w = float(self.width())
        h = float(self.height())

        # Clip strictly inside the parent card's rounded top border (radius 36px, stroke 3px)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(3.0, 3.0, w - 6.0, h + 100.0), 33.0, 33.0)
        painter.setClipPath(clip_path)

        # 1. Base gradient
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(220, 252, 231, 230))
        grad.setColorAt(0.35, QColor(204, 251, 241, 180))
        grad.setColorAt(0.8, QColor(230, 255, 250, 240))
        grad.setColorAt(1.0, QColor(240, 253, 250, 255))
        painter.fillRect(self.rect(), grad)

        # 2. Organic flowing waves on top-left (matching reference)
        wave1 = QPainterPath()
        wave1.moveTo(0, 0)
        wave1.lineTo(w * 0.42, 0)
        wave1.cubicTo(w * 0.46, h * 0.16, w * 0.34, h * 0.42, w * 0.18, h * 0.38)
        wave1.cubicTo(w * 0.06, h * 0.34, 0, h * 0.42, 0, h * 0.46)
        wave1.closeSubpath()
        painter.fillPath(wave1, QColor(167, 243, 208, 85))

        wave2 = QPainterPath()
        wave2.moveTo(0, h * 0.22)
        wave2.cubicTo(w * 0.16, h * 0.14, w * 0.32, h * 0.30, w * 0.38, h * 0.48)
        wave2.cubicTo(w * 0.28, h * 0.62, w * 0.12, h * 0.66, 0, h * 0.58)
        wave2.closeSubpath()
        painter.fillPath(wave2, QColor(153, 246, 228, 70))

        # 3. Draw Sparkles
        sparkle_color = QColor(45, 212, 191, 230)
        # Left sparkles
        self._draw_star(painter, w * 0.43, h * 0.44, 9.5, 3.2, sparkle_color)
        self._draw_star(painter, w * 0.46, h * 0.56, 6.5, 2.2, sparkle_color)
        dash_pen = QPen(sparkle_color, 2.5, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(dash_pen)
        painter.drawLine(QPointF(w * 0.43, h * 0.32), QPointF(w * 0.445, h * 0.295))
        painter.drawLine(QPointF(w * 0.41, h * 0.35), QPointF(w * 0.42, h * 0.37))
        # Right sparkles
        self._draw_star(painter, w * 0.94, h * 0.52, 7.5, 2.5, sparkle_color)
        painter.drawLine(QPointF(w * 0.91, h * 0.44), QPointF(w * 0.925, h * 0.42))
        painter.drawLine(QPointF(w * 0.93, h * 0.39), QPointF(w * 0.94, h * 0.41))

        # 4. Animated Lumi Mascot - 45% scale, upright & matching reference
        target_w = 150
        target_h = int(target_w * (384.0 / 256.0))
        mx = int(w - target_w - 20)
        my = 12

        if self._frames:
            seq = self._waving_seq if self._mode == "waving" else self._idle_seq
            frame_idx = seq[self._current_seq_idx % len(seq)]
            frame = self._frames[frame_idx]
            scaled = frame.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if self._mode == "diving":
                painter.save()
                painter.translate(mx + scaled.width() / 2, my + scaled.height() / 2)
                painter.rotate(-16.0)
                painter.drawPixmap(-scaled.width() // 2, -scaled.height() // 2 + 12, scaled)
                painter.restore()
            else:
                painter.drawPixmap(mx, my, scaled)
        else:
            fallback = QPixmap(paths.resource("assets", "lumi", "lumi_character.png"))
            if not fallback.isNull():
                scaled = fallback.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                if self._mode == "diving":
                    painter.save()
                    painter.translate(mx + scaled.width() / 2, my + scaled.height() / 2)
                    painter.rotate(-16.0)
                    painter.drawPixmap(-scaled.width() // 2, -scaled.height() // 2 + 12, scaled)
                    painter.restore()
                else:
                    painter.drawPixmap(mx, my, scaled)

        # 5. Fluffy White Cloud Shelf under Lumi - gentle shelf supporting arms/chest
        cloud = QPainterPath()
        cloud.moveTo(w * 0.26, h)
        cloud.cubicTo(w * 0.34, h * 0.98, w * 0.46, h * 0.89, w * 0.58, h * 0.89)
        cloud.cubicTo(w * 0.70, h * 0.85, w * 0.82, h * 0.87, w * 0.91, h * 0.93)
        cloud.cubicTo(w * 0.96, h * 0.96, w, h * 0.96, w, h)
        cloud.lineTo(w, h + 30)
        cloud.lineTo(w * 0.26, h + 30)
        cloud.closeSubpath()
        painter.fillPath(cloud, QColor(255, 255, 255, 255))


# ── LUMI CARD (POPUP WINDOW) ─────────────────────────────────────────────────
class LumiCard(QFrame):
    """The modern Lumi Help Center card popup matching the design references."""

    minimize_requested = Signal()
    close_requested = Signal()
    expand_toggled = Signal(bool)
    command_requested = Signal(str)
    typing_occurred = Signal()

    def __init__(self, support_panel: QWidget, parent=None):
        super().__init__(parent)
        self._support_panel = support_panel
        self.setObjectName("lumiMainCard")
        self.setFixedSize(465, 520)
        self._is_expanded = False
        self._exp_btns: list[QPushButton] = []

        self.setStyleSheet(
            "QFrame#lumiMainCard {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #dcfce7, stop:0.35 #e6fffa, stop:0.7 #f0fdfa, stop:1.0 #e6fffa);"
            "  border: 3px solid #5eead4;"
            "  border-radius: 36px;"
            "}"
        )

        # Soft mint drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setColor(QColor(45, 212, 191, 75))
        shadow.setOffset(0, 10)
        self.setGraphicsEffect(shadow)

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)

        # View 0: Welcome / Landing View
        self._welcome_view = self._build_welcome_view()
        self._stack.addWidget(self._welcome_view)

        # View 1: Conversation View
        self._chat_view = self._build_chat_view()
        self._stack.addWidget(self._chat_view)

    def toggle_expand(self):
        self._is_expanded = not getattr(self, "_is_expanded", False)
        if self._is_expanded:
            parent = self.parentWidget()
            pw = parent.width() if parent else 1200
            ph = parent.height() if parent else 800
            target_w = max(680, min(860, int(pw * 0.75)))
            target_h = max(620, min(840, int(ph * 0.88)))
            self.setFixedSize(target_w, target_h)
            for b in self._exp_btns:
                icons.button_icon(b, "minimize", 14, "#475569")
                b.setToolTip(i18n.t("Restore size"))
        else:
            self.setFixedSize(465, 520)
            for b in self._exp_btns:
                icons.button_icon(b, "maximize", 14, "#475569")
                b.setToolTip(i18n.t("Expand"))

        self.expand_toggled.emit(self._is_expanded)
        if hasattr(self._support_panel, "_sync_thread_height"):
            self._support_panel._sync_thread_height()

    def _build_welcome_view(self) -> QWidget:
        root = QWidget()
        box = QVBoxLayout(root)
        box.setContentsMargins(0, 0, 0, 16)
        box.setSpacing(12)

        # Header with flowing waves, animated mascot, and fluffy cloud shelf
        self._welcome_header = LumiWelcomeHeader(root)
        self._mascot = self._welcome_header
        self._welcome_header.minimize_requested.connect(self.minimize_requested.emit)
        self._welcome_header.close_requested.connect(self.close_requested.emit)
        box.addWidget(self._welcome_header)

        # Middle: Pill search bar
        search_wrap = QWidget()
        search_layout = QHBoxLayout(search_wrap)
        search_layout.setContentsMargins(18, 0, 18, 0)

        pill = QFrame()
        pill.setObjectName("lumiSearchPill")
        pill.setFixedHeight(52)
        pill.setStyleSheet(
            "QFrame#lumiSearchPill {"
            "  background: #ffffff;"
            "  border: 1px solid #cbd5e1;"
            "  border-radius: 26px;"
            "}"
            "QFrame#lumiSearchPill:focus-within {"
            "  border-color: #2dd4bf;"
            "}"
        )
        p_row = QHBoxLayout(pill)
        p_row.setContentsMargins(18, 2, 6, 2)
        p_row.setSpacing(10)

        self._input = QLineEdit()
        self._input.setPlaceholderText(i18n.t("Ask me anything about Prism..."))
        self._input.setStyleSheet(
            "QLineEdit { border: none; background: transparent; font-size: 13.5px; color: #0f172a; }"
        )
        self._input.returnPressed.connect(self._on_search_submitted)
        self._input.textChanged.connect(lambda _: self.typing_occurred.emit())
        p_row.addWidget(self._input, stretch=1)

        send_btn = QPushButton()
        send_btn.setFixedSize(38, 38)
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.setToolTip(i18n.t("Send"))
        send_btn.setIcon(icons.icon("send-plane", 18, "#0d9488"))
        send_btn.setIconSize(QSize(18, 18))
        send_btn.setStyleSheet(
            "QPushButton {"
            "  background: #99f6e4;"
            "  border: none;"
            "  border-radius: 19px;"
            "}"
            "QPushButton:hover {"
            "  background: #5eead4;"
            "}"
        )
        send_btn.clicked.connect(self._on_search_submitted)
        p_row.addWidget(send_btn)

        search_layout.addWidget(pill)
        box.addWidget(search_wrap)

        # Bottom: 3 Quick Action Cards
        cards_wrap = QWidget()
        cards_layout = QHBoxLayout(cards_wrap)
        cards_layout.setContentsMargins(16, 0, 16, 0)
        cards_layout.setSpacing(8)

        card1 = _QuickCard(i18n.t("Ask assistant"), i18n.t("Get help and find docs"), "chat-dots")
        card1.clicked.connect(self._open_assistant_chat)
        cards_layout.addWidget(card1)

        card2 = _QuickCard(i18n.t("Book a meeting"), i18n.t("Talk to the team"), "calendar-dots")
        card2.clicked.connect(self._open_book_meeting)
        cards_layout.addWidget(card2)

        card3 = _QuickCard(i18n.t("Contact support"), i18n.t("Get help from our team"), "headphones-mic")
        card3.clicked.connect(self._open_contact_sheet)
        cards_layout.addWidget(card3)

        box.addWidget(cards_wrap)
        box.addStretch(1)

        return root

    def _build_chat_view(self) -> QWidget:
        root = QWidget()
        box = QVBoxLayout(root)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(10)

        # Chat header: Back button | Avatar | Title | Min/Close
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        back_btn = QPushButton()
        back_btn.setFixedSize(30, 30)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setToolTip(i18n.t("Back to Lumi Home"))
        icons.button_icon(back_btn, "chevron-left", 14, "#334155")
        back_btn.setStyleSheet(
            "QPushButton {"
            "  border: 1px solid #cbd5e1;"
            "  background: #f8fafc;"
            "  border-radius: 15px;"
            "  min-width: 30px; max-width: 30px;"
            "  min-height: 30px; max-height: 30px;"
            "  padding: 0;"
            "}"
            "QPushButton:hover {"
            "  background: #f1f5f9;"
            "  border-color: #94a3b8;"
            "}"
        )
        back_btn.clicked.connect(self._show_welcome)
        top_row.addWidget(back_btn, alignment=Qt.AlignVCenter)

        avatar_lbl = QLabel()
        av_pix = QPixmap(paths.resource("assets", "lumi", "lumi_avatar.png"))
        if not av_pix.isNull():
            avatar_lbl.setPixmap(av_pix.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        avatar_lbl.setFixedSize(30, 30)
        top_row.addWidget(avatar_lbl, alignment=Qt.AlignVCenter)

        info_col = QVBoxLayout()
        info_col.setSpacing(1)
        c_title = QLabel("Lumi")
        c_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #0f172a;")
        info_col.addWidget(c_title)
        c_status = QLabel("● " + i18n.t("Online · Prism Assistant"))
        c_status.setStyleSheet("font-size: 11px; font-weight: 600; color: #10b981;")
        info_col.addWidget(c_status)
        top_row.addLayout(info_col, stretch=1)

        min_btn = QPushButton()
        min_btn.setFixedSize(28, 28)
        min_btn.setCursor(Qt.PointingHandCursor)
        min_btn.setToolTip(i18n.t("Minimize"))
        icons.button_icon(min_btn, "minus", 14, "#475569")
        min_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 6px; }"
        )
        min_btn.clicked.connect(self.minimize_requested.emit)
        top_row.addWidget(min_btn, alignment=Qt.AlignVCenter)

        exp_btn = QPushButton()
        exp_btn.setFixedSize(28, 28)
        exp_btn.setCursor(Qt.PointingHandCursor)
        exp_btn.setToolTip(i18n.t("Expand"))
        icons.button_icon(exp_btn, "maximize", 14, "#475569")
        exp_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 6px; }"
        )
        exp_btn.clicked.connect(self.toggle_expand)
        self._exp_btns.append(exp_btn)
        top_row.addWidget(exp_btn, alignment=Qt.AlignVCenter)

        close_btn = QPushButton()
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip(i18n.t("Close"))
        icons.button_icon(close_btn, "x", 14, "#475569")
        close_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0; }"
            "QPushButton:hover { background: rgba(0,0,0,0.07); border-radius: 6px; }"
        )
        close_btn.clicked.connect(self.close_requested.emit)
        top_row.addWidget(close_btn, alignment=Qt.AlignVCenter)

        box.addLayout(top_row)

        # Embedded SupportPanel inside the card
        if hasattr(self._support_panel, "set_compact"):
            self._support_panel.set_compact(True)
        box.addWidget(self._support_panel, stretch=1)

        return root

    def _show_welcome(self):
        self._stack.setCurrentIndex(0)
        self._mascot.set_mode("waving")

    def _show_chat(self):
        self._stack.setCurrentIndex(1)

    def _on_search_submitted(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._show_chat()
        # Feed question directly to SupportPanel
        if hasattr(self._support_panel, "_entry"):
            self._support_panel._entry.setText(text)
            self._support_panel._on_typed()

    def _open_assistant_chat(self):
        self._show_chat()
        if hasattr(self._support_panel, "_start_ai"):
            self._support_panel._start_ai()

    def _open_book_meeting(self):
        if hasattr(self._support_panel, "_book_meeting"):
            self._support_panel._book_meeting()

    def _open_contact_sheet(self):
        if hasattr(self._support_panel, "_open_contact"):
            self._support_panel._open_contact()


# ── LUMI EDGE BUTTON (Android-style floating accessibility button) ───────────
# The launcher used to be a 260-285 px dark pill reading "Need help? Ask Lumi
# anything." with a mascot walking on an 88 px stage above it. It sat on cards,
# table rows and footer buttons in the bottom-right of every screen, and the
# screens reserved 120 px under their last row to make room for it. The owner
# (14 Oct 2026): "make it like an accessibility bar, just like Android has".
# So it is now a small round face docked to the right edge: half see-through at
# rest, opaque under the cursor or focus, a short "Ask Lumi" label sliding out
# to its left on hover, draggable up and down the edge, and tuckable into a
# slim tab. It is a plain child widget of the window — no top-level window, no
# WA_TranslucentBackground — so it renders the same on Windows and macOS.

_LUMI_TEAL = "#18c7c1"           # Lumi's own ring colour (the avatar's rim)
_PREFS_FILE = "gui_lumi_button.json"


def _effects_on() -> bool:
    return (os.environ.get("PRISM_EFFECTS", "1") != "0"
            and os.environ.get("QT_QPA_PLATFORM") != "offscreen")


def _prefs_path() -> str:
    return paths.user_dir(_PREFS_FILE)


def load_button_prefs() -> dict:
    """Where the owner left the button: {"from_bottom": int|None,
    "tucked": bool, "welcomed": bool}. A missing or hand-mangled file is the
    default spot, never an error."""
    out = {"from_bottom": None, "tucked": False, "welcomed": False}
    try:
        with open(_prefs_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return out
    if not isinstance(data, dict):
        return out
    fb = data.get("from_bottom")
    if isinstance(fb, int) and not isinstance(fb, bool) and fb >= 0:
        out["from_bottom"] = fb
    out["tucked"] = data.get("tucked") is True
    out["welcomed"] = data.get("welcomed") is True
    return out


def save_button_prefs(prefs: dict) -> None:
    """Atomic write (temp file + os.replace, like favorites.save) into the
    user's own Prism folder. UI state is never worth a crash: failures are
    swallowed and the button simply forgets."""
    path = _prefs_path()
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"from_bottom": prefs.get("from_bottom"),
                       "tucked": bool(prefs.get("tucked")),
                       "welcomed": bool(prefs.get("welcomed"))}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


class LumiEdgeButton(QWidget):
    """Lumi's launcher: a small round button docked to the host's right edge.

    Emits `toggle_requested` on click, Enter or Space — the same signal the old
    pill emitted, so LumiOverlay opens and closes the card exactly as before.
    """

    toggle_requested = Signal()
    tucked_changed = Signal(bool)

    _RING = 3            # room around the face for the focus ring

    def __init__(self, host: QWidget, persist: bool = True):
        super().__init__(host)
        self._host = host
        self._persist = persist
        self.setObjectName("lumiEdgeButton")
        self.setAttribute(Qt.WA_Hover, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(i18n.t("Ask Lumi"))

        prefs = load_button_prefs() if persist else {
            "from_bottom": None, "tucked": False, "welcomed": True}
        self._from_bottom: Optional[int] = prefs["from_bottom"]
        self._tucked = bool(prefs["tucked"])
        self._welcomed = bool(prefs["welcomed"])

        self._hover = False
        self._card_is_open = False
        self._press_at: Optional[QPoint] = None   # host coords of the press
        self._press_y = 0
        self._dragging = False
        self._pushed = False                      # dragged against the edge
        self._pulse = 0.0
        self._pulse_anim: Optional[QVariantAnimation] = None
        self._label_anim: Optional[QVariantAnimation] = None
        self._face = QPixmap(paths.resource("assets", "lumi", "lumi_avatar.png"))
        self._face_cache: dict = {}

        self._label = QLabel(i18n.t("Ask Lumi"), host)
        self._label.setObjectName("lumiEdgeLabel")
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(
            f"QLabel#lumiEdgeLabel {{ background: {theme.NEUTRAL[900]};"
            f" color: #ffffff; font-family: '{theme.FONT_BODY}';"
            " font-size: 12px; font-weight: 600;"
            f" padding: {theme.SPACE_1}px {theme.SPACE_3}px;"
            f" border-radius: {theme.R_CONTROL}px; }}")
        self._label.hide()

        self._diam = self._diameter()
        self._sync_text()
        self.reposition()

    # ── geometry ─────────────────────────────────────────────────────────
    def _diameter(self) -> int:
        """From the font's line height, not a pixel guess: ~2.4 lines, held
        between theme.LUMI_BUTTON_MIN and _MAX. Logical pixels, so a 150 %
        Windows display and a retina Mac get the same size on screen."""
        d = round(QFontMetrics(self.font()).height() * 2.4)
        return max(theme.LUMI_BUTTON_MIN, min(theme.LUMI_BUTTON_MAX, d))

    def diameter(self) -> int:
        return self._diam

    def is_tucked(self) -> bool:
        return self._tucked

    def from_bottom(self) -> int:
        if self._from_bottom is None:
            return theme.LUMI_REST_FROM_BOTTOM
        return self._from_bottom

    def _clamp_y(self, y: int) -> int:
        h = self._host.height()
        top = theme.LUMI_EDGE_GAP
        bottom = max(top, h - self._diam - theme.LUMI_EDGE_GAP)
        return max(top, min(bottom, int(y)))

    def _x(self) -> int:
        w = self._host.width()
        if self._tucked:
            return w - theme.LUMI_TAB_W
        return w - theme.LUMI_EDGE_GAP - self._diam

    def reposition(self):
        """Dock to the right edge at the remembered height, clamped inside
        the host — called on every host resize and DPI/font change."""
        d = self._diam
        y = self._clamp_y(self._host.height() - self.from_bottom() - d)
        w = theme.LUMI_TAB_W if self._tucked else d
        self.setGeometry(self._x(), y, w, d)
        self.raise_()
        if self._label.isVisible():
            self._place_label(animate=False)

    # ── state ────────────────────────────────────────────────────────────
    def set_card_open(self, is_open: bool):
        self._card_is_open = bool(is_open)
        self.update()

    def set_tucked(self, tucked: bool):
        tucked = bool(tucked)
        if tucked == self._tucked:
            return
        self._tucked = tucked
        self._hide_label()
        self._sync_text()
        self.reposition()
        self.update()
        self._save()
        self.tucked_changed.emit(tucked)

    def move_to_bottom(self):
        """Back to the default spot, untucked."""
        self._from_bottom = None
        if self._tucked:
            self._tucked = False
            self._sync_text()
            self.tucked_changed.emit(False)
        self.reposition()
        self.update()
        self._save()

    def activate(self):
        """What a click, Enter or Space does: a tucked tab comes back; the
        button asks for Lumi."""
        if self._tucked:
            self.set_tucked(False)
        else:
            self.toggle_requested.emit()

    def _sync_text(self):
        if self._tucked:
            self.setToolTip(i18n.t("Bring Lumi back"))
            self.setAccessibleDescription(i18n.t("Lumi is tucked away. Press to bring the button back."))
        else:
            self.setToolTip(i18n.t("Ask Lumi — drag up or down to move, right-click to tuck away"))
            self.setAccessibleDescription(i18n.t("Opens Lumi, Prism’s help."))

    def _save(self):
        if self._persist:
            save_button_prefs({"from_bottom": self._from_bottom,
                               "tucked": self._tucked,
                               "welcomed": self._welcomed})

    # ── the "Ask Lumi" label ─────────────────────────────────────────────
    def _label_target(self):
        self._label.adjustSize()
        lw, lh = self._label.width(), self._label.height()
        x = self.x() - theme.SPACE_2 - lw
        y = self.y() + (self.height() - lh) // 2
        return max(0, x), max(0, y)

    def _place_label(self, animate: bool):
        x, y = self._label_target()
        if self._label_anim is not None:
            self._label_anim.stop()
        if not animate or not _effects_on():
            self._label.move(x, y)
            return
        anim = QVariantAnimation(self)
        anim.setDuration(140)
        anim.setStartValue(x + theme.SPACE_3)
        anim.setEndValue(x)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda v: self._label.move(int(v), y))
        self._label_anim = anim
        anim.start()

    def _show_label(self):
        if self._tucked or self._dragging or self._card_is_open:
            return
        was = self._label.isVisible()
        self._label.show()
        self._label.raise_()
        self.raise_()
        self._place_label(animate=not was)

    def _hide_label(self):
        if self._label_anim is not None:
            self._label_anim.stop()
        self._label.hide()

    def label_widget(self) -> QLabel:
        return self._label

    # ── first run / celebration: one gentle pulse instead of the mascot ──
    def pulse(self, times: int = 2):
        if not _effects_on() or self._tucked:
            return
        if self._pulse_anim is not None:
            self._pulse_anim.stop()
        anim = QVariantAnimation(self)
        anim.setDuration(900)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setLoopCount(max(1, times))
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _step(v):
            self._pulse = float(v)
            self.update()

        def _done():
            self._pulse = 0.0
            self.update()

        anim.valueChanged.connect(_step)
        anim.finished.connect(_done)
        self._pulse_anim = anim
        anim.start()

    def welcome_once(self):
        """The first time Prism shows the button for this user, it pulses
        twice so a newcomer notices it — the job the walking mascot did."""
        if self._welcomed or not _effects_on():
            return
        self._welcomed = True
        self._save()
        QTimer.singleShot(1200, self.pulse)

    # Kept for LumiOverlay callers of the old pill.
    def trigger_celebration(self, duration_ms: int = 3500):
        self.pulse(1)

    def on_user_typing(self):
        pass

    # ── events ───────────────────────────────────────────────────────────
    def event(self, ev):
        if ev.type() in (QEvent.FontChange, QEvent.DevicePixelRatioChange,
                         QEvent.ScreenChangeInternal):
            self._diam = self._diameter()
            self._face_cache.clear()
            self.reposition()
            self.update()
        return super().event(ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.welcome_once()

    def enterEvent(self, ev):
        self._hover = True
        self._show_label()
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover = False
        if not self.hasFocus():
            self._hide_label()
        self.update()
        super().leaveEvent(ev)

    def focusInEvent(self, ev):
        self._show_label()
        self.update()
        super().focusInEvent(ev)

    def focusOutEvent(self, ev):
        if not self._hover:
            self._hide_label()
        self.update()
        super().focusOutEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activate()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def _host_pos(self, ev) -> QPoint:
        return self.mapTo(self._host, ev.position().toPoint())

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._press_at = self._host_pos(ev)
            self._press_y = self.y()
            self._dragging = False
            self._pushed = False
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._press_at is None or not (ev.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(ev)
        self.drag_to(self._host_pos(ev))
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.LeftButton or self._press_at is None:
            return super().mouseReleaseEvent(ev)
        self.end_drag()
        ev.accept()

    def drag_to(self, at: QPoint):
        """Follow the pointer up or down the edge (never sideways). Pulling it
        right by more than half its width, into the edge, tucks it on release."""
        if self._press_at is None:
            self._press_at = QPoint(at)
            self._press_y = self.y()
        dx = at.x() - self._press_at.x()
        dy = at.y() - self._press_at.y()
        if not self._dragging:
            if abs(dx) + abs(dy) < QApplication.startDragDistance():
                return
            self._dragging = True
            self._hide_label()
        y = self._clamp_y(self._press_y + dy)
        self._from_bottom = max(0, self._host.height() - y - self._diam)
        self._pushed = (not self._tucked) and dx > self._diam // 2
        # A hint of the tuck: the face slides into the edge while pushed.
        shift = min(dx, self._diam // 2) if self._pushed else 0
        self.move(self._x() + max(0, shift), y)
        self.update()

    def end_drag(self):
        """Release: a click if it never moved, otherwise snap to the edge
        (or tuck, if it was pushed into it) and remember where."""
        dragged, pushed = self._dragging, self._pushed
        self._press_at = None
        self._dragging = False
        self._pushed = False
        if not dragged:
            self.activate()
            return
        if pushed:
            self.set_tucked(True)
        else:
            self.reposition()
            self._save()
        self.update()

    def context_menu(self) -> QMenu:
        menu = QMenu(self)
        if self._tucked:
            menu.addAction(i18n.t("Bring Lumi back"), lambda: self.set_tucked(False))
        else:
            menu.addAction(i18n.t("Ask Lumi"), self.toggle_requested.emit)
            menu.addAction(i18n.t("Tuck away"), lambda: self.set_tucked(True))
        menu.addAction(i18n.t("Move to bottom"), self.move_to_bottom)
        return menu

    def contextMenuEvent(self, ev):
        self._hide_label()
        self.context_menu().exec(ev.globalPos())
        ev.accept()

    # ── painting ─────────────────────────────────────────────────────────
    def _face_pixmap(self, size: int) -> QPixmap:
        dpr = self.devicePixelRatioF() or 1.0
        key = (size, round(dpr, 2))
        pix = self._face_cache.get(key)
        if pix is None:
            if self._face.isNull():
                return QPixmap()
            pix = self._face.scaled(max(1, round(size * dpr)), max(1, round(size * dpr)),
                                    Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pix.setDevicePixelRatio(dpr)
            self._face_cache[key] = pix
        return pix

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        lit = (self._hover or self.hasFocus() or self._dragging
               or self._card_is_open or self._pulse > 0)
        p.setOpacity(1.0 if lit else theme.LUMI_IDLE_OPACITY)
        if self._tucked:
            self._paint_tab(p)
        else:
            self._paint_face(p)
        p.end()

    def _paint_tab(self, p: QPainter):
        w, h = self.width(), self.height()
        path = QPainterPath()
        # Rounded on the left, running off the right edge of the window.
        path.addRoundedRect(QRectF(0, 0, w * 2, h), w * 0.9, w * 0.9)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_LUMI_TEAL))
        p.drawPath(path)
        pen = QPen(QColor("#ffffff"), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        cx, cy = w * 0.55, h / 2.0
        p.drawLine(QPointF(cx + 2, cy - 5), QPointF(cx - 2.5, cy))
        p.drawLine(QPointF(cx - 2.5, cy), QPointF(cx + 2, cy + 5))
        if self.hasFocus():
            p.setPen(QPen(QColor(theme.NEUTRAL[900]), 2.0))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

    def _paint_face(self, p: QPainter):
        ring = self._RING
        r = QRectF(self.rect()).adjusted(ring, ring, -ring, -ring)
        # Soft shadow, drawn (no QGraphicsEffect: those turn black on some
        # Windows GPU drivers when a widget sits over a scroll area).
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(9, 9, 11, 46))
        p.drawEllipse(r.translated(0, 1.5))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(r)
        face = r.adjusted(2, 2, -2, -2)
        clip = QPainterPath()
        clip.addEllipse(face)
        p.save()
        p.setClipPath(clip)
        # The avatar's own disc is ~96 % of its square; overscan so its black
        # corners stay outside the clip.
        size = int(face.width() * 1.08)
        pix = self._face_pixmap(size)
        if not pix.isNull():
            p.drawPixmap(QPointF(face.center().x() - size / 2.0,
                                 face.center().y() - size / 2.0), pix)
        p.restore()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(_LUMI_TEAL), 2.0))
        p.drawEllipse(r.adjusted(1, 1, -1, -1))
        if self._pulse > 0:
            grow = ring * self._pulse
            c = QColor(_LUMI_TEAL)
            c.setAlphaF(max(0.0, 0.8 * (1.0 - self._pulse)))
            p.setPen(QPen(c, 2.0))
            p.drawEllipse(r.adjusted(-grow, -grow, grow, grow))
        if self.hasFocus():
            p.setPen(QPen(QColor(theme.NEUTRAL[900]), 2.0))
            p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))


# ── FULL FLOATING OVERLAY COORDINATOR ───────────────────────────────────────
class LumiOverlay(QWidget):
    """Coordinates the edge button and the popup card. The card opens beside
    the button, never over it, so the button stays where the owner put it and
    a second press closes Lumi again."""

    command_requested = Signal(str)

    def __init__(self, host: QWidget, support_panel: QWidget):
        super().__init__(host)
        self._host = host
        self._support_panel = support_panel
        self.setFixedSize(1, 1)

        self._launcher = LumiEdgeButton(host)
        self._launcher.toggle_requested.connect(self.toggle)
        self._launcher.tucked_changed.connect(lambda _t: self.reposition())

        self._card = LumiCard(support_panel, host)
        self._card.minimize_requested.connect(self.close)
        self._card.close_requested.connect(self.close)
        self._card.expand_toggled.connect(lambda _: self.reposition())
        self._card.command_requested.connect(self.command_requested.emit)
        if hasattr(support_panel, "command_requested"):
            support_panel.command_requested.connect(self.command_requested.emit)

        self._card_anim: Optional[QVariantAnimation] = None
        self._is_closing = False

        self._card.hide()
        self.reposition()

        # Follow host resizing automatically
        self._host.installEventFilter(self)

    @property
    def button(self) -> LumiEdgeButton:
        return self._launcher

    def eventFilter(self, watched, event):
        if watched == self._host and event.type() == QEvent.Resize:
            self.reposition()
        return super().eventFilter(watched, event)

    def celebrate(self, duration_ms: int = 3500):
        """A finished task or a sent quote: one pulse of the button."""
        self._launcher.trigger_celebration(duration_ms)
        if hasattr(self._card, "_welcome_header") and hasattr(self._card._welcome_header, "set_mode"):
            self._card._welcome_header.set_mode("waving")

    def is_open(self) -> bool:
        return self._card.isVisible() and not self._is_closing

    def open(self):
        if self._card_anim and self._card_anim.state() == QVariantAnimation.Running:
            self._card_anim.stop()

        self._is_closing = False
        self._launcher.set_card_open(True)
        self._launcher._hide_label()
        self.reposition()

        if not _effects_on():
            self._card.show()
            self._card.raise_()
            self._launcher.raise_()
            return

        # Slide the card in from the edge it is docked to.
        target_x = self._card.x()
        cy = self._card.y()
        start_x = target_x + 40

        self._card.move(start_x, cy)
        self._card.show()
        self._card.raise_()
        self._launcher.raise_()

        anim = QVariantAnimation(self)
        anim.setDuration(240)
        anim.setStartValue(start_x)
        anim.setEndValue(target_x)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _step(val):
            self._card.move(int(val), cy)

        def _done():
            self._card.move(target_x, cy)
            if hasattr(self._card, "_welcome_header") and hasattr(self._card._welcome_header, "set_mode"):
                self._card._welcome_header.set_mode("waving")

        anim.valueChanged.connect(_step)
        anim.finished.connect(_done)
        self._card_anim = anim
        anim.start()

    def close(self):
        if self._card_anim and self._card_anim.state() == QVariantAnimation.Running:
            self._card_anim.stop()

        if not _effects_on() or not self._card.isVisible():
            self._is_closing = False
            self._card.hide()
            self._launcher.set_card_open(False)
            return

        self._is_closing = True
        cy = self._card.y()
        start_x = self._card.x()

        anim = QVariantAnimation(self)
        anim.setDuration(200)
        anim.setStartValue(start_x)
        anim.setEndValue(start_x + 40)
        anim.setEasingCurve(QEasingCurve.InCubic)

        def _step(val):
            self._card.move(int(val), cy)

        def _done():
            self._card.hide()
            self._is_closing = False
            self._launcher.set_card_open(False)
            self.reposition()

        anim.valueChanged.connect(_step)
        anim.finished.connect(_done)
        self._card_anim = anim
        anim.start()

    def toggle(self):
        if self.is_open():
            self.close()
        else:
            self.open()

    def reposition(self):
        area = self._host.rect()
        edge = 24
        gap = theme.SPACE_3

        self._launcher.reposition()
        b = self._launcher.geometry()

        cw = self._card.width()
        ch = self._card.height()
        # Right edge just left of the button (or the tucked tab).
        cx = max(edge, b.x() - gap - cw)
        # Bottom level with the button's bottom, kept inside the window.
        cy = b.y() + b.height() - ch
        cy = max(edge, min(cy, area.height() - edge - ch))
        self._card.move(cx, cy)
