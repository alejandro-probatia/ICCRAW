from iccraw.cli import build_parser


def test_parser_has_expected_commands():
    parser = build_parser()
    text = parser.format_help()
    assert "raw-info" in text
    assert "build-profile" in text
    assert "export-cgats" in text
    assert "batch-develop" in text
    assert "auto-profile-batch" in text
