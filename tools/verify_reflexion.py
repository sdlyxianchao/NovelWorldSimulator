# -*- coding: utf-8 -*-
"""判据：Reflexion 架构（验收层 / 反思循环 / 修复合约 / 全书检测）。

**纯逻辑，不起窗口、不调模型、不读用户数据**（夹具全部内联或来自 `samples/`）。

这一套判据要回答的不是"函数能不能跑"，而是**四个历史毛病有没有被结构性地堵住**：

| 历史毛病 | 对应的判据 |
|---|---|
| 修完"太碎"变成"太长"（0→2） | A2 / B1（跨类退化一律退回） |
| 同分时保留原文、把整轮修改丢掉 | A8 / A9 / B3（archive 三级排序） |
| 把整段砍掉、毛病当然归零 | A4（canary：满分本身可疑） |
| 加一类毛病要改四处、漏一处没人修 | C1 / C2 / C3（注册表 + 覆盖判据） |

⚠ 每条判据都问过一句"**我要是重构这段代码，它还会红吗**"（§42.7 的教训）：
  凡是能用"真跑一遍、真渲染一次"回答的，就不去 grep 源码。
[EN] Checks for the Reflexion architecture: the verdict layer, the loop, the repair
[EN] registry and the book-level detectors. Pure logic; fixtures are inline or come from
[EN] `samples/`, and every assertion tests behaviour rather than source text.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from crew import critic as CR             # noqa: E402
from crew import global_checks as GC      # noqa: E402
from crew import prose_flow as PF         # noqa: E402
from crew import reflexion as RX          # noqa: E402
from crew import repair_recipes as REC    # noqa: E402
from crew import verdict as V             # noqa: E402

CHECKS: list[tuple[bool, str, str]] = []


def ok(name: str, cond: bool, detail: str = '') -> None:
    CHECKS.append((bool(cond), name, detail))


# ══════════════════════════ 夹具 ══════════════════════════

#: 一段"太碎"的正文（每句一件事、没有分句）—— `flat_span_issues` 会判它。
_FLAT = ('岛村倚着窗框。驹子坐在火钵旁。炭火映着她半边脸颊。窗外的雪把脚步声吞掉了。'
         '更鼓从巷子那头过来。她抬手拨了拨灯芯。影子铺在榻榻米上。')

#: 一段"憋气"的正文（长句过半 / 有超长句）—— `long_span_issues` 会判它。
_LONG = ('他心里清楚这时候说什么都不合适，所以一直没有开口的意思。'
         '窗纸外面的雪把整条街的脚步声都吞掉了，连更鼓也不真切。'
         '驹子把手从袖子里抽出来又放回去，在膝上按了一下才松开。')

#: 一段干净的正文（两种都不判）。
_CLEAN = ('她抬手拨了拨灯芯，火苗一跳，影子在榻榻米上晃出细碎的边，一直铺到纸门底下。'
          '“炭还旺么。”驹子低声问，把手从袖子里抽出来，又放回去。'
          '岛村没有答，只把窗子推开一条缝，让雪气灌进来。')


def _score_counts(text: str) -> dict:
    return dict(PF.prose_issue_count(text))


# ══════════════════════════ A 组：验收层 ══════════════════════════

def group_a() -> None:
    print('\n── A 验收层（判定权归代码，不归写稿的那一方）──', flush=True)

    # A1 真正的改进要收
    d1 = V.compare(_FLAT, _CLEAN, label='平铺段')
    ok('A1 ★★★ 真的改好了（太碎 → 有分句）⇒ **收**',
       d1.level == 'accept' and d1.applied,
       f'{d1.level} · {d1.why}')

    # A2 修好一类、把另一类改多 ⇒ 退回（这是"病换到另一头"的根治）
    d2 = V.compare(_FLAT, _LONG, label='平铺段')
    up_has_long = '憋气段' in d2.up
    ok('A2 ★★★ **跨类退化一律退回**：太碎改好了、但把憋气段改多了 ⇒ 拒',
       d2.level == 'reject' and up_has_long,
       f'{d2.level} · {d2.why}')

    # A3 台词变少 ⇒ 硬约束
    src = '她问：“炭还旺么。”他说：“旺着。”她又问：“要不要添。”'
    bad = '她问炭还旺不旺，他说旺着，她又问要不要添。'
    d3 = V.compare(src, bad, label='重复')
    ok('A3 ★★★ **台词不许变少**（并进叙述就没人替角色说话）⇒ 违反硬约束',
       d3.level == 'reject' and any('台词' in x for x in d3.violated),
       f'{d3.violated}')

    # A4 canary：毛病清零、但内容掉了一成以上 ⇒ 判"删达标"。
    #    ⚠ 分数要**落在硬约束之外**（字数比 0.93 > 0.85），否则先被 `_invariants`
    #      拦住，canary 这条判据就测不到它自己（反例法 M3 的第一版就是这样）。
    _o4 = V.Score(counts={'平铺段': 4}, zh=300, speeches=4, sentences=20)
    # 265 落在"硬约束之外（>255）、canary 之内（<270）"那条窄带里 ——
    # 这条判据只有在这个区间才有意义。
    _n4 = V.Score(counts={}, zh=265, speeches=4, sentences=20)
    d4 = V.compare_scores(_o4, _n4, label='平铺段')
    ok('A4 ★★★ **满分本身可疑**：毛病清零但字数掉了一成 ⇒ 拒（这是"删达标"）',
       d4.level == 'reject' and bool(d4.suspect),
       f'{d4.level} · {d4.suspect or d4.violated}')

    # A5 灌水 1.5 倍 ⇒ 拒（构造分数：造一段"恰好 1.5 倍"的中文不可控）
    _o5 = V.Score(counts={'重复': 1}, zh=300, speeches=4, sentences=20)
    _n5 = V.Score(counts={'重复': 0}, zh=520, speeches=4, sentences=20)
    d5 = V.compare_scores(_o5, _n5, label='重复')
    ok('A5 ★★ 字数灌到原稿 1.45 倍以上 ⇒ 拒（那不是改写，是加戏）',
       d5.level == 'reject' and any('灌水' in x for x in d5.violated),
       f'{d5.violated}')

    # A6 一个字没动 ⇒ 拒（且不该记一条教训）
    d6 = V.compare(_CLEAN, _CLEAN, label='重复')
    ok('A6 ★★ 一个字都没动 ⇒ 拒（免得把"无改动"也记成一条教训）',
       d6.level == 'reject' and '没动' in d6.why, d6.why)

    # A7 净收益为正、单类退化 1 ⇒ 只给候选，**不直接替换**
    #    构造分数：平铺 3→0、重复 1→1、憋气 0→1。加权 4.0 → 3.5，
    #    但憋气多了一处 ⇒ 不许直接采纳，只进 archive。
    _o7 = V.Score(counts={'平铺段': 3, '重复': 1}, zh=300, speeches=5, sentences=22)
    _n7 = V.Score(counts={'平铺段': 0, '重复': 1, '憋气段': 1}, zh=300,
                  speeches=5, sentences=22)
    d7 = V.compare_scores(_o7, _n7, label='平铺段')
    ok('A7 ★★★ 净收益为正但有一类轻微变差 ⇒ 降级为 `tradeoff`（候选，'
       '**不直接替换正文**）',
       d7.level == 'tradeoff',
       f'{d7.level} · {d7.why}')
    if d7.level == 'tradeoff':
        ok('A7b ★★ 而且 `applied` 必须是 False（候选 ≠ 已采纳）',
           d7.applied is False, f'applied={d7.applied}')

    # A8/A9 archive 排序：同 weighted 时，台词多的 / 字数多的胜出
    s_short = V.Score.of('她问：“炭还旺么。”')
    s_long = V.Score.of('她问：“炭还旺么。”他说：“旺着。”她又问：“要不要添。”')
    ok('A8 ★★★ archive 排序：**同毛病数时台词多的那一版更好**'
       '（旧代码 `if after < best` 在同分时把整轮修改丢掉）',
       V.better((s_long, 'a'), (s_short, 'b')),
       f'台词 {s_short.speeches} vs {s_long.speeches}')

    s_big = V.Score.of(_CLEAN + '她又问了一遍，他没有答。')
    ok('A9 ★★ archive 排序：同毛病数、同台词数时**字数多的**更好（不许悄悄缩水）',
       V.better((s_big, 'a'), (s_short, 'b')),
       f'字数 {s_short.zh} vs {s_big.zh}')


# ══════════════════════════ B 组：反思循环 ══════════════════════════

async def _mk_step(returns: str, calls: list):
    """造一个"每次返回固定文本"的步骤，并记下被调用了几次。"""
    async def _step(text: str) -> str:
        calls.append(len(text))
        return returns
    return _step


def group_b() -> None:
    print('\n── B 反思循环（收改进 / 拒退化 / 写教训 / 取最优）──', flush=True)

    async def main():
        # B1 三步，顺序是**坏的在先、好的在后** —— 这也是真实形态：
        #    某一步改坏了被退回（正文不动），下一步再改好。
        #    ⚠ 第一版把"改进"放第一，它一让步数清零就 `break` 了，
        #      后面两步根本没跑，于是"有没有拒绝"测的是空气。
        calls: list = []
        steps = [
            (await _mk_step(_LONG, calls), '平铺段', 1),       # 平铺修好了、憋气变多
            (await _mk_step(_CLEAN, calls), '平铺段', 1),      # 真的改好
        ]
        res = await RX.reflect(_FLAT, steps, trials=1, patience=1, tag='判据B1')
        ok('B1 ★★★ 一轮里"改进的被收、退化的被拒"同时成立',
           res.accepted >= 1 and res.rejected >= 1,
           f'收 {res.accepted} / 拒 {res.rejected} · {res.summary()}')
        ok('B1b ★★★ 最终稿**不比原文差**（退化版不许混进来）',
           V.Score.of(res.text).weighted <= V.Score.of(_FLAT).weighted,
           f'{V.Score.of(_FLAT).weighted} → {V.Score.of(res.text).weighted}')

        # B2 教训进了记忆，且带具体差异与原句
        mem = res.memory
        ok('B2 ★★★ 被拒的尝试变成**一条带类别的教训**（下一轮看得见）',
           mem is not None and len(mem) >= 1
           and any('憋气段' in (x.why or '') or '憋气段' in (x.label or '')
                   for x in mem.items),
           '；'.join(x.one_line()[:44] for x in (mem.items if mem else [])[:2]))
        ok('B2b ★★ 教训的 `advice` 是**动作句**，不是"注意质量"这种空话',
           all(len(x.advice) >= 8 for x in (mem.items if mem else [])),
           '')
        ok('B2c ★★ 教训带**原句锚点**（没有锚点，模型不知道该看哪儿）',
           any(x.span for x in (mem.items if mem else [])),
           str([x.span[:18] for x in (mem.items if mem else [])][:2]))

        # B3 archive：第 1 轮改进、第 2 轮"同分且更差"⇒ 必须返回第 1 轮那版
        calls2: list = []
        good = await _mk_step(_CLEAN, calls2)
        worse = await _mk_step(_FLAT, calls2)
        res2 = await RX.reflect(_FLAT, [(good, '平铺段', 1)], trials=1,
                                patience=1, tag='判据B3')
        ok('B3 ★★★ **取 archive 里最好的那一版**（不是最后跑出来的那一版）',
           res2.text.strip() == _CLEAN.strip(),
           f'返回 {"改好的" if res2.text.strip() == _CLEAN.strip() else "原文"}')

        # B3b archive 的排序**不只看"有没有交出新东西"**：一个被降级成
        #     tradeoff 的候选（加权 4.0→3.5，但憋气多一处）整体仍更优，
        #     最终应当被选为最优 —— 这是"候选备选"这套设计的全部意义。
        _lo = V.Score(counts={'平铺段': 3, '重复': 1}, zh=300, speeches=5, sentences=22)
        _hi = V.Score(counts={'平铺段': 0, '重复': 1, '憋气段': 1}, zh=300,
                      speeches=5, sentences=22)
        ok('B3b ★★★ archive 排序认的是**加权**：tradeoff 候选更优时会被选中',
           V.better((_hi, 'b'), (_lo, 'a')), f'{_lo.weighted} vs {_hi.weighted}')

        # B4 已经干净的类被跳过
        res3 = await RX.reflect(_CLEAN, [(worse, '平铺段', 1)], trials=2,
                                patience=1, tag='判据B4')
        ok('B4 ★★ 这一类已经是 0 ⇒ 跳过它（重跑只会添乱）',
           res3.trials == 0 or res3.accepted == 0,
           f'trials={res3.trials} accepted={res3.accepted} stop={res3.stop}')

        # B5 边界：空文本 / 没步骤
        r5a = await RX.reflect('', [(worse, '平铺段', 1)], trials=2)
        r5b = await RX.reflect(_FLAT, [], trials=2)
        ok('B5 ★★ 空文本 / 没有步骤 ⇒ 安全返回，不抛',
           r5a.text == '' and r5b.text == _FLAT, f'{r5a.stop} / {r5b.stop}')

        # B6 步骤抛异常不中断整轮
        async def boom(_text: str) -> str:
            raise RuntimeError('故意炸')
        # 两个 step 必须**同一类**，否则第二个会被"这一类已经是 0"跳过，
        # 测到的就不是"异常隔离"而是"跳过规则"。
        r6 = await RX.reflect(_FLAT, [(boom, '平铺段', 1),
                                      (good, '平铺段', 1)], trials=1, patience=1)
        ok('B6 ★★★ 某一步炸掉 ⇒ 其余步骤照常跑（一步失败不许拖垮整轮）',
           r6.text.strip() == _CLEAN.strip(),
           f'accepted={r6.accepted} rejected={r6.rejected}')

        # B7 patience：连续没改善就停
        async def same(text: str) -> str:
            return text
        r7 = await RX.reflect(_FLAT, [(same, '平铺段', 1)], trials=5, patience=1)
        ok('B7 ★★ 一直没改善 ⇒ 按 `patience` 早停（不烧钱）',
           r7.trials <= 2 and '改善' in r7.stop, f'{r7.trials} 轮 · {r7.stop}')

        # B8 教训库有界
        mem8 = RX.Memory(cap=4)
        for i in range(20):
            mem8.add(RX.Lesson(label='平铺段', why=f'第 {i} 次', advice='改短一点'))
        ok('B8 ★★ 教训库**有界**（无界记忆最后会把上下文吃光）',
           len(mem8) <= 4, f'{len(mem8)} 条 / cap=4')

        # B9 落盘往返
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / '教训.jsonl'
            mem9 = RX.Memory(cap=8)
            mem9.add(RX.Lesson(label='重复', why='改多了', advice='只改点名那处',
                               span='“炭还旺么。”'))
            mem9.save(p)
            back = RX.Memory(cap=8)
            n = back.load(p)
            ok('B9 ★ 教训库能落盘/读回（导出关口要跨天沿用，也要给人查）',
               n == 1 and back.items[0].label == '重复'
               and back.items[0].span == '“炭还旺么。”', f'{n} 条')

        # B10 空记忆的 brief 必须是空串（保证提示词逐字不变）
        ok('B10 ★★★ 空记忆 ⇒ `brief()` 返回空串（提示词与旧版逐字一致）',
           RX.Memory().brief() == '', repr(RX.Memory().brief()))

    asyncio.run(main())


# ══════════════════════════ C 组：架构 ══════════════════════════

def group_c() -> None:
    print('\n── C 修复合约（加一类毛病只改一处）──', flush=True)

    # C1 顺序 == 老实现（老顺序是十几轮真跑调出来的，不能重排）
    # ★★ 2026-10-28：新增的 `_fix_dialogue_tags`（确定性删副词）排在最前 ——
    #   "先删后写"是这张表自己的排序纪律（删不会写进新东西，所以要排在
    #   需要模型的重写之前）。所以这条判据现在钉的是**老八步的相对顺序一个没动**
    #   ＋ 新增那一步**必须在第一位**（它一旦排到重写类之后，"先删后写"就废了）。
    #   ⚠ 别把 `want` 整串换成"九步的新顺序" —— 那等于把"老顺序没动"这条
    #     判据自己删掉：以后谁重排老八步，这里也跟着改一下就能绿。
    # [EN] ★★ 2026-10-28: the new deterministic `_fix_dialogue_tags` sits first, per this
    # [EN] table's own "delete before rewrite" rule. So the check now pins **the old eight's
    # [EN] relative order** plus **the new one must be first**. Replacing `want` wholesale
    # [EN] with a new nine-step list would delete the guard itself.
    want_old = ['_fix_topic_spin', '_fix_answer_drift', '_fix_prop_cycle',
                '_fix_plausibility', '_fix_flat_paragraphs', '_fix_repeats',
                '_fix_crowded', '_fix_meta_narration']
    want = ['_fix_dialogue_tags', '_fix_slop'] + want_old
    got = [r.attr for r in REC.ordered()]
    # ⚠ 2026-10-28 又搬了一次：新增的确定性剥离从**一步**变成**两步**
    #   （`_fix_dialogue_tags` 之外又加了 `_fix_slop`），
    #   于是"剔掉新增的、剩下的必须等于老八步"这句里的"剔掉"也要剔两个 ——
    #   只剔一个 ⇒ 剩下九个 ⇒ 与老八步比不上 ⇒ 红。
    #   这正是本项目记过的：**口径一改，判据的刀也要跟着搬。**
    _NEW = ('_fix_dialogue_tags', '_fix_slop')
    ok('C1 ★★★ 老八步的相对顺序**一个位置都没动**，且新增的确定性剥离排在最前',
       got == want and [x for x in got if x not in _NEW] == want_old,
       ' / '.join(got))

    keys = list(PF.prose_issue_count(_CLEAN).keys())
    ok('C2 ★★★ **每一类数得出来的毛病都有人负责**（漏一类就报红，'
       '而不是等读代码才发现）',
       REC.uncovered(keys) == [], f'没人负责：{REC.uncovered(keys)}')
    ok('C3 ★★ 反过来：登记过的类都在计数表里（名字写错/检测器漏了也报红）',
       REC.extra(keys) == [], f'数不出：{REC.extra(keys)}')

    # C4 每步候选数：确定性动作 1 个，改写类 ≤2（成本是线性的）
    by_attr = {r.attr: r for r in REC.RECIPES}
    ok('C4 ★★ 确定性剥离只给 1 个候选、改写类 ≤2（候选数线性花钱）',
       by_attr['_fix_meta_narration'].n_best == 1
       and all(r.n_best <= REC.MAX_N_BEST for r in REC.RECIPES)
       and by_attr['_fix_answer_drift'].n_best == 2,
       str({r.attr: r.n_best for r in REC.RECIPES}))

    # C5 `_check_round_steps` 真的从注册表读（改注册表就改结果）
    from crew import agents as A
    obj = A.Novelist.__new__(A.Novelist)
    names = [getattr(fn, '__name__', '') for fn, _lbl in obj._check_round_steps()]
    ok('C5 ★★★ 生产路径的步骤表**就是注册表**（不是另抄一份）',
       names == want, ' / '.join(names))
    ok('C5b ★★ 两条路径都还在：新 `_checkup` 分发 + 旧 `_checkup_legacy` 保留',
       hasattr(obj, '_checkup') and hasattr(obj, '_checkup_legacy')
       and hasattr(obj, '_checkup_reflexion'), '')

    # C5c 分发层真的按开关走 —— 用**打桩的两个实现**数一下谁被调了。
    #     这条比"两个方法都在"结实：后者在开关接反时照样绿。
    import asyncio as _aio

    async def _which(flag: str) -> list[str]:
        from config import CFG
        old = CFG.s('PROSE_REFLEXION')
        CFG.set('PROSE_REFLEXION', flag)
        seen: list[str] = []
        obj2 = A.Novelist.__new__(A.Novelist)

        # ⚠ 用 `**kw` 而不是照抄真实签名（2026-10-25）：这条判据守的是
        #   "开关决定走哪条路"，不是"参数表长什么样"。照抄签名的话，
        #   产品每加一个可选参数（例如 `style_rounds`）这里就崩，
        #   而崩掉的原因是**判据钉了实现形式**，不是产品坏了。
        # [EN] Use `**kw` instead of mirroring the real signature: this check guards
        # [EN] "the switch decides which path", not the parameter list. Mirroring it means every
        # [EN] new optional product parameter breaks the check for the wrong reason.
        async def _reflex(text, **kw):
            seen.append('reflexion')
            return text

        async def _legacy(text, **kw):
            seen.append('legacy')
            return text

        obj2._checkup_reflexion = _reflex
        obj2._checkup_legacy = _legacy
        try:
            await obj2._checkup('岛村倚着窗框。驹子坐在火钵旁。', rounds=1)
        finally:
            CFG.set('PROSE_REFLEXION', old or 'true')
        return seen

    _on = _aio.run(_which('true'))
    _off = _aio.run(_which('false'))
    ok('C5c ★★★ 开关**真的决定走哪条路**（`PROSE_REFLEXION` 开 → Reflexion，'
       '关 → 旧路径）',
       _on == ['reflexion'] and _off == ['legacy'], f'开={_on} 关={_off}')

    # C6 hint 通道：没反思时零回归
    base = PF.rewrite_prompt('她坐在火钵旁。炭火映着她的脸。')
    PF.reset_reflect_hint(PF.set_reflect_hint(''))
    same = PF.rewrite_prompt('她坐在火钵旁。炭火映着她的脸。')
    tok = PF.set_reflect_hint('上一轮把憋气段改多了，这次只改点名那处')
    hinted = PF.apply_hint(PF.rewrite_prompt('她坐在火钵旁。炭火映着她的脸。'))
    PF.reset_reflect_hint(tok)
    after = PF.rewrite_prompt('她坐在火钵旁。炭火映着她的脸。')
    ok('C6 ★★★ 没有反思时 `rewrite_prompt` **逐字不变**（改了但零回归）',
       same == base and after == base, f'{len(base)} 字')
    ok('C6b ★★★ 有反思时它真的进了提示词（Reflexion 的"语言反馈"通道）',
       hinted != base and '上一轮把憋气段改多了' in hinted, f'{len(hinted)} 字')
    ok('C6c ★★ 而且是在**末尾**追加（约束类内容放最后才压得住前面的示范）',
       hinted.rstrip().endswith('这次只改点名那处'), hinted[-26:].replace('\n', ' '))

    # C7 7 个改写调用点都接上了 hint（真读控制流：语料里每个 *_rewrite_prompt
    #    都必须包在 apply_hint 里 —— 不 grep 字符串，检查"调用形态"）
    import ast as _ast
    src = (APP / 'crew' / 'agents.py').read_text(encoding='utf-8')
    tree = _ast.parse(src)
    rewrite_calls, wrapped = 0, 0
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Call):
            continue
        fn = node.func
        name = getattr(fn, 'attr', '') or getattr(fn, 'id', '')
        if name.endswith('_rewrite_prompt'):
            rewrite_calls += 1
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Call):
            continue
        fn = node.func
        if (getattr(fn, 'attr', '') or getattr(fn, 'id', '')) != 'apply_hint':
            continue
        inner = node.args[0] if node.args else None
        if isinstance(inner, _ast.Call):
            f2 = inner.func
            nm = getattr(f2, 'attr', '') or getattr(f2, 'id', '')
            if nm.endswith('_rewrite_prompt'):
                wrapped += 1
    ok('C7 ★★★ **所有改写调用都带上了反思**（漏一处，那一类就学不到教训）',
       rewrite_calls > 0 and wrapped == rewrite_calls,
       f'{wrapped}/{rewrite_calls}')


# ══════════════════════════ D 组：全书检测 ══════════════════════════

def group_d() -> None:
    print('\n── D 全书检测（先量真人，再上真跑）──', flush=True)

    # D1/D2 真人零命中 —— 铁律：凡"多不多"的规则先量真人分布
    base = APP / 'samples' / 'zh'
    echo_hits = churn_hits = 0
    n_files = 0
    if base.exists():
        # ★★★ 2026-10-26：**只量正文**（`正文/*.md`），不量大纲/设定/伏笔。
        #   这两条规则问的是"**叙事里**有没有绕圈说同一句 / 道具来回流转"，
        #   而大纲本来就会把同一句"完成判据"在几站里重复写（那是**表格**，不是台词）。
        #   实测：`故事大纲.md` 一个文件就假红 3 条（"疏已用印"在 4 站里出现 4 次 ——
        #   它本来就是那一站的事）。⇒ 量错了对象，比量错阈值更致命。
        # [EN] ★★★ 2026-10-26: **measure prose only** (`正文/*.md`), not outline/settings/hooks.
        # [EN] Both rules ask "does the **narrative** circle one line / pass a prop back and forth",
        # [EN] while an outline repeats the same "done when" sentence across stations by design
        # [EN] (that is a table, not dialogue). Measured: `故事大纲.md` alone produced 3 false reds.
        # [EN] ⇒ measuring the wrong object is worse than a wrong threshold.
        for f in sorted(base.rglob('正文/*.md')):
            t = f.read_text(encoding='utf-8')
            n_files += 1
            echo_hits += len(GC.echo_phrase(t))
            churn_hits += len(GC.prop_churn(t))
    ok('D1 ★★★ 真人样本**零命中"台词回声"**（否则这条规则在打健康文本）',
       n_files >= 12 and echo_hits == 0, f'{n_files} 篇 · 命中 {echo_hits}')
    ok('D2 ★★★ 真人样本**零命中"道具流转"**',
       n_files >= 12 and churn_hits == 0, f'{n_files} 篇 · 命中 {churn_hits}')

    # D3 内联夹具：反复问同一件事（措辞每次不同）
    echo_fix = ('“妹妹到了这里，缺什么只管打发小丫头来取。”\n'
                '“若是缺什么，尽管说，别委屈了自己。”\n'
                '“我想问姑娘这屋里，可还缺什么物件？”\n'
                '“往后缺什么，只管言语。”\n')
    e3 = GC.echo_phrase(echo_fix)
    ok('D3 ★★★ 反复问"缺什么"（措辞每次不同）⇒ 被抓成候选',
       bool(e3) and any('缺什么' in x.key for x in e3),
       '；'.join(x.one_line()[:30] for x in e3[:2]))

    # D4 内联夹具：同一件东西被反复转手
    churn_fix = ('他把鸭子推过去。她提着鸭子站起来。傩送把鸭子放她脚边。\n'
                 '“这两只鸭子，是我专门为你留的。”她拿着鸭子不说话。\n'
                 '他伸手把鸭子拿了回去。\n')
    c4 = GC.prop_churn(churn_fix)
    ok('D4 ★★★ 同一件东西递/推/提/放 4 次以上 ⇒ 被抓成候选',
       bool(c4) and any('鸭子' in x.key for x in c4),
       '；'.join(x.one_line()[:34] for x in c4[:2]))

    # D5 跨天逐字复读
    d5 = GC.cross_day_echo([(1, '“你这个人哪，我是真不知道说什么好。”'),
                            (2, '“你这个人哪，我是真不知道说什么好。”')])
    ok('D5 ★★ 同一条长台词在两天里逐字一样 ⇒ 报"跨天复读"',
       bool(d5) and d5[0].days == (1, 2), str([x.one_line()[:30] for x in d5]))

    # D6 单天不报跨天
    d6 = GC.cross_day_echo([(1, '“你这个人哪，我是真不知道说什么好。”')])
    ok('D6 ★★ 只有一天 ⇒ 不报跨天（没有对照就没有"复读"）',
       d6 == [], str(d6))

    # D7 这一层**不进**确定性计数（否则会拿会抖的判官当收敛判据）
    found = GC.audit_book([(1, echo_fix)])
    keys = set(PF.prose_issue_count(echo_fix).keys())
    ok('D7 ★★★ 全书候选**不混进 `prose_issue_count`**（它不是收敛判据）',
       not (set(found['counts'].keys()) & keys) and '台词回声' not in keys,
       f'{sorted(found["counts"])} vs {sorted(keys)}')

    # D9 反思记录必须落在**运行文件夹**里（真跑 snow_v25 实测写到了项目根）
    from export.novel_version import _reflect_days_root

    class _R:
        root = 'C:/x/run9'

    _where = str(_reflect_days_root(_R())).replace('\\', '/')
    ok('D9 ★★★ 反思记录写在**运行文件夹的 `导出/`** 里（真跑实测发现它写到了'
       '项目根 —— 因为 `RunFolder` 的属性叫 `root` 不是 `dir`，异常被兜底成 `.`）',
       _where.endswith('run9/导出'), _where)

    # D2b 称谓 + 指代**不许**判成台词回声（望江楼实测的假阳性）
    # ⚠ 夹具要**真的能触发**：门槛是「同一个片段 ≥4 句不同台词」，
    #   第一版只写了 2 句含「掌柜这」，剔掉白名单也照样不命中 ⇒ 测的是空气。
    _addr = ('“掌柜，这白灯笼一亮来的都是些什么人”\n'
             '“掌柜，这纸上写的，怎么都洇了？”\n'
             '“掌柜，这字一碰就淡了。”\n'
             '“掌柜，这白灯笼一亮，来的都是些什么人啊？”\n'
             '“掌柜，这字我认。可这纸，怎么还是潮的？”')
    ok('D2b ★★★ **称谓 + 指代不算台词回声**（望江楼实测：「掌柜这」曾被判 ×6，'
       '那是"称谓+指代"，不是同一句话换着说）',
       GC.echo_phrase(_addr) == [], str([x.key for x in GC.echo_phrase(_addr)]))

    # ── D10 概述句代替场景：可数，但**只许检测、不许自动修** ──
    _tell = '忽然对岛村吐露自己长年记日记的私密习惯，说些只有纸笔知道的琐碎。'
    _tell_hit = GC.telling_sentences(_tell)
    ok('D10 ★★★ 「概述句代替场景」能可数地抓出来（读者被告知"有这件事"，'
       '却没看到它发生）',
       len(_tell_hit) == 1 and '琐碎' in _tell_hit[0][2], f'{len(_tell_hit)} 处')

    ok('D10b ★★★ 真人 54 篇**零命中**（"说些…""谈些…"这类词在正常叙述里也有，'
       '口径必须收到零误报）',
       sum(len(GC.telling_sentences(f.read_text(encoding='utf-8')))
           for f in (APP / 'samples' / 'zh').rglob('*.md')) == 0, '')

    # ★★★ 这一条是整组里最要紧的：**可数 ≠ 该自动改**。
    #   修它必须写出"她具体说了什么" = 新增内容，违反"事实一个字不许改"。
    #   所以它必须留在计数表之外 —— 一旦进了 `prose_issue_count`，
    #   就会被 Reflexion 的步骤链抓走，机器就会开始编造情节。
    ok('D10c ★★★ 它**不在 `prose_issue_count` 里**（进去了就会被自动修复链抓走，'
       '而修它只能靠编造内容）',
       '概述代场景' not in PF.prose_issue_count(_tell)
       and '概述代场景' not in V.RUBRIC, '')
    ok('D10d ★★ 而且它**没有 repair recipe**（没人会去"修"它，这是刻意的）',
       all('概述代场景' not in r.all_labels() for r in REC.RECIPES), '')

    # D8 记录能生成（导出关口要写给人看）
    lines = GC.report_lines(GC.audit_book([(1, echo_fix)]))
    ok('D8 ★★ 候选能变成一份**给人看的清单**（带原文，可回查）',
       len(lines) >= 2 and any('原文' in x for x in lines),
       f'{len(lines)} 行')



# ══════════════════════════ E 组：顾问（权限最小化） ══════════════════════════

_ITEMS = [
    {'kind': '台词回声', 'key': '缺什么', 'detail': '「缺什么」出现在 4 句不同台词里'},
    {'kind': '道具流转', 'key': '鸭子', 'detail': '「鸭子」在递/推/提/放里出现 5 次'},
]


def group_e() -> None:
    print('\n── E 顾问（只表态、不给改法、要能证明自己没坏）──', flush=True)

    async def main():
        # E1 正常输出能被解析（理由在前）
        raw_ok = '1｜删掉它读者就不知道她缺什么了，戏靠这句推进｜手法\n' \
                 '2｜换个人递一次就够了，后面几次没带来新信息｜打转'
        op = CR.parse(raw_ok, _ITEMS)
        ok('E1 ★★★ 顾问的话能被解析（理由在前、结论在后）',
           len(op) == 2 and op[0].is_device and not op[1].is_device,
           '；'.join(x.one_line()[:28] for x in op))

        # E2 顺序反了 ⇒ 拒掉，不瞎猜
        raw_bad = '1｜手法｜删掉它读者就不知道她缺什么了\n' \
                  '2｜打转｜换个人递一次就够了'
        op2 = CR.parse(raw_bad, _ITEMS)
        ok('E2 ★★★ **结论写在理由前面 ⇒ 整行丢掉**（顺序是硬约束，'
           '研究里唯一稳定有效的那个机械约束）',
           op2 == [], f'{len(op2)} 条被采纳')

        # E3 编号越界 ⇒ 丢，不崩
        op3 = CR.parse('9｜编出来的条目｜打转', _ITEMS)
        ok('E3 ★★ 模型自己编了个不存在的编号 ⇒ 丢掉，不许越界', op3 == [], '')

        # E4 没有 ask ⇒ 什么都不做
        r4 = await CR.review(_ITEMS, ask=None)
        ok('E4 ★★★ 没有顾问可用 ⇒ **什么都不做**（最坏也要保住原稿）',
           r4.opinions == [] and bool(r4.why), r4.why)

        # E5 内建对照：把"明显是手法"的那条判成打转 ⇒ 整批不可信
        async def bad_ask(prompt, tier, purpose):
            n = prompt.count('\n')      # 实际条数不重要，直接给全"打转"
            return '\n'.join(f'{i}｜没说出损失｜打转' for i in (1, 2, 3))
        r5 = await CR.review(_ITEMS, ask=bad_ask)
        ok('E5 ★★★ **内建对照被判成"打转" ⇒ 整批不可信**（判官要先证明自己没坏）',
           r5.trusted is False and CR.hint_of(r5) == '',
           f'trusted={r5.trusted} · {r5.why[:30]}')

        # E6 正常顾问：可信、只挑"打转"的进提示，且**不给改法**
        async def good_ask(prompt, tier, purpose):
            return '1｜删掉它读者就不知道她缺什么了｜手法\n' \
                   '2｜换个人递一次就够了｜打转\n' \
                   '3｜话题自然重复，每句都在推进｜手法'
        r6 = await CR.review(_ITEMS, ask=good_ask)
        hint = CR.hint_of(r6)
        ok('E6 ★★★ 可信时只把"打转"的写进反思提示，且提示里**没有改法**',
           r6.trusted and len(r6.loops) == 1 and '鸭子' in hint
           and '应该' not in hint and '改成' not in hint,
           hint.replace('\n', ' ')[:50])

        # E7 能力不相交：提示词里明写"不许写应该改成"
        p7 = CR.build_prompt(_ITEMS)
        ok('E7 ★★★ 提示词里**明写"不许写应该改成"**（给了改法，它就同时成了写稿方）',
           '不许写' in p7 and '应该改成' in p7 and '先写理由' in p7, '')

        # E8 调用炸了 ⇒ 不抛，说明原因
        async def boom(prompt, tier, purpose):
            raise RuntimeError('故意炸')
        r8 = await CR.review(_ITEMS, ask=boom)
        ok('E8 ★★ 顾问调用失败 ⇒ 不抛异常、不瞎表态（调用方据此保原稿）',
           r8.opinions == [] and '失败' in r8.why, r8.why)

    asyncio.run(main())



# ══════════════════════ F 组：源头配额（提示词里的规则要有上限） ══════════════════════

def group_f() -> None:
    print('\n── F 源头配额（方向对了还要有上限）──', flush=True)
    from crew import agents as A

    # F1 原方向必须还在（别为了治"一直挡"把"可以不接"删掉）
    ok('F1 ★★★ 「不是每句都得接」这条**方向还在**（删了它，对话会变回'
       '两个人严丝合缝念稿）',
       '不是每句都得接' in A.LIVE_SPEECH_RULES, '')

    # F2 配额必须在（这才是 R56 的修复本体）
    ok('F2 ★★★ 而且补了**配额**：「一场戏至少要有一处真正的回答」'
       '（望江楼实测：问 5 次、挡 5 次 —— 规则被过度执行，戏原地不动）',
       '不能一次都不接' in A.LIVE_SPEECH_RULES
       and '至少要有一处真正的回答' in A.LIVE_SPEECH_RULES, '')

    # F3 配额要说清"什么算真正的回答" —— 否则模型会把"又一句反问"当回答
    ok('F3 ★★★ 并且写明**什么算回答**：给出一条对方原本不知道的信息，'
       '不是态度、不是评语、不是又一句反问',
       '对方原本不知道的信息' in A.LIVE_SPEECH_RULES
       and '不是又一句反问' in A.LIVE_SPEECH_RULES, '')

    # F4 这条纪律本身：**凡"可以有例外"的规则都必须带配额**。
    #    用两条已知的真规则做回归 —— 它们都写了"但…"的反向边界。
    ok('F4 ★★ 两条已知会被过度执行的规则**都带了反向边界**'
       '（"不必每句都接" → 至少有一次回答；"话不是直线" → 别每句都卡）',
       '别每句都卡' in A.LIVE_SPEECH_RULES
       and '不能一次都不接' in A.LIVE_SPEECH_RULES, '')

    # F5 老实记下：这个形态**在导出层检测不了**（真人 4 篇命中，比例比真跑还高）
    #    —— 所以它才必须在源头治。判据钉住"别有人又去加一个假判据"。
    ok('F5 ★★★ 这一项**没有**对应的确定性检测器（真人 4 篇命中"短答"，'
       '比例 0.88 > 望江楼 0.44 ⇒ 统计上分不开；它只能在源头治）',
       '短答' not in (PF.prose_issue_count('“问什么。”\n“嗯。”') or {}), '')

    # ══════════════════════════════════════════════════════════════
    # F6–F9：**语体边界**（2026-10-20 深夜，用户读望江楼说"半文半白"）
    # ══════════════════════════════════════════════════════════════
    # 根因：`agent/core.py:1371` 那条"不许夹文言词、不许半文半白"**只管台词**，
    #   叙述层一条约束都没有。而 `style.sentence` 只写"句子短、动词多、形容词少"
    #   是**纯方向** —— 要"短"，最省力的办法就是砍虚词 ⇒ 砍成文言
    #   （`柳氏西窗坐`「我立柜边擦桌」）。这和 R56 是同一种病。
    # [EN] The "no classical wording" rule only covered dialogue; narration had none, and
    # [EN] `sentence` was a bare direction ("short") whose cheapest implementation is to
    # [EN] drop function words -- which is exactly classical Chinese.
    from pathlib import Path as _P

    from novel_bench.bench import dataset as _DS
    from novel_bench.bench import project_builder as _PB

    _w = _DS.load_work(_P('novel_bench/dataset/works/29_mowenlou.yaml'))
    _c = [x for x in _w.cases if x.id == 'mwl-01'][0]
    _rules = _PB._rules(_w, _c)

    ok('F6 ★★★ 叙述层**真的有语体约束**了（此前"不许半文半白"只管台词，'
       '叙述一条都没有 —— 而用户读到的混杂恰恰在叙述里）',
       '全篇一种' in _rules and '不许半文半白' in _rules, '')

    # ⚠ 只查"关键词在最终文本里出现"太松：`style.sentence` 里也有"不许靠砍虚词"，
    #   于是删掉 `project_builder` 那一条**关键词仍在**，变异抓不到（M46 实测）。
    #   ⇒ 查**那条规则本身的整行**（带"·"前缀与箭头示例），它只可能来自代码。
    # [EN] Matching bare keywords is too loose: the same wording also lives in
    # [EN] `style.sentence`, so deleting the code-side rule kept the check green. Match the
    # [EN] rule line itself (bullet + arrow example), which can only come from the code.
    # ⚠ 锚点 2026-10-25 更新：规则原文已改成"**也不许**用现代翻译腔充数"（多一个字），
    #   旧锚点量的是"不许用…"⇒ 产品是对的、判据红。这是"锚点过期"不是"产品坏了"。
    #   注意**要连 `· ` 一起查**（理由见下一条 F7 上面的注释），别只查关键词。
    # [EN] ⚠ Anchor updated 2026-10-25: the rule now reads "**也不许**用现代翻译腔充数" (one extra
    # [EN] character), so the old anchor failed while the product was correct -- a stale anchor, not a
    # [EN] broken product. Keep the `· ` prefix (reason in the note above F7).
    ok('F7 ★★★ 而且是**成对**的：「不许靠砍虚词变短」+「不许用现代翻译腔」。'
       '只写"句子短"会逼出文言，只写"不许文言"又会被翻译腔填满',
       ('· **不许靠砍虚词变短**' in _rules
        and '`柳氏西窗坐` ✗ → `柳氏在西窗下坐着` ✓' in _rules
        and '· **也不许用现代翻译腔充数**' in _rules), '')

    ok('F8 ★★ 「句子短」这个**方向本身还在**（治好混杂不等于放弃节奏；'
       '删掉"短"会变成另一种极端）',
       '句子短、动词多、形容词少' in _rules, '')

    # F9 ★★★ 语体一致性**没有确定性检测器**，理由要留档：
    #   用"处所状语直接接动词"（`柳氏西窗坐` / `我立柜边擦桌`）去量，
    #   真人 54 篇命中 13 处，**全是误报**（`他在铺上躺` / `梯子往墙上靠` / `往下看`）——
    #   那在现代汉语里是正常省略。正则分不开"文言倒装"与"正常省略"。
    #   用词频（之/其/乃 × 情绪/开始）更糟：真人也有"之×1 + 开始×1"，两头都命中。
    #   ⇒ 只能在源头治；硬做判据会变成专杀真人的假判据。
    # ⚠ 锚点 2026-10-25 更新，**意图不变**："只治句式不治词汇，模型会改成用文言词"。
    #   规则原文把"不许用文言虚词"并进了上一条（改成点名 `忽闻／遂／乃／其／之`
    #   "这类词一个都不要"），旧锚点「不许用文言虚词：`我遂问` ✗ → `我就问` ✓」已经不存在。
    #   ⇒ 查**现在那句话**：既点名了那几个词、又说"一个都不要"。
    #   ⚠ 不许直接把这条删掉 —— 删了就成了"没人管文言词"，而那条病是真出现过的。
    # [EN] ⚠ Anchor updated 2026-10-25, **same intent**: "fixing syntax without vocabulary lets the
    # [EN] model switch to classical words". The rule was merged into the previous bullet (naming
    # [EN] `忽闻／遂／乃／其／之` and saying "not one of these"), so the old anchor no longer exists.
    # [EN] => check the sentence that is there now. ⚠ Do not delete this criterion: that would leave
    # [EN] classical vocabulary unguarded, and the defect really occurred.
    ok('F10 ★★★ 第三类反例是**文言虚词**（`我遂问` / `便以鞋尖抵住`）—— '
       '只治句式、不治词汇，模型会改成"不砍虚词但用文言词"（v4 实测：'
       '翻译腔 4→0、倒装 3→0，但冒出「遂」「便以」）',
       '这类词一个都不要' in _rules and '`忽闻`／`遂`／`乃`' in _rules, '')

    ok('F11 ★★★ 而且**故意不禁** `方才/为何/可还`（明清白话里本来就有，'
       '禁了会把正常白话一起杀掉 —— 这与"专杀真人"是同一类错误）',
       '`方才` `为何` `可还` `不曾` 是**明清白话里本来就有的**' in _rules, '')

    ok('F9 ★★★ 这一项**也故意没有检测器**：用"处所状语直接接动词"量，'
       '真人 54 篇命中 13 处**全是误报**（`他在铺上躺`/`往下看`）—— '
       '正则分不开文言倒装与正常省略；词频（之×其×乃）更糟，真人也两头都命中',
       '半文半白' not in (PF.prose_issue_count('柳氏西窗坐，白衣映灯。') or {}), '')



# ══════════════════ G 组：装订稿末尾的质量指标页 ══════════════════

def group_g() -> None:
    print('\n── G 质量指标页（放末尾、逐项解释、失败不影响导出）──', flush=True)
    from export import quality_page as QP

    _t = ('岛村倚着窗框。驹子坐在火钵旁。炭火映着她半边脸颊。'
          '“炭还旺么。”她低声问，把手从袖子里抽出来，又放回去。'
          '窗外的雪把脚步声吞掉了，更鼓从巷子那头慢慢过来。')

    page = QP.render(_t)
    ok('G1 ★★★ 指标页能生成，并且**自己声明是附录、可以删**'
       '（它是给作者看的，不是作品的一部分）',
       bool(page.strip()) and '附录' in page and '删掉' in page, f'{len(page)} 字')

    # G2 逐项列全八项 —— **为 0 也要列**，否则读者分不清"没毛病"和"没检查"
    ok('G2 ★★★ **八项检测逐项列全**（为 0 的也列；只写"全部为 0"'
       '等于没解释，读者看不出查了哪八样）',
       all(k in page for k, *_ in QP._ROWS) and len(QP._ROWS) == 8,
       f'{len(QP._ROWS)} 项')

    # G3 每一项都要有"它指什么"和"为什么算毛病"两栏
    ok('G3 ★★★ 每一项都写清**口径**与**为什么算毛病**'
       '（只有一个数字不带解释，等于没写）',
       all(len(cal) >= 8 and len(why) >= 15 for _k, cal, _h, why in QP._ROWS),
       '')

    # G4 全书级候选也要逐项列四类，且**写明它不是毛病**
    ok('G4 ★★★ 全书级候选**逐项列出四类口径**，并明写"它可能是手法"'
       '（否则作者会把"鸭子被推 5 次"直接删掉）',
       all(k in page for k, *_ in QP._BOOK_ROWS)
       and len(QP._BOOK_ROWS) == 4
       and '可能是手法' in page, f'{len(QP._BOOK_ROWS)} 类')

    # G5 真人参考必须带样本量（不带样本量的"参考值"没有信息量）
    ok('G5 ★★ 真人参考**带样本量**（"36 篇"），否则那个数字没法判断可信度',
       '篇' in page and str(QP._HUMAN_N) in page, f'N={QP._HUMAN_N}')

    # G6 空文本不崩、返回空串（宁可没有附录，不许把导出搞崩）
    ok('G6 ★★★ 空文本**安全返回空串**（指标页是加分项，不许成为新的故障点）',
       QP.render('') == '' and QP.render('   ') == '', '')

    # G7 装订稿里**真的加上了**，而且只加在 novel 那一档
    import ast
    import inspect

    from export import novel_version as NV
    src = inspect.getsource(NV.render_manuscript)
    ok('G7 ★★★ 装订稿**真的调用了**它，且**只在 `novel` 那一档**'
       '（参考册要看过程痕迹、原文稿一个字符都不许动）',
       'quality_page' in src and 'if mode == MODE_NOVEL:' in src, '')

    # G8 指标页在**末尾**（在正文之后，不在文件头）
    doc = ('# 标题\n\n## 第 1 天\n\n' + _t)
    p2 = QP.render(doc)
    ok('G8 ★★ 它是**附录**：整页以 `---` 开头（在正文之后追加，不抢文件的头）',
       p2.startswith('---'), p2[:12].replace('\n', ' '))

    # G9 ★★★ 拼接**真的发生在末尾**（`text = text + _page`），不是拼到文件头。
    #    ⚠ 用 AST 而不是字符串：`"+ _page"` 这种判据一改写法就假绿
    #      （实测 M23 把 `text.rstrip() + "\n\n" + _page` 改成 `_page + text`，
    #       G8 照样绿 —— 因为 G8 测的是"指标页自身以 --- 开头"，与拼接位置无关）。
    #    ⇒ 这里找的是"赋值给 text，且加法的**右操作数**里有 `_page`"。
    _tree = ast.parse(src)

    def _appends_page(t) -> bool:
        for n in ast.walk(t):
            if not isinstance(n, ast.Assign):
                continue
            if not any(isinstance(x, ast.Name) and x.id == 'text'
                       for x in n.targets):
                continue
            v = n.value
            if not isinstance(v, ast.BinOp) or not isinstance(v.op, ast.Add):
                continue
            names = {x.id for x in ast.walk(v.right) if isinstance(x, ast.Name)}
            if '_page' in names:
                return True
        return False

    ok('G9 ★★★ 而且指标页是**追加在末尾**的（`text = text + _page`），'
       '不是拼到文件头抢正文的位置',
       _appends_page(_tree), '')



# ══════════════ H 组：剧情卡住（在世界状态层判，不在文本层判） ══════════════

class _Ps:
    """最小的 `PersonState` 替身（只要指纹用到的那几项）。"""

    def __init__(self, mission='', stuck=0):
        self.mission = mission
        self.mission_stuck = stuck
        self.status = '在场'

    def is_active(self):
        return True


class _W:
    """最小的 `WorldState` 替身。

    ⚠ 字段名必须与真实对象**逐字一致**（`scene` / `topic` / `people` /
      `beat_fingerprint` / `stall_beats` / `on_stage_names` / `off_stage_names`）——
      指纹读的就是这几个名字；替身写错一个字母，测的就是替身而不是产品。
    """

    def __init__(self, scene='望江楼·前厅', topic='白绫', people=None, off=None):
        self.scene = scene
        self.topic = topic
        self.people = people if people is not None else {
            '阿九': _Ps('侍立'), '柳氏': _Ps('逼问'), '沈砚': _Ps('抹壶')}
        self._off = off or ['济仁堂伙计']
        self.beat_fingerprint = ''
        self.stall_beats = 0
        self.watch_note = ''

    def on_stage_names(self):
        return list(self.people)

    def off_stage_names(self):
        return list(self._off)


def group_h() -> None:
    print('\n── H 剧情卡住（世界状态层：四样全同才算没动）──', flush=True)
    import sys as _sys
    if str(APP) not in _sys.path:
        _sys.path.insert(0, str(APP))
    from director import pressure as PRESS
    from director import stall as ST

    def _fp(w) -> str:
        """**所有指纹调用走这里**：崩了返回标记串，不许让整组崩掉。

        ⚠ 这是"判据自己崩了"那类假绿的根治：指纹一崩（某一行被改坏），
          第一版会让整个 `group_h` 抛出去 —— 反例法只看到"组崩溃"，
          **定位不到是哪一项**（M24/M25 就是这么隐身的）。
          返回标记串之后，"崩了"与"没变"是两件事，各自能判。
        [EN] Every fingerprint call goes through here. A crash returns a marker string
        [EN] instead of taking the whole group down, which is what hid M24/M25.
        """
        try:
            return ST.fingerprint(w)
        except Exception as e:                                   # noqa: BLE001
            return f'崩溃:{type(e).__name__}'

    # H1 四样全同 ⇒ 指纹一样（"换十种说法"也骗不过）
    w1 = _W()
    w2 = _W()
    ok('H1 ★★★ 世界没变时指纹**逐字相同**（这是"卡住"的定义：与措辞无关）',
       _fp(w1) == _fp(w2), _fp(w1))

    # H2 四样任一变 ⇒ 指纹就变。**逐项验**，否则不知道是哪一项没接上。
    _cases = [
        ('空间', lambda w: setattr(w, 'scene', '望江楼·后院')),
        ('在场人', lambda w: w.people.pop('沈砚')),
        ('手上事', lambda w: setattr(w.people['阿九'], 'mission', '去后厨添水')),
        ('话题', lambda w: setattr(w, 'topic', '井里的白绫')),
    ]
    # H2 四样**逐项验**。⚠ 必须写成四条字面量，不能用 f-string 拼编号 ——
    #    规则表的 B3 会**静态扫描**脚本里的编号字面量来核对"引用的判据真的存在"，
    #    f-string 拼出来的编号它扫不到，对账链就断了（实测：改成字面量之后 B3 立刻绿）。
    #    ⚠ 每项还要**独立容错**：指纹一崩，第一版会让整个 group_h 抛出去，
    #    反例法只看到"组崩溃"、定位不到是哪一项（M24/M25 就是这么隐身的）。
    # [EN] Four literal assertions, not an f-string loop: the rule table's B3 statically
    # [EN] scans id literals, so generated ids break the reconciliation chain.
    def _differ(mutate) -> tuple[bool, str]:
        w = _W()
        try:
            base = _fp(w)
            mutate(w)
            after = _fp(w)
            return (after != base), f'{base} → {after}'
        except Exception as e:                                   # noqa: BLE001
            return False, f'崩溃 {type(e).__name__}'

    _ok1, _d1 = _differ(lambda w: setattr(w, 'scene', '望江楼·后院'))
    ok('H2 ★★★ **空间**一变，指纹就变（四样任一项都要接上，漏一项那一条路就不再是判据）',
       _ok1, _d1)
    _ok2, _d2 = _differ(lambda w: w.people.pop('沈砚'))
    ok('H2b ★★★ **在场人物**一变，指纹就变（换人不算世界变了，这一条就形同虚设）',
       _ok2, _d2)
    _ok3, _d3 = _differ(lambda w: setattr(w.people['阿九'], 'mission', '去后厨添水'))
    ok('H2c ★★★ **手上那件事**一变，指纹就变（目标换了就是真推进，必须算"动了"）',
       _ok3, _d3)
    _ok4, _d4 = _differ(lambda w: setattr(w, 'topic', '井里的白绫'))
    ok('H2d ★★★ **话题**一变，指纹就变（一晚上聊同一件事正是卡住的最常见形态）',
       _ok4, _d4)

    # H3 标点差异**不许**算"变了"（换个逗号就骗过指纹，这条就废了）
    _same = _fp(_W()) == _fp(
        _W(people={'阿九': _Ps('侍 立，'),
                   '柳氏': _Ps('逼问'), '沈砚': _Ps('抹壶')}))
    ok('H3 ★★★ 只差标点/空格 ⇒ **仍算没变**（否则改个逗号就骗过指纹）',
       _same, '')

    # H4 连拍计数：首拍记 1，相同则累加
    w5 = _W()
    ns = [ST.note(w5) for _ in range(4)]
    ok('H4 ★★★ 连拍计数语义 = **"连续几拍（含本拍）一样"**'
       '（第一版写成"与上一拍相同的次数"，于是阈值说 3 实际要到第 4 拍）',
       ns == [1, 2, 3, 4], str(ns))

    # H5 三档阈值
    ok('H5 ★★★ 三档都到位：3 → vary（换事件类型）· 5 → shift（换人）· 8 → settle（结算）',
       ST.level(2) == '' and ST.level(3) == 'vary' and ST.level(5) == 'shift'
       and ST.level(8) == 'settle', '')

    # H6 世界一动，计数归 1（不是归 0 —— 这一拍本身也算"第 1 拍一样"）
    w6 = _W()
    for _ in range(4):
        ST.note(w6)
    w6.scene = '望江楼·后院'
    ok('H6 ★★ 世界一变 ⇒ 计数**归 1**（这一拍是新的一段的第一拍）',
       ST.note(w6) == 1, '')

    # H7 vary 档真的换了事件类型
    class _P:
        def as_dict(self):
            return {'goal': 0.9, 'hardship': 0.7, 'secret': 0.2, 'time': 0.8}
    t_no = ST.pick_type(_P(), '')
    t_avoid = ST.pick_type(_P(), '人物冲突')
    ok('H7 ★★★ `vary` 真的换了一类事：上一拍是「人物冲突」⇒ 这次不用它',
       t_no == '人物冲突' and t_avoid != '人物冲突' and t_avoid != '',
       f'原 {t_no} → 换 {t_avoid}')

    # H8 只有一类够门槛 ⇒ 照旧用它（不许凭空造一个低压力的事）
    class _P2:
        def as_dict(self):
            return {'goal': 0.9, 'hardship': 0.1, 'secret': 0.0, 'time': 0.2}
    ok('H8 ★★★ 换不动就**照旧**（宁可连着同类，也不许凭空造一个低压力事件 —— '
       '那会让推演不可解释）',
       ST.pick_type(_P2(), '人物冲突') == '人物冲突', '')

    # H9 全低 ⇒ 空串（"今天没戏"这条出口不许被堵死）
    class _P3:
        def as_dict(self):
            return {'goal': 0.0, 'hardship': 0.0, 'secret': 0.0, 'time': 0.0}
    ok('H9 ★★★ 四条压力全低 ⇒ 返回空串（**不许出事**）—— '
       '这条出口一旦被堵死，模型就只能靠"来人"凑戏',
       ST.pick_type(_P3(), '外部刺激') == '', '')

    # H10 shift 档会写提示，且提示里点名"必须有一个人进出"
    try:
        w10 = _W()
        for _ in range(6):
            ST.note(w10)
        _h = ST.shift_hint(w10, 6)
    except Exception as e:                                       # noqa: BLE001
        _h = f'崩溃 {type(e).__name__}'
    ok('H10 ★★★ `shift` 档会写一条"下一拍必须有人进出"的提示（走已有的 '
       '`watch_note` 通道，不新造字段）',
       '必须有一个人进出' in _h and '济仁堂伙计' in _h, _h[:44])

    # H11 指纹是纯函数：算两遍一样，且不改 world（除了 note）
    w11 = _W()
    a1 = _fp(w11)
    a2 = _fp(w11)
    ok('H11 ★★ 指纹是**纯函数**：连算两遍一样，且不改动 world',
       a1 == a2 and w11.stall_beats == 0, '')

    # H12 观察器不许影响推演：world 残缺也得安全返回
    class _Bad:
        pass
    ok('H12 ★★★ 指纹/连拍在**残缺的 world 上也安全返回**（它是观察器，'
       '任何失败都不许影响推演）',
       isinstance(_fp(_Bad()), str) and ST.note(_Bad()) >= 0, '')

    # H13 接进了生产路径（引擎换事件类型 + 主循环算指纹）
    import inspect

    from director import engine as DE

    from sim import loop as SL
    _esrc = inspect.getsource(DE.DirectorEngine._inject_event)
    _lsrc = inspect.getsource(SL.RunLoop._tick)
    ok('H13 ★★★ 两处都**真的接上了**：`_inject_event` 调 `stall.pick_type`，'
       '`_tick` 每拍调 `stall.note_and_hint`',
       'pick_type' in _esrc and 'note_and_hint' in _lsrc, '')

    # H14 settle 档必须传连拍数（漏参数会被 int(None) 兜成 0 ⇒ 静默无效）
    ok('H14 ★★★ `settle` 档调 `request_settle` 时**传了连拍数**'
       '（漏参数会被兜成 0，静默什么都不做 —— 界面上看不出异常）',
       'request_settle(_n)' in _lsrc, '')

    # ── H15/H16：**同义词**（2026-10-20 深夜补，实测发现指纹在这里漏了一口气）──
    #   指纹的"每人手上那件事"吃的是**模型写的派活文本**。同一个目标换个说法
    #   （"弄清白绫的来历" / "搞明白那条白绫是从哪来的"）字面不同 ⇒ 指纹不同
    #   ⇒ **被算成"世界动了"** ⇒ 卡住反而更难被发现。这是"以为免疫、其实没有"。
    # [EN] The mission slot takes model-written text, so a re-worded goal changed the
    # [EN] fingerprint and counted as progress -- synonym leakage in the one layer that was
    # [EN] supposed to be wording-independent.

    class _PersonSyn:                                    # noqa: D401 - 判据内联夹具
        def __init__(self, m):
            self.mission = m
            self.status = '在场'
            self.mission_stuck = 0

        def is_active(self):
            return True

    class _WorldSyn:
        def __init__(self, people):
            self.scene = '望江楼·前厅'
            self.topic = '白绫'
            self.people = people

        def on_stage_names(self):
            return list(self.people)

        def off_stage_names(self):
            return []

    _w1 = _WorldSyn({'阿九': _PersonSyn('弄清白绫的来历'), '柳氏': _PersonSyn('追问白绫的事')})
    _w2 = _WorldSyn({'阿九': _PersonSyn('搞明白那条白绫是从哪来的'), '柳氏': _PersonSyn('盘问白绫的事')})
    _w3 = _WorldSyn({'阿九': _PersonSyn('说出白绫的来历'), '柳氏': _PersonSyn('追问白绫的事')})
    ok('H15 ★★★ **同义改写不算推进**（"弄清/搞明白"、"来历/从哪来"、'
       '"追问/盘问" 归成同一个目标键 —— 否则换个说法就骗过指纹）',
       _fp(_w1) == _fp(_w2), f'{_fp(_w1)} vs {_fp(_w2)}')
    ok('H16 ★★★ **成对：真换了目标必须算推进**（"弄清"→"说出" 是两件事：'
       '一个是查到、一个是交出去 —— 归一不许把它们并掉）',
       _fp(_w1) != _fp(_w3), f'{_fp(_w1)} vs {_fp(_w3)}')

#: 与 `mwl_v2` 同形态的正文（含句首人名 + 大量动宾动作）。**内联**，
#: 因为判据不该依赖 `novel_bench/results/` 里的历史产物（随时可能被清掉）。
_EXT_BODY = (
    '亥时，望江楼前厅。我拿抹布蹭锡壶。安知柜台后抹壶，推碗对柳氏："喝。"\n'
    '柳氏坐窗下条案，白衣端茶碗。我把抹布搁桌上直身：'
    '"那你到这楼里来，是要做什么？"安知对柳氏："茶凉了就不好喝了。"\n'
    '柳氏抬眼向我："你忘了井，也忘了我。"安知对我："茶喝了，就该走了。"\n'
    '柳氏放下碗瞥我，茶盏顿案。我放壶手蹭围裙。她盯着我手：'
    '"你端壶的手，抖什么。"我攥壶把，掌心汗擦不干。\n'
    '安知推碗瞥我："喝。"柳氏摩挲盏边："那白绫，你当真一点都不记得了？"\n'
    '安知端盏搁托盘："茶钱记我账上。"我捏着衣角："大姐，你莫再问了。"\n'
    '安知拿柜台紫砂壶抹净，布纹掠过壶钮。我却将壶放回案上，转身退去廊下。\n'
    '灶膛柴火塌着细响，我深吸一口气。柳氏将茶盏推到我面前，盏底划出轻响：'
    '"这茶，你喝着是什么味？"我端起盏喝一口，茶汤滚过舌面。\n'
    '我提壶续水，手抖差点摔了壶。壶嘴淌出的水线却歪了半寸。'
    '安知把算盘一推，端起杯，又放下。柳氏推盏，瓷底蹭着桌面退开半指。\n'
    '安知指了指凉茶，杯壁凝着水珠。柳氏望地，盯着桌脚下那片暗影，'
    '指尖在碗沿敲了敲。我放下壶，抹布沾了水，重新擦过一遍桌沿。\n'
)



# ══════════ I 组：外部评审 → 分诊（人名歧义 / 动作密度 / 只吃真的那部分）══════════

#: 用户实际收到的那份外部评审（原样，只截到每条的"修复方法"）。**故意用真的**：
#: 手写的干净夹具证明不了"对着自由文本能不能拆对、量对"。
_EXT_REVIEW = (
    '【问题1】人物标识混乱，读者难以分辨说话者\n'
    '修复方法：2. 若"安知"是动词，应改为"别问"或"不必多问"\n'
    '【问题2】时空跳跃频繁，缺乏过渡衔接\n'
    '具体表现：时间突然从"亥时"跳到深夜\n'
    '【问题3】对话与动作脱节，信息密度失衡\n'
    '具体表现：大量对话夹杂琐碎动作描写（抹壶、放壶、端盏、搁盏）\n'
    '【问题4】悬念设置过于密集，失去重点\n'
    '具体表现：柳氏追问频率过高（5次追问白绫）\n'
    '【问题5】第一人称视角与全知视角混杂\n'
    '具体表现：安知拿柜台紫砂壶抹净，布纹掠过壶钮\n'
)
# ⚠ 这三个人名必须有一个**形似常用短语**（`安知` 本身就是「怎么知道」）——
#   I1/I3/I7/I11 这四条查的正是「人名与短语分不开」那种歧义。
#   2026-10-26 去专名时这里被换成了普通名字，四条判据当场假红。
# [EN] One of these names must **look like a common phrase** (`安知` = "how would one know");
# [EN] I1/I3/I7/I11 all test that ambiguity, so an ordinary name turns them falsely red.
_CR_NAMES = ('安知', '柳氏', '阿九')


def group_i() -> None:
    print('\n── I 外部评审分诊（只吃真的那部分）──', flush=True)
    from crew import critique as CR
    from crew import name_guard as NG

    async def main():
        # ── 人名歧义 ──
        # ⚠ 正例只能用**语义上真成立**的：这几个名字本身就是一个常用短语（"何须""安知"），
        #   人名与短语在正文里分不开。2026-10-26 之前这里写的是一个具体作品的主角名，
        #   批量去专名时被换成了普通人名，这条判据当场变成假红 —— 记一次：
        #   **靠"某个例子"做语义判据时，例子的性质要写在旁边**，否则改名的人不知道自己改掉的是什么。
        # [EN] ⚠ Positive cases must be **semantically real**: these names are literally common
        # [EN] phrases ("何须", "安知"), so a person and a phrase cannot be told apart in prose.
        # [EN] Until 2026-10-26 this used a specific work's protagonist; the de-naming pass swapped in
        # [EN] an ordinary name and the criterion went falsely red. Lesson: when a semantic criterion
        # [EN] leans on one example, **write down what makes that example special**.
        ok('I1 ★★★ 形似常用短语的人名能认出来（何须 / 安知 本身就是短语；'
           '岛村/翠翠/王熙凤这类不会误报）',
           NG.collides('何须') and NG.collides('安知')
           and not NG.collides('岛村') and not NG.collides('翠翠')
           and not NG.collides('王熙凤') and not NG.collides('阿九'), '')

        _t = '。安知柜台后抹壶。安知对柳氏说了一句。'
        _hits = NG.risky_positions(_t, '安知')
        ok('I2 ★★★ 只报**真的会被误读**的位置：「安知柜台后抹壶」算，'
           '「安知对柳氏…」不算（有介词顶着，读者不会读成祈使句）',
           len(_hits) == 1 and '柜台' in _hits[0][2], str([h[2] for h in _hits]))

        # 名字的"首次出场没交代身份"
        _m = NG.first_mention_hint('安知推碗对柳氏说：喝。', _CR_NAMES)
        ok('I3 ★★ 首次出场没带身份词 ⇒ 报一条（外部评审唯一可取的那半句建议）',
           bool(_m), str(_m)[:40])

        # ── 动作密度 ──
        d_human_max = 5.6          # samples/zh 36 篇实测最高
        d_v2 = GC.action_density(_EXT_BODY)
        ok('I4 ★★★ 动作密度口径是**动宾**（"抹壶""搁盏"），不是光杆动词 —— '
           '第一版把 6 处数成 35 处，还据此判"成立"',
           d_v2['n'] >= 6 and d_v2['per_k'] >= 10,
           f'{d_v2["n"]} 处 / {d_v2["per_k"]} 每千字')

        ok('I5 ★★★ 阈值在**真人样本上限之上**（真人最高 5.6，阈值 6.0）—— '
           '这条是 5 条批评里唯一"既真、又可数、真人基线还干净"的',
           GC.ACTION_PER_K > d_human_max,
           f'阈值 {GC.ACTION_PER_K} > 真人最高 {d_human_max}')

        # ── 分诊骨架 ──
        chunks = CR.split_items(_EXT_REVIEW)
        ok('I6 ★★★ 自由文本评审能拆成 5 条（`【问题N】` 这种写法）',
           len(chunks) == 5, f'{len(chunks)} 条')

        items = CR.adjudicate(_EXT_REVIEW, text=_EXT_BODY, names=_CR_NAMES)
        by = {it.index: it for it in items}

        ok('I7 ★★★ 人名那一条判 **成立**，且实测数字是"2 处"这种真数（不是"9 处"）',
           by[1].verdict == 'confirmed' and '处' in by[1].measured,
           f'{by[1].verdict} · {by[1].measured}')

        ok('I8 ★★★ **处方风险被标出来**：「应改为别问」要改设定 ⇒ '
           '`prescription_risky` 必须为真（照改会毁掉楼名/人名/规矩四合一的双关）',
           by[1].prescription_risky, by[1].prescription[:40])

        ok('I9 ★★★ 动作那一条判 **成立**（19.4 每千字，真人上限 5.6）',
           by[3].verdict == 'confirmed', f'{by[3].verdict} · {by[3].measured}')

        # ★★★ 整组里最要紧的一条：验不了的必须如实标 unverifiable
        ok('I10 ★★★ **验不了就说验不了**：时空/悬念/视角三条都必须是 '
           '`unverifiable`，**不许**因为"检测器返回 0"就判成 `refuted`'
           '（那是假反驳：`percept_issues` 测的是"隔着纸门看见睫毛"，'
           '不是"背对柜台却看见布纹"）',
           by[2].verdict == 'unverifiable' and by[4].verdict == 'unverifiable'
           and by[5].verdict == 'unverifiable',
           '、'.join(f'{i}:{by[i].verdict}' for i in (2, 4, 5)))

        # 只有 confirmed 进教训库
        ls = CR.lessons(items)
        ok('I11 ★★★ **只有成立的那几条进改写教训库**（夸大的按放大数字改会过度矫正；'
           '验不了的没资格驱动改写）',
           len(ls) == 2 and all('外部评审' in x['why'] for x in ls),
           f'{len(ls)} 条')

        ok('I12 ★★ 教训里的修法用**我们自己的**，不是它给的处方',
           all('改为' not in x['advice'] and '别问' not in x['advice'] for x in ls),
           '、'.join(x['advice'][:18] for x in ls))

        # I16 ★★★ **短文本不许下结论**：220 字里一处动作就能算出 59 每千字，
        #     那个数没有意义。必须判 `unverifiable`，**不许**判 `refuted`。
        #     ⚠ 这条要单独用**短**夹具：I9 用的 374 字夹具永远走不到这条分支
        #       （反例法 M39 一开始就是这么隐身的）。
        _short = ('沈砚柜台后抹壶。沈砚推碗："喝。"柳氏端茶碗："井里的水凉。"'
                  '沈砚对柳氏："茶凉了。"我放壶："我确实是逃荒来的。"')
        _it_short = CR.adjudicate(
            '【问题1】对话与动作脱节\n具体表现：大量琐碎动作描写\n',
            text=_short, names=_CR_NAMES)
        ok('I16 ★★★ **短文本（<300 字）不下密度结论**：判 `unverifiable`，'
           '不是 `refuted`（220 字里一处动作就能算出 59 每千字，那个数没有意义）',
           bool(_it_short) and _it_short[0].verdict == 'unverifiable',
           _it_short[0].verdict if _it_short else '（没拆出条目）')

        # ── 接进导出链路 ──
        import inspect

        from export import novel_version as NV2
        _src = inspect.getsource(NV2)
        ok('I14 ★★★ 导出关口**真的接了分诊**：读 `外部评审.md`、跑 `adjudicate`、'
           '把结果写进 `导出/反思记录.md`',
           'REVIEW_NAME' in _src and 'adjudicate' in _src
           and 'critique=crit' in _src, '')
        ok('I15 ★★★ 而且**不改稿**：分诊只产出"教训"进提示词，'
           '不接受它的处方直接改正文（照改会撞既定设计）',
           '_adjudicate_review' in _src
           and 'crit_lessons' in _src
           and 'crit_lessons' in inspect.getsource(NV2._reflect_whole_book), '')

        # 分诊表可读
        md = CR.markdown(items)
        ok('I13 ★★ 分诊表能给人看，且**显式警告"别照改"**',
           '成立' in md and '不要照改' in md.lower() or '勿照改' in md,
           md.split(chr(10))[0])

    asyncio.run(main())



# ══════════════════════════ 入口 ══════════════════════════

def main() -> int:
    # ★ 每一组都包 try：**崩溃必须自己记一条红的**。
    #   踩过的坑（§63.3）：`finish()` 只 print traceback 不进 `checks`，
    #   于是变异脚本看到"0 条红"，看着像"判据不灵"，其实是脚本崩了。
    for fn in (group_a, group_b, group_c, group_d, group_e, group_f,
               group_g, group_h, group_i):
        try:
            fn()
        except BaseException as e:                               # noqa: BLE001
            ok(f'{fn.__name__} 执行失败（崩溃也算不通过）', False, repr(e)[:120])
    bad = [x for x in CHECKS if not x[0]]
    for good, name, detail in CHECKS:
        print(('  ✓ ' if good else '  ✗ ') + name + (f'　〔{detail}〕' if detail else ''))
    print(f'\n验证：{len(CHECKS) - len(bad)}/{len(CHECKS)}')
    if bad:
        print('红了：')
        for _g, name, detail in bad:
            print(f'  · {name}　〔{detail}〕')
    return 0 if not bad else 2


if __name__ == '__main__':
    sys.exit(main())
