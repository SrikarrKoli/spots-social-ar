from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import numpy as np

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .camera import CameraService
from .assistant import AssistantError, LocalAssistant
from .intent_parser import IntentParser
from .intent_dispatch import dispatch_intent
from .memories import MemoryService, is_note_request, is_bare_comment_request
from .comment_actions import is_read_request, read_comments, is_edit_request, edit_comment
from .note_deletion import is_delete_request, is_undo_request, delete_or_restore
from .note_commands import is_rename_request, is_visual_identification, explicit_name_comment, is_conversation_turn, clean_object_name, is_cancel_request
from .config import ROOT, Settings
from .database import Database, seed_demo
from .restaurant_demo import seed_restaurant_demo
from .models import (
    AddViewsResponse,
    AssistantRequest,
    AssistantResponse,
    ConfirmIdentityRequest,
    CreatePostRequest,
    EnrollLiveRequest,
    EnrollLiveResponse,
    EnrollmentDiagnostics,
    HealthResponse,
    ObjectSummary,
    PerformanceDiagnostics,
    Post,
    Profile,
    RecognitionResponse,
    ScanRequest,
    ScanResponse,
    ThreadResponse,
    TranscriptionResponse,
)
from .recognition import build_recognizer
from .repositories import InvalidReplyError, NotFoundError, Repository
from .transcription import (
    TranscriptionError,
    TranscriptionNotConfigured,
    build_transcription_provider,
)


MAX_AUDIO_BYTES = 25 * 1024 * 1024
SUPPORTED_AUDIO_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/m4a",
    "audio/ogg",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    cv2.setNumThreads(app_settings.opencv_threads)
    database = Database(app_settings.database_path)
    repository = Repository(database)
    assistant = LocalAssistant(app_settings.ollama_url, app_settings.assistant_model)
    camera = CameraService(
        source=app_settings.camera_source,
        camera_index=app_settings.camera_index,
        fixture_path=app_settings.camera_fixture,
        width=app_settings.camera_width,
        height=app_settings.camera_height,
        detection_ttl_ms=app_settings.detection_ttl_ms,
        dictionary_name=app_settings.marker_dictionary,
        recognizer=build_recognizer(
            app_settings.recognizer,
            dictionary_name=app_settings.marker_dictionary,
        ),
        recognition_max_width=app_settings.recognition_max_width,
        recognition_fps=app_settings.recognition_fps,
        stream_fps=app_settings.stream_fps,
        jpeg_quality=app_settings.stream_jpeg_quality,
        max_auto_banked_per_identity=(
            app_settings.max_auto_banked_files_per_identity
        ),
    )
    transcription = build_transcription_provider(
        provider=app_settings.transcription_provider,
        api_key=app_settings.openai_api_key,
        model=app_settings.openai_transcription_model,
        prompt=app_settings.openai_transcription_prompt,
        whisper_model=app_settings.whisper_model,
        whisper_device=app_settings.whisper_device,
        whisper_compute_type=app_settings.whisper_compute_type,
    )
    memories = MemoryService(repository, camera, assistant, app_settings.enrolled_dir)
    camera.load_shed_active = lambda: bool(
        getattr(transcription, "busy", False)
    )

    def _relative_reference(path: Path) -> str:
        try:
            return str(path.relative_to(ROOT))
        except ValueError:
            return str(path)

    def _thumbnails(views: list[np.ndarray]) -> list[str]:
        thumbnails: list[str] = []
        for view in views:
            thumb = cv2.resize(
                view, (240, int(240 * view.shape[0] / max(1, view.shape[1])))
            )
            ok, encoded = cv2.imencode(
                ".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 70]
            )
            if ok:
                thumbnails.append(base64.b64encode(encoded.tobytes()).decode())
        return thumbnails

    def _diagnostics(capture: object, views_enrolled: int) -> EnrollmentDiagnostics:
        return EnrollmentDiagnostics(
            frames_sampled=capture.frames_sampled,
            views_selected=len(capture.views),
            views_enrolled=views_enrolled,
            best_sharpness=round(capture.best_sharpness, 1),
        )

    def _persist_banked_view(identity_key: str, image: np.ndarray) -> None:
        record = repository.object_by_identity(identity_key)
        if record is None:
            return
        success, encoded = cv2.imencode(".png", image)
        if not success:
            return
        digest = hashlib.sha1(encoded.tobytes()).hexdigest()[:10]
        app_settings.enrolled_dir.mkdir(parents=True, exist_ok=True)
        path = app_settings.enrolled_dir / f"{record.id}-banked-{digest}.png"
        if path.exists():
            return
        path.write_bytes(encoded.tobytes())
        repository.add_reference_path(record.id, _relative_reference(path))

    camera.view_bank_sink = _persist_banked_view

    def _slug_object_id(title: str, digest_source: bytes) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
        if not slug:
            raise HTTPException(status_code=422, detail="Title needs a letter or digit")
        digest = hashlib.sha1(digest_source).hexdigest()[:8]
        return f"{slug}-{digest}"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        seed_demo(database)
        if app_settings.restaurant_demo_enabled:
            seed_restaurant_demo(database)
        references = [
            (identity_key, ROOT / reference_path)
            for identity_key, reference_path in repository.object_references(
                max_per_identity=app_settings.max_reference_files_per_identity
            )
        ]
        camera.load_reference_files(references)
        camera.start()
        yield
        camera.stop()

    app = FastAPI(
        title="Locus API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.database = database
    app.state.repository = repository
    app.state.camera = camera
    app.state.transcription = transcription
    app.state.assistant = assistant
    app.state.memories = memories

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        assistant_status, assistant_message = await assistant.readiness()
        return HealthResponse(
            camera_status=camera.status,
            camera_source=camera.source,
            transcription_status=transcription.status,
            camera_index=camera.camera_index,
            llm_parser_enabled=app_settings.llm_parser_enabled,
            assistant_status=assistant_status,
            assistant_model=assistant.model,
            assistant_message=assistant_message,
        )

    parser = IntentParser(app_settings.ollama_url, app_settings.assistant_model)
    app.state.intent_parser = parser

    @app.post("/api/assistant", response_model=AssistantResponse)
    async def converse(payload: AssistantRequest) -> AssistantResponse:
        history = [item.model_dump() for item in payload.history]
        if payload.awaiting_description and payload.pending_title and re.fullmatch(r"(?:yes|yeah|yep|correct|right|that's right|that is right|yes please)[.! ]*", payload.message.strip(), re.I):
            return AssistantResponse(text=f"Got it — {payload.pending_title}. What should the comment say?", model=assistant.model,
                camera_used=False, camera_source=camera.source, awaiting_note=True, pending_title=payload.pending_title)
        if is_bare_comment_request(payload.message):
            return await memories.begin_comment(payload)
        if app_settings.llm_parser_enabled:
            try:
                intent = await parser.parse(payload, repository.objects())
                handled = await dispatch_intent(memories, payload, intent)
            except AssistantError as error:
                return AssistantResponse(text=str(error), model=assistant.model,
                    camera_used=False, camera_source=camera.source)
            if handled is not None:
                return handled
        else:
            if (payload.awaiting_note or payload.awaiting_name or payload.pending_delete_ids or payload.awaiting_description or payload.pending_edit_ids) and is_cancel_request(payload.message):
                return AssistantResponse(text="Cancelled. Nothing was changed.", model=assistant.model,
                                         camera_used=False, camera_source=camera.source)
            if is_edit_request(payload.message):
                return await edit_comment(memories, payload)
            if is_read_request(payload.message):
                return await read_comments(memories, payload)
            if payload.pending_edit_ids and not is_conversation_turn(payload.message):
                return await edit_comment(memories, payload)
            if payload.awaiting_description and not is_note_request(payload.message, history) and not is_conversation_turn(payload.message):
                title = clean_object_name(payload.message)
                return AssistantResponse(text=f"Got it{': ' + title if title else ''}. What comment should I save? You can say 'add a comment saying …'.", model=assistant.model,
                    camera_used=False, camera_source=camera.source, awaiting_note=True, pending_title=title)
            if is_undo_request(payload.message):
                return await delete_or_restore(memories, payload, undo=True)
            if payload.pending_delete_ids or is_delete_request(payload.message):
                return await delete_or_restore(memories, payload)
            if is_rename_request(payload.message) and not (payload.awaiting_note or payload.awaiting_name or is_note_request(payload.message, history) or explicit_name_comment(payload.message)):
                return await memories.rename(payload)
            if (payload.awaiting_note and not is_conversation_turn(payload.message)) or (payload.awaiting_name and not is_conversation_turn(payload.message)) or is_note_request(payload.message, history) or explicit_name_comment(payload.message):
                return await memories.save(payload)
        context: dict = {"camera_source": camera.source}
        if payload.object_id:
            try:
                thread = await asyncio.to_thread(repository.thread, payload.object_id)
            except NotFoundError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            context["selected_thread"] = {
                "object": thread.object.model_dump(),
                "posts": [post.model_dump(mode="json") for post in thread.posts[-8:]],
            }
        frame = await asyncio.to_thread(camera.assistant_frame) if payload.include_camera else None
        if payload.include_camera and frame is None:
            raise HTTPException(status_code=503, detail="No fresh camera frame. Reconnect the camera or turn off camera sharing to chat.")
        if frame and is_visual_identification(payload.message):
            capture = await asyncio.to_thread(camera.memory_capture)
            matches = capture[2] if capture else []
            corrected = bool(re.search(r"\b(?:wrong|guessing|that is not|that's not)\b", payload.message, re.I))
            if corrected or len(matches) != 1 or matches[0].tier != "high":
                return AssistantResponse(
                    text="I'm not sure which object this is. Center one object and tell me what it is. Then I'll ask what comment you want to save. You can say cancel to skip.",
                    model=assistant.model, camera_used=True, camera_source=camera.source,
                    captured_at=frame[1], awaiting_description=True)
        context["camera_attached"] = frame is not None
        context["recognized_objects"] = [
            {"identity": item["identity_key"], "tier": item["tier"]}
            for item in camera.snapshot()["detections"]
        ] if frame else []
        try:
            answer = await assistant.answer(
                payload.message, [item.model_dump() for item in payload.history],
                json.dumps(context)[:16000],
                base64.b64encode(frame[0]).decode() if frame else None,
            )
        except AssistantError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        if frame and re.search(r"\b(?:looks? like|seems? (?:like|to be)|might be|could be|not sure|can't (?:tell|identify)|cannot (?:tell|identify))\b", answer, re.I):
            return AssistantResponse(
                text="I'm not confident about that object. Keep it centered and tell me what it is. Then I'll ask for the comment you want to save. Say cancel to skip.",
                model=assistant.model, camera_used=True, camera_source=camera.source,
                captured_at=frame[1], awaiting_description=True)
        return AssistantResponse(text=answer, model=assistant.model,
                                 camera_used=frame is not None, camera_source=camera.source,
                                 captured_at=frame[1] if frame else None)

    @app.get(
        "/api/diagnostics/performance", response_model=PerformanceDiagnostics
    )
    async def performance_diagnostics() -> PerformanceDiagnostics:
        return PerformanceDiagnostics.model_validate(camera.performance_snapshot())

    @app.get("/api/profiles", response_model=list[Profile])
    async def profiles() -> list[Profile]:
        return await asyncio.to_thread(repository.profiles)

    @app.get("/api/objects", response_model=list[ObjectSummary])
    async def objects() -> list[ObjectSummary]:
        return await asyncio.to_thread(repository.objects)

    @app.get(
        "/api/objects/by-identity/{identity_key}", response_model=ObjectSummary
    )
    async def object_by_identity(identity_key: str) -> ObjectSummary:
        record = await asyncio.to_thread(
            repository.object_by_identity, identity_key
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Object is not enrolled")
        return record

    @app.post(
        "/api/objects/enroll",
        response_model=ObjectSummary,
        status_code=status.HTTP_201_CREATED,
    )
    async def enroll_object(
        title: str = Form(...),
        description: str | None = Form(default=None),
        image: UploadFile = File(...),
    ) -> ObjectSummary:
        content = await image.read(10 * 1024 * 1024 + 1)
        if not content or len(content) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=413, detail="Enrolment image must be 1 byte–10 MB"
            )
        frame = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise HTTPException(
                status_code=422, detail="Enrolment file is not a readable image"
            )
        slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
        if not slug:
            raise HTTPException(status_code=422, detail="Title needs a letter or digit")
        digest = hashlib.sha1(content).hexdigest()[:8]
        object_id = f"{slug}-{digest}"
        enrolled_dir = app_settings.enrolled_dir
        enrolled_dir.mkdir(parents=True, exist_ok=True)
        reference_file = enrolled_dir / f"{object_id}.png"
        reference_file.write_bytes(content)
        try:
            relative = reference_file.relative_to(ROOT)
            reference_path = str(relative)
        except ValueError:
            reference_path = str(reference_file)
        if not camera.enroll_reference(object_id, frame):
            raise HTTPException(
                status_code=422,
                detail="That view has too little visible texture to recognise later",
            )
        record = await asyncio.to_thread(
            repository.enroll_object,
            object_id=object_id,
            title=title.strip(),
            description=description.strip() if description else None,
            reference_path=reference_path,
        )
        return record

    @app.post("/api/objects/enroll-live/scan", response_model=ScanResponse)
    async def scan_live(payload: ScanRequest) -> ScanResponse:
        """Stage 1 of creating an object: burst-scan only.

        Nothing is enrolled or persisted — the scan waits (5 min) for
        the user to review the crops and confirm creation.
        """
        if camera.source == "disabled":
            raise HTTPException(
                status_code=503,
                detail="Camera is disabled; live enrolment needs the camera",
            )
        scan_id, capture = await asyncio.to_thread(
            camera.create_pending_scan, payload.duration_seconds
        )
        if scan_id is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No usable view captured (sampled {capture.frames_sampled} "
                    f"frames, best sharpness {capture.best_sharpness:.0f}) — "
                    "hold the object inside the centre guide, in good light, "
                    "and slowly turn it"
                ),
            )
        return ScanResponse(
            scan_id=scan_id,
            captured_views=_thumbnails(capture.views),
            diagnostics=_diagnostics(capture, 0),
        )

    @app.post(
        "/api/objects/enroll-live/scans/{scan_id}/more", response_model=ScanResponse
    )
    async def scan_more(scan_id: str, payload: ScanRequest) -> ScanResponse:
        capture = await asyncio.to_thread(
            camera.extend_pending_scan, scan_id, payload.duration_seconds
        )
        if capture is None:
            raise HTTPException(
                status_code=404, detail="Scan not found or expired — scan again"
            )
        return ScanResponse(
            scan_id=scan_id,
            captured_views=_thumbnails(capture.views),
            diagnostics=_diagnostics(capture, 0),
        )

    @app.delete("/api/objects/enroll-live/scans/{scan_id}")
    async def discard_scan(scan_id: str) -> dict[str, bool]:
        if not camera.drop_pending_scan(scan_id):
            raise HTTPException(status_code=404, detail="Scan not found")
        return {"deleted": True}

    @app.post(
        "/api/objects/enroll-live",
        response_model=EnrollLiveResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def enroll_object_live(payload: EnrollLiveRequest) -> EnrollLiveResponse:
        """Stage 2: create the object from a reviewed pending scan.

        Only now are views enrolled, files written, and the object (and
        its thread) persisted.
        """
        capture = camera.get_pending_scan(payload.scan_id)
        if capture is None:
            raise HTTPException(
                status_code=404, detail="Scan not found or expired — scan again"
            )
        views = capture.views
        success, first_encoded = cv2.imencode(".png", views[0])
        if not success:
            raise HTTPException(status_code=422, detail="Captured view was unusable")
        object_id = _slug_object_id(payload.title, first_encoded.tobytes())

        enrolled_dir = app_settings.enrolled_dir
        enrolled_dir.mkdir(parents=True, exist_ok=True)
        reference_paths: list[str] = []
        enrolled_views: list[np.ndarray] = []
        for index, view in enumerate(views):
            # Enrolment gate is deliberately looser than recognition:
            # low-texture objects may enrol from few keypoints, while the
            # strict 15-inlier / 0.35 recognition bar prevents guessing.
            if not camera.enroll_reference(object_id, view, min_keypoints=5):
                continue
            ok, encoded = cv2.imencode(".png", view)
            if not ok:
                continue
            path = enrolled_dir / f"{object_id}-live-{index}.png"
            path.write_bytes(encoded.tobytes())
            reference_paths.append(_relative_reference(path))
            enrolled_views.append(view)
        if not reference_paths:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Captured {len(views)} view(s) from {capture.frames_sampled} "
                    "frames, but none had enough visible texture to enrol — "
                    "try better light or a less plain side of the object"
                ),
            )
        record = await asyncio.to_thread(
            repository.enroll_object,
            object_id=object_id,
            title=payload.title.strip(),
            description=payload.description.strip()
            if payload.description
            else None,
            reference_path=reference_paths[0],
            extra_reference_paths=tuple(reference_paths[1:]),
        )
        camera.drop_pending_scan(payload.scan_id)
        return EnrollLiveResponse(
            **record.model_dump(),
            captured_views=_thumbnails(enrolled_views),
            diagnostics=_diagnostics(capture, len(reference_paths)),
        )

    @app.post(
        "/api/objects/{object_id}/add-views", response_model=AddViewsResponse
    )
    async def add_views(object_id: str, payload: ScanRequest) -> AddViewsResponse:
        """Improve an existing object with another live burst of views.

        The object's identity and thread are untouched; the new angles
        are banked under the same identity (like tracked view banking).
        """
        record = await asyncio.to_thread(repository.object_by_id, object_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Object not found")
        if camera.source == "disabled":
            raise HTTPException(
                status_code=503,
                detail="Camera is disabled; adding views needs the camera",
            )
        capture = await asyncio.to_thread(
            camera.capture_enrollment_capture, payload.duration_seconds
        )
        if not capture.views:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No usable view captured (sampled {capture.frames_sampled} "
                    f"frames, best sharpness {capture.best_sharpness:.0f}) — "
                    "hold the object inside the centre guide and slowly turn it"
                ),
            )
        enrolled_dir = app_settings.enrolled_dir
        enrolled_dir.mkdir(parents=True, exist_ok=True)
        added = 0
        for view in capture.views:
            if not camera.enroll_reference(
                record.identity_key, view, min_keypoints=5
            ):
                continue
            ok, encoded = cv2.imencode(".png", view)
            if not ok:
                continue
            digest = hashlib.sha1(encoded.tobytes()).hexdigest()[:10]
            path = enrolled_dir / f"{record.id}-added-{digest}.png"
            if not path.exists():
                path.write_bytes(encoded.tobytes())
                await asyncio.to_thread(
                    repository.add_reference_path,
                    record.id,
                    _relative_reference(path),
                )
            added += 1
        if not added:
            raise HTTPException(
                status_code=422,
                detail="None of the captured views had enough texture to add",
            )
        return AddViewsResponse(
            object_id=record.id,
            reference_count=camera.reference_count(record.identity_key),
            diagnostics=_diagnostics(capture, added),
        )

    @app.post("/api/recognition/confirm")
    async def confirm_identity(payload: ConfirmIdentityRequest) -> dict[str, bool]:
        """Confirm a provisional sighting; banks that view for the object."""
        confirmed = await asyncio.to_thread(
            camera.confirm_identity, payload.identity_key
        )
        if not confirmed:
            raise HTTPException(
                status_code=404, detail="No current sighting of that object"
            )
        return {"confirmed": True}

    @app.delete("/api/objects/{object_id}")
    async def discard_object(object_id: str) -> dict[str, bool]:
        """Discard an enrolment (e.g. the captured crops were wrong).

        Only objects enrolled into the enrolled dir can be discarded,
        seeded demo objects cannot, and an object with posts is kept —
        discarding must never silently delete a conversation.
        """
        record = await asyncio.to_thread(repository.object_by_id, object_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Object not found")
        if await asyncio.to_thread(repository.post_count, object_id) > 0:
            raise HTTPException(
                status_code=409,
                detail="This object has posts; its enrolment cannot be discarded",
            )
        paths = await asyncio.to_thread(
            repository.object_reference_paths, object_id
        )
        enrolled_root = app_settings.enrolled_dir.resolve()
        files: list[Path] = []
        for raw in paths:
            candidate = Path(raw)
            resolved = (
                candidate if candidate.is_absolute() else ROOT / candidate
            ).resolve()
            if enrolled_root not in resolved.parents:
                raise HTTPException(
                    status_code=409,
                    detail="Only live/photo-enrolled objects can be discarded",
                )
            files.append(resolved)
        camera.remove_reference(record.identity_key)
        for path in files:
            path.unlink(missing_ok=True)
        await asyncio.to_thread(repository.delete_object, object_id)
        return {"deleted": True}

    @app.get("/api/objects/{object_id}/posts", response_model=ThreadResponse)
    async def thread(object_id: str) -> ThreadResponse:
        try:
            return await asyncio.to_thread(repository.thread, object_id)
        except NotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post(
        "/api/objects/{object_id}/posts",
        response_model=Post,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_post(object_id: str, payload: CreatePostRequest) -> Post:
        try:
            return await asyncio.to_thread(
                repository.create_post,
                object_id=object_id,
                author_id=payload.author_id,
                body=payload.body,
                parent_post_id=payload.parent_post_id,
                client_request_id=payload.client_request_id,
            )
        except NotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except InvalidReplyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/recognition", response_model=RecognitionResponse)
    async def recognition() -> RecognitionResponse:
        snapshot = camera.snapshot()
        identity_keys = [
            detection["identity_key"] for detection in snapshot["detections"]
        ]
        context = await asyncio.to_thread(
            repository.recognition_context, identity_keys
        )
        for detection in snapshot["detections"]:
            resolved = context.get(detection["identity_key"])
            if resolved is not None:
                detection["object"], detection["preview"] = resolved
        return RecognitionResponse.model_validate(snapshot)

    @app.get("/api/objects/{object_id}/reference")
    async def object_reference(object_id: str) -> FileResponse:
        paths = await asyncio.to_thread(repository.object_reference_paths, object_id)
        for stored in paths:
            path = (ROOT / stored).resolve()
            allowed = (app_settings.enrolled_dir.resolve(), (ROOT / "objects").resolve())
            if any(path.is_relative_to(root) for root in allowed) and path.is_file():
                return FileResponse(path, headers={"Cache-Control": "private, max-age=60"})
        raise HTTPException(status_code=404, detail="No saved object image")

    @app.get("/api/camera/stream")
    async def camera_stream() -> StreamingResponse:
        if camera.source == "disabled":
            raise HTTPException(status_code=503, detail="Camera is disabled")
        return StreamingResponse(
            camera.mjpeg_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/transcriptions", response_model=TranscriptionResponse)
    async def transcribe(audio: UploadFile = File(...)) -> TranscriptionResponse:
        content_type = (audio.content_type or "").split(";", 1)[0]
        if content_type not in SUPPORTED_AUDIO_TYPES:
            raise HTTPException(
                status_code=415,
                detail="Unsupported audio format. Record WebM, WAV, MP3, MP4, M4A, or OGG.",
            )
        content = await audio.read(MAX_AUDIO_BYTES + 1)
        if not content:
            raise HTTPException(status_code=422, detail="The recording is empty")
        if len(content) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Recording exceeds 25 MB")
        filename = audio.filename or "recording.webm"
        try:
            text = await transcription.transcribe(
                filename=filename, content_type=content_type, audio=content
            )
        except TranscriptionNotConfigured as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except TranscriptionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return TranscriptionResponse(text=text, provider=transcription.name)

    frontend_dist = ROOT / "frontend" / "dist"
    if frontend_dist.exists():
        assets = frontend_dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def frontend(path: str, request: Request) -> FileResponse:
            candidate = frontend_dist / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")

    return app


app = create_app()
