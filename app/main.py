import os
import secrets
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

load_dotenv()

SERVICE_KEY = os.environ.get("AI_SERVICE_KEY", "")
if not SERVICE_KEY:
    raise RuntimeError("AI_SERVICE_KEY is not set. Add it to ai-service/.env")

from .generate import GenerationError, generate_questions  # noqa: E402
from .pdf_text import PdfError, extract_links, extract_text  # noqa: E402
from .questions import parse_questions  # noqa: E402
from .skills import extract_skills  # noqa: E402

MAX_BYTES = 5 * 1024 * 1024
MIN_TEXT_CHARS = 150

app = FastAPI(title="PREP AI service")


def require_key(x_service_key: str = Header(default="")) -> None:
    if not secrets.compare_digest(x_service_key.encode(), SERVICE_KEY.encode()):
        raise HTTPException(status_code=401, detail="Invalid service key")


class ParsedSkill(BaseModel):
    name: str
    category: str
    source: str


class ParseResponse(BaseModel):
    skills: list[ParsedSkill]
    sections_found: list[str]
    page_count: int
    char_count: int
    github_url: str | None = None
    linkedin_url: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


# A plain `def` (not async) so FastAPI runs the CPU-bound PDF work in a worker thread.
@app.post("/parse-resume", response_model=ParseResponse, dependencies=[Depends(require_key)])
def parse_resume(file: UploadFile = File(...)):
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Resume must be 5 MB or smaller")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    try:
        text, page_count = extract_text(data)
    except PdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if len(text.strip()) < MIN_TEXT_CHARS:
        raise HTTPException(
            status_code=422,
            detail="No readable text found. This looks like a scanned or image-only PDF. "
            "Export a text-based PDF from Word or Google Docs and upload that instead",
        )

    result = extract_skills(text)
    return {**result, **extract_links(data, text), "page_count": page_count, "char_count": len(text)}


class ExtractRequest(BaseModel):
    text: str = Field(min_length=20, max_length=20000)


class ExtractResponse(BaseModel):
    skills: list[str]


# Used for job descriptions: the recruiter pastes the text and gets suggested required skills.
@app.post("/extract-skills", response_model=ExtractResponse, dependencies=[Depends(require_key)])
def extract_skills_from_text(body: ExtractRequest):
    return {"skills": [s["name"] for s in extract_skills(body.text)["skills"]]}


class ParsedQuestion(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    category: str = "technical"


class QuestionsResponse(BaseModel):
    questions: list[ParsedQuestion]
    skipped: list[str]


# Reads MCQs from a PDF that follows the template (Q1. text / A) B) C) D) / Answer: B).
@app.post("/parse-questions", response_model=QuestionsResponse, dependencies=[Depends(require_key)])
def parse_questions_pdf(file: UploadFile = File(...)):
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="The PDF must be 5 MB or smaller")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    try:
        text, _ = extract_text(data)
    except PdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if len(text.strip()) < 30:
        raise HTTPException(
            status_code=422,
            detail="No readable text found. This looks like a scanned or image-only PDF",
        )

    questions, skipped = parse_questions(text)
    if not questions:
        detail = "No questions found. Check that the PDF follows the template shown on the page"
        if skipped:
            detail += f". First problem: {skipped[0]}"
        raise HTTPException(status_code=422, detail=detail)
    return {"questions": questions, "skipped": skipped}


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    skills: list[str] = Field(default_factory=list, max_length=30)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    technical: int = Field(default=0, ge=0, le=15)
    aptitude: int = Field(default=0, ge=0, le=15)
    coding: int = Field(default=0, ge=0, le=15)


class GeneratedQuestion(BaseModel):
    category: str
    question: str
    code_snippet: str | None = None
    options: list[str]
    correct_index: int


class GenerateResponse(BaseModel):
    questions: list[GeneratedQuestion]
    dropped: int


@app.post("/generate-questions", response_model=GenerateResponse, dependencies=[Depends(require_key)])
def generate(body: GenerateRequest):
    counts = {"technical": body.technical, "aptitude": body.aptitude, "coding": body.coding}
    if not 1 <= sum(counts.values()) <= 20:
        raise HTTPException(status_code=422, detail="Ask for between 1 and 20 questions in total")
    try:
        questions, dropped = generate_questions(
            body.topic, [s.strip() for s in body.skills if s.strip()], body.difficulty, counts
        )
    except GenerationError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
    return {"questions": questions, "dropped": dropped}