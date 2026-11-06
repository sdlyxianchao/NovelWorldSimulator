
# Novel World AI Simulator · Configuration Classification

> This document explains the storage location and scope of configuration items.

> **Removed since 2026-10-06**: the settings below were **deleted from the program** (a knob you
> can turn that does nothing is a liability), so this document no longer lists them:
> `NOVEL_LOG_MODEL`, `EMBED_MAP_IN_LOG`, `TYPEWRITER`, `SLOW_ON_KEY_EVENT`, `TUI_THEME`,
> `TUI_REFRESH_MS`, `MAP_ENABLED`, `COMMAND_BOX_COLLAPSED`, `FIRST_RUN_WIZARD`, the six
> `COMPLIANCE_EXTERNAL*` items, `COMPLIANCE_AGGREGATION`, `PROJECT_NAME`, `PROJECT_PATH`,
> `CLOCK_MODE`. Rationale: see the comments in `config.py` and the fake-knob list in
> `tools/verify_config_sweep.py`.

---

## Configuration Layers

```
Software Settings (.env)
    └── Project Settings (<project-name>.nwsproj)
            └── Save Settings (save-info.json + state.db)
```

---

## 1. Software Settings (.env)

**Location**: Program root directory `.env`

**Scope**: Global, shared across all projects

**Characteristics**:
- Not specific to any novel
- LLM connection, token budget, interface settings, etc.
- Requires program restart to take effect (except some)

### Configuration List

#### LLM Connection
| Setting | Description |
|---------|-------------|
| `LLM_PROVIDER` | Protocol (openai_compatible / ollama) |
| `LLM_BASE_URL` | API address |
| `LLM_API_KEY` | API Key (**required**) |
| `LLM_TIMEOUT_SECONDS` | Request timeout (seconds) |
| `LLM_MAX_RETRIES` | Failure retry count |
| `LLM_MAX_CONCURRENCY` | Global concurrency limit |
| `MOCK_LLM` | Demo mode (zero cost) |
| `MODEL_FRONT` | Premium tier model |
| `MODEL_DAILY` | Daily tier model |
| `MODEL_CHEAP` | Budget tier model |
| `MODEL_PRICE_OVERRIDES` | Manual price override (`hit/miss/output`, or the old `miss/output`) |
| `LLM_OFFPEAK_DISCOUNT` | **Off-peak discount** (added 2026-10-12, default 0.5). Applies only to peak-priced models (DeepSeek); 1.0 disables |
| `LLM_DEDUP_ENABLED` | **Same-question reuse** switch (added 2026-10-12, on by default) |
| `LLM_DEDUP_PURPOSES` | Reusable-purpose whitelist (**empty = the built-in default in code**, see `llm/dedup.py`) |
| `LLM_DEDUP_TTL_SECONDS` | Reuse shelf life in seconds (default 3600) |
| `EMBEDDING_PROVIDER` | Vector retrieval (local / api / ollama / none). **No longer shown on the Tianji page** (downgraded 2026-10-25: `llm/embedding.py` is not wired into retrieval); edit `.env` only |
| `EMBEDDING_MODEL_LOCAL` | Local vector model |
| `EMBEDDING_MODEL_API` | API vector model |
| `EMBEDDING_OLLAMA_MODEL` | Ollama embedding model |
| `EMBEDDING_OLLAMA_URL` | Ollama service address |

#### Token Economy
| Setting | Description |
|---------|-------------|
| `TOKEN_BUDGET_PER_DAY` | Daily token budget |
| `TOKEN_WARN_AT` | Budget warning threshold |
| `BUDGET_EXHAUST_POLICY` | Budget exhaustion policy |
| `CONTEXT_CACHE` | Context cache |
| `SUMMARIZE_MEMORY_AFTER` | Memory compression threshold |
| `MAX_CONTEXT_TOKENS` | Max context tokens |

#### Output & Logging
| Setting | Description |
|---------|-------------|
| `LOG_LEVEL` | Log level |
| `DEBUG_MODE` | Debug mode |
| `SAVE_RAW_LOGS` | Save raw logs |
| `LANGUAGE` | Language |
| `UI_OPACITY` | UI transparency (%): **the higher, the more transparent** — 0 = fully opaque, 100 = most transparent (panel base keeps 30% floor). Affects **only** the start screen and the run screen; **dialogs are never affected** |
| `LOG_ROTATE_DAYS` | Log retention days |
| `SNAPSHOT_KEEP` | Snapshot retention count |
| `OUTPUT_FORMAT` | Narrative output format (screenplay / free text) |
| `SCRIPT_AMBIENT` | Auto ambient narration |
| `SCRIPT_IMAGES` | Stills placement (scene / portrait) |
| `SCRIPT_SCENE_MAX_ENTRIES` | Max entries per scene |

#### Display Rhythm
| Setting | Description |
|---------|-------------|
| `DISPLAY_PROFILE` | Display mode (reading / fast) |
| `READING_CPS` | Reading speed (chars/sec) |
| `DISPLAY_BACKLOG_LIMIT` | Backlog limit |
| `DISPLAY_CATCHUP_POLICY` | Backlog policy |
| `DISPLAY_LOCK_SIM` | Lock mode |

#### Interface Settings
| Setting | Description |
|---------|-------------|

#### Reference & Research
| Setting | Description |
|---------|-------------|
| `REFERENCE_DIR` | User reference library directory |
| `REFERENCE_INJECT_MAX` | Single injection limit |
| `SKILLS_DIR` | Skills directory |
| `SKILLS_ENABLED` | Skills enabled |
| `MCP_CONFIG` | MCP config file |
| `MCP_ENABLED` | MCP master switch (web servers have their own `enabled`) |
| `MCP_TIMEOUT_SECONDS` | Per-call MCP timeout |
| `RESEARCH_AUTO` | Auto research |
| `RESEARCH_MAX_PER_DAY` | Daily research limit |
| `RESEARCH_CACHE_DAYS` | Research cache days |
| `ONLINE_LOOKUP` | Online search |

#### AI Quality
| Setting | Description |
|---------|-------------|
| `PROMPTS_DIR` | Prompts directory |
| `PROMPT_WATCH` | Prompt hot reload |
| `REVIEW_PASS` | Review pass |
| `REVIEW_THRESHOLD` | Review threshold |
| `FEWSHOT_FROM_NOVEL` | Few-shot from text |

#### Film Shots
| Setting | Description |
|---------|-------------|
| `FILM_MODE` | Film shot cards |
| `DISPLAY_FILM_CARDS` | Interface shows film cards |

#### Compliance
| Setting | Description |
|---------|-------------|
| `COMPLIANCE_ENABLED` | Compliance master switch |
| `COMPLIANCE_JURISDICTION` | Jurisdiction |
| `COMPLIANCE_LEVEL` | Review level |
| `COMPLIANCE_SCAN_ON_INGEST` | Ingest static scan |
| `COMPLIANCE_LLM_REVIEW` | LLM review strategy |
| `COMPLIANCE_ACTION` | Default action on hit |
| `COMPLIANCE_LOG` | Compliance hit log |
| `COMPLIANCE_WHITELIST` | Project whitelist |
| `COMPLIANCE_MODEL` | Compliance Agent model |
| `COMPLIANCE_POLICY_DIR` | Custom policy directory |
| `COMPLIANCE_WATCH_POLICY` | Policy hot reload |
| `COMPLIANCE_CHECKPOINTS` | Checkpoint coverage |

---

## 2. Project Settings (.nwsproj)

**Location**: `Projects/<project-name>/<project-name>.nwsproj`

**Scope**: Single project, shared across all saves

**Characteristics**:
- Specific to a novel
- Genre, style, run mode, etc.
- Can be modified in project settings interface
- Determined when creating project, adjustable during run

### Configuration List

#### Project Info
| Setting | Description |
|---------|-------------|
| `DEFAULT_PROJECTS_DIR` | Projects root directory |

#### Genre & Style (**Project-specific**)
| Setting | Description | Why Project-level |
|---------|-------------|-------------------|
| `STORY_GENRE` | Story genre | **Each novel has different genre** (mystery/fantasy/romance) |
| `NOVEL_STYLE` | Style source | **Each novel has different style** |
| `NOVEL_STYLE_CUSTOM` | Custom style | **Project-specific style description** |
| `CRAFT_LIBRARY` | Craft library | **Different genres need different libraries** |
| `CRAFT_CASES_ENABLED` | Case library | **Different genres enable different cases** |
| `SCENE_NAME` | Scene name | **Project-specific scene** |
| `SCENE_START_HINT` | Opening scenario | **Project-specific opening** |
| `CALENDAR_DISPLAY` | Calendar display | **Project-specific calendar** (regnal for historical, modern for contemporary) |
| `输出语言` (in `.nwsproj`) | Output language (`auto`/`zh`/`en`) | **The same machine must support both "English draft → Chinese output" and "Chinese draft → English output"** — pick it per project (stored in `.nwsproj`, not `.env`) |

#### Run Boundaries (**Project-specific**)
| Setting | Description | Why Project-level |
|---------|-------------|-------------------|
| `RUN_MODE` | Run mode | **Different projects may need different modes** |
| `OPEN_CHECKPOINT_EVERY_DAYS` | open mode checkpoint interval | **Project-specific** |
| `STORY_DAY_EVERY_DAYS` | story_day mode pause interval | **Project-specific** |
| `STORY_START_POINT` | Story starting point | **Each novel has different starting point** |
| `ENDING_SCENE` | Ending scene | **Project-specific** |
| `PLOT_ADHERENCE` | Plot adherence | **Different projects need different adherence** |
| `AUTO_SUMMARY_ON_END` | Auto-export **run report** on end | **Project-specific**; off by default (the report carries billing and OOC analysis — better read after the run) |
| `STORY_DOC_MODEL` | Story doc tier | **Project-specific** |
| `SUMMARY_MODEL` | Run report tier | **Project-specific** |

#### Export (**Project-specific**, §10.10)
> These switches only control **whether to auto-export when a run ends**.
> **Manual export is always available** — including mid-run, where only
> completed days are included. Turning auto off does not remove the feature.

| Setting | Description | Why Project-level |
|---------|-------------|-------------------|
| `EXPORT_ON_END_REFERENCE` | Auto-export **novel reference** (source book) | **Project-specific**; free — whether to keep one per run is a project call |
| `EXPORT_ON_END_NOVEL` | Auto-export **novel version** (readable draft) | **Project-specific**; free, same reasoning |
| `EXPORT_ON_END_GUIDE` | Auto-export **writing guide** (outline) | **Project-specific**; costs LLM calls, off by default |
| `EXPORT_NOVEL_POLISH` | Extra **LLM-polished draft** of the novel version | **Project-specific**; costs LLM calls and rewrites wording, off by default |

#### Time System (**Project-specific**)
| Setting | Description | Why Project-level |
|---------|-------------|-------------------|
| `GAME_START_TIME` | Game start time | **Each novel has different time** |
| `TIME_RATIO` | Time ratio | **Different projects need different pace** |
| `BEAT_SECONDS` | Beat (story seconds) | **Different projects need different pace** |
| `QUIET_MINUTES` | Quiet threshold | **Different projects need different pace** |
| `TICK_REAL_MS` | Heartbeat interval | **Project-specific** |
| `AUTO_RUN_DAYS` | Run day limit | **Project-specific** |
| `PAUSE_AT_NIGHT` | Night pause | **Project-specific** |

#### Agent Core (**Project-specific**)
| Setting | Description | Why Project-level |
|---------|-------------|-------------------|
| `AGENT_MAX` | Max foreground agents | **Different projects have different character counts** |
| `MEMORY_RETRIEVE_K` | Memory retrieval top-K | **Project-specific** |
| `WEIGHT_RECENCY` | Recency weight | **Project-specific** |
| `WEIGHT_IMPORTANCE` | Importance weight | **Project-specific** |
| `WEIGHT_RELEVANCE` | Relevance weight | **Project-specific** |
| `RECENCY_DECAY` | Recency decay | **Project-specific** |
| `IMPORTANCE_SCORING` | Importance scoring | **Project-specific** |
| `REFLECTION_THRESHOLD` | Reflection threshold | **Project-specific** |
| `REFLECTION_MAX_PER_DAY` | Daily reflection limit | **Project-specific** |
| `PLANNING_ENABLED` | Hierarchical planning | **Project-specific** |
| `PLAN_BLOCK_MINUTES` | Plan block minutes | **Project-specific** |
| `DIALOGUE_MIN_TURNS` | Dialogue min turns | **Project-specific** |
| `DIALOGUE_MAX_TURNS` | Dialogue max turns | **Project-specific** |
| `GROUP_CHAT_MAX` | Group chat max | **Project-specific** |

#### Foreground/Background (**Project-specific**)
| Setting | Description | Why Project-level |
|---------|-------------|-------------------|
| `BACKGROUND_MODE` | Background mode | **Project-specific** |
| `BACKGROUND_TICK_MINUTES` | Background batch interval | **Project-specific** |
| `PROMOTE_ON_STAGE` | Auto promote on stage | **Project-specific** |
| `BACKGROUND_EVENT_RATE` | Background event rate | **Project-specific** |

#### Director Engine (**Project-specific**)
| Setting | Description | Why Project-level |
|---------|-------------|-------------------|
| `DIRECTOR_ENABLED` | Director engine switch | **Project-specific** |
| `DRAMA_LEVEL` | Drama level | **Different projects need different drama** |
| `CONFLICT_FREQUENCY` | Conflict frequency | **High for mystery / low for slice-of-life** |
| `REVEAL_PACING` | Reveal pacing | **Slow for mystery / fast for fantasy** |
| `COINCIDENCE_RATE` | Coincidence rate | **Project-specific** |
| `NEW_FACE_RATE` | New character rate | **Project-specific** |
| `TENSION_CURVE` | Tension curve | **Different genres different curves** |
| `CLIMAX_EVERY_DAYS` | Climax interval | **Project-specific** |
| `BRANCH_PROPOSALS` | Branch proposals count | **Project-specific** |
| `BRANCH_WAIT_SECONDS` | Branch wait seconds | **Project-specific** |
| `BRANCH_AUTO_POLICY` | Branch timeout policy | **Project-specific** |
| `STALL_WINDOW_MINUTES` | Stall detection window | **Project-specific** |
| `REPETITION_SIMILARITY` | Dialogue loop similarity | **Project-specific** |
| `INTERVENTION_POLICY` | Intervention policy | **Project-specific** |

---

## 3. Save Settings (save-info.json + state.db)

**Location**: `Projects/<project-name>/saves/<save-name>/`

**Scope**: Single save

**Characteristics**:
- Records game state at save time
- Auto-save (end of day / key events) or manual save
- Can restore to save state

### save-info.json

```json
{
  "name": "auto-save_2026-10-04-20-00",
  "description": "Game day 3, 19:30\nWeather: Rain, Scene: Riverside Teahouse\nCurrent node: N03, Tension: 0.6\nPresent: Shen Yan, A Zhi, Lu Jiu",
  "time": "2026-10-04 20:00:00",
  "game_day": 3,
  "game_time": "Day 3, Xu Hour (19:30)",
  "current_node": "N03",
  "tension": 0.6,
  "event_count": 15,
  "weather": "Rain",
  "scene": "Riverside Teahouse",
  "scene_desc": "Riverside teahouse, rainy night",
  "on_stage": ["Shen Yan", "A Zhi", "Lu Jiu"],
  "off_stage": ["Lu Jiu"],
  "active_lines": ["Old story surfaces"],
  "activated_foreshadows": ["F01"]
}
```

### state.db

Stores runtime state:
- Memory stream (memory table)
- Event records (events table)
- Snapshot records (snapshots table)
- Compliance records (compliance_log table)
- Billing records (budget_log table)

### settings/story-progress.yaml

```yaml
nodes:
  - id: N01
    name: Rainy Night Visitor
    summary: A stranger knocks on the door on a rainy night
    criteria: Visitor mentions the key word of the old story
    status: completed
  - id: N02
    name: Old Story Surfaces
    summary: Characters react differently
    criteria: At least two people disagree on the same event
    status: in_progress
```

---

## Configuration Priority

When the same setting exists at multiple levels, priority is:

```
Save Settings > Project Settings > Software Settings
```

**Example**:
- `.env` has `STORY_GENRE=auto`
- `.nwsproj` has `STORY_GENRE=mystery+supernatural|anthology|male`
- Final: `mystery+supernatural|anthology|male`

---

## Best Practices

### Software Settings (.env)

- LLM connection (API Key, models, etc.)
- Token budget (global budget control)
- Interface settings (theme, display mode, etc.)
- Reference library (skills directory, MCP, etc.)
- Compliance (jurisdiction, review level, etc.)

### Project Settings (.nwsproj)

- Story genre (mystery/fantasy/romance)
- Run mode (story/open/story_day)
- Director engine parameters (drama level, conflict frequency)
- Time system parameters (time ratio, calendar)
- Agent parameters (max agents, memory parameters)

### Save Settings (save-info.json)

- Game state (day, node, tension)
- Present characters list
- Event count
- Description info

---

**Related Documents**:
- [README](README_EN.md)
- [Configuration Guide](Configuration_Guide.md)
- [User Manual](User_Manual.md)
- [配置指南](配置指南.md)
- [使用说明](使用说明.md)
- [配置分类](配置分类.md)