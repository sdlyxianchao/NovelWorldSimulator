# -*- coding: utf-8 -*-

"""**取文**：把"用户给的那份东西"变成一个能拆的正文文本。

三种输入（用户 2026-10-10 点名要的三样）
--------------------------------------
```text
① 一个文件    .txt / .md / .text / .docx / .html / .htm / .pdf
② 一个文件夹  里面装着一堆上面那些文件（一本书被拆成多份时最常见）
③ 一个网址    书的**索引页**（章节列表）—— 去爬，见 `booklab/web.py`
```

为什么单独一层（而不是直接塞进 `reader`)
--------------------------------------
`reader` 管的是"读到之后**怎么取样**"（分章 → 分层抽 → 挑重点章），
这一层管的是"**从哪儿读、读不读得出来**"。混在一起的话，"再加一种格式"
就得动取样逻辑 —— 而取样逻辑是拆书里最贵、最容易改坏的一段。

★ 共用开卷的解码器（`ingest.scanner.read_single_file`）
  纯文本 / docx / html 一律走它：**同一个文件开卷读得出、拆书读不出**
  是最说不过去的一种不一致（用户会以为其中一个是坏的）。
  ⚠ PDF 是这一层独有的（开卷不读 PDF），走 `pypdf`；它是**可选依赖** ——
    没装时给出的必须是"要装什么"，不是一句 `ModuleNotFoundError`。

⚠ 这一层**只读**用户的文件，一个字都不写回去（与开卷同一条铁律）。

English:
**Extraction**: turn "the thing the user gave" into splittable body text.
Three inputs (the three the user named on 2026-10-10)
--------------------------------------
```text
① A file    .txt / .md / .text / .docx / .html / .htm / .pdf
② A folder  containing a bunch of the above files (most common when a book is split into parts)
③ A URL     the book's **index page** (chapter list) -- go crawl it, see `booklab/web.py`
```
Why a separate layer (instead of stuffing it straight into `reader`)
--------------------------------------
`reader` handles "**how to sample** after reading" (split into chapters -> layered sampling ->
pick key chapters),
this layer handles "**where to read from, and whether it can be read at all**". Mixed together,
"adding one more format"
would require touching the sampling logic -- and the sampling logic is the most expensive and
most fragile part of book-splitting.
★ Shares the opening-book decoder (`ingest.scanner.read_single_file`)
  Plain text / docx / html all go through it: **the same file readable by the opening-book side but not by book-splitting**
  is the most indefensible kind of inconsistency (users will think one of them is broken).
  ⚠ PDF is unique to this layer (the opening-book side doesn't read PDFs), goes through `pypdf`; it is an **optional dependency** --
    when not installed, the message must be "what to install", not a bare `ModuleNotFoundError`.
⚠ This layer **only reads** the user's files, not one character is written back (same iron rule
as the opening-book side).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

_LOG = logging.getLogger('nws.booklab.sources')

#: 纯文本类后缀（交给开卷那套解码 + chardet 探测）
# [EN] : Plain-text suffixes (handed to the opening-book decode + chardet detection)
TEXT_SUFFIXES = frozenset({'.txt', '.md', '.text', '.markdown'})
#: Word 文档
# [EN] : Word documents
DOCX_SUFFIXES = frozenset({'.docx'})
#: 网页存档（已下载的 .html）
# [EN] : Web archive (downloaded .html)
HTML_SUFFIXES = frozenset({'.html', '.htm', '.xhtml'})
#: PDF
PDF_SUFFIXES = frozenset({'.pdf'})
#: ★★★ 2026-10-27（用户：「有些书籍是图片格式的 你至少要支持常见格式
#:   包括 pdf 文字 pdf 图片 Word 格式 html txt 常见电子书格式 以及 wps 格式」）
#:   下面这批是**这一轮补进来的**。原来的清单只有 txt/md/docx/html/pdf，
#:   而用户手上的书多半是 **epub / 扫描版 PDF / WPS 存的 .wps** —— 认不出来
#:   的表现不是报错，是"选了文件但一个字都读不出来"，最难排查的那一种。
# [EN] ★★★ 2026-10-27 (user: "some books are image-only; support the common formats at least:
#   text PDF, image PDF, Word, html, txt, common ebook formats, and WPS"). The set below was added
#   in this round. The old list was txt/md/docx/html/pdf only, while the books on the user's desk
#   are mostly **epub / scanned PDF / .wps saved by WPS** -- and failing to recognise a format does
#   not raise, it silently yields "file chosen, not one character read", the hardest kind to debug.
#: 旧版 Word（`.doc`）—— OLE 复合文档，不是 zip，python-docx 读不了。
# [EN] : Legacy Word (`.doc`) -- an OLE compound file, not a zip; python-docx cannot read it.
DOC_SUFFIXES = frozenset({'.doc'})
#: WPS 三件套（`.wps` 文字 / `.et` 表格 / `.dps` 演示）。
#:   ★ `.wps` **不是** zip：WPS 默认存的 `.wps` 是 OLE 复合文档（与 `.doc` 同族），
#:     所以走的是同一条路（COM 优先，读不出再 `olefile` 抽文本流）。
# [EN] : The WPS trio (`.wps` text / `.et` spreadsheet / `.dps` presentation). ★ `.wps` is **not** a
# [EN] zip: WPS saves `.wps` as an OLE compound file (same family as `.doc`), so it takes the same
# [EN] route (COM first, then `olefile` to pull the text stream).
WPS_SUFFIXES = frozenset({'.wps', '.et', '.dps'})
#: 电子书：`.epub`（zip + OPF + XHTML，主流）/ `.mobi`/`.azw3`（Kindle）。
# [EN] : Ebooks: `.epub` (zip + OPF + XHTML, the mainstream one) / `.mobi`/`.azw3` (Kindle).
EPUB_SUFFIXES = frozenset({'.epub'})
MOBI_SUFFIXES = frozenset({'.mobi', '.azw3', '.azw'})
#: 富文本与开放文档（老资料 / LibreOffice 常见）。
# [EN] : Rich text and open documents (old material / common with LibreOffice).
RTF_SUFFIXES = frozenset({'.rtf'})
ODT_SUFFIXES = frozenset({'.odt'})
#: ★★★ 图片（单张扫描页 / 拍照的页）。**没有文字层，只能 OCR**。
#:   一本书被拆成几百张图时最常见的就是这个（"图片格式的书籍"）。
# [EN] : ★★★ Images (single scanned / photographed pages). **No text layer, OCR only.** This is the
# [EN] most common shape when a book arrives as hundreds of images ("image-format book").
IMAGE_SUFFIXES = frozenset({'.jpg', '.jpeg', '.png', '.webp', '.bmp',
                            '.tif', '.tiff'})
#: 全部认的后缀。
# [EN] : All recognized suffixes.
#:
#: ★ 与 `ingest.scanner._READ_SUFFIX` **故意不同**：那边多 `.yaml/.yml`
#:   （设定集是 yaml），而拆书读的是**正文**，yaml 混进来只会把标题与元数据
#:   当成正文拆。两边各自的清单就写在各处，别互相 import 一个"通用"表 ——
#:   合并之后想改一边会牵动另一边（开卷那边的注释里已经记过一次同类教训）。
# [EN] : ★ **Deliberately different** from `ingest.scanner._READ_SUFFIX`: that side has extra
# [EN] `.yaml/.yml`
# [EN] : (settings sets are yaml), while book-splitting reads the **body text**; letting yaml in would
# [EN] only
# [EN] : treat titles and metadata as body text to split. Each side keeps its own list where it is,
# [EN] don't import
# [EN] : a "common" table from one another -- after merging, changing one side would drag the other
# [EN] (the comments
SUPPORTED_SUFFIXES = (TEXT_SUFFIXES | DOCX_SUFFIXES | DOC_SUFFIXES
                      | WPS_SUFFIXES | HTML_SUFFIXES | PDF_SUFFIXES
                      | EPUB_SUFFIXES | MOBI_SUFFIXES | RTF_SUFFIXES
                      | ODT_SUFFIXES | IMAGE_SUFFIXES)

#: 扫描文件夹时跳过的目录（与开卷同一套）
# [EN] : Directories to skip when scanning a folder (same set as the opening-book side)
SKIP_DIRS = frozenset({'.workbuddy', '__pycache__', '.venv', '.git', '.svn',
                       'node_modules', '.mypy_cache', '.pytest_cache'})

#: 单个文件最多读多少字符。**不是省内存，是防呆**：用户误选了一个几百 MB 的
#: 日志文件时，程序应该在"读到一半"就打住并照实说，而不是把内存吃掉。
# [EN] : Max characters to read from a single file. **Not to save memory, but as a guard**: when a user
# [EN] picks a
# [EN] : several-hundred-MB log file by mistake, the program should stop "halfway through reading" and
# [EN] say so, not eat all the memory.
MAX_FILE_CHARS = 8_000_000
#: 文件夹最多读多少个文件（同理，防呆）
# [EN] : Max files to read from a folder (same idea, a guard)
MAX_DIR_FILES = 400


def suffix_of(p: Path | str) -> str:
    """小写后缀（含点）；拿不到返回空串。
        English:
    Lowercased suffix (with dot); returns empty string if it can't be obtained.
    """
    try:
        return Path(p).suffix.lower()
    except (TypeError, ValueError):
        return ''


def is_supported(p: Path | str) -> bool:
    """这个路径是不是拆书认的文档格式。
        English:
    Whether this path is a document format recognized by book-splitting.
    """
    return suffix_of(p) in SUPPORTED_SUFFIXES


def kind_of(p: Path | str) -> str:
    """这个文件按哪条路读 —— 报错与提示里要用。

    2026-10-27 起有九种：`text` / `docx` / `html` / `pdf` /
    **`ole`**（旧版 Word 与 WPS 三件套，都是 OLE 复合文档）/
    **`epub`** / **`mobi`** / **`rtf`** / **`odt`** / **`image`**（只能 OCR）。
        English:
    Which route this file is read by -- used in errors and hints.
    Since 2026-10-27 there are nine: `text` / `docx` / `html` / `pdf` /
    **`ole`** (legacy Word and the WPS trio, all OLE compound files) /
    **`epub`** / **`mobi`** / **`rtf`** / **`odt`** / **`image`** (OCR only).
    """
    s = suffix_of(p)
    if s in PDF_SUFFIXES:
        return 'pdf'
    if s in DOCX_SUFFIXES:
        return 'docx'
    if s in HTML_SUFFIXES:
        return 'html'
    if s in (DOC_SUFFIXES | WPS_SUFFIXES):
        return 'ole'
    if s in EPUB_SUFFIXES:
        return 'epub'
    if s in MOBI_SUFFIXES:
        return 'mobi'
    if s in RTF_SUFFIXES:
        return 'rtf'
    if s in ODT_SUFFIXES:
        return 'odt'
    if s in IMAGE_SUFFIXES:
        return 'image'
    return 'text'


# ══════════════════════════════════════════════════════════════
#  文件名排序：带数字的按数字排
# [EN] Filename sorting: ones with digits sort by the number
# ══════════════════════════════════════════════════════════════
_NUM_RE = re.compile(r'(\d+)')


def natural_key(p: Path | str):
    """自然序的排序键：`第2章` 排在 `第10章` 前面。

    ⚠ 不能用 `sorted()` 的字典序 —— 那会把 `第10章` 排到 `第2章` 前面，
      于是"一本书被拆成多个文件"时**顺序是乱的**，而拆出来的结论看上去仍然
      像模像样（最坏的一种错：不报错、结果错）。
    
        English:
        ⚠ Can't use the lexicographic order of `sorted()` -- that would put `第10章` before `第2章`,
          so when "a book is split into multiple files" the **order is scrambled**, yet the split conclusions still look
          plausible (the worst kind of error: no error raised, wrong result).
    """
    parts = _NUM_RE.split(str(p))
    out: list = []
    for i, seg in enumerate(parts):
        out.append(int(seg) if i % 2 else seg.lower())
    return out


def list_files(root: Path | str, *, limit: int = MAX_DIR_FILES) -> list[Path]:
    """列出一个文件夹里**所有认得的文档**（递归，自然序）。

    结果按**相对路径**的自然序 —— 一本书被拆成 `1.txt` … `10.txt` 时
    顺序才是对的（见 `natural_key`）。
    
        English:
    List **all recognized documents** in a folder (recursive, natural order).
        Results are in the natural order of **relative paths** -- only then is the order correct when a book is split
        into `1.txt` ... `10.txt` (see `natural_key`).
    """
    base = Path(root)
    if not base.is_dir():
        return []
    found: list[Path] = []
    for p in base.rglob('*'):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name.startswith('.') or p.name.startswith('~$'):
            continue
        if p.is_file() and is_supported(p):
            found.append(p)
    found.sort(key=lambda p: natural_key(p.relative_to(base).as_posix()))
    return found[:max(1, int(limit))]


# ══════════════════════════════════════════════════════════════
#  读一个文件
# [EN] Read one file
# ══════════════════════════════════════════════════════════════
def read_file(path: Path | str) -> str:
    """读一个文件 → 纯文本。

    ★ 2026-10-27：按 `kind_of()` 的九条路分发（原来只有 PDF 一条特殊路）。
      新增的六条各自有**独立的失败话术**（见 `format_hint`）：
      它们失败时最要紧的不是"返回空"，而是**让界面能说出该装什么**。

    PDF 走 `pypdf`（扫不出字就 OCR）；ole / epub / mobi / rtf / odt 各自走
    自己的解码器；图片直接 OCR；其余走开卷的解码器
    （`ingest.scanner.read_single_file`），拿不到就自己按 utf-8 兜底 ——
    **不许因为某个文件读不出就整本拆不下去**。

        English:
    Read one file -> plain text.
        ★ 2026-10-27: dispatched by the nine routes of `kind_of()` (there used to be only one
        special route, PDF). The six new ones each have their **own failure wording** (see
        `format_hint`): when they fail the important thing is not "return empty", it is **letting
        the UI say what to install**.
        PDF goes through `pypdf` (OCR if no text comes out); ole / epub / mobi / rtf / odt each use
        their own decoder; images go straight to OCR; the rest go through the opening-book decoder
        (`ingest.scanner.read_single_file`), falling back to utf-8 -- **must not let the whole book
        fail to split because one file can't be read**.
    """
    p = Path(path)
    if not p.is_file():
        return ''
    k = kind_of(p)
    if k == 'pdf':
        return read_pdf_text(p)
    if k == 'ole':
        return read_ole_text(p)
    if k == 'epub':
        return read_epub_text(p)
    if k == 'mobi':
        return read_mobi_text(p)
    if k == 'rtf':
        return read_rtf_text(p)
    if k == 'odt':
        return read_odt_text(p)
    if k == 'image':
        return _read_image_text(p)
    text = _via_ingest(p)
    if text.strip():
        return text
    try:
        return p.read_text(encoding='utf-8', errors='ignore')
    except OSError as e:                                         # noqa: BLE001
        _LOG.warning('读不了 %s：%r', p, e)
        return ''


def _via_ingest(p: Path) -> str:
    """走开卷的解码器（**同一个解码器**，见模块头）。

    ★★★ 2026-10-27 修了一个**静默的错**：`FileItem` 的字段叫 **`content`**，
      这里原来写的是 `getattr(item, 'text', '')` ⇒ **恒为空** ⇒
      `.docx` 一路掉到下面的"utf-8 读原始字节"，读出来的是 zip 的二进制
      （`PK\\x03\\x04` 开头的一串乱码），而**它不报错、也不为空** ——
      于是拆书拿到一份"看起来有内容"的垃圾正文。

      （这正是"同一个文件开卷读得出、拆书读不出"最坏的一种：两边**都读得出**，
      只是拆书这边读出来的是 zip。）

        English:
    Go through the opening-book decoder (**the same decoder**, see module header).
        ★★★ 2026-10-27 fixed a **silent** bug: `FileItem`'s field is **`content`**, but this read
        `getattr(item, 'text', '')` => **always empty** => `.docx` fell through to "read raw bytes
        as utf-8", yielding the zip's binary (a run of mojibake starting with `PK\\x03\\x04`), and
        **it neither raised nor came back empty** -- so book-splitting received a "looks like it has
        content" garbage body. (This is the worst form of "opening-book reads it, splitting doesn't":
        both sides **do** read something, splitting just reads the zip.)
    """
    try:
        from ingest.scanner import read_single_file
        item = read_single_file(p)
        return str(getattr(item, 'content', '')
                   or getattr(item, 'text', '') or '')
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('开卷解码器没读成 %s（改走 utf-8 兜底）：%r', p, e)
        return ''


# ── PDF ──────────────────────────────────────────────────────
def pdf_pages(path: Path | str) -> list[str]:
    """PDF 的**逐页**文本（页选择要用到"第 N 页"）。

    返回空列表有三种原因，**都要能被调用方区分**（见 `pdf_hint`）：
      · 没装 `pypdf`；· 文件坏了；· 是扫描件（有页面但抽不出字）。
    
        English:
    PDF's **per-page** text (page selection needs "page N").
        An empty list has three reasons, **all must be distinguishable by the caller** (see `pdf_hint`):
          · `pypdf` not installed; · file is corrupted; · it's a scan (has pages but no text can be extracted).
    """
    p = Path(path)
    try:
        from pypdf import PdfReader
    except ImportError:
        _LOG.warning('没装 pypdf —— 拆 PDF 需要它')
        return []
    try:
        reader = PdfReader(str(p))
        if getattr(reader, 'is_encrypted', False):
            try:
                reader.decrypt('')          # 有些 PDF 只是"空密码"加密
                # [EN] Some PDFs are only encrypted with an "empty password"
            except Exception:                                    # noqa: BLE001
                return []
        out: list[str] = []
        for page in reader.pages:
            try:
                out.append(str(page.extract_text() or ''))
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('这一页抽不出文字：%r', e)
                out.append('')
        return out
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('读 PDF 失败 %s：%r', p, e)
        return []


def read_pdf_text(path: Path | str, *, allow_ocr: bool = True,
                  progress=None, should_stop=None) -> str:
    """PDF 全文（逐页拼起来，页与页之间空一行）。

    ★★★ 2026-10-27：**扫描件自动走 OCR**。
      以前抽不出字就直接返回空 —— 用户拿到的是"选了文件但一个字都没有"，
      而真正的答案是"这份是扫描件，要 OCR"。现在判成扫描件就自动 OCR。

    Args:
        allow_ocr:   关掉则退回老行为（抽不出字就空着，测试/比对用）。
        progress:    `f(已完成页数, 总页数)` —— 透传给 OCR（几百页要跑很久）。
        should_stop: `f() -> bool` —— 透传给 OCR：**每页问一次**，
                     停的时候**交出已识别的那些页**（半本也比没有强）。

        English:
    PDF full text (pages concatenated, with a blank line between pages).
        ★★★ 2026-10-27: **scans go through OCR automatically**. Previously, no extractable text
        meant an empty return -- the user got "file chosen, not one character", when the real
        answer was "this is a scan, it needs OCR". Now a detected scan is OCR'd automatically.
        Args:
        allow_ocr:   off means the old behaviour (empty when nothing extracts; for tests).
        progress:    `f(done, total)` -- passed through to OCR (hundreds of pages take a while).
        should_stop: `f() -> bool` -- passed through to OCR: **asked once per page**, and when
                     stopping it **hands back the pages already recognized** (half beats nothing).
    """
    pages = pdf_pages(path)
    if allow_ocr and pages:
        from booklab import ocr                                  # noqa: PLC0415
        if ocr.is_scan(pages):
            _LOG.info('%s：判为扫描件（%d 页），改走 OCR', Path(path).name,
                      len(pages))
            pages = ocr.ocr_pdf(path, progress=progress, should_stop=should_stop)
    return '\n\n'.join(t for t in pages if t.strip())


def pdf_hint(path: Path | str) -> str:
    """PDF 读不出文字时**该说的话**（区分"没装依赖"与"扫描件"）。

    ★ 这两句话必须分开：一个是"去装个包"，一个是"这份文件里根本没有字"。
      混成一句"读不出来"，用户会去装包，装完还是读不出来。
    
        English:
    What to say when PDF text can't be read (distinguish "dependency not installed" from "scan").
        ★ These two messages must be separate: one is "go install a package", the other is "this file simply has no text".
          Merged into one "can't read it", the user will go install the package, and after installing it still can't be read.
    """
    try:
        import pypdf                                              # noqa: F401
    except ImportError:
        return 'PDF 要装一个纯 Python 的解析库才能读：pip install pypdf'
    pages = pdf_pages(path)
    if not pages:
        return '这份 PDF 打不开（可能坏了，或者有密码）'
    if not any(t.strip() for t in pages):
        # ★★★ 2026-10-27：这句话原来是"要 OCR 才行，本项目不做 OCR" ——
        #   用户拿到的就是一个死胡同（他手上的书恰恰多半是扫描件）。
        #   现在扫描件会自动走 OCR，这句话只剩"OCR 也没装 / 也没读出字"两种情况。
        # [EN] ★★★ 2026-10-27: this used to say "needs OCR, this project doesn't do OCR" -- a dead
        #   end for the user (whose books are mostly scans). Scans now go through OCR automatically;
        #   this wording remains only for "OCR not installed" or "OCR read nothing".
        from booklab import ocr                                  # noqa: PLC0415
        if ocr.available():
            # ⚠ 这一句**不许说"OCR 也没读出字"** —— `pdf_hint` 自己**没有跑过 OCR**，
            #   而真正读的流程（`read_pdf_text`）会在判成扫描件之后自动 OCR。
            #   上次就是这么写的，结果界面上写着"OCR 也没读出字"，
            #   而同一份文件其实 OCR 出了六十多个字 —— 一句没跑过就说失败的假话。
            # [EN] ⚠ This must **not** say "OCR read nothing either" -- `pdf_hint` never **ran**
            # [EN] OCR itself, while the real reading path (`read_pdf_text`) OCRs automatically
            # [EN] after detecting a scan. It used to say exactly that, so the UI claimed "OCR
            # [EN] read nothing" for a file that actually OCR'd to sixty-some characters -- a claim
            # [EN] of failure made without ever trying.
            return (f'这份 PDF 有 {len(pages)} 页，但**一页都抽不出文字** ——'
                    '它是扫描件 / 图片版，会**自动用 OCR 读**（页数多会比较慢）')
        return (f'这份 PDF 有 {len(pages)} 页，但**一页都抽不出文字** ——'
                '它是扫描件 / 图片版，' + ocr.hint())
    return ''


# ══════════════════════════════════════════════════════════════
#  其它格式（2026-10-27 补：doc / wps / epub / mobi / rtf / odt / 图片）
# [EN] Other formats (added 2026-10-27: doc / wps / epub / mobi / rtf / odt / images)
#
#  ★ 每一条都要守同一个规矩：**读不出来要能说出该装什么**（见 `format_hint`），
#    不许只返回一个空字符串 —— 用户看到的是"选了文件但一个字都没有"，
#    而这既可能是"认不出格式"，也可能是"这本书本来就是空的"。
# [EN] ★ Every one of them keeps the same rule: **if it can't be read, say what to install**
#    (see `format_hint`) -- never just return an empty string. What the user sees is "file chosen,
#    not one character", which could equally mean "format not recognised" or "this book is empty".
# ══════════════════════════════════════════════════════════════

#: 每种 OLE 后缀优先用哪个 COM 程序开（本机**装了 Word 也装了 WPS**，见 2026-10-27 实测）。
#:   ★ 顺序有讲究：`.doc` 先找 Word、`.wps` 先找 WPS —— 各自"同族"的那个最稳。
#:   ⚠ WPS 的 ProgID 是 `KWps.*`（带 K），不是 `Wps.*`，写错就静默失败。
# [EN] : Which COM program to try first per OLE suffix (this machine has **both Word and WPS**,
# [EN] measured 2026-10-27). ★ Order matters: `.doc` tries Word first, `.wps` tries WPS first --
# [EN] each is most stable with its own family. ⚠ WPS ProgIDs are `KWps.*` (with the K), not
# [EN] `Wps.*` -- a typo fails silently.
_COM_PROGS: dict[str, tuple[str, ...]] = {
    '.doc': ('Word.Application', 'KWps.Application'),
    '.wps': ('KWps.Application', 'Word.Application'),
    '.et': ('KET.Application', 'Excel.Application'),
    '.dps': ('KWPP.Application', 'PowerPoint.Application'),
}


def _ole_via_com(p: Path) -> str:
    """用本机装的 Word / WPS 打开 OLE 文档，直接取正文。

    ★ 为什么优先走 COM：`.doc` / `.wps` 是**二进制复合文档**，纯 Python 没法
      正确解析（Word 的 FIB/CLX 结构），硬抽出来是乱码。本机既然装了
      Word 与 WPS，让它们自己读最准。

    ⚠ COM 三件事必须做对，否则**会残留 Office 进程**：
      ① `Visible = False`（不弹窗）；② `DisplayAlerts` 关掉（不弹"是否启用宏"）；
      ③ `finally` 里一定 `Quit()`。

        English:
    Open the OLE document with the locally installed Word / WPS and take the body text.
        ★ Why COM first: `.doc` / `.wps` are **binary compound documents**; pure Python cannot
        parse them properly (Word's FIB/CLX structure) and hard-extraction yields mojibake. With
        Word and WPS installed, letting them read it is the most accurate.
        ⚠ Three things must be right with COM or **Office processes are left behind**:
        ① `Visible = False` (no window); ② turn `DisplayAlerts` off (no "enable macros?" prompt);
        ③ always `Quit()` in `finally`.
    """
    try:
        import win32com.client as wc                             # noqa: PLC0415
    except ImportError:
        return ''
    sfx = suffix_of(p)
    for prog in _COM_PROGS.get(sfx, ('Word.Application',)):
        app = None
        try:
            app = wc.Dispatch(prog)
            for attr, val in (('Visible', False), ('DisplayAlerts', 0)):
                try:
                    setattr(app, attr, val)
                except Exception:                                # noqa: BLE001
                    pass
            text = _com_body(app, prog, p)
            if text and text.strip():
                return text
        except Exception as e:                                   # noqa: BLE001
            _LOG.info('COM %s 打不开 %s：%r', prog, p.name, e)
        finally:
            if app is not None:
                try:
                    app.Quit()
                except Exception:                                # noqa: BLE001
                    pass
    return ''


def _com_body(app, prog: str, p: Path) -> str:
    """从已打开的 COM 应用里取正文（**不同应用取法不同**，所以单独一个函数）。

        English:
    Take the body text from an already-open COM app (**each app is different**, hence its own fn).
    """
    try:
        if prog in ('Word.Application', 'KWps.Application'):
            doc = app.Documents.Open(str(p), ReadOnly=True)
            try:
                return str(doc.Content.Text or '')
            finally:
                try:
                    doc.Close(False)
                except Exception:                                # noqa: BLE001
                    pass
        if prog in ('Excel.Application', 'KET.Application'):
            wb = app.Workbooks.Open(str(p), ReadOnly=True)
            try:
                out: list[str] = []
                for sheet in wb.Worksheets:
                    try:
                        used = sheet.UsedRange
                        out.append(str(used.Text or ''))
                    except Exception:                            # noqa: BLE001
                        continue
                return '\n\n'.join(t for t in out if t.strip())
            finally:
                try:
                    wb.Close(False)
                except Exception:                                # noqa: BLE001
                    pass
        # PowerPoint / WPS 演示：按页取每个形状里的文字
        # [EN] PowerPoint / WPS presentation: take the text of every shape, slide by slide
        pres = app.Presentations.Open(str(p), ReadOnly=True,
                                      WithWindow=False)
        try:
            out = []
            for slide in pres.Slides:
                try:
                    for shape in slide.Shapes:
                        try:
                            if shape.HasTextFrame:
                                t = str(shape.TextFrame.TextRange.Text or '')
                                if t.strip():
                                    out.append(t)
                        except Exception:                        # noqa: BLE001
                            continue
                except Exception:                                # noqa: BLE001
                    continue
            return '\n\n'.join(out)
        finally:
            try:
                pres.Close()
            except Exception:                                    # noqa: BLE001
                pass
    except Exception as e:                                       # noqa: BLE001
        _LOG.info('COM 取正文失败（%s / %s）：%r', prog, p.name, e)
    return ''


def _ole_text_guess(p: Path) -> str:
    """COM 也打不开时的**最后一招**：从 OLE 流里硬抽可读文本。

    ⚠ 这是"聊胜于无"的一档：Word 二进制里正文常以 UTF-16LE 存着，
      但混着大量格式控制符 ⇒ 抽出来的东西**可能带乱码**。
      宁可给一份带噪点的正文，也不要让用户拿到"一个字都没有"。

        English:
    The **last resort** when COM won't open it either: hard-extract readable text from the OLE stream.
        ⚠ This is the "better than nothing" tier: body text in Word binaries is often stored as
        UTF-16LE, but mixed with lots of formatting control characters => the result **may contain
        mojibake**. Better to hand over a noisy body text than "not a single character".
    """
    try:
        import olefile                                           # noqa: PLC0415
        import re as _re
    except ImportError:
        return ''
    try:
        ole = olefile.OleFileIO(str(p))
    except Exception as e:                                       # noqa: BLE001
        _LOG.info('olefile 打不开 %s：%r', p.name, e)
        return ''
    chunks: list[str] = []
    try:
        for stream in ole.listdir():
            name = '/'.join(stream)
            if 'WordDocument' not in name and 'Data' not in name:
                continue
            try:
                raw = ole.openstream(stream).read()
            except Exception:                                    # noqa: BLE001
                continue
            for enc in ('utf-16-le', 'utf-8', 'gbk'):
                try:
                    txt = raw.decode(enc, errors='ignore')
                except Exception:                                # noqa: BLE001
                    continue
                # 只留"成句"的片段：连续 6 个以上的中日韩字符或可打印 ASCII
                # [EN] Keep only "sentence-like" runs: 6+ consecutive CJK or printable ASCII
                found = _re.findall(r'[\u4e00-\u9fff\u3000-\u303f]{6,}'
                                    r'|[A-Za-z][A-Za-z ,.\'"]{11,}', txt)
                chunks.extend(found)
                if len(chunks) > 4000:
                    break
            if len(chunks) > 4000:
                break
    finally:
        try:
            ole.close()
        except Exception:                                        # noqa: BLE001
            pass
    return '\n'.join(chunks)


def _looks_like_text(s: str, *, min_len: int = 12, printable: float = 0.9) -> bool:
    """硬抽的结果**像不像正文**（`_ole_text_guess` 的闸门，见那里）。

    两条门槛：① 够长（≥ `min_len` 个"成词"字符）；② 可打印率够高
    （控制字符 / 替换符占比不超过 `1 - printable`）。

        English:
    Does a hard-extracted result **look like body text** (the gate of `_ole_text_guess`, see there).
        Two thresholds: ① long enough (>= `min_len` "word-forming" characters); ② printable enough
        (control / replacement characters must not exceed a `1 - printable` share).
    """
    import unicodedata
    t = str(s or '').strip()
    if not t:
        return False
    bad = sum(1 for ch in t
              if unicodedata.category(ch)[0] == 'C' or ch == '\ufffd')
    if (bad / len(t)) > (1.0 - printable):
        return False
    return len(re.findall(r'[\u4e00-\u9fff]|[A-Za-z]', t)) >= min_len


def read_ole_text(path: Path | str) -> str:
    """旧版 Word（`.doc`）与 WPS 三件套（`.wps`/`.et`/`.dps`）→ 纯文本。

    两条路：① 本机 Word / WPS（COM，最准）；② `olefile` 硬抽（带噪点）。

        English:
    Legacy Word (`.doc`) and the WPS trio (`.wps`/`.et`/`.dps`) -> plain text.
        Two routes: ① local Word / WPS via COM (most accurate); ② `olefile` hard-extraction (noisy).
    """
    p = Path(path)
    # ★★★ 两条路的产出**都要过 `_looks_like_text` 那道闸门** ——
    #   实测（2026-10-27）一个 104 字节的坏 .doc：Word 的"文本恢复"会把它当文本打开，
    #   COM 一路顺顺当当返回 `'邢\x11?\x00\x00…'` —— **既不为空也不报错**，
    #   交给取样层就是一份"看起来有内容"的垃圾，比"读不出来"更难发现。
    #   ⇒ 闸门放在**这一处**（两条路的汇合点），不放在各条路自己里面
    #   （"同一件事一处实现"）。
    # [EN] ★★★ Both routes' output **must pass the `_looks_like_text` gate** -- measured
    #   (2026-10-27) on a 104-byte corrupt .doc: Word's "text recovery" opens it as text and COM
    #   happily returns `'邢\x11?\x00\x00…'` -- **neither empty nor an error**, so the sampling
    #   layer receives "looks like it has content" garbage, harder to notice than "can't read it".
    #   => The gate sits **here** (where both routes meet), not inside each route ("one
    #   implementation per thing").
    text = _ole_via_com(p)
    if text.strip() and _looks_like_text(text):
        return text
    text = _ole_text_guess(p)
    if text.strip() and _looks_like_text(text):
        _LOG.info('%s：COM 没读出正文，改用 olefile 硬抽（可能带噪点）', p.name)
        return text
    _LOG.warning('%s 读不出正文（COM 与 olefile 都没读到像正文的东西）', p.name)
    return ''


def _html_to_text(data) -> str:
    """HTML / XHTML / ODT 的 XML → 纯文本（去掉脚本、样式、注释）。

        English:
    HTML / XHTML / ODT XML -> plain text (drop scripts, styles, comments).
    """
    try:
        from lxml import html as lhtml                           # noqa: PLC0415
    except ImportError:
        import re as _re
        raw = data.decode('utf-8', errors='ignore') if isinstance(data, bytes) else str(data)
        return _re.sub(r'<[^>]+>', ' ', raw)
    try:
        doc = lhtml.fromstring(data)
    except Exception as e:                                       # noqa: BLE001
        _LOG.info('HTML 解析失败：%r', e)
        return ''
    try:
        for bad in doc.xpath('//script|//style|//noscript'):
            parent = bad.getparent()
            if parent is not None:
                parent.remove(bad)
    except Exception:                                            # noqa: BLE001
        pass
    try:
        parts = [str(t).strip() for t in doc.xpath('//text()')]
    except Exception as e:                                       # noqa: BLE001
        _LOG.info('取文本失败：%r', e)
        return ''
    return '\n'.join(t for t in parts if t)


def read_epub_text(path: Path | str) -> str:
    """`.epub` → 纯文本（按 OPF 的** spine 顺序**，不是 zip 里的物理顺序）。

    ★ 为什么必须按 spine 顺序：epub 里 xhtml 的文件名常常是乱的
      （`part0001.html`…），按 zip 顺序拼会**把书拆成错序**，而错序的书
      拆出来的"开头/结尾"全是错的（取样层最怕这个）。

        English:
    `.epub` -> plain text (in **spine order** from the OPF, not the physical order inside the zip).
        ★ Why spine order matters: xhtml filenames inside an epub are often arbitrary
        (`part0001.html`...); concatenating in zip order **scrambles the book**, and a scrambled
        book makes the sampled "beginning / end" wrong (the worst thing for the sampling layer).
    """
    try:
        from ebooklib import epub as _epub                       # noqa: PLC0415
        from ebooklib import ITEM_DOCUMENT                       # noqa: PLC0415
    except ImportError:
        # ⚠ 常量在 **`ebooklib` 顶层**，不在 `ebooklib.epub` 里（ebooklib 0.20 实测）。
        #   写成 `epub.ITEM_DOCUMENT` 会 `AttributeError`，而 old 版本又把它放在 epub 模块
        #   ⇒ 两处都取一遍，取不到就用字面量 9（这个值是 OPF 规范定的，不会变）。
        # [EN] ⚠ The constant lives at the **`ebooklib` top level**, not in `ebooklib.epub`
        # [EN] (measured on ebooklib 0.20). `epub.ITEM_DOCUMENT` raises `AttributeError`, while
        # [EN] older releases kept it in the epub module => try both, else fall back to the literal
        # [EN] 9 (fixed by the OPF spec, it will not change).
        try:
            import ebooklib as _el                               # noqa: PLC0415
            from ebooklib import epub as _epub                   # noqa: PLC0415
            ITEM_DOCUMENT = getattr(_el, 'ITEM_DOCUMENT', None) \
                or getattr(_epub, 'ITEM_DOCUMENT', 9)
        except ImportError:
            _LOG.warning('读 epub 要装：pip install ebooklib')
            return ''
    try:
        book = _epub.read_epub(str(Path(path)))
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('epub 打不开 %s：%r', path, e)
        return ''
    out: list[str] = []
    try:
        for item in book.get_items_of_type(ITEM_DOCUMENT):
            try:
                raw = item.get_content()
            except Exception:                                    # noqa: BLE001
                continue
            text = _html_to_text(raw)
            if text.strip():
                out.append(text)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('epub 取正文失败：%r', e)
    return '\n\n'.join(out)


def read_mobi_text(path: Path | str) -> str:
    """`.mobi` / `.azw3` → 纯文本。

    ★ `mobi` 这个库做的事是**转成 epub**，然后递归交给本文件的 `read_file`
      （走 epub 那条路）—— 自己再写一遍 html 解析就是"同一件事两处实现"
      （本项目明令禁止）。

    ⚠ 这个库的 `extract()` 有两个坑（都实测过）：
      ① **签名只有一个参数**：`extract(infile)`。网上流传的
         `extract(path, outdir)` 是别的版本，传两个参数直接 `TypeError`。
      ② 它**自己 `mkdtemp` 且从不清理**（临时目录名以 `mobiex` 开头），
         拆一批 mobi 就会在系统临时目录里堆一批垃圾 ⇒ 读完自己删。

        English:
    `.mobi` / `.azw3` -> plain text.
        ★ The `mobi` library **converts to epub**, which is then handed back to `read_file` in this
        same file (taking the epub route) -- writing another html parser here would be "the same
        thing implemented twice" (explicitly forbidden in this project).
        ⚠ This library's `extract()` has two traps (both measured):
        ① **the signature takes a single argument**: `extract(infile)`. The `extract(path, outdir)`
           form floating around belongs to another version and raises `TypeError` outright.
        ② it **`mkdtemp`s on its own and never cleans up** (temp dir names start with `mobiex`), so
           batch-splitting mobis piles garbage into the system temp dir => delete it ourselves.
    """
    try:
        from mobi import extract                                 # noqa: PLC0415
    except ImportError:
        _LOG.warning('读 mobi/azw3 要装：pip install mobi')
        return ''
    try:
        out = extract(str(Path(path)))
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('mobi 解不开 %s：%r', path, e)
        return ''
    if not out:
        return ''
    try:
        return read_file(out)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('mobi 转出来的文件读不了：%r', e)
        return ''
    finally:
        _cleanup_mobi_tmp(out)


def _cleanup_mobi_tmp(out) -> None:
    """删掉 `mobi.extract` 留下的临时目录（它自己不删 —— 见 `read_mobi_text` 的 ②）。

    ★ 只删**它造的那层**：往上找名字以 `mobiex` 开头的目录，找不到就只删文件本身 ——
      宁可留一个文件，也绝不 `rmtree` 一个来路不明的目录。

        English:
    Delete the temp dir left behind by `mobi.extract` (it never does -- see ② in `read_mobi_text`).
        ★ Only delete **the layer it created**: walk up for a directory whose name starts with
        `mobiex`; if none is found, delete just the file -- better to leave one file behind than to
        `rmtree` a directory of unknown origin.
    """
    import shutil
    p = Path(out)
    try:
        target: Path | None = None
        for cand in (p.parent, *p.parent.parents):
            if cand.name.startswith('mobiex'):
                target = cand
                break
        if target is not None:
            shutil.rmtree(target, ignore_errors=True)
        elif p.is_file():
            p.unlink(missing_ok=True)
    except Exception as e:                                       # noqa: BLE001
        _LOG.info('mobi 临时目录没删掉（不影响结果）：%r', e)


def read_rtf_text(path: Path | str) -> str:
    """`.rtf` → 纯文本（去 RTF 控制字）。老资料里还挺常见。
        English:
    `.rtf` -> plain text (strip RTF control words). Still common in older material.
    """
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as e:                                         # noqa: BLE001
        _LOG.warning('读不了 %s：%r', p, e)
        return ''
    text = raw.decode('utf-8', errors='ignore')
    if text.count('\ufffd') > len(text) * 0.1:      # utf-8 解出一堆替换符 ⇒ 多半是 gbk
        text = raw.decode('gbk', errors='ignore')
    text = text.replace('\\par', '\n').replace('\\line', '\n')
    # 去掉 {\…} 里的控制字与不可见字符
    # [EN] Drop control words and invisible characters inside {\…}
    text = re.sub(r'\\[a-zA-Z]+-?\d*\s?', ' ', text)
    text = re.sub(r'[{}]', '', text)
    text = re.sub(r'\\\'[0-9a-fA-F]{2}', '', text)
    return '\n'.join(ln.strip() for ln in text.splitlines() if ln.strip())


def read_odt_text(path: Path | str) -> str:
    """`.odt` → 纯文本（它就是个 zip，正文在 `content.xml`）。
        English:
    `.odt` -> plain text (it is a zip; the body lives in `content.xml`).
    """
    import zipfile
    try:
        with zipfile.ZipFile(str(Path(path))) as z:
            data = z.read('content.xml')
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('odt 打不开 %s：%r', path, e)
        return ''
    return _html_to_text(data)


def _read_image_text(path: Path | str) -> str:
    """一张图 → 文本（**只能 OCR**）。
        English:
    One image -> text (**OCR only**).
    """
    from booklab import ocr                                      # noqa: PLC0415
    if not ocr.available():
        _LOG.warning('%s 是图片，%s', Path(path).name, ocr.hint())
        return ''
    return ocr.ocr_image(str(Path(path)))


def format_hint(path: Path | str) -> str:
    """这个文件**读不出来时该说的话**（按格式分开）。

    ★ 与 `pdf_hint` 是同一条规矩：
      "该装一个包"和"这份文件里根本没有字"**必须分开说** ——
      混成一句"读不出来"，用户会去装包，装完还是读不出来。

        English:
    What to say when this file **can't be read** (worded per format).
        ★ Same rule as `pdf_hint`: "install a package" and "this file simply has no text" **must be
        worded separately** -- merged into "can't read it", the user installs the package and it
        still doesn't work.
    """
    p = Path(path)
    k = kind_of(p)
    if k == 'ole':
        return (f'{p.suffix} 是旧版 Word / WPS 的二进制格式：本机装了 Word 与 WPS 时会'
                '自动让它们读；两个都打不开时才会用 olefile 硬抽（可能带噪点）。'
                '若一个字都没有，可以先用 Word 另存为 .docx 或 .txt 再拆')
    if k == 'epub':
        return '读 .epub 要装：pip install ebooklib'
    if k == 'mobi':
        return '读 .mobi / .azw3 要装：pip install mobi'
    if k == 'image':
        from booklab import ocr                                  # noqa: PLC0415
        # ⚠ 与 `pdf_hint` 同一条纪律：这里**没有跑过 OCR**，就不许说"OCR 也没读出字"。
        # [EN] ⚠ Same rule as `pdf_hint`: OCR has **not been run here**, so it must not claim
        # [EN] "OCR read nothing either".
        if ocr.available():
            return (f'{p.name} 是图片（没有文字层），会**用 OCR 读**'
                    '（一页约 1~3 秒，几百页要跑一会儿）')
        return ocr.hint()
    if k == 'pdf':
        return pdf_hint(p)
    return ''


# ══════════════════════════════════════════════════════════════
#  一个文件夹
# [EN] One folder
# ══════════════════════════════════════════════════════════════
def read_dir(root: Path | str) -> list[tuple[str, str]]:
    """读一个文件夹 → `[(文件显示名, 正文), …]`（自然序，空内容的跳过）。
        English:
    Read a folder → `[(file display name, body), …]` (natural order, skip empty content).
    """
    out: list[tuple[str, str]] = []
    for f in list_files(root):
        text = _clip_len(read_file(f))
        if text.strip():
            out.append((f.stem, text))
    return out


def _clip_len(s: str, cap: int = MAX_FILE_CHARS) -> str:
    t = str(s or '')
    return t if len(t) <= cap else t[:cap]
