from types import SimpleNamespace
from backend.app.note_deletion import is_delete_request
from test_memories import mock_capture, payload


def test_voice_delete_hides_note_in_thread_preview_and_undo_restores(client, monkeypatch):
    mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high')])
    saved = client.post('/api/assistant', json=payload()).json()['saved_note']
    result = client.post('/api/assistant', json=payload('delete-request-001', message='Delete that note', last_note_id=saved['id'])).json()
    assert result['deleted_note_ids'] == [saved['id']]
    assert saved['id'] not in [post['id'] for post in client.get('/api/objects/concert-poster/posts').json()['posts']]
    context = client.app.state.repository.recognition_context(['concert-poster'])
    assert context['concert-poster'][1].body != saved['body']
    # Retrying a deletion never deletes a different note.
    retry = client.post('/api/assistant', json=payload('delete-request-001', message='Delete that note', last_note_id=saved['id'])).json()
    assert retry['deleted_note_ids'] == [saved['id']]
    restored = client.post('/api/assistant', json=payload(message='undo', deletion_id=result['deletion_id'])).json()
    assert restored['memory_changed']
    assert saved['id'] in [post['id'] for post in client.get('/api/objects/concert-poster/posts').json()['posts']]


def test_ambiguous_delete_asks_which_note_then_accepts_ordinal(client, monkeypatch):
    mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high')])
    saved = client.post('/api/assistant', json=payload(author_id='maya')).json()['saved_note']
    first = client.post('/api/assistant', json=payload('choose-delete-001', message='Delete a note on the concert poster', author_id='maya')).json()
    assert first['pending_delete_ids'] == [1, saved['id']]
    assert first['deleted_note_ids'] == []
    second = client.post('/api/assistant', json=payload('choose-delete-002', message='the second one', pending_delete_ids=first['pending_delete_ids'], author_id='maya')).json()
    assert second['deleted_note_ids'] == [saved['id']]


def test_delete_by_text_and_cancel_and_negative_requests(client, monkeypatch):
    mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high')])
    saved = client.post('/api/assistant', json=payload()).json()['saved_note']
    result = client.post('/api/assistant', json=payload('delete-text-001', message='Remove the note saying This TV has great picture quality.')).json()
    assert result['deleted_note_ids'] == [saved['id']]
    cancelled = client.post('/api/assistant', json=payload(message='cancel', pending_delete_ids=[1])).json()
    assert not cancelled['memory_changed']
    assert not is_delete_request("Don't delete that note")
    assert not is_delete_request('How do I delete a note?')


def test_delete_root_with_replies_and_restore_survives_database_reopen(client, monkeypatch):
    mock_capture(client, monkeypatch, [SimpleNamespace(identity_key='concert-poster', tier='high')])
    result = client.post('/api/assistant', json=payload('delete-root-001', message='Delete all notes for the concert poster', author_id='maya')).json()
    assert set(result['deleted_note_ids']) == {1, 2}
    assert client.get('/api/objects/concert-poster/posts').json()['posts'] == []
    from backend.app.repositories import Repository
    from backend.app.database import Database
    repo = Repository(Database(client.app.state.settings.database_path))
    assert repo.thread('concert-poster').posts == []
    assert repo.undo_note_deletion('guest', result['deletion_id']) is None
    assert repo.undo_note_deletion('guest', None) is None
    assert repo.undo_note_deletion('maya', result['deletion_id']) is not None
    assert len(repo.thread('concert-poster').posts[0].replies) == 1
