import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "app.db"
PDF_DIR = DATA_DIR / "pdfs"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

PDF_DIR.mkdir(parents=True, exist_ok=True)
