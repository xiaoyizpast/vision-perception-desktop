# -*- coding: utf-8 -*-
"""只读数据加载与契约适配层（v1.0）。

兼容两种目录布局：
1. 工程仓库布局：
   - out/web/*.session.json & *.run.json
   - out/compare/compare.json & out/compare/*.jpg
   - out/probe/*.png
   - data/raw/*.mp4
   - runs_web/<id>/{meta.json, timeline.json, audio.wav, video.mp4}（可选脉冲刻度与演示音频）
2. 交付快照目录布局：
   - data/web/*.session.json & *.run.json & compare.json
   - data/video/*.mp4

只读约定：绝不修改、写入或伪造任何原始数据。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class StateSegment:
    """时间轴合并后的连续状态区间（含端点 [start_frame, end_frame]）。"""
    state: str
    start_frame: int
    end_frame: int


@dataclass
class PulseEvent:
    """演示音频脉冲时刻（来自 runs_web/<id>/timeline.json 或由 S2 period_s 推导显示刻度）。"""
    t: float
    timbre: Optional[str] = None
    interval_s: Optional[float] = None
    track_id: Optional[int] = None


@dataclass
class SessionBundle:
    """单个回放会话的只读数据包。"""
    session_id: str
    title: str
    json_path: Path
    raw: Dict[str, Any]
    video_path: Optional[Path]
    audio_path: Optional[Path]
    pulses: List[PulseEvent] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    state_segments: List[StateSegment] = field(default_factory=list)
    track_by_id: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    @property
    def video(self) -> Optional[Dict[str, Any]]:
        return self.raw.get("video")

    @property
    def model(self) -> Dict[str, Any]:
        return self.raw.get("model") or {}

    @property
    def calibration(self) -> Dict[str, Any]:
        return self.raw.get("calibration") or {"metric": False, "homography": None, "note": ""}

    @property
    def zones(self) -> Dict[str, Any]:
        return self.raw.get("zones") or {
            "near_line": 0.72,
            "mid_line": 0.45,
            "basis": "foot_y / video.height",
            "semantic": "演示用画面下沿占比分区，非物理坐标",
        }

    @property
    def summary(self) -> Dict[str, Any]:
        return self.raw.get("summary") or {}

    @property
    def quality(self) -> Optional[Dict[str, Any]]:
        return self.raw.get("quality")

    @property
    def frames(self) -> List[Dict[str, Any]]:
        return self.raw.get("frames") or []

    @property
    def samples(self) -> List[Dict[str, Any]]:
        return self.raw.get("samples") or []

    @property
    def tracks(self) -> List[Dict[str, Any]]:
        return self.raw.get("tracks") or []

    @property
    def frame_count(self) -> int:
        if self.video and self.video.get("frames"):
            return int(self.video["frames"])
        return len(self.frames)

    @property
    def fps(self) -> float:
        if self.video and self.video.get("fps"):
            return float(self.video["fps"])
        return 30.0

    def frame_samples(self, frame_idx: int) -> List[Dict[str, Any]]:
        """按契约 O(1) 切片取第 frame_idx 帧目标，不全表过滤。"""
        if not self.frames or frame_idx < 0 or frame_idx >= len(self.frames):
            return []
        fr = self.frames[frame_idx]
        s0 = int(fr.get("sample_start", 0))
        s1 = int(fr.get("sample_end", s0))
        if s0 < 0 or s1 < s0 or s0 >= len(self.samples):
            return []
        return self.samples[s0:min(s1, len(self.samples))]

    def frame_info(self, frame_idx: int) -> Dict[str, Any]:
        if not self.frames or frame_idx < 0 or frame_idx >= len(self.frames):
            return {"i": frame_idx, "t": None, "count": 0, "near": 0, "mid": 0, "far": 0, "state": "S0", "alert": None}
        return self.frames[frame_idx]


@dataclass
class RunBundle:
    """训练监控 run.json 只读数据包。"""
    run_id: str
    json_path: Path
    raw: Dict[str, Any]
    existing_artifacts: List[Tuple[str, Path, int]] = field(default_factory=list)


@dataclass
class CompareFrameGroup:
    """模型对比同一视频同一帧的三模型对比图组。"""
    video: str
    frame: int
    images: Dict[str, Path]


@dataclass
class WorkspaceData:
    """整个数据根目录的扫描结果。"""
    root: Path
    sessions: List[SessionBundle] = field(default_factory=list)
    runs: List[RunBundle] = field(default_factory=list)
    compare_rows: List[Dict[str, Any]] = field(default_factory=list)
    compare_frame_groups: List[CompareFrameGroup] = field(default_factory=list)
    probe_images: List[Path] = field(default_factory=list)


def _read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _effective_state(fr: Dict[str, Any]) -> str:
    """容错：若出现 state=='S0' 且 count>0（契约第 8 节），按 count 优先渲染为 S1/S2。"""
    st = fr.get("state") or "S0"
    cnt = int(fr.get("count", 0))
    if st == "S0" and cnt > 0:
        return "S2" if int(fr.get("near", 0)) > 0 else "S1"
    return st


def _merge_state_segments(frames: List[Dict[str, Any]]) -> List[StateSegment]:
    """把连续相同的 S0/S1/S2 帧合并成区间，符合 docs/06 第 4 节第 4 条。"""
    if not frames:
        return []
    segs: List[StateSegment] = []
    cur_state = _effective_state(frames[0])
    start = int(frames[0].get("i", 0))
    prev = start
    for idx in range(1, len(frames)):
        fr = frames[idx]
        st = _effective_state(fr)
        fi = int(fr.get("i", idx))
        if st != cur_state:
            segs.append(StateSegment(state=cur_state, start_frame=start, end_frame=prev))
            cur_state = st
            start = fi
        prev = fi
    segs.append(StateSegment(state=cur_state, start_frame=start, end_frame=prev))
    return segs


def _resolve_video_path(raw: Dict[str, Any], root: Path, json_path: Path) -> Optional[Path]:
    video_meta = raw.get("video")
    if not video_meta:
        return None
    filename = video_meta.get("filename")
    src_video = (raw.get("source") or {}).get("video")

    candidates: List[Path] = []
    if filename:
        candidates.extend([
            root / "data" / "raw" / filename,
            root / "data" / "video" / filename,
            json_path.parent.parent / "video" / filename,
            json_path.parent.parent / "raw" / filename,
            json_path.parent / filename,
        ])
    if src_video:
        p = Path(src_video)
        candidates.append(p if p.is_absolute() else root / p)

    sid = raw.get("session_id", "")
    alias_ids = [sid] + (["synthetic_bus"] if sid == "demo_synthetic_bus" else [])
    for aid in alias_ids:
        candidates.append(root / "runs_web" / aid / "video.mp4")

    for cand in candidates:
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


def _resolve_runs_web_extras(raw: Dict[str, Any], root: Path) -> Tuple[Optional[str], Optional[Path], List[PulseEvent], List[str]]:
    """若仓库中存在 runs_web/<id>/，读取可选的展示标题、audio.wav 与脉冲刻度 pulses。"""
    sid = raw.get("session_id", "")
    candidates = [sid] + (["synthetic_bus"] if sid == "demo_synthetic_bus" else [])

    for cid in candidates:
        run_dir = root / "runs_web" / cid
        if not run_dir.is_dir():
            continue
        title = None
        notes: List[str] = []
        meta = _read_json(run_dir / "meta.json")
        if isinstance(meta, dict):
            title = meta.get("title")
            if isinstance(meta.get("notes"), list):
                notes = [str(x) for x in meta["notes"]]
        audio_path = run_dir / "audio.wav"
        if not audio_path.is_file():
            audio_path = None
        pulses: List[PulseEvent] = []
        tl = _read_json(run_dir / "timeline.json")
        if isinstance(tl, dict) and isinstance(tl.get("pulses"), list):
            for p in tl["pulses"]:
                if isinstance(p, dict) and "t" in p:
                    pulses.append(
                        PulseEvent(
                            t=float(p["t"]),
                            timbre=p.get("timbre"),
                            interval_s=p.get("interval_s"),
                            track_id=p.get("track_id"),
                        )
                    )
        return title, audio_path, pulses, notes
    return None, None, [], []


def _synthesize_pulses_from_frames(frames: List[Dict[str, Any]], fps: float) -> List[PulseEvent]:
    """当没有 runs_web/timeline.json 时，按 frames[].alert.period_s 在 S2 段生成可视化脉冲刻度。"""
    pulses: List[PulseEvent] = []
    next_t: Optional[float] = None
    for fr in frames:
        st = _effective_state(fr)
        alert = fr.get("alert")
        if st != "S2" or not isinstance(alert, dict):
            next_t = None
            continue
        t = fr.get("t")
        t_f = float(t) if t is not None else int(fr.get("i", 0)) / max(fps, 1e-6)
        period = max(0.12, min(float(alert.get("period_s") or 0.25), 1.0))
        if next_t is None or t_f >= next_t:
            pulses.append(
                PulseEvent(
                    t=t_f,
                    timbre=alert.get("timbre"),
                    interval_s=period,
                    track_id=alert.get("track_id"),
                )
            )
            next_t = t_f + period
    return pulses


def _friendly_title(raw: Dict[str, Any], runs_web_title: Optional[str]) -> str:
    if runs_web_title:
        return runs_web_title
    sid = raw.get("session_id", "session")
    name_map = {
        "field_v2_s": "夜间校园 · field_v2",
        "field_v1_s": "傍晚逆光 · field_v1",
        "demo_synthetic_bus": "合成样例 · synthetic_bus",
    }
    base = name_map.get(sid, sid)
    model = raw.get("model") or {}
    parts = [base]
    if model.get("name"):
        parts.append(str(model["name"]))
    if model.get("imgsz"):
        parts.append(str(model["imgsz"]))
    return " · ".join(parts)


def load_session_file(path: Path, root: Path) -> Optional[SessionBundle]:
    raw = _read_json(path)
    if not isinstance(raw, dict) or "frames" not in raw or "samples" not in raw:
        return None
    video_path = _resolve_video_path(raw, root, path)
    rw_title, audio_path, pulses, notes = _resolve_runs_web_extras(raw, root)
    title = _friendly_title(raw, rw_title)
    frames = raw.get("frames") or []
    fps = float((raw.get("video") or {}).get("fps") or 30.0)
    if not pulses:
        pulses = _synthesize_pulses_from_frames(frames, fps)
    segments = _merge_state_segments(frames)
    track_by_id: Dict[int, Dict[str, Any]] = {}
    for tr in raw.get("tracks") or []:
        tid = tr.get("track_id")
        if tid is not None and int(tid) >= 0:
            track_by_id[int(tid)] = tr

    return SessionBundle(
        session_id=str(raw.get("session_id") or path.stem),
        title=title,
        json_path=path,
        raw=raw,
        video_path=video_path,
        audio_path=audio_path,
        pulses=pulses,
        notes=notes,
        state_segments=segments,
        track_by_id=track_by_id,
    )


def load_run_file(path: Path, root: Path) -> Optional[RunBundle]:
    raw = _read_json(path)
    if not isinstance(raw, dict) or "epochs" not in raw or "best" not in raw:
        return None
    existing: List[Tuple[str, Path, int]] = []
    artifacts = raw.get("artifacts") or {}
    for rel_name, info in artifacts.items():
        if not isinstance(info, dict):
            continue
        p_str = info.get("path", "")
        bsize = int(info.get("bytes", 0))
        cand_paths = [Path(p_str)] if p_str else []
        if p_str and not Path(p_str).is_absolute():
            cand_paths.append(root / p_str)
        run_id = raw.get("run_id", "")
        if run_id:
            cand_paths.append(root / "runs" / "detect" / run_id / rel_name)
        for cp in cand_paths:
            try:
                if cp.is_file():
                    existing.append((rel_name, cp, bsize))
                    break
            except OSError:
                continue
    return RunBundle(
        run_id=str(raw.get("run_id") or path.stem),
        json_path=path,
        raw=raw,
        existing_artifacts=existing,
    )


def _scan_compare_frames(compare_dir: Path) -> List[CompareFrameGroup]:
    if not compare_dir.is_dir():
        return []
    pat = re.compile(r"^(.+)_f(\d+)_([^.]+)\.(jpg|jpeg|png)$", re.IGNORECASE)
    grouped: Dict[Tuple[str, int], Dict[str, Path]] = {}
    for img in sorted(compare_dir.iterdir()):
        if not img.is_file():
            continue
        m = pat.match(img.name)
        if not m:
            continue
        video, frame_s, model_name = m.group(1), m.group(2), m.group(3)
        grouped.setdefault((video, int(frame_s)), {})[model_name] = img
    return [
        CompareFrameGroup(video=video, frame=frame, images=imgs)
        for (video, frame), imgs in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    ]


def load_workspace(root: Path) -> WorkspaceData:
    """扫描整个项目根目录或交付快照目录，返回完整只读数据结构。"""
    root = root.resolve()
    ws = WorkspaceData(root=root)

    json_dirs: List[Path] = []
    for rel in [Path("out/web"), Path("data/web"), Path(".")]:
        d = root / rel
        if d.is_dir() and d not in json_dirs:
            json_dirs.append(d)

    # 同时扫描用户通过 V6 实时追踪导出的本地会话目录（位于独立桌面程序目录旁）
    app_base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    user_sess_root = app_base / "user_sessions"
    if user_sess_root.is_dir():
        for sub in sorted(user_sess_root.iterdir(), reverse=True):
            if sub.is_dir() and sub not in json_dirs:
                json_dirs.append(sub)

    seen_session_ids = set()
    seen_run_ids = set()

    for jdir in json_dirs:
        for f in sorted(jdir.glob("*.session.json")):
            sb = load_session_file(f, root)
            if sb and sb.session_id not in seen_session_ids:
                seen_session_ids.add(sb.session_id)
                ws.sessions.append(sb)
        for f in sorted(jdir.glob("*.run.json")):
            rb = load_run_file(f, root)
            if rb and rb.run_id not in seen_run_ids:
                seen_run_ids.add(rb.run_id)
                ws.runs.append(rb)

    priority = {"field_v2_s": 0, "field_v1_s": 1, "demo_synthetic_bus": 2}
    ws.sessions.sort(key=lambda s: (priority.get(s.session_id, 50), s.session_id))

    for cpath in [
        root / "out" / "compare" / "compare.json",
        root / "data" / "web" / "compare.json",
        root / "compare.json",
    ]:
        if cpath.is_file():
            rows = _read_json(cpath)
            if isinstance(rows, list):
                ws.compare_rows = rows
                break

    ws.compare_frame_groups = _scan_compare_frames(root / "out" / "compare")

    probe_dir = root / "out" / "probe"
    if probe_dir.is_dir():
        ws.probe_images = sorted(
            [p for p in probe_dir.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
        )

    return ws
