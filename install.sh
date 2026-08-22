#!/usr/bin/env bash
# Install Whisper Dictation into the current user account.
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  echo "install.sh: refuse to run as root; install as your desktop user" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Report what is missing before the user discovers it as silence.
#
# Most of these fail quietly at runtime: without notify-send every message
# disappears, and without wl-copy DICTATE_INSERT=paste has nothing to paste.
# This is a warning, not a gate — you may be installing before the packages.
check_dependencies() {
  local -a missing=()
  local cmd note

  while read -r cmd note; do
    [[ -n "$cmd" ]] || continue
    if ! command -v "$cmd" >/dev/null 2>&1; then
      missing+=("$(printf '%-14s %s' "$cmd" "$note")")
    fi
  done <<'DEPS'
pw-cat records the microphone; dictation captures nothing without it
whisper-cli transcribes; dictation cannot run at all without it
ydotool types the transcript into the focused window
python3 runs the polish, tray, and silence watchdog
notify-send every notification is silently dropped without it
wl-copy DICTATE_INSERT=paste has nothing to paste without it
DEPS

  if [[ "${#missing[@]}" -gt 0 ]]; then
    echo "Missing commands:" >&2
    printf '  %s\n' "${missing[@]}" >&2
    echo >&2
    echo "  See README.md for your distro's package names." >&2
    echo >&2
  fi
}

check_dependencies

BIN_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"
MODEL_DIR="${WHISPER_MODEL_DIR:-${HOME}/.local/share/whisper.cpp/models}"
UNIT_DIR="${HOME}/.config/systemd/user"
YDOTOOL_DROPIN="${UNIT_DIR}/ydotool.service.d"
DESKTOP_ID="local.dictate-toggle.desktop"
TRAY_DESKTOP_ID="local.dictate-tray.desktop"
CANCEL_DESKTOP_ID="local.dictate-cancel.desktop"
AUTOSTART_DIR="${HOME}/.config/autostart"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/whisper-dictate"

mkdir -p "$BIN_DIR" "$APP_DIR" "$MODEL_DIR" "$UNIT_DIR" "$YDOTOOL_DROPIN" \
  "$AUTOSTART_DIR" "$CONFIG_DIR"

install -m 0644 "$ROOT/bin/dictate-common.sh" "$BIN_DIR/dictate-common.sh"
install -m 0755 "$ROOT/bin/dictate-toggle" "$BIN_DIR/dictate-toggle"
install -m 0755 "$ROOT/bin/dictate-watch" "$BIN_DIR/dictate-watch"
install -m 0755 "$ROOT/bin/dictate-llm-keepalive" "$BIN_DIR/dictate-llm-keepalive"
install -m 0755 "$ROOT/bin/dictate-polish.py" "$BIN_DIR/dictate-polish.py"
install -m 0755 "$ROOT/bin/dictate-tray" "$BIN_DIR/dictate-tray"

# Never overwrite settings the user has already edited.
for sample in config dictionary; do
  if [[ ! -e "$CONFIG_DIR/$sample" ]]; then
    install -m 0600 "$ROOT/contrib/${sample}.example" "$CONFIG_DIR/$sample"
  fi
done

sed "s|^Exec=.*|Exec=${BIN_DIR}/dictate-toggle|" \
  "$ROOT/contrib/local.dictate-toggle.desktop" >"$APP_DIR/$DESKTOP_ID"
sed "s|^Exec=.*|Exec=${BIN_DIR}/dictate-tray --daemon|" \
  "$ROOT/contrib/local.dictate-tray.desktop" >"$APP_DIR/$TRAY_DESKTOP_ID"
sed "s|^Exec=.*|Exec=${BIN_DIR}/dictate-toggle --cancel|" \
  "$ROOT/contrib/local.dictate-cancel.desktop" >"$APP_DIR/$CANCEL_DESKTOP_ID"
cp "$APP_DIR/$TRAY_DESKTOP_ID" "$AUTOSTART_DIR/$TRAY_DESKTOP_ID"

install -m 0644 "$ROOT/contrib/systemd/dictate-llm-keepalive.service" \
  "$UNIT_DIR/dictate-llm-keepalive.service"
install -m 0644 "$ROOT/contrib/systemd/dictate-llm-keepalive.timer" \
  "$UNIT_DIR/dictate-llm-keepalive.timer"
install -m 0644 "$ROOT/contrib/systemd/ydotool.socket.conf" \
  "$YDOTOOL_DROPIN/socket.conf"

if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 >/dev/null 2>&1 || true
elif command -v kbuildsycoca5 >/dev/null 2>&1; then
  kbuildsycoca5 >/dev/null 2>&1 || true
fi

systemctl --user daemon-reload >/dev/null 2>&1 || true

if systemctl --user cat ydotool.service >/dev/null 2>&1; then
  systemctl --user enable --now ydotool.service >/dev/null 2>&1 || true
fi

echo "Installed scripts to ${BIN_DIR}"
echo "Installed dictation launcher to ${APP_DIR}/${DESKTOP_ID}"
echo "Installed cancel launcher to ${APP_DIR}/${CANCEL_DESKTOP_ID}"
echo "Installed tray icon (autostarts on login) to ${AUTOSTART_DIR}/${TRAY_DESKTOP_ID}"
echo "Settings and dictionary live in ${CONFIG_DIR}"
echo
echo "Bind these in your desktop's custom shortcuts:"
echo "  Dictation:  ${BIN_DIR}/dictate-toggle"
echo "  Cancel:     ${BIN_DIR}/dictate-toggle --cancel"
echo
echo "Next:"
echo "  1. Install whisper.cpp (whisper-cli), PipeWire pw-cat, ydotool, notify-send,"
echo "     python-gobject, and gtk3."
echo "  2. Download a ggml model into ${MODEL_DIR}"
echo "     Recommended: ggml-large-v3-turbo.bin"
echo "  3. Optional LLM: install Ollama, pull mistral:7b, then:"
echo "       systemctl --user enable --now dictate-llm-keepalive.timer"
echo
echo "See README.md for distro packages and model download commands."
