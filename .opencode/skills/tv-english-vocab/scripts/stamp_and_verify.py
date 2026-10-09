#!/usr/bin/env python3
"""Validate vocabulary JSON against its transcript, then fill in episode metadata.

Two jobs, both of which should happen before exporting:

1. Verify every `quote` appears verbatim in the episode transcript. Catches
   invented quotations and transcript/JSON drift.
2. Fill `code`, `show`, `episode_title`, `season`, `episode_num`, and
   `source_url` from the sidecar written by fetch_transcript.py. The app groups
   and labels everything from these fields.

Usage
-----
  stamp_and_verify.py                      check + stamp every file in data/vocab
  stamp_and_verify.py data/vocab/bb.json  check one file
  stamp_and_verify.py --check-only         verify without writing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

VOCAB_DIR = Path("data/vocab")
TRANSCRIPT_DIR = Path("data/transcripts")

META_KEYS = ("code", "show", "show_slug", "episode_title", "season", "episode_num", "source_url")


def safe_name(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-." else "-" for c in text).strip("-").lower() or "show"


def episode_key(show: str, code: str) -> str:
    """Globally unique id. Codes repeat across shows: s01e01 is not unique."""
    return f"{safe_name(show)}|{code}" if show else code


def load_sidecars(transcript_dir: Path) -> dict[tuple[str, str], dict]:
    """Keyed by (show_slug, code) so two shows' s01e01 never collide."""
    out: dict[tuple[str, str], dict] = {}
    for p in sorted(transcript_dir.glob("*/*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        code = d.get("code")
        if code:
            out[(safe_name(d.get("show", "")), code)] = d
    return out


def transcript_text(transcript_dir: Path, code: str, show: str) -> str | None:
    if show:
        p = transcript_dir / safe_name(show) / f"{code}.txt"
        if p.exists():
            return p.read_text(encoding="utf-8")
    # Fall back to any transcript whose filename matches the code.
    hits = sorted(transcript_dir.glob(f"*/{code}.txt"))
    return hits[0].read_text(encoding="utf-8") if hits else None


def suspect_word(word: str, quote: str) -> str | None:
    """Heuristic: does this `word` look like a stored clause rather than a chunk?

    Returns a reason string, or None. These are REVIEW CANDIDATES, not errors:
    the heuristic cannot separate a frozen idiom from a pasted sentence, so a
    human or the agent must confirm each one. The signature of the real failure
    is a lexical subject plus a finite verb — i.e. the entry is a proposition
    about something rather than a reusable expression.
    """
    w = word.strip()
    toks = w.split()

    # A lexical (possessive) subject directly followed by a finite verb:
    # "my arches happen to be..." is a sentence; "buckle up" is a chunk.
    m = re.match(
        r"^(my|his|her|its|our|their|your)\s+\S+\s+"
        r"(happen|happens|happened|seem|seems|seemed|became|become|becomes|"
        r"means|meant|turned|turns|cost|costs|sold|sells|was|were|is|are)\b",
        w,
        re.I,
    )
    if m and len(toks) >= 4:
        return f"词头带「{m.group(1)} + 名词 + 谓语」，像小句而非可储存的块"

    # A very long headword: real chunks rarely exceed five words.
    if len(toks) >= 6:
        return f"词头 {len(toks)} 词，超出短语常见长度（需人工确认是否为整句）"

    # A slash means two headwords were pasted into one field, as happened with
    # "a roomful / be touchy", whose phonetic and gloss only covered "touchy".
    if "/" in w.strip():
        parts = [s.strip() for s in w.split("/") if s.strip()]
        return f"词头用「/」拼接了 {len(parts)} 个条目（{' / '.join(parts)}），应拆开"

    return None


def audit(path: Path, entries: list[dict]) -> list[tuple[str, str]]:
    """Return (word, reason) for entries a human should look at."""
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        word = str(e.get("word", ""))
        reason = suspect_word(word, str(e.get("quote", "")))
        if reason:
            out.append((word, reason))
    return out


def process(path: Path, sides: dict, transcript_dir: Path, check_only: bool) -> list[str]:
    problems: list[str] = []
    try:
        words = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON ({exc})"]

    if isinstance(words, dict):
        words = words.get("words", [])
    if not isinstance(words, list) or not words:
        return [f"{path.name}: empty or malformed vocabulary"]

    texts: dict[str, str | None] = {}
    changed = False

    for i, w in enumerate(words):
        word = w.get("word", "")
        code = w.get("code", "")
        show = w.get("show", "")
        if not code:
            return [f"{path.name}: entry #{i + 1} ({word or '?'}) has no 'code'; run the skill from step 3"]
        if not show:
            return [
                f"{path.name}: entry #{i + 1} ({word}) has no 'show'; "
                f"{code} is ambiguous across series"
            ]

        side = sides.get((safe_name(show), code))
        if side is None:
            problems.append(f"{path.name}: no transcript sidecar for {show} {code}")
            continue

        ekey = episode_key(show, code)
        if ekey not in texts:
            texts[ekey] = transcript_text(transcript_dir, code, show)
        text = texts[ekey]
        if text is None:
            problems.append(f"{path.name}: no transcript file for {show} {code}")
            continue

        quote = (w.get("quote") or "").strip()
        if quote:
            if quote not in text:
                problems.append(
                    f"{path.name}: quote not found verbatim in {show} {code}: {quote[:70]!r}"
                )
        elif side.get("title"):
            problems.append(f"{path.name}: entry #{i + 1} ({word}) has no quote")

        level = str(w.get("level", "")).upper()
        if level not in {"B2", "C1"}:
            problems.append(f"{path.name}: entry #{i + 1} ({word}) has level {level!r}, expected B2 or C1")

        wanted = {
            "code": code,
            "show": side.get("show", show),
            "show_slug": safe_name(side.get("show", show)),
            "episode_title": side.get("title", ""),
            "season": side.get("season"),
            "episode_num": side.get("episode"),
            "source_url": side.get("source", ""),
        }
        for k, v in wanted.items():
            if v not in (None, "") and w.get(k) != v:
                w[k] = v
                changed = True

    if changed and not check_only:
        path.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify quotes and stamp episode metadata.")
    ap.add_argument("files", nargs="*", type=Path, help="vocab JSON files (default: all of data/vocab)")
    ap.add_argument("--vocab-dir", type=Path, default=VOCAB_DIR)
    ap.add_argument("--transcript-dir", type=Path, default=TRANSCRIPT_DIR)
    ap.add_argument("--check-only", action="store_true", help="verify without writing")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="treat review candidates as failures instead of warnings",
    )
    args = ap.parse_args()

    files = args.files or sorted(args.vocab_dir.glob("*.json"))
    if not files:
        print(f"error: no vocabulary files under {args.vocab_dir}", file=sys.stderr)
        return 1

    sides = load_sidecars(args.transcript_dir)
    all_problems: list[str] = []
    review: list[tuple[str, str]] = []
    total = 0
    for f in files:
        probs = process(f, sides, args.transcript_dir, args.check_only)
        entries = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(entries, dict):
            entries = entries.get("words", [])
        flagged = audit(f, entries)
        review += [(w, r, f.name) for w, r in flagged]
        total += 1
        if probs:
            all_problems.extend(probs)
            print(f"FAIL {f.name} ({len(entries)} entries)")
        else:
            verb = "checked" if args.check_only else "stamped"
            mark = f"  [{len(flagged)} to review]" if flagged else ""
            print(f"  ok {f.name}  {verb} {len(entries)} entries{mark}")

    if review:
        print("\nNeeds review — confirm each is a reusable chunk, not a sentence:")
        for w, r, fname in review:
            print(f"  - {w!r}  ({fname})\n      {r}", file=sys.stderr)
        if args.strict:
            print(
                "\nstrict mode: treating review candidates as failures.",
                file=sys.stderr,
            )
            return 1

    if all_problems:
        print("\nProblems:", file=sys.stderr)
        for p in all_problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(f"\n{len(files)} file(s) verified; every quote is verbatim.")
    if review:
        print(f"{len(review)} entr{'y' if len(review)==1 else 'ies'} still need a human decision.")
    return 0


if __name__ == "__main__":
    sys.exit(main())