"""Live Gnani smoke test: TTS one word, STT it back, closed-set check.

Key comes ONLY from the GNANI_API_KEY environment variable (local .env or
Render dashboard). This script never prints the key, only lengths/statuses.

Run from the repo root:  env\\Scripts\\python.exe server/smoke_voice.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from speech import Speech, SpeechError  # noqa: E402


def load_dotenv() -> None:
    path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


async def main() -> int:
    load_dotenv()
    s = Speech()
    print("configured:", s.configured, flush=True)
    if not s.configured:
        print("set GNANI_API_KEY first (see .env.example)", flush=True)
        return 2
    print("key_len:", len(os.environ["GNANI_API_KEY"]), flush=True)
    try:
        wav = await s.synthesize("Tamil", "en-IN")
    except SpeechError as e:
        print("tts_fail:", str(e)[:200], flush=True)
        return 1
    print("tts_ok bytes:", len(wav), flush=True)
    try:
        tr = await s.transcribe(wav)
    except SpeechError as e:
        print("stt_fail:", str(e)[:200], flush=True)
        return 1
    print("stt_ok transcript:", tr, flush=True)
    print("closed_set_hit:", "tamil" in tr.lower(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
