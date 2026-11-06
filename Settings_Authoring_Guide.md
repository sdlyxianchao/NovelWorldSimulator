# Settings Authoring Guide

> This document answers exactly one question: **how do you hand your book to this program so it
> can actually run it?**
>
> Two routes are below — **let another AI tool write it for you** (section 3, prompts are
> copy-pasteable) or **write it by hand** (section 4, with the field limit table). Both produce
> the **same folder layout** (section 2).
>
> First, the most important thing: **the length plan in section 1**. It decides how many chapters
> each place gets and how many words the whole book is. It only exists as of 2026-10-27 — before
> that, "80,000 words for the whole book" written in an outline landed nowhere.

中文版：[`设定集提供指南.md`](设定集提供指南.md)

---

## 1. First, set the size: the length plan (**the most important section**)

### 1.1 Three things, three lines

Put them in the outline (`大纲/故事大纲.md` / `outline/story_outline.md`), each on **its own line**:

```markdown
## Length plan
- Total chapters: 32
- Total words: 75,000
- Words per chapter: 2400
```

**All three are optional** (the program falls back as described below); filling them in is what
actually puts you in control:

| Field | Means | When omitted |
|---|---|---|
| `Total chapters` | how many chapters the book should run | unlimited |
| `Total words` | how many words the whole book should be | unlimited |
| `Words per chapter` | how long one chapter is | if total words *and* total chapters are given, they are divided; otherwise **unlimited** |

⚠ **One chapter = one day = one draft the program produces.** Not a metaphor: it wraps up and
persists one draft per day, and that draft is a chapter. So "total chapters" is "how many days
you intend to run".

### 1.2 "At least a few chapters per place" — write it on **each station**

In the outline's station list, add a `Chapters` line to every station:

```markdown
### Station 2 · Outside the Orchid Temple

- **Span**: a few days
- **Length**: full
- **Chapters**: 5        ← this line
- **Summary**: …
- **Done when**: …
```

It means: **even if this station's business is finished early, it must produce 5 chapters before
the run is allowed to move on.**

⚠ Two different things, do not mix them:
- `Length` (full / medium / brief / in passing) = **how thick a single day is** (the beat budget —
  40–60 beats in a day, or 1);
- `Chapters` = **how many days this station occupies**.

One event can be written as three chapters (`full` + `Chapters: 3`) or glossed in one
(`in passing` + `Chapters: 1`).

**When `Chapters` is missing**, the length tier falls back:

| Length tier | Fallback chapters | Why |
|---|---|---|
| `full` | 4 | 40–60 beats a day; setup/rise/turn/aftermath need the room |
| `medium` | 3 | 15–25 beats a day is enough to finish one piece of business |
| `brief` | **2** | "brief" means "don't write it thick", not "skip it" — leaving after one chapter means the station was never written |
| `in passing` | 1 | one line and it's gone |

### 1.3 Recommended numbers (**clear without being bloated**)

Measured for an eight-station episodic book; the basis for each is in brackets:

| Item | Recommended | Basis |
|---|---|---|
| **Total chapters** | **28–34** (for eight stations) | averaging 3–4 per station. Below 24 each place only gets a beginning; past 40 it starts padding |
| **Total words** | **60k–90k** | 32 chapters × 2400 ≈ 77k. Trade publishing runs 100–150k, web serials 200k+; **a supernatural episodic book is tightest at 70–80k** |
| **Words per chapter** | **2000–2800** | measured: a `medium` day is ~1900 chars; existing sample chapters are 1500–2400 |
| **Plot beats per station** | `brief` 1–2 / `medium` 3 / `full` 4–5 | a station does **one** thing; that thing splits into this many units. One main beat per chapter |
| **Story time per station** | `one scene` 2 h / `that day` 12 h / `a few days` 3 d / `ten days` 10 d / `months` 90 d | the closed set behind the span tiers (see 1.4) |
| **Story time, whole book** | **3–4 months** | eight stations add up to ~100 days, plus travel between them |

⚠ **These are soft targets, not hard gates**: the program hands them to the writers as a per-day
word goal, so coming out a little over or under is normal. The hard gates are the **beat budget**
(length tier) and the **minimum chapter count**.

### 1.4 Laying out eight stations (a template you can copy)

| Station | Span | Length | Chapters | Words | Job |
|---|---|---|---|---|---|
| 1 | that day | medium | 3 | 7k | establish the people and the rules |
| 2 | a few days | full | 5 | 12k | the first complete unit story |
| 3 | a few days | full | 5 | 12k | raise the stakes |
| 4 | one scene | brief | 2 | 5k | **the breather** (creates the drop before the tight part) |
| 5 | a few days | full | 5 | 12k | the warmest station — sugar before the knife |
| 6 | months | medium | 3 | 7k | stretch time out, dig up the hidden thread |
| 7 | that day | full | 5 | 12k | **the tightest station in the book** (the turn lives here) |
| 8 | one scene | full | 4 | 10k | resolution, and leave it open |
| | | | **32** | **77k** | |

⚠ **Do not make all eight `full`**: everything detailed means nothing is. One or two breathers
are mandatory in the middle.

---

## 2. What the folder looks like

```
<book title>/
├── setting/
│   ├── world.md            # what this world is, what can never happen
│   ├── rules.md            # hard constraints (POV / taboos / forbidden writing)
│   ├── places.yaml         # the places, each with its rooms (≤12 entries; first 8 get interiors)
│   └── characters/         # one md per person
│       ├── <a>.md
│       └── <b>.md
├── foreshadowing.md        # optional
├── outline/
│   └── story_outline.md    # ★ length plan + station list (the program follows this)
└── text/                   # optional: chapters already written (texture samples + start point)
    ├── chapter 1 xxx.md
    └── chapter 2 xxx.md
```

⚠ **Folder names get renamed, logical names don't**: the program recognises "which file looks
like the worldview", not what it is called — `world.md` and `世界观.md` both work (the English
layout has its own alias table).

---

## 3. Route A: have another AI tool write it

> Every prompt below is **copy-pasteable as-is**. ⚠ Don't paste all six at once — go one at a
> time and **read each output before moving on** (if it drifts, everything after it drifts).

### 3.0 Give it this first (**with every single prompt**)

```text
You are helping me write a "novel setting collection" for a simulation program. Three hard rules:

1. Write setting only, no prose (unless I separately ask for sample chapters).
2. Every field has a character limit and is truncated past it — better short than long.
3. ⚠ NEVER write concrete dialogue in your examples. Your examples get copied into the prose as
   material, and then the whole book repeats that one line of yours. If you must illustrate,
   write "someone said something".
```

### 3.1 Worldview (→ `setting/world.md`)

```text
Write a novel worldview, ≤120 characters.

Only three things:
  ① what world this is, when, where;
  ② what can **never** happen here (one or two iron laws is enough);
  ③ what daily life looks like (how people get by).

No timelines, no power systems, no "in a distant land".
```

### 3.2 Top-level rules (→ `setting/rules.md`)

```text
Write 4-6 "top-level rules", each ≤30 characters, one per line.

They are **hard constraints**: when they clash with plot or with what a character wants, these
win. Only write things that can actually be judged — never "write well". A few of each kind:

  · POV and prose (which person, never write what he doesn't know, how long a paragraph)
  · taboos (what nobody may touch, what nobody may say)
  · the genre's lifeblood (for supernatural fiction: "horror comes only from the unsettling
    detail, never from gore")

⚠ No adjectives like "vivid" or "tense" — the program cannot judge them and they just eat a slot.
```

### 3.3 Characters (→ `setting/characters/<name>.md`, one file each)

```text
Write a character card. Fields and limits (**copy the field names exactly**):

  Name:
  Role: ≤30 chars
  Brief: ≤30 chars
  Personality: ≤30 chars
  Secret: ≤40 chars (what he won't say)
  Goal: ≤40 chars (what **he himself** wants, not what the plot needs)
  Red line: ≤40 chars (what he will never do)
  Relations: up to 8, each ≤25 chars, format "Person: what relation"
  Details: up to 8, each ≤40 chars (things on him, catchphrases, small habits)
  First appearance: which station (or "undecided")

⚠ "Goal" is **his own wish**, not "advance the plot".
⚠ "Details" are what drives each day's story — the more concrete the better
   ("a chipped purple-clay pot", not "has a pot").
```

### 3.4 Places (→ `setting/places.yaml`)

```text
Write YAML listing 8-12 places. **Only three fields**, with hard limits:

  - name:
    note: ≤20 chars (how many floors, what's there, when it's busy)
    where: ≤30 chars (landmark + direction + distance, so someone who never read the setting
                      can still place it)
    inside: [room1, room2, …]   ← at most 8, each ≤8 chars

⚠ The first 8 entries get both a "surroundings" and an "interior" map, **so the first 8 must be
   buildings with indoor scenes**; cities, bridges and rivers go further down.
⚠ For entries in another city, put the distance in front ("(station 2 · 1800 li away)") —
   without a distance the program lays all eight cities into one map.
⚠ Do not list rooms inside a building as their own entry; put them in that building's `inside`.
```

### 3.5 Outline and stations (→ `outline/story_outline.md`) ★ the important one

```text
Write a story outline in four parts:

[1. One line] What the whole book is, in one sentence.

[2. Beginning / rise / turn / resolution] Four short blocks, each ≤80 characters.
  ⚠ Write the climax as "who did what" (a visible action), never "the tension rises".

[3. Length plan] Three lines (copy this format, swap in your numbers):
  - Total chapters: 32
  - Total words: 75,000
  - Words per chapter: 2400

[4. Station list] 4-8 stations, each like this:

  ### Station N · <name, ≤6 chars>

  - **Span**: one scene / that day / a few days / ten days / months (pick one)
  - **Length**: full / medium / brief / in passing (pick one)
  - **Chapters**: <how many chapters for this station, a positive integer>
  - **Summary**: ≤80 chars
  - **Done when**: ≤50 chars, **exactly one thing**, phrased as "who achieved what"
  - **Beats**: (optional) 3–6 units as a numbered list — the steps inside this station
  - **Climax**: one line — who did what
  - **Emotion**: a shape like loose→tight→heavy
  - **Options**: (only the last station needs this) two or three ending forks,
    e.g. "registered / offered / the door left open"

★★ Four hard rules:
  1. **One piece of business per station.** Put two in the criterion and the station never advances.
  2. **Don't make every station `full`**: leave one or two breathers in the middle.
  3. **Adjacent stations may differ wildly in span** (`months` next to `one scene` is normal).
  4. Fill `Chapters` with "how many chapters this needs to be told properly" —
     **never the source novel's chapter numbers**.

★★★ The heading must look like `### Station N · name` (Chinese `第 N 站` works too). The program
  **slices the station table out of the outline by that heading**; if it can't find one it falls
  back to "read only the first 4000 characters" — with many stations the back half of the book is
  cut off, and **nothing reports an error** (a real incident, measured 2026-10-27).

★★★ **The lines you write are used as-is** (span / length / chapters / done-when / climax / beats /
  options). The model no longer rewrites them — when it did, criteria picked up coordinating words,
  the station got split in two, and 8 stations / 32 chapters landed as 9 / 35.
  ⇒ So **write the criterion as one thing yourself**; don't expect the program to split it for you.
  Fields you leave out are still filled by the model (those are marked "inferred" in the UI).
```

### 3.5.1 Chapter plan (optional, → `outline/chapter-outline.md`)

```text
If you have already laid the book out by chapter, write a separate chapter plan. The filename must
contain the words "chapter plan" / "chapter outline" (Chinese `章纲.md` works), split by station:

  ## Station N · <the same station name as in the outline>

  **Chapter 1 · <title>**
  - Advance: what this chapter moves forward.
  - Climax: the last beat of this chapter.

The program attaches it **by station name** and during the run **feeds only the current station's
chapters** (it is not a checklist — if the criterion is unmet the run is still in that station).
⚠ The station name must match the outline; a station that doesn't match is **not attached** (a
plan hanging on the wrong station is worse than none).
```

### 3.6 Sample chapters (→ `text/chapter 1 xxx.md`, **2–3 is enough**)

```text
Write the opening 2-3 chapters, 2000-2800 characters each.

They serve two purposes:
  ① the **start point** for the simulation (it continues from here);
  ② a **texture sample** for the writers' room (it learns your sentences and rhythm, not your plot).

So put your best sentences here, but **don't advance the plot too fast** — if chapters one and
two already spill the answer, there is nothing left to play.

⚠ End each chapter on an unanswered question; do not close on a rhetorical question.
```

---

## 4. Route B: writing it by hand

### 4.1 Field limits (**exceeding them truncates — the second half just disappears**)

| Where | Field | Limit |
|---|---|---|
| Worldview | whole file | ≤120 chars |
| Top-level rules | count / each | ≤6 / ≤30 chars each |
| Character | role · brief · personality | ≤30 chars each |
| Character | secret · goal · red line | ≤40 chars each |
| Character | relations | **≤16**, ≤25 chars each (raised from 8 on 2026-10-27) |
| Character | foreshadowing | ≤8, ≤25 chars each |
| Character | details | **≤20** (raised from 8 on 2026-10-27); name ≤20 / body ≤70 / where ≤20 / who ≤40 |
| Place | note / where | ≤20 / ≤30 chars |
| Place | inside | ≤8 items, ≤8 chars each |
| Place | count | ≤12 (first 8 get interiors) |
| Station | name / summary / done-when | ≤6 / ≤80 / ≤50 chars |
| Station | beats / climax / options | ≤6 units (≤80 chars each) / ≤150 chars / ≤6 (≤40 chars each) |
| Station | count | 4–8 stations |
| Length plan | chapters / words / words per chapter | any positive integer (`75k` also parses) |

### 4.2 The three mistakes hand-writing always makes

1. **Two things in one "done when".** The program asks every beat "is it done?" — with two things
   bundled it can never answer yes. The symptom is "the progress table never moves". **Split it
   into two stations.**
2. **Chapter numbers from the source novel.** "chapters 5–8" in an outline is for your own
   cross-reference; `Chapters` wants **how many chapters to write** (usually 1–6).
3. **Listing rooms as their own place entry.** Rooms belong in the building's `inside`; listing
   them separately pushes the buildings that actually need an interior map out of the first 8.

### 4.3 Self-check before you import

- [ ] Is every heading written as `### Station N · name`? (otherwise no station table is sliced
      and the back half of the book is cut)
- [ ] Does every station's "done when" state **exactly one thing**?
- [ ] Does the last station list `Options` (the ending forks)? The run offers them when it arrives.
- [ ] Is at least one station `brief` or `in passing` (not everything `full`)?
- [ ] Does every station carry `Chapters`? (the tier falls back, but you setting it is better)
- [ ] Do the chapter counts add up to roughly the total in your length plan?
- [ ] Are the first 8 places all **buildings with indoor scenes**?
- [ ] Do places in other cities carry a distance?
- [ ] 2–3 sample chapters, and the plot isn't racing ahead?

---

## 5. After you import it

1. Main window → **Import** → pick your folder → let ingestion finish;
2. Open `setting/故事进度.yaml` afterwards and confirm **every station carries `章数`** and that
   the `篇幅规划` block is present (if not, the outline wasn't written right — back to 1.1).
   The station and chapter counts must be **exactly what you wrote** (8 stations / 32 chapters in
   the outline must land as 8 / 32), and the last station must still have its `选项`;
3. At kickoff the program works out a per-day target from "total words ÷ total chapters" (it logs
   a line: "length plan: the setting collection carries one — per-day target N words").
   ⚠ The "roughly how many words per day" box in the kickoff dialog is **hand-filled first** —
   if you type a number it wins; only when it is left at 0 does the computed one apply.

> To check that the program really follows all this, run:
> `.venv\Scripts\python.exe tools\verify_length_plan.py` (40 criteria; all green or it's wrong).
> The station chain (slice -> build nodes -> split -> assembly -> run) has its own
> `tools\verify_station_plan.py` (61 criteria), and the extraction quotas
> `tools\verify_extract_quota.py` (14 criteria).
