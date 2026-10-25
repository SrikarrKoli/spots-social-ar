from __future__ import annotations

import asyncio
import base64
import hashlib
import re
from pathlib import Path

import cv2
from fastapi import HTTPException

from .assistant import AssistantError, LocalAssistant
from .camera import CameraService, _centre_crop
from .models import AssistantRequest, AssistantResponse
from .note_commands import extract_note_content, extract_object_name, clean_object_name, clean_comment
from .repositories import Repository
from .noun_phrases import noun_parts, comment_tail


def is_note_request(message: str, history: list[dict] = ()) -> bool:
    text = message.lower().replace("’", "'").strip()
    if re.search(r"\b(don't|do not|never|cancel|stop)\b", text):
        return False
    if re.match(r"^(what|how|why|when|does|do you|can you explain)\b", text):
        return False
    if re.search(r"\b(take|save|leave|write|jot|make|create|post|add|record|store)\b.{0,100}\b(notes?|comments?|memor(?:y|ies))\b", text):
        return True
    if re.search(r"\b(?:remember\s+(this|that)|note that)\b", text):
        return True
    return bool(re.search(r"\bsave (it|that|this)\b", text) and any(
        re.search(r"\b(note|notes|remember)\b", item["content"], re.I) for item in history
    ))


def is_bare_comment_request(message: str) -> bool:
    """Fast-path an explicit start command only; never treat the command as content."""
    text = message.strip().lower().replace("’", "'")
    if not is_note_request(text) or re.search(r"\b(?:not|don't|never|cancel|stop|delete|edit|change)\b", text):
        return False
    return bool(re.fullmatch(
        r"(?:(?:okay|ok|hey|please|spots|can you|could you|i want to|i'd like to|i would like to|let me|let's)\s*[, ]*\s*)*"
        r"(?:add|leave|make|take|write|save|post|create|record)\s+(?:(?:a|another|my|some|the|new)\s+)*"
        r"(?:comments?|notes?)(?:\s+(?:to|on|about|for)\s+(?:(?:this|that|the|a|new)\s+)*(?:object|thing|item))?"
        r"(?:\s+(?:here|right here|please|now))?[.!?]*", text))


class MemoryService:
    def __init__(self, repository: Repository, camera: CameraService, assistant: LocalAssistant, directory: Path):
        self.repository, self.camera, self.assistant, self.directory = repository, camera, assistant, directory
        self.lock = asyncio.Lock()

    def response(self, note, captured_at=None):
        obj = self.repository.object_by_id(note.object_id)
        return AssistantResponse(
            text=f'Saved to {obj.title}: “{note.body}” I’ll show it when I recognize this object again.',
            model=self.assistant.model, camera_used=captured_at is not None,
            camera_source=self.camera.source, captured_at=captured_at,
            saved_note=note, saved_object=obj,
        )

    async def begin_comment(self, payload: AssistantRequest, requested_title: str = "") -> AssistantResponse:
        def respond(text, **extra):
            return AssistantResponse(text=text, model=self.assistant.model, camera_used=False,
                camera_source=self.camera.source, **extra)
        if requested_title:
            title = clean_object_name(requested_title)
            if title:
                return respond(f"Sure — a new comment on {title}. What should it say?", awaiting_note=True, pending_title=title)
        capture = await asyncio.to_thread(self.camera.memory_capture) if payload.include_camera else None
        matches = capture[2] if capture else []
        if len(matches) == 1 and matches[0].tier == "high":
            record = self.repository.object_by_identity(matches[0].identity_key)
            if record:
                return respond(f"Sure — a new comment on {record.title}. What should it say?",
                    awaiting_note=True, pending_title=record.title)
        stable = await asyncio.to_thread(self.camera.stable_view) if capture else None
        if stable:
            frame, captured_at = stable
            ok, jpeg = cv2.imencode('.jpg', _centre_crop(frame))
            if ok:
                try:
                    guess = await self.assistant.answer(
                        "Identify the main foreground object in this view. Reply with a short noun phrase of at most six words. If ambiguous, reply unknown. Do not invent a name or a comment.",
                        [], "This steady camera view is only a tentative target suggestion, never saved identity.",
                        base64.b64encode(jpeg.tobytes()).decode())
                    title = clean_object_name(guess)
                    if title and len(title.split()) <= 6 and not re.search(r"\b(?:unknown|uncertain|unsure|not|maybe|cannot|multiple)\b", title, re.I):
                        return AssistantResponse(text=f"It looks like {title}. Is that the object you want to comment on? Say yes, or tell me its name.",
                            model=self.assistant.model, camera_used=True, camera_source=self.camera.source,
                            captured_at=captured_at, awaiting_description=True, pending_title=title)
                except AssistantError:
                    pass
        return respond("Sure. What object are you commenting on? Tell me its name, then what the comment should say.", awaiting_description=True)

    async def rename(self, payload: AssistantRequest, parsed_name: str = "") -> AssistantResponse:
        name = clean_object_name(parsed_name) if parsed_name else extract_object_name(payload.message)
        if not name:
            return AssistantResponse(text='Tell me the exact name, for example: "Rename this to Dinnie poster."',
                model=self.assistant.model, camera_used=False, camera_source=self.camera.source)
        if not payload.include_camera:
            raise HTTPException(422, "Turn on camera sharing and point at the saved object to rename it.")
        create_new = False
        async with self.lock:
            capture = await asyncio.to_thread(self.camera.memory_capture)
            if capture is None:
                raise HTTPException(503, "I need a fresh camera view to rename the object.")
            frame, captured_at, matches = capture
            if not matches:
                create_new = True
            elif len(matches) != 1 or matches[0].tier != "high":
                raise HTTPException(409, "Center one saved object so I can confidently rename it.")
            record = self.repository.object_by_identity(matches[0].identity_key) if matches else None
            if record is None and not create_new:
                raise HTTPException(404, "Save a note on this object first.")
            if record:
                obj = await asyncio.to_thread(self.repository.rename_object, record.id, name)
                return AssistantResponse(text=f'Renamed this object to {obj.title}. Its saved notes are unchanged.',
                    model=self.assistant.model, camera_used=True, camera_source=self.camera.source,
                    captured_at=captured_at, saved_object=obj)
        # Naming an object is not permission to manufacture a comment.
        if not payload.request_id:
            raise HTTPException(422, "A request ID is required to name a new object.")
        object_id = 'memory-' + hashlib.sha256(('name:' + payload.request_id).encode()).hexdigest()[:16]
        existing = self.repository.object_by_id(object_id)
        if existing:
            return AssistantResponse(text=f'Named this object {existing.title}. No comment was added.',
                model=self.assistant.model, camera_used=False, camera_source=self.camera.source, saved_object=existing)
        crop = _centre_crop(frame)
        path = self.directory / f'{object_id}.png'
        async with self.lock:
            try:
                if not await asyncio.to_thread(self.camera.enroll_reference, object_id, crop, min_keypoints=15):
                    raise HTTPException(422, 'This view is too plain or blurry. Center the object in good light and try again.')
                self.directory.mkdir(parents=True, exist_ok=True)
                ok, encoded = cv2.imencode('.png', crop)
                if not ok:
                    raise HTTPException(503, "Couldn't store the object's image.")
                await asyncio.to_thread(path.write_bytes, encoded.tobytes())
                obj = await asyncio.to_thread(self.repository.enroll_object, object_id=object_id,
                    title=name, description=None, reference_path=str(path.resolve()))
            except Exception:
                self.camera.remove_reference(object_id)
                path.unlink(missing_ok=True)
                raise
        return AssistantResponse(text=f'Named this object {obj.title}. What comment would you like to add?',
            model=self.assistant.model, camera_used=True, camera_source=self.camera.source,
            captured_at=captured_at, saved_object=obj, awaiting_note=True, pending_title=name)

    async def save(self, payload: AssistantRequest, parsed_content: dict | None = None, parsed_name: str = "") -> AssistantResponse:
        if not payload.request_id:
            raise HTTPException(422, "A request ID is required to save a note safely.")
        # Retry the same request without re-enrolling, re-transcribing or duplicating a note.
        request_id = "memory:" + payload.request_id
        existing = await asyncio.to_thread(self.repository.memory_by_request, request_id)
        if existing:
            return self.response(existing)
        if not payload.include_camera:
            raise HTTPException(422, "Turn on camera sharing to attach your note to the object you're looking at.")
        if payload.author_id not in {profile.id for profile in self.repository.profiles()}:
            raise HTTPException(404, "Profile not found")
        if self.lock.locked():
            raise HTTPException(409, "Another note is being saved. Please wait a moment.")
        async with self.lock:
            capture = await asyncio.to_thread(self.camera.memory_capture)
            if capture is None:
                raise HTTPException(503, "I need a fresh camera view to save that note. Reconnect the camera and try again.")
            frame, captured_at, matches = capture
            title_hint = clean_object_name(parsed_name) or clean_object_name(payload.pending_title)
            if title_hint and len(matches) > 1:
                named = [match for match in matches if match.tier == "high" and (record := self.repository.object_by_identity(match.identity_key)) and record.title.casefold() == title_hint.casefold()]
                if len(named) == 1:
                    matches = named
            if title_hint and matches and await asyncio.to_thread(self.camera.stable_view):
                height, width = frame.shape[:2]
                # Saved background objects must not block a new foreground target.
                peripheral = all(hasattr(match, 'center') and
                    ((match.center[0] / width - .5) ** 2 + (match.center[1] / height - .5) ** 2) ** .5 > .35
                    for match in matches)
                if peripheral:
                    matches = []
            # Only a fresh match from this exact image may select an existing identity.
            if len(matches) > 1 or (matches and matches[0].tier != "high"):
                if parsed_content is not None:
                    held = clean_comment(parsed_content.get('body', ''))
                    return AssistantResponse(text="I see several possible objects. Which one do you mean? Tell me its name; I’ll keep your comment while we choose.",
                        model=self.assistant.model, camera_used=True, camera_source=self.camera.source,
                        captured_at=captured_at, awaiting_name=True, pending_body=held)
                raise HTTPException(409, "I can't confidently choose one object. Center just that object, move closer, then repeat your note. Nothing was saved to another object.")
            ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                raise HTTPException(503, "Couldn't capture the object. Please try again.")
            try:
                if parsed_content is not None:
                    extracted = dict(parsed_content)
                elif payload.awaiting_name:
                    name, tail = noun_parts(payload.message)
                    extracted = {'body': ' '.join(part for part in [payload.pending_body, comment_tail(tail)] if part),
                                 'title': extract_object_name(payload.message) or name}
                elif payload.awaiting_note:
                    extracted = extract_note_content(payload.message, [], followup=True)
                    if len(extracted['body']) > 500:
                        raise AssistantError("Please keep the note under 500 characters. Nothing was saved.")
                else:
                    extracted = await self.assistant.extract_note(
                        payload.message, [item.model_dump() for item in payload.history],
                        base64.b64encode(jpeg.tobytes()).decode(),
                    )
            except AssistantError as error:
                raise HTTPException(502, str(error)) from error
            explicit_title = clean_object_name(parsed_name) or extract_object_name(payload.message) or clean_object_name(payload.pending_title) or (extracted['title'] if payload.awaiting_name else '')
            extracted['body'] = clean_comment(extracted['body'])
            if extracted['title'] != 'Remembered object':
                extracted['title'] = clean_object_name(extracted['title']) or 'Remembered object'
            if explicit_title:
                extracted['title'] = explicit_title
            record = self.repository.object_by_identity(matches[0].identity_key) if matches else None
            if not extracted['body']:
                return AssistantResponse(text="What should the new comment say?",
                    model=self.assistant.model, camera_used=True, camera_source=self.camera.source,
                    captured_at=captured_at, awaiting_note=True, pending_title=explicit_title or (extracted['title'] if extracted['title'] != 'Remembered object' else ''))
            path = None
            object_id = record.id if record else "memory-" + hashlib.sha256(request_id.encode()).hexdigest()[:16]
            title = explicit_title or (clean_object_name(record.title) if record else extracted['title'])
            if record is None and (not title or title == 'Remembered object'):
                return AssistantResponse(text='I have your note. What should I call this object? For example, "blue water bottle". Your comment is held while we name it.',
                    model=self.assistant.model, camera_used=True, camera_source=self.camera.source,
                    captured_at=captured_at, awaiting_name=True, pending_body=extracted['body'])
            try:
                if record is None:
                    crop = _centre_crop(frame)
                    # Require enough texture for the matcher; never claim reliable future
                    # recognition from an empty/featureless image.
                    if not await asyncio.to_thread(self.camera.enroll_reference, object_id, crop, min_keypoints=15):
                        raise HTTPException(422, "That view is too plain or blurry to recognize later. Point at a detailed part of the object in good light and repeat your note.")
                    self.directory.mkdir(parents=True, exist_ok=True)
                    path = self.directory / f'{object_id}.png'
                    ok, encoded = cv2.imencode('.png', crop)
                    if not ok:
                        raise HTTPException(503, "Couldn't store the object's image. Nothing was saved.")
                    await asyncio.to_thread(path.write_bytes, encoded.tobytes())
                note = await asyncio.to_thread(self.repository.save_memory,
                    object_id=object_id, title=title, reference_path=str(path.resolve()) if path else None,
                    author_id=payload.author_id, body=extracted['body'], request_id=request_id,
                    rename_title=title if record and title != record.title else None)
            except Exception:
                if record is None:
                    self.camera.remove_reference(object_id)
                    if path:
                        path.unlink(missing_ok=True)
                raise
            return self.response(note, captured_at)
