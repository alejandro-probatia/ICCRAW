from nexoraw.cli import build_parser
from nexoraw.version import __version__


def test_parser_has_expected_commands():
    parser = build_parser()
    text = parser.format_help()
    assert parser.prog == "nexoraw"
    assert "raw-info" in text
    assert "metadata" in text
    assert "build-profile" in text
    assert "export-cgats" in text
    assert "batch-develop" in text
    assert "auto-profile-batch" in text
    assert "compare-qa-reports" in text
    assert "check-tools" in text
    assert "check-amaze" in text
    assert "check-c2pa" in text
    assert "check-display-profile" in text
    assert "verify-c2pa" in text


def test_parser_has_version_option(capsys):
    parser = build_parser()
    try:
        parser.parse_args(["--version"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_parser_accepts_batch_worker_controls():
    parser = build_parser()

    develop = parser.parse_args(
        [
            "develop",
            "capture.nef",
            "--recipe",
            "recipe.yml",
            "--out",
            "out.tiff",
            "--cache-dir",
            "cache",
        ]
    )
    batch = parser.parse_args(
        [
            "batch-develop",
            "raws",
            "--recipe",
            "recipe.yml",
            "--profile",
            "camera.icc",
            "--out",
            "out",
            "--workers",
            "2",
            "--cache-dir",
            "cache",
        ]
    )
    auto = parser.parse_args(
        [
            "auto-profile-batch",
            "--charts",
            "charts",
            "--targets",
            "targets",
            "--recipe",
            "recipe.yml",
            "--reference",
            "reference.json",
            "--profile-out",
            "camera.icc",
            "--profile-report",
            "report.json",
            "--out",
            "out",
            "--workdir",
            "work",
            "--workers",
            "3",
            "--cache-dir",
            "cache",
        ]
    )

    assert develop.cache_dir == "cache"
    assert batch.workers == 2
    assert batch.cache_dir == "cache"
    assert auto.workers == 3
    assert auto.cache_dir == "cache"
