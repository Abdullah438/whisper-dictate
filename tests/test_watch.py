"""The watchdog is what stops a forgotten recording from filling tmpfs."""
from __future__ import annotations

import array
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import threading
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


def grow_wav(path, chunks, interval=0.1):
    """Append audio over time, the way pw-cat writes while recording."""

    def run():
        for chunk in chunks:
            with open(path, "ab") as fh:
                fh.write(array.array("h", chunk).tobytes())
            time.sleep(interval)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


CHUNK_LOUD = [6000 if i % 2 else -6000 for i in range(4000)]
CHUNK_QUIET = [0] * 4000


def test_stops_once_the_speaker_goes_quiet(tmp_path):
    state = tmp_path / "run" / "whisper-dictate"
    state.mkdir(parents=True)
    wav = state / "dictation.wav"
    write_wav(wav, [])
    recorder = fake_recorder(tmp_path)
    (state / "record.pid").write_text(str(recorder.pid))
    grow_wav(wav, [CHUNK_QUIET] * 4 + [CHUNK_LOUD] * 8 + [CHUNK_QUIET] * 20)
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


def test_does_not_stop_on_a_pause_shorter_than_configured(tmp_path):
    """A quieter word followed by a short pause must not read as sustained
    silence. Regression test: DICTATE_SILENCE_SECONDS used to double as the
    RMS averaging window, so a quieter word blended with a shorter pause
    could average out to "quiet" well before the speaker had gone silent
    that long -- cutting the recording off mid-sentence."""
    state = tmp_path / "run" / "whisper-dictate"
    state.mkdir(parents=True)
    wav = state / "dictation.wav"
    write_wav(wav, [])
    recorder = fake_recorder(tmp_path)
    (state / "record.pid").write_text(str(recorder.pid))
    bindir = staged_watcher(tmp_path)

    moderate = [1200 if i % 2 else -1200 for i in range(4000)]
    grow_wav(
        wav,
        [CHUNK_QUIET] * 2 + [CHUNK_LOUD] * 4 + [moderate] * 10 + [CHUNK_QUIET] * 40,
        interval=0.1,
    )

    watcher = subprocess.Popen(
        [sys.executable, str(bindir / "dictate-watch")],
        env={**os.environ, "XDG_RUNTIME_DIR": str(tmp_path / "run"),
             "DICTATE_MAX_SECONDS": "0", "DICTATE_SILENCE_SECONDS": "2.0"},
    )
    try:
        # The pause starts around t=1.6s; this is only ~1s into it.
        time.sleep(2.6)
        assert not (bindir / "dictate-toggle.called").exists()
        # The pause has now run past the configured 2s.
        time.sleep(2.5)
        assert (bindir / "dictate-toggle.called").exists()
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


def feed_all(detector, levels):
    """Returns the index of the reading that ends the recording, or None."""
    for i, level in enumerate(levels):
        if detector.feed(level):
            return i
    return None


def test_detector_stops_after_a_quiet_room_a_voice_and_a_pause(watch_mod):
    d = watch_mod.SilenceDetector()
    assert feed_all(d, [20, 20, 4000, 5000, 4500, 20]) == 5


def test_detector_keeps_going_while_the_voice_is_still_there(watch_mod):
    d = watch_mod.SilenceDetector()
    assert feed_all(d, [20, 4000, 5000, 3000, 4500, 3500]) is None


def test_detector_ignores_silence_before_the_speaker_starts(watch_mod):
    d = watch_mod.SilenceDetector()
    assert feed_all(d, [0, 0, 0, 5, 0, 2]) is None


def test_detector_calibrates_to_a_noisy_room(watch_mod):
    """A level that is speech on a quiet mic is only room noise on a loud one."""
    d = watch_mod.SilenceDetector()
    # Floor of 900: 1200 is not four times over it, so it is not a voice.
    assert feed_all(d, [900, 1200, 1100, 950, 1000]) is None
    loud = watch_mod.SilenceDetector()
    assert feed_all(loud, [900, 1200, 6000, 5500, 900]) is not None


def test_detector_survives_someone_who_starts_talking_immediately(watch_mod):
    """No quiet floor is ever recorded, so the threshold must cap to the peak."""
    d = watch_mod.SilenceDetector()
    assert feed_all(d, [5000, 6000, 5500]) is None
    assert d.feed(100)


def test_detector_never_hears_speech_in_a_silent_recording(watch_mod):
    d = watch_mod.SilenceDetector()
    assert feed_all(d, [0] * 10) is None
    assert not d.heard_speech


def test_detector_absolute_override_pins_the_threshold(watch_mod):
    d = watch_mod.SilenceDetector(absolute=350.0)
    # Speech has to clear 700, and silence is anything at or under 350.
    assert feed_all(d, [400, 500, 600]) is None
    assert feed_all(d, [800, 900]) is None
    assert d.feed(300)
