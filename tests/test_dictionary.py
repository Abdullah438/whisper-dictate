"""The user dictionary is the last pass, so it has to win over the model."""
from __future__ import annotations


def write(tmp_path, body: str) -> str:
    path = tmp_path / "dictionary"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_reads_entries_and_ignores_comments(polish_mod, tmp_path):
    path = write(tmp_path, "# a comment\n\nkubernetes = Kubernetes\nnot an entry\n")
    assert polish_mod.load_dictionary(path) == [("kubernetes", "Kubernetes")]


def test_replaces_case_insensitively_on_word_boundaries(polish_mod, tmp_path):
    entries = polish_mod.load_dictionary(write(tmp_path, "pipe wire = PipeWire\n"))
    assert polish_mod.apply_dictionary("the Pipe Wire daemon", entries) == "the PipeWire daemon"
    # Not inside another word.
    assert polish_mod.apply_dictionary("pipewired", entries) == "pipewired"


def test_longest_entry_wins(polish_mod, tmp_path):
    entries = polish_mod.load_dictionary(
        write(tmp_path, "code = code\nvisual studio code = VS Code\n")
    )
    assert polish_mod.apply_dictionary("open visual studio code", entries) == "open VS Code"


def test_a_short_entry_does_not_eat_a_longer_replacement(polish_mod, tmp_path):
    """Applied one at a time, "code" would rewrite the "Code" in "VS Code"."""
    entries = polish_mod.load_dictionary(
        write(tmp_path, "code = code\nvisual studio code = VS Code\n")
    )
    assert polish_mod.apply_dictionary("open Visual Studio Code now", entries) == "open VS Code now"


def test_replacement_backslashes_are_literal(polish_mod, tmp_path):
    entries = polish_mod.load_dictionary(write(tmp_path, r"back slash = \1 \n"))
    assert polish_mod.apply_dictionary("a back slash here", entries) == r"a \1 \n here"


def test_missing_file_is_not_an_error(polish_mod, tmp_path):
    assert polish_mod.load_dictionary(str(tmp_path / "nope")) == []


def test_fix_nouns_applies_builtins_then_the_dictionary(polish_mod, tmp_path, monkeypatch):
    monkeypatch.setenv("DICTATE_DICTIONARY", write(tmp_path, "why do tool = ydotool\n"))
    out = polish_mod.fix_nouns("u lama types with why do tool")
    assert out == "Ollama types with ydotool"
