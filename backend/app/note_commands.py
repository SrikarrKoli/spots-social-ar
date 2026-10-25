"""Extract spoken note content without allowing a model to invent the memory."""
from __future__ import annotations

import re
from .noun_phrases import noun_parts, comment_tail


VERBS = r"(?:take|save|leave|write(?: down)?|jot(?: down)?|make|create|post|add|record|store)"
NOTE = r"(?:notes?|comments?|memor(?:y|ies))"
COMMAND = rf"(?:\b{VERBS}\s+(?:(?:a|the|this|my|some)\s+)?{NOTE}\b|\bnote that\b)"


def object_title(text: str) -> str:
    return noun_parts(text)[0] or "Remembered object"


def extract_note_content(message: str, history: list[dict], *, followup: bool = False) -> dict[str, str]:
    text = message.strip()
    # A naming clause and a note clause are independent actions in one utterance.
    naming = extract_object_name(text)
    note_start = re.search(COMMAND, text, re.I)
    if naming and note_start:
        text = text[note_start.start():]
    name_comment = explicit_name_comment(text)
    if naming and name_comment and not note_start:
        return {"body": name_comment, "title": naming}
    if naming and not note_start and not re.search(r"\b(?:saying|remember that)\b", text, re.I):
        return {"body": "", "title": naming}
    if followup and not note_start and not re.search(r"\b(?:saying|remember that)\b", text, re.I):
        title, tail = noun_parts(text)
        # A description introduces the noun first, then supplies its comment.
        if re.match(r"^(?:it(?:'s|’s| is)|this is|that is)\b", text, re.I) and title and tail:
            return {"body": comment_tail(tail), "title": title}
        return {"body": text, "title": title or "Remembered object"}
    body = ""
    # Punctuation and command syntax define content; source text remains verbatim.
    saying = re.search(r"\b(?:saying|that says|which says|with text|with the words|to say)\s*[:,-]?\s+(.+)", text, re.I | re.S)
    remember = re.search(r"\bremember\s+(?:that|this)\s*[:,-]?\s+(.+)", text, re.I | re.S)
    command = re.search(COMMAND, text, re.I)
    if saying:
        body = saying.group(1).strip()
        # A question mark commonly closes a polite 'can you ... saying X?' request.
        body = body.split('?', 1)[0].strip()
    elif remember:
        body = remember.group(1).strip()
    elif command:
        suffix = text[command.end():].strip()
        if re.fullmatch(r"[.!?]+", suffix):
            suffix = ""
        if suffix.startswith((':', ',', '-', '—')):
            body = suffix.lstrip(':,-— ').strip()
        elif re.match(r"^(?:that|saying)\s+", suffix, re.I):
            body = re.sub(r"^(?:that|saying)\s+", '', suffix, flags=re.I)
        elif suffix and not re.match(r"^(?:please|for me|on |about |for |of |there|here|on that|on this|on it)[.!?\s]?", suffix, re.I):
            body = suffix
    if not body and command and re.match(r'^(?:about|on|of|for)\s+', suffix, re.I):
        _, tail = noun_parts(suffix)
        if tail:
            body = comment_tail(tail)
    if naming:
        body = re.split(r"(?:[,.]?\s+(?:and|then)\s+|[.;]\s*)(?:please )?(?:name|call|rename|label)\b", body, maxsplit=1, flags=re.I)[0]
    # Remove courteous trailing command language, not any substantive note content.
    body = re.sub(r"\s+(?:for me\s+)?please[.!?]*$", '', body, flags=re.I).strip(' "“”')
    if body:
        return {"body": body, "title": naming or object_title(text)}
    reference = re.search(r"\b(?:on|about|of)\s+(?:that|it|this|them)(?=\s+(?:for me|please)\b|[.!?]|$)|\bsave (?:it|that|this)\b", text, re.I)
    if reference:
        # Resolve 'make the notes on that' to the most recent actual note request.
        for index in range(len(history) - 1, -1, -1):
            item = history[index]
            if item['role'] != 'user':
                continue
            if re.search(COMMAND, item['content'], re.I) or re.search(r'\bremember (?:that|this)\b', item['content'], re.I):
                previous = extract_note_content(item['content'], history[:index])
                if previous['body']:
                    return previous
        if re.search(r'\bsave (?:it|that|this)\b', text, re.I):
            for item in reversed(history):
                if item['role'] == 'assistant':
                    body = re.sub(r'^(?:suggested note|draft|your note)\s*:\s*', '', item['content'], flags=re.I)
                    return {"body": body.strip(' "“”'), "title": object_title(body)}
    return {"body": "", "title": naming or object_title(text)}


def is_rename_request(message: str) -> bool:
    text = message.lower().replace('’', "'")
    if re.search(r"\b(don't|do not|cancel|never)\b", text) or re.match(r'^(?:how|what|why)\b', text) or re.search(r"\b(?:explain|tell me) how\b", text):
        return False
    return bool(re.search(r"\b(?:rename|(?:name|call|label)(?: it| this| that| the| this object)|(?:the |its )name (?:is|should be)|save (?:it|this|that) as)\b", text))


def clean_object_name(text: str) -> str:
    text = re.split(r"\s+(?:and then|and|then)\s+(?=(?:please |also )?(?:take|save|add|leave|write|make|note|say|call|name|rename)\b)|[?!.;]", text, maxsplit=1, flags=re.I)[0]
    return noun_parts(text)[0]


def explicit_name_comment(message: str) -> str:
    match = re.search(r"\b(?:name|call|rename|label)\s+(?:it|this|that|(?:the|this|that) (?:object|bottle|poster|thing))\s+(?:(?:as|to)\s+)?(.+)", message, re.I)
    if not match:
        return ''
    _, tail = noun_parts(match.group(1))
    if re.match(r'^(?:(?:and|then)\s+)?(?:take|add|save|make|leave|write)\b', tail, re.I):
        return ''
    return comment_tail(tail)


def extract_object_name(message: str) -> str:
    patterns = [
        r"\b(?:rename|name|call|label)\s+(?:it|this|that|(?:the|this|that) (?:object|bottle|poster|thing))\s+(.+)",
        r"\b(?:the name|its name)\s+(?:is|should be)\s+(.+)",
        r"\bsave\s+(?:it|this|that)\s+as\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.I)
        if match:
            return clean_object_name(match.group(1))
    return ''


def is_visual_identification(message: str) -> bool:
    return bool(re.search(r"\b(?:what (?:is (?:this|that|it)|are (?:these|those)|am I|do you see)|what[’']s (?:this|that|in)|identify (?:this|that|it)|recogniz(?:e|ing)|describe (?:this|that|the (?:object|room|scene))|see this|see that|looking at|in (?:this|the|my) room|that(?:'s| is) (?:wrong|not)|you(?:'re| are) (?:wrong|guessing))\b", message, re.I))


def is_conversation_turn(text: str) -> bool:
    """Questions and camera/setup chatter must never be treated as note dictation."""
    text = re.sub(r'^(?:(?:okay|ok|hey|so|well|yeah|yes)[,!.]?\s+)+', '', text.strip(), flags=re.I)
    return bool(re.match(r"(?:do you|can you see|did you|are you|is (?:it|this|that)|what|where|when|why|how|tell me|read|show|stop|thank|sounds good|it(?:'s| is) in my frame)\b", text, re.I) or '?' in text)


def clean_comment(text: str) -> str:
    """Remove command framing, not the speaker's actual comment."""
    text = re.sub(r'^(?:(?:okay|ok|hey|so|well)[,!.]?\s+)+', '', text.strip(), flags=re.I)
    text = re.sub(r'^(?:can you |could you |please )?(?:say|saying|write|put|note)(?: that)?\s*[:,-]?\s+', '', text, flags=re.I)
    text = re.split(r"\s+and (?:please )?(?:make sure (?:you )?(?:save|post|add)|(?:save|post) (?:it|that|this)|(?:keep|put) (?:it|that|this) (?:as|in) (?:the |a )?(?:note|comment))\b", text, maxsplit=1, flags=re.I)[0]
    text = re.sub(r'\s+(?:for me\s+)?please[.!?]*$', '', text, flags=re.I)
    text = re.split(r"[.!?]\s+(?:can you see|do you see|it(?:'s| is) in my frame|I(?:'m| am) pointing)\b", text, maxsplit=1, flags=re.I)[0]
    return text.strip(' ,:;“”"')


def is_cancel_request(text: str) -> bool:
    return bool(re.fullmatch(r"(?:okay[, ]+|please )?(?:cancel|never mind|stop(?: listening)?|(?:don't|do not) (?:save|post|delete|change|edit)(?: (?:it|that|this|a|the)(?: (?:note|comment))?)?)[.!?]*", text.strip().replace('’', "'"), re.I))
