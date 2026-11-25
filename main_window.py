# -*- coding: utf-8 -*-
"""主窗口壳：现代顶部双层导航（零左侧挤压）+ 浅/深主题一键切换 + 6 视图联动 + 全局快捷键。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from data_loader import SessionBundle, WorkspaceData, _effective_state, load_session_file, load_workspace
from theme import COLORS, current_theme_mode, set_theme_mode
from widgets.compare_view import CompareView
from widgets.live_track_view import LiveTrackView, VIDEO_EXTS
from widgets.playback_view import PlaybackView
from widgets.quality_view import QualityView
from widgets.training_view import TrainingView
from widgets.trajectory_view import TrajectoryView


class MainWindow(QMainWindow):
    """视障动态障碍物感知工程 · 原生桌面可视化控制台（现代顶部导航 + 浅/深双主题）。"""

    def __init__(self, data_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data_root = data_root
        self._workspace: Optional[WorkspaceData] = None
        self._active_session: Optional[SessionBundle] = None
        self._last_frame_idx: int = 0
        self._nav_buttons: List[QPushButton] = []

        self.setWindowTitle("视障感知工程 · 可视化控制台（原生桌面版 v1.2）")
        self.resize(1366, 820)
        self.setMinimumSize(1160, 680)
        self.setAcceptDrops(True)

        self._build_ui()
        self._bind_shortcuts()
        self.load_data_root(self._data_root)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_v = QVBoxLayout(central)
        root_v.setContentsMargins(0, 0, 0, 0)
        root_v.setSpacing(0)

        # ==================== 顶部第 1 层：品牌 + 当前上下文 + 全局操作 ====================
        top = QFrame()
        top.setObjectName("TopBar")
        top.setFixedHeight(54)
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(16, 0, 16, 0)
        top_lay.setSpacing(10)

        brand = QLabel("● 视障感知控制台")
        brand.setStyleSheet("font-size: 17px; font-weight: 800;")
        top_lay.addWidget(brand)

        self._lbl_run_title = QLabel("未加载会话")
        self._lbl_run_title.setObjectName("PillAccent")
        top_lay.addWidget(self._lbl_run_title)

        self._lbl_model_pill = QLabel("")
        self._lbl_model_pill.setObjectName("PillNeutral")
        top_lay.addWidget(self._lbl_model_pill)

        self._lbl_top_state = QLabel("● S0 静默")
        top_lay.addWidget(self._lbl_top_state)

        top_lay.addStretch(1)

        btn_upload = QPushButton("+ 导入视频追踪")
        btn_upload.setObjectName("PrimaryBtn")
        btn_upload.setToolTip("导入本地视频（不受 20MB 限制）并实时运行 YOLO26n + ByteTrack 追踪（快捷键 6）")
        btn_upload.clicked.connect(self._open_video_import)
        top_lay.addWidget(btn_upload)

        btn_open = QPushButton("切换目录")
        btn_open.setToolTip("打开 vproj 仓库目录或解压后的交付快照目录（含 out/web 或 data/web）")
        btn_open.clicked.connect(self._choose_data_dir)
        top_lay.addWidget(btn_open)

        btn_reload = QPushButton("刷新")
        btn_reload.setToolTip("重新扫描当前数据源")
        btn_reload.clicked.connect(lambda: self.load_data_root(self._data_root))
        top_lay.addWidget(btn_reload)

        self._btn_theme = QPushButton("切换深色")
        self._btn_theme.setToolTip("在清爽浅色主题与专业深色主题之间一键切换")
        self._btn_theme.clicked.connect(self._toggle_theme)
        top_lay.addWidget(self._btn_theme)

        root_v.addWidget(top)

        # ==================== 顶部第 2 层：横向 6 视图导航条（释放整栏左侧宽度） ====================
        nav_strip = QFrame()
        nav_strip.setObjectName("NavStrip")
        nav_strip.setFixedHeight(46)
        nav_lay = QHBoxLayout(nav_strip)
        nav_lay.setContentsMargins(16, 4, 16, 4)
        nav_lay.setSpacing(8)

        nav_specs = [
            ("V1 感知回放台", "视频 + 叠加层 + 时间轴 + 状态 HUD（快捷键 1）"),
            ("V2 轨迹视图", "图像平面 foot_path 轨迹与多维筛选（快捷键 2）"),
            ("V3 画质体检", "客观视频画质统计与抽样参考帧（快捷键 3）"),
            ("V4 训练监控", "Loss/mAP 曲线、Best Epoch、早停与产物画廊（快捷键 4）"),
            ("V5 模型对比", "YOLO26 n/s/m 横评表与同帧三联对比（快捷键 5）"),
            ("V6 视频导入追踪", "上传本地视频/摄像头实时 YOLO26n + ByteTrack 追踪（快捷键 6）"),
        ]
        for idx, (label, tip) in enumerate(nav_specs):
            btn = QPushButton(label)
            btn.setObjectName("NavTab")
            btn.setToolTip(tip)
            btn.setProperty("active", "true" if idx == 0 else "false")
            btn.clicked.connect(lambda _=False, i=idx: self.switch_view(i))
            nav_lay.addWidget(btn)
            self._nav_buttons.append(btn)

        nav_lay.addStretch(1)

        hk_lbl = QLabel("Space 播放 · ←/→ 单帧 · Shift±1s · L 图例 · 1–6 切视图")
        hk_lbl.setObjectName("MutedText")
        nav_lay.addWidget(hk_lbl)

        root_v.addWidget(nav_strip)

        # ==================== 中部主视图堆栈（100% 宽度给内容） ====================
        self._stack = QStackedWidget()
        self._v1 = PlaybackView()
        self._v2 = TrajectoryView()
        self._v3 = QualityView()
        self._v4 = TrainingView()
        self._v5 = CompareView()
        self._v6 = LiveTrackView(weights_dir=self._resolve_weights_dir(self._data_root))

        self._stack.addWidget(self._v1)
        self._stack.addWidget(self._v2)
        self._stack.addWidget(self._v3)
        self._stack.addWidget(self._v4)
        self._stack.addWidget(self._v5)
        self._stack.addWidget(self._v6)

        self._v1.sessionChanged.connect(self._on_session_changed)
        self._v1.frameChanged.connect(self._on_frame_changed)
        self._v1.inspectTrackRequested.connect(self._on_inspect_track)
        self._v2.jumpToPlayback.connect(self._on_jump_to_playback)
        self._v6.sessionExported.connect(lambda p: self._on_live_session_exported(p, switch_to_v1=False))
        self._v6.openInPlaybackRequested.connect(lambda p: self._on_live_session_exported(p, switch_to_v1=True))

        root_v.addWidget(self._stack, 1)

        # ==================== 底部常驻合规声明与数据源栏 ====================
        bottom = QFrame()
        bottom.setObjectName("BottomComplianceBar")
        bottom.setFixedHeight(32)
        b_lay = QHBoxLayout(bottom)
        b_lay.setContentsMargins(16, 0, 16, 0)
        b_lay.setSpacing(12)

        comp = QLabel(
            "合规声明：分区为演示逻辑（按框底边占画面高度比例），非米制距离  ·  "
            "alert 为演示规则，非风险引擎  ·  检出百分比为有检出帧占比，非准确率"
        )
        comp.setObjectName("ComplianceText")
        b_lay.addWidget(comp, 1)

        self._lbl_data_dir = QLabel("")
        self._lbl_data_dir.setObjectName("MutedText")
        b_lay.addWidget(self._lbl_data_dir)

        root_v.addWidget(bottom)
        self._update_top_state_pill("S0")

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._sc_play_pause)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self._sc_step(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self._sc_step(1))
        QShortcut(QKeySequence("Shift+Left"), self, lambda: self._sc_step_sec(-1.0))
        QShortcut(QKeySequence("Shift+Right"), self, lambda: self._sc_step_sec(1.0))
        QShortcut(QKeySequence("L"), self, self._sc_toggle_legend)
        for idx in range(6):
            QShortcut(QKeySequence(str(idx + 1)), self, lambda i=idx: self.switch_view(i))

    def _focus_is_text_input(self) -> bool:
        fw = self.focusWidget()
        return fw is not None and fw.metaObject().className() in {"QLineEdit", "QSpinBox", "QDoubleSpinBox"}

    def _sc_play_pause(self) -> None:
        if not self._focus_is_text_input() and self._stack.currentIndex() == 0:
            self._v1.toggle_play()

    def _sc_step(self, delta: int) -> None:
        if not self._focus_is_text_input() and self._stack.currentIndex() == 0:
            self._v1.step_frame(delta)

    def _sc_step_sec(self, delta_s: float) -> None:
        if not self._focus_is_text_input() and self._stack.currentIndex() == 0:
            self._v1.step_seconds(delta_s)

    def _sc_toggle_legend(self) -> None:
        if not self._focus_is_text_input() and self._stack.currentIndex() == 0:
            self._v1.toggle_legend()

    def _toggle_theme(self) -> None:
        next_mode = "dark" if current_theme_mode() == "light" else "light"
        self.apply_theme_mode(next_mode)

    def apply_theme_mode(self, mode: str) -> None:
        qss = set_theme_mode(mode)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(qss)
        self._btn_theme.setText("切换深色" if mode == "light" else "切换浅色")
        # 通知 6 个视图刷新自定义配色与 QPainter 画布
        for view in (self._v1, self._v2, self._v3, self._v4, self._v5, self._v6):
            if hasattr(view, "refresh_theme"):
                view.refresh_theme()
        # 刷新顶部状态徽章
        if self._active_session:
            fr = self._active_session.frame_info(self._last_frame_idx)
            self._update_top_state_pill(_effective_state(fr))
        else:
            self._update_top_state_pill("S0")

    def switch_view(self, index: int) -> None:
        if index != 0:
            self._v1.pause()
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", "true" if i == index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _choose_data_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "选择感知工程根目录（vproj 或解压后的交付包目录）",
            str(self._data_root),
        )
        if chosen:
            self.load_data_root(Path(chosen))

    def _resolve_weights_dir(self, root: Path) -> Path:
        app_base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        for cand in [root / "weights", app_base / "weights", app_base / "bundled_data" / "weights"]:
            if cand.is_dir() and any(cand.glob("*.pt")):
                return cand
        return root / "weights"

    def _open_video_import(self) -> None:
        self.switch_view(5)
        self._v6.prompt_select_video()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = Path(url.toLocalFile())
                if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = Path(url.toLocalFile())
                if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                    self.switch_view(5)
                    self._v6.set_video_file(p)
                    event.acceptProposedAction()
                    return

    def _on_live_session_exported(self, session_json_path: Path, switch_to_v1: bool = False) -> None:
        sb = load_session_file(session_json_path, self._data_root)
        if sb is None:
            return
        self._v1.add_or_select_session(sb)
        if switch_to_v1:
            self.switch_view(0)

    def load_data_root(self, root: Path) -> None:
        self._data_root = root
        self._lbl_data_dir.setText(f"数据源：{root}")
        ws = load_workspace(root)
        self._workspace = ws

        self._v3.set_probe_images(ws.probe_images)
        self._v4.set_runs(ws.runs)
        self._v5.set_data(ws.compare_rows, ws.compare_frame_groups)
        self._v1.set_sessions(ws.sessions)
        self._v6.refresh_weights(self._resolve_weights_dir(root))

    def _on_session_changed(self, session: Optional[SessionBundle]) -> None:
        self._active_session = session
        self._last_frame_idx = 0
        self._v2.set_session(session)
        self._v3.set_session(session)

        has_q = session is not None and session.quality is not None
        self._nav_buttons[2].setText("V3 画质体检" if has_q else "V3 画质体检 (空)")

        if session is None:
            self._lbl_run_title.setText("未加载会话")
            self._lbl_model_pill.setText("")
            self._update_top_state_pill("S0")
            return

        self._lbl_run_title.setText(session.title)
        m = session.model
        v = session.video
        res = f"{v['width']}×{v['height']}" if v else "无视频"
        self._lbl_model_pill.setText(f"{m.get('name', '—')} · imgsz {m.get('imgsz', '—')} · {res}")

    def _update_top_state_pill(self, st: str) -> None:
        if st == "S2":
            self._lbl_top_state.setText("▲ S2 近场音频")
            self._lbl_top_state.setStyleSheet(
                f"font-size: 13px; font-weight: 700; color: {COLORS['state_s2_text']}; "
                f"background-color: {COLORS['state_s2_bg']}; border: 1px solid {COLORS['state_s2_border']}; "
                "padding: 4px 10px; border-radius: 7px;"
            )
        elif st == "S1":
            self._lbl_top_state.setText("◆ S1 远场提示")
            self._lbl_top_state.setStyleSheet(
                f"font-size: 13px; font-weight: 700; color: {COLORS['state_s1_text']}; "
                f"background-color: {COLORS['state_s1_bg']}; border: 1px solid {COLORS['state_s1_border']}; "
                "padding: 4px 10px; border-radius: 7px;"
            )
        else:
            self._lbl_top_state.setText("● S0 静默")
            self._lbl_top_state.setStyleSheet(
                f"font-size: 13px; font-weight: 700; color: {COLORS['state_s0_text']}; "
                f"background-color: {COLORS['state_s0_bg']}; border: 1px solid {COLORS['state_s0_border']}; "
                "padding: 4px 10px; border-radius: 7px;"
            )

    def _on_frame_changed(self, frame_idx: int) -> None:
        self._last_frame_idx = frame_idx
        self._v2.set_current_frame(frame_idx)
        if not self._active_session:
            return
        fr = self._active_session.frame_info(frame_idx)
        self._update_top_state_pill(_effective_state(fr))

    def _on_inspect_track(self, track_id: int) -> None:
        self.switch_view(1)
        self._v2.select_track(track_id)

    def _on_jump_to_playback(self, track_id: int, frame_idx: int) -> None:
        self.switch_view(0)
        self._v1.highlight_track_at_frame(track_id, frame_idx)

    def closeEvent(self, event) -> None:
        self._v6.shutdown_worker()
        self._v1.close_resources()
        super().closeEvent(event)
