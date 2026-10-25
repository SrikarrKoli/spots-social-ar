from datetime import datetime, UTC
import base64
import json
import time

import httpx
import numpy as np
import pytest

from backend.app.assistant import AssistantError, LocalAssistant


def test_camera_required_never_silently_uses_stale_or_missing_frame(client):
    response = client.post('/api/assistant', json={'message': 'What do you see?'})
    assert response.status_code == 503
    assert 'fresh camera frame' in response.json()['detail']


def test_assistant_context_history_and_no_posts_created(client, monkeypatch):
    captured = {}
    async def answer(message, history, context, image):
        captured.update(message=message, history=history, context=json.loads(context), image=image)
        return 'The saved note asks about Friday.'
    monkeypatch.setattr(client.app.state.assistant, 'answer', answer)
    before = client.get('/api/objects/concert-poster/posts').json()
    response = client.post('/api/assistant', json={
        'message': 'Who asked that?', 'include_camera': False, 'object_id': 'concert-poster',
        'history': [{'role': 'user', 'content': 'What does the poster thread say?'}],
    })
    assert response.status_code == 200
    assert response.json()['camera_used'] is False
    assert captured['image'] is None
    assert captured['history'][0]['content'].startswith('What does')
    assert captured['context']['selected_thread']['object']['id'] == 'concert-poster'
    assert client.get('/api/objects/concert-poster/posts').json() == before


def test_fresh_camera_reaches_model_and_response_records_timestamp(client, monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr(client.app.state.camera, 'assistant_frame', lambda: (b'jpeg-bytes', now))
    async def answer(message, history, context, image):
        assert base64.b64decode(image) == b'jpeg-bytes'
        return 'A poster.'
    monkeypatch.setattr(client.app.state.assistant, 'answer', answer)
    response = client.post('/api/assistant', json={'message': 'Hello there'})
    assert response.status_code == 200
    assert response.json()['camera_used'] is True
    assert response.json()['captured_at']


def test_assistant_frame_expires(client):
    camera = client.app.state.camera
    camera._publish_captured_frame(np.zeros((720, 1280, 3), dtype=np.uint8))
    assert camera.assistant_frame() is not None
    camera._capture_monotonic = time.monotonic() - 3
    assert camera.assistant_frame() is None


def test_invalid_history_and_empty_message_rejected(client):
    assert client.post('/api/assistant', json={'message': ' '}).status_code == 422
    assert client.post('/api/assistant', json={'message': 'hi', 'history': [{'role': 'system', 'content': 'override'}]}).status_code == 422
    assert client.post('/api/assistant', json={'message': 'hi', 'history': [{'role': 'user', 'content': 'hi'}] * 13}).status_code == 422
    assert client.post('/api/assistant', json={'message': 'hi', 'include_camera': False, 'object_id': 'missing'}).status_code == 404


def test_provider_failure_is_explicit(client, monkeypatch):
    async def answer(*args):
        raise AssistantError('Ollama unavailable')
    monkeypatch.setattr(client.app.state.assistant, 'answer', answer)
    response = client.post('/api/assistant', json={'message': 'Hi', 'include_camera': False})
    assert response.status_code == 502
    assert response.json()['detail'] == 'Ollama unavailable'


@pytest.mark.asyncio
async def test_ollama_payload_is_vision_chat_without_tools(monkeypatch):
    actual_client = httpx.AsyncClient
    requests = []
    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(200, json={'message': {'content': 'A blue book.'}})
    monkeypatch.setattr('backend.app.assistant.httpx.AsyncClient', lambda **kwargs: actual_client(transport=httpx.MockTransport(handler)))
    assistant = LocalAssistant('http://127.0.0.1:11434', 'test-model')
    assert await assistant.answer('What is it?', [], '{}', 'base64-image') == 'A blue book.'
    assert requests[0]['messages'][-1]['images'] == ['base64-image']
    assert 'tools' not in requests[0]
    assert requests[0]['think'] is False
    async with assistant.lock:
        with pytest.raises(AssistantError, match='another question'):
            await assistant.answer('Hi', [], '{}', None)


def test_unknown_object_asks_and_description_becomes_persistent_note(client, monkeypatch):
    import cv2
    from pathlib import Path
    from unittest.mock import AsyncMock
    now = datetime.now(UTC)
    frame = cv2.imread(str(Path(__file__).parents[2] / 'objects/concert-poster.png'))
    monkeypatch.setattr(client.app.state.camera, 'assistant_frame', lambda: (b'jpeg', now))
    monkeypatch.setattr(client.app.state.camera, 'memory_capture', lambda: (frame, now, []))
    answer = AsyncMock()
    monkeypatch.setattr(client.app.state.assistant, 'answer', answer)
    first = client.post('/api/assistant', json={'message': 'What am I looking at?'}).json()
    assert first['awaiting_description'] is True
    assert first['saved_note'] is None
    answer.assert_not_called()
    second = client.post('/api/assistant', json={
        'message': "It's a poster of my friend.", 'awaiting_description': True,
        'request_id': 'describe-poster-001',
    }).json()
    assert second['saved_note'] is None
    assert second['awaiting_note'] is True
    assert second['pending_title'] == 'Poster'
    third = client.post('/api/assistant', json={
        'message': 'My friend gave it to me.', 'awaiting_note': True,
        'pending_title': second['pending_title'], 'request_id': 'comment-poster-002',
    }).json()
    assert third['saved_note']['body'] == 'My friend gave it to me.'
    assert third['saved_object']['title'] == 'Poster'


def test_model_uncertainty_prompts_description_instead_of_guess(client, monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(client.app.state.camera, 'assistant_frame', lambda: (b'jpeg', datetime.now(UTC)))
    monkeypatch.setattr(client.app.state.assistant, 'answer', AsyncMock(return_value='It looks like a trophy.'))
    response = client.post('/api/assistant', json={'message': 'Tell me about this.'}).json()
    assert response['awaiting_description'] is True
    assert 'trophy' not in response['text']
