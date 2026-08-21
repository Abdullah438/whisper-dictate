#!/usr/bin/env bash
# Shared settings loader. Sourced by dictate-toggle and rewrite-selection.
#
# A desktop global shortcut launches these scripts without your shell
# environment, so `export DICTATE_LLM=0` in ~/.zshrc never reaches them.
# Settings therefore live in a config file that the scripts read themselves.
# An explicit environment variable still wins over the file.

DICTATE_CONFIG="${DICTATE_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/whisper-dictate/config}"

DICTATE_SETTINGS=(
  WHISPER_MODEL WHISPER_MODEL_DIR WHISPER_LANG WHISPER_BIN WHISPER_PROMPT
  WHISPER_VAD WHISPER_VAD_MODEL WHISPER_TIMEOUT
  DICTATE_LLM DICTATE_LLM_MODEL DICTATE_LLM_HOST DICTATE_LLM_ALLOW_REMOTE
  DICTATE_CLIPBOARD DICTATE_CONTEXT DICTATE_CONTEXT_FILE DICTATE_DICTIONARY
  DICTATE_MAX_SECONDS DICTATE_SILENCE_SECONDS DICTATE_SILENCE_LEVEL
  DICTATE_KEY_DELAY DICTATE_PASTE_THRESHOLD
  YDOTOOL_SOCKET
)

dictate_load_config() {
  local file="${DICTATE_CONFIG}"
  [[ -f "$file" && -r "$file" ]] || return 0

  # The file is sourced, so it must not be writable by anyone else.
  if [[ ! -O "$file" ]] || [[ -n "$(find "$file" -maxdepth 0 -perm /go+w -print 2>/dev/null)" ]]; then
    echo "whisper-dictate: ignoring $file (not owned by you, or group/world writable)" >&2
    return 0
  fi

  local key
  local -a saved=()
  for key in "${DICTATE_SETTINGS[@]}"; do
    [[ -n "${!key+set}" ]] && saved+=("$key=${!key}")
  done

  # shellcheck disable=SC1090
  source "$file"

  # Anything that was already in the environment overrides the file.
  local pair
  for pair in "${saved[@]}"; do
    printf -v "${pair%%=*}" '%s' "${pair#*=}"
  done
}

# The config file sets plain shell variables. dictate-watch and the Python
# helpers are separate processes that read the environment, so every setting
# has to be exported or the file would only work for the shell scripts.
dictate_export_settings() {
  local key
  for key in "${DICTATE_SETTINGS[@]}"; do
    [[ -n "${!key+set}" ]] && export "${key?}"
  done
  return 0
}

dictate_load_config
dictate_export_settings

# Lock helper shared by dictation and rewrite.
#
# mkdir is atomic and, unlike an flock fd, cannot be inherited by a child such
# as pw-cat. The PID inside lets a later press tell "another run is working"
# apart from "the previous run died and left the directory behind" — without
# that check, one crash makes every following press report Busy until logout.
dictate_lock_age() {
  local now started
  now="$(date +%s)"
  started="$(stat -c %Y "$1" 2>/dev/null || echo "$now")"
  echo $(( now - started ))
}

dictate_acquire_lock() {
  local dir="$1"
  if mkdir "$dir" 2>/dev/null; then
    echo $$ >"$dir/pid"
    return 0
  fi

  local owner=""
  owner="$(cat "$dir/pid" 2>/dev/null || true)"
  if [[ -n "$owner" ]] && kill -0 "$owner" 2>/dev/null; then
    return 1
  fi
  if [[ -z "$owner" ]] && [[ "$(dictate_lock_age "$dir")" -lt 10 ]]; then
    # Another run is between mkdir and writing its PID.
    return 1
  fi

  rm -rf "$dir"
  if mkdir "$dir" 2>/dev/null; then
    echo $$ >"$dir/pid"
    return 0
  fi
  return 1
}
