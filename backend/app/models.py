from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Profile(BaseModel):
    id: str
    display_name: str
    initials: str
    color: str


class ObjectSummary(BaseModel):
    id: str
    identity_key: str
    identity_kind: str = "instance"
    title: str
    description: str | None = None


class Post(BaseModel):
    id: int
    object_id: str
    author: Profile
    body: str
    created_at: datetime
    parent_post_id: int | None = None
    replies: list["Post"] = Field(default_factory=list)


class ThreadResponse(BaseModel):
    object: ObjectSummary
    posts: list[Post]
    updated_at: datetime | None


class ConversationPreview(BaseModel):
    author_name: str
    body: str
    reply_count: int


class CreatePostRequest(BaseModel):
    author_id: str
    body: str = Field(min_length=1, max_length=500)
    parent_post_id: int | None = None
    client_request_id: str = Field(min_length=8, max_length=80)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message cannot be empty")
        return cleaned


class Detection(BaseModel):
    identity_key: str
    confidence: float = 1.0
    method: str = "instance-features"
    tier: Literal["high", "provisional"] = "high"
    corners: list[list[float]]
    center: list[float]
    object: ObjectSummary | None = None
    preview: ConversationPreview | None = None


class ScanRequest(BaseModel):
    duration_seconds: float = Field(default=4.0, ge=3.0, le=5.0)


class EnrollLiveRequest(BaseModel):
    """Create an object from a reviewed pending scan."""

    scan_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class ConfirmIdentityRequest(BaseModel):
    identity_key: str = Field(min_length=1, max_length=200)


class EnrollmentDiagnostics(BaseModel):
    frames_sampled: int
    views_selected: int
    views_enrolled: int
    best_sharpness: float


class EnrollLiveResponse(ObjectSummary):
    # Base64 JPEG thumbnails of the exact centre crops that were enrolled,
    # so the user can see what the system thinks the object is.
    captured_views: list[str] = Field(default_factory=list)
    diagnostics: EnrollmentDiagnostics


class ScanResponse(BaseModel):
    scan_id: str
    captured_views: list[str] = Field(default_factory=list)
    diagnostics: EnrollmentDiagnostics


class AddViewsResponse(BaseModel):
    object_id: str
    reference_count: int
    diagnostics: EnrollmentDiagnostics


class RecognitionResponse(BaseModel):
    status: Literal["starting", "ready", "unavailable", "disabled"]
    source: Literal["camera", "fixture", "disabled"]
    message: str | None
    captured_at: datetime | None
    frame_width: int
    frame_height: int
    detections: list[Detection]


class HealthResponse(BaseModel):
    camera_name: str | None = None
    status: Literal["ok"] = "ok"
    camera_status: str
    camera_source: str
    transcription_status: str
    camera_index: int = 0
    llm_parser_enabled: bool = False
    assistant_status: str = "unavailable"
    assistant_model: str = ""
    assistant_message: str | None = None


class AssistantMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[AssistantMessage] = Field(default_factory=list, max_length=12)
    object_id: str | None = Field(default=None, max_length=200)
    include_camera: bool = True
    author_id: str = Field(default="guest", max_length=100)
    request_id: str | None = Field(default=None, min_length=8, max_length=80)
    awaiting_description: bool = False
    pending_edit_ids: list[int] = Field(default_factory=list, max_length=100)
    pending_edit_body: str = Field(default="", max_length=500)
    read_aloud: bool = False
    awaiting_note: bool = False
    awaiting_name: bool = False
    pending_delete_ids: list[int] = Field(default_factory=list, max_length=100)
    last_note_id: int | None = None
    deletion_id: str | None = Field(default=None, max_length=100)
    pending_title: str = Field(default="", max_length=80)
    pending_body: str = Field(default="", max_length=500)
    # Set after a bare "reply": the next utterance is posted under this note.
    awaiting_reply: bool = False
    pending_reply_to: int | None = None

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Say or type a question first")
        return value.strip()


class AssistantResponse(BaseModel):
    text: str
    model: str
    camera_used: bool
    camera_source: str
    captured_at: datetime | None = None
    awaiting_description: bool = False
    pending_edit_ids: list[int] = Field(default_factory=list, max_length=100)
    pending_edit_body: str = Field(default="", max_length=500)
    read_aloud: bool = False
    awaiting_note: bool = False
    awaiting_name: bool = False
    pending_delete_ids: list[int] = Field(default_factory=list, max_length=100)
    last_note_id: int | None = None
    deletion_id: str | None = Field(default=None, max_length=100)
    pending_title: str = Field(default="", max_length=80)
    pending_body: str = Field(default="", max_length=500)
    awaiting_reply: bool = False
    pending_reply_to: int | None = None
    deleted_note_ids: list[int] = Field(default_factory=list)
    memory_changed: bool = False
    saved_note: Post | None = None
    saved_object: ObjectSummary | None = None


class PerformanceDiagnostics(BaseModel):
    capture_fps: float
    recognition_fps: float
    stream_fps: float
    recognition_p50_ms: float
    recognition_p95_ms: float
    latest_frame_age_ms: float | None
    captured_sequence: int
    recognized_sequence: int
    encoded_sequence: int
    active_stream_clients: int
    active_reference_variants: int
    bank_persist_queue_depth: int
    bank_persist_dropped: int


class TranscriptionResponse(BaseModel):
    text: str
    provider: str


class ApiError(BaseModel):
    detail: str
