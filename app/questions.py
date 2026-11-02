"""Reads multiple-choice questions out of text that follows a simple template."""
import re

MAX_QUESTIONS = 50

# "Q1." / "Question 2:" / "3." / "4)" at the start of a line begins a new question.
_QUESTION = re.compile(r"^\s*(?:(?:Q|Question)\s*(\d{1,3})\s*[.):\-]|(\d{1,3})\s*[.)])\s*(.*)$", re.IGNORECASE)
# "A)" / "A." / "(a)" begins an option.
_OPTION = re.compile(r"^\s*\(?([A-Fa-f])[.)]\s*(.*)$")
# Optional "Type: aptitude" / "Category: coding" line inside a question.
_CATEGORY = re.compile(r"^\s*(?:type|category)\s*[:\-]\s*(technical|aptitude|coding)\s*$", re.IGNORECASE)
# "Answer: B" / "Ans - c" / "Correct answer: (D)"
_ANSWER = re.compile(r"^\s*(?:correct\s+answer|correct\s+option|answer|ans)\s*[:\-]?\s*\(?([A-Fa-f])\)?\s*[.)]?\s*$", re.IGNORECASE)


def _finish(block: dict, skipped: list[str]) -> dict | None:
    number = block["number"]
    question = " ".join(block["question"]).strip()
    options = [(letter, " ".join(parts).strip()) for letter, parts in block["options"]]

    if len(question) < 5:
        skipped.append(f"Question {number}: the question text is missing or too short")
        return None
    if not 2 <= len(options) <= 6:
        skipped.append(f"Question {number}: found {len(options)} options, expected between 2 and 6")
        return None
    letters = [letter.upper() for letter, _ in options]
    if letters != [chr(65 + i) for i in range(len(letters))]:
        skipped.append(f"Question {number}: options must be lettered A, B, C... in order")
        return None
    if any(not text for _, text in options):
        skipped.append(f"Question {number}: an option is empty")
        return None
    if block["answer"] is None:
        skipped.append(f"Question {number}: no 'Answer: X' line found")
        return None
    answer = block["answer"].upper()
    if answer not in letters:
        skipped.append(f"Question {number}: the answer {answer} is not one of the options")
        return None

    return {
        "question": question,
        "options": [text for _, text in options],
        "correct_index": letters.index(answer),
        "category": block["category"],
    }


def parse_questions(text: str) -> tuple[list[dict], list[str]]:
    """Returns (questions, skipped). Anything that cannot be read is reported, never guessed."""
    questions: list[dict] = []
    skipped: list[str] = []
    block: dict | None = None
    mode = "question"

    def flush():
        nonlocal block
        if block is not None:
            done = _finish(block, skipped)
            if done:
                questions.append(done)
        block = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        category = _CATEGORY.match(line)
        if block is not None and category:
            block["category"] = category.group(1).lower()
            continue

        # Once a question has its answer, a lettered line cannot be an option of it.
        answer = _ANSWER.match(line)
        if block is not None and answer:
            block["answer"] = answer.group(1)
            mode = "done"
            continue

        start = _QUESTION.match(line)
        if start and (block is None or block["answer"] is not None or block["options"]):
            flush()
            number = start.group(1) or start.group(2)
            block = {"number": number, "question": [start.group(3)], "options": [], "answer": None, "category": "technical"}
            mode = "question"
            continue

        if block is None or mode == "done":
            continue

        option = _OPTION.match(line)
        if option:
            block["options"].append((option.group(1), [option.group(2)]))
            mode = "option"
        elif mode == "question":
            block["question"].append(line)
        elif mode == "option":
            block["options"][-1][1].append(line)

    flush()

    if len(questions) > MAX_QUESTIONS:
        skipped.append(f"Only the first {MAX_QUESTIONS} questions were imported")
        questions = questions[:MAX_QUESTIONS]
    return questions, skipped