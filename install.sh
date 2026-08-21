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

# KDE: bind shortcuts inside KWin. Application launcher shortcuts go
# inactive after reboot, so Ctrl+? never fires from kglobalshortcutsrc alone.
KWIN_SCRIPT_ID="whisper-dictate-shortcuts"
KWIN_SCRIPT_DST="${HOME}/.local/share/kwin/scripts/${KWIN_SCRIPT_ID}"
if [[ -d "$ROOT/contrib/kwin/${KWIN_SCRIPT_ID}" ]]; then
  mkdir -p "$KWIN_SCRIPT_DST"
  cp -a "$ROOT/contrib/kwin/${KWIN_SCRIPT_ID}/." "$KWIN_SCRIPT_DST/"
  if command -v kwriteconfig6 >/dev/null 2>&1; then
    kwriteconfig6 --file kwinrc --group Plugins --key "${KWIN_SCRIPT_ID}Enabled" true
  fi
  if command -v qdbus6 >/dev/null 2>&1; then
    qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript \
      "$KWIN_SCRIPT_ID" >/dev/null 2>&1 || true
    qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
    qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript \
      "${KWIN_SCRIPT_DST}/contents/code/main.js" "$KWIN_SCRIPT_ID" \
      >/dev/null 2>&1 || true
    qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.start \
      >/dev/null 2>&1 || true
  fi
  # Drop Plasma application-shortcut grabs so KWin owns the chords.
  # Also free Meta+Alt+R if Spectacle bound it to screen recording.
  python3 - <<'PY' >/dev/null 2>&1 || true
from gi.repository import Gio, GLib
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
kga = Gio.DBusProxy.new_sync(bus, 0, None, "org.kde.kglobalaccel", "/kglobalaccel", "org.kde.KGlobalAccel", None)
def clear(comp, act, name, friendly):
    action = [comp, act, name, friendly]
    kga.call_sync("setShortcut", GLib.Variant("(asaiu)", (action, [], 4)), 0, 4000, None)
clear("local.dictate-toggle.desktop", "_launch", "Whisper Dictation", "Whisper Dictation")
clear("local.rewrite-selection.desktop", "_launch", "Rewrite Selection", "Rewrite Selection")
clear("org.kde.spectacle.desktop", "RecordScreen", "Spectacle", "Start/Stop Screen Recording")
PY
fi

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
echo "  3. On KDE, dictation is Ctrl+? (Ctrl+Shift+/) and rewrite is Meta+Alt+R."
echo "     Those are installed as a KWin script so they survive login."
echo "  4. Optional LLM: install Ollama, pull mistral:7b, then:"
echo "       systemctl --user enable --now dictate-llm-keepalive.timer"
echo
echo "See README.md for distro packages and model download commands."
