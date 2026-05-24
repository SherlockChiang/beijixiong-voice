from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

DEFAULT_SPEED_PITCH = 1.0
DEFAULT_MAX_PAUSE_MS = 0
DEFAULT_SILENCE_THRESHOLD_DB = -42.0
DEFAULT_MIN_SILENCE_MS = 240
DEFAULT_SPEED = 1.0
DEFAULT_DEVICE = "cuda"
DEFAULT_OUTPUT = Path("output/beijixiong_voice.wav")

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CKPT_FILE = PROJECT_ROOT / "model_1250000.safetensors"
DEFAULT_VOCODER_PATH = PROJECT_ROOT / "vocos-mel-24khz"
DEFAULT_WHISPER_PATH = PROJECT_ROOT / "whisper-large-v3-turbo"

AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}

EMOTION_SPEED_FACTORS = {
    "sad": 0.70,
    "hurt": 0.82,
    "cry": 0.70,
    "soft": 0.92,
}

# ── Pinyin accent pipeline ──────────────────────────────────────────────────

CJK_RE = re.compile(r"[㐀-鿿]")
TOKEN_RE = re.compile(r"\[[^\]]+\]|[A-Za-z0-9_:-]+|[,.!?;:]+|\S")
TEXT_RUN_RE = re.compile(r"[㐀-鿿]+|[^㐀-鿿]+")

PUNCT_TRANSLATION = str.maketrans(
    {
        "。": ".",
        "，": ",",
        "！": "!",
        "？": "?",
        "、": ",",
        "；": ";",
        "：": ":",
        "—": ",",
        "…": "...",
    }
)


def _lazy_pinyin(text: str) -> list[str]:
    from pypinyin import Style, lazy_pinyin
    return lazy_pinyin(
        text,
        style=Style.NORMAL,
        neutral_tone_with_five=False,
        errors=lambda value: list(value),
    )


def _group_pinyin(parts: list[str]) -> str:
    parts = [p for p in parts if p.strip()]
    if len(parts) <= 3:
        return "".join(parts)
    groups: list[str] = []
    index = 0
    while index < len(parts):
        remaining = len(parts) - index
        size = remaining if remaining <= 3 else 2
        groups.append("".join(parts[index : index + size]))
        index += size
    return " ".join(groups)


def _romanize_chinese(text: str) -> str:
    normalized = text.translate(PUNCT_TRANSLATION)
    output: list[str] = []
    for run in TEXT_RUN_RE.findall(normalized):
        if CJK_RE.search(run):
            output.append(_group_pinyin(_lazy_pinyin(run)))
        else:
            output.append(run)
    return "".join(output)


def _soften_final(word: str) -> str:
    for old, new in (
        ("iang", "ee-ahng"), ("iong", "ee-ong"), ("uang", "oo-ahng"),
        ("ang", "ahng"), ("eng", "ung"), ("ong", "awng"),
        ("ian", "ee-en"), ("iao", "ee-aow"), ("uan", "oo-en"),
        ("ai", "eye"), ("ei", "ay"), ("ao", "aow"), ("ou", "oh"),
        ("uo", "woh"), ("ui", "way"), ("iu", "yo"),
    ):
        if old in word:
            word = word.replace(old, new)
    return word


def _reshape_initial(word: str) -> str:
    for old, new in (("x", "sh"), ("q", "ch"), ("zh", "j"), ("c", "ts"), ("r", "rr")):
        if word.startswith(old):
            return new + word[len(old):]
    return word


def _stretch_vowel(word: str) -> str:
    for vowel in ("a", "o", "e"):
        idx = word.rfind(vowel)
        if idx != -1:
            return word[:idx] + vowel * 3 + word[idx + 1:]
    return word


def _accent_word(token: str, level: int, word_index: int) -> str:
    word = token.lower()
    word = word.replace("u:", "yu").replace("ü", "yu")
    word = re.sub(r"[1-5]$", "", word)
    word = _reshape_initial(word)
    word = _soften_final(word)
    if level >= 3 and word_index % 5 == 0:
        word = word.capitalize()
    if level >= 4 and word_index % 7 == 3:
        word = _stretch_vowel(word)
    return word


def _join_tokens(tokens: list[str]) -> str:
    output: list[str] = []
    no_space = {".", ",", "!", "?", ";", ":", "..."}
    for token in tokens:
        if not output:
            output.append(token)
        elif token in no_space:
            output[-1] = output[-1].rstrip() + token
        elif output[-1].endswith("["):
            output.append(token)
        else:
            output.append(" " + token)
    return "".join(output).strip()


def accent_chinese(text: str, intensity: int = 2) -> str:
    """Convert Chinese text to English-accented pinyin for F5-TTS.

    intensity: 1=soft, 2=balanced, 3=strong, 4=chaos
    """
    source = _romanize_chinese(text)
    tokens = TOKEN_RE.findall(source)
    accented: list[str] = []
    word_index = 0
    for token in tokens:
        if token.startswith("[") and token.endswith("]"):
            accented.append(token)
        elif re.fullmatch(r"[A-Za-z0-9_:-]+", token):
            accented.append(_accent_word(token, intensity, word_index))
            word_index += 1
        else:
            accented.append(token)
    return _join_tokens(accented)


def emotion_speed_factor(emotion: str) -> float:
    key = emotion.lower().strip()
    return EMOTION_SPEED_FACTORS.get(key, 1.0)


def shape_emotion_text(text: str, emotion: str) -> str:
    key = emotion.lower().strip()
    if key not in {"sad", "hurt", "cry"}:
        return text

    shaped = text.strip()
    shaped = re.sub(r"[。.!！]\s*", "... ", shaped)
    shaped = re.sub(r"[，,、]\s*", ", ", shaped)
    shaped = re.sub(r"\s+", " ", shaped).strip()
    return shaped


def prepare_generation_text(
    text: str,
    *,
    emotion: str = "",
    accent: bool = False,
    accent_intensity: int = 2,
) -> str:
    final_text = shape_emotion_text(text, emotion)
    if accent:
        final_text = accent_chinese(final_text, intensity=accent_intensity)
    return final_text


def scan_references(refs_dir: Path) -> dict:
    """Scan references/ for {character}_{emotion} audio files.

    Returns:
        {
            "characters": ["luna", "kai", ...],
            "map": {
                "luna": {
                    "angry": {
                        "file": "references/luna_angry.mp3",
                        "ref_text": "...",
                    },
                    ...
                },
            },
        }
    """
    refs_dir = Path(refs_dir).resolve()
    if not refs_dir.is_dir():
        return {"characters": [], "map": {}}

    char_map: dict[str, dict] = {}
    for f in sorted(refs_dir.iterdir()):
        if f.is_dir() or f.suffix.lower() not in AUDIO_EXTS:
            continue
        stem = f.stem
        if "_" not in stem:
            continue
        char, emotion = stem.split("_", 1)
        if not char or not emotion:
            continue

        ref_text = ""
        txt_path = f.with_suffix(".txt")
        if txt_path.is_file():
            ref_text = txt_path.read_text(encoding="utf-8").strip()

        char_map.setdefault(char, {})[emotion] = {
            "file": str(f),
            "ref_text": ref_text,
        }

    characters = sorted(char_map.keys())
    return {"characters": characters, "map": char_map}


def resolve_reference(
    refs_dir: Path, character: str, emotion: str
) -> tuple[str, str]:
    data = scan_references(refs_dir)
    char_data = data["map"].get(character)
    if not char_data:
        available = ", ".join(data["characters"]) or "(none)"
        raise RuntimeError(
            f"Character {character!r} not found in {refs_dir}. "
            f"Available: {available}"
        )
    entry = char_data.get(emotion)
    if not entry:
        available = ", ".join(sorted(char_data.keys())) or "(none)"
        raise RuntimeError(
            f"Emotion {emotion!r} not found for character {character!r}. "
            f"Available: {available}"
        )
    return entry["file"], entry["ref_text"]


def apply_speed_pitch(audio_array, factor: float):
    if factor <= 0:
        raise RuntimeError("--speed-pitch must be greater than 0.")
    if math.isclose(factor, 1.0, rel_tol=1e-3, abs_tol=1e-3):
        return audio_array

    try:
        from scipy.signal import resample_poly
    except ImportError as exc:
        raise RuntimeError(
            "scipy.signal is required for speed/pitch processing. "
            "Install dependencies with: pip install -r requirements.txt"
        ) from exc

    ratio = 1.0 / factor
    limit = 1000
    up = max(1, round(ratio * limit))
    down = limit
    divisor = math.gcd(up, down)
    up //= divisor
    down //= divisor
    return resample_poly(audio_array, up, down).astype(audio_array.dtype, copy=False)


def patch_f5_torchaudio_load() -> None:
    """Avoid TorchCodec-backed torchaudio.load on Windows.

    torchaudio 2.11 routes load() through TorchCodec. On Windows this can fail
    when FFmpeg shared DLLs are missing. F5-TTS only needs a waveform tensor and
    sample rate here, so soundfile is enough for WAV/FLAC-style references.
    """
    try:
        import numpy as np
        import soundfile as sf
        import torch
        import f5_tts.infer.utils_infer as utils_infer
    except ImportError as exc:
        raise RuntimeError(
            "soundfile/torch are required for the safe F5-TTS audio loader. "
            "Install dependencies with: pip install -r requirements.txt"
        ) from exc

    def safe_load(uri, *args, **kwargs):
        data, sample_rate = sf.read(str(uri), dtype="float32", always_2d=True)
        # torchaudio.load returns channels-first tensors.
        tensor = torch.from_numpy(np.ascontiguousarray(data.T))
        return tensor, sample_rate

    import torchaudio
    torchaudio.load = safe_load
    utils_infer.torchaudio.load = safe_load


def patch_whisper_local() -> None:
    """Point F5-TTS Whisper transcription at a local model directory."""
    if not DEFAULT_WHISPER_PATH.is_dir():
        return

    import sys
    import types

    # Block torchcodec import — transformers tries it for audio preprocessing
    # but it fails on Windows without FFmpeg DLLs.
    if "torchcodec" not in sys.modules:
        fake = types.ModuleType("torchcodec")
        fake.__path__ = []  # type: ignore[attr-defined]
        sys.modules["torchcodec"] = fake
        for sub in ("decoders", "encoders", "samplers", "transforms", "_core", "_core.ops", "_core._metadata", "_internally_replaced_utils"):
            child = types.ModuleType(f"torchcodec.{sub}")
            child.__path__ = []  # type: ignore[attr-defined]
            sys.modules[f"torchcodec.{sub}"] = child
            parts = sub.split(".")
            parent = fake
            for p in parts[:-1]:
                parent = getattr(parent, p)
            setattr(parent, parts[-1], child)
        # transformers checks isinstance(inputs, torchcodec.decoders.AudioDecoder)
        setattr(sys.modules["torchcodec.decoders"], "AudioDecoder", type("AudioDecoder", (), {}))

    try:
        from transformers import pipeline
        import f5_tts.infer.utils_infer as utils_infer
    except ImportError:
        return

    whisper_path = str(DEFAULT_WHISPER_PATH)

    def _init_asr(device=None, dtype=None):
        utils_infer.asr_pipe = pipeline(
            "automatic-speech-recognition",
            model=whisper_path,
            torch_dtype=dtype,
            device=device or utils_infer.device,
        )

    utils_infer.initialize_asr_pipeline = _init_asr


def compress_long_silences(
    audio_array,
    sample_rate: int,
    *,
    max_pause_ms: int = DEFAULT_MAX_PAUSE_MS,
    threshold_db: float = DEFAULT_SILENCE_THRESHOLD_DB,
    min_silence_ms: int = DEFAULT_MIN_SILENCE_MS,
):
    if max_pause_ms <= 0:
        return audio_array

    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is required for silence compression.") from exc

    if len(audio_array) == 0:
        return audio_array

    mono = audio_array
    if getattr(audio_array, "ndim", 1) > 1:
        mono = np.max(np.abs(audio_array), axis=1)
    else:
        mono = np.abs(audio_array)

    peak = float(np.max(mono))
    if peak <= 0:
        return audio_array

    threshold = peak * (10 ** (threshold_db / 20.0))
    silent = mono <= threshold
    min_samples = max(1, int(sample_rate * min_silence_ms / 1000))
    keep_samples = max(1, int(sample_rate * max_pause_ms / 1000))

    chunks = []
    start = 0
    index = 0
    length = len(audio_array)

    while index < length:
        if not silent[index]:
            index += 1
            continue

        silence_start = index
        while index < length and silent[index]:
            index += 1
        silence_end = index
        silence_len = silence_end - silence_start

        if silence_len >= min_samples and silence_len > keep_samples:
            keep_left = keep_samples // 2
            keep_right = keep_samples - keep_left
            cut_start = silence_start + keep_left
            cut_end = silence_end - keep_right
            chunks.append(audio_array[start:cut_start])
            start = cut_end

    chunks.append(audio_array[start:])
    if len(chunks) == 1:
        return audio_array
    return np.concatenate(chunks).astype(audio_array.dtype, copy=False)


def generate_audio(
    text: str,
    *,
    ref_file: str,
    ref_text: str,
    output: Path,
    speed: float = DEFAULT_SPEED,
    speed_pitch: float = DEFAULT_SPEED_PITCH,
    max_pause_ms: int = DEFAULT_MAX_PAUSE_MS,
    silence_threshold_db: float = DEFAULT_SILENCE_THRESHOLD_DB,
    min_silence_ms: int = DEFAULT_MIN_SILENCE_MS,
    device: str = DEFAULT_DEVICE,
    ckpt_file: str = "",
    vocoder_path: str = "",
    accent: bool = False,
    accent_intensity: int = 2,
    emotion: str = "",
    prepared_text: bool = False,
) -> str:
    try:
        from f5_tts.api import F5TTS
    except ImportError as exc:
        raise RuntimeError(
            "f5-tts is required. Install with: pip install -r requirements.txt"
        ) from exc

    patch_f5_torchaudio_load()
    patch_whisper_local()

    try:
        import numpy as np
        from scipy.io.wavfile import write as write_wav
    except ImportError as exc:
        raise RuntimeError(
            "scipy/numpy are required. Install with: pip install -r requirements.txt"
        ) from exc

    # Auto-detect local model files
    if not ckpt_file and DEFAULT_CKPT_FILE.is_file():
        ckpt_file = str(DEFAULT_CKPT_FILE)
    if not vocoder_path and DEFAULT_VOCODER_PATH.is_dir():
        vocoder_path = str(DEFAULT_VOCODER_PATH)

    ckpt_label = Path(ckpt_file).name if ckpt_file else "huggingface"
    vocoder_label = Path(vocoder_path).name if vocoder_path else "huggingface"
    print(f"Loading F5TTS on device: {device}")
    print(f"  ckpt: {ckpt_label}")
    print(f"  vocoder: {vocoder_label}")

    ref_text = ref_text.strip()
    try:
        import soundfile as sf

        ref_info = sf.info(str(ref_file))
        ref_duration = ref_info.frames / ref_info.samplerate if ref_info.samplerate else 0
        if ref_duration > 12 and ref_text:
            print(
                "Warning: reference audio is longer than 12s. "
                "F5-TTS will clip it internally, so ref_text must match the clipped first part only. "
                "A full-audio transcript can make speech too fast or drop the beginning."
            )
    except Exception:
        pass

    tts = F5TTS(
        model="F5TTS_v1_Base",
        device=device,
        ckpt_file=ckpt_file,
        vocoder_local_path=vocoder_path or None,
    )
    if not prepared_text:
        text = prepare_generation_text(
            text,
            emotion=emotion,
            accent=accent,
            accent_intensity=accent_intensity,
        )
    else:
        text = text.strip()
    print(f"Final prompt: {text}")

    print(f"Model loaded. Starting inference...")
    wav, sr, _ = tts.infer(
        ref_file=ref_file,
        ref_text=ref_text,
        gen_text=text,
        speed=speed * emotion_speed_factor(emotion),
    )

    audio_array = np.array(wav)
    audio_array = compress_long_silences(
        audio_array,
        sr,
        max_pause_ms=max_pause_ms,
        threshold_db=silence_threshold_db,
        min_silence_ms=min_silence_ms,
    )
    audio_array = apply_speed_pitch(audio_array, speed_pitch)

    output.parent.mkdir(parents=True, exist_ok=True)
    write_wav(str(output), sr, audio_array)
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate voice-cloned Chinese speech using F5-TTS."
    )
    parser.add_argument(
        "text",
        nargs="?",
        default="大家好，我是北极熊。今天我来读中文。",
        help="Chinese text to synthesize.",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"WAV output path. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--refs-dir",
        type=Path,
        default=None,
        help="Directory containing {character}_{emotion} reference audio files.",
    )
    parser.add_argument(
        "--character",
        default=None,
        help="Character name (filename prefix before _).",
    )
    parser.add_argument(
        "--emotion",
        default=None,
        help="Emotion name (filename part after _).",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=DEFAULT_SPEED,
        help=f"F5-TTS inference speed. Default: {DEFAULT_SPEED}",
    )
    parser.add_argument(
        "--speed-pitch",
        type=float,
        default=DEFAULT_SPEED_PITCH,
        help=f"Post-processing speed/pitch multiplier. Default: {DEFAULT_SPEED_PITCH}",
    )
    parser.add_argument(
        "--max-pause-ms",
        type=int,
        default=DEFAULT_MAX_PAUSE_MS,
        help=f"Compress detected long silences to this duration in ms. Default: {DEFAULT_MAX_PAUSE_MS}",
    )
    parser.add_argument(
        "--silence-threshold-db",
        type=float,
        default=DEFAULT_SILENCE_THRESHOLD_DB,
        help=f"Relative silence threshold in dB. Default: {DEFAULT_SILENCE_THRESHOLD_DB}",
    )
    parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help=f"Device for inference (cuda/cpu). Default: {DEFAULT_DEVICE}",
    )
    parser.add_argument(
        "--ckpt-file",
        default="",
        help=f"Path to F5TTS model checkpoint. Default: auto-detect {DEFAULT_CKPT_FILE.name}",
    )
    parser.add_argument(
        "--vocoder-path",
        default="",
        help=f"Path to vocoder directory. Default: auto-detect {DEFAULT_VOCODER_PATH.name}",
    )
    parser.add_argument(
        "--ref-file",
        default=None,
        help="Override reference audio file path directly.",
    )
    parser.add_argument(
        "--ref-text",
        default=None,
        help="Override reference transcript directly.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available characters and emotions, then exit.",
    )
    parser.add_argument(
        "--accent",
        action="store_true",
        help="Convert Chinese text to English-accented pinyin before synthesis.",
    )
    parser.add_argument(
        "--accent-intensity",
        type=int,
        choices=[1, 2, 3, 4],
        default=2,
        help="Accent intensity: 1=soft, 2=balanced, 3=strong, 4=chaos. Default: 2",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        refs_dir = args.refs_dir or Path(__file__).resolve().parent / "references"

        if args.list:
            data = scan_references(refs_dir)
            if not data["characters"]:
                print(f"No reference audio found in {refs_dir}")
                print("Expected filename format: {character}_{emotion}.wav")
                return 0
            for char in data["characters"]:
                emotions = sorted(data["map"][char].keys())
                print(f"  {char}: {', '.join(emotions)}")
            return 0

        if args.ref_file and args.ref_text:
            ref_file = args.ref_file
            ref_text = args.ref_text
        else:
            if not args.character or not args.emotion:
                print("Error: --character and --emotion are required (or use --ref-file + --ref-text).", file=sys.stderr)
                return 1
            ref_file, ref_text = resolve_reference(refs_dir, args.character, args.emotion)
            if args.ref_file:
                ref_file = args.ref_file
            if args.ref_text:
                ref_text = args.ref_text

        print(f"Character: {args.character} | Emotion: {args.emotion}")
        print(f"Reference: {ref_file}")
        print(f"Ref text: {ref_text}")
        print(f"Generating: {args.text}")

        generate_audio(
            args.text,
            ref_file=ref_file,
            ref_text=ref_text,
            output=args.output,
            speed=args.speed,
            speed_pitch=args.speed_pitch,
            max_pause_ms=args.max_pause_ms,
            silence_threshold_db=args.silence_threshold_db,
            device=args.device,
            ckpt_file=args.ckpt_file,
            vocoder_path=args.vocoder_path,
            accent=args.accent,
            accent_intensity=args.accent_intensity,
            emotion=args.emotion or "",
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Done: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
