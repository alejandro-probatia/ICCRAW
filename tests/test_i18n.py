"""Tests para el sistema de i18n: resolución de idioma y carga de traductor."""
from __future__ import annotations

from unittest import mock

from probraw import i18n


def test_resolve_language_explicit_overrides_system():
    assert i18n.resolve_language("es") == "es"
    assert i18n.resolve_language("en") == "en"


def test_resolve_language_auto_falls_back_to_system_detection():
    with mock.patch.object(i18n, "detect_system_language", return_value="en"):
        assert i18n.resolve_language("auto") == "en"
        assert i18n.resolve_language("") == "en"
        assert i18n.resolve_language(None) == "en"

    with mock.patch.object(i18n, "detect_system_language", return_value="es"):
        assert i18n.resolve_language("auto") == "es"


def test_resolve_language_unknown_value_falls_back_to_system():
    with mock.patch.object(i18n, "detect_system_language", return_value="en"):
        assert i18n.resolve_language("fr") == "en"
        assert i18n.resolve_language("xx") == "en"


def test_detect_system_language_returns_supported_code():
    detected = i18n.detect_system_language()
    assert detected in {"es", "en"}
