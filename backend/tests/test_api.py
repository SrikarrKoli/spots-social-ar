from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.conftest import make_test_settings


def post_payload(**overrides):
    payload = {
        "author_id": "guest",
        "body": "I’m in — doors open at seven.",
        "parent_post_id": None,
        "client_request_id": "test-request-0001",
    }
    payload.update(overrides)
    return payload


def test_seeded_demo_and_marker_resolution(client: TestClient):
    profiles = client.get("/api/profiles")
    assert profiles.status_code == 200
    assert {profile["id"] for profile in profiles.json()} == {
        "maya",
        "theo",
        "lina",
        "guest",
    }
    assert {item["id"] for item in client.get("/api/objects").json()} == {
        "concert-poster",
        "favorite-book",
    }

    marker = client.get("/api/objects/by-marker/7")
    assert marker.status_code == 200
    assert marker.json()["id"] == "concert-poster"

    thread = client.get("/api/objects/concert-poster/posts").json()
    assert thread["posts"][0]["body"] == "Anyone want to go Friday?"
    assert thread["posts"][0]["replies"][0]["author"]["id"] == "theo"


def test_post_persists_across_app_restart(database_path):
    settings = make_test_settings(database_path)
    with TestClient(create_app(settings)) as first_client:
        response = first_client.post(
            "/api/objects/concert-poster/posts", json=post_payload()
        )
        assert response.status_code == 201
        post_id = response.json()["id"]

    with TestClient(create_app(settings)) as second_client:
        thread = second_client.get(
            "/api/objects/concert-poster/posts"
        ).json()
        assert any(post["id"] == post_id for post in thread["posts"])


def test_create_is_idempotent(client: TestClient):
    first = client.post("/api/objects/concert-poster/posts", json=post_payload())
    second = client.post("/api/objects/concert-poster/posts", json=post_payload())
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    changed_target = client.post(
        "/api/objects/favorite-book/posts", json=post_payload()
    )
    assert changed_target.status_code == 409


def test_reply_must_match_object_and_top_level(client: TestClient):
    concert = client.get("/api/objects/concert-poster/posts").json()
    concert_parent = concert["posts"][0]
    concert_reply = concert_parent["replies"][0]

    wrong_object = client.post(
        "/api/objects/favorite-book/posts",
        json=post_payload(
            parent_post_id=concert_parent["id"],
            client_request_id="test-request-wrong-object",
        ),
    )
    assert wrong_object.status_code == 409

    nested = client.post(
        "/api/objects/concert-poster/posts",
        json=post_payload(
            parent_post_id=concert_reply["id"],
            client_request_id="test-request-nested-reply",
        ),
    )
    assert nested.status_code == 409


def test_message_is_trimmed_and_validated(client: TestClient):
    created = client.post(
        "/api/objects/concert-poster/posts",
        json=post_payload(
            body="   hello    from the poster   ",
            client_request_id="test-request-clean-message",
        ),
    )
    assert created.status_code == 201
    assert created.json()["body"] == "hello    from the poster"

    empty = client.post(
        "/api/objects/concert-poster/posts",
        json=post_payload(body="   ", client_request_id="test-request-empty"),
    )
    assert empty.status_code == 422


def test_disabled_transcription_is_explicit(client: TestClient):
    response = client.post(
        "/api/transcriptions",
        files={"audio": ("recording.webm", b"not-real-audio", "audio/webm")},
    )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
