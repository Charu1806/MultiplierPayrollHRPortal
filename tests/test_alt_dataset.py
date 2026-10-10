"""Alt dataset loads different company/cycle without code changes."""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def alt_env(monkeypatch):
    monkeypatch.setenv("DATASET", "alt")
    from domain import config as cfg

    cfg.reload()
    yield
    monkeypatch.delenv("DATASET", raising=False)
    cfg.reload()


def test_alt_company_and_cutoff(alt_env):
    from domain.config import company_config, cycle_config, rules_config

    co = company_config()
    assert co["name"] == "Northwind Labs"
    assert co["admin"]["name"] == "Sam Lee"
    cy = cycle_config()
    assert cy["cycles"]["october"]["inputFinalisation"] == "2026-10-10"
    assert cy["cycles"]["october"]["payDate"] == "2026-10-25"
    rules = rules_config()
    assert float(rules["aiCheck"]["upThreshold"]) == pytest.approx(0.4)
