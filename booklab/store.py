# -*- coding: utf-8 -*-
"""**拆书库**：读回拆出来的技能包，并按"这本书像不像"挑给它用。

用户要的那一环
--------------
「在**后续有类似书籍设定进来的时候**，使用这些经验辅助各个Agent工作，
特别是三人小组（小说家 剧作家 导演）用于优化故事」

这个模块就是"后续"那一步。上游是 `skillgen`（写包），下游是
`crew/agents.craft_block`（进提示词）。

怎么判断"像"
------------
三档，**从硬到软**（`match()`）：

| 档 | 比什么 | 例子 |
|---|---|---|
| ① 类型卡命中 | 当前书的`主题材`/`结构` 与拆书包的`适用类型.题材` **互相包含** | 当前"悬疑" ↔ 拆的"悬疑灵异" |
| ② 关键词重叠 | 当前书的触发词（题材、钩子库、爽点模式…）与包里的`触发关键词`重叠 | 两边都有"伏笔" |
| ③ 模块名命中 | 当前书的**问题**（作者在书斋里写的那句）里出现了模块名 | 问题里提到"钩子" |

★ 为什么要三档而不是一个相似度分数：**分数没法解释**。
  作者问"你凭什么用这本的经验"，答案必须是"因为你的书是悬疑、它也标着悬疑"，
  而不是"相似度 0.73"。所以 `match()` 返回的是**为什么命中**（`hit`）。

★ 匹配不上就**不用**（不硬塞）。一本言情写法用在悬疑上，比不用更坏 ——
  这是"不加选择地引用经验"的典型翻车方式。

English:
**Dismantling library**: read back the dismantled skill packs, and pick ones for it by "does
this book look similar".
The link the user wants
--------------
"**When a similar book setup comes in later**, use these lessons to assist each Agent's work,
especially the three-person team (novelist, playwright, director) for optimizing the story"
This module is that "later" step. Upstream is `skillgen` (writes packs), downstream is
`crew/agents.craft_block` (goes into the prompt).
How to judge "similar"
------------
Three tiers, **from hard to soft** (`match()`):
| tier | what is compared | example |
|---|---|---|
| ① genre-card hit | the current book's `primary genre`/`structure` and the pack's `applicable types.genre` **mutually contain** | current "suspense" ↔ dismantled "suspense-supernatural" |
| ② keyword overlap | the current book's trigger words (genre, hook library, payoff patterns...) overlap with the pack's `trigger keywords` | both have "foreshadowing" |
| ③ module-name hit | the module name appears in the current book's **question** (the sentence the author writes in the study) | the question mentions "hook" |
★ Why three tiers instead of one similarity score: **scores cannot be explained**.
  When the author asks "why are you using this book's lessons", the answer must be "because your book is suspense, and it is also tagged suspense",
  not "similarity 0.73". So `match()` returns **why it hit** (`hit`).
★ If it does not match, **do not use it** (do not force it in). A romance writing style applied
to suspense is worse than not using it --
  this is the typical way "indiscriminately citing lessons" goes wrong.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

_LOG = logging.getLogger('nws.booklab.store')

from booklab import skillgen as SG  # noqa: E402  （用它的 PREFIX / skills_dir）
from booklab.theory import CORE_AXES  # noqa: E402  （标签的核心轴，与 registry 同源）
# [EN] noqa: E402  (uses its PREFIX / skills_dir)
# [EN] noqa: E402  (the core axis of the tag, same origin as registry)

#: 一次最多引用几本拆书经验（**默认值**；真正的取值走旋钮 `BOOKLAB_LESSON_PACKS`）
# [EN] : maximum number of dismantling lesson packs to reference at once (**default value**; the real
# [EN] value comes from the knob `BOOKLAB_LESSON_PACKS`)
MAX_PACKS = 2
#: 给所有职位的那一段的字数上限
# [EN] : character limit for the paragraph given to all roles
AGENT_CHARS = 900
#: 给三人小组那一段的上限（他们拿的是完整版）
# [EN] : limit for the paragraph given to the three-person team (they get the full version)
WRITER_CHARS = 1800


def max_packs() -> int:
    """引用份数上限（旋钮 `BOOKLAB_LESSON_PACKS`）。读不到就用模块常量。
        English:
    Citation count limit (knob `BOOKLAB_LESSON_PACKS`). If it cannot be read, use the module
    constant.
    """
    try:
        from config import CFG
        return max(1, int(CFG.i('BOOKLAB_LESSON_PACKS') or MAX_PACKS))
    except Exception:                                            # noqa: BLE001
        return MAX_PACKS


def writers_full() -> bool:
    """三人小组是不是该拿**完整版**（旋钮 `BOOKLAB_SKIP_WRITERS` **取反**）。

    名字做成反的（`SKIP_WRITERS=True` = 不给完整版）是为了与"省钱"的
    默认方向一致：**默认给完整版**（默认值 False）。
    
        English:
    Whether the three-person team should get the **full version** (knob `BOOKLAB_SKIP_WRITERS`
    **negated**).
        The name is made inverted (`SKIP_WRITERS=True` = do not give the full version) to align with the default direction of "saving money":
        **full version by default** (default value False).
    """
    try:
        from config import CFG
        return not bool(CFG.b('BOOKLAB_SKIP_WRITERS'))
    except Exception:                                            # noqa: BLE001
        return True


@dataclass
class Pack:
    """一个拆书技能包。
        English:
    A dismantling skill pack.
    """

    dir: Path
    name: str = ''
    brief: dict = field(default_factory=dict)
    modules: list[dict] = field(default_factory=list)
    final: dict = field(default_factory=dict)
    coverage: str = ''
    notes: list[str] = field(default_factory=list)
    #: 命中的理由（`match` 填）—— 给人看"凭什么用它"
    # [EN] : the reason for a hit (filled by `match`) -- to show people "why use it"
    hit: str = ''

    @property
    def title(self) -> str:
        return str(self.brief.get('title') or self.name)

    @property
    def genre(self) -> str:
        return str(self.brief.get('genre') or '')

    @property
    def tags(self) -> dict[str, list[str]]:
        """受控标签 `{轴: [值]}`（写在 `digest.json` 的 `final.标签` 里）。

        ★ 与 `skills/registry` 读的是**同一份数据**（都来自 `SKILL.md` 的
          frontmatter / `digest.json` 的 `final`）—— 但两条路读的场合不同：
          那边是"考据通道按问题找技能"，这里是"开卷时按类型卡挑拆书经验"。
          所以**不要**把它们合并成一处（合并会让一处的改动影响到另一处）。
        
                English:
        Controlled tags `{axis: [values]}` (written in `digest.json`'s `final.标签`).
                ★ Reads the **same data** as `skills/registry` (both come from `SKILL.md`'s
                  frontmatter / `digest.json`'s `final`) -- but the two paths read it on different occasions:
                  that side is "the research channel finds skills by question", here it is "at opening time, pick book-breakdown lessons by genre card".
                  So **do not** merge them into one place (merging would let a change in one place affect the other).
        """
        raw = self.final.get('标签') if isinstance(self.final, dict) else None
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[str]] = {}
        for k, v in raw.items():
            vals = [v] if isinstance(v, str) else list(v or [])
            vals = [str(x).strip() for x in vals if str(x).strip()]
            if vals:
                out[str(k).strip()] = vals
        return out

    @property
    def ok(self) -> bool:
        return bool(self.modules)


def list_packs(root: Path | None = None) -> list[Pack]:
    """列出所有拆书包（**只读**，读不了的那个跳过并记日志）。

    两个位置都扫：
      · `skills/book-dismantle/<书名>/`（2026-10-10 起的新位置，两级）；
      · `skills/书拆·<书名>/`（旧位置，一级）—— 留着是为了**旧包还能用**，
        不为了兼容而兼容：真的没有旧包时这一段什么都不做，零成本。
    
        English:
    List all dismantling packs (**read-only**; skip the unreadable one and log it).
        Scan both locations:
          · `skills/book-dismantle/<book name>/` (new location since 2026-10-10, two levels);
          · `skills/书拆·<book name>/` (old location, one level) -- kept so that **old packs still work**,
            not compatibility for compatibility's sake: when there really is no old pack this section does nothing, zero cost.
    """
    out: list[Pack] = []
    base_new = SG.book_root(root)
    if base_new.is_dir():
        for d in sorted(base_new.iterdir()):
            if d.is_dir():
                p = load_pack(d)
                if p is not None:
                    out.append(p)
    base_old = root or SG.skills_dir()
    if base_old.is_dir():
        for d in sorted(base_old.iterdir()):
            if d.is_dir() and d.name.startswith(SG.PREFIX):
                p = load_pack(d)
                if p is not None:
                    out.append(p)
    return out


def load_pack(d: Path) -> Pack | None:
    """读一个包（优先 `digest.json`；没有就退回解析 `SKILL.md` 的 frontmatter）。
        English:
    Read one pack (prefer `digest.json`; otherwise fall back to parsing the `SKILL.md` frontmatter).
    """
    d = Path(d)
    js = d / 'digest.json'
    if js.is_file():
        try:
            raw = json.loads(js.read_text(encoding='utf-8'))
            return Pack(dir=d, name=d.name,
                        brief=dict(raw.get('brief') or {}),
                        modules=[m for m in (raw.get('modules') or [])
                                 if isinstance(m, dict)],
                        final=dict(raw.get('final') or {}),
                        coverage=str(raw.get('coverage') or ''),
                        notes=[str(x) for x in (raw.get('notes') or [])])
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('拆书包 %s 的 digest.json 读不了：%r', d.name, e)
    md = d / 'SKILL.md'
    if not md.is_file():
        return None
    # 退回解析 md（老包 / 手改过的包）：模块名从 `### N. 名称` 里取
    # [EN] Fall back to parsing md (old packs / hand-edited packs): module name is taken from `### N. name`
    try:
        text = md.read_text(encoding='utf-8')
    except Exception:                                            # noqa: BLE001
        return None
    import re
    mods = [{'名称': m.group(1).strip()}
            for m in re.finditer(r'^### \d+\.\s*(.+)$', text, re.MULTILINE)]
    title = ''
    mm = re.search(r'^名称:\s*' + re.escape(SG.PREFIX) + r'(.+)$', text, re.MULTILINE)
    if mm:
        title = mm.group(1).strip()
    return Pack(dir=d, name=d.name, brief={'title': title or d.name},
                modules=mods[:6])


# ══════════════════════════════════════════════════════════════
#  匹配
# [EN] Matching
# ══════════════════════════════════════════════════════════════
def _terms(genre_card: dict) -> list[str]:
    """当前书的关键词（题材/结构/钩子库/爽点模式/冲突引擎…）。
        English:
    The current book's keywords (genre/structure/hook library/payoff patterns/conflict engine...).
    """
    out: list[str] = []
    if not isinstance(genre_card, dict):
        return out
    for k in ('主题材', '类型', '结构', '结构轴'):
        v = str(genre_card.get(k) or '').strip()
        if v:
            out.append(v)
    conf = genre_card.get('冲突偏好')
    if isinstance(conf, dict):
        for v in conf.values():
            s = str(v or '').strip()
            if s:
                out.append(s)
    for k in ('钩子库', '爽点模式', '人物原型库'):
        v = genre_card.get(k)
        if isinstance(v, list):
            out += [str(x).strip() for x in v if str(x).strip()]
    # 拆词：'悬疑·单元剧' → 悬疑 / 单元剧
    # [EN] Tokenize: 'suspense·anthology' -> suspense / anthology
    bits: list[str] = []
    for x in out:
        bits += [w for w in re.split(r'[·、,，/|\s]+', x) if len(w) >= 2]
    seen: list[str] = []
    for b in bits:
        if b not in seen:
            seen.append(b)
    return seen


def _overlap(a: list[str], b: list[str]) -> list[str]:
    """互相包含算命中（"悬疑" ↔ "悬疑灵异"）。返回命中的词。
        English:
    Mutual containment counts as a hit ("suspense" ↔ "suspense-supernatural"). Return the hit words.
    """
    hit: list[str] = []
    for x in a:
        for y in b:
            if x and y and (x in y or y in x):
                hit.append(x if len(x) <= len(y) else y)
                break
    return hit


def _common(a: str, b: str, n: int = 2) -> str:
    """`a` 与 `b` 的**最长公共子串**（短于 n 个字的返回空串）。

    ★ 中文没有词边界，所以"两个串像不像"不能靠 split，要靠**公共片段**。
    
        English:
    The **longest common substring** of `a` and `b` (returns an empty string if shorter than n
    characters).
        ★ Chinese has no word boundaries, so "are two strings similar" cannot rely on split, it relies on **shared fragments**.
    """
    a, b = str(a or ''), str(b or '')
    if len(a) < n or len(b) < n:
        return ''
    best = ''
    for i in range(len(a)):
        for j in range(i + n, len(a) + 1):
            piece = a[i:j]
            if piece in b and len(piece) > len(best):
                best = piece
    return best


def _shares_word(a: str, b: str, n: int = 2) -> bool:
    """`a` 与 `b` 有没有长度 ≥n 的**公共子串**。

    ★ 中文没有空格，`split()` 拆不出词 —— 第一版按标点拆词，于是
      "钩子要具体"整个成了**一个词**，作者问"钩子怎么留"永远匹配不上。
      改成"有没有两字以上的公共片段"：**"钩子"**是两个字的公共片段 → 命中。
      这是中文轻量匹配最实用的一招（不需要分词库，也不会因为分词错而漏）。
    
        English:
    Whether `a` and `b` have a **common substring** of length ≥n.
        ★ Chinese has no spaces, so `split()` cannot split words -- the first version split by punctuation, so
          "钩子要具体" became **one word** entirely, and when the author asked "how to keep a hook", it could never match.
          Changed to "is there a common fragment of two or more characters": **"钩子"** is a two-character common fragment -> hit.
          This is the most practical lightweight matching trick for Chinese (no tokenizer library needed, and no misses from bad tokenization).
    """
    return bool(_common(a, b, n))


def _overlap(a: list[str], b: list[str]) -> list[str]:
    """两边像不像。返回**命中的那个片段**（给人看"凭什么算像"）。

    ★★ 这里第一版写的是 `x in y or y in x`（互相包含），看着合理，
      但它**抓不住同题材的两种叫法** —— 当前书的类型卡写的是「悬疑灵异」，
      拆的那本书标的是「悬疑·单元剧」，两者**谁也不包含谁**，
      于是"类型相符"这一档永远不命中 → 拆书库里的东西一本都用不上。
      （判据 `verify_booklab` 的类型匹配那条就是盯这个的。）
      改成比**公共片段**之后，"悬疑"这个两字片段命中，档位才真的起作用。
    
        English:
    Whether the two sides look alike. Returns **the matched fragment** (to show people "why it
    counts as alike").
        ★★ The first version here wrote `x in y or y in x` (mutual containment), which looks reasonable,
          but it **cannot capture two different names for the same subject matter** -- the current book's genre card says "悬疑灵异",
          while the book being broken down is labeled "悬疑·单元剧", and the two **contain neither** the other,
          so the "genre matches" tier never hits -> nothing in the book-breakdown library can be used at all.
          (The `verify_booklab` criterion's genre-matching item is exactly what watches for this.)
          After changing to comparing **common fragments**, the two-character fragment "悬疑" hits, and only then does the tier actually take effect.
    """
    hit: list[str] = []
    for x in a:
        for y in b:
            if not x or not y:
                continue
            c = _common(x, y)
            if c and c not in hit:
                hit.append(c)
                break
    return hit


def match(genre_card: dict, packs: list[Pack] | None = None, *,
          question: str = '', limit: int | None = None,
          want_tags: dict[str, list[str]] | None = None) -> list[Pack]:
    """挑出"和这本书像"的拆书经验。

    `question` = 作者当前手写的那几句（书斋·自定义风格 / 本幕提示）。有它时
    **模块名命中**也算一档 —— 作者在问"钩子怎么留"，那本拆过钩子的书就该被想起来。

    `want_tags` = **作者/类型卡给的受控标签**（`{轴: [值]}`）。有它时多一档打分：
    标签**精确命中**，且**核心轴（题材/读者需求/情绪）权重 2 分、其余 1 分**；
    三轴全不命中就不返回（宁可说"库里没有"，也不推一份不相关的拆解）。

    `limit=None` 时读旋钮 `BOOKLAB_LESSON_PACKS`。

    ★ 2026-10-10 加标签这一档的来历：`oh-story`（MIT）的索引侧要求
      **值必须取自标签词表**，且"核心轴 2 分、其余 1 分、无核心轴命中不返回"。
      本项目的 `store._common`（中文公共片段匹配）**保留** ——
      它解决"悬疑 ↔ 悬疑灵异"这种**同义不同形**，是本地已有的优点，不要因为
      有了标签就把它删掉（标签是收敛，公共片段是兜底，两件事）。
    
        English:
    Pick out book-breakdown lessons that "resemble this book".
        `question` = the few sentences the author currently wrote by hand (book studio · custom style / this act's prompt). When present,
        **module-name matches** also count as a tier -- the author is asking "how to keep a hook", so the book that broke down hooks should be recalled.
        `want_tags` = **controlled tags given by the author/genre card** (`{axis: [values]}`). When present, one more scoring tier:
        tags **hit exactly**, and **core axes (subject matter/reader need/emotion) weigh 2 points, the rest 1 point**;
        if none of the three axes hit, return nothing (better to say "not in the library" than to push an irrelevant breakdown).
        When `limit=None`, read the knob `BOOKLAB_LESSON_PACKS`.
        ★ The origin of adding the tag tier on 2026-10-10: `oh-story` (MIT)'s index side requires
          **values must come from the tag vocabulary**, and "core axes 2 points, the rest 1 point, no return if no core axis hits".
          This project's `store._common` (Chinese common-fragment matching) is **kept** --
          it solves **same-meaning-different-form** cases like "悬疑 ↔ 悬疑灵异", and is a locally existing strength; do not delete it just because
          tags now exist (tags are convergence, common fragments are the fallback -- two different things).
    """
    packs = packs if packs is not None else list_packs()
    if not packs:
        return []
    if limit is None:
        limit = max_packs()
    mine = _terms(genre_card)
    q = str(question or '')
    tags = {str(k): [str(x) for x in (v or [])] for k, v in (want_tags or {}).items()}
    core_hit_any = False
    scored: list[tuple[int, Pack]] = []
    for p in packs:
        if not p.ok:
            continue
        score = 0
        hits: list[str] = []
        # ① 类型（硬命中）
        # [EN] ① Genre (hard hit)
        g_hit = _overlap(mine, [p.genre])
        if g_hit:
            score += 100
            hits.append('类型相符：' + '、'.join(g_hit[:3]))
        # ② 触发词重叠
        # [EN] ② Trigger word overlap
        kws = [str(m.get('名称') or '') for m in p.modules]
        kw_hit = _overlap(mine, kws + [p.title])
        if kw_hit:
            score += 20 * len(set(kw_hit))
            hits.append('关键词重叠：' + '、'.join(sorted(set(kw_hit))[:4]))
        # ③ 模块名出现在作者的问题里
        # [EN] ③ Module name appears in the author's question
        #
        # ⚠ 比的是**有没有公共的两字片段**，不是"整个模块名是问题的子串"。
        #   第一版写 `m['名称'] in q` —— 作者问"钩子怎么留"、模块叫"钩子要具体"时
        #   **匹配不上**（整个名字不在那句话里），而"作者在问钩子"恰恰是
        #   这一档最该起作用的时候。换成 `_shares_word` 之后"钩子"能对上。
        # [EN] ⚠ What is compared is **whether there is a shared two-character fragment**, not "the whole
        # [EN] module name is a substring of the question".
        # [EN] The first version wrote `m['name'] in q` -- when the author asks "how to keep a hook" and the
        # [EN] module is named "hooks must be specific"
        # [EN] it **fails to match** (the whole name is not in that sentence), yet "the author is asking about
        # [EN] hooks" is exactly
        # [EN] when this tier should kick in. After switching to `_shares_word`, "hook" matches.
        if q:
            q_hit: list[str] = [str(m.get('名称'))
                                for m in p.modules
                                if _shares_word(str(m.get('名称') or ''), q)]
            if q_hit:
                score += 40 * len(q_hit)
                hits.append('你问到的：' + '、'.join(str(x) for x in q_hit[:3]))
        # ④ 受控标签（核心轴 2 分、其余 1 分）
        # [EN] ④ Controlled tags (core axis 2 points, others 1 point)
        if tags:
            ptags = getattr(p, 'tags', None) or {}
            tag_hits: list[str] = []
            tag_score = 0
            for axis, vals in tags.items():
                theirs = set(ptags.get(axis) or [])
                for v in vals:
                    if v in theirs:
                        tag_score += 10 * (2 if axis in CORE_AXES else 1)
                        tag_hits.append(f'{axis}={v}')
            if tag_hits:
                score += tag_score
                hits.append('标签命中：' + '、'.join(tag_hits[:4]))
                if any(h.split('=', 1)[0] in CORE_AXES for h in tag_hits):
                    core_hit_any = True
            elif not any(ptags):
                # 这一份没打标签：**不算命中，但也不当没看见**（照实说）
                # [EN] this one is untagged: **does not count as a hit, but not ignored either** (report it as-is)
                hits.append('（这一份没有受控标签，本次跳过标签匹配）')
        if score:
            p.hit = '；'.join(hits)
            scored.append((score, p))
    # ★ 给了标签、却**一份都没命中核心轴** ⇒ 当作"库里没有"（返回空）。
    #   为什么这么狠：不设这道闸，只要"适用阶段"撞一个值就会返回一份
    #   题材完全不相干的经验 —— 那比不返回更坏（模型会照着它写）。
    # [EN] ★ tagged, but **not a single core-axis hit** ⇒ treat as "not in the library" (return empty).
    # [EN] Why so harsh: without this gate, any collision on a single "applicable stage" value would return
    # [EN] a pack about
    # [EN] a completely unrelated subject -- which is worse than returning nothing (the model would write
    # [EN] following it).
    if tags and scored and not core_hit_any:
        return []
    scored.sort(key=lambda x: (-x[0], x[1].name))
    return [p for _s, p in scored[:max(1, int(limit))]]


# ══════════════════════════════════════════════════════════════
#  渲染成提示词里的一段
# [EN] Render as a paragraph in the prompt
# ══════════════════════════════════════════════════════════════
def _clip(s: str, n: int) -> str:
    s = ' '.join(str(s or '').split())
    return s if len(s) <= n else s[:n].rstrip() + '…'


HEAD = '【同类书的写法（从拆书库里取，供参考）】'


def render(packs: list[Pack], *, full: bool = False,
           chars: int | None = None) -> str:
    """把挑出来的经验拼成一段。

    `full=False`（给所有职位）：只给**模块名 + 怎么做**，压缩。
    `full=True`（给三人小组）：再加上节奏 / 人设 / 语言 / **不适合**。
    
        English:
    Assemble the picked-out lessons into a paragraph.
        `full=False` (for all positions): give only **module name + how to do it**, compressed.
        `full=True` (for the three-person team): also add pacing / character design / language / **what is unsuitable**.
    """
    if not packs:
        return ''
    cap = chars if chars is not None else (WRITER_CHARS if full else AGENT_CHARS)
    blocks: list[str] = [HEAD]
    for p in packs:
        blocks.append(f'▸ 《{p.title}》'
                      + (f'（{p.genre}）' if p.genre else '')
                      + (f' —— {p.hit}' if p.hit else ''))
        for m in p.modules[: (6 if full else 4)]:
            one = f'· {m.get("名称")}：{_clip(m.get("怎么做"), 120 if full else 90)}'
            if full and m.get('什么时候用'):
                one += f'（什么时候用：{_clip(m.get("什么时候用"), 60)}）'
            blocks.append(one)
        if full:
            for key, label in (('节奏', '节奏'), ('人设', '立人'),
                               ('语言', '文风')):
                v = p.final.get(key)
                if v:
                    blocks.append(f'· {label}：{_clip(v, 160)}')
            bad = p.final.get('不适合')
            if bad:
                blocks.append('· **不要照搬**：'
                              + _clip('；'.join(str(x) for x in bad[:2]), 140))
    blocks.append('（这些是**别的书**的做法，用来提醒你**有这么一些路子**；'
                  '照不照用、用哪一条，由这一场戏自己定。）')
    return _clip('\n'.join(blocks), cap)


def for_agents(genre_card: dict, *, question: str = '',
               packs: list[Pack] | None = None,
               limit: int | None = None) -> str:
    """给**所有职位**的一段（压缩版）。没有匹配就空串（**不硬塞**）。
        English:
    The paragraph for **all positions** (compressed version). Empty string if no match (**do not
    force-fit**).
    """
    return render(match(genre_card, packs, question=question, limit=limit))


def for_writers(genre_card: dict, *, question: str = '',
                packs: list[Pack] | None = None,
                limit: int | None = None) -> str:
    """给**三人小组**（小说作家 · 剧作者 · 导演）的一段（完整版）。

    他们拿到的比别的职位多：节奏 / 立人 / 文风 / **不要照搬什么** ——
    因为这几位决定了"这个故事怎么讲"，而写法经验正是用在这一层上。
    
        English:
    The paragraph for the **three-person team** (novelist · playwright · director) (full version).
        What they get is more than other positions: pacing / character-building / writing style / **what not to copy directly** --
        because these few decide "how this story is told", and writing-technique lessons are exactly what applies at this layer.
    """
    return render(match(genre_card, packs, question=question, limit=limit),
                  full=True)


def table_md(genre_card: dict, packs: list[Pack] | None = None) -> str:
    """《本书可参考的写法.md`：这一本用上了哪些拆书经验、凭什么。
        English:
    "Reference-worthy writing styles of this book.md": which book-breaking experiences were used in
    this one, and on what basis. [Output language] All **output text** must be written in
    **Simplified Chinese** — narration, voiceover, dialogue, documentation, summaries, suggestions
    all count, **even if the source material is in another language**. Proper nouns such as person
    names, place names, and book titles **retain their original spelling**; do not transliterate or
    paraphrase them. **Key names** in the JSON **stay as-is** (e.g. "动作", "台词"); only write the
    **values** in Chinese.
    """
    all_packs = packs if packs is not None else list_packs()
    if not all_packs:
        return ('# 本书可参考的写法\n\n> 拆书库里还没有东西。\n>\n'
                '> 想让 Agent 有"同类书的写法"可用：在开始菜单点「拆　书」，'
                '把一本你觉得写得好的书拆一遍。\n')
    used = match(genre_card, all_packs)
    rows = ['# 本书可参考的写法', '',
            f'> 拆书库里共 **{len(all_packs)}** 份经验，'
            f'这一本用上了 **{len(used)}** 份（按题材与关键词匹配）。', '',
            '## 这一本用上的', '',
            '| 拆自 | 类型 | 为什么用它 | 拿过来的写法 |',
            '|---|---|---|---|']
    for p in used:
        names = '、'.join(str(m.get('名称') or '') for m in p.modules[:4])
        rows.append(f'| 《{p.title}》 | {p.genre or "—"} | {p.hit or "—"} | {names} |')
    rest = [p for p in all_packs if p not in used]
    if rest:
        rows += ['', '## 库里还有（这一本没匹配上）', '',
                 '| 拆自 | 类型 | 库里有什么 |', '|---|---|---|']
        for p in rest:
            names = '、'.join(str(m.get('名称') or '') for m in p.modules[:4])
            rows.append(f'| 《{p.title}》 | {p.genre or "—"} | {names} |')
    rows += ['', '> 匹配规则：**类型互相包含**（悬疑 ↔ 悬疑灵异）为硬命中；',
             '> 关键词重叠（钩子、伏笔、反差…）加分；',
             '> 你在书斋里写的问题里出现模块名，也会把它想起来。',
             '> 匹配不上就**不用** —— 硬塞一本言情的写法进悬疑，比不用更坏。']
    return '\n'.join(rows) + '\n'
