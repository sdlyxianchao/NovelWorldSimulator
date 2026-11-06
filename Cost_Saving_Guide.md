# Cost-Saving Guide · Bringing the LLM Bill Down

> This document answers one question: **this program keeps getting more expensive to run --
> which few places should I touch?**
>
> The conclusion first; the four levers are ordered by how much they save:
>
> | Rank | Lever | Rough saving | Cost to you |
> |---|---|---|---|
> | ① | Give routine work a cheap model | **The most** (flagship vs budget differs 25-50x) | Ten minutes to pick through the list |
> | ② | Make the prefix cache actually hit | **~90%** of the input side | Not a single character changed -- just don't put variables in the fixed layer |
> | ③ | Turn on same-question reuse | Depends on the repeat rate; **5%-20%** is common | Flip one switch |
> | ④ | Run in the cheap window | **Halves it outright** for DeepSeek users | Move bulk runs to the evening or weekend |
>
> Each is explained below: **where to configure it, why it helps, and how to tell whether you got it.**

---

## 0. First, learn to read the bill

Open the **Usage Report** (the column on the left of the main window). It unfolds in three layers:

```
whole software / a project  ->  division method (model / date / module / run)  ->  Agent  ->  detail
```

**The most useful single step: switch the division method to "Model".** You then see how much each
model cost, what share of the total it is, and (since 2026-10-12) its **cache hit ratio**.

Three numbers to watch:

- **Which model is the big item** -- usually Actor and Extras (once per person per beat). If your
  most expensive model carries most of the volume, lever ① is your biggest opportunity.
- **Cache hit ratio** -- a long-run **0%** means something in the prefix is changing, and lever ②
  is not being collected.
- **Saved by cache (estimated)** -- this is the money not spent *because* caching hit. It is an
  estimate, and how good it is depends on the unit prices you filled in (see section 3).

> ⚠ **Same-question reuse does not appear in this table.** A reused request **sends nothing and
> spends nothing**, so it counts as neither a call nor a cost. To see how much it saved, look at the
> "Current state" line at the bottom of the "Models & LLM" page.

---

## 0.5 Let the program look first (added 2026-11-01)

The **"Tianji · Cost & Tuning"** page turns the levers above into buttons:

- **The table**: calls / input / output / cache hit rate / share / cost per purpose, plus a plain
  description of **what each step does** (so you never have to guess what `agent_decide` means) --
  computed by the same code as the CLI `tools/report_llm_cost.py`, so the two can never disagree;
- **"Export CSV"**: writes that table to `logs/cost_report/cost_7d_<timestamp>.csv` (UTF-8 with
  BOM, so Excel opens it on double-click without mojibake). Same columns as the screen, no totals
  row -- ready to drop into a spreadsheet;
- **"Smart analysis"**: sends that table, your current config and the registered models' unit
  prices to a model, and gets back structured advice -- **which config items to change** (with an
  "Apply" button that asks once before writing `.env`) and **which tier should switch to a
  cheaper model**;
- **"Deep pass"**: additionally explains how this program assembles context (prefix order,
  dedup, caching), so it proposes **software-level** changes -- the part tuning cannot reach;
- Each run costs **one call** (about 2-4k input tokens); the tier is chosen on the page
  (default: daily);
- The page keeps **its own log** (`logs/cost_advisor.log`: page opens, every analysis, every
  apply), and each result is archived under `logs/cost_advice/`.

> ⚠ It gives **advice, not verdicts**: a config suggestion only gets an "Apply" button when the
> key really exists in `SPEC` and the value passes its type/range check. Read the reasoning
> before you click.

---

## 1. Give routine work a cheap model (the biggest saving)

**Why this is lever one**: flagship and budget tiers differ **25-50x** in unit price. Only the few
steps that actually write prose need a good model; judging, extraction, compression, proofreading
and labelling -- work that wants *a conclusion* -- are often done just as well by the budget tier.

Using a flagship model to answer "is this station's criterion satisfied?" is paying sports-car
prices to deliver parcels.

**Where**: **"Tianji · Crew Agents"** -- click any row (crew positions, system services and the
special Agent are all in this list) and the editor has a **Model** group:

- the dropdown holds the models you configured on "Models & LLM", plus "(default)";
- next to it, **"Add by recommendation"** pre-fills the suggested model name, so you only supply the
  endpoint and key;
- two small lines underneath say **which kind it recommends / why** and **whether you have one**.

**How to pick**: on "Tianji · Models & LLM" there is a **recommendation table**, listing per Agent
what this kind of work needs (prose & long form / judgment & gating / extraction & structuring /
high-frequency performance / checklists / external service). If you don't want to read it all, note
these four:

| Who | Needs | Why |
|---|---|---|
| **Novelist** (writes the sample chapter) | prose & long form | the only one writing prose; if the prose is weak the whole chain is wasted |
| **Actor / Extras** (per-beat lines) | high-frequency performance | once per person per beat, **the two biggest spenders**; wants "sounds human", not "flowery" |
| **Progress Evaluator / Script Review** | judgment & gating | runs every beat and wants a single conclusion; the budget tier suffices |
| **Book Ingest** | extraction & structuring | emits hundreds to thousands of JSON lines at once; needs a big output cap |

> Memory hook: **only "words written for a human" deserve a good model; "conclusions for the
> program" can use a cheap one.**

---

## 2. Make the prefix cache actually hit (not one character to change)

**How it works**: DeepSeek automatically stores a repeated input prefix and, on the next hit, bills
it at the **cache-hit price** -- about **1/10** of a miss.

**The constraint**: it only counts when the prefix is byte-identical **from the very first token**.
In other words: **if something in the prefix changes, everything from that character on is billed at
full price.**

This program already splits the prompt into two layers (done back on 2026-10-07):

```
P0 fixed layer (constant for the whole round)  <-  total worldview + genre card + style
                                                   + static persona layer (name/identity/
                                                     character/catchphrase/secret/red line)
P1 changing layer (per scene / per beat)       <-  current situation, recent memories,
                                                   who is present, ...
```

**So the only thing you have to do is: don't put anything varying into P0.**

- Do not write "it is now day 3, 14:27" into the worldview or the persona card;
- Do not write "present right now: A, B, C" (that changes every scene);
- Those belong in "current situation" -- which already sits in the changing layer.

**How to tell whether you got it**: the **cache hit ratio** for that model in the Usage Report. A
long-run 0% means something in the prefix is changing (or your calls are so sparse that the cache
already expired -- DeepSeek clears unused caches within hours to days).

> Reference data point: putting a timestamp with seconds resolution at the start of a system prompt
> drops the hit ratio from ~52% to **0%**.

---

## 3. Turn on same-question reuse (one switch)

**What it does**: an identical input + model + parameters asked again within its shelf life
**returns the previous answer** -- no request, no quota, no cost, and the result is still correct.

"The same question asked twice" is far more common in a simulation than one would think: retries;
two stages of the same beat (the director judges, then continuity verifies); the author replaying a
beat; a UI button double-clicked.

**Where**: **"Tianji · Run" -> Token economy**:

| Config item | Default | Meaning |
|---|---|---|
| `LLM_DEDUP_ENABLED` | on | master switch |
| `LLM_DEDUP_PURPOSES` | see below | the **reusable purposes** whitelist |
| `LLM_DEDUP_TTL_SECONDS` | 3600 | shelf life in seconds; after that the model is asked again |

The default whitelist (these uses "must give the same conclusion for the same input", so reuse
costs no quality):

```
progress_eval, progress, genre, style, extract, book_scan,
compliance, day_verify, summary, day_summary, memory_compact
```

> ⚠⚠ **Never add `dialogue` / `narrate` / `crew_novelist` / `day_story` and the like to the
> whitelist.** Those want "different every time" -- caching them makes the whole cast say the same
> line. The code enforces this: **an unrecognized purpose is never reused** (the whitelist must be
> written explicitly), and a criterion specifically pins down "creative purposes are really sent
> every time".

---

## 4. Run in the cheap window (DeepSeek only)

DeepSeek uses **peak/off-peak pricing**:

| Window (Beijing time) | Price |
|---|---|
| Mon-Fri **09:00-12:00, 14:00-18:00** | peak (full price) |
| everything else + weekends + statutory holidays | **off-peak (half price)** |

**A simulation is work that can pick its time** (unlike online Q&A that must answer immediately), so:

- bulk runs, replays and batch generation -- move them to the **evening or weekend** and the bill is
  cut in half;
- the saving block on "Tianji · Models & LLM" shows the **current window**, saying "peak -- better
  to wait for off-peak".

**Config item**: `LLM_OFFPEAK_DISCOUNT` (default `0.5`). It only applies to models **recognizable
as peak-priced** (DeepSeek today); other providers are flat and unaffected. Set it to `1.0` to
disable the discount (always bill at peak).

---

## 5. To make the ledger accurate: fill in unit prices

**Why you must fill them in**: the built-in price table is only a **transcribed reference**, and
**prices keep moving** -- DeepSeek raised its cache-hit price 11x on 2026-08-17. Treating one
moment's numbers as truth only makes the ledger "look precise while being entirely wrong".

**Where**: "Tianji · Models & LLM" -> click **Edit** on a row -> the "Unit price (CNY per million
tokens, optional)" fields:

```
cache-hit price  /  cache-miss price  /  output price
```

- **Filling only part is fine**: output price alone works; unfilled parts fall back to the built-in
  reference price;
- **empty = estimated from the built-in reference** (never recorded as 0);
- once filled, the model row shows the prices and "Saved by cache" in the usage report becomes
  accurate too.

**Where to find your real prices**: sign in to your provider's console -> the "Models & Pricing"
page, and copy the **per million tokens** number.

**Another route**: instead of the UI, write `MODEL_PRICE_OVERRIDES` (in `.env` or under Tianji):

```
MODEL_PRICE_OVERRIDES=hy3=0.25/1/4,my-proxy-model=1/3/12
```

The format is `name=miss/output` (old form; the hit price is derived at 1/10) or
`name=hit/miss/output` (all three filled in).

---

## 6. A few more levers (the program already does them)

| Lever | Status | Where to tune |
|---|---|---|
| **Output caps** sized per model, auto halve-and-retry when hit | built in | the `LLM_MAX_TOKENS_MODE` group |
| **Thinking off** (for "I just want a conclusion") | built in | automatic via `NO_THINK_PURPOSES`; it also **self-heals** (retries with thinking off and remembers) |
| **Proactive context compression** (folds at the trigger line, keeps the most recent original text) | built in | the four `CTX_COMPACT_*` numbers |
| **Layered context trimming** (fixed + semi-fixed + dynamic) | built in | `MAX_CONTEXT_TOKENS` |
| **Free tiers** (where they exist) | use them if available | e.g. Zhipu's `glm-4-flash` is a 0-price tier |

**One more thing you can do yourself**: run the **least quality-sensitive** work (labelling, bulk
tidying) on a local model (Ollama) and keep the API for where it really matters.
⚠ Only if you **already have Ollama installed**; otherwise skip this line — the items above are
where the real savings are.

---

## 7. A self-check list

Walk it in order; usually the first one or two items already show a clear change:

- [ ] Open the Usage Report, switch the division to **Model**, and see **which is the big item**;
- [ ] Assign a **cheap model** to the positions carrying lots of judging/extraction (Crew Agents ->
      click that row -> Model);
- [ ] Confirm the **cache hit ratio is not 0**; if it is, check the fixed layer for something
      varying;
- [ ] Make sure `LLM_DEDUP_ENABLED` is on (it is by default) and that the "Current state" line shows
      a reuse count;
- [ ] **Fill in the unit prices** from your own bill so "Saved by cache" is trustworthy;
- [ ] Schedule bulk runs for the **evening or weekend**.

---

## Appendix: where these levers live in the code

For anyone digging deeper (and for locating things when something is off):

| Concern | File |
|---|---|
| price table / pricing / peak-off-peak / cache savings | `llm/tokens.py` |
| model registry (with unit prices) / resolution order | `llm/models.py` |
| same-question reuse (key / whitelist / TTL / LRU) | `llm/dedup.py` |
| where it is wired (`chat()` reuse and cache fields) | `llm/router.py` |
| ledger database (`cache_tok` column / WAL / aggregation) | `llm/usage.py` |
| usage report UI | `gui/usage_dialog.py` |
| the saving block and unit-price inputs on "Models & LLM" | `gui/app_flet.py` |
