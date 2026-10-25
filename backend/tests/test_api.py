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


def test_seeded_demo_and_identity_resolution(client: TestClient):
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

    identity = client.get("/api/objects/by-identity/concert-poster")
    assert identity.status_code == 200
    assert identity.json()["id"] == "concert-poster"
    assert identity.json()["identity_key"] == "concert-poster"
    assert "marker_id" not in identity.json()

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


def test_enroll_object_from_photo(client: TestClient):
    import io

    import cv2
    import numpy as np

    rng = np.random.default_rng(3)
    image = np.full((240, 320, 3), (40, 60, 90), np.uint8)
    for _ in range(120):
        x, y = int(rng.integers(0, 300)), int(rng.integers(0, 220))
        cv2.circle(image, (x, y), 5, (200, 180, 60), -1)
    cv2.putText(image, "BLUE MUG", (30, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)
    success, encoded = cv2.imencode(".png", image)
    assert success

    response = client.post(
        "/api/objects/enroll",
        data={"title": "Blue mug"},
        files={"image": ("mug.png", io.BytesIO(encoded.tobytes()), "image/png")},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["title"] == "Blue mug"
    assert created["identity_key"] == created["id"]
    assert client.get(f"/api/objects/by-identity/{created['identity_key']}").status_code == 200
