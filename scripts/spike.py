"""T0.3 feasibility spike: arXiv search -> PDF download -> text extraction -> one Gemini call.

Throwaway script that checks assumptions A1-A5 in docs/PLAN.md before building on them.
Run: .venv/bin/python scripts/spike.py "retrieval augmented generation"
"""
import os
import sys
import xml.etree.ElementTree as ET

import httpx
import pymupdf
from dotenv import load_dotenv
from google import genai

load_dotenv()

ATOM = {"a": "http://www.w3.org/2005/Atom"}
query = sys.argv[1] if len(sys.argv) > 1 else "retrieval augmented generation"

# A1: arXiv search
resp = httpx.get(
    "https://export.arxiv.org/api/query",
    params={"search_query": f"all:{query}", "max_results": 3},
    timeout=30,
)
resp.raise_for_status()
entries = ET.fromstring(resp.text).findall("a:entry", ATOM)
print(f"[A1] arXiv returned {len(entries)} entries")
entry = entries[0]
title = " ".join(entry.find("a:title", ATOM).text.split())
authors = [a.find("a:name", ATOM).text for a in entry.findall("a:author", ATOM)]
year = entry.find("a:published", ATOM).text[:4]
pdf_url = next(l.get("href") for l in entry.findall("a:link", ATOM) if l.get("title") == "pdf")
print(f"     {title} ({year}) — {', '.join(authors[:3])}")
print(f"     pdf: {pdf_url}")

# A2: PDF download
pdf = httpx.get(pdf_url, follow_redirects=True, timeout=60)
pdf.raise_for_status()
print(f"[A2] downloaded {len(pdf.content) / 1024:.0f} KB ({pdf.headers.get('content-type')})")

# A5: text extraction
with pymupdf.open(stream=pdf.content, filetype="pdf") as doc:
    text = "\n".join(page.get_text() for page in doc)
    pages = doc.page_count
print(f"[A5] extracted {len(text):,} chars from {pages} pages")

# A3/A4: one Gemini call over the full text
model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
    sys.exit("[A3] FAILED: set GEMINI_API_KEY in .env")
client = genai.Client()
resp = client.models.generate_content(
    model=model,
    contents=f"<paper>\n{text}\n</paper>\n\nIn 3 sentences: what problem does this paper address and which datasets does it use?",
)
usage = resp.usage_metadata
print(f"[A3/A4] model={model}, prompt_tokens={usage.prompt_token_count:,}")
print(resp.text)
