from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import BinaryIO

import pytest
from fastapi.testclient import TestClient

import backend.app.transcription as transcription_module
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.transcription import (
    FasterWhisperTranscriptionProvider,
    TranscriptionError,
)
from backend.tests.conftest import make_test_settings


@dataclass
class FakeSegment:
    text: str


class FakeWhisperModel:
    def __init__(self, segments: list[str] | None = None) -> None:
        self.segments = segments if segments is not None else [" hello ", " world "]
        self.audio = b""
        self.options: dict[str, object] = {}
        self.thread_id: int | None = None

    def transcribe(
        self, audio: BinaryIO, **options: object
    ) -> tuple[Iterable[FakeSegment], object]:
        self.audio = audio.read()
        self.options = options
        self.thread_id = threading.get_ident()
        return iter(FakeSegment(text) for text in self.segments), object()


def test_faster_whisper_settings_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_TRANSCRIPTION_PROVIDER", "faster-whisper")
    monkeypatch.setenv("APP_WHISPER_MODEL", "small.en")
    monkeypatch.setenv("APP_WHISPER_DEVICE", "cpu")
    monkeypatch.setenv("APP_WHISPER_COMPUTE_TYPE", "int8")

    settings = Settings.from_env()

    assert settings.transcription_provider == "faster-whisper"
    assert settings.whisper_model == "small.en"
    assert settings.whisper_device == "cpu"
    assert settings.whisper_compute_type == "int8"


@pytest.mark.asyncio
async def test_faster_whisper_transcribes_off_event_loop() -> None:
    model = FakeWhisperModel()
    factory_args: list[tuple[str, str, str]] = []

    def factory(model_name: str, device: str, compute_type: str):
        factory_args.append((model_name, device, compute_type))
        return model

    provider = FasterWhisperTranscriptionProvider(
        model_name="medium",
        device="cpu",
        compute_type="int8",
        prompt="Names may include Maya.",
        model_factory=factory,
    )
    event_loop_thread = threading.get_ident()

    text = await provider.transcribe(
        filename="recording.webm",
        content_type="audio/webm",
        audio=b"browser-audio",
    )

    assert text == "hello world"
    assert factory_args == [("medium", "cpu", "int8")]
    assert model.audio == b"browser-audio"
    assert model.thread_id != event_loop_thread
    assert model.options == {
        "beam_size": 5,
        "vad_filter": True,
        "without_timestamps": True,
        "initial_prompt": "Names may include Maya.",
    }


@pytest.mark.asyncio
async def test_faster_whisper_rejects_empty_transcript() -> None:
    provider = FasterWhisperTranscriptionProvider(
        model_name="medium",
        device="cpu",
        compute_type="int8",
        prompt="",
        model_factory=lambda *_: FakeWhisperModel(["  "]),
    )

    with pytest.raises(TranscriptionError, match="No speech was detected"):
        await provider.transcribe(
            filename="recording.webm",
            content_type="audio/webm",
            audio=b"silence",
        )


def test_faster_whisper_endpoint_uses_existing_api_contract(
    database_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeWhisperModel([" local transcription "])
    monkeypatch.setattr(
        transcription_module,
        "_load_whisper_model",
        lambda *_: model,
    )
    settings = replace(
        make_test_settings(database_path),
        transcription_provider="faster-whisper",
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/transcriptions",
            files={"audio": ("recording.webm", b"audio", "audio/webm")},
        )

    assert response.status_code == 200
    assert response.json() == {
        "text": "local transcription",
        "provider": "faster-whisper",
    }
