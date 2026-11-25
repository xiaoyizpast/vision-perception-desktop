# -*- coding: utf-8 -*-
"""V2 轨迹视图（Trajectory Plane）。

严格遵循 docs/06 第 6 节 V2 规范：
- 以「图像平面」方式画 foot_path：x=foot_x，y=foot_y，纵轴向下（与画面方向一致）
- 明确标注「图像平面示意，非米制俯视图」
- 多维过滤：类别、置信度下限、分区（near/mid/far）、最短轨迹帧数、ID 搜索
- Hover 高亮折线并弹出详情（id / 类别 / 帧区间 / 样本数 / conf_mean / conf_max）
- 点选轨迹 → 侧栏显示完整信息，支持一键同步 V1 回放台播放头
- tracks == [] 时展示规范空态提示，绝不报错
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from data_loader import SessionBundle
from theme import COLORS
from widgets.common import DisclaimerBanner, SectionCard

TRAJ_CLASS_COLORS = {
    "person": QColor("#38BDF8"),
    "bus": QColor("#F59E0B"),
    "car": QColor("#A855F7"),
    "motorcycle": QColor("#EC4899"),
    "bicycle": QColor("#22C55E"),
}


class TrajectoryPlaneCanvas(QWidget):
    """矢量图像平面轨迹画布（x=foot_x, y=foot_y，纵轴向下）。"""

    trackSelected = Signal(int)
    trackActivated = Signal(int, int)  # (track_id, frame_idx)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        self._session: Optional[SessionBundle] = None
        self._tracks: List[Dict[str, Any]] = []
        self._selected_id: Optional[int] = None
        self._hover_id: Optional[int] = None
        self._current_frame: int = 0

        self._plane_rect = QRectF()
        self._scale = 1.0
        self._vw = 720
        self._vh = 1280
        self._screen_paths: List[Tuple[int, List[Tuple[int, float, float]]]] = []

    def set_data(self, session: Optional[SessionBundle], tracks: List[Dict[str, Any]]) -> None:
        self._session = session
        self._tracks = tracks
        if session and session.video:
            self._vw = int(session.video["width"])
            self._vh = int(session.video["height"])
        else:
            self._vw, self._vh = 720, 1280
        if self._selected_id not in {int(t["track_id"]) for t in tracks}:
            self._selected_id = None
        self._hover_id = None
        self._rebuild_screen_cache()
        self.update()

    def set_selected_id(self, track_id: Optional[int]) -> None:
        self._selected_id = track_id
        self.update()

    def set_current_frame(self, frame_idx: int) -> None:
        self._current_frame = frame_idx
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rebuild_screen_cache()

    def _compute_plane(self) -> Tuple[QRectF, float]:
        pad_l, pad_r, pad_t, pad_b = 58.0, 28.0, 36.0, 36.0
        avail_w = max(40.0, self.width() - pad_l - pad_r)
        avail_h = max(40.0, self.height() - pad_t - pad_b)
        scale = min(avail_w / max(self._vw, 1), avail_h / max(self._vh, 1))
        pw = self._vw * scale
        ph = self._vh * scale
        ox = pad_l + (avail_w - pw) * 0.5
        oy = pad_t + (avail_h - ph) * 0.5
        return QRectF(ox, oy, pw, ph), scale

    def _rebuild_screen_cache(self) -> None:
        rect, scale = self._compute_plane()
        self._plane_rect = rect
        self._scale = scale
        self._screen_paths.clear()
        for tr in self._tracks:
            tid = int(tr["track_id"])
            pts = tr.get("foot_path") or []
            spts = [(int(p[0]), rect.x() + float(p[1]) * scale, rect.y() + float(p[2]) * scale) for p in pts]
            self._screen_paths.append((tid, spts))

    def _hit_test(self, px: float, py: float, max_dist: float = 10.0) -> Tuple[Optional[int], Optional[int]]:
        best_d = max_dist
        best_tid: Optional[int] = None
        best_frame: Optional[int] = None
        for tid, spts in self._screen_paths:
            for f, sx, sy in spts:
                d = math.hypot(px - sx, py - sy)
                if d < best_d:
                    best_d = d
                    best_tid = tid
                    best_frame = f
        return best_tid, best_frame

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pt = event.position()
        tid, frame = self._hit_test(pt.x(), pt.y())
        if tid != self._hover_id:
            self._hover_id = tid
            self.update()
        if tid is not None and self._session:
            tr = self._session.track_by_id.get(tid)
            if tr:
                tip = (
                    f"轨迹 #{tid}  ({tr.get('class_name', '—')})\n"
                    f"帧区间：{tr['first_frame']} ~ {tr['last_frame']}  ·  样本数 {tr['n']}\n"
                    f"平均置信度：{tr.get('conf_mean', 0):.3f}  |  最高：{tr.get('conf_max', 0):.3f}\n"
                    f"悬停帧：#{frame}（点击选中，双击跳转回放台）"
                )
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            tid, _ = self._hit_test(event.position().x(), event.position().y())
            if tid is not None:
                self._selected_id = tid
                self.trackSelected.emit(tid)
                self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            tid, frame = self._hit_test(event.position().x(), event.position().y())
            if tid is not None:
                self._selected_id = tid
                tr = self._session.track_by_id.get(tid) if self._session else None
                target_f = frame if frame is not None else (int(tr["first_frame"]) if tr else 0)
                self.trackActivated.emit(tid, target_f)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(COLORS["bg_canvas"]))

        rect, scale = self._compute_plane()
        self._plane_rect = rect
        self._scale = scale

        # 画布区域底色与坐标网格（动态跟随浅/深主题）
        painter.setPen(QPen(QColor(COLORS["border_strong"]), 1.5))
        painter.setBrush(QColor(COLORS["bg_canvas_inner"]))
        painter.drawRect(rect)

        grid_pen = QPen(QColor(COLORS["grid_line"]), 1.0, Qt.PenStyle.DotLine)
        painter.setPen(grid_pen)
        f_axis = QFont("Microsoft YaHei UI", 9)
        painter.setFont(f_axis)

        for i in range(1, 4):
            gx = rect.left() + rect.width() * (i / 4.0)
            painter.drawLine(QPointF(gx, rect.top()), QPointF(gx, rect.bottom()))
        for i in range(1, 5):
            gy = rect.top() + rect.height() * (i / 5.0)
            painter.drawLine(QPointF(rect.left(), gy), QPointF(rect.right(), gy))

        # 坐标刻度（原视频像素 px，纵轴向下）
        painter.setPen(QColor(COLORS["text_muted"]))
        painter.drawText(QRectF(rect.left(), rect.top() - 24, rect.width(), 20), Qt.AlignmentFlag.AlignLeft, "X: 0 px")
        painter.drawText(QRectF(rect.left(), rect.top() - 24, rect.width(), 20), Qt.AlignmentFlag.AlignRight, f"{self._vw} px →")
        painter.drawText(QRectF(4, rect.top(), 50, 20), Qt.AlignmentFlag.AlignRight, "0 px")
        painter.drawText(QRectF(4, rect.bottom() - 18, 50, 20), Qt.AlignmentFlag.AlignRight, f"{self._vh} px")
        painter.drawText(QRectF(12, rect.bottom() + 8, self.width() - 24, 22), Qt.AlignmentFlag.AlignCenter, "纵轴向下（与原画面方向一致 · 单位：像素 px，非米制）")

        if self._session:
            zones = self._session.zones
            near_y = rect.top() + float(zones.get("near_line", 0.72)) * rect.height()
            mid_y = rect.top() + float(zones.get("mid_line", 0.45)) * rect.height()

            painter.fillRect(QRectF(rect.left(), near_y, rect.width(), rect.bottom() - near_y), QColor(220, 38, 38, 28))
            painter.fillRect(QRectF(rect.left(), mid_y, rect.width(), near_y - mid_y), QColor(234, 179, 8, 22))

            zpen = QPen(QColor(COLORS["border_strong"]), 1.4, Qt.PenStyle.DashLine)
            painter.setPen(zpen)
            painter.drawLine(QPointF(rect.left(), mid_y), QPointF(rect.right(), mid_y))
            painter.drawLine(QPointF(rect.left(), near_y), QPointF(rect.right(), near_y))

            painter.setPen(QColor(COLORS["state_s1_text"]))
            painter.drawText(QPointF(rect.left() + 8, mid_y - 6), f"MID ({zones.get('mid_line', 0.45):.2f})")
            painter.setPen(QColor(COLORS["state_s2_text"]))
            painter.drawText(QPointF(rect.left() + 8, near_y - 6), f"NEAR ({zones.get('near_line', 0.72):.2f})")

        # 空态处理
        if not self._tracks:
            painter.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.Bold))
            painter.setPen(QColor(COLORS["text_secondary"]))
            msg = "当前会话暂无已确认轨迹（tracks == []）" if (not self._session or not self._session.tracks) else "当前筛选条件下无匹配轨迹"
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, msg)
            return

        # 绘制所有普通轨迹，再绘制悬停/选中轨迹置顶
        painter.save()
        painter.setClipRect(rect)

        ordered = sorted(
            self._tracks,
            key=lambda t: (int(t["track_id"]) == self._selected_id, int(t["track_id"]) == self._hover_id),
        )
        for tr in ordered:
            tid = int(tr["track_id"])
            pts = tr.get("foot_path") or []
            if not pts:
                continue
            is_sel = (tid == self._selected_id)
            is_hov = (tid == self._hover_id)
            col = QColor(TRAJ_CLASS_COLORS.get(tr.get("class_name", ""), QColor("#38BDF8")))
            col.setAlphaF(0.95 if (is_sel or is_hov) else 0.35)

            pen = QPen(col, 3.2 if is_sel else (2.6 if is_hov else 1.7))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            if len(pts) == 1:
                sx = rect.x() + float(pts[0][1]) * scale
                sy = rect.y() + float(pts[0][2]) * scale
                painter.setBrush(col)
                painter.drawEllipse(QPointF(sx, sy), 4.0, 4.0)
            else:
                path = QPainterPath(QPointF(rect.x() + float(pts[0][1]) * scale, rect.y() + float(pts[0][2]) * scale))
                for p in pts[1:]:
                    path.lineTo(QPointF(rect.x() + float(p[1]) * scale, rect.y() + float(p[2]) * scale))
                painter.drawPath(path)

            if is_sel or is_hov:
                # 起止点标记 + 标签
                s0x, s0y = rect.x() + float(pts[0][1]) * scale, rect.y() + float(pts[0][2]) * scale
                s1x, s1y = rect.x() + float(pts[-1][1]) * scale, rect.y() + float(pts[-1][2]) * scale
                painter.setPen(QPen(QColor("#FFFFFF"), 1.5))
                painter.setBrush(QColor("#22C55E"))
                painter.drawEllipse(QPointF(s0x, s0y), 5.0, 5.0)
                painter.setBrush(QColor("#EF4444"))
                painter.drawEllipse(QPointF(s1x, s1y), 5.0, 5.0)
                painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
                painter.setPen(QColor(COLORS["text_primary"]))
                painter.drawText(QPointF(s1x + 8, s1y + 4), f"#{tid} ({tr.get('class_name','')})")

            # 若当前 V1 播放帧恰好落在该轨迹上，绘出当前时刻位置点
            for p in pts:
                if int(p[0]) == self._current_frame:
                    cx = rect.x() + float(p[1]) * scale
                    cy = rect.y() + float(p[2]) * scale
                    painter.setPen(QPen(QColor("#FFFFFF"), 2.0))
                    painter.setBrush(QColor("#38BDF8") if not is_sel else QColor("#FACC15"))
                    painter.drawEllipse(QPointF(cx, cy), 6.0 if is_sel else 4.5, 6.0 if is_sel else 4.5)
                    break

        painter.restore()


class TrajectoryView(QWidget):
    """V2 轨迹视图完整页面。"""

    jumpToPlayback = Signal(int, int)  # (track_id, frame_idx)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._session: Optional[SessionBundle] = None
        self._track_zones: Dict[int, Set[str]] = {}
        self._filtered: List[Dict[str, Any]] = []
        self._selected_id: Optional[int] = None
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(10)

        # 强制标注：图像平面示意，非米制俯视图
        outer.addWidget(
            DisclaimerBanner("图像平面示意（x = foot_x，y = foot_y，纵轴向下，单位 px），非米制俯视图。轨迹数 ≠ 人数；id = -1 未确认样本不计入轨迹。")
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # 左侧过滤栏
        left_card = SectionCard("轨迹过滤器")
        left_card.setMinimumWidth(245)

        left_card.root_layout.addWidget(QLabel("类别筛选"))
        self._cmb_cls = QComboBox()
        self._cmb_cls.currentIndexChanged.connect(self._apply_filters)
        left_card.root_layout.addWidget(self._cmb_cls)

        left_card.root_layout.addWidget(QLabel("途经分区筛选"))
        self._cmb_zone = QComboBox()
        self._cmb_zone.addItems(["全部分区", "含近场 (near)", "含中场 (mid)", "含远场 (far)"])
        self._cmb_zone.currentIndexChanged.connect(self._apply_filters)
        left_card.root_layout.addWidget(self._cmb_zone)

        left_card.root_layout.addWidget(QLabel("平均置信度下限"))
        self._spn_conf = QDoubleSpinBox()
        self._spn_conf.setRange(0.0, 1.0)
        self._spn_conf.setSingleStep(0.05)
        self._spn_conf.setDecimals(2)
        self._spn_conf.setValue(0.0)
        self._spn_conf.valueChanged.connect(self._apply_filters)
        left_card.root_layout.addWidget(self._spn_conf)

        left_card.root_layout.addWidget(QLabel("最短轨迹帧数（样本数 n）"))
        self._spn_min_n = QSpinBox()
        self._spn_min_n.setRange(1, 2000)
        self._spn_min_n.setValue(1)
        self._spn_min_n.valueChanged.connect(self._apply_filters)
        left_card.root_layout.addWidget(self._spn_min_n)

        left_card.root_layout.addWidget(QLabel("按轨迹 ID 搜索"))
        self._txt_search = QLineEdit()
        self._txt_search.setPlaceholderText("输入数字，如 46")
        self._txt_search.textChanged.connect(self._apply_filters)
        left_card.root_layout.addWidget(self._txt_search)

        btn_reset = QPushButton("重置所有筛选")
        btn_reset.clicked.connect(self._reset_filters)
        left_card.root_layout.addWidget(btn_reset)

        self._lbl_filter_stat = QLabel("已显示 0 / 0 条轨迹")
        self._lbl_filter_stat.setObjectName("PillAccent")
        self._lbl_filter_stat.setWordWrap(True)
        left_card.root_layout.addWidget(self._lbl_filter_stat)

        left_card.root_layout.addStretch(1)
        splitter.addWidget(left_card)

        # 中间轨迹画布
        canvas_card = QFrame()
        canvas_card.setObjectName("Card")
        cl = QVBoxLayout(canvas_card)
        cl.setContentsMargins(8, 8, 8, 8)
        self._canvas = TrajectoryPlaneCanvas()
        self._canvas.trackSelected.connect(self._on_track_selected)
        self._canvas.trackActivated.connect(lambda tid, f: self.jumpToPlayback.emit(tid, f))
        cl.addWidget(self._canvas, 1)
        splitter.addWidget(canvas_card)

        # 右侧详情与列表
        right_w = QWidget()
        right_w.setMinimumWidth(340)
        right_box = QVBoxLayout(right_w)
        right_box.setContentsMargins(4, 0, 0, 0)
        right_box.setSpacing(10)

        detail_card = SectionCard("选中轨迹详情")
        detail_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._lbl_detail = QLabel("请在画布或下方列表中点选一条轨迹。\n（悬停可快速预览，双击同步回放台）")
        self._lbl_detail.setObjectName("SubText")
        self._lbl_detail.setWordWrap(True)
        self._lbl_detail.setMinimumHeight(96)
        self._lbl_detail.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        detail_card.root_layout.addWidget(self._lbl_detail)

        sync_row = QHBoxLayout()
        sync_row.setSpacing(8)
        self._btn_jump_first = QPushButton("跳至首帧 (V1)")
        self._btn_jump_first.setObjectName("PrimaryBtn")
        self._btn_jump_first.setEnabled(False)
        self._btn_jump_first.clicked.connect(lambda: self._jump_selected(first=True))
        self._btn_jump_last = QPushButton("跳至末帧 (V1)")
        self._btn_jump_last.setEnabled(False)
        self._btn_jump_last.clicked.connect(lambda: self._jump_selected(first=False))
        sync_row.addWidget(self._btn_jump_first)
        sync_row.addWidget(self._btn_jump_last)
        detail_card.root_layout.addLayout(sync_row)
        right_box.addWidget(detail_card)

        list_card = SectionCard("轨迹索引列表")
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["ID", "类别", "帧区间", "n", "均置信"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.cellClicked.connect(self._on_table_clicked)
        self._table.cellDoubleClicked.connect(self._on_table_double_clicked)
        list_card.root_layout.addWidget(self._table, 1)
        right_box.addWidget(list_card, 1)

        splitter.addWidget(right_w)
        splitter.setSizes([260, 660, 400])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        outer.addWidget(splitter, 1)

    def refresh_theme(self) -> None:
        self._canvas.update()

    def set_session(self, session: Optional[SessionBundle]) -> None:
        self._session = session
        self._selected_id = None
        self._track_zones.clear()

        self._cmb_cls.blockSignals(True)
        self._cmb_cls.clear()
        self._cmb_cls.addItem("全部类别")

        if session:
            vh = float((session.video or {}).get("height") or 1280.0)
            near_line = float(session.zones.get("near_line", 0.72))
            mid_line = float(session.zones.get("mid_line", 0.45))
            classes = sorted({str(t.get("class_name", "")) for t in session.tracks if t.get("class_name")})
            for c in classes:
                self._cmb_cls.addItem(c)
            for tr in session.tracks:
                tid = int(tr["track_id"])
                zset: Set[str] = set()
                for p in tr.get("foot_path") or []:
                    norm_y = float(p[2]) / max(vh, 1.0)
                    if norm_y > near_line:
                        zset.add("near")
                    elif norm_y > mid_line:
                        zset.add("mid")
                    else:
                        zset.add("far")
                self._track_zones[tid] = zset
        self._cmb_cls.blockSignals(False)
        self._reset_filters()

    def set_current_frame(self, frame_idx: int) -> None:
        self._canvas.set_current_frame(frame_idx)

    def select_track(self, track_id: int) -> None:
        self._selected_id = track_id
        self._canvas.set_selected_id(track_id)
        self._on_track_selected(track_id)

    def _reset_filters(self) -> None:
        self._cmb_cls.setCurrentIndex(0)
        self._cmb_zone.setCurrentIndex(0)
        self._spn_conf.setValue(0.0)
        self._spn_min_n.setValue(1)
        self._txt_search.clear()
        self._apply_filters()

    def _apply_filters(self) -> None:
        if not self._session:
            self._filtered = []
            self._canvas.set_data(None, [])
            self._populate_table([])
            self._lbl_filter_stat.setText("未加载会话")
            return

        cls_filter = self._cmb_cls.currentText()
        zone_idx = self._cmb_zone.currentIndex()
        zone_map = {1: "near", 2: "mid", 3: "far"}
        req_zone = zone_map.get(zone_idx)
        min_conf = self._spn_conf.value()
        min_n = self._spn_min_n.value()
        search_txt = self._txt_search.text().strip()

        out: List[Dict[str, Any]] = []
        for tr in self._session.tracks:
            tid = int(tr.get("track_id", -1))
            if tid < 0:
                continue
            if cls_filter != "全部类别" and tr.get("class_name") != cls_filter:
                continue
            if req_zone and req_zone not in self._track_zones.get(tid, set()):
                continue
            if float(tr.get("conf_mean", 0.0)) < min_conf:
                continue
            if int(tr.get("n", 0)) < min_n:
                continue
            if search_txt and search_txt not in str(tid):
                continue
            out.append(tr)

        self._filtered = out
        self._canvas.set_data(self._session, out)
        self._populate_table(out)
        self._lbl_filter_stat.setText(f"已显示 {len(out)} / {len(self._session.tracks)} 条已确认轨迹")

    def _populate_table(self, tracks: List[Dict[str, Any]]) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(tracks))
        for r, tr in enumerate(tracks):
            tid = int(tr["track_id"])
            it_id = QTableWidgetItem()
            it_id.setData(Qt.ItemDataRole.DisplayRole, tid)
            it_cls = QTableWidgetItem(str(tr.get("class_name", "—")))
            it_rng = QTableWidgetItem(f"{tr['first_frame']}-{tr['last_frame']}")
            it_n = QTableWidgetItem()
            it_n.setData(Qt.ItemDataRole.DisplayRole, int(tr.get("n", 0)))
            it_c = QTableWidgetItem(f"{float(tr.get('conf_mean', 0.0)):.3f}")
            for c, item in enumerate([it_id, it_cls, it_rng, it_n, it_c]):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, item)
        self._table.setSortingEnabled(True)

    def _on_track_selected(self, track_id: int) -> None:
        self._selected_id = track_id
        if not self._session or track_id not in self._session.track_by_id:
            self._btn_jump_first.setEnabled(False)
            self._btn_jump_last.setEnabled(False)
            return
        tr = self._session.track_by_id[track_id]
        fps = max(self._session.fps, 1e-6)
        t0 = tr["first_frame"] / fps
        t1 = tr["last_frame"] / fps
        z_names = {"near": "近场", "mid": "中场", "far": "远场"}
        zones_txt = " / ".join(z_names[z] for z in ["near", "mid", "far"] if z in self._track_zones.get(track_id, set())) or "—"
        self._lbl_detail.setText(
            f"轨迹 ID：#{track_id}    类别：{tr.get('class_name', '—')}\n"
            f"帧区间：{tr['first_frame']} ~ {tr['last_frame']}（{t0:.2f}s ~ {t1:.2f}s）\n"
            f"样本数 n：{tr.get('n', 0)}\n"
            f"置信度：均值 {float(tr.get('conf_mean', 0)):.3f}  |  最高 {float(tr.get('conf_max', 0)):.3f}\n"
            f"途经分区：{zones_txt}（画面下沿占比）"
        )
        self._btn_jump_first.setEnabled(True)
        self._btn_jump_last.setEnabled(True)

    def _on_table_clicked(self, row: int, _col: int) -> None:
        item = self._table.item(row, 0)
        if item:
            tid = int(item.data(Qt.ItemDataRole.DisplayRole))
            self._canvas.set_selected_id(tid)
            self._on_track_selected(tid)

    def _on_table_double_clicked(self, row: int, _col: int) -> None:
        item = self._table.item(row, 0)
        if item:
            tid = int(item.data(Qt.ItemDataRole.DisplayRole))
            self._selected_id = tid
            self._jump_selected(first=True)

    def _jump_selected(self, first: bool) -> None:
        if not self._session or self._selected_id is None:
            return
        tr = self._session.track_by_id.get(self._selected_id)
        if not tr:
            return
        frame = int(tr["first_frame"] if first else tr["last_frame"])
        self.jumpToPlayback.emit(self._selected_id, frame)
