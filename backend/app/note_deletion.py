"""Resolve spoken deletions against saved notes, with durable undo."""
import asyncio
import json
import re
from fastapi import HTTPException
from .models import AssistantResponse


def is_delete_request(text: str) -> bool:
    text = text.replace("’", "'")
    if re.search(r"\b(?:don't|do not|never)\b|\b(?:how|explain)\b", text, re.I):
        return False
    return bool(re.search(r'\b(?:delete|remove|erase|forget)\b.{0,100}\b(?:notes?|comments?|memor(?:y|ies))\b', text, re.I))


def is_undo_request(text: str) -> bool:
    return bool(re.fullmatch(r"(?:please )?(?:undo(?: (?:that|the deletion|delete|deletion))?|restore (?:that|the|my) (?:note|notes|memory))[.!?]*", text.strip(), re.I))


def words(text: str) -> str:
    return ' '.join(re.findall(r'\w+', text.lower()))


async def delete_or_restore(service, payload, *, undo=False):
    repo, camera = service.repository, service.camera
    def response(text, **extra):
        return AssistantResponse(text=text, model=service.assistant.model,
            camera_used=False, camera_source=camera.source, **extra)
    if undo:
        result = await asyncio.to_thread(repo.undo_note_deletion, payload.author_id, payload.deletion_id)
        if result is None:
            return response('There is no deleted note to restore in this profile.')
        return response('Restored the deleted note and its replies.', memory_changed=True,
            saved_object=repo.object_by_id(result['object_id']))
    if not payload.request_id:
        raise HTTPException(422, 'A request ID is required to delete a note safely.')
    request_id = 'delete:' + payload.request_id
    previous = repo.deletion_result(request_id)
    if previous:
        return response('That deletion was already completed. Say undo to restore it.', deletion_id=request_id,
            deleted_note_ids=json.loads(previous['post_ids']), memory_changed=True,
            saved_object=repo.object_by_id(previous['object_id']))
    if payload.pending_delete_ids:
        # The original choices bind the follow-up to that object, even after looking away.
        with repo.database.connect() as connection:
            marks = ','.join('?' for _ in payload.pending_delete_ids)
            rows = connection.execute(f'SELECT DISTINCT object_id FROM posts WHERE id IN ({marks})', payload.pending_delete_ids).fetchall()
        obj = repo.object_by_id(rows[0]['object_id']) if len(rows) == 1 else None
    else:
        named = [item for item in repo.objects() if words(item.title) in words(payload.message)]
        if len(named) > 1:
            return response('More than one saved object matches. Tell me its exact name and which note to delete.')
        obj = named[0] if named else None
        if obj is None and payload.last_note_id and re.search(r'\b(?:that|last|just|it)\b', payload.message, re.I):
            with repo.database.connect() as connection:
                row = connection.execute('SELECT object_id FROM active_posts WHERE id = ? AND author_id = ?', (payload.last_note_id, payload.author_id)).fetchone()
            obj = repo.object_by_id(row['object_id']) if row else None
        if obj is None:
            capture = await asyncio.to_thread(camera.memory_capture) if payload.include_camera else None
            matches = capture[2] if capture else []
            if len(matches) != 1 or matches[0].tier != 'high':
                return response('Tell me the saved object’s name, or center one saved object, so I can find its note.')
            obj = repo.object_by_identity(matches[0].identity_key)
    if obj is None:
        return response('I could not find that saved object. Nothing was deleted.')
    thread = repo.thread(obj.id)
    notes = [post for root in thread.posts for post in [root, *root.replies] if post.author.id == payload.author_id]
    if payload.pending_delete_ids:
        notes = [post for post in notes if post.id in payload.pending_delete_ids]
    if not notes:
        return response(f'There are no notes from your current profile to delete on {obj.title}.')
    text = payload.message
    chosen = []
    all_notes = bool(re.search(r'\b(?:all|every)\b', text, re.I))
    if all_notes:
        chosen = notes
    elif payload.pending_delete_ids:
        ordinal = re.search(r'\b(first|second|third|fourth|fifth|last|\d+)\b', text, re.I)
        if ordinal:
            value = ordinal.group(1).lower()
            index = {'first': 0, 'second': 1, 'third': 2, 'fourth': 3, 'fifth': 4, 'last': len(notes)-1}.get(value)
            if index is None:
                index = int(value)-1
            chosen = [notes[index]] if 0 <= index < len(notes) else []
        if not chosen:
            chosen = [post for post in notes if words(text).strip() and words(text) in words(post.body)]
    else:
        quoted = re.search(r'(?:says|saying|about|containing|with (?:the )?words|reads)\s+["“]?(.+?)["”]?[.!?]*$', text, re.I)
        if quoted:
            fragment = words(quoted.group(1))
            chosen = [post for post in notes if fragment and fragment in words(post.body)]
        elif payload.last_note_id and re.search(r'\b(?:that|last|just)\b', text, re.I):
            chosen = [post for post in notes if post.id == payload.last_note_id]
        elif len(notes) == 1:
            chosen = notes
    if not chosen or (len(chosen) > 1 and not all_notes):
        choices = '\n'.join(f'{index+1}. {post.body}' for index, post in enumerate(notes))
        return response(f'Which note on {obj.title} should I delete? Say its number or its text. Say cancel to keep them.\n{choices}',
            pending_delete_ids=[post.id for post in notes])
    try:
        result = await asyncio.to_thread(repo.delete_notes, obj.id, [post.id for post in chosen], payload.author_id, request_id)
    except Exception as error:
        from .repositories import NotFoundError
        if isinstance(error, NotFoundError):
            raise HTTPException(409, str(error)) from error
        raise
    return response(f'Deleted {len(chosen)} note' + ('s' if len(chosen) != 1 else '') + f' from {obj.title}. Say undo to restore it.',
        deletion_id=request_id, deleted_note_ids=json.loads(result['post_ids']), memory_changed=True, saved_object=obj)
