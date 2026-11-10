"""MVP API tests: state machine, report contract, threshold gating.

Run on Render or any machine with Python:  pytest server/tests
(Cannot run in the current sandbox: no Python runtime there.)
"""
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def new_session():
    r = client.post("/api/sessions")
    assert r.status_code == 200
    return r.json()["session_id"]


def onboard(sid, lang="tamil"):
    r = client.post(f"/api/sessions/{sid}/onboarding",
                    json={"question": "q1", "mode": "button", "value": lang})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/sessions/{sid}/onboarding",
                    json={"question": "q2", "mode": "button", "value": "photo"})
    assert r.status_code == 200, r.text


def test_voice_onboarding_never_auto_accepts():
    sid = new_session()
    r = client.post(f"/api/sessions/{sid}/onboarding",
                    json={"question": "q1", "mode": "voice"})
    body = r.json()
    assert body["accepted"] is False
    assert body["requires_tap"] is True


def test_demo_path_full_story():
    sid = new_session()
    onboard(sid)
    r = client.post(f"/api/sessions/{sid}/captures", data={"demo_entry": "sii2-10"})
    assert r.status_code == 200, r.text
    report = r.json()["report"]
    assert report["coverage"]["confident"] == report["coverage"]["total"] == 2
    assert report["retrieval_match"]["inscription_id"] == "sii2-10"
    assert report["model_versions"]["recognizer"] == "stub-0.1"

    r = client.post(f"/api/sessions/{sid}/decision", json={"decision": "accept"})
    body = r.json()
    assert r.status_code == 200, r.text
    tags = [c["tag"] for c in body["claims"]]
    assert tags[0] == "stone"  # coverage sentence always first
    assert "published" in tags
    assert "4 of" not in body["text"]
    assert "2 of 2" in body["claims"][0]["text"]


def test_partial_translation_flagged_not_filled():
    sid = new_session()
    onboard(sid)
    client.post(f"/api/sessions/{sid}/captures", data={"demo_entry": "sii2-11"})
    r = client.post(f"/api/sessions/{sid}/decision", json={"decision": "accept"})
    texts = [c["text"] for c in r.json()["claims"]]
    assert any("skipping the gap" in t for t in texts)


def test_upload_path_reading_only():
    sid = new_session()
    onboard(sid)
    r = client.post(f"/api/sessions/{sid}/captures",
                    files={"photo": ("wall.jpg", b"fake-bytes")})
    assert r.status_code == 200, r.text
    report = r.json()["report"]
    assert report["coverage"] == {"confident": 3, "total": 4}


def test_language_switch_rerenders_no_rerecognize():
    sid = new_session()
    onboard(sid)
    client.post(f"/api/sessions/{sid}/captures", data={"demo_entry": "sii2-40"})
    client.post(f"/api/sessions/{sid}/decision", json={"decision": "accept"})
    r = client.post(f"/api/sessions/{sid}/explain", json={"language": "tamil"})
    body = r.json()
    assert body["quality_flag"] == "unverified"
    assert body["retrieval_match"]["inscription_id"] == "sii2-40"


def test_wrong_state_rejected():
    sid = new_session()
    r = client.post(f"/api/sessions/{sid}/captures", data={"demo_entry": "sii2-10"})
    assert r.status_code == 409  # still in onboarding
