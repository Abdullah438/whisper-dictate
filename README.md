# Whisper Dictation

Offline **speech dictation** for Linux. Hold no cloud account: click the tray microphone (or tap a shortcut), speak, click again, and the transcript is typed into the focused window.

This is dictation (speech-to-text). It is not a desktop “dictator.”

It is built for **PipeWire + Wayland**, with optional **NVIDIA CUDA** via `whisper.cpp` and optional punctuation cleanup via a local **Ollama** model.

## What it does

1. First click (or shortcut press) starts a 16 kHz mono recording with `pw-cat`.
2. Second click stops, runs `whisper-cli`, optionally copy-edits the text with Ollama, then types it with `ydotool`.
3. Notifications stay low-urgency so Plasma does not steal focus from the app you were typing in.
4. A system tray icon can show idle / recording / transcribing.
5. Highlight text and press **Ctrl+Shift+Y** to rewrite it with the same local Mistral model.

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

That copies the scripts to `~/.local/bin`, installs a hidden shortcut launcher, a tray app (autostart), and user systemd units.

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

### Tray icon

`install.sh` puts **Whisper Dictation** in the system tray and in session autostart.

- **Left-click** the microphone to start recording. The icon turns into a red record mark.
- **Left-click** again to stop, transcribe, and type.
- **Right-click** → Quit tray (dictation itself stays installed).
- Start it now with `dictate-tray --daemon &` if you do not want to log out.

The tray uses the desktop StatusNotifier protocol (KDE Plasma, and most other Linux panels).

### Shortcut (optional)

The keyboard shortcut still works if you want it:

1. Settings → Shortcuts → add the hidden launcher `local.dictate-toggle.desktop`.
2. Bind it to **Meta+Alt+D**, or another chord that does not fight your desktop.

GNOME / Hyprland / Sway can bind either:

```bash
~/.local/bin/dictate-toggle    # one-shot toggle
~/.local/bin/dictate-tray      # start tray, or toggle if it is already running
```

### Rewrite selection

Highlight a sentence or paragraph, then press **Ctrl+Shift+Y** (or bind `local.rewrite-selection.desktop` to another Ctrl+Shift chord). The script copies the selection, rewrites it with `mistral:7b`, and types the result over the highlight.

Use this for text you already wrote. Dictation cleanup stays a separate, stricter pass.

Ctrl+Shift+Y is used instead of Ctrl+Shift+R so it does not steal Redo or browser hard-refresh.

### ydotool on Wayland

The installer writes `~/.config/systemd/user/ydotool.service.d/socket.conf` so `ydotoold` listens on `$XDG_RUNTIME_DIR/.ydotool_socket`. Enable it:

```bash
systemctl --user enable --now ydotool.service
```

You also need write access to `/dev/uinput` (often the `input` group, or the udev rule shipped with `ydotool`). Log out after a group change. Do not `chmod 666 /dev/uinput`.

### Optional: Ollama polish

Whisper output is usable on its own. Ollama only fixes punctuation, capitalization, and obvious ASR mistakes. It is instructed **not to answer questions** — a dictated question stays a question.

```bash
# Install Ollama, then:
ollama pull mistral:7b
systemctl --user enable --now dictate-llm-keepalive.timer
```

To skip polish:

```bash
export DICTATE_LLM=0
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

- **Click the tray mic** (or press the dictation shortcut): recording starts.
- **Speak.**
- **Click again:** transcribe, polish (if enabled), type into the focused field.
- **Select text, then Ctrl+Shift+Y:** rewrite that selection in place.

Set `DICTATE_LLM=0` if you want raw Whisper text with no local LLM. Rewrite still needs Ollama.

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `WHISPER_MODEL` | (auto) | Exact ggml path |
| `WHISPER_MODEL_DIR` | `~/.local/share/whisper.cpp/models` | Search directory |
| `WHISPER_LANG` | `en` | Language, or `auto` |
| `WHISPER_BIN` | `whisper-cli` | Binary name |
| `YDOTOOL_SOCKET` | `$XDG_RUNTIME_DIR/.ydotool_socket` | ydotoold socket |
| `DICTATE_LLM` | `1` | `0` skips Ollama |
| `DICTATE_LLM_MODEL` | `mistral:7b` | Cleanup model |
| `DICTATE_LLM_HOST` | `http://127.0.0.1:11434` | Ollama API (localhost only unless `DICTATE_LLM_ALLOW_REMOTE=1`) |
| `DICTATE_CLIPBOARD` | `1` | `0` skips Klipper / `wl-copy` |

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
bin/dictate-toggle              # toggle recording / transcribe
bin/dictate-tray                # system tray (click to toggle)
bin/dictate-polish.py           # copy-edit + proper-noun fixes (stdin only)
bin/rewrite-selection           # rewrite highlighted text
bin/rewrite-text.py             # Mistral rewrite (stdin only)
bin/dictate-llm-keepalive       # ping Ollama so the model stays resident
contrib/local.dictate-toggle.desktop
contrib/local.dictate-tray.desktop
contrib/local.rewrite-selection.desktop
contrib/systemd/                # user units + ydotool socket drop-in
contrib/ollama/                 # optional system pin for mistral:7b
install.sh
LICENSE
SECURITY.md
```

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
