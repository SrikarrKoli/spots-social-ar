import pytest
from backend.app.note_commands import extract_note_content, extract_object_name, object_title


@pytest.mark.parametrize('utterance,title,comment', [
    ("It's a blue water bottle by LinkedIn and say it looks really nice.", 'Blue water bottle', 'by LinkedIn. It looks really nice.'),
    ("It's a red jersey and say it looks great.", 'Red jersey', 'it looks great.'),
    ('This is a poster of my friend.', 'Poster', 'of my friend.'),
])
def test_spoken_description_separates_noun_phrase_from_comment(utterance, title, comment):
    assert extract_note_content(utterance, [], followup=True) == {'title': title, 'body': comment}


def test_request_words_never_become_title_even_in_naming_followup():
    from backend.app.note_commands import clean_object_name
    phrase = 'Can you make a note about this jersey right here'
    assert clean_object_name(phrase) == 'Jersey'
    assert object_title(phrase) == 'Jersey'
    assert extract_note_content(phrase, [], followup=True) == {'title': 'Jersey', 'body': ''}


def test_named_object_followed_by_spoken_comment():
    phrase = 'Call it blue water bottle by LinkedIn and say it looks really nice.'
    assert extract_object_name(phrase) == 'Blue water bottle'
    assert extract_note_content(phrase, []) == {'title': 'Blue water bottle', 'body': 'by LinkedIn. It looks really nice.'}
