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

from pathlib import Path  # noqa: E402

from stamp_and_verify import (  # noqa: E402
    GRANDFATHERED,
    chinese_field_problem,
    suspect_word,
    word_share,
)

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


# words list, expect_within_35pct_word_share
BALANCE_CASES = [
    # --- must fail the gate on a new episode ---
    ("全习语", ["go for a bowl", "bail someone out", "cut a deal"], False),
    (
        "习语压倒性",
        ["be on notice", "take the edge off", "grow some balls",
         "work us in", "zero in on", "slip through the cracks"],
        False,
    ),
    (
        "接近但不够",
        ["a bottleneck", "scale up", "manage expectations", "level with",
         "run into trouble", "the upside", "growing pains"],
        False,
    ),
    # --- must pass ---
    (
        "达标：六词四短语",
        ["waddle", "therapeutic", "efficacy", "holistic",
         "a PET scan", "an anti-emetic",
         "manage expectations", "the upside", "growing pains", "be bound to"],
        True,
    ),
    ("恰好踩线 7/20 = 35%", ["a", "b", "c", "d", "e", "f", "g"] + [f"w{i} x{i}" for i in range(13)], True),
    ("差一格 6/20 = 30%", ["a", "b", "c", "d", "e", "f"] + [f"w{i} x{i}" for i in range(14)], False),
]


def balance_fails(words: list[str]) -> bool:
    """Run the ratio check exactly as process() does, for a non-grandfathered file."""
    from stamp_and_verify import balance_problem

    return balance_problem(Path("hypothetical-s01e01.json"), [{"word": w} for w in words]) is not None

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

    for label, words, want_pass in BALANCE_CASES:
        failed = balance_fails(words)
        if failed == want_pass:
            failures.append(
                f"  配比 {label}: expected pass={want_pass}, got pass={not failed}"
            )

    # The grandfather list is transcribed by hand and has twice been written
    # with the season/episode digits transposed (s02e01 for s01e02). Pin it to
    # the files that actually exist: every current file must be grandfathered
    # (so the gate never fires on shipped data) and nothing else may be listed.
    vocab_dir = Path(__file__).resolve().parents[3] / "data" / "vocab"
    if vocab_dir.is_dir():
        on_disk = {p.stem for p in vocab_dir.glob("*.json")}
        if GRANDFATHERED - on_disk:
            failures.append(
                f"  GRANDFATHERED 列了不存在的文件: {sorted(GRANDFATHERED - on_disk)}"
            )
        if on_disk - GRANDFATHERED:
            failures.append(
                f"  以下文件会撞上 35% 单词闸门，需加入 GRANDFATHERED: "
                f"{sorted(on_disk - GRANDFATHERED)}"
            )

    if failures:
        print("FAIL")
        print("\n".join(failures))
        return 1

    print(
        f"PASS  {len(CASES)} cases, {len(KNOWN_OVERFIRES)} known review prompts, "
        f"{len(CN_CASES)} chinese-field, {len(BALANCE_CASES)} balance"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())