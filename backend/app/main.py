from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .camera import CameraService
from .config import ROOT, Settings
from .database import Database, seed_demo
from .models import (
    ConversationPreview,
    CreatePostRequest,
    HealthResponse,
    ObjectSummary,
    Post,
    Profile,
    RecognitionResponse,
    ThreadResponse,
    TranscriptionResponse,
)
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
    database = Database(app_settings.database_path)
    repository = Repository(database)
    camera = CameraService(
        source=app_settings.camera_source,
        camera_index=app_settings.camera_index,
        fixture_path=app_settings.camera_fixture,
        width=app_settings.camera_width,
        height=app_settings.camera_height,
        detection_ttl_ms=app_settings.detection_ttl_ms,
        dictionary_name=app_settings.marker_dictionary,
    )
    transcription = build_transcription_provider(
        provider=app_settings.transcription_provider,
        api_key=app_settings.openai_api_key,
        model=app_settings.openai_transcription_model,
        prompt=app_settings.openai_transcription_prompt,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        seed_demo(database)
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

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            camera_status=camera.status,
            camera_source=camera.source,
            transcription_status=transcription.status,
        )

    @app.get("/api/profiles", response_model=list[Profile])
    async def profiles() -> list[Profile]:
        return await asyncio.to_thread(repository.profiles)

    @app.get("/api/objects", response_model=list[ObjectSummary])
    async def objects() -> list[ObjectSummary]:
        return await asyncio.to_thread(repository.objects)

    @app.get(
        "/api/objects/by-marker/{marker_id}", response_model=ObjectSummary
    )
    async def object_by_marker(marker_id: int) -> ObjectSummary:
        record = await asyncio.to_thread(repository.object_by_marker, marker_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Marker is not registered")
        return record

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
        for detection in snapshot["detections"]:
            object_record = await asyncio.to_thread(
                repository.object_by_marker, detection["marker_id"]
            )
            detection["object"] = object_record
            if object_record is not None:
                object_thread = await asyncio.to_thread(
                    repository.thread, object_record.id
                )
                if object_thread.posts:
                    preview_post = object_thread.posts[-1]
                    detection["preview"] = ConversationPreview(
                        author_name=preview_post.author.display_name,
                        body=preview_post.body,
                        reply_count=len(preview_post.replies),
                    )
        return RecognitionResponse.model_validate(snapshot)

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
