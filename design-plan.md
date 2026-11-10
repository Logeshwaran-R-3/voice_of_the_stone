# Voice of the Stone — System Design Plan (from Spec v0.1)

> Status: **Final** — accepted by the owner. Scope contract (§12) in force. Implementation still needs a separate explicit request.

Source: `Chola-Era Tamil Inscription Reader System Specification v0.1` (design only, no code yet).
Scope: Chola-era Tamil script, Thanjavur (Brihadeeswarar) first; PWA + backend; Gnani Vachana TTS / Prisma STT for voice.
Principle: truthfulness over fluency — say what was read, what was not, and what is interpretation.

## 1. What the system is

Two capture paths, one truth pipeline:

- **Photo path:** user uploads 1+ photos → preprocess → stitch if needed → segment → recognize → Reading Report → explanation → TTS.
- **Live path:** PWA scores frames on-device, uploads keyframes only (A1) → server stitches → same pipeline. Audio is the only continuous stream.

The **Reading Report** is the single source of truth. All speech and all language renderings derive from it. Nothing spoken may add names, numbers, dates, or places not in the confirmed reading or a matched publication.

Out of v1 (do not design for): other eras/scripts, other sites, wake word, voice cloning, offline use, text editing (v2 option).

## 2. Architecture

### 2.1 Components

**Client — PWA (framework TBD, recommend one: React/Vite + TypeScript or SvelteKit)**
- Routes: `/onboarding`, `/capture`, `/processing`, `/review`, `/explanation`.
- Responsibilities: camera/mic access, frame-quality scoring, onboarding UI (5-sec voice window + buttons), audio playback, session UI, retention/delete controls.
- No recognition on-device in v1.

**Backend — Python + FastAPI (recommended), modular services**
- `api-gateway` + `session-manager`: session lifecycle, state machine enforcement.
- `preprocessing`: perspective/deskew, illumination normalization, denoise (OpenCV).
- `stitching`: keyframe/mosaic alignment with seam scoring (OpenCV).
- `segmentation`: layout + line segmentation.
- `recognizer`: scope classifier → glyph/line recognition (Tesseract baseline → CRNN+CTC target).
- `lexicon-service`: Chola-era lexicon lookup (match / near-match / unknown).
- `calibration`: line-score calibration (conformal-style, to validate) + Reading Report builder.
- `retrieval`: published inscription index (Hultzsch etc.), returns match or none.
- `explanation`: claim tagging + LLM draft (strictly from claims) + multilingual rendering + name/number check.
- `speech-service`: wraps Gnani STT (onboarding only) and TTS (all output), sentence-by-sentence synthesis.
- Stores: image store (retention policy), corpus/lexicon DB, search index (product TBD — Postgres FTS or SQLite FTS to start, vector later if needed), session store.

### 2.2 Data flow

```
capture → preprocess → stitch? → segment lines → recognize
  → lexicon check → calibrate → Reading Report (stored w/ model versions)
  → retrieval match → claims → render in chosen language → TTS → playback
```

Language change re-renders from the stored report; recognition never re-runs.

## 3. Key data contracts

### 3.1 Reading Report (per capture / per mosaic) — JSON sketch

```json
{
  "report_id": "uuid",
  "session_id": "uuid",
  "model_versions": {"recognizer": "…", "scope_clf": "…", "calibrator": "…"},
  "scope_result": {"label": "in-scope|out-of-scope|no-text", "confidence": 0.0},
  "lines": [
    {
      "line_id": 1,
      "region": {"x": 0, "y": 0, "w": 0, "h": 0, "source_frame": "f12"},
      "text": "…",
      "glyphs": [{"char": "…", "conf": 0.0, "status": "ok|unrecognized|seam-disagree"}],
      "word_matches": [{"span": [0, 5], "verdict": "match|near|unknown"}],
      "calibrated_score": 0.0,
      "status": "spoken|skipped|partial"
    }
  ],
  "seams": [{"seam_id": 1, "quality": 0.0, "affected_lines": [3]}],
  "continuation_flag": true,
  "retrieval_match": {"inscription_id": "…", "ref": "Hultzsch …", "similarity": 0.0},
  "coverage": {"confident": 4, "total": 7},
  "claims": [{"id": "c1", "text": "…", "tag": "stone|published|interpretation"}]
}
```

Rules: unknown glyphs stay marked, never replaced by nearest class; scope classifier must output "none of these"; seam-disputed glyphs are read from source frames and accepted only on agreement.

### 3.2 Session state machine

`start → onboarding_q1 → onboarding_q2 → capture → processing → confirmation → explanation → follow-up`.
Failure states (each with spoken + visual message): no-text, wrong-script, too-blurry, stitch-failed, service-unavailable.

### 3.3 API sketch (FastAPI)

- `POST /sessions` → create session.
- `POST /sessions/{id}/onboarding` `{question, mode: voice|button, payload}` → next question or capture config. Voice path: single 5-sec window per question, closed-set match on 12 language names / 2 capture modes; low confidence → highlight guess, require tap; no voice retry.
- `POST /sessions/{id}/captures` (multipart photos) → capture id.
- `POST /sessions/{id}/keyframes` (live path, stills + quality meta) → mosaic job.
- `GET /sessions/{id}/report` → Reading Report.
- `POST /sessions/{id}/decision` `{accept|recapture}`.
- `POST /sessions/{id}/explain` `{language}` → claims + rendered text + audio job.
- `GET /sessions/{id}/audio/{sentence_id}` (stream) or WebSocket for streaming TTS.
- `DELETE /sessions/{id}/images` → user deletion per retention policy.

## 4. Component designs

### 4.1 Onboarding + voice input
- Bilingual prompt (Tamil + English) via TTS at start; language picker + stream/upload buttons visible immediately.
- STT: Gnani Prisma `vachana-stt-v3`, one 5-sec window per question (Q1 language, Q2 mode). Closed-set matching only; never auto-select on low confidence. After expiry: buttons only.
- Mic open only inside windows; closed during playback (no barge-in v1). Confirm Tamil STT language code with Gnani (open item).

### 4.2 Capture + frame scoring (on-device)
- Upload: one or more photos; if `continuation_flag`, prompt (voice + text) for another photo with guidance: one direction, ~1/3 overlap, hold steady.
- Live: per-frame scoring (sharpness via Laplacian variance, motion via inter-frame diff/flow, glare via highlight mask). Keep best frames with ≥30% overlap target; lock indicator on good hold; user can retake. Upload stills, not video (A1).

### 4.3 Preprocessing + stitching (server-side, A4)
- Preprocess: perspective/deskew, illumination normalization, denoise.
- Stitch: feature match + outlier rejection (RANSAC), perspective correction, planar-wall mosaic. Photo and video paths share alignment code.
- Seam rules (mandatory): per-seam quality score; glyphs near seams read from source frames, accepted only on agreement; poor seam → ask for recapture of that area, never silently stitch. Refuse to stitch below quality threshold (curved walls, parallax, glare). Review screen shows seams visibly — never a fake clean photo.

### 4.4 Recognition + calibration
- Baseline: fine-tuned Tesseract with custom Chola model (matches prior Brihadeeswarar work). Target: line-level CRNN + CTC on synthetic + real data. Lexicon-driven word segmentation (no word gaps on stone).
- Scope classifier with explicit out-of-scope class gates everything.
- Calibration: held-out real photos, conformal-style (validate); line spoken only if calibrated score ≥ threshold. Unspoken lines counted and announced ("I could read 4 of 7 lines confidently").
- Every report stored with model versions for the final evaluation.

### 4.5 Retrieval + explanation + rendering
- Order: (1) retrieval from published corpus (Hultzsch+) → explanation from published translation, labeled `published`; (2) else LLM draft strictly from confirmed lines, labeled `interpretation`; (3) else reading-only + statement of what failed.
- LLM: benchmark candidates on Tamil before choosing; structured claims output with tags; hard no-gap-filling rule. Provider open.
- Rendering: each language generated from structured claims (never free-translate an earlier explanation); automated check that all names/numbers in claims survive unchanged. 12 Vachana languages selectable (A2: language + voice selectable), each with verified/unverified flag; unverified shows a visible notice until native-speaker review passes.

### 4.6 Speech output (Gnani Vachana)
- Verified: model `vachana-voice-v3`, presets Karan/Simran/Nara/Riya/Viraj/Raju, 8k/16k/22.05k/44.1k, PCM + Ogg Opus, hosted API `https://api.vachana.ai`, batch + streaming, key via speechstack@gnani.ai, docs docs.inya.ai/vachana.
- Design: sentence-by-sentence synthesis, play on first ready; mic closed during playback; text always shown with audio. Audition every preset per language before exposing. Controlled lexicon for proper nouns (Rajaraja, Rajendra, Thanjavur) + Tamil numerals; pronunciation-hint support unverified — confirm with Gnani. LiveKit Agents plugin exists as optional session layer; fit is a judgement call, not required for v1.

## 5. Data plan (design implications)

- Re-OCR Hultzsch Tamil with a Tamil model → hand-correct → ground truth per inscription; English translations usable as-is.
- Collect hundreds–low-thousands of labeled real lines at Thanjavur with epigraphist verification; lock held-out real-photo test set in Phase 1, never train on it.
- Synthetic generator from expert-approved glyph samples on degraded stone textures (no known medieval font; expect to build glyph set from labeled data). TBSI useful only for degradation/preprocessing experiments, not text. Vatteluttu repo (28-char, no license) and Kaggle 59-class set: quarantined until expert + license cleared. TVA corpus: literature Tamil, license unconfirmed — lexicon aid at most, not inscription ground truth.
- Hard gates: named epigraphist, ASI/TNDA photo permission, license clearance per dataset, Gnani API key.

## 6. NFR implementation

- Latency budgets (validate): frame lock <3s after steady framing; report <10s/capture; first spoken sentence <3s after report. Sentence streaming + early TTS start is the main lever.
- Privacy: mic/camera open only on their screens; retention policy stated + user delete; log reports, not raw audio, by default.
- Accessibility: audio + text always together; large labeled buttons; adjustable text size.
- Reliability: timeouts + text-only fallback + visible error on every Gnani/LLM call.
- Logging: every report + model versions persisted for Phase 6.

## 7. Build order (maps to spec §14, with dev exit criteria)

1. **P0 foundations:** epigraphist, permissions, licenses, Gnani key, voice auditions (Tamil first), LLM Tamil benchmark. Exit: written confirmations.
2. **P1 data:** Hultzsch re-OCR + correction, lexicon + retrieval index, real-photo collection, locked test set + calibration harness. Exit: corpus + locked test exist; harness runs.
3. **P2 recognition:** Tesseract baseline → CRNN; scope classifier; calibration; report builder. Exit: report for every test image with calibrated scores.
4. **P3 explanation:** retrieval, claim tagging, drafter, rendering + name/number checks. Exit: automated consistency checks pass.
5. **P4 voice + photo app:** onboarding (voice windows + buttons), TTS pipeline, photo path + multi-photo guidance. Exit: end-to-end photo flow works.
6. **P5 video path:** frame scoring, keyframe upload, stitching + seam rules. Exit: live flow works, seam flags verified.
7. **P6 evaluation gate:** owner-defined measurement + epigraphist + per-language native review. Exit: pass or blocked.
8. **P7 hardening:** errors, privacy, accessibility, load.

## 8. Risks → design answers

| Risk | Answer in this plan |
|---|---|
| Synthetic→real gap | Real-photo test locked early; calibration on real photos only; Tesseract baseline before CRNN |
| Seam hallucinations | Seam scores, source-frame agreement rule, visible seams, refuse-and-recapture threshold |
| 12-language quality spread | Per-language verified flags + notice; claims-based rendering; name/number checks |
| Gnani unknowns | Sentence streaming, auditions, open-items list to speechstack@gnani.ai (Tamil quality, pronunciation hints, streaming details, limits, pricing, terms) |
| Deferred release gate | Test set + harness + stored reports exist from P1 regardless (§15) |

## 9. Open items needing answers before/during build

1. Gnani: Tamil voice quality, pronunciation control, streaming TTS details, rate limits, pricing/terms, STT Tamil code.
2. LLM provider after Tamil benchmark.
3. Hosting/GPU/cost; search-index product; PWA framework.
4. Licenses (Hultzsch reuse, TVA, GitHub, Kaggle) + ASI/TNDA photo permission in writing.
5. Release-gate definition deferred — but thresholds need first calibration run.
6. Assumptions A1–A4 taken as accepted unless the owner objects.
7. "Muse code": this is Muse Code (the tool producing this plan) — build tasks will be structured as small coded increments with tests.

## 10. Suggested immediate next actions

1. Confirm assumptions A1–A4 and the PWA framework + hosting answers.
2. Fire off access requests: Gnani key, epigraphist, ASI/TNDA permission.
3. Stand up repo skeleton: `client/` (PWA), `server/` (FastAPI + service modules), `data/` (corpus, lexicon), `eval/` (calibration harness + locked test manifest).
4. Implement session state machine + report schema + stubbed pipeline first (photo path, canned report → explanation → TTS stub), then fill in recognition and stitching behind the same contracts.

## 11. Decision interview log (in progress)

Settled: the single deliverable is this design plan; no implementation until the owner explicitly says so.
- Q1 (settled): A1–A4 all accepted for v1. Clarified: each onboarding question opens a 5-second voice window first, then switches to buttons-only; voice does not return until the next question. No voice retries.
- Q2 (settled): data-first for v1. Prepare a working data slice for an MVP that showcases the idea.
- Q3 (settled): narrow MVP — photo upload only, small curated Thanjavur corpus, Tamil + English output.
- Q4 (settled): responsive web app (PWA) compatible with mobile, tablet, and desktop screen sizes; owner verifies with Chrome DevTools resolution switching.
- Q5 (settled, conditional): try LLM via Meta model API if viable; if not viable, MVP goes with retrieval + reading-only and no LLM.
- Q6 (settled): 8 curated inscriptions in the MVP corpus.
- Q7 (settled, conditional): prefer Meta API vision model fine-tuned on our data if viable — must read text from images and reply in the user's intended language; fallback is the Tesseract custom baseline. Viability check is a build-time research task.
- Q8 (settled): threshold-gated explanation — above threshold tells the whole story; below threshold states only the understood context and asks the user for what's needed (e.g., recapture, better photo) when that can plausibly improve the output. Numeric threshold value deferred to the first calibration run.
- Q9 (settled): cloud-hosted MVP backend on Render.
- Q10 (settled): scope contract accepted; plan marked Final.

## 12. Settled contract (Final)

- Goals: responsive web app (mobile/tablet/desktop) demoing photo → Chola-era reading → spoken explanation; data-first MVP on 8 curated Thanjavur inscriptions showcasing the idea; truthfulness over fluency throughout.
- Non-goals for MVP: live video/stitching, all 12 TTS languages (Tamil + English only), LLM drafting unless Meta API proves viable, offline use, wake word, voice cloning.
- Decisions: A1–A4 accepted (stills, language+voice selection, voice-only-onboarding with 5-sec-window-then-buttons per question, server-side stitching); threshold-gated explanation (full story above, honest partial + ask-user-for-help below); Meta API vision model preferred for recognition if fine-tunable on our data, else Tesseract baseline; backend hosted on Render.
- Constraints: Reading Report stays the single source of truth; names/numbers only when confirmed; text always shown with audio; mic open only in onboarding windows.
- Risks: Meta API viability (fine-tuning + Tamil vision quality) unproven; real-stone transfer; Render cost/latency unmeasured.
- Validation: majority-of-8 end-to-end + visible honest-failure behavior; numeric threshold set after first calibration run; owner checks responsive layouts via Chrome DevTools.
- Unresolved: Meta API viability check; numeric threshold value; PWA framework pick; Gnani key + voice auditions; epigraphist, permissions, licenses.
- Scope: this document is the sole deliverable. Code, tests, data, and hosting setup are follow-ons needing their own go-ahead; accepting this plan never approves implementation.
