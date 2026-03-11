#!/usr/bin/env bash
# Share the DebaterHub SDK env vars via 1Password secure link.
#
# Usage:
#   ./scripts/share-env.sh                    # anyone with link can view
#   ./scripts/share-env.sh dev@example.com    # restricted to that email
#   OP_LINK_EXPIRY=30d ./scripts/share-env.sh # custom expiry (default 7d)
#
# Prerequisites:
#   1. Install 1Password CLI: https://developer.1password.com/docs/cli/get-started
#   2. Sign in: eval $(op signin)

set -euo pipefail

ITEM_ID="sblawz4r3ytx4jkvodfxdjnh4q"
EXPIRY="${OP_LINK_EXPIRY:-7d}"

# Check op exists
if ! command -v op &>/dev/null; then
  echo "1Password CLI (op) not found."
  echo "Install: https://developer.1password.com/docs/cli/get-started"
  exit 1
fi

# Check signed in
if ! op whoami &>/dev/null; then
  echo "Not signed in to 1Password."
  echo "Run: eval \$(op signin)"
  exit 1
fi

# Build share command
SHARE_ARGS=(item share "$ITEM_ID" --expiry "$EXPIRY")

if [[ -n "${1:-}" ]]; then
  SHARE_ARGS+=(--emails "$1")
  echo "Sharing with: $1 (restricted)"
else
  echo "Creating public share link"
fi

LINK=$(op "${SHARE_ARGS[@]}" 2>&1)

echo ""
echo "--- DebaterHub SDK Environment ---"
echo ""
echo "  $LINK"
echo ""
echo "Expires: $EXPIRY | No 1Password account needed to view"
echo ""
echo "After opening, create a .env file:"
echo "  cp .env.example .env"
echo "  # paste values from the link into .env"
