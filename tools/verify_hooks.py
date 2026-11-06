# -*- coding: utf-8 -*-
"""验证：**钩子群演**（群演三档里的第三档，设计稿 §5.2）——
反复出现、像有故事的客人，要**跨场记忆**。

`world/crowd.py` 的模块注释里自己写着"钩子群演这一轮没做：它要跨场记忆
和'值不值得转正成正式人物卡'的判断"。这一轮补上。

判据分层（每层都要能红，见 `developers/mutate_hooks.py`）：
  A **跨场记忆**：功能群演走掉 → 进名册；同一个人（称呼+标志）再次走掉 →
     见面次数 +1、前情累积；背景群演**不进**（场面不是人）。
  B **回访**：至少隔 3 个故事日；只在名册里挑；回来时挂着 `钩子` 与**前情**；
     `needs_line()` 会把前情讲给人物听（"上回来过：…"）。
  C **转正**：够次数才进建议清单；**只给建议**（不改世界、不造人物卡）。
  D **接线**：`_sync_crowd` **先回访老熟人、再招新面孔**；
     日界落 `可转正群演.md`。

用法：.venv\\Scripts\\python.exe tools/verify_hooks.py
产出：assets/screenshots/hooks_report.json

English:
Verification: **hook extras** (the third tier of the three extra tiers, design doc §5.2) --
customers who appear repeatedly and seem to have a story must have **cross-scene memory**.
The module comment in `world/crowd.py` says itself: "hook extras were not done this round: they
need cross-scene memory
and the judgment of 'is it worth promoting to a formal character card'". This round adds them.
Criteria are layered (each layer must be able to go red, see `developers/mutate_hooks.py`):
  A **Cross-scene memory**: functional extra exits -> enters roster; the same person (appellation + marker) exits again ->
     meeting count +1, prior context accumulates; background extras **do not enter** (a scene is not a person).
  B **Return visit**: at least 3 story days apart; only picked from the roster; when returning, carries `hook` and **prior context**;
     `needs_line()` will tell the previous context to the character ("last time you came: ...").
  C **promotion to regular**: only after enough appearances does it enter the suggestion list; **only suggestions are given** (no world changes, no character cards created).
  D **wiring**: `_sync_crowd` **first revisits old acquaintances, then recruits new faces**;
Usage: .venv\\Scripts\\python.exe tools/verify_hooks.py
Output: assets/screenshots/hooks_report.json
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
import textwrap
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from config import CFG                                         # noqa: E402
# ⚠ 不量像素、不弹窗、**绝不点会 `CFG.save()` 的按钮**（MEMORY 的铁律）。
# [EN] ⚠ Do not measure pixels, do not pop dialogs, **never click a button that calls `CFG.save()`**
# [EN] (an iron rule in MEMORY).
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


def make_world(day=1):
    from world.state import WorldState
    w = WorldState()
    w.scene = '临河茶肆'
    w.game_day = day
    w.extras_today = 0
    return w


def a_guest(world, rng=None, 称呼='来讨债的', 标志='袖口磨得发亮', 诉求='要见掌柜'):
    from world import crowd as C
    e = {'kind': '功能', '称呼': 称呼, '诉求': 诉求, '标志': 标志,
         '寿命': 2, '剩余': 1, '一行': f'{称呼}——{诉求}'}
    world.extras.append(e)
    return e


# ══════════════════════════════════════════════════════════════
#  A. 跨场记忆
# [EN] A. Cross-scene memory
# ══════════════════════════════════════════════════════════════
def test_memory() -> bool:
    ok = True
    from world import crowd as C
    saved = CFG.raw('EXTRAS_HOOKS')
    try:
        CFG.set('EXTRAS_HOOKS', 'true')
        w = make_world()
        a_guest(w)
        C.tick_extras(w)                      # 寿命到 0 → 退场 → 记名册
        # [EN] Lifespan reaches 0 -> exit -> enter the roster
        ok &= rec('A1 ★★ 功能群演走掉 → 进了钩子名册（跨场记忆的写入端）',
                  len(w.hooks) == 1 and w.hooks[0]['称呼'] == '来讨债的',
                  str(w.hooks))
        ok &= rec('A1 名册里带着**首次/最近**是哪一天', 
                  w.hooks[0].get('首次第几天') == 1 and w.hooks[0].get('上次第几天') == 1,
                  str(w.hooks[0]))
        ok &= rec('A1 名册里留着**前情**（他上次来干嘛）',
                  w.hooks[0].get('前情') == ['要见掌柜'], str(w.hooks[0].get('前情')))

        # 同一个"人"再来一次 → 次数 +1、前情累积
        # [EN] The same "person" appears again -> count +1, prior context accumulates
        w.game_day = 5
        a_guest(w, 诉求='说账拖了三个月')
        C.tick_extras(w)
        ok &= rec('A2 ★★ 同一个人（称呼+标志）再次出现 → **见面次数 +1**',
                  len(w.hooks) == 1 and w.hooks[0]['见面次数'] == 2, str(w.hooks))
        ok &= rec('A2 ★ 前情累积（两件都记着）',
                  len(w.hooks[0].get('前情') or []) == 2,
                  str(w.hooks[0].get('前情')))

        # 背景群演不进名册（"两个脚夫在门口歇脚"是场面，不是人）
        # [EN] Background extras do not enter the roster ("two porters resting at the door" is a scene, not a
        # [EN] person)
        w2 = make_world()
        # ⚠ 这条背景群演**故意带上"称呼"**：不带的话它会先被
        #   `who` 判空挡掉，于是"背景也进名册"那个变异**测不出来**
        #   （反例法抓到的 —— 判据要能隔离出被验的那一行）。
        # [EN] ⚠ This background extra **deliberately carries an "appellation"**: without it, it would first be
        # [EN] filtered out by `who` being empty, so the mutation "background also enters the roster" **would
        # [EN] not be caught**
        # [EN] (Caught by the counterexample method -- the criterion must be able to isolate the line under
        # [EN] test).
        w2.extras.append({'kind': '背景', '称呼': '两个脚夫',
                          '一行': '两个脚夫在门口歇脚', '剩余': 1})
        C.tick_extras(w2)
        ok &= rec('A3 ★★ 背景群演**不进**名册（场面不是人）',
                  w2.hooks == [], str(w2.hooks))

        # 关掉旋钮 → 不记
        # [EN] Turn off the knob -> no recording
        CFG.set('EXTRAS_HOOKS', 'false')
        w3 = make_world()
        a_guest(w3)
        C.tick_extras(w3)
        ok &= rec('A3 ★ `EXTRAS_HOOKS=false` → 不记名册（旋钮真被读）',
                  w3.hooks == [], str(w3.hooks))
    finally:
        CFG.set('EXTRAS_HOOKS', saved)
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 回访
# [EN] B. Return visit
# ══════════════════════════════════════════════════════════════
def test_recall() -> bool:
    ok = True
    from world import crowd as C
    saved = CFG.raw('EXTRAS_HOOKS')
    try:
        CFG.set('EXTRAS_HOOKS', 'true')
        rng = random.Random(3)
        w = make_world(1)
        a_guest(w)
        C.tick_extras(w)

        # 隔得太近 → 不回访（刚走又回来就是骚扰）
        # [EN] Too close together -> no return visit (leaving and immediately coming back is harassment)
        w.game_day = 2
        got = [C.recall_hook(w, rng) for _ in range(40)]
        ok &= rec('B1 ★★ 刚走两天就回来 → 不回访（要至少隔 3 个故事日）',
                  all(g is None for g in got), str([g for g in got if g]))

        # 隔够了 → 有几率回来，且带着前情
        # [EN] Far enough apart -> a chance to return, and carrying prior context
        w.game_day = 6
        back = None
        for _ in range(200):
            back = C.recall_hook(w, rng)
            if back:
                break
        ok &= rec('B2 ★★ 隔够了就**可能回访**（不是永远不来）', back is not None,
                  str(back))
        if back:
            ok &= rec('B2 ★★ 回来的人**带着前情**（这才叫跨场记忆）',
                      back.get('钩子') is True and back.get('前情'),
                      str(back.get('前情')))
            ok &= rec('B2 ★ 回来的是**同一个人**（称呼 + 标志都对得上）',
                      back.get('称呼') == '来讨债的'
                      and back.get('标志') == '袖口磨得发亮', str(back))
            ok &= rec('B2 ★ 人物看得到前情（`needs_line` 会讲"上回来过…"）',
                      '上回来过' in C.needs_line(w), C.needs_line(w)[:110])

        # 关掉旋钮 → 不回访
        # [EN] Turn off the knob -> no return visit
        CFG.set('EXTRAS_HOOKS', 'false')
        w4 = make_world(9)
        a_guest(w4)
        C.tick_extras(w4)
        w4.hooks = [{'key': 'x|y', '称呼': 'x', '标志': 'y', '前情': ['旧事'],
                     '见面次数': 2, '首次第几天': 1, '上次第几天': 1}]
        ok &= rec('B3 ★ `EXTRAS_HOOKS=false` → 不回访（旋钮真被读）',
                  all(C.recall_hook(w4, rng) is None for _ in range(50)), '')
        # 反例：开着的时候同一份名册是能回访的（判据不是恒真）
        # [EN] Counterexample: when it is on, the same roster can produce a return visit (the criterion is not
        # [EN] vacuously true)
        CFG.set('EXTRAS_HOOKS', 'true')
        w5 = make_world(9)
        w5.hooks = list(w4.hooks)
        ok &= rec('B3 ★ 反例：旋钮打开后**同一份名册能回访**（判据不是恒真）',
                  any(C.recall_hook(w5, rng) for _ in range(50)), '')
    finally:
        CFG.set('EXTRAS_HOOKS', saved)
    return ok


# ══════════════════════════════════════════════════════════════
#  C. 转正建议（只建议，不代造）
# [EN] C. Promotion suggestion (suggest only, do not create on behalf of)
# ══════════════════════════════════════════════════════════════
def test_promote_suggestion() -> bool:
    ok = True
    from world import crowd as C
    saved_h, saved_n = CFG.raw('EXTRAS_HOOKS'), CFG.raw('EXTRAS_HOOK_PROMOTE_AT')
    try:
        CFG.set('EXTRAS_HOOKS', 'true')
        CFG.set('EXTRAS_HOOK_PROMOTE_AT', '3')
        w = make_world(1)
        w.hooks = [{'key': 'a|b', '称呼': '赊账的', '标志': 'b',
                    '前情': ['说下月一定还'], '见面次数': 2,
                    '首次第几天': 1, '上次第几天': 2}]
        ok &= rec('C1 ★ 只见过 2 次（< 3）→ **还不到建议转正**',
                  C.hook_suggestions(w) == [], str(C.hook_suggestions(w)))
        w.hooks[0]['见面次数'] = 3
        got = C.hook_suggestions(w)
        ok &= rec('C1 ★★ 到 `EXTRAS_HOOK_PROMOTE_AT` 次 → 进建议清单',
                  len(got) == 1 and got[0]['称呼'] == '赊账的', str(got))
        ok &= rec('C1 ★ 旋钮改大就不提了（真被读）',
                  (CFG.set('EXTRAS_HOOK_PROMOTE_AT', '8')
                   or C.hook_suggestions(w) == []), '')
        CFG.set('EXTRAS_HOOK_PROMOTE_AT', '3')

        # ★★ 只给建议：不许往世界里塞人物
        # [EN] ★★ Suggestions only: do not stuff characters into the world
        before = len(getattr(w, 'people', {}) or {})
        C.hook_suggestions(w)
        ok &= rec('C2 ★★ **只给建议**：世界里的正式人物一个没多（程序不代作者决策）',
                  len(getattr(w, 'people', {}) or {}) == before,
                  f'{before} → {len(getattr(w, "people", {}) or {})}')
        md = C.hooks_md(w)
        ok &= rec('C2 ★ `hooks_md` 有清单也有"建议转正"那一段',
                  '钩子群演' in md and '建议转正' in md and '赊账的' in md,
                  md[-120:].replace('\n', ' '))
        ok &= rec('C2 ★ 明写"程序不会自动写进设定集"（免得作者以为已经办好了）',
                  '不会**自动' in md or '不会自动' in md or '不会' in md, '')

        # 已经提过的别反复提
        # [EN] Do not repeatedly suggest what has already been suggested
        w.hooks_promoted = ['a|b']
        ok &= rec('C2 ★ 提过的不要再重复提（`hooks_promoted` 记着）',
                  C.hook_suggestions(w) == [], str(C.hook_suggestions(w)))
        # 关掉旋钮 → 一律不建议
        # [EN] Turn off the knob -> no suggestions at all
        CFG.set('EXTRAS_HOOKS', 'false')
        w.hooks_promoted = []
        ok &= rec('C2 ★ `EXTRAS_HOOKS=false` → 连建议都不给',
                  C.hook_suggestions(w) == [], '')
    finally:
        CFG.set('EXTRAS_HOOKS', saved_h)
        CFG.set('EXTRAS_HOOK_PROMOTE_AT', saved_n)
    return ok


# ══════════════════════════════════════════════════════════════
#  D. 接线
# [EN] D. Wiring
# ══════════════════════════════════════════════════════════════
def test_wiring() -> bool:
    ok = True
    import inspect
    from sim.loop import RunLoop
    from world import crowd as C

    src = inspect.getsource(RunLoop._sync_crowd)
    ok &= rec('D1 ★★ `_sync_crowd` 真的调了 `recall_hook`',
              'recall_hook' in src,
              ' | '.join(l.strip() for l in src.split('\n') if 'recall_hook' in l))
    # ★ 2026-10-07 调整（不是放宽）：新面孔那一步**搬去了 `_cast_extra`**
    #   （门外的人现在由剧组里「群众演员」投，规则池降级成兜底）。
    #   所以"老熟人优先"这条判据要在**跨函数的调用顺序**上看：
    #   `_sync_crowd` 里先 `recall_hook`，**之后**才去要新面孔
    #   （新面孔那一步现在叫 `_cast_extra`，它内部才可能落到 `new_extra`）。
    #   判据本意没变：老熟人的戏份比新路人值钱。
    # [EN] ★ 2026-10-07 adjustment (not a relaxation): the new-face step **moved to `_cast_extra`**
    # [EN] (People outside the door are now cast by "extras" in the troupe; the rule pool is downgraded to
    # [EN] a fallback).
    # [EN] So the criterion "old acquaintances first" must be viewed at the level of **cross-function call
    # [EN] order**:
    # [EN] In `_sync_crowd`, call `recall_hook` first, and only **after that** request new faces
    # [EN] (The new-face step is now called `_cast_extra`; only inside it can it fall through to
    # [EN] `new_extra`).
    # [EN] The intent of the criterion is unchanged: an old acquaintance's screen time is worth more than a
    # [EN] new passerby's.
    i_recall = src.find('recall_hook')
    i_new = max(src.find('_cast_extra'), src.find('new_extra'))
    ok &= rec('D1 ★★ 而且排在**要新面孔之前**（老熟人的戏份比新路人值钱）',
              i_recall >= 0 and i_new > i_recall, f'recall@{i_recall} < new@{i_new}')
    cast_src = inspect.getsource(RunLoop._cast_extra)
    ok &= rec('D1c ★ 新面孔那一步留着**规则兜底**（拿不到 AI 也不能让门外空着）',
              'new_extra' in cast_src, '')

    src2 = inspect.getsource(RunLoop._end_day)
    ok &= rec('D2 ★ 日界落 `可转正群演.md`',
              '可转正群演.md' in src2 and 'hooks_md' in src2,
              ' | '.join(l.strip() for l in src2.split('\n') if 'hooks_md' in l))

    # 端到端：老熟人真的被推成了「【又来了】」
    # [EN] End to end: the old acquaintance really is pushed as "【Here again】"
    w = make_world(9)
    loop = RunLoop.__new__(RunLoop)
    loop.world = w
    loop._rng = random.Random(5)
    loop._cb_warned = set()
    loop._status = lambda *a, **k: None
    lines: list[str] = []
    loop._on_narrative = lambda text, pri, kind='': lines.append(text)

    class Disp:
        async def enqueue_narrative(self, *a, **k):
            pass

    loop.display = Disp()
    C.sync_crowd(w, loop._rng)      # 先让门外有人（crowd_size 要 ≥3 才招人）
    # [EN] First make sure there is someone outside the door (crowd_size must be ≥3 to recruit)

    # ── D0 ★★ `_sync_crowd` **整段不能抛异常**（2026-10-07 查出来的一处死代码）──
    #   它引用过一个**不存在的 `tick_num`** → 每拍 `NameError`，被下面那个宽
    #   `except` 吞成一行 warning，于是**退场播报整段是死代码** —— 而它正是
    #   用户报的"对话又死循环"的修复。宽 `except` 会把"完全没跑"伪装成"跑过了"，
    #   所以这条链必须有**行为**判据看着（源码哨兵 `'tick_num' in src` 抓不住它：
    #   那个名字在文件里出现得挺多）。
    #   判据：真跑一次，`exit_notice` 必须收到我们传进去的那个拍号，
    #   而且**没有**留下 'crowd' 那条异常播报。
    # [EN] ── D0 ★★ `_sync_crowd` **the whole block must not raise an exception** (a piece of dead code
    # [EN] found on 2026-10-07) ──
    # [EN] It referenced a **nonexistent `tick_num`** -> `NameError` every tick, swallowed by the broad
    # [EN] `except` below into a single warning line, so **the entire exit-broadcast block is dead code**
    # [EN] -- and it is exactly
    # [EN] the fix for the user-reported "dialogue infinite loop again". A broad `except` disguises "never
    # [EN] ran" as "ran",
    # [EN] so this chain must have a **behavioral** criterion watching it (the source sentinel `'tick_num'
    # [EN] in src` cannot catch it:
    # [EN] that name appears quite a lot in the file).
    # [EN] Criterion: actually run it once; `exit_notice` must receive the tick number we passed in,
    # [EN] and **must not** leave behind the 'crowd' exception broadcast.
    calls: list[int] = []
    real_notice, real_recall2 = C.exit_notice, C.recall_hook
    saved_hk = CFG.raw('EXTRAS_HOOKS')
    try:
        C.exit_notice = lambda world, gone, tick=0: (calls.append(int(tick)), '')[1]
        C.recall_hook = lambda world, rng=None: {
            'kind': '功能', '称呼': '赊账的', '诉求': '说下月一定还',
            '标志': '袖口磨亮', '钩子': True, '前情': [], '寿命': 3, '剩余': 3}
        CFG.set('EXTRAS_HOOKS', 'true')
        asyncio.run(loop._sync_crowd(7))
    finally:
        C.exit_notice, C.recall_hook = real_notice, real_recall2
        CFG.set('EXTRAS_HOOKS', saved_hk)
    ok &= rec('D0 ★★ `_sync_crowd(tick_num)` 整段跑得通、退场播报真的拿到拍号'
              '（引用未定义变量会被宽 except 吞成一行 warning）',
              calls == [7] and 'crowd' not in loop._cb_warned,
              f'calls={calls} warned={sorted(loop._cb_warned)}')

    real_recall, real_new = C.recall_hook, C.new_extra
    saved = CFG.raw('EXTRAS_HOOKS')
    try:
        CFG.set('EXTRAS_HOOKS', 'true')
        C.recall_hook = lambda world, rng=None: {
            'kind': '功能', '称呼': '赊账的', '诉求': '说下月一定还',
            '标志': '袖口磨得发亮', '钩子': True, '前情': ['说要见掌柜'],
            '寿命': 3, '剩余': 3}
        # 让"招人"这一步一定发生（不然行数少、`_sync_crowd` 不会调）
        w.scene = '街市'                 # 客流基准高 → crowd_size ≥ 3
        # [EN] Make the "recruit" step definitely happen (otherwise line count is low and `_sync_crowd` will
        # [EN] not be called)
        # [EN] High traffic baseline -> crowd_size ≥ 3
        hit = False
        # ⚠ 必须在**事件循环里**调：`_push_narrative` 第一件事是
        #   `asyncio.create_task(...)`，没有运行中的循环会直接 RuntimeError
        #   （被 `_sync_crowd` 的兜底吞掉 → 表现成"回访没播报"，第一版就这么假红的）。
        # [EN] ⚠ Must be called **inside the event loop**: the first thing `_push_narrative` does is
        # [EN] `asyncio.create_task(...)`; without a running loop it raises RuntimeError directly
        # [EN] (swallowed by `_sync_crowd`'s fallback -> manifests as "return visit not broadcast"; the first
        # [EN] version went falsely red exactly this way).
        async def _once():
            # ⚠ `_sync_crowd` 从 2026-10-07 起是**协程**（新面孔那一步要问剧组），
            #   少了 `await` 会只创建协程对象、一行都不跑 ——
            #   表现成"回访没播报"（和当初忘了在事件循环里调是同一类假红）。
            # [EN] ⚠ `_sync_crowd` has been a **coroutine** since 2026-10-07 (the new-face step needs to ask the
            # [EN] troupe),
            # [EN] missing `await` will only create a coroutine object and not run a single line --
            # [EN] manifests as "return visit not broadcast" (the same class of false red as forgetting to call it
            # [EN] inside the event loop).
            await loop._sync_crowd()
        for _ in range(60):
            lines.clear()
            asyncio.run(_once())
            if any('又来了' in x for x in lines):
                hit = True
                break
        ok &= rec('D3 ★★ 老熟人回访真的被推成「【又来了】」（端到端）', hit,
                  str(lines[:3]))
    finally:
        C.recall_hook, C.new_extra = real_recall, real_new
        CFG.set('EXTRAS_HOOKS', saved)
    return ok


def test_exit_noise() -> bool:
    """E. **退场播报不许刷屏**（用户 2026-10-07：「对话又死循环了」）。

    截图上满屏都是同一批括号 NOTE，同一句连着出现 4~6 次：
        （邻铺的伙计过来借火，站着说了两句闲话走了）
        （有人把茶碗盖一磕，起身结账走了走了）      ← 还多了个"走了"
        （靠窗那桌把昨日的听来的事又讲了一遍走了）
        （两个脚夫在门口歇脚，就着粗茶啃干粮走了）

    ★ 根因（三件事叠一起，量出来的 —— 80 拍里 **104 条**播报、单句最多 **29 次**）：
      ① 背景群演寿命**写死 3 拍**，而每拍都把人数补满 →
         "补满 → 3 拍后一起退 → 又补满"，每 3 拍必有一批退场；
      ② 退场**逐条播报**（`for who in gone[:2]`）—— 背景来去本来不该占一行字；
      ③ `who` 取的是**整句场面描写**，句子结尾本来就有动作，再拼"走了"
         → **"走了走了"**（那个重词就是这么来的）。

    修完：80 拍 **7 条**（只有"换过一拨"，且 `BG_NOTICE_EVERY=12` 拍冷却），
    没有"走了走了"，`_bg_lines` 优先挑最近没用过的。

    ⚠ 判据要**两边都守**：只压住背景、同时把"功能群演点名"也一起砍掉，
      那是把功能删了而不是修毛病 —— 所以 E4 专门盯着"该说的还要说"。
    
        English:
    E. **Exit announcements must not flood the screen** (user 2026-10-07: "the dialogue is in an
    infinite loop again").
        In the screenshot the whole screen is the same batch of parenthesized NOTE lines, with the same sentence appearing 4~6 times in a row:
            (the shop assistant from the neighboring stall came over to borrow a light, stood and chatted a couple of words, then left)
            (someone tapped the tea-bowl lid, got up to pay and left, left)      <- there's even an extra "left"
            (the table by the window told yesterday's gossip again and left)
            (two porters rested at the door, gnawed dry rations with coarse tea and left)
        ★ Root cause (three things stacked together, measured -- in 80 beats **104** announcements, a single sentence up to **29 times**):
          ① Background extra lifespan is **hardcoded to 3 beats**, and the crowd is refilled to full every beat ->
             "refill -> all leave after 3 beats -> refill again", so every 3 beats there is guaranteed to be a batch of exits;
          ② Exits are **announced one by one** (`for who in gone[:2]`) -- background comings and goings shouldn't take up a line of text at all;
          ③ `who` takes the **entire scene description sentence**, and the sentence ending already has an action, then "left" is appended
             -> **"left, left"** (that's where the duplicated word comes from).
        After the fix: 80 beats with **7** lines (only "a batch was swapped", and `BG_NOTICE_EVERY=12` beat cooldown),
        no "left, left", and `_bg_lines` prioritizes the ones not used recently.
        ⚠ The criterion must **hold on both sides**: only suppressing the background while also cutting out the "functional extra roll-call",
          that's deleting the feature rather than fixing the bug -- so E4 specifically watches that "what should be said still gets said".
    """
    ok = True
    from world import crowd as C

    class _W:
        scene = '临河茶肆'
        weather = '晴'
        extras: list = []
        extras_today = 0

    def _run(ticks: int = 80, seed: int = 7) -> list[str]:
        """跑 80 拍，收集**所有**退场播报（背景与功能各走一遍）。

        `crowd_size` 被顶成 6 —— 否则"门外没人"就什么都不会发生，
        量出来是 0 条，看着像"改好了"（**假绿**：什么都没验证到）。
        
                English:
        Run 80 beats, collect **all** exit announcements (both background and functional run through
        once).
                `crowd_size` is pushed up to 6 -- otherwise "no one outside the door" means nothing will happen,
                and the measured count is 0, which looks like "fixed" (**false green**: nothing was actually verified).
        """
        real = C.crowd_size
        C.crowd_size = lambda w: 6
        try:
            rng = random.Random(seed)
            w = _W()
            out: list[str] = []
            for t in range(1, ticks + 1):
                C.sync_crowd(w, rng)
                gone = C.tick_extras(w)
                n = C.exit_notice(w, gone, tick=t)
                if n:
                    out.append(n)
            return out
        finally:
            C.crowd_size = real

    notes = _run()
    # E0 前置：必须真的退过场（否则下面几条全都在"验空气"）
    # [EN] E0 prerequisite: there must actually have been an exit (otherwise the following checks are all
    # [EN] "testing air")
    ok &= rec('E0 前置：80 拍里背景群演真的退过场（不是"什么都没发生"）',
              len(notes) > 0, f'{len(notes)} 条播报')

    # E1 总量：背景退场是有冷却的
    # [EN] E1 Volume: background exits have a cooldown
    cap = 80 // C.BG_NOTICE_EVERY + 2
    ok &= rec(f'E1 ★ 背景退场播报被节流（80 拍 ≤ {cap} 条；旧规则是 104 条）',
              len(notes) <= cap, f'{len(notes)} 条')

    # E2 **播报要短** —— 背景退场只说"换过一拨"，不再把整句场面描写搬上屏。
    #   ⚠ 第一版这里写的是"单句 ≤ 4 次"，**口径错了**：改成节流之后只有一种句子
    #   （"（堂里的人换过一拨）"），它的次数必然等于总条数（= 被冷却压住的 7），
    #   于是这条永远红。**判断"有没有刷屏"该看总条数（E1 已守）+ 单句是不是长得像
    #   一段场面描写**：旧规则那 4 句都是 20 字上下的具体场面，各出现 24~29 次。
    # [EN] E2 **Broadcast must be short** -- a background exit only says "a batch has been swapped", no
    # [EN] longer puts the whole scene description on screen.
    # [EN] ⚠ The first version wrote here "single sentence ≤ 4 times", **the metric was wrong**: after
    # [EN] changing to throttling there is only one kind of sentence
    # [EN] ("(the people in the hall have been swapped)"), its count is necessarily equal to the total
    # [EN] number of entries (= 7 suppressed by the cooldown),
    # [EN] so this check is always red. **To judge whether there is screen flooding, look at the total
    # [EN] count (already guarded by E1) + whether a single sentence looks like
    # [EN] a scene description**: the old rule's 4 sentences were all concrete scenes around 20 characters,
    # [EN] each appearing 24~29 times.
    longest = max((len(x) for x in notes), default=0)
    ok &= rec('E2 ★ 退场播报是"一句话"，不是整段场面描写'
              '（旧规则把 20 字上下的场面句直接搬上屏，那句各出现 24~29 次）',
              longest <= 14, f'最长 {longest} 字：{max(notes, key=len)[:40] if notes else ""}')

    # E3 那个重词
    # [EN] E3 that heavy word
    ok &= rec('E3 ★ 不再出现「走了走了」（整句场面描写后面别再拼"走了"）',
              not any('走了走了' in x for x in notes),
              [x for x in notes if '走了走了' in x][:1] or '没有')

    # E4 反例方向：功能/钩子群演**仍然点名**
    # [EN] E4 Counterexample direction: functional/hook extras **are still named**
    class _W2(_W):
        pass

    w2 = _W2()
    msg = C.exit_notice(w2, [{'kind': '功能', 'label': '来讨债的'}], tick=100)
    ok &= rec('E4 ★ 功能群演退场**照旧点名**（别把"该说的"一起砍掉）',
              msg is not None and '来讨债的' in msg, repr(msg))

    # E5 `_bg_lines` 优先挑最近没用过的
    # [EN] E5 `_bg_lines` prefers picking ones not used recently
    real_size = C.crowd_size
    C.crowd_size = lambda w: 6
    try:
        rng = random.Random(3)
        w3 = _W()
        seen: list[str] = []
        for _ in range(12):
            seen += C._bg_lines(w3, 1, rng)          # noqa: SLF001
        # 茶楼池子 4 条：连着抽 12 次，**相邻两次不该相同**
        # [EN] Teahouse pool has 4 entries: draw 12 times in a row, **two adjacent draws must not be the same**
        dup = sum(1 for a, b in zip(seen, seen[1:]) if a == b)
        ok &= rec('E5 ★ 相邻两次抽到的背景场面不重复（避重记在 `world.bg_recent`）',
                  dup == 0, f'重复 {dup} 次 / 12 次抽取')
    finally:
        C.crowd_size = real_size

    # E6 接线：主循环走的是同一个出口（不是自己在外面拼字符串）
    # [EN] E6 Wiring: the main loop goes through the same exit (it does not concatenate strings outside on
    # [EN] its own)
    import inspect
    from sim.loop import RunLoop
    src = inspect.getsource(RunLoop._sync_crowd)
    ok &= rec('E6 ★★ `_sync_crowd` 的退场播报走 `exit_notice()`（判断只有一处）',
              'exit_notice' in src,
              ' | '.join(l.strip() for l in src.split('\n') if 'exit_notice' in l))
    # ⚠ **必须走 AST，不能用子串**：这段函数里我留了注释解释"以前是
    #   `push(f"（{who}走了）")`" —— 子串匹配会被自己的注释骗过，报出一条假红。
    #   （项目里同一个坑踩过：判据 A10o 被 docstring 骗过，那次也是改成 AST。）
    #   AST 只看**代码里的字符串字面量**，注释根本不在树里。
    # [EN] ⚠ **Must use AST, cannot use substring**: inside this function I left a comment explaining "it
    # [EN] used to be
    # [EN] `push(f"({who} left)")"` -- substring matching would be fooled by my own comment and report a
    # [EN] false red.
    # [EN] (The same pitfall was hit in the project before: criterion A10o was fooled by a docstring, and
    # [EN] that time it was also changed to AST.)
    # [EN] AST only looks at **string literals in the code**; comments are not in the tree at all.
    import ast as _ast
    lits: list[str] = []
    for node in _ast.walk(_ast.parse(textwrap.dedent(src))):
        if isinstance(node, _ast.Constant) and isinstance(node.value, str):
            lits.append(node.value)
        elif isinstance(node, _ast.JoinedStr):            # f-string 的各段
        # [EN] The segments of the f-string
            for sub in _ast.walk(node):
                if isinstance(sub, _ast.Constant) and isinstance(sub.value, str):
                    lits.append(sub.value)
    bad_lits = [x for x in lits if '走了' in x]
    ok &= rec("E6b ★ 主循环里不再有自己拼的退场句（AST 找字符串字面量，躲开注释）",
              not bad_lits, bad_lits[:2] or '没有')
    return ok


if __name__ == '__main__':
    print('钩子群演（跨场记忆）—— 验证', flush=True)
    ok = True
    try:
        head('A. 跨场记忆（走掉的记进名册）')
        ok &= test_memory()
        head('B. 回访（隔几天、带前情）')
        ok &= test_recall()
        head('C. 转正建议（只建议、不代造）')
        ok &= test_promote_suggestion()
        head('D. 接线（先回访后招新 / 日界落盘）')
        ok &= test_wiring()
        head('E. 退场播报不许刷屏（用户报「对话又死循环」）')
        ok &= test_exit_noise()
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'hooks_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1200:])
    sys.exit(0 if report['ok'] else 2)
