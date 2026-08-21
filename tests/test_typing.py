"""How a line break reaches the focused window.

`ydotool type` turns a newline into KEY_ENTER, and in a message box Enter
sends. A rewrite that spans two lines would post half a sentence and type the
rest into the next message, so the separator has to be chosen deliberately.
"""
from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMMON = ROOT / "bin" / "dictate-common.sh"

FAKE_YDOTOOL = """#!/bin/sh
if [ "$1" = "key" ]; then shift; printf 'key %s\\n' "$*" >> "$YDOTOOL_LOG"; exit 0; fi
f=""
while [ $# -gt 0 ]; do [ "$1" = "--file" ] && f="$2"; shift; done
printf 'type %s\\n' "$(cat "$f")" >> "$YDOTOOL_LOG"
"""

SHIFT_ENTER = "key 42:1 28:1 28:0 42:0"
BARE_ENTER = "key 28:1 28:0"


@pytest.fixture
def typer(tmp_path):
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    tool = fakebin / "ydotool"
    tool.write_text(FAKE_YDOTOOL)
    tool.chmod(0o755)
    log = tmp_path / "calls.log"
    scratch = tmp_path / "scratch.txt"

    def run(text: str, **env) -> list[str]:
        log.write_text("")
        subprocess.run(
            ["bash", "-c",
             f'source "{COMMON}"; dictate_type_text "$1" "{scratch}" /dev/null', "_", text],
            env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}",
                 "YDOTOOL_LOG": str(log),
                 "XDG_CONFIG_HOME": str(tmp_path / "config"), **env},
            check=True, capture_output=True, text=True,
        )
        return log.read_text().splitlines()

    run.scratch = scratch
    return run


def test_a_line_break_is_not_a_bare_enter(typer):
    calls = typer("Hey there\nsecond line")
    assert calls == ["type Hey there", SHIFT_ENTER, "type second line"]
    assert BARE_ENTER not in calls


def test_single_line_text_sends_no_keys_at_all(typer):
    assert typer("just one line") == ["type just one line"]


def test_several_breaks_each_get_a_separator(typer):
    calls = typer("one\ntwo\nthree")
    assert calls.count(SHIFT_ENTER) == 2
    assert [c for c in calls if c.startswith("type")] == ["type one", "type two", "type three"]


def test_blank_line_between_paragraphs_is_preserved(typer):
    calls = typer("para one\n\npara two")
    assert calls == ["type para one", SHIFT_ENTER, SHIFT_ENTER, "type para two"]


def test_enter_mode_restores_the_old_behaviour(typer):
    assert typer("one\ntwo", DICTATE_NEWLINE="enter") == ["type one", BARE_ENTER, "type two"]


def test_space_mode_joins_the_lines(typer):
    calls = typer("one\ntwo", DICTATE_NEWLINE="space")
    assert calls == ["type one", "type  ", "type two"]
    assert not any(c.startswith("key") for c in calls)


def test_the_scratch_file_does_not_outlive_the_typing(typer):
    typer("something private\nand more")
    assert not typer.scratch.exists()


CTRL_V = "key 29:1 47:1 47:0 29:0"
CTRL_SHIFT_V = "key 29:1 42:1 47:1 47:0 42:0 29:0"
SHIFT_INSERT = "key 42:1 110:1 110:0 42:0"
SET_PRIMARY = "wl-copy --primary --type text/plain"

# Stub, so a test can never write to the real primary selection.
FAKE_WL_COPY = """#!/bin/sh
printf 'wl-copy %s\\n' "$*" >> "$YDOTOOL_LOG"; cat > /dev/null
"""


@pytest.fixture
def inserter(tmp_path):
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    tool = fakebin / "ydotool"
    tool.write_text(FAKE_YDOTOOL)
    tool.chmod(0o755)
    clip = fakebin / "wl-copy"
    clip.write_text(FAKE_WL_COPY)
    clip.chmod(0o755)
    log = tmp_path / "calls.log"
    scratch = tmp_path / "scratch.txt"

    def run(text: str, **env) -> list[str]:
        log.write_text("")
        subprocess.run(
            ["bash", "-c",
             f'source "{COMMON}"; dictate_insert_text "$1" "{scratch}" /dev/null', "_", text],
            env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}",
                 "YDOTOOL_LOG": str(log),
                 "XDG_CONFIG_HOME": str(tmp_path / "config"), **env},
            check=True, capture_output=True, text=True,
        )
        return log.read_text().splitlines()

    return run


def test_default_still_types(inserter):
    assert inserter("hello there") == ["type hello there"]


def test_paste_is_one_keystroke_regardless_of_length(inserter):
    """The whole point: cost must not scale with the length of the transcript."""
    short = inserter("hi", DICTATE_INSERT="paste")
    long = inserter("word " * 400, DICTATE_INSERT="paste")
    assert short == [SET_PRIMARY, SHIFT_INSERT]
    assert long == [SET_PRIMARY, SHIFT_INSERT]


def test_the_default_chord_also_fills_the_primary_selection(inserter):
    """Konsole and Alacritty bind Shift+Insert to paste-primary, not clipboard."""
    calls = inserter("hi", DICTATE_INSERT="paste")
    assert calls.index(SET_PRIMARY) < calls.index(SHIFT_INSERT)


def test_paste_key_can_be_either_ctrl_chord(inserter):
    assert inserter("hi", DICTATE_INSERT="paste", DICTATE_PASTE_KEY="ctrl+v") == [CTRL_V]
    assert inserter("hi", DICTATE_INSERT="paste", DICTATE_PASTE_KEY="ctrl+shift+v") == [CTRL_SHIFT_V]


def test_paste_falls_back_to_typing_without_a_clipboard(inserter):
    """Pasting reads the clipboard, so it cannot work when that is switched off."""
    calls = inserter("hello", DICTATE_INSERT="paste", DICTATE_CLIPBOARD="0")
    assert calls == ["type hello"]


def test_paste_never_types_the_text(inserter):
    """A stray type call would double-insert the transcript."""
    calls = inserter("secret words\nsecond line", DICTATE_INSERT="paste")
    assert not any(c.startswith("type") for c in calls)


# "auto" types a short line and pastes a long one: typing is the better thing
# to watch, but its cost scales with length and pasting's does not.
def test_auto_types_a_short_line(inserter):
    calls = inserter("Sounds good to me.", DICTATE_INSERT="auto")
    assert calls == ["type Sounds good to me."]


def test_auto_pastes_a_long_one(inserter):
    long = "word " * 60
    calls = inserter(long, DICTATE_INSERT="auto")
    assert calls == [SET_PRIMARY, SHIFT_INSERT]


def test_auto_switches_exactly_at_the_threshold(inserter):
    at = "x" * 80
    over = "x" * 81
    assert inserter(at, DICTATE_INSERT="auto", DICTATE_TYPE_MAX_CHARS="80") == [f"type {at}"]
    assert inserter(over, DICTATE_INSERT="auto", DICTATE_TYPE_MAX_CHARS="80") == [
        SET_PRIMARY, SHIFT_INSERT
    ]


def test_the_threshold_is_configurable(inserter):
    text = "x" * 30
    assert inserter(text, DICTATE_INSERT="auto", DICTATE_TYPE_MAX_CHARS="10") == [
        SET_PRIMARY, SHIFT_INSERT
    ]
    assert inserter(text, DICTATE_INSERT="auto", DICTATE_TYPE_MAX_CHARS="200") == [f"type {text}"]


def test_auto_still_types_when_the_clipboard_is_off(inserter):
    """Pasting needs the clipboard; without it, length cannot change the answer."""
    long = "word " * 60
    calls = inserter(long, DICTATE_INSERT="auto", DICTATE_CLIPBOARD="0")
    assert calls == [f"type {long.strip()}"] or calls[0].startswith("type")
    assert not any(c.startswith("key") for c in calls)


def test_explicit_modes_ignore_the_threshold(inserter):
    """type and paste stay absolute — only auto looks at length."""
    long = "word " * 60
    assert inserter(long, DICTATE_INSERT="paste") == [SET_PRIMARY, SHIFT_INSERT]
    assert inserter("hi", DICTATE_INSERT="paste") == [SET_PRIMARY, SHIFT_INSERT]
    assert inserter(long, DICTATE_INSERT="type")[0].startswith("type")
