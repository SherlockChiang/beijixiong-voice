# Design Notes

## Goal

Beijixiong Voice 的目标不是复刻 Sora 或 Bark 本身，而是做一个可本地运行、易试听、易调参的小工具：把中文转成适合英文 TTS 朗读的拼音 prompt，让 Bark 的英文 speaker preset 读出带一点异国口音的中文效果。

重点取舍：

- 优先本地部署和稳定使用。
- 优先 GUI 可用性，避免只停留在脚本示例。
- 音色标签按实际听感命名，不把 Bark 数字 preset 误当官方性别标签。
- 默认输出尽量流畅、有活力，而不是强行鬼畜拼写。

## Architecture

项目由三层组成：

- `beijixiong_voice.py`: 核心生成逻辑和 CLI。
- `gui_server.py`: 基于 Python 标准库的本地 HTTP 服务。
- `gui/`: 单页 Web GUI，包含 HTML、CSS、JS。

没有引入 Flask/FastAPI 这类额外 Web 框架，目的是让部署链路更短。GUI 后端直接复用 CLI 的核心函数，避免两套生成逻辑。

## Text Pipeline

中文输入会经历以下步骤：

1. 标点标准化：把中文标点转换成英文标点。
2. 拼音转换：使用 `pypinyin` 转成无声调拼音。
3. 短语连读：把连续中文片段按 2 到 3 个音节分组，例如：

```text
大家好，我是北极熊。今天我来读中文。
```

转换为：

```text
dajiahao, woshi beijixiong. jintian wolai duzhongwen.
```

这样避免 `da jia hao` 这种逐音节空格造成的明显停顿，也避免整句完全粘连造成可懂度下降。

## Voice Presets

Bark 的 `v2/en_speaker_*` 只是 speaker preset 编号，不是官方性别标签。早期版本曾把 `v2/en_speaker_8` 标成 `girl`，试听后发现偏低沉，因此改成 `warm-low`。

当前策略：

- 保留少量常用候选。
- 使用中性、听感导向的名字。
- 默认使用 `little-girl`，但文档中明确它只是当前最接近的候选。

如果未来要稳定获得特定“小女孩音色”，更适合接入支持参考音频或音色克隆的模型，而不是继续依赖 Bark 的数字 preset。

## Audio Pipeline

Bark 输出音频后，项目会按音色预设应用 `speed_pitch`。

旧实现通过写入不同 WAV 采样率来变速变调，这对某些播放器不够稳。现在改为：

1. 使用 `scipy.signal.resample_poly` 对音频数组做真实重采样。
2. 保持 Bark 原始 `SAMPLE_RATE` 写出 WAV。

这样能让语速和音高更亮，同时保持标准 WAV 元数据。

## GUI Behavior

GUI 提供：

- 文本输入
- 音色选择
- seed、温度、分段、语速/升调参数
- prompt 预览
- 生成进度估算条
- 当前音频播放
- 历史音频播放、重命名、删除
- 夜间模式切换

进度条是前端估算进度，因为 Bark 生成过程没有稳定的逐阶段回调。后端返回成功后进度会直接到 100%。

## Known Limits

- 首次运行需要下载 Bark 模型权重，完整模型体积较大。
- Bark 输出仍有随机性，即使固定 seed 也不能保证完全像传统 TTS 一样稳定。
- 数字 speaker preset 不能严格控制年龄、性别或角色。
- GUI 服务绑定在 `127.0.0.1:7860`，默认只用于本机访问。
