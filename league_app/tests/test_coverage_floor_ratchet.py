"""Tests for scripts/check_coverage_floor_ratchet.py (CI infrastructure).

The ratchet is the only thing standing between "coverage may not regress" and
"coverage may not regress unless you edit one number", so it gets its own
tests: each one builds a throwaway git repository in tmp_path and runs the real
script as a subprocess, the same way `make ci` and GitHub Actions do.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_coverage_floor_ratchet.py"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_ERROR = 2

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _load_module():
    spec = importlib.util.spec_from_file_location("_floor_ratchet", SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot import {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ratchet = _load_module()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    """Run git in `repo` with a hermetic environment (no user/system config)."""
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Ratchet Test",
        "GIT_AUTHOR_EMAIL": "ratchet@example.invalid",
        "GIT_COMMITTER_NAME": "Ratchet Test",
        "GIT_COMMITTER_EMAIL": "ratchet@example.invalid",
    }
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return done.stdout.strip()


def run_script(repo: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the ratchet script with `repo` as cwd, stripped of inherited CI vars."""
    child_env = {k: v for k, v in os.environ.items() if not k.startswith(("GITHUB_", "COVERAGE_FLOOR_"))}
    child_env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
        }
    )
    child_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=child_env,
    )


def write_floor(repo: Path, value: str) -> None:
    (repo / "coverage-floor.txt").write_text(f"# a comment\n\n{value}\n", encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo whose single commit sets the coverage floor to 60."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "--initial-branch=main")
    write_floor(root, "60")
    git(root, "add", "coverage-floor.txt")
    git(root, "commit", "-qm", "add coverage floor")
    return root


# ---------------------------------------------------------------------------
# parse_floor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("60\n", 60.0),
        ("60", 60.0),
        ("  62.5  \n", 62.5),
        ("# comment\n\n60\n", 60.0),
        ("60  # trailing comment\n", 60.0),
        ("\n\n# only comments then value\n70\n", 70.0),
    ],
)
def test_parse_floor_accepts(text: str, expected: float) -> None:
    assert ratchet.parse_floor(text, "test") == expected


@pytest.mark.parametrize("text", ["", "# just a comment\n", "sixty\n", "60 70\n"])
def test_parse_floor_rejects(text: str) -> None:
    with pytest.raises(ratchet.FloorError):
        ratchet.parse_floor(text, "test")


def test_parse_floor_matches_the_makefile() -> None:
    """The Makefile's sed expression and parse_floor() must agree on COV_MIN."""
    if shutil.which("make") is None:
        pytest.skip("make is not installed")
    # --no-print-directory: -C otherwise prints Entering/Leaving lines.
    # MAKEFLAGS/MAKELEVEL are dropped so this works when pytest itself was
    # started by `make ci` (no inherited jobserver, no recursion warnings).
    env = {k: v for k, v in os.environ.items() if k not in {"MAKEFLAGS", "MFLAGS", "MAKELEVEL"}}
    from_make = subprocess.run(
        ["make", "--no-print-directory", "-C", str(REPO_ROOT), "print-cov-min"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()
    floor_file = REPO_ROOT / "coverage-floor.txt"
    from_script = ratchet.format_floor(ratchet.parse_floor(floor_file.read_text(encoding="utf-8"), str(floor_file)))
    assert from_make == from_script


# ---------------------------------------------------------------------------
# the ratchet itself
# ---------------------------------------------------------------------------


def test_lowering_the_floor_fails(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    write_floor(repo, "50")
    done = run_script(repo, "--base", base)
    assert done.returncode == EXIT_VIOLATION
    assert "coverage floor went DOWN: 60 -> 50" in done.stderr


def test_raising_the_floor_passes(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    write_floor(repo, "65")
    done = run_script(repo, "--base", base)
    assert done.returncode == EXIT_OK
    assert "coverage floor raised: 60 -> 65" in done.stdout


def test_unchanged_floor_passes(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    done = run_script(repo, "--base", base)
    assert done.returncode == EXIT_OK
    assert "unchanged at 60" in done.stdout


def test_fractional_decrease_fails(repo: Path) -> None:
    """59.9 < 60 — the compare is numeric, not lexical."""
    base = git(repo, "rev-parse", "HEAD")
    write_floor(repo, "59.9")
    done = run_script(repo, "--base", base)
    assert done.returncode == EXIT_VIOLATION
    assert "60 -> 59.9" in done.stderr


def test_deleting_the_floor_file_is_an_error(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    (repo / "coverage-floor.txt").unlink()
    done = run_script(repo, "--base", base)
    assert done.returncode == EXIT_ERROR
    assert "does not exist" in done.stderr


# ---------------------------------------------------------------------------
# graceful skips
# ---------------------------------------------------------------------------


def test_bootstrapping_commit_skips(tmp_path: Path) -> None:
    """The commit that first adds coverage-floor.txt has nothing to compare to."""
    root = tmp_path / "bootstrap"
    root.mkdir()
    git(root, "init", "-q", "--initial-branch=main")
    (root / "README").write_text("hello\n", encoding="utf-8")
    git(root, "add", "README")
    git(root, "commit", "-qm", "initial commit without a floor")
    base = git(root, "rev-parse", "HEAD")
    write_floor(root, "60")
    done = run_script(root, "--base", base)
    assert done.returncode == EXIT_OK
    assert "bootstrapping" in done.stdout


def test_missing_base_ref_skips(repo: Path) -> None:
    done = run_script(repo, "--base", "origin/does-not-exist")
    assert done.returncode == EXIT_OK
    assert "skipping" in done.stdout


def test_no_comparison_point_skips(repo: Path) -> None:
    """A fresh branch with one commit, no origin and no main-like ref."""
    git(repo, "checkout", "-q", "-b", "feature")
    git(repo, "branch", "-q", "-D", "main")
    write_floor(repo, "50")  # would be a violation if a base could be found
    done = run_script(repo)
    assert done.returncode == EXIT_OK
    assert "no base commit to compare against" in done.stdout


def test_not_a_git_repository_skips(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    write_floor(plain, "60")
    done = run_script(plain)
    assert done.returncode == EXIT_OK
    assert "not a git repository" in done.stdout


# ---------------------------------------------------------------------------
# base-commit detection from the GitHub Actions environment
# ---------------------------------------------------------------------------


def test_pull_request_uses_merge_base_of_the_base_branch(repo: Path) -> None:
    """A PR that lowers the floor fails, detected purely from GITHUB_* vars."""
    git(repo, "update-ref", "refs/remotes/origin/main", git(repo, "rev-parse", "main"))
    git(repo, "checkout", "-q", "-b", "pr-branch")
    write_floor(repo, "40")
    git(repo, "commit", "-qam", "lower the floor")
    done = run_script(
        repo,
        env={
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_BASE_REF": "main",
            "GITHUB_SHA": git(repo, "rev-parse", "HEAD"),
        },
    )
    assert done.returncode == EXIT_VIOLATION
    assert "60 -> 40" in done.stderr
    assert "merge-base of HEAD and origin/main" in done.stderr


def test_push_compares_against_the_previous_commit(repo: Path) -> None:
    write_floor(repo, "55")
    git(repo, "commit", "-qam", "lower the floor")
    done = run_script(
        repo,
        env={
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_SHA": git(repo, "rev-parse", "HEAD"),
        },
    )
    assert done.returncode == EXIT_VIOLATION
    assert "60 -> 55" in done.stderr
    assert "HEAD~1" in done.stderr


def test_push_event_payload_before_wins_over_head_parent(repo: Path, tmp_path: Path) -> None:
    """A multi-commit push is judged against the floor before the whole push."""
    before = git(repo, "rev-parse", "HEAD")
    write_floor(repo, "70")
    git(repo, "commit", "-qam", "raise the floor")
    write_floor(repo, "58")
    git(repo, "commit", "-qam", "and quietly drop it below where it started")
    event = tmp_path / "event.json"
    event.write_text(f'{{"before": "{before}"}}', encoding="utf-8")
    done = run_script(
        repo,
        env={
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_EVENT_PATH": str(event),
            "GITHUB_SHA": git(repo, "rev-parse", "HEAD"),
        },
    )
    assert done.returncode == EXIT_VIOLATION
    assert "60 -> 58" in done.stderr
    assert "'before' commit" in done.stderr


def test_local_run_compares_against_origin_main(repo: Path) -> None:
    git(repo, "update-ref", "refs/remotes/origin/main", git(repo, "rev-parse", "main"))
    git(repo, "checkout", "-q", "-b", "local-work")
    write_floor(repo, "45")
    done = run_script(repo)
    assert done.returncode == EXIT_VIOLATION
    assert "merge-base of HEAD and origin/main" in done.stderr


def test_base_ref_env_override(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    write_floor(repo, "61")
    done = run_script(repo, env={"COVERAGE_FLOOR_BASE_REF": base})
    assert done.returncode == EXIT_OK
    assert "raised: 60 -> 61" in done.stdout


def test_print_floor(repo: Path) -> None:
    done = run_script(repo, "--print-floor")
    assert done.returncode == EXIT_OK
    assert done.stdout.strip() == "60"
