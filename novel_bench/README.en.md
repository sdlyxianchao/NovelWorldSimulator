# NovelBench · Novel Simulation Quality Benchmark

> An evaluation harness that lives outside the app's runtime: take a real novel's setting bible
> and a cut point, let the simulator continue from there, then compare its output against what the
> author actually wrote — with **counters and a blind judge**, not vibes.
>
> 中文: [README.md](README.md)

---

## 1. Why it exists

Every change to a prompt, a scheduler or an export path raises the same question: **did it get better
or worse?** Reading a few transcripts by hand does not answer it — that is exactly how "the same
action replayed 61–87% of the time" and "4-gram repetition is 20x human" went unnoticed.

This tool turns "better or worse" into reproducible numbers:

| Question | What the harness reports |
|---|---|
| Does the prose read like a human wrote it? | 4-gram repetition, sentence-length spread, near-duplicate lines, leaked meta-marks, **choppy / breathless paragraphs** — each against a human baseline |
| Is it spinning on the same prop? | **Prop cycle** (one object repeatedly refilled and drained). Human maximum is 0 |
| Is the formatting consistent? | **Mixed quote styles** (ASCII and Chinese quotes in one piece; a single style costs nothing) |
| Do characters sound like themselves? | "Character" dimension in the blind review, plus cast coverage and dialogue ratio |
| Does it break the original? | Canon-consistency dimension, plus taboo/anachronism counts |
| How far is it from real fiction? | The **same rubric** scores both the transcript and the author's text; the report shows the **gap** |
| Was this optimisation worth it? | `compare` prints per-case deltas between two runs |

## 2. Three design decisions

1. **Reference-anchored, not absolute.** Every case scores the author's own continuation with the
   same rubric. The headline number is `gap = sim − reference`, because absolute scores drift
   between judge models and between weeks.
2. **Blind pairwise.** Transcript and reference are shown as A/B in both orders; a win requires the
   judge to pick the same text twice, otherwise it counts as a tie. Cheapest known defence against
   position bias.
3. **Judge `小说原文`, not `小说版本`.**
   `导出/小说版本_*.md` says of itself "**this is a source draft, not a finished piece**" and
   **deliberately keeps** script markers (`▸ 出场`, `◇ 心声`, `**场景**`); judging it turns
   "by design" into "30 leaked meta-marks" and depresses every score. Use
   `导出/小说原文_*.md` (the novelist's own text, no script markers). Order: 原文 → 当天故事 →
   版本 → daily dumps. Found only after the first A/B run on 2026-10-18.
3b. **Counters as a floor.** Judges get tired, drift, and are impressed by length; counters do not.
   Repetition, taboo words, idle beats and cast coverage are always reported alongside the judge.

## 2.5 Stance: an idea generator, not a fidelity test

> The user's words: **"this software exists to give authors ideas; it does not try to match the
> original text. Reasonable variation is an important feature."**

That sentence governs the whole rubric. The first version violated it (asking "is this a good
*continuation*", treating `gap` as the primary metric, counting "new character" as a conflict);
all of that is now corrected:

| Item | How it is scored now |
|---|---|
| `canon` | deducts only for **violations** (world rules / period / forms of address / established facts); **new people, places and subplots are not penalised** |
| `plot` | only asks whether this passage works **on its own** (setup, turn, landing); fidelity to the original is irrelevant |
| **`novelty` (weight 0.20)** | rewards "a road the original did not take, taken for good reasons"; 1 = merely rephrasing the source |
| `gap` | **demoted** to ruler calibration ("is this rubric strict on this work"), not a score target |
| pairwise | asks "which is more worth an author's reference", and says "do not prefer the one that looks more like the original" |

Re-scoring the same four outputs under the new rubric: mean 37 → 48, Snow Country 42 → **64**
with `gap` going from −24 to **+7**, and pairwise from "4 losses" to "3 ties, 1 loss".
**The old rubric was systematically depressing the scores.**

## 3. Layout

```
novel_bench/
├── README.md / README.en.md        this file (zh / en)
├── USAGE.md / USAGE.en.md          detailed usage and troubleshooting
├── .env.example                    standalone config (judge model, beats, timeouts)
├── bench/                          the harness (stdlib + PyYAML only)
│   ├── config.py                   reads only novel_bench/.env
│   ├── dataset.py                  loading + schema validation
│   ├── project_builder.py          case -> the app's nine settings files
│   ├── runner.py                   headless drive of the real simulation loop
│   ├── metrics.py                  counters (zero model calls)
│   ├── judge.py                    LLM review (rubric + blind pairwise)
│   ├── report.py                   aggregation, comparison, MD/HTML report
│   └── cli.py                      command line entry point
├── dataset/
│   ├── works/*.yaml                26 works, 28 cases
│   ├── presets.yaml                smoke / core / full
│   └── schema.md                   field reference
├── docs/
│   ├── methodology.md              metric definitions, formulas, limitations
│   ├── sources.md                  papers/tools/theory behind the design
│   └── models.md                   judge-model survey and cost estimates
└── results/                        per-run artefacts
```

## 4. Coverage

26 works, 28 cases, sampled across four axes:

| Axis | Coverage |
|---|---|
| Format | Published 22 · Web serial 4 |
| Era | Classical 8 · Modern 8 · Contemporary 6 · Web 4 |
| Region | China 16 · UK 4 · US 2 · Russia 1 · Japan 2 · Latin America 1 |
| Genre | family saga, historical romance, mythology, classical Chinese tales, satire, lyrical realism, urban tragedy, comedy of manners, wuxia, xianxia, hard SF, cosmic horror, period family drama, tomb raiding, gothic, modernism, dystopia, children's fantasy, political fantasy, psychological crime, mystery, magical realism |

The rationale for each title is in its `representativeness` field; sources and selection criteria
are in `docs/sources.md`.

**The dataset is deliberately small.** No full novels: each work contributes a 700–1200 character
bible, a 150–300 character recap and a 300–500 character "author continuation". Public-domain works
may include a short verbatim excerpt; in-copyright works use a faithful paraphrase and are marked
`license: in_copyright_short_quote`. A full evaluation therefore costs about 28 short stories of
reading, not 26 books.

## 5. Quick start

```bash
cp novel_bench/.env.example novel_bench/.env    # fill NB_LLM_API_KEY + NB_JUDGE_MODEL

python novel_bench/bench/cli.py check                    # free: validate the dataset
python novel_bench/bench/cli.py smoke --preset smoke     # free: build + assemble, no model calls
python novel_bench/bench/cli.py run --preset smoke --ticks 8   # costs money
python novel_bench/bench/cli.py judge  --run results/<ts>       # costs money
python novel_bench/bench/cli.py report --run results/<ts>       # free
python novel_bench/bench/cli.py compare --a results/<old> --b results/<new>
```

The simulation uses the **app's** LLM settings (`NovelWorldSimulator/.env`); the review uses
`novel_bench/.env`. Keeping them separate prevents "we changed the judge" from looking like
"the product improved".

## 6. Reading the report

| Field | Meaning | How to use |
|---|---|---|
| `sim_mean` | transcript score, 0–100 | track the trend, not the absolute value |
| `ref_mean` | author text, same rubric | calibration: if this is low too, the rubric fits the case poorly |
| `gap_mean` | sim − reference (negative = worse) | **primary metric**, closer to 0 is better |
| `win_rate` | blind pairwise win rate (ties included) | 20–30% is already strong |
| `hygiene_mean` | counter-derived score | below 80: check repetition and meta-mark leakage first |
| `verdicts` | win / loss / tie | many ties means the two are close, or the judge cannot tell |

## 6.5 Thinking mode and cost (read this as of 2026-10)

The new `deepseek-flash` (a rolling alias) **thinks before writing** by default: thinking is billed
as output and competes with the body for the same `max_tokens`. Same "write 300 characters of
fiction" prompt:

| | Time | Output tokens | Of which thinking | Body |
|---|---|---|---|---|
| Default (thinking on) | 6.1s | 900 (hit the cap) | 900 | **0 chars** |
| Thinking off | 1.9s | 217 | 0 | 256 chars |

Impact on the simulation: one `agent_decide` normally costs 200–400 tokens; with thinking on it is
**3600–4300** — about CNY 0.027 per beat, CNY 29 of pure thinking per story day (1080 beats), plus
10–15 extra seconds per beat.

Using it in the harness:

```bash
# same case, same tick count, only the thinking mode differs (this run only; .env is untouched)
python novel_bench/bench/cli.py run --case ltxz-01 --ticks 6 --think-mode auto --run-id ab-auto
python novel_bench/bench/cli.py run --case ltxz-01 --ticks 6 --think-mode off  --run-id ab-off
python novel_bench/bench/cli.py judge --run novel_bench/results/ab-auto
python novel_bench/bench/cli.py judge --run novel_bench/results/ab-off
python novel_bench/bench/cli.py compare --a .../ab-auto --b .../ab-off
```

`meta.json` records `think_mode`; **two runs are only comparable at the same mode**. The app's own
switch is under "Tianji · LLM access → if unfilled use these three (global fallback) → Thinking"
(`auto / off / always`), effective on the next beat with no restart.

## 7. Boundaries (read this)

- **No automatic evaluation.** Money is spent only when you type `run` / `judge`.
- **The goal is not to beat the author.** It is to shrink the gap and expose structural defects.
- **Divergence is allowed.** `ground_truth.divergence_note` says what must be preserved and what is free.
- **The judge is one reader, not the truth.** Per-judge scores and comments are kept in
  `cases/*/judge.json`; when in doubt, a human reading wins.
- **Copyright.** Public-domain works may quote briefly; in-copyright works are paraphrased and
  tagged. The dataset is for local evaluation only — do not redistribute.

## 8. References

The methodology draws on G-Eval, MT-Bench's judge-bias analysis, LitBench and WebNovelBench;
see `docs/sources.md`. Model recommendations are in `docs/models.md`.
