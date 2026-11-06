# 使用说明

面向"改完一次代码，想量一下有没有变好"的场景。全过程手动触发，工具不会自己跑去花钱。

---

## 1. 前置条件

- 主程序能正常跑：`NovelWorldSimulator/.venv/Scripts/python.exe main_gui.py` 起得来。
- 本工具不额外装包，只用到主程序已有的 `PyYAML`。
- Windows 下用绝对路径调 Python（`./.venv/Scripts/python.exe`），别依赖 PATH。

所有命令都在 **`NovelWorldSimulator/`** 目录下执行：

```bash
cd "C:/Users/chao/OneDrive/桌面/小说世界AI模拟/NovelWorldSimulator"
```

---

## 2. 首次配置

```bash
cp novel_bench/.env.example novel_bench/.env
```

编辑 `novel_bench/.env`，至少填两项：

```dotenv
NB_LLM_API_KEY=sk-...
NB_JUDGE_MODEL=deepseek-chat
```

`NB_LLM_BASE_URL` 默认指向 DeepSeek；换厂商时连 base_url 一起换（任何 OpenAI 兼容端点都行）。
选型建议见 `docs/models.md`。

> 推演用的模型**不在这里配**。它读主程序的 `.env` / `llm_models.json`。
> 想换推演模型，去「天问 · LLM 接入」或改主程序 `.env`。

---

## 3. 命令一览

```bash
python novel_bench/bench/cli.py <命令> [参数]
```

| 命令 | 花钱 | 作用 |
|---|---|---|
| `check` | 否 | 校验数据集 schema，打印统计 |
| `list [--kind 网络]` | 否 | 列出所有用例 |
| `build --case <id>` | 否 | 只生成项目设定集，人工翻看用 |
| `smoke [--preset smoke]` | 否 | 建项目 + 装配，确认"人物/世界观/规则"都读到了 |
| `run --preset <档> --ticks <N>` | **是** | 跑推演，落 `results/<run-id>/` |
| `metrics --run <目录>` | 否 | 重算计数指标（改了 metrics 公式后重跑） |
| `judge --run <目录> [--case <id>]` | **是** | LLM 评审，落 `cases/*/judge.json` |
| `report --run <目录>` | 否 | 汇总 `report.md` / `report.html` / `scores.csv` |
| `all --preset smoke` | **是** | `run` + `report`，不含评审 |
| `compare --a <旧> --b <新>` | 否 | 两次运行的逐用例对比 |

> ⚠ **`metrics` 公式改过之后，历史产物必须重算才能横向比**（2026-10-20 新增了四项：
> 道具循环 / 太碎段 / 憋气段 / 引号混用）。旧 `metrics.json` 里没有这些字段，
> `compare` 会把"字段缺失"当成"没有毛病"，看着像变好了。
> 重算免费，一条命令：`python -m novel_bench.bench.cli metrics --run results/<run-id>`。
> 口径是否与主程序一致，跑 `tools/verify_bench_parity.py` 就知道（两边阈值/词表/结论不一致会红）。

> ⚠ 上面这些命令**只针对数据集里的用例**。想跑 `samples/` 或你自己的素材文件夹 → 见 **§9**。

### 常用参数

- `--ticks 8`：跑多少拍。一拍 = 一次模型往返（实测 1–2 分钟，含审读）。
  加上开场（约 9 分钟）与收尾，**8 拍约 20–25 分钟/用例**。嫌慢就 `--ticks 4`，约 12 分钟/用例。
- `--case <id>`：只跑一个用例，调试用。
- `--preset smoke|core|full`：三档规模。
- `--run-id <名字>`：指定输出目录名，建议用 `before-xxx` / `after-xxx` 便于对比。
- `--kind 网络`：按载体/类型/国别筛，`list --kind 中文` 之类可以先看有什么。

---

## 4. 一次完整的评测流程

```bash
# ① 确认没坏（0 成本，约 20 秒）
python novel_bench/bench/cli.py check
python novel_bench/bench/cli.py smoke --preset smoke

# ② 基线（花钱；smoke 4 例约 1.5 小时）
python novel_bench/bench/cli.py run  --preset smoke --run-id base
python novel_bench/bench/cli.py judge --run novel_bench/results/base
python novel_bench/bench/cli.py report --run novel_bench/results/base

# ③ 改代码（提示词 / 调度 / 预算 / 导出……）

# ④ 复测（同样的用例、同样的拍数、同样的评委）
python novel_bench/bench/cli.py run  --preset smoke --run-id after-fix
python novel_bench/bench/cli.py judge --run novel_bench/results/after-fix
python novel_bench/bench/cli.py report --run novel_bench/results/after-fix

# ⑤ 对比
python novel_bench/bench/cli.py compare --a novel_bench/results/base --b novel_bench/results/after-fix
```

判断标准（`smoke` 只够发现"崩了"）：

- `hygiene_mean` 掉了 5 分以上 ⇒ 先查重复与元标记，多半是回归。
- `gap_mean` 变好 3 分以内、且 CI 跨 0 ⇒ 视为噪声，不要声称改进。
- `win_rate` 从 10% 跳到 25% 这类幅度才算结构性变化。
- 要下结论，用 `core`（14 例），别用 `smoke`。

---

## 5. 产物长什么样

```
results/base/
├── run.json                    这次跑了哪些用例、参数
├── summary.json                全部汇总数据（下游都读它）
├── scores.csv                  Excel 可开，每用例一行
├── report.md                   给人看的报告
├── report.html                 同内容网页版（可直接发给别人）
├── judge_cache.jsonl           评审缓存（同 prompt 不重复付费）
└── cases/
    └── hlm-01/
        ├── meta.json           拍数、耗时、字数、是否超时
        ├── transcript.jsonl    逐条实录（kind / text / who / 时间）
        ├── transcript.md       同上，排版后可读
        ├── metrics.json        计数指标 +  penalties 明细
        └── judge.json          六维分、评语、逐评委原始分、盲评结果
```

`transcript.md` 是判断"到底写成了什么样"的第一手材料；评委结论只当索引。

---

## 6. 加一部新作品

在 `novel_bench/dataset/works/` 新建 `NN_id.yaml`（照抄任意现有文件改）：

```yaml
id: my_novel
title: 书名
title_en: Title
author: 作者
year: "2000"
country: 中国
language: zh
category: 当代          # 古典 / 现代 / 当代 / 网络
medium: 出版            # 出版 / 网络
genres: [类型1, 类型2]
representativeness: |
  一两句：为什么这部值得收（文学史位置 / 类型开创 / 语言特殊）。
license: in_copyright_short_quote
bible:
  worldview: |          # 400–800 字：世界规则、时代、地点、当下局势
  rules:                # 3–5 条硬约束，进 prompt 最前面
    - ...
  places:               # 3–5 处，说明要"能用"
    - 名称: ...
      说明: ...
  people:               # 3–5 人，身份/性格/口癖/秘密/目标/红线
    - 姓名: ...
      身份: ...
      性格: ...
      口癖: ...
      秘密: ...
      目标: ...
      红线: ...
  relations:
    - 甲: 人物A
      乙: 人物B
      关系: 一句话
  foreshadows:
    - 编号: F1
      内容: ...
  details:
    - 名称: 器物
      说明: 一句话
  style:
    pov: 第三人称限知    # 第一人称 / 第三人称限知 / 第三人称全知 / 多视角
    era: premodern      # premodern / modern / contemporary / fantasy / dystopia / steampunk
    sentence: 句法特征
    diction: 用词特征
    dialogue: 对白密度
    taboos: [手机, 咖啡, 分钟]   # 这个词一个字都不许出现
cases:
  - id: my-01
    cut: 中段            # 开篇 / 中段 / 转折 / 高潮前 / 收束
    at: 第几章什么地方
    story_time: "午后"
    place: 与 places 里的名称一致
    present: [人物A, 人物B]      # 必须是 bible.people 里的人
    focus: [人物声音, 关系张力]
    previously: |        # 非开篇必填：150–300 字前情
    scene_seed: |        # 100–200 字：此刻正在发生什么，停在哪一句
    ground_truth:
      beats:             # 4–6 条，作者实际写下的后续
        - ...
      excerpt: |         # 300–500 字：公版可摘原文，在版权期内的写忠实复述
      divergence_note: | # 说明什么必须接住、什么可以自由
```

写完必须跑：

```bash
python novel_bench/bench/cli.py check
python novel_bench/bench/cli.py smoke --case my-01
```

`check` 会报：人物缺字段、present 里有不存在的人、关系引用了没定义的人、非开篇缺前情、
excerpt 过长、genre/category 拼错……这些问题会让推演"看起来跑了但人物是空的"，必须清零。

---

## 7. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `smoke` 报"人物 0" | `人物.yaml` 字段名写错（必须是中文键） | 对照 `project_builder._people` |
| `run` 一开始就结束、`entries=0` | 主程序 LLM 没配好，或 `.env` 里 `LLM_BASE_URL` 不通 | 先用主程序跑一次推演确认 |
| 用例超时（`timed_out: true`） | 单拍太慢或模型卡住 | 调大 `NB_RUN_TIMEOUT`；换快模型 |
| `judge` 全部报 `HTTP 4xx` | 模型名错 / key 没额度 | 单测：`curl` 该端点 |
| 评委输出不是 JSON | 模型不听话 | 换模型；工具已做 fenced-JSON 容错 |
| 报告里 `ref_mean` 很低 | 复述型参考文本天然弱于原文 | 看 `license` 字段，别据此下结论 |
| `results/.work` 堆项目 | `NB_KEEP_PROJECTS=true` | 改回 false；或手动删 |
| 一个用例跑了 40 分钟还没完 | 开着思考（新版 flash 默认先想再写） | `--think-mode off`，或调小 `--ticks` |
| 评审很慢、输出很难解析 | 评委模型在思考 | `NB_JUDGE_THINKING=auto`（默认）或 `off` |
| 桌面上多出 flet 窗口 | 跑过 GUI 判据，与本工具无关 | 见主程序 `util/flet_shutdown.py` |

---

## 8. 与主程序判据的分工

```bash
# 改完代码，先跑判据（守"会不会崩"）
python tools/run_all_verifications.py

# 判据全绿，再跑基准（守"写得好不好"）
python novel_bench/bench/cli.py run --preset smoke
```

判据红了不要跑基准——那是在测量一个坏掉的系统。
基准分掉了不要回头改判据——那是两件事。

---

## 9. 数据集之外：跑你自己的素材（2026-10-18）

本工具只认 `dataset/works/*.yaml` 里写死的用例 —— 好处是"同一把尺子"，代价是
**它量不了你自己的项目**。想量"这次改动放到 `samples/` 或我的项目里，出来的东西
是不是变好了"，用源码树里那个脚本（**不随发布包提供**）：

```bash
cd "C:/Users/chao/OneDrive/桌面/小说世界AI模拟/NovelWorldSimulator"

# samples 里的一篇
./.venv/Scripts/python.exe developers/run_input_folder.py \
    --src "samples/zh/06_科幻_回声站" --name "回声站" --ticks 6 --run-id test-echo

# 自己的素材文件夹（设定/、大纲/、正文/ 那一层）
./.venv/Scripts/python.exe developers/run_input_folder.py \
    --src "C:/路径/我的设定集" --name "我的书" --ticks 6 --run-id test-mine
```

- 走的是**开卷**那条路（`run_ingest` → 建项目 → 装配 → 跑 N 拍），和界面**同一批函数**；
  本工具的 `build`/`smoke` 是"拿 YAML 直接造设定集"，两者不能互相替代。
- 产物落在 `novel_bench/results/manual/<run-id>/`：`novel.md`（当天故事，用的是
  **和本工具同一套抽取逻辑**，所以字面指标可与基准产物横向比）、`transcript.md`、
  `summary.md`（推演小结）、`project/`。
- ⚠ **`metrics` / `judge` / `report` / `compare` 读不了这种产物**：它们要求
  `cases/<用例 id>/` 这一层，且 `id` 必须是数据集里有的（`cmd_metrics` 只遍历
  `run_dir/cases`）。想要打分，要么把这些素材**加进数据集**（§6 加新作品），
  要么只做人工对照 + 字面量（字数 / 4-gram 重复率 / 台词条数）。
- 它替你锁的开关与 `bench/runner.py` 的 `_FORCED` 一致（含 `SCRIPT_REVIEW_EVERY_TICKS=1`）——
  **两处必须一样**，否则"工具集跑出来的"和"真实项目跑出来的"不可比，而外面看不出来。
- `--resummarize <产物目录>` 只重写小结，不重跑、不花钱。
- 多例合并成一份报告：`developers/make_test_report.py <目录…> [--out 报告.md]`。

> ⚠ `--no-ingest` 对 `samples/` 与普通项目**通常不行**：那些素材的人物是自然语言 md
> （`设定/人物/<名>.md`），必须过一遍开卷才产出 `人物.yaml`，否则装配会报"设定集里没有人物"。

完整参数与耗时见主程序 `使用说明.md` 的 **5.8.4**。
