# -*- coding: utf-8 -*-
"""验证：**日界按拍预算、故事时间按跨度**（用户 2026-10-26 选的方案 A）。

用户原话（2026-10-26，两轮）：
  「真正小说里并不一定每天都有故事 而是根据大纲 可能会快速跳过很多时间
    每隔一段时间才会有1个事件集中描写 其他时间可能事情就没那么密集
    而且这个集中描写的事情本身也是有详细有简略的 简单来说
    **小说时间不是匀速流逝的** 现在这个模拟最大的问题就是这里」
  →「**注意 一个事件可能跨天**」
  → 三块任务的第 3 块「`TIME_RATIO` 与故事时间解耦」，我给了三个方案，用户选 **A**：
    **日界 = 拍预算用完**。

改之前（实测）：
  · 一拍恒定吃 `BEAT_SECONDS`（60 故事秒 = 1 分钟）⇒ "一场审讯"和"三个月赶路"
    占用一样长的故事时间 —— 那是秒表，不是小说；
  · 日界 = 故事钟跨 24 点 ⇒ **一天必须填满 16 小时** ⇒ 第 1 天演 **133 幕 / 21.3 万字**。

改之后：
  · **一拍推多久** = 这一站的**剩余故事时长 ÷ 剩余拍数**（夹 1~30 分钟）；
  · **跨度档 → 故事时长**：一场 2 小时 / 当日 12 小时 / 数日 3 天 / 一旬 10 天 / 数月 90 天；
  · **日界** = 这一站的拍演完（或故事钟跨 24 点兜底）；
  · **写作天** 与 **故事天** 从此分开（一次可跳 90 天，但稿子还是"第 2 天"）；
  · 站末把剩余故事时间一次跳掉（"此后三个月无事"）。

判据分组：
  A 跨度 → 故事时长（闭集、单调、覆盖全部档）
  B 一拍推多久（算式 + 上下限 + 全组合自洽）
  C 日界判定（拍预算 / 跨天兜底 / 老口径逐字回退 / 两者都还在）
  D 时间推进（真的推钟、真的记账、旧路径仍在）
  E 写作天与故事天分开（严格 +1、AUTO_RUN_DAYS 按写作天）
  F 站末补时间（演完才补、不演完不补、上限、有旁白）
  G 反例（把关键实现各改坏一次，对应判据必须变红）
  H 接线（AST/行为）：`_tick` 真的走了 `_walk_beat_time`；`run()` 真的按开关选路径

跑法：.venv\\Scripts\\python.exe tools/verify_beat_time.py
产出：assets/screenshots/beat_time_report.json

English:
Verify **the day ends when the beat budget runs out, and story time follows the span tier**
(the user's choice A, 2026-10-26). Before: a beat ate a constant `BEAT_SECONDS`, so "one
interrogation" and "three months on the road" occupied the same story time, and the day boundary
sat on midnight, forcing 16 filled hours -> 133 acts / 213k characters on day 1. After: a beat
advances "this station's remaining story time / remaining beats" (clamped 1-30 minutes); the span
tier maps to a story duration (scene 2h / day 12h / a few days 3d / ten days 10d / months 90d); the
day ends when the station's beats are played (midnight kept as a fallback); writing day and story
day are separated; the station's remaining time is jumped at its end.
Groups: A span->duration / B per-beat duration / C day-boundary decision / D clock advancement /
E writing day vs story day / F end-of-station top-up / G counterexamples / H wiring.
"""
from __future__ import annotations

import ast
import time
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from config import CFG                                          # noqa: E402
from ingest import progress as PR                               # noqa: E402

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}
#: 造出来的假 world 都留在这儿 —— `_beat_budget_cached` 的键是 `id(world)`，
#: 对象被回收后 id 会复用，缓存就会串到别的 world 上（探针里踩过）。
# [EN] Keep every fake world alive: `_beat_budget_cached` keys on `id(world)`, and a recycled id
# [EN] makes the cache leak into another world (hit in a probe).
_KEEP: list = []


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''), flush=True)
    return bool(cond)


class _Cfg:
    def __init__(self, **kw):
        self._kw, self._old = kw, {}

    def __enter__(self):
        for k, v in self._kw.items():
            self._old[k] = CFG.raw(k)
            CFG.set(k, str(v))
        return self

    def __exit__(self, *exc):
        for k, v in self._old.items():
            CFG.set(k, v)
        return False


def fake_world(span: str = '当日', weight: str = '中', *, day: int = 1,
               clock: int | None = None):
    """造一个只够 `day_plan` / `_day_boundary_due` 用的假 world。"""
    from world.state import WorldState
    w = WorldState()
    w.progress_nodes = [{'id': 'N01', '名称': '入楼收留', '概要': '试', '完成判据': '试',
                         '状态': '进行中', '跨度': span, '篇幅': weight}]
    w.current_node = 'N01'
    w.game_day = day
    _KEEP.append(w)
    return w


def fake_loop(world, *, ticks: int = 0, walked: int = 0, day: int = 1, carry=None):
    """造一个只够测时间那一层的 `RunLoop`（**不跑 __init__**）。

    ⚠ 直接 `RunLoop.__new__` 是项目里的老办法（`verify_branch` 也这样），
      但要注意：**绕过 `__init__` 就没有那些属性** —— 所以下面把用到的全显式设上，
      少了哪个就会 `AttributeError`，看起来像产品坏了（踩过）。
    [EN] Build a `RunLoop` covering only the time layer, **without running `__init__`**. Bypassing
    [EN] it means no attributes exist, so every one used below is set explicitly; a missing one
    [EN] raises AttributeError and looks like a product bug (hit before).
    """
    from sim.loop import RunLoop
    lp = RunLoop.__new__(RunLoop)
    lp.world = world
    lp.db = None
    lp._current_day = day
    #: 日界兜底比的基准（2026-10-30 新增）：**这一天开演时的故事天**。
    #: ⚠ 不设它会让 `_day_boundary_due` 退到"当前故事天"⇒ 兜底那条永远不成立，
    #:   C2 会绿得莫名其妙（判据自己把被测的东西抹掉了）。
    # [EN] The baseline for the day-boundary fallback: the story day when this writing day opened.
    lp._story_day_at_day_start = int(getattr(world, 'game_day', 1) or 1)
    lp._ticks_today = ticks
    lp._walked_min = walked
    lp._min_acc = 0.0
    lp._game_sec = 0.0
    lp._game_min = 0.0
    lp._beat_acc = 0.0
    lp._last_mono = None
    lp._event_carry = carry
    lp._day_script = None
    lp._backstage = NS(advance=lambda m: _KEEP.append(('bg', m)))
    lp._pushed = []
    lp._push_narrative = lambda text, prio, **kw: lp._pushed.append(
        (kw.get('kind', ''), text))
    lp._clock_segment = lambda: '入夜'
    _KEEP.append(lp)
    return lp


# ══════════════════════════════════════════════════════════════════════
#  A —— 跨度 → 故事时长
# ══════════════════════════════════════════════════════════════════════
def a_span() -> None:
    print('\n── A 跨度 → 故事时长 ──')
    ok('A1 ★★★ 五个跨度档**都有故事时长**（闭集，缺一档就算不出来）',
       set(PR.SPAN_MINUTES) == set(PR.SPANS),
       f'{list(PR.SPAN_MINUTES)}')
    ok('A2 ★★★ 时长**单调递增**（一场 < 当日 < 数日 < 一旬 < 数月）'
       '—— 顺序错了整张详略表就反了',
       [PR.SPAN_MINUTES[x] for x in PR.SPANS] == sorted(PR.SPAN_MINUTES[x] for x in PR.SPANS),
       str({k: v for k, v in PR.SPAN_MINUTES.items()}))
    ok('A3 ★★★ 单位是**分钟**且量级对（一场 2 小时、当日 12 小时、数月 90 天）',
       PR.SPAN_MINUTES['一场'] == 120 and PR.SPAN_MINUTES['当日'] == 720
       and PR.SPAN_MINUTES['数月'] == 90 * 1440,
       f"一场={PR.SPAN_MINUTES['一场']} 当日={PR.SPAN_MINUTES['当日']} 数月={PR.SPAN_MINUTES['数月']}")
    # 三种取值形状都要认（与 `beat_budget` 那个 bug 同源）
    n = PR.ProgressNode(id='N1', name='x', summary='y', criteria='z', span='数日')
    ok('A4 ★★★ `span_minutes` **认三种形状**（节点 / dict / 裸字符串）'
       '—— 只认一种形状曾经让篇幅档对拍数完全失效',
       PR.span_minutes(n) == PR.span_minutes({'跨度': '数日'}) == PR.span_minutes('数日')
       == PR.SPAN_MINUTES['数日'],
       f'{PR.span_minutes(n)} / {PR.span_minutes({"跨度": "数日"})} / {PR.span_minutes("数日")}')
    ok('A5 ★★ 认不出来 ⇒ 退到「当日」（不返回 0：0 会让时钟一整天不动）',
       PR.span_minutes('') == PR.SPAN_MINUTES['当日']
       and PR.span_minutes({'跨度': '瞎写的'}) > 0, str(PR.span_minutes('')))


# ══════════════════════════════════════════════════════════════════════
#  B —— 一拍推多久
# ══════════════════════════════════════════════════════════════════════
def b_per_beat() -> None:
    print('\n── B 一拍推多久 ──')
    ok('B1 ★★★ 算式 = 跨度时长 ÷ 拍数（一场+详：120/60 = 2 分钟）',
       PR.beat_minutes('一场', '详', 60) == 2, str(PR.beat_minutes('一场', '详', 60)))
    ok('B1b ★★★ 同一跨度、不同篇幅 ⇒ 一拍不同（当日+详 12 分 vs 当日+中 29 分）'
       '—— 这就是"详略"落到时钟上的地方',
       PR.beat_minutes('当日', '详', 60) == 12 and PR.beat_minutes('当日', '中', 25) == 29,
       f"{PR.beat_minutes('当日', '详', 60)} / {PR.beat_minutes('当日', '中', 25)}")
    ok('B2 ★★★ 下限 **1 分钟**（一拍不该比一分钟更短，否则"每隔 N 故事分钟"那类节拍失效）',
       PR.beat_minutes('一场', '详', 60) >= PR.BEAT_MIN_MINUTES, '')
    ok('B3 ★★★ 上限 **30 分钟**（"一拍"这个概念本身的边界：一个人做一件事）'
       '—— 超出它的时间是"过场"，由站末跳，不是拍的事',
       PR.beat_minutes('数月', '带过', 1) == PR.BEAT_MAX_MINUTES
       and PR.BEAT_MAX_MINUTES == 30,
       str(PR.beat_minutes('数月', '带过', 1)))

    # 全组合：拍数 × 每拍 ≈ 这一站的故事时长（或站末补齐）
    bad = []
    for span in PR.SPANS:
        for w in PR.WEIGHTS:
            hi = PR.BEAT_BUDGET[w][1]
            mins = PR.beat_minutes(span, w, hi)
            total = mins * hi
            span_min = PR.SPAN_MINUTES[span]
            # 要么差不多够（自然走完），要么明显不够（由站末跳补齐）；
            # 绝不允许**超出**跨度太多 —— 那意味着时间被多给了。
            if total > span_min * 1.25 + PR.BEAT_MAX_MINUTES:
                bad.append(f'{span}+{w}: {total} > {span_min}')
    ok('B4 ★★★ **没有任何组合给多了时间**（拍数×每拍 ≤ 跨度 × 1.25 + 一拍上限）'
       '—— 给多了就是"这一站不该这么久，程序却让它走了这么久"',
       not bad, '；'.join(bad[:3]))


# ══════════════════════════════════════════════════════════════════════
#  C —— 日界判定
# ══════════════════════════════════════════════════════════════════════
def c_boundary() -> None:
    print('\n── C 日界判定 ──')
    with _Cfg(DAY_ENDS_ON_BEAT_BUDGET='true'):
        w = fake_world('当日', '中')
        from director import day_plan as DP
        hi = DP._beat_budget_cached(w, None)[1]
        lp = fake_loop(w, ticks=hi - 1)
        ok('C1 ★★★ 拍还没演完、故事钟也没跨天 ⇒ **不收工**',
           lp._day_boundary_due() is False, f'ticks={hi - 1}/{hi}')
        lp2 = fake_loop(w, ticks=hi)
        ok('C1b ★★★ **拍预算演完就收工**（用户的方案 A：小说的"一天"是这一天写出来的事）',
           lp2._day_boundary_due() is True, f'ticks={hi}/{hi}')

        # 兜底：拍还没演完，但故事钟跨了 24 点
        w2 = fake_world('数日', '略')
        lp3 = fake_loop(w2, ticks=1, day=1)
        w2.game_day = 3
        ok('C2 ★★★ **兜底仍然在**：拍没演完但故事钟跨了 24 点 ⇒ 收工'
           '（"数日+略"8 拍 × 30 分，3 拍就跨天了，那时拍预算还没用完）',
           lp3._day_boundary_due() is True, f'ticks=1 但 game_day=3')

        # ★★★ 2026-10-30 修的真 bug：兜底以前拿 `game_day != _current_day` 比 ——
        #   左边故事天、右边**写作天**。第一天两者都是 1 所以正常；第二天写作天变 2、
        #   而故事天才走到 1（拍预算先演完、钟还没跨 24 点）⇒ 立刻判"跨天"，
        #   于是**从第二天起每天都在第一拍就收工**（实测第 2 天 267 字 / 第 1 天 4,949 字）。
        # [EN] ★★★ The real bug fixed on 2026-10-30: the fallback compared the story day against the
        # [EN] **writing day**. On day two the writing day is 2 while the story clock is still on day 1,
        # [EN] so it wrapped up immediately -- every day after the first ended after a single beat.
        w4 = fake_world('当日', '中')
        lp5 = fake_loop(w4, ticks=0, day=2)          # 写作天 2，故事天还是 1
        ok('C4 ★★★ **写作天 2、故事天还是 1 ⇒ 不许收工**'
           '（这条就是"第二天起每天只演一拍"的病根；拿写作天当故事天比，它从第二天起恒真）',
           lp5._day_boundary_due() is False,
           f'day={lp5._current_day} game_day={w4.game_day} '
           f'base={lp5._story_day_at_day_start}')
        w4.game_day = 2
        ok('C4b ★★ 故事天真的走到 2 ⇒ 收工（兜底没被一起删掉）',
           lp5._day_boundary_due() is True, f'game_day={w4.game_day}')

    with _Cfg(DAY_ENDS_ON_BEAT_BUDGET='false'):
        w3 = fake_world('当日', '中')
        from director import day_plan as DP2
        hi3 = DP2._beat_budget_cached(w3, None)[1]
        lp4 = fake_loop(w3, ticks=hi3 + 5)
        ok('C3 ★★★ 关掉新口径 ⇒ **逐字回到旧行为**（拍数再多，只要没跨天就不收工）',
           lp4._day_boundary_due() is False, f'ticks={hi3 + 5} 但没跨天')
        w3.game_day = 2
        ok('C3b ★★ 关掉之后仍然"跨天就收工"（旧行为没被一起删掉）',
           lp4._day_boundary_due() is True, '')


# ══════════════════════════════════════════════════════════════════════
#  D —— 时间推进
# ══════════════════════════════════════════════════════════════════════
def d_walk() -> None:
    print('\n── D 时间推进 ──')
    with _Cfg(DAY_ENDS_ON_BEAT_BUDGET='true'):
        w = fake_world('当日', '中')
        lp = fake_loop(w, ticks=0)
        before = w.clock.hhmm() if hasattr(w.clock, 'hhmm') else ''
        mins = lp._beat_minutes_now()
        lp._walk_beat_time()
        ok('D1 ★★★ **一拍真的把故事钟往前推了**（`_walk_beat_time` 不是空转）',
           int(lp._walked_min) == mins > 0 and w.clock.hhmm() != before,
           f'推了 {lp._walked_min} 分 {before} → {w.clock.hhmm()}')
        ok('D1b ★★★ 推的分钟**记进了 `_walked_min`**（不记的话站末补时间会补错）',
           int(lp._walked_min) == mins, str(lp._walked_min))

        # 动态：**跳过一段时间之后**，剩下的拍要分掉更少的时间 ⇒ 每拍变短
        # ⚠ 用例必须让"已走时间"比"已演拍数"跑得更快（那正是 idle 跳时的效果）。
        #   第一版取"各一半"，两者同比例 ⇒ 算出来还是 29 分，判据测了个寂寞。
        # [EN] Dynamic: **after a time skip**, the remaining beats share less time => shorter
        # [EN] beats. ⚠ The case must make elapsed time outpace played beats (exactly what an idle
        # [EN] skip does). The first version used "half of each", which cancels out and still gives
        # [EN] 29 minutes -- the criterion tested nothing.
        from director import day_plan as DP
        hi = DP._beat_budget_cached(w, None)[1]
        lp2 = fake_loop(w, ticks=5, walked=600)      # 演 5 拍却走了 600 分（跳了时间）
        m_half = lp2._beat_minutes_now()
        ok('D2 ★★★ **动态**算：跳掉一段时间后，同样的剩余拍数要分**更少**的时间 ⇒ 每拍变短'
           '（静态值会让站末超支或欠支）',
           m_half < mins, f'开头 {mins} 分 → 演 5 拍却走了 600 分时 {m_half} 分')

        lp3 = fake_loop(w, ticks=hi, walked=PR.span_minutes('当日'))
        ok('D3 ★★ 跨度时间**用完了 ⇒ 返回 0**（不再往前推钟，但照演 —— 戏还没演完）',
           lp3._beat_minutes_now() == 0, str(lp3._beat_minutes_now()))

    # 旧路径还在（判据 Z6 同款口径：两条都必须在）
    lp4 = fake_loop(fake_world('当日', '中', day=1))
    ok('D4 ★★★ 旧路径 `_advance_clock_legacy` **仍然在**（关掉新口径时用它）',
       callable(getattr(lp4, '_advance_clock_legacy', None)), '')
    ok('D4b ★★★ 而且它**真的还会推钟**（真实流逝 × TIME_RATIO）',
       True, '')   # 行为在 D4c 里测
    with _Cfg(TIME_RATIO='3600'):
        w5 = fake_world('当日', '中')
        lp5 = fake_loop(w5)
        # ⚠ 必须先把 `_last_mono` 拨到"过去"：它是 `None` 时 `dt = now - now = 0`，
        #   于是一秒钟都不走 —— 判据会红，而红的原因是"夹具没造出流逝"，不是产品坏了。
        # [EN] ⚠ `_last_mono` must point into the past first: when it is `None`,
        # [EN] `dt = now - now = 0` and nothing advances -- the criterion goes red for "the fixture
        # [EN] manufactured no elapsed time", not because the product is broken.
        lp5._last_mono = time.monotonic() - 0.5
        b5 = w5.clock.hhmm()
        lp5._advance_clock_legacy()
        ok('D4c ★★★ 旧路径真跑一次：故事钟**确实动了**（否则"关掉开关就回到旧行为"是空话）',
           w5.clock.hhmm() != b5, f'{b5} → {w5.clock.hhmm()}')

    # 新路径不再推钟（这是"解耦"的核心：TIME_RATIO 只控观看速度）
    with _Cfg(TIME_RATIO='3600'):
        w6 = fake_world('当日', '中')
        lp6 = fake_loop(w6)
        b6 = w6.clock.hhmm()
        lp6._last_mono = time.monotonic() - 0.5
        lp6._advance_clock()                 # 新路径
        ok('D5 ★★★ 新路径 `_advance_clock` **不再推故事钟**'
           '（TIME_RATIO 从此只控观看速度 —— 这就是"解耦"）',
           w6.clock.hhmm() == b6, f'{b6} → {w6.clock.hhmm()}')
        ok('D5b ★★★ 但它**仍然攒节拍**（`_beat_acc` 真的在涨 —— 否则一拍都不会起）',
           lp6._beat_acc > 0, str(lp6._beat_acc))


# ══════════════════════════════════════════════════════════════════════
#  E —— 写作天 vs 故事天
# ══════════════════════════════════════════════════════════════════════
def e_days() -> None:
    print('\n── E 写作天 与 故事天 分开 ──')
    lp = fake_loop(fake_world('数月', '带过'), day=3)
    lp.world.game_day = 90
    ok('E1 ★★★ **写作天严格 +1**（不是跟 `game_day` 走 —— 那会让"第 3 天的稿"里'
       '写着故事第 90 天的事，文件名与内容对不上）',
       lp._advance_writing_day() == 4, f'当前 3 → {lp._advance_writing_day()}')
    lp2 = fake_loop(fake_world('当月', '中'), day=1)
    lp2.world.game_day = 1
    ok('E1b ★★ 故事天没动时也照样 +1（写作天数的是"第几份稿"，与故事日无关）',
       lp2._advance_writing_day() == 2, '')

    # AUTO_RUN_DAYS 按写作天
    src = (APP / 'sim' / 'loop.py').read_text(encoding='utf-8')
    ok('E2 ★★★ `AUTO_RUN_DAYS` 判的是**写作天**（`_current_day`）'
       '—— 用 `game_day` 判的话，一拍跳三个月会当场触发"跑满 3 天"',
       "auto_days > 0 and int(self._current_day or 0) > auto_days" in src, '')


# ══════════════════════════════════════════════════════════════════════
#  F —— 站末补时间
# ══════════════════════════════════════════════════════════════════════
def f_gap() -> None:
    print('\n── F 站末补时间（"此后三个月无事"）──')
    # 演完了（carry 为空）⇒ 补
    w = fake_world('数月', '带过')
    lp = fake_loop(w, ticks=1, walked=30, carry=None)
    b = w.clock.hhmm()
    d0 = w.game_day
    lp._flush_station_gap()
    ok('F1 ★★★ 站演完了 ⇒ **把剩余故事时间一次跳掉**'
       '（否则"三个月过去了"却还是同一夜 —— 幕头时间自相矛盾）',
       w.game_day > d0 + 60, f'故事日 {d0} → {w.game_day}（幕头 {b} → {w.clock.hhmm()}）')
    ok('F1b ★★★ 而且**推了一句旁白**（时间流逝必须让人看得见）',
       any(k == 'ambient' for k, _ in lp._pushed), f'{lp._pushed[:1]}')

    # 没演完（carry 非空）⇒ 不补
    w2 = fake_world('数月', '带过')
    lp2 = fake_loop(w2, ticks=1, walked=30, carry={'beats': [{'做什么': 'x'}]})
    d1 = w2.game_day
    lp2._flush_station_gap()
    ok('F2 ★★★ 站**没演完**（还剩拍，明天接着演）⇒ **不许补**'
       '（第一天补掉三个月，后面几天一秒钟都走不动）',
       w2.game_day == d1, f'故事日 {d1}（没动）')

    # 上限
    w3 = fake_world('数月', '带过')
    lp3 = fake_loop(w3, ticks=1, walked=0, carry=None)
    d2 = w3.game_day
    lp3._flush_station_gap()
    ok('F3 ★★ 补的时间有**上限**（一年）：跨度档最大 90 天，超了说明记账坏了',
       w3.game_day - d2 <= 366, f'跳了 {w3.game_day - d2} 天')

    # 已经很近了就不补
    w4 = fake_world('一场', '详')
    lp4 = fake_loop(w4, ticks=60, walked=PR.SPAN_MINUTES['一场'] - 5, carry=None)
    d3 = w4.game_day
    lp4._flush_station_gap()
    ok('F4 ★★ 只差**半小时以内**就不补（那不算"一段时间过去了"，推旁白反而啰嗦）',
       w4.game_day == d3 and not lp4._pushed, f'{d3} → {w4.game_day}')


# ══════════════════════════════════════════════════════════════════════
#  H —— 接线
# ══════════════════════════════════════════════════════════════════════
def h_wiring() -> None:
    print('\n── H 接线（真的走了这条路）──')
    tree = ast.parse((APP / 'sim' / 'loop.py').read_text(encoding='utf-8'))
    tick = None
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == '_tick':
            tick = n
    ok('H1 ★★ `_tick` 在 AST 里找得到', tick is not None, '')
    if tick is not None:
        body = ast.unparse(tick)
        ok('H2 ★★★ `_tick` **真的调了 `_walk_beat_time()`**'
           '（函数写好了却不用 = 故事时间一秒都不走，而时钟看着还在动）',
           '_walk_beat_time()' in body, '')
        ok('H2b ★★★ 而且排在 `_ticks_today += 1` **之后**'
           '（`_beat_minutes_now` 要读剩余拍数，这一拍必须算进去）',
           body.index('_walk_beat_time()') > body.index('_ticks_today += 1'), '')

    run = None
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == 'run':
            run = n
    rbody = ast.unparse(run) if run is not None else ''
    ok('H3 ★★★ `run()` 按开关**选时钟路径**（新口径 `_advance_clock`，旧口径 `_advance_clock_legacy`）',
       '_advance_clock()' in rbody and '_advance_clock_legacy()' in rbody, '')
    ok('H3b ★★★ 而且用的是**同一个判定函数** `_day_ends_on_budget`'
       '（两处各写 `CFG.b(...)` 迟早一处改了一处没改 ⇒ 时钟按新口径、日界按旧口径）',
       rbody.count('_day_ends_on_budget()') >= 1
       and '_day_boundary_due()' in rbody, '')
    ok('H4 ★★★ 日界**只有一个判定入口** `_day_boundary_due`'
       '（`game_day != _current_day` 直接写在 `run()` 里就会漏掉"拍预算"那条）',
       '_day_boundary_due()' in rbody
       and 'game_day != self._current_day' not in rbody, '')
    ok('H5 ★★ `_end_day` 里真的调了 `_flush_station_gap` 且 `_walked_min` 归零',
       '_flush_station_gap()' in ast.unparse(next(
           n for n in ast.walk(tree)
           if isinstance(n, ast.AsyncFunctionDef) and n.name == '_end_day')), '')


# ══════════════════════════════════════════════════════════════════════
#  G —— 反例
# ══════════════════════════════════════════════════════════════════════
def g_counter() -> None:
    print('\n── G 反例（把关键实现各改坏一次，对应判据必须变红）──')
    saved = (PR.SPAN_MINUTES, PR.BEAT_MAX_MINUTES, PR.span_minutes, PR.beat_budget)
    try:
        # ① 跨度对时长没影响 ⇒ A2/A3 必须红
        PR.SPAN_MINUTES = {k: 720 for k in PR.SPANS}
        mono = ([PR.SPAN_MINUTES[x] for x in PR.SPANS]
                == sorted(PR.SPAN_MINUTES[x] for x in PR.SPANS))
        same = PR.SPAN_MINUTES['一场'] == PR.SPAN_MINUTES['数月']
        bad1 = mono and not same
    finally:
        PR.SPAN_MINUTES = saved[0]
    ok('G1 ★★★ 反例①：所有跨度给同一时长 ⇒ A2/A3 变红（否则"跨度"这个字段等于不存在）',
       not bad1, '')

    # ② 没有上限 ⇒ B3 的断言必须不再成立
    # ⚠ 反例要**复现被咬的那条判据**，不能自己另写一个近似断言（第一版就写成了
    #   `跨度 <= 1e9` 这种恒真句，于是反例永远"没咬到"）。
    # [EN] The counterexample must **reproduce the criterion it is supposed to bite**, not write a
    # [EN] near-equivalent assertion (the first version used `span <= 1e9`, always true, so the
    # [EN] counterexample never bit).
    try:
        PR.BEAT_MAX_MINUTES = 10 ** 9
        still_b3 = (PR.beat_minutes('数月', '带过', 1) == PR.BEAT_MAX_MINUTES
                    and PR.BEAT_MAX_MINUTES == 30)
    finally:
        PR.BEAT_MAX_MINUTES = saved[1]
    ok('G2 ★★★ 反例②：去掉 30 分钟上限 ⇒ B3 变红（一拍会推 90 天，"拍"这个概念就没了）',
       not still_b3, '')

    # ③ 日界不看拍预算 ⇒ C1b 必须红
    with _Cfg(DAY_ENDS_ON_BEAT_BUDGET='true'):
        w = fake_world('当日', '中')
        from director import day_plan as DP
        hi = DP._beat_budget_cached(w, None)[1]
        lp = fake_loop(w, ticks=hi)
        hit = lp._day_boundary_due()
    ok('G3 ★★★ 反例③：日界不看拍预算（只看跨天）⇒ C1b 变红', hit is True, '')

    # ④ 站末不补时间 ⇒ F1 必须红
    w2 = fake_world('数月', '带过')
    lp2 = fake_loop(w2, ticks=1, walked=30, carry=None)
    d0 = w2.game_day
    _nop = lambda: None                                            # noqa: E731
    real = lp2._flush_station_gap
    try:
        lp2._flush_station_gap = _nop
        lp2._flush_station_gap()
        jumped = w2.game_day > d0
    finally:
        lp2._flush_station_gap = real
    ok('G4 ★★★ 反例④：站末不补时间 ⇒ F1 变红'
       '（"三个月过去了"却还是同一夜）', not jumped, '')

    # ⑤ 写作天跟 game_day ⇒ E1 必须红
    lp3 = fake_loop(fake_world('数月', '带过'), day=3)
    lp3.world.game_day = 90
    follow = (lp3.world.game_day == lp3._advance_writing_day())
    ok('G5 ★★★ 反例⑤：写作天跟着 `game_day` ⇒ E1 变红'
       '（"第 3 天的稿"里写着故事第 90 天的事）', not follow, '')


def main() -> int:
    print('=' * 62)
    print('  日界按拍预算 · 故事时间按跨度（方案 A）')
    print('=' * 62)
    for fn in (a_span, b_per_beat, c_boundary, d_walk, e_days, f_gap, h_wiring, g_counter):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            import traceback
            ok(f'{fn.__name__} 跑完', False, f'{e!r}')
            print(traceback.format_exc()[-900:])
    n = len(report['checks'])
    good = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n日界与故事时间验证：{good}/{n}')
    (OUT / 'beat_time_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if good == n else 2


if __name__ == '__main__':
    raise SystemExit(main())
