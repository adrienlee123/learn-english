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
  REPO=$(gh repo create learn-english --public --source=. --remote=origin \
           --description "B2-C1 vocabulary mined from TV transcripts" --push)
  echo "==> created $REPO"
else
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$REPO.git"
  echo "==> using existing $REPO"
fi

echo "==> pushing main"
git add -A
git -c user.name="$(git config user.name || echo opencode)" \
    -c user.email="$(git config user.email || echo opencode@local)" \
    commit -q -m "Update vocabulary and rebuild app" || echo "    (nothing new to commit)"
git push -q origin HEAD

echo "==> publishing site/ to gh-pages"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cp -R site/. "$TMP/"
printf '' > "$TMP/.nojekyll"          # keep Pages from hiding dotfiles

(
  cd "$TMP"
  git init -q -b gh-pages
  git add -A
  git -c user.name="$(git config user.name || github-actions[bot])" \
      -c user.email="$(git config user.email || 41898282+github-actions[bot]@users.noreply.github.com)" \
      commit -q -m "Deploy $(date '+%Y-%m-%d %H:%M')"
  git push -q --force "https://x-access-token:$(gh auth token)@github.com/$REPO.git" gh-pages
)

echo "==> enabling Pages on gh-pages"
gh api -X PUT "repos/$REPO/pages" \
  -f source[branch]=gh-pages -f source[path]=/ 2>/dev/null \
  || gh api -X POST "repos/$REPO/pages" -f source[branch]=gh-pages -f source[path]=/ \
  || echo "    (Pages may already be enabled)"

sleep 3
echo
echo "Live at: https://$(gh repo view "$REPO" -q .name).github.io/"