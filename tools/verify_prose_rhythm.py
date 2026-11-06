# -*- coding: utf-8 -*-
"""判据：**文字的节奏**——别把小说写成"动作清单"。

来历（2026-10-18 用户原话）
---------------------------
「生成的小说或者写的文章句子感觉太简练了，过于追求故事推进，不像正常人写的小说
可能有很多不是特别有意义的句子或者词语，但是本身会很好的控制语言推进的节奏。」

先量，别猜（`developers/probe_prose_rhythm.py`，真人 18 章节 vs 四份产物）：

| 指标 | 真人均值 | ykg-01 | bc-01 | zx-01 |
|---|---|---|---|---|
| 全新句%（与前 3 句重合 <0.10） | 92.4 | **100** | 93.8 | **100** |
| 回声句%（0.10–0.35，即"再带一笔"） | **6.4** | **0.0** | 6.2 | **0.0** |
| TTR%（词汇丰富度） | **35.1** | 52.9 | 45.3 | 50.9 |
| 句长中位 / 标准差的均值 | 9.8 / 6.5 | **6 / 3.6** | **24 / 7.1** | **16 / 5.6** |

⇒ "太简练"的可数形状是：**每一句都在带新信息（全新句 100%、回声句 0）**，
且**词汇不复用（TTR 高 10–25 点）**，句子要么全碎（中位 6 字）要么整段不断（24 字）。
真人有 6% 的句子是"把刚发生的事再带一笔"——**那一笔就是节奏**。

这条判据守的是**产品侧的三条约束**（它们是把文本推向"议程"的闸）：
  A. 演员提示词：允许"不推进的句子"、要求长短交错、允许"回声"
  B. 手势闸：`_is_pure_gesture` 只删"没有附加成分"的（别把闲笔当噪声）
  C. 环境句：候选池用完**不是永久停**（否则一天只有 1–5 条空气）
  D. 审读：区分"回声"与"重复"（别把回声改写成新动作）

⚠ **不判"分数必须高于 X"**：真人样本彼此差得也很大（句长中位 7–12），
  用数值当闸门会变成另一种过拟合。判的是"这几条约束还在不在"。

跑法：`.venv/Scripts/python.exe tools/verify_prose_rhythm.py`
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail='') -> bool:
    CHECKS.append((name, bool(cond), str(detail)))
    print(f'{"  ✓" if cond else "  ✗"} {name}'
          + (f'   [{detail}]' if detail else ''), flush=True)
    return bool(cond)


def _read(rel: str) -> str:
    try:
        return (APP / rel).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


# ══════════════════════════════════════════════════════════
#  A  演员提示词：允许闲笔 / 长短交错 / 回声
# ══════════════════════════════════════════════════════════
def group_a() -> None:
    from util.prompts import strip_comments, template

    tpl, src = template('agent_decide_tail', '')
    body = strip_comments(tpl or '')
    ok('A1 ★★★ 外置模板取到了（来源 user 或 内置都算，但**不能是空**）',
       len(body) > 800, f'{src} / {len(body)} 字')

    # ── 允许"不推进的句子"：这是用户这次诉求的正中心 ──
    ok('A2 ★★★ 提示词明写"**不必每句都在走**"（一拍有一处变化就够，剩下的可以不推进）',
       '不必每句都在走' in body and '有一处' in body, '')
    ok('A3 ★★★ 而且给了**具体的例子**（不是一句抽象口号 —— "写点闲笔"这种话模型不当回事）',
       ('站在门口听' in body or '门口听了一会儿' in body)
       and ('擦干' in body or '炭塌' in body or '冒气' in body), '')
    ok('A4 ★★★ 说清了**为什么**（那些句子在控节奏，不是在占字数）——'
       '只写"允许"而不写"为什么"，模型会当成可选项',
       '控节奏' in body, '')
    # 成对：旧口径必须**删掉**，否则两条指令打架，模型会挑严的那条
    # [EN] Paired: the old wording must be **gone**, otherwise the two instructions fight and the
    # [EN] model follows the stricter one.
    ok('A5 ★★★ 成对：旧的"**只把气氛再描一遍不算**"已经删掉'
       '（它正是在禁止闲笔：两条并存时模型只会听严的那条）',
       '只把气氛再描一遍' not in body, '')

    # ── 长短交错 ──
    ok('A6 ★★★ 提示词要求**一段里至少一句长的**（别把推进写成一串五六字的短句）',
       '至少要有' in body and ('一句长的' in body or '长句铺' in body), '')
    ok('A7 ★★ 而且给了**反面例子**（碎句清单长什么样）——'
       '只有正面要求时，模型不知道"太长/太碎"的边界',
       '读起来像清单' in body or '她抬头' in body, '')

    # ── 回声 ──
    ok('A8 ★★★ 明写"再提一次**叫回声，不叫复读**"，并给了边界'
       '（换角度 / 换主语 / 换后果）',
       '回声' in body and ('换了角度' in body or '换角度' in body), '')
    # 成对：复读那条不能因此被冲掉
    ok('A9 ★★★ 成对：**复读禁令还在**（"同一句话原样说第二遍"仍是错的）',
       ('原样说第二遍' in body or '同一件事同一个说法' in body)
       and '复读' in body, '')

    # ── 台词长度不再一刀切 ──
    ok('A10 ★★ 台词长度不再写死"十几二十字以内"（改成"大多数十几二十字"＋允许偶尔长的）',
       '十几二十字以内' not in body and '电报' in body, '')

    # ★★★ 2026-10-18 真跑抓出来的：只写"不必每句都在走"，模型把整拍都写成 `wait`
    #   （6 拍里 10 次"听脚步声/等回应"、零条动作）。这就是"只禁不推会把戏抽干"
    #   的翻版 —— 所以"允许闲笔"必须**限定在句子层面**，并显式排除 `wait`。
    # [EN] ★★★ Caught by a real run on 2026-10-18: with only "not every sentence has to move",
    # [EN] the model wrote the whole beat as `wait` (10 "listening for footsteps" in 6 beats, zero
    # [EN] actions). Same disease as "only forbidding, never pushing". So "idle lines allowed" must
    # [EN] be scoped to **the sentence**, and `wait` must be explicitly excluded.
    ok('A13 ★★★ 明写"**说的是句子，不是这一拍**"（否则模型整拍摆烂）',
       '说的是句子' in body and '不是这一拍' in body, '')
    ok('A14 ★★★ 明写 **`wait` 不算"往前走一步"**（真跑实证：不加这条，6 拍里 10 次 wait、零动作）',
       '不算那件事' in body or '`wait` 不算' in body, '')
    ok('A15 ★★ 而且给了"全员在等"的反面例子（`正在 等脚步声/侧耳听` 那种）',
       '听脚步声' in body and '戏停了' in body, '')

    # ★★★ 2026-10-18 第二轮真跑：加了"允许闲笔"之后，评委的第一条缺陷从
    #   "台词太直" 变成「**整段靠短句堆气氛，事件没有推进**」
    #   （原话："意象本身不坏，但整段靠这类短句堆气氛，事件没有推进，落点空"）。
    #   ⇒ 钟摆的另一头也必须钉住：**空气要挂在人的动作上**，不是独立一段纯景物。
    # [EN] ★★★ Second real run on 2026-10-18: after "idle lines allowed", the judge's first
    # [EN] defect moved from "lines too direct" to "the whole passage piles up short mood lines,
    # [EN] nothing advances". => Pin the other end of the swing too: **air must hang on a
    # [EN] person's action**, not a standalone block of scenery.
    ok('A16 ★★★ 明写"**空气要挂在人身上**"（写的是他做事时周围什么样，不是先写完风景'
       '再让人物动）—— 否则会从"太推进"荡到"堆气氛"',
       '空气要挂在人身上' in body, '')
    ok('A17 ★★ 而且点名了"**堆气氛**"这个反面（用的是真跑产物里的原话）',
       '堆气氛' in body and '纯景物' in body, '')

    # ── 内置镜像：用户目录没有覆盖文件时用这份，两份必须同口径 ──
    core = _read('agent/core.py')
    ok('A11 ★★★ 内置镜像（`agent/core.py` 里那份）**同样**有闲笔/长短/回声三条'
       '＋"wait 不算往前走一步"（只改外置那份的话，没有用户目录的机器上等于没改，且看不出来）',
       all(k in core for k in ('不必每句都在走', '长句铺', '回声', '不算那件事')),
       str([k for k in ('不必每句都在走', '长句铺', '回声', '不算那件事') if k not in core]))
    ok('A12 ★★★ 成对：内置镜像里那句"只把气氛再描一遍不算"也删掉了',
       '只把气氛再描一遍' not in core, '')


# ══════════════════════════════════════════════════════════
#  B  手势闸：只删"没有附加成分"的，别把闲笔当噪声
# ══════════════════════════════════════════════════════════
def group_b() -> None:
    from display.scene_builder import SceneBuilder

    b = SceneBuilder.__new__(SceneBuilder)
    # 这三条是**闲笔**（带时长 / 带对象及量词 / 带结果），旧实现全判成"纯手势"，
    # 于是"连着两拍都这样"时第二拍被删 —— 实测误伤。
    # [EN] These three are **idle lines** (a duration / an object with a measure word / a result).
    # [EN] The old implementation judged all of them as "pure gestures", so the second of two
    # [EN] consecutive beats was dropped -- measured false positive.
    idle = ('站在门口听了一会儿。', '扫了一眼屋角那只旧箱子', '坐在那儿没动，看着火。')
    ok('B1 ★★★ 带时长/对象/结果的"闲笔"**不算纯手势**（它们正是真人在控节奏的写法）',
       not any(b._is_pure_gesture(x) for x in idle),
       str([x for x in idle if b._is_pure_gesture(x)]))
    # 成对：真刷屏的那种还得拦住
    spam = ('转向某人', '点头', '望向纸门', '沉默')
    ok('B2 ★★★ 成对：**真刷屏的**（"转向某人"/"点头"这种没有任何附加成分的）仍然算纯手势',
       all(b._is_pure_gesture(x) for x in spam),
       str([x for x in spam if not b._is_pure_gesture(x)]))
    ok('B3 ★★ 门槛是个**有名字的常量**（不是散在函数里的魔数 —— 以后调它有据可查）',
       isinstance(getattr(SceneBuilder, 'GESTURE_MAX_LEN', None), int)
       and SceneBuilder.GESTURE_MAX_LEN <= 10,
       str(getattr(SceneBuilder, 'GESTURE_MAX_LEN', None)))


# ══════════════════════════════════════════════════════════
#  C  环境句：池子用完不是永久停
# ══════════════════════════════════════════════════════════
class _W:
    scene = '某屋'
    weather = '晴'
    clock = None
    calendar = 'auto'
    sound_design = {'底噪': '檐水不断', '事件声': ['算盘被碰了一下', '门轴响'],
                    '静默': '门外没有脚步声'}


def group_c() -> None:
    from display.scene_builder import SceneBuilder

    b = SceneBuilder(_W(), day=1)
    pool = len(b._ambient_candidates())
    ok('C0 ★ 夹具里候选池不是空（否则下面几条是"没数据 ⇒ 量不到 ⇒ 绿"）',
       pool >= 3, f'{pool} 条')

    got = [b._pick_ambient_line() for _ in range(pool * 6)]
    n = sum(1 for x in got if x)
    ok('C1 ★★★ 池子出完一轮之后**还能再出**（旧实现"用过就永不"⇒ 一天最多 1–5 条，'
       '`AMBIENT_MINUTES` 调多小都不会变多，是个假旋钮）',
       n > pool, f'取 {pool * 6} 次得到 {n} 条（池子 {pool} 条）')
    ok('C2 ★★★ 成对：**相邻两条不同**（不许刷屏 —— 2026-10-17 那条修复必须还在）',
       all(a != b2 for a, b2 in zip(got, got[1:]) if a and b2), '')
    ok('C3 ★★★ 成对：冷却期内的确**不写**（宁可不写，也不重复上一句）',
       any(x == '' for x in got), f'空 {sum(1 for x in got if not x)} 次')

    # 配置项：0 = 退回旧行为（永不复现），证明它是个真旋钮
    from config import CFG
    old = CFG.i('AMBIENT_REPEAT_EVERY')
    try:
        CFG.set('AMBIENT_REPEAT_EVERY', '0')
        b2 = SceneBuilder(_W(), day=1)
        p2 = len(b2._ambient_candidates())
        got2 = [b2._pick_ambient_line() for _ in range(p2 * 6)]
        n2 = sum(1 for x in got2 if x)
    finally:
        CFG.set('AMBIENT_REPEAT_EVERY', str(old))
    ok('C4 ★★★ 配置 `AMBIENT_REPEAT_EVERY=0` ⇒ 退回"永不复现"（旧行为可回到，'
       '证明这是个**真旋钮**而不是装饰）',
       n2 == p2, f'设 0 时 {p2 * 6} 次只有 {n2} 条（池子 {p2} 条）')


# ══════════════════════════════════════════════════════════
#  D  审读：区分"回声"与"重复"
# ══════════════════════════════════════════════════════════
def group_d() -> None:
    src = _read('crew/agents.py')
    ok('D1 ★★★ 审读提示词里写了"**回声不算重复**"（否则演员隔几句再带一笔，'
       '会被审读改写成新动作 —— 节奏就没了）',
       '回声' in src and '不算重复' in src, '')
    ok('D2 ★★★ 而且给了判法（同一件事同一个说法才算重复 / 同一个东西另一种看法是回声）',
       ('同一个说法' in src or '原样' in src) and ('另一种看法' in src or '换' in src), '')
    ok('D3 ★★★ 成对：**重复那条主体还在**（不能因为加了"回声"就把判重放宽成不判）',
       '是不是同一件事' in src and '同一件事的下一步' in src, '')


# ══════════════════════════════════════════════════════════
#  E  真跑：发出去的 prompt 里真有这三条（"写了 ≠ 生效"那条铁律）
# ══════════════════════════════════════════════════════════
class _FakeDB:
    def retrieve_memory(self, *a, **k):
        return []

    def add_memory(self, *a, **k):
        pass

    def count_memories(self, *a, **k):
        return 0

    def get_summaries(self, *a, **k):
        return []

    def recent_events(self, *a, **k):
        return []


def _capture_prompt() -> str:
    import asyncio

    from agent import core as AC
    from agent.core import Agent
    from world.state import GameTime, PersonState, WorldState

    w = WorldState()
    w.scene = '临河茶肆'
    w.clock = GameTime()
    ps = PersonState(name='主角', location='临河茶肆', role='前台',
                     identity='茶肆掌柜', personality='话少，先听后说',
                     current_goal='把账上的窟窿弄清')
    w.people['主角'] = ps
    a = Agent(ps, _FakeDB(), w)
    seen: dict = {}
    real = AC.llm.chat

    async def fake_chat(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '测试'}, ensure_ascii=False), {})

    AC.llm.chat = fake_chat
    try:
        asyncio.run(a.decide())
    finally:
        AC.llm.chat = real
    return str(seen.get('prompt') or '')


def group_e() -> None:
    p = _capture_prompt()
    ok('E1 ★★★ 真跑 `decide()` 抓到了 prompt（不是空跑）', len(p) > 500, f'{len(p)} 字')
    ok('E2 ★★★ **发出去的那一坨**里有"不必每句都在走"（A 组只证明模板文件里有；'
       '模板可能没被选中、或被剥注释剥掉）',
       '不必每句都在走' in p, p[-300:])
    ok('E3 ★★★ 也有"长句铺"（长短交错那条真的进了提示词）', '长句铺' in p, '')
    ok('E4 ★★★ 也有"回声"（允许再带一笔那条真的进了提示词）', '回声' in p, '')
    ok('E5 ★★ 成对：旧口径"只把气氛再描一遍不算"**没有**出现在发出去的 prompt 里',
       '只把气氛再描一遍' not in p, '')


def main() -> int:
    for fn in (group_a, group_b, group_c, group_d, group_e):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            ok(f'{fn.__name__} 执行失败', False, repr(e))
    bad = [c for c in CHECKS if not c[1]]
    print(f'\n文字节奏验证：{len(CHECKS) - len(bad)}/{len(CHECKS)}', flush=True)
    if bad:
        print('有失败项：', flush=True)
        for n, _, _d in bad:
            print(f'  ✗ {n}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
