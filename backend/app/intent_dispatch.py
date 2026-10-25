"""Execute validated intent through existing transactional object/note operations."""
import asyncio
from .models import AssistantResponse
from .note_commands import clean_object_name, object_title
from .comment_actions import read_comments, edit_comment, resolve_object, flattened
from .note_deletion import delete_or_restore, words


async def dispatch_intent(service, payload, intent):
    def respond(text, **extra):
        return AssistantResponse(text=text, model=service.assistant.model,
            camera_used=False, camera_source=service.camera.source, **extra)
    action = intent.action
    if action == 'chat':
        return None
    if action == 'clarify':
        return respond(intent.question or 'What would you like me to save or change?')
    if action == 'cancel':
        return respond('Cancelled. Nothing was changed.')
    body = ' '.join(intent.comment_spans).strip()
    title = clean_object_name(intent.object_name) if intent.object_name else ''
    target = (' on ' + intent.target_object) if intent.target_object else ''
    if action == 'describe_object':
        title = title or clean_object_name(payload.message)
        return respond(f'Got it{": " + title if title else ""}. What comment should I save?', awaiting_note=True, pending_title=title)
    if action == 'name_object':
        if not title:
            return respond('What should I call this object?')
        return await service.rename(payload, parsed_name=title)
    if action == 'add_comment':
        if not body and not payload.pending_body:
            return await service.begin_comment(payload, requested_title=title or intent.target_object or payload.pending_title)
        if intent.target_object:
            capture = await asyncio.to_thread(service.camera.memory_capture) if payload.include_camera else None
            matches = capture[2] if capture else []
            visible = service.repository.object_by_identity(matches[0].identity_key) if len(matches) == 1 and matches[0].tier == 'high' else None
            if not visible or words(visible.title) != words(intent.target_object):
                return respond(f'Point at {intent.target_object} and repeat the comment so I can attach it to the correct object.')
        if payload.awaiting_name and payload.pending_body and body != payload.pending_body:
            body = ' '.join(part for part in [payload.pending_body, body] if part)
        return await service.save(payload, parsed_content={
            'body': body, 'title': title or payload.pending_title or object_title(payload.message),
        }, parsed_name=title)
    if action == 'read_comments':
        request = payload.model_copy(update={'message': 'Read comments' + target + (' aloud' if intent.read_aloud else '')})
        result = await read_comments(service, request)
        return result.model_copy(update={'read_aloud': intent.read_aloud})
    if action == 'undo':
        return await delete_or_restore(service, payload, undo=True)
    if action in {'edit_comment', 'delete_comment'}:
        select = {'last': ' last', 'all': ' all', 'number': f' number {intent.number}', 'matching': ' saying ' + intent.matching_text}.get(intent.selector, '')
        message = ('Change my' if action == 'edit_comment' else 'Delete') + select + ' comment' + target
        if action == 'edit_comment':
            message += (' to say ' + body) if body else ''
        elif intent.selector == 'matching':
            message = 'Delete comment' + target + ' saying ' + intent.matching_text
        request = payload.model_copy(update={'message': message})
        # Select numbered/quoted notes using their real IDs, then bind the follow-up.
        if intent.selector in {'number', 'matching'} and not (payload.pending_edit_ids or payload.pending_delete_ids):
            obj = await resolve_object(service, request)
            if obj:
                notes = [post for post in flattened(service.repository.thread(obj.id)) if post.author.id == payload.author_id]
                if intent.selector == 'number' and 1 <= intent.number <= len(notes):
                    ids = [notes[intent.number-1].id]
                elif intent.selector == 'matching':
                    ids = [post.id for post in notes if words(intent.matching_text) in words(post.body)]
                else:
                    ids = []
                if ids:
                    field = 'pending_edit_ids' if action == 'edit_comment' else 'pending_delete_ids'
                    request = request.model_copy(update={field: ids})
                    if action == 'delete_comment':
                        request = request.model_copy(update={'message': 'all' if len(ids) == 1 else intent.matching_text})
        if action == 'edit_comment':
            request = request.model_copy(update={'pending_edit_body': body or payload.pending_edit_body})
            return await edit_comment(service, request)
        return await delete_or_restore(service, request)
    return respond('Please tell me the action you want to take. Nothing was changed.')
