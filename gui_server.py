from __future__ import annotations

import json
import mimetypes
import re
import time
import wave
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from beijixiong_voice import (
    DEFAULT_MAX_CHARS,
    DEFAULT_SEED,
    DEFAULT_SPEED_PITCH,
    DEFAULT_TEXT_TEMP,
    DEFAULT_VOICE,
    DEFAULT_WAVEFORM_TEMP,
    VOICE_PRESETS,
    generate_audio_file,
    make_polar_bear_prompt,
)


ROOT = Path(__file__).resolve().parent
GUI_DIR = ROOT / "gui"
OUTPUT_DIR = ROOT / "output"


def json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("._") or "beijixiong"


def audio_path(file_name: str) -> Path:
    name = safe_name(file_name)
    path = (OUTPUT_DIR / name).resolve()
    output_root = OUTPUT_DIR.resolve()
    if not str(path).startswith(str(output_root)) or path.suffix.lower() != ".wav":
        raise RuntimeError("Invalid audio file.")
    return path


def audio_info(path: Path) -> dict:
    duration = None
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            duration = round(frames / rate, 2) if rate else None
    except wave.Error:
        try:
            from scipy.io import wavfile

            rate, data = wavfile.read(str(path))
            duration = round(len(data) / rate, 2) if rate else None
        except Exception:
            pass

    stat = path.stat()
    return {
        "file": path.name,
        "url": f"/audio?file={path.name}",
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "duration": duration,
    }


def list_audio_files() -> list[dict]:
    if not OUTPUT_DIR.exists():
        return []
    files = sorted(
        OUTPUT_DIR.glob("*.wav"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    return [audio_info(path) for path in files]


class GuiHandler(SimpleHTTPRequestHandler):
    server_version = "BeijixiongVoiceGUI/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_file(GUI_DIR / "index.html")
            return
        if parsed.path == "/api/config":
            self.send_json(
                {
                    "defaultVoice": DEFAULT_VOICE,
                    "defaultSeed": DEFAULT_SEED,
                    "defaultTextTemp": DEFAULT_TEXT_TEMP,
                    "defaultWaveformTemp": DEFAULT_WAVEFORM_TEMP,
                    "defaultMaxChars": DEFAULT_MAX_CHARS,
                    "defaultSpeedPitch": DEFAULT_SPEED_PITCH,
                    "voices": VOICE_PRESETS,
                }
            )
            return
        if parsed.path == "/api/audios":
            self.send_json({"audios": list_audio_files()})
            return
        if parsed.path == "/audio":
            self.serve_audio(parse_qs(parsed.query).get("file", [""])[0])
            return
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if parsed.path.startswith("/gui/"):
            self.serve_file(ROOT / parsed.path.lstrip("/"))
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {
            "/api/preview",
            "/api/generate",
            "/api/rename-audio",
            "/api/delete-audio",
        }:
            self.send_error(404)
            return

        try:
            payload = self.read_json()
            if parsed.path == "/api/rename-audio":
                old_path = audio_path(str(payload.get("file") or ""))
                if not old_path.is_file():
                    raise RuntimeError("Audio file not found.")
                new_base = safe_name(str(payload.get("name") or old_path.stem))
                new_path = audio_path(f"{Path(new_base).stem}.wav")
                if new_path.exists() and new_path != old_path:
                    raise RuntimeError("A file with that name already exists.")
                old_path.rename(new_path)
                self.send_json({"audio": audio_info(new_path)})
                return

            if parsed.path == "/api/delete-audio":
                path = audio_path(str(payload.get("file") or ""))
                if path.is_file():
                    path.unlink()
                self.send_json({"ok": True, "audios": list_audio_files()})
                return

            prompt = make_polar_bear_prompt(
                str(payload.get("text") or ""),
                raw_pinyin=False,
                intensity="balanced",
                prefix="",
                compact_pinyin=True,
            )
            if parsed.path == "/api/preview":
                self.send_json({"prompt": prompt})
                return

            voice = str(payload.get("voice") or DEFAULT_VOICE)
            if voice not in VOICE_PRESETS:
                raise RuntimeError(f"Unknown voice preset: {voice}")

            output_name = safe_name(str(payload.get("outputName") or "beijixiong"))
            output = OUTPUT_DIR / f"{output_name}_{voice}_{int(time.time())}.wav"
            speaker = str(payload.get("speaker") or VOICE_PRESETS[voice]["speaker"])
            speed_pitch = float(
                payload.get("speedPitch")
                or VOICE_PRESETS[voice].get("speed_pitch")
                or DEFAULT_SPEED_PITCH
            )
            generate_audio_file(
                prompt,
                output=output,
                speaker=speaker,
                preload=not bool(payload.get("noPreload")),
                small_models=False,
                seed=int(payload.get("seed") or DEFAULT_SEED),
                text_temp=float(payload.get("textTemp") or DEFAULT_TEXT_TEMP),
                waveform_temp=float(
                    payload.get("waveformTemp") or DEFAULT_WAVEFORM_TEMP
                ),
                max_chars=int(payload.get("maxChars") or DEFAULT_MAX_CHARS),
                speed_pitch=speed_pitch,
            )
            self.send_json(
                {
                    "prompt": prompt,
                    "audio": audio_info(output),
                }
            )
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        if not body:
            return {}
        value = json.loads(body)
        if not isinstance(value, dict):
            raise RuntimeError("JSON body must be an object.")
        return value

    def send_json(self, payload: object, status: int = 200) -> None:
        data = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_file(self, path: Path) -> None:
        path = path.resolve()
        if not str(path).startswith(str(ROOT)) or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif path.suffix in {".html", ".css"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_audio(self, file_name: str) -> None:
        try:
            path = audio_path(file_name)
        except RuntimeError:
            self.send_error(404)
            return
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[gui] {self.address_string()} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 7860), GuiHandler)
    print("Beijixiong Voice GUI: http://127.0.0.1:7860")
    server.serve_forever()


if __name__ == "__main__":
    main()
