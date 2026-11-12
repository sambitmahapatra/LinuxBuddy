# linuxbuddy.zsh — a ZLE widget that turns the current command line into a
# LinuxBuddy-generated command.
#
# INSTALL
#   1. pip install -e .            (so the `lb` command is on your PATH)
#   2. Add this line to your ~/.zshrc:
#          source /path/to/linuxbuddy/shell/linuxbuddy.zsh
#   3. Start a new shell (or `source ~/.zshrc`).
#
# USE
#   Type a natural-language request at the prompt, e.g.
#          csv files over 100 megs
#   then press Ctrl-G. The line is REPLACED by the suggested command, with
#   the cursor at the end. Nothing runs — review it, edit if you like, and
#   press Enter yourself.
#
#   Tiered by risk (lb signals risk via its exit code):
#     * read-only command  -> buffer replaced, no fuss.
#     * destructive command -> buffer replaced AND a warning is shown, so you
#       can't miss that it writes/deletes/chmods.
#     * can't tell (abstain) -> your typed line is left untouched and lb's hint
#       appears below the prompt.
#
# The widget runs `lb` only in a command substitution; it never execs the
# result. Because the command lands in YOUR buffer, requests that change shell
# state (`cd`, `export`) work — your own shell runs them when you press Enter.

# Enable the v2 multi-turn session for Ctrl-G calls, keyed on a stable per-
# terminal id (see linuxbuddy.bash for the full why). The widget runs `lb` in a
# $(…) subshell with a different PID each Ctrl-G, so keying on the parent PID
# would never accumulate. `$$` is this interactive shell's PID (fixed for the
# terminal); the nanosecond timestamp makes it unique across terminals. Exported
# once at source time so every `lb` here inherits the SAME id. A direct
# `lb "..."` without the widget stays single-turn.
export LINUXBUDDY_SESSION="lb-$$-$(date +%s%N)"

_linuxbuddy_widget() {
  emulate -L zsh
  setopt localoptions no_aliases

  local request=$BUFFER
  # Nothing but whitespace -> do nothing.
  if [[ -z ${request//[[:space:]]/} ]]; then
    return 0
  fi

  local errfile out ret
  errfile=$(mktemp "${TMPDIR:-/tmp}/linuxbuddy.XXXXXX")
  # Pass the whole buffer as ONE argument; `lb` joins argv itself. We only ever
  # run `lb` — never the command it returns.
  out=$(command lb "$request" 2>"$errfile")
  ret=$?

  case $ret in
    (0)
      # Read-only command: replace the buffer, cursor to end.
      BUFFER=$out
      CURSOR=${#BUFFER}
      ;;
    (3)
      # Destructive command: replace the buffer AND flag it unmissably.
      BUFFER=$out
      CURSOR=${#BUFFER}
      zle -M -- "⚠ destructive — review, then press Enter"
      ;;
    (*)
      # Abstain (exit 1) or error: leave the typed line untouched, show the hint.
      zle -M -- "$(<"$errfile")"
      ;;
  esac

  command rm -f "$errfile"
}

zle -N _linuxbuddy_widget
bindkey '^g' _linuxbuddy_widget
