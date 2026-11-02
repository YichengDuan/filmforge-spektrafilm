# ComfyUI-Spektrafilm

三个节点：`SpektrafilmPreset`、`SpektrafilmImage`、`SpektrafilmVideoFrames`。
胶片模型来自 Andrea Volpato / spektrafilm 与 Aedan Diez / spektrafilm OFX；
出处与许可见仓库根目录 ACKNOWLEDGEMENTS.md、LICENSES.md。

## 在现有 ComfyUI 安装

先在本项目完成 OFX 与桥接构建。需要原生 CUDA 时再编译 CUDA 库；使用已有
CUDA Toolkit 和 C++ 编译器，GLM 只下载到工作区，不安装系统包。

```bash
bash scripts/setup_ubuntu.sh
bash scripts/build_ofx_ubuntu.sh Release
bash scripts/build_bridge.sh
bash scripts/build_cuda_spectral.sh  # 可选；本机验证 CUDA 12.0 / GCC 12 / sm_86
python3 scripts/install_comfyui.py \
  --comfy-root /path/to/ComfyUI \
  --host-python /path/to/comfy-python \
  --device YOUR_VULKAN_INDEX \
  --icd /usr/share/vulkan/icd.d/nvidia_icd.json \
  --cuda-device YOUR_NVIDIA_SMI_INDEX
```

替换路径和设备编号。CUDA 与 Vulkan 的设备编号可能不同。已有节点会备份到本项目
`.local/comfyui-backups/`，个人路径写入被 Git 忽略的 `filmforge.local.json`。
重启 ComfyUI 后在 `SpektrafilmPreset.backend` 选择后端。
安装器不更换 Python、不安装 ComfyUI 依赖、不修改启动脚本。
渲染子进程沿用所选 Python/NumPy，GPU 选择只在子进程生效。

| backend | 当前能力 | 依赖与边界 |
|---|---|---|
| `cuda-spectral` | 原生 81 波段色彩、曝光、密度 preview grain、曝光阶段 halation、camera diffusion、时域相关性 | 本项目 CUDA 库 + NumPy；渲染 GPU 运算不调用 Vulkan，不使用最终 RGB LUT；未移植 OFX 全部高级参数 |
| `vulkan` | 当前桥接同一组功能，直接运行上游 renderer | Vulkan 驱动与本项目 Vulkan 库 |
| `cuda-lut` | GPU 三线性插值的颜色近似 | 需要宿主已有 torch；grain/halation/diffusion/时域相关性必须设为 0 |
| `cpu-physical` | 原版确定性物理色彩 | 需要独立 Python 3.13 原版环境；现有宿主模式不提供 |

本机现有 Python 3.12.11 / NumPy 2.5.4 已实测原生 CUDA 图片和视频节点。
新增后端无需把原版 spektrafilm、Qt、colour 或另一个 torch 安装进 ComfyUI。
当前 CUDA 已优化 RGB 传输、共享内存卷积及相关颗粒的中间结果复用；
同卡平均耗时对比与实际视频测试见 `docs/CUDA_OPTIMIZATION.md`。

## 图片

连接 `LoadImage → SpektrafilmImage → SaveImage`，再把
`SpektrafilmPreset.preset_json` 接到 `SpektrafilmImage.preset_json`。
选择真实胶片与相纸 profile，先用曝光 0，再逐步增加 grain、halation、diffusion。
类别为 `image/spektrafilm (isolated)`。

输入为 `[B,H,W,3或4]` 的有限 SDR 浮点 IMAGE；图片按 sRGB 解码。
alpha 为 straight alpha。输出按 sRGB 编码并裁剪到 0–1，HDR/Log 需先明确转换。
需要保留浮点动态范围时，使用独立 CLI 的线性 EXR 输出。

## 视频

运行 `python3 scripts/create_video_workflows.py` 生成可拖入画布的示例：

* `examples/Filmforge_Video_Native_CUDA.json`：原生 CUDA 色彩与空间效果。
* `examples/Filmforge_Video_Full_Vulkan.json`：上游 Vulkan。
* `examples/Filmforge_Video_Fast_CUDA_LUT.json`：仅颜色的 LUT 近似。

使用 ComfyUI 原生 LoadVideo / GetVideoComponents / CreateVideo / SaveVideo，
保留 fps 与原音轨。选择自己的视频文件，明确 `input_transfer`：普通 Rec.709 视频用
`bt709`，sRGB 视频用 `srgb`，已知线性帧用 `linear-rec709`。节点输出统一是 sRGB IMAGE。
示例默认文件名 `filmforge_demo_10s.mp4` 只是测试素材名，公共仓库不包含视频。

`SpektrafilmVideoFrames` 也可接已有的 IMAGE 帧批次。分段处理时设置原片绝对
`start_frame`；相同 seed、profile、参数与帧索引可重现。时域相关性是线性残差混合，
不是上游原生 AR(1) 模型。该节点逐帧渲染，但输入批次仍占宿主 RAM；长片使用流式 CLI。
VHS 是可选的外部节点包，本项目不依赖它，尚未验证 VHS 专用接口。

本机已通过原生 CUDA 的 320×180、250 帧、25fps、带音轨 MP4 流程；
原生 CUDA 的 720p/1080p 250 帧独立 CLI 验证见 `benchmarks/ubuntu_results.md`。
API 自动执行已验收；手动操作画布未验收。

## 独立原版环境

需要 CPU physical 时，可将本节点目录复制到另一个 ComfyUI 的 `custom_nodes/`，
启动前设置 `FILMFORGE_ROOT=/absolute/path/to/filmforge-spektrafilm`。
不配置 `python_executable` 时，worker 使用本项目 `bin/filmforge-video` 和 `.venv`。
ComfyUI 主进程仍按它原有的方式启动。

## 故障排查

* 没有 CUDA 选项：先编译 CUDA 库，再带 `--cuda-device` 重新运行安装器，重启宿主。
* 找不到共享库：完成相应构建脚本；原生 CUDA 首先需要 OFX 生成的光谱数据。
* invalid device ordinal：重新核对子进程可见 GPU 与 `--cuda-device`。
* 显存不足：缩小分辨率/批次或使用空闲 GPU；没有自动降低效果质量。
* profile 不可用：从当前后端的注册表重新选择；原版 Python 与 OFX 名称并不完全相同。

English: native CUDA now covers the controls exposed by these three nodes. It is
not a port of every OFX control or a CUDA OFX plugin. Rendering uses a subprocess,
existing host Python/NumPy, and the locally built native library. No host packages,
model weights, or global GPU settings are changed. See docs/CUDA_BACKEND.md.
