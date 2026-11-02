"""Skill extraction: normalise resume text, split it into sections, match a skills taxonomy."""
import json
import re
from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "skills.json"

# ---------- section detection ----------

_SECTION_WORDS = {
    "skills": [
        "skills", "technical skills", "key skills", "core skills", "skill set", "core competencies",
        "technologies", "tech stack", "technical expertise", "technical proficiency",
        "tools and technologies", "skills and tools", "skills and technologies", "programming languages",
    ],
    "education": ["education", "academic background", "academics", "academic qualifications"],
    "projects": ["projects", "academic projects", "personal projects", "key projects", "technical projects"],
    "experience": [
        "experience", "work experience", "professional experience", "internships", "internship",
        "internship experience", "work history",
    ],
    "certifications": ["certifications", "certificates", "courses", "licenses and certifications"],
    "achievements": ["achievements", "awards", "accomplishments", "honors and awards"],
    "summary": ["summary", "objective", "career objective", "profile", "professional summary"],
}
_HEADER_TO_SECTION = {w: sec for sec, words in _SECTION_WORDS.items() for w in words}

_LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl"}
_BULLETS = re.compile("[\u2022\u25cf\u25aa\u25e6\u25a0\u25a1\u25b6\u25ba\u27a2\u2714\u2713]")


def normalize(text: str) -> str:
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)
    text = text.replace("\u00a0", " ")
    text = _BULLETS.sub("\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _header_key(line: str) -> str:
    key = line.strip().strip(":-\u2013\u2014|*#").strip().lower().replace("&", "and")
    key = re.sub(r"\s+", " ", key)
    return key if len(key) <= 45 else ""


def split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in text.split("\n"):
        section = _HEADER_TO_SECTION.get(_header_key(line))
        if section:
            current = section
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return {name: "\n".join(lines) for name, lines in sections.items()}


# ---------- taxonomy matching ----------

# A skill must not touch letters, digits, + or # on either side. That keeps "Java" out of "JavaScript",
# "SQL" out of "MySQL", "Git" out of "GitHub" and "C" out of "C++". A trailing ".js"-style suffix is
# also rejected so "node" does not match inside "node.js" (that has its own alias).
_LEFT = r"(?<![A-Za-z0-9_+#])"
_RIGHT = r"(?![A-Za-z0-9_+#])(?!\.[A-Za-z0-9])"


def _compile(words: list[str], flags: int) -> re.Pattern | None:
    if not words:
        return None
    ordered = sorted(set(words), key=len, reverse=True)
    body = "|".join(re.escape(w) for w in ordered)
    return re.compile(f"{_LEFT}(?:{body}){_RIGHT}", flags)


@dataclass(frozen=True)
class Skill:
    name: str
    category: str
    pattern: re.Pattern | None  # case-insensitive, counted anywhere in the resume
    exact: re.Pattern | None  # case-sensitive, counted only inside the Skills section ("C", "R", "Go")


def _load() -> list[Skill]:
    skills = []
    for entry in json.loads(DATA_FILE.read_text(encoding="utf-8")):
        exact_words = entry.get("exact_aliases", [])
        words = list(entry.get("aliases", []))
        if not exact_words:
            words.append(entry["name"])
        skills.append(
            Skill(
                name=entry["name"],
                category=entry["category"],
                pattern=_compile(words, re.IGNORECASE),
                exact=_compile(exact_words, 0),
            )
        )
    return skills


TAXONOMY = _load()


def extract_skills(text: str) -> dict:
    text = normalize(text)
    sections = split_sections(text)
    skills_text = sections.get("skills", "")

    found = []
    for s in TAXONOMY:
        in_skills_section = bool(
            (s.pattern and s.pattern.search(skills_text)) or (s.exact and s.exact.search(skills_text))
        )
        in_body = bool(s.pattern and s.pattern.search(text))
        if in_skills_section:
            source = "skills_section"
        elif in_body:
            source = "body"
        else:
            continue
        found.append({"name": s.name, "category": s.category, "source": source})

    found.sort(key=lambda x: (x["category"], x["name"].lower()))
    sections_found = sorted(k for k, v in sections.items() if k != "header" and v.strip())
    return {"skills": found, "sections_found": sections_found}