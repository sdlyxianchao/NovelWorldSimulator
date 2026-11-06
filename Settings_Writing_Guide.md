# Guide to Writing Novel Settings

> This document answers one question: **how should you write your settings so the program can use them -- and use them well.**
>
> It has two halves:
> * The first half is **writing theory** (how to write settings that actually hold together);
> * The second half is **how this program actually reads your settings** (which words get carried through verbatim,
>   which get compressed, which sentence appears in front of whom and when).
>
> The second half is specific to this program and the easiest thing to overlook: no matter how well your settings
> are written, if they land somewhere the program never reads -- or get compressed down to a single sentence --
> they're "not written" as far as the simulation is concerned.
>
> Every "what the program does" in this document is verified against the source code, not guessed;
> wherever a specific number appears, the file it comes from is cited so you can check it yourself.
>
> Companion document: **`Settings_Authoring_Guide.md`** (Chinese: `设定集提供指南.md`) -- that one covers
> **where a settings folder comes from** (how to have another AI tool write it, what prompts to use,
> what the field limits are if you hand-write it), and **how to set "how many chapters per location /
> how many words for the whole book"** (the length plan -- see section 1 there and Appendix A here).

---

## 0. One-Minute Cheat Sheet

**The single most important sentence**: settings come in two kinds -- **background** and **actable things**.
Most settings fail not because they're too small, but because they contain **only background, no actable things**.

| | Background (climate) | Actable thing (weather) |
|---|---|---|
| Example | "This city has perpetual rain, paper is dear, the magistrate calls the tune" | "The chipped teapot on the counter -- no one is allowed to touch it" |
| How the program uses it | Usually only a one-line "climate" cue; expanded on Day 1 / climax days / every 3 days -- **and what gets expanded is just ~120 words of summarized text** | **Shows up every day** (whenever this scene is in this location) |
| What goes wrong | You wrote three thousand words; only ~120 make it into the simulation | You wrote none, so every day the characters can only "look, wipe, wait" |
| How much to write | 300-800 words original (**the rules that actually carry weight go in a separate rule file**) | **Write a lot**: one item per fact, the more specific the better |

**The three mistakes people make most often**

1. **Treating settings as a backdrop.** "Three great factions, five major cultivation realms, seven eras" --
   it reads complete, but no character in the simulation will change what they do today because of it.
   Good settings **directly become obstacles**: "the levee height was calculated one chi off, and 'fixing it' is itself a capital crime."
2. **Too much big-picture background, not enough small specifics.** Big-picture background has a **hard quota** in
   the program (only ~140 words normally fed in); you write three thousand words and it still gets cut; meanwhile
   the "chipped teapot" you wrote gets pulled in **entry by entry** into the prompt.
3. **Writing what should be word-for-word as free-flowing prose.** The "Top Rules" file is **brought into the prompt
   byte-for-byte**, while "Worldview" gets compressed by the AI to about 120 words. So:
   **Hard constraints belong in the rule file; background atmosphere belongs in the worldview file.**

---

## 1. Settings Are "Structural Elements", Not Backdrop

### 1.1 Theory: A Setting Must Create Dilemma

In the Western screenwriting canon there's a rule (and this program actually uses it,
`craft/playbooks/西方编剧正典.yaml`):

> **Worldbuilding** -- A setting is a **structural element**, not a backdrop: the rules of the world
> must create the character's current dilemma.
> Prompt: "Make one rule of the world directly become the character's current obstacle -- don't explain the setting first."

That sentence is the foundation of this whole guide. Compare two ways of writing:

**The backdrop way** (it turns into air during simulation):

```
This world is divided into nine heavens; cultivators pass through five realms -- Qi Refining, Foundation Building,
Golden Core, Nascent Soul, Spirit Severance. Each realm corresponds to a concentration of spiritual energy;
breaking through requires spirit stones and comprehension.
```

**The structural-element way** (used by the simulation every day):

```
The cultivation world doesn't run on "seizing"; it runs on borrowing. Borrow and you must return;
if you can't return, it's recorded -- on the borrower. Each item borrowed leaves a "debt-mark."
A wandering cultivator with too many debt-marks gets turned away everywhere.
```

Why the second works: it turns "a person's current situation" into something **computable**.
How many debt-marks on him? Who is counting? At which shop will he be turned away?
**The trouble of today's scene grows out of the setting itself.**

> A simple self-check: **delete the setting you just wrote; does the character's today change?**
> If not, it's backdrop.

### 1.2 The Three-Layer Relationship: Constraint -> Cost -> Violable

A setting that pushes plot needs all three:

| | What it means | Example (from *The Water Clock* rule file) |
|---|---|---|
| **Constraint** | What can't be done / must be done | The water clock may only be calibrated, never altered; one alteration requires a record, a signature, a seal |
| **Cost** | What happens if it's violated | An undocumented alteration **is itself a clue** (it's effectively a confession) |
| **Violable** | Someone actually wants to violate it | At the end, the protagonist alters the clock himself -- to slow the water by one beat |

A setting that's only a constraint is a wish; one with a cost but no violator is decoration.

### 1.3 Big vs Small: Climate vs Weather

Lao She has a technique in *Teahouse* (the program has it too, `剧作与舞台.yaml`):

> **One small prop to carry everything** -- a recurring small object (a piece of calligraphy, a lamp,
> a teapot) can carry the pressure of an entire era, more reliably than any editorializing.

This program turns that idea into **two layers with separate quotas**:

| | Big background (climate) | Small things (weather) |
|---|---|---|
| When it enters the prompt | Day 1, climax days, every 3 days, on changing location -- **only then is the full text expanded** | **Every day** (when the occasion fits) |
| How many words at a time | Normally <= **140** words; expanded <= **900** words | At most **4 entries, up to 70 words each, 260 total** |
| What to write | The world's rules, the era's pressure, where the story begins | Objects, customs, verbal tics, small rules, local color |
| File source | `CANON_BRIEF` / `CANON_FULL` in `world/layers.py` | `DETAIL_*` in the same file |

> ⚠ **A common misunderstanding**: 140 / 900 are **quotas**,
> and the "content" comes from your **Worldview.md in the settings bundle** -- which is, at ingest time,
> a ~120-word summary produced by the AI from your original text
> (the prompt in `ingest/extractor.py` requires "worldview <= 120 words").
>
> In other words: **you write three thousand words; what makes it into the simulation is around 120 words.**
> The expansion vs. non-expansion difference is just whether those 120 words are given in full or in the first 140.
>
> So how do you write big background that actually does work? Two routes (both in §4.1):
> 1. **Write it into "Top Rules"** (verbatim, 2000-word quota) --
>    things like "This city has no supernatural forces" or "Time slippage will always come back as a human cost";
> 2. **Split it into actable small things** (detail layer, every day) --
>    "The water clock may only be calibrated once per night -- an error must be compensated" comes from exactly this route.

**Why this split**: big background gets re-sent every beat; by day nine nobody cares.
But "the master's chipped teapot, he won't let anyone touch it" is what today's scene can actually use.

> So: **write big background accurately (into rules); write small things abundantly (into details).**

### 1.4 Foreshadowing: The Subtle Thread, The Long-Arcing Vein

Jin Shengtan has two principles on foreshadowing (the program uses them):

> **Grass-snake, ash-line** -- Foreshadowing is like a thread of ash hidden in grass, appearing broken yet actually continuous.
> **The long-arcing vein** -- Foreshadowing spans long stretches of text and is collected at the critical moment.

The program does one concrete thing with foreshadowing: **the foreshadowing list has fields**
(number / content / bury location / expected recovery location),
and **unactivated foreshadowing items** are listed in the prompt to remind the writer "the reader is still owed a payoff here".
When *Ending.md* is written, **uncollected foreshadowing is given its own section**.

So when you write foreshadowing, fill in all four fields for maximum usefulness:

```markdown
- **No. 3** -- In the old archive of the Calendar Bureau, the page from ten years ago is blank
  (with a paper-trimmed rough edge beside it).
```

**Burying** it goes on Day 1 (flipping the old archive); the **expected recovery** is at the very end
(the senior colleague's confession) -- all four fields filled, and the program knows "this thread is still unpaid."

> Counter-example: "Something big will happen later." That isn't foreshadowing, it's **plot preview** --
> it has no specific object or fact that could be paid off, so during simulation the program cannot judge
> whether it's been redeemed.

---

## 2. The Five Layers of Settings: This Is the Program's Skeleton

### 2.1 What the Five Layers Are

The program divides your settings into five layers by **scope of action**. This isn't a taxonomic habit; it
answers the question: **which line of setting appears in front of whom, when**.

| Layer | What it is | When it appears | Who may write | Source file |
|---|---|---|---|---|
| **World layer** | Big background: what the world looks like, the era's rules, where the story begins | **Usually only "climate"**; the full text expands on Day 1 / climax day / every 3 days / when location changes | Author | `世界观.md`, `顶级规则.md`, `类型卡.yaml`, `风格卡.yaml` |
| **Main-line layer** | Where this book is going: outline, progress nodes, foreshadowing | Per chapter (on node switch) and on Day 1 | Author | `剧情走向.md` (= your outline), `故事进度.yaml`, `伏笔与悬线.yaml` |
| **Scene layer** | This place, plus the people it touches | Whenever a scene happens in this location | Author + crew | `地点.yaml`, `关系.yaml` |
| **Detail layer** | Objects, customs, verbal tics, small rules, local color | **Appears whenever it's useful today** | Author + crew | `细节设定.yaml` (extracted from your docs at ingest) |
| **Character layer** | A single character's own setting | Whenever this character appears | Author | `人物.yaml` (= your character cards) |

> "Crew" = the program's AI positions (director, novelist, screenwriter, ...). They may **only add to
> the "scene layer" and "detail layer"** -- they cannot touch your world layer or main-line layer --
> this is enforced by the program, see §7.3.

### 2.2 Three Self-Check Questions

After writing one line of setting, ask yourself:

1. **Which layer does it belong to?** (If you can't answer, it's probably "atmosphere" -- and atmosphere
   is the easiest thing to be compressed away.)
2. **When should it appear?** ("Always there" usually means "never important.")
3. **Who does it affect?** (Nobody -> it's backdrop.)

In the program, every setting actually carries these three into its filter
(`SettingItem` in `world/layers.py`: `when / where / who / weight`). You can **write them explicitly**,
e.g. in detail settings:

```yaml
- 名称: 缺角的紫砂壶
  内容: 柜上那把壶缺了个角，谁也不许动
  场合: 临河茶肆          # only appears at Riverside Teahouse
  涉及: 主角            # only when Shen Yan is present
```

Not writing them also works (then it's "everywhere, always"), but writing them **saves quota and improves
matching accuracy**: with only 4 detail slots per pass, no `where` tag means a detail can be displaced by
something from the neighboring location.

---

## 3. Per-Category Writing Guide

> Every subsection has the same structure: **what it is / what the program does with it / how to write it / common mistakes**.
> Examples cite the bundled sample projects (`samples/zh/`, all original; feel free to copy or modify).

### 3.1 How to Lay Out the Folder

The program categorizes files by **keywords in filename and path**.

```
我的小说/                       <- this folder is the "reference folder"
├── 设定/
│   ├── 世界观.md               <- keyword "世界观" -> classified as "setting"
│   ├── 顶级规则.md             <- keyword "规则" -> classified as "rule" (highest priority)
│   └── 人物/
│       ├── 主角.md
│       └── 柳娘.md
├── 大纲/
│   └── 故事大纲.md              <- keyword "大纲" -> classified as "outline"
├── 伏笔.md                    <- keyword "伏笔" -> classified as "foreshadowing"
└── 正文/
    ├── 第一章 早了一刻.md      <- keyword "第一章" -> classified as "chapter"
    └── 第二章 茶棚.md
```

**Categorization keyword table** (any one hit counts; **first match wins**, in the order below):

| Priority | Category | Keywords |
|---|---|---|
| 1 | **Rule** | 规则, 铁律, 铁则, 守则, 法则, 戒律, 准则, 准绳, 禁忌, 契约, 规范, rule, constraint |
| 2 | Character | 人物, 角色, character, person |
| 3 | Outline | 大纲, outline, 剧情, 梗概 |
| 4 | Foreshadowing | 伏笔, 悬念, 线索, foreshadow |
| 5 | Chapter | 正文, 章节, 第X章, chapter, 故事 |
| 6 | Setting | 设定, 世界观, 背景, world, setting |
| — | Misc | None hit |

**Three key points**

* **"Rules" must come first** because it's the only category that is brought in **verbatim**.
  When you write `设定/顶级规则.md`, the path also contains "设定"; the program classifies it as
  **rule** (not setting).
* **Files that hit no keyword go to "misc"**: their content is still sent to the AI, but **it's not treated
  specifically as chapter or outline** (the style card only looks at chapters, the progress table only looks at
  outlines). At ingest, the program lists this in a checklist, **does not rename your files**, and only writes
  a note + a categorization-fix table. To resolve permanently, rename them yourself
  (`第一卷.txt` -> `正文-第一卷.txt`).
* `.md` `.txt` `.docx` `.html` are all supported. **`.docx` only reads paragraph text** -- table contents inside
  .docx are not read. Don't put critical settings into tables.

### 3.2 Worldview.md -- "What the World Is Like"

**What the program does with it**: feeds into the **world layer**. Only ~140 words go in normally (a single
"climate" line); expanded to ~900 words on Day 1 / climax days / every 3 days. At ingest, the AI **compresses** it
into roughly 120 words and stores that in the settings bundle.

**How to write it**

* 300-800 words. **Write "rules" first, then "scene"**: what readers and characters really need is rules.
* Split into three sections -- "when and where -> this line's rules -> what it looks like now" -- better than one
  block of prose.
* **Leave concrete details to the "detail layer"** (see §3.9); only the framework belongs here.
* ⚠ Remember this file's **two purposes**:
  1) Provide material for the AI to summarize into ~120 words stored in the settings bundle -- **that's the
     120 words the simulation sees**;
  2) If that summary misses what you wanted, **edit the settings bundle after ingest**
     (§4.1 "manually edit the settings bundle").
  So: **the world's most critical rules shouldn't only live here -- create a separate rule file.**

**Example** (excerpt from `samples/zh/03_都市_夜班书店/设定/世界观.md`):

```markdown
Contemporary city; at the corner of an old street in the south end of town there is a 24-hour bookshop.
Half the signboard light is dead -- from a distance it reads "Night   Book   ".

The shop has three unspoken rules:
1. **Never urge anyone to buy a book.** If you ask which one is good, the owner only says,
   "This one hasn't been read yet."
2. **Between three and four in the morning, don't ask a customer what they do for a living.**
3. **The one book in the register's drawer is not for sale.**

The owner has a quirk: he can **hear a book's wish to be read**. A read book shines a little brighter;
a book no one has touched for a long time slowly grows dim -- not metaphorically; in his eyes it really does dim.
```

Why it's good: **three rules + one quirk**, all actable. In the simulation "a customer asks which book is good",
"a customer at three in the morning", "the unsellable book" can all directly become scenes.

**Common mistakes**

| Mistake | Consequence |
|---|---|
| Writing it like a history textbook (dynasty, geography, political system...) | Compressed to 120 words; the rest happens to be the least useful part |
| Writing only "atmosphere" ("It's mysterious here" / "People live in fear") | No specific action can be staged |
| Putting hard constraints in this file | The AI will summarize them (conditions may be simplified) -> belongs in "Top Rules" instead |

### 3.3 Top Rules.md -- The File Most Worth Investing In

**What the program does with it**: it is brought into the settings bundle (`本地设定集/顶级规则.md`)
**byte-for-byte**, placed at the front of every prompt during simulation, up to 2000 words.
Every decision a character makes, every line they speak, every twist the director pulls --
all see your words verbatim.

**Division of labor with Worldview**: Worldview is **background** (what the world looks like);
Top Rules is **constraint** (what absolutely must not happen, how this book must never be written).

**Four suggestions**

1. **5 to 10 is the sweet spot.** Dozens will fight each other; the model's attention dilutes.
   Pick the ones "if this is violated, the book collapses."
2. **Write "how NOT to do it", not "specify the plot for me."** Rules like "the protagonist must die"
   force the simulation to work around them; the story gets stiff.
3. **Two-column writing is clearest**: `## World Iron Rules` (what absolutely won't happen)
   + `## Writing Method` (narrative discipline).
4. **Each rule must be checkable.** "Write better-looking prose" is not checkable;
   "inner monologue no more than three sentences per chapter" is.

**Example** (excerpt from `samples/zh/01_悬疑单元_更漏子/设定/顶级规则.md`):

```markdown
## World Iron Rules
- The water clock may only be calibrated, never altered. One alteration requires a record,
  a signature, a seal; **an undocumented alteration is itself a clue**.
- The whole city's schedule is set by this set of copper pots: water one beat faster, the whole
  district wakes one beat earlier. Time discrepancies always manifest as human affairs --
  there is no "mere coincidence" in this book.
- No ghosts, no supernatural forces. Every "strange event" must ultimately have a coherent
  human explanation.

## Writing Method
- **Finish one case before starting the next**: a chapter must close the current case; the
  through-line may only be planted, never explained within the chapter.
- Shen Yan solves cases only by "reading the water" -- no flashes of insight, no lucky
  coincidences -- every clue must have been shown to the reader first.
- His inner monologue: no more than three sentences per chapter; judgments come out through
  action and dialogue.
```

These six rules each govern one thing: **world boundary -- causal law -- supernatural ban -- chapter
structure -- case-solving method -- narrative discipline**. This is what "checkable rules" look like.

**Common mistakes**

* Mixed into `世界观.md` -> at ingest the AI will try to summarize a few -- but that's **paraphrase**:
  conditions may be simplified, voice may be rewritten. **If you want it word-for-word, make a separate rule file.**
* Written as a wish ("I hope this book moves people") -> not a constraint; has no effect during simulation.

### 3.4 Character Cards -- Seven Fields, Each Does One Thing

**What the program does with it**: assembles a "person"; each field goes into different places:

| Field | Who reads it | Limit | What it does |
|---|---|---|---|
| **Name** | Everyone | -- | Identity; **required** |
| **Identity** | Personality card (every beat) | 30 chars | Who they are, where they work |
| **Personality** | Personality card + portrait image | 30 chars | The tone of how they do things |
| **Verbal tic** | Personality card | 30 chars | **One of their own catchphrases**; the program counts how often it appears |
| **Secret** | Personality card | 40 chars | What they don't want known; **goes into the prompt, so see the warning below** |
| **Goal** | Personality card + outermost goal layer | 40 chars | What they want from life |
| **Red line** | Personality card | 40 chars | What they absolutely won't do (constrains them together with Top Rules) |
| **Age** (optional) | Casting (`actors/casting.py`) | -- | **Their age.** `十六` / `16` / `六十来岁` all work; when present, the age tier follows it |
| **Appearance day** (optional) | When assembling | See below | Which story day they appear; `未登场` = don't release them yet |

> **Why write "Age" separately**: the `演员类型` is composed as "age tier × temperament"
> (e.g. `少年·憨厚`), and the age tier decides **speech rate and volume**. Without an age the
> program can only guess from keywords in the intro/personality -- and numbers there are often not
> ages ("六十来岁" gets read as "十来岁"; "in his last life he was seven" is worse). Guessing wrong
> makes that character's speech rhythm wrong for the whole book. **One `年龄: 十六` line is the
> cheapest fix.** You can also name it outright with `演员类型: 少年·憨厚` (explicit naming wins).

Source of the limits: the prompts in `ingest/extractor.py` (every field has a hard requirement).
**Going over doesn't error -- it just gets cut** -- so write within the limits, not over them expecting
them all to stick.

**Example** (`samples/zh/03_都市_夜班书店/设定/人物/周迟.md`):

```markdown
Bookshop owner, mid-thirties, former publishing-house editor. No internet, no advertising, no discounts;
he buys books entirely based on "is it bright."

He hands over a book the way a doctor writes a prescription: he doesn't ask what you want; he asks,
"What time have you been going to sleep lately?"

Looks easygoing, but there's one thing he cannot get past -- on the day he resigned, a book he'd
personally handled was made by him, with his own hands, "into something no one would read." His own
books, from that day on, he can't hear.
```

In this passage, "asks 'what time have you been going to sleep'" is **verbal-tic level** concrete
(a hundred times more useful than "speaks wittily"); "his own books he can't hear from then on"
is **secret + goal** fused together.

**About "Appearance day"**

In a character card you can write one line:

```markdown
登场：第 3 天
```

The program accepts: `第3天` / `3` / `三天` / `未登场` (= don't release yet; `后期` / `终局` are synonyms).
**Blank = Day 1.** An unrecognized format is also treated as Day 1 -- guessing "late" makes a character
who should appear fail to appear, and the cost is much higher.

Why this exists: a real-machine run on one book had a character **marked "appears only at the finale"
showing up every day in the "present characters" list** -- scenes had no boundary; nobody was responsible
for "who is here right now."

> ⚠ **The most critical consequence of this**: when a person hasn't appeared yet, if they accidentally
> end up "present", **their secret is effectively public**. So any character whose trump card is saved for
> later must have "登场" written.

**Common mistakes**

| Mistake | Consequence |
|---|---|
| Personality as adjective stack ("smart, kind, resilient, principled") | The model can't tell from this how they act. **Write "how they act"**: mouth that doesn't spare others, soft at heart |
| Verbal tic as filler ("嗯" / "啊") | Adding "嗯" to every sentence is awkward. Write **one of their own lines**: "The numbers don't match" |
| Secret as background ("His origins are complicated") | Nothing to reveal. Write **a concrete fact**: "Three years ago he took the fall for someone else" |
| Goal as state ("wants to become stronger") | Hard to judge whether it's been achieved. Write **an achievable thing**: "Hold onto this building" |
| Only the protagonist has a card | Supporting roles may be empty, but each must at minimum have **identity + personality + goal**, or they're just background on stage |

### 3.5 Locations -- The Program Uses Them for Four Things

**What the program does with them**:

1. **Filter scene-layer settings** ("this scene is at Riverside Teahouse" -> only Riverside Teahouse-relevant
   things appear);
2. **Judge whether to change scenes** (everyone present **all went to a different real location**, then it
   switches);
3. **Provide the day's small-map framing range** (which locations appear today);
4. **At ingest, draw the three-level base map from them** (overall / partial / indoor -- see §3.5b).

**How to write them**: `名称` + `说明` (<= 20 chars). The explanation should be **usable information**,
not literary description -- because the program uses it to judge "what kind of patrons and what events fit this place".

```yaml
- 名称: 临河茶肆
  说明: 临河的茶楼，两层，后院有口井
- 名称: 城东渡口
  说明: 船来船往，天黑就没人了
```

"There's a well in the back yard" is usable (foreshadowing can be buried in the well; it creaks at night);
"antique charm, lingering flavor" is not.

**Two optional fields: for sharper base maps** (added 2026-10-08)

At ingest, the program draws a **three-level base map** (§3.5b) from your location list. If you want the map
to match what's in your head, add these two fields -- **skipping them also works**, the program will guess
from the description and common sense:

```yaml
- 名称: 临河茶肆
  说明: 临河的茶楼，两层，后院有口井
  方位: 城东渡口西边，临着河
  内里: [堂屋, 后院, 井, 柜台]
```

| Field | What it governs | Example |
|---|---|---|
| `方位` | This place's **position on the overall map** relative to others (which side, what's adjacent) | `城东渡口西边，临着河` |
| `内里` | **Indoor-map** rooms/courtyards/objects (room-level) | `[堂屋, 后院, 井, 柜台]` |

> **Why bother**: the `说明` line "two stories, well in the back yard" is understandable (it'll infer "back
> yard" and "well"), but the inference is coarse. Write `内里` explicitly and the indoor map lands in one
> pass -- and the indoor map decides whether "which room a person is in inside the building" can be drawn.
>
> ⚠ These two fields are **position and layout for the base map**, not plot.
> Don't write "a murder will happen here" into `方位` -- that's foreshadowing territory (§3.7).

**Common mistakes**

* **Too few locations.** With only one, the story can only happen in one room (not wrong, but then you
  have to rely on the "detail layer" and "outside people" for variation).
* **Vague location names** ("some room") -> the program doesn't recognize it; scene switches and the
  small map both break.
* **Mismatched location names and character positions**: a character's default position is the opening
  location; if the place they `move` to **isn't in your location list**, the program treats them as
  "shifting to a corner of the same scene" -- no trouble; but if they move between **two places both
  in the list**, it counts as exit / scene change.

### 3.5b Small World Map -- The Base Map Drawn Automatically at Ingest

**What it is**: a **three-level base map generated at ingest and reused across subsequent rounds**, stored
in `设定集/小世界地图.yaml`. You don't write this by hand (even if you do, the program redraws it from your
location list).

**Why it exists**: before this, the small map was **drawn from scratch every day by art** -- the same place
might appear top-left today and bottom-right tomorrow ("map" then became "illustration of the day");
and "which room a person is in inside the building" had nowhere to land. With the base map, art's daily
job becomes **framing from the base map + filling in details**.

**What each of the three levels draws**:

| Level | What it draws | When it goes on screen |
|---|---|---|
| **Overall** | **Position and paths between places** (city / town / village scale) | Today's scenes **span two or more places** |
| **Partial** | **Around one specific place** (river, bridge, street, neighbors) | Today's scenes are **at one place**, and that place has no indoor map |
| **Indoor** | **The rooms and courtyards inside the building** (hall / back yard / well / counter) | Today's scenes are **at one place**, and that place has an indoor map |

> One line: **today's finest level wins**.

**What it looks like at ingest** (you'll see these lines in the ingest log):

```
▶ Freezing local settings bundle -- base map ready: overall yes / partial 3 / indoor 3
```

**Disable / Modify**:

| What you want | How to do it |
|---|---|
| No base map (fall back to "daily fresh placement") | Settings (Tianji) -> **Small Map** -> turn off "Three-level base map" |
| Also generate a layer of **atmosphere background art** (actually painted) | Settings -> Small Map -> enable "Bitmap atmosphere background" (one image per layer, **costs tokens**) |
| Make one place's indoor map more accurate | In that location's `内里:` field, list the rooms clearly |

> ⚠ **The base map isn't life-or-death**: if it can't be drawn (model fails / turned off), the simulation
> still runs -- the small map just falls back to daily fresh placement, and the same place's position may
> drift. The program will say so in the log.
>
> ⚠ **It doesn't invent things out of thin air**: place names in the base map only come from your
> `地点.yaml`; indoor-layer names can only be rooms/objects (no place names allowed). Names the model
> invents are discarded.

### 3.6 Relationships -- Don't Just Write "Relationship", Also Write "Tension"

**What the program does with it**: feeds into the scene layer, and only appears when **at least one of the
two people involved is present**.

```yaml
- 甲: 主角
  乙: 阿枝
  关系: 主仆
  张力: 阿枝一直在试探掌柜的旧事
```

* `关系` should be **neutral phrasing** (holds for both sides): master-servant, master-disciple,
  husband-wife, fellow townsfolk, old acquaintance.
  Writing "he has a crush on her" turns into a description that applies to the other side too, awkward to read.
* `张力` is what really pushes the scene -- **"what is currently taut between them."**
  Relationships with no tension are backdrop.

### 3.7 Foreshadowing -- All Four Fields

**What the program does with it**: feeds into the main-line layer. Unactivated foreshadowing gets listed in
the prompt (a reminder that the reader is still owed something); the *Ending.md* has a section for
**foreshadowing that's still uncollected**.

Fields: `编号` / `内容` / `埋设` / `预计回收`.

```markdown
- **编号** 四 · 柳娘多给的那几文钱：她每次只多给三文，从不多也不少。
```

* One foreshadowing item corresponds to **one specific object or fact** ("three extra coins each time",
"a page trimmed out of an old archive").
* `预计回收` should be a **position** (mid-game / pre-climax / final chapter), not a specific plot.
* The number is for your own matching; the model doesn't care much what the number looks like -- but
  **don't omit it**; you'll need to name it when collecting.

### 3.8 Outline / Story Outline.md -- It Gets Split into "Progress Nodes"

**What the program does with it**: at ingest the outline is split into several **progress nodes**, each
with `name / summary / completion criterion`. During simulation:

* The **current node** enters every character's prompt ("[This Stop] Opening (an uninvited guest at the
  teahouse)");
* Every beat asks the model "is this node's completion criterion satisfied?";
* If yes, it moves forward one slot and opens "do you want to choose a route?".

Hard requirements for splitting nodes (written in the prompt of `ingest/progress.py`):

| Field | Limit | Key point |
|---|---|---|
| Name | **no more than 6 characters** | Concise; recognizable at a glance |
| Summary | **no more than 80 characters** | What happens in this stretch |
| Completion criterion | **no more than 50 characters** | **Must be judgeable**: the model treats it as a yes/no question |
| Span | -- | **How much story time this stop covers** (see below) |
| Length | -- | **How thickly this stop should be written** (see below) |

#### Span and length: novel time is **not uniform**

These two optional fields are the easiest to skip and the most decisive for "does this read like a
novel". A real novel does not write one chapter per day: it may dismiss three months in a single
sentence ("nothing happened for three months"), or spend twenty pages on one confrontation. **A
single event can also span several days** (three days on the road is one event, not three).

Without them the program only has a uniform clock that fills every day, which is what makes a story
read like a log.

| Field | Allowed values | Meaning |
|---|---|---|
| **Span** | `一场` / `当日` / `数日` / `一旬` / `数月` (one scene / the day / a few days / ten days / months) | How much story time this stop covers |
| **Length** | `详` / `中` / `略` / `带过` (full / normal / brief / in passing) | How thickly this stop should be written |

Some combinations and how they read:

| Setting | Reads like |
|---|---|
| `数月` + `带过` | "Nothing happened for three months" -- one sentence |
| `数日` + `略` | Travelling, arrangements, messages -- state it and move on |
| `当日` + `中` | Scene and dialogue; most nodes are this tier |
| `一场` + `详` | One scene written to the bottom (showdown, confrontation, the truth comes out) |

**Length -> beats** (how many beats each stop gets; **a hard cap, not a suggestion**):

| Length | Beats |
|---|---|
| `详` | 40-60 |
| `中` | 15-25 |
| `略` | 3-8 |
| `带过` | 1 |

**Length -> how thick the prose is** (when the day is organized into a novel at wrap-up):

| Length | What the organizer writes |
|---|---|
| `详` | **Write it out**: every act of the material must land in the prose; roughly 20% of the material's characters per piece (capped at 3000 characters a piece) |
| `中` | Normal pace, about 12%; transitions and repeated routine may be merged into one sentence |
| `略` | **Two or three sentences for the whole stop** (no matter how many acts played) |
| `带过` | **One sentence**: how much time passed, where we ended up, what changed |

> Consecutive `略` / `带过` stops are merged into **one montage pass**, one sentence each -- exactly
> how "months pass between stops" should read. Over-long `略` / `带过` passages are **trimmed at a
> sentence boundary** (the prompt alone only holds 40-74% of the time, so this layer is a hard
> constraint). `详` / `中` are **never** trimmed: those tiers require that no event be skipped, and
> the tail is the ending.

> Do **not** mark every stop `详`: all-thick means no contrast, and the reader tires.
> Two adjacent stops may differ enormously (`数月` followed by `一场` is normal) -- that is what a
> novel looks like.

**What happens if you omit them**: the program **infers** (from keywords in the summary and by
counting place names) and writes `推断：跨度、篇幅（程序推的，可改）` ("inferred: span, length --
guessed by the program, you can change it") under that node in `故事进度.yaml`. Your own values are
**never touched**.

**A stop that asks the reader to choose: `选项:` (choices)**

Some places in a story are "here you have to pick a road" (how it ends, who to follow, who gets the
letter). Give that stop an `选项:` field and the **story overview** chart in the Plot panel draws it
as a row of clickable options; pick one and the chart continues down that line:

```yaml
# ⚠ The keys below are the **real** keys in 故事进度.yaml (they are Chinese in the file;
#    the English words are just glosses here).
- id: N08
  名称: The trial              # name
  概要: The retrial opens; Chen Wang must state his final choice in public.
  完成判据: Chen Wang announces his final choice in public.
  选项: [go home, be offered up, keep the door]      # choices
```

- To describe what follows a line, write that option as an object and list the points under
  后续 (`points`), each with 名称 (`name`) + 概要 (`summary`):

  ```yaml
  选项:
    - 标签: go home
      后续:
        - {名称: struck off, 概要: The name is crossed off the register; nobody remembers him.}
    - 标签: keep the door
  ```

- **If you omit it**: the program reads phrasing like "...three roads" out of the summary and notes
  *"these were read out of the summary"* on the chart. **If it cannot read them, there is no choice
  point** -- it will never invent a fork on a straight road.
- Keep each label **under ~8 characters** and avoid possessive particles (that is a sentence
  fragment, not a road name).
- ⚠ The choices **only affect this chart and your record**: which line is actually played is still
  decided by the simulation itself. The field says "these roads exist", not "you must take this one".

**How to write completion criteria**:

| Good | Bad |
|---|---|
| 掌柜出手应付 | 气氛变得紧张 |
| 有人认账 | 真相逐渐浮出水面 |
| 两人公开对峙 | 关系发生变化 |
| 主角得知X的存在 | 主角有所成长 |

How the criterion is written decides **whether the story moves forward** -- if you can't write a
judgeable criterion, this node is never completed, and the simulation gets stuck "at this stop."

We recommend writing the outline in four parts -- **opening, development, twist, resolution**
(the first rule of "Chinese classical chaptering" in the program). Example
(`samples/zh/01_悬疑单元_更漏子/大纲/故事大纲.md`):

```markdown
**起** ｜ The night-watch drum in Pingkang Ward was a whole beat early. That night two "accidents"...
**承** ｜ Shen Yan thinks backward along the water's pace: in the past three years, the city has had
        seven "clock adjustments"...
**转** ｜ That rainy night was his first year in the Calendar Bureau...
**合** ｜ Shen Yan uses his only trick -- slowing the water by one beat -- to scramble his senior's watch...
```

> Tip: chapter files are split by lines matching `第X章 / 第X回 / Chapter N`
> (`ingest/progress.split_chapters`). Write your chapter titles in this format so the progress table can
> line up.

### 3.9 Detail -- The Easiest to Overlook, but Most Affects "Every Day"

**What this is**: objects, customs, verbal tics, small rules, local color, who owes whom a word.
They're **not summarized**; they're singled out and stored in `细节设定.yaml`, in the **detail layer**,
**may enter the prompt every day**.

**What the program does with it**: each time it picks at most **4 entries** (each <= 70 chars) into the
prompt, filtered by "where is this scene / who's present".

**Why it's worth writing specifically**: this is the real fuel of "daily stories". Compare:

| Only big background | Add the detail layer |
|---|---|
| Characters can only "look, wipe, wait" (real logs have shown "look" 627 times, "wipe" 565 times) | There are things to touch, rules to break, words to say |
| Each day's scene relies on the director improvising an event | The scene grows out of the setting itself |

**How to write it**: one fact per entry, specific enough to hold in your hand.

```yaml
- 名称: 缺角的紫砂壶
  内容: 柜上那把壶缺了个角，谁也不许动
  场合: 临河茶肆
  涉及: 主角
- 名称: 更漏只校一次
  内容: 店里更漏一夜只许校一次，校错要赔
  场合: 临河茶肆
```

| Good | Bad |
|---|---|
| 缺角的紫砂壶，谁也不许动 | 楼里的陈设很有年头 |
| 更漏一夜只许校一次，校错要赔 | 这里的人守规矩 |
| 渡口天黑之后不再开船，敲也不开 | 渡口晚上很冷清 |

The difference: the good entries are **things that can be violated** (he's determined to touch that
chipped teapot / he goes knocking on the dock gate at midnight).

**Companion practices**:

* Write **8-15 entries** for best results (the program only allows 4 per pass, so the more you have,
  the more you need to mark `场合`);
* Tag each with `场合` or `涉及`, otherwise it'll be displaced by small things from elsewhere;
* Have **one that recurs** (Lao She's "one small prop to carry everything") -- such items will be carried
  by the **props** position in the crew into the image prompt, and really appear on screen.

> You don't need to create a dedicated file for details: at ingest the program will **extract them**
> from your existing setting documents (one item in the extraction output is called "细节"). But you
> must have **written them somewhere** in your documents, otherwise there's nothing to extract.
> Easiest place: add a section "the trade's craft" at the end of Worldview.

### 3.10 Chapter Text -- It's the Source of "Style"

**What the program does with it** (at ingest):

1. **Extract the style card**: reads your chapter text, summarizes sentence length, narrative distance,
   vocabulary preferences, dialogue proportion, viewpoint discipline, chaptering preferences, plus a
   **5-10-item list of AI-flavor forbidden words** (the most jarring stock phrases in this book). During
   simulation this line enters the prompt ("[Style] sentence length = short-and-medium; distance =
   close-third limited; forbidden = ...").
2. **Align the progress table**: see which chapter you've reached, match it to a node, continue from there.

**So**:

* To make the simulation sound **like you write**, give it **one chapter you're most satisfied with**
  (one is enough). The program will also **take 1-2 passages as a style example** (`FEWSHOT_FROM_NOVEL`,
  default on) -- the most direct way to "teach this book how to talk".
* **Keep your good passages**: they are the source of the style card's examples.
* Only outline, no chapter text -> the style card can only cobble together from the full settings, and
  the result will tend toward "generic voice".

### 3.11 Genre and Style -- Decides Which "Craft Book" Is Read

**The genre card** (determined at ingest, also specifiable manually in the project studio) has three axes:

```
Genre (mystery / xianxia / urban / alternate history / romance / sci-fi ...) x
    Structure (case-of-the-week / progression-flow / ensemble / three-act ...)  x
    Channel (male-channel / female-channel / publishing-oriented ...)
```

It decides **which "craft book" the program hands to each AI position** (the `playbook映射` in
`craft/genres/*.yaml`). For example, the "alternate history" card maps to
`three-act structure · political-strategy layout · grass-snake-ash-line`, so the director pulling events
and the novelist writing sample chapters read exactly those rules.

> If your project genre doesn't have a corresponding profile, the program falls back to **the mapping built
> into the genre card itself** -- no craft will be missing. To make it more specific, add your own genre
> profile under `craft/` (or point `CRAFT_LIBRARY` at your own folder).

**The style card** is **extracted automatically** (from chapter text), but you can **override** it: in the
project studio there's a "style source" option -- pick "use the extracted style card / plain narrative /
use my hand-written style". A hand-written style goes straight into the prompt.

---

## 4. What the Program Will "Do" to Your Settings (Hard Requirements)

This section covers "technical facts you must know". **Not following them won't error, it just silently drops a piece**.

### 4.1 Where Your Original Text Goes: A "What Survives" Table

This is the section of this guide **you should remember most**. Once you put your settings into the
reference folder, at ingest they take two paths:

| Which path | Which content | Result |
|---|---|---|
| **Verbatim** (byte-for-byte) | **Rule-class documents** (filename contains "规则/铁律/守则...") | Whatever you write is what the model sees (2000-word quota) -> **put hard constraints here** |
| **AI summarized** (compress + rewrite) | All other setting documents -> worldview, characters, locations, relationships, foreshadowing, details | Worldview compressed to **~120 words**, location description 20 chars, character fields 30-40 chars |

**Once summarized, anything beyond 120 words in your original isn't seen by the simulation**
(the original stays in your folder, the simulation just doesn't see it). This implication is hard:

> **Long documents lose their "hard requirements."**
> If you write "no supernatural elements" in the third paragraph of your worldview, it most likely won't
> survive -- or gets rewritten as something soft like "the tone is realistic" -- and "soft" equals no
> constraint power.

**Three ways to make your settings survive**

| Approach | What it suits | How to do it |
|---|---|---|
| Write into a **rule file** | Hard constraints, world iron rules, narrative discipline | Make a separate `设定/顶级规则.md`, 5-10 entries |
| Write into the **detail layer** | Objects, customs, small rules -- daily-use things | Add a "trade's craft" section at the end of Worldview; one fact per entry (they get extracted separately at ingest) |
| **Manually edit the settings bundle** | You actually need a full background passage carried verbatim | See the technique below |

**Technique: Manually edit the settings bundle**

After ingest, the program freezes the summarized result into the project's `设定集/` (`世界观.md`,
`人物.yaml`, `地点.yaml` ...). You can **directly edit these files**:

* Add back the points that got compressed away (e.g. the two most important sentences of that
  background passage);
* Make a character card's field more accurate (the seven fields are what the simulation actually reads).

After editing, **start a new round** (click "起 笔" to run another round) re-freezes a fresh copy; what you
edited then goes into the simulation. Note: **the currently running round is unaffected** -- each round uses
its own frozen snapshot. That's intentional (changing settings shouldn't affect the round that's already running).

> Many people don't know about this route, but it's the most direct: **instead of complaining "my writing
> got compressed away," after ingest go look at the settings bundle and put back what's important.**

### 4.2 The Character-Limit Table (Going Over Gets Cut)

| Content | Limit | Source |
|---|---|---|
| Worldview | ~120 words (after summary) | `ingest/extractor.py` |
| Location description | 20 chars | same |
| Location 方位 / 内里 | Not extracted (**hand-write** in the settings bundle, see §3.5) | `world/atlas.py` |
| Character 身份 / 性格 | 30 chars | same |
| Character 秘密 / 目标 / 红线 | 40 chars | same |
| Relationship / foreshadowing | max 8 entries each, 25 chars per entry | same |
| Top Rules | max 6 entries (extraction path) / 2000 chars (in prompt) | same / `world/state.py` |
| Detail | max 8 entries (extraction), 40 chars per entry | same |
| Progress node Name / Summary / Criterion | 6 / 80 / 50 chars | `ingest/progress.py` |
| Style card fields | 20 chars each; 5-10 forbidden words, each <= 6 chars | `ingest/style.py` |
| Full text sent for extraction | 20000 chars (**whole files dropped by importance**, not head-and-tail) | `_MAX_CONTENT` in `ingest/extractor.py` (`CAPS` in `ingest/preview.py` mirrors it) |

> ⚠ **Not every file enters that window** (changed 2026-10-27): the `06_地图` and `写作参考`
> directories, plus anything classified as `正文` (body) / `大纲` (outline), **each have their own
> channel** and do not spend this budget -- they are still scanned (drawing still reads the map
> book), they just don't crowd out extraction. The rest is ordered
> `rules -> characters -> foreshadowing -> settings -> misc`; when it doesn't fit, **whole files
> are dropped from the tail** and named in the ingest log (never silent, never cut in half).

> **Going over the limit is not an error**, it's "won't fit in". If the output gets truncated at ingest,
> the program tells you on the UI ("already salvaged by closest-closed prefix: N characters saved"),
> and prompts you to check the settings bundle.

### 4.3 Where a Sentence Appears (The Whole Picture a Character Sees)

When a character makes a decision each beat, the material they see assembled looks like this
(`world/state.py` + `agent/core.py`):

```
[Top Rules · inviolable]   <- your rule text verbatim (up to 2000 chars)
[Worldview]                <- big background: only on Day 1 / climax / every 3 days is full text expanded; content is the summarized ~120 words
[Main-line] [Here] [Small stuff]  <- story line / progress / foreshadow · this location and relationship · useful small things today
[Genre] [Style]            <- what genre + how to talk (incl. AI-flavor forbidden words)
[Today's script]           <- what today's scene is doing + what's assigned to me
[This stop] [Today's plan] [What you want]  <- three layers of goal (closest first)
[Recap]                    <- what happened in recent days (<= 240 chars)
[Recent memory]            <- the five things they personally just experienced
```

From this chart you can derive three things:

* **Rules and worldview sit at the top** (highest weight) -- to control the simulation, write in these two
  places; and of them **only rules are carried verbatim**, so the most important constraints go into rules.
* **Characters do not see "the full text of the settings."** What they see is filtered fragments
  (worldview only 120 words; details 4 entries a pass). So "is this useful today?" matters more than
  "is this well written."
* **`[Small stuff]` is the only line that's "every day"** -- it's the detail layer. If you want daily
  variation, this slot needs to have stock.

### 4.4 The Linked Relationship Between "Secret" and "Appearance Day"

A character's `秘密` (secret) **goes into the prompt** (it's what they "know in their heart"). That's fine.

The issue is with **people who haven't appeared yet**: the program judges "who's present" by "are they at
this location". A character "only appearing on Day 10", if no "Appearance Day" is written, might end up
present from Day 1 -- and their secret will then be **publicly** mentioned in every conversation.

**Conclusion: any character whose trump card is saved for later must have "Appearance Day" written.**

### 4.5 The Ingest Check-Up and the Three Tiers

At the end of ingest, the program assigns your materials a tier (`ingest/pipeline._assess_tier`):

| Tier | Condition |
|---|---|
| **Gold** | Characters >= 2, with story reference, with secrets or verbal tics, with foreshadowing list, with chapter text >= 1 chapter |
| **Silver** | Characters >= 2, with story reference (lacking secrets / foreshadowing / chapter) |
| **Bronze** | Otherwise |

The **gap list** tells you what's missing, and you can **let the AI fill it in** (these items it can fill):
missing foreshadowing list, characters missing secrets/verbal tics, missing outline, worldview too short
(<40 chars), missing character fields.

> ⚠ **"At least 2 named characters" and "chapter text" it cannot fill** -- because AI cannot invent
> your characters and your chapter text; making them up would be fabrication, which is worse than missing.
> These two you must write yourself.
>
> The way to fill in is **append-only, never overwrite**: write to the end of your file (with a dated
> section), or write a new `AI补全设定.md`. **The program never overwrites your original.**

---

## 5. Theory References: The Ones the Program Actually Uses

The program includes six "craft bookshelves" (`craft/playbooks/`), distributed by role:

| Shelf | Theory source | Who reads it | Representative entries |
|---|---|---|---|
| **Chinese Classical Chaptering** | Jin Shengtan, Li Yu, Aristotle, Propp | Novelist, researcher | 起承转合 · 草蛇灰线 · 伏脉千里 · 横云断岭 · 立主脑减头绪密针线 · 章回钩子 · 志怪笔法 · 权谋布局 |
| **Western Screenwriting Canon** | McKee, Field, Snyder's *Save the Cat*, Truby, Vogler, Aristotle | Novelist, screenwriter | Conflict three levels · Expectation gap · **Scene = value shift** · Three-act · Plot point · 15 beats · Hero's journey · Reversal & discovery · **Suspense engine** · Character arc · **Worldbuilding** · Ethical inquiry |
| **Web Novel Methodology** | Qidian / Jinjiang top works and web-novel craft theory | Novelist, publicity, writers' room | Golden three chapters · Expectation management · Climax cycle · Empathy discipline · Progression feedback loop · Map change · Channel poison points · Emotion curve · Misunderstanding creation · Sweet strike |
| **Drama & Stage** | **Lao She's *Teahouse* stage practice**, Stanislavski, Baker's *Dramatic Technique*, Archer's *Play-Making* | Screenwriter, script supervisor, props, art | **One sentence to stand a person up** · Entering and exiting both carry drama · Write time through scene · Ensemble staging · **One small prop to carry everything** · Stage notes written for the actor · One shift per scene · Shootability check · Monologue restraint |
| **Character & Dialogue** | A breakdown of a serialized Tomato novel's method (contrasting persona / speaking-is-identity / weak-counter), Stanislavski, Baker, McKee, Lao She's dialogue theory | **Actor**, novelist, screenwriter, language editor, reviewer | **Speech is identity** (lines any character could say have not been written onto a real person) · Contrasts meant to be visible to the reader · One line of dialogue does four things · The weak use the other's logic to strike back · Ensemble distinguished by layer of obsession · Pauses and non-answers are also dialogue · Title change signals relationship change · **Dialogue is not a straight line** · **Not every line needs a response** · **Volume is scarce** · **One thing at a time** · **Pauses fall on paper** · **Speak differently to different people** (the latter six added 2026-10-12: make dialogue **sound like a real person** -- hesitate, don't respond to every line, don't shout easily, one thing at a time, pauses on paper, change face for the listener) |
| **Scene & Space** | **Open-source project structural practices** (Azgaar / OSMnx / momepy / Edgar / graph-dungeon-generator / DeepFloorplan / Streetmix / depthmapX, see `developers/docs/外部借鉴/07_地图与空间.md`) | Novelist, screenwriter, writers' room, director, art, props, script supervisor | **Inside and outside distinguished first** (the well is in the yard; the counter is inside) · Rooms are maps not points · Streets are sequences not points · Doors are boundaries not decoration · Movement needs a basis · What's visible is computable · Lively vs. quiet determined by connectivity · Base map first, then framing |

> ⚠ The sixth shelf is not like the other five: the first five answer "how should the story be told";
> this one answers "**where** does what happens actually happen" (plan / bearing / inside-outside / movement).
> Its source is also not a single book, but **structures from open-source projects that can be verified** --
> we only borrow the methods, not the style.

**Where each theory used in this guide maps back**

| Theory | Source | Where in this guide | How the program uses it |
|---|---|---|---|
| Setting is a structural element, not backdrop | "Worldbuilding" in Western Canon | §1.1 | Director pulling events, novelist writing sample chapters see it |
| One small prop to carry everything | Lao She *Teahouse* | §1.3, §3.9 | Detail layer + props position (into image prompts) |
| Grass-snake ash-line / Long-arcing vein | Jin Shengtan | §1.4, §3.7 | Foreshadowing list + unactivated items in prompt |
| One shift per scene (Scene = value shift) | Baker / Archer / McKee | §3.8 (completion criterion) | Screenwriter shot-by-shot: "each beat must state this shift" |
| One sentence to stand a person up | Lao She *Teahouse* | §3.4 (verbal tic) | Lines spoken by the person themselves; framework only gives "what's wanted" |
| 立主脑, 减头绪, 密针线 | Li Yu | §3.8 (node split) | Progress table + subplots can't dominate the main line |
| Suspense engine (one unresolved question per scene) | Western Canon | §3.7, §3.9 | Division of foreshadowing and detail |
| Expectation management / Climax cycle | Web Novel Methodology | §3.11 (genre card) | Genre card mapping -> director's pulling-event preferences |
| Shootability check (who / where / does what / says what) | Drama & Stage | §3.9 | Screenwriter shot-by-shot + script supervisor continuity |
| 写时间通过场景 | Lao She *Teahouse* | §1.3 | Use objects/environment to write time, not make characters speak the year |
| Speech is identity | Dialogue theory (Stanislavski / Baker) | §3.4 (verbal tic & dialogue) | Actor reads "Character & Dialogue": before writing, decide how this person speaks |
| Weak use the other's logic to strike back | Dialogue theory | §3.4 | Actor reads same shelf: weak uses the other's argument against them, doesn't tantrum |
| **Dialogue is not a straight line** / **Not every line responds** / **Volume is scarce** / **One thing at a time** / **Pauses on paper** / **Different face for the listener** | Dialogue theory + common sense of how people actually speak (added 2026-10-12) | §3.4 (verbal tic & dialogue) | Actor, novelist, screenwriter, reviewer **all read**: dialogue must **sound like a real person** -- hesitate, not every line needs a response, don't shout easily, one thing per line, pauses on paper, change face for the listener |

> These aren't decorative. At runtime the program **actually composes them into the corresponding
> position's prompt** (`crew/agents.craft_block`), so "which school of writing you want the simulation to
> resemble" largely depends on **which entries the genre card maps to**.

---

## 6. Self-Check Checklist and Templates

### 6.1 Twelve Checks After Writing Settings

Don't look at the next section until you've checked these off.

| # | Self-check | What happens if you don't pass |
|---|---|---|
| 1 | Every hard constraint is in a **rule file** (not scattered through Worldview) | Gets summarized away, condition gets distorted |
| 2 | Rules are **5-10 entries**, each checkable | Too many fight each other; too vague to enforce |
| 3 | Worldview original is **300-800 words**, written as "rules" not "history textbook" | The summarized 120 words will be all fluff |
| 3b | **The rules that actually do work are in a separate rule file** (not only lying in Worldview) | They get compressed away, no constraint power in the simulation |
| 4 | Character cards have **identity + personality + goal** (supporting roles too, at minimum) | They're just background on stage |
| 5 | At least half the characters have **secrets or verbal tics** | Ingest tier won't move up; characters have no voice |
| 6 | Late-appearing characters have **"Appearance day"** written | Their secret is public from Day 1 |
| 7 | Locations include **usable information** (what's there, what can be hidden), not literary description | Scene changes, small maps, and events all fail to land |
| 8 | Every relationship has **tension** (what's currently taut) | The relationship is backdrop |
| 9 | Each foreshadowing entry has **concrete object/fact + bury + expected recovery** | Can't judge whether it was paid off |
| 10 | The completion criterion for each outline node is **judgeable** | The story gets stuck "at this stop" |
| 11 | You've written **8+ "actable small things"** (objects / customs / small rules) | Every day can only "look, wipe, wait" |
| 12 | You have **at least one chapter of your own writing you're satisfied with** | Style card can only cobble, result tends toward generic voice |

### 6.2 Template Skeleton (You Can Lay It Out As-Is)

```
我的小说/                          <- reference folder (this is the "Gold tier" structure)
├── 设定/
│   ├── 世界观.md                  <- 300-800 words: rules + scene
│   ├── 顶级规则.md                <- 5-10 hard constraints (verbatim, the most important)
│   ├── 地点.yaml                  <- 3-5 places: name + description (optional 方位 / 内里, see §3.5)
│   └── 人物/
│       ├── <protagonist>.md
│       ├── <side-A>.md
│       └── <side-B>.md
├── 大纲/
│   └── 故事大纲.md                <- opening / development / twist / resolution four parts
├── 伏笔.md                        <- number + content + bury + expected recovery
└── 正文/
    └── 第一章 <title>.md          <- one chapter is enough (the main source of the style card)
```

Skeleton for the four files:

**`设定/世界观.md`**

```markdown
# Worldview

<one sentence: when, where, and what this line of work is about>

## The Trade's Rules
- <rule one: what can and can't be done>
- <rule two>
- <rule three>

## How Things Stand
<two or three sentences: what the current situation is, what everyone is privately worried about>
```

**`设定/顶级规则.md`**

```markdown
# Top Rules

## World Iron Rules
- <what absolutely won't happen>
- <what must cost something>
- <whether there are supernatural forces, where the boundary is>

## Writing Method
- <structural discipline: how to close one chapter / one case>
- <character discipline: who solves problems by what means, what's not allowed>
- <narrative discipline: viewpoint, monologue, what's not allowed to write>
```

**`设定/地点.yaml`**

```yaml
# 3-5 places is enough. Description <= 20 chars; write "usable information"
# (how many floors, what's there, when it's busy)
- 名称: <place one>
  说明: <e.g. riverside teahouse, two stories, well in the back yard>
  # The two lines below are optional -- used by the base map at ingest (see §3.5 / §3.5b)
  方位: <e.g. by the river, west of <place two>>
  内里: [<hall>, <back yard>, <well>, <counter>]
- 名称: <place two>
  说明: <e.g. boats in and out, no one after dark>
```

> ⚠ The program **will not** guess locations from chapter text -- either you write them in this file,
> or at ingest the AI summarizes them out of your other setting documents (then it's only `名称` + `说明`).
> `方位` / `内里` **are only read from this file you wrote by hand**.

**`设定/人物/<name>.md`**

```markdown
# <Name>

<identity: one sentence>

<personality: written as "how they act", not a stack of adjectives>
口癖: <one of their own lines>
目标: <an achievable thing>
秘密: <a concrete fact> (optional)
红线: <what they absolutely won't do> (optional)
登场: <day N / 未登场> (optional, blank = Day 1)
```

**`大纲/故事大纲.md`**

```markdown
# <Book title> · Story Outline

> <one-line pitch>

**起** ｜ <how it opens, what the first trouble is>

**承** ｜ <how the trouble gets more complicated>

**转** ｜ <what gets turned around, at what cost>

**合** ｜ <how it closes; who gets what, who loses what>
```

### 6.3 Three "Bad to Good" Rewrites

**① Worldview: from history textbook to actable situation**

```markdown
<!-- bad -->
The Tang dynasty is one of the most prosperous periods in Chinese history; Chang'an was the
world's largest city at the time, with a population over a million; the ward-market system was
strict, night curfew enforced...

<!-- good -->
Tang, Chang'an. The hour in this city is not read from the sky, it is heard from the night drum;
the drum is set by the water clock of the Imperial Astronomy Bureau. The water clock is a set of
copper pots; water drips from the one above into the one below; the floating arrow points to the
graduation -- one beat faster in the water, and the whole district's day starts one beat earlier.
The trade's rule: the water clock may only be calibrated, never altered; one alteration requires
a record, a signature, a seal.
```

What's changed is **the viewpoint**: from "introduce this city" to "how this city's rules press down on the people of this line of work."

**② Character: from label to something judgeable**

```markdown
<!-- bad -->
Personality: smart, calm, kind, principled, rich inner life.

<!-- good -->
Speaks little, hands extremely steady; can fine-tune the floating arrow to half a li while talking.
Looks cold, but actually protects his own: when someone on his team gets in trouble, he takes the
fall first, then quietly asks what happened.
Verbal tic: "Wait a moment."
```

"Can fine-tune the floating arrow to half a li while talking" -- that one line gives **skill + personality
+ identity** all at once, and can be staged during the simulation (others can marvel, ask him to fix things,
use it to test him).

**③ Detail: from atmosphere to things you can touch**

```markdown
<!-- bad -->
The teahouse has an old-world feel; the decor is plain and rustic; the patrons chat in low voices;
the atmosphere is calm.

<!-- good -->
The chipped Yixing teapot: the pot on the counter has a chipped spout; no one is allowed to touch it.
Calibrate-the-clock once: the in-shop water clock may only be calibrated once per night; the one on
duty pays if it's wrong.
Dock-after-dark-no-ferry: the dock stops running ferries after dark; knocking won't open it.
```

All three can be **violated**, and "can be violated" is "can be dramatized."

---

## 7. Advanced: Making Settings and Simulation Mesh

### 7.1 Settings Are "Fuel", Not "Specification"

Once the simulation starts running, every day the program asks a few AI positions the same question:
**"what do we need so that the next stretch of the scene can play out?"** Your settings are their
**only source material**.

So there is a very practical standard for judging whether a setting is good:

> **Can it answer "what to do with today's scene"?**

"This city has perpetual rain" -- can only give an extra line of "rain" to an environment cue.
"The dock stops running ferries after dark; knocking won't open it" -- can directly spawn a scene:
he must arrive before dark, or he knocks, and the rule inside says it cannot be opened.

### 7.2 The Detail Layer Is "Daily Fuel"

After tens of beats of simulation, if you find the screen is full of "look, wipe, wait," the cause is
**nine times out of ten too little fuel**. Top up in this order:

1. **Add details**: 8-15 actable small things (objects / customs / small rules);
2. **Add locations**: two or three other places to go to (otherwise characters have nowhere to go);
3. **Add "outsiders"**: you don't need to write them -- but **the extras position** will reference your
   settings when generating people. If your worldview clearly says "what this trade's people live on",
   the outside customers that come in will be on-topic;
4. **Add relationship tension**: when two people have something taut between them, they probe each other
   (that's the most enduring drama).

### 7.3 The Crew Can Only Add to Two Layers

The program's AI positions (director, novelist, screenwriter, etc.) hold a **writers' room** daily:
discussing "to make the next stretch play out, what small settings should we add?" But their permissions
are locked:

| Layer | Can the crew touch it? |
|---|---|
| World layer (big background, rules) | **No** -- can't even add one entry |
| Main-line layer (outline, progress, foreshadowing) | **No** |
| Scene layer (locations, relationships) | Can add |
| Detail layer (objects, customs, small rules) | Can add |
| Character layer | Not allowed |

And every entry they add **must have a scope** (limit to location / limit to person / limit to time) --
leave all three blank and it means "active everywhere," which is effectively modifying your overall setting;
**rejected on the spot**.

What they accept is stored in `临时设定.md`, **physically isolated from your settings bundle**:
`世界观.md`, `顶级规则.md`, and the character cards are never modified.
Want to make one of them "official," just edit your own file accordingly.

> To disable the writers' room: in Settings (Tianji), `CREW_SETTING_TALK`.
> To also disable the setting-layer split (revert to old behavior): `SETTING_LAYERS`.

### 7.4 How to Tell Whether Your Settings Are Good

Once the simulation is running, a few files in the run folder are **check-up reports for you**:

| File | What it answers |
|---|---|
| `分层设定.md` | **When does each setting appear, who does it affect, how heavy is its weight** (this is the page to read first) |
| `临时设定.md` | What the crew felt was missing, what they added, what they rejected (the same kind repeatedly added means your settings lack that category) |
| `场记报告.md` | Where today's plot doesn't line up with prior context / settings |
| `当天地图.md` / `美术指导.md` | Whether your locations are specific enough, whether the visual style drifted |
| `结局.md` | **Unresolved threads** (uncollected foreshadowing gets its own section) |
| `可转正群演.md` | Recurring extras (whether to give them a character card is up to you) |

**The most useful reading**: start with `分层设定.md`.
If you wrote three thousand words of worldview but **the World layer cell only has ~120 words or so**,
you know those words aren't normally appearing in front of characters -- either accept that it's just
"climate," or move it into **an actable entry** (write it as detail, or as a rule).

### 7.5 The Last Sentence

This program isn't an automatic novelist. It **takes the world you've written and replays it forward
under your rules**, producing material you can rewrite, compare against, and continue from.

So whether your settings are good, the standard is a single one:

> **If someone else picked up this settings bundle, would they know "what today's scene should be"?**

If yes, it's enough.

---

## Appendix A: Field Cheat Sheet

| File | Field | Limit | Who reads it |
|---|---|---|---|
| 世界观.md | Whole file | ~120 chars (after summarization into prompt; original 300-800 chars) | World layer; every beat (normally one line) |
| 顶级规则.md | Whole file | 2000 chars (verbatim) | Front of everyone's prompt |
| Character | Name / Identity / Personality / Verbal tic / Secret / Goal / Red line | 30 / 30 / 30 / 40 / 40 / 40 chars | Personality card (every beat) |
| Character | Appearance day (optional) | -- | Decides which day they appear when assembling |
| Location | Name / Description | 20 chars | Scene layer + scene change + small map |
| Relationship | A / B / Type / Tension | 25 chars | Scene layer (when one of them is present) |
| Foreshadowing | Number / Content / Bury / Expected recovery | 25 chars, max 8 entries | Main-line layer + uncollected reminder |
| Outline -> Node | Name / Summary / Criterion | **6 / 80 / 50 chars** | Main-line layer (asks every beat if criterion is met) |
| Outline -> Node | **Chapters** (minimum chapters for this station) | integer 1-20; falls back to the length tier if omitted | **Hard gate**: the station will not advance until this many chapters are played |
| Outline -> Length plan | Total chapters / Total words / Words per chapter | any positive integer (`75k` is accepted too) | Daily word target (soft target, not a gate) |
| Detail | Name / Content / Where / Who | Content 40 chars; 4 entries per pass | Detail layer (every day) |
| Chapter | -- | -- | Style card extraction + progress alignment |
| Genre card | Theme / Sub-genre / Structure / Channel | 20 chars each | Decides which craft book is read |
| Style card | Sentence length / Narrative distance / Vocab preference / Dialogue ratio / Viewpoint discipline / Chaptering preference / AI-flavor forbidden list | 20 chars each; 5-10 forbidden words | The "[Style]" line in the prompt |

## Appendix B: Filename Keywords (Determines Classification)

| Category | Keywords |
|---|---|
| Rule | 规则, 铁律, 铁则, 守则, 法则, 戒律, 准则, 准绳, 禁忌, 契约, 规范, rule, constraint |
| Character | 人物, 角色, character, person |
| Outline | 大纲, outline, 剧情, 梗概 |
| Foreshadowing | 伏笔, 悬念, 线索, foreshadow |
| Chapter | 正文, 章节, 第X章, chapter, 故事 |
| Setting | 设定, 世界观, 背景, world, setting |

> Match order is **top to bottom**, first hit wins. So `设定/顶级规则.md` is classified as **rule**.
> No keyword hit -> misc (content still goes to the AI, but not treated specifically as chapter or outline).

## Appendix C: Ready-Made Writing References

The program bundles six **original** sample projects (`samples/zh/`, one per genre, free to quote and modify):

| Folder | Genre | What's worth looking at |
|---|---|---|
| `01_悬疑单元_更漏子/` | Mystery · case-of-the-week | **Model rule file** (world iron rules + case-solving discipline); foreshadowing style |
| `02_玄幻修仙_借山道人/` | Xianxia | How the setting becomes a situation ("borrow and you must return, recorded on the borrower") |
| `03_都市_夜班书店/` | Urban | **Border of supernatural settings** (single supernatural ability + its upper limit + no punching through) |
| `04_历史架空_河工疏/` | Alternate history | How one rule directly creates a dilemma ("alteration" itself is a capital crime) |
| `05_言情_灯花记/` | Romance | Meet only once a year: how a limit creates tension |
| `06_科幻_回声站/` | Sci-fi | How a single scene + single character sustain a long-running simulation |

They are all laid out in the **Gold tier** structure; you can pick one and use its folder as the input folder
to try the simulation right away.

## Appendix D: Source of "What the Program Does" in This Guide

| Statement | Code location |
|---|---|
| World-layer partitioning and appearance timing | `world/layers.py` (`LAYERS` / `select` / `render`) |
| Big background 140 -> 900 chars; detail 4 entries x 70 chars | `world/layers.py` (`CANON_BRIEF` / `CANON_FULL` / `DETAIL_MAX_ITEMS`) |
| **What the simulation reads is the ~120-word summarized worldview** | `ingest/pipeline.py` (`_freeze` stores `settings["世界观"]`) + `ingest/extractor.py` ("worldview <= 120 words") |
| Whether and when settings bundle hand-edits take effect | `sim/setup.py` (`freeze_settings_into_run`: frozen ones are **not overwritten**) |
| Prompt assembly order for characters | `world/state.py` (`world_prefix`) + `agent/core.py` (`decide`) |
| Limits for each field | `ingest/extractor.py`, `ingest/style.py`, `ingest/genre.py`, `ingest/progress.py` |
| Full text limit for extraction | `CAPS` in `ingest/preview.py` |
| How filenames get classified | `_CATEGORY_RULES` in `ingest/scanner.py` |
| Verbatim rule text | `collect_rules` in `ingest/pipeline.py` |
| Three-tier rating and gap list | `_assess_tier` in `ingest/pipeline.py`, `scan_issues` in `ingest/repair.py` |
| Progress node fields and limits | `_BUILD_PROMPT` in `ingest/progress.py` |
| Chapter-splitting rule | `split_chapters` in `ingest/progress.py` |
| The gate for "crew can only write two layers" | `world/layers.py` (`CREW_WRITABLE` / `admit_new`) |
| Six craft bookshelves and which position reads which | `craft/playbooks/*.yaml`, `SHELVES` in `crew/agents.py` |
| Genre card -> craft entry mapping | `craft/genres/*.yaml` (`playbook映射`), `craft/craftmix.py` |
