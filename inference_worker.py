# -*- coding: utf-8 -*-
"""本地视频 / 摄像头实时检测与 ByteTrack 追踪后台线程引擎。

设计原则：
- 在独立 QThread 中加载 YOLO 权重与逐帧追踪，绝不阻塞 UI 线程；
- 严格遵循感知层契约 v1.0：
  - 坐标为原视频像素（px），world 恒为 null（未标定）；
  - zone 按脚点归一化高度判定：near > 0.72，mid > 0.45，其余 far；
  - alert 仅采用 scripts/demo.py 演示规则（非风险引擎）；
  - 未确认轨迹 id = -1，不复用上一条轨迹 ID，不计入 tracks；
- 导出结果严格写入程序同级独立目录（user_sessions/），
  绝不修改上游感知工程目录中的任何源码或数据文件。
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def default_user_sessions_dir() -> Path:
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return base / "user_sessions"

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

SCHEMA_VERSION = "1.0"
NEAR_LINE = 0.72
MID_LINE = 0.45
VEHICLE_CLASSES = {2, 3, 5, 7}  # car / motorcycle / bus / truck


@dataclass
class TrackTaskConfig:
    """一次视频实时追踪任务的全部配置。"""
    source_kind: str              # "video" 或 "camera"
    video_path: Optional[Path]
    camera_index: int
    weights_path: Path
    imgsz: int = 960
    conf: float = 0.25
    classes: Optional[List[int]] = None   # None = 全类别；[0] = 仅行人；[0,1,2,3,5,7] = 行人+车辆
    device: str = ""                      # "" 自动；"0" CUDA；"cpu"
    tracker: str = "bytetrack.yaml"
    throttle_to_fps: bool = True          # 是否按原视频帧率限速展示（更适合人眼实时观看）
    save_session: bool = True             # 结束后自动导出 session.json + 16 列 CSV
    output_root: Optional[Path] = None

    def resolved_output_root(self) -> Path:
        return self.output_root if self.output_root is not None else default_user_sessions_dir()


def _safe_slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return s or "imported_video"


def _pct(sorted_values: List[float], q: float) -> Optional[float]:
    if not sorted_values:
        return None
    k = min(len(sorted_values) - 1, max(0, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[k]


class LiveTrackingWorker(QThread):
    """逐帧执行 YOLO + ByteTrack 并将实时帧、检测框、状态与统计推送至前端。"""

    statusMessage = Signal(str)
    # payload: dict{frame_idx, total_frames, fps, width, height, qimage, frame_info, samples, trails, infer_ms, live_fps}
    frameProcessed = Signal(dict)
    # finished payload: dict{session_json: str|None, csv_path: str|None, frames: int, samples: int, tracks: int, avg_fps: float, elapsed_s: float}
    trackingFinished = Signal(dict)
    trackingError = Signal(str)

    def __init__(self, cfg: TrackTaskConfig, parent=None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._stop_flag = False
        self._pause_flag = False

    def request_stop(self) -> None:
        self._stop_flag = True
        self._pause_flag = False

    def set_paused(self, paused: bool) -> None:
        self._pause_flag = paused

    def set_throttle(self, enabled: bool) -> None:
        self._cfg.throttle_to_fps = enabled

    def run(self) -> None:
        cap = None
        try:
            cfg = self._cfg
            if not cfg.weights_path.is_file():
                self.trackingError.emit(f"未找到模型权重文件：{cfg.weights_path}")
                return

            if cfg.source_kind == "video":
                if not cfg.video_path or not cfg.video_path.is_file():
                    self.trackingError.emit("未选择有效的本地视频文件。")
                    return
                cap = cv2.VideoCapture(str(cfg.video_path))
                if not cap.isOpened():
                    self.trackingError.emit(f"无法打开视频文件：{cfg.video_path}")
                    return
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
                if src_fps <= 1e-3 or src_fps > 240.0:
                    src_fps = 30.0
            else:
                cap = cv2.VideoCapture(cfg.camera_index, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(cfg.camera_index)
                if not cap.isOpened():
                    self.trackingError.emit(f"无法打开摄像头设备 #{cfg.camera_index}，请检查连接或权限。")
                    return
                total_frames = 0
                src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
                if src_fps <= 1e-3:
                    src_fps = 30.0

            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

            self.statusMessage.emit(f"正在加载模型权重 {cfg.weights_path.name}（设备：{cfg.device or '自动'}）...")
            import torch
            from ultralytics import YOLO

            device = cfg.device
            if not device:
                device = "0" if torch.cuda.is_available() else "cpu"

            model = YOLO(str(cfg.weights_path))
            names = model.names or {}
            self.statusMessage.emit(f"模型已就绪（{cfg.weights_path.name} @ {device}），开始实时检测与 ByteTrack 追踪...")

            # 采集数据用于结束后导出标准 session.json 与 16 列 CSV
            all_samples: List[Dict[str, Any]] = []
            all_frames: List[Dict[str, Any]] = []
            active_trails: Dict[int, List[Tuple[int, float, float]]] = {}

            t_start_all = time.perf_counter()
            frame_idx = 0
            fps_window: List[float] = []

            while not self._stop_flag:
                while self._pause_flag and not self._stop_flag:
                    self.msleep(35)
                if self._stop_flag:
                    break

                t_loop = time.perf_counter()
                ok, bgr = cap.read()
                if not ok or bgr is None:
                    break

                h, w = bgr.shape[:2]
                if width == 0 or height == 0:
                    width, height = w, h

                t_inf0 = time.perf_counter()
                res = model.track(
                    bgr,
                    persist=True,
                    imgsz=cfg.imgsz,
                    conf=cfg.conf,
                    classes=cfg.classes,
                    tracker=cfg.tracker,
                    device=device,
                    verbose=False,
                )[0]
                infer_ms = (time.perf_counter() - t_inf0) * 1000.0

                t_sec = round(frame_idx / src_fps, 3)
                sample_start = len(all_samples)
                frame_samples: List[Dict[str, Any]] = []
                near_cnt = mid_cnt = far_cnt = 0
                nearest: Optional[Tuple[float, Dict[str, Any]]] = None

                boxes = res.boxes
                if boxes is not None and len(boxes) > 0:
                    xyxy = boxes.xyxy.cpu().numpy()
                    cls_arr = boxes.cls.cpu().numpy().astype(int)
                    conf_arr = boxes.conf.cpu().numpy()
                    id_arr = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else None

                    for idx_b in range(len(xyxy)):
                        x1, y1, x2, y2 = [float(v) for v in xyxy[idx_b]]
                        cid = int(cls_arr[idx_b])
                        cf = float(conf_arr[idx_b])
                        tid = int(id_arr[idx_b]) if id_arr is not None else -1
                        cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
                        fx, fy = cx, y2
                        norm_y = fy / max(float(h), 1.0)
                        if norm_y > NEAR_LINE:
                            zone = "near"
                            near_cnt += 1
                        elif norm_y > MID_LINE:
                            zone = "mid"
                            mid_cnt += 1
                        else:
                            zone = "far"
                            far_cnt += 1

                        cname = str(names.get(cid, str(cid))) if isinstance(names, dict) else str(cid)
                        s_obj: Dict[str, Any] = {
                            "f": frame_idx,
                            "t": t_sec,
                            "id": tid,
                            "cls": cid,
                            "name": cname,
                            "conf": round(cf, 3),
                            "box": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                            "center": [round(cx, 1), round(cy, 1)],
                            "foot": [round(fx, 1), round(fy, 1)],
                            "world": None,
                            "zone": zone,
                            "foot_norm": round(norm_y, 4),
                        }
                        frame_samples.append(s_obj)
                        all_samples.append(s_obj)

                        if tid >= 0:
                            tr_pts = active_trails.setdefault(tid, [])
                            tr_pts.append((frame_idx, round(fx, 1), round(fy, 1)))
                            if len(tr_pts) > 50:
                                del tr_pts[:-50]

                        if zone == "near":
                            if nearest is None or norm_y > nearest[0]:
                                nearest = (norm_y, s_obj)

                sample_end = len(all_samples)
                if nearest is not None:
                    norm_y, ns = nearest
                    timbre = "B" if ns["cls"] in VEHICLE_CLASSES else "A"
                    period = max(0.12, min(0.12 + 0.55 * (1.0 - norm_y), 1.0))
                    state = "S2"
                    alert = {
                        "active": True,
                        "timbre": timbre,
                        "period_s": round(period, 3),
                        "track_id": ns["id"],
                        "distance_proxy": round(norm_y, 4),
                    }
                elif len(frame_samples) > 0:
                    state = "S1"
                    alert = None
                else:
                    state = "S0"
                    alert = None

                fr_info = {
                    "i": frame_idx,
                    "t": t_sec if frame_samples else None,
                    "count": len(frame_samples),
                    "near": near_cnt,
                    "mid": mid_cnt,
                    "far": far_cnt,
                    "state": state,
                    "alert": alert,
                    "sample_start": sample_start,
                    "sample_end": sample_end,
                }
                all_frames.append(fr_info)

                # 转 RGB QImage 推送 UI
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                rgb = np.ascontiguousarray(rgb)
                qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()

                # 只拷贝当前帧涉及到的轨迹尾迹，避免跨线程共享可变容器
                cur_trails = {
                    s["id"]: list(active_trails[s["id"]])
                    for s in frame_samples
                    if s["id"] >= 0 and s["id"] in active_trails
                }

                loop_dt = max(time.perf_counter() - t_loop, 1e-4)
                fps_window.append(1.0 / loop_dt)
                if len(fps_window) > 20:
                    fps_window.pop(0)
                live_fps = sum(fps_window) / len(fps_window)

                self.frameProcessed.emit({
                    "frame_idx": frame_idx,
                    "total_frames": total_frames,
                    "fps": src_fps,
                    "width": w,
                    "height": h,
                    "qimage": qimg,
                    "frame_info": fr_info,
                    "samples": frame_samples,
                    "trails": cur_trails,
                    "infer_ms": infer_ms,
                    "live_fps": live_fps,
                    "device": device,
                })

                frame_idx += 1

                # 若开启原速节流，补足剩余帧间隔
                if cfg.throttle_to_fps and cfg.source_kind == "video":
                    budget = 1.0 / src_fps
                    spent = time.perf_counter() - t_loop
                    if spent < budget:
                        self.msleep(int((budget - spent) * 1000))

            elapsed_all = max(time.perf_counter() - t_start_all, 1e-4)
            avg_fps = frame_idx / elapsed_all

            # 仅本地视频且开启自动保存、且至少跑了 1 帧时导出标准 session.json + 16 列 CSV
            session_json_path: Optional[Path] = None
            csv_path: Optional[Path] = None
            tracks_count = 0

            if cfg.save_session and cfg.source_kind == "video" and cfg.video_path and frame_idx > 0:
                self.statusMessage.emit("正在生成标准 session.json 与 16 列轨迹 CSV（写入 user_sessions）...")
                session_json_path, csv_path, tracks_count = self._export_artifacts(
                    cfg=cfg,
                    width=width,
                    height=height,
                    fps=src_fps,
                    frames=all_frames,
                    samples=all_samples,
                )

            self.trackingFinished.emit({
                "session_json": str(session_json_path) if session_json_path else None,
                "csv_path": str(csv_path) if csv_path else None,
                "frames": frame_idx,
                "samples": len(all_samples),
                "tracks": tracks_count,
                "avg_fps": avg_fps,
                "elapsed_s": elapsed_all,
                "stopped_early": self._stop_flag,
            })

        except Exception as exc:  # noqa: BLE001
            self.trackingError.emit(f"实时推理异常：{type(exc).__name__}: {exc}")
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def _export_artifacts(
        self,
        cfg: TrackTaskConfig,
        width: int,
        height: int,
        fps: float,
        frames: List[Dict[str, Any]],
        samples: List[Dict[str, Any]],
    ) -> Tuple[Path, Path, int]:
        assert cfg.video_path is not None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = _safe_slug(cfg.video_path.stem)
        sid = f"live_{slug}_{cfg.weights_path.stem}_{ts}"
        out_dir = cfg.resolved_output_root() / sid
        out_dir.mkdir(parents=True, exist_ok=True)

        csv_path = out_dir / f"{sid}_tracks.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow([
                "frame", "timestamp", "track_id", "class_id", "class_name", "conf",
                "x1", "y1", "x2", "y2", "cx", "cy", "foot_x", "foot_y",
                "world_x", "world_y",
            ])
            for s in samples:
                x1, y1, x2, y2 = s["box"]
                cx, cy = s["center"]
                fx, fy = s["foot"]
                w.writerow([
                    s["f"], s["t"], s["id"], s["cls"], s["name"], s["conf"],
                    x1, y1, x2, y2, cx, cy, fx, fy, "", "",
                ])

        # 汇总 tracks（严格排除 id < 0 未确认样本）
        by_id: Dict[int, List[Dict[str, Any]]] = {}
        unassigned = 0
        for s in samples:
            if s["id"] < 0:
                unassigned += 1
                continue
            by_id.setdefault(s["id"], []).append(s)

        tracks: List[Dict[str, Any]] = []
        for tid in sorted(by_id):
            pts = by_id[tid]
            confs = [p["conf"] for p in pts]
            tracks.append({
                "track_id": tid,
                "class_id": pts[0]["cls"],
                "class_name": pts[0]["name"],
                "first_frame": pts[0]["f"],
                "last_frame": pts[-1]["f"],
                "n": len(pts),
                "conf_mean": round(sum(confs) / len(confs), 3),
                "conf_max": round(max(confs), 3),
                "foot_path": [[p["f"], p["foot"][0], p["foot"][1]] for p in pts],
            })

        n_frames = len(frames)
        confs_all = sorted(s["conf"] for s in samples)
        classes_cnt: Dict[str, int] = {}
        for s in samples:
            k = s["name"] or str(s["cls"])
            classes_cnt[k] = classes_cnt.get(k, 0) + 1
        hit_frames = sum(1 for fr in frames if fr["count"] > 0)
        near_frames = sum(1 for fr in frames if fr["state"] == "S2")
        duration_s = round(n_frames / max(fps, 1e-6), 3)

        doc = {
            "schema_version": SCHEMA_VERSION,
            "session_id": sid,
            "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "generator": "VisionMonitorDesktop/inference_worker.py",
            "source": {
                "csv": str(csv_path).replace("\\", "/"),
                "video": str(cfg.video_path.resolve()).replace("\\", "/"),
            },
            "video": {
                "filename": cfg.video_path.name,
                "width": width,
                "height": height,
                "fps": round(fps, 3),
                "frames": n_frames,
                "duration_s": duration_s,
            },
            "model": {
                "weights": str(cfg.weights_path.name),
                "name": cfg.weights_path.stem,
                "imgsz": cfg.imgsz,
                "conf": cfg.conf,
                "tracker": cfg.tracker,
            },
            "calibration": {
                "homography": None,
                "metric": False,
                "note": "未标定：坐标是像素，不是米；world 字段为 null 时禁止按米制展示。",
            },
            "zones": {
                "near_line": NEAR_LINE,
                "mid_line": MID_LINE,
                "basis": "foot_y / video.height",
                "semantic": "演示用画面下沿占比分区，非物理坐标",
            },
            "summary": {
                "frames": n_frames,
                "duration_s": duration_s,
                "samples": len(samples),
                "tracks": len(tracks),
                "unassigned_samples": unassigned,
                "frames_with_targets": hit_frames,
                "detect_frame_rate": round(hit_frames / n_frames, 4) if n_frames else None,
                "near_frames": near_frames,
                "max_targets_per_frame": max((fr["count"] for fr in frames), default=0),
                "mean_conf": round(sum(confs_all) / len(confs_all), 3) if confs_all else None,
                "conf_p50": _pct(confs_all, 0.5) if confs_all else None,
                "classes": classes_cnt,
            },
            "quality": None,
            "frames": frames,
            "samples": samples,
            "tracks": tracks,
        }

        session_path = out_dir / f"{sid}.session.json"
        session_path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return session_path, csv_path, len(tracks)
