# -*- coding: utf-8 -*-
"""把"一站里串了好几件事"的进度节点**拆成一站一件事**。

为什么要有这个模块
------------------
用户 2026-10-21：「运行界面右上角的剧情的进度表一直不动 你看下是有问题 还是确实没有变动」。

查下来的结论是**判据确实没满足**（那一天评估了 14 次、模型每次都答了，7 次结论全 false），
而卡住的原因在产品结构里：`director/engine.py` 的判定口径明确写着

    · 判据里说的要是**一串**事，**只做到其中一件就是没满足** —— 必须**全部**做到

那句本身是对的（2026-10-14 加它，就是为了治「第一天就想把谜底解开」）。
问题在于**生成进度表时允许一站捆四件事** —— 于是"必须全部做到"变成"几乎永远做不到"：

    实测（某项目 N01 的判据）：
      「阿九完成多站委托，发现旧账署名线索，听老陈讲古知楼重走环线。」
    日志显示：署名线索 ✅ 听讲古 ✅ —— 只卡在"多站委托"。而这一站**必须四件全做**才推进。
    ⇒ 进度表在界面上永远是 0/4。

用户要的方向是「拆判据」：**一站一件事**。这样"必须全部做到"只针对一件事，
每一步都走得动，进度表才有意义。

怎么拆（规则是通用的，不含任何一部作品的专名）
------------------------------------------------
★ 不靠 LLM：装配（`sim/setup.py`）时也要能拆，那里不能联网、不能等模型。
★ 也不靠"数动词"：中文动宾结构没有可靠的字面判据（这个项目反复量过，
  凡是"吃自由文本"的判据最后都会漏）。⇒ 只用**三个可数的、保守的条件**：

  1. **分隔符**：`、` `；` `;` `，` `,` —— 顿号/分号几乎必然并列；逗号可能是修饰，
     所以再叠下面两条把它挡掉一部分；
  2. **原判据够长**（去空白 ≥ `_MIN_WHOLE` 字）：短判据里的逗号多半是修饰，
     不是并列（例：「两人对峙，气氛紧张」10 字 ⇒ 不拆）；
  3. **每一段都够长**（≥ `_MIN_PART` 字）：挡住「之后，」「一边，」这种半句碎片。

★ 还有一条**硬上限** `_MAX_NODES`：拆完总节点数不能超。
  不设限的话，一份"每站都写了四件事"的进度表会炸成二十几站，
  界面列不下、模型也更容易迷路 —— 宁可少拆几站，别把表炸掉。

⚠ 拆出来的每一站都**继承原站的「状态」**：原来标了 `已完成` 的整站，
  拆开之后每一段都是 `已完成`（不继承的话，走完的站会变回"未开始"，进度倒退）。
⚠ 只在**内存里**拆，**不写回** `故事进度.yaml`：那是作者的设定集，
  产品不该悄悄改它。想看原始的四站，打开那份文件即可；
  界面上把鼠标放在节点上会说明"由「原名」拆出"（见 `gui/app_flet.py` 的 tooltip）。

English
-------
Split progress nodes whose completion criterion packs several separate tasks into one station.

Why: the criterion pack (see `director/engine.py`) explicitly says "if the criterion names a **series**
of things, doing only one of them is not enough -- **all** must be done". That rule is correct (it was
added to stop the story from racing ahead), but progress-table generation allowed one station to carry
four tasks, so "all must be done" became "almost never achievable". Measured on one project: the N01
criterion listed four tasks; the logs showed two of them already happened, and the station could never
advance => the progress table sat at 0/4 forever.

The user's chosen direction is "split the criteria": **one station, one task**. Then "all must be done"
applies to a single task and every step can actually move.

Rules are generic -- no proper nouns from any work of fiction:
★ No LLM: splitting must also work at assembly time (`sim/setup.py`), which is offline.
★ No "count the verbs": Chinese verb-object structure has no reliable literal test (measured repeatedly
  in this project; anything that eats free text ends up leaking). So only **three countable, conservative**
  conditions: separators (`、；;，,`), the whole criterion is long enough (`_MIN_WHOLE`), and every part is
  long enough (`_MIN_PART`).
★ A hard cap `_MAX_NODES`: without it a table where every station lists four tasks explodes into
  twenty-odd stations -- the UI cannot list them and the model gets lost.
⚠ Every split part **inherits the station's 状态**: a station marked done stays done after splitting
  (otherwise finished progress would rewind).
⚠ Splitting happens **in memory only** and is **never written back** to `故事进度.yaml`: that file is the
  author's setting document and the product must not silently edit it.
"""
from __future__ import annotations

import re

#: 并列分隔 —— 顿号/分号几乎必然并列；逗号可能是修饰，靠下面两条长度条件挡。
# [EN] Coordination separators -- the enumeration comma / semicolon are almost always coordination; the
# [EN] regular comma may be a modifier, held back by the two length conditions below.
_SPLIT_RE = re.compile(r'[、；;，,]')

#: 原判据（去空白）至少要这么长才考虑拆。短判据里的逗号多半是修饰。
# [EN] The whole criterion (whitespace stripped) must be at least this long to be considered; in short
# [EN] criteria a comma is usually a modifier.
_MIN_WHOLE = 14

#: 拆出来的每一段至少要这么长（挡「之后，」「一边，」这类半句碎片）。
# [EN] Every split part must be at least this long (blocks fragments like "之后，").
_MIN_PART = 5

#: 一份进度表的**总节点数上限**（原表已经这么长就不再拆）。
# [EN] Hard cap on total nodes per table (no splitting once the table is already this long).
_MAX_NODES = 12

#: 拆开后给站名加的后缀。
#:
#: ★ 2026-10-21：原来只有 ①②③④ 四个（"最多拆 4 段"）。但那实际上是**拿标记数量
#:   当成了段数上限** —— 一句里并了 5 件事的判据就整句不拆（保留原样），
#:   于是那一站**永远卡着**，正是这次要治的病。
#:   ⇒ 扩到 9 个：真正控总量的是 `_MAX_NODES`（拆完总站数），段数只要一个"别无限切"的保险。
#:   ⚠ 标记数就是段数上限（代码里 `2 <= len(parts) <= len(_MARKS)`）。
#:     再多也不该拆 —— 一句判据里并了十件事，说明这句本身就不成形，
#:     硬切只会切出十几个连作者都看不懂的碎片。
# [EN] ★ 2026-10-21: it used to be just ①②③④ ("split at most 4 ways"), but that was really
# [EN] **using the number of marks as the part cap** -- a criterion naming five tasks was left whole,
# [EN] so that station stayed **stuck forever**, which is exactly the disease being treated here.
# [EN] => Extended to 9: total size is controlled by `_MAX_NODES` (final station count), and the part
# [EN] count only needs a "don't split forever" guard.
# [EN] ⚠ The number of marks IS the part cap (the code checks `2 <= len(parts) <= len(_MARKS)`).
# [EN] Beyond that it should not split -- a criterion packing ten tasks is not a well-formed criterion,
# [EN] and forcing a split only yields fragments no author can read.
_MARKS = '①②③④⑤⑥⑦⑧⑨'


def split_criteria_text(text: str) -> list[str]:
    """把一句"串了好几件事"的判据切成几段；**切不动就原样返回一段**。

    ★ 只做**保守**切分：三个条件（长度、段数、每段长度）任一不满足就原样返回。
      宁可漏拆，不可乱拆 —— 乱拆会切出"气氛紧张"这种永远满足不了的假站，
      那比卡在原来那一站更糟。

        English:
    Split a criterion that names several tasks; **return it as a single part when it cannot be split
    cleanly**. Only conservative splitting: if any of the three conditions fails, return it unchanged.
    Better to under-split than to split wrongly -- a wrong split produces a fake station that can never
    be satisfied, which is worse than being stuck at the original one.
    """
    whole = str(text or '').strip()
    if not whole:
        return [whole]
    core = re.sub(r'\s+', '', whole)
    if len(core) < _MIN_WHOLE:
        return [whole]
    parts = [p.strip() for p in _SPLIT_RE.split(whole)]
    # 段尾的句号/逗号去掉：原句只有一个句号落在最后一段，拆开后会出现
    # 「①一件事 ②一件事 ③一件事。」这种不一致 —— 每段都当独立判据看，不该带句末符号。
    # [EN] Strip trailing full stops from each part: the original sentence has one period on its last
    # [EN] part, and after splitting you get "① … ② … ③ …。" -- each part is an independent criterion,
    # [EN] so it should not carry sentence-final punctuation.
    parts = [p.strip().rstrip('。．.') for p in parts]
    parts = [p for p in parts if p]
    # 段数要 ≥2（否则没有并列），且不超过 4（再多说明这句判据本身不成形）
    if not (2 <= len(parts) <= len(_MARKS)):
        return [whole]
    # 每一段都要够长
    if any(len(re.sub(r'\s+', '', p)) < _MIN_PART for p in parts):
        return [whole]
    return parts


def split_fat_nodes(nodes: list[dict], *, log=None) -> tuple[list[dict], int]:
    """把一份进度表里"一站捆多件"的节点拆开；返回 `(新表, 拆出的站数)`。

    ★ **不改传入的列表**（返回新表，元素也是新 dict）：调用方可能还在用原表
      （`sim/setup.py` 里 `settings["nodes"]` 后面还有别的用途）。
    ★ id 全部**重排**成 `N01..Nxx`：拆开之后原 id 不再连续，留着会在
      "当前节点 / 已完成判断 / 界面清单"三处各出各的问题（本项目对 id 的依赖不浅）。
    ★ 原来标了 `已完成` 的站，拆开后每一段都是 `已完成`（否则进度倒退）。
    ★ 拆出来的段带一个内部标记 `_拆自`（原站名）：只给界面写 tooltip 用，
      **不参与任何逻辑判断，也不落盘**。

        English:
    Split this table's multi-task nodes; returns `(new table, number of stations created by splitting)`.
    ★ **Does not mutate the argument** (returns a new list of new dicts).
    ★ All ids are **renumbered** `N01..Nxx`.
    ★ A station marked done yields parts that are all done (otherwise progress would rewind).
    ★ Split parts carry an internal `_拆自` marker (the original station name) used only for the UI
      tooltip: **no logic reads it and it is never persisted**.
    """
    src = [nd for nd in (nodes or []) if isinstance(nd, dict)]
    if not src:
        return [], 0
    budget = max(0, _MAX_NODES - len(src))
    out: list[dict] = []
    created = 0
    for nd in src:
        crit = str(nd.get('完成判据') or nd.get('criteria') or '')
        parts = split_criteria_text(crit)
        # 名额不够就整站保留（宁可这一站粗一点，也别把表炸到列不下）
        if len(parts) < 2 or budget < len(parts) - 1:
            out.append(dict(nd))
            continue
        budget -= len(parts) - 1
        created += len(parts) - 1
        name = str(nd.get('名称') or nd.get('name') or '').strip() or '—'
        status = str(nd.get('状态') or '').strip()
        for i, part in enumerate(parts):
            piece = dict(nd)
            piece['名称'] = f'{name}{_MARKS[i]}' if len(parts) > 1 else name
            piece['完成判据'] = part
            # 状态继承：整站走完了，每一段都走完了
            piece['状态'] = status
            piece['_拆自'] = name
            out.append(piece)
        if log is not None:
            log('进度表：站「%s」的判据串了 %d 件事 → 拆成 %d 站（%s）',
                name, len(parts), len(parts), ' / '.join(
                    p[:12] + ('…' if len(p) > 12 else '') for p in parts))
    for i, nd in enumerate(out):
        nd['id'] = f'N{i + 1:02d}'
    return out, created
