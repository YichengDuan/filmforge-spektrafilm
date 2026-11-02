# Filmforge Spektrafilm：Ubuntu Vulkan / CUDA 视频 CLI 与 ComfyUI 节点

这里已完成实际下载、构建、图片模拟和视频渲染。胶片算法来自
[Andrea Volpato / spektrafilm](https://github.com/andreavolpato/spektrafilm)，
GPU 渲染器来自 [Aedan Diez / spektrafilm OFX](https://github.com/chaert-s/spektrafilm-ofx)。
本项目添加参数、媒体、C ABI、子进程桥接，以及沿用上游公式与资料的原生 CUDA 移植。
这是个人集成项目，并非上述上游项目的官方版本。完整来源、参考实现与贡献边界见
[ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)，许可见 [LICENSES.md](LICENSES.md)。

构建环境、缓存、测试素材和插件 staging 位于项目目录；未安装系统软件包、升级
驱动或写入系统 OFX 目录。经用户指定，可把节点安装到现有 ComfyUI，并直接使用
其原有 Python/NumPy 运行 Vulkan/CUDA 子进程，不修改宿主 Python 或安装依赖。

原生 `cuda-spectral` 已覆盖当前节点的光谱色彩、preview grain、曝光阶段 halation、
camera diffusion 和可复现时域参数。它不使用最终 RGB LUT，也不代表 OFX 全部高级
功能已移植。160 组 profile、100 帧复现、720p/1080p 250 帧视频和 ComfyUI API 已实测；
本轮继续优化 RGB 传输、空间卷积和时域中间结果复用。见
[CUDA 使用](docs/CUDA_BACKEND.md) 与 [同卡耗时对比](docs/CUDA_OPTIMIZATION.md)。

A2000 的每项 100 轮平均对比中，12 组配置均快于当前 Vulkan 接口；全效果
720p/1080p 分别约 1.43×/1.49×（Portra/Endura）。完整 250 帧 MP4 命令耗时
分别减少约 24%/23%。计时范围、标准差、背景负载和数值一致性均在对比文档中明确列出。

## 从源码安装

当前验证平台为 Ubuntu 24.04 x86_64，需要可用的 NVIDIA Vulkan 驱动、git、
C++17 编译器、CMake ≥3.24、Python 和 uv。下列脚本只下载/解包到项目目录，
不安装系统软件包，也不会安装节点到已有 ComfyUI。

```bash
bash scripts/setup_ubuntu.sh
bash scripts/build_ofx_ubuntu.sh Release
bash scripts/build_bridge.sh
# 可选：使用本机已存在的 CUDA Toolkit 与兼容 C++ 编译器。
bash scripts/build_cuda_spectral.sh
```

节点包在 `comfyui/ComfyUI-Spektrafilm/`。在另行准备的 ComfyUI 环境中部署方法见
[节点安装说明](comfyui/README.md)。本仓库不携带上游克隆、二进制、生成 LUT、
模型权重、个人配置或原始环境日志；安装脚本会获取固定 SHA 的上游源码。

## 直接运行

```bash
source scripts/env.sh
# 本机 Vulkan 的 1 是 RTX 3070 Ti；与 nvidia-smi 的设备编号不同。
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
export SPEKTRAFILM_VULKAN_DEVICE_INDEX=1

python scripts/test_still.py --input-space linear-rec709
filmforge-video --list-profiles
filmforge-video --help
filmforge-video --input your-input.mp4 --output examples/result.mp4 \
  --preset examples/preset.json --audio --encoder auto
# 长视频：保存线性 EXR 基线并支持续跑。
filmforge-video --input your-input.mp4 --output examples/long.mp4 \
  --preset examples/preset.json --frames-dir examples/long-frames
# 重复同命令并添加 --resume，复用已完成帧。
# 原生 CUDA（先按 nvidia-smi 确认设备编号；与 Vulkan 编号不同）。
CUDA_VISIBLE_DEVICES=1 FILMFORGE_CUDA_DEVICE=0 \
  filmforge-video --backend cuda-spectral --input your-input.mp4 \
  --output examples/cuda.mp4 --grain .35 --halation .3 --diffusion .1 --audio
```

缺少色彩传递元数据的视频必须明确给出 `--input-transfer bt709` 或 `srgb`。
仅接受已经明确为 Rec.709 的 SDR 视频；请先阅读
[色彩与时间轴约定](docs/VIDEO_COLOR_PIPELINE.md)。输入场景线性 EXR 可以超过 1，
但当前 MP4/MOV 输出是 8-bit SDR；默认 CPU H.264，支持 HEVC 和按实际尺寸探测 NVENC。

## 阶段验收

| 阶段 | 状态 | 已实测结果与边界 |
|---|---|---|
| A 环境与审计 | Done | 双仓库与 SDK SHA、环境、调用链、功能矩阵、许可审计已落盘 |
| B 原版图片/LUT | Partial | runtime、16-bit TIFF、float EXR、PNG 预览、33³/65³ 官方 LUT 已运行；上游 829 通过、5 失败；Qt GUI 仅 offscreen 构造验证 |
| C OFX Linux | Partial | Release/Debug 全构建，三个 bundle，GPU float/half 拷贝成功；上游 core harness 的 pass 数断言失败；未验证 Resolve |
| D 离线视频 | Partial | Vulkan、原生 CUDA 光谱/空间效果、CPU physical 颜色；流式视频/序列、音频、EXR 续跑、分段与时序已测；未支持全部 OFX 功能 |
| E ComfyUI | Partial | 三节点本机注册，Vulkan/CUDA 图片、原生 CUDA 250 帧带音轨视频 API 已测；宿主原有 Python/NumPy；VHS/手动前端尚未验证 |
| F 性能/正确性 | Partial | 720p/1080p 各 250 帧、音视频时长、时序与色彩诊断已实测；4K 仅单帧；CPU/GPU 严格视觉等价未达成 |

GPU 桥接及节点子进程测试为 **4 passed**，OFX Python 测试 **11 passed**。
新增图片 IO/alpha 检查 **2 passed**，本地测试合计 **6 passed**。
官方 LUT QA 的插值误差已测量，但单调性与 gamut compression 检查有失败，
不能把“导出成功”理解为“所有 QA 通过”。

## 构建与测试

```bash
bash scripts/setup_ubuntu.sh          # 可重入；仅下载/解包到本目录
bash scripts/probe_ubuntu.sh
bash scripts/build_ofx_ubuntu.sh Release
bash scripts/build_ofx_ubuntu.sh Debug
bash scripts/build_bridge.sh
bash scripts/run_vulkan_tests.sh
bash scripts/run_media_tests.sh
# 首次性能实测：脚本会保护已存在结果，避免覆盖。
bash scripts/run_benchmarks.sh
```

[Ubuntu 设置说明](docs/UBUNTU_SETUP.md) · [实际性能表](benchmarks/ubuntu_results.md) ·
[阶段记录](docs/STAGE_RESULTS.md) · [已知限制](docs/KNOWN_LIMITATIONS.md) ·
[架构与功能矩阵](docs/ARCHITECTURE.md) · [LUT QA](docs/LUT_QA.md) ·
[许可审计](docs/LICENSE_AUDIT.md) · [ComfyUI 节点说明](comfyui/README.md)。

## 固定源码

* spektrafilm：`3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`
* spektrafilm-ofx：`86476afc5b077de77e2278e3658d1ba9309892a1`
* OpenFX 1.5.1：`ab779510b2655b4d11a7e01e5c521f9aa8c88976`

上游工作树保持干净；源码固定在 upstream/lock.json，
Python 版本固定在 requirements.lock，Ubuntu 包版本与校验值在 .deps/。
执行机器上的完整原始日志位于 logs/，不随仓库发布；公开的去本机路径证据见
[benchmarks/evidence](benchmarks/evidence)。本地 bundle 仅暂存到 install/OFX/Plugins/。

## 后续明确任务

1. 在独立修复分支定位上游三个快照差异与两个失效测试；不重写基线掩盖差异。
2. 修正 Vulkan harness 中落后于 renderer 的 pass 计数与 diffusion 计数规则，并保留数值校验。
3. 对齐两项目的 profile 数据、coupler、scanner、白点与显影默认值后再做严格 CPU/GPU parity。
4. 用用户真实素材完成更广泛格式、时间轴和 4K 长视频验证。
5. 继续验证高级 OFX 参数、其他显卡与更长视频；评估 GPU tensor 直通和异步传输的实际收益。

原创桥接代码按 GPL-3.0-or-later 提供；OFX 派生的原生 CUDA 文件标记 GPL-3.0-only，
完整 GPL 文本在 LICENSE，各文件与资产范围见 LICENSES.md。上游资产另有许可，
请保留作者、原始许可与致谢。生成 LUT 为本地测试资产，不作为商业 LUT 包发布。
