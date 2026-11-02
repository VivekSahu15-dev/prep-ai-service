"""PDF to plain text, and the profile links inside it, using PyMuPDF."""
import re
from collections import Counter

import pymupdf

MAX_PAGES = 10


class PdfError(Exception):
    """Raised when a file cannot be turned into text. The message is safe to show to the student."""


def extract_text(data: bytes) -> tuple[str, int]:
    """Return (text, page_count). Only the first MAX_PAGES pages are read."""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfError("This file could not be read as a PDF") from exc

    with doc:
        if doc.needs_pass:
            raise PdfError("This PDF is password protected. Remove the password and upload it again")
        pages = min(doc.page_count, MAX_PAGES)
        text = "\n".join(doc[i].get_text("text", sort=True) for i in range(pages))
        return text, doc.page_count


_GITHUB = re.compile(r"github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?![A-Za-z0-9-])", re.IGNORECASE)
_LINKEDIN = re.compile(r"linkedin\.com/in/([A-Za-z0-9_%\-]{3,100})", re.IGNORECASE)
_GITHUB_NOT_A_USER = {
    "features", "topics", "about", "pricing", "enterprise", "sponsors", "marketplace",
    "orgs", "settings", "login", "join", "explore", "collections", "apps",
}


def extract_links(data: bytes, text: str) -> dict:
    """Find the student's GitHub and LinkedIn profile links.

    Looks at the visible text and at hyperlinks behind words like "GitHub", which text extraction alone misses.
    """
    parts = [text]
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            for i in range(min(doc.page_count, MAX_PAGES)):
                for link in doc[i].get_links():
                    if link.get("uri"):
                        parts.append(link["uri"])
    except Exception:
        pass  # unreadable links are not an error, the text may still hold them
    blob = "\n".join(parts)

    # Resumes often link several repositories, all under one username, so take the most common one.
    names = [m.group(1) for m in _GITHUB.finditer(blob) if m.group(1).lower() not in _GITHUB_NOT_A_USER]
    github_url = None
    if names:
        winner = Counter(n.lower() for n in names).most_common(1)[0][0]
        original = next(n for n in names if n.lower() == winner)
        github_url = f"https://github.com/{original}"

    linkedin = _LINKEDIN.search(blob)
    linkedin_url = f"https://www.linkedin.com/in/{linkedin.group(1).rstrip('-')}" if linkedin else None
    return {"github_url": github_url, "linkedin_url": linkedin_url}