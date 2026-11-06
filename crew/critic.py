# -*- coding: utf-8 -*-
"""**顾问（Advisor）** —— 判官只表态，不给改法，也不许给分。

★★★ 为什么要有这一层，以及它为什么**不是**又一个判据
==================================================
研究结论（见 `crew/reflexion.py` 顶部）：LLM 判官会偏向自己的输出、
分布外退化到接近抛硬币。所以这一层被**刻意压到最低权限**：

| 它**能**做的 | 它**不能**做的 |
|---|---|
| 指着给定的一条候选说"这是手法 / 这是打转" | 提议怎么改（改法归写稿那一方） |
| 说一句"删掉它读者会少读到什么" | 给总分、定通过与否（判定权在 `verdict`） |
| | 新增条目、引用没给出的内容 |

三条来自公开实践的具体约束，每一条都对应一类真实故障：

1. **理由先写、结论后写**（rationale-first）。
   出处那篇的实测很反常：把 rubric 改来改去掉不出效果，
   **唯一稳定的提升来自"强制先产出理由"这个机械约束**。
   同一份 rubric、只改输出顺序，一致性和误差都变好。
2. **能力不相交**（capability-disjoint）：没有任何组件既"提议"又"施加"。
   这里的具体含义是 —— **顾问不许写改法**。一旦它开始说"应该改成……"，
   它就同时成了写稿方，自偏好立刻回来。
3. **canary 对照**：混一条**明显是手法**的正常写法进去。
   如果它把这条判成"打转"，说明这个判官此刻不可信 ⇒
   **整批判定降级为"仅供参考"**，`trusted=False`，调用方应当原样保留稿子。
   研究里管这个叫"完美成绩本身可疑"的另一面：**判据要先能证明自己没坏**。

⚠ 这一层**永不单独否决**任何东西：`trusted=False` 时调用方必须回退到"什么都不改"，
  而不是"按它的意见改"。**宁可不动，不许改坏。**

[EN] An advisor, not a judge. It may only say "device or loop" for the candidates it is
[EN] given -- never how to fix them (that would make it a writer again, and
[EN] self-preference comes right back). Rationale comes before the verdict because that
[EN] mechanical ordering is the only reliably effective constraint in the cited work. A
[EN] built-in canary (an obviously-fine repetition) detects a broken judge: if it calls
[EN] the canary a loop, the whole batch is downgraded to advisory and the caller must
[EN] leave the prose untouched.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

_LOG = logging.getLogger(__name__)

#: 内建对照：一句话里"话题词重复"是**正常写法**（真人样本里满地都是）。
#: 判官若把它判成"打转"，说明它此刻在用"见过就算病"的粗糙标准。
CANARY_KEY = '__canary__'
CANARY_TEXT = ('「十五年前」在 3 句不同台词里出现，每句都在推进新信息'
               '（第一次说堤修于何时、第二次说今年还得量、第三次说是谁的徒弟）')

_VERDICT_RE = re.compile(r'^\s*(\d+)\s*[|｜]\s*(.+?)\s*[|｜]\s*(手法|打转)\s*$', re.M)


@dataclass
class Opinion:
    """顾问对一条候选的表态。**没有分数、没有改法**。"""
    index: int
    key: str
    is_device: bool
    reason: str

    def one_line(self) -> str:
        return f'{"手法" if self.is_device else "打转"}：{self.key} —— {self.reason}'


@dataclass
class Result:
    opinions: list[Opinion] = field(default_factory=list)
    trusted: bool = True
    why: str = ''
    raw: str = ''

    @property
    def loops(self) -> list[Opinion]:
        """被判为"打转"的那些（只有 `trusted` 时才该拿去当反思提示）。"""
        return [x for x in self.opinions if not x.is_device]

    def summary(self) -> str:
        if not self.opinions:
            return '顾问没有表态（保持原样）'
        return (f'{len(self.opinions)} 条：手法 '
                f'{sum(1 for x in self.opinions if x.is_device)} / 打转 {len(self.loops)}'
                + ('' if self.trusted else '（**不可信**：对照被判成打转）'))


def build_prompt(items: list[dict]) -> str:
    """拼提示词。**理由在结论之前**，这条顺序是硬要求，别改。"""
    rows = []
    for i, it in enumerate(items, 1):
        kind = str(it.get('kind') or '重复')
        detail = str(it.get('detail') or '')
        sample = str(it.get('sample') or '')
        rows.append(f'{i}. [{kind}] {detail}' + (f'　原句：{sample}' if sample else ''))
    body = '\n'.join(rows)
    return (
        '你是这本书的**审读顾问**。下面是从全书里挑出来的若干「重复形态」，'
        '请逐条判断：它是**手法**（读者会因此受益，该留）还是**打转**'
        '（删掉它读者不会损失什么，该改）。\n\n'
        f'{body}\n\n'
        '**输出格式**：一条一行，三栏用竖线隔开，顺序不能反：\n'
        '编号｜理由（不超过 30 字，必须说清"删掉它读者会少读到什么"）｜结论\n'
        '结论只能是「手法」或「打转」两个字之一。\n\n'
        '硬性要求（违反任何一条，这次表态都算无效）：\n'
        '- **先写理由，再写结论**。反过来写的行会被丢掉。\n'
        '- **只许用上面给出的编号**，不许新增条目、不许编造没出现过的句子。\n'
        '- **不许写"应该改成……"** —— 你只判断该不该留，怎么改不是你的事。\n'
        '- 不要开场白、不要总结、不要解释你在做什么。\n'
    )


def parse(text: str, items: list[dict]) -> list[Opinion]:
    """解析顾问的话。**认不出的行直接丢** —— 宁可少几条表态，不许瞎猜。

    ⚠ 要防的两种脏输出：模型把结论写在理由前面（顺序反了），
      以及它自己加了 `4.` 这种不存在的编号。前者被正则拒掉，
      后者按 `index` 越界丢掉。
    """
    out: list[Opinion] = []
    seen: set[int] = set()
    for m in _VERDICT_RE.finditer(str(text or '')):
        idx = int(m.group(1))
        if not (1 <= idx <= len(items)) or idx in seen:
            continue
        seen.add(idx)
        key = str((items[idx - 1] or {}).get('key') or items[idx - 1].get('kind') or idx)
        out.append(Opinion(index=idx, key=key,
                           is_device=(m.group(3) == '手法'),
                           reason=m.group(2).strip()[:60]))
    return out


async def review(items: list[dict], *, ask=None, tier: str = 'cheap',
                 use_canary: bool = True) -> Result:
    """让顾问看一眼这些候选。**没有 `ask` 就什么都不做**（零成本、零风险）。

    `ask` 形如 `async (messages, tier, purpose) -> str`。
    """
    items = [dict(x or {}) for x in (items or [])]
    if not items:
        return Result(why='没有候选')
    if ask is None:
        return Result(why='没有可用的顾问（保持原样）')

    probe = list(items)
    if use_canary:
        probe = probe + [{'kind': '对照', 'key': CANARY_KEY, 'detail': CANARY_TEXT}]
    prompt = build_prompt(probe)
    try:
        raw = await ask(prompt, tier, 'critic')
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('顾问表态失败（保持原样）：%r', e)
        return Result(why=f'调用失败：{e}')
    raw = str(raw or '')
    opinions = parse(raw, probe)
    if not opinions:
        return Result(why='一条都没解析出来（保持原样）', raw=raw)

    # ★ 对照：它把"明显是手法"的那条判成打转 ⇒ 这个判官此刻不可信。
    trusted, why = True, ''
    canary_idx = len(probe)
    for x in opinions:
        if x.index == canary_idx:
            if not x.is_device:
                trusted = False
                why = ('内建对照（话题词自然重复）被判成"打转" ⇒ '
                       '这一批表态不可信，调用方应原样保留')
            opinions = [y for y in opinions if y.index != canary_idx]
            break
    if not trusted:
        _LOG.warning('顾问 %s', why)
    return Result(opinions=opinions, trusted=trusted, why=why, raw=raw)


def hint_of(result: Result, limit: int = 6) -> str:
    """把顾问结论变成**给写稿方看的反思提示**。

    只在 `trusted` 时给东西 —— 不可信的表态拿去改稿就是"按坏判官改"。
    ⚠ 只挑"打转"的，且**不给改法**（改法是写稿方自己的事）。
    """
    if not result or not result.trusted:
        return ''
    lines = [f'- {x.key} 在反复出现，读起来像在原地打转（{x.reason}）'
             for x in result.loops[:limit]]
    return '\n'.join(lines)


__all__ = ['Opinion', 'Result', 'review', 'build_prompt', 'parse', 'hint_of',
           'CANARY_KEY', 'CANARY_TEXT']
