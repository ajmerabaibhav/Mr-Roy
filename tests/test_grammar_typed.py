"""The two new sources: a checked LLM reply, and the day's typing."""

import json
from dataclasses import asdict
from datetime import date, datetime, timezone

import pytest

from mr_roy import grammar, typed

ITEMS = [("a", "the result which you have gave is not new"),
         ("b", "can you check the people that is building it")]


def _reply(*rows):
    return "```json\n" + "\n".join(json.dumps(r) for r in rows) + "\n```"


def test_parse_keeps_real_corrections():
    out = grammar.parse_llm(_reply(
        {"i": 1, "said": "you have gave", "should_be": "you have given",
         "kind": "verb", "why": "past participle after have"},
    ), ITEMS)
    assert len(out) == 1
    f = out[0]
    assert (f.said, f.should_be, f.kind, f.basis, f.mode) == (
        "you have gave", "you have given", "verb", "llm", "spoken")
    assert f.instruction == 'use "given"'
    assert f.rule == "past participle after have"  # the checker's reason, not the generic one


def test_parse_drops_what_was_never_said():
    """A correction whose span is not in the transcript is an invention."""
    out = grammar.parse_llm(_reply(
        {"i": 1, "said": "I are going home", "should_be": "I am going home", "kind": "verb"},
        {"i": 9, "said": "you have gave", "should_be": "you have given", "kind": "verb"},
        {"i": 2, "said": "the people that is", "should_be": "the people that is", "kind": "verb"},
    ), ITEMS)
    assert out == []


def test_parse_dedupes_and_survives_junk():
    row = {"i": 2, "said": "people that is building", "should_be": "people that are building",
           "kind": "verb", "why": "plural subject"}
    out = grammar.parse_llm("Here you go:\n" + _reply(row, row) + "\nnot json at all", ITEMS)
    assert len(out) == 1 and out[0].source == "b"


def test_typed_reads_only_what_a_person_typed(tmp_path, monkeypatch):
    monkeypatch.setattr(typed, "PROJECTS", tmp_path)
    folder = tmp_path / "-Users-someone-work"
    folder.mkdir()
    when = datetime(2026, 9, 20, 10, 30, tzinfo=timezone.utc)

    def row(text, **extra):
        return json.dumps({"type": "user", "timestamp": when.isoformat().replace("+00:00", "Z"),
                           "message": {"role": "user", "content": text}, **extra})

    (folder / "session.jsonl").write_text("\n".join([
        row("can you check whether the build is working or not"),
        row("/clear"),                                    # a command, not prose
        row("<system-reminder>be good</system-reminder>"),  # never typed
        row("look at this <pasted_content id=1>x y z q</pasted_content>"),  # too short once stripped
        row("[Request interrupted by user for tool use]"),  # written by the tool
        row("yes"),                                        # too short
        row("i said this one out loud into the microphone"),  # dictated, not typed
        json.dumps({"type": "assistant", "timestamp": when.isoformat(),
                    "message": {"content": "reply from the model here"}}),
        "{ broken json",
    ]) + "\n")
    # A transcript belonging to this project is our own grammar call coming back.
    ours = tmp_path / "-Users-someone-mr-roy-data-llm"
    ours.mkdir()
    (ours / "s.jsonl").write_text(row("this prompt was written by the checker itself") + "\n")

    out = typed.for_day(date(2026, 9, 20),
                        exclude=["I said this one out loud into the microphone."])
    assert [text for _, text in out] == ["can you check whether the build is working or not"]


def test_llm_is_optional(monkeypatch):
    monkeypatch.setattr(grammar, "llm_binary", lambda: "/bin/echo")
    assert grammar.llm_available()
    monkeypatch.setattr(grammar, "llm_binary", lambda: None)
    assert not grammar.llm_available()
    assert grammar.llm_check(ITEMS) == []  # and nothing is spawned


def test_label_is_one_word_and_verified():
    out = grammar.parse_llm(_reply(
        {"i": 1, "said": "you have gave", "should_be": "you have given", "kind": "verb",
         "label": "Participle form", "why": "past participle after have"},
    ), ITEMS)
    assert out[0].label == "participle"  # one word, lowercased


def test_the_certain_rules_run_beside_the_model_without_repeating_it():
    """A rule never has an off night, but it must not say what was already said."""
    from mr_roy.grammar import GrammarFinding

    llm = [GrammarFinding("phrase", "revert back to me", "reply to me", "ctx", "u1",
                          basis="llm", mode="spoken")]
    rules = [
        GrammarFinding("phrase", "revert back", "reply", "ctx", "u1", basis="rule"),   # same span
        GrammarFinding("phrase", "am having a doubt", "have a doubt", "ctx", "u2",
                       basis="rule"),                                                   # new
    ]
    merged = grammar.merge(llm, rules)
    assert [f.said for f in merged] == ["revert back to me", "am having a doubt"]


def test_indian_english_vocabulary_is_not_marked_as_a_mistake():
    """Grammar is corrected. A regional word is not a mistake, and saying it is
    loses the reader in one morning."""
    for fine in ("Please prepone the meeting to Tuesday",
                 "Kindly do the needful before Friday",
                 "I have a doubt about the pricing"):
        assert grammar.check(fine, "x") == [], fine
    # but the stative verb in the continuous is grammar, and is caught
    caught = grammar.check("I am having a doubt about the pricing", "x")
    assert [(f.said, f.should_be) for f in caught] == [("am having a doubt", "have a doubt")]


def test_codex_is_used_when_claude_is_missing(monkeypatch, tmp_path):
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\necho '{\"i\": 1, \"said\": \"you have gave\", \"should_be\": \"you have given\", \"kind\": \"verb\"}'\n")
    codex.chmod(0o755)
    monkeypatch.setattr(grammar, "LLM_CLI", "")
    monkeypatch.setattr(grammar.shutil, "which", lambda name: str(codex) if name == "codex" else None)
    monkeypatch.setattr(grammar.os, "access", lambda path, mode: str(path) == str(codex))
    assert grammar.llm_name() == "codex"
    found = grammar.llm_check([("s1", "thank you for the result you have gave me today")], "typed")
    assert [(f.said, f.should_be) for f in found] == [("you have gave", "you have given")]


def test_typed_reads_codex_prompt_history(tmp_path, monkeypatch):
    monkeypatch.setattr(typed, "PROJECTS", tmp_path / "none")
    history = tmp_path / "history.jsonl"
    monkeypatch.setattr(typed, "CODEX_HISTORY", history)
    noon = datetime(2026, 9, 20, 12, 0).timestamp()
    history.write_text("\n".join([
        json.dumps({"session_id": "s", "ts": noon, "text": "can you tell me that whether it is good"}),
        json.dumps({"session_id": "s", "ts": noon - 86400, "text": "this one was typed the day before"}),
        json.dumps({"session_id": "s", "ts": noon, "text": "/model"}),
        "{ broken json",
    ]) + "\n")
    out = typed.for_day(date(2026, 9, 20))
    assert [text for _, text in out] == ["can you tell me that whether it is good"]


def test_logged_out_claude_falls_back_to_codex(monkeypatch):
    monkeypatch.setattr(grammar, "llm_binaries", lambda: ["/x/claude", "/x/codex"])
    tried = []

    def call(binary, prompt, config):
        tried.append(binary)
        if binary.endswith("claude"):
            raise RuntimeError("Not logged in · Please run /login")
        return "codex reply"

    monkeypatch.setattr(grammar, "_call_llm", call)
    assert grammar._run_llm("p") == "codex reply"
    monkeypatch.setattr(grammar, "_call_llm", lambda *a: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(RuntimeError):  # both fail: the day is marked unfinished and retried
        grammar._run_llm("p")


def test_text_box_mistakes_are_not_crowded_out_by_chats():
    chats = [{"mode": "typed", "source": f"2026-10-05-typed-56acc225-{n}", "said": f"c{n}"} for n in range(8)]
    boxes = [{"mode": "typed", "source": f"2026-10-05-typed-ax-{n}", "said": f"b{n}"} for n in range(3)]
    spoken = [{"mode": "spoken", "source": "2026-10-05-wispr-x", "said": "s"}]
    shown = grammar.typed_rows(spoken + chats + boxes, 6)
    assert [r["said"] for r in shown] == ["c0", "b0", "c1", "b1", "c2", "b2"]
    assert len(grammar.typed_rows(chats, 6)) == 6  # no text boxes: chats fill the section


def test_text_box_sentence_already_in_a_chat_is_counted_once(tmp_path, monkeypatch):
    # 6 Oct: the Claude app's box and its transcript both held one message,
    # and its single mistake showed as "2 times".
    from mr_roy import textboxes

    message = "can you check that wether this thing i can isntalled in a smart kiosk or not"
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "s.jsonl").write_text(json.dumps({
        "type": "user", "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": {"content": message + ". and also tell me why"}}) + "\n")
    monkeypatch.setattr(typed, "PROJECTS", tmp_path)
    monkeypatch.setattr(typed, "CODEX_HISTORY", tmp_path / "none")
    monkeypatch.setattr(textboxes, "for_day", lambda day: [("app", message + ".")])
    assert len(typed.for_day(date.today())) == 1


def test_two_passes_merge_one_mistake_once():
    items = [("a", "so i want clear few of my doubts about whole thing today")]
    f = lambda said, to: grammar.GrammarFinding(kind="article", said=said, should_be=to, context="", source="a")
    first = [f("clear few of", "clear a few of")]
    second = [f("clear few of my doubts", "clear a few of my doubts"), f("about whole thing", "about the whole thing")]
    merged = grammar.merge_passes(first, second, items)
    assert [m.said for m in merged] == ["clear few of", "about whole thing"]


def test_page_shows_no_history_it_cannot_keep():
    """Data is kept two days: no weekly comparison, no repeat counts (product review, 12 Oct)."""
    from datetime import date

    from mr_roy import report

    row = asdict(grammar.check("he don't know", "one", "typed")[0]) | {"times": 5}
    page = report.build_html(date(2026, 10, 15), grammar=[row], analysis={"grammar_engine": "claude-cli"})
    assert "Seven days" not in page and "compared with" not in page
    assert "times this month" not in page and "5 times" not in page
