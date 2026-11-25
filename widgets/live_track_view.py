# -*- coding: utf-8 -*-
"""V6 视频导入与实时追踪视图（Live Video Upload & Tracking）。

能力：
- 支持点击选择或直接拖放任意大小本地视频（.mp4 / .mov / .avi / .mkv），不受 20MB 限制；
- 支持可选切换本地摄像头实时流验证；
- 自动发现 vproj/weights/*.pt（默认 yolo26s.pt）并支持选择自定义权重；
- 边推理边实时渲染检测框、轨迹 ID、脚点、近/中场分区线、近期轨迹尾迹与 S0/S1/S2 状态 HUD；
- 追踪完成后自动导出标准 session.json + 16 列 CSV 至程序同级 user_sessions/ 目录，
  一键导入 V1 回放台与 V2 轨迹视图复盘（绝不改动上游源目录）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from inference_worker import LiveTrackingWorker, MID_LINE, NEAR_LINE, TrackTaskConfig
from theme import COLORS
from widgets.common import DisclaimerBanner, SectionCard

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm"}
TRAIL_COLORS = {
    "person": QColor("#38BDF8"),
    "bus": QColor("#F59E0B"),
    "car": QColor("#A855F7"),
    "motorcycle": QColor("#EC4899"),
    "bicycle": QColor("#22C55E"),
}


class LiveOverlayCanvas(QWidget):
    """实时追踪帧与叠加层渲染画布（支持直接拖放本地视频文件）。"""

    videoDropped = Signal(Path)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(300, 340)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True)

        self._qimg: Optional[QImage] = None
        self._vw: int = 720
        self._vh: int = 1280
        self._frame_info: Dict[str, Any] = {}
        self._samples: List[Dict[str, Any]] = []
        self._trails: Dict[int, List[Tuple[int, float, float]]] = {}
        self._dragging_file: bool = False

        self.show_zones: bool = True
        self.show_trails: bool = True
        self.show_foot: bool = True

    def clear_frame(self) -> None:
        self._qimg = None
        self._frame_info = {}
        self._samples = []
        self._trails = {}
        self.update()

    def update_live_frame(self, payload: Dict[str, Any]) -> None:
        self._qimg = payload.get("qimage")
        self._vw = int(payload.get("width") or 720)
        self._vh = int(payload.get("height") or 1280)
        self._frame_info = payload.get("frame_info") or {}
        self._samples = payload.get("samples") or []
        self._trails = payload.get("trails") or {}
        self.update()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = Path(url.toLocalFile())
                if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                    self._dragging_file = True
                    self.update()
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, _event) -> None:
        self._dragging_file = False
        self.update()

    def dropEvent(self, event: QDropEvent) -> None:
        self._dragging_file = False
        self.update()
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = Path(url.toLocalFile())
                if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                    self.videoDropped.emit(p)
                    event.acceptProposedAction()
                    return

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QColor(COLORS["bg_canvas"]))

        if self._qimg is None or self._qimg.isNull():
            border_col = QColor(COLORS["accent"]) if self._dragging_file else QColor(COLORS["border_strong"])
            pen = QPen(border_col, 2.0, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QColor(COLORS["bg_canvas_inner"]))
            box = self.rect().adjusted(24, 24, -24, -24)
            painter.drawRoundedRect(box, 14, 14)

            painter.setPen(QColor(COLORS["text_primary"]))
            painter.setFont(QFont("Microsoft YaHei UI", 14, QFont.Weight.Bold))
            painter.drawText(
                box.adjusted(20, -34, -20, -34),
                Qt.AlignmentFlag.AlignCenter,
                "松开鼠标即可导入视频" if self._dragging_file else "拖放本地视频到此处，或点击左侧「选择本地视频」",
            )
            painter.setPen(QColor(COLORS["text_secondary"]))
            painter.setFont(QFont("Microsoft YaHei UI", 11))
            painter.drawText(
                box.adjusted(24, 26, -24, 26),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                "支持 MP4 / MOV / AVI / MKV（不受 20MB 限制）\n使用本机 YOLO26n + ByteTrack 实时检测与逐帧追踪行人",
            )
            return

        w = max(1, self.width() - 16)
        h = max(1, self.height() - 16)
        scale = min(w / max(self._vw, 1), h / max(self._vh, 1))
        dw, dh = self._vw * scale, self._vh * scale
        ox, oy = (self.width() - dw) * 0.5, (self.height() - dh) * 0.5
        draw_rect = QRectF(ox, oy, dw, dh)

        painter.setPen(QPen(QColor(COLORS["border_strong"]), 1.5))
        painter.drawRect(draw_rect)
        painter.drawImage(draw_rect, self._qimg)

        # 切入原视频像素坐标系严格等比叠加
        painter.save()
        painter.setClipRect(draw_rect)
        painter.translate(ox, oy)
        painter.scale(scale, scale)
        inv = 1.0 / max(scale, 0.1)

        # 分区线
        if self.show_zones:
            near_y = NEAR_LINE * self._vh
            mid_y = MID_LINE * self._vh
            painter.fillRect(QRectF(0, near_y, self._vw, self._vh - near_y), QColor(220, 0, 0, 22))
            zpen = QPen(QColor(255, 255, 255, 195), max(1.5, 1.5 * inv), Qt.PenStyle.DashLine)
            painter.setPen(zpen)
            painter.drawLine(QPointF(0, mid_y), QPointF(self._vw, mid_y))
            painter.drawLine(QPointF(0, near_y), QPointF(self._vw, near_y))

            font_z = QFont("Microsoft YaHei UI")
            font_z.setPixelSize(int(max(11, round(11.5 * inv))))
            font_z.setBold(True)
            painter.setFont(font_z)
            fm_z = QFontMetricsF(font_z)
            for y_v, txt, bg in [
                (mid_y, f"MID {MID_LINE:.2f}", QColor(255, 165, 0, 210)),
                (near_y, f"NEAR {NEAR_LINE:.2f}", QColor(220, 0, 0, 220)),
            ]:
                tw = fm_z.horizontalAdvance(txt) + 10 * inv
                th = fm_z.height() + 3 * inv
                pill = QRectF(self._vw - tw - 8 * inv, y_v - th - 4 * inv, tw, th)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(bg)
                painter.drawRoundedRect(pill, 4 * inv, 4 * inv)
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, txt)

        # 实时轨迹尾迹
        if self.show_trails:
            for s in self._samples:
                tid = int(s.get("id", -1))
                pts = self._trails.get(tid)
                if not pts or len(pts) < 2:
                    continue
                col = QColor(TRAIL_COLORS.get(s.get("name", ""), QColor("#38BDF8")))
                col.setAlphaF(0.65)
                pen = QPen(col, 2.2 * inv)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                path = QPainterPath(QPointF(pts[0][1], pts[0][2]))
                for p in pts[1:]:
                    path.lineTo(QPointF(p[1], p[2]))
                painter.drawPath(path)

        # 检测框 + 标签 + 脚点
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(int(max(10, round(10.5 * inv))))
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetricsF(font)
        base_w = max(2.0, (self._vw / 720.0) * 2.0)

        for s in self._samples:
            tid = int(s.get("id", -1))
            unassigned = tid < 0
            x1, y1, x2, y2 = s["box"]
            zone = s.get("zone")
            if unassigned:
                col = QColor(COLORS["zone_unassigned"])
                style = Qt.PenStyle.DashLine
            elif zone == "near":
                col = QColor(COLORS["zone_near"])
                style = Qt.PenStyle.SolidLine
            elif zone == "mid":
                col = QColor(COLORS["zone_mid"])
                style = Qt.PenStyle.SolidLine
            else:
                col = QColor(COLORS["zone_far"])
                style = Qt.PenStyle.SolidLine

            painter.setPen(QPen(col, base_w, style))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1)))

            label = f"{s['name']} {s['conf']:.2f}" if unassigned else f"{s['name']} #{tid} {s['conf']:.2f}"
            tw = fm.horizontalAdvance(label) + 8 * inv
            th = fm.height() + 2 * inv
            lx = max(0.0, min(x1, self._vw - tw))
            ly = y1 - th - 2 * inv
            if ly < 36 * inv:
                ly = min(self._vh - th, y1 + 2 * inv)
            bg = QColor(col)
            bg.setAlpha(205)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(lx, ly, tw, th), 3 * inv, 3 * inv)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(QRectF(lx, ly, tw, th), Qt.AlignmentFlag.AlignCenter, label)

            if self.show_foot:
                fx, fy = s["foot"]
                r = max(3.0, 3.5 * inv)
                painter.setPen(QPen(QColor("#FFFFFF"), max(1.0, 1.2 * inv)))
                painter.setBrush(QBrush(QColor(COLORS["foot_dot"])))
                painter.drawEllipse(QPointF(fx, fy), r, r)

        painter.restore()

        # 画面顶部状态条
        st = self._frame_info.get("state", "S0")
        alert = self._frame_info.get("alert")
        if st == "S2" and isinstance(alert, dict):
            dot_col = QColor(COLORS["state_s2"])
            tb = alert.get("timbre", "A")
            tname = "行人" if tb == "A" else "车辆"
            txt = f"S2 近场 · {tb}({tname}) · {alert.get('period_s', 0):.2f}s · #{alert.get('track_id', -1)}"
        elif st == "S1":
            dot_col = QColor(COLORS["state_s1"])
            txt = f"S1 远场 · 当前目标 {self._frame_info.get('count', 0)}"
        else:
            dot_col = QColor(COLORS["state_s0"])
            txt = "S0 静默 · 无目标"

        bar = QRectF(draw_rect.x(), draw_rect.y(), draw_rect.width(), 34.0)
        painter.fillRect(bar, QColor(30, 30, 30, 230))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_col)
        painter.drawEllipse(QPointF(bar.x() + 16, bar.center().y()), 6.0, 6.0)
        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(bar.adjusted(30, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, txt)


class LiveTrackView(QWidget):
    """V6 视频导入与实时检测追踪视图。"""

    sessionExported = Signal(Path)         # 导出 session.json 后静默注册进 V1 回放台
    openInPlaybackRequested = Signal(Path) # 用户点击复盘按钮时切回 V1 并播放

    def __init__(self, weights_dir: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._weights_dir = weights_dir
        self._selected_video: Optional[Path] = None
        self._worker: Optional[LiveTrackingWorker] = None
        self._paused: bool = False
        self._last_exported_json: Optional[Path] = None
        self._build_ui()
        self.refresh_weights(weights_dir)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(10)

        outer.addWidget(
            DisclaimerBanner(
                "实时追踪基于本地 YOLO26n + ByteTrack（未标定像素坐标系）：分区为画面下沿占比演示逻辑，非米制距离；"
                "alert 仅为演示规则，非风险引擎；实测 FPS 仅记录本机速度。"
            )
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ==================== 左侧：导入与参数配置栏 ====================
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(290)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_box = QWidget()
        left_lay = QVBoxLayout(left_box)
        left_lay.setContentsMargins(0, 0, 6, 0)
        left_lay.setSpacing(10)

        # 1. 视频输入源与快速启动卡（一屏直达：选视频 -> 立刻追踪）
        src_card = SectionCard("1. 导入视频与运行")
        self._cmb_source = QComboBox()
        self._cmb_source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._cmb_source.setMinimumContentsLength(10)
        self._cmb_source.addItems(["本地视频（支持拖放）", "本机摄像头 (Camera 0)"])
        self._cmb_source.currentIndexChanged.connect(self._on_source_kind_changed)
        src_card.root_layout.addWidget(self._cmb_source)

        self._btn_pick_video = QPushButton("选择本地视频文件...")
        self._btn_pick_video.clicked.connect(self.prompt_select_video)
        src_card.root_layout.addWidget(self._btn_pick_video)

        self._lbl_video_info = QLabel("尚未选择视频（也可直接把视频拖入右侧画布）")
        self._lbl_video_info.setObjectName("SubText")
        self._lbl_video_info.setWordWrap(True)
        src_card.root_layout.addWidget(self._lbl_video_info)

        self._btn_start = QPushButton("开始实时追踪 (YOLO26n)")
        self._btn_start.setObjectName("PrimaryBtn")
        self._btn_start.setMinimumHeight(40)
        self._btn_start.clicked.connect(self.start_tracking)
        src_card.root_layout.addWidget(self._btn_start)

        r2 = QHBoxLayout()
        r2.setSpacing(8)
        self._btn_pause = QPushButton("暂停")
        self._btn_pause.setEnabled(False)
        self._btn_pause.clicked.connect(self._toggle_pause)
        self._btn_stop = QPushButton("停止")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self.stop_tracking)
        r2.addWidget(self._btn_pause)
        r2.addWidget(self._btn_stop)
        src_card.root_layout.addLayout(r2)

        self._btn_open_v1 = QPushButton("在 V1 回放台复盘本次结果 →")
        self._btn_open_v1.setEnabled(False)
        self._btn_open_v1.clicked.connect(self._open_exported_session)
        src_card.root_layout.addWidget(self._btn_open_v1)
        left_lay.addWidget(src_card)

        # 2. 模型与追踪参数卡
        cfg_card = SectionCard("2. N 档位模型与参数")

        cfg_card.root_layout.addWidget(QLabel("检测权重 (.pt)"))
        w_row = QHBoxLayout()
        w_row.setSpacing(6)
        self._cmb_weights = QComboBox()
        self._cmb_weights.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._cmb_weights.setMinimumContentsLength(10)
        w_row.addWidget(self._cmb_weights, 1)
        btn_pick_w = QPushButton("浏览")
        btn_pick_w.setFixedWidth(64)
        btn_pick_w.clicked.connect(self._pick_custom_weights)
        w_row.addWidget(btn_pick_w)
        cfg_card.root_layout.addLayout(w_row)

        cfg_card.root_layout.addWidget(QLabel("目标类别筛选"))
        self._cmb_classes = QComboBox()
        self._cmb_classes.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._cmb_classes.setMinimumContentsLength(10)
        self._cmb_classes.addItems([
            "行人 + 常见车辆（默认）",
            "仅追踪行人（person）",
            "COCO 全类别",
        ])
        cfg_card.root_layout.addWidget(self._cmb_classes)

        p_grid = QGridLayout()
        p_grid.setSpacing(8)
        p_grid.addWidget(QLabel("输入尺寸"), 0, 0)
        self._cmb_imgsz = QComboBox()
        self._cmb_imgsz.addItems(["640", "960", "1280"])
        self._cmb_imgsz.setCurrentText("960")
        p_grid.addWidget(self._cmb_imgsz, 0, 1)

        p_grid.addWidget(QLabel("置信阈值"), 1, 0)
        self._spn_conf = QDoubleSpinBox()
        self._spn_conf.setRange(0.05, 0.95)
        self._spn_conf.setSingleStep(0.05)
        self._spn_conf.setDecimals(2)
        self._spn_conf.setValue(0.25)
        p_grid.addWidget(self._spn_conf, 1, 1)

        p_grid.addWidget(QLabel("推理设备"), 2, 0)
        self._cmb_device = QComboBox()
        self._cmb_device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._cmb_device.setMinimumContentsLength(8)
        self._cmb_device.addItems(["自动 (GPU 0)", "GPU 0 (CUDA)", "CPU"])
        p_grid.addWidget(self._cmb_device, 2, 1)
        cfg_card.root_layout.addLayout(p_grid)

        self._chk_throttle = QCheckBox("按原视频帧率节流预览")
        self._chk_throttle.setChecked(True)
        self._chk_throttle.toggled.connect(self._on_throttle_changed)
        cfg_card.root_layout.addWidget(self._chk_throttle)

        self._chk_save = QCheckBox("结束后导出 session.json 回放")
        self._chk_save.setChecked(True)
        cfg_card.root_layout.addWidget(self._chk_save)

        left_lay.addWidget(cfg_card)
        left_lay.addStretch(1)
        left_scroll.setWidget(left_box)
        splitter.addWidget(left_scroll)

        # ==================== 中间：实时叠加画布 + 进度条 ====================
        center_w = QWidget()
        center_lay = QVBoxLayout(center_w)
        center_lay.setContentsMargins(6, 0, 6, 0)
        center_lay.setSpacing(10)

        canvas_card = QFrame()
        canvas_card.setObjectName("Card")
        cl = QVBoxLayout(canvas_card)
        cl.setContentsMargins(8, 8, 8, 8)
        self._canvas = LiveOverlayCanvas()
        self._canvas.videoDropped.connect(self.set_video_file)
        cl.addWidget(self._canvas, 1)
        center_lay.addWidget(canvas_card, 1)

        prog_card = QFrame()
        prog_card.setObjectName("Card")
        pl = QVBoxLayout(prog_card)
        pl.setContentsMargins(14, 10, 14, 10)
        pl.setSpacing(8)

        self._lbl_status = QLabel("就绪：请选择或拖放本地视频，点击「开始实时追踪」")
        self._lbl_status.setObjectName("TitleText")
        self._lbl_status.setWordWrap(True)
        pl.addWidget(self._lbl_status)

        st_row = QHBoxLayout()
        st_row.setSpacing(10)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("进度：%p%")
        st_row.addWidget(self._progress, 1)

        self._lbl_perf = QLabel("推理：— ms · 实时：— FPS")
        self._lbl_perf.setObjectName("PillAccent")
        st_row.addWidget(self._lbl_perf)
        pl.addLayout(st_row)
        center_lay.addWidget(prog_card)
        splitter.addWidget(center_w)

        # ==================== 右侧：实时追踪状态 HUD ====================
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setMinimumWidth(305)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_box = QWidget()
        right_lay = QVBoxLayout(right_box)
        right_lay.setContentsMargins(6, 0, 2, 0)
        right_lay.setSpacing(10)

        self._state_card = QFrame()
        self._state_card.setObjectName("StateCardS0")
        sc_lay = QVBoxLayout(self._state_card)
        sc_lay.setContentsMargins(14, 12, 14, 12)
        sc_lay.setSpacing(6)

        self._lbl_live_state = QLabel("● S0 · 待机")
        self._lbl_live_state.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLORS['state_s0_text']};")
        sc_lay.addWidget(self._lbl_live_state)

        self._lbl_live_sub = QLabel("等待开始实时推理追踪")
        self._lbl_live_sub.setObjectName("SubText")
        self._lbl_live_sub.setWordWrap(True)
        sc_lay.addWidget(self._lbl_live_sub)

        kv = QGridLayout()
        kv.setSpacing(8)
        self._kv_nearest = self._make_kv("最近目标 ID", "—")
        self._kv_proxy = self._make_kv("脚点占比", "—")
        self._kv_period = self._make_kv("脉冲间隔", "—")
        self._kv_timbre = self._make_kv("演示音色", "—")
        kv.addWidget(self._kv_nearest[0], 0, 0)
        kv.addWidget(self._kv_proxy[0], 0, 1)
        kv.addWidget(self._kv_period[0], 1, 0)
        kv.addWidget(self._kv_timbre[0], 1, 1)
        sc_lay.addLayout(kv)
        right_lay.addWidget(self._state_card)

        zone_card = SectionCard("实时分区目标数")
        zr = QHBoxLayout()
        zr.setSpacing(8)
        self._z_tot = self._make_pill("总计", "0", "accent")
        self._z_near = self._make_pill("近场", "0", "near")
        self._z_mid = self._make_pill("中场", "0", "mid")
        self._z_far = self._make_pill("远场", "0", "far")
        for b in [self._z_tot[0], self._z_near[0], self._z_mid[0], self._z_far[0]]:
            zr.addWidget(b)
        zone_card.root_layout.addLayout(zr)
        right_lay.addWidget(zone_card)

        tgt_card = SectionCard("当前帧追踪目标")
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["ID", "类别", "分区", "置信"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setMinimumHeight(210)
        tgt_card.root_layout.addWidget(self._table)
        right_lay.addWidget(tgt_card)

        right_lay.addStretch(1)
        right_scroll.setWidget(right_box)
        splitter.addWidget(right_scroll)

        splitter.setSizes([325, 670, 345])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        outer.addWidget(splitter, 1)
        self._last_live_state = "S0"
        self.refresh_theme()

    def _make_kv(self, title: str, val: str):
        frame = QFrame()
        frame.setObjectName("HudKv")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(9, 6, 9, 6)
        lay.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("MutedText")
        v = QLabel(val)
        v.setStyleSheet("font-size: 16px; font-weight: 800;")
        lay.addWidget(t)
        lay.addWidget(v)
        return frame, v

    def _make_pill(self, title: str, val: str, role: str):
        frame = QFrame()
        frame.setObjectName("CardAlt")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(6, 7, 6, 7)
        lay.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("MutedText")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v = QLabel(val)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setProperty("zone_role", role)
        lay.addWidget(t)
        lay.addWidget(v)
        return frame, v

    def refresh_theme(self) -> None:
        role_colors = {
            "accent": COLORS["accent"],
            "near": COLORS["state_s2_text"],
            "mid": COLORS["state_s1_text"],
            "far": COLORS["ok_text"],
        }
        for _, v in (self._z_tot, self._z_near, self._z_mid, self._z_far):
            col = role_colors.get(v.property("zone_role"), COLORS["text_primary"])
            v.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {col};")
        st = getattr(self, "_last_live_state", "S0")
        st_col = {"S2": COLORS["state_s2_text"], "S1": COLORS["state_s1_text"]}.get(st, COLORS["state_s0_text"])
        self._lbl_live_state.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {st_col};")
        self._canvas.update()

    # ==================== 权重与视频选择 ====================
    def refresh_weights(self, weights_dir: Path) -> None:
        """聚焦 N 档位（yolo26n.pt），自动过滤 s / m 档位模型。"""
        self._weights_dir = weights_dir
        self._cmb_weights.clear()
        excluded = {"yolo26s.pt", "yolo26m.pt"}
        found: List[Path] = []
        if weights_dir.is_dir():
            found = sorted(p for p in weights_dir.glob("*.pt") if p.name.lower() not in excluded)
        found.sort(key=lambda p: (0 if p.name.lower() == "yolo26n.pt" else 1, p.name))
        for p in found:
            mb = p.stat().st_size / (1024 * 1024)
            self._cmb_weights.addItem(f"{p.name} ({mb:.1f} MB)", str(p))
        if not found:
            self._cmb_weights.addItem("未发现 yolo26n.pt，请点击浏览", "")

    def _pick_custom_weights(self) -> None:
        f, _ = QFileDialog.getOpenFileName(
            self, "选择 YOLO 权重文件 (.pt)", str(self._weights_dir), "PyTorch 权重 (*.pt)"
        )
        if f:
            p = Path(f)
            self._cmb_weights.insertItem(0, f"{p.name}（自定义）", str(p))
            self._cmb_weights.setCurrentIndex(0)

    def _on_source_kind_changed(self, idx: int) -> None:
        is_video = (idx == 0)
        self._btn_pick_video.setEnabled(is_video)
        self._chk_throttle.setEnabled(is_video)
        self._chk_save.setEnabled(is_video)
        if not is_video:
            self._lbl_video_info.setText("已选择本机摄像头（Camera 0），点击「开始实时追踪」即可开启实时检测")

    def prompt_select_video(self) -> None:
        start_dir = str(self._selected_video.parent) if self._selected_video else str(Path.home())
        if not Path(start_dir).exists():
            start_dir = str(Path.cwd())
        f, _ = QFileDialog.getOpenFileName(
            self,
            "导入本地视频进行实时追踪（不受 20MB 限制）",
            start_dir,
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.flv *.wmv *.webm);;所有文件 (*.*)",
        )
        if f:
            self.set_video_file(Path(f))

    def set_video_file(self, path: Path) -> None:
        if not path.is_file():
            return
        self._cmb_source.setCurrentIndex(0)
        self._selected_video = path
        mb = path.stat().st_size / (1024 * 1024)
        self._lbl_video_info.setText(f"已导入：{path.name}\n体积：{mb:.2f} MB\n路径：{path}")
        self._lbl_status.setText(f"已导入视频 {path.name}，点击「开始实时追踪」即可运行 YOLO26n + ByteTrack")

    # ==================== 推理启停控制 ====================
    def start_tracking(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        src_kind = "video" if self._cmb_source.currentIndex() == 0 else "camera"
        if src_kind == "video" and not self._selected_video:
            self.prompt_select_video()
            if not self._selected_video:
                return

        w_str = self._cmb_weights.currentData()
        if not w_str:
            self._lbl_status.setText("请先选择有效的 .pt 模型权重文件。")
            return

        cls_idx = self._cmb_classes.currentIndex()
        classes = [0, 1, 2, 3, 5, 7] if cls_idx == 0 else ([0] if cls_idx == 1 else None)
        dev_idx = self._cmb_device.currentIndex()
        device = "" if dev_idx == 0 else ("0" if dev_idx == 1 else "cpu")

        cfg = TrackTaskConfig(
            source_kind=src_kind,
            video_path=self._selected_video,
            camera_index=0,
            weights_path=Path(w_str),
            imgsz=int(self._cmb_imgsz.currentText()),
            conf=float(self._spn_conf.value()),
            classes=classes,
            device=device,
            throttle_to_fps=self._chk_throttle.isChecked(),
            save_session=self._chk_save.isChecked(),
        )

        self._last_exported_json = None
        self._btn_open_v1.setEnabled(False)
        self._paused = False
        self._btn_pause.setText("暂停")
        self._progress.setValue(0)
        self._set_running_ui(True)

        worker = LiveTrackingWorker(cfg, self)
        worker.statusMessage.connect(self._lbl_status.setText)
        worker.frameProcessed.connect(self._on_frame_processed)
        worker.trackingFinished.connect(self._on_tracking_finished)
        worker.trackingError.connect(self._on_tracking_error)
        self._worker = worker
        worker.start()

    def _toggle_pause(self) -> None:
        if not self._worker or not self._worker.isRunning():
            return
        self._paused = not self._paused
        self._worker.set_paused(self._paused)
        self._btn_pause.setText("继续" if self._paused else "暂停")
        self._lbl_status.setText("已暂停实时追踪" if self._paused else "继续实时追踪中...")

    def _on_throttle_changed(self, checked: bool) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.set_throttle(checked)

    def stop_tracking(self) -> None:
        if self._worker and self._worker.isRunning():
            self._lbl_status.setText("正在停止实时追踪并保存已完成帧...")
            self._worker.request_stop()

    def shutdown_worker(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(3000)

    def _set_running_ui(self, running: bool) -> None:
        self._btn_start.setEnabled(not running)
        self._btn_pause.setEnabled(running)
        self._btn_stop.setEnabled(running)
        self._cmb_source.setEnabled(not running)
        self._btn_pick_video.setEnabled((not running) and self._cmb_source.currentIndex() == 0)
        self._cmb_weights.setEnabled(not running)
        self._cmb_classes.setEnabled(not running)
        self._cmb_imgsz.setEnabled(not running)
        self._spn_conf.setEnabled(not running)
        self._cmb_device.setEnabled(not running)

    def _on_frame_processed(self, payload: Dict[str, Any]) -> None:
        self._canvas.update_live_frame(payload)

        fi = int(payload["frame_idx"])
        tot = int(payload["total_frames"])
        if tot > 0:
            pct = min(100, int(round((fi + 1) * 100.0 / tot)))
            self._progress.setValue(pct)
            self._progress.setFormat(f"帧 {fi + 1} / {tot}（%p%）")
        else:
            self._progress.setRange(0, 0)
            self._progress.setFormat(f"实时流 · 已处理 {fi + 1} 帧")

        self._lbl_perf.setText(
            f"推理：{payload['infer_ms']:.1f} ms/帧 · 实时：{payload['live_fps']:.1f} FPS（{payload['device']}）"
        )

        # 更新右侧 HUD
        fr = payload["frame_info"]
        samples = payload["samples"]
        st = fr.get("state", "S0")
        alert = fr.get("alert")

        self._last_live_state = st
        if st == "S2":
            self._state_card.setObjectName("StateCardS2")
            self._lbl_live_state.setText("▲ S2 · 近场音频")
            self._lbl_live_state.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLORS['state_s2_text']};")
            self._lbl_live_sub.setText("近场区检出目标（画面下沿占比 > 0.72，演示规则）")
        elif st == "S1":
            self._state_card.setObjectName("StateCardS1")
            self._lbl_live_state.setText("◆ S1 · 远场提示")
            self._lbl_live_state.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLORS['state_s1_text']};")
            self._lbl_live_sub.setText("中/远场区存在目标，近场为空（演示规则）")
        else:
            self._state_card.setObjectName("StateCardS0")
            self._lbl_live_state.setText("● S0 · 静默")
            self._lbl_live_state.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLORS['state_s0_text']};")
            self._lbl_live_sub.setText("当前帧无目标")
        self._state_card.style().unpolish(self._state_card)
        self._state_card.style().polish(self._state_card)

        if isinstance(alert, dict):
            tid = alert.get("track_id", -1)
            self._kv_nearest[1].setText(f"#{tid}" if tid >= 0 else "未确认")
            self._kv_proxy[1].setText(f"{alert.get('distance_proxy', 0) * 100:.1f}%")
            self._kv_period[1].setText(f"{alert.get('period_s', 0):.3f} s")
            tb = alert.get("timbre")
            self._kv_timbre[1].setText("A · 行人" if tb == "A" else ("B · 车辆" if tb == "B" else "—"))
        else:
            self._kv_nearest[1].setText("—")
            self._kv_proxy[1].setText("—")
            self._kv_period[1].setText("—")
            self._kv_timbre[1].setText("—")

        self._z_tot[1].setText(str(fr.get("count", 0)))
        self._z_near[1].setText(str(fr.get("near", 0)))
        self._z_mid[1].setText(str(fr.get("mid", 0)))
        self._z_far[1].setText(str(fr.get("far", 0)))

        ordered = sorted(samples, key=lambda x: x["foot"][1], reverse=True)
        self._table.setRowCount(len(ordered))
        z_cn = {"near": "近场", "mid": "中场", "far": "远场"}
        for r, s in enumerate(ordered):
            tid = s["id"]
            vals = [
                "未确认" if tid < 0 else f"#{tid}",
                s["name"],
                z_cn.get(s["zone"], "—"),
                f"{s['conf']:.2f}",
            ]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, c, it)

    def _on_tracking_finished(self, summary: Dict[str, Any]) -> None:
        self._set_running_ui(False)
        self._progress.setRange(0, 100)
        if not summary.get("stopped_early"):
            self._progress.setValue(100)
        sj = summary.get("session_json")
        msg = (
            f"追踪完成：共 {summary['frames']} 帧 / {summary['samples']} 样本 / "
            f"{summary['tracks']} 条轨迹 · 均速 {summary['avg_fps']:.1f} FPS（本机实测）"
        )
        if sj:
            self._last_exported_json = Path(sj)
            self._btn_open_v1.setEnabled(True)
            msg += f"  |  已导出至 user_sessions"
            self.sessionExported.emit(self._last_exported_json)
        self._lbl_status.setText(msg)

    def _on_tracking_error(self, err: str) -> None:
        self._set_running_ui(False)
        self._progress.setRange(0, 100)
        self._lbl_status.setText(err)

    def _open_exported_session(self) -> None:
        if self._last_exported_json and self._last_exported_json.is_file():
            self.openInPlaybackRequested.emit(self._last_exported_json)
