# linuxbuddy.bash — a Readline widget (bind -x) that turns the current command
# line into a LinuxBuddy-generated command, injected into YOUR shell buffer so
# you review it and press Enter yourself. Nothing runs automatically.
#
# INSTALL
#   1. pip install -e .            (so the `lb` command is on your PATH)
#   2. Add this line to your ~/.bashrc:
#          source /path/to/linuxbuddy/shell/linuxbuddy.bash
#   3. Start a new shell (or `source ~/.bashrc`).
#
# USE
#   Type a natural-language request at the prompt, e.g.
#          csv files over 100 megs
#   then press Ctrl-G. The line is REPLACED by the suggested command, cursor at
#   the end. Review it, edit if you like, press Enter. Nothing runs until you do.
#
#   Tiered by risk (lb signals risk via its exit code):
#     * read-only command  -> buffer replaced, no fuss.
#     * destructive command -> buffer replaced AND a warning line is printed
#       above the prompt, so you can't miss that it writes/deletes/chmods.
#     * can't tell (abstain) -> your typed line is LEFT ALONE and lb's hint is
#       shown below the prompt. You don't lose what you typed.
#
# Because the command lands in YOUR buffer (not a subprocess), requests that
# change shell state — `cd`, `export` — work: your own shell runs them.

_linuxbuddy_widget() {
  local request=$READLINE_LINE

  # Nothing but whitespace -> do nothing, leave the line as-is.
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
    0)
      # Read-only command: replace the buffer, cursor to end.
      READLINE_LINE=$out
      READLINE_POINT=${#READLINE_LINE}
      ;;
    3)
      # Destructive command: warn ABOVE the prompt, then replace the buffer.
      printf '\n# \342\232\240 destructive — review, then press Enter\n' >&2
      READLINE_LINE=$out
      READLINE_POINT=${#READLINE_LINE}
      ;;
    *)
      # Abstain (exit 1) or any error: leave the typed line untouched, show the
      # hint below the prompt. Do NOT clobber what the user wrote.
      printf '\n%s\n' "$(<"$errfile")" >&2
      ;;
  esac

  command rm -f "$errfile"
}

# Bind Ctrl-G to the widget. `bind -x` runs the function with READLINE_LINE /
# READLINE_POINT exposed and writes them back to the live buffer.
bind -x '"\C-g": _linuxbuddy_widget' 2>/dev/null
