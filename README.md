# Whisper Dictation

Offline **speech dictation** for Linux. Hold no cloud account: click the tray microphone (or tap a shortcut), speak, click again, and the transcript is typed into the focused window.

This is dictation (speech-to-text). It is not a desktop “dictator.”

It is built for **PipeWire + Wayland**, with optional **NVIDIA CUDA** via `whisper.cpp` and optional punctuation cleanup via a local **Ollama** model.

## What it does

1. First click (or shortcut press) starts a 16 kHz mono recording with `pw-cat`.
2. Second click stops, runs `whisper-cli`, optionally copy-edits the text with Ollama, then types it with `ydotool`.
3. Notifications stay low-urgency so Plasma does not steal focus from the app you were typing in.
4. A system tray icon can show idle / recording / transcribing, and can cancel a recording.
5. Highlight text and run `rewrite-selection` (bind that script in your desktop) to rewrite it with the same local Mistral model.

A recording never runs forever: it stops on its own after `DICTATE_MAX_SECONDS`
(10 minutes by default), and it can stop when you simply stop talking — see
[Hands-free stop](#hands-free-stop). `dictate-toggle --cancel` throws a recording
away without transcribing or typing anything.

Default model order:

1. `ggml-large-v3-turbo.bin` (recommended)
2. `ggml-large-v3-turbo-q8_0.bin`
3. `ggml-small.en.bin`
4. `ggml-base.en.bin`

## Requirements

| Piece | Why |
| --- | --- |
| PipeWire (`pw-cat`) | Capture the microphone |
| whisper.cpp (`whisper-cli`) | Local speech recognition |
| A ggml Whisper model | The weights `whisper-cli` loads |
| `ydotool` / `ydotoold` | Type into the focused Wayland window |
| `notify-send` | Recording / done toasts |
| Python 3 + `python-gobject` + GTK 3 | Tray icon and LLM polish |
| Ollama + `mistral:7b` | Optional cleanup only |

On KDE Plasma Wayland, clipboard paste (`Ctrl+V`) is unreliable from a global shortcut. This stack types with `ydotool` instead.

Read **[SECURITY.md](SECURITY.md)** before enabling `ydotool` or `/dev/uinput`. That daemon can type into any focused window, including terminals and password fields.

## Install

```bash
gh repo clone Abdullah438/whisper-dictate
cd whisper-dictate
chmod +x install.sh bin/*
./install.sh
```

That copies the scripts to `~/.local/bin`, installs a tray app (autostart), and user systemd units. Bind the scripts yourself in your desktop's shortcut settings.

`install.sh` reports any missing commands before it copies anything, and keeps
going — you can install it before the packages and fix them up afterwards.

### On a new machine

In order, none of which depends on this repo being the same checkout:

1. Install the packages for your distro (below).
2. Download a Whisper model, and the VAD model.
3. `git clone` this repo and run `./install.sh`.
4. Assign shortcuts to the **Whisper Dictation** and **Rewrite Selection**
   entries the installer registers.
5. `systemctl --user enable --now ydotool.service`, and add yourself to the
   group that owns `/dev/uinput`.

Your settings do not travel with the repo — they live in
`~/.config/whisper-dictate/`. Copy `config` and `dictionary` across if you want
the same behaviour, or let `install.sh` seed fresh ones from `contrib/`.

### Packages

**Arch / CachyOS**

```bash
sudo pacman -S --needed whisper-cpp ydotool pipewire python python-gobject gtk3 libnotify
# GPU (optional, if you have NVIDIA):
sudo pacman -S --needed ggml-cuda ggml-cpu
```

**Fedora**

```bash
sudo dnf install whisper-cpp ydotool pipewire python3 python3-gobject gtk3 libnotify
```

**Debian / Ubuntu**

Package names vary. You need `whisper-cli` (or a whisper.cpp build), `ydotool`, PipeWire, Python 3, and `libnotify-bin`. Building [whisper.cpp](https://github.com/ggml-org/whisper.cpp) from source is the portable path if your distro has no package.

### Whisper model

```bash
mkdir -p ~/.local/share/whisper.cpp/models
curl -L --fail --output ~/.local/share/whisper.cpp/models/ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
sha256sum ~/.local/share/whisper.cpp/models/ggml-large-v3-turbo.bin
# expected: 1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69
```

`large-v3-turbo` is about 1.6 GB. Full `ggml-large-v3.bin` (~3.1 GB) is a bit more accurate and a lot slower; turbo is the better default for dictation.

### Voice activity detection (recommended)

Whisper invents text when it is handed near-silence — that is where `Thank you.`
and `[BLANK_AUDIO]` come from. A VAD model trims the silence before decoding:

```bash
curl -L --fail --output ~/.local/share/whisper.cpp/models/ggml-silero-v5.1.2.bin \
  https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin
```

It is picked up automatically once it is in the model directory (about 2 MB).
Set `WHISPER_VAD=0` to ignore it.

### Tray icon

`install.sh` puts **Whisper Dictation** in the system tray and in session autostart.

- **Left-click** the microphone to start recording. The icon turns into a red record mark.
- **Left-click** again to stop, transcribe, and type.
- **Right-click** → Cancel and discard (throw away the current recording), or Quit tray (dictation itself stays installed).
- Start it now with `dictate-tray --daemon &` if you do not want to log out.

The tray uses the desktop StatusNotifier protocol (KDE Plasma, and most other Linux panels).

### Shortcuts

This project does not install keyboard shortcuts. Point your desktop at the scripts:

```bash
~/.local/bin/dictate-toggle       # first press records, second press transcribes
~/.local/bin/rewrite-selection    # rewrite the current text selection
~/.local/bin/dictate-tray         # tray icon; click to toggle if it is already running
```

**KDE Plasma:** `install.sh` already registers **Whisper Dictation** and **Rewrite
Selection** as command shortcuts — they just have no key yet. Go to Settings →
Keyboard → Shortcuts, search for those two names, and assign a chord to each.

Do **not** use *Add New → Command or URL* to point at the same script. That
creates a second entry with the same `Exec`, and you end up with two rows per
script: the one you created and the one the installer registered. Only one of
them can hold the binding, and it is usually not the one you are looking at.
If you already did this, delete the extra `net.local.*.desktop` files from
`~/.local/share/applications` and assign the key to the installed row.

Avoid a chord whose key needs Shift to type, such as `Ctrl+?` (Shift+/).
Plasma stores it without the Shift modifier and it can silently never fire on
Wayland. `Meta+Ctrl+/` and `Meta+Ctrl+\` work well and collide with nothing.
Remember that a global shortcut is swallowed before the focused app sees it, so
`Ctrl+/` would cost you toggle-comment in every editor.

**GNOME:** Settings → Keyboard → Keyboard Shortcuts → Custom Shortcuts.

**Hyprland / Sway:** bind the same paths in `hyprland.conf` or the Sway config.

### Settings

Settings live in `~/.config/whisper-dictate/config`, which `install.sh` seeds
from [`contrib/config.example`](contrib/config.example):

```bash
# ~/.config/whisper-dictate/config
DICTATE_SILENCE_SECONDS=2.5
WHISPER_LANG=en
```

Use that file rather than `~/.bashrc` or `~/.zshrc`. A desktop global shortcut
starts these scripts without your shell environment, so an `export` in a shell
rc file never reaches them. An environment variable of the same name still wins
over the file, which is handy for one-off runs:

```bash
DICTATE_LLM=0 dictate-toggle
```

The file is sourced by bash, so it is ignored if anyone but you can write it.

### Hands-free stop

Pressing the shortcut twice is not always practical. Two limits can end a
recording for you:

```bash
DICTATE_MAX_SECONDS=600      # hard cap, on by default
DICTATE_SILENCE_SECONDS=2.5  # stop after this much silence, off by default
```

What counts as silence is calibrated while you speak, against the quietest and
loudest stretches of that recording. There is no usable fixed number: microphone
gain differs by an order of magnitude between machines, so any constant is
either deaf on a quiet mic or permanently triggered in a noisy room. Silence
also only counts once you have actually started speaking, so a slow start does
not cut the recording short.

Set `DICTATE_SILENCE_LEVEL` to a fixed RMS if the calibration guesses wrong for
you. `dictate-toggle --cancel` (or **Cancel and discard** in the tray) drops a
recording without typing it.

### Personal dictionary

Whisper will keep mishearing the names and jargon you actually use. Put them in
`~/.config/whisper-dictate/dictionary`, one per line:

```
# spoken form = replacement
pipe wire = PipeWire
why do tool = ydotool
kubernetes = Kubernetes
```

The left side is matched whole-word and case-insensitively, and may be several
words; longer entries are applied first. This pass runs last, after the LLM, so
it always wins. Unlike `WHISPER_PROMPT`, it cannot push Whisper into inventing
those words when you did not say them.

### Rewrite selection

Highlight a sentence or paragraph, then run `rewrite-selection`. The script reads the selection, rewrites it with `mistral:7b`, and types the result over the highlight.

Line breaks are typed as **Shift+Enter**, not Enter. In a message box — WhatsApp
Web, Slack, Discord, Telegram, most webmail reply fields — Enter *sends*, so a
two-line rewrite would post half a sentence and type the rest into the next
message. Shift+Enter is the line break those apps expect, and a plain text area
or editor treats it the same as Enter. Set `DICTATE_NEWLINE=enter` if you only
ever type into editors, or `DICTATE_NEWLINE=space` to collapse every rewrite
onto one line.

It reads the Wayland *primary* selection, which highlighting already fills, so
the normal path never touches your clipboard. Apps that do not export a primary
selection fall back to a synthetic `Ctrl+C`; that path empties the clipboard
first, so a copy that never lands cannot type stale clipboard content over your
text. Set `DICTATE_PRIMARY=0` to always use `Ctrl+C`.

Use this for text you already wrote. Dictation cleanup stays a separate, stricter pass.

### ydotool on Wayland

The installer writes `~/.config/systemd/user/ydotool.service.d/socket.conf` so `ydotoold` listens on `$XDG_RUNTIME_DIR/.ydotool_socket`. Enable it:

```bash
systemctl --user enable --now ydotool.service
```

You also need write access to `/dev/uinput` (often the `input` group, or the udev rule shipped with `ydotool`). Log out after a group change. Do not `chmod 666 /dev/uinput`.

### Optional: Ollama polish

Whisper output is usable on its own. Ollama only fixes punctuation, capitalization, and obvious ASR mistakes. It is instructed **not to answer questions** — a dictated question stays a question.

The last four accepted dictations stay in `$XDG_RUNTIME_DIR/whisper-dictate/recent.json` for this login. Polish may use them to resolve names and the current topic. It must still emit only the line you just spoke. Set `DICTATE_CONTEXT=0` to turn that off. This is not fed into Whisper’s `--prompt`.

```bash
# Install Ollama, then:
ollama pull mistral:7b
systemctl --user enable --now dictate-llm-keepalive.timer
```

To skip polish, put this in `~/.config/whisper-dictate/config`:

```bash
DICTATE_LLM=0
```

To keep `mistral:7b` loaded across reboots, copy the optional system drop-in:

```bash
sudo install -m 0755 contrib/ollama/ollama-pin-model /usr/local/bin/ollama-pin-model
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo cp contrib/ollama/keep-alive.conf /etc/systemd/system/ollama.service.d/keep-alive.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

## Usage

- **Click the tray mic** (or your dictation shortcut): recording starts.
- **Speak.**
- **Click again** (or the same shortcut): transcribe, polish (if enabled), type into the focused field.
- **Select text, then your rewrite shortcut:** rewrite that selection in place.

Set `DICTATE_LLM=0` in the config file if you want raw Whisper text with no local LLM. Rewrite still needs Ollama.

## Settings reference

Set these in `~/.config/whisper-dictate/config`, or as environment variables for
a single run.

| Variable | Default | Meaning |
| --- | --- | --- |
| `WHISPER_MODEL` | (auto) | Exact ggml path |
| `WHISPER_MODEL_DIR` | `~/.local/share/whisper.cpp/models` | Search directory |
| `WHISPER_LANG` | `en` | Language, or `auto` |
| `WHISPER_BIN` | `whisper-cli` | Binary name |
| `WHISPER_PROMPT` | (empty) | Initial prompt; do not put brand names here |
| `WHISPER_VAD` | `auto` | Use the VAD model when present; `0` disables |
| `WHISPER_VAD_MODEL` | `$WHISPER_MODEL_DIR/ggml-silero-v5.1.2.bin` | Silero VAD weights |
| `WHISPER_TIMEOUT` | `120` | Seconds before transcription is abandoned |
| `YDOTOOL_SOCKET` | `$XDG_RUNTIME_DIR/.ydotool_socket` | ydotoold socket |
| `DICTATE_LLM` | `1` | `0` skips Ollama |
| `DICTATE_LLM_MODEL` | `mistral:7b` | Cleanup model |
| `DICTATE_LLM_HOST` | `http://127.0.0.1:11434` | Ollama API (localhost only unless `DICTATE_LLM_ALLOW_REMOTE=1`) |
| `DICTATE_CLIPBOARD` | `1` | `0` skips Klipper / `wl-copy` |
| `DICTATE_CONTEXT` | `1` | `0` stops polish from seeing recent dictations |
| `DICTATE_DICTIONARY` | `~/.config/whisper-dictate/dictionary` | Spoken-word replacements |
| `DICTATE_MAX_SECONDS` | `600` | Stop recording after this long; `0` disables |
| `DICTATE_SILENCE_SECONDS` | `0` | Stop after this much silence; `0` disables |
| `DICTATE_SILENCE_LEVEL` | `0` | Fixed silence RMS; `0` calibrates to your mic and voice |
| `DICTATE_KEY_DELAY` | `8` | `ydotool` key delay, in ms |
| `DICTATE_NEWLINE` | `shift-enter` | How a line break is typed: `shift-enter`, `enter`, `space` |
| `DICTATE_INSERT` | `type` | `type` keystroke by keystroke, or `paste` in one keystroke |
| `DICTATE_PASTE_KEY` | `shift+insert` | Paste chord: `shift+insert`, `ctrl+v`, `ctrl+shift+v` |
| `DICTATE_PRIMARY` | `1` | Rewrite reads the primary selection; `0` uses `Ctrl+C` |
| `DICTATE_CONFIG` | `~/.config/whisper-dictate/config` | Settings file |

### Getting the text in faster

Typing is the default because it works everywhere, but it costs
`DICTATE_KEY_DELAY` + `DICTATE_KEY_HOLD` per character — about 16 ms at the
defaults. A 300-character transcript therefore spends roughly **5 seconds**
arriving, every bit of it *after* whisper.cpp and the LLM have already finished.

```bash
DICTATE_INSERT=paste
```

Pasting is one keystroke regardless of length, so the wait disappears.

The chord matters, because no single one is universal. `Ctrl+V` pastes in GUI
apps but is readline's quoted-insert in a terminal. `Ctrl+Shift+V` pastes in
terminals but opens Paste Special in LibreOffice and the Markdown preview in
VS Code. The default is therefore **`Shift+Insert`**: GUI text fields treat it
as paste, and Konsole and Alacritty bind it to paste-*primary*, so the primary
selection is filled alongside the clipboard and the same keystroke covers both.

| `DICTATE_PASTE_KEY` | GUI apps | Terminals |
| --- | --- | --- |
| `shift+insert` (default) | paste | paste (primary) |
| `ctrl+v` | paste | quoted-insert |
| `ctrl+shift+v` | varies — dialogs in some | paste |

Pasting needs `DICTATE_CLIPBOARD=1` (the default), and the transcript passes
through your clipboard; `shift+insert` also replaces your primary selection.
A few password and payment fields refuse paste outright. With the clipboard
switched off it falls back to typing.

If you would rather keep typing, `DICTATE_KEY_DELAY=0` is far quicker than the
default, though some apps drop or reorder characters that arrive with no delay
between them.

## Security

This is local dictation, not a cloud service. It still has real privileges:

- **Keystroke injection.** `ydotool` types into the focused window. Confirm focus before the second press.
- **Microphone.** Recording runs until you press the shortcut again.
- **Clipboard history.** Disable with `DICTATE_CLIPBOARD=0` if you do not want transcripts in Klipper.
- **No root.** The installer and the hotkey refuse to run as root.
- **Local LLM only.** Polish is sent to loopback unless you explicitly allow a remote host.

Details, checksums, and how to report issues: [SECURITY.md](SECURITY.md).

## Layout

```
bin/dictate-common.sh           # settings file loader + lock helper
bin/dictate-toggle              # toggle recording / transcribe
bin/dictate-watch               # time cap and silence auto-stop for a recording
bin/dictate-tray                # system tray (click to toggle)
bin/dictate-polish.py           # copy-edit + dictionary fixes (stdin only)
bin/rewrite-selection           # rewrite highlighted text
bin/rewrite-text.py             # Mistral rewrite (stdin only)
bin/dictate-llm-keepalive       # ping Ollama so the model stays resident
contrib/config.example          # seeds ~/.config/whisper-dictate/config
contrib/dictionary.example      # seeds ~/.config/whisper-dictate/dictionary
contrib/local.dictate-toggle.desktop
contrib/local.dictate-tray.desktop
contrib/local.rewrite-selection.desktop
contrib/systemd/                # user units + ydotool socket drop-in
contrib/ollama/                 # optional system pin for mistral:7b
tests/                          # pytest suite (guardrails, dictionary, locking)
install.sh
uninstall.sh
LICENSE
SECURITY.md
```

## Development

```bash
pip install pytest
pytest tests -q
shellcheck bin/dictate-toggle bin/dictate-common.sh bin/rewrite-selection \
  bin/dictate-llm-keepalive install.sh uninstall.sh
```

The tests cover the parts that fail silently: the polish guardrails that stop
the model from answering your dictation, the dictionary, the WAV level reader
behind the silence stop, and the lock that must not wedge dictation after a
crash. They never contact Ollama — the model reply is canned.

## Uninstall

```bash
./uninstall.sh           # scripts, launchers, autostart, units
./uninstall.sh --purge   # also ~/.config/whisper-dictate
```

Whisper models, packages, and the shortcuts you bound yourself are left alone.

## License

[MIT](LICENSE) for this repository (scripts, units, docs), copyright Abdullah Khan, 2026.

Third-party pieces you install yourself are not covered by that MIT grant:

| Component | Typical license | Notes |
| --- | --- | --- |
| OpenAI Whisper weights (`ggml-*.bin`) | MIT (OpenAI) | Downloaded from Hugging Face / whisper.cpp |
| whisper.cpp | MIT | Distro package or upstream build |
| `ydotool` | AGPL-3.0 | Keystroke injection helper |
| Python 3 + GTK | LGPL | Tray icon (`python-gobject`) |

Do not dictate secrets. See [SECURITY.md](SECURITY.md).
