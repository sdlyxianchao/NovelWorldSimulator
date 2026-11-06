# -*- coding: utf-8 -*-
"""逻辑验证：**一天 4.4 万字的戏，不能导出成 1 千字**（2026-10-17）。

用户原话：
    「为何发生给你了很多事情 最后导出的内容非常少？剧情部分呢？人物对话呢？
      导出的应该是一个经过润色的完整的小说才对」

### 实测到的四层流失（同一天，第 1 天）

| 环节 | 大小 | 怎么丢的 |
|---|---|---|
| `每天的生活/第001天.md`（落盘） | **44,736 字** | — |
| 喂给「整理成小说」的材料 | **5 行**（日志实测 1,723 token 入） | `_day_lines()` 里 `if not lines and groups:` —— `_daily_narrative` 有 1 行就不展开 30 幕剧本 |
| 「当天故事.md」这一章 | **917 字** | 输入只有 5 行 + `raw[:6000]` 截断 + `max_tokens=2600`；模型输出 **79 token** |
| 《小说版本》导出 | **1,185 字** | `render_manuscript` 用那 917 字**整份替换**了 43,648 字的可读材料 |
| 点「润色」后 | **918 字** | 润色提示词是「只做整理，不新增情节」⇒ 越润越短 |

用户看到的就是最后那两个数字。

### 判据（全部是**行为级**，用真实的一份一天材料跑）

  A **`_day_lines()` 必须用完整的一天**：给 30 幕 + 一个几乎是空的
    `_daily_narrative`，产出必须接近 30 幕摊开的行数，**不能只有那几行**；
    同时**成对**判：`scenes` 为空时仍然照用 `_daily_narrative`（别一刀切）。
  B **分块**：4.4 万字要切成多块、每块 ≤ 上限、**每块都不为空**、
    且**合起来不丢材料**（切块的目的是写完整，不是丢内容）。
  C **输出预算跟材料走**：材料 3,600 字时 `max_tokens` 必须 > 材料长度的一半
    （实测 2,600 正好卡住，再多一点就截断）。
  D **导出不许被残稿覆盖**：整理稿 917 字 vs 材料 43,670 字时，
    `render_manuscript` 必须**保住材料**（并且如实说明），不能输出 1,185 字。
  E **行内元标记要剃掉**：`〔aside·丁〕` / `〔dialogue·X〕` 实测一天 132 处，
    留着读起来是文件格式不是小说；但**转场标记必须留**（`〔切至 …〕`）。

跑法：.venv\\Scripts\\python.exe tools/verify_novel_fullness.py
产出：assets/screenshots/novel_fullness_report.json

English:
Logic verification: **a day of 44k characters must not export as 1k** (2026-10-17).
User's exact words: "why is the exported content so little? Where is the plot? Where is the dialogue?
The export should be a polished, complete novel."
### The four layers of loss actually measured (same day, day 1)
| Stage | Size | How it got lost |
| `每天的生活/第001天.md` (persisted) | **44,736 chars** | — |
| material fed to "organize into a novel" | **5 lines** (log: 1,723 input tokens) | `if not lines and groups:` in `_day_lines()` -- one line in `_daily_narrative` and the 30 scenes are never expanded |
| "当天故事.md" chapter | **917 chars** | only 5 lines of input + `raw[:6000]` truncation + `max_tokens=2600`; the model emitted **79 tokens** |
| "小说版本" export | **1,185 chars** | `render_manuscript` replaced 43,648 chars of readable material with those 917 |
| after clicking "polish" | **918 chars** | the polish prompt says "only tidy, never add plot" => it only gets shorter |
The user saw those last two numbers.
### Criteria (all **behavioral**, run against one real day of material)
  A **`_day_lines()` must use the whole day**: given 30 scenes plus an almost-empty
    `_daily_narrative`, the output must be close to the expanded 30 scenes, **not just those few
    lines**; paired check: when `scenes` is empty it must still use `_daily_narrative`.
  B **Chunking**: 44k characters must split into several chunks, each ≤ the limit, **none empty**,
    and **together not losing material** (the point of chunking is to write it fully, not to drop it).
  C **Output budget follows the material**: with 3,600 characters of material `max_tokens` must be
    more than half the material length (2,600 hit the cap in practice).
  D **The export must not be overwritten by a crippled draft**: with a 917-char draft against 43,670
    chars of material, `render_manuscript` must **keep the material** (and say so), not emit 1,185.
  E **Inline markers must be stripped**: `〔aside·X〕` / `〔dialogue·X〕` occurred 132 times in one
    day; leaving them in reads like a file format, not a novel. But **transition markers must stay**
    (`〔切至 …〕`).
How to run: .venv\\Scripts\\python.exe tools/verify_novel_fullness.py
Output: assets/screenshots/novel_fullness_report.json
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                         # noqa: E402
import verify_ui_common as VU                                  # noqa: E402
VU.redirect_env_writes()
CFG.set('MOCK_LLM', 'true')

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  夹具：造一个 30 幕、4 万字量级的一天（与真实材料同构）
# [EN] Fixture: one day of 30 scenes at roughly 40k characters (same shape as real material)
# ══════════════════════════════════════════════════════════════
_ENV = '茶炉顶盖噗噗轻跳，案上水汽不散；布巾离壶，壶底磕案面一下'


class _Entry:
    def __init__(self, kind: str, who: str, text: str):
        self.kind = kind
        self.who = who
        self.text = text


class _Scene:
    """夹具幕 —— **字段必须跟真实 `S.SceneScript` 对齐**。

    ⚠ 2026-10-19 第六轮补 `time_label` / `place` / `node_name`。
      原来只有 `entries`，于是"每一幕有没有时间"这件事在这个夹具里
      **根本不存在** ⇒ 幕头判据怎么写都是绿（`getattr` 取不到就空串）。
      这正是本项目记过的「`getattr(obj,'字段',默认)` 让'字段不存在'不可见」。
    [EN] Fixture scene -- **fields must match the real `S.SceneScript`**. Added `time_label` /
    [EN] `place` / `node_name` in round six: with only `entries`, "does each act carry a time"
    [EN] simply did not exist in this fixture, so any header criterion stayed green.
    """

    def __init__(self, entries, time_label: str = '', place: str = '',
                 node_name: str = ''):
        self.entries = entries
        self.time_label = time_label
        self.place = place
        self.node_name = node_name


def make_day_scenes(n_scenes: int = 30) -> list:
    """造 `n_scenes` 幕，规模对齐**真实材料**。

    实测第 1 天：30 幕 / 208 动作 / 275 心声 / 74 对白 / 150 环境，
    合计 **44,736 字符**。这里每幕给 7 条（2 动作 + 2 心声 + 1 对白 + 2 环境）
    = 210 条，单条 100-200 字，总量落在 3 万字量级。

    ⚠ **每条内容都必须唯一**：`export._fold_repeats` 会把"同一句反复"折掉，
      夹具要是复制粘贴出来的，量出来的材料量会被它吃掉一半（第一版就栽在这儿：
      60 条一样的动作被折成 1 条，D 组全假红）。

        English:
    Build `n_scenes` scenes, scaled to the **real material**.
        Measured day 1: 30 scenes / 208 actions / 275 thoughts / 74 dialogue / 150 ambient =
        **44,736 characters**. Here each scene gives 7 entries (2 actions + 2 thoughts + 1 dialogue +
        2 ambient) = 210 entries, 100-200 characters each, totalling ~30k characters.
        ⚠ **Every entry must be unique**: `export._fold_repeats` folds "the same sentence repeated",
          so a copy-pasted fixture gets half its material eaten (the first version died here: 60
          identical actions folded into 1, and all of group D went false red).
    """
    scenes = []
    _SHICHEN = ('子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥')
    for i in range(n_scenes):
        entries = [
            # ★ 每幕开头那行场景标题**必须有**：真实材料长这样
            #   （`## 辰时 08:00`），而 `_split_for_transcribe` 就是**按它断开**的。
            #   夹具少了它，B5（"尽量在场景边界断开"）会假红。
            # [EN] ★ The scene heading line **must be there**: the real material looks like this
            # [EN] (`## 辰时 08:00`), and `_split_for_transcribe` breaks **on it**. Without it in the
            # [EN] fixture, B5 ("break on scene boundaries") goes false red.
            _Entry('scene', '', f'{_SHICHEN[i % 12]}时 {(i % 12) * 2 + 6:02d}:00'),
            _Entry('action', '掌柜甲',
                   f'第{i}幕：站在柜台后，布头绕壶身一圈圈蹭过去，眼睛半垂着，'
                   f'没往客人乙那边看一眼，指节在壶盖上停了第{i}下又移开，'
                   f'壶底磕在柜台木面上响了一声轻的，随后又绕回壶腹'),
            _Entry('action', '客人乙',
                   f'第{i}幕：拿抹布蹭桌面的木纹，从东头一直蹭到西头，'
                   f'走到第{i}圈时手忽然停了，指头在桌沿上摹了一下字的拐弯，'
                   f'摹完自己愣了一下，又低头接着擦'),
            _Entry('aside', '客人乙',
                   f'第{i}幕：这笔锋太像了，像我梦里头写自己名字的手感，'
                   f'可他明明失忆前不会这手，为什么第{i}次看见还是觉得熟，'
                   f'熟得心里发紧，一句话也不敢问出口'),
            _Entry('aside', '丁',
                   f'第{i}幕：账角露着，绕圈记的账迟早碰上，傻子账上不糊涂，'
                   f'这一笔我记到第{i}页了，等他自个儿觉出来，比我说破强'),
            _Entry('dialogue', '丁',
                   f'楼走的就是个圈，前头站过的地方后头还得站回去，'
                   f'你信不信第{i}桩事还会回来，回来了你别装着不认得。'),
            _Entry('ambient', '', f'{_ENV}，第{i}声该响而没响，屋里静得能听见瓦上的水'),
            _Entry('ambient', '', f'隔墙茶肆的盏盖碰着碗沿，细响不断，这已经是第{i}回了'),
        ]
        # ⚠ 30 幕要**铺在一天之内**（真实一天不会超过 24 小时）：
        #   每幕 48 分钟，00:00 → 23:12，严格递增且不跨天。
        #   第一版写 `(i % 12) * 2 + 6`，30 幕里时间**绕回了两圈**
        #   ⇒ A5d（单调递增）红得对，是夹具造了假数据。
        # [EN] 30 acts must fit **inside one day** (a real day never exceeds 24h): 48 minutes
        # [EN] each, 00:00 -> 23:12, strictly increasing. The first version wrapped around twice,
        # [EN] so A5d was right and the fixture was lying.
        _tot = i * 48
        _hh, _mm = _tot // 60, _tot % 60
        scenes.append(_Scene(
            entries,
            time_label=f'{_SHICHEN[(_tot // 120) % 12]}时 {_hh:02d}:{_mm:02d}',
            place='临河茶肆' if i % 3 else '后院灶房',
            node_name=f'节点{i // 6 + 1}'))
    return scenes


def scene_lines(scenes) -> list[str]:
    """把夹具摊成行（与 `display.script_render.one_line` 等价的最小实现）。
        English:
    Spread the fixture into lines (a minimal equivalent of `display.script_render.one_line`).
    """
    out = []
    for sc in scenes:
        for e in sc.entries:
            if e.kind == 'scene':
                out.append(f'## {e.text}')
            elif e.kind == 'action':
                out.append(f'· 动作 {e.who}：{e.text}')
            elif e.kind == 'aside':
                out.append(f'◇ 心声 {e.who}：{e.text}')
            elif e.kind == 'dialogue':
                out.append(f'{e.who} →客人乙：{e.text}')
            else:
                out.append(f'∿ 环境 {e.text}')
    return out


class _FakeLoop:
    """只带 `_builder` 的壳 —— `_day_lines` 只用到它。
        English:
    A shell carrying only `_builder` -- that's all `_day_lines` uses.
    """
    _builder = None


def day_lines_of(scenes, narrative) -> list[str]:
    """用**真的** `_day_lines()` 算材料（不接运行实例）。
        English:
    Compute the material with the **real** `_day_lines()` (no live instance needed).
    """
    from sim.loop import RunLoop
    loop = _FakeLoop()

    class _S:
        entries = []

    # 打桩 `script_render.one_line`：夹具的 Entry 不是真 Entry 对象。
    # [EN] Stub `script_render.one_line`: the fixture Entry isn't a real Entry object.
    from display import script_render as SR
    real = SR.one_line

    def fake_one(e):
        if e.kind == 'scene':
            return f'## {e.text}'
        if e.kind == 'action':
            return f'· 动作 {e.who}：{e.text}'
        if e.kind == 'aside':
            return f'◇ 心声 {e.who}：{e.text}'
        if e.kind == 'dialogue':
            return f'{e.who} →客人乙：{e.text}'
        return f'∿ 环境 {e.text}'
    SR.one_line = fake_one
    try:
        return RunLoop._day_lines(loop, narrative, scenes=scenes)
    finally:
        SR.one_line = real


# ══════════════════════════════════════════════════════════════
#  A —— 材料必须是**完整的一天**
# [EN] A -- the material must be **the whole day**
# ══════════════════════════════════════════════════════════════
def material_checks() -> None:
    scenes = make_day_scenes(30)
    full = scene_lines(scenes)
    full_chars = sum(len(x) for x in full)
    # ⚠ 期望值取 **> 12000** 而不是"对齐真实的 4.4 万"：这一组判据要证明的是
    #   **"材料没有被截断/丢弃"**，而旧的截断线是 6000 —— 只要夹具明显超过它
    #   （这里 2.2 倍），"材料丢没丢"就量得出来。把夹具堆到 4.4 万只会让判据又臭又长，
    #   并不增加证伪力（真实 4.4 万那份是用户数据，另由 `verify_export` 的真机段覆盖）。
    # [EN] ⚠ The expectation is **> 12000** rather than "match the real 44k": this group proves
    # [EN] **"the material was not truncated / dropped"**, and the old truncation line was 6000 --
    # [EN] as long as the fixture clearly exceeds it (2.2x here), "was material lost" is measurable.
    # [EN] Padding the fixture to 44k would only make the criteria long and ugly without adding
    # [EN] disproving power (the real 44k copy is user data, covered by `verify_export`'s real-machine
    # [EN] section).
    ok('A0 ★ 夹具规模明显超过旧截断线 6000（30 幕 / 240 行 / >1.2 万字）',
       len(full) == 240 and full_chars > 12000,
       f'{len(full)} 行 / {full_chars} 字符')
    report['fixture_chars'] = full_chars

    # ★★★ 真实故障现场：`_daily_narrative` 里只剩 5 行（3 个出场 + 1 事件 + 1 环境）
    # [EN] ★★★ The real failure scene: `_daily_narrative` retains only 5 lines
    narrative = ['〔出场〕掌柜甲（已在场）', '〔出场〕客人乙（已在场）', '〔出场〕丁（已在场）',
                 '〔事件 · 外部刺激〕门外有人驻足不走', '〔环境〕檐水一滴一滴落在阶前']
    got = day_lines_of(scenes, narrative)
    got_chars = sum(len(x) for x in got)
    ok('A1 ★★★ `_daily_narrative` 只剩 5 行时，材料仍必须是**完整的一天**'
       '（旧实现 `if not lines and groups:` 会让它只返回那 5 行 ⇒ '
       '一天 4.4 万字的戏被整理成 900 字，就是用户报的那个症状）',
       len(got) >= len(full), f'{len(got)} 行 / {got_chars} 字符（应 >= {len(full)} 行）')
    ok('A2 ★★★ 而且材料**不能比 30 幕摊开少多少**（丢一行都不算完整）',
       got_chars >= full_chars * 0.99,
       f'{got_chars} vs {full_chars}（{got_chars / max(1, full_chars) * 100:.1f}%）')
    # 那 5 行也不能丢：它们是 scenes 里没有的（补漏那一半）
    # [EN] Those 5 lines must not be dropped either: they aren't in scenes (the gap-filling half)
    ok('A3 ★★ `_daily_narrative` 里**scenes 没有的行**要补进去'
       '（补漏那一半不能省：非剧本模式下全靠它）',
       all(any(n in x for x in got) for n in narrative),
       f'补进来 {sum(1 for n in narrative if any(n in x for x in got))}/5 行')

    # ── 成对判据：`scenes` 为空时必须照用 `_daily_narrative`（别一刀切）──
    # [EN] ── Paired criterion: with empty `scenes` it must still use `_daily_narrative` ──
    only_narr = day_lines_of([], ['第一行旁白', '第二行旁白'])
    ok('A4 ★★★ **成对**：`scenes` 为空（非剧本模式）时，材料就是 `_daily_narrative`'
       '（不能因为它"不够完整"就返回空 —— 那等于整天不整理）',
       only_narr == ['第一行旁白', '第二行旁白'], str(only_narr))

    # ── 不许重复：scenes 里已有的行不能因为补漏又出现一遍 ──
    # [EN] ── No duplicates: lines already in scenes must not reappear via gap-filling ──
    # ⚠ 探针必须拿**真的** scenes 行（第一版手抄了一句、和生成的不一致 ⇒ 判据自己假红）。
    # [EN] ⚠ The probe must use a **real** scenes line (the first version hand-copied one that did
    # [EN] not match the generated text => the criterion went false red on itself).
    dup_narr = [full[0]]
    got_dup = day_lines_of(scenes, dup_narr)
    # ⚠ 2026-10-19 第六轮：`_day_lines` 现在**每幕前面加一行幕头**
    #   （`〔第 N 幕 · 子时 23:40 · 地点〕`，时序的唯一真相，见那边的长注释）。
    #   判"正文行不重复"要先把幕头剔掉 —— 否则幕头会被当成"多出来的行"。
    #   ⚠ 但幕头**本身**也要成对判：每一幕恰好一行（0 = 又没有时间了，
    #     2 = 重复加了）。这是"搬家要成对判每块恰好出现 1 次"那条纪律。
    # [EN] `_day_lines` now prepends one header line per act (the single source of time). The
    # [EN] "no duplicate body lines" criterion must strip headers first. ⚠ Headers get their own
    # [EN] paired check: exactly one per act (0 = time is gone again, 2 = added twice).
    def _body(rows: list[str]) -> list[str]:
        return [x for x in rows if not str(x).startswith('〔第 ')]

    ok('A5 ★★ 补漏**不去重就会重复整段戏**（scenes 已有的行只出现一次）',
       len(_body(got_dup)) == len(_body(full)),
       f'{len(_body(got_dup))} vs scenes {len(_body(full))} 行正文')
    # ⚠ 幕头要从**真实现产出的 `got`** 里找 —— 第一版从 `full` 找，而 `full` 是
    #   `scene_lines()`（夹具自己算的期望值，不经过 `_day_lines`）⇒ 恒 0 行、
    #   恒假红。这是"期望值不许来自被测函数的另一条路"那条纪律。
    # [EN] Headers must come from `got` (real output). The first version looked in `full`, which
    # [EN] is `scene_lines()` -- the fixture's own expectation that never goes through
    # [EN] `_day_lines` => always 0 rows, always false red.
    _hdr = [x for x in got if str(x).startswith('〔第 ')]
    ok('A5b ★★★ **每一幕恰好一行幕头**（时序的唯一真相去了整理层 —— '
       '没有它，"夜深了""终于到了"只能由模型自己编，用户报的"时序混乱"就是这么来的）',
       len(_hdr) == len(scenes), f'{len(_hdr)} 行幕头 / {len(scenes)} 幕')
    # ★★★ **时间必须单调递增**：这一条才真正证明"整理层拿到的是一根时间轴"。
    #   只判"有幕头"不够 —— 幕头顺序错了，模型照样会把"夜深了"写在前头。
    # [EN] **Times must increase monotonically**: this is what actually proves the organizer
    # [EN] receives a *timeline*. "A header exists" is not enough -- out-of-order headers let the
    # [EN] model put "it is late" at the front again.
    import re as _re

    def _mins(row: str) -> int:
        m = _re.search(r'(\d{2}):(\d{2})', row)
        return int(m.group(1)) * 60 + int(m.group(2)) if m else -1

    _seq = [_mins(x) for x in _hdr]
    _seq = [x for x in _seq if x >= 0]
    ok('A5d ★★★ 幕头的**时间单调递增**（整理层拿到的是一根时间轴，不是一堆乱序的钟点）',
       len(_seq) >= 2 and all(b >= a for a, b in zip(_seq, _seq[1:])),
       f'{len(_seq)} 个钟点：{_seq[:5]}…' if _seq else '（没有钟点）')
    ok('A5c ★★★ 幕头里**真带了时钟**（`time_label` 不是空串就写进去）',
       any('：' in x or ':' in x for x in _hdr) or not _hdr,
       repr(_hdr[0]) if _hdr else '（夹具没有 time_label）')


# ══════════════════════════════════════════════════════════════
#  B —— 分块：写完整，不丢内容
# [EN] B -- chunking: write it fully, don't drop content
# ══════════════════════════════════════════════════════════════
def chunk_checks() -> None:
    from crew import agents as A

    scenes = make_day_scenes(30)
    body = '\n'.join(scene_lines(scenes))
    ok('B0 ★ 材料量级明显超过旧截断线（>1.2 万字）', len(body) > 12000,
       f'{len(body)} 字符（旧截断线 6000）')

    chunks = A._split_for_transcribe(body, 6000)
    ok('B1 ★★★ 材料超过一块时要**切成多块**（一块喂完模型会挑几段写、中段整段跳过）',
       len(chunks) >= 2, f'{len(chunks)} 块 / 材料 {len(body)} 字符')
    sizes = [len(c) for c in chunks]
    ok('B2 ★★ 每块**不超过上限太多**（块太大又变回"一次喂完"）',
       max(sizes) <= 6000 * 1.25, f'最大块 {max(sizes)}（上限 6000）')
    ok('B3 ★★★ **每块都不为空**（空块会让模型对着空气写一段）',
       all(c.strip() for c in chunks), f'空块 {sum(1 for c in chunks if not c.strip())} 个')

    # ★★★ 切块**不许丢材料**：合起来的字符数要接近原文（只允许丢换行/空白）
    # [EN] ★★★ Chunking **must not drop material**: total characters must be close to the source
    # [EN] (only newlines/whitespace may be lost)
    total = sum(len(c) for c in chunks)
    no_ws = lambda x: len(re.sub(r'\s', '', x))  # noqa: E731
    ok('B4 ★★★ 分块后**一个字都没丢**（合起来 ≈ 原文，只少空白）',
       abs(no_ws(''.join(chunks)) - no_ws(body)) <= 2,
       f'{no_ws("".join(chunks))} vs {no_ws(body)}')

    # 按场景边界断：每块开头最好是 `## ` 或正文第一行
    # [EN] Break on scene boundaries: each chunk should start with `## ` or the very first line
    heads = sum(1 for c in chunks[1:] if c.lstrip().startswith('## '))
    ok('B5 ★★ 尽量在**场景边界**断开（模型一段正好一到两场戏，章节天然分段）',
       heads >= len(chunks) - 2, f'{heads}/{len(chunks) - 1} 块以 `## ` 开头')

    # ── 成对判据：设 0 = 不分块，整段返回（给大上下文模型的退路）──
    # [EN] ── Paired criterion: 0 = no chunking, return the whole text (escape hatch for big contexts) ──
    one = A._split_for_transcribe(body, 0)
    ok('B6 ★★★ **成对**：`CREW_DAY_NOVEL_CHUNK=0` 时不切（整段一次交给模型）',
       len(one) == 1 and one[0] == body.strip(), f'{len(one)} 块')
    # 短材料不硬切
    short = A._split_for_transcribe('一二三', 6000)
    ok('B7 ★ 材料本来就短 ⇒ 一块（不为了凑块数去切碎）',
       len(short) == 1, f'{len(short)} 块')

    # ── ★★★ **调用点也要钉**（"函数与调用点两半都要钉"）──
    #   上面 B1-B7 量的是 `_split_for_transcribe` **这个函数**，
    #   而"整理时到底有没有用它"是另一件事：把调用点改回
    #   `chunks = [body_all]`（不分块），或者调用前先 `[:6000]` 截一刀，
    #   上面那七条**一条都不会红**（反例法 ④⑤ 就是这样各撞一次）。
    #   ⇒ 这里用 AST 钉 `_transcribe` 的方法体：
    #     ① 真的调了 `_split_for_transcribe`；
    #     ② `body_all` 那一行**没有切片**（`[:6000]` 那一刀不许回来）。
    # [EN] ── ★★★ **The call site must be pinned too** ("pin both the function and the call site") ──
    # [EN]   B1-B7 above measure the **function** `_split_for_transcribe`; whether the organizing step
    # [EN]   actually **calls** it is a different matter: reverting the call site to
    # [EN]   `chunks = [body_all]` (no chunking), or slicing `[:6000]` before the call, makes **none of
    # [EN]   those seven go red** (counterexamples 4 and 5 each hit exactly this).
    # [EN]   => Use AST to pin `_transcribe`'s body: ① it really calls `_split_for_transcribe`;
    # [EN]      ② the `body_all` line **has no slice** (the `[:6000]` cut must not come back).
    import ast
    import inspect as _inspect
    tree = ast.parse((APP_DIR / 'crew' / 'agents.py').read_text(encoding='utf-8'))
    tr = None
    tjobs = None
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == '_transcribe':
            tr = n
        if isinstance(n, ast.FunctionDef) and n.name == '_transcribe_jobs':
            tjobs = n
    ok('B8 ★ `_transcribe` 在 AST 里找得到', tr is not None, '')
    if tr is not None:
        body_src = ast.unparse(tr)
        # ★★★ 2026-10-26 改口径（**只挪了位置，没放松要求**）：
        #   切块那一步从 `_transcribe` 里挪进了 `_transcribe_jobs`（按情节单元摊成写作次，
        #   见 `crew/unit_plan.py`）。原来这里认的是"`_transcribe` 方法体里出现
        #   `_split_for_transcribe(`"，改完就红 —— 而"到底有没有按上限切"一个字没变。
        #   ⇒ 现在钉**整条链**：`_transcribe` 调 `_transcribe_jobs`，
        #     `_transcribe_jobs` 调 `_split_for_transcribe`。缺任何一环都红
        #     （比原来更严：原来只查一处，现在两处都要在）。
        # [EN] ★★★ Anchor moved, requirement not relaxed (2026-10-26): the chunking step moved
        # [EN] from `_transcribe` into `_transcribe_jobs` (turning plot units into writing passes,
        # [EN] see `crew/unit_plan.py`). The old anchor ("`_split_for_transcribe(` appears in
        # [EN] `_transcribe`") went red while "is the material actually cut at the cap" had not
        # [EN] changed. Now the **whole chain** is pinned: `_transcribe` calls `_transcribe_jobs`,
        # [EN] and `_transcribe_jobs` calls `_split_for_transcribe` -- either link missing goes red.
        ok('B9 ★★★ 整理**真的走了切块那条链**'
           '（函数写好了却不用 = 整段还是 4 万字一次喂，反例法 ④ 撞的就是这个）',
           '_transcribe_jobs(' in body_src
           and tjobs is not None
           and '_split_for_transcribe(' in ast.unparse(tjobs),
           f'链：_transcribe→{("_transcribe_jobs" if "_transcribe_jobs(" in body_src else "✗")}'
           f'→{("split" if tjobs is not None and "_split_for_transcribe(" in ast.unparse(tjobs) else "✗")}')
        sliced = []
        for n in ast.walk(tr):
            if not isinstance(n, ast.Assign):
                continue
            for tgt in n.targets:
                if isinstance(tgt, ast.Name) and tgt.id == 'body_all':
                    if any(isinstance(x, ast.Subscript) for x in ast.walk(n.value)):
                        sliced.append(ast.unparse(n))
        ok('B10 ★★★ `body_all` 那一行**不许切片**'
           '（`[:6000]` 那一刀是"内容少"的元凶之一；反例法 ⑤ 撞的就是这个）',
           not sliced, '；'.join(sliced)[:160])

    # ── ★★ 提示词必须要求"写全" ──
    #   `C1` 守的是"输出预算跟材料走"，而"模型会不会挑着写"靠的是提示词里那句
    #   「一处都不许跳过」。少了它，模型拿到 11 块也只会挑好写的几段
    #   （反例法 ⑨ 撞的就是这个：把那条要求删掉，当时一条判据都不红）。
    # [EN] ── ★★ The prompt must demand "write all of it" ──
    # [EN]   `C1` guards "the output budget follows the material", but whether the model **picks and
    # [EN]   chooses** depends on that "not a single passage may be skipped" sentence in the prompt.
    # [EN]   Without it, even 11 chunks will only produce the easy passages (counterexample 9 hit
    # [EN]   this: deleting that requirement turned no criterion red at the time).
    p_src = _inspect.getsource(A.Novelist._transcribe_once)
    ok('B11 ★★★ 提示词要求**一处都不许跳过**'
       '（不然模型会挑几段写，块数再多也白搭）',
       '一处都不许跳过' in p_src, '')

    # ── ★★★ B12：**`CREW_DAY_NOVEL_CHUNK` 真的决定了切几片**（2026-10-26 补）──
    #   2026-10-26 改成"按情节单元摊写作次"之后，切块那一步进了 `_transcribe_jobs`。
    #   光钉"链还在"（B9）不够：把参数写成常量（`_transcribe_jobs(units, 0, …)`）
    #   链条照样在，材料却整段一次喂 —— 那正是反例法 ④ 要咬的形状。
    #   ⚠ 只测 `_transcribe_jobs` **也不够**（第一版就栽在这儿：反例法 ④ 把
    #     `_transcribe` 里那个参数改成常量，B12 照样绿 —— 因为它是**直接调函数**测的）。
    #     必须走**真入口** `_transcribe`：同一份材料、两个上限，数**模型被叫了几次**。
    # [EN] ★★★ B12 (added 2026-10-26): **`CREW_DAY_NOVEL_CHUNK` really decides the piece count**.
    # [EN] After the "pack plot units into writing passes" refactor, chunking lives in
    # [EN] `_transcribe_jobs`. Pinning "the chain still exists" (B9) is not enough.
    # [EN] ⚠ Testing `_transcribe_jobs` **alone** is not enough either (that is how the first
    # [EN] version failed: counterexample 4 hardcoded the argument inside `_transcribe` and B12
    # [EN] stayed green because it called the function directly). Go through the **real entry**
    # [EN] `_transcribe`: same material, two caps, count how often the model is called.

    class _W:
        progress_nodes: list = []
        current_node = ''
        scene = ''
        weather = '晴'
        style_card: dict = {}

        def on_stage_names(self):
            return []

        def world_prefix(self):
            return '世界观'

        def clock_display(self):
            return '子时'

    class _Stub(A.Novelist):
        def __init__(self):
            self.key = 'novelist'
            self.calls = 0

        async def _transcribe_once(self, ctx, body, **kw):
            self.calls += 1
            return '这一段写好了。' * 6

    def _calls_with(cap: str) -> int:
        old_cap = CFG.s('CREW_DAY_NOVEL_CHUNK')
        try:
            CFG.set('CREW_DAY_NOVEL_CHUNK', cap)
            st = _Stub()
            ctx = A.SetCtx(world=_W(), db=None, day=1)
            asyncio.run(st._transcribe(ctx, body))
            return st.calls
        finally:
            CFG.set('CREW_DAY_NOVEL_CHUNK', old_cap)

    _many_calls = _calls_with('6000')
    _one_call = _calls_with('0')
    ok('B12 ★★★ `CREW_DAY_NOVEL_CHUNK` **真的决定切几片**（走真入口 `_transcribe` 数调用次数）'
       '—— 上限 6000 ⇒ 多次；设 0 ⇒ 一次（那是给大上下文模型的退路）',
       _many_calls >= 2 and _one_call == 1,
       f'6000→{_many_calls} 次 / 0→{_one_call} 次')


# ══════════════════════════════════════════════════════════════
#  C —— 输出预算跟材料走
# [EN] C -- the output budget follows the material
# ══════════════════════════════════════════════════════════════
def budget_checks() -> None:
    import inspect
    from crew import agents as A

    src = inspect.getsource(A.Novelist._transcribe_once)
    ok('C1 ★★★ 输出上限**跟材料长度走**（`max(配置, 材料×N)`）'
       '—— 只改配置默认值不管用：老用户 `.env` 里还存着 2600',
       'max(CFG.i(' in src.replace(' ', '') or 'max(CFG.i' in src, '')
    # 行为判：把 CFG 压到 400（最小），材料 3,600 字，看实际传出去的 max_tokens
    # [EN] Behavior check: pin CFG to 400 (the minimum), material 3,600 chars, inspect the actual
    # [EN] max_tokens passed out
    seen: dict = {}
    real_ask = A.ask

    async def fake_ask(tier, messages, **kw):
        seen['tier'] = tier
        seen['max_tokens'] = kw.get('max_tokens')
        class R:
            ok = True
            value = '（测试输出）'
            notes = []
        return R()
    A.ask = fake_ask
    old = CFG.s('CREW_DAY_NOVEL_TOKENS')
    try:
        CFG.set('CREW_DAY_NOVEL_TOKENS', '400')
        n = A.Novelist.__new__(A.Novelist)
        n.key = 'novelist'

        class Ctx:
            def world_brief(self, k=500):
                return '世界观'
            def genre(self):
                return ('', '')

        body = '· 动作 甲：' + '啊' * 3600
        asyncio.run(A.Novelist._transcribe_once(
            n, Ctx(), body, scope='', link='', craft='', cot_block=''))
    finally:
        A.ask = real_ask
        CFG.set('CREW_DAY_NOVEL_TOKENS', old)
    mt = seen.get('max_tokens') or 0
    ok('C2 ★★★ 配置写 400（最小）时，材料 3,600 字仍拿到**够写的预算**'
       '（实测 2,600 正好卡住、再多一点就截断）',
       mt >= 3600 * 0.8, f'max_tokens={mt}（材料 {len(body)} 字）')

    # 成对：材料很短时不该把预算顶到很大（省钱）
    # [EN] Paired: with very short material the budget must not balloon (save money)
    seen.clear()
    A.ask = fake_ask
    old = CFG.s('CREW_DAY_NOVEL_TOKENS')
    try:
        CFG.set('CREW_DAY_NOVEL_TOKENS', '400')
        n = A.Novelist.__new__(A.Novelist)
        n.key = 'novelist'

        class Ctx2:
            def world_brief(self, k=500):
                return '世界观'
            def genre(self):
                return ('', '')
        # ⚠ 材料给 **200 字**而不是 5 字："很短"仍成立，而"无脑按材料×N 放大"
        #   这种变异才会真的超出下限（5 字 ×20 = 100，判据看不出问题 —— 反例法 ⑧ 撞过）。
        # [EN] ⚠ Give **200** characters rather than 5: "very short" still holds, but a mutation that
        # [EN] blindly scales by material length finally exceeds the floor (5 chars ×20 = 100, which
        # [EN] the criterion cannot see -- counterexample 8 hit this).
        short_body = '· 动作 甲：' + '啊' * 200
        asyncio.run(A.Novelist._transcribe_once(
            n, Ctx2(), short_body, scope='', link='', craft='', cot_block=''))
    finally:
        A.ask = real_ask
        CFG.set('CREW_DAY_NOVEL_TOKENS', old)
    mt2 = seen.get('max_tokens') or 0
    ok('C3 ★★ 成对：材料很短时预算**不膨胀**（配置值当下限，不是无脑放大）',
       mt2 <= 800, f'max_tokens={mt2}（材料 208 字）')


# ══════════════════════════════════════════════════════════════
#  D —— 导出不许被残稿覆盖
# [EN] D -- the export must not be overwritten by a crippled draft
# ══════════════════════════════════════════════════════════════
_DAY_MD = """# 第 1 天 · 辰时 · 晴

> 在场：掌柜甲、客人乙  张力：0.60

## 辰时 08:00
**场景** 临街楼
**环境** 日头渐高
**在场** 掌柜甲、客人乙

""" + '\n\n'.join(
    f'· 动作 掌柜甲：第{i}段动作，布头绕壶身一圈圈蹭到第{i}圈，'
    f'眼睛半垂没往那边看，指节在壶盖上停了一下，壶底磕在柜台木面上响了一声'
    for i in range(200)) + '\n'


def export_checks(tmp: Path) -> None:
    from export import novel_version as NV
    from store.runfolder import RunFolder

    root = tmp / '第1次模拟2026-01-01-00-00'
    (root / '每天的生活').mkdir(parents=True, exist_ok=True)
    (root / '导出').mkdir(parents=True, exist_ok=True)
    day = root / '每天的生活' / '第001天.md'
    day.write_text(_DAY_MD, encoding='utf-8')
    run = RunFolder(tmp, root.name)
    # ⚠ 口径必须一致：`render_manuscript` 返回的 `chars` 是**去掉所有空白**后的字符数，
    #   而 `_tidy_for_novel` 的结果含换行 ⇒ 直接比会差 5-8%（假红）。
    #   ⇒ 两边都过一遍 `re.sub(r'\s','',…)`。
    # [EN] Units must match: `chars` returned by `render_manuscript` excludes all whitespace, while
    # [EN] `_tidy_for_novel`'s result keeps newlines => comparing directly is 5-8% off (false red).
    # [EN] => Strip whitespace on both sides.
    _nw = lambda x: len(re.sub(r'\s', '', x))              # noqa: E731
    material = _nw(NV._tidy_for_novel(NV.read_day(day)[2]))
    ok('D0 ★ 夹具一天的"可读材料"够长（万字量级）', material > 10000,
       f'{material} 字符')

    # ── ① 没有 `当天故事.md`（整理没跑）⇒ 必须用材料，不能是空 ──
    # [EN] ① No `当天故事.md` (organizing never ran) => must use the material, not be empty
    res = NV.render_manuscript(run, mode=NV.MODE_NOVEL)
    ok('D1 ★★★ 没有整理稿时，导出**用完整材料**（不是空稿）',
       res['chars'] >= material * 0.95, f'{res["chars"]} vs 材料 {material}')

    # ── ② 整理稿只有 900 字（真实故障现场）⇒ **不许整份替换** ──
    # [EN] ② The organized draft is only 900 chars (the real failure scene) => **must not replace**
    short = '掌柜甲在柜台后擦壶。客人乙在擦条案。' * 50        # ≈ 900 字
    (root / '当天故事.md').write_text(
        f'# 当天故事\n\n## 第 1 天 · 辰时\n\n{short}\n', encoding='utf-8')
    res2 = NV.render_manuscript(run, mode=NV.MODE_NOVEL)
    ok('D2 ★★★ 整理稿 900 字 vs 材料几万字 ⇒ 导出**保住材料**'
       '（旧实现 `if better: body = better` 会输出 1,185 字 —— 用户报的症状）',
       res2['chars'] >= material * 0.95,
       f"导出 {res2['chars']} / 材料 {material}（整理稿只有 {len(short)}）")
    # ⚠ **不能用 `'素材稿' in text`**：文件头本来就写着
    #   「**这是素材稿，不是成稿。**」⇒ 那个条件永远为真，变异也咬不住
    #   （反例法 ⑬ 撞过：把"为什么改用素材稿"那一段删掉，判据照样绿）。
    #   要认的是**那一段说明本身**（"整理稿只有 N 字"）。
    # [EN] ⚠ **Must not use `"素材稿" in text`**: the file header already says
    # [EN]   "**这是素材稿，不是成稿。**" => that condition is always true and no mutation can break it
    # [EN]   (counterexample 13 hit this: deleting the "why we switched" paragraph kept it green).
    # [EN]   Recognize **that paragraph itself** ("整理稿只有 N 字").
    ok('D3 ★★★ 而且**如实说明**为什么改用素材稿（不静默降级）',
       '整理稿只有' in res2['text'] and '改用' in res2['text'],
       res2['text'][:240].replace('\n', ' '))
    ok('D4 ★ 整理稿太短时，那份残稿的内容**不该出现在导出里**'
       '（否则一段 900 字摘要顶掉整天）',
       '掌柜甲在柜台后擦壶。客人乙在擦条案。' * 3 not in res2['text'], '')

    # ── ③ 整理稿够长（≥15%）⇒ 用整理稿（那才是"小说"）──
    # [EN] ③ The organized draft is long enough (>=15%) => use it (that's the "novel")
    good = '这一天的戏收在灯上。' * (int(material * 0.3) // 10)
    (root / '当天故事.md').write_text(
        f'# 当天故事\n\n## 第 1 天 · 辰时\n\n{good}\n', encoding='utf-8')
    res3 = NV.render_manuscript(run, mode=NV.MODE_NOVEL)
    ok('D5 ★★★ **成对**：整理稿够长（≥15%）时就用它 —— 那才是小说，不是素材稿',
       '这一天的戏收在灯上。' in res3['text'], f"导出 {res3['chars']} 字符")
    ok('D6 ★ 用整理稿时**不加**"改用素材稿"那句说明',
       '整理稿只有' not in res3['text'], '')


# ══════════════════════════════════════════════════════════════
#  E —— 行内元标记
# [EN] E -- inline metadata markers
# ══════════════════════════════════════════════════════════════
def marker_checks() -> None:
    from export import novel_version as NV

    body = '\n'.join([
        '· 动作 丁：拨了两下算盘',
        '◇ 心声 丁：〔aside·丁〕傻子账上不糊涂。',
        '客人乙 →丁：〔dialogue·客人乙 → 丁〕（慢半拍）……我记得。',
        '◇ 心声 掌柜甲：{aside·掌柜甲}（心声）笔锋像他，不奇怪。',
        '〔切至 · 柜上长凳｜同一时刻〕',
        '〔事件 · 伏笔激活〕井里浮起半截香签',
        '〔切回 · 临街楼〕',
    ])
    out = NV._tidy_for_novel(body)
    for mark in ('〔aside·', '〔dialogue·', '{aside·'):
        ok(f'E1 ★★★ `{mark}` 被剃掉（实测一天 132 处，留着读起来是文件格式不是小说）',
           mark not in out, out.replace('\n', ' ／ ')[:160])
    ok('E2 ★★★ **成对**：转场标记 `〔切至 …〕` 必须留下'
       '（"同一时刻不同人在做不同事"的表达载体，剃了戏就断了）',
       '〔切至 · 柜上长凳｜同一时刻〕' in out, '')
    ok('E2b ★★ `〔事件 · …〕` 也留着（那是剧情节点，不是机器标记）',
       '〔事件 · 伏笔激活〕' in out, '')
    ok('E3 ★ 剃完不留空括号残骸（`（）` / `( )`）',
       not re.search(r'[（(]\s*[）)]', out), out.replace('\n', ' ／ ')[:160])
    ok('E4 ★ 台词本身**一个字没动**（只剃标记，不改内容）',
       '傻子账上不糊涂' in out and '……我记得。' in out, '')


# ══════════════════════════════════════════════════════════════
def main() -> None:
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix='nws_fullness_'))
    print('\n── A 材料必须是完整的一天 ──')
    try:
        material_checks()
    except Exception:                                            # noqa: BLE001
        ok('A 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── B 分块：写完整、不丢内容 ──')
    try:
        chunk_checks()
    except Exception:                                            # noqa: BLE001
        ok('B 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── C 输出预算跟材料走 ──')
    try:
        budget_checks()
    except Exception:                                            # noqa: BLE001
        ok('C 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── D 导出不许被残稿覆盖 ──')
    try:
        export_checks(tmp)
    except Exception:                                            # noqa: BLE001
        ok('D 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── E 行内元标记 ──')
    try:
        marker_checks()
    except Exception:                                            # noqa: BLE001
        ok('E 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])

    n = len(report['checks'])
    good = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n导出内容完整性验证：{good}/{n}')
    (OUT / 'novel_fullness_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    VU.safe_rmtree(tmp, ignore_errors=True)
    sys.exit(0 if good == n else 2)


if __name__ == '__main__':
    main()
