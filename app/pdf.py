"""PDF download and text extraction shared by saved arXiv papers and uploads."""
import httpx
import pymupdf

# Below this many characters we assume the PDF has no usable text layer (e.g. a scan).
MIN_TEXT_CHARS = 500


class PdfError(Exception):
    pass


async def download(url: str) -> bytes:
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise PdfError(f"PDF download failed: {e.__class__.__name__}") from e
    if not resp.content.startswith(b"%PDF"):
        raise PdfError("Downloaded file is not a PDF")
    return resp.content


def extract_text(data: bytes) -> str:
    """Return the PDF's text, or raise PdfError if it has no usable text layer."""
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            text = "\n".join(page.get_text() for page in doc)
    except Exception as e:  # pymupdf raises several exception types for corrupt files
        raise PdfError("Could not read PDF") from e
    # Some PDFs yield NUL characters; SQLite's length() and text functions stop at the first one.
    text = text.replace("\x00", "")
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise PdfError("PDF has no extractable text (it may be a scanned image)")
    return text
