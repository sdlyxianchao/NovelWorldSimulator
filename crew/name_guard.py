# -*- coding: utf-8 -*-
"""**人名歧义守卫** —— 设定阶段就该拦下的问题。

★★★ 由来（2026-10-20 晚，一份外部批评暴露的）
============================================
外部 AI 读望江楼那篇，第一条批评是：

> 「'我'（第一人称主角）与'沈砚'同时出现，但'沈砚'究竟是第三人称角色名
>   还是动作描述（'沈砚'作为动词）？阅读时需反复猜测。」
> 处方：「若'沈砚'是动词，应改为'别问'或'不必多问'」

**诊断对，处方会毁掉整本书。**

查了设定（`望江楼模拟项目/02_项目设定.md`）：「沈砚」在三处同时是三个东西 ——
  楼名 **望江楼**、掌柜人名 **沈砚**、楼的规矩「**不问来路，不问去处**」，
而掌柜的口头禅正是「**沈砚。**」
这是作者的核心双关。改成「别问」，这个双关就没有了。

**但它暴露的读者困惑是真的。** 实测 v2 正文：人名出现 10 次，
其中 **9 次在句首**，最糟的一次是：

    。沈砚柜台后抹壶          ← 读者会读成「别问，柜台后面抹壶……」

⇒ 真正该修的不是名字，是**句法**：句首人名紧接谓语时，与常用短语同形的名字
   会被读成祈使句。加一个身份标记（「掌柜沈砚…」）或用介词隔开（「沈砚对柳氏…」）
   就消歧了，一个字都不用改设定。

## 两条可数的东西

1. `collides(name)` —— **名字是否形似常用短语**。
   纯结构判：首字是文言否定/疑问虚字（莫/勿/无/未/何/焉/岂/休/安），
   次字是常见动词（问/说/管/道/想/料/知/提/言）。
   「沈砚」= 莫+问 ⇒ 命中；「岛村」「翠翠」「王熙凤」⇒ 不命中。
   ⚠ 这**不是**"名字起错了"的判断，只是"这个名字有歧义风险，正文要小心"。

2. `risky_positions(text, name)` —— **正文里哪些位置真的会被误读**。
   形态：句首（标点/引号/换行之后）+ 名字 + **直接跟谓语**。
   「沈砚对柳氏…」不算（有介词"对"顶着）；「沈砚柜台后抹壶」算。
   这条**与名字是否冲突无关**，是通用的句法纪律 —— 但对冲突名才致命。

## 为什么放在 `crew/` 而不是 `world/`
它要被**两个地方**用：设定装配时（提前提醒作者）与导出检查时（事后报告）。
放这里两边都能 import，且不依赖 `world` 的构造。
[EN] A guard for ambiguous character names: `collides()` spots names that read like a
[EN] common phrase, `risky_positions()` finds the spots in the prose where such a name is
[EN] most likely misread (sentence-initial, followed directly by a predicate). This is a
[EN] **syntax** fix, not a rename -- the measured case was a deliberate pun that a rename
[EN] would have destroyed.
"""
from __future__ import annotations

import re

#: 文言里"否定/劝阻/疑问"类的**首字**。名字以这些字开头，就容易与常用短语同形。
_LEAD = set('莫勿无未何焉岂休安毋罔靡')
#: 常见的**次字**（动词/谓词性）。首字 + 次字构成"像一句话"的短词。
_NEXT = set('问说道管想料知提言须必可要能动得来去行走看听')

#: 名字后面紧跟这几个字时**不算歧义** —— 它们是明确的"说话/朝向"引导词，
#: 读者一看就知道后面是人名在做主语（「沈砚对柳氏说」读不成祈使句）。
_SAFE_AFTER = tuple('对向朝把将和与跟问说笑叹道答嚷叫喊看盯望低抬转站坐走退')
#: 明确的介词/连词首字（同上，给"紧跟"判据留出安全出口）
_SAFE_LEAD = tuple('对向朝把将和与跟')


def collides(name: str) -> bool:
    """这个名字**是否形似常用短语**（有被读成一句话的风险）。

    只判两位以上的名字；单字名一律返回 False（「昭」「棠」这类不会误读成句子）。
    """
    n = str(name or '').strip()
    if len(n) < 2:
        return False
    return n[0] in _LEAD and n[1] in _NEXT


def risky_positions(text: str, name: str) -> list[tuple[int, int, str]]:
    """正文里**会被误读**的位置 → `[(start, end, 命中片段)]`。

    判据（三条同时成立才算）：
      ① 名字前面是**句读**（`。！？；」”"` 或换行/开头）——
         句首是最容易被当成新句子开头的位置；
      ② 名字后面**没有**紧跟引号、标点、或"对/向/朝"这类引导词；
      ③ 名字后面确实跟着汉字（否则它就是个孤立的名字，不会误读）。

    ⚠ 只对 `collides()` 为真的名字有意义 —— 别的名字（「岛村柜台后抹壶」）
      读者不会读成祈使句，因为"岛村"不是动词短语。
      但函数本身不检查这一点：调用方决定要不要先过 `collides()`。
    """
    n = str(name or '').strip()
    raw = str(text or '')
    if not n or not raw:
        return []
    out: list[tuple[int, int, str]] = []
    # 句首 = 开头，或紧跟在句读/引号/换行之后
    pat = re.compile(r'(?:^|[。！？；」”"\n])(' + re.escape(n) + r')(.{0,2})')
    for m in pat.finditer(raw):
        tail = m.group(2) or ''
        if not tail:
            continue                       # ③ 后面什么都没有：孤立的名字
        if tail[0] in '，。！？；：、」”"\'）)…—-~': 
            continue                       # ② 紧跟标点：那是一句完整的话，不是谓语
        if tail.startswith(_SAFE_LEAD):
            continue                       # ② 紧跟介词：读者不会读成祈使句
        out.append((m.start(1), m.end(1), m.group(0).strip()))
    return out


def first_mention_hint(text: str, names) -> list[str]:
    """**首次出场**没有身份交代的名字。

    外部批评的建议里唯一可取的一条：「需在首次出场时明确交代」。
    可数形态：这个名字第一次出现时，**同一句里有没有出现任何身份词**
    （掌柜/老板/先生/姑娘/大人/夫人/公子…），没有就算"没交代"。

    ⚠ 只对 `collides()` 为真的名字报 —— 别的名字首次出场不带身份词是常态
      （「岛村盘腿坐着」没人会误解他是谁）。
    """
    raw = str(text or '')
    out: list[str] = []
    for name in names or ():
        n = str(name or '').strip()
        if not n or not collides(n):
            continue
        pos = raw.find(n)
        if pos < 0:
            continue
        # 取这个名字所在的**整句**（前后各退到最近的句读）
        left = max(raw.rfind(ch, 0, pos) for ch in '。！？\n') + 1
        right = min([x for x in (raw.find(ch, pos) for ch in '。！？\n') if x > 0],
                    default=len(raw))
        line = raw[left:right]
        if any(w in line for w in ('掌柜', '老板', '先生', '姑娘', '大人',
                                   '夫人', '公子', '小姐', '师父', '老爷')):
            continue
        out.append(f'「{n}」首次出场时没有身份交代（形似常用短语，容易被读成一句话）：'
                   f'…{line.strip()[:40]}…')
    return out


def report(text: str, names) -> list[str]:
    """一份给人看的清单（进日志 / 导出记录）。空列表 = 没问题。"""
    lines: list[str] = []
    for name in names or ():
        n = str(name or '').strip()
        if not collides(n):
            continue
        hits = risky_positions(text, n)
        if hits:
            lines.append(f'「{n}」有 {len(hits)} 处会被误读成祈使句'
                         f'（句首 + 紧跟谓语）：' +
                         '、'.join(h[2][:14] for h in hits[:3]))
    lines += first_mention_hint(text, names)
    return lines


__all__ = ['collides', 'risky_positions', 'first_mention_hint', 'report']
