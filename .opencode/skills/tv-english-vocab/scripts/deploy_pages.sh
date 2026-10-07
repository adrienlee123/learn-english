#!/usr/bin/env bash
# Build the study app and publish it to GitHub Pages via the gh-pages branch.
#
#   deploy_pages.sh                 build + push + enable Pages (if needed)
#   deploy_pages.sh --repo my/repo use an existing repo
#   deploy_pages.sh --no-push      build only, print what would be pushed
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SKILL_DIR/../../.."                # -> project root
SKILL=".opencode/skills/tv-english-vocab"
REPO=""
DO_PUSH=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --no-push) DO_PUSH=0; shift ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

echo "==> building site"
python3 "$SKILL/scripts/build_app.py" --out site --generated "$(date '+%Y-%m-%d %H:%M')"

if [[ ! -d .git ]]; then
  echo "==> initialising repo"
  git init -q
  git add -A
  git -c user.name="$(git config user.name || echo opencode)" \
      -c user.email="$(git config user.email || echo opencode@local)" \
      commit -q -m "Initial commit: tv-english-vocab skill"
fi

if [[ "$DO_PUSH" != "1" ]]; then
  echo "==> --no-push: skipping upload"
  exit 0
fi

if [[ -z "$REPO" ]]; then
  REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)
fi
if [[ -z "$REPO" ]]; then
  gh repo create learn-english --public --source=. --remote=origin \
    --description "B2-C1 vocabulary mined from TV transcripts" --push >/dev/null
  # gh prints a URL here; resolve the canonical owner/name instead.
  REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
  echo "==> created $REPO"
else
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$REPO.git"
  echo "==> using existing $REPO"
fi

# Prefer SSH: on some networks github.com over HTTPS is unreachable even while
# api.github.com and git@github.com still work.
if ! curl -fsS -o /dev/null -m 10 https://github.com 2>/dev/null; then
  if ssh -o BatchMode=yes -o ConnectTimeout=10 -T git@github.com >/dev/null 2>&1; then
    echo "==> HTTPS to github.com unavailable; using SSH"
    git remote set-url origin "git@github.com:$REPO.git"
  fi
fi

# GitHub's receive service occasionally returns 500; retry before giving up.
push_with_retry() {
  local remote="$1" ref="$2" n=1 max=4
  while :; do
    if git push -q --force "$remote" "$ref" 2>/tmp/_push.err; then return 0; fi
    if (( n >= max )); then
      echo "    push failed after $n attempts:" >&2
      tail -2 /tmp/_push.err >&2
      return 1
    fi
    echo "    push attempt $n failed, retrying..." >&2
    sleep $((n * 15))
    n=$((n + 1))
  done
}

# Let git authenticate through the gh helper so no token lands in a URL or log.
gh auth setup-git >/dev/null 2>&1 || true

echo "==> pushing main"
git add -A
git -c user.name="$(git config user.name || opencode)" \
    -c user.email="$(git config user.email || opencode@local)" \
    commit -q -m "Update vocabulary and rebuild app" || echo "    (nothing new to commit)"
# Non-fatal: the site can still be published if the source push is rejected.
push_with_retry origin HEAD || echo "    continuing: gh-pages is what serves the site"

echo "==> publishing site/ to gh-pages"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cp -R site/. "$TMP/"
printf '' > "$TMP/.nojekyll"          # keep Pages from hiding dotfiles

(
  cd "$TMP"
  git init -q -b gh-pages
  git remote add origin "git@github.com:$REPO.git"
  git add -A
  git -c user.name="$(git config user.name || github-actions)" \
      -c user.email="$(git config user.email || github-actions@users.noreply.github.com)" \
      commit -q -m "Deploy $(date '+%Y-%m-%d %H:%M')"
  push_with_retry origin gh-pages
)

echo "==> enabling Pages on gh-pages"
gh api -X PUT "repos/$REPO/pages" \
  -f source[branch]=gh-pages -f source[path]=/ 2>/dev/null \
  || gh api -X POST "repos/$REPO/pages" -f source[branch]=gh-pages -f source[path]=/ \
  || echo "    (Pages may already be enabled)"

sleep 3
# A repo named after the owner serves from the root; anything else is a subpath.
OWNER="${REPO%%/*}"
NAME="${REPO##*/}"
if [[ "$NAME" == "$OWNER.github.io" ]]; then
  URL="https://$OWNER.github.io/"
else
  URL="https://$OWNER.github.io/$NAME/"
fi
echo
echo "Live at: $URL"