# -*- coding: utf-8 -*-
"""**选角**：把「演员类型」与「这本小说的角色」拼成一个人的演法。

用户 2026-10-07
--------------
「一般来说 剧组人员Agent是提前写好的 演员Agent 都是创建项目的时候生成的，
这个你有特别的优化技巧吗……或者说你按照现实世界的模式 先提前写好各种演员的
Agent 比如年轻男演员 女演员 小孩 老人 甜美型 高冷型等等 参考现实世界的演员类型，
每一种一个 等到开卷的时候 选择需要的类型 进行分配 如果同一种类型多余一个则复制
然后根据具体角色再定制修改 即**所有Agent 提示词分两部分 一部分预设 一部分根据
小说定制** 定制的部分优先级高于预设」

这个模块就是那句话的落地。四件事：

一、预设与定制是**两层**，不是一个拼盘
---------------------------------------
| 层 | 是什么 | 谁给的 | 随什么变 |
|---|---|---|---|
| **类型预设**（`archetypes.yaml`） | 这一类演员**怎么演**：语速、句长、身体习惯、待人接物的底色 | 演员自带 | 不随书变（一个类型演一百本书都这样） |
| **角色定制**（人物卡 + 选角细读） | 在这个本子里**演谁**：身份、处境、目标、秘密、关系、跟谁顶 | 剧本给的 | 一部一换 |

★ 关键在**冲突时怎么判**，而不是"两层都写上" —— 两层都写、不写仲裁规则，
模型会自己在两套说法里挑一套（每次挑的可能不一样，表现就是"这个人忽冷忽热"）。
仲裁规则写在提示词里，只有三条（见 `ARBITRATION`），核心一句：
**定制的「演谁」压过预设的「怎么演」；预设只管"怎么说"，不管"说什么"。**

二、同型多人：复制 + **变奏轴**，不是复制粘贴
-------------------------------------------
用户说"同一种类型多余一个则复制"。照字面复制会撞 —— 两个"青年·高冷"写出来
一模一样，读者分不出谁是谁。所以每个类型自带若干条**变奏轴**
（同一个类型必须能长出好几种人），实例化时按领取顺序取不同的那条。
这同时是**反刻板**的结构保证：一个类型只有一种演法，那它就是套路
（`哑类型` 判据会查这个）。

三、定制层的料从哪来
-------------------
不另加调用 —— 用已有的三样东西拼：
  ① 人物卡上原本就有的字段（性格/口癖/秘密/目标/红线）；
  ② **变奏轴**上分到的那一句（"你这一份是：冷在防"）；
  ③ 可选的一段**选角细读**（`casting` 字段，开卷时由已有那一步顺带产出的，
     写完直接挂到人物卡上）。**没有就不写** —— 不许为了凑"定制"而编。

四、与"假按钮"的关系
-------------------
类型库不是装饰：`cast_all()` 的产出**真的进演员决策提示词**
（`agent/core._persona_prompt`），并且落一份 `选角表.md` 给人看。
判据 `verify_casting` 会验"这话真的到了提示词里"，不是"函数存在"。

English:
**casting**: combine the "actor type" with "this novel's character" into one person's way of
acting.
user 2026-10-07
--------------
"Generally the crew Agent is written in advance; actor Agents are all generated when the project
is created,
do you have any special optimization tricks for this... or rather, follow the real-world
pattern: write various actor
Agents in advance, e.g. young male actor, actress, child, old person, sweet type, aloof type,
etc., referencing real-world actor types,
one for each kind, and when the book opens, select the needed types for assignment; if more than
one of the same type is needed, copy
and then customize/modify according to the specific role, i.e. **all Agent prompts have two
parts: one preset part and one customized
according to the novel**; the customized part takes priority over the preset"
This module is the implementation of that sentence. Four things:
One, preset and customization are **two layers**, not a mixed platter
---------------------------------------
| layer | what it is | who provides it | what it varies with |
|---|---|---|---|
| **type preset** (`archetypes.yaml`) | how this kind of actor **acts**: speech rate, sentence length, physical habits, default manner of dealing with people | comes with the actor | does not vary with the book (one type acts this way across a hundred books) |
| **role customization** (character card + casting close-read) | **who they play** in this script: identity, situation, goal, secret, relationships, who they clash with | provided by the script | changes per book |
★ the key is **how to arbitrate on conflict**, not "write both layers" -- write both layers
without arbitration rules,
and the model will pick one of the two accounts on its own (and may pick differently each time;
the symptom is "this person blows hot and cold").
The arbitration rules are written in the prompt, only three of them (see `ARBITRATION`), the
core one being:
**the customized "who to play" overrides the preset "how to act"; the preset only governs "how
to say it", not "what to say".**
Two, multiple of the same type: copy + **variation axis**, not copy-paste
-------------------------------------------
The user said "if more than one of the same type is needed, copy". Literal copying will collide
-- two "youth·aloof" written
identically, and the reader can't tell who is who. So each type carries several **variation
axes**
(the same type must be able to grow into several different people), and at instantiation time,
take a different one according to the order claimed.
This is also a structural guarantee of **anti-stereotyping**: a type with only one way of acting
is a cliché
(the `哑类型` criterion checks this).
Three, where the material for the customization layer comes from
-------------------
no extra call -- assemble from the existing three things:
  ① fields already present on the character card (personality/verbal tic/secret/goal/red line);
  ② the one sentence assigned on the **variation axis** ("your copy is: cold as defense");
  ③ an optional passage of **casting close-read** (the `casting` field, produced incidentally by the existing step at book-open time,
     and attached directly to the character card once written). **if absent, don't write it** -- do not fabricate just to fill out "customization".
Four, the relationship with the "fake button"
-------------------
the type library is not decoration: the output of `cast_all()` **really goes into the actor
decision prompt**
(`agent/core._persona_prompt`), and a copy of `选角表.md` is saved for human reading.
The criterion `verify_casting` verifies "this sentence really reached the prompt", not "the
function exists".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_LOG = logging.getLogger('nws.actors')

APP_DIR = Path(__file__).resolve().parent.parent
#: 类型库文件（**别直接用它** —— 路径一律走 `_types_path()`，那才是唯一来源）
# [EN] : Type library file (**do not use it directly** — always go through `_types_path()`, that is the
# [EN] only source of truth)
_LIB = APP_DIR / 'actors' / 'archetypes.yaml'

#: 单条预设进提示词时的字数上限（提示词里它只占一小段 —— 演员的上下文
#: 还要留给记忆、在场名单、导演提示那些。150 字上下是"够认得出这一类人"的量）
# [EN] : Character limit for a single preset when injected into the prompt (it only occupies a small
# [EN] segment there — the actor's context
# [EN] still needs room for memory, the present-cast list, director's notes and so on. Around 150
# [EN] characters is the amount needed to be "enough to recognize this kind of person")
_PRESET_CHARS = 150
#: 定制层的字数上限（人物卡的字段本来就短，这里防的是选角细读写太长）
# [EN] : Character limit for the customization layer (character card fields are short to begin with;
# [EN] this prevents casting detail from being written too long)
_CAST_CHARS = 220

_cache: dict[str, Any] = {}


# ══════════════════════════════════════════════════════════════
#  读库
# [EN] Read the library
# ══════════════════════════════════════════════════════════════
def load(force: bool = False) -> dict:
    """读 `archetypes.yaml`（带缓存）。读不了就返回空库（**不抛**）。
        English:
    read `archetypes.yaml` (with cache). If unreadable, return an empty library (**don't raise**).
    """
    if _cache and not force:
        return _cache
    data: dict[str, Any] = {'types': {}, 'match': {}, 'age': {}, 'default': ''}
    try:
        raw = yaml.safe_load(_types_path().read_text(encoding='utf-8')) or {}
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('演员类型库读不了（%s）—— 选角这一步退化为"不预设"', e)
        _cache.clear()
        _cache.update(data)
        return _cache
    if not isinstance(raw, dict):
        _cache.clear()
        _cache.update(data)
        return _cache
    skip = {'名称', '来源', '适用', '匹配表', '年龄表', '_DEFAULT'}
    for k, v in raw.items():
        if k in skip or not isinstance(v, dict):
            continue
        if not (v.get('骨架') or v.get('说话')):
            continue
        data['types'][str(k)] = v
    for field_name, slot in (('匹配表', 'match'), ('年龄表', 'age')):
        src = raw.get(field_name)
        data[slot] = {str(k): [str(x) for x in v]
                      for k, v in (src or {}).items() if isinstance(v, list)}
    data['default'] = str(raw.get('_DEFAULT') or '').strip()
    if not data['default'] and data['types']:
        data['default'] = sorted(data['types'])[0]
    _cache.clear()
    _cache.update(data)
    _LOG.info('演员类型库：%d 型 / 年龄 %d 组 / 气质 %d 组',
              len(data['types']), len(data['age']), len(data['match']))
    return _cache


def keys() -> list[str]:
    return sorted(load()['types'])


def entry(key: str) -> dict:
    """某一型（认不出返回 `{}` —— 调用方自己决定怎么兜）。
        English:
    a certain type (return `{}` if unrecognized -- the caller decides how to fall back).
    """
    return dict(load()['types'].get(str(key or '').strip()) or {})


def variants(key: str) -> list[str]:
    """某一型的变奏轴。空 = 这一型没写变奏（判据会报它）。
        English:
    the variation axes of a certain type. Empty = this type has no variations written (the criterion
    will flag it).
    """
    v = entry(key).get('变奏') or []
    return [str(x).strip() for x in v if str(x).strip()]


# ══════════════════════════════════════════════════════════════
#  匹配：人物卡上的字 → 类型
# [EN] Match: characters on the character card → type
# ══════════════════════════════════════════════════════════════
#
# ★★★ 2026-10-25 修的两个"子串误命中"（用户报的：一位六十来岁的被配成少年、一位老者被配成壮年）
# ------------------------------------------------------------------------
# 原来的匹配是 `if w in blob`，中文没有词边界 ⇒ 词表里的**短词会命中长词的一部分**。
# 实跑（某本书第 5 次）抓到两处，症状都是"年龄/气质凭空变了"：
#   ① 「六十来岁」**含**「十来岁」⇒ 六十岁的掌柜被配成 **少年**
#      （若词表里有「十岁」还会被配成「孩」—— 同一个坑更深的一层）；
#   ② 那天还顺带核了反向风险：「不老实」含「老实」⇒ 会被配成憨厚，
#      意思正好反过来。
# 修法不是"把词表改长一点"（换本书又会撞别的词），而是**给命中词查一下左右边界**：
#   · 年龄词：左边紧邻数字（六/三/8…）⇒ 它只是"一个更大数字的尾巴"，作废；
#   · 气质词：左边紧邻否定词（不/没/无…）⇒ 意思反过来，作废。
# ⚠ 作废的词**不直接丢**，先记成"弱命中"；等全表扫完都没有强命中时才用它。
#   为什么：`七八十岁` 里 `八十` 左边是 `七`，按边界规则该作废，可它确实指老年；
#   直接丢会让这一层**彻底配不上**（退化比误配更坏）。
# ⚠ 词本身以否定字开头时不算（`不正经` 就在痞气词表里，它左边是"很"也照样有效）。
# [EN] ★★★ Two substring false-positives fixed 2026-10-25 (user: 阿九 should be a youth,
# [EN] 沈砚 should be elderly). The old match was `if w in blob`, and Chinese has no word
# [EN] boundaries => a short word in the table matches **part of a longer word**. Two real hits:
# [EN] (1) 「六十来岁」 **contains** 「十来岁」 => a sixty-year-old shopkeeper was cast as a **teen**;
# [EN] (2) the mirror risk: 「不老实」 contains 「老实」 => cast as honest, the opposite meaning.
# [EN] The fix is not "make the word list longer" (another book hits other words) but a
# [EN] **boundary check** on each hit: an age word preceded by a digit is the tail of a larger
# [EN] number; a mood word preceded by a negation means the opposite.
# [EN] ⚠ A rejected hit is kept as a **weak** candidate and used only if nothing strong is found:
# [EN] in `七八十岁`, `八十` is preceded by `七`, yet it really does mean elderly -- dropping it
# [EN] outright would make the tier unmatchable (degrading is worse than a near miss).
# [EN] ⚠ If the word itself starts with a negation (`不正经` is in the 痞气 list), it still counts.

#: 数字（中文/阿拉伯）：年龄词左边紧邻它，就只是"一个更大数字的尾巴"
# [EN] Digits (Chinese/Arabic): an age word right after one is the tail of a larger number
_NUMERALS = set('〇零一二三四五六七八九十百千两几0123456789')

#: 否定词：气质词左边紧邻它，意思正好反过来
# [EN] Negations: a mood word right after one means the opposite
_NEGATIONS = set('不没无别未勿非')


def _boundary_ok(blob: str, i: int, w: str, kind: str) -> bool:
    """命中词 `w` 在 `blob[i]` 处的边界是否站得住（见上方那段说明）。

        English:
    Whether the hit `w` at `blob[i]` survives the boundary check (see the note above).
    """
    if kind not in ('age', 'mood'):
        return True
    prev = blob[i - 1] if i > 0 else ''
    if kind == 'age':
        return prev not in _NUMERALS
    # mood：`不老实` 里的 `老实` 作废；但 `不正经` 这种**自己带否定字**的词照旧
    return not (prev in _NEGATIONS and w[:1] not in _NEGATIONS)


def _hit_in(table: dict[str, list[str]], blob: str, kind: str = '') -> tuple[str, str]:
    """在 `{类别: [词…]}` 里找第一个**边界站得住**的命中，返回 `(类别, 词)`。

    两轮：先全表找强命中；一个都没有时才退回**第一个弱命中**（边界可疑的）。
    ⚠ 顺序必须是"全表扫完再退弱"，不能在同一个类别里遇到弱的就返回 ——
      否则 `六十来岁` 会在"少年"那一类里直接命中 `十来岁`，永远到不了"老年"的 `六十`。

        English:
    Find the first **boundary-passing** hit in `{category: [word...]}`, return `(category, word)`.
    Two rounds: scan the whole table for a strong hit first; only if there is none, fall back to
    the **first weak** (suspicious-boundary) hit.
    ⚠ It must be "finish the whole table before falling back", not "return the first weak one
      within a category" -- otherwise `六十来岁` would match `十来岁` inside the teen category and
      never reach `六十` in the elderly one.
    """
    weak: tuple[str, str] = ('', '')
    for cls, words in table.items():
        for w in words:
            if not w:
                continue
            i = blob.find(w)
            while i >= 0:
                if _boundary_ok(blob, i, w, kind):
                    return cls, w
                # ⚠ **只有年龄留弱命中**：`七八十岁` 里的 `八十` 确实是老年，
                #   丢掉它会让这一层彻底配不上（退化比近似更坏）。
                #   气质**不留**：`不老实` 取了反义，比"没配上"坏得多 ——
                #   宁可落默认型（还能看到"未命中"），也不要断言一个相反的性格。
                # [EN] ⚠ **Only age keeps a weak fallback**: `八十` inside `七八十岁` really does mean
                # [EN] elderly, and dropping it would make the tier unmatchable.
                # [EN] Temperament does **not**: `不老实` means the opposite, which is worse than no
                # [EN] match at all (the default type at least shows "not matched").
                if kind == 'age' and not weak[0]:
                    weak = (cls, w)
                i = blob.find(w, i + 1)
    return weak


#: 年龄层按岁数分档（只用于**人物卡里写了年龄却没写汉字**的情形，如 `年龄: 16`）
#: [EN] Age bracket by number (only when the card gives a bare number, e.g. `年龄: 16`)
_AGE_BY_NUMBER = ((10, '孩'), (17, '少年'), (30, '青年'), (55, '中年'), (200, '老年'))


def _age_from_number(text: str) -> tuple[str, str]:
    """`年龄: 16` / `十六岁` 这类**纯岁数** → 年龄层。取不到就返回 `('','')`。

    ⚠ 只在"作者显式写了年龄字段"时用，不拿它去扫性格/简介 ——
      简介里的数字多半是年份、排行、价钱（"十七岁那年"倒还好，"跑了十七趟"就坏了）。

        English:
    A bare age (e.g. `年龄: 16`) -> age bracket, `('','')` when it cannot be read.
    ⚠ Only used for the explicit age field, never for personality/intro text: numbers there are
      usually years, ranks or prices.
    """
    m = re.search(r'\d{1,3}', text or '')
    if m:
        num, hit = int(m.group()), m.group()
    else:
        # 汉字数字：只认"X岁 / 十X岁 / X十岁"这种明确的岁数写法
        m2 = re.search(r'([一二三四五六七八九十]{1,3})\s*岁', text or '')
        if not m2:
            return '', ''
        num = _cn_number(m2.group(1))
        if not num:
            return '', ''
        hit = m2.group(1) + '岁'
    if num <= 0:
        return '', ''
    for limit, age in _AGE_BY_NUMBER:
        if num <= limit:
            return age, hit
    return '', ''


_CN_DIGIT = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
             '六': 6, '七': 7, '八': 8, '九': 9}


def _cn_number(s: str) -> int | None:
    """`十六` → 16、`二十` → 20、`三十五` → 35、`十` → 10。认不出返回 None。

        English: `十六` -> 16, `二十` -> 20, `三十五` -> 35, `十` -> 10; None if unreadable.
    """
    s = (s or '').strip()
    if not s:
        return None
    if '十' not in s:
        return _CN_DIGIT.get(s) if len(s) == 1 else None
    a, _, b = s.partition('十')
    hi = _CN_DIGIT.get(a, 1) if a else 1
    lo = _CN_DIGIT.get(b, 0) if b else 0
    if (a and a not in _CN_DIGIT) or (b and b not in _CN_DIGIT):
        return None
    return hi * 10 + lo


def _resolve(*texts: str, age_pin: str = '') -> tuple[str, str, bool]:
    """`find()` 的实现，额外返回**年龄是不是从卡片上读到的**。

    `age_pin` = 人物卡上 `年龄/年纪/岁数` 字段的原文。**它优先**：
    作者写了年龄就照它定年龄层，不再去性格/简介里猜。

        English:
    The implementation behind `find()`, additionally returning **whether the age was read from the
    card**. `age_pin` is the raw text of the card's `年龄/年纪/岁数` field and takes **priority**:
    if the author wrote an age, that decides the bracket -- no guessing from personality/intro.
    """
    lib = load()
    types = lib['types']
    blob = ' '.join(str(x or '') for x in texts)
    if not types:
        return '', '', False

    age_tbl = lib.get('age') or {}
    mood_tbl = lib.get('match') or {}

    # ① 年龄层：**显式字段优先**，其次才扫卡片文字
    # [EN] ① Age bracket: the explicit field wins, otherwise scan the card text
    age, age_hit, from_card = '', '', False
    pin = str(age_pin or '').strip()
    if pin:
        age, age_hit = _hit_in(age_tbl, pin, kind='age')
        if not age:
            age, age_hit = _age_from_number(pin)
        from_card = bool(age)
    if not age:
        age, age_hit = _hit_in(age_tbl, blob, kind='age')
        from_card = bool(age)

    # ② 气质
    # [EN] ② Temperament
    mood, mood_hit = _hit_in(mood_tbl, blob, kind='mood')

    if age and mood:
        key = f'{age}·{mood}'
        if key in types:
            return key, (mood_hit or age_hit), False
        # ★★ 兜底 1：**同年龄层、换气质**（不是先换年龄层！）
        #   顺序是这一条设计的全部要点：年龄层管的是**嗓子与节奏**，
        #   它比"他是哪一类人"更难改 —— 一个七岁的小孩就算嘴上不饶人，
        #   也该是小孩的语速。先换年龄层的话，"七岁的毒舌"会变成
        #   一个成年人毒舌（判据 B2 当场抓到过这个顺序错误）。
        # [EN] ★★ Fallback 1: **same age bracket, switch temperament** (NOT switch age bracket first!)
        # [EN] The order is the entire point of this design: the age bracket governs **voice and rhythm**,
        # [EN] and it is harder to change than "what kind of person he is" — even if a seven-year-old is
        # [EN] sharp-tongued,
        # [EN] he should still have a child's speech rate. If you switch the age bracket first, "seven-year-old
        # [EN] snark" becomes
        # [EN] an adult being snarky (criterion B2 caught this ordering error on the spot).
        same_age = [k for k in sorted(types) if k.startswith(age + '·')]
        if same_age:
            _LOG.info('「%s」想要 %s·%s 但这一型不存在，落在同年龄层的 %s',
                      blob[:20], age, mood, same_age[0])
            return same_age[0], '', False
        # 兜底 2：**同气质、换年龄层**（尽量挨着）
        # [EN] Fallback 2: **same temperament, switch age bracket** (keep them adjacent if possible)
        for a in ('青年', '少年', '中年', '老年', '孩'):
            k2 = f'{a}·{mood}'
            if k2 in types:
                _LOG.info('「%s」配到 %s·%s 但这一型不存在，落到 %s',
                          blob[:20], age, mood, k2)
                # 换了年龄层 ⇒ 卡片上写的那个年龄已经不作数了，年龄是推的
                # [EN] the age tier was switched => the card's age no longer applies; it is inferred
                return k2, '', True
    # ③ 只有年龄配上了：同年龄层里挑一个（**这算"配上了"，所以带命中词**）
    # [EN] ③ Only the age matches: pick one within the same age bracket (**this counts as "matched", so
    # [EN] carry the hit word**)
    if age and age_hit:
        same_age = [k for k in sorted(types) if k.startswith(age + '·')]
        if same_age:
            # ★ 2026-10-25：先试**默认气质**（沉稳 = 库里最中性那一档）。
            #   原来的 `same_age[0]` 是**按字母序**挑 —— 那等于替作者断言了一个
            #   他根本没写的性格（`老人` 会变成 `老年·威严`）。B4 那条注释自己
            #   就写着"凭字母序挑的类型不是兜底"，同一条道理对气质也成立。
            # [EN] ★ 2026-10-25: try the **default temperament** first (沉稳 is the most neutral in
            # [EN] the library). The old `same_age[0]` picked **alphabetically**, i.e. asserted a
            # [EN] temperament the author never wrote (`老人` became `老年·威严`). Criterion B4
            # [EN] already says "a type chosen by alphabetical order is not a fallback"; the same
            # [EN] holds for temperament.
            dtone = str(lib.get('default') or '').split('·')[-1]
            prefer = f'{age}·{dtone}'
            if prefer in types:
                return prefer, age_hit, not from_card
            return same_age[0], age_hit, not from_card
    if mood and mood_hit:
        for a in ('青年', '少年', '中年', '老年', '孩'):
            k2 = f'{a}·{mood}'
            if k2 in types:
                # 只有气质配上 ⇒ 年龄层是这一型自带的，等于推的
                # [EN] only temperament matched => the age tier comes with the type, i.e. inferred
                return k2, mood_hit, True
    # ④ **什么都没配上** → 落默认型，而且命中是空的。
    #   ⚠ 不许在这里挑"随便一个同年龄层的型"：那等于用一个**凭字母序挑的**
    #     类型冒充兜底（判据 B4 抓到过）。兜底要有名字、可追溯。
    # [EN] ④ **Nothing matched** → fall to the default type, and the hit is empty.
    # [EN] ⚠ Do not pick "some random type in the same age bracket" here: that amounts to using a **type
    # [EN] chosen by alphabetical order**
    # [EN] to masquerade as the fallback (criterion B4 caught this). A fallback must have a name and be
    # [EN] traceable.
    d = str(lib['default'] or '')
    return (d if d in types else sorted(types)[0]), '', True   # 全兜底 ⇒ 年龄是推的


def find(*texts: str, age_pin: str = '') -> tuple[str, str]:
    """按人物卡的「性格 / 身份 / 简介」粗配类型，返回 `(类型, 命中的词)`。

    **两步**（顺序不能反）：
      ① 定**年龄层**（`年龄表`）—— 它管嗓子与节奏，比气质更难改，所以先定；
      ② 定**气质**（`匹配表`）。
    合成 `年龄层·气质`；这一型不存在时逐级兜底：同气质换年龄层 → 同年龄层
    换气质 → 落默认。**兜底一律返回空命中**（`''`），调用方要照实记下来 ——
    不许把"没配上"说成"配上了"。

    `age_pin`（可选）是人物卡上 `年龄/年纪/岁数` 的原文，给了就**优先**照它定年龄层。
    详见 `_resolve()`。

        English:
    roughly match a type by the character card's "personality / identity", return `(type, hit
    word)`.
        **two steps** (order cannot be reversed):
          ① determine the **age tier** (`年龄表`) -- it governs voice and rhythm, and is harder to change than temperament, so determine it first;
          ② determine the **temperament** (`匹配表`).
        compose `age tier·temperament`; when this type doesn't exist, fall back level by level: same temperament, different age tier → same age tier,
        different temperament → fall to default. **any fallback returns an empty hit** (`''`), and the caller must record it faithfully --
        do not describe "didn't match" as "matched".
        `age_pin` (optional) is the raw `年龄/年纪/岁数` text from the card; when given it takes
        **priority** for the age tier. See `_resolve()`.
    """
    key, hit, _ = _resolve(*texts, age_pin=age_pin)
    return key, hit


# ══════════════════════════════════════════════════════════════
#  一份选角
# [EN] A casting
# ══════════════════════════════════════════════════════════════
@dataclass
class Casting:
    """**一个人**的选角结果：类型 + 变奏 + 定制细读。
        English:
    **one person**'s casting result: type + variation + customized close-read.
    """

    name: str
    archetype: str = ''
    variant: str = ''
    matched: bool = False        # 类型是**配出来的**还是**兜底的**（照实记）
    hit: str = ''                # 命中的那个词（落盘给人看"为什么是这一型"）
    casting: str = ''            # 定制层：这一份"怎么演"（可空）
    break_type: str = ''         # 显式打破类型的那一处（可空）
    #: 年龄层是**推出来的**吗（2026-10-25 加）。
    #: `False` = 人物卡上写了年龄（`年龄:` 字段，或简介里"六十来岁"这种读得到的）；
    #: `True`  = 卡片上没有任何年龄信息，年龄是从气质/兜底顺序倒推的。
    #: ⚠ 这一位必须照实记：`人物卡命中「老实」` 听起来像"老实这个词决定了他是中年"，
    #:   其实年龄卡片上根本没写 —— 表上不区分，作者就看不出"该去补一行 `年龄:`"。
    #: [EN] whether the age tier was **inferred** (added 2026-10-25).
    #: [EN] `False` = the card states an age (`年龄:` field, or "六十来岁" readable from the intro);
    #: [EN] `True` = no age anywhere on the card and the tier was inferred from temperament/fallback
    #: [EN] order. ⚠ Must be recorded faithfully: "card matched 「老实」" sounds like that word
    #: [EN] decided he is middle-aged, when the card never said an age at all.
    age_guessed: bool = False
    # [EN] whether the type was **matched** or **fell back** (record it faithfully)
    # [EN] the word that was hit (persisted so people can see "why it is this type")
    # [EN] customization layer: how this one "performs" (nullable)
    # [EN] the place where the type is explicitly broken (nullable)

    @property
    def ok(self) -> bool:
        return bool(self.archetype)


def _clip(s: Any, n: int) -> str:
    t = ' '.join(str(s or '').split())
    return t if len(t) <= n else t[:n].rstrip() + '…'


def instantiate(name: str, card: dict | None, *, taken: dict[str, int] | None = None
                ) -> Casting:
    """按人物卡造一份选角。

    `taken` = 已领走的变奏计数 `{类型: 已用几个}` —— **同型多人靠它分流**：
    第 1 个用变奏[0]，第 2 个用变奏[1]……取完一轮从头来（并在日志里说一声，
    因为"取完一轮"意味着这一型的人已经多到该考虑换一型了）。
    
        English:
    Build a cast from the character cards.
        `taken` = count of variations already claimed `{type: how many used}` —— **same-type multiple people are split by it**:
        the 1st uses variation[0], the 2nd uses variation[1]... after a full round start over from the beginning (and announce it in the log,
        because "a full round taken" means this type already has enough people that switching to another type should be considered).
    """
    c = card or {}
    at = str(c.get('演员类型') or c.get('archetype') or '').strip()
    hit = ''
    age_guessed = False
    if at and at in load()['types']:
        matched = True                     # 作者点名的，算配上了
        age_guessed = False                # 点名的类型自带年龄层，不是推的
        # [EN] named by the author counts as matched
    else:
        # ★ 2026-10-25：把**显式年龄字段**也交给 `find()`，且它优先。
        #   以前只看 性格/身份/简介 —— 而人物的年龄常常单独写一行（`年龄: 十六`），
        #   结果"卡片写了年龄却没被读到"，只能从性格里猜（阿九就是这么变成中年的）。
        #   ⚠ 仍然**不读** 秘密/目标/红线：那三段是**前史**，"十来岁那年"、
        #     "上一世他才七岁"都写在那儿，拿它定当前年龄必错。
        # [EN] ★ 2026-10-25: also feed the **explicit age field** to `find()`, with priority. It used
        # [EN] to read 性格/身份/简介 only — yet age is often its own line (`年龄: 十六`), so "the card
        # [EN] said the age and nobody read it" and the age had to be guessed from temperament.
        # [EN] ⚠ Still **not** reading 秘密/目标/红线: those are backstory ("aged ten that year",
        # [EN] "in his last life he was seven") and would pin the wrong current age.
        age_pin = str(c.get('年龄') or c.get('年纪') or c.get('岁数') or '').strip()
        at, hit, age_guessed = _resolve(c.get('性格'), c.get('身份'), c.get('简介'),
                                       age_pin=age_pin)
        matched = bool(hit)
    vs = variants(at)
    v = str(c.get('变奏') or '').strip()
    if not v and vs:
        n = int((taken or {}).get(at, 0))
        if taken is not None:
            taken[at] = n + 1
        if n >= len(vs):
            _LOG.info('「%s」这一型已经排到第 %d 个（变奏只有 %d 条），变奏从头再来 '
                      '—— 这一型的人可能太多了，考虑换一型', at, n + 1, len(vs))
        v = vs[n % len(vs)] if vs else ''
    return Casting(
        name=str(name or '').strip(),
        archetype=at, variant=v, matched=matched, hit=hit,
        age_guessed=age_guessed,
        casting=_clip(c.get('选角') or c.get('casting') or '', _CAST_CHARS),
        break_type=_clip(c.get('打破类型') or c.get('break_type') or '', 80),
    )


def cast_all(people: list[dict] | dict) -> list[Casting]:
    """把整份人物表选一遍（同型自动分流变奏）。`people` 可以是列表或 `{名: 卡}`。
        English:
    Cast the entire character roster (same type auto-splits variations). `people` can be a list or
    `{name: card}`.
    """
    if isinstance(people, dict):
        rows = [(k, v) for k, v in people.items() if isinstance(v, dict)]
    else:
        rows = [(str(p.get('姓名') or p.get('name') or ''), p)
                for p in (people or []) if isinstance(p, dict)]
    taken: dict[str, int] = {}
    out: list[Casting] = []
    for name, card in rows:
        if not str(name or '').strip():
            continue
        out.append(instantiate(name, card, taken=taken))
    return out


# ══════════════════════════════════════════════════════════════
#  渲染：预设层 / 定制层 / 两层拼装
# [EN] Rendering: preset layer / customization layer / two-layer assembly
# ══════════════════════════════════════════════════════════════
#: ★★ 仲裁规则 —— **就这三条**，多一条都会被模型当成"可以商量的建议"。
# [EN] : ★★ Arbitration rules — **just these three**, any more and the model will treat them as
# [EN] "suggestions that can be negotiated".
#:
#: 为什么非要写死：两层都写、却不写冲突怎么办，模型会自己在两套说法里挑一套
#: （每次挑的可能还不一样）。表现就是"这个人忽冷忽热"、"上一拍还毒舌这一拍
#: 突然文雅" —— 而查起来极难，因为两个来源单看都对。
# [EN] : Why it must be hard-coded: if both layers are written but there is no rule for conflicts, the
# [EN] model will pick one of the two accounts on its own
# [EN] : (and it may pick differently each time). The symptom is "this person is hot and cold", "one
# [EN] beat he is snarky and the next beat
# [EN] : he suddenly turns refined" — and this is extremely hard to diagnose, because each source looks
# [EN] correct on its own.
ARBITRATION = """【两层的分工（冲突时按这个判）】
· 类型只管你**怎么演**：说话的快慢长短、身上的习惯、待人接物的底色。
· 角色只管你**演谁**：身份、处境、目标、秘密、跟在场谁亲谁远。
· **两个不一致时，以角色为准** —— 你是这个人，不是这个类型。
· 例外只有一处：下面「打破类型」里写着的那一点，照它演。
  那一点正是这个人最像人的地方，也是你**和别人不一样**的地方。"""


def render_preset(c: Casting, *, chars: int = _PRESET_CHARS) -> str:
    """**预设层**：这一类演员怎么演（不含他是谁）。认不出类型时返回空串。
        English:
    **Preset layer**: how this kind of actor performs (not who he is). Returns empty string when the
    type can't be recognized.
    """
    e = entry(c.archetype)
    if not e:
        return ''
    bits: list[str] = []
    sk = _clip(e.get('骨架'), 110)
    if sk:
        bits.append(sk)
    sp = e.get('说话') or {}
    if isinstance(sp, dict):
        w: list[str] = []
        if sp.get('句长'):
            w.append(f"句子{sp['句长']}")
        if sp.get('语速'):
            w.append(f"语速{sp['语速']}")
        if sp.get('口头禅'):
            ct = '、'.join(str(x) for x in (sp['口头禅'] or [])[:3])
            w.append(f"惯用{ct}")
        if w:
            bits.append('说话：' + '；'.join(w) + '。')
        if sp.get('忌讳'):
            bits.append(f"忌讳：{sp['忌讳']}。")
    if e.get('身体'):
        bits.append('身体：' + _clip(e['身体'], 60) + '。')
    if c.variant:
        bits.append(f"你这一份是：{c.variant}。")
    txt = '\n'.join(x for x in bits if x)
    return f"〔你这一类演员 · {c.archetype}〕\n{_clip(txt, chars)}"


def render_cast(c: Casting, card: dict | None = None) -> str:
    """**定制层**：在这个本子里演谁。没有料就返回空串（**不编**）。
        English:
    **Custom layer**: who he plays in this script. Returns empty string when there's nothing (**do
    not invent**).
    """
    k = card or {}
    rows = []
    # ★★★ 2026-10-28：**说话指纹**单列一行，紧挨口癖 —— 口癖是"听得见的那一下"，
    #   指纹是"怎么说话"（句长 / 抓手 / 心虚动作 / 称呼差）。两个人物的指纹撞了，
    #   遮住名字就分不出谁在说，而这就是编辑一眼圈出来的那种假。
    # [EN] ★★★ 2026-10-28: the **speech fingerprint** gets its own line right after the tic --
    # [EN] the tic is "the bit you hear"; the fingerprint is "how he talks". If two characters'
    # [EN] fingerprints collide, you cannot tell them apart with the names covered.
    for label, key in (('身份', '身份'), ('性格', '性格'), ('口癖', '口癖'),
                       ('说话指纹', '说话指纹'),
                       ('秘密', '秘密'), ('目标', '目标'), ('红线', '红线')):
        v = str(k.get(key) or '').strip()
        if v:
            rows.append(f'{label}：{v}')
    if c.casting:
        rows.append(f'这一份怎么演：{c.casting}')
    if c.break_type:
        rows.append(f'打破类型：{c.break_type}')
    if not rows:
        return ''
    return '〔在这个本子里，你演的是〕\n' + '\n'.join(rows)


def prompt_block(c: Casting, card: dict | None = None, *,
                 with_arbitration: bool = True) -> str:
    """**两层拼好的那一段**（进演员决策提示词的半固定层）。

    顺序是**预设在前、定制在后** —— 后写的更靠近模型的输出，也更容易压过前面
    （这是提示词位置上的常识，但更要紧的是"最后一句是仲裁规则"，
    模型读完两层之后紧接着读到"冲突时以角色为准"，判得最清楚）。

    没有类型（库读不了 / 类型认不出）时退化成只给定制层 —— **不许因此什么都不给**。
    
        English:
    **The segment with both layers assembled** (the semi-fixed layer fed into the actor decision
    prompt).
        Order is **preset first, custom second** —— what's written later is closer to the model's output and easier to override the earlier part
        (this is common sense about prompt position, but more important is that "the last sentence is the arbitration rule":
        after reading both layers the model immediately reads "when in conflict, defer to the character", which makes the judgment clearest).
        When there's no type (library unreadable / type unrecognized) degrade to giving only the custom layer —— **never give nothing because of that**.
    """
    pre = render_preset(c)
    cus = render_cast(c, card)
    if not (pre or cus):
        return ''
    parts = [x for x in (pre, cus) if x]
    if len(parts) == 2 and with_arbitration:
        parts.append(ARBITRATION)
    return '\n'.join(parts)


# ══════════════════════════════════════════════════════════════
#  落盘（给人看的那一页）
# [EN] Persistence (the page people read)
# ══════════════════════════════════════════════════════════════
def table_md(casts: list[Casting]) -> str:
    """`选角表.md`：谁演谁、凭什么配的、这一份的变奏是哪条。
        English:
    `选角表.md`: who plays whom, why it fits, and which variation this copy uses.
    """
    rows = ['# 选角表', '',
            '| 角色 | 演员类型 | 怎么配的 | 这一份的变奏 |',
            '|---|---|---|---|']
    for c in casts:
        if c.matched:
            how = f'人物卡命中「{c.hit}」'
            # ★ 2026-10-25：年龄**没写在卡片上**时必须说出来。
            #   原来只写「人物卡命中「老实」」，读起来像"老实这个词决定了他中年"——
            #   其实卡片上一个年龄字都没有，年龄是从气质倒推的（阿九就是这么变成中年的）。
            #   作者看到这半句才知道"该去补一行 `年龄:`"。
            # [EN] ★ 2026-10-25: when the age is **not written on the card**, say so. A bare
            # [EN] 「人物卡命中「老实」」 reads as "honesty made him middle-aged", when the card has
            # [EN] no age at all and the tier was inferred from temperament. Only this half-sentence
            # [EN] tells the author to add an `年龄:` line.
            if c.age_guessed:
                tier = (c.archetype or '').split('·')[0]
                how += (f'（**年龄未写**，按{tier}位推）' if tier else '（**年龄未写**）')
        else:
            how = '**未命中（兜底默认）**'
        rows.append(f'| {c.name} | {c.archetype or "（无）"} | {how} | '
                    f'{c.variant or "—"} |')
    n_def = sum(1 for c in casts if not c.matched)
    n_age = sum(1 for c in casts if c.matched and c.age_guessed)
    rows += ['', f'> 共 {len(casts)} 位；其中 **{n_def} 位没能在人物卡里配对**'
                 + (f'，**{n_age} 位的年龄卡片上没写**（那个年龄层是推出来的）' if n_age else ''),
             '> （落的是默认类型 —— 想让某位换个演法，',
             '> 在人物卡里写一行 `演员类型: 青年·毒舌` 即可，或写 `性格:` 让它自己配）。',
             '>',
             '> **想让年龄定死，就在人物卡里单独写一行** `年龄: 十六`（或 `年龄: 16`）——',
             '> 写了这一行，年龄层按它定，不再从性格倒推。',
             '> 只写在「简介」里时程序得靠关键词猜，容易猜偏（`六十来岁` 曾经被当成少年）。',
             '', '> 类型库在 `actors/archetypes.yaml`；'
                 '两层提示词的分工与优先级见 `actors/casting.py` 的模块头。']
    return '\n'.join(rows) + '\n'


# ══════════════════════════════════════════════════════════════
#  ★★ 四层的**可写入口**（2026-10-11）
# [EN] ★★ The **writable entry points** of the four layers (2026-10-11)
# ══════════════════════════════════════════════════════════════
#
# 用户问的那件事：
#   「演员Agent在系统层面是没有具体角色的 但是在项目层面是有具体角色的
#     演员Agent在系统全局设置（天机）中如何设置和在项目级别如何设置」
# [EN] The thing the user asked:
# [EN] "The actor Agent has no concrete role at the system level, but it does have a concrete role at
# [EN] the project level.
# [EN] How is the actor Agent configured in the system global settings (Tianji) and how is it
# [EN] configured at the project level?"
#
# 答案（也是本节的实现依据）——**按"换什么它才变"分四层**：
# [EN] Answer (also the implementation basis for this section) — **split into four layers by "what must
# [EN] change for it to change"**:
#
# | 层 | 存在哪 | 放什么 | 换什么它才变 | 界面入口 |
# [EN] | Layer | Where it lives | What it holds | What must change for it to change | UI entry point |
# |---|---|---|---|---|
# | ① 系统·职位 | `agents/actor.md` | 演员**这个工种**怎么干活 | 换软件版本 | 天机·剧组 Agents |
# | ② 系统·类型库 | `actors/archetypes.yaml` | **预写好的各种演员**（怎么说话） | 换软件版本 | 天机·剧组 Agents →「演员类型库」 |
# | ③ 项目·剧组 | `<项目>/agents/actor.md` | 这**一部戏**的演法基调 | 换书 | 项目·剧组 Agents |
# | ④ 项目·**角色** | `<项目>/设定集/人物.yaml` | **张三这个人**（身份+四个选角字段） | 换人 | 项目·剧组 Agents →「角色设置」 |
# [EN] | ① System·Position | `agents/actor.md` | how the actor **as a job type** works | software version change | Tianji·Crew Agents |
# [EN] | ② System·Type Library | `actors/archetypes.yaml` | **pre-written various actors** (how they talk) | software version change | Tianji·Crew Agents → "Actor Type Library" |
# [EN] | ③ Project·Crew | `<project>/agents/actor.md` | the performance baseline of **this one show** | change book | Project·Crew Agents |
# [EN] | ④ Project·**Role** | `<project>/settings/characters.yaml` | **this person Zhang San** (identity + four casting fields) | change person | Project·Crew Agents → "Role Settings" |
#
# ★★★ **一条硬约束（架构级的，不是偏好）**：
#   ④ 具体角色**绝不能写进任何一份 md**。
#   一个项目有 N 个角色、一份 `actor.md` 只有一段正文、而且**人人通读** ——
#   把"张三高冷、李四热情"写进去，等于让**每个角色都读到别人的设定**，
#   当场串台（张三会知道李四的秘密）。所以角色只能待在**一人一份**的记录里
#   （人物卡），由 `instantiate()` 各取各的。
#   判据 `verify_actor_layers` 的 D 组盯的就是这件事。
# [EN] ★★★ **One hard constraint (architectural, not a preference)**:
# [EN] ④ A concrete role **must never be written into any md file**.
# [EN] A project has N roles, an `actor.md` has only one body of text, and **everyone reads all of it**
# [EN] —
# [EN] writing "Zhang San is aloof, Li Si is warm" into it means **every role reads the others'
# [EN] settings**,
# [EN] immediate cross-talk (Zhang San would know Li Si's secrets). So a role can only live in a
# [EN] **one-per-person** record
# [EN] (the character card), with `instantiate()` taking each one separately.
# [EN] Group D of the criterion `verify_actor_layers` is watching exactly this.
#
# ⚠ 写文件的两条纪律（本模块是**产品里少数会写项目文件夹**的地方）：
#   1. **行级编辑**：只动目标那一个人的那几行，其它字节**逐字不动**
#      （包括作者手写的注释、未知字段、缩进风格）—— 整文件 `yaml.dump`
#      重写会把注释和字段顺序全丢掉，那是"静默丢内容"；
#   2. **先备份**：写之前存一份同目录的 `.bak`（同名文件只留最近一份）。
#      作者在界面上改坏了能自己捞回来。
# [EN] ⚠ Two disciplines for writing files (this module is **one of the few places in the product that
# [EN] writes to the project folder**):
# [EN] 1. **Line-level editing**: touch only the lines of that one target person, leave every other byte **byte-for-byte untouched**
# [EN] (including author-written comments, unknown fields, indentation style) — a whole-file
# [EN] `yaml.dump`
# [EN] rewrite throws away comments and field order, which is "silently losing content";
# [EN] 2. **Back up first**: before writing, save a `.bak` in the same directory (keep only the most recent one for a given filename).
# [EN] That way, if the author breaks something in the UI, they can fish it back themselves.
#
#: 人物表的文件名（在 `设定集/` 下）
# [EN] : Filename of the character table (under `settings/`)
PEOPLE_FILE = '人物.yaml'
#: 类型库的文件名（在软件根目录的 `actors/` 下）
# [EN] : Filename of the type library (under `actors/` in the software root directory)
TYPES_FILE = 'archetypes.yaml'

#: ④ 角色层**归界面管**的那四个字段（中文名 = 人物卡里的键名，与 `instantiate` 认的一致）。
#: ⚠ 顺序就是界面上从上到下的顺序；每一项 `(键, 中文标签, 控件类型)`。
# [EN] : The four fields of the ④ role layer that are **managed by the UI** (Chinese name = key name in
# [EN] the character card, consistent with what `instantiate` recognizes).
# [EN] : ⚠ The order is the top-to-bottom order in the UI; each item is `(key, Chinese label, control
# [EN] type)`.
CARD_FIELDS: tuple[tuple[str, str, str], ...] = (
    ('演员类型', '演员类型', 'type'),      # 从类型库选（也给"自动配"＝空）
    ('变奏', '这一份的变奏', 'variant'),   # 跟着所选类型走
    # [EN] Choose from the type library (also offers "auto-match" = empty)
    # [EN] Follows the chosen type
    ('选角', '选角细读（这一份怎么演）', 'text'),
    ('打破类型', '打破类型（只写一点）', 'text'),
)


def _cards_of(people) -> list[dict]:
    """`settings['people']` → `[{'姓名':…, **卡片}]`（过滤掉拿不到名字的）。
        English:
    `settings['people']` → `[{'姓名':…, **card}]` (filter out those whose names can't be obtained).
    """
    out: list[dict] = []
    for p in (people or []):
        if not isinstance(p, dict):
            continue
        nm = str(p.get('姓名') or p.get('name') or '').strip()
        if not nm:
            continue
        d = dict(p)
        d['姓名'] = nm
        out.append(d)
    return out


def load_cards(settings_dir) -> list[dict]:
    """读一个项目的**人物表**（`设定集/人物.yaml`）。读不到返回空表。

    ⚠ 它只读**项目级设定集**，不读运行文件夹里那份冻结的快照 ——
      界面上改的是"下一轮要用什么"，与正在跑的这一轮无关
      （`freeze_settings_into_run` 已经把这一轮的冻结好了）。
    
        English:
    Read a project's **character roster** (`设定集/人物.yaml`). Returns an empty table when it can't be
    read.
        ⚠ It only reads the **project-level settings set**, not the frozen snapshot in the run folder ——
          what's changed in the UI is "what to use for the next round", unrelated to the round currently running
          (`freeze_settings_into_run` has already frozen this round).
    """
    try:
        p = Path(settings_dir) / PEOPLE_FILE
        if not p.is_file():
            return []
        data = yaml.safe_load(p.read_text(encoding='utf-8')) or []
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('读人物表失败（当没有人物）：%r', e)
        return []
    return _cards_of(data)


def card_fields(card: dict) -> dict:
    """从一张人物卡里取出**归界面管的那四个字段**（缺的填空串）。

    ★ 同时认英文别名：手改过 `archetype:` 的人，界面上也该看到它，
      否则"他明明写了、界面却显示空"——那是会让人改第二遍的那种坑。
    
        English:
    Extract the **four fields managed by the UI** from a character card (fill missing ones with
    empty strings).
        ★ Also recognize English aliases: people who've hand-edited `archetype:` should also see it in the UI,
          otherwise "he clearly wrote it, but the UI shows empty" —— that's the kind of trap that makes people edit it a second time.
    """
    c = card or {}
    alias = {'演员类型': ('archetype',), '变奏': ('variant',),
             '选角': ('casting',), '打破类型': ('break_type',)}
    out: dict[str, str] = {}
    for key, _label, _kind in CARD_FIELDS:
        v = str(c.get(key) or '').strip()
        if not v:
            for a in alias.get(key, ()):
                v = str(c.get(a) or '').strip()
                if v:
                    break
        out[key] = v
    return out


def _yaml_scalar(s: str) -> str:
    """把一个值写成一行 YAML 标量（该加引号就加，别让 `:`/`#` 把行拆坏）。
        English:
    Write a value as a one-line YAML scalar (add quotes where needed, don't let `:`/`#` break the
    line).
    """
    t = ' '.join(str(s or '').split())
    if not t:
        return "''"
    #  ⚠ `,` 必须算进去：`口头禅` 是 flow 序列（`[a, b]`），值里带逗号会被拆成两项。
    # [EN] ⚠ `,` must be counted: `catchphrase` is a flow sequence (`[a, b]`), and a value containing a
    # [EN] comma will be split into two items.
    if any(ch in t for ch in ':#{}[]&*!|>\'"%@`,' ) or t[0] in '-? ' or t[-1] == ' ':
        return "'" + t.replace("'", "''") + "'"
    return t


def _backup(p: Path) -> None:
    """写之前留一份 `.bak`（同类文件只留最近一份，不越攒越多）。
        English:
    Keep a `.bak` before writing (only the most recent one per file type, don't let them pile up).
    """
    try:
        if p.is_file():
            (p.parent / (p.name + '.bak')).write_bytes(p.read_bytes())
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('备份 %s 失败（照样继续写）：%r', p.name, e)


def write_card(settings_dir, name: str, fields: dict) -> tuple[bool, str]:
    """把 ④ 角色层的那几个字段写回**人物表**（`设定集/人物.yaml`）。

    返回 `(成功?, 说明)`。**行级编辑**：只改目标那一个人名下的那几行，
    文件里其它部分**逐字不动**（作者手写的注释、别人的卡片、未知字段都在）。

    ★ 为什么不做整文件 `yaml.dump` 重写：那会把注释与字段顺序全丢掉。
      这条是本项目"不许静默丢内容"的直接推论 —— 而人物表恰恰是作者会手写的地方。
    ★ 为什么允许写项目文件夹：**开卷的产物本来就是程序写的**（`ingest/pipeline`
      写 `人物.yaml`、`ingest/atlas` 写 `小世界地图.yaml`），而这里是**作者在界面上
      主动改**（与「书斋」改风格是同一条路）。铁律里那条"永不反写"管的是
      **AI 生成的推演产物不许自动写进项目** —— 不是"作者不能改自己的设定"。
      ⚠ 仍然照旧只写**这一轮之后**（`freeze_settings_into_run` 已冻结当轮快照）。
    
        English:
    Write the fields of ④ the character layer back to the **character roster** (`设定集/人物.yaml`).
        Returns `(success?, explanation)`. **Line-level editing**: only change those lines under the target person's name,
        the rest of the file is **left untouched verbatim** (the author's handwritten comments, others' cards, unknown fields all remain).
        ★ Why not do a whole-file `yaml.dump` rewrite: that would lose all comments and field order.
          This is a direct corollary of this project's "never silently drop content" —— and the character roster is exactly where the author writes by hand.
        ★ Why writing to the project folder is allowed: **the products of ingest are written by the program anyway** (`ingest/pipeline`
          writes `人物.yaml`, `ingest/atlas` writes `小世界地图.yaml`), while here it's **the author actively editing** in the UI
          (the same path as "书斋" changing style). The iron rule "never write back" governs
          **AI-generated reasoning products must not be automatically written into the project** —— not "the author can't edit his own settings".
          ⚠ Still, as before, only write **after this round** (`freeze_settings_into_run` has already frozen the current-round snapshot).
    """
    p = Path(settings_dir) / PEOPLE_FILE
    if not p.is_file():
        return False, f'没有 {PEOPLE_FILE}'
    try:
        raw = p.read_text(encoding='utf-8')
    except Exception as e:                                       # noqa: BLE001
        return False, f'读不到：{e!r}'
    lines = raw.splitlines(keepends=True)

    # ── 定位这个人那一段：`- 姓名: X` 那一行 → 下一个 `- ` 之前 ──
    # [EN] ── Locate that person's paragraph: the line `- name: X` → up to the next `- ` ──
    want = str(name or '').strip()
    head, tail = -1, -1
    for i, ln in enumerate(lines):
        s = ln.lstrip()
        if not s.startswith('- '):
            continue
        body = s[2:].strip()
        for pref in ('姓名:', 'name:'):
            if body.startswith(pref):
                who = body[len(pref):].strip().strip('\'"')
                if who == want:
                    head = i
                elif head >= 0:
                    tail = i                      # 下一个人开头 = 本段结束
                    # [EN] The start of the next person = the end of this paragraph
                break
        if tail >= 0:
            break
    if head < 0:
        return False, f'人物表里没有「{want}」'
    if tail < 0:
        tail = len(lines)

    # 缩进从该段里已有的字段行学（没有就按 2 空格 —— 与 `ingest` 写的格式一致）
    # [EN] Learn the indentation from existing field lines in that paragraph (if none, use 2 spaces —
    # [EN] consistent with the format `ingest` writes)
    indent = '  '
    for ln in lines[head:tail]:
        m = re.match(r'^(\s+)\S', ln)
        if m:
            indent = m.group(1)
            break

    # ── 逐字段替换；没有的就追加到本段末尾 ──
    # [EN] ── Replace field by field; append any missing ones to the end of this paragraph ──
    seg = lines[head:tail]
    for key, _label, _kind in CARD_FIELDS:
        val = ' '.join(str((fields or {}).get(key) or '').split())
        hit = -1
        for j, ln in enumerate(seg):
            if j == 0:
                continue                          # 第 0 行是 `- 姓名:`
                # [EN] Line 0 is `- name:`
            if re.match(rf'^\s*{re.escape(key)}\s*:', ln):
                hit = j
                break
        if val:
            newline = f'{indent}{key}: {_yaml_scalar(val)}\n'
            if hit >= 0:
                seg[hit] = newline
            else:
                #  ⚠ 追加到**最后一个非空行**之后，不是段尾 ——
                #    段尾往往跟着一个空行（人物之间那条视觉分隔），
                #    直接 append 会把新字段写到空行后面，读起来像"另一个人的"。
                # [EN] ⚠ Append after the **last non-empty line**, not at the end of the paragraph —
                # [EN] the end of the paragraph is often followed by a blank line (the visual separator between
                # [EN] characters),
                # [EN] and appending directly would write the new field after the blank line, which reads like it
                # [EN] belongs to "another person".
                at = len(seg)
                while at > 0 and not seg[at - 1].strip():
                    at -= 1
                seg.insert(at, newline)
        elif hit >= 0:
            del seg[hit]                          # 清空 = 删掉那一行（不留空壳）
    # 段尾保证有一个换行（原文件可能没有）
            # [EN] Clearing = delete that line (don't leave an empty shell)
            # [EN] Guarantee a trailing newline at the end of the paragraph (the original file may not have one)
    if seg and not seg[-1].endswith('\n'):
        seg[-1] = seg[-1] + '\n'

    out = ''.join(lines[:head] + seg + lines[tail:])
    if out == raw:
        return True, '（没有变化）'
    _backup(p)
    return (_atomic_write(p, out), '已写入')


def _atomic_write(p: Path, text: str) -> bool:
    """原子写（先写临时文件再替换）—— 半截文件比不写更坏。
        English:
    Atomic write (write a temp file first then replace) —— a half-written file is worse than not
    writing.
    """
    import os
    try:
        tmp = p.with_name(p.name + '.tmp')
        tmp.write_text(text, encoding='utf-8', newline='')
        os.replace(tmp, p)
        return True
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('写 %s 失败：%r', p.name, e)
        try:
            (p.with_name(p.name + '.tmp')).unlink(missing_ok=True)
        except Exception:                                        # noqa: BLE001
            pass
        return False


def _types_path() -> Path:
    """类型库文件的位置 —— **唯一来源**（`load()` 与写入都走它）。

    ⚠ 别再另立一个模块级常量（原来是 `_LIB`）：两处各写一遍路径，
      "写进 A、读的还是 B"这种错**看日志都看不出来** ——
      表现是"改了类型库，界面/选角一点没变"，而两边单看都对。
      判据 `verify_actor_layers` 就是靠**接管这一个函数**来把整条读写链
      搬到临时目录上的（接管不了就只能去改用户的真文件，那不允许）。
    
        English:
    Location of the type library file —— **single source** (both `load()` and writing go through
    it).
        ⚠ Don't create another module-level constant (it used to be `_LIB`): writing the path in two places means
          a "write to A, read from B" kind of bug **can't be seen even in the logs** ——
          it manifests as "changed the type library, but the UI/casting didn't change at all", while each side looks correct on its own.
          The criterion `verify_actor_layers` relies on **taking over this one function** to move the entire read-write chain
          onto a temp directory (if it can't take over, the only option would be to modify the user's real file, which is not allowed).
    """
    return _LIB


#: 类型库里的**非类型**顶层键（与 `load()` 里那份 `skip` 同一口径 ——
#: 写两遍就会漂：那边加了键这边不认，界面就会把 `名称:` 当成一个"演员类型"列出来）。
# [EN] : **non-type** top-level keys in the type library (same criterion as the `skip` in `load()` --
# [EN] : writing it twice will drift: if a key is added there and not recognized here, the UI will list
# [EN] `名称:` as an "actor type").
_SKIP_KEYS = {'名称', '来源', '适用', '匹配表', '年龄表', '_DEFAULT'}


def type_names() -> list[str]:
    """类型库里有哪些类型（**按文件里的顺序** —— 作者排的顺序是有意思的）。
        English:
    Which types exist in the type library (**in file order** —— the order the author arranged has
    meaning).
    """
    try:
        text = _types_path().read_text(encoding='utf-8')
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('读类型名失败：%r', e)
        return []
    known = set(load()['types'])
    out: list[str] = []
    for ln in text.splitlines():
        if not ln or ln[0].isspace() or ln.startswith('#'):
            continue
        if not ln.rstrip().endswith(':'):
            continue
        k = ln.split(':')[0].strip()
        if k in _SKIP_KEYS or k.startswith('_'):
            continue
        if k:
            out.append(k)
    # ⚠ 加上"文件里有、但按 `load()` 的口径不算类型"的那些不合适（那种块缺骨架/说话），
    #   所以以 `known` 为准过滤一遍：界面列出来的必须是**真能选**的。
    # [EN] ⚠ adding "those that exist in the file but don't count as types under `load()`'s criterion" is
    # [EN] not appropriate (such blocks lack a skeleton/speech),
    # [EN] so filter with `known` as the source of truth: what the UI lists must be **actually
    # [EN] selectable**.
    return [k for k in out if k in known] or sorted(known)


def _type_block(name: str, data: dict | None = None) -> str:
    """按**固定模板**把一型的字段拼成 YAML 文本块（字段顺序稳定，人看着顺）。

    ⚠ 自己拼而不 `yaml.safe_dump`：一是要保字段顺序，二是多行的 `骨架`
      用 `>` 折叠块更可读（dump 出来是带引号的一长行）。
    
        English:
    Assemble a type's fields into a YAML text block by a **fixed template** (stable field order,
    pleasant to read).
        ⚠ Assemble by hand instead of `yaml.safe_dump`: one, to preserve field order; two, the multi-line `骨架`
          is more readable using a `>` folded block (dump gives a long quoted single line).
    """
    e = dict(data) if data is not None else entry(name)
    b: list[str] = [f'{name}:']
    if e.get('常演'):
        b.append(f'  常演: {_yaml_scalar(e["常演"])}')
    #  ⚠ `骨架` **不做 `' '.join(split())`**：作者在 yaml 里怎么分行，就照样保留
    #    （折成一行虽然语义相同，但"整块替换"把排版吃掉，与本模块
    #      "不静默丢内容"的纪律不一致 —— 而且人读起来差很多）。
    # [EN] ⚠ `骨架` does **not do `' '.join(split())`**: however the author breaks lines in the yaml, keep it
    # [EN] that way
    # [EN] (collapsing to one line is semantically identical, but "whole-block replacement" eats the
    # [EN] layout, which conflicts with this module's
    # [EN] "don't silently drop content" discipline -- and it reads very differently for a human).
    sk_lines = [x.strip() for x in str(e.get('骨架') or '').splitlines()]
    sk_lines = [x for x in sk_lines if x]
    if sk_lines:
        b.append('  骨架: >-')
        b += [f'    {x}' for x in sk_lines]
    sp = e.get('说话') if isinstance(e.get('说话'), dict) else {}
    if sp:
        b.append('  说话:')
        for k in ('句长', '语速'):
            if sp.get(k):
                b.append(f'    {k}: {_yaml_scalar(sp[k])}')
        ct = [str(x) for x in (sp.get('口头禅') or []) if str(x).strip()]
        if ct:
            b.append('    口头禅: [' + ', '.join(_yaml_scalar(x) for x in ct) + ']')
        if sp.get('忌讳'):
            b.append(f'    忌讳: {_yaml_scalar(sp["忌讳"])}')
    if e.get('身体'):
        b.append(f'  身体: {_yaml_scalar(e["身体"])}')
    if e.get('张力'):
        b.append(f'  张力: {_yaml_scalar(e["张力"])}')
    vs = [str(x) for x in (e.get('变奏') or []) if str(x).strip()]
    if vs:
        b.append('  变奏:')
        for v in vs:
            b.append(f'    - {_yaml_scalar(v)}')
    if e.get('忌讳'):
        b.append(f'  忌讳: {_yaml_scalar(e["忌讳"])}')
    return '\n'.join(b) + '\n'


def save_type(name: str, fields: dict, *, create: bool = False) -> tuple[bool, str]:
    """新建 / 修改类型库里的一型（**整块替换**，不碰文件头那 65 行注释）。

    ★ 为什么是"整块替换"而不是整文件 dump：`archetypes.yaml` 顶上有一大段
      **设计说明**（为什么要有这一层、两条轴怎么来的、与刻板印象的界线…），
      那是这个文件最有价值的部分之一；`yaml.safe_dump` 会把它全抹掉。
      而类型块**内部只有字段、没有注释**（已逐块核对过），所以替换整块是安全的。
    ⚠ 替换边界：从 `^<名字>:$` 到**下一个顶格行**（或文件尾）——
      顶格行 = 另一个类型名或顶层键（`名称:` / `来源:` / …）。
    
        English:
    Create/modify a type in the type library (**whole-block replacement**, don't touch the 65-line
    comment header).
        ★ Why "whole-block replacement" instead of whole-file dump: `archetypes.yaml` has a big block of
          **design notes** at the top (why this layer exists, where the two axes come from, the boundary with stereotypes...),
          which is one of the most valuable parts of this file; `yaml.safe_dump` would wipe it all out.
          And the type block **contains only fields internally, no comments** (verified block by block), so replacing the whole block is safe.
        ⚠ Replacement boundary: from `^<name>:$` to **the next top-level line** (or end of file) ——
          a top-level line = another type name or a top-level key (`名称:` / `来源:` / ...).
    """
    cur = entry(name)
    if not cur and not create:
        return False, f'类型库里没有「{name}」'
    if cur and create:
        return False, f'「{name}」已经存在'
    data = {
        '常演': fields.get('常演', cur.get('常演', '')),
        '骨架': fields.get('骨架', cur.get('骨架', '')),
        '说话': {'句长': (fields.get('句长') if fields.get('句长') is not None
                         else (cur.get('说话') or {}).get('句长', '')),
                 '语速': (fields.get('语速') if fields.get('语速') is not None
                         else (cur.get('说话') or {}).get('语速', '')),
                 '口头禅': (fields.get('口头禅')
                          if fields.get('口头禅') is not None
                          else (cur.get('说话') or {}).get('口头禅', [])),
                 '忌讳': (fields.get('说话忌讳') if fields.get('说话忌讳') is not None
                         else (cur.get('说话') or {}).get('忌讳', ''))},
        '身体': fields.get('身体', cur.get('身体', '')),
        '张力': fields.get('张力', cur.get('张力', '')),
        '变奏': (fields.get('变奏') if fields.get('变奏') is not None
                 else cur.get('变奏', [])),
        '忌讳': fields.get('忌讳', cur.get('忌讳', '')),
    }
    p = _types_path()
    if not p.is_file():
        return False, f'没有 {TYPES_FILE}'
    try:
        lines = p.read_text(encoding='utf-8').splitlines(keepends=True)
    except Exception as e:                                       # noqa: BLE001
        return False, f'读不到：{e!r}'
    head = tail = -1
    for i, ln in enumerate(lines):
        if ln.rstrip() == f'{name}:' and not ln[0].isspace():
            head = i
        elif head >= 0 and ln.strip() and not ln[0].isspace():
            tail = i
            break
    if head >= 0 and tail < 0:
        tail = len(lines)
    block = _type_block(name, data)
    if head < 0:                                      # 新建 ⇒ 追加到文件尾
    # [EN] create new ⇒ append to end of file
        text = ''.join(lines).rstrip('\n') + '\n\n' + block
    else:
        text = ''.join(lines[:head]) + block + ''.join(lines[tail:])
    _backup(p)
    okw = _atomic_write(p, text)
    if okw:
        load(force=True)                              # 让缓存看到新的（别让旧值继续生效）
        # [EN] let the cache see the new value (don't let the old value keep taking effect)
    return okw, ('已写入' if okw else '写不进去（详见日志）')
