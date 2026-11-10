"""Gnani speech service: Timbre TTS + Prisma STT over raw HTTP.

Docs: https://docs.gnani.ai (TTS: timbre-v2.5, STT: prisma-v3.0).
The API key comes only from the GNANI_API_KEY environment variable and is
never logged, returned, or committed. Without it the service reports
unconfigured and callers fall back to text-only behavior.
"""
from __future__ import annotations

import os

import httpx

BASE = "https://api.vachana.ai"
TTS_MODEL = "timbre-v2.5"
# Provisional personas (consistent professional voice); swap via env after
# playground auditions. Voices are per-model: v2.5 names only.
VOICES = {"ta": os.environ.get("VOTS_VOICE_TA", "Asmita"),
          "en-IN": os.environ.get("VOTS_VOICE_EN", "Devika")}
LANG = {"ta": "ta-IN", "en-IN": "en-IN"}
TIMEOUT = 20.0


class SpeechError(Exception):
    pass


class Speech:
    def __init__(self, key: str | None = None):
        self.key = key if key is not None else os.environ.get("GNANI_API_KEY", "")
        self.configured = bool(self.key)

    async def synthesize(self, text: str, language: str) -> bytes:
        """One sentence (or short paragraph) -> WAV bytes. Raises SpeechError."""
        if not self.configured:
            raise SpeechError("TTS not configured (GNANI_API_KEY missing)")
        body = {"text": text, "voice": VOICES[language], "model": TTS_MODEL,
                "language": LANG[language], "speed": 1.0,
                "audio_config": {"sample_rate": 22050, "num_channels": 1,
                                 "sample_width": 2, "encoding": "linear_pcm",
                                 "container": "wav"}}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as c:
                r = await c.post(f"{BASE}/api/v1/tts/inference",
                                 headers={"X-API-Key-ID": self.key}, json=body)
        except httpx.HTTPError as e:
            raise SpeechError(f"TTS request failed: {e}") from e
        if r.status_code != 200:
            raise SpeechError(f"TTS {r.status_code}: {r.text[:200]}")
        return r.content

    async def transcribe(self, wav: bytes) -> str:
        """5s onboarding clip -> Latin-script transcript ('' if no speech)."""
        if not self.configured:
            raise SpeechError("STT not configured (GNANI_API_KEY missing)")
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as c:
                r = await c.post(
                    f"{BASE}/stt/v3", headers={"X-API-Key-ID": self.key},
                    files={"audio_file": ("clip.wav", wav, "audio/wav")},
                    data={"model": "prisma-v3.0", "format": "transliterate"})
        except httpx.HTTPError as e:
            raise SpeechError(f"STT request failed: {e}") from e
        if r.status_code != 200:
            raise SpeechError(f"STT {r.status_code}: {r.text[:200]}")
        return r.json().get("transcript", "") or ""
