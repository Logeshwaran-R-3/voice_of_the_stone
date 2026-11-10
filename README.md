# Voice of the Stone — MVP

A web app that reads Chola-era Tamil inscriptions at Thanjavur and speaks
honest explanations. This MVP covers the **photo path** with 8 curated
inscriptions, Tamil + Indian English output, and stubbed recognizer/STT/TTS
behind interfaces. Full contract: `design-plan.md` (Final).

## Run locally

```sh
pip install -r server/requirements.txt
uvicorn app:app --app-dir server
```

Open http://127.0.0.1:8000 in a browser. Check phone/tablet/PC layouts with
Chrome DevTools resolution switching.

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
  partial-translation flags, language re-render, recapture recovery.
- Stubbed: recognition (canned), voice in/out (Gnani key + Meta key pending),
  Tamil rendering (draft, unverified).
- Not yet runtime-verified here: this sandbox has no Python/Node runtimes, so
  `pytest server/tests` and the server smoke test must run on Render or a dev
  machine before any demo claim. No test has been seen passing yet.
