#!/usr/bin/env python3
"""Fetch a TV episode transcript for vocabulary mining.

Two modes:

1. Online (default): resolve the show slug on springfieldspringfield.co.uk,
   fetch the episode script page, and save clean dialogue text.

2. Local: parse a user-supplied .srt / .vtt / .txt subtitle or transcript file
   and save the English lines in the same normalized shape.

Usage
-----
  # single episode
  fetch_transcript.py --show "breaking bad" --season 1 --episode 1

  # S01E05 shorthand
  fetch_transcript.py --show succession --code s03e11

  # discover what is available (episode list + titles)
  fetch_transcript.py --show "big bang theory" --list

  # local subtitle file
  fetch_transcript.py --file ~/Downloads/Breaking.Bad.S01E01.srt --show "Breaking Bad" --code s01e01

  # print to stdout instead of writing files
  fetch_transcript.py --show friends --code s01e01 --stdout --max-chars 4000
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

BASE = "https://www.springfieldspringfield.co.uk"
SEARCH_URL = f"{BASE}/tv_show_episode_scripts.php?search={{q}}"
SHOW_URL = f"{BASE}/episode_scripts.php?tv-show={{slug}}"
EPISODE_URL = f"{BASE}/view_episode_scripts.php?tv-show={{slug}}&episode={{code}}"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_OUT_ROOT = Path("data/transcripts")


# --------------------------------------------------------------------------- #
# http
# --------------------------------------------------------------------------- #
def fetch(url: str, timeout: int = 30, retries: int = 3) -> str:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return raw.decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - network noise is expected here
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last}")


# --------------------------------------------------------------------------- #
# show resolution
# --------------------------------------------------------------------------- #
STOP_SLUGS = {"the-simpsons", "coven-academy-2026"}

# Breadcrumb labels that are site chrome rather than an episode title.
CRUMB_NOISE = {
    "tv show episode scripts",
    "episode scripts",
    "movie scripts",
    "more tv show episode scripts",
}


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _tokens(slug: str) -> list[str]:
    """Significant words of a slug: drop year suffixes and a leading article."""
    parts = [p for p in slug.split("-") if p]
    parts = [p for p in parts if not re.fullmatch(r"(19|20)\d{2}", p)]
    if parts and parts[0] in {"the", "a", "an"}:
        parts = parts[1:]
    return parts


def score_slug(slug: str, show: str) -> int:
    """Higher is better. Ranks 'stranger-things-2016' above 'beyond-stranger-things'."""
    want = slugify(show)
    want_tokens = _tokens(want)
    got = _tokens(slug)

    score = 0
    if slug == want:
        score += 200
    if got == want_tokens:
        score += 120
    if slug.startswith(want + "-"):
        score += 40
    if want_tokens and want_tokens == got[: len(want_tokens)]:
        score += 60
    if want_tokens and set(want_tokens) <= set(got):
        score += 30
    elif want_tokens and got and want_tokens[0] == got[0]:
        score += 5

    # This skill targets US shows, so break ties against non-US editions.
    tail = set(got) - set(want_tokens)
    if "uk" in tail or "british" in tail:
        score -= 40
    if "us" in tail or "american" in tail:
        score += 10

    # prefer short, tight slugs
    score -= len(got) * 2
    return score


def search_slugs(show: str) -> list[str]:
    page = fetch(SEARCH_URL.format(q=urllib.parse.quote(show)))
    found = re.findall(r"tv-show=([a-z0-9\-\.]+)", page)
    # de-duplicate, preserve order
    seen: list[str] = []
    for slug in found:
        if slug not in seen and slug not in STOP_SLUGS:
            seen.append(slug)
    return seen


def resolve_slug(show: str, hint: str | None = None) -> str:
    if hint:
        return slugify(hint)
    candidates = search_slugs(show)
    if not candidates:
        raise RuntimeError(
            f"no show found for {show!r} on {BASE}. "
            "Re-run with --slug <known-slug> or use --file with a local subtitle."
        )
    ranked = sorted(candidates, key=lambda s: score_slug(s, show), reverse=True)
    best, top = ranked[0], score_slug(ranked[0], show)
    if top <= 0:
        raise RuntimeError(
            f"could not confidently match {show!r}; candidates: {candidates[:8]}. "
            "Pass --slug to choose one."
        )
    return best


# --------------------------------------------------------------------------- #
# episode list
# --------------------------------------------------------------------------- #
@dataclass
class Episode:
    code: str  # s01e01
    number: str  # "1."
    title: str


def episode_list(slug: str) -> list[Episode]:
    page = fetch(SHOW_URL.format(slug=slug))
    pattern = re.compile(
        r'href="[^"]*view_episode_scripts\.php\?tv-show=[^"]*&episode=(s\d+e\d+)"[^>]*>(.*?)</a>',
        re.S,
    )
    out: list[Episode] = []
    for code, label in pattern.findall(page):
        label = html.unescape(re.sub(r"<[^>]+>", "", label)).strip()
        m = re.match(r"^(\d+\.?\s*)(.*)$", label)
        number, title = (m.group(1).strip(), m.group(2).strip()) if m else ("", label)
        out.append(Episode(code=code.lower(), number=number, title=title))
    return out


# --------------------------------------------------------------------------- #
# online script extraction
# --------------------------------------------------------------------------- #
def extract_script(page: str) -> str:
    anchor = page.find('class="scrolling-script-container"')
    if anchor < 0:
        raise RuntimeError("script container not found; the page layout may have changed")
    # Resume after the opening tag's '>' so its attributes are not kept.
    start = page.find(">", anchor)
    start = start + 1 if start > 0 else anchor
    end = page.find('class="breadcrumbs"', start)
    body = page[start : end if end > start else len(page)]

    body = re.sub(r"<script\b.*?</script>", "\n", body, flags=re.S | re.I)
    body = re.sub(r"<style\b.*?</style>", "\n", body, flags=re.S | re.I)
    body = re.sub(r"<br\s*/?>", "\n", body)
    body = re.sub(r"</(p|div|li|tr)>", "\n", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)

    lines: list[str] = []
    for raw in body.split("\n"):
        line = raw.replace("\u00a0", " ")
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)

    # Collapse the CSS blob that sometimes leaks into the container.
    lines = [ln for ln in lines if not ln.startswith("@charset") and "--bs-" not in ln]

    # Cut the page footer that follows the script.
    cuts = (
        "Report an Issue",
        "Previous Episode",
        "Springfield! Springfield!",
        "Episode Scripts |",
        "More TV Show Episode Scripts",
    )
    for i, ln in enumerate(lines):
        if ln.startswith(cuts):
            lines = lines[:i]
            break

    # Nav labels and subtitle index numbers can survive the cut.
    nav = {"Next Episode", "Previous Episode", "Report an Issue"}
    cleaned = [ln for ln in lines if ln.strip() not in nav]
    cleaned = [ln for ln in cleaned if not re.fullmatch(r"\d{1,3}", ln)]
    return "\n".join(ln.lstrip("\ufeff") for ln in cleaned)


CHROME = re.compile(
    r"^(?:window\.|_taboola|function\s*\(|Springfield!?\s*Springfield!?|About|"
    r"Terms|Privacy Policy|Contact|Previous Episode|Next Episode|"
    r"Report an Issue|Episode Scripts \||\(function|\}\)|var\s|if\s*\(|/\*)",
)

# A plausible dialogue line: starts with a capital/quote, ends in normal
# punctuation, and contains no code punctuation soup.
CODEISH = re.compile(r"[{};=<>|\[\]]|\w+\s*\(\s*['\"]")


def dialogue_lines(text: str) -> list[str]:
    """Lines that look like actual spoken or scripted content."""
    out: list[str] = []
    for ln in text.split("\n"):
        words = ln.split()
        if len(words) < 3 or CHROME.match(ln) or CODEISH.search(ln):
            continue
        if not re.search(r"[A-Za-z]{3}", ln):
            continue
        out.append(ln)
    return out


def episode_title_from_page(page: str, code: str) -> str:
    """Breadcrumb ends with '... > Breaking Bad > Season 1 > Pilot'."""
    m = re.search(r'<div class="breadcrumbs">(.*?)</div>', page, re.S)
    if not m:
        return ""
    # Split on the '>' separators between breadcrumb links.
    raw = m.group(1)
    parts = re.split(r"&nbsp;*(?:&gt;)?&nbsp;*|&gt;", raw)
    crumbs: list[str] = []
    for part in parts:
        text = html.unescape(re.sub(r"<[^>]+>", "", part)).strip()
        if not text or text == ">":
            continue
        # Drop structural crumbs and anything that is only 'Season N' / 'Episode N'.
        if re.fullmatch(r"(Season|Series|Part|Volume|Episode)\s*\d*", text):
            continue
        if text.lower() in CRUMB_NOISE:
            continue
        crumbs.append(text)
    return crumbs[-1].strip() if crumbs else ""


# --------------------------------------------------------------------------- #
# local subtitle parsing
# --------------------------------------------------------------------------- #
TIMESTAMP = re.compile(r"^\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->")


def parse_subtitle_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".srt", ".vtt"} or TIMESTAMP.search(text):
        text = re.sub(r"^WEBVTT.*", "", text)
        text = re.sub(r"^\d{2,}:.*$", "", text, flags=re.M)
        text = re.sub(r"^\d+$", "", text, flags=re.M)
        text = re.sub(r"<[^>]+>", "", text)

    lines: list[str] = []
    for raw in text.split("\n"):
        line = html.unescape(raw.replace("\u00a0", " "))
        line = re.sub(r"\[.*?\]", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        line = line.strip("-–— ").strip()
        if line and not TIMESTAMP.match(raw):
            lines.append(line)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# output
# --------------------------------------------------------------------------- #
def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9\-\.]+", "-", text).strip("-").lower() or "show"


def write_output(out_root: Path, show: str, code: str, title: str, text: str, source: str) -> dict:
    slug = safe_name(show)
    target_dir = out_root / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    txt_path = target_dir / f"{code}.txt"
    txt_path.write_text(text, encoding="utf-8")

    meta = {
        "show": show,
        "season": int(code[1:3]),
        "episode": int(code[4:6]),
        "code": code,
        "title": title,
        "source": source,
        "line_count": len(text.split("\n")),
        "char_count": len(text),
        "transcript_path": str(txt_path),
    }
    meta_path = target_dir / f"{code}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    meta["meta_path"] = str(meta_path)
    return meta


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch a TV episode transcript.")
    ap.add_argument("--show", help='show title, e.g. "Breaking Bad"')
    ap.add_argument("--season", type=int, help="season number")
    ap.add_argument("--episode", type=int, help="episode number")
    ap.add_argument("--code", help="episode code such as s01e01")
    ap.add_argument("--slug", help="skip search; use this springfieldspringfield slug")
    ap.add_argument("--list", action="store_true", help="list available episodes and exit")
    ap.add_argument("--file", type=Path, help="parse a local .srt/.vtt/.txt instead of fetching")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT_ROOT, help="output root dir")
    ap.add_argument("--stdout", action="store_true", help="print transcript instead of writing")
    ap.add_argument("--max-chars", type=int, default=0, help="truncate stdout output")
    args = ap.parse_args()

    code = args.code
    if not code and args.season and args.episode:
        code = f"s{args.season:02d}e{args.episode:02d}"
    if not args.show:
        ap.error("--show is required (or pass --file with an explicit --show)")

    if args.file:
        if not code:
            ap.error("--code (or --season/--episode) is required with --file")
        text = parse_subtitle_file(args.file)
        title = ""
        source = str(args.file)
    else:
        slug = resolve_slug(args.show, args.slug)
        if args.list:
            eps = episode_list(slug)
            print(json.dumps({"show": args.show, "slug": slug, "episodes": [asdict(e) for e in eps]},
                             ensure_ascii=False, indent=2))
            return 0
        if not code:
            ap.error("--code (or --season/--episode) is required")
        page = fetch(EPISODE_URL.format(slug=slug, code=code))
        if "scrolling-script-container" not in page:
            print(f"error: no script at {slug} {code}", file=sys.stderr)
            return 2
        text = extract_script(page)
        # The container is present even when a script is missing; catch the empty case.
        if len(dialogue_lines(text)) < 5:
            print(
                f"error: {args.show} {code} has no script text on the source site "
                f"(slug={slug}). Try another episode, or pass --file <subtitle>.",
                file=sys.stderr,
            )
            return 2
        title = episode_title_from_page(page, code)
        if not title:
            for ep in episode_list(slug):
                if ep.code == code:
                    title = ep.title
                    break
        source = EPISODE_URL.format(slug=slug, code=code)

    if args.stdout:
        out = text[: args.max_chars] if args.max_chars > 0 else text
        print(out)
        return 0

    meta = write_output(args.out, args.show, code, title, text, source)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())