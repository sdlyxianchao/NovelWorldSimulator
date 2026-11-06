# Script-style Narrative Output Format

> This document is an extended specification (v1.12) of design spec **§10.6 "Daily Life" Format**.
> The original "narrative prose: action / dialogue / narration, follow the style card" was **free text**;
> this spec upgrades that block into a **structured script**, and explains why it is designed this way.
>
> Implementation: `display/script.py` (data model), `display/script_render.py` (three renderers),
> `display/scene_builder.py` (runtime assembly).
> Config: `.env` keys `OUTPUT_FORMAT` / `SCRIPT_AMBIENT` / `SCRIPT_IMAGES` /
> `SCRIPT_SCENE_MAX_ENTRIES`.

---

## 1. The Three Problems We Solve

The previous implementation was a one-dimensional string stream:
`_daily_narrative.append(f"{name}{action}")`.
That format created three problems the prose could not express:

| Problem | Concrete symptom |
|---|---|
| **"he said" and "he did" are indistinguishable** | Action and dialogue live in the same flat layer; reading it feels like every character is talking nonstop |
| **"Simultaneous" gets flattened into "sequential"** | Two people act in the same tick; rendered as two consecutive lines, they look like one after the other |
| **Provenance is invisible** | Which story node this beat advances, which foreshadowing it collects, whose goal it serves -- all only known to the LLM in its prompt, never to the author |

So we upgrade narrative from "string" to **a sequence of structured entries**: each entry carries a
type, a subject, and provenance; a renderer then turns the same sequence into different shapes for
different consumers.

---

## 2. Entry Types

Fifteen types, all in actual use (not reserved):

| Type | Code | Purpose | On screen |
|---|---|---|---|
| Time note | `time` | In-act time advance ("half a ke later") | dimmed small text |
| Scene note | `scene` | Location + environment (light / sound / smell / weather) | block at top of beat |
| Enter | `enter` | Who came in, from where | `▸ Enter Nazhi (from the back kitchen)` |
| Exit | `exit` | Who left, toward where | `▸ Exit Nazhi (into the back kitchen)` |
| Narration | `narration` | Third-party narration, background | body text |
| Dialogue | `dialogue` | Who says what to whom, optionally with tone / action cue | name + line (most prominent) |
| Action | `action` | **What someone is doing** | indent + `·`, dimmed |
| Aside | `aside` | Inner activity, not voiced | indent + `◇` |
| Parallel | `parallel` | Multiple tracks in the same beat | vertical bar + one line per track |
| Cut | `cut` | Same moment, different place (parallel edit) | `〔 Cut to · East Dock 〕` |
| Cut back | `cut_back` | Return to the main scene | `〔 Cut back · Riverside Teahouse 〕` |
| Event | `event` | External event (injected by director) | `〔 Event · external 〕` |
| Beat | `beat` | Quiet moment / breath | a slim horizontal line |
| Note | `note` | Mechanism info (tension, foreshadowing) | `※ ...` |
| Image | `image` | Image output | rounded thumbnail |

A design trade-off: **there is no fuzzy "ensemble action" type**. Any action must hang off a subject
-- a person, or "the street" / "inside the hall" style places. At the same instant not only people
are doing things; the environment is too.

---

## 3. Simultaneity: Three Levels of Handling (the heart of this design)

The user explicitly asked for this. The rule:

```
A tick's actions are grouped by location
├─ Same place as the current scene (or no location specified) -> same-scene
└─ Different place from the current scene                         -> remote
```

| Situation | Treatment | Why |
|---|---|---|
| **Only one person** | Just give the action / dialogue; **no `parallel` wrapping** | One person acting but wrapped in "simultaneous" makes readers think someone is missing |
| **Multiple people, same scene** | One `parallel`, one track per person | This is the real "simultaneous" |
| **Remote, actually doing things** | `cut` -> the remote track -> `cut_back` | Remote simultaneity is expressed by editing |
| **Remote, only zoning out / changing expression** | **Do not cut** | Otherwise every tick fills the screen with `Cut to ... Cut back ...` |

The "worth cutting" test (`_worth_cutting`): `move` / `interact` / `speak` with dialogue are worth
it; `wait` / `emote` / pure `think` are not.

### Tracks carry "visibility"

| Visibility | Meaning | On-screen mark |
|---|---|---|
| `present` | In the same scene | no mark |
| `offscene` | **Off-scene, heard but not seen** (e.g. clatter from the back kitchen) | `（off-scene）` |
| `elsewhere` | Somewhere else (remote simultaneity) | `（elsewhere）` |

This layer is necessary: novels constantly contain both "visible" and "audible" presences.
Without it you cannot write "Nazhi is in the back kitchen -- you can hear her but not see her".

---

## 4. Disk Format ("Daily Life")

Example (matches the real output of `flush_daily_script()`):

```markdown
# Day 3 · Xu hour · Rain
> Present: Shen Yan, Nazhi  Key event: N06  Tension: 0.42

## Xu hour 19:30 · The Slip
**Scene** Riverside Teahouse · inside the hall
**Environment** Rain taps the eaves; the lamp at the door flutters in a gust. · Weather rain
**Present** Shen Yan, Nazhi
**Source** Node N07 · Slip ; Foreshadowing F01

▸ Enter Nazhi (from the back kitchen)

> Rain taps the eaves; the lamp at the door flutters in a gust.

Shen Yan (paused, did not raise his head): You've been speaking in code all day.

· Action Shen Yan: wiping the counter with a rag

◇ Aside Shen Yan: must not let him know about the third person.

〔 Simultaneous 〕
- Shen Yan | wiping the counter, eyes never leaving the door
- Nazhi (off-scene) | stacking bowls in the back kitchen with a clatter
- The street (elsewhere) | the night-watch drum has struck third watch

〔 Cut to · East Dock | same moment 〕

· Action The cloaked figure (elsewhere): stepped off the boat

〔 Cut back · Riverside Teahouse · inside the hall 〕

〔 Event · external 〕 hoofbeats grow from afar to near

〔 Beat 〕 a moment

※ Tension 0.42 -> 0.58

〔 Image 〕 Riverside Teahouse  assets/images/scene_xxx.png

▸ Exit Nazhi (into the back kitchen)

## Xu hour 20:40 · The Well
**Scene** Backyard
**Environment** Weather rain
**Present** Shen Yan
**Source** Foreshadowing F01 · the well in the back yard

> Only the rain in the back yard.

〔 Simultaneous 〕
- Shen Yan | squatting by the well, one hand on the rim
- Inside the hall (off-scene) | the lamp still burns
```

### Relationship to design spec §10.6 (additive only)

| §10.6 original | Current |
|---|---|
| `# Day 1 · <calendar> · <weather>` | **unchanged** |
| `> Present: ... Key event: ... Tension: ...` | **unchanged** |
| `## <hour/period> · <subsection title>` | **unchanged** (that is "beat header") |
| `(Narrative: action / dialogue / narration, follow the style card)` | **upgraded to** the structured block above |
| `【Inner voice · someone】...` | becomes `◇ Aside someone: ...` |
| `【Shot】camera move / framing / enter` | **unchanged** (§10.8, see the division-of-labor note below) |

Old run folders still open normally (see section 7).

---

## 5. How "People Doing Things" Is Expressed

User's words: **"A person isn't always talking; he might be doing something."** Three measures:

1. **Each Action stands as its own entry with a subject** -- action is not stuffed inside a
   parenthesis after dialogue.
   People who "are there but say nothing, yet keep doing things" become readable.
2. **`speakers()` and `actors()` are counted separately**: their difference is exactly
   "people who are there but did not speak", so the UI can surface "someone who says nothing
   but is busy all the time".
3. **"Thinking" is an aside, not an action**.
   *(A pitfall hit earlier.)* An early version rendered `think`'s `inner_thought` as action text,
   producing `· Action Shen Yan: (if we can't leave tonight...)` -- which reads like he's
   murmuring to himself. Now `think` -> `◇ Aside`, and `inner_thought` no longer pretends to be
   action.

Also: **"speaking" and "what the hands are doing" are two entries, not one sentence**
(in the `〔 Simultaneous 〕` block, give a "he is saying:" track; the spoken line then expands
on the line below), because collapsing both into one loses one of them.

### Rule text is the skeleton, not the draft

`_action_text()` produces a **guaranteed-complete-skeleton** sentence in which no slot is
empty; it is not literary. The division of labor:

```
Rules guarantee structure (who, when, where, simultaneous-with-whom)
   +
Prose is not produced here: on the normal path the novelist writes the sample
chapter, the screenwriter turns it into a script, and the actors (character
agents) produce their own action and dialogue -- skeleton text only fills empty
slots. Full-manuscript polish is a separate path (`EXPORT_NOVEL_POLISH` at export).
```

Don't ask the rules to write prose, and don't ask the model to decide "who is simultaneous with
whom" -- it gets that wrong constantly.

---

## 6. "Beat Source": Making the Settings Visible

Every entry can carry `anchors` (node / foreshadowing / character goal), and the beat header
summarizes them in one line:

```
**Source** Node N07 · Slip ; Foreshadowing F01
```

Why: the user asked for "**everyone acts according to their character settings and the story's
development**". That fact now lives in two layers --

* **Generation layer**: a character's settings and goals constrain Agent decisions inside the
  prompt (existing mechanism, unchanged)
* **Readable layer**: `anchors` show "this beat serves which setting" right on the screen

The second layer is new this round and is **auditable**: the author can see at a glance which
beat advances which node, instead of having to trust the program "ran by the settings". In the
future when "plot verification" is wired (design spec §X, the feedback workflow), this anchor
is exactly what it relies on.

---

## 7. Three Render Forms

The same `SceneScript` feeds three destinations:

| Destination | Function | Character |
|---|---|---|
| **Screen** | `render_blocks()` | Structured blocks; GUI colors and indents by `role`; **labels follow the UI language** |
| **Disk** | `to_markdown()` | Labels are **fixed in Chinese** (must round-trip back to data); human-readable, human-editable |
| **Back to LLM** | `to_context()` | Extremely compact; about 40% shorter than the Markdown in practice, and contains no image paths |

**Why disk-fixed-Chinese but UI-follows-language?**
The parser needs the labels as anchors. If the English interface writes `CHARACTERS:` and the
Chinese interface writes "出场", the parser has to guess between two grammars, and users might
hand-edit the file. **Disk is data, UI is presentation** -- separating them keeps the rules
simple. English-speaking users still see English labels in the GUI (via `kind` -> i18n mapping).

---

## 8. Image Output: Where It Goes and the Cost Discipline

Per the user's "**text first, with some image output**", the rules are:

| Position | When it renders | Source |
|---|---|---|
| Scene image | **Whenever the location changes** (no repeat within one location across back-to-back beats) | Pillow-drawn mini map frame, **zero cost** |
| Character portrait | On a character's **first appearance** | Pillow-drawn ink-line portrait on rice paper, **zero cost** |
| Cap | **At most 2 per beat** | Images are accent; three per screen squeezes the text out |

Config `SCRIPT_IMAGES = off | map | portrait | both` (default `both`).

**Cost discipline (important)**: the two above are drawn locally with Pillow -- no network, no
cost. **Text-to-image scene illustration is out of scope here** -- that one charges per image, needs
its own switch and per-image confirmation, and should not be bundled with a "default on" image
feature.

---

## 9. Compatibility and Migration

| Case | Behaviour |
|---|---|
| New run folder | Write `.md` (human-readable) + `.json` (sidecar, machine-readable) |
| **JSON is the source of truth** | UI prefers `.json`; an edited `.md` does not affect the UI |
| Has no `.json` but has script-formatted `.md` | Reverse-parse the `.md` (`parse_markdown`) |
| **Legacy plain-text `.md`** | **Do not parse**; render as raw prose -- keep its paragraph structure intact, do not force-split narration into narration / dialogue / action |
| Detection rule | `looks_like_script()`: presence of structural markers (`**Scene**` / `▸ Enter` / `〔 Simultaneous 〕` ...); `> ` does NOT count, since old prose can also have blockquote lines |
| Want the old behaviour back | Set `OUTPUT_FORMAT=prose` in `.env`, and the original logic is restored bit-for-bit |

---

## 10. Config Items

| Config | Default | Notes |
|---|---|---|
| `OUTPUT_FORMAT` | `script` | `script` = script-style; `prose` = legacy free text |
| `SCRIPT_AMBIENT` | `true` | Auto-add an environment line at the top of a beat / empty scene (**derived from real period and weather, never invented**) |
| `SCRIPT_IMAGES` | `both` | Image position: `off` / `map` / `portrait` / `both` |
| `SCRIPT_SCENE_MAX_ENTRIES` | `40` | Maximum entries per beat; auto-split when exceeded |

About the environment line: it is not "made-up filler" -- the period comes from `WorldState.clock`
and the weather from `WorldState.weather`, both real values; the sentence is **deterministically**
chosen from a "period x weather" phrase library (re-running the same day-period produces the
same result, for reproducibility). Turn it off if you don't want it.

---

## 11. Consistency with Existing Conventions

| Existing convention | How this design honors it |
|---|---|
| **The program never writes back into the project folder** (§1) | The script only writes to the run folder; the renderer is strictly read-only |
| **Reading surface** (§11.7 reading pacer) | Script blocks are streamed entry-by-entry to the pacer (`one_line()`); P0-P3 priorities carry over; P0 events still auto-slow |
| **Translucent reading surface** (`UI_OPACITY`) | Script rendering uses the same parchment-tone container, under the same opacity control |
| **FILM_MODE shot card** (§10.8) | **Division of labor**: shot card is "how to shoot" (camera / framing); the script is "what happens". Shot cards continue as optional additional lines, not folded into the entry body |
| **Soft clock** (§2.2) | Beats are split by **world state** changes (period / location), not by wall-clock time |
| **Compliance checkpoints** | The script and plain text share the same CP5/CP6 pipeline; no new bypass paths |

---

## 12. Known Boundaries

1. **Granularity of beat splitting**: currently "period change + location change + entry cap".
   If finer-grained "scenes" (e.g. split by conflict escalation) are wanted later, add a rule; no
   format change needed.
2. **Simultaneity only goes as deep as "same tick"**: cross-tick parallelism (A doing something
   while B does three things in parallel) gets flattened onto the time axis. For finer
   simultaneity, action timestamps are required -- doable later.
3. **`interact`'s target is not classified**: the program does not know whether the target is a
   person or an object, so we use neutral phrasing like "turns toward X". Let the LLM polish
   pass do the classification.
4. **A character's move does not auto-update `location`**: `RunLoop._process_action` does not
   write back into `PersonState.location`, so "location change -> cut" currently only takes
   effect for characters whose location was set at initialization. Hooking up Agent-side
   location write-back will make this precise automatically.
