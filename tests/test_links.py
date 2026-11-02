import pymupdf

from app.pdf_text import extract_links


def test_finds_links_in_plain_text():
    text = "Jane Doe\nlinkedin.com/in/jane-doe-1a2b3c  |  github.com/janedoe\nProjects: github.com/janedoe/portfolio and github.com/janedoe/api"
    links = extract_links(b"", text)
    assert links["github_url"] == "https://github.com/janedoe"
    assert links["linkedin_url"] == "https://www.linkedin.com/in/jane-doe-1a2b3c"


def test_finds_hyperlinks_hidden_behind_words():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "GitHub  LinkedIn", fontsize=12)
    page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(72, 60, 120, 76), "uri": "https://github.com/hiddenuser"})
    page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(130, 60, 190, 76), "uri": "https://www.linkedin.com/in/hidden-user/"})
    links = extract_links(doc.tobytes(), "GitHub LinkedIn")
    assert links["github_url"] == "https://github.com/hiddenuser"
    assert links["linkedin_url"] == "https://www.linkedin.com/in/hidden-user"


def test_ignores_non_profile_github_pages_and_missing_links():
    assert extract_links(b"", "see github.com/features and nothing else")["github_url"] is None
    assert extract_links(b"", "no links here") == {"github_url": None, "linkedin_url": None}


def test_most_common_username_wins():
    text = "github.com/real/one github.com/real/two github.com/other/x"
    assert extract_links(b"", text)["github_url"] == "https://github.com/real"