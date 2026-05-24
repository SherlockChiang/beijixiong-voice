# Beijixiong Voice

Beijixiong Voice 是一个本地 Bark TTS 小工具，用英文 speaker preset 朗读中文拼音，生成带一点“北极熊口音”的中文语音。它提供命令行和轻量 Web GUI，默认偏明亮、年轻的音色，支持生成记录播放、重命名、删除和夜间模式。

## Features

- 本地生成：模型权重下载完成后，生成过程在本机运行。
- Web GUI：输入文本、选择音色、调整稳定参数、查看生成进度。
- 音频管理：生成后的 WAV 保存在 `output/`，可在页面中播放、重命名、删除。
- 短语连读：中文会转成紧凑拼音短语，例如 `dajiahao, woshi beijixiong.`，减少逐字停顿。
- 多音色预设：使用 Bark 的 `v2/en_speaker_*` preset，并按实际听感命名。
- 情绪预设：通过非语音标签、标点节奏、温度和语速组合，让输出更接近开心、难过、委屈、紧张等状态。
- 停顿压缩：检测生成音频中的过长静音，把短语间停顿压到可控范围。
- 稳定输出：固定 seed、长文本分段、真实重采样调整语速/音高。
- 夜间模式：跟随系统主题，也支持手动切换并记住选择。

## Requirements

Bark 和 PyTorch 对 Python 版本比较挑，建议使用 Python 3.10 或 3.11。

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

首次运行 Bark 会下载模型权重。完整模型较大，下载完成后再次生成会快很多。

可选：设置 Hugging Face token 以提高下载稳定性。

```powershell
$env:HF_TOKEN="hf_xxxxxxxxxxxxxxxxx"
```

## Start GUI

推荐使用启动脚本：

```powershell
.\run_gui.ps1
```

它会优先使用 `.venv\Scripts\python.exe`，启动本地服务，并自动打开：

```text
http://127.0.0.1:7860
```

也可以手动启动：

```powershell
.\.venv\Scripts\python.exe gui_server.py
```

## CLI Usage

预览 Bark prompt：

```powershell
.\.venv\Scripts\python.exe beijixiong_voice.py "大家好，我是北极熊。今天我来读中文。" --preview
```

示例输出：

```text
Bark prompt:
dajiahao, woshi beijixiong. jintian wolai duzhongwen.
Voice: little-girl (v2/en_speaker_9)
```

生成 WAV：

```powershell
.\.venv\Scripts\python.exe beijixiong_voice.py "大家好，我是北极熊。" -o output/beijixiong.wav
```

查看音色：

```powershell
.\.venv\Scripts\python.exe beijixiong_voice.py --list-voices
```

查看情绪：

```powershell
.\.venv\Scripts\python.exe beijixiong_voice.py --list-emotions
```

生成带情绪的语音：

```powershell
.\.venv\Scripts\python.exe beijixiong_voice.py "我真的很难过。" --emotion sad -o output/sad.wav
.\.venv\Scripts\python.exe beijixiong_voice.py "太好了，我们成功了。" --emotion happy -o output/happy.wav
```

一次生成全部预设，方便试听：

```powershell
.\.venv\Scripts\python.exe beijixiong_voice.py "大家好，我是北极熊。" --voice all -o output/beijixiong.wav
```

## Voice Presets

Bark 官方的 `v2/en_speaker_*` 是数字 speaker preset，不保证与性别标签一一对应。本项目按实际听感重新命名，避免把低沉声音误标为女声。

当前预设：

- `little-girl`: 当前最接近明亮年轻音色的候选，基于 `v2/en_speaker_9`
- `soft-young`: 更柔和的年轻感候选，基于 `v2/en_speaker_4`
- `clear-young`: 更清晰偏高的候选，基于 `v2/en_speaker_3`
- `warm-low`: 偏低、温暖的声音，基于 `v2/en_speaker_8`
- `low-young`: 稍低的年轻感候选，基于 `v2/en_speaker_2`
- `narrator`: 稳定低沉旁白感，基于 `v2/en_speaker_6`

## Notes

- GUI 中生成的文件默认进入 `output/`，该目录不会提交到 Git。
- 情绪预设是对 Bark 的 prompt bias，不是严格可控的情感 TTS；建议用 GUI 多试听几次，挑最自然的一版。
- `最大停顿` 和 `静音阈值` 是后处理参数。停顿太长时降低最大停顿；剪得太狠时把最大停顿调大，或把静音阈值调低。
- `--speed-pitch` 使用 `scipy.signal.resample_poly` 对音频数据做真实重采样，并保持标准 WAV 采样率。
- Bark 不是严格可控的传统 TTS，同一个 preset 的结果仍会有随机性和风格漂移。
- 如果中文预览提示缺少 `pypinyin`，通常是 GUI 服务没有用 `.venv` 的 Python 启动。使用 `.\run_gui.ps1` 可以避免这个问题。

## Future Direction: Real Emotional TTS

当前 Bark 方案适合快速本地生成和调风格，但它不是严格的情感 TTS。下一阶段建议接入真正支持参考音频或情绪控制的本地模型：

- CosyVoice：优先候选。适合中文、多语言、zero-shot voice cloning，并且新版方向更强调韵律和情绪控制。
- F5-TTS：适合高质量 zero-shot voice cloning，可用授权参考音频克隆固定角色声线；情绪需要依赖参考音频或情绪分支。
- GPT-SoVITS：适合有固定授权声线素材时做 few-shot/zero-shot 克隆，工程生态成熟，但情绪控制通常要靠参考音频和数据质量。

如果目标是稳定的“萌萌小女孩声线”，最好准备一段授权参考音频，包含平静、开心、难过等不同情绪；模型会比纯数字 speaker preset 更容易保持角色一致。
