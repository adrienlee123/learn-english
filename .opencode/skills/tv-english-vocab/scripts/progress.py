#!/usr/bin/env python3
"""Track vocabulary extraction progress across a show, in episode order.

Run from the project root:

  python3 .opencode/skills/tv-english-vocab/scripts/progress.py breaking-bad

Shows, for every episode the source site lists, whether the transcript was
fetched and whether vocabulary has been extracted. Next unprocessed episode is
printed last so a session can resume without re-deriving anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_transcript as ft  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("show", help="show title, e.g. breaking-bad")
ap.add_argument("--root", type=Path, default=Path("data/transcripts"))
args = ap.parse_args()

slug = ft.resolve_slug(args.show)
eps = ft.episode_list(slug)

vocab_keys = set()
for p in Path("data/vocab").glob("*.json"):
    try:
        for e in json.loads(p.read_text(encoding="utf-8")):
            if isinstance(e, dict) and e.get("code"):
                vocab_keys.add((ft.safe_name(e.get("show", "")), e["code"]))
    except json.JSONDecodeError:
        pass

done = missing = todo = 0
rows = []
for e in eps:
    code = e.code
    fetched = (args.root / slug / f"{code}.txt").exists()
    extracted = (slug, code) in vocab_keys
    if extracted:
        state, done = "done", done + 1
    elif fetched:
        state, todo = "todo", todo + 1
    else:
        state, missing = "no-script", missing + 1
    rows.append((code, state, e.title, len((args.root / slug / f"{code}.txt").read_text(
        encoding="utf-8").split("\n")) if fetched else 0))

print(f"\n{args.show}  (slug={slug})  源站 {len(eps)} 集\n")
for code, state, title, lines in rows:
    mark = {"done": "✓", "todo": "·", "no-script": "—"}[state]
    pad = "  " if state != "todo" else ""
    print(f" {mark} {code}  {title[:44]:46}{lines:>5}行{pad}")

nxt = next((c for c, s, _, _ in rows if s == "todo"), None)
print(f"\n已抽 {done} | 待抽 {todo} | 源站无剧本 {missing}")
print(f"下一集: {nxt or '（本剧已全部抽完）'}")