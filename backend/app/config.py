from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _path_env(name: str, default: str) -> Path:
    value = Path(os.getenv(name, default)).expanduser()
    return value if value.is_absolute() else ROOT / value


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    camera_source: str
    camera_index: int
    camera_fixture: Path
    camera_width: int
    camera_height: int
    detection_ttl_ms: int
    marker_dictionary: str
    recognizer: str
    enrolled_dir: Path
    max_reference_files_per_identity: int
    max_auto_banked_files_per_identity: int
    recognition_max_width: int
    recognition_fps: float
    stream_fps: float
    stream_jpeg_quality: int
    opencv_threads: int
    transcription_provider: str
    openai_api_key: str | None
    openai_transcription_model: str
    openai_transcription_prompt: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    llm_parser_enabled: bool = True
    assistant_model: str = "qwen3.5:4b"
    ollama_url: str = "http://127.0.0.1:11434"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=_path_env("APP_DATABASE_PATH", "./data/locus.db"),
            camera_source=os.getenv("APP_CAMERA_SOURCE", "camera").lower(),
            camera_index=int(os.getenv("APP_CAMERA_INDEX", "0")),
            camera_fixture=_path_env(
                "APP_CAMERA_FIXTURE", "./markers/markerless-fixture.png"
            ),
            camera_width=int(os.getenv("APP_CAMERA_WIDTH", "1280")),
            camera_height=int(os.getenv("APP_CAMERA_HEIGHT", "720")),
            detection_ttl_ms=int(os.getenv("APP_DETECTION_TTL_MS", "2000")),
            marker_dictionary=os.getenv(
                "APP_MARKER_DICTIONARY", "DICT_4X4_50"
            ),
            recognizer=os.getenv("APP_RECOGNIZER", "instance").lower(),
            enrolled_dir=_path_env("APP_ENROLLED_DIR", "./data/enrolled"),
            max_reference_files_per_identity=max(
                1, int(os.getenv("APP_MAX_REFERENCE_FILES_PER_IDENTITY", "4"))
            ),
            max_auto_banked_files_per_identity=max(
                0, int(os.getenv("APP_MAX_AUTO_BANKED_FILES_PER_IDENTITY", "2"))
            ),
            recognition_max_width=max(
                320, int(os.getenv("APP_RECOGNITION_MAX_WIDTH", "960"))
            ),
            recognition_fps=max(
                0.5, float(os.getenv("APP_RECOGNITION_FPS", "8"))
            ),
            stream_fps=max(1.0, float(os.getenv("APP_STREAM_FPS", "15"))),
            stream_jpeg_quality=min(
                95, max(30, int(os.getenv("APP_STREAM_JPEG_QUALITY", "75")))
            ),
            opencv_threads=max(1, int(os.getenv("APP_OPENCV_THREADS", "3"))),
            transcription_provider=os.getenv(
                "APP_TRANSCRIPTION_PROVIDER", "disabled"
            ).lower(),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_transcription_model=os.getenv(
                "OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe"
            ),
            openai_transcription_prompt=os.getenv(
                "OPENAI_TRANSCRIPTION_PROMPT",
                "Names in this social app may include Vishal, Pravan, Theo, and Lina.",
            ),
            whisper_model=os.getenv("APP_WHISPER_MODEL", "medium"),
            whisper_device=os.getenv("APP_WHISPER_DEVICE", "cpu"),
            whisper_compute_type=os.getenv(
                "APP_WHISPER_COMPUTE_TYPE", "int8"
            ),
            llm_parser_enabled=os.getenv("APP_LLM_PARSER_ENABLED", "true").lower() == "true",
            assistant_model=os.getenv("APP_ASSISTANT_MODEL", "qwen3.5:4b"),
            ollama_url=os.getenv("APP_OLLAMA_URL", "http://127.0.0.1:11434"),
        )
