# Task 35 — Autonomous Adaptive Stress Test

Read `CLAUDE.md`, `STATUS.md`, recent `LOG.md`. Branch `v2-multiturn`.

## What this is

An **autonomous, intelligent stress test** for LinuxBuddy. You are NOT following
a pre-written test list. You are building a system of independent agents that
**think for themselves** — they explore, observe, adapt, and probe weaknesses
like a curious human would.

The philosophy: a human tester doesn't follow a script. They try things, see
what breaks, get suspicious, poke harder at the weak spots, try weird phrasings,
and build increasingly devious scenarios. That's what these agents must do.

---

## The agents

Build this as a Python script (`tests/stress_test.py`) with 5 agent functions
that coordinate through shared state (a results list + the filesystem).

### Agent 1: Environment Builder

**Job:** Create a realistic, rich test playground inside the maze.

But NOT from a hardcoded list. Instead:
- Think about what kinds of files and folders a real user's project would have
- Create files with **tricky properties**: spaces in names, ALL-CAPS, dotfiles,
  deep nesting, symlinks, empty dirs, large files, files with similar names
  (report.csv, report_final.csv, report_backup.csv), mixed extensions
- Create at least 30-40 files across 4+ levels of nesting
- **Document what you created and why** — each file should exist to test
  something specific (but the agent decides WHAT to test, not me)

Location: `testlinuxbuddy/stress/` — do NOT touch existing maze fixtures.
Clean up after the full run.

### Agent 2: Explorer

**Job:** Systematically discover what LinuxBuddy can and cannot do.

This agent works like a new user who's been told "this tool translates English
to shell commands" and is trying to figure out its capabilities and limits.

How it works:
1. Start with broad, natural requests — the kind a real person would type
2. Observe the output (command + exit code)
3. Decide: does this look right? Is the command correct for what was asked?
4. Based on what it learns, form hypotheses about what works and what doesn't
5. Test those hypotheses with targeted follow-ups

**The agent must generate its own requests.** Give it these guidelines:
- Cover every domain it can discover: file finding, text search, navigation,
  file operations (copy/move/delete/rename/mkdir), viewing files, permissions,
  system info, process management, archiving
- Use natural, varied phrasing — not command-like syntax
- Try the same operation multiple ways ("find CSVs", "where are the
  spreadsheets", "list all csv files", "any csvs here?", "show me the csvs")
- Try ambiguous and vague requests ("clean up the temp files", "organize the
  downloads", "what's in here")
- Try things that SHOULD be refused (outside maze, nonsense, off-topic)
- Try multi-word filenames, paths with spaces, dotfiles, ALL-CAPS filenames

**The Explorer reports a structured finding for each test:**
```python
{
    "request": "the natural language input",
    "cwd": "/path/where/run",
    "command": "what lb emitted",
    "exit_code": 3,
    "judgment": "CORRECT" | "WRONG_COMMAND" | "WRONG_EXIT" | "UNEXPECTED" | "CRASH",
    "reasoning": "why this judgment — what did I expect vs what I got",
    "category": "what domain/capability this tests",
    "suspicion": "optional — what this result makes me want to test next"
}
```

Run **at least 60 single-turn tests**, but the agent decides the actual
requests. It should feel like a thorough, curious human exploring the tool.

### Agent 3: Adversary

**Job:** Read the Explorer's results and **attack the weaknesses**.

This agent receives the Explorer's findings and:
1. Identifies every WRONG/UNEXPECTED result
2. Groups them by failure pattern (synonym gap? routing priority? gate leak?
   rendering bug?)
3. For each failure pattern, **designs targeted probes** to map the exact
   boundary — what's the simplest phrasing that fails? What's the closest
   working phrasing? Is this a single-word trigger issue or a structural parse
   failure?
4. Runs those probes
5. Also tries to **break things that passed** — if "delete X" worked, try
   "remove X", "get rid of X", "trash X", "erase X", "nuke X", "throw away X"
   to find where the synonym coverage ends
6. Tries to find **gate leaks** — destructive operations that escape the maze
   check (this is a security test; any leak is critical severity)

Run **at least 30 adversarial probes**, adaptively chosen based on Explorer
findings.

### Agent 4: Session Tester

**Job:** Test multi-turn sessions independently.

This agent knows that LinuxBuddy has a multi-turn session feature (via
`LINUXBUDDY_SESSION` env var) and must verify it works correctly.

It should independently design and run multi-turn chains:
1. The **golden chain** (find → filter → operate) — but with its OWN phrasings,
   not the scripted example from the docs
2. **Refinement chains** — start broad, narrow down ("find files" → "only the
   big ones" → "just the csvs")
3. **Reset verification** — mid-chain reset words clear the frame
4. **Cross-domain chains** — start with find, then try to operate on results
5. **Adversarial chains** — try to confuse the session (switch topics mid-chain,
   use ambiguous pronouns, mix destructive and read ops)

For each chain, verify:
- Turn N+1 KEEPS turn N's filters (the critical accumulation property)
- Reset actually clears the frame
- A new unrelated request starts fresh
- Session isolation (different LINUXBUDDY_SESSION values don't interfere)

Each chain uses a unique `LINUXBUDDY_SESSION` value. Use `lb --frame` between
turns to inspect the session state if needed.

Run **at least 8 multi-turn chains** of 2-4 turns each.

### Agent 5: Judge (final analysis)

**Job:** Read ALL results from Agents 2-4 and produce the definitive report.

This agent does NOT run any tests. It analyzes:
1. **Overall health score** — what % works correctly?
2. **Failure taxonomy** — categorize every failure by root cause:
   - Synonym gap (the rules don't know this phrasing)
   - Routing priority (wrong domain won)
   - Rendering bug (right domain, wrong command)
   - Gate leak (destructive op allowed outside maze) — **CRITICAL**
   - Session bug (multi-turn state not preserved/accumulated)
   - Exit code wrong (right command, wrong risk signal)
3. **Severity ranking** — gate leaks > session bugs > routing > synonyms
4. **The rules ceiling** — explicitly identify which failures are inherent
   limits of the rules-based approach vs actual bugs to fix
5. **Phase-2 signal** — which failures would a learned intent encoder fix?
   This directly feeds the training data for the Phase-2 model.

---

## Output files

### `stress_test_results.csv`
Every test from Agents 2-4, one row per test:
```
id,agent,phase,category,cwd,request,command,exit_code,judgment,reasoning,suspicion
```

### `stress_test_report.md`
The Judge's full report:
```markdown
# LinuxBuddy Stress Test Report
## Executive Summary
[1 paragraph: overall health, critical issues, the rules ceiling]

## Test Coverage
- Total tests run: N
- Passed: N (%)
- By agent: Explorer N/N, Adversary N/N, Session N/N

## Critical Issues (fix before Phase 2)
[gate leaks, session bugs, wrong exit codes — actual bugs]

## The Rules Ceiling (Phase-2 territory)
[synonym gaps, phrasing the rules can't handle — training signal for encoder]
[list every failed phrasing — this becomes the Phase-2 training corpus]

## Multi-Turn Session Health
[per-chain results, accumulation verified?, reset works?]

## Failure Taxonomy
[grouped by root cause, with examples]

## Raw Failure Log
[every WRONG/UNEXPECTED row with full context]
```

---

## Implementation

```python
#!/usr/bin/env python3
"""LinuxBuddy Autonomous Adaptive Stress Test"""

import subprocess, os, csv, json, time, re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List

@dataclass
class TestResult:
    id: int
    agent: str
    category: str
    cwd: str
    request: str
    command: str
    exit_code: int
    judgment: str  # CORRECT, WRONG_COMMAND, WRONG_EXIT, UNEXPECTED, CRASH, REFUSED_OK, ABSTAIN_OK
    reasoning: str
    suspicion: str = ""

class StressTest:
    def __init__(self):
        self.results: List[TestResult] = []
        self.maze_root = os.path.expanduser("~/linuxbuddy/testlinuxbuddy")
        self.stress_dir = os.path.join(self.maze_root, "stress")
        self.counter = 0

    def run_lb(self, request: str, cwd: str, session_id: str = None) -> tuple:
        """Run lb and return (stdout, exit_code)"""
        env = {**os.environ, "LINUXBUDDY_MAZE_ROOT": self.maze_root}
        if session_id:
            env["LINUXBUDDY_SESSION"] = session_id
        else:
            env.pop("LINUXBUDDY_SESSION", None)
        try:
            r = subprocess.run(
                ["lb", request], capture_output=True, text=True,
                env=env, cwd=cwd, timeout=10
            )
            return r.stdout.strip(), r.returncode
        except subprocess.TimeoutExpired:
            return "TIMEOUT", -1
        except Exception as e:
            return f"CRASH: {e}", -2

    # ... agent methods: build_environment, explore, attack, test_sessions, judge
```

The skeleton above is a STARTING POINT. The key requirement is that the
explore(), attack(), and test_sessions() methods **generate their own test
cases intelligently** rather than iterating over a hardcoded list.

For explore(): use your understanding of what a CLI natural-language tool
should handle. Think about what a user would actually type. Vary phrasing
naturally. After each batch of tests, look at what's failing and adjust.

For attack(): read the explorer's results, find patterns in failures, and
design probes that map the failure boundaries precisely.

For test_sessions(): design multi-turn chains that exercise the session
accumulation logic in ways that would catch real bugs (like the PPID bug
from Task 31).

---

## Constraints

- Do NOT modify any LinuxBuddy source code — this is testing only
- Do NOT push — we'll push everything together after review
- Clean up `testlinuxbuddy/stress/` after the run
- Timeout each `lb` call at 10 seconds
- If `lb` crashes, log CRASH and continue
- Commit the script (`tests/stress_test.py`) but NOT the output files
  (results.csv and report.md are ephemeral — deliver them for review but
  don't track them)
- The Explorer and Adversary decide exit-code expectations based on
  understanding the system: reads = 0, destructive = 3, abstain = 1,
  refused = 1. They should reason about this, not look it up.

## The spirit of this task

You are NOT a test runner executing a checklist. You are a team of
intelligent testers who are genuinely curious about where this tool breaks.
Surprise me with what you find. The best outcome is discovering a failure
mode nobody anticipated — that's exactly what the static sweep couldn't do.

## Done when

- `stress_test.py` runs end-to-end
- At least 100 total tests across all agents (Explorer 60+, Adversary 30+,
  Session 8+ chains)
- `stress_test_results.csv` and `stress_test_report.md` delivered for review
- The script is committed on `v2-multiturn` (not pushed)
- Results explicitly separate bugs-to-fix from Phase-2-encoder-territory
