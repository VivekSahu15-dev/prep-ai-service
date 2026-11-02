"""Question generation with the Gemini API. The model's answer is checked before anything is returned."""
import json
import os
import re

import httpx

CATEGORIES = ("technical", "aptitude", "coding")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GenerationError(Exception):
    """A problem with generating questions. The message is safe to show to the recruiter."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


def build_prompt(topic: str, skills: list[str], difficulty: str, counts: dict[str, int]) -> str:
    wanted = ", ".join(f"{n} {name}" for name, n in counts.items() if n > 0)
    skill_line = f"Skills the candidate should have: {', '.join(skills)}." if skills else ""
    return f"""You write multiple-choice questions for a campus recruitment test.

Role / topic: {topic}
{skill_line}
Difficulty: {difficulty}
Write exactly: {wanted}.

Question types:
- "technical": a conceptual or practical question about the role's skills.
- "aptitude": quantitative, logical reasoning or verbal ability, suitable for engineering graduates.
- "coding": a code-reading question. Put a short code snippet (at most 12 lines) in "code_snippet" and ask what it prints, what the bug is, or what its complexity is. The question must be answerable by reading the code.

Rules:
- Every question has exactly 4 options and exactly one correct option.
- Distractors must be plausible. Never use "all of the above" or "none of the above".
- Vary which option is correct.
- Only include "code_snippet" for coding questions. Use null for the others.
- Do not number the questions.

Reply with JSON only, in this shape:
{{"questions": [{{"category": "technical", "question": "...", "code_snippet": null, "options": ["...", "...", "...", "..."], "correct_index": 0}}]}}"""


def parse_questions_json(raw: str) -> tuple[list[dict], int]:
    """Turn the model's reply into clean questions. Returns (questions, number_dropped)."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GenerationError("The AI reply could not be read. Please try again.") from exc

    items = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise GenerationError("The AI reply was not in the expected format. Please try again.")

    questions, dropped, seen = [], 0, set()
    for item in items:
        if not isinstance(item, dict):
            dropped += 1
            continue
        question = str(item.get("question", "")).strip()
        options = item.get("options")
        index = item.get("correct_index")
        category = str(item.get("category", "technical")).strip().lower()
        snippet = item.get("code_snippet")

        valid = (
            len(question) >= 5
            and isinstance(options, list)
            and 2 <= len(options) <= 6
            and all(isinstance(o, str) and o.strip() for o in options)
            and isinstance(index, int)
            and not isinstance(index, bool)
            and 0 <= index < len(options)
        )
        key = question.lower()
        if not valid or key in seen:
            dropped += 1
            continue
        seen.add(key)
        questions.append(
            {
                "category": category if category in CATEGORIES else "technical",
                "question": question,
                "code_snippet": snippet.strip()[:2000] if isinstance(snippet, str) and snippet.strip() else None,
                "options": [o.strip() for o in options],
                "correct_index": index,
            }
        )
    if not questions:
        raise GenerationError("The AI did not return any usable questions. Please try again.")
    return questions, dropped


def generate_questions(topic: str, skills: list[str], difficulty: str, counts: dict[str, int]) -> tuple[list[dict], int]:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise GenerationError("AI question generation is not set up. Add GEMINI_API_KEY to ai-service/.env", 503)
    model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

    body = {
        "contents": [{"role": "user", "parts": [{"text": build_prompt(topic, skills, difficulty, counts)}]}],
        "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
    }
    try:
        res = httpx.post(GEMINI_URL.format(model=model), headers={"x-goog-api-key": key}, json=body, timeout=60)
    except httpx.HTTPError as exc:
        raise GenerationError("Could not reach the AI provider. Check the internet connection and try again.", 503) from exc

    if res.status_code == 429:
        raise GenerationError("The free AI quota is used up for the moment. Wait a minute and try again.", 429)
    if res.status_code == 404:
        raise GenerationError("The AI model name was not found. Set GEMINI_MODEL in ai-service/.env to a model listed in Google AI Studio.", 503)
    if res.status_code in (400, 401, 403):
        raise GenerationError("The AI provider rejected the request. Check that GEMINI_API_KEY is correct.", 503)
    if res.status_code >= 400:
        raise GenerationError(f"The AI provider returned an error ({res.status_code}). Please try again.", 502)

    try:
        parts = res.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise GenerationError("The AI reply was empty. Please try again.") from exc
    return parse_questions_json(text)