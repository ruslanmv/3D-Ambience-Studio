#!/usr/bin/env bash
set -euo pipefail
OWNER="${1:-ruslanmv}"
REPO="${2:-3D-Ambience-Studio}"
if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required: https://cli.github.com/" >&2
  exit 1
fi
gh auth status
gh repo create "$OWNER/$REPO" --public --source . --remote origin --push --description "Ambient environment creation and publishing pipeline for 3D-Avatar-Chatbot and Meta Quest/WebXR"
