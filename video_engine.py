# -*- coding: utf-8 -*-
"""高精度视频逐帧解码与智能缓存引擎（基于 OpenCV）。"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PySide6.QtGui import QImage


class VideoFrameEngine:
    """轻量逐帧解码与 LRU 缓存引擎，保证播放丝滑且单帧/拖动零漂移。"""

    def __init__(self, max_cache: int = 120) -> None:
        self._cap: Optional[cv2.VideoCapture] = None
        self._path: Optional[Path] = None
        self._next_pos: int = -1
        self._total_frames: int = 0
        self._fps: float = 30.0
        self._width: int = 0
        self._height: int = 0
        self._cache: OrderedDict[int, QImage] = OrderedDict()
        self._max_cache = max_cache

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def total_frames(self) -> int:
        return self._total_frames

    @property
    def fps(self) -> float:
        return self._fps

    def close(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap = None
        self._path = None
        self._next_pos = -1
        self._total_frames = 0
        self._cache.clear()

    def open(self, path: Optional[Path]) -> bool:
        self.close()
        if path is None or not path.is_file():
            return False
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return False
        self._cap = cap
        self._path = path
        self._next_pos = 0
        self._total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self._fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        self._width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        self._height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        return True

    def get_frame(self, frame_idx: int) -> Optional[QImage]:
        """读取指定帧号（0 起）并返回深拷贝的 QImage（RGB888）。"""
        if not self.is_open:
            return None
        if frame_idx < 0:
            frame_idx = 0
        if self._total_frames > 0 and frame_idx >= self._total_frames:
            frame_idx = self._total_frames - 1

        cached = self._cache.get(frame_idx)
        if cached is not None:
            self._cache.move_to_end(frame_idx)
            return cached

        assert self._cap is not None
        if self._next_pos != frame_idx:
            if 0 < (frame_idx - self._next_pos) <= 4:
                while self._next_pos < frame_idx:
                    ok, _ = self._cap.read()
                    if not ok:
                        break
                    self._next_pos += 1
            else:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                self._next_pos = frame_idx

        ok, bgr = self._cap.read()
        if not ok or bgr is None:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_idx - 1))
            ok, bgr = self._cap.read()
            if not ok or bgr is None:
                return None
            self._next_pos = max(0, frame_idx - 1) + 1
        else:
            self._next_pos = frame_idx + 1

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        if w != self._width or h != self._height:
            self._width, self._height = w, h
        rgb = np.ascontiguousarray(rgb)
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()

        self._cache[frame_idx] = qimg
        self._cache.move_to_end(frame_idx)
        while len(self._cache) > self._max_cache:
            self._cache.popitem(last=False)
        return qimg
