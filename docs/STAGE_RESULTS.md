# 执行记录（2026-11-01 晚，本机时间）

## A — Done

执行 scripts/probe_ubuntu.sh：Ubuntu 24.04.4、内核 7.0.0-38、驱动 615.71.09、
RTX 3070 Ti 8GB 与 RTX A2000 Laptop 8GB。物理内存 free 显示 46GiB（约 48GB），
初始工作分区可用 43GB。DISPLAY=:0。设备在初始沙箱内被隐藏，主机检测正常。
两个项目完整 clone，OpenFX SDK tag OFX_Release_1.5.1 clone，SHA 记录在 lock.json。
阅读 README、CMake、runtime/API/GUI/LUT、renderer、shader、harness 与完整许可。
架构和功能矩阵见 ARCHITECTURE.md；许可见 LICENSE_AUDIT.md。

没有修改系统或现有 ComfyUI。已有 ComfyUI 的路径仅在最初 nvidia-smi 输出中被动出现，
未对其执行安装、写入、导入、重启或 API 调用。未发现标准路径的 Resolve。

## B — Partial

Python 3.13.7 与完整官方 [dev] 依赖安装到本地 .venv，版本全部 freeze。
scripts/test_still.py 合成 scene-linear HDR 灰阶及色块，保存 TIFF16 / EXR float 和
sRGB PNG。runtime 实际模拟通过；16,384 像素样例首次记录处理 0.5537 秒。
Qt/napari 原版 GUI 在 offscreen 下实际构造成功；不是桌面 OpenGL 验收。
最终本地图片 IO 检查验证 PNG 的 straight alpha RGB 读写与 TIFF16 输出，以及负值
拒绝。发现 OpenImageIO 默认关联 alpha 会改变 RGB，已在桥接的 ImageSpec 中显式
设置 oiio:UnassociatedAlpha；该修复后的本地测试合计 6 passed。

`python -m pytest upstream/spektrafilm/tests -q`：829 passed / 5 failed。
失败精确日志 logs/python-full-tests.log；未替换 baseline。
33³、65³ 官方 LUT 构建均成功，QA 都有 2 项 fail，详见 LUT_QA.md。

## C — Partial

系统依赖只下载 .deb 并解包到 .deps/root；未运行 sudo 或 apt install。
`bash scripts/build_ofx_ubuntu.sh Release` 和 Debug 都完成 27 个构建步骤，
shader 编译、数据生成及三个 .ofx.bundle 成功；原始完整日志保留。
`bash scripts/install_ofx_ubuntu.sh --dry-run` 与 workspace staging 均执行成功。
实际路径 install/OFX/Plugins/{spektrafilm,spektrafilm_flow,spektrafilm_dev}.ofx.bundle。

Release/Debug VulkanCopyHarness 的 float16/float32 拷贝通过。print-scan、halation、
diffusion、DIR、scanner、preview/production grain 测试在 pass 数断言失败。
错误例：`Expected 3 core bootstrap passes, saw 4.`；diffusion 的计数差异更大。
renderer 的 print-scan 已计入额外 pass，而 harness 的固定公式未同步。
未把这些失败报告为通过，也未删除或弱化上游断言。
OFX 自带 Python SDR transfer tests 为 11 passed。

对照官网：当前网站称 Linux beta 0.3.12、四个 flavor；本源码 CMake Linux 0.1.9，
只生成 main/flow/dev。官网包未下载或执行；官方二进制资源许可证不同，不能借包补齐源码。
Resolve 宿主验证未做，也没有安装宿主。

## D — Partial（可运行 MVP）

新增 src/vulkan_bridge.cpp + 根 CMakeLists，直接编译上游 VulkanRenderer.cpp 与
生成 profile tables 为共享库。Python ctypes 提供帧接口；算法与 shader 保持上游原样。
`bin/filmforge-video --help`、真实 profile 枚举、preset JSON、dry-run、进度、错误码、
输出配置/性能 JSON 已实现。支持媒体与均匀尺寸图像目录、单图片输出 float EXR、
H.264/H.265、可选 AAC 音轨、NVENC 运行探测/CPU fallback、EXR 基线与续跑。
backend cpu-physical 复用原版确定性颜色；不声称 CPU 时空 grain 已实现。

实际时序测试：相同 100 帧重复处理逐值相同；独立 absolute start_frame 与全片重合段
逐值相同。真实 EXR → MP4、断点续跑、分段 EXR 对齐、配置变化拒绝、缺失文件与
无效 Vulkan 设备错误、CPU 短视频、HEVC fallback 均已验证。
关键记录 benchmarks/{temporal,media-verification}.json 和 logs/media-tests.log。
实际用户拍摄素材尚未提供；已处理合法的运动测试 MP4，不能代称真实摄影素材验收。
额外 720p 短片实际以 hevc_nvenc 输出成功。NVENC 探测已改为实际目标尺寸；过小的
64×48 HEVC 输入无法使用硬件编码时，auto 正确退回 libx265。

## E — Partial

独立 comfyui/ComfyUI-Spektrafilm 包包含 SpektrafilmPreset、SpektrafilmImage、
SpektrafilmVideoFrames。模块加载、输入 schema、profile 枚举、Vulkan 独立进程往返、
重复结果和分段一致性已测试；桥接测试合计 4 passed。
没有把节点安装进现有 ComfyUI，没有导入其 torch/插件，没有拷贝模型权重。
未验证实时宿主注册/UI/VHS；API prompt 示例不是已执行的 UI 工作流。

## F — Partial

720p/1080p 各 10 秒、25fps、250 帧实际视频渲染完成；同时启用 grain=.35、
halation=.3、diffusion=.1。FFprobe 检查输出色彩标记和 AAC/视频时长，误差不超过一帧。
每设备 VRAM 与 Python RSS 采样保留，实测表 benchmarks/ubuntu_results.md。
4K 只做单帧烟测，不推算持续播放能力。

色彩比较记录 benchmarks/quality.json：两实现默认物理参数/数据尚未完全对齐，
因此 RMSE/PSNR/DeltaE 是诊断，不是视觉等价验收；不能声称 GPU 与 Python 完全相同。
完整上游和本地错误/限制见 KNOWN_LIMITATIONS.md。下一步为上游回归定位、harness
计数修正、精确参数对齐，以及在另行指定的全新宿主上完成最终集成验证。
