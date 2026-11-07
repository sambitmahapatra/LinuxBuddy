# Task 17 — domain: wsl_interop (the differentiator)

Read `CLAUDE.md` and the Tier 3 batch rules. This is the final domain and the
one no other tool helps with. Mostly read-only. Several scenarios use nested
command substitution — those are DEFERRED. Many are GUI — buildable but
hand-tested (can't verify headlessly).

## Intents to build (clean, single-level)

### Read-only (work anywhere)

| Intent | Example | Command |
|---|---|---|
| `open_explorer` | "open this folder in Windows Explorer" | `explorer.exe .` (GUI) |
| `goto_cdrive` | "how do I get to my C drive", "take me to the C drive" | `cd /mnt/c` |
| `goto_home` | "back to my linux home" | `cd ~` |
| `path_to_linux` | "convert C:\Users\me into a Ubuntu path" | `wslpath -u -- {winpath}` |
| `path_to_windows` | "how would this Linux path look on Windows" | `wslpath -w -- {path}` |
| `copy_to_clipboard` | "put my current path on the Windows clipboard" | `pwd | clip.exe` (2-stage pipe) |
| `cdrive_space` | "free space on the C drive" | `df -h /mnt/c` |
| `home_space` | "how much space does ubuntu have left" | `df -h ~` |

## Slots

`WINPATH` (a Windows path like `C:\...` — path_to_linux), `PATH` (path_to_windows).

## Deferred — DO NOT build (abstain, document why)

- **Nested `$(...)` navigation** — "take me to my windows downloads/desktop/
  documents", "show where my Windows user folder lives" all use
  `cd $(wslpath $(cmd.exe /C ... ))` or `powershell.exe ...`. The flat-argv +
  round-trip model cannot represent nested command substitution safely.
  Abstain on these. (This is a known V1 limitation — a candidate for V1.1 with
  a dedicated "WSL path resolver" helper.)
- **cp to a Windows folder** (`cp -- file $(wslpath ...)`) — same nested-$()
  problem, plus it's a write. Defer.
- `explorer.exe "$(wslpath ...)"` (open a resolved Windows folder) — nested.
  `explorer.exe .` (open current) is fine and built.

## Verification note

GUI intents (`open_explorer`) and clipboard (`clip.exe`) can't be verified by a
headless script — they open windows / touch the Windows clipboard. **Verify
these BY HAND**, not in an automated run. Do NOT let an automated verification
execute `explorer.exe` (it spawns windows — this caused a cascade before). The
path/space intents (`wslpath`, `df`) ARE script-verifiable.

## Build

- `kb/commands/` for explorer.exe, wslpath, clip.exe, df, cd (all
  `risk_ops: [read]`).
- Capability `wsl_interop` in `kb/taxonomy.yaml`.
- Extend `nlu.py` with a wsl parser — it should fire on WSL/Windows cues
  ("Windows", "C drive", "explorer", "clipboard", "wslpath", a `C:\` path) so
  it doesn't steal generic navigation.

## Tests (`tests/test_wsl_interop.py`)

| input | expect |
|---|---|
| "open this folder in explorer" | open_explorer |
| "take me to the C drive" | goto_cdrive |
| "convert C:\\Users\\me to a linux path" | path_to_linux, winpath=C:\Users\me |
| "how would /home/me/x look on windows" | path_to_windows |
| "put my path on the windows clipboard" | copy_to_clipboard |
| "free space on C drive" | cdrive_space |
| "take me to my windows downloads" | abstain (nested $(), deferred) |

## Done when

`pytest` passes (incl. regression across ALL domains). Script-verify the
path/space intents against the real WSL (`lb free space on C drive` →
`df -h /mnt/c`; `lb convert C:\Users\sambi to a linux path` → `wslpath -u`).
Hand-verify `open_explorer` and `clipboard` yourself (don't automate them).
**This completes all 9 domains — Phase 2 is done.** Update STATUS.md to reflect
the full domain set and that the next step is install + dogfood.
