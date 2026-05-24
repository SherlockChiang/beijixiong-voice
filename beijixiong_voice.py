from __future__ import annotations

import argparse
import math
import os
import random
import re
import sys
from pathlib import Path


DEFAULT_VOICE = "little-girl"
DEFAULT_OUTPUT = Path("output/beijixiong_voice.wav")
DEFAULT_PREFIX = ""
DEFAULT_SEED = 20260523
DEFAULT_TEXT_TEMP = 0.62
DEFAULT_WAVEFORM_TEMP = 0.64
DEFAULT_MAX_CHARS = 170
DEFAULT_SPEED_PITCH = 1.16
DEFAULT_COMPACT_PINYIN = True
DEFAULT_EMOTION = "neutral"

CJK_RE = re.compile(r"[\u3400-\u9fff]")
TOKEN_RE = re.compile(r"\[[^\]]+\]|[A-Za-z0-9_:-]+|[,.!?;:]+|\S")
TEXT_RUN_RE = re.compile(r"[\u3400-\u9fff]+|[^\u3400-\u9fff]+")

PUNCT_TRANSLATION = str.maketrans(
    {
        "\u3002": ".",
        "\uff0c": ",",
        "\uff01": "!",
        "\uff1f": "?",
        "\u3001": ",",
        "\uff1b": ";",
        "\uff1a": ":",
        "\u2014": ",",
        "\u2026": "...",
    }
)

INTENSITY_LEVELS = {
    "soft": 1,
    "balanced": 2,
    "strong": 3,
    "chaos": 4,
}

VOICE_PRESETS = {
    "little-girl": {
        "speaker": "v2/en_speaker_9",
        "description": "best current bright young candidate",
        "speed_pitch": 1.2,
    },
    "soft-young": {
        "speaker": "v2/en_speaker_4",
        "description": "soft young-ish candidate",
        "speed_pitch": 1.1,
    },
    "clear-young": {
        "speaker": "v2/en_speaker_3",
        "description": "clear higher English candidate",
        "speed_pitch": 1.12,
    },
    "warm-low": {
        "speaker": "v2/en_speaker_8",
        "description": "warm low voice; not a girl voice",
        "speed_pitch": 1.08,
    },
    "low-young": {
        "speaker": "v2/en_speaker_2",
        "description": "lower young-ish candidate",
        "speed_pitch": 1.06,
    },
    "narrator": {
        "speaker": "v2/en_speaker_6",
        "description": "stable low narrator voice from the original test",
        "speed_pitch": 1.0,
    },
}

EMOTION_PRESETS = {
    "neutral": {
        "label": "平静",
        "description": "steady and plain delivery",
        "prefix": "",
        "text_temp": 0.62,
        "waveform_temp": 0.64,
        "speed_pitch": 1.0,
        "style": "plain",
    },
    "happy": {
        "label": "开心",
        "description": "brighter, faster, more animated",
        "prefix": "[laughs softly]",
        "text_temp": 0.7,
        "waveform_temp": 0.72,
        "speed_pitch": 1.06,
        "style": "bright",
    },
    "sad": {
        "label": "难过",
        "description": "slower, softer, with sighing pauses",
        "prefix": "[sighs]",
        "text_temp": 0.56,
        "waveform_temp": 0.58,
        "speed_pitch": 0.92,
        "style": "sad",
    },
    "hurt": {
        "label": "委屈",
        "description": "small, hesitant, emotionally restrained",
        "prefix": "[sighs softly]",
        "text_temp": 0.6,
        "waveform_temp": 0.62,
        "speed_pitch": 0.96,
        "style": "hesitant",
    },
    "nervous": {
        "label": "紧张",
        "description": "uneven and slightly breathy",
        "prefix": "[gasps]",
        "text_temp": 0.74,
        "waveform_temp": 0.76,
        "speed_pitch": 1.04,
        "style": "hesitant",
    },
    "cute": {
        "label": "撒娇",
        "description": "lively and playful",
        "prefix": "[giggles]",
        "text_temp": 0.68,
        "waveform_temp": 0.7,
        "speed_pitch": 1.08,
        "style": "bright",
    },
    "whisper": {
        "label": "轻声",
        "description": "soft whisper-like delivery",
        "prefix": "[whispers]",
        "text_temp": 0.54,
        "waveform_temp": 0.56,
        "speed_pitch": 0.94,
        "style": "soft",
    },
}

EXACT_SPELLINGS = {
    "a": "ah",
    "ai": "eye",
    "bei": "bay",
    "ci": "tsuh",
    "chi": "chee",
    "de": "duh",
    "er": "are",
    "ge": "guh",
    "gong": "gawng",
    "hao": "haow",
    "he": "huh",
    "ji": "gee",
    "jia": "jee-ah",
    "le": "luh",
    "ma": "mah",
    "mei": "may",
    "men": "mun",
    "neng": "nung",
    "ni": "nee",
    "qing": "ching",
    "ren": "run",
    "ri": "ree",
    "shi": "shee",
    "si": "suh",
    "wo": "woh",
    "xiong": "shee-ong",
    "yi": "yee",
    "you": "yo",
    "yu": "you",
    "zhe": "juh",
    "zhi": "zhee",
    "zi": "dzuh",
}


def contains_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text))


def _lazy_pinyin(text: str) -> list[str]:
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError as exc:
        raise RuntimeError(
            "Input contains Chinese characters, so pypinyin is required. "
            "Install dependencies with: pip install -r requirements.txt. "
            f"Current Python: {sys.executable}"
        ) from exc

    return lazy_pinyin(
        text,
        style=Style.NORMAL,
        neutral_tone_with_five=False,
        errors=lambda value: list(value),
    )


def romanize_chinese(text: str, compact_pinyin: bool = DEFAULT_COMPACT_PINYIN) -> str:
    normalized = text.translate(PUNCT_TRANSLATION)
    if not compact_pinyin:
        parts = _lazy_pinyin(normalized)
        return " ".join(part for part in parts if part.strip())

    output: list[str] = []
    for run in TEXT_RUN_RE.findall(normalized):
        if contains_cjk(run):
            output.append(group_pinyin(_lazy_pinyin(run)))
        else:
            output.append(run)
    return "".join(output)


def group_pinyin(parts: list[str]) -> str:
    parts = [part for part in parts if part.strip()]
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


def normalize_source(
    text: str,
    raw_pinyin: bool,
    compact_pinyin: bool = DEFAULT_COMPACT_PINYIN,
) -> str:
    normalized = text.translate(PUNCT_TRANSLATION)
    if raw_pinyin or not contains_cjk(normalized):
        return normalized
    return romanize_chinese(normalized, compact_pinyin=compact_pinyin)


def soften_final(word: str) -> str:
    replacements = (
        ("iang", "ee-ahng"),
        ("iong", "ee-ong"),
        ("uang", "oo-ahng"),
        ("ang", "ahng"),
        ("eng", "ung"),
        ("ong", "awng"),
        ("ian", "ee-en"),
        ("iao", "ee-aow"),
        ("uan", "oo-en"),
        ("ai", "eye"),
        ("ei", "ay"),
        ("ao", "aow"),
        ("ou", "oh"),
        ("uo", "woh"),
        ("ui", "way"),
        ("iu", "yo"),
    )
    for old, new in replacements:
        if old in word:
            word = word.replace(old, new)
    return word


def reshape_initial(word: str) -> str:
    replacements = (
        ("x", "sh"),
        ("q", "ch"),
        ("zh", "j"),
        ("c", "ts"),
        ("r", "rr"),
    )
    for old, new in replacements:
        if word.startswith(old):
            return new + word[len(old) :]
    return word


def stretch_vowel(word: str) -> str:
    for vowel in ("a", "o", "e"):
        index = word.rfind(vowel)
        if index != -1:
            return word[:index] + vowel * 3 + word[index + 1 :]
    return word


def accent_word(token: str, level: int, word_index: int) -> str:
    original = token
    word = token.lower()
    word = word.replace("u:", "v").replace("ü", "v").replace("v", "yu")
    word = re.sub(r"[1-5]$", "", word)

    if level >= 3 and word_index % 5 == 0:
        word = word.capitalize()

    if level >= 4 and word_index % 7 == 3:
        word = stretch_vowel(word)

    if original.isupper():
        return word.upper()
    return word


def join_tokens(tokens: list[str]) -> str:
    output: list[str] = []
    no_space_before = {".", ",", "!", "?", ";", ":", "..."}

    for token in tokens:
        if not output:
            output.append(token)
            continue

        if token in no_space_before:
            output[-1] = output[-1].rstrip() + token
        elif output[-1].endswith("["):
            output.append(token)
        else:
            output.append(" " + token)

    return "".join(output).strip()


def apply_emotion(prompt: str, emotion: str = DEFAULT_EMOTION) -> str:
    preset = EMOTION_PRESETS.get(emotion, EMOTION_PRESETS[DEFAULT_EMOTION])
    styled = prompt

    if preset["style"] == "sad":
        styled = styled.replace(", ", "... ")
        styled = re.sub(r"\.\s*", "... ", styled).strip()
    elif preset["style"] == "hesitant":
        styled = styled.replace(", ", "... ")
        styled = re.sub(r"\.\s*$", "...", styled)
    elif preset["style"] == "bright":
        styled = re.sub(r"\.\s*$", "!", styled)
    elif preset["style"] == "soft":
        styled = styled.replace("! ", ". ")

    emotion_prefix = str(preset["prefix"]).strip()
    if emotion_prefix:
        styled = f"{emotion_prefix} {styled}"
    return styled.strip()


def make_polar_bear_prompt(
    text: str,
    *,
    raw_pinyin: bool = False,
    intensity: str = "balanced",
    prefix: str = DEFAULT_PREFIX,
    compact_pinyin: bool = DEFAULT_COMPACT_PINYIN,
    emotion: str = DEFAULT_EMOTION,
) -> str:
    level = INTENSITY_LEVELS[intensity]
    source = normalize_source(text, raw_pinyin, compact_pinyin=compact_pinyin)
    tokens = TOKEN_RE.findall(source)

    accented: list[str] = []
    word_index = 0
    for token in tokens:
        if token.startswith("[") and token.endswith("]"):
            accented.append(token)
        elif re.fullmatch(r"[A-Za-z0-9_:-]+", token):
            accented.append(accent_word(token, level, word_index))
            word_index += 1
        else:
            accented.append(token)

    prompt = join_tokens(accented)
    clean_prefix = prefix.strip()
    if clean_prefix:
        prompt = f"{clean_prefix} {prompt}"
    prompt = apply_emotion(prompt, emotion)
    return prompt


def list_voices() -> str:
    rows = ["Available voices:"]
    for name, preset in VOICE_PRESETS.items():
        rows.append(f"  {name:<12} {preset['speaker']:<16} {preset['description']}")
    return "\n".join(rows)


def list_emotions() -> str:
    rows = ["Available emotions:"]
    for name, preset in EMOTION_PRESETS.items():
        rows.append(f"  {name:<8} {preset['label']:<6} {preset['description']}")
    return "\n".join(rows)


def split_prompt(prompt: str, max_chars: int) -> list[str]:
    if max_chars <= 0 or len(prompt) <= max_chars:
        return [prompt]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for token in re.split(r"(\s+)", prompt):
        token_len = len(token)
        if current and current_len + token_len > max_chars:
            chunks.append("".join(current).strip())
            current = [token.lstrip()]
            current_len = len(current[0])
        else:
            current.append(token)
            current_len += token_len

    if current:
        chunks.append("".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def seed_everything(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass

    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


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


def generate_audio_file(
    prompt: str,
    *,
    output: Path,
    speaker: str,
    preload: bool,
    small_models: bool,
    seed: int,
    text_temp: float,
    waveform_temp: float,
    max_chars: int,
    speed_pitch: float,
) -> None:
    if small_models:
        os.environ["SUNO_USE_SMALL_MODELS"] = "True"

    try:
        import numpy as np
        from bark import SAMPLE_RATE, generate_audio, preload_models
        from scipy.io.wavfile import write as write_wav
    except ImportError as exc:
        raise RuntimeError(
            "Bark/scipy dependencies are missing. Install them with: "
            "pip install -r requirements.txt"
        ) from exc

    if preload:
        preload_models()

    seed_everything(seed)
    audio_parts = []
    chunks = split_prompt(prompt, max_chars=max_chars)
    for index, chunk in enumerate(chunks, start=1):
        if len(chunks) > 1:
            print(f"Generating chunk {index}/{len(chunks)}...")
        audio_parts.append(
            generate_audio(
                chunk,
                history_prompt=speaker,
                text_temp=text_temp,
                waveform_temp=waveform_temp,
            )
        )

    audio_array = audio_parts[0] if len(audio_parts) == 1 else np.concatenate(audio_parts)
    audio_array = apply_speed_pitch(audio_array, speed_pitch)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_wav(str(output), SAMPLE_RATE, audio_array)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a local Bark voice with a Sora2-like pinyin accent."
    )
    parser.add_argument(
        "text",
        nargs="?",
        default="大家好，我是北极熊。今天我来读中文。",
        help="Chinese text or pre-written romanized pinyin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"WAV output path. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--voice",
        choices=tuple(VOICE_PRESETS) + ("all",),
        default=DEFAULT_VOICE,
        help=f"Voice preset, or 'all' to render every preset. Default: {DEFAULT_VOICE}",
    )
    parser.add_argument(
        "--speaker",
        default=None,
        help="Override Bark history prompt / speaker id, for example v2/en_speaker_6.",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="List built-in voice presets and exit.",
    )
    parser.add_argument(
        "--list-emotions",
        action="store_true",
        help="List built-in emotion presets and exit.",
    )
    parser.add_argument(
        "--emotion",
        choices=tuple(EMOTION_PRESETS),
        default=DEFAULT_EMOTION,
        help=f"Emotion preset. Default: {DEFAULT_EMOTION}",
    )
    parser.add_argument(
        "--intensity",
        choices=tuple(INTENSITY_LEVELS),
        default="balanced",
        help="How aggressively to rewrite pinyin for the accent.",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help="Optional Bark non-speech prefix such as '[clears throat]'.",
    )
    parser.add_argument(
        "--raw-pinyin",
        action="store_true",
        help="Skip Chinese-to-pinyin conversion and treat input as romanized text.",
    )
    parser.add_argument(
        "--spaced-pinyin",
        action="store_true",
        help="Keep spaces between every pinyin syllable instead of compacting Chinese runs.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print the final Bark prompt without generating audio.",
    )
    parser.add_argument(
        "--no-preload",
        action="store_true",
        help="Call generate_audio without preload_models().",
    )
    parser.add_argument(
        "--small-models",
        action="store_true",
        help="Set SUNO_USE_SMALL_MODELS=True before loading Bark.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed for more repeatable local output. Default: {DEFAULT_SEED}",
    )
    parser.add_argument(
        "--text-temp",
        type=float,
        default=DEFAULT_TEXT_TEMP,
        help=f"Bark text temperature. Lower is steadier. Default: {DEFAULT_TEXT_TEMP}",
    )
    parser.add_argument(
        "--waveform-temp",
        type=float,
        default=DEFAULT_WAVEFORM_TEMP,
        help=f"Bark waveform temperature. Lower is steadier. Default: {DEFAULT_WAVEFORM_TEMP}",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help=f"Split long prompts for stability. Default: {DEFAULT_MAX_CHARS}",
    )
    parser.add_argument(
        "--speed-pitch",
        type=float,
        default=None,
        help=(
            "Speed/pitch multiplier applied by resampling audio data. "
            f"Default comes from the voice preset, fallback {DEFAULT_SPEED_PITCH}."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.list_voices:
            print(list_voices())
            return 0
        if args.list_emotions:
            print(list_emotions())
            return 0

        prompt = make_polar_bear_prompt(
            args.text,
            raw_pinyin=args.raw_pinyin,
            intensity=args.intensity,
            prefix=args.prefix,
            compact_pinyin=not args.spaced_pinyin,
            emotion=args.emotion,
        )

        print("Bark prompt:")
        print(prompt)

        selected_voices = list(VOICE_PRESETS) if args.voice == "all" else [args.voice]
        if args.preview:
            for voice in selected_voices:
                speaker = args.speaker or VOICE_PRESETS[voice]["speaker"]
                print(f"Voice: {voice} ({speaker})")
            return 0

        rendered_outputs: list[Path] = []
        for voice in selected_voices:
            speaker = args.speaker or VOICE_PRESETS[voice]["speaker"]
            speed_pitch = (
                args.speed_pitch
                if args.speed_pitch is not None
                else float(VOICE_PRESETS[voice].get("speed_pitch", DEFAULT_SPEED_PITCH))
            )
            speed_pitch *= float(EMOTION_PRESETS[args.emotion].get("speed_pitch", 1.0))
            output = args.output
            if args.voice == "all":
                output = args.output.with_name(
                    f"{args.output.stem}_{voice}{args.output.suffix}"
                )

            print(f"Generating with voice {voice} ({speaker})...")
            generate_audio_file(
                prompt,
                output=output,
                speaker=speaker,
                preload=not args.no_preload,
                small_models=args.small_models,
                seed=args.seed,
                text_temp=args.text_temp,
                waveform_temp=args.waveform_temp,
                max_chars=args.max_chars,
                speed_pitch=speed_pitch,
            )
            rendered_outputs.append(output)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    for output in rendered_outputs:
        print(f"Done: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
