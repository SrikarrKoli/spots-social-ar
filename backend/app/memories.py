from __future__ import annotations

import asyncio
import base64
import hashlib
import re
from pathlib import Path

import cv2
import numpy as np
from fastapi import HTTPException

from .assistant import AssistantError, LocalAssistant
from .camera import CameraService, _centre_crop
from .models import AssistantRequest, AssistantResponse
from .note_commands import extract_note_content, extract_object_name, clean_object_name, clean_comment, named_target, split_reply
from .repositories import InvalidReplyError, NotFoundError, Repository
from .noun_phrases import noun_parts, comment_tail


def is_note_request(message: str, history: list[dict] = ()) -> bool:
    text = message.lower().replace("’", "'").strip()
    if re.search(r"\b(don't|do not|never|cancel|stop)\b", text):
        return False
    if re.match(r"^(what|how|why|when|does|do you|can you explain)\b", text):
        return False
    if re.search(r"\b(take|save|leave|write|jot|make|create|post|add|record|store)\b.{0,100}\b(notes?|comments?|memor(?:y|ies))\b", text):
        return True
    if re.search(r"\b(?:remember\s+(this|that)|note that|(?:jot|write|note)\s+down)\b", text):
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


def reply_target(posts, target: str, viewer_id: str):
    """The top-level note a reply belongs under, plus any reply words caught in `target`.

    No name means the latest note from someone else (or the latest note at all); a
    name picks that person's latest note, or the thread they last replied in.
    """
    def latest(entries):
        return max(entries, key=lambda entry: (entry[0].created_at, entry[0].id), default=None)
    generic = re.sub(r"(?:'s)?\s*(?:note|comment|post|message|one)$", "", target.casefold()).strip()
    if generic in {"", "that", "this", "it", "them", "the", "the last", "the latest", "their", "his", "her"}:
        chosen = latest([(post, post) for post in posts if post.author.id != viewer_id]) or latest([(post, post) for post in posts])
        return chosen[1], ""
    named: dict[str, list] = {}
    for root in posts:
        for post in [root, *root.replies]:
            full = post.author.display_name.casefold()
            for name in {full, full.split()[0]}:
                named.setdefault(name, []).append((post, root))
    wanted = target.casefold()
    for name in sorted(named, key=len, reverse=True):
        if wanted == name or re.match(rf"{re.escape(name)}(?:'s\b|\b)", wanted):
            _, root = latest(named[name])
            leftover = re.sub(r"^(?:'s)?\s*(?:note|comment|post|message)?[\s,:;—-]*", "", target[len(name):], flags=re.I)
            return root, leftover
    return None, ""


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
        # Ask only for the note itself; the object is whatever is in view when it's spoken.
        title = clean_object_name(requested_title) if requested_title else ""
        if not title:
            capture = await asyncio.to_thread(self.camera.memory_capture) if payload.include_camera else None
            record = self.facing_record(capture[0], capture[2]) if capture else None
            title = record.title if record else ""
        return respond(f"What should the note{' on ' + title if title else ''} say?",
            awaiting_note=True, pending_title=title)

    def facing_record(self, frame, matches):
        """The saved object the wearer is facing: the confident match nearest the centre."""
        confident = [match for match in matches if match.tier == "high"]
        if not confident:
            return None
        height, width = frame.shape[:2]
        def distance(match):
            corners = getattr(match, "corners", None)
            if corners is None:
                return 0.0
            x, y = np.asarray(corners).mean(axis=0)
            return (x / width - .5) ** 2 + (y / height - .5) ** 2
        for match in sorted(confident, key=distance):
            record = self.repository.object_by_identity(match.identity_key)
            if record:
                return record
        return None

    async def guess_title(self, frame) -> str:
        """Name a new object from the camera so the wearer is never asked to."""
        ok, jpeg = cv2.imencode('.jpg', _centre_crop(frame))
        if not ok:
            return ""
        try:
            guess = await self.assistant.answer(
                "Name the main foreground object in this view with a short noun phrase of at most four words. Reply with the phrase only.",
                [], "Used only as a display name for a saved note; the user can rename it.",
                base64.b64encode(jpeg.tobytes()).decode())
        except AssistantError:
            return ""
        title = clean_object_name(guess)
        if not title or len(title.split()) > 6 or re.search(r"\b(?:unknown|uncertain|unsure|cannot|multiple)\b", title, re.I):
            return ""
        return title

    async def reply(self, payload: AssistantRequest) -> AssistantResponse:
        """Post a spoken reply into the thread of a note on the object in view."""
        def respond(text, **extra):
            return AssistantResponse(text=text, model=self.assistant.model, camera_used=False,
                camera_source=self.camera.source, **extra)
        if not payload.request_id:
            raise HTTPException(422, "A request ID is required to post a reply safely.")
        if payload.awaiting_reply and payload.pending_reply_to:
            object_id = await asyncio.to_thread(self.repository.post_object_id, payload.pending_reply_to)
            record = self.repository.object_by_id(object_id) if object_id else None
            thread = await asyncio.to_thread(self.repository.thread, object_id) if record else None
            parent = next((post for post in thread.posts if post.id == payload.pending_reply_to), None) if thread else None
            if parent is None:
                return respond("That note is no longer available. Nothing was posted.")
            body = payload.message
        else:
            record = None
            if payload.include_camera:
                capture = await asyncio.to_thread(self.camera.memory_capture)
                record = self.facing_record(capture[0], capture[2]) if capture else None
            if record is None and payload.object_id:
                record = self.repository.object_by_id(payload.object_id)
            if record is None:
                return respond("Look at the object with the note you want to reply to, then say “reply saying …”. Nothing was posted.")
            thread = await asyncio.to_thread(self.repository.thread, record.id)
            if not thread.posts:
                return respond(f"There's no note on {record.title} to reply to yet. Say “leave a note saying …” to start one.")
            target, body = split_reply(payload.message)
            parent, leftover = reply_target(thread.posts, target, payload.author_id)
            if parent is None:
                return respond(f"I couldn't find a note from {target} on {record.title}. Nothing was posted.")
            body = body or leftover
        body = clean_comment(body)
        recipient = parent.author.display_name.split()[0]
        if not body:
            return respond(f"What's your reply to {recipient}?", awaiting_reply=True,
                pending_reply_to=parent.id, pending_title=record.title)
        if len(body) > 500:
            return respond("Please keep the reply under 500 characters. Nothing was posted.")
        try:
            post = await asyncio.to_thread(self.repository.create_post, object_id=record.id,
                author_id=payload.author_id, body=body, parent_post_id=parent.id,
                client_request_id="reply:" + payload.request_id)
        except NotFoundError as error:
            raise HTTPException(404, str(error)) from error
        except InvalidReplyError as error:
            raise HTTPException(409, str(error)) from error
        return respond(f"Replied to {recipient} on {record.title}: “{post.body}”",
            saved_note=post, saved_object=record, memory_changed=True)

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

    async def save(self, payload: AssistantRequest, parsed_content: dict | None = None, parsed_name: str = "", target=None) -> AssistantResponse:
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
            # Attach to the object being faced rather than asking which one was meant.
            record = target or self.facing_record(frame, matches)
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
            explicit_title = (clean_object_name(parsed_name) or extract_object_name(payload.message)
                or clean_object_name(payload.pending_title) or named_target(payload.message)
                or (extracted['title'] if payload.awaiting_name else ''))
            extracted['body'] = clean_comment(extracted['body'])
            if not extracted['body']:
                return AssistantResponse(text="What should the new comment say?",
                    model=self.assistant.model, camera_used=True, camera_source=self.camera.source,
                    captured_at=captured_at, awaiting_note=True, pending_title=explicit_title or (extracted['title'] if extracted['title'] != 'Remembered object' else ''))
            path = None
            object_id = record.id if record else "memory-" + hashlib.sha256(request_id.encode()).hexdigest()[:16]
            title = explicit_title or (clean_object_name(record.title) if record else '')
            if record is None and not title:
                title = await self.guess_title(frame) or 'Saved object'
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
