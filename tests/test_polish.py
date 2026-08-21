"""The polish guardrails are what keep the model from answering your dictation.

A weakened prompt still returns fluent text, so these regressions are invisible
in normal use. Each test pins one rejection rule with a canned model reply.
"""
from __future__ import annotations

import io
import json

import pytest


class FakeOpener:
    def __init__(self, reply: str):
        self.reply = reply
        self.payload: dict | None = None

    def open(self, req, timeout=None):
        self.payload = json.loads(req.data.decode())
        body = json.dumps({"message": {"content": self.reply}}).encode()
        return _Response(body)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_ollama(polish_mod, monkeypatch, isolated_env):
    def install(reply: str) -> FakeOpener:
        opener = FakeOpener(reply)
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
