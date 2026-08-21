"""Shell-level behaviour: the hallucination filter, the lock, and config loading."""
from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOGGLE = ROOT / "bin" / "dictate-toggle"
COMMON = ROOT / "bin" / "dictate-common.sh"


def bash(script: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


@pytest.fixture
def run_dir(tmp_path):
    return {"XDG_RUNTIME_DIR": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "config")}


def clean_text(value: str, run_dir: dict) -> str:
    result = bash(f'source "{TOGGLE}"; clean_text "$1"' + ' _ "$@"', run_dir)
    return result.stdout


@pytest.mark.parametrize(
    "raw",
    ["Thank you.", "thank you", "Thanks for watching.", "you", "[BLANK_AUDIO]", "   "],
)
def test_whisper_hallucinations_are_dropped(raw, run_dir):
    out = bash(f'source "{TOGGLE}"; clean_text {raw!r}', run_dir)
    assert out.stdout == "", out.stderr


def test_real_speech_survives_and_is_collapsed(run_dir):
    script = 'source "%s"; clean_text "$(printf \'  hello\\n  there  \')"' % TOGGLE
    out = bash(script, run_dir)
    assert out.stdout == "hello there", out.stderr


def test_sourcing_does_not_start_a_recording(run_dir, tmp_path):
    out = bash(f'source "{TOGGLE}"; echo sourced', run_dir)
    assert out.stdout.strip().endswith("sourced")
    assert not (tmp_path / "whisper-dictate" / "record.pid").exists()


def test_status_reports_idle(run_dir):
    out = bash(f'"{TOGGLE}" --status', run_dir)
    assert out.stdout.strip() == "idle"


def test_lock_is_held_against_a_live_owner(run_dir, tmp_path):
    lock = tmp_path / "lock.d"
    out = bash(
        f'source "{COMMON}"; dictate_acquire_lock "{lock}" && echo first;'
        f' dictate_acquire_lock "{lock}" && echo second || echo busy',
        run_dir,
    )
    assert out.stdout.split() == ["first", "busy"]


def test_a_dead_owner_does_not_wedge_dictation_forever(run_dir, tmp_path):
    """Without stale-lock recovery, one crash makes every later press "Busy"."""
    lock = tmp_path / "lock.d"
    lock.mkdir()
    # A PID that cannot be running: the previous holder died without cleaning up.
    (lock / "pid").write_text("2\n")
    out = bash(
        f'source "{COMMON}"; touch -d "1 hour ago" "{lock}";'
        f' dictate_acquire_lock "{lock}" && echo recovered || echo wedged',
        run_dir,
    )
    assert out.stdout.strip() == "recovered"


def test_config_file_supplies_settings(run_dir, tmp_path):
    cfg = tmp_path / "config" / "whisper-dictate"
    cfg.mkdir(parents=True)
    (cfg / "config").write_text("WHISPER_LANG=de\n")
    out = bash(f'source "{COMMON}"; echo "$WHISPER_LANG"', run_dir)
    assert out.stdout.strip() == "de"


def test_environment_overrides_the_config_file(run_dir, tmp_path):
    cfg = tmp_path / "config" / "whisper-dictate"
    cfg.mkdir(parents=True)
    (cfg / "config").write_text("WHISPER_LANG=de\n")
    out = bash(f'source "{COMMON}"; echo "$WHISPER_LANG"', {**run_dir, "WHISPER_LANG": "fr"})
    assert out.stdout.strip() == "fr"


def test_config_values_reach_child_processes(run_dir, tmp_path):
    """dictate-watch and the Python helpers read the environment, not the shell."""
    cfg = tmp_path / "config" / "whisper-dictate"
    cfg.mkdir(parents=True)
    (cfg / "config").write_text("DICTATE_SILENCE_SECONDS=2.5\n")
    out = bash(
        f'source "{COMMON}"; python3 -c'
        ' \'import os; print(os.environ.get("DICTATE_SILENCE_SECONDS", "unset"))\'',
        run_dir,
    )
    assert out.stdout.strip() == "2.5", out.stderr


def test_a_world_writable_config_is_ignored(run_dir, tmp_path):
    cfg = tmp_path / "config" / "whisper-dictate"
    cfg.mkdir(parents=True)
    target = cfg / "config"
    target.write_text("WHISPER_LANG=de\n")
    target.chmod(0o666)
    out = bash(f'source "{COMMON}"; echo "${{WHISPER_LANG:-unset}}"', run_dir)
    assert out.stdout.strip() == "unset"
    assert "ignoring" in out.stderr


def test_the_process_locale_is_left_alone(run_dir):
    """WHISPER_LANG=en must not become LANG=en for whisper-cli and friends."""
    out = bash(
        f'export LANG=en_US.UTF-8; source "{TOGGLE}"; echo "$LANG"',
        {**run_dir, "WHISPER_LANG": "en"},
    )
    assert out.stdout.strip() == "en_US.UTF-8"
