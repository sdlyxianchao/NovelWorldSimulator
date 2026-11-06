# -*- coding: utf-8 -*-
"""**拆书的方法论**：拆什么、怎么拆、拆出来干什么用。

用户 2026-10-07
--------------
「你要根据**拆书理论和方法**去读书，然后学习小说的**情节塑造 小说节奏 人物塑造**
等等拆书需要拆的东西 整理之后变成本地 SKILL」

这个模块回答"拆什么、按什么顺序拆"。它是**纯数据 + 提示词**，不发 LLM 请求
（发请求在 `analyzer.py`）。

拆书是什么
----------
一句话：**逆向工程**。人家写完的成品，你倒着推它的设计图。
普通读者读完说"这本好看"，拆书的人读完要能说出**"它好在第几章、用了什么办法"** ——
后者才是能拿走的东西。

三条来路（本模块的维度表是这三样合出来的）
----------------------------------------
① 网文圈的**三刀拆书法**（流传最广的那一套）：
     第一刀拆**骨架** —— 每章一句话，看出波浪线；
     第二刀拆**人设** —— 标签 / 动机 / 关系三件事；
     第三刀拆**情绪** —— 哪里爽哪里憋、作者怎么压的、章末怎么勾人。
② **十步拆文法**（书名 → 题材 → 字数 → 人物 → 主线 → 结构 → 情绪 → 钩子 → 语言 → 可复用模块）：
   它比三刀多出来的是"**可复用模块**"那一步 —— 也就是**移植**：
   不抄情节，提取"公式"。
③ 拉片式精拆（影视那一路）：**每章功能 / 章末钩子类型 / 情绪曲线 / 信息释放节奏**。

四道工序（`analyzer.py` 照这个跑）
--------------------------------
```text
① 建目录   分章 → 章名 + 字数（零成本，本地）
② 粗扫     分批读 → 每章一句话 + 功能 + 情绪强度（**得出波浪线**）
③ 精拆     挑重点章逐段读 → 这一步才谈得上"手法"
④ 归纳     跨章提炼 → **可复用的模块**（这才是最终能用的东西）
```

★ 为什么必须"先粗扫、再精拆"：一本网文几十万到几百万字，**不可能全读**。
  粗扫是**为了知道该精读哪几章**。直接全篇精读既贵又读不完；
  上来就精读开头三章，又只能学到开头怎么写。

★ 为什么最后一定要"归纳成模块"：拆解笔记（"第 12 章这里写得好"）**没法用** ——
  它是**关于那本书的**。能用的东西必须是**脱离了那本书还成立的**：
  "怎么把一个人物的本事藏到第三幕才亮出来"。
  这一步做不好，拆书就只是读书笔记。

English:
**Methodology of book dismantling**: what to dismantle, how to dismantle, what the dismantled
output is used for.
User 2026-10-07
--------------
"You have to read the book according to **book-dismantling theory and methods**, then learn the
novel's **plot shaping, novel pacing, character shaping**
and so on — the things that book dismantling needs to dismantle, and after organizing them turn
them into a local SKILL"
This module answers "what to dismantle, in what order to dismantle". It is **pure data +
prompt**, does not send LLM requests
(sending requests happens in `analyzer.py`).
What book dismantling is
----------
In one sentence: **reverse engineering**. Someone else's finished product, you work backward to
its design blueprint.
An ordinary reader finishes and says "this one's good", the book-dismantler finishes and must be
able to say **"which chapter it's good in, and by what method"** —
the latter is the thing that can be taken away.
Three sources (this module's dimension table is combined from these three)
----------------------------------------
① The web-fiction circle's **three-cut book-dismantling method** (the most widely circulated
one):
     First cut dismantles the **skeleton** — one sentence per chapter, see the wave line;
     Second cut dismantles the **character design** — three things: tags / motivation / relationships;
     Third cut dismantles **emotion** — where it's satisfying, where it's stifled, how the author suppressed it, how the chapter end hooks the reader.
② **Ten-step text-dismantling method** (book title → genre → word count → characters → mainline
→ structure → emotion → hooks → language → reusable modules):
   What it adds over the three cuts is the "**reusable modules**" step — that is, **transplantation**:
   don't copy the plot, extract the "formula".
③ Frame-by-frame-style fine dismantling (the film/TV route): **chapter function / chapter-end
hook type / emotional curve / information-release pacing**.
Four processes (`analyzer.py` runs according to this)
--------------------------------
```text
① Build catalog   split chapters → chapter name + word count (zero cost, local)
② Rough scan read in batches → one sentence per chapter + function + emotional intensity
(**derive the wave line**)
③ Fine dissection Pick key chapters and read them paragraph by paragraph → only at this step can
we talk about "technique"
④ Synthesis Extract across chapters → **reusable modules** (these are the things that can
actually be used in the end)
```
★ Why "coarse scan first, then fine dissection" is mandatory: a web novel is hundreds of
thousands to millions of characters; **it is impossible to read it all**.
  The coarse scan is **to know which chapters deserve close reading**. Reading everything closely is both expensive and impossible to finish;
  while starting with a close read of the first three chapters only teaches you how the opening is written.
★ Why the final step must be "synthesize into modules": dissection notes ("chapter 12 is well
written here") **cannot be used** ——
  they are **about that book**. What can be used must be **something that still holds after leaving that book**:
  "how to hide a character's ability until the third act to reveal it".
  If this step is done poorly, book dissection is just reading notes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ══════════════════════════════════════════════════════════════
#  维度表：拆什么
# [EN] Dimension table: what to dismantle
# ══════════════════════════════════════════════════════════════
#: 每个维度：`key` · `name`（显示名）· `ask`（问模型什么）· `out`（要什么形态的产出）
# [EN] : Each dimension: `key` · `name` (display name) · `ask` (what to ask the model) · `out` (what
# [EN] form of output is wanted)
#:
#: `ask` 与 `out` 都是**直接进提示词的**，所以要写得像"给人下的活"，
#: 不能写成给人看的说明。
# [EN] : `ask` and `out` both go **directly into the prompt**, so write them like "a job handed to a
# [EN] person",
# [EN] : not like an explanation written for a person to read.
@dataclass(frozen=True)
class Dimension:
    key: str
    name: str
    ask: str          # 问什么（进提示词）
    out: str          # 产出什么形态
    # [EN] What to ask (goes into the prompt)
    # [EN] What form of output

    def label(self) -> str:
        return self.name


DIMENSIONS: tuple[Dimension, ...] = (
    Dimension(
        'skeleton', '骨架与节奏',
        '这本书的**节拍**是怎么排的：哪里在压（攒着不给）、哪里在爆（一次给足）、'
        '压了多久才爆。**先看开头三章**：第一章用什么把读者拽住、主角的目标什么时候'
        '给出来、第一个钩子在第几段。',
        '一条"波浪线"：分段说出哪几段在压、哪几段在爆、转折点在第几章附近。',
    ),
    Dimension(
        'character', '人物塑造',
        '人物只用三件事看：**标签**（一句话怎么形容他，必须有特别突出的那一点）、'
        '**动机**（他为什么非要这么做）、**关系**（谁烘托他、谁是他的对手）。'
        '特别注意：**作者是怎么让读者记住一个人的**（第一次出场给了他什么动作或台词）。',
        '主要人物每人三行（标签/动机/关系）+ **作者立人的手法**一句。',
    ),
    Dimension(
        'emotion', '情绪与钩子',
        '哪些地方让读者爽、哪些地方让读者憋，**作者是用什么办法制造这两种感觉的**；'
        '每章结尾留的是什么钩子（悬念型/反转型/预告型/情绪型）。'
        '重点说清：**压是怎么压的**（连续打压、还是给一点希望再打）。',
        '情绪手法清单 + 章末钩子的常见类型。',
    ),
    Dimension(
        'plot', '情节与伏笔',
        '主线是什么（一句话）、支线怎么挂在主线上；'
        '**伏笔是怎么埋的、隔多久回收**（埋的时候读者知不知道那是伏笔）；'
        '一次释放给读者多少信息、藏多少。',
        '主线一句话 + 伏笔的埋与收的规律 + 信息释放节奏。',
    ),
    Dimension(
        'structure', '结构与单元',
        '这本书怎么分单元（每几章一件事）、单元之间怎么递进、'
        '**每一个单元自己的起承转合**是什么样。',
        '单元长度与递进方式 + 一个单元的典型形状。',
    ),
    Dimension(
        'voice', '语言与文风',
        '句子长短、对话与叙述的比例、叙述视角贴着谁、'
        '**哪些句子是这本书独有的味道**（不是好词好句，是"这种话只有这本书会这么写"）。',
        '文风几条可照着写的特征（要具体到能执行，不要"文笔细腻"这种话）。',
    ),
    Dimension(
        'world', '设定投放',
        '世界观是**怎么交给读者的**（一上来讲一遍，还是散在情节里一点点给）；'
        '设定与情节怎么互相推动。',
        '设定投放方式 + 设定推动情节的例子。',
    ),
)

#: 粗扫/精拆/归纳各阶段该问的维度（拆全书骨架时不必逐维问一遍）
# [EN] : the dimensions to ask at each stage of rough scan / fine dismantle / synthesis (when
# [EN] dismantling the book's skeleton you don't need to ask every dimension)
SCAN_DIMS = ('skeleton', 'emotion', 'plot')
DEEP_DIMS = ('character', 'voice', 'emotion', 'skeleton')
FINAL_DIMS = ('skeleton', 'character', 'emotion', 'plot', 'structure', 'voice', 'world')

# ══════════════════════════════════════════════════════════════
#  ★★★ 专业书 / 资料书那一套（2026-10-27）
#
#  用户原话：「我是不是可以找一些中国古代建筑史等书籍来拆书进而增加相关 SKILL
#  …让它可以拆小说 也可以拆各种专业书籍 用来做素材」。
#
#  ★ 关键：**不是把上面七维换个说法**。专业书里没有人物、没有情绪曲线、
#    没有伏笔 —— 硬套七维的结果是"拆出一本谁也用不上的空话"。
#    专业书该拆的是**素材条目**：一条能被查证、能被引用、能被拿去写的事实。
#
#  ⚠ 提示词里的**例子不许出现具体的术语/名词**（本项目的老纪律：
#    提示词里的例子会被模型当素材抄 —— 若这里写"斗拱"，拆任何一本建筑书
#    都会抄出一条"斗拱"）。所以例子一律用"某术语 / 某做法"这种占位。
# [EN] ★★★ The reference / specialist-book set (2026-10-27)
# [EN] User: "could I feed in a history of Chinese architecture ... make it split novels **and**
# [EN] specialist books, for material".
# [EN] ★ The point: this is **not** the seven dimensions above with different words. A reference
# [EN] book has no characters, no emotional curve, no foreshadowing -- force-fitting the seven
# [EN] yields "a book of empty talk nobody can use". What a reference book should be split into is
# [EN] **material entries**: facts that can be checked, cited, and written from.
# [EN] ⚠ **No concrete term may appear in the prompts' examples** (a standing rule here: models copy
# [EN] the examples in a prompt as if they were material -- write "斗拱" here and every architecture
# [EN] book splits out a "斗拱" entry). Hence placeholders like "某术语 / 某做法".
# ══════════════════════════════════════════════════════════════

REF_DIMENSIONS: tuple[Dimension, ...] = (
    Dimension(
        'term', '术语与其含义',
        '这本书里**哪些词是有专门含义的**：一个词在这本书里指什么、'
        '不同时代/不同流派叫法有什么差别、它和哪个词容易混。'
        '★ 只收**这本书真的定义了**的，不收顺手提到的。',
        '每条：名字 = 这本书里的定义（一句话）+ 容易混的那个词。',
    ),
    Dimension(
        'fact', '可查证的事实与数据',
        '带**数字、年代、地名、制度名**的硬事实：尺寸、用量、造价、年代、'
        '谁在什么时候定下来的。★ 数字必须照抄（改一个零就全错），'
        '并且**写清它成立的范围**（哪朝、哪地、哪一等）。',
        '每条：一句话事实 + 成立范围 + 原书给的出处。',
    ),
    Dimension(
        'rule', '规矩 / 做法 / 禁忌',
        '这件事**该怎么做、不许怎么做**：等级规矩、施工次序、礼制禁忌、'
        '犯了会怎么样。★ 这类最能直接拿去写（"他不敢这么盖，因为……"）。',
        '每条：规矩一句话 + 谁受它约束 + 违反了是什么后果。',
    ),
    Dimension(
        'case', '实例 / 个案',
        '书里举的**真实例子**（哪座建筑、哪件事、哪个人）：它之所以被举出来，'
        '是因为它典型，还是因为它例外。',
        '每条：例子一句话 + 它是"典型"还是"例外"。',
    ),
    Dimension(
        'caveat', '易错处 / 有争议处',
        '作者**明确提醒过**的坑：常见误解、断代有争议的说法、'
        '后人穿凿的说法。★ 这是最有价值的一类 —— 它直接防住"写错了还不知道"。',
        '每条：坑一句话 + 正确的说法是什么。',
    ),
)

#: 专业书粗扫 / 精拆 / 归纳各问哪些维度
# [EN] : Which dimensions to ask at each stage for a reference book
REF_SCAN_DIMS = ('term', 'fact', 'rule')
REF_DEEP_DIMS = ('term', 'fact', 'rule', 'caveat')
REF_FINAL_DIMS = ('term', 'fact', 'rule', 'case', 'caveat')

#: ★ 专业书的**五门禁**（替代小说那五条 —— 小说的"情绪链/戏剧单元"在这里毫无意义）。
#:   每条条目都必须写明这五项，缺一项就记账（与小说同一条纪律）。
# [EN] : ★ The reference book's **five gates** (replacing the novel's five -- "emotional chain /
# [EN] dramatic unit" are meaningless here). Every entry must state all five; a missing one is
# [EN] booked (the same rule as for novels).
REF_GATES: tuple[str, ...] = (
    '这条能怎么用',      # 写的时候具体怎么用（不是"很有参考价值"这种话）
    '可信度',            # 通说 / 作者一家之言 / 有争议
    '边界条件',           # 哪朝哪地哪一等成立；换个地方还成立吗
    '可替换项',          # 换个题材还能用吗（能换去哪）
    '不可照搬',          # 哪些是用不了的（现代术语、作者推测、断代存疑）
)

#: 专业书条目**最少要几条**才算拆出东西（低于这个数就是"读完了但没拆出东西"）
# [EN] : Minimum number of entries before we say a reference book was actually split
REF_MIN_ENTRIES = 8


def by_key(key: str) -> Dimension | None:
    # ★ 2026-10-27：专业书的维度在 `REF_DIMENSIONS` 里（**另一张表**）。
    #   只查 `DIMENSIONS` 时 `dims_text(REF_DEEP_DIMS)` 会**静默返回空串** ——
    #   提示词里那一段"这一次要拆的维度"直接是空的，模型等于没收到要求，
    #   而这个错**不报错**（提示词照发、钱照花）。
    # [EN] ★ 2026-10-27: reference-book dimensions live in `REF_DIMENSIONS` (**a separate table**).
    # [EN] Querying only `DIMENSIONS` makes `dims_text(REF_DEEP_DIMS)` **silently return an empty
    # [EN] string** -- the "what to dissect this time" section of the prompt is simply blank, the
    # [EN] model never receives the requirement, and **nothing raises** (prompt sent, money spent).
    for table in (DIMENSIONS, REF_DIMENSIONS):
        for d in table:
            if d.key == key:
                return d
    return None


def dims_text(keys: tuple[str, ...] = FINAL_DIMS) -> str:
    """把选中的维度拼成"这次要拆哪几样"（进提示词）。
        English:
    Assemble the selected dimensions into "what to dissect this time" (into the prompt).
    """
    rows: list[str] = []
    for k in keys:
        d = by_key(k)
        if d:
            rows.append(f'### {d.name}\n{d.ask}\n**要产出**：{d.out}')
    return '\n\n'.join(rows)


def names_of(keys: tuple[str, ...]) -> list[str]:
    return [d.name for d in (by_key(k) for k in keys) if d]


# ══════════════════════════════════════════════════════════════
#  提示词
# [EN] Prompt
# ══════════════════════════════════════════════════════════════
#: 粗扫（第 ② 道工序）：一批章 → 每章一句话 + 功能 + 情绪强度
# [EN] : Rough scan (process ②): a batch of chapters → one sentence per chapter + function + emotional
# [EN] intensity
SCAN_PROMPT = """你是一个**拆书的人**。下面是一本书其中一批章节的**开头部分**。

你的活不是评价这本书好不好，而是**看清它在干什么**。

── 这是本什么书 ──
书名：{title}
类型：{genre}
{prefer}
── 这一批（第 {lo}~{hi} 章）──
{chapters}

要求（这是"看一眼这一章在干什么"，不是精读）：

1. 逐章给一条：**这一章干了什么**，一句话，写清"谁做了什么、结果如何"。
   **不要写细节、不要写好词好句、不要复述对话。**
2. 给这一章一个**功能**（从这几个里挑，可以多选）：
   `推进主线` / `立人设` / `埋伏笔` / `收伏笔` / `放钩子` / `制造情绪` / `铺垫` / `过渡`
3. 给一个**情绪强度** 0~5（0 = 平淡过渡，3 = 有明显起伏，5 = 大爆点）。
   判断标准是"读者的心跳快不快"，不是"事情大不大"。
4. 每章给一个**章末钩子类型**：`悬念` / `反转` / `预告` / `情绪` / `无`。

只输出 JSON，不要围栏、不要解释：
{{"章": [{{"章": "第1章 标题", "一句话": "…", "功能": ["推进主线"], "情绪": 3, "钩子": "悬念"}}],
  "这一批的观察": "一两句：这一批整体在做什么"}}"""


#: 精拆（第 ③ 道工序）：挑出来的重点章，逐段看手法
# [EN] : Fine dismantle (process ③): the selected key chapters, look at technique paragraph by
# [EN] paragraph
DEEP_PROMPT = """你是一个**拆书的人**，正在**精读**这本书挑出来的重点章节。

粗扫告诉你这几章是这本书最要紧的地方。现在要看清的是：**作者到底怎么写的。**

── 这是本什么书 ──
书名：{title}
类型：{genre}
{prefer}
── 重点看这几样 ──
{dims}

── 要精读的部分 ──
{chapters}

要求：

1. **先定位再说话**：每一条都要指出"**这是哪一章、大致什么位置**"。
   说不清出处的结论不要写 —— 那是读后感，不是拆书。
2. **说手法，不是夸作品**。禁止写"写得很好""很精彩""引人入胜"这类话 ——
   要说的是"**他在这里做了 X，所以读者会有 Y 的感觉**"。
3. 对每一个拆解点，写清三件事：
   `怎么写的`（具体到句子/段落/结构上的做法）· `为什么有效`（读者那边发生了什么）·
   `怎么用`（换成别的故事，这一招还能怎么使）。
4. 至少 4 条、至多 8 条。**宁可少写几条但每条都在点上。**

只输出 JSON，不要围栏：
{{"拆解": [{{"维度": "人物塑造", "出处": "第3章 开头", "怎么写的": "…",
            "为什么有效": "…", "怎么用": "…"}}],
  "这几章的结论": "一两句"}}"""


#: 归纳（第 ④ 道工序）：跨章提炼成**可复用的模块**
# [EN] : Synthesis (process ④): distill across chapters into **reusable modules**
FINAL_PROMPT = """你在**拆一本书**，前面已经读完了：全书的分章概览、几处重点章节的精读笔记。
现在做最后一步，也是**最要紧的一步**：把笔记变成**能拿走的东西**。

── 这是本什么书 ──
书名：{title}
类型：{genre}
用户说这本好在：{good}
{prefer}
── 全书概览（每章一句 + 功能 + 情绪）──
{scan}

── 重点章节的精读笔记 ──
{deep}

要求：

**第一步的自觉：分清"关于这本书的"和"能拿走的"。**
"第 12 章主角在码头认出了那个人" —— 这是前者，扔掉。
"**怎么让一次相认同时完成三件事**（推进主线、翻一个人物的底、回收一条伏笔）"
—— 这是后者，留下。

1. `模块`：3~6 条**可复用的写法**。每条写下面这些字段 ——
   ★ **前五个是"门禁"，缺任何一个这一条就不算拆出来**（不必凑，宁可少给一条）。

   **门禁五条**（决定这一招**能不能跨书用**）：
   · `读者想看什么` —— 这一招满足的是读者哪一句**抽象**需求（不是这本书的情节）
   · `情绪链` —— 读者的情绪怎么走：缺口 → 加压 → 触发 → 爆发 → 余波（用箭头写）
   · `戏剧单元` —— **去掉素材之后**剩下的那个结构
     （例："被轻视的人在一个公开场合用结果反证"——里面没有一个人名、一个地名）
   · `可替换项` —— 哪些位置可以整体换掉。**必须写成「功能位→任意X」**，
     例：`欺压者→任何压制主角的人`、`证据→任何能当场翻盘的东西`。
     ⚠ **不许写成「原书专名→任意X」**（写成 `王掌柜→任意人` 这种＝把这本书的专名
       抄进了机制卡，等于没抽象）。这一条是**格式要求**，写不对就不算数。
   · `不可照搬` —— 这一招里**哪些东西绝对不能跟着搬**（原文的专名、独有设定、
     标志性台词、事件的具体顺序）。这里**允许也必须**点名这本书的专名 —— 点名是它的职责。

   **工艺五条**（决定这一招**怎么用**）：
   · `名称` —— 给这一招起个能记住的名字（六到十二个字）
   · `怎么做` —— 具体到能照着执行（两三句）
   · `什么时候用` —— 什么处境下该想起它
   · `为什么管用` —— 读者/观众那边发生了什么
   · `这本书的例子` —— 一句话说它在这本书里出在哪儿（**只作证，不作内容**）

   **不要抄情节、不要抄原句**，写的是**做法**。`不可照搬` 里点名是为归档，
   其余字段一律不许出现这本书的人名、地名、门派名、书名。
2. `节奏`：这本书的节拍规律（压多长、爆多大、单元多长），要能拿来当模板用。
3. `人设`：这本书立人的共同手法（不是某个人物的设定，是**作者立人的套路**）。
4. `语言`：可照着写的文风特征（具体，不要"文笔细腻"这类评价）。
5. `不适合`：**这本书的做法里，有哪些是换本书就不能用的**（比如"靠主角光环硬解"）。
   这一条不许空着 —— 说不出不适合什么，说明还没看清。
6. `适用`：这本书的类型与它最值得被哪一类故事参考（一句话）。
7. `标签`：给这份拆解打**受控标签**（值**必须**从下面这几轴里选，不在表里的值会被丢弃）：
{tags}
   一轴可以多个值；拿不准的轴**整轴不写**，别硬凑。

只输出 JSON，不要围栏：
{{"模块": [{{"读者想看什么": "…", "情绪链": "…", "戏剧单元": "…",
            "可替换项": ["功能位→任意X", "…"], "不可照搬": ["…"],
            "名称": "…", "怎么做": "…", "什么时候用": "…",
            "为什么管用": "…", "这本书的例子": "…"}}],
  "节奏": "…", "人设": "…", "语言": "…", "不适合": ["…"], "适用": "…",
  "标签": {{"题材": ["…"], "读者需求": ["…"], "情绪": ["…"],
            "剧情功能": ["…"], "适用阶段": ["…"]}}}}"""


# ══════════════════════════════════════════════════════════════
#  EM 卡的**生成时门禁**（2026-10-10 加，来源见下方注释）
# [EN] EM card's **generation-time gate** (added 2026-10-10, source see comment below)
# ══════════════════════════════════════════════════════════════
#: 「门禁五条」—— 缺任何一条，这张卡就**不算拆出来**（`analyzer` 会照实记进 notes，
#: 不静默通过）。
# [EN] : "Five gates" — if any one is missing, this card **does not count as dismantled** (`analyzer`
# [EN] will faithfully record it into notes,
# [EN] : not silently pass).
#:
#: 来历：`zenstory-ai/oh-story-claudecode`（**MIT**，7.4k★）的「可复现模块卡（EM）」
#: 写明**五门禁**＝ `读者想看什么 / 情绪链 / 戏剧单元 / 可替换项 / 不可照搬`，
#: 缺一登记被拒。本项目原来只有 `名称/怎么做/什么时候用/为什么管用/这本书的例子`
#: —— 信息量更少，而且**没有"可替换项 / 不可照搬"这对反抄袭字段**。
#: ★ 采纳的是它的**字段设计**（那是机制，不是代码）；措辞与例子全部按本项目重写。
# [EN] : Origin: `zenstory-ai/oh-story-claudecode` (**MIT**, 7.4k★)'s "reproducible module card (EM)"
# [EN] : states the **five gates** = `what readers want to see / emotional chain / dramatic unit /
# [EN] replaceable items / not to be copied directly`,
# [EN] : missing one is registered as rejected. This project originally only had `name/how to do/when
# [EN] to use/why it works/example from this book`
# [EN] : — less information, and **no "replaceable items / not to be copied directly" pair of
# [EN] anti-plagiarism fields**.
# [EN] : ★ What is adopted is its **field design** (that's the mechanism, not the code); wording and
# [EN] examples are all rewritten for this project.
GATES: tuple[str, ...] = ('读者想看什么', '情绪链', '戏剧单元', '可替换项', '不可照搬')

#: 「可替换项」的**格式要求**：必须写「功能位→任意X」。
# [EN] : **Format requirement** for "replaceable items": must write "function slot→any X".
#:
#: ★★ 这一条是这次借鉴里**最值得记的一个想法**：
#:   它把"反抄袭"从**事后检查**变成了**生成时的格式要求** ——
#:   模型要写 `欺压者→任何压制主角的人`，就不能写 `王掌柜→任意人`；
#:   写成后者，机械检查立刻能判出来（见 `skillgen.leak_check`）。
#:   而"事后查有没有抄"永远查不全：抽象得不够的卡，字面上一个专名都没有，
#:   你没法用一条规则把它抓出来。
# [EN] : ★★ This one is **the most memorable idea** from this borrowing:
# [EN] : it turns "anti-plagiarism" from **post-hoc checking** into a **generation-time format
# [EN] requirement** —
# [EN] : the model has to write `oppressor→anyone who suppresses the protagonist`, it cannot write
# [EN] `Shopkeeper Wang→any person`;
# [EN] : if the latter is written, a mechanical check can immediately detect it (see
# [EN] `skillgen.leak_check`).
# [EN] : And "checking afterward whether anything was copied" can never be complete: a card that isn't
# [EN] abstract enough has literally no proper nouns,
# [EN] :   and you have no way to catch it with a single rule.
REPLACE_ARROW = '→'

# ══════════════════════════════════════════════════════════════
#  专业书的提示词（2026-10-27）
#
#  ★ 与小说那三条**同形不同内容**：外层结构一致（`"章"` 列表 / `"条目"` 列表），
#    这样 `analyzer` 的解析不用写第二套；里面的字段换成专业书真正要问的。
#  ⚠ 例子一律用占位（"某术语 / 某做法"）—— 提示词里的例子会被当素材抄。
# [EN] Prompts for reference books (2026-10-27)
# [EN] ★ **Same shape, different content** as the novel's three: the outer structure matches
# [EN] (`"章"` list / `"条目"` list) so `analyzer` needs no second parser; the fields inside become
# [EN] what a reference book actually asks. ⚠ Examples use placeholders ("某术语 / 某做法") -- the
# [EN] examples in a prompt get copied as if they were material.
# ══════════════════════════════════════════════════════════════
REF_SCAN_PROMPT = """你在**拆一本专业书 / 资料书**（不是小说）。下面是一批章节的开头部分。

★ 专业书里**没有人物、没有情绪曲线、没有伏笔** —— 不要去找这些，找到了也是硬凑。

你的活是看清**这一批在讲什么、值不值得细看**：

── 这是本什么书 ──
书名：{title}
类型：{genre}
{prefer}
── 这一批（第 {lo}~{hi} 章）──
{chapters}

要求（这是"看一眼这一章是干什么的"，不是精读）：

1. 逐章给一条：`专题` —— 这一章在讲哪个专题/哪一类问题（一句话）。
2. 逐章给一个 `密度` 0~5：这一章里**能被查证、能被引用**的硬信息多不多
   （0 = 通篇议论没有硬信息；3 = 有事实但不密；5 = 几乎每段都有事实/数据/规矩）。
   ★ 判的是"硬信息"，不是"字数多不多"。
3. 逐章列出 `条目`：这一章里**可能值得单独拆出来的条目名字**，1~6 个
   （只写名字，不要展开，不要抄整段）。
4. 空章（前言 / 序 / 索引 / 参考文献 / 版权页 / 纯图版）密度给 0，条目给空数组。

只输出 JSON，不要围栏、不要解释：
{{"章": [{{"章": "第3章 标题", "专题": "…", "密度": 4, "条目": ["…", "…"]}}],
  "这一批的观察": "一两句：这一批整体在讲什么"}}"""


#: 精拆：对挑出来的重点章，按专业书维度逐条拆
# [EN] : Fine dismantle: for the selected key chapters, dismantle entry by entry along the
# [EN] reference-book dimensions
REF_DEEP_PROMPT = """你在**拆一本专业书**，正在**精读**挑出来的重点章节。

{prefer}── 这是本什么书 ──
书名：{title}
类型：{genre}

── 这一批重点章 ──
{chapters}

── 这一次要拆的维度 ──
{dims}

要求：

1. 一条一条地拆，每条给下面这些字段：
   · `维度` —— 从上面那些维度里挑一个
   · `名字` —— 这条叫什么（术语名 / 这条规矩的名字）
   · `内容` —— **一句话说清**（★ 用你自己的话**改写**，不许整段抄原文：
                超过 80 字的连续原文是直接侵权，本项目不收）
   · `出处` —— **必填**，写到"第几章"或"第几章第几节"，能写页码就写页码
   · `为什么值得记` —— 它解决了什么具体问题（不是"很有参考价值"这种话）

2. ★ 只收**这一章真的给了**的东西。书里顺手提到但没展开的，不收。
3. 数字照抄（改一个零就全错），并**写清它成立的范围**（哪朝 / 哪地 / 哪一等）。

只输出 JSON，不要围栏：
{{"拆解": [{{"维度": "术语与其含义", "名字": "…", "内容": "…",
            "出处": "第3章", "为什么值得记": "…"}}],
  "这一章的结论": "一两句"}}"""


#: 归纳：把笔记变成**可查证、可引用、能拿去写**的素材条目
# [EN] : Synthesis: turn notes into **checkable, citable, writable** material entries
REF_FINAL_PROMPT = """你在**拆一本专业书**，前面已经读完了：全书的分章概览、几处重点章节的精读笔记。
现在做最后一步：**把笔记变成能拿走的素材**。

── 这是本什么书 ──
书名：{title}
类型：{genre}
用户说这本好在：{good}
{prefer}
── 全书概览（每章的专题 + 信息密度 + 条目名）──
{scan}

── 重点章节的精读笔记 ──
{deep}

要求：

**第一步的自觉：分清"关于这本书的"和"能拿走的"。**
"第 5 章讲完了某做法的演变" —— 这是前者，扔掉。
"**某做法在某朝是这么做的、到某朝变成了那样，因为……**" —— 这是后者，留下。

1. `条目`：{min_entries}~{max_entries} 条**能拿去用的素材**。每条写下面这些字段 ——
   ★ **前五个是"门禁"，缺任何一个这一条就不算拆出来**（不必凑，宁可少给一条）：

   · `名字` —— 这条叫什么
   · `类别` —— `术语` / `事实` / `规矩` / `实例` / `易错` 五选一
   · `内容` —— 一句话。**必须是你自己改写的**，不许整段抄原文（>80 字连续原文不收）
   · `出处` —— **必填**：第几章（能带页码就带）
   · `这条能怎么用` —— 写的时候具体怎么用（要具体到能落笔，不是"很有参考价值"）
   · `可信度` —— `通说` / `作者一家之言` / `有争议` 三选一
   · `边界条件` —— 哪朝 / 哪地 / 哪一等成立；换个地方还成立吗
   · `可替换项` —— 换个题材还能用吗（能换去哪）
   · `不可照搬` —— 哪些是用不了的（现代术语、作者推测、断代存疑的部分）
   · `这本书的例子` —— 原书里的一个具体例子（**一句话，不许成段引用**）

2. `这本书的用法`：一两句，说清这本书的素材**适合喂给什么样的写作任务**。
3. `不适合`：一两句，说清**什么情况下不该用这本书**（它的立场、年代、局限）。

只输出 JSON，不要围栏：
{{"条目": [{{"名字": "…", "类别": "术语", "内容": "…", "出处": "第3章",
            "这条能怎么用": "…", "可信度": "通说", "边界条件": "…",
            "可替换项": "…", "不可照搬": "…", "这本书的例子": "…"}}],
  "这本书的用法": "…", "不适合": "…"}}"""

#: 受控标签的轴（值必须取自 `skills/book-dismantle/标签词表.md`）。
# [EN] : Axes of controlled tags (values must come from `skills/book-dismantle/标签词表.md`).
#:
#: 来历：`sanshanjianke/ai-webnovel-workflow`（MIT）的 `backend-node/tags/*.json`
#: 把"标签"升级成"一个词 + 一组可执行写作参数"；`oh-story` 的索引侧要求
#: **值必须取自 `标签词表.md`**，写入侧与查询侧共用同一张表。
#: 本项目取其**受控词表**这一半（"可执行写作参数"那半与 EM 卡的字段重复，不抄）。
# [EN] : Origin: `sanshanjianke/ai-webnovel-workflow` (MIT)'s `backend-node/tags/*.json`
# [EN] : upgrades "tag" into "one word + a set of executable writing parameters"; the index side of
# [EN] `oh-story` requires
# [EN] : **values must come from `标签词表.md`**, and the write side and query side share the same table.
# [EN] : This project takes its **controlled vocabulary** half (the "executable writing parameters"
# [EN] half overlaps with the EM card's fields, not copied).
TAG_AXES: tuple[str, ...] = ('题材', '读者需求', '情绪', '剧情功能', '适用阶段')
#: 核心轴：命中它给 2 分，其余轴 1 分（来源：oh-story 的"核心轴加权"）
# [EN] : Core axis: hitting it gives 2 points, other axes 1 point (source: `oh-story`'s "core axis
# [EN] weighting")
CORE_AXES: tuple[str, ...] = ('题材', '读者需求', '情绪')

#: 标签词表：轴 → 允许的值（与 `skills/book-dismantle/标签词表.md` **同源**，
#: 那边是给人读的、这里是给程序用的；改动时两边一起改，判据会核对）。
# [EN] : Tag vocabulary: axis → allowed values (same source as `skills/book-dismantle/标签词表.md`,
# [EN] : that side is for humans to read, this side is for the program to use; when changing, change
# [EN] both sides together, the criteria will check).
TAG_VALUES: dict[str, tuple[str, ...]] = {
    '题材': ('悬疑', '玄幻', '都市', '历史', '言情', '科幻', '武侠', '志怪', '其他'),
    '读者需求': ('爽感释放', '情绪宣泄', '解谜满足', '代入沉浸', '见识新奇', '共鸣治愈'),
    '情绪': ('紧张', '压抑', '温情', '悲凉', '荒诞', '热血', '惆怅'),
    '剧情功能': ('开篇立人', '反转', '揭秘', '收束', '过渡', '攀峰', '余波'),
    '适用阶段': ('开头', '中段', '收尾', '全篇'),
}


def norm_tags(raw) -> dict[str, list[str]]:
    """把模型给的标签规整成**受控值**（不在词表里的丢弃，并**照实报告**）。

    返回 `{轴: [值, ...]}`。**不做同义词猜测** —— 猜错会把一份"玄幻"的拆解
    挂到"悬疑"上，那是静默错误里最难查的一种。丢掉的值由调用方记进 notes。
    
        English:
    Normalize the labels given by the model into **controlled values** (discard those not in the
    vocabulary, and **report faithfully**).
        Return `{axis: [value, ...]}`. **Do not guess synonyms** —— a wrong guess will attach a "xuanhuan" dissection
        to "suspense", which is one of the hardest silent errors to track down. Discarded values are recorded into notes by the caller.
    """
    out: dict[str, list[str]] = {}
    if not isinstance(raw, dict):
        return out
    for axis, vals in raw.items():
        a = str(axis or '').strip()
        allowed = TAG_VALUES.get(a)
        if not allowed:
            continue
        if isinstance(vals, str):
            vals = [vals]
        keep: list[str] = []
        for v in (vals or []):
            s = str(v or '').strip()
            if s in allowed and s not in keep:
                keep.append(s)
        if keep:
            out[a] = keep
    return out


def tags_text() -> str:
    """给提示词用的受控词表（一行一轴）。
        English:
    Controlled vocabulary for the prompt (one axis per line).
    """
    return '\n'.join(f'  · `{a}`：' + ' / '.join(vs) for a, vs in TAG_VALUES.items())


# ══════════════════════════════════════════════════════════════
#  首问（对话框那四个问题）
# [EN] First questions (the four questions in the dialog)
# ══════════════════════════════════════════════════════════════
#: 打开拆书对话框要问的四件事（用户点名要问的）。
#: `key` 是内部字段名，`ask` 是问法，`hint` 是给用户的提示。
# [EN] : The four things to ask when opening the book-dismantle dialog (the user specifically asked to
# [EN] ask these).
# [EN] : `key` is the internal field name, `ask` is the way to ask, `hint` is the hint given to the
# [EN] user.
QUESTIONS: tuple[dict, ...] = (
    {'key': 'title', 'ask': '这本书叫什么',
     'hint': '随便写 —— 它只用来给拆出来的技能包命名'},
    {'key': 'genre', 'ask': '它是什么类型',
     'hint': '比如"年代文·群像""悬疑·单元剧"。写得越准，'
             '以后越容易在同类书上被用起来'},
    {'key': 'good', 'ask': '你觉得它哪些地方好',
     'hint': '哪一段、哪个人物、哪种写法让你觉得"这个我写不出来"。'
             '**这一条最要紧** —— 拆解会重点看这些地方'},
    {'key': 'focus', 'ask': '想重点拆什么',
     'hint': '比如"对话怎么写得像真人""怎么让人物立住""节奏怎么控"。'
             '不填就按标准维度全拆一遍'},
)

#: 四个问题都空着也能跑（但要说清"什么都没说 → 按标准来"）
# [EN] : It can still run with all four questions blank (but must clearly state "nothing said → follow
# [EN] the standard")
DEFAULTS = {'title': '', 'genre': '', 'good': '', 'focus': ''}


def questions_text() -> list[dict]:
    """给界面用（带显示名）。
        English:
    For the UI (with display names).
    """
    return [dict(q) for q in QUESTIONS]


def focus_line(focus: str) -> str:
    """把"重点拆什么"变成提示词里的一句（空则返回空串）。
        English:
    Turn "what to focus dissecting" into a sentence in the prompt (return an empty string if empty).
    """
    f = ' '.join(str(focus or '').split())
    if not f:
        return ''
    return (f'【作者特别想拆的】**{f}** —— 上面那些维度里，'
            '凡是能和这一条挂上的，都要多说几句；挂不上的可以少说。')


def prefer_line(good: str) -> str:
    """把"觉得哪里好"变成提示词里的一段（空则返回空串）。
        English:
    Turn "what feels good" into a paragraph in the prompt (return an empty string if empty).
    """
    g = ' '.join(str(good or '').split())
    if not g:
        return ''
    return (f'【作者认为这本书好在】{g}\n'
            '—— 拆的时候**优先看这些地方**：它们好在哪儿、用的什么办法。')
