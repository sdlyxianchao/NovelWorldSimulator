#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""世界法则验证：**事件是压力算出来的，不是模型挑出来的**。

★★★ 这一支守的是什么（2026-10-19 用户：「把'导演'从编剧改成世界法则」）
----------------------------------------------------------------------
改之前：导演每 8 拍问模型「请设计一个戏剧事件」。
那是一个**编剧**在做的事 —— 他想"这里该有个转折"，然后编一个。

两个后果都量到过：
  ① **收敛**：同一部《雪国》跑两次，文字重合 9.7%，**骨架重合 62.5%** ——
     "设计一个事件"这个问题本身就把答案收窄了（模型挑最安全的那一类）；
  ② **不可解释**：读者说不出"这件事为什么现在发生"。

改之后：类型由 `director/pressure.py` 从世界状态**算**出来（四个连续量、
纯代码、零模型调用），模型只负责**写成一件具体的事**。

这一支要证明三件事，缺一件整件事就是假的：
  · **A 压力算得对**：四种局面各算出对应的那一条最大（不是随机、不是恒定）；
  · **B 类型真的由压力定**：模型答别的类型时，最终类型仍是压力定的那个；
  · **C 全低就不出事**：四条压力都低时返回 None —— 这一条是"日常生活型"的开关，
    没有它，世界法则退化成"每 8 拍必须出点事"，跟改之前没区别。

⚠ **D 组守支路**：`_regen_event`（描述撞了重复时重生成）曾经把
  `event.event_type` 改回模型给的值 —— 主路改对了、支路忘了，判据只判主路就绿。
  这是本项目的"同一件事两处实现"，必须两条路各判一次。

⚠ **E 组守可解释性**：事件的理由必须是**压力的证据**，不是模型的复述。
  没有它，"推演"与"随机挑一件事"在结果上看不出区别。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

_n = _bad = 0


def ok(desc: str, cond: bool, detail: str = '') -> None:
    global _n, _bad
    _n += 1
    if not cond:
        _bad += 1
    print(f"  {'✓' if cond else '✗'} {desc}" + (f"  — {detail}" if detail else ''))


class _DB:
    def retrieve_memory(self, *a, **k):
        return []

    def add_memory(self, *a, **k):
        pass

    def add_event(self, *a, **k):
        pass

    def count_memories(self, *a, **k):
        return 0

    def get_summaries(self, *a, **k):
        return []

    def recent_events(self, *a, **k):
        return []


def _world(**people_spec) -> object:
    """造一个世界。`people_spec` 是 `名字=dict(字段...)`。"""
    from world.state import PersonState, WorldState
    from util.timefmt import GameTime

    w = WorldState()
    w.scene = '茶肆'
    w.game_day = 12
    w.clock = GameTime(day=12, minutes=9 * 60)
    for name, kw in people_spec.items():
        w.people[name] = PersonState(name=name, location='茶肆', **kw)
    return w


# ══════════════════════════════════════════════════════════════
#  A. 四条压力各算得出（纯函数，零调用）
# [EN] A. Each of the four pressures is computable (pure, zero calls)
# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    from director import pressure as P

    ok('A1 ★★ 四个压力名与事件类型的映射是全的（少一个就有一类局面永远不触发）',
       set(P.PRESSURE_EVENT) == {'goal', 'hardship', 'secret', 'time'}
       and set(P.PRESSURE_EVENT.values()) == {'人物冲突', '巧合', '秘密泄露', '外部刺激'},
       str(P.PRESSURE_EVENT))

    # ① 秘密压顶
    w = _world(甲=dict(secret='账上的窟窿是我填的', debut_day=2, current_goal='把账本找出来'),
               乙=dict(current_goal='今天去买米'))
    k, ev, v, pr = P.decide(w)
    ok('A2 ★★★ **藏了十天的秘密** ⇒ 秘密压力最大、类型是「秘密泄露」'
       '（不是"投一个泄密事件"，是**藏不住了**）',
       k == 'secret' and ev == '秘密泄露' and v >= 0.6, f'{k}/{ev}/{v:.2f}')

    # ② 目标对撞
    w2 = _world(甲=dict(current_goal='把账本找出来对清楚'),
                乙=dict(current_goal='把账本烧掉不能让人看见'))
    k2, ev2, v2, pr2 = P.decide(w2)
    ok('A3 ★★★ **两个人都在盯账本** ⇒ 目标冲突最大、类型是「人物冲突」'
       '（不需要判断立场对立：抢同一个东西本身就是冲突）',
       k2 == 'goal' and ev2 == '人物冲突' and v2 >= 0.45, f'{k2}/{ev2}/{v2:.2f}')

    # ③ 身体见底
    w3 = _world(甲=dict(stamina=0.15, current_goal='躺着'))
    w3.people['甲'].emotion['fear'] = 0.9
    k3, ev3, v3, pr3 = P.decide(w3)
    ok('A4 ★★★ **体力见底 + 极度恐惧** ⇒ 处境恶化最大、类型是「巧合」'
       '（身体撑不住时人会做出不像自己的事）',
       k3 == 'hardship' and ev3 == '巧合' and v3 >= 0.4, f'{k3}/{ev3}/{v3:.2f}')

    # ④ 时间
    from util.timefmt import GameTime
    w4 = _world(甲=dict(current_goal='等人'))
    w4.clock = GameTime(day=12, minutes=22 * 60)
    k4, ev4, v4, pr4 = P.decide(w4, beats_left_today=2)
    ok('A5 ★★★ **一天快过完 + 只剩两拍** ⇒ 时间压力最大、类型是「外部刺激」'
       '（期限逼近会逼人准备不足地行动）',
       k4 == 'time' and ev4 == '外部刺激' and v4 >= 0.6, f'{k4}/{ev4}/{v4:.2f}')

    # ⑤ 四种局面给出四种**不同**的结果 —— 防止"永远返回同一个"这种最隐蔽的假实现
    # [EN] ⑤ The four situations give four **different** answers (guards the most hidden fake:
    # [EN] "always returns the same one").
    four = {k, k2, k3, k4}
    ok('A6 ★★★ 四种局面给出**四种不同**的结论（同一个答案 = 压力没接线）',
       len(four) == 4, str(sorted(four)))

    # ⑥ 可复现
    again = P.decide(_world(甲=dict(secret='账上的窟窿是我填的', debut_day=2,
                                    current_goal='把账本找出来'),
                            乙=dict(current_goal='今天去买米')))
    ok('A7 ★★★ 同一局面**可复现**（纯代码算的，不许调模型 —— 那样每次都不一样，'
       '就变成"换个地方随机"）',
       again[0] == 'secret' and abs(again[2] - v) < 1e-9, f'{again[0]}/{again[2]:.4f}')


# ══════════════════════════════════════════════════════════════
#  C. 全低就不出事（"日常生活型"的开关）
# [EN] C. All-low means nothing happens (the slice-of-life switch)
# ══════════════════════════════════════════════════════════════
def group_c() -> None:
    from director import pressure as P
    from director.engine import DirectorEngine

    w = _world(甲=dict(current_goal='等人'), 乙=dict(current_goal='扫地'))
    k, ev, v, pr = P.decide(w)
    ok('C1 ★★★ 四个人各忙各的、没有秘密、身体好、时间还早 ⇒ **全低**',
       k == '' and ev == '' and v == 0.0, pr.line())

    real = None
    try:
        import llm.router as R
        real = R.llm.chat
        called = {'n': 0}

        async def fake(tier, messages, **kw):
            called['n'] += 1
            return json.dumps({'是否介入': True, '类型': '巧合', '事件': '猫打翻油灯',
                               '涉及人物': [], '强度': 0.5, '理由': '猫'}, ensure_ascii=False)

        R.llm.chat = fake
        ev_ = asyncio.run(DirectorEngine(_world(甲=dict(current_goal='等人'),
                                                乙=dict(current_goal='扫地')), _DB())
                          ._inject_event())
    finally:
        if real is not None:
            import llm.router as R2
            R2.llm.chat = real

    ok('C2 ★★★ **全低时返回 None（这一拍不出事）**'
       '—— 没有这一条，世界法则就退化成"每 8 拍必须出点事"，跟改之前没区别',
       ev_ is None, repr(ev_))
    ok('C3 ★★★ 而且**连模型都没调**（不该出事的拍，不该花这次钱）',
       called['n'] == 0, f'调用 {called["n"]} 次')

    # 强制通道：高潮日 / 停滞自救 —— 全低也得出事，否则那两条路被废掉
    # [EN] Forced channels (climax day / stagnation rescue) must fire even when all are low.
    real2 = None
    try:
        import llm.router as R
        real2 = R.llm.chat

        async def fake2(tier, messages, **kw):
            return json.dumps({'是否介入': True, '类型': '巧合', '事件': '猫打翻油灯',
                               '涉及人物': [], '强度': 0.5, '理由': '猫'}, ensure_ascii=False)

        R.llm.chat = fake2
        ev2 = asyncio.run(DirectorEngine(_world(甲=dict(current_goal='等人'),
                                                乙=dict(current_goal='扫地')), _DB())
                          ._inject_event(reason_hint='停滞自救'))
    finally:
        if real2 is not None:
            import llm.router as R2
            R2.llm.chat = real2
    ok('C4 ★★★ 成对：**强制通道（停滞自救）全低也得出事**'
       '（让压力门槛拦掉它 = 把"越跑越平"的补救废掉）',
       ev2 is not None, repr(ev2.event_type if ev2 else None))
    ok('C5 ★★ 而且理由**说实话**（"四股压力都低，这一拍是被强制推的"），'
       '不许编一个压力的理由',
       bool(ev2) and '强制' in str(ev2.reason), str(ev2.reason) if ev2 else '')


# ══════════════════════════════════════════════════════════════
#  B/D/E. 生产路径：类型由压力定，模型与重生成都改不了
# [EN] B/D/E. Production path: the type comes from pressure; neither the model nor
# [EN] regeneration can change it
# ══════════════════════════════════════════════════════════════
def _capture(w, *, fake_type: str = '巧合', fake_desc: str = '一只猫打翻了油灯',
             reason_hint: str = '', settle: int = 0) -> tuple[object, str]:
    """真跑 `_inject_event`，模型**故意**返回别的类型。返回 (事件, 真发出去的 prompt)。"""
    import llm.router as R
    from director.engine import DirectorEngine

    cap: dict[str, str] = {}
    real = R.llm.chat

    async def fake(tier, messages, **kw):
        cap['p'] = messages[-1]['content'] if messages else ''
        return json.dumps({'是否介入': True, '类型': fake_type, '事件': fake_desc,
                           '涉及人物': [], '强度': 0.6, '理由': '因为猫'},
                          ensure_ascii=False)

    # ⚠ 必须把两个"率闸"临时开到 1：`REVEAL_PACING` / `COINCIDENCE_RATE` 是**概率**闸，
    #   默认值下"秘密泄露"会被按概率拦掉 ⇒ `_inject_event` 返回 None ⇒
    #   这一条会读成"类型没定对"，而真凶是"这次被概率拦了"（第一版就这么红的）。
    #   这一支判的是**类型由谁定**，不是"该不该揭"——后者有它自己的判据。
    # [EN] The two random gates must be opened to 1 for this check: `REVEAL_PACING` /
    # [EN] `COINCIDENCE_RATE` are **probabilistic**, so a "secret leak" gets dropped by chance and
    # [EN] `_inject_event` returns None => the check reads as "wrong type" while the real cause is
    # [EN] "the dice said no" (exactly how the first version went red).
    from config import CFG as _C
    _saved = {}
    for _k in ('REVEAL_PACING', 'COINCIDENCE_RATE'):
        try:
            _saved[_k] = _C.s(_k)
            _C.set(_k, '1.0')
        except Exception:                                        # noqa: BLE001
            pass
    R.llm.chat = fake
    try:
        ev = asyncio.run(DirectorEngine(w, _DB())._inject_event(
            reason_hint=reason_hint, settle=settle))
    finally:
        R.llm.chat = real
        for _k, _v in _saved.items():
            try:
                _C.set(_k, _v)
            except Exception:                                    # noqa: BLE001
                pass
    return ev, cap.get('p', '')


def group_b() -> None:
    # 秘密局：模型答"巧合"，最终必须是"秘密泄露"
    ev, p = _capture(_world(甲=dict(secret='账上的窟窿是我填的', debut_day=2,
                                    current_goal='把账本找出来'),
                            乙=dict(current_goal='今天去买米')))
    ok('B1 ★★★ **模型答"巧合"，最终类型仍是压力定的「秘密泄露」**'
       '—— 只"提示它照抄"是不够的：提示是软的，而挑类型正是退化成"写作"的那一步',
       ev is not None and ev.event_type == '秘密泄露',
       f'{ev.event_type if ev else None}')

    ok('B2 ★★★ prompt 里**明写了这一次的类型**（不是留空让它挑）',
       '秘密泄露' in p and '这一次发生的是' in p, '')
    ok('B3 ★★★ prompt 里**给了压力的证据**（"甲 藏的事已经压到 1.00"）'
       '—— 模型要知道"为什么是这一类"，才写得具体',
       '藏的事已经压到' in p, '')
    ok('B4 ★★★ 而且明说**不许换类型、不许写"什么都没发生"**'
       '（松一句，模型就会退回写它喜欢的那类）',
       '不要换类型' in p, '')

    # E 组：理由来自压力，不是模型的复述
    ok('E1 ★★★ 事件的理由**来自压力的证据**，不是模型的复述（"因为猫"）'
       '—— 没有它，"推演"与"随机挑一件事"在结果上看不出区别',
       ev is not None and '压到' in str(ev.reason) and '猫' not in str(ev.reason),
       str(ev.reason) if ev else '')

    # 目标局
    ev2, p2 = _capture(_world(甲=dict(current_goal='把账本找出来对清楚'),
                              乙=dict(current_goal='把账本烧掉不能让人看见')))
    ok('B5 ★★★ 目标局 ⇒ 「人物冲突」（换一个局面，类型跟着换 —— 证明是算出来的）',
       ev2 is not None and ev2.event_type == '人物冲突',
       f'{ev2.event_type if ev2 else None}')


def group_d() -> None:
    """D：**重生成支路也不许改类型**（主路改对、支路忘了 = 只判主路就绿）。"""
    import llm.router as R
    from director.engine import DirectorEngine, DirectorEvent

    w = _world(甲=dict(secret='账上的窟窿是我填的', debut_day=2, current_goal='把账本找出来'),
               乙=dict(current_goal='今天去买米'))
    ev = DirectorEvent(event_type='秘密泄露', description='旧描述', involved=[],
                       intensity=0.5, node_relevant=w.current_node, reason='甲 藏的事已经压到 1.00')
    cap: dict[str, str] = {}
    real = R.llm.chat

    async def fake(tier, messages, **kw):
        cap['p'] = messages[-1]['content'] if messages else ''
        # 重生成时模型改口说"巧合" —— 绝不许它改回来
        return json.dumps({'类型': '巧合', '事件': '一只猫打翻了油灯', '涉及人物': [],
                           '强度': 0.4, '理由': '猫'}, ensure_ascii=False)

    R.llm.chat = fake
    try:
        got = asyncio.run(DirectorEngine(w, _DB())._regen_event(
            [{'role': 'user', 'content': 'x'}], ev, ['一段很重复的描述'], 0.85))
    finally:
        R.llm.chat = real

    ok('D1 ★★★ **重生成支路也不许把类型改回模型说的那个**'
       '（主路改对、支路忘了 —— 这是"同一件事两处实现"的典型）',
       got is not None and got.event_type == '秘密泄露',
       f'{got.event_type if got else None}')
    ok('D2 ★★ 但**描述确实换了**（重生成该做的事还是要做，否则这条判据就变成"整条支路废掉"）',
       got is not None and got.description == '一只猫打翻了油灯',
       str(got.description if got else ''))


# ══════════════════════════════════════════════════════════════
#  F. 只此一处 + 零成本
# [EN] F. One implementation + zero cost
# ══════════════════════════════════════════════════════════════
def _read(rel: str) -> str:
    try:
        return (APP / rel).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def group_f() -> None:
    import ast as _ast
    eng = _read('director/engine.py')
    # ⚠ 用 AST 判**真正的引用**，不判源码文本：`MIN_PRESSURE` 在我自己的注释里也出现过
    #   （"哪怕它低于 MIN_PRESSURE"），按文本判就红了而产品是对的 —— 又一例"源码含字符串"。
    # [EN] Judge **real references** via AST, not source text: `MIN_PRESSURE` also appears in my
    # [EN] own comment, so a text test goes red while the product is correct.
    _names: set[str] = set()
    _consts: list[str] = []
    try:
        _tree2 = _ast.parse(eng)
        for _n in _ast.walk(_tree2):
            if isinstance(_n, _ast.Name):
                _names.add(_n.id)
            elif isinstance(_n, _ast.Attribute):
                _names.add(_n.attr)
            elif isinstance(_n, _ast.Constant) and isinstance(_n.value, str):
                _consts.append(_n.value)
    except SyntaxError:
        pass
    _joined = '\n'.join(_consts)

    ok('F1 ★★★ 压力判定**只有一处实现**（`director/pressure.py`），engine 只是调用'
       '（engine 里不许自己再算一遍阈值）',
       'from director import pressure' in eng
       and 'PRESS.decide(' in eng
       and 'MIN_PRESSURE' not in _names, '')

    # ⚠ 用**全部字符串常量**（含 f-string 的固定段），不设长度门槛：
    #   第一版只收 >80 字的常量，而提示词是 f-string ⇒ 被拆成很多短段 ⇒ 一条都收不到。
    # [EN] Use **all** string constants (including f-string literal parts) with no length filter:
    # [EN] the first version only kept >80-char constants, but the prompt is an f-string and gets
    # [EN] split into short pieces, so nothing was collected.
    ok('F2 ★★★ 提示词里**没有"请设计一个戏剧事件"**（那正是"编剧"的提问方式，'
       '它会自己把答案收窄）',
       bool(_consts) and '请设计一个戏剧事件' not in _joined,
       f'{len(_consts)} 段字符串常量')
    ok('F2b ★★★ 提示词里**明写了"这一次发生的是哪一类"**（类型由压力给，模型只写具体）',
       '这一次发生的是' in _joined, '')
    ok('F2c ★★★ 提示词里**给了压力段**（`[局面推到了这一步]`）'
       '—— 只给类型不给理由，模型写出来的事会跟局面脱节',
       '[局面推到了这一步]' in _joined, '')


def group_e() -> None:
    """E：**僵局结算** —— 连着几拍全员在等，要的是"结果"，不是"再挂一个悬念"。

    2026-10-19 用户：「剧情要尽快推进」。
    实测（《雪国》34 拍）：14 次决策里 7 次 `wait`，理由全是"等脚步声"；
    而导演按压力算出来的是「外部刺激」⇒ 模型写"门外又传来脚步声"
    ⇒ **悬念再加一层，人更不动**。所以僵局要**绕开压力**，用「巧合」逼人动。
    """
    # 僵局局：模型答"外部刺激"（正是坏写法），最终必须是「巧合」
    ev, p = _capture(_world(甲=dict(current_goal='等门外那个人走'),
                            乙=dict(current_goal='等门外那个人走')),
                     fake_type='外部刺激', fake_desc='门外又传来一阵脚步声',
                     settle=3)
    ok('E1 ★★★ 僵局时**绕开压力**：模型答"外部刺激"，最终类型仍是「巧合」'
       '（结算 = 外物先撑不住、逼人动；"外部刺激"只会再挂一层悬念）',
       ev is not None and ev.event_type == '巧合',
       f'{ev.event_type if ev else None}')
    ok('E2 ★★★ 提示词里有一整段 `[这一场僵住了]`（不是混在压力段里说一句）',
       '[这一场僵住了]' in p, '')
    ok('E3 ★★★ 明写**不许再挂一层悬念**，并举了"门外又传来脚步声"这个坏写法',
       '再挂一层悬念' in p and '门外又传来脚步声' in p, '')
    ok('E4 ★★★ 说清了这一拍**必须给出一个新事实**，给了具体样子'
       '（门开了 / 人进来了 / 东西掉了 / 有人说出了一件没人知道的事）',
       '必须给出一个新事实' in p
       and ('门真的开了' in p or '东西掉了' in p or '此前没人知道的事' in p), '')
    ok('E5 ★★★ 理由写的是**僵局的证据**（"连着 3 拍没人动"），不是压力的证据'
       '—— 否则事后看不出这一次是被僵局推的',
       ev is not None and '连着' in str(ev.reason) and '拍' in str(ev.reason),
       str(ev.reason) if ev else '')

    # ── 成对：不僵局时仍按压力分类型（不许把"巧合"写死成万能类型）──
    ev2, _p2 = _capture(_world(甲=dict(secret='账上的窟窿是我填的', debut_day=2,
                                      current_goal='把账本找出来'),
                               乙=dict(current_goal='今天去买米')),
                        fake_type='巧合', settle=0)
    ok('E6 ★★★ 成对：`settle=0` 时**仍然按压力分类型**（秘密局 ⇒ 秘密泄露）——'
       '不许因为加了僵局通道就把类型写死成"巧合"',
       ev2 is not None and ev2.event_type == '秘密泄露',
       f'{ev2.event_type if ev2 else None}')

    # ── 僵局判定的**行为**（纯函数，见 `sim.loop.stall_beats`）──
    # ⚠ 第一版判的是"源码里有没有 `_stall_beats` 和 `'wait'` 这两个词" ——
    #   反例法 M11（把统计表达式换成 `_waiters = 0`）**照样绿**：词都还在，
    #   行为已经没了。这就是"源码含字符串当判据"的老坑，改成行为判。
    # [EN] The first version judged "does the source contain `_stall_beats` and 'wait'". Mutation
    # [EN] M11 (replacing the counting expression with `_waiters = 0`) stayed green: the words
    # [EN] remained, the behaviour was gone. Classic "source text as criterion" trap.
    from sim.loop import stall_beats as _SB

    class _Act:
        def __init__(self, v: str):
            self.verb = v
    _all_wait = [('甲', _Act('wait')), ('乙', _Act('wait')), ('丙', _Act('wait'))]
    _mixed = [('甲', _Act('wait')), ('乙', _Act('act')), ('丙', _Act('act'))]
    ok('E7 ★★★ 行为：连 3 拍全员在等 ⇒ 第 3 拍**要求结算**'
       '（这是"剧情尽快推进"的可数实现）',
       _SB(2, _all_wait, need=3) == (3, True), str(_SB(2, _all_wait, need=3)))
    ok('E7b ★★★ 成对：**多数**不在等就归零（`1 等 + 2 做` 是正常场面，不该被打断）',
       _SB(2, _mixed, need=3) == (0, False), str(_SB(2, _mixed, need=3)))
    ok('E7c ★★★ 成对：`need=0` 关得掉（配置是**真旋钮**，不是装饰）',
       _SB(9, _all_wait, need=0) == (0, False), str(_SB(9, _all_wait, need=0)))

    # ★★★ **僵局的第二种形状**（2026-10-19 当天复测加）：不是"在等"，是"没别的话可说"。
    #   真跑实证：一句台词一字不差说了 5 次、一个话题追问 8 轮，而**没人连等三拍** ——
    #   只认 `wait` 的话，这种卡法一次都抓不到。
    # [EN] The **second shape** of deadlock: not "waiting" but "nothing else to say". Measured:
    # [EN] one line said verbatim five times while **nobody waited three beats** -- judging `wait`
    # [EN] alone would never catch it.
    _all_speak = [('甲', _Act('speak')), ('乙', _Act('speak')), ('丙', _Act('speak'))]
    ok('E7d ★★★ 行为：两人以上同拍撞上"说过的话"（`stuck>=2`）⇒ 也算僵局、要结算',
       _SB(2, _all_speak, need=3, stuck=2) == (3, True),
       str(_SB(2, _all_speak, need=3, stuck=2)))
    ok('E7e ★★★ 成对：只有一个人说了老话（`stuck=1`）⇒ **不算**僵局'
       '（一个人重复是"他坚持"，全场重复才是没新话可说）',
       _SB(2, _all_speak, need=3, stuck=1) == (0, False),
       str(_SB(2, _all_speak, need=3, stuck=1)))

    # ── 生产路径：`_dup_speaks` 真的在台词重复时被累加 ──
    ok('E7f ★★★ `_maybe_retry_repeat` 里真的累加 `_dup_speaks`'
       '（只写纯函数、没人喂数据 = 这条通道永远 0）',
       '_dup_speaks += 1' in _read('sim/loop.py'), '')

    # ── 生产路径：`_process_actions` 真的调了它，也真的把结果转给导演 ──
    import ast as _ast2
    fn = None
    try:
        for n in _ast2.walk(_ast2.parse(_read('sim/loop.py'))):
            if isinstance(n, (_ast2.FunctionDef, _ast2.AsyncFunctionDef)) \
                    and n.name == '_process_actions':
                fn = n
    except SyntaxError:
        fn = None
    calls_stall = calls_settle = False
    if fn is not None:
        for n in _ast2.walk(fn):
            if isinstance(n, _ast2.Call):
                f = n.func
                if isinstance(f, _ast2.Name) and f.id == 'stall_beats':
                    calls_stall = True
                if isinstance(f, _ast2.Attribute) and f.attr == 'request_settle':
                    calls_settle = True
    ok('E8 ★★★ 生产路径两头都接上了：`_process_actions` 调了 `stall_beats`，'
       '也算出结果后调了 `director.request_settle`（只写纯函数不接线 = 死代码）',
       calls_stall and calls_settle,
       f'stall_beats={calls_stall} request_settle={calls_settle}')
    ok('E8b ★★ 而且门槛来自配置（`STALL_BREAK_BEATS` 读得到）',
       'STALL_BREAK_BEATS' in _read('sim/loop.py'), '')

    # ── 边界：`request_settle` 只接受正数 ──
    # ⚠ 第一版测的是 `request_settle(0) 之后 _settle_beats == 0` —— 变异
    #   （去掉 `if n > 0`）之后它**还是 0**，判据抓不到。改成测负数。
    # [EN] The first version checked "after request_settle(0), _settle_beats == 0" -- that stays 0
    # [EN] even with the guard removed. Test a negative value instead.
    from director.engine import DirectorEngine
    w = _world(甲=dict(current_goal='等'))
    d = DirectorEngine(w, _DB())
    d.request_settle(-5)
    ok('E9 ★★ 边界：负数不生效（`-5` 不许变成"立刻结算"）',
       getattr(d, '_settle_beats', -99) == 0, str(getattr(d, '_settle_beats', '缺字段')))
    d.request_settle(4)
    ok('E9b ★★ 正数生效，而且 `on_tick` 读得走（读走即清零，不会连拍结算）',
       d._settle_beats == 4, str(d._settle_beats))


def main() -> int:
    print('═' * 62)
    print('  世界法则验证 · 事件是压力算出来的，不是模型挑出来的')
    print('═' * 62)
    print('\n【A】四条压力各算得出（纯函数）')
    group_a()
    print('\n【C】全低就不出事（"日常生活型"的开关）')
    group_c()
    print('\n【B】生产路径：类型由压力定，模型改不了')
    group_b()
    print('\n【D】重生成支路也不许改类型')
    group_d()
    print('\n【E】僵局结算：连 N 拍全员在等 ⇒ 给那个悬置一个结果')
    group_e()
    print('\n【F】只此一处 + 零成本')
    group_f()
    print()
    print('═' * 62)
    print(f'世界法则验证：{_n - _bad}/{_n} 通过')
    print('═' * 62)
    return 0 if _bad == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
