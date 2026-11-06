#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证：**场次编排** —— 一场戏接一场戏（2026-10-11）。

作者看了运行记录之后点名：

    「这些人很多时候会东一句西一句，有些小的场景没交代清楚，突然大家就跳到
      几个新场景了」「我还看到很多场景反复切换 却没有任何人物出场 动作 情节的
      —— 各种放到电视剧里就是无意义的场景切换，这是不对的」

查下来的结论是：**剧作家确实分了拍（那张表结构完整），但那张表没有下达，
运行时也没有"场"这个单位** —— 于是
  · 演员的提示词里只有一段 400 字的当天梗概 + 自己分到的两件事；
  · 分幕是**事后**按"时段变了 / 地点变了"切的，不是"这一拍演完了"；
  · 换场要等"场上一个人都不剩"，且目标地点恰好命中地点表。

所以这一支盯四件事：
  ① **下达**：剧作家写的每一拍（在哪 / 讲什么 / 有谁 / 要落到哪些动作 /
     动什么道具 / 情绪 / 演完的样子）真的进了演员的决策提示词；
     而且**只给当前这一拍**（把后面的戏透给他，他就会去抢别人那一场）。
  ② **收场**：该出场的都露过面 + 戏量够了 ⇒ 这一场收；没到齐接着演；
     到上限硬收（防一场戏无限拖）。
  ③ **换场**：收场后按**下一拍指定的地方**换，而不是等"人都走光"；
     地点不在表里就不换（宁可少切，也别把场面话当地名）。
  ④ **底线**：没有分拍时**什么都不做** —— 行为与加这一层之前**逐字相同**。
     这一条最要紧：新加的层绝不能把本来跑得通的推演弄坏。

产出：assets/screenshots/scene_beat_report.json

English:
Verify: **stage scheduling** -- one scene after another (2026-10-11).

After reading a run log the author called out:

    "these people are all over the place most of the time, some small scenes are never explained
     clearly and then everyone suddenly jumps to several new scenes" and "I also see many scenes
     switching back and forth with no character entering, no action, no plot -- on TV that is a
     meaningless scene change, and it is wrong".

The investigation concluded: **the playwright really did split beats (the sheet is structurally
complete), but that sheet was never handed down, and the runtime had no notion of a "scene"** --
therefore
  · an actor's prompt contained only a 400-character synopsis of the day plus his own two tasks;
  · act breaks happened **after the fact**, keyed on "the time slot changed / the location changed",
    not on "this beat is finished";
  · a scene change waited until "not a single person remained on stage", and only if the target
    location happened to be in the location table.

So this script watches four things:
  ① **Handed down**: every beat the playwright wrote (where / about what / who is in it / which
     actions it lands / which props / the mood / what "finished" looks like) really reaches the
     actor's decision prompt; and **only the current beat is given** (leaking later scenes makes him
     steal someone else's).
  ② **Wrap-up**: everyone who should appear has appeared + enough drama ⇒ wrap this scene up; if not
     everyone has shown, keep playing; at the cap, force a wrap-up (so a scene cannot drag forever).
  ③ **Scene change**: after wrapping up, change to **the place the next beat specifies**, instead of
     waiting for "everyone to leave"; a place not in the table is not switched to (better to switch
     less than to treat stage talk as a place name).
  ④ **Bottom line**: with no beat breakdown, **do nothing** -- behavior is **byte-for-byte identical**
     to before this layer existed. This one matters most: a newly added layer must never break a
     simulation that used to run fine.

Output: assets/screenshots/scene_beat_report.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG, SPEC  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
REPORT: dict = {'checks': []}

#: 这一支会动的配置项 —— 跑完**逐个还原**（不能把测试值留给下一个脚本）。
# [EN] : The config keys this script touches -- **restored one by one** when done (test values must
# [EN] not leak into the next script).
TOUCHED = ('SCENE_BEATS', 'SCENE_BEAT_MIN_TICKS', 'SCENE_BEAT_MAX_TICKS',
           'SCENE_BEAT_MIN_ACTS', 'MOCK_LLM')
_SAVED: dict = {}


def save_cfg() -> None:
    for k in TOUCHED:
        try:
            _SAVED[k] = CFG.raw(k) if hasattr(CFG, 'raw') else None
        except Exception:                                        # noqa: BLE001
            _SAVED[k] = None


def restore_cfg() -> None:
    for k, v in _SAVED.items():
        if v is None:
            continue
        try:
            CFG.set(k, v)
        except Exception:                                        # noqa: BLE001
            pass


def ok(name: str, cond, detail: str = '') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    print(f'  {"[OK]  " if cond else "[FAIL]"} {name}'
          + (f'  — {str(detail)[:170]}' if detail else ''), flush=True)
    return bool(cond)


def head(t: str) -> None:
    print(f'\n── {t} ──', flush=True)


#: 两拍，地点不同（用来验"按拍换场"）、名单与 `verify_run_control.make_project`
#: 造的三个人对得上（主角 / 柳氏 / 阿福）。
# [EN] : Two beats at different places (to verify "scene change by beat"); the names match the three
# [EN] people created by `verify_run_control.make_project` (主角 / 柳氏 / 阿福).
BEATS: list[dict] = [
    {'拍': 1, '场': '堂屋', '主题': '试鞋底', '出场': ['主角', '阿福'],
     '发生': '阿福点破鞋底干净', '要点': ['阿福问鞋底', '主角答不上'],
     '道具': ['抹布'], '情绪': '试探', '推进': '主角露了空'},
    {'拍': 2, '场': '院子', '主题': '翻旧案', '出场': ['柳氏'],
     '发生': '柳氏翻出旧账', '要点': ['柳氏摊开旧账本'],
     '道具': ['旧账'], '情绪': '压着火', '推进': '旧案浮头'},
]


# ══════════════════════════════════════════════════════════════
#  A. 纯逻辑
# [EN] A. Pure logic
# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    head('A. 场次编排（纯逻辑）')
    from director import stage as STAGE
    from director.day_plan import beats_text

    # ── A1/A2 建不建得起来 ──
    # [EN] -- A1/A2 whether it can be built --
    p = STAGE.StagePlan(BEATS, day=1)
    ok('A1 有分拍 ⇒ 编排建起来，当前是第 1 拍（场/主题都读对了）',
       p.total == 2 and p.index == 1 and p.current is not None
       and p.current.place == '堂屋' and p.current.topic == '试鞋底',
       f'total={p.total} index={p.index} current={p.current}')

    empty = STAGE.StagePlan([], day=1)
    ok('A2 ★★ 没有分拍 ⇒ `current` 为 None，提示词与收场判定都是空串'
       '（这一层**什么都不做** —— 不把跑得通的推演弄坏的底线）',
       empty.total == 0 and empty.current is None
       and empty.prompt_block('主角').strip() == ''
       and empty.done_reason() == '' and empty.enabled in (True, False),
       f'total={empty.total} prompt={empty.prompt_block("主角")!r}')

    # ── A3 收场判据四条 ──
    # [EN] -- A3 the four wrap-up criteria --
    CFG.set('SCENE_BEAT_MIN_TICKS', '2')
    CFG.set('SCENE_BEAT_MAX_TICKS', '6')
    CFG.set('SCENE_BEAT_MIN_ACTS', '2')
    q = STAGE.StagePlan(BEATS, day=1)
    q.observe(acted=1, present=['主角'])
    r_low = q.done_reason()
    q.observe(acted=0, present=['主角'])
    r_thin = q.done_reason()
    q.observe(acted=1, present=['阿福'])
    r_done = q.done_reason()
    ok('A3a ★ 跑不够「一场戏最少演几拍」⇒ **不收**'
       '（设太小会让一场戏和一拍一样长，反而更碎）',
       q.index == 1 and r_low == '' and r_thin == '',
       f'1拍后={r_low!r} 2拍后={r_thin!r}')
    ok('A3c ★★ 人都到齐 + 戏量够了 ⇒ **收场**，并把"为什么收"说清楚',
       '演完' in r_done and '3 拍' in r_done, r_done)

    hard = STAGE.StagePlan(BEATS, day=1)
    for _ in range(6):
        hard.observe(acted=1, present=['主角'])
    ok('A3d ★★ 到「一场戏最多演几拍」⇒ **硬收**'
       '（否则一场戏能无限拖下去）',
       '到上限' in hard.done_reason(), hard.done_reason())

    # ⚠ 单独验一次"人没到齐就不收"：上面 A3c 走后状态已经变了，所以新起一个。
    # [EN] ⚠ Verify "not everyone arrived ⇒ don't wrap" separately: the state changed after A3c, so
    # [EN] start a fresh plan.
    miss = STAGE.StagePlan(BEATS, day=1)
    for _ in range(3):
        miss.observe(acted=2, present=['主角'])
    ok('A3e ★★ 戏量早就够了、但**阿福一直没露面** ⇒ 仍然不收场',
       miss.done_reason() == '' and miss.missing_cast() == ['阿福'],
       f'done={miss.done_reason()!r} missing={miss.missing_cast()}')

    # ── A4 「本场」块带全了没有 ──
    # [EN] -- A4 is the "this scene" block complete --
    blk = p.prompt_block('主角')
    need = ['第 1 / 2 拍', '堂屋', '试鞋底', '主角、阿福', '阿福问鞋底',
            '抹布', '试探', '主角露了空', '你在其中']
    miss_a4 = [x for x in need if x not in blk]
    ok('A4 ★★★ 「本场」块把剧作家写的**每一样**都带上了'
       '（在哪 / 讲什么 / 有谁 / 要落到哪些动作 / 道具 / 情绪 / 演完的样子）',
       not miss_a4, f'缺={miss_a4}')
    ok('A4b ★★ 只给**当前这一拍**：第 2 拍的细节（要点、道具）一个字都没透'
       '（透了，演员就会去抢别人那一场）',
       '柳氏摊开旧账本' not in blk and '旧账' not in blk,
       blk.strip()[:160])

    ok('A5 「你在其中 / 这场戏没有你」跟着 `who` 走'
       '（不在名单里的人也知道该去做别的）',
       '你在其中' in p.prompt_block('主角')
       and '这场戏没有你' in p.prompt_block('柳氏'),
       p.prompt_block('柳氏').strip()[:100])

    # ── A6 验算看得到新字段吗 ──
    # [EN] -- A6 can verification see the new fields --
    bt = beats_text(BEATS)
    need2 = ['主题：试鞋底', '出场：主角、阿福', '要点：阿福问鞋底',
             '道具：抹布', '情绪：试探']
    miss_a6 = [x for x in need2 if x not in bt]
    ok('A6 ★★ 验算 / 排练看得到新字段（`beats_text`）—— '
       '看都看不到，就不可能判断"这场戏交代完整没有"',
       not miss_a6, f'缺={miss_a6}')

    # ── A7 模型给"一串"而不是数组 ──
    # [EN] -- A7 the model returns a string rather than an array --
    from crew import agents as CREW
    s = CREW._str_list('他问账；她不应，掌柜按住册子', 4, 60)
    n = CREW._cast_list('主角、阿福', {'主角', '阿福', '柳氏'})
    n2 = CREW._cast_list(['主角', '查无此人'], {'主角', '阿福', '柳氏'})
    ok('A7 ★ 模型给**一整句**也给**数组** ⇒ 两种都认（给串时按中英标点切开）',
       s == ['他问账', '她不应', '掌柜按住册子'] and n == ['主角', '阿福'],
       f's={s} n={n}')
    ok('A7b ★ `出场` 里**不在册的名字被丢掉** —— '
       '留着它，那一场永远等不到"人到齐"，收场条件就废了',
       n2 == ['主角'], n2)

    # ── A8 配置项 ──
    # [EN] -- A8 config keys --
    keys = ('SCENE_BEATS', 'SCENE_BEAT_MIN_TICKS', 'SCENE_BEAT_MAX_TICKS',
            'SCENE_BEAT_MIN_ACTS')
    miss_a8 = [k for k in keys if k not in SPEC]
    ok('A8 四个配置项都在（用户要能自己调，而不是改代码）',
       not miss_a8, f'缺={miss_a8}')
    CFG.set('SCENE_BEATS', 'false')
    ok('A8b ★ 关掉 `SCENE_BEATS` ⇒ 这一层不生效（`enabled` 为假）',
       p.enabled is False, f'enabled={p.enabled}')
    CFG.set('SCENE_BEATS', 'true')
    ok('A8c 打开 ⇒ 生效', p.enabled is True, f'enabled={p.enabled}')

    # ── A10 世界上的那两个字段 ──
    # [EN] -- A10 the two fields on the world --
    from world.state import WorldState
    from dataclasses import fields as _dc_fields
    _f = {f.name for f in _dc_fields(WorldState)}
    ok('A10 ★ `WorldState` 上有 `stage_plan` 与 `stage_index` 两个字段'
       '（提示词读前者、续跑读后者 —— 字段没了，两件事会静默失灵）',
       'stage_plan' in _f and 'stage_index' in _f,
       sorted(n for n in _f if 'stage' in n))

    # ── A9 演员的提示词（真方法，绑到替身对象上）──
    # [EN] -- A9 the actor's prompt (the real methods, bound onto a stand-in object) --
    group_a9(STAGE, p)


class _Fake:
    """只带 `world` 与 `name` 的替身 —— 用来直接调 `Agent._frame_line`。

    ⚠ 为什么要替身：真 `Agent` 要 world / db / persona 一整套才有意义，
      而 `_frame_line` / `_stage_line` **只读 `self.world` 与 `self.name`**。
      用替身调**同一个函数对象**，测的仍然是产品代码（不是复制一份逻辑）。

        English:
    A stand-in carrying only `world` and `name` -- used to call `Agent._frame_line` directly.
        ⚠ Why a stand-in: a real `Agent` needs world / db / persona to be meaningful, while
          `_frame_line` / `_stage_line` **only read `self.world` and `self.name`**.
          Calling the **same function object** through a stand-in still tests product code (it does
          not duplicate the logic).
    """

    def __init__(self, world, name: str) -> None:
        self.world = world
        self.name = name


def group_a9(STAGE, plan) -> None:
    from agent.core import Agent

    class _W:
        pass

    # ⚠★ 替身上必须把**这一条链上用到的方法都绑上**（2026-10-12 补 `_map_line`）。
    #   上一轮给 `_stage_line` 加了「地图事实」那一段（`self._map_line(...)`），
    #   而替身只绑了 `_frame_line` / `_stage_line` —— 于是 `self._map_line`
    #   当场 `AttributeError`，被 `_stage_line` 的 `except` 吞掉、返回空串，
    #   A9（「本场」有没有真的进提示词）就**默默变红**了：报的是"没出现本场"，
    #   真凶却是"替身少绑了一个方法"。产品代码没问题，判据的架子缺了一条腿。
    # [EN] ⚠★ The stand-in must have **every method used along this chain** bound (added
    # [EN] `_map_line` on 2026-10-12).
    # [EN] The previous round added the "map facts" block to `_stage_line` (`self._map_line(...)`),
    # [EN] while the stand-in only bound `_frame_line` / `_stage_line` -- so `self._map_line` raised
    # [EN] `AttributeError` on the spot, `_stage_line`'s `except` swallowed it and returned an empty
    # [EN] string, and A9 ("did this scene really reach the prompt") went quietly red: the message
    # [EN] said "this scene did not appear" while the real cause was "the stand-in is missing one
    # [EN] method". The product code was fine; the criterion's scaffold was missing a leg.
    _Fake._frame_line = Agent._frame_line
    _Fake._stage_line = Agent._stage_line
    _Fake._map_line = Agent._map_line
    w = _W()
    w.stage_plan = plan
    w.day_script = None
    a = _Fake(w, '主角')

    # ★★★ 2026-10-19：**A9 原判「一定出现本场」—— 那个前提已经被推翻了。**
    #
    #   用户把定位改成「推演工具」之后，加了 `AGENT_FREEDOM`：高自由度时
    #   **分拍表正是要被拿掉的那一样**（它就是"这一拍该演什么"）。
    #   于是"一定出现"不再成立 —— 但**不许因此把这条删掉**：
    #   它守的那件事（这一层真的接到演员身上了）仍然要守，只是变成**成对**：
    #     · 低自由度（0）：`本场` **必须在**（剧本档的契约）；
    #     · 高自由度（90）：`本场` **必须不在**（自由档的契约）。
    #   两条一起看，既证明接线，也证明**这个旋钮真的起作用**（一刀切不成对就会放水）。
    # [EN] ★★★ 2026-10-19: **A9 used to require "本场 always appears" -- that premise is gone.**
    # [EN] After the reposition and `AGENT_FREEDOM`, the beat sheet is exactly what gets removed at
    # [EN] high freedom. But **do not delete the check**: what it guards (this layer really reaches
    # [EN] the actor) still matters, so it becomes **paired**: low freedom => 本场 must be there;
    # [EN] high freedom => it must not. Together they prove the wiring AND that the knob works.
    from agent import freedom as _FR
    # ⚠ 2026-10-19：`freedom.level` 已拆成 `task_level` / `style_level`，
    #   这里判的是**剧本给多少**，所以用 `task_level`。
    _orig_level = _FR.task_level
    try:
        _FR.task_level = lambda: 0.0
        line_low = a._frame_line()
        _FR.task_level = lambda: 0.9
        line_high = a._frame_line()
    finally:
        _FR.task_level = _orig_level

    ok('A9 ★★★ 低自由度时演员的提示词里**真的出现了「本场」**'
       '（剧作家的表下达的落点 —— 这一条是整件事的中心）',
       '本场' in line_low and '试鞋底' in line_low and '抹布' in line_low,
       line_low.strip()[:150])

    ok('A9d ★★★ 成对：**高自由度时分拍表必须消失**'
       '（它就是"这一拍该演什么"；留着它，人物只是在演一场排好的戏）',
       '本场' not in line_high and '试鞋底' not in line_high,
       line_high.strip()[:150])

    # ⚠ A9b / A9c 必须在**低自由度**下判：不固定的话，它们会因为"自由度把本场拿掉了"
    #   而变绿 —— 那不是它们声称的「没有编排就不出现」，是**假绿**。
    # [EN] ⚠ A9b / A9c must run at **low freedom**: otherwise they go green because "the freedom
    # [EN] knob removed it", not because "there is no schedule" -- a false green.
    _w_plan = w.stage_plan
    try:
        _FR.task_level = lambda: 0.0
        w.stage_plan = None
        ok('A9b ★★ 没有编排 ⇒ 这一段不出现（行为与加这一层之前一样）',
           '本场' not in a._frame_line())

        w.stage_plan = plan
        CFG.set('SCENE_BEATS', 'false')
        ok('A9c ★ 关掉 `SCENE_BEATS` ⇒ 提示词里也不出现这一段'
           '（关得掉才算"可以退回从前"）',
           '本场' not in a._frame_line())
        CFG.set('SCENE_BEATS', 'true')
    finally:
        _FR.task_level = _orig_level
        w.stage_plan = _w_plan


# ══════════════════════════════════════════════════════════════
#  B. 真跑（真调 RunLoop 的收场与换场）
# [EN] B. Real run (actually calling RunLoop's wrap-up and scene change)
# ══════════════════════════════════════════════════════════════
async def group_b(tmp: Path) -> None:
    head('B. 真跑：收场与换场（真调 RunLoop 的方法）')
    from store.runfolder import RunFolder
    from sim.setup import assemble
    from verify_run_control import make_project
    from director.stage import StagePlan
    from agent.core import Action

    proj = make_project(tmp / '场次')
    run = RunFolder(proj.root, '第1次模拟2026-10-11-00-01').create()
    loop, world, db = assemble(proj, run)

    world.place_names = ['堂屋', '院子']
    world.scene = '堂屋'
    world.stage_index = 0
    stage = StagePlan(BEATS, day=1)
    world.stage_plan = stage
    loop._stage_plan = stage
    # ⚠ 测试里把门槛压到最低，让"收场"在这一支里能真的发生；
    #   门槛本身的值由 A3 那一组管（那里用的是真实默认值的关系）。
    # [EN] ⚠ Push the thresholds to the floor so a wrap-up can really happen inside this script; the
    # [EN] threshold values themselves are covered by group A3 (which works with the real defaults).
    CFG.set('SCENE_BEAT_MIN_TICKS', '1')
    CFG.set('SCENE_BEAT_MIN_ACTS', '1')
    CFG.set('SCENE_BEAT_MAX_TICKS', '6')

    dividers: list = []
    narratives: list = []
    scenes: list = []
    loop.on_divider(lambda d: dividers.append(d))
    loop.on_narrative(lambda text, prio, **kw: narratives.append(str(text)))
    loop.on_scene(lambda *a, **kw: scenes.append((a, kw)))

    def _act(name: str, verb: str = 'speak') -> tuple:
        who = type('A', (), {'name': name})()
        return (who, Action(verb=verb, dialogue='这是一句正经台词。'))

    # ① 一拍：主角到了，阿福还没露面 ⇒ 不该收
    # [EN] ① Beat 1: Shen Yan has arrived, A Fu has not shown up yet ⇒ should not receive
    loop._stage_observe([_act('主角')])
    loop._maybe_close_beat()
    ok('B1 ★ 该出场的**还没到齐** ⇒ 不收场（`stage_index` 不动）',
       int(getattr(world, 'stage_index', 0)) == 0,
       f'stage_index={getattr(world, "stage_index", None)}')

    # ② 第二拍：阿福到了 ⇒ 该收
    # [EN] ② Beat 2: A Fu has arrived ⇒ should receive
    loop._stage_observe([_act('阿福')])
    loop._maybe_close_beat()
    ok('B2 ★★ 人都到齐 + 戏量够 ⇒ **真的收场了**（`stage_index` 前进到 1）',
       int(getattr(world, 'stage_index', 0)) == 1,
       f'stage_index={getattr(world, "stage_index", None)} · ledger={stage.ledger_line()}')
    ends = [d for d in dividers
            if str(getattr(d, 'kind', '')) == 'scene_end']
    ok('B3 ★★ 收场推了一条「幕终」分隔符，而且**带上了"为什么收"**',
       bool(ends) and any(str(getattr(d, 'note', '') or '') for d in ends),
       f'{len(ends)} 条 · note={[str(getattr(d, "note", ""))[:30] for d in ends][:2]}')

    ok('B4 ★★ 换场按**下一拍指定的地方**（`堂屋` → `院子`），'
       '而不是等"人都走光"',
       str(getattr(world, 'scene', '')) == '院子',
       f'scene={getattr(world, "scene", "")!r}')

    # 演员被导演调过去了没有（第 2 拍该出场的是柳氏）
    # [EN] Has the actor been called over by the director yet (the one who should appear in beat 2 is Liu
    # [EN] Shi)
    ppl = getattr(world, 'people', {}) or {}
    liu = ppl.get('柳氏')
    ok('B5 ★★ 这一拍该出场的人被**调到了这个场**'
       '（否则就是"场景切了却没人"的老毛病）',
       liu is not None and str(getattr(liu, 'location', '')) == '院子',
       f'柳氏.location={getattr(liu, "location", None)!r}')

    ok('B6 ★ 中栏出现了「第 2 拍 · 院子 · 翻旧案」那一行'
       '（作者看得见"现在是第几拍、在演什么"）',
       any('翻旧案' in x for x in narratives),
       [x for x in narratives if '拍' in x][:2])

    # ③ 底线：没有编排时**什么都不做**
    # [EN] ③ Bottom line: when there is no blocking, **do nothing**
    n_div = len(dividers)
    loop._stage_plan = None
    world.stage_plan = None
    loop._stage_observe([_act('主角')])
    loop._maybe_close_beat()
    ok('B7 ★★ 没有编排 ⇒ 收场那一路**一步都不走**'
       '（分隔符没多、场景没动）',
       len(dividers) == n_div and str(getattr(world, 'scene', '')) == '院子',
       f'分隔符 {n_div} → {len(dividers)}')

    # ④ 整轮真跑不崩（mock）——加了这一层之后推演还得跑得起来
    # [EN] (4) A full round really runs without crashing (mock) -- after adding this layer the
    # [EN] simulation must still run.
    world.stage_plan = stage
    loop._stage_plan = stage
    try:
        await loop.run(max_ticks=3)
        crashed = ''
    except Exception as e:                                       # noqa: BLE001
        crashed = repr(e)
    ok('B8 ★★ 加了这一层之后，**整轮推演照样跑得起来**（mock 跑 3 拍不抛异常）',
       not crashed, crashed)


def main() -> int:
    # `--a-only`：只跑 A 组（纯逻辑、秒级）—— 反例法对那些变异用它，
    # 一次跑 18 条才不至于把时间全花在装配 world 上。
    # [EN] `--a-only`: run group A only (pure logic, seconds) -- the reverse experiments use it for
    # [EN] those mutations, otherwise 18 rounds would spend all their time assembling worlds.
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--a-only', action='store_true', help='只跑 A 组')
    args = ap.parse_args()

    save_cfg()
    tmp = Path(tempfile.mkdtemp(prefix='nws_stage_'))
    try:
        CFG.set('MOCK_LLM', 'true')
        group_a()
        if not args.a_only:
            asyncio.run(group_b(tmp))
    finally:
        restore_cfg()
        shutil.rmtree(tmp, ignore_errors=True)
    passed = sum(1 for c in REPORT['checks'] if c['ok'])
    total = len(REPORT['checks'])
    REPORT['passed'], REPORT['total'] = passed, total
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'scene_beat_report.json').write_text(
        json.dumps(REPORT, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n场次编排验证：{passed}/{total} 通过', flush=True)
    return 0 if passed == total else 1


if __name__ == '__main__':
    raise SystemExit(main())
