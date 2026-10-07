---
name: TV English Vocabulary
description: 从美剧剧集中提取 B2–C1 词汇并导出 CSV（音标、词性、中英释义、剧中台词、例句）。当用户给出美剧剧集（如「绝命毒师 S1E1」「Breaking Bad 2x05」「看了一集《生活大爆炸》」）并想要背单词、学台词、导出生词表时使用。
metadata:
  opencode/autoinvoke: true
---

# 美剧生词本

Input is a show plus an episode. Output is a CSV of B2–C1 vocabulary mined from
that episode's transcript.

## Workflow

### 1. Parse the request

Resolve a show title and an episode code. Common inputs:

| User says | show | code |
| --- | --- | --- |
| `绝命毒师 第一季第一集` | `Breaking Bad` | `s01e01` |
| `Breaking Bad 2x05` | `Breaking Bad` | `s02e05` |
| `老友记 S01E01` | `Friends` | `s01e01` |
| `看了一集《继承之战》` | `Succession` | ask |
| `随便来一集现代家庭` | `Modern Family` | ask |

For a Chinese title, translate to the canonical English title. If the user did
not name an episode, ask for one rather than guessing; a full-season sweep is
a separate, much longer job and needs its own confirmation.

### 2. Fetch the transcript

```sh
python3 .opencode/skills/tv-english-vocab/scripts/fetch_transcript.py \
  --show "Breaking Bad" --season 1 --episode 1
```

Writes `data/transcripts/<show>/s01e01.txt` plus a `.json` sidecar with the
episode title, source URL, and line count.

Useful variations:

- `--show X --list` — show the available episode codes and titles.
- `--code s03e11` — instead of `--season`/`--episode`.
- `--slug <slug>` — when show matching picks the wrong show (the US/UK split
  is the usual culprit, e.g. `the-office-us` vs `the-office-uk`).
- `--file path/to.srt --show X --code s01e01` — use a subtitle file the user
  downloaded instead of the online source.
- `--stdout --max-chars 6000` — read the text directly without writing files.

**When fetching fails** the script says which slug and code it tried. Common
causes: the show is not on the source site (try `--file` with a subtitle), the
episode has no script (try another), or a Cloudflare-style block (try
`--file`). Report the failure plainly; do not invent a transcript.

### 3. Select the vocabulary

Read `references/selection-criteria.md` and apply it. The whole transcript is
usually 300–900 lines, so read it in full with the Read tool rather than
sampling. Expect 20–35 entries, roughly 60/40 B2 to C1.

Never invent a quote. Every `quote` must appear verbatim in the transcript
file. If you want a line you cannot find, drop the entry.

### 4. Write the vocabulary JSON

Save to `data/vocab/<show>-<code>.json` as a JSON list:

```json
[
  {
    "word": "burn the candle at both ends",
    "phonetic": "/ˌbɜːn ðə ˈkændl æt boʊθ endz/",
    "pos": "phr. v.",
    "level": "C1",
    "meaning_en": "to overwork yourself by burning energy at night and day",
    "meaning_cn": "过度消耗精力；起早贪黑",
    "quote": "Listen, Walt, you're burning the candle at both ends.",
    "quote_cn": "听着，沃尔特，你这样把自己耗得太狠了。",
    "scene": "Skyler to Walt, kitchen",
    "example": "If you burn the candle at both ends like this, you'll burn out by thirty.",
    "example_cn": "你要是这样两头烧，三十岁就熬垮了。",
    "note": "近义：overextend oneself。show 中为口语化劝告，非字面蜡烛。"
  }
]
```

Required: `word`, `phonetic`, `pos`, `meaning_cn`, `meaning_en`, `level`.
Recommended: `quote`, `quote_cn`, `scene`, `example`, `example_cn`, `note`.
`level` must be exactly `B2` or `C1`.

### 5. Export to CSV

```sh
python3 .opencode/skills/tv-english-vocab/scripts/export_vocab.py \
  data/vocab/breaking-bad-s01e01.json -o data/vocab/breaking-bad-s01e01.csv
```

The exporter validates required fields, rejects levels other than B2/C1,
normalizes the IPA, and writes UTF-8 with a BOM so Excel opens the Chinese
columns correctly.

To build one growing vocabulary across many episodes, merge instead:

```sh
python3 .opencode/skills/tv-english-vocab/scripts/export_vocab.py \
  data/vocab/breaking-bad-s02e03.json --merge data/vocab/my-vocabulary.csv
```

Matching is case-insensitive on `word`, so re-running the same episode does not
create duplicates. `--tsv` writes tab-separated instead, for Anki imports.

### 6. Stamp episode metadata (required for the app)

The vocabulary JSON must carry `code`, `show`, `episode_title`, `season`,
`episode_num`, and `source_url`. Copy them from the transcript sidecar so the
app can group and label everything:

```sh
python3 - <<'PY'
import json, pathlib
side = json.loads(pathlib.Path('data/transcripts/breaking-bad/s01e01.json').read_text())
p = pathlib.Path('data/vocab/breaking-bad-s01e01.json')
words = json.loads(p.read_text())
for w in words:
    w.update(code=side['code'], show=side['show'],
             episode_title=side['title'], season=side['season'],
             episode_num=side['episode'], source_url=side['source'])
p.write_text(json.dumps(words, ensure_ascii=False, indent=2))
PY
```

Skip this only if the user explicitly asked for CSV alone.

### 7. Build the mobile app

```sh
python3 .opencode/skills/tv-english-vocab/scripts/build_app.py --out site
```

Reads every `data/vocab/*.json` plus its transcript and emits a self-contained
static site to `site/`: flashcard deck, searchable list, tap-to-look-up
transcript, and progress stats. It picks up all previously extracted episodes,
so the deck grows as more are processed.

Useful flags: `--no-script` omits transcripts (much smaller bundle),
`--generated "<timestamp>"` stamps the build time shown in the app,
`--show` prints the output tree with file sizes.

Then tell the user `site/index.html` opens directly in any browser, no server
needed.

### 8. Deploy to GitHub Pages (only when asked)

```sh
bash .opencode/skills/tv-english-vocab/scripts/deploy_pages.sh
```

Builds, commits, pushes `site/` to the `gh-pages` branch, and enables Pages.
Use `--repo owner/name` for an existing repo, `--no-push` to build only.

This publishes to a **public URL** — free GitHub Pages does not support private
repos. Confirm with the user before the first deploy and before adding any
episode they would not want public.

### 9. Report back

Tell the user:

- where the CSV is
- how many entries, split B2 / C1
- the show, episode code, episode title, and source URL
- the 5 most useful or interesting items, inline, so they can start studying
  without opening the file
- that the app is at `site/index.html`, or the live URL if deployed

Then offer the obvious follow-up: the next episode, or a merged master
vocabulary.

## Notes

- Do not modify `fetch_transcript.py`, `export_vocab.py`, `build_app.py`, or the
  files under `web/` during a normal run. If a site layout changes, fix the
  parser and say what you changed. `build_app.py` also copies `web/` verbatim,
  so app restyling is an edit to the templates, not to `site/`.
- `site/` is generated. Never hand-edit it; rebuild instead.
- After changing `web/assets/app.js` or `sw.js`, bump the `CACHE` constant in
  `sw.js`. Cache-first means phones keep serving the old build otherwise.
- Episode scripts on the source site are user-uploaded and sometimes contain
  transcription errors. Quote them as-is and flag real errors in `note`.
- Vocabulary should come from **this** episode's transcript. Do not pad the
  list with well-known words just because they are likely to appear.