"""Read saved notes verbatim and edit the intended comment through real DB actions."""
import asyncio
import re
from fastapi import HTTPException
from .models import AssistantResponse
from .note_commands import extract_note_content
from .repositories import NotFoundError


def is_read_notes(text: str) -> bool:
    return bool(re.search(r'\b(?:notes?|comments?|thread|memories)\b', text, re.I) and
        re.search(r'\b(?:read|what|which|previous|past|earlier|before|left|saved|tell me|any)\b', text, re.I) and
        not re.search(r'\b(?:delete|remove|edit|change|update|replace|correct|add|write|take|leave)\b', text, re.I)) or bool(re.fullmatch(r'(?:read|show|tell me) (?:more|the next notes)[.!?]*', text.strip(), re.I))


def is_edit_note(text: str) -> bool:
    return bool(re.search(r'\b(?:edit|change|update|replace|correct|adjust|fix|rewrite)\b.{0,80}\b(?:note|comment|memory)\b', text, re.I)) or bool(re.search(r"\b(?:that(?:'s| is) not what I (?:meant|wanted)|I meant (?:to say|the note))\b", text, re.I))


def edit_body(text: str) -> str:
    match = re.search(r'\b(?:to (?:say|read)|so (?:it|the note) says|instead say|I meant to say|should (?:say|read))\s*[:,-]?\s+(.+)', text, re.I | re.S)
    if not match:
        match = re.search(r'\b(?:note|comment|memory)\s+(?:to|with)\s*[:,-]?\s+(.+)', text, re.I | re.S)
    if not match:
        return ''
    return re.sub(r'\s+(?:for me\s+)?please[.!?]*$', '', match.group(1), flags=re.I).strip(' "“”')


def question_or_camera_setup(text: str) -> bool:
    text = re.sub(r'^(?:okay|ok|hey|so|well)[,.]?\s*', '', text.strip(), flags=re.I)
    return bool(re.match(r"^(?:what|which|why|how|when|where|who|can you|could you|do you|did you|does|is (?:it|this|that)|are you)\b", text, re.I) or re.search(r"\b(?:in (?:my|the) frame|in view|can you see|do you see|pointing (?:at|to)|camera (?:is|view))\b", text, re.I))


def clean_comment(text: str) -> str:
    # Keep statements intended as content; discard setup/checking-visibility sentences.
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    kept = [part for part in sentences if part and not question_or_camera_setup(part)]
    return ' '.join(kept).strip()


async def resolve_object(service, payload, *, last_note=False):
    repo = service.repository
    named = [obj for obj in repo.objects() if obj.title.lower() in payload.message.lower()]
    if len(named) == 1:
        return named[0]
    if last_note and payload.last_note_id:
        with repo.database.connect() as db:
            row = db.execute('SELECT object_id FROM active_posts WHERE id=?', (payload.last_note_id,)).fetchone()
        if row:
            return repo.object_by_id(row['object_id'])
    capture = await asyncio.to_thread(service.camera.memory_capture) if payload.include_camera else None
    matches = capture[2] if capture else []
    if len(matches) == 1 and matches[0].tier == 'high':
        obj = repo.object_by_identity(matches[0].identity_key)
        if obj and (not named or obj.id in {item.id for item in named}):
            return obj
    return None


async def read_notes(service, payload):
    repo = service.repository
    obj = await resolve_object(service, payload, last_note=bool(re.search(r'\b(?:that|last|just)\b', payload.message, re.I)))
    def response(text, **extra):
        return AssistantResponse(text=text, model=service.assistant.model, camera_used=False, camera_source=service.camera.source, **extra)
    if obj is None:
        return response('Which saved object should I read? Tell me its name or center it in the camera.')
    thread = repo.thread(obj.id)
    notes = [post for root in thread.posts for post in [root, *root.replies]]
    if not notes:
        return response(f'There are no saved comments on {obj.title} yet.')
    start = payload.notes_offset if re.search(r'\b(?:more|next)\b', payload.message, re.I) else 0
    page = notes[start:start+5]
    if not page:
        return response(f'That is all the saved comments on {obj.title}.', notes_offset=0)
    lines = [f'{len(notes)} saved comments on {obj.title}.'] if start == 0 else [f'More comments on {obj.title}.']
    for index, post in enumerate(page, start+1):
        lines.append(f'{index}. {post.author.display_name}, {post.created_at.strftime("%B %d, %Y")}: {post.body}')
    if start + len(page) < len(notes):
        lines.append('Say read more to hear the next comments.')
    return response('\n'.join(lines), read_aloud=True, notes_offset=start+len(page))


async def edit_note(service, payload):
    repo = service.repository
    def response(text, **extra):
        return AssistantResponse(text=text, model=service.assistant.model, camera_used=False, camera_source=service.camera.source, **extra)
    body = edit_body(payload.message) or payload.pending_edit_body
    if payload.awaiting_edit and not body and not question_or_camera_setup(payload.message):
        body = clean_comment(payload.message)
    ids = payload.pending_edit_ids
    if ids:
        with repo.database.connect() as db:
            marks = ','.join('?' for _ in ids)
            row = db.execute(f'SELECT DISTINCT object_id FROM active_posts WHERE id IN ({marks})', ids).fetchall()
        obj = repo.object_by_id(row[0]['object_id']) if len(row) == 1 else None
    else:
        obj = await resolve_object(service, payload, last_note=bool(re.search(r'\b(?:that|last|just|meant|wanted)\b', payload.message, re.I)))
    if obj is None:
        return response('Tell me the saved object’s name or center it, then say which comment to change.')
    thread = repo.thread(obj.id)
    notes = [post for root in thread.posts for post in [root, *root.replies] if post.author.id == payload.author_id and (not ids or post.id in ids)]
    if not notes:
        return response(f'There are no comments from your current profile to change on {obj.title}.')
    chosen = None
    if len(notes) == 1:
        chosen = notes[0]
    elif not ids and payload.last_note_id and re.search(r'\b(?:that|last|just|meant|wanted)\b', payload.message, re.I):
        chosen = next((item for item in notes if item.id == payload.last_note_id), None)
    else:
        ordinal = re.search(r'\b(first|second|third|fourth|fifth|last|\d+)\b', payload.message, re.I)
        if ordinal:
            value = ordinal.group(1).lower()
            index = {'first':0,'second':1,'third':2,'fourth':3,'fifth':4,'last':len(notes)-1}.get(value)
            if index is None:
                index = int(value)-1
            chosen = notes[index] if 0 <= index < len(notes) else None
    if chosen is None:
        return response('Which comment should I change? Say its number.\n'+'\n'.join(f'{i+1}. {post.body}' for i,post in enumerate(notes)),
            pending_edit_ids=[post.id for post in notes], pending_edit_body=body)
    if not body or question_or_camera_setup(body):
        return response(f'What should this comment say instead? Current comment: “{chosen.body}”',
            pending_edit_ids=[chosen.id], awaiting_edit=True)
    if len(body) > 500:
        raise HTTPException(422, 'Keep the replacement comment under 500 characters. Nothing was changed.')
    if not payload.request_id:
        raise HTTPException(422, 'A request ID is required to edit a comment safely.')
    try:
        post = await asyncio.to_thread(repo.edit_note, chosen.id, body, payload.author_id, payload.request_id)
    except NotFoundError as error:
        raise HTTPException(404, str(error)) from error
    return response(f'Updated the comment on {obj.title} to: “{post.body}”',
        saved_note=post, saved_object=obj, memory_changed=True)
