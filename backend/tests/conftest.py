from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def make_test_settings(database_path: Path) -> Settings:
    return Settings(
        database_path=database_path,
        camera_source="disabled",
        camera_index=0,
        camera_fixture=database_path.parent / "missing.png",
        camera_width=1280,
        camera_height=720,
        detection_ttl_ms=750,
        marker_dictionary="DICT_4X4_50",
        recognizer="instance",
        enrolled_dir=database_path.parent / "enrolled",
        max_reference_files_per_identity=4,
        max_auto_banked_files_per_identity=2,
        recognition_max_width=960,
        recognition_fps=8.0,
        stream_fps=15.0,
        stream_jpeg_quality=75,
        opencv_threads=3,
        transcription_provider="disabled",
        openai_api_key=None,
        openai_transcription_model="gpt-transcribe",
        openai_transcription_prompt="",
        whisper_model="medium",
        whisper_device="cpu",
        whisper_compute_type="int8",
    )


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def client(database_path: Path):
    with TestClient(create_app(make_test_settings(database_path))) as test_client:
        yield test_client
