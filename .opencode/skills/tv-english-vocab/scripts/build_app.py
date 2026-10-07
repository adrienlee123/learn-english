#!/usr/bin/env python3
"""Build a static, offline-capable study app from the extracted vocabulary.

Reads every data/vocab/*.json plus its matching transcript, then writes a
self-contained site to --out (default: site/). No network, no build toolchain:
open dist/index.html directly, or serve it, or push it to GitHub Pages.

Usage
-----
  build_app.py                              # writes ./site
  build_app.py --out dist
  build_app.py --no-script                  # skip transcripts (smaller bundle)
  build_app.py --out dist --show           # print the tree + sizes
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEB = HERE.parent / "web"
DEFAULT_VOCAB_DIR = Path("data/vocab")
DEFAULT_TRANSCRIPT_DIR = Path("data/transcripts")

# A transcript is dialogue-heavy; beyond this the mobile page gets sluggish.
MAX_SCRIPT_LINES = 2200
# Only link words that are plausibly content vocabulary.
TAPABLE = re.compile(r"^[A-Za-z][A-Za-z'-]*$")


def safe_name(text: str) -> str:
    """Match fetch_transcript.write_output's directory naming."""
    return re.sub(r"[^A-Za-z0-9\-\.]+", "-", text).strip("-").lower() or "show"


STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "to", "of", "for", "with", "and", "or",
    "but", "if", "as", "by", "from", "up", "out", "off", "over", "under", "no",
    "not", "my", "your", "his", "her", "its", "their", "this", "that", "these",
    "those", "is", "are", "was", "were", "be", "been", "it", "you", "i", "we",
}


def lemma(word: str) -> str:
    """Single-word lemma so 'agreed' and 'agree' resolve together in the script.

    Returns "" when the entry cannot be linked from a transcript token: function
    words, very short forms, and multi-word phrases whose head is a stopword
    (e.g. 'in custody' must not highlight every 'in' in the episode).
    """
    raw = word.lower().strip()
    head = re.sub(r"[^a-z'-]", "", raw.split()[0] if raw.split() else raw).strip("-")
    if len(head) < 4 or head in STOPWORDS:
        return ""

    if " " in raw or "-" in raw.strip("- "):
        # Multi-word phrase: only link on the head word.
        return head

    if not head.isalpha():
        return ""
    w = head
    for suf in ("ies", "ing", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            if suf == "ies":
                return w[: -len("ies")] + "y"
            if suf == "ing":
                base = w[: -len("ing")]
                # 'running' -> 'run', 'stopping' -> 'stop'
                return base + base[-1] if len(base) > 2 and base[-1] == base[-2] else base
            return w[: -len(suf)]
    return w


def slug_dir(episode_key: str) -> str:
    return episode_key.split("|")[0]


def load_sidecars(transcript_dir: Path) -> dict:
    """Episode metadata written by fetch_transcript.py, keyed by SxxExx code."""
    out: dict[str, dict] = {}
    if not transcript_dir.exists():
        return out
    for p in transcript_dir.glob("*/*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if d.get("code"):
            out[d["code"]] = d
    return out


def load_vocab(vocab_dir: Path) -> list[dict]:
    if not vocab_dir.exists():
        return []
    out = []
    for p in sorted(vocab_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"warn: skipping {p} ({exc})", file=sys.stderr)
            continue
        if isinstance(data, dict):
            data = data.get("words", [])
        out.extend(data)
    return out


def build_episodes(
    words: list[dict], transcript_dir: Path, with_script: bool
) -> tuple[list, list]:
    episodes: list[dict] = []
    flat: list[dict] = []
    seen: set[str] = set()
    meta_by_code = load_sidecars(transcript_dir)

    for w in words:
        code = w.get("code") or w.get("episode_code") or ""
        if not code or code in seen:
            continue
        seen.add(code)

        side = meta_by_code.get(code, {})
        show = w.get("show") or side.get("show") or ""
        ep_title = w.get("episode_title") or side.get("title") or ""
        season = w.get("season", side.get("season"))
        ep_num = w.get("episode_num", side.get("episode"))

        label = " · ".join(x for x in (show, ep_title or code) if x) or code
        ep = {
            "key": code,
            "code": code,
            "show": show,
            "title": label,
            "short": (show + " " + code).strip() if show else code,
            "season": season,
            "episode": ep_num,
            "sourceUrl": w.get("source_url") or side.get("source") or "",
            "lines": [],
        }
        if with_script:
            for cand in (slug_dir(code), safe_name(show)):
                tp = transcript_dir / cand / f"{code}.txt"
                if tp.exists():
                    lines = tp.read_text(encoding="utf-8").split("\n")
                    ep["lines"] = [ln for ln in lines if ln.strip()][:MAX_SCRIPT_LINES]
                    break
        episodes.append(ep)

    # Ensure every word carries the fields the UI expects.
    for w in words:
        code = w.get("code") or w.get("episode_code") or ""
        head = w.get("word", "").strip()
        if not code or not head:
            continue
        side = meta_by_code.get(code, {})
        flat.append(
            {
                "key": f"{code}|{head.lower()}",
                "word": head,
                "lemma": lemma(head),
                "phonetic": w.get("phonetic", ""),
                "pos": w.get("pos", ""),
                "level": str(w.get("level", "B2")).upper(),
                "meaning_en": w.get("meaning_en", ""),
                "meaning_cn": w.get("meaning_cn", ""),
                "quote": w.get("quote", ""),
                "quote_cn": w.get("quote_cn", ""),
                "example": w.get("example", ""),
                "example_cn": w.get("example_cn", ""),
                "note": w.get("note", ""),
                "scene": w.get("scene", ""),
                "episodeKey": code,
                "episodeTitle": w.get("episode_title") or side.get("title") or "",
            }
        )
    return episodes, flat


def write_site(out: Path, payload: dict, with_script: bool) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    shutil.copy2(WEB / "index.html", out / "index.html")
    shutil.copytree(WEB / "assets", out / "assets")
    shutil.copy2(WEB / "manifest.webmanifest", out / "manifest.webmanifest")
    shutil.copy2(WEB / "icon.svg", out / "icon.svg")
    if with_script:
        shutil.copy2(WEB / "sw.js", out / "sw.js")

    (out / "assets" / "data.js").write_text(
        "window.VOCAB_DB = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the static study app.")
    ap.add_argument("--vocab-dir", type=Path, default=DEFAULT_VOCAB_DIR)
    ap.add_argument("--transcript-dir", type=Path, default=DEFAULT_TRANSCRIPT_DIR)
    ap.add_argument("--out", type=Path, default=Path("site"))
    ap.add_argument("--no-script", action="store_true", help="omit transcripts")
    ap.add_argument("--generated", default="", help="timestamp string stored in the app")
    ap.add_argument("--show", action="store_true", help="print resulting tree and sizes")
    args = ap.parse_args()

    words = load_vocab(args.vocab_dir)
    if not words:
        print(
            f"error: no vocabulary found in {args.vocab_dir}. Run fetch_transcript.py "
            "and export_vocab.py first.",
            file=sys.stderr,
        )
        return 1

    episodes, flat = build_episodes(words, args.transcript_dir, not args.no_script)
    if not flat:
        print("error: vocabulary entries lack 'code'/'word' fields", file=sys.stderr)
        return 1

    payload = {
        "generated": args.generated or None,
        "episodes": episodes,
        "words": flat,
    }
    write_site(args.out, payload, not args.no_script)

    script_lines = sum(len(ep["lines"]) for ep in episodes)
    print(
        json.dumps(
            {
                "output": str(args.out),
                "words": len(flat),
                "episodes": len(episodes),
                "transcript_lines": script_lines,
                "total_bytes": sum(f.stat().st_size for f in args.out.rglob("*") if f.is_file()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.show:
        for f in sorted(args.out.rglob("*")):
            if f.is_file():
                print(f"  {f.stat().st_size:>9,}  {f.relative_to(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())