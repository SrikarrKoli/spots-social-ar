import io
import wave

import numpy as np
import pytest

from backend.app.speech import KokoroSpeech, SpeechBusy, SpeechUnavailable, find_espeak


class FakePipeline:
    def __call__(self, text, voice):
        yield text, None, np.zeros(2400, dtype=np.float32)


def ready_kokoro():
    speech = KokoroSpeech(voice="af_heart")
    speech._pipeline = FakePipeline()
    speech.status = "ready"
    return speech


def test_health_reports_browser_voice_by_default(client):
    health = client.get('/api/health').json()
    assert health['speech_provider'] == 'browser'
    assert health['speech_status'] == 'browser'


def test_browser_provider_never_renders_server_audio(client):
    response = client.post('/api/speech', json={'text': 'Saved your note.'})
    assert response.status_code == 503


@pytest.mark.parametrize('text', ['', '   ', 'x' * 601])
def test_blank_or_oversized_text_is_rejected_before_generation(client, text):
    assert client.post('/api/speech', json={'text': text}).status_code == 422


def test_kokoro_returns_playable_wav_in_the_heart_voice(client):
    client.app.state.speech = ready_kokoro()
    health = client.get('/api/health').json()
    assert (health['speech_provider'], health['speech_status'], health['speech_voice']) == ('kokoro', 'ready', 'af_heart')

    response = client.post('/api/speech', json={'text': 'Replied to Vishal on Concert poster.'})

    assert response.status_code == 200
    assert response.headers['content-type'] == 'audio/wav'
    assert response.headers['cache-control'] == 'no-store'
    with wave.open(io.BytesIO(response.content)) as audio:
        assert audio.getframerate() == 24000
        assert audio.getnframes() == 2400


def test_loading_and_busy_engine_are_errors_not_silent_success():
    loading = KokoroSpeech(voice="af_heart")
    with pytest.raises(SpeechUnavailable):
        loading.synthesize("Hello")

    busy = ready_kokoro()
    # Another reply holds the engine for longer than the wait allows.
    busy._generate = type('HeldLock', (), {'acquire': lambda self, timeout: False, 'release': lambda self: None})()
    with pytest.raises(SpeechBusy):
        busy.synthesize("Hello")


def test_missing_espeak_gives_a_clear_setup_error(monkeypatch, tmp_path):
    monkeypatch.setattr('backend.app.speech.ESPEAK_PREFIXES', (tmp_path / 'none',))
    with pytest.raises(SpeechUnavailable, match='brew install espeak-ng'):
        find_espeak(None, None)
