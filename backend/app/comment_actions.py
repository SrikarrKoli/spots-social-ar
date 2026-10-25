"""Read stored comments verbatim and edit a chosen comment without model claims."""
import asyncio
import re
from fastapi import HTTPException
from .models import AssistantResponse
from .note_commands import clean_comment
from .note_deletion import words


def is_read_request(text):
    return bool(re.search(r'\b(?:notes?|comments?|threads?|memories)\b', text, re.I) and
        re.search(r'\b(?:read|hear|tell|show|what|any|previous|past|before|left|saved)\b', text, re.I) and
        not re.search(r'\b(?:add|save|take|delete|remove|change|edit|update)\b', text, re.I))


def is_edit_request(text):
    return bool(re.search(r'\b(?:change|edit|update|correct|replace|adjust|rewrite|fix)\b.{0,80}\b(?:note|comment|it|that)\b', text, re.I) and
        not re.search(r"\b(?:don't|do not|never|how do|how can)\b", text.replace('’', "'"), re.I))


def flattened(thread):
    return [post for root in thread.posts for post in [root, *root.replies]]


async def resolve_object(service, payload, pending_ids=(), last=False):
    repo = service.repository
    if pending_ids or (last and payload.last_note_id):
        ids = pending_ids or [payload.last_note_id]
        with repo.database.connect() as connection:
            marks = ','.join('?' for _ in ids)
            rows = connection.execute(f'SELECT DISTINCT object_id FROM active_posts WHERE id IN ({marks})', ids).fetchall()
        return repo.object_by_id(rows[0]['object_id']) if len(rows) == 1 else None
    named = [obj for obj in repo.objects() if words(obj.title) in words(payload.message)]
    if len(named) == 1:
        return named[0]
    capture = await asyncio.to_thread(service.camera.memory_capture) if payload.include_camera else None
    matches = capture[2] if capture else []
    if len(matches) == 1 and matches[0].tier == 'high':
        obj = repo.object_by_identity(matches[0].identity_key)
        if not named or any(obj and item.id == obj.id for item in named):
            return obj
    if not named and payload.object_id and not payload.include_camera:
        return repo.object_by_id(payload.object_id)
    return None


def response(service, text, **extra):
    return AssistantResponse(text=text, model=service.assistant.model,
        camera_used=False, camera_source=service.camera.source, **extra)


async def read_comments(service, payload):
    obj = await resolve_object(service, payload)
    if not obj:
        return response(service, 'Which object? Say its saved name or point at one saved object.')
    notes = flattened(await asyncio.to_thread(service.repository.thread, obj.id))
    aloud = bool(re.search(r'\b(?:read|aloud|hear|speak)\b', payload.message, re.I))
    if not notes:
        return response(service, f'There are no saved comments on {obj.title}.', read_aloud=aloud)
    entries = [f'{index+1}. {post.author.display_name}: “{post.body}”' for index, post in enumerate(notes)]
    return response(service, f'{len(notes)} saved comments on {obj.title}:\n' + '\n'.join(entries), read_aloud=aloud)


def replacement(text):
    match = re.search(r'\b(?:to say|so it says|to read|with|to)\s*[:,-]?\s+["“]?(.+)', text, re.I | re.S)
    return clean_comment(match.group(1)) if match else ''


async def edit_comment(service, payload):
    body = payload.pending_edit_body or replacement(payload.message)
    last = bool(re.search(r'\b(?:that|last|just)\b', payload.message, re.I))
    obj = await resolve_object(service, payload, payload.pending_edit_ids, last=last)
    if obj is None:
        return response(service, 'Which object’s comment should I change? Say its saved name or point at it.')
    notes = [post for post in flattened(service.repository.thread(obj.id)) if post.author.id == payload.author_id]
    if payload.pending_edit_ids:
        notes = [post for post in notes if post.id in payload.pending_edit_ids]
    chosen = None
    if payload.pending_edit_ids and len(notes) == 1:
        chosen = notes[0]
        if not body:
            body = clean_comment(payload.message)
    elif last and notes:
        chosen = next((post for post in notes if post.id == payload.last_note_id), None) or (notes[-1] if re.search(r'\blast\b', payload.message, re.I) else None)
    if chosen is None:
        quoted = re.search(r"\b(?:saying|that says|containing)\s+[\"“]?(.+?)\s+to(?: say)?\s+", payload.message, re.I)
        if quoted:
            matches = [post for post in notes if words(quoted.group(1)) in words(post.body)]
            chosen = matches[0] if len(matches) == 1 else None
    if chosen is None:
        ordinal = re.search(r'\b(first|second|third|fourth|fifth|\d+)\b', payload.message, re.I)
        if ordinal:
            value = ordinal.group(1).lower()
            index = {'first': 0, 'second': 1, 'third': 2, 'fourth': 3, 'fifth': 4}.get(value)
            index = int(value)-1 if index is None else index
            chosen = notes[index] if 0 <= index < len(notes) else None
        elif len(notes) == 1:
            chosen = notes[0]
    if chosen is None:
        if not notes:
            return response(service, f'There are no comments from your current profile to edit on {obj.title}.')
        choices = '\n'.join(f'{index+1}. {post.body}' for index, post in enumerate(notes))
        return response(service, f'Which comment on {obj.title} should I change? Say its number.\n{choices}',
            pending_edit_ids=[post.id for post in notes], pending_edit_body=body)
    if not body:
        return response(service, 'What should that comment say instead?', pending_edit_ids=[chosen.id])
    if len(body) > 500:
        raise HTTPException(422, 'Keep the replacement comment under 500 characters. Nothing was changed.')
    if not payload.request_id:
        raise HTTPException(422, 'A request ID is required to edit a comment safely.')
    try:
        note = await asyncio.to_thread(service.repository.edit_note, chosen.id, payload.author_id, body, 'edit:' + payload.request_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return response(service, f'Updated the comment on {obj.title} to: “{note.body}”', saved_note=note,
        saved_object=obj, memory_changed=True)
