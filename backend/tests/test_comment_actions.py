from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock
from test_memories import mock_capture, payload


def setup_visible(client, monkeypatch):
    mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high')])
    monkeypatch.setattr(client.app.state.camera, 'assistant_frame', lambda: (b'jpeg', datetime.now(UTC)))
    answer = AsyncMock(return_value='Yes, I can see it.')
    monkeypatch.setattr(client.app.state.assistant, 'answer', answer)
    return answer


def test_fridge_question_is_not_saved_even_during_note_dictation(client, monkeypatch):
    setup_visible(client, monkeypatch)
    before = client.get('/api/objects/concert-poster/posts').json()
    result = client.post('/api/assistant', json=payload(message="Okay, do you see this fridge? It's in my frame.", awaiting_note=True)).json()
    assert result['saved_note'] is None
    assert client.get('/api/objects/concert-poster/posts').json() == before


def test_read_past_comments_uses_database_and_never_creates_a_comment(client, monkeypatch):
    answer = setup_visible(client, monkeypatch)
    before = client.get('/api/objects/concert-poster/posts').json()
    result = client.post('/api/assistant', json=payload(message='Read aloud the past comments on this object', awaiting_note=True)).json()
    assert result['read_aloud'] is True
    assert 'Anyone want to go Friday?' in result['text']
    assert 'Yes — I can grab the tickets.' in result['text']
    assert result['saved_note'] is None
    answer.assert_not_awaited()
    assert client.get('/api/objects/concert-poster/posts').json() == before


def test_edit_last_note_updates_same_post_preserves_replies_and_retry(client, monkeypatch):
    setup_visible(client, monkeypatch)
    data = payload('edit-friday-0001', message='Change my last comment to say I am going Saturday.', author_id='maya', last_note_id=1)
    first = client.post('/api/assistant', json=data).json()
    assert first['saved_note']['id'] == 1
    assert first['saved_note']['body'] == 'I am going Saturday.'
    assert first['memory_changed']
    thread = client.get('/api/objects/concert-poster/posts').json()
    assert len(thread['posts']) == 1 and len(thread['posts'][0]['replies']) == 1
    assert client.post('/api/assistant', json=data).json()['saved_note']['id'] == 1
    with client.app.state.repository.database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM note_edits').fetchone()[0] == 1
    assert client.app.state.repository.recognition_context(['concert-poster'])['concert-poster'][1].body == 'I am going Saturday.'


def test_edit_can_ask_for_replacement_without_capturing_the_instruction(client, monkeypatch):
    setup_visible(client, monkeypatch)
    first = client.post('/api/assistant', json=payload(message='Edit my comment', author_id='maya')).json()
    assert first['pending_edit_ids'] == [1]
    second = client.post('/api/assistant', json=payload('edit-followup-001', message='Please say I am going Saturday.', author_id='maya', pending_edit_ids=first['pending_edit_ids'])).json()
    assert second['saved_note']['body'] == 'I am going Saturday.'


def test_multiple_comments_ask_which_one_and_hold_replacement(client, monkeypatch):
    setup_visible(client, monkeypatch)
    extra = client.post('/api/assistant', json=payload(author_id='maya')).json()['saved_note']
    first = client.post('/api/assistant', json=payload(message='Change my comment to say See you Saturday.', author_id='maya')).json()
    assert first['pending_edit_ids'] == [1, extra['id']]
    assert first['pending_edit_body'] == 'See you Saturday.'
    second = client.post('/api/assistant', json=payload('edit-choice-0001', message='second one', author_id='maya', pending_edit_ids=first['pending_edit_ids'], pending_edit_body=first['pending_edit_body'])).json()
    assert second['saved_note']['id'] == extra['id']
    assert second['saved_note']['body'] == 'See you Saturday.'


def test_comment_cleanup_excludes_request_framing_and_trailing_camera_chatter():
    from backend.app.note_commands import clean_comment, extract_note_content
    assert clean_comment('Okay, please say I bought it yesterday. Can you see it?') == 'I bought it yesterday'
    parsed = extract_note_content('Add a comment on this fridge saying I bought it yesterday and make sure you save it.', [])
    assert clean_comment(parsed['body']) == 'I bought it yesterday'


def test_naming_new_object_does_not_invent_a_comment(client, monkeypatch):
    mock_capture(client, monkeypatch)
    result = client.post('/api/assistant', json=payload(message='Name it blue water bottle')).json()
    assert result['saved_object']['title'] == 'Blue water bottle'
    assert result['saved_note'] is None
    assert client.get('/api/objects/' + result['saved_object']['id'] + '/posts').json()['posts'] == []


def test_question_during_edit_and_name_prompt_cannot_write(client, monkeypatch):
    setup_visible(client, monkeypatch)
    before = client.get('/api/objects/concert-poster/posts').json()
    for extra in [{'pending_edit_ids': [1]}, {'awaiting_name': True, 'pending_body': 'Buy milk.'}]:
        result = client.post('/api/assistant', json=payload(message='Do you see this fridge?', author_id='maya', **extra)).json()
        assert result['saved_note'] is None
    assert client.get('/api/objects/concert-poster/posts').json() == before
