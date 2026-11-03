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
#   press Enter yourself. If LinuxBuddy can't tell what you mean, the line is
#   left untouched and a short message appears below the prompt.
#
# The widget runs `lb` only in a command substitution; it never execs the
# result and never changes your shell state, so your cwd (and `cd ..`)
# are unaffected.

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
  # Pass the whole buffer as ONE argument; `lb` joins argv itself.
  out=$(command lb "$request" 2>"$errfile")
  ret=$?

  if (( ret == 0 )); then
    # Replace the buffer with the suggested command; leave it for the user.
    BUFFER=$out
    CURSOR=${#BUFFER}
  else
    # Leave the buffer unchanged; show the stderr message below the prompt.
    local msg
    msg=$(<"$errfile")
    zle -M -- "$msg"
  fi

  command rm -f "$errfile"
}

zle -N _linuxbuddy_widget
bindkey '^g' _linuxbuddy_widget
