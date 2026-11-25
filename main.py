# -*- coding: utf-8 -*-
"""视障动态障碍物感知工程 · 原生桌面可视化控制台启动入口。

用法：
    python main.py
    python main.py --data-dir /path/to/perception_project
    （也可通过环境变量 VISION_DATA_DIR 指定默认数据目录）
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path


def _ensure_stdio_for_windowed_exe() -> None:
    """PyInstaller --windowed 模式下 sys.stdout/stderr 可能为 None，
    而 ultralytics / torch 日志输出会写入它们；这里安全重定向到日志文件，避免 NoneType 崩溃。
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    try:
        log_file = open(base / "runtime.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        log_file = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = log_file
    if sys.stderr is None:
        sys.stderr = log_file


_ensure_stdio_for_windowed_exe()

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox

from main_window import MainWindow
from theme import build_stylesheet

def resolve_default_data_dir() -> Path:
    """按开箱即用优先级自动探测数据目录：环境变量 VISION_DATA_DIR -> 同级 bundled_data -> 当前目录。"""
    app_base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    env_dir = os.environ.get("VISION_DATA_DIR", "").strip()
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.extend([
        app_base / "bundled_data",
        app_base / "data",
        app_base,
    ])
    for cand in candidates:
        if (cand / "out" / "web").is_dir() or (cand / "data" / "web").is_dir():
            return cand
    return app_base


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="视障感知工程原生桌面可视化控制台")
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="感知工程根目录（含 out/web 或 data/web）",
    )
    ap.add_argument(
        "--selftest-live",
        action="store_true",
        help="在当前运行环境（含冻结 EXE）内执行一次真实 YOLO26n + ByteTrack 推理自检后退出",
    )
    return ap.parse_args()


def run_selftest_live(data_root: Path) -> int:
    """在冻结 EXE 内直接验证 torchvision::nms + YOLO26n + ByteTrack 真实追踪链路。"""
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    log_path = base / "selftest_live.log"
    lines = []
    try:
        import cv2
        import torch
        import torchvision
        from torchvision.extension import _has_ops
        from ultralytics import YOLO

        lines.append(f"frozen={getattr(sys, 'frozen', False)} exe={sys.executable}")
        lines.append(f"torch={torch.__version__} cuda={torch.cuda.is_available()}")
        lines.append(f"torchvision={torchvision.__version__} has_ops={_has_ops()}")
        assert _has_ops(), "torchvision C++ ops (_C_stable) 未加载！"

        # 1) 直接测试 torchvision.ops.nms（CPU + CUDA）
        boxes = torch.tensor([[0.0, 0.0, 10.0, 10.0], [1.0, 1.0, 11.0, 11.0]], dtype=torch.float32)
        scores = torch.tensor([0.9, 0.8], dtype=torch.float32)
        keep_cpu = torchvision.ops.nms(boxes, scores, 0.5)
        lines.append(f"nms_cpu_ok keep={keep_cpu.tolist()}")
        if torch.cuda.is_available():
            keep_cuda = torchvision.ops.nms(boxes.cuda(), scores.cuda(), 0.5)
            lines.append(f"nms_cuda_ok keep={keep_cuda.tolist()}")

        # 2) 真实加载内置 yolo26n.pt + synthetic_bus.mp4 跑 10 帧 ByteTrack
        weights = data_root / "weights" / "yolo26n.pt"
        video = data_root / "data" / "raw" / "synthetic_bus.mp4"
        assert weights.is_file(), f"缺少权重: {weights}"
        assert video.is_file(), f"缺少测试视频: {video}"

        model = YOLO(str(weights))
        cap = cv2.VideoCapture(str(video))
        assert cap.isOpened(), f"打不开视频: {video}"
        device = "0" if torch.cuda.is_available() else "cpu"
        det_total = 0
        id_set = set()
        for i in range(10):
            ok, frame = cap.read()
            if not ok:
                break
            res = model.track(frame, persist=True, imgsz=640, conf=0.25, classes=[0, 1, 2, 3, 5, 7], tracker="bytetrack.yaml", device=device, verbose=False)[0]
            if res.boxes is not None and len(res.boxes) > 0:
                det_total += len(res.boxes)
                if res.boxes.id is not None:
                    id_set.update(res.boxes.id.cpu().numpy().astype(int).tolist())
        cap.release()
        lines.append(f"yolo_bytetrack_ok device={device} frames=10 detections={det_total} track_ids={sorted(id_set)}")
        assert det_total > 0, "10 帧检出数为 0"
        lines.append("SELFTEST_PASS")
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0
    except Exception:  # noqa: BLE001
        lines.append("SELFTEST_FAIL")
        lines.append(traceback.format_exc())
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1


def main() -> int:
    args = parse_args()
    data_root = args.data_dir if (args.data_dir and args.data_dir.exists()) else resolve_default_data_dir()
    if args.selftest_live:
        return run_selftest_live(data_root)

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("视障感知工程可视化控制台")
    for fp in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        if Path(fp).is_file():
            QFontDatabase.addApplicationFont(fp)
    app.setFont(QFont("Microsoft YaHei UI", 11))
    app.setStyleSheet(build_stylesheet())

    try:
        win = MainWindow(data_root=data_root)
        win.show()
        return app.exec()
    except Exception:  # noqa: BLE001
        err = traceback.format_exc()
        base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        try:
            (base / "crash_error.log").write_text(err, encoding="utf-8")
        except OSError:
            pass
        QMessageBox.critical(None, "启动异常", f"程序启动出现异常，详情已写入 crash_error.log：\n\n{err[-800:]}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
