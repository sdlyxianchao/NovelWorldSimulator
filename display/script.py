# -*- coding: utf-8 -*-
"""剧本式输出：数据模型（设计稿 §10.6 的扩展，见 `剧本输出格式.md`）。

为什么要有这一层
----------------
运行界面以前把叙事当**一维字符串流**：`_daily_narrative.append(f"{名字}{动作}")`。
这带来三个表达不了的麻烦：

1. **人物不是一直说话**——他可能在擦柜台、在数米缸、在听着什么。字符串流里
   动作和对白是同一层，读者分不清"他说"和"他做"。
2. **同一时刻不同人在做不同事**——一个 tick 里两个 agent 各做一个动作，
   拼成两行就是"先后"，而其实是"同时"。
3. **出处不可见**——这段戏到底在推进哪个节点、回收哪条伏笔、服务谁的目标？
   只在 prompt 里，读者（和作者）看不到。

所以把叙事从"字符串"升级成"结构化词条序列"，每个词条带**类型 + 主体 + 出处**，
渲染器再按不同用途（屏幕 / 落盘 / 回灌 LLM）输出不同形态。

词条类型（按设计稿 §10.6 的「动作/对话/旁白」扩充分解）
--------------------------------------------------------
    时间说明  TIME        幕内时间推进（"过了半个时辰"）
    场景说明  SCENE       地点 + 环境（天气/光线/声响/气味）
    人物出场  ENTER       谁进来了，从哪来
    人物退场  EXIT        谁走了，往哪去
    旁白      NARRATION   第三方叙述、交代背景
    对白      DIALOGUE    谁对谁说，可带语气/动作提示
    动作      ACTION      某人在做什么（**不说话的段落靠它撑起来**）
    心声      ASIDE       内心活动，不外泄
    同时      PARALLEL    同场同时，多条并行轨
    切至      CUT         异地同时（平行剪辑）
    切回      CUT_BACK    回到主场景
    事件      EVENT       外部事件（导演注入）
    停顿      BEAT        静场 / 呼吸点
    标注      NOTE        机制信息（张力、伏笔激活、节点推进）
    插图      IMAGE       图片输出（场景图 / 人物像 / 地图帧）
    前情提要  RECAP       **开演前那一段回顾**（每轮/每天开头，不是故事本身）

设计取舍
--------
* **只增不改**：设计稿 §10.6 已有的「每天的生活」骨架（`# 第N天` 头、
  `## 时段 · 小节`）保持不变，只是把小节**内部**从自由文本升级为脚本块。
  `OUTPUT_FORMAT=prose` 可退回旧行为，新旧运行文件夹都能读。
* **策略生成、非 LLM 生成**：幕的切分、同时性归并、出场退场 diff 都是规则，
  零 token、可复现、可测试。LLM 只负责它擅长的（台词、细节），
  不负责"谁和谁同时"这种结构判断。
* **出处必须可见**：每个词条可带 `anchors`（节点 / 伏笔 / 目标），
  幕首汇总成「本幕依据」。这是"每个人按自己的人物设定和故事发展来"的**可审计形式**。

English:
Why this layer is needed
----------------
The run UI used to treat narrative as a **one-dimensional string stream**:
`_daily_narrative.append(f"{name}{action}")`.
This caused three problems that could not be expressed:
1. **Characters are not always speaking** —— they may be wiping the counter, counting the rice jar, listening to something. In a string stream,
   actions and dialogue are on the same layer, and the reader cannot tell "he said" from "he did".
2. **Different people do different things at the same moment** —— in one tick two agents each do one action,
   concatenating them into two lines reads as "one after another", when it is actually "simultaneous".
3. **Provenance is invisible** —— which node is this passage advancing, which foreshadowing is it paying off, whose goal does it serve?
   It's only in the prompt; the reader (and the author) cannot see it.
So upgrade the narrative from "strings" to a "structured entry sequence", where each entry
carries **type + subject + provenance**,
and the renderer then outputs different forms according to different purposes (screen / disk /
feedback to LLM).
Entry types (decomposed by extending the "action/dialogue/narration" of design doc §10.6)
--------------------------------------------------------
    Time description  TIME        In-act time advance ("half a shichen has passed")
    Scene description SCENE       Location + environment (weather/light/sound/smell)
    Character entrance ENTER       Who came in, from where
    Character exit     EXIT        Who left, to where
    Narration          NARRATION   Third-party narration, setting the background
    Dialogue           DIALOGUE    Who says what to whom, may carry tone/action hints
    Action             ACTION      What someone is doing (**silent passages rely on this to hold up**)
    Inner voice        ASIDE       Inner activity, not exposed
    Simultaneous       PARALLEL    Same scene, same time, multiple parallel tracks
    Cut to             CUT         Different place, same time (parallel editing)
    Cut back           CUT_BACK    Return to the main scene
    Event              EVENT       External event (injected by director)
    Pause              BEAT        Silence / breath point
    Annotation         NOTE        Mechanism info (tension, foreshadow activation, node advancement)
    Illustration       IMAGE       Image output (scene image / character portrait / map frame)
    Recap              RECAP       **That recap segment before the show starts** (at the beginning of each round/day, not the story itself)
Design trade-offs
--------
* **Only add, don't modify**: the "everyday life" skeleton already in design doc §10.6 (`# 第N天` header,
  `## 时段 · 小节`) stays unchanged; only the **inside** of the section is upgraded from free text to script blocks.
  `OUTPUT_FORMAT=prose` falls back to the old behavior; both new and old run folders can be read.
* **Strategy generation, not LLM generation**: act splitting, simultaneity merging, and entrance/exit diffs are all rules,
  zero tokens, reproducible, testable. The LLM only handles what it is good at (dialogue, details),
  not "who is simultaneous with whom"-style structural judgments.
* **Provenance must be visible**: each entry can carry `anchors` (node / foreshadowing / goal),
  summarized at the head of the act as "basis for this act". This is the **auditable form** of "each person acts according to their own character setting and story development".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ══════════════════════════════════════════════════════════════════════
#  行内元标记（模型写进正文的"记账格式"）—— **唯一实现**
# [EN] Inline metadata markers (the "bookkeeping format" the model writes into the prose) -- the
# [EN] **single implementation**
# ══════════════════════════════════════════════════════════════════════
# ★★★ 2026-10-17：模型会把这些**我们内部的标记**原样写进台词 / 细节 / 内心：
#     `〔action·甲〕`（2 处）、`〔aside·乙〕`、`〔心声·丙〕`、
#     `{aside·丁}`（半角），还有 `（并入第 3 条，不单立）` 这种**自言自语**。
#   实测一次真实运行：3453 字的一天里有 **10 处**。它们会一路进到落盘的台本、
#   界面、导出 —— 读者看到的是文件格式，不是小说。
#
#   ⚠ 为什么放**这里**（`Entry.__post_init__` 调用）而不是只放在导出时剃：
#     导出只是**最后一个出口**。台本落盘（`每天的生活/`）、界面中栏、原文稿、
#     参考稿、小说版本 —— 有五个出口，每个出口各剃一遍就是"同一件事五处实现"。
#     `Entry` 是所有这些出口的**唯一上游**（`display.script.Entry` 是词条的唯一构造
#     入口），在这里洗一次，五个出口全干净。
#   ⚠ 不许动**转场标记**（`〔切至 …〕` / `〔切回 …〕` / `〔同时〕`）—— 它们是叙事结构，
#     不是记账格式（`export/novel_version._tidy_for_novel` 那条成对判据守着这一点）。
# [EN] ★★★ 2026-10-17: the model writes these **internal** markers straight into dialogue /
# [EN] detail / inner voice: `〔action·X〕`, `〔aside·X〕`, `〔心声·X〕`, `{aside·X}` (half-width), plus
# [EN] self-talk like `（并入第 3 条，不单立）`. Measured on one real run: **10 occurrences** in a
# [EN] 3453-character day. They travel all the way into the persisted script, the UI and the export --
# [EN] the reader sees file format, not a novel.
# [EN] ⚠ Why here (called from `Entry.__post_init__`) rather than only stripping at export: export is
# [EN] just the **last exit**. The persisted script, the middle-column UI, the raw copy, the reference
# [EN] copy and the novel version are five exits; stripping in each is "one thing implemented five
# [EN] times". `Entry` is the **single upstream** of all of them, so one wash here cleans all five.
# [EN] ⚠ Must not touch **transition markers** (`〔切至 …〕` / `〔切回 …〕` / `〔同时〕`) -- those are
# [EN] narrative structure, not bookkeeping (a paired criterion in
# [EN] `export/novel_version._tidy_for_novel` guards that).
META_MARK_RE = re.compile(
    r'[〔{]\s*(?:aside|dialogue|recall|action|narration|note|inner|心声|动作|旁白|标注'
    # ★★★ 2026-10-18：**审读自己给的标签**。实测某一轮续写，剧本审读的
    #   `改成` 写成「〔改动作〕柳氏拇指沿杯口抹了半圈…」—— 那是**它对自己说的话**，
    #   却跟着改写一起进了正文。这类标签同样是"我们的内部格式"，
    #   在唯一入口洗掉，五个出口全干净。
    # [EN] ★★★ 2026-10-18: **labels the reviewer itself adds**. Measured in the Mowen Tower run,
    # [EN] the reviewer's `改成` came back as "[改动作] Liu Shi ran a thumb along the cup rim..." --
    # [EN] a note to itself that rode the rewrite straight into the body. Same "internal format of
    # [EN] ours", washed at the single entry point so all five exits stay clean.
    r'|改动作|改台词|改旁白|改写|改成|改后|心里|内心|心理|台词|对白|神态'
    r')(?:\s*·[^〕}\n]{0,80})?[〕}]', re.I)

#: 模型**对自己下的指令**（不是内容）：固定带这几个词，且只在括号里出现。
# [EN] Instructions the model gives **itself** (not content): always carry these words, and only
# [EN] ever appear inside brackets.
_SELF_TALK_RE = re.compile(r'[（(]\s*(?:并入|不单立|同上|略)[^）)]{0,30}[）)]')

#: **行首的圆括号标签**：`（心里）旧账上也有这一笔` / `(心声) …`。
#: 与 `_SELF_TALK_RE` 的区别：那个是"模型对自己下的指令"，这个是"模型给这段贴的类型"；
#: 两者都只该出现在**我们的内部格式**里，不该进正文。
#: ⚠ 只剥**行首**那一处、且词在白名单里：`他把碗放下（没再拿起）` 是正常内容，不能碰。
# [EN] **A parenthesized label at the start of a line**: `(心里) the old ledger has this entry too`.
# [EN] Unlike `_SELF_TALK_RE` (instructions to itself), this is "the type it stuck on the passage";
# [EN] both belong to **our internal format** and must not reach the body.
# [EN] ⚠ Only the **leading** one, only whitelisted words: `他把碗放下（没再拿起）` is real content.
_LEAD_LABEL_RE = re.compile(
    r'^\s*[（(]\s*(?:心里|心声|内心|心理|动作|旁白|叙述|改动作|改台词|改写|改成)'
    r'(?:\s*[·:：][^）)]{0,20})?\s*[）)]\s*')


def strip_meta_marks(text: str) -> str:
    """剥掉正文里的**行内元标记**，并收拾残留的空括号 / 双空格。

    ★ 只剥"我们自己格式的标记"，不动任何正常文字：
      · `〔action·甲〕甲脊背挺直` → `甲脊背挺直`
      · `（并入第 3 条，不单立）` → 空（这是模型的自我指令，不是内容）
      · `〔切至 · 正堂南门内〕` → **保留**（叙事结构）
    [EN] ★ Only strips "markers in our own format", never normal text:
    [EN]   `〔action·X〕he straightened` -> `he straightened`; `（并入第 3 条…）` -> empty (the model's
    [EN]   own instruction to itself, not content); `〔切至 · …〕` -> **kept** (narrative structure).
    """
    if not text:
        return text
    # ⚠ 早退条件要看**两个**正则：只判 `META_MARK_RE` 的话，
    #   `（并入第 3 条，不单立）` 这种（没有 〔〕 标记、只有自我指令）会被直接放过去
    #   —— 实测第一次就漏了这一条。
    # [EN] ⚠ The early exit must consider **both** regexes: checking only `META_MARK_RE` lets
    # [EN] `（并入第 3 条，不单立）` (no 〔〕 marker, just self-talk) straight through -- missed it on
    # [EN] the very first measurement.
    if (not META_MARK_RE.search(text) and not _SELF_TALK_RE.search(text)
            and not _LEAD_LABEL_RE.search(text)):
        return text
    out = _LEAD_LABEL_RE.sub('', text)
    out = META_MARK_RE.sub('', out)
    # 模型还会顺手写"（并入第 N 条，不单立）"这类**对自己下的指令** —— 它们固定带
    # "并入 / 不单立 / 略 / 同上"这些词，且只在括号里出现。
    # [EN] The model also jots instructions **to itself** like "（并入第 N 条，不单立）" -- these
    # [EN] always carry words like 并入 / 不单立 / 同上 and only ever appear inside brackets.
    out = _SELF_TALK_RE.sub('', out)
    out = re.sub(r'[（(]\s*[）)]', '', out)          # 空括号
    out = re.sub(r'[ \t]{2,}', ' ', out)
    return out.strip()

# ══════════════════════════════════════════════════════════════
#  词条类型
# [EN] Entry types
# ══════════════════════════════════════════════════════════════
TIME = 'time'
SCENE = 'scene'
ENTER = 'enter'
EXIT = 'exit'
NARRATION = 'narration'
DIALOGUE = 'dialogue'
ACTION = 'action'
ASIDE = 'aside'
PARALLEL = 'parallel'
CUT = 'cut'
CUT_BACK = 'cut_back'
EVENT = 'event'
BEAT = 'beat'
NOTE = 'note'
IMAGE = 'image'
# ── 2026-10-06 新增的两个（用户要求"补充缺少的类型"）──
#   ⚠ **加类型必须有真实来源**，否则就是死代码（这个项目对"假按钮"零容忍）：
#     · AMBIENT ← `SceneBuilder.observe_quiet()`（全场无事时写环境白描，
#       以前它产的是 BEAT「片刻无话」，那句话其实什么都没说）
#     · RECALL  ← `SceneBuilder.observe_reflection()`（人物的回忆/省思，
#       以前和"当下心声"共用 ASIDE，读者分不出"他现在想"和"他想起"）
AMBIENT = 'ambient'      # 环境白描 / 群像背景（雨声、市声、光影、街上的人）
RECALL = 'recall'        # 回想 / 省思（不属当下场景，是人物心里翻出来的旧事）
# ── 2026-10-07 新增的 ──
#   RECAP ← `sim/loop.py::_push_recap()`（每轮开头与每个日界推的那一段回顾）。
#   为什么不复用 NOTE：NOTE 是「机制标注」（进度、张力、伏笔），屏幕上跟
#   「（进度）节点完成」长一个样；而用户要的是「各功能部分用不同颜色/背景/
#   边框方块明显区分」，前情提要是**给人读的故事背景**，不是体检报告。
RECAP = 'recap'          # 前情提要（开演前的回顾，不是当天发生的事）
#: **今日剧情简介**（2026-10-07）：用户要的顺序是
#: 「前情提要 → **今日剧情简介** → 正式剧情」。
#: ⚠ 和 `RECAP` 分开而不是合成一个"开演前"：两者回答的问题不同 ——
#:   前情提要讲"前面发生了什么"，今日简介讲"今天要演什么"。
#:   合成之后只能二选一，而用户要的是**两条都在**（顺序也定死了）。
BRIEF = 'brief'          # 今日剧情简介（今天这一章要讲什么）
#: **推演写成的小说**（2026-10-21 用户点名：「点击停止的时候、或者某次推演结束的时候，
#: 可以自动把根据推演生成的小说输出到推演窗口里（默认可以是收起来的，用户点了才展开，
#: 或者这个是收还是展开用户可以配置）」）。
#:
#: ★ 为什么单独一个类型、不并进 `RECAP` 或 `NOTE`：
#:   · `RECAP` 是**开演前**的前情提要，`NOTE` 是机制标注（进度/张力/伏笔）；
#:   · 这一条是**演完之后**由小说家整理出来的**成篇正文**，长度差两个数量级
#:     （几百到几千字），而且它要**可折叠**（默认收起，点开才展开）；
#:   · 混进 NOTE 会被界面的"一行一条"排版压成一行，读者根本没法读。
#: ⚠ 界面按这个类型给**独立样式 + 折叠**（见 `gui` 里对 `NOVEL` 的分支）；
#:   没有折叠能力的旧界面至少也要整段显示，不许截断。
# [EN] **The novel written from the simulation** (named by the user 2026-10-21: when I hit stop, or
# [EN] when a run finishes, automatically output the generated novel into the simulation window --
# [EN] collapsed by default, expandable on click, or the user can configure which).
# [EN] ★ Why a separate type rather than folding into RECAP/NOTE: RECAP is the pre-show recap and NOTE
# [EN] is a mechanism marker; this is the **finished prose** organized after the show -- two orders of
# [EN] magnitude longer, and it must be **collapsible**. Merged into NOTE it would be flattened into
# [EN] one line by the "one entry per row" layout and become unreadable.
NOVEL = 'novel'          # 推演写成的小说（成篇正文，可折叠）
#: **今日任务分配**（2026-10-07 第八轮）：今天谁该做什么 —— 导演写剧本时
#: 分派到每个人头上的那几件事（`DayScript.roles`）。
# [EN] ── Two added 2026-10-06 (user asked to "fill in the missing types") ──
# [EN] ⚠ **Adding a type must have a real source**, otherwise it is dead code (this project has zero
# [EN] tolerance for "fake buttons"):
# [EN] · AMBIENT ← `SceneBuilder.observe_quiet()` (writes environmental description when nothing
# [EN] happens on stage,
# [EN] previously it produced a BEAT "a moment of silence", but that line actually said nothing)
# [EN] · RECALL  ← `SceneBuilder.observe_reflection()` (a character's recollection/reflection,
# [EN] previously it shared ASIDE with "current inner voice", so readers could not tell "what he thinks
# [EN] now" from "what he remembers")
# [EN] Environmental description / group background (rain, city sounds, light and shadow, people on the
# [EN] street)
# [EN] Recollection / reflection (not part of the current scene, old matters dredged up in a
# [EN] character's mind)
# [EN] ── Added 2026-10-07 ──
# [EN] RECAP ← `sim/loop.py::_push_recap()` (the recap pushed at the start of each round and each day
# [EN] boundary).
# [EN] Why not reuse NOTE: NOTE is "mechanism annotation" (progress, tension, foreshadowing), on screen
# [EN] it looks exactly
# [EN] like "(progress) node complete"; but the user wants "each functional part clearly distinguished
# [EN] by different colors/backgrounds/
# [EN] bordered boxes", and a recap is **story background for people to read**, not a health report.
# [EN] Recap (the review before the show starts, not what happened today)
# [EN] : **Today's story brief** (2026-10-07): the order the user wants is
# [EN] : "Recap → **Today's story brief** → the actual story".
# [EN] : ⚠ Kept separate from `RECAP` instead of merged into one "pre-show": the two answer different
# [EN] questions ——
# [EN] : the recap tells "what happened before", the today brief tells "what is to be performed today".
# [EN] : merging them would force an either/or, but the user wants **both** (and the order is fixed
# [EN] too).
# [EN] Today's story brief (what this chapter is going to tell today)
# [EN] : **Today's task assignment** (2026-10-07 eighth round): who should do what today —— the few
# [EN] things
# [EN] : the director assigns to each person when writing the script (`DayScript.roles`).
#:
#: 用户白名单里那句「**导演工作分配**」就是它。它此前只有一条别扭的出路：
#: 被写进各人的 `ps.day_plan`（人物自己看得见），**读者一个字都看不到** ——
#: 于是屏幕上"今天要演什么"有了（`BRIEF`），"谁负责哪一件"却缺了一块。
# [EN] : The user's whitelist phrase "**director's work assignment**" is this. Before this it had only
# [EN] one awkward outlet:
# [EN] : written into each person's `ps.day_plan` (visible to the characters themselves), **the reader
# [EN] could not see a single word** ——
# [EN] : so on screen "what is to be performed today" existed (`BRIEF`), but "who is responsible for
# [EN] which one" was a missing piece.
#:
#: ⚠ 与 `NOTE` 里那条 `（导演派活）…` **不是同一件事**，别合并：
#:   · 那条是**每 N 拍的临时派活**（导演盯着进度现派的，随时会变）；
#:   · 这一条是**一天一次的任务分配**（开演前定下来的框架）。
#:   一个是过程里的调整，一个是这一天的大纲 —— 时间尺度不同、来源也不同
#:   （一个是 `director.engine.dispatch`，一个是 `crew/agents.Screenwriter`）。
TASK = 'task'            # 今日任务分配（谁负责哪几件事）
# ── 2026-10-07 新增的两个：**剧组的过程**怎么显示 ──
# [EN] : ⚠ It is **not the same thing** as the `(director assigns work)…` entry in `NOTE`, do not
# [EN] merge:
# [EN] : · that one is **ad-hoc assignment every N beats** (the director assigning on the fly as
# [EN] progress is watched, can change at any time);
# [EN] :   · this one is **a once-a-day task assignment** (the framework set before the show starts).
# [EN] : one is an adjustment during the process, the other is the outline for the day —— different
# [EN] time scales, different sources
# [EN] :   (one is `director.engine.dispatch`, the other is `crew/agents.Screenwriter`).
# [EN] Today's task assignment (who is responsible for which things)
# [EN] ── Two added 2026-10-07: how to display **the crew's process** ──
#
# 用户 2026-10-07：「窗口输出的内容你把作者写小说 剧作家创作剧本 剧组排练
# 然后重新修改 再排练 再修改等过程用**小的消息**（只显示阶段名和用时，
# 不真实输出内部细节，但细节写入日志）……别的不要加到运行界面中间窗口」。
# [EN] User 2026-10-07: "For the window output, take the process of the author writing the novel, the
# [EN] playwright creating the script, the crew rehearsing
# [EN] then revising again, rehearsing again, revising again, etc. and use **small messages** (showing
# [EN] only the stage name and elapsed time,
# [EN] not actually outputting internal details, but writing details to the log)…… do not add anything
# [EN] else to the middle window of the running interface".
#
# 在那之前，剧组每出一份活都会把**正文推到中栏**（`（剧组 · 美术）水墨淡彩…`），
# 于是读者读着读着就被一段"美术指导"打断 —— 而那是拍摄现场的花絮，不是小说。
# 现在分成两种**只报状态、不报内容**的消息：
# [EN] Before that, every piece of work the crew produced would **push the body text into the middle
# [EN] column** (`(crew · art) ink wash…`),
# [EN] so the reader, while reading, would be interrupted by a chunk of "art direction" —— and that is
# [EN] footage from the shooting set, not the novel.
# [EN] Now it is split into two kinds of messages that **report status only, not content**:
#
#   · `STAGE` —— **阶段**：作者写小说 / 剧作家创作剧本 / 排练 / 重新修改 /
#     开演 / 暂停 / 一天讨论 / 总结会。一条小字，只有阶段名与用时。
#   · `CREW`  —— **剧组工作状态**：哪个职位出工了、交没交活。同样只有状态。
# [EN] · `STAGE` —— **stage**: author writing novel / playwright creating script / rehearsal / revision
# [EN] /
# [EN] show start / pause / day discussion / summary meeting. One small line, only the stage name and
# [EN] elapsed time.
# [EN] · `CREW` —— **crew work status**: which position has started work, whether the work was
# [EN] delivered. Also status only.
#
# ⚠ 两者的产出**照旧落盘**（`剧组台账.md` / 各职位的 `.md`）也照旧进日志 ——
#   被拿掉的只是"往读者眼前推内容"这一件事。
STAGE = 'stage'          # 剧组阶段（只报阶段名与用时）
CREW = 'crew'            # 剧组工作状态（哪个职位在做什么）
#: **收工总结**（2026-10-07）：用户白名单里那句
#: 「手动停止以及一天自动停止之后的总结」—— 复盘职位给的「今日总结」
#: （剧情总结 + 存在的问题 + 后续修改意见）。
#: ⚠ 它与 `CREW`（工作状态）是两件事：那个是"谁出工了"，这个是**给人读的结论**。
#:   它是**唯一**会以"内容"形式上屏的剧组产出（用户点名要的）。
SUMMARY = 'summary'      # 收工总结（今日总结 / 手动停止后的总结）
# [EN] ⚠ The output of both is **still written to disk** (`剧组台账.md` / each position's `.md`) and still
# [EN] goes into the log ——
# [EN] what was removed is only the one thing: "pushing content in front of the reader".
# [EN] Crew stage (reports only stage name and elapsed time)
# [EN] Crew work status (which position is doing what)
# [EN] : **Wrap-up summary** (2026-10-07): the user's whitelist phrase
# [EN] : "the summary after manual stop and after the automatic day-end stop" —— the "today's summary"
# [EN] given by the review position
# [EN] : (plot summary + existing problems + follow-up revision suggestions).
# [EN] : ⚠ It and `CREW` (work status) are two different things: that one is "who has started work",
# [EN] this one is **a conclusion for people to read**.
# [EN] : It is the **only** crew output that appears on screen in "content" form (the user explicitly
# [EN] asked for it).
# [EN] Wrap-up summary (today's summary / summary after manual stop)

ALL_KINDS = (TIME, SCENE, ENTER, EXIT, NARRATION, DIALOGUE, ACTION, ASIDE,
             AMBIENT, RECALL, PARALLEL, CUT, CUT_BACK, EVENT, BEAT, NOTE,
             IMAGE, RECAP, BRIEF, TASK, STAGE, CREW, SUMMARY)

# ══════════════════════════════════════════════════════════════
#  ★★ **中栏白名单** —— 运行界面的中间窗口只许出现这些
# [EN] ★★ **Middle column whitelist** —— only these are allowed to appear in the middle window of the
# [EN] running interface
# ══════════════════════════════════════════════════════════════
# 用户 2026-10-07 逐条点名了允许出现的，并明说「**别的不要加到运行界面中间窗口**」：
# [EN] User 2026-10-07 named the allowed ones item by item, and stated explicitly "**do not add
# [EN] anything else to the middle window of the running interface**":
#
#   人物场景介绍 · 前情提要 · 今日故事简介 · 旁白 · 人物动作 · 人物台词对话 ·
#   场景切换 · 外部环境变化 · 关键变量 · 冲突提示 · 导演工作分配 ·
#   手动停止与一天自动停止之后的总结
#   （另加：剧组阶段小消息与工作状态 —— 那是同一句话里要的）
# [EN] Character scene introduction · recap · today's story brief · narration · character actions ·
# [EN] character dialogue ·
# [EN] scene switching · external environment changes · key variables · conflict alerts · director's
# [EN] work assignment ·
# [EN] the summary after manual stop and after the automatic day-end stop
# [EN] (plus: crew stage small messages and work status —— those were asked for in the same sentence)
#
# 对照到词条类型：
# [EN] Mapped to entry types:
#
# | 用户说的 | kind |
# [EN] | What the user said | kind |
# |---|---|
# | 人物场景介绍 / 外部环境变化 | `AMBIENT` · `ENTER` · `EXIT` |
# | 前情提要 / 今日故事简介 | `RECAP` · `BRIEF` |
# | 旁白 | `NARRATION` · `ASIDE` · `RECALL` |
# | 人物动作 / 台词对话 | `ACTION` · `DIALOGUE` |
# | 场景切换 | `SCENE` · `TIME` · `CUT` · `CUT_BACK` · `PARALLEL` |
# | 冲突提示 | `EVENT` |
# | 关键变量 / 导演工作分配 / 故障 | `NOTE` |
# | **今日任务分配** | `TASK`（2026-10-07 第八轮补：`NOTE` 装的是"每 N 拍的临时派活"，
#   一天一次的那份任务分配此前没有 kind，于是读者看不到 —— 见 `TASK` 的说明）|
# | 剧组阶段 / 工作状态 | `STAGE` · `CREW` |
# [EN] | character scene introduction / external environment changes | `AMBIENT` · `ENTER` · `EXIT` |
# [EN] | recap / today's story brief | `RECAP` · `BRIEF` |
# [EN] | narration | `NARRATION` · `ASIDE` · `RECALL` |
# [EN] | character actions / dialogue | `ACTION` · `DIALOGUE` |
# [EN] | scene switching | `SCENE` · `TIME` · `CUT` · `CUT_BACK` · `PARALLEL` |
# [EN] | conflict alerts | `EVENT` |
# [EN] | key variables / director's work assignment / fault | `NOTE` |
# [EN] | **today's task assignment** | `TASK` (added 2026-10-07 eighth round: `NOTE` holds "ad-hoc assignment every N beats",
# [EN] the once-a-day task assignment previously had no kind, so the reader could not see it —— see the
# [EN] description of `TASK`) |
# [EN] | crew stage / work status | `STAGE` · `CREW` |
#
# ⚠ **这份名单是产品行为**，不是"配色表"：不在里面的 kind 一律**不上屏**
#   （仍然进日志、仍然落盘）。加新 kind 时先回答一句"它属于用户列的哪一条"
#   —— 答不出来就别加进 `WINDOW_KINDS`（`BEAT` 就是这么被挡在外面的：
#   "片刻无话"是画面感，不是用户列的任何一条）。
# [EN] ⚠ **This list is product behavior**, not a "color palette": any kind not in it is **never shown
# [EN] on screen**
# [EN] (it still goes to the log, still gets written to disk). When adding a new kind, first answer the
# [EN] question "which item of the user list does it belong to"
# [EN] —— if you can't answer, don't add it to `WINDOW_KINDS` (`BEAT` was kept out this way:
# [EN] "a moment of silence" is a visual feeling, not any item of the user list).
#
# ⚠ `NOTE` 留在名单里是有意的：它承载「**关键变量**」（进度节点完成、张力、
#   导演派活、岔路口）与「**故障信号**」（没出活、决策连续失败、合规拦截）。
#   故障信号必须上屏 —— 静音掉它就等于把"某个东西坏了"的唯一线索也静音了
#   （与 `CREW_SCREEN` 那条"没出活在任何档位都要推"同一条规矩）。
# [EN] ⚠ Keeping `NOTE` in the list is intentional: it carries "**key variables**" (progress node
# [EN] completion, tension,
# [EN] director tasking, forks) and "**fault signals**" (no output produced, consecutive decision
# [EN] failures, compliance interception).
# [EN] Fault signals must be shown on screen —— muting them equals muting the only clue that "something
# [EN] is broken"
# [EN] (same rule as the `CREW_SCREEN` one: "no output must be pushed at any level").
WINDOW_KINDS = frozenset({
    SCENE, TIME, ENTER, EXIT,
    NARRATION, DIALOGUE, ACTION, ASIDE, RECALL,
    AMBIENT, CUT, CUT_BACK, PARALLEL,
    EVENT, NOTE, RECAP, BRIEF, TASK,
    STAGE, CREW, SUMMARY,
})


def on_window(kind: str) -> bool:
    """这一条**该不该出现在运行界面的中间窗口**（唯一判据，界面与判据共用）。

    为什么抽成函数而不是在界面上就地写一个 `in`：判据要能**直接测语义**
    （喂一批 kind 进去，看谁过谁不过），而不是去读界面的源码字符串
    —— 那种"源码哨兵"抓不住"条件被改成 `if True`"。

    两条例外，都是"看起来像词条、其实不是"的东西：

    * `kind` 为空（老回调不传类型）→ **放行**。那是"说不清是什么"的历史路径，
      把它一律挡掉会让整条叙事流静默消失（比多显示一条严重得多）。
    * `divider:` 开头 → **放行**。分隔符（日界 / 幕终 / 故事终 / 模块）
      走的是**另一条通道**（`on_divider`），只是它在实时流里也占一行；
      它是用户要的"场景切换"那一类路标，不属于"剧组过程花絮"。
    
        English:
    Whether this entry **should appear in the middle window of the run UI** (the single criterion,
    shared by the UI and the criterion).
        Why extract it into a function instead of writing an `in` inline in the UI: the criterion must be able to **directly test semantics**
        (feed a batch of kinds in, see who passes and who fails), rather than reading the UI's source string
        -- that kind of "source sentinel" cannot catch "the condition was changed to `if True`".
        Two exceptions, both things that "look like entries but are not":
        * `kind` is empty (old callbacks do not pass a type) -> **allow**. That is the historical path for "cannot say what it is";
          blocking it outright would make an entire narrative stream silently disappear (far more serious than showing one extra line).
        * Starts with `divider:` -> **allow**. Dividers (day boundary / act end / story end / module)
          go through **another channel** (`on_divider`); it just also occupies a line in the live stream;
          it is the kind of signpost the user wants for "scene switching", and does not belong to "production process trivia".
    """
    k = str(kind or '')
    if not k:
        return True
    if k.startswith('divider:'):
        return True
    return k in WINDOW_KINDS

# 可见性：同场、场外（只闻其声）、别处（异地同时）
# [EN] Visibility: same scene, off-scene (voice only), elsewhere (different place, same time)
PRESENT = 'present'
OFFSCENE = 'offscene'
ELSEWHERE = 'elsewhere'

VISIBILITY_LABEL = {
    PRESENT: '在场',
    OFFSCENE: '场外',
    ELSEWHERE: '别处',
}

# 屏幕渲染时的缩进层级（GUI 与 CLI 共用，保证两边看起来一样）
# [EN] Indentation level during screen rendering (shared by GUI and CLI, so both sides look the same)
INDENT = {
    TIME: 0, SCENE: 0, ENTER: 0, EXIT: 0, NARRATION: 0, DIALOGUE: 0,
    ACTION: 1, ASIDE: 1, AMBIENT: 1, RECALL: 1, EVENT: 0, BEAT: 0,
    NOTE: 0, IMAGE: 1, RECAP: 0,
}


# ══════════════════════════════════════════════════════════════
#  并行轨（「同一时刻不同人在做不同事」的载体）
# [EN] Parallel track (the carrier of "different people doing different things at the same moment")
# ══════════════════════════════════════════════════════════════
@dataclass
class Track:
    """并行轨的一条：某个主体此刻在做的一件事。

    主体可以是人物，也可以是环境/群像（用 `subject='街上'` 这类），
    因为「同一时刻」不只有人在做事——环境也在发生。
    
        English:
    One of the parallel tracks: one thing a subject is doing at this moment.
        The subject can be a character, or the environment / crowd (using something like `subject='the street'`),
        because "the same moment" is not only people doing things -- the environment is also happening.
    """
    subject: str
    text: str
    visibility: str = PRESENT
    # 该轨所属地点（异地同时时用；同场时留空）
    # [EN] The location this track belongs to (used for different place, same time; left empty for same
    # [EN] scene)
    place: str = ''
    # 该主体是否在说话（并行轨里也可以有对白，如两人同时开口）
    # [EN] Whether this subject is speaking (parallel tracks can also contain dialogue, e.g. two people
    # [EN] speaking at once)
    is_speech: bool = False
    anchors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {'subject': self.subject, 'text': self.text,
                'visibility': self.visibility, 'place': self.place,
                'is_speech': self.is_speech, 'anchors': self.anchors}

    @classmethod
    def from_dict(cls, d: dict) -> 'Track':
        return cls(subject=str(d.get('subject', '')),
                   text=str(d.get('text', '')),
                   visibility=str(d.get('visibility') or PRESENT),
                   place=str(d.get('place', '')),
                   is_speech=bool(d.get('is_speech')),
                   anchors=dict(d.get('anchors') or {}))


# ══════════════════════════════════════════════════════════════
#  词条
# [EN] Entry
# ══════════════════════════════════════════════════════════════
@dataclass
class Entry:
    """一条剧本词条。

    只有 `kind` 和 `text` 是必填，其余按类型取用：

    * `DIALOGUE` 用 `speaker` / `to` / `tone`
    * `ACTION`  用 `speaker` / `visibility`
    * `ASIDE`   用 `speaker`
    * `PARALLEL` 用 `tracks`（`text` 留空）
    * `CUT` / `CUT_BACK` 用 `place`
    * `IMAGE`   用 `image` / `caption`
    * 任何类型都可以带 `anchors`，说明它服务哪条设定
    
        English:
    A script entry.
        Only `kind` and `text` are required; the rest are used according to type:
        * `DIALOGUE` uses `speaker` / `to` / `tone`
        * `ACTION`   uses `speaker` / `visibility`
        * `ASIDE`    uses `speaker`
        * `PARALLEL` uses `tracks` (`text` left empty)
        * `CUT` / `CUT_BACK` use `place`
        * `IMAGE`    uses `image` / `caption`
        * Any type can carry `anchors`, indicating which setting it serves
    """
    kind: str
    text: str = ''
    speaker: str = ''
    to: str = ''
    tone: str = ''                 # 语气/动作提示，如「压低声音」
    # [EN] Tone/action hint, e.g. "lower the voice"
    visibility: str = PRESENT
    place: str = ''
    tracks: list[Track] = field(default_factory=list)
    anchors: dict[str, str] = field(default_factory=dict)
    image: str = ''
    caption: str = ''
    # 出处标记：用于「这段是程序生成的」vs「这段是 LLM 写的」，便于审校
    # [EN] Provenance marker: used to distinguish "this passage is program-generated" vs "this passage is
    # [EN] LLM-written", for review
    source: str = ''
    # 显示优先级（沿用阅读节奏器 P0-P3 语义，0 最高）
    # [EN] Display priority (follows the reading-rhythm P0-P3 semantics, 0 is highest)
    priority: int = 2

    def __post_init__(self) -> None:
        if self.kind not in ALL_KINDS:
            raise ValueError(f'未知词条类型: {self.kind!r}')
        # ★★★ 2026-10-17：**在唯一入口洗掉行内元标记**（见 `META_MARK_RE` 那段）。
        #   `Entry` 是台本落盘 / 界面中栏 / 原文稿 / 参考稿 / 小说版本 五个出口的
        #   共同上游 ⇒ 在这里洗一次，五处全干净；各出口各洗一遍就是五处实现。
        #   ⚠ 转场标记不受影响（正则里没有 切至/切回/同时）。
        # [EN] ★★★ 2026-10-17: **wash inline metadata markers at the single entry point** (see the
        # [EN] `META_MARK_RE` block). `Entry` is the shared upstream of all five exits (persisted
        # [EN] script / middle-column UI / raw copy / reference copy / novel version) => one wash here
        # [EN] cleans all five; washing in each exit would be five implementations.
        # [EN] ⚠ Transition markers are untouched (the regex has no 切至/切回/同时).
        if self.text:
            self.text = strip_meta_marks(self.text)

    # ── 便捷构造 ──
    # [EN] ── Convenience constructors ──
    @property
    def is_stage_direction(self) -> bool:
        """是不是"舞台指示"（进场/退场/停顿/标注）——屏幕上用更暗的样式。
                English:
        Whether it is a "stage direction" (entrance/exit/pause/annotation) -- on screen it uses a dimmer
        style.
        """
        return self.kind in (ENTER, EXIT, BEAT, NOTE)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {'kind': self.kind}
        for key in ('text', 'speaker', 'to', 'tone', 'place', 'image',
                    'caption', 'source'):
            if getattr(self, key):
                d[key] = getattr(self, key)
        if self.visibility != PRESENT:
            d['visibility'] = self.visibility
        if self.tracks:
            d['tracks'] = [tk.to_dict() for tk in self.tracks]
        if self.anchors:
            d['anchors'] = dict(self.anchors)
        if self.priority != 2:
            d['priority'] = self.priority
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Entry':
        return cls(
            kind=str(d.get('kind', NARRATION)),
            text=str(d.get('text', '')),
            speaker=str(d.get('speaker', '')),
            to=str(d.get('to', '')),
            tone=str(d.get('tone', '')),
            visibility=str(d.get('visibility') or PRESENT),
            place=str(d.get('place', '')),
            tracks=[Track.from_dict(t) for t in (d.get('tracks') or [])],
            anchors=dict(d.get('anchors') or {}),
            image=str(d.get('image', '')),
            caption=str(d.get('caption', '')),
            source=str(d.get('source', '')),
            priority=int(d.get('priority', 2)),
        )


# ══════════════════════════════════════════════════════════════
#  一幕（一个小节 / 一场戏）
# [EN] An act (a section / a scene)
# ══════════════════════════════════════════════════════════════
@dataclass
class SceneScript:
    """一幕戏：一个连续时间、一个地点、一组词条。
        English:
    One scene: one continuous time, one place, one set of entries.
    """

    # 幕首信息（对应设计稿 §10.6 的 `## <时辰/时段> · <小节标题>`）
    time_label: str = ''        # 时间说明，如「戌时 19:30」
    place: str = ''             # 场景说明：地点
    place_desc: str = ''        # 场景说明：环境一行（光/声/气味）
    # [EN] Act header info (corresponds to `## <time period/slot> · <section title>` in design doc §10.6)
    # [EN] Time description, e.g. "戌时 19:30"
    # [EN] Scene description: location
    # [EN] Scene description: environment line (light/sound/smell)
    weather: str = ''
    title: str = ''             # 小节标题
    # [EN] Section title

    # 幕内
    # [EN] Within the act
    entries: list[Entry] = field(default_factory=list)

    # 幕首在场名单（渲染「出场/退场」时用的基线）
    # [EN] Act header present-cast list (the baseline used when rendering "entrance/exit")
    cast: list[str] = field(default_factory=list)

    # 出处（「本幕依据」，让"这段戏在推进什么"可见）
    # [EN] Provenance ("basis for this act", makes visible "what this scene is advancing")
    day: int = 1
    node: str = ''
    node_name: str = ''
    tension_before: float = 0.0
    tension_after: float = 0.0
    anchors: dict[str, str] = field(default_factory=dict)
    started: bool = True        # 是否已经写入幕首（build 时用）
    # [EN] Whether it has already been written to the act header (used at build time)

    # ── 追加 ──
    # [EN] ── Append ──
    def add(self, entry: Entry) -> Entry:
        self.entries.append(entry)
        return entry

    def extend(self, entries: list[Entry]) -> None:
        self.entries.extend(entries)

    # ── 查询 ──
    # [EN] ── Query ──
    def by_kind(self, kind: str) -> list[Entry]:
        return [e for e in self.entries if e.kind == kind]

    def speakers(self) -> list[str]:
        """出过声的人（去重保序）。
                English:
        People who have spoken (deduplicated, order preserved).
        """
        out: list[str] = []
        for e in self.entries:
            for name in ([e.speaker] if e.speaker and e.kind == DIALOGUE else []):
                if name not in out:
                    out.append(name)
        return out

    def actors(self) -> list[str]:
        """有过动作的人（去重保序）——**这个和 speakers 的差集，就是
        「在场但没说话的人」，正是"人物不是一直说话"需要被看见的部分。**
                English:
        People who have acted (deduplicated, order preserved) -- **the difference between this and
        speakers is
                "people present but not speaking", exactly the part that needs to be seen for "characters do not always speak".**
        """
        out: list[str] = []
        for e in self.entries:
            candidates = [e.speaker] if e.speaker else []
            candidates += [t.subject for t in e.tracks if t.subject]
            for name in candidates:
                if name and name not in out:
                    out.append(name)
        return out

    @property
    def empty(self) -> bool:
        return not any(e.kind != NOTE for e in self.entries)

    def to_dict(self) -> dict:
        return {
            'time_label': self.time_label, 'place': self.place,
            'place_desc': self.place_desc, 'weather': self.weather,
            'title': self.title, 'cast': list(self.cast), 'day': self.day,
            'node': self.node, 'node_name': self.node_name,
            'tension_before': self.tension_before,
            'tension_after': self.tension_after,
            'anchors': dict(self.anchors),
            'entries': [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'SceneScript':
        return cls(
            time_label=str(d.get('time_label', '')),
            place=str(d.get('place', '')),
            place_desc=str(d.get('place_desc', '')),
            weather=str(d.get('weather', '')),
            title=str(d.get('title', '')),
            entries=[Entry.from_dict(e) for e in (d.get('entries') or [])],
            cast=list(d.get('cast') or []),
            day=int(d.get('day', 1)),
            node=str(d.get('node', '')),
            node_name=str(d.get('node_name', '')),
            tension_before=float(d.get('tension_before') or 0.0),
            tension_after=float(d.get('tension_after') or 0.0),
            anchors=dict(d.get('anchors') or {}),
        )


# ══════════════════════════════════════════════════════════════
#  构造辅助（其他模块用这些，不要手搓 Entry）
# [EN] Construction helpers (other modules use these, don't hand-roll Entry)
# ══════════════════════════════════════════════════════════════
def narration(text: str, *, source: str = '', **kw) -> Entry:
    return Entry(NARRATION, text, source=source, priority=2, **kw)


def scene_desc(place: str, desc: str = '', *, weather: str = '') -> Entry:
    text = desc or '（无环境说明）'
    return Entry(SCENE, text, place=place, caption=weather, priority=2)


def enter(name: str, how: str = '') -> Entry:
    return Entry(ENTER, how, speaker=name, priority=3)


def exit_(name: str, how: str = '') -> Entry:
    return Entry(EXIT, how, speaker=name, priority=3)


def dialogue(speaker: str, text: str, *, to: str = '', tone: str = '',
             anchors: dict | None = None) -> Entry:
    return Entry(DIALOGUE, text, speaker=speaker, to=to, tone=tone,
                 anchors=anchors or {}, priority=1)


def action(who: str, text: str, *, visibility: str = PRESENT,
           place: str = '', anchors: dict | None = None) -> Entry:
    return Entry(ACTION, text, speaker=who, visibility=visibility, place=place,
                 anchors=anchors or {}, priority=3)


def aside(who: str, text: str) -> Entry:
    return Entry(ASIDE, text, speaker=who, priority=2)


def ambient(text: str, *, place: str = '') -> Entry:
    """环境白描 / 群像背景 —— 全场无事的那些片刻写它，比一句"片刻无话"实在。
        English:
    Environmental description / crowd background -- write it for those moments when nothing happens
    on stage; more substantial than a line saying "a moment of silence".
    """
    return Entry(AMBIENT, text, place=place, priority=3)


def recall(who: str, text: str) -> Entry:
    """回想 / 省思 —— 人物心里翻出来的旧事（区别于 `aside` 的"当下心声"）。
        English:
    Flashback / reflection -- old events surfacing in a character's mind (different from `aside`'s
    "present inner voice").
    """
    return Entry(RECALL, text, speaker=who, priority=2)


def parallel(tracks: list[Track], *, note: str = '') -> Entry:
    return Entry(PARALLEL, note, tracks=tracks, priority=2)


def cut(place: str, note: str = '') -> Entry:
    return Entry(CUT, note, place=place, priority=1)


def cut_back(place: str = '') -> Entry:
    return Entry(CUT_BACK, '', place=place, priority=2)


def event(text: str, *, kind_name: str = '', anchors: dict | None = None) -> Entry:
    return Entry(EVENT, text, caption=kind_name, anchors=anchors or {}, priority=0)


def beat(text: str = '片刻') -> Entry:
    return Entry(BEAT, text, priority=3)


def note(text: str, *, label: str = '', anchors: dict | None = None) -> Entry:
    """机制标注。

    `label` 是屏幕上那行前面那个词（如 `※ 肖像：…` 里的「肖像」），
    **可翻译**；用 `Entry.caption` 这个字段携带 —— 它是现成的自由文本槽，
    JSON 边车会一起存下来（Markdown 只存正文，标签丢了不影响阅读）。
    留空时屏幕显示成 `※ 标注：…`。
    
        English:
    Mechanism annotation.
        `label` is the word in front of that line on screen (e.g. "Portrait" in `※ Portrait: ...`),
        **translatable**; carried via the `Entry.caption` field -- it is a ready-made free-text slot,
        and the JSON sidecar will save it along (Markdown only saves the body text, losing the label does not affect reading).
        When left empty, the screen displays `※ Annotation: ...`.
    """
    return Entry(NOTE, text, caption=label,
                 anchors=anchors or {}, priority=3)


def image(path: str, caption: str = '', *, kind_hint: str = '') -> Entry:
    return Entry(IMAGE, kind_hint, image=path, caption=caption, priority=2)


def recap(text: str) -> Entry:
    """前情提要 —— **开演前那一段回顾**（用户 2026-10-07：「每次推演开始
    一开始应该有一小段前情提要」）。

    ⚠ 它**不是当天发生的事**，所以不进正文的段落流（见
      `display/story_render.py` 的 `NON_INDENT`）—— 屏幕上它是一块独立的
      方块，跟「（进度）节点完成」那种机制标注也分开（那是体检报告，不是故事）。
    
        English:
    Previously on -- **that recap segment before the show starts** (user 2026-10-07: "every
    simulation should start
        with a short previously-on at the beginning").
        ⚠ It is **not something that happened today**, so it does not enter the body's paragraph stream (see
          `NON_INDENT` in `display/story_render.py`) -- on screen it is an independent
          block, and is also separate from mechanism annotations like "(progress) node complete" (that is a health report, not the story).
    """
    return Entry(RECAP, text, priority=1)


def brief(text: str) -> Entry:
    """今日剧情简介 —— **正式剧情之前那一段**（用户 2026-10-07 要的）。

    与 `recap()` 同一套：它也不是当天发生的事，所以不进正文的段落流，
    屏幕上是一块独立方块（见 `story_render.NON_INDENT` 与
    `gui/app_flet.py::NARR_BLOCK_STYLE['brief']`）。
    
        English:
    Today's plot brief -- **that segment before the formal plot** (requested by the user
    2026-10-07).
        Same scheme as `recap()`: it is also not something that happened today, so it does not enter the body's paragraph stream,
        and on screen it is an independent block (see `story_render.NON_INDENT` and
        `gui/app_flet.py::NARR_BLOCK_STYLE['brief']`).
    """
    return Entry(BRIEF, text, priority=1)
