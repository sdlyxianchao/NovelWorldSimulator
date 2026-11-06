# -*- coding: utf-8 -*-
"""验证：**上下文分层裁剪**（设计稿 §2.4）—— `MAX_CONTEXT_TOKENS` /
`CONTEXT_CACHE` / `SUMMARIZE_MEMORY_AFTER`。

用户 2026-10-06：「继续全做完」。这三项以前**一个都没人读** ——
上下文是把所有东西一股脑拼起来的：跑到第十天，一个人物的 prompt 里光记忆
与对话就有几千 token，而且**最先被挤掉的恰好是世界观和人格**（模型开始出戏）。

判据分层（每层都要能红，见 `developers/mutate_context.py`）：
  A **分层**：固定前缀**永不裁**；动态层优先裁；裁**从尾部往前**；
     记忆块尾部 = 最不重要、事件块尾部 = 最旧（方向反了会删掉刚说的话）。
  B **预算**：没超预算**一个字都不裁**；超了才裁；裁到底还超要 `over=True`。
  C **接线**：`Agent.decide()` 的 prompt 真的受 `MAX_CONTEXT_TOKENS` 约束，
     而且**固定前缀（人格 / 世界观 / 顶级规则）在裁剪后仍在**。
  D **缓存**：`CONTEXT_CACHE=false` 时 `world_prefix()` 真的不再用缓存。
  E **记忆压缩**：没到阈值**一次 LLM 都不调**；超了就折成一条、**先写后删**；
     拿不到模型结果 → **退回原文拼接**（绝不丢内容）；`=0` 关得掉；
     日界真的会跑（`_end_day` → `_compact_memories`）。

用法：.venv\\Scripts\\python.exe tools/verify_context.py
产出：assets/screenshots/context_report.json

English:
Verification: **layered context trimming** (design doc §2.4) —— `MAX_CONTEXT_TOKENS` /
`CONTEXT_CACHE` / `SUMMARIZE_MEMORY_AFTER`.
User 2026-10-06: "keep going and finish it all". Previously **not one of these three was read by
anyone** ——
the context was everything concatenated all together: by day ten, a character's prompt already
had thousands of tokens of just memory
and dialogue, and **what got squeezed out first happened to be the worldview and personality**
(the model starts breaking character).
Layered criteria (each layer must be able to go red, see `developers/mutate_context.py`):
  A **Layering**: the fixed prefix is **never trimmed**; the dynamic layer is trimmed first; trimming goes **from the tail backward**;
     the tail of the memory block = least important, the tail of the event block = oldest (reverse the direction and it deletes what was just said).
  B **Budget**: if under budget, **not a single character is trimmed**; only over budget does it trim; if still over after trimming to the end, it must be `over=True`.
  C **Wiring**: `Agent.decide()`'s prompt is actually constrained by `MAX_CONTEXT_TOKENS`,
     and **the fixed prefix (personality / worldview / top-level rules) is still there after trimming**.
  D **Cache**: when `CONTEXT_CACHE=false`, `world_prefix()` really no longer uses the cache.
  E **Memory compression**: if the threshold isn't reached, **not a single LLM call is made**; if exceeded, it folds into one entry, **write first then delete**;
     if the model result can't be obtained → **fall back to concatenating the original text** (never lose content); `=0` turns it off;
     the day boundary really runs (`_end_day` → `_compact_memories`).
Usage: .venv\\Scripts\\python.exe tools/verify_context.py
Output: assets/screenshots/context_report.json
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from config import CFG                                         # noqa: E402
# ⚠ 不量像素、不弹窗、**绝不点会 `CFG.save()` 的按钮**（MEMORY 的铁律）。
# [EN] ⚠ Do not measure pixels, do not pop up dialogs, **never click a button that triggers
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


FIXED = '你正在扮演「阿九」。人格：话少、记性好。\n[世界观] 这是个临河的小城。'
SEMI = ('[前情提要] 第 1 天：他丢了件东西。\n[这一站] 弄清楼前那件事。\n'
        '场景：临河茶肆，时间：第 1 天·辰时')
TAIL = '请以 JSON 回答你的行动：{"动作":"wait"}'


def mem_block(n=40):
    from llm import context as CTX
    return CTX.memory_block([{'type': 'observation', 'content': f'记忆{i}',
                              'importance': i % 10, 'game_ts': i * 100}
                             for i in range(n)])


def ev_block(n=30):
    from llm import context as CTX
    return CTX.recent_block([{'content': f'事件{i}'} for i in range(n)])


# ══════════════════════════════════════════════════════════════
#  A. 分层与方向
# [EN] A. Layering and direction
# ══════════════════════════════════════════════════════════════
def test_layers() -> bool:
    ok = True
    from llm import context as CTX

    # ① 方向：记忆块尾部 = 最不重要
    # [EN] ① Direction: tail of the memory block = least important
    mb = CTX.memory_block([
        {'type': 'o', 'content': '不重要', 'importance': 1, 'game_ts': 0},
        {'type': 'o', 'content': '很重要', 'importance': 10, 'game_ts': 9999},
    ])
    lines = mb.split('\n')
    ok &= rec('A1 ★ 记忆块**尾部是最不重要的**（裁尾部就是先走它）',
              '不重要' in lines[-1] and '很重要' in lines[0], str(lines))
    # ② 方向：事件块头部 = 最新
    # [EN] ② Direction: head of the event block = newest
    eb = CTX.recent_block([{'content': '旧事'}, {'content': '新事'}])
    e_lines = eb.split('\n')
    ok &= rec('A2 ★ 事件块**新的在前、旧的在后**（先走的总是最旧的）',
              '新事' in e_lines[0] and '旧事' in e_lines[-1], str(e_lines))

    # ③ 固定前缀永不裁
    # [EN] ③ Fixed prefix is never trimmed
    dyn = [mem_block(60)]
    tiny = CTX.pack(FIXED, SEMI, dyn, TAIL, budget=40)
    ok &= rec('A3 ★★ 预算再小，**固定前缀一个字都没少**',
              '话少、记性好' in tiny.text and '临河的小城' in tiny.text,
              tiny.text[:120].replace('\n', ' | '))
    ok &= rec('A4 动态层被裁光（预算实在不够）', '记忆0' not in tiny.text,
              f'over={tiny.over}')
    ok &= rec('A4 裁了就说（`trimmed` 不留空 —— 静默少喂是事故）',
              bool(tiny.trimmed), str(tiny.trimmed[:2]))

    # ④ 动态层优先于半固定层：预算够放 semi 但放不下 dyn 时，dyn 先走
    # [EN] ④ Dynamic layer takes priority over semi-fixed layer: when the budget fits semi but not dyn, dyn
    # [EN] goes first
    p = CTX.pack(FIXED, SEMI, [mem_block(60)], TAIL,
                 budget=CTX.estimate(FIXED + SEMI + TAIL) + 30)
    ok &= rec('A5 ★ 预算刚好够半固定层 → 半固定层**留着**，只裁动态层',
              '这一站' in p.text and '记忆39' not in p.text, p.trimmed[:2])

    # ⑤ 逐块从尾部丢：越靠后的块越先走
    # ⚠ 用**中文**造大块：`estimate_tokens` 按"词数"算 ASCII，
    #   `'b'*200` 只算 1 个词（2 token），拿它当"大块"根本撑不出差异 ——
    #   这是本项目的老坑（口径是 CJK 字数 + 词数）。
    # [EN] ⑤ Drop block by block from the tail: later blocks go first
    # [EN] ⚠ Use **Chinese** to build large blocks: `estimate_tokens` counts ASCII by "word count",
    # [EN] `'b'*200` counts as only 1 word (2 tokens), using it as a "large block" cannot produce any
    # [EN] difference at all ——
    # [EN] this is an old pitfall of this project (the measure is CJK character count + word count).
    blocks = ['块A\n' + '甲' * 10, '块B\n' + '乙' * 300, '块C\n' + '丙' * 300]
    p2 = CTX.trim_dynamic(blocks, CTX.estimate(FIXED) + 40, FIXED, TAIL)
    # ⚠ 判据要跟"把最重要的那个被丢掉的块补一部分回来"**对齐**：
    #   第一版断言"块 B 一个字都不剩"，而实现是**会补回一行**的 → 假红。
    #   该断言的是：**最不重要的块 C 整块消失**、块 B 只剩**开头一点点**、
    #   块 A 完整留着，而且顺序没乱。
    # [EN] ⚠ The criterion must be **aligned** with "restore part of the most important dropped block":
    # [EN] the first version asserted "block B has not a single character left", while the implementation
    # [EN] **restores one line** → false red.
    # [EN] What should be asserted is: **the least important block C disappears entirely**, block B keeps
    # [EN] only **a tiny bit at the start**,
    # [EN] block A stays complete, and the order is not disturbed.
    b_kept = p2.text.count('乙')
    ok &= rec('A6 ★★ 从尾部往前丢：最不重要的块 C **整块消失**',
              '块C' not in p2.text and '丙' not in p2.text, p2.trimmed[:3])
    ok &= rec('A6 ★ 夹在中间的块 B 只剩**开头一点点**（300 字里留不到 30）',
              '块B' in p2.text and b_kept < 30, f'乙方字留存 {b_kept}/300')
    ok &= rec('A6 ★ 块 A 完整留着（最该留的先留）',
              '块A' in p2.text and p2.text.count('甲') == 10,
              str(p2.text.count('甲')))
    ok &= rec('A6 顺序没乱（A 在 B 之前）',
              p2.text.find('块A') < p2.text.find('块B'),
              f"{p2.text.find('块A')} < {p2.text.find('块B')}")
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 预算
# [EN] B. Budget
# ══════════════════════════════════════════════════════════════
def test_budget() -> bool:
    ok = True
    from llm import context as CTX
    dyn = [mem_block(40), ev_block(30)]
    full = CTX.pack(FIXED, SEMI, dyn, TAIL, budget=0)
    ok &= rec('B1 ★ `budget=0` → 不裁（等价于老行为：想全量喂就全量喂）',
              full.trimmed == [] and '记忆39' in full.text and '事件29' in full.text,
              str(full.tokens))
    big = CTX.pack(FIXED, SEMI, dyn, TAIL, budget=full.tokens + 500)
    ok &= rec('B2 ★ 预算够 → **一个字都不裁**', big.trimmed == [], str(big.tokens))
    small = CTX.pack(FIXED, SEMI, dyn, TAIL, budget=200)
    ok &= rec('B2 ★ 超了才裁', bool(small.trimmed), str(small.trimmed[:2]))
    ok &= rec('B2 ★ 裁完真的进了预算（不是裁了还超）',
              small.tokens <= 200, f'{small.tokens} ≤ 200')
    # 逐级预算单调：预算越大，留下的越多
    # [EN] Budgets are monotonic level by level: the larger the budget, the more is kept
    sizes = [CTX.pack(FIXED, SEMI, dyn, TAIL, budget=b).tokens
             for b in (120, 200, 400, 800)]
    ok &= rec('B3 ★ 预算越大留得越多（单调）', sizes == sorted(sizes), str(sizes))
    # 裁到底还超 → over 标记（调用方该出声）
    # [EN] If still over after trimming to the bottom → over flag (the caller should speak up)
    over = CTX.pack(FIXED + '人' * 400, SEMI, dyn, TAIL, budget=60)
    ok &= rec('B4 ★★ 预算连固定前缀都吃不下 → `over=True`（不许装作没事）',
              over.over and over.tokens > 60, f'{over.tokens} over={over.over}')
    return ok


# ══════════════════════════════════════════════════════════════
#  C. 接线：真的进了 person 决策的 prompt
# [EN] C. Wiring: it really enters the prompt of the person decision
# ══════════════════════════════════════════════════════════════
def test_decide_prompt() -> bool:
    ok = True
    from agent import core as AC
    from world.state import WorldState, PersonState, GameTime

    world = WorldState()
    world.scene = '临河茶肆'
    world.clock = GameTime()
    # ⚠ 两件事一起坑过这一条（第一版就是这么假绿的）：
    #   ① `MAX_CONTEXT_TOKENS` 的 SPEC 有 `min=500`（`coerce` 会夹住），
    #      所以"调小预算"最小只能到 500；
    #   ② **固定前缀是永不裁的** —— 把世界观/规则写很长时，
    #      光固定层就 437 token，prompt **再怎么裁也下不到 500 以下**。
    #      所以这一段的固定层要**保持短**，靠又长又肥的**动态层**（当前情况）
    #      把 prompt 撑到远超预算 —— 那才是会被裁掉的部分。
    # [EN] ⚠ Two things together tripped this one (that is how the first version ended up falsely green):
    # [EN] ① The SPEC of `MAX_CONTEXT_TOKENS` has `min=500` (`coerce` clamps it),
    # [EN] so "lower the budget" can only go down to 500 at minimum;
    # [EN] ② **the fixed prefix is never trimmed** —— when the worldview/rules are written very long,
    # [EN] the fixed layer alone is 437 tokens, the prompt **cannot be trimmed below 500 no matter what**.
    # [EN] So the fixed layer of this section must **stay short**, rely on the long and fat **dynamic
    # [EN] layer** (current situation)
    # [EN] to push the prompt far beyond the budget —— that is the part that will get trimmed.
    world.worldview_text = '这是个临河的小城。'
    world.rules_text = '夜里不许出门。'
    ps = PersonState(name='阿九', location='临河茶肆', role='前台',
                     current_goal='找到妹妹')
    ps.day_plan = ['开门', '巡铺']
    world.people['阿九'] = ps
    BIG_CONTEXT = '门口站着个生人，一直往铺子里看。' * 200

    class Mongo:
        """假库：喂**很多**记忆（好把动态层撑爆）。
                English:
        Fake DB: feed **lots** of memories (to blow out the dynamic layer).
        """

        def retrieve_memory(self, *a, **k):
            return [{'type': 'observation', 'content': f'很久以前的第 {i} 件事',
                     'importance': 5, 'game_ts': i * 10} for i in range(80)]

        def get_summaries(self, *a, **k):
            return [{'game_day': 1, 'text': '他丢了件东西。'}]

        def add_memory(self, *a, **k):
            return 1

        def count_memories(self, *a, **k):
            return 5

        def oldest_memories(self, *a, **k):
            return []

        def drop_memories(self, *a, **k):
            return 0

    seen: dict = {}
    real = AC.llm.chat

    async def fake_chat(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''
        # ⚠ 必须返回 `(文本, 元信息)` —— 2026-10-26 修：`Agent.decide` 现在一律带
        #   `return_meta=True`（要读 `meta['truncated']` 判断"思考把额度吃光了"），
        #   只回字符串会让 `raw, meta = ...` 当场 `ValueError: too many values to unpack`。
        #   症状极具误导性：C1/C2 三条判据全红，看着像"裁剪失效"，其实是桩的形状过期了。
        # [EN] ⚠ Must return `(text, meta)` -- fixed 2026-10-26: `Agent.decide` now always passes
        # [EN] `return_meta=True` (it reads `meta['truncated']` to tell "thinking ate the budget"),
        # [EN] so returning a bare string makes `raw, meta = ...` raise ValueError right away.
        # [EN] The symptom is deeply misleading: C1/C2 all go red and it looks like "trimming broke".
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '测试'}, ensure_ascii=False),
                {'truncated': False, 'empty_output': False, 'model': 'stub',
                 'tier': tier, 'purpose': kw.get('purpose')})

    AC.llm.chat = fake_chat
    saved = CFG.raw('MAX_CONTEXT_TOKENS')
    try:
        a = AC.Agent(ps, Mongo(), world)
        # ⚠ 这里**不能**用 `0` 当"不裁"：`MAX_CONTEXT_TOKENS` 的 SPEC 有 `min=500`，
        #   `coerce` 会把 0 夹成 500 —— 两边都是 500，"变短了"当然测不出来
        #   （第一版就是这么假红的）。要拿"很大的预算"当基准。
        CFG.set('MAX_CONTEXT_TOKENS', '30000')        # 足够大 = 实际不裁
        # [EN] ⚠ Here you **cannot** use `0` as "no trimming": the SPEC of `MAX_CONTEXT_TOKENS` has `min=500`,
        # [EN] `coerce` clamps 0 to 500 —— both sides are 500, of course "got shorter" cannot be tested
        # [EN] (that is how the first version ended up falsely red). Use "a very large budget" as the baseline.
        # [EN] Large enough = effectively no trimming
        asyncio.run(a.decide(BIG_CONTEXT))
        full = seen.get('prompt', '')
        CFG.set('MAX_CONTEXT_TOKENS', '500')          # SPEC 的 min 就是 500
        # [EN] The min of SPEC is 500
        asyncio.run(a.decide(BIG_CONTEXT))
        small = seen.get('prompt', '')
        ok &= rec('C1 ★★ 调小 `MAX_CONTEXT_TOKENS` → 决策 prompt 真的变短了',
                  len(small) < len(full), f'{len(full)} → {len(small)} 字')
        ok &= rec('C2 ★★ 裁过之后，**人格 / 世界观 / 顶级规则仍然在**'
                  '（固定前缀永不裁）',
                  all(k in small for k in ('阿九', '临河的小城', '夜里不许出门')),
                  small[:160].replace('\n', ' | '))
        ok &= rec('C2 ★ 而且动态层确实被削掉了（当前情况那一大坨变少）',
                  small.count('门口站着个生人') < full.count('门口站着个生人'),
                  f"{full.count('门口站着个生人')} → {small.count('门口站着个生人')}")
        ok &= rec('C3 决策该给的东西一个没丢（JSON 指令还在）',
                  '请以 JSON 回答' in small, small[-90:].replace('\n', ' | '))
    finally:
        AC.llm.chat = real
        CFG.set('MAX_CONTEXT_TOKENS', saved)
    return ok


# ══════════════════════════════════════════════════════════════
#  D. CONTEXT_CACHE
# ══════════════════════════════════════════════════════════════
def test_cache() -> bool:
    ok = True
    from world.state import WorldState, GameTime
    world = WorldState()
    world.scene = '临河茶肆'
    world.clock = GameTime()
    world.worldview_text = '这是个临河的小城。'
    world.rules_text = '夜里不许出门。'
    real = world.world_prefix()
    # ⚠ **别自己拼 key**：`_prefix_cache[0]` 的指纹在 2026-10-06 之后还包含
    #   风格来源 / 本幕提示 —— 手工拼的旧指纹对不上，缓存永远不命中，
    #   于是"走缓存"那条判据假红。直接问对象要它自己的指纹。
    # [EN] ⚠ **Do not assemble the key yourself**: the fingerprint of `_prefix_cache[0]` after 2026-10-06
    # [EN] also includes
    # [EN] style source / current act hint —— a hand-assembled old fingerprint will not match, the cache
    # [EN] never hits,
    # [EN] so the "goes through cache" criterion is falsely red. Just ask the object for its own
    # [EN] fingerprint.
    key = world._prefix_cache[0]
    ok &= rec('D1 首次调用就把结果缓存下来了', getattr(world, '_prefix_cache', None)
              is not None, str(getattr(world, '_prefix_cache', None))[:60])
    saved = CFG.raw('CONTEXT_CACHE')
    try:
        # 往缓存里塞一个"毒值"（指纹一样、内容不同）：开了缓存就会拿到它
        # [EN] Stuff a "poison value" into the cache (same fingerprint, different content): with cache on you
        # [EN] will get it
        world._prefix_cache = (key, '【缓存命中】')
        CFG.set('CONTEXT_CACHE', 'true')
        ok &= rec('D2 ★ `CONTEXT_CACHE=true` → 走缓存（拿到的是缓存里的）',
                  world.world_prefix() == '【缓存命中】', world.world_prefix()[:40])
        CFG.set('CONTEXT_CACHE', 'false')
        got = world.world_prefix()
        ok &= rec('D2 ★★ `CONTEXT_CACHE=false` → **真的不用缓存**（重新拼）',
                  got != '【缓存命中】' and '夜里不许出门' in got, got[:60])
    finally:
        CFG.set('CONTEXT_CACHE', saved)
        world._prefix_cache = (key, real)
    return ok


# ══════════════════════════════════════════════════════════════
#  E. 记忆压缩（SUMMARIZE_MEMORY_AFTER）
# [EN] E. Memory compression (SUMMARIZE_MEMORY_AFTER)
# ══════════════════════════════════════════════════════════════
def _tmp_db(n_mem: int):
    """一个真的 SQLite 库（要验 `count/oldest/drop` 真的动数据，不能打桩）。
        English:
    A real SQLite database (need to verify `count/oldest/drop` really touch the data, no stubbing
    allowed).
    """
    import tempfile
    from store.db import DB
    path = Path(tempfile.mkdtemp(prefix='nws_ctx_')) / 'ctx.db'
    db = DB(path)
    for i in range(n_mem):
        db.add_memory('阿九', f'第 {i} 件事', 'observation', 5.0, float(i * 60))
    return db


def test_compact() -> bool:
    ok = True
    from agent.core import Agent
    from world.state import WorldState, PersonState, GameTime
    import llm.replies as R

    world = WorldState()
    world.clock = GameTime()
    world.scene = '临河茶肆'
    ps = PersonState(name='阿九', location='临河茶肆', role='前台')
    world.people['阿九'] = ps

    calls: list[str] = []
    # ⚠ 打桩要打 **`agent.core.ask`**：`agent/core.py` 里是
    #   `from llm.replies import ask`（模块级绑定），改 `llm.replies.ask`
    #   对它没有任何影响 —— 第一版就是这么假红的。
    # [EN] ⚠ The stub must patch **`agent.core.ask`**: in `agent/core.py` it is
    # [EN] `from llm.replies import ask` (module-level binding), changing `llm.replies.ask`
    # [EN] has no effect on it —— that is how the first version ended up falsely red.
    from agent import core as AC
    real = AC.ask

    def fake(reply, ok_=True):
        async def _f(tier, messages, **kw):
            from llm.replies import Reply
            calls.append(kw.get('purpose', ''))
            return Reply(value=reply, ok=ok_,
                         notes=[] if ok_ else ['模型没给可用的正文'])
        return _f

    saved = CFG.raw('SUMMARIZE_MEMORY_AFTER')
    try:
        db = _tmp_db(50)
        a = Agent(ps, db, world)

        # ① 没到阈值 → 一次 LLM 都不调
        # [EN] ① Below threshold → not a single LLM call
        CFG.set('SUMMARIZE_MEMORY_AFTER', '200')
        calls.clear()
        r = asyncio.run(a.compact_memory())
        ok &= rec('E1 ★ 没到阈值 → `skipped`，**一次 LLM 调用都没有**',
                  r.get('skipped') and calls == [], f'{r} / {calls}')
        ok &= rec('E1 没到阈值 → 记忆一条没动', db.count_memories('阿九') == 50,
                  str(db.count_memories('阿九')))

        # ② 超阈值 → 折成一条
        # [EN] ② Above threshold → fold into one entry
        CFG.set('SUMMARIZE_MEMORY_AFTER', '10')
        AC.ask = fake('他把早先那件事处理完了；还欠着一个人情。')
        calls.clear()
        before = db.count_memories('阿九')
        r = asyncio.run(a.compact_memory(keep=10))
        after = db.count_memories('阿九')
        ok &= rec('E2 ★★ 超阈值 → 折起一批，条数真的少了',
                  after < before and r.get('ok'), f'{before} → {after} / {r}')
        ok &= rec('E2 ★ 调的一次是 `memory_compact`（没拿别的事来凑）',
                  calls == ['memory_compact'], str(calls))
        rows = db.retrieve_memory('阿九', 5)
        ok &= rec('E2 ★★ 摘要**真的进了库**（写进去了）',
                  any('已压缩' in str(x.get('content')) for x in rows),
                  str([str(x.get('content'))[:24] for x in rows[:3]]))

        # ③ 拿不到模型结果 → 退回原文拼接（**绝不丢内容**）
        # [EN] ③ Cannot get model result → fall back to concatenating the original text (**never drop
        # [EN] content**)
        db2 = _tmp_db(30)
        a2 = Agent(ps, db2, world)
        AC.ask = fake('', ok_=False)
        r2 = asyncio.run(a2.compact_memory(keep=5))
        ok &= rec('E3 ★★ 模型拿不到 → **退回原文拼接**，不空着也不丢内容',
                  r2.get('ok') and '；' in str(
                      db2.retrieve_memory('阿九', 1)[0].get('content', '')),
                  str(r2))
        ok &= rec('E3 降级时也真的压下去了（条数变少）',
                  db2.count_memories('阿九') < 30, str(db2.count_memories('阿九')))

        # ④ `=0` 关得掉
        # [EN] ④ `=0` turns it off
        db3 = _tmp_db(30)
        a3 = Agent(ps, db3, world)
        CFG.set('SUMMARIZE_MEMORY_AFTER', '0')
        calls.clear()
        r3 = asyncio.run(a3.compact_memory())
        ok &= rec('E4 ★ `SUMMARIZE_MEMORY_AFTER=0` → 关掉（旋钮真被读）',
                  r3.get('skipped') and db3.count_memories('阿九') == 30 and not calls,
                  f'{r3} / 记忆 {db3.count_memories("阿九")}')
        AC.ask = real
    finally:
        AC.ask = real
        CFG.set('SUMMARIZE_MEMORY_AFTER', saved)
    return ok


def test_compact_wiring() -> bool:
    """★★ 日界真的会跑压缩 —— 否则 `compact_memory` 写得再好也没人调。
        English:
    ★★ The day boundary really runs compression —— otherwise no matter how well `compact_memory` is
    written, no one calls it.
    """
    ok = True
    import inspect
    from sim.loop import RunLoop
    src = inspect.getsource(RunLoop._end_day)
    ok &= rec('E5 ★ `_end_day` 里真的调了 `_compact_memories()`',
              '_compact_memories()' in src,
              ' | '.join(l.strip() for l in src.split('\n')
                         if '_compact_memories' in l))
    src2 = inspect.getsource(RunLoop._compact_memories)
    ok &= rec('E5 ★ 它真的对**每个 agent** 调了 `compact_memory()`',
              'compact_memory()' in src2 and 'gather' in src2, src2[:80])
    ok &= rec('E5 ★ 并发跑（串行 12 个人就是 12 次往返）',
              'asyncio.gather' in src2, '')
    return ok


# ══════════════════════════════════════════════════════════════
#  F. **主动压缩**（2026-10-10，用户点名）
# [EN] F. **Proactive compression** (2026-10-10, user called it out)
# ══════════════════════════════════════════════════════════════
#
# 用户原话：「不是要提醒我自己去调整 而是系统要提示我 并且进行主动压缩」。
# [EN] User's exact words: "It is not about reminding me to adjust it myself, but the system should
# [EN] prompt me and perform proactive compression".
#
# 这一组守**两件缺一不可的事**：
#   ① 贴到触发线时**真的动手压**（而不是只记一条"快满了"的日志）；
#   ② 压完**要讲给作者听**（中栏看得见）—— 否则它和"模型今天忽然变笨了"
#      长得一模一样：人物忘掉前因、说话变浅，屏幕上却没有一句解释。
# [EN] This group guards **two things, neither is optional**:
# [EN] ① When hitting the trigger line, **actually compress** (rather than just logging a "getting
# [EN] full" entry);
# [EN] ② After compressing, **tell the author** (visible in the middle column) —— otherwise it looks
# [EN] exactly
# [EN] the same as "the model suddenly got dumber today": characters forget prior context, speech
# [EN] becomes shallow, yet not a single line of explanation on screen.
#
# ⚠ 判据必须**量到 token 真的降下来**。"调用了压缩"这种断言挡不住
#   "压了个寂寞"（比如保留比例传了 1.0、等于什么都没折）—— 那是本项目
#   最忌讳的"判名字在不在"式断言。
# [EN] ⚠ The criterion must **measure that tokens actually drop**. An assertion like "compression was
# [EN] called" cannot stop
# [EN] "compressed for nothing" (e.g. keeping ratio passed as 1.0, i.e. folding nothing at all) —— that
# [EN] is this project's
# [EN] most taboo style of assertion, the "check whether the name is present" kind.
def _compact_fixture(big_lines: int):
    """一个"上下文被撑爆"的夹具：短固定层 + 又长又肥的 `当前情况`。

    ⚠ 固定层要**短**：它是永不裁的，写长了再怎么压也下不来（C 组踩过这个坑）。
    
        English:
    A fixture for "context blown out": short fixed layer + long and fat `当前情况`.
        ⚠ The fixed layer must be **short**: it is never trimmed, so if written long, no amount of compression can bring it down (group C stepped on this pit).
    """
    from world.state import WorldState, PersonState, GameTime
    from agent import core as AC
    world = WorldState()
    world.scene = '临河茶肆'
    world.clock = GameTime()
    world.worldview_text = '这是个临河的小城。'
    world.rules_text = '夜里不许出门。'
    ps = PersonState(name='阿九', location='临河茶肆', role='前台',
                     current_goal='找到妹妹')
    ps.day_plan = ['开门', '巡铺']
    world.people['阿九'] = ps

    class Mongo:
        def retrieve_memory(self, *a, **k):
            return [{'type': 'observation', 'content': f'很久以前第 {i} 件事',
                     'importance': 5, 'game_ts': i * 10} for i in range(5)]

        def get_summaries(self, *a, **k):
            return [{'game_day': 1, 'text': '他丢了件东西。'}]

        def add_memory(self, *a, **k):
            return 1

        def count_memories(self, *a, **k):
            return 5

        def oldest_memories(self, *a, **k):
            return []

        def drop_memories(self, *a, **k):
            return 0

    #:`当前情况` 就是"这一场戏说到现在的全部" —— 它才是撑大上下文的那一块
    # [EN] : `current situation` is "everything said in this scene up to now" —— it is the part that
    # [EN] inflates the context
    big = '\n'.join(f'第 {i} 拍：有人说了一句要紧的话。' for i in range(big_lines))
    return AC, world, ps, Mongo(), big


def test_active_compact() -> bool:
    ok = True
    AC, world, ps, db, big = _compact_fixture(120)
    seen: dict = {}
    summarised: list[str] = []

    async def fake_chat(tier, messages, **kw):
        msg = messages[-1]['content'] if messages else ''
        # ⚠ 桩必须返回 `(文本, 元信息)`：真实 `llm.chat(return_meta=True)` 就
        #   是这个形状，只回字符串会让上层 `raw, meta = ...` 当场
        #   `ValueError: too many values to unpack` —— 转一圈表现成"压缩没生效"。
        # [EN] ⚠ The stub must return `(text, meta)`: the real `llm.chat(return_meta=True)` is
        # [EN] exactly this shape; returning only a string makes the upper layer `raw, meta = ...` immediately
        # [EN] throw
        # [EN] `ValueError: too many values to unpack` —— which after a round shows up as "compression did not
        # [EN] take effect".
        meta = {'truncated': False, 'empty_output': False, 'has_reasoning': False,
                'max_tokens': kw.get('max_tokens'), 'model': 'stub',
                'tier': tier, 'purpose': kw.get('purpose')}
        if kw.get('purpose') == 'ctx_compact' or '压成' in msg:
            summarised.append(msg)
            return '他把井底那件事说了出来，还没了结。', meta
        seen['prompt'] = msg
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '测试'}, ensure_ascii=False), meta)

    real = AC.llm.chat
    AC.llm.chat = fake_chat
    saved = {k: CFG.raw(k) for k in
             ('MAX_CONTEXT_TOKENS', 'CTX_COMPACT_AT', 'CTX_COMPACT_KEEP',
              'CTX_COMPACT_TARGET')}
    try:
        a = AC.Agent(ps, db, world)
        # ── F1 没到触发线 ⇒ **一次都不压**（不白花模型调用）──
        CFG.set('MAX_CONTEXT_TOKENS', '200000')     # 远大于实际
        # [EN] ── F1 Below trigger line ⇒ **compress not even once** (do not waste model calls) ──
        # [EN] far larger than actual
        asyncio.run(a.decide(big))
        full = seen.get('prompt', '')
        ok &= rec('F1 ★ 没到触发线时**一次都不压**（不做无用的模型调用）',
                  not summarised and not getattr(a, 'last_compaction', None),
                  f'压了 {len(summarised)} 次')

        # ── F2 贴到触发线 ⇒ 真的动手压，而且 prompt 真的变短 ──
        # [EN] ── F2 Hits trigger line ⇒ actually compresses, and the prompt really gets shorter ──
        # ★★ 2026-10-26：**900 → 2000**。原来 900 太小：压完之后 `CTX.pack` 仍然
        #   放不下那几块动态内容，于是**整块丢掉** —— prompt 里只剩固定前缀。
        #   那时 F2c（"压出来的东西要留在 prompt 里"）必然红，而这跟"压缩是否生效"
        #   无关：900 连"压过之后的摘要"都装不下。判据要测的是**压缩这条路**，
        #   不是"预算小到极限时会怎样"（那归 `llm.context` 自己的裁剪判据）。
        #   ⚠ 2000 仍然远小于原文（≈6900 token）⇒ 触发线与"变短"照样成立。
        # [EN] ★★ 2026-10-26: **900 -> 2000**. 900 was too small: even after compaction
        # [EN] `CTX.pack` still could not fit the dynamic blocks, so it **dropped them whole** and the
        # [EN] prompt kept only the fixed prefix. F2c ("what was folded must stay in the prompt") was
        # [EN] therefore always red, and that has nothing to do with "did compaction work": 900 cannot
        # [EN] even hold the summary. This criterion tests **the compaction path**, not "what happens
        # [EN] at an extreme small budget" (that belongs to `llm.context`'s own trimming criteria).
        # [EN] ⚠ 2000 is still far below the original (~6900 tokens) => the trigger and "it got
        # [EN] shorter" both still hold.
        CFG.set('MAX_CONTEXT_TOKENS', '4000')
        CFG.set('CTX_COMPACT_AT', '0.8')
        CFG.set('CTX_COMPACT_KEEP', '0.35')
        CFG.set('CTX_COMPACT_TARGET', '0.5')
        asyncio.run(a.decide(big))
        small = seen.get('prompt', '')
        info = getattr(a, 'last_compaction', None) or {}
        ok &= rec('F2 ★★★ 贴到 `CTX_COMPACT_AT` 就**主动压缩**（不是只记一条日志）',
                  bool(summarised) and bool(info),
                  f'压了 {len(summarised)} 次 / 记录={bool(info)}')
        ok &= rec('F2b ★★★ 压完 prompt **真的变短**（判 token 降下来，'
                  '不是"调用了压缩"这种名字断言）',
                  len(small) < len(full) and info.get('after', 0) < info.get('before', 1),
                  f"{len(full)} → {len(small)} 字 / "
                  f"{info.get('before')} → {info.get('after')} token")
        ok &= rec('F2c ★★ 折出来的东西**留在 prompt 里**（摘要在，不是整段丢掉）',
                  '已压缩' in small, small[:80].replace('\n', ' | '))

        # ── F3 保留比例真的说了算 ──
        CFG.set('CTX_COMPACT_KEEP', '0.9')          # 几乎全留 ⇒ 压不动多少
        # [EN] ── F3 The keeping ratio really matters ──
        # [EN] keep almost all ⇒ can barely compress
        a2 = AC.Agent(ps, db, world)
        summarised.clear()
        asyncio.run(a2.decide(big))
        lo = (getattr(a2, 'last_compaction', None) or {}).get('after', 0)
        CFG.set('CTX_COMPACT_KEEP', '0.1')          # 几乎全折 ⇒ 压得很狠
        # [EN] fold almost all ⇒ compresses very hard
        a3 = AC.Agent(ps, db, world)
        summarised.clear()
        asyncio.run(a3.decide(big))
        hi = (getattr(a3, 'last_compaction', None) or {}).get('after', 0)
        ok &= rec('F3 ★★ `CTX_COMPACT_KEEP` 真的说了算：保留得越少、压完越短'
                  '（0.9 保留 → 长；0.1 保留 → 短）',
                  bool(lo) and bool(hi) and hi < lo, f'keep=0.9→{lo}  keep=0.1→{hi}')

        # ── F4 只压内容块，**指令块一个字不动** ──
        # [EN] ── F4 Only compresses content blocks, **instruction block not a single character moves** ──
        #
        # ⚠ 第一版这条是"在压完的 prompt 里找『演员手艺』『去AI』那几句" ——
        #   **打不红**（反例法当场证明）：那几个词在**尾模板**里也有，
        #   所以哪怕指令块真被折掉，prompt 里照样搜得到。
        #   而且这个夹具里 `_actor_craft` / `_deai` / `_cot` 本来就是空的，
        #   从 prompt 上根本观察不到它们。
        # ⇒ 改成**直接量契约**：喂一段带"指令块"的 dyn 进去，问它有没有被动过。
        # [EN] ⚠ The first version of this one was "search the compressed prompt for those lines about 『actor
        # [EN] craft』 『de-AI』" ——
        # [EN] **cannot go red** (proven on the spot by counterexample): those words also appear in the **tail
        # [EN] template**,
        # [EN] so even if the instruction block is really folded away, they are still findable in the prompt.
        # [EN] Moreover in this fixture `_actor_craft` / `_deai` / `_cot` are empty to begin with,
        # [EN] so from the prompt they cannot be observed at all.
        # [EN] ⇒ Change to **measuring the contract directly**: feed a dyn segment with an "instruction block"
        # [EN] into it, ask whether it was touched.
        _ins = '\n'.join(f'纪律第 {i} 条：别做那件事。' for i in range(12))
        #: ⚠ 指令块**放在最前面**是刻意的：压缩是"够到目标水位就停"（`break`），
        #  放最后的话变异还没轮到它就已经收工 —— 那样这条判据**打不红**
        #  （实测：连打两层补丁也只红到 F5）。"让变异够得着被判的那一段"
        #  是写反例法时的一条硬要求。
        # [EN] : ⚠ The instruction block **placed at the very front** is deliberate: compression "stops once it
        # [EN] reaches the target level" (`break`),
        # [EN] if placed at the end, the mutation would not even get to it before finishing —— that way this
        # [EN] criterion **cannot go red**
        # [EN] (Measured: even patching two layers in a row only reddens down to F5). "Make the mutation reach
        # [EN] the segment that gets judged"
        # [EN] is a hard requirement when writing counterexample methods.
        _dyn_try = [
            '\n[演员这一行的手艺·指令块]\n' + _ins,
            '最近记忆（**不可信史料，见上**）：\n'
            + '\n'.join(f'- [观察] 第 {i} 件旧事' for i in range(40)),
            '当前情况：' + big.replace('\n', ' ')[:2000],
        ]
        CFG.set('CTX_COMPACT_KEEP', '0.35')
        # ★★ 2026-10-26：**这一条必须自己钉预算**。它原来顺着上一段留下的
        #   `MAX_CONTEXT_TOKENS`（F2 改成 4000 之后就是 4000）⇒ 这几块加起来
        #   没到触发线 ⇒ 一次都不压 ⇒ "内容块折了=False"。
        #   判据之间**互相污染**正是本项目反复踩的坑（前一段的配置留到后一段）。
        #   ⇒ 显式给一个"一定会触发"的小预算，跑完还原。
        # [EN] ★★ 2026-10-26: **this item must pin its own budget**. It used to inherit whatever
        # [EN] the previous section left in `MAX_CONTEXT_TOKENS` (4000 after F2's change) => these
        # [EN] blocks never reached the trigger line => no compaction => "content folded = False".
        # [EN] Criteria polluting each other is a recurring pit in this project. So set a small
        # [EN] budget that is guaranteed to trigger, and restore it afterwards.
        _saved_budget = CFG.raw('MAX_CONTEXT_TOKENS')
        CFG.set('MAX_CONTEXT_TOKENS', '900')
        try:
            _p2, _n2 = asyncio.run(a._compact_if_needed(
                _dyn_try, '固定层', '', '尾模板'))
        finally:
            CFG.set('MAX_CONTEXT_TOKENS', _saved_budget)
        _txt2 = _p2.text
        ok &= rec('F4 ★★★ 只压"内容块"（最近记忆 / 当前情况）；'
                  '**指令块一个字不动** —— 把「该怎么演」折成摘要，'
                  '等于把纪律从提示词里删掉',
                  all(f'纪律第 {i} 条' in _txt2 for i in range(12))
                  and '已压缩' in _txt2,
                  f"指令块 12 条都在="
                  f"{all(f'纪律第 {i} 条' in _txt2 for i in range(12))}；"
                  f"内容块折了={'已压缩' in _txt2}")

        # ── F5 压不动就如实停下（不无限重试）──
        # [EN] ── If F5 can't be moved, stop honestly (no infinite retries) ──
        AC2, world2, ps2, db2, tiny = _compact_fixture(3)
        a4 = AC2.Agent(ps2, db2, world2)
        summarised.clear()
        CFG.set('MAX_CONTEXT_TOKENS', '500')        # 比固定层还小 ⇒ 怎么压都超
        # [EN] Smaller than the fixed layer ⇒ no matter how you compress, it overflows
        asyncio.run(a4.decide('短'))
        n_calls = len(summarised)
        ok &= rec('F5 ★★★ 压不动时**如实停下**（最多 `CTX_COMPACT_MAX_ROUNDS` 轮，'
                  '不无限重试烧钱）',
                  n_calls <= int(CFG.i('CTX_COMPACT_MAX_ROUNDS')) * 2,
                  f'压缩调用 {n_calls} 次')

        # ── F6 这件事会**讲给作者听** ──
        # [EN] ── F6 This matter will be **told to the author** ──
        import inspect
        from sim.loop import RunLoop
        src = inspect.getsource(RunLoop._announce_compaction)
        # ⚠ **两侧都要查**。第一版只查了循环那侧（`_announce_compaction` 的源码
        #   里有 `last_compaction`），于是把 Agent 那边的赋值删掉时它**照样绿** ——
        #   反例法当场证明那是装饰品：管道的**两头**都得接上才算数。
        # [EN] ⚠ **Both sides must be checked**. The first version only checked the loop side
        # [EN] (`_announce_compaction`'s source
        # [EN] has `last_compaction` in it), so when the assignment on the Agent side was deleted it **still
        # [EN] stayed green** ——
        # [EN] the counterexample method proved on the spot that it was decoration: the **two ends** of the
        # [EN] pipeline both have to be connected for it to count.
        agent_src = inspect.getsource(AC.Agent._compact_if_needed)
        ok &= rec('F6 ★★★ 压缩会**播报给作者**：Agent 那侧真的把说明记下来'
                  '（`self.last_compaction = …`）',
                  'self.last_compaction = ' in agent_src,
                  '漏了这一步：压缩发生了但没人说得出口')
        ok &= rec('F6b ★★★ 而主循环那侧真的把它读出来、推给作者'
                  '（管道两头都要接上，只接一头 = 假按钮）',
                  'last_compaction' in src and '_push_narrative' in src,
                  src[:70].replace('\n', ' '))
        # ⚠ 判"读完要清"，否则一拍压缩过、后面每一拍都重复播同一句。
        # [EN] ⚠ Judge "clear after reading", otherwise one tick compresses and every subsequent tick replays
        # [EN] the same line.
        ok &= rec('F6c ★★ 播完**清掉标记**（否则同一句话会被反复播报，'
                  '这个项目以前被 550 条重复消息刷过屏）',
                  'last_compaction = None' in src, '')
        ok &= rec('F6d ★ 主循环里真的调了它（写完不接线 = 假按钮）',
                  '_announce_compaction(actions)'
                  in inspect.getsource(RunLoop._tick),
                  '')
    finally:
        AC.llm.chat = real
        for k, v in saved.items():
            if v is not None:
                CFG.set(k, str(v))
    return ok


if __name__ == '__main__':
    print('上下文分层裁剪 —— 验证', flush=True)
    ok = True
    try:
        head('A. 分层与方向（固定永不裁 / 尾部往前）')
        ok &= test_layers()
        head('B. 预算（不超不裁 / 超了才裁 / over 要报）')
        ok &= test_budget()
        head('C. 接线（真的进了人物决策 prompt）')
        ok &= test_decide_prompt()
        head('D. CONTEXT_CACHE')
        ok &= test_cache()
        head('E. 记忆压缩（阈值 / 折起 / 降级 / 关掉 / 日界接线）')
        ok &= test_compact()
        ok &= test_compact_wiring()
        head('F. **主动压缩**（贴线就压 / 保留最近一段 / 落到水位 / 讲给作者听）')
        ok &= test_active_compact()
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'context_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1500:])
    sys.exit(0 if report['ok'] else 2)
