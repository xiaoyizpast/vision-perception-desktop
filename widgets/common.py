# -*- coding: utf-8 -*-
"""通用现代组件：卡片、KPI 指标卡、免责提示条、高清图片预览弹窗（完全支持浅/深双主题切换）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from theme import COLORS


class SectionCard(QFrame):
    """统一风格的圆角卡片容器，自动随全局 QSS 切换浅/深主题。"""

    def __init__(self, title: str = "", subtitle: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(14, 12, 14, 12)
        self.root_layout.setSpacing(9)

        if title:
            head = QHBoxLayout()
            head.setSpacing(8)
            lbl = QLabel(title)
            lbl.setObjectName("TitleText")
            head.addWidget(lbl)
            if subtitle:
                sub = QLabel(subtitle)
                sub.setObjectName("SubText")
                head.addWidget(sub)
            head.addStretch(1)
            self.root_layout.addLayout(head)


class KpiCard(QFrame):
    """紧凑现代 KPI 统计卡，随主题自动调整配色。"""

    def __init__(
        self,
        label: str,
        value: str = "—",
        hint: str = "",
        accent_role: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardAlt")
        self._accent_role = accent_role  # "", "accent", "danger", "ok"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(2)

        self._label = QLabel(label)
        self._label.setObjectName("SubText")
        lay.addWidget(self._label)

        self._value = QLabel(value)
        lay.addWidget(self._value)

        self._hint = QLabel(hint)
        self._hint.setObjectName("MutedText")
        self._hint.setVisible(bool(hint))
        lay.addWidget(self._hint)
        self.refresh_theme()

    def set_value(self, value: str, hint: Optional[str] = None, accent: Optional[str] = None) -> None:
        self._value.setText(value)
        if accent is not None:
            # 兼容旧调用：将十六进制或角色名映射到主题角色
            if accent in ("accent", "danger", "ok", ""):
                self._accent_role = accent
            elif "F87171" in accent or "DC" in accent or "EF4444" in accent:
                self._accent_role = "danger"
            elif "4ADE80" in accent or "22C55E" in accent or "16A34A" in accent:
                self._accent_role = "ok"
            elif "38BDF8" in accent or "2563EB" in accent:
                self._accent_role = "accent"
            else:
                self._accent_role = ""
        if hint is not None:
            self._hint.setText(hint)
            self._hint.setVisible(bool(hint))
        self.refresh_theme()

    def refresh_theme(self) -> None:
        if self._accent_role == "accent":
            col = COLORS["accent"]
        elif self._accent_role == "danger":
            col = COLORS["state_s2_text"]
        elif self._accent_role == "ok":
            col = COLORS["ok_text"]
        else:
            col = COLORS["text_primary"]
        self._value.setStyleSheet(f"font-size: 19px; font-weight: 800; color: {col};")


class DisclaimerBanner(QFrame):
    """醒目的合规免责横幅（带文字与符号，随主题自动适配）。"""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WarnBanner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        badge = QLabel("! 口径提示")
        badge.setObjectName("WarnBadge")
        badge.setFixedHeight(25)
        lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        lbl = QLabel(text)
        lbl.setObjectName("WarnText")
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)


class ImagePreviewDialog(QDialog):
    """点击缩略图弹出的高清原图查看弹窗。"""

    def __init__(self, title: str, image_path: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1100, 760)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        top = QHBoxLayout()
        info = QLabel(f"{title}   ·   {image_path.name}")
        info.setObjectName("TitleText")
        top.addWidget(info)
        top.addStretch(1)
        close_btn = QPushButton("关闭 (Esc)")
        close_btn.clicked.connect(self.accept)
        top.addWidget(close_btn)
        lay.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        img_lbl = QLabel()
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = QPixmap(str(image_path))
        if not pix.isNull():
            if pix.width() > 1400 or pix.height() > 1000:
                pix = pix.scaled(
                    1400, 1000,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            img_lbl.setPixmap(pix)
        else:
            img_lbl.setText("无法读取图片文件")
        scroll.setWidget(img_lbl)
        lay.addWidget(scroll, 1)
