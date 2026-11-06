# -*- coding: utf-8 -*-
"""章节标题识别 —— **全项目唯一的实现**（2026-10-27 抽出）。

★★★ 为什么抽成模块（而不是各写各的）
「什么算一个章节标题」这件事本来有**三份**实现：

  · `ingest/progress.py::_CHAPTER_RE`   —— 开卷时拆正文（喂前情对齐）
  · `booklab/reader.py::_CHAPTER_RE`    —— 读整本书（拆书 / 取样）
  · `developers/mutate_ingest_scan.py`  —— 反例法的刀（指着第一份）

而 `booklab/reader.py` 的注释白纸黑字写着"复用 `ingest.progress.split_chapters`
的正则思路（**同一套规则**）" —— **其实各写各的，注释是假的**。
两份正则后来必然漂移：作者看到"开卷认识的章节"和"拆书认识的章节"对不上，
却不知道该信哪个。

★★★ 这一版修的真 bug（2026-10-27 改样章时撞出来的）
老正则是 `第.{1,5}[章回节]` —— 中间那个 `.{1,5}` **允许任意字符**，
于是正文里单独成行的一句台词：

    第二回正了。

会被当成**章节标题**（`第` + `二` + `回` + 剩下的当标题）。
后果不是"多认一章"这么轻：**它把这一行之后的所有正文都切成了"第二章"**，
而真正的章节标题还在前面 ⇒ 章节边界整个错位 ⇒ **前情提要按错的章节对齐**。
而且坏得很安静：拆不出来时每��文件都返回同一个键 `"正文"`，
调用方一合并就互相覆盖（这个老坑 `ingest/progress.py` 里已经记着）。

⇒ 新规则的核心一句话：**章节标记后面必须跟一个分隔符（空格 / 冒号 / 间隔号…），
或者整行到头就是标记本身。**
中文正文**行内不会有空格**，所以"标记 + 分隔符"是标题的强特征；
而"第二回正了。"是 `标记 + 汉字`，直接被挡掉。

⚠ 已知取舍：`第一章夜客`（**标记与标题之间没有空格**）在严格档下不算标题。
   这种写法确实存在，但程序自己的示例（`samples/` 全部六套）与说明书都写的是
   `# 第一章 标题`（**有空格**），MuMuAINovel 产的也是 `## 第1章 标题`（**有空格**）。
   ⇒ 严格档认不出时**退回宽松档**（分隔符可省），宁多拆也不整篇一章。

    English:
The single source of truth for "what counts as a chapter heading".
This module replaces three separate regexes (ingest / booklab reader / the mutation knife).
The old pattern `第.{1,5}[章回节]` let an arbitrary run of characters sit between 第 and the
unit character, so a standalone line of prose such as "第二回正了。" was taken for a chapter
heading -- which shifted every following chapter boundary and corrupted the recap alignment.
New rule: a chapter marker must be followed by a separator (space / colon / middle dot ...)
or be the whole line.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    'CN_DIGITS', 'CN_UNITS', 'NUM_CHARS', 'cn_to_int', 'ChapterMark',
    'find_chapter_marks', 'split_chapters', 'chapter_no',
    'STRICT', 'LOOSE',
]

#: 中文数字（**闭集** —— 认不出的字一律当"不是数字"，不猜）。
#: 「同义词是字面判据的漏报后门」⇒ 可数槽必须闭集。
#: 大写（壹贰叁…）也收 —— "第壹章" 在正式一点的稿子里真会出现。
#: [EN] Chinese numerals (**closed set** -- any unknown character means "not a number", never guess).
#: [EN] Formal variants (壹贰叁...) are accepted too -- "第壹章" really does show up in formal manuscripts.
CN_DIGITS: dict[str, int] = {
    '零': 0, '〇': 0,
    '一': 1, '壹': 1, '二': 2, '贰': 2, '两': 2, '三': 3, '叁': 3,
    '四': 4, '肆': 4, '五': 5, '伍': 5, '六': 6, '陆': 6,
    '七': 7, '柒': 7, '八': 8, '捌': 8, '九': 9, '玖': 9,
}

#: 位值单位。
#: [EN] Place-value units.
CN_UNITS: dict[str, int] = {
    '十': 10, '拾': 10, '百': 100, '佰': 100, '千': 1000, '仟': 1000,
}

#: 章节号里允许出现的数字字符（**闭集**）。
#: [EN] The characters allowed inside a chapter number (**closed set**).
_NUM_CHARS = ''.join(sorted(set(CN_DIGITS) | set(CN_UNITS) | set('0123456789')))

#: 同一份闭集，**公开**给别的模块用。
#:   `world/layers.py` 的「必出日」那一栏也在解析**章号** ⇒ 必须用同一套闭集，
#:   不能各写各的（"同一件事两处实现"必然漂移：那边自己写了一份 `_CN_NUM`，
#:   **只认单个字** ⇒「第十五章」被静默丢掉，而「第100章」是好的 ——
#:   两者的差别作者根本看不出来，只会觉得"写了没反应"）。
#: [EN] The same closed set, **exported** for other modules.
#: [EN] `world/layers.py`'s "must appear" field also parses **chapter numbers** => it must use the
#: [EN] same closed set instead of its own copy ("the same thing implemented twice" always drifts:
#: [EN] that other copy accepted **single characters only** => "chapter fifteen" was silently
#: [EN] dropped, while "chapter 100" worked -- the author cannot tell the difference, they just
#: [EN] think "I wrote it and nothing happened").
NUM_CHARS: str = _NUM_CHARS

#: 章节单位字。
#: [EN] Chapter unit characters.
_UNIT_CHARS = '章回节卷'

#: 章节标记（**不含**分隔符）：`第N章` / `第 N 回` / `Chapter 3`。
#: ⚠ 数字部分是**闭集**，不是 `.{1,5}` —— 那是这个 bug 的根源。
#: [EN] The chapter marker (**without** the separator): `第N章` / `第 N 回` / `Chapter 3`.
#: ⚠ The number part is a **closed set**, not `.{1,5}` -- that looseness was the root of the bug.
_MARKER = (r'(?:第\s*[' + _NUM_CHARS + r']+\s*[' + _UNIT_CHARS + r']'
           r'|Chapter\s*[0-9]+)')

#: 分隔符：空白，或 `：:·、-—` 这类标题连接符（后带空白）。
#: [EN] The separator: whitespace, or a title connector such as `：:·、-—` (plus whitespace).
_SEP = r'(?:[ \t\u3000]+|[ \t\u3000]*[：:·、\-—][ \t\u3000]*)'

#: 严格档的标题余文：**不许含句读**（。！？!?；;，,…）。
#:   这是"这一行是标题，不是一句话"的第二个证据。
#: [EN] Strict-mode tail: **no sentence punctuation** (.!?;,...).
#:   This is the second piece of evidence that the line is a heading, not a sentence.
_TAIL_STRICT = r'[^\n。！？!?；;，,…]{0,120}'

#: 宽松档的标题余文：整行（PDF 抽出来的文本常常一行到底）。
#: [EN] Loose-mode tail: the whole line (PDF-extracted text often runs to one line).
_TAIL_LOOSE = r'[^\n]*'

#: 宽松档另外认 `【任意标题】`（读整本书时很多书这么分节）。
#: [EN] Loose mode also accepts `【any title】` (many books section themselves that way).
_BRACKET = r'【[^】\n]{1,20}】'


def cn_to_int(s: str) -> int | None:
    """中文数字 → 整数；**认不出返回 None**（`""`、`井底`、`两三`）。

    支持到千位：`三`→3、`十`→10、`十五`→15、`二十三`→23、`一百零八`→108。

    ⚠ `两三`（约数）**判为非法** —— 它不是章号也不是天数。
      老的 `ingest/progress.py::_cn_to_int` 与 `booklab/selection.py::cn2int`
      在这一点上**本来就不一致**（前者 None，后者 3），这里统一成"非法"。

        English:
    Chinese numeral -> integer; **returns None when it cannot be read** (`""`, `井底`, `两三`).
    ⚠ "两三" (an approximate count) is **invalid** -- it is neither a chapter number nor a day count.
      The old `ingest/progress.py::_cn_to_int` and `booklab/selection.py::cn2int`
      **disagreed** on this (None vs 3); they now agree on "invalid".
    """
    t = str(s or '').strip()
    if not t:
        return None
    if t.isdigit():
        return int(t)
    total = 0
    cur = 0
    prev_digit = False
    for ch in t:
        if ch in CN_DIGITS:
            # 连续两个数字（"两三"）非法 —— 但"零"是占位符，它后面跟数字是合法的（"一百零八"）。
            # [EN] Two consecutive digits ("两三") are invalid -- but 零 is a placeholder, so a digit
            # after it is fine ("一百零八").
            if prev_digit and cur != 0:
                return None
            cur = CN_DIGITS[ch]
            prev_digit = True
        elif ch in CN_UNITS:
            total += (cur or 1) * CN_UNITS[ch]
            cur = 0
            prev_digit = False
        else:
            return None
    return total + cur


@dataclass
class ChapterMark:
    """一个章节标记。

        English:
    One chapter marker.
    """
    start: int          #: 匹配起点（整行开头，含 markdown 井号）
    end: int            #: 匹配终点（这一行的行尾）
    marker: str         #: 标记本身（`第N章` / `Chapter 3` / `【…】`）
    tail: str           #: 标题余文（` 夜客` 的 `夜客`），可能为空
    tail_start: int     #: `tail` 在原文里的起点
    title: str          #: 整行标题（去掉 markdown 井号与首尾空白）
    no: int             #: 章号（认不出 = 0，**不猜**）


def _build_re(*, strict: bool, allow_bracket: bool) -> re.Pattern:
    """拼正则。**分组契约**：1 = 标记，2 = 标题余文。

    严格档：分隔符**必须有**（或整行就是标记）；余文不许含句读。
    宽松档：分隔符可省；余文是整行；另认 `【…】`。

        English:
    Build the regex. **Group contract**: 1 = marker, 2 = tail.
    Strict: the separator is **required** (or the marker is the whole line); the tail carries no
    sentence punctuation.
    Loose: the separator is optional; the tail is the whole line; `【…】` is accepted too.
    """
    alt = _MARKER
    if allow_bracket:
        alt += '|' + _BRACKET
    tail = _TAIL_STRICT if strict else _TAIL_LOOSE
    if strict:
        # 分隔符必须在标记之后、余文之前；余文可为空（"第一章" 独占一行）
        body = rf'(?:(?:{_SEP})({tail}))?'
    else:
        # 分隔符可有可无；余文可为空
        body = rf'(?:(?:{_SEP})?({tail}))?'
    return re.compile(rf'^(?:#{{1,6}}[ \t]*)?({alt}){body}[ \t]*$', re.MULTILINE)


#: 严格档：给摄取（拆正文 / 前情对齐）—— **错拆会毁掉前情提要**。
#: [EN] Strict mode: for ingestion (splitting body text / recap alignment) -- **a wrong split
#: corrupts the recap**.
STRICT = _build_re(strict=True, allow_bracket=False)

#: 宽松档：给读整本书 —— 书里没有别的行，宁可多拆。
#: [EN] Loose mode: for reading whole books -- a book has no other lines, over-splitting is safer.
LOOSE = _build_re(strict=False, allow_bracket=True)


def find_chapter_marks(text: str, *, strict: bool = True,
                       allow_bracket: bool = False,
                       fallback: bool = True) -> list[ChapterMark]:
    """找出一段文本里的所有章节标记。

    严格档找不到时**自动退回宽松档**（分隔符可省）——
    免得"认不出"变成"整篇一章"（那是更坏的结果）。

    ⚠ `fallback=False` 用来**单独测严格档**（判据要用它把两道闸分开：
      "分隔符"与"余文不许含句读"是两道**独立**的闸，各自都要能红）。

        English:
    Find all chapter markers in a chunk of text.
    Strict mode falls back to loose mode when it finds nothing -- so that "not recognized" never
    turns into "the whole text is one chapter" (which is worse).
    """
    raw = str(text or '')
    if not raw:
        return []
    pattern = _build_re(strict=strict, allow_bracket=allow_bracket)
    matches = list(pattern.finditer(raw))
    if not matches and strict and fallback:
        # 严格档颗粒太细 → 宽松档再试一次（**别把"认不出"变成"整篇一章"**）
        # [EN] Strict is too picky -> try loose once (never turn "not recognized" into "one chapter")
        pattern = _build_re(strict=False, allow_bracket=allow_bracket)
        matches = list(pattern.finditer(raw))
    out: list[ChapterMark] = []
    for m in matches:
        marker = m.group(1)
        tail = m.group(2) or ''
        title = m.group(0).strip().lstrip('#').strip()
        out.append(ChapterMark(
            start=m.start(), end=m.end(), marker=marker, tail=tail,
            tail_start=m.start(2) if m.group(2) is not None else m.end(1),
            title=title, no=chapter_no(title),
        ))
    return out


def chapter_no(title: str) -> int:
    """章节标题 → 章号（`第一章 · 夜客`→1、`第12章`→12、`Chapter 3`→3）。

    ★ 为什么要它：正文**拼接顺序**以前由文件系统决定。
      实测 Windows/NTFS 下 `rglob` 返回的是「第一章 → 第三章 → 第二章」
      （同一前缀的汉字按码位排：一 U+4E00 < 三 U+4E09 < 二 U+4E8C）。
      ⇒ 「文风样本取前 4000 字」会**从第一章跨到第三章**，
      「正文对齐」给模型的章节顺序也是乱的。
      认不出章号就返回 0（排最后，不猜）。

        English:
    Chapter title -> chapter number.
    ★ Why: the concatenation order of body text used to be decided by the file system.
      Measured on Windows/NTFS: `rglob` returns "chapter 1 -> chapter 3 -> chapter 2"
      (same-prefix Chinese sorts by code point: 一 U+4E00 < 三 U+4E09 < 二 U+4E8C).
      => the "style sample = first 4000 chars" would cross from chapter 1 into chapter 3,
      and the chapter order handed to the alignment model was scrambled too.
      An unparseable title returns 0 (sorted last; never guess).
    """
    s = str(title or '').strip()
    if not s:
        return 0
    m = re.search(r'第\s*([' + _NUM_CHARS + r']+)\s*[' + _UNIT_CHARS + r']', s)
    if m:
        n = cn_to_int(m.group(1))
        if n:
            return n
    m2 = re.search(r'[Cc]hapter\s*([0-9]+)', s)
    if m2:
        return int(m2.group(1))
    return 0


def split_chapters(text: str) -> dict[str, str]:
    """把正文按「第X章 / 第X回 / 第X节 / Chapter N」拆分。

    接受两种写法（**两种都要认**）：
      · `第一章 早了一刻`        —— 裸标题
      · `# 第一章 早了一刻`      —— markdown 标题（示例与说明书推荐的写法）
    键里**不带**井号（`第一章 早了一刻`，不是 `# 第一章 早了一刻`），
    免得下游拿到的名字带着 markdown 记号。

    ⚠ 拆不出章节时返回 `{"正文": 全文}` —— 调用方必须**自己防覆盖**
      （见 `ingest/pipeline.py`：键相同会互相盖掉，实测三章只剩一章）。

        English:
    Split body text by chapter heading.
    ⚠ When it cannot be split it returns `{"正文": full text}` -- the caller must **guard against
    overwriting** (see `ingest/pipeline.py`: identical keys overwrite each other; measured: three
    chapters collapsed into one).
    """
    raw = str(text or '')
    matches = find_chapter_marks(raw, strict=True)
    if not matches:
        return {"正文": raw}
    chapters: dict[str, str] = {}
    for i, m in enumerate(matches):
        title = m.title
        start = m.end
        end = matches[i + 1].start if i + 1 < len(matches) else len(raw)
        chapters[title] = raw[start:end].strip()
    return chapters
