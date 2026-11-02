# CUDA 优化与 Vulkan 同卡对比

验收目标：同一 A2000、相同输入/参数/精度，优化 CUDA 的平均实际渲染耗时低于
当前 Vulkan 接口，再用 MP4 完整流程验证。没有更改上游 Vulkan 渲染器或降低效果。

## 实际改动

* **Packed RGB 传输**：RGB 输入直接传三通道，GPU 内转换到渲染器使用的 RGBA。
  输出在 GPU 打包为 RGB，减少 25% 的 RGB 场景传输字节；RGBA 输入仍保留 alpha。
  移除了 CPU RGB→RGBA 拼接和默认路径上的额外输出复制，返回数组保持独立所有权。
* **共享内存卷积**：保持 Gaussian 半径、边缘钳位、权重递推、求和顺序和除法。
  同一系数每帧只生成一次，块内像素复用输入。水平 tile 为 128×2，垂直为 16×16。
  半径超过 32 时运行原求和路径，保留完整半径；downsample 仍沿用上游规则。
  仅预计算权重的实验没有稳定收益；权重缓存用于共享内存卷积。
* **时域中间结果复用**：rho>0 的独立纹理、共享纹理和无 grain 基线共享一次曝光、
  diffusion、halation 和显影。仍执行各自的光谱扫描，并按原公式混合线性残差。
  保留 NumPy 原来的 FP32 相减、FP64 标量混合与最终 FP32 输出。

以上是调度、内存和重复计算优化，沿用 Aedan Diez / spektrafilm-ofx 的公式与资料。
没有启用 fast math、FP16 光谱计算或 LUT 近似。源码与生成器保留 GPL/作者声明。
当前也没有启用 pinned 双缓冲、CUDA Graph、跨帧异步重叠或 PyTorch tensor 直通。

## 100 轮方法

正式 GPU 为 **NVIDIA RTX A2000 Laptop 8GB**，CUDA 物理编号 1、Vulkan 编号 0。
每个配置先预热 10 帧，然后执行 100 轮，每轮每后端渲染 1 帧，并轮换后端顺序。
对比 Vulkan、保存的优化前 CUDA、优化后 CUDA。每后端/每配置取 100 个样本。
两对 profile × 两分辨率 × 三种设置，共 12 个配置、3,600 次正式渲染。

计时包含 Python 校验、主机操作、GPU 传输和渲染，排除首次 profile 准备及视频编解码。
平均 ms 是各帧耗时的算术平均，fps 为 `1000 / 平均ms`；加速比为
`Vulkan平均ms / CUDA平均ms`。原始样本、中位数、标准差和 P95 均保留。
背景显示/视频活动及另一张卡上的 ComfyUI 任务继续运行；不是独占 GPU 的硬件上限。
此前 3070 Ti 采样受到新启动的生成任务影响，已明确标记并发负载，不作为最终 A2000 验收数据。

全效果定义：preview grain=.35、halation=.3、camera diffusion=.1、exposure=0、seed=1234。
时域设置在上述全效果上增加 rho=.7；纯色彩将空间/随机效果设为 0。
输入为相同的随机线性 Rec.709 float32 RGB 图像，每轮使用相同绝对 frame index。

数值表与完整原始样本见 `benchmarks/evidence/cuda-opt-a2000-100rounds.json`，
汇总表见 `benchmarks/ubuntu_results.md`。这些平均值不与另一张显卡或历史负载的数字混算。

## A2000：100 轮平均耗时

单位 ms/帧，± 为样本标准差；每项 n=100。所有 12 组均通过平均耗时低于 Vulkan 的验收。

`kodak_portra_400` → `kodak_portra_endura`

| 分辨率 | 设置 | Vulkan 平均±SD | 旧 CUDA 平均 | 优化 CUDA 平均±SD | 加速比 |
|---|---|---:|---:|---:|---:|
| 720p | 纯色彩 | 42.22 ± 8.72 | 36.95 | 19.94 ± 4.22 | 2.12× |
| 720p | 全效果 | 52.58 ± 7.50 | 55.45 | 36.86 ± 2.83 | 1.43× |
| 720p | 全效果 + rho=.7 | 203.03 ± 34.84 | 207.53 | 44.77 ± 3.50 | 4.54× |
| 1080p | 纯色彩 | 87.54 ± 20.74 | 75.44 | 39.26 ± 5.98 | 2.23× |
| 1080p | 全效果 | 132.13 ± 17.90 | 135.16 | 88.67 ± 7.63 | 1.49× |
| 1080p | 全效果 + rho=.7 | 467.21 ± 72.52 | 476.81 | 101.14 ± 7.26 | 4.62× |

`kodak_vision3_500t` → `kodak_2383`

| 分辨率 | 设置 | Vulkan 平均±SD | 旧 CUDA 平均 | 优化 CUDA 平均±SD | 加速比 |
|---|---|---:|---:|---:|---:|
| 720p | 纯色彩 | 37.06 ± 6.76 | 32.45 | 17.33 ± 3.16 | 2.14× |
| 720p | 全效果 | 53.24 ± 6.22 | 54.86 | 37.62 ± 3.17 | 1.42× |
| 720p | 全效果 + rho=.7 | 189.49 ± 18.38 | 189.33 | 44.14 ± 3.27 | 4.29× |
| 1080p | 纯色彩 | 87.44 ± 14.36 | 74.23 | 39.35 ± 5.84 | 2.22× |
| 1080p | 全效果 | 126.30 ± 17.68 | 134.61 | 84.99 ± 6.69 | 1.49× |
| 1080p | 全效果 + rho=.7 | 495.77 ± 102.66 | 502.30 | 100.51 ± 7.66 | 4.93× |

## 完整 MP4 对比

每个后端/分辨率一次完整测试：10 秒、25fps、250 帧，Portra/Endura，全效果 rho=0，
相同 CPU libx264 与 AAC 音轨。下面是包含启动、解码、渲染、编码与收尾的墙钟总时间。

| 分辨率 | Vulkan 总秒数 | CUDA 总秒数 | CUDA 耗时减少 |
|---|---:|---:|---:|
| 720p | 43.44 | 33.22 | 23.5% |
| 1080p | 99.38 | 76.87 | 22.7% |

四个视频均为 250 帧，视频 10.000s / 音频 10.005s，BT.709 primaries/transfer/matrix、
limited range 检查通过。这里的视频总时间不是 100 段视频的平均；100 轮指上面的帧渲染对比。

## 工具检查边界

CUDA events、逐像素旧版对照、原有六项测试、160 profile 与时序回归均已执行。
本机 Compute Sanitizer 的注入未成功，不能声称通过 memcheck。最小测试仍在首次被插桩的
CUDA API 前结束，错误为 `Target application terminated before first instrumented API call`。
精确命令与 stderr 保存在本机 logs/cuda-opt-memcheck-file.log，未通过修改驱动或系统包解决。
Nsight Compute 探测未采集到 kernel 指标；本报告的 GPU 分段时间仅来自 CUDA events。

## 正确性

优化前 CUDA 库与代码在工作区 `.local/cuda-opt-baseline/` 保留，未覆盖。
专门 A/B 测试覆盖 RGB/RGBA、1×1、奇数尺寸、非连续数组、8193×1 的大半径 fallback、
720p/1080p、rho=0/.3/.7/1、不同 profile 与曝光、返回数组跨调用的独立性。
这些对照中优化前后输出逐像素精确一致。100 轮性能矩阵的各配置末帧也全部精确一致。

原有 160 组 profile、效果组合、100 帧重复/独立分段、颗粒相关性及输入错误回归已通过。
六项本地测试通过。Vulkan/CUDA 的高分辨率 grain cell 浮点边界差异仍存在，
优化未扩大为新的算法近似；见 CUDA_BACKEND.md 的原始边界。

## 复现

```bash
source scripts/env.sh
export CUDA_VISIBLE_DEVICES=1 FILMFORGE_CUDA_DEVICE=0
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
export SPEKTRAFILM_VULKAN_DEVICE_INDEX=0 SPEKTRAFILM_VULKAN_TILE_MODE=legacy
python scripts/compare_cuda_vulkan.py \
  --output benchmarks/a2000-new-100rounds.json --rounds 100 --frames 1 --warmup 10
python scripts/compare_cuda_vulkan_video.py --output-dir benchmarks/a2000-video-new
```

设备编号必须以本机枚举为准。若另外保留了旧 CUDA runtime，可用
`--baseline-dir /path/to/saved-runtime` 加入旧版对照。该目录需要 src/cuda_spectral.py、
build/cuda-spectral/libfilmforge_cuda_spectral.so 和 build/ofx-Release 的光谱资源。
公开仓库不分发该旧二进制；不传参数也能比较当前 CUDA 与 Vulkan。

`FILMFORGE_CUDA_BLUR=reference|cached|tiled` 可选逐像素原递推、缓存权重或共享内存路径，
默认 tiled，用于局部 A/B 诊断。正常使用无需设置。后端与现有三个节点名字保持一致。
ComfyUI 每个任务启动渲染子进程，会读取当前库；现有 Python 和包不需要变更。

原理参考：[NVIDIA CUDA 内存优化](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/contents.html)。
最终收益采用本机实测，不从通用优化建议推算。
