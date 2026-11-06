# -*- coding: utf-8 -*-
"""认知模式层：把「思维链 / 反思链 / 组合」三种设计模式收在一处。

为什么要单独一个文件
--------------------
参考《AI Agent 从入门到精通》第四章（智能体经典范式）与第七章（构建你的
Agent 框架）里那几种范式，本项目**用得上、又不该散着装**的只有三种：

| 范式（教程里的名字） | 在本项目里长什么样 | 为什么用它 |
|---|---|---|
| **思维链 CoT** | 一次调用里**先想后答**：先填 `推演/构思`，再填动作/分拍/台词 | 人物"开口之前心里先过一遍"，台词才像人说的；且**零额外调用** |
| **反思链 Reflection** | **执行 → 反思 → 优化**：产出之后换一双眼睛审，有问题就重做 | 剧本侧本来就有（验算/排练/复盘），台词侧缺一条（见 `looks_unnatural`）|
| **组合（ReAct + Reflection）** | `polish.PolishAgent` 那条（工具循环 + 自省）与三人小组那条 | 已经是现成的，这里只做**登记**，不重造 |

三条纪律（与 `craft/craftmix` 同源）
----------------------------------
1. **模式是数据、注入是实现**。16 个职位各自往提示词里手写"先想后答"，
   迟早漂成 16 种说法；所以模式表在这里一份，注入函数也只有这里一份。
2. **思考步骤必须从工艺库长出来**（`craft/playbooks/*.yaml`）——
   不给模型发明新理论。`cot_block()` 里每一条自问都挂一个**该职位已经在读的
   条目名**，并把那条的「提示词」真取出来贴在旁边（`craftmix.resolve_entry`）。
   取不到就只留自问（**不编一条手艺**）。
3. **关掉就逐字退回**。`COGNITION=false` 时 `cot_block()` 一律返回空串 ——
   调用方不必各写一个 `if`，"退回老行为"因此是**结构保证**而不是靠自觉。

⚠ 与 `crew/agents.craft_block` 的分工（别混）：
  · `craft_block` 给的是**手艺内容**（这一行怎么干，按货架/点名取）；
  · 这里给的是**思考骨架**（按什么顺序自问）。两者都在提示词里，位置不同：
    手艺在前（背景），骨架紧挨着输出（纪律）。

English:
Cognitive pattern layer: gathers the three design patterns "chain-of-thought / reflection chain
/ composition" in one place.
Why a separate file
--------------------
Referencing Chapter 4 (classic agent paradigms) and Chapter 7 (building your
Agent framework) of 《AI Agent 从入门到精通》, of those paradigms, only three are **useful to this
project and should not be scattered around**:
| Paradigm (name in the tutorial) | What it looks like in this project | Why use it |
|---|---|---|
| **Chain-of-Thought CoT** | In one call, **think first, then answer**: first fill in `推演/构思`, then fill in action/beats/dialogue | Characters "run it through their head before speaking", so the dialogue sounds human; and **zero extra calls** |
| **Reflection chain Reflection** | **execute -> reflect -> optimize**: after producing, review with a fresh pair of eyes, and redo if there is a problem | The script side already has it (verification/rehearsal/review), the dialogue side is missing one (see `looks_unnatural`) |
| **Composition (ReAct + Reflection)** | The one in `polish.PolishAgent` (tool loop + self-reflection) and the one for the three-person group | Both already exist, here we only **register** them, not rebuild them |
Three disciplines (same origin as `craft/craftmix`)
----------------------------------
1. **Patterns are data, injection is implementation**. If all 16 roles each hand-write "think first, then answer" into their prompts,
   sooner or later it drifts into 16 different phrasings; so the pattern table is only here in one copy, and the injection function is also only here in one copy.
2. **The thinking steps must grow out of the craft library** (`craft/playbooks/*.yaml`) --
   do not invent new theories for the model. In `cot_block()`, every self-question is attached to an **entry name that this role is already reading**, and the "prompt" of that entry is actually fetched and pasted alongside it (`craftmix.resolve_entry`).
   If it cannot be fetched, keep only the self-question (**do not make up a craft**).
   3. **Turn it off and it reverts verbatim**. When `COGNITION=false`, `cot_block()` always returns the empty string --
callers do not need to each write an `if`, so "reverting to old behavior" is a **structural guarantee** rather than relying on discipline.
⚠ Division of labor with `crew/agents.craft_block` (do not mix them up):
· `craft_block` provides **craft content** (how to do this line, fetched by shelf or by name);
  · Here it provides the **thinking skeleton** (in what order to ask yourself). Both are in the prompt, at different positions:
  craft comes first (background), the skeleton sits right next to the output (discipline).
Whether this role should carry the thinking skeleton right now (master switch + sub-switch).
"""
from __future__ import annotations

import logging

from config import CFG

_LOG = logging.getLogger("nws.cognition")

#: 四种模式（`PATTERN` 的取值）
COT = 'cot'            # 思维链：单次调用内先想后答
REFLECT = 'reflect'    # 反思链：产出后审一遍（执行→反思→优化）
BOTH = 'both'          # 组合：上面两条都用
NONE = 'none'          # **故意的"不引入"**（不是漏掉，理由写在 `_WHY_NONE` 里）
# [EN] : Four modes (values of `PATTERN`)
# [EN] Chain of Thought: think first, then answer within a single call
# [EN] Chain of Reflection: review once after producing (execute -> reflect -> optimize)
# [EN] Combined: use both of the above
# [EN] **Deliberate "non-introduction"** (not an omission, reason written in `_WHY_NONE`)


# ══════════════════════════════════════════════════════════════════
#  模式表（**数据**：每个 Agent 用哪种模式、为什么）
# [EN] Pattern table (**data**: which pattern each Agent uses, and why)
# ══════════════════════════════════════════════════════════════════
#: Agent 键 → 模式。键与 `crew/roster.ROSTER` 的 key 对齐（另有 `polish_agent`
#: 和 `agent` 两个不在名册上的）。
# [EN] : Agent key -> pattern. Keys align with the keys of `crew/roster.ROSTER` (additionally
# [EN] `polish_agent`
# [EN] : and `agent` are the two not on the roster).
PATTERN: dict[str, str] = {
    # ── 三人小组 + 演员（用户点名要看的四位）──
    'actor':        BOTH,     # 推演（CoT）每拍都用；台词自省（Reflection）见 looks_unnatural
    'screenwriter': BOTH,     # 构思（CoT）+ 验算/排练（既有的反思链）
    'novelist':     BOTH,     # 构思（CoT）+ 导演验算/复盘（既有的反思链）
    'director':     BOTH,     # 派活/挑事前的推演（CoT）+ 验算（既有的反思链）
    # ── 审查型职位：它们本来就是"反思"的落点，补的是**顺序**（先逐条核再结论）──
    # [EN] -- Three-person team + actor (the four the user specifically asked to see) --
    # [EN] Reasoning (CoT) used in every beat; line self-reflection (Reflection) see looks_unnatural
    # [EN] Ideation (CoT) + verification/rehearsal (the existing chain of reflection)
    # [EN] Ideation (CoT) + director verification/review (the existing chain of reflection)
    # [EN] Reasoning before assigning work/stirring things up (CoT) + verification (the existing chain of
    # [EN] reflection)
    # [EN] -- Review-type positions: they are inherently the landing point of "reflection"; what is added
    # [EN] is the **order** (check item by item first, then conclude) --
    'continuity':   COT,
    'researcher':   COT,
    'polisher':     COT,
    # ★★ **剧本审读**（2026-10-08）：审查型里**最需要顺序**的一个 ——
    #   它每拍要判六件事（人话/像不像这个人/接不接上文/一个主题/搭不搭场景/
    #   **像不像活人在说话** ← 2026-10-12 加的最后一件，用户点名），
    #   而模型天生爱"扫一眼就下结论"。骨架把它按住"先逐条读、再看上文、
    #   最后才判主题"的顺序（主题是**合起来**才看得出的事，必须放最后）。
    # [EN] ★★ **Script review** (2026-10-08): among review types, the one that **most needs order** --
    # [EN] It must judge six things per beat (is it human speech / does it seem like this person / does it
    # [EN] connect to the preceding text / one theme / does it fit the scene /
    # [EN] **does it sound like live people talking** <- added 2026-10-12, the last item, named by the
    # [EN] user),
    # [EN] and models are naturally prone to "glance once and conclude". The skeleton holds it to the order
    # [EN] of "read item by item first, then look at the preceding text,
    # [EN] and only judge the theme last" (the theme is something that can only be seen **when combined**,
    # [EN] so it must go last).
    'script_doctor': COT,
    'reviewer':     REFLECT,  # 它**本身**就是复盘 = 反思链的终点，不再套一层
    'rehearsal':    REFLECT,  # 同上：空走一遍就是一次反思
    'settings_room': REFLECT, # 三方会审 = 三个视角互审，不再套一层
    # ── 清单型产出（cheap 档）：输出是"物件/色/声"的清单，先想后答没有增量 ──
    # [EN] It **itself** is the review = the endpoint of the chain of reflection, not nested another layer
    # [EN] Same as above: running through it empty is one reflection
    # [EN] Three-party joint review = three perspectives cross-reviewing, not nested another layer
    # [EN] -- List-type output (cheap tier): the output is a list of "objects/colors/sounds", thinking
    # [EN] first then answering adds no increment --
    'props':        NONE,
    'art':          NONE,
    'stylist':      NONE,
    'sound':        NONE,
    'publicity':    NONE,
    'extra':        NONE,
    # ★ 2026-10-17 补登记（`verify_cognition` A1 报缺这两个）：
    #   `storyboard`（分镜）与 `visref`（视觉参考）都是**清单型产出**，与上面那批同类。
    #   漏登记的后果不是报错，而是它们会走 `cot_block` 的默认分支
    #   （"没登记 = 在心里过一遍"），等于给一张表多加一段推理输出。
    # [EN] ★ Registered 2026-10-17 (`verify_cognition` A1 reported both missing):
    # [EN]   `storyboard` (shot list) and `visref` (visual references) are both **list-type
    # [EN]   outputs**, same class as the batch above. The failure mode is not an error: they
    # [EN]   fall into `cot_block`'s default branch ("unregistered = think it through silently"),
    # [EN]   i.e. one extra reasoning block on top of a table.
    'storyboard':   NONE,
    'visref':       NONE,
    # ── 已经在跑的自主 Agent ──
    # ⚠ `polish_agent` 定 **REFLECT** 而不是 BOTH：它的"先想后做"是 **ReAct**
    #   自带的 Thought 循环（`polish/agent.py` 里那个），**不在这一层重复实现** ——
    #   否则同一件事会写两遍（骨架一份、ReAct 提示词一份），迟早对不上。
    #   所以它在这里只需要登记"它有一条反思链"（`_reflect()` 自省）。
    # [EN] -- Autonomous Agents already running --
    # [EN] ⚠ `polish_agent` is set to **REFLECT** rather than BOTH: its "think first, then do" is the
    # [EN] **ReAct**
    # [EN] built-in Thought loop (the one in `polish/agent.py`), **not reimplemented at this layer** --
    # [EN] otherwise the same thing would be written twice (one in the skeleton, one in the ReAct prompt),
    # [EN] and sooner or later they would not match.
    # [EN] So here it only needs to register "it has a chain of reflection" (`_reflect()` self-reflection).
    'polish_agent': REFLECT,
}

#: `NONE` 的**理由**（写清楚，"不引入"也是设计决定，不是漏做）。
# [EN] : the **reason** for `NONE` (write it clearly, "non-introduction" is also a design decision, not
# [EN] an omission).
_WHY_NONE: dict[str, str] = {
    'props': '产出是"这一场有哪些物件"的清单，且走 cheap 档；先想后答不改变结果，'
             '白花额度。它的质量靠"具体可画"这条硬要求兜。',
    'art': '一次定、全剧用的一条美术指导，输出是画风 + 三色 + 忌；'
           '它已经被 `prompt_prefix()` 直接拼进出图提示词，'
           '再套一层推理只是让这条更晚出来。',
    'stylist': '同上：产出是"谁穿什么"的表，进的是出图提示词。',
    'sound': '产出是"底噪/事件声/静默"三条短句，本身已经要求"具体到哪一下"。',
    'publicity': '写卖点，不是写故事；它读的是已经定稿的正文，不需要推演。',
    'extra': '一次投一个路人，输出三个短字段；走 cheap 档且**规则池兜底**，'
             '给自己加推理反而会让兜底更快被触发。',
    'storyboard': '产出是「第几镜 · 画什么 · 谁在场」的表，直接进下游生图/分镜导出；'
                  '先想后答不改变那张表，只是把镜头描述写晚一步。',
    'visref': '它**一次模型都不调** —— 直接调 `image_gen` 出图 + 记一份清单，'
              '没有"想"这一层可加。',
}

#: 思考字段名（各职位的产出里**那个字段**装它的盘算）。
#: ⚠ 一职一名而不是统一叫 `推演`：界面上/落盘里，一眼能看出是谁在想什么。
# [EN] : the thinking field name (the field in each position's output that holds its deliberation).
# [EN] : ⚠ one name per position rather than uniformly calling it `reasoning`: on the UI / on disk, you
# [EN] can tell at a glance who is thinking what.
#:
#: ⚠ **没登记在这张表里的职位 = "在心里过一遍、不写出来"**（见 `cot_block`）。
#:   这不是漏了，是对**散文产出**的职位故意的：小说作家的产出是要原样交给
#:   剧作者的**正文**，让它多写一个 `构思` 字段，剧作者就得先剥掉那一段 ——
#:   多一道剥壳就多一种"没剥干净，构思跑到样章里去了"的坏法，而收益只是
#:   让日志里多几行。所以作家的骨架**只进提示词**（模型自己的思考过程），
#:   不要求它落成字段。
# [EN] : ⚠ **positions not registered in this table = "run through it in the mind, do not write it
# [EN] out"** (see `cot_block`).
# [EN] : This is not an omission; it is deliberate for positions with **prose output**: the novelist's
# [EN] output is meant to be handed over as-is to
# [EN] : the playwright's **main text**; making it write an extra `ideation` field would force the
# [EN] playwright to strip that passage first --
# [EN] : one more shell to peel means one more failure mode of "not peeled cleanly, ideation leaked
# [EN] into the sample chapter", while the benefit is only
# [EN] : a few more lines in the log. So the writer's skeleton **only goes into the prompt** (the
# [EN] model's own thought process),
# [EN] :   and it is not required to persist it as a field.
THINK_FIELD: dict[str, str] = {
    'actor':        '推演',
    'screenwriter': '构思',
    'director':     '推演',
    'continuity':   '核查',
    'researcher':   '核查',
    'polisher':     '核查',
    'script_doctor': '核查',
}


# ══════════════════════════════════════════════════════════════════
#  思考骨架（**顺序**：按这个顺序自问，答案压进思考字段）
# [EN] Thinking skeleton (**order**: ask yourself in this order, press the answers into the thinking
# [EN] field)
# ══════════════════════════════════════════════════════════════════
#: `key → ((自问, 出处条目名), …)`。
# [EN] : `key -> ((self-question, source entry name), ...)`.
#:
#: `出处条目名` **必须**是该职位 `crew/agents.SHELVES` + `READS` 里读得到的
#: 那几条之一（判断依据见 `tools/verify_cognition.py` 的 B 组）——
#: 骨架问的是"手艺里那几条，按什么顺序用"，不是新发明一批理论。
#: 条目名写空串 = 这条自问不挂手艺（那就只留自问，别硬凑一个出处）。
# [EN] : `source entry name` **must** be one of those readable from that position's
# [EN] `crew/agents.SHELVES` + `READS`
# [EN] : (for the basis of judgment see group B in `tools/verify_cognition.py`) --
# [EN] : the skeleton asks "among those items in the craft, in what order are they used", not inventing
# [EN] a batch of new theories.
# [EN] : entry name written as an empty string = this self-question is not tied to a craft item (then
# [EN] just keep the self-question, do not force a source).
#: 精简档（`cot_block(..., compact=True)`）**保留哪几问** —— 按措辞里的关键词认。
#: ★ 只留「换给别人说成不成立」那一问：五问里只有它直接检验
#:   "这句话是不是**这个**人的"，其余四问（要什么 / 刚才那句对我做了什么 /
#:   多长 / 什么声音）在松档属于"怎么写"的规定，一并交给模型自己。
# ⚠ 关键词必须与 `THINK_STEPS` 里的措辞一致；改了措辞这里要跟着改
#   （`verify_agent_freedom` 有一条判"精简版真的只剩一问"，改漏了会红）。
# [EN] Which questions the compact band keeps, matched by keyword. ★ Only "would it hold if
# [EN] someone else said it" -- the only one testing "is this line **this** person's"; the other
# [EN] four are "how to write" rules that the loose band hands back to the model.
# [EN] ⚠ Keywords must match `THINK_STEPS`; a check guards "compact really leaves one".
_COMPACT_KEEP: tuple[str, ...] = ('换给别人说', '别人说成不成立')

THINK_STEPS: dict[str, tuple[tuple[str, str], ...]] = {
    # ── 演员：全项目**输出台词最多**的职位，"开口之前先过一遍"就落在这里 ──
    # [EN] -- Actor: the position with the **most line output** in the whole project, "run through it
    # [EN] before speaking" lands right here --
    'actor': (
        ('我此刻**要什么**（这一步的目的，一句话说清）', '一句台词办四件事'),
        ('**[刚才]**那一句（或那件事）对我做了什么 —— 我该接、该岔开、'
         '还是该当没听见？', '停顿与不答也是台词'),
        ('这一句**换给别人说**成不成立？不成立才算说到我身上了。',
         '说话方式就是身份'),
        ('我该说**多长**？落了下风就说半句；能不答就用一个动作带过去。',
         '话长短由处境定'),
        # ★ 2026-10-12（用户点名："很容易吼 而不是正常说话"）——**开口前最后一个念头**。
        #   位置是刻意的：它是"这句话从我嘴里出来是什么样"，紧挨着那句台词，
        #   比任何写在别处的纪律都管用（模型最后看到的那个问题，就是它回答的方向）。
        # [EN] ★ 2026-10-12 (the user named this: "it shouts easily instead of speaking normally") --
        # [EN] **the last thought before speaking**.
        # [EN] The position is deliberate: it is "what this sentence sounds like coming out of my mouth",
        # [EN] right next to the line itself, which works better than any discipline written elsewhere (the
        # [EN] last question the model sees is the direction it answers in).
        ('这句话该用什么**声音**说？**平常声够了吗** —— 真到了要喊的地步，'
         '就得付那份代价（旁人回头、事后哑了）。', '音量是稀缺的'),
    ),
    # ── 剧作者：把样章改成"能拍的一串事" ──
    # [EN] -- Playwright: turn the sample chapter into "a string of shootable events" --
    'screenwriter': (
        ('这一天**变的是什么**（从怎样变成怎样）？', '一场一转变'),
        ('分几拍？**每一拍各自**变什么 —— 说不出转变的那拍就该删。',
         '一场一转变'),
        ('谁、在哪儿、做什么、说什么 —— 四样齐了才是戏。', '可拍性检查'),
        ('进场出场的人**带动了什么**？别让谁白走一趟。', '上场下场都带戏'),
        ('人多了要主次分明：这一拍只让两三个人推事情。', '群像调度'),
    ),
    # ── 小说作家：这一章怎么写成"读下去"的样子 ──
    # [EN] -- Novelist: how to write this chapter into something that "reads on" --
    'novelist': (
        ('这一章**变的是什么**？写给谁看、他看完记住了哪一下？', '起承转合'),
        ('这一章要有一个**让人记住的场面** —— 谁在哪儿撞上了什么？',
         '反差要撞给读者看'),
        ('人物做的每件事，都**指得回主线**吗？', '草蛇灰线'),
        ('结尾留一个**未了**，让人接得下去。', '期待感管理'),
    ),
    # ── 导演（派活/挑事）：先看清"卡在哪儿"，再动手 ──
    # [EN] -- Director (assigning work/stirring things up): first see clearly "where it is stuck", then act
    # [EN] --
    'director': (
        ('这一拍**最该被推进**的是哪一件事？说不出来就先别派。',
         '场景=价值转变'),
        ('每个人现在**离他要的东西还差什么**？', '期望鸿沟'),
        ('我派的必须是**要达成什么**，不是"怎么做" —— '
         '写死了他就成了提线木偶。', '期望鸿沟'),
    ),
    # ── 审查型：补的是**顺序**（先逐条核，再下结论）──
    # [EN] -- Review type: what is added is the **order** (check item by item first, then conclude) --
    'continuity': (
        ('**先逐条核**：时间对不对？物件对不对？一条一条过，别跳。',
         '一场一转变'),
        ('再核**称呼与在场**：谁该在场、谁已经走了。', '上场下场都带戏'),
        ('最后才下结论 —— **核不出来的不要报**。', '群像调度'),
    ),
    'researcher': (
        ('先把**名物 / 制度 / 称谓 / 手续**逐个挑出来：哪些真的会被查出来。',
         '权谋布局'),
        ('再判**站不站得住** —— 查不到就明说查不到，**不编**。', ''),
    ),
    'polisher': (
        ('这**一句**像不像这个人会说的话？换个人说成不成立？',
         '说话方式就是身份'),
        ('它是**绕**、是**空**、还是**在解释**？', '文气'),
        ('改法只给**方向**，不要替他重写。', '独白节制'),
    ),
    'script_doctor': (
        ('**先逐条读**这一批新的：哪一条我读不通？哪一条的人物没做任何事？'
         '（一条一条过，别跳）', '上场下场都带戏'),
        ('**再把每一条放回上文**：它是接哪一句说的？那个称呼对着的是谁？',
         '称呼一变关系就变'),
        ('这句**换个人说**成不成立？换个场合说成不成立？', '说话方式就是身份'),
        # ★ 2026-10-12（用户点名）：审读要能一眼看出"这段不像活人说话"。
        # [EN] ★ 2026-10-12 (the user named this): the review must be able to see at a glance that "this
        # [EN] does not sound like live people talking".
        ('这一批**有活人的样子吗**？有人句句都接上、全程在吼、'
         '一口气把三件事说完？', '音量是稀缺的'),
        ('**最后才判主题**：这一批合起来在说哪一件事？（说不到一起就是散）',
         '群像靠执念分层'),
    ),
}


# ══════════════════════════════════════════════════════════════════
#  注入
# [EN] Injection
# ══════════════════════════════════════════════════════════════════
def _enabled(key: str) -> bool:
    """这个职位现在要不要带思考骨架（总闸 + 分闸）。

    ⚠ 分闸的两档是**按"谁在产出故事"分的**，不是按职位表：
      演员那一路每拍都跑（最贵），单独一个开关；剧组那一路一天几次（便宜），
      共用一个。这样用户想省额度时是"关掉最贵的那一路"，而不是逐职位去关。
    
        English:
    ⚠ The two sub-switch tiers are **divided by "who is producing the story"**, not by the role
    table:
        the actor path runs every beat (most expensive), a separate switch; the crew path runs a few times a day (cheap),
          sharing one. This way, when the user wants to save quota, it is "turn off the most expensive path", rather than turning off roles one by one.
        Which pattern this Agent uses (returns `NONE` if unrecognized -- unlike the roster `role()` which throws an exception:
    """
    if not CFG.b('COGNITION'):
        return False
    return CFG.b('COT_ACTOR' if str(key) == 'actor' else 'COT_CREW')


def pattern(key: str) -> str:
    """这个 Agent 用哪种模式（认不出返回 `NONE` —— 与名册 `role()` 抛异常不同：
    模式表是可以"还没登记"的，那不代表产品坏了）。
        English:
    the pattern table can be "not yet registered", and that does not mean the product is broken).
        The thinking field name (returns the empty string if this role has none).
    """
    return PATTERN.get(str(key or '').strip(), NONE)


def think_field(key: str) -> str:
    """思考字段名（这个职位没有就返回空串）。
        English:
    The **reason** for `NONE` (for docs/criteria to read; other patterns return the empty string).
    """
    return THINK_FIELD.get(str(key or '').strip(), '')


def why_none(key: str) -> str:
    """`NONE` 的**理由**（给文档/判据读；别的模式返回空串）。

    ⚠ 写这个函数是为了让 `_WHY_NONE` **不是死数据**（本项目对"挂着没人看"
      零容忍）：`verify_cognition` 的 A 组会遍历模式表，凡 `NONE` 的
      必须在这里说得出理由，说不出来就红。
    
        English:
    ⚠ This function is written so that `_WHY_NONE` **is not dead data** (this project has
        zero tolerance for "hanging there with nobody reading it"): group A of `verify_cognition` iterates the pattern table, and anything `NONE`
          must be able to state its reason here, or it goes red.
        This role's cognitive pattern, **one line of Chinese** (that column in the crew ledger).
    """
    k = str(key or '').strip()
    if pattern(k) != NONE:
        return ''
    return _WHY_NONE.get(k, '')


#: 模式的中文短标签（**给人看**：剧组台账里那一列）。
# [EN] : the Chinese short label of the pattern (**for humans**: that column in the crew ledger).
MODE_LABEL: dict[str, str] = {
    COT: '思维链',
    REFLECT: '反思链',
    BOTH: '思维链+反思',
    NONE: '—',
}


def label(key: str) -> str:
    """这个职位的认知模式，**一行中文**（剧组台账里那一列）。

    为什么要有它：模式表如果只有判据在读，那它和"写着好看的注释"就没区别了。
    台账是**作者会翻的那一页** —— 在那儿写清"谁先想后答、谁只是审",
    这张表才算真的被用到（`pattern()` 也因此有了产品侧的读者）。
    
        English:
    Why it exists: if the pattern table is only read by the criteria, then it is no different from
    "a comment written to look good".
        The ledger is **the page the author will flip through** -- writing clearly there "who thinks first then answers, who only reviews",
        is what makes this table actually used (`pattern()` thereby also gains a product-side reader).
        Replace the source entry name with **the prompt of that entry in the craft library** (actually read; the empty string if it cannot be fetched).
    """
    return MODE_LABEL.get(pattern(str(key or '').strip()), '—')


def _clip(text: str, n: int = 72) -> str:
    s = ' '.join(str(text or '').split())
    return s if len(s) <= n else s[:n - 1].rstrip('，。；、 ') + '…'


def _tip(entry: str) -> str:
    """把出处条目名换成**手艺库里那一条的提示词**（真读，取不到就是空串）。

    为什么非要真取一次：只写条目名的话，模型读到的是一串名词
    （"说话方式就是身份"），它得自己猜那是什么意思；把那一架里写好的
    「提示词」贴出来，骨架才和它手上那本手艺书**是同一句话**。
    
        English:
    Why it must actually be fetched once: if only the entry name is written, what the model reads is
    a string of nouns
        ("speaking style is identity"), and it has to guess what that means; pasting out the "prompt" written in that shelf makes the skeleton **the same sentence** as the craft book in its hands.
        This role's "think first, then answer" skeleton (returns the empty string when it takes no input).
    """
    name = str(entry or '').strip()
    if not name:
        return ''
    try:
        from craft import craftmix
        e = craftmix.resolve_entry(name)
        if not e:
            return ''
        return _clip(str(e.get('提示词') or e.get('原理') or ''), 72)
    except Exception:                                            # noqa: BLE001
        return ''


def cot_block(key: str, compact: bool = False) -> str:
    """这个职位的「先想后答」骨架（不吃任何东西时返回空串）。

    `compact=True` 时只留**最关键的那一问**（见下 `_COMPACT_KEEP`）——
    给"文笔规训调松"那一档用（`agent/freedom.cot_full()` 为假时）。

    ⚠ **精简不是删掉思维链**：完全不挂骨架时，人物决策会退化成
      "看到关键词就反应"（2026-10 实测过）。所以松档保留一问，只是不再
      逼它把五问都过一遍 —— 那五问本身也是一种"写法规定"。
    ⚠ 为什么保留的是「换给别人说成不成立」那一问：它是五问里**唯一**直接
      检验"这句话是不是这个人的"的一问，其余四问（要什么 / 刚才那句
      对我做了什么 / 多长 / 什么声音）在松档交给模型自己判断。
    [EN] The skeleton; `compact=True` keeps only the single most important question,
    [EN] used by the loosest prose band (`freedom.cot_full()` false).
    [EN] ⚠ Compact is **not** removal: with no skeleton at all, decisions degrade into
    [EN] keyword reactions (measured). ⚠ The kept question is "would it hold if someone else said
    [EN] it" -- the only one that directly tests "is this line this person's".

    ⚠ **两道闸，各管一件事**：
      · `THINK_STEPS`（骨架表）= **内容 + 运行时闸门** —— 没给它写骨架，就没得注入；
      · `PATTERN`（模式表）= **声明** —— 判据（`verify_cognition` 的 A3/A4b）
        盯着两者**一一对应**（有 `cot/both` 就必有骨架，有骨架就必是 `cot/both`）。
      为什么不在这里再抄一遍 `pattern()` 判断：那一道在运行时**永远不会触发**
      （判据已经保证两者一致），反例法当场揭穿它是死分支
      （删掉它一条判据都不红）—— 本项目对死代码零容忍。

    ⚠ 返回空串的三种情形**都是正常的**，调用方一律当"这段不出现"处理：
      · 模式表里这个职位没有 `cot`（`NONE` / 纯 `reflect`）→ 骨架表里也就没有它；
      · `COGNITION` 或对应的分闸关着；
      · 还没给它写骨架。
    
        English:
    ⚠ **Two gates, each handling one thing**:
    · `THINK_STEPS` (skeleton table) = **content + runtime gate** -- if no skeleton is written for
    it, there is nothing to inject;
        · `PATTERN` (pattern table) = **declaration** -- the criteria (`verify_cognition`'s A3/A4b)
          watch that the two correspond **one-to-one** (if there is `cot/both`, there must be a skeleton; if there is a skeleton, it must be `cot/both`).
          Why not copy the `pattern()` check here as well: that one will **never trigger** at runtime
          (the criteria already guarantee the two are consistent), the counterexample method exposes it on the spot as a dead branch
          (delete it and not a single criterion turns red) — this project has zero tolerance for dead code.
        ⚠ The three cases where an empty string is returned are **all normal**; callers uniformly treat it as "this segment does not appear":
          · This position has no `cot` in the pattern table (`NONE` / pure `reflect`) → it is also absent from the skeleton table;
          · `COGNITION` or the corresponding sub-switch is off;
          · No skeleton has been written for it yet.
    """
    k = str(key or '').strip()
    if not _enabled(k):
        return ''
    steps = THINK_STEPS.get(k)
    if not steps:
        return ''
    field = think_field(k)
    if field:
        lines = [f'【开口之前，先在心里按顺序过一遍 —— 把答案压进 `{field}`】']
    else:
        # 散文产出的职位（小说作家）：**不要求落成字段**（理由见 `THINK_FIELD`
        # 上面那段）—— 骨架只进提示词，让它把这几问想过一遍再动笔。
        # [EN] Positions with prose output (novelist): **not required to persist as a field** (reason see
        # [EN] `THINK_FIELD`
        # [EN] the paragraph above) -- the skeleton only goes into the prompt, letting it think through these
        # [EN] questions before starting to write.
        lines = ['【动笔之前，先在心里按顺序过一遍（不必写出来）】']
    # ⚠ 编号要**重排**：精简档跳过几问之后，如果还印原编号就会出现
    #   "从头开始却写着 3."，模型会以为自己漏了前两问（实测会让它去补）。
    # [EN] Renumber: in the compact band, keeping the original numbers prints "3." as the first
    # [EN] item and the model thinks it skipped two (measured: it tries to fill them in).
    _n = 0
    for ask, ref in steps:
        if compact and not any(k in str(ask) for k in _COMPACT_KEEP):
            continue
        _n += 1
        tip = _tip(ref)
        line = f'{_n}. {ask}'
        if tip:
            line += f'\n   〔手艺「{ref}」〕{tip}'
        lines.append(line)
    if field:
        lines.append(f'⚠ `{field}` 是你自己看的盘算（一到三句、共 ≤ 60 字），'
                     f'**不要把它写进台词或正文** —— 那是给别人听的。')
    return '\n'.join(lines)


def think_schema(key: str, hint: str) -> str:
    """思考字段在 JSON 格式说明里的那一小段（`"推演": "（…）", `）。

    **关掉时返回空串** —— 为什么非要做成"跟开关走"：
    如果骨架没了、而 JSON 格式里还写着那个字段，模型照样会把它输出出来，
    那就不是"关掉 = 逐字退回"了（差在提示词上，判据一抓一个准）。
    所以字段的启停必须与骨架**同一处判据**（`_enabled`）。

    `hint` 是给模型的填写说明（各职位不同，比如演员是"开口之前那几句盘算"）。
    
        English:
    That small paragraph about the thinking field in the JSON format description (`"推演": "(…)", `).
        **Return an empty string when disabled** — why it must "follow the switch":
        If the skeleton is gone but that field is still written in the JSON format, the model will still output it,
        then it is no longer "disabled = verbatim fallback" (the difference is in the prompt, and the criteria catch it every time).
        So the enabling/disabling of the field must use the **same criterion** as the skeleton (`_enabled`).
        `hint` is the filling instruction given to the model (varies by position, e.g. for an actor it is "those few calculations before speaking").
    """
    k = str(key or '').strip()
    f = think_field(k)
    if not f or not _enabled(k):
        return ''
    return f'"{f}": "（{hint}）", '


#: 各职位填思考字段时的说明（给 `think_schema` 的 `hint` 用；一处一份，
#: 免得九处调用各写一句话、迟早漂成九种说法）。
# [EN] : the explanation for each position when filling the thinking field (used for `think_schema`'s
# [EN] `hint`; one copy in one place,
# [EN] : to avoid nine call sites each writing a sentence and sooner or later drifting into nine
# [EN] phrasings).
THINK_HINT: dict[str, str] = {
    'actor': '开口之前那几句盘算，一到三句、≤60 字',
    # ★★ 2026-10-10 补字数上限。原来只有"一到三句"，而这一条是**唯一**
    #   没人给上限的（演员那条写着 ≤60 字）—— 后果在真机日志里看得一清二楚：
    # [EN] ★★ 2026-10-10 added word-count cap. Originally there was only "one to three sentences", and this
    # [EN] one was the **only**
    # [EN] one with no cap given (the actor's line says <=60 characters) -- the consequence is plainly
    # [EN] visible in real-machine logs:
    #
    #     `day_script` 的输出上限是 `CREW_SCRIPT_TOKENS=4000`，而 JSON 的
    #     **第一个字段就是这个 `构思`**。模型先在它上面自由发挥，把额度吃光，
    #     后面的「拍」写不完 —— 实测两次 `out=3998`（正好卡在 4000）、
    #     一次正文为空，返回被截在半句话上（下面这行是**截断现场**的重现，
    #     人名一律用中性词 —— `verify_generic_project` 盯着"判据/源码里
    #     不许出现某一部具体作品的专有名词"，注释里也不行）：
    #       `{"构思": "那天的事被翻了出来，账上那笔债落到「甲」头上。分六拍：…`
    #     于是剧本反复重写（那天的日志里 `day_script` 问了 6 次，`rounds=4`），
    #     最后 `verdict` 还是「不通过」。**给它一句话的字数上限**，
    #     额度就留给真正要交付的那几拍。
    # [EN] `day_script`'s output cap is `CREW_SCRIPT_TOKENS=4000`, and the first
    # [EN] **field of the JSON is this `ideation`**. The model first free-associates on it, eats up the
    # [EN] budget,
    # [EN] and the following "beat" cannot be finished -- measured twice at `out=3998` (right at 4000),
    # [EN] once the main text was empty, the return truncated at half a sentence (the line below is a
    # [EN] reproduction of the **truncation scene**,
    # [EN] names uniformly use neutral words -- `verify_generic_project` watches for "criteria/source code
    # [EN] must not contain proper nouns of a specific work", not even in comments):
    # [EN] `{"ideation": "That day's matter was dug out, and that debt on the books fell on "Jia"'s head.
    # [EN] Split into six beats: ...`
    # [EN] So the script was rewritten repeatedly (in that day's log `day_script` was asked 6 times,
    # [EN] `rounds=4`),
    # [EN] and in the end `verdict` was still "fail". **Give it a one-sentence word-count cap**,
    # [EN] and the budget is left for the beats that actually need to be delivered.
    'screenwriter': '这一天的转变与分拍的思路，一到三句、≤60 字',
    'director': '先看清局面再下手，一到三句',
    'continuity': '先逐条核过之后的结论，一到三句',
    'researcher': '先挑出名物、再判站不站得住，一到三句',
    'polisher': '你读下来最要紧的判断，一到三句',
}


def think_schema_of(key: str) -> str:
    """`think_schema(key, THINK_HINT[key])` 的简写（各调用点用这个）。
        English:
    Shorthand for `think_schema(key, THINK_HINT[key])` (each call site uses this).
    """
    return think_schema(key, THINK_HINT.get(str(key or '').strip(), '先想清楚，一到三句'))


def take_think(data, key: str) -> str:
    """从一份产出里**取**思考字段的内容（拿不到返回空串）。

    宽容读法（各职位可能写成 `推演`/`思考`/`盘算`）：先认字段名，再认那几个别名。
    这一步只是"取"，**不判对错** —— 模型没给盘算不算故障（骨架在提示词里，
    它至少先想过一遍），所以不记笔记、不降级。
    
        English:
    **Extract** the content of the thinking field from one output (return an empty string if
    unavailable).
        Lenient reading (each position may write `推演`/`思考`/`盘算`): first recognize the field name, then recognize those aliases.
        This step only "extracts", **it does not judge right or wrong** — the model not providing a calculation is not a fault (the skeleton is in the prompt,
        it at least thought it through once), so no note is recorded and no degradation occurs.
    """
    if not isinstance(data, dict):
        return ''
    names = [think_field(key)] + ['推演', '构思', '盘算', '思量']
    for n in names:
        if not n:
            continue
        v = data.get(n)
        if isinstance(v, (list, tuple)):
            v = ' '.join(str(x) for x in v)
        s = ' '.join(str(v or '').split())
        if s:
            return s[:200]
    return ''


def note_think(key: str, data, *, who: str = '') -> str:
    """取出来 + 记一条日志（**唯一入口**，`crew/studio.Studio.call` 用它）。

    为什么记日志：`推演` 不上面向用户的窗口（用户的中间栏白名单里没有它），
    但"这个人/这位职位当时是怎么想的"恰恰是**事后查"为什么演出成这样"**
    最要紧的一条线索 —— 不落到日志里，它就等于没发生。
    
        English:
    Extract it + log one entry (**the only entry point**, used by `crew/studio.Studio.call`).
        Why log it: `推演` does not go to the user-facing window (it is not in the user's middle-column whitelist),
        but "what this person/this position was thinking at the time" is precisely the most important clue for **retrospectively investigating "why the performance turned out this way"**
        — if it does not land in the logs, it is as if it never happened.
    """
    tr = take_think(data, key)
    if not tr:
        return ''
    _LOG.info('「%s」先想过：%s', who or key, tr[:100])
    return tr


# ══════════════════════════════════════════════════════════════════
#  反思链：**台词自省**（执行 → 反思 → 优化）
# [EN] Chain of reflection: **line self-reflection** (execute -> reflect -> optimize)
# ══════════════════════════════════════════════════════════════════
#: "这一句不太像人在场上说的话"的**规则判据**（零成本先粗筛）。
# [EN] : the **rule-based criterion** for "this line does not sound like something a person would say
# [EN] on stage" (zero-cost rough screening first).
#:
#: 为什么不直接让模型判：每拍每个人都要过一遍，问一次模型就是每拍多一次调用
#: （演员是全项目最贵的职位）。先用规则把**明显不像话**的挑出来
#: （和 `agent/core._IMP_RULES`、`style/deai` 同一条思路：规则先粗筛、
#: 模型只处理"说不准"的那一小撮）。
# [EN] : why not let the model judge directly: every person in every beat has to go through it, and
# [EN] asking the model once means one extra call per beat
# [EN] : (the actor is the most expensive position in the whole project). First use rules to pick out
# [EN] the **obviously unnatural** ones
# [EN] : (the same idea as `agent/core._IMP_RULES`, `style/deai`: rough screening by rules first,
# [EN] : The model only handles the small set that is "hard to call").
#:
#: ⚠ 判据要**窄**（宁可漏，不可误报）：误报会让好好的台词被要求重说，
#:   表现成"人物说话总是被打断重来"。所以只认下面这两类**确定的**毛病。
_LONG_LINE = 34        # 一句口语超过这么多字，基本就是"写作文"
# [EN] : ⚠ The criterion must be **narrow** (better to miss than to false-positive): a false positive
# [EN] makes perfectly good dialogue get flagged for a retake,
# [EN] : which shows up as "characters are always getting interrupted and starting over". So only
# [EN] recognize the following two kinds of **definite** defects.
# [EN] When a single spoken line exceeds this many characters, it is basically "writing an essay"
_UNNATURAL_WORDS: tuple[str, ...] = (
    # 书面连接词（口语里不会有人这么衔接）
    # [EN] Written connectives (no one would link things this way in speech)
    '因此', '然而', '总之', '综上', '由此可见', '换言之', '与此同时',
    '不仅', '而且', '因而', '故而', '进而', '再者',
    # 情绪直说（把"我怎么想"直接报出来 —— 台词里最典型的机器腔）
    # [EN] Stating emotions outright (reporting "what I think" directly -- the most typical robotic tone in
    # [EN] dialogue)
    '我非常', '感到十分', '十分悲伤', '十分愤怒', '非常难过', '情绪复杂',
    '五味杂陈', '百感交集',
    # 解释腔（对读者解释，而不是对场上的人说话）
    # [EN] Explanatory tone (explaining to the reader, rather than speaking to the people on stage)
    '这是因为', '之所以', '也就是说', '换句话说', '众所周知', '不难看出',
)


def unnatural_reason(line: str) -> str:
    """这一句台词"不太像人在场上说的"吗？返回**原因**（不是就返回空串）。

    返回原因的用意：它会被拼进**自省提示词**，让演员知道"哪一点不像"，
    而不是笼统地听到一句"再说一遍"（那样他只会换个说法说同一句）。
    
        English:
    Does this line "not quite sound like something a person would say on stage"? Return the
    **reason** (return an empty string if not).
        The purpose of returning the reason: it gets spliced into the **introspection prompt**, letting the actor know "which point does not seem right",
        instead of vaguely hearing "say it again" (in which case he would only rephrase the same line differently).
    """
    s = str(line or '').strip()
    if not s:
        return ''
    for w in _UNNATURAL_WORDS:
        if w in s:
            return f'这一句里有「{w}」这种书面字眼，人当场不会这么说话'
    if len(s) > _LONG_LINE:
        return f'这一句 {len(s)} 个字太长了 —— 场上的人一次说不完这么多'
    return ''


#: 演员自省的提示词（`sim/loop._self_review` 用 `_REVIEW_CTX.format(...)` 填）。
# [EN] : The actor self-reflection prompt (used by `sim/loop._self_review` with
# [EN] `_REVIEW_CTX.format(...)`).
ACTOR_REVIEW_CTX = """你刚才要说的那一句是：「{line}」

**先别急着说。** 你站在场上，把这一句在嘴里过一遍，问自己一件事：
> 这真是「{name}」此刻会从嘴里说出来的话吗？

判据（来自你这一行的三本手艺：说话方式就是身份 / 停顿与不答也是台词 /
话长短由处境定）：
- **换个人说成不成立**？换给在场任何一个人说都毫不违和 → 这句没写到人身上。
- **是不是在解释**？把心里的事直接报出来（"我很愤怒""我感到十分悲伤"）、
  或者用书面字眼衔接（"因此""然而""总之"）→ 那不是人在场上说话。
- **是不是太长**？落了下风的人说半句就够；**能不答就用一个动作带过去**。

**要么改，要么坚持原话**（坚持也是对的：真有非说不可的理由，就原样说出来）。
按同一个 JSON 格式再答一次。"""
