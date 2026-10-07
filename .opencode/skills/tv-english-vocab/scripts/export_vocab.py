#!/usr/bin/env python3
"""Turn a vocabulary JSON file into a UTF-8 (BOM) CSV for Excel / Numbers.

Input JSON: either a bare list of entries or an object with a "words" list.

    [
      {
        "word": "game the system",
        "phonetic": "/ɡeɪm ðə ˈsɪstəm/",
        "pos": "phr. v.",
        "meaning_cn": "钻空子牟利",
        "meaning_en": "to exploit rules or loopholes for personal gain",
        "level": "C1",
        "quote": "I'm not in the business of breaking the law. I'm game the system.",
        "quote_cn": "我不是干违法的，我是钻规则的空子。",
        "example": "If you game the system like that, eventually it catches up with you.",
        "example_cn": "你要是那样钻空子，迟早要出事。",
        "note": "原文引文疑似字幕误差，正确说法是 game the system。"
      }
    ]

Required keys: word, phonetic, pos, meaning_cn, meaning_en, level.
Optional: quote, quote_cn, example, example_cn, note.

Usage
-----
  export_vocab.py vocab.json                        # writes vocab.csv next to it
  export_vocab.py vocab.json -o out/breaking-bad.csv
  export_vocab.py vocab.json --merge out/all.csv    # append, skipping words already there
  export_vocab.py vocab.json --tsv                  # tab-separated for Anki
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

COLUMNS = [
    ("word", "Word / Phrase"),
    ("phonetic", "Phonetic (IPA)"),
    ("pos", "Part of Speech"),
    ("level", "CEFR Level"),
    ("meaning_en", "Definition (EN)"),
    ("meaning_cn", "释义（中文）"),
    ("quote", "Quote from Episode"),
    ("quote_cn", "台词翻译"),
    ("example", "Example Sentence"),
    ("example_cn", "例句翻译"),
    ("note", "Usage Note"),
]

REQUIRED = ["word", "phonetic", "pos", "meaning_cn", "meaning_en", "level"]

VALID_LEVELS = {"B2", "C1"}


def load(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("words", data.get("entries", []))
    if not isinstance(data, list):
        raise SystemExit(f"{path}: expected a JSON list of entries")
    return data


def normalize(entry: dict, index: int) -> dict:
    row: dict[str, str] = {}
    missing = [k for k in REQUIRED if not str(entry.get(k, "")).strip()]
    if missing:
        raise SystemExit(f"entry #{index} ({entry.get('word', '?')}) missing: {', '.join(missing)}")

    level = str(entry["level"]).strip().upper()
    if level not in VALID_LEVELS:
        raise SystemExit(f"entry #{index} ({entry['word']}): level must be B2 or C1, got {level!r}")

    for key, _ in COLUMNS:
        value = entry.get(key, "")
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value)
        row[key] = str(value).strip()

    row["phonetic"] = normalize_phonetic(row["phonetic"], row["word"])
    return row


def normalize_phonetic(value: str, word: str) -> str:
    """Strip stress marks/slashes some models add; keep the IPA itself intact."""
    text = value.strip()
    for prefix in ("ipa:", "ipa ", "UK:", "US:", "UK ", "US "):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix) :].strip()
    text = text.strip().strip("/[]").strip()
    # Some sources space-pad the IPA: "[ kəˈlestərɒl ]" -> "kəˈlestərɒl"
    text = re.sub(r"\s+", " ", text)
    if not text:
        raise SystemExit(f"{word}: phonetic is empty after normalization")
    return f"/{text}/"


def merge_into(existing: Path, rows: list[dict], delimiter: str) -> tuple[list[dict], int]:
    """Read an existing export, then append new rows, skipping words already present."""
    if not existing.exists() or existing.stat().st_size == 0:
        return rows, 0

    with existing.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        records = [r for r in reader if any(cell.strip() for cell in r)]

    if not records:
        return rows, 0

    header, body = records[0], records[1:]
    # Map the written header labels back to our keys so old files still merge.
    label_to_key = {label: key for key, label in COLUMNS}
    keys = [label_to_key.get(cell.strip(), cell.strip()) for cell in header]

    # Refuse to merge into a file we do not recognise: treating a data row as a
    # header would silently drop every column.
    if "word" not in keys:
        raise SystemExit(
            f"{existing}: header does not look like a vocabulary export "
            f"(missing 'Word / Phrase'). Merge into a file created by this script."
        )

    current = [dict(zip(keys, rec)) for rec in body]
    seen = {r.get("word", "").strip().lower() for r in current}

    added, skipped = [], 0
    for row in rows:
        key = row["word"].strip().lower()
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        added.append(row)
    return current + added, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description="Export vocabulary JSON to CSV/TSV.")
    ap.add_argument("vocab", type=Path, help="vocabulary JSON file")
    ap.add_argument("-o", "--out", type=Path, help="output path (default: <vocab>.csv)")
    ap.add_argument("--tsv", action="store_true", help="write tab-separated instead of comma")
    ap.add_argument("--merge", type=Path, help="append into an existing CSV/TSV, skipping duplicates")
    args = ap.parse_args()

    entries = load(args.vocab)
    rows = [normalize(e, i + 1) for i, e in enumerate(entries)]

    delimiter = "\t" if args.tsv else ","
    out = args.out or args.vocab.with_suffix(".tsv" if args.tsv else ".csv")

    skipped = 0
    if args.merge:
        rows, skipped = merge_into(args.merge, rows, delimiter)
        out = args.merge

    out.parent.mkdir(parents=True, exist_ok=True)

    # utf-8-sig so Excel on Windows/macOS shows Chinese text correctly.
    # A merge rewrites the whole file from `rows`, so the header is always
    # re-emitted. Omitting it here used to corrupt the *next* merge, which then
    # read a data row as the header and blanked every column.
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        writer.writerow([label for _, label in COLUMNS])
        for row in rows:
            writer.writerow([row.get(key, "") for key, _ in COLUMNS])

    print(
        json.dumps(
            {
                "output": str(out),
                "entries_written": len(rows),
                "duplicates_skipped": skipped,
                "format": "tsv" if args.tsv else "csv",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())