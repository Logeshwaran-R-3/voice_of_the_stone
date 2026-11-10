# Eval (MVP)

## What exists
- `test_manifest.json`: the 8 demo entries with expected behavior (6 full-story,
  2 hard cases that must show partial flags, never filled gaps).
- `server/tests/test_api.py`: contract tests for the state machine, report
  schema, threshold gating, and claim tags. Run with `pytest server/tests`
  on any machine with Python (Render works; the dev sandbox has no runtime).

## What is provisional
- Threshold `0.6` (`VOTS_MVP_THRESHOLD` on Render) is a placeholder. The first
  calibration run on real photos sets the real value (design plan §12).
- The photo set is hotlinked to Wikimedia Commons. Before locking the test set,
  vendor the 8 binaries, record SHA-256 hashes here, and freeze expected
  reports per photo.

## Locking checklist (before any release claim)
1. Vendor photos; record hashes in the manifest; set `locked: true`.
2. Calibrate line scores on held-out real photos; set the threshold.
3. Freeze one expected Reading Report per test photo; diff on every run.
4. Native-speaker review for Tamil; flip the language flag only then.
