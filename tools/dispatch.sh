#!/usr/bin/env bash
#
# Fire the collect workflow via GitHub's repository_dispatch API.
# Use this to test the external trigger path locally, or as a fallback
# when the cron-job.org external trigger ALSO fails (belt + braces +
# manual override).
#
# Usage:
#   tools/dispatch.sh morning
#   tools/dispatch.sh evening
#
# Requires the `gh` CLI authenticated to a token with workflow scope.
# Reads owner/repo from the current git remote.

set -euo pipefail

EDITION="${1:-}"
if [ -z "$EDITION" ] || { [ "$EDITION" != "morning" ] && [ "$EDITION" != "evening" ]; }; then
  echo "Usage: $0 morning|evening" >&2
  exit 2
fi

EVENT_TYPE="${EDITION}_brief"

# Get owner/repo from origin remote.
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
if [ -z "$REPO" ]; then
  echo "Could not determine repo. Run inside the repo, or set REPO=owner/name." >&2
  exit 2
fi

echo "Firing repository_dispatch event '${EVENT_TYPE}' on ${REPO}…"
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  "/repos/${REPO}/dispatches" \
  -f "event_type=${EVENT_TYPE}" \
  --silent

echo "Dispatch sent. Watch:"
echo "  https://github.com/${REPO}/actions/workflows/collect.yml"
