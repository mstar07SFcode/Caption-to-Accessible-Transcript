#!/bin/bash
# ============================================================
#  Shared launcher helpers. Sourced by the numbered .command
#  files; not meant to be double-clicked itself.
#
#  Solves two things the launchers used to assume:
#    1. Where the pipeline code lives. They hardcoded
#       "$DIR/usf-caption-pipeline", a hand-assembled layout that
#       no shipped copy of this project actually has.
#    2. Where the user's caption folders live. They assumed the
#       launcher sat inside the working folder. Now the user is
#       asked once and the answer is remembered.
# ============================================================

LAUNCHER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$LAUNCHER_DIR/.caption_workflow"
WORK_SUBFOLDERS=(Raw_Captions Edited_Captions Archived_Captions VTT_Files HTML_Transcripts)

# ---- Python ------------------------------------------------

# Sets PY. Exits with a readable message if Python 3 is missing.
find_python() {
  PY="$(command -v python3)"
  if [ -z "$PY" ]; then
    echo "ERROR: Python 3 is not installed."
    echo "Install it from https://www.python.org/downloads/ and try again."
    echo
    read -n1 -r -p "Press any key to close..."
    exit 1
  fi
}

# ---- Pipeline location -------------------------------------

# Sets PIPELINE to the directory CONTAINING the importable `pipeline` package,
# so `cd "$PIPELINE" && python3 -m pipeline.batch ...` works.
# Checked in order: the repo layout (launchers/ sits beside pipeline/), a
# pipeline/ beside the launcher, then the old usf-caption-pipeline/ name.
find_pipeline() {
  local candidates=(
    "$LAUNCHER_DIR/.."
    "$LAUNCHER_DIR"
    "$LAUNCHER_DIR/usf-caption-pipeline"
  )
  for c in "${candidates[@]}"; do
    if [ -f "$c/pipeline/batch.py" ]; then
      PIPELINE="$(cd "$c" && pwd)"
      return 0
    fi
  done
  echo "ERROR: cannot find the pipeline code."
  echo "Looked for a 'pipeline' folder in:"
  for c in "${candidates[@]}"; do echo "  $c"; done
  echo
  echo "Keep these launchers inside the project folder, next to 'pipeline'."
  echo
  read -n1 -r -p "Press any key to close..."
  exit 1
}

# ---- Working folder ----------------------------------------

_is_valid_workdir() {
  [ -n "$1" ] && [ -d "$1" ]
}

# Creates the five caption folders if they are missing.
_ensure_subfolders() {
  local wf="$1" made=0
  for d in "${WORK_SUBFOLDERS[@]}"; do
    if [ ! -d "$wf/$d" ]; then
      mkdir -p "$wf/$d" && made=1
    fi
  done
  [ "$made" = "1" ] && echo "Created the caption folders in: $wf"
  return 0
}

_prompt_for_workdir() {
  echo "Where are your caption folders?"
  echo "Drag the folder into this window (or type its path), then press Return."
  echo "It should be the folder that holds Raw_Captions, Edited_Captions, etc."
  echo "A new empty folder is fine — the subfolders will be created."
  echo
  local input
  while true; do
    read -r -p "Folder: " input
    # Strip surrounding quotes and the trailing space Finder adds on drag.
    input="${input%\"}"; input="${input#\"}"
    input="${input%\'}"; input="${input#\'}"
    input="${input%"${input##*[![:space:]]}"}"
    # Expand a leading ~ (read -r does not).
    case "$input" in "~"*) input="$HOME${input#\~}" ;; esac
    if _is_valid_workdir "$input"; then
      WORKDIR="$(cd "$input" && pwd)"
      return 0
    fi
    echo "  That is not a folder I can open. Try again, or press Ctrl-C to quit."
  done
}

# Sets WORKDIR. Reads the remembered path; prompts if missing or stale, and
# remembers the answer next to the launcher.
get_workdir() {
  WORKDIR=""
  if [ -f "$CONFIG_FILE" ]; then
    WORKDIR="$(head -n1 "$CONFIG_FILE")"
    if ! _is_valid_workdir "$WORKDIR"; then
      echo "The remembered caption folder is gone:"
      echo "  $WORKDIR"
      echo
      WORKDIR=""
    fi
  fi

  if [ -z "$WORKDIR" ]; then
    _prompt_for_workdir
    printf '%s\n' "$WORKDIR" > "$CONFIG_FILE"
    echo "Remembered. To change it later, delete this file:"
    echo "  $CONFIG_FILE"
    echo
  else
    echo "Caption folder: $WORKDIR"
    read -r -p "Use this folder? [Y/n] " keep
    case "$keep" in
      n|N|no|NO)
        _prompt_for_workdir
        printf '%s\n' "$WORKDIR" > "$CONFIG_FILE"
        echo "Remembered."
        echo
        ;;
    esac
  fi
  _ensure_subfolders "$WORKDIR"
  echo
}
