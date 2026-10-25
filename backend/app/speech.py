"""Local text-to-speech for the assistant voice (Kokoro), with browser speech as fallback.

This module only renders text to audio. It never saves notes, changes object
identity, or reports an action as done.
"""
from __future__ import annotations

import io
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
MAX_SPEECH_CHARS = 600
# Homebrew prefixes on Apple Silicon and Intel; the bundled eSpeak in Kokoro's
# wheel points at its build machine on macOS, so a system eSpeak NG is required.
ESPEAK_PREFIXES = (Path("/opt/homebrew/opt/espeak-ng"), Path("/usr/local/opt/espeak-ng"))


class SpeechUnavailable(Exception):
    pass


class SpeechBusy(Exception):
    pass


def find_espeak(library: Path | None, data: Path | None) -> tuple[Path, Path]:
    if library and data:
        return library, data
    for prefix in ESPEAK_PREFIXES:
        found_library = prefix / "lib" / "libespeak-ng.dylib"
        found_data = prefix / "share" / "espeak-ng-data"
        if found_library.exists() and found_data.exists():
            return library or found_library, data or found_data
    raise SpeechUnavailable(
        "eSpeak NG was not found. Run `brew install espeak-ng`, or set "
        "APP_ESPEAK_LIBRARY and APP_ESPEAK_DATA."
    )


class BrowserSpeech:
    """The browser speaks with its own system voice; the server renders nothing."""

    name = "browser"
    voice = None
    status = "browser"
    message = None

    def start(self) -> None:
        return None

    def synthesize(self, text: str) -> bytes:
        raise SpeechUnavailable("Server speech is off; the browser voice is in use.")


class KokoroSpeech:
    """One Kokoro pipeline per process, loaded and warmed once off the request loop."""

    name = "kokoro"

    def __init__(self, *, voice: str, espeak_library: Path | None = None, espeak_data: Path | None = None) -> None:
        self.voice = voice
        self.espeak_library = espeak_library
        self.espeak_data = espeak_data
        self.status = "loading"
        self.message: str | None = None
        self._pipeline = None
        self._generate = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._load, name="kokoro-load", daemon=True).start()

    def _load(self) -> None:
        try:
            library, data = find_espeak(self.espeak_library, self.espeak_data)
            # Imported lazily so the API starts quickly and tests never load torch.
            from kokoro import KPipeline
            from phonemizer.backend.espeak.wrapper import EspeakWrapper

            EspeakWrapper.set_library(str(library))
            EspeakWrapper.set_data_path(str(data))
            pipeline = KPipeline(lang_code=self.voice[0], repo_id="hexgrad/Kokoro-82M")
            with self._generate:
                self._pipeline = pipeline
                self._render("Ready.")
            self.status = "ready"
        except Exception as error:  # noqa: BLE001 - surfaced through /api/health
            logger.exception("Kokoro speech failed to load")
            self.status = "unavailable"
            self.message = f"Kokoro speech is unavailable: {error}"

    def _render(self, text: str) -> bytes:
        import numpy as np
        import soundfile

        chunks = [np.asarray(audio) for _, _, audio in self._pipeline(text, voice=self.voice)]
        if not chunks:
            raise SpeechUnavailable("Kokoro produced no audio for that text.")
        buffer = io.BytesIO()
        soundfile.write(buffer, np.concatenate(chunks), SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return buffer.getvalue()

    def synthesize(self, text: str) -> bytes:
        if self.status != "ready":
            raise SpeechUnavailable(self.message or "The assistant voice is still loading. Try again in a moment.")
        # One reply at a time, so speech never queues up behind itself or starves recognition.
        if not self._generate.acquire(timeout=10):
            raise SpeechBusy("The assistant voice is busy. Try again in a moment.")
        try:
            return self._render(text)
        finally:
            self._generate.release()


def build_speech_provider(
    *, provider: str, voice: str, espeak_library: Path | None, espeak_data: Path | None
) -> BrowserSpeech | KokoroSpeech:
    if provider == "browser":
        return BrowserSpeech()
    if provider == "kokoro":
        return KokoroSpeech(voice=voice, espeak_library=espeak_library, espeak_data=espeak_data)
    raise ValueError("Speech provider must be kokoro or browser")
