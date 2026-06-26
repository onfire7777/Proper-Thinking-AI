import os
import re
from pypdf import PdfReader
from typing import List, Dict, Optional

# Extract text from PDF with page number tracking
def extract_text_from_pdf(file_path: str) -> List[Dict[str, any]]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file not found: {file_path}")
    
    reader = PdfReader(file_path)
    pages_data = []
    
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if text.strip():
            pages_data.append({
                'page_number': page_num,
                'text': text.strip()
            })
    
    return pages_data

# Extract metadata from PDF file
def get_book_metadata(file_path: str) -> Dict[str, str]:
    
    reader = PdfReader(file_path)
    metadata = reader.metadata
    
    title = metadata.get('/Title', '') if metadata else ''
    if not title:
        title = os.path.splitext(os.path.basename(file_path))[0]

    author = ""
    if metadata:
        author = (metadata.get("/Author") or "").strip()

    # Extract front-matter text for best-effort field extraction.
    # Keep it bounded so ingestion stays fast/reliable.
    front_text_parts: List[str] = []
    max_pages_to_scan = min(6, len(reader.pages))
    for i in range(max_pages_to_scan):
        try:
            t = reader.pages[i].extract_text() or ""
        except Exception:
            t = ""
        t = t.strip()
        if t:
            front_text_parts.append(t)
    front_text = "\n".join(front_text_parts)

    # ISBN extraction (10 or 13 digits; may include hyphens).
    isbn = ""
    isbn_match = re.search(
        r"\bISBN(?:-1[03])?\s*[:\-]?\s*([0-9Xx][0-9\-]{8,16}[0-9Xx])\b",
        front_text,
        flags=re.IGNORECASE,
    )
    if isbn_match:
        candidate = isbn_match.group(1)
        candidate = candidate.replace("-", "").replace(" ", "").strip()
        # Normalize X upper-case and keep 10/13 length.
        candidate = candidate[:-1] + candidate[-1].upper() if candidate and candidate[-1].lower() == "x" else candidate
        if len(candidate) in (10, 13):
            isbn = candidate.upper()

    # Edition extraction (best-effort).
    # Examples: "Second edition", "Revised Edition", "1st edition".
    edition = ""
    edition_match = re.search(
        r"\b((?:1st|first|2nd|second|3rd|third|4th|fourth|revised|updated|new)\s+(?:edition|ed\.?|printing)|(?:edition|ed\.?|printing)\s+(?:of\s+)?\d{4}.*?)\b",
        front_text,
        flags=re.IGNORECASE,
    )
    if edition_match:
        edition = edition_match.group(1).strip()

    # Target audience extraction (best-effort; only from explicit "for"/"intended" phrases).
    target_audience = ""
    audience_match = re.search(
        r"\b(?:intended for|audience|who should|who is this book for|this book is for)\b\s*[:\-]?\s*(.{0,140})",
        front_text,
        flags=re.IGNORECASE,
    )
    if audience_match:
        target_audience = audience_match.group(1).strip()
        # Clean trailing sentence fragments.
        target_audience = re.sub(r"\s+", " ", target_audience)[:140].strip()

    edition_isbn = ""
    if edition and isbn:
        edition_isbn = f"{edition} (ISBN {isbn})"
    elif edition:
        edition_isbn = edition
    elif isbn:
        edition_isbn = f"ISBN {isbn}"

    # Author extraction (fallback from visible front-matter text).
    # Prefer copyright/byline-style lines when PdfReader metadata is missing.
    if not author:
        # e.g. "Copyright © 2011 Eric Ries" or "Copyright 2011 Eric Ries"
        copyright_match = re.search(
            r"Copyright\s*(?:©|\(c\)|\(C\))?\s*\d{4}\s*([A-Z][A-Za-z\-.' ]{2,60})",
            front_text,
            flags=re.IGNORECASE,
        )
        if copyright_match:
            author = copyright_match.group(1).strip()
            author = re.sub(r"\s+", " ", author)

    if not author:
        # e.g. "By Eric Ries"
        byline_match = re.search(
            r"\bBy\s+([A-Z][A-Za-z\-.' ]{2,60})",
            front_text,
            flags=re.IGNORECASE,
        )
        if byline_match:
            author = byline_match.group(1).strip()
            author = re.sub(r"\s+", " ", author)
    
    return {
        'title': title,
        'author': author,
        'edition_isbn': edition_isbn,
        'page_numbering_basis': 'Digital',  # Our chunker/citations use PDF page index (Digital) today.
        'target_audience': target_audience,
        'filename': os.path.basename(file_path),
        'total_pages': len(reader.pages)
    }
