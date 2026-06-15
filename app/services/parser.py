import io
import re
import logging
from typing import Optional
from datetime import datetime, timezone

import pdfplumber
import spacy
from spacy.language import Language

from app.core.config import settings
from app.utils.file_handler import read_file

logger = logging.getLogger(__name__)

# PERF [CRITICAL]: spaCy model loaded ONCE at startup, not per request
_nlp: Optional[Language] = None


def load_spacy_model() -> Language:
    global _nlp
    if _nlp is None:
        _nlp = spacy.load(settings.SPACY_MODEL)
        logger.info({"event": "spacy_loaded", "model": settings.SPACY_MODEL})
    return _nlp


# ── Skill keywords ────────────────────────────────────────────────────────────
SKILL_KEYWORDS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
    "react", "reactjs", "react.js", "angular", "vue", "nextjs", "next.js",
    "node", "nodejs", "node.js", "express", "fastapi", "django", "flask",
    "spring", "springboot", "spring boot", "laravel",
    "sql", "postgresql", "mysql", "mongodb", "redis", "sqlite", "cassandra",
    "docker", "kubernetes", "k8s", "aws", "azure", "gcp", "terraform",
    "git", "github", "gitlab", "ci/cd", "jenkins", "github actions",
    "machine learning", "deep learning", "nlp", "computer vision",
    "pytorch", "tensorflow", "scikit-learn", "pandas", "numpy",
    "rest", "restful", "graphql", "grpc", "microservices",
    "linux", "bash", "shell scripting",
    "html", "css", "tailwind", "bootstrap", "sass",
}

EDUCATION_KEYWORDS = {
    "university", "college", "institute", "school", "bachelor", "master",
    "b.tech", "m.tech", "b.e", "m.e", "mba", "phd", "diploma", "degree",
}

CERT_KEYWORDS = {
    "certified", "certification", "certificate", "aws certified",
    "google certified", "microsoft certified", "pmp", "cpa", "cfa",
}


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_text_pdfplumber(content: bytes) -> str:
    """EDGE CASE: catches corrupt/truncated PDFs gracefully."""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            # EDGE CASE: PDF with zero pages
            if not pdf.pages:
                logger.warning({"event": "pdf_no_pages"})
                return ""
            pages = []
            for page in pdf.pages:
                try:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
                except Exception as page_err:
                    # EDGE CASE: single corrupt page — skip, continue with rest
                    logger.warning({"event": "pdf_page_extract_failed", "error": str(page_err)})
                    continue
            return "\n".join(pages).strip()
    except Exception as e:
        logger.warning({"event": "pdfplumber_failed", "error": str(e)})
        return ""


def _extract_text_ocr(content: bytes) -> str:
    """
    EDGE CASE: image-only (scanned) PDFs produce empty text from pdfplumber.
    Fallback: rasterize each page and run Tesseract OCR.
    """
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image

        doc = fitz.open(stream=content, filetype="pdf")
        # EDGE CASE: fitz opens file but has 0 pages
        if doc.page_count == 0:
            logger.warning({"event": "ocr_empty_pdf"})
            return ""

        texts = []
        for page_num in range(doc.page_count):
            try:
                page = doc[page_num]
                pix = page.get_pixmap(dpi=200)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_text = pytesseract.image_to_string(img)
                if ocr_text.strip():
                    texts.append(ocr_text)
            except Exception as page_err:
                logger.warning({"event": "ocr_page_failed", "page": page_num, "error": str(page_err)})
                continue

        return "\n".join(texts).strip()
    except Exception as e:
        logger.warning({"event": "ocr_failed", "error": str(e)})
        return ""


def extract_text(content: bytes) -> str:
    """Try pdfplumber first; fall back to OCR for image-only documents."""
    text = _extract_text_pdfplumber(content)
    if not text:
        logger.info({"event": "fallback_to_ocr"})
        text = _extract_text_ocr(content)
    return text


# ── Field extractors ──────────────────────────────────────────────────────────

def _extract_email(text: str) -> Optional[str]:
    match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    return match.group(0) if match else None


def _extract_phone(text: str) -> Optional[str]:
    match = re.search(r"(\+?\d[\d\s\-().]{8,15}\d)", text)
    return match.group(0).strip() if match else None


def _extract_name(doc) -> Optional[str]:
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            return ent.text.strip()
    return None


def _extract_skills(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for skill in SKILL_KEYWORDS:
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, lower):
            found.append(skill)
    return sorted(set(found))


def _extract_education(text: str) -> list[dict]:
    lines = text.split("\n")
    education = []
    for line in lines:
        if any(kw in line.lower() for kw in EDUCATION_KEYWORDS):
            entry = line.strip()
            if entry and len(entry) > 5:
                education.append({"raw": entry[:300]})
    return education[:5]


def _extract_experience(doc, text: str) -> list[dict]:
    lines = text.split("\n")
    date_pattern = re.compile(
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|"
        r"march|april|june|july|august|september|october|november|december)"
        r"[\s,]*\d{4}",
        re.IGNORECASE,
    )
    experience = []
    for i, line in enumerate(lines):
        if date_pattern.search(line) or any(
            kw in line.lower()
            for kw in ("engineer", "developer", "analyst", "manager", "intern",
                       "lead", "architect", "consultant", "specialist")
        ):
            entry = " ".join(lines[max(0, i - 1): i + 2]).strip()
            if entry:
                experience.append({"raw": entry[:300]})
    return experience[:10]


def _extract_certifications(text: str) -> list[str]:
    certs = []
    for line in text.split("\n"):
        if any(kw in line.lower() for kw in CERT_KEYWORDS):
            cert = line.strip()
            if cert and len(cert) > 3:
                certs.append(cert[:200])
    return certs[:10]


def _score_resume(parsed: dict) -> float:
    """Heuristic quality score based on profile completeness."""
    score = 0.0
    if parsed.get("name"):       score += 10
    if parsed.get("email"):      score += 10
    if parsed.get("phone"):      score += 5
    score += min(len(parsed.get("skills", [])) * 3, 30)
    score += min(len(parsed.get("education", [])) * 10, 20)
    score += min(len(parsed.get("experience", [])) * 5, 20)
    if parsed.get("certifications"): score += 5
    return min(round(score, 2), 100.0)


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_resume(file_path: str) -> dict:
    """
    Read file from storage, extract text, run NER pipeline,
    return structured profile dict including resume_score.
    """
    logger.info({"event": "parse_start", "file_path": file_path})

    # EDGE CASE: file missing from storage
    try:
        content = read_file(file_path)
    except (FileNotFoundError, Exception) as e:
        logger.error({"event": "parse_file_read_failed", "file_path": file_path, "error": str(e)})
        return _empty_profile(error=f"File read failed: {str(e)}")

    # EDGE CASE: empty file
    if not content:
        logger.warning({"event": "parse_empty_file", "file_path": file_path})
        return _empty_profile(error="File is empty")

    text = extract_text(content)

    # EDGE CASE: image-only PDF with no extractable or OCR-able text
    if not text or not text.strip():
        logger.warning({"event": "parse_no_text", "file_path": file_path})
        return _empty_profile(error="No extractable text found. Document may be image-only or corrupt.")

    nlp = load_spacy_model()
    # PERF: cap input length via config to prevent memory spikes on very large docs
    doc = nlp(text[:settings.SPACY_TEXT_CAP])

    parsed = {
        "name":             _extract_name(doc),
        "email":            _extract_email(text),
        "phone":            _extract_phone(text),
        "skills":           _extract_skills(text),
        "education":        _extract_education(text),
        "experience":       _extract_experience(doc, text),
        "certifications":   _extract_certifications(text),
    }

    parsed["resume_score"] = _score_resume(parsed)

    logger.info({
        "event": "parse_complete",
        "file_path": file_path,
        "skills_found": len(parsed["skills"]),
        "resume_score": parsed["resume_score"],
    })

    return parsed


def _empty_profile(error: str = "") -> dict:
    return {
        "name": None, "email": None, "phone": None,
        "skills": [], "education": [], "experience": [],
        "certifications": [], "resume_score": 0.0,
        "error": error,
    }
