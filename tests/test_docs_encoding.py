from pathlib import Path


MOJIBAKE_MARKERS = ("Ã", "Â", "�", "â€™", "â€œ", "â€", "ðŸ")


def test_markdown_docs_are_utf8_without_mojibake():
    root = Path(__file__).resolve().parents[1]
    paths = [root / "README.md", root / "CHANGELOG.md", *sorted((root / "docs").glob("*.md"))]

    failures = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        markers = [marker for marker in MOJIBAKE_MARKERS if marker in text]
        if markers:
            failures.append(f"{path.relative_to(root)}: {', '.join(markers)}")

    assert not failures, "Mojibake markers found in Markdown docs:\n" + "\n".join(failures)
