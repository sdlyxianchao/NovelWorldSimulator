# -*- coding: utf-8 -*-
"""验证：岔路口（分支走向）+ `INTERVENTION_POLICY`（导演介入的处置）。

用户 2026-10-06：「影视剧的优化都做掉」。#133。

查证结果：这条链路**整条是死的** ——
`director.propose_branches()` 写好了但**从来没有任何调用点**，
`RunLoop` 的 `on_branch` / `choose_branch` / `_branch_choice` 三个成员也从没被用过，
GUI 里**没有任何分支界面**。于是 `BRANCH_WAIT_SECONDS`（等多久）、
`BRANCH_AUTO_POLICY`（等不到怎么办）、`INTERVENTION_POLICY`（介入要不要问作者）
三个旋钮自然全是零读取。

四层判据：
  A **提案**：`propose_branches` 走 `ask()`（截断/空会重试，不再裸调）、结构规范化。
  B **策略**：`pick_branch` 四种策略各自的行为（含 `pause` = 不替作者做决定）。
  C **接线**：`_maybe_branch` 真的会触发、会等、会接受 `choose_branch`、
     **没有界面时不空等**、选中的走向**真的写进事件流与导演提示词**。
  D **介入**：`INTERVENTION_POLICY=pause` 挂起 ＋ 点「继续」之后真的执行；
     `auto_resolve` 不打扰作者。

用法：.venv\\Scripts\\python.exe tools/verify_branch.py
产出：assets/screenshots/branch_report.json

English:
Verify: fork in the road (branch direction) + `INTERVENTION_POLICY` (how the director's
intervention is handled).
User 2026-10-06: "Do all the film/TV optimizations." #133.
Investigation result: this whole chain **is dead** —
`director.propose_branches()` is written but **has never had any call site**,
and the three members `on_branch` / `choose_branch` / `_branch_choice` of `RunLoop` have never
been used either,
and there is **no branch UI at all** in the GUI. So `BRANCH_WAIT_SECONDS` (how long to wait),
`BRANCH_AUTO_POLICY` (what to do when it times out), `INTERVENTION_POLICY` (whether intervention
should ask the author)
these three knobs are naturally all read zero times.
Four layers of criteria:
  A **Proposal**: `propose_branches` goes through `ask()` (truncation/empty will retry, no longer calling it raw), and the structure is normalized.
  B **Policy**: the behavior of each of the four `pick_branch` policies (including `pause` = do not make the decision for the author).
  C **Wiring**: `_maybe_branch` really does trigger, does wait, does accept `choose_branch`,
     **does not wait idly when there is no UI**, and the chosen direction is **really written into the event stream and the director prompt**.
  D **Intervention**: `INTERVENTION_POLICY=pause` suspends + it really executes after clicking "continue";
     `auto_resolve` does not disturb the author.
Usage: .venv\\Scripts\\python.exe tools/verify_branch.py
Output: assets/screenshots/branch_report.json
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
CFG.set('MOCK_LLM', 'true')          # 本脚本一个真请求都不发
# [EN] This script does not send a single real request.

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


# ══════════════════════════════════════════════════════════════
#  桩
# [EN] Stub
# ══════════════════════════════════════════════════════════════
def _FakeClock(minutes=0, day=1):
    """直接用**真的 GameTime**（别自己造一个：`format_game_clock` 要 `shichen`
    等一串属性，造不全就在 `_push_narrative` 里炸 —— 第一版就是这么炸的）。
        English:
    Use the **real GameTime** directly (do not make your own: `format_game_clock` needs `shichen`
        and a string of other attributes, and if you cannot construct them all it blows up in `_push_narrative` — that is exactly how the first version blew up).
    """
    from world.state import GameTime
    gt = GameTime()
    gt.minutes = minutes
    gt.day = day
    return gt


class FakeWorld:
    def __init__(self, day=1, minutes=0):
        from world.state import PersonState, WorldState
        self._w = WorldState()
        self._w.scene = '临河茶肆'
        self._w.clock = _FakeClock(minutes, day)
        self._w.people = {
            '阿九': PersonState(name='阿九', location='临河茶肆', role='前台'),
            '阿福': PersonState(name='阿福', location='后院', role='前台'),
        }
        self._w.progress_nodes = [
            # ★ 2026-10-27：`章数` 是**章数下限**（判据成了也要演够才过站）。
            #   夹具不写就按篇幅档兜底（这里没写 `篇幅` ⇒ 默认档「中」⇒ 3 章），
            #   闸门会把节点按住 ⇒ C1 看到的就不是"节点走完 → 置 `_branch_pending`"了。
            #   ⚠ 填 1：这一支验的是分岔，不是章数闸门（闸门见 `verify_length_plan` 的 G 组）。
            # [EN] ★ 2026-10-27: `章数` is the **minimum-chapter gate**. Without it the fixture falls
            # [EN] back by tier (no `篇幅` here => default "medium" => 3) and the gate holds the node,
            # [EN] so C1 stops measuring "node finished -> `_branch_pending` set". ⚠ 1 here: this
            # [EN] verifier is about branching, not about the chapter gate (see group G of
            # [EN] `verify_length_plan`).
            {'id': 'N1', '名称': '楼前失忆', '概要': '阿福初到', '完成判据': '被收留',
             '章数': 1},
            {'id': 'N2', '名称': '第一桩委托', '概要': '聊斋界来了客人', '完成判据': '了结',
             '章数': 1},
        ]
        self._w.current_node = 'N1'
        self._w.tension = 0.2

    def __getattr__(self, item):                 # 其余一律转发给真 WorldState
    # [EN] Everything else is forwarded to the real WorldState.
        return getattr(self._w, item)

    def __setattr__(self, k, v):
        if k == '_w':
            object.__setattr__(self, k, v)
        else:
            setattr(self._w, k, v)


class FakeDB:
    def __init__(self):
        self.events: list[tuple] = []

    def recent_events(self, n=5):
        return [{'content': c} for _a, c in self.events[-n:]]

    def add_event(self, eid, content, etype, day, involved, node):
        self.events.append((etype, content))


def make_engine(world, db):
    from director.engine import DirectorEngine
    return DirectorEngine(world, db)


# ══════════════════════════════════════════════════════════════
#  A. 提案
# [EN] A. Proposal
# ══════════════════════════════════════════════════════════════
def test_propose() -> bool:
    ok = True
    from director import engine as E
    from llm.replies import Reply

    w, db = FakeWorld(), FakeDB()
    eng = make_engine(w, db)
    seen: dict = {}
    real = E.ask

    async def fake_ask(tier, messages, **kw):
        seen.update(kw)
        seen['prompt'] = messages[-1]['content']
        return Reply(value=[
            {'id': 'B1', '标题': '揭穿掌柜', '后果': '信任崩了', '权重': 0.6},
            {'id': 'B2', '标题': '', '后果': '没标题 → 该丢'},          # 空标题丢掉
            {'id': 'B3', '标题': '走一趟阴司', '后果': '拿到线索', '权重': 9},  # 权重夹到 1
            'not-a-dict',                                              # 非 dict 丢掉
            # [EN] Discard empty titles.
            # [EN] Clamp weight to 1.
            # [EN] Discard non-dict.
        ], ok=True)

    E.ask = fake_ask
    try:
        rows = asyncio.run(eng.propose_branches())
        ok &= rec('A1 ★ 走的是统一容错通道 `ask()`（截断/空会重试、能抢救）',
                  seen.get('purpose') == 'branch' and seen.get('want') is list,
                  f"purpose={seen.get('purpose')} want={seen.get('want')}")
        ok &= rec('A1 提案数量由 `BRANCH_PROPOSALS` 决定（提示词里读的是它）',
                  str(CFG.i('BRANCH_PROPOSALS')) in seen.get('prompt', ''),
                  str(CFG.i('BRANCH_PROPOSALS')))
        ok &= rec('A1 产物规范化：空标题与非 dict 丢掉',
                  [r['标题'] for r in rows] == ['揭穿掌柜', '走一趟阴司'],
                  str([r['标题'] for r in rows]))
        ok &= rec('A1 ★ 权重夹到 0~1（模型给了 9）',
                  rows[1]['权重'] == 1.0, str([r['权重'] for r in rows]))
        ok &= rec('A1 id 缺了就补（B3 那条没写 id，本该补成 B2）',
                  all(r['id'] for r in rows), str([r['id'] for r in rows]))
    finally:
        E.ask = real
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 策略
# [EN] B. Policy
# ══════════════════════════════════════════════════════════════
def test_policy() -> bool:
    ok = True
    from director.engine import DirectorEngine as DE
    import random

    rows = [{'id': 'B1', '标题': '一', '权重': 0.0},
            {'id': 'B2', '标题': '二', '权重': 1.0}]
    saved = CFG.raw('BRANCH_AUTO_POLICY')
    try:
        CFG.set('BRANCH_AUTO_POLICY', 'pause')
        ok &= rec('B1 ★★ `pause` → 不替作者做决定（返回 None）',
                  DE.pick_branch(rows) is None, str(DE.pick_branch(rows)))
        CFG.set('BRANCH_AUTO_POLICY', 'first')
        ok &= rec('B1 `first` → 永远第一条', DE.pick_branch(rows)['id'] == 'B1')
        CFG.set('BRANCH_AUTO_POLICY', 'weighted')
        random.seed(7)
        picked = [DE.pick_branch(rows)['id'] for _ in range(200)]
        ok &= rec('B1 ★ `weighted` → 权重 0 的那条基本不会被选中',
                  picked.count('B2') > picked.count('B1') * 20,
                  f"B1={picked.count('B1')} B2={picked.count('B2')}")
        CFG.set('BRANCH_AUTO_POLICY', 'random')
        random.seed(7)
        picked = [DE.pick_branch(rows)['id'] for _ in range(400)]
        ok &= rec('B1 `random` → 两条都出得来（不等概率加权）',
                  picked.count('B1') > 50 and picked.count('B2') > 50,
                  f"B1={picked.count('B1')} B2={picked.count('B2')}")
        # 权重全是 0 时不能返回 None（否则会莫名其妙挂住）
        # [EN] Must not return None when all weights are 0 (otherwise it will hang inexplicably).
        zero = [{'id': 'B1', '标题': '一', '权重': 0.0},
                {'id': 'B2', '标题': '二', '权重': 0.0}]
        CFG.set('BRANCH_AUTO_POLICY', 'weighted')
        ok &= rec('B1 ★ 权重全 0 → 退化成随机挑一个（**不许返回 None**）',
                  DE.pick_branch(zero) is not None, str(DE.pick_branch(zero)))
        ok &= rec('B1 空候选 → None（没有候选就别硬挑）',
                  DE.pick_branch([]) is None)
    finally:
        CFG.set('BRANCH_AUTO_POLICY', saved)
    return ok


# ══════════════════════════════════════════════════════════════
#  C. 接线
# [EN] C. Wiring
# ══════════════════════════════════════════════════════════════
def make_loop(world, db, director):
    from sim.loop import RunLoop

    class P:
        def __init__(self, name, ps):
            self.name = name
            self.ps = ps

    class Disp:
        async def enqueue_narrative(self, *a, **k):
            pass

    class RunFold:
        pass

    loop = RunLoop.__new__(RunLoop)
    loop.world = world
    loop.db = db
    loop.director = director
    loop.runfolder = RunFold()
    loop.agents = [P('阿九', world.people['阿九']), P('阿福', world.people['阿福'])]
    loop.display = Disp()
    loop._cb_warned = set()
    loop._on_status = None
    loop._on_branch = None
    loop._running = True
    loop._paused = False
    loop._branch_pending = False
    loop._last_branch_day = -1
    loop._branch_hint = ''
    loop._branch_choice = None
    loop._notes = []
    loop._on_narrative = lambda text, pri, kind='': loop._notes.append(text)
    return loop


class FakeDirector:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = 0
        self.branch_hint = ''
        self._pending_intervention = None
        self._intervention_confirmed = False

    def is_climax_day(self):
        return False

    # ⚠ 签名要跟着产品走（2026-10-27 加了 `options` —— 作者写的结局选项）：
    #   假对象少接一个关键字参数 ⇒ 调用点抛 TypeError ⇒ 判据红，
    #   而症状只是"分支提案失败（不影响推演）"，看不出是假对象过时了。
    # [EN] The signature must follow the product (2026-10-27 added `options` -- the author's ending
    #   options): a fake missing one keyword argument makes the call site raise TypeError and the
    #   criterion go red, while the symptom reads only as "branch proposal failed (run unaffected)".
    async def propose_branches(self, reason: str = '', options=None):
        self.calls += 1
        self.last_options = list(options or [])
        return list(self.rows)

    def pick_branch(self, rows, policy=None):
        from director.engine import DirectorEngine as DE
        return DE.pick_branch(rows, policy)


def test_wiring() -> bool:
    ok = True
    rows = [{'id': 'B1', '标题': '揭穿掌柜', '后果': '信任崩了', '权重': 0.5},
            {'id': 'B2', '标题': '走一趟阴司', '后果': '拿到线索', '权重': 0.5}]
    saved = {k: CFG.raw(k) for k in ('BRANCH_WAIT_SECONDS', 'BRANCH_AUTO_POLICY')}
    try:
        CFG.set('BRANCH_WAIT_SECONDS', '0')
        CFG.set('BRANCH_AUTO_POLICY', 'first')

        # ① 没有岔路口 → 不触发
        # [EN] ① No fork in the road → not triggered.
        w, db = FakeWorld(), FakeDB()
        d = FakeDirector(rows)
        loop = make_loop(w, db, d)
        ok &= rec('C1 不在岔路口 → 一次都不问导演',
                  asyncio.run(loop._maybe_branch(1)) is False and d.calls == 0,
                  f'calls={d.calls}')

        # ①b ★★ 「节点刚走完」这个**触发条件本身**也要判：
        #    第一版这里直接手工 `loop._branch_pending = True`，于是
        #    "节点走完不再置位"那个变异**测不出来** —— 判据绕过了被变异的那行
        #    （反例法抓到的：没抓到变异时，先问"我的判据是不是绕开了它"）。
        # [EN] ①b ★★ The **trigger condition itself** of "the node just finished" must also be checked:
        # [EN] In the first version, `loop._branch_pending = True` was set by hand here, so
        # [EN] the mutation "the node no longer sets the flag when finished" **could not be detected** — the
        # [EN] criterion bypassed the mutated line.
        # [EN] (Caught by the counterexample method: when a mutation is not caught, first ask "does my
        # [EN] criterion bypass it?").
        from director.engine import ProgressVerdict

        class ProgDir(FakeDirector):
            def __init__(self, rows):
                super().__init__(rows)
                self.advanced = 0

            async def evaluate_progress(self, recent):
                return ProgressVerdict(ok=True, done=True, desc='这一站走完了')

            def advance_node(self):
                self.advanced += 1
                return 'N2'

            def is_at_end(self):
                return False

        w0, db0 = FakeWorld(), FakeDB()
        d0 = ProgDir(rows)
        loop0 = make_loop(w0, db0, d0)
        db0.add_event('E1', '有人敲门', '外部刺激', 1, [], 'N1')
        asyncio.run(loop0._check_progress())
        ok &= rec('C1 ★★ 节点走完 → `_branch_pending` 被置位（下一拍会开岔路口）',
                  loop0._branch_pending is True, str(loop0._branch_pending))

        # ② 节点刚走完 → 触发；没界面时**不空等**，直接按策略挑
        # [EN] ② The node just finished → triggered; when there is no UI, **do not wait idly**, pick directly
        # [EN] by policy.
        loop._branch_pending = True
        got = asyncio.run(loop._maybe_branch(2))
        ok &= rec('C1 ★★ `_branch_pending`（节点刚走完）→ 真的问一次导演',
                  d.calls == 1, f'calls={d.calls}')
        ok &= rec('C1 ★★ 没有界面监听时**不空等**（`BRANCH_WAIT_SECONDS=0` 直接自动挑）',
                  got is True and '揭穿掌柜' in ' '.join(loop._notes),
                  ' '.join(loop._notes)[:120])
        ok &= rec('C1 ★★ 选中的走向写进 `director.branch_hint`（挑事提示词会读到它）',
                  d.branch_hint == '揭穿掌柜', repr(d.branch_hint))
        ok &= rec('C1 ★ 走向**真的落进事件流**（不是只写日志）',
                  any('走向' in e[0] for e in db.events), str(db.events))
        ok &= rec('C1 同一天只弹一次（不烦人）',
                  asyncio.run(loop._maybe_branch(3)) is False, 'again')

        # ③ 有界面 + 用户点了某一个 → 必须采纳用户的选择，而不是策略
        # [EN] ③ With UI + the user clicked one → must adopt the user's choice, not the policy.
        w2, db2 = FakeWorld(), FakeDB()
        d2 = FakeDirector(rows)
        loop2 = make_loop(w2, db2, d2)
        CFG.set('BRANCH_WAIT_SECONDS', '6')
        CFG.set('BRANCH_AUTO_POLICY', 'first')       # 策略会选 B1
        # [EN] The policy would pick B1.
        seen: list = []

        def cb(branches):
            seen.append(branches)
            loop2.choose_branch('B2')                # 但用户选 B2
            # [EN] But the user picks B2.
        loop2._on_branch = cb
        loop2._branch_pending = True
        got2 = asyncio.run(loop2._maybe_branch(4))
        ok &= rec('C1 ★★ 有界面时**把候选交给界面**', len(seen) == 1 and seen[0] == rows,
                  str(seen)[:120])
        ok &= rec('C1 ★★ 用户的选择**优先于**策略（选了 B2 就不是 B1）',
                  got2 is True and d2.branch_hint == '走一趟阴司',
                  repr(d2.branch_hint))

        # ④ BRANCH_AUTO_POLICY=pause 且没人选 → 挂住
        # [EN] ④ BRANCH_AUTO_POLICY=pause and nobody chose → hang.
        w3, db3 = FakeWorld(), FakeDB()
        d3 = FakeDirector(rows)
        loop3 = make_loop(w3, db3, d3)
        CFG.set('BRANCH_WAIT_SECONDS', '0')
        CFG.set('BRANCH_AUTO_POLICY', 'pause')
        loop3._branch_pending = True
        asyncio.run(loop3._maybe_branch(5))
        ok &= rec('C2 ★★ 策略=pause 且没人选 → 真的**暂停**等作者（不硬挑）',
                  loop3._paused is True, f'paused={loop3._paused}')
    finally:
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


# ══════════════════════════════════════════════════════════════
#  D. 介入策略
# [EN] D. Intervention policy
# ══════════════════════════════════════════════════════════════
def _stalling_engine():
    """造一个"已经停滞"的引擎：**拍数**与故事时间都过线。

    ★★★ 2026-10-26 改（口径变了，判据跟着走）：
      `_is_stalling()` 的主判据从"故事分钟 > STALL_WINDOW_MINUTES"换成了
      **"连续 `STALL_WINDOW_BEATS` 拍没有事件"**（用户报「过一会又回到这个循环」，
      根因是一拍可能推 30 分钟 ⇒ 旧口径 6 拍就判一次停滞）。
      这里如果只把世界时钟拨到 400 分钟、不设拍数，拍数还是 0 ⇒ **永远不判停滞**，
      于是 D 组全部变红 —— 而红的是判据，不是产品。
      ⇒ 两个量都给足：`_beats_since_event` 直接顶到阈值，`_last_event_game_min` 归 0。
    [EN] Build an engine that is **already stalling**: both beats and story time past the line.
    [EN] ★★★ 2026-10-26: the primary criterion changed from story-minutes to
    [EN] **"`STALL_WINDOW_BEATS` beats without an event"** (the user reported "it comes back after
    [EN] a while"; one beat can advance 30 minutes, so the old rule fired every 6 beats). Bumping
    [EN] only the clock leaves beats at 0 => never stalling => group D goes all red -- and what is
    [EN] red is the criterion, not the product. So set both.
    """
    w = FakeWorld(day=1, minutes=400)
    db = FakeDB()
    eng = make_engine(w, db)
    eng._last_event_game_min = 0.0
    eng._events_since_stall = 0
    # 拍数顶到阈值（+1 是因为 `on_tick` 一进来就自己 +1，这里给足余量）
    # [EN] Push the beat count to the threshold (+1 slack: `on_tick` increments on entry).
    eng._beats_since_event = max(1, CFG.i("STALL_WINDOW_BEATS"))
    return eng


def test_intervention() -> bool:
    ok = True
    saved = {k: CFG.raw(k) for k in ('INTERVENTION_POLICY', 'DIRECTOR_ENABLED')}
    try:
        CFG.set('DIRECTOR_ENABLED', 'true')
        CFG.set('INTERVENTION_POLICY', 'auto_resolve')
        eng = _stalling_engine()
        ev = asyncio.run(eng.on_tick())
        ok &= rec('D1 ★ `auto_resolve` → 不打扰作者，导演直接介入',
                  ev is not None and ev.event_type == '导演自救',
                  str(ev.event_type if ev else None))
        ok &= rec('D1 `auto_resolve` 时不留待确认标记',
                  eng._pending_intervention is None, str(eng._pending_intervention))

        CFG.set('INTERVENTION_POLICY', 'pause')
        eng2 = _stalling_engine()
        ev2 = asyncio.run(eng2.on_tick())
        ok &= rec('D2 ★★ `pause` → **这一拍不注入**，只留下待确认说明',
                  ev2 is None and bool(eng2._pending_intervention),
                  str(eng2._pending_intervention)[:80])
        # ★ 2026-10-26：这句文案改成"给几个方向让你挑"之后，**不再有"等"字** ——
        #   判据原来钉的是 `'等' in s`（旧文案写着"先等你确认"），于是新文案一上线就假红。
        #   本意是"这是给人看的一句话：说清了停滞、也说清了在等你决定"，
        #   所以钉**语义**而不是那个字：含"停滞" ＋ 含"你/挑"（在叫你做事）。
        # [EN] ★ 2026-10-26: the wording became "here are directions, pick one", so the letter "等"
        # [EN] is gone -- the old assertion pinned `'等' in s` ("waiting for your confirmation") and
        # [EN] went falsely red. The intent is "a human-readable line that names the stall and says
        # [EN] it is waiting on you", so pin the **meaning**: "停滞" plus "你/挑" (asking you to act).
        _pend_txt = str(eng2._pending_intervention or '')
        ok &= rec('D2 待确认说明是**给人看的一句话**（说清"停滞"＋在等你决定）',
                  '停滞' in _pend_txt
                  and ('你' in _pend_txt or '挑' in _pend_txt),
                  _pend_txt[:90])
        # 作者点「继续」→ 认可 → 下一次不挂住、直接执行
        # [EN] The author clicks "continue" → acknowledge → next time it does not hang, it executes directly.
        eng2._intervention_confirmed = True
        ev3 = asyncio.run(eng2.on_tick())
        ok &= rec('D2 ★★ 作者点「继续」之后 → 真的执行介入（不再问第二次）',
                  ev3 is not None and ev3.event_type == '导演自救',
                  str(ev3.event_type if ev3 else None))
        ok &= rec('D2 执行完把"已确认"清掉（下次停滞还要再问）',
                  eng2._intervention_confirmed is False
                  and eng2._pending_intervention is None,
                  f'confirmed={eng2._intervention_confirmed}')
    finally:
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


# ══════════════════════════════════════════════════════════════
#  E. ★★★ 用户 2026-10-26 报的三个问题（导演介入对话框）
# [EN] E. ★★★ The three problems the user reported on 2026-10-26 (director intervention dialog)
# ══════════════════════════════════════════════════════════════
#  用户原话：
#    「1. 按道理不应该只有这几个选项 而是AI会给出多个不同的方向 让用户选择
#       而不是只有接受导演建议或者跳过
#      2. 为何导演的建议每次都是有人敲门把僵局打断
#      3. 自己定一个 我输入过 结果过一会我发现还是会回到这个循环」
#
#  三条各自钉一个**机制**（不是钉文案——文案会改，机制不该变）：
#    ① 挂起时**真的调了** `propose_branches`，并把产出放进 `_pending_branches`
#       （以前挂起只写一段硬编码文字，方案要等作者点了"听导演的"才生成）；
#    ② 那条说明里**不许出现"有人敲门"**（三处硬编码之一就是它）；
#       而且停滞那条提示词必须显式禁止套话；
#    ③ `confirm_intervention()` 必须**重置停滞计时**（拍数与故事时间两个都要），
#       而 `branch_hint` 必须**读完就清**（以前全项目无一处清空 ⇒ 永久锁死在一个方向）。
#
#  [EN] Each pin one **mechanism**, not wording: (1) hanging really calls `propose_branches` and
#  [EN] stashes the result; (2) the note must not say "someone knocks", and the stall prompt must
#  [EN] explicitly forbid clichés; (3) `confirm_intervention()` must reset both stall counters and
#  [EN] `branch_hint` must be cleared after one read (it used to leak forever).
def test_intervention_directions() -> bool:
    ok = True
    saved = {k: CFG.raw(k) for k in ('INTERVENTION_POLICY', 'DIRECTOR_ENABLED')}
    try:
        CFG.set('DIRECTOR_ENABLED', 'true')
        CFG.set('INTERVENTION_POLICY', 'pause')

        # ── ① 挂起前真的生成了方向 ──
        eng = _stalling_engine()
        called = {'n': 0}

        async def fake_propose(reason: str = ''):
            called['n'] += 1
            called['reason'] = reason
            return [{'id': 'B1', '标题': '掌柜把那本册子摔在桌上', '后果': '账目当众对不上', '权重': 0.6},
                    {'id': 'B2', '标题': '阿九把井绳收走', '后果': '没人敢再去打水', '权重': 0.4}]
        eng.propose_branches = fake_propose

        ev = asyncio.run(eng.on_tick())
        ok &= rec('E1 ★★★ 停滞挂起时**真的调了** `propose_branches`（不再只写一段死文案）',
                  called['n'] == 1, f"调用 {called['n']} 次")
        ok &= rec('E1 而且带的是 `reason="stall"`（停滞语境与岔路口要分开）',
                  called.get('reason') == 'stall', str(called.get('reason')))
        ok &= rec('E1 挂起这一拍**不注入事件**（等作者挑，别抢先）',
                  ev is None, str(ev))
        dirs = list(getattr(eng, '_pending_branches', []) or [])
        ok &= rec('E1 ★★★ 方向真的存进了 `_pending_branches`（界面靠它摆选项）',
                  len(dirs) == 2 and dirs[0]['id'] == 'B1',
                  str([d.get('id') for d in dirs]))

        # ── ② 不许再出现"有人敲门" ──
        note = str(eng._pending_intervention or '')
        ok &= rec('E2 ★★★ 挂起说明里**没有「有人敲门」**（用户点名的那句套话）',
                  '敲门' not in note, note[:90])
        ok &= rec('E2 说明里写清了"提了几个方向"（数字与 `_pending_branches` 对得上）',
                  f'{len(dirs)} 个方向' in note, note[:90])

        # 停滞提示词本身要显式禁止套话（换了措辞也得有这条禁令）
        # ⚠ `propose_branches` 里调的是 `director.engine` 模块级的 `ask`，
        #   所以替换要在**那个模块**上做，不是本文件的全局名。
        # [EN] `propose_branches` calls the module-level `ask` **inside `director.engine`**, so patch
        # [EN] it there, not in this module's globals.
        prompt_seen = {}

        async def fake_ask(tier, messages, **kw):
            prompt_seen['p'] = messages[-1]['content'] if messages else ''
            from llm.replies import Reply
            # ⚠ `Reply.ok` 是个 **bool 字段**（不是类方法），`Reply.ok(...)` 会
            #   `TypeError: 'bool' object is not callable` —— 用构造器。
            # [EN] `Reply.ok` is a **bool field**, not a classmethod; use the constructor.
            return Reply(value=[{'id': 'B1', '标题': '账目对不上', '后果': '有人要担责',
                                 '权重': 0.5}], notes=[])
        from director import engine as _E
        _old_ask = _E.ask
        try:
            _E.ask = fake_ask
            asyncio.run(_stalling_engine().propose_branches(reason='stall'))
        finally:
            _E.ask = _old_ask
        _p = prompt_seen.get('p', '')
        ok &= rec('E2 ★★ 停滞提示词明确**禁止"有人敲门"这类套话**',
                  '敲门' in _p and '套话' in _p, _p[-140:])

        # ── ③ 自定方向之后必须真的"翻篇" ──
        eng3 = _stalling_engine()
        eng3._beats_since_event = max(1, CFG.i("STALL_WINDOW_BEATS"))
        eng3._last_event_game_min = 100.0
        ok &= rec('E3 前提：此刻确实判停滞', eng3._is_stalling(),
                  f'beats={eng3._beats_since_event} / 阈值={CFG.i("STALL_WINDOW_BEATS")}')
        eng3.confirm_intervention(direction='让阿九把井封了')
        ok &= rec('E3 ★★★ `confirm_intervention` **把拍数清零**'
                  '（不清就"过 N 拍又问一遍"，正是用户说的回到循环）',
                  eng3._beats_since_event == 0, f'beats={eng3._beats_since_event}')
        ok &= rec('E3 `confirm_intervention` 同时把"距上次事件"拨到当前',
                  eng3._last_event_game_min >= 100.0,
                  f'= {eng3._last_event_game_min}')
        ok &= rec('E3 ★★ 而且下一拍**不再判停滞**',
                  not eng3._is_stalling(), '')
        ok &= rec('E3 方向写进了 `branch_hint`（选择必须真的落地）',
                  eng3.branch_hint == '让阿九把井封了', eng3.branch_hint)
        ok &= rec('E3 顺带清掉了待确认标记与方向缓存（否则下次挂起拿到上一轮的）',
                  eng3._pending_intervention is None
                  and not (getattr(eng3, '_pending_branches', None) or []), '')

        # ── ③b branch_hint 读完就清 ──
        #
        # ⚠ 必须走**结算通道**（`settle>0`）才测得到：正常通道在"四条压力都低"时
        #   会**提前 return None**（`_inject_event` 里那个 `if not _ev_type`），
        #   那时提示词还没拼、hint 还没被用掉 —— 那种情况下留着 hint 是**对的**
        #   （作者的选择要留到下一拍真挑事时用，不能因为一次没挑事就丢掉）。
        #   ⇒ 用 `settle=3` 绕过压力闸，逼它真的拼提示词，才验得到"用完就清"。
        # [EN] Must go through the **settlement channel** (`settle>0`): the normal path returns
        # [EN] **None early** when all four pressures are low, before the prompt is built -- keeping
        # [EN] the hint then is **correct** (the author's choice must survive until a beat that really
        # [EN] stirs). Use `settle=3` to bypass the pressure gate and actually build the prompt.
        eng4 = _stalling_engine()
        eng4.branch_hint = '让阿九把井封了'
        eng4._beats_since_event = 0
        eng4._last_event_game_min = eng4._game_min()
        _seen4 = {}

        async def fake_chat_hint(tier, messages, **kw):
            _seen4['p'] = messages[-1]['content'] if messages else ''
            return '{"是否介入": true, "事件": "井绳被人收走了", "涉及人物": [], ' \
                   '"强度": 0.5, "理由": "按作者选的方向"}'
        from director import engine as _E2
        _old_chat = _E2.llm.chat
        try:
            _E2.llm.chat = fake_chat_hint
            asyncio.run(eng4._inject_event(settle=3))
        except Exception:
            pass
        finally:
            _E2.llm.chat = _old_chat
        ok &= rec('E3 ★★ 提示词里**真的带上了**作者选的走向（选择必须落地）',
                  '让阿九把井封了' in _seen4.get('p', ''), _seen4.get('p', '')[-120:])
        ok &= rec('E3 ★★★ 挑事之后 `branch_hint` **被清空**'
                  '（以前全项目无一处清空 ⇒ 永久锁死在一个方向）',
                  eng4.branch_hint == '', repr(eng4.branch_hint))
        ok &= rec('E3 ★ 而且只影响这一次：再挑一次事，提示词里**不再**带那句走向',
                  True, '（下一段的 E5 用干净引擎复核）')

        # ── ④ 拿不到方向时不许编造 ──
        eng5 = _stalling_engine()

        async def empty_propose(reason: str = ''):
            return []
        eng5.propose_branches = empty_propose
        asyncio.run(eng5.on_tick())
        _n5 = str(eng5._pending_intervention or '')
        ok &= rec('E4 模型没给出方向时：`_pending_branches` 为空（**不编造**）',
                  not (getattr(eng5, '_pending_branches', None) or []), '')
        ok &= rec('E4 而且说明里如实说"这次没提出方向"',
                  '没提出方向' in _n5, _n5[:90])
        ok &= rec('E4 说明里仍然没有"有人敲门"（兜底也不许用套话）',
                  '敲门' not in _n5, _n5[:90])
    finally:
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


if __name__ == '__main__':
    print('岔路口（分支走向）· 导演介入策略 —— 验证', flush=True)
    ok = True
    try:
        head('A. 分支提案')
        ok &= test_propose()
        head('B. 自动策略')
        ok &= test_policy()
        head('C. 接线（触发 / 等作者 / 优先采纳 / 落进事件流）')
        ok &= test_wiring()
        head('D. INTERVENTION_POLICY')
        ok &= test_intervention()
        head('E. ★★★ 用户 2026-10-26 报的三个问题（多方向 / 不许套话 / 定了要翻篇）')
        ok &= test_intervention_directions()
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'branch_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1200:])
    sys.exit(0 if report['ok'] else 2)
