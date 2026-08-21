"""Rewrite has the same job as polish: never invent, never change who is speaking."""
from __future__ import annotations


def test_pronoun_drift_flags_a_dropped_speaker(rewrite_mod):
    assert rewrite_mod.pronoun_drift(
        "i think i can do it and i will tell you",
        "The task will be done and an update will follow.",
    )


def test_pronoun_drift_allows_a_faithful_edit(rewrite_mod):
    assert not rewrite_mod.pronoun_drift(
        "i think i can do it and i will tell you",
        "I think I can do it, and I will tell you.",
    )


def test_a_paragraph_is_not_exploded_into_chat_lines(rewrite_mod):
    raw = "hey can you check the log and tell me what you see"
    out = "Hey,\ncan you check the log\nand tell me what you see?"
    assert "\n" not in rewrite_mod.align_line_breaks(raw, out)


def test_existing_paragraph_breaks_survive(rewrite_mod):
    raw = "first para\n\nsecond para"
    out = "First para.\n\nSecond para."
    assert rewrite_mod.align_line_breaks(raw, out) == out


def test_shares_the_context_size_with_polish(rewrite_mod, polish_mod):
    assert rewrite_mod.LLM_NUM_CTX == polish_mod.LLM_NUM_CTX
