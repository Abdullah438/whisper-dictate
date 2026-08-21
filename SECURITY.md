# Security

This tool hears your microphone, transcribes speech on this machine, and then **types into whichever window is focused**. Treat it like a keyboard you do not fully control.

## Trust model

- **Offline by default.** Audio and text stay on the local computer. Whisper runs via `whisper-cli`. Optional polish talks only to `127.0.0.1:11434` unless you override that.
- **Your user account.** `install.sh`, `dictate-toggle`, `dictate-tray`, and `rewrite-selection` refuse to run as root. Runtime files go in `$XDG_RUNTIME_DIR/whisper-dictate` with mode `700`.
- **No network downloads at runtime.** Model files are fetched by you, separately. Verify the checksum before first use.

## What this software can do

| Capability | Risk |
| --- | --- |
| Microphone via PipeWire | The tray click or hotkey can record you while it is armed |
| `ydotool` / `/dev/uinput` | Full keystroke injection into the focused app, including terminals and password fields |
| Clipboard (`wl-copy`, Klipper) | Transcripts land in clipboard history unless you set `DICTATE_CLIPBOARD=0` |
| Rewrite selection | Sends highlighted text to local Ollama, then types over it |

Do **not** grant world-writable access to `$XDG_RUNTIME_DIR/.ydotool_socket`. Anyone who can write to that socket can type as you.

## What we do not do

- Dictated text is not passed on process command lines (`ps` / audit logs).
- Success notifications do not include the transcript.
- Ollama polish is copy-edit only. If the model answers a question anyway, that output is discarded and the Whisper transcript is used.
- HTTP redirects from a local Ollama URL to another host are not followed.

## Practical rules

1. Look at the focused window before the second shortcut press. The next keys go there.
2. Do not dictate or rewrite passwords, recovery phrases, or secrets. Clipboard managers and `paste.txt` can retain them until the next run.
3. Leave `DICTATE_LLM_HOST` on loopback. If you must use a remote Ollama, set `DICTATE_LLM_ALLOW_REMOTE=1` and assume that host can read every utterance.
4. Prefer distro packages for `whisper-cli` and `ydotool`. If you download `ggml-large-v3-turbo.bin`, check:

   ```
   sha256sum ggml-large-v3-turbo.bin
   # expected: 1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69
   ```

5. `/dev/uinput` access is powerful. Use the vendor udev rule or the `input` group; do not `chmod 666 /dev/uinput`.

## Reporting issues

Open a GitHub issue on this repository. Do not attach recordings, transcripts, or `paste.log` if they may contain private speech.
