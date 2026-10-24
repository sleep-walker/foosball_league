#!/usr/bin/env python3
"""Enforce the coverage-floor ratchet: ``coverage-floor.txt`` may only go UP.

The number in ``coverage-floor.txt`` is the minimum total coverage enforced by
``make ci`` (``pytest --cov-fail-under=$(COV_MIN)``).  That gate alone only
stops *measured* coverage from falling below the floor — nothing stops someone
from lowering the floor itself.  This script closes that hole: it compares the
floor in the working tree against the floor on the base commit and fails if the
value decreased.

Pure local git plumbing (``git show``, ``git merge-base``, ``git rev-parse``) —
no network access and no GitHub API calls.  The base commit is picked from the
standard GitHub Actions environment variables when they are present:

  pull_request  ->  merge-base of HEAD and origin/$GITHUB_BASE_REF
  push          ->  the push event's "before" commit, else HEAD~1
  local run     ->  merge-base of HEAD and origin/main (or origin/master, …)

When no comparison point can be determined (brand-new branch, no origin, a
shallow clone that lacks the base commit) or the base commit simply has no
``coverage-floor.txt`` yet (the bootstrapping commit that introduces it), the
check *skips* with a log message and exits 0 rather than crashing.

Exit codes:
  0  floor unchanged / raised, or the check was skipped
  1  the floor decreased (ratchet violation)
  2  the floor file or an argument is unusable
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

FLOOR_FILE = "coverage-floor.txt"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_ERROR = 2

PREFIX = "[coverage-floor-ratchet]"


class FloorError(Exception):
    """A coverage floor value that cannot be parsed."""


def log(message: str) -> None:
    print(f"{PREFIX} {message}", flush=True)


def fail(message: str) -> None:
    print(f"{PREFIX} ERROR: {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# floor file parsing
# ---------------------------------------------------------------------------


def parse_floor(text: str, origin: str) -> float:
    """Return the numeric floor from the contents of a coverage-floor file.

    Blank lines and ``#`` comments are ignored so the file can document itself;
    the first remaining line must be a bare number.  Keep this in sync with the
    ``COV_MIN`` sed expression in the Makefile (``make print-cov-min``).
    """
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            return float(line)
        except ValueError:
            raise FloorError(f"{origin}:{lineno}: {line!r} is not a number") from None
    raise FloorError(f"{origin}: contains no coverage floor value")


def format_floor(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------


def git(*args: str, repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def repo_root(start: Path) -> Path | None:
    done = git("rev-parse", "--show-toplevel", repo=start)
    return Path(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip() else None


def rev_parse(ref: str, repo: Path) -> str | None:
    """Resolve ``ref`` to a commit sha, or None if it does not exist here."""
    done = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", repo=repo)
    return done.stdout.strip() or None


def merge_base(a: str, b: str, repo: Path) -> str | None:
    done = git("merge-base", a, b, repo=repo)
    return done.stdout.strip() if done.returncode == 0 else None


def floor_text_at(ref: str, path: str, repo: Path) -> str | None:
    """Contents of ``path`` at ``ref``, or None when the file is absent there."""
    done = git("show", f"{ref}:{path}", repo=repo)
    return done.stdout if done.returncode == 0 else None


def is_shallow(repo: Path) -> bool:
    done = git("rev-parse", "--is-shallow-repository", repo=repo)
    return done.stdout.strip() == "true"


# ---------------------------------------------------------------------------
# base commit selection
# ---------------------------------------------------------------------------


def push_event_before(repo: Path) -> str | None:
    """The 'before' sha of a GitHub Actions push event, if it is usable.

    Read from the local event payload file — no API call.  Force pushes and
    branch creations report an all-zero sha, which is not a usable base.
    """
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).is_file():
        return None
    try:
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    before = payload.get("before")
    if not isinstance(before, str) or set(before) <= {"0"}:
        return None
    return rev_parse(before, repo)


def resolve_base(repo: Path, head: str, explicit: str | None) -> tuple[str | None, str]:
    """Return (base commit sha or None, human-readable description)."""
    if explicit:
        sha = rev_parse(explicit, repo)
        if sha is None:
            return None, f"--base {explicit!r} does not resolve to a commit in this repository"
        return sha, f"--base {explicit}"

    from_env = os.environ.get("COVERAGE_FLOOR_BASE_REF")
    if from_env:
        sha = rev_parse(from_env, repo)
        if sha is None:
            return None, f"COVERAGE_FLOOR_BASE_REF={from_env!r} does not resolve to a commit here"
        return sha, f"COVERAGE_FLOOR_BASE_REF={from_env}"

    event = os.environ.get("GITHUB_EVENT_NAME", "")
    base_ref = os.environ.get("GITHUB_BASE_REF", "")

    if event in {"pull_request", "pull_request_target"} and base_ref:
        for candidate in (f"origin/{base_ref}", f"refs/remotes/origin/{base_ref}", base_ref):
            sha = rev_parse(candidate, repo)
            if sha is None:
                continue
            base = merge_base(head, sha, repo)
            if base:
                return base, f"merge-base of HEAD and {candidate} (PR base {base_ref})"
            log(
                f"no merge-base between HEAD and {candidate}; comparing against that "
                f"branch tip instead"
            )
            return sha, f"{candidate} tip (PR base {base_ref}, no common ancestor available)"
        hint = " (the clone is shallow — use actions/checkout with fetch-depth: 0)" if is_shallow(repo) else ""
        return None, f"PR base ref {base_ref!r} is not present in this clone{hint}"

    if event == "push":
        before = push_event_before(repo)
        if before:
            return before, "the push event's 'before' commit"
        parent = rev_parse(f"{head}~1", repo)
        if parent:
            return parent, "HEAD~1"
        hint = " (the clone is shallow — use actions/checkout with fetch-depth: 0)" if is_shallow(repo) else ""
        return None, f"no previous commit reachable from {head}{hint}"

    # Local / unknown CI: best effort against the upstream trunk.
    for candidate in ("origin/main", "origin/master", "main", "master"):
        sha = rev_parse(candidate, repo)
        if sha is None:
            continue
        base = merge_base(head, sha, repo)
        if base:
            return base, f"merge-base of HEAD and {candidate}"
        return sha, f"{candidate} tip (no common ancestor with HEAD)"

    return None, "none of origin/main, origin/master, main, master exist in this repository"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if the committed coverage floor is lower than the base commit's.",
    )
    parser.add_argument(
        "--base",
        metavar="REF",
        help="compare against this git ref instead of auto-detecting the base commit",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        default=None,
        help=f"path to the coverage floor file (default: {FLOOR_FILE} at the repo root)",
    )
    parser.add_argument(
        "--print-floor",
        action="store_true",
        help="print the working-tree floor value and exit",
    )
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    root = repo_root(cwd)

    floor_path = Path(args.file) if args.file else (root or cwd) / FLOOR_FILE
    if not floor_path.is_file():
        fail(f"{floor_path} does not exist — the coverage floor file is required")
        return EXIT_ERROR
    try:
        current = parse_floor(floor_path.read_text(encoding="utf-8"), str(floor_path))
    except FloorError as exc:
        fail(str(exc))
        return EXIT_ERROR

    if args.print_floor:
        print(format_floor(current))
        return EXIT_OK

    if root is None:
        log(f"not a git repository ({cwd}) — skipping the ratchet check")
        return EXIT_OK

    try:
        rel_path = floor_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        log(f"{floor_path} is outside {root} — skipping the ratchet check")
        return EXIT_OK

    head_env = os.environ.get("GITHUB_SHA", "")
    head = (head_env and rev_parse(head_env, root)) or rev_parse("HEAD", root)
    if head is None:
        log("HEAD does not resolve to a commit (empty repository?) — skipping the ratchet check")
        return EXIT_OK

    base, how = resolve_base(root, head, args.base)
    if base is None:
        log(f"no base commit to compare against: {how} — skipping the ratchet check")
        return EXIT_OK

    base_text = floor_text_at(base, rel_path, root)
    if base_text is None:
        log(
            f"{rel_path} does not exist at the base commit {base[:12]} ({how}) — "
            f"bootstrapping, skipping the ratchet check (floor is {format_floor(current)})"
        )
        return EXIT_OK

    try:
        previous = parse_floor(base_text, f"{base[:12]}:{rel_path}")
    except FloorError as exc:
        log(f"cannot read the floor at the base commit: {exc} — skipping the ratchet check")
        return EXIT_OK

    if current < previous:
        fail(
            f"coverage floor went DOWN: {format_floor(previous)} -> {format_floor(current)}\n"
            f"  base commit : {base} ({how})\n"
            f"  floor file  : {rel_path}\n"
            f"\n"
            f"The coverage floor is a ratchet: it may only ever be raised.  Lowering it\n"
            f"hides a coverage regression instead of fixing it.  Either restore "
            f"{format_floor(previous)} in\n"
            f"{rel_path}, or add tests until coverage clears the existing floor."
        )
        return EXIT_VIOLATION

    if current > previous:
        log(
            f"coverage floor raised: {format_floor(previous)} -> {format_floor(current)} "
            f"(base {base[:12]}, {how}) — OK"
        )
    else:
        log(
            f"coverage floor unchanged at {format_floor(current)} "
            f"(base {base[:12]}, {how}) — OK"
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
