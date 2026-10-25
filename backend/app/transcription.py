from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from io import BytesIO
from threading import Event, Lock
from typing import BinaryIO, Protocol

import httpx


class TranscriptionError(Exception):
    pass


class TranscriptionNotConfigured(TranscriptionError):
    pass


class TranscriptionProvider(Protocol):
    name: str

    @property
    def status(self) -> str: ...

    @property
    def busy(self) -> bool: ...

    async def transcribe(
        self, *, filename: str, content_type: str, audio: bytes
    ) -> str: ...


class WhisperSegment(Protocol):
    text: str


class WhisperModel(Protocol):
    def transcribe(
        self, audio: BinaryIO, **options: object
    ) -> tuple[Iterable[WhisperSegment], object]: ...


WhisperModelFactory = Callable[[str, str, str], WhisperModel]


def _load_whisper_model(
    model_name: str, device: str, compute_type: str
) -> WhisperModel:
    from faster_whisper import WhisperModel as FasterWhisperModel

    return FasterWhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
    )


@dataclass(slots=True)
class DisabledTranscriptionProvider:
    name: str = "disabled"

    @property
    def status(self) -> str:
        return "unconfigured"

    @property
    def busy(self) -> bool:
        return False

    async def transcribe(
        self, *, filename: str, content_type: str, audio: bytes
    ) -> str:
        raise TranscriptionNotConfigured(
            "Speech transcription is not configured. You can still type a message."
        )


@dataclass(slots=True)
class OpenAITranscriptionProvider:
    api_key: str
    model: str
    prompt: str
    name: str = "openai"

    @property
    def status(self) -> str:
        return "configured"

    @property
    def busy(self) -> bool:
        return False

    async def transcribe(
        self, *, filename: str, content_type: str, audio: bytes
    ) -> str:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data={"model": self.model, "prompt": self.prompt},
                    files={"file": (filename, audio, content_type)},
                )
        except httpx.HTTPError as error:
            raise TranscriptionError(
                "The transcription service could not be reached."
            ) from error

        if response.is_error:
            try:
                provider_message = response.json().get("error", {}).get("message")
            except ValueError:
                provider_message = None
            raise TranscriptionError(
                provider_message or "The transcription provider rejected the audio."
            )

        try:
            text = str(response.json()["text"]).strip()
        except (ValueError, KeyError, TypeError) as error:
            raise TranscriptionError(
                "The transcription provider returned an invalid response."
            ) from error
        if not text:
            raise TranscriptionError("No speech was detected in the recording.")
        return text


@dataclass(slots=True)
class FasterWhisperTranscriptionProvider:
    model_name: str
    device: str
    compute_type: str
    prompt: str
    model_factory: WhisperModelFactory | None = field(default=None, repr=False)
    name: str = field(default="faster-whisper", init=False)
    _model: WhisperModel = field(init=False, repr=False)
    _inference_lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _busy: Event = field(default_factory=Event, init=False, repr=False)

    def __post_init__(self) -> None:
        factory = self.model_factory or _load_whisper_model
        try:
            self._model = factory(
                self.model_name,
                self.device,
                self.compute_type,
            )
        except Exception as error:
            raise ValueError(
                "Could not load the local Faster Whisper model "
                f"{self.model_name!r} on {self.device!r} with "
                f"compute type {self.compute_type!r}."
            ) from error

    @property
    def status(self) -> str:
        return "configured"

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    def _transcribe_sync(self, audio: bytes) -> str:
        options: dict[str, object] = {
            "beam_size": 1,
            "vad_filter": True,
            "without_timestamps": True,
        }
        if self.prompt.strip():
            options["initial_prompt"] = self.prompt.strip()

        try:
            with self._inference_lock:
                self._busy.set()
                try:
                    segments, _ = self._model.transcribe(BytesIO(audio), **options)
                    text = " ".join(
                        segment.text.strip()
                        for segment in segments
                        if segment.text.strip()
                    ).strip()
                finally:
                    self._busy.clear()
        except Exception as error:
            raise TranscriptionError(
                "Local speech transcription failed."
            ) from error

        if not text:
            raise TranscriptionError("No speech was detected in the recording.")
        return text

    async def transcribe(
        self, *, filename: str, content_type: str, audio: bytes
    ) -> str:
        del filename, content_type
        return await asyncio.to_thread(self._transcribe_sync, audio)


def build_transcription_provider(
    *,
    provider: str,
    api_key: str | None,
    model: str,
    prompt: str,
    whisper_model: str,
    whisper_device: str,
    whisper_compute_type: str,
) -> TranscriptionProvider:
    if provider == "disabled":
        return DisabledTranscriptionProvider()
    if provider == "openai":
        if not api_key:
            return DisabledTranscriptionProvider()
        return OpenAITranscriptionProvider(api_key, model, prompt)
    if provider == "faster-whisper":
        return FasterWhisperTranscriptionProvider(
            model_name=whisper_model,
            device=whisper_device,
            compute_type=whisper_compute_type,
            prompt=prompt,
        )
    raise ValueError(f"Unsupported transcription provider: {provider}")
