# -*- coding: utf-8 -*-

"""**技能路由**：让各职位在需要的时候，从 `skills/` 里挑到合适的那一份。

用户 2026-10-10：
「拆书功能落地之后 你还得修改相关Agent，让他们在需要的时候选择合适的SKILL用起来。」

两类技能，两种给法（**这是这个模块唯一的设计决定，别把两者混起来**）
------------------------------------------------------------------
| | 谁写的 | 长什么样 | 怎么给 |
|---|---|---|---|
| **领域技能** | 人写的（`skills/<名字>/SKILL.md`） | 1~5 KB 的知识卡（中医药方常识 / 兵器甲胄 / 官制对照 / 节气物候…） | **给要点**：正文摘录进提示词 |
| **拆书技能** | 拆书功能产出（`skills/book-dismantle/<书名>/`） | 长（6 条写法 × 五门禁字段 + 节奏 / 立人 / 文风） | **不给正文**，只给一句索引 |

★★ 为什么拆书技能**不在这里给正文**（这一条想清楚再改）：
   它的正文已经由 `craft_block` 的第 ③ 段（`booklab/store`）按题材挑过一版
   给过了。在这里再塞一遍，模型会看到**同一份内容的两种署名**，
   于是把它当成"两条独立经验" —— 它会照着写，而且更信。
   **同一份内容，只给一次。** 这里只负责让 Agent 知道"库里还有哪几份、
   凭什么跟这一刻有关"，要细看它自己有路（`skills/book-dismantle/<书名>/`）。

为什么"给要点"也要限字数
------------------------
一张知识卡 5 KB，十二个职位每个都塞进去就是 60 KB 的提示词 ——
**那不是"给了技能"，那是把注意力淹掉**。所以按职位**只给最相关的一两份**、
每份只摘最前面那一段（卡片都是"总述在前、细节在后"的结构）。

接线方式：由 `crew/agents.craft_block` 作为**第 ④ 段**调一次 ——
一处接上，十四个职位同时拿到（与第 ③ 段同一个道理，别再到处加参数）。

English:
**Skill routing**: let each role, when needed, pick an appropriate one from `skills/`.
User 2026-10-10:
"After the book-dismantle feature lands, you also need to modify the related Agents so they pick
and use the appropriate SKILL when needed."
Two kinds of skills, two ways of giving them (**this is the only design decision in this module,
don't mix the two up**)
------------------------------------------------------------------
| | Who wrote it | What it looks like | How it's given |
|---|---|---|---|
| **Domain skill** | Written by a human (`skills/<name>/SKILL.md`) | 1~5 KB knowledge card (TCM prescription common sense / weapons and armor / official-rank reference / solar terms and phenology...) | **Give key points**: excerpt body text into the prompt |
| **Book-dismantle skill** | Produced by the book-dismantle feature (`skills/book-dismantle/<book name>/`) | Long (6 writing modes × five-gate fields + pacing / character-building / style) | **Don't give body text**, give only a one-line index |
★★ Why book-dismantle skills **don't give body text here** (think this through before changing
it):
   Its body text has already been selected by genre in paragraph ③ of `craft_block` (`booklab/store`)
   and given. Stuffing it in again here makes the model see **two bylines for the same content**,
   so it treats them as "two independent experiences" -- it will write accordingly, and trust it more.
   **The same content, given only once.** Here we only make the Agent aware of "what else is in the library,
   and why it's relevant to this moment"; to look closer it has its own path (`skills/book-dismantle/<book name>/`).
Why "give key points" also needs a character limit
------------------------
One knowledge card is 5 KB; stuffing one into each of twelve roles is 60 KB of prompt --
**that isn't "giving skills", that's drowning the attention**. So per role give **only the one
or two most relevant**,
and from each excerpt only the very first paragraph (cards all have the structure "overview
first, details later").
Wiring: called once by `crew/agents.craft_block` as **paragraph ④** --
wired in one place, fourteen roles get it at the same time (same reasoning as paragraph ③, stop
adding parameters everywhere).
"""
from __future__ import annotations

import logging

from config import CFG

_LOG = logging.getLogger('nws.crew.skills')

#: 一级技能里**不是**领域知识卡的那一类（拆书产出）—— 它们的正文不在这里给。
#: ⚠ 判据会核对它和 `booklab/skillgen.BOOK_DIR` 是同一个值。
# [EN] : In the tier-1 skills, the category that is **not** a domain knowledge card (book-dismantle
# [EN] output) -- their body text is not given here.
# [EN] : ⚠ The criterion will check that it is the same value as `booklab/skillgen.BOOK_DIR`.
DISMANTLE_CATEGORY = 'book-dismantle'

#: 每份知识卡最多摘多少字（**只摘开头那一段**，卡片都是总述在前）。
# [EN] : Maximum characters to excerpt per knowledge card (**only the opening paragraph**; cards always
# [EN] put the overview first).
EXCERPT_CHARS = 700
#: 整段最多多少字（超过就截）
# [EN] : Maximum characters for the whole block (truncate if exceeded).
TOTAL_CHARS = 1600

#: 这个职位额外关心哪些词（拼进查询串）。
# [EN] : Which extra words this role cares about (spliced into the query string).
#:
#: ★ 为什么要有它：注册表是按**查询串**打分的，而"这一刻该查什么"只有职位自己知道——
#:   资料员查的是"名物/制度/称谓"，道具查的是"器物/兵器"，造型查的是"服饰/纹样"。
#:   只拿题材（"悬疑灵异"）去查，八张知识卡一张都命不中（题材里没有"药方"两个字），
#:   于是这一整层永远不出活 —— 而"接上了但从不生效"比"没接"更难发现。
#: ⚠ 这些词只用来**检索**，不是"这个职位只能看这些"的允许清单：
#:   命中的仍然是注册表按全部字段打的分（题材 / 触发关键词 / 标签都会算）。
# [EN] : ★ Why it exists: the registry scores by **query string**, and only the role itself knows what
# [EN] should be queried at this moment --
# [EN] : The researcher queries "names/institutions/forms of address", props queries "objects/weapons",
# [EN] styling queries "clothing/patterns".
# [EN] : Querying with only the genre ("suspense paranormal") hits none of the eight knowledge cards
# [EN] (the genre contains no word like "prescription"),
# [EN] : so this entire layer never produces output -- and "wired up but never effective" is harder to
# [EN] notice than "not wired up".
# [EN] : ⚠ These words are only for **retrieval**, not an allowlist of "this role can only look at
# [EN] these":
# [EN] : Hits are still scored by the registry over all fields (genre / trigger keywords / tags all
# [EN] count).
WANTS: dict[str, str] = {
    'researcher': '名物 制度 称谓 官制 品级 律法 药方 方子 药材 兵器 甲胄 '
                  '节气 物候 路程 车马 礼仪 朝代 饮食',
    'continuity': '称谓 称呼 品级 官制 礼数 节气 时辰 路程',
    'script_doctor': '称谓 称呼 礼数 品级 忌讳 礼数',
    'props': '器物 兵器 甲胄 乐器 炊具 车马 灯 伞 舟船',
    'art': '服饰 居所 器物 颜色 纹样 建筑',
    'stylist': '服饰 纹样 发式 随身物 首饰',
    'sound': '乐器 钟鼓 更鼓 市声 声响',
    'polisher': '称谓 雅言 俗语 礼数 药方 官称',
    'novelist': '病 药 方子 律法 官制 礼数 器物 节气',
    'screenwriter': '称谓 礼数 器物 官制',
    'director': '礼数 制度 品级',
    'settings_room': '制度 礼数 名物 官制 节气',
    'actor': '称谓 说话 口癖 礼数',
    'reviewer': '制度 礼数 官制',
    'publicity': '题材 卖点',
    'extra': '市井 行当 称谓 器物',
}


def _limit() -> int:
    """这个职位最多给几份（旋钮 `CREW_SKILL_LIMIT`）。
        English:
    Maximum number given to this role (knob `CREW_SKILL_LIMIT`).
    """
    try:
        return max(1, min(5, int(CFG.i('CREW_SKILL_LIMIT') or 2)))
    except Exception:                                            # noqa: BLE001
        return 2


def _on() -> bool:
    """总开关（旋钮 `CREW_SKILL_ROUTE`）—— 关掉则这一段为空，**其余行为一字不变**。
        English:
    Master switch (knob `CREW_SKILL_ROUTE`) -- when off this paragraph is empty, and **all other
    behavior is unchanged character for character**.
    """
    try:
        return bool(CFG.b('CREW_SKILL_ROUTE'))
    except Exception:                                            # noqa: BLE001
        return True


def query_for(key: str, *, genre: str = '', structure: str = '',
              question: str = '') -> str:
    """拼这一职位这一刻的**查询串**（题材 + 结构 + 职位关心的词 + 作者手写的几句）。
        English:
    Splice the **query string** for this role at this moment (genre + structure + words the role
    cares about + a few lines handwritten by the author).
    """
    bits = [str(genre or '').strip(), str(structure or '').strip(),
            WANTS.get(str(key or ''), ''), str(question or '').strip()]
    return ' '.join(x for x in bits if x).strip()


def route(key: str, *, genre: str = '', structure: str = '',
          question: str = '', limit: int | None = None) -> dict:
    """挑出这一刻跟这个职位相关的技能 → `{'领域': [...], '拆书': [...]}`。

    ⚠ 注册表坏了 / 目录不在 → 返回两个空表（**不许把推演带崩**：
      技能是增强项，不是前提 —— 与"外部创作服务失败一律回退"同一条纪律）。
    
        English:
    Pick out the skills relevant to this role at this moment → `{'domain': [...], 'book-dismantle':
    [...]}`.
        ⚠ Registry broken / directory missing → return two empty lists (**don't crash the reasoning**:
          skills are an enhancement, not a precondition -- the same discipline as "external creative service failures always fall back").
    """
    out = {'领域': [], '拆书': []}
    q = query_for(key, genre=genre, structure=structure, question=question)
    if not q:
        return out
    try:
        from skills.registry import skill_registry
        hits = skill_registry.match_all(q)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('技能路由失败（不影响推演）：%r', e)
        return out
    n = int(limit) if limit else _limit()
    for s in hits:
        if _is_dismantle(s):
            out['拆书'].append(s)
        elif len(out['领域']) < n:
            out['领域'].append(s)
    return out


def _is_dismantle(s) -> bool:
    """这一份是不是"拆书产出"的（看分类，不看名字 —— 名字会随语言变）。
        English:
    Whether this one is "book-dismantle output" (look at the category, not the name -- names change
    with language).
    """
    try:
        return str(getattr(s, 'category', '') or '') == DISMANTLE_CATEGORY
    except Exception:                                            # noqa: BLE001
        return False


# ══════════════════════════════════════════════════════════════
#  渲染
# [EN] Render
# ══════════════════════════════════════════════════════════════
HEAD = '【可用的技能（装在 skills/ 里的知识包）】'


def _clip(s: str, n: int) -> str:
    t = ' '.join(str(s or '').split())
    return t if len(t) <= n else t[:n].rstrip() + '…'


def render_domain(skills: list) -> list[str]:
    """领域技能那几行（**给要点**）。
        English:
    The lines for domain skills (**give key points**).
    """
    out: list[str] = []
    for s in skills:
        name = str(getattr(s, 'display_name', '') or '')
        cat = str(getattr(s, 'category', '') or '')
        purpose = _clip(str(getattr(s, 'purpose', '') or ''), 90)
        body = _clip(str(getattr(s, 'content', '') or ''), EXCERPT_CHARS)
        line = f'▸ **{name}**' + (f'（{cat}）' if cat else '')
        if purpose:
            line += f' —— {purpose}'
        out.append(line)
        if body:
            out.append(body)
        out.append('')
    return out


def render_index(skills: list) -> list[str]:
    """拆书技能那几行（**只给索引**，正文由 `craft_block` 第 ③ 段给）。
        English:
    The lines for book-dismantle skills (**give only the index**; body text is given by paragraph ③
    of `craft_block`).
    """
    if not skills:
        return []
    names = []
    for s in skills:
        nm = str(getattr(s, 'display_name', '') or '')
        g = str(getattr(s, 'genre', '') or '')
        names.append(f'《{nm}》' + (f'（{g}）' if g else ''))
    return ['· 拆书库里还有这几份跟这一刻沾边：' + '、'.join(names)
            + '（写法要点在上面那一段里给过了）']


def render(route_result: dict) -> str:
    """把路由结果拼成一段（空 = 什么都不给）。
        English:
    Splice the routing result into one block (empty = give nothing).
    """
    domain = list(route_result.get('领域') or [])
    index = list(route_result.get('拆书') or [])
    if not domain and not index:
        return ''
    lines: list[str] = [HEAD]
    if domain:
        lines += render_domain(domain)
    lines += render_index(index)
    if domain:
        lines.append('（上面是**系统里装着的知识包**，用不用由这一场戏自己定；'
                     '要细看全文，在 `skills/<技能名>/SKILL.md`。）')
    return _clip_all('\n'.join(x for x in lines if x is not None), TOTAL_CHARS)


def _clip_all(s: str, cap: int) -> str:
    return s if len(s) <= cap else s[:cap].rstrip() + '\n…（技能摘录到此为止）'


def skill_block(key: str, *, genre: str = '', structure: str = '',
                question: str = '', limit: int | None = None) -> str:
    """职位用得到的那一段（`craft_block` 的第 ④ 段）。空串 = 没得给。
        English:
    The paragraph the role can use (paragraph ④ of `craft_block`). Empty string = nothing to give.
    """
    if not _on():
        return ''
    try:
        return render(route(key, genre=genre, structure=structure,
                            question=question, limit=limit))
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('技能那一段没拼出来（不影响推演）：%r', e)
        return ''


# ══════════════════════════════════════════════════════════════
#  落盘：这一本用上了哪些技能（给人核对）
# [EN] Write to disk: which skills were used for this book (for human verification).
# ══════════════════════════════════════════════════════════════
def table_md(genre: str, structure: str = '', *, roles: list[str] | None = None,
             question: str = '') -> str:
    """《本书可用的技能.md》：**逐职位**列它这一刻挑到了哪几份、凭什么。

    ★ 为什么逐职位列：路由是**按职位**发生的（资料员挑到药方、造型挑到服饰）——
      只列一张总表的话，作者看到"用了中医药方常识"却不知道该谢谁，
      也核对不了"该挑到的那个人挑到没有"。
    
        English:
    "Skills available for this book.md": list **per role** which ones it picked at this moment and
    why.
        ★ Why list per role: routing happens **per role** (the researcher picks prescriptions, styling picks clothing) --
          if you list only one overall table, the author sees "used TCM prescription common sense" but doesn't know whom to thank,
          and can't verify "whether the one who should have picked it did pick it".
    """
    if roles is None:
        try:
            from crew import roster as ROSTER
            roles = [r.key for r in ROSTER.ROSTER]
        except Exception:                                        # noqa: BLE001
            roles = list(WANTS)
    if not _on():
        return ('# 本书可用的技能\n\n> 技能路由被关掉了（天机里的 '
                '`CREW_SKILL_ROUTE`）。打开之后，各职位会按自己这一刻的活儿'
                '去 `skills/` 里挑知识包。\n')
    rows = ['# 本书可用的技能', '',
            '> 各职位**按自己这一刻的活儿**从 `skills/` 里挑知识包'
            '（题材 + 职位的关心点 + 你在书斋手写的那几句一起进检索）。',
            '> 挑不到就是空的 —— **没匹配上不给**，硬塞一份不相干的东西比不给更坏。',
            '', '| 职位 | 挑到的知识包 | 凭什么 |', '|---|---|---|']
    empty = 0
    for k in roles:
        got = route(k, genre=genre, structure=structure, question=question)
        domain = list(got.get('领域') or [])
        if not domain:
            empty += 1
            rows.append(f'| `{k}` | （没有匹配上的） | — |')
            continue
        names = '、'.join(f'**{getattr(s, "display_name", "")}**' for s in domain)
        rows.append(f'| `{k}` | {names} | 题材/关键词命中 |')
    n_roles = len(roles)
    rows += ['', f'> 共 {n_roles} 个职位，**{n_roles - empty}** 个挑到了知识包、'
                 f'{empty} 个没有匹配上的。']
    return '\n'.join(rows) + '\n'
