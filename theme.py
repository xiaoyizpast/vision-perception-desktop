# -*- coding: utf-8 -*-
"""现代双主题系统：默认清爽浅色主题（Light）+ 专业深色主题（Dark）。

设计准则：
- 默认浅色主题（冷灰白底 #F3F6FA + 纯白卡片 #FFFFFF + 克莱因蓝 #2563EB），护眼、通透、层次分明；
- 满足 WCAG AA 高对比度（正文对比度 > 12:1，次级文案 > 6:1），基础字号 ≥ 15–16px；
- 所有自定义 QPainter 组件实时读取 COLORS（原地更新字典），切换主题瞬间全界面同步刷新。
"""

from __future__ import annotations

from typing import Dict

LIGHT_COLORS: Dict[str, str] = {
    "mode": "light",
    "bg_root": "#F2F5F9",
    "bg_sidebar": "#FFFFFF",
    "bg_topbar": "#FFFFFF",
    "bg_navstrip": "#F8FAFC",
    "bg_card": "#FFFFFF",
    "bg_card_alt": "#F6F8FB",
    "bg_canvas": "#E8EEF5",
    "bg_canvas_inner": "#FFFFFF",
    "bg_chart": "#FFFFFF",
    "bg_input": "#FFFFFF",
    "bg_hover": "#EBF2FE",
    "bg_pill": "#EEF2F7",
    "bg_hud_kv": "#FFFFFF",
    "border": "#DCE3EE",
    "border_strong": "#B8C5D8",
    "grid_line": "#E2E8F0",
    "text_primary": "#0F172A",
    "text_secondary": "#475569",
    "text_muted": "#64748B",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_bg": "#DBEAFE",
    "accent_text": "#1E40AF",
    # 契约规定绘制色（docs/06 第 5 节）
    "zone_near": "#DC0000",
    "zone_mid": "#E68A00",
    "zone_far": "#00A800",
    "zone_unassigned": "#7A8699",
    "foot_dot": "#0000FF",
    # 状态色带（S0 灰 / S1 黄 / S2 红）
    "state_s0": "#94A3B8",
    "state_s1": "#EAB308",
    "state_s2": "#DC2626",
    "state_s2_bg": "#FEF2F2",
    "state_s2_border": "#EF4444",
    "state_s2_text": "#B91C1C",
    "state_s1_bg": "#FEFCE8",
    "state_s1_border": "#EAB308",
    "state_s1_text": "#A16207",
    "state_s0_bg": "#F8FAFC",
    "state_s0_border": "#CBD5E1",
    "state_s0_text": "#334155",
    # 图表系列色
    "chart_1": "#2563EB",
    "chart_2": "#EA580C",
    "chart_3": "#16A34A",
    "chart_4": "#9333EA",
    "chart_5": "#E11D48",
    "chart_6": "#CA8A04",
    "warn_bg": "#FFFBEB",
    "warn_border": "#F59E0B",
    "warn_badge_bg": "#F59E0B",
    "warn_badge_fg": "#FFFFFF",
    "warn_text": "#92400E",
    "ok_bg": "#ECFDF5",
    "ok_border": "#10B981",
    "ok_text": "#047857",
    "best_ms_bg": "#DCFCE7",
    "best_ms_fg": "#166534",
    "best_rate_bg": "#DBEAFE",
    "best_rate_fg": "#1E40AF",
    "bottom_bar_bg": "#FFFBEB",
    "bottom_bar_text": "#92400E",
    "playhead": "#0F172A",
    "track_bg": "#CBD5E1",
    "tooltip_bg": "#FFFFFF",
    "tooltip_fg": "#0F172A",
    "early_bg": "#FFF7ED",
    "early_border": "#EA580C",
    "early_text": "#C2410C",
}

DARK_COLORS: Dict[str, str] = {
    "mode": "dark",
    "bg_root": "#0B0F14",
    "bg_sidebar": "#0F151D",
    "bg_topbar": "#0F151D",
    "bg_navstrip": "#121923",
    "bg_card": "#131A24",
    "bg_card_alt": "#18212E",
    "bg_canvas": "#080B10",
    "bg_canvas_inner": "#0F151E",
    "bg_chart": "#0F151E",
    "bg_input": "#1A2332",
    "bg_hover": "#212D3F",
    "bg_pill": "#162231",
    "bg_hud_kv": "#0D131C",
    "border": "#263346",
    "border_strong": "#364863",
    "grid_line": "#1F2A3A",
    "text_primary": "#F1F5F9",
    "text_secondary": "#A8B6C8",
    "text_muted": "#8B9BB0",
    "accent": "#38BDF8",
    "accent_hover": "#7DD3FC",
    "accent_bg": "#12324A",
    "accent_text": "#7DD3FC",
    "zone_near": "#DC0000",
    "zone_mid": "#FFA500",
    "zone_far": "#00C800",
    "zone_unassigned": "#888888",
    "foot_dot": "#0000FF",
    "state_s0": "#5A6577",
    "state_s1": "#EAB308",
    "state_s2": "#DC2626",
    "state_s2_bg": "#3A1116",
    "state_s2_border": "#EF4444",
    "state_s2_text": "#FCA5A5",
    "state_s1_bg": "#33280B",
    "state_s1_border": "#EAB308",
    "state_s1_text": "#FDE047",
    "state_s0_bg": "#1A222E",
    "state_s0_border": "#475569",
    "state_s0_text": "#CBD5E1",
    "chart_1": "#38BDF8",
    "chart_2": "#F97316",
    "chart_3": "#22C55E",
    "chart_4": "#A855F7",
    "chart_5": "#F43F5E",
    "chart_6": "#FACC15",
    "warn_bg": "#2B210B",
    "warn_border": "#D97706",
    "warn_badge_bg": "#D97706",
    "warn_badge_fg": "#111827",
    "warn_text": "#FDE68A",
    "ok_bg": "#0D2B1D",
    "ok_border": "#16A34A",
    "ok_text": "#86EFAC",
    "best_ms_bg": "#0D2B1D",
    "best_ms_fg": "#86EFAC",
    "best_rate_bg": "#12324A",
    "best_rate_fg": "#7DD3FC",
    "bottom_bar_bg": "#141922",
    "bottom_bar_text": "#FDE68A",
    "playhead": "#F8FAFC",
    "track_bg": "#1E293B",
    "tooltip_bg": "#1E293B",
    "tooltip_fg": "#F8FAFC",
    "early_bg": "#7C2D12",
    "early_border": "#F97316",
    "early_text": "#FFEDD5",
}

# 全局可变活动色板（所有模块引用同一个 dict 对象，切换主题时原地 update）
COLORS: Dict[str, str] = dict(LIGHT_COLORS)


def set_theme_mode(mode: str) -> str:
    """切换全局主题（'light' | 'dark'），返回新的全局 QSS。"""
    src = DARK_COLORS if mode == "dark" else LIGHT_COLORS
    COLORS.clear()
    COLORS.update(src)
    return build_stylesheet()


def current_theme_mode() -> str:
    return COLORS.get("mode", "light")


def build_stylesheet() -> str:
    c = COLORS
    is_light = (c.get("mode") == "light")
    chk_mark = "#2563EB" if is_light else "#38BDF8"
    scroll_handle = "#CBD5E1" if is_light else "#334155"
    scroll_hover = "#94A3B8" if is_light else "#475569"
    splitter_col = "#DCE3EE" if is_light else "#263346"

    return f"""
    * {{
        font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
        font-size: 15px;
        color: {c["text_primary"]};
    }}

    QMainWindow, QDialog {{
        background-color: {c["bg_root"]};
    }}

    QWidget {{
        background-color: transparent;
    }}

    QSplitter::handle {{
        background-color: {splitter_col};
        width: 4px;
        height: 4px;
        margin: 2px 1px;
        border-radius: 2px;
    }}
    QSplitter::handle:hover {{
        background-color: {c["accent"]};
    }}

    QFrame#TopBar {{
        background-color: {c["bg_topbar"]};
        border-bottom: 1px solid {c["border"]};
    }}

    QFrame#NavStrip {{
        background-color: {c["bg_navstrip"]};
        border-bottom: 1px solid {c["border"]};
    }}

    QFrame#BottomComplianceBar {{
        background-color: {c["bottom_bar_bg"]};
        border-top: 1px solid {c["border"]};
    }}

    QFrame#Card {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
    }}

    QFrame#CardAlt {{
        background-color: {c["bg_card_alt"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
    }}

    QFrame#HudKv {{
        background-color: {c["bg_hud_kv"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
    }}

    QFrame#WarnBanner {{
        background-color: {c["warn_bg"]};
        border: 1px solid {c["warn_border"]};
        border-radius: 10px;
    }}

    QFrame#StateCardS0 {{
        background-color: {c["state_s0_bg"]};
        border: 2px solid {c["state_s0_border"]};
        border-radius: 12px;
    }}

    QFrame#StateCardS1 {{
        background-color: {c["state_s1_bg"]};
        border: 2px solid {c["state_s1_border"]};
        border-radius: 12px;
    }}

    QFrame#StateCardS2 {{
        background-color: {c["state_s2_bg"]};
        border: 2px solid {c["state_s2_border"]};
        border-radius: 12px;
    }}

    QLabel#TitleText {{
        font-size: 16px;
        font-weight: 700;
        color: {c["text_primary"]};
    }}

    QLabel#SubText {{
        font-size: 13px;
        color: {c["text_secondary"]};
    }}

    QLabel#MutedText {{
        font-size: 13px;
        color: {c["text_muted"]};
    }}

    QLabel#PillAccent {{
        font-size: 14px;
        font-weight: 700;
        color: {c["accent_text"]};
        background-color: {c["accent_bg"]};
        border: 1px solid {c["border"]};
        padding: 4px 10px;
        border-radius: 7px;
    }}

    QLabel#PillNeutral {{
        font-size: 14px;
        color: {c["text_secondary"]};
        background-color: {c["bg_pill"]};
        border: 1px solid {c["border"]};
        padding: 4px 10px;
        border-radius: 7px;
    }}

    QLabel#WarnBadge {{
        background-color: {c["warn_badge_bg"]};
        color: {c["warn_badge_fg"]};
        font-weight: 700;
        font-size: 13px;
        padding: 3px 9px;
        border-radius: 6px;
    }}

    QLabel#WarnText {{
        color: {c["warn_text"]};
        font-size: 14px;
        font-weight: 600;
    }}

    QLabel#EarlyBadge {{
        background-color: {c["early_bg"]};
        border: 1px solid {c["early_border"]};
        color: {c["early_text"]};
        font-size: 14px;
        font-weight: 700;
        padding: 5px 12px;
        border-radius: 8px;
    }}

    QLabel#ComplianceText {{
        font-size: 13px;
        color: {c["bottom_bar_text"]};
        font-weight: 600;
    }}

    QPushButton {{
        background-color: {c["bg_input"]};
        border: 1px solid {c["border_strong"]};
        border-radius: 8px;
        padding: 6px 14px;
        min-height: 22px;
        font-size: 14px;
        font-weight: 500;
        color: {c["text_primary"]};
    }}
    QPushButton:hover {{
        background-color: {c["bg_hover"]};
        border-color: {c["accent"]};
    }}
    QPushButton:pressed {{
        background-color: {c["accent_bg"]};
    }}
    QPushButton:disabled {{
        color: {c["text_muted"]};
        background-color: {c["bg_card_alt"]};
        border-color: {c["border"]};
    }}
    QPushButton:focus {{
        border: 2px solid {c["accent"]};
    }}

    QPushButton#PrimaryBtn {{
        background-color: {c["accent"]};
        border: 1px solid {c["accent"]};
        color: #FFFFFF;
        font-weight: 700;
    }}
    QPushButton#PrimaryBtn:hover {{
        background-color: {c["accent_hover"]};
        border-color: {c["accent_hover"]};
    }}
    QPushButton#PrimaryBtn:disabled {{
        background-color: {c["border_strong"]};
        border-color: {c["border_strong"]};
        color: #FFFFFF;
    }}

    QPushButton#NavTab {{
        padding: 6px 16px;
        min-height: 22px;
        border-radius: 8px;
        border: 1px solid transparent;
        background-color: transparent;
        color: {c["text_secondary"]};
        font-size: 14px;
        font-weight: 600;
    }}
    QPushButton#NavTab:hover {{
        background-color: {c["bg_hover"]};
        color: {c["text_primary"]};
    }}
    QPushButton#NavTab[active="true"] {{
        background-color: {c["accent_bg"]};
        border: 1px solid {c["accent"]};
        color: {c["accent_text"]};
        font-weight: 700;
    }}

    QPushButton#ChipBtn {{
        padding: 6px 12px;
        min-height: 22px;
        border-radius: 8px;
        font-size: 14px;
        background-color: {c["bg_input"]};
        border: 1px solid {c["border_strong"]};
    }}
    QPushButton#ChipBtn:checked {{
        background-color: {c["accent_bg"]};
        border: 1px solid {c["accent"]};
        color: {c["accent_text"]};
        font-weight: 700;
    }}

    QListWidget, QTableWidget, QTreeWidget {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        outline: none;
        gridline-color: {c["border"]};
        selection-background-color: {c["accent_bg"]};
        selection-color: {c["accent_text"]};
    }}

    QListWidget::item {{
        padding: 9px 10px;
        border-bottom: 1px solid {c["border"]};
        border-radius: 6px;
        margin: 2px 3px;
        color: {c["text_primary"]};
    }}
    QListWidget::item:hover {{
        background-color: {c["bg_hover"]};
    }}
    QListWidget::item:selected {{
        background-color: {c["accent_bg"]};
        border: 1px solid {c["accent"]};
        color: {c["accent_text"]};
        font-weight: 600;
    }}

    QHeaderView::section {{
        background-color: {c["bg_card_alt"]};
        color: {c["text_secondary"]};
        padding: 7px 8px;
        border: none;
        border-bottom: 1px solid {c["border_strong"]};
        border-right: 1px solid {c["border"]};
        font-weight: 700;
        font-size: 14px;
    }}

    QTableWidget::item {{
        padding: 5px 8px;
        font-size: 14px;
    }}

    QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
        background-color: {c["bg_input"]};
        border: 1px solid {c["border_strong"]};
        border-radius: 8px;
        padding: 5px 10px;
        min-height: 24px;
        font-size: 14px;
        color: {c["text_primary"]};
    }}
    QComboBox {{
        padding-right: 26px;
    }}
    QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
        border: 2px solid {c["accent"]};
    }}
    QComboBox QAbstractItemView {{
        background-color: {c["bg_card"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border_strong"]};
        selection-background-color: {c["accent_bg"]};
        selection-color: {c["accent_text"]};
    }}

    QCheckBox {{
        spacing: 8px;
        font-size: 14px;
        color: {c["text_primary"]};
        padding: 2px 0;
    }}
    QCheckBox::indicator {{
        width: 17px;
        height: 17px;
        border-radius: 4px;
        border: 2px solid {c["border_strong"]};
        background-color: {c["bg_input"]};
    }}
    QCheckBox::indicator:checked {{
        background-color: {chk_mark};
        border-color: {chk_mark};
    }}

    QProgressBar {{
        background-color: {c["bg_card_alt"]};
        border: 1px solid {c["border_strong"]};
        border-radius: 7px;
        height: 22px;
        text-align: center;
        font-size: 13px;
        font-weight: 600;
        color: {c["text_primary"]};
    }}
    QProgressBar::chunk {{
        background-color: {c["accent"]};
        border-radius: 6px;
    }}

    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 9px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {scroll_handle};
        min-height: 30px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {scroll_hover};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 9px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {scroll_handle};
        min-width: 30px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {scroll_hover};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    QToolTip {{
        background-color: {c["tooltip_bg"]};
        color: {c["tooltip_fg"]};
        border: 1px solid {c["accent"]};
        padding: 6px 10px;
        border-radius: 6px;
        font-size: 14px;
    }}
    """
