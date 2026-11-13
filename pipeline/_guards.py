"""Shared guard helpers for the pipeline scripts.

The pipeline used to warn and carry on when an input was missing:

    WARNING: char_readings.json missing - run _build_char_readings.py
    WARNING: beautifulsoup4 not installed; cannot read rendered links

That is the worst of both worlds. The run "succeeds", prints a summary
with a plausible-looking number in it, and the degraded artefact is what
reaches the APK: 506 grammar points silently became 11, and 10 690
Bulgarian glosses became 0.

A missing input and a broken input are different problems. A missing
input has exactly one fix -- run the command that produces it -- so the
scripts now stop and say so. Every guard here prints the command to run.

The one escape hatch is ``--allow-degraded``, for the case where the
degraded output is genuinely what is wanted (for example a fast smoke
run of the pipeline while iterating on something else). It is never the
default, and 08_build_content_db.py refuses to write a degraded database
even with the flag set: a silently-degraded content.db that still
"builds" is the worst possible outcome, because it ships.
"""

from __future__ import annotations

import os
import sys


def allow_degraded() -> bool:
    """True when the run was started with --allow-degraded."""
    return os.environ.get("HANZI_BG_ALLOW_DEGRADED") == "1"


def set_allow_degraded() -> None:
    """Turn on the escape hatch for this process."""
    os.environ["HANZI_BG_ALLOW_DEGRADED"] = "1"


def require_file(path: str, what: str, command: str) -> str | None:
    """Return the path, or stop the run if the file is missing.

    ``what`` says what the file is, in words a reader can act on, and
    ``command`` is the exact command that produces it.

    With --allow-degraded the warning is printed and None is returned
    instead, so the caller can carry on with whatever it can do.
    """
    if os.path.exists(path):
        return path
    message = (
        f"ERROR: missing {what}: {path}\n"
        f"       run: {command}"
    )
    if allow_degraded():
        print(f"WARNING: missing {what} -- continuing in degraded mode")
        print(f"         {command}")
        return None
    print(message, file=sys.stderr)
    raise SystemExit(1)


def require_import(module: str, package: str, command: str) -> None:
    """Stop the run when a third-party package is not importable.

    ``module`` is the import name, ``package`` the pip package that
    provides it.
    """
    try:
        __import__(module)
    except ImportError:
        message = (
            f"ERROR: the '{package}' package is not installed\n"
            f"       run: python -m pip install -r pipeline/requirements.txt\n"
            f"       ({command} needs it)"
        )
        if allow_degraded():
            print(f"WARNING: {package} not installed -- continuing in degraded mode")
            return
        print(message, file=sys.stderr)
        raise SystemExit(1)


def require_ok(result: bool, message: str, command: str) -> None:
    """Stop the run when a step reported that it produced nothing usable."""
    if result:
        return
    if allow_degraded():
        print(f"WARNING: {message} -- continuing in degraded mode")
        return
    print(f"ERROR: {message}\n       run: {command}", file=sys.stderr)
    raise SystemExit(1)
