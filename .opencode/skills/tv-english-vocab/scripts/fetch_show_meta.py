#!/usr/bin/env python3
"""Fetch show metadata and cover art from TVmaze (no API key required).

Reads every transcript sidecar, resolves the show title against TVmaze, and
downloads a portrait cover per show into data/covers/. The result is an
index.json that build_app.py embeds and copies into the site.

Covers are stored locally on purpose: the app is offline-first, and a service
worker cannot cache third-party images reliably.

Usage
-----
  fetch_show_meta.py                 # resolve + download anything missing
  fetch_show_meta.py --refresh       # re-download covers that already exist
  fetch_show_meta.py --dry-run       # only report the TVmaze matches
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SEARCH_URL = "https://api.tvmaze.com/singlesearch/shows?q={q}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

TRANSCRIPT_DIR = Path("data/transcripts")
COVER_DIR = Path("data/covers")


def get(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.tvmaze.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def safe_name(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-." else "-" for c in text).strip("-").lower() or "show"


def shows_from_sidecars(transcript_dir: Path) -> dict[str, set[str]]:
    """show name -> set of episode codes, taken from the fetch sidecars."""
    out: dict[str, set[str]] = {}
    for p in sorted(transcript_dir.glob("*/*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        show = (d.get("show") or "").strip()
        if show and d.get("code"):
            out.setdefault(show, set()).add(d["code"])
    return out


def lookup(show: str) -> dict | None:
    url = SEARCH_URL.format(q=urllib.parse.quote(show))
    try:
        data = json.loads(get(url).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"warn: TVmaze lookup failed for {show!r}: {exc}", file=sys.stderr)
        return None
    image = data.get("image") or {}
    return {
        "title": data.get("name", show),
        "year": (data.get("premiered") or "")[:4],
        "genres": data.get("genres") or [],
        "cover": image.get("medium") or image.get("original") or "",
        "tvmaze": (data.get("urls") or {}).get("tv", ""),
        "status": data.get("status", ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch show covers from TVmaze.")
    ap.add_argument("--transcript-dir", type=Path, default=TRANSCRIPT_DIR)
    ap.add_argument("--cover-dir", type=Path, default=COVER_DIR)
    ap.add_argument("--refresh", action="store_true", help="re-download existing covers")
    ap.add_argument("--dry-run", action="store_true", help="report matches, download nothing")
    args = ap.parse_args()

    shows = shows_from_sidecars(args.transcript_dir)
    if not shows:
        print(f"error: no transcript sidecars under {args.transcript_dir}", file=sys.stderr)
        return 1

    args.cover_dir.mkdir(parents=True, exist_ok=True)
    index_path = args.cover_dir / "index.json"
    index: dict = {}
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))

    for show, codes in sorted(shows.items()):
        meta = lookup(show)
        if not meta or not meta["cover"]:
            print(f"  skip  {show}: no TVmaze image")
            continue

        slug = safe_name(show)
        entry = index.get(slug, {})
        entry.update(
            slug=slug,
            show=show,
            title=meta["title"],
            year=meta["year"],
            genres=meta["genres"],
            tvmaze=meta["tvmaze"],
            episodes=sorted(codes),
        )

        local = args.cover_dir / f"{slug}.jpg"
        if args.dry_run:
            print(f"  match {show:24} -> {meta['title']} ({meta['year']})  {meta['cover']}")
        elif args.refresh or not local.exists():
            try:
                local.write_bytes(get(meta["cover"]))
                entry["cover_file"] = f"{slug}.jpg"
                entry["cover_bytes"] = local.stat().st_size
                print(f"  saved {show:24} -> {local.name} ({entry['cover_bytes']:,} bytes)")
            except Exception as exc:  # noqa: BLE001
                print(f"  warn  {show}: download failed ({exc})", file=sys.stderr)
                entry["cover_file"] = None
                continue
        else:
            entry["cover_file"] = local.name
            entry["cover_bytes"] = local.stat().st_size
            print(f"  cached {show:24} -> {local.name}")

        index[slug] = entry
        time.sleep(0.4)  # be polite to the public API

    if not args.dry_run:
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"shows": len(index), "index": str(index_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())