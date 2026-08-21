#!/usr/bin/env bash
# Install Whisper Dictation into the current user account.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"
MODEL_DIR="${WHISPER_MODEL_DIR:-${HOME}/.local/share/whisper.cpp/models}"
UNIT_DIR="${HOME}/.config/systemd/user"
YDOTOOL_DROPIN="${UNIT_DIR}/ydotool.service.d"
DESKTOP_ID="local.dictate-toggle.desktop"

mkdir -p "$BIN_DIR" "$APP_DIR" "$MODEL_DIR" "$UNIT_DIR" "$YDOTOOL_DROPIN"

install -m 0755 "$ROOT/bin/dictate-toggle" "$BIN_DIR/dictate-toggle"
install -m 0755 "$ROOT/bin/dictate-llm-keepalive" "$BIN_DIR/dictate-llm-keepalive"

sed "s|^Exec=.*|Exec=${BIN_DIR}/dictate-toggle|" \
  "$ROOT/contrib/local.dictate-toggle.desktop" >"$APP_DIR/$DESKTOP_ID"

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
echo "Installed launcher to ${APP_DIR}/${DESKTOP_ID}"
echo
echo "Next:"
echo "  1. Install whisper.cpp (whisper-cli), PipeWire pw-cat, ydotool, and notify-send."
echo "  2. Download a ggml model into ${MODEL_DIR}"
echo "     Recommended: ggml-large-v3-turbo.bin"
echo "  3. Bind a global shortcut to ${DESKTOP_ID} (KDE: Meta+Alt+D works well)."
echo "  4. Optional LLM polish: install Ollama, pull mistral:7b, then:"
echo "       systemctl --user enable --now dictate-llm-keepalive.timer"
echo
echo "See README.md for distro packages and model download commands."
