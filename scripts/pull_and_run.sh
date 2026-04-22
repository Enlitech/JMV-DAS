#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TARGET_BRANCH="${JMV_DAS_TARGET_BRANCH:-}"
if [[ -z "$TARGET_BRANCH" && -f "$ROOT/.jmv-das-target-branch" ]]; then
  TARGET_BRANCH="$(tr -d '[:space:]' < "$ROOT/.jmv-das-target-branch")"
fi
if [[ -z "$TARGET_BRANCH" ]]; then
  TARGET_BRANCH="$(git branch --show-current)"
fi

if [[ -z "$TARGET_BRANCH" ]]; then
  echo "Failed to determine target branch." >&2
  exit 1
fi

git fetch origin "$TARGET_BRANCH"

CURRENT_BRANCH="$(git branch --show-current || true)"
if [[ "$CURRENT_BRANCH" != "$TARGET_BRANCH" ]]; then
  if git show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
    git checkout "$TARGET_BRANCH"
  else
    git checkout -b "$TARGET_BRANCH" "origin/$TARGET_BRANCH"
  fi
fi

git pull --ff-only origin "$TARGET_BRANCH"
./scripts/run.sh
