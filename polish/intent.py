# -*- coding: utf-8 -*-
"""**作者这句话是什么意思** —— 把打磨对话里的口语指令解析成**结构化意图**。

用户 2026-10-11 夜报（原话）：
    「摄取的时候还是有问题 系统给我列出了4个自查问题 我说**修复4个问题**
      但是它不知道我什么意思 **而且反复让我修改**
      我让它**修复所有自查问题 不要问我** 也不行 **必须一轮一问**
      我想如果我跟它说 **至少多少轮不要问我 修复所有问题**
      或者说**修复所有问题 不要问我** 他应该理解并执行才对」

## 为什么非要一个专门的模块（不能只靠提示词）

上一版把「作者说的是哪几条」这件事**全托给模型**（`polish/agent.py` 的协议第 7 条
写着"他说「1」「2」指的是上面那几条编号建议"）。实测不够：
模型**数不清**"4 个问题"到底对应哪四条，也没法**保证不问**（它想确认就会问）。

这两件事都是**程序能算准**的：
  · "上面有几条、编号是几" —— 我们手里就有那份列表（自查问题 / 体检编号）；
  · "作者说不要问我" —— 这是一句**可以识别的意图**，识别出来就该**在代码里
    拦住那次反问**，而不是求模型"配合一下"。

所以这里只做三件事（纯函数，零 LLM、零 IO、可单测）：

| 识别 | 例子 | 得到 |
|---|---|---|
| **点名的编号** | 处理 1 2 / 先改第 2 条 / 前两个 / 后面那条 | 编号列表（1 起算） |
| **整批** | 修复所有问题 / 修复4个问题 / 全都改掉 / 都改了 | 全部条目 |
| **免打扰** | 不要问我 / 至少3轮不要问我 / 以后别问我 | 多少轮不问 |

★ **免打扰是可以撤销的**：作者说一句「可以问我了」，`noask_all` 就解除 ——
  否则一次"别问我"会把后面的对话永久变成哑巴，那比反复问更糟。

English:
**What does this sentence from the author mean** -- parse spoken instructions in the polishing
conversation into a **structured intent**.
User report, late 2026-10-11 (verbatim):
  "There is still a problem during ingestion. The system listed 4 self-check problems for me, I said
  **fix the 4 problems**, but it does not understand what I mean, **and it keeps making me revise**.
  I told it to **fix all the self-check problems and don't ask me**, that doesn't work either -- it
  insists on **one question per round**. I think if I tell it **don't ask me for at least N rounds,
  fix all problems**, or say **fix all problems, don't ask me**, it should understand and do it."
## Why a dedicated module is required (a prompt alone is not enough)
The previous version left "which items does the author mean" **entirely to the model** (item 7 of the
protocol in `polish/agent.py` says "when he says 1, 2 he means those numbered suggestions above").
Measured: not good enough -- the model **cannot count** which four items "4 problems" refers to, and
it cannot **guarantee not asking** (when it wants to confirm, it asks).
Both of these are things **code can compute exactly**:
  · "how many items there are above and what their numbers are" -- we already hold that list
    (self-check problems / checkup numbering);
  · "the author says don't ask me" -- that is a **recognisable intent**, and once recognised the
    question must be **blocked in code**, not begged for from the model.
So this module does exactly three things (pure functions: no LLM, no IO, unit-testable):
| Recognise | Examples | Result |
|---|---|---|
| **Named numbers** | process 1 2 / change item 2 first / the first two / the one after | list of numbers (1-based) |
| **The whole batch** | fix all problems / fix the 4 problems / change them all | every item |
| **Do not disturb** | don't ask me / don't ask me for at least 3 rounds / don't ask me anymore | how many rounds not to ask |
★ **Do-not-disturb is revocable**: once the author says "you can ask me now", `noask_all` is lifted --
  otherwise a single "don't ask me" would silence the rest of the conversation forever, which is worse
  than asking repeatedly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from i18n import t

#: 中文数字（够用就行：编号不会超过十来条）。
# [EN] Chinese numerals (only the ones we need: the numbering never exceeds a dozen or so).
_CN_DIGITS = {'一': 1, '两': 2, '二': 2, '三': 3, '四': 4, '五': 5,
              '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

#: "别问我"这类意思的动词部分（前面通常还有个否定词）。
# [EN] The verb part of the "don't ask me" family (usually preceded by a negation).
_NOASK = re.compile(
    r'(不要|不用|不必|不需要|无需|别|甭)\s*(再)?\s*'
    r'(问我|问我了|问|征求我的意见|征求我意见|让我确认|找我确认|打断我|烦我|吵我|请示)'
    r'|(自己|你)(决定|看着办|拿主意|拿个主意|先做主)'
    r'|(不用|不必|不要)\s*(再)?\s*(确认|问我确认)'
    r'|(尽管|直接)\s*(动手|做|改|推进)')


#: **撤销**免打扰："可以问我了"。
# [EN] **Revoking** do-not-disturb: "you can ask me now".
_ASK_AGAIN = re.compile(
    # ⚠ "要问我" 前面必须是**否定以外**的字 —— 不然"不**要问我**"会被读成
    #   "要我重新问你"（实测踩到：'修复所有自查问题 不要问我' 被理解反了）。
    # [EN] The char before "要问我" must **not** be a negation -- otherwise "don't ask me"
    # [EN] is read as "do ask me again" (measured: 'fix all self-check problems, don't ask me'
    # [EN] was understood backwards).
    r'(?<![不别甭无需])(可以|能|请|该|要)\s*(再)?\s*(问我|问一下我)'
    r'|(问我|问一下)吧'
    r'|(有问题|拿不准)\s*(就|要)\s*(问我|问)')

#: "全部 / 所有"这一类词。
# [EN] The "all / every" family of words.
_ALLW = r'(所有|所有的|全部|全部所有|全都|统统|通通|一切|每个|各个|逐条|一条不落)'
#: "修 / 改 / 处理"这一类动词。
# [EN] The "fix / change / handle" family of verbs.
_FIXW = r'(修复|修好|修完|修补|改好|改掉|改正|改完|改过|改动|解决|处理|收拾|搞定|过一遍|整一遍|看一下)'

_FIX_ALL = re.compile(
    _ALLW + r'[^。！？!?\n]{0,10}' + _FIXW
    + r'|' + _FIXW + r'[^。！？!?\n]{0,10}' + _ALLW
    + r'|都\s*(给)?\s*(改|修|处理|解决|搞定|收拾|弄)'
    # 上面那条不许裸着用 `都` —— 它必须紧跟（至多一个"给"之后）一个动词
    # （"都改了""这些都给处理了"），否则"我都听你的"也会被当成"全改"。
    # [EN] The rule above must not use a bare `都` -- it has to be immediately followed by a verb
    # [EN] ("都改了"), otherwise "我都听你的" would also be taken as "change everything".
)

#: "N 个问题 / 这 N 条"这类**计数**说法（它们说的是"一共几条"，不是"第几条"）。
# [EN] The **counting** phrasing "N problems / these N items" (it says "how many in total", not
# [EN] "which one").
_COUNT = re.compile(r'(这|那)?\s*(\d+|[一二两三四五六七八九十]+)\s*(个|条|项|处|点)?\s*'
                    r'(问题|自查|建议|毛病|缺陷|条目)')

#: "第 N 条"。
# [EN] "item N".
_ORDINAL = re.compile(r'第\s*(\d+|[一二两三四五六七八九十]+)\s*(条|个|点|项|处)?')

#: "前 N 个 / 后 N 条"。
# [EN] "the first N / the last N".
_HEAD_TAIL = re.compile(r'(前|后)\s*(\d+|[一二两三四五六七八九十]+)\s*(条|个|点|项|处)?')

#: 裸数字（不是"第 3 章"这类）。前后不许再贴着数字，免得把 `12` 拆成 `1`、`2`。
# [EN] Bare numbers (not things like "chapter 3"). No adjacent digits allowed before/after, so `12`
# [EN] is not split into `1` and `2`.
_BARE_NUM = re.compile(r'(?<![\d第])(\d{1,2})(?![\d])')


def _num(s: str) -> int | None:
    """把 `3` / `三` / `两` 都读成整数（读不出来给 `None`）。
        English:
    Read `3` / `三` / `两` as an integer (`None` when unreadable).
    """
    s = str(s or '').strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s in _CN_DIGITS:
        return _CN_DIGITS[s]
    # 十X / X十（够用：12 → 十二）
    # [EN] ten-X / X-ten (enough for our needs: 12 -> 十二)
    if '十' in s:
        head, _, tail = s.partition('十')
        a = _CN_DIGITS.get(head, 1 if not head else None)
        b = _CN_DIGITS.get(tail, 0 if not tail else None)
        if a is not None and b is not None:
            return a * 10 + b
    return None


@dataclass
class PolishIntent:
    """作者这一句话解析出来的意图（**全部字段都可为空** = 就是一句普通的话）。
        English:
    The intent parsed from this one sentence (every field may be empty = just an ordinary sentence).
    """

    #: "接下来 N 轮不要问我"（0 = 没这条）
    # [EN] "Do not ask me for the next N rounds" (0 = not present)
    noask_rounds: int = 0
    #: "以后别问我"（一直到作者说"可以问我了"）
    # [EN] "Don't ask me anymore" (until the author says "you can ask me now")
    noask_all: bool = False
    #: "可以问我了"（撤销上面的）
    # [EN] "You can ask me now" (revokes the above)
    ask_again: bool = False
    #: "所有问题都修了"
    # [EN] "fix every problem"
    fix_all: bool = False
    #: 点名的编号（1 起算）
    # [EN] The named item numbers (1-based)
    picks: list[int] = field(default_factory=list)
    #: 展开成"这一轮要做的事"（编号 → 原文）
    # [EN] Expanded into "things to do this round" (number -> source text)
    work: list[str] = field(default_factory=list)
    #: 给作者看的一句"我懂你的意思了"
    # [EN] One line for the author saying "I understood you"
    note: str = ''


def looks_like_fix(text: str) -> bool:
    """这句话是不是在**让我干活**（而不是闲聊 / 提问）。
        English:
    Is this sentence **telling me to work** (rather than small talk / a question)?
    """
    return bool(re.search(_FIXW, str(text or ''))) or bool(_ALLW and
                                                            re.search(_ALLW, str(text or '')))


def parse(instruction: str, *, problems: list[str] | None = None,
          review: list[str] | None = None) -> PolishIntent:
    """把作者这一句话解析成 `PolishIntent`。

    `problems` 是**上一轮自查出来的那几条**（编号 1..N），`review` 是体检报告里
    「建议优先打磨」那几条（也是 1..N）。指代**先认自查**（作者刚看到的就是它），
    自查为空再认体检。
    [EN] Parse this one sentence into a `PolishIntent`.
    [EN] `problems` are **the items self-checked in the previous round** (numbered 1..N), `review`
    [EN] are the "suggested priorities" from the checkup report (also 1..N). References resolve
    [EN] **against self-check first** (that is what the author just saw), falling back to the checkup
    [EN] when self-check is empty.
    """
    text = str(instruction or '')
    problems = list(problems or [])
    review = list(review or [])
    src = problems or review
    out = PolishIntent()
    if not text.strip():
        return out

    # ── ① 免打扰 ──
    # [EN] -- 1. Do not disturb --
    if _ASK_AGAIN.search(text):
        out.ask_again = True
    if _NOASK.search(text):
        m = re.search(r'(\d+|[一二两三四五六七八九十]+)\s*轮', text)
        n = _num(m.group(1)) if m else None
        if n and n > 0:
            out.noask_rounds = min(int(n), 99)
        else:
            out.noask_all = True

    # ── ② 整批 vs 点名 ──
    # [EN] -- 2. Whole batch vs named items --
    if out.ask_again and not _NOASK.search(text):
        return out
    if not src:
        # 手里没有列表 → 只能识别"别问我"这一半；整批/点名都无从展开
        # （**不许编条目**：编出来的编号会指到没有的地方）。
        # [EN] With no list in hand, only the "don't ask me" half can be recognised; neither the whole
        # [EN] batch nor named items can be expanded.
        # [EN] (**Never invent items**: an invented number points at nothing.)
        return _with_noask_note(out, 0)

    # ⚠ 一律用 `finditer` + `group(1)`：`findall` 在**多分组**的正则上返回元组，
    #   直接把元组喂给 `_num` 会静默变成 `None`（实测：'先改第 2 条' 的 2 被判没了）。
    # [EN] Always use `finditer` + `group(1)`: on a regex with **several groups** `findall` returns
    # [EN] tuples, and feeding a tuple to `_num` silently yields `None` (measured: the 2 in
    # [EN] 'change item 2 first' was lost).
    count_m = _COUNT.search(text)
    counted = _num(count_m.group(2)) if count_m else None
    ordinal = [n for n in (_num(m.group(1)) for m in _ORDINAL.finditer(text)) if n]
    headtail = [(m.group(1), _num(m.group(2))) for m in _HEAD_TAIL.finditer(text)]
    # 裸数字：把"第 N"与"N 个问题"这两段先挖掉，剩下的数字才算"点名"
    # [EN] Bare numbers: dig out the "item N" and "N problems" spans first; what remains are "named"
    # [EN] numbers
    stripped = _COUNT.sub(' ', _ORDINAL.sub(' ', text))
    stripped = _HEAD_TAIL.sub(' ', stripped)

    if out.ask_again and not looks_like_fix(text) and not ordinal and not headtail:
        return _with_noask_note(out, len(src))

    # 整批：① 有"所有/全部+动词"；② 或"数出来的个数"正好等于列表长度
    # [EN] Whole batch: ① there is "all/every + verb"; ② or the "counted number" equals the list
    # [EN] length exactly
    if _FIX_ALL.search(text) or (counted is not None and counted == len(src)
                                 and looks_like_fix(text)):
        out.fix_all = True
        out.work = list(src)

    # 点名：ordinal（第 N 条）/ head-tail（前 N 个）/ 裸数字
    # [EN] Named: ordinal ("item N") / head-tail ("the first N") / bare numbers
    picks: list[int] = []
    for n in ordinal:
        if 1 <= n <= len(src):
            picks.append(n)
    for d, n in headtail:
        if not n:
            continue
        if d == '前':
            picks.extend(range(1, min(n, len(src)) + 1))
        else:
            picks.extend(range(max(1, len(src) - n + 1), len(src) + 1))
    if not picks and not out.fix_all:
        bare = [n for n in (_num(x) for x in _BARE_NUM.findall(stripped)) if n]
        bare = [n for n in bare if 1 <= n <= len(src)]
        # ⚠ **两个以上**才算点名：单个裸数字太容易是别的东西（"改3处"里的 3
        #   其实是数量）。"第 2 条"那种单个的由 `_ORDINAL` 负责。
        # [EN] ⚠ Only **two or more** count as named items: a single bare number is far too easily
        # [EN] something else (the 3 in "change 3 places" is really a quantity). Single ones like
        # [EN] "item 2" are handled by `_ORDINAL`.
        if len(bare) >= 2:
            picks.extend(bare)
    picks = sorted({p for p in picks if 1 <= p <= len(src)})
    out.picks = picks
    if not out.fix_all and picks:
        out.work = [src[i - 1] for i in picks]

    return _with_noask_note(out, len(src))


def _with_noask_note(out: PolishIntent, n_items: int) -> PolishIntent:
    """把「我懂你的意思了」那句话拼出来（**也是唯一的用户可见文案**）。
        English:
    Assemble the "I understood you" line (**also the only user-visible text**).
    """
    bits: list[str] = []
    if out.ask_again and not out.noask_all and not out.noask_rounds:
        bits.append(t('好，有问题我会再问你。'))
    if out.noask_rounds:
        bits.append(t('好，接下来 {n} 轮我不会问你 —— 拿不准的我自己定，'
                      '并把我的假设写在回话里。').format(n=out.noask_rounds))
    elif out.noask_all:
        bits.append(t('好，从现在起我不再问你（要我重新问你，说一句「可以问我了」）。'))
    if out.fix_all and out.work:
        bits.append(t('你说的是上面那 {n} 条 —— 这一轮我**全都**改掉。')
                    .format(n=len(out.work)))
    elif out.work:
        bits.append(t('我理解你要的是第 {x} 条 —— 这一轮就改这几条。')
                    .format(x='、'.join(str(i) for i in out.picks)))
    out.note = '\n'.join(x for x in bits if x)
    return out


def review_items(text: str) -> list[str]:
    """从**体检报告**里把编号条目抽出来（「1. 改哪里 —— 怎么改」那种）。

    抽不到就给空表 —— **严格按编号行认**，不要"看到有字就当条目"：
    体检报告里还有「【最突出的问题】」这类没有编号的段落，把它们也算进来的话
    "第 2 条"就会指错地方。
    [EN] Extract the numbered items from the **checkup report** (the "1. where -- how" kind).
    [EN] Return an empty list when none are found -- **recognise strictly by numbered lines**, do not
    [EN] treat "any text at all" as an item: the checkup report also contains unnumbered paragraphs
    [EN] like "the most glaring problem", and counting those in would make "item 2" point at the wrong
    [EN] place.
    """
    out: list[str] = []
    for ln in str(text or '').splitlines():
        # ⚠ 编号那一行**可能带段头**（体检报告是「【建议优先打磨】1. 改哪里 —— 怎么改」，
        #   1 号那一条**不在行首**）—— 所以先把段头剥掉再认，否则第 1 条永远收不到、
        #   后面因为"不连续"整列全丢（实测：整份报告抽出 0 条）。
        # [EN] ⚠ The numbered line **may carry a section header** (the checkup report writes
        # [EN] "【suggested priorities】1. where -- how", so item 1 is **not at the line start**) --
        # [EN] strip the header before matching, otherwise item 1 is never collected and everything
        # [EN] after it is dropped for "not consecutive" (measured: 0 items extracted from a whole
        # [EN] report).
        ln = re.sub(r'^\s*【[^】]{0,20}】\s*', '', ln)
        m = re.match(r'\s*(\d{1,2})\s*[.、)）]\s*(\S.*)$', ln)
        if not m:
            continue
        # 编号必须**从 1 连续**：跳到别的号（比如正文里的"2026."）就地收手。
        # [EN] The numbering must be **consecutive from 1**: stop as soon as it jumps (e.g. a literal
        # [EN] "2026." in the text).
        if int(m.group(1)) != len(out) + 1:
            break
        out.append(m.group(2).strip())
    return out
