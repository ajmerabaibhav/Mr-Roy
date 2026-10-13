"""Regressions from the 12 Oct product review: each test fails without its fix."""

import argparse
import datetime as dates
import json
import subprocess
from types import SimpleNamespace

from mr_roy import cli, config, grammar, micgate, report, schedule, textboxes


def test_claude_call_leaves_no_transcript(monkeypatch):
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: seen.append(cmd) or SimpleNamespace(
        returncode=0, stdout="[]", stderr=""))
    grammar._call_llm("/usr/bin/claude", "prompt", config)
    assert "--no-session-persistence" in seen[0]


def test_future_day_does_not_purge_todays_typing(monkeypatch):
    monkeypatch.setattr(schedule, "on_battery", lambda: False)
    textboxes.write("com.apple.Notes", ["I has written four words today."])
    cli._analyse_day(argparse.Namespace(day="2099-12-01", force=True))
    assert textboxes.for_day(dates.date.today())


def _morning_env(monkeypatch, calls):
    class Morning(dates.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.combine(dates.date.today(), dates.time(10))

    monkeypatch.setattr(dates, "datetime", Morning)
    monkeypatch.setattr(micgate, "is_mic_in_use", lambda: False)
    monkeypatch.setattr(config, "user_name", lambda: "Test")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(report, "open_report", lambda day: calls.append(day) or "report.html")


def test_manual_morning_opens_the_page_just_made(monkeypatch):
    calls = []
    _morning_env(monkeypatch, calls)
    today = dates.date.today()
    (config.REPORTS_DIR / f"{today}.html").write_text("report")
    config.write_json_atomically(config.REPORTS_DIR / f"{today}-analysis.json", {"version": 2})
    cli.cmd_morning(argparse.Namespace(automatic=False))
    assert calls == [today]


def test_unreadable_grammar_file_opens_the_page_once(monkeypatch):
    calls = []
    _morning_env(monkeypatch, calls)
    yesterday = dates.date.today() - dates.timedelta(days=1)
    (config.REPORTS_DIR / f"{yesterday}.html").write_text("report")
    config.write_json_atomically(config.REPORTS_DIR / f"{yesterday}-analysis.json", {"version": 2})
    (config.REPORTS_DIR / f"{yesterday}-grammar.json").write_text('[{"kind": "verb", "sa')
    for _ in range(3):
        cli.cmd_morning(argparse.Namespace(automatic=True))
    assert calls == [yesterday]


def test_one_torn_line_keeps_the_rest_of_the_day():
    day = dates.date(2026, 10, 11)
    textboxes.write("com.apple.Notes", ["The first sentence is fine."], day)
    with open(textboxes.folder() / f"{day}.jsonl", "a") as handle:
        handle.write('{"t": "2026-10-11T10:00", "app": "com.goo\n')
    textboxes.write("com.apple.Notes", ["The second sentence is fine."], day)
    assert len(textboxes.for_day(day)) == 2


def test_correction_must_quote_whole_words():
    reply = '{"i": 1, "said": "a apple", "should_be": "an apple", "kind": "article"}'
    assert grammar.parse_llm(reply, [("s", "I bought a banana apple")], "typed") == []
    assert len(grammar.parse_llm(reply, [("s", "I ate a apple today")], "typed")) == 1


def test_bare_links_are_scrubbed_but_not_ordinary_dots():
    assert "token" not in textboxes.scrub("see example.com/reset?token=abc for the reset")
    assert "[link]" in textboxes.scrub("open docs.google.com/document/d/1x please")
    assert textboxes.scrub("I use Node.js, e.g. for this") == "I use Node.js, e.g. for this"


def test_local_rules_page_is_not_an_all_clear():
    page = report.build_html(dates.date(2026, 10, 11), [], {"grammar_engine": "local-rules"})
    assert "Rest on it" not in page and "proves nothing" in page


def test_the_nightly_cap_is_on_the_page():
    items = [(f"s{n}", "this is a message that is long enough") for n in range(600)]
    assert grammar.unchecked(items) == 600 - grammar.LLM_BATCH * grammar.LLM_MAX_BATCHES
    page = report.build_html(dates.date(2026, 10, 11), [], {
        "grammar_engine": "claude-cli", "sources": {"typed": 600}, "unchecked": 120})
    assert "left 120 of them unchecked" in page


def test_remove_stops_the_other_jobs_when_one_is_stuck(monkeypatch, tmp_path):
    monkeypatch.setattr(schedule, "AGENTS_DIR", tmp_path)
    for label in schedule.JOBS:
        (tmp_path / f"{label}.plist").write_text("x")
    stuck = next(iter(schedule.JOBS))
    monkeypatch.setattr(schedule, "service_state", lambda label: {"loaded": label == stuck})
    monkeypatch.setattr(schedule, "_launchctl", lambda *a: SimpleNamespace(returncode=5, stderr="5: I/O"))
    try:
        schedule.uninstall()
    except schedule.InstallationError:
        pass
    assert [p.stem for p in tmp_path.glob("*.plist")] == [stuck]


def test_dictation_quote_contains_the_mistake():
    # Wispr's hand-edit path quoted the first 160 characters, not the mistake.
    heard = ("Okay so this morning I sat down with my notes and went through everything again, "
             "and I was thinking of adding only these three features to the thing that we have "
             "been building over the past few weeks with the team, and then we discussed about "
             "the plan yesterday")
    found = grammar.compare(heard, heard.replace("discussed about", "discussed"), "w", edited=True)
    assert found and all(f.said in f.context.lower() for f in found)


def test_jobs_keep_ai_settings_and_this_install(monkeypatch, tmp_path):
    monkeypatch.setenv("MR_ROY_LLM", "codex")
    monkeypatch.setattr(schedule.sys, "executable", str(tmp_path / "python"))
    (tmp_path / "roy").touch()
    data = schedule.plist_for("com.mrroy.nightly", schedule.JOBS["com.mrroy.nightly"])
    assert data["EnvironmentVariables"]["MR_ROY_LLM"] == "codex"
    assert data["ProgramArguments"][0] == str(tmp_path / "roy")


def test_icon_file_needs_no_tool():
    png = schedule._icon_png()
    data = schedule.icns(png)
    assert data[:4] == b"icns" and int.from_bytes(data[4:8], "big") == len(data)
    assert data[8:12] == b"ic10" and data[16:] == png
