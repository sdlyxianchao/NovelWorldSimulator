# Novel World AI Simulator · Configuration Guide

> This document explains how to configure the `.env` file for different scenarios.
> Each configuration item includes detailed explanations of its function and why it's configured this way in each scenario.
> For complete parameter documentation, see `.env.example`.
>
> **Configuration Layers**: Settings are organized into software settings (.env), project settings (.nwsproj), and save settings.
> See [Configuration Classification](Configuration_Classification.md) for details.

[中文](配置指南.md) | [README](README_EN.md) | [User Manual](User_Manual.md) | [Configuration Classification](Configuration_Classification.md)

---

## Table of Contents

1. [Quick Start Configuration](#1-quick-start-configuration)
2. [Demo Mode (Zero Cost)](#2-demo-mode-zero-cost)
3. [First Use Configuration](#3-first-use-configuration)
4. [Budget Configuration](#4-budget-configuration)
5. [High Quality Configuration](#5-high-quality-configuration)
6. [Long Serial Configuration](#6-long-serial-configuration)
7. [Mystery/Suspense Configuration](#7-mysterysuspense-configuration)
8. [Fantasy/Cultivation Configuration](#8-fantasycultivation-configuration)
9. [Local Model Configuration (Ollama, optional)](#9-local-model-configuration-ollama-optional)
10. [Debug Configuration](#10-debug-configuration)
11. [Compliance Configuration](#11-compliance-configuration)
12. [FAQ](#12-faq)

---

## 1. Quick Start Configuration

**Scenario**: First time using, want to try quickly.

```ini
# Required: LLM API Key
LLM_API_KEY=sk-your-key

# Keep other defaults
```

**Configuration Details**:

| Setting | Value | Description |
|---------|-------|-------------|
| `LLM_API_KEY` | `sk-your-key` | **Required**. Your LLM service API Key, obtained from DeepSeek/OpenAI platforms. Without this, the program cannot call LLM. |

**Steps**:
1. Copy `.env.example` to `.env`
2. Fill in `LLM_API_KEY`
3. Run `python main.py`
4. Follow the wizard

---

## 2. Demo Mode (Zero Cost)

**Scenario**: Don't want to spend money, just want to experience the interface and flow.

```ini
# Enable demo mode
MOCK_LLM=true

# Optional: Debug mode (view detailed logs)
DEBUG_MODE=true

# Optional: Disable compliance (faster speed)
COMPLIANCE_ENABLED=false
```

**Configuration Details**:

| Setting | Value | Description |
|---------|-------|-------------|
| `MOCK_LLM` | `true` | **Core setting**. Enable demo mode, no real API requests, uses built-in corpus for full flow. Good for experiencing interface, teaching, screenshots. |
| `DEBUG_MODE` | `true` | Enable debug mode, logs full LLM request/response, Agent decision details, director judgment logic. Helps understand program internals. |
| `COMPLIANCE_ENABLED` | `false` | Disable compliance detection. Compliance needs LLM calls, disabling speeds up demo. |

**Effect**:
- No real API requests
- Uses built-in corpus for full flow
- Good for experiencing interface, teaching, screenshots

---

## 3. First Use Configuration

**Scenario**: First time using officially, have API Key.

> **⚠️ Price Notice**: LLM service prices are subject to market adjustments. Prices in this document are estimates only. Please refer to the latest official prices from LLM service providers (e.g., DeepSeek, OpenAI) for actual costs.

```ini
# LLM Configuration
LLM_API_KEY=sk-your-key
LLM_BASE_URL=https://api.deepseek.com/v1

# Budget control (small budget for first run)
TOKEN_BUDGET_PER_DAY=100000
AUTO_RUN_DAYS=1

# Run mode
RUN_MODE=story

# Keep other defaults
```

**Configuration Details**:

| Setting | Value | Description |
|---------|-------|-------------|
| `LLM_API_KEY` | `sk-your-key` | **Required**. Your LLM service API Key. |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | LLM service address. Default DeepSeek, can change to OpenAI, etc. |
| `TOKEN_BUDGET_PER_DAY` | `100000` | **Budget control**. Max 100k tokens/day (≈$10, estimate only). Small budget for first run to test. |
| `AUTO_RUN_DAYS` | `1` | **Run day limit**. Set to 1 for first run, only run 1 day then pause to observe. |
| `RUN_MODE` | `story` | **Run mode**. `story` follows progress table to endpoint with summary. Default mode. |

**Tips**:
- First run: set `AUTO_RUN_DAYS=1` to test overnight
- Observe token consumption before adjusting budget
- Use `MOCK_LLM=true` to familiarize with interface first

---

## 4. Budget Configuration

**Scenario**: Limited budget, want to save money.

> **⚠️ Price Notice**: LLM service prices are subject to market adjustments. Prices in this document are estimates only. Please refer to the latest official prices from LLM service providers (e.g., DeepSeek, OpenAI) for actual costs.

```ini
# Use cheaper models (premium for key scenarios, Flash for daily/summary)
MODEL_FRONT=deepseek-chat
MODEL_DAILY=deepseek-flash
MODEL_CHEAP=deepseek-flash

# Lower budget
TOKEN_BUDGET_PER_DAY=50000

# Disable non-essential features
REVIEW_PASS=false
FEWSHOT_FROM_NOVEL=false
CRAFT_CASES_ENABLED=false
RESEARCH_AUTO=false
BACKGROUND_MODE=off

# Use budget tier for documents (the daily-life log tier is fixed and no longer configurable)
STORY_DOC_MODEL=MODEL_DAILY
SUMMARY_MODEL=MODEL_DAILY

# Export: keep only the two free ones (day-by-day binding, no LLM calls);
# report and guide cost tokens, so export them manually when needed
EXPORT_ON_END_REFERENCE=true
EXPORT_ON_END_NOVEL=true
EXPORT_ON_END_GUIDE=false
AUTO_SUMMARY_ON_END=false
EXPORT_NOVEL_POLISH=false

# Disable compliance LLM review
COMPLIANCE_LLM_REVIEW=never
```

**Configuration Details**:

| Setting | Value | Description |
|---------|-------|-------------|
| `MODEL_FRONT` | `deepseek-chat` | **Premium tier model**. For key events, important dialogue, reflection, story docs, summaries. ~15% calls. Use good model for quality. |
| `MODEL_DAILY` | `deepseek-flash` | **Daily tier model**. For routine loops, log整理. ~55% calls. Flash is 50%+ cheaper. |
| `MODEL_CHEAP` | `deepseek-flash` | **Budget tier model**. For compression, scoring, background, progress eval. ~30% calls. Flash is 50%+ cheaper. |
| `TOKEN_BUDGET_PER_DAY` | `50000` | **Budget control**. Max 50k tokens/day (≈$5, estimate only). Lower budget controls cost. |
| `REVIEW_PASS` | `false` | **Review pass**. Disable review. Review needs extra LLM calls, disabling saves tokens. |
| `FEWSHOT_FROM_NOVEL` | `false` | **Few-shot from text**. Disable few-shot. Few-shot needs extra LLM calls, disabling saves tokens. |
| `CRAFT_CASES_ENABLED` | `false` | **Case library**. Disable case library. Case library injects into LLM prompts, disabling reduces tokens. |
| `RESEARCH_AUTO` | `false` | **Auto research**. Disable auto research. Research needs extra LLM calls, disabling saves tokens. |
| `BACKGROUND_MODE` | `off` | **Background mode**. Disable background. Background agents consume tokens, disabling saves tokens. |
| `STORY_DOC_MODEL` | `MODEL_DAILY` | **Story doc tier**. Use daily tier for story docs, cheaper. |
| `SUMMARY_MODEL` | `MODEL_DAILY` | **Run report tier**. Use daily tier for run reports, cheaper. |
| `AUTO_SUMMARY_ON_END` | `false` | **Auto-export run report on end**. Off means export it by hand — the report carries billing and OOC analysis, best read after the run. **Turning it off does not remove the feature**: manual export is always available. |
| `EXPORT_ON_END_GUIDE` | `false` | **Auto-export writing guide**. The guide needs LLM calls; export it manually when needed to save tokens. |
| `EXPORT_NOVEL_POLISH` | `false` | **Polished novel draft**. Polishing rewrites the text via LLM — costs tokens and changes wording; skip it to save. |
| `COMPLIANCE_LLM_REVIEW` | `never` | **Compliance LLM review**. Disable LLM review, only use rule layer. Rule layer is zero cost. |

**Budget Tips**:
- Premium tier: good model (deepseek-chat), daily/summary: Flash (50%+ cheaper)
- Disable review, few-shot, case library
- Background mode off
- Use budget tier for documents

**Cheap Model Recommendations**:
- `deepseek-flash`: DeepSeek Flash (recommended, cheap and fast)
- `gpt-4o-mini`: OpenAI cheap model
- `qwen-turbo`: Qwen cheap model
- `glm-4-flash`: Zhipu cheap model (free)

---

## 5. High Quality Configuration

**Scenario**: Pursuing quality, sufficient budget.

> **⚠️ Price Notice**: LLM service prices are subject to market adjustments. Prices in this document are estimates only. Please refer to the latest official prices from LLM service providers (e.g., DeepSeek, OpenAI) for actual costs.

```ini
# Use good models
MODEL_FRONT=deepseek-reasoner
MODEL_DAILY=deepseek-chat
MODEL_CHEAP=deepseek-chat

# Higher budget
TOKEN_BUDGET_PER_DAY=500000

# Enable all quality features
REVIEW_PASS=true
REVIEW_THRESHOLD=0.8
FEWSHOT_FROM_NOVEL=true
CRAFT_CASES_ENABLED=true
RESEARCH_AUTO=true

# Vector retrieval: leave it at the default none (the UI no longer offers this switch;
# to change it, edit this line directly)
# EMBEDDING_PROVIDER=none

# Use premium tier for documents
STORY_DOC_MODEL=MODEL_FRONT
SUMMARY_MODEL=MODEL_FRONT

# Export: all four on; also let the LLM turn the novel version into a
# coherent manuscript (saved separately, never overwriting the bound draft)
EXPORT_ON_END_REFERENCE=true
EXPORT_ON_END_NOVEL=true
EXPORT_ON_END_GUIDE=true
AUTO_SUMMARY_ON_END=true
EXPORT_NOVEL_POLISH=true
```

**Configuration Details**:

| Setting | Value | Description |
|---------|-------|-------------|
| `MODEL_FRONT` | `deepseek-reasoner` | **Premium tier model**. DeepSeek Reasoner (reasoning model), highest quality. For key scenarios. |
| `MODEL_DAILY` | `deepseek-chat` | **Daily tier model**. DeepSeek Chat, good quality. For routine scenarios. |
| `MODEL_CHEAP` | `deepseek-chat` | **Budget tier model**. DeepSeek Chat, good quality. For summary scenarios. |
| `TOKEN_BUDGET_PER_DAY` | `500000` | **Budget control**. Max 500k tokens/day (≈$50, estimate only). High quality needs more tokens. |
| `REVIEW_PASS` | `true` | **Review pass**. Enable review. Review checks quality, rewrites if below threshold. |
| `REVIEW_THRESHOLD` | `0.8` | **Review threshold**. 0.8 means 80+ score to pass. Higher = stricter quality. |
| `FEWSHOT_FROM_NOVEL` | `true` | **Few-shot from text**. Enable few-shot. Extracts good paragraphs as examples, improving quality. |
| `CRAFT_CASES_ENABLED` | `true` | **Case library**. Enable case library. Injects reference cases into prompts. |
| `RESEARCH_AUTO` | `true` | **Auto research**. Enable auto research. Auto-queries reference library, skills, MCP for knowledge gaps. |
| `EMBEDDING_PROVIDER` | `none` | **Vector retrieval**. Off by default (keyword matching instead). ⚠ The Tianji page **no longer shows** this switch; edit `.env` directly to change it. `llm/embedding.py` is not yet wired into memory retrieval, so changing it has no effect on the simulation today — see the note above chapter 9. |
| `STORY_DOC_MODEL` | `MODEL_FRONT` | **Story doc tier**. Use premium for story docs, highest quality. |
| `SUMMARY_MODEL` | `MODEL_FRONT` | **Run report tier**. Use premium for run reports, highest quality. |
| `EXPORT_ON_END_GUIDE` | `true` | **Auto-export writing guide**. Produces a synopsis-ready outline at the end of each run. |
| `EXPORT_NOVEL_POLISH` | `true` | **Polished novel draft**. Sends the bound draft through the LLM for a coherent read; **saved separately, never overwrites the bound draft**. |

**Quality Tips**:
- Premium tier: good model (deepseek-reasoner)
- Enable review pass for quality assurance
- Use case library for reference

---

## 6. Long Serial Configuration

**Scenario**: Running stories for 10+ days.

> **⚠️ Price Notice**: LLM service prices are subject to market adjustments. Prices in this document are estimates only. Please refer to the latest official prices from LLM service providers (e.g., DeepSeek, OpenAI) for actual costs.

### Option A: story_day Mode (Recommended)

```ini
# Run mode: follow progress table but pause every N days
RUN_MODE=story_day
STORY_DAY_EVERY_DAYS=3  # Pause every 3 days

# Time system
TIME_RATIO=3600  # fast lane (default 1 = real time; 3600 ≈ 24 s per story day)
PAUSE_AT_NIGHT=true  # Night pause saves tokens

# Budget
TOKEN_BUDGET_PER_DAY=300000

# Snapshot retention
SNAPSHOT_KEEP=50
LOG_ROTATE_DAYS=30

# Stall detection
STALL_WINDOW_MINUTES=240  # 4 hours no events = stall

# Director engine
DRAMA_LEVEL=0.7  # Moderate drama
CLIMAX_EVERY_DAYS=3  # Small climax every 3 days
```

**Configuration Details**:

| Setting | Value | Description |
|---------|-------|-------------|
| `RUN_MODE` | `story_day` | **Run mode**. `story_day` follows progress table but pauses every N days. Good for long serials. |
| `STORY_DAY_EVERY_DAYS` | `3` | **Pause interval**. Auto-pause every 3 virtual days. Can check progress, generate docs, adjust settings. |
| `TIME_RATIO` | `3600` | **Time ratio**. N story seconds per real second.
  **Default is 1 (real time — a story day takes about 24 hours)**; the 3600 in the example means a story day takes about 24 seconds, useful for quickly seeing a whole arc; `60` means about 24 minutes per story day, a common setting for long runs. |
| `PAUSE_AT_NIGHT` | `true` | **Night pause**. Auto-pause when all sleep, saves tokens. Multi-day runs benefit from night pauses. |
| `TOKEN_BUDGET_PER_DAY` | `300000` | **Budget control**. Max 300k tokens/day (≈$30, estimate only). Long stories need more tokens. |
| `SNAPSHOT_KEEP` | `50` | **Snapshot retention**. Keep 50 snapshots. Multi-day runs benefit from more snapshots. |
| `LOG_ROTATE_DAYS` | `30` | **Extra log cleanup** (only `nws*.log`). ⚠ Whatever you put here, startup **still deletes anything older than 30 days** under `nws*.log` (main *and* dialogue logs — **copy anything you want to keep**); this setting cleans again on top of that. `llm_calls.jsonl` is **outside every cleanup rule** and keeps growing. |
| `STALL_WINDOW_MINUTES` | `240` | **Stall detection window**. 4 hours no events = stall. Long stories may have quiet periods. |
| `DRAMA_LEVEL` | `0.7` | **Drama level**. 0.7 = moderate drama. Long stories need sustained tension. |
| `CLIMAX_EVERY_DAYS` | `3` | **Climax interval**. At least one small climax every 3 days. Keeps reader interest. |

**story_day Mode Features**:
- Follows story progress table (not infinite sandbox)
- Auto-pauses every N virtual days
- Can check progress, generate docs, adjust settings during pause
- Continues after confirmation
- Good for long serials, avoids running through at once

### Option B: story Mode (Uninterrupted)

```ini
RUN_MODE=story
AUTO_RUN_DAYS=0  # Unlimited days
```

### Option C: open Mode (Infinite Simulation)

```ini
RUN_MODE=open
OPEN_CHECKPOINT_EVERY_DAYS=3  # Pause every 3 days
```

**Long Story Tips**:
- Use `story_day` mode for periodic pauses
- Set `PAUSE_AT_NIGHT=true` for night pauses
- Increase snapshot retention
- Increase drama level for sustained tension
- Use `storyline` command periodically to generate story documents

---

## 7. Mystery/Suspense Configuration

**Scenario**: Mystery, suspense, supernatural stories.

```ini
# Genre
STORY_GENRE=悬疑+灵异|单元剧|男频

# Director engine (mystery needs high tension)
DRAMA_LEVEL=0.8
CONFLICT_FREQUENCY=0.5
REVEAL_PACING=0.3  # Slow reveal
COINCIDENCE_RATE=0.1  # Few coincidences

# Tension curve
TENSION_CURVE=medium

# Craft library
CRAFT_LIBRARY=builtin
CRAFT_CASES_ENABLED=true
```

**Configuration Details**:

| Setting | Value | Description |
|---------|-------|-------------|
| `STORY_GENRE` | `悬疑+灵异\|单元剧\|男频` | **Story genre**. Manually specify genre, skip LLM detection. Format: "main+sub\|structure\|channel". |
| `DRAMA_LEVEL` | `0.8` | **Drama level**. 0.8 = high drama. Mystery needs high tension. |
| `CONFLICT_FREQUENCY` | `0.5` | **Conflict frequency**. 0.5 = moderate. Mystery needs frequent conflicts. |
| `REVEAL_PACING` | `0.3` | **Reveal pacing**. 0.3 = slow reveal. Mystery needs gradual truth revelation. |
| `COINCIDENCE_RATE` | `0.1` | **Coincidence rate**. 0.1 = few coincidences. Mystery needs logical consistency. |
| `TENSION_CURVE` | `medium` | **Tension curve**. `medium` = moderate fluctuation. Mystery needs stable tension. |
| `CRAFT_LIBRARY` | `builtin` | **Craft library**. Use built-in library. Contains mystery methodology and cases. |
| `CRAFT_CASES_ENABLED` | `true` | **Case library**. Enable case library. Contains classic mystery references. |

**Mystery Tips**:
- Lower reveal pacing (`REVEAL_PACING=0.3`)
- Fewer coincidences (`COINCIDENCE_RATE=0.1`)
- Use medium tension curve
- Enable case library for classic mystery references

---

## 8. Fantasy/Cultivation Configuration

**Scenario**: Fantasy, cultivation, upgrade-flow stories.

```ini
# Genre
STORY_GENRE=玄幻+修仙|升级流|男频

# Director engine (fantasy needs excitement)
DRAMA_LEVEL=0.7
CONFLICT_FREQUENCY=0.6
NEW_FACE_RATE=0.2  # Frequent new characters

# Tension curve
TENSION_CURVE=roller  # Roller coaster

# Time system
TIME_RATIO=3600  # fast lane (default 1 = real time; 3600 ≈ 24 s per story day)
```

**Configuration Details**:

| Setting | Value | Description |
|---------|-------|-------------|
| `STORY_GENRE` | `玄幻+修仙\|升级流\|男频` | **Story genre**. Manually specify genre. Fantasy/cultivation is usually upgrade-flow. |
| `DRAMA_LEVEL` | `0.7` | **Drama level**. 0.7 = moderate drama. Fantasy needs excitement but not too much. |
| `CONFLICT_FREQUENCY` | `0.6` | **Conflict frequency**. 0.6 = higher. Fantasy needs frequent conflicts to drive upgrades. |
| `NEW_FACE_RATE` | `0.2` | **New character rate**. 0.2 = higher. Fantasy needs frequent new characters to expand world. |
| `TENSION_CURVE` | `roller` | **Tension curve**. `roller` = roller coaster. Fantasy needs dramatic ups and downs. |
| `TIME_RATIO` | `3600` | **Time ratio**. N story seconds per real second.
  **Default is 1 (real time)**; the 3600 example means a story day takes about 24 seconds — a fast lane for long fantasy arcs. |

**Fantasy Tips**:
- Use roller coaster tension curve
- Increase new character rate
- Fast pace time system
- Reference "A Record of a Mortal's Journey to Immortality", "Shrouding the Heavens", etc.

---

## 9. Local Model Configuration (Ollama, optional)

> **This chapter is optional. Not installing Ollama does not affect normal use in any way.**
> The default setup uses a cloud API (`LLM_PROVIDER=openai_compatible`) plus keyword retrieval
> (`EMBEDDING_PROVIDER=none`) and runs out of the box, with no local model service to install.
> Only read this chapter if you want the content to **never leave your machine**.

> **About "vector retrieval" (`EMBEDDING_*`)**: the Tianji · AI Model Config page **no longer shows**
> this switch (downgraded 2026-10-25). The reason is that `llm/embedding.py` is **not wired into**
> the memory-retrieval path yet — so whether you put `none` / `api` / `local` / `ollama` there,
> **it makes no difference to the simulation**. The default `none` (keyword matching) is what the
> program actually uses. To change it you must edit `.env` by hand; the UI switch will come back
> once embeddings are genuinely wired in.

**Scenario**: Don't want to send data to cloud, use local models.

```ini
# LLM Configuration
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama  # Ollama doesn't need real key

# Models (need to pull first)
MODEL_FRONT=qwen2.5:14b
MODEL_DAILY=qwen2.5:7b
MODEL_CHEAP=qwen2.5:7b

# Vector retrieval (use Ollama embedding)
EMBEDDING_PROVIDER=ollama
EMBEDDING_OLLAMA_MODEL=nomic-embed-text
EMBEDDING_OLLAMA_URL=http://localhost:11434

# Turn off online lookup (compliance itself runs locally and sends nothing out)
ONLINE_LOOKUP=false

# MCP: the three built-in servers are local and read-only — safe to leave on
MCP_ENABLED=true
MCP_TIMEOUT_SECONDS=20
```

**Configuration Details**:

| Setting | Value | Description |
|---------|-------|-------------|
| `LLM_PROVIDER` | `ollama` | **Protocol**. Use Ollama local service. |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | **Ollama address**. Default local port 11434. |
| `LLM_API_KEY` | `ollama` | **API Key**. Ollama doesn't need real key, fill anything. |
| `MODEL_FRONT` | `qwen2.5:14b` | **Premium tier model**. Qwen2.5 14B, good quality. Need `ollama pull qwen2.5:14b`. |
| `MODEL_DAILY` | `qwen2.5:7b` | **Daily tier model**. Qwen2.5 7B, fast. Need `ollama pull qwen2.5:7b`. |
| `MODEL_CHEAP` | `qwen2.5:7b` | **Budget tier model**. Qwen2.5 7B, fast. |
| `EMBEDDING_PROVIDER` | `ollama` | **Vector retrieval**. Use Ollama embedding. |
| `EMBEDDING_OLLAMA_MODEL` | `nomic-embed-text` | **Ollama embedding model**. Need `ollama pull nomic-embed-text`. |
| `EMBEDDING_OLLAMA_URL` | `http://localhost:11434` | **Ollama address**. |
| `ONLINE_LOOKUP` | `false` | **Online lookup**. Disable online search, data stays local. |
| `MCP_ENABLED` | `true` | **MCP master switch**. It only gates *permission to call*; the three built-in servers (Project Lore / Timeline / Clock) are **local, read-only, never leave the machine**, so leaving this on is safe. The web templates live in `mcp_servers.yaml` and default to `false` individually. |
| `MCP_TIMEOUT_SECONDS` | `20` | **Per-call MCP timeout**. First start of a server (especially npx-based) can be slow — raise this if you see timeouts. |

**A note on embeddings**: `EMBEDDING_PROVIDER` takes four values, and **only `ollama` requires you to
install Ollama first**:

| Value | What you must install | Notes |
|---|---|---|
| `none` (default) | **nothing** | keyword matching instead; zero dependencies |
| `api` | nothing, but you need an account with a `/embeddings` endpoint | reuses the key above, billed per token |
| `local` | `pip install sentence-transformers` | downloads a ~100MB model on first run |
| `ollama` | **Ollama plus pulled models** | fully local, no network |

**Ollama Installation** (only needed when `EMBEDDING_PROVIDER=ollama` or `LLM_PROVIDER=ollama`):
1. Download: https://ollama.com
2. Install and start
3. Pull LLM model: `ollama pull qwen2.5:14b`
4. Pull embedding model: `ollama pull nomic-embed-text`

**Ollama Embedding Models** (only needed when `EMBEDDING_PROVIDER=ollama`):
- `nomic-embed-text`: General purpose, good quality (recommended)
- `mxbai-embed-large`: Larger model, better quality
- `bge-m3`: Multi-language support

---

## 10. Debug Configuration

**Scenario**: Development debugging, need detailed logs.

```ini
# Debug mode
DEBUG_MODE=true
# NOTE: LOG_LEVEL currently has no effect (the main log always records DEBUG and above)
# LOG_LEVEL=DEBUG

# Save raw logs
SAVE_RAW_LOGS=true

# Demo mode (optional, avoid real API calls)
MOCK_LLM=true
```

**Configuration Details**:

| Setting | Value | Description |
|---------|-------|-------------|
| `DEBUG_MODE` | `true` | **Debug mode**. Also writes the **first 200 characters of each LLM request** into the **main log**, and lets the ledger store the **full response** (200 chars otherwise). ⚠ It does **not** affect the dialogue log — that one always records everything. |
| `LOG_LEVEL` | (any value) | ⚠ **Currently has no effect** (stated plainly): the value is saved but the logger does not read it — the main log **always records DEBUG and above**. |
| `SAVE_RAW_LOGS` | `true` | **Save the call ledger**. Writes to `logs/llm_calls.jsonl` (**not** inside the run folder, and it **accumulates across runs**). Affects the ledger only — not the main or dialogue log. |
| `MOCK_LLM` | `true` | **Demo mode**. Optional, avoid real API calls. Use demo mode for debugging to save tokens. |

**Log Locations** (all three explained in the User Manual §12):
- Main log: `logs/nws_<title>_<time>.log` — program flow (usernames / keys are masked)
- Dialogue log: `logs/nws_<title>_dialogue_<time>.log` — every LLM exchange in full (**not masked**)
- Call ledger: `logs/llm_calls.jsonl` — one line per call, accumulating across runs

> ⚠ **There is no `nws_debug.log` file** (older docs said so by mistake). With
> `DEBUG_MODE=true`, debug detail goes into the **main log** (plus the first 200 characters of
> each request, and full responses in the ledger).

**Debug Information Includes**:
- Full LLM request/response
- Agent decision details (memory retrieval, actions, dialogue)
- Director judgment logic (tension, drama level, stall detection)
- Memory retrieval details (sorting scores, top-K results)

---

## 11. Compliance Configuration

**Scenario**: Need strict content review.

```ini
# Compliance master switch
COMPLIANCE_ENABLED=true

# Jurisdiction
COMPLIANCE_JURISDICTION=zh_us  # Dual law union

# Review level
COMPLIANCE_LEVEL=strict  # Strict

# LLM review
COMPLIANCE_LLM_REVIEW=always  # Review every item
COMPLIANCE_MODEL=             # Which tier reviews (blank = budget tier)

# ⚠ External compliance services (aliyun_green / tencent_cm / baidu) are **not implemented**.
#   The six COMPLIANCE_EXTERNAL* settings were removed from the program — do not set them;
#   they have no effect. Compliance today is "lexicon rules + local LLM review", all on this machine.
```

**Configuration Details**:

| Setting | Value | Description |
|---------|-------|-------------|
| `COMPLIANCE_ENABLED` | `true` | **Compliance master switch**. Enable compliance detection. Reviews input settings and character actions. |
| `COMPLIANCE_JURISDICTION` | `zh_us` | **Jurisdiction**. `zh_us` dual law union, conflicts follow Chinese law. `zh` Chinese only, `us` US only. |
| `COMPLIANCE_LEVEL` | `strict` | **Review level**. `strict` C1 strict, all sensitive content reviewed. `standard` standard, only flagged items. `relaxed` only C0 (legally prohibited). |
| `COMPLIANCE_LLM_REVIEW` | `always` | **LLM review strategy**. `always` review every item (expensive but accurate). `hybrid` only flagged items (recommended). `never` rule layer only (fast but may miss). |
| `COMPLIANCE_MODEL` | blank | **Which tier reviews**. Blank = budget tier. |

**Compliance Levels**:
- `strict`: C1 strict, all sensitive content reviewed
- `standard`: Standard, only flagged items reviewed (recommended)
- `relaxed`: Only C0 (legally prohibited)

---

## 12. FAQ

### Q: The narrative in the centre column reads like a flat list — I can't tell who is speaking and who is doing something

Narrative output defaults to **screenplay style** (scenes and beats, with actions
kept separate from dialogue). If you are seeing one continuous block of text, either
it was switched back, or you opened an old run folder:

```ini
# Screenplay (default): scenes + time / place / entrances / narration / dialogue / action / meanwhile
OUTPUT_FORMAT=script

# Revert to the old free text
# OUTPUT_FORMAT=prose
```

Tuning:

```ini
# No auto ambient lines (the scene-opening and quiet-moment sentence)
SCRIPT_AMBIENT=false

# Stills: off / map (scene only) / portrait (characters only) / both (default)
SCRIPT_IMAGES=off

# Scene length before splitting
SCRIPT_SCENE_MAX_ENTRIES=40
```

Full format spec (including how to read `〔同时〕` and `〔切至〕`):
[剧本输出格式.md](剧本输出格式.md) and User Manual 4.2.2.

### Q: Do the images in the centre column cost anything?

No. Scene stills and character portraits are **drawn locally with Pillow** — zero
cost, nothing leaves the machine. Paid text-to-image illustrations are **not** part
of the default switches and must be enabled separately.

### Q: API connection failed?

```ini
# Check configuration
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-your-key

# Or use demo mode
MOCK_LLM=true
```

### Q: Token consumption too fast?

```ini
# Lower budget
TOKEN_BUDGET_PER_DAY=50000

# Disable non-essential features
REVIEW_PASS=false
FEWSHOT_FROM_NOVEL=false
BACKGROUND_MODE=off

# Use cheaper model
MODEL_CHEAP=deepseek-flash
```

### Q: Character out of character (OOC)?

```ini
# Check if character cards are complete
# No direct config in .env, need to supplement in project settings:
# - Character secrets
# - Character catchphrases
# - Behavioral red lines

# Use reflection function
# In main interface: reflect <character-name>
```

### Q: Story can't continue?

```ini
# Lower plot adherence
PLOT_ADHERENCE=0.3

# Or switch to open mode
RUN_MODE=open
OPEN_CHECKPOINT_EVERY_DAYS=3
```

### Q: How to start from middle?

```ini
# Specify starting node
STORY_START_POINT=N03

# Or start from beginning
STORY_START_POINT=begin
```

### Q: How to check token consumption?

In main interface:
```
budget
```

Or detailed bill:
```
status
```

### Q: How to switch display mode?

Shortcuts:
- `Ctrl+D`: Toggle reading/fast mode
- `Ctrl+F`: Toggle auto-follow
- `Enter`: Catch up to latest

Or commands:
```
display reading
display fast
readspeed 20
```

### Q: How to enable film shot cards?

```ini
FILM_MODE=true
DISPLAY_FILM_CARDS=true
```

In main interface enter `film on`.

---

## Configuration Template Summary

### Minimal Configuration (Demo Mode)

```ini
MOCK_LLM=true
```

### Standard Configuration (First Use)

```ini
LLM_API_KEY=sk-your-key
TOKEN_BUDGET_PER_DAY=100000
AUTO_RUN_DAYS=1
```

### Budget Configuration

```ini
LLM_API_KEY=sk-your-key
MODEL_FRONT=deepseek-chat
MODEL_DAILY=deepseek-flash
MODEL_CHEAP=deepseek-flash
TOKEN_BUDGET_PER_DAY=50000
REVIEW_PASS=false
BACKGROUND_MODE=off
```

### High Quality Configuration

```ini
LLM_API_KEY=sk-your-key
MODEL_FRONT=deepseek-reasoner
MODEL_DAILY=deepseek-chat
MODEL_CHEAP=deepseek-chat
TOKEN_BUDGET_PER_DAY=500000
REVIEW_PASS=true
REVIEW_THRESHOLD=0.8
EMBEDDING_PROVIDER=local
```

### Debug Configuration

```ini
MOCK_LLM=true
DEBUG_MODE=true
LOG_LEVEL=DEBUG
```

---

**For more parameter documentation, see `.env.example`.**

**Happy Writing!** 📚✨