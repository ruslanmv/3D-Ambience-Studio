#!/usr/bin/env bash
# Build the exact file tree that gets pushed to the Hugging Face Space.
#
#   bash deploy/huggingface/build-tree.sh /tmp/space
#
# One definition of "what the Space contains", used by three callers: the sync workflow, anyone
# testing the image locally with `docker build`, and tests/test_hf_deploy.py, which builds the
# tree and checks that every path the Dockerfile copies is actually in it. That last one is the
# reason this is a script and not a list of `cp` lines inside the workflow — a rename in the
# repository silently breaks an inline copy, and nothing notices until a deploy fails.
#
# The tree is deliberately smaller than the repository. A Space is a public git repo that gets
# rebuilt on every push, so it carries only what the image needs.
set -euo pipefail

TARGET="${1:?usage: build-tree.sh <target-dir>}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HF_DIR="$REPO_ROOT/deploy/huggingface"

mkdir -p "$TARGET"
# Refuse a non-empty target rather than merging into it: a leftover file from an older layout
# would be pushed to the Space and then rebuilt into the image.
if [ -n "$(ls -A "$TARGET" 2>/dev/null)" ]; then
    echo "❌ $TARGET is not empty — pass a fresh directory." >&2
    exit 1
fi

cd "$REPO_ROOT"

# ── Space-specific files, at the root where Hugging Face looks for them ───────────────────────
cp "$HF_DIR/README.md" "$TARGET/README.md"          # the Space card: YAML frontmatter + docs
cp "$HF_DIR/Dockerfile" "$TARGET/Dockerfile"        # what the Space builds
cp "$HF_DIR/requirements.txt" "$TARGET/requirements.txt"
cp "$HF_DIR/app.py" "$TARGET/app.py"                # uvicorn app:app
cp "$HF_DIR/.dockerignore" "$TARGET/.dockerignore"
cp "$HF_DIR/gitattributes" "$TARGET/.gitattributes"   # HF's default LFS rules, not ours to drop

# ── The application ──────────────────────────────────────────────────────────────────────────
cp pyproject.toml "$TARGET/pyproject.toml"
cp LICENSE "$TARGET/LICENSE"
cp README.md "$TARGET/REPO_README.md"               # renamed: README.md is the Space card

mkdir -p "$TARGET/apps"
cp -R apps/api "$TARGET/apps/api"
cp -R apps/web "$TARGET/apps/web"                   # source — stage 1 of the Dockerfile builds it
cp -R schemas "$TARGET/schemas"
cp -R examples "$TARGET/examples"                   # camera contracts; the plate routes need these

# ── Strip what must not be pushed ────────────────────────────────────────────────────────────
# Build output and caches would be stale the moment they landed, and node_modules is both
# enormous and full of platform-specific binaries that Hugging Face would reject as un-LFS'd
# blobs. The image rebuilds all of it.
rm -rf "$TARGET/apps/web/node_modules" "$TARGET/apps/web/dist"
# The Space runs the app, it does not check it. The tests are also the one part of the tree that
# would fail if anybody did run them there, since they look for repository directories the deploy
# tree deliberately omits.
rm -rf "$TARGET/apps/api/tests"
# The development Dockerfiles (API on 8000, Vite on 5173). Next to the Space's own Dockerfile they
# are three files describing three different ways to start, two of which do not apply here.
rm -f "$TARGET/apps/api/Dockerfile" "$TARGET/apps/web/Dockerfile"
find "$TARGET" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$TARGET" -name '*.py[cod]' -delete
find "$TARGET" -name '.pytest_cache' -type d -prune -exec rm -rf {} +
find "$TARGET" -name '.ruff_cache' -type d -prune -exec rm -rf {} +
# Any stored credential or generated project from a local run. The data directory is gitignored,
# so this should never match — it is here because pushing one to a public Space repository is
# unrecoverable, and "should never" is not a guarantee worth relying on.
rm -rf "$TARGET/data"
find "$TARGET" -name 'generation-settings.json' -delete
find "$TARGET" -name '.env' -delete

echo "✅ deploy tree built at $TARGET"
