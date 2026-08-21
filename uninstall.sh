#!/usr/bin/env bash
# Remove Whisper Dictation from the current user account.
# Settings, the dictionary, and Whisper models are kept unless --purge is given.
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  echo "uninstall.sh: refuse to run as root" >&2
  exit 1
fi

PURGE=0
case "${1:-}" in
  --purge) PURGE=1 ;;
  -h|--help)
    cat <<'EOF'
uninstall.sh — remove Whisper Dictation from this account

Usage:
  ./uninstall.sh           Remove scripts, launchers, autostart, and units
  ./uninstall.sh --purge   Also remove ~/.config/whisper-dictate

Whisper models in ~/.local/share/whisper.cpp/models are never touched.
Keyboard shortcuts were added by you, so remove those in your desktop settings.
EOF
    exit 0
    ;;
  "") ;;
  *)
    echo "uninstall.sh: unknown option $1" >&2
    exit 1
    ;;
esac

BIN_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"
UNIT_DIR="${HOME}/.config/systemd/user"
AUTOSTART_DIR="${HOME}/.config/autostart"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/whisper-dictate"
STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/whisper-dictate"

# systemctl always talks to the real session, whatever HOME says, so only touch
# the timer when this account is really the one that has the unit installed.
if [[ -f "$UNIT_DIR/dictate-llm-keepalive.timer" ]]; then
  systemctl --user disable --now dictate-llm-keepalive.timer >/dev/null 2>&1 || true
fi

pkill -f "$BIN_DIR/dictate-tray" >/dev/null 2>&1 || true

for name in dictate-common.sh dictate-toggle dictate-watch dictate-tray \
            dictate-polish.py dictate-llm-keepalive rewrite-selection rewrite-text.py; do
  rm -f "$BIN_DIR/$name"
done

rm -f "$APP_DIR/local.dictate-toggle.desktop" \
      "$APP_DIR/local.dictate-tray.desktop" \
      "$APP_DIR/local.rewrite-selection.desktop" \
      "$AUTOSTART_DIR/local.dictate-tray.desktop" \
      "$UNIT_DIR/dictate-llm-keepalive.service" \
      "$UNIT_DIR/dictate-llm-keepalive.timer" \
      "$UNIT_DIR/ydotool.service.d/socket.conf"

rmdir "$UNIT_DIR/ydotool.service.d" 2>/dev/null || true
rm -rf "$STATE_DIR"

systemctl --user daemon-reload >/dev/null 2>&1 || true

if [[ "$PURGE" -eq 1 ]]; then
  rm -rf "$CONFIG_DIR"
  echo "Removed ${CONFIG_DIR}"
else
  echo "Kept settings in ${CONFIG_DIR} (use --purge to remove them)"
fi

echo "Removed Whisper Dictation from ${BIN_DIR}"
echo
echo "Still installed, because this script did not add them:"
echo "  - Whisper models in ~/.local/share/whisper.cpp/models"
echo "  - Packages (whisper-cpp, ydotool, ollama) and the mistral:7b model"
echo "  - Your keyboard shortcuts — remove those in your desktop settings"
if [[ -e /etc/systemd/system/ollama.service.d/keep-alive.conf ]]; then
  echo "  - /etc/systemd/system/ollama.service.d/keep-alive.conf (installed with sudo)"
fi
