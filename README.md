# Voice of the Stone — MVP

A web app that reads Chola-era Tamil inscriptions at Thanjavur and speaks
honest explanations. This MVP covers the **photo path** with 8 curated
inscriptions, Tamil + Indian English output, and stubbed recognizer/STT/TTS
behind interfaces. Full contract: `design-plan.md` (Final).

## Run locally

```sh
pip install -r server/requirements.txt
pip install -r server/requirements-test.txt   # pytest + httpx2 (silences the TestClient warning)
pytest server/tests
uvicorn app:app --app-dir server
```

Open http://127.0.0.1:8000 in a browser. Check phone/tablet/PC layouts with
Chrome DevTools resolution switching.

## Voice setup (Gnani)

Copy `.env.example` to `.env` and set `GNANI_API_KEY` (local only, never
committed). On Render, set `GNANI_API_KEY` in the dashboard under Environment.
Without a key the app runs text-only with stubbed audio; nothing breaks.
Voices default to Asmita (Tamil) and Devika (English) on Timbre v2.5 —
audition alternatives in the Gnani playground and override with
`VOTS_VOICE_TA` / `VOTS_VOICE_EN`.

## Deploy (Render)

Push this repo; `render.yaml` builds and starts the single web service
(API + static client). Threshold is set via `VOTS_MVP_THRESHOLD` (default 0.6,
provisional until calibration).

## Map

- `client/` — PWA shell (vanilla JS, no build step): onboarding with 5s voice
  windows, photo upload, demo corpus picker, review, tagged explanation.
- `server/` — FastAPI: session state machine, Reading Report schema,
  entity-overlap retrieval, threshold-gated explanation, STT/TTS stubs.
- `data/` — raw Hultzsch OCR (pristine) + cleaned 8-entry MVP slice + photos.
- `eval/` — test manifest (unlocked) + calibration/hardening checklist.
- `notes/implementation-log.md` — running build log.

## Status

- Working: full photo/demo flow end to end, claim tags, coverage statements,
  partial-translation flags, language re-render, recapture recovery, Gnani
  voice in (5s STT clips, closed-set match, tap fallback) and out
  (sentence-by-sentence TTS with queued playback). 13 API tests, all passing.
- Stubbed: recognition (canned; Tesseract/Meta next), Tamil rendering
  (draft, unverified).
- Voice needs `GNANI_API_KEY`; without it the app degrades to text-only.
- Note: this sandbox has no Python/Node runtimes, so tests and smoke checks
  run on your machine / Render, not here.
