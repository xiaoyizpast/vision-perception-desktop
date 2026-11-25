# -*- coding: utf-8 -*-
"""V1 视频与检测叠加层画布（原视频像素坐标系等比缩放，误差 = 0 px）。

严格遵循 docs/06 第 5 节绘制规范：
- 近场框：#DC0000（2px 原视频像素）
- 中场框：#FFA500
- 远场框：#00C800
- 未确认（id == -1 或 None）：#888888 虚线，不写 ID，不复用 ID
- 标签：`person #12 0.87`，框左上角外侧，裁切时自动移至框内
- 脚点：蓝色 #0000FF 实心圆（半径 3px），外环白边提升暗场可读性
- 分区线：y = near_line * height、y = mid_line * height，白色虚线 + 右侧 NEAR/MID 小字
- 顶部状态条：34px 高、#1E1E1E 底，白字：S0 静默 / S1 远场 / S2 近场音频 · A · 0.21s
- 轨迹尾迹：同类别颜色，默认透明度 0.35，选中高亮至 0.9
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from data_loader import SessionBundle, _effective_state
from theme import COLORS

CLASS_TRAIL_COLORS = {
    "person": QColor("#38BDF8"),
    "bus": QColor("#F59E0B"),
    "car": QColor("#A855F7"),
    "motorcycle": QColor("#EC4899"),
    "bicycle": QColor("#22C55E"),
}


class VideoOverlayCanvas(QWidget):
    """支持竖屏/横屏等比显示、叠加层渲染、点击选中目标的硬件加速画布。"""

    targetClicked = Signal(int)  # 发出被点击的 track_id（>=0）

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(280, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        self._session: Optional[SessionBundle] = None
        self._frame_img: Optional[QImage] = None
        self._frame_idx: int = 0
        self._selected_track_id: Optional[int] = None

        # 图层开关
        self.show_boxes: bool = True
        self.show_foot: bool = True
        self.show_zones: bool = True
        self.show_trails: bool = True
        self.show_status_bar: bool = True
        self.show_unassigned: bool = True
        self.show_legend: bool = False

        # 缓存当前视频绘制几何（用于鼠标点击命中的逆变换）
        self._draw_rect: QRectF = QRectF()
        self._scale: float = 1.0

    def set_session(self, session: Optional[SessionBundle]) -> None:
        self._session = session
        self._frame_img = None
        self._frame_idx = 0
        self._selected_track_id = None
        self.update()

    def set_frame(self, frame_idx: int, image: Optional[QImage]) -> None:
        self._frame_idx = frame_idx
        self._frame_img = image
        self.update()

    def set_selected_track(self, track_id: Optional[int]) -> None:
        self._selected_track_id = track_id
        self.update()

    def toggle_legend(self) -> bool:
        self.show_legend = not self.show_legend
        self.update()
        return self.show_legend

    def _video_size(self) -> Tuple[int, int]:
        if self._session and self._session.video:
            return int(self._session.video["width"]), int(self._session.video["height"])
        if self._frame_img is not None and not self._frame_img.isNull():
            return self._frame_img.width(), self._frame_img.height()
        return 720, 1280

    def _compute_fit_rect(self, vw: int, vh: int) -> Tuple[QRectF, float]:
        w = max(1, self.width() - 16)
        h = max(1, self.height() - 16)
        scale = min(w / max(vw, 1), h / max(vh, 1))
        dw = vw * scale
        dh = vh * scale
        ox = (self.width() - dw) * 0.5
        oy = (self.height() - dh) * 0.5
        return QRectF(ox, oy, dw, dh), scale

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._session:
            return super().mousePressEvent(event)
        if self._draw_rect.isEmpty() or self._scale <= 0:
            return super().mousePressEvent(event)
        pt = event.position()
        if not self._draw_rect.contains(pt):
            return super().mousePressEvent(event)

        vx = (pt.x() - self._draw_rect.x()) / self._scale
        vy = (pt.y() - self._draw_rect.y()) / self._scale
        samples = self._session.frame_samples(self._frame_idx)
        # 优先命中面积最小的框（防大框遮挡小框）
        hits: List[Tuple[float, int]] = []
        for s in samples:
            tid = s.get("id")
            if tid is None or int(tid) < 0:
                continue
            box = s.get("box")
            if not box or len(box) != 4:
                continue
            x1, y1, x2, y2 = box
            if x1 <= vx <= x2 and y1 <= vy <= y2:
                area = max(1.0, (x2 - x1) * (y2 - y1))
                hits.append((area, int(tid)))
        if hits:
            hits.sort(key=lambda t: t[0])
            chosen = hits[0][1]
            self._selected_track_id = chosen
            self.targetClicked.emit(chosen)
            self.update()
        else:
            self._selected_track_id = None
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 背景底板（跟随浅/深主题）
        painter.fillRect(self.rect(), QColor(COLORS["bg_canvas"]))

        if self._session is None:
            self._draw_empty_message(painter, "尚未加载会话数据", "请在左侧选择会话或打开数据目录")
            return

        vw, vh = self._video_size()
        draw_rect, scale = self._compute_fit_rect(vw, vh)
        self._draw_rect = draw_rect
        self._scale = scale

        # 视频舞台背景框
        painter.setPen(QPen(QColor(COLORS["border_strong"]), 1.5))
        painter.setBrush(QColor(COLORS["bg_canvas_inner"]))
        painter.drawRect(draw_rect)

        # 1. 绘制视频底图
        if self._session.video is None:
            self._draw_empty_message(
                painter,
                "无视频元信息（video == null）",
                "已禁用视频帧回放；您仍可在下方时间轴与 V2 轨迹视图中检视数据",
                draw_rect,
            )
        elif self._frame_img is not None and not self._frame_img.isNull():
            painter.drawImage(draw_rect, self._frame_img)
        else:
            self._draw_empty_message(
                painter,
                "未找到视频文件或解码失败",
                f"期望视频：{self._session.video.get('filename', '未知')}",
                draw_rect,
            )

        # 2. 切入原视频像素坐标系，严格等比叠加（零错位）
        painter.save()
        painter.setClipRect(draw_rect)
        painter.translate(draw_rect.x(), draw_rect.y())
        painter.scale(scale, scale)

        zones = self._session.zones
        near_line = float(zones.get("near_line", 0.72))
        mid_line = float(zones.get("mid_line", 0.45))

        if self.show_zones:
            self._draw_zone_lines(painter, vw, vh, near_line, mid_line, scale)

        samples = self._session.frame_samples(self._frame_idx)

        if self.show_trails:
            self._draw_active_trails(painter, samples, scale)

        if self.show_boxes or self.show_foot:
            self._draw_detections(painter, samples, vw, vh, scale)

        painter.restore()

        # 3. 顶部状态条（在视频显示区域顶部，固定屏幕像素 34px 高）
        if self.show_status_bar:
            self._draw_top_status_bar(painter, draw_rect)

        # 4. 可折叠图例（右下角，快捷键 L）
        if self.show_legend:
            self._draw_legend(painter, draw_rect)

    def _draw_empty_message(
        self,
        painter: QPainter,
        title: str,
        subtitle: str,
        rect: Optional[QRectF] = None,
    ) -> None:
        r = rect if rect is not None else QRectF(self.rect())
        painter.save()
        f1 = QFont("Microsoft YaHei UI", 13, QFont.Weight.Bold)
        painter.setFont(f1)
        painter.setPen(QColor(COLORS["text_primary"]))
        painter.drawText(r.adjusted(16, -22, -16, -22), Qt.AlignmentFlag.AlignCenter, title)
        f2 = QFont("Microsoft YaHei UI", 10)
        painter.setFont(f2)
        painter.setPen(QColor(COLORS["text_secondary"]))
        painter.drawText(r.adjusted(20, 26, -20, 26), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, subtitle)
        painter.restore()

    def _draw_zone_lines(
        self,
        painter: QPainter,
        vw: int,
        vh: int,
        near_line: float,
        mid_line: float,
        scale: float,
    ) -> None:
        inv = 1.0 / max(scale, 0.1)
        near_y = near_line * vh
        mid_y = mid_line * vh

        # 轻度近场底色提示（仅极低透明度，不遮画面）
        painter.fillRect(QRectF(0, near_y, vw, vh - near_y), QColor(220, 0, 0, 22))

        dash_pen = QPen(QColor(255, 255, 255, 195), max(1.5, 1.5 * inv), Qt.PenStyle.DashLine)
        dash_pen.setDashPattern([8, 6])
        painter.setPen(dash_pen)
        painter.drawLine(QPointF(0, mid_y), QPointF(vw, mid_y))
        painter.drawLine(QPointF(0, near_y), QPointF(vw, near_y))

        # 右侧标签 NEAR / MID
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(int(max(13, 13 * inv)))
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetricsF(font)

        for y_val, text, bg_col in [
            (mid_y, f"MID  {mid_line:.2f}", QColor(255, 165, 0, 210)),
            (near_y, f"NEAR {near_line:.2f}", QColor(220, 0, 0, 220)),
        ]:
            tw = fm.horizontalAdvance(text) + 12 * inv
            th = fm.height() + 4 * inv
            pill = QRectF(vw - tw - 8 * inv, y_val - th - 4 * inv, tw, th)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_col)
            painter.drawRoundedRect(pill, 4 * inv, 4 * inv)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_active_trails(
        self,
        painter: QPainter,
        samples: List[Dict[str, Any]],
        scale: float,
    ) -> None:
        if not self._session:
            return
        inv = 1.0 / max(scale, 0.1)
        active_ids = {int(s["id"]) for s in samples if s.get("id") is not None and int(s["id"]) >= 0}
        if self._selected_track_id is not None:
            active_ids.add(self._selected_track_id)

        for tid in active_ids:
            tr = self._session.track_by_id.get(tid)
            if not tr:
                continue
            pts = tr.get("foot_path") or []
            if len(pts) < 2:
                continue
            # 取到当前帧为止的最近 45 个点
            tail = [p for p in pts if p[0] <= self._frame_idx][-45:]
            if len(tail) < 2:
                continue
            base_col = QColor(CLASS_TRAIL_COLORS.get(tr.get("class_name", ""), QColor("#38BDF8")))
            is_sel = (tid == self._selected_track_id)
            base_col.setAlphaF(0.92 if is_sel else 0.38)
            pen = QPen(base_col, (3.2 if is_sel else 2.0) * inv)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath(QPointF(tail[0][1], tail[0][2]))
            for p in tail[1:]:
                path.lineTo(QPointF(p[1], p[2]))
            painter.drawPath(path)

    def _draw_detections(
        self,
        painter: QPainter,
        samples: List[Dict[str, Any]],
        vw: int,
        vh: int,
        scale: float,
    ) -> None:
        inv = 1.0 / max(scale, 0.1)
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(int(max(10, round(10.5 * inv))))
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetricsF(font)

        for s in samples:
            tid_raw = s.get("id")
            unassigned = (tid_raw is None or int(tid_raw) < 0)
            if unassigned and not self.show_unassigned:
                continue
            box = s.get("box")
            if not box or len(box) != 4:
                continue
            x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
            zone = s.get("zone")
            name = str(s.get("name", "obj"))
            conf = float(s.get("conf", 0.0))
            is_sel = (not unassigned and int(tid_raw) == self._selected_track_id)

            if unassigned:
                color = QColor(COLORS["zone_unassigned"])
                pen_style = Qt.PenStyle.DashLine
            elif zone == "near":
                color = QColor(COLORS["zone_near"])
                pen_style = Qt.PenStyle.SolidLine
            elif zone == "mid":
                color = QColor(COLORS["zone_mid"])
                pen_style = Qt.PenStyle.SolidLine
            else:
                color = QColor(COLORS["zone_far"])
                pen_style = Qt.PenStyle.SolidLine

            if self.show_boxes:
                # 原视频 720 宽计 2px（随缩放等比）
                base_w = max(2.0, (vw / 720.0) * 2.0)
                if is_sel:
                    base_w *= 1.8
                pen = QPen(color, base_w, pen_style)
                painter.setPen(pen)
                painter.setBrush(QColor(color.red(), color.green(), color.blue(), 36 if is_sel else 0))
                painter.drawRect(QRectF(x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1)))

                # 标签：未确认绝不写 ID，绝不复用上一条 ID
                if unassigned:
                    label = f"{name} {conf:.2f}"
                else:
                    label = f"{name} #{int(tid_raw)} {conf:.2f}"

                tw = fm.horizontalAdvance(label) + 8 * inv
                th = fm.height() + 2 * inv
                # 放框左上角外侧；若被顶部裁切则自动移到框内
                lx = max(0.0, min(x1, vw - tw))
                ly = y1 - th - 2 * inv
                if ly < 36 * inv:  # 避让顶部状态条与画面上沿
                    ly = min(vh - th, y1 + 2 * inv)

                lbl_rect = QRectF(lx, ly, tw, th)
                bg = QColor(color)
                bg.setAlpha(205)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(bg)
                painter.drawRoundedRect(lbl_rect, 3 * inv, 3 * inv)
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, label)

            if self.show_foot:
                foot = s.get("foot")
                if foot and len(foot) == 2:
                    fx, fy = float(foot[0]), float(foot[1])
                    r = max(3.0, 3.5 * inv)
                    painter.setPen(QPen(QColor("#FFFFFF"), max(1.0, 1.2 * inv)))
                    painter.setBrush(QBrush(QColor(COLORS["foot_dot"])))
                    painter.drawEllipse(QPointF(fx, fy), r, r)

    def _draw_top_status_bar(self, painter: QPainter, draw_rect: QRectF) -> None:
        if not self._session or draw_rect.width() < 120:
            return
        fr = self._session.frame_info(self._frame_idx)
        st = _effective_state(fr)
        alert = fr.get("alert")

        if st == "S2":
            dot_col = QColor(COLORS["state_s2"])
            if isinstance(alert, dict):
                timbre = alert.get("timbre") or "A"
                t_name = "行人" if timbre == "A" else ("车辆" if timbre == "B" else timbre)
                period = float(alert.get("period_s") or 0.0)
                tid = alert.get("track_id")
                tid_part = f" · #{tid}" if tid is not None and int(tid) >= 0 else ""
                text = f"S2 近场 · {timbre}({t_name}) · {period:.2f}s{tid_part}"
            else:
                text = "S2 近场音频（演示规则）"
        elif st == "S1":
            dot_col = QColor(COLORS["state_s1"])
            text = f"S1 远场 · 当前目标 {int(fr.get('count', 0))}"
        else:
            dot_col = QColor(COLORS["state_s0"])
            text = "S0 静默 · 无目标"

        bar_rect = QRectF(draw_rect.x(), draw_rect.y(), draw_rect.width(), 34.0)
        painter.save()
        painter.fillRect(bar_rect, QColor(30, 30, 30, 230))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_col)
        painter.drawEllipse(QPointF(bar_rect.x() + 16, bar_rect.center().y()), 6.0, 6.0)

        f = QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold)
        painter.setFont(f)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(
            bar_rect.adjusted(30, 0, -10, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )
        painter.restore()

    def _draw_legend(self, painter: QPainter, draw_rect: QRectF) -> None:
        if draw_rect.width() < 180 or draw_rect.height() < 180:
            return
        painter.save()
        bw = min(192.0, draw_rect.width() - 12.0)
        bh = 104.0
        box = QRectF(draw_rect.left() + 8, draw_rect.top() + 40, bw, bh)
        painter.setPen(QPen(QColor("#334155"), 1.0))
        painter.setBrush(QColor(15, 21, 29, 200))
        painter.drawRoundedRect(box, 8, 8)

        f = QFont("Microsoft YaHei UI", 8)
        painter.setFont(f)
        items = [
            (QColor(COLORS["zone_near"]), False, "近场 near（>0.72）"),
            (QColor(COLORS["zone_mid"]), False, "中场 mid（0.45~0.72）"),
            (QColor(COLORS["zone_far"]), False, "远场 far（≤0.45）"),
            (QColor(COLORS["zone_unassigned"]), True, "未确认（id=-1 虚线）"),
            (QColor(COLORS["foot_dot"]), False, "脚点（框底中点 px）"),
        ]
        y = box.top() + 13
        for col, dashed, label in items:
            if dashed:
                p = QPen(col, 2.0, Qt.PenStyle.DashLine)
                painter.setPen(p)
                painter.drawLine(QPointF(box.left() + 8, y), QPointF(box.left() + 20, y))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(col)
                painter.drawEllipse(QPointF(box.left() + 14, y), 4.0, 4.0)
            painter.setPen(QColor("#E2E8F0"))
            painter.drawText(QRectF(box.left() + 25, y - 9, bw - 30, 18), Qt.AlignmentFlag.AlignVCenter, label)
            y += 19

        painter.restore()
