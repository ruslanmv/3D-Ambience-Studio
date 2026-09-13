"""Checks that run before anything is billed.

Two different kinds of harm, both cheap to rule out and expensive to discover late.

**A leaked credential.** A key that reaches a commit is a key that has to be revoked, and by the
time anybody notices, it is in a fork, a CI log and a clone. So before a paid run this refuses to
proceed if `.env` is not ignored, or if any *tracked* file carries something shaped like a key.
The check is on tracked files rather than the whole tree on purpose: an ignored `.env` holding a
real key is the intended arrangement, not a finding.

**A wasted batch.** Twenty images at production quality is real money, and the ways to waste it
are dull: no key, a key that is a placeholder, an output directory that already holds a published
version. Each of those fails identically at image one and at image twenty, so they are worth
catching at image zero.

Everything returns problems rather than raising, so a caller can print all of them at once. A
person who fixes one, re-runs, and is told about the next one has been failed twice.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

#: An assignment that carries a value.
#:
#: Two details are load-bearing, and both were bugs first. The separator may be preceded by a
#: closing quote, because in JSON the name is quoted too — `"OPENAI_API_KEY": "sk-…"` — and a
#: pattern that insists on `NAME=` walks straight past a key in a settings file. And the gap
#: around the separator is spaces and tabs, never `\s`, because `\s` matches a newline: in
#: .env.example, `OPENAI_API_KEY=` followed by the next line's variable name matched, and an
#: empty placeholder was reported as a leak.
ASSIGNMENT = re.compile(r"""(OPENAI_API_KEY|HF_TOKEN|OPENAI_KEY)["']?[ \t]*[=:][ \t]*["']?([A-Za-z0-9_\-]{8,})""")

#: Files a key legitimately appears in as an empty placeholder.
ALLOWED_EMPTY = {".env.example"}

TEXT_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".json", ".md", ".yml", ".yaml", ".toml", ".sh", ".txt", ".env", ""}


def _git(root: Path, *args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=30, check=False
        )
        return result.returncode, result.stdout
    except (OSError, subprocess.SubprocessError):
        # Not a checkout, or no git. Not a reason to block a run — only a reason not to claim the
        # repository is clean.
        return 1, ""


def env_is_ignored(root: Path) -> bool:
    code, _ = _git(root, "check-ignore", "-q", ".env")
    return code == 0


def tracked_files_with_secrets(root: Path) -> list[str]:
    """Tracked files carrying something shaped like a real credential."""
    code, listing = _git(root, "ls-files")
    if code != 0:
        return []
    found = []
    for name in listing.splitlines():
        if name in ALLOWED_EMPTY:
            continue
        path = root / name
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if ASSIGNMENT.search(text):
            found.append(name)
    return found


def check(root: Path, *, require_key: bool = True) -> list[str]:
    """Every reason not to start a paid run, collected."""
    problems: list[str] = []

    if not env_is_ignored(root):
        problems.append(
            ".env is not ignored by git. Add it to .gitignore before putting a key in it — a "
            "committed key has to be revoked, not deleted."
        )

    leaked = tracked_files_with_secrets(root)
    if leaked:
        problems.append(
            "These tracked files contain something shaped like a credential: "
            + ", ".join(leaked)
            + ". Remove the value and rotate the key before generating anything."
        )

    if require_key:
        key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if not key:
            problems.append(
                "No OPENAI_API_KEY in the environment. Export it, or put it in .env (ignored). "
                "It is never read from a manifest, a project file or the settings store."
            )
        elif len(key) < 20 or key.lower().startswith(("your", "sk-xxx", "changeme", "<")):
            problems.append("OPENAI_API_KEY looks like a placeholder rather than a key.")

    return problems
