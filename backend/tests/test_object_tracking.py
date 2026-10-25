import cv2
import numpy as np

from backend.app.object_tracking import ObjectMotionTracker
from backend.app.recognition import RecognizedInstance


def scene(x, y, present=True):
    rng = np.random.default_rng(42)
    frame = np.full((360, 640, 3), 35, dtype=np.uint8)
    # Distinct static distractor; only the target should move.
    frame[40:150,450:560] = np.random.default_rng(23).integers(40,220,(110,110,3),dtype=np.uint8)
    texture = rng.integers(50,250,(110,110,3),dtype=np.uint8)
    if present:
        frame[y:y+110,x:x+110] = texture
    return frame


def measurement(x, y, tier='high'):
    return RecognizedInstance('moving-bottle',np.array([[x,y],[x+109,y],[x+109,y+109],[x,y+109]],np.float32),.9,'instance-features',tier)


def seeded():
    tracker = ObjectMotionTracker()
    tracker.update(scene(120,160),[measurement(120,160)],1.)
    tracker.update(scene(132,166),[measurement(132,166)],1.1)
    return tracker


def test_follows_moving_object_through_brief_identity_miss_not_static_distractor():
    tracker=seeded()
    result=tracker.update(scene(144,172),[],1.2)
    assert len(result)==1
    assert result[0].identity_key=='moving-bottle'
    assert result[0].method.endswith('+optical-flow')
    assert np.allclose(result[0].corners.mean(axis=0),[198.5,226.5],atol=2)
    result=tracker.update(scene(156,178),[],1.3)
    assert np.allclose(result[0].corners.mean(axis=0),[210.5,232.5],atol=2)


def test_hides_when_object_disappears_instead_of_holding_old_position():
    tracker=seeded()
    assert tracker.update(scene(132,166,present=False),[],1.2)==[]
    assert tracker.tracks=={}


def test_motion_cannot_keep_identity_alive_without_recent_recognition():
    tracker=seeded()
    for step in range(1,7):
        tracker.update(scene(132+step*3,166),[],1.1+step*.1)
    assert tracker.update(scene(153,166),[],1.81)==[]


def test_one_sighting_or_provisional_identity_never_gets_promoted_by_motion():
    for tier in ['high','provisional']:
        tracker=ObjectMotionTracker()
        tracker.update(scene(120,160),[measurement(120,160,tier)],1.)
        assert tracker.update(scene(132,166),[],1.1)==[]


def test_deleted_identity_is_not_resurrected_by_tracker():
    tracker=seeded()
    tracker.remove('moving-bottle')
    assert tracker.update(scene(144,172),[],1.2)==[]


def test_distant_new_scene_does_not_reuse_old_object():
    tracker=seeded()
    assert tracker.update(np.full((360,640,3),220,np.uint8),[],1.2)==[]


def test_camera_publishes_followed_position_and_removes_lost_marker(tmp_path,monkeypatch):
    from backend.app.camera import CameraService
    class Recognizer:
        detections=[]
        def detect(self,frame): return self.detections
    recognizer=Recognizer()
    camera=CameraService(source='disabled',camera_index=0,fixture_path=tmp_path/'none',width=640,height=360,detection_ttl_ms=2000,dictionary_name='DICT_4X4_50',recognizer=recognizer)
    clock=[10.]
    monkeypatch.setattr('backend.app.camera.time.monotonic',lambda:clock[0])
    for index,(x,y) in enumerate([(120,160),(132,166)]):
        clock[0]=10+index*.1
        recognizer.detections=[measurement(x,y)]
        camera._process_frame(scene(x,y))
    recognizer.detections=[]
    clock[0]=10.2
    camera._process_frame(scene(144,172))
    shown=camera.snapshot()['detections']
    assert len(shown)==1
    assert np.allclose(shown[0]['center'],[198.5,226.5],atol=2)
    clock[0]=10.3
    camera._process_frame(scene(144,172,present=False))
    assert camera.snapshot()['detections']==[]


def test_frozen_recognition_is_not_shown_for_full_old_ttl(tmp_path,monkeypatch):
    from backend.app.camera import CameraService
    class Recognizer:
        def detect(self,frame): return [measurement(120,160)]
    camera=CameraService(source='disabled',camera_index=0,fixture_path=tmp_path/'none',width=640,height=360,detection_ttl_ms=2000,dictionary_name='DICT_4X4_50',recognizer=Recognizer())
    clock=[10.]
    monkeypatch.setattr('backend.app.camera.time.monotonic',lambda:clock[0])
    camera._process_frame(scene(120,160))
    clock[0]=10.1
    camera._process_frame(scene(120,160))
    assert camera.snapshot()['detections']
    clock[0]=11.0
    assert camera.snapshot()['detections']==[]
