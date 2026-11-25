# -*- coding: utf-8 -*-
"""V3 画质体检视图（Video Quality）。

严格遵循 docs/06 第 6 节 V3 与第 8 节规范：
- 客观展示 session.quality 指标（亮度中位数/P10、对比度中位数、清晰度中位数/P10、发虚帧占比、欠曝/过曝像素占比）
- 只做客观展示，不做阈值判定（合格/不合格判定阈值尚未设定）
- 展示 out/probe/*.png 参考抽样帧画廊，点击查看大图；缺图隐藏不显示破图
- 当 quality == null 时显示规范空态提示
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from data_loader import SessionBundle
from theme import COLORS
from widgets.common import DisclaimerBanner, ImagePreviewDialog, KpiCard, SectionCard


class QualityView(QWidget):
    """V3 画质体检视图。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._session: Optional[SessionBundle] = None
        self._probe_images: List[Path] = []
        self._show_all_probes: bool = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        root.addWidget(
            DisclaimerBanner("画质体检仅客观展示 tools/video_quality.py 的聚合统计值与参考抽样帧，不做合格/不合格阈值判定。")
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self._body_lay = QVBoxLayout(body)
        self._body_lay.setContentsMargins(0, 0, 6, 0)
        self._body_lay.setSpacing(12)

        # 空态提示卡（quality == null）
        self._empty_card = SectionCard("当前会话无画质体检数据")
        self._empty_lbl = QLabel("当前选中会话的 quality 字段为 null（例如合成样例 demo_synthetic_bus 未跑画质体检）。请切换至 field_v1_s 或 field_v2_s 查看真实视频画质指标。")
        self._empty_lbl.setObjectName("SubText")
        self._empty_lbl.setWordWrap(True)
        self._empty_card.root_layout.addWidget(self._empty_lbl)
        self._body_lay.addWidget(self._empty_card)

        # 指标卡片网格
        self._metrics_card = SectionCard("视频画质聚合统计", "客观观测值")
        grid = QGridLayout()
        grid.setSpacing(10)
        self._k_bright = KpiCard("亮度中位数 (0–255)", "—", "")
        self._k_contrast = KpiCard("对比度中位数", "—", "")
        self._k_sharp = KpiCard("清晰度中位数 (Laplacian)", "—", "")
        self._k_blur = KpiCard("发虚帧占比", "—", "仅统计值，无判定阈值")
        self._k_dark = KpiCard("暗部像素占比中位数", "—", "")
        self._k_blown = KpiCard("过曝像素占比中位数", "—", "")
        self._k_meta = KpiCard("抽样视频信息", "—", "")

        grid.addWidget(self._k_bright, 0, 0)
        grid.addWidget(self._k_contrast, 0, 1)
        grid.addWidget(self._k_sharp, 0, 2)
        grid.addWidget(self._k_blur, 0, 3)
        grid.addWidget(self._k_dark, 1, 0)
        grid.addWidget(self._k_blown, 1, 1)
        grid.addWidget(self._k_meta, 1, 2, 1, 2)
        self._metrics_card.root_layout.addLayout(grid)
        self._body_lay.addWidget(self._metrics_card)

        # 参考帧画廊（out/probe/*.png）
        self._probe_card = SectionCard("参考抽样帧画廊", "来自 out/probe/*.png，点击查看大图")
        bar = QHBoxLayout()
        self._lbl_probe_count = QLabel("")
        self._lbl_probe_count.setObjectName("SubText")
        bar.addWidget(self._lbl_probe_count)
        bar.addStretch(1)
        self._btn_toggle_all = QPushButton("显示全部参考帧")
        self._btn_toggle_all.setObjectName("ChipBtn")
        self._btn_toggle_all.setCheckable(True)
        self._btn_toggle_all.toggled.connect(self._on_toggle_all)
        bar.addWidget(self._btn_toggle_all)
        self._probe_card.root_layout.addLayout(bar)

        self._gallery_host = QWidget()
        self._gallery_grid = QGridLayout(self._gallery_host)
        self._gallery_grid.setSpacing(12)
        self._gallery_grid.setContentsMargins(0, 4, 0, 4)
        self._probe_card.root_layout.addWidget(self._gallery_host)
        self._body_lay.addWidget(self._probe_card)

        self._body_lay.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def set_probe_images(self, images: List[Path]) -> None:
        self._probe_images = [p for p in images if p.is_file()]
        self._rebuild_gallery()

    def set_session(self, session: Optional[SessionBundle]) -> None:
        self._session = session
        q = session.quality if session else None

        if not q:
            self._empty_card.setVisible(True)
            self._metrics_card.setVisible(False)
        else:
            self._empty_card.setVisible(False)
            self._metrics_card.setVisible(True)

            def fmt(val, digits=1, suffix=""):
                return f"{float(val):.{digits}f}{suffix}" if isinstance(val, (int, float)) else "—"

            self._k_bright.set_value(
                fmt(q.get("brightness_med"), 1),
                f"P10 分位：{fmt(q.get('brightness_p10'), 1)}",
                COLORS["accent"],
            )
            self._k_contrast.set_value(fmt(q.get("contrast_med"), 1), "灰度标准差中位数")
            self._k_sharp.set_value(
                fmt(q.get("sharpness_med"), 1),
                f"P10 分位：{fmt(q.get('sharpness_p10'), 1)}",
            )
            blur = q.get("blurry_frame_ratio")
            self._k_blur.set_value(
                f"{float(blur) * 100:.1f}%" if isinstance(blur, (int, float)) else "—",
                "客观统计占比（无阈值判定）",
            )
            dark = q.get("dark_pixel_ratio_med")
            self._k_dark.set_value(
                f"{float(dark) * 100:.2f}%" if isinstance(dark, (int, float)) else "—",
                "像素值偏暗占比中位数",
            )
            blown = q.get("blown_pixel_ratio_med")
            self._k_blown.set_value(
                f"{float(blown) * 100:.2f}%" if isinstance(blown, (int, float)) else "—",
                "像素值过曝占比中位数",
            )
            v_info = session.video if session else None
            res_txt = f"{v_info['width']}×{v_info['height']} px" if v_info else "—"
            self._k_meta.set_value(
                f"{q.get('frames', '—')} 帧 · {fmt(q.get('fps'), 2, ' fps')}",
                f"源：{q.get('video', '—')}  |  分辨率：{res_txt}",
            )

        self._rebuild_gallery()

    def _on_toggle_all(self, checked: bool) -> None:
        self._show_all_probes = checked
        self._btn_toggle_all.setText("仅看当前会话相关帧" if checked else "显示全部参考帧")
        self._rebuild_gallery()

    def _clear_gallery(self) -> None:
        while self._gallery_grid.count():
            item = self._gallery_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _rebuild_gallery(self) -> None:
        self._clear_gallery()
        valid = [p for p in self._probe_images if p.is_file()]
        if not valid:
            self._probe_card.setVisible(False)
            return

        self._probe_card.setVisible(True)
        filtered = valid
        if not self._show_all_probes and self._session:
            sid = self._session.session_id.lower()
            prefix = "v1" if "v1" in sid else ("v2" if "v2" in sid else "")
            if prefix:
                matched = [p for p in valid if p.name.lower().startswith(prefix)]
                if matched:
                    filtered = matched

        self._lbl_probe_count.setText(f"共展示 {len(filtered)} 张参考抽样帧（总库 {len(valid)} 张）")

        cols = 4
        for idx, path in enumerate(filtered):
            card = QFrame()
            card.setObjectName("CardAlt")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 10, 10, 10)
            cl.setSpacing(6)

            pix = QPixmap(str(path))
            if pix.isNull():
                continue
            thumb = pix.scaled(220, 260, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            img_lbl = QLabel()
            img_lbl.setPixmap(thumb)
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_lbl.setMinimumHeight(210)
            img_lbl.setStyleSheet(f"background: {COLORS['bg_canvas']}; border-radius: 6px;")

            # 点击打开高清预览
            open_btn = QPushButton(f"查看 {path.name}")
            open_btn.clicked.connect(lambda _=False, p=path: ImagePreviewDialog(f"画质参考帧 · {p.name}", p, self).exec())

            cl.addWidget(img_lbl)
            cl.addWidget(open_btn)
            self._gallery_grid.addWidget(card, idx // cols, idx % cols)

    def refresh_theme(self) -> None:
        for k in (self._k_bright, self._k_contrast, self._k_sharp, self._k_blur, self._k_dark, self._k_blown, self._k_meta):
            k.refresh_theme()
        self._rebuild_gallery()
