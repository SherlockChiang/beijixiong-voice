# Beijixiong Voice

Beijixiong Voice 是一个本地 F5-TTS 语音克隆工具，通过参考音频克隆声音和情绪，生成中文语音。它提供命令行和轻量 Web GUI，支持角色/情绪管理、停顿压缩和语速/音高调整。

## Features

- 本地生成：模型权重下载完成后，生成过程在本机运行。
- 声音克隆：通过参考音频克隆音色，文件名自动识别角色和情绪。
- Web GUI：选择角色和情绪、先生成可编辑的口音 Prompt，再生成音频。
- 参考音频管理：支持 GUI 上传自定义参考音频，自动解析文件名。
- 音频管理：生成后的 WAV 保存在 `output/`，可在页面中播放、重命名、删除。
- 停顿压缩：检测生成音频中的过长静音，把短语间停顿压到可控范围。
- 夜间模式：跟随系统主题，也支持手动切换并记住选择。

## Requirements

需要 CUDA 兼容的 GPU（CPU 也可运行但速度很慢）。建议 Python 3.10 或 3.11。

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

首次运行会从 Hugging Face 下载 F5-TTS 模型权重（约 1-2 GB）。可设置缓存目录：

```powershell
$env:HF_HOME="C:\hf_cache"
```

## Reference Audio Setup

参考音频放在 `references/` 目录下，文件名格式为 `{角色}_{情绪}.{扩展名}`：

```text
references/
  luna_angry.wav
  luna_angry.txt      ← 参考文本（可选）
  luna_happy.wav
  luna_sad.wav
  kai_angry.wav
  kai_neutral.wav
```

- 推荐格式：`.wav`。Windows + PyTorch/TorchCodec 环境下，`.mp3`, `.ogg`, `.m4a` 可能依赖 FFmpeg shared DLL，容易出现 `Could not load libtorchcodec`。
- 项目已在 F5-TTS 内部把 `torchaudio.load` 替换为 `soundfile` 读取器，优先绕过 TorchCodec；因此参考音频建议先转成 WAV。
- 文件名中 `_` 前面是角色名，后面是情绪名
- 可选的 `.txt` 文件存放参考文本（与音频同名），内容是参考音频中实际说的话
- `ref_text` 必须准确匹配参考音频内容，否则会降低生成质量
- 参考音频和参考文本通常属于本地资产，默认不会提交到 Git；仓库只保留 `references/.gitkeep`

也可以通过 GUI 的"上传参考音频"面板上传，系统会自动保存为正确的文件名格式。

## Start GUI

推荐使用启动脚本：

```powershell
.\run_gui.ps1
```

也可以手动启动：

```powershell
.\.venv\Scripts\python.exe gui_server.py
```

打开 <http://127.0.0.1:7860>

## GUI Workflow

1. 选择角色和情绪。
2. 输入中文文本。
3. 点击 `生成口音 Prompt`。
4. 在 Prompt 文本框里手动调整拼写、停顿和省略号。
5. 点击 `生成音频`。

`sad`、`hurt`、`cry` 等情绪会自动应用较慢的推理语速；如果还偏快，优先调低 GUI 里的 `推理速度`，而不是 `语速/升调`。

## CLI Usage

列出可用角色和情绪：

```powershell
.\.venv\Scripts\python.exe beijixiong_voice.py --list
```

生成语音（需要指定角色和情绪）：

```powershell
.\.venv\Scripts\python.exe beijixiong_voice.py "大家好，我是北极熊。" --character luna --emotion neutral -o output/test.wav
```

生成带情绪的语音：

```powershell
.\.venv\Scripts\python.exe beijixiong_voice.py "我真的很难过。" --character luna --emotion sad -o output/sad.wav
.\.venv\Scripts\python.exe beijixiong_voice.py "太好了！" --character luna --emotion happy -o output/happy.wav
```

直接指定参考音频（跳过文件名解析）：

```powershell
.\.venv\Scripts\python.exe beijixiong_voice.py "测试" --ref-file ref.wav --ref-text "参考文本" -o output/test.wav
```

## Notes

- 参考音频质量直接影响输出质量。建议使用 5-15 秒的清晰语音。
- 如果生成内容混入参考音频里的句子，通常是参考音频过长、参考文本不匹配，或参考音频在半句话中间结束。建议剪成 6-10 秒的完整短句，并让 `.txt` 只包含这段真实内容。
- `--speed` 控制 F5-TTS 推理速度，`--speed-pitch` 是后处理的语速/音高调整。
- `最大停顿` 和 `静音阈值` 是后处理参数。
- GUI 服务绑定在 `127.0.0.1:7860`，默认只用于本机访问。
- 生成的文件默认进入 `output/`，该目录不会提交到 Git。
