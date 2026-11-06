# -*- coding: utf-8 -*-
"""**项目档**：剧组按"这一本书"调整的那一层。

用户 2026-10-07
--------------
「剧组人员虽然提前写好了 也需要针对不同小说进行调整 这部分你有什么的优化方案」

问题说得很准
------------
剧组那些职位是**行当**（场记永远是查连戏的、美术永远是定调子的），
这一层不该随书变；但**每一本书该让他们多注意什么、少做什么**，
是另一回事 —— 侦探小说里场记该盯线索物，喜剧里道具该多找笑料物件，
而这两种东西在"职位定义"里都写不下（写进去就变成了两套职位）。

分层
----
| 层 | 谁 | 随书变吗 | 在哪 |
|---|---|---|---|
| **职位定义**（行当） | 场记是查连戏的 | **不变** | `crew/roster.py` · `crew/agents.py` 的类 |
| **行当手艺**（怎么干） | 查什么、按什么标准 | 半变 | `craft/playbooks/*.yaml`（按题材挑条目） |
| **项目档**（这本书的侧重） | 这本要多查什么、不许出现什么 | **每本都变** | 本模块 |

★ 冲突时的规矩（与演员那两层同一条）：
  **项目档压过默认偏好**。它是"这本书的规矩"，职位那一层是"这一行的常识" ——
  常识让位于具体。所以项目档那一段在提示词里**排在默认手艺之后**，
  并且明写一句"这本书的特别要求，与上面的通用手艺冲突时以它为准"。

料从哪来（不新增调用）
--------------------
全部来自**开卷时已经算出来的那两张卡**，一个字都不额外问模型：
  · `类型卡`（`craft/genres/*.yaml`）：冲突偏好 · 钩子库 · 爽点模式 ·
    人物原型库 · 毒点红线 · 风格建议 —— 这几项本来就是"这本书该怎么写"；
  · `风格卡`（从原作抽的）：语气、禁词、样例。

一处设置、全体生效
----------------
`build(world)` 在装配时调一次，结果挂到 `world.crew_profile`；
`crew/agents.craft_block()` 每拼一次手艺就把它接在后面 —— 所以
**十二个职位一次全拿到**，不用改十二处提示词（那是"两处各写一份"的老坑）。

English:
**Project profile**: the layer the crew adjusts for "this one book".
User 2026-10-07
--------------
"Although the crew members are written in advance, they also need to be adjusted for different
novels. What optimization plan do you have for this part?"
The question is very accurate
------------
Those crew roles are **trades** (the script supervisor always checks continuity, the art
director always sets the tone),
this layer should not change per book; but **what each book should have them pay more attention
to, and do less of**,
is another matter -- in a detective novel the script supervisor should watch for clue objects,
in a comedy the props department should find more gag objects,
and neither of these things can be written into the "role definition" (writing them in would
create two sets of roles).
Layering
----
| Layer | Who | Changes per book? | Where |
|---|---|---|---|
| **Role definition** (trade) | Script supervisor checks continuity | **Unchanged** | `crew/roster.py` · classes in `crew/agents.py` |
| **Trade craft** (how to do it) | What to check, by what standard | Semi-variable | `craft/playbooks/*.yaml` (pick entries by genre) |
| **Project profile** (this book's emphasis) | What this book should check more of, what must not appear | **Changes every book** | this module |
★ Rule on conflict (same as the actor's two layers):
  **The project profile overrides default preferences**. It is "this book's rules", while the role layer is "this trade's common sense" --
  common sense gives way to the specific. So the project profile section is placed **after the default craft** in the prompt,
  and explicitly states "this book's special requirements, when in conflict with the general craft above, take precedence".
Where the material comes from (no new calls)
--------------------
All comes from **the two cards already computed when opening the book**, not a single extra word
asked of the model:
  · `Genre card` (`craft/genres/*.yaml`): conflict preferences · hook library · hook mode ·
    character archetype library · toxic point red lines · style suggestions -- these items are inherently "how this book should be written";
  · `Style card` (extracted from the source work): tone, forbidden words, examples.
Set once, effective for all
----------------
`build(world)` is called once at assembly time, and the result is attached to
`world.crew_profile`;
`crew/agents.craft_block()` appends it each time craft is assembled -- so
**all twelve roles get it at once**, no need to change twelve prompts (that is the old trap of
"writing it in two places").
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

_LOG = logging.getLogger('nws.crew.profile')

#: 项目档那一段的抬头（`craft_block` 用它拼）
# [EN] : The header of the project profile section (used by `craft_block` to assemble)
HEAD = '【这本书的特别要求（与上面的通用手艺冲突时，以这一段为准）】'


@dataclass
class Profile:
    """一本书的剧组档。字段都是"从卡里取到的"，取不到就是空（**不编**）。
        English:
    The crew profile of one book. The fields are all "taken from the cards"; if not obtainable, they
    are empty (**no making up**).
    """

    genre: str = ''
    structure: str = ''
    engine: str = ''            # 冲突主引擎
    # [EN] Conflict main engine
    hooks: list[str] = field(default_factory=list)
    beats: list[str] = field(default_factory=list)      # 爽点模式
    redlines: list[str] = field(default_factory=list)   # 毒点红线
    proto: list[str] = field(default_factory=list)      # 人物原型库
    style: dict = field(default_factory=dict)           # 风格建议
    tone: str = ''              # 一句话调性（从题材＋风格建议拼）
    #: 各职位的**额外侧重**（这本要多做什么）—— 由 `note_for` 按卡推
    # [EN] Hook mode
    # [EN] Toxic point red lines
    # [EN] Character archetype library
    # [EN] Style suggestions
    # [EN] One-line tone (assembled from genre + style suggestions)
    # [EN] : The **extra emphasis** for each role (what this book should do more of) -- pushed by
    # [EN] `note_for` per card
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return any((self.engine, self.hooks, self.beats, self.redlines,
                    self.style, self.tone))


def _as_list(v: Any, n: int = 4) -> list[str]:
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()][:n]
    return []


def _pick(d: Any, *keys: str) -> str:
    if not isinstance(d, dict):
        return ''
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ''


def build(world) -> Profile:
    """从世界里那两张卡建一份项目档（**取不到的部分留空，不编**）。
        English:
    Build a project profile from the two cards in the world (**leave empty what is not obtainable,
    no making up**).
    """
    card = getattr(world, 'genre_card', None) or {}
    if not isinstance(card, dict):
        card = {}
    style_card = getattr(world, 'style_card', None) or {}
    if not isinstance(style_card, dict):
        style_card = {}
    conf = card.get('冲突偏好') or {}
    style = card.get('风格建议') or {}
    if not isinstance(style, dict):
        style = {}
    p = Profile(
        genre=str(card.get('类型') or card.get('主题材') or '').strip(),
        structure=str(card.get('结构') or card.get('结构轴') or '').strip(),
        engine=_pick(conf, '主引擎'),
        hooks=_as_list(card.get('钩子库')),
        beats=_as_list(card.get('爽点模式')),
        redlines=_as_list(card.get('毒点红线')),
        proto=_as_list(card.get('人物原型库')),
        style={str(k): str(v) for k, v in style.items() if str(v).strip()},
    )
    # 一句话调性：题材 + 风格建议里最能定调的那一条
    # [EN] One-line tone: the single most tone-defining item from genre + style suggestions
    tone_bits = [x for x in (p.genre, p.structure) if x]
    for k in ('叙事距离', '氛围营造', '句长'):
        if p.style.get(k):
            tone_bits.append(f'{k}：{p.style[k]}')
            break
    p.tone = ' · '.join(tone_bits)
    # 风格卡里的语气（原作抽出来的那一条）——有就补进调性
    # [EN] The tone from the style card (the item extracted from the source work) -- if present, add it
    # [EN] into the tone
    _st = _pick(style_card, '语气', 'tone', '风格')
    if _st and _st not in p.tone:
        p.tone = (p.tone + ' · ' + _st).strip(' ·')
    p.extra = _derive_extra(p, style_card)
    return p


# ══════════════════════════════════════════════════════════════
#  各职位的额外侧重
# [EN] Extra emphasis for each role
# ══════════════════════════════════════════════════════════════
def _derive_extra(p: Profile, style_card: dict) -> dict[str, str]:
    """按这本书的卡，给相关职位各加一句"这本要多注意什么"。

    规则写得直白（不是又一门手艺，只是**把卡上的原话搬到该看的人面前**）——
    所以每条都是"从卡的哪个字段来"可追溯的，不是凭空多出来的要求。
    
        English:
    Based on this book's cards, add for each relevant role a line on "what this book should pay more
    attention to".
        The rules are written plainly (not another craft, just **moving the card's original words in front of the people who should see them**) --
        so each one is traceable to "which field of the card it comes from", not a requirement conjured out of thin air.
    """
    ex: dict[str, str] = {}
    if p.hooks:
        ex['continuity'] = f'这本书靠这几样抓人：{"、".join(p.hooks[:3])} —— 连戏时**优先盯与它们有关的物与话**是否对得上。'
        ex['publicity'] = f'卖点从这几样里挑：{"、".join(p.hooks[:3])}。'
    if p.engine:
        ex['screenwriter'] = f'这本书的冲突主引擎是「{p.engine}」—— 每一拍都要能指回它。'
        ex['settings_room'] = f'补局部设定时，优先补能推动「{p.engine}」的那些。'
    if p.beats:
        ex['reviewer'] = f'这几样是这本书的"给到位"：{"、".join(p.beats[:3])} —— 复盘时看今天给到了没有。'
        ex['props'] = f'物件要服务这几样：{"、".join(p.beats[:3])}（要回收的那类，选**能反复出现**的物）。'
    if p.proto:
        ex['settings_room'] = (ex.get('settings_room', '') +
                              f' 人物原型参考：{"、".join(p.proto[:4])}。').strip()
    if p.style:
        ex['novelist'] = '风格：' + '；'.join(f'{k}{v}' for k, v in list(p.style.items())[:3]) + '。'
        ex['polisher'] = ('判"像不像这本书"时按这几条：'
                        + '；'.join(f'{k}{v}' for k, v in list(p.style.items())[:3]) + '。')
        ex['art'] = '画面按这本书的调子：' + (p.style.get('氛围营造')
                                          or p.style.get('叙事距离') or '（风格建议没写）') + '。'
        ex['sound'] = '声音的浓淡跟着这本书的调子走，不要比正文更满。'
        ex['stylist'] = '造型按这本书的底色走，不要比正文更精致。'
    if p.style.get('对话占比') or p.style.get('句长'):
        ex['actor'] = ('这本书的说话方式：'
                      + '；'.join(x for x in (p.style.get('句长'),
                                             '对话占比' + p.style.get('对话占比', '')
                                             if p.style.get('对话占比') else '') if x)
                      + '。')
    if p.redlines:
        ex['__all__'] = f'**这本书不许出现**：{"、".join(p.redlines[:3])}。'
    _wh = _as_list(style_card.get('禁词') or style_card.get('禁用词'), 6)
    if _wh:
        ex['polisher'] = (ex.get('polisher', '') + f' 原作忌用词：{"、".join(_wh)}。').strip()
        ex['novelist'] = (ex.get('novelist', '') + f' 忌用词：{"、".join(_wh)}。').strip()
    return {k: v for k, v in ex.items() if v}


def note_for(p: Profile | None, key: str) -> str:
    """某个职位在这一本书里的额外侧重（没有就空串）。
        English:
    A role's extra emphasis in this one book (empty string if none).
    """
    if p is None or not p.ok:
        return ''
    k = str(key or '')
    one = p.extra.get(k, '')
    every = p.extra.get('__all__', '')
    if not one and not every:
        return ''
    # ⚠ 结构里带 `kind` 不能进 `__all__`（它是"所有职位"的禁忌，不是某个人的侧重）
    # [EN] ⚠ Entries with `kind` in the structure cannot go into `__all__` (it is the taboo of "all roles",
    # [EN] not the emphasis of any individual)
    kind = ''
    if p.engine:
        kind = f'这本书的调性：{p.tone}。' if p.tone else ''
    return '\n'.join(x for x in (kind, one, every) if x)


# ══════════════════════════════════════════════════════════════
#  进提示词 / 落盘
# [EN] Into prompts / written to disk
# ══════════════════════════════════════════════════════════════
def attach(world) -> Profile:
    """建一份并挂到 `world.crew_profile`（装配时调一次）。
        English:
    Build one and attach it to `world.crew_profile` (called once at assembly time).
    """
    try:
        p = build(world)
        world.crew_profile = p
        if p.ok:
            _LOG.info('项目档就绪：%s（%d 个职位有额外侧重）',
                      p.tone or '（调性未定）', len(p.extra))
        else:
            _LOG.info('项目档为空（类型卡/风格卡都没料）—— 剧组按默认手艺干活')
        return p
    except Exception as e:                                          # noqa: BLE001
        _LOG.warning('项目档建不起来（剧组照常干，只是没有"这本书的特别要求"）：%r', e)
        try:
            world.crew_profile = Profile()
        except Exception:                                           # noqa: BLE001
            pass
        return Profile()


def block_for(p: Profile | None, key: str) -> str:
    """拼好的一段（进职位提示词）。空串 = 这本书没给这个职位额外要求。
        English:
    The assembled section (into the role prompt). Empty string = this book gives this role no extra
    requirement.
    """
    note = note_for(p, key)
    return f'{HEAD}\n{note}' if note else ''


def table_md(p: Profile | None) -> str:
    """`本剧组守则.md`：这本书的调性、各职位的额外侧重、不许出现什么。
        English:
    `本剧组守则.md`: this book's tone, each role's extra emphasis, what must not appear.
    """
    if p is None or not p.ok:
        return ('# 本剧组守则\n\n> 这本书没有可用的类型卡或风格卡 —— '
                '剧组按默认手艺干活（不是故障）。\n')
    rows = ['# 本剧组守则', '',
            f'**调性**：{p.tone or "（未定）"}', '']
    if p.engine:
        rows.append(f'- 冲突主引擎：**{p.engine}**')
    if p.hooks:
        rows.append(f'- 钩子库：{"、".join(p.hooks)}')
    if p.beats:
        rows.append(f'- 爽点模式：{"、".join(p.beats)}')
    if p.proto:
        rows.append(f'- 人物原型库：{"、".join(p.proto)}')
    if p.style:
        rows.append('- 风格建议：' + '；'.join(f'{k}{v}' for k, v in p.style.items()))
    if p.redlines:
        rows.append(f'- **毒点红线**：{"、".join(p.redlines)}')
    rows += ['', '## 各职位在这本书里的额外侧重', '',
             '| 职位 | 这本要多注意 |', '|---|---|']
    from crew import roster as R
    for r in R.ROSTER:
        note = p.extra.get(r.key, '')
        if note:
            rows.append(f'| {r.name} | {note} |')
    every = p.extra.get('__all__', '')
    if every:
        rows += ['', f'> **全体**：{every}']
    rows += ['', '> 来源：`类型卡`（冲突偏好/钩子库/爽点模式/毒点红线/风格建议）'
                 '与 `风格卡`（从原作抽的）—— **一个字都不是多问出来的**。',
             '> 与默认行规冲突时，以这一页为准（职位定义那一层是"这一行的常识"，'
             '这一页是"这本书的规矩"）。']
    return '\n'.join(rows) + '\n'
