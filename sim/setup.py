# -*- coding: utf-8 -*-
"""世界装配（设计稿 §四）：把「一个运行文件夹」变成「一个能跑起来的世界」。

为什么单独一层
--------------
`RunLoop` 要五样东西才能跑：`WorldState` / `Agent[]` / `DirectorEngine` /
`DB` / `RunFolder`。可界面上手里只有一个运行文件夹，此前**没有任何代码**
把这两头连起来 —— 所以模拟循环一直没接进 GUI，运行界面的「暂停」「停止」
也就无处可挂。

把这段装配单独放这里，好处是：GUI、验证脚本、以后的命令行都调同一个函数。
否则三处各装各的，迟早装出三种不一样的世界。

装什么、从哪装
--------------
来源是运行文件夹的 `本地设定集/`（摄取时冻结的九件套）：

| 文件 | 装进 |
|---|---|
| `人物.yaml` | `WorldState.people`（→ 每个 `Agent`） |
| `世界观.md` | `WorldState.worldview_text` |
| `剧情走向.md` | 同上（剧情参考线，拼进总设定） |
| `顶级规则.md` | `WorldState.rules_text`（**原样进 prompt 最前面**，不做概括） |
| `故事进度.yaml` | `WorldState.progress_nodes` + `current_node` |
| `类型卡.yaml` / `风格卡.yaml` | `WorldState.genre_card` / `style_card` |
| `关系.yaml` / `伏笔与悬线.yaml` / `地点.yaml` | 汇总进 `worldview_text`（供 prompt 前缀） |
| `细节设定.yaml` | **细节层**素材（器物/习俗/小规矩）→ 分层索引（`world/layers.py`） |
| `小世界地图.yaml` | **三级底图**（`world/atlas.py` 的 `Atlas`）→ 天天地图从它取景 |

★ **分层设定**（2026-10-07）：装完之后 `world.layer_index` 是设定集的**分层投影**
（世界层 / 主线层 / 场景层 / 细节层，每条带生效时机·场合·影响谁·权重），
`world_prefix()` 按"今天 + 这个场合 + 在场的这些人"筛着用 —— 大背景平时只当
"气候"，细节层每天都出场。落盘 `分层设定.yaml` / `分层设定.md`（给人翻）。
剧组在推演中讨论出来的**局部设定**走 `world.local_settings`（另一条路，
**绝不并进设定集**），见 `world/layers.admit_new`。

**风格控制（虐心/幽默/爽点…）不在这里读**，它来自 `CFG`：
那是「这一轮怎么讲」的参数，属于「启动故事」对话框，不是冻结的设定。

坑：`世界观.md` / `剧情走向.md` 虽然是 `.md`，实际内容却是
`yaml.dump(字符串)` 写出来的（`'正文…\\n'` 带引号和转义）。
必须走 `yaml.safe_load`，直接 `read_text` 会读出引号。
而用户也可能把它手改成普通 markdown —— 所以两种都要认（见 `_read_text_setting`）。

English:
World assembly (design doc §4): turn "a run folder" into "a world that can run".
Why a separate layer
--------------
`RunLoop` needs five things to run: `WorldState` / `Agent[]` / `DirectorEngine` /
`DB` / `RunFolder`. But the UI only has a run folder in hand, and previously **no code**
connected these two ends -- so the simulation loop was never wired into the GUI, and the run
screen's "Pause" "Stop"
had nowhere to hook in.
Putting this assembly here separately has the benefit: GUI, validation scripts, and future CLI
all call the same function.
Otherwise three places each assemble their own, and sooner or later you get three different
worlds.
What to install, and from where
--------------
The source is the run folder's `本地设定集/` (the nine-piece set frozen at ingestion time):
| File | Installed into |
|---|---|
| `人物.yaml` | `WorldState.people` (→ each `Agent`) |
| `世界观.md` | `WorldState.worldview_text` |
| `剧情走向.md` | Same as above (plot reference line, concatenated into the overall setting) |
| `顶级规则.md` | `WorldState.rules_text` (**goes verbatim at the very front of the prompt**, no summarization) |
| `细节设定.yaml` | **Detail layer** material (objects/customs/small rules) → layered index (`world/layers.py`) |
| `小世界地图.yaml` | **Three-level base map** (`Atlas` in `world/atlas.py`) → the day-by-day map takes its framing from it |
★ **Layered settings** (2026-10-07): after loading, `world.layer_index` is a **layered
projection** of the setting set
(world layer / main-plot layer / scene layer / detail layer, each entry carrying activation
timing·occasion·who it affects·weight),
`world_prefix()` filters usage by "today + this occasion + these people present" -- the big
backdrop normally acts only as
**Local settings** discussed by the cast during simulation go through `world.local_settings` (a
separate path,
**never merged into the setting set**), see `world/layers.admit_new`.
**Style control (angst/humor/payoff...) is not read here**; it comes from `CFG`:
that is the parameter for "how to tell it this round", belonging to the "Start Story" dialog,
not frozen settings.
written by `yaml.dump(string)` (`'body...\\n'` with quotes and escapes).
Must go through `yaml.safe_load`; a direct `read_text` reads out the quotes.
And users may hand-edit it into plain markdown -- so both forms must be recognized (see
`_read_text_setting`).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from agent.core import Agent
from config import CFG
# 剧组（2026-10-07）：名册在装配时自查，缺人/断线在这里就说一声
# [EN] Crew (2026-10-07): the roster self-checks at assembly time; report missing people / broken lines
# [EN] here
from crew import roster as ROSTER
# 这里几条文案会**原样弹到界面上**（启动失败那一类），所以要走 t()
# [EN] Several strings here are **popped onto the UI as-is** (the startup-failure kind), so they must
# [EN] go through t()
from i18n import t
from util import outlang
from director.engine import DirectorEngine
from sim.loop import RunLoop
from store.db import DB
from util.timefmt import GameTime
from world.atlas import Atlas
from world.state import PersonState, WorldState

_LOG = __import__("logging").getLogger("nws.sim.setup")

# 设定集文件（摄取冻结产出的名字，见 ingest/pipeline.py 的 _freeze）
# [EN] Setting-collection file (the name produced by the frozen ingest step, see _freeze in
# [EN] ingest/pipeline.py)
F_CHARS = "人物.yaml"
F_WORLD = "世界观.md"
F_PLACES = "地点.yaml"
F_RELATIONS = "关系.yaml"
F_FORESHADOW = "伏笔与悬线.yaml"
F_PLOT = "剧情走向.md"
# ★ 顶级规则（2026-10-06）：作者写死的硬约束。由 `ingest/pipeline.collect_rules`
#   原文照录落盘（**不经 LLM 概括**），装配时单独取出来，进 prompt 的最前面。
# [EN] ★ Top-level rules (2026-10-06): hard constraints the author wrote down. Produced by
# [EN] `ingest/pipeline.collect_rules`
# [EN] Persisted verbatim from the source (**not summarized by an LLM**), pulled out separately at
# [EN] assembly time and put at the very front of the prompt.
F_RULES = "顶级规则.md"
#: **只给写作层**的约束（`style.notes`）：作家读，演员不读。
#: ⚠ 单独一份而不是塞进 `顶级规则.md`，因为后者会**原样进每个演员的提示词** ——
#:   而"每样最多复位三次"这种成品要求，演员在一拍里根本没法执行，只会让他不敢动。
# [EN] Constraints for the **writing layer only** (`style.notes`): the writer reads them, actors do not.
# [EN] ⚠ A separate file because `顶级规则.md` goes **verbatim into every actor prompt**, and
# [EN] "each prop resets at most three times" is not something an actor can execute in one beat --
# [EN] it only makes him avoid the prop.
F_WRITER_RULES = "写作层规则.md"
#: **给演员**的表演备注（`style.actor_notes`）：演员也读。
F_ACTOR_NOTES = "表演备注.md"
F_GENRE = "类型卡.yaml"
F_STYLE = "风格卡.yaml"
F_PROGRESS = "故事进度.yaml"
# ★ 2026-10-28：导入故事时由摄取对齐写下的「前情提要 + 上部结尾」——
#   推演第一章前情 / 起笔对话框 / 导出承接段三处共用的唯一事实来源。
# [EN] 2026-10-28: recap + previous-story tail written by ingest alignment --
# [EN] the single source shared by day-1 recap / start dialog / export continuation block.
F_RECAP = "前情提要.md"
F_MAP = "小世界地图.yaml"
# ★ 细节层（2026-10-07）：器物 / 习俗 / 口头禅 / 小规矩 —— **每天的故事多半由
#   这些小设定推动**（用户原话）。见 `world/layers.py` 的分层表。
# [EN] ★ Detail layer (2026-10-07): objects / customs / catchphrases / small rules —— **most of each
# [EN] day's story is driven
# [EN] by these small settings** (user's own words). See the layer table in `world/layers.py`.
F_DETAIL = "细节设定.yaml"

# 风格控制项（来自 CFG，不是设定集）
# [EN] Style control items (from CFG, not the setting collection)
_STYLE_FIELDS = (
    ("angst_level", "ANGST_LEVEL"),
    ("humor_level", "HUMOR_LEVEL"),
    ("satisfaction_density", "SATISFACTION_DENSITY"),
    ("romance_ratio", "ROMANCE_RATIO"),
    ("suspense_density", "SUSPENSE_DENSITY"),
    ("worldbuilding_pace", "WORLDBUILDING_PACE"),
    ("character_iq", "CHARACTER_IQ"),
)


class SetupError(RuntimeError):
    """装配失败（设定集缺失/为空）。界面上要把它转成一句人话提示。
        English:
    Assembly failure (setting set missing/empty). The UI must turn this into a human-readable
    message.
    """


# ══════════════════════════════════════════════════════════════
#  读
# [EN] Read
# ══════════════════════════════════════════════════════════════
def _read_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as e:                                  # noqa: BLE001
        _LOG.warning("读取 %s 失败: %s", path.name, e)
        return default
    return default if data is None else data


def _read_text_setting(path: Path, default: str = "") -> str:
    """读「其实是 YAML 字符串的 .md」（世界观 / 剧情走向）。

    两种形态都要认：
      · 摄取冻结的 `yaml.dump(字符串)` → 有引号和 `\\n` 转义，要走 YAML；
      · 用户手改成的普通 markdown → 就是原文，YAML 解析可能报错或解出非字符串。
    
        English:
    Read ".md that is actually a YAML string" (worldview / plot direction).
        Both forms must be recognized:
          · The ingestion-frozen `yaml.dump(string)` → has quotes and `\\n` escapes, must go through YAML;
          · User hand-edited plain markdown → just the raw text; YAML parsing may error or resolve to a non-string.
    """
    if not path.exists():
        return default
    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        data = yaml.safe_load(raw)
    except Exception:                                       # noqa: BLE001
        return raw.strip()
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, dict) and data:
        # 被手改成 `键: 值` 了 → 取值拼回去
        # [EN] Manually changed to `key: value` → parse the value back out
        return "\n".join(str(v) for v in data.values() if v is not None).strip()
    return raw.strip()


def _as_text_list(raw) -> list[str]:
    """把一个字段归一成**短字符串列表**（情节线 / 选项用）。

    作者手写 yaml 时会写成一串（"A；B；C"），AI 冻结出来的则是数组 —— 两种都要认。
    ⚠ 不做默认值、只做归一：没有就是空列表（推演行为与以前一致）。
    
        English:
    Normalise a field into a **list of short strings** (for beats / options). A hand-written yaml
    may hold one line ("A; B; C"), while the frozen output holds an array -- both are accepted.
    """
    if isinstance(raw, str):
        # ⚠ 与 `ingest/progress._text_list` 同一套分隔符（含斜杠：见那边的注释）
        # [EN] Same separator set as `ingest/progress._text_list` (slashes included; see the note there)
        raw = [x for x in re.split(r'[；;\n、/｜|]+', raw) if x.strip()]
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x).strip() for x in raw if str(x or '').strip()]


def _resolve_node_spans(nodes: list[dict]) -> list[dict]:
    """把节点缺的「跨度 / 篇幅」补齐（**只在内存里**，不写回作者的 yaml）。

    为什么在装配这一层补：`ingest.progress.resolve_span_weight` 是唯一实现，
    装配（打开/续跑每一卷都走）与生成两处都要用；在这里补一次，
    下游 `beat_budget_for` / `_carry_unplayed_beats` / 写作层的详略
    读到的是**同一份、已补齐**的表 —— 三处各推一次的写法必然漂。

    ⚠ 作者写了的**一个字都不动**（`resolve_span_weight` 内部保证），
      只把"哪几维是推的"记在 `推断` 上（人看得懂的说法，界面能显示）。
    ⚠ 失败不算错：推断只是优化，**不许因此开不了卷**。
    [EN] Fill in missing span/length **in memory only** (never written back to the author's yaml).
    [EN] Assembly runs on every open/resume, so filling here gives `beat_budget_for`,
    [EN] `_carry_unplayed_beats` and the writer's density **one** finished table -- three separate
    [EN] inference sites would inevitably drift. Author-written values are never touched; only
    [EN] "which dimensions were inferred" is recorded under a human-readable key.
    [EN] ⚠ Failure is not an error: inference is an optimisation and must never block opening a book.
    """
    if not nodes:
        return nodes
    try:
        from ingest.progress import ProgressNode, resolve_span_weight
        objs = [ProgressNode(id=str(n.get('id') or ''), name=str(n.get('名称') or ''),
                             summary=str(n.get('概要') or ''),
                             criteria=str(n.get('完成判据') or ''),
                             status=str(n.get('状态') or '未开始'),
                             span=str(n.get('跨度') or ''),
                             weight=str(n.get('篇幅') or ''))
                for n in nodes]
        for n, o in zip(nodes, resolve_span_weight(objs)):
            n['跨度'] = o.span
            n['篇幅'] = o.weight
            if o.inferred:
                names = {'span': '跨度', 'weight': '篇幅'}
                n['推断'] = '、'.join(names.get(x, x) for x in o.inferred) + '（程序推的，可改）'
    except Exception as e:                                   # noqa: BLE001
        _LOG.warning('进度节点的跨度/篇幅推断跳过（%s）—— 原表照用', e)
    return nodes


def load_settings(settings_dir: Path) -> dict:
    """把设定集目录读成一个统一的 dict（缺什么就是空，不抛）。
        English:
    Read the setting set directory into a unified dict (missing means empty, does not throw).
    """
    chars: list[dict] = []
    for p in (_read_yaml(settings_dir / F_CHARS, []) or []):
        if isinstance(p, dict):
            chars.append(p)
        elif isinstance(p, str):          # 手写成 `- 主角` 这种简写也要认
        # [EN] Hand-written shorthand like `- 主角` must also be recognized
            chars.append({"姓名": p})

    nodes: list[dict] = []
    raw_nodes = _read_yaml(settings_dir / F_PROGRESS, {}) or {}
    # ★ 2026-10-27：**书级篇幅规划**（总章数 / 总字数 / 每章字数）与节点表同处存放。
    #   ⚠ 它也必须**搬**（与 跨度/篇幅/章数 同一个坑的三个前例）。
    # [EN] ★ 2026-10-27: the **book-level length plan** sits next to the node table. ⚠ It too must be
    # [EN] carried across (the same trap already bit span/weight/chapters).
    length_plan: dict = {}
    if isinstance(raw_nodes, dict):
        _lp = raw_nodes.get("篇幅规划")
        if isinstance(_lp, dict):
            length_plan = _lp
        raw_nodes = raw_nodes.get("节点", [])
    for n in (raw_nodes or []):
        if not isinstance(n, dict):
            continue
        nodes.append({
            "id": str(n.get("id") or f"N{len(nodes) + 1:02d}"),
            "名称": str(n.get("名称") or ""),
            "概要": str(n.get("概要") or ""),
            "完成判据": str(n.get("完成判据") or ""),
            "状态": str(n.get("状态") or "未开始"),
            # ★★★ 2026-10-26：**这两个字段必须搬**。
            #   上一轮给 `ProgressNode` 加了「跨度 / 篇幅」并写进 yaml，却**漏搬了这一处**
            #   —— 于是运行时 `world.progress_nodes` 里根本没有这两个键：
            #     · `beat_budget_for` 每次现推（作者写的"篇幅:详"被无声忽略）；
            #     · `_carry_unplayed_beats` 读 `跨度` 永远空 ⇒ **跨天携带从来没生效过**；
            #     · 写作层按情节单元定详略也读不到（这一轮的新功能会静默退化成"全按中档"）。
            #   ⚠ 这正是本项目记过的"配置字段**漏搬**比没写更难发现"：yaml 里写了、
            #     代码里也有推断兜底 ⇒ 两条路都"能跑"，只是永远不是作者要的那一档。
            # [EN] ★★★ 2026-10-26: **these two fields must be carried over**. The previous round
            # [EN] added span/length to `ProgressNode` and to the yaml, but missed this loader:
            # [EN] `world.progress_nodes` simply had no such keys, so `beat_budget_for` always
            # [EN] inferred (the author's "length: thick" was silently ignored),
            # [EN] `_carry_unplayed_beats` always saw an empty span (**cross-day carry never once
            # [EN] fired**), and this round's per-station density could not read it either.
            # [EN] Exactly the documented trap: a **dropped** config field is harder to notice than
            # [EN] a missing one -- both paths still "run", just never at the author's tier.
            "跨度": str(n.get("跨度") or ""),
            "篇幅": str(n.get("篇幅") or ""),
            # ★ 2026-10-27：章数。**这一处必须搬**（与上面 跨度/篇幅 同一个坑：
            #   yaml 里写了、这里漏搬 ⇒ 运行时永远读不到 ⇒ 章数下限永远不生效，
            #   而 `min_chapters_for` 有按篇幅档的兜底 ⇒ **两条路都能跑、只是永远不生效**）。
            #   ⚠ 归一交给 `min_chapters_for`（它认 "3~4"、认不出给兜底），
            #     这里只做"原样搬运 + 转成 int"。
            # [EN] ★ 2026-10-27: the chapter count **must be carried here** (same trap as span/weight
            # [EN] above: present in the yaml, dropped by the loader => never visible at runtime, and
            # [EN] because `min_chapters_for` has a tier fallback, **both paths keep running** -- just
            # [EN] never at the author's number). Normalisation is `min_chapters_for`'s job.
            "章数": int(n.get("章数") or 0),
            # ★ 2026-10-27：**站内的台阶**（高潮 / 情节线 / 选项）也必须搬。
            #   ⚠ 与上面「跨度 / 篇幅 / 章数」是同一个坑的第五、六、七例：
            #   yaml 里写了、这里漏搬 ⇒ 运行时 `world.progress_nodes` 里根本没有这些键
            #   ⇒ 导演永远看不到"这一站还剩哪些事没演过"，而**两条路都能跑**
            #   （没有台阶时推演照旧），所以看不出是漏搬。
            #   ⚠ `情节线` 允许作者手写成一串（"A；B；C"），这里统一成列表。
            # [EN] ★ 2026-10-27: the station's **inner steps** (climax / beats / options) must be
            # [EN] carried too. ⚠ Same trap as span/weight/chapters above, cases five to seven:
            # [EN] present in the yaml, dropped by the loader => `world.progress_nodes` has no such
            # [EN] keys, so the director never sees "what is left to play in this station", and
            # [EN] **both paths still run** (without steps the run behaves as before), which is
            # [EN] exactly why a dropped field is invisible.
            "高潮": str(n.get("高潮") or ""),
            "情节线": _as_text_list(n.get("情节线")),
            "选项": _as_text_list(n.get("选项")),
            # 章纲（按站切好的章一级施工图）：推演时只喂当前站那几章。
            # [EN] Chapter plan (sliced per station): only the current station's chapters reach the run.
            "章纲": str(n.get("章纲") or ""),
        })
    nodes = _resolve_node_spans(nodes)

    return {
        "people": chars,
        "worldview": _read_text_setting(settings_dir / F_WORLD),
        "plot": _read_text_setting(settings_dir / F_PLOT),
        # ★ 2026-10-28：导入故事接续推演用的前情（含上部结尾）。
        #   ⚠ **必须搬**（"配置字段漏搬比没写更难发现"的第 N 例）：
        #     摄取写了这个文件、这里不读 ⇒ 前情永远进不了推演，
        #     "起点跟前情提要对不上"原样复发，而两条路都"能跑"看不出漏。
        # [EN] ★ 2026-10-28: the recap (with the previous story's tail) for continuing an imported
        # [EN] story. ⚠ **Must be carried here** (yet another case of "a dropped field is harder to
        # [EN] notice than a missing one"): ingest writes the file, if the loader skips it the recap
        # [EN] never reaches the run and the start-point mismatch recurs silently.
        "recap": _read_text_setting(settings_dir / F_RECAP),
        # 顶级规则（可能为空字符串 —— 大多数项目不写，写了就照原样进 prompt）
        # [EN] Top-level rules (may be an empty string —— most projects don't write them; if written, they go
        # [EN] into the prompt verbatim)
        "rules": _read_text_setting(settings_dir / F_RULES),
        "writer_rules": _read_text_setting(settings_dir / F_WRITER_RULES),
        "actor_notes": _read_text_setting(settings_dir / F_ACTOR_NOTES),
        "places": _read_yaml(settings_dir / F_PLACES, []) or [],
        "relations": _read_yaml(settings_dir / F_RELATIONS, []) or [],
        "foreshadows": _read_yaml(settings_dir / F_FORESHADOW, []) or [],
        "genre_card": _read_yaml(settings_dir / F_GENRE, {}) or {},
        "style_card": _read_yaml(settings_dir / F_STYLE, {}) or {},
        "nodes": nodes,
        "length_plan": length_plan,
        "map": _read_yaml(settings_dir / F_MAP, {}) or {},
        # 细节层素材（细节设定.yaml；没有这个文件的旧项目就是空表 —— 不抛）
        # [EN] Detail-layer material (细节设定.yaml; old projects without this file just get an empty table —— no
        # [EN] exception thrown)
        "detail": _read_yaml(settings_dir / F_DETAIL, []) or [],
    }


def _start_clock() -> GameTime:
    """起始时刻：`GAME_START_TIME` 空则从第 1 天 08:00 起。
        English:
    Start time: if `GAME_START_TIME` is empty, start from day 1 08:00.
    """
    raw = (CFG.s("GAME_START_TIME") or "").strip()
    if raw and ":" in raw:
        try:
            hh, mm = raw.split(":", 1)
            return GameTime(day=1, minutes=int(hh) * 60 + int(mm))
        except ValueError:
            pass
    return GameTime()


def worldview_text_of(settings: dict) -> str:
    """**公开名字**：`_worldview_text(settings)`（见下面那个实现）。

    ★ 为什么要公开（2026-10-11）：用户在「起笔」对话框里要看到**这一轮开头
      会念的那句前情提要**，而第一章的前情提要取的就是这段文本的
      `【剧情参考线】`/`【世界观】`（`director.day_plan.opening_context`）。
      对话框还没有 world（还没装配），只能自己从项目设定集算一遍 ——
      **必须走同一个函数**，走两条路迟早"对话框说的"和"实际念的"不一样
      （那正是用户点名要避免的："请确保这里的前情提要和后续运行窗口……一样"）。
    
        English:
    **Public name**: `_worldview_text(settings)` (see the implementation below).
        ★ Why make it public (2026-10-11): in the "Start Writing" dialog the user needs to see **the recap
          that will be read at the start of this round**, and the first chapter's recap is taken from this text's
          The dialog has no world yet (not assembled), so it can only compute it itself from the project setting set --
          **must go through the same function**; two paths will sooner or later make "what the dialog says" and "what is actually read" differ
          (which is exactly what the user called out to avoid: "please ensure the recap here and the subsequent run window... are the same").
    """
    return _worldview_text(settings)


def _plot_setup_only(plot: str) -> str:
    """把「剧情参考线」**砍到只剩「起」段**（到「承」之前）再进提示词前缀。

    ★★★ 2026-10-14（用户）：「推演感觉故事线推进的特别快 …… 第一天就想把谜底解开，
    这个节奏是不对的」。
    实据：某一轮**当天就把 N01 判完成**，复盘自己写着"坐实重走前世环线、
    点出前世旧债、七世债缘线索前移"（那是 N02/N03 的内容）。
    根因之一就在这一行 —— 原来是把**整条**剧情走向当 Agent 提示词前缀：

        起：主角白日醒在楼前、失忆入伙。承：茶楼日常夜客讲究，掌柜半语。
        转：遇白衣碎片、旁人旧疤、干支账异。合：主角直面七世前世，护楼取舍。

    「转/合」那两个分句**把谜底和结局都写明了**，而这段文本是**每个 Agent 的
    前缀**、从第 1 天起就带着 ⇒ 模型当然直奔结局。

    ⇒ 只放「起」段（"失忆入伙"这种**开局状态**），后面的弧线不进日常提示词。
    ⚠ 口径必须与 `director/day_plan._opening_context` 里那段**一致**
      （那边是从带 `【剧情参考线】` 标记的整段文本里取「起」，砍的也是
      `承/转/合` 三个字）—— 两处各写一份迟早漂，`verify_context.py`
      有一条判据同时钉两边。
    ⚠ 找不到任何标记（用户就写了一句话、没分起承转合）→ **原样返回**：
      那种写法里没写弧线，没有可砍的东西，硬砍反而会丢信息。
    [EN] Trim the "story reference line" **down to just the "setup" part** (before "development")
    before it goes into the prompt prefix.
    [EN] ★★★ 2026-10-14 (user): "the simulation feels way too fast ... it wants to crack the mystery on
    [EN] day one; that pacing is wrong." Evidence: one run had N01 marked complete **the same
    [EN] day**, and the retrospective itself said "confirmed the tower re-walks the past cycle, pointed
    [EN] at the past-life debt, moved the seven-lives thread forward" (that is N02/N03 material). One root
    [EN] cause is right here -- the **whole** story line used to be the Agent prompt prefix.
    [EN] The "turn" and "resolution" clauses **state the mystery and the ending outright**, and this text
    [EN] is **every Agent's prefix**, carried from day 1 => the model naturally races to the ending.
    [EN] => Keep only the "setup" clause (the *opening state*, e.g. "wakes with amnesia and joins"),
    [EN] and keep the later arc out of day-to-day prompts.
    [EN] ⚠ Must stay **consistent** with the block in `director/day_plan._opening_context` (that one takes
    [EN] the "setup" from the marker-wrapped text and cuts at the same three characters). Two copies drift
    [EN] eventually; `verify_context.py` has a check pinning both sides.
    [EN] ⚠ No markers at all (the user wrote one sentence with no 起/承/转/合) -> **return as-is**: no arc
    [EN] was written there, nothing to cut, and cutting anyway would lose information.
    """
    text = ' '.join(str(plot or '').split()).strip()
    if not text:
        return ''
    cut = len(text)
    for mark in ('承', '转', '合'):
        k = text.find(mark)
        if k > 0:
            cut = min(cut, k)
    if cut >= len(text):
        return text                      # 没有任何弧线标记 → 原样
    head = text[:cut].strip(' 　，。；、·—-.')
    head = head.lstrip('起：: 　')
    # 砍完太短（比如只写了"起："）→ 原样返回，别把设定清空
    # [EN] Cut result too short (e.g. only "setup:" was written) -> return as-is rather than blanking it
    return head if len(head) >= 8 else text


def _worldview_text(settings: dict) -> str:
    """把散着的设定拼成一段总世界观（Agent 的 prompt 前缀用）。
        English:
    Concatenate the scattered settings into one overall worldview (used as the Agent's prompt
    prefix).
    """
    parts: list[str] = []
    # ★ 2026-10-28：前情提要**排第一** —— 接续导入故事推演时，
    #   "故事停在哪"比"大纲从哪起头"更要紧（作者视角：这是第 N 部了）。
    # [EN] ★ 2026-10-28: recap **goes first** -- when continuing an imported story, "where the story
    # [EN] stopped" outranks "where the outline starts".
    if settings.get("recap"):
        parts.append(f"【前情提要】\n{settings['recap']}")
    if settings["worldview"]:
        parts.append(f"【世界观】\n{settings['worldview']}")
    if settings["plot"]:
        parts.append(f"【剧情参考线】\n{_plot_setup_only(settings['plot'])}")

    places = [str(p.get("名称", "")) for p in settings["places"]
              if isinstance(p, dict) and p.get("名称")]
    if places:
        parts.append("【地点】" + "、".join(places))

    rels = []
    for r in settings["relations"]:
        if isinstance(r, dict) and (r.get("甲") or r.get("乙")):
            rels.append(f"{r.get('甲', '')}—{r.get('乙', '')}：{r.get('关系', '')}")
    if rels:
        parts.append("【人物关系】" + "；".join(rels))

    hooks = []
    for f in settings["foreshadows"]:
        if isinstance(f, dict) and f.get("内容"):
            hooks.append(f"[{f.get('编号', 'F?')}] {f.get('内容')}")
    if hooks:
        parts.append("【伏笔与悬线】" + "；".join(hooks))

    return "\n\n".join(parts)


_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _parse_debut(raw: Any) -> int:
    """解析人物卡里的可选字段「登场」，返回"第几个故事日登场"。

    认这几种写法：`第3天` / `3` / `三天` / `未登场`（= 999，等于先不放出来）。
    ⚠ **认不出就当第 1 天，不猜。** 猜错的代价不对称：
      · 猜晚 → 该出场的人不出场，故事直接跑偏；
      · 猜早 → 只是"多一个不该在的人在场"，比前者好查得多。
    节点编号（`K09`）会被当成**第 9 天**（数字部分就当日数）—— 这是有意的近似：
    写 `K09` 的作者想说的本来就是"中期以后"，而"节点→故事日"的映射表我们没有。
    作者要让某人后段才出场，写「未登场」，等该放的时候再改设定重开一轮。
    
        English:
    Parse the optional field "登场" (debut) in a character card, returning "on which story day they
    debut".
        ⚠ **If unrecognizable, treat as day 1, do not guess.** The cost of guessing wrong is asymmetric:
          · Guess late → the person who should appear doesn't, and the story goes off the rails;
          · Guess early → merely "one extra person present who shouldn't be", far easier to catch than the former.
        A node number (`K09`) is treated as **day 9** (the numeric part counts as the day count) -- this is a deliberate approximation:
        an author who writes `K09` means "mid-game or later" anyway, and we don't have a "node→story day" mapping table.
        If an author wants someone to appear only in a later phase, write 「未登场」, and when it's time to release them, change the setting and restart a round.
    """
    s = str(raw or "").strip()
    if not s:
        return 1
    if any(k in s for k in ("未登场", "后期", "后段", "终局", "结局")):
        return 999
    m = re.search(r"(\d+)", s)
    if m:
        return max(1, int(m.group(1)))
    for ch, n in _CN_NUM.items():
        if ch in s:
            return n
    return 1


# ══════════════════════════════════════════════════════════════
#  装
# [EN] Assemble
# ══════════════════════════════════════════════════════════════
def _apply_round_cast(world) -> None:
    """把 `ROUND_CAST` 落到 `world.round_cast` 上（**必须跟本书人物表核对**）。

    单独一个函数是为了让它**在人物建完之后**才跑 —— 放在 `build_world` 中间
    （人物循环之前）的话 `world.people` 还是空的，名单会被整体判成"对不上"，
    而那正是最坏的结局（没人上场）。
    
        English:
    Assign `ROUND_CAST` to `world.round_cast` (**must be reconciled with this book's character
    table**).
        A separate function is used so it only runs **after the characters are built** -- if placed in the middle of `build_world`
        (before the character loop), then `world.people` would still be empty, and the roster would be judged as "mismatched" as a whole,
        and that is precisely the worst outcome (nobody takes the stage).
    """
    want = [x.strip() for x in str(CFG.s("ROUND_CAST") or "").split(',')
            if x.strip()]
    if not want:
        return
    known = set(getattr(world, "people", None) or {})
    hit = [n for n in want if n in known]
    miss = [n for n in want if n not in known]
    if miss:
        _LOG.warning("本轮出场名单里有 %d 个名字不在本书人物表里（已忽略）：%s"
                     "（照实的名字是：%s）",
                     len(miss), "、".join(miss),
                     "、".join(list(known)[:8]) or "（这本没有人物）")
    if hit:
        world.round_cast = hit
        _LOG.info("本轮出场名单：%s（其余人这轮不上场）", "、".join(hit))
    else:
        _LOG.warning("本轮出场名单一个都没对上，按「全体上场」跑")


def build_world(settings: dict, *, front_max: int | None = None,
                scene: str = "", style_source: str = "",
                style_custom: str = "",
                start_clock: Any | None = None,
                user_directive: str = "") -> WorldState:
    """按设定集建 `WorldState`（人物 + 进度 + 风格控制 + 总世界观）。

    `scene` = **本轮开场地点**，来自项目文件（书斋 · 类型与风格里的「场景名称」）。
    优先级：项目值 > 全局 `.env`(SCENE_NAME) > 设定里的第一个地点 > "默认场景"。
    项目值走参数而不是 `CFG.set()` —— 写进 CFG 会在下一次 `CFG.save()`
    时**漏进全局 `.env`**，别的项目就跟着变了。

    `user_directive` = **作者对本轮走向的建议**（2026-10-11，`sim/directive.py`）——
      他在「起笔」对话框里填的那一栏。挂到 `world.user_directive`，
      由 `crew/agents.craft_block()` 拼进每个人的提示词。空串 = 他没填
      （那就**一个字都不加**，逐字退回老行为）。
      与 `scene=` 同一个道理走参数：**不进 CFG**，否则会漏进全局 `.env` 与下一轮。
    
        English:
    Build `WorldState` from the settings collection (characters + progress + style control + overall
    worldbuilding).
        `scene` = **the opening location for this round**, comes from the project file (the "scene name" in 书斋 · 类型与风格).
        Priority: project value > global `.env`(SCENE_NAME) > the first location in the settings > "default scene".
        The project value goes through a parameter rather than `CFG.set()` -- writing it into CFG would, on the next `CFG.save()`,
        **leak into the global `.env`**, and other projects would change along with it.
        `user_directive` = **the author's suggestion for this round's direction** (2026-10-11, `sim/directive.py`) --
          the field they filled in the "起笔" dialog. Attached to `world.user_directive`,
          and `crew/agents.craft_block()` splices it into each person's prompt. Empty string = they didn't fill it
          (then **not a single word is added**, falling back verbatim to the old behavior).
          Same reasoning as `scene=`, it goes through a parameter: **it does not go into CFG**, otherwise it would leak into the global `.env` and the next round.
    """
    scene_names = [str(p.get("名称", "")) for p in settings["places"]
                   if isinstance(p, dict) and p.get("名称")]
    picked = (scene or "").strip()
    if not picked or picked == "auto":
        picked = (CFG.s("SCENE_NAME") or "").strip()
    world = WorldState(
        # ★ `start_clock` = **这一轮从哪天几点起**（2026-10-08）。
        #   续跑时由「起笔」按上一轮的**停点**算好传进来
        # [EN] ★ `start_clock` = **which day and what time this round starts from** (2026-10-08).
        # [EN] On a continuation run, the "起笔" computes it from the previous round's **stop point** and passes
        # [EN] it in
        #   （`sim/resume.plan()` → `start_clock_of()`）；
        #   不给就还是老规矩（`GAME_START_TIME`，默认第 1 天 08:00）。
        # [EN] If not given, the old rule applies (`GAME_START_TIME`, default day 1 08:00).
        clock=(start_clock if start_clock is not None else _start_clock()),
        calendar=CFG.s("CALENDAR_DISPLAY") or "auto",
        weather="晴",
        scene=(picked if picked not in ("", "auto")
               else (scene_names[0] if scene_names else "默认场景")),
        scene_desc="",
        worldview_text=_worldview_text(settings),
        rules_text=str(settings.get("rules") or ""),
        # ★ 2026-10-21：写作层规则与表演备注**分两个字段**（见 `F_WRITER_RULES` 的说明）。
        #   `writer_notes` 只被作家读（`SetCtx.world_brief` 拼进去），
        #   `actor_notes` 被 `world_prefix_stable` 拼进演员前缀。
        writer_notes=str(settings.get("writer_rules") or ""),
        actor_notes=str(settings.get("actor_notes") or ""),
        genre_card=settings["genre_card"] if isinstance(settings["genre_card"], dict) else {},
        style_card=settings["style_card"] if isinstance(settings["style_card"], dict) else {},
        progress_nodes=[dict(n) for n in settings["nodes"]],
        # ★ 风格来源 / 自定义风格 / 本幕提示（2026-10-06 接）——
        #   优先级：**项目值 > 全局 `.env`**。项目值走参数而不是 `CFG.set()`：
        #   写进 CFG 会在下一次 `CFG.save()` 时漏进全局 `.env`，别的项目跟着变
        #   （`scene=` 那条注释说的就是这个坑，这里是同一个道理）。
        # [EN] ★ Style source / custom style / this-scene hint (added 2026-10-06) ——
        # [EN] Priority: **project value > global `.env`**. Project values go through parameters rather than
        # [EN] `CFG.set()`:
        # [EN] Writing into CFG would leak into the global `.env` on the next `CFG.save()`, and other projects
        # [EN] would change along with it
        # [EN] (the comment on the `scene=` line is about this same pitfall; here it's the same reasoning).
        style_source=(str(style_source or "").strip()
                      or (CFG.s("NOVEL_STYLE") or "auto")),
        style_custom=str(style_custom or "").strip()
        or (CFG.s("NOVEL_STYLE_CUSTOM") or ""),
        scene_hint=(CFG.s("SCENE_START_HINT") or ""),
    )

    # ★ 地点表（结构化留一份）。
    #   2026-10-06 补：以前「地点」只以 `【地点】A、B` 那句话的形式活在
    #   `worldview_text` 里 —— 是给人看的，程序手上**没有**一份能查的表，
    #   于是"换场"这件事根本无从判断（`world.scene` 永远不会变）。
    #   挂在实例上而不是加 dataclass 字段：WorldState 有存盘序列化，
    #   加字段要连带改 schema，不值得 —— 这份表只是运行期的判据。
    # [EN] ★ Location table (keep a structured copy).
    # [EN] Added 2026-10-06: previously "locations" only existed in the form of the sentence `【地点】A、B`
    # [EN] inside `worldview_text` —— that's for humans; the program had **no** queryable table on hand,
    # [EN] so the very act of "changing scene" couldn't be judged at all (`world.scene` would never
    # [EN] change).
    # [EN] Attached to the instance rather than adding a dataclass field: WorldState is saved and
    # [EN] serialized,
    # [EN] adding a field would require changing the schema too, not worth it —— this table is only a
    # [EN] runtime criterion.
    world.place_names = list(scene_names)
    # ★ 关系表（结构化留一份）：开场要写"这个人跟主角/跟这楼是什么关系"，
    #   以前关系只以一句话的形式活在 `worldview_text` 里，程序手上没有可查的表。
    #   同样挂实例（不进 dataclass schema，避免牵动存盘格式）。
    # [EN] ★ Relationship table (keep a structured copy): the opening needs to write "what relation this
    # [EN] person has to the protagonist / to this building",
    # [EN] previously relationships only existed as a sentence inside `worldview_text`; the program had no
    # [EN] queryable table on hand.
    # [EN] Likewise attached to the instance (does not go into the dataclass schema, avoiding disturbing
    # [EN] the save format).
    world.relations = [r for r in (settings.get("relations") or [])
                       if isinstance(r, dict)]

    # 风格控制：来自 CFG（本轮设置），不是设定集
    # [EN] Style control: from CFG (this round's settings), not the setting collection
    for attr, key in _STYLE_FIELDS:
        try:
            setattr(world, attr, CFG.f(key))
        except Exception:                                   # noqa: BLE001
            pass
    world.pacing_style = CFG.s("PACING_STYLE") or "medium"

    # ★★ **本轮推演三样**（2026-10-11，用户在「起笔」里点名要控制的）──────
    # [EN] ★★ **Three things inferred this round** (2026-10-11, the user named them for control in "起笔")
    # [EN] ──────
    #
    # 与上面那段风格控制一样**读 CFG**（同一个对话框里的「运行边界 / 风格控制」
    # 也是这么读的）—— 所以"下次起笔它们还在"，对话框里看得见当前值。
    # [EN] is read the same way) —— so "they'll still be there on the next 起笔", and the current values are
    # [EN] visible in the dialog.
    #
    # ⚠ 其中两样写的是**这本书里的名字**（人名 / 地名），必须**跟本书核对**：
    #   换一本书之后，上一本书的名字多半对不上 —— 不核对就会出两件很坏的事：
    #     · `ROUND_CAST` 全对不上 ⇒ `is_on_stage` 恒假 ⇒ **整轮没有一个人上场**；
    #     · `ROUND_SCENE` 是个不存在的地名 ⇒ 场景名挂在半空。
    #   所以**认不出来的丢掉并说一句**（不是静默照用、也不是静默清空）。
    # [EN] ⚠ Two of them are written as **names from this book** (person names / place names) and must be
    # [EN] **checked against this book**:
    # [EN] After switching books, the previous book's names mostly won't match —— skipping the check causes
    # [EN] two very bad things:
    # [EN] · `ROUND_CAST` all mismatch ⇒ `is_on_stage` is always false ⇒ **no one is on stage the entire
    # [EN] round**;
    # [EN] · `ROUND_SCENE` is a nonexistent place name ⇒ the scene name hangs in midair.
    # [EN] So **drop anything unrecognized and say a word about it** (not silently use it, nor silently
    # [EN] clear it).
    try:
        world.daily_words = max(0, int(CFG.i("ROUND_DAILY_WORDS") or 0))
    except Exception:                                        # noqa: BLE001
        world.daily_words = 0
    # ★★★ 2026-10-27：**设定集里写了篇幅规划时，它比全局配置更靠前**。
    #   作者在大纲里写「总章数 32 / 总字数 7.5万」—— 那是**这本书**的口径；
    #   `ROUND_DAILY_WORDS` 是**全局**配置（换本书还留着，见 `scene=` 那条注释的坑）。
    #   所以顺序是：作者在「起笔」里手填的 > 设定集里这本书写的 > 全局默认（0 = 不限）。
    #   ⚠ 反过来会出事：全局值压住项目值 ⇒ 作者写完大纲发现字数完全对不上。
    # [EN] ★★★ 2026-10-27: **a length plan in the setting collection outranks the global config**.
    # [EN] "32 chapters / 75,000 words" in the outline is **this book's** measure, while
    # [EN] `ROUND_DAILY_WORDS` is **global** (it survives a book switch -- the trap described in the
    # [EN] `scene=` comment). So: hand-filled in "起笔" > this book's setting collection > global.
    # [EN] ⚠ The reverse breaks things: a global value overriding the project value means the author
    # [EN] writes an outline and then the word count doesn't match at all.
    if not world.daily_words:
        try:
            from ingest.progress import words_per_chapter
            _wpc = words_per_chapter(settings.get("length_plan"))
        except Exception:                                    # noqa: BLE001
            _wpc = 0
        if _wpc > 0:
            world.daily_words = _wpc
            _LOG.info("篇幅规划：设定集写了篇幅规划 ⇒ 每天目标 %d 字（总字数 ÷ 总章数，"
                      "或作者直接写的每章字数）", _wpc)

    # ⚠ **出场名单不在这里核** —— 这一刻 `world.people` 还是空的（人物在下面
    #   那个循环里才建出来）。核名单要等人建完，见 `_apply_round_cast`。
    # [EN] ⚠ **The cast list is not checked here** —— at this moment `world.people` is still empty
    # [EN] (characters are created in the loop
    # [EN] below). Checking the roster must wait until the people are created, see `_apply_round_cast`.

    _want_scene = str(CFG.s("ROUND_SCENE") or "").strip()
    if _want_scene:
        if _want_scene in {str(x).strip() for x in (scene_names or [])}:
            world.scene = _want_scene
            world.scene_locked = True
            _LOG.info("本轮锁定场景：%s（不发生换场）", _want_scene)
        else:
            _LOG.warning("本轮锁定的场景「%s」不在本书地点表里，忽略（照常换场）",
                         _want_scene)


    # ★★ **作者对本轮走向的建议**（2026-10-11，`sim/directive.py`）——
    #   同样是"本轮设置"，但**走参数不走 CFG**（见函数说明）：
    #   它是这一轮的内容，进 `.env` 就会在下一轮 / 别的项目里**静默复活**。
    # [EN] ★★ **The author's suggestion for this round's direction** (2026-10-11, `sim/directive.py`) ——
    # [EN] It's likewise a "this round setting", but **goes through parameters rather than CFG** (see the
    # [EN] function doc):
    # [EN] it's content of this round; entering `.env` would make it **silently resurrect** in the next
    # [EN] round / other projects.
    try:
        from sim import directive as _DIR
        _DIR.attach(world, user_directive)
    except Exception as e:                                  # noqa: BLE001
        _LOG.warning('作者走向建议没挂上（这一轮按没有建议跑）：%r', e)

    # 人物：前 AGENT_MAX 个上前台，其余挂后台（后台走批量摘要，不逐个决策）
    # [EN] Characters: the first AGENT_MAX go to the foreground, the rest hang in the background
    # [EN] (background goes through batch summarization, not per-character decisions)
    limit = front_max if front_max is not None else CFG.i("AGENT_MAX")
    # ★★ **选角**（2026-10-07，见 `actors/casting.py`）——
    #   装配的这一刻给每个人配一个**演员类型**（+ 同型多人的变奏轴）。
    #   为什么在这里做、而不是演员第一次决策时现配：类型是**这一轮固定**的
    #   （一个类型演一百本书都这样），而且同型分流要靠"谁先领走"的顺序 ——
    #   放在决策里做会随执行顺序漂移（今天他是第二种冷，明天可能是第一种）。
    #   配不到就落默认型并**照实标注**（`cast_matched=False`）。
    # [EN] ★★ **Casting** (2026-10-07, see `actors/casting.py`) ——
    # [EN] At this moment of assembly, give each person an **actor type** (+ a variation axis for multiple
    # [EN] people of the same type).
    # [EN] Why do it here rather than assigning on the actor's first decision: the type is **fixed for this
    # [EN] round**
    # [EN] (one type plays a hundred books the same way), and same-type splitting depends on the order of
    # [EN] "who claims it first" ——
    # [EN] doing it inside decisions would drift with execution order (today he's the second kind of cold,
    # [EN] tomorrow maybe the first).
    # [EN] If no match, fall back to the default type and **annotate it truthfully**
    # [EN] (`cast_matched=False`).
    _casts: dict[str, object] = {}
    _cast_list: list = []
    try:
        from actors import casting as CASTING
        _cards = [p for p in settings["people"] if isinstance(p, dict)]
        _cast_list = CASTING.cast_all(_cards)
        for _c in _cast_list:
            _casts[_c.name] = _c
        _n_def = sum(1 for _c in _cast_list if not _c.matched)
        if _n_def:
            _LOG.info("选角：%d 位没能在人物卡里配对，用了默认类型（在人物卡里写"
                      "一行 `演员类型: 青年·毒舌` 可指定，或写 `性格:` 让它自己配）",
                      _n_def)
        # ⚠ 把选角结果**原样挂在 world 上**，给 `assemble` 落「选角表.md」用。
        #   为什么不让它按 `world.people` 重新 instantiate 一遍：那样"配上的"
        #   会被说成"点名的"（因为 `ps.archetype` 此时已经有值了），
        #   于是表上写着"人物卡命中"，而实际上这一位是**兜底**来的 ——
        #   那是"把兜的说成配的"，本项目对这件事零容忍。
        # [EN] ⚠ Attach the casting result **to world as-is**, for `assemble` to write "选角表.md".
        # [EN] Why not let it re-instantiate from `world.people`: that way the "matched" ones
        # [EN] would be described as "named" ones (because `ps.archetype` already has a value at this point),
        # [EN] so the table would say "character card hit" while in fact this one came from the **fallback** ——
        # [EN] that's "calling a fallback a match", and this project has zero tolerance for that.
        world._casts = _cast_list                                    # noqa: SLF001
    except Exception as e:                                          # noqa: BLE001
        _LOG.warning("选角这一步没跑成（演员照常演，只是没有类型预设）：%r", e)
    for idx, p in enumerate(settings["people"]):
        name = str(p.get("姓名") or p.get("name") or "").strip()
        if not name or name in world.people:
            continue
        # ★ 「登场」（2026-10-06）：写了「第3天 / 未登场」的人**一开始不在场**。
        #   真机日志里「连终局才登场的角色都 126 次在场」的根因就是没有这个概念 ——
        #   场景没有边界，谁也不必对"此刻谁在这儿"负责（秘密因此形同公开）。
        # [EN] ★ "Debut" (2026-10-06): people marked "day 3 / not yet debuted" are **not on stage at the
        # [EN] start**.
        # [EN] The root cause of "characters who only debut at the finale were on stage 126 times" in real logs
        # [EN] is the absence of this concept ——
        # [EN] scenes had no boundary, no one was responsible for "who is here right now" (and so secrets were
        # [EN] effectively public).
        debut = _parse_debut(p.get("登场") or p.get("debut") or "")
        _cast = _casts.get(name)
        world.people[name] = PersonState(
            name=name,
            identity=str(p.get("身份") or p.get("简介") or ""),
            personality=str(p.get("性格") or ""),
            catchphrase=str(p.get("口癖") or ""),
            # ★★★ 2026-10-28：**说话指纹**（句长 / 嘴上的抓手 / 心虚时的小动作 / 称呼差）。
            #   只认作者写在人物卡里的那一栏 —— **没写就是空**，不许从"性格"里推
            #   （推出来的那一份会跟别人撞成一个味，正是要修的那个病）。
            # [EN] ★★★ 2026-10-28: **speech fingerprint**. Only what the author wrote in the card;
            # [EN] empty when absent -- never inferred from "personality" (an inferred one collides
            # [EN] with everyone else's, which is exactly the disease being fixed).
            speech_fp=str(p.get("说话指纹") or p.get("speech_fp") or ""),
            secret=str(p.get("秘密") or ""),
            # ★★★ 2026-10-18：**这条秘密谁知情**（`知情者: 甲、乙`）。
            #   不写 = 只有他自己知道 —— 那是默认，也是最常见的写法。
            #   它决定"别人能不能说出这条秘密"（说出来就是越界，见 `WorldState.leaks`）。
            # [EN] ★★★ 2026-10-18: **who knows this secret** (`knowers: A, B`). Omitted = only he
            # [EN] knows, the default and the usual case. It decides whether others may state it
            # [EN] (stating it is out of bounds; see `WorldState.leaks`).
            knows=[x.strip() for x in str(
                p.get("知情者") or p.get("knowers") or "").replace('，', '、')
                .replace(',', '、').split('、') if x.strip()],
            goal=str(p.get("目标") or ""),
            # ★★★ 2026-10-18：**他真正缺的东西**（专业论述 #4 欲望 vs 需求，Truby）。
            #   与 `goal` 是两个字段、两件事：`目标` 是他说得出口的，`需求` 是他缺的。
            #   ⚠ 不写就是空串 ⇒ 这一维不参与（不编）—— 缺口 #4 的落点在这里。
            # [EN] ★★★ 2026-10-18: **what he actually lacks** (#4 want vs need, Truby). `目标` is what
            # [EN] he can say out loud; `需求` is what he lacks. ⚠ Omitted = empty = this dimension is
            # [EN] not in play (never invented).
            need=str(p.get("需求") or p.get("need") or ""),
            redline=str(p.get("红线") or ""),
            archetype=str(getattr(_cast, "archetype", "") or ""),
            variant=str(getattr(_cast, "variant", "") or ""),
            casting_note=str(getattr(_cast, "casting", "") or ""),
            break_type=str(getattr(_cast, "break_type", "") or ""),
            cast_matched=bool(getattr(_cast, "matched", True)),
            location=world.scene,
            status=("未登场" if debut > 1 else "在场"),
            role="前台" if idx < max(1, limit) else "后台",
            debut_day=debut,
            met=(debut <= 1),
        )

    # ★★ **本轮出场名单**（2026-10-11）—— 必须等人建完再核。
    # [EN] ★★ **This round's cast list** (2026-10-11) —— must wait until the people are created before
    # [EN] checking.
    #
    # 用户：「起笔时可以控制……本轮出场人物」。名单是**人写的**（逗号分隔的人名），
    # 而 `is_on_stage` 认的是**这本书人物表里的名字** —— 所以这里要对一遍：
    #   · 认不出来的**丢掉并说一句**（换一本书之后，上一本的名字多半对不上）；
    #   · 全都没对上 ⇒ **当没设**（照常全体上场）。
    #     ⚠ 这一条最要紧：照用的话 `is_on_stage` 恒假 ⇒ **整轮没有一个人上场**，
    #       而现象是"它一句话都不说"（最难往"名单写错了"上面想）。
    # [EN] User: "at 起笔 you can control ... this round's cast". The list is **hand-written**
    # [EN] (comma-separated person names),
    # [EN] and `is_on_stage` recognizes **names from this book's character table** —— so check it here:
    # [EN] · **drop unrecognized ones and say a word about it** (after switching books, the previous book's
    # [EN] names mostly won't match);
    # [EN] · if none match ⇒ **treat as unset** (everyone goes on stage as usual).
    # [EN] ⚠ This one matters most: using it as-is makes `is_on_stage` always false ⇒ **no one is on stage
    # [EN] the entire round**,
    # [EN] and the symptom is "it doesn't say a single word" (the hardest thing to trace back to "the list
    # [EN] was written wrong").
    _apply_round_cast(world)

    # ★★★ 2026-10-21（用户：「进度表一直不动 …… 按照第一个方向执行（拆判据）」）：
    #   **装配时把"一站捆好几件事"的判据拆开，一站一件事**（`world/progress_split.py`）。
    #
    #   为什么放在这里（而不是只改生成提示词）：生成只发生在**开卷**那一次，
    #   而存量项目的 `故事进度.yaml` 早就写好了 —— 只改生成侧等于**只对新项目生效**，
    #   用户手上这个卡住的项目一个字都不会变。装配是每次开卷/续跑的必经之路，放在这里
    #   所有存量项目自动受益。
    #
    #   ⚠ 只在**内存里**拆，**不写回** yaml：那是作者的设定集，产品不该悄悄改它。
    #   ⚠ 必须在下面那句 `current_node = progress_nodes[0]` **之前**：拆开后节点重排了 id，
    #     先指再拆会把 `current_node` 指到一个已经不存在/含义变了的 id 上。
    #   ⚠ 必须在 `_apply_round_cast` **之后**：那一支可能整表换人（见它的说明），
    #     先拆再换等于白拆。
    # [EN] ★★★ 2026-10-21 (user: "the progress table never moves ... take the first direction
    # [EN] (split the criteria)"): **at assembly time, split nodes whose criterion packs several
    # [EN] tasks into one station** (`world/progress_split.py`), one station per task.
    # [EN] Why here rather than only fixing the generation prompt: generation happens **when opening a
    # [EN] book**, and existing projects' `故事进度.yaml` was written long ago -- changing only the
    # [EN] generation side means **new projects only**, and the project the user is stuck on would not
    # [EN] change by a single character. Assembly is on the path of every open/resume, so every
    # [EN] existing project benefits automatically.
    # [EN] ⚠ Splitting is **in memory only** and **never written back** to the yaml: that file is the
    # [EN] author's setting document and the product must not silently edit it.
    # [EN] ⚠ Must run **before** `current_node = progress_nodes[0]` below: splitting renumbers ids, and
    # [EN] pointing first would leave `current_node` on an id that no longer exists or has changed
    # [EN] meaning.
    # [EN] ⚠ Must run **after** `_apply_round_cast`: that branch may swap the whole table, and
    # [EN] splitting before it would be wasted work.
    if world.progress_nodes:
        try:
            from world import progress_split as _PS
            _split, _made = _PS.split_fat_nodes(world.progress_nodes, log=_LOG.info)
            if _made:
                world.progress_nodes = _split
                _LOG.info('进度表已细化：一站一件事（多出 %d 站，共 %d 站）',
                          _made, len(_split))
        except Exception as _e:                              # noqa: BLE001
            # 拆不开不算错：原表照用。**别让"优化"变成"开不了卷"**。
            # [EN] Failing to split is not an error: use the original table. **An optimization must
            # [EN] never prevent opening the book.**
            _LOG.warning('进度节点拆分跳过（%s）—— 原表照用', _e)

    if world.progress_nodes:
        world.current_node = str(world.progress_nodes[0].get("id") or "N01")
        # ★★★ 2026-10-21：**第一个节点要标「进行中」**。
        #   原来只设 `current_node`，而设定集 yaml 里每个节点的 `状态` 都写着「未开始」
        #   ⇒ 数据层和界面两边各说各话：`current_node` 说"在 N01"，`状态` 说"一个都没开始"。
        #   可见后果（用户 2026-10-21 报的）：右上「剧情」面板把节点列出来时，
        #   **四个节点全是 ○，当前那个不高亮** —— 而"当前高亮"正是他点名要的。
        #
        #   ⚠ 只在该节点**还没开始**时标（空 / `未开始`），**绝不覆盖 `已完成`**：
        #     续跑时如果当前节点已经走完（`advance_node` 把它标成已完成、
        #     但 `current_node` 还指着它），覆盖就等于把进度倒回去。
        #   ⚠ 取值沿用装订期口径（`ingest/progress.py`：未开始 / 进行中 / 已完成 / 已偏离），
        #     别自造第五种。
        # [EN] ★★★ 2026-10-21: **mark the first node "in progress"**.
        # [EN] It used to set only `current_node` while the settings yaml says "not started" for every
        # [EN] node => the data and the UI disagreed: `current_node` said "we are at N01", `状态` said
        # [EN] "nothing has begun". Visible consequence (reported 2026-10-21): when the Plot panel
        # [EN] lists the nodes, **all four are ○ with no highlight on the current one** -- and that
        # [EN] highlight is exactly what the user asked for.
        # [EN] ⚠ Only mark it when it is **not yet started** (empty / `未开始`), and **never overwrite
        # [EN] `已完成`**: on resume, if the current node is already done (`advance_node` marked it done
        # [EN] while `current_node` still points at it), overwriting would rewind the progress.
        # [EN] ⚠ Reuse the binding-period vocabulary (`ingest/progress.py`: not started / in progress /
        # [EN] done / diverged) -- do not invent a fifth.
        _first = world.progress_nodes[0]
        if isinstance(_first, dict) and str(_first.get('状态') or '').strip() in ('', '未开始'):
            _first['状态'] = '进行中'

    # ★★ 分层设定（2026-10-07，见 `world/layers.py`）——
    #   把设定集按**作用范围**编成条目（世界/主线/场景/细节四层），
    #   `world_prefix()` 之后按"今天 + 这个场合 + 在场的这些人"筛着用。
    # [EN] ★★ Layered settings (2026-10-07, see `world/layers.py`) ——
    # [EN] Organize the setting collection into entries by **scope** (four layers: world / mainline / scene
    # [EN] / detail),
    # [EN] then after `world_prefix()` filter and use them by "today + this occasion + these people
    # [EN] present".
    #
    #   为什么在装配时编、而不是每次现编：它是**这一轮冻结的设定**的投影，
    #   一轮里不会变（变的只有剧组新增的局部设定 —— 那走 `rebuild_layers()`）。
    #   `_layer_settings` 留着是为了让 `rebuild_layers()` 能重编同一份来源。
    world._layer_settings = dict(settings)          # noqa: SLF001 —— 运行期私有料
    # [EN] Why compile at assembly time rather than compiling on the fly each time: it's the projection of
    # [EN] **this round's frozen settings**,
    # [EN] Does not change within a round (the only changes are the local settings newly added by the crew
    # [EN] — those go through `rebuild_layers()`).
    # [EN] `_layer_settings` is kept so that `rebuild_layers()` can rebuild from the same source.
    # [EN] noqa: SLF001 —— runtime private material
    try:
        world.rebuild_layers()
        _LOG.info("分层设定：%d 条（世界 %d · 主线 %d · 场景 %d · 细节 %d）",
                  len(world.layer_index),
                  sum(1 for i in world.layer_index if i.layer == 'canon'),
                  sum(1 for i in world.layer_index if i.layer == 'arc'),
                  sum(1 for i in world.layer_index if i.layer == 'scene'),
                  sum(1 for i in world.layer_index if i.layer == 'detail'))
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning("分层设定索引构建失败（退回老的单段前缀）：%r", e)
        world.layer_index = []

    # ★★ **项目档**（2026-10-07，`crew/profile.py`）——
    #   从类型卡＋风格卡推出"这本书的特别要求"（这本要多查什么、不许出现什么）。
    #   挂在 `world.crew_profile` 上，由 `crew/agents.craft_block()` 每拼一次手艺
    #   就接在后面 —— **一处设置、十二个职位同时生效**。
    # [EN] ★★ **Project profile** (2026-10-07, `crew/profile.py`) ——
    # [EN] Derive "this book's special requirements" from the type card + style card (what this book needs
    # [EN] extra checking on, what must not appear).
    # [EN] Attached to `world.crew_profile`, and each time `crew/agents.craft_block()` assembles the craft
    # [EN] block
    # [EN] it is appended right after —— **set in one place, effective for all twelve positions**.
    try:
        from crew import profile as PROF
        PROF.attach(world)
        from crew import agents as CREWAGENTS
        CREWAGENTS.bind_world(world)
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning("项目档挂载失败（剧组按默认手艺干活）：%r", e)
    return world


def build_atlas(settings_dir: Path | str | None) -> Atlas | None:
    """按 `设定集/小世界地图.yaml` 读**三级底图**（见 `world/atlas.py`）。

    用户 2026-10-08：「在开卷的时候把一些整体地图 局部地图(房屋附近 房屋内部)
    提前画好，需要的时候基于这些地图让美术加细节」。

    ★ 与它顶掉的旧函数 `build_map()` 的区别（这不是改名，是换了一条链）：
      旧的读的是同一份 yaml，但那份文件**从来只写过一个空占位**
      （`{"名称":"待生成","地点":[]}`），所以 `build_map()` 永远返回 `None`；
      而它返回的那个 `GameMap` 挂到主循环之后**没有任何地方读**。
      现在是**开卷时真的生成**（`ingest/atlas.py`）、运行时真的读来取景。

    `None` = 这本书没有底图（没生成过 / 生成失败 / `MAP_ATLAS` 关着）——
    **不是故障**：每天照旧现摆位，只是同一处地方的位置会飘。
    
        English:
        User 2026-10-08: "At the start of the book, draw some overall maps and local maps (near the house, inside the house)
        in advance, and when needed have the artist add details based on these maps."
        ★ The difference from the old function it replaces, `build_map()` (this is not a rename, it's switching to a different chain):
          the old one read the same yaml, but that file **had only ever contained an empty placeholder**
          and the `GameMap` it returned, after being attached to the main loop, **was read nowhere**.
          Now it is **actually generated at the start of the book** (`ingest/atlas.py`), and actually read at runtime to frame the scene.
        `None` = this book has no base map (never generated / generation failed / `MAP_ATLAS` turned off) --
        **not a fault**: every day it places things on the spot as before, except the position of the same place will drift.
    """
    try:
        # ⚠ 是**模块级函数** `world.atlas.load()`，不是 `Atlas.load()`
        #   —— 写成后者会 AttributeError，被下面那个 `except` 吞掉，
        #   表现成"这本书没有底图"（**静默失效**：底图明明生成了却不生效）。
        #   实测由 `tools/verify_resume_manage.py` 跑真机时打出来。
        # [EN] ⚠ It is the **module-level function** `world.atlas.load()`, not `Atlas.load()`
        # [EN] —— writing the latter causes AttributeError, which is swallowed by the `except` below,
        # [EN] manifesting as "this book has no base map" (**silent failure**: the base map was clearly
        # [EN] generated but does not take effect).
        # [EN] Actually observed when running on real hardware via `tools/verify_resume_manage.py`.
        from world import atlas as ATLAS
        return ATLAS.load(settings_dir)
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning("底图读回失败（当没有底图）：%r", e)
        return None


def freeze_settings_into_run(project, run) -> Path:
    """把项目级 `设定集/` 冻结一份到本轮运行文件夹，返回该目录。

    为什么需要这一步：运行文件夹的「本地设定集」是**这一轮冻结的快照** ——
    开跑时拷一份进去，之后项目设定改了也不影响正在跑的这一轮。

    判断标准必须是「**里面有没有人物.yaml**」，而不是「目录在不在」：
    `RunFolder.create()` 会把「本地设定集」建出来（空目录），
    只看 `exists()` 会一直读到空设定集 —— 这个坑真踩过。

    只**读**项目级设定集、只**写**运行文件夹；项目文件夹一如既往只读。
    
        English:
    Freeze a copy of the project-level `设定集/` into this round's run folder, and return that
    directory.
        Why this step is needed: the run folder's "local settings collection" is **a snapshot frozen for this round** --
        copy one in at start, and afterwards changes to the project settings won't affect the round that is already running.
        The criterion must be "**whether it contains 人物.yaml**", not "whether the directory exists":
        `RunFolder.create()` will create the "local settings collection" (an empty directory),
        so checking only `exists()` would keep reading an empty settings collection -- I've actually hit this pitfall before.
        Only **read** the project-level settings collection, only **write** the run folder; the project folder stays read-only as always.
    """
    dst = run.settings_dir
    if (dst / F_CHARS).exists():
        return dst
    src = getattr(project, "settings_dir", None)
    if src is None or not (src / F_CHARS).exists():
        return dst                      # 两边都没有 → 交给调用方报错（带明确提示）
        # [EN] Neither side has it → hand off to the caller to raise the error (with a clear message)
    dst.mkdir(parents=True, exist_ok=True)
    import shutil
    for p in src.iterdir():
        if p.is_file():
            try:
                shutil.copy2(p, dst / p.name)
            except OSError as e:                            # noqa: BLE001
                _LOG.warning("冻结 %s 失败: %s", p.name, e)
    _LOG.info("已把项目级设定集冻结到本轮：%s", dst)
    return dst


def assemble(project, run, *, image_hook=None, front_max: int | None = None,
             start_clock: Any | None = None,
             resume_scenes: list | None = None,
             resume_recap: str = "",
             user_directive: str = "",
             start_day: int = 1,
             db=None):
    """装配出可以跑的 `(loop, world, db)`。

    设定集来源按顺序：本轮已冻结的 →（没有就）从项目级冻结一份过来。

    `start_clock` / `resume_scenes` = **续跑**用的两样（2026-10-08）：
      · `start_clock`：这一轮从**哪天几点**起（`util.timefmt.GameTime`）；
      · `resume_scenes`：上一轮**同一天已经写好的那几幕** ——
        新的幕接在它们后面，收工落盘时就是**完整的这一天**（不覆盖掉前半段）。
    `resume_recap` = **本轮开头那句「上一回说到」**（2026-10-11）——
      本轮 db 是新的空库，`recap_text()` 读不到任何东西、只能退到设定集
      开场白，于是"每一轮前情提要都一样"（用户报的）。这一项把这句换掉，
      算它的是 `sim/resume.resume_recap`。不给就照旧。
    `user_directive` = **作者对本轮走向的建议**（2026-10-11）——
      用户在「起笔」对话框的**前情提要下面**填的那一栏，挂到 `world` 上供
      全剧组的提示词取用（`sim/directive.py`）。不给 = 没填 = 一个字都不加。
    `start_day` = **这一轮的写作天从几号起**（2026-10-31）——
      续跑时传 `resume.plan()['day']`。不传 = 1（新书从第 1 天起）。
      ⚠ 它和 `start_clock` **不是同一件事**：`start_clock` 是**故事钟**
      （`story_day`，可能被"站末补时间"推得比稿子快），`start_day` 是**第几份稿**
      （落盘文件名 / 幕头 / 停点 `day`）。两者不接就会各说一个数。
    这几项都由「起笔」按上一轮的停点/作者输入算（见 `sim/resume.py`）。
    
        English:
    Assemble a runnable `(loop, world, db)`.
        Settings collection sources in order: the one already frozen for this round -> (if none) freeze a copy from the project level.
        `start_clock` / `resume_scenes` = the two things used for **resuming a run** (2026-10-08):
          · `start_clock`: from **which day and what time** this round starts (`util.timefmt.GameTime`);
          · `resume_scenes`: the scenes **already written for the same day** in the previous round --
            new scenes are appended after them, and when work is finished and written to disk it is **the complete day** (without overwriting the earlier part).
        `resume_recap` = **the "previously on" line at the start of this round** (2026-10-11) --
          this round's db is a new empty database, `recap_text()` can't read anything and can only fall back to the settings collection's
          opening lines, hence "the recap is the same every round" (reported by the user). This item replaces that line;
          it's computed by `sim/resume.resume_recap`. If not provided, it stays as before.
        `user_directive` = **the author's suggestion for this round's direction** (2026-10-11) --
          the field the user fills in **below the recap** in the "起笔" dialog, attached to `world` for
          the whole crew's prompts to use (`sim/directive.py`). Not provided = not filled = not a single word is added.
        These items are all computed by "起笔" based on the previous round's stopping point / the author's input (see `sim/resume.py`).
    """
    # ★ 把**这本书的输出语言**装上（`util/outlang`）—— 所有 LLM 调用都会带上
    #   "输出用 X 语言"那一句。放在这里，无头脚本（不走 GUI）也能生效。
    # [EN] ★ Install **this book's output language** (`util/outlang`) —— all LLM calls will carry
    # [EN] the sentence "output in language X". Placed here so headless scripts (not going through the GUI)
    # [EN] also take effect.
    outlang.set_from_project(getattr(project, 'output_lang', ''))
    # ★★ Agent 设置（2026-10-11，`crew/catalog.py`）——
    #   ① `ensure_ready()`：首次运行时把内置职位的 md 与 `agents/README.md`
    #      播到软件目录（幂等，之后一次都不写）；**顺带保证盘上有那份文件**，
    #      因为作者要能直接用文本编辑器改它。
    #   ② `bind_project(project)`：告诉这一层"这一轮是哪本书" ——
    #      项目层那份定制（`<项目>/agents/`）就是这么被合进来的。
    #   ⚠ 挂不上**不让装配失败**（按出厂名册干活），但要说一声：
    #     静默退回出厂名册的表现是"我改的那句提示词不起作用"，最难查。
    # [EN] ★★ Agent settings (2026-10-11, `crew/catalog.py`) ——
    # [EN] ① `ensure_ready()`: on first run, copy the built-in positions' md and `agents/README.md`
    # [EN] into the software directory (idempotent, never writes again afterward); **also ensures that file
    # [EN] exists on disk**,
    # [EN] because the author must be able to edit it directly with a text editor.
    # [EN] ② `bind_project(project)`: tells this layer "which book this round is" ——
    # [EN] the project-level customization (`<project>/agents/`) is merged in this way.
    # [EN] ⚠ Failing to attach **must not fail assembly** (work from the factory roster), but say
    # [EN] something:
    # [EN] the silent fallback to the factory roster manifests as "the prompt I edited has no effect",
    # [EN] which is the hardest to diagnose.
    try:
        from crew import catalog as CAT
        CAT.ensure_ready()
        CAT.bind_project(project)
        _st = CAT.stats()
        _LOG.info("Agent 设置就绪：%d 个职位（自建 %d 个，本项目定制 %d 个）",
                  _st['total'], _st['custom'], _st['overridden'])
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning("Agent 设置没挂上（按出厂名册干活）：%r", e)
    settings_dir = freeze_settings_into_run(project, run)
    settings = load_settings(settings_dir)
    if not settings["people"]:
        raise SetupError(
            t("本地设定集里没有人物（{dir}）。请先在开卷向导里完成摄取，"
              "或检查「人物.yaml」。", dir=settings_dir))

    world = build_world(settings, front_max=front_max,
                        start_clock=start_clock,
                        scene=getattr(project, "scene_name", "") or "",
                        # 书斋的「风格来源」落在项目文件里（`风格=`）——
                        # 换项目就该换风格，所以它是项目级，不是全局。
                        # [EN] The study's "style source" lives in the project file (`风格=`),
                        # [EN] changing projects should change style, so it is project-level, not global.
                        style_source=getattr(project, "style", "") or "",
                        style_custom=getattr(project, "style_custom", "") or "",
                        # ★ 作者对本轮走向的建议（「起笔」对话框里填的）——
                        #   走参数、不走 CFG：它是**这一轮**的内容，
                        #   进 `.env` 就会在下一轮静默复活。
                        # [EN] ★ The author's suggestion for this round's direction (filled in the "起笔" dialog) ——
                        # [EN] goes through parameters, not CFG: it is **this round's** content,
                        # [EN] putting it in `.env` would silently resurrect it in the next round.
                        user_directive=user_directive)
    if not world.people:
        raise SetupError(t("人物.yaml 解析后仍为空 —— 检查文件格式"
                           "（应为 `- 姓名: …` 的列表）。"))

    # ★ 分层设定的两件收尾（2026-10-07）：
    #   ① **续跑**：把上一轮推演留下的局部设定读回来（剧组新增的那些）。
    #      必须先读、再 `rebuild_layers()` —— 顺序反了它们就不在索引里，
    #      表现成"昨天的临时设定今天不见了"。
    #   ② **落盘**：`分层设定.yaml` / `.md` + `临时设定.json` / `.md`。
    #      用户要的是"自己分层次、设置设定文件集合"——落成人能翻的一页，
    #      而不是只活在一个 dict 里。
    # [EN] ★ The two finishing touches of layered settings (2026-10-07):
    # [EN] ① **Resume**: read back the local settings left by the previous round's deduction (the ones the
    # [EN] crew newly added).
    # [EN] Must read first, then `rebuild_layers()` —— reverse the order and they will not be in the index,
    # [EN] manifesting as "yesterday's temporary settings are gone today".
    # [EN] What the user wants is to "layer things themselves and set up a collection of setting files" ——
    # [EN] persisted as a page humans can flip through,
    # [EN] rather than living only in a dict.
    try:
        from world import layers as LAYERS
        if CFG.b("SETTING_LAYERS"):
            prev = LAYERS.load_local(getattr(run, "root", None))
            if prev:
                world.local_settings = list(prev)
                world.rebuild_layers()
                _LOG.info("读回上一轮的局部设定：%d 条", len(prev))
            LAYERS.save_profile(getattr(run, "root", None), world.layer_index,
                                day=int(getattr(world, "game_day", 1) or 1),
                                # ⚠ 落盘标签**固定中文**（与剧本落盘同一条规矩：
                                #   这份 .md 是运行文件夹里的产物，不随界面语言走）
                                # [EN] ⚠ Persisted labels are **fixed in Chinese** (the same rule as script persistence:
                                # [EN] this .md is an artifact in the run folder, it does not follow the UI language)
                                extra_header="本页由程序生成 —— 它说明"
                                             "**哪一句设定**会在**什么时候**"
                                             "被谁看到。")
            LAYERS.save_local(getattr(run, "root", None), world)
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning("分层设定落盘/读回失败（不影响推演）：%r", e)

    # ★★ `db` 可以由调用方**现成地递进来**（2026-10-12）——
    #   `gui/app_flet._start_round` 现在把装配放进**后台线程**跑（界面不冻，
    #   超时看门狗才有机会跑），而 SQLite 的连接**默认不许跨线程用**：
    #   连接在哪个线程建，就只能在哪用。
    #   装配本身只把 `db` 转手交给 `Agent` / `DirectorEngine`（构造函数不碰它），
    #   所以"**主线城建连接、后台线程转手、之后主线城用**"是安全的；反过来
    #   （在这里建、拿回主线城用）会当场 `ProgrammingError`，实测过。
    #   不传就照旧自己建（无头脚本、判据都走这条路）。
    # [EN] ★★ `db` may be **handed in ready-made** by the caller (2026-10-12) --
    # [EN] `gui/app_flet._start_round` now runs assembly on a **background thread** (the UI does not freeze,
    # [EN] and the timeout watchdog gets its chance), while a SQLite connection **may not be used across
    # [EN] threads by default**: it belongs to whichever thread created it.
    # [EN] Assembly itself only passes `db` on to `Agent` / `DirectorEngine` (their constructors do not
    # [EN] touch it), so "**create the connection on the main thread, hand it over in the background
    # [EN] thread, use it from the main thread afterwards**" is safe; the other way round (create it here
    # [EN] and use it from the main thread) raises `ProgrammingError` on the spot -- measured.
    # [EN] If not passed, it creates its own as before (headless scripts and criteria all take that path).
    if db is None:
        db = DB(run.db_path)
    # ★★ 2026-10-10：把「这一轮属于哪个项目 / 哪个存档」告诉用量台账。
    #   设一次，之后这一轮里**所有** LLM 调用都会带上这两栏 ——
    #   它们是"统计界面第二层要按项目/推演任务划分"的数据来源。
    #   ⚠ 用 `set_ctx`（只覆盖给了的键），别用"整份替换"：
    #     这一轮里 Agent 名是随时在变的，替换会把人家设好的抹掉。
    # [EN] ★★ 2026-10-10: tell the usage ledger "which project / which save this round belongs to".
    # [EN] Set once, and afterward **all** LLM calls in this round carry these two columns ——
    # [EN] they are the data source for "the statistics UI's second layer divided by project / deduction
    # [EN] task".
    # [EN] ⚠ Use `set_ctx` (only overrides the keys given), not "replace the whole thing":
    # [EN] in this round the Agent name changes at any time, and replacement would wipe out what others
    # [EN] have set.
    try:
        from llm import usage as USAGE
        USAGE.set_ctx(module=USAGE.MODULE_SELF,
                      project=str(getattr(project, 'name', '') or ''),
                      run=str(getattr(run, 'name', '') or ''))
    except Exception:                                            # noqa: BLE001
        pass
    agents = [Agent(ps, db, world)
              for ps in world.people.values() if ps.role == "前台"]
    director = DirectorEngine(world, db)
    # ★ 合规 Agent（§16.1）：**独立**于叙事链的一份实例。
    #   造不出来（缺依赖等）不该让推演起不来，但**要说一声** ——
    #   合规是生死线，"悄悄没有合规"是最坏的一种安静。
    # [EN] ★ Compliance Agent (§16.1): a **separate** instance independent of the narrative chain.
    # [EN] Failure to create it (missing dependency, etc.) should not prevent the deduction from starting,
    # [EN] but **say something** ——
    # [EN] compliance is a life-or-death line, "silently having no compliance" is the worst kind of quiet.
    compliance = None
    try:
        from compliance.agent import ComplianceAgent
        compliance = ComplianceAgent(db)
        _LOG.info("合规 Agent 就绪：%s", compliance.status())
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning("合规 Agent 初始化失败（本轮**没有合规检查**）：%r", e)
    loop = RunLoop(world, agents, director, db, run,
                   atlas=build_atlas(run.settings_dir), image_hook=image_hook,
                   compliance=compliance,
                   # ★ 续跑：同一天已经写好的那几幕（见本函数说明）。
                   # [EN] ★ Resume: the scenes already written on the same day (see this function's description).
                   resume_scenes=resume_scenes,
                   # ★ 续跑：本轮开头那句「上一回说到」（见本函数说明）。
                   # [EN] ★ Resume: this round's opening line "last time on..." (see this function's description).
                   resume_recap=resume_recap,
                   # ★ 续跑：**写作天从哪儿起**（2026-10-31）。
                   #   `resume.plan()['day']` 就是上一轮停点记的那一天；不接的话
                   #   这一轮会从"第 1 天"重新编号，而世界时钟已经接着第 3 天了。
                   # [EN] ★ Resume: **which writing day to start from** (2026-10-31).
                   #   `resume.plan()['day']` is the day recorded by the previous stop point; without
                   #   this the round renumbers from "day 1" while the world clock already continues
                   #   at day 3.
                   start_day=start_day)
    # ★★ 剧组（2026-10-07）：**推演开始前先把这班人点清**。
    #   见 `crew/roster.py`（名册）与 `crew/studio.py`（制片厂）。
    # [EN] ★★ Crew (2026-10-07): **count the whole troupe clearly before the deduction begins**.
    # [EN] See `crew/roster.py` (roster) and `crew/studio.py` (studio).
    #
    #   为什么在这装配、而不是在 `RunLoop` 里自查：装配是"这一轮要开拍了"的那一刻，
    #   名册缺人或某个职位接到的东西不存在，**这时候报出来最便宜**
    #   （跑起来之后的表现是"某个职位于是一直不吭声"，那种最难查）。
    #   ⚠ 缺人/断线都**不让装配失败**（缺一个职位不该开不了机），但要说一声。
    # [EN] Why assemble here instead of self-checking in `RunLoop`: assembly is the moment of "this round
    # [EN] is about to start shooting",
    # [EN] if the roster is missing people or some position was given something that does not exist,
    # [EN] **reporting it at this point is cheapest**
    # [EN] (after it starts running, the manifestation is "some position just stays silent forever", which
    # [EN] is the hardest to diagnose).
    # [EN] ⚠ Missing people / broken links **must not fail assembly** (missing one position should not
    # [EN] prevent startup), but say something.
    try:
        chk = loop.studio.selfcheck()
        miss_roles = chk.get('members_missing') or []
        miss_hooks = chk.get('hooks_missing') or {}
        if miss_roles:
            _LOG.warning("剧组缺人（这些职位没有实现，今天不会出工）：%s",
                         "、".join(miss_roles))
        if miss_hooks:
            for k, hs in miss_hooks.items():
                _LOG.warning("剧组接线对不上：「%s」的 %s 在程序里找不到 —— "
                             "它声称接上的东西不存在（要修的是名册或那处实现）",
                             k, "、".join(hs))
        else:
            _LOG.info("剧组就绪：%d 个职位全部在位，接线全部命中",
                      len(ROSTER.ROSTER))
    except Exception as e:                                          # noqa: BLE001
        _LOG.warning("剧组自查失败（不影响推演）：%r", e)

    # ★★ 落三份"给人看"的档（2026-10-07）——
    #   `本剧组守则.md`：这本书要剧组多注意什么（项目档的投影）；
    #   `选角表.md`：谁演谁、凭什么配的、这一份的变奏是哪条；
    #   `本书可参考的写法.md`：拆书库里哪几份经验被这一本用上了、凭什么（第六轮加）。
    #   为什么落盘而不只是活在内存里：这些是**作者会想改/想核对**的东西
    #   （"这个人该换个演法""为什么用这本的经验"），而能改的前提是**看得见**。
    #   写失败只记日志（**不影响开跑**）——它们是说明书，不是运行依赖。
    # [EN] ★★ Persist three "for humans" files (2026-10-07) ——
    # [EN] `本剧组守则.md`: what this book needs the crew to pay extra attention to (a projection of the project
    # [EN] profile);
    # [EN] `选角表.md`: who plays whom, why they were cast that way, and which variation this copy is;
    # [EN] `本书可参考的写法.md`: which experiences from the book-analysis library were used by this book and why
    # [EN] (added in round six).
    # [EN] Why persist to disk rather than just live in memory: these are things **the author will want to
    # [EN] change / verify**
    # [EN] ("this person should act differently" "why use this book's experience"), and the prerequisite
    # [EN] for being able to change them is **being visible**.
    # [EN] Write failures only get logged (**does not affect startup**) —— they are documentation, not a
    # [EN] runtime dependency.
    try:
        root = getattr(run, "root", None)
        if root is not None:
            from crew import profile as PROF
            (root / '本剧组守则.md').write_text(
                PROF.table_md(getattr(world, 'crew_profile', None)),
                encoding='utf-8')
            from actors import casting as CASTING
            # 用 `build_world` 留下的**原始选角结果**（不是重算一遍）——
            # 重算会把"兜底来的"说成"点名的"（见 `build_world` 里那段说明）。
            # [EN] Use the **original casting results** left by `build_world` (not recomputing them) ——
            # [EN] recomputing would describe "fallback picks" as "hand-picked" (see the explanation in
            # [EN] `build_world`).
            _rows = list(getattr(world, '_casts', None) or [])
            if not _rows:
                _rows = [CASTING.instantiate(_n, _c) for _n, _c in _cast_cards(world)]
            (root / '选角表.md').write_text(CASTING.table_md(_rows),
                                            encoding='utf-8')
            # ★ 拆书经验：这一本用上了哪几份、凭什么
            # [EN] ★ Book-analysis experience: which ones this book used and why
            from booklab import store as BOOKLAB
            _card = getattr(world, 'genre_card', None) or {}
            (root / '本书可参考的写法.md').write_text(
                BOOKLAB.table_md(_card), encoding='utf-8')
            # ★★ 技能：逐职位列它这一刻挑到了哪几份知识包（2026-10-10，
            #    用户：「让他们在需要的时候选择合适的SKILL用起来」）。
            #    为什么也落盘：路由是**按职位**发生的，作者要能核对
            #    "该挑到药方的那个职位挑到没有" —— 活在提示词里就核不了。
            # [EN] ★★ Skills: list per position which knowledge packs it picked at this moment (2026-10-10,
            # [EN] user: "let them pick and use the appropriate SKILL when needed").
            # [EN] Why also persist to disk: routing happens **per position**, and the author must be able to
            # [EN] verify
            # [EN] "did the position that should have picked up the remedy pick it up" —— living only in the prompt
            # [EN] makes it unverifiable.
            from crew import skill_router as SKILLR
            (root / '本书可用的技能.md').write_text(
                SKILLR.table_md(str(_card.get('主题材') or _card.get('类型') or ''),
                                str(_card.get('结构') or '')),
                encoding='utf-8')
    except Exception as e:                                          # noqa: BLE001
        _LOG.warning("落「本剧组守则/选角表/可参考写法」失败（不影响推演）：%r", e)

    _LOG.info("装配完成：%d 人（前台 %d），%d 个进度节点，场景「%s」",
              len(world.people), len(agents), len(world.progress_nodes), world.scene)
    return loop, world, db


def _cast_cards(world) -> list[tuple[str, dict]]:
    """从已装配的世界里取回"人物名 → 卡"（落选角表用）。

    为什么从 `world.people` 反读、而不是把 `build_world` 里的 `_casts` 传出来：
      `assemble` 拿不到 `build_world` 的局部变量，而**再选一次**用同一份
      `PersonState` 是幂等的（类型/变奏都已经写进 `ps` 了，`instantiate`
      会优先用 `ps` 上已有的那份）—— 所以不需要把中间结果穿出来。
    
        English:
    Retrieve "character name -> card" from the assembled world (used for the rejected-cast list).
        Why read back from `world.people` instead of passing out the `_casts` from `build_world`:
          `assemble` cannot access `build_world`'s local variables, and **re-selecting once** with the same
          `PersonState` is idempotent (type/variation have already been written into `ps`, and `instantiate`
          will prefer the one already on `ps`) -- so there is no need to thread intermediate results out.
    """
    out: list[tuple[str, dict]] = []
    for name, ps in (getattr(world, 'people', None) or {}).items():
        out.append((name, {
            '性格': ps.personality, '身份': ps.identity, '口癖': ps.catchphrase,
            # ★ 2026-10-28：说话指纹也要跟着带上 —— 否则"落盘那份"和"真正在演的那份"
            #   不是同一份，界面上改了指纹、下一轮载入时又变回没有。
            # [EN] Carry the speech fingerprint too, so the persisted copy and the performed one
            # [EN] stay the same object.
            '说话指纹': getattr(ps, 'speech_fp', ''),
            # 已定好的，直接带上 —— 保证落盘那份和真正在演的那份是同一份
            # [EN] Already decided ones, carry them directly —— ensure the persisted copy and the one actually
            # [EN] being performed are the same copy
            '演员类型': getattr(ps, 'archetype', ''),
            '变奏': getattr(ps, 'variant', ''),
            '选角': getattr(ps, 'casting_note', ''),
            '打破类型': getattr(ps, 'break_type', ''),
        }))
    return out


def settings_summary(settings: dict) -> str:
    """一句话概括装到了什么（给对话框做"本轮将载入…"的提示）。
        English:
    Summarize in one sentence what was loaded (for the dialog's "this round will load..." hint).
    """
    # ★★★ 2026-10-21：进度节点数要报**拆分之后的**。
    #   装配时会把"一站捆几件事"的判据拆开（`world/progress_split.py`），
    #   而这里如果还报设定集里的原始站数，就会出现
    #   **"这一轮载入 4 个进度节点"但进度表上一共 10 站** —— 用户会以为出了问题。
    #   ⇒ 这里跑**同一份**拆分（纯字符串计算，不花钱、不碰文件），把真实会跑的站数报出来。
    #   ⚠ 只改数字、不新增文案：`t()` 的 key 是中文原文，新增未登记的 key
    #     会让 i18n 覆盖率判据变红，而这一条不需要新文案。
    # [EN] ★★★ 2026-10-21: report the **post-split** node count here.
    # [EN] Assembly splits nodes whose criterion packs several tasks (`world/progress_split.py`); if
    # [EN] this still reported the raw count from the settings file, you would get **"this round loads
    # [EN] 4 progress nodes" while the progress table shows 10 stations** -- which reads as a bug.
    # [EN] => Run **the same** split here (pure string work, no cost, touches no files) and report the
    # [EN] real number.
    # [EN] ⚠ Number only, no new wording: `t()` keys are the Chinese text, and adding an unregistered
    # [EN] key turns the i18n coverage criterion red, while this change needs no new wording.
    _nodes_n = len(settings['nodes'])
    try:
        from world import progress_split as _PS
        _split, _made = _PS.split_fat_nodes(settings['nodes'])
        if _made:
            _nodes_n = len(_split)
    except Exception:                                        # noqa: BLE001
        pass
    bits = [t("人物 {n} 位", n=len(settings['people'])),
            t("进度节点 {n} 个", n=_nodes_n)]
    if settings["places"]:
        bits.append(t("地点 {n} 处", n=len(settings["places"])))
    if settings["foreshadows"]:
        bits.append(t("伏笔 {n} 条", n=len(settings["foreshadows"])))
    if settings.get("detail"):
        bits.append(t("细节 {n} 条", n=len(settings["detail"])))
    return " · ".join(bits)
