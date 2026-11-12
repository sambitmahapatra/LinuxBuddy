"""The ``lb`` command: natural-language request -> a runnable command string.

Pipeline: nlu.parse -> planner.compile -> render.to_shell.

Contract (so a caller — including the shell widget — can trust stdout AND the
exit code signals risk):
  * read-only command -> print the command to stdout, exit 0.
  * destructive command (write/delete/privilege) -> print the command to
    stdout, exit 3. The widget shows a warning; stdout is still exactly the
    command and nothing else.
  * abstain / failure -> print a short message to stderr, exit 1, and print
    NOTHING to stdout. stdout is therefore always either empty or a single
    runnable command.

Nothing is executed. LinuxBuddy only prints a command for the user to run.
"""
from __future__ import annotations

import os
import sys

from . import gate, hybrid, session, session_resolver
from .nlu import parse, abstain_hint
from .planner import compile, risk_ops, PlanError
from .render import to_shell, RenderError

__all__ = ["main"]

_ABSTAIN_MSG = "LinuxBuddy: not sure what you mean"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    # --- session debug/control flags (work regardless of session mode) ---
    if args == ["--reset"]:
        session.clear(session.store_key())
        print("LinuxBuddy: session cleared")
        return 0
    if args == ["--frame"]:
        fr = session.load(session.store_key())
        print(fr.to_json() if fr is not None
              else "LinuxBuddy: no active session frame")
        return 0

    request = " ".join(args)

    # Multi-turn is OPT-IN via LINUXBUDDY_SESSION (the shell widget exports it).
    # A direct `lb "..."` call — including the 139-scenario sweep — takes the
    # unchanged v1 single-turn path below, so single-turn behaviour never shifts.
    if os.environ.get("LINUXBUDDY_SESSION"):
        return _run_session(request)
    return _run_single_turn(request)


def _run_single_turn(request: str) -> int:
    """The v1 pipeline, unchanged: parse -> compile -> gate -> render. When the
    rules abstain, the OPTIONAL encoder fallback is consulted at this one seam
    (Task 39); if it too declines, we abstain exactly as v1 did."""
    frame = parse(request)
    if frame is None:
        # Rules abstained — the single seam for the encoder fallback. The encoder
        # picks an intent + slots; it runs through the SAME pipeline below.
        enc_frame, info = hybrid.classify_fallback(request)
        if enc_frame is not None:
            return _emit_frame(enc_frame, info)
        # Prefer a specific hint ("how big? try ...") when we can tell which
        # defining slot was missing; otherwise the generic message.
        print(abstain_hint(request) or _ABSTAIN_MSG, file=sys.stderr)
        return 1
    return _emit_frame(frame, None)


def _emit_frame(frame, info) -> int:
    """compile -> gate -> render for a frame, from the rules (info=None) or the
    encoder (info carries source/score). Same exit-code contract either way; a
    compile/render failure or a gate denial abstains (no command on stdout)."""
    try:
        argv_plan = compile(frame)
    except PlanError:
        print(_ABSTAIN_MSG, file=sys.stderr)
        return 1

    # Destructive-containment gate (P2.0): a write/delete/chmod plan may only
    # be emitted when cwd is inside the maze (prototype mode). Checked AFTER
    # compile, BEFORE rendering/printing — so nothing destructive reaches
    # stdout from the wrong place. Encoder-chosen destructives are gated too.
    denied = gate.check(risk_ops(frame.intent), os.getcwd())
    if denied:
        print(denied, file=sys.stderr)
        return 1

    try:
        command = to_shell(argv_plan)
    except RenderError:
        print(_ABSTAIN_MSG, file=sys.stderr)
        return 1

    # Confidence surfacing (Guardrail): when the command came from the encoder
    # rather than the rules, nudge the human to review. Goes to STDERR so stdout
    # stays EXACTLY the command (the widget's buffer contract is unchanged).
    if info and info.get("source") == "encoder":
        if info.get("destructive"):
            print("LinuxBuddy ~ interpreted (language model) — DESTRUCTIVE, "
                  "double-check the target before you run it", file=sys.stderr)
        else:
            print("LinuxBuddy ~ interpreted (language model) — review before running",
                  file=sys.stderr)

    print(command)
    # Exit code signals risk to the shell widget: 3 = destructive (it warns),
    # 0 = read-only. (A denied destructive plan already returned 1 above.)
    return 3 if gate.is_destructive(risk_ops(frame.intent)) else 0


def _emit_plan_frame(plan_frame):
    """Compile a session plan Frame through the v1 safe pipeline (compile ->
    gate -> render). Returns (rc, emitted): emitted is False when compile/render
    could not produce a command (caller then falls back to single-turn), so a
    failed emit never gets persisted as the session frame."""
    try:
        argv_plan = compile(plan_frame)
    except PlanError:
        return 1, False
    denied = gate.check(risk_ops(plan_frame.intent), os.getcwd())
    if denied:
        print(denied, file=sys.stderr)
        return 1, True  # a real (gated) decision — the frame stands
    try:
        command = to_shell(argv_plan)
    except RenderError:
        return 1, False
    print(command)
    rc = 3 if gate.is_destructive(risk_ops(plan_frame.intent)) else 0
    return rc, True


def _run_session(request: str) -> int:
    """Multi-turn path: load the frame, classify the turn, merge/replace, then
    render through the SAME v1 pipeline. Falls back to single-turn whenever the
    turn isn't a usable multi-turn move."""
    key = session.store_key()
    frame = session.load(key)
    return _session_dispatch(request, frame, key)


def _session_dispatch(request: str, frame, key: str) -> int:
    act, delta = session.classify(request, frame)

    if act == "reset":
        session.clear(key)
        remainder = delta.get("remainder")
        if not remainder:
            print("LinuxBuddy: starting over — the next request starts fresh",
                  file=sys.stderr)
            return 1
        return _session_dispatch(remainder, None, key)  # the rest, parsed fresh

    if act == "new":
        sf = session.SessionFrame.from_request(request, cwd=os.getcwd(), shell_id=key)
        if sf is None:
            return _run_single_turn(request)
    elif act in ("refine", "operate"):
        if frame is None:
            return _run_single_turn(request)  # nothing to refine/operate on
        sf = frame
        sf.merge(delta)
    else:  # fallback
        # The value-add seam (Task 45): an elliptical turn the rules can't place,
        # but a live frame exists. Consult the context-aware resolver (torch-free,
        # ONNX) to recover an operate act the rules miss; everything still renders
        # through to_command_plan -> compile -> gate -> render. Destructive turns
        # are never recovered (resolver returns None) -> they fall to single-turn,
        # which abstains (invariant #6). Any encoder absence/failure -> None -> the
        # unchanged single-turn fallback, exactly as before.
        if frame is not None:
            delta, info = session_resolver.resolve_fallback(request, frame)
            if delta is not None:
                frame.merge(delta)
                frame.record(request, info.get("act", "operate"))
                if info.get("source") == "encoder":
                    print("LinuxBuddy ~ interpreted (language model) — review "
                          "before running", file=sys.stderr)
                rc, emitted = _emit_plan_frame(frame.to_command_plan())
                if emitted:
                    session.save(key, frame)
                    return rc
        return _run_single_turn(request)

    sf.record(request, act)
    rc, emitted = _emit_plan_frame(sf.to_command_plan())
    if not emitted:
        return _run_single_turn(request)  # couldn't compile/render → safe default
    session.save(key, sf)
    return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
