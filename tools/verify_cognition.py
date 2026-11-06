# -*- coding: utf-8 -*-
"""判据：**认知模式**（思维链 / 反思链 / 组合）—— `crew/cognition.py` 那一层。

为什么单开一支
--------------
用户 2026-10-07：「你看下哪些 Agent 可以引入 思维链 反思链 或者综合使用这些
设计模式 来强化其功能，让整个演戏流程更加接近真实世界的句子」——
参考《AI Agent 从入门到精通》第四章（ReAct / Plan-and-Solve / Reflection）
与第七章（构建你的 Agent 框架）。

模式表（谁用哪种模式、为什么）、思考骨架、台词自省判据都在 `crew/cognition.py`
一处。这一支判它**真的接上了**，而不是"文档里写了"。

判据分六层，**每层都要能红**（见 `developers/mutate_cognition.py`）：

  A **模式表（数据）**：名册每个职位都有模式；`NONE` 的说得出为什么；
     声明 `cot/both` 的必须有骨架；思考字段不许与模式矛盾；
     ★★ 骨架里挂的每一条手艺，**必须是这个职位货架里读得到的**。
  B **提示词层**：骨架真进提示词、真带该职位的手艺原文、按开关**逐字退回**。
  C **行为级（演员）**：打桩抓**真发出去的 prompt** —— 它里面有骨架、
     `推演` 字段真的被解析进 `Action.think_trace`；关掉总闸后**一字不剩**。
  D **行为级（剧组）**：剧作者那一次调用真的带 `构思`，且产出里真有它。
  E **反思链（台词自省）**：明显不像人话的台词**真的被改写**；正常台词
     **一次调用都不多花**；关掉开关/预算 0 → 逐字退回；判据不许误报。
  F **落地与隐私**：盘算进台账（作者看得见）、**不进叙事缓冲**（私下）。
  G **反假按钮**：新旋钮每一个都在产品源码里被字面量读过。

用法：.venv\\Scripts\\python.exe tools/verify_cognition.py
产出：assets/screenshots/cognition_report.json

English:
Criterion: **cognition mode** (chain-of-thought / reflection chain / combination) -- the
`crew/cognition.py` layer.
Why a separate branch
--------------
User 2026-10-07: "Look at which Agents can introduce chain-of-thought, reflection chain, or a
combination of these
design patterns to strengthen their functions, making the whole acting process closer to
real-world sentences" --
and Chapter 7 (Building Your Agent Framework).
The mode table (who uses which mode and why), thinking skeleton, and line self-review criteria
are all in `crew/cognition.py`
in one place. This branch checks that it is **truly wired up**, not just "written in the docs".
The criteria are divided into six layers, and **each layer must be able to go red** (see
`developers/mutate_cognition.py`):
  A **Mode table (data)**: every position in the roster has a mode; `NONE` ones can state why;
     those declaring `cot/both` must have a skeleton; the thinking field must not contradict the mode;
     ★★ every craft attached in the skeleton **must be readable from this position's shelf**.
  B **Prompt layer**: the skeleton really enters the prompt, really carries that position's original craft text, and falls back **verbatim** based on the switch.
  C **Behavior level (actor)**: stub to capture **the prompt actually sent out** -- it contains the skeleton,
     The `推演` field is actually parsed into `Action.think_trace`; after turning off the master switch, **not a single character remains**.
  D **Behavior level (crew)**: the playwright's single call really carries `构思`, and it really appears in the output.
  E **Reflection chain (dialogue introspection)**: lines that clearly do not sound human **are actually rewritten**; normal lines
     **do not cost a single extra call**; turning off the switch / budget 0 -> falls back verbatim; the criterion must not produce false positives.
  F **Persistence and privacy**: deliberation goes into the ledger (visible to the author), **does not go into the narrative buffer** (private).
  G **Anti-fake-button**: every new knob is literally read in the product source code.
Usage: .venv\\Scripts\\python.exe tools/verify_cognition.py
Output: assets/screenshots/cognition_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from config import CFG                                         # noqa: E402
# ⚠ 不量像素、不弹窗、**绝不点会 `CFG.save()` 的按钮**（见 MEMORY 的铁律）。
# [EN] ⚠ Do not measure pixels, do not pop up dialogs, **never click a button that triggers
# [EN] `CFG.save()`** (see the iron rule in MEMORY).
CFG.set('MOCK_LLM', 'true')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

#: 本轮新增的旋钮（G 组逐个查"真被读到"）。
# [EN] : The knobs added in this round (check each of group G to see if it is "actually read").
NEW_KNOBS = ('COGNITION', 'COT_ACTOR', 'COT_CREW',
             'ACTOR_SELF_REVIEW', 'ACTOR_SELF_REVIEW_MAX')


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'   [{str(detail)[:110]}]' if detail and not cond else ''))
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


class _CfgGuard:
    """成组改旋钮并**必定还原**（判据跑完不能给后面的脚本留下脏配置）。
        English:
    Change knobs as a group and **must restore** (after the criterion finishes, it must not leave
    dirty config for later scripts).
    """

    def __init__(self, **kw):
        self._kw = kw
        self._old: dict = {}

    def __enter__(self):
        for k, v in self._kw.items():
            self._old[k] = CFG.raw(k)
            CFG.set(k, str(v))
        return self

    def __exit__(self, *exc):
        for k, v in self._old.items():
            CFG.set(k, v)
        return False


# ══════════════════════════════════════════════════════════════
#  A. 模式表（数据）
# [EN] A. Mode table (data)
# ══════════════════════════════════════════════════════════════
def test_table() -> bool:
    ok = True
    from crew import roster as R
    from crew import cognition as COG
    from crew import agents as A

    # `agent` 不在名单里：`agent/core.Agent` **就是演员**（PATTERN['actor'] 覆盖它），
    # 单列一个键会让"演员"有两份模式声明，反而是隐患。
    # [EN] `agent` is not in the roster: `agent/core.Agent` **is the actor** (PATTERN['actor'] overrides
    # [EN] it),
    # [EN] Listing it as a separate key would give the "actor" two mode declarations, which is a hazard
    # [EN] instead.
    keys = list(R.keys()) + ['polish_agent']
    miss = [k for k in keys if k not in COG.PATTERN]
    ok &= rec('A1 ★ 名册的每个职位 + 两个自主 Agent 都在模式表里',
              not miss, f'缺：{miss}')
    ok &= rec('A1 模式取值只在四种里（拼错的当场现形）',
              all(v in (COG.COT, COG.REFLECT, COG.BOTH, COG.NONE)
                  for v in COG.PATTERN.values()),
              str(sorted(set(COG.PATTERN.values()))))

    # 四类都要有 —— 全变 cot 或全变 none 都不该发生
    # [EN] All four categories must be present -- everything becoming cot or everything becoming none
    # [EN] should not happen
    kinds = set(COG.PATTERN.values())
    ok &= rec('A2 ★ 四种模式**都用上了**（不是一刀切）',
              kinds == {COG.COT, COG.REFLECT, COG.BOTH, COG.NONE},
              str(sorted(kinds)))

    # NONE 必须说得出理由
    # [EN] NONE must be able to state a reason
    none_bad = [k for k, v in COG.PATTERN.items()
                if v == COG.NONE and len(COG.why_none(k)) < 10]
    ok &= rec('A3 ★★ 每个「不引入」都说得出理由（不是漏做）',
              not none_bad, f'没说理由：{none_bad}')
    # COT / BOTH 必须有骨架
    # [EN] COT / BOTH must have a skeleton
    cot_bad = [k for k, v in COG.PATTERN.items()
               if v in (COG.COT, COG.BOTH) and not COG.THINK_STEPS.get(k)]
    ok &= rec('A3 ★★ 每个「先想后答」的职位都有思考骨架（不然开关是假的）',
              not cot_bad, f'没骨架：{cot_bad}')
    # 思考字段不许与模式矛盾
    # [EN] The thinking field must not contradict the mode
    field_bad = [k for k in COG.THINK_FIELD if COG.pattern(k) not in (COG.COT, COG.BOTH)]
    ok &= rec('A4 ★ 思考字段只给用了 CoT 的职位（字段与模式不许打架）',
              not field_bad, f'矛盾：{field_bad}')
    # ★★ 反过来也要成立：**有骨架的职位，模式必须是 cot/both**
    #   （改了模式却没删骨架 = 声明与实现打架：声明说"它不用 CoT"，骨架却在注入）
    # [EN] ★★ The converse must also hold: **positions with a skeleton must have mode cot/both**
    # [EN] (changing the mode without deleting the skeleton = declaration fighting implementation: the
    # [EN] declaration says "it does not use CoT", yet the skeleton is still being injected)
    orphan = [k for k in COG.THINK_STEPS
              if COG.pattern(k) not in (COG.COT, COG.BOTH)]
    ok &= rec('A4 ★★ 有骨架的职位，模式必须是 cot/both（模式与骨架一一对应）',
              not orphan, f'打架：{orphan}')
    ok &= rec('A4 ★★ 有思考字段的职位，骨架表里也得有它（三张表不许各说各话）',
              not [k for k in COG.THINK_FIELD if not COG.THINK_STEPS.get(k)],
              str([k for k in COG.THINK_FIELD if not COG.THINK_STEPS.get(k)]))
    ok &= rec('A4 `why_none` 对非 NONE 的返回空串（两套口径不重叠）',
              all(COG.why_none(k) == '' for k, v in COG.PATTERN.items()
                  if v != COG.NONE))

    # ★★ 骨架出处必须在该职位货架里 —— 挂了一条它没读过的手艺 = 骨架在教它没学过的
    # [EN] ★★ The skeleton source must be on that position's shelf -- attaching a craft it has not read =
    # [EN] the skeleton is teaching it something it never learned
    from craft import craftmix
    bad_ref = []
    for k, steps in COG.THINK_STEPS.items():
        allowed = set(A.SHELVES.get(k) or ())
        for _ask, ref in steps:
            if not ref:
                continue
            e = craftmix.resolve_entry(ref)
            if not e or str(e.get('_货架') or '') not in allowed:
                bad_ref.append(f'{k}:{ref}')
    ok &= rec('A5 ★★ 骨架里每一条手艺都是**这个职位读得到的**'
              '（跨架点名 = 职位声明是假的）',
              not bad_ref, f'越界：{bad_ref}')
    seen = {ref for steps in COG.THINK_STEPS.values() for _a, ref in steps if ref}
    ok &= rec('A5 骨架里挂的手艺**真的在工艺库里**（名字对得上）',
              all(craftmix.resolve_entry(r) for r in seen),
              str([r for r in seen if not craftmix.resolve_entry(r)]))

    # 演员那几条：这是"像不像人说话"的核心，缺一条都算退步
    # [EN] The actor's items: this is the core of "does it sound like a human speaking"; missing any
    # [EN] one counts as a regression
    actor_refs = [r for _a, r in COG.THINK_STEPS.get('actor', ())]
    # ★★ 2026-10-12（用户点名"很容易吼 而不是正常说话"）：
    #   骨架从四条加到五条 —— 补的是**开口前最后一个念头**（该用什么声音说）。
    #   判据从"正好四条"改成**更硬的两件事**：
    #     ① 四条老的自问**一条不少**（按出处条目名逐个核，不是数字数）；
    #     ② 音量那一条必须**排在最后** —— 位置是这一条的要点：
    #        紧挨着台词的那一问才管得住"动不动就吼"，夹在中间就白写了。
    # [EN] ★★ 2026-10-12 (the user named this: "it shouts easily instead of speaking normally"):
    # [EN] the skeleton grows from four to five -- what is added is **the last thought before speaking**
    # [EN] (what voice to use).
    # [EN] The criterion changes from "exactly four" to **two harder things**:
    # [EN] 1) the four old self-questions are **all still there** (checked one by one by source entry
    # [EN] name, not by counting);
    # [EN] 2) the volume one must come **last** -- position is the point of this entry: the question
    # [EN] right next to the line is what governs "shouting at the drop of a hat"; stuck in the middle
    # [EN] it would be wasted.
    _actor_need = {'一句台词办四件事', '停顿与不答也是台词',
                   '说话方式就是身份', '话长短由处境定'}
    ok &= rec('A6 ★★ 演员的骨架：四条老的自问**一条不少**，'
              '且「音量是稀缺的」排在**最后**（开口前最后一个念头）',
              _actor_need <= set(actor_refs)
              and actor_refs[-1] == '音量是稀缺的',
              str(actor_refs))
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 提示词层
# [EN] B. Prompt layer
# ══════════════════════════════════════════════════════════════
def test_prompt_block() -> bool:
    ok = True
    from crew import cognition as COG
    from craft import craftmix

    blk = COG.cot_block('actor')
    ok &= rec('B1 ★ 演员的骨架非空，且把答案指向 `推演`',
              bool(blk) and '推演' in blk, blk[:80].replace('\n', ' | '))
    ok &= rec('B1 四条自问都在（逐条查文本，不只看非空）',
              all(t in blk for t in ('要什么', '刚才', '换给别人说', '该说'))
              and '开口之前' in blk, blk[:120].replace('\n', ' | '))
    # ★★ 手艺是**真从工艺库取的原文** —— 换一条条目名，贴出来的提示词就跟着变
    # [EN] ★★ The craft is **the original text taken from the craft library for real** -- change an entry
    # [EN] name, and the pasted prompt changes accordingly
    tip = str((craftmix.resolve_entry('说话方式就是身份') or {}).get('提示词') or '')
    ok &= rec('B2 ★★ 骨架里贴的是**工艺库里那条手艺的原文**（不是写死的套话）',
              bool(tip) and tip[:18] in blk, tip[:40])
    ok &= rec('B2 出处条目名也一并给出（作者能顺着去查那一架）',
              '说话方式就是身份' in blk, '')

    # 每个 cot/both 的都要有骨架
    # [EN] Every cot/both one must have a skeleton
    empty = [k for k, v in COG.PATTERN.items()
             if v in (COG.COT, COG.BOTH) and not COG.cot_block(k)]
    ok &= rec('B3 ★ 所有用了 CoT 的职位都生得出骨架', not empty, str(empty))
    # NONE 的必须生不出
    # [EN] NONE ones must not be able to produce one
    leak = [k for k, v in COG.PATTERN.items() if v == COG.NONE and COG.cot_block(k)]
    ok &= rec('B3 ★ 「不引入」的职位**生不出骨架**（骨架不越界）',
              not leak, str(leak))
    # 纯反思的（reviewer/rehearsal/settings_room）也不该有骨架
    # [EN] Pure reflection ones (reviewer/rehearsal/settings_room) also should not have a skeleton
    ref_only = [k for k, v in COG.PATTERN.items()
                if v == COG.REFLECT and COG.cot_block(k)]
    ok &= rec('B3 ★ 纯反思型职位不为它套 CoT（它本身就是反思的落点）',
              not ref_only, str(ref_only))
    # 散文产出的职位：骨架不要求落字段
    # [EN] Positions with prose output: the skeleton is not required to land in a field
    nv = COG.cot_block('novelist')
    ok &= rec('B4 ★ 小说作家（散文产出）的骨架**不要求写字段**'
              '（要求了剧作者就得先剥壳）',
              bool(nv) and '不必写出来' in nv and '构思' not in nv,
              nv[:80].replace('\n', ' | '))

    # ★★ 逐字退回：关总闸 / 关分闸
    # [EN] ★★ Verbatim fallback: turn off the master switch / turn off the sub-switch
    with _CfgGuard(COGNITION='false'):
        off = [k for k in COG.THINK_STEPS if COG.cot_block(k)]
        ok &= rec('B5 ★★ `COGNITION=false` → 所有骨架消失（逐字退回）',
                  not off, str(off))
    with _CfgGuard(COT_ACTOR='false'):
        ok &= rec('B5 ★ `COT_ACTOR=false` → 演员那条没了，剧组那条还在',
                  COG.cot_block('actor') == ''
                  and bool(COG.cot_block('screenwriter')),
                  repr(COG.cot_block('actor'))[:40])
    with _CfgGuard(COT_CREW='false'):
        ok &= rec('B5 ★ `COT_CREW=false` → 剧组那条没了，演员那条还在',
                  COG.cot_block('screenwriter') == ''
                  and bool(COG.cot_block('actor')))
    # 关闸之后**真的与从前一字不差**：不是"短一点"，是空串
    # [EN] After turning the switch off, **it is truly identical to before, character for character**: not
    # [EN] "a bit shorter", but an empty string
    with _CfgGuard(COGNITION='false'):
        ok &= rec('B5 ★★ 关闸后的返回是**空串**（提示词里那段整个不出现）',
                  COG.cot_block('actor') == '' and COG.cot_block('polisher') == '')
    return ok


# ══════════════════════════════════════════════════════════════
#  C. 行为级：演员的 prompt 里真有它
# [EN] C. Behavior level: it really is in the actor's prompt
# ══════════════════════════════════════════════════════════════
class _FakeDB:
    def __init__(self):
        self.mem: list = []

    def retrieve_memory(self, *a, **k):
        return []

    def add_memory(self, agent, content, mem_type='obs', importance=5.0, **k):
        self.mem.append((mem_type, content))

    def count_memories(self, *a, **k):
        return 0

    def get_summaries(self, *a, **k):
        return []

    def recent_events(self, *a, **k):
        return []


def _make_actor():
    from agent.core import Agent
    from world.state import WorldState, PersonState, GameTime
    w = WorldState()
    w.scene = '临河茶肆'
    w.clock = GameTime()
    db = _FakeDB()
    ps = PersonState(name='主角', location='临河茶肆', role='前台',
                     identity='茶肆掌柜', personality='话少，先听后说',
                     catchphrase='（不说话）', current_goal='把账上的窟窿弄清')
    w.people['主角'] = ps
    w._db = db
    return Agent(ps, db, w), w


def test_actor_prompt() -> bool:
    ok = True
    from agent import core as AC
    from agent.core import Action

    a, _w = _make_actor()
    seen: dict = {}
    real = AC.llm.chat

    async def fake_chat(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''
        # ⚠ 真实调用要 `return_meta=True`（`decide` 用的是 `raw, meta = ...`）——
        #   第一版这里只回一个字符串，于是 `decide` 在解包处就抛了、
        #   直接降级成 wait，**根本没走到解析那一段**（判据当场抓出来）。
        # [EN] ⚠ Real calls must use `return_meta=True` (`decide` uses `raw, meta = ...`) --
        # [EN] The first version returned only a string here, so `decide` threw at the unpacking site,
        # [EN] directly degrading to wait, **never even reaching the parsing section** (the criterion caught it
        # [EN] on the spot).
        return (json.dumps({'动作': 'speak', '参数': {'目标': ''},
                            '台词': '账上的窟窿我记着呢。', '内心': '不能让他知道',
                            '推演': '我要的是把话压住，先认下来。',
                            '理由': '稳住他'}, ensure_ascii=False), {})

    AC.llm.chat = fake_chat
    try:
        with _CfgGuard(COGNITION='true'):
            seen.clear()
            act_on = asyncio.run(a.decide())
            p_on = seen['prompt']
        with _CfgGuard(COGNITION='false'):
            seen.clear()
            act_off = asyncio.run(a.decide())
            p_off = seen['prompt']
    finally:
        AC.llm.chat = real

    # ⚠⚠ **指纹必须用骨架独有的整句**，不能用"开口之前"这种泛词 ——
    #   2026-10-18 晚给演员加了手艺条目「邻接对」，它的提示词是
    #   "这一拍**开口之前**先看：上一个人问的是谁"，于是关掉认知之后
    #   p_off 里照样有这四个字 ⇒ C1 假红（产品没坏，判据的指纹太短）。
    # [EN] ⚠⚠ The fingerprint must be the skeleton's **own full sentence**, never a generic word
    # [EN] like "before speaking": the `adjacency pair` craft entry added to the actor on 2026-10-18
    # [EN] contains exactly those four characters, so `p_off` still had them and C1 went false red.
    _FP = '开口之前，先在心里按顺序过一遍'
    ok &= rec('C1 ★★ 打开的：演员**真发出去的那段 prompt** 里有思考骨架',
              _FP in p_on and '不成立才算说到我身上' in p_on,
              p_on[-260:].replace('\n', ' | '))
    ok &= rec('C1 ★★ 骨架**排在去 AI 清单之后**（离那句台词最近）',
              p_on.find('开口之前') > p_on.find('【去 AI') if '【去 AI' in p_on
              else True, '')
    ok &= rec('C1 ★★ 关掉总闸的：同一函数发出的 prompt 里**一个字都没有**'
              '（逐字退回，不是"短一点"）',
              _FP not in p_off and '不成立才算说到我身上' not in p_off,
              p_off[-200:].replace('\n', ' | '))
    ok &= rec('C1 ★ prompt 里的 JSON 格式要求带上 `推演`（模型才知道往哪写）',
              '"推演"' in p_on and '"推演"' not in p_off,
              '')
    ok &= rec('C2 ★★ 模型给的 `推演` **真的被解析进 `Action.think_trace`**',
              '把话压住' in act_on.think_trace, repr(act_on.think_trace))
    ok &= rec('C2 ★ 模型**没给**那一项时，解析拿空串、不报错（宽容读法）',
              _decide_without_think() == '', '')
    ok &= rec('C2 ★ 它**不进台词/内心**（盘算是私下那几句，不是给人看的心声）',
              '把话压住' not in act_on.dialogue
              and '把话压住' not in act_on.inner_thought,
              f'dialogue={act_on.dialogue!r} inner={act_on.inner_thought!r}')
    return ok


def _decide_without_think() -> str:
    """模型没写 `推演` 时，`think_trace` 该是空串（**不报错、不降级**）。

    ⚠ 这一条是"宽容读法"的另一半：`take_think`/解析都不许因为少一个字段
      就把整条决策判成失败 —— 骨架在提示词里，它至少先想过一遍才开口。
    
        English:
    When the model does not write `推演`, `think_trace` should be an empty string (**no error, no
    degradation**).
        ⚠ This is the other half of the "lenient reading": neither `take_think` nor parsing is allowed, because of one missing field,
          to judge the entire decision as a failure -- the skeleton is in the prompt, it at least thought it through once before speaking.
    """
    from agent import core as AC
    a, _w = _make_actor()
    real = AC.llm.chat

    async def fake_chat(tier, messages, **kw):
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '测试'}, ensure_ascii=False), {})

    AC.llm.chat = fake_chat
    try:
        with _CfgGuard(COGNITION='true'):
            return asyncio.run(a.decide()).think_trace
    finally:
        AC.llm.chat = real


# ══════════════════════════════════════════════════════════════
#  D. 行为级：剧作者的 `构思`
# [EN] D. Behavior level: the playwright's `构思`
# ══════════════════════════════════════════════════════════════
def test_crew_prompt() -> bool:
    ok = True
    from crew import agents as A
    from crew.agents import SetCtx
    from llm import replies as R
    from llm.replies import Reply
    from world.state import WorldState, GameTime, PersonState

    w = WorldState()
    w.scene = '临河茶肆'
    w.clock = GameTime()
    w.people['主角'] = PersonState(name='主角', location='临河茶肆')
    ctx = SetCtx(world=w, db=None, day=1, people=['主角'])

    seen: dict = {}
    real = A.ask

    async def fake_ask(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''
        return Reply(ok=True, value={
            '构思': '这一天的变：账上不对 → 有人不想被认出来。三拍各推一步。',
            '剧情简介': '今天要演的是把账上的窟窿摊到明面上。',
            '场景介绍': '堂里两盏灯，柜台后头一片暗。',
            '拍': [{'拍': 1, '场': '堂内', '发生': '掌柜又数了一遍那几文',
                    '推进': '账目不对被摊到明面上'}],
            '角色任务': {'主角': ['把少了的那几文弄清楚']}})

    A.ask = fake_ask
    try:
        with _CfgGuard(COGNITION='true'):
            note = asyncio.run(A.Screenwriter().work(ctx, story='样章'))
            p_on = seen['prompt']
        with _CfgGuard(COGNITION='false'):
            seen.clear()
            asyncio.run(A.Screenwriter().work(ctx, story='样章'))
            p_off = seen['prompt']
    finally:
        A.ask = real

    ok &= rec('D1 ★★ 剧作者发出去的 prompt 里有骨架 + `构思` 字段',
              '动手之前先想清楚' in p_on and '"构思"' in p_on,
              p_on[-300:].replace('\n', ' | '))
    ok &= rec('D1 ★ 骨架上挂了剧作那一架的手艺（一场一转变 / 可拍性检查）',
              '一场一转变' in p_on and '可拍性检查' in p_on, '')
    ok &= rec('D1 ★★ 关掉总闸后那段没了（逐字退回）',
              '动手之前先想清楚' not in p_off and '"构思"' not in p_off, '')
    ok &= rec('D2 ★★ 剧作者的 `构思` **真的进了产出**（`note.data`，随台账落盘）',
              '这一天的变' in str((note.data or {}).get('构思') or ''),
              str((note.data or {}).get('构思'))[:60])
    ok &= rec('D2 分拍照旧（新字段不挤掉老字段）',
              len(note.data.get('拍') or []) == 1
              and (note.data.get('角色任务') or {}).get('主角'),
              str(list((note.data or {}).keys())))
    return ok


# ══════════════════════════════════════════════════════════════
#  E. 反思链：台词自省（执行 → 反思 → 优化）
# [EN] E. Reflection chain: line self-review (execute -> reflect -> optimize)
# ══════════════════════════════════════════════════════════════
class _StubAgent:
    def __init__(self, name, lines):
        self.name = name
        self._lines = list(lines)
        self.calls = 0
        self.last_ctx = ''

    async def decide(self, ctx=''):
        self.calls += 1
        self.last_ctx = str(ctx or '')
        from agent.core import Action
        nxt = self._lines.pop(0) if self._lines else ''
        if isinstance(nxt, tuple):
            return Action(verb=nxt[0], reason='')
        return Action(verb='speak', dialogue=nxt, think_trace='上一遍的盘算ABC')


def _make_loop():
    from sim.loop import RunLoop
    loop = RunLoop.__new__(RunLoop)
    loop._review_left = CFG.i('ACTOR_SELF_REVIEW_MAX')
    loop._warn_once = lambda tag, msg: None
    return loop


def test_self_review() -> bool:
    ok = True
    from crew import cognition as COG
    from agent.core import Action
    from sim.loop import RunLoop

    # ── 判据本身：窄 ──
    # [EN] -- The criterion itself: narrow --
    ok &= rec('E1 ★ 规则判得出"明显不像人话"（书面字眼 / 太长）',
              bool(COG.unnatural_reason('因此我决定暂时不动这件事。'))
              and bool(COG.unnatural_reason('这是一句很长的话' * 5)),
              COG.unnatural_reason('因此我决定暂时不动这件事。'))
    ok &= rec('E1 ★★ 规则**不误报**：演示语料里那八句台词一句都不该被挑出来',
              all(not COG.unnatural_reason(x) for x in (
                  '「你今日话里有话。」', '「话就是话，哪来的里外。」',
                  '「那这盏灯，是给谁留的？」', '「留给会回来的人。」',
                  '「若他不回来呢？」', '「那就留给等他的人。」',
                  '「外头雨大，明日再走不迟。」', '「明日……明日的事，明日再说。」')),
              '')

    # ── 真改写 ──
    #: 一句"明显不像人话"的台词（含书面连接词「因此」）—— 后面好几条都要用它。
    # [EN] -- Real rewrite --
    # [EN] : A line that is "obviously not human speech" (containing the written connective "therefore") --
    # [EN] several later items will use it.
    long_line = '因此我不便再往下说了，这件事就此打住。'
    with _CfgGuard(COGNITION='true', ACTOR_SELF_REVIEW='true',
                   ACTOR_SELF_REVIEW_MAX='2'):
        loop = _make_loop()
        # ⚠ 桩**只给一次回答** —— `_self_review` 只调一次 `decide`，
        #   而那次回答就是"自省之后"的那句。第一版把原句也塞进桩里，
        #   于是"自省后仍说原话"被误判成"没改"（判据自己写错）。
        # [EN] ⚠ The stub **gives only one response** -- `_self_review` calls `decide` only once,
        # [EN] and that response is the line "after self-review". The first version stuffed the original line
        # [EN] into the stub as well,
        # [EN] so "still says the original after self-review" was misjudged as "did not change" (the criterion
        # [EN] itself was written wrong).
        ag = _StubAgent('主角', ['哦。'])
        got = asyncio.run(loop._self_review(ag, Action(verb='speak', dialogue=long_line,
                                                      think_trace='盘算XYZ')))
        ok &= rec('E2 ★★ 不像人话的台词**真的被自省改写**（用的是新那句）',
                  got.dialogue == '哦。' and ag.calls == 1,
                  f'got={got.dialogue!r} calls={ag.calls}')
        ok &= rec('E2 ★★ 自省时把**上一遍的盘算**递了回去（思维链二次利用）',
                  '盘算XYZ' in ag.last_ctx and '你刚才要说的那一句' in ag.last_ctx,
                  ag.last_ctx[:120].replace('\n', ' | '))
        ok &= rec('E2 ★ 提示词里说清了**为什么**不像人话（不是笼统一句"再说一遍"）',
                  '书面字眼' in ag.last_ctx, ag.last_ctx[-90:].replace('\n', ' | '))

        # ── 正常台词：一次都不多花 ──
        # [EN] -- Normal lines: not a single extra call is spent --
        loop2 = _make_loop()
        ag2 = _StubAgent('阿枝', ['账上的事，我记着呢。'])
        got2 = asyncio.run(loop2._self_review(
            ag2, Action(verb='speak', dialogue='账上的事，我记着呢。')))
        ok &= rec('E3 ★★ 正常台词**一次调用都不多花**（规则先粗筛）',
                  ag2.calls == 0 and got2.dialogue == '账上的事，我记着呢。',
                  f'calls={ag2.calls}')
        # 非台词动作不掺和
        # [EN] Non-line actions do not get involved
        loop3 = _make_loop()
        ag3 = _StubAgent('阿枝', ['因此我这样说，其实是因为我早已想清楚了这一切的来龙去脉。'])
        got3 = asyncio.run(loop3._self_review(
            ag3, Action(verb='move', target='门外')))
        ok &= rec('E3 非台词动作不掺和（它没有"像不像人话"这回事）',
                  ag3.calls == 0, f'calls={ag3.calls}')

        # ── 坚持原话 / 改成不说话了 ──
        # [EN] -- Insists on the original wording / changes to saying nothing --
        loop4 = _make_loop()
        ag4 = _StubAgent('主角', [long_line])          # 自省后仍说原话
        # [EN] Still says the original after self-review
        got4 = asyncio.run(loop4._self_review(
            ag4, Action(verb='speak', dialogue=long_line)))
        ok &= rec('E4 ★ 他**坚持原话**时尊重他（不硬改，也不丢）',
                  got4.dialogue == long_line, repr(got4.dialogue))
        loop5 = _make_loop()
        ag5 = _StubAgent('主角', [('wait',)])           # 自省后不说了
        # [EN] Says nothing after self-review
        got5 = asyncio.run(loop5._self_review(
            ag5, Action(verb='speak', dialogue=long_line)))
        ok &= rec('E4 ★ 自省后决定不说 → 变成 wait（别把原句塞回去）',
                  got5.verb == 'wait', got5.verb)

        # ── 预算 0 ──
        # [EN] -- Budget 0 --
        from types import SimpleNamespace as SN
        loop6 = _make_loop()
        loop6._review_left = 0
        ag6 = _StubAgent('主角', ['短句。'])
        got6 = asyncio.run(loop6._self_review(
            ag6, Action(verb='speak', dialogue=long_line)))
        ok &= rec('E5 ★ 预算 0 → 一次都不问（等同关掉）',
                  ag6.calls == 0 and got6.dialogue == long_line, f'calls={ag6.calls}')

    # ── 关掉开关：逐字退回 ──
    # [EN] -- Turn the switch off: verbatim fallback --
    from sim.loop import _self_review_budget
    for k, v in (('COGNITION', 'false'), ('ACTOR_SELF_REVIEW', 'false')):
        with _CfgGuard(**{k: v}):
            loop = _make_loop()
            # ⚠ 额度**从产品里取**（`_self_review_budget()`，`_tick` 用的就是它）——
            #   第一版这里自己重算了一遍表达式，那是"测自己写的式子"：
            #   产品改了它照样绿（反例法会当场揭穿）。
            # [EN] ⚠ The quota is **taken from the product** (`_self_review_budget()`, which is exactly what
            # [EN] `_tick` uses) --
            # [EN] The first version recomputed the expression itself here, which is "testing the formula you wrote
            # [EN] yourself":
            # [EN] when the product changes, it still goes green (the counterexample method would expose it on the
            # [EN] spot).
            loop._review_left = _self_review_budget()
            ag = _StubAgent('主角', ['短句。'])
            got = asyncio.run(loop._self_review(
                ag, Action(verb='speak', dialogue=long_line)))
            ok &= rec(f'E6 ★★ `{k}=false` → 产品自己给的额度是 0，自省一次都不走'
                      '（逐字退回）',
                      loop._review_left == 0 and ag.calls == 0
                      and got.dialogue == long_line,
                      f'left={loop._review_left} calls={ag.calls}')
    with _CfgGuard(COGNITION='true', ACTOR_SELF_REVIEW='true',
                   ACTOR_SELF_REVIEW_MAX='3'):
        ok &= rec('E6 ★ 都开着时额度就是旋钮那个数（旋钮真被读）',
                  _self_review_budget() == 3, str(_self_review_budget()))
    return ok


# ══════════════════════════════════════════════════════════════
#  F. 落地与隐私
# [EN] F. Landing and privacy
# ══════════════════════════════════════════════════════════════
def test_landing_and_privacy() -> bool:
    ok = True
    from agent.core import Action
    from sim.loop import RunLoop
    from crew.agents import SetCtx, OnDuty

    # ── 盘算进 `world.actor_think` ──
    # [EN] -- Deliberation goes into `world.actor_think` --
    loop = _make_loop()
    loop.world = SimpleNamespace(actor_think={})
    ag = _StubAgent('主角', [])
    ag.name = '主角'
    loop._note_think([(ag, Action(verb='speak', dialogue='x',
                                  think_trace='我要的是把账压住，先认下来。'))])
    ok &= rec('F1 ★★ 盘算落进 `world.actor_think`（作者能看见）',
              '把账压住' in str(loop.world.actor_think.get('主角') or ''),
              str(loop.world.actor_think))

    # ── 剧组台账「演员」那一行带上它 ──
    # [EN] -- The crew ledger's "actor" row carries it --
    ctx = SetCtx(world=loop.world, db=None, day=1, people=['主角', '阿枝'])
    line = OnDuty('actor')._fallback_line(ctx)
    ok &= rec('F2 ★★ 剧组台账的「演员」行里能读到那句盘算',
              '主角' in line and '把账压住' in line, line)

    # ── 隐私：盘算绝不进"场上刚发生" ──
    # [EN] -- Privacy: deliberation never goes into "just happened on stage" --
    class _BS:
        def backstage_people(self):
            return [SimpleNamespace(name='阿福')]

    lp = _make_loop()
    lp._backstage = _BS()
    only_think = lp._mentioned_names(
        [(ag, Action(verb='wait', think_trace='阿福阿福阿福阿福'))])
    ok &= rec('F3 ★★ 盘算里提到后台的人 → **不把他拉上台**（盘算是私下的）',
              only_think == set(), str(only_think))
    spoken = lp._mentioned_names(
        [(ag, Action(verb='speak', dialogue='去把阿福请来'))])
    ok &= rec('F3 ★ 而台词里提到他 → 照旧算"被点名"（这条没被改坏）',
              spoken == {'阿福'}, str(spoken))
    ok &= rec('F3 ★ 源码层面：`_mentioned_names` 的扫描字段里**没有** think_trace',
              'think_trace' not in
              __import__('inspect').getsource(RunLoop._mentioned_names), '')

    # ── 认知模式那一列真的在台账上（模式表的"产品侧读者"）──
    #   ⚠ 模式表如果只有判据在读，它和"写着好看的注释"没区别 ——
    #     台账是作者会翻的那一页，在那儿写清"谁先想后答、谁只是审"才算真用上。
    # [EN] -- The cognition-mode column is really on the ledger (the mode table's "product-side reader") --
    # [EN] ⚠ If the mode table is only read by the criterion, it is no different from "a comment written to
    # [EN] look nice" --
    # [EN] The ledger is the page the author will flip through; only by writing clearly there "who thinks
    # [EN] before answering, who merely reviews" is it truly put to use.
    from crew.studio import Studio
    st = Studio(world=SimpleNamespace(game_day=1), db=None)
    md = st.ledger_md()
    lines = [l for l in md.splitlines() if l.startswith('|') and '**' in l]
    by_name = {l.split('**')[1]: l for l in lines}
    ok &= rec('F4 ★★ 剧组台账里有「认知」一列（模式表被作者读得到）',
              '| 认知 |' in md, md.splitlines()[4] if len(md.splitlines()) > 4 else '')
    ok &= rec('F4 ★★ 四个标签真的印上去了：演员=思维链+反思 · 复盘=反思链 · '
              '道具=—（不引入）',
              '思维链+反思' in by_name.get('演员', '')
              and '反思链' in by_name.get('复盘', '')
              and by_name.get('道具', '').count('—') >= 2,
              f"演员={by_name.get('演员','')[:60]} 道具={by_name.get('道具','')[:60]}")
    return ok


# ══════════════════════════════════════════════════════════════
#  G. 反假按钮：新旋钮真被产品源码读到
# [EN] G. Anti-fake button: the new knob is really read by the product source
# ══════════════════════════════════════════════════════════════
def test_knobs() -> bool:
    from config import SPEC
    miss = [k for k in NEW_KNOBS if k not in SPEC]
    ok = rec('G1 ★ 五个新旋钮都在 SPEC 里', not miss, f'缺：{miss}')

    skip = {'.venv', '__pycache__', '.git', 'logs', 'assets', 'packages',
            'generated-images', '发布版本', 'node_modules', '.workbuddy',
            'samples', 'tools', 'developers', 'tests'}
    src = ''
    for p in sorted(APP_DIR.rglob('*.py')):
        if any(s in p.parts for s in skip) or p.name == 'config.py':
            continue
        try:
            src += p.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
    zero = [k for k in NEW_KNOBS
            if f'"{k}"' not in src and f"'{k}'" not in src]
    ok &= rec('G1 ★★ 每个新旋钮都被**产品源码**字面量读过（一个假按钮都没有）',
              not zero, f'零读取：{zero}')
    ok &= rec('G2 ★ 总闸真的在最前面拦（`COGNITION` 在 `cognition.py` 里被读）',
              "'COGNITION'" in (APP_DIR / 'crew' / 'cognition.py').read_text(
                  encoding='utf-8'), '')
    ok &= rec('G2 ★ 自省那两个旋钮在 `sim/loop.py` 里被读（不是只在面板上）',
              all(f"'{k}'" in (APP_DIR / 'sim' / 'loop.py').read_text(
                  encoding='utf-8') for k in ('ACTOR_SELF_REVIEW',
                                              'ACTOR_SELF_REVIEW_MAX')), '')
    return ok


if __name__ == '__main__':
    print('认知模式（思维链 / 反思链 / 组合）—— 验证', flush=True)
    ok = True
    try:
        head('A. 模式表（数据）')
        ok &= test_table()
        head('B. 提示词层（骨架真进提示词 / 逐字退回）')
        ok &= test_prompt_block()
        head('C. 行为级：演员决策')
        ok &= test_actor_prompt()
        head('D. 行为级：剧作者')
        ok &= test_crew_prompt()
        head('E. 反思链：台词自省')
        ok &= test_self_review()
        head('F. 落地与隐私')
        ok &= test_landing_and_privacy()
        head('G. 反假按钮')
        ok &= test_knobs()
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
    report['ok'] = bool(ok)
    (OUT / 'cognition_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n认知模式验证：{passed}/{len(report["checks"])}'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1500:])
    sys.exit(0 if report['ok'] else 2)
