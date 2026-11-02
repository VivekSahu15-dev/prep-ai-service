from app.skills import extract_skills


def names(text):
    return {s["name"] for s in extract_skills(text)["skills"]}


SAMPLE = """Jane Doe
SKILLS
Languages: C, C++, Java, JavaScript, Python
Backend: Node.js, Express.js, MySQL, MongoDB
Tools: Git, GitHub, Docker
PROJECTS
Built a REST API with Node.js and React. Used Redux for state.
"""


def test_finds_expected_skills():
    expected = {"C", "C++", "Java", "JavaScript", "Python", "Node.js", "Express.js",
                "MySQL", "MongoDB", "Git", "GitHub", "Docker", "React", "Redux", "REST APIs"}
    assert expected <= names(SAMPLE)


def test_no_false_substring_matches():
    found = names("SKILLS\nJavaScript, MySQL, GitHub")
    assert "Java" not in found
    assert "SQL" not in found
    assert "Git" not in found


def test_c_does_not_match_c_plus_plus_or_csharp():
    found = names("SKILLS\nC++, C#")
    assert "C" not in found
    assert {"C++", "C#"} <= found


def test_ambiguous_single_letters_only_in_skills_section():
    assert "C" not in names("EXPERIENCE\nGot grade C in a course")
    assert "C" in names("SKILLS\nC, Python")
    assert "R" not in names("EXPERIENCE\nPlan R was used")


def test_source_marks_skills_section_vs_body():
    result = {s["name"]: s["source"] for s in extract_skills(SAMPLE)["skills"]}
    assert result["Python"] == "skills_section"
    assert result["React"] == "body"


def test_dotnet_and_trailing_punctuation():
    found = names("PROJECTS\nWorked on ASP.NET and used Docker. Also Python.")
    assert {".NET", "Docker", "Python"} <= found


def test_ligature_cleanup():
    assert "Docker" in names("SKILLS\nDocker, Con\ufb01guration")