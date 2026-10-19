"""The flow as a picture: each step a card you can drag, each way out of a step a line to the next one.

It edits the SAME flow as the list of steps (the graph dict is shared), so switching between the two never loses anything. Where a card sits is kept
beside the steps in `graph["layout"]` ({step: [x, y]}); a step nobody has placed yet is put in a column by how far it is from the start.

    drag a card            move it
    drag from a dot        join that way out to another card (drop on empty space to cancel)
    right-click a dot      cut that line (the flow ends there)
    click a card           open it below to change what it says
    wheel / buttons        zoom; drag the background to pan

No rule about the flow lives here — which steps exist, where each goes — that is flow_model.py. This only draws it and says what the person did.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem, QGraphicsObject, QGraphicsPathItem, QGraphicsScene, QGraphicsView, QMenu)

import i18n
import theme
from addons.whatsapp import flow_model as M

NODE_W = 236
HEAD_H = 26
TEXT_H = 38
ROW_H = 21
PORT_R = 6
GROUPS = {"send_text": "say", "media": "say", "send_location": "say", "template": "say",
          "buttons": "ask", "list": "ask", "ask": "ask", "location_request": "ask",
          "condition": "decide", "delay": "decide",
          "set_attribute": "remember", "add_tag": "remember", "remove_tag": "remember",
          "api_request": "connect", "webhook": "connect", "capi_event": "connect", "jump_flow": "connect",
          "send_products": "sell", "send_form": "sell", "request_payment": "sell",
          "handoff": "hand", "agent": "hand", "end": "hand"}


def group_colour(kind: str) -> str:
    return {"say": theme.ACCENT, "ask": theme.OK_INK, "decide": theme.WARN_INK, "remember": theme.NEUTRAL[600], "connect": "#6d4fc2", "sell": "#b0651a", "hand": theme.ERR_INK}.get(GROUPS.get(kind, ""), theme.NEUTRAL[600])


def node_height(node: dict) -> int:
    return HEAD_H + TEXT_H + ROW_H * len(M.branches(node)) + (8 if M.branches(node) else 4)


class _Port(QGraphicsEllipseItem):
    """The dot at the end of one way out of a step. Drag it to another card to join them."""

    def __init__(self, owner: "NodeItem", branch: dict, index: int):
        super().__init__(-PORT_R, -PORT_R, PORT_R * 2, PORT_R * 2, owner)
        self.owner, self.branch, self.index = owner, branch, index
        self.setZValue(3)
        self.setCursor(Qt.CrossCursor)
        self.setAcceptHoverEvents(True)
        self.setToolTip(i18n.t("Drag to another step to join them. Right-click to cut the line."))
        self._line = None
        self.restyle()

    def restyle(self):
        joined = M.branch_target(self.branch) is not None
        self.setBrush(QBrush(QColor(theme.ACCENT if joined else "#ffffff")))
        self.setPen(QPen(QColor(theme.ACCENT if joined else theme.NEUTRAL[400]), 1.6))

    def centre_in_scene(self) -> QPointF:
        return self.mapToScene(QPointF(0, 0))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._line = QGraphicsPathItem()
            self._line.setPen(QPen(QColor(theme.ACCENT), 2, Qt.DashLine))
            self._line.setZValue(5)
            self.scene().addItem(self._line)
            self._drag(event.scenePos())
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self._line is not None:
            self._drag(event.scenePos())

    def _drag(self, to: QPointF):
        a = self.centre_in_scene()
        path = QPainterPath(a)
        path.cubicTo(a + QPointF(60, 0), to - QPointF(60, 0), to)
        self._line.setPath(path)

    def mouseReleaseEvent(self, event):
        if self._line is None:
            return
        scene = self.scene()
        scene.removeItem(self._line)
        self._line = None
        for item in scene.items(event.scenePos()):
            node = item if isinstance(item, NodeItem) else item.parentItem() if isinstance(item.parentItem(), NodeItem) else None
            if node is not None and node is not self.owner:
                self.owner.canvas.join(self.owner.nid, self.branch, node.nid)
                return

    def contextMenuEvent(self, event):
        if M.branch_target(self.branch) is None:
            return
        menu = QMenu()
        menu.addAction(i18n.t("Cut this line")).triggered.connect(lambda: self.owner.canvas.join(self.owner.nid, self.branch, None))
        menu.exec(event.screenPos())


class NodeItem(QGraphicsObject):
    """One step: a coloured edge, its kind and name, what it says, and a dot for each way out."""

    def __init__(self, canvas: "FlowCanvas", nid: str, node: dict):
        super().__init__()
        self.canvas, self.nid, self.node = canvas, nid, node
        self.problem = False
        self.is_entry = False
        self.home = [0, 0]                                                  # where it was last drawn or put, to tell a click from a move
        self.ports: list = []
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setCursor(Qt.OpenHandCursor)
        self.rebuild()

    def height(self) -> int:
        return node_height(self.node)

    def boundingRect(self) -> QRectF:
        return QRectF(-2, -2, NODE_W + 4, self.height() + 4)

    def rebuild(self):
        self.prepareGeometryChange()
        for p in self.ports:
            p.setParentItem(None)
            if p.scene() is not None:
                p.scene().removeItem(p)
        self.ports = []
        for i, b in enumerate(M.branches(self.node)):
            port = _Port(self, b, i)
            port.setPos(NODE_W, HEAD_H + TEXT_H + ROW_H * i + ROW_H / 2 + 2)
            self.ports.append(port)
        self.setToolTip("%s — %s" % (M.type_name(self.node.get("type")), M.describe_step(self.node)))
        self.update()

    def in_point(self) -> QPointF:
        return self.mapToScene(QPointF(0, HEAD_H / 2))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.canvas.node_moved(self)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.canvas.placed(self)

    def paint(self, p: QPainter, _option, _widget=None):
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0, 0, NODE_W, self.height())
        selected = self.isSelected()
        edge = QColor(theme.ERR_INK if self.problem else theme.ACCENT if selected else theme.NEUTRAL[300])
        p.setPen(QPen(edge, 2.0 if (selected or self.problem) else 1.2))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRoundedRect(rect, 10, 10)
        stripe = QPainterPath()
        stripe.addRoundedRect(QRectF(0, 0, 6, rect.height()), 3, 3)
        p.fillPath(stripe, QColor(group_colour(self.node.get("type"))))
        small = QFont(theme.FONT_BODY)
        small.setPixelSize(10)
        small.setBold(True)
        body = QFont(theme.FONT_BODY)
        body.setPixelSize(12)
        p.setFont(small)
        p.setPen(QColor(theme.NEUTRAL[600]))
        p.drawText(QRectF(14, 4, NODE_W - 20 - (60 if self.is_entry else 0), HEAD_H - 6), Qt.AlignVCenter | Qt.AlignLeft,
                   ("%s · %s" % (M.type_name(self.node.get("type")), self.nid)).upper())
        if self.is_entry:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.OK_INK))
            p.drawRoundedRect(QRectF(NODE_W - 58, 6, 48, 15), 7, 7)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRectF(NODE_W - 58, 6, 48, 15), Qt.AlignCenter, i18n.t("START"))
        p.setFont(body)
        p.setPen(QColor(theme.TEXT))
        text = M.describe_step(self.node) or ""
        fm = QFontMetrics(body)
        p.drawText(QRectF(14, HEAD_H, NODE_W - 24, TEXT_H - 2), Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap, fm.elidedText(text, Qt.ElideRight, (NODE_W - 24) * 2 - 12))
        tiny = QFont(theme.FONT_BODY)
        tiny.setPixelSize(11)
        p.setFont(tiny)
        for i, b in enumerate(M.branches(self.node)):
            y = HEAD_H + TEXT_H + ROW_H * i + 2
            joined = M.branch_target(b) is not None
            p.setPen(QColor(theme.NEUTRAL[700] if joined else theme.NEUTRAL[500]))
            label = b["label"] or (i18n.t("Next") if len(self.ports) > 1 else "")
            p.drawText(QRectF(14, y, NODE_W - 32, ROW_H), Qt.AlignVCenter | Qt.AlignRight, QFontMetrics(tiny).elidedText(label, Qt.ElideRight, NODE_W - 40))


class FlowCanvas(QGraphicsView):
    """The picture. `selected(nid)` when a card is clicked (`""` when nothing is), `edited()` when a card moved or two cards were joined or cut."""
    selected = Signal(str)
    edited = Signal()

    def __init__(self, graph: dict, parent=None):
        super().__init__(parent)
        self.graph = graph
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMinimumHeight(260)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setStyleSheet("QGraphicsView { background: rgba(0,0,0,0.025); border: 1px solid %s; border-radius: %dpx; }" % (theme.HAIRLINE, theme.R_CONTROL))
        self.items_: dict = {}
        self.edges: list = []
        self._issues: dict = {}
        self._building = False
        self.scene_.selectionChanged.connect(self._selection)
        self.reload()

    # ── building the picture ─────────────────────────────────────────────────
    def reload(self):
        """Redraw everything from the graph (after the list of steps changed it, or a card was added or removed)."""
        self._building = True
        keep = self.current()
        self.scene_.clear()
        self.items_, self.edges = {}, []
        nodes = self.graph.get("nodes") or {}
        layout = M.auto_layout(self.graph, across=NODE_W + 70, down=30, height=lambda n: node_height(nodes[n]))
        for nid in M.order_of(self.graph):
            item = NodeItem(self, nid, nodes[nid])
            item.setPos(*layout[nid])
            item.home = [round(item.pos().x()), round(item.pos().y())]
            self.scene_.addItem(item)
            self.items_[nid] = item
        self._flags()
        self._edges()
        if keep in self.items_:
            self.items_[keep].setSelected(True)
        self._building = False
        self.scene_.setSceneRect(self.scene_.itemsBoundingRect().adjusted(-80, -60, 160, 120))

    def touch(self, nid: str):
        """One step's words or ways out changed (a button was added, a target chosen): redraw that card and the lines, nothing else."""
        if nid in self.items_:
            self.items_[nid].rebuild()
            self._flags()
            self._edges()

    def refresh(self):
        """A step's words or ways out changed: redraw the cards and lines without losing where they are."""
        for nid, item in self.items_.items():
            item.rebuild()
        self._flags()
        self._edges()

    def _flags(self):
        for nid, item in self.items_.items():
            item.is_entry = self.graph.get("entry") == nid
            item.problem = any(i.get("severity") == "error" for i in self._issues.get(nid, []))
            item.update()
            for p in item.ports:
                p.restyle()

    def set_issues(self, issues: list):
        self._issues = M.issues_by_node(issues)
        self._flags()

    def _edges(self):
        for e in self.edges:
            if e["item"].scene() is not None:
                self.scene_.removeItem(e["item"])
                if e.get("arrow") is not None:
                    self.scene_.removeItem(e["arrow"])
        self.edges = []
        for nid, item in self.items_.items():
            for port in item.ports:
                target = M.branch_target(port.branch)
                if target in self.items_:
                    path_item = QGraphicsPathItem()
                    path_item.setZValue(-1)
                    arrow = self.scene_.addPolygon(QPolygonF(), QPen(Qt.NoPen), QBrush(QColor(theme.NEUTRAL[500])))
                    arrow.setZValue(-1)
                    self.scene_.addItem(path_item)
                    self.edges.append({"item": path_item, "arrow": arrow, "from": nid, "port": port, "to": target})
        self._route()

    def _route(self):
        sel = self.current()
        for e in self.edges:
            a = e["port"].centre_in_scene()
            b = self.items_[e["to"]].in_point()
            dx = max(60.0, abs(b.x() - a.x()) * 0.45)
            path = QPainterPath(a)
            if b.x() >= a.x():
                path.cubicTo(a + QPointF(dx, 0), b - QPointF(dx, 0), b)
            else:                                                          # going back: loop out and round so the line does not run through the cards
                path.cubicTo(a + QPointF(dx + 40, 60), b - QPointF(dx + 40, -60), b)
            hot = sel in (e["from"], e["to"])
            colour = QColor(theme.ACCENT if hot else theme.NEUTRAL[400])
            e["item"].setPath(path)
            e["item"].setPen(QPen(colour, 2.0 if hot else 1.4))
            e["arrow"].setBrush(QBrush(colour))
            e["arrow"].setPolygon(QPolygonF([b, b + QPointF(-9, -5), b + QPointF(-9, 5)]))

    # ── what the cards report ────────────────────────────────────────────────
    def node_moved(self, item: NodeItem):
        if not self._building and self.edges:
            self._route()

    def placed(self, item: NodeItem):
        """A card was let go: remember where."""
        if self._building:
            return
        here = [round(item.pos().x()), round(item.pos().y())]
        if item.home == here:                                               # a click is not a move
            return
        item.home = here
        layout = self.graph.setdefault("layout", {})
        for nid, other in self.items_.items():                              # the first move fixes everyone, so a later change cannot shuffle the rest
            layout.setdefault(nid, [round(other.pos().x()), round(other.pos().y())])
        layout[item.nid] = here
        self.edited.emit()

    def join(self, nid: str, branch: dict, target):
        """Join one way out of a step to another step — or, with None, cut it."""
        if M.branch_target(branch) == target:
            return
        M.set_branch(branch, target)
        self._flags()
        self._edges()
        self.edited.emit()

    def _selection(self):
        if self._building:
            return
        sel = self.current()
        self._route()
        self.selected.emit(sel)

    # ── the person's view ────────────────────────────────────────────────────
    def current(self) -> str:
        items = [i for i in self.scene_.selectedItems() if isinstance(i, NodeItem)]
        return items[0].nid if items else ""

    def select(self, nid: str):
        if nid in self.items_:
            self.scene_.clearSelection()
            self.items_[nid].setSelected(True)
            self.centerOn(self.items_[nid])

    def position(self, nid: str) -> list:
        i = self.items_[nid]
        return [round(i.pos().x()), round(i.pos().y())]

    def arrange(self):
        """Forget where cards were put by hand and lay them out again from the start."""
        self.graph.pop("layout", None)
        self.reload()
        for nid in self.items_:
            self.graph.setdefault("layout", {})[nid] = self.position(nid)
        self.fit()
        self.edited.emit()

    def zoom(self, factor: float):
        z = self.transform().m11() * factor
        if 0.3 <= z <= 2.0:
            self.scale(factor, factor)

    def fit(self):
        rect = self.scene_.itemsBoundingRect()
        if rect.isValid():
            self.fitInView(rect.adjusted(-30, -30, 30, 30), Qt.KeepAspectRatio)
            if self.transform().m11() > 1.0:
                self.resetTransform()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
        else:
            super().wheelEvent(event)
