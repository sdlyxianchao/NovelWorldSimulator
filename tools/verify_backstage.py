# -*- coding: utf-8 -*-
"""验证：**前后台双制**（设计稿 §五）—— `BACKGROUND_MODE` /
`BACKGROUND_TICK_MINUTES` / `PROMOTE_ON_STAGE` / `BACKGROUND_EVENT_RATE`。

用户 2026-10-06：「继续全做完」。这四项以前**一个都没人读** ——
"后台人物"只是装配时贴的 `role="后台"` 标签：既不行动、也不留记忆、
更不会在需要的时候走到台前（台前永远是同一份名册）。

判据分层（每层都要能红，见 `developers/mutate_backstage.py`）：
  A **节流**：按**故事分钟**攒，攒够 `BACKGROUND_TICK_MINUTES` 才 due；
     `off` 档永不动；没有后台人物也算不 due。
  B **light 档**：规则层给**每个**后台人物补一条经历记忆（零成本）；
     事件率 `0` → **一次 LLM 都不调**、`1` → 调一次「批量摘要」；
     摘要失败要**走 warn 说出来**，不许静默。
  C **full 档**：每个后台人物真走一次 `decide()`，产出进记忆 + 事件流。
  D **升格**（`PROMOTE_ON_STAGE`）：被点名 / 地点对得上 → 提到台前；
     台前满员（`AGENT_MAX`）不再升；关掉旋钮一律不动。
  E **降格**（超员队列）：超 `AGENT_MAX` 时按「戏份权重 × 最近出场」降，
     产出**过渡记忆**（不硬塞、不丢弃）。
  F **接线**：`RunLoop._run_backstage()` 真的调批次器、真的推 NOTE；
     `_mentioned_names` 真的能从动作文本里认出后台人物。

用法：.venv\\Scripts\\python.exe tools/verify_backstage.py
产出：assets/screenshots/backstage_report.json

English:
Verification: **dual backstage/front-stage regime** (design doc §5) — `BACKGROUND_MODE` /
`BACKGROUND_TICK_MINUTES` / `PROMOTE_ON_STAGE` / `BACKGROUND_EVENT_RATE`.
User 2026-10-06: "Go ahead and finish it all". These four items previously **had no one reading
them at all** —
"backstage characters" were just a `role="后台"` tag attached at assembly time: they neither act,
nor leave memories,
much less walk to the stage when needed (the stage is always the same roster).
Assertions in layers (each layer must be able to go red, see `developers/mutate_backstage.py`):
  A **Throttling**: accumulate by **story minutes**, due only after accumulating `BACKGROUND_TICK_MINUTES`;
     `off` tier never moves; no backstage characters also counts as not due.
  B **light tier**: the rule layer adds one experience memory to **each** backstage character (zero cost);
     event rate `0` → **no LLM called at all**, `1` → call "batch summary" once;
     summary failure must **go through warn and speak up**, no silence.
  C **full tier**: each backstage character really goes through `decide()` once, output goes into memory + event stream.
  D **Promotion** (`PROMOTE_ON_STAGE`): named / location matches → lift to the stage;
     stage full (`AGENT_MAX`) → no more promotion; knob off → never move.
  E **Demotion** (over-capacity queue): when over `AGENT_MAX`, demote by "screen-share weight × most recent appearance",
     output **transition memory** (no force-fitting, no discarding).
  F **Wiring**: `RunLoop._run_backstage()` really calls the batcher, really pushes NOTE;
     `_mentioned_names` really can recognize backstage characters from action text.
Usage: .venv\\Scripts\\python.exe tools/verify_backstage.py
Output: assets/screenshots/backstage_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from config import CFG                                         # noqa: E402
# ⚠ 不量像素、不弹窗、**绝不点会 `CFG.save()` 的按钮**（MEMORY 的铁律）。
# [EN] ⚠ Do not measure pixels, do not pop up dialogs, **never click a button that would call
# [EN] `CFG.save()`** (an iron rule of MEMORY).
CFG.set('MOCK_LLM', 'true')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


class FakeDB:
    """够用的假库：记下写入的记忆与事件，供判据检查。
        English:
    A mock library that suffices: records written memories and events, for assertion checking.
    """

    def __init__(self):
        self.memories: list[tuple] = []
        self.events: list[tuple] = []

    def add_memory(self, agent, content, memory_type='observation',
                   importance=5.0, game_ts=0, ref_event=''):
        self.memories.append((agent, content, memory_type, game_ts))
        return len(self.memories)

    def add_event(self, eid, content, event_type='action', game_day=1,
                  involved=None, node='', snapshot=''):
        self.events.append((eid, content, event_type))

    def recent_events(self, n=20, game_day=0):
        return []

    def retrieve_memory(self, *a, **k):
        return []


class P:
    """最小人物桩：`run_batch` 只碰 `.name` / `.ps` / `.decide()`。
        English:
    Minimal character stub: `run_batch` only touches `.name` / `.ps` / `.decide()`.
    """

    def __init__(self, name, role='后台', location='临河茶肆', status='在场',
                 goal='', identity=''):
        from world.state import PersonState
        self.name = name
        self.ps = PersonState(name=name, role=role, location=location,
                              status=status, goal=goal, identity=identity)
        self.decided = 0

    async def decide(self):
        from agent.core import Action
        self.decided += 1
        return Action(verb='interact', target='账本', reason='测试')


def make_world():
    from world.state import WorldState, GameTime
    w = WorldState()
    w.scene = '临河茶肆'
    w.clock = GameTime()
    w.clock.day = 1
    w.clock.minutes = 0
    w.people = {}
    return w


def make_batcher(world, db, agents, warns=None):
    from sim.backstage import BackstageBatcher
    import random
    return BackstageBatcher(world, agents, db, random.Random(7),
                            on_warn=(lambda tag, msg: warns.append((tag, msg)))
                            if warns is not None else None)


# ══════════════════════════════════════════════════════════════
#  A. 节流
# [EN] A. Throttling
# ══════════════════════════════════════════════════════════════
def test_throttle() -> bool:
    ok = True
    world = make_world()
    bg = P('掌柜', role='后台')
    for a in (bg,):
        world.people[a.name] = a.ps
    b = make_batcher(world, FakeDB(), [bg])
    saved_t, saved_m = CFG.raw('BACKGROUND_TICK_MINUTES'), CFG.raw('BACKGROUND_MODE')
    saved_p = CFG.raw('PROMOTE_ON_STAGE')
    try:
        # ⚠ 这一段只管"节流"，所以先把升格关掉 —— 否则 `run_batch()` 里的
        #   `promote()` 会把掌柜提到台前（他就在这个地点），**名册当场变空**，
        #   后面几条判据全部连锁假红（第一版就是这么红的）。
        # [EN] ⚠ This section only deals with "throttling", so first turn off promotion — otherwise `promote()`
        # [EN] in
        # [EN] `run_batch()` will bring the shopkeeper to the stage (he is at this location), **the roster
        # [EN] becomes empty on the spot**,
        # [EN] and all subsequent assertions cascade into false reds (that's exactly how the first version went
        # [EN] red).
        CFG.set('PROMOTE_ON_STAGE', 'false')
        CFG.set('BACKGROUND_TICK_MINUTES', '30')
        ok &= rec('A0 名册只认 `role=后台` 且在场的人',
                  [a.name for a in b.backstage_people()] == ['掌柜'],
                  str([a.name for a in b.backstage_people()]))
        b.advance(10)
        ok &= rec('A1 攒 10 分钟 < 30 → 还不到点', b.due() is False, f'acc={b._acc}')
        b.advance(25)
        ok &= rec('A1 ★ 再攒 25（共 35 ≥ 30）→ 到点', b.due() is True, f'acc={b._acc}')
        asyncio.run(b.run_batch())
        ok &= rec('A1 ★ 跑完一批 → 计数归零（否则会连着跑）',
                  b.due() is False, f'acc={b._acc}')

        # ⚠ 这条第一版是坏的：它紧接着 `run_batch()` 之后判，那时 `_acc` 刚归零，
        #   `due()` 本来就 False —— 于是"把 off 档改空转"的变异**一条都不红**。
        #   必须先攒满分钟数，让**只有 mode 这一个变量**决定结果。
        # [EN] ⚠ This one was broken in the first version: it asserts right after `run_batch()`, when `_acc`
        # [EN] has just been reset to zero,
        # [EN] so `due()` is already False — thus the mutation "make the off tier idle" **doesn't go red at
        # [EN] all**.
        # [EN] You must first accumulate enough minutes, so that **only mode, the single variable, decides the
        # [EN] result**.
        b.advance(999)
        CFG.set('BACKGROUND_MODE', 'off')
        ok &= rec('A2 ★ `BACKGROUND_MODE=off` → 攒再多也不到点（旋钮真被读）',
                  b.due() is False, f'mode={CFG.s("BACKGROUND_MODE")} acc={b._acc}')
        CFG.set('BACKGROUND_MODE', 'light')
        ok &= rec('A2 ★ 反例：改回 light 就立刻到点（判据不是恒真）',
                  b.due() is True, f'mode={CFG.s("BACKGROUND_MODE")} acc={b._acc}')

        CFG.set('BACKGROUND_MODE', 'light')
        b2 = make_batcher(world, FakeDB(), [P('前台的', role='前台')])
        b2.advance(999)
        ok &= rec('A3 ★ 没有后台人物 → 也不到点（不做空事）',
                  b2.due() is False, str(b2.backstage_people()))
    finally:
        CFG.set('BACKGROUND_TICK_MINUTES', saved_t)
        CFG.set('BACKGROUND_MODE', saved_m)
        CFG.set('PROMOTE_ON_STAGE', saved_p)
    return ok


# ══════════════════════════════════════════════════════════════
#  B. light 档
# [EN] B. light tier
# ══════════════════════════════════════════════════════════════
def test_light() -> bool:
    ok = True
    from sim import backstage as BS
    world = make_world()
    db = FakeDB()
    people = [P('掌柜', goal='把这月的账理清'), P('阿桂', identity='厨娘')]
    for a in people:
        world.people[a.name] = a.ps
    warns: list[tuple] = []
    b = make_batcher(world, db, people, warns)

    saved_m, saved_r = CFG.raw('BACKGROUND_MODE'), CFG.raw('BACKGROUND_EVENT_RATE')
    # ⚠ 这一段只管"批次本身"。升格单列在 D 段 —— 不关掉的话 `run_batch()`
    #   里先跑的 `promote()` 会把这两个人提上台（他们就在这个地点），
    #   `backstage_people()` 当场变空 → 后面 B2/B3 全连锁假红。
    # [EN] ⚠ This section only deals with "the batch itself". Promotion is a separate item in section D —
    # [EN] if not turned off, `run_batch()`
    # [EN] will run `promote()` first and lift these two people to the stage (they are at this location),
    # [EN] `backstage_people()` becomes empty on the spot → all of B2/B3 cascade into false reds.
    saved_p = CFG.raw('PROMOTE_ON_STAGE')
    CFG.set('PROMOTE_ON_STAGE', 'false')
    calls: list[str] = []

    def fake_ask_factory(reply_text, ok_=True):
        async def _f(tier, messages, **kw):
            from llm.replies import Reply
            calls.append(kw.get('purpose', ''))
            return Reply(value=reply_text, ok=ok_,
                         notes=[] if ok_ else ['模型没给可用的正文'])
        return _f

    import llm.replies as R
    real = R.ask
    try:
        CFG.set('BACKGROUND_MODE', 'light')

        # ① 事件率 = 0 → 规则记忆照写，但**一次 LLM 都不调**
        # [EN] ① Event rate = 0 → rule memory is still written, but **no LLM is called at all**
        CFG.set('BACKGROUND_EVENT_RATE', '0')
        calls.clear(); db.memories.clear()
        news = asyncio.run(b.run_batch())
        ok &= rec('B1 ★ 事件率=0 → **一次 LLM 调用都没有**（省钱是本档的重点）',
                  calls == [], str(calls))
        ok &= rec('B1 ★ 规则层给**每个**后台人物补了一条经历记忆',
                  len(db.memories) == 2
                  and {m[0] for m in db.memories} == {'掌柜', '阿桂'},
                  str([(m[0], m[1][:16]) for m in db.memories]))
        ok &= rec('B1 ★ 记忆带**故事时间**（`game_ts` 是第 5 个参数，不是 game_day）',
                  all(isinstance(m[3], float) and m[3] >= 1440 for m in db.memories),
                  str([m[3] for m in db.memories]))
        ok &= rec('B1 事件率=0 → 不产事件、不播报',
                  news == [] and db.events == [], f'{news} / {db.events}')

        # ② 事件率 = 1 → 调一次批量摘要，事件入库、返回播报行
        # [EN] ② Event rate = 1 → call a batch summary once, events go into storage, returns broadcast lines
        CFG.set('BACKGROUND_EVENT_RATE', '1')
        R.ask = fake_ask_factory('后堂有人在搬东西，响动一直没停。')
        calls.clear(); db.events.clear()
        news = asyncio.run(b.run_batch())
        ok &= rec('B2 ★ 事件率=1 → 调了**一次**「批量摘要」（一次覆盖所有人，不是每人一次）',
                  calls == ['backstage_summary'], str(calls))
        ok &= rec('B2 ★ 摘要进事件流（导演与前台看得到）',
                  len(db.events) == 1 and db.events[0][2] == '后台', str(db.events))
        ok &= rec('B2 ★ 返回播报行', news == ['后堂有人在搬东西，响动一直没停。'],
                  str(news))

        # ③ 摘要拿不到 → **要出声**（不许静默降级）
        # [EN] ③ Summary unavailable → **must speak up** (no silent degradation)
        R.ask = fake_ask_factory('', ok_=False)
        warns.clear(); db.events.clear()
        news = asyncio.run(b.run_batch())
        ok &= rec('B3 ★★ 批量摘要拿不到 → 走 warn 说出来（不静默）',
                  any(t == 'bg_summary' for t, _ in warns), str(warns))
        ok &= rec('B3 拿不到 → 不产事件、不播报（不编）',
                  news == [] and db.events == [], f'{news} / {db.events}')
    finally:
        R.ask = real
        CFG.set('BACKGROUND_MODE', saved_m)
        CFG.set('BACKGROUND_EVENT_RATE', saved_r)
        CFG.set('PROMOTE_ON_STAGE', saved_p)
    return ok


# ══════════════════════════════════════════════════════════════
#  C. full 档
# [EN] C. full tier
# ══════════════════════════════════════════════════════════════
def test_full() -> bool:
    ok = True
    world = make_world()
    db = FakeDB()
    people = [P('掌柜'), P('阿桂')]
    for a in people:
        world.people[a.name] = a.ps
    b = make_batcher(world, db, people)
    saved = CFG.raw('BACKGROUND_MODE')
    saved_p = CFG.raw('PROMOTE_ON_STAGE')
    try:
        CFG.set('PROMOTE_ON_STAGE', 'false')     # 同上：隔离升格
        # [EN] Same as above: isolate promotion
        CFG.set('BACKGROUND_MODE', 'full')
        news = asyncio.run(b.run_batch())
        ok &= rec('C1 ★ full 档：每个后台人物**真走一次决策**',
                  [a.decided for a in people] == [1, 1],
                  str([a.decided for a in people]))
        ok &= rec('C1 ★ full 档的产出进记忆 + 事件流',
                  len(db.memories) == 2 and len(db.events) == 2,
                  f'记忆 {len(db.memories)} / 事件 {len(db.events)}')
        ok &= rec('C1 播报不超过 3 条（别抢主角的戏）', len(news) <= 3, str(len(news)))
    finally:
        CFG.set('BACKGROUND_MODE', saved)
        CFG.set('PROMOTE_ON_STAGE', saved_p)
    return ok


# ══════════════════════════════════════════════════════════════
#  D. 升格 / E. 降格
# [EN] D. Promotion / E. Demotion
# ══════════════════════════════════════════════════════════════
def test_promote_demote() -> bool:
    ok = True
    saved_p, saved_a = CFG.raw('PROMOTE_ON_STAGE'), CFG.raw('AGENT_MAX')
    try:
        # ① 关掉旋钮 → 一律不动
        # [EN] ① Turn off the knob → never move
        world = make_world()
        bg = P('掌柜', role='后台', location='临河茶肆')
        world.people['掌柜'] = bg.ps
        b = make_batcher(world, FakeDB(), [bg])
        CFG.set('PROMOTE_ON_STAGE', 'false')
        ok &= rec('D1 ★ `PROMOTE_ON_STAGE=false` → 谁都不动（旋钮真被读）',
                  b.promote({'掌柜'}) == [] and bg.ps.role == '后台',
                  f'{bg.ps.role}')

        # ② 被点名 → 升格
        # [EN] ② Named → promote
        CFG.set('PROMOTE_ON_STAGE', 'true')
        CFG.set('AGENT_MAX', '12')
        news = b.promote({'掌柜'})
        ok &= rec('D2 ★★ 被**点到名** → 提到台前', bg.ps.role == '前台', bg.ps.role)
        ok &= rec('D2 升格要播报（用户看得见人是怎么上台的）',
                  any('掌柜' in x for x in news), str(news))
        ok &= rec('D2 升格时**补一条经历记忆**（不然上台的人记忆里一片空白）',
                  any('后堂' in m[1] for m in b.db.memories), str(b.db.memories))

        # ②b ★★ 「被点名」这条路要**单独**验：上面那位就站在这个地点，
        #    所以就算把 `called` 去掉他照样升格 —— 变异测不出来（反例法抓到的）。
        #    要验点名，得让**地点对不上、只有名字能把他拉上台**。
        # [EN] ②b ★★ The "named" path must be verified **separately**: the person above is standing at this
        # [EN] location,
        # [EN] so even if `called` is removed he still gets promoted — the mutation can't detect it (caught by
        # [EN] the counterexample method).
        # [EN] To verify naming, you must make **the location mismatch, so that only the name can pull him to
        # [EN] the stage**.
        world2b = make_world()
        far = P('阿福', role='后台', location='城东渡口')     # 地点对不上
        # [EN] Location mismatched
        world2b.people['阿福'] = far.ps
        b2b = make_batcher(world2b, FakeDB(), [far])
        b2b.promote({'阿福'})
        ok &= rec('D2b ★★ 人在别处（地点对不上），但**被点名** → 一样升格',
                  far.ps.role == '前台', far.ps.role)

        # ③ 地点对得上 → 升格（没被点名也算）
        # [EN] ③ Location matches → promote (counts even if not named)
        world3 = make_world()
        bg3 = P('阿桂', role='后台', location='临河茶肆')
        world3.people['阿桂'] = bg3.ps
        b3 = make_batcher(world3, FakeDB(), [bg3])
        b3.promote(set())
        ok &= rec('D3 ★ 虽然没被点名，但**人就在这个地点** → 也升格',
                  bg3.ps.role == '前台', bg3.ps.role)

        # ④ 地点离得远 + 没点名 → 不动
        # [EN] ④ Location far away + not named → don't move
        world4 = make_world()
        bg4 = P('阿福', role='后台', location='城南码头')
        world4.people['阿福'] = bg4.ps
        b4 = make_batcher(world4, FakeDB(), [bg4])
        b4.promote(set())
        ok &= rec('D4 既没人叫、地点也对不上 → 老实待在后堂',
                  bg4.ps.role == '后台', bg4.ps.role)

        # ⑤ 台前满员 → 不再升
        # [EN] ⑤ Stage full → no more promotion
        world5 = make_world()
        front = [P(f'前台{i}', role='前台') for i in range(3)]
        back = P('掌柜', role='后台')
        for a in front + [back]:
            world5.people[a.name] = a.ps
        b5 = make_batcher(world5, FakeDB(), front + [back])
        CFG.set('AGENT_MAX', '3')
        b5.promote({'掌柜'})
        ok &= rec('D5 ★ 台前已满（`AGENT_MAX`）→ 不再升格',
                  back.ps.role == '后台', back.ps.role)

        # ⑥ 超员 → 降格（按「戏份权重 × 最近出场」）
        # [EN] ⑥ Over capacity → demote (by "screen-share weight × most recent appearance")
        world6 = make_world()
        # ⚠ 「新人」放在**名册最前面**：第一版把他放最后，于是"降格不按权重、
        #   直接倒序取"那个变异恰好也降他 —— 一条都不红。要让**顺序**真的影响结果。
        # [EN] ⚠ Put the "newcomer" at the **front of the roster**: the first version put him last, so the
        # [EN] mutation "demote not by weight,
        # [EN] just take in reverse order" also happened to demote him — not a single red. Make **order**
        # [EN] actually affect the result.
        rook = P('新人', role='前台')
        vets = [P('老手', role='前台') for _ in range(2)]
        for a in [rook] + vets:
            world6.people[a.name] = a.ps
        b6 = make_batcher(world6, FakeDB(), [rook] + vets)
        CFG.set('AGENT_MAX', '2')
        # 老手各上过 5 次台、新人一次都没上过 → 该降新人（"不硬塞"）
        # [EN] Veterans have each been on stage 5 times, the newcomer has never been on stage → the newcomer
        # [EN] should be demoted ("don't force-fit")
        for _ in range(5):
            b6.note_on_screen('老手')
        news6 = b6.demote_over_capacity()
        ok &= rec('D6 ★★ 超员时降的是**戏份最轻**的那个（老手留下、新人回后台）',
                  rook.ps.role == '后台' and all(a.ps.role == '前台' for a in vets),
                  f'新人={rook.ps.role} 老手={[a.ps.role for a in vets]}')
        ok &= rec('D6 ★ 降格要**补过渡记忆**（不硬塞、不丢弃）',
                  any('后堂' in m[1] for m in b6.db.memories), str(b6.db.memories))
        ok &= rec('D6 降格要播报', any('新人' in x for x in news6), str(news6))

        # ⑦ 没超员就不降（判据不能恒真）
        # [EN] ⑦ If not over capacity, don't demote (the assertion must not be a tautology)
        world7 = make_world()
        solo = P('独苗', role='前台')
        world7.people['独苗'] = solo.ps
        b7 = make_batcher(world7, FakeDB(), [solo])
        CFG.set('AGENT_MAX', '4')
        ok &= rec('D7 ★ 反例：没超员 → 一个人都不降（判据不是恒真）',
                  b7.demote_over_capacity() == [] and solo.ps.role == '前台',
                  solo.ps.role)
    finally:
        CFG.set('PROMOTE_ON_STAGE', saved_p)
        CFG.set('AGENT_MAX', saved_a)
    return ok


# ══════════════════════════════════════════════════════════════
#  F. 接线（RunLoop）
# [EN] F. Wiring (RunLoop)
# ══════════════════════════════════════════════════════════════
def test_wiring() -> bool:
    ok = True
    from agent.core import Action
    from sim.loop import RunLoop
    world = make_world()
    bg = P('掌柜', role='后台')
    world.people['掌柜'] = bg.ps
    db = FakeDB()

    loop = RunLoop.__new__(RunLoop)
    loop.world = world
    from sim.backstage import BackstageBatcher
    import random
    loop._backstage = BackstageBatcher(world, [bg], db, random.Random(3))
    loop._pending_mention = set()
    loop._cb_warned = set()
    loop._on_status = None
    notes: list[str] = []
    # ⚠ 回调要收 `**kw` —— 产品侧 `_push_narrative` 现在一次带三个关键字
    #   （`kind` / `detail` / `update_key`）。只写 `kind=''` 会因 `detail` 未预期而抛
    #   TypeError，产品于是**退回两参调用**（它会留一条 warning），`kind` 永远拿不到 ⇒
    #   "词条类型真的传到界面了吗"这条判据永远红，而产品其实是对的。
    # [EN] ⚠ The callback must take `**kw`: `_push_narrative` now passes three keywords
    # [EN] (`kind` / `detail` / `update_key`). Declaring only `kind=''` raises TypeError on
    # [EN] `detail`, the product **falls back to two positional args** (it does log a warning), and
    # [EN] `kind` never arrives -- so "did the entry type reach the UI" stays permanently red while
    # [EN] the product is in fact correct.
    loop._on_narrative = lambda text, pri, kind='', **kw: notes.append((text, kind))

    class Disp:
        """⚠ `_push_narrative` 第一件事是 `self.display.enqueue_narrative(...)`
        （`create_task` 在 `_on_narrative` **之前**）。不塞这个桩就 AttributeError，
        异常被 `_run_backstage` 的兜底吞掉 —— 表现成"播报没推出去"（第一版就这么红的）。
                English:
        ⚠ The first thing `_push_narrative` does is `self.display.enqueue_narrative(...)`
                (`create_task` comes **before** `_on_narrative`). Without this stub it's an AttributeError,
                and the exception is swallowed by `_run_backstage`'s fallback -- manifesting as "the announcement wasn't pushed out" (that's how the first version went red).
        """

        async def enqueue_narrative(self, *a, **k):
            pass

    loop.display = Disp()

    saved_t, saved_m = CFG.raw('BACKGROUND_TICK_MINUTES'), CFG.raw('BACKGROUND_MODE')
    saved_p = CFG.raw('PROMOTE_ON_STAGE')
    try:
        CFG.set('BACKGROUND_MODE', 'light')
        CFG.set('BACKGROUND_EVENT_RATE', '0')
        CFG.set('BACKGROUND_TICK_MINUTES', '30')

        # ③ 先判 `_mentioned_names`（**必须在跑批次之前**）：它只认"后台名册"，
        #    而下面那一步会把掌柜提上台 —— 顺序反了名册就是空的，判据假红。
        # [EN] ③ Check `_mentioned_names` first (**must be before running the batch**): it only recognizes the
        # [EN] "backstage roster",
        # [EN] and the next step will lift the shopkeeper to the stage — if the order is reversed the roster is
        # [EN] empty and the assertion goes false red.
        acts = [(object(), Action(verb='speak', dialogue='去请掌柜来一趟',
                                  reason='要找人对账'))]
        got = loop._mentioned_names(acts)
        ok &= rec('F3 ★★ `_mentioned_names` 从台词里认出了后台人物',
                  got == {'掌柜'}, str(got))
        # 反例：不提到就不该冒出来
        # [EN] Counterexample: if not mentioned, it should not pop up
        acts2 = [(object(), Action(verb='speak', dialogue='今天茶不错', reason='闲聊'))]
        ok &= rec('F3 ★ 反例：没提到 → 空集合（判据不是恒真）',
                  loop._mentioned_names(acts2) == set(), str(loop._mentioned_names(acts2)))

        # ① 不到点 → 什么都不做（不能每拍都跑）。先把升格关掉，隔离"节流"这件事。
        # [EN] ① Not yet due → do nothing (must not run every beat). First turn off promotion, to isolate the
        # [EN] "throttling" concern.
        CFG.set('PROMOTE_ON_STAGE', 'false')
        asyncio.run(loop._run_backstage())
        ok &= rec('F1 ★ 没到点 → 一次都不跑', db.memories == [], str(db.memories))

        # ② 到点 → 跑，并推 NOTE
        # [EN] ② Due → run, and push NOTE
        loop._backstage.advance(31)
        asyncio.run(loop._run_backstage())
        ok &= rec('F2 ★★ `RunLoop._run_backstage` 真的执行了这批后台',
                  len(db.memories) == 1, str(db.memories))
        ok &= rec('F2 ★ `mention` 用完就清（不会每批都拿上一拍的旧名字）',
                  loop._pending_mention == set(), str(loop._pending_mention))

        # ④ 被点名 → 这一批真的把人拉上台（端到端）
        # [EN] ④ Named → this batch really pulls the person to the stage (end-to-end)
        CFG.set('PROMOTE_ON_STAGE', 'true')
        loop._pending_mention = {'掌柜'}
        loop._backstage.advance(31)
        asyncio.run(loop._run_backstage())
        ok &= rec('F4 ★★ 被点名 → 批次里真的升格（端到端）',
                  bg.ps.role == '前台', bg.ps.role)
        ok &= rec('F4 升格那条真的推到了叙事（`kind=note`）',
                  any('掌柜' in t and k == 'note' for t, k in notes), str(notes[:3]))

        # ⑤ 出错要出声，不能静默
        # [EN] ⑤ Errors must speak up, not be silent
        class Boom:
            def due(self):
                raise RuntimeError('炸了')
        loop._backstage = Boom()
        warns: list[str] = []
        loop._cb_warned = set()
        loop._warn_once = lambda tag, msg: warns.append((tag, msg))
        asyncio.run(loop._run_backstage())
        ok &= rec('F5 ★★ 后台批次抛异常 → 走 `_warn_once` 说出来（不静默）',
                  any(t == 'backstage' for t, _ in warns), str(warns))
    finally:
        CFG.set('BACKGROUND_TICK_MINUTES', saved_t)
        CFG.set('BACKGROUND_MODE', saved_m)
        CFG.set('PROMOTE_ON_STAGE', saved_p)
    return ok


# ══════════════════════════════════════════════════════════════
#  G. 主线接线（时钟攒分钟 / `_tick` 真的在调）
# [EN] G. Main-line wiring (clock accumulates minutes / `_tick` is really being called)
# ══════════════════════════════════════════════════════════════
def test_clock_feeds_batcher() -> bool:
    """★★ `_advance_clock` 真的把**故事分钟**喂给批次器（端到端，非直接调用）。

    只判 `BackstageBatcher.advance()` 自己是不够的 —— "测了实现、没测接线"
    是本项目反复栽的坑（`verify_craft` 那次就是：函数对不对全绿，
    把调用改空转一条都不红）。所以这里走**真的** `_advance_clock`。
    
        English:
    ★★ `_advance_clock` actually feeds **story minutes** into the batcher (end-to-end, not a direct
    call).
        Only testing `BackstageBatcher.advance()` itself is not enough -- "tested the implementation, not the wiring"
        is a pit this project has repeatedly fallen into (`verify_craft` was exactly that: functions all green if correct,
        change the call to a no-op and not a single test goes red). So here we go through the **real** `_advance_clock`.
    """
    import time
    ok = True
    from sim.loop import RunLoop
    from world.state import WorldState, GameTime

    world = WorldState()
    world.scene = '临河茶肆'
    world.clock = GameTime()
    loop = RunLoop.__new__(RunLoop)
    loop.world = world
    loop._rng = __import__('random').Random(1)
    from sim.backstage import BackstageBatcher
    loop._backstage = BackstageBatcher(world, [], FakeDB(), loop._rng)
    loop._last_mono = None
    loop._sec_acc = 0.0
    loop._beat_acc = 0.0
    loop._game_sec = 0.0
    loop._game_min = 0.0

    # ★★★ 2026-10-26：**口径被用户推翻了，判据跟着走**（方案 A：日界 = 拍预算用完）。
    #   以前 `_advance_clock` 一个人干两件事：①攒真实时间决定起不起下一拍；②按
    #   `真实流逝 × TIME_RATIO` 推故事钟。这条判据钉的是"②把分钟喂给了批次器"。
    #   语义拆开之后 ② 搬到了 `_walk_beat_time()`（每拍推一次，落到唯一的 `_world_walk`），
    #   `_advance_clock` **只剩 ①**、并按设计不再推钟 ⇒ 再拿它量批次器会**永远红**。
    #   红的不是产品，是判据还按旧契约说话。新契约照旧要问同一句话：
    #   **"故事分钟到底有没有喂进批次器？"** —— 改问新那条路。
    # [EN] ★★★ 2026-10-26: **the contract was overturned by the user, so the criterion follows**
    # [EN] (option A: the day ends when the beat budget runs out). `_advance_clock` used to do two
    # [EN] things; (2) moved to `_walk_beat_time()` (once per beat, landing in the single
    # [EN] `_world_walk`), and `_advance_clock` by design no longer advances the clock => measuring
    # [EN] the batcher through it would be **permanently red**. What is red is the criterion, not the
    # [EN] product. The question stays the same -- **do story minutes reach the batcher?** -- just
    # [EN] asked of the new path.
    loop._ticks_today = 0
    loop._walked_min = 0
    loop._min_acc = 0.0
    # 一拍推多久由 `_beat_minutes_now()` 按"剩余时间 ÷ 剩余拍数"算；那个算法本身归
    # `verify_beat_time` 管，这里只要一个确定的输入，好让"喂没喂进批次器"成为唯一变量。
    # [EN] How long a beat lasts is computed by `_beat_minutes_now()`; that algorithm belongs to
    # [EN] `verify_beat_time`. Here we only need a deterministic input so "did it reach the
    # [EN] batcher" is the single variable.
    loop._beat_minutes_now = lambda: 3
    before = loop._backstage._acc
    loop._walk_beat_time()
    ok &= rec('G1 ★★ 一拍真的把故事分钟喂进了批次器（走 `_walk_beat_time` → `_world_walk`）',
              loop._backstage._acc > before,
              f'{before} → {loop._backstage._acc}')
    ok &= rec('G1b ★★ 而且时钟自己也走了这 3 分钟（不是只喂了批次器）',
              loop._game_min >= 3, f'game_min={loop._game_min}')
    # ★ 零头也要算：`world.tick()` 只吃整分钟，不足一分钟的部分必须留在累加器里，
    #   否则"一拍 2.4 分钟"这种小数会被反复截断、后台永远攒不满。
    # [EN] ★ Remainders must count too: `world.tick()` takes whole minutes only, so the fractional
    # [EN] part must stay in the accumulator, or "a 2.4-minute beat" gets truncated every time and
    # [EN] the backstage never accumulates.
    acc_before = loop._backstage._acc
    min_before = int(loop._game_min)
    loop._world_walk(0.4)
    loop._world_walk(0.4)
    ok &= rec('G2 ★ 不满一分钟的零头被**攒着**（不丢，也不提前进位）',
              int(loop._game_min) == min_before and abs(loop._min_acc - 0.8) < 1e-6,
              f'min_acc={loop._min_acc:.2f} · game_min={loop._game_min}')
    loop._world_walk(0.4)
    ok &= rec('G3 ★ 攒够一分钟就真的进位（3 × 0.4 = 1.2 ⇒ 时钟 +1、零头留 0.2）',
              int(loop._game_min) == min_before + 1
              and abs(loop._min_acc - 0.2) < 1e-6
              and loop._backstage._acc > acc_before,
              f'min_acc={loop._min_acc:.2f} · acc {acc_before} → {loop._backstage._acc}')
    return ok


def test_tick_calls_it() -> bool:
    """★ 接线哨兵：`_tick` 里**确实有那一行** `await self._run_backstage()`。

    ⚠ 老实说这一条是**弱判据**（看源码文本，不是真跑 `_tick`）——
    `_tick` 依赖十几个协作者（导演 / 分幕 / 落盘 / 状态栏…），
    在这个不弹窗、不量像素的脚本里跑起来只会测到桩。
    但"有人把那一行删掉"这件事必须有东西拦得住，所以留它做哨兵，
    并**清楚标出来它是弱的那一种**（比"看起来全绿、其实没接线"强）。
    
        English:
    ★ Wiring sentinel: in `_tick` there **really is that line** `await self._run_backstage()`.
        ⚠ Honestly, this one is a **weak assertion** (looks at source text, does not actually run `_tick`) --
        `_tick` depends on a dozen collaborators (director / scene splitting / persistence / status bar...),
        running it in this script that pops no windows and measures no pixels would only test the stubs.
        But "someone deletes that line" must have something to stop it, so keep it as a sentinel,
        and **clearly mark it as the weak kind** (better than "looks all green, but actually not wired").
    """
    import inspect
    from sim.loop import RunLoop
    src = inspect.getsource(RunLoop._tick)
    ok = rec('G3 ★ `_tick` 里真的调了后台批次（接线哨兵）',
             'await self._run_backstage()' in src,
             ' | '.join(l.strip() for l in src.split('\n')
                        if '_run_backstage' in l))
    ok &= rec('G3 后台批次排在**前台步进之后**（设计稿 §六的顺序）',
              src.find('_process_actions(actions)') < src.find('_run_backstage()'),
              f'{src.find("_process_actions(actions)")} < {src.find("_run_backstage()")}')
    return ok


if __name__ == '__main__':
    print('前后台双制 —— 验证', flush=True)
    ok = True
    try:
        head('A. 节流（按故事分钟 / off 档 / 无后台人物）')
        ok &= test_throttle()
        head('B. light 档（规则记忆 · 事件率 · 摘要失败要出声）')
        ok &= test_light()
        head('C. full 档（后台也逐个决策）')
        ok &= test_full()
        head('D/E. 升格与降格（超员队列）')
        ok &= test_promote_demote()
        head('F. 接线（RunLoop 真的在跑后台）')
        ok &= test_wiring()
        head('G. 主线接线（时钟攒分钟 / `_tick` 真在调）')
        ok &= test_clock_feeds_batcher()
        ok &= test_tick_calls_it()
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'backstage_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1200:])
    sys.exit(0 if report['ok'] else 2)
