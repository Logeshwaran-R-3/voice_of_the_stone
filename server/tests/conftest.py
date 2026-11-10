"""Test path setup: make server/ importable so `app` and `speech` resolve
no matter which directory pytest is launched from."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
