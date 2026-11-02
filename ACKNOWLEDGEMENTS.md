# 出处、参考实现与贡献说明 / Attribution and references

本仓库是 Ubuntu 的离线视频与 ComfyUI 集成层。物理胶片模型、胶片 profile 和
Vulkan 胶片渲染核心来自下面的上游作者；本仓库不将其署名为自己的原创算法。
This is an independent integration project, not an official upstream release.
No upstream endorsement or affiliation is implied.

## 直接复用的项目

| 作者 / 项目 | 本仓库如何使用 | 固定来源与许可 |
|---|---|---|
| Andrea Volpato — **spektrafilm** | 调用 Python runtime 做光谱曝光、负片/印片/扫描；使用官方 profile 注册表及官方 LUT CLI；以原版测试作为参考 | [repository](https://github.com/andreavolpato/spektrafilm), [pinned commit](https://github.com/andreavolpato/spektrafilm/tree/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc); GPLv3 source; profile/LUT CC BY-SA 4.0 notice is separate |
| Aedan Diez — **spektrafilm OFX** | 编译原样 VulkanRenderer.cpp、生成的 profile tables 和原样 GLSL shader；通过薄 C ABI 处理离线帧，沿用 halation、diffusion、density grain 与 print/scan | [repository](https://github.com/chaert-s/spektrafilm-ofx), [pinned commit](https://github.com/chaert-s/spektrafilm-ofx/tree/86476afc5b077de77e2278e3658d1ba9309892a1), [website](https://spektrafilm.114c.de/); GPLv3 public source; official binaries/LUT notices have different scope |
| Academy Software Foundation / OpenFX contributors — **OpenFX SDK** | 仅用于构建上游 OFX 插件的头文件与接口定义；独立帧桥接本身不模拟 OFX 宿主 | [repository](https://github.com/AcademySoftwareFoundation/openfx), [OFX_Release_1.5.1 commit](https://github.com/AcademySoftwareFoundation/openfx/tree/ab779510b2655b4d11a7e01e5c521f9aa8c88976); BSD 3-Clause plus embedded notices |

上游文件按 SHA 下载，不将它们的 Git 历史或数据重新包装成本仓库的源文件。
具体源码入口：

* 原版 `src/spektrafilm/runtime/{api,process,pipeline,params_builder}.py`：API、
  参数构造、光谱流水线与各阶段语义。
* 原版 `src/spektrafilm_lut_creator/`：合法的 profile 枚举、LUT 烘焙与插值 QA；
  生成的 LUT 不纳入本仓库发布。
* OFX `src/{SpektraVulkanRenderer,SpektraRenderer,SpektraParameters,SpektraProfileCurves}.h`
  与 `SpektraVulkanRenderer.cpp`：图像缓冲、参数、时间与 Vulkan renderer 接口。
* OFX `shaders/vulkan/`、`tools/generate_profile_curves.py`、
  `tools/SpektraVulkanCopyHarness.cpp`：GPU 算法、构建数据与测试参考。
* 各上游 README、CMakeLists.txt、LICENSE 和 Legal/：构建方式、版本与使用范围。

## 上游科学工作与其他依赖

OFX 的 [THIRD_PARTY_NOTICES.txt](https://github.com/chaert-s/spektrafilm-ofx/blob/86476afc5b077de77e2278e3658d1ba9309892a1/Legal/THIRD_PARTY_NOTICES.txt)
还署名 Johannes Hanika / [vkdt](https://github.com/hanatos/vkdt) 的光谱上采样方向、
Mallett and Yuksel 2019 的光谱重建工作，以及 Andrea Volpato 的研究基础。
本仓库通过上游实现使用这些工作，没有另行声称独立实现或重新验证其论文结论。

* [FFmpeg / ffprobe](https://ffmpeg.org/)：视频解码、编码、色彩矩阵/范围转换与音频复用。
* [OpenImageIO](https://github.com/AcademySoftwareFoundation/OpenImageIO)：PNG/TIFF/EXR
  IO、float 与 16-bit 输出、显式 straight alpha。
* [Colour](https://github.com/colour-science/colour)、NumPy、SciPy 和原版依赖：
  原版模拟、构建数据和 CIEDE2000 色彩诊断。
* [Vulkan](https://www.vulkan.org/) / Khronos、glslang、CMake、Ninja：GPU 与构建工具链。
* [ComfyUI](https://github.com/comfyanonymous/ComfyUI)：目标节点宿主协议；本仓库仅
  提供独立节点包，没有复制宿主、VHS 或模型权重。

每个依赖保留各自许可证，不能把本项目 GPL 声明当成所有第三方资产的再许可。

## 本仓库新增的工作

Maintainer: **YichengDuan**。开发中使用 OpenAI Codex 辅助编写与验证集成代码。

新增内容为：Ubuntu 工作区隔离脚本、固定源码/依赖版本、C ABI 包装、FFmpeg
流式媒体 CLI、显式 SDR 色彩传递、EXR 续跑、absolute frame/seed 规则、独立
ComfyUI 子进程节点、测试和本机实测文档。

`temporal_grain_correlation > 0` 是本桥接扩展：对原版 grain 渲染结果的线性残差
混合；不是上游原生时序模式，不能声称与 OFX 完全一致。严格 CPU/GPU parity、
Resolve 和实时 ComfyUI 宿主仍有未完成验证，详情见 docs/KNOWN_LIMITATIONS.md。

## 发布边界

仅发布集成源码、固定版本清单、许可、文档和经去除本机路径的测试证据。
不发布官方二进制、生成 LUT、profile 数据包、模型权重、测试视频、个人配置或
原始环境日志。需要这些构建输入时，从各自的官方上游获取，并保留原始声明。
完整许可盘点见 [docs/LICENSE_AUDIT.md](docs/LICENSE_AUDIT.md)。
