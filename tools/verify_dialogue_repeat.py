# -*- coding: utf-8 -*-
"""验证：**说了一样的话 → 先问是不是非说不可**（用户 2026-10-07）。

用户原话
--------
「如果说了一样的话，你要看下是不是必须，如果不是必须重复，就让人物
  重新想清楚当前情况，重新说话」
「重说的过程不要让这个人真的说出来，而是在内部计算」

背景
----
去重护栏（`SceneBuilder._said`）只认"一模一样"——它分不清两类完全不同的重复：

  · **模型偷懒复读**（"先看水"一字不差出现 4 次）→ 该拦；
  · **这句话非说不可**（追问、对方没听见、口语应答"嗯"）→ 拦了反而是错的。

以前一律丢，丢的代价是**那一拍可能整拍空白**（对照探针里就是这样：
桩反复说同一句，A 段第 3 拍起全空）。

现在的做法：**把"是不是必须"交回给人物自己** —— 让他重新想清楚当前情况
再说一次；他若仍坚持原话，那就是"必须"，放行。

这一支钉住的行为（**每条都要能红**）：

  A **窄判据**：口语应答（"嗯""……"）放行；「先看水」这种**短但不该放行**的
    当真台词处理（按长度猜会把护栏搞废）。
  B **护栏开口**：`already_said` 只读、`allow_repeat` 放行、且放行不误伤别人。
  C **重说的四种结局**（单点调用 `_review_repeat`）：
      没重复 → 原样；短应答 → 不重说；仍坚持 → 放行；想了之后改口 → 用新话。
  D **端到端**：真跑两拍，桩第二拍复读同一句 →
      · 屏幕上出现的是**改口后**的那句；
      · **第一遍那句没有上屏**（"重说是内部盘算"）；
      · 缓冲里也**没有**留下第一遍那句话（别的角色听不见它）；
      · 桩确实**多被调了一次**（重说真发生了，不是碰巧）。
  E **退回得干净**：`DIALOGUE_RETRY_DUP=false` → 老行为（那句被丢，屏幕空白）；
    `DIALOGUE_RETRY_MAX=0` → 不重说（省一次调用），但坚持时仍然放行。
  F **内部盘算不落痕**：`decide()` 只读——重说不会写记忆、不会推屏幕。

跑法：.venv\\Scripts\\python.exe tools/verify_dialogue_repeat.py
产出：assets/screenshots/dialogue_repeat_report.json

English:
Verification: **if it says the same thing -> first ask whether it must be said** (user
2026-10-07).
User's exact words
--------
"If it says the same thing, you should check whether it is necessary. If it is not necessary to
repeat, have the character
  rethink the current situation and speak again"
"The restatement process should not let this person actually say it out loud, but compute it
internally"
Background
----
The deduplication guardrail (`SceneBuilder._said`) only recognizes "exactly the same" -- it
cannot distinguish two completely different kinds of repetition:
  · **Model laziness repeating** ("先看水" appears 4 times verbatim) -> should block;
  · **This line must be said** (follow-up question, the other party did not hear, colloquial response "嗯") -> blocking it is actually wrong.
Previously it was always dropped; the cost of dropping was that **that beat might be entirely
blank** (in the control probe it was exactly like this:
the stub repeatedly says the same line, and from beat 3 of segment A onward it is all blank).
The current approach: **hand "whether it is necessary" back to the character himself** -- let
him rethink the current situation
and say it again; if he still insists on the original line, then it is "necessary", and it is
allowed through.
The behavior pinned by this branch (**every one must be able to go red**):
  A **Narrow criterion**: colloquial responses ("嗯", "……") are allowed through; something like "先看水" that is **short but should not be allowed through**
    is treated as a real line (guessing by length would ruin the guardrail).
  B **Guardrail openings**: `already_said` is read-only, `allow_repeat` allows through, and the allowance does not wrongly affect others.
  C **The four outcomes of restatement** (single-point call to `_review_repeat`):
      no repeat -> as-is; short response -> do not restate; still insists -> allow through; after thinking, changes position -> use the new line.
  D **End-to-end**: actually run two beats, the stub repeats the same line on the second beat ->
      · what appears on screen is the line **after changing position**;
      · **the first-pass line does not go on screen** ("restatement is internal deliberation");
      · the first-pass line also **does not** remain in the buffer (other characters cannot hear it);
      · the stub is indeed **called one extra time** (the restatement really happened, it was not a coincidence).
  E **Clean fallback**: `DIALOGUE_RETRY_DUP=false` -> old behavior (that line is dropped, screen blank);
    `DIALOGUE_RETRY_MAX=0` -> do not restate (save one call), but still allow through when insisting.
  F **Internal deliberation leaves no trace**: `decide()` is read-only -- restatement does not write memory or push to screen.
Run: .venv\\Scripts\\python.exe tools/verify_dialogue_repeat.py
Output: assets/screenshots/dialogue_repeat_report.json
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

from verify_ui_common import safe_rmtree                       # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

#: 屏幕上**真的出现了**的句子（`_push_narrative` 收到什么就是什么）
# [EN] : the sentence that **actually appeared** on screen (whatever `_push_narrative` receives is what
# [EN] it gets)
SCREEN: list[str] = []


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════════
#  夹具（与 verify_dialogue_thread 同源的最小世界）
# [EN] Fixture (minimal world, same origin as verify_dialogue_thread)
# ══════════════════════════════════════════════════════════════════
def make_world(names=('主角', '柳娘')):
    from world.state import WorldState, PersonState
    w = WorldState(scene='司天台', weather='雨')
    for n in names:
        w.add_person(PersonState(n, identity=f'{n}的身份', personality='话少'))
    w.place_names = ['司天台', '西市']
    w.worldview_text = '唐，长安。城里的时辰不是听天，是听更鼓。'
    return w


async def _noop(*a, **k):
    return None


async def _false(*a, **k):
    return False


class _StubDirector:
    def __init__(self):
        self._pending_intervention = None

    async def on_tick(self):
        return None

    async def on_day_start(self):
        return 0.0

    def is_at_end(self):
        return False

    def current_node_info(self):
        return None

    def evaluate_progress(self, events):
        raise AssertionError('不该走到进度评估')


def make_loop(w, *, script_mode=True):
    """造一个只够跑 `_tick` 的 RunLoop（不装配项目、不连数据库）。
        English:
    Build a RunLoop that is only enough to run `_tick` (do not assemble the project, do not connect
    to the database).
    """
    from sim.loop import RunLoop
    from agent.core import Agent

    class _DB:
        def get_summaries(self, k=6, scope='故事'):
            return []

        def recent_events(self, n=20, game_day=0):
            return []

        def retrieve_memory(self, *a, **k):
            return []

        def add_memory(self, *a, **k):
            pass

        def add_event(self, *a, **k):
            pass

        def count_memories(self, *a, **k):
            return 0

    db = _DB()
    agents = [Agent(w.people[n], db, w) for n in w.people]
    loop = RunLoop(w, agents, _StubDirector(), db, None)   # run=None：不落盘
    # [EN] run=None: do not persist to disk
    loop._rng = random.Random(7)
    loop._push_narrative = lambda text, *a, **k: SCREEN.append(str(text))
    loop._status = lambda *a, **k: None
    loop._maybe_branch = _noop
    loop._maybe_dispatch = _noop
    loop._run_backstage = _noop
    loop._check_progress = _false
    loop._maybe_group_chat = _noop
    loop._sync_crowd = _noop
    loop._flush_tick = lambda *a, **k: None
    loop._maybe_quiet = lambda: None
    return loop


def patch_decide(fn):
    """把 `Agent.decide` 换成桩。

    `fn(谁, 这个人的第几次决策, context) -> JSON 文本` —— 用回调而不是固定队列，
    因为这一支的关键就是**同一个人的第一次决策与"重说"要走不同分支**
    （而分岔点只有 `context` 里那句"你刚说过"）。
    
        English:
    Replace `Agent.decide` with a stub.
        `fn(who, this person's nth decision, context) -> JSON text` -- use a callback instead of a fixed queue,
        because the key point of this branch is that **the same person's first decision and the "repeat" must go down different branches**
        (and the branch point is only the line "you just said" in `context`).
    """
    from agent.core import Agent
    real = Agent.decide
    calls: list[tuple[str, int, str]] = []
    per: dict[str, int] = {}

    async def _decide(self, context: str = ''):
        from llm import router as R
        real_chat = R.llm.chat

        async def _fake_chat(tier, messages, **kw):
            name = str(self.name)
            i = per.get(name, 0)
            per[name] = i + 1
            calls.append((name, i, str(context)))
            body = fn(name, i, str(context))
            return (body, {}) if kw.get('return_meta') else body

        R.llm.chat = _fake_chat
        try:
            return await real(self, context)
        finally:
            R.llm.chat = real_chat

    Agent.decide = _decide
    return calls, lambda: setattr(Agent, 'decide', real)


def say(who: str, line: str, to: str = '') -> str:
    return json.dumps({'动作': 'speak', '参数': {'目标': to}, '台词': line,
                       '内心': '', '理由': '接话'}, ensure_ascii=False)


def act(verb: str, target: str = '') -> str:
    return json.dumps({'动作': verb, '参数': {'目标': target}, '台词': '',
                       '内心': '', '理由': '动作'}, ensure_ascii=False)


def lines_of(loop) -> list[str]:
    """这一轮真的进了剧本的台词（从**真词条**读，与落盘同源）。
        English:
    This round really entered the script's dialogue (read from the **real entry**, same source as
    what is written to disk).
    """
    from display import script_render as SR
    from display import script as S
    b = getattr(loop, '_builder', None)
    if b is None:
        return []
    groups = list(getattr(b, 'scenes', None) or [])
    cur = getattr(b, 'current', None)
    if cur is not None and cur not in groups:
        groups.append(cur)
    out: list[str] = []
    for sc in groups:
        for e in (getattr(sc, 'entries', None) or []):
            if getattr(e, 'kind', '') == S.DIALOGUE:
                one = SR.one_line(e)
                if one:
                    out.append(one)
    return out


# ══════════════════════════════════════════════════════════════════
#  A —— 判据要窄（按长度猜会把护栏搞废）
# [EN] A -- criterion must be narrow (guessing by length would ruin the guardrail)
# ══════════════════════════════════════════════════════════════════
def test_narrow_judge() -> None:
    from sim.loop import is_short_reply
    ok('A1 口语应答算"可以重复"：嗯 / …… / 好 / 知道了', all(
        is_short_reply(x) for x in ('嗯', '……', '…', '好', '知道了', '嗯。',
                                    '唉', '是的', '')), '')
    # ★ 这条是本组的重点：「先看水」只有 4 个字，但它是一句**真台词**，
    #   按长度猜（≤6 字）会把它判成应答放行 —— 那护栏就等于白设。
    # [EN] ★ This one is the focus of this group: "先看水" is only 4 characters, but it is a **real line**,
    # [EN] guessing by length (≤6 chars) would judge it as a response and let it through -- then the
    # [EN] guardrail is pointless.
    ok('A2 ★ 短台词**不**算应答（「先看水」3 个字、「不许改」3 个字，'
       '可它们都是真话）',
       not is_short_reply('先看水') and not is_short_reply('不许改'),
       '')
    ok('A3 正常台词当然不算', not is_short_reply('漏刻只许校，不许改。'), '')


# ══════════════════════════════════════════════════════════════════
#  B —— 护栏开的那两个口子
# [EN] B -- the two openings the guardrail provides
# ══════════════════════════════════════════════════════════════════
def test_guard_doors() -> None:
    from display.scene_builder import SceneBuilder
    from agent.core import Action

    class _A:
        name = '主角'

    w = make_world()
    b = SceneBuilder(w, day=1)
    a = _A()
    one = Action(verb='speak', dialogue='水不会说谎，人会。')
    ok('B1 没人说过 → `already_said` 说不算重复', not b.already_said('主角', '水不会说谎，人会。'))
    ok('B2 第一次上屏（护栏放行）', b._worth_emitting(a, one))
    ok('B3 ★ 第二次被拦（去重还在起作用）',
       not b._worth_emitting(a, Action(verb='speak', dialogue='水不会说谎，人会。')))
    ok('B4 `already_said` 认得出他说过了', b.already_said('主角', '水不会说谎，人会。'))
    b.allow_repeat('主角', '水不会说谎，人会。')
    ok('B5 ★ 登记放行之后 → 真的过去了（"必须重复"的通路）',
       b._worth_emitting(a, Action(verb='speak', dialogue='水不会说谎，人会。')))
    ok('B6 放行按 (人, 话) 精确匹配 —— 不误伤别人',
       not b.already_said('柳娘', '水不会说谎，人会。')
       and not b.already_said('主角', '另一句话。'))
    ok('B7 放行名单在**这一天内**有效（是新的一句就照常走护栏）',
       not b.already_said('主角', '漏刻只许校，不许改。'), '')


# ══════════════════════════════════════════════════════════════════
#  C —— `_review_repeat` 的几种结局
# [EN] C -- the several outcomes of `_review_repeat`
# ══════════════════════════════════════════════════════════════════
def _fresh_loop_with_said(pressing: bool = True):
    """一个"主角已经说过那句话"的世界。

    ⚠ 必须**显式给这一拍的重说预算**（`_retry_left`）：真跑时它由 `_tick`
      重置，而这里直接调 `_review_repeat`（C 组就是这么红的 —— 预算 0，
      重说一次都没发生，判据却"看着像产品坏了"）。
    
        English:
    A world where "Shen Yan has already said that line".
        ⚠ Must **explicitly give this beat's repeat budget** (`_retry_left`): in a real run it is set by `_tick`
          reset, while here `_review_repeat` is called directly (this is exactly how group C went red -- budget 0,
          not a single repeat happened, yet the criterion "looked like the product was broken").
    """
    w = make_world()
    loop = make_loop(w)
    loop._retry_left = CFG.i('DIALOGUE_RETRY_MAX')
    b = loop._ensure_builder()
    b._said.add(('主角', '水不会说谎，人会。'))
    # ★★ 2026-10-26：**"非说不可"现在要查三个条件**（`_must_repeat_reason`：
    #   对方没听见 / 在追问），而它读的是 `world.recent_lines` 这本**场上公开的账**。
    #   夹具只往 `_said`（"说过什么"的登记）里塞，`recent_lines` 是空的 ⇒
    #   产品按新规矩判"不算非说不可"、把这一句丢掉 ⇒ C4/D7/D12 全红。
    #   ⚠ 这不是产品退步：2026-10-19 的实测（同一句隔十句原样重现）证明
    #     "无条件放行"会让戏在原地打转。**判据要跟着新契约走，并且成对**：
    #       `pressing=True`  → 有人追问过 ⇒ 放行（测"非说不可"这条路）
    #       `pressing=False` → 没人追问   ⇒ 丢掉（测"不再无条件放行"）
    if pressing:
        w.recent_lines.append({'kind': 'speak', 'who': '主角',
                               'text': '水不会说谎，人会。'})
        w.recent_lines.append({'kind': 'speak', 'who': '柳娘',
                               'text': '你说什么？'})
    return w, loop


def test_review_outcomes() -> None:
    from agent.core import Action
    loop_agent = lambda loop: next(a for a in loop.agents if a.name == '主角')

    # ① 没重复 → 原样返回，且**不花调用**
    # [EN] ① No repeat -> return as-is, and **no call spent**
    w, loop = _fresh_loop_with_said()
    calls, restore = patch_decide(lambda n, i, c: say(n, '漏刻只许校，不许改。'))
    try:
        got = asyncio.run(loop._review_repeat(
            loop_agent(loop), Action(verb='speak', dialogue='漏刻只许校，不许改。')))
    finally:
        restore()
    ok('C1 没重复 → 原样返回，一次调用都不花',
       got.dialogue == '漏刻只许校，不许改。' and not calls, f'调用 {len(calls)} 次')

    # ② 短应答 → 原样返回，也不花调用（人本来就会重复"嗯"）
    # [EN] ② Short response -> return as-is, also no call spent (people naturally repeat "嗯")
    w, loop = _fresh_loop_with_said()
    loop._ensure_builder()._said.add(('主角', '嗯'))
    calls, restore = patch_decide(lambda n, i, c: say(n, '嗯'))
    try:
        got = asyncio.run(loop._review_repeat(
            loop_agent(loop), Action(verb='speak', dialogue='嗯')))
    finally:
        restore()
    ok('C2 口语应答("嗯")重复 → 放行，不浪费一次调用',
       got.dialogue == '嗯' and not calls, f'调用 {len(calls)} 次')

    # ③ 重复 + 重说**改口** → 用新话
    # [EN] ③ Repeat + restatement **changes position** -> use the new words
    w, loop = _fresh_loop_with_said()
    calls, restore = patch_decide(
        lambda n, i, c: say(n, '先看水。') if '你刚说过' in c else say(n, '水不会说谎，人会。'))
    try:
        got = asyncio.run(loop._review_repeat(
            loop_agent(loop), Action(verb='speak', dialogue='水不会说谎，人会。')))
    finally:
        restore()
    ok('C3 ★ 重说之后改口 → 用**新话**（这就是"重新想清楚、重新说话"）',
       got.dialogue == '先看水。', f'拿到 {got.dialogue!r}')
    ok('C3b ★ 重说真的发生了（多花了一次调用）', len(calls) == 1,
       f'调用 {len(calls)} 次')
    ok('C3c 重说的提示里点了名：**这是开口之前的盘算**（不是当众改口）',
       calls and '别人听不见' in calls[0][2] and '你刚说过' in calls[0][2],
       calls[0][2][:40] if calls else '')

    # ④ 重复 + 重说**仍坚持** → 放行（"必须重复"是他自己认下来的）
    # [EN] ④ Repeat + restatement **still insists** -> allow through ("must repeat" is what he himself
    # [EN] conceded)
    w, loop = _fresh_loop_with_said()
    calls, restore = patch_decide(lambda n, i, c: say(n, '水不会说谎，人会。'))
    try:
        got = asyncio.run(loop._review_repeat(
            loop_agent(loop), Action(verb='speak', dialogue='水不会说谎，人会。')))
    finally:
        restore()
    b = loop._builder
    ok('C4 ★ 重说之后**仍是同一句** → 返回原句（当作非说不可）',
       got.dialogue == '水不会说谎，人会。', f'拿到 {got.dialogue!r}')
    ok('C4b ★ 并且已经登记放行 —— 护栏不会再把它丢掉',
       not b.already_said('主角', '水不会说谎，人会。'), '')
    from agent.core import Action as _Act

    class _A2:
        name = '主角'
    ok('C4c 放行是**真的**（走一遍护栏：它过去了）',
       b._worth_emitting(_A2(), _Act(verb='speak', dialogue='水不会说谎，人会。')), '')

    # ⑤ 重复 + 重说**决定不说了** → 尊重他（不把原句塞回去）
    # [EN] ⑤ Repeat + restatement **decides not to say it** -> respect him (do not stuff the original line
    # [EN] back)
    w, loop = _fresh_loop_with_said()
    calls, restore = patch_decide(lambda n, i, c: act('wait'))
    try:
        got = asyncio.run(loop._review_repeat(
            loop_agent(loop), Action(verb='speak', dialogue='水不会说谎，人会。')))
    finally:
        restore()
    ok('C5 ★ 想了之后决定不说 → 用他的新动作（不把原句塞回去）',
       str(getattr(got, 'verb', '')) == 'wait' and not getattr(got, 'dialogue', ''),
       f'{got.verb} {getattr(got, "dialogue", "")!r}')
    ok('C5b 这一支**不**登记放行（他没坚持，不需要开口子）',
       ('主角', '水不会说谎，人会。') not in loop._builder._forced,
       str(loop._builder._forced))

    # ⑤c 重说时输出**残缺**（说"要说"、台词却是空的）→ 也别把原句塞回去
    # [EN] ⑤c During restatement the output is **incomplete** (says he wants to say it, but the line is
    # [EN] empty) -> also do not stuff the original line back
    w, loop = _fresh_loop_with_said()
    calls, restore = patch_decide(lambda n, i, c: json.dumps(
        {'动作': 'speak', '参数': {}, '台词': '', '内心': '', '理由': ''},
        ensure_ascii=False))
    try:
        got = asyncio.run(loop._review_repeat(
            loop_agent(loop), Action(verb='speak', dialogue='水不会说谎，人会。')))
    finally:
        restore()
    ok('C5c ★ 重说输出残缺（"要说"却没台词）→ 当成"不说了"，别塞回原句',
       str(getattr(got, 'verb', '')) == 'wait'
       and not getattr(got, 'dialogue', ''),
       f'{getattr(got, "verb", "")} {getattr(got, "dialogue", "")!r}')

    # ⑥ 预算为 0 → 不重说（省调用）
    # [EN] ⑥ Budget is 0 -> do not restate (save the call)
    w, loop = _fresh_loop_with_said()
    loop._retry_left = 0
    calls, restore = patch_decide(lambda n, i, c: say(n, '先看水。'))
    try:
        got = asyncio.run(loop._review_repeat(
            loop_agent(loop), Action(verb='speak', dialogue='水不会说谎，人会。')))
    finally:
        restore()
    ok('C6 这一拍的重说预算用完 → 不重说（原样交回去，让护栏照旧拦）',
       got.dialogue == '水不会说谎，人会。' and not calls, f'调用 {len(calls)} 次')

    # ⑦ 开关关掉 → 老行为
    # [EN] ⑦ Switch turned off -> old behavior
    w, loop = _fresh_loop_with_said()
    old = CFG.b('DIALOGUE_RETRY_DUP')
    CFG.set('DIALOGUE_RETRY_DUP', 'false')
    calls, restore = patch_decide(lambda n, i, c: say(n, '先看水。'))
    try:
        got = asyncio.run(loop._review_repeat(
            loop_agent(loop), Action(verb='speak', dialogue='水不会说谎，人会。')))
    finally:
        restore()
        CFG.set('DIALOGUE_RETRY_DUP', 'true' if old else 'false')
    ok('C7 ★ 关掉开关 → 与从前一字不差（不重说、不花调用）',
       got.dialogue == '水不会说谎，人会。' and not calls, f'调用 {len(calls)} 次')

    # ⑧ 不是 speak → 不碰
    # [EN] ⑧ Not speak -> do not touch
    w, loop = _fresh_loop_with_said()
    calls, restore = patch_decide(lambda n, i, c: act('move', '司天台漏刻科'))
    try:
        got = asyncio.run(loop._review_repeat(
            loop_agent(loop), Action(verb='move', target='司天台漏刻科')))
    finally:
        restore()
    ok('C8 非台词动作不掺和', got.verb == 'move' and not calls, '')


# ══════════════════════════════════════════════════════════════════
#  D —— 端到端：真跑两拍
# [EN] D -- end-to-end: actually run two beats
# ══════════════════════════════════════════════════════════════════
def test_end_to_end() -> None:
    def run_two_beats(reply_on_retry: str, *, retry_on=True, max_retry='2',
                      pressing=True):
        """跑两拍：第一拍他说那句话，第二拍**又想**说同一句。
                English:
        Run two beats: in the first beat he says that line, in the second beat he **wants** to say the
        same line again.
        """
        CFG.set('DIALOGUE_RETRY_DUP', 'true' if retry_on else 'false')
        CFG.set('DIALOGUE_RETRY_MAX', max_retry)
        w = make_world()
        loop = make_loop(w)
        SCREEN.clear()

        def fn(name, i, ctx):
            if name != '主角':
                # 第一拍由柳娘**点名**主角 —— 这样第二拍的主角就是
                # 「该接话的人」（走**领说者**那条路，而不是 rest 那条）。
                # 两条路的接法不同（领说者的话要立刻进缓冲），都得覆盖到。
                # [EN] The first beat has 柳娘 **call out** 主角 by name -- this way, in the second beat, 主角 is
                # [EN] "the person who should take the turn" (goes through the **lead speaker** path, not the rest
                # [EN] path).
                # [EN] The two paths connect differently (the lead speaker's words must immediately enter the buffer),
                # [EN] both must be covered.
                return (say('柳娘', '主角，那一夜的水你说。', to='主角') if i == 0
                        else act('wait'))
            if '你刚说过' in ctx:
                return reply_on_retry
            return say('主角', '水不会说谎，人会。')      # 每一拍都想说同一句
            # [EN] Each beat wants to say the same line

        calls, restore = patch_decide(fn)
        try:
            asyncio.run(loop._tick(1))
            first = list(SCREEN)
            # ★ 2026-10-26：第二拍要想"非说不可"，场上得**真的有人追问过**
            #   （`_must_repeat_reason` 只看这句之后的行）。这里补一句，模拟
            #   "他上一句说完，对方没听清"这个真实情形。
            # [EN] ★ For the second beat to count as "must say", **someone must really have
            # [EN] pressed** (`_must_repeat_reason` only looks at rows after the line). Add one to
            # [EN] model "he said it, the other did not catch it".
            if pressing:
                w.recent_lines.append({'kind': 'speak', 'who': '柳娘',
                                       'text': '你说的什么？再说一遍。'})
            SCREEN.clear()
            asyncio.run(loop._tick(2))
            second = list(SCREEN)
        finally:
            restore()
        CFG.set('DIALOGUE_RETRY_DUP', 'true')
        CFG.set('DIALOGUE_RETRY_MAX', '2')
        return w, loop, first, second, calls

    # ── ① 改口 ──
    # [EN] -- ① changes position --
    w, loop, first, second, calls = run_two_beats(say('主角', '先看水。'))
    ok('D1 ★ 第一拍：那句话正常上屏', any('水不会说谎' in x for x in first),
       ' | '.join(first)[:80])
    ok('D2 ★★ 第二拍：屏幕上出现的是**改口后**的那句（不是空白）',
       any('先看水' in x for x in second), ' | '.join(second)[:90])
    ok('D3 ★★ 第二拍：**第一遍那句没有上屏**（重说是内部盘算）',
       not any('水不会说谎' in x for x in second), ' | '.join(second)[:90])
    said = [r for r in w.recent_lines if r.get('who') == '主角']
    ok('D4 ★★ 缓冲里也只有**最终**那句 —— 别的角色听不见他"没说的话"',
       sum(1 for r in said if '水不会说谎' in str(r.get('text'))) == 1
       and any('先看水' in str(r.get('text')) for r in said),
       str([(r.get('who'), r.get('text')) for r in said]))
    ok('D5 重说确实多花了一次调用（主角：1 + 2 = 3）',
       sum(1 for c in calls if c[0] == '主角') == 3,
       str([(c[0], c[1]) for c in calls]))
    ok('D6 剧本词条里也只有最终那句',
       sum(1 for x in lines_of(loop) if '水不会说谎' in x) == 1
       and any('先看水' in x for x in lines_of(loop)),
       str(lines_of(loop)))

    # ── ② 坚持 ──
    # [EN] -- ② insists --
    w2, loop2, f2, s2, c2 = run_two_beats(say('主角', '水不会说谎，人会。'))
    ok('D7 ★★ 他坚持 → 第二拍**仍然说得出来**（不再被丢成空白）',
       any('水不会说谎' in x for x in s2), ' | '.join(s2)[:90])
    ok('D8 坚持时也花了那一次调用（先问过他，不是直接放行）',
       sum(1 for c in c2 if c[0] == '主角') == 3,
       str([(c[0], c[1]) for c in c2]))

    # ── ③ 关掉开关：老行为（空白） ──
    # [EN] -- ③ turn off the switch: old behavior (blank) --
    w3, loop3, f3, s3, c3 = run_two_beats(say('主角', '先看水。'), retry_on=False)
    ok('D9 ★ 关掉开关 → 老行为：第二拍那句被丢掉（这一拍就没有他的台词）',
       not any('水不会说谎' in x for x in s3)
       and not any('先看水' in x for x in s3),
       ' | '.join(s3)[:90])
    ok('D9b 关掉开关 → 不花重说那次调用（主角只被问 2 次）',
       sum(1 for c in c3 if c[0] == '主角') == 2,
       str([(c[0], c[1]) for c in c3]))

    # ── ④ 预算 0：不重说，但坚持放行的那条路也不走 ──
    # [EN] -- ④ budget 0: do not restate, but the insistence-allowed path is also not taken --
    w4, loop4, f4, s4, c4 = run_two_beats(say('主角', '先看水。'), max_retry='0')
    ok('D10 预算 0 → 不重说，等价于"只去重、不追问"',
       not any('先看水' in x for x in s4)
       and not any('水不会说谎' in x for x in s4),
       ' | '.join(s4)[:80])

    # ── ⑤ 同拍里**不是领说者**的那个人，也要被问这一句 ──
    #   （反例法当场抓出来的缺口：D1~D10 里会说重复话的主角**恰好**都是领说者，
    #    于是 `_tick` 里 rest 那条接线**没有任何判据守着** —— 把它删掉照样全绿。）
    # [EN] -- ⑤ in the same beat, **the person who is not the lead speaker** must also be asked this line
    # [EN] --
    # [EN] (The gap caught on the spot by the counterexample method: in D1~D10, the 主角 who would say
    # [EN] repeated lines is **exactly** always the lead speaker,
    # [EN] so the rest wiring inside `_tick` **has no criterion guarding it** -- delete it and everything
    # [EN] still passes.)
    CFG.set('DIALOGUE_RETRY_MAX', '4')
    w11 = make_world()
    loop11 = make_loop(w11)
    SCREEN.clear()

    def fn11(name, i, ctx):
        if '你刚说过' in ctx:
            return say(name, f'{name}换个说法。')
        if name == '柳娘':
            return say('柳娘', '更鼓早了整整一刻。')
        return say('主角', f'主角第 {i} 句。')

    calls11, restore11 = patch_decide(fn11)
    try:
        asyncio.run(loop11._tick(1))
        SCREEN.clear()
        asyncio.run(loop11._tick(2))
        s11 = list(SCREEN)
    finally:
        restore11()
        CFG.set('DIALOGUE_RETRY_MAX', '2')
    ok('D11 ★★ 同拍**不是**领说者的人，说重复的话也被"先问一句"',
       any('柳娘换个说法' in x for x in s11)
       and not any('这雨下得没完' in x for x in s11), ' | '.join(s11)[:100])

    # ── ⑥ 重说给出的"新句"**也可能是一句老话** → 照样要上屏 ──
    #   对照探针跑出来的：台词池小的时候，桩绕一圈又说回来说过的句子，
    #   第 6 拍于是又空了一次 —— 只按"新句 == 原句"判断放行是不够的。
    # [EN] -- ⑥ the "new line" given by restatement **may also be an old line** -> it still must go on
    # [EN] screen --
    # [EN] Found by running the control probe: when the line pool is small, the stub goes around and comes
    # [EN] back to a line it has already said,
    # [EN] so beat 6 goes blank again -- judging allowance only by "new line == original line" is not
    # [EN] enough.
    w12 = make_world()
    loop12 = make_loop(w12)

    def fn12(name, i, ctx):
        if name != '柳娘':
            return act('wait')
        if '你刚说过' in ctx:
            return say('柳娘', '漏刻只许校，不许改。')     # 想清楚之后给的**也是老话**
            # [EN] After thinking it through, what it gives **is also an old line**
        return say('柳娘', '水不会说谎，人会。' if i != 1 else '漏刻只许校，不许改。')

    shots: list[list[str]] = []
    calls12, restore12 = patch_decide(fn12)
    try:
        for t in (1, 2, 3):
            SCREEN.clear()
            asyncio.run(loop12._tick(t))
            shots.append(list(SCREEN))
            # ★ 2026-10-26：同上 —— 下一拍要"非说不可"，得先有人追问过。
            # [EN] ★ Same as above: the next beat needs a real follow-up question on the ledger.
            w12.recent_lines.append({'kind': 'speak', 'who': '主角',
                                     'text': '你说什么？再说一遍。'})
    finally:
        restore12()
    ok('D12 ★★ 重说给出的"新句"若也是一句老话 → 照样上屏（不能又变空白）',
       bool(shots[2]) and any('漏刻只许校' in x for x in shots[2]),
       ' | '.join(shots[2])[:100] or '（第三拍空白）')


# ══════════════════════════════════════════════════════════════════
#  F —— 内部盘算不落痕（`decide()` 是只读的）
# [EN] F -- internal deliberation leaves no trace (`decide()` is read-only)
# ══════════════════════════════════════════════════════════════════
def test_pure_decide() -> None:
    """重说靠的是 `decide()` 再跑一遍 —— 它必须是**只读**的。

    这条判据的价值：以后谁往 `decide()` 里加了一句"顺手把这次决策记进记忆"
    或"顺手推一条屏幕"，重说就会变成"人物先当众说了一遍再改口" ——
    正是用户明确不要的那件事。所以这里用**真实 source 比对**钉住它不写库。
    
        English:
    Repeating relies on running `decide()` again -- it must be **read-only**.
        The value of this criterion: in the future, if anyone adds to `decide()` a line like "conveniently record this decision into memory"
        or "conveniently push a screen", then repeating will become "the character first says it publicly and then changes their words" --
        exactly the thing the user explicitly does not want. So here **real source comparison** is used to pin down that it does not write to the database.
    """
    import ast
    src = (APP_DIR / 'agent' / 'core.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    fn = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == 'Agent':
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name == 'decide':
                    fn = sub
                    break
    ok('F1 找得到 `Agent.decide`（判据不是空转）', fn is not None, '')
    if fn is None:
        return
    seg = ast.get_source_segment(src, fn) or ''
    banned = ['.add_memory(', '.add_event(', 'note_line(', '_push_narrative(',
              'save(', 'write_text(']
    hit = [b for b in banned if b in seg]
    ok('F2 ★★ `decide()` 里没有任何写操作 —— 所以"重说"不会留下第一遍的痕迹',
       not hit, f'发现：{hit}' if hit else f'{len(seg)} 字符，干净')


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_rep_'))
    print('═' * 62)
    print('  验证：说了一样的话 → 先问是不是非说不可（2026-10-07）')
    print('═' * 62)
    try:
        print('\n【A】判据要窄（不按长度猜）')
        test_narrow_judge()
        print('\n【B】护栏开的两个口子')
        test_guard_doors()
        print('\n【C】`_review_repeat` 的几种结局')
        test_review_outcomes()
        print('\n【D】端到端（真跑两拍）')
        test_end_to_end()
        print('\n【F】内部盘算不落痕')
        test_pure_decide()
    except Exception:                                            # noqa: BLE001
        traceback.print_exc()
        report['fatal'] = traceback.format_exc()
    finally:
        safe_rmtree(tmp)

    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'dialogue_repeat_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  重复台词验证：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
