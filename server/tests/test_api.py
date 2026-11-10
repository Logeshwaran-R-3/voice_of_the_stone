"""MVP API tests: state machine, report contract, threshold gating.

Run from the repo root:  pytest server/tests
"""
from fastapi.testclient import TestClient

try:
    from server.app import app
except ModuleNotFoundError:  # pytest launched from inside server/
    from app import app  # noqa

import sys as _sys

# The exact module object serving requests (never a second copy of it).
appmod = _sys.modules.get("server.app") or _sys.modules["app"]

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


class FakeSpeech:
    configured = True
    heard = "tamil"
    fail = False

    async def transcribe(self, wav):
        if FakeSpeech.fail:
            from speech import SpeechError
            raise SpeechError("down")
        return FakeSpeech.heard

    async def synthesize(self, text, language):
        if FakeSpeech.fail:
            from speech import SpeechError
            raise SpeechError("down")
        return b"RIFF" + text.encode("utf-8")[:8]


def test_voice_accepts_closed_set_keyword(monkeypatch):
    monkeypatch.setattr(appmod, "SPEECH", FakeSpeech())
    FakeSpeech.heard = "tamil please"
    FakeSpeech.fail = False
    sid = new_session()
    r = client.post(f"/api/sessions/{sid}/voice",
                    data={"question": "q1"},
                    files={"audio": ("clip.wav", b"wav-bytes")})
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["accepted"] is True
    assert body["language"] == "ta"


def test_voice_falls_back_to_tap_when_unsure(monkeypatch):
    monkeypatch.setattr(appmod, "SPEECH", FakeSpeech())
    FakeSpeech.heard = "hello hello"
    FakeSpeech.fail = False
    sid = new_session()
    r = client.post(f"/api/sessions/{sid}/voice",
                    data={"question": "q1"},
                    files={"audio": ("clip.wav", b"wav-bytes")})
    body = r.json()
    assert body["accepted"] is False
    assert body["requires_tap"] is True


def test_voice_falls_back_when_speech_down(monkeypatch):
    monkeypatch.setattr(appmod, "SPEECH", FakeSpeech())
    FakeSpeech.fail = True
    try:
        sid = new_session()
        r = client.post(f"/api/sessions/{sid}/voice",
                        data={"question": "q1"},
                        files={"audio": ("clip.wav", b"wav-bytes")})
        body = r.json()
        assert r.status_code == 200, r.text
        assert body["accepted"] is False
        assert body["requires_tap"] is True
    finally:
        FakeSpeech.fail = False


def test_voice_wrong_state_rejected():
    sid = new_session()
    r = client.post(f"/api/sessions/{sid}/voice",
                    data={"question": "q2"},
                    files={"audio": ("clip.wav", b"wav-bytes")})
    assert r.status_code == 409  # still in q1


def test_audio_sentences_served(monkeypatch):
    monkeypatch.setattr(appmod, "SPEECH", FakeSpeech())
    FakeSpeech.fail = False
    sid = new_session()
    onboard(sid)
    client.post(f"/api/sessions/{sid}/captures", data={"demo_entry": "sii2-40"})
    r = client.post(f"/api/sessions/{sid}/decision", json={"decision": "accept"})
    audio = r.json()["audio"]
    assert audio["status"] == "ready"
    assert len(audio["sentences"]) >= 2
    first = client.get(audio["sentences"][0]["url"])
    assert first.status_code == 200
    assert first.headers["content-type"] == "audio/wav"


def test_audio_unknown_id_404():
    assert client.get("/api/audio/doesnotexist").status_code == 404


def test_explain_without_key_stays_stubbed(monkeypatch):

    class Unkeyed:
        configured = False

    monkeypatch.setattr(appmod, "SPEECH", Unkeyed())
    sid = new_session()
    onboard(sid)
    client.post(f"/api/sessions/{sid}/captures", data={"demo_entry": "sii2-12"})
    r = client.post(f"/api/sessions/{sid}/decision", json={"decision": "accept"})
    assert r.json()["audio"]["status"] == "stubbed"
