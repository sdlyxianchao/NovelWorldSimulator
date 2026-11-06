# -*- coding: utf-8 -*-
"""**拆书**（`booklab/`）：把一本写得好的书读成"能拿走的写法"，供 Agent 参考。

⚠ 名字就叫**「拆书」**（用户 2026-10-07 定：*"拆书是术语，不好随便修改"*）。
  它是行业里既有的叫法，和 `三刀拆书法` / `十步拆文法`（见 `theory.py`）是同一批词 ——
  属"说法来源"，不是本项目自造的产品名，所以不给它另起名字。英文界面上叫
  **`Book Deconstruction`**（2026-10-10 用户点名的译法 —— 意译出"拆解"本义；
  此前叫 `Book Lab`，那个名字看不出"拆"这件事）。

  历史（免得下一个人再动它）：2026-10-07 当天曾被改成「打谱」（围棋术语），
  随即按用户要求改了回来；那次改名留下的"新旧前缀都认"那套兼容常量也一并撤掉了——
  现在 `skillgen` 只有**一个** `PREFIX = '书拆·'`，没有第二套名字。
  ⚠ 代码标识符（模块 `booklab/` · 旋钮 `BOOKLAB_*` · `verify_booklab` / `mutate_booklab`）
  从头到尾没动过：用户一个都看不到，改它们只会白白牵动一大片判据。

用户 2026-10-07
--------------
「你加一个拆书功能，在开始菜单里放一个位置，打开之后是拆书对话框，跟开卷类似
但是**我传入的是一本书籍或者一本书的一部分**，你问我**书籍名字 类型
觉得哪些地方好 重点拆什么**，你要根据**拆书理论和方法**去读书，然后学习小说的
**情节塑造 小说节奏 人物塑造**等等拆书需要拆的东西 整理之后变成本地SKILL，
根据书籍类型和特点抽取出来 整理成本地SKILL，在**后续有类似书籍设定进来的时候**，
使用这些经验**辅助各个Agent工作，特别是三人小组（小说家 剧作家 导演）用于优化故事**」

一页看懂（六个模块 + 两条线）
----------------------------
```text
① theory.py     拆什么、按什么顺序拆（方法论，纯数据）
② sources.py    从哪儿读、读得出来吗（txt/md/docx/html/**pdf** · 文件夹 · 网址）
③ selection.py  只拆哪一段（`1-10,15-21` / `前3章` / `第5章-第8章` / 标题关键词）
④ reader.py     怎么读得完（分章 → 分层取样 → 挑重点章）
⑤ analyzer.py   四道工序：建目录 → 粗扫 → 精拆 → 归纳
⑥ skillgen.py   把结论写成 skills/book-dismantle/<书名>/（SKILL.md + digest.json + 拆书记录.md）
                                    ↓
        store.py（拆书库）—— 后续开卷时按"类型 + 关键词"匹配
                                    ↓
        crew/agents.craft_block() —— 一处接上，十四个职位同时拿到；
                                      三人小组（小说家/剧作家/导演）拿到的是完整版
        crew/skill_router.py     —— 另一条：各职位按自己这一刻的活儿
                                      去 skills/ 里挑**知识包**（药方/器物/官制…）
```

★ 三种输入的收口在 `reader.read_book`（文件 / 文件夹 / 网址），
  而**范围筛选必须发生在取样之前** —— 用户说"只拆前 10 页"，那 10 页就是全部素材。
  ⚠ 解析不了的范围**不许当"全部"**（见 `selection.py` 模块头第 1 条纪律）。

它与"开卷"的区别（这两个功能容易混）
----------------------------------
| | 开卷（`ingest/`） | 拆书（`booklab/`） |
|---|---|---|
| 读的是什么 | 你**自己要写**的那本书的素材 | 你**觉得写得好**的那本书 |
| 目的是什么 | 把它变成设定集（人物/地点/伏笔/进度） | 把它变成**写法**（情节/节奏/人设/文风） |
| 产出放在哪 | 项目里（开始推演用） | `skills/`（以后写同类书时参考） |
| 读法 | 尽量读全 | **读不完**，只读该读的（分层取样 + 挑重点章） |
| 会不会进提示词 | 设定进 | 匹配上的写法经验进 |

★ 一句话：**开卷是"把这本书变成我的世界"，拆书是"把这本书变成我的本事"。**

三条纪律
--------
1. **只读用户的文件**，一个字都不写回去（与开卷同一条铁律）。
2. **不许静默降级**：没读到哪一批、哪一步没拿到结果，都要照实记进
   `Digest.notes` 并显示给作者 —— 少读几批却交出一份看着完整的报告，比失败更坏。
3. **不抄原文**：产出的是做法（怎么做/什么时候用/为什么管用），
   "这本书的例子"只作证；判据会查有没有成段引用。

用法
----
```python
from booklab import analyzer as A, skillgen as SG
d = await A.run('路径/某本书.txt', A.Brief(title='…', genre='悬疑·单元剧',
                                           good='第 12 章那场戏', focus='节奏'))
if d.ok:
    w = SG.write(d)            # → skills/书拆·某本书/
    SG.reload_registry()       # 让注册表立刻认出它
```

English:
**Book Deconstruction** (`booklab/`): read a well-written book into "takeaway techniques" for
Agents to reference.
⚠ It is literally called **"Book Deconstruction"** (user 2026-10-07 decided: *"Book
Deconstruction is a term, not to be changed casually"*).
  it belongs to "sources of phrasing", not a product name invented by this project, so it is not renamed. In the English UI it is called
  **`Book Deconstruction`** (the translation specified by the user on 2026-10-10 —— it paraphrases the original meaning of "deconstruct";
  previously it was called `Book Lab`, a name that doesn't convey the act of "deconstruction").
  History (so the next person doesn't touch it again): on 2026-10-07 it was once changed to "打谱" (a Go term),
  and immediately changed back at the user's request; the compatibility constants for recognizing both old and new prefixes left by that rename were also removed ——
  now `skillgen` has only **one** `PREFIX = '书拆·'`, with no second set of names.
  ⚠ Code identifiers (module `booklab/` · knobs `BOOKLAB_*` · `verify_booklab` / `mutate_booklab`)
  have never been touched: the user never sees any of them, and changing them would only needlessly drag along a large set of assertions.
User 2026-10-07
--------------
"Add a book deconstruction feature, put an entry in the start menu, opening it brings up the
book deconstruction dialog, similar to ingest
but **what I pass in is a book or a portion of a book**, you ask me **the book name, type,
which parts I think are good, what to focus on deconstructing**, you should read the book
according to the **book deconstruction theory and method**, then learn the novel's
**plot shaping, novel pacing, character building** and so on, the things that need to be
deconstructed, and after organizing turn them into a local SKILL,
extract according to the book's type and characteristics, organize into a local SKILL, and
**when similar book settings come in later**,
use this experience to **assist each Agent's work, especially the three-person team (novelist,
playwright, director) for optimizing stories**"
Understand in one page (six modules + two lines)
----------------------------
```text
① theory.py     what to deconstruct, in what order (methodology, pure data)
② sources.py    where to read from, can it be read (txt/md/docx/html/**pdf** · folders · URLs)
③ selection.py which segment to deconstruct (`1-10,15-21` / `first 3 chapters` / `chapters 5-8`
/ title keywords)
④ reader.py how to finish reading (split into chapters → layered sampling → pick key chapters)
⑤ analyzer.py   four stages: build catalog → rough scan → fine deconstruction → summarize
⑥ skillgen.py write conclusions to skills/book-dismantle/<book name>/ (SKILL.md + digest.json +
拆书记录.md)
                                    ↓
        store.py (deconstruction library) —— on later ingest, match by "type + keywords"
                                    ↓
        crew/agents.craft_block() —— wired in one place, all fourteen roles get it at once;
                                      the three-person team (novelist/playwright/director) gets the full version
        crew/skill_router.py     —— the other line: each role, based on its task at this moment,
                                      picks **knowledge packs** (prescriptions/objects/officialdom...) from skills/
```
★ The convergence point for the three kinds of input is `reader.read_book` (file / folder /
URL),
  and **range filtering must happen before sampling** —— if the user says "only deconstruct the first 10 pages", those 10 pages are all the material.
  ⚠ A range that cannot be parsed **must not be treated as "all"** (see `selection.py` module header rule 1).
Its difference from "ingest" (these two features are easily confused)
----------------------------------
| | Ingest (`ingest/`) | Book Deconstruction (`booklab/`) |
|---|---|---|
| What is read | Material for the book you **want to write yourself** | The book you **think is well written** |
| What is the purpose | Turn it into a setting collection (characters/locations/foreshadowing/progress) | Turn it into **writing techniques** (plot/pacing/character design/style) |
| Where the output goes | In the project (for starting deduction) | `skills/` (for reference when writing similar books later) |
| How to read | Read as fully as possible | **Cannot finish**, read only what should be read (layered sampling + pick key chapters) |
| Will it enter the prompt | Settings do | Matched writing experience does |
★ One sentence: **Ingest is "turn this book into my world", Book Deconstruction is "turn this
book into my skills".**
Three rules
--------
1. **Only read the user's files**, write not a single word back (same iron rule as ingest).
2. **No silent degradation**: whichever batch was not read, which step did not get a result, all must be recorded truthfully in
   `Digest.notes` and shown to the author —— reading a few batches less yet delivering a report that looks complete is worse than failure.
3. **Do not copy the original text**: what is produced is method (how to do it/when to use it/why it works),
   "this book's example" serves only as evidence; the checker will look for whether there are block quotes.
Usage
----
```python
from booklab import analyzer as A, skillgen as SG
d = await A.run('path/somebook.txt', A.Brief(title='…', genre='suspense·episodic',
                                           good='Chapter 12 that scene', focus='rhythm'))
if d.ok:
    SG.reload_registry()       # make the registry recognize it immediately
```
[Output language] All **output text** must be written in **Simplified Chinese** — narration,
voice-over, dialogue, documentation, summaries, and suggestions all count, **even if the source
material is in another language**. Proper nouns such as personal names, place names, and book
titles **retain their original spelling**; do not transliterate or translate them by meaning.
**Key names in JSON remain unchanged** (e.g. "动作", "台词"); only write the **values** in Chinese.
"""
from __future__ import annotations

from booklab import (analyzer, metrics, reader, selection,  # noqa: F401
                     skillgen, sources, store, theory, web)

__all__ = ['analyzer', 'metrics', 'reader', 'selection', 'skillgen',
           'sources', 'store', 'theory', 'web']
