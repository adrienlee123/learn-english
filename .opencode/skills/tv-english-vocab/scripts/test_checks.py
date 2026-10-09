#!/usr/bin/env python3
"""Regression tests for the entry checks in stamp_and_verify.py.

Run: python3 .opencode/skills/tv-english-vocab/scripts/test_checks.py

These exist because a clause ("my arches happen to be extremely archy") once
slipped into the vocabulary disguised as a headword. The heuristic cannot be
exact, so the tests pin down which mistakes it must catch and which legitimate
idioms it must stay quiet about.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stamp_and_verify import suspect_word  # noqa: E402

# word, expect_flagged, why
CASES = [
    # --- must be caught ---
    ("my arches happen to be extremely archy", True, "回归用例：词头被误粘成整句"),
    ("her plan became impossible overnight", True, "所有格主语 + 谓语 = 命题"),
    ("his excuse turned out to be worthless", True, "所有格主语 + 谓语 = 命题"),
    ("a roomful / be touchy", True, "回归用例：两个词头粘在一个字段"),

    # --- must stay quiet ---
    ("arches", False, "修正后的正确词头"),
    ("buckle up", False, "祈使短语动词"),
    ("one step ahead", False, "固定短语"),
    ("inoperable", False, "单词"),
    ("a book come to life", False, "6 词但无可替换主语，是习语"),
    ("go our separate ways", False, "真短语"),
    ("be a dick about it", False, "真短语"),
    ("giant stick up his ass", False, "4 词，无所有格主语"),
    ("heart's in the right place", False, "所有格但不是「主语+谓语」"),
]

# The length rule deliberately over-fires so that long idioms get eyeballed.
# These are the known, accepted false positives.
KNOWN_OVERFIRES = [
    "not as far as I know",
    "this is going down the toilet",
    "take it back to the counter",
    "nudge something in the right direction",
    "have them by the short hairs",
]


def main() -> int:
    failures: list[str] = []
    for word, want, why in CASES:
        got = suspect_word(word, "") is not None
        if got != want:
            failures.append(f"  {word!r}: expected flagged={want}, got {got}  ({why})")

    for word in KNOWN_OVERFIRES:
        if suspect_word(word, "") is None:
            failures.append(
                f"  {word!r}: expected a review prompt from the length rule"
            )

    if failures:
        print("FAIL")
        print("\n".join(failures))
        return 1

    print(f"PASS  {len(CASES)} cases, {len(KNOWN_OVERFIRES)} known review prompts")
    return 0


if __name__ == "__main__":
    sys.exit(main())