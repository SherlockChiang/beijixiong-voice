# Design Notes

## Goal

Beijixiong Voice 的目标是做一个可本地运行、易试听、易调参的语音克隆工具：通过参考音频克隆声音和情绪，让 F5-TTS 生成中文语音。

重点取舍：

- 优先本地部署和稳定使用。
- 优先 GUI 可用性，避免只停留在脚本示例。
- 声音和情绪通过参考音频克隆，文件名自动识别。
- 保留后处理模块（停顿压缩、语速/音高调整）。

## Architecture

项目由三层组成：

- `beijixiong_voice.py`: 核心生成逻辑和 CLI。
- `gui_server.py`: 基于 Python 标准库的本地 HTTP 服务。
- `gui/`: 单页 Web GUI，包含 HTML、CSS、JS。

没有引入 Flask/FastAPI 这类额外 Web 框架，目的是让部署链路更短。GUI 后端直接复用 CLI 的核心函数，避免两套生成逻辑。

## Reference Audio System

参考音频放在 `references/` 目录下，通过文件名自动识别角色和情绪：

- 文件名格式：`{character}_{emotion}.{ext}`
- 支持格式：`.wav`, `.mp3`, `.flac`, `.ogg`, `.m4a`
- 可选的 `.txt` 参考文本文件与音频同名

`scan_references()` 函数扫描目录，解析文件名，返回 `{characters, map}` 结构。不需要额外的配置文件。

GUI 支持上传参考音频，通过 base64 编码传输，服务器保存为正确的文件名格式。

## Character & Emotion

角色和情绪完全由参考音频文件名决定：

- `luna_angry.wav` → 角色 `luna`，情绪 `angry`
- `luna_happy.wav` → 角色 `luna`，情绪 `happy`
- `kai_neutral.wav` → 角色 `kai`，情绪 `neutral`

GUI 中角色下拉框在上，情绪下拉框在下。切换角色时，情绪下拉框自动更新为该角色可用的情绪列表。

## Audio Pipeline

F5-TTS 输出音频后，项目会应用后处理：

1. 停顿压缩：检测并压缩过长静音。
2. 语速/音高调整：使用 `scipy.signal.resample_poly` 对音频数组做真实重采样。

这些后处理模块与 TTS backend 无关，更换 backend 时可以保留。

## GUI Behavior

GUI 提供：

- 文本输入
- 角色/情绪选择（基于文件名自动发现）
- 参考音频预览和文本显示
- 推理速度、语速/升调、停顿压缩参数
- 两步生成流程：先生成可编辑的口音 Prompt，再用手动确认后的 Prompt 生成音频
- 参考音频上传（折叠面板）
- 生成进度估算条
- 当前音频播放
- 历史音频播放、重命名、删除
- 夜间模式切换

## Known Limits

- 首次运行需要下载 F5-TTS 模型权重（约 1-2 GB）。
- GPU 推理速度较快，CPU 推理很慢。
- 参考音频质量直接影响输出质量，建议 5-15 秒清晰语音。
- `ref_text` 必须准确匹配参考音频内容。
- 参考音频可能包含授权或隐私素材，默认通过 `.gitignore` 排除，仓库只保留 `references/.gitkeep`。
- GUI 服务绑定在 `127.0.0.1:7860`，默认只用于本机访问。
