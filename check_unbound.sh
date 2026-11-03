#!/usr/bin/env bash
#
# check_unbound.sh — which placeholders in the scenario CSV have no binding?
#
# Lives OUTSIDE testlinuxbuddy/ on purpose: build_maze.sh section 2 wipes
# everything under the maze root except the builder itself.
#
# Usage:
#   ./check_unbound.sh              # unbound placeholders (PID/PORT/GPU_ID expected)
#   ./check_unbound.sh --runtime    # same, after starting the runtime helpers
#   ./check_unbound.sh --paths      # also audit that every bound path exists
#
# Exit status is 0 when the only unbound names are the runtime three, 1 if
# anything else is unbound.

set -uo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CSV="$HERE/data/scenarios/LinuxBuddy_360_WSL2_Terminal_Scenarios.csv"
MAZE="$HERE/testlinuxbuddy"
BINDINGS="$MAZE/bindings.env"

WANT_RUNTIME=0
WANT_PATHS=0
for arg in "$@"; do
  case "$arg" in
    --runtime) WANT_RUNTIME=1 ;;
    --paths)   WANT_PATHS=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

for f in "$CSV" "$BINDINGS"; do
  [ -r "$f" ] || { echo "FATAL: cannot read $f" >&2; exit 2; }
done

# The three values a fixture cannot hold (see bindings.env section 7).
RUNTIME_NAMES=" PID PORT GPU_ID "

# Placeholder names used by the CSV: the parameter_placeholders column plus
# anything $-referenced in the reference_shell_plan, since the two disagree.
# Shell-provided names are not the fixture's job to bind.
names_from_csv() {
  python3 - "$CSV" <<'PY'
import csv, re, sys

SHELL = {
    "PATH", "HOME", "USER", "PWD", "SHELL", "IFS", "RANDOM", "PS1", "OLDPWD",
    "LANG", "TERM", "EDITOR", "UID", "HOSTNAME", "LINENO", "BASH_SOURCE",
    "FUNCNAME", "PIPESTATUS", "SECONDS", "TMPDIR", "_",
}
var = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
seen = set()
with open(sys.argv[1], newline="") as fh:
    for row in csv.DictReader(fh):
        for field in ("parameter_placeholders", "reference_shell_plan"):
            for name in var.findall(row.get(field) or ""):
                # Only SCREAMING_SNAKE names are placeholders; $1, $_, $env:X
                # and lowercase shell locals are not.
                if name.upper() == name and name not in SHELL:
                    seen.add(name)
for name in sorted(seen):
    print(name)
PY
}

mapfile -t NAMES < <(names_from_csv)
[ "${#NAMES[@]}" -gt 0 ] || { echo "FATAL: no placeholders parsed from $CSV" >&2; exit 2; }

# shellcheck disable=SC1090
source "$BINDINGS"
if [ "$WANT_RUNTIME" = 1 ]; then
  # shellcheck disable=SC1090
  source "$MAZE/runtime_setup.sh"
fi

unbound=()
runtime_unbound=()
empty=()
for n in "${NAMES[@]}"; do
  if [ -z "${!n+x}" ]; then
    case "$RUNTIME_NAMES" in
      *" $n "*) runtime_unbound+=("$n") ;;
      *)        unbound+=("$n") ;;
    esac
  elif [ -z "${!n}" ]; then
    empty+=("$n")
  fi
done

echo "placeholders in CSV: ${#NAMES[@]}   bound: $(( ${#NAMES[@]} - ${#unbound[@]} - ${#runtime_unbound[@]} ))"

status=0
if [ "${#unbound[@]}" -gt 0 ]; then
  echo
  echo "UNBOUND (${#unbound[@]}):"
  printf '  %s\n' "${unbound[@]}"
  status=1
fi
if [ "${#empty[@]}" -gt 0 ]; then
  echo
  echo "BOUND BUT EMPTY (${#empty[@]}):"
  printf '  %s\n' "${empty[@]}"
  status=1
fi
if [ "${#runtime_unbound[@]}" -gt 0 ]; then
  echo
  echo "runtime-only, expected to be unset (${#runtime_unbound[@]}):"
  printf '  %s\n' "${runtime_unbound[@]}"
  echo "  -> 'source testlinuxbuddy/runtime_setup.sh' exports these"
fi

# Optional: does every bound path actually exist? Write targets are supposed
# not to, so they are listed separately rather than as failures.
if [ "$WANT_PATHS" = 1 ]; then
  echo
  echo "--- path audit ---"
  missing=()
  for n in "${NAMES[@]}"; do
    [ -n "${!n+x}" ] || continue
    v="${!n}"
    case "$v" in /*) ;; *) continue ;; esac   # only absolute paths
    [ -e "$v" ] || [ -L "$v" ] || missing+=("$n=$v")
  done
  if [ "${#missing[@]}" -eq 0 ]; then
    echo "every absolute bound path exists"
  else
    echo "absent (${#missing[@]}) — expected for write targets:"
    printf '  %s\n' "${missing[@]}"
  fi
fi

exit "$status"
