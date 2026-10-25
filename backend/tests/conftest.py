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
        transcription_provider="disabled",
        openai_api_key=None,
        openai_transcription_model="gpt-transcribe",
        openai_transcription_prompt="",
    )


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def client(database_path: Path):
    with TestClient(create_app(make_test_settings(database_path))) as test_client:
        yield test_client
