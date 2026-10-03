import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "app.db"
PDF_DIR = DATA_DIR / "pdfs"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
# Tried in order when the primary model is rate-limited (429) or overloaded (503).
GEMINI_FALLBACK_MODELS = [
    m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-flash-latest,gemini-3.5-flash").split(",") if m.strip()
]

PDF_DIR.mkdir(parents=True, exist_ok=True)
