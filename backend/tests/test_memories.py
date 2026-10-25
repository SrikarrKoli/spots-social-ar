import asyncio
from dataclasses import replace
from datetime import datetime, UTC
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import cv2
import numpy as np
from fastapi.testclient import TestClient
import pytest

from backend.app.main import create_app
from backend.app.memories import is_note_request
from backend.app.recognition import InstanceRecognizer
from conftest import make_test_settings


@pytest.mark.parametrize('text', [
    'Take a note: this TV is great quality.',
    'Can you please leave a note about the TV saying it is great quality?',
    'Can you use the spots notes tab and make the notes on that for me please?',
    'Remember that my keys are inside this drawer.',
    'Save a memory of this poster: concert is Friday.',
])
def test_explicit_note_commands(text):
    assert is_note_request(text)


@pytest.mark.parametrize('text', [
    'What do you see?', 'How do I take a note?', 'What notes did I save?',
    'Do not save a note', "Don't take a note", 'Explain the note on the book',
])
def test_questions_and_cancellation_are_not_save_commands(text):
    assert not is_note_request(text)


def mock_capture(client, monkeypatch, matches=()):
    frame = cv2.imread(str(Path(__file__).parents[2] / 'objects/concert-poster.png'))
    now = datetime.now(UTC)
    monkeypatch.setattr(client.app.state.camera, 'memory_capture', lambda: (frame, now, list(matches)))
    extraction = AsyncMock(return_value={'body': 'This TV has great picture quality.', 'title': 'TV'})
    monkeypatch.setattr(client.app.state.assistant, 'extract_note', extraction)
    return extraction


def payload(request_id='memory-test-0001', **extra):
    return {'message': 'Take a note: this TV has great picture quality.', 'request_id': request_id,
            'author_id': 'guest', **extra}


def test_save_new_object_note_and_recover_after_restart(client, database_path, monkeypatch):
    extraction = mock_capture(client, monkeypatch)
    result = client.post('/api/assistant', json=payload())
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['saved_note']['body'] == 'This TV has great picture quality.'
    object_id = data['saved_object']['id']
    assert object_id.startswith('memory-')
    assert 'Saved to TV' in data['text']
    refs = client.app.state.repository.object_reference_paths(object_id)
    assert len(refs) == 1 and Path(refs[0]).exists()
    # No repeated enrollment/extraction, even if the camera is disconnected on retry.
    monkeypatch.setattr(client.app.state.camera, 'memory_capture', lambda: None)
    repeated = client.post('/api/assistant', json=payload()).json()
    assert repeated['saved_note']['id'] == data['saved_note']['id']
    assert extraction.await_count == 1
    with TestClient(create_app(make_test_settings(database_path))) as restarted:
        thread = restarted.get(f'/api/objects/{object_id}/posts').json()
        assert [post['body'] for post in thread['posts']] == ['This TV has great picture quality.']
        # Reloaded image fingerprint still recognizes the saved object.
        matcher = InstanceRecognizer()
        matcher.load_references([(object_id, Path(refs[0]))])
        detections = matcher.detect(cv2.imread(refs[0]))
        assert any(item.identity_key == object_id and item.tier == 'high' for item in detections)


def test_existing_visible_object_wins_over_stale_selected_thread(client, monkeypatch):
    mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high')])
    response = client.post('/api/assistant', json=payload(object_id='favorite-book')).json()
    assert response['saved_object']['id'] == 'concert-poster'
    assert response['saved_note']['object_id'] == 'concert-poster'
    assert len(client.get('/api/objects').json()) == 2


def test_missing_note_content_asks_followup_and_saves_next_turn(client, monkeypatch):
    extraction = mock_capture(client, monkeypatch)
    extraction.return_value = {'body': '', 'title': 'TV'}
    first = client.post('/api/assistant', json=payload(message='Take a note')).json()
    assert first['awaiting_note'] is True
    assert first['saved_note'] is None
    assert len(client.get('/api/objects').json()) == 2
    extraction.return_value = {'body': 'Great picture quality.', 'title': 'TV'}
    second = client.post('/api/assistant', json=payload('memory-followup-2', message='Great picture quality.', awaiting_note=True, pending_title=first['pending_title'])).json()
    assert second['saved_note']['body'] == 'Great picture quality.'
    assert second['awaiting_note'] is False


def test_uncertain_and_multiple_objects_never_attach_a_note(client, monkeypatch):
    extraction = mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='provisional')])
    assert client.post('/api/assistant', json=payload()).status_code == 409
    extraction.assert_not_awaited()
    mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high'), SimpleNamespace(identity_key='favorite-book', tier='high')])
    assert client.post('/api/assistant', json=payload()).status_code == 409
    assert len(client.get('/api/objects').json()) == 2


def test_no_camera_no_memory_and_no_accidental_text_only_save(client, monkeypatch):
    monkeypatch.setattr(client.app.state.camera, 'memory_capture', lambda: None)
    assert client.post('/api/assistant', json=payload()).status_code == 503
    assert client.post('/api/assistant', json=payload(include_camera=False)).status_code == 422
    assert len(client.get('/api/objects').json()) == 2


def test_memory_transaction_rollback_removes_enrollment(client, monkeypatch):
    mock_capture(client, monkeypatch)
    def fail(**kwargs):
        raise RuntimeError('Disk full')
    monkeypatch.setattr(client.app.state.repository, 'save_memory', fail)
    with pytest.raises(RuntimeError, match='Disk full'):
        client.post('/api/assistant', json=payload())
    assert not list(client.app.state.settings.enrolled_dir.glob('memory-*'))
    assert len(client.get('/api/objects').json()) == 2


def test_pending_note_cancellation_does_not_save(client):
    response = client.post('/api/assistant', json=payload(message='cancel', awaiting_note=True)).json()
    assert response['awaiting_note'] is False
    assert response['saved_note'] is None


def test_actual_spoken_followup_recovers_tv_note_without_visual_hallucination():
    from backend.app.note_commands import extract_note_content
    history = [
        {'role': 'user', 'content': "Can you please leave a note about the TV saying it's great quality? It's only looking at the TV."},
        {'role': 'assistant', 'content': 'I cannot write notes.'},
    ]
    result = extract_note_content('Can you use the spots notes tab and make the notes on that for me please?', history)
    assert result == {'body': "it's great quality", 'title': 'TV'}
    assert extract_note_content('Take a note', history)['body'] == ''
    assert extract_note_content('take a note: this TV has great picture quality.', [])['body'] == 'this TV has great picture quality.'
    assert extract_note_content('Take a note that the concert is on Friday.', [])['body'] == 'the concert is on Friday.'
    assert extract_note_content('Remember that I left my keys here.', [])['body'] == 'I left my keys here.'


def test_bare_note_punctuation_and_new_object_reference_do_not_copy_old_note():
    from backend.app.note_commands import extract_note_content
    history = [{'role': 'user', 'content': 'Take a note: the concert is Friday.'}]
    assert extract_note_content('Take a note.', history)['body'] == ''
    assert extract_note_content('Take a note of this TV.', history)['body'] == ''


def test_rename_persists_and_does_not_change_notes(client, monkeypatch):
    from backend.app.note_commands import is_rename_request, extract_object_name
    assert is_rename_request('Can you name it as a Dinnie poster?')
    assert not is_rename_request("Don't rename this to anything")
    assert extract_object_name('Rename this to Dinnie poster please.') == 'Dinnie poster'
    mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high')])
    before = client.get('/api/objects/concert-poster/posts').json()['posts']
    result = client.post('/api/assistant', json=payload(message='Rename this to Dinnie poster.'))
    assert result.status_code == 200, result.text
    assert result.json()['saved_object']['title'] == 'Dinnie poster'
    after = client.get('/api/objects/concert-poster/posts').json()
    assert after['object']['title'] == 'Dinnie poster'
    assert after['posts'] == before
    mock_capture(client, monkeypatch, [])
    new = client.post('/api/assistant', json=payload(message='Name this Lamp.')).json()
    assert new['saved_object']['title'] == 'Lamp'


@pytest.mark.parametrize('message', [
    'Name it blue water bottle and take a note: it looks really nice.',
    'Can you call this a blue water bottle and add a comment saying it looks really nice.',
    'Take a note: it looks really nice. And name it blue water bottle.',
    'Please label it blue water bottle then note that it looks really nice.',
])
def test_natural_combined_name_and_note(message):
    from backend.app.note_commands import extract_note_content, extract_object_name
    assert extract_object_name(message) == 'Blue water bottle'
    parsed = extract_note_content(message, [])
    assert parsed['title'] == 'Blue water bottle'
    assert parsed['body'].rstrip('.') == 'it looks really nice'
    assert is_note_request(message)


def test_named_note_followup_retains_name_and_never_generates_number(client, monkeypatch):
    mock_capture(client, monkeypatch)
    # Use the real extraction so command handling is tested end to end.
    from backend.app.assistant import LocalAssistant
    monkeypatch.setattr(client.app.state.assistant, 'extract_note', LocalAssistant.extract_note.__get__(client.app.state.assistant))
    first = client.post('/api/assistant', json=payload(message='Name it blue water bottle and take a note.')).json()
    assert first['awaiting_note'] and first['pending_title'] == 'Blue water bottle'
    second = client.post('/api/assistant', json=payload('named-note-followup', message='It looks really nice.', awaiting_note=True, pending_title=first['pending_title'])).json()
    assert second['saved_object']['title'] == 'Blue water bottle'
    assert second['saved_note']['body'] == 'It looks really nice.'


def test_unnamed_note_holds_content_then_saves_with_spoken_name(client, monkeypatch):
    mock_capture(client, monkeypatch)
    from backend.app.assistant import LocalAssistant
    monkeypatch.setattr(client.app.state.assistant, 'extract_note', LocalAssistant.extract_note.__get__(client.app.state.assistant))
    first = client.post('/api/assistant', json=payload(message='Take a note: it looks really nice.')).json()
    assert first['awaiting_name'] and first['pending_body'] == 'it looks really nice.'
    assert first['saved_note'] is None
    second = client.post('/api/assistant', json=payload('name-after-note-001', message='Blue water bottle', awaiting_name=True, pending_body=first['pending_body'])).json()
    assert second['saved_object']['title'] == 'Blue water bottle'
    assert second['saved_note']['body'] == 'it looks really nice.'


def test_combined_rename_note_is_atomic_and_attaches_current_object(client, monkeypatch):
    mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high')])
    from backend.app.assistant import LocalAssistant
    monkeypatch.setattr(client.app.state.assistant, 'extract_note', LocalAssistant.extract_note.__get__(client.app.state.assistant))
    result = client.post('/api/assistant', json=payload(message='Call it blue water bottle and add a comment saying it looks really nice.')).json()
    assert result['saved_object']['id'] == 'concert-poster'
    assert result['saved_object']['title'] == 'Blue water bottle'
    assert result['saved_note']['body'] == 'it looks really nice.'
