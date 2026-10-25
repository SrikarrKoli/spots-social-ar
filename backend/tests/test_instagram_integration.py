from dataclasses import replace

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.restaurant_demo import seed_restaurant_demo
from backend.tests.conftest import make_test_settings


def test_restaurant_demo_preserves_existing_objects_and_user_edits(database_path):
    settings = replace(make_test_settings(database_path), restaurant_demo_enabled=True)
    app = create_app(settings)
    with TestClient(app) as client:
        objects = client.get('/api/objects').json()
        assert len(objects) == 6
        assert next(obj for obj in objects if obj['id'] == 'concert-poster')['title'] == 'Concert poster'
        menu = next(obj for obj in objects if obj['id'] == 'demo-menu-chicken-tikka')
        assert menu['identity_kind'] == 'demo'
        post = client.post(f"/api/objects/{menu['id']}/posts", json={
            'author_id': 'pravan', 'body': 'Keep this actual comment',
            'client_request_id': 'instagram-persistent-comment', 'parent_post_id': None,
        })
        assert post.status_code == 201
        with app.state.database.connect() as connection:
            connection.execute("UPDATE posts SET body = 'Edited demo note' WHERE seed_key = 'instagram-chicken-tikka'")
        seed_restaurant_demo(app.state.database)
        notes = client.get(f"/api/objects/{menu['id']}/posts").json()['posts']
        assert [note['body'] for note in notes] == ['Edited demo note', 'Keep this actual comment']
    with TestClient(create_app(settings)) as client:
        assert len(client.get('/api/objects/demo-menu-chicken-tikka/posts').json()['posts']) == 2


def test_reference_route_serves_only_saved_images_inside_allowed_directory(client, tmp_path):
    repository = client.app.state.repository
    enrolled = client.app.state.settings.enrolled_dir
    enrolled.mkdir()
    image = enrolled / 'safe.png'
    image.write_bytes(b'image-bytes')
    repository.enroll_object(object_id='safe', title='Safe', description=None, reference_path=str(image))
    assert client.get('/api/objects/safe/reference').content == b'image-bytes'
    private = tmp_path / 'private.txt'
    private.write_text('private')
    repository.add_reference_path('safe', str(private))
    image.unlink()
    assert client.get('/api/objects/safe/reference').status_code == 404
    assert client.get('/api/objects/missing/reference').status_code == 404
