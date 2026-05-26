"""FastAPI entry point for the modern web version.

Run from the project root with:
    uvicorn backend.main:app --reload --port 8504
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from disaster_risk_v4 import app  # noqa: E402

