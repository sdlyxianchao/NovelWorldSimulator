# -*- coding: utf-8 -*-
"""判据：**提示词前缀的稳定性**（前缀缓存能不能命中，全看这一条）。

为什么单开一支
--------------
《AI Agent 从入门到精通》第九章 §9.10「缓存友好：把前缀钉死，把要紧的话放在两端」：
自回归模型的前缀缓存是**逐 token 比对最长公共前缀**，从第一个不同的 token 起，
后面**全部按未缓存价重算**。那一章量过：系统提示开头放一行带秒的时间戳，
命中率从 52% 掉到 **0%**。

本项目的病是同一个：`decide()` 那个"固定前缀"里原来混着
**每拍都在变**（人物当前目标/情绪/神态/位置）与**每场都在变**
（分层设定按天·场景·在场筛）的东西 —— 前缀缓存**一次都不会命中**。

这一支把"重排之后不许再退回去"钉死。四层，**每层都要能红**
（见 `developers/mutate_prefix_cache.py`）：

  A **拆分等价**：`world_prefix()` 的输出与 `stable + live` 拼回来**逐字相同**
     （拆了前缀不能把送给模型的东西改了 —— 那是偷改口径）。
  B **稳定段真的稳定**：改场景 / 改在场名单 / 走一天 → `stable` 一个字节都不变；
     `live` 会变（不然就是"把该动的也冻住了"，另一个方向的错）。
  C **行为级（最要紧）**：真跑几拍，抓**实际发出去的那段 prompt** ——
     同一个人物相邻两次的 P0 必须**逐字相同**。
     ⚠ 缺数据**不许算通过**（探针没接上时"全都相同"是真空成立）。
  D **契约不许被牺牲**：世界观 / 顶级规则 / 人格**仍然在受保护的前缀里**
     （设计稿 §2.4「固定前缀永不裁」）—— 为了缓存把它们挪进可裁层是**不允许**的。

用法：.venv\\Scripts\\python.exe tools/verify_prefix_cache.py
产出：assets/screenshots/prefix_cache_report.json

English:
Criterion: **stability of the prompt prefix** (whether the prefix cache can hit depends entirely
on this).
Why spin this off into its own branch
--------------
"AI Agent 从入门到精通" Chapter 9 §9.10 "Cache friendliness: nail the prefix down, put the important
words at both ends":
An autoregressive model's prefix cache compares **token by token for the longest common
prefix**; from the first differing token onward,
everything after is **recomputed at uncached price**. That chapter measured: putting a timestamp
line with seconds at the start of the system prompt
dropped the hit rate from 52% to **0%**.
This project's disease is the same: inside `decide()`'s "fixed prefix" there used to be a mix of
**things that change every beat** (character's current goal/emotion/expression/position) and
**things that change every scene**
(layered settings filtered by day·scene·presence) —— the prefix cache **never hits once**.
This branch nails down "after reordering, no going back". Four layers, **each layer must be able
to go red**
(see `developers/mutate_prefix_cache.py`):
  A **Split equivalence**: the output of `world_prefix()` and `stable + live` joined back are **character-for-character identical**
     (splitting the prefix must not change what's sent to the model —— that would be sneaky spec alteration).
  B **The stable segment is truly stable**: change scene / change present roster / advance one day → `stable` doesn't change by a single byte;
     `live` does change (otherwise it's "freezing what should move", the error in the other direction).
  C **Behavioral level (most important)**: actually run a few beats, capture **the actual prompt sent out** ——
     P0 for the same character on two adjacent runs must be **character-for-character identical**.
     ⚠ Missing data **must not count as pass** (when the probe isn't hooked up, "all identical" holds vacuously).
  D **The contract must not be sacrificed**: worldview / top-level rules / personality **still in the protected prefix**
     (design doc §2.4 "the fixed prefix is never trimmed") —— moving them into the trimmable layer for caching is **not allowed**.
Usage: .venv\\Scripts\\python.exe tools/verify_prefix_cache.py
Output: assets/screenshots/prefix_cache_report.json
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    # ★ 这种"守钱"的判据要能**看见数**，不能只有红绿（2026-11-01）：
    #   绿着但不知道前缀到底是 21% 还是 70%，就没法判断还值不值得再改。
    #   要数字时设 `NWS_VERBOSE=1`（默认不多嘴，免得回归日志被数字刷屏）。
    # [EN] A "guards the money" check must let you **see the number**, not just red/green
    # [EN] (2026-11-01): green but unknown 21% vs 70% means you cannot tell whether more work pays
    # [EN] off. Set `NWS_VERBOSE=1` to see it (silent by default so regression logs stay readable).
    import os as _os
    _show = detail and (not cond or _os.environ.get('NWS_VERBOSE'))
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'   [{str(detail)[:160]}]' if _show else ''))
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


class _Cfg:
    def __init__(self, **kw):
        self._kw, self._old = kw, {}

    def __enter__(self):
        for k, v in self._kw.items():
            self._old[k] = CFG.raw(k)
            CFG.set(k, str(v))
        return self

    def __exit__(self, *exc):
        for k, v in self._old.items():
            CFG.set(k, v)
        return False


def _mkworld():
    """一个"有料"的世界：规则 / 世界观 / 类型卡 / 风格卡 / **分层索引**全都写上。

    ⚠ 三条"没料就测不出来"的坑（第一版全踩了，4 条判据假红）：
      · 没有规则/世界观/类型/风格 → 稳定段是空的 → A/B 两组恒真；
      · 没有分层索引（`layer_index`）→ `[此处]/[主线]/[小事]` 都不出现，
        "换场景 live 会变"这条**无从观察**；
      · 人物没有 `current_goal` → 半固定层里就没有"当前目标"这一行，
        而判据要靠它当 P0 的切分点（C 组于是切不开、整段当 P0 比）。
    
        English:
    A world with "substance": rules / worldview / type card / style card / **layered index** all
    filled in.
        ⚠ Three pitfalls where "no substance means it can't be tested" (the first version hit all of them, 4 criteria went falsely red):
          · No rules/worldview/type/style → the stable segment is empty → groups A/B are both vacuously true;
            "changing scene makes live change" **cannot be observed at all**;
          · Character has no `current_goal` → the semi-fixed layer has no "current goal" line,
            and the criterion relies on it as the split point for P0 (so group C can't be split, and the whole segment is compared as P0).
    """
    from world.state import WorldState, GameTime, PersonState
    from world.layers import SettingItem
    w = WorldState()
    w.rules_text = '夜里不许出门；谁动了更漏谁就得说清行踪。'
    w.worldview_text = '临河小城，常年落雨，人情密、口风紧。'
    w.genre_card = {'主题材': '悬疑', '结构': '单元剧', '频道': '男频'}
    w.style_card = {'句长': '短', '叙事距离': '贴近人物限知视角',
                    'AI腔禁词表': ['首先', '五味杂陈']}
    w.style_source = 'auto'
    w.clock = GameTime()
    w.scene = '临河茶肆'
    w.people = {'主角': PersonState(name='主角', location='临河茶肆',
                                  role='前台', identity='茶肆掌柜',
                                  personality='话少，先听后说',
                                  current_goal='把账上的窟窿弄清'),
                '柳氏': PersonState(name='柳氏', location='临河茶肆',
                                  role='前台', current_goal='看住柜上的账'),
                '阿福': PersonState(name='阿福', location='后院',
                                  role='前台', current_goal='守好后门')}
    # 分层索引：三条不同层的设定，其中"此处"绑在**临河茶肆**上 ——
    # 换场景时 `[此处]` 就该消失/变化，B1 那条才观察得到。
    # [EN] Layered index: settings at three different layers, where "here" is bound to **临河茶肆** ——
    # [EN] When the scene changes, `[此处]` should disappear/change; only then can the B1 entry be observed.
    w.layer_index = [
        SettingItem(layer='canon', name='临河', text='临河小城，常年落雨。'),
        SettingItem(layer='arc', name='旧案', text='三年前那桩旧案要浮出来。'),
        SettingItem(layer='detail', name='缺角的壶', text='柜上那把壶缺了个角。',
                    where='临河茶肆', weight=4),
    ]
    return w


# ══════════════════════════════════════════════════════════════
#  A 拆分等价
# [EN] A: Split equivalence
# ══════════════════════════════════════════════════════════════
def test_split() -> bool:
    ok = True
    w = _mkworld()
    joined = w.world_prefix()
    stab, live = w.world_prefix_stable(), w.world_prefix_live()
    ok &= rec('A1 ★★ `world_prefix()` == `stable + live` **逐字相同**'
              '（拆前缀 ≠ 改口径：送给模型的东西一个字都不许变）',
              joined == '\n'.join(x for x in (stab, live) if x),
              f'{joined[:80]!r} / {stab[:40]!r}+{live[:40]!r}')
    ok &= rec('A3 稳定段非空（夹具没料的话这一组全是恒真）',
              bool(stab.strip()), repr(stab[:60]))
    ok &= rec('A1 ★ `[世界观]` 在**稳定段**里（它比"主线/此处/小事"稳得多：'
              '不开分层整轮不变，开了分层也只按天变宽度）',
              '[世界观]' in stab, stab[:80])
    ok &= rec('A1 ★ `[顶级规则` 也在稳定段里（作者写死的硬约束）',
              '[顶级规则' in stab, '')
    ok &= rec('A1 ★ `[类型]` / `[风格]` 在稳定段里（只跟这本书有关）',
              '[类型]' in stab and '[风格]' in stab, '')

    # 两个方法的**分工**：live 里不该出现稳定段的东西
    # [EN] Division of labor between the two methods: things that shouldn't appear in live for the stable
    # [EN] segment
    ok &= rec('A2 ★ 稳定段与"在变"那半**不重叠**（各管各的）',
              '[顶级规则' not in live and '[风格]' not in live, live[:80])
    return ok


# ══════════════════════════════════════════════════════════════
#  B 稳定段真的稳定
# [EN] B: The stable segment is truly stable
# ══════════════════════════════════════════════════════════════
def test_stability() -> bool:
    ok = True
    w = _mkworld()
    base = w.world_prefix_stable()
    base_live = w.world_prefix_live()

    # ① 换场景（live 必须变；stable 必须不变）
    # [EN] ① Change scene (live must change; stable must not change)
    w.scene = '城外渡口'
    w._prefix_cache = None
    ok &= rec('B1 ★★ 换场景 → **稳定段一字不变**（否则前缀缓存从这儿全废）',
              w.world_prefix_stable() == base, '')
    ok &= rec('B1 ★ 换场景 → "在变"那半**确实变了**（不能把该动的也冻住）',
              w.world_prefix_live() != base_live,
              f'{base_live[:40]!r} → {w.world_prefix_live()[:40]!r}')

    # ② 换在场名单（"此处/小事"按在场筛）
    # [EN] ② Change the present roster ("here/small matter" filtered by presence)
    w.scene = '临河茶肆'
    w._prefix_cache = None
    w.people['阿福'].location = '临河茶肆'
    ok &= rec('B2 ★★ 改在场名单 → 稳定段仍不变',
              w.world_prefix_stable() == base, '')

    # ③ 走一天
    # [EN] ③ Advance one day
    w.game_day = 5
    w.clock.day = 5
    w._prefix_cache = None
    ok &= rec('B3 ★★ 往前走一天 → 稳定段仍不变',
              w.world_prefix_stable() == base, '')

    # ④ 张力过展开线（世界观会从"一句气候"展开成全量）
    #   ⚠ 这一条**允许它变**（按天/按展开日变是设计内的），
    #      但它必须**只影响 [世界观] 那一段**，不能把规则/类型/风格一起带走。
    # [EN] ④ Tension crosses the expansion line (worldview expands from "a one-line climate" into the full
    # [EN] volume)
    # [EN] ⚠ This entry **is allowed to change** (changing by day/by expansion day is within design),
    # [EN] but it must **only affect the [世界观] segment**, and must not drag rules/types/style along with
    # [EN] it.
    w.tension = 0.95
    w._prefix_cache = None
    now = w.world_prefix_stable()
    if now != base:
        ok &= rec('B4 ★ 世界观展开时，规则/类型/风格**仍然一字不变**'
                  '（变的只有世界观那一段）',
                  '[顶级规则' in now and '[类型]' in now and '[风格]' in now,
                  now[:100])
    else:
        ok &= rec('B4 ★ 展开线没触发（夹具没分层索引）→ 稳定段原样',
                  True, '')

    # ⑤ 关掉分层：回到"世界观取前 500 字"，且**仍在稳定段里**
    # [EN] ⑤ Turn off layering: return to "worldview takes the first 500 characters", and **still inside
    # [EN] the stable segment**
    with _Cfg(SETTING_LAYERS='false'):
        w2 = _mkworld()
        ok &= rec('B5 ★ `SETTING_LAYERS=false` 时 `[世界观]` 仍在稳定段'
                  '（老做法也要走同一条路）',
                  '[世界观]' in w2.world_prefix_stable(),
                  w2.world_prefix_stable()[:80])
    return ok


# ══════════════════════════════════════════════════════════════
#  C 行为级：抓真发出去的 prompt
# [EN] C: Behavioral level: capture the prompt actually sent out
# ══════════════════════════════════════════════════════════════
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


def _spy_pack(seen: list, real):
    """包一层 `llm.context.pack`，把**产品自己传进来的那个 `fixed`** 记下来。

    ⚠ 为什么必须这样量（第一版是从 prompt 文本里"切" P0，判据当场假绿）：
      切法是"从开头切到第一个半固定层标记（当前目标/情绪/位置…）之前"——
      而**变异①把动态层塞回 P0 之后**，那些标记就出现在 P0 内部了，
      于是切出来的那一段**依然逐拍相同** → 判据不红。
      也就是说：用文本猜"P0 在哪儿"，等于**用被验对象自己划的线去验它**。
      真正该量的是产品**声明**为固定层的那一份 —— 那就只有 `pack()` 的第一参数。
    
        English:
    Wrap a layer around `llm.context.pack`, and record **the very `fixed` that the product passes in
    itself**.
        ⚠ Why it must be measured this way (the first version "cut" P0 out of the prompt text, and the criterion went falsely green on the spot):
          The cut was "from the start up to just before the first semi-fixed layer marker (current goal/emotion/position…)" ——
          but **after mutation ① stuffed the dynamic layer back into P0**, those markers appear inside P0,
          so the cut-out segment **is still identical beat-to-beat** → the criterion doesn't go red.
          In other words: guessing "where P0 is" from text is equal to **using the line drawn by the object under test to test it**.
          What should really be measured is the copy the product **declares** as the fixed layer —— that is only the first argument of `pack()`.
    """
    from llm import context as CTX

    def wrapper(fixed, semi, dyn_blocks, tail, budget=None):
        seen.append({'fixed': fixed, 'semi': semi, 'dyn': list(dyn_blocks)})
        return real(fixed, semi, dyn_blocks, tail, budget=budget)

    return wrapper


def test_behaviour() -> bool:
    """★ 真跑几拍，量**产品自己传进 `pack()` 的那个 `fixed`**。
        English:
    ★ Actually run a few beats, and measure **the very `fixed` that the product passes into
    `pack()`**.
    """
    ok = True
    from agent import core as AC
    from agent.core import Agent
    from llm import context as CTX

    w = _mkworld()
    db = _DB()
    a = Agent(w.people['主角'], db, w)
    seen: list = []
    real_chat = AC.llm.chat
    real_pack = CTX.pack

    async def spy(tier, messages, **kw):
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '判据'}, ensure_ascii=False), {})

    AC.llm.chat = spy
    CTX.pack = _spy_pack(seen, real_pack)
    try:
        for i in range(4):
            # 每拍都动一下"会变"的东西：位置 / 情绪 / 神态
            # [EN] Jiggle the "will change" things on every beat: position / emotion / expression
            a.ps.location = '临河茶肆' if i % 2 else '账台'
            a.ps.emotion = {'不安': 0.5 + i * 0.1}
            a.ps.mood_note = f'第 {i} 拍的神态'
            asyncio.run(a.decide())
    finally:
        AC.llm.chat = real_chat
        CTX.pack = real_pack

    ok &= rec('C0 ★★ 真的抓到了 `pack()` 的固定层（< 2 条就什么都量不到 —— '
              '缺数据不许算通过）', len(seen) >= 2, f'{len(seen)} 条')
    if len(seen) < 2:
        return ok

    fixed = [s['fixed'] for s in seen]
    semi = [s['semi'] for s in seen]
    same = sum(1 for x, y in zip(fixed, fixed[1:]) if x == y)
    tot = len(fixed) - 1
    ok &= rec(f'C1 ★★★ 同一人物连续 {len(fixed)} 拍的**固定层逐字相同**'
              f'（{same}/{tot}）—— 这就是"前缀缓存能不能命中"的那个数',
              same == tot, '' if same == tot else f'第一次差异：{fixed[0][:60]!r}')
    ok &= rec('C1 ★★ 而半固定层**确实在变**（位置/情绪/神态每拍都动过 —— '
              '不是"整段冻住"那种假绿）',
              len(set(semi)) > 1, f'{len(set(semi))} 种不同的半固定层')
    ok &= rec('C2 ★★ 固定层里同时有：顶级规则 / 世界观 / '
              '**人格卡（身份·性格那一套，不只是名字）**',
              all(k in fixed[0] for k in ('夜里不许出门', '临河小城', '身份：')),
              fixed[0][:120].replace('\n', ' | '))
    ok &= rec('C2 ★ 固定层**里面没有**"当前目标/情绪/神态/位置"'
              '（那四样每拍都在变，放进固定层就等于把缓存废掉）',
              all(k not in fixed[0] for k in ('当前目标', '神态：', '情绪：')),
              fixed[0][-80:].replace('\n', ' | '))
    ok &= rec('C3 ★ 人物状态**没有丢**：它在半固定层里',
              all(k in semi[0] for k in ('当前目标', '位置：')), semi[0][:80])
    ok &= rec('C3 ★ 世界那半截也**没有丢**（[主线]/[此处]/[小事] 之类在固定层之后）',
              any(k in semi[0] for k in ('[主线]', '[此处]', '[小事]')), '')
    return ok


# ══════════════════════════════════════════════════════════════
#  D 契约不许被牺牲
# [EN] D: The contract must not be sacrificed
# ══════════════════════════════════════════════════════════════
def test_contract() -> bool:
    """把预算压到最低（SPEC 的 min=500）之后，三样东西**仍然在**。
        English:
    After pushing the budget to the minimum (SPEC's min=500), those three things **are still
    there**.
    """
    ok = True
    from agent import core as AC
    from agent.core import Agent

    w = _mkworld()
    db = _DB()
    a = Agent(w.people['主角'], db, w)
    seen: dict = {}
    real = AC.llm.chat

    async def spy(tier, messages, **kw):
        seen['p'] = messages[-1]['content'] if messages else ''
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '判据'}, ensure_ascii=False), {})

    AC.llm.chat = spy
    try:
        with _Cfg(MAX_CONTEXT_TOKENS='500'):
            for i in range(6):
                a._add_memory('action', f'第 {i} 条很占地方的一长串记忆' * 12)
            asyncio.run(a.decide('很长很长的一段当前情况' * 60))
        small = seen.get('p', '')
        # ★ ★ **同一套夹具、把预算放开再跑一次** —— D1 第二半要拿它做对照。
        #   ⚠ 第一版判的是**绝对字数**（`len(small) < 4000`）：产品里每加一段
        #     常备内容（2026-10-18 加了「你嘴上要的/缺的」「这一拍的距离」），
        #     这个数就会往上爬，判据**自己变红**，而"裁没裁"这件事一点没变。
        #   ⇒ 改成**相对**：压到 500 之后的长度必须明显短于放开预算时的那一次。
        #     这才是"确实裁过"的证据，也不会被产品长胖顶红。
        # [EN] ★ Run the **same fixture again with the budget released** -- the second half of D1
        # [EN] needs a control. ⚠ The first version judged an **absolute length** (`< 4000`), so every
        # [EN] new standing block (2026-10-18 added the want/need and distance blocks) pushed it up and
        # [EN] the criterion **went red by itself** while "was it trimmed" had not changed at all.
        # [EN] => judge **relative**: after squeezing to 500 it must be clearly shorter than the
        # [EN] unconstrained run. That is evidence of trimming and immune to the product growing.
        seen.pop('p', None)
        with _Cfg(MAX_CONTEXT_TOKENS='200000'):
            asyncio.run(a.decide('很长很长的一段当前情况' * 60))
        big = seen.get('p', '')
    finally:
        AC.llm.chat = real
    ok &= rec('D1 ★★★ 裁到最低预算之后，**顶级规则 / 世界观 / 人格**仍在'
              '（设计稿 §2.4「固定前缀永不裁」—— 为缓存把它们挪进可裁层是不允许的）',
              all(k in small for k in ('夜里不许出门', '临河小城', '主角')),
              small[:160].replace('\n', ' | '))
    ok &= rec('D1 ★ 而动态层确实被裁了（压缩后 ≤ 放开时的六成；'
              '判的是**相对**，不是绝对字数 —— 后者会被产品长胖顶红）',
              bool(big) and len(small) < len(big) * 0.6,
              f'压到 500：{len(small)} 字 / 放开：{len(big)} 字')
    return ok


# ══════════════════════════════════════════════════════════════
#  E 真实前缀占比（**这一支守的是"那笔钱"**）
# [EN] E: real prefix share (**this group guards the money**)
# ══════════════════════════════════════════════════════════════
def test_real_prefix() -> bool:
    """连续 4 拍，**真发出去的 messages** 的公共前缀占多少。

    ★★★ 为什么这一支必须存在（2026-10-19 量出来的）：
      上面 A–D 四组测的都是 `_persona_static_only()` / `world_prefix_stable()`
      **这些函数的输出**稳不稳 —— 而线上真正的损失发生在**拼装顺序**上：
      每拍变的「当前目标 / 情绪 / 位置 / 场景·时间 / 在场」，原来排在 `semi`
      的第二位，于是固定层只有 **135 字**，后面 7600 字稳定内容全部拿不到缓存。
      实测（`usage.db` 近 7 天）：`agent_decide` 占输入 **53%**（1324 万 token），
      前缀缓存**只命中 1.1%**；同一时间 `crew_script_doctor` 17.3%、`day_verify` 15.1%
      —— 机制是通的，是这条路的顺序错了。厂商命中价约 1/10。

    ⚠ 判的是**真实 messages**（拦 `llm.chat` 抓），不是自己拼一份 ——
      测副本会得到"函数稳定、线上不命中"这种最迷惑的绿。
    [EN] ★★★ Why this group must exist (measured 2026-10-19): A-D test whether the **functions'**
    [EN] output is stable, while the real loss was in **assembly order**: the per-beat "current goal /
    [EN] emotion / location / scene-time / present" sat second in `semi`, so the fixed layer was only
    [EN] **135 chars** and the following 7600 stable chars all missed. Measured (`usage.db`, 7 days):
    [EN] `agent_decide` is **53% of input** with a **1.1%** hit rate, while `crew_script_doctor` hits
    [EN] 17.3% and `day_verify` 15.1% -- the mechanism works; this path had the wrong order.
    [EN] ⚠ It judges the **real messages** (intercepting `llm.chat`), not a self-built copy.
    """
    ok = True
    from agent import core as AC
    from agent.core import Agent

    w = _mkworld()
    a = Agent(w.people['主角'], _DB(), w)
    ps: list[str] = []
    real = AC.llm.chat

    async def spy(tier, messages, **kw):
        ps.append(messages[-1]['content'] if messages else '')
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '判据'}, ensure_ascii=False), {})

    AC.llm.chat = spy
    try:
        for i in range(4):
            asyncio.run(a.decide())
            w.clock = w.clock.add(20)
            w.note_line('柳氏', f'第{i}句', kind='speak')
            w.topic = f'第{i}句'
            w.topic_open_with = '主角'
            w.beat_tick = i + 1
    finally:
        AC.llm.chat = real

    ok &= rec('E1 ★★ 抓到了 4 拍真实 prompt（没抓到的话下面几条是空的）',
              len(ps) == 4 and all(len(x) > 1000 for x in ps),
              f'{len(ps)} 条 / 长度 {[len(x) for x in ps]}')
    if not ps:
        return False
    base = ps[0]
    shares = []
    for p in ps[1:]:
        n = min(len(base), len(p))
        j = 0
        while j < n and base[j] == p[j]:
            j += 1
        shares.append(j / max(1, len(base)))
    worst = min(shares) if shares else 0.0
    # ★★★ 门槛 0.55（2026-11-01 提高，原为 0.20）。
    #   历程：重排前 **1.8%** → 2026-10-19 第一次重排 **21.2%**
    #   → 2026-11-01 把尾部那一大段写作纪律前移 **67.2%**。
    #
    #   ⚠⚠ 为什么必须提门槛：阈值留在 0.20 时，"把纪律段挪回尾部"这个回退
    #     照样能过（21.2% > 20%）—— 判据绿着，钱照样按 10 倍计价。
    #     **基线一动，门槛就得跟着动，否则这条判据只证明"曾经好过"。**
    #   ⚠ 不压到 0.65：夹具是"同一人物连续 4 拍"，实测 67.2%；留 12 个百分点
    #     的余量给"某些书的世界观更长 / 人格卡更短"这种比例变化
    #     （`_live_world` 跨场会变，前缀本来就会短一点）。
    # [EN] ★★★ Threshold 0.55 (raised 2026-11-01, was 0.20).
    # [EN] History: 1.8% before any reorder → 21.2% after the first reorder (2026-10-19) →
    # [EN] 67.2% after hoisting the big craft-discipline block (2026-11-01).
    # [EN] ⚠⚠ Why the threshold must move: at 0.20, *moving the discipline block back to the tail*
    # [EN] would still pass (21.2% > 20%) -- green check, money still billed at 10x.
    # [EN] **When the baseline moves, the threshold must move, or the check only proves "it used
    # [EN] to be good".**
    # [EN] ⚠ Not 0.65: the fixture measures "same character, 4 consecutive beats" at 67.2%; keep
    # [EN] 12 points of headroom for books with longer world / shorter persona cards
    # [EN] (`_live_world` changes across scenes, so the prefix naturally shortens a bit).
    ok &= rec('E2 ★★★ **连续 4 拍的公共前缀 ≥ 55%**（1.8% → 21.2% → 67.2%）'
              '—— 这一条直接对应"厂商前缀缓存能不能命中"，也就是"输入按 10 倍还是 1 倍计价"',
              worst >= 0.55, f'最差 {worst:.1%} / 各拍 {[f"{x:.1%}" for x in shares]}')

    # ★★★ 成对：**稳定块一个都不许丢**（重排最容易犯的错是搬着搬着掉了一块）。
    #   每块**恰好一次** —— 0 次是丢了，2 次是重复烧钱。
    # [EN] ★★★ Paired: **not one stable block may be lost** (the classic reorder bug). Exactly once
    # [EN] each -- 0 means lost, 2 means paid twice.
    p_last = ps[-1]
    want = {
        # ⚠ 用**不带 markdown 星号**的片段：原文是「你是**一个人**，不是旁白」，
        #   写 `你是一个人` 会漏（星号夹在中间）。判据自己被这个坑过一次。
        # [EN] Use a fragment **without markdown stars**: the original is
        # [EN] `你是**一个人**，不是旁白`, and `你是一个人` misses because of the stars.
        # ⚠ 用**整块的首行**当指纹：`不是旁白` 那种短片段在全文里会出现 3 次
        #   （规则自己反复提到旁白），一测就假红。
        # [EN] Use the block's **first line**: a short fragment like `不是旁白` occurs 3 times in
        # [EN] the text (the rule mentions it repeatedly), which reads as a false red.
        '说话人隔离规则': '── 你是**一个人**，不是旁白 ──',
        '去 AI 清单': '【别写成 AI 腔',
        '思维链骨架': '开口之前，先在心里按顺序过一遍',
    }
    bad = {k: p_last.count(v) for k, v in want.items() if p_last.count(v) != 1}
    ok &= rec('E3 ★★★ 成对：三块**一轮不变**的规则（说话人隔离 / 去 AI 清单 / 思维链）'
              '各出现**恰好一次**（0 = 搬丢了，2 = 重复烧钱）',
              not bad, str(bad) if bad else '各 1 次')
    # ★ 顺序断言：三块必须在「当前目标」**之前**，否则前缀照样在那里断掉。
    # [EN] ★ Order: all three must precede "current goal", else the prefix is still cut there.
    i_goal = p_last.find('目标：')
    i_cot = p_last.find('开口之前，先在心里按顺序过一遍')
    i_deai = p_last.find('【别写成 AI 腔')
    ok &= rec('E4 ★★★ 而且它们都排在「当前目标」**之前**'
              '（排在后面 = 前缀照样在"当前目标"那一处断掉，等于没重排）',
              -1 not in (i_goal, i_cot, i_deai)
              and i_cot < i_goal and i_deai < i_goal,
              f'去AI@{i_deai} 骨架@{i_cot} 目标@{i_goal}')

    # ══════════════════════════════════════════════════════════════
    #  E5–E7：**搬运不许丢东西**（2026-11-01，随"纪律段前移"一起加的）
    # [EN] E5-E7: **moving blocks must not lose anything** (2026-11-01, added with the hoist)
    # ══════════════════════════════════════════════════════════════
    # ★★★ 为什么必须有一组"查丢没丢"的判据：
    #   重排最经典的事故是**搬着搬着掉了一块**，而掉的那块正好是写作纪律 ——
    #   模型**照样能演**（JSON 格式还在、动作还合法），只是越演越像 AI。
    #   E2 这种"前缀够不够长"的判据**只会更绿**（掉了内容前缀反而更短更整齐），
    #   所以"丢了东西"这件事只有下面这组能发现。
    # [EN] ★★★ Why a "did anything get lost" group is mandatory: the classic reorder accident is
    # [EN] **dropping a block while moving it**, and the dropped block is often craft discipline --
    # [EN] the model **still acts** (JSON shape fine, verbs legal), it just drifts toward AI prose.
    # [EN] A criterion like E2 ("is the prefix long enough") only gets **greener** (dropping content
    # [EN] makes the prefix shorter and tidier), so only this group can catch the loss.
    p_last = ps[-1]
    try:
        from util import prompts as _PR
        _tpl, _src = _PR.template('agent_decide_tail', '')
        _tpl = _PR.strip_comments(_tpl) or _tpl
        _lines = [ln.strip() for ln in _tpl.split('\n') if ln.strip()]
        # ⚠ 含 `{` 的行（`{n_layers}` / `{layers}` / `{think_field}`）在 prompt 里
        #   已经被填掉了 ⇒ 不能当指纹，否则这条判据恒红。
        # [EN] ⚠ Lines containing `{` (the placeholders) are already filled in the prompt ⇒ they
        # [EN] cannot be fingerprints or this check is permanently red.
        _cand = [ln for ln in _lines if len(ln) >= 14 and '{' not in ln][:30]
        _miss = [ln for ln in _cand if ln not in p_last]
        ok &= rec('E5 ★★★ 模板里的**每一条纪律**都还在发出去的 prompt 里'
                  f'（抽 {len(_cand)} 条当指纹）—— 重排最怕"搬着搬着掉一块"，'
                  '而掉了纪律模型照样能演，E2 反而更绿',
                  bool(_cand) and not _miss,
                  f'缺 {len(_miss)} 条：{[x[:40] for x in _miss[:3]]}')
    except Exception as _e:                                # noqa: BLE001
        ok &= rec('E5 读模板失败（读不到就不许算通过）', False, repr(_e))

    _n_ladder = p_last.count('推进你此刻最想推进的事')
    ok &= rec('E6 ★★ 「目标层级」那一块**恰好出现一次**（0 = 搬丢了，2 = 同一段烧两遍钱）',
              _n_ladder == 1, f'{_n_ladder} 次')

    _ijson = p_last.rfind('请以 JSON 回答你的行动')
    ok &= rec('E7 ★★ 「请以 JSON 回答」仍在**最后 300 字**之内'
              '（贴生成位置，指令更容易被遵守）',
              _ijson > 0 and len(p_last) - _ijson < 300,
              f'距末尾 {len(p_last) - _ijson} 字 / 全文 {len(p_last)} 字')
    return ok


if __name__ == '__main__':
    print('提示词前缀稳定性（前缀缓存）—— 验证', flush=True)
    ok = True
    try:
        head('A. 拆分等价（拆前缀不许改口径）')
        ok &= test_split()
        head('B. 稳定段真的稳定')
        ok &= test_stability()
        head('C. 行为级：抓真发出去的 prompt')
        ok &= test_behaviour()
        head('D. 契约：固定前缀永不裁')
        ok &= test_contract()
        head('E. 真实前缀占比（这一支守的是钱）')
        ok &= test_real_prefix()
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False,
            report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'prefix_cache_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n前缀缓存验证：{passed}/{len(report["checks"])}'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1500:])
    sys.exit(0 if report['ok'] else 2)
