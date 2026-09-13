"""The checks that stand between a rotated key and a committed one.

Written after a key was pasted into a transcript and had to be rotated. The lesson was not "be
careful" — it was that nothing in the repository would have stopped the next one reaching a
commit, and a check that only exists in somebody's head is not a check.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from ambience.services import preflight

REPO_ROOT = Path(__file__).resolve().parents[3]

#: The fake credentials, assembled rather than written out.
#:
#: This file is scanned by the very check it tests. A literal `sk-proj-…` here would make every
#: paid run refuse to start, citing this file — and the obvious fix, exempting `tests/`, would
#: carve out the one directory where a real key is most likely to be pasted by accident. So the
#: checker stays strict and the fixture is built at runtime. What lands in the fixture repository
#: is byte-identical to a literal.
FAKE_OPENAI = "sk-" + "proj-" + "abcdefghijklmnop"
FAKE_HF = "hf_" + "ABCDEFGHIJKLMNOPQRSTUVWX"

#: Held in a name, for the same reason, and note that this sentence is careful not to spell the
#: pattern out either. A scanner cannot tell a value from an identifier: a quoted variable name
#: followed by a colon and another variable reads as a leak even though nothing secret is there.
#: Over-eager is the right direction for a secret scanner to err, so the test moves, not the check.
ENV_NAME = "OPENAI_" + "API_KEY"


@pytest.fixture
def repo(tmp_path):
    """A real git repository, because every check here asks git a question."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True)
    return tmp_path


def commit(repo: Path, name: str, text: str) -> None:
    (repo / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", name], cwd=repo, check=True)


class TestThisRepository:
    def test_env_is_ignored_here(self):
        # The check protecting this repository, run against this repository.
        assert preflight.env_is_ignored(REPO_ROOT)

    def test_no_tracked_file_carries_a_credential(self):
        assert preflight.tracked_files_with_secrets(REPO_ROOT) == []

    def test_the_example_file_exists_and_is_empty_of_values(self):
        example = REPO_ROOT / ".env.example"
        assert example.is_file()
        text = example.read_text(encoding="utf-8")
        assert "OPENAI_API_KEY=" in text
        assert preflight.ASSIGNMENT.search(text) is None, ".env.example must carry names, never values"


class TestDetection:
    def test_a_tracked_key_is_found(self, repo):
        commit(repo, "config.py", f'OPENAI_API_KEY = "{FAKE_OPENAI}"')
        assert preflight.tracked_files_with_secrets(repo) == ["config.py"]

    def test_an_untracked_env_is_not_a_finding(self, repo):
        # An ignored .env holding a real key is the intended arrangement, not a leak.
        (repo / ".env").write_text(f"OPENAI_API_KEY={FAKE_OPENAI}\n", encoding="utf-8")
        assert preflight.tracked_files_with_secrets(repo) == []

    def test_an_empty_placeholder_is_not_a_finding(self, repo):
        commit(repo, ".env.example", "OPENAI_API_KEY=\nHF_TOKEN=\n")
        assert preflight.tracked_files_with_secrets(repo) == []

    def test_a_hugging_face_token_counts_too(self, repo):
        commit(repo, "notes.md", f"HF_TOKEN: {FAKE_HF}")
        assert preflight.tracked_files_with_secrets(repo) == ["notes.md"]


class TestGate:
    def test_an_unignored_env_blocks_a_paid_run(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        problems = preflight.check(tmp_path, require_key=False)
        assert any(".env is not ignored" in p for p in problems)

    def test_a_leaked_key_blocks_a_paid_run(self, repo):
        commit(repo, "settings.json", json.dumps({ENV_NAME: FAKE_OPENAI}))
        assert any("credential" in p for p in preflight.check(repo, require_key=False))

    def test_a_missing_key_blocks_a_paid_run(self, repo, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert any("No OPENAI_API_KEY" in p for p in preflight.check(repo))

    def test_a_placeholder_key_blocks_a_paid_run(self, repo, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "your-key-here")
        assert any("placeholder" in p for p in preflight.check(repo))

    def test_a_clean_repository_with_a_key_passes(self, repo, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", FAKE_OPENAI + "a" * 24)
        assert preflight.check(repo) == []

    def test_every_problem_is_reported_at_once(self, tmp_path, monkeypatch):
        # Fixing one, re-running and being told about the next has failed the person twice.
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        commit(tmp_path, "leak.py", f'OPENAI_API_KEY="{FAKE_OPENAI}"')
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert len(preflight.check(tmp_path)) >= 3
