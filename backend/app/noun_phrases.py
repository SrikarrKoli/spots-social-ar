"""Separate a concrete noun phrase from the rest of a spoken utterance.

The local English dependency parser supplies word boundaries; titles are always
copied from the transcript, never generated from the camera image.
"""
from functools import lru_cache
import re
import threading

_lock = threading.Lock()
_META_NOUNS = {'note', 'notes', 'comment', 'comments', 'memory', 'memories', 'name', 'tab', 'request'}


@lru_cache(maxsize=1)
def _pipeline():
    import spacy
    return spacy.load('en_core_web_sm', disable=['ner', 'lemmatizer'])


def noun_parts(text: str) -> tuple[str, str]:
    text = text.strip(' :,-“”"')
    if not text or text.startswith('Remembered object'):
        return '', ''
    with _lock:
        doc = _pipeline()(text)
    for chunk in doc.noun_chunks:
        if chunk.root.pos_ not in {'NOUN', 'PROPN'} or chunk.root.text.lower() in _META_NOUNS:
            continue
        tokens = list(chunk)
        while tokens and (tokens[0].pos_ == 'DET' or tokens[0].lower_ in {'my', 'your', 'our'}):
            tokens.pop(0)
        if not tokens:
            continue
        name = text[tokens[0].idx:chunk.end_char].strip()
        # Locative filler is not an object name or meaningful comment.
        tail = text[chunk.end_char:].strip().lstrip(' ,:;.-')
        tail = re.sub(r'^(?:right\s+)?(?:here|there)\b[,.]?\s*', '', tail, flags=re.I)
        tail = re.sub(r'^(?:please|for me)[.!?]*$', '', tail, flags=re.I)
        return (name[:1].upper() + name[1:]) if len(name) <= 80 else '', tail
    return '', ''


def comment_tail(text: str) -> str:
    """Drop spoken command glue while preserving the actual words of the comment."""
    text = re.sub(r'^(?:and\s+)?(?:please\s+)?(?:say(?:ing)?|note that|remember that)\s+', '', text, flags=re.I)
    text = re.sub(r'\s+and\s+(?:please\s+)?say\s+', '. ', text, flags=re.I)
    text = re.sub(r'\s+(?:for me\s+)?please[.!?]*$', '', text, flags=re.I)
    text = re.sub(r'([.!?]\s+)([a-z])', lambda match: match.group(1) + match.group(2).upper(), text)
    return text.strip(' ,:;“”"')
