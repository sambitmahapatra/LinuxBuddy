# Task 18 — bash widget: buffer injection with tiered confirm

Read `CLAUDE.md`. This is the #1 dogfooding finding: a printed command the user
must somehow run themselves is useless for a Linux-new user (they typed
fragments of it and got "command not found"). The command must land IN their
shell buffer, ready to press Enter. Raw CLI — no GUI, no TUI, just Readline.

A zsh ZLE widget already exists (`shell/linuxbuddy.zsh`). Build the **bash**
equivalent with `bind -x`, and add the tiered-confirm behavior to both.

## Behavior

1. User types a natural-language request at the prompt, presses the bound key
   (keep `Ctrl-G`).
2. The widget calls `lb` with the buffer text.
3. `lb` returns a command and signals its risk (see the lb change below).
4. The widget **replaces the buffer** with the returned command — editable,
   NOT executed. Cursor at end. The user reviews and presses Enter.
5. **Tiered confirm by risk:**
   - **Read-only command** → just replace the buffer. User presses Enter. Done.
   - **Destructive command** → replace the buffer, AND print a visible warning
     line above the prompt first (e.g. `# ⚠ destructive — review, then Enter`).
     The command is in the buffer but the warning is unmissable. (The maze gate
     already blocks destructive outside the maze; this is the in-maze warning.)
   - **Abstain** (lb printed nothing, exit 1) → leave the buffer unchanged and
     show lb's hint below the prompt. Do not clear what the user typed.

## The `lb` change (risk signaling)

The widget needs to know the command's risk. Change `cli.py` to signal it by
**exit code** (keeps stdout = exactly the command, nothing else):

- exit 0 → a read-only command on stdout
- exit 1 → abstain (hint on stderr, nothing on stdout) — unchanged
- exit 3 → a destructive command on stdout (the widget warns)

`cli.py` already has the intent's `risk_ops` available (from the gate wiring).
Map destructive risk_ops (write/delete/privilege) → exit 3, read → exit 0.
Add a test that a destructive request exits 3 and a read exits 0.

## The widgets

- `shell/linuxbuddy.bash` — `bind -x` binding that reads `READLINE_LINE`, calls
  `lb`, sets `READLINE_LINE`/`READLINE_POINT` to the returned command, and
  handles the exit-code tiers above.
- Update `shell/linuxbuddy.zsh` to the same tiered behavior (it currently just
  replaces the buffer; add the destructive warning and the abstain-hint path).
- Each has install instructions as a comment (source from `.bashrc` / `.zshrc`).

## Manual check (the real test — run in a real shell)

In bash, after sourcing the widget, inside the maze:
1. Type `find big csv files`, press Ctrl-G → buffer becomes the find command,
   cursor at end, NOT run. Press Enter → it runs. ✓
2. Type `delete the old logs` (once a destructive intent exists) or any
   destructive request → warning shows, command in buffer, Enter runs it. ✓
3. Type `fix this` → buffer unchanged, hint shown. ✓
4. Confirm `cd`/`export` requests work — the command lands in the buffer and
   the user's own shell runs it (this is why buffer injection, not a subprocess).

## Done when

The bash widget works end-to-end in a real bash session (the four manual checks),
`lb` signals risk by exit code with a test, and the zsh widget has parity.
Report what the buffer showed for a read vs a destructive request. This is the
task that turns "built" into "usable" — verify it by actually using it.
