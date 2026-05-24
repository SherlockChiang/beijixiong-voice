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
    AUDIO_EXTS,
    DEFAULT_DEVICE,
    DEFAULT_MAX_PAUSE_MS,
    DEFAULT_SILENCE_THRESHOLD_DB,
    DEFAULT_SPEED,
    DEFAULT_SPEED_PITCH,
    emotion_speed_factor,
    generate_audio,
    prepare_generation_text,
    resolve_reference,
    scan_references,
)

ROOT = Path(__file__).resolve().parent
GUI_DIR = ROOT / "gui"
OUTPUT_DIR = ROOT / "output"
REFS_DIR = ROOT / "references"


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


def ref_audio_path(file_name: str) -> Path:
    name = safe_name(file_name)
    ref_root = REFS_DIR.resolve()
    # Try exact path first
    path = (REFS_DIR / name).resolve()
    if str(path).startswith(str(ref_root)) and path.is_file() and path.suffix.lower() in AUDIO_EXTS:
        return path
    # Try without extension (for delete by character_emotion)
    stem = Path(name).stem
    for ext in AUDIO_EXTS:
        candidate = (REFS_DIR / f"{stem}{ext}").resolve()
        if candidate.is_file() and str(candidate).startswith(str(ref_root)):
            return candidate
    raise RuntimeError("Reference audio not found.")


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
    server_version = "BeijixiongVoiceGUI/2.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_file(GUI_DIR / "index.html")
            return
        if parsed.path == "/api/config":
            data = scan_references(REFS_DIR)
            self.send_json(
                {
                    "characters": data["characters"],
                    "map": data["map"],
                    "defaultSpeed": DEFAULT_SPEED,
                    "defaultSpeedPitch": DEFAULT_SPEED_PITCH,
                    "defaultMaxPauseMs": DEFAULT_MAX_PAUSE_MS,
                    "defaultSilenceThresholdDb": DEFAULT_SILENCE_THRESHOLD_DB,
                }
            )
            return
        if parsed.path == "/api/audios":
            self.send_json({"audios": list_audio_files()})
            return
        if parsed.path == "/audio":
            self.serve_audio(parse_qs(parsed.query).get("file", [""])[0])
            return
        if parsed.path == "/api/references/audio":
            self.serve_ref_audio(parse_qs(parsed.query).get("file", [""])[0])
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
            "/api/prompt",
            "/api/generate",
            "/api/rename-audio",
            "/api/delete-audio",
            "/api/references/upload",
            "/api/references/delete",
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

            if parsed.path == "/api/references/delete":
                file_name = str(payload.get("file") or "")
                path = ref_audio_path(file_name)
                path.unlink()
                txt_path = path.with_suffix(".txt")
                if txt_path.is_file():
                    txt_path.unlink()
                data = scan_references(REFS_DIR)
                self.send_json({"ok": True, "characters": data["characters"], "map": data["map"]})
                return

            if parsed.path == "/api/references/upload":
                character = safe_name(str(payload.get("character") or ""))
                emotion = safe_name(str(payload.get("emotion") or ""))
                ref_text = str(payload.get("ref_text") or "")
                audio_data = payload.get("audio_data")
                ext = str(payload.get("ext") or "wav").lstrip(".")

                if not character:
                    raise RuntimeError("Character name is required.")
                if not emotion:
                    raise RuntimeError("Emotion name is required.")
                if not audio_data:
                    raise RuntimeError("audio_data is required (base64-encoded).")
                if f".{ext.lower()}" not in AUDIO_EXTS:
                    raise RuntimeError(f"Unsupported audio format: .{ext}")

                import base64

                raw_bytes = base64.b64decode(audio_data)
                REFS_DIR.mkdir(parents=True, exist_ok=True)
                file_path = REFS_DIR / f"{character}_{emotion}.{ext}"
                file_path.write_bytes(raw_bytes)

                if ref_text:
                    txt_path = file_path.with_suffix(".txt")
                    txt_path.write_text(ref_text, encoding="utf-8")

                data = scan_references(REFS_DIR)
                self.send_json({"ok": True, "characters": data["characters"], "map": data["map"]})
                return

            character = str(payload.get("character") or "")
            emotion = str(payload.get("emotion") or "")

            if parsed.path == "/api/prompt":
                if not character or not emotion:
                    raise RuntimeError("character and emotion are required.")
                ref_file, ref_text = resolve_reference(REFS_DIR, character, emotion)
                text = str(payload.get("text") or "")
                prompt = prepare_generation_text(
                    text,
                    emotion=emotion,
                    accent=bool(payload.get("accent")),
                    accent_intensity=int(payload.get("accentIntensity") or 2),
                )
                speed = float(payload.get("speed") or DEFAULT_SPEED)
                self.send_json(
                    {
                        "character": character,
                        "emotion": emotion,
                        "ref_file": ref_file,
                        "ref_text": ref_text,
                        "text": text,
                        "prompt": prompt,
                        "effectiveSpeed": speed * emotion_speed_factor(emotion),
                    }
                )
                return

            if not character or not emotion:
                raise RuntimeError("character and emotion are required.")
            ref_file, ref_text = resolve_reference(REFS_DIR, character, emotion)

            text = str(payload.get("prompt") or "").strip()
            if not text:
                raise RuntimeError("请先生成或填写口音 Prompt。")
            output_name = safe_name(str(payload.get("outputName") or "beijixiong"))
            output = OUTPUT_DIR / f"{output_name}_{character}_{emotion}_{int(time.time())}.wav"

            speed = float(payload.get("speed") or DEFAULT_SPEED)
            speed_pitch = float(payload.get("speedPitch") or DEFAULT_SPEED_PITCH)

            prompt = generate_audio(
                text,
                ref_file=ref_file,
                ref_text=ref_text,
                output=output,
                speed=speed,
                speed_pitch=speed_pitch,
                max_pause_ms=int(payload.get("maxPauseMs") or DEFAULT_MAX_PAUSE_MS),
                silence_threshold_db=float(
                    payload.get("silenceThresholdDb") or DEFAULT_SILENCE_THRESHOLD_DB
                ),
                device=DEFAULT_DEVICE,
                emotion=emotion,
                prepared_text=True,
            )
            self.send_json(
                {
                    "ref_file": ref_file,
                    "ref_text": ref_text,
                    "prompt": prompt,
                    "effectiveSpeed": speed * emotion_speed_factor(emotion),
                    "audio": audio_info(output),
                }
            )
        except Exception as exc:
            import traceback
            traceback.print_exc()
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

    def serve_ref_audio(self, file_name: str) -> None:
        try:
            path = ref_audio_path(file_name)
        except RuntimeError:
            self.send_error(404)
            return
        data = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "audio/wav"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[gui] {self.address_string()} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 7860), GuiHandler)
    print("Beijixiong Voice GUI (F5-TTS): http://127.0.0.1:7860")
    server.serve_forever()


if __name__ == "__main__":
    main()
