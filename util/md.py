# -*- coding: utf-8 -*-
"""Markdown 切分（**围栏感知**）。

为什么单独一个模块
------------------
这个项目里有两处按标题切 Markdown 的地方，各自写了一份正则：

  · `gui/app_flet.read_manual()`  —— 帮助面板左栏目录用（按 `##` 切）
  · `research/manual_qa._split_sections()` —— 「问个问题」检索用（按 `##`~`####` 切）

两份实现，**同一个 bug**：都不认 ``` 代码围栏。

2026-10-06 用户报的现象：「帮助信息里左边有一个**登场人物**是什么？为什么没序号」。
根子在这里：`使用说明.md` §4.2.4「每轮开场」里有个 ```markdown 示例块，
里面第 497 行写着 `## 登场人物` —— 那是**开场卡的格式示例**，不是章节。
可正则不认围栏，把它当成了真的二级标题一刀切下去，于是：

  ① 左栏目录里凭空多出一项「登场人物」（它本来不是章节，自然也没有序号）；
  ② **它吞掉了后面所有 `###` 小节** —— §4.3 快捷键、§4.5 开卷对话框、
     §4.7 天机对话框、§4.10 帮助面板、§4.16 全局消息框…… 全成了它的正文
     （实测这一节 **23158 字**，而真章节只有几百到几千字）；
  ③ 用户点「4. 主界面详解」**读不到那半个 §4** —— 正文被割裂了；
  ④ 「问个问题」检索出的章节路径变成 `登场人物 › 4.8 书斋对话框 › …`，
     模型引用时也跟着张冠李戴。

英文手册同一个位置是 `## On stage`，一模一样。

所以修在**解析层**（而不是去改文档）：代码块里的 `#` 不该被当标题，
这是任何 Markdown 解析都该有的行为 —— 而且那份示例**本来就该**长成
`## 登场人物`（它跟 `开场.md` 的真实格式一致，改了文档反而会让示例骗人）。

一条健壮性设计
--------------
**围栏没闭合时，不当围栏看**。文档写坏一个 ``` 是很容易发生的事；
如果按"开了就一直关到文件尾"处理，后面所有标题会整片消失、目录直接空掉 ——
那是比"多切出一个假标题"严重得多的故障。所以这里**只屏蔽成对的围栏**，
落单的开启行按普通行处理（退回旧行为，多切一个也比全丢好）。

English:
Markdown splitting (**fence-aware**).
Why a separate module
------------------
This project has two places that split Markdown by heading, each with its own regex:
  · `gui/app_flet.read_manual()` -- used by the help panel's left-column TOC (splits by `##`)
  · `research/manual_qa._split_sections()` -- used by "ask a question" search (splits by `##`~`####`)
Two implementations, **the same bug**: neither recognizes ``` code fences.
2026-10-06 user-reported symptom: "In the help info there's a **登场人物** on the left, what is it?
Why no number?"
inside which line 497 says `## 登场人物` -- that's a **format example for the opening card**, not a
section.
But the regex doesn't recognize fences, treats it as a real level-2 heading and cuts there, so:
  ① The left-column TOC gains an extra entry "登场人物" out of nowhere (it was never a section, so naturally no number);
     (measured: this section is **23158 characters**, while real sections are only a few hundred to a few thousand);
  ③ Users clicking "4. 主界面详解" **can't read that half of §4** -- the body text got severed;
     and model citations get misattributed accordingly.
The English manual has `## On stage` at the same spot, exactly the same.
So fix it at the **parsing layer** (rather than editing the doc): `#` inside a code block
shouldn't be treated as a heading,
which is behavior any Markdown parser should have -- and that example **should** look like
`## 登场人物` anyway (it matches the real format of `开场.md`; changing the doc would make the example
lie instead).
A robustness design
--------------
**When a fence is not closed, do not treat it as a fence**. It is very easy to accidentally
break a ``` while writing docs;
if you treat it as "once opened, it stays closed until end of file", then all subsequent
headings disappear in one block, and the table of contents becomes completely empty --
that is a far more serious failure than "cutting out one extra fake heading". So here **only
paired fences are masked**;
a lone opening line is handled as a normal line (falling back to the old behavior; cutting one
extra is better than losing everything).
"""
from __future__ import annotations

import re

# 围栏开头：行首 0~3 个空格 + 三个及以上的 ` 或 ~（后面可以跟 info string）
# [EN] Fence start: 0~3 spaces at line start + three or more ` or ~ (optionally followed by an info
# [EN] string)
_FENCE_OPEN = re.compile(r'^[ \t]{0,3}(`{3,}|~{3,})(.*)$')
# 二级标题（目录用）：行首 `## ` + 非空标题
# [EN] Level-2 heading (for TOC): line start `## ` + non-empty title
_H2 = re.compile(r'^##[ \t]+(.*)$')
# 二~四级标题（检索用）
# [EN] Level 2~4 headings (for search)
_H234 = re.compile(r'^(#{2,4})[ \t]+(.*)$')
# 水平分割线：正文里拿掉（它只用来在渲染时分隔，不是内容）
# [EN] Horizontal rule: removed from body text (it only divides during rendering, not content)
_HR = re.compile(r'(?m)^---[ \t]*$')


def fence_mask(text: str) -> list[bool]:
    """逐行标记「这一行是不是在代码围栏里」（围栏行本身也算，`.split('\\n')` 对齐）。

    支持 ``` 与 ~~~、0~3 空格缩进、info string（```markdown）、
    闭合行长度 ≥ 开启行。

    闭合判定**故意宽松**：CommonMark 要求闭合行后面只能剩空白，这里不管 ——
    别人手写的文档里 ```` ```这是说明 ```` 这种写法很常见，容错比严格有用。

    ⚠ **未闭合的围栏不屏蔽**（见模块头的说明）——文档写坏一个 ``` 时，
    宁可多切出一个假标题，也不能让整份目录空掉。
    
        English:
    Mark line by line whether "this line is inside a code fence" (the fence lines themselves also
    count, aligned with `.split('\\n')`).
        Supports ``` and ~~~, 0~3 spaces of indentation, info string (```markdown),
        and closing line length >= opening line.
        Closing detection is **intentionally lenient**: CommonMark requires that only whitespace remain after the closing line, but this does not care --
        in hand-written docs, forms like ```` ```this is a note ```` are very common, and tolerance is more useful than strictness.
        ⚠ **Unclosed fences are not masked** (see the module header note) -- when a ``` is broken in the docs,
        it is better to cut out one extra fake heading than to let the whole table of contents become empty.
    """
    lines = str(text or '').split('\n')
    mask = [False] * len(lines)
    opened: tuple[str, int, int] | None = None      # (字符, 长度, 起始行号)
    # [EN] (char, length, start line number)
    for i, ln in enumerate(lines):
        m = _FENCE_OPEN.match(ln)
        if opened is None:
            if m:
                opened = (m.group(1)[0], len(m.group(1)), i)
            continue
        ch, n, start = opened
        if m and m.group(1)[0] == ch and len(m.group(1)) >= n:
            for j in range(start, i + 1):
                mask[j] = True
            opened = None
    return mask


def heading_rows(text: str, *, level: tuple[int, ...] = (2,)) -> list[int]:
    """**不在围栏里**的标题行号（`level` 给出要哪些级别，如 `(2,)` 或 `(2,3,4)`）。
        English:
    Heading line numbers **not inside fences** (`level` specifies which levels are wanted, e.g.
    `(2,)` or `(2,3,4)`).
    """
    lines = str(text or '').split('\n')
    mask = fence_mask(text)
    want = set(level)
    out: list[int] = []
    for i, ln in enumerate(lines):
        if mask[i]:
            continue
        m = _H234.match(ln)
        if m and len(m.group(1)) in want:
            out.append(i)
    return out


def split_h2(text: str) -> tuple[str, list[tuple[str, str]]]:
    """按**二级**标题切：`(导言, [(标题, 正文), …])`。帮助面板的目录用这个。

    与旧 `gui.app_flet.read_manual()` 的返回形状一致（那边的调用点不用改）。
    
        English:
    Split by **level-2** headings: `(intro, [(title, body), ...])`. The help panel's table of
    contents uses this.
        Same return shape as the old `gui.app_flet.read_manual()` (call sites there do not need changes).
    """
    src = str(text or '')
    lines = src.split('\n')
    marks = heading_rows(src, level=(2,))
    if not marks:
        return _HR.sub('', src).strip(), []
    intro = _HR.sub('', '\n'.join(lines[:marks[0]])).strip()
    out: list[tuple[str, str]] = []
    for k, i in enumerate(marks):
        title = _H2.match(lines[i]).group(1).strip()
        end = marks[k + 1] if k + 1 < len(marks) else len(lines)
        body = _HR.sub('', '\n'.join(lines[i + 1:end])).strip()
        if title:
            out.append((title, body))
    return intro, out


def split_sections(text: str) -> list[dict]:
    """按 `##`~`####` 切段，`title` 是**带父级的路径**（`A › B › C`）。

    为什么带父级：光看「4.5.0 第 2 步的项目名称与三个下拉框」不知道在讲哪一步；
    带上「4.5 开卷对话框（导入向导）›」之后，模型引用时也不会张冠李戴。

    与旧 `research.manual_qa._split_sections()` 的返回形状一致
    （`{'title', 'lines', 'body'}`，调用点不用改）。
    
        English:
    Split sections by `##`~`####`; `title` is the **path with parents** (`A › B › C`).
        Why include parents: just seeing "4.5.0 Step 2's project name and three dropdowns" does not tell you which step it is talking about;
        with "4.5 Open dialog (import wizard) ›" attached, the model will not mix things up when citing it either.
        Same return shape as the old `research.manual_qa._split_sections()`
        (`{'title', 'lines', 'body'}`, call sites do not need changes).
    """
    src = str(text or '')
    lines = src.split('\n')
    mask = fence_mask(src)
    stack: dict[int, str] = {}
    out: list[dict] = []
    cur: dict | None = None
    for i, ln in enumerate(lines):
        if not mask[i]:
            m = _H234.match(ln)
            if m:
                lv, title = len(m.group(1)), m.group(2).strip()
                stack[lv] = title
                for deeper in [k for k in stack if k > lv]:
                    del stack[deeper]
                cur = {"title": " › ".join(stack[k] for k in sorted(stack)),
                       "lines": []}
                out.append(cur)
                continue
        if cur is not None:
            cur["lines"].append(ln)
    for c in out:
        c["body"] = _HR.sub('', '\n'.join(c["lines"])).strip()
    return [c for c in out if c["title"]]


def split_blocks(text: str, level: int = 3) -> list[str]:
    """把一段 Markdown 按第 `level` 级标题切成**若干可直接渲染的片段**（各自带标题行）。

    为什么需要它（2026-10-06 实测）：帮助面板右栏原来把**整章**（§4 两万多字）
    交给**一个** `ft.Markdown`。而 `ft.Markdown` 在 `ListView` 里、
    **首次挂载之前**就设好内容时，高度**算不准** —— ListView 以为"内容没超出"，
    于是既不滚动、也不出滚动条，用户读不到后半章（他问的"有没有下拉条"
    底下压着的其实是这个）。

    拆成多个小片段之后，每个 Markdown 的高度都很小、测量可靠，
    整个 `ListView` 的高度就算对了。**额外的好处**：以后要让"左栏点到小节"
    也有地方落（每个片段对应一个小节）。

    ⚠ 用 `heading_rows()` 而不是直接 `re.split`：**围栏里的 `###` 不算标题**
    （说明书里真的有代码块写着 `###`）。开头那段（章节引言，标题之前的部分）
    也会作为第一个片段保留。
    
        English:
    Split a Markdown passage by `level`-th headings into **several directly renderable fragments**
    (each with its heading line).
        Why this is needed (measured on 2026-10-06): the help panel's right column originally gave **an entire chapter** (§4, over 20k words)
        to **a single** `ft.Markdown`. And when `ft.Markdown` is inside a `ListView` and
        its content is set **before the first mount**, its height is **computed inaccurately** -- the ListView thinks "the content has not overflowed",
        so it neither scrolls nor shows a scrollbar, and the user cannot read the second half of the chapter (what was behind his question "is there a dropdown bar"
        is actually this).
        After splitting into multiple small fragments, each Markdown's height is very small and measured reliably,
        and the whole `ListView`'s height is computed correctly. **An extra benefit**: in the future, if you want "clicking a subsection in the left column"
        to also have somewhere to land (each fragment corresponds to a subsection).
        ⚠ Use `heading_rows()` instead of directly calling `re.split`: **`###` inside fences does not count as a heading**
        (the manual really does have code blocks containing `###`). The opening part (the chapter introduction, the part before the heading)
        is also kept as the first fragment.
    """
    src = str(text or '')
    if not src.strip():
        return []
    lines = src.split('\n')
    marks = heading_rows(src, level=(level,))
    if not marks:
        return [src]
    out: list[str] = []
    if marks[0] > 0:
        head = '\n'.join(lines[:marks[0]]).strip()
        if head:
            out.append(head)
    for k, i in enumerate(marks):
        end = marks[k + 1] if k + 1 < len(marks) else len(lines)
        chunk = '\n'.join(lines[i:end]).strip()
        if chunk:
            out.append(chunk)
    return out or [src]



# ══════════════════════════════════════════════════════════════════════
#  「把它当纯文本显示」—— 给**不经过 Markdown 渲染**的控件用
# [EN] "Display it as plain text" -- for controls that do **not** go through Markdown rendering
# ══════════════════════════════════════════════════════════════════════
#
# 2026-10-06 用户报：「搜索结果里有 markdown 渲染没成功的地方 还有不少」。
# 查下来不是渲染器坏了，是**有些地方压根没走渲染器**：
#   · 左栏目录行 / 正文顶上那行标题 —— 是 `ft.Text`，直接塞了章节标题原文；
#   · 「命中处摘录」（`_snippets`）—— 也是 `ft.Text`，摘的是**Markdown 原文**。
# 而说明书里有 8 个章节标题自带行内语法（`**小说体**`、`` `samples/` ``、
# `` `story_day` ``），摘录里更是 `###`、`![图](路径)`、表格竖线 什么都有 ——
# 屏幕上就是一堆星号和反引号。
# [EN] 2026-10-06 user report: "There are places in the search results where markdown rendering didn't
# [EN] succeed, and quite a few".
# [EN] Investigation shows it's not that the renderer is broken, it's that **some places never go
# [EN] through the renderer at all**:
# [EN] · Left-column TOC lines / the title line at the top of the body -- these are `ft.Text`, with the
# [EN] raw section title stuffed in directly;
# [EN] · "Match excerpt" (`_snippets`) -- also `ft.Text`, excerpting the **raw Markdown**.
# [EN] And in the manual, 8 section titles carry inline syntax (`**小说体**`, `` `samples/` ``,
# [EN] `` `story_day` ``), while excerpts contain everything: `###`, `![图](路径)`, table pipes, etc. --
# [EN] on screen it's just a pile of asterisks and backticks.
#
# 两条路：① 把这些地方也换成 Markdown 控件（但它们要**单行省略**、
# 要贴着小字排版，Markdown 控件做不到）；② **先把标记去掉再当纯文本显示**。
# 这里走 ② —— 显示的本来就是个"预览"，去掉标记才是它该有的样子。
# [EN] Two paths: ① switch these places to Markdown controls too (but they need **single-line
# [EN] ellipsis**,
# [EN] and must hug small-font layout, which Markdown controls can't do); ② **strip the markup first,
# [EN] then display as plain text**.
# [EN] Here we take ② -- what's displayed is a "preview" anyway, and stripping markup is how it should
# [EN] look.
#
# ⚠ 不动的那些：`research/manual_qa` 把标题喂给模型时**保留原文**
#   （模型看 `**小说体**` 完全没问题，而且那是"这一节的真名"）。
# [EN] ⚠ What stays untouched: `research/manual_qa` **keeps the original text** when feeding titles to
# [EN] the model
# [EN] (the model is perfectly fine seeing `**小说体**`, and that's "the real name of this section").
_INLINE_RULES: list[tuple[re.Pattern, str]] = [
    # 图片 → 它的 alt 文字（`![](路径)` 没有 alt 就整段去掉，别露一行路径）
    # [EN] Image → its alt text (for `![](路径)` with no alt, drop the whole thing, don't leak a path line)
    (re.compile(r'!\[([^\]]*)\]\([^)\s]*\)'), r'\1'),
    # 链接 → 链接文字
    # [EN] Link → link text
    (re.compile(r'\[([^\]]+)\]\([^)\s]*\)'), r'\1'),
    (re.compile(r'\*{3}([^*\n]+)\*{3}'), r'\1'),
    (re.compile(r'\*{2}([^*\n]+)\*{2}'), r'\1'),
    (re.compile(r'(?<![\*\w])\*([^*\n]+)\*(?![\*\w])'), r'\1'),
    (re.compile(r'_{2}([^_\n]+)_{2}'), r'\1'),
    (re.compile(r'`+([^`]*)`+'), r'\1'),
    (re.compile(r'~~([^~\n]+)~~'), r'\1'),
    # 行内 HTML（说明书里没用，但别人改了文档就会露出来）
    # [EN] Inline HTML (not used in the manual, but it'll show up if others edit the docs)
    (re.compile(r'</?[A-Za-z][A-Za-z0-9]*[^>]{0,60}>'), ''),
]
# 块级标记：**必须锚行首**（`(?m)`）。
# [EN] Block-level markup: **must anchor to line start** (`(?m)`).
#
# ⚠ 2026-10-06 修：早先写的是 `(?:^|\s)>[ \t]?`（"行首或空格后"），
#   本意是"摘录的窗口常常从半行中间开始"，结果**把正文里正常的 `>` 吃了** ——
#   `价格 $3 < 5 > 2` 变成 `价格 $3 < 5 2`。现在窗口是在**原始文本**上切的
#   （带 `\n`），真的行首会以 `\n` 出现，所以老老实实锚行首就对了。
# [EN] ⚠ 2026-10-06 fix: earlier it was written as `(?:^|\s)>[ \t]?` ("line start or after a space"),
# [EN] the intent was "excerpt windows often start mid-line", but it ended up **eating normal `>` in
# [EN] body text** --
# [EN] `价格 $3 < 5 > 2` became `价格 $3 < 5 2`. Now the window is cut on the **raw text**
# [EN] (with `\n`), so real line starts appear as `\n`, and honestly anchoring to line start is
# [EN] correct.
_BLOCK_LEAD = re.compile(r'(?m)^[ \t]{0,3}#{1,6}[ \t]+')
_BLOCK_QUOTE = re.compile(r'(?m)^[ \t]{0,3}>[ \t]?')
_BLOCK_BULLET = re.compile(r'(?m)^[ \t]*[-*+][ \t]+')
# 整行围栏（连 info string 一起吃掉：` ```markdown ` → 空）
# [EN] Whole-line fence (eats the info string too: ` ```markdown ` → empty)
_FENCE_LINE = re.compile(r'(?m)^[ \t]{0,3}(`{3,}|~{3,})[ \t]*[A-Za-z0-9_+.#-]*[ \t]*$')
# 落单的围栏（窗口从行中间开始时会剩下）：三连及以上
# [EN] Lone fence (left over when the window starts mid-line): three or more
_FENCE_LEFT = re.compile(r'`{3,}[A-Za-z0-9_+.#-]*|~{3,}[A-Za-z0-9_+.#-]*')


def plain_inline(s: str) -> str:
    """去掉**行内** Markdown 标记，留下能直接显示的纯文字（标题用）。

    `**加粗**` → `加粗` · `` `代码` `` → `代码` · `[字](url)` → `字` · `![图](p)` → 图。
    
        English:
    Remove **inline** Markdown markers, leaving plain text that can be displayed directly (used for
    headings).
        `**bold**` → `bold` · `` `code` `` → `code` · `[text](url)` → `text` · `![img](p)` → img.
    """
    out = str(s or '')
    for pat, rep in _INLINE_RULES:
        out = pat.sub(rep, out)
    return out.strip()


def plain_preview(s: str) -> str:
    """给"一行预览"用：在 `plain_inline` 之上再去掉**块**标记。

    还要处理两件"摘录特有"的事：
      · **表格**：整行 `| a | b |` 换成 `a · b`，而 `| --- | --- |` 那条
        **分隔行直接丢掉**（不然摘录里会出现一串破折号，看着像乱码）——
        摘录的窗口可能从半行中间开始，所以不能只判断"行首的 `|`"；
      · **换行**：最后统一压成空格（摘录是"一行"，不能真的折行）。
    
        English:
    For "one-line preview": remove **block** markers on top of `plain_inline`.
        Also handle two things that are "specific to excerpts":
          · **Tables**: a whole row `| a | b |` becomes `a · b`, while the `| --- | --- |`
            **separator line is simply discarded** (otherwise a string of dashes would appear in the excerpt, looking like garbled text) --
            an excerpt's window may start in the middle of a line, so you cannot only check for a `|` at the start of the line;
          · **Line breaks**: finally all compressed into spaces (an excerpt is "one line" and must not actually wrap).
    """
    out = str(s or '')
    # ⚠ **围栏必须在 `plain_inline` 之前**处理：不然后面那条"成对反引号"规则
    #   会把 ` ```markdown ` 和结尾的 ` ``` ` 当成一段**行内代码**，
    #   把 info string（`markdown`）当正文留在结果里。
    # [EN] ⚠ **Fences must be processed before `plain_inline`**: otherwise the later "paired backtick" rule
    # [EN] will treat ` ```markdown ` and the trailing ` ``` ` as a stretch of **inline code**,
    # [EN] leaving the info string (`markdown`) in the result as body text.
    out = _FENCE_LINE.sub(' ', out)
    out = plain_inline(out)
    out = _FENCE_LEFT.sub(' ', out)     # 窗口从行中间切进来时剩下的围栏
    # [EN] Fence remnants left when the window cuts in mid-line
    out = _BLOCK_LEAD.sub(' ', out)
    out = _BLOCK_QUOTE.sub(' ', out)
    out = _BLOCK_BULLET.sub(' ', out)
    if '|' in out:
        # 表格：按格子拆 → 扔掉**纯装饰**的格子（`---` / `:--:` / 空），
        # 其余用中点接起来。比"整段替换竖线"稳：分隔行不管出现在窗口哪个位置
        # 都会被丢掉，不会留下一串破折号。
        # [EN] Table: split by cells → discard **purely decorative** cells (`---` / `:--:` / empty),
        # [EN] join the rest with a middle dot. More robust than "replace pipes wholesale": no matter where the
        # [EN] separator row appears in the window
        # [EN] it gets dropped, so no run of dashes is left behind.
        cells = [x.strip() for x in out.split('|')]
        keep = [x for x in cells if x and not re.fullmatch(r'[\s:\-]+', x)]
        out = ' · '.join(keep) if keep else ' '.join(cells)
    out = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', out)   # 保险：没 alt 的图
    out = re.sub(r'\s+', ' ', out)                    # 换行/连续空白 → 一个空格
    out = re.sub(r'(?:\s*·\s*){2,}', ' · ', out)      # 空单元格留下的 `· ·`
    # [EN] Safety net: images with no alt
    # [EN] Newlines/consecutive whitespace → a single space
    # [EN] `· ·` left behind by empty cells
    out = re.sub(r'^[\s·]+|[\s·]+$', '', out)
    return out
