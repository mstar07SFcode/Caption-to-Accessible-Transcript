#!/bin/bash
# ============================================================
#  Shared helpers for the Caption-to-Accessible-Transcript
#  double-click launchers.
#
#  Sourced by 0_/1_/2_/3_*.command. Not meant to be run alone.
#
#  Responsibilities:
#    - locate the pipeline package (always the repo root)
#    - find Python 3
#    - ask once for the user's working folder, then remember it
#    - create the standard subfolders
# ============================================================

# --- Locate the repo -------------------------------------------------------
# The launchers live in <repo>/launchers, so the pipeline package that
# `python3 -m pipeline.batch` needs is one level up.
LAUNCHER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$LAUNCHER_DIR/.." && pwd)"
PIPELINE="$REPO"
VENV="$REPO/.venv"

CONFIG_DIR="$HOME/.config/caption-to-transcript"
CONFIG_FILE="$CONFIG_DIR/config"

# --- Python ----------------------------------------------------------------

require_python() {
  PY="$(command -v python3)"
  if [ -z "$PY" ]; then
    echo "ERROR: Python 3 is not installed."
    echo "Install it from https://www.python.org/downloads/ and try again."
    echo
    read -n1 -r -p "Press any key to close..."
    exit 1
  fi
}

# --- Working folder --------------------------------------------------------

_save_working_folder() {
  mkdir -p "$CONFIG_DIR"
  printf 'WORKING_FOLDER=%s\n' "$1" > "$CONFIG_FILE"
}

_prompt_for_folder() {
  # Prefer the native macOS folder picker; fall back to typing a path.
  local picked=""
  if command -v osascript >/dev/null 2>&1; then
    picked="$(osascript -e 'try
  POSIX path of (choose folder with prompt "Choose your caption working folder")
end try' 2>/dev/null)"
    picked="${picked%/}"
  fi
  if [ -z "$picked" ]; then
    echo "Type the full path to your working folder (or drag the folder here)," >&2
    echo "then press Return:" >&2
    read -r picked
    # Dragging a folder into Terminal escapes spaces; unescape them.
    picked="${picked//\\ / }"
    picked="${picked%/}"
  fi
  printf '%s' "$picked"
}

# Sets WF to the user's working folder, asking only when it isn't already known.
resolve_working_folder() {
  WF=""
  if [ -f "$CONFIG_FILE" ]; then
    WF="$(sed -n 's/^WORKING_FOLDER=//p' "$CONFIG_FILE" | head -n1)"
  fi

  if [ -n "$WF" ] && [ -d "$WF" ]; then
    echo "Working folder: $WF"
    read -r -p "Use this folder? [Y/n] " KEEP
    case "$KEEP" in
      n|N|no|NO) WF="" ;;
    esac
  elif [ -n "$WF" ]; then
    echo "Saved working folder no longer exists: $WF"
    WF=""
  fi

  while [ -z "$WF" ] || [ ! -d "$WF" ]; do
    echo
    echo "Choose the folder where your caption files live."
    echo "(This is where Raw_Captions, Edited_Captions, HTML_Transcripts etc. go.)"
    WF="$(_prompt_for_folder)"
    if [ -z "$WF" ]; then
      echo "No folder chosen."
      read -r -p "Try again? [Y/n] " AGAIN
      case "$AGAIN" in
        n|N|no|NO)
          echo "Cancelled."
          read -n1 -r -p "Press any key to close..."
          exit 0 ;;
      esac
    elif [ ! -d "$WF" ]; then
      echo "Not a folder: $WF"
      WF=""
    fi
  done

  _save_working_folder "$WF"
  export WF
  echo "Using working folder: $WF"
}

ensure_folders() {
  mkdir -p "$WF/Raw_Captions" "$WF/Edited_Captions" "$WF/Archived_Captions" \
           "$WF/VTT_Files" "$WF/HTML_Transcripts"
}

# --- AI mode ---------------------------------------------------------------

# Sets RUNPY (interpreter to use) and appends API flags to the ARGS array.
# Call as:  choose_ai_mode "description of what AI adds"
choose_ai_mode() {
  local ai_description="$1"
  echo "Mode:"
  echo "  [1] Basic — no AI (fast, free, nothing leaves your Mac)"
  echo "  [2] AI    — $ai_description (needs setup + API key)"
  read -r -p "Choose 1 or 2 [1]: " MODE

  if [ "$MODE" != "2" ]; then
    RUNPY="$PY"
    return
  fi

  if [ ! -x "$VENV/bin/python" ]; then
    echo
    echo "AI mode is not set up yet. Run '0_Setup_AI_Cleanup.command' first."
    echo "Falling back to Basic mode."
    RUNPY="$PY"
    return
  fi

  RUNPY="$VENV/bin/python"
  if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo
    read -rs -p "Paste your Anthropic API key (hidden, used only this run): " ANTHROPIC_API_KEY
    echo
    export ANTHROPIC_API_KEY
  fi
  ARGS+=(--backend api)

  echo
  read -r -p "Use batch mode? Cheaper (~50% less) but can take several minutes [y/N] " BATCH
  case "$BATCH" in
    y|Y|yes|YES)
      ARGS+=(--batch)
      echo "Batch mode on. Submitting all files together; please leave this window open."
      echo "It will give up after 1 hour rather than hang." ;;
    *) echo "Running one request per file..." ;;
  esac
}
