# 原生 CUDA 后端

2026-11-02，本机 Ubuntu 实际构建与验证。`cuda-spectral` 已覆盖当前 Filmforge
CLI 和三个 ComfyUI 节点公开的胶片处理功能。它不等于 OFX 全部功能的 CUDA 移植，
也没有生成 CUDA 版 OFX 插件。

后续已完成 packed RGB、共享内存卷积和时域复用优化。
当前性能以 [A2000 100 轮平均耗时对比](CUDA_OPTIMIZATION.md) 为准；下方保留初版记录。

| 处理部分 | 原生 CUDA 状态 |
|---|---|
| Hanatos 光谱重建、曝光、胶片曲线 | 已运行，与上游同一组生成数据 |
| 81 波段印片曝光、相纸曲线、81 波段扫描、线性 Rec.709 | 已运行；未使用最终 RGB 3D LUT |
| Preview density grain、seed、绝对 frame index | 已运行；位于胶片密度阶段 |
| Halation scatter 与 bounce | 已运行；位于曝光后、显影前 |
| Camera diffusion | 已运行；上游 Black Pro Mist 默认族、相同 sigma clustering/downsampling 与两分量分组 |
| temporal_grain_correlation | 已运行；与 Vulkan 桥接相同的线性 grain 残差混合扩展 |
| Straight alpha、流式媒体、EXR 续跑、音轨和 SDR 编码 | 使用现有媒体层；CUDA 渲染测试通过 |
| Production/synthesis grain、DIR 调节、print diffusion、scanner 调节、其他色域/HDR | 未接入此 CUDA 后端；不属于当前节点公开功能 |
| PyTorch GPU tensor 直接互操作、CUDA Graph、pinned 双缓冲 | 未实现；仍通过 NumPy/主机内存传输 |

## 构建与使用

先构建上游 OFX Release 和 Vulkan 桥接，生成光谱资料。
本机使用已存在的 `/usr/bin/nvcc` 12.0.140、GCC 12、CMake 3.28.3，目标 sm_86；
没有安装系统包、更换 Python 或升级驱动。CUDA toolkit 不是安装脚本自动下载的依赖。

```bash
bash scripts/build_ofx_ubuntu.sh Release
bash scripts/build_bridge.sh
bash scripts/build_cuda_spectral.sh
source scripts/env.sh
# 替换为 nvidia-smi 中的 CUDA 物理编号。测试时 1 为 A2000。
export CUDA_VISIBLE_DEVICES=1
export FILMFORGE_CUDA_DEVICE=0
filmforge-video --backend cuda-spectral --list-profiles
filmforge-video --backend cuda-spectral \
  --input input.mp4 --output examples/cuda-output.mp4 \
  --film kodak_portra_400 --print kodak_portra_endura \
  --grain 0.35 --halation 0.3 --diffusion 0.1 --seed 1234 --audio
```

生成库：`build/cuda-spectral/libfilmforge_cuda_spectral.so`。
渲染过程中不创建 Vulkan device、不调用 Vulkan renderer；CPU 资料准备直接复用上游
VulkanRenderer.cpp 中的公开源码辅助函数。因此当前构建/链接仍需要 Vulkan headers/loader，
运行 native CUDA 不需要可用的 Vulkan ICD。两个 Python 后端共享媒体/色彩传递约定。

GLM 1.0.1 从官方仓库下载到 `.deps/glm`，固定 SHA
`0af55ccecd98d4e5a8d1fad7de25ba429d60e863`。生成脚本把上游三个 GLSL shader 的
buffer、vector、入口语法转换为 CUDA C++，保留算术和操作分支，并写入原文件 SHA256。
可写 RGB swizzle 被显式展开，避免 GLM 的 CUDA swizzle 返回临时值导致丢失写入。
生成文件位于 build/，不发布上游 profile 数据。GLM 采用其 MIT 许可，完整声明随构建保留。

光谱/卷积使用 FP32；时域残差保留原 NumPy 的 FP32 相减/FP64 混合规则。
未启用 fast math，并显式关闭 FMA 收缩。跨 API 数值与颗粒 hash 仍可能在边界
不同，不能承诺 Vulkan/CUDA 位级一致。数学函数精度和 FMA 语义参考
[NVIDIA CUDA 浮点说明](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/mathematical-functions.html)。

## 实测验证

测试 GPU 为 **RTX A2000 Laptop 8GB**；3070 Ti 正有其他用户 GPU 工作，未占用或中断它。
整个工作站有并发 GPU 任务，以下数据只描述本次运行，不是无竞争环境下的硬件上限。

* 20 胶片 × 8 相纸，160 组有限、黑场、中灰、高光色块对照全部通过；
  测试块上的最大绝对差 `1.073e-6`，alpha 精确保留。
* Halation、diffusion、grain 单独/组合、rho=.7：257×513 强边缘/HDR 输入测试，
  CUDA/Vulkan RMSE 约 `1.4e-7` 至 `1.7e-7`。
* 更高分辨率随机细节图开启全部效果后，720p RMSE `1.860e-4`、最大差 `0.02674`；
  1080p RMSE `3.700e-4`、最大差 `0.04631`。高分辨率的部分 grain cell hash 在
  浮点边界不同：超过 `1e-4` 的通道占比分别约 0.250%/0.608%。
  这些纹理差异没有被当成颜色算法的位级等价。
* 同一配置 100 帧重复、独立分段均精确相同；颗粒方差 `1.9995e-7`，
  相邻相关性 `.00125`；rho=.7 实测 `.69822`。
* NaN、负输入、错误 profile、rho、frame index 被明确拒绝；无效 CUDA device
  报 `invalid device ordinal`。后端不会悄悄退回 LUT 或降低效果。
* 原生 CUDA 720p/1080p 各 250 帧 MP4→MP4、AAC 音轨、FFprobe Rec.709/limited
  标记验收通过；视频 10.000s，音频 10.005s。
* ComfyUI 原有 Python/NumPy：本机三个图片输出成功；独立测试宿主 320×180、
  250 帧、25fps 带音轨工作流成功，音视频均 10.000s；输出为 sRGB 标记。
  所有原有宿主节点仍在注册表中。未做手动画布操作验收。

## 性能边界

同一 A2000、相同输入与配置，每个设置/后端预热 2 帧后正式采样 12 帧。
下面是每帧中位数；计时包含 NumPy/主机传输，排除视频编解码。
Vulkan 明确选 legacy full-frame；CUDA 也处理整帧。

| 分辨率 | 效果 | Vulkan 中位 ms | CUDA 中位 ms |
|---|---|---:|---:|
| 720p | 仅光谱色彩 | 27.483 | 24.977 |
| 1080p | 仅光谱色彩 | 61.207 | 54.200 |
| 720p | grain .35 / halation .3 / diffusion .1 | 39.672 | 48.242 |
| 1080p | 同上 | 90.512 | 109.282 |

上表保留初版逐分量 CUDA 的结果。随后按上游默认值加入两分量分组，复测如下：

| 分辨率 | Vulkan 中位 ms | 分组 CUDA 中位 ms | CUDA GPU 总 ms | diffusion GPU ms | halation GPU ms |
|---|---:|---:|---:|---:|---:|
| 720p | 39.619 | 42.871 | 20.809 | 10.253 | 6.775 |
| 1080p | 89.931 | 95.928 | 48.087 | 22.088 | 18.453 |

这次 CUDA 总耗时比 Vulkan 高约 8.2%/6.7%，而初版约为 21.6%/20.7%。
GPU 时间使用显式开启的 CUDA events，只计 GPU 阶段；总耗时包含 NumPy 验证、复制、
CPU 参数准备和 GPU 传输。两者之差不能全部算作 PCIe 传输。diffusion+halation 占
这次 CUDA GPU 时间约 82%/84%。每帧 diffusion 派发为 28/30 次，包含 clear/resolve。
该次采样尚未使用后续的共享内存卷积；GPU tensor 直通目前仍未实现。
不能据此承诺最终加速倍数，不同 GPU/日期/精度的历史数据不混算加速比。

初版含 CPU H.264 编码与音轨的完整 CUDA CLI 实测：720p `7.373 fps` / `33.910s`，
1080p `3.336 fps` / `74.939s`，各处理 250 帧。本轮没有采样完整进程树 RSS 或显存峰值，
不将以前 Vulkan 的内存数据套用到 CUDA。

复现命令：

```bash
source scripts/env.sh
export CUDA_VISIBLE_DEVICES=1 FILMFORGE_CUDA_DEVICE=0
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
export SPEKTRAFILM_VULKAN_DEVICE_INDEX=0 SPEKTRAFILM_VULKAN_TILE_MODE=legacy
python scripts/validate_cuda_backend.py --output benchmarks/cuda-native-validation-new.json
python scripts/profile_cuda_backend.py --output benchmarks/cuda-native-profile-new.json
python scripts/benchmark_cuda_native_video.py
python scripts/test_video_workflows.py --workflow Filmforge_Video_Native_CUDA
```

视频测试保护已存在输出；复跑前保留旧结果并选择新的输出名称或手动归档。
原始本机日志不公开；去除本机路径后的数值证据在 benchmarks/evidence/。
