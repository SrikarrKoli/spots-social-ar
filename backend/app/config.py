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
    transcription_provider: str
    openai_api_key: str | None
    openai_transcription_model: str
    openai_transcription_prompt: str

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
            detection_ttl_ms=int(os.getenv("APP_DETECTION_TTL_MS", "750")),
            marker_dictionary=os.getenv(
                "APP_MARKER_DICTIONARY", "DICT_4X4_50"
            ),
            recognizer=os.getenv("APP_RECOGNIZER", "instance").lower(),
            enrolled_dir=_path_env("APP_ENROLLED_DIR", "./data/enrolled"),
            transcription_provider=os.getenv(
                "APP_TRANSCRIPTION_PROVIDER", "disabled"
            ).lower(),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_transcription_model=os.getenv(
                "OPENAI_TRANSCRIPTION_MODEL", "gpt-transcribe"
            ),
            openai_transcription_prompt=os.getenv(
                "OPENAI_TRANSCRIPTION_PROMPT",
                "Names in this social app may include Maya, Theo, and Lina.",
            ),
        )
