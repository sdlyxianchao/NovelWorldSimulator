# Novel World AI Simulator

> ## ⚠ First, what it is **not**: this is **not** an "AI writes your novel" tool.
>
> It is a **novel-writing assistant**, and it has exactly one moment of use —
> **when you are stuck and do not know where the plot should go next, let it play the current
> situation forward**: to see what these characters of yours **would do, would say, and where they
> would push things** in that situation.
>
> What comes out is **not finished prose**. It is **a few paths you can choose between**. You pick
> the direction, and you write the words.

**One-line positioning**: a plot simulator and a testing ground for your settings. **Not** an AI
ghostwriter, **not** one-click finished chapters.

| When you use it | What it gives you |
|---|---|
| Halfway through, and you don't know what happens next | It plays the situation forward and lays out a few possible turns |
| You can't tell how this character would react right now | He speaks and acts from his own memory, habits and secrets |
| You want to know whether a subplot holds up | It runs a few days past this node to see if the story collapses on its own |
| A character is starting to sound unlike himself | Put him in different situations and listen, then fix his character card |

> It does not write for you, and it does not decide for you — it only **plays the situation one
> turn further**, so that you have something to choose from.

[中文](README.zh-CN.md) | [Configuration Guide](Configuration_Guide.md) | [Configuration Classification](Configuration_Classification.md) | [User Manual](User_Manual.md) | [Complete Use Guide](Complete_Use_Guide.md) | [Settings Writing Guide](Settings_Writing_Guide.md) | [Script Output Format](Script_Output_Format.md) | [Cost Saving Guide](Cost_Saving_Guide.md)

---

## What It Is

**A novel-writing assistant — a plot simulator that runs inside your own settings.**

Give it a folder containing your settings and drafts. Within **your** rules, it plays the story forward and produces material you can **rewrite, compare against, and continue from**. It does not write the novel for you, and it does not make decisions for you — it is a **material generator** and a **testing ground for your settings**.

**What it does**
- Reads your settings, outline, character cards and chapters; extracts world and characters
- Plays the plot forward within the bounds of your settings; writes each story day to disk
- Produces story documents, run summaries, outline suggestions, and "what if it went this way" comparisons

**What it does not do**
- It does not produce publish-ready prose
- It does not ramble endlessly — by default there is a clear progress table and an endpoint
- It does not overwrite your drafts (the program never writes back into your project folder)

**Try a ready-made one first**: the `samples/` folder in the program directory holds **one
original story per genre** (mystery / case-of-the-week, xianxia, urban, alternate history,
romance, science fiction), each written **in Chinese and in English**. Point Import at a
**single story folder** (e.g. `samples/en/01_mystery_the_water_clock/`) and run it — not at
`samples/` or `samples/en/`, or all six will be read as one book. Full list in
[User Manual 6.1](User_Manual.md).

These six are **worked-out examples on the Gold standard**, not placeholders: every outline is
**3400+ characters**, the Chinese and English versions line up station by station, and each
station spells out its three fields (done-when / climax / beats), plus a section on the order of
the reveals and a set of rules for humour. See [`samples/README.md`](samples/README.md).

---

## Watch One Run

![From launch to export: one complete run](assets/images/demo/walkthrough.gif)

That is **one real run, start to finish** — no cuts, no staging: splash → start screen → picking
the book → first stroke → the middle column accumulating day by day → the map → stopping →
wrapping up → exporting. About 35 seconds (47 screenshots composited in capture order; step-by-step
text is in `User_Manual.md`).

Worth noticing:

- **The middle column does not appear all at once** — it grows one beat at a time. The
  "Crew Agents" column on the right shows **who is working**; "working" and "handed in" are two
  states of the same row.
- **Stopping is not instant** — the wrap-up runs continuity → publicity → review → retrospective →
  tidy → export, which takes tens of seconds to a few minutes. It is not hung.
- The **map** at the end is that day's world state, not an illustration.

---

## What You Get

When a run finishes (or whenever you stop it), your project folder contains:

| Output | Contents | How you can use it |
|--------|----------|--------------------|
| **Daily narrative** | Full narrative split by story day | Pick usable passages and rewrite them into your manuscript |
| **Story document** | Timeline / key scenes / highlights / character arcs / foreshadowing status | Read once for inspiration, check whether any foreshadowing was missed |
| **Run summary** | Run overview / storyline / key plot / character performance / suggestions | Review "where did this run drift" |
| **Outline suggestions** | Node comparison table / new subplots / foreshadowing updates / next steps | Feed back into your own outline |
| **Full settings bundle** | Packaged world + characters + progress + style card | Move to another tool or machine, or archive as a settings snapshot |
| **Key event list** | Time, type and characters of each event | Quickly locate "what happened on which day" |
| **Snapshots** | Complete world state at any moment | Return to a node and play a different path |

> The most practical habit for a writer: **run the same settings two or three times and compare the versions as alternative drafts.** Side by side, you often spot a path your own manuscript never considered.

---

## Typical Writing Scenarios

These are all moments of "I don't know how to go on" — which is exactly when this tool is for:

**1. Stuck in the middle**
Drop in your existing chapters and settings; let it continue from the latest point. It may not give you *the* path — but it usually gives you three you hadn't considered.

**2. Characters "don't sound right"**
In a run, each character has their own memory, speech habits, plans and secrets. Watch how they speak in different scenes, then recalibrate your character cards.

**3. Validate plot logic**
"If the protagonist reveals everything right here, can the story hold up?" Let it play three days forward from that node and see whether it collapses.

**4. Fill in detail and scenes**
Only have an outline? Let it turn outline nodes into passages with dialogue, action and interiority.

**5. Try different tones**
Use the style controls (angst / humour / payoff density / suspense / pacing) and run the same settings with different values, then compare which register fits better.

---

## Feature List

- **Intake**: Reads .md / .txt / .docx / .html; extracts settings, determines genre, extracts style, aligns with existing text
- **Complete**: Default `story` mode with a progress table and endpoint, auto-wraps with a summary
- **Continue**: Existing text → continue from latest progress; outline only → start at any node
- **Faithful**: Director engine loads a narrative craft library (Western screenwriting canon / Chinese classical methods / web-novel methodology)
- **Controllable**: Live style panel — angst, humour, payoff density, romance, suspense, character IQ, pacing
- **Legible**: Narrative renders **screenplay-style** — scenes and beats (time / place / entrances & exits / narration / dialogue / action / inner voice). **Different people doing different things at the same moment become a 「meanwhile」 parallel track**, and simultaneous events elsewhere use 「cut to」. Each scene names the story node and foreshadowing it advances — readable and auditable
- **Recorded**: Daily narrative on disk; story document, outline suggestions and run summary on demand
- **Reversible**: Snapshot rewind — return to any node and take a different path
- **Affordable**: Token hard budget + degradation ladder + daily bill
- **Compliant**: Independent compliance checking (local policy library + LLM review + optional external services)
- **Researched**: Knowledge gaps (institutions, law, timekeeping, travel time) go through the research channel — built-in skills (8 offline knowledge packs) and MCP servers (3 local read-only query servers) come first, web/LLM only as fallback. **Earlier layers are cheaper and more reliable**

---

## External Creation Services (optional enhancements)

You can attach three **separate creation services** next to the app (all under `novelservices/`, all
**optional**: the simulation runs fine without them):

| Service | What it does | Who uses it | Where its port lives |
|---------|--------------|-------------|----------------------|
| **MuMuAINovel** | Writes novel prose (sample chapters / export rewrite) | Novelist | its own `backend/.env` (default 8001) |
| **PlotPilot (Mòshū)** | Narrative engine: what should happen in this chapter | Screenwriter | **app root** `.env` (default 8005) |
| **PenShot** | Director / storyboard engine: how this scene is shot | Director | **app root** `.env` (default 8000) |

- **Configure / start / stop**: Start screen → "Settings" → "External Creative Services". Each section has a
  master switch, "who uses it", **start automatically at program start**, **stop when the program closes**,
  plus Start/Stop buttons and live status.
- **Ports are handled by setup**: at install time it checks local ports (Docker running on the machine is
  fine); if one is taken by another program it scans upward for a usable port and writes it into the `.env`
  that service reads. If the occupant is the service itself (health check passes), it is left alone.
  To see the current ports: `start --selftest report.json` (`port` / `port_busy` per service).
- **Graceful fallback**: if a service is down / times out / returns empty, the corresponding post falls back to
  the app's own logic and records the reason on the output.
- Release bundles **exclude** `novelservices/` (large, separately licensed) — all three being absent on a
  user machine is a **supported normal state**.

---

## Input Folder Standards

| Tier | What to Include | Result |
|------|-----------------|--------|
| **Runnable** | Any .md: an idea / an outline / ≥1 chapter | Runs. Characters flat, generic path |
| **Recommended** | ①Outline + ②Character info + ③World/background | Behaviour matches settings; director has a full roadmap |
| **Optimal** | Recommended + ④Character cards (secrets/catchphrases) + ⑤Foreshadowing list + ⑥Chapters | Style card active; prior context aligned; foreshadowing precisely activated |

File and folder names containing these keywords are classified automatically: `设定`/`world`/`background`, `人物`/`character`, `大纲`/`outline`, `正文`/`chapter`, `伏笔`/`foreshadow`.

**Where does a setting collection come from?** See
**[`Settings_Authoring_Guide.md`](Settings_Authoring_Guide.md)** (中文:
[`设定集提供指南.md`](设定集提供指南.md)) — copy-pasteable prompts for having another AI tool
write the worldview / characters / places / outline / sample chapters, plus a field-limit table
for writing it by hand. Its **length plan** (chapters per place, words for the whole book, plot
beats per station) is new as of 2026-10-27: `Chapters` is a hard gate (a station may not advance
before it has produced that many), `Total words` is a soft target.

---

## Start Screen (eight entries)

Launching shows an **ink-wash title screen**, not the editor:

```
                    [ Logo ]
            Novel World AI Simulator
              ── live a story once ──
              Current project 【title】

                 New        import a novel folder
                 Recent     open a previous story
                 Start      run one round of inference
                 Deconstruct  learn technique from a good book
                 Settings   program settings: models, budget
                 Project    this book's settings: genre, style
                 Resume     back to the running interface
                 Exit       quit

              v0.3.3 · local · Python + Flet
```

| Entry | Caption | What it does | Without a project |
|---|---|---|---|
| **New** | import a novel folder | Four-step import wizard to bring in a new novel | enabled |
| **Recent** | open a previous story | Pick a project and continue | greyed out |
| **Start** | run one round of inference | Set this round's parameters and go | greyed out |
| **Deconstruct** | learn technique from a good book | Break a good book down into the skill library | enabled |
| **Settings** | program settings: models, budget | **Global** settings — apply to every project | enabled |
| **Project** | this book's settings: genre, style | **Only the current project** | greyed out |
| **Resume** | back to the running interface | Jump back to the running UI | greyed out |
| **Exit** | quit | Close the program | enabled |

> **The order is "find the book first, then write"**: New (new book) -> Recent (old book) -> Start (run).
> **Settings vs Project** is the pair people confuse: one is program-wide, one is per-book.

**Keyboard**: `Up` / `Down` to move, `Enter` to confirm, `Esc` back to the running story.

**The message box on startup** reports the capability check (it says "corrected", "restart needed",
or "demo mode"). **That is an explanation, not an error** — if it says "restart needed", restart once.

---

## Quick Start

### 1. Install & launch (one step)

**No Python knowledge needed — just double-click.**

| OS | What to do |
|----|------------|
| **Windows** | Double-click **`start.exe`** in the project root |
| **macOS** | Double-click **`start`** in Finder (or run `./start`) |
| **Linux** | Run `./start` in a terminal |

The launcher handles everything: find Python → create an isolated environment (`.venv`) → install dependencies → start the app.

> A **"book cover" splash** appears first (no console, but the whole startup is visible): logo / name /
> "把故事，活一遍", a **scrolling startup message** below, and a **`›` chevron** at the right of that
> strip that expands into the **command-line output** (the command being run, raw errors, and the
> failing step in red -- where the launcher then stops); click it again and the chevron **turns to
> `⌄`** to collapse. The footer reads `v0.3.3 · local · Python + Flet`, **✕** at the top right
> closes it, and it vanishes by itself once the app window is up.
>
>
> Expanded, the log area is **14 lines / 218px** (since 2026-10-27; it used to be 7 lines) and holds
> **each service's full bring-up** (environment, dependencies, port, health check). All three share
> one stream, every line starting with **`[time][service]`** so you can tell at a glance who said
> it; lines without that prefix come from the launcher itself (version, platform, preparing the
> runtime). The program's own WARNING/ERROR during startup lands there too (`[time][app]`), so
> "which step hung" needs no file digging.
> ⚠ **The strip shows progress only** (the lines marked `→`) — an ordinary line of service output
> never pushes it away; otherwise a single `ERROR` in a uvicorn log would make "starting up" read as
> "startup failed".
>
> **On failure the reason appears once**: the strip switches to a neutral "启动没成功"
> ("startup did not complete") and the reason goes on the **centred red line below it** (full width,
> wrapping to two lines when long, so the "press ✕ to enter anyway" half is never cut off). The same
> sentence used to be painted on both, 42px apart when collapsed — which read as "two error lines".
>
> Collapsed it is only **860×350** (860×602 expanded) -- a small block in the middle of the screen.

> ⚠ **The three launchers are compiled per platform** (Go, cross-compiled), and the set in the root
> is for **this machine's platform only**.
> **One release package carries all four platforms**: the root holds this machine's set, the other
> three live in `启动器/其他平台/<platform>/` (copy that folder's three files into the package root
> when moving to another OS). The in-package `平台说明.md` states where each set is.

<details>
<summary>How to build a release (one folder per version, all four platforms)</summary>

```bash
python tools/make_release.py                            # -> 发布版本/0.3.3/
python tools/make_release.py --dry-run                  # print the plan, copy nothing
python tools/make_release.py --force                    # overwrite that version (only if it has our manifest)
```

Eight steps: create the version folder -> copy the whole tree (exclusions apply before copying) ->
put the four launcher sets in place -> regenerate `.env` / `.env.example` -> sync keys present in the
local `.env` but unregistered -> blank secrets and LLM config in the example -> sweep logs / caches /
ledgers / dev dirs / old backups -> self-check (full-text search for the **real key**, `sk-...`
literals, local paths, leftover logs and databases, required files, magic of all four launcher sets).
The version has exactly one source: `config.VERSION`.

All four sets live in the source tree under `launchers/dist/` (cross-compiled artifacts); if one is
missing, run `python launchers/build.py` (needs a Go toolchain). Packaging and the self-check both
**read the launchers' magic** to verify the platform (Windows is `MZ`, Linux is `ELF`, macOS is Mach-O
with the cputype distinguishing arm64 from x86_64) -- the filename can't tell you (Linux and macOS are
both `setup`); only the magic can.

</details>
</details>

> **Requirement**: **Python 3.10+** installed ([download](https://www.python.org/downloads/) — on Windows tick **Add Python to PATH**). The first run needs internet to install dependencies (1–3 min); later launches take a few seconds.

**Useful flags**:

```bash
start.exe --mock          # demo mode (zero cost, no API key needed)
start.exe --reinstall     # force reinstall dependencies
```

<details>
<summary>Prefer doing it manually (developers)</summary>

```bash
cd NovelWorldSimulator
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python main_gui.py
```
</details>

> On first launch the UI runtime is checked and installed automatically. For offline use, place the runtime package in `packages/`.

### 1.1 Put it on the Desktop and in the Start Menu (optional)

If you'd rather not dig through folders for the launcher, install the shortcuts once:

| System | Install | Uninstall |
|--------|---------|-----------|
| **Windows** | double-click **`setup.exe`** | double-click **`uninstall.exe`** |
| **macOS** | double-click **`setup`** in Finder | double-click **`uninstall`** in Finder |
| **Linux** | `./setup` | `./uninstall` |

- **Windows**: a Desktop shortcut plus a Start Menu folder with **Launch / Open project folder / User manual / Uninstall**
- **macOS**: `~/Applications/小说世界AI模拟.app` (in Launchpad and Spotlight) plus a Desktop alias
- **Linux**: an application-menu entry plus a Desktop icon

The icons point at this platform's start script, so no reinstall is needed after code
updates. No administrator rights required, and uninstalling removes **only the
shortcuts** — your novel project data is never deleted. Preview first with
`setup.exe --dry-run`.

### 2. Configure

```bash
cp .env.example .env
# Edit .env and fill in your LLM API key
# Or set MOCK_LLM=true to try it in demo mode (zero cost)
```

Scenario-based configuration: [Configuration Guide](Configuration_Guide.md). Where each setting lives: [Configuration Classification](Configuration_Classification.md).

### 3. Use it

Launching opens the **start screen** (ink-wash title screen + eight vertical entries):
New / Recent / Start / Deconstruct / Global Settings / Project Settings / Resume / Exit.
See [Start screen](#start-screen-eight-entries).

**New Story** walks you through the import wizard:

1. Choose the novel folder
2. Ingest and extract settings (AI optimisation options are chosen here)
3. Review the completeness grade (Runnable / Recommended / Optimal)
4. Confirm genre, style, starting point
5. Create the project and start

> The interface supports **Chinese / English** — switch it in Settings · Global → Interface language.

Full tutorial: [User Manual](User_Manual.md).

---

## Common Operations

Eight entries on the start screen (in top-to-bottom order):

| Entry | Purpose | Without a project |
|-------|---------|-------------------|
| **New** | Import a novel folder and create a project | enabled |
| **Recent** | Open an existing project and resume from a snapshot | greyed out |
| **Start** | Run one round of inference (sets round parameters) | greyed out |
| **Deconstruct** | Break a good book down into writing technique in the skill library | enabled |
| **Global Settings** | API, models, budget, compliance, logging | enabled |
| **Project Settings** | Genre, style, run mode, style controls | greyed out |
| **Resume** | Back to the running interface | greyed out |
| **Exit** | Quit | enabled |

> **Greyed out is not broken**: the one-line caption under an entry says why it is unavailable
> (e.g. "import a novel first").

Common commands (typed in the command box):

| Command | Purpose |
|---------|---------|
| `progress` / `pg` | View the story progress table |
| `storyline` / `sl` | Generate the story document |
| `outline` / `ol` | Generate outline suggestions |
| `summary` | Generate the run summary |
| `snapshot` / `snap` | Take a snapshot (with note) |
| `rewind` / `rw` | List snapshots / rewind |
| `pause` / `resume` | Pause / resume |
| `help` / `?` | Help panel |

---

## Driving It From Scripts (Python SDK / CLI)

Everything the interface can do, a script can do too — **same implementation**,
just a different shell. Useful for batch runs, scheduled jobs, and unattended
servers. The SDK **does not depend on the GUI** (the whole `nws` package never
imports flet), so it runs headlessly.

### Python SDK

```python
import sys
sys.path.insert(0, r"<project>\developers\sdk")     # this one line is all you need
import nws

nws.config.set(MOCK_LLM=True)                      # demo mode: zero cost, offline
book = nws.project.create("Demo", source=r"C:\src\demo")   # create a book
nws.ingest.run(book)                               # ingest source -> settings
r = nws.run.start(book, days=1, max_ticks=6)       # pen to paper: run it
r.wait()
nws.export.run(book, r.run, kinds=["novel", "report"])
print(r.snapshot(), nws.usage.summary(book.name))
```

Nine modules covering the whole pipeline:

| Module | What it drives |
|--------|----------------|
| `nws.config` | **Global settings** (29 SPEC groups; read/write `.env`; `temporary()` restores) |
| `nws.project` | **Projects**: create / find / open / list / delete (moved to trash, recoverable) / **per-project settings** |
| `nws.ingest` | **Ingest**: `plan()` shows what would be sent, `run()` does it, `gate=` is the consent door |
| `nws.run` | **Run**: start / pause / resume / stop / snapshot / branch / resume-from-last |
| `nws.archive` | **Archives**: a copy of one round (snapshot semantics) |
| `nws.export` | **Export**: five kinds (two call the model), versions never overwritten |
| `nws.usage` | **Usage**: calls / tokens / cost, split by model · date · module · run task |
| `nws.mumu` | The optional **MuMuAINovel** writing service (status / start / stop / write / polish) |
| `nws.aio` | Async facade (for Jupyter / FastAPI / Flet) |

- **Full API reference** → `developers/sdk/API.md`（源码树里，不随发布包提供）
- **Eight runnable samples** → `developers/sdk/samples/`（源码树里，不随发布包提供）

### Command line

```bash
python -m nws list                     # which books exist
python -m nws info <book>              # state of one book
python -m nws ingest <book> --plan      # only show what would be sent (no cost)
python -m nws run <book> --days 1 --ticks 6 --follow
python -m nws export <book> --kinds novel,report
python -m nws usage --scope <book> --by 模型
python -m nws mumu status
```

⚠ **Costly or destructive actions require `--yes`** (delete a book, ingest);
without it they only describe what they *would* do.

**Two disciplines**: the SDK never writes your `.env` (call `save()` explicitly)
and never touches your source folder; "delete" always **moves** things into a
recoverable `已删除备份` folder. Two of the 70 checks in `tools/verify_sdk.py`
prove this by comparing the `.env` sha1 and the real `Projects/` entry count.

### Run any source folder with one command (unattended)

`novel_bench` only scores the cases pinned in its dataset. To measure "**is the
output actually better when this change lands on `samples/` or on my own
project**", use this (source tree only: `developers/run_input_folder.py`, **not
shipped in the release package**; the equivalent inside a release build is the
Import → Start flow in the UI):

```bash
./.venv/Scripts/python.exe developers/run_input_folder.py \
    --src "samples/en/06_scifi_echo_station" --name "Echo Station" --ticks 6 --run-id test-echo
```

It takes **the same path and the same functions** as the UI (import → create
project → assemble → run N beats). Outputs: `novel.md` (the day's story),
`transcript.md` (line-by-line record), `summary.md` (run digest, including how
many entries the script doctor rewrote and why), and `project/` (a real project
folder you can reopen in the UI).

Useful flags: `--ticks N`, `--cast a,b` to limit the cast, `--scene` to pin a
scene, `--clock HH:MM` for the start time, `--no-ingest` to treat `--src` as an
already-distilled settings folder, and `--resummarize <dir>` to **rewrite only
the digest** (no re-run, no cost).

To merge several runs into one report, pass the output folders to
`developers/make_test_report.py <dir…>`; it prints a summary table (word count,
rewrites, simulation score, reference score, blind verdict) plus each case's
digest and prose. Details and timings: section **5.8.4** of `User_Manual.md`.

---

## Tech Stack

- **Language**: Python 3.10+
- **UI**: Flet 1.0 (desktop GUI, Chinese ink-wash visual style)
- **LLM**: OpenAI-compatible protocol (DeepSeek by default; Hunyuan Hy3 / OpenAI / Claude /
  Qwen / Zhipu GLM / Kimi / MiniMax / local Ollama also supported)
- **Several models at once** (since 2026-10-12): **one program can use several providers**,
  each entry carrying its own endpoint and key. The "Models & LLM" page manages *which*
  models exist; each Agent picks its own under "Crew Agents" — one provider for prose,
  another for judgments. The page also carries a **recommendation table**
- **Costs you can see, and cut** (since 2026-10-12): the Usage Report lists cost and tokens
  **per model**, with each model's **cache hit ratio** and **money saved by caching**; every
  model can carry unit prices from your own bill. The four levers (model tiering / prefix
  caching / same-question reuse / the cheap window) are in **`Cost_Saving_Guide.md`**
- **Storage**: SQLite + files (Markdown / YAML / JSON)
- **Dependencies**: flet, Pillow, pyyaml, python-docx, chardet, httpx

## References

- **Generative Agents** (Stanford, UIST'23): memory stream, tri-weight retrieval, reflection, hierarchical planning
- **Concordia** (DeepMind) / AI Town / Project Sid: director framework, foreground/background scheduling
- **Screenwriting canon**: McKee, Field, Snyder, Truby, Egri, Bell, Aristotle, Propp, Vogler
- **Chinese classical methods**: Jin Shengtan, Li Yu
- **Web-novel methodology**: Qidian / Jinjiang top works

## Copyright & Disclaimer

- **Case library**: methodology breakdowns only — no source text, no substantial plot excerpts (copyright red line).
- **User project data**: stays local; the program never writes back into your project folder.
- **Compliance layer**: assists with filtering and warnings, **not legal advice**; responsibility for published content rests with the author.
- **Reference material**: read locally as context only; exports never copy passages wholesale.

## License

[To be determined]

---

**Related documents**:
- [Configuration Guide](Configuration_Guide.md) — 12 typical scenarios
- [Configuration Classification](Configuration_Classification.md) — where each setting lives
- [User Manual](User_Manual.md) — full tutorial and command reference
- [Complete Use Guide](Complete_Use_Guide.md) — from zero to export (with "how many models" example setups)
- [Settings Writing Guide](Settings_Writing_Guide.md) — how to write settings so the program can use them
- [Script Output Format](Script_Output_Format.md) — narrative output format spec (incl. "simultaneous" and "cut to")
- [Cost Saving Guide](Cost_Saving_Guide.md) — four ways to save: tier routing, prefix cache, reuse, off-peak
- [mcp/README.md](mcp/README.md) — MCP servers: 3 built-in + how to write your own
- [skills/README.md](skills/README.md) — skills: 8 built-in + how to write your own

**Chinese documents**:
- [配置指南](配置指南.md) — 12 个典型场景的配置说明
- [配置分类](配置分类.md) — 配置项存在哪、作用范围
- [使用说明](使用说明.md) — 完整教程与命令手册
- [完整使用流程指南](完整使用流程指南.md) — 从零到导出（含「需要几个模型」实例搭配）
- [设定写作指导](设定写作指导.md) — 设定该怎么写程序才用得上
- [剧本输出格式](剧本输出格式.md) — 叙事输出的格式规范（含「同时」「切至」怎么读）
- [省钱指南](省钱指南.md) — 省钱四招
