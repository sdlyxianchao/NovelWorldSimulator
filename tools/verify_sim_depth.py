# -*- coding: utf-8 -*-
"""验证四项推演深度优化：前情提要 / 导演死旋钮 / 速度 / 计划链。

这四项的共同点是「**代码里早就写好、但从来没人调用**」或者
「**写了个旋钮却没人读**」—— 光看代码像是对的（每个函数单独看都合理），
所以每条判据都要能在**改回原样**时红出来。

用法：.venv\\Scripts/python.exe tools/verify_sim_depth.py
产出：assets/screenshots/sim_depth_report.json

English:
Verify four reasoning-depth optimizations: recap / director dead knobs / speed / plan chain.
What these four have in common is "**written in the code long ago, but never called by anyone**"
or
"**a knob was written but nobody reads it**" —— just looking at the code it seems fine (each
function looks reasonable on its own),
so each criterion must be able to go red when **reverted to the original**.
Usage: .venv\\Scripts/python.exe tools/verify_sim_depth.py
Output: assets/screenshots/sim_depth_report.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from config import CFG                                       # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('OUTPUT_FORMAT', 'script')

from i18n import set_lang                                    # noqa: E402
set_lang('zh')

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  A. 纯逻辑
# [EN] A. Pure logic
# ══════════════════════════════════════════════════════════════
def logic_checks() -> None:
    from store.db import DB, tokens, similarity
    from world.state import WorldState, PersonState
    from util.timefmt import GameTime
    from director.engine import DirectorEngine

    # ── A1 分词：必须是二元组，不能是单字 ──
    # [EN] ── A1 Tokenization: must be pairs, not single characters ──
    t = tokens('今夜别出门')
    ok('A1 相关性的分词是**二元组**（不是单字集合 —— 单字集合几乎恒命中，等于没有区分度）',
       '今夜' in t and '别出' in t and '今' not in t, sorted(t))
    ok('A1b 英文按词、长度 1 的词丢掉（a / i 这种不参与打分）',
       'water' in tokens('The Water Clock') and 'a' not in tokens('a b'),
       sorted(tokens('The Water Clock')))

    # ── A2 相似度真有区分度 ──
    # [EN] ── A2 Similarity really has discrimination ──
    same = similarity('更夫报说后巷出了事', '后巷出了事，更夫来报')
    diff = similarity('更夫报说后巷出了事', '掌柜擦了一晚上紫砂壶')
    ok('A2 同一个事件换个说法 → 相似度高；不相干的 → 接近 0（能拿来拦重复事件）',
       same > 0.45 and diff < 0.1, f'换个说法={same:.2f} 不相干={diff:.2f}')

    # ── A3 记忆检索：相关性真有排序作用 ──
    # [EN] ── A3 Memory retrieval: relevance really has a sorting effect ──
    db = DB(Path(tempfile.mkdtemp(prefix='nws_depth_db_')) / 'a.db')
    db.add_memory('甲', '更夫来报：后巷出了事，地上有血', 'observation', 5, game_ts=100)
    db.add_memory('甲', '掌柜擦了一晚上紫砂壶，一句话没说', 'observation', 5, game_ts=100)
    got = db.retrieve_memory('甲', 2, '后巷到底出了什么事', now_game_min=120)
    ok('A3 ★ 检索时"相关的那条"排在前面（旧实现单字命中 → 两条都是 1.0，排序随机）',
       got and '后巷' in got[0]['content'] and got[0]['_relevance'] > got[1]['_relevance'],
       [(m['content'][:10], round(m['_relevance'], 2)) for m in got])

    # ── A4 recency 走**故事时间** ──
    # [EN] ── A4 recency goes by **story time** ──
    db2 = DB(Path(tempfile.mkdtemp(prefix='nws_depth_db_')) / 'b.db')
    db2.add_memory('乙', '很久以前的事（第 1 天）', 'observation', 5, game_ts=1 * 1440)
    db2.add_memory('乙', '刚刚发生的事（第 20 天）', 'observation', 5, game_ts=20 * 1440)
    got2 = db2.retrieve_memory('乙', 2, '', now_game_min=20 * 1440 + 10)
    # ⚠ 判据要比**幅度**，不能只比大小：退回真实时间后两条记忆的 ts 只差几毫秒，
    #   `_recency` 仍是"大于"（相差 1e-6），只比大小的话这条永远绿（反例法实测）。
    # [EN] ⚠ The criterion must compare **magnitude**, not just relative order: after reverting to real
    # [EN] time the two memories' ts differ by only a few milliseconds,
    # [EN] `_recency` is still "greater" (differing by 1e-6); if you only compare relative order this test
    # [EN] stays green forever (verified by counterexample testing).
    ok('A4 ★ recency 按**故事时间**算（第 20 天的记忆新、第 1 天的旧，差距显著）',
       got2 and '刚刚发生' in got2[0]['content']
       and got2[0]['_recency'] - got2[1]['_recency'] > 0.1,
       [(m['content'][:8], round(m['_recency'], 3)) for m in got2])
    # 对照：真实时间几乎相同 → 旧实现（按 time.time()）根本分不出这两条
    # [EN] Control: real times are almost identical → the old implementation (using time.time()) simply
    # [EN] cannot distinguish these two
    ok('A4b 两条记忆的**真实写入时刻**几乎一样（所以旧实现分不出来）',
       abs(got2[0]['ts'] - got2[1]['ts']) < 2.0,
       f'真实时间差 {abs(got2[0]["ts"] - got2[1]["ts"]):.3f}s')

    # ── A5 空 query 不做假分 ──
    # [EN] ── A5 Empty query does not produce fake scores ──
    got3 = db2.retrieve_memory('乙', 2, '')
    ok('A5 没有 query 时相关性一律 0（旧实现人人有份的"假分"会让检索看上去在工作）',
       all(m['_relevance'] == 0.0 for m in got3), [m['_relevance'] for m in got3])

    # ── A6 RECENCY_DECAY 旋钮真的被读 ──
    # [EN] ── A6 The RECENCY_DECAY knob is really read ──
    old = CFG.s('RECENCY_DECAY')
    CFG.set('RECENCY_DECAY', '0.90')
    fast = db2.retrieve_memory('乙', 2, '', now_game_min=20 * 1440 + 10)[-1]['_recency']
    CFG.set('RECENCY_DECAY', '0.999')
    slow = db2.retrieve_memory('乙', 2, '', now_game_min=20 * 1440 + 10)[-1]['_recency']
    CFG.set('RECENCY_DECAY', old)
    ok('A6 `RECENCY_DECAY` 旋钮真的参与计算（改它 → 旧记忆的留存系数跟着变）',
       fast < slow, f'0.90→{fast:.4f} / 0.999→{slow:.4f}')

    # ── A7 前情提要：写入/读出/升序/空不记 ──
    # [EN] ── A7 Recap: write / read / ascending order / empty not recorded ──
    db3 = DB(Path(tempfile.mkdtemp(prefix='nws_depth_db_')) / 'c.db')
    db3.add_summary(2, '第二天的事。')
    db3.add_summary(1, '第一天的事。')
    db3.add_summary(3, '')
    rows = db3.get_summaries(5)
    ok('A7 `add_summary` / `get_summaries` 落盘并读回，**空文本不记**',
       [r['game_day'] for r in rows] == [1, 2], [r['game_day'] for r in rows])
    ok('A7b 读回来是**按天升序**（拼 prompt 要从早到晚读，倒着给模型会串）',
       [r['text'] for r in rows] == ['第一天的事。', '第二天的事。'],
       [r['text'] for r in rows])

    # ── A8 张力曲线：三档系数不同，auto 跟随节奏感 ──
    # [EN] ── A8 Tension curve: three levels have different coefficients, auto follows the sense of rhythm
    # [EN] ──
    from director.engine import _TENSION_CURVE
    ok('A8 张力曲线三档（flat/medium/roller）的衰减与抬升**互不相同**',
       len({v for v in _TENSION_CURVE.values()}) == 3, _TENSION_CURVE)

    world = WorldState()
    d = DirectorEngine(world, db3)
    old_curve, old_pacing = CFG.s('TENSION_CURVE'), CFG.s('PACING_STYLE')
    CFG.set('TENSION_CURVE', 'auto')
    CFG.set('PACING_STYLE', 'slow')
    slow_c = d._curve()
    CFG.set('PACING_STYLE', 'roller')
    roll_c = d._curve()
    CFG.set('PACING_STYLE', old_pacing)
    ok('A8b `auto` 跟着书斋里的**节奏感**走（选"过山车"→ 张力曲线也变过山车）',
       slow_c == _TENSION_CURVE['flat'] and roll_c == _TENSION_CURVE['roller'],
       f'slow→{slow_c} roller→{roll_c}')

    # ── A9 跨天回落：张力真的降下来（这是"事件注入不会永久关闭"的前提）──
    # [EN] ── A9 Cross-day falloff: tension really drops (this is the precondition for "event injection
    # [EN] will not be permanently disabled") ──
    CFG.set('TENSION_CURVE', 'medium')
    CFG.set('PACING_STYLE', 'medium')
    world.tension = 0.9
    vals = []
    for _ in range(3):
        vals.append(round(d.on_day_start(), 3))
    ok('A9 ★ 跨天时张力**按曲线回落**（旧实现只增不减 → 越过 0.4 后事件注入永久关闭）',
       all(b < a for a, b in zip([0.9] + vals, vals)) and vals[-1] < 0.6, vals)
    world.tension = 0.01
    d.on_day_start()
    ok('A9b 回落不会掉到负数', world.tension >= 0.0, world.tension)

    # ── A10 事件抬升用曲线系数（不是写死的 0.3）──
    # [EN] ── A10 Event boost uses the curve coefficient (not a hardcoded 0.3) ──
    world.tension = 0.0
    CFG.set('TENSION_CURVE', 'flat')
    d.tension_rise(1.0)
    flat_v = round(world.tension, 3)
    world.tension = 0.0
    CFG.set('TENSION_CURVE', 'roller')
    d.tension_rise(1.0)
    roll_v = round(world.tension, 3)
    CFG.set('TENSION_CURVE', old_curve)
    ok('A10 ★ 事件抬升幅度由曲线决定（写了一年的 0.3 硬编码已经换成旋钮）',
       flat_v == _TENSION_CURVE['flat'][1] and roll_v == _TENSION_CURVE['roller'][1]
       and roll_v > flat_v, f'flat={flat_v} roller={roll_v}')

    # ── A11 高潮日 ──
    # ⚠ 判据要设 `game_day`，不是 `clock` —— `is_climax_day()` 读的是 `world.game_day`
    #   （产品里这两者由 `_advance_clock` 保持同步，夹具里得自己设对那个字段）。
    # [EN] ── A11 Climax day ──
    # [EN] ⚠ The criterion must set `game_day`, not `clock` — `is_climax_day()` reads `world.game_day`
    # [EN] (In the product these two are kept in sync by `_advance_clock`; in the fixture you must set that
    # [EN] field correctly yourself).
    CFG.set('CLIMAX_EVERY_DAYS', '5')
    world.game_day = 5
    d5 = d.is_climax_day()
    world.game_day = 3
    d3 = d.is_climax_day()
    world.game_day = 10
    d10 = d.is_climax_day()
    ok('A11 高潮日 = 每 `CLIMAX_EVERY_DAYS` 天一次（5/10 是，3 不是）',
       d5 and d10 and not d3, f'第5天={d5} 第3天={d3} 第10天={d10}')

    # ── A12 停滞检测走**故事时间**（重点：真实时间几乎没动）──
    # [EN] ── A12 Stagnation detection goes by **story time** (key point: real time barely moves) ──
    world.clock = GameTime(day=1, minutes=0)
    d2 = DirectorEngine(world, db3)
    CFG.set('STALL_WINDOW_MINUTES', '180')
    t0 = time.time()
    ok('A12 刚开局不算停滞', not d2._is_stalling(), '')
    world.clock = GameTime(day=1, minutes=60 * 4)          # 故事里过了 4 小时
    # [EN] 4 hours passed in the story
    stalled = d2._is_stalling()
    real_elapsed = time.time() - t0
    ok('A12b ★ 故事时间过了 4 小时 → 判定停滞（此时**真实时间只过了不到 1 秒**）',
       stalled and real_elapsed < 1.0,
       f'停滞={stalled} 真实耗时={real_elapsed:.3f}s（旧实现按 time.time() 永远判不出）')

    # ── A12c ★★★ 导演的**常规介入闸**不能被张力长期关死（2026-10-10）──
    # [EN] ── A12c ★★★ The director's **routine intervention gate** must not be locked shut by tension for
    # [EN] long periods (2026-10-10) ──
    #
    # 这一条来自用户第一次真跑一天之后的复盘（「五人台词几乎原地循环、
    # 掌柜该给的坦白拍没有落地」）。根因就是**闸门本身**：
    # [EN] This one comes from the user's retrospective after actually running a full day for the first
    # [EN] time ("the five characters' dialogue loops almost in place,
    # [EN] the confession shot the shopkeeper should have delivered never landed"). The root cause is **the
    # [EN] gate itself**:
    #
    #   ① 张力在**一天之内只升不降** —— 唯一回落的地方是 `on_day_start()`
    #      （跨天那一刻）。一次事件抬升 ~0.10，从 0.30 抬到 0.41 之后，
    #      `tension < 0.4` 当天就再也打不开了。
    #   ② 而"一天"有多长？那次的 `停点.json` 写着 **ticks_today = 391**。
    #      日志侧完全吻合：391 拍里 `director_event` 只被问过 3 次
    #      （19:25 / 19:26 / 19:27，张力 0.30→0.63），**之后 49 分钟零事件**。
    # [EN] ① Tension **only rises within a day, never falls** — the only place it falls is `on_day_start()`
    # [EN] (the moment of crossing days). One event boosts ~0.10, so after going from 0.30 to 0.41,
    # [EN] `tension < 0.4` can never open again for the rest of the day.
    # [EN] ② And how long is "a day"? That time's `停点.json` says **ticks_today = 391**.
    # [EN] The log side matches perfectly: out of 391 ticks, `director_event` was asked only 3 times
    # [EN] (19:25 / 19:26 / 19:27, tension 0.30→0.63), **then 49 minutes with zero events**.
    #
    # ⇒ 判据问的不是"张力会不会回落"（A9 已经在问），而是**那个闸会不会关上**。
    # [EN] ⇒ The criterion is not asking "will tension fall" (A9 already asks that), but **will that gate
    # [EN] close**.
    #
    # ⚠ 判的是 `should_intervene()` 的**返回值**，不是"日志里有没有挑事" ——
    #   后者在"事件被概率闸拦下"时也会绿，那就成了装饰品。
    #   概率那一层用 `DRAMA_LEVEL × CONFLICT_FREQUENCY` 顶到 1.0 / 0.0 来当开关，
    #   于是"会不会挑"只取决于闸门本身。
    # [EN] ⚠ What is judged is the **return value** of `should_intervene()`, not "whether there is any
    # [EN] stirring in the log" —
    # [EN] the latter also goes green when "the event is blocked by the probability gate", which makes it a
    # [EN] decoration.
    # [EN] For the probability layer, use `DRAMA_LEVEL × CONFLICT_FREQUENCY` pushed to 1.0 / 0.0 as a
    # [EN] switch,
    # [EN] so that "whether it stirs" depends only on the gate itself.
    world3 = WorldState()
    db4 = DB(Path(tempfile.mkdtemp(prefix='nws_depth_db_')) / 'gate.db')
    d3 = DirectorEngine(world3, db4)
    old_q = CFG.s('DIRECTOR_QUIET_MINUTES')
    old_dl, old_cf = CFG.s('DRAMA_LEVEL'), CFG.s('CONFLICT_FREQUENCY')
    always = lambda: (CFG.set('DRAMA_LEVEL', '1.0'),
                      CFG.set('CONFLICT_FREQUENCY', '1.0'))   # noqa: E731
    never = lambda: (CFG.set('DRAMA_LEVEL', '0.0'),
                     CFG.set('CONFLICT_FREQUENCY', '1.0'))    # noqa: E731
    world3.clock = GameTime(day=1, minutes=0)
    world3.tension = 0.9                     # 张力**高过** 0.4 那个闸
    # [EN] The gate where tension is **above** 0.4
    CFG.set('DIRECTOR_QUIET_MINUTES', '5')

    # ① 刚发生过事件 + 张力高 ⇒ 不挑（原口径原样保留，没有变成"每拍都挑"）
    # [EN] ① An event just happened + tension high ⇒ do not stir (original wording kept as-is, not turned
    # [EN] into "stir every tick")
    d3._last_event_game_min = d3._game_min()
    never()
    ok('A12c 安静 0 分钟 + 张力 0.9：**不挑事**'
       '（原口径一字未改 —— 别把闸门修成"每拍都挑"）',
       d3.should_intervene() is False, '')

    # ② 安静够久 + 张力还高 ⇒ 必须挑
    # [EN] ② Quiet long enough + tension still high ⇒ must stir
    always()
    world3.clock = GameTime(day=1, minutes=30)      # 安静 30 分钟 ≫ 5
    # [EN] Quiet for 30 minutes ≫ 5
    ok('A12c2 ★★★ 安静超过 `DIRECTOR_QUIET_MINUTES` 之后，**张力还高着也照常挑事**'
       '（这样这一天剩下的几百拍不会"再也没有外部刺激" —— 用户报的原地循环就是它）',
       d3.should_intervene() is True, '')

    # ③ 张力低那一路照旧能挑（改动不能把老路弄丢）
    #   ⚠ 概率那一层要顶到 1.0 —— 设成 0.0 的话 `random.random() < 0` 恒假，
    #     这条会红成"闸门坏了"，其实只是判据自己把概率关了（第一版就写错成 never()）。
    # [EN] ③ The low-tension path can still stir as before (the change must not lose the old path)
    # [EN] ⚠ The probability layer must be pushed to 1.0 — if set to 0.0 then `random.random() < 0` is
    # [EN] always false,
    # [EN] and this test goes red as "the gate is broken" when in fact the criterion itself turned off the
    # [EN] probability (the first version got it wrong as never()).
    always()
    world3.tension = 0.1
    d3._last_event_game_min = d3._game_min()        # 刚发生过事件（安静 0 分钟）
    # [EN] An event just happened (quiet 0 minutes)
    ok('A12c3 张力低于 0.4 时照旧挑事（老路还在，没被新条件顶掉）',
       d3.should_intervene() is True, '')

    # ④ 旋钮真的说了算：设得很大 ⇒ 完全退回旧口径
    # [EN] ④ The knob really decides: set it very large ⇒ fully reverts to the old wording
    always()
    world3.tension = 0.9
    d3._last_event_game_min = d3._game_min() - 600  # 安静 600 分钟
    # [EN] Quiet for 600 minutes
    CFG.set('DIRECTOR_QUIET_MINUTES', '99999')
    ok('A12c4 ★ `DIRECTOR_QUIET_MINUTES` 真的说了算：设得很大 ⇒ 安静再久也不挑'
       '（= 想退回旧行为的人有路可走，不是把新行为焊死）',
       d3.should_intervene() is False, '')
    CFG.set('DIRECTOR_QUIET_MINUTES', old_q)
    CFG.set('DRAMA_LEVEL', old_dl)
    CFG.set('CONFLICT_FREQUENCY', old_cf)

    # ── A12d ★★★ 节点推进要**记下来**（`状态`）──
    # [EN] ── A12d ★★★ Node advancement must be **recorded** (`状态`) ──
    #
    # 原来 `advance_node()` 只改 `current_node`、`状态` 一个字不写，而 `状态`
    # 有**四处**在读 ⇒ 三件看得见的后果全错：
    #   · `结局.md` 的「没走完的进度节点」列出**每一个**节点（用户那份文件里
    #     6 个一个不少地列着，包括早就走完的）；
    #   · 当天落盘的「关键事件」永远是空的；
    #   · `RUN_MODE=story` 的自动收尾判据 `all(状态=='已完成')` **永远为假**。
    # [EN] Originally `advance_node()` only changed `current_node`, writing nothing to `状态`, while `状态`
    # [EN] is read in **four places** ⇒ three visible consequences all wrong:
    # [EN] · The "unfinished progress nodes" in `结局.md` lists **every** node (in the user's file,
    # [EN] all 6 are listed, including ones long since completed);
    # [EN] · The "key events" persisted that day are always empty;
    # [EN] · The auto-wrap-up criterion `all(状态=='已完成')` for `RUN_MODE=story` is **always false**.
    world4 = WorldState()
    d4 = DirectorEngine(world4, db4)
    world4.progress_nodes = [
        {'id': 'N01', '名称': '甲', '完成判据': 'a', '状态': '进行中'},
        {'id': 'N02', '名称': '乙', '完成判据': 'b', '状态': '未开始'},
        {'id': 'N03', '名称': '丙', '完成判据': 'c', '状态': '未开始'},
    ]
    world4.current_node = 'N01'
    new_id = d4.advance_node()
    ok('A12d ★★★ 推进节点时把**走完的那个标成已完成**、下一个标成进行中'
       '（不写的话「结局.md 的未完成节点」「当天的关键事件」'
       '「story 模式自动收尾」三处全是错的）',
       new_id == 'N02'
       and world4.progress_nodes[0]['状态'] == '已完成'
       and world4.progress_nodes[1]['状态'] == '进行中',
       f"new={new_id} 状态={[n['状态'] for n in world4.progress_nodes]}")
    ok('A12d2 ★ 走完的节点**不会**被算进"没走完"那一列（结局.md 就是这么挑的）',
       [n['名称'] for n in world4.progress_nodes
        if n.get('状态') != '已完成'] == ['乙', '丙'],
       str([n['名称'] for n in world4.progress_nodes if n.get('状态') != '已完成']))
    ok('A12d3 ★ 走到最后一个节点时返回 None，且**不越界**（终点不推进）',
       d4.advance_node() == 'N03' and d4.advance_node() is None,
       f"current={world4.current_node}")

    # ── A13 计划 / 前情 的 prompt 片段 ──
    # [EN] ── A13 Prompt fragments for plan / recap ──
    from agent.core import Agent
    a = Agent.__new__(Agent)
    a.world = WorldState()
    a.db = db3
    a.ps = PersonState(name='甲')
    ok('A13 没排计划时 `_plan_line()` 给空串（不留空壳标题）',
       a._plan_line() == '', repr(a._plan_line()))
    a.ps.day_plan = ['去后院看水', '把档整理一遍']
    ok('A13b 排了计划就带 `[今日计划]` 段',
       a._plan_line().startswith('\n[今日计划]') and '看水' in a._plan_line(),
       a._plan_line().replace('\n', '⏎'))
    # ⚠ 这一条必须换一个**空的** DB：`db3` 里 A7 刚写过前情提要，
    #   用它来断言"没有前情提要时给空串"是自相矛盾（判据自己写错了，实测红过）。
    # [EN] ⚠ This one must use a different, **empty** DB: in `db3`, A7 just wrote a recap,
    # [EN] so using it to assert "give an empty string when there is no recap" is self-contradictory (the
    # [EN] criterion itself was wrong, verified red in practice).
    empty_db = DB(Path(tempfile.mkdtemp(prefix='nws_depth_db_')) / 'empty.db')
    a.db = empty_db
    ok('A13c 没有前情提要时 `_story_so_far()` 给空串（不留空壳标题）',
       a._story_so_far() == '', repr(a._story_so_far()))
    a.db = db3
    ok('A13d 有前情提要时按「第 N 天：…」列出',
       '[前情提要]' in a._story_so_far() and '第 2 天' in a._story_so_far(),
       a._story_so_far().replace('\n', '⏎'))

    # ── A14 world_prefix 缓存真的生效、且能失效 ──
    # ⚠ 判据要比**同一个字符串对象**（`is`），不能用 `==` 兜底 —— 内容相等
    #   在"没缓存"时也成立，那样这条判据永远绿（写反例法时才发现的坑）。
    # [EN] ── A14 world_prefix cache really takes effect, and can be invalidated ──
    # [EN] ⚠ The criterion must compare **the same string object** (`is`), not fall back on `==` — content
    # [EN] equality
    # [EN] also holds when "not cached", so this criterion would stay green forever (a pitfall found while
    # [EN] writing counterexamples).
    from world.state import WorldState as WS
    w = WS(worldview_text='临河小城')
    p1 = w.world_prefix()
    ok('A14 `world_prefix()` 结果被缓存（第二次直接返回缓存里的那个串，不重拼）',
       getattr(w, '_prefix_cache', None) is not None and w.world_prefix() is p1, '')
    w.worldview_text = '换了一座城'
    ok('A14b 内容变了缓存**立刻失效**（按内容判等，不是按"改没改过"的标志位）',
       '换了一座城' in w.world_prefix(), w.world_prefix()[:30])

    # ── A15 persona 固定层缓存 ──
    # [EN] ── A15 persona fixed-layer cache ──
    a2 = Agent.__new__(Agent)
    a2.world = WorldState()
    a2.db = db3
    a2.ps = PersonState(name='乙', identity='掌柜')
    a2._persona_key = None
    a2._persona_static = ''
    s1 = a2._persona_prompt()
    a2.ps.current_goal = '把账对平'          # 只动动态层
    # [EN] Only touch the dynamic layer
    s2 = a2._persona_prompt()
    a2.ps.identity = '前朝旧吏'              # 动固定层
    # [EN] Touch the fixed layer
    s3 = a2._persona_prompt()
    ok('A15 persona 分固定层/动态层：改目标不重算固定层，改身份才重算',
       '掌柜' in s1 and '把账对平' in s2 and '前朝旧吏' in s3,
       f'{s1!r} → {s3!r}')


# ══════════════════════════════════════════════════════════════
#  B. 真机（MOCK）：并行决策 / 重复事件拦截 / 跨天三件事
# [EN] B. Real machine (MOCK): parallel decisions / duplicate event interception / three cross-day
# [EN] things
# ══════════════════════════════════════════════════════════════
async def live_checks(tmp: Path) -> None:
    from verify_ui_common import isolate_projects_dir
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim.setup import assemble
    import agent.core as AC
    import director.engine as DE

    isolate_projects_dir(tmp / 'Projects')
    proj = make_project(tmp / '深度')
    run = RunFolder(proj.root, '第1次模拟2026-01-01-00-00').create()
    loop, world, _ = assemble(proj, run)
    world.progress_nodes = []
    from logger import log_dir
    from llm.router import llm
    await llm.ensure_started(log_dir())

    real_chat = AC.llm.chat
    calls: list[str] = []

    def _spy(sleep_purposes: dict[str, float], fixed: dict[str, str] | None = None):
        async def spy(tier, messages, **kw):
            p = kw.get('purpose', '')
            calls.append(p)
            if p in sleep_purposes:
                await asyncio.sleep(sleep_purposes[p])
            if fixed and p in fixed:
                return fixed[p]
            return await real_chat(tier, messages, **kw)
        return spy

    # ── B1 并行决策：用**耗时**取证 ──
    # [EN] ── B1 Parallel decisions: take evidence from **elapsed time** ──
    #
    # ★★ 判据必须写成**差分**，不能写绝对墙钟阈值（2026-10-06 改，并行回归之后）。
    #    原来写的是 `concurrent < 0.55`（B2 是 `tick_cost < 0.57`）—— 空载实测
    #    `并发=0.36s 串行=0.65s`，**裕度只有 0.19s**。一旦机器上有别的进程
    #    （并行回归一次跑 8 个），调度开销把这 0.19s 吃掉就变红 ——
    #    全量并行跑时它就这么偶发红了一次（36/37），而串行复跑又是 37/37。
    #    那种红最坏：它说的是"机器忙"，不是"产品坏了"。
    # [EN] ★★ The criterion must be written as a **difference**, not an absolute wall-clock threshold
    # [EN] (changed 2026-10-06, after parallel regression).
    # [EN] It originally said `concurrent < 0.55` (B2 was `tick_cost < 0.57`) — measured idle
    # [EN] `并发=0.36s 串行=0.65s`, **margin only 0.19s**. Once there are other processes on the machine
    # [EN] (the parallel regression runs 8 at once), scheduling overhead eats that 0.19s and it goes red —
    # [EN] during a full parallel run it went intermittently red exactly like that (36/37), while a serial
    # [EN] rerun was 37/37 again.
    # [EN] That kind of red is the worst: it says "the machine is busy", not "the product is broken".
    #
    #    现在改成问**这件事本身**：并发比串行**省下了多少**？
    #      · 正确的实现：省下 ≈ 一次调用的时间；
    #      · 串行的实现：省下 ≈ 0（这正是要抓的坏法）。
    #    负载对两边**是加法**，所以差分稳；绝对阈值不稳。
    #    同时把夹具的延时从 0.30 抬到 0.60：信号大一倍，噪声占比就小一半
    #    （代价是这一支多跑 ~3 秒，换一条不会说谎的判据，值）。
    # [EN] Now it is changed to ask **about this thing itself**: how much does parallel **save** over
    # [EN] serial?
    # [EN] · Correct implementation: saves ≈ the time of one call;
    # [EN] · Serial implementation: saves ≈ 0 (this is exactly the bad case to catch).
    # [EN] Load is **additive** for both sides, so the difference is stable; absolute thresholds are not.
    # [EN] Also raise the fixture delay from 0.30 to 0.60: the signal doubles, so the noise fraction
    # [EN] halves.
    # [EN] (The cost is that this branch runs ~3 seconds longer, in exchange for a criterion that won't
    # [EN] lie, which is worth it).
    on_stage = [a for a in loop.agents if a.ps.is_active()]
    ok('B1 夹具就绪：至少两位前台人物', len(on_stage) >= 2, len(on_stage))
    AC.llm.chat = _spy({'agent_decide': 0.60})
    try:
        t0 = time.monotonic()
        await asyncio.gather(*(a.decide() for a in on_stage[:2]))
        concurrent = time.monotonic() - t0
        t0 = time.monotonic()
        for a in on_stage[:2]:
            await a.decide()
        serial = time.monotonic() - t0
    finally:
        AC.llm.chat = real_chat
    ok('B1b ★ 两个人同时决策省下 ≈ 一次调用的时间（不是两个相加）'
       '—— 判的是**差分**，不是绝对秒数',
       serial > 0.9 and (serial - concurrent) > 0.35,
       f'并发={concurrent:.2f}s 串行={serial:.2f}s 省下={serial - concurrent:.2f}s'
       f'（阈值 省下>0.35）')

    # ── B2 真的走 _tick：它内部用的是 gather ──
    # [EN] ── B2 really goes through _tick: it uses gather internally ──
    AC.llm.chat = _spy({'agent_decide': 0.60})
    try:
        t0 = time.monotonic()
        await loop._tick(1)
        tick_cost = time.monotonic() - t0
    finally:
        AC.llm.chat = real_chat
    # 同一个道理：跟"两次串行决策"比**省下的差额**，不跟绝对秒数比。
    # [EN] Same reasoning: compare against the **saved delta** versus "two serial decisions", not against
    # [EN] absolute seconds.
    ok('B2 ★ `RunLoop._tick` 内部的决策是并发的（比两次串行省下 ≈ 一次调用）',
       (serial - tick_cost) > 0.35,
       f'一拍={tick_cost:.2f}s 串行={serial:.2f}s 省下={serial - tick_cost:.2f}s')

    # ── B3 重复事件被拦 ──
    # [EN] ── B3 duplicate events are blocked ──
    #
    # ★★ 把三个"率"旋钮**钉死**（2026-10-06）。
    #    这一段（B3 / B3b / B4）要验的是**去重**和**高潮覆盖**，**不是节奏闸门** ——
    #    但夹具里的事件类型恰好是**揭示型**（`秘密泄露` / `伏笔激活`），
    #    而 `_rate_gate()` 对揭示型要掷一次骰子：
    # [EN] ★★ **Pin down** the three "rate" knobs (2026-10-06).
    # [EN] This section (B3 / B3b / B4) is meant to verify **deduplication** and **climax coverage**, **not
    # [EN] the pacing gate** ——
    # [EN] and `_rate_gate()` rolls a die for reveal types:
    #
    #        elif "秘密" in etype or "伏笔" in etype:
    #            rate = CFG.f("REVEAL_PACING")      # .env 默认 0.5
    #            if random.random() >= rate:        # ← 一半概率直接返回 None
    # [EN] rate = CFG.f("REVEAL_PACING")      # .env default 0.5
    # [EN] if random.random() >= rate:        # ← half the time it returns None directly
    #                return None
    #
    #    于是这几条判据**约一半概率自己变红**。实测（同一份代码连跑 6 次、串行）：
    # [EN] So these criteria **go red on their own about half the time**. Measured (same code run 6 times
    # [EN] serially):
    #        exit=2 35/37 · exit=2 36/37 · exit=2 36/37 · exit=0 37/37
    #        · exit=2 36/37 · exit=0 37/37
    #    红的是 `B3b 注入=None 调用=1` 与 `B4 注入=None` —— 全是掷骰，不是产品坏了。
    # [EN] the red ones are `B3b 注入=None 调用=1` and `B4 注入=None` —— all dice rolls, not a broken product.
    #
    #    ⚠ 这是套件里最坏的一种红：**红的概率比绿还高**，会把人训练成"看到红先怀疑
    #    测试"。所以这里的做法不是"多跑几次"，而是**把这个变量从场景里拿掉**：
    #    设成 1.0 = 揭示型一律放行，让判据只盯着它自己要验的那件事。
    # [EN] ⚠ This is the worst kind of red in a suite: **more likely red than green**, which trains people
    # [EN] to "see red and first suspect
    # [EN] the test". So the approach here is not "run it a few more times", but **remove this variable
    # [EN] from the scenario**:
    # [EN] set it to 1.0 = reveal types always pass, so the criteria only focus on what they are meant to
    # [EN] verify.
    #
    #    ⚠ 「闸门真的会拦」**没有因此失去覆盖** —— 那条判据在 `tools/verify_craft.py`
    #    里（它把 `REVEAL_PACING` 设成 0 再断言事件被拦下）。两处各管一段，
    #    不要在这支脚本里重复验闸门，也不要为此把 `REVEAL_PACING` 调回 0.5。
    # [EN] ⚠ "The gate really blocks" **has not lost coverage because of this** —— that criterion is in
    # [EN] `tools/verify_craft.py`
    # [EN] (it sets `REVEAL_PACING` to 0 and then asserts the event is blocked). Each covers its own part,
    # [EN] don't re-verify the gate in this script, and don't set `REVEAL_PACING` back to 0.5 for this.
    _saved_pacing = CFG.raw('REVEAL_PACING')
    CFG.set('REVEAL_PACING', '1')
    loop.db.add_event('E900', '更夫来报：后巷出了事，地上有血', '外部刺激', 1, [], 'N01')
    same = json.dumps({'是否介入': True, '类型': '外部刺激',
                       '事件': '后巷出了事，更夫来报，地上有血',
                       '涉及人物': [], '强度': 0.5, '理由': '演示'},
                      ensure_ascii=False)
    calls.clear()
    AC.llm.chat = _spy({}, fixed={'director_event': same})
    try:
        ev = await loop.director._inject_event()
    finally:
        AC.llm.chat = real_chat
    ok('B3 ★ 与最近事件太像（换个说法）→ 重生成一次；仍然像 → **不注入**',
       ev is None and calls.count('director_event') == 2,
       f'注入={ev} director_event 调用次数={calls.count("director_event")}')

    # 反例：完全不同的新事件照常注入
    # [EN] Counter-example: a completely different new event is injected as usual
    calls.clear()
    fresh = json.dumps({'是否介入': True, '类型': '秘密泄露',
                        '事件': '账本夹层里的那封信被风吹落，落在三个人中间',
                        '涉及人物': [], '强度': 0.6, '理由': '演示'},
                       ensure_ascii=False)
    AC.llm.chat = _spy({}, fixed={'director_event': fresh})
    try:
        ev2 = await loop.director._inject_event()
    finally:
        AC.llm.chat = real_chat
    ok('B3b 反例：**新**事件照常注入（判据不是"一律不注入"）',
       ev2 is not None and calls.count('director_event') == 1,
       f'注入={ev2.description if ev2 else None} 调用={calls.count("director_event")}')

    # ── B4 高潮日**强制**注入（不受张力门槛限制）──
    # ⚠ 这里必须换一句**全新的**事件描述：B3b 刚把 `fresh` 那句话写进了事件表，
    #   复用同一句会被重复度检测拦下（`_inject_event` 返回 None），
    #   于是落到"停滞自救"分支，判据就会红成一片（实测踩过）。
    world.tension = 0.95                     # 远高于 0.4 —— 旧逻辑下这条路是死的
    # [EN] ── B4 climax day **forced** injection (not subject to the tension threshold) ──
    # [EN] ⚠ Here you must switch to a **brand-new** event description: B3b just wrote the `fresh` sentence
    # [EN] into the event table,
    # [EN] reusing the same sentence gets blocked by duplicate detection (`_inject_event` returns None),
    # [EN] then it falls into the "stagnation self-rescue" branch, and the criteria go red all over
    # [EN] (measured, been there).
    # [EN] Far above 0.4 —— under the old logic this path was dead
    world.clock = type(world.clock)(day=5, minutes=0)
    world.game_day = 5
    loop.director._climax_fired_day = 0
    CFG.set('CLIMAX_EVERY_DAYS', '5')
    climax_ev = json.dumps({'是否介入': True, '类型': '伏笔激活',
                            '事件': '那本没人买走的旧书，扉页上多出一行陌生的字',
                            '涉及人物': [], '强度': 0.7, '理由': '演示'},
                           ensure_ascii=False)
    calls.clear()
    AC.llm.chat = _spy({}, fixed={'director_event': climax_ev})
    try:
        ev3 = await loop.director.on_tick()
    finally:
        AC.llm.chat = real_chat
    ok('B4 ★ 高潮日即使张力 0.95 也照样挑事（旧逻辑 `tension < 0.4` 把它永远关死了）',
       ev3 is not None and ev3.event_type != '导演自救',
       f'注入={ev3.description[:28] if ev3 else None} 类型={ev3.event_type if ev3 else None}')
    ok('B4b 高潮日会把张力抬到曲线目标（不是干等它自己掉）',
       world.tension >= 0.6, round(world.tension, 3))
    # 还原（B5 起与节奏闸门无关了，别把夹具状态留给后面的判据）
    # [EN] Restore (from B5 on it's unrelated to the pacing gate, don't leave fixture state for later
    # [EN] criteria)
    CFG.set('REVEAL_PACING', _saved_pacing)

    # ── B5 跨天：前情提要 + 计划 + 张力回落 ──
    # [EN] ── B5 cross-day: recap + plan + tension falloff ──
    world.clock = type(world.clock)(day=2, minutes=0)
    world.game_day = 2
    loop._current_day = 2
    world.tension = 0.9
    await loop._summarize_day(['掌柜在柜台后擦了一夜的壶。', '信没人来认领。'])
    sums = loop.db.get_summaries(3)
    ok('B5 ★ 跨天时把这一天压成一条前情提要，落在 DB 里',
       any(s['game_day'] == 2 for s in sums), [s['text'][:24] for s in sums])
    before_t = world.tension
    loop.director.on_day_start()
    ok('B5b 跨天时张力回落', world.tension < before_t,
       f'{before_t:.2f} → {world.tension:.2f}')
    await loop._plan_day()
    planned = [a for a in loop.agents if getattr(a.ps, 'day_plan', None)]
    ok('B5c ★ 跨天时给前台人物排了今日计划（`make_plan` 以前从没被调用过）',
       len(planned) == len([a for a in loop.agents if a.ps.is_active()]),
       [(a.name, len(a.ps.day_plan)) for a in loop.agents])

    # ── B6 决策 prompt 里两样都在 ──
    # [EN] ── B6 both are present in the decision prompt ──
    seen: dict = {}

    async def pick(tier, messages, **kw):
        seen[kw.get('purpose', '')] = '\n'.join(str(m.get('content', ''))
                                                for m in messages)
        return await real_chat(tier, messages, **kw)

    AC.llm.chat = pick
    try:
        await loop.agents[0].decide()
    finally:
        AC.llm.chat = real_chat
    p = seen.get('agent_decide', '')
    ok('B6 ★ 决策 prompt 里同时带上了 `[前情提要]` 与 `[今日计划]`',
       '[前情提要]' in p and '[今日计划]' in p,
       [x for x in p.splitlines() if x.startswith('[')][:6])

    # ── B7 计划 prompt 也带前情与规则（不是闭着眼睛排）──
    # [EN] ── B7 the plan prompt also carries the recap and rules (not planning blind) ──
    seen.clear()
    AC.llm.chat = pick
    try:
        await loop.agents[0].make_plan()
    finally:
        AC.llm.chat = real_chat
    pp = seen.get('plan', '')
    ok('B7 排计划的 prompt 里带上了前情提要（按已发生的事来排今天）',
       '[前情提要]' in pp, [x for x in pp.splitlines() if x.startswith('[')][:4])


async def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_depth_'))
    try:
        logic_checks()
        await live_checks(tmp)
    except BaseException:                                    # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()
        print(report['fatal'])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'sim_depth_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n推演深度验证：{len(report["checks"]) - len(bad)}/{len(report["checks"])}')
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    print('报告：assets/screenshots/sim_depth_report.json')
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
