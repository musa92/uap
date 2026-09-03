#!/usr/bin/env bash
# Point every repository URL at a chosen GitHub owner and repo name.
#
#   scripts/set-repo.sh universal-ads-protocol uap    # org
#   scripts/set-repo.sh musa92 uap                    # personal account
#
# Run once before the first push. GitHub preserves stars, forks and issues on a
# later transfer and leaves permanent redirects, so this is reversible.
set -euo pipefail

OWNER="${1:?usage: set-repo.sh <owner> [repo]}"
REPO="${2:-uap}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

FILES=$(grep -rl 'github\.com/[A-Za-z0-9_-]*/uap' "$ROOT" \
        --include='*.md' --include='*.toml' --include='*.json' \
        --exclude-dir=.git || true)

if [ -z "$FILES" ]; then
  echo "no repository URLs found"; exit 0
fi

for f in $FILES; do
  perl -pi -e "s{github\\.com/[A-Za-z0-9_-]+/uap\\b}{github.com/${OWNER}/${REPO}}g" "$f"
  echo "  updated $(basename "$f")"
done

echo
echo "repository URLs now point at https://github.com/${OWNER}/${REPO}"
