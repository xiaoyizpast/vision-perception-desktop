# -*- coding: utf-8 -*-
"""V1 感知回放台（Playback Studio）——可拖拽 3 栏现代舒展布局 + 浅/深双主题。"""

from __future__ import annotations

import time
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data_loader import SessionBundle, _effective_state
from theme import COLORS
from video_engine import VideoFrameEngine
from widgets.common import KpiCard, SectionCard
from widgets.timeline_bar import TimelineBar
from widgets.video_canvas import VideoOverlayCanvas


class PlaybackView(QWidget):
    """V1 感知回放台主视图。"""

    sessionChanged = Signal(object)
    frameChanged = Signal(int)
    inspectTrackRequested = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._sessions: List[SessionBundle] = []
        self._session: Optional[SessionBundle] = None
        self._engine = VideoFrameEngine(max_cache=120)
        self._current_frame: int = 0
        self._playing: bool = False
        self._speed: float = 1.0
        self._play_anchor_wall: float = 0.0
        self._play_anchor_frame: int = 0
        self._audio_enabled: bool = False
        self._selected_track_id: Optional[int] = None

        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.75)
        self._audio_player = QMediaPlayer(self)
        self._audio_player.setAudioOutput(self._audio_output)

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_tick)

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ==================== 左栏：会话列表 + 2 列紧凑图层开关 + 模型元信息 ====================
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(240)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_box = QWidget()
        left_lay = QVBoxLayout(left_box)
        left_lay.setContentsMargins(0, 0, 6, 0)
        left_lay.setSpacing(10)

        sess_card = SectionCard("回放会话列表")
        self._session_list = QListWidget()
        self._session_list.setMinimumHeight(180)
        self._session_list.setMaximumHeight(240)
        self._session_list.currentRowChanged.connect(self._on_session_row_changed)
        sess_card.root_layout.addWidget(self._session_list)
        left_lay.addWidget(sess_card)

        layer_card = SectionCard("叠加图层")
        lg = QGridLayout()
        lg.setHorizontalSpacing(8)
        lg.setVerticalSpacing(6)
        self._chk_boxes = QCheckBox("检测框")
        self._chk_boxes.setChecked(True)
        self._chk_foot = QCheckBox("脚点圆点")
        self._chk_foot.setChecked(True)
        self._chk_zones = QCheckBox("分区线")
        self._chk_zones.setChecked(True)
        self._chk_trails = QCheckBox("轨迹尾迹")
        self._chk_trails.setChecked(True)
        self._chk_status_bar = QCheckBox("画面状态条")
        self._chk_status_bar.setChecked(True)
        self._chk_unassigned = QCheckBox("未确认(-1)")
        self._chk_unassigned.setChecked(True)
        self._chk_legend = QCheckBox("画面图例(L)")
        self._chk_legend.setChecked(False)

        checks = [
            self._chk_boxes, self._chk_foot,
            self._chk_zones, self._chk_trails,
            self._chk_status_bar, self._chk_unassigned,
            self._chk_legend,
        ]
        for idx, chk in enumerate(checks):
            chk.toggled.connect(self._sync_layer_flags)
            lg.addWidget(chk, idx // 2, idx % 2)
        layer_card.root_layout.addLayout(lg)
        left_lay.addWidget(layer_card)

        meta_card = SectionCard("模型与标定摘要")
        self._meta_label = QLabel("未选择会话")
        self._meta_label.setObjectName("SubText")
        self._meta_label.setWordWrap(True)
        meta_card.root_layout.addWidget(self._meta_label)
        left_lay.addWidget(meta_card)

        left_lay.addStretch(1)
        left_scroll.setWidget(left_box)
        splitter.addWidget(left_scroll)

        # ==================== 中栏：大视野视频舞台 + 舒展播控时间轴 + 4 KPI ====================
        center_w = QWidget()
        center_lay = QVBoxLayout(center_w)
        center_lay.setContentsMargins(6, 0, 6, 0)
        center_lay.setSpacing(10)

        canvas_card = QFrame()
        canvas_card.setObjectName("Card")
        c_lay = QVBoxLayout(canvas_card)
        c_lay.setContentsMargins(8, 8, 8, 8)
        self._canvas = VideoOverlayCanvas()
        self._canvas.targetClicked.connect(self._on_canvas_target_clicked)
        c_lay.addWidget(self._canvas, 1)
        center_lay.addWidget(canvas_card, 1)

        ctrl_card = QFrame()
        ctrl_card.setObjectName("Card")
        ctrl_lay = QVBoxLayout(ctrl_card)
        ctrl_lay.setContentsMargins(14, 10, 14, 10)
        ctrl_lay.setSpacing(8)

        self._timeline = TimelineBar()
        self._timeline.seekRequested.connect(self.seek_to_frame)
        ctrl_lay.addWidget(self._timeline)

        # 第 1 行播控：主操作 + 帧/时间读数（间距充裕，零冲突）
        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(8)

        self._btn_play = QPushButton("播放")
        self._btn_play.setObjectName("PrimaryBtn")
        self._btn_play.setMinimumWidth(84)
        self._btn_play.setToolTip("播放 / 暂停（快捷键 Space）")
        self._btn_play.clicked.connect(self.toggle_play)
        btn_row1.addWidget(self._btn_play)

        self._btn_prev_sec = QPushButton("-1s")
        self._btn_prev_sec.setMinimumWidth(56)
        self._btn_prev_sec.setToolTip("后退 1 秒（Shift + ←）")
        self._btn_prev_sec.clicked.connect(lambda: self.step_seconds(-1.0))
        btn_row1.addWidget(self._btn_prev_sec)

        self._btn_prev = QPushButton("上一帧")
        self._btn_prev.setMinimumWidth(72)
        self._btn_prev.setToolTip("上一帧（←）")
        self._btn_prev.clicked.connect(lambda: self.step_frame(-1))
        btn_row1.addWidget(self._btn_prev)

        self._btn_next = QPushButton("下一帧")
        self._btn_next.setMinimumWidth(72)
        self._btn_next.setToolTip("下一帧（→）")
        self._btn_next.clicked.connect(lambda: self.step_frame(1))
        btn_row1.addWidget(self._btn_next)

        self._btn_next_sec = QPushButton("+1s")
        self._btn_next_sec.setMinimumWidth(56)
        self._btn_next_sec.setToolTip("前进 1 秒（Shift + →）")
        self._btn_next_sec.clicked.connect(lambda: self.step_seconds(1.0))
        btn_row1.addWidget(self._btn_next_sec)

        btn_row1.addStretch(1)

        self._frame_readout = QLabel("帧 0 / 0 · 0.00s / 0.00s")
        self._frame_readout.setObjectName("PillAccent")
        btn_row1.addWidget(self._frame_readout)
        ctrl_lay.addLayout(btn_row1)

        # 第 2 行播控：倍速 + 音频脉冲开关
        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(10)
        speed_lbl = QLabel("播放倍速：")
        speed_lbl.setObjectName("SubText")
        btn_row2.addWidget(speed_lbl)
        self._cmb_speed = QComboBox()
        self._cmb_speed.addItems(["0.25x", "0.5x", "1.0x", "1.5x", "2.0x"])
        self._cmb_speed.setCurrentText("1.0x")
        self._cmb_speed.setFixedWidth(96)
        self._cmb_speed.currentTextChanged.connect(self._on_speed_changed)
        btn_row2.addWidget(self._cmb_speed)

        self._btn_audio = QPushButton("演示音频：关")
        self._btn_audio.setObjectName("ChipBtn")
        self._btn_audio.setCheckable(True)
        self._btn_audio.setToolTip("开启/关闭近场演示脉冲音频（audio.wav）")
        self._btn_audio.toggled.connect(self._on_audio_toggled)
        btn_row2.addWidget(self._btn_audio)
        btn_row2.addStretch(1)
        ctrl_lay.addLayout(btn_row2)

        center_lay.addWidget(ctrl_card)

        # 底部 4 张统计 KPI 卡（现在宽敞 660px+，数字零截断）
        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)
        self._kpi_detect = KpiCard("有检出帧占比", "—", "非准确率", accent_role="accent")
        self._kpi_tracks = KpiCard("轨迹 / 样本数", "—", "轨迹数非人数")
        self._kpi_conf = KpiCard("置信 均值/中位", "—", "")
        self._kpi_near = KpiCard("近场帧 (S2)", "—", "", accent_role="danger")
        for card in [self._kpi_detect, self._kpi_tracks, self._kpi_conf, self._kpi_near]:
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            stats_row.addWidget(card)
        center_lay.addLayout(stats_row)

        splitter.addWidget(center_w)

        # ==================== 右栏：实时状态 HUD + 分区统计 + 目标明细表 ====================
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setMinimumWidth(310)
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

        st_top = QHBoxLayout()
        self._lbl_state_badge = QLabel("● S0 · 静默")
        st_top.addWidget(self._lbl_state_badge)
        st_top.addStretch(1)
        self._lbl_level = QLabel("Level 0")
        self._lbl_level.setObjectName("PillNeutral")
        st_top.addWidget(self._lbl_level)
        sc_lay.addLayout(st_top)

        self._lbl_state_desc = QLabel("当前帧无检出目标（演示规则，非风险引擎）")
        self._lbl_state_desc.setObjectName("SubText")
        self._lbl_state_desc.setWordWrap(True)
        sc_lay.addWidget(self._lbl_state_desc)

        hud_grid = QGridLayout()
        hud_grid.setSpacing(8)
        self._hud_nearest = self._make_hud_kv("最近目标 ID", "—")
        self._hud_proxy = self._make_hud_kv("脚点占比", "—")
        self._hud_period = self._make_hud_kv("脉冲间隔", "—")
        self._hud_timbre = self._make_hud_kv("演示音色", "—")
        hud_grid.addWidget(self._hud_nearest[0], 0, 0)
        hud_grid.addWidget(self._hud_proxy[0], 0, 1)
        hud_grid.addWidget(self._hud_period[0], 1, 0)
        hud_grid.addWidget(self._hud_timbre[0], 1, 1)
        sc_lay.addLayout(hud_grid)
        right_lay.addWidget(self._state_card)

        zone_card = SectionCard("当前帧分区统计", "画面下沿占比")
        z_row = QHBoxLayout()
        z_row.setSpacing(8)
        self._z_total = self._make_zone_pill("总计", "0", "accent")
        self._z_near = self._make_zone_pill("近场", "0", "near")
        self._z_mid = self._make_zone_pill("中场", "0", "mid")
        self._z_far = self._make_zone_pill("远场", "0", "far")
        for box in [self._z_total[0], self._z_near[0], self._z_mid[0], self._z_far[0]]:
            z_row.addWidget(box)
        zone_card.root_layout.addLayout(z_row)
        right_lay.addWidget(zone_card)

        tgt_card = SectionCard("当前帧检出目标", "点击高亮")
        self._tgt_table = QTableWidget(0, 4)
        self._tgt_table.setHorizontalHeaderLabels(["ID", "类别", "分区", "置信度"])
        self._tgt_table.verticalHeader().setVisible(False)
        self._tgt_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tgt_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tgt_table.setMinimumHeight(185)
        self._tgt_table.setMaximumHeight(240)
        self._tgt_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tgt_table.cellClicked.connect(self._on_target_row_clicked)
        tgt_card.root_layout.addWidget(self._tgt_table)

        self._btn_jump_track = QPushButton("在 V2 轨迹视图中查看选中轨迹 →")
        self._btn_jump_track.setEnabled(False)
        self._btn_jump_track.clicked.connect(self._jump_selected_track)
        tgt_card.root_layout.addWidget(self._btn_jump_track)
        right_lay.addWidget(tgt_card)

        notes_card = SectionCard("数据口径说明")
        self._notes_label = QLabel("分区为演示逻辑（按框底边占画面高度比例），非米制坐标。")
        self._notes_label.setObjectName("SubText")
        self._notes_label.setWordWrap(True)
        notes_card.root_layout.addWidget(self._notes_label)
        right_lay.addWidget(notes_card)

        right_lay.addStretch(1)
        right_scroll.setWidget(right_box)
        splitter.addWidget(right_scroll)

        splitter.setSizes([255, 720, 355])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        root.addWidget(splitter, 1)
        self.refresh_theme()

    def _make_hud_kv(self, title: str, val: str):
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

    def _make_zone_pill(self, title: str, val: str, role: str):
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
        for kpi in (self._kpi_detect, self._kpi_tracks, self._kpi_conf, self._kpi_near):
            kpi.refresh_theme()
        role_colors = {
            "accent": COLORS["accent"],
            "near": COLORS["state_s2_text"],
            "mid": COLORS["state_s1_text"],
            "far": COLORS["ok_text"],
        }
        for _, v in (self._z_total, self._z_near, self._z_mid, self._z_far):
            col = role_colors.get(v.property("zone_role"), COLORS["text_primary"])
            v.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {col};")
        self._update_hud(self._current_frame)
        self._canvas.update()
        self._timeline.update()

    # ==================== 数据加载与切换 ====================
    def set_sessions(self, sessions: List[SessionBundle]) -> None:
        self.pause()
        self._sessions = sessions
        self._session_list.blockSignals(True)
        self._session_list.clear()
        for s in sessions:
            summ = s.summary
            rate = summ.get("detect_frame_rate")
            rate_str = f"{rate * 100:.1f}%" if isinstance(rate, (int, float)) else "—"
            vid = s.video
            res_str = f"{vid['width']}×{vid['height']}" if vid else "无视频"
            audio_tag = " [音]" if s.audio_path else ""
            text = f"{s.title}\n{res_str} · {s.frame_count}帧 · {rate_str}{audio_tag}"
            item = QListWidgetItem(text)
            item.setToolTip(str(s.json_path))
            self._session_list.addItem(item)
        self._session_list.blockSignals(False)

        if sessions:
            self._session_list.setCurrentRow(0)
            self._load_session(sessions[0])
        else:
            self._load_session(None)

    def add_or_select_session(self, session: SessionBundle) -> None:
        self.pause()
        for idx, existing in enumerate(self._sessions):
            if existing.session_id == session.session_id:
                self._sessions[idx] = session
                self._session_list.setCurrentRow(idx)
                self._load_session(session)
                return

        self._sessions.insert(0, session)
        summ = session.summary
        rate = summ.get("detect_frame_rate")
        rate_str = f"{rate * 100:.1f}%" if isinstance(rate, (int, float)) else "—"
        vid = session.video
        res_str = f"{vid['width']}×{vid['height']}" if vid else "无视频"
        item = QListWidgetItem(f"[新] {session.title}\n{res_str} · {session.frame_count}帧 · {rate_str}")
        item.setToolTip(str(session.json_path))
        self._session_list.blockSignals(True)
        self._session_list.insertItem(0, item)
        self._session_list.setCurrentRow(0)
        self._session_list.blockSignals(False)
        self._load_session(session)

    def _on_session_row_changed(self, row: int) -> None:
        if 0 <= row < len(self._sessions):
            self._load_session(self._sessions[row])

    def _load_session(self, session: Optional[SessionBundle]) -> None:
        self.pause()
        self._session = session
        self._current_frame = 0
        self._selected_track_id = None
        self._btn_jump_track.setEnabled(False)
        self._engine.close()
        self._audio_player.stop()

        self._canvas.set_session(session)
        self._timeline.set_session(session)

        if session is None:
            self._meta_label.setText("未找到任何 .session.json 数据文件。")
            self._btn_play.setEnabled(False)
            self._btn_audio.setEnabled(False)
            self.sessionChanged.emit(None)
            return

        has_video = session.video is not None and self._engine.open(session.video_path)
        self._btn_play.setEnabled(has_video or session.frame_count > 1)
        self._btn_prev.setEnabled(session.frame_count > 1)
        self._btn_next.setEnabled(session.frame_count > 1)
        self._btn_prev_sec.setEnabled(session.frame_count > 1)
        self._btn_next_sec.setEnabled(session.frame_count > 1)

        if session.audio_path and session.audio_path.is_file():
            self._audio_player.setSource(QUrl.fromLocalFile(str(session.audio_path)))
            self._btn_audio.setEnabled(True)
            self._btn_audio.setToolTip(f"演示脉冲音频：{session.audio_path.name}")
        else:
            self._audio_player.setSource(QUrl())
            self._btn_audio.setChecked(False)
            self._btn_audio.setEnabled(False)
            self._btn_audio.setToolTip("当前会话未附带 audio.wav")

        m = session.model
        v = session.video
        cal = session.calibration
        zones = session.zones
        res_line = (
            f"{v['width']}×{v['height']} px @ {v['fps']:.2f} fps（{v.get('duration_s', 0):.2f}s）"
            if v else "无视频元信息（video == null）"
        )
        cal_txt = "已标定（metric=true）" if cal.get("metric") else "未标定（metric=false，像素）"
        self._meta_label.setText(
            f"会话：{session.session_id}\n"
            f"权重：{m.get('weights', '—')}  |  imgsz：{m.get('imgsz', '—')}\n"
            f"阈值：{m.get('conf', '—')}  |  跟踪：{m.get('tracker', '—')}\n"
            f"视频：{res_line}\n"
            f"标定：{cal_txt}\n"
            f"分区：near > {zones.get('near_line', 0.72)} / mid > {zones.get('mid_line', 0.45)}"
        )

        s = session.summary
        rate = s.get("detect_frame_rate")
        fwt = s.get("frames_with_targets", 0)
        tot_f = s.get("frames", session.frame_count)
        self._kpi_detect.set_value(
            f"{rate * 100:.1f}%" if isinstance(rate, (int, float)) else "—",
            f"{fwt}/{tot_f} 帧（非准确率）",
            "accent",
        )
        unass = s.get("unassigned_samples", 0)
        self._kpi_tracks.set_value(
            f"{s.get('tracks', 0)} / {s.get('samples', 0)}",
            f"未确认 {unass} · 峰值 {s.get('max_targets_per_frame', 0)}/帧",
        )
        mc = s.get("mean_conf")
        p50 = s.get("conf_p50")
        mc_s = f"{mc:.2f}" if isinstance(mc, (int, float)) else "—"
        p50_s = f"{p50:.2f}" if isinstance(p50, (int, float)) else "—"
        cls_map = s.get("classes") or {}
        cls_txt = " ".join(f"{k}:{v}" for k, v in list(cls_map.items())[:2]) or "无目标"
        self._kpi_conf.set_value(f"{mc_s} / {p50_s}", cls_txt)
        nf = s.get("near_frames", 0)
        nf_pct = (nf / tot_f * 100.0) if tot_f else 0.0
        self._kpi_near.set_value(
            f"{nf} 帧 ({nf_pct:.0f}%)",
            f"演示脉冲 {len(session.pulses)} 次",
            "danger" if nf > 0 else "",
        )

        note_lines = [
            f"• 标定：{cal.get('note') or '未标定，坐标单位为原视频像素（px），非米制。'}",
            f"• 分区：{zones.get('semantic') or '按框底边占画面高度比例划分，非真实物理坐标。'}",
            "• 统计：所有百分比均为「有检出帧占比」，非模型准确率。",
        ]
        for n in session.notes:
            if n not in "\n".join(note_lines):
                note_lines.append(f"• {n}")
        self._notes_label.setText("\n".join(note_lines))

        self.sessionChanged.emit(session)
        self._render_frame(0)

    # ==================== 播放与同步控制 ====================
    def toggle_play(self) -> None:
        if not self._session or self._session.frame_count <= 1:
            return
        if self._playing:
            self.pause()
        else:
            self.play()

    def play(self) -> None:
        if not self._session or self._session.frame_count <= 1:
            return
        if self._current_frame >= self._session.frame_count - 1:
            self._current_frame = 0
        self._playing = True
        self._play_anchor_wall = time.perf_counter()
        self._play_anchor_frame = self._current_frame
        self._btn_play.setText("暂停")
        self._sync_audio_play()
        self._timer.start()

    def pause(self) -> None:
        self._playing = False
        self._timer.stop()
        self._audio_player.pause()
        self._btn_play.setText("播放")

    def seek_to_frame(self, frame_idx: int) -> None:
        if not self._session or self._session.frame_count <= 0:
            return
        f = max(0, min(int(frame_idx), self._session.frame_count - 1))
        self._current_frame = f
        if self._playing:
            self._play_anchor_wall = time.perf_counter()
            self._play_anchor_frame = f
            self._sync_audio_play()
        elif self._audio_enabled and self._session.audio_path:
            ms = int(round((f / max(self._session.fps, 1e-6)) * 1000))
            self._audio_player.setPosition(ms)
        self._render_frame(f)

    def step_frame(self, delta: int) -> None:
        if not self._session:
            return
        self.pause()
        self.seek_to_frame(self._current_frame + delta)

    def step_seconds(self, delta_s: float) -> None:
        if not self._session:
            return
        delta_frames = int(round(delta_s * self._session.fps))
        self.seek_to_frame(self._current_frame + delta_frames)

    def toggle_legend(self) -> None:
        new_state = self._canvas.toggle_legend()
        self._chk_legend.blockSignals(True)
        self._chk_legend.setChecked(new_state)
        self._chk_legend.blockSignals(False)

    def highlight_track_at_frame(self, track_id: int, frame_idx: int) -> None:
        self.pause()
        self._selected_track_id = track_id
        self._canvas.set_selected_track(track_id)
        self._btn_jump_track.setEnabled(True)
        self.seek_to_frame(frame_idx)

    def _on_speed_changed(self, text: str) -> None:
        try:
            self._speed = float(text.replace("x", ""))
        except ValueError:
            self._speed = 1.0
        self._audio_player.setPlaybackRate(self._speed)
        if self._playing:
            self._play_anchor_wall = time.perf_counter()
            self._play_anchor_frame = self._current_frame

    def _on_audio_toggled(self, checked: bool) -> None:
        self._audio_enabled = checked
        self._btn_audio.setText("演示音频：开" if checked else "演示音频：关")
        if checked and self._playing:
            self._sync_audio_play()
        else:
            self._audio_player.pause()

    def _sync_audio_play(self) -> None:
        if not self._session or not self._audio_enabled or not self._session.audio_path:
            self._audio_player.pause()
            return
        ms = int(round((self._current_frame / max(self._session.fps, 1e-6)) * 1000))
        self._audio_player.setPlaybackRate(self._speed)
        self._audio_player.setPosition(ms)
        self._audio_player.play()

    def _on_tick(self) -> None:
        if not self._playing or not self._session:
            return
        elapsed = time.perf_counter() - self._play_anchor_wall
        target = self._play_anchor_frame + int(round(elapsed * self._session.fps * self._speed))
        if target >= self._session.frame_count - 1:
            self._current_frame = self._session.frame_count - 1
            self._render_frame(self._current_frame)
            self.pause()
            return
        if target != self._current_frame:
            self._current_frame = target
            self._render_frame(target)

    def _render_frame(self, frame_idx: int) -> None:
        if not self._session:
            return
        img = self._engine.get_frame(frame_idx) if self._engine.is_open else None
        self._canvas.set_frame(frame_idx, img)
        self._timeline.set_current_frame(frame_idx)

        fps = max(self._session.fps, 1e-6)
        total = max(1, self._session.frame_count)
        cur_t = frame_idx / fps
        tot_t = (total - 1) / fps
        self._frame_readout.setText(f"帧 {frame_idx} / {total - 1} · {cur_t:.2f}s / {tot_t:.1f}s")

        self._update_hud(frame_idx)
        self.frameChanged.emit(frame_idx)

    def _update_hud(self, frame_idx: int) -> None:
        if not self._session:
            return
        fr = self._session.frame_info(frame_idx)
        st = _effective_state(fr)
        samples = self._session.frame_samples(frame_idx)

        if st == "S2":
            self._state_card.setObjectName("StateCardS2")
            self._lbl_state_badge.setText("▲ S2 · 近场音频")
            self._lbl_state_badge.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLORS['state_s2_text']};")
            self._lbl_level.setText("Level 2")
            self._lbl_state_desc.setText("画面近场区存在目标，演示脉冲音频激活（非风险引擎）")
        elif st == "S1":
            self._state_card.setObjectName("StateCardS1")
            self._lbl_state_badge.setText("◆ S1 · 远场提示")
            self._lbl_state_badge.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLORS['state_s1_text']};")
            self._lbl_level.setText("Level 1")
            self._lbl_state_desc.setText("检出中/远场目标，近场区为空（演示规则）")
        else:
            self._state_card.setObjectName("StateCardS0")
            self._lbl_state_badge.setText("● S0 · 静默")
            self._lbl_state_badge.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLORS['state_s0_text']};")
            self._lbl_level.setText("Level 0")
            self._lbl_state_desc.setText("当前帧无检出目标（静默状态）")
        self._state_card.style().unpolish(self._state_card)
        self._state_card.style().polish(self._state_card)

        alert = fr.get("alert")
        nearest_sample = max(samples, key=lambda x: float(x.get("foot", [0, 0])[1])) if samples else None

        if isinstance(alert, dict):
            tid = alert.get("track_id")
            tid_txt = f"#{tid}" if tid is not None and int(tid) >= 0 else "未确认"
            proxy = alert.get("distance_proxy")
            proxy_txt = f"{float(proxy) * 100:.1f}%" if isinstance(proxy, (int, float)) else "—"
            period = alert.get("period_s")
            period_txt = f"{float(period):.3f} s" if isinstance(period, (int, float)) else "—"
            timbre = alert.get("timbre")
            timbre_txt = "A · 行人" if timbre == "A" else ("B · 车辆" if timbre == "B" else "—")
            self._hud_nearest[1].setText(tid_txt)
            self._hud_proxy[1].setText(proxy_txt)
            self._hud_period[1].setText(period_txt)
            self._hud_timbre[1].setText(timbre_txt)
        else:
            if nearest_sample is not None:
                tid = nearest_sample.get("id")
                tid_txt = f"#{tid}" if tid is not None and int(tid) >= 0 else "未确认"
                fn = nearest_sample.get("foot_norm")
                proxy_txt = f"{float(fn) * 100:.1f}%" if isinstance(fn, (int, float)) else "—"
            else:
                tid_txt, proxy_txt = "—", "—"
            self._hud_nearest[1].setText(tid_txt)
            self._hud_proxy[1].setText(proxy_txt)
            self._hud_period[1].setText("—")
            self._hud_timbre[1].setText("—")

        self._z_total[1].setText(str(int(fr.get("count", len(samples)))))
        self._z_near[1].setText(str(int(fr.get("near", 0))))
        self._z_mid[1].setText(str(int(fr.get("mid", 0))))
        self._z_far[1].setText(str(int(fr.get("far", 0))))

        ordered = sorted(samples, key=lambda x: float((x.get("foot") or [0, 0])[1]), reverse=True)
        self._tgt_table.setRowCount(len(ordered))
        zone_cn = {"near": "近场", "mid": "中场", "far": "远场"}
        for r, s in enumerate(ordered):
            tid = s.get("id")
            unassigned = (tid is None or int(tid) < 0)
            id_item = QTableWidgetItem("未确认" if unassigned else f"#{int(tid)}")
            id_item.setData(Qt.ItemDataRole.UserRole, None if unassigned else int(tid))
            cls_item = QTableWidgetItem(str(s.get("name", "—")))
            z_item = QTableWidgetItem(zone_cn.get(s.get("zone"), "—"))
            conf_item = QTableWidgetItem(f"{float(s.get('conf', 0.0)):.2f}")
            for col_i, item in enumerate([id_item, cls_item, z_item, conf_item]):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._tgt_table.setItem(r, col_i, item)

    def _sync_layer_flags(self) -> None:
        self._canvas.show_boxes = self._chk_boxes.isChecked()
        self._canvas.show_foot = self._chk_foot.isChecked()
        self._canvas.show_zones = self._chk_zones.isChecked()
        self._canvas.show_trails = self._chk_trails.isChecked()
        self._canvas.show_status_bar = self._chk_status_bar.isChecked()
        self._canvas.show_unassigned = self._chk_unassigned.isChecked()
        self._canvas.show_legend = self._chk_legend.isChecked()
        self._canvas.update()

    def _on_canvas_target_clicked(self, track_id: int) -> None:
        self._selected_track_id = track_id
        self._btn_jump_track.setEnabled(True)

    def _on_target_row_clicked(self, row: int, _col: int) -> None:
        item = self._tgt_table.item(row, 0)
        if not item:
            return
        tid = item.data(Qt.ItemDataRole.UserRole)
        self._selected_track_id = tid
        self._canvas.set_selected_track(tid)
        self._btn_jump_track.setEnabled(tid is not None)

    def _jump_selected_track(self) -> None:
        if self._selected_track_id is not None:
            self.inspectTrackRequested.emit(self._selected_track_id)

    def close_resources(self) -> None:
        self.pause()
        self._engine.close()
