from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from backend.app.memories import is_bare_comment_request


@pytest.mark.parametrize('text', [
 'I want to add a new comment to this new object', 'Add a comment',
 'Can you add another comment to this object?', 'Leave a new note on that thing',
 'Please add a new comment here',
])
def test_start_comment_keywords(text):
    assert is_bare_comment_request(text)


@pytest.mark.parametrize('text', [
 "Don't add a comment", 'What comments did people add?',
 'Add a comment saying I bought this yesterday', 'Delete my comment',
 'I do not want to add a new comment',
])
def test_start_command_never_consumes_content_or_negation(text):
    assert not is_bare_comment_request(text)


def mock_capture(client, monkeypatch, matches=()):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    capture = (frame, datetime.now(UTC), list(matches))
    monkeypatch.setattr(client.app.state.camera, 'memory_capture', lambda: capture)
    return frame, capture[1]


def test_keyword_request_bypasses_llm_and_does_not_save_command(client, monkeypatch):
    mock_capture(client, monkeypatch)
    parser = AsyncMock(side_effect=AssertionError('Parser must not consume bare command'))
    monkeypatch.setattr(client.app.state.intent_parser, 'parse', parser)
    result = client.post('/api/assistant', json={'message':'I want to add a new comment to this new object'}).json()
    assert result['awaiting_description']
    assert not result['saved_note']
    assert 'center' not in result['text'].lower()
    parser.assert_not_awaited()


def test_recognized_object_asks_for_comment_instead_of_centering(client, monkeypatch):
    mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster',tier='high')])
    result = client.post('/api/assistant', json={'message':'Add a new comment to this object'}).json()
    assert result['awaiting_note']
    assert result['pending_title'] == 'Concert poster'
    assert not result['saved_note']


def test_stable_guess_is_confirmed_before_comment_and_yes_is_not_saved(client, monkeypatch):
    stable = mock_capture(client, monkeypatch)
    monkeypatch.setattr(client.app.state.camera, 'stable_view', lambda: stable)
    answer = AsyncMock(return_value='Blue water bottle')
    monkeypatch.setattr(client.app.state.assistant, 'answer', answer)
    result = client.post('/api/assistant', json={'message':'Add a new comment'}).json()
    assert result['awaiting_description']
    assert result['pending_title'] == 'Blue water bottle'
    assert result['saved_note'] is None
    confirmed = client.post('/api/assistant', json={'message':'yes', 'awaiting_description':True,'pending_title':result['pending_title']}).json()
    assert confirmed['awaiting_note']
    assert confirmed['pending_title'] == 'Blue water bottle'
    assert confirmed['saved_note'] is None


def test_steady_view_requires_dwell_rejects_motion_and_expires(client, monkeypatch):
    import time
    camera = client.app.state.camera
    now = time.monotonic()
    monkeypatch.setattr('backend.app.camera.time.monotonic', lambda: now)
    frame = np.full((480,640,3),100,dtype=np.uint8)
    camera._publish_captured_frame(frame)
    assert camera.stable_view() is None
    camera._view_samples.clear()
    for n in range(10): camera._view_samples.append((now - 3.2 + n*.35,np.full((36,48),100,dtype=np.uint8)))
    assert camera.stable_view() is not None
    camera._view_samples[0]=(now-3.2,np.zeros((36,48),dtype=np.uint8))
    assert camera.stable_view() is None
    camera._capture_monotonic=now-3
    assert camera.stable_view() is None


def test_named_fresh_match_resolves_multiple_objects_without_center_loop(client, monkeypatch):
    from backend.app.models import AssistantRequest
    import asyncio
    mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster',tier='high'),SimpleNamespace(identity_key='favorite-book',tier='high')])
    result = asyncio.run(client.app.state.memories.save(AssistantRequest(
        message='Concert poster',request_id='named-target-comment',author_id='guest',pending_title='Concert poster'),
        parsed_content={'body':'Meet here at six','title':'Concert poster'},parsed_name='Concert poster'))
    assert result.saved_note.body == 'Meet here at six'
    assert result.saved_object.id == 'concert-poster'


def test_keyword_start_works_even_when_llm_parser_is_unavailable(database_path, monkeypatch):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from backend.tests.conftest import make_test_settings
    with TestClient(create_app(replace(make_test_settings(database_path),llm_parser_enabled=True))) as client:
        mock_capture(client,monkeypatch)
        parse = AsyncMock(side_effect=AssertionError("LLM must not be needed for this explicit command"))
        monkeypatch.setattr(client.app.state.intent_parser,'parse',parse)
        result=client.post('/api/assistant',json={'message':'I want to add a new comment to this new object'}).json()
        assert result['awaiting_description']
        parse.assert_not_awaited()


@pytest.mark.asyncio
async def test_semantic_empty_comment_command_also_starts_draft(client, monkeypatch):
    from backend.app.intent_dispatch import dispatch_intent
    from backend.app.intent_parser import ParsedIntent
    from backend.app.models import AssistantRequest
    mock_capture(client,monkeypatch)
    result = await dispatch_intent(client.app.state.memories, AssistantRequest(message='Could you jot something about this bottle?'),
        ParsedIntent(action='add_comment',object_name='bottle',action_phrase='jot'))
    assert result.awaiting_note
    assert result.pending_title == 'Bottle'
    assert result.saved_note is None


@pytest.mark.asyncio
async def test_ambiguous_comment_holds_body_while_selecting_name(client, monkeypatch):
    from backend.app.models import AssistantRequest
    mock_capture(client,monkeypatch,[SimpleNamespace(identity_key='concert-poster',tier='high'),SimpleNamespace(identity_key='favorite-book',tier='high')])
    result=await client.app.state.memories.save(AssistantRequest(message='Add a comment saying meet here at six',request_id='held-ambiguous',author_id='guest'),parsed_content={'body':'meet here at six','title':'Remembered object'})
    assert result.awaiting_name
    assert result.pending_body == 'meet here at six'
    assert result.saved_note is None
    assert 'center' not in result.text.lower()
