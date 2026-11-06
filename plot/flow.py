# -*- coding: utf-8 -*-
"""剧情总览（`剧情总览.json`）：一次推演「从头到尾」的流程图数据。

用户 2026-10-26：
    「运行界面右侧的剧情Panel的按钮 可以点击 我点击了之后出现一个对话框 其中包含了本次推演
     从开始到现在的故事线，包含所有主要情节，其中每个情节用少量文字总结，作为一个Panel。
     然后从开头到结尾用一个流程图（从上往下的）展示，如果中间涉及到了让用户选择剧情，
     则展示一个多选，并从用户选择的剧情继续流程。还有，我希望这个Panel可以作为主入口，
     除了当前推演，对话框的最上面加一个跑马灯形式的左右切换，我还可以切换到之前的推演，
     查看之前的剧情流程图。」

★★★ 三条设计规矩（都踩过）：

① **一条故事线只有一个事实来源**：情节 = `设定集/故事进度.yaml` 的节点，
   「演到哪儿了」= 这次推演 `每天的生活/*.json` 里每幕的 `node_name`。
   两边都不复制、不另存 —— 界面里那句"正在演"和导出里那章叫什么，必须同源。

② **不花 LLM**：这张图是**读出来的**，不是"让模型总结一遍"。
   理由与 `_flush_novel_on_stop` 那条一样：停止/刷新路径上花钱，用户点一次「停止」
   就可能被扣一笔，而且它要的是"我演过什么"，不是"模型觉得我演过什么"。
   节点的「概要」本来就是作者/构建步骤写好的三十来字，够用了。

③ **推断必须标注**：选项（"三条路"）现在多半是**从概要里读出来的** ——
   那就照实写 `inferred: True`，界面显示「（从概要里读出来的）」，作者才知道去补
   `选项:` 字段。与 `actors/casting.age_guessed`、`progress.inferred` 同一口径。

English:
Story overview (`剧情总览.json`): the flowchart data for one run, start to finish.
★★★ Three rules (all learned the hard way):
① **One source of truth per story line**: plot points come from the nodes in
  `设定集/故事进度.yaml`; "how far we got" comes from each scene's `node_name` in this run's
  `每天的生活/*.json`. Neither is copied or re-stored -- "currently playing" in the UI and the
  chapter name in the export must share one source.
② **No LLM calls**: the chart is **read**, not "summarised by a model". Same reason as
  `_flush_novel_on_stop`: spending money on a refresh path means one click on Stop can bill the
  user, and what they asked for is "what did I play", not "what does a model think I played".
  The node summaries are already 30-odd characters written by the author/build step.
③ **Inference must be marked**: the choice options are usually **read out of the summary** right
  now, so record `inferred: True` honestly and let the UI say "read out of the summary" -- only
  then does the author know to fill in the `选项:` field. Same rule as
  `actors/casting.age_guessed` and `progress.inferred`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = [
    'FLOW_FILE', 'SCHEMA',
    'STATE_DONE', 'STATE_NOW', 'STATE_TODO',
    'MARK_TURN', 'MARK_KEY', 'TURN_TENSION', 'MAX_DETAIL_DAYS',
    'flow_path', 'read_nodes', 'choice_options', 'scan_days',
    'scan_detail', 'build_flow', 'ensure_flow', 'save_flow', 'load_flow', 'is_stale',
    'list_runs', 'set_pick', 'pick_of', 'branch_points_of',
]

#: 剧情总览落在**推演文件夹**里（每个推演一份，跟着存档一起搬）。
# [EN] The overview lives **in the run folder** (one per run, moves with the archive).
FLOW_FILE = '剧情总览.json'

#: 数据版本。改结构时 +1，读旧文件走兼容（见 `load_flow`）。
# [EN] Data version; bump on structural change, old files are tolerated by `load_flow`.
SCHEMA = 1

STATE_DONE = 'done'      # 这次推演里演过、且已经收尾
STATE_NOW = 'now'        # 正在演的一站
STATE_TODO = 'todo'      # 还没演到

# ── 详细剧情的标记等级（2026-10-26）─────────────────────────────
#: **转折点**：导演认定的事件（`event` 条目带 caption）与**情节站切换**。
#: 这两类的共同点是"从那以后不一样了"，不是"戏更好看"。
# [EN] **Turning point**: an event the director asserts (an `event` entry with a caption) or a
# [EN] station switch. Both mean "things are different after this", not "this bit was good".
MARK_TURN = 'turn'
#: **关键剧情**：张力一步跳得够大（`TURN_TENSION` 以上）或有人第一次登场。
#: ⚠ 与转折点分开，是因为它**只是"戏紧了"**，未必换了方向 —— 混成一档会让
#:   "转折点"这个词失去意义（用户要的是"关键剧情**和**转折点"，两件事）。
# [EN] **Key beat**: tension jumps by at least `TURN_TENSION`, or someone appears for the first time.
# [EN] ⚠ Kept apart from a turning point because it only means "the scene got tight", not "the
# [EN] direction changed" -- merging them makes the word "turning point" meaningless (the user asked
# [EN] for key plot **and** turning points, two things).
MARK_KEY = 'key'

#: 张力跳多大才算"关键"。0.15 的量级参考：本机真跑一天 12 幕的张力区间是 0.30~0.77，
#: 单幕常见跳幅 0.00~0.14 ⇒ 0.15 意味着"确实换了火候"，而不是日常抖动。
# [EN] How big a tension jump counts as "key". Calibration: a real 12-scene day here spans
# [EN] 0.30-0.77 with typical single-scene jumps of 0.00-0.14, so 0.15 means "the heat really
# [EN] changed" rather than normal jitter.
TURN_TENSION = 0.15

#: 详细剧情最多收几天（超出的只留梗概与标记，不存分拍与正文）。
#: ⚠ 为什么要有上限：这一层存的是**剧作家的正文与分拍**（实测一天 ~2650 字正文 + 6 拍 +
#:   16 镜）。30 天就是 8 万字，界面打开会卡、`剧情总览.json` 会涨到 MB 级。
#:   上限之后"很久以前的那几天"仍然有梗概和转折点 —— 只是没有逐拍细节，
#:   而那正是"回头看大概"用得上的部分。
# [EN] How many days of detail to keep (older ones keep only the brief and marks, no beats/prose).
# [EN] ⚠ Why a cap: this layer stores **the playwright's prose and beats** (measured: ~2650
# [EN] characters plus 6 beats and 16 shots per day). Thirty days is 80k characters, which makes the
# [EN] dialog sluggish and the JSON megabyte-sized. Beyond the cap the brief and marks remain -- exactly
# [EN] the part useful for "recall roughly what happened".
MAX_DETAIL_DAYS = 30

#: 每天最多存几拍 / 几镜（异常长的一天不把整个文件撑爆）。
# [EN] Max beats / shots stored per day.
MAX_BEATS_DAY = 40
MAX_SHOTS_DAY = 80
#: 正文最多存几段（超出的截断并记一笔）。
# [EN] Max prose paragraphs stored per day.
MAX_STORY_PARAS = 200

_PROGRESS_NAMES = ('故事进度.yaml', '故事进度.yml')
_DAY_RE = re.compile(r'^第(\d+)天')

#: 「三条路」这类写法 → 选项。`(三|两|几)` 是因为作者不会写"3 条路"。
# [EN] "three roads" style phrasing -> options. `(三|两|几)` because authors don't write "3 roads".
_CHOICE_TAIL = re.compile(r'(.{2,80}?)([三两几])条(?:路|道)')
#: 选项前面那句话的引导词（"阿九**面对**归籍、祭献、留门三条路"）。
# [EN] Lead-in words before the options.
_CHOICE_LEAD = re.compile(r'^.*?(?:面对|可走|可选|分别是|摆在面前的|要在|是)')
#: 选项之间的分隔：顿号/逗号/斜杠/或/还是/以及。
# [EN] Separators between options.
_CHOICE_SEP = re.compile(r'[、，,／/；;]|还是|或者|以及|和')


def flow_path(run_root) -> Path:
    """这一次推演的剧情总览文件路径。"""
    return Path(run_root) / FLOW_FILE


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M')


# ══════════════════════════════════════════════════════════════
#  读：情节表 + 演过的天
# [EN] Read: the plot table + the days that were played
# ══════════════════════════════════════════════════════════════
def read_nodes(settings_dir) -> list[dict]:
    """读 `设定集/故事进度.yaml` 的节点（**原样字段**，不做任何推断）。

    ⚠ 自己解析而**不走 `sim.setup.load_settings`**：那一个是"把整个世界装起来"
      （要人物、地点、关系、类型卡…），只为了看一张情节表就把世界装一遍，
      对话框一打开就是几秒白屏。这里只读一个 yaml。
    ⚠ 结构不认识就返回 `[]`（**不猜**）：抱着一个猜错的结构画流程图，
      比画不出来更糟 —— 用户会拿它当"我演过这些"。

    [EN] Read the nodes of `设定集/故事进度.yaml` (fields as-is, no inference).
    ⚠ Parses directly instead of `sim.setup.load_settings`: that one **assembles the whole world**
    (characters, places, relations, genre...), and assembling a world just to see a plot table means
    a multi-second white screen every time the dialog opens. This reads one yaml.
    ⚠ Unknown structure returns `[]` (no guessing): drawing a chart from a mis-guessed structure is
    worse than drawing nothing -- the user would read it as "this is what I played".
    """
    d = Path(settings_dir)
    path = next((d / n for n in _PROGRESS_NAMES if (d / n).is_file()), None)
    if path is None:
        return []
    try:
        import yaml
        doc = yaml.safe_load(path.read_text(encoding='utf-8', errors='ignore')) or {}
    except Exception:                                            # noqa: BLE001
        return []
    raw = doc.get('节点') if isinstance(doc, dict) else doc
    out: list[dict] = []
    for i, n in enumerate(raw or [], 1):
        if not isinstance(n, dict):
            continue
        out.append({
            'id': str(n.get('id') or f'N{i:02d}'),
            'name': str(n.get('名称') or n.get('name') or '').strip(),
            'summary': str(n.get('概要') or n.get('summary') or '').strip(),
            'criteria': str(n.get('完成判据') or n.get('criteria') or '').strip(),
            'status': str(n.get('状态') or n.get('status') or '未开始').strip(),
            'span': str(n.get('跨度') or '').strip(),
            'weight': str(n.get('篇幅') or '').strip(),
            'options': n.get('选项') or n.get('分支') or n.get('options') or [],
        })
    return out


def choice_options(node: dict) -> tuple[list[dict], bool]:
    """这一站是不是**要用户选**：返回 `(选项列表, 是否程序推的)`。

    选项列表的形状是 `[{'label': '归籍', 'points': [...]}]`；`points` 可以为空
    （"这条线后面的事还没演到"）。

    ★ 两条来源，作者写的优先：
      ① `选项:` 字段（列表，或 `A、B、C` 字符串，或 `[{标签, 后续}]`）—— 作者写的，`inferred=False`；
      ② 概要用「…归籍、祭献、留门**三条路**…」这种写法 —— **读出来的**，`inferred=True`。
    ②存在，是因为老项目的进度表里没有 `选项:`，而"故事到这儿要选"这件事
    本来就写在概要里了；不读它，流程图就永远是"一条直路"，而那与故事不符。

    ⚠ 推出来的选项**必须**带 `inferred=True`（界面要显示"从概要里读出来的"）。
    ⚠ 判据保守：`2 <= 选项数 <= 4`、每个 `1~8` 字、不能含"的"。读不出来就是没有选择点，
      **宁可少画一个分叉，也不要在直路上凭空造一个选择**（用户会真的去点）。

    [EN] Is this station a **user choice**? Returns `(options, inferred)`. Options are
    `[{'label': ..., 'points': [...]}]`, `points` may be empty ("what follows this line hasn't been
    played"). ★ Two sources, the author's own wins: ① an `选项:` field; ② phrasing like
    "...归籍、祭献、留门**三条路**..." in the summary -- **read out of it**, `inferred=True`.
    ② exists because old projects have no `选项:` field while "there's a choice here" is already
    stated in the summary; without it the chart would always be one straight road.
    ⚠ Inferred options **must** carry `inferred=True` (the UI says "read out of the summary").
    ⚠ Deliberately conservative: 2-4 options, 1-8 characters each, no "的". Unreadable => no choice
    point; **better to miss a fork than to invent one on a straight road** (the user really clicks it).
    """
    raw = node.get('options')
    labels: list[str] = []
    points: list[list[dict]] = []
    if isinstance(raw, str):
        raw = [x for x in _CHOICE_SEP.split(raw) if x.strip()]
    if isinstance(raw, list) and raw:
        for item in raw:
            if isinstance(item, dict):
                lb = str(item.get('标签') or item.get('label') or item.get('名称') or '').strip()
                nxt = item.get('后续') or item.get('points') or []
                labels.append(lb)
                points.append([p for p in nxt if isinstance(p, dict)])
            else:
                labels.append(str(item).strip())
                points.append([])
        labels = [x for x in labels if x]
        if len(labels) >= 2:
            return ([{'label': lb, 'points': pt} for lb, pt in zip(labels, points)], False)
        return [], False

    m = _CHOICE_TAIL.search(str(node.get('summary') or ''))
    if not m:
        return [], False
    body = _CHOICE_LEAD.sub('', m.group(1))
    parts = [x.strip() for x in _CHOICE_SEP.split(body) if x and x.strip()]
    parts = [x for x in parts if 1 <= len(x) <= 8 and '的' not in x]
    if 2 <= len(parts) <= 4:
        return ([{'label': x, 'points': []} for x in parts], True)
    return [], False


def _read_scenes(json_path: Path) -> list[Any]:
    """读一天的 `.json` 边车 → `SceneScript` 列表（读不出就空表）。"""
    try:
        from display import script_render as SR
        return list(SR.from_json(json_path.read_text(encoding='utf-8', errors='ignore')) or [])
    except Exception:                                            # noqa: BLE001
        return []


def scan_days(run_root) -> list[dict]:
    """这一次推演**已经落盘的每一天**：几幕、演了哪几站、从几点到几点。

    返回 `[{day, scenes, from, to, nodes, node_counts, last_node}]`，按天升序。

    ⚠ 只认 `第NNN天.json`（幕里才带 `node_name`）。只有 `.md` 的老运行 ⇒ 返回空
      ⇒ 情节表全标"还没演到"，而不是瞎猜 —— 这和导出的退化路径是同一条规矩。
    ⚠ `nodes` 只做**去重、保留首次出现顺序**（不按名字合并两天，见 `导出按事件装订`）。
    [EN] Every persisted day of this run: how many scenes, which stations, what time span.
    ⚠ Only `第NNN天.json` counts (scenes carry `node_name`); old runs with only `.md` return nothing
    => every plot point reads "not yet", instead of guessing. Same rule as the export's fallback.
    ⚠ `nodes` deduplicates **preserving first appearance**.
    """
    d = Path(run_root) / '每天的生活'
    if not d.is_dir():
        return []
    out: list[dict] = []
    for p in sorted(d.glob('*.json')):
        m = _DAY_RE.match(p.name)
        if not m:
            continue
        scenes = _read_scenes(p)
        if not scenes:
            continue
        names: list[str] = []
        counts: dict[str, int] = {}
        for s in scenes:
            nm = str(getattr(s, 'node_name', '') or '').strip()
            if not nm:
                continue
            counts[nm] = counts.get(nm, 0) + 1
            if nm not in names:
                names.append(nm)
        out.append({
            'day': int(m.group(1)),
            'scenes': len(scenes),
            'from': str(getattr(scenes[0], 'time_label', '') or ''),
            'to': str(getattr(scenes[-1], 'time_label', '') or ''),
            'nodes': names,
            'node_counts': counts,
            'last_node': str(getattr(scenes[-1], 'node_name', '') or '').strip(),
        })
    out.sort(key=lambda x: x['day'])
    return out


# ══════════════════════════════════════════════════════════════
#  详细剧情：剧作家的分拍 + 正文 + 关键剧情与转折点
# [EN] Detailed story: the playwright's beats + prose + key beats and turning points
# ══════════════════════════════════════════════════════════════
#: 剧作家工作底稿的文件名（`director/day_plan.save_cached` 写的）。
#: ⚠ 与 `director.day_plan.CACHE_NAME` 是同一个文件 —— 两边各写一个名字，
#:   一边改名另一边查不到，表现就是"详细剧情永远是空的"（而且不报错）。
# [EN] The playwright's working draft filename (written by `director/day_plan.save_cached`).
# [EN] ⚠ It is the same file as `director.day_plan.CACHE_NAME`; two literals would drift and the
# [EN] detail layer would be **permanently empty** -- without any error.
_SCRIPT_CACHE = '当日剧本.json'

#: 正文段落之间怎么切。剧作家的正文用空行分段（实测 2650 字 / 49 段）。
# [EN] How the prose is split; the playwright separates paragraphs with blank lines.
_PARA_SEP = re.compile(r'\n\s*\n')


def _read_script_cache(run_root: Path) -> dict:
    """读 `当日剧本.json`（按天累积的那份底稿）：`{day: {...}}`，读不出就空。

    ⚠ **优先用 `director.day_plan.load_cached`**（那边是写入方，字段含义只有一处）；
      这里只做"整天批量读"这一件事，避免逐天调 30 次。
    [EN] Read the by-day working draft (`当日剧本.json`) as `{day: {...}}`, empty when unreadable.
    [EN] ⚠ Prefers `director.day_plan.load_cached` (the writer, so field meanings live in one place);
    [EN] this only does the "read them all at once" part instead of 30 separate calls.
    """
    p = Path(run_root) / _SCRIPT_CACHE
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding='utf-8', errors='ignore'))
    except Exception:                                            # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[int, dict] = {}
    for k, v in data.items():
        try:
            day = int(str(k).strip())
        except (TypeError, ValueError):
            continue
        if isinstance(v, dict):
            out[day] = v
    return out


def _marks_of(scenes: list, prev_node: str = '',
              prev_cast: set | None = None) -> tuple[list[dict], set, str]:
    """一天的**关键剧情与转折点**（从真演出的幕里数出来，一个字都不编）。

    返回 `(标记列表, 累计人物集合, 最后一站的站名)` —— 后两个是**跨天状态**，
    由调用方逐天递进来再递出去（见下面第三条 ⚠）。

    四条判据，按"有多硬"排序：

    | 判据 | 等级 | 为什么算 |
    |---|---|---|
    | `event` 条目（导演认定的事件，带 caption） | **转折** | 那不是"演出来的"，是**有人按下去的**；它出现就意味着方向变了 |
    | 情节站切换（`node_name` 变了） | **转折** | 故事从这一站走到了下一站 |
    | 张力一步跳 ≥ `TURN_TENSION` | 关键 | 火候变了（但方向没变） |
    | **换场**（幕级 `place` 变了） | 关键 | 戏的舞台换了 —— 比"谁进来了"更能说明"这一段过去了" |

    ⚠ **"某某第一次登场"这条判据被删掉了（2026-10-26 实测后）**：
      第一版按 `cast` 判"新人"，而 `cast` 是**这一刻的在场名单** —— 开场那一幕
      全员都在，于是第一天的"关键剧情"变成 7 条「阿九 第一次登场」「沈砚 第一次登场」…
      把真正的转折全淹了。人物表在"在场人物"那一栏已经写着，**不该占转折点的位置**。
      真要"新角色进来"，该由 `event`（导演事件）或剧情站推进来表达，那两条本来就有。
    ⚠ **张力跳变只在同一天内比较**：跨天的张力会被日界回落带走（`TENSION_CURVE`），
      拿它跟昨天比会把每个日界都判成"转折"。
    ⚠ `prev_cast` 仍然返回（统计"这次推演出现过几个人"有用），但**不再参与判据**。
    [EN] The day's **key beats and turning points**, counted out of the scenes actually played.
    [EN] Four criteria ordered by hardness: ① an `event` entry (the director asserted it, with a
    [EN] caption) is a **turn** -- it is not "something that came out of the acting", someone pressed
    [EN] it, so it means the direction changed; ② a **station switch** is a **turn**; ③ a tension jump
    [EN] of at least `TURN_TENSION` is a **key beat** (the heat changed, not the direction); ④ a
    [EN] **change of place** is a **key beat** -- the stage moved, which says more about "this stretch
    [EN] is over" than "who walked in".
    [EN] ⚠ **The "first appearance" criterion was deleted** (measured 2026-10-26): the first version
    [EN] judged newcomers from `cast`, which is **who is present right now** -- the opening scene has
    [EN] everyone, so day one's "key plot" became seven lines of "X appears for the first time",
    [EN] drowning the real turning points. The cast list already lives in its own panel and **must not
    [EN] occupy the turning-point slots**. A genuinely new character belongs in an `event` or a station
    [EN] advance, both of which are already covered.
    [EN] ⚠ Tension jumps are compared **within one day only**: across a day boundary the curve resets
    [EN] (`TENSION_CURVE`), so comparing with yesterday would mark every boundary a turning point.
    [EN] ⚠ `prev_cast` is still returned (useful as "how many people appeared in this run") but **no
    [EN] longer feeds any criterion**.
    """
    out: list[dict] = []
    seen = set(prev_cast or set())
    node = str(prev_node or '')
    place = ''                     # ⚠ 换场判据**每天重置**：跨天本来就在别处开场
    for sc in (scenes or []):
        tl = str(getattr(sc, 'time_label', '') or '')
        nm = str(getattr(sc, 'node_name', '') or '').strip()
        pl = str(getattr(sc, 'place', '') or '').strip()
        t0 = _as_float(getattr(sc, 'tension_before', 0.0))
        t1 = _as_float(getattr(sc, 'tension_after', 0.0))
        for who in (getattr(sc, 'cast', None) or []):
            if str(who or '').strip():
                seen.add(str(who).strip())
        # ① 导演认定的事件
        for e in (getattr(sc, 'entries', None) or []):
            if str(getattr(e, 'kind', '') or '') != 'event':
                continue
            txt = str(getattr(e, 'text', '') or '').strip()
            if not txt:
                continue
            out.append({'kind': MARK_TURN, 'why': 'event',
                        'caption': str(getattr(e, 'caption', '') or ''),
                        'text': txt, 'time': tl, 'place': pl, 'node': nm,
                        'tension': [round(t0, 3), round(t1, 3)]})
        # ② 情节站切换（第一幕不算"切换"：那是这一天的起点）
        if node and nm and nm != node:
            # ⚠ 只给**代码 + 参数**，不给拼好的中文句子：这个文件会被英文界面读，
            #   把「情节推进到「X」」写进 JSON 就是又一次"把语言冻进盘里"
            #   （上一轮 `detail`/`tail` 就栽在这上面，见 `_evidence_of` 的说明）。
            #   排版归界面：`gui.story_flow_dialog.mark_text()`。
            # [EN] Only a **code + parameters**, never a pre-assembled Chinese sentence: an English
            # [EN] UI reads this file, and baking the sentence in freezes the language onto disk --
            # [EN] exactly what `detail` / `tail` did last round (see `_evidence_of`). Formatting
            # [EN] belongs to `gui.story_flow_dialog.mark_text()`.
            out.append({'kind': MARK_TURN, 'why': 'node', 'caption': '',
                        'node': nm, 'time': tl, 'place': pl,
                        'tension': [round(t0, 3), round(t1, 3)]})
        if nm:
            node = nm
        # ③ 换场（同一天内的幕级地点变化）
        if place and pl and pl != place:
            out.append({'kind': MARK_KEY, 'why': 'place', 'caption': '',
                        'a': place, 'b': pl, 'time': tl, 'place': pl, 'node': nm,
                        'tension': [round(t0, 3), round(t1, 3)]})
        if pl:
            place = pl
        # ④ 张力跳变
        if abs(t1 - t0) >= TURN_TENSION:
            out.append({'kind': MARK_KEY, 'why': 'tension', 'caption': '',
                        'a': round(t0, 2), 'b': round(t1, 2),
                        'time': tl, 'place': pl, 'node': nm,
                        'tension': [round(t0, 3), round(t1, 3)]})
    for m in out:
        # `event` 的正文是**素材原文**（导演写的事件描述），照原样留；其余都是代码。
        # [EN] An `event`'s body is **source material** (the director's own wording) and stays as-is;
        # [EN] everything else is a code.
        if m.get('text'):
            m['text'] = _clip(m['text'], 200)
    return out, seen, node


def _as_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _beat_row(b: dict) -> dict:
    """一拍 → 一条**可读的小段**（剧作家原本就是按这个粒度写的）。

    ⚠ 只搬**已有的字段**，不补写：`发生` 是"这一拍到底发生了什么"，
      `要点` 是几句具体动作，`推进` 是它对主线的推动。缺的字段留空
      （比如有的拍没有 `难题`），而不是拿别的字段顶替 —— 顶替会让读者
      把"目标"当成"发生"，而那两件事在剧作上是不同的。
    [EN] One beat -> one **readable segment** (this is exactly the granularity the playwright wrote
    [EN] at). ⚠ Only existing fields are carried over, never filled in: 发生 is "what actually happens
    [EN] in this beat", 要点 are concrete actions, 推进 is its push on the main line. Missing fields stay
    [EN] empty (some beats have no 难题) rather than being substituted -- substituting would make the
    [EN] reader take "goal" for "what happened", two different things in dramaturgy.
    """
    def _s(k: str) -> str:
        return str(b.get(k) or '').strip()

    pts = b.get('要点') or []
    if isinstance(pts, str):
        pts = [pts]
    cast = b.get('出场') or []
    if isinstance(cast, str):
        cast = [cast]
    return {
        'n': int(b.get('拍') or 0) or 0,
        'scene': _s('场'),
        'theme': _clip(_s('主题'), 80),
        'cast': [str(x).strip() for x in cast if str(x).strip()],
        'happen': _clip(_s('发生'), 400),
        'points': [_clip(str(x), 200) for x in pts if str(x).strip()][:12],
        'push': _clip(_s('推进'), 200),
        'goal': _clip(_s('目标'), 120),
        'mood': _clip(_s('情绪'), 60),
        'props': _clip(_s('道具'), 80),
        'trouble': _clip(_s('难题'), 160),
    }


def _shot_row(s: dict) -> dict:
    """一镜 → 一条（分镜师给的镜头清单；正文之外"画面上是什么"就靠它）。"""
    def _s(k: str) -> str:
        return str(s.get(k) or '').strip()
    return {
        'n': int(s.get('镜') or 0) or 0,
        'beat': int(s.get('拍') or 0) or 0,
        'size': _clip(_s('景别'), 20),
        'frame': _clip(_s('画面'), 240),
        'line': _clip(_s('台词'), 240),
        'point': _clip(_s('叙事点'), 120),
    }


def scan_detail(project_dir, run_root, *, days: list[dict] | None = None) -> dict:
    """这一次推演的**详细剧情**：按天摊开剧作家的分拍、正文、以及关键剧情与转折点。

    用户 2026-10-26：「剧情总览太简略了 我希望是每次推演里面的**细节剧情** 要很详细
    （到达每次剧作家写**小段剧情**的程度）要包含当前这次推演的**关键剧情和转折点**」

    ★ "剧作家写的小段"就是 `当日剧本.json` 里的 **`beats`（分拍）**：
      每拍有 `场` / `主题` / `发生` / `要点` / `推进` —— 那是剧作家交付的**最小叙事单元**，
      比它更细的只有逐条台词（那是演员的活，不是"剧情"）。
      `story` 是他把这些拍连起来写的**正文**，`shots` 是分镜师按拍拆的镜头。
      三层都收：先看小段（抓得住情节）、再看正文（读得到笔法）、最后看镜头（想得起画面）。

    ★ **一个模型调用都不花**：全是读盘 + 数数。用户点开总览不该被扣额度。

    ★ 转折点从**真演出的幕**里数（`event` / 站切换 / 张力跳 / 新人登场），
      不从分拍里猜 —— 分拍是"打算演什么"，幕才是"真的演成了什么"。
      用户要的是"这次推演发生了什么"，不是"剧作家的计划"。

    ⚠ 只收 `MAX_DETAIL_DAYS` 天：更早的天保留梗概与标记，去掉分拍/正文/镜头
      （见 `MAX_DETAIL_DAYS` 的说明）。**梗概与转折点一天都不少**。
    ⚠ 读不出 `当日剧本.json` 时仍然给"按天 + 标记"（那是从幕里数的），
      只是没有分拍与正文 —— 老运行（这个文件之前没有）照样能看。
    [EN] This run's **detailed story**: per day, the playwright's beats, prose, and the key beats and
    [EN] turning points. ★ "The playwright's small segment" is `beats` in `当日剧本.json`: each has
    [EN] scene / theme / what happens / key points / push, the **smallest narrative unit** delivered.
    [EN] Finer than that are individual lines (the actors' work, not "plot"). `story` is his prose
    [EN] connecting them and `shots` the storyboard. All three are kept: beats to hold the plot, prose
    [EN] to feel the writing, shots to recall the picture.
    [EN] ★ **Zero model calls** -- all disk reads and counting. Opening the overview must not bill.
    [EN] ★ Turning points are counted from the scenes **actually played** (event / station switch /
    [EN] tension jump / newcomer), never guessed from the beat sheet -- the sheet is "what we planned",
    [EN] the scenes are "what actually happened", and the user asked for the latter.
    [EN] ⚠ Only `MAX_DETAIL_DAYS` days are kept; older ones keep the brief and marks but lose
    [EN] beats/prose/shots. **The brief and turning points are never dropped.**
    [EN] ⚠ Without `当日剧本.json` it still returns per-day marks from the scenes -- old runs work.
    """
    project_dir = Path(project_dir)
    run_root = Path(run_root)
    if days is None:
        days = scan_days(run_root)
    cache = _read_script_cache(run_root)
    keep_from = (max((d['day'] for d in days), default=0) - MAX_DETAIL_DAYS + 1) if days else 0

    out_days: list[dict] = []
    turns: list[dict] = []
    prev_cast: set = set()
    prev_node = ''
    for d in days:
        day = int(d['day'])
        scenes = _read_scenes((run_root / '每天的生活' / f'第{day:03d}天.json'))
        marks, prev_cast, prev_node = _marks_of(scenes, prev_node, prev_cast)
        for m in marks:
            m['day'] = day
        turns.extend(marks)

        rec = cache.get(day) or {}
        row: dict = {
            'day': day,
            'from': d.get('from', ''),
            'to': d.get('to', ''),
            'scenes': int(d.get('scenes') or 0),
            'nodes': list(d.get('nodes') or []),
            'brief': _clip(str(rec.get('day_brief') or ''), 300),
            'intro': _clip(str(rec.get('scene_intro') or ''), 400),
            'marks': marks,
            'beats': [], 'shots': [], 'story': [], 'notes': [],
        }
        if day >= keep_from:
            raw_beats = rec.get('beats') or []
            if isinstance(raw_beats, list):
                row['beats'] = [_beat_row(b) for b in raw_beats[:MAX_BEATS_DAY]
                                if isinstance(b, dict)]
                if len(raw_beats) > MAX_BEATS_DAY:
                    row['notes'].append(f'另有 {len(raw_beats) - MAX_BEATS_DAY} 拍未收录')
            raw_shots = rec.get('shots') or []
            if isinstance(raw_shots, list):
                row['shots'] = [_shot_row(s) for s in raw_shots[:MAX_SHOTS_DAY]
                                if isinstance(s, dict)]
                if len(raw_shots) > MAX_SHOTS_DAY:
                    row['notes'].append(f'另有 {len(raw_shots) - MAX_SHOTS_DAY} 镜未收录')
            story = str(rec.get('story') or '').strip()
            if story:
                paras = [x.strip() for x in _PARA_SEP.split(story) if x.strip()]
                # ⚠ 先记原数再截断：先截断再算差，`len(paras) - MAX` 恒为负数/零
                #   （实测报出"正文另有 0 段未收录"——注释在说谎，而看起来正常）。
                # [EN] Record the original count *before* truncating: computing the difference
                # [EN] afterwards makes `len(paras) - MAX` zero or negative (measured: the note
                # [EN] claimed "0 more paragraphs omitted", i.e. a note that lies while looking fine).
                n_all = len(paras)
                if n_all > MAX_STORY_PARAS:
                    paras = paras[:MAX_STORY_PARAS]
                    row['notes'].append(f'正文另有 {n_all - MAX_STORY_PARAS} 段未收录')
                row['story'] = paras
            probs = rec.get('problems') or []
            if isinstance(probs, list):
                row['notes'].extend(_clip(str(p), 160) for p in probs[:6] if str(p).strip())
        out_days.append(row)

    # 转折点排序：**转折**在关键之前（同一天内保持时间顺序，`sorted` 是稳定的）
    turns.sort(key=lambda m: (int(m.get('day') or 0), 0 if m.get('kind') == MARK_TURN else 1))
    return {
        'schema': 1,
        'days': out_days,
        'turns': turns,
        'stats': {
            'days': len(out_days),
            'turns': sum(1 for m in turns if m.get('kind') == MARK_TURN),
            'keys': sum(1 for m in turns if m.get('kind') == MARK_KEY),
            'beats': sum(len(d.get('beats') or []) for d in out_days),
            'shots': sum(len(d.get('shots') or []) for d in out_days),
            'chars': sum(len(''.join(d.get('story') or [])) for d in out_days),
        },
    }


def _synopsis(project_dir: Path) -> str:
    """这段故事「到目前为止」的一段话概要（**读现成的，不让模型写**）。

    优先 `设定集/已发生故事线.md` 的 `## 前情提要`（那是真的已经发生的），
    没有就退回 `设定集/剧情走向.md` 的第一段（起承转合）。都没有就空串。
    [EN] A paragraph of "the story so far" (**read an existing one, never ask a model**). Prefers the
    `## 前情提要` section of `已发生故事线.md` (what actually happened), otherwise the first paragraph
    of `剧情走向.md`, otherwise empty.
    """
    sd = project_dir / '设定集'
    p = sd / '已发生故事线.md'
    if p.is_file():
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            text = ''
        m = re.search(r'(?m)^##\s*前情提要\s*$(.*?)(?=^##\s|\Z)', text, re.S)
        seg = (m.group(1) if m else '').strip()
        if seg:
            return _clip(seg, 400)
    q = sd / '剧情走向.md'
    if q.is_file():
        try:
            seg = q.read_text(encoding='utf-8', errors='ignore').strip()
        except OSError:
            seg = ''
        seg = re.sub(r'^#.*$', '', seg, count=1, flags=re.M).strip()
        for para in re.split(r'\n\s*\n', seg):
            if para.strip():
                return _clip(para.strip(), 400)
    return ''


def _clip(text: str, n: int) -> str:
    s = re.sub(r'\s+', ' ', str(text or '')).strip()
    return s if len(s) <= n else s[:n].rstrip() + '…'


def _evidence_of(name: str, days: list[dict]) -> tuple[list[int], int]:
    """这一站在这次推演里的**实据**：演过的天号 + 幕数。没演过就是 `([], 0)`。

    ★ 存**数字**、不存排好版的句子（"第 1 天 · 11 幕"）：这个文件是数据，
      而"第 N 天"在英文界面里要说 `day 3`。把中文句子写进 JSON，等于把生成那一刻
      的语言冻进盘里 —— 之后切英文，图上还是中文（`verify_ui_english` 当场红）。
      ⇒ 排版交给界面（`gui.story_flow_dialog.detail_text`），数据只给数。
    ★ 这一行是"流程图说的和正文对得上"的唯一凭据 —— 没有它，用户没法核对
      "你说演过了，演了多少？"（导出里那句"按事件装订"是同一个思路）。
    [EN] The **evidence** for this station in this run: the day numbers plus the scene count;
    `([], 0)` when unplayed. ★ Stores **numbers**, not a formatted sentence ("day 1 · 11 scenes"):
    this file is data, and "第 N 天" must read "day 3" in English. Baking a Chinese sentence into the
    JSON freezes the generation-time language onto disk. So formatting belongs to the UI
    (`gui.story_flow_dialog.detail_text`). ★ This line is the only thing tying the chart to the prose;
    without it the user cannot check "you say it was played, how much of it?".
    """
    hit = [d for d in days if name in d.get('nodes', [])]
    if not hit:
        return [], 0
    nums = sorted({int(d['day']) for d in hit})
    scenes = sum(int(d.get('node_counts', {}).get(name, 0)) for d in hit)
    return nums, scenes


def build_flow(project_dir, run_root, *, picks: dict | None = None) -> dict:
    """拼出这一次推演的剧情总览（**纯函数**：只读盘，不写、不调模型）。

    返回的结构（`SCHEMA` = 1）：

    ```
    {schema, run, project, generated_at, synopsis, stats,
     days: [{day, scenes, from, to, nodes}],
     points: [{pid, node, title, summary, criteria, state, played, days, scenes,
               unplayed_done, kind: 'plot'|'choice',
               options: [{label, points}], options_inferred: bool}],
     picks: {pid: label},
     tail: '' | 'no_table' | 'nothing_played'}
    ```

    ★ `state` 的判法（顺序要紧）：
      ① 设定集标了**已完成**且这次演过 ⇒ `done`（"完成判据达到了"是比"是不是最后一站"更硬的凭据）；
      ② 是**最后一幕**所在的那一站 ⇒ `now`；
      ③ 这次演过 ⇒ `done`；④ 其余 ⇒ `todo`。
      ⚠ 只按"最后一幕"判会把已经收尾的一站永远画成"正在演"（用户会以为推演没往前走）。
    [EN] Assemble this run's overview (a **pure function**: reads disk, never writes, never calls a
    model). ★ `state` order matters: ① project status is 已完成 and it was played here => `done`
    (the completion criterion is a harder signal than "is it the last station"); ② it holds the last
    scene => `now`; ③ played here => `done`; ④ otherwise `todo`. ⚠ Judging only by "last scene" would
    paint a finished station as "currently playing" forever.
    """
    project_dir = Path(project_dir)
    run_root = Path(run_root)
    nodes = read_nodes(project_dir / '设定集')
    days = scan_days(run_root)

    seen: list[str] = []
    for d in days:
        for nm in d['nodes']:
            if nm not in seen:
                seen.append(nm)
    last = days[-1].get('last_node', '') if days else ''

    points: list[dict] = []
    for i, n in enumerate(nodes, 1):
        nm = n['name']
        if not nm:
            continue
        played = nm in seen
        if played and n['status'] == '已完成':
            state = STATE_DONE
        elif last and nm == last:
            state = STATE_NOW
        elif played:
            state = STATE_DONE
        else:
            state = STATE_TODO
        opts, inferred = choice_options(n)
        ev_days, ev_scenes = _evidence_of(nm, days)
        # 设定集说它完了、而这次推演没演到 —— 照实记一个标记，别让人以为这次演过。
        # ⚠ 记**标记**不记那句中文：见 `_evidence_of` 的说明（数据里不许冻语言）。
        # [EN] The project says it is done but this run never played it -- record a flag instead of a
        # [EN] Chinese sentence (see `_evidence_of`: no frozen language in the data).
        unplayed_done = bool(not played and n['status'] == '已完成')
        points.append({
            'pid': f'P{i:02d}',
            'node': n['id'],
            'title': nm,
            'summary': n['summary'] or n['criteria'],
            'criteria': n['criteria'],
            'state': state,
            'played': played,
            'days': ev_days,
            'scenes': ev_scenes,
            'unplayed_done': unplayed_done,
            'kind': 'choice' if opts else 'plot',
            'options': opts,
            'options_inferred': bool(inferred),
            'span': n['span'],
            'weight': n['weight'],
        })

    stats = {
        'days': len(days),
        'scenes': sum(int(d.get('scenes', 0)) for d in days),
        'points': len(points),
        'played': len(seen),
        'choices': sum(1 for p in points if p['kind'] == 'choice'),
    }
    # 结尾那句话给**代码**，不给句子（理由同上：这个文件会被英文界面读）。
    # 取值：'' / 'no_table'（没有情节表）/ 'nothing_played'（一站都还没演到）
    # [EN] The closing line is a **code**, not a sentence (same reason: an English UI reads this
    # [EN] file). Values: '' / 'no_table' / 'nothing_played'.
    if not points:
        tail = 'no_table'
    elif any(p['state'] in (STATE_NOW, STATE_DONE) for p in points):
        tail = ''
    else:
        tail = 'nothing_played'
    # ★★★ 2026-10-26（用户：「剧情总览太简略了 我希望是每次推演里面的细节剧情
    #   要很详细（到达每次剧作家写小段剧情的程度）要包含当前这次推演的
    #   关键剧情和转折点」）：**详细层与流程层同一份文件、同一次生成**。
    #   为什么不另开一个 `剧情详情.json`：两层说的是**同一件事**（这次推演发生了什么），
    #   分成两个文件就必然出现"流程图说有 3 天、详情只有 2 天"，而这种不一致
    #   用户一眼就会看到，而且不报错。
    # [EN] ★★★ 2026-10-26 (the user: "the overview is too brief; I want the detailed story of each
    # [EN] run, down to the small segments the playwright writes, including this run's key plot and
    # [EN] turning points"): **the detail layer lives in the same file and the same build as the
    # [EN] flow layer**. Why not a separate `剧情详情.json`: both describe **the same thing** (what
    # [EN] happened in this run), and two files inevitably produce "the flow chart says 3 days, the
    # [EN] detail only has 2" -- an inconsistency the user spots instantly, with no error anywhere.
    detail = scan_detail(project_dir, run_root, days=days)
    stats['turns'] = int((detail.get('stats') or {}).get('turns') or 0)
    stats['keys'] = int((detail.get('stats') or {}).get('keys') or 0)
    stats['beats'] = int((detail.get('stats') or {}).get('beats') or 0)
    stats['story_chars'] = int((detail.get('stats') or {}).get('chars') or 0)
    return {
        'schema': SCHEMA,
        'run': run_root.name,
        'project': project_dir.name,
        'generated_at': _now(),
        'synopsis': _synopsis(project_dir),
        'stats': stats,
        'days': [{k: d[k] for k in ('day', 'scenes', 'from', 'to', 'nodes')} for d in days],
        'points': points,
        'picks': dict(picks or {}),
        'tail': tail,
        'detail': detail,
    }


# ══════════════════════════════════════════════════════════════
#  存 / 取
# [EN] Save / load
# ══════════════════════════════════════════════════════════════
def load_flow(run_root) -> dict | None:
    """读盘上那份（坏了/没有 → `None`，**不抛**）。"""
    p = flow_path(run_root)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except Exception:                                            # noqa: BLE001
        return None
    if not isinstance(data, dict) or not isinstance(data.get('points'), list):
        return None
    if int(data.get('schema') or 0) > SCHEMA:
        # 更新的软件写的文件：**不猜**它能读，当作没有（会重算一份 SCHEMA 版本）。
        # [EN] Written by a newer build: don't guess, treat as absent (a SCHEMA copy gets rebuilt).
        return None
    data.setdefault('picks', {})
    return data


def save_flow(run_root, data: dict) -> Path:
    """落盘。**先写临时文件再替换** —— 中断时不会留下半截 JSON。"""
    p = flow_path(run_root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
        tmp.replace(p)
    except OSError:
        pass
    return p


def _source_mtimes(project_dir: Path, run_root: Path) -> list[float]:
    """会影响剧情总览的那几个文件的修改时间。"""
    out: list[float] = []
    # ★ 2026-10-26：`当日剧本.json`（剧作家底稿）**必须算进来** —— 详细剧情那一层
    #   的分拍与正文全从它来。漏了它的后果是"剧作家刚写的那一天，总览里还是旧的"，
    #   而且**看起来完全正常**（有内容，只是少一天）。
    # [EN] ★ 2026-10-26: `当日剧本.json` (the playwright's draft) **must be included** -- the
    # [EN] beats and prose of the detail layer come from it. Missing it means "the day the
    # [EN] playwright just wrote still shows the old version", and it **looks perfectly fine**
    # [EN] (there is content, just one day short).
    cands = [Path(run_root) / '停点.json', Path(run_root) / '每天的生活',
             Path(run_root) / _SCRIPT_CACHE]
    for nm in _PROGRESS_NAMES:
        cands.append(Path(project_dir) / '设定集' / nm)
    for c in cands:
        try:
            if c.exists():
                out.append(c.stat().st_mtime)
        except OSError:
            pass
    try:
        for f in (Path(run_root) / '每天的生活').glob('*.json'):
            out.append(f.stat().st_mtime)
    except OSError:
        pass
    return out


def is_stale(project_dir, run_root) -> bool:
    """盘上的剧情总览比素材旧了吗（旧了就该重算）。

    ⚠ 留 1 秒余量：`save_flow` 与"同一次落盘里的当天 json"经常同一秒内完成，
      不留给余量会每次打开都重算（重算本身很便宜，但会覆盖 `generated_at`，
      界面上那句"更新于"就一直跳）。
    [EN] Is the file on disk older than its sources? ⚠ One second of slack: `save_flow` and that
    day's json often land in the same second, and without slack every open would recompute (cheap,
    but it overwrites `generated_at`, so the "updated at" line keeps jumping).
    """
    p = flow_path(run_root)
    if not p.is_file():
        return True
    try:
        mine = p.stat().st_mtime
    except OSError:
        return True
    return any(m > mine + 1.0 for m in _source_mtimes(Path(project_dir), Path(run_root)))


def ensure_flow(project_dir, run_root, *, force: bool = False) -> dict:
    """**拿到一份能用的剧情总览**：有且不旧就直接用，否则重算并落盘。

    ★ 这是产品里唯一的入口（对话框打开、日界自动刷新、回填脚本都走它）：
      "什么时候该重算"只在一处判 —— 两处各判一次，必然出现"界面这张旧、
      盘上那份新"（图片那条路上踩过：`_sync_day_map` 的根因）。

    ★★★ **重算不覆盖用户选过的分支**：`picks` 从旧文件里带过来。
      选项是"你自己选的路线"，不是算出来的东西 —— 重算把它清了，
      表现就是"我点过的分支，过一天又变回没选"，用户会以为选择没生效。
    [EN] **Get a usable overview**: reuse it when fresh, otherwise recompute and save. ★ The only
    entry point in the product (dialog open, day-boundary refresh, backfill all go through it), so
    "when to recompute" is decided in one place. ★★★ **Recomputing never overwrites the user's
    branch picks** -- picks are "the route you chose", not a computed value; clearing them would look
    like the choice never took effect.
    """
    run_root = Path(run_root)
    data = None if force else load_flow(run_root)
    if data is not None and not is_stale(project_dir, run_root):
        # 素材没变：直接用它，但把 `picks` 传下去（调用方可能刚改过）。
        # [EN] Sources unchanged: reuse it, keeping picks from the caller.
        return data
    picks = dict((data or {}).get('picks') or {})
    fresh = build_flow(project_dir, run_root, picks=picks)
    save_flow(run_root, fresh)
    return fresh


# ══════════════════════════════════════════════════════════════
#  选择（多选 → 从选中的那条线继续）
# [EN] Choices (pick one, continue down that line)
# ══════════════════════════════════════════════════════════════
def pick_of(data: dict, pid: str) -> str:
    """这一站选了哪条线（没选 → 空串）。"""
    return str(((data or {}).get('picks') or {}).get(str(pid)) or '')


def set_pick(data: dict, pid: str, label: str) -> dict:
    """记下选择（`label` 为空 = 取消）。**纯函数**：改的是传进来的那一份。

    ⚠ 只认这一站**真的有**的选项：点了个不存在的标签多半是旧数据/错位，
      记下来会让流程图显示一条没有内容的线。
    [EN] Record a pick (`label` empty = clear). ⚠ Only labels this station actually offers: recording
    a stale/mismatched label would render a line with nothing in it.
    """
    if not isinstance(data, dict):
        return data
    pid = str(pid)
    pts = [p for p in (data.get('points') or []) if str(p.get('pid')) == pid]
    labels = [str(o.get('label') or '') for o in ((pts[0].get('options') if pts else []) or [])]
    picks = dict(data.get('picks') or {})
    if not label:
        picks.pop(pid, None)
    elif label in labels:
        picks[pid] = label
    data['picks'] = picks
    return data


def branch_points_of(point: dict, label: str) -> list[dict]:
    """选中的那条线**后面还有哪些情节**（数据里没写就是空表 → 界面说"还没演到"）。

    ★ 这就是"从用户选择的剧情继续流程"的数据面：选项可以在设定集里带 `后续:`
      （`[{名称, 概要}, …]`），流程图会在选中那条线下面把它们接上去。
      老项目没有 `后续:`，那就是空 —— **不编结局**。
    [EN] Which plot points follow the chosen line (empty when the data has none => the UI says "not
    played yet"). ★ This is the data side of "continue from the chosen branch": an option may carry
    `后续:` in the setting bible, and the chart renders them under the picked line. Old projects have
    none => empty -- **never invent an ending**.
    """
    for o in (point.get('options') or []):
        if str(o.get('label') or '') == str(label or ''):
            return [p for p in (o.get('points') or []) if isinstance(p, dict)]
    return []


def list_runs(project_dir) -> list[Path]:
    """这个项目下所有推演文件夹（按序号升序）。

    ⚠ 走 `store.project.list_run_dirs`：**拾卷、剧情总览、回填脚本必须是同一个顺序**，
      三处各排一次必然出"跑马灯的顺序和列表不一样"。
    [EN] All run folders of this project, ascending by index. ⚠ Delegates to
    `store.project.list_run_dirs`: Pickup, the overview and the backfill script must share one order.
    """
    from store.project import list_run_dirs
    return list_run_dirs(Path(project_dir))
