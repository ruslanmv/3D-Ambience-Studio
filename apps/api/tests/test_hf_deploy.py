"""Guards on the Hugging Face deployment.

A broken deploy is expensive to notice: the workflow pushes, Hugging Face rebuilds, and the
failure surfaces minutes later in a build log nobody is watching. Everything here is a check that
turns such a failure into a red test on the commit that caused it.

The one thing these tests deliberately do not do is run Docker. What they check instead is the
agreement between the three files that have to stay in step — build-tree.sh decides what is in
the deploy tree, the Dockerfile decides what it copies out of it, and pyproject.toml decides what
gets installed — because every deployment break so far has been a disagreement between two of
them, not a bad Docker instruction.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
HF = REPO / "deploy" / "huggingface"
WORKFLOW = REPO / ".github" / "workflows" / "sync-hf-space.yml"


def _frontmatter() -> dict[str, str]:
    text = (HF / "README.md").read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert match, "The Space README must open with YAML frontmatter."
    out = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


@pytest.fixture(scope="module")
def deploy_tree(tmp_path_factory) -> Path:
    """The real tree, built by the real script — not a fixture imitating one."""
    target = tmp_path_factory.mktemp("hf") / "space"
    result = subprocess.run(
        ["bash", str(HF / "build-tree.sh"), str(target)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"build-tree.sh failed:\n{result.stdout}\n{result.stderr}"
    return target


# ── The Space card ───────────────────────────────────────────────────────────────────────────


def test_space_is_a_docker_space_on_7860():
    """Both halves of the one fact that makes a Docker Space work at all.

    `app_port` must match the port uvicorn binds in the Dockerfile. They are written in two files
    and nothing at runtime reconciles them: a mismatch is a Space that builds, starts, passes its
    own health check and serves nothing.
    """
    front = _frontmatter()
    assert front["sdk"] == "docker"
    assert front["app_port"] == "7860"

    dockerfile = (HF / "Dockerfile").read_text(encoding="utf-8")
    assert "--port" in dockerfile and "7860" in dockerfile.split("CMD")[-1]


def test_space_card_declares_the_licence_the_repo_uses():
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["name"] == "3d-ambience-studio"
    assert _frontmatter()["license"] == "apache-2.0"
    assert (REPO / "LICENSE").is_file()


# ── Dependencies ─────────────────────────────────────────────────────────────────────────────


def test_requirements_matches_pyproject_dependencies():
    """The duplicate list stays a duplicate.

    requirements.txt exists for Docker layer caching, which means the dependency list is written
    twice. Drift would install a different set in the Space than anywhere else, so the copy is
    pinned to the original here rather than trusted.
    """
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    declared = sorted(d.strip() for d in pyproject["project"]["dependencies"])
    mirrored = sorted(
        line.strip()
        for line in (HF / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )
    assert mirrored == declared, (
        "deploy/huggingface/requirements.txt has drifted from pyproject.toml.\n"
        f"  pyproject: {declared}\n  requirements: {mirrored}"
    )


# ── The tree and the Dockerfile agree ────────────────────────────────────────────────────────


def _dockerfile_copy_sources() -> list[str]:
    """Every path the Dockerfile copies from the build context.

    Sources coming from an earlier build stage (``--from=web``) are excluded: those exist only
    inside the image, so looking for them in the tree would fail for the wrong reason.
    """
    sources: list[str] = []
    for line in (HF / "Dockerfile").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.upper().startswith("COPY "):
            continue
        tokens = line.split()[1:]
        if any(t.startswith("--from=") for t in tokens):
            continue
        tokens = [t for t in tokens if not t.startswith("--")]
        sources.extend(tokens[:-1])  # the last token is the destination
    assert sources, "Parsed no COPY sources — the parser or the Dockerfile changed shape."
    return sources


def test_every_path_the_dockerfile_copies_is_in_the_tree(deploy_tree):
    """The check that would have caught a rename.

    The Dockerfile names paths in the *deploy tree*, which is a different, smaller shape than the
    repository. Rename a directory and the inline copies still succeed while the image loses a
    file, so the two are compared directly.
    """
    missing = [src for src in _dockerfile_copy_sources() if not (deploy_tree / src.rstrip("/")).exists()]
    assert not missing, f"Dockerfile copies paths the deploy tree does not contain: {missing}"


def test_tree_carries_the_camera_contracts(deploy_tree):
    """Without these the wizard's target list is empty and no plate can be generated.

    main.py resolves a contract by filename under examples/backplate-camera relative to the
    working directory. It is the one directory whose absence breaks the product while leaving the
    Space apparently healthy — the API answers, the UI loads, the dropdown is just empty.
    """
    contracts = sorted((deploy_tree / "examples" / "backplate-camera").glob("*.json"))
    assert contracts, "No camera contracts in the deploy tree."


def test_tree_omits_build_output_and_caches(deploy_tree):
    """Hugging Face rejects large un-LFS'd blobs, and stale build output is worse than none."""
    for unwanted in ("apps/web/node_modules", "apps/web/dist", "data"):
        assert not (deploy_tree / unwanted).exists(), f"{unwanted} must not be pushed to the Space."
    assert not list(deploy_tree.rglob("__pycache__"))
    assert not list(deploy_tree.rglob("*.pyc"))


def test_tree_carries_no_credentials(deploy_tree):
    """A Space repository is public by default and its history is force-pushed, not amended.

    Anything secret that reaches it has been published, and rewriting the commit does not unsend
    it. Stored provider settings and .env files are stripped by the script; this fails if that
    ever stops being true, and also catches a Hugging Face token pasted into a deploy file.
    """
    assert not list(deploy_tree.rglob("generation-settings.json"))
    assert not list(deploy_tree.rglob(".env"))
    token_like = re.compile(r"hf_[A-Za-z0-9]{20,}")
    offenders = [
        path.relative_to(deploy_tree)
        for path in deploy_tree.rglob("*")
        if path.is_file()
        and path.suffix in {".md", ".py", ".yml", ".yaml", ".sh", ".json", ".toml", ".txt", ""}
        and token_like.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not offenders, f"Files in the deploy tree contain something shaped like an HF token: {offenders}"


def test_the_tree_keeps_hugging_faces_own_lfs_rules(deploy_tree):
    """The deploy replaces the Space's history wholesale, so anything not in the tree is deleted.

    .gitattributes is created by Hugging Face when the Space is made. Nothing we push should match
    its patterns, but silently removing a file the platform put there is the kind of side effect
    that is noticed months later by something else.
    """
    rules = (deploy_tree / ".gitattributes").read_text(encoding="utf-8")
    assert "filter=lfs" in rules


def test_space_readme_replaces_the_repo_readme(deploy_tree):
    """The Space card has to be README.md — Hugging Face reads the frontmatter from that name."""
    assert (deploy_tree / "README.md").read_text(encoding="utf-8").startswith("---\n")
    assert (deploy_tree / "REPO_README.md").is_file()


def test_build_tree_refuses_a_dirty_target(tmp_path):
    """Merging into an existing directory would push a file from an older layout."""
    target = tmp_path / "space"
    target.mkdir()
    (target / "leftover.txt").write_text("from a previous layout", encoding="utf-8")
    result = subprocess.run(
        ["bash", str(HF / "build-tree.sh"), str(target)], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert (target / "leftover.txt").exists(), "A refused build must not delete what is there."


# ── The workflow ─────────────────────────────────────────────────────────────────────────────


def test_workflow_builds_the_tree_with_the_script():
    """Not with its own copy of the file list, which is the thing that goes stale."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "deploy/huggingface/build-tree.sh" in text
    assert "test_hf_deploy.py" in text, "The workflow should run these checks before pushing."


def test_workflow_takes_every_credential_from_secrets():
    """No token, username or Space name baked into the file."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert not re.search(r"hf_[A-Za-z0-9]{20,}", text), "A Hugging Face token is hard-coded."
    for name in ("HF_TOKEN", "HF_USERNAME", "SPACE_NAME"):
        assert f"secrets.{name}" in text


def test_entry_point_reexports_the_one_app():
    """`uvicorn app:app` must reach the same application, not a second one defined for the Space."""
    source = (HF / "app.py").read_text(encoding="utf-8")
    assert "from ambience.main import app" in source
    assert "FastAPI(" not in source, "app.py must not define its own application."
