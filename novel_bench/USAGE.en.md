# Usage

For one workflow: "I changed something — did the output get better?"
Everything is manual; the tool never spends money on its own.

---

## 1. Prerequisites

- The simulator itself runs (`NovelWorldSimulator/.venv/Scripts/python.exe main_gui.py`).
- No extra packages: the harness uses the app's existing `PyYAML` and the standard library.
- On Windows, always call Python by absolute path (`./.venv/Scripts/python.exe`), never rely on PATH.

Run every command from **`NovelWorldSimulator/`**:

```bash
cd "C:/Users/chao/OneDrive/桌面/小说世界AI模拟/NovelWorldSimulator"
```

---

## 2. First-time setup

```bash
cp novel_bench/.env.example novel_bench/.env
```

Fill in at least:

```dotenv
NB_LLM_API_KEY=sk-...
NB_JUDGE_MODEL=deepseek-chat
```

`NB_LLM_BASE_URL` defaults to DeepSeek. Any OpenAI-compatible `/chat/completions` endpoint works —
Qwen, GLM, Kimi, OpenRouter, vLLM, Ollama (`http://localhost:11434/v1`).
See `docs/models.md` for model selection and cost.

> The **generation** model is not configured here. It comes from the app's own
> `.env` / `llm_models.json`. To change how the simulation writes, change the app.

---

## 3. Commands

```bash
python novel_bench/bench/cli.py <command> [options]
```

| Command | Costs money | What it does |
|---|---|---|
| `check` | no | validate the dataset schema and print stats |
| `list [--kind 网络]` | no | list every case |
| `build --case <id>` | no | write the generated settings files only |
| `smoke [--preset smoke]` | no | build + assemble; verifies people/world/rules are actually read |
| `run --preset <p> --ticks <n>` | **yes** | run the simulation, write `results/<run-id>/` |
| `metrics --run <dir>` | no | recompute counters (after changing the formulas) |
| `judge --run <dir> [--case <id>]` | **yes** | LLM review, writes `cases/*/judge.json` |
| `report --run <dir>` | no | build `report.md` / `report.html` / `scores.csv` |
| `all --preset smoke` | **yes** | `run` + `report` (no judge) |
| `compare --a <old> --b <new>` | no | per-case delta between two runs |

Useful options:

- `--ticks 8` — one beat is one model round-trip (1–2 min measured, review included).
  With the opening (~9 min) and wrap-up, **8 beats ≈ 20–25 min per case**; use `--ticks 4` (~12 min) to iterate faster.
- `--case <id>` — a single case, for debugging.
- `--preset smoke|core|full` — 4 / 14 / 28 cases.
- `--run-id <name>` — name the output folder (`before-x`, `after-x`) so comparisons are obvious.

---

## 4. A full loop

```bash
# 1) make sure nothing is broken (free, ~20 s)
python novel_bench/bench/cli.py check
python novel_bench/bench/cli.py smoke --preset smoke

# 2) baseline (costs money; 4 cases ≈ 1.5 h)
python novel_bench/bench/cli.py run   --preset smoke --run-id base
python novel_bench/bench/cli.py judge --run novel_bench/results/base
python novel_bench/bench/cli.py report --run novel_bench/results/base

# 3) change the code (prompts / scheduling / budgets / export)

# 4) re-run with the same cases, same ticks, same judge
python novel_bench/bench/cli.py run   --preset smoke --run-id after-fix
python novel_bench/bench/cli.py judge --run novel_bench/results/after-fix
python novel_bench/bench/cli.py report --run novel_bench/results/after-fix

# 5) compare
python novel_bench/bench/cli.py compare --a novel_bench/results/base --b novel_bench/results/after-fix
```

How to read the result (`smoke` can only prove "it broke", not "it improved"):

- `hygiene_mean` down by 5+ → look for repetition or meta-mark regressions first.
- `gap_mean` better by <3 with a CI crossing 0 → noise, do not claim a win.
- A jump like `win_rate` 10% → 25% is a structural change.
- For a conclusion, use `core`, not `smoke`.

---

## 5. Output layout

```
results/base/
├── run.json                what ran, with which parameters
├── summary.json            all aggregates (everything downstream reads this)
├── scores.csv              one row per case, opens in Excel
├── report.md               human report
├── report.html             same content, self-contained
├── judge_cache.jsonl       review cache (identical prompts are never re-paid)
└── cases/hlm-01/
    ├── meta.json           beats, seconds, chars, timeout flag
    ├── transcript.jsonl    raw entries (kind / text / who / time)
    ├── transcript.md       the same, readable
    ├── metrics.json        counters + penalty breakdown
    └── judge.json          six dimension scores, comments, per-judge raw output, pairwise
```

`transcript.md` is the primary evidence. Judge comments are an index, not a verdict.

---

## 6. Adding a work

Create `novel_bench/dataset/works/NN_id.yaml` by copying any existing file. Required fields are
documented in `dataset/schema.md`; the essentials:

- `bible`: 400–800 characters of worldview, 3–5 hard `rules`, 3–5 `places`, 3–5 `people`
  (身份/性格/口癖/秘密/目标/红线), `relations`, `foreshadows`, `details`, and a `style` block
  (`pov`, `era`, `sentence`, `diction`, `taboos`).
- `cases[]`: `cut` (开篇/中段/转折/高潮前/收束), `place`, `present` (must exist in `people`),
  `scene_seed`, `previously` (required unless `cut: 开篇`), and `ground_truth`
  (`beats`, `excerpt`, `divergence_note`).

Then:

```bash
python novel_bench/bench/cli.py check
python novel_bench/bench/cli.py smoke --case my-01
```

`check` catches the silent killers: misspelled Chinese keys, `present` names not in `people`,
relations pointing at undefined people, a non-opening case without a recap, an overlong excerpt.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `smoke` reports "people 0" | Chinese keys misspelled in `人物.yaml` | compare with `project_builder._people` |
| `run` ends immediately with `entries=0` | the app's LLM endpoint is unreachable | run the simulator once from the GUI first |
| `timed_out: true` | a beat is very slow or the model hung | raise `NB_RUN_TIMEOUT`, use a faster model |
| `judge` returns HTTP 4xx for every call | wrong model name or no quota | test the endpoint directly |
| Judge output is not JSON | model does not follow instructions | switch model; fenced-JSON salvage is already in place |
| `ref_mean` is low | paraphrase references are weaker than the original | check the `license` field before drawing conclusions |
| `results/.work` fills up | `NB_KEEP_PROJECTS=true` | set it back to false |
| One case takes 40+ min | thinking is on (new flash thinks by default) | `--think-mode off`, or lower `--ticks` |
| Judge is slow / output unparseable | the judge model is thinking | `NB_JUDGE_THINKING=auto` (default) or `off` |
| Stray "flet working" windows | unrelated: left by GUI verification scripts | see `util/flet_shutdown.py` |

---

## 8. Division of labour with the existing checks

```bash
# after a code change: first prove it does not crash
python tools/run_all_verifications.py

# only when green: measure whether it writes better
python novel_bench/bench/cli.py run --preset smoke
```

A red check means a bug. A dropped benchmark score means quality regressed. They are different jobs,
and fixing one should not be used to explain away the other.
