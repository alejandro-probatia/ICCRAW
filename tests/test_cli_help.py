from iccraw.cli import build_parser
from iccraw.version import __version__


def test_parser_has_expected_commands():
    parser = build_parser()
    text = parser.format_help()
    assert "raw-info" in text
    assert "build-profile" in text
    assert "export-cgats" in text
    assert "batch-develop" in text
    assert "auto-profile-batch" in text
    assert "compare-qa-reports" in text
    assert "check-tools" in text
    assert "check-amaze" in text


def test_parser_has_version_option(capsys):
    parser = build_parser()
    try:
        parser.parse_args(["--version"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert __version__ in captured.out
