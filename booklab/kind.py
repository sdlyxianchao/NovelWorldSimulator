# -*- coding: utf-8 -*-
"""**判书**：这是一本什么书 —— 小说、专业书，还是两者混着。

为什么要有这一层
----------------
用户 2026-10-27：「我是不是可以找一些中国古代建筑史等书籍来拆书进而增加相关 SKILL
…让它可以拆小说 也可以拆各种专业书籍 用来做素材」。

★ 拆书现在**整条链路写死了"这是一本小说"**：七个维度是骨架/人物/情绪/情节，
  取样是"黄金三章 + 按情绪强度挑章"，指标在看"对白占比"。
  这些对《中国古代建筑史》**全是错的**：它没有人物、没有情绪曲线、
  对白占比天然是 0（现有指标会把它报成"几乎没有对话"的异常）。

⇒ 所以第一件事不是改提示词，是**先判这本书是什么**，然后按类型分流：
  · `novel`     —— 走现有那条**写法线**（七维：节奏/人设/文风…）
  · `reference` —— 走新的那条**素材线**（条目：知识点 + 出处 + 怎么用）
  · `mixed`     —— 两条都走（如"历史小说 + 大量考据"、"学术随笔"）

为什么用**启发式**而不是一律问模型
----------------------------------
1. **零成本、零延迟**：判类型只该花毫秒，不该为"这是不是小说"付一次 LLM；
2. **可判据化**：规则能写进 `verify_booklab` 逐条钉住，模型的判断**没法反例法**；
3. 特征其实很硬：专业书有"参考文献 / 图 3-2 / 表 1-1 / 索引 / 绪论"，
   小说有"他说 / 她道 + 引号"。这些是**排版事实**，不是语感。
⚠ 启发式判不准的时候（两方分数接近）⇒ 归 `mixed`，并且**界面上允许用户改**
  （判错类型的代价是拆出来一整本废条目，必须能人工兜回来）。

English:
**Book judging**: what kind of book is this -- novel, reference, or a mix.
Why this layer exists
----------------
User 2026-10-27: "could I feed in books like a history of Chinese architecture and split them to
grow the related SKILLs ... make it split novels **and** specialist books, for material".
★ Book-splitting currently hard-codes "this is a novel" along the **whole** chain: the seven
dimensions are skeleton/character/emotion/plot, sampling is "golden three chapters + pick chapters
by emotional intensity", and the metrics look at "dialogue share". All of that is **wrong** for a
history of Chinese architecture: it has no characters, no emotional curve, and its dialogue share
is naturally 0 (the existing metric reports that as an anomaly: "almost no dialogue").
=> So the first thing is not to rewrite prompts, it is to **judge what this book is**, then branch:
  · `novel`     -- the existing **craft line** (seven dimensions: pacing / character / voice ...)
  · `reference` -- the new **material line** (entries: fact + source + how to use it)
  · `mixed`     -- both (e.g. "historical novel + heavy research", "academic essays")
Why **heuristics** rather than always asking the model
----------------------------------
1. **Zero cost, zero latency**: judging the type should take milliseconds, not one LLM call to ask
   "is this a novel?";
2. **Criterion-friendly**: rules can be nailed down one by one in `verify_booklab`; a model's
   verdict **cannot be mutated** to prove the criterion can go red;
3. the features are actually hard facts: reference books carry "参考文献 / 图 3-2 / 表 1-1 / 索引 /
   绪论", novels carry "他说 / 她道 + quotation marks". These are **typographic facts**, not vibes.
⚠ When the heuristics can't tell (scores are close) => return `mixed`, and **let the user override
it in the UI** (a wrong type costs an entire book of useless entries; there must be a manual way
back).
"""
from __future__ import annotations

import re

from i18n import t

#: 三种类型（**闭集** —— 下游 `if` 只认这三个值，别再冒出第四种）
# [EN] : The three types (a **closed set** -- downstream `if`s only know these three, no fourth)
NOVEL = 'novel'
REFERENCE = 'reference'
MIXED = 'mixed'
ALL_KINDS = (NOVEL, REFERENCE, MIXED)

#: ⚠ 本模块里 `t` 是**翻译函数**（`i18n.t`）⇒ 任何局部变量都不许叫 `t`
#:   （2026-10-27：`_score`/`density` 里原本有个 `t = str(text)`，一 import 就会
#:    `TypeError: 'str' object is not callable`）。正文样本一律叫 `s`。
# [EN] : ⚠ In this module `t` is the **translation function** (`i18n.t`) => no local variable may
# [EN] be named `t` (2026-10-27: `_score`/`density` had `t = str(text)`; importing `t` would then
# [EN] raise `TypeError: 'str' object is not callable`). Body samples are always named `s`.

#: ★ 专业书的**排版事实**（不是语感）：这些标记几乎不会出现在小说里。
#:   每条都是"看见了就基本能定"的硬信号，权重也给得高。
# [EN] : ★ Reference books' **typographic facts** (not vibes): these marks almost never appear in a
# [EN] novel. Each is a hard signal -- "seen it, basically settled" -- hence the high weight.
_REF_MARKS: tuple[tuple[str, int], ...] = (
    (r'参考文献', 6), (r'注\s*释', 3), (r'索\s*引', 5), (r'绪\s*论', 4),
    (r'摘\s*要', 3), (r'Abstract', 3), (r'ISBN', 5), (r'出\s*版\s*社', 4),
    (r'编\s*著', 3), (r'第\s*[一二三四五六七八九十\d]+\s*节', 3),
    (r'图\s*\d+\s*[-–—.]?\s*\d*', 4), (r'表\s*\d+\s*[-–—.]?\s*\d*', 4),
    (r'\[\d+\]', 3),                       # 脚注编号 [1] [2]
    (r'见\s*图\s*\d', 3), (r'(?i)fig\.\s*\d', 2), (r'(?i)op\.\s*cit', 2),
    (r'本\s*章\s*小\s*结', 3), (r'思\s*考\s*题', 3),
)

#: ★ 小说的硬信号：对话（引号 + 引导词）。专业书**几乎不出现**。
# [EN] : ★ Novels' hard signal: dialogue (quotation marks + speech tags). Reference books
# [EN] **almost never** have it.
_DIALOG_RE = re.compile(r'[「“"『\'][^」”"』\']{2,80}[」”"』\']')
_SPEECH_RE = re.compile(
    r'(说|道|问|答|喊|叫|骂|笑|叹|低声|沉声|喃喃|嘟囔|喝道|应道|回道)'
    r'[：:，,。！!？?）)]?\s*[「“"『\']')

#: 小说里常见的叙事词（**弱**信号：专业书也会写"据说"，所以权重低）
# [EN] : Narrative words common in novels (**weak** signal: reference books also say "据说")
_NARR_RE = re.compile(r'(心里想|暗道|心头|忽然|猛地|缓缓地|只见|却说|话说)')

#: 单位 / 数据密度：专业书满是"3.6 米""公元 782 年""出挑 5 踩"
# [EN] : Unit / data density: reference books are full of "3.6 米", "公元 782 年", "出挑 5 踩"
_DATA_RE = re.compile(
    r'\d+(?:\.\d+)?\s*(?:米|厘米|毫米|公里|尺|寸|丈|斤|两|度|年|月|日|'
    r'世纪|年代|%|％|平方米|立方米|公斤|吨|层|间|架|踩|斗)')

#: 判定时取多少字做样本（**从头取**：前言/目录最能说明类型）
# [EN] : How many characters to sample (taken **from the start**: the preface / TOC tells the most)
SAMPLE_CHARS = 30_000
#: 判 `mixed` 的余量：两方分数差小于这个比例就"不敢定"
# [EN] : Margin for `mixed`: if the two scores differ by less than this share, we "dare not decide"
MIXED_MARGIN = 0.25


def _score(text: str) -> tuple[float, float]:
    """返回 `(小说分, 专业书分)`（都归一到 0~1）。
        English:
    Return `(novel score, reference score)` (both normalised to 0~1).
    """
    s = str(text or '')
    if not s.strip():
        return 0.0, 0.0
    n = max(1, len(s))
    ref = 0.0
    for pat, w in _REF_MARKS:
        try:
            hits = len(re.findall(pat, s))
        except re.error:
            continue
        if hits:
            # 同一标记出现再多也不无限加分：封顶 3 次（"参考文献"出现 40 次还是同一件事）
            # [EN] Cap at 3 hits: "参考文献" appearing 40 times is still one and the same fact
            ref += w * min(3, hits)
    ref += min(6.0, len(_DATA_RE.findall(s)) * 0.15)      # 数据密度
    novel = 0.0
    dialog = len(_DIALOG_RE.findall(s))
    novel += min(10.0, dialog * (4000.0 / n) * 0.9)       # 对话密度（按字数归一）
    novel += min(5.0, len(_SPEECH_RE.findall(s)) * 0.35)  # "他说「"
    novel += min(3.0, len(_NARR_RE.findall(s)) * 0.10)    # 叙事词（弱）
    # 归一：两边都用同一个分母，便于比较
    # [EN] Normalise both by the same denominator so they can be compared
    return min(1.0, novel / 18.0), min(1.0, ref / 30.0)


def judge(text: str, *, genre_hint: str = '') -> str:
    """判类型 → `NOVEL` / `REFERENCE` / `MIXED`。

    Args:
        text:       正文样本（会自己截前 `SAMPLE_CHARS` 字）。
        genre_hint: 用户在界面填的"类型"自由文本（如"建筑史""年代文"）。
                    ★ 它是**辅助**不是判决：写一本人设书也可能填"小说"，
                      见过用户填"悬疑·单元剧"而书其实是专业书 ⇒
                      只在两边分数**都很低**（样本太短、特征不足）时才听它。

        English:
    Judge the type -> `NOVEL` / `REFERENCE` / `MIXED`.
        Args:
        text:       body sample (truncated to the first `SAMPLE_CHARS` characters).
        genre_hint: the free-text "type" the user typed in the UI (e.g. "建筑史", "年代文").
                    ★ It is a **hint, not a verdict**: someone filling a character book may also
                    write "小说", and users have typed "悬疑·单元剧" for what is really a reference
                    book => it is only listened to when **both** scores are very low (sample too
                    short, features insufficient).
    """
    sample = str(text or '')[:SAMPLE_CHARS]
    novel, ref = _score(sample)
    # 两边都没信号 ⇒ 听用户填的（或归 mixed，让用户自己改）
    # [EN] Neither side has a signal => listen to what the user typed (or say mixed and let them fix)
    if novel < 0.05 and ref < 0.05:
        hint = str(genre_hint or '')
        if re.search(r'史|论|教程|教材|手册|词典|词典|图鉴|规范|标准|志|考|概论|原理', hint):
            return REFERENCE
        if re.search(r'小说|言情|玄幻|悬疑|科幻|穿越|年代|文|剧', hint):
            return NOVEL
        return MIXED
    total = novel + ref
    if total <= 0:
        return MIXED
    gap = abs(novel - ref) / total
    if gap < MIXED_MARGIN:
        return MIXED
    return NOVEL if novel > ref else REFERENCE


def density(text: str) -> float:
    """一章的**信息密度**（0~5，专业书挑章用）。

    ★ 这是"专业书没有高潮章节"那个问题的答案：小说按**情绪强度**挑章
      （`reader.pick_deep` 的第 ② 条），专业书改按**信息密度**挑 ——
      挑"事实/数据/规矩最密"的那几章，而不是"最精彩"的那几章。

    ★ 为什么放在这里（而不是 `reader`）：判据也要用它核对"挑出来的章
      是不是真的密度最高"，**同一个打分只能有一处实现**。

    ⚠ 空章（前言 / 索引 / 参考文献 / 版权页 / 纯图版）必须得 0
      —— 它们是"字数不少但一条素材都拆不出来"的典型，
      被挑进精读就是白白花一次 LLM。

        English:
    A chapter's **information density** (0~5; used to pick reference-book chapters).
        ★ This is the answer to "a reference book has no climax": novels pick chapters by
        **emotional intensity** (rule ② of `reader.pick_deep`), reference books pick by
        **information density** -- the chapters densest in facts / data / rules, not the most
        "exciting" ones.
        ★ Why here (not in `reader`): the criteria use it too, to check that "the picked chapters
        really are the densest" -- **one scoring implementation only**.
        ⚠ Empty chapters (preface / index / bibliography / copyright / plate pages) must score 0 --
        they are the classic "plenty of characters, not one extractable entry", and picking them
        for deep reading wastes an LLM call.
    """
    s = str(text or '')
    if not s.strip():
        return 0.0
    if _EMPTY_CHAPTER_RE.search(s[:400]):        # 只扫开头（标题/前言写在最前）
        return 0.0
    n = max(1, len(s))
    score = 0.0
    try:
        score += min(2.0, len(_DATA_RE.findall(s)) * (2000.0 / n) * 0.5)
    except re.error:
        pass
    for pat, w in _REF_MARKS:
        try:
            hits = len(re.findall(pat, s))
        except re.error:
            continue
        if hits:
            score += min(0.6, w * 0.06 * min(3, hits) * (2000.0 / n) * 2)
    # 术语密度：连续的专业词（这里用"书名号里的词"与"4 字以上的名词块"代理）
    # [EN] Term density: proxied by words in 《》 and 4+ character noun-ish runs
    try:
        score += min(1.0, len(re.findall(r'《[^》]{2,20}》', s)) * 0.10)
    except re.error:
        pass
    return round(min(5.0, score), 2)


#: ★ 空章（**字数不少但拆不出素材**）：前言 / 序 / 索引 / 参考文献 / 版权页 /
#:   图版目录 / 附录 / 后记。它们被挑进精读 = 白白花一次 LLM。
# [EN] : ★ Empty chapters (**plenty of characters, no material**): preface / foreword / index /
# [EN] bibliography / copyright / list of plates / appendix / afterword. Picking them for deep
# [EN] reading = an LLM call spent for nothing.
_EMPTY_CHAPTER_RE = re.compile(
    r'(前\s*言|序\s*言|前\s*记|编者的话|出版说明|凡\s*例|目\s*录|'
    r'索\s*引|参考文献|注释表|图\s*版|图\s*版目录|插\s*图\s*目\s*录|'
    r'附\s*录|后\s*记|跋|版权页|图书在版编目|内容提要|作者简介|'
    # ⚠ `(?i)` 只能写在表达式**开头**，写在中间会 `re.error`（全局标志位置非法）
    #   ⇒ 用 `(?i:…)` 这种**带作用域**的写法。
    # [EN] ⚠ `(?i)` is only legal **at the start**; mid-pattern it raises `re.error` (global flags
    # [EN] not at the start) => use the scoped form `(?i:…)`.
    r'(?i:contents)|(?i:acknowledg)|(?i:bibliograph)|(?i:index))')


def label(kind: str) -> str:
    """类型名（界面与报告用，**按界面语言翻译**）。

    ★ 为什么在函数里现造这张表，而不是模块级常量：
      翻译要跟着**运行时**的语言走（`set_lang()` 之后还得是英文），
      模块级字典会把它钉死在导入那一刻的语言上。
      用字面量 `t('…')` 也让 i18n 覆盖判据**扫得到**这三条（漏译会红）。

        English:
    The type name (for the UI and reports, **translated to the UI language**).

    ★ Why the table is built inside the function instead of being a module constant:
      translation must follow the **runtime** language (still English after `set_lang()`),
      whereas a module-level dict would freeze it at import time.
      Using literal `t('…')` also lets the i18n-coverage criterion **see** these three
      (a missing translation turns it red).
    """
    table = {NOVEL: t('小说'),
             REFERENCE: t('专业书 / 资料书'),
             MIXED: t('混合（小说 + 考据）')}
    return table.get(str(kind), str(kind))


def why(text: str) -> str:
    """**为什么判成这个**（给界面/日志看的证据串）。

    ★ 判错类型的代价是一整本废条目 ⇒ 判据和界面都要能说出理由，
      不许只给一个结论（"我判它是专业书"这种话没法复核）。

        English:
    **Why it was judged this way** (an evidence string for the UI / logs).
        ★ A wrong type costs a whole book of useless entries => both the criteria and the UI must be
        able to state the reason; never give a bare verdict ("I judged it a reference book" cannot
        be re-checked).
    """
    sample = str(text or '')[:SAMPLE_CHARS]
    novel, ref = _score(sample)
    dialog = len(_DIALOG_RE.findall(sample))
    data = len(_DATA_RE.findall(sample))
    marks = []
    for pat, _w in _REF_MARKS:
        try:
            n = len(re.findall(pat, sample))
        except re.error:
            continue
        if n:
            marks.append(f'{pat}×{n}')
    return (f'小说分 {novel:.2f}（对话 {dialog} 处）/ 专业书分 {ref:.2f}'
            f'（数据 {data} 处；标记：{"、".join(marks[:6]) or "无"}）'
            f' ⇒ {label(judge(sample))}')
