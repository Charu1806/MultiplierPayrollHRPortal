"""Field normalisation (formatted CPF → digits)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services import rules as rules_svc  # noqa: E402


def test_cpf_formatted_input_strips_and_validates():
    result = rules_svc.normalize_field_value("CPF", "123.456.789-09")
    assert result["ok"] is True
    assert result["normalised"] == "12345678909"
    assert result["error"] is None


def test_cpf_invalid_after_strip():
    result = rules_svc.normalize_field_value("CPF", "123.456.789")
    assert result["ok"] is False
    assert result["error"]
