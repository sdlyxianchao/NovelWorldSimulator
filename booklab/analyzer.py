# -*- coding: utf-8 -*-
"""**拆解**：把一本书读成一份"能拿走的写法"。

四道工序（`theory.py` 的模块头有完整说明）
----------------------------------------
```text
① 建目录   分章（`reader`，零成本）
② 粗扫     分批读 → 每章一句话 + 功能 + 情绪强度
③ 精拆     挑出来的重点章逐段读 → 手法
④ 归纳     跨章提炼 → **可复用的模块**
```

三条纪律
--------
1. **不许静默降级**：粗扫里某一批没拿到结果，要把"哪一批没读到"记下来
   （`Digest.notes`），并**照实说这本书是浮着拆的** —— 悄悄少读几批、
   然后交出一份看起来完整的报告，比直接失败更坏。
2. **每一步都要留下"读到了什么"**：粗扫的逐章表和精拆的笔记都要进产物，
   作者才能复核"你这结论是从哪儿来的"。
3. **不抄原文**：所有产出都是**做法**。判据会查产物里有没有成段引用
   （`verify_booklab` 的版权那条）。

⚠ 本模块**不自己发请求**，全走 `llm.replies.ask` —— 那是全项目唯一的
  「解析 → 重试 → 抢救」入口，对话日志、预算台账、输出语言注入都挂在它上面。

English:
**Dissection**: read a book into a "takeaway writing method".
Four processes (the header of `theory.py` has the full explanation)
----------------------------------------
```text
① Create directory   chapter split (`reader`, zero-cost)
② Rough scan     batched reading → one sentence per chapter + function + emotional intensity
③ Fine dissection     paragraph-by-paragraph reading of selected key chapters → techniques
④ Summarize     cross-chapter extraction → **reusable modules**
```
Three disciplines
--------
1. **No silent degradation**: if a batch in the rough scan does not get a result, record "which batch was not read"
   (`Digest.notes`), and **truthfully say this book was dissected floating** — quietly reading fewer batches,
   then handing in a seemingly complete report, is worse than failing outright.
2. **Every step must leave behind "what was read"**: both the per-chapter table of the rough scan and the notes of the fine dissection must go into the output,
   so the author can review "where did your conclusion come from".
3. **Do not copy the original text**: all output is **method**. The criteria check whether the output contains paragraph-length quotations
   (the copyright item of `verify_booklab`).
⚠ This module **does not make requests itself**; everything goes through `llm.replies.ask` —
that is the project's only
  entry point for "parse → retry → salvage"; conversation logs, budget ledger, and output language injection all hang off it.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from i18n import t
from llm.replies import ask

from booklab import reader as R
from booklab import theory as T
# ★ 2026-10-27：类型判定（小说 / 专业书 / 混合）—— 决定走"写法线"还是"素材线"
# [EN] ★ 2026-10-27: type judging (novel / reference / mixed) -- decides the craft line vs the
# [EN] material line
from booklab import kind as K
from booklab.kind import NOVEL, REFERENCE, MIXED

_LOG = logging.getLogger('nws.booklab.analyzer')

#: 每一步的输出上限（安全网，不是目标值）
# [EN] : Output cap per step (safety net, not a target value)
_SCAN_TOKENS = 3000
_DEEP_TOKENS = 2600
#: ★ 2026-10-10 从 3200 提到 4600：模块卡升级成 EM 五门禁卡之后，
#:   每条要写的字段从 5 个变成 10 个（加 `读者想看什么/情绪链/戏剧单元/
#:   可替换项/不可照搬`），还要多给一份受控标签。
#:   ⚠ 这个数**只影响上限**，不多花钱（模型写不满就用不到）；
#:     但给少了会**截在半句**上 —— 本项目在"正文被思考吃光"那件事上已经吃过一次。
# [EN] : ★ 2026-10-10 raised from 3200 to 4600: after the module card was upgraded to the EM five-gate
# [EN] card,
# [EN] : the fields to write per item went from 5 to 10 (adding
# [EN] `reader_wants/emotion_chain/dramatic_unit/
# [EN] :   replaceable_items/not_copyable`), plus one more controlled-tag set.
# [EN] : ⚠ This number **only affects the cap**, it does not cost more (if the model does not fill it,
# [EN] it goes unused);
# [EN] : but giving too little will **truncate mid-sentence** — this project already got burned once on
# [EN] the "body text eaten by thinking" issue.
_FINAL_TOKENS = 4600
#: 粗扫最多跑几批的**默认值**（真正的取值走 `CFG`，见 `run()`）——
#: 旋钮 `BOOKLAB_MAX_BATCHES` 的 default 必须与它一致（判据会查这一个数不一处）。
# [EN] : **Default value** for the max number of batches in the rough scan (the real value comes from
# [EN] `CFG`, see `run()`) —
# [EN] : the default of the knob `BOOKLAB_MAX_BATCHES` must match it (the criteria check this one
# [EN] number, not in one place).
MAX_BATCHES = 26


def _cfg_max_batches() -> int:
    """粗扫批数上限（`BOOKLAB_MAX_BATCHES`）。读不到就用模块常量。
        English:
    Rough scan batch upper limit (`BOOKLAB_MAX_BATCHES`). If unreadable, use the module constant.
    """
    try:
        from config import CFG
        return max(1, int(CFG.i('BOOKLAB_MAX_BATCHES') or MAX_BATCHES))
    except Exception:                                            # noqa: BLE001
        return MAX_BATCHES


def enabled() -> bool:
    """拆书功能开着吗（`BOOKLAB_ENABLED`）。读不到时**默认开着**。
        English:
    Is the book-dissection feature on (`BOOKLAB_ENABLED`). When unreadable, **defaults to on**.
    """
    try:
        from config import CFG
        return bool(CFG.b('BOOKLAB_ENABLED'))
    except Exception:                                            # noqa: BLE001
        return True


@dataclass
class Brief:
    """作者在对话框里答的那四件事。
        English:
    The four things the author answers in the dialog.
    """

    title: str = ''
    genre: str = ''
    good: str = ''
    focus: str = ''

    def filled(self) -> bool:
        return any((self.title, self.genre, self.good, self.focus))


@dataclass
class Digest:
    """拆解产物（`skillgen` 用它写 SKILL 包；界面用它作预览）。
        English:
    Dissection output (`skillgen` uses it to write the SKILL package; the UI uses it as a preview).
    """

    brief: Brief = field(default_factory=Brief)
    book: R.Book | None = None
    scan: list[dict] = field(default_factory=list)
    deep: list[dict] = field(default_factory=list)
    final: dict = field(default_factory=dict)
    #: **定量画像**（`booklab.metrics.scan`，纯本地零成本）。
    #: 它的用途是**核对面**：模型说"节奏快"，这里就有"句长中位 9 字"来对。
    # [EN] : **Quantitative profile** (`booklab.metrics.scan`, purely local and zero-cost).
    # [EN] : Its purpose is to **cross-check the surface**: the model says "fast pace", and here we have
    # [EN] "median sentence length 9 characters" to check against.
    metrics: dict = field(default_factory=dict)
    #: ★★★ 2026-10-27：**这本书是什么类型**（`booklab.kind` 的三个值之一）。
    #:   它决定整条链路走**写法线**（小说七维）还是**素材线**（专业书条目），
    #:   见 `booklab/kind.py` 模块头。★ 它**必须落进 SKILL 包** ——
    #:   否则以后查这本技能的人不知道它是按哪条线拆的（也无法判断能不能用）。
    # [EN] ★★★ 2026-10-27: **what kind of book this is** (one of the three values in
    # [EN] `booklab.kind`). It decides whether the whole chain takes the **craft line** (novel's
    # seven dimensions) or the **material line** (reference-book entries), see the header of
    # `booklab/kind.py`. ★ It **must be written into the SKILL pack** -- otherwise whoever looks up
    # this pack later cannot tell which line it was split along (nor whether it is usable).
    kind: str = 'novel'
    seconds: float = 0.0
    batches_ok: int = 0
    batches_all: int = 0
    #: 每一步照实记下来的话（没读到哪一批、哪一步没拿到结果）
    # [EN] : If every step is recorded truthfully (which batch was not read, which step did not get a
    # [EN] result)
    notes: list[str] = field(default_factory=list)

    @property
    def modules(self) -> list[dict]:
        rows = self.final.get('模块') if isinstance(self.final, dict) else None
        return [r for r in (rows or []) if isinstance(r, dict) and r.get('名称')]

    @property
    def entries(self) -> list[dict]:
        """**素材条目**（专业书那条线的产物；小说这条线为空）。

        ★ 与 `modules` 是**两码事**：`模块` 是"可复用的**写法**"，
          `条目` 是"可查证的**素材**"。同一个 `final` 里只会有一种 ——
          按 `kind` 分流时就定死了（见 `_final_one`）。

            English:
        **Material entries** (the product of the reference-book line; empty on the novel line).
            ★ Fundamentally different from `modules`: a `模块` is a reusable **craft**, an `条目` is
            a checkable **fact**. Only one of the two exists in a given `final` -- it is decided when
            `kind` branches (see `_final_one`).
        """
        rows = self.final.get('条目') if isinstance(self.final, dict) else None
        return [r for r in (rows or []) if isinstance(r, dict) and r.get('名字')]

    @property
    def is_ref(self) -> bool:
        """这本是按**素材线**拆的（专业书 / 混合）。
            English:
        Was this split along the **material line** (reference / mixed)?
        """
        return _is_ref(self.kind)

    @property
    def tags(self) -> dict[str, list[str]]:
        """受控标签（`{轴: [值]}`）。**已过词表过滤** —— 见 `theory.norm_tags`。
                English:
        Controlled tags (`{axis: [values]}`). **Already filtered through the vocabulary** -- see
        `theory.norm_tags`.
        """
        raw = self.final.get('标签') if isinstance(self.final, dict) else None
        return raw if isinstance(raw, dict) else {}

    @property
    def gate_stats(self) -> tuple[int, int]:
        """`(五门禁齐全的卡数, 总卡数)` —— 给界面与报告用的**机械计数**。

        ★ 为什么要有它：`oh-story` 那条纪律「**计数不手写**」（它的
          `novel_count`/`atom_count` 由来源闭包自动算）值得照搬 ——
          手写的计数一定会和内容对不上，而"卡片说谎"比"卡片少"坏得多。
        
                English:
        `(number of cards with all five gates present, total number of cards)` -- a **mechanical count**
        for the UI and reports.
                ★ Why it exists: the `oh-story` discipline "**counts are not handwritten**" (its
                  `novel_count`/`atom_count` are computed automatically by source closure) is worth copying --
                  handwritten counts will always mismatch the content, and "cards that lie" is far worse than "too few cards".
        """
        # ★ 2026-10-27：专业书的门禁是 `REF_GATES`（能怎么用 / 可信度 / 边界条件…），
        #   不是小说的 `GATES`（读者想看什么 / 情绪链…）。用错表 ⇒ 每条都判"缺门禁"。
        # [EN] ★ 2026-10-27: a reference book's gates are `REF_GATES` (how to use it / reliability /
        # [EN] boundary conditions...), not the novel's `GATES`. Wrong table => every entry is
        # [EN] judged "missing gates".
        if _is_ref(self.kind):
            ents = self.entries
            ok_r = sum(1 for e in ents if all(e.get(g) for g in T.REF_GATES))
            return ok_r, len(ents)
        mods = self.modules
        ok = sum(1 for m in mods if all(m.get(g) for g in T.GATES))
        return ok, len(mods)

    @property
    def counts(self) -> dict:
        """**纯数值**的结构计数（照 `oh-story` `_meta.json` 的做法）。

        ⚠ 只放数字与枚举，**不放内容** —— 它的用途是"不靠模型自评也能核一遍"。
        
                English:
        **Pure numeric** structural counts (following the approach of `oh-story` `_meta.json`).
                ⚠ Only numbers and enums, **no content** -- its purpose is "verify without relying on the model's self-assessment".
        """
        ok, total = self.gate_stats
        return {
            'kind': self.kind,
            'modules': total,
            'modules_gated': ok,
            'entries': len(self.entries),
            # ★ 有出处的条目数：**没出处的不能当素材引用**
            # [EN] ★ Entries with a source: **one without a source cannot be quoted as material**
            'entries_sourced': sum(1 for e in self.entries
                                   if str(e.get('出处') or '').strip()),
            'scan_chapters': len(self.scan),
            'deep_notes': len(self.deep),
            'batches_ok': self.batches_ok,
            'batches_all': self.batches_all,
            'chapters': (self.book.n if self.book else 0),
            'notes': len(self.notes),
            'seconds': round(self.seconds, 1),
            'tag_axes': len(self.tags),
            'tags': sum(len(v) for v in self.tags.values()),
        }

    @property
    def ok(self) -> bool:
        """拆成了吗：**有产物**才算成（其它都是中间产物）。

        ★ 2026-10-27：专业书那条线的产物是**条目**，不是模块。
          写死"有模块才算成" ⇒ 专业书拆得再好也永远判"没拆成"，
          而 `skillgen` 会因为"没拆成"拒绝落盘 ⇒ **整条素材线走不通**。

            English:
        Did it split: only **having output** counts as success (everything else is an intermediate
        product).
            ★ 2026-10-27: the reference-book line's output is **entries**, not modules. Hard-coding
            "modules or nothing" means a perfectly split reference book is always judged "not split",
            and `skillgen` refuses to write it => **the whole material line is dead**.
        """
        return bool(self.entries) if _is_ref(self.kind) else bool(self.modules)

    @property
    def coverage(self) -> str:
        """读到的覆盖率（照实说）。
                English:
        Coverage of what was read (state it as it is).
        """
        if not self.batches_all:
            return '（没扫）'
        return f'{self.batches_ok}/{self.batches_all} 批'


def _emit(on_step: Callable[[str, str], None] | None,
          key: str, extra: str = '') -> None:
    """报一步进度（界面把它变成一行小字或一条阶段消息）。

    ⚠ 回调失败**不影响拆解**，但要吞掉的同时**记日志** ——
      界面挂了不该让拆书挂掉。
    
        English:
    Report progress for one step (the UI turns it into a line of small text or a stage message).
        ⚠ Callback failure **does not affect dissection**, but while swallowing it, **log it** —
          If the UI crashes, it must not bring down book splitting.
    """
    if on_step is None:
        return
    try:
        on_step(key, extra)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('拆书进度回调失败（不影响拆解）：%r', e)


# ══════════════════════════════════════════════════════════════
#  主流程
# [EN] Main flow
# ══════════════════════════════════════════════════════════════
async def run(path: str, brief: Brief | None = None, *,
              on_step: Callable[[str, str], None] | None = None,
              max_batches: int | None = None,
              selection: Any = None,
              kind: str | None = None) -> Digest:
    """拆一本书。`path` = **文件 / 文件夹 / 网址**（用户 2026-10-10 点名三种）。

    `selection` = 只拆哪一部分（`1-10,15-21` / `前3章` / `第5章-第8章`），
    见 `booklab/selection.py`。留空 = 不筛，按分层取样读。

    `max_batches=None` 时读旋钮 `BOOKLAB_MAX_BATCHES`（默认 26）。

    `kind` = **用户指定的类型**（`novel` / `reference` / `mixed`；`None` = 自动判）。
    ★ 为什么允许指定：自动判定是**启发式**，判错的代价是"一整本废条目"
      —— 所以必须给人工一条兜回来的路（界面上就是那个下拉）。
      指定了就在 `notes` 里照实记一句"用户指定"，不假装是判出来的。

        English:
    `kind` = **the type the user chose** (`novel` / `reference` / `mixed`; `None` = judge it).
        ★ Why allow it: the automatic verdict is a **heuristic**, and being wrong costs "a whole
        book of useless entries" -- so there must be a manual way back (that dropdown in the UI).
        When it is specified, `notes` says so honestly instead of pretending it was judged.
        When `max_batches=None`, read the knob `BOOKLAB_MAX_BATCHES` (default 26).

    Split one book. `path` = **file / folder / URL** (the user named these three types on
    2026-10-10).
        `selection` = which part to split (`1-10,15-21` / `first 3 chapters` / `chapter 5-chapter 8`),
        see `booklab/selection.py`. Empty = no filtering, read by stratified sampling.
        When `max_batches=None`, read the knob `BOOKLAB_MAX_BATCHES` (default 26).
    """
    t0 = time.monotonic()
    d = Digest(brief=brief or Brief())
    if not d.brief.title:
        # 书名没填就用文件名 —— 但**不假装作者填过**（`title_from` 记在笔记里）
        # [EN] If the title is not filled in, use the filename — but **do not pretend the author filled it in**
        # [EN] (`title_from` is recorded in the notes)
        pass
    if max_batches is None:
        max_batches = _cfg_max_batches()

    # ── ① 建目录 ──
    # [EN] ── ① Create directory ──
    _emit(on_step, 'read')
    book = R.read_book(path, selection=selection, on_step=on_step)
    d.book = book
    # 读入这一步照实记下的东西（PDF 抽不出字 / 范围一个都没选上 / 网址残缺…）
    # **一条都不许丢** —— 见 `booklab/__init__` 模块头第 2 条纪律。
    # [EN] Read in what was truthfully recorded at this step (PDF cannot extract text / no range selected /
    # [EN] URL incomplete...)
    # [EN] **Not one may be lost** — see discipline item 2 in the header of the `booklab/__init__` module.
    for x in (book.notes or []):
        if x not in d.notes:
            d.notes.append(x)
    sel = getattr(book, 'selection', None)
    if sel is not None and sel.active():
        d.notes.append(t('只拆了「{x}」—— 不是整本：'
                         '{n} {u}（源里一共 {tot} {u}）',
                         x=sel.label(), n=book.n, u=book.unit_kind,
                         tot=book.total_units or book.n))
    if not d.brief.title:
        d.brief.title = book.name
    if not book.n:
        if not any('没有读到' in x for x in d.notes):
            d.notes.append(t('这本书里没有读到正文（文件是空的 / 全是二进制？）'))
        d.seconds = time.monotonic() - t0
        return d
    _emit(on_step, 'read_done', book.summary())

    # ── ①b 判类型：这是本什么书（决定后面走哪条线）──
    # ★★★ 2026-10-27：整条链路原来**只有小说一条线**（七维：节奏/人物/情绪…）。
    #   专业书没有人物、没有情绪曲线，硬套七维拆出来的是一整本空话。
    #   ⇒ 在花钱之前先判类型：小说走写法线，专业书/混合走素材线。
    #   ★ 判型的依据**照实写进 notes**（`kind.why`）—— 判错的代价是一整本废条目，
    #     必须让人能复核"它为什么这么判"，并且在界面上能改。
    # [EN] ── ①b Judge the type: what kind of book is this (decides which line follows) ──
    # [EN] ★★★ 2026-10-27: the chain used to have **only the novel line** (seven dimensions:
    # [EN] pacing / character / emotion...). A reference book has no characters and no emotional
    # [EN] curve; force-fitting the seven yields a whole book of empty talk. => Judge the type
    # [EN] **before spending money**: novels take the craft line, reference/mixed take the material
    # [EN] line. ★ The basis for the verdict is written into `notes` (`kind.why`) -- a wrong type
    # [EN] costs a whole book of useless entries, so people must be able to re-check "why it judged
    # [EN] so", and be able to change it in the UI.
    _emit(on_step, 'kind')
    sample = '\n\n'.join(c.text for c in book.chapters[:20])
    if kind in K.ALL_KINDS:
        # ★ 用户指定优先（人工兜回路），并且**照实记一句**是"用户指定"不是"判出来的"
        # [EN] ★ User's choice wins (the manual way back), and **note honestly** that it was chosen,
        # [EN] not judged
        d.kind = str(kind)
        d.notes.append(t('类型由用户指定为「{k}」（不是判出来的）', k=K.label(d.kind)))
        _emit(on_step, 'kind', K.label(d.kind))
    else:
        d.kind = K.judge(sample, genre_hint=d.brief.genre)
        _emit(on_step, 'kind', K.label(d.kind))
    # ⚠ **只在"不是小说"时记账**。小说是**默认路径**（原来就有的那条线），
    #   给它记一条"判类型：小说…"是**无端记账** —— 判据 C9 抓的就是这个
    #   （"没有意外时 notes 是空的"，否则读的人会以为出了什么问题）。
    #   专业书 / 混合才是"意外"（走了另一条线），值得一记。
    # [EN] ⚠ **Only book it when it is *not* a novel**. The novel is the **default route** (the line
    # [EN] that already existed); logging "judged type: novel..." for it is **gratuitous booking** --
    # [EN] criterion C9 catches exactly this ("notes must be empty when nothing unexpected happened",
    # [EN] otherwise the reader assumes something went wrong). Reference / mixed *are* unexpected
    # [EN] (they take the other line) and are worth recording.
    if d.kind != NOVEL:
        d.notes.append(t('判类型：{w}', w=K.why(sample)))
    if d.kind == MIXED:
        d.notes.append(t('判成「{k}」—— 既像叙事也像考据。本次按**素材线**拆'
                         '（专业书那套）；若想要写法线，把类型填成「小说」再拆一次',
                         k=K.label(d.kind)))

    # ── ② 粗扫 ──
    # ★ 2026-10-10（外部调研第 06 类建议 4）：**先跑一遍零成本的定量层**。
    #   放在 LLM 之前有两个理由：
    #     ① 它不花钱 —— 万一后面模型挂了，这一层的结果照样有用；
    #     ② 更重要的：它是**唯一不靠模型的那部分**，用来核对后面模型写的
    #        "节奏快""对话密"有没有说过头。若放到最后算，那些数字会被
    #        模型自己的结论污染（人会照着已有的说法找证据，模型也一样）。
    # [EN] ── ② Rough scan ──
    # [EN] ★ 2026-10-10 (external research category 06 recommendation 4): **first run the zero-cost
    # [EN] quantitative layer**.
    # [EN] There are two reasons for placing it before the LLM:
    # [EN] ① It costs nothing — if the model crashes later, the results of this layer are still useful;
    # [EN] ② More importantly: it is **the only part that does not rely on the model**, used to check
    # [EN] whether the later model-written
    # [EN] "fast pace" "dense dialogue" claims are overstated. If it were computed last, those numbers
    # [EN] would be
    # [EN] polluted by the model's own conclusions (people look for evidence matching an existing claim,
    # [EN] and so do models).
    _emit(on_step, 'metrics')
    try:
        from booklab import metrics as M
        d.metrics = M.scan('\n\n'.join(c.text for c in book.chapters))
    except Exception as e:                                       # noqa: BLE001
        d.metrics = {}
        _LOG.warning('定量扫描失败（不影响拆书）：%r', e)

    scan_rows = R.scan_set(book)
    groups = R.batches(scan_rows)[:max(1, int(max_batches))]
    d.batches_all = len(groups)
    _emit(on_step, 'scan', t('{n} 批').format(n=len(groups)))
    scan: list[dict] = []
    for i, rows in enumerate(groups, 1):
        got = await _scan_one(d, rows, i, len(groups), kind=d.kind)
        if got:
            scan.extend(got)
            d.batches_ok += 1
        else:
            d.notes.append(t('第 {i} 批（{a}~{b}）没读到 —— 这本书是浮着拆的')
                           .format(i=i, a=rows[0].title, b=rows[-1].title))
        _emit(on_step, 'scan_one', f'{i}/{len(groups)}')
    d.scan = scan
    if not scan:
        d.notes.append(t('粗扫一章都没读到 —— 检查模型配置，或这本书太大'))
        d.seconds = time.monotonic() - t0
        return d

    # ── ③ 精拆 ──
    # [EN] ── ③ Fine dissection ──
    deep_rows = R.pick_deep(book, scan, good=d.brief.good, kind=d.kind)
    _emit(on_step, 'deep', t('{n} 章').format(n=len(deep_rows)))
    deep = await _deep_one(d, deep_rows, kind=d.kind)
    d.deep = deep
    if not deep:
        d.notes.append(t('精读这几章没拿到笔记 —— 归纳那一步只有概览可依'))

    # ── ④ 归纳 ──
    # [EN] ── ④ Summarize ──
    _emit(on_step, 'final')
    d.final = await _final_one(d, kind=d.kind)
    if not d.final:
        d.notes.append(t('归纳这一步没拿到结果 —— 没有产出可用的写法'))

    d.seconds = time.monotonic() - t0
    _emit(on_step, 'done')
    return d


# ══════════════════════════════════════════════════════════════
#  每一步
# [EN] Every step
# ══════════════════════════════════════════════════════════════
def _is_ref(kind: str) -> bool:
    """走**素材线**（专业书 / 混合）还是**写法线**（小说）。

    ★ `MIXED` 归到素材线：它的考据成分正是用户想要的"素材"，
      而叙事成分想要的话可以在类型里选"小说"重拆一次（判错有出路）。

        English:
    Take the **material line** (reference / mixed) or the **craft line** (novel)?
        ★ `MIXED` goes to the material line: its research component is exactly the "material" the
        user wants, and if they want the craft side they can re-split with the type set to "novel"
        (there is a way out of a wrong verdict).
    """
    return str(kind) in (REFERENCE, MIXED)


async def _scan_one(d: Digest, rows: list[R.Chapter], i: int,
                    total: int, *, kind: str = NOVEL) -> list[dict]:
    """粗扫一批。返回这一批的逐章行（拿不到就空列表 —— 由调用方记账）。

    ★ 2026-10-27：专业书走 `REF_SCAN_PROMPT`（问专题 / 信息密度 / 条目名），
      小说走原来的 `SCAN_PROMPT`（问一句话 / 功能 / 情绪强度 / 钩子）。
      **外层结构同形**（都是 `{"章": [...]}`，每章一条），所以解析共用一套循环，
      只差取哪些字段。

        English:
    Coarse-scan one batch. Return this batch's per-chapter lines (empty list if unavailable -- the
    caller keeps score).
        ★ 2026-10-27: reference books use `REF_SCAN_PROMPT` (topic / information density / entry
        names), novels keep `SCAN_PROMPT` (one-liner / function / emotional intensity / hook). The
        **outer shape is the same** (both `{"章": [...]}`, one row per chapter), so parsing shares
        one loop and only the fields differ.
    """
    if _is_ref(kind):
        prompt = T.REF_SCAN_PROMPT.format(
            title=d.brief.title or '（未填）',
            genre=d.brief.genre or '（未填）',
            prefer=T.prefer_line(d.brief.good),
            lo=rows[0].title, hi=rows[-1].title,
            chapters=R.render_batch(rows),
        )
    else:
        prompt = T.SCAN_PROMPT.format(
            title=d.brief.title or '（未填）',
            genre=d.brief.genre or '（未填）',
            prefer=T.prefer_line(d.brief.good),
            lo=rows[0].title, hi=rows[-1].title,
            chapters=R.render_batch(rows),
        )
    try:
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='book_scan', want=dict, json_mode=True,
                        max_tokens=_SCAN_TOKENS, temperature=0.3, default=None)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('粗扫第 %d 批失败：%r', i, e)
        return []
    if not rep.ok or not isinstance(rep.value, dict):
        return []
    raw = rep.value.get('章') or rep.value.get('chapters') or []
    out: list[dict] = []
    if _is_ref(kind):
        # 专业书：**专题 / 密度 / 条目名**。
        #   ⚠ `密度` 是模型填的 —— 提示词里写了 ≠ 生效（实测 40~74% 不遵守）
        #     ⇒ 模型没填/填错时**用本地 `kind.density()` 补上**，不让挑章那一步抓瞎。
        # [EN] Reference book: **topic / density / entry names**. ⚠ `密度` is model-filled --
        # [EN] written in the prompt ≠ in effect (measured 40~74% non-compliance) => when the model
        # [EN] omits or mangles it, **fill it in from the local `kind.density()`**, so chapter
        # [EN] picking is not left guessing.
        by_title = {c.title: c for c in (d.book.chapters if d.book else [])}
        for r in raw:
            if not isinstance(r, dict):
                continue
            title = str(r.get('章') or '').strip()
            if not title:
                continue
            try:
                dens: float = float(r.get('密度') or 0)
            except (TypeError, ValueError):
                dens = 0.0
            if not dens:
                ch = by_title.get(title)
                if ch is not None:
                    dens = K.density(ch.text)
            items = r.get('条目')
            if isinstance(items, str):
                items = [items]
            out.append({'章': title[:40],
                        '专题': str(r.get('专题') or '').strip()[:120],
                        '密度': max(0.0, min(5.0, dens)),
                        '条目': [str(x).strip()[:30] for x in (items or [])
                                 if str(x).strip()][:6]})
        return out
    for r in raw:
        if not isinstance(r, dict):
            continue
        title = str(r.get('章') or '').strip()
        one = str(r.get('一句话') or r.get('概括') or '').strip()
        if not title or not one:
            continue
        func = r.get('功能')
        if isinstance(func, str):
            func = [func]
        try:
            emo = int(r.get('情绪') or 0)
        except (TypeError, ValueError):
            emo = 0
        out.append({'章': title[:40], '一句话': one[:120],
                    '功能': [str(x).strip() for x in (func or []) if str(x).strip()][:4],
                    '情绪': max(0, min(5, emo)),
                    '钩子': str(r.get('钩子') or '无').strip()[:8]})
    return out


async def _deep_one(d: Digest, rows: list[R.Chapter],
                    *, kind: str = NOVEL) -> list[dict]:
    """精读挑出来的几章。

    ★ 2026-10-27：专业书走 `REF_DEEP_PROMPT` + `REF_DEEP_DIMS`
      （术语 / 事实 / 规矩 / 易错），小说走原来的 `DEEP_PROMPT`。
      ⚠ 两条提示词**同形**（都是 `{title}/{genre}/{prefer}/{dims}/{chapters}`），
      这样这里不用写两套 format（改一处就漏一处的老坑）。

        English:
    Deep-read the few chapters picked out.
        ★ 2026-10-27: reference books use `REF_DEEP_PROMPT` + `REF_DEEP_DIMS`
        (terms / facts / rules / pitfalls), novels keep `DEEP_PROMPT`. ⚠ Both prompts have the
        **same shape** (all take `{title}/{genre}/{prefer}/{dims}/{chapters}`), so there is no need
        for two format calls here (the old trap of changing one and missing the other).
    """
    if not rows:
        return []
    ref = _is_ref(kind)
    prompt = (T.REF_DEEP_PROMPT if ref else T.DEEP_PROMPT).format(
        title=d.brief.title or '（未填）',
        genre=d.brief.genre or '（未填）',
        prefer=T.prefer_line(d.brief.good),
        dims=T.dims_text(T.REF_DEEP_DIMS if ref else T.DEEP_DIMS),
        chapters=R.render_deep(rows),
    )
    try:
        rep = await ask('daily', [{'role': 'user', 'content': prompt}],
                        purpose='book_deep', want=dict, json_mode=True,
                        max_tokens=_DEEP_TOKENS, temperature=0.4, default=None)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('精读失败：%r', e)
        return []
    if not rep.ok or not isinstance(rep.value, dict):
        return []
    raw = rep.value.get('拆解') or raw_rows(rep.value)
    out: list[dict] = []
    if _is_ref(kind):
        # 专业书条目：**出处必填**（溯源是这个功能的命根子 —— 见 `digest.json` 的 `deep`）
        # [EN] Reference-book entries: **出处 is mandatory** (traceability is this feature's
        # [EN] lifeline -- see `deep` in `digest.json`)
        for r in (raw or []):
            if not isinstance(r, dict):
                continue
            body = str(r.get('内容') or '').strip()
            if not body:
                continue
            out.append({
                '维度': str(r.get('维度') or '').strip()[:20],
                '名字': str(r.get('名字') or '').strip()[:30],
                '内容': body[:400],
                '出处': str(r.get('出处') or '').strip()[:60],
                '为什么值得记': str(r.get('为什么值得记') or '').strip()[:300],
            })
        return out[:12]
    for r in (raw or []):
        if not isinstance(r, dict):
            continue
        how = str(r.get('怎么写的') or '').strip()
        if not how:
            continue
        out.append({
            '维度': str(r.get('维度') or '').strip()[:20],
            '出处': str(r.get('出处') or '').strip()[:40],
            '怎么写的': how[:400],
            '为什么有效': str(r.get('为什么有效') or '').strip()[:300],
            '怎么用': str(r.get('怎么用') or '').strip()[:300],
        })
    return out[:8]


def raw_rows(v: dict) -> list:
    """兜底：模型偶尔把数组放在别的键下（`拆解点` / `points`…）。
        English:
    Fallback: the model occasionally puts the array under another key (`拆解点` / `points`...).
    """
    for k in ('拆解点', '要点', 'points', 'findings'):
        x = v.get(k)
        if isinstance(x, list):
            return x
    return []


async def _final_one(d: Digest, *, kind: str = NOVEL) -> dict:
    """归纳成可复用的模块（专业书则归纳成**素材条目**）。

    ★ 2026-10-27：专业书走 `REF_FINAL_PROMPT`，产出的是**条目**
      （名字 / 类别 / 内容 / 出处 / 五门禁），不是"写法模块"。
      ⚠ 两条线的**门禁不同**：小说是 `GATES`（读者想看什么 / 情绪链 / 戏剧单元…），
      专业书是 `REF_GATES`（能怎么用 / 可信度 / 边界条件 / 可替换项 / 不可照搬）
      —— 专业书问"情绪链"是没意义的。

        English:
    Summarize into reusable modules (for a reference book: into **material entries**).
        ★ 2026-10-27: reference books use `REF_FINAL_PROMPT` and produce **entries**
        (name / category / content / source / five gates), not "craft modules".
        ⚠ The two lines have **different gates**: novels use `GATES` (what the reader wants /
        emotional chain / dramatic unit...), reference books use `REF_GATES` (how to use it /
        reliability / boundary conditions / swappable / not transferable) -- asking a reference
        book for an "emotional chain" is meaningless.
    """
    ref = _is_ref(kind)
    deep_txt = '（没有精读笔记）'
    if d.deep:
        if ref:
            deep_txt = '\n\n'.join(
                f"- 【{r.get('维度') or '?'}·{r.get('出处') or '?'}"
                f"】{r.get('名字') or ''}：{r.get('内容')}"
                f"\n  为什么值得记：{r.get('为什么值得记')}"
                for r in d.deep)
        else:
            deep_txt = '\n\n'.join(
                f"- 【{r.get('维度') or '?'}·{r.get('出处') or '?'}】{r.get('怎么写的')}"
                f"\n  为什么有效：{r.get('为什么有效')}\n  怎么用：{r.get('怎么用')}"
                for r in d.deep)
    common = dict(
        title=d.brief.title or '（未填）',
        genre=d.brief.genre or '（未填）',
        good=d.brief.good or '（没说）',
        prefer=(T.prefer_line(d.brief.good) + '\n' + T.focus_line(d.brief.focus)).strip(),
        scan=R.outline_text(d.book, d.scan) if d.book else '（没有概览）',
        deep=deep_txt,
    )
    if ref:
        prompt = T.REF_FINAL_PROMPT.format(
            **common,
            min_entries=T.REF_MIN_ENTRIES, max_entries=T.REF_MIN_ENTRIES * 4,
        )
    else:
        prompt = T.FINAL_PROMPT.format(
            **common,
            # ★ 受控标签词表注入（值只能从这里选，写入侧与查询侧共用一张表）
            # [EN] ★ Controlled tag vocabulary injection (values can only be chosen from here; the write side and
            # [EN] the query side share one table)
            tags=T.tags_text(),
        )
    try:
        rep = await ask('front', [{'role': 'user', 'content': prompt}],
                        purpose='book_final', want=dict, json_mode=True,
                        max_tokens=_FINAL_TOKENS, temperature=0.4, default=None)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('归纳失败：%r', e)
        return {}
    if not rep.ok or not isinstance(rep.value, dict):
        return {}
    v = rep.value
    if _is_ref(kind):
        # ── 专业书：素材条目（**出处必填**，五门禁是 `REF_GATES`）──
        # [EN] ── Reference book: material entries (**出处 mandatory**, gates are `REF_GATES`) ──
        entries: list[dict] = []
        _no_src: list[str] = []
        _gate_missing_ref: list[str] = []
        for r in (v.get('条目') or v.get('entries') or []):
            if not isinstance(r, dict):
                continue
            nm = str(r.get('名字') or '').strip()
            body = str(r.get('内容') or '').strip()
            if not (nm and body):
                continue
            row = {
                '名字': nm[:30],
                '类别': str(r.get('类别') or '').strip()[:6],
                '内容': body[:400],
                '出处': str(r.get('出处') or '').strip()[:60],
                '这本书的例子': str(r.get('这本书的例子') or '').strip()[:200],
            }
            for g in T.REF_GATES:
                row[g] = str(r.get(g) or '').strip()[:240]
            if not row['出处']:
                _no_src.append(nm)
            miss = [g for g in T.REF_GATES if not row.get(g)]
            if miss:
                _gate_missing_ref.append(f'「{nm}」缺 {"/".join(miss)}')
            entries.append(row)
        # ★ 出处是这条线的命根子：没出处的条目**不能算素材**（没法复核 = 不能引用）
        # [EN] ★ Source is this line's lifeline: an entry without one **is not material**
        # [EN] (unverifiable = unquotable)
        if _no_src:
            d.notes.append('这些条目没写出处，已照收但**不能当素材引用**：'
                           + '、'.join(_no_src[:4]))
        if _gate_missing_ref:
            d.notes.append('这些条目缺门禁字段（照收，但跨书复用会打折）：'
                           + '；'.join(_gate_missing_ref[:4]))
        if not entries:
            d.notes.append('归纳没有产出条目 —— 这本书可能不适合当素材拆'
                           '（或类型判错了，可在界面上改成「小说」重拆）')
        bad_r = v.get('不适合')
        if isinstance(bad_r, str):
            bad_r = [bad_r]
        return {
            '条目': entries[:24],
            '这本书的用法': str(v.get('这本书的用法') or '').strip()[:400],
            '不适合': [str(x).strip()[:160] for x in (bad_r or [])
                       if str(x).strip()][:4],
        }
    mods: list[dict] = []
    # ★ 2026-10-10：模块卡升级为 **EM 五门禁卡**（见 `theory.GATES` 的来历）。
    #   门禁缺项**不许静默通过** —— 本项目那条纪律在这里的落地方式是：
    #   卡照样收（信息不浪费），但把"哪几条缺门禁"照实写进 `d.notes`，
    #   由作者看见。这比"直接丢掉这张卡"好：丢掉会让作者以为模型没拆出来。
    # [EN] ★ 2026-10-10: the module card was upgraded to the **EM five-gate card** (see the origin in
    # [EN] `theory.GATES`).
    # [EN] Missing gate items **must not silently pass** — the way this project's discipline is implemented
    # [EN] here is:
    # [EN] the card is still accepted (information is not wasted), but "which gate items are missing" is
    # [EN] truthfully written into `d.notes`,
    # [EN] for the author to see. This is better than "just discarding this card": discarding would make
    # [EN] the author think the model did not dissect it out.
    _gate_missing: list[str] = []
    for r in (v.get('模块') or v.get('modules') or []):
        if not isinstance(r, dict):
            continue
        nm = str(r.get('名称') or '').strip()
        how = str(r.get('怎么做') or '').strip()
        if not (nm and how):
            continue
        row = {
            '名称': nm[:20], '怎么做': how[:400],
            '什么时候用': str(r.get('什么时候用') or '').strip()[:200],
            '为什么管用': str(r.get('为什么管用') or '').strip()[:200],
            '这本书的例子': str(r.get('这本书的例子') or '').strip()[:200],
        }
        # ── 门禁五条 ──
        # [EN] ── Five gates ──
        for g in T.GATES:
            val = r.get(g)
            if g == '可替换项':
                if isinstance(val, str):
                    val = [val]
                row[g] = [str(x).strip()[:120] for x in (val or []) if str(x).strip()][:4]
            elif g == '不可照搬':
                if isinstance(val, str):
                    val = [val]
                row[g] = [str(x).strip()[:120] for x in (val or []) if str(x).strip()][:4]
            else:
                row[g] = str(val or '').strip()[:240]
        miss = [g for g in T.GATES if not row.get(g)]
        if miss:
            _gate_missing.append(f'「{nm}」缺 {"/".join(miss)}')
        mods.append(row)
    if _gate_missing:
        d.notes.append('这些模块卡少了门禁字段（信息照收，但跨书复用会打折）：'
                       + '；'.join(_gate_missing[:4]))
    bad = v.get('不适合')
    if isinstance(bad, str):
        bad = [bad]
    # ── 受控标签（不在词表里的值会被丢掉，并照实记）──
    # [EN] ── Controlled tags (values not in the vocabulary are dropped, and truthfully recorded) ──
    tags = T.norm_tags(v.get('标签'))
    _raw_tags = v.get('标签') if isinstance(v.get('标签'), dict) else {}
    _dropped: list[str] = []
    for axis, vals in _raw_tags.items():
        allowed = T.TAG_VALUES.get(str(axis or '').strip())
        if allowed is None:
            _dropped.append(str(axis))
            continue
        for x in ([vals] if isinstance(vals, str) else (vals or [])):
            s = str(x or '').strip()
            if s and s not in allowed:
                _dropped.append(f'{axis}={s}')
    if _dropped:
        d.notes.append('这些标签不在受控词表里，已丢弃（要用就把它加进 '
                       '`skills/book-dismantle/标签词表.md` 与 `theory.TAG_VALUES`）：'
                       + '、'.join(dict.fromkeys(_dropped))[:120])
    return {
        '模块': mods[:6],
        '节奏': str(v.get('节奏') or '').strip()[:500],
        '人设': str(v.get('人设') or '').strip()[:500],
        '语言': str(v.get('语言') or '').strip()[:500],
        '不适合': [str(x).strip()[:160] for x in (bad or []) if str(x).strip()][:4],
        '适用': str(v.get('适用') or '').strip()[:200],
        '标签': tags,
    }


# ══════════════════════════════════════════════════════════════
#  预览（对话框里给作者看的那一页）
# [EN] Preview (the page shown to the author in the dialog)
# ══════════════════════════════════════════════════════════════
def preview_md(d: Digest) -> str:
    """拆解结果的可读版（落盘也用这一份）。
        English:
    Readable version of the split result (also the copy written to disk).
    """
    b = d.brief
    lines = [f'# 拆书 · {b.title or "（未命名）"}', '']
    if b.genre:
        lines.append(f'**类型**：{b.genre}')
    if b.good:
        lines.append(f'**作者说它好在**：{b.good}')
    if b.focus:
        lines.append(f'**重点拆**：{b.focus}')
    if d.book is not None:
        from_what = {'file': '文件', 'dir': '文件夹', 'url': '网址'}.get(
            d.book.source_kind, '文件')
        lines.append(f'**读了**（{from_what}）：{d.book.summary()}'
                     f'（粗扫 {d.coverage}，精读 {len(d.deep)} 条笔记）')
        sel = getattr(d.book, 'selection', None)
        if sel is not None and sel.active():
            # ★ 这一行是**必须的**：报告必须能自证"我拆的是哪一部分" ——
            #   不然以后回头看这份拆解，分不清"这本书就这么点"还是"只拆了一截"。
            # [EN] ★ This line is **required**: the report must be able to prove "which part I dissected" —
            # [EN] otherwise, looking back at this dissection later, one cannot tell whether "this book is just
            # [EN] this much" or "only a segment was dissected".
            lines.append(f'**只拆了这一部分**：{sel.describe(d.book.n, d.book.unit_kind)}'
                         f'（源里一共 {d.book.total_units} {d.book.unit_kind}）')
        if d.book.notes:
            lines.append(f'**读入说明**：{"；".join(str(x) for x in d.book.notes)}')
    lines.append(f'**用时**：{d.seconds:.0f}s')
    lines += ['', '---', '', '## 能拿走的写法', '']
    if not d.modules:
        lines.append('> 这一轮没归纳出可用的写法（见下面的说明）。')
    for i, m in enumerate(d.modules, 1):
        lines.append(f'### {i}. {m["名称"]}')
        # 门禁字段（跨书复用靠它们）——报告里也照写，别只在 SKILL 里有
        # [EN] Gate fields (cross-book reuse depends on them) — also write them in the report as-is, do not
        # [EN] only have them in SKILL
        for key, label in (('读者想看什么', '读者想看什么'),
                           ('情绪链', '情绪链'),
                           ('戏剧单元', '戏剧单元（去掉素材后的结构）')):
            if m.get(key):
                lines.append(f'- **{label}**：{m[key]}')
        if m.get('可替换项'):
            lines.append('- **可替换项**（这些位置可以整体换掉）：'
                         + '；'.join(str(x) for x in m['可替换项']))
        if m.get('不可照搬'):
            lines.append('- **不可照搬**（跟着搬会出事）：'
                         + '；'.join(str(x) for x in m['不可照搬']))
        lines.append(f'- **怎么做**：{m["怎么做"]}')
        if m.get('什么时候用'):
            lines.append(f'- **什么时候用**：{m["什么时候用"]}')
        if m.get('为什么管用'):
            lines.append(f'- **为什么管用**：{m["为什么管用"]}')
        if m.get('这本书的例子'):
            lines.append(f'- **这本书的例子**：{m["这本书的例子"]}')
        lines.append('')
    f = d.final or {}
    for key, label in (('节奏', '节奏'), ('人设', '人设'), ('语言', '语言')):
        if f.get(key):
            lines += [f'## {label}', '', f[key], '']
    if f.get('不适合'):
        lines += ['## 换本书就不能用的', '']
        lines += [f'- {x}' for x in f['不适合']]
        lines.append('')
    if f.get('适用'):
        lines += ['## 适合谁参考', '', f['适用'], '']
    # ★ 定量画像放在**模型结论之后**：它的用途是核对面（"模型说节奏快，
    #   这里句长中位 9 字"），放在前面会让人先信数字再读结论，反而少了对照。
    # [EN] ★ Place the quantitative profile **after the model conclusions**: its purpose is to cross-check
    # [EN] the surface ("the model says fast pace,
    # [EN] here the median sentence length is 9 characters"); placing it earlier would make people believe
    # [EN] the numbers before reading the conclusions, which reduces the contrast.
    try:
        from booklab import metrics as M
        blk = M.render_block(d.metrics)
        if blk:
            lines += ['---', '', blk]
    except Exception:                                            # noqa: BLE001
        pass
    if d.notes:
        lines += ['---', '', '## 这一步的说明（照实记）', '']
        lines += [f'- {x}' for x in d.notes]
        lines.append('')
    return '\n'.join(lines)
