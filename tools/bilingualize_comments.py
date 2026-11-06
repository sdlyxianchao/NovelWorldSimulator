# -*- coding: utf-8 -*-
"""把源码里的**中文注释**逐条补上英文译文（双语化）。
Give every Chinese comment in the source tree an English twin.

产物形态（the shape it produces）
---------------------------------
**块级双语** —— 一整段中文之后跟一整段英文，而不是"中英中英"逐行交错：

    # 演员的身份由角色卡决定，这一份只管"演员这个工种"怎么干活。
    # 换一本书，这一份也该是对的。
    # [EN] An actor's identity comes from the character card; this file only
    # [EN] covers how the trade of "actor" itself works.
    # [EN] It should stay correct across books.

★ 为什么是**块级**而不是逐行：本项目的注释多半是**一写一大段**（讲一个坑、
  一段来龙去脉）。逐行交错会变成"中文一句、英文一句、中文一句…"，
  读者两边都读不连贯。块级 = 中文整段读完再读英文整段。

★ `docstring` 也一并处理（它是最值钱的那部分注释）：在中文正文之后追加英文段，
  **闭引号留在原位**，所以引号风格、缩进、后面的代码都不受影响。

★ 三条安全纪律（动的是全项目 450+ 个源文件，必须守住）
  1. **只碰注释与 docstring 的正文** —— 注释位置用 `tokenize`（不是正则：
     字符串里的 `#` 不是注释）、docstring 位置用 `ast`。**代码一个字符不动**。
  2. **写前备份 + 原子写** —— `<文件>.bak-bilingual`（已存在就不覆盖），
     并且**保住原来的行尾**（CRLF 不能变成 LF）。
  3. **可中断续跑** —— 跑过的文件记在 `.bilingual_done.json` 里。
     也可以 `--undo` 把某个文件从备份整份还原回去。

用法（usage）
-------------
::

    python tools/bilingualize_comments.py --list              # 看有哪些文件要处理
    python tools/bilingualize_comments.py --dry-run            # 只看统计（不调模型）
    python tools/bilingualize_comments.py --paths a.py --apply  # 试一个文件
    python tools/bilingualize_comments.py --apply --jobs 6      # 全量
    python tools/bilingualize_comments.py --undo a.py           # 从备份还原

⚠ 真翻译要**调模型**（花钱）。走 `cheap` 档、`purpose='bilingualize'`，
  账记进 `usage.db`，所以事后查得到这一趟花了多少。

Add an English translation line-by-line to the **Chinese comments** in the source
(bilingualize).
Give every Chinese comment in the source tree an English twin.
Product shape (the shape it produces)
---------------------------------
**Block-level bilingual** —— a whole Chinese paragraph followed by a whole English paragraph,
rather than "Chinese-English-Chinese-English" interleaved line by line:
    # An actor's identity is determined by the character card; this file only cares about how "the actor trade" does its work.
    # Switch to another book, and this file should still be correct.
    # [EN] An actor's identity comes from the character card; this file only
    # [EN] covers how the trade of "actor" itself works.
    # [EN] It should stay correct across books.
★ Why **block-level** rather than line-by-line: this project's comments are mostly **written in
big chunks at a time** (explaining a pitfall,
  the whole story). Interleaving line by line would produce "one Chinese sentence, one English sentence, one Chinese sentence...",
  and the reader can't read either side coherently. Block-level = read the whole Chinese paragraph, then the whole English paragraph.
★ `docstring` is handled the same way (it's the most valuable part of the comments): append the
English paragraph after the Chinese body,
  **the closing quote stays in place**, so quote style, indentation, and the code after it are unaffected.
★ Three safety rules (this touches 450+ source files across the whole project, so they must be
held)
  1. **Only touch the body of comments and docstrings** — use `tokenize` for comment positions (not regex:
     a `#` inside a string is not a comment), and `ast` for docstring positions. **Not a single character of code is changed**.
  2. **Back up before writing + atomic write** — `<file>.bak-bilingual` (do not overwrite if it already exists),
     and **preserve the original line endings** (CRLF must not become LF).
  3. **Interruptible and resumable** — files already processed are recorded in `.bilingual_done.json`.
     You can also use `--undo` to fully restore a file from its backup.
Usage
-------------
::
    python tools/bilingualize_comments.py --list              # see which files need processing
    python tools/bilingualize_comments.py --dry-run            # just view stats (no model calls)
    python tools/bilingualize_comments.py --paths a.py --apply  # try one file
    python tools/bilingualize_comments.py --apply --jobs 6      # full run
    python tools/bilingualize_comments.py --undo a.py           # restore from backup
⚠ Real translation requires **calling the model** (costs money). Use the `cheap` tier,
`purpose='bilingualize'`,
  and the cost is recorded in `usage.db`, so you can look up afterward how much this run cost.
The py files to process (stable ordering, convenient for batching and resuming). / Files to
process.

English:
Append an English translation to every **Chinese comment** in the source (bilingualize).
Give every Chinese comment in the source tree an English twin.
Product shape (the shape it produces)
---------------------------------
**Block-level bilingual** — a whole Chinese paragraph followed by a whole English paragraph,
rather than "Chinese-English-Chinese-English" interleaved line by line:
    # An actor's identity is determined by the character card; this file only cares about how "the actor trade" does its work.
    # Switch to another book, and this file should still be correct.
    # [EN] An actor's identity comes from the character card; this file only
    # [EN] covers how the trade of "actor" itself works.
    # [EN] It should stay correct across books.
★ Why **block-level** rather than line-by-line: this project's comments are mostly **written in
big chunks at a time** (explaining a pitfall,
  the whole story). Interleaving line by line would turn into "one Chinese sentence, one English sentence, one Chinese sentence...",
  and the reader can't read either side coherently. Block-level = read the whole Chinese paragraph, then the whole English paragraph.
★ `docstring` is handled too (it's the most valuable part of the comments): after the Chinese
body, append the English paragraph,
  **the closing quote stays in place**, so the quote style, indentation, and the code after it are unaffected.
★ Three safety disciplines (this touches 450+ source files across the project, so they must be
upheld)
1. **Only touch the body of comments and docstrings** — use `tokenize` for comment positions
(not regex:
  a `#` inside a string is not a comment), and `ast` for docstring positions. **Do not change a single character of code**.
     2. **Back up before writing + atomic write** — `<file>.bak-bilingual` (do not overwrite if it already exists),
  and **preserve the original line endings** (CRLF must not become LF).
     3. **Interruptible and resumable** — processed files are recorded in `.bilingual_done.json`.
  You can also `--undo` to fully restore a file from its backup.
Usage
-------------
::
python tools/bilingualize_comments.py --list              # See which files need processing
    python tools/bilingualize_comments.py --dry-run            # Statistics only (no model calls)
    python tools/bilingualize_comments.py --paths a.py --apply  # Try one file
    python tools/bilingualize_comments.py --apply --jobs 6      # Full run
    python tools/bilingualize_comments.py --undo a.py           # Restore from backup
⚠ Real translation requires **calling the model** (costs money). Use the `cheap` tier,
`purpose='bilingualize'`,
and log the cost to `usage.db`, so you can look up afterwards how much this run cost.
Add an English translation line-by-line to the **Chinese comments** in the source
(bilingualize).
Give every Chinese comment in the source tree an English twin.
Product shape (the shape it produces)
---------------------------------
**Block-level bilingual** — a whole Chinese paragraph followed by a whole English paragraph,
rather than "Chinese-English-Chinese-English" interleaved line by line:
# An actor's identity is determined by the character card; this file only cares about how "the
actor trade" does its work.
    # Switch to another book, and this file should still be correct.
    # [EN] An actor's identity comes from the character card; this file only
    # [EN] covers how the trade of "actor" itself works.
    # [EN] It should stay correct across books.
    ★ Why **block-level** rather than line-by-line: this project's comments are mostly **written in
big chunks at a time** (explaining a pitfall,
the whole story). Interleaving line by line would produce "one Chinese sentence, one English
sentence, one Chinese sentence...",
  and the reader can't read either side coherently. Block-level = read the whole Chinese paragraph, then the whole English paragraph.
  ★ `docstring` is handled the same way (it's the most valuable part of the comments): append the
English paragraph after the Chinese body,
**the closing quote stays in place**, so quote style, indentation, and the code after it are
unaffected.
★ Three safety rules (this touches 450+ source files across the whole project, so they must be
held)
  1. **Only touch the body of comments and docstrings** — use `tokenize` for comment positions (not regex:
     a `#` inside a string is not a comment), and `ast` for docstring positions. **Not a single character of code is changed**.
  2. **Back up before writing + atomic write** — `<file>.bak-bilingual` (do not overwrite if it already exists),
     and **preserve the original line endings** (CRLF must not become LF).
  3. **Interruptible and resumable** — files already processed are recorded in `.bilingual_done.json`.
     You can also use `--undo` to fully restore a file from its backup.
Usage
-------------
::
    python tools/bilingualize_comments.py --list              # see which files need processing
    python tools/bilingualize_comments.py --dry-run            # just view stats (no model calls)
    python tools/bilingualize_comments.py --paths a.py --apply  # try one file
    python tools/bilingualize_comments.py --apply --jobs 6      # full run
    python tools/bilingualize_comments.py --undo a.py           # restore from backup
⚠ Real translation requires **calling the model** (costs money). Use the `cheap` tier,
`purpose='bilingualize'`,
  and the cost is recorded in `usage.db`, so you can look up afterward how much this run cost.
The py files to process (stable ordering, convenient for batching and resuming). / Files to
process.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import io
import json
import re
import sys
import time
import tokenize
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

DONE_FILE = APP / ".bilingual_done.json"
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
EN_MARK = "# [EN] "
#: docstring 里英文段的**标记行** —— 幂等就靠认它。
#: （注释块有 `# [EN]` 前缀可认；docstring 里放不了注释，
#:   所以用一个独立成行的小标题当地标。）
# [EN] : The **marker line** in the English paragraph of a docstring — idempotency depends on
# [EN] recognizing it.
# [EN] : (Comment blocks can be recognized by the `# [EN]` prefix; you can't put comments inside a
# [EN] docstring,
# [EN] :   so use a small standalone heading line as a landmark.)
EN_SECTION = "English:"

#: 不处理的目录（**理由要写清**，不然下一个人会以为是漏了）。
#: · `.venv` / `__pycache__` / `node_modules` —— 第三方，不是我们的代码
#: · `novelservices/MuMuAINovel/backend/` —— **上游 GPL 项目的检出**：
#:   改它的注释会污染 `git status`，也会让 `git pull` 上游新版处处冲突。
#:   （本项目自写的 `nws_paths.py` / `mumu_client.py` / `quality/` /
#:     顶层那些脚本 **不在**这一条里，照常处理。）
# [EN] : Directories not processed (**the reason must be stated clearly**, otherwise the next person
# [EN] will think it was missed).
# [EN] : · `.venv` / `__pycache__` / `node_modules` —— third-party, not our code
# [EN] : · `novelservices/MuMuAINovel/backend/` —— **checkout of the upstream GPL project**:
# [EN] : modifying its comments pollutes `git status`, and makes `git pull` of upstream conflict
# [EN] everywhere.
# [EN] :   (This project's own `nws_paths.py` / `mumu_client.py` / `quality/` /
# [EN] :     and the top-level scripts are **not** covered by this rule; process them as usual.)
SKIP_PARTS = {".venv", "__pycache__", "node_modules", ".git", "assets",
              "logs", "output", "exports", "packages"}
SKIP_PREFIX = ("novelservices/MuMuAINovel/backend",)


def iter_files() -> list[Path]:
    """要处理的 py 文件（排序稳定，便于分批与续跑）。/ Files to process.
    py files to process (stable sort, convenient for batching and resuming). / Files to process.
    
    py files to process (stable sort, convenient for batching and resuming). / Files to process.
        py files to process (stable sort, convenient for batching and resuming). / Files to process.
    
        English:
    py files to process (stable sort, convenient for batching and resuming). / Files to process.
        py files to process (stable sort, convenient for batching and resuming). / Files to process.
        py files to process (stable sort, convenient for batching and resuming). / Files to process.
            py files to process (stable sort, convenient for batching and resuming). / Files to process.
    """
    out: list[Path] = []
    for p in sorted(APP.rglob("*.py")):
        rel = p.relative_to(APP).as_posix()
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        if rel.startswith(SKIP_PREFIX):
            continue
        out.append(p)
    return out


# ══════════════════════════════════════════════════════════════════
#  单元：注释块 / docstring
# [EN] Unit: comment block / docstring
# ══════════════════════════════════════════════════════════════════


class Unit:
    """一个待译单元：要么是一个**注释块**，要么是一段 **docstring**。
    One unit to translate: either a contiguous comment block or a docstring.
    
    One unit to translate: either a **comment block** or a **docstring**.
        One unit to translate: either a contiguous comment block or a docstring.
    
        English:
    One unit to translate: either a **comment block** or a **docstring**.
        One unit to translate: either a contiguous comment block or a docstring.
        One unit to translate: either a **comment block** or a **docstring**.
            One unit to translate: either a contiguous comment block or a docstring.
    """

    __slots__ = ("kind", "rows", "indent", "texts", "end_col", "quote", "raw")

    def __init__(self, kind: str, rows: list[int], indent: str,
                 texts: list[str], *, end_col: int = -1, quote: str = "",
                 raw: bool = False) -> None:
        self.kind = kind          # 'comment' | 'doc'
        self.rows = rows          # 涉及的行号（0-based）
        self.indent = indent      # 插入译文时用的缩进
        self.texts = texts        # 逐行正文（翻译的输入 / 写回时按行配对）
        self.end_col = end_col    # 仅 docstring：闭引号之后的列
        self.quote = quote        # 仅 docstring：`"""` 还是 `'''`
        #  ★ 仅 docstring：这一段是不是 **raw 字符串**（`r"""…"""`）。
        #    raw 里反斜杠**不转义**，所以插入译文时**不能**把 `\` 变成 `\\`；
        #    普通 docstring 里则**必须**转义（否则 `…\User Pinned\…` 里的 `\U`
        #    会变成"截断的 Unicode 转义" ⇒ 整个文件 SyntaxError，实测坏了 2 个）。
        # [EN] Line numbers involved (0-based)
        # [EN] Indentation used when inserting the translation
        # [EN] Line-by-line body (input to translation / paired line-by-line when writing back)
        # [EN] Docstring only: column after the closing quote
        # [EN] Docstring only: `"""` or `'''`
        # [EN] ★ Docstring only: is this segment a **raw string** (`r"""…"""`).
        # [EN] In raw, backslashes are **not escaped**, so when inserting the translation you **must not** turn
        # [EN] `\` into `\\`;
        # [EN] in a normal docstring you **must** escape (otherwise the `\U` in `…\User Pinned\…`
        # [EN] becomes a "truncated Unicode escape" ⇒ the whole file gets a SyntaxError; measured: broke 2).
        self.raw = raw


def collect(path: Path) -> tuple[list[str], list[Unit]]:
    """一个文件里**需要翻译**的单元。返回 `(源码行, 单元)`。

    ★ 注释位置用 `tokenize` 而不是正则：正则会把字符串里的 `#` 当成注释
      （`x = "a # b"` 就是这么炸的）。tokenize 给的是**语法级**的位置。
      Tokenizer beats regex here — a `#` inside a string literal is not a
      comment.
    
        English:
    The units in a file that **need translation**. Returns `(source lines, units)`.
        ★ Use `tokenize` instead of regex for comment positions: regex would treat a `#` inside a string as a comment
          (that is exactly how `x = "a # b"` blows up). What tokenize gives is a **syntax-level** position.
          Tokenizer beats regex here — a `#` inside a string literal is not a
          comment.
    """
    src = path.read_text(encoding="utf-8")
    lines = src.split("\n")
    units: list[Unit] = []

    # ── ① 注释块 ──
    # [EN] ── ① Comment block ──
    rows: list[tuple[int, int, str]] = []       # (row, col, body)
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type != tokenize.COMMENT:
                continue
            row = t.start[0] - 1
            if row >= len(lines):
                continue
            raw = t.string
            if raw.startswith(EN_MARK):
                continue                        # 已经是译文行 → 跳过（幂等）
                # [EN] Already a translated line → skip (idempotent)
            body = raw.lstrip("#").strip()
            if body and CJK.search(body):
                rows.append((row, t.start[1], body))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return lines, units                     # 语法有问题的文件不动（不冒险）
    # 把"行号连续"的注释并成一块（块级双语就是靠这一步）
        # [EN] Files with syntax problems are left alone (no risk-taking)
        # [EN] Merge comments with "consecutive line numbers" into one block (block-level bilingual output
        # [EN] relies on this step)
    cur: list[tuple[int, int, str]] = []
    blocks: list[list[tuple[int, int, str]]] = []
    for item in rows:
        if cur and item[0] != cur[-1][0] + 1:
            blocks.append(cur)
            cur = []
        cur.append(item)
    if cur:
        blocks.append(cur)
    for blk in blocks:
        #  ★★ **幂等：这一块已经译过了就跳过**。
        #    判据 = 块尾的**下一行**是一条 `# [EN]`（工具就是插在那儿）。
        #    ⚠ 这一条**必须**有（实测踩到）：只靠"跳过 `# [EN]` 开头的行"
        #      是不够的 —— 中文原行**当然还在**，所以重跑时它会被**再收一次**，
        #      于是同一个块会**再追加一遍译文**（跑几遍就是几段）。
        #      判据 D4 就是为此立的碑。
        # [EN] ★★ **Idempotency: if this block has already been translated, skip it.**
        # [EN] Criterion = the **next line** after the block tail is a `# [EN]` (that's where the tool inserts
        # [EN] it).
        # [EN] ⚠ This one **must** be present (learned the hard way): relying only on "skip lines starting with
        # [EN] `# [EN]`"
        # [EN] is not enough -- the original Chinese line is **of course still there**, so on a rerun it gets
        # [EN] **collected again**,
        # [EN] and thus the same block gets **appended with the translation again** (N runs = N copies).
        # [EN] Criterion D4 was established as a monument for this.
        nxt = blk[-1][0] + 1
        if nxt < len(lines) and lines[nxt].lstrip().startswith("# [EN]"):
            continue
        units.append(_mk_comment(blk, lines))

    # ── ② docstring ──
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return lines, units
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node, clean=False)
        if not doc or not CJK.search(doc):
            continue
        #  ★★ **幂等：已经译过的 docstring 不要再译一遍**。
        #    判据 = 末尾连着 ≥2 行都不含中文（我插入的英文段就在闭引号之前）。
        #    ⚠ 这条不写会出事（实测）：一个 docstring 只要**同时**含中文和英文，
        #      `CJK.search(doc)` 就仍然为真 ⇒ 每次跑都**再追加一段英文**，
        #      跑几遍就是几段。注释块有 `# [EN]` 前缀天然幂等，
        #      **docstring 没有前缀，只能靠这条判据**。
        # [EN] ★★ **Idempotency: do not translate an already-translated docstring again**.
        # [EN] Criterion = ≥2 consecutive lines at the end contain no Chinese (the English segment I inserted
        # [EN] sits right before the closing quote).
        # [EN] ⚠ Not writing this will cause trouble (measured): as long as a docstring contains **both**
        # [EN] Chinese and English,
        # [EN] `CJK.search(doc)` is still true ⇒ every run **appends another English segment**,
        # [EN] run it a few times and you get several segments. Comment blocks have the `# [EN]` prefix so they
        # [EN] are naturally idempotent,
        # [EN] **docstrings have no prefix and can only rely on this criterion**.
        #  ★★ **幂等：已经译过的 docstring 不要再译一遍** —— **认 `EN_SECTION` 标记**。
        #    ⚠ 这里**不能**用"末尾两行不含中文"当判据（第一版就是那么写的，后来被
        #      `_usable` 的放宽打破）：译文允许保留中文专有名词（`选角表.md` 这类），
        #      于是"末尾含中文"**永远为真** ⇒ 每跑一轮就**再追加一段英文**，
        #      实测把 50 个文件的 docstring 撑到 587 行（每段重复 4 遍）。
        #      标记行是**内容里看得见的地标**，跟"译文里有没有中文"无关。
        # [EN] ★★ **Idempotency: do not re-translate a docstring that has already been translated** —
        # [EN] **recognize the `EN_SECTION` marker**.
        # [EN] ⚠ Here you **cannot** use "the last two lines contain no Chinese" as the criterion (that's how
        # [EN] the first version was written, and it was later
        # [EN] broken by the loosening of `_usable`): translations are allowed to keep Chinese proper nouns
        # [EN] (things like `选角表.md`),
        # [EN] so "the tail contains Chinese" is **always true** ⇒ each run **appends another English
        # [EN] paragraph**,
        # [EN] and in practice this blew up the docstrings of 50 files to 587 lines (each paragraph repeated 4
        # [EN] times).
        # [EN] The marker line is a **landmark visible in the content**, unrelated to "whether the translation
        # [EN] contains Chinese".
        #    A marker line, not a "looks like English" heuristic: the latter broke
        #    as soon as translations were allowed to keep Chinese nouns.
        _dl = [x for x in doc.split("\n") if x.strip()]
        if any(x.strip() == EN_SECTION for x in doc.split("\n")):
            continue
        body0 = node.body[0]
        val = body0.value                     # ast.Constant
        if not isinstance(val, ast.Constant) or not isinstance(val.value, str):
            continue
        end_col = val.end_col_offset
        end_row = val.end_lineno - 1
        #  ★ 这一段是不是 **raw 字符串**（`r"""…"""`）？判断错任一边，
        #    文件都会语法坏掉（见 `render()` 里那段转义说明）。
        #    ⚠ 同样按**字节**切（`col_offset` 是字节偏移）。
        # [EN] ★ Is this segment a **raw string** (`r"""…"""`)? Get it wrong either way,
        # [EN] and the file's syntax breaks (see the escape explanation in `render()`).
        # [EN] ⚠ Also slice by **bytes** (`col_offset` is a byte offset).
        _hb = lines[val.lineno - 1].encode("utf-8")[:val.col_offset]
        is_raw = _hb.decode("utf-8", "replace").rstrip().endswith(("r", "R"))
        #  ★★ `ast` 的行列偏移是 **UTF-8 字节偏移**，不是字符偏移！
        #    中文 docstring 按字符切会切错位 —— 实测：38 个字符的行报
        #    `end_col=94`，于是 `line[:94]` 把**整行**拿走、闭引号被吃掉，
        #    整个 `"""` 不闭合 ⇒ 文件语法坏掉（`ast.parse` 报在很远的地方）。
        #    所以这里一律**先 encode 再按字节切**。
        # [EN] ★★ `ast`'s row/column offsets are **UTF-8 byte offsets**, not character offsets!
        # [EN] Slicing a Chinese docstring by characters will slice at the wrong position —— measured: for a
        # [EN] 38-character line it reports
        # [EN] `end_col=94`, so `line[:94]` takes the **entire line** and the closing quote gets eaten,
        # [EN] the whole `"""` never closes ⇒ the file's syntax breaks (`ast.parse` reports it far away).
        # [EN] So here always **encode first, then slice by bytes**.
        _lb = lines[end_row].encode("utf-8")
        tail3 = _lb[max(0, end_col - 3):end_col].decode("utf-8", "replace")
        quote = "'''" if tail3 == "'''" else '"""'
        indent = re.match(r"[ \t]*", lines[val.lineno - 1]).group(0)
        units.append(Unit("doc", [end_row], indent, doc.split("\n"),
                          end_col=end_col, quote=quote, raw=is_raw))
    return lines, units


def _mk_comment(rows: list[tuple[int, int, str]], lines: list[str]) -> Unit:
    """把连续几行注释并成一个块。/ Merge contiguous comment lines into one unit.
    Merge contiguous comment lines into one unit. / Merge contiguous comment lines into one unit.
    
    Merge contiguous comment lines into one block. / Merge contiguous comment lines into one unit.
        Merge contiguous comment lines into one unit. / Merge contiguous comment lines into one unit.
    
        English:
    Merge contiguous comment lines into one unit.
        Merge contiguous comment lines into one unit.
        Merge contiguous comment lines into one block.
            Merge contiguous comment lines into one unit.
    """
    indent = re.match(r"[ \t]*", lines[rows[0][0]]).group(0)
    return Unit("comment", [r for r, _c, _b in rows], indent,
                [b for _r, _c, b in rows])


# ══════════════════════════════════════════════════════════════════
#  翻译 / translate
# [EN] Translate / translate
# ══════════════════════════════════════════════════════════════════

_PROMPT = """\
You translate Chinese comments in a Python codebase into English.

Input: a numbered list of comment lines (they come from contiguous comment
paragraphs and docstrings). Output: a JSON **object** whose keys are those same
numbers **as strings** and whose values are the English translations, e.g.
{"0": "First line.", "1": "Second line."}.

Why an object and not an array: line-for-line correspondence is the whole point
here. If an array comes back one item short, every following line shifts by one
and the translation lands on the WRONG line. With explicit keys a missing line
simply stays missing and nothing shifts.

Hard rules:
1. Output **only** the JSON object. No prose, no code fence, no explanation.
2. Include every number you translated, using the same numbers as the input.
   Never merge two input lines into one value.
3. These are **comments in source code**, read by programmers. Be technical,
   specific and terse. Do not add enthusiasm, do not explain, do not invent
   examples that were not there.
4. Keep identifiers, file paths, function names, config keys, numbers and proper
   nouns **exactly as they are** (e.g. `crew/catalog.py`, `RunLoop`, `MOCK_LLM`,
   `SET_W`, `Flet`). If a Chinese string is a real folder/file name
   (like `第N次模拟`), keep it as-is.
5. Convert Chinese full-width punctuation to ASCII where it makes sense
   （，→ ,  。→ .  ：→ :  ；→ ;  （）→ ()  「」→ ""), but KEEP box-drawing
   characters (═ ─ │ ├ └ ┌ ┐ ┼ ◆ ★) and emoji as they are.
6. Keep a leading marker if the Chinese line starts with one: ⚠ ★ · ① 、 etc.
   Keep the same marker at the start of the translation.
7. If a line is already English, or is pure punctuation/box-drawing, return it
   **unchanged**.

Input lines ({n} in total):
{lines}"""


async def translate(texts: list[str], *, batch: int = 70) -> list[str]:
    """把一批中文注释译成英文（分批送，长文件不会顶到上限）。
    Translate a batch of comment lines; chunked so long files stay in budget.
    
    Translate a batch of Chinese comments into English (sent in batches, so long files won't hit the
    limit).
        Translate a batch of comment lines; chunked so long files stay in budget.
    
        English:
    Translate a batch of Chinese comments into English (sent in batches, so long files won't hit the
    limit).
        Translate a batch of comment lines; chunked so long files stay in budget.
        Translate a batch of Chinese comments into English (sent in batches, so long files won't hit the
        limit).
            Translate a batch of comment lines; chunked so long files stay in budget.
    """
    #  ★★ 这里必须用 `util.text.fill`，**不能**用 `str.format` ——
    #    提示词里内嵌了 JSON 示例 `{"0": ...}`，`str.format` 会把 `"0"`
    #    当成字段名，直接 `KeyError: '"0"'`。
    #    （`util/text.py` 的 `fill()` 注释里早就写了这条，我还是踩了一遍。）
    # [EN] ★★ Here you must use `util.text.fill`, and **must not** use `str.format` ——
    # [EN] the prompt has an embedded JSON example `{"0": ...}`, and `str.format` will treat `"0"`
    # [EN] as a field name, directly raising `KeyError: '"0"'`.
    # [EN] (The comment on `fill()` in `util/text.py` already documented this, and I still stepped in it.)
    #    Use `fill`, not `str.format`: the prompt embeds a JSON example.
    from util.text import fill
    out: list[str] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        numbered = "\n".join(f"{n}. {t}" for n, t in enumerate(chunk))
        prompt = fill(_PROMPT, n=len(chunk), lines=numbered)
        out.extend(await _ask(prompt, len(chunk)))
    return out


async def _ask(prompt: str, n: int) -> list[str]:
    """问一次模型（失败就**原样退回空**，绝不因为翻译失败弄坏代码）。
    One model call; on failure return blanks so the caller skips those lines.

    ★ 收的是 **`{编号: 译文}` 对象**而不是数组 —— 见提示词里那段说明：
      数组缺一条会让**后面每一条都错位**（译文贴到错误的行上：实测出现过
      "docstring 第 1 项丢了第二行、第 2 项贴上了第 1 项的尾巴"），
      对象则缺哪条就哪条空着，**不会平移**。
    
    Ask the model once (on failure, **return blanks as-is**, never break the code because
    translation failed).
        One model call; on failure return blanks so the caller skips those lines.
        ★ What's received is a **`{index: translation}` object**, not an array — see the explanation in the prompt:
          an array missing one item causes **every following item to be misaligned** (translations land on the wrong lines: in practice we've seen
          "docstring item 1 lost its second line, item 2 got item 1's tail appended"),
          whereas with an object, whichever item is missing just stays blank, **no shifting**.
    
        English:
    One model call; on failure **return blanks as-is**, never break the code because translation
    failed.
        One model call; on failure return blanks so the caller skips those lines.
        ★ What's received is a **`{index: translation}` object**, not an array — see the explanation in the prompt:
          an array missing one item causes **every following item to be misaligned** (translations land on the wrong lines: in practice we've seen
          "docstring item 1 lost its second line, item 2 got item 1's tail appended"),
          whereas with an object, whichever item is missing just stays blank, **no shifting**.
        Ask the model once (on failure, **return blanks as-is**, never break the code because
        translation failed).
            One model call; on failure return blanks so the caller skips those lines.
            ★ What's received is a **`{index: translation}` object**, not an array — see the explanation in the prompt:
              an array missing one item causes **every following item to be misaligned** (translations land on the wrong lines: in practice we've seen
              "docstring item 1 lost its second line, item 2 got item 1's tail appended"),
              whereas with an object, whichever item is missing just stays blank, **no shifting**.
    """
    from llm.replies import ask
    from llm.router import llm
    await llm.ensure_started()
    rep = await ask(
        "cheap",
        [{"role": "user", "content": prompt}],
        purpose="bilingualize",
        want=dict,
        max_tokens=min(16000, max(2000, n * 160)),
        temperature=0.1,
        retry=True,
        no_think=True,              # 纯翻译是"结论型"活儿，不需要想
        # [EN] Pure translation is a "conclusion-type" job, no thinking needed
        default={})
    m = rep.value if isinstance(rep.value, dict) else {}
    if not m:
        return [None] * n
    return [m.get(str(i), m.get(i)) for i in range(n)]


# ══════════════════════════════════════════════════════════════════
#  写回 / write back
# [EN] Write back / write back
# ══════════════════════════════════════════════════════════════════


def _wrap(en: str, width: int = 96) -> list[str]:
    """长译文折行（按词折，保持可读）。/ Wrap a long translation on words.
    Wrap a long translation on words (wrap by word, keeping it readable). / Wrap a long translation
    on words.
    
        English:
        Wrap a long translation on words (wrap by word, keeping it readable). / Wrap a long translation
        on words.
    """
    words, cur, out = en.split(), "", []
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return out or [""]


def _usable(en: object) -> str:
    """这条译文能不能用？/ Is this translation usable?

    ★★ 判据是"**基本上译成了英文**"，而不是"一个中文字都没有"。
      （第一版要求"绝对不含中文"，实测代价很大：提示词里明确允许保留
       **真正的中文专有名词**（`第N次模拟`、`示例书` 这类文件夹名），
       于是那 1.2% 的译文被判"翻不干净"丢掉 ⇒ 留下 363 个块没译文。）
      现在的口径：**中文字数 ≥ 4 且明显多于英文词数**（cn*2 > en_words）
      ⇒ 才算"没翻"；少量专有名词照收。

    ★★ The rule is "**mostly translated into English**", not "contains zero
    Chinese characters": the prompt explicitly allows keeping real Chinese
    proper nouns, so a strict check threw away 1.2% of good translations.
    
        English:
        ★★ The rule is "**mostly translated into English**", not "contains zero
        Chinese characters": the prompt explicitly allows keeping real Chinese
        proper nouns, so a strict check threw away 1.2% of good translations.
    """
    s = str(en or "").strip()
    if not s:
        return ""
    cn = len(CJK.findall(s))
    if not cn:
        return s
    en_words = len(re.findall(r"[A-Za-z]{2,}", s))
    #  ★ 口径 = "**整行几乎全是中文**"才算没翻。
    #    ⚠ 别用"中文字数 vs 英文词数"比（第一版就是那么比）：本项目大量注释是
    #      **短句 + 中文示例**（`` `人物[0].性格` 的路径语法 ``、`写 已发生故事线.md。`），
    #      译文天然是"几个英文词 + 一串中文专有名词"，一比就被误杀 ——
    #      实测因此留下 11 行**永远补不上**的缺口，而模型其实译得没问题。
    # [EN] ★ Criterion = only lines that are "**almost entirely Chinese**" count as untranslated.
    # [EN] ⚠ Don't compare "Chinese character count vs English word count" (the first version did that): in
    # [EN] this project a large number of comments are
    # [EN] **short sentences + Chinese examples** (`` `人物[0].性格` path syntax ``, `写 已发生故事线.md。`),
    # [EN] the translation is naturally "a few English words + a string of Chinese proper nouns", so such a
    # [EN] comparison produces false positives --
    # [EN] measured in practice this left 11 lines that could **never be filled in**, even though the model
    # [EN] had actually translated them fine.
    #    "Almost entirely Chinese" is the real signal; a word-count ratio is not.
    if cn >= 8 and en_words <= 2:
        return ""                       # 整行基本还是中文 —— 不要
        # [EN] Still Chinese -- do not
    return s


def _emit(orig: str, en: str) -> list[str]:
    """按**原文行**的形态排版译文：保住前导空白；代码/列表行不折行。
    Re-indent the translation to match its original line; never re-wrap
    code-ish lines.

    ★★ 为什么必须这么做（实测踩到）：docstring 里常有**代码示例与列表**
      （本项目的注释里到处都是 `    python xxx.py`、`  1. …`、表格）。
      统一 `strip()` + 折行会把它们的缩进压平、把示例折成半句，
      于是"译文把原文的排版弄坏了" —— 而 docstring 里那些示例正是最该
      保住的（读者照抄就能跑）。
      Even the translation must keep the original indentation, or code samples
      inside docstrings become unreadable.
    
        English:
        Re-indent the translation to match its original line; never re-wrap
        code-ish lines.
          Even the translation must keep the original indentation, or code samples
          inside docstrings become unreadable.
    """
    lead = re.match(r"[ \t]*", orig).group(0)
    txt = en.strip()
    stripped = orig.strip()
    # 代码 / 表格 / 列表 / 引用块：**不折行**（折了就不是那个东西了）
    # [EN] Code / tables / lists / block quotes: **do not wrap** (wrapping makes it no longer that thing)
    codeish = bool(lead) or stripped.startswith(
        ("```", "|", ">", "- ", "* ", "1. ", "2. ", "3. "))
    if codeish or len(txt) <= 96:
        return [lead + txt]
    return [lead + w for w in _wrap(txt)]


def render(lines: list[str], units: list[Unit], translated: list[list[str]]) -> str:
    """把译文插进去（**原行一个字不动**）。/ Insert the translations.

    · 注释块 → 在块的**最后一行之后**追加 `# [EN]` 行（保持折行）；
    · docstring → 在**闭引号之前**插入英文段。
    
    Insert the translations (**not a single character of the original lines changed**). / Insert the
    translations.
        · comment block → append a `# [EN]` line **after the last line of the block** (keeping wrapping);
        · docstring → insert the English paragraph **before the closing quote**.
    
        English:
        Insert the translations (**not a single character of the original lines changed**). / Insert the
        translations.
            · comment block → append a `# [EN]` line **after the last line of the block** (keeping wrapping);
            · docstring → insert the English paragraph **before the closing quote**.
    """
    head_insert: dict[int, list[str]] = {}               # 在 row 之后插入
    tail_insert: dict[int, tuple[int, list[str]]] = {}   # 在 (row, col) 之前插入
    # [EN] Insert after row
    # [EN] Insert before (row, col)

    for u, tr in zip(units, translated):
        good = [_usable(x) for x in tr]
        if not any(good):
            continue                            # 一条都没拿到 → 整个单元不动
            # [EN] Did not get a single one → leave the whole unit untouched
        if u.kind == "comment":
            out_lines: list[str] = []
            for orig, g in zip(u.texts, good):
                if g:
                    out_lines.extend(u.indent + EN_MARK + w
                                     for w in _emit(orig, g))
            if out_lines:
                head_insert.setdefault(u.rows[-1], []).extend(out_lines)
        else:                                   # docstring
            en_block: list[str] = []
            for orig, g in zip(u.texts, good):
                if g:
                    en_block.extend(_emit(orig, g))
            if not en_block:
                continue
            #  ★★ **普通 docstring 里，译文的反斜杠必须转义成 `\\`** ——
            #    不然 `…\User Pinned\TaskBar\` 这种正文塞进去，`\U` 就成了
            #    「截断的 Unicode 转义」⇒ 整个文件 SyntaxError（实测坏了 2 个：
            #    `store/project.py` 与 `developers/probe_taskbar_pin.py`）。
            #    raw docstring 里反过来 —— 一个字都不能动。
            #    （`\\` 在普通 docstring 里渲染出来**正是** `\`，语义不变。）
            # [EN] ★★ **In a normal docstring, the translation's backslashes must be escaped as `\\`** ——
            # [EN] otherwise when text like `…\User Pinned\TaskBar\` is inserted, the `\U` becomes
            # [EN] a "truncated Unicode escape" ⇒ the whole file gets a SyntaxError (measured: broke 2:
            # [EN] `store/project.py` and `developers/probe_taskbar_pin.py`).
            # [EN] In a raw docstring it is the opposite —— not a single character may be touched.
            # [EN] (`\\` in a normal docstring renders as **exactly** `\`, semantics unchanged.)
            if not u.raw:
                en_block = [w.replace("\\", "\\\\") for w in en_block]
            #  标记行（缩进跟正文一样）—— 下次靠它认出"这个 docstring 已经译过了"
            # [EN] Marker line (indented the same as the body) — next time, use it to recognize "this docstring has
            # [EN] already been translated"
            en_block = [u.indent + EN_SECTION] + en_block
            tail_insert[u.rows[-1]] = (u.end_col - len(u.quote), en_block,
                                       u.indent)

    out: list[str] = []
    for i, line in enumerate(lines):
        cur = line
        if i in tail_insert:                    # docstring：在闭引号之前插入
        # [EN] docstring: insert before the closing quote
            at, en_block, indent = tail_insert[i]
            body = ("\n" + indent).join(en_block)
            #  ⚠ 见 `collect()` 里那段说明：`at` 是**字节**偏移，必须按字节切。
            # [EN] ⚠ See the explanation in `collect()`: `at` is a **byte** offset, so you must slice by bytes.
            _lb = line.encode("utf-8")
            cur = (_lb[:at].decode("utf-8") + "\n" + indent + body + "\n"
                   + indent + _lb[at:].decode("utf-8"))
        out.append(cur)
        out.extend(head_insert.get(i, []))
    return "\n".join(out)


def write_back(path: Path, text: str) -> None:
    """备份 + 原子写（**保住原行尾**：CRLF 的文件不能变成 LF）。
    Back up, then write atomically — preserving the original line endings.
    
    Back up + atomic write (**preserve original line endings**: a CRLF file must not become LF).
        Back up, then write atomically — preserving the original line endings.
    
        English:
        Back up, then write atomically — preserving the original line endings.
        Back up + atomic write (**preserve original line endings**: a CRLF file must not become LF).
            Back up, then write atomically — preserving the original line endings.
    """
    raw = path.read_bytes()
    bak = path.with_suffix(path.suffix + ".bak-bilingual")
    if not bak.exists():                    # 已存在就不覆盖（背后是最初那份）
    # [EN] If it already exists, do not overwrite (what is behind it is the original version)
        bak.write_bytes(raw)
    nl = "\r\n" if b"\r\n" in raw else "\n"
    data = text.replace("\n", nl) if nl == "\r\n" else text
    tmp = path.with_suffix(path.suffix + ".tmp-write")
    tmp.write_bytes(data.encode("utf-8"))
    tmp.replace(path)


def undo(path: Path) -> bool:
    """从备份整份还原。/ Restore a file from its backup.
    Restore a file entirely from its backup. / Restore a file from its backup.
    
    Restore a file entirely from its backup. / Restore a file from its backup.
        Restore a file entirely from its backup. / Restore a file from its backup.
    
        English:
        Restore a file entirely from its backup. / Restore a file from its backup.
        Restore a file entirely from its backup. / Restore a file from its backup.
            Restore a file entirely from its backup. / Restore a file from its backup.
    """
    bak = path.with_suffix(path.suffix + ".bak-bilingual")
    if not bak.is_file():
        return False
    path.write_bytes(bak.read_bytes())
    return True


# ══════════════════════════════════════════════════════════════════
#  主流程 / main
# [EN] Main flow / main
# ══════════════════════════════════════════════════════════════════


def _done() -> dict:
    try:
        return json.loads(DONE_FILE.read_text(encoding="utf-8"))
    except Exception:                       # noqa: BLE001
        return {}


def _mark_done(rel: str, n: int) -> None:
    d = _done()
    d[rel] = {"lines": n, "when": time.strftime("%Y-%m-%d %H:%M:%S")}
    DONE_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                         encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    files = iter_files()
    if args.paths:
        wanted = {Path(p).resolve() for p in args.paths}
        files = [p for p in files if p.resolve() in wanted]

    if args.undo:
        n = sum(1 for p in files if undo(p))
        print(f"已从备份还原 {n} 个文件")
        return 0

    done = {} if args.redo else _done()
    plan: list[tuple[Path, list[str], list[Unit]]] = []
    for p in files:
        rel = p.relative_to(APP).as_posix()
        if rel in done:
            continue
        lines, units = collect(p)
        if units:
            plan.append((p, lines, units))
    total = sum(sum(len(u.texts) for u in units) for _p, _l, units in plan)
    print(f"待处理：{len(plan)} 个文件 / {total} 行注释"
          f"（已完成的跳过 {len(done)} 个）")

    if args.list or args.dry_run:
        for p, _l, units in plan[: (args.limit or len(plan))]:
            print(f"  {p.relative_to(APP).as_posix():58} "
                  f"{len(units):>4} 块 / {sum(len(u.texts) for u in units):>5} 行")
        if args.dry_run:
            print("\n（--dry-run：没有调模型、没有改文件）")
        return 0

    if args.limit:
        plan = plan[: args.limit]

    from config import CFG
    from llm.router import llm
    if CFG.mock:
        print("✗ 现在是**演示模式**（MOCK_LLM=true）—— 翻译要真模型才能做。")
        print("  改 `.env` 里的 MOCK_LLM=false 再跑。")
        return 2
    await llm.ensure_started()

    sem = asyncio.Semaphore(max(1, int(args.jobs)))
    ok_n = fail_n = lines_n = 0
    t0 = time.time()

    async def one(idx: int, p: Path, lines: list[str], units: list[Unit]) -> None:
        nonlocal ok_n, fail_n, lines_n
        async with sem:
            try:
                flat: list[str] = []
                for u in units:
                    flat.extend(u.texts)
                tr = await translate(flat)
                # 按单元切回去（每个单元的译文条数 == 它的原文行数）
                # [EN] Slice back by unit (each unit's number of translation entries == its number of source lines)
                cut, pos = [], 0
                for u in units:
                    cut.append(tr[pos:pos + len(u.texts)])
                    pos += len(u.texts)
                new = render(lines, units, cut)
                got = sum(1 for c in cut for x in c if _usable(x))
                if got == 0:
                    raise RuntimeError("一条译文都没拿到")
                if args.apply:
                    write_back(p, new)
                    _mark_done(p.relative_to(APP).as_posix(), got)
                lines_n += got
                ok_n += 1
                print(f"  [{idx}/{len(plan)}] {p.relative_to(APP).as_posix():50} "
                      f"+{got:>4} 行  ({time.time() - t0:.0f}s)", flush=True)
            except Exception as e:                          # noqa: BLE001
                fail_n += 1
                print(f"  [{idx}/{len(plan)}] ✗ {p.relative_to(APP).as_posix()}"
                      f"  {type(e).__name__}: {str(e)[:90]}", flush=True)

    await asyncio.gather(*[one(i + 1, p, l, u)
                           for i, (p, l, u) in enumerate(plan)])

    print(f"\n完成：成功 {ok_n} 个文件（+{lines_n} 行译文）· "
          f"失败 {fail_n} 个 · 用时 {time.time() - t0:.0f}s")
    if not args.apply:
        print("（**没有加 --apply**：一个文件都没写）")
    else:
        from llm import usage as U
        t = U.totals()
        print(f"台账：{t.get('calls', 0)} 次 · {U.fmt_cost(t.get('cost', 0))}")
    return 0 if fail_n == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把中文注释补上英文（双语化）")
    ap.add_argument("--list", action="store_true", help="只列出要处理的文件")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不调模型不改文件")
    ap.add_argument("--apply", action="store_true", help="真写回（不加就只打印）")
    ap.add_argument("--undo", action="store_true", help="从 .bak-bilingual 还原")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 个文件")
    ap.add_argument("--jobs", type=int, default=6, help="并发（默认 6）")
    ap.add_argument("--redo", action="store_true", help="忽略已完成记录，全部重跑")
    ap.add_argument("--paths", nargs="*", default=None, help="只处理指定文件")
    a = ap.parse_args(argv)
    return asyncio.run(run(a))


if __name__ == "__main__":
    raise SystemExit(main())
