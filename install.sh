#!/usr/bin/env bash
# Install Whisper Dictation into the current user account.
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  echo "install.sh: refuse to run as root; install as your desktop user" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"
MODEL_DIR="${WHISPER_MODEL_DIR:-${HOME}/.local/share/whisper.cpp/models}"
UNIT_DIR="${HOME}/.config/systemd/user"
YDOTOOL_DROPIN="${UNIT_DIR}/ydotool.service.d"
DESKTOP_ID="local.dictate-toggle.desktop"
TRAY_DESKTOP_ID="local.dictate-tray.desktop"
REWRITE_DESKTOP_ID="local.rewrite-selection.desktop"
AUTOSTART_DIR="${HOME}/.config/autostart"

mkdir -p "$BIN_DIR" "$APP_DIR" "$MODEL_DIR" "$UNIT_DIR" "$YDOTOOL_DROPIN" "$AUTOSTART_DIR"

install -m 0755 "$ROOT/bin/dictate-toggle" "$BIN_DIR/dictate-toggle"
install -m 0755 "$ROOT/bin/dictate-llm-keepalive" "$BIN_DIR/dictate-llm-keepalive"
install -m 0755 "$ROOT/bin/dictate-polish.py" "$BIN_DIR/dictate-polish.py"
install -m 0755 "$ROOT/bin/dictate-tray" "$BIN_DIR/dictate-tray"
install -m 0755 "$ROOT/bin/rewrite-selection" "$BIN_DIR/rewrite-selection"
install -m 0755 "$ROOT/bin/rewrite-text.py" "$BIN_DIR/rewrite-text.py"

sed "s|^Exec=.*|Exec=${BIN_DIR}/dictate-toggle|" \
  "$ROOT/contrib/local.dictate-toggle.desktop" >"$APP_DIR/$DESKTOP_ID"
sed "s|^Exec=.*|Exec=${BIN_DIR}/dictate-tray --daemon|" \
  "$ROOT/contrib/local.dictate-tray.desktop" >"$APP_DIR/$TRAY_DESKTOP_ID"
sed "s|^Exec=.*|Exec=${BIN_DIR}/rewrite-selection|" \
  "$ROOT/contrib/local.rewrite-selection.desktop" >"$APP_DIR/$REWRITE_DESKTOP_ID"
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
echo "Installed rewrite launcher to ${APP_DIR}/${REWRITE_DESKTOP_ID}"
echo "Installed tray icon (autostarts on login) to ${AUTOSTART_DIR}/${TRAY_DESKTOP_ID}"
echo
echo "Next:"
echo "  1. Install whisper.cpp (whisper-cli), PipeWire pw-cat, ydotool, notify-send,"
echo "     python-gobject, and gtk3."
echo "  2. Download a ggml model into ${MODEL_DIR}"
echo "     Recommended: ggml-large-v3-turbo.bin"
echo "  3. Dictation shortcut: bind ${DESKTOP_ID} (example: Meta+Alt+D)."
echo "  4. Rewrite shortcut: bind ${REWRITE_DESKTOP_ID} (Ctrl+Shift+Y)."
echo "     Select text, then press the shortcut."
echo "  5. Optional LLM: install Ollama, pull mistral:7b, then:"
echo "       systemctl --user enable --now dictate-llm-keepalive.timer"
echo
echo "See README.md for distro packages and model download commands."
