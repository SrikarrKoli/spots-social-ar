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
    corners: list[list[float]]
    center: list[float]
    object: ObjectSummary | None = None
    preview: ConversationPreview | None = None


class RecognitionResponse(BaseModel):
    status: Literal["starting", "ready", "unavailable", "disabled"]
    source: Literal["camera", "fixture", "disabled"]
    message: str | None
    captured_at: datetime | None
    frame_width: int
    frame_height: int
    detections: list[Detection]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    camera_status: str
    camera_source: str
    transcription_status: str


class TranscriptionResponse(BaseModel):
    text: str
    provider: str


class ApiError(BaseModel):
    detail: str
