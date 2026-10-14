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

from stamp_and_verify import chinese_field_problem, suspect_word  # noqa: E402

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

# label, entry, expect_flagged
CN_CASES = [
    # --- must be caught: English prose leaked into a Chinese field ---
    (
        "回归：释义里混进英文",
        {"meaning_cn": "「小蓝」——代购药Ingredients 的跑腿"},
        True,
    ),
    (
        "回归：例句结尾粘上英文",
        {"example_cn": "他做完了戒毒疗程，现在算改过自新了Pro tip。"},
        True,
    ),
    ("中文字段没写中文", {"quote_cn": "Yeah, he blew away."}, True),

    # --- must stay quiet: proper nouns are legitimate inside Chinese ---
    (
        "人名用空格隔开",
        {"quote_cn": "Walt，你把我关在门外的时候。"},
        False,
    ),
    (
        "外来词用空格隔开",
        {"quote_cn": "半数交易都是在 Taco Cabeza 谈成的。"},
        False,
    ),
    (
        "音标符号不算残留",
        {"meaning_cn": "一手交钱；现金预付（cash up front 说法）。"},
        False,
    ),
    (
        "中文口语借词不算残留",
        {"example_cn": "他们没接那个offer？那是他们亏了。"},
        False,
    ),
]

# The length rule deliberately over-fires so that long idioms get eyeballed.
# These are the known, accepted false positives.
KNOWN_OVERFIRES = [
    "not as far as I know",
    "this is going down the toilet",
    "take it back to the counter",
    "nudge something in the right direction",
    "have them by the short hairs",
    "burn the shit out of someone",
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

    for label, entry, want in CN_CASES:
        got = chinese_field_problem(label, entry) is not None
        if got != want:
            failures.append(
                f"  {label}: expected chinese-flagged={want}, got {got}"
            )

    if failures:
        print("FAIL")
        print("\n".join(failures))
        return 1

    print(
        f"PASS  {len(CASES)} cases, {len(KNOWN_OVERFIRES)} known review prompts, "
        f"{len(CN_CASES)} chinese-field cases"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())