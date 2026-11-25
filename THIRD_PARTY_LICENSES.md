# 第三方组件许可证与版权合规说明（Third-Party Licenses & Notices）

本项目（**vision-perception-desktop**）自身源码采用 **GNU Affero General Public License v3.0 (AGPL-3.0)** 开源发布（完整原文见仓库根目录 [LICENSE](./LICENSE)）。

采用 **AGPL-3.0** 的直接依据是：本项目在实时检测与 ByteTrack 追踪模块（`inference_worker.py`）中直接集成了 **Ultralytics** 库（其开源许可证为 AGPL-3.0）。为严格履行上游强 Copyleft 许可证义务、避免开源合规争议，本项目同步以 AGPL-3.0 协议开放全部源代码。

---

## 一、核心第三方依赖许可证矩阵

| 组件 | 测试版本 | 许可证 | 与 AGPL-3.0 兼容性 | 说明与上游项目 |
|---|---|---|---|---|
| **Ultralytics** | 8.4.x | **AGPL-3.0** | 同协议（触发 AGPL-3.0） | 目标检测与 ByteTrack 跟踪框架 ([github.com/ultralytics/ultralytics](https://github.com/ultralytics/ultralytics)) |
| **PySide6 (Qt for Python)** | 6.12.x | **LGPL-3.0-only** / GPL-2.0 / GPL-3.0 | 兼容（动态链接） | 原生桌面 GUI 与多媒体框架，版权归 The Qt Company Ltd. 所有 ([qt.io](https://www.qt.io/)) |
| **PyTorch** | 2.14.x | **BSD-3-Clause** | 兼容 | 深度学习张量与推理框架 ([pytorch.org](https://pytorch.org/)) |
| **TorchVision** | 0.29.x | **BSD-3-Clause** | 兼容 | 视觉算子（含 `torchvision::nms`）([github.com/pytorch/vision](https://github.com/pytorch/vision)) |
| **OpenCV (`opencv-python`)** | 5.1.x | **Apache-2.0** | 兼容 | 视频解码与图像处理 ([opencv.org](https://opencv.org/)) |
| **NumPy** | 2.5.x | **BSD-3-Clause** | 兼容 | 数值数组计算 ([numpy.org](https://numpy.org/)) |
| **SciPy** | 1.18.x | **BSD-3-Clause** | 兼容 | 科学计算与跟踪匹配依赖 ([scipy.org](https://scipy.org/)) |
| **lap** | 0.5.x | **BSD-2-Clause** | 兼容 | ByteTrack 线性指派求解器 |
| **PyInstaller**（仅本地构建） | 6.22.x | **GPL-2.0-or-later WITH Bootloader-exception** | 兼容（构建工具） | 仅用于本地打包桌面分发包，不限制应用自身许可证 |

---

## 二、版权、隐私与再分发合规边界（已在本仓库强制执行）

1. **不含预训练权重文件（`.pt`）**  
   本仓库不包含 Ultralytics 预训练权重文件（如 `yolo26n.pt`）。使用者请自行通过 Ultralytics 官方渠道下载权重或加载自行训练的 `.pt` 权重，并遵守对应权重的使用条款。

2. **不含第三方专有二进制运行库（如 NVIDIA CUDA DLL）**  
   本仓库仅托管纯文本源代码，不提交 PyInstaller 生成的 `release/` 二进制包。若使用者自行使用 `build_release.ps1` 构建包含 PyTorch CUDA（`cudart64_*.dll`、`nvjpeg64_*.dll` 等）的离线发行包并对外再分发，请自行核查并遵守 **NVIDIA CUDA Toolkit End User License Agreement (EULA)** 及 Qt LGPL-3.0 再分发义务（如提供对应完整源代码与可替换动态库声明）。

3. **不含实拍路人视频与未授权肖像素材**  
   为保护自然人肖像权与个人隐私，本仓库严禁提交任何未经书面肖像授权的户外/校园实拍视频（`.mp4`）、抽样截图（`.png` / `.jpg`）或个人项目申报材料。使用者请在本地指定自己的测试视频与符合数据契约的 JSON 文件。

4. **安全与工程边界免责声明**  
   本软件仅用于视觉感知、轨迹回放与科研教学演示：
   - 未经相机地面标定时，所有坐标均为像素坐标（`px`），**不代表物理距离**；
   - `S0 / S1 / S2` 与 `alert` 仅为基于框底边占比的演示规则，**不构成碰撞风险预测引擎**；
   - 本软件**不可替代白手杖、导盲犬、专业定向行走训练或人工陪护，不作任何避障或防碰撞安全承诺**。
