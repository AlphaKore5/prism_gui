"""Terms of Use / Privacy Policy, read from inside the app — no network
needed, and no risk of the in-app copy drifting from what a customer agreed
to (the bundled file IS the one on paths.resource(), not a link that can
404 or point at whichever version happens to be live on the website today).

QTextBrowser.setMarkdown() is used deliberately instead of
widgets/markdown.py's render_markdown() — that renderer is built for
freeform LLM chat prose and has no table support, and both TERMS_OF_USE.md
and PRIVACY_POLICY.md lean on markdown tables for the data-collected /
seat-limits summaries. Qt's own Markdown-to-rich-text conversion (Qt 5.14+)
handles tables, and this content is fixed, reviewed English — not
translated text — so i18n.install() deliberately leaves setMarkdown()
alone (see i18n.py's own docstring on that).

The page is laid out as a reader, not a text dump: a contents list on the left
(click a section, the document scrolls to it; the section you are in is marked
as you scroll), the document typeset on the right, and the document's own
status note — "draft, not yet reviewed" — kept visible as a notice above it
rather than as a grey quote buried in the text. Nothing in the file is
dropped: the notice and the title/date line are lifted out of the body only
to be shown somewhere better.
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextLength
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)

import i18n
import paths
import theme
from dialogs.base import PrismDialog
from widgets import controls as C

_TITLE = re.compile(r"^#\s+(.*)$", re.M)
_NOTICE = re.compile(r"(?:^>.*\n?)+", re.M)
_META = re.compile(r"^\*\*Effective date:\*\*.*$", re.M)
_SECTION = re.compile(r"^(\d+)\.\s+(.*)$")


def split_document(text: str) -> dict:
    """Lift the title, the status note and the date line out of the body.

    Returns {"title", "notice", "meta", "body"}; every part is optional and a
    file that has none of them comes back whole in "body"."""
    title = notice = meta = ""
    m = _TITLE.search(text)
    if m and text[:m.start()].strip() == "":
        title = m.group(1).strip()
        text = text[:m.start()] + text[m.end():]
    m = _NOTICE.search(text)
    if m and text[:m.start()].strip() == "":
        notice = " ".join(
            line.lstrip("> ").strip() for line in m.group(0).splitlines())
        notice = re.sub(r"[*`]", "", notice)
        text = text[:m.start()] + text[m.end():]
    m = _META.search(text)
    if m:
        meta = re.sub(r"\*\*|\[|\]", "", m.group(0)).strip()
        text = text[:m.start()] + text[m.end():]
    # The "---" rules between sections add nothing once headings are styled.
    text = re.sub(r"^\s*---\s*$", "", text, flags=re.M)
    return {"title": title, "notice": notice, "meta": meta, "body": text.strip()}


class LegalDialog(PrismDialog):
    def __init__(self, title: str, resource_name: str, parent=None):
        parts = split_document(self._load(resource_name))
        super().__init__(title, parts["meta"], icon="lock" if "rivacy" in title else "book", parent=parent,
                         scrollable=False, closable=True)
        self.resize(1040, 720)
        self.setMinimumSize(760, 520)
        self._sections: list[tuple[str, int]] = []   # (heading, block number)

        if parts["notice"]:
            self.body.addWidget(self._notice(parts["notice"]))

        row = QHBoxLayout()
        row.setSpacing(theme.SPACE_4)
        self.body.addLayout(row, stretch=1)

        self.toc = QListWidget()
        self.toc.setObjectName("legalToc")
        self.toc.setFixedWidth(250)
        self.toc.setFocusPolicy(Qt.NoFocus)
        self.toc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.toc.setWordWrap(True)
        self.toc.setStyleSheet(
            "#legalToc { background: transparent; border: none; outline: 0;"
            " font-size: 13px; }"
            "#legalToc::item { padding: 7px 10px; border-radius: 8px;"
            f" color: {theme.NEUTRAL[600]}; }}"
            f"#legalToc::item:hover {{ background: {theme.NEUTRAL[100]}; }}"
            f"#legalToc::item:selected {{ background: {theme.NEUTRAL[200]};"
            f" color: {theme.TEXT}; font-weight: 700; }}")
        row.addWidget(self.toc)

        page = QFrame()
        page.setObjectName("legalPage")
        page.setStyleSheet(
            "#legalPage { background: #ffffff; border: 1px solid "
            f"{theme.NEUTRAL[200]}; border-radius: 12px; }}")
        pl = QVBoxLayout(page)
        pl.setContentsMargins(2, 2, 2, 2)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.view.setFrameShape(QFrame.NoFrame)
        self.view.viewport().setStyleSheet("background: transparent;")
        self.view.setMarkdown(parts["body"])
        self._typeset()
        pl.addWidget(self.view)
        row.addWidget(page, stretch=1)

        for heading, _block in self._sections:
            self.toc.addItem(QListWidgetItem(heading))
        self.toc.currentRowChanged.connect(self._jump)
        self.view.verticalScrollBar().valueChanged.connect(self._follow)
        if self._sections:
            self.toc.setCurrentRow(0)

        self.footer.add_secondary(
            self.button(i18n.t("Close"), on_click=self.accept))

    # ── pieces ─────────────────────────────────────────────────────────

    @staticmethod
    def _notice(text: str) -> QWidget:
        bar = QFrame()
        bar.setObjectName("legalNotice")
        bar.setStyleSheet(
            f"#legalNotice {{ background: {theme.WARN_BG};"
            f" border: 1px solid {theme.WARN}; border-radius: 10px; }}"
            "QLabel { background: transparent; border: none; }")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        mark = QLabel("!")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(22, 22)
        mark.setStyleSheet(
            f"background: {theme.WARN} !important; color: white;"
            " border-radius: 11px; font-weight: 800;")
        lay.addWidget(mark, 0, Qt.AlignTop)
        short = text if len(text) < 190 else text[:text.find(". ", 60) + 1] or text
        label = QLabel(short)
        label.setWordWrap(True)
        label.setToolTip(text)
        label.setStyleSheet(f"color: {theme.WARN_INK}; font-size: 12.5px;")
        lay.addWidget(label, 1)
        return bar

    def _typeset(self):
        """Give the converted Markdown real typography: a readable measure and
        line height, headings that rank, tables with a header row."""
        doc = self.view.document()
        doc.setDocumentMargin(34)
        base = QFont(theme.FONT_BODY)
        base.setPixelSize(14)
        doc.setDefaultFont(base)
        ink = QColor(theme.NEUTRAL[800])
        quiet = QColor(theme.NEUTRAL[500])
        cur = QTextCursor(doc)
        block = doc.begin()
        number = 0
        while block.isValid():
            cur.setPosition(block.position())
            cur.select(QTextCursor.BlockUnderCursor)
            level = block.blockFormat().headingLevel()
            bf = QTextBlockFormat(block.blockFormat())
            cf = QTextCharFormat()
            cf.setForeground(ink)
            if level:
                heading = block.text().strip()
                bf.setTopMargin(26 if level <= 2 else 16)
                bf.setBottomMargin(8)
                bf.setLineHeight(120, QTextBlockFormat.ProportionalHeight.value)
                f = QFont(theme.FONT_HEADING)
                f.setPixelSize({1: 30, 2: 24}.get(level, 18))
                f.setWeight(QFont.Bold)
                cf.setFont(f)
                cf.setForeground(QColor(theme.TEXT))
                if level == 2:
                    self._sections.append((heading, block.blockNumber()))
            else:
                bf.setLineHeight(156, QTextBlockFormat.ProportionalHeight.value)
                if not block.textList():
                    bf.setBottomMargin(10)
                else:
                    bf.setBottomMargin(5)
                if block.blockFormat().hasProperty(
                        QTextBlockFormat.BlockQuoteLevel):
                    cf.setForeground(quiet)
            cur2 = QTextCursor(block)
            cur2.setBlockFormat(bf)
            cur2.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cur2.mergeCharFormat(cf)
            number += 1
            block = block.next()
        self._style_tables(doc)

    def _style_tables(self, doc):
        from PySide6.QtGui import QTextTable
        root = doc.rootFrame()
        for frame in root.childFrames():
            if not isinstance(frame, QTextTable):
                continue
            fmt = frame.format()
            fmt.setBorder(1)
            fmt.setBorderStyle(fmt.BorderStyle.BorderStyle_Solid)
            fmt.setBorderBrush(QColor(theme.NEUTRAL[300]))
            fmt.setCellPadding(8)
            fmt.setCellSpacing(0)
            fmt.setBorderCollapse(True) if hasattr(fmt, 'setBorderCollapse') else None
            fmt.setTopMargin(6)
            fmt.setBottomMargin(14)
            fmt.setWidth(QTextLength(QTextLength.PercentageLength, 100))
            frame.setFormat(fmt)
            for r in range(frame.rows()):
                for c in range(frame.columns()):
                    cell = frame.cellAt(r, c)
                    cf = cell.format().toTableCellFormat()
                    cf.setBorder(1)
                    cf.setBorderBrush(QColor(theme.NEUTRAL[200]))
                    if r == 0:
                        cf.setBackground(QColor(theme.NEUTRAL[100]))
                    cell.setFormat(cf)

    # ── navigation ─────────────────────────────────────────────────────

    def _block_top(self, number: int) -> int:
        doc = self.view.document()
        block = doc.findBlockByNumber(number)
        return int(doc.documentLayout().blockBoundingRect(block).top())

    def _jump(self, row: int):
        if not 0 <= row < len(self._sections):
            return
        bar = self.view.verticalScrollBar()
        # Scrolling here moves the document; _follow must not bounce the list.
        self._jumping = True
        bar.setValue(max(self._block_top(self._sections[row][1]) - 8, 0))
        self._jumping = False

    _jumping = False

    def _follow(self, value: int):
        if self._jumping or not self._sections:
            return
        at = value + 40
        row = 0
        for i, (_h, block) in enumerate(self._sections):
            if self._block_top(block) <= at:
                row = i
        if row != self.toc.currentRow():
            self.toc.blockSignals(True)
            self.toc.setCurrentRow(row)
            self.toc.blockSignals(False)

    @staticmethod
    def _load(resource_name: str) -> str:
        path = paths.resource(resource_name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            # A build missing its own legal text is a packaging bug, not a
            # crash the customer should see — degrade to a clear pointer
            # rather than an empty dialog or a traceback.
            return (f"_Could not load `{resource_name}` from this build. "
                    f"See it online instead: alphakore.org_")
