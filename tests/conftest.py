"""Keep all automated checks away from the user's real data."""

import sys
import logging
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mr_roy import config, log, report, schedule, textboxes, typed, wispr


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    # Deliberately failing export tests must not look like production failures.
    monkeypatch.setattr(log, "get", lambda name="": logging.getLogger(f"roy-test.{name}"))
    for name, suffix in (("ROOT", ""), ("DATA_DIR", "data"), ("REPORTS_DIR", "reports")):
        path = tmp_path / suffix
        path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(config, name, path)
    monkeypatch.setattr(wispr, "DB_PATH", tmp_path / "absent.sqlite")
    # The typing source reads the real ~/.claude/projects, and the grammar
    # checker shells out to the real Claude CLI. A test does neither.
    monkeypatch.setattr(typed, "PROJECTS", tmp_path / "projects")
    monkeypatch.setattr(typed, "CODEX_HISTORY", tmp_path / "codex-history.jsonl")
    monkeypatch.setenv("MR_ROY_NO_LLM", "1")
    monkeypatch.setattr(schedule, "LOG_DIR", tmp_path / "logs")
    # Paths fixed at import, so redirected one by one: a test once deleted
    # the real .accessibility-granted (10 Oct).
    monkeypatch.setattr(textboxes, "GRANTED", tmp_path / "data" / ".accessibility-granted")
    monkeypatch.setattr(schedule, "APP", tmp_path / "Mr Roy.app")
    # The catch-up job hands off to the morning one, which opens the page:
    # a test run opened a pytest report in the user's Safari (11 Oct).
    monkeypatch.setattr(report, "open_report", lambda day=None: None)


REAL_OPEN_REPORT = report.open_report


@pytest.fixture
def real_open_report(monkeypatch):
    """For the one test of opening itself (it mocks the `open` command)."""
    monkeypatch.setattr(report, "open_report", REAL_OPEN_REPORT)


@pytest.fixture
def tmp(tmp_path):
    """Compatibility with the original script-style test functions."""
    return tmp_path
