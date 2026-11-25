# -*- coding: utf-8 -*-
"""V5 模型对比视图（Model Benchmark）。

严格遵循 docs/06 第 6 节 V5 规范：
- 消费 out/compare/compare.json（n / s / m × field_v1 / field_v2）
- 可排序对比表格：按「耗时 ms/帧（越低越快）」与「有检出帧占比（越高检出越充分）」两列分别高亮，
  绝不合成单一总分；不把 detect_rate 标成准确率
- 双栏可视化对比条形图
- 对比帧三联并排检视器：out/compare/<video>_f<frame>_<model>.jpg（yolo26n / s / m 三张并排），点击查看大图
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data_loader import CompareFrameGroup
from theme import COLORS
from widgets.common import DisclaimerBanner, ImagePreviewDialog, SectionCard


class HorizontalBarChart(QWidget):
    """简洁现代的分组横向对比条形图。"""

    def __init__(self, title: str, unit: str, lower_is_better: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._title = title
        self._unit = unit
        self._lower_is_better = lower_is_better
        self._items: List[Tuple[str, float, str, bool]] = []  # (label, value, color_hex, is_best)
        self.setMinimumHeight(230)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_items(self, items: List[Tuple[str, float, str, bool]]) -> None:
        self._items = items
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(COLORS["bg_chart"]))
        painter.setPen(QPen(QColor(COLORS["border"]), 1.0))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)

        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        painter.setPen(QColor(COLORS["text_primary"]))
        painter.drawText(QRectF(14, 10, self.width() - 28, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._title)

        if not self._items:
            painter.setPen(QColor(COLORS["text_muted"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无横评数据")
            return

        max_v = max(max(v for _, v, _, _ in self._items), 1e-6)
        top_y = 44.0
        row_h = max(24.0, (self.height() - top_y - 14.0) / max(len(self._items), 1))
        label_w = 155.0
        val_w = 94.0
        bar_max_w = max(40.0, self.width() - label_w - val_w - 28.0)

        painter.setFont(QFont("Microsoft YaHei UI", 9))
        for i, (label, val, col_hex, is_best) in enumerate(self._items):
            y = top_y + i * row_h
            bh = min(18.0, row_h - 8.0)
            by = y + (row_h - bh) * 0.5

            painter.setPen(QColor(COLORS["text_primary"]) if is_best else QColor(COLORS["text_secondary"]))
            painter.drawText(QRectF(12, y, label_w - 8, row_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, label)

            # 轨道底
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS["track_bg"]))
            painter.drawRoundedRect(QRectF(label_w + 8, by, bar_max_w, bh), 5, 5)

            # 实际条
            bw = max(4.0, (val / max_v) * bar_max_w)
            painter.setBrush(QColor(col_hex))
            painter.drawRoundedRect(QRectF(label_w + 8, by, bw, bh), 5, 5)

            # 数值
            badge = " ★" if is_best else ""
            if is_best and self._lower_is_better:
                val_col = COLORS["best_ms_fg"]
            elif is_best:
                val_col = COLORS["best_rate_fg"]
            else:
                val_col = COLORS["text_primary"]
            painter.setPen(QColor(val_col))
            painter.drawText(
                QRectF(label_w + 14 + bar_max_w, y, val_w, row_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                f"{val:.1f}{self._unit}{badge}",
            )


class CompareView(QWidget):
    """V5 模型对比主视图。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: List[Dict[str, Any]] = []
        self._groups: List[CompareFrameGroup] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        root.addWidget(
            DisclaimerBanner(
                "横评表格按「ms/帧（越低越快）」与「有检出帧占比（非准确率）」两列分别高亮，不合成单一总分；"
                "速度测于本机 RTX 5060 Laptop，不代表端侧部署帧率。"
            )
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 6, 0)
        body_lay.setSpacing(12)

        # 空态卡
        self._empty_card = SectionCard("暂无模型横评数据")
        el = QLabel("未找到 out/compare/compare.json 或 data/web/compare.json。")
        el.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self._empty_card.root_layout.addWidget(el)
        body_lay.addWidget(self._empty_card)

        self._content = QWidget()
        c_lay = QVBoxLayout(self._content)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(12)

        # 1. 可排序横评表格
        tbl_card = SectionCard("YOLO26 n / s / m 模型横评表", "点击列头可排序 · 绿色=同视频速度最优，蓝色=同视频有检出帧占比最优")
        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels([
            "视频", "模型", "尺寸", "阈值", "帧数",
            "检出帧占比(%)", "检出人次", "置信中位", "耗时(ms/帧)",
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSortingEnabled(True)
        self._table.setMinimumHeight(250)
        from PySide6.QtWidgets import QHeaderView
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tbl_card.root_layout.addWidget(self._table)
        c_lay.addWidget(tbl_card)

        # 2. 双栏对比条形图
        chart_row = QHBoxLayout()
        chart_row.setSpacing(12)
        self._bar_ms = HorizontalBarChart("单帧耗时对比（ms/帧，★ 越低越快）", " ms", lower_is_better=True)
        self._bar_rate = HorizontalBarChart("有检出帧占比对比（%，★ 非准确率）", "%", lower_is_better=False)
        chart_row.addWidget(self._bar_ms, 1)
        chart_row.addWidget(self._bar_rate, 1)
        c_lay.addLayout(chart_row)

        # 3. 对比帧三联并排检视器
        self._frames_card = SectionCard("同帧三模型并排对比", "yolo26n / yolo26s / yolo26m 逐帧检出对比（点击看原图）")
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("选择对比帧："))
        self._cmb_group = QComboBox()
        self._cmb_group.setMinimumWidth(280)
        self._cmb_group.currentIndexChanged.connect(self._on_group_changed)
        sel_row.addWidget(self._cmb_group)
        sel_row.addStretch(1)
        self._frames_card.root_layout.addLayout(sel_row)

        self._triptych = QHBoxLayout()
        self._triptych.setSpacing(12)
        self._frames_card.root_layout.addLayout(self._triptych)
        c_lay.addWidget(self._frames_card)

        body_lay.addWidget(self._content)
        body_lay.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def set_data(self, rows: List[Dict[str, Any]], groups: List[CompareFrameGroup]) -> None:
        self._rows = rows
        self._groups = groups

        if not rows and not groups:
            self._empty_card.setVisible(True)
            self._content.setVisible(False)
            return

        self._empty_card.setVisible(False)
        self._content.setVisible(True)
        self._populate_table(rows)
        self._populate_charts(rows)
        self._populate_groups(groups)

    def _video_extrema(self, rows: List[Dict[str, Any]]) -> Tuple[Dict[str, float], Dict[str, float]]:
        best_ms: Dict[str, float] = {}
        best_rate: Dict[str, float] = {}
        for r in rows:
            v = str(r.get("video", ""))
            ms = float(r.get("ms_per_frame", 1e9))
            dr = float(r.get("detect_rate", -1.0))
            if v not in best_ms or ms < best_ms[v]:
                best_ms[v] = ms
            if v not in best_rate or dr > best_rate[v]:
                best_rate[v] = dr
        return best_ms, best_rate

    def _populate_table(self, rows: List[Dict[str, Any]]) -> None:
        best_ms, best_rate = self._video_extrema(rows)
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vid = str(r.get("video", "—"))
            mdl = str(r.get("model", "—"))
            dr = float(r.get("detect_rate", 0.0))
            ms = float(r.get("ms_per_frame", 0.0))
            is_best_dr = abs(dr - best_rate.get(vid, -1.0)) < 1e-6
            is_best_ms = abs(ms - best_ms.get(vid, -1.0)) < 1e-6

            vals = [
                vid,
                mdl,
                int(r.get("imgsz", 0)),
                float(r.get("conf", 0.0)),
                int(r.get("frames", 0)),
                round(dr * 100.0, 2),
                int(r.get("persons", 0)),
                float(r.get("conf_med", 0.0)),
                ms,
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem()
                if c == 5:
                    item.setData(Qt.ItemDataRole.DisplayRole, v)
                    if is_best_dr:
                        item.setBackground(QColor(COLORS["best_rate_bg"]))
                        item.setForeground(QColor(COLORS["best_rate_fg"]))
                        item.setToolTip("同视频有检出帧占比最高（非准确率）")
                elif c == 8:
                    item.setData(Qt.ItemDataRole.DisplayRole, v)
                    if is_best_ms:
                        item.setBackground(QColor(COLORS["best_ms_bg"]))
                        item.setForeground(QColor(COLORS["best_ms_fg"]))
                        item.setToolTip("同视频单帧耗时最低（速度最优）")
                else:
                    item.setData(Qt.ItemDataRole.DisplayRole, v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(i, c, item)

        self._table.setSortingEnabled(True)

    def _populate_charts(self, rows: List[Dict[str, Any]]) -> None:
        best_ms, best_rate = self._video_extrema(rows)
        model_col = {"yolo26n": "#22C55E", "yolo26s": "#38BDF8", "yolo26m": "#F97316"}
        ms_items = []
        rate_items = []
        for r in rows:
            vid = str(r.get("video", ""))
            mdl = str(r.get("model", ""))
            lbl = f"{vid} · {mdl}"
            ms = float(r.get("ms_per_frame", 0.0))
            dr = float(r.get("detect_rate", 0.0))
            col = model_col.get(mdl, "#A855F7")
            ms_items.append((lbl, ms, col, abs(ms - best_ms.get(vid, -1.0)) < 1e-6))
            rate_items.append((lbl, dr * 100.0, col, abs(dr - best_rate.get(vid, -1.0)) < 1e-6))
        self._bar_ms.set_items(ms_items)
        self._bar_rate.set_items(rate_items)

    def _populate_groups(self, groups: List[CompareFrameGroup]) -> None:
        self._cmb_group.blockSignals(True)
        self._cmb_group.clear()
        for g in groups:
            self._cmb_group.addItem(f"{g.video}  ·  帧 #{g.frame}  ({len(g.images)} 模型)")
        self._cmb_group.blockSignals(False)

        if not groups:
            self._frames_card.setVisible(False)
            return
        self._frames_card.setVisible(True)
        self._cmb_group.setCurrentIndex(0)
        self._render_group(groups[0])

    def _on_group_changed(self, idx: int) -> None:
        if 0 <= idx < len(self._groups):
            self._render_group(self._groups[idx])

    def _clear_triptych(self) -> None:
        while self._triptych.count():
            item = self._triptych.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_group(self, group: CompareFrameGroup) -> None:
        self._clear_triptych()
        order = ["yolo26n", "yolo26s", "yolo26m"]
        keys = [k for k in order if k in group.images] + [k for k in sorted(group.images) if k not in order]
        for mdl in keys:
            path = group.images[mdl]
            if not path.is_file():
                continue
            pix = QPixmap(str(path))
            if pix.isNull():
                continue
            card = QFrame()
            card.setObjectName("CardAlt")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 10, 10, 10)
            cl.setSpacing(6)

            hdr = QLabel(f"{mdl}   ·   帧 #{group.frame}")
            hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hdr.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLORS['accent'] if mdl == 'yolo26s' else COLORS['text_primary']};")
            cl.addWidget(hdr)

            img_lbl = QLabel()
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_lbl.setStyleSheet(f"background-color: {COLORS['bg_canvas']}; border-radius: 6px;")
            img_lbl.setPixmap(
                pix.scaled(310, 460, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
            cl.addWidget(img_lbl)

            btn = QPushButton("高清原图")
            btn.clicked.connect(
                lambda _=False, m=mdl, p=path: ImagePreviewDialog(f"模型对比 · {group.video} 帧 #{group.frame} · {m}", p, self).exec()
            )
            cl.addWidget(btn)
            self._triptych.addWidget(card, 1)

    def refresh_theme(self) -> None:
        if self._rows:
            self._populate_table(self._rows)
            self._populate_charts(self._rows)
        if self._groups and 0 <= self._cmb_group.currentIndex() < len(self._groups):
            self._render_group(self._groups[self._cmb_group.currentIndex()])
        self._bar_ms.update()
        self._bar_rate.update()
