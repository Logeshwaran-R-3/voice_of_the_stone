"""Voice of the Stone - MVP server (single Render service: API + static client).

Implements the design-plan contracts with stubbed recognizer/STT/TTS behind
interfaces: session state machine, Reading Report schema, threshold-gated
explanation, entity-overlap retrieval over the 8-entry MVP corpus.
Real adapters (Tesseract, Meta Model API vision, Gnani) slot in later.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from speech import Speech, SpeechError

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "mvp"

with open(DATA / "corpus.json", encoding="utf-8") as f:
    CORPUS = json.load(f)["entries"]
with open(DATA / "photos.json", encoding="utf-8") as f:
    PHOTOS = {p["id"]: p for p in json.load(f)["photos"]}
try:
    with open(DATA / "ta.json", encoding="utf-8") as f:
        TA_SUMMARIES = json.load(f)
except FileNotFoundError:
    TA_SUMMARIES = {}

# Provisional until the first calibration run sets it (design plan 12).
THRESHOLD = float(os.environ.get("VOTS_MVP_THRESHOLD", "0.6"))

# MVP closed sets (Q3 narrow scope: Tamil + Indian English, photo path only).
LANGUAGES = {"tamil": "ta", "indian english": "en-IN", "english": "en-IN"}
MODES = {"photo", "upload"}

app = FastAPI(title="Voice of the Stone (MVP)")


# ---------------------------------------------------------------- models
class ScopeLabel(str, Enum):
    in_scope = "in-scope"
    out_of_scope = "out-of-scope"
    no_text = "no-text"


class State(str, Enum):
    start = "start"
    q1 = "onboarding_q1"
    q2 = "onboarding_q2"
    capture = "capture"
    processing = "processing"
    confirmation = "confirmation"
    explanation = "explanation"
    followup = "follow-up"


class Glyph(BaseModel):
    char: str
    conf: float
    status: str = "ok"  # ok | unrecognized | seam-disagree


class Line(BaseModel):
    line_id: int
    region: dict[str, Any] = Field(default_factory=dict)
    text: str = ""
    glyphs: list[Glyph] = Field(default_factory=list)
    calibrated_score: float = 0.0
    status: str = "skipped"  # spoken | skipped | partial


class Claim(BaseModel):
    id: str
    text: str
    tag: str  # stone | published | interpretation


class Report(BaseModel):
    report_id: str
    session_id: str
    model_versions: dict[str, str]
    scope_result: dict[str, Any]
    lines: list[Line]
    seams: list[dict[str, Any]] = Field(default_factory=list)
    continuation_flag: bool = False
    retrieval_match: Optional[dict[str, Any]] = None
    coverage: dict[str, int]
    claims: list[Claim] = Field(default_factory=list)


class Session(BaseModel):
    id: str
    state: State = State.start
    language: Optional[str] = None
    mode: Optional[str] = None
    report: Optional[Report] = None


SESSIONS: dict[str, Session] = {}


def get_session(sid: str) -> Session:
    try:
        return SESSIONS[sid]
    except KeyError:
        raise HTTPException(404, "unknown session")


def need_state(s: Session, *allowed: State) -> None:
    if s.state not in allowed:
        raise HTTPException(409, f"state is {s.state}, need one of {[a.value for a in allowed]}")


# ------------------------------------------------------- recognizer Ports
class Recognizer:
    """Interface real adapters (Tesseract, Meta vision) will implement."""

    name = "stub-0.1"

    def read(self, image: bytes, filename: str) -> dict[str, Any]:
        raise NotImplementedError


class StubRecognizer(Recognizer):
    """Deterministic canned reading: 3 confident lines + 1 unrecognized.

    Provenance is labeled stub in every report; never mistaken for real output.
    """

    def read(self, image: bytes, filename: str) -> dict[str, Any]:
        del image, filename
        return {
            "scope": {"label": "in-scope", "confidence": 0.62},
            "lines": [
                {"text": "[canned] svasti sri ... rajendra-chola ...", "score": 0.81},
                {"text": "[canned] ... 104 kasu ... chandesvaradeva ...", "score": 0.77},
                {"text": "[canned] ... tanjavur ...", "score": 0.66},
                {"text": "", "score": 0.12},
            ],
        }


RECOGNIZER: Recognizer = StubRecognizer()

def _load_dotenv() -> None:
    """Local-dev convenience: read repo-root .env (Render uses dashboard env)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


_load_dotenv()
SPEECH = Speech()
AUDIO_CACHE: dict[str, tuple[str, str]] = {}  # id -> (sentence, language)

NUMBER_WORDS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
                "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
                "10": "ten", "11": "eleven", "12": "twelve", "13": "thirteen",
                "14": "fourteen", "15": "fifteen", "16": "sixteen",
                "17": "seventeen", "18": "eighteen", "19": "nineteen",
                "20": "twenty"}


def sayable(text: str) -> str:
    """Spell out small numbers so TTS reads them as words, not digits."""
    return re.sub(r"\b\d+\b", lambda m: NUMBER_WORDS.get(m.group(0), m.group(0)), text)


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    out: list[str] = []
    for p in parts:
        while len(p) > 450:  # keep each TTS call short; split on word boundary
            cut = p.rfind(" ", 0, 450)
            cut = cut if cut > 0 else 450
            out.append(p[:cut])
            p = p[cut:].strip()
        out.append(p)
    return out


def audio_payload(text: str, language: str) -> dict[str, Any]:
    if not SPEECH.configured:
        return {"status": "stubbed",
                "detail": "Gnani TTS wires up when the API key is provided."}
    if len(AUDIO_CACHE) > 500:
        AUDIO_CACHE.clear()
    sentences = []
    for sent in split_sentences(sayable(text)):
        aid = uuid.uuid4().hex[:12]
        AUDIO_CACHE[aid] = (sent, language)
        sentences.append({"id": aid, "url": f"/api/audio/{aid}"})
    return {"status": "ready", "sentences": sentences}


VOICE_KEYWORDS = {
    "q1": {"tamil": ["tamil", "tamizh", "thamil"],
           "english": ["english", "angilam", "ingili"]},
    "q2": {"photo": ["photo", "upload", "picture", "camera", "file"]},
}
VOICE_DEFAULT = {"q1": "tamil", "q2": "photo"}


def match_voice(transcript: str, question: str) -> tuple[Optional[str], float]:
    toks = _tokens(transcript)
    for value, keys in VOICE_KEYWORDS[question].items():
        if toks & set(keys):
            return value, 1.0
    return None, 0.0


# ------------------------------------------------------------- retrieval
def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower())) - {
        "the", "and", "for", "with", "from", "that", "this", "into",
    }


def retrieve(reading_text: str) -> Optional[dict[str, Any]]:
    """Entity-overlap match of a reading against corpus entries."""
    toks = _tokens(reading_text)
    best: Optional[dict[str, Any]] = None
    for e in CORPUS:
        bag = " ".join(e["translation"] + [e["intro"]] +
                       e["entities"]["persons"] + e["entities"]["places"] +
                       e["entities"]["numbers"])
        overlap = toks & _tokens(bag)
        sim = len(overlap) / max(1, len(toks))
        if best is None or sim > best["similarity"]:
            best = {"inscription_id": e["id"], "ref": f"SII II No. {e['sii_no']}",
                    "similarity": round(sim, 3)}
    if best and best["similarity"] >= 0.2:
        return best
    return None


# ------------------------------------------------------------ pipeline
def build_report(session_id: str, reading: dict[str, Any],
                 demo_entry: Optional[dict[str, Any]] = None) -> Report:
    lines = []
    for i, ln in enumerate(reading["lines"], 1):
        score = ln["score"]
        if score >= THRESHOLD:
            status = "spoken"
        elif ln["text"]:
            status = "partial"
        else:
            status = "skipped"
        glyphs = ([Glyph(char="?", conf=score, status="unrecognized")]
                  if not ln["text"] else [])
        lines.append(Line(line_id=i, text=ln["text"], glyphs=glyphs,
                          calibrated_score=score, status=status))
    confident = sum(1 for ln in lines if ln.status == "spoken")
    match = ({"inscription_id": demo_entry["id"],
              "ref": f"SII II No. {demo_entry['sii_no']}", "similarity": 1.0}
             if demo_entry else retrieve(" ".join(ln.text for ln in lines)))
    return Report(
        report_id=uuid.uuid4().hex[:12],
        session_id=session_id,
        model_versions={"recognizer": RECOGNIZER.name, "scope_clf": "stub-0.1",
                        "calibrator": "provisional-0.6"},
        scope_result=reading["scope"],
        lines=lines,
        continuation_flag=False,
        retrieval_match=match,
        coverage={"confident": confident, "total": len(lines)},
    )


def explain(report: Report, language: str) -> dict[str, Any]:
    """Threshold-gated explanation (Q8). Claims carry truthfulness tags."""
    cov = report.coverage
    spoken = [ln for ln in report.lines if ln.status == "spoken"]
    mean_score = (sum(ln.calibrated_score for ln in spoken) / len(spoken)
                  if spoken else 0.0)
    claims: list[Claim] = [Claim(
        id="c0",
        text=(f"I could read {cov['confident']} of {cov['total']} lines confidently."),
        tag="stone")]
    recovery = None
    entry = None
    if report.retrieval_match:
        entry = next((e for e in CORPUS
                      if e["id"] == report.retrieval_match["inscription_id"]), None)
    if mean_score >= THRESHOLD and entry:
        for i, para in enumerate(entry["translation"], 1):
            claims.append(Claim(id=f"c{i}", text=para, tag="published"))
        if entry.get("translation_partial"):
            claims.append(Claim(id="cx", text=("Part of this translation is missing "
                                              "from the scan; I am skipping the gap, not guessing it."),
                                tag="stone"))
    elif mean_score >= THRESHOLD:
        for ln in spoken:
            claims.append(Claim(id=f"c{ln.line_id}", text=f"Line {ln.line_id}: {ln.text}",
                                tag="stone"))
        claims.append(Claim(id="cx", text=("No published match found, so this is "
                                          "reading only."), tag="stone"))
    else:
        for ln in spoken:
            claims.append(Claim(id=f"c{ln.line_id}", text=f"Line {ln.line_id}: {ln.text}",
                                tag="stone"))
        claims.append(Claim(id="cx", text=("That is all I could read reliably. "
                                          "A clearer photo may help."), tag="stone"))
        recovery = {"action": "recapture",
                    "reason": "below confidence threshold",
                    "guidance": "Hold steady, add light, and keep the text square in frame."}
    report.claims = claims
    if language == "ta":
        flag: str = "unverified"
        summary = (TA_SUMMARIES.get(entry["id"]) if entry else None) or \
            "[Tamil rendering not yet available for this reading.]"
        text = f"{claims[0].text}\n{summary}"
    else:
        flag = "verified"
        text = "\n".join(c.text for c in claims)
    return {"claims": [c.model_dump() for c in claims], "text": text,
            "language": language, "quality_flag": flag,
            "audio": audio_payload(text, language),
            "recovery": recovery,
            "retrieval_match": report.retrieval_match}

# ------------------------------------------------------------ endpoints
class OnboardingIn(BaseModel):
    question: str  # q1 | q2
    mode: str  # voice | button
    value: Optional[str] = None


@app.post("/api/sessions")
def create_session() -> dict[str, str]:
    s = Session(id=uuid.uuid4().hex[:12], state=State.q1)
    SESSIONS[s.id] = s
    return {"session_id": s.id, "state": s.state.value,
            "prompt": "Vanakkam. Hello. Which language should I speak? / Naan eppadi pesa?."}


@app.post("/api/sessions/{sid}/onboarding")
def onboarding(sid: str, body: OnboardingIn) -> dict[str, Any]:
    s = get_session(sid)
    if body.question == "q1":
        need_state(s, State.q1)
        if body.mode == "voice":
            # STT stub: never confident -> client highlights guess, requires tap.
            return {"accepted": False, "guess": "tamil", "confidence": 0.0,
                    "requires_tap": True, "state": s.state.value,
                    "detail": "Voice heard; tap to confirm. (STT stub: Gnani key pending.)"}
        code = LANGUAGES.get((body.value or "").strip().lower())
        if not code:
            raise HTTPException(400, "choose Tamil or Indian English")
        s.language = code
        s.state = State.q2
        return {"accepted": True, "language": s.language, "state": s.state.value}
    if body.question == "q2":
        need_state(s, State.q2)
        if body.mode == "voice":
            return {"accepted": False, "guess": "photo", "confidence": 0.0,
                    "requires_tap": True, "state": s.state.value,
                    "detail": "Voice heard; tap to confirm. (STT stub: Gnani key pending.)"}
        if (body.value or "").strip().lower() not in MODES:
            raise HTTPException(400, "MVP supports photo upload only")
        s.mode = "photo"
        s.state = State.capture
        return {"accepted": True, "mode": s.mode, "state": s.state.value}
    raise HTTPException(400, "question must be q1 or q2")


@app.post("/api/sessions/{sid}/captures")
async def capture(sid: str, demo_entry: Optional[str] = Form(None),
                  photo: Optional[UploadFile] = File(None)) -> dict[str, Any]:
    s = get_session(sid)
    need_state(s, State.capture)
    s.state = State.processing
    entry = None
    if demo_entry:
        entry = next((e for e in CORPUS if e["id"] == demo_entry), None)
        if entry is None:
            s.state = State.capture
            raise HTTPException(400, "unknown demo_entry id")
        reading = {"scope": {"label": "in-scope", "confidence": 0.9},
                   "lines": [{"text": f"[demo] {p[:80]}", "score": 0.9}
                             for p in entry["translation"][:3]] or
                   [{"text": "", "score": 0.1}]}
    elif photo is not None:
        blob = await photo.read()
        if not blob:
            s.state = State.capture
            raise HTTPException(400, "empty photo upload")
        reading = RECOGNIZER.read(blob, photo.filename or "upload.jpg")
    else:
        s.state = State.capture
        raise HTTPException(400, "send a photo or a demo_entry id")
    if reading["scope"]["label"] != "in-scope":
        s.state = State.capture
        return {"state": s.state.value, "failure": {
            "kind": "wrong-script" if reading["scope"]["label"] == "out-of-scope"
                    else "no-text",
            "message": "I could not find Chola-era Tamil text in that photo."}}
    s.report = build_report(s.id, reading, entry)
    s.state = State.confirmation
    return {"state": s.state.value, "report": s.report.model_dump()}


@app.get("/api/sessions/{sid}/report")
def get_report(sid: str) -> dict[str, Any]:
    s = get_session(sid)
    need_state(s, State.confirmation, State.explanation, State.followup)
    assert s.report is not None
    return {"state": s.state.value, "report": s.report.model_dump()}


class DecisionIn(BaseModel):
    decision: str  # accept | recapture


@app.post("/api/sessions/{sid}/decision")
def decide(sid: str, body: DecisionIn) -> dict[str, Any]:
    s = get_session(sid)
    need_state(s, State.confirmation)
    if body.decision == "recapture":
        s.state = State.capture
        s.report = None
        return {"state": s.state.value}
    if body.decision != "accept":
        raise HTTPException(400, "decision must be accept or recapture")
    assert s.report is not None and s.language is not None
    s.state = State.explanation
    return {"state": s.state.value, **explain(s.report, s.language)}


class ExplainIn(BaseModel):
    language: str  # re-render from stored report; never re-runs recognition


@app.post("/api/sessions/{sid}/explain")
def re_explain(sid: str, body: ExplainIn) -> dict[str, Any]:
    s = get_session(sid)
    need_state(s, State.explanation, State.followup)
    assert s.report is not None
    code = LANGUAGES.get(body.language.strip().lower(), body.language)
    if code not in ("ta", "en-IN"):
        raise HTTPException(400, "MVP languages: Tamil, Indian English")
    s.language = code
    s.state = State.followup
    return {"state": s.state.value, **explain(s.report, code)}


@app.post("/api/sessions/{sid}/voice")
async def voice_answer(sid: str, question: str = Form(...),
                       audio: UploadFile = File(...)) -> dict[str, Any]:
    """One 5s onboarding clip -> closed-set match. Never auto-accepts unsure."""
    s = get_session(sid)
    if question == "q1":
        need_state(s, State.q1)
    elif question == "q2":
        need_state(s, State.q2)
    else:
        raise HTTPException(400, "question must be q1 or q2")
    blob = await audio.read()
    transcript = ""
    if blob:
        try:
            transcript = await SPEECH.transcribe(blob)
        except SpeechError:
            transcript = ""
    value, conf = match_voice(transcript, question)
    if value and conf >= 1.0:
        if question == "q1":
            s.language = "ta" if value == "tamil" else "en-IN"
            s.state = State.q2
            return {"accepted": True, "language": s.language,
                    "state": s.state.value, "heard": transcript}
        s.mode = "photo"
        s.state = State.capture
        return {"accepted": True, "mode": s.mode, "state": s.state.value,
                "heard": transcript}
    return {"accepted": False, "guess": value or VOICE_DEFAULT[question],
            "confidence": 0.0, "requires_tap": True, "state": s.state.value,
            "heard": transcript,
            "detail": "Voice heard; tap to confirm."}


@app.get("/api/audio/{aid}")
async def audio(aid: str) -> Response:
    try:
        text, language = AUDIO_CACHE[aid]
    except KeyError:
        raise HTTPException(404, "unknown audio")
    try:
        blob = await SPEECH.synthesize(text, language)
    except SpeechError as e:
        raise HTTPException(503, f"speech unavailable: {e}")
    return Response(content=blob, media_type="audio/wav")


@app.get("/api/corpus")
def corpus() -> dict[str, Any]:
    out = []
    for e in CORPUS:
        photo = PHOTOS.get(e["photo_id"], {})
        out.append({"id": e["id"], "sii_no": e["sii_no"], "king": e["king"],
                    "location": e["location"], "intro": e["intro"],
                    "translation_partial": e.get("translation_partial", False),
                    "photo": {"url": photo.get("url"), "title": photo.get("title"),
                              "artist": photo.get("artist"),
                              "license": photo.get("license")}})
    return {"entries": out, "pairing_status": "unverified"}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "threshold": str(THRESHOLD),
            "recognizer": RECOGNIZER.name,
            "voice": "configured" if SPEECH.configured else "unconfigured"}


CLIENT = ROOT / "client"


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(CLIENT / "index.html")


@app.get("/sw.js", include_in_schema=False)
def sw() -> FileResponse:
    return FileResponse(CLIENT / "sw.js")


app.mount("/static", StaticFiles(directory=CLIENT), name="static")
