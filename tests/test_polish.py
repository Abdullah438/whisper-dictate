"""The polish guardrails are what keep the model from answering your dictation.

A weakened prompt still returns fluent text, so these regressions are invisible
in normal use. Each test pins one rejection rule with a canned model reply.
"""
from __future__ import annotations

import io
import json

import pytest


class FakeOpener:
    def __init__(self, reply: str, done_reason: str = "stop"):
        self.reply = reply
        self.done_reason = done_reason
        self.payload: dict | None = None
        self.timeout: float | None = None

    def open(self, req, timeout=None):
        self.payload = json.loads(req.data.decode())
        self.timeout = timeout
        body = json.dumps(
            {"message": {"content": self.reply}, "done_reason": self.done_reason}
        ).encode()
        return _Response(body)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_ollama(polish_mod, monkeypatch, isolated_env):
    def install(reply: str, done_reason: str = "stop") -> FakeOpener:
        opener = FakeOpener(reply, done_reason)
        monkeypatch.setattr(
            polish_mod.urllib.request, "build_opener", lambda *_a, **_k: opener
        )
        return opener

    return install


RAW = "so i was thinking we should ship the parser fix tomorrow"


def test_accepts_a_clean_copy_edit(polish_mod, fake_ollama):
    fake_ollama("So I was thinking we should ship the parser fix tomorrow.")
    assert polish_mod.polish(RAW) == "So I was thinking we should ship the parser fix tomorrow."


def test_rejects_an_answer_to_the_dictation(polish_mod, fake_ollama):
    # The classic failure: the model treats the transcript as a question.
    fake_ollama("Sure! Shipping tomorrow sounds reasonable as long as CI is green.")
    assert polish_mod.polish(RAW) == RAW


def test_rejects_a_much_longer_rewrite(polish_mod, fake_ollama):
    fake_ollama(
        "So I was thinking we should ship the parser fix tomorrow, "
        "assuming the test suite passes and the reviewers have signed off "
        "on the remaining comments in the pull request thread."
    )
    assert polish_mod.polish(RAW) == RAW


def test_rejects_pronoun_drift(polish_mod, fake_ollama):
    raw = "i think i can finish it today and i will tell you when i do"
    fake_ollama("The work should be finished today and an update will follow.")
    assert polish_mod.polish(raw) == raw


def test_rejects_a_spliced_in_recent_line(polish_mod, fake_ollama, isolated_env, monkeypatch):
    monkeypatch.setenv("DICTATE_CONTEXT_FILE", str(isolated_env / "recent.json"))
    polish_mod.remember_recent("The parser fix landed on Tuesday after the review")
    fake_ollama(
        "So I was thinking we should ship the parser fix tomorrow. "
        "The parser fix landed on Tuesday after the review."
    )
    assert polish_mod.polish(RAW) == RAW


def test_strips_preamble_and_fences(polish_mod, fake_ollama):
    fake_ollama("Here's the corrected transcript: So I was thinking we should ship the parser fix tomorrow.")
    assert polish_mod.polish(RAW).startswith("So I was thinking")


def test_strips_trailing_edited_note(polish_mod, fake_ollama):
    fake_ollama("So I was thinking we should ship the parser fix tomorrow. (edited)")
    assert polish_mod.polish(RAW).endswith("tomorrow.")


def test_keeps_a_question_as_a_question(polish_mod, fake_ollama):
    raw = "do you think we should ship the parser fix tomorrow"
    fake_ollama("Do you think we should ship the parser fix tomorrow?")
    assert polish_mod.polish(raw).endswith("?")


def test_never_calls_a_remote_host(polish_mod, monkeypatch, isolated_env):
    monkeypatch.setenv("LLM_HOST", "http://example.com:11434")
    called = False

    def boom(*_a, **_k):
        nonlocal called
        called = True
        raise AssertionError("must not open a remote connection")

    monkeypatch.setattr(polish_mod.urllib.request, "build_opener", boom)
    assert polish_mod.polish(RAW) == RAW
    assert not called


def test_uses_one_context_size(polish_mod, fake_ollama, isolated_env):
    """A num_ctx that differs from the keepalive makes Ollama reload the model."""
    opener = fake_ollama("So I was thinking we should ship the parser fix tomorrow.")
    polish_mod.polish(RAW)
    assert opener.payload is not None
    assert opener.payload["options"]["num_ctx"] == polish_mod.LLM_NUM_CTX

    polish_mod.remember_recent("Some earlier dictation about the tray icon")
    opener = fake_ollama("So I was thinking we should ship the parser fix tomorrow.")
    polish_mod.polish(RAW)
    assert opener.payload["options"]["num_ctx"] == polish_mod.LLM_NUM_CTX


def test_recent_is_capped_and_round_trips(polish_mod, isolated_env):
    for i in range(8):
        polish_mod.remember_recent(f"line number {i}")
    recent = polish_mod.load_recent()
    assert len(recent) == polish_mod.MAX_RECENT
    assert recent[-1] == "line number 7"


def test_context_can_be_disabled(polish_mod, isolated_env, monkeypatch):
    polish_mod.remember_recent("something said earlier")
    monkeypatch.setenv("DICTATE_CONTEXT", "0")
    assert polish_mod.load_recent() == []


def test_drops_a_brand_name_that_was_not_spoken(polish_mod):
    out = polish_mod.drop_unprompted(
        "i restarted the service", "I restarted the Ollama service",
        polish_mod.SPOKEN_OLLAMA, "Ollama",
    )
    assert "Ollama" not in out


def test_keeps_a_brand_name_that_was_spoken(polish_mod):
    out = polish_mod.drop_unprompted(
        "i restarted olama", "I restarted Ollama.",
        polish_mod.SPOKEN_OLLAMA, "Ollama",
    )
    assert "Ollama" in out


# A dictation long enough that the model's reply can run out of tokens. Every
# other guard here watches for words being added; these watch for them going
# missing, which is what truncation and summarising look like.
LONG_RAW = " ".join(
    f"the {a} step {b} the {c} record before the window closes"
    for a in ("parser", "worker", "cache", "router", "backup", "index")
    for b in ("reads", "checks", "rotates")
    for c in ("staging", "nightly", "pending")
)


def test_a_truncated_reply_is_refused(polish_mod, fake_ollama):
    """Ollama says done_reason=length when it ran out of tokens mid-sentence."""
    half = " ".join(LONG_RAW.split()[: len(LONG_RAW.split()) // 2]) + " and then the"
    fake_ollama(half, done_reason="length")
    assert polish_mod.polish(LONG_RAW) == LONG_RAW


def test_a_summarised_reply_is_refused(polish_mod, fake_ollama):
    """done_reason=stop, fluent, plausible — and a third of the words gone."""
    third = " ".join(LONG_RAW.split()[: len(LONG_RAW.split()) // 3]) + "."
    fake_ollama(third)
    assert polish_mod.polish(LONG_RAW) == LONG_RAW


def test_removing_filler_is_still_allowed(polish_mod, fake_ollama):
    """The floor must not punish the shortening polish is supposed to do.

    About a sixth filler, which is normal for speech. The cleaned version
    keeps ~83% of the words and has to survive the floor.
    """
    spoken = " ".join(
        f"um word{i} word{i}a word{i}b word{i}c word{i}d" for i in range(20)
    )
    cleaned = " ".join(
        f"word{i} word{i}a word{i}b word{i}c word{i}d" for i in range(20)
    ) + "."
    fake_ollama(cleaned)
    assert polish_mod.polish(spoken) == cleaned


def test_short_dictations_are_exempt_from_the_floor(polish_mod, fake_ollama):
    """A brief line gets edited without the floor second-guessing it."""
    raw = "um so i think we should go now"
    fake_ollama("So I think we should go now.")
    assert polish_mod.polish(raw) == "So I think we should go now."


def test_the_token_budget_covers_a_long_dictation(polish_mod, fake_ollama):
    """1024 cut a reply off at about four minutes of speech."""
    opener = fake_ollama("fine.")
    polish_mod.polish("hello there friend")
    assert opener.payload["options"]["num_predict"] >= 2048
    assert opener.payload["options"]["num_ctx"] == polish_mod.LLM_NUM_CTX


def test_a_long_dictation_gets_a_longer_timeout(polish_mod, fake_ollama):
    short = fake_ollama("fine.")
    polish_mod.polish("hello there friend")
    long_opener = fake_ollama("fine.")
    polish_mod.polish(LONG_RAW)
    assert long_opener.timeout > short.timeout


# The model sometimes signs off with an aside after an otherwise correct edit.
# It defeats every other guard at once: the transcript is all present so the
# overlap is perfect, and a short note fits inside the too_long slack.
ASIDE = "(No recent dictations were provided to use for this transcript.)"


def test_an_appended_note_is_stripped_not_typed(polish_mod, fake_ollama):
    raw = "what do you think can AI do in this era"
    fake_ollama(f"What do you think AI can do in this era? {ASIDE}")
    assert polish_mod.polish(raw) == "What do you think AI can do in this era?"


def test_a_reply_that_is_only_a_note_falls_back(polish_mod, fake_ollama):
    raw = "okay"
    fake_ollama(ASIDE)
    assert polish_mod.polish(raw) == raw


def test_a_bracketed_note_is_stripped_too(polish_mod, fake_ollama):
    raw = "ship it tomorrow if the tests pass"
    fake_ollama("Ship it tomorrow if the tests pass. [note: no context supplied]")
    assert polish_mod.polish(raw) == "Ship it tomorrow if the tests pass."


def test_the_old_edited_marker_is_still_handled(polish_mod, fake_ollama):
    raw = "ship it tomorrow if the tests pass"
    fake_ollama("Ship it tomorrow if the tests pass. (edited)")
    assert polish_mod.polish(raw) == "Ship it tomorrow if the tests pass."


def test_a_parenthetical_the_speaker_said_survives(polish_mod, fake_ollama):
    """Only asides the speaker did not say are removed."""
    raw = "i paid the bill the big one"
    fake_ollama("I paid the bill (the big one).")
    assert polish_mod.polish(raw) == "I paid the bill (the big one)."


def test_recent_dictations_are_not_mentioned_when_there_are_none(
    polish_mod, fake_ollama, isolated_env
):
    """Naming them unprompted is what invited the note about their absence."""
    opener = fake_ollama("Fine.")
    polish_mod.polish("this is a line with several words in it")
    system = opener.payload["messages"][0]["content"]
    assert "recent dictation" not in system.lower()

    polish_mod.remember_recent("an earlier line about the tray icon")
    opener = fake_ollama("Fine.")
    polish_mod.polish("this is a line with several words in it")
    assert "recent dictation" in opener.payload["messages"][0]["content"].lower()
