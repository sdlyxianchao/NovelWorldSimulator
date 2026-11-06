# -*- coding: utf-8 -*-

"""**选择范围**：只拆你想拆的那一部分。

用户 2026-10-10 的原话：
「另外根据我学的理论 **拆书不需要全拆** 最后支持拆哪些页（按照 1-10,15-21 这样输入，
或者**前多少页**，或者**哪些章节**）」。

为什么要有这一层（而不是让用户自己把文件切好）
--------------------------------------------
拆书本身就是"读那些该读的"，而"该读哪儿"最懂的是**作者**：
他可能只想学某一卷的写法、只想看前三章的钩子。让他去手工切文件，
等于把"我知道我要什么"这条信息丢掉了。

支持的写法（**都在这一个输入框里**）
----------------------------------
```text
留空            全部（照旧按分层取样读）
1-10,15-21      第 1~10 与第 15~21 个单位
3               只第 3 个
5-             从第 5 个到结尾
前10 / 前10页 / 前3章   最前面这一段
第3章-第8章      按章
第2章           按章
「井底」         按标题里含这几个字挑（书名号/引号里的话当标题关键词）
全部 / 全        不限制（等于留空）
```

两种单位：**页**（PDF 这种分页的）与**章**（有章节标题的）。
用户写「页」就按页，写「章」就按章，什么都不写（`1-10` 这种）**按源自己的单位**。

三条纪律
--------
1. **解析不了就说解析不了**，并且**不许悄悄当成"全部"** ——
   用户以为只拆了 10 页、实际拆了一整本，是"看起来成功"的那种坏。
2. 范围**越界不算错**：写了 `1-9999` 而这本书只有 30 章，就取到 30 为止
   （照实报"实际拆了 30"）。
3. 单位与源对不上时（比如对一份 txt 写"前 10 页"）**照实说明**：
   "这份文本没有页，按**章**取前 10" —— 而不是拒绝执行。

English:
**Selection scope**: only split the part you want to split.
User's original words on 2026-10-10:
"Also, based on the theory I learned, **splitting a book doesn't require splitting the whole
thing**; ultimately support splitting which pages (entered like 1-10,15-21,
or **the first how many pages**, or **which chapters**)."
Why this layer exists (instead of letting the user cut the file themselves)
--------------------------------------------
Splitting a book is itself "reading the parts that should be read", and the one who best knows
"which parts should be read" is the **author**:
They may only want to learn the writing style of a certain volume, or only want to see the hooks
of the first three chapters. Making them cut the file by hand
is equivalent to throwing away the information "I know what I want".
Supported syntax (**all in this one input box**)
----------------------------------
```text
Leave blank            all (read as before via stratified sampling)
1-10,15-21      units 1~10 and 15~21
3               only the 3rd
5-              from the 5th to the end
第2章           by chapter
「井底」 pick by titles containing these characters (text inside book-title marks/quotes is treated
as title keywords)
全部 / 全        no limit (same as leaving blank)
```
Two units: **page** (for paginated ones like PDF) and **chapter** (for those with chapter
titles).
If the user writes 「页」, go by page; if 「章」, go by chapter; if nothing (`1-10`), **use the
source's own unit**.
Three disciplines
--------
1. **If it can't be parsed, say so**, and **must not quietly treat it as "all"** ——
   the user thinks only 10 pages were split, but actually the whole book was, which is the bad kind of "looks successful".
2. An **out-of-range range is not an error**: if `1-9999` is written but the book only has 30 chapters, take up to 30
   (reporting truthfully "actually split 30").
3. When the unit doesn't match the source (e.g. writing "first 10 pages" for a txt) **explain truthfully**:
   "this text has no pages, taking the first 10 by **chapter**" —— rather than refusing to execute.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from util.chapters import cn_to_int

#: 「到最后」用的哨兵（比任何真实章号都大）
# [EN] : The sentinel for "to the end" (larger than any real chapter number)
INF = 10 ** 9
#: 单个条目最多允许的号码（防呆：`999999999` 这种一眼是手滑）
# [EN] : The maximum number allowed for a single entry (sanity check: something like `999999999` is
# [EN] obviously a typo)
MAX_INDEX = 100_000

#: 全角 → 半角（用户从别处粘过来的范围常常是全角标点）
# [EN] : Full-width → half-width (ranges users paste from elsewhere often use full-width punctuation)
_FULL2HALF = str.maketrans({
    '，': ',', '、': ',', '；': ';', '　': ' ',
    '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
    '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
    '～': '~', '—': '-', '－': '-', '‑': '-', '–': '-',
})
#: 拆条目
# [EN] : Split entries
_SPLIT_RE = re.compile(r'[,;/\s]+')
#: `A-B` / `A-` / `A`
_RANGE_RE = re.compile(r'^(\d{1,6})\s*[~\-]\s*(\d{1,6})?$')
_SINGLE_RE = re.compile(r'^\d{1,6}$')
#: 「前 N」/「最后 N」
# [EN] : "first N" / "last N"
_HEAD_RE = re.compile(r'^(?:前|头)\s*(\d{1,6})')
_TAIL_RE = re.compile(r'^(?:最后|后)\s*(\d{1,6})')
#: 去掉「第 … 」与单位后缀
# [EN] : Strip the "第 … " prefix and the unit suffix
_UNIT_WORDS = ('页', '章节', '章', '回', '节', '卷', '篇', 'part', 'chapter')
#: 明确写"全部"的几种写法
# [EN] : The several ways of explicitly writing "all"
_ALL_WORDS = frozenset({'全部', '全', '所有', '整本', 'all', '*'})
#: 引号里的东西当**标题关键词**（用户想说"只拆'井底'那一章"）
# [EN] : Treat what's inside quotes as a **title keyword** (the user might mean "only split the '井底'
# [EN] chapter")
_QUOTED_RE = re.compile(r'[「『“"\']([^」』”"\']{1,30})[」』”"\']')

#: 中文数字（"第一章" 比 "第1章" 更常写）
# [EN] : Chinese numerals ("第一章" is written more often than "第1章")
_CN_DIGITS = {'零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
              '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
_CN_UNITS = {'十': 10, '百': 100, '千': 1000}


def cn2int(s: str) -> int:
    """中文数字 → 整数；**含非数字字就返回 0**（这样"井底"不会被当数字）。

    支持到千位：`十`→10、`十一`→11、`二十三`→23、`一百零八`→108、`三百六十五`→365。

    ★ 2026-10-27：实现搬去 `util/chapters.py::cn_to_int`（**全项目唯一一份**）。
      原来这里与 `ingest/progress.py::_cn_to_int` 各写一套，而**两套在"两三"上答案不一样**
      （这里 3、那里 None）—— 现在统一成"非法"（本函数对外仍返回 0，契约不变）。

        English:
    ★ 2026-10-27: the implementation moved to `util/chapters.py::cn_to_int` (the single copy).
      This file and `ingest/progress.py::_cn_to_int` each had their own parser, and **the two
      disagreed on "两三"** (3 vs None) -- they now agree on "invalid" (this function still returns
      0 to the outside; the contract is unchanged).
    """
    n = cn_to_int(s)
    return n if n is not None else 0


def _as_num(s: str) -> int:
    """一段文字 → 号码（不合法返回 0）。
        English:
    A piece of text → number (return 0 if invalid).
    """
    t = str(s or '').strip().translate(_FULL2HALF).strip()
    if not t:
        return 0
    if t.isdigit():
        n = int(t)
        return n if 1 <= n <= MAX_INDEX else 0
    n = cn2int(t)
    return n if 1 <= n <= MAX_INDEX else 0


def _clean(tok: str) -> tuple[str, str]:
    """反复剥掉「第」与单位后缀 → `(剩下的, 说到的单位或空串)`。

    ★ 为什么是"反复"而不是"各剥一次"：`第5章-第8章` 里**两头都有**「第…章」，
      各剥一次的话左边只会剥掉「章」、剩下 `第5`，再跟「第8」拼成
      `第5-第8` —— 于是整串被当成**标题关键词**，一个都选不上，
      而报告会说是"没选上"（看起来像范围写错，其实是解析错了）。
    
        English:
    Repeatedly strip off "第" and unit suffixes → `(remainder, mentioned unit or empty string)`.
          if stripped once each, the left side would only lose "章", leaving `第5`, then combine with "第8" to form
          `第5-第8` —— so the whole string is treated as a **title keyword**, none get selected,
          and the report will say "nothing selected" (looks like a miswritten range, but actually a parse error).
    """
    t = str(tok or '').strip()
    unit = ''
    for _ in range(5):
        before = t
        for w in sorted(_UNIT_WORDS, key=len, reverse=True):
            if len(t) > len(w) and t.lower().endswith(w):
                unit = unit or ('页' if w == '页' else '章')
                t = t[: -len(w)].strip()
        if t.startswith('第') and len(t) > 1:
            t = t[1:].strip()
        if t == before:
            break
    return t, unit


def _split_range(tok: str) -> tuple[tuple[str, str], tuple[str, str]] | None:
    """`第5章-第8章` → `((5, 章), (8, 章))`；没有分隔符返回 `None`。

    两边**各自**剥「第」与单位 —— 因为两头通常都带着（`第5章-第8章`）。
    
        English:
        Strip "第" and unit **on each side separately** —— because both ends usually carry them (`第5章-第8章`).
    """
    for sep in ('~', '-'):
        if sep in str(tok or ''):
            a, _s, b = str(tok).partition(sep)
            return _clean(a), _clean(b)
    return None


def parse(spec: str) -> Selection:
    """解析范围说明。**解析不了就带 `err` 返回**（不抛、更不许当全部）。
        English:
    Range parsing note. **If it can't be parsed, return with `err`** (don't throw, and certainly
    don't treat as all).
    """
    raw = str(spec or '').strip()
    if not raw:
        return Selection(raw='')
    nt = raw.translate(_FULL2HALF).strip()
    if nt in _ALL_WORDS:
        return Selection(raw=raw)

    head = tail = 0
    ranges: list[tuple[int, int]] = []
    names: list[str] = []
    kind = 'auto'
    bad: list[str] = []

    # 先把引号里的当**标题关键词**取出来（它们可能含空格/逗号）
    # [EN] First extract what's inside the quotes as **title keywords** (they may contain spaces/commas)
    for m in _QUOTED_RE.finditer(nt):
        names.append(m.group(1).strip())
    body = _QUOTED_RE.sub(' ', nt)

    for tok in _SPLIT_RE.split(body):
        t = tok.strip()
        if not t:
            continue
        m = _HEAD_RE.match(t)
        if m:
            n = _as_num(m.group(1))
            if n:
                head = max(head, n)
            else:
                bad.append(t)
            kind = _kind_of(t, kind)
            continue
        m = _TAIL_RE.match(t)
        if m:
            n = _as_num(m.group(1))
            if n:
                tail = max(tail, n)
            else:
                bad.append(t)
            kind = _kind_of(t, kind)
            continue

        core, unit = _clean(t)
        if unit and kind == 'auto':
            kind = unit

        # ★ 先按分隔符**切开再各剥一次单位**，而不是整串剥。
        #   整串剥的话 `第5章-第8章` 会剥成 `5章-第8`（右边那个「第」剥不掉），
        #   于是被当成**标题关键词**，一个都选不上（见 `_clean` 的说明）。
        # [EN] ★ First **split by the delimiter, then strip the unit from each part**, instead of stripping the
        # [EN] whole string.
        # [EN] If you strip the whole string, `第5章-第8章` becomes `5章-第8` (the `第` on the right can't be
        # [EN] stripped),
        # [EN] and then it's treated as a **title keyword**, so nothing gets selected (see the explanation in
        # [EN] `_clean`).
        rng = _split_range(t)
        if rng is not None:
            (a, ua), (b, ub) = rng
            if kind == 'auto':
                kind = ua or ub or kind
            lo = _as_num(a)
            has_hi = bool(str(b).strip())
            hi = _as_num(b) if has_hi else 0
            if lo and has_hi and hi and hi < lo:
                bad.append(t)                    # `10-3` 这种倒着的
                # [EN] Reversed ones like `10-3`
            elif lo and (not has_hi or hi):
                ranges.append((lo, hi or INF))
            else:
                bad.append(t)
            continue

        n = _as_num(core)
        if n:
            ranges.append((n, n))
            continue
        # 剩下的当**标题关键词**（用户可能直接写"井底"或"井底之蛙"）
        # [EN] The rest are treated as **title keywords** (the user may write "井底" or "井底之蛙" directly)
        cleaned = re.sub(r'[的个那这几章回节卷页里]+$', '', t).strip()
        if cleaned:
            names.append(cleaned)

    if bad:
        return Selection(
            raw=raw, kind=kind, head=head, tail=tail,
            ranges=tuple(ranges), names=tuple(names),
            err=f'这部分看不懂：「{"、".join(bad[:3])}」——'
                f'范围请写成 `1-10,15-21`、`前3章`、`第5章-第8章` 或者 `全部`')
    sel = Selection(raw=raw, kind=kind, head=head, tail=tail,
                    ranges=tuple(dict.fromkeys(ranges)),
                    names=tuple(dict.fromkeys(names)))
    if not sel.active():
        return replace(sel, err=f'「{raw}」里没读出任何范围 —— 想全拆就留空')
    return sel


def _kind_of(tok: str, kind: str) -> str:
    """从这一条里读出用户说的单位（说了就盖过默认）。
        English:
    Read the unit the user mentioned from this entry (if mentioned, it overrides the default).
    """
    if kind != 'auto':
        return kind
    if '章' in tok or '回' in tok or '节' in tok or '卷' in tok:
        return '章'
    if '页' in tok:
        return '页'
    return kind


@dataclass(frozen=True)
class Selection:
    """一次"只拆这一部分"的说明。
        English:
    A note for "only split this part" once.
    """

    raw: str = ''
    #: `auto`（按源自己的单位）/ `页` / `章`
    # [EN] : `auto` (use the source's own unit) / `页` / `章`
    kind: str = 'auto'
    #: 取最前面的 N 个（0 = 不限）
    # [EN] : take the first N (0 = unlimited)
    head: int = 0
    #: 取最后面的 N 个（0 = 不限）
    # [EN] : take the last N (0 = unlimited)
    tail: int = 0
    #: 1 起、闭区间的段
    # [EN] : 1-based, inclusive range
    ranges: tuple[tuple[int, int], ...] = ()
    #: 按**标题**挑（含这几个字就算）
    # [EN] : pick by **title** (counts if it contains these characters)
    names: tuple[str, ...] = ()
    #: 非空 = 没解析成功（GUI 要把这句话显示出来，**不许静默当全部**）
    # [EN] : non-empty = parsing failed (the GUI must display this message, **must not silently treat as
    # [EN] all**)
    err: str = ''

    # ── 状态 ──
    # [EN] ── State ──
    @property
    def ok(self) -> bool:
        return not self.err

    def active(self) -> bool:
        """要不要真的筛（`head/tail/ranges/names` 一个都没有 = 不筛）。
                English:
        Whether to actually filter (none of `head/tail/ranges/names` present = no filter).
        """
        return bool(self.ok and (self.head or self.tail
                                 or self.ranges or self.names))

    def wanted_kind(self) -> str:
        """用户明确说的单位（`auto` = 没说）。
                English:
        The unit the user explicitly stated (`auto` = not stated).
        """
        return self.kind if self.kind in ('页', '章') else 'auto'

    # ── 给人看的话 ──
    # [EN] ── Human-readable message ──
    def label(self) -> str:
        """把范围说回成人话（界面与报告都用它）。
                English:
        Express the range back in plain language (used by both UI and report).
        """
        if self.err:
            return self.err
        if not self.active():
            return '全部'
        bits: list[str] = []
        if self.head:
            bits.append(f'前 {self.head}')
        if self.tail:
            bits.append(f'最后 {self.tail}')
        for lo, hi in self.ranges:
            if hi >= INF:
                bits.append(f'{lo} 起')
            elif hi == lo:
                bits.append(f'第 {lo}')
            else:
                bits.append(f'{lo}-{hi}')
        for n in self.names:
            bits.append(f'含「{n}」')
        unit = '' if self.wanted_kind() == 'auto' else self.wanted_kind()
        return '、'.join(bits) + (f' {unit}' if unit else '')

    def describe(self, total: int, unit: str = '章') -> str:
        """「实际拆了哪几个」——**按真实单位报**（越界时总数会小于请求）。
                English:
        "Which ones were actually split" —— **report by real units** (when out-of-bounds the total will
        be less than requested).
        """
        if not self.active():
            return f'全部 {total} {unit}'
        return f'{self.label()} → 实际 {total} {unit}'

    def as_dict(self) -> dict:
        return {'原始': self.raw, '单位': self.kind, '前几': self.head,
                '后几': self.tail, '段': [list(r) for r in self.ranges],
                '标题关键词': list(self.names), '说明': self.label()}


def pick_indices(sel: Selection, n: int) -> list[int]:
    """`n` 个单位里该留哪些（0 起下标，**按原顺序**）。

    ★ 越界**不算错**：`1-9999` 而只有 30 个 → 就是 30 个（照实）。
    
        English:
    Which of the `n` units to keep (0-based index, **in original order**).
        ★ Out-of-bounds **is not an error**: `1-9999` but only 30 exist → just 30 (report as-is).
    """
    if n <= 0:
        return []
    if not sel.active():
        return list(range(n))
    # ★ 只写了**标题关键词**时，基数必须是"全部"，否则 `keep` 会是空的
    #   （第一版就是这么错的：names 单独用 → 一个都不留 → 空书 → 报告说
    #    "这本书里没有读到正文"，把"筛错了"说成"书是空的"）。
    # [EN] ★ When only **title keywords** are given, the base must be "all", otherwise `keep` will be empty
    # [EN] (The first version got this wrong: names used alone → nothing is kept → empty book → the report
    # [EN] says
    # [EN] "no body text was read from this book", turning "filtered wrong" into "the book is empty").
    if not (sel.head or sel.tail or sel.ranges):
        return list(range(n))
    keep: set[int] = set()
    if sel.head:
        keep.update(range(min(n, sel.head)))
    if sel.tail:
        keep.update(range(max(0, n - sel.tail), n))
    for lo, hi in sel.ranges:
        for i in range(lo, min(hi, MAX_INDEX) + 1):
            if i > n:
                break
            keep.add(i - 1)
    out = sorted(keep)
    if sel.names:
        return out          # 名字那一道由 `pick_by_name` 做（它要知道标题）
        # [EN] The name pass is done by `pick_by_name` (it needs to know the titles)
    return out


def pick_by_name(sel: Selection, titles: list[str],
                 base: list[int] | None = None) -> list[int]:
    """再按标题关键词筛一道。`base=None` 表示"没别的条件"。

    命中判定：标题里**含有**那串字（不分大小写）。中文不分词 ——
    用户写「井底」而章节叫「第二章 井底之蛙」时，包含关系就够了。
    
        English:
    Then filter once more by title keyword. `base=None` means "no other condition".
        Match test: the title **contains** that string of characters (case-insensitive). Chinese is not tokenized ——
    """
    if not sel.names:
        return list(range(len(titles))) if base is None else base
    idx = list(range(len(titles))) if base is None else list(base)
    kws = [k.lower() for k in sel.names if k.strip()]
    if not kws:
        return idx
    out = [i for i in idx
           if any(k in str(titles[i] or '').lower() for k in kws)]
    return out


def apply(sel: Selection, titles: list[str]) -> list[int]:
    """一步到位：给标题列表，返回该留哪些下标。
        English:
    One step: given the title list, return which indices to keep.
    """
    base = pick_indices(sel, len(titles))
    if not sel.names:
        return base
    # 只写标题关键词时 `base` 是"全部"，那就是按名字筛；两者都有就是**取交集**
    # [EN] When only title keywords are given, `base` is "all", so it filters by name; when both are
    # [EN] present, it's the **intersection**
    named = set(pick_by_name(sel, titles, None))
    return [i for i in base if i in named]


#: 空选择（判据与默认参数用）
# [EN] : empty selection (used by the predicate and default arguments)
NONE = Selection()
