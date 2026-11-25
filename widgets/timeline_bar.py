# -*- coding: utf-8 -*-
"""V1 现代化自定义时间轴与状态告警色带组件。

契约要求（docs/06 第 4、5 节 & docs/05）：
- 把 state == S0 / S1 / S2 的连续帧合并成区间渲染（不逐帧画点）；
- 独立告警色带：S0 灰 / S1 黄 / S2 红；
- 在脉冲时间点画清晰小竖线（pulses）；
- 播放头清晰可见，支持点击 / 拖动实时跳转（< 100 ms）；
- 鼠标悬停显示对应帧号、时间、状态与目标数 Tooltip。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from data_loader import SessionBundle, _effective_state
from theme import COLORS


class TimelineBar(QWidget):
    """集进度条、状态区间色带与脉冲刻度于一体的交互式时间轴。"""

    seekRequested = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(68)
        self.setMaximumHeight(74)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._session: Optional[SessionBundle] = None
        self._current_frame: int = 0
        self._hover_frame: Optional[int] = None
        self._dragging: bool = False
        self._pad_x: float = 14.0

    def set_session(self, session: Optional[SessionBundle]) -> None:
        self._session = session
        self._current_frame = 0
        self._hover_frame = None
        self.update()

    def set_current_frame(self, frame_idx: int) -> None:
        if frame_idx != self._current_frame:
            self._current_frame = frame_idx
            self.update()

    def _track_rect(self) -> QRectF:
        return QRectF(self._pad_x, 12.0, max(10.0, self.width() - 2 * self._pad_x), 14.0)

    def _band_rect(self) -> QRectF:
        return QRectF(self._pad_x, 34.0, max(10.0, self.width() - 2 * self._pad_x), 14.0)

    def _x_to_frame(self, x: float) -> int:
        if not self._session or self._session.frame_count <= 1:
            return 0
        tr = self._track_rect()
        ratio = max(0.0, min(1.0, (x - tr.left()) / max(tr.width(), 1.0)))
        return int(round(ratio * (self._session.frame_count - 1)))

    def _frame_to_x(self, frame_idx: int) -> float:
        tr = self._track_rect()
        if not self._session or self._session.frame_count <= 1:
            return tr.left()
        ratio = max(0.0, min(1.0, frame_idx / float(self._session.frame_count - 1)))
        return tr.left() + ratio * tr.width()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._session:
            self._dragging = True
            f = self._x_to_frame(event.position().x())
            self._current_frame = f
            self.seekRequested.emit(f)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._session:
            return
        f = self._x_to_frame(event.position().x())
        self._hover_frame = f
        if self._dragging:
            if f != self._current_frame:
                self._current_frame = f
                self.seekRequested.emit(f)
        self.update()

        # 悬停 Tooltip
        fr = self._session.frame_info(f)
        st = _effective_state(fr)
        t_val = fr.get("t")
        if t_val is None:
            t_val = f / max(self._session.fps, 1e-6)
        st_txt = {"S0": "S0 静默", "S1": "S1 远场", "S2": "S2 近场音频"}.get(st, st)
        tip = (
            f"帧 #{f} / {self._session.frame_count - 1}  ·  {float(t_val):.2f}s\n"
            f"状态：{st_txt}  |  目标 {int(fr.get('count', 0))} "
            f"(近 {int(fr.get('near', 0))} / 中 {int(fr.get('mid', 0))} / 远 {int(fr.get('far', 0))})"
        )
        QToolTip.showText(event.globalPosition().toPoint(), tip, self)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def leaveEvent(self, _event) -> None:
        self._hover_frame = None
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        tr = self._track_rect()
        br = self._band_rect()

        # 1. 上方进度滑轨背景
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["track_bg"]))
        painter.drawRoundedRect(tr, 6, 6)

        if not self._session or self._session.frame_count <= 0:
            painter.setBrush(QColor(COLORS["track_bg"]))
            painter.drawRoundedRect(br, 4, 4)
            return

        total = max(1, self._session.frame_count)
        play_x = self._frame_to_x(self._current_frame)

        # 已播放填充
        filled = QRectF(tr.left(), tr.top(), max(0.0, play_x - tr.left()), tr.height())
        painter.setBrush(QColor(COLORS["accent"]))
        painter.drawRoundedRect(filled, 6, 6)

        # 2. 下方状态色带（合并区间渲染：S0 灰 / S1 黄 / S2 红）
        painter.setBrush(QColor(COLORS["state_s0"]))
        painter.drawRoundedRect(br, 4, 4)

        color_map = {
            "S0": QColor(COLORS["state_s0"]),
            "S1": QColor(COLORS["state_s1"]),
            "S2": QColor(COLORS["state_s2"]),
        }
        for seg in self._session.state_segments:
            x0 = tr.left() + (seg.start_frame / float(total)) * tr.width()
            x1 = tr.left() + ((seg.end_frame + 1) / float(total)) * tr.width()
            seg_w = max(1.5, x1 - x0)
            painter.fillRect(QRectF(x0, br.top(), seg_w, br.height()), color_map.get(seg.state, QColor("#5A6577")))

        # 3. 脉冲刻度竖纹（pulses）
        dur = max(self._session.frame_count / max(self._session.fps, 1e-6), 1e-6)
        pulse_pen = QPen(QColor(255, 255, 255, 215), 1.3)
        painter.setPen(pulse_pen)
        for p in self._session.pulses:
            ratio = max(0.0, min(1.0, p.t / dur))
            px = br.left() + ratio * br.width()
            painter.drawLine(QPointF(px, br.top() + 1), QPointF(px, br.bottom() - 1))

        # 4. 底部色带图例微字
        f = QFont("Microsoft YaHei UI", 8)
        painter.setFont(f)
        painter.setPen(QColor(COLORS["text_muted"]))
        painter.drawText(
            QRectF(br.left(), br.bottom() + 2, br.width(), 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"状态色带：■ 灰 S0 静默   ■ 黄 S1 远场   ■ 红 S2 近场（白竖线 = 演示脉冲 ×{len(self._session.pulses)}）",
        )

        # 5. 悬停参考线
        if self._hover_frame is not None:
            hx = self._frame_to_x(self._hover_frame)
            painter.setPen(QPen(QColor(148, 163, 184, 180), 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(hx, tr.top() - 4), QPointF(hx, br.bottom() + 2))

        # 6. 播放头指针
        painter.setPen(QPen(QColor(COLORS["playhead"]), 2.2))
        painter.drawLine(QPointF(play_x, tr.top() - 5), QPointF(play_x, br.bottom() + 3))
        tri = QPolygonF([
            QPointF(play_x - 6, tr.top() - 8),
            QPointF(play_x + 6, tr.top() - 8),
            QPointF(play_x, tr.top() - 1),
        ])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["accent"]))
        painter.drawPolygon(tri)
