# Implementation log

## Kickoff answers (owner)
- Meta API: no access yet → research viability now, start build on Tesseract fallback path.
- Gnani: owner HAS the Vachana API key → ask for it securely at TTS wiring time, not before.
- Seed data: start from public sources for the 8-inscription MVP slice.

## Research: Meta Llama API viability (2026-11-10)
Sources: Meta/Llama docs via web search; mixed signals, treat as paper viability only.
- Hosted Llama API exists (api.llama.com, preview): OpenAI-compatible chat, API-key auth.
- Vision input: Llama 4 Maverick/Scout accept image blocks in chat. Fits "read text from images".
- Fine-tuning: supported on paper (Llama 3.3 8B named; "fine-tune on specialized datasets" + eval suite).
- Cautions: preview status, endpoints/models churning; some Oct-2026 sources report waitlist / catalog shifts
  toward third-party hosts (Together, Novita, Groq) and a separate Meta Model API (api.meta.ai) for Muse models.
  No access in hand, so nothing is empirically verified. 8 inscriptions is thin for fine-tuning a vision
  model — few-shot prompted reading may be the realistic MVP shape IF access arrives.
- Decision: MVP recognition = Tesseract custom baseline behind a `Recognizer` interface; Llama-vision
  adapter slots in later without touching the pipeline. Revisit when API access exists.

## Correction (owner): Meta Model API, not Llama
- Hosted Meta Model API (api.meta.ai/v1, OpenAI-compatible, self-serve): Muse Wonder/Spark/Ember accept
  image input → vision reading over the API is VIABLE (no training needed for few-shot/prompted reading).
- Hosted fine-tuning is NOT offered — SFT/RL exist only for open-weight models (Spark Open 816B, Glimmer 30B)
  via self-host post-training. Owner's "trained with our data" condition therefore resolves to: no training
  on the hosted API; recognition = prompted/few-shot Meta vision + Tesseract baseline fallback.
- Access: owner has no key yet → build the Recognizer interface + Tesseract path first; Meta adapter stubbed.
- Shell network is broken in this sandbox (TLS schannel failure) → all downloads via web_fetch + local copy
  from session tool-outputs.

## Research: Hultzsch source
- Archive.org hosts Vol II Part III full text (djvu.txt, DLI scan 2015.34589) + text PDF: 1891 Hultzsch,
  long public domain. Downloading to data/raw/hultzsch/ as the transcription/translation base.
- Printed Tamil in the scan needs Tamil-model re-OCR + hand correction per the design plan; English
  translations usable directly. Tamil OCR engine TBD (test Tesseract Tamil on the scan first).
- Sourced (2026-11-10): vol2-part3 (Nos. 63-78, 482K chars, 4 translations), vol2-part4-venkayya
  (Nos. 79+, texts only, 0 translations), vol2-part1-central-shrine (Nos. 1+, 2M chars, translations
  present as TRANSLATION. sections). All in data/raw/hultzsch/.
- 8 CC-licensed Thanjavur wall-inscription photos curated in data/mvp/photos.json with attribution.
  Photos hotlink to upload.wikimedia.org (local binary download blocked in sandbox).
- OCR reality check (No. 64): English intros/translations cleanable by hand; Tamil Text sections are
  total gibberish (need Tamil-model re-OCR of page images or epigraphist). Transliteration ground truth
  stays an open item; MVP retrieval bridges via entities (names/numbers/places).

## MVP slice built (2026-11-10)
- 8 entries (SII Nos. 9,10,11,12,32,40,42,43) in data/mvp/corpus.json: intro + cleaned
  translation + entities + photo link + raw source spans. Nos. 11 and 32 flagged partial
  (hard cases for honest-failure demos). Photo pairing UNVERIFIED throughout.
- data/mvp/ta.json: draft Tamil summaries, unverified, pending native review.

## Scaffold built (2026-11-10)
- server/app.py: FastAPI state machine, Reading Report schema, stub recognizer,
  entity retrieval, threshold-gated explain (0.6 provisional), STT/TTS stubs,
  demo_entry path for corpus-backed demos. Serves client/ statically.
- client/: vanilla-JS PWA (index, styles, app, manifest, sw). 5s voice windows
  then buttons-only; demo picker with attribution; tagged claims; Tamil/English
  re-render; responsive + reduced-motion aware.
- render.yaml (free tier, VOTS_MVP_THRESHOLD), server/tests/test_api.py,
  eval/ manifest+README (unlocked), data/README, root README.
- Verified here: all JSON valid; client routes resolve; corpus/photo/ta ids join.
  NOT verified here (no Python/Node in sandbox): pytest run, server smoke test.
  Those must pass on Render/dev machine before any demo claim.

## Voice phase (2026-11-10, owner approved)
- Gnani docs researched: TTS = Timbre v2.5 REST (raw WAV back), STT = Prisma v3.0
  REST with format=transliterate for Latin keyword matching. Spec's vachana-voice-v3
  preset names are outdated; voices now per-model (Asmita/Devika provisional).
- server/speech.py: raw-httpx wrapper, key from GNANI_API_KEY only, never logged.
- app.py: POST /voice (closed-set accept or tap fallback), GET /api/audio/{id}
  per-sentence synthesis, numbers spelled out for TTS, timeouts + 503 fallback.
- client: 16kHz WAV recorder for 5s windows, sequential audio queue + replay,
  per-sentence failure skips with text always shown.
- tests: 7 new (13 total), Gnani mocked, key-independent. httpx2 added to
  requirements-test.txt to silence the Starlette TestClient warning.
- Key handling: .env.example + .gitignore; Render dashboard env by owner; the key
  is never pasted in chat or code.
- Verification run (2026-11-10, project env, Python 3.15.2): 13 passed.
  Fixed on the way: tests/conftest.py sys.path setup, dual-style app import,
  single appmod resolution (a shadow `import app` copy had silently broken 2
  voice/audio mocks). Sandbox blocks TestClient sockets, so the suite runs
  unsandboxed; remaining warning is the known httpx2 notice.
