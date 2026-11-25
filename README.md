# Vision Perception Desktop（视障动态障碍物感知 · 原生桌面可视化控制台）

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![PySide6 / Qt6](https://img.shields.io/badge/GUI-PySide6%20(Qt6)-41CD52.svg)](https://doc.qt.io/qtforpython-6/)

面向**视障人士动态障碍物感知与风险预测研究**打造的**纯原生桌面可视化与实时追踪控制台**（基于 Python + PySide6 / Qt6 + OpenCV + YOLO26n + ByteTrack，**非网页、无浏览器内核、完全离线运行**）。

项目严格遵循**可视化前端数据契约 v1.0**，既可以只读回放结构化检测/轨迹/训练/横评数据，也内置本地视频导入与摄像头实时推理追踪工作台，并支持自动导出标准 `session.json` 与 16 列轨迹 CSV 供下游风险决策引擎消费。

---

## 核心特性

- **纯原生桌面体验 + 浅/深双主题**：默认清爽现代浅色主题（高对比度 WCAG AA ≥ 4.5:1），顶栏一键无刷新切换深色主题；顶部双层导航释放主视野，全视图支持可拖拽 `QSplitter` 自适应 1366×768 及以上分辨率。
- **零错位原视频像素叠加**：视频与检测框在原视频像素坐标系下等比缩放渲染（完美适配 `720×1280` 竖屏与横屏），内置 120 帧 LRU 缓存，逐帧步进与进度条 Seek 零漂移。
- **端到端视频导入与实时追踪（V6）**：支持点击或直接拖放任意体积的本地视频（不受 20MB 限制）及本机摄像头，后台 `QThread` 实时执行 `YOLO26n + ByteTrack` 行人/交通目标追踪，实时输出叠加画面、轨迹尾迹、S0/S1/S2 状态 HUD，并自动导出合规 `session.json` 与 16 列 CSV。
- **严格恪守三条工程诚实红线**：
  1. **像素不是米**：未标定（`calibration.metric == false`）时所有坐标标明像素 `px`，`near/mid/far` 明确表述为「画面下沿占比分区」，绝不伪造物理米制距离或速度。
  2. **`alert` 不是风险引擎**：`S0 / S1 / S2` 脉冲节奏明确标注为演示规则，不伪造碰撞概率或风险分数，不作任何避障安全承诺。
  3. **不虚标精度**：无标注视频的检出统计明确标注为「有检出帧占比（非准确率）」；训练监控顶部固定免责提示。

---

## 六大功能视图（快捷键 `1` – `6`）

| 视图 | 快捷键 | 消费数据 / 输入 | 核心能力 |
|---|---|---|---|
| **V1 感知回放台** | `1` | `*.session.json` + 原视频 + 可选 `audio.wav` | 原视频像素坐标系叠加层（近/中/远场框、未确认 `id=-1` 灰虚线框、蓝色脚点、`NEAR/MID` 分区虚线、轨迹尾迹、画面状态条、`L` 开合图例）；合并区间状态时间轴（S0 灰 / S1 黄 / S2 红 + 脉冲竖纹）；单帧 / ±1s / 倍速 / 音频同步播控；右侧实时 HUD 与当前帧目标表 |
| **V2 轨迹视图** | `2` | `tracks[].foot_path` | 图像平面轨迹示意（纵轴向下，单位 `px`，标注非米制俯视图）；按类别、途经分区、置信度下限、最短轨迹帧数、ID 搜索多维过滤；悬停预览，点击或双击双向同步 V1 播放头 |
| **V3 画质体检** | `3` | `session.quality` + 参考抽样帧 | 客观展示亮度、对比度、清晰度、发虚帧占比、暗部/过曝像素占比（不做阈值判定）与参考帧高清画廊；`quality == null` 时展示规范空态 |
| **V4 训练监控** | `4` | `*.run.json` + 训练产物图 | 顶部固定免责横幅、早停徽标（`[早停] epochs_run/planned`）、Best Epoch 摘要卡、原生矢量交互损失/指标/学习率曲线（含 `BEST` 竖线与鼠标十字读数）、缺失图片自动隐藏的产物画廊 |
| **V5 模型对比** | `5` | `compare.json` + 同帧对比图 | 可排序横评表格（同视频内「单帧耗时」最优绿标与「有检出帧占比」最优蓝标分列高亮，不合成单一总分）、双栏对比柱状图、同帧三模型并排高清对比 |
| **V6 视频导入追踪** | `6` | 任意本地视频 / 摄像头 + `.pt` 权重 | 顶栏 **「+ 导入视频追踪」** 或直接拖放视频文件导入，锁定轻量化 N 档位（`yolo26n.pt`，亦支持浏览加载自定义 `.pt`），实时跑 `YOLO26n + ByteTrack` 并导出标准 `session.json` 与 16 列 CSV 至 `user_sessions/`，一键跳转 V1 复盘 |

---

## 项目目录结构

```text
vision-perception-desktop/
├─ main.py                     # 入口、高 DPI 适配、无控制台日志保护与 --selftest-live 自检
├─ main_window.py              # 顶部双层导航主壳、浅/深主题切换、全局快捷键与拖放导入
├─ theme.py                    # 现代浅色（默认）与深色双套 Design Token 及 QSS
├─ data_loader.py              # 只读数据扫描与契约 v1.0 解析（支持工程目录/快照目录/user_sessions）
├─ video_engine.py             # OpenCV 顺序解码 + 120 帧 LRU 缓存引擎
├─ inference_worker.py         # QThread 后台 YOLO26n + ByteTrack 实时追踪与契约导出器
├─ widgets/
│  ├─ common.py                # 通用卡片、KPI 指标卡、合规免责横幅、高清图片预览弹窗
│  ├─ video_canvas.py          # V1 原视频像素坐标系硬件叠加画布
│  ├─ timeline_bar.py          # V1 合并区间状态色带 + 脉冲刻度交互时间轴
│  ├─ playback_view.py         # V1 感知回放台
│  ├─ trajectory_view.py       # V2 轨迹视图
│  ├─ quality_view.py          # V3 画质体检
│  ├─ training_view.py         # V4 训练监控（含矢量交互曲线图）
│  ├─ compare_view.py          # V5 模型对比（含横向柱状图与三联检视）
│  └─ live_track_view.py       # V6 视频导入与实时追踪工作台
├─ VisionMonitorDesktop.spec   # PyInstaller 打包配置（含 torchvision _C_stable.pyd 修复）
├─ build_release.ps1           # Windows 绿色便携版一键打包脚本
├─ requirements.txt            # Python 依赖清单
├─ LICENSE                     # GNU AGPL-3.0 完整许可证文本
└─ THIRD_PARTY_LICENSES.md     # 第三方依赖版权与合规审计说明
```

---

## 快速开始

### 1. 安装依赖（Python 3.10–3.12）

```bash
python -m venv .venv
# Windows 激活虚拟环境
.venv\Scripts\activate

# 1) 根据你的 GPU/CUDA 版本从 https://pytorch.org 安装 PyTorch 与 TorchVision
# 2) 安装其余运行依赖
pip install -r requirements.txt
```

### 2. 准备模型权重与数据（可选）

- **实时追踪权重**：从 [Ultralytics 官方](https://github.com/ultralytics/ultralytics) 获取 `yolo26n.pt`（或你自行微调的 `.pt` 权重），放入 `weights/` 目录或在 V6 界面点击 **「浏览」** 加载。
- **只读回放数据**：通过 `--data-dir` 参数、环境变量 `VISION_DATA_DIR` 或界面右上角 **「切换目录」** 指向包含 `out/web/*.session.json`（或 `data/web/`）的目录。

### 3. 启动桌面客户端

```bash
python main.py
# 或指定数据目录
python main.py --data-dir /path/to/your/perception_data
```

### 4. 本地打包 Windows 绿色便携 EXE（可选）

```powershell
pip install pyinstaller
powershell -ExecutionPolicy Bypass -File .\build_release.ps1 -VenvPython .\.venv\Scripts\python.exe
```

> 打包完成后可在产物目录中执行 `VisionMonitorDesktop.exe --selftest-live` 验证 `torchvision::nms` 与 `YOLO + ByteTrack` 在冻结环境中的推理链路。

---

## 键盘快捷键

| 快捷键 | 功能 |
|---|---|
| `Space` | 播放 / 暂停（V1） |
| `←` / `→` | 上一帧 / 下一帧（V1） |
| `Shift + ←` / `Shift + →` | 后退 / 前进 1 秒（V1） |
| `L` | 显示 / 隐藏画面图例（V1） |
| `1` – `6` | 快速切换 V1 – V6 六个视图 |

---

## 版权、许可证与免责声明

- **开源协议**：本项目源代码依据 **GNU Affero General Public License v3.0 ([AGPL-3.0](./LICENSE))** 开源发布，以完整兼容上游 Ultralytics 的 AGPL-3.0 协议。
- **第三方版权与合规**：详见 [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md)。本仓库**不包含**任何预训练模型权重、第三方专有二进制 DLL（如 NVIDIA CUDA 运行库）以及任何包含真实人物肖像的视频/图片素材。
- **安全免责**：本软件仅用于科研、教学与算法过程可视化演示，不构成医疗或出行安全设备，**不得替代白手杖、导盲犬、专业定向行走训练或人工陪护**。
