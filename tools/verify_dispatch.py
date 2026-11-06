# -*- coding: utf-8 -*-
"""验证：导演**派活**（`DISPATCH_EVERY_TICKS`）+ **五层目标金字塔**（`GOAL_LADDER`）。

用户 2026-10-06：「影视剧的优化都做掉」。#132 这两件。

先说一个查证结果：**这两个旋钮以前根本不存在**（全项目零命中）——
之前那份"待办清单"里写的"DISPATCH_EVERY_TICKS / GOAL_LADDER 零读取"其实是
**零存在**。所以这一轮是"新建旋钮 + 实现"。

判据分四层（每层都要能红，见 `developers/mutate_dispatch.py`）：
  A **金字塔**：层数按 `GOAL_LADDER`、顺序由近及远、**空层不占名额**；
     ★★ 反空转闸**故意不算「此刻」**（派活是导演给的，拿它当判据等于把闸废掉）。
  B **派活本身**：只派在场的人；**不写"怎么做"**；拿不到就**不写**（不清空上一条）。
  C **接线**：`_maybe_dispatch` 真的每 N 拍调一次、真的写进 `ps.mission`、
     真的推 NOTE；而且那层**真的进了决策提示词**（模型看到的 prompt 里有 `[此刻]`）。
  D **旋钮真被读**：`DISPATCH_EVERY_TICKS=0` 关得掉。
  E **卡死放行闸**（2026-10-19 第十二轮）：`_mission_still_running` 在"关键词一直在、
     事一直没办成"这一形状下会**永真**，而拦人时不清 `ps.mission` ⇒ 人会被永久锁在
     同一件没办成的事上（snow_v11 实录：连拦两轮，第三轮起再无新目标）。
     新旋钮 `DISPATCH_STUCK_ROUNDS`：连续被拦几轮就判卡死、强制换新的。
     ★ 必须**成对**判：E2 判"该放行时真放行"，E3 判"关掉闸后他真的每轮都被拦、
     目标一个字节都不变"（否则 E2 可能只是测试里没触发拦截）。

用法：.venv\\Scripts\\python.exe tools/verify_dispatch.py
产出：assets/screenshots/dispatch_report.json

English:
Verification: director **dispatch** (`DISPATCH_EVERY_TICKS`) + **five-layer goal pyramid**
(`GOAL_LADDER`).
User 2026-10-06: "do all the film/TV optimizations". #132 these two.
First a verification result: **these two knobs did not exist before** (zero hits across the
project) --
what the earlier "to-do list" said, "DISPATCH_EVERY_TICKS / GOAL_LADDER zero reads", was
actually
**zero existence**. So this round is "create the knobs + implement".
The criterion has four layers (each must be able to go red, see
`developers/mutate_dispatch.py`):
  A **Pyramid**: layer count follows `GOAL_LADDER`, order from near to far, **empty layers do not take a slot**;
     ★★ the anti-idle gate **deliberately does not count "this moment"** (dispatch is given by the director; using it as a criterion is equivalent to scrapping the gate).
  B **Dispatch itself**: only dispatch to present people; **do not write "how to do it"**; if unavailable **do not write** (do not clear the previous entry).
  C **Wiring**: `_maybe_dispatch` is really called once every N ticks, really writes to `ps.mission`,
     really pushes a NOTE; and that layer **really reaches the decision prompt** (the prompt the model sees contains `[this moment]`).
  D **Knobs really read**: `DISPATCH_EVERY_TICKS=0` can turn it off.
Usage: .venv\\Scripts\\python.exe tools/verify_dispatch.py
Output: assets/screenshots/dispatch_report.json
"""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import sys
import textwrap
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from config import CFG                                         # noqa: E402
# ⚠ 一个像素都不量、不弹窗、**绝不点会 `CFG.save()` 的按钮**（见 MEMORY 的铁律）。
# [EN] ⚠ Not a single pixel measured, no popups, **never click a button that would call `CFG.save()`**
# [EN] (see the iron rule in MEMORY).
CFG.set('MOCK_LLM', 'true')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


class FakeDB:
    """够用的假库：只回答"最近事件"与"检索记忆"。
        English:
    Sufficient fake library: only answers "recent events" and "retrieve memory".
    """

    def __init__(self, events=None):
        self._events = list(events or [])

    def recent_events(self, n=5):
        return self._events[-n:]

    def retrieve_memory(self, *a, **k):
        return []

    def add_event(self, *a, **k):
        pass


def make_agent(world, mission='', day_plan=(), goal='找到妹妹', db=None):
    """用**真构造器**造 Agent（别 `__new__` + 手塞属性：`name` 是只读属性，
    手塞会炸，而且真实构造出来的对象才是被测的那个）。
        English:
    Use the **real constructor** to build the Agent (don't `__new__` + manually stuff attributes:
    `name` is a read-only property,
        manually stuffing will blow up, and only an object built by the real constructor is the one under test).
    """
    from agent.core import Agent
    from world.state import PersonState
    ps = PersonState(name='阿九', location=world.scene, role='前台',
                     current_goal=goal)
    ps.mission = mission
    ps.day_plan = list(day_plan)
    world.people['阿九'] = ps
    return Agent(ps, db or world._db, world)


def make_world(db=None):
    from world.state import WorldState, GameTime
    w = WorldState()
    w.scene = '临河茶肆'
    w.clock = GameTime()
    w._db = db or FakeDB()
    w.progress_nodes = [
        {'id': 'N1', '名称': '楼前失忆', '概要': '阿福初到', '完成判据': '被收留'},
        {'id': 'N2', '名称': '第一桩委托', '概要': '聊斋界来了客人', '完成判据': '了结'},
    ]
    w.current_node = 'N1'
    return w


# ══════════════════════════════════════════════════════════════
#  A. 目标金字塔
# [EN] A. Goal pyramid
# ══════════════════════════════════════════════════════════════
def test_ladder() -> bool:
    allok = True
    w = make_world()
    a = make_agent(w, mission='把账房夜里的事弄清楚',
                   day_plan=['开门', '巡铺'])
    saved = CFG.raw('GOAL_LADDER')
    try:
        want = {2: ['此刻', '这一站'], 3: ['此刻', '这一站', '今日计划'],
                4: ['此刻', '这一站', '今日计划', '这一程'],
                5: ['此刻', '这一站', '今日计划', '这一程', '你想要的']}
        for n, layers in want.items():
            CFG.set('GOAL_LADDER', str(n))
            got = [x for x, _ in a._ladder_layers()]
            allok &= ok(f'A1 GOAL_LADDER={n} → 层 = {" / ".join(layers)}',
                      got == layers, str(got))
        CFG.set('GOAL_LADDER', '5')
        blocks = a._goal_ladder()
        allok &= ok('A2 五层**按由近及远的顺序**拼进提示词',
                  [blocks.find(f'[{x}]') for x in ('此刻', '这一站', '今日计划',
                                                   '这一程', '你想要的')]
                  == sorted(blocks.find(f'[{x}]') for x in
                            ('此刻', '这一站', '今日计划', '这一程', '你想要的')),
                  blocks.replace('\n', ' | ')[:200])
        allok &= ok('A2 ★ 「这一程」取的是进度表里**当前节点的下一个**',
                  '第一桩委托' in blocks, blocks[:200].replace('\n', ' | '))

        # ★ 空层不占名额：没派活、没计划的人，照样看得到他真正有的那几层
        # [EN] ★ Empty layers do not take up a slot: someone with no assignment and no plan still sees exactly
        # [EN] the layers they actually have
        a2 = make_agent(w, mission='', day_plan=[], goal='')
        allok &= ok('A3 ★ 空的层**不占名额**（只剩这一站/这一程两层）',
                  [x for x, _ in a2._ladder_layers()] == ['这一站', '这一程'],
                  str([x for x, _ in a2._ladder_layers()]))

        # ★★ 反空转闸不许把「此刻」算进去
        # [EN] ★★ The anti-idle gate must not count "this moment"
        a3 = make_agent(w, mission='导演派的活', day_plan=[], goal='')
        w3 = make_world()
        w3.current_node_info = lambda: None
        w3.progress_nodes = []
        w3.current_node = ''
        a3.world = w3
        allok &= ok('A4 ★★ 反空转闸**故意不算「此刻」**（只给派活也算"没目标"）',
                  a3._all_goals_empty() is True,
                  f'all_empty={a3._all_goals_empty()}')
        a3.ps.day_plan = ['开门']
        allok &= ok('A4 有自己的计划 → 闸门不触发', a3._all_goals_empty() is False)
    finally:
        CFG.set('GOAL_LADDER', saved)
    return allok


# ══════════════════════════════════════════════════════════════
#  B. 派活本身
# [EN] B. Dispatch itself
# ══════════════════════════════════════════════════════════════
def test_dispatch() -> bool:
    allok = True
    from director.engine import DirectorEngine
    from director import engine as E
    w = make_world(FakeDB([{'content': '阿九在擦门柱'}]))
    eng = DirectorEngine.__new__(DirectorEngine)
    eng.world = w
    eng.db = w._db

    seen: dict = {}
    real = E.ask

    async def fake_ask(tier, messages, **kw):
        from llm.replies import Reply
        seen['prompt'] = messages[-1]['content']
        return Reply(value={'派活': [
            {'人物': '阿九', '要什么': '弄清楚夜里是谁动过账'},
            {'人物': '不在场的人', '要什么': '凑数的'},      # 不在场 → 该被丢掉
            {'人物': '阿九', '要什么': ''},                  # 空任务 → 该被丢掉
            # [EN] Not present → should be dropped
            # [EN] Empty task → should be dropped
        ]}, ok=True)

    E.ask = fake_ask
    try:
        got = asyncio.run(eng.dispatch(['阿九', '阿福']))
        p = seen.get('prompt', '')
        allok &= ok('B1 ★ 提示词明确要求「只写要达成什么，绝不写怎么做」',
                  '只写「要达成什么」' in p and '绝不写「怎么做」' in p,
                  p[:160].replace('\n', ' | '))
        allok &= ok('B1 ★★ 派活只认**在场的人**（"不在场的人"被丢掉）',
                  list(got) == ['阿九'], str(got))
        allok &= ok('B1 空任务丢掉（不给"要什么"为空的）',
                  got.get('阿九') == '弄清楚夜里是谁动过账', str(got))
    finally:
        E.ask = real

    # 拿不到 → 空 dict（**不编**）
    # [EN] Unavailable → empty dict (**do not fabricate**)
    E.ask = lambda *a, **k: _async(None)
    try:
        # 让 ask 返回一个 ok=False 的 Reply
        # [EN] Have ask return a Reply with ok=False
        E.ask = _bad_ask
        got2 = asyncio.run(eng.dispatch(['阿九']))
        allok &= ok('B2 ★ 拿不到结果 → 空 dict（不编派活）', got2 == {}, str(got2))
    finally:
        E.ask = real
    return allok


def _async(v):
    async def _f():
        return v
    return _f()


async def _bad_ask(*a, **k):
    from llm.replies import Reply
    return Reply(ok=False, notes=['模型没返回'])


# ══════════════════════════════════════════════════════════════
#  C. 接线：真的每 N 拍调、真的写进去、真的进提示词
# [EN] C. Wiring: actually called every N ticks, actually written, actually reaches the prompt
# ══════════════════════════════════════════════════════════════
def test_wiring() -> bool:
    allok = True
    from sim.loop import RunLoop
    from director.engine import DirectorEngine
    from world.state import PersonState

    w = make_world()
    # 「在场」判定走 `is_on_stage`：在场 + 前台 + **地点对得上**。
    # ⚠ 这里**必须有一个场外的人**（阿福在后院）：第一版只放了一个在场的，
    #   于是"派活不看在场"这个变异**测不出来**（反例法抓到的）。
    # [EN] "Present" is determined via `is_on_stage`: on stage + foreground + **location matches**.
    # [EN] ⚠ There **must be someone off stage** here (A-Fu is in the backyard): the first version only had
    # [EN] one present person,
    # [EN] so the mutation "dispatch ignores presence" **could not be detected** (caught by the
    # [EN] counterexample method).
    w.people = {
        '阿九': PersonState(name='阿九', location='临河茶肆', role='前台'),
        '阿福': PersonState(name='阿福', location='后院', role='前台'),
    }

    class P:
        def __init__(self, name):
            self.name = name
            self.ps = w.people[name]

    class D:
        def __init__(self):
            self.calls = 0
            self.last_people: list[str] = []

        async def dispatch(self, people):
            self.calls += 1
            self.last_people = list(people)
            return {n: f'派给{n}的活' for n in people}

    class Disp:
        async def enqueue_narrative(self, *a, **k):
            pass

    loop = RunLoop.__new__(RunLoop)
    loop.world = w
    loop.agents = [P('阿九'), P('阿福')]     # 阿福在后院 → 不在场，派活不该给他
    # [EN] A-Fu is in the backyard → not present, dispatch should not be given to him
    loop.director = D()
    loop.display = Disp()
    loop._cb_warned = set()
    loop._on_status = None
    notes: list[str] = []
    loop._on_narrative = lambda text, pri, kind='': notes.append(text)

    saved = CFG.raw('DISPATCH_EVERY_TICKS')
    try:
        CFG.set('DISPATCH_EVERY_TICKS', '3')
        for tick in (1, 2, 3, 4, 5, 6):
            asyncio.run(loop._maybe_dispatch(tick))
        allok &= ok('C1 ★★ 每 3 拍调一次（1~6 拍 → 正好 2 次）',
                  loop.director.calls == 2, f'{loop.director.calls} 次')
        allok &= ok('C1 ★★ 派活只给**在场**的人（后院那位不该被派）',
                  loop.director.last_people == ['阿九'],
                  str(loop.director.last_people))
        allok &= ok('C1 ★★ 派活真的写进了 `ps.mission`（不是只返回值）',
                  loop.world.people['阿九'].mission == '派给阿九的活',
                  repr(loop.world.people['阿九'].mission))
        allok &= ok('C1 ★ 派活推了一条 NOTE（导演做的事不该是隐形的）',
                  any('（导演派活）' in x for x in notes), str(notes[:2]))
        allok &= ok('C1 提示词里能看到它',
                  '（导演派活）阿九：派给阿九的活' in ' '.join(notes),
                  ' '.join(notes)[:120])

        CFG.set('DISPATCH_EVERY_TICKS', '0')
        loop.director.calls = 0
        for tick in (3, 6, 9):
            asyncio.run(loop._maybe_dispatch(tick))
        allok &= ok('C2 ★ `DISPATCH_EVERY_TICKS=0` 关得掉（旋钮真被读）',
                  loop.director.calls == 0, f'{loop.director.calls} 次')
    finally:
        CFG.set('DISPATCH_EVERY_TICKS', saved)
    return allok


# ══════════════════════════════════════════════════════════════
#  E. 派活**卡死放行闸**（2026-10-19 第十二轮）
# [EN] E. Dead-stuck release valve for assignments (2026-10-19 round 12)
# ══════════════════════════════════════════════════════════════
def _run_stuck(cap: int, rounds: int = 3):
    """搭一个"**关键词一直在、事一直没办成**"的场景，连跑 `rounds` 轮派活。

    返回 `(是否换到新目标, 每轮之后的 stuck, 最终 mission, director 被调次数)`。

    ⚠ 夹具走**生产侧 API** 造"他一直在办那件事"：`world.note_line(..., kind=...)`
       的 kind 取 `WorldState.ACT_KINDS` / `SPEAK_KINDS` 里真会出现的字符串
       （`act` / `speak`），不自己造 kind —— 本项目踩过"自造 kind ⇒ 判据全绿而
       生产侧从不写这个字符串"的坑。
    ⚠ 场景必须**每轮都往窗口里添新的同关键词言行**：这才是实测的卡住形状
       （snow_v11：同一个人被连拦两轮，第三轮起再无新目标，当天条目少三分之一）。
        English:
    Build a "keywords keep appearing, thing never gets done" scene and run `rounds`
    dispatch rounds. ⚠ The fixture uses the **production-side API**.
    """
    from sim.loop import RunLoop
    from world.state import PersonState

    w = make_world()
    w.people = {'阿九': PersonState(name='阿九', location='临河茶肆', role='前台')}
    ps = w.people['阿九']
    ps.mission = '哨兵_旧派活'

    class P:
        def __init__(self, name):
            self.name = name
            self.ps = w.people[name]

    class D:
        def __init__(self):
            self.calls = 0

        async def dispatch(self, people):
            self.calls += 1
            return {n: f'哨兵_新派活{self.calls}' for n in people}

    class Disp:
        async def enqueue_narrative(self, *a, **k):
            pass

    loop = RunLoop.__new__(RunLoop)
    loop.world = w
    loop.agents = [P('阿九')]
    loop.director = D()
    loop.display = Disp()
    loop._cb_warned = set()
    loop._on_status = None
    loop._on_narrative = lambda *a, **k: None

    saved = CFG.raw('DISPATCH_STUCK_ROUNDS')
    saved_every = CFG.raw('DISPATCH_EVERY_TICKS')
    trace: list[int] = []
    try:
        CFG.set('DISPATCH_STUCK_ROUNDS', str(cap))
        CFG.set('DISPATCH_EVERY_TICKS', '8')
        for i in range(rounds):
            # 他这一轮又"办"了那件旧派活（关键词继续出现，事没办成）
            # [EN] This round he "worked on" that old assignment again (keywords keep
            # [EN] appearing, thing still not done)
            w.note_line('阿九', f'第{i}轮继续办：哨兵_旧派活', kind='act')
            w.note_line('阿九', '哨兵_旧派活还没办成', kind='speak')
            asyncio.run(loop._maybe_dispatch(8 * (i + 1)))
            trace.append(ps.mission_stuck)
    finally:
        CFG.set('DISPATCH_STUCK_ROUNDS', saved)
        CFG.set('DISPATCH_EVERY_TICKS', saved_every)
    return (ps.mission != '哨兵_旧派活'), trace, ps.mission, loop.director.calls


def test_stuck_release() -> bool:
    """E 组：派活**卡死放行闸** —— 治 v11 字数暴跌的第二个原因。

    `_mission_still_running` 在"关键词一直在、事一直没办成"这一形状下会**永真**，
    而 `_maybe_dispatch` 拦人时**不清 `ps.mission`** ⇒ 越卡住越永远派不到活。
    真跑实录（snow_v11）：同一个人被连拦两轮，第三轮起再无新目标。

    判据全部**行为判**（不读"源码里有没有某个词"）：
      E1 纯函数：轮数 < cap 不放行 / == cap 放行 / cap<=0 永不放行。
      E2 端到端：关键词一直在的人，第三轮**强制换到新目标**，且前两轮确实被拦过。
      E3 ★★ **成对**：关掉闸后，同场景他**每轮都被拦、目标一个字节都没变**。
         —— 没有这一条，"换到新目标"可能只因测试里压根没触发拦截。
      E4 字段真接上：`PersonState.mission_stuck` 存在；`_maybe_dispatch` 直接读它，
         不 `getattr` 兜默认值（兜了就看不出"字段没接上"）。
      E5 旋钮在配置表、同组、默认 2（**不默认关** —— 老行为会把人锁死一整晚）。
      E6 派到新活 ⇒ 记账归零（不是只在"放行"那一刻归零）。
        English:
    E group: the dead-stuck release valve. All criteria are **behavioural**.
        E3 is the **paired** criterion: with the valve off, the same scene must block him
    every round and never change the goal by a byte.
    """
    allok = True
    import inspect
    from sim.loop import RunLoop, stuck_mission_release
    from world.state import PersonState

    # ---- E1 纯函数 ----
    # [EN] E1 Pure function: rounds vs release
    allok &= ok('E1 被拦 1 轮、cap=2 → 还不算卡死（正常在办要留得住）',
              stuck_mission_release(1, 2) is False, 'rounds=1,cap=2')
    allok &= ok('E1 被拦 2 轮、cap=2 → 判卡死，放行',
              stuck_mission_release(2, 2) is True, 'rounds=2,cap=2')
    allok &= ok('E1 被拦 9 轮、cap=2 → 仍然判卡死（不会"放过"）',
              stuck_mission_release(9, 2) is True, 'rounds=9,cap=2')
    allok &= ok('E1 cap=0 → 永不放行（关闸 = 回到老行为）',
              stuck_mission_release(99, 0) is False, 'rounds=99,cap=0')
    allok &= ok('E1 rounds=0 → 不放行（一轮都没被拦，谈不上卡）',
              stuck_mission_release(0, 2) is False, 'rounds=0,cap=2')

    # ---- E2 端到端 ----
    # [EN] E2 End to end
    changed, trace, mission, calls = _run_stuck(2, rounds=3)
    allok &= ok('E2 ★★ 关键词一直在、事没办成 ⇒ 前两轮被拦，第三轮**强制换到新目标**',
              changed and mission == '哨兵_新派活3', f'mission={mission!r}')
    allok &= ok('E2 前两轮确实被拦过（不是"根本没触发拦截"）',
              trace[:2] == [1, 2], f'stuck 轨迹={trace}')
    allok &= ok('E2 ★ 放行后记账归零（只在被拦时 +1）',
              trace[-1] == 0, f'stuck 轨迹={trace}')
    allok &= ok('E2 三轮派活导演都被问了（派活没被整体关掉）',
              calls == 3, f'{calls} 次')

    # ---- E3 ★★ 成对判据 ----
    # [EN] E3 ★★ Paired criterion
    changed0, trace0, mission0, _c0 = _run_stuck(0, rounds=3)
    allok &= ok('E3 ★★ 关闸（cap=0）⇒ 三轮全被拦，`ps.mission` **一个字节都没变**',
              (not changed0) and mission0 == '哨兵_旧派活' and trace0 == [1, 2, 3],
              f'mission={mission0!r} stuck={trace0}')
    allok &= ok('E3 ★★ 关闸时轮次**照记**（打开闸当天就能用，不用等一晚）',
              trace0[-1] == 3, f'stuck 轨迹={trace0}')

    # ---- E4 字段真接上（不许 getattr 兜）----
    # [EN] E4 The field is really wired (no getattr fallback)
    ps4 = PersonState(name='阿九')
    allok &= ok('E4 ★ `PersonState.mission_stuck` 真存在且默认 0',
              ps4.mission_stuck == 0, f'mission_stuck={ps4.mission_stuck!r}')
    fnames = {f.name for f in dataclasses.fields(PersonState)}
    allok &= ok('E4 ★★ 它在 `dataclasses.fields` 里（不是靠 `__init__` 外挂的属性）',
              'mission_stuck' in fnames, str(sorted(fnames)[:12]))

    def ast_scan(fn) -> tuple[bool, bool]:
        """AST 扫一个函数体：`(有没有直接用 ps.mission_stuck, 有没有 getattr 兜)`。

        ⚠ **不许用"源码含字符串"判**（本项目纪律）：用 `getattr(ps, "mission_stuck", 0)`
          写就一样能过"含 `ps.mission_stuck`"这种判法 —— 引号一换就漏。
          走 AST 才分得清"真正的属性访问"和"字符串参数里的字"。
        [EN] AST-scan a function body: `(direct `ps.mission_stuck`?, getattr fallback?)`.
        [EN] ⚠ Never judge by substring: `getattr(ps, "mission_stuck", 0)` would pass a
        [EN] "contains `ps.mission_stuck`" check the moment the quotes change. Only AST tells
        [EN] a real attribute access from characters inside a string argument.
        """
        import ast as _ast
        tree = _ast.parse(textwrap.dedent(inspect.getsource(fn)))

        class _V(_ast.NodeVisitor):
            def __init__(self):
                self.direct = False
                self.fallback = False

            def visit_Attribute(self, node):
                if node.attr == 'mission_stuck' and isinstance(node.value, _ast.Name) \
                        and node.value.id == 'ps':
                    self.direct = True
                self.generic_visit(node)

            def visit_Call(self, node):
                f = node.func
                if isinstance(f, _ast.Name) and f.id == 'getattr' and len(node.args) >= 2:
                    a1 = node.args[1]
                    if isinstance(a1, _ast.Constant) and a1.value == 'mission_stuck':
                        self.fallback = True
                self.generic_visit(node)

        v = _V()
        v.visit(tree)
        return v.direct, v.fallback

    # ★★ 2026-10-26：**扫的对象跟着代码搬家了，不是判据放宽**。
    #   那套"卡死就放行"的循环从 `_maybe_dispatch` 里抽成了 `_apply_missions`
    #   （`_maybe_dispatch` 只剩一句 `missions = self._apply_missions(...)`）。
    #   原来钉在旧函数上 ⇒ 永远扫不到 `ps.mission_stuck`，红的是判据不是产品。
    #   判据要问的事没变：**这个字段是直接读的，还是 `getattr` 兜着读的**。
    # [EN] ★★ 2026-10-26: **the scanned target moved with the code; the criterion was not
    # [EN] relaxed**. The "stuck => release" loop was extracted out of `_maybe_dispatch` into
    # [EN] `_apply_missions` (leaving one delegation line behind). Pinned to the old function it can
    # [EN] never see `ps.mission_stuck` -- the criterion is red, not the product. The question is
    # [EN] unchanged: **is the field read directly, or through a `getattr` fallback?**
    direct_d, fallback_d = ast_scan(RunLoop._apply_missions)
    allok &= ok('E4 ★★ `_apply_missions` 里 AST 扫得到**真正的属性读** `ps.mission_stuck`'
              '（2026-10-26 从 `_maybe_dispatch` 抽出来的那段）',
              direct_d, f'direct={direct_d} fallback={fallback_d}')
    allok &= ok('E4 ★★ 而且**没有** `getattr(..., "mission_stuck", ...)` 兜底'
              '（兜底会让"字段没接上"永远不可见）',
              not fallback_d, f'direct={direct_d} fallback={fallback_d}')
    direct_s, fallback_s = ast_scan(RunLoop._mission_stuck)
    allok &= ok('E4 ★★ `_mission_stuck` 自己也不兜底',
              (not fallback_s), f'direct={direct_s} fallback={fallback_s}')
    body = inspect.getsource(RunLoop._apply_missions)
    # ⚠ 原来是 `== 2`（"恰好两处清零"）。抽出 `_apply_missions` 之后多了一条
    #   "被导演点名强制换活"的清零路径，变成了 3 处 —— 那是对的，不是退步。
    #   判据要守的是**成对**：既有自增、也有清零，缺一边就等于"卡死永远不放行"或
    #   "每轮都放行"。**不写死条数**（数条数的判据一改代码就假红）。
    # [EN] ⚠ It used to be `== 2` ("exactly two zeroings"). After extracting
    # [EN] `_apply_missions` a third path appeared ("the director named him, force a new task") --
    # [EN] which is correct, not a regression. What the criterion guards is the **pair**: an
    # [EN] increment and a zeroing; lose one side and either "never releases" or "always releases".
    # [EN] **Do not hardcode the count** (counting criteria go falsely red on any refactor).
    allok &= ok('E4 ★ 放行与归零是**成对**写的（同一段循环里既有自增、也有清零）',
              body.count('ps.mission_stuck = 0') >= 2
              and 'ps.mission_stuck = ps.mission_stuck + 1' in body,
              f'清零 {body.count("ps.mission_stuck = 0")} 处 / 自增 '
              f'{body.count("ps.mission_stuck = ps.mission_stuck + 1")} 处')
    allok &= ok('E4 ★★ 纯函数 `stuck_mission_release` 是模块级、可直接 import 的'
              '（判据不能只钉方法体，纯逻辑要能单独测）',
              callable(stuck_mission_release)
              and inspect.getmodule(stuck_mission_release).__name__ == 'sim.loop',
              f'{stuck_mission_release.__module__}')

    # ---- E5 旋钮在配置表 ----
    # [EN] E5 The knob is in the config table
    from config import SPEC
    sp = SPEC.get('DISPATCH_STUCK_ROUNDS') or {}
    allok &= ok('E5 ★ `DISPATCH_STUCK_ROUNDS` 在配置表里，type=int、默认 2（**不默认关**）',
              sp.get('type') == 'int' and sp.get('default') == 2, str(sp)[:160])
    allok &= ok('E5 ★ 同组「导演引擎」（和 DISPATCH_EVERY_TICKS 摆在一起）',
              sp.get('group') == '导演引擎', str(sp.get('group')))
    allok &= ok('E5 ★ 下限 0（0 = 关闸，老行为，可能把人锁死一整晚）',
              sp.get('min') == 0, f"min={sp.get('min')!r}")
    allok &= ok('E5 ★ `.env` 没写时 `CFG.i()` 回落到默认 2（不是 0）',
              CFG.i('DISPATCH_STUCK_ROUNDS') == 2,
              f"i()={CFG.i('DISPATCH_STUCK_ROUNDS')}")
    allok &= ok('E5 ★ `DISPATCH_EVERY_TICKS` 仍在（没被这次改动碰坏）',
              CFG.i('DISPATCH_EVERY_TICKS') == 8,
              f"i()={CFG.i('DISPATCH_EVERY_TICKS')}")

    # ---- E6 派到新活 ⇒ 记账归零 ----
    # [EN] E6 A new assignment zeroes the counter (not just the release moment)
    w6 = make_world()
    w6.people = {'阿九': PersonState(name='阿九', location='临河茶肆', role='前台')}
    w6.people['阿九'].mission_stuck = 7
    _run_stuck_on(w6, 2, rounds=1)
    allok &= ok('E6 ★ 攒了 7 轮的人一拿到新活就归零（不是永远背着旧账）',
              w6.people['阿九'].mission_stuck == 0,
              f'mission_stuck={w6.people["阿九"].mission_stuck}')
    allok &= ok('E6 ★ 而且真换到了新目标',
              w6.people['阿九'].mission == '哨兵_新派活X',
              repr(w6.people['阿九'].mission))
    return allok


def _run_stuck_on(w, cap: int, rounds: int = 1):
    """在**既有世界**上跑派活（给 E6 用：验证"派到新活就归零"）。"""
    from sim.loop import RunLoop

    class P:
        def __init__(self, name):
            self.name = name
            self.ps = w.people[name]

    class D:
        async def dispatch(self, people):
            return {n: '哨兵_新派活X' for n in people}

    class Disp:
        async def enqueue_narrative(self, *a, **k):
            pass

    loop = RunLoop.__new__(RunLoop)
    loop.world = w
    loop.agents = [P('阿九')]
    loop.director = D()
    loop.display = Disp()
    loop._cb_warned = set()
    loop._on_status = None
    loop._on_narrative = lambda *a, **k: None
    saved = CFG.raw('DISPATCH_STUCK_ROUNDS')
    try:
        CFG.set('DISPATCH_STUCK_ROUNDS', str(cap))
        for i in range(rounds):
            asyncio.run(loop._maybe_dispatch(8 * (i + 1)))
    finally:
        CFG.set('DISPATCH_STUCK_ROUNDS', saved)


def test_prompt_has_ladder() -> bool:
    """★★ 「〔此刻〕那一层真的进了人物决策的 prompt」—— 端到端。

    只判 `_goal_ladder()` 的输出是不够的（"测了实现、没测接线"）：
    要打桩 `llm.chat`、真跑一遍 `decide()`，看**模型收到的 prompt** 里有没有它。
    
        English:
    ★★ "The layer `〔this moment〕` really entered the character decision prompt" -- end to end.
        Only judging the output of `_goal_ladder()` is not enough ("tested the implementation, not the wiring"):
        you must stub `llm.chat`, really run `decide()` once, and check whether the **prompt the model receives** contains it.
    """
    allok = True
    from agent import core as AC
    w = make_world()
    # ⚠ 五层都**得有内容**才看得全（空层不占名额是 A3 特意验的行为）——
    #   第一版这里只给了 mission，于是「今日计划」那层本来就该空着，
    #   判据却要求五行俱全 → 假红。**判据要跟被验的规则对齐**。
    # [EN] ⚠ All five layers **must have content** for the full view (empty layers not taking a slot is the
    # [EN] behavior A3 specifically verifies) --
    # [EN] the first version only gave mission here, so the "today's plan" layer was supposed to be empty
    # [EN] anyway,
    # [EN] yet the criterion demanded all five rows be present → false red. **The criterion must align with
    # [EN] the rule being verified**.
    a = make_agent(w, mission='哨兵_派活内容ABC',
                   day_plan=['开门', '巡铺'])
    seen: dict = {}
    real = AC.llm.chat

    async def fake_chat(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''
        return json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                           '内心': '', '理由': '测试'}, ensure_ascii=False)

    AC.llm.chat = fake_chat
    saved = CFG.raw('GOAL_LADDER')
    try:
        CFG.set('GOAL_LADDER', '5')
        asyncio.run(a.decide())
        p = seen.get('prompt', '')
        allok &= ok('C3 ★★ 派活那一层**真的进了**决策提示词（`[此刻]` + 哨兵内容）',
                  '[此刻]' in p and '哨兵_派活内容ABC' in p,
                  p[:200].replace('\n', ' | '))
        allok &= ok('C3 ★★ 五层都在 prompt 里',
                  all(f'[{x}]' in p for x in ('此刻', '这一站', '今日计划',
                                             '这一程', '你想要的')),
                  ' '.join(x for x in ('此刻', '这一站', '今日计划', '这一程',
                                       '你想要的') if f'[{x}]' in p))
        n_layers = len(a._ladder_layers())
        allok &= ok(f'C3 那句话说清了「几层目标」（这里 {n_layers} 层），与旋钮一致',
                  f'{n_layers}层目标' in p.replace(' ', ''),
                  p[:160].replace('\n', ' | '))
    finally:
        AC.llm.chat = real
        CFG.set('GOAL_LADDER', saved)
    return allok


if __name__ == '__main__':
    print('导演派活 · 五层目标金字塔 —— 验证', flush=True)
    allok = True
    try:
        head('A. 目标金字塔')
        allok &= test_ladder()
        head('B. 派活本身')
        allok &= test_dispatch()
        head('C. 接线（每 N 拍调 / 写进 mission / 进提示词）')
        allok &= test_wiring()
        head('E. 派活卡死放行闸（DISPATCH_STUCK_ROUNDS）')
        allok &= test_stuck_release()
        head('C3. 派活那一层真的进了决策提示词')
        allok &= test_prompt_has_ladder()
    except Exception:
        report['fatal'] = traceback.format_exc()
        ok('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        allok = False
    report['ok'] = bool(allok)
    (OUT / 'dispatch_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1200:])
    sys.exit(0 if report['ok'] else 2)
