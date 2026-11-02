# Optional nodes — separate subprocess environment

## 中文安装与使用

本仓库提供独立节点包；请选用另行准备的 ComfyUI 测试环境。以下是安装方法，
不是已在你的现有 ComfyUI 中执行过的操作。

先在本项目目录构建隔离运行环境：

```bash
bash scripts/setup_ubuntu.sh
bash scripts/build_ofx_ubuntu.sh Release
bash scripts/build_bridge.sh
```

把 `comfyui/ComfyUI-Spektrafilm` 整个目录复制到所选 ComfyUI 的
`custom_nodes/ComfyUI-Spektrafilm`。不要把原版 spektrafilm 的 numpy、Qt 或
其他依赖安装进 ComfyUI 的 Python 环境。处理过程由本项目的 `.venv` 独立运行。

启动所选 ComfyUI 前设置本项目的绝对路径：

```bash
export FILMFORGE_ROOT=/absolute/path/to/filmforge-spektrafilm
# 先用 vulkaninfo --summary 确认设备顺序，再选择自己的 GPU 编号。
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
export SPEKTRAFILM_VULKAN_DEVICE_INDEX=1
# 然后按该 ComfyUI 环境原有方式启动，不要切换到本项目的 .venv 启动宿主。
```

`1` 只是测试机器 RTX 3070 Ti 的 Vulkan 编号，不是所有机器的默认值。
节点位于 `image/spektrafilm (isolated)` 分类。

### 图片

按下面连接节点：

```text
LoadImage.IMAGE ───────────────► SpektrafilmImage.images
SpektrafilmPreset.preset_json ─► SpektrafilmImage.preset_json
SpektrafilmImage.IMAGE ────────► SaveImage.images
```

Preset 可选胶片、相纸、backend、grain、halation、diffusion、seed 与
temporal_grain_correlation。建议先选 `vulkan`、`kodak_portra_400`、
`kodak_portra_endura`，效果先设为 0，确认基础渲染后逐步增加。
`cpu-physical` 是确定性物理颜色模式，尚不接受 grain、halation、diffusion 的非零设置。

### 视频帧

把已有流程产生的 `IMAGE` 帧批次接到 `SpektrafilmVideoFrames.images`，
Preset 接 `preset_json`，显式填写 `fps` 和 `start_frame`。输出是处理后的
`IMAGE` 批次与原样返回的 `fps`，再接你所用视频保存节点。

分段处理时，`start_frame` 填该段在原视频中的绝对起始帧数；相同片段使用同一
seed 和配置。它控制 grain 索引，不会自动跳过输入视频。VHS/VideoHelperSuite
不属于本包依赖，具体宿主的视频保存接口尚未验证。

输入为有限、0–1 范围的 sRGB 浮点 IMAGE；HDR、负值和 NaN/Inf 不接受。
ComfyUI 输出裁剪到 SDR 范围；需要保留线性浮点范围时请改用独立视频 CLI 的 EXR 输出。

示例 `examples/comfyui_api_workflow.json` 是 **API prompt 格式**：需要替换
LoadImage 的文件名，并通过 ComfyUI API 的 `prompt` 字段提交；它不是能直接拖入
画布的 UI workflow 格式。此文档未声称完整 ComfyUI 宿主流程已验收。

### 常见问题

* 找不到节点：确认复制的是带 `__init__.py` 的整个节点目录，并重启所选测试宿主。
* 提示 `Set FILMFORGE_ROOT`：启动宿主的同一进程环境中必须设置上述变量。
* 共享库不存在：先完成 OFX Release 与 `build_bridge.sh` 构建。
* Vulkan 不可用：检查宿主启动环境的设备访问权限、ICD 和 GPU 编号；无需重装模型。
* profile 不可用：Python 与 OFX 的注册表不同，使用该 backend 实际支持的配置。

验证范围：模块/schema、profile 枚举、真实 GPU 子进程往返、重复结果和分段重合区
已测试；实时宿主注册、画布流程与 VHS 尚未测试。现有 ComfyUI 未被修改。

## English reference

The current existing ComfyUI was never modified, imported, restarted, or connected.
The package in ComfyUI-Spektrafilm contains three nodes. Only Python stdlib loads
at module import; NumPy and torch are used from the chosen host when processing.
No simulation, Qt, CUDA or colour dependencies are installed into the host.

For a **new disposable ComfyUI checkout** that you explicitly choose later:

1. Build this workspace with scripts/setup_ubuntu.sh, build_ofx_ubuntu.sh Release,
   and build_bridge.sh. Do not install spektrafilm into the host environment.
2. Copy this node directory into that new checkout's custom_nodes/.
3. Start that host with `FILMFORGE_ROOT=/absolute/path/to/this/workspace` and, on
   this machine, `VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json` and
   `SPEKTRAFILM_VULKAN_DEVICE_INDEX=1` to select RTX 3070 Ti.
4. Use examples/comfyui_api_workflow.json as an **API prompt**, substituting a
   valid input filename; it is not the UI canvas workflow serialization format.

SpektrafilmPreset enumerates actual runtime registries. Some profile slugs differ
between Python and OFX; CPU selections are checked against the CPU registry.
SpektrafilmImage accepts a batch; SpektrafilmVideoFrames additionally passes fps
and an absolute start_frame. The preset carries seed and temporal correlation.
Frames use bounded sRGB float IMAGE transport; alpha is straight if supplied,
and output is clipped for the ComfyUI IMAGE contract. The subprocess memory-maps
input/output batches and processes one frame at a time. No model weights enter
the subprocess. Disk/RAM requirements still scale with the host's input batch.

Tested: node module import, schema/profile enumeration, actual Vulkan subprocess
round trip, repeated output and segment overlap. Not tested: live ComfyUI host
registration, UI workflow execution or VHS. No GPU LUT node or VideoFile node is
claimed. CPU physical mode currently disables spatial and stochastic effects.
