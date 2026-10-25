from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.note_commands import is_reply_request, split_reply
from test_memories import mock_capture


POSTER = [SimpleNamespace(identity_key='concert-poster', tier='high')]


def ask(client, message, request_id='reply-test-0001', **extra):
    return client.post('/api/assistant', json={
        'message': message, 'request_id': request_id, 'author_id': 'theo', **extra,
    }).json()


def replies(client, object_id='concert-poster'):
    return client.get(f'/api/objects/{object_id}/posts').json()['posts'][0]['replies']


@pytest.mark.parametrize('text, target, body', [
    ('Reply saying I will bring it back tomorrow', '', 'I will bring it back tomorrow'),
    ('Reply to Vishal: sounds good', 'Vishal', 'sounds good'),
    ('Can you reply to Lina saying see you at six please', 'Lina', 'see you at six'),
    ('Respond, I agree', '', 'I agree'),
    ('Reply', '', ''),
])
def test_split_reply_keeps_spoken_words(text, target, body):
    assert is_reply_request(text)
    assert split_reply(text) == (target, body)


@pytest.mark.parametrize('text', ['Did anyone reply?', "Don't reply", 'What did Vishal reply?'])
def test_questions_about_replies_are_not_replies(text):
    assert not is_reply_request(text)


def test_reply_joins_the_thread_of_the_note_in_view(client, monkeypatch):
    mock_capture(client, monkeypatch, POSTER)
    parser = AsyncMock(side_effect=AssertionError('Replies must not need the LLM parser'))
    monkeypatch.setattr(client.app.state.intent_parser, 'parse', parser)
    before = len(replies(client))

    result = ask(client, 'Reply saying count me in for Friday')

    assert result['saved_note']['body'] == 'count me in for Friday'
    assert result['saved_note']['parent_post_id'] == 1
    assert 'Replied to Vishal on Concert poster' in result['text']
    assert len(replies(client)) == before + 1
    assert replies(client)[-1]['body'] == 'count me in for Friday'
    parser.assert_not_awaited()


def test_named_reply_finds_that_persons_thread(client, monkeypatch):
    mock_capture(client, monkeypatch, POSTER)
    # Lina's note lives on the book; naming her targets it even while the poster is selected.
    monkeypatch.setattr(client.app.state.camera, 'memory_capture', lambda: None)
    result = ask(client, 'Reply to Lina: chapter two was the best part', object_id='favorite-book')
    assert result['saved_note']['parent_post_id'] == 3
    assert result['saved_object']['id'] == 'favorite-book'


def test_bare_reply_asks_once_then_posts_the_next_sentence(client, monkeypatch):
    mock_capture(client, monkeypatch, POSTER)
    first = ask(client, 'Reply')
    assert first['awaiting_reply'] is True
    assert first['pending_reply_to'] == 1
    assert first['saved_note'] is None
    assert first['text'] == "What's your reply to Vishal?"

    second = ask(client, 'I can drive us there', 'reply-test-0002',
                 awaiting_reply=True, pending_reply_to=first['pending_reply_to'])
    assert second['saved_note']['body'] == 'I can drive us there'
    assert second['saved_note']['parent_post_id'] == 1
    assert second['awaiting_reply'] is False


def test_reply_is_idempotent_on_retry(client, monkeypatch):
    mock_capture(client, monkeypatch, POSTER)
    first = ask(client, 'Reply saying see you there')
    again = ask(client, 'Reply saying see you there')
    assert first['saved_note']['id'] == again['saved_note']['id']


def test_reply_needs_a_note_and_an_object_and_never_guesses(client, monkeypatch):
    mock_capture(client, monkeypatch, [])
    nothing = ask(client, 'Reply saying hello')
    assert nothing['saved_note'] is None
    assert 'Look at the object' in nothing['text']

    mock_capture(client, monkeypatch, POSTER)
    stranger = ask(client, 'Reply to Bob: hello', 'reply-test-0003')
    assert stranger['saved_note'] is None
    assert "couldn't find a note from Bob" in stranger['text']
