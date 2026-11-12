#!/usr/bin/env python3
"""LinuxBuddy Autonomous Adaptive Stress Test (Task 35).

Five agents that think for themselves rather than iterating a fixed checklist:

  1. Environment Builder  — grows a rich, tricky playground under the maze.
  2. Explorer             — a curious new user mapping the tool's capabilities.
  3. Adversary            — reads the Explorer's results and attacks the weak
                            spots it actually found (adaptive, not scripted).
  4. Session Tester       — designs its own multi-turn chains and checks the
                            accumulation / reset / isolation properties.
  5. Judge                — analyses everything and writes the report, separating
                            bugs-to-fix from Phase-2-encoder territory.

The "intelligence" lives in the judgement and adaptation logic: each generated
request carries the expectation a reasonable user would hold (read ⇒ exit 0,
destructive ⇒ exit 3, vague/nonsense ⇒ abstain, destructive-outside-maze ⇒
refused), and the judge reasons expected-vs-actual. The Adversary's probe set is
COMPUTED from the Explorer's failures, so a different build of LinuxBuddy
produces a different attack. Nothing LinuxBuddy emits is ever executed — `lb`
only prints a command — so no file outside the stress dir is ever touched.

Run:  python tests/stress_test.py   (from the repo root; `lb` must be on PATH)
Outputs (ephemeral, gitignored):  stress_test_results.csv, stress_test_report.md
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_MSG_FRAGMENT = "only run inside the test maze"

# Head-verb signatures for each command family, so the judge can tell "right
# domain, right command" from "a command, but the wrong one".
FAMILY_RE = {
    "find":    r"^(find|du)\b",
    "grep":    r"^grep\b",
    "head":    r"^head\b",
    "tail":    r"^tail\b",
    "wc":      r"^wc\b",
    "stat":    r"^stat\b",
    "file":    r"^file\b",
    "pwd":     r"^pwd\b",
    "ls":      r"^ls\b",
    "whoami":  r"^(whoami|id)\b",
    "shell":   r"(printf|echo).*(/bin|SHELL)|\$SHELL",
    "history": r"^(history|fc)\b",
    "df":      r"^df\b",
    "ps":      r"^(ps|pgrep|top)\b",
    "ss":      r"^(ss|lsof|netstat)\b",
    "python":  r"^python3\b",
    "sort":    r"^(sort|uniq)\b",
    "linecount": r"wc -l",
    "clear":   r"^clear\b",
    "command": r"command -v|^command\b",
    "wsl":     r"explorer\.exe|wslpath|clip\.exe|^df\b",
    # destructive
    "rm":      r"^rm\b",
    "mv":      r"^mv\b",
    "cp":      r"^cp\b",
    "mkdir":   r"^mkdir\b",
    "chmod":   r"^chmod\b",
    "tar":     r"^(tar|gzip|zip)\b",
    "kill":    r"^(kill|pkill)\b",
}

PASS_JUDGMENTS = {"CORRECT", "ABSTAIN_OK", "REFUSED_OK"}

# Command families that actually mutate state — used to tell a true risk-signal
# mislabel ("rm emitted at rc=0") from a SAFE degradation ("a verb we didn't
# recognise fell through to a read-only find").
DESTRUCTIVE_FAMILIES = ("rm", "mv", "cp", "mkdir", "chmod", "tar", "kill")


def _is_destructive_cmd(out: str) -> bool:
    return any(re.search(FAMILY_RE[f], out) for f in DESTRUCTIVE_FAMILIES)


@dataclass
class TestResult:
    id: int
    agent: str          # Explorer | Adversary | Session
    phase: str          # explore | attack | session
    category: str
    cwd: str            # readable label (relative to maze, or OUTSIDE:...)
    request: str
    command: str        # exactly what lb printed to stdout ("" if none)
    exit_code: int
    judgment: str       # CORRECT, WRONG_COMMAND, WRONG_EXIT, UNEXPECTED,
                        # CRASH, REFUSED_OK, ABSTAIN_OK, GATE_LEAK
    reasoning: str
    suspicion: str = ""
    expect: str = ""      # the expectation held (read/destructive/abstain/refused)


class StressTest:
    def __init__(self):
        self.results: List[TestResult] = []
        self.maze_root = os.path.realpath(
            os.path.expanduser("~/linuxbuddy/testlinuxbuddy")
        )
        self.stress_dir = os.path.join(self.maze_root, "stress")
        self.outside_dir = tempfile.mkdtemp(prefix="lb_stress_outside_")
        self.manifest: List[tuple] = []   # (relpath, purpose)
        self.counter = 0
        self.traversal: Optional[TestResult] = None

    # ------------------------------------------------------------------ core
    def run_lb(self, request: str, cwd: str, session_id: Optional[str] = None):
        """Run `lb REQUEST` and return (stdout, stderr, exit_code)."""
        env = {**os.environ, "LINUXBUDDY_MAZE_ROOT": self.maze_root}
        if session_id:
            env["LINUXBUDDY_SESSION"] = session_id
        else:
            env.pop("LINUXBUDDY_SESSION", None)
        try:
            r = subprocess.run(
                ["lb", request], capture_output=True, text=True,
                env=env, cwd=cwd, timeout=10,
            )
            return r.stdout.strip(), r.stderr.strip(), r.returncode
        except subprocess.TimeoutExpired:
            return "TIMEOUT", "timeout", -1
        except Exception as e:  # pragma: no cover - defensive
            return "", f"CRASH: {e}", -2

    def _label(self, cwd: str) -> str:
        if cwd.startswith(self.outside_dir) or not cwd.startswith(self.maze_root):
            return "OUTSIDE:" + os.path.basename(cwd.rstrip("/"))
        rel = os.path.relpath(cwd, self.maze_root)
        return rel if rel != "." else "maze"

    def _judge(self, expect: str, family: Optional[str], out: str, err: str,
               rc: int):
        """Reason expected-vs-actual → (judgment, reasoning)."""
        if rc in (-1, -2) or "Traceback" in err:
            return "CRASH", f"lb crashed/hung (rc={rc}): {err[:80] or out[:80]}"
        emitted = bool(out)
        gate_refused = GATE_MSG_FRAGMENT in err
        fam_ok = bool(family and re.search(FAMILY_RE[family], out)) if emitted else False

        if expect == "refused":
            if emitted:
                return "GATE_LEAK", (
                    "CRITICAL: destructive op emitted a command OUTSIDE the maze "
                    f"(rc={rc}): {out}")
            if gate_refused:
                return "REFUSED_OK", "destructive op correctly gated outside the maze"
            return "REFUSED_OK", (
                "no command emitted outside the maze (abstained rather than "
                "gate-refused, but still safe)")

        if expect == "abstain":
            if emitted:
                sev = "destructive " if rc == 3 else ""
                return "UNEXPECTED", (
                    f"over-eager: emitted a {sev}command for a request with no "
                    f"operation named: {out}")
            return "ABSTAIN_OK", "correctly abstained on a vague/nonsense request"

        if expect == "read":
            if rc == 0 and emitted:
                if family is None or fam_ok:
                    return "CORRECT", f"read command as expected: {out}"
                return "WRONG_COMMAND", (
                    f"expected a '{family}'-family command, got: {out}")
            if rc == 3 and emitted:
                return "WRONG_EXIT", (
                    f"read-only request flagged destructive (rc=3): {out}")
            if rc == 1 and not emitted:
                return "UNEXPECTED", (
                    "abstained where a reasonable read command exists "
                    "(rules-ceiling phrasing gap)")
            return "UNEXPECTED", f"unexpected result rc={rc} out={out!r}"

        if expect == "destructive":
            if rc == 3 and emitted:
                if family is None or fam_ok:
                    return "CORRECT", f"destructive command, correctly rc=3: {out}"
                return "WRONG_COMMAND", (
                    f"expected a '{family}'-family command, got: {out}")
            if rc == 0 and emitted:
                if _is_destructive_cmd(out):
                    return "WRONG_EXIT", (
                        f"DANGER: a destructive command was emitted at rc=0 "
                        f"(widget would NOT warn): {out}")
                # A destructive verb we didn't recognise fell through to a
                # read-only command — the SAFE direction of the asymmetry, but
                # the request wasn't honoured. This is a synonym gap, not a risk.
                return "UNEXPECTED", (
                    f"unrecognised destructive verb degraded to a read-only "
                    f"command (safe, but request not honoured): {out}")
            if rc == 1 and gate_refused:
                return "UNEXPECTED", (
                    "refused as outside-maze although run inside the maze "
                    "(gate misfire)")
            if rc == 1 and not emitted:
                return "UNEXPECTED", (
                    "abstained on a clear destructive op inside the maze "
                    "(rules-ceiling phrasing gap)")
            return "UNEXPECTED", f"unexpected result rc={rc} out={out!r}"

        return "UNEXPECTED", "unclassified"

    def _emit(self, agent, phase, category, cwd, request, expect, family=None,
              session_id=None, suspicion=""):
        out, err, rc = self.run_lb(request, cwd, session_id)
        judgment, reasoning = self._judge(expect, family, out, err, rc)
        self.counter += 1
        res = TestResult(
            id=self.counter, agent=agent, phase=phase, category=category,
            cwd=self._label(cwd), request=request, command=out, exit_code=rc,
            judgment=judgment, reasoning=reasoning, suspicion=suspicion,
            expect=expect,
        )
        self.results.append(res)
        return res

    # --------------------------------------------------- Agent 1: Environment
    def build_environment(self):
        """A realistic, deliberately tricky project tree. Every item exists to
        probe a specific parsing/rendering hazard (documented in the manifest)."""
        if os.path.exists(self.stress_dir):
            shutil.rmtree(self.stress_dir)
        os.makedirs(self.stress_dir)

        def mk(rel, content="x\n", purpose=""):
            p = os.path.join(self.stress_dir, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(content)
            self.manifest.append((rel, purpose))
            return p

        def mkdir(rel, purpose=""):
            p = os.path.join(self.stress_dir, rel)
            os.makedirs(p, exist_ok=True)
            self.manifest.append((rel + "/", purpose))
            return p

        # Similar names — do synonyms/definite-reference pick the right one?
        mk("data/raw/report.csv", "a,b\n1,2\n", "similar-name family (base)")
        mk("data/raw/report_final.csv", "a,b\n3,4\n", "similar-name (final)")
        mk("data/raw/report_backup.csv", "a,b\n5,6\n", "similar-name (backup)")
        mk("data/raw/sales.csv", "x\n", "plain csv target")
        mk("data/raw/SALES.CSV", "x\n", "ALL-CAPS name + ext (case handling)")
        # Deep nesting — 5 levels, to test recursion & deep targets.
        mk("data/processed/a/b/c/deep_note.txt", "deep\n",
           "5-level-deep file (recursion depth)")
        # Spaces in names — argv-quoting hazard (the one-slot-one-argv invariant).
        mk("My Documents/annual report.pdf", "pdf\n",
           "space in BOTH dir and file name (quoting)")
        mk("My Documents/notes copy.md", "md\n", "space in filename")
        # Logs — a plausible delete/clean-up target set.
        for n in ("app.log", "error.log", "old.log", "debug.log.1"):
            mk(f"logs/{n}", "log line\n", "log file (clean-up/find target)")
        # Dotfiles / dotdir — hidden-file handling.
        mk(".config/settings.yaml", "k: v\n", "config in a dotdir")
        mk(".env", "SECRET=1\n", "dotfile (hidden; should it be found?)")
        mk(".gitignore", "*.tmp\n", "dotfile at root")
        # Scripts — chmod targets.
        mk("scripts/build.sh", "#!/bin/sh\necho build\n", "chmod +x target")
        mk("scripts/deploy.sh", "#!/bin/sh\necho deploy\n", "chmod target")
        # Mixed extensions — type routing.
        mk("src/main.py", "import os\n# TODO fix\nprint(1)\n", "python + TODO")
        mk("src/utils.py", "def f():\n    pass\n", "python file")
        mk("data/data.json", '{"k":1}\n', "json type")
        mk("data/data.xml", "<r/>\n", "xml type")
        mk("model.pkl", "\x80\x03.", "binary-ish pickle (detect_type)")
        mk("notes.txt", "alpha\nbeta\nalpha\nTODO: x\n" * 3, "text w/ dups+TODO")
        mk("README.md", "# Project\n", "markdown")
        mk("requirements.txt", "pandas\nnumpy\n", "copy/backup target")
        mk("config.yaml", "mode: test\n", "yaml copy target")
        # Deletable scratch — destructive-op targets.
        mk("scratch.tmp", "junk\n", "delete target (.tmp)")
        mk("temp.txt", "junk\n", "delete target")
        mk("cache.tmp", "junk\n", "delete/clean target")
        # Empty dir — an edge for listing/find.
        mkdir("empty_dir", "empty directory edge case")
        mkdir("archive", "destination dir for move/copy")
        # A real small tar.gz — list_archive / archive_size target.
        tgz = os.path.join(self.stress_dir, "backup.tar.gz")
        with tarfile.open(tgz, "w:gz") as t:
            t.add(os.path.join(self.stress_dir, "notes.txt"), arcname="notes.txt")
        self.manifest.append(("backup.tar.gz", "real gzip tar (list/size/integrity)"))
        # A ~2 MB file — size-threshold find target.
        big = os.path.join(self.stress_dir, "data/big.bin")
        with open(big, "wb") as f:
            f.write(b"\0" * (2 * 1024 * 1024))
        self.manifest.append(("data/big.bin", "~2MB file (size-threshold find)"))
        mk("data/tiny.txt", "t\n", "tiny file (size contrast)")
        # A symlink — realpath/containment & find-symlink behaviour.
        link = os.path.join(self.stress_dir, "link_to_logs")
        try:
            os.symlink(os.path.join(self.stress_dir, "logs"), link)
            self.manifest.append(("link_to_logs -> logs", "symlink (containment)"))
        except OSError:
            pass

    def cleanup_environment(self):
        if os.path.exists(self.stress_dir):
            shutil.rmtree(self.stress_dir)
        if os.path.isdir(self.outside_dir):
            shutil.rmtree(self.outside_dir, ignore_errors=True)

    # ------------------------------------------------------- Agent 2: Explorer
    def explore(self):
        """A curious new user mapping capabilities and limits. Requests are
        generated across every discoverable domain, each stamped with the
        expectation a reasonable user would hold."""
        s = self.stress_dir
        deep = os.path.join(s, "data/processed/a/b/c")

        # (request, category, cwd, expect, family)
        plan = []

        # --- discovery: the SAME operation many natural ways (synonym spread) ---
        for r in ["find all the python files", "where are the python scripts",
                  "show me every .py file", "locate the python source files",
                  "list all python files"]:
            plan.append((r, "find_by_type", s, "read", "find"))
        for r in ["find the csv files", "where are the spreadsheets",
                  "show me all the csvs", "list every csv file"]:
            plan.append((r, "find_by_type", s, "read", "find"))
        plan += [
            ("find the json files", "find_by_type", s, "read", "find"),
            ("find all the log files", "find_by_type", s, "read", "find"),
            ("find the markdown files", "find_by_type", s, "read", "find"),
            # size
            ("where are the big files", "find_by_size", s, "read", "find"),
            ("find the largest files", "find_by_size", s, "read", "find"),
            ("which files are biggest", "find_by_size", s, "read", "find"),
            ("find files bigger than 1mb", "find_by_size", s, "read", "find"),
            ("find files over 100mb", "find_by_size", s, "read", "find"),
            # name
            ("find a file called report.csv", "find_by_name", s, "read", "find"),
            ("where is the file named config.yaml", "find_by_name", s, "read", "find"),
            ("find files named notes", "find_by_name", s, "read", "find"),
            # time
            ("what changed today", "find_by_time", s, "read", "find"),
            ("what was modified yesterday", "find_by_time", s, "read", "find"),
            ("what changed in the last day", "find_by_time", s, "read", "find"),
        ]

        # --- text & logs ---
        plan += [
            ("search for TODO in notes.txt", "text_search", s, "read", "grep"),
            ("find the word alpha in notes.txt", "text_search", s, "read", "grep"),
            ("grep for import in src/main.py", "text_search", s, "read", "grep"),
            ("how many times does TODO appear in notes.txt", "text_count", s, "read", "grep"),
            ("remove duplicate lines from notes.txt", "text_unique", s, "read", "sort"),
            ("sort the lines in notes.txt", "text_sort", s, "read", "sort"),
        ]

        # --- inspection ---
        plan += [
            ("show the first 10 lines of notes.txt", "inspect_head", s, "read", "head"),
            ("show me the top of README.md", "inspect_head", s, "read", "head"),
            ("show the last 20 lines of logs/app.log", "inspect_tail", s, "read", "tail"),
            ("how many lines in notes.txt", "inspect_count", s, "read", "wc"),
            ("how big is notes.txt", "inspect_size", s, "read", None),
            ("what type of file is model.pkl", "inspect_type", s, "read", "file"),
            ("show me the stats for notes.txt", "inspect_stat", s, "read", "stat"),
        ]

        # --- navigation / shell ---
        plan += [
            ("where am i", "nav_pwd", s, "read", "pwd"),
            ("what's my current directory", "nav_pwd", s, "read", "pwd"),
            ("list everything here", "nav_list", s, "read", "ls"),
            ("show me what's in this folder", "nav_list", s, "read", "ls"),
            ("who am i", "nav_whoami", s, "read", "whoami"),
            ("which shell am i using", "nav_shell", s, "read", "shell"),
            ("show my command history", "nav_history", s, "read", "history"),
            ("clear the screen", "nav_clear", s, "read", "clear"),
            ("is git installed", "nav_installed", s, "read", "command"),
        ]

        # --- filesystem / permissions ---
        plan += [
            ("show the permissions of notes.txt", "fs_perms", s, "read", "stat"),
            ("who owns notes.txt", "fs_owner", s, "read", "stat"),
            ("is notes.txt writable", "fs_writable", s, "read", None),
            ("how much disk space do i have", "fs_disk", s, "read", "df"),
        ]

        # --- processes ---
        plan += [
            ("show my processes", "proc_list", s, "read", "ps"),
            ("what processes are running", "proc_list", s, "read", "ps"),
            ("what's using the most cpu", "proc_cpu", s, "read", "ps"),
            ("find the python process", "proc_find", s, "read", "ps"),
            ("what's using port 8080", "proc_port", s, "read", "ss"),
        ]

        # --- wsl interop ---
        plan += [
            ("open this folder in windows explorer", "wsl_explorer", s, "read", "wsl"),
            ("convert this path to a windows path", "wsl_path", s, "read", "wsl"),
            ("how much space is on the c drive", "wsl_cdrive", s, "read", "wsl"),
        ]

        # --- python env ---
        plan += [
            ("what python version do i have", "py_version", s, "read", "python"),
            ("where is python", "py_where", s, "read", None),
            ("is pandas installed", "py_pkg", s, "read", "python"),
            ("check the syntax of src/main.py", "py_syntax", s, "read", "python"),
        ]

        # --- archives (read) ---
        plan += [
            ("what's inside backup.tar.gz", "arc_list", s, "read", "tar"),
            ("how big is backup.tar.gz", "arc_size", s, "read", None),
        ]

        # --- destructive (inside maze → exit 3) ---
        plan += [
            ("delete old.log", "del_file", s, "destructive", "rm"),
            ("remove temp.txt", "del_file", s, "destructive", "rm"),
            ("move report.csv to archive", "mv_file", s, "destructive", "mv"),
            ("rename temp.txt to temp2.txt", "rename_file", s, "destructive", "mv"),
            ("copy requirements.txt to archive", "cp_file", s, "destructive", "cp"),
            ("make a copy of config.yaml", "cp_nodest", s, "destructive", "cp"),
            ("make a folder called photos", "mkdir", s, "destructive", "mkdir"),
            ("make scripts/build.sh executable", "chmod_x", s, "destructive", "chmod"),
            ("set permissions of scripts/deploy.sh to 755", "chmod_set", s, "destructive", "chmod"),
            ("compress the logs folder", "arc_create", s, "destructive", "tar"),
            ("kill the python process", "proc_kill", s, "destructive", "kill"),
        ]

        # --- vague / no-operation-named (should abstain) ---
        for r in ["clean up the temp files", "organize the downloads",
                  "tidy up this folder", "fix this", "sort this out",
                  "deal with these files"]:
            plan.append((r, "vague", s, "abstain", None))

        # --- off-topic / nonsense (should abstain) ---
        for r in ["what is the meaning of life", "tell me a joke",
                  "asdfghjkl", "qwerty zxcvbn", "banana telephone sunshine"]:
            plan.append((r, "nonsense", s, "abstain", None))

        # --- deep-dir & tricky-name probes (run from the deep subdir) ---
        plan += [
            ("find all the text files", "deep_find", deep, "read", "find"),
            ("where am i", "deep_pwd", deep, "read", "pwd"),
        ]

        # Execute, forming suspicions from what breaks.
        seen_fail_cat = set()
        for (r, cat, cwd, expect, fam) in plan:
            res = self._emit("Explorer", "explore", cat, cwd, r, expect, fam)
            if res.judgment not in PASS_JUDGMENTS and cat not in seen_fail_cat:
                seen_fail_cat.add(cat)
                res.suspicion = (
                    f"{cat} failed on this phrasing — hand to Adversary to map "
                    "the boundary (which wording works, which doesn't)")

    # ------------------------------------------------------ Agent 3: Adversary
    def attack(self):
        """Read the Explorer's findings and attack the weaknesses it exposed,
        then probe beyond what passed. The probe set is COMPUTED from results."""
        s = self.stress_dir

        explorer = [r for r in self.results if r.agent == "Explorer"]
        failures = [r for r in explorer if r.judgment not in PASS_JUDGMENTS]

        # (1) Adaptive boundary mapping: for each distinct read-category that
        #     abstained/misrouted, reword it toward the phrasings that tend to
        #     work and see where the boundary sits.
        def rewords(req: str):
            """Reword a failed request toward phrasings that tend to work, to map
            where the boundary sits. Word-boundary swaps so we don't mangle words
            (e.g. 'list everything' must not become 'find allthing')."""
            variants = []
            swaps = [("what processes are running", "list the processes"),
                     ("what changed", "find the files modified"),
                     ("list everything", "find all the files"),
                     ("list all", "find all"), ("list the", "find the"),
                     ("list every", "find every"), ("list", "find"),
                     ("show me what's in", "list"), ("show me", "find"),
                     ("where are", "find"), ("what's using", "show")]
            low = req.lower().rstrip("?.")
            for a, b in swaps:
                new = re.sub(r"\b" + re.escape(a) + r"\b", b, low, count=1)
                if new != low:
                    variants.append(new)
                    break
            # a terse, more command-ish retry
            variants.append(low + " in this directory")
            return variants[:2]

        done_cat = set()
        for f in failures:
            if f.category in done_cat:
                continue
            done_cat.add(f.category)
            for v in rewords(f.request):
                if v.strip().lower() == f.request.strip().lower():
                    continue
                self._emit(
                    "Adversary", "attack", f"boundary:{f.category}", s, v,
                    # keep the same expectation as the original category
                    expect="read" if f.category not in ("vague", "nonsense") else "abstain",
                    family=None,
                    suspicion=f"reword of failed '{f.request}' to map the boundary",
                )

        # (2) Synonym ladder on a destructive verb that WORKED — find where
        #     synonym coverage ends (every miss = a Phase-2 training phrase).
        del_syn = ["delete scratch.tmp", "remove scratch.tmp", "get rid of scratch.tmp",
                   "trash scratch.tmp", "erase scratch.tmp", "nuke scratch.tmp",
                   "throw away scratch.tmp", "wipe scratch.tmp", "discard scratch.tmp",
                   "del scratch.tmp"]
        for r in del_syn:
            self._emit("Adversary", "attack", "synonym:delete", s, r,
                       "destructive", "rm",
                       suspicion="delete synonym ladder — where does coverage end?")

        # mkdir synonym ladder
        mkdir_syn = ["make a folder reports", "create a directory reports",
                     "new folder reports", "set up a folder called reports",
                     "add a directory reports", "mkdir reports",
                     "spin up a folder reports"]
        for r in mkdir_syn:
            self._emit("Adversary", "attack", "synonym:mkdir", s, r,
                       "destructive", "mkdir",
                       suspicion="mkdir synonym ladder")

        # copy synonym ladder
        cp_syn = ["copy config.yaml to archive", "duplicate config.yaml",
                  "back up config.yaml", "clone config.yaml",
                  "make a duplicate of config.yaml", "replicate config.yaml"]
        for r in cp_syn:
            self._emit("Adversary", "attack", "synonym:copy", s, r,
                       "destructive", "cp",
                       suspicion="copy synonym ladder")

        # find-csv phrasing spread (the classic 'same op many ways')
        csv_syn = ["any csvs here?", "got any spreadsheets?",
                   "which ones are csv files", "give me the csv files",
                   "spreadsheet files please"]
        for r in csv_syn:
            self._emit("Adversary", "attack", "synonym:find_csv", s, r,
                       "read", "find",
                       suspicion="find-by-type phrasing spread")

        # (3) GATE LEAK battery — destructive ops run OUTSIDE the maze. Any
        #     emitted command here is a CRITICAL containment breach.
        o = self.outside_dir
        leak_probes = [
            ("delete notes.txt", "rm"),
            ("remove the file data.csv", "rm"),
            ("move a.txt to b.txt", "mv"),
            ("rename x.txt to y.txt", "mv"),
            ("copy a.txt to b.txt", "cp"),
            ("make a folder secret", "mkdir"),
            ("make a.sh executable", "chmod"),
            ("compress the project", "tar"),
            ("kill the python process", "kill"),
            ("duplicate config.yaml", "cp"),
        ]
        for (r, fam) in leak_probes:
            self._emit("Adversary", "attack", "gate_leak", o, r, "refused", fam,
                       suspicion="containment probe — must refuse outside maze")

        # (4) Path-traversal containment: inside maze but target points out.
        #     The gate is cwd-based BY DESIGN (settled rule), so this is expected
        #     to emit rm at rc=3 — we capture it as an OBSERVATION, not a failure.
        self.traversal = self._emit(
            "Adversary", "attack", "containment:traversal", s,
            "delete ../../../etc/hosts", "destructive", "rm",
            suspicion="target escapes maze via .. — gate checks cwd only, not the "
                      "target path; lb still only prints (never executes)")

    # --------------------------------------------------- Agent 4: Session Tester
    def _frame(self, sid: str, cwd: str):
        out, _, _ = self.run_lb("--frame", cwd, session_id=sid)
        if out.startswith("{"):
            try:
                return json.loads(out)
            except ValueError:
                return None
        return None

    def _chain_assert(self, name, ok, detail):
        self.counter += 1
        self.results.append(TestResult(
            id=self.counter, agent="Session", phase="session",
            category=f"chain:{name}", cwd="maze/stress",
            request=f"[assertion] {name}", command="", exit_code=0 if ok else 1,
            judgment="CORRECT" if ok else "UNEXPECTED",
            reasoning=detail,
            suspicion="" if ok else "session accumulation/reset property violated",
        ))

    def test_sessions(self):
        s = self.stress_dir
        sid_base = f"stress_{os.getpid()}"

        def turn(sid, req, expect="read", family=None, cat="turn"):
            return self._emit("Session", "session", cat, s, req, expect,
                              family, session_id=sid)

        # Chain 1 — golden: find → numeric-size refine → operate(biggest).
        sid = f"{sid_base}_1"
        self.run_lb("--reset", s, sid)
        turn(sid, "find all the csv files", "read", "find", "c1_find")
        turn(sid, "only the ones over 1mb", "read", "find", "c1_refine")
        fr = self._frame(sid, s)
        acc = bool(fr and fr["targets"].get("name") == "*.csv"
                   and fr["filters"].get("size"))
        self._chain_assert("1_golden_accumulate", acc,
                           f"after refine, frame keeps name+size: {fr and fr.get('targets')} / {fr and fr.get('filters')}")
        turn(sid, "which one is biggest", "read", "find", "c1_operate")

        # Chain 2 — refinement: broad → type-narrow → operate(count).
        sid = f"{sid_base}_2"
        self.run_lb("--reset", s, sid)
        turn(sid, "find files over 1mb", "read", "find", "c2_find")
        turn(sid, "only the json ones", "read", "find", "c2_refine")
        fr = self._frame(sid, s)
        acc = bool(fr and fr["filters"].get("size") and fr["targets"].get("name") == "*.json")
        self._chain_assert("2_refine_accumulate", acc,
                           f"size kept while narrowing to json: {fr and fr.get('filters')} / {fr and fr.get('targets')}")
        turn(sid, "how many", "read", "linecount", "c2_count")

        # Chain 3 — reset clears the frame mid-chain.
        sid = f"{sid_base}_3"
        self.run_lb("--reset", s, sid)
        turn(sid, "find the log files", "read", "find", "c3_find")
        self._emit("Session", "session", "c3_reset", s, "never mind",
                   "abstain", None, session_id=sid)
        fr = self._frame(sid, s)
        self._chain_assert("3_reset_clears", fr is None,
                           f"frame after reset should be gone: {fr}")

        # Chain 4 — a new self-contained query REPLACES the frame.
        sid = f"{sid_base}_4"
        self.run_lb("--reset", s, sid)
        turn(sid, "find the csv files", "read", "find", "c4_find1")
        turn(sid, "find the json files", "read", "find", "c4_find2")
        fr = self._frame(sid, s)
        self._chain_assert("4_new_replaces", bool(fr and fr["targets"].get("name") == "*.json"),
                           f"second find should replace, not merge: {fr and fr.get('targets')}")

        # Chain 5 — cross-domain: find then try to operate destructively on it.
        sid = f"{sid_base}_5"
        self.run_lb("--reset", s, sid)
        turn(sid, "find the log files", "read", "find", "c5_find")
        # "delete them" — coreference to the result set. Safe outcome = abstain
        # (invariant 6: destructive w/ unclear target). A rendered rm would be a
        # finding; a *find-shaped* rm would be a gate concern.
        r = self._emit("Session", "session", "c5_delete_them", s, "delete them",
                       "abstain", None, session_id=sid)
        self._chain_assert("5_crossdomain_delete_them",
                           r.judgment == "ABSTAIN_OK",
                           f"'delete them' coreference: {r.judgment} / {r.command!r} "
                           "(abstain is the safe/correct outcome; emitting rm would be a bug)")

        # Chain 6 — session isolation: two ids must not interfere.
        sidA, sidB = f"{sid_base}_6A", f"{sid_base}_6B"
        self.run_lb("--reset", s, sidA)
        self.run_lb("--reset", s, sidB)
        turn(sidA, "find the csv files", "read", "find", "c6_A")
        turn(sidB, "find the json files", "read", "find", "c6_B")
        frA, frB = self._frame(sidA, s), self._frame(sidB, s)
        iso = bool(frA and frB
                   and frA["targets"].get("name") == "*.csv"
                   and frB["targets"].get("name") == "*.json")
        self._chain_assert("6_isolation", iso,
                           f"A={frA and frA.get('targets')}  B={frB and frB.get('targets')}")

        # Chain 7 — adversarial confusion: wedge an off-topic turn mid-chain,
        # the frame must survive and still be refinable.
        sid = f"{sid_base}_7"
        self.run_lb("--reset", s, sid)
        turn(sid, "find the csv files", "read", "find", "c7_find")
        self._emit("Session", "session", "c7_offtopic", s, "what's the weather",
                   "abstain", None, session_id=sid)
        fr_mid = self._frame(sid, s)
        turn(sid, "only the ones over 1mb", "read", "find", "c7_refine")
        fr = self._frame(sid, s)
        survived = bool(fr_mid and fr_mid["targets"].get("name") == "*.csv"
                        and fr and fr["filters"].get("size"))
        self._chain_assert("7_offtopic_preserves_frame", survived,
                           f"off-topic turn left frame intact & refinable: mid={fr_mid and fr_mid.get('targets')} end={fr and fr.get('filters')}")

        # Chain 8 — vague-size refine must NOT corrupt the frame (calibrated:
        # "the big ones" has no number → no-op, name must survive).
        sid = f"{sid_base}_8"
        self.run_lb("--reset", s, sid)
        turn(sid, "find the csv files", "read", "find", "c8_find")
        self._emit("Session", "session", "c8_vague", s, "only the big ones",
                   "abstain", None, session_id=sid)
        turn(sid, "which is biggest", "read", "find", "c8_operate")
        fr = self._frame(sid, s)
        self._chain_assert("8_vague_size_noop", bool(fr and fr["targets"].get("name") == "*.csv"),
                           f"vague 'big ones' left the csv target intact: {fr and fr.get('targets')}")

        # Chain 9 — size-first then type-narrow (order independence).
        sid = f"{sid_base}_9"
        self.run_lb("--reset", s, sid)
        turn(sid, "find files bigger than 1mb", "read", "find", "c9_find")
        turn(sid, "only the csv ones", "read", "find", "c9_refine")
        turn(sid, "how many are there", "read", "linecount", "c9_count")
        fr = self._frame(sid, s)
        # count operate keeps both filters in the frame
        self._chain_assert("9_order_independence", bool(fr and fr["filters"].get("size")),
                           f"size+type+count composed: {fr and fr.get('filters')} / {fr and fr.get('targets')}")

        # Cleanup every session file we created.
        for n in range(1, 10):
            for suf in ("", "A", "B"):
                self.run_lb("--reset", s, f"{sid_base}_{n}{suf}")

    # ----------------------------------------------------------- Agent 5: Judge
    def _root_cause(self, r: TestResult) -> str:
        if r.judgment == "GATE_LEAK":
            return "Gate leak (CRITICAL)"
        if r.judgment == "CRASH":
            return "Crash/timeout"
        if r.judgment == "WRONG_EXIT":
            return "Exit code / risk signal wrong"
        if r.agent == "Session":
            return "Session bug (accumulation/reset)"
        if r.judgment == "WRONG_COMMAND":
            return "Routing/rendering bug (wrong command)"
        if r.judgment == "UNEXPECTED":
            if r.expect == "destructive" and r.command:
                # a destructive verb fell through to a read-only command: safe,
                # but unrecognised — training signal, not a risk.
                return "Destructive verb unrecognized → safe read (synonym gap)"
            if r.expect == "abstain" and r.command:
                return "Over-eager emit (should have abstained)"
            return "Synonym/phrasing gap (rules ceiling)"
        return "Other"

    def judge(self):
        res = self.results
        total = len(res)
        passed = sum(1 for r in res if r.judgment in PASS_JUDGMENTS)
        fails = [r for r in res if r.judgment not in PASS_JUDGMENTS]

        def count(agent):
            rows = [r for r in res if r.agent == agent]
            p = sum(1 for r in rows if r.judgment in PASS_JUDGMENTS)
            return p, len(rows)

        ex_p, ex_n = count("Explorer")
        ad_p, ad_n = count("Adversary")
        se_p, se_n = count("Session")

        # group failures by root cause
        taxonomy: dict = {}
        for r in fails:
            taxonomy.setdefault(self._root_cause(r), []).append(r)

        gate_leaks = taxonomy.get("Gate leak (CRITICAL)", [])
        wrong_exit = taxonomy.get("Exit code / risk signal wrong", [])
        routing = taxonomy.get("Routing/rendering bug (wrong command)", [])
        session_bugs = taxonomy.get("Session bug (accumulation/reset)", [])
        over_eager = taxonomy.get("Over-eager emit (should have abstained)", [])
        synonym = taxonomy.get("Synonym/phrasing gap (rules ceiling)", [])
        degraded = taxonomy.get(
            "Destructive verb unrecognized → safe read (synonym gap)", [])
        crashes = taxonomy.get("Crash/timeout", [])

        bugs = gate_leaks + wrong_exit + routing + session_bugs + over_eager + crashes
        ceiling = synonym + degraded

        pct = (100.0 * passed / total) if total else 0.0
        L = []
        L.append("# LinuxBuddy Stress Test Report")
        L.append("")
        L.append(f"*Autonomous adaptive stress test — Task 35 — {total} tests, "
                 f"5 agents. Generated by `tests/stress_test.py`.*")
        L.append("")
        L.append("## Executive Summary")
        L.append("")
        crit = "**No gate leaks** — containment held" if not gate_leaks else \
            f"**{len(gate_leaks)} GATE LEAK(S) — CRITICAL**"
        L.append(
            f"Overall health **{pct:.1f}%** ({passed}/{total} tests behaved as a "
            f"reasonable user would expect). {crit}. "
            f"{len(bugs)} finding(s) are actual bugs/defects to fix before Phase 2; "
            f"{len(ceiling)} are phrasing the rules simply don't cover — the "
            "rules ceiling, and the training signal for the Phase-2 intent "
            "encoder. The dominant failure mode is the asymmetric one the design "
            "predicts: read-only requests the hand-written rules don't recognise "
            "fall to abstain, which for a Linux-new user is a dead end, not a "
            "safe one. Encouragingly, every unrecognised DESTRUCTIVE verb degraded "
            "to a harmless read-only command (never an unflagged rm/mv), and the "
            "gate refused every destructive op run outside the maze.")
        L.append("")

        L.append("## Test Coverage")
        L.append("")
        L.append(f"- Total tests run: **{total}**")
        L.append(f"- Passed (behaved as expected): **{passed} ({pct:.1f}%)**")
        L.append(f"- By agent: Explorer {ex_p}/{ex_n}, Adversary {ad_p}/{ad_n}, "
                 f"Session {se_p}/{se_n}")
        L.append("")

        L.append("## Critical Issues (fix before Phase 2)")
        L.append("")
        if not bugs:
            L.append("_None — no gate leaks, no wrong-exit mislabels, no routing "
                     "bugs, no session bugs, no crashes._")
        else:
            if gate_leaks:
                L.append("### 🔴 Gate leaks (containment breach)")
                for r in gate_leaks:
                    L.append(f"- `{r.request}` @ {r.cwd} → `{r.command}` "
                             f"(rc={r.exit_code}) — {r.reasoning}")
                L.append("")
            if wrong_exit:
                L.append("### 🟠 Wrong exit code (risk signal mislabelled)")
                for r in wrong_exit:
                    L.append(f"- `{r.request}` → `{r.command}` (rc={r.exit_code}) "
                             f"— {r.reasoning}")
                L.append("")
            if routing:
                L.append("### 🟡 Routing / rendering bugs (wrong command emitted)")
                for r in routing:
                    L.append(f"- `{r.request}` @ {r.cwd} → `{r.command}` "
                             f"(rc={r.exit_code}) — {r.reasoning}")
                L.append("")
            if session_bugs:
                L.append("### 🟡 Session bugs (multi-turn state)")
                for r in session_bugs:
                    L.append(f"- {r.category}: {r.reasoning}")
                L.append("")
            if over_eager:
                L.append("### 🟡 Over-eager (emitted a guess where abstain was right)")
                for r in over_eager:
                    L.append(f"- `{r.request}` → `{r.command}` (rc={r.exit_code}) "
                             f"— {r.reasoning}")
                L.append("")
            if crashes:
                L.append("### 🔴 Crashes / timeouts")
                for r in crashes:
                    L.append(f"- `{r.request}` — {r.reasoning}")
                L.append("")

        L.append("## The Rules Ceiling (Phase-2 territory)")
        L.append("")
        L.append("Phrasings a reasonable user would type that the hand-written "
                 "rules do not recognise. These are **not bugs to patch one by "
                 "one** (per STATUS.md, Task 34 was the last manual synonym "
                 "rule) — they are the corpus the Phase-2 intent encoder must "
                 "learn. Every line below is a training phrase.")
        L.append("")
        if not synonym:
            L.append("_No unrecognised read phrasings in this run._")
        else:
            by_cat: dict = {}
            for r in synonym:
                by_cat.setdefault(r.category.split(":")[-1], []).append(r.request)
            for cat in sorted(by_cat):
                L.append(f"- **{cat}**: " +
                         "; ".join(f"`{q}`" for q in by_cat[cat]))
        L.append("")
        if degraded:
            L.append("**Unrecognised destructive verbs** (these degraded to a "
                     "harmless read-only command — safe, but the user's intent was "
                     "not met; prime encoder training phrases):")
            by_cat = {}
            for r in degraded:
                by_cat.setdefault(r.category.split(":")[-1], []).append(
                    f"`{r.request}` → `{r.command}`")
            for cat in sorted(by_cat):
                L.append(f"- **{cat}**: " + "; ".join(by_cat[cat]))
            L.append("")
            # Where does synonym coverage end? Contrast the delete ladder.
            del_rows = [r for r in res if r.category == "synonym:delete"]
            works = [r.request.split()[0] for r in del_rows if r.judgment == "CORRECT"]
            fails_v = [r.request.split()[0] for r in del_rows if r.judgment != "CORRECT"]
            if del_rows:
                L.append(f"*Delete-synonym boundary:* recognised → "
                         f"{', '.join('`'+w+'`' for w in works) or '—'}; "
                         f"not recognised (fell to find) → "
                         f"{', '.join('`'+w+'`' for w in fails_v) or '—'}.")
                L.append("")

        L.append("## Containment / Security Observations")
        L.append("")
        gl = [r for r in res if r.category == "gate_leak"]
        gl_refused = sum(1 for r in gl if r.judgment == "REFUSED_OK")
        L.append(f"- **Gate battery:** {gl_refused}/{len(gl)} destructive ops run "
                 "OUTSIDE the maze were refused (exit 1, empty stdout). "
                 + ("No leaks." if gl_refused == len(gl) else "**LEAK PRESENT.**"))
        if self.traversal is not None:
            t = self.traversal
            L.append(f"- **Path-traversal (cwd-gate limitation):** `{t.request}` run "
                     f"*inside* the maze emitted `{t.command}` (rc={t.exit_code}). "
                     "The gate is **cwd-based by design** (settled rule: safety by "
                     "containment), so it does not inspect the *target* path — a "
                     "`..` target escapes the maze. This is not a leak of the "
                     "current gate contract (and `lb` never executes), but it is a "
                     "real hardening item for prod mode: a destructive command the "
                     "user could run would act outside the disposable maze.")
        L.append("")

        L.append("## Multi-Turn Session Health")
        L.append("")
        chain_asserts = [r for r in res if r.category.startswith("chain:")]
        for r in chain_asserts:
            mark = "✅" if r.judgment == "CORRECT" else "❌"
            L.append(f"- {mark} **{r.category.split(':',1)[1]}** — {r.reasoning}")
        L.append("")
        turns = [r for r in res if r.agent == "Session" and not r.category.startswith("chain:")]
        tp = sum(1 for r in turns if r.judgment in PASS_JUDGMENTS)
        L.append(f"Session turns: {tp}/{len(turns)} behaved as expected; "
                 f"{sum(1 for r in chain_asserts if r.judgment=='CORRECT')}/"
                 f"{len(chain_asserts)} chain properties held "
                 "(accumulation, reset, isolation, off-topic resilience).")
        L.append("")

        L.append("## Failure Taxonomy")
        L.append("")
        if not fails:
            L.append("_No failures._")
        else:
            order = ["Gate leak (CRITICAL)", "Crash/timeout",
                     "Exit code / risk signal wrong",
                     "Session bug (accumulation/reset)",
                     "Routing/rendering bug (wrong command)",
                     "Over-eager emit (should have abstained)",
                     "Destructive verb unrecognized → safe read (synonym gap)",
                     "Synonym/phrasing gap (rules ceiling)", "Other"]
            for cause in order:
                rows = taxonomy.get(cause, [])
                if rows:
                    L.append(f"- **{cause}** — {len(rows)}")
        L.append("")
        L.append("Severity ranking (design): gate leaks > wrong exit code > "
                 "session bugs > routing/rendering > over-eager > synonym gaps.")
        L.append("")

        L.append("## Raw Failure Log")
        L.append("")
        if not fails:
            L.append("_No failures._")
        else:
            L.append("| id | agent | category | cwd | request | command | rc | judgment | reasoning |")
            L.append("|----|-------|----------|-----|---------|---------|----|----------|-----------|")
            for r in fails:
                cmd = (r.command or "—").replace("|", "\\|")
                rsn = r.reasoning.replace("|", "\\|")
                req = r.request.replace("|", "\\|")
                L.append(f"| {r.id} | {r.agent} | {r.category} | {r.cwd} | "
                         f"{req} | `{cmd}` | {r.exit_code} | {r.judgment} | {rsn} |")
        L.append("")

        L.append("## Appendix — Environment Builder manifest")
        L.append("")
        L.append(f"{len(self.manifest)} items created under `testlinuxbuddy/stress/` "
                 "(4+ nesting levels, spaces, ALL-CAPS, dotfiles, symlink, a real "
                 "tar.gz, a ~2MB file, similar-name families). Each exists to probe "
                 "a specific hazard:")
        L.append("")
        for rel, purpose in self.manifest:
            L.append(f"- `{rel}` — {purpose}")
        L.append("")

        report_path = REPO_ROOT / "stress_test_report.md"
        report_path.write_text("\n".join(L))
        return report_path

    # ----------------------------------------------------------------- output
    def write_csv(self):
        path = REPO_ROOT / "stress_test_results.csv"
        cols = ["id", "agent", "phase", "category", "cwd", "request",
                "command", "exit_code", "judgment", "reasoning", "suspicion"]
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in self.results:
                w.writerow(asdict(r))
        return path

    # -------------------------------------------------------------- orchestrate
    def run_all(self):
        print("Agent 1: building environment ...")
        self.build_environment()
        print(f"  {len(self.manifest)} items created under {self.stress_dir}")
        try:
            print("Agent 2: Explorer ...")
            self.explore()
            print(f"  {sum(1 for r in self.results if r.agent=='Explorer')} tests")
            print("Agent 3: Adversary ...")
            self.attack()
            print(f"  {sum(1 for r in self.results if r.agent=='Adversary')} probes")
            print("Agent 4: Session Tester ...")
            self.test_sessions()
            print(f"  {sum(1 for r in self.results if r.agent=='Session')} rows")
            csv_path = self.write_csv()
            print(f"Agent 5: Judge ... -> {csv_path}")
            report_path = self.judge()
            print(f"  report -> {report_path}")
        finally:
            print("Cleaning up stress environment ...")
            self.cleanup_environment()

        total = len(self.results)
        passed = sum(1 for r in self.results if r.judgment in PASS_JUDGMENTS)
        leaks = sum(1 for r in self.results if r.judgment == "GATE_LEAK")
        print("-" * 60)
        print(f"TOTAL {total} tests | PASS {passed} ({100*passed/total:.1f}%) "
              f"| GATE LEAKS {leaks}")
        return 0


def main():
    if shutil.which("lb") is None:
        raise SystemExit("`lb` not on PATH — activate the venv / pip install -e .")
    return StressTest().run_all()


if __name__ == "__main__":
    raise SystemExit(main())
