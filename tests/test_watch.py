"""The watchdog is what stops a forgotten recording from filling tmpfs."""
from __future__ import annotations

import array
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import time

BIN = pathlib.Path(__file__).resolve().parent.parent / "bin"


def write_wav(path, samples):
    data = array.array("h", samples).tobytes()
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
    header += b"data" + struct.pack("<I", len(data))
    path.write_bytes(header + data)
    return str(path)


def test_duration_reads_a_growing_file(watch_mod, tmp_path):
    wav = write_wav(tmp_path / "a.wav", [0] * 16000)
    assert abs(watch_mod.duration(wav) - 1.0) < 0.01


def test_tail_rms_is_low_for_silence(watch_mod, tmp_path):
    wav = write_wav(tmp_path / "b.wav", [0] * 32000)
    assert watch_mod.tail_rms(wav, 1.0) == 0.0


def test_tail_rms_is_high_for_speech(watch_mod, tmp_path):
    loud = [6000 if i % 2 else -6000 for i in range(32000)]
    wav = write_wav(tmp_path / "c.wav", loud)
    assert watch_mod.tail_rms(wav, 1.0) > 5000


def test_tail_rms_only_looks_at_the_end(watch_mod, tmp_path):
    loud = [6000 if i % 2 else -6000 for i in range(16000)]
    wav = write_wav(tmp_path / "d.wav", loud + [0] * 16000)
    assert watch_mod.tail_rms(wav, 0.5) == 0.0


def test_tail_rms_waits_for_enough_audio(watch_mod, tmp_path):
    wav = write_wav(tmp_path / "e.wav", [0] * 800)
    assert watch_mod.tail_rms(wav, 1.0) is None


def test_missing_file_is_not_an_error(watch_mod, tmp_path):
    assert watch_mod.tail_rms(str(tmp_path / "nope.wav"), 1.0) is None
    assert watch_mod.duration(str(tmp_path / "nope.wav")) == 0.0


def fake_recorder(tmp_path):
    """A live process whose comm is pw-cat, so the watchdog treats it as the recorder."""
    binary = tmp_path / "pw-cat"
    shutil.copy(shutil.which("sleep"), binary)
    binary.chmod(0o755)
    return subprocess.Popen([str(binary), "30"])


def staged_watcher(tmp_path):
    """A copy of the watchdog next to a stub toggle, so nothing real is started."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy(BIN / "dictate-watch", bindir / "dictate-watch")
    stub = bindir / "dictate-toggle"
    stub.write_text('#!/bin/sh\ntouch "$0.called"\n')
    stub.chmod(0o755)
    return bindir


def run_watcher(bindir, run_dir, **env):
    subprocess.run(
        [sys.executable, str(bindir / "dictate-watch")],
        env={
            **os.environ,
            "XDG_RUNTIME_DIR": str(run_dir),
            "DICTATE_MAX_SECONDS": "0",
            **env,
        },
        timeout=20,
        check=True,
    )
    return (bindir / "dictate-toggle.called").exists()


LOUD = [6000 if i % 2 else -6000 for i in range(16000)]
QUIET = [0] * 32000


def test_stops_once_the_speaker_goes_quiet(tmp_path):
    state = tmp_path / "run" / "whisper-dictate"
    state.mkdir(parents=True)
    write_wav(state / "dictation.wav", LOUD + QUIET)
    recorder = fake_recorder(tmp_path)
    (state / "record.pid").write_text(str(recorder.pid))
    try:
        assert run_watcher(staged_watcher(tmp_path), tmp_path / "run",
                           DICTATE_SILENCE_SECONDS="1.0")
    finally:
        recorder.kill()
        recorder.wait()


def test_does_not_stop_before_the_speaker_starts(tmp_path):
    """Silence at the very beginning must not cut the recording short."""
    state = tmp_path / "run" / "whisper-dictate"
    state.mkdir(parents=True)
    write_wav(state / "dictation.wav", QUIET)
    recorder = fake_recorder(tmp_path)
    (state / "record.pid").write_text(str(recorder.pid))
    bindir = staged_watcher(tmp_path)

    watcher = subprocess.Popen(
        [sys.executable, str(bindir / "dictate-watch")],
        env={**os.environ, "XDG_RUNTIME_DIR": str(tmp_path / "run"),
             "DICTATE_MAX_SECONDS": "0", "DICTATE_SILENCE_SECONDS": "0.5"},
    )
    try:
        time.sleep(2)
        assert not (bindir / "dictate-toggle.called").exists()
    finally:
        recorder.kill()
        recorder.wait()
        watcher.wait(timeout=10)


def test_exits_when_the_recording_ends(tmp_path):
    state = tmp_path / "run" / "whisper-dictate"
    state.mkdir(parents=True)
    write_wav(state / "dictation.wav", QUIET)
    (state / "record.pid").write_text("2")  # a PID that cannot be the recorder
    assert not run_watcher(staged_watcher(tmp_path), tmp_path / "run",
                           DICTATE_SILENCE_SECONDS="0.5")


def test_fresh_rms_advances_its_cursor(watch_mod, tmp_path):
    wav = write_wav(tmp_path / "f.wav", [0] * 16000)
    level, cursor = watch_mod.fresh_rms(wav, watch_mod.WAV_HEADER)
    assert level == 0.0
    assert cursor == watch_mod.WAV_HEADER + 32000
    # Nothing new yet.
    assert watch_mod.fresh_rms(wav, cursor) == (None, cursor)


def test_fresh_rms_sees_speech_the_tail_window_would_miss(watch_mod, tmp_path):
    """Loud at the start, silent at the end — the trailing window reads 0."""
    wav = write_wav(tmp_path / "g.wav", LOUD + QUIET)
    level, _ = watch_mod.fresh_rms(wav, watch_mod.WAV_HEADER)
    assert level is not None and level > 700
    assert watch_mod.tail_rms(wav, 1.0) == 0.0


def test_fresh_rms_resets_when_the_file_is_reused(watch_mod, tmp_path):
    wav = write_wav(tmp_path / "h.wav", [0] * 800)
    _level, cursor = watch_mod.fresh_rms(wav, watch_mod.WAV_HEADER + 10_000_000)
    assert cursor == watch_mod.WAV_HEADER
