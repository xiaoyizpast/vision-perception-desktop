# -*- coding: utf-8 -*-
"""V4 训练监控视图（Training Monitor）。

严格遵循 docs/06 第 6 节 V4 与第 8 节规范：
- 顶部固定一行免责：「本 run 仅验证链路，指标不代表项目精度」
- 曲线：train.box_loss / val.box_loss / train.cls_loss / val.cls_loss / precision / recall / map50 / map50_95
- best epoch 竖线标记（best.epoch）
- 早停徽标：early_stopped == true 时显示「早停：{epochs_run}/{planned_epochs}」
- 产物画廊：仅展示本地实际存在的图片（缺图隐藏，绝不显示破图）
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data_loader import RunBundle
from theme import COLORS
from widgets.common import DisclaimerBanner, ImagePreviewDialog, KpiCard, SectionCard


class MetricCurveCanvas(QWidget):
    """矢量多序列训练曲线图（支持 best epoch 竖线标记与鼠标十字准星 Hover 提示）。"""

    def __init__(self, title: str, y_fixed_01: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._title = title
        self._y_fixed_01 = y_fixed_01
        self._epochs: List[int] = []
        self._series: List[Tuple[str, QColor, List[Optional[float]]]] = []
        self._best_epoch: Optional[int] = None
        self._hover_idx: Optional[int] = None
        self.setMinimumHeight(270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def set_data(
        self,
        epochs: List[int],
        series: List[Tuple[str, str, List[Optional[float]]]],
        best_epoch: Optional[int],
    ) -> None:
        self._epochs = epochs
        self._series = [(name, QColor(hex_c), vals) for name, hex_c, vals in series]
        self._best_epoch = best_epoch
        self._hover_idx = None
        self.update()

    def _plot_rect(self) -> QRectF:
        return QRectF(54.0, 58.0, max(60.0, self.width() - 72.0), max(80.0, self.height() - 92.0))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._epochs:
            return
        pr = self._plot_rect()
        x = event.position().x()
        if pr.left() <= x <= pr.right():
            n = len(self._epochs)
            if n == 1:
                idx = 0
            else:
                ratio = (x - pr.left()) / max(pr.width(), 1.0)
                idx = max(0, min(n - 1, int(round(ratio * (n - 1)))))
            if idx != self._hover_idx:
                self._hover_idx = idx
                self.update()
        else:
            if self._hover_idx is not None:
                self._hover_idx = None
                self.update()

    def leaveEvent(self, _event) -> None:
        if self._hover_idx is not None:
            self._hover_idx = None
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(COLORS["bg_chart"]))

        # 外框
        painter.setPen(QPen(QColor(COLORS["border"]), 1.0))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)

        # 标题与第二行图例（互不遮挡）
        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Bold))
        painter.setPen(QColor(COLORS["text_primary"]))
        painter.drawText(QRectF(14, 8, self.width() - 28, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._title)

        lx = 14.0
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        for name, col, _ in self._series:
            tw = painter.fontMetrics().horizontalAdvance(name)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(col)
            painter.drawEllipse(QPointF(lx + 5, 41), 4.0, 4.0)
            painter.setPen(QColor(COLORS["text_secondary"]))
            painter.drawText(QRectF(lx + 13, 31, tw + 8, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            lx += tw + 26

        pr = self._plot_rect()
        if not self._epochs or not self._series:
            painter.setPen(QColor(COLORS["text_muted"]))
            painter.drawText(pr, Qt.AlignmentFlag.AlignCenter, "暂无训练曲线数据")
            return

        # 计算 Y 范围
        all_vals = [v for _, _, vals in self._series for v in vals if isinstance(v, (int, float))]
        if not all_vals:
            painter.setPen(QColor(COLORS["text_muted"]))
            painter.drawText(pr, Qt.AlignmentFlag.AlignCenter, "数值全为空")
            return

        if self._y_fixed_01:
            y_min, y_max = 0.0, 1.0
        else:
            raw_min, raw_max = min(all_vals), max(all_vals)
            span = max(raw_max - raw_min, 1e-4)
            y_min = max(0.0, raw_min - span * 0.1)
            y_max = raw_max + span * 0.12

        def x_of(idx: int) -> float:
            if len(self._epochs) <= 1:
                return pr.center().x()
            return pr.left() + (idx / float(len(self._epochs) - 1)) * pr.width()

        def y_of(val: float) -> float:
            ratio = (val - y_min) / max(y_max - y_min, 1e-9)
            return pr.bottom() - ratio * pr.height()

        # 网格线与 Y 刻度
        painter.setFont(QFont("Microsoft YaHei UI", 8))
        for step in range(5):
            r = step / 4.0
            gy = pr.bottom() - r * pr.height()
            gv = y_min + r * (y_max - y_min)
            painter.setPen(QPen(QColor(COLORS["grid_line"]), 1.0, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(pr.left(), gy), QPointF(pr.right(), gy))
            painter.setPen(QColor(COLORS["text_muted"]))
            painter.drawText(QRectF(4, gy - 9, 46, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{gv:.2f}")

        # X 刻度
        n = len(self._epochs)
        tick_step = max(1, n // 8)
        for idx in range(0, n, tick_step):
            gx = x_of(idx)
            painter.setPen(QColor(COLORS["text_muted"]))
            painter.drawText(QRectF(gx - 18, pr.bottom() + 6, 36, 18), Qt.AlignmentFlag.AlignCenter, f"E{self._epochs[idx]}")
        if (n - 1) % tick_step != 0:
            gx = x_of(n - 1)
            painter.drawText(QRectF(gx - 18, pr.bottom() + 6, 36, 18), Qt.AlignmentFlag.AlignCenter, f"E{self._epochs[-1]}")

        # Best Epoch 竖线标记
        if self._best_epoch is not None and self._best_epoch in self._epochs:
            b_idx = self._epochs.index(self._best_epoch)
            bx = x_of(b_idx)
            painter.setPen(QPen(QColor("#22C55E"), 1.8, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(bx, pr.top()), QPointF(bx, pr.bottom()))
            tag_rect = QRectF(min(bx + 4, pr.right() - 88), pr.top() + 2, 86, 20)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(22, 163, 74, 215))
            painter.drawRoundedRect(tag_rect, 4, 4)
            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(QFont("Microsoft YaHei UI", 8, QFont.Weight.Bold))
            painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, f"BEST E{self._best_epoch}")

        # 绘制各条折线
        for _name, col, vals in self._series:
            pen = QPen(col, 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            started = False
            pts_drawn: List[QPointF] = []
            for idx, v in enumerate(vals):
                if v is None:
                    started = False
                    continue
                pt = QPointF(x_of(idx), y_of(float(v)))
                pts_drawn.append(pt)
                if not started:
                    path.moveTo(pt)
                    started = True
                else:
                    path.lineTo(pt)
            painter.drawPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(col)
            for pt in pts_drawn:
                painter.drawEllipse(pt, 3.0, 3.0)

        # Hover 十字线与信息浮框
        if self._hover_idx is not None and 0 <= self._hover_idx < len(self._epochs):
            hx = x_of(self._hover_idx)
            painter.setPen(QPen(QColor(148, 163, 184, 190), 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(hx, pr.top()), QPointF(hx, pr.bottom()))

            lines = [f"Epoch {self._epochs[self._hover_idx]}"]
            for name, col, vals in self._series:
                v = vals[self._hover_idx] if self._hover_idx < len(vals) else None
                lines.append(f"{name}: {v:.4f}" if isinstance(v, (int, float)) else f"{name}: —")

            box_w = 185.0
            box_h = 20.0 * len(lines) + 12.0
            bx = hx + 12 if (hx + 12 + box_w) < pr.right() else hx - box_w - 12
            by = pr.top() + 26
            box = QRectF(bx, by, box_w, box_h)
            painter.setPen(QPen(QColor(COLORS["accent"]), 1.0))
            painter.setBrush(QColor(COLORS["tooltip_bg"]))
            painter.drawRoundedRect(box, 6, 6)
            painter.setFont(QFont("Microsoft YaHei UI", 9))
            painter.setPen(QColor(COLORS["tooltip_fg"]))
            for i, line in enumerate(lines):
                painter.drawText(QRectF(box.left() + 8, box.top() + 6 + i * 20, box_w - 16, 20), Qt.AlignmentFlag.AlignVCenter, line)


class TrainingView(QWidget):
    """V4 训练监控主视图。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._runs: List[RunBundle] = []
        self._run: Optional[RunBundle] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        # 契约强制顶部固定一行免责
        root.addWidget(DisclaimerBanner("本 run 仅验证链路，指标不代表项目精度"))

        # 选择条 + 早停徽标
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        run_lbl = QLabel("训练运行记录：")
        run_lbl.setObjectName("TitleText")
        top_bar.addWidget(run_lbl)
        self._cmb_run = QComboBox()
        self._cmb_run.setMinimumWidth(260)
        self._cmb_run.currentIndexChanged.connect(self._on_run_selected)
        top_bar.addWidget(self._cmb_run)

        self._early_badge = QLabel("")
        self._early_badge.setObjectName("EarlyBadge")
        self._early_badge.setVisible(False)
        top_bar.addWidget(self._early_badge)

        self._status_badge = QLabel("")
        self._status_badge.setObjectName("PillNeutral")
        top_bar.addWidget(self._status_badge)
        top_bar.addStretch(1)
        root.addLayout(top_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 6, 0)
        body_lay.setSpacing(12)

        # 空态卡片
        self._empty_card = SectionCard("暂无训练监控数据")
        el = QLabel("数据目录下未找到 *.run.json 文件。可用 tools/export_run.py 导出训练记录后刷新。")
        el.setWordWrap(True)
        el.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self._empty_card.root_layout.addWidget(el)
        body_lay.addWidget(self._empty_card)

        # 内容容器
        self._content = QWidget()
        c_lay = QVBoxLayout(self._content)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(12)

        # Best Epoch KPI 网格
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)
        self._k_best_ep = KpiCard("Best Epoch", "—", "")
        self._k_map50 = KpiCard("Best mAP50", "—", "仅链路验证值")
        self._k_map95 = KpiCard("Best mAP50-95", "—", "仅链路验证值")
        self._k_pr = KpiCard("Best Precision / Recall", "—", "仅链路验证值")
        for k in [self._k_best_ep, self._k_map50, self._k_map95, self._k_pr]:
            kpi_row.addWidget(k)
        c_lay.addLayout(kpi_row)

        # 训练配置与备注卡
        cfg_card = SectionCard("训练超参与运行摘要")
        self._lbl_cfg = QLabel("—")
        self._lbl_cfg.setObjectName("SubText")
        self._lbl_cfg.setWordWrap(True)
        cfg_card.root_layout.addWidget(self._lbl_cfg)
        c_lay.addWidget(cfg_card)

        # 双栏曲线：损失 + 指标
        chart_row = QHBoxLayout()
        chart_row.setSpacing(12)
        self._loss_chart = MetricCurveCanvas("训练 / 验证损失曲线（Box / Cls Loss）", y_fixed_01=False)
        self._metric_chart = MetricCurveCanvas("验证指标曲线（Precision / Recall / mAP）", y_fixed_01=True)
        chart_row.addWidget(self._loss_chart, 1)
        chart_row.addWidget(self._metric_chart, 1)
        c_lay.addLayout(chart_row)

        # 学习率曲线
        self._lr_chart = MetricCurveCanvas("学习率调度曲线 (lr)", y_fixed_01=False)
        self._lr_chart.setMinimumHeight(200)
        c_lay.addWidget(self._lr_chart)

        # 产物画廊（仅展示存在的图片；缺图隐藏）
        self._art_card = SectionCard("训练产物画廊", "点击查看大图；缺失图片自动隐藏")
        self._art_grid_host = QWidget()
        self._art_grid = QGridLayout(self._art_grid_host)
        self._art_grid.setSpacing(12)
        self._art_grid.setContentsMargins(0, 4, 0, 4)
        self._art_card.root_layout.addWidget(self._art_grid_host)
        self._lbl_other_files = QLabel("")
        self._lbl_other_files.setWordWrap(True)
        self._lbl_other_files.setStyleSheet(f"font-size: 14px; color: {COLORS['text_muted']};")
        self._art_card.root_layout.addWidget(self._lbl_other_files)
        c_lay.addWidget(self._art_card)

        body_lay.addWidget(self._content)
        body_lay.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def set_runs(self, runs: List[RunBundle]) -> None:
        self._runs = runs
        self._cmb_run.blockSignals(True)
        self._cmb_run.clear()
        for r in runs:
            self._cmb_run.addItem(f"{r.run_id}  ({r.raw.get('epochs_run', 0)} 轮)")
        self._cmb_run.blockSignals(False)

        if runs:
            self._empty_card.setVisible(False)
            self._content.setVisible(True)
            self._cmb_run.setCurrentIndex(0)
            self._render_run(runs[0])
        else:
            self._empty_card.setVisible(True)
            self._content.setVisible(False)
            self._early_badge.setVisible(False)
            self._status_badge.setText("无运行记录")

    def _on_run_selected(self, idx: int) -> None:
        if 0 <= idx < len(self._runs):
            self._render_run(self._runs[idx])

    def _clear_artifacts(self) -> None:
        while self._art_grid.count():
            item = self._art_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_run(self, rb: RunBundle) -> None:
        self._run = rb
        raw = rb.raw
        early = bool(raw.get("early_stopped"))
        ep_run = raw.get("epochs_run", 0)
        ep_plan = raw.get("planned_epochs")
        if early:
            plan_txt = str(ep_plan) if ep_plan is not None else "?"
            self._early_badge.setText(f"[早停] {ep_run}/{plan_txt}")
            self._early_badge.setVisible(True)
        else:
            self._early_badge.setVisible(False)

        st_map = {"early_stopped": "状态：已早停", "completed": "状态：已完成", "unknown": "状态：未知"}
        self._status_badge.setText(st_map.get(raw.get("status", "unknown"), "状态：未知"))

        best = raw.get("best") or {}
        best_ep = best.get("epoch")
        self._k_best_ep.set_value(
            f"Epoch {best_ep}" if best_ep is not None else "—",
            f"实际运行 {ep_run} / 计划 {ep_plan or '—'} 轮",
            "#4ADE80",
        )
        fmt = lambda v: f"{float(v):.4f}" if isinstance(v, (int, float)) else "—"
        self._k_map50.set_value(fmt(best.get("map50")), "Best Epoch mAP50（不代表项目精度）", COLORS["accent"])
        self._k_map95.set_value(fmt(best.get("map50_95")), "Best Epoch mAP50-95（不代表项目精度）")
        self._k_pr.set_value(
            f"{fmt(best.get('precision'))} / {fmt(best.get('recall'))}",
            "Precision / Recall（链路验证值）",
        )

        m = raw.get("model") or {}
        self._lbl_cfg.setText(
            f"初始权重：{m.get('init_weights', '—')}   |   输入尺寸：{m.get('imgsz', '—')}   |   "
            f"Batch：{m.get('batch', '—')}   |   优化器：{m.get('optimizer', '—')}   |   "
            f"Patience：{m.get('patience', '—')}   |   Seed：{m.get('seed', '—')}\n"
            f"数据集配置：{raw.get('data', '—')}   |   导出时间：{raw.get('created_at', '—')}\n"
            f"备注：{raw.get('notes') or '无'}"
        )

        # 曲线数据组装
        ep_rows = raw.get("epochs") or []
        xs = [int(e["epoch"]) for e in ep_rows]
        t_box = [(e.get("train") or {}).get("box_loss") for e in ep_rows]
        v_box = [(e.get("val") or {}).get("box_loss") for e in ep_rows]
        t_cls = [(e.get("train") or {}).get("cls_loss") for e in ep_rows]
        v_cls = [(e.get("val") or {}).get("cls_loss") for e in ep_rows]

        self._loss_chart.set_data(
            xs,
            [
                ("train.box_loss", COLORS["chart_1"], t_box),
                ("val.box_loss", COLORS["chart_2"], v_box),
                ("train.cls_loss", COLORS["chart_4"], t_cls),
                ("val.cls_loss", COLORS["chart_5"], v_cls),
            ],
            best_ep,
        )

        prec = [(e.get("metrics") or {}).get("precision") for e in ep_rows]
        rec = [(e.get("metrics") or {}).get("recall") for e in ep_rows]
        m50 = [(e.get("metrics") or {}).get("map50") for e in ep_rows]
        m95 = [(e.get("metrics") or {}).get("map50_95") for e in ep_rows]
        self._metric_chart.set_data(
            xs,
            [
                ("precision", COLORS["chart_1"], prec),
                ("recall", COLORS["chart_3"], rec),
                ("map50", COLORS["chart_6"], m50),
                ("map50_95", COLORS["chart_2"], m95),
            ],
            best_ep,
        )

        lrs = [e.get("lr") for e in ep_rows]
        self._lr_chart.set_data(xs, [("lr", COLORS["chart_4"], lrs)], best_ep)

        # 产物画廊（缺图自动隐藏）
        self._clear_artifacts()
        img_exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        img_arts: List[Tuple[str, Path, int]] = []
        other_arts: List[Tuple[str, Path, int]] = []
        for rel, path, sz in rb.existing_artifacts:
            if not path.is_file():
                continue
            if path.suffix.lower() in img_exts:
                img_arts.append((rel, path, sz))
            else:
                other_arts.append((rel, path, sz))

        if not img_arts and not other_arts:
            self._art_card.setVisible(False)
            return
        self._art_card.setVisible(True)

        cols = 3
        for idx, (rel, path, _sz) in enumerate(img_arts):
            pix = QPixmap(str(path))
            if pix.isNull():
                continue
            card = QFrame()
            card.setObjectName("CardAlt")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 10, 10, 10)
            cl.setSpacing(6)
            lbl_img = QLabel()
            lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_img.setMinimumHeight(180)
            lbl_img.setStyleSheet(f"background-color: {COLORS['bg_canvas']}; border-radius: 6px;")
            lbl_img.setPixmap(
                pix.scaled(310, 210, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
            btn = QPushButton(f"查看 {rel}")
            btn.clicked.connect(lambda _=False, r=rel, p=path: ImagePreviewDialog(f"训练产物 · {r}", p, self).exec())
            cl.addWidget(lbl_img)
            cl.addWidget(btn)
            self._art_grid.addWidget(card, idx // cols, idx % cols)

        if other_arts:
            txt = "其他本地产物：" + "   ·   ".join(f"{rel} ({sz / 1024:.1f} KB)" for rel, _, sz in other_arts)
            self._lbl_other_files.setText(txt)
            self._lbl_other_files.setVisible(True)
        else:
            self._lbl_other_files.setVisible(False)

    def refresh_theme(self) -> None:
        for k in (self._k_best_ep, self._k_map50, self._k_map95, self._k_pr):
            k.refresh_theme()
        if self._run:
            self._render_run(self._run)
        else:
            self._loss_chart.update()
            self._metric_chart.update()
            self._lr_chart.update()
