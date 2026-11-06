# -*- coding: utf-8 -*-
"""**读书**：把一本（可能几十万到几百万字的）书切成"能读得完的样子"。

为什么要单独一层
----------------
拆书的第一道难题不是"怎么拆"，是**读不完** —— 一本连载网文几百章，
逐字喂给模型既贵又超上下文。所以这里解决的是**取样**：
怎么在有限次调用里，看到这本书真正的样子。

三道取样（按顺序，越往后越精细）
--------------------------------
```text
① 分章     第X章 / 第X回 → 章节表（零成本，本地正则）
② 分层取样 章数超过预算时，**按位置分层抽**（不是随机抽）：
            开头密集（黄金三章必留）+ 中段均匀 + 尾部留几章
③ 挑重点   粗扫完之后，按"情绪强度 + 章末钩子 + 用户说好的地方"挑出精读章
```

★ 为什么开头要**密集**留：一本书的前三章是它最贵的三章 ——
  作者在那儿把所有本事都用了一遍（钩子、目标、人设、世界观投放）。
  均匀抽样会把这些"逢 12 取 1"跳过去。

★ 为什么尾部也要留：网文是按章收钱的，**越到后面越知道作者靠什么留住读者**；
  只看前三分之一，学到的只是"开头怎么写"。

★ 抽取规则写成"按位置分层"而不是"随机"：随机抽样**不可复现** ——
  同一本书拆两次得到不同的结论，作者会以为程序不稳定。
  分层抽样是**确定的**（同一本书总是抽同一批章），可以复核。

⚠ 这一层**只读**用户的文件，一个字都不写回去（与开卷同一条铁律）。

English:
**Book reading**: cut a book (possibly hundreds of thousands to millions of characters) into "a
readable shape".
Why a separate layer
----------------
The first hard problem of splitting a book isn't "how to split", it's **can't finish reading**
-- a serial web novel has hundreds of chapters,
feeding it to the model word by word is both expensive and exceeds context. So what's solved
here is **sampling**:
how, within a limited number of calls, to see what this book really looks like.
Three samplings (in order, more refined as you go)
--------------------------------
```text
① Split chapters   Chapter X / 回 X -> chapter list (zero cost, local regex)
② Layered sampling when chapter count exceeds budget, **sample by position in layers** (not
random):
            dense at the start (golden three chapters always kept) + uniform in the middle + keep a few at the tail
③ Pick key ones after rough scan completes, pick close-reading chapters by "emotional intensity
+ end-of-chapter hook + places the user said were good"
```
★ Why the start must be kept **dense**: a book's first three chapters are its three most
expensive chapters --
  that's where the author used every skill at once (hook, goal, characterization, worldview delivery).
  Uniform sampling would skip these by "take 1 every 12".
★ Why also keep the tail: web novels charge per chapter, **the further in, the more you know
what the author uses to hold readers**;
  looking only at the first third, all you learn is "how to write an opening".
★ The extraction rule is written as "layered by position" not "random": random sampling is **not
reproducible** --
  splitting the same book twice gives different conclusions, the author would think the program is unstable.
  Layered sampling is **deterministic** (the same book always samples the same batch of chapters), and can be verified.
⚠ This layer **only reads** the user's files, writes not a single character back (same iron rule
as opening the book).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from booklab import selection as SEL
from booklab import sources as SRC
# ★ 2026-10-27：挑章要按"这是小说还是专业书"分流，密度打分在 `kind` 里（只此一处）
# [EN] ★ 2026-10-27: chapter picking branches on "novel or reference"; the density score lives in
# [EN] `kind` (this is the only implementation)
from booklab import kind
from util.chapters import find_chapter_marks
from booklab import ocr as OCR
from booklab.kind import NOVEL, REFERENCE

_LOG = logging.getLogger('nws.booklab.reader')

#: 网址是不是这种开头（判断"用户给的是网址还是路径"）
# [EN] : Is the URL this kind of prefix (determines "whether the user gave a URL or a path")
_URL_RE = re.compile(r'^https?://', re.I)

#: 每章取样多少字（粗扫用）。400 字够看清"这一章干了什么"，
#: 再多对"一句话概括"没有增量，只是变贵。
# [EN] : How many characters to sample per chapter (for the rough scan). 400 chars is enough to see
# [EN] "what this chapter did",
# [EN] : more yields no increment for "one-sentence summary", it just gets more expensive.
HEAD_CHARS = 400
#: 精读时每段取多少字（重点章要看到手法，所以长得多）
# [EN] : How many characters to sample per paragraph during close reading (key chapters need to show
# [EN] technique, so much longer)
DEEP_CHARS = 2600
#: 粗扫最多扫多少章（超出就分层抽样）。24 批 × 12 章 ≈ 288 章，是一个
#: 长篇的合理覆盖量；再多的部分靠"单元规律"推断，不逐章读。
# [EN] : Max chapters to scan in rough scan (beyond that, layered sampling). 24 batches x 12 chapters ~
# [EN] 288 chapters, a
# [EN] : reasonable coverage for a long work; the rest is inferred from "unit patterns", not read
# [EN] chapter by chapter.
MAX_SCAN_CHAPTERS = 288
#: 一批多少章（进一次 LLM 调用）
# [EN] : How many chapters per batch (one LLM call)
BATCH = 12
#: 精读最多挑几章
# [EN] : Max chapters to pick for close reading
MAX_DEEP = 8

#: ★★★ 2026-10-27：章节标记的识别搬去 `util/chapters.py`（**全项目唯一实现**）。
#:   这里原来有一份自己的正则 `第.{1,5}[章回节卷]` —— 与 `ingest/progress.py` 那份**各写各的**，
#:   而本文件的注释还写着"复用 `ingest.progress.split_chapters` 的正则思路（**同一套规则**）"，
#:   **那是假的**。⇒ 现在真的共用一份。
#:
#:   口径差异（**故意**留的）：读整本书用**宽松档**（分隔符可省、余文是整行、另认 `【…】`），
#:   因为书里没有别的行，宁可多拆；开卷拆正文用**严格档**（错拆会毁掉前情提要）。
#:
#:   [EN] ★★★ 2026-10-27: chapter-marker recognition moved to `util/chapters.py` (the single
#:   implementation).
#:   This file used to carry its own regex `第.{1,5}[章回节卷]` -- **each had its own copy**, while
#:   this file's comment claimed "the same set of rules" -- **it was not true**.
#:   => they really do share one copy now.
#:
#:   The policies differ on purpose: reading a whole book uses **loose mode** (separator optional,
#:   tail is the whole line, `【…】` accepted too) because a book has no other lines; splitting body
#:   text at open-book uses **strict mode** (a wrong split corrupts the recap).


@dataclass
class Chapter:
    """一章。`text` 是**全文**（取样按需裁），`chars` 是全长。
        English:
    One chapter. `text` is the **full text** (sampling trims as needed), `chars` is the full length.
    """

    no: int
    title: str
    text: str = ''

    @property
    def chars(self) -> int:
        return len(self.text or '')

    def head(self, n: int = HEAD_CHARS) -> str:
        """取开头 n 字（粗扫用）。
                English:
        Take the first n characters (used for coarse scan).
        """
        return _clip(self.text, n)

    def as_scan_row(self) -> dict:
        return {'章': self.title, '字数': self.chars}


@dataclass
class Book:
    """一本书（或书的一部分）。

    `unit_kind` 是这本书的**单位**：`章`（有章节结构的文本）或 `页`（PDF 这种分页的）。
    界面与报告都要用它说清"拆了 10 页"还是"拆了 10 章" —— 两者不是一回事。
    
        English:
    A book (or part of a book).
        `unit_kind` is this book's **unit**: `章` (text with chapter structure) or `页` (paginated like PDF).
        Both UI and report must use it to state clearly whether "split 10 pages" or "split 10 chapters" -- the two are not the same thing.
    """

    name: str = ''
    path: str = ''
    chapters: list[Chapter] = field(default_factory=list)
    #: `章` / `页`（选择范围的单位，见 `booklab/selection.py`）
    # [EN] : `章` / `页` (unit for the selection range, see `booklab/selection.py`)
    unit_kind: str = '章'
    #: 从哪儿来的：`file` / `dir` / `url`
    # [EN] : Where it came from: `file` / `dir` / `url`
    source_kind: str = 'file'
    #: 原始说明（路径或网址）
    # [EN] : Original description (path or URL)
    source: str = ''
    #: 用户圈的范围（`Selection`；没有就是 None）
    # [EN] : The range the user circled (`Selection`; None if absent)
    selection: Any = None
    #: **源里一共有多少个单位**（筛之前）。报告要写"前 3 章 → 实际 3 章（共 120）"，
    #: 没有它就说不清"是书短还是范围窄"。
    # [EN] : **How many units in the source in total** (before filtering). The report must say "first 3
    # [EN] chapters -> actually 3 chapters (of 120)",
    # [EN] : without it you can't tell "is the book short or is the range narrow".
    total_units: int = 0
    #: 这一轮读的过程里发生的事（**照实记**，见模块头第 2 条纪律）
    # [EN] : What happened during this round of reading (**record faithfully**, see discipline rule 2 in
    # [EN] the module header)
    notes: list[str] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return sum(c.chars for c in self.chapters)

    @property
    def n(self) -> int:
        return len(self.chapters)

    def summary(self) -> str:
        return (f'{self.name}：{self.n} {self.unit_kind} · '
                f'{self.chars // 1000} 千字')


def _clip(s: str, n: int) -> str:
    t = str(s or '')
    return t if len(t) <= n else t[:n].rstrip() + '…'


def split_into_chapters(text: str) -> list[Chapter]:
    """把正文切成章。

    ★ 复用 `ingest.progress.split_chapters` 的正则思路（**同一套规则**）——
      两处各写一套的话，"开卷认出的章节"和"拆书认出的章节"就会不一样，
      而作者会以为其中一个是错的。切不开时整篇当一章（**照样能拆**）。
    
        English:
    Split the body text into chapters.
        ★ Reuse the regex approach of `ingest.progress.split_chapters` (**the same set of rules**) ——
          if each place wrote its own, the "chapters recognized at open-book" and the "chapters recognized at book-splitting" would differ,
          and the author would think one of them is wrong. When it can't be split, treat the whole text as one chapter (**it can still be split**).
    """
    body = str(text or '').strip()
    if not body:
        return []
    marks = find_chapter_marks(body, strict=False, allow_bracket=True)
    if not marks:
        return [Chapter(no=1, title='（全文）', text=body)]
    out: list[Chapter] = []
    for i, m in enumerate(marks):
        title = ' '.join(m.title.split())[:40]
        start = m.end
        end = marks[i + 1].start if i + 1 < len(marks) else len(body)
        piece = body[start:end].strip()
        # ★★ 标题与正文**在同一行**时（PDF 抽出来的文本常常一行到底），
        #    `m.end()` 已经落到行尾，取到的只剩换行 —— 于是这一章被判成
        #    "标题下面太短"的目录页**丢掉**，整本书变成"认不出章"，
        #    接着回落到按页拆（页对拆书没有意义）。
        #    退一步：改从标题 token 之后那截开始取。
        #    ⚠ 只在原来那截**太短**时才退 —— 正常小说（标题独占一行、
        #      正文在下一行）走的是老路，一个字都不变。
        # [EN] ★★ When title and body are **on the same line** (text extracted from PDF often runs to one
        # [EN] line),
        # [EN] `m.end()` has already landed at end of line, what's captured is only the newline -- so this
        # [EN] chapter is judged
        # [EN] a table-of-contents page where "under the title it's too short" **gets dropped**, the whole book
        # [EN] becomes "no chapters recognized",
        # [EN] then falls back to splitting by page (pages are meaningless for splitting a book).
        # [EN] Step back: instead take from the segment after the title token.
        # [EN] ⚠ Only step back when that original segment is **too short** -- a normal novel (title on its own
        # [EN] line,
        # [EN] body on the next line) takes the old path, not one character changes.
        if len(piece) < 50 and m.tail:
            alt = body[m.tail_start:end].strip()
            if len(alt) > len(piece):
                piece = alt
        # 标题下面的正文太短的（目录页那一类）跳过 —— 它们不是章
        # [EN] Skip ones where the body under the title is too short (the table-of-contents-page type) -- they
        # [EN] are not chapters
        if len(piece) < 50:
            continue
        out.append(Chapter(no=len(out) + 1, title=title, text=piece))
    return out or [Chapter(no=1, title='（全文）', text=body)]


def read_book(path: str | Path, *, selection: Any = None,
              on_step: Any = None) -> Book:
    """读一本 —— 可以是**文件 / 文件夹 / 网址**，并且**只读你要的那一部分**。

    三种输入（用户 2026-10-10 点名）：
      · 文件：`.txt .md .text .docx .html .htm .pdf`（解码见 `booklab/sources`）
        ★ 2026-10-27 起还认：`.doc` / `.wps` `.et` `.dps` / `.epub` /
        `.mobi` `.azw3` / `.rtf` / `.odt` / 图片（走 OCR）
      · 文件夹：里面一堆上面那些文件（一本书被拆成多份）
      · 网址：书的**索引页**，去爬（见 `booklab/web.py`）

    `selection` 见 `booklab/selection.py`（`1-10,15-21` / `前3章` / `第5章-第8章`）。
    传 `None` 或空说明 = 不筛（照旧按分层取样读）。

    ★ 三条都在这一处收口 —— 因为"选择范围"这一步**必须发生在取样之前**：
      用户说"只拆前 10 页"，那 10 页就是全部素材，分层取样应当在这 10 页里挑，
      而不是先在全书的 500 页里挑完再丢掉挑中的（那样挑出来的东西全没了）。
    
        English:
        Three kinds of input (named by the user on 2026-10-10):
          · File: `.txt .md .text .docx .html .htm .pdf` (for decoding see `booklab/sources`)
          · Folder: a bunch of the above files inside (one book split into multiple parts)
          · URL: the book's **index page**, go crawl it (see `booklab/web.py`)
        Passing `None` or an empty description = no filtering (read as before, by stratified sampling).
        ★ All three converge here —— because the "select range" step **must happen before sampling**:
          if the user says "only split the first 10 pages", then those 10 pages are the entire material, and stratified sampling should pick within those 10 pages,
          not first pick across all 500 pages of the whole book and then discard the picked ones (that way everything picked is gone).
    """
    sel = selection if isinstance(selection, SEL.Selection) else SEL.parse(
        selection or '')
    raw = str(path or '').strip()
    if _URL_RE.match(raw):
        return _read_url(raw, sel, on_step)
    p = Path(raw)
    if p.is_dir():
        return _read_dir(p, sel)
    if p.is_file():
        return _read_file(p, sel, on_step=on_step)
    return Book(name=p.name, path=raw, source=raw,
                selection=sel, notes=[f'这个路径不存在：{raw}'])


def _read_url(url: str, sel: SEL.Selection, on_step: Any) -> Book:
    """爬一个索引页。
        English:
    Crawl one index page.
    """
    from booklab import web as WEB
    book = Book(name=url, path=url, source=url, source_kind='url', selection=sel)
    got = WEB.crawl_index(url, on_step=on_step)
    book.name = _short_name(got.title or url)
    book.notes += list(got.notes)
    if not got.ok:
        book.notes.append(got.err or '这个网址没有爬出内容')
        return book
    units = [Chapter(no=i, title=t or f'第 {i} 章', text=x)
             for i, (t, x) in enumerate(got.chapters, 1)]
    return _finish(book, units, '章', sel, total_label='章')


def _read_file(p: Path, sel: SEL.Selection, *, on_step=None) -> Book:
    """读一个文件（PDF 与其它分开走 —— 前者的单位是**页**）。
        English:
    Read one file (PDF goes separately from the others —— the former's unit is the **page**).
    """
    book = Book(name=p.stem, path=str(p), source=str(p),
                source_kind='file', selection=sel)
    if SRC.kind_of(p) == 'pdf':
        return _read_pdf(p, book, sel, on_step=on_step)
    text = SRC.read_file(p)
    if not text.strip():
        book.notes.append('这个文件里没有读到文字（空的？或者编码全乱了）')
        return book
    units = split_into_chapters(text)
    return _finish(book, units, '章', sel)


def _read_pdf(p: Path, book: Book, sel: SEL.Selection, *,
              on_step=None) -> Book:
    """读 PDF。

    ★ 单位的选择（这一处最要紧）：
      · 用户写「页」  → **按页**（他要的就是物理页，别自作聪明合并成章）；
      · 用户写「章」或按默认 → 先看正文里**认不认得出章**：认得出就按章
        （拆书要的是章，页只是纸张），认不出就退回按页并**照实说明**。
    
        English:
    Read PDF.
        ★ Choice of unit (this is the most critical spot):
          · User writes "页"  → **by page** (what he wants is physical pages, don't get clever and merge into chapters);
          · User writes "章" or by default → first see whether chapters are **recognizable** in the body text: if recognizable, go by chapter
            (book-splitting wants chapters, pages are just paper), if not recognizable, fall back to by-page and **state it truthfully**.
    """
    pages = SRC.pdf_pages(p)
    # ★★★ 2026-10-27：扫描版 PDF **自动 OCR**（用户："有些书籍是图片格式的"）。
    #   以前 `pdf_pages` 抽不出字就直接返回 ⇒ 用户拿到"选了文件但一个字都没有"，
    #   而真正的答案是"这是扫描件，要 OCR"。
    #   ★ OCR 一页约 1~3 秒，几百页要跑十几分钟 ⇒ **逐页报进度**
    #     （界面要能显示"正在 OCR 第 x/y 页"，否则用户以为卡死了）。
    # [EN] ★★★ 2026-10-27: scanned PDFs are **OCR'd automatically** (user: "some books are
    # [EN] image-format"). Previously `pdf_pages` returning no text meant an immediate return --
    # [EN] the user got "file chosen, not one character", when the real answer was "this is a scan,
    # [EN] it needs OCR". ★ OCR takes ~1-3s a page, so hundreds of pages take tens of minutes =>
    # [EN] **report progress page by page** (the UI must show "OCR-ing page x/y", otherwise the
    # [EN] user thinks it hung).
    if pages and OCR.is_scan(pages):
        if on_step is not None:
            try:
                on_step('ocr', f'0/{len(pages)}')
            except Exception:                                    # noqa: BLE001
                pass
        pages = OCR.ocr_pdf(
            p,
            progress=(lambda i, n: on_step('ocr', f'{i}/{n}'))
            if on_step is not None else None,
        )
        if any(t.strip() for t in pages):
            book.notes.append(
                f'这是一份**扫描版 PDF**（{len(pages)} 页抽不出文字），已用 OCR 读出正文')
        else:
            book.notes.append(SRC.pdf_hint(p) or 'OCR 也没读出文字')
    if not pages:
        book.notes.append(SRC.pdf_hint(p))
        return book
    if sel.wanted_kind() == '页':
        units = [Chapter(no=i, title=f'第 {i} 页', text=t)
                 for i, t in enumerate(pages, 1)]
        return _finish(book, units, '页', sel)

    body = '\n\n'.join(t for t in pages if t.strip())
    chapters = split_into_chapters(body)
    if len(chapters) >= 3:
        return _finish(book, chapters, '章', sel)
    # 认不出章 → 按页（并说清为什么）
    # [EN] No chapters recognized -> by page (and state clearly why)
    if sel.active():
        book.notes.append('这份 PDF 里没认出章节标题 —— 按**页**来取')
    units = [Chapter(no=i, title=f'第 {i} 页', text=t)
             for i, t in enumerate(pages, 1)]
    return _finish(book, units, '页', sel)


def _read_dir(p: Path, sel: SEL.Selection) -> Book:
    """读一个文件夹（一本书被拆成多个文件时）。

    ★ 一个文件**一篇地切**，而不是先拼起来再切：
      拼起来再切的话，一个文件里没写"第X章"时它会被并进上一章，
      于是"这本书的章节"和"用户手上的文件"对不上 —— 而用户是**按文件**
      想事情的（他可能就想"只拆 3 到 6 那一卷"）。
    
        English:
    Read one folder (when one book is split into multiple files).
        ★ Split **one document at a time**, not concatenate first and then split:
          if you concatenate then split, when a file doesn't write "第X章" it gets merged into the previous chapter,
          so "this book's chapters" and "the files the user holds" don't match —— and the user thinks **in terms of files**
          (he may just want "only split volume 3 to 6").
    """
    book = Book(name=p.name, path=str(p), source=str(p),
                source_kind='dir', selection=sel)
    files = SRC.list_files(p)
    if not files:
        book.notes.append(f'这个文件夹里没有能拆的文档'
                          f'（认的格式：{" ".join(sorted(SRC.SUPPORTED_SUFFIXES))}）')
        return book
    units: list[Chapter] = []
    for f in files:
        text = SRC.read_file(f)
        if not text.strip():
            continue
        inner = split_into_chapters(text)
        if len(inner) == 1:
            inner[0].title = f.stem
            inner[0].no = len(units) + 1
            units.append(inner[0])
        else:
            for c in inner:
                c.no = len(units) + 1
                units.append(c)
    if not units:
        book.notes.append('这个文件夹里的文档都没读到文字')
    return _finish(book, units, '章', sel)


def _finish(book: Book, units: list[Chapter], kind: str,
            sel: SEL.Selection, total_label: str = '') -> Book:
    """筛 → 去掉空的 → 写回 `book`（**所有输入形态的最后一步**）。

    三件事都在这里做完，别让四条读入路径各写一遍（那正是"某一条路忘了筛"
    这类 bug 的温床）。
    
        English:
    Filter → drop empty ones → write back to `book` (**the final step of all input forms**).
        Do all three things here, don't let the four read-in paths each write it once (that is exactly the breeding ground
        for bugs like "some path forgot to filter").
    """
    if sel.err:
        # 解析失败：**不许当全部**（见 selection 模块头第 1 条纪律）——
        # 记下来、且这一轮什么都不拆（宁可"没读"，不要"多读"）。
        # [EN] Parse failure: **must not treat as all** (see discipline rule 1 in the selection module header)
        # [EN] --
        # [EN] record it, and split nothing this round (better "not read" than "read too much").
        book.notes.append(sel.err)
        book.selection = sel
        book.total_units = len(units)
        return book
    book.total_units = len(units)
    titles = [c.title for c in units]
    if sel.active():
        idx = SEL.apply(sel, titles)
        if sel.wanted_kind() == '页' and kind != '页':
            book.notes.append('这份文本没有「页」—— 按**章**来取')
        if sel.wanted_kind() == '章' and kind != '章':
            book.notes.append('这份文件只有页、没有章名 —— 按**页**来取')
        units = [units[i] for i in idx]
        if not units:
            book.notes.append(
                f'按「{sel.label()}」一个都没选上 —— 这本书一共 {len(titles)} '
                f'{kind}，检查一下范围写对没有')
    empty = [c for c in units if not (c.text or '').strip()]
    if empty:
        book.notes.append(f'这 {len(empty)} {kind}是空的（没有文字），已跳过')
    book.chapters = [c for c in units if (c.text or '').strip()]
    book.unit_kind = kind
    book.selection = sel
    return book


def _short_name(s: str, limit: int = 40) -> str:
    t = ' '.join(str(s or '').split())
    return t if len(t) <= limit else t[:limit]


# ══════════════════════════════════════════════════════════════
#  分层取样
# [EN] Layered sampling
# ══════════════════════════════════════════════════════════════
#: 开头**必须留**的章数（黄金三章 + 一点余量）
# [EN] : Number of chapters that **must be kept** at the start (golden three chapters + a bit of
# [EN] margin)
HEAD_KEEP = 4
#: 尾部留几章
# [EN] : How many chapters to keep at the tail
TAIL_KEEP = 3


def layer_pick(n: int, budget: int = MAX_SCAN_CHAPTERS) -> list[int]:
    """从 `n` 章里按**位置分层**挑出至多 `budget` 章的**下标**（0 起）。

    分层规则（确定性的，同一本书总是同一批 —— 可复核）：

    ```text
    前 4 章            全留（黄金三章：作者的全部本事都在这里用过一遍）
    最后 3 章          全留（网文按章收钱，尾部最能看出作者靠什么留人）
    中间              均匀取满剩下的名额
    ```

    不够预算时全留（**书短就不抽**）。
    
        English:
    Pick at most `budget` chapter **indices** (0-based) from `n` chapters by **positional
    stratification**.
        Stratification rules (deterministic, the same book always gets the same batch —— reviewable):
        ```text
        First 4 chapters        keep all (golden three chapters: the author used all his skills here once)
        Last 3 chapters         keep all (web fiction charges per chapter, the tail best shows what the author uses to retain readers)
        Middle                  fill the remaining slots evenly
        ```
        When budget is insufficient, keep all (**short book means no sampling**).
    """
    if n <= 0:
        return []
    if n <= budget:
        return list(range(n))
    head = list(range(min(HEAD_KEEP, n)))
    tail = list(range(max(HEAD_KEEP, n - TAIL_KEEP), n))
    rest = budget - len(head) - len(tail)
    mid_lo, mid_hi = HEAD_KEEP, n - TAIL_KEEP
    picked = list(head)
    if rest > 0 and mid_hi > mid_lo:
        span = mid_hi - mid_lo
        # 均匀取：step 用浮点算，保证"中间每一段都被碰到"
        # [EN] Sample uniformly: compute step with floats, ensuring "every middle segment is touched"
        step = span / rest
        for i in range(rest):
            picked.append(mid_lo + int(i * step))
    picked += tail
    return sorted(set(x for x in picked if 0 <= x < n))


def scan_set(book: Book, budget: int = MAX_SCAN_CHAPTERS) -> list[Chapter]:
    """粗扫要读的那批章（分层取样后的）。
        English:
    The batch of chapters to read for the coarse scan (after stratified sampling).
    """
    idx = layer_pick(book.n, budget)
    return [book.chapters[i] for i in idx]


def batches(chapters: list[Chapter], size: int = BATCH) -> list[list[Chapter]]:
    """按 `size` 分批（进 LLM 的单元）。
        English:
    Batch by `size` (the unit entering the LLM).
    """
    size = max(1, int(size))
    return [chapters[i:i + size] for i in range(0, len(chapters), size)]


def render_batch(rows: list[Chapter]) -> str:
    """把一批章拼成提示词里的那一段（每章取开头 `HEAD_CHARS` 字）。
        English:
    Concatenate a batch of chapters into that passage in the prompt (take the first `HEAD_CHARS`
    characters of each chapter).
    """
    out: list[str] = []
    for c in rows:
        out.append(f'【{c.title}】（{c.chars} 字）\n{c.head(HEAD_CHARS)}')
    return '\n\n'.join(out)


def render_deep(rows: list[Chapter]) -> str:
    """精读那一段（每章取开头 `DEEP_CHARS` 字）。

    ⚠ 精读**也只取开头**：一章几万字全塞进去会爆上下文。取 2600 字足以看清
      "这一章是怎么开场的、怎么立人的、怎么埋钩子的" —— 那正是手法所在。
      章的后半段更多是"把这一章推完"，手法密度反而低。
    
        English:
    Deep-read that passage (take the first `DEEP_CHARS` characters of each chapter).
        ⚠ Deep reading **also takes only the beginning**: stuffing tens of thousands of characters of a chapter in would blow the context. 2600 characters is enough to see clearly
          "how this chapter opens, how it establishes the character, how it plants the hook" —— that is exactly where the technique lies.
          The second half of a chapter is more about "pushing this chapter to completion", and the technique density is actually lower.
    """
    out: list[str] = []
    for c in rows:
        out.append(f'【{c.title}】（{c.chars} 字，这里取开头）\n{_clip(c.text, DEEP_CHARS)}')
    return '\n\n'.join(out)


# ══════════════════════════════════════════════════════════════
#  挑重点章（粗扫完成后）
# [EN] Pick key chapters (after rough scan completes)
# ══════════════════════════════════════════════════════════════
def pick_deep(book: Book, scan: list[dict], *, good: str = '',
              extra: list[str] | None = None,
              limit: int = MAX_DEEP,
              kind: str = NOVEL) -> list[Chapter]:
    """从粗扫结果里挑**精读**的章。

    三个来源，按优先级：
      ① **用户说"好在哪儿"**里点到章名的 —— 那是他真正想学的地方；
      ② 粗扫里**情绪强度最高**的几章（爆点最能看出手法）；
      ③ 开头三章（立人设、放钩子的手法最密）。

    ★★★ 2026-10-27：**专业书走另一套挑法**（`kind == REFERENCE`）。
      专业书没有情绪曲线，按"情绪强度"挑等于随机挑；而"开头三章"在专业书里
      恰恰是**绪论 / 前言 / 凡例** —— 一条素材都拆不出来。
      ⇒ 专业书改按 `kind.density()` 的**信息密度**挑（见 `_pick_deep_reference`）。

    ⚠ 全是**确定性**挑法，不用随机：同一本书拆两次得到同一批精读章。

        English:
    Pick the chapters for **deep reading** from the coarse-scan results.
        Three sources, by priority:
          ① chapters named by the user in "what's good about it" —— that is what he really wants to learn;
          ② the few chapters with the **highest emotional intensity** in the coarse scan (explosive points best show the technique);
          ③ the opening three chapters (the densest technique for establishing the character design and planting hooks).
        ★★★ 2026-10-27: **reference books take a different route** (`kind == REFERENCE`). They have
        no emotional curve, so picking by "intensity" is a coin flip, and their "opening three" are
        exactly the **introduction / preface / notes on use** -- not one extractable entry.
        => Reference books are picked by **information density** (`kind.density()`), see
        `_pick_deep_reference`.
        ⚠ All are **deterministic** selection methods, no randomness: splitting the same book twice yields the same batch of deep-read chapters.
    """
    if kind == REFERENCE:
        return _pick_deep_reference(book, scan, good=good, extra=extra,
                                    limit=limit)
    if not scan:
        return book.chapters[:min(3, book.n)]

    by_title = {c.title: c for c in book.chapters}
    picked: list[Chapter] = []

    def add(c: Chapter | None) -> None:
        if c is not None and c not in picked:
            picked.append(c)

    # ① 用户点到的
    # [EN] ① Ones the user pointed at
    g = str(good or '')
    if g:
        for title, c in by_title.items():
            key = title.split('】')[-1].strip() if '】' in title else title
            if key and key in g:
                add(c)
        for t in (extra or []):
            add(by_title.get(t))

    # ② 情绪最高的几章（并列时取靠后的 —— 后面还能爆，说明手法更稳）
    # [EN] ② The few chapters with highest emotion (on ties take the later one -- still explosive later
    # [EN] means the technique is more stable)
    rows = sorted(scan, key=lambda r: (-int(r.get('情绪') or 0),
                                       -_no_of(r.get('章') or '')))
    for r in rows:
        if len(picked) >= limit - 3:
            break
        if int(r.get('情绪') or 0) >= 3:
            add(by_title.get(str(r.get('章') or '')))

    # ③ 开头三章（**一定进** —— 那是作者本事最密的地方）
    # [EN] ③ The opening three chapters (**always included** -- that's where the author's skill is densest)
    for c in book.chapters[:3]:
        add(c)

    return picked[:limit]


def _pick_deep_reference(book: Book, scan: list[dict], *, good: str = '',
                         extra: list[str] | None = None,
                         limit: int = MAX_DEEP) -> list[Chapter]:
    """专业书挑精读章：**按信息密度**，不是按情绪。

    ★ 与小说那条路的三个差别（每一条都是被"专业书没有高潮"逼出来的）：

      · **不按情绪挑**：它没有情绪曲线，`情绪` 字段在专业书里恒为空；
      · **开头三章不再"一定进"**：那几章是绪论/前言/凡例 ——
        `kind.density()` 给它们 0 分，进精读就是白花一次 LLM；
      · **密度 0 的章直接跳过**（前言 / 索引 / 参考文献 / 版权页 / 纯图版）。

    ⚠ `scan` 里的 `密度` 是**模型填的**（`REF_SCAN_PROMPT` 要求它填）。
      本项目的老教训：**提示词里写了 ≠ 生效**（实测 40~74% 不遵守）
      ⇒ 模型没填（或全填 0）时，**退回本地 `kind.density()` 现算**，
      不许因为模型偷懒就"一章都不挑"。

        English:
    Pick deep-read chapters for a reference book: **by information density**, not emotion.
        ★ Three differences from the novel route (each forced by "a reference book has no climax"):
          · **not by emotion**: there is no emotional curve, the `情绪` field is always empty here;
          · **the opening three are no longer "always in"**: those are the introduction / preface /
            notes on use -- `kind.density()` gives them 0, and deep-reading them wastes an LLM call;
          · **chapters with density 0 are skipped outright** (preface / index / bibliography /
            copyright / plate pages).
        ⚠ The `密度` in `scan` is **filled in by the model** (required by `REF_SCAN_PROMPT`). An old
        lesson here: **written in the prompt ≠ in effect** (measured: 40~74% non-compliance)
        => when the model leaves it out (or fills all zeros), **fall back to computing
        `kind.density()` locally**, never end up "picking no chapter at all" because the model
        was lazy.
    """
    by_title = {c.title: c for c in book.chapters}
    picked: list[Chapter] = []

    def add(c: Chapter | None) -> None:
        if c is not None and c not in picked:
            picked.append(c)

    # ① 用户点到的（与小说同一条：那是他真正想学的地方）
    # [EN] ① The ones the user pointed at (same rule as novels: that is what he really wants)
    g = str(good or '')
    if g:
        for title, c in by_title.items():
            key = title.split('】')[-1].strip() if '】' in title else title
            if key and key in g:
                add(c)
        for t in (extra or []):
            add(by_title.get(t))

    # ② 密度最高的几章（**密度 0 的不要** —— 见上面第 3 条）
    # [EN] ② The densest chapters (**density 0 is excluded** -- see point 3 above)
    def _dens(r: dict) -> float:
        try:
            return float(r.get('密度') or 0)
        except (TypeError, ValueError):
            return 0.0

    rows = sorted(scan, key=lambda r: (-_dens(r), -_no_of(r.get('章') or '')))
    for r in rows:
        if len(picked) >= limit:
            break
        if _dens(r) <= 0:
            continue
        add(by_title.get(str(r.get('章') or '')))

    # ③ 兜底：模型没填密度 ⇒ 本地现算（不许因为模型偷懒就一章都不挑）
    # [EN] ③ Fallback: the model didn't fill density => compute locally (never pick nothing)
    if not picked:
        for c in sorted(book.chapters,
                        key=lambda c: (-kind.density(c.text), c.no)):
            if len(picked) >= limit:
                break
            if kind.density(c.text) > 0:
                add(c)
    return picked[:limit]


def _no_of(title: str) -> int:
    m = re.search(r'(\d+)', str(title or ''))
    return int(m.group(1)) if m else 0


def outline_text(book: Book, scan: list[dict], *, cap: int = 6000) -> str:
    """把粗扫结果拼成"全书概览"（进归纳那一步的提示词）。

    按章号排序、格式紧凑 —— 这是唯一一处"把整本书压缩成一段"的地方。
    
        English:
    Concatenate the coarse-scan results into a "whole-book overview" (the prompt that goes into the
    summarization step).
        Sort by chapter number, compact format — this is the only place that "compresses the entire book into one paragraph".
    """
    if not scan:
        return '（没有概览）'
    order = {c.title: c.no for c in book.chapters}
    rows = sorted(scan, key=lambda r: order.get(str(r.get('章') or ''), 9999))
    lines: list[str] = []
    for r in rows:
        func = '、'.join(str(x) for x in (r.get('功能') or []))
        hook = str(r.get('钩子') or '')
        bits = [f"{r.get('章')}", str(r.get('一句话') or '')]
        tail = []
        if func:
            tail.append(func)
        if hook and hook != '无':
            tail.append(f'钩子：{hook}')
        if r.get('情绪'):
            tail.append(f"情绪{r.get('情绪')}")
        line = '｜'.join(bits + ([' '.join(tail)] if tail else []))
        lines.append('- ' + line)
    return _clip('\n'.join(lines), cap)
