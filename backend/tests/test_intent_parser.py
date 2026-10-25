from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.models import AssistantRequest
from backend.app.intent_parser import IntentParser, ParsedIntent, validate_grounding
from backend.app.assistant import AssistantError
from conftest import make_test_settings
from test_memories import mock_capture, payload


def test_parser_replaces_invented_comment_and_name_with_spoken_words():
    request = AssistantRequest(message='Delete that note')
    assert validate_grounding(ParsedIntent(action='delete_comment', action_phrase='Delete', selector='all'), request, []).selector == 'last'
    request = AssistantRequest(message='Take a note saying It looks nice.')
    reworded = validate_grounding(ParsedIntent(action='add_comment', action_phrase='Take a note', comment_spans=['It is a Samsung TV.']), request, [])
    assert reworded.comment_spans == ['It looks nice.']
    invented = validate_grounding(ParsedIntent(action='add_comment', object_name='Samsung TV', action_phrase='Take a note', comment_spans=['It looks nice.']), request, [])
    assert invented.object_name == ''
    assert invented.comment_spans == ['It looks nice.']


def test_camera_question_cannot_become_note_even_if_model_misclassifies():
    request = AssistantRequest(message="Okay, do you see this fridge? It's in my frame.", awaiting_note=True)
    parsed = validate_grounding(ParsedIntent(action='add_comment', comment_spans=[request.message]), request, [])
    assert parsed.action == 'chat'


@pytest.mark.asyncio
async def test_schema_request_is_text_only_and_response_is_validated(monkeypatch):
    original = httpx.AsyncClient
    def handler(request):
        data = json.loads(request.content)
        assert data['format']['properties']['action']['enum']
        assert data['options']['temperature'] == 0
        assert all('images' not in message for message in data['messages'])
        return httpx.Response(200, json={'message': {'content': json.dumps({'action': 'add_comment', 'action_phrase': 'jot down', 'comment_spans': ['I bought it yesterday']})}})
    monkeypatch.setattr('backend.app.intent_parser.httpx.AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler)))
    parsed = await IntentParser('http://local', 'test').parse(AssistantRequest(message='Could you jot down that I bought it yesterday'), [])
    assert parsed.comment_spans == ['I bought it yesterday']


@pytest.fixture
def llm_client(database_path):
    with TestClient(create_app(replace(make_test_settings(database_path), llm_parser_enabled=True))) as client:
        yield client


def test_llm_drives_unusual_save_and_existing_write_handlers(llm_client, monkeypatch):
    extraction = mock_capture(llm_client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high')])
    parser = AsyncMock(return_value=ParsedIntent(action='add_comment', comment_spans=['I bought it yesterday']))
    monkeypatch.setattr(llm_client.app.state.intent_parser, 'parse', parser)
    response = llm_client.post('/api/assistant', json=payload(message='Could you jot this down for me, I bought it yesterday')).json()
    assert response['saved_note']['body'] == 'I bought it yesterday'
    extraction.assert_not_awaited()
    assert llm_client.get('/api/health').json()['llm_parser_enabled'] is True


def test_llm_chat_never_falls_through_to_legacy_save_rules(llm_client, monkeypatch):
    mock_capture(llm_client, monkeypatch)
    monkeypatch.setattr(llm_client.app.state.intent_parser, 'parse', AsyncMock(return_value=ParsedIntent(action='chat')))
    monkeypatch.setattr(llm_client.app.state.camera, 'assistant_frame', lambda: (b'jpeg', datetime.now(UTC)))
    monkeypatch.setattr(llm_client.app.state.assistant, 'answer', AsyncMock(return_value='I can help with that.'))
    before = len(llm_client.app.state.repository.thread('concert-poster').posts)
    response = llm_client.post('/api/assistant', json=payload(message='Do you understand what I mean when I say take a note?', awaiting_note=True)).json()
    assert response['saved_note'] is None
    assert len(llm_client.app.state.repository.thread('concert-poster').posts) == before


def test_llm_failure_asks_to_repeat_without_writes(llm_client, monkeypatch):
    monkeypatch.setattr(llm_client.app.state.intent_parser, 'parse', AsyncMock(side_effect=AssistantError('Please repeat. Nothing was changed.')))
    before = llm_client.get('/api/objects/concert-poster/posts').json()
    response = llm_client.post('/api/assistant', json=payload(message='What about the other one')).json()
    assert response['text'] == 'Please repeat. Nothing was changed.'
    assert response['saved_note'] is None
    assert llm_client.get('/api/objects/concert-poster/posts').json() == before


def test_numbered_followup_is_bound_to_actual_spoken_selection_and_pending_action():
    request = AssistantRequest(message='the second one', pending_edit_ids=[1, 2], pending_edit_body='Bought last week.')
    result = validate_grounding(ParsedIntent(action='edit_comment', action_phrase='edit', selector='number', number=2, comment_spans=['Bought last week.']), request, [])
    assert result.number == 2
    assert validate_grounding(ParsedIntent(action='edit_comment', selector='number', number=1), request, []).number == 2
    with pytest.raises(AssistantError):
        validate_grounding(ParsedIntent(action='delete_comment', selector='number', number=2), request, [])


def test_unspecified_delete_cannot_be_promoted_to_last():
    request = AssistantRequest(message='Delete a note')
    result = validate_grounding(ParsedIntent(action='delete_comment', action_phrase='Delete', selector='last'), request, [])
    assert result.selector == 'unspecified'


def test_llm_edit_dispatch_updates_existing_comment(llm_client, monkeypatch):
    mock_capture(llm_client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high')])
    monkeypatch.setattr(llm_client.app.state.intent_parser, 'parse', AsyncMock(return_value=ParsedIntent(action='edit_comment', comment_spans=['Going Saturday.'], selector='last')))
    result = llm_client.post('/api/assistant', json=payload(message='No I meant going Saturday.', last_note_id=1, author_id='maya')).json()
    assert result['saved_note']['id'] == 1
    assert result['saved_note']['body'] == 'Going Saturday.'
    assert len(llm_client.app.state.repository.thread('concert-poster').posts[0].replies) == 1


def test_llm_read_does_not_force_audio_unless_asked(llm_client, monkeypatch):
    mock_capture(llm_client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high')])
    monkeypatch.setattr(llm_client.app.state.intent_parser, 'parse', AsyncMock(return_value=ParsedIntent(action='read_comments')))
    result = llm_client.post('/api/assistant', json=payload(message='What did people leave here before?')).json()
    assert 'Anyone want to go Friday?' in result['text']
    assert not result['read_aloud']


def test_llm_cannot_save_bare_object_request_as_a_comment():
    request = AssistantRequest(message='Can you make a note about this jersey right here')
    parsed = validate_grounding(ParsedIntent(action='add_comment', object_name='jersey', action_phrase='make a note', comment_spans=['this jersey right here']), request, [])
    assert parsed.comment_spans == []
    assert parsed.object_name == 'jersey'


def test_llm_description_name_is_grounded_when_model_omits_name():
    request = AssistantRequest(message="It's a fridge.", awaiting_description=True)
    result = validate_grounding(ParsedIntent(action='describe_object'), request, [])
    assert result.object_name == 'Fridge'
