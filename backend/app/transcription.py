from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


class TranscriptionError(Exception):
    pass


class TranscriptionNotConfigured(TranscriptionError):
    pass


class TranscriptionProvider(Protocol):
    name: str

    @property
    def status(self) -> str: ...

    async def transcribe(
        self, *, filename: str, content_type: str, audio: bytes
    ) -> str: ...


@dataclass(slots=True)
class DisabledTranscriptionProvider:
    name: str = "disabled"

    @property
    def status(self) -> str:
        return "unconfigured"

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


def build_transcription_provider(
    *, provider: str, api_key: str | None, model: str, prompt: str
) -> TranscriptionProvider:
    if provider == "disabled":
        return DisabledTranscriptionProvider()
    if provider == "openai":
        if not api_key:
            return DisabledTranscriptionProvider()
        return OpenAITranscriptionProvider(api_key, model, prompt)
    raise ValueError(f"Unsupported transcription provider: {provider}")
