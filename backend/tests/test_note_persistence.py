"""End to end: a spoken note stays with its object across restarts and new viewpoints."""
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import cv2
import numpy as np
from fastapi.testclient import TestClient

from backend.app.main import create_app
from conftest import make_test_settings

PHOTO = Path(__file__).parents[2] / 'frontend/public/assets/authentic-menu-pov.jpg'


def object_image(top: int, left: int) -> np.ndarray:
    """A detailed physical object: a patch of a real photo, about 360x280."""
    photo = cv2.imread(str(PHOTO))
    return photo[top:top + 560, left:left + 720][::2, ::2].copy()


MUG = (1500, 300)
OTHER = (2800, 1200)


def view(item: np.ndarray, *, centre=(640, 360), scale=1.0, angle=0.0, background=90, seed=0) -> np.ndarray:
    """Place the object in a 1280x720 frame at a position, size and tilt."""
    rng = np.random.default_rng(seed)
    frame = np.clip(rng.normal(background, 6, (720, 1280, 3)), 0, 255).astype(np.uint8)
    height, width = item.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, scale)
    matrix[:, 2] += (centre[0] - width / 2, centre[1] - height / 2)
    mask = cv2.warpAffine(np.full((height, width), 255, np.uint8), matrix, (1280, 720))
    placed = cv2.warpAffine(item, matrix, (1280, 720))
    frame[mask > 0] = placed[mask > 0]
    return frame


def look_at(client: TestClient, monkeypatch, frame: np.ndarray) -> None:
    camera = client.app.state.camera
    monkeypatch.setattr(camera, 'memory_capture', lambda: (frame, datetime.now(UTC), camera.recognizer.detect(frame)))


def say(client: TestClient, message: str, request_id: str) -> dict:
    response = client.post('/api/assistant', json={'message': message, 'request_id': request_id, 'author_id': 'theo'})
    assert response.status_code == 200, response.text
    return response.json()


def test_note_stays_with_its_object_across_restart_and_new_viewpoints(database_path, monkeypatch):
    settings = make_test_settings(database_path)
    mug = object_image(*MUG)

    with TestClient(create_app(settings)) as client:
        monkeypatch.setattr(client.app.state.assistant, 'answer', AsyncMock(return_value='Lucky mug'))
        look_at(client, monkeypatch, view(mug))
        saved = say(client, 'Take a note: this is my lucky mug, please do not borrow it.', 'persist-note-0001')
        object_id = saved['saved_object']['id']
        assert saved['saved_object']['title'] == 'Lucky mug'
        assert saved['saved_note']['body'] == 'this is my lucky mug, please do not borrow it.'

    # A full restart: only what was written to disk survives.
    with TestClient(create_app(settings)) as restarted:
        camera = restarted.app.state.camera
        later = view(mug, centre=(430, 300), scale=0.8, angle=9, background=55, seed=7)

        # The reloaded fingerprint recognises the object moved, smaller, tilted, on a new background.
        matches = camera.recognizer.detect(later)
        assert [match.identity_key for match in matches if match.tier == 'high'] == [object_id]

        # And the live view shows the object with its note.
        for _ in range(3):
            camera._process_frame(later)
        recognition = restarted.get('/api/recognition').json()
        shown = [item for item in recognition['detections'] if item['identity_key'] == object_id]
        assert shown and shown[0]['object']['title'] == 'Lucky mug'
        assert shown[0]['preview']['body'] == 'this is my lucky mug, please do not borrow it.'

        # A second note from the new viewpoint joins the same object rather than making a new one.
        monkeypatch.setattr(restarted.app.state.assistant, 'answer', AsyncMock(return_value='Coffee cup'))
        look_at(restarted, monkeypatch, later)
        again = say(restarted, 'Leave a note saying it goes in the top cupboard.', 'persist-note-0002')
        assert again['saved_object']['id'] == object_id
        thread = restarted.get(f'/api/objects/{object_id}/posts').json()
        assert [post['body'] for post in thread['posts']] == [
            'this is my lucky mug, please do not borrow it.',
            'it goes in the top cupboard.',
        ]

        # A different object in the same spot never inherits the mug's notes.
        stranger = view(object_image(*OTHER), centre=(430, 300), scale=0.8, angle=9, background=55, seed=7)
        assert object_id not in {match.identity_key for match in camera.recognizer.detect(stranger)}


def test_second_profile_discovers_recognized_object_and_replies(client):
    mug = object_image(*MUG)
    encoded_ok, encoded = cv2.imencode('.png', mug)
    assert encoded_ok

    enrolled = client.post(
        '/api/objects/enroll',
        data={'title': 'Blue cafe mug'},
        files={'image': ('mug.png', encoded.tobytes(), 'image/png')},
    )
    assert enrolled.status_code == 201, enrolled.text
    object_id = enrolled.json()['id']

    note = client.post(
        f'/api/objects/{object_id}/posts',
        json={
            'author_id': 'maya',
            'body': 'The cardamom latte is worth trying.',
            'parent_post_id': None,
            'client_request_id': 'maya-mug-note-0001',
        },
    )
    assert note.status_code == 201, note.text

    later = view(mug, centre=(460, 320), scale=0.85, angle=-7, background=50, seed=11)
    matches = client.app.state.camera.recognizer.detect(later)
    recognized = next(match for match in matches if match.identity_key == object_id)
    assert recognized.tier == 'high'

    resolved = client.get(f'/api/objects/by-identity/{recognized.identity_key}')
    assert resolved.status_code == 200
    thread = client.get(f'/api/objects/{resolved.json()["id"]}/posts').json()
    assert thread['posts'][0]['author']['id'] == 'maya'
    assert thread['posts'][0]['body'] == 'The cardamom latte is worth trying.'

    reply = client.post(
        f'/api/objects/{object_id}/posts',
        json={
            'author_id': 'guest',
            'body': 'I will order that next time.',
            'parent_post_id': note.json()['id'],
            'client_request_id': 'guest-mug-reply-0001',
        },
    )
    assert reply.status_code == 201, reply.text
    updated = client.get(f'/api/objects/{object_id}/posts').json()
    assert updated['posts'][0]['replies'][0]['author']['id'] == 'guest'
    assert updated['posts'][0]['replies'][0]['body'] == 'I will order that next time.'
