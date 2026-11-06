# -*- coding: utf-8 -*-
"""故事进度表 + 正文对齐（设计稿 §3.5）。

核心：从大纲提取有序节点，正文逐章对齐标记已完成节点，
产出已发生故事线（前情提要），建议起始点。

English:
Story progress table + body text alignment (design doc §3.5).
Core: extract ordered nodes from the outline, align body text chapter by chapter to mark
completed nodes,
produce the occurred storyline (recap), suggest a starting point.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

from llm.replies import ask
from util.jsonio import extract_json_lenient
from util.io import atomic_write_text
from util.chapters import (  # noqa: F401  （`split_chapters` / `chapter_no` 是**再导出**）
    chapter_no, cn_to_int, split_chapters,
)
from util.text import fill

_LOG = __import__("logging").getLogger("nws.ingest")


#: **跨度档**：这一站覆盖多久的故事时间。**闭集**（不许自由文本）。
#:
#: ★★★ 2026-10-26 新增。根因见 `docs` 里那一整套说明（简版）：
#:   小说的时间不是匀速的 —— "太原站、崂山站、莒州站"三站之间可能隔了几个月，
#:   而"开庭抉择"那一天要细写到每一句话。以前节点**只有内容、没有体量**，
#:   程序只好让一个匀速时钟去填满每一天，于是「一天 = 133 幕 / 21.3 万字」。
#:
#: ⚠ 必须是闭集：自由文本（"大概两个月吧"）没法拿去算拍预算，
#:   而"算不出来就落默认值"等于这个字段不存在。
# [EN] **Span ladder**: how much story time this node covers. **Closed set** (no free text).
# [EN] Novels do not run on a uniform clock -- three stations may span months while the final
# [EN] hearing is written line by line. Nodes used to carry **content but no volume**, so a uniform
# [EN] clock had to fill every single day: "one day = 133 acts / 213k characters".
# [EN] ⚠ Must be a closed set: free text ("maybe two months") cannot drive a beat budget, and
# [EN] "unparseable falls back to a default" makes the field non-existent in practice.
SPANS: tuple[str, ...] = ('一场', '当日', '数日', '一旬', '数月')

#: **篇幅档**：这一站该写多厚。**闭集**。
#: `详` = 一场戏细写到底；`带过` = 一句话交代过去。
# [EN] **Length ladder**: how thickly to write this node. Closed set.
WEIGHTS: tuple[str, ...] = ('详', '中', '略', '带过')

#: 篇幅档 → **拍预算** `(下限, 上限)`。
#:
#: ★★★ 这个表是全项目的**唯一事实来源**：导演分拍、硬闸收束、界面提示都读它。
#:   以前 `ROUND_DAILY_WORDS` 是个**软目标**（"告诉编剧大概写多少"）+ 且默认为 0（不限）
#:   ⇒ 一拍都不封顶 ⇒ 一天能演 133 幕。软目标挡不住任何东西。
#:
#: ⚠ 数字不是拍的：实测一段"能读的场景"大约 15~25 拍（每拍 1~3 句台词），
#:   所以 `中` 就取这个区间；`详` 翻倍多一点；`略` 只够交代一件事；
#:   `带过` 允许 1 拍（**但不允许 0 拍** —— 0 拍等于这一站不存在，
#:   而进度判据要凭事件推进，一拍不演它永远推不动）。
# [EN] Length ladder → **beat budget** `(min, max)`. This table is the **single source of truth**
# [EN] for the whole project: the director splitting beats, the hard stop, and the UI all read it.
# [EN] `ROUND_DAILY_WORDS` used to be a **soft** target (`0` = unlimited) and a soft target stops
# [EN] nothing -- one day reached 133 acts. The numbers are measured: a readable scene is about
# [EN] 15-25 beats, so `中` takes that band, `详` about double, `略` enough for one event, and
# [EN] `带过` allows a single beat (**never zero** -- zero beats means the node never advances,
# [EN] while the progress criterion reads events).
BEAT_BUDGET: dict[str, tuple[int, int]] = {
    '详': (40, 60),
    '中': (15, 25),
    '略': (3, 8),
    '带过': (1, 1),
}

#: **一拍大约写多少汉字**（实测值，2026-10-30）。
#:
#: 用来把"每章字数"换算成"这一天该演几拍"。以前拍数只由上面那张表定，
#: 而那张表是按"一拍 ≈ 76 字"那个年代的实测定的 —— 现在一拍早已不是那个体量了：
#:   · `第1次模拟` 第 1 天：9 幕 / 4,949 汉字 ⇒ **≈ 550 字/拍**；
#:   · `第2次模拟` 第 1 天：1 幕 / 561 字符（中途稿）⇒ ≈ 550 字/拍。
#: ⇒ 按旧表演 15~25 拍其实写出 **8,000~13,000 字**（五章的体量），
#:   而设定集里写的"每章 2,400 字"根本对不上。这就是用户问的"一天到底给多少字"。
#: ⚠ 它只是**换算系数**，不是硬闸：真正的硬闸仍然是拍数（见 `beats_for_words`）。
# [EN] **How many Chinese characters one beat produces** (measured 2026-10-30). Used to turn the
# [EN] book's "words per chapter" into "how many beats this day gets". The tier table above was
# [EN] calibrated when a beat produced ~76 chars; today it is ~550 (measured: 4,949 chars over 9
# [EN] scenes, and 561 chars in a one-scene mid-run draft), so 15-25 beats actually wrote 8k-13k
# [EN] characters -- five chapters, not one. That is exactly the user's "how many words does a day
# [EN] actually give". ⚠ A conversion factor, not a gate: the gate is still the beat count.
CHARS_PER_BEAT = 550

#: 一天最多几拍（换算出来的拍数封顶）。防"每章字数写成 5 万"这种误填把一天拉成 90 拍。
# [EN] Ceiling on the converted beat count, so a typo like "50,000 words per chapter" cannot stretch
# [EN] one day to 90 beats.
MAX_BEATS_BY_WORDS = 30


def beats_for_words(words: int) -> int:
    """**每章字数 → 这一天的拍数**（`words / CHARS_PER_BEAT`，夹在 `[1, MAX_BEATS_BY_WORDS]`）。

    ⚠ `words <= 0` 时返回 `0`（＝"这本书没写目标字数，别管我"），调用方要自己判断 ——
      返回 1 会让"没写"变成"一天一拍"，那是最坏的一种默认。
    [EN] **Words per chapter -> beats for one day**. ⚠ Returns `0` when `words <= 0` (= "this book
    [EN] declared no target, leave me alone"); returning 1 would turn "unset" into "one beat a day".
    """
    try:
        w = int(words or 0)
    except Exception:                                            # noqa: BLE001
        return 0
    if w <= 0:
        return 0
    n = int(round(w / float(CHARS_PER_BEAT)))
    return max(1, min(MAX_BEATS_BY_WORDS, n))

#: **跨度档 → 这一站吃掉多少故事时间**（分钟）。闭集，与 `SPANS` 一一对应。
#:
#: ★★★ 2026-10-26（用户选 A：**日界 = 拍预算用完**）：
#:   这是"小说时间不是匀速的"真正落到时钟上的那一步。
#:   以前一拍推多久是 `BEAT_SECONDS`（60 故事秒 = 1 分钟）**恒定**，于是
#:   "一场审讯"和"三个月的赶路"拍数相同的话占用一样长的故事时间 ——
#:   那不是小说，那是秒表。现在一拍推多久由 **跨度 ÷ 拍数** 算出来。
#:
#: ⚠ 数字的来源（每一条都对着"小说里这一段该占多少故事时间"）：
#:   · `一场` 2 小时 —— 一场戏（审讯 / 摊牌 / 对决）通常一个晚上就完；
#:   · `当日` 12 小时 —— 一天里醒着的那段（早到夜）；
#:   · `数日` 3 天 —— "走了三天的路"；
#:   · `一旬` 10 天 —— "十天之后"；
#:   · `数月` 90 天 —— "此后三个月无事"。
#: ⚠ 这些是**故事时间**，不是"写多厚"——写多厚是 `BEAT_BUDGET`（拍数）。
# [EN] **Span tier -> how much story time this station eats** (minutes). Closed set, one per
# [EN] `SPANS` entry. ★★★ 2026-10-26 (the user chose A: **the day ends when the beat budget runs
# [EN] out**): this is where "novel time is not uniform" finally reaches the clock. It used to be
# [EN] a constant `BEAT_SECONDS` (60 story seconds = 1 minute) per beat, so "one interrogation"
# [EN] and "three months on the road" occupied the same amount of story time if they had the same
# [EN] beat count -- a stopwatch, not a novel. Now the per-beat duration is **span / beats**.
# [EN] ⚠ Every number answers "how much story time should this stretch take": a scene 2 hours, a
# [EN] day 12 waking hours, a few days 3 days, ten days 10 days, months 90 days.
# [EN] ⚠ This is **story time**, not "how thick to write" (that is `BEAT_BUDGET`).
SPAN_MINUTES: dict[str, int] = {
    '一场': 2 * 60,
    '当日': 12 * 60,
    '数日': 3 * 24 * 60,
    '一旬': 10 * 24 * 60,
    '数月': 90 * 24 * 60,
}

#: 一拍推多少**故事分钟**的上下限。
#:
#: ★★★ 2026-10-26：这两个数是"一拍"这个概念本身的边界，不是拍的。
#:   · 下限 **1 分钟**：一拍不该比一分钟更短 —— 电影的"一个镜头"也几十秒起，
#:     再短读者感觉不到时间在动，而且"每隔 N 故事分钟"那类节拍（`AMBIENT_MINUTES`）会失效。
#:   · 上限 **30 分钟**：一拍是**场景内的一个节拍**（一个人做一件事、说一两句）。
#:     一次换场、一段等待，最多半小时。**再长的"时间流逝"不是拍该干的事** ——
#:     那是"过场"：站末把剩余时间一次跳掉（`sim/loop._end_day`），并推一句旁白。
#:   ⚠ 所以 `数月 + 带过`（跨度 90 天、1 拍）不是"一拍 90 天"，而是
#:     "一拍 30 分钟 + 站末跳 89 天 23.5 小时"，读起来正是「此后三个月无事」。
# [EN] Bounds for one beat's story duration. ⚠ These are the bounds of the **concept** "one beat",
# [EN] not arbitrary numbers. Floor 1 minute: a beat shorter than that and the reader cannot feel
# [EN] time moving (and "every N story minutes" tempos stop working). Ceiling 30 minutes: a beat is
# [EN] **one pulse inside a scene** (one person doing one thing, one or two lines); a scene change
# [EN] or a wait is at most half an hour. **Longer time passing is not a beat's job** -- that is a
# [EN] transition: the remaining time is jumped at the end of the station and narrated in one line.
# [EN] ⚠ So `months + in passing` is NOT "90 days in one beat" but "30 minutes in one beat, then a
# [EN] 89-day jump at the station's end" -- which is exactly how "nothing happened for three
# [EN] months" reads.
BEAT_MIN_MINUTES = 1
BEAT_MAX_MINUTES = 30

#: 默认篇幅档（节点既没写、也推不出来时）。取 `中` 而不是 `详`：
#: 猜厚了会烧钱，猜薄了作者能看见"这一站太短"再补 —— 两种错法的代价不对称。
# [EN] Default length tier when a node neither states nor implies one. `中`, not `详`: guessing thick
# [EN] burns money, guessing thin is visible and re-runnable -- the two errors are not symmetric.
DEFAULT_WEIGHT = '中'
DEFAULT_SPAN = '当日'

#: **篇幅档 → 这一站默认写几章**（作者没在节点上写 `章数` 时用）。
#:
#: ★★★ 2026-10-27（用户：「每个地方至少有若干章节……这个我可以在设定集里设定吗」）：
#:   以前"这一站写多厚"只有 `篇幅`（拍预算，**一天**的口径），
#:   而"这一站占几章"**根本没有字段** —— 于是同一件事演一天就过站，
#:   八个地点跑完只剩八章，每个地点连起承转合都摊不开。
#:   这一张表把"详略"和"章数"接起来：`详` 该摊 4 章、`略` 一章够了。
#:
#: ⚠ 数字怎么来的（与 `BEAT_BUDGET` 同一套实测）：
#:   · 一章 = 一天 = 一份整理稿（实测中档一天约 1900 字）；
#:   · `详` 一天 40~60 拍，一件事要摊开"起承转合 + 余波"才装得下 ⇒ 4 章；
#:   · `中` 一天 15~25 拍 ⇒ 3 章够讲完一件事；
#:   · `略` 只够交代发生了什么 ⇒ 2 章（**不取 1**：判据达成即过站的话，
#:     作者会看到"这一站一章就走了"，而‘略’的意思只是"别细写"，不是"跳过"）；
#:   · `带过` 就是一句话带过去 ⇒ 1 章。
#: ⚠ 作者写了 `章数` 时**以作者的为准**（`min_chapters_for`），这张表只是兜底。
# [EN] **Length tier -> how many chapters this station defaults to** (used when the node carries no
# [EN] `章数`). ★★★ 2026-10-27 (user: "I want each place to have at least a few chapters ... can I
# [EN] set that in the setting collection?"): "how thickly to write one station" only had `篇幅`
# [EN] (the beat budget, a **per-day** measure), while "how many chapters this station occupies" had
# [EN] **no field at all** -- so a station advanced after a single day and eight places produced
# [EN] eight chapters, too few to even lay out a beginning/middle/end per place. This table joins
# [EN] thickness to chapter count. ⚠ Where the numbers come from (same measurements as
# [EN] `BEAT_BUDGET`): one chapter = one day = one organized draft (a `中` day measured ~1900 chars);
# [EN] `详` is 40-60 beats a day, so unfolding setup/rising/turn/aftermath needs 4 chapters; `中` 3;
# [EN] `略` 2 (**not 1**: "in brief" means "don't write it thick", not "skip it"); `带过` is one line,
# [EN] so 1. ⚠ An author-written `章数` **wins** (`min_chapters_for`); this table is only the fallback.
MIN_CHAPTERS: dict[str, int] = {'详': 4, '中': 3, '略': 2, '带过': 1}

#: 一个站的章数上限。超过这个数作者多半是写错了（把"第 5–8 章"这种原著章号填进来了）。
# [EN] Upper bound for one station's chapter count. Beyond this the author probably filled in
# [EN] source-novel chapter numbers ("chapters 5-8") instead of "how many chapters to write".
MAX_CHAPTERS = 20

#: **站内的台阶**（2026-10-27 新增）：高潮一句、情节单元若干、结局选项若干。
#:
#: 为什么要这一层：`完成判据` 只说了**终点线**，没说这一站**从哪儿走到哪儿**。
#: 于是"这一站要演 5 章"时，导演每天只能拿 80 字概要现编 —— 实测出来的样子是
#: "天数够了、但每天在原地打转"。章数硬闸**只保证天数，不保证推进**，这一层管推进。
#: ⚠ 三个都是**可选**：老项目没有就留空，推演行为与以前完全一致。
#: [EN] **The steps inside a station** (added 2026-10-27): one climax line, a few plot units, a few
#: [EN] ending options. Why: `criteria` states only the **finish line**, not the path, so a
#: [EN] five-chapter station leaves the director improvising from an 80-char summary each day --
#: [EN] measured behaviour is "enough days, no progress". The chapter floor **guarantees days, not
#: [EN] progress**; this layer is what guarantees progress. All three are **optional**.
CLIMAX_MAX_CHARS = 150
BEATS_MAX_ITEMS = 6
BEATS_EACH_CHARS = 80
OPTIONS_MAX_ITEMS = 6
OPTIONS_EACH_CHARS = 40

#: 跨度推断规则：`(档, 关键词…)`，**从上往下第一个命中的胜**。
#:
#: ⚠ 顺序是从"长"到"短"：`数月` 里含 `月`、`数日` 里含 `日`，先判短的会把长的
#:   吃掉一半（虽然这几条不互为子串，但以后加词就容易踩 —— 顺序写死在这里更稳）。
#: ⚠ 中文没有词边界（本项目的老教训）：这里也**必须**只在"整词"上判，
#:   所以关键词都写成两字以上，不写单字（`月` / `日` 这种会误命中的一律不用）。
# [EN] Span inference rules: `(tier, keywords...)`, **first match from the top wins**. Ordered
# [EN] longest-to-shortest; keywords are all two characters or more because Chinese has no word
# [EN] boundary and single characters (`月` / `日`) would match far too much.
_SPAN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('数月', ('数月', '几个月', '半年', '多月', '整月', '经年', '多年',
              '一年', '两年', '三年', '数年', '岁月', '光阴')),
    ('一旬', ('一旬', '旬日', '半月', '半个月', '十余日', '十来天', '十日')),
    ('数日', ('数日', '几日', '几天', '三日', '五日', '七日', '翌日', '次日',
              '隔日', '数天')),
    ('一场', ('一场', '一席', '一晚', '一夜')),
    ('当日', ('当夜', '当天', '当日', '这一日', '这一天', '雨夜', '月圆之夜',
              '清晨', '中午', '傍晚', '深夜')),
)

#: 篇幅推断规则：`(档, 关键词…)`，同样从上往下第一个命中。
#: ⚠ 只放**明确的转折语**：`真相`/`对决`/`抉择` 这种，放 `发现` 会把半个大纲都判成详写。
# [EN] Length inference rules: first match from the top. Only **unambiguous turning-point words**
# [EN] here -- adding something like `发现` would tag half an outline as `详`.
_WEIGHT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('带过', ('途中', '路上', '一路', '往来', '流转', '过了', '转眼', '一晃',
              '日常', '平淡', '无事')),
    ('详', ('对决', '对峙', '真相', '坦白', '抉择', '开庭', '当众', '摊牌',
            '表白', '决裂', '生死', '决战', '揭穿', '认罪')),
    ('略', ('得知', '听说', '传来', '交代', '安排', '收拾', '辞行', '告别',
            '启程', '抵达')),
)


def infer_span(node: "ProgressNode", idx: int = 0, total: int = 0) -> str:
    """从节点的名字/概要**推断跨度档**（作者没写时）。

    ★ 除了关键词，还有一条**结构性**依据：概要里出现多个地名（"太原站…崂山站…莒州站"）
      ⇒ 这一站在路上，跨度不可能只有一天。这条比关键词可靠 —— 关键词是猜语气，
      地名个数是数出来的。
    [EN] Infer the span tier from the node's name/summary. Besides keywords there is one
    [EN] **structural** signal: several place names in the summary ("Taiyuan ... Laoshan ...
    [EN] Juzhou") means this node travels, so it cannot cover a single day. That is more reliable
    [EN] than keywords -- keywords guess tone, counting place names is counting.
    """
    text = f"{getattr(node, 'name', '')} {getattr(node, 'summary', '')}"
    for tier, words in _SPAN_RULES:
        if any(w in text for w in words):
            return tier
    # 结构依据：≥3 个「…站」⇒ 这一站在跨站赶路，至少数日
    if len(re.findall(r'[\u4e00-\u9fff]{2,4}站', text)) >= 3:
        return '数月'
    if len(re.findall(r'[\u4e00-\u9fff]{2,4}站', text)) == 2:
        return '数日'
    return DEFAULT_SPAN


def infer_weight(node: "ProgressNode", idx: int = 0, total: int = 0) -> str:
    """从节点的名字/概要推断篇幅档（作者没写时）。

    ★ 结构依据两条（都与"位置"有关，比关键词稳）：
      · **第一个节点**通常是开场 —— 要立人物与氛围，给 `中`，不给 `带过`；
      · **最后一个节点**通常是收束 —— 给 `中`，不给 `带过`（结尾被一句带过是最伤的）。
      ⚠ 不因为"是高潮"就猜 `详`：那要靠作者写，程序猜厚会直接烧钱。
    [EN] Infer the length tier. Two structural signals beat keywords: the **first** node is the
    [EN] opening (needs room to establish people and mood -> `中`, never `带过`), and the **last** is
    [EN] the ending (`中` too -- skipping the ending in one line is the worst outcome). It never
    [EN] guesses `详` just because a node "feels like a climax": that is the author's call, and
    [EN] guessing thick burns money.
    """
    text = f"{getattr(node, 'name', '')} {getattr(node, 'summary', '')}"
    for tier, words in _WEIGHT_RULES:
        if any(w in text for w in words):
            return tier
    if total and idx in (0, total - 1):
        return '中'
    return DEFAULT_WEIGHT


def resolve_span_weight(nodes: list["ProgressNode"]) -> list["ProgressNode"]:
    """把每个节点缺的 `跨度` / `篇幅` 补齐，并**照实标注哪几维是推的**。

    ⚠ 只在**内存里**补，写盘时由 `to_dict` 带着 `推断：跨度（程序推的，可改）`
      一起落进 `故事进度.yaml` —— 让作者一眼看到"这两个是我没写、程序猜的"。
    ⚠ 作者已经写了的**一个字都不动**（哪怕写的是 `详` 而程序觉得该 `略`）。
    [EN] Fill in any missing `span` / `weight` and **record which dimensions were inferred**.
    [EN] In-memory only; `to_dict` writes the marker into `故事进度.yaml` so the author can see
    [EN] exactly which two fields the program guessed. ⚠ Author-written values are **never touched**.
    """
    total = len(nodes)
    out: list[ProgressNode] = []
    for i, n in enumerate(nodes):
        inferred: list[str] = list(getattr(n, 'inferred', ()) or ())
        if not getattr(n, 'span', ''):
            n.span = infer_span(n, i, total)
            if 'span' not in inferred:
                inferred.append('span')
        elif n.span not in SPANS:
            # 作者写了自由文本（"两个月"）⇒ 归一到最近的档，并标明被程序改过
            # [EN] The author wrote free text ("two months"): normalise to the nearest tier and say so.
            n.span = _nearest_span(n.span)
            if 'span' not in inferred:
                inferred.append('span')
        if not getattr(n, 'weight', ''):
            n.weight = infer_weight(n, i, total)
            if 'weight' not in inferred:
                inferred.append('weight')
        elif n.weight not in WEIGHTS:
            n.weight = _nearest_weight(n.weight)
            if 'weight' not in inferred:
                inferred.append('weight')
        n.inferred = tuple(inferred)
        out.append(n)
    return out


#: **英文写法**的跨度词（`samples/en` 的样本用英文写，作者也可能这么写）。
#: ⚠ 顺序与中文一致：长跨度在前。`day` 特别宽（`seven days` 会先命中 `days`，这是对的）。
#: ⚠ 只在这里做"自由文本 → 档"的翻译，**档案本身仍然是那五个中文词**
#:   —— `SPANS` 是闭集，落盘也统一写中文，不然 `故事进度.yaml` 里会中英混排。
#: ⚠ **已知差异（不改，记在这里免得下一个人以为漏了）**：`一夜` / `一晚` 这类词，
#:   `infer_span`（关键词表）判 `一场`（2 小时），而 `_nearest_span`（归一）会落到 `当日`。
#:   两者都是"猜"，而且 8 小时的夜更接近 `当日`；但改 `infer_span` 会动到
#:   `verify_progress_split` 的既有断言，且这不是本轮要修的问题 —— 留作已知项。
# [EN] English span words (the `samples/en` stories are written in English, and an author might
# [EN] too). ⚠ Same order as Chinese: longer spans first. `day` is very broad (`seven days` hits
# [EN] `days` first, which is correct). ⚠ This only translates free text into a tier -- the tiers
# [EN] themselves stay the five Chinese words, so the persisted YAML never mixes languages.
# [EN] ⚠ **Known divergence (deliberately not fixed)**: for `一夜` / `一晚`, `infer_span`
# [EN] (keyword table) says `一场` (2 hours) while `_nearest_span` lands on `当日`. Both are
# [EN] guesses, and an 8-hour night is closer to `当日`; fixing `infer_span` would move existing
# [EN] assertions in `verify_progress_split` and is out of scope here -- recorded as known.
_EN_SPAN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('数月', ('month', 'months', 'year', 'years', 'seasons', 'a season')),
    ('一旬', ('fortnight', 'ten days', 'half a month', 'a ten-day')),
    ('数日', ('days', 'day or two', 'several days', 'a few days')),
    ('一场', ('scene', 'one scene', 'single scene', 'one sitting', 'single night')),
    ('当日', ('that day', 'same day', 'one day', 'a day', 'night')),
)

#: **英文写法**的篇幅词。⚠ `full` / `brief` / `in passing` 三档要分清：
#: `in passing` 必须排在 `brief` 之前判（它俩不冲突，但 `pass` 别写成前缀匹配）。
# [EN] English length words. ⚠ Keep the three tiers distinct; match `in passing` explicitly.
_EN_WEIGHT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('带过', ('in passing', 'one line', 'one sentence', 'gloss over', 'pass over')),
    ('详', ('full', 'detailed', 'in detail', 'thorough', 'at length')),
    ('略', ('brief', 'briefly', 'in brief', 'short', 'sketch', 'summary')),
)


#: 中文数字（只认 0~99 的常见写法，够用了）。`两` 也是 2。
#: ⚠ 为什么要它：`_nearest_span` 原来用 `\d+` 抓天数，而 **`\d` 匹配不了"三""十"**
#:   ⇒ 作者写"三天""十天"时一个都不认，直接落到默认档 `当日`。
#:   而那个函数的文档字符串举的例子正是"`十天`→`一旬`" —— **文档承诺了、代码没做到**
#:   （2026-10-26 审核样本时发现）。
# [EN] Chinese numerals (0-99, enough). ⚠ Why: `_nearest_span` used `\d+` for day counts, and
# [EN] **`\d` does not match 三 / 十**, so "三天" / "十天" fell through to the default tier while
# [EN] the docstring right above advertised "十天 -> 一旬". Documentation promised, code didn't.
_CN_DIGIT = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
             '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def _cn_to_int(raw: str) -> int | None:
    """`三`→3、`十五`→15、`二十`→20、`两三`→None（认不出就返回 None，交给调用方兜底）。

    ★ 2026-10-27：实现搬去 `util/chapters.py::cn_to_int`（**全项目唯一一份**）。
      原来这里与 `booklab/selection.py::cn2int` 各写一套中文数字解析，
      而**两套在"两三"上答案不一样**（这里 None、那里 3）—— 现在统一成"非法"。

        English:
    ★ 2026-10-27: the implementation moved to `util/chapters.py::cn_to_int` (the single copy).
      This file and `booklab/selection.py::cn2int` each had their own Chinese-numeral parser, and
      **the two disagreed on "两三"** (None vs 3) -- they now agree on "invalid".
    """
    return cn_to_int(raw)


def _nearest_span(raw: str) -> str:
    """自由文本 → 最近的跨度档（`两个月`→`数月`、`十天`→`一旬`、`one scene`→`一场`）。

    ⚠ **中文写法优先判**（老行为一字不动），中文都对不上才试英文 ——
      这样"作者用中文写的自由文本"永远不会因为加了英文而改变结果。
    ⚠ 「半个月」要判成 `一旬`（15 天）而不是 `数月`：它含"个月"，
      如果先走月的那条规则就会被放大成 90 天。这一条与 `_SPAN_RULES` 里的
      `半月` 同一口径（两处不一致会让"同一个词，两条路给出两个档"）。
    ⚠ 「十日」判 `一旬` 而不是 `数日`：`SPAN_MINUTES` 里 `一旬` 就是 **10 天**，
      而 `数日` 是 3 天。这条口径与 `_SPAN_RULES` 已对齐（那里原来把「十日」
      放在 `数日` 档，同一份代码两个答案 —— 2026-10-26 一并修掉）。
    """
    s = str(raw or '')
    # ① 半个月 / 一旬 / 十来天 —— 必须先于"月"判
    if re.search(r'半(个)?月|一旬|旬日|十来天|十余日', s):
        return '一旬'
    # ② 「几日 / 数天」这种模糊量（没有数字可算）
    if re.search(r'[几数][个]?[日天]', s):
        return '数日'
    # ③ 月 / 年 —— 阿拉伯与中文数字都认（`\d` 认不了"两"）
    if re.search(r'([0-9]+|[零一二两三四五六七八九十]+)\s*年'
                 r'|([0-9]+|[零一二两三四五六七八九十]+)\s*个月'
                 r'|[几数]?个?月|半年|数年', s):
        return '数月'
    # ④ 「N 天 / N 日」—— 10 天起算 `一旬`（与 `SPAN_MINUTES` 对齐）
    m = re.search(r'([0-9]+|[零一二两三四五六七八九十]+)\s*[天日]', s)
    if m:
        tok = m.group(1)
        n = int(tok) if tok.isdigit() else _cn_to_int(tok)
        if n is not None:
            return '一场' if n <= 1 else ('数日' if n < 10 else ('一旬' if n < 25 else '数月'))
    for tier in SPANS:
        if tier in s:
            return tier
    low = s.lower()
    for tier, words in _EN_SPAN_RULES:
        if any(w in low for w in words):
            return tier
    return DEFAULT_SPAN


def _nearest_weight(raw: str) -> str:
    """自由文本 → 最近的篇幅档（`详细`→`详`、`简单交代`→`略`、`in passing`→`带过`）。"""
    s = str(raw or '')
    if any(w in s for w in ('详', '重点', '细', '大书')):
        return '详'
    if any(w in s for w in ('略', '简', '粗', '几句')):
        return '略'
    if any(w in s for w in ('带过', '一笔', '一句')):
        return '带过'
    for tier in WEIGHTS:
        if tier in s:
            return tier
    low = s.lower()
    for tier, words in _EN_WEIGHT_RULES:
        if any(w in low for w in words):
            return tier
    return DEFAULT_WEIGHT


def _weight_of_any(node) -> str:
    """从**三种形状**里取篇幅档：`ProgressNode` / `{'篇幅': …}` / 裸字符串。

    ★★★ 2026-10-26 修的一个真 bug（上一轮引入的）：

    `beat_budget()` 原来只写 `getattr(node, 'weight', '')` —— 而它的两个调用方
    （`director/day_plan.beat_budget_for` 与 `beat_minutes_for`）传的都是
    **`{'篇幅': w}` 这种 dict** ⇒ `getattr` 永远拿不到 ⇒ **永远落到默认档「中」**。
    后果：`详` 的站本该 40~60 拍，实际一直是 15~25 拍 —— **篇幅档对拍数从来没生效过**，
    而 G 组判据（`PR.beat_budget({'篇幅':'详'})`）看不见：它测的是同一个错。

    ⚠ 这类"同一个函数被两种形状调用、只有一种被支持"的错，判据必须**两种形状各测一次**。
    [EN] Read the length tier from **three shapes**: a `ProgressNode`, a `{'篇幅': …}` dict, or a
    [EN] bare string. ★★★ 2026-10-26, fixing a real bug introduced the previous round:
    [EN] `beat_budget()` only did `getattr(node, 'weight', '')`, while both of its callers pass a
    [EN] **`{'篇幅': w}` dict** => `getattr` never sees it => **always fell back to the default
    [EN] "medium" tier**. Consequence: a `详` station should get 40-60 beats and always got 15-25 --
    [EN] **the length tier never affected the beat count**, and the group-G criterion could not see it
    [EN] because it made the same mistake. ⚠ Criteria for a function called with two shapes must test
    [EN] **both shapes**.
    """
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return str(node.get('篇幅') or node.get('weight') or '')
    return str(getattr(node, 'weight', '') or '')


def _parse_chapters(raw) -> int:
    """把作者写的章数归一成**一个整数**。

    认这几种写法（作者真的会这么写，别只认一种）：
      · `3` / `3.0`（YAML 解出来可能是浮点）
      · `"3"` / `"三"`（中文数字）
      · `"3~4"` / `"3-4"` / `"3到4"` → **取下限 3**
        （"3~4 章"是"至少 3 章"的意思；取上限会让每一站都演满，那就没有余量了）
      · 认不出 / 不是正数 → `0`（**0 = 没写**，交给 `MIN_CHAPTERS` 按篇幅档兜底，
        绝不静默当成 1 —— 那会让"作者写了 30"这种错变成"演 1 章就走"）

        English:
    Normalise the author's chapter count into **one integer**. Accepts plain numbers, Chinese
    numerals, and ranges (`3~4` / `3-4` / `3到4` -> the lower bound: "3 to 4 chapters" means
    "at least 3"; taking the upper bound would run every station to its maximum). Unparseable or
    non-positive -> `0` (**0 = not written**, so `MIN_CHAPTERS` can fall back by length tier --
    never silently 1, which would turn a typo like "30" into "advance after one chapter").
    """
    if raw is None:
        return 0
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, (int, float)):
        n = int(raw)
        return n if 0 < n <= MAX_CHAPTERS else 0
    s = str(raw or '').strip()
    if not s:
        return 0
    # 区间：取**第一个**整数作为下限
    # [EN] Range: the **first** integer is the lower bound
    m = re.search(r'\d+', s)
    if m:
        n = int(m.group())
        return n if 0 < n <= MAX_CHAPTERS else 0
    # 中文数字（"三"、"四"）
    # [EN] Chinese numeral
    m = re.match(r'^([零一二两三四五六七八九])$', s)
    if m:
        n = _CN_DIGIT.get(m.group(1), 0)
        return n if 0 < n <= MAX_CHAPTERS else 0
    return 0


def _clip_text(raw, n: int) -> str:
    """把一段自由文本压到 `n` 字（高潮用）。

    ⚠ **硬截断而不是交给模型**：这一项是写进 yaml、再逐拍喂给导演的，
    一条几百字的"高潮"会把每天的提示词撑大，而它本来只是"这一站的顶点"一句话。
    
        English:
    Clip a free-text field to `n` chars (used for the climax).
    """
    s = str(raw or '').strip()
    return s[:n] if n > 0 else s


def _text_list(raw, max_items: int, each: int) -> tuple[str, ...]:
    """把一个字段归一成**短字符串元组**（情节线 / 选项用）。

    认两种写法：模型给数组最常见，但给一串用「；/、/换行」隔开的文本也不少见
    （作者手写 yaml 时更是这样）。条数与每条长度都**在这里封顶** ——
    与 `章数` 同一条规矩：**不做默认值、只做封顶**，空就是空。
    
        English:
    Normalise a field into a **tuple of short strings** (used for beats / options).
    """
    if isinstance(raw, str):
        # ⚠ 分隔符要认全：作者手写最常用的是「A；B」和换行，但「归籍 / 祭献 / 留门」
        #   这种**斜杠**写法同样常见 —— 实测漏了斜杠就把三个结局选项当成了一整条，
        #   作者最后只看到一个选项可选。
        # [EN] ⚠ Cover every separator: authors most often write "A; B" or newlines, but
        # [EN] "return / offer / leave" style **slashes** are just as common -- missing them turned
        # [EN] three ending options into one single string, leaving the author one option to pick.
        raw = [x for x in re.split(r'[；;\n、/｜|]+', raw) if x.strip()]
    if isinstance(raw, dict):                      # {"1": "…"} 这种也认
        raw = list(raw.values())
    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[str] = []
    for x in raw:
        s = str(x or '').strip()
        if not s:
            continue
        out.append(s[:each] if each > 0 else s)
        if len(out) >= max_items:
            break
    return tuple(out)


def min_chapters_for(node) -> int:
    """**这一站至少要演几章**（`>=1`）。

    取值顺序（与 `span` / `weight` 同一套规矩：**作者写的永远优先**）：
      ① 节点上写了 `章数` → 用作者的（超出 `MAX_CHAPTERS` 视为没写，别拿它卡死）；
      ② 没写 → 按这一站的 `篇幅` 档查 `MIN_CHAPTERS`；
      ③ 篇幅也没定 → 按默认档 `中` → 3 章。

    ⚠ 接受 `ProgressNode` / `{'章数':…,'篇幅':…}` / 裸篇幅字符串（三种形状调用方都在用，
      见 `_weight_of_any` 那条"只支持一种形状"的教训）。
    ⚠ 返回值**恒 >= 1**：返回 0 会让"演 0 章就过站"变成可能，那一站等于不存在。

        English:
    **How many chapters this station must run for at minimum** (`>=1`). Order (same rule as
    `span` / `weight`: **what the author wrote always wins**): ① the node's own `章数`
    (beyond `MAX_CHAPTERS` counts as unwritten, so it can never lock the run); ② otherwise
    `MIN_CHAPTERS` by this station's `篇幅` tier; ③ no tier either -> the default `中` -> 3.
    ⚠ Accepts a `ProgressNode`, a `{'章数':…, '篇幅':…}` dict, or a bare length-tier string.
    ⚠ The result is **always >= 1**: returning 0 would allow "advance after zero chapters", which
    makes the station non-existent.
    """
    if isinstance(node, str):
        own, weight = 0, node
    elif isinstance(node, dict):
        own = _parse_chapters(node.get('章数') if '章数' in node
                              else node.get('chapters'))
        weight = str(node.get('篇幅') or node.get('weight') or '')
    else:
        own = _parse_chapters(getattr(node, 'chapters', 0))
        weight = str(getattr(node, 'weight', '') or '')
    if own > 0:
        return own
    if weight in MIN_CHAPTERS:
        return MIN_CHAPTERS[weight]
    return MIN_CHAPTERS[DEFAULT_WEIGHT]


def beat_budget(node: "ProgressNode | None") -> tuple[int, int]:
    """**这一站该分几拍**（`(下限, 上限)`）。取不到节点就给 `中` 的区间。

    ⚠ 接受 `ProgressNode` / `{'篇幅': …}` / 裸字符串（见 `_weight_of_any` 的说明 ——
      只支持一种形状曾经让篇幅档**对拍数完全失效**）。
    [EN] **How many beats this station gets** `(min, max)`; the `中` band when unavailable.
    [EN] ⚠ Accepts a `ProgressNode` / `{'篇幅': …}` / a bare string (see `_weight_of_any` --
    [EN] supporting only one shape once made the length tier **completely ineffective**).
    """
    w = _weight_of_any(node)
    return BEAT_BUDGET.get(w) or BEAT_BUDGET[DEFAULT_WEIGHT]


def span_minutes(node_or_span) -> int:
    """这一站吃掉多少**故事分钟**（`跨度` 档；认不出就给 `当日`）。

    接受 `ProgressNode` / `{'跨度': …}` / 裸字符串 —— 三种形状调用方都在用。
    [EN] How many **story minutes** this station eats (from the span tier; unrecognised falls back
    [EN] to `当日`). Accepts a `ProgressNode`, a `{'跨度': …}` dict, or a bare string.
    """
    if isinstance(node_or_span, str):
        raw = node_or_span
    elif isinstance(node_or_span, dict):
        raw = str(node_or_span.get('跨度') or node_or_span.get('span') or '')
    else:
        raw = str(getattr(node_or_span, 'span', '') or '')
    return SPAN_MINUTES.get(raw) or SPAN_MINUTES[DEFAULT_SPAN]


def beat_minutes(span, weight: str, beats: int = 0) -> int:
    """**一拍推多少故事分钟** = 这一站的故事时长 ÷ 这一站的拍数。

    ★★★ 2026-10-26：这一个式子就是"详略 + 跨度"两维**同时**落到时钟上的地方。
      · 跨度决定"这一段占多少故事时间"（一场 2 小时 / 数月 90 天）；
      · 篇幅决定"这一段写多少拍"（详 50 / 带过 1）；
      · 相除 ⇒ 每拍推多久。于是 `一场+详` 一拍 2.4 分钟（像真在演），
        `数月+带过` 一拍 90 天（一句话带过）—— 两者都是同一套代码。
    ⚠ `beats` 传 0 时按那一档的**上限**算（预算还没定下来时也能给出数）。
    ⚠ 结果夹在 `[BEAT_MIN_MINUTES, BEAT_MAX_MINUTES]` —— 上限是"一拍"这个概念本身的
      边界（见那两个常量的说明），超出它的时间由**站末跳**处理，不是拍的事。
    [EN] **How many story minutes one beat advances** = the station's story duration / its beat
    [EN] count. ★★★ This single expression is where "thickness" and "span" both reach the clock:
    [EN] the span says how much story time the stretch occupies, the length tier says how many
    [EN] beats it is written in, and the quotient is the per-beat duration. So `one scene + full`
    [EN] gives 2.4 minutes per beat (it feels performed) and `months + in passing` gives 30 minutes
    [EN] (the rest is a jump at the station's end). ⚠ `beats=0` uses the tier's ceiling. ⚠ Clamped to
    [EN] `[BEAT_MIN_MINUTES, BEAT_MAX_MINUTES]` -- the ceiling is the bound of the *concept* "one
    [EN] beat", and anything beyond it is handled by the end-of-station jump, not by a beat.
    """
    w = str(weight or '')
    if w not in BEAT_BUDGET:
        w = DEFAULT_WEIGHT
    n = int(beats or 0) or BEAT_BUDGET[w][1]
    n = max(1, n)
    mins = span_minutes(span) / n
    return max(BEAT_MIN_MINUTES, min(BEAT_MAX_MINUTES, int(round(mins))))


@dataclass
class ProgressNode:
    id: str
    name: str
    summary: str
    criteria: str
    status: str = "未开始"   # 未开始 / 进行中 / 已完成 / 已偏离
    chapter: str = ""        # 对齐到的章节
    #: 跨度档（`SPANS` 之一）。空 = 没定，由 `infer_span` 推。
    # [EN] Span tier (one of `SPANS`). Empty = undecided, filled by `infer_span`.
    span: str = ''
    #: 篇幅档（`WEIGHTS` 之一）。空 = 没定，由 `infer_weight` 推。
    # [EN] Length tier (one of `WEIGHTS`). Empty = undecided, filled by `infer_weight`.
    weight: str = ''
    #: **这一站至少演几章**（作者写的；`0` = 没写，由 `min_chapters_for` 按篇幅档兜底）。
    #:
    #: ★★★ 2026-10-27（用户要的"每个地方至少有若干章节"）：
    #:   `篇幅` 管的是**一天写多厚**（拍预算），`章数` 管的是**这一站占几章** ——
    #:   两件事不同：同一件事可以演三天（详 × 3 章），也可以一天演完（略 × 1 章）。
    #: ⚠ 不在这里给默认值：给了就分不清"作者要 3 章"和"程序兜底 3 章"。
    # [EN] **Minimum chapters for this station** (author-written; `0` = not written, and
    # [EN] `min_chapters_for` falls back by length tier). ★★★ 2026-10-27 (the user's "each place
    # [EN] should have at least a few chapters"): `篇幅` is **how thick a single day is** (the beat
    # [EN] budget) while `章数` is **how many chapters this station occupies** -- different things:
    # [EN] one event may run three days (thick x 3 chapters) or finish in one (brief x 1).
    # [EN] ⚠ No default here: a default would erase "the author asked for 3" vs "we fell back to 3".
    chapters: int = 0
    #: **这一站的高潮**（≤150 字）：这一站**最该发生的那一下**。
    #:
    #: ★★★ 2026-10-27（作者写了、程序却读不到的一层）：`完成判据` 只说了**终点线**，
    #:   没说这一站**从哪儿走到哪儿**。于是一站要演 5 章时，导演每天只能拿 80 字概要现编
    #:   —— 结果就是"演够了天数，但每天在原地打转"，而章数硬闸**只保证天数、不保证推进**。
    #:   高潮是"这一站不许提前演到的那一下"：先铺垫，最后才到它。
    #: [EN] **This station's climax** (<=150 chars): the one beat the station is building toward.
    #: [EN] ★★★ 2026-10-27 (a layer the author wrote and the program never read): `criteria` states
    #: [EN] only the **finish line**, not the path. So when a station must run five chapters, the
    #: [EN] director can only improvise from an 80-char summary each day -- "enough days, no progress".
    #: [EN] The climax is "the beat this station must not reach early": lay the ground, arrive last.
    climax: str = ''
    #: **这一站内部的台阶**（情节单元，2~6 条，每条 ≤80 字）。
    #:
    #: 与 `climax` 配对用：高潮是顶点，情节线是**到顶点之前要走过的几件事**。
    #: ⚠ 它是**参考**不是清单：推演按判据走，不按清单打勾（把推演变成"逐条执行"
    #:   就与产品定位冲突了）—— 它的作用是让导演知道"这一站还剩哪些事没演过"。
    # [EN] **The steps inside this station** (plot units, 2-6 items, each <=80 chars). Paired with
    # [EN] `climax`: the climax is the peak, the beat list is what must happen *before* it.
    # [EN] ⚠ It is a **reference, not a checklist**: the run is driven by criteria, not by ticking
    # [EN] boxes (turning it into item-by-item execution would clash with the product's purpose) --
    # [EN] its job is to tell the director "what in this station has not been played yet".
    beats: tuple[str, ...] = ()
    #: **最后一站的选择**（结局选项，如 `归籍 / 祭献 / 留门`）。
    #:
    #: 只在**故事停在一个选择上**时才填（多半是最后一站）。这一站的事了结之后，
    #: 程序把它们交给作者选 —— 复用现有的分支通道，不新开一套机制。
    #: ⚠ 空元组 = 这一站没有选择，照常推进到下一站（或收束）。
    # [EN] **The choice at the final station** (ending options, e.g. `return / offer / leave the door`).
    # [EN] Filled only when **the story stops on a choice** (usually the last station). After that
    #: station's business is settled the program hands them to the author -- reusing the existing
    # [EN] branch channel rather than inventing a new mechanism. Empty tuple = no choice here.
    options: tuple[str, ...] = ()
    #: **这一站的章纲**（章一级施工图，原文片段）。
    #:
    #: ★ 它按站切好存在节点上，**推演时只喂当前站那几章**（不是整本 32 章）。
    #: ⚠ **只当参考，不当清单**：推演按判据走，不按章打勾 —— 把 32 章硬塞进去
    #:   逐条执行，就把"推演引擎"变成了"清单执行器"，那是产品定位的反面。
    #:   它的用处是让导演知道"这一站还剩哪几章的事没演过"。
    # [EN] **This station's chapter plan** (chapter-level blueprint, a verbatim slice). ★ Stored on the
    # [EN] node per station; **only the current station's chapters are fed to the run** (not all 32).
    # [EN] ⚠ **Reference, not checklist**: the run follows criteria, not chapters -- forcing 32
    # [EN] chapters item by item would turn a "simulation engine" into a "checklist runner", the
    # [EN] opposite of this product. Its use is telling the director which chapters of this station
    # [EN] have not been played yet.
    chapter_plan: str = ''
    #: **哪几维是推出来的**（`'span'` / `'weight'`）。
    #:
    #: ⚠ 必须照实记：与 `actors/casting.py` 的 `age_guessed` 同一口径 ——
    #:   "标注了是推的"作者才知道该去补；不标就会被当成他写的设定。
    # [EN] **Which dimensions were inferred** (`'span'` / `'weight'`). Must be recorded faithfully,
    # [EN] same rule as `age_guessed` in `actors/casting.py`: only a visible "inferred" mark tells
    # [EN] the author what to go and fill in.
    inferred: tuple[str, ...] = ()
    # [EN] Not started / In progress / Completed / Deviated
    # [EN] Aligned chapter

    def to_dict(self) -> dict:
        d = {"id": self.id, "名称": self.name, "概要": self.summary,
             "完成判据": self.criteria, "状态": self.status}
        # ★ 只在**有值**时才写这两个键：老项目的 yaml 里没有它们，
        #   新写的文件也不该因为"默认值"而显得作者填过。
        # [EN] Only emit these two keys when they carry a value: old projects lack them, and a fresh
        # [EN] file must not look as if the author filled in a default.
        if self.span:
            d["跨度"] = self.span
        if self.weight:
            d["篇幅"] = self.weight
        # ★ 章数**也一样**：只写作者真填过的。
        #   ⚠ 不写兜底值 —— 兜底由 `min_chapters_for` 按篇幅档现算，
        #     写进文件会让作者以为自己写过（与 `跨度 / 篇幅` 同一条规矩）。
        # [EN] Same for the chapter count: only emit what the author actually filled in. The fallback
        # [EN] is computed live by `min_chapters_for`; persisting it would look author-written.
        if self.chapters:
            d["章数"] = self.chapters
        # ★ 高潮 / 情节线 / 选项：同样**只写有值的**（老项目没有这三个键，
        #   新文件也不该显得作者填过）。
        # [EN] Climax / beats / options: likewise **only when they carry a value**.
        if self.climax:
            d["高潮"] = self.climax
        if self.beats:
            d["情节线"] = list(self.beats)
        if self.options:
            d["选项"] = list(self.options)
        if self.chapter_plan:
            d["章纲"] = self.chapter_plan
        if self.inferred:
            # ⚠ 用作者看得懂的话，不用 `inferred: ('span',)` 这种内部形状。
            # [EN] Phrased for the author, not as an internal `('span',)` tuple.
            names = {'span': '跨度', 'weight': '篇幅'}
            d["推断"] = '、'.join(names.get(x, x) for x in self.inferred) + '（程序推的，可改）'
        return d


# ── 构建进度表 ─────────────────────────────────────────────────────────
# ★ 预算写死，别靠 `llm.chat` 的默认 2000（2026-10-06 的血）：这个数组要装 6~8 个
#   节点，每个节点「概要 30~80 字 + 判据 30~50 字」，中文一算就是 2000+ token；
#   而推理模型还要在里面再花掉一份思考额度 —— 那天真实跑出来**正好 2000**，
#   数组被砍在半句话里。更要命的是当时没有数组抢救（`repair_json` 只认 dict），
#   于是进度表**静默变成 0 个节点**，界面上只看到"进度节点 0 个"。
# [EN] ── Build progress table ─────────────────────────────────────────────────
# [EN] ★ Hardcode the budget, don't rely on `llm.chat`'s default 2000 (the 2026-10-06 lesson): this
# [EN] array has to hold 6~8
# [EN] nodes, each with "summary 30~80 chars + criteria 30~50 chars"; in Chinese that's 2000+ tokens;
# [EN] and a reasoning model also burns a thinking budget inside it -- that day the actual output was
# [EN] **exactly 2000**,
# [EN] and the array got cut off mid-sentence. Worse, there was no array rescue at the time
# [EN] (`repair_json` only handles dict),
# [EN] so the progress table **silently became 0 nodes**, and the UI only showed "0 progress nodes".
# ★ 2026-10-27 从 3000 提到 4500：节点多了「高潮 / 情节线 / 选项」三个字段，
#   8 个节点 × (高潮 50 + 情节线 6×30 + 选项) 实测要多出 1500~2000 token；
#   而 3000 那次的输出已经是 2853 —— 再挤就又是"数组被截断、进度表归零"那个老伤。
#   ⚠ 上限只放**输出**（模型写不写得完），输入那一头由切片压着（见 `slice_stations`）。
# [EN] ★ Raised 3000 -> 4500 on 2026-10-27: nodes gained climax / beats / options, and eight nodes
# [EN] x (climax 50 + beats 6x30 + options) costs 1500~2000 more tokens, while the 3000-token run
# [EN] already produced 2853 -- tightening further would reopen the old "array cut off, progress
# [EN] table zeroed" wound. ⚠ This caps **output** only; input is held down by `slice_stations`.
_PROGRESS_MAX_TOKENS = 4500
_ALIGN_MAX_TOKENS = 3000

_BUILD_PROMPT = """你是一位故事结构专家。下面是一份小说的大纲/剧情参考线。
请把它拆成有序的节点列表（4~8个节点），每个节点代表故事中的一个关键阶段。

每个节点包含：
- 名称：简洁（2~6字）
- 概要：这一节点要发生什么（一段话，30~80字）
- 完成判据：自然语言描述，供 LLM 判定（如「主角得知X的存在」「两人公开对峙」）

★★★ 「完成判据」**能照抄就照抄**（2026-10-27 补，这条很要紧）：
- 大纲里作者写了「完成判据」的，**原样照抄，一个字都不要改**。
- ⚠ 为什么：判据是硬门槛，一改写就常冒出并列词（"…之后，…""…并…"），
  程序会把它们当成**两件事**拆成两站 —— 实测作者写 8 站、模型改写后落盘 10 站，
  32 章变 40 章。作者的判据本来就只有一件事，照抄最安全。
- 大纲没写判据的，才由你按下面的规矩写一条。

★★★ 「完成判据」**只能写一件事**（这是硬要求，2026-10-21 补）：
- 判定端读判据的规矩是「**串了几件事就必须全部做到**才算完成」——
  一站捆两件事，就等于"两件都做完才推进"，故事会**长期卡在这一站**；
- 所以：**一件事一个节点**。如果一段剧情里确实有几件事先后发生，
  就把它拆成**几个连续的节点**（各占一个编号），而不是塞进同一个判据；
- 判据里**不要出现并列**（顿号、分号、逗号连接的多件事）：出现并列就说明该拆站了；
- 判据要写得**可判定**：能对着最近发生的事回答"做到/没做到"。
  不要写"气氛紧张""关系微妙"这种状态描述 —— 它们永远判不了，等于永远推不动。

★ 长度与条数是硬要求（输出很长，很容易写超）：
- **节点数严格控制在 4~8 个之间**（写不下就合并，不要切成十几段）；
- 「名称」**不超过 6 个字**；「概要」**不超过 80 个字**；「完成判据」**不超过 50 个字**；
- **只输出 JSON 数组本身**：第一个字符是 `[`、最后一个字符是 `]`，
  不要开场白、不要结语、不要用 ```json 代码块包起来。

★★★ 「跨度」与「篇幅」——**小说的时间不是匀速的，这两项就是在说这件事**：
- 「跨度」只许从这五个词里选**一个**：`一场` / `当日` / `数日` / `一旬` / `数月`
  它表示**这一站覆盖多久的故事时间**。例如：
  · 一场对峙、一次夜谈 → `一场`
  · 在同一天里从早忙到晚 → `当日`
  · 办一件事花了两三天、或从一城到另一城 → `数日`
  · 十天上下、或跨了几个城镇 → `一旬`
  · 隔了几个月、换季、经年累月 → `数月`
- 「篇幅」只许从这四个词里选**一个**：`详` / `中` / `略` / `带过`
  它表示**这一站该写多厚**：
  · `详` = 一场戏细写到底（关键转折、摊牌、对决、真相揭开）
  · `中` = 有场景有对话，但不必每句都写（多数节点是这一档）
  · `略` = 交代清楚发生了什么就够（赶路、打点、传话）
  · `带过` = 一句话带过去（长时间无事、只为了让时间过去）
- ⚠ **不要每一站都给 `详`**：全篇都详等于没有详略，读者会累，而且这一层是
  作者用来控制节奏的，你替他全填 `详` 就等于把节奏抹平了。
- ⚠ 相邻两站的跨度**可以差很多**（`数月` 接 `一场` 是正常的）：这正是小说的样子。

★★★ 「章数」——**这一站要占几章**（2026-10-27 新增，作者要"每个地点至少若干章节"）：
- 只填一个**正整数**（1~20），写 `"3~4"` 也可以（程序取下限 3）。
- 它是"这一站**至少**演几章"，不是"最多"：判据满足了也要演够这个数才过站。
- ⚠ 与「篇幅」是**两件事**：`篇幅` 是一天写多厚，`章数` 是这一站占几天。
  一件事可以写三章（`篇幅:详` + `章数:3`），也可以一章带过（`篇幅:带过` + `章数:1`）。
- ⚠ **不要填原著的章节号**（大纲里"第 5–8 章"那种是原著对照用的，不是要写几章）；
  按"这一站的事要摊开才讲得清，得几章"来填：关键转折 4~6 章、一般 3~4 章、
  过场 1~2 章。
- 作者没写时程序会按篇幅档兜底（`详`4 / `中`3 / `略`2 / `带过`1）——
  **你不填也不会出错**，填了才是作者自己定的节奏。

★★★ 「高潮」与「情节线」——**这一站内部的台阶**（2026-10-27 新增）：
- 「高潮」：这一站**最该发生的那一下**（一句话，≤50 字）。它是这一站的顶点，
  推演时会被当成"**不许提前演到的东西**"—— 先铺垫，最后才到这一下。
- 「情节线」：到顶点之前要按顺序走过的 **2~6 件具体的事**，每条 ≤30 字
  （写"发生了一件什么具体的事"，不要写"气氛变了""关系变好"这种状态）。
- ⚠ **大纲里作者写了「高潮」「情节线」就照抄**，不要改写、不要归纳；
  大纲没写就凭「概要」自己拆。
- ⚠ **不要把后几站的谜底写进前几站的高潮**：还没走到那一站，提前写就是剧透。

★★★ 「选项」——**只在故事停在一个选择上时才填**（多半是最后一站）：
- 填一个短词数组，例如 ["归籍", "祭献", "留门"]。这一站的事了结之后，
  程序会把它们交给作者选 —— 作者不选，故事就停在那个选择上。
- ⚠ 不是最后一站、或故事没有"停在一个选择上"，**就不要填**（给空数组或不给这个键）。
  给错了会让每一站都弹出选择，推演就没法自己往前走了。

请以 JSON 数组回答：
[
  {"名称": "...", "概要": "...", "完成判据": "...", "跨度": "当日", "篇幅": "中", "章数": 3,
   "高潮": "……", "情节线": ["……", "……"], "选项": []},
  ...
]
⚠ 「高潮」「情节线」「选项」三个键**可以整个不写**（老大纲没有这些），写了就按上面的长度封顶。

大纲/剧情参考线：
{outline}
"""
# ★★★ 2026-10-21（用户：「进度表一直不动……」→「按照第一个方向执行（拆判据）」）：
#   上面那段「只能写一件事」是**源头**。为什么非要写在这里：
#   判定口径（`director/engine.py` 的 `_PROGRESS_PROMPT`）明确要求"判据里串了几件事
#   就必须全部做到"，那条是对的（治"第一天就把谜底解开"），但它把"一站捆四件事"变成了
#   **几乎永远做不到**。实测某项目：日志里那一站的判据列了四件事，其中两件早就发生了，
#   只是"多站委托"没走完 ⇒ 进度表永远 0/N、界面上看着像"卡死"。
#   ⇒ 源头让模型一站一件事；模型仍不听话时由 `split_fat_nodes` 兜底拆（`sim/setup.py` 与
#     `build_progress_table` 共用同一份），**不靠提示词自觉**。
#   ⚠ 这里**不写具体书里的例子**：提示词里的例子会被当素材抄（本项目的既有教训）。
# [EN] ★★★ 2026-10-21 (user: "the progress table never moves" -> "take the first direction, split
# [EN] the criteria"): the paragraph above is the **source fix**. Why it belongs here: the evaluation
# [EN] rule (`_PROGRESS_PROMPT` in `director/engine.py`) explicitly demands "if the criterion names
# [EN] several things, all of them must be done". That rule is right (it stops the story racing ahead),
# [EN] but combined with "one station carries four tasks" it makes advancement **practically
# [EN] impossible**. Measured on one project: the station's criterion listed four tasks, two had long
# [EN] since happened, and only the last was open => the table sat at 0/N and looked stuck.
# [EN] => Have the model emit one task per station at the source; when it still doesn't, `split_fat_nodes`
# [EN] catches it (shared by `sim/setup.py` and `build_progress_table`) -- **never rely on the prompt
# [EN] alone**.
# [EN] ⚠ No in-book examples here: examples in a prompt get copied as material (an existing lesson in
# [EN] this project).


_LENGTH_KEYS = {
    '总章数': ('总章数', '全书章数', 'total chapters', 'chapters'),
    '总字数': ('总字数', '目标字数', '全书字数', 'total words', 'target words'),
    '每章字数': ('每章字数', '单章字数', 'words per chapter'),
}


def _to_int(raw: str) -> int:
    """`75000` / `7.5万` / `7万5` → 整数。**认不出给 0**（0 = 没写）。

        English:
    `75000` / `7.5万` / `7万5` -> integer. **0 when unparseable** (0 = not written).
    """
    s = str(raw or '').strip().replace(',', '').replace('，', '')
    if not s:
        return 0
    m = re.search(r'(\d+(?:\.\d+)?)\s*万', s)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r'\d+(?:\.\d+)?', s)
    if not m:
        return 0
    try:
        return int(float(m.group()))
    except ValueError:
        return 0


def parse_length_plan(text: str) -> dict[str, int]:
    """从大纲里读**书级篇幅规划**（`{'总章数':…, '总字数':…, '每章字数':…}`）。

    ★★★ 2026-10-27（用户：「整体故事需要在一定数量的字数……这个可以在设定集里设定吗」）：
    以前"写多少字"只有一个**每天**的软目标 `ROUND_DAILY_WORDS`（且默认 0 = 不限），
    作者在大纲里写"全书 8 万字"**没有任何地方接得住** —— 那句话被当成散文读掉了。

    认这几种写法（作者真的会这么写）：
      · `- 总章数: 32` / `总章数：32`
      · `- 总字数: 75000` / `总字数: 7.5万字` / `全书 8 万字`
      · `- 每章字数: 2400`
      · 英文：`Total chapters: 32` / `Total words: 80,000`

    ⚠ 只在**标题行/列表行**里找（`^\\s*[-*#]?\\s*键`），不在整段正文里正则乱扫 ——
      大纲的散文里出现"三十万字"多半是在形容原著，不是给程序下命令。
    ⚠ **加粗也要认**（`- **总章数**：32`）：作者写大纲时几乎一定会加粗字段名，
      而"写了却读不到"是最难发现的一种静默失效 —— 第一版就栽在这里
      （指南里写的是 `- 总章数: 32`，实际落到盘上的是加粗的那一行）。
    ⚠ 读不到就返回全 0 的字典（**不抛、不猜**）："没写"与"写错了"由调用方按
      `words_per_chapter` 的口径处理。

        English:
    Read the **book-level length plan** out of the outline
    (`{'总章数':…, '总字数':…, '每章字数':…}`). ★★★ 2026-10-27 (user: "the whole story needs a
    certain word count ... can I set that in the setting collection?"): "how many words" only had a
    **per-day** soft target (`ROUND_DAILY_WORDS`, default 0 = unlimited), so an author writing
    "80,000 words for the whole book" in the outline had **nowhere to land** -- read as prose.
    Accepts `总章数: 32`, `总字数: 7.5万字`, `每章字数: 2400`, and the English forms.
    ⚠ Only matches **heading / list lines**, never free prose: "three hundred thousand characters"
    in the body is usually describing a source novel, not instructing the program.
    ⚠ Returns an all-zero dict when nothing is found (**no raise, no guessing**).
    """
    out = {'总章数': 0, '总字数': 0, '每章字数': 0}
    for line in str(text or '').splitlines():
        s = line.strip().lstrip('-#*>').strip()
        # `**字段**` 这种加粗写法：先把开头的 `**` 摘掉，否则"键"永远匹配不上。
        # [EN] Bold field names: strip the leading `**` first, or the key can never match.
        while s.startswith('**'):
            s = s[2:].strip()
        if not s:
            continue
        low = s.lower()
        for key, aliases in _LENGTH_KEYS.items():
            if out[key]:
                continue
            for a in aliases:
                if low.startswith(a.lower()):
                    rest = s[len(a):].lstrip('：: ＝= \t*').strip()
                    n = _to_int(rest)
                    if n > 0:
                        out[key] = n
                    break
    return out


def words_per_chapter(plan: dict | None) -> int:
    """这一本**每章该写多少字**（0 = 不限）。

    取值顺序：① 作者写了 `每章字数` → 直接用；② 写了 `总字数` 与 `总章数` → 相除；
    ③ 都没有 → `0`（**0 = 不限**，沿用 `ROUND_DAILY_WORDS` 的老规矩，绝不猜一个数）。

    ⚠ 相除时**向下取整并保底 300**：一章 300 字以下就不是一章，是段笔记。
    [EN] **Words per chapter** for this book (0 = unlimited). ① the author's `每章字数`;
    ② `总字数` / `总章数`; ③ neither -> `0` (0 = unlimited, the old `ROUND_DAILY_WORDS` rule --
    never invent a number). ⚠ Division floors at 300: below that it is a note, not a chapter.
    """
    p = plan if isinstance(plan, dict) else {}
    own = int(p.get('每章字数') or 0)
    if own > 0:
        return own
    total = int(p.get('总字数') or 0)
    chapters = int(p.get('总章数') or 0)
    if total > 0 and chapters > 0:
        return max(300, total // chapters)
    return 0


# ── 站表切片 ───────────────────────────────────────────────────────────
# ★★★ 2026-10-27：建节点**不能再拿"大纲前 4000 字"当输入**。
#   事故现场（一次真实项目实测）：大纲 + 章纲 13,581 字，前 4000 字正好卡在第 4 站中间 ——
#   第 5~8 站的**完成判据与章数一个字都没进提示词**，模型只能凭"承"段和那句章序表
#   反推：章数碰巧蒙对（5/3/5/4），判据全是编的 —— 第 6 站跨度「数月」被写成「数日」、
#   第 8 站判据从「主角在庭上做出选择」变成「掌柜把话讲全」（**结局三选一整个没了**），
#   第 7 站判据串了两件事又被拆成两站 ⇒ **作者写 8 站 32 章，落盘 9 站 35 章**。
#   那不是"少看了一点"，是**后半本书被换掉了**，而且全程无提示。
# [EN] ★★★ 2026-10-27: building nodes **must stop using "the first 4000 chars of the outline"**.
# [EN] The incident (measured on a real project): outline + chapter plan = 13,581 chars, and the first
# [EN] 4000 cut off right in the middle of station 4 -- **not one criterion or chapter count from
# [EN] stations 5-8 reached the prompt**, so the model reconstructed them from the "carrying" section
# [EN] and the chapter-order line: the counts happened to match (5/3/5/4) but every criterion was
# [EN] invented -- station 6's span "months" became "days", station 8's criterion changed from "Chen
# [EN] Wang makes a choice in court" to "the keeper finally says it all" (**the three ending options
# [EN] vanished**), and station 7's two-task criterion got split into two stations => **the author's
# [EN] 8 stations / 32 chapters landed as 9 stations / 35 chapters**.
# [EN] That is not "seeing a bit less", it is **the back half of the book being replaced**, silently.

#: 站标题：`### 第 1 站 · 白日入门（第 1 章）` / `## Station 1 · ...`
_STATION_HEAD_RE = re.compile(
    r'^#{2,4}\s*(?:第\s*(\d+)\s*站|Station\s*(\d+))[^\n]*$',
    re.IGNORECASE | re.MULTILINE)

#: 站块里的字段行。⚠ **中英文键名都要认**：英文大纲写的是
#: `- **Span**: one scene` / `- **Done when**: …` / `- **Climax**: …`，
#: 只认中文键的话英文项目会**一条字段都匹配不上 ⇒ 切出 0 站 ⇒ 静默回退**，
#: 而这个回退正是中文这侧刚出过的事故（后半本书被换掉、全程无提示）。
# [EN] Field lines inside a station block. ⚠ **Both Chinese and English keys must be accepted**:
# [EN] English outlines write `- **Span**: one scene` / `- **Done when**: ...` / `- **Climax**: ...`
# [EN] -- accepting only Chinese keys means an English project **matches no field at all => zero
# [EN] stations sliced => silent fallback**, which is exactly the accident that just happened on the
# [EN] Chinese side (the back half of the book replaced, with no warning anywhere).
_FIELD_KEYS = (
    '跨度', '篇幅', '章数', '完成判据', '高潮', '情节线', '选项', '概要',
    'Done when', 'Span', 'Length', 'Chapters', 'Summary', 'Climax', 'Beats',
    'Options', 'Criteria',
)
#: ⚠ 括号是**可选**的（"- **情节线**（3 个单元）："有，"- **跨度**：当日"没有）——
#:   写成必需就成了"字段行一条都匹配不上、切出来 0 站"，而这正好会静默回退，最难发现。
# [EN] Field lines inside a station block. ⚠ The parentheses are **optional** ("- **beats** (3 units):"
# [EN] has them, "- **span**: same day" does not) -- making them mandatory yields "not one field
# [EN] line matches, zero stations sliced", which silently falls back. Hardest kind to notice.
#: ⚠ 两处都不能用 `\s`（它含 `\n`，会**跨行**）：
#:   · 行首空白必须是 `[ \t]`，否则 `^` 之后能一路吃到上一行的换行；
#:   · 「：」之后的空白同理 —— 写成 `\s*` 时，"- **情节线**：" 会把**下一行第一条单元**
#:     当成自己的值（实测：情节线第一条就这样被吃掉，切出来只剩 2 条）。
# [EN] ⚠ Neither spot may use `\s` (it contains `\n`, so it **crosses lines**): the leading space
# [EN] must be `[ \t]`, and likewise the space after the colon -- with `\s*`, "- **beats**:" swallows
# [EN] **the next line's first beat** as its own value (measured: the first beat was eaten and only
# [EN] two survived).
_STATION_FIELD_RE = re.compile(
    r'^[ \t]*[-*]?[ \t]*\**\s*(' + '|'.join(_FIELD_KEYS) + r')\s*\**\s*'
    r'(?:（[^）]*）|\([^)]*\))?\s*[：:][ \t]*([^\r\n]*)',
    re.MULTILINE | re.IGNORECASE)

#: 跨度 / 篇幅的**英文值 → 档位**（英文大纲写 `one scene` / `normal` / `in passing`…）。
#: ⚠ 这两个表是**闭集**：档位一共就五个 / 四个，认不出时**原样保留**（不猜），
#:   交给 `resolve_span_weight` 去推断并标注"这是推的"。
# [EN] English span/length **values -> tiers**. ⚠ Both tables are **closed sets**: there are only
# [EN] five / four tiers, and anything unrecognised is **kept as-is** (never guessed) for
# [EN] `resolve_span_weight` to infer and mark as "inferred".
_SPAN_EN = {'one scene': '一场', 'the same day': '当日', 'three days': '数日',
            'a fortnight': '一旬', 'six months': '数月'}
_LENGTH_EN = {'full': '详', 'normal': '中', 'brief': '略', 'in passing': '带过'}

#: 英文键名 → 中文键名（`Done when` → `完成判据`、`Span` → `跨度`…）。
#: ⚠ 不做这一层归一，下面的"至少有一个站字段"过滤会因为键名不同把英文站全滤掉。
# [EN] English key -> Chinese key. ⚠ Without this, the "at least one station field" filter below
# [EN] drops every English station because the keys don't match.
_FIELD_ALIASES = {
    'span': '跨度', 'length': '篇幅', 'chapters': '章数',
    'done when': '完成判据', 'criteria': '完成判据',
    'climax': '高潮', 'beats': '情节线', 'options': '选项',
    'summary': '概要',
}

#: 情节线下面的编号单元：`  1. 醒在台阶下：…`
_BEAT_ITEM_RE = re.compile(r'^\s*\d+\s*[.、)）]\s*(.+?)\s*$', re.MULTILINE)

#: 切片总长上限。八站 × (标题 + 六字段 + 3~6 个情节单元) 实测约 2500~4000 字，
#: 留一倍余量给"作者写得比这细"的项目。
# [EN] Slice size cap. Eight stations x (title + six fields + 3-6 beats) measures 2500-4000 chars;
# [EN] the headroom is for projects whose author writes in more detail.
SLICE_MAX_CHARS = 8000

#: 切片失败时的老口径（回退，不是新行为）。
# [EN] The old figure, used as the fallback (not new behaviour).
OUTLINE_HEAD_CHARS = 4000


def _with_continuation(body: str, pos: int, cur: str, limit: int) -> str:
    """把字段行的**缩进续行**拼回来（`概要` 最常写成好几行）。

    ⚠ 遇到空行 / 下一个 `-` 字段 / 编号单元就停 —— 否则会把"情绪""可笑处"那些行
    也拼进概要里，切片就又变成一锅粥了。
    
        English:
    Re-attach a field line's **indented continuation lines** (`summary` is usually written over
    several lines). ⚠ Stop at a blank line / the next `-` field / a numbered beat, otherwise the
    "mood" and "joke" lines get folded into the summary and the slice turns into soup again.
    """
    out = cur
    lines = body[pos:].splitlines()[1:]
    for line in lines:
        s = line.rstrip('\r')
        if not s.strip():
            break
        if not s[:1].isspace():
            break
        if s.lstrip().startswith(('-', '*')) or _BEAT_ITEM_RE.match(s):
            break
        # ⚠ 英文换行处是**词间断**，拼回去要补一个空格（实测 "ahead" + "of" → "aheadof"）；
        #   中文没有词边界，不能补。
        # [EN] ⚠ An English line break falls **between words**, so re-joining needs a space
        # [EN] (measured: "ahead" + "of" -> "aheadof"); Chinese has no word boundary, so none.
        piece = s.strip()
        if out and piece and out[-1].isascii() and out[-1].isalnum() \
                and piece[0].isascii() and piece[0].isalnum():
            out += ' '
        out += piece
        if len(out) >= limit:
            break
    return out


def _station_blocks(text: str) -> list[tuple[str, dict, list[str]]]:
    """从大纲里切出**站块**：`(标题行, 字段dict, 情节单元list)`。

    两条过滤（都是为了防止"把不是站表的东西当站表"）：
      · 一个块**至少要有一个站字段**（完成判据/跨度/篇幅/章数）—— 章纲.md 里
        `## 第 1 站` 那些块只有"推进/情节/高潮/钩子"，没有判据 ⇒ **不会被当成站**；
      · **同一站号只取第一次出现**（章纲与大纲站号重合时的第二道保险）。
    
        English:
    Slice **station blocks** out of an outline: `(title line, field dict, beat list)`. Two filters
    (both guard against mistaking something else for the station table): a block must carry **at
    least one station field** (criteria/span/weight/chapters) -- chapter-plan blocks only have
    "advance/beat/climax/hook" and so are **not** treated as stations; and **a station number is
    taken on first appearance only** (second guard when a chapter plan reuses the same numbers).
    """
    heads = list(_STATION_HEAD_RE.finditer(text or ''))
    if not heads:
        return []
    out: list[tuple[str, dict, list[str]]] = []
    seen: set[str] = set()
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end():end]
        num = str(m.group(1) or m.group(2) or '')
        if num in seen:
            continue
        fields: dict[str, str] = {}
        beats: list[str] = []
        for fm in _STATION_FIELD_RE.finditer(body):
            key = _FIELD_ALIASES.get(fm.group(1).lower(), fm.group(1))
            val = (fm.group(2) or '').strip()
            if key == '情节线':
                # 单元可能写在同一行（"1. … 2. …"），也可能换行写
                # [EN] Beats may sit on one line or on their own lines
                sub = body[fm.end():]
                opts = [x.strip() for x in _BEAT_ITEM_RE.findall(sub)]
                if not opts and val:
                    opts = [x.strip() for x in re.split(r'[；;]', val) if x.strip()]
                beats = [b[:BEATS_EACH_CHARS] for b in opts[:BEATS_MAX_ITEMS]]
            elif val:
                # 概要 / 完成判据 / 高潮都可能换行写 ⇒ 把缩进续行拼回来
                # [EN] Summary / criterion / climax may wrap => re-attach indented continuations
                val = _with_continuation(body, fm.end(), val, 200)
                # ★ 跨度 / 篇幅的**英文值归一成档位**（英文大纲写 `one scene` / `normal`）。
                #   ⚠ 不归一的话模型要自己把英文翻成 `一场` / `中` —— 而档位是**闭集**，
                #   让它自由翻译就有可能翻出一个不存在的档，后面所有按档取值的逻辑
                #   （拍预算、章数兜底）会一起失灵。
                # [EN] ★ Normalise English span/length values to the tier (English outlines write
                # [EN] `one scene` / `normal`). ⚠ Without it the model translates into `一场` / `中`
                # [EN] itself -- and tiers are a **closed set**, so free translation can produce a
                # [EN] tier that does not exist, breaking everything keyed on it (beat budget,
                # [EN] chapter fallback).
                low = val.strip().lower()
                if key == '跨度':
                    val = _SPAN_EN.get(low, val)
                elif key == '篇幅':
                    val = _LENGTH_EN.get(low, val)
                fields[key] = val
        if not any(fields.get(k) for k in ('完成判据', '跨度', '篇幅', '章数')):
            continue
        seen.add(num)
        out.append((m.group(0).strip('# ').strip(), fields, beats))
    return out


def slice_stations(text: str, *, max_chars: int = SLICE_MAX_CHARS) -> tuple[str, int]:
    """把大纲压成**只含站表**的短文本：`(文本, 站数)`。站数为 0 = 没切出站（调用方回退）。

    ★ 为什么是"压"而不是"把窗口放大"：放大窗口既费钱又会把散文（情绪、可笑处、
    原著章号、章纲的 32 章）一起塞进去，那些东西**对建节点有害** —— 模型会照着
    "第 5–8 章"填章数、照着章纲把站拆碎。压成站表之后八站只要 2500~4000 字，
    **比原来的 4000 字还便宜，而且后半本书真的在里面**。

    ⚠ 装不下时按"从最不要紧的砍起"：情节线 → 概要 → 保留标题与判据（那两样丢了
    就等于没站表）。
    
        English:
    Compress an outline into **only the station table**: `(text, station count)`. A count of 0 means
    nothing was sliced (the caller falls back). ★ Why compress instead of enlarging the window:
    enlarging costs more and drags in prose (mood, jokes, source-novel chapter numbers, the 32
    chapters of the chapter plan) that is **harmful** here -- the model copies "chapters 5-8" into
    the chapter count and shreds stations following the chapter plan. Compressed, eight stations
    need 2500-4000 chars: **cheaper than the old 4000, with the back half of the book actually
    inside**. ⚠ When it still doesn't fit, cut from the least important up: beats -> summary ->
    always keep the title and the criterion (losing those means having no station table at all).
    """
    blocks = _station_blocks(text)
    if not blocks:
        return '', 0

    def _render(keep_beats: int, keep_summary: bool) -> str:
        lines: list[str] = []
        for title, fields, beats in blocks:
            head = [f'{fields[k]}' for k in ('跨度', '篇幅', '章数')
                    if fields.get(k)]
            lines.append(f'### {title}')
            if head:
                lines.append(f"- 跨度/篇幅/章数：{' / '.join(head)}"
                             if len(head) == 3 else
                             '- ' + '、'.join(f'{k}：{fields[k]}'
                                              for k in ('跨度', '篇幅', '章数')
                                              if fields.get(k)))
            if fields.get('完成判据'):
                lines.append(f"- 完成判据：{fields['完成判据']}")
            if fields.get('高潮'):
                lines.append(f"- 高潮：{fields['高潮']}")
            if fields.get('选项'):
                lines.append(f"- 选项：{fields['选项']}")
            if keep_summary and fields.get('概要'):
                lines.append(f"- 概要：{fields['概要']}")
            if keep_beats and beats:
                lines.append('- 情节线：' + ' '.join(
                    f'{i}. {b}' for i, b in enumerate(beats[:keep_beats], 1)))
            lines.append('')
        return '\n'.join(lines).strip()

    for keep_beats, keep_summary in ((BEATS_MAX_ITEMS, True), (3, True),
                                     (3, False), (0, False)):
        out = _render(keep_beats, keep_summary)
        if len(out) <= max_chars:
            return out, len(blocks)
    return _render(0, False)[:max_chars], len(blocks)


#: 章纲文件的**文件名特征**（`章纲.md` / `chapter outline.md` / `chapter plan.md`）。
#:
#: ⚠ 只认文件名、不认内容：章纲与大纲都是"大纲"类，靠内容区分会误判
#: （大纲里也写着"第 N 站"）。认不出来就**没有章纲**，推演行为与以前一致。
# [EN] **Filename markers** of a chapter plan. ⚠ Match on the filename, not the content: a chapter
# [EN] plan and an outline are both "outline" category files, and content-based detection misfires
# [EN] (the outline also says "station N"). Unrecognised simply means **no chapter plan**, and the
# [EN] run behaves exactly as before.
CHAPTER_PLAN_NAMES = ('章纲', 'chapter plan', 'chapter outline', 'chapter-plan')

#: 一站的章纲最多带多少字。
#:   ★★★ 2026-10-27：1000 → **1800**。原来按"5 章 × 每章 4 行 ≈ 750 字"定的，
#:   而一个"小案"体量的站本来就是 **7 章**（实测某部真实作品最长一站 1484 字）——
#:   按 1000 截，**后两章整段消失，而且截在第五章的半句话上**，全程没有任何提示。
#:   症状长得像"章纲没写完"，其实是**作者的章纲被砍了**。
# [EN] How many chars of chapter plan one station may carry. ★★★ 2026-10-27: 1000 -> **1800**.
# [EN] It was sized for "5 chapters x 4 lines", but a station of "small case" size is **7 chapters**
# [EN] (measured: the longest one is 1484 chars). At 1000 the last two chapters vanish entirely and
# [EN] the cut lands mid-sentence, with no warning at all.
CHAPTER_PLAN_MAX_CHARS = 1800


def is_chapter_plan(name: str) -> bool:
    """这个文件是不是**章纲**（章一级施工图），而不是站表。"""
    # ⚠ `-` / `_` 当空格看：作者会写 `chapter-outline.md`、`chapter_plan.md`，
    #   只认空格的话英文项目**一份章纲都认不出来**（而症状是"章纲没生效"，
    #   看不出是文件名写法的问题）。
    # [EN] ⚠ Treat `-` / `_` as spaces: authors write `chapter-outline.md`, `chapter_plan.md`, and
    # [EN] matching only spaces means an English project has **no chapter plan recognised at all**
    # [EN] (and the symptom reads as "the plan didn't work", not as a filename issue).
    low = str(name or '').lower().replace('-', ' ').replace('_', ' ')
    return any(k in low for k in CHAPTER_PLAN_NAMES)


def slice_chapter_plan(text: str, *,
                       per_station: int = CHAPTER_PLAN_MAX_CHARS
                       ) -> list[tuple[str, str]]:
    """把章纲按站切开：`[(站标题, 该站的章节文本)]`。

    ⚠ 与 `slice_stations` 用**同一套站标题**来切，但不做字段过滤 —— 章纲里本来
    就没有"完成判据"，一过滤就全没了。
    
        English:
    Split a chapter plan by station: `[(station title, that station's chapter text)]`.
    ⚠ Uses the **same station headings** as `slice_stations`, but without the field filter -- a
    chapter plan has no "done when" field, so filtering would drop everything.
    """
    heads = list(_STATION_HEAD_RE.finditer(text or ''))
    if not heads:
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        num = str(m.group(1) or m.group(2) or '')
        if num in seen:
            continue
        seen.add(num)
        body = '\n'.join(x.rstrip('\r') for x in
                         text[m.end():end].splitlines()).strip()
        if not body:
            continue
        title = m.group(0).strip('# ').strip()
        out.append((title, _clip_chapter_plan(body, per_station, title)))
    return out


def _clip_chapter_plan(body: str, limit: int, title: str = '') -> str:
    """超出每站上限时**按整章边界**截，绝不截在半句话上。

    ★★★ 2026-10-27：原来是 `body[:limit]` —— 截出来的最后一章是**半句话**，
      而模型会照着那句半截的话演；更糟的是**没有任何提示**，作者以为 7 章都进去了。
      现在退到最后一个 `**第 N 章` 之前，并把"丢了几章"写进日志。
    [EN] Clip on a **chapter boundary**, never mid-sentence; log how many chapters were dropped.
    """
    if limit <= 0 or len(body) <= limit:
        return body
    cut = body[:limit]
    i = cut.rfind('**第 ')
    kept = (cut[:i] if i > 0 else cut).rstrip()
    lost = body.count('**第 ') - kept.count('**第 ')
    try:
        from logger import get_logger
        get_logger('nws.ingest').warning(
            '章纲「%s」超出每站上限 %d 字（实际 %d 字），按整章边界截断，丢了 %d 章',
            title, limit, len(body), max(0, lost))
    except Exception:                                    # noqa: BLE001
        pass
    return kept


def _station_name_of(title: str) -> str:
    """从 `第 1 站 · 白日入门（第 1 章）` / `Station 1 · The early drum` 取出站名。"""
    s = re.sub(r'^第\s*\d+\s*站', '', str(title or '')).strip()
    s = re.sub(r'^Station\s*\d+', '', s, flags=re.IGNORECASE).strip()
    s = s.lstrip('·・:：-— ').strip()
    return re.split(r'[（(]', s)[0].strip()


def match_station(name: str, blocks) -> tuple | None:
    """按**站名双向包含**匹配一个节点与一个站块。

    ⚠ 为什么是双向：模型会把站名改写（作者写「府城」，它写「**府城数地**」；
    作者写「重审」，它写「**庭上重审**」），单向包含只能命中一半。
    ⚠ 为什么按名不按号：站号在拆站之后必然错位。
    
        English:
    Match a node to a station block by **two-way containment on the station name**. ⚠ Two-way
    because the model rewrites names (author: "府城", model: "府城数地"; author: "重审", model:
    "庭上重审") -- one-way containment only hits half of them. ⚠ By name, not by number, because
    numbers misalign the moment a station is split.
    """
    n = str(name or '').strip()
    if not n:
        return None
    for blk in blocks:
        sn = _station_name_of(blk[0])
        if sn and (sn in n or n in sn):
            return blk
    return None


def apply_author_stations(nodes: list[ProgressNode],
                          blocks: list[tuple[str, dict, list[str]]]) -> int:
    """**用作者写的站表覆盖模型给的那一版**，返回覆盖几条。

    ★★★ 2026-10-27：这一层才是"后半本书被换掉"的真正解药。
    切片里已经有作者亲手写的判据 / 跨度 / 篇幅 / 章数 / 高潮 / 情节线 / 选项，
    却还要让模型**重写一遍** —— 实测它一改写就出事：判据里冒出「后」这种并列词
    ⇒ 触发"串了几件事"拆分 ⇒ 作者写 8 站、落盘 10 站、32 章变 40 章。
    ⚠ **只覆盖作者写了的字段**（空的不动）：某一站作者没写章数时，模型的推断仍然算数。
    ⚠ 模型的价值在"大纲没写时它来补"，不是"把作者写过的重写一遍"。
    
        English:
    **Overwrite the model's version with the author's station table**; returns how many nodes were
    overwritten. ★★★ 2026-10-27: this layer is the real cure for "the back half of the book being
    replaced". The slice already holds the author's own criteria / span / weight / chapters /
    climax / beats / options, yet the model was asked to **rewrite them** -- and measured, every
    rewrite breaks something: a criterion picks up a coordinating word like "after" => the
    "several tasks in one" split fires => the author's 8 stations land as 10, and 32 chapters
    become 40. ⚠ **Only fields the author wrote** are overwritten (empties are left alone): if a
    station has no chapter count, the model's inference still counts. ⚠ The model's value is
    "filling what the outline left out", not "rewriting what the author wrote".
    """
    if not blocks:
        return 0
    n = 0
    for nd in nodes:
        blk = match_station(nd.name, blocks)
        if blk is None:
            continue
        _title, fields, beats = blk
        if fields.get('完成判据'):
            nd.criteria = fields['完成判据'][:200]
        if fields.get('跨度'):
            nd.span = fields['跨度']
        if fields.get('篇幅'):
            nd.weight = fields['篇幅']
        if fields.get('章数'):
            nd.chapters = _parse_chapters(fields['章数'])
        if fields.get('高潮'):
            nd.climax = fields['高潮'][:CLIMAX_MAX_CHARS]
        if fields.get('选项'):
            nd.options = _text_list(fields['选项'], OPTIONS_MAX_ITEMS,
                                    OPTIONS_EACH_CHARS)
        if beats:
            nd.beats = tuple(beats[:BEATS_MAX_ITEMS])
        if fields.get('概要'):
            nd.summary = fields['概要'][:200]
        n += 1
    return n


def attach_chapter_plan(nodes: list[ProgressNode],
                        blocks: list[tuple[str, str]]) -> int:
    """把切好的章纲**按站名**挂到节点上，返回挂上几条。

    ⚠ 只按**站名**匹配（与 `apply_author_stations` 用同一个 `match_station`，
    双向包含）：按站号对位在拆站之后必然错位，而错位的章纲比没有章纲更糟
    （导演会照着别的站的章节演）。匹配不上就不挂 —— 那一站照旧演，不冒险。
    
        English:
    Attach the sliced chapter plan to nodes **by station name**; returns how many attached.
    ⚠ Name matching only (a plan heading containing the node name counts as a hit): matching by
    station number misaligns the moment a station gets split, and a misaligned plan is worse than
    none (the director would play another station's chapters). No match -> not attached.
    """
    if not blocks:
        return 0
    n = 0
    for nd in nodes:
        blk = match_station(nd.name, blocks)
        if blk is not None:
            nd.chapter_plan = blk[1]
            n += 1
    return n


def split_and_rebuild(nodes: list[ProgressNode]) -> list[ProgressNode]:
    """模型仍把好几件事写进一个判据时，在这里**拆开并重建节点**。

    ★★★ 2026-10-21：上面 `_BUILD_PROMPT` 已经要求"一件事一个节点"，但本项目的
    既有实测是**提示词里的约束只能挡住 40~74%** —— 关键约束必须配解析层硬处理。

    ⚠ 走**与装配侧同一份实现**（`world.progress_split.split_fat_nodes`）：
      两处各写一套的话，迟早出现"新开的卷拆了、续跑的老项目没拆"。
    ⚠ 拆完**重新编号**由那个函数负责（它会把 id 排成 N01..Nxx）。

    ★ 2026-10-27 抽成函数：拆站这条路上**每个字段都要跟着走**（跨度 / 篇幅 /
      章数 / 高潮 / 情节线 / 选项 / 章纲），而它以前埋在 `build_progress_table`
      里 ⇒ 判据测不到，只能靠真跑发现（章数就是这么丢的）。抽出来之后
      `verify_station_plan` 可以直接把它跑一遍。
    
        English:
    When the model still packs several tasks into one criterion, **split it and rebuild the nodes**.
    ★★★ 2026-10-21: `_BUILD_PROMPT` already demands "one task per node", but this project's
    measured experience is that **prompt constraints only hold 40~74% of the time** -- key
    constraints must be enforced in the parsing layer. ⚠ Uses the **same implementation as
    assembly** (`world.progress_split.split_fat_nodes`): two copies would eventually yield "new
    books split, resumed old projects not". Renumbering after the split is that function's job.
    ★ 2026-10-27 extracted: **every field must ride along this path** (span / weight / chapters /
    climax / beats / options / chapter plan), and it used to be buried inside
    `build_progress_table` => untestable, findable only by a real run (that is how chapters were
    lost). Extracted, `verify_station_plan` can exercise it directly.
    """
    try:
        from world import progress_split as _PS
        # ⚠ 不用 `to_dict()`：那个方法**不含 `chapter`**（对齐到的章节），
        #   绕它一圈会把已对齐的章节信息丢掉。这里自己摊开，把所有字段都带上。
        # [EN] ⚠ Not `to_dict()`: it **omits `chapter`** (the aligned chapter), and going through it
        # [EN] would drop already-aligned chapter info. Flatten here so every field rides along.
        _raw = [{'id': n.id, '名称': n.name, '概要': n.summary,
                 '完成判据': n.criteria, '状态': n.status, '_chapter': n.chapter,
                 # ★ 2026-10-26：跨度/篇幅要**跟着一起摊开**，否则拆完就丢
                 #   （拆出来的段会全部退回默认档 ⇒ "拆过的那本书节奏被抹平"，
                 #    而症状是"每站都差不多长"，看不出跟拆分有关）。
                 '跨度': n.span, '篇幅': n.weight,
                 # ★★★ 2026-10-27：**章数 / 高潮 / 情节线 / 选项 / 章纲也必须跟着摊开**。
                 '章数': n.chapters, '高潮': n.climax,
                 '情节线': list(n.beats or ()), '选项': list(n.options or ()),
                 '章纲': n.chapter_plan,
                 '_inferred': tuple(n.inferred or ())}
                for n in nodes]
        _dicts, _made = _PS.split_fat_nodes(_raw, log=lambda *_a: _LOG.info(*_a))
        if _made:
            nodes = [ProgressNode(id=str(d.get('id') or ''),
                                  name=str(d.get('名称') or ''),
                                  summary=str(d.get('概要') or ''),
                                  criteria=str(d.get('完成判据') or ''),
                                  # 状态照抄（拆出来的段沿用原站状态）
                                  status=str(d.get('状态') or '未开始'),
                                  chapter=str(d.get('_chapter') or ''),
                                  # 拆出来的段沿用原站的跨度/篇幅（它们本来就是同一站）
                                  span=str(d.get('跨度') or ''),
                                  weight=str(d.get('篇幅') or ''),
                                  # ★ 2026-10-27：章数与站内的台阶**照抄母站**。
                                  chapters=int(d.get('章数') or 0),
                                  climax=str(d.get('高潮') or ''),
                                  beats=tuple(d.get('情节线') or ()),
                                  options=tuple(d.get('选项') or ()),
                                  # 拆出来的两半是**同一站**，照抄同一份章纲
                                  chapter_plan=str(d.get('章纲') or ''),
                                  inferred=tuple(d.get('_inferred') or ()))
                     for d in _dicts]
            _LOG.info("进度表已细化：一站一件事（多出 %d 站，共 %d 站）",
                      _made, len(nodes))
    except Exception as _e:                                  # noqa: BLE001
        # 拆不开不算错：原表照用（别让"优化"变成"开不了卷"）
        # [EN] Failing to split is not an error: keep the original table.
        _LOG.warning("进度节点拆分跳过（%s）—— 原表照用", _e)
    return nodes


async def build_progress_table(outline_text: str) -> list[ProgressNode]:
    """从大纲构建进度节点表。

    ★ 走 `llm/replies.ask(want=list)`：**数组也有抢救**。
    这是 2026-10-06 那次开卷真正丢掉的东西 —— 截断的数组在以前救不回来，
    这一步"白花钱"且**不留痕迹**（既不报错，也不提示，节点数就是 0）。
    
        English:
    Build the progress node table from the outline.
        ★ Use `llm/replies.ask(want=list)`: **arrays also get rescue**.
        That's what was really lost in the 2026-10-06 open-book incident -- a truncated array used to be unrecoverable,
        this step "wasted money" and **left no trace** (no error, no warning, node count was just 0).
    """
    if not outline_text.strip():
        return [ProgressNode("N01", "开端", "故事开始，人物登场，核心悬念提出。", "起始场景完成"),
                ProgressNode("N02", "发展", "悬念展开，线索逐渐揭开。", "至少一条线索被主动追查"),
                ProgressNode("N03", "转折", "关键秘密揭露或最可信的人露出破绽。", "核心人物关系发生重大变化"),
                ProgressNode("N04", "高潮", "最终对峙，选择必须做出。", "主角做出决定性选择"),
                ProgressNode("N05", "收束", "人各归其位，留余韵。", "日常秩序恢复，留未尽之线")]

    # ★★★ 2026-10-27：**先按站切片，再交给模型**（理由与实测见 `slice_stations` 的注释）。
    #   切不出站（老项目的大纲不是"第 N 站"这种写法）就回退老口径 `前 4000 字`，
    #   并**明确记一行** —— 静默回退正是这次事故最难发现的地方。
    # [EN] ★★★ 2026-10-27: **slice by station first, then hand it to the model** (rationale and
    # [EN] measurements in `slice_stations`). When nothing can be sliced (older outlines are not
    # written as "station N"), fall back to the old `first 4000 chars` and **log one clear line** --
    # [EN] a silent fallback is exactly what made this incident so hard to notice.
    _sliced, _n_stations = slice_stations(outline_text)
    _blocks = _station_blocks(outline_text)
    if _sliced:
        _LOG.info("站表切片：原文 %d 字 → 站表 %d 字（读到 %d 站）",
                  len(outline_text), len(_sliced), _n_stations)
        _outline = _sliced
    else:
        _LOG.info("站表切片：没找到「第 N 站」标题（原文 %d 字）→ 回退前 %d 字"
                  "（⚠ 站多的话后半会被截掉，见 slice_stations 的注释）",
                  len(outline_text), OUTLINE_HEAD_CHARS)
        _outline = outline_text[:OUTLINE_HEAD_CHARS]

    messages = [{"role": "user", "content": fill(_BUILD_PROMPT, outline=_outline)}]
    rep = await ask("cheap", messages, purpose="progress", want=list,
                    json_mode=True, max_tokens=_PROGRESS_MAX_TOKENS, temperature=0.2)
    nodes_raw = rep.value if isinstance(rep.value, list) else []
    if not nodes_raw:
        # 数组这条路彻底没拿到 -> 再试一层：有的模型会把数组包进 {"节点": [...]}
        # [EN] The array path got nothing at all -> try one more layer: some models wrap the array in {"nodes":
        # [EN] [...]}
        obj = extract_json_lenient(rep.raw, {})
        nodes_raw = obj.get("节点", []) if isinstance(obj, dict) else []
    # 抢救回来的数组末尾可能带一个空壳（`[{...}, {}]`，是补那个悬空 `{` 的产物），
    # 它没有「名称」，会变成一个名为"节点N"的空节点 —— 丢掉。
    # [EN] The rescued array may have an empty shell at the end (`[{...}, {}]`, a byproduct of filling in
    # [EN] the dangling `{`),
    # [EN] it has no "name" and would become an empty node named "nodeN" -- drop it.
    nodes_raw = [nd for nd in nodes_raw if isinstance(nd, dict)
                 and (nd.get("名称") or nd.get("概要") or nd.get("完成判据"))]

    nodes: list[ProgressNode] = []
    for i, nd in enumerate(nodes_raw):
        nodes.append(ProgressNode(
            id=f"N{i+1:02d}",
            name=str(nd.get("名称") or nd.get("name") or f"节点{i+1}"),
            summary=str(nd.get("概要") or nd.get("summary") or ""),
            criteria=str(nd.get("完成判据") or nd.get("criteria") or ""),
            # ★ 2026-10-26：跨度与篇幅。模型没给就留空，交给下面的
            #   `resolve_span_weight` 推断并**标注是推的**。
            # ⚠ 这里不做兜底默认值：一兜底就分不清"模型给的"和"程序猜的"。
            # [EN] Span and length tiers. Left empty when the model omits them, so
            # [EN] `resolve_span_weight` can infer them **and mark them as inferred**. No default here:
            # [EN] defaulting would erase the difference between "given" and "guessed".
            span=str(nd.get("跨度") or nd.get("span") or "").strip(),
            weight=str(nd.get("篇幅") or nd.get("weight") or "").strip(),
            # ★ 2026-10-27：章数。**只认作者真写过的**（`_parse_chapters` 认不出就是 0），
            #   兜底留给 `min_chapters_for` 按篇幅档现算 —— 与 跨度/篇幅 同一条规矩：
            #   不做默认值，否则 yaml 里会出现"作者从没写过、却像他写的"的字段。
            # [EN] Chapters: only what the author really wrote (`_parse_chapters` returns 0 when it
            # [EN] can't parse); the fallback is computed live by `min_chapters_for`.
            chapters=_parse_chapters(nd.get("章数") if "章数" in nd
                                     else nd.get("chapters")),
            # ★ 2026-10-27：站内的**台阶**（高潮 / 情节线 / 选项）。
            #   同样是"只认写过的、只做封顶"：没给就是空，推演时按老样子走，
            #   不会因为这一层是新的就让老项目出问题。
            # [EN] ★ 2026-10-27: the station's **inner steps** (climax / beats / options).
            # [EN] Same rule: only what was written, and only capped. Empty means the run behaves
            # [EN] exactly as before, so this new layer can never break an existing project.
            climax=_clip_text(nd.get("高潮") if "高潮" in nd
                              else nd.get("climax"), CLIMAX_MAX_CHARS),
            beats=_text_list(nd.get("情节线") if "情节线" in nd
                             else nd.get("beats"), BEATS_MAX_ITEMS, BEATS_EACH_CHARS),
            options=_text_list(nd.get("选项") if "选项" in nd
                               else nd.get("options"), OPTIONS_MAX_ITEMS, OPTIONS_EACH_CHARS),
        ))
    for _n in rep.notes:
        _LOG.warning("进度表：%s", _n)
    # ★★★ 2026-10-27：**作者写的站表覆盖模型给的那一版**（理由见
    #   `apply_author_stations`）。⚠ 必须在**拆分之前**：模型改写过的判据常冒出并列词，
    #   先拆后覆盖的话，拆出来的两站会拿到**同一个**作者判据（两站同判据 = 一完成就
    #   连着完成两站），而先覆盖再拆，作者那一件事的判据根本不会触发拆分。
    # [EN] ★★★ 2026-10-27: **the author's station table overwrites the model's version** (why, see
    # [EN] `apply_author_stations`). ⚠ Must run **before splitting**: the model's reworded criteria
    # [EN] often pick up coordinating words; split first and the two halves would receive the **same**
    # [EN] author criterion (two stations, one criterion = completing one completes both), while
    # [EN] overwriting first means the author's single-task criterion never triggers a split.
    if _blocks:
        _n_over = apply_author_stations(nodes, _blocks)
        if _n_over:
            _LOG.info("站表覆盖：%d 站用回作者写的（判据/跨度/篇幅/章数/高潮/情节线/选项）",
                      _n_over)
    # ★★★ 2026-10-21：**模型仍把好几件事写进一个判据时，在这里拆开**。
    #   上面 `_BUILD_PROMPT` 已经要求"一件事一个节点"，但本项目的既有实测是
    #   **提示词里的约束只能挡住 40~74%** —— 关键约束必须配解析层硬处理。
    #   ⚠ 走**与装配侧同一份实现**（`world/progress_split.split_fat_nodes`）：
    #     两处各写一套的话，迟早出现"新开的卷拆了、续跑的老项目没拆"。
    #   ⚠ 拆完**重新编号**由那个函数负责（它会把 id 排成 N01..Nxx）。
    # [EN] ★★★ 2026-10-21: **when the model still packs several tasks into one criterion, split it
    # [EN] here**. `_BUILD_PROMPT` above already demands "one task per node", but this project's
    # [EN] measured experience is that **prompt constraints only hold 40~74% of the time** -- key
    # [EN] constraints must be enforced in the parsing layer.
    # [EN] ⚠ Uses the **same implementation as assembly** (`world.progress_split.split_fat_nodes`):
    # [EN] two copies would eventually yield "new books split, resumed old projects not".
    nodes = split_and_rebuild(nodes)
    # ★★★ 2026-10-26：**最后一步才补跨度/篇幅**（放在拆分之后，理由有两条）：
    #   ① 拆分会让节点数变化，"第几个/共几个"那条结构性推断必须按**拆完的**算；
    #   ② 拆出来的段与它母站同档，所以先摊开带过去、再统一 resolve，不会互相打架。
    # [EN] ★★★ Fill span/weight **last**, after splitting, for two reasons: (1) splitting changes the
    # [EN] node count, and the index-based structural inference must run on the final list; (2) split
    # [EN] parts share their station's tier, so flattening first and resolving once avoids conflicts.
    nodes = resolve_span_weight(nodes)
    _LOG.info("进度表构建完成：%d 个节点（跨度/篇幅已定，其中 %d 站有推断成分）",
              len(nodes), sum(1 for n in nodes if n.inferred))
    return nodes


# ── 正文对齐 ─────────────────────────────────────────────────────────
# [EN] ── Body text alignment ─────────────────────────────────────────────────
_ALIGN_PROMPT = """你是一位小说编辑。下面是一份小说已写好的正文（按章节分段，**最后附有一段【末章结尾】**），以及一份故事进度表（节点列表）。
请判断：正文已覆盖了哪些节点？每段正文大致对应哪个节点？

请以 JSON 回答：
{
  "对齐": [
    {"章节": "第1章", "覆盖节点": ["N01"], "摘要": "本章发生了什么（一句话）"},
    ...
  ],
  "已完成节点": ["N01", "N02"],
  "前情提要": "已发生的事件摘要、人物关系现状、已揭示和未揭示的秘密（150~300字）。**必须覆盖到【末章结尾】为止**——这是故事停下的地方，不是中间某章",
  "前文末段": "故事停在哪：此刻的场景、在场的人、悬而未决的那件事（60~120字）。下一部要从这里接着写"
}

★ 长度是硬要求：每条的「摘要」**一句话、不超过 40 字**；「前情提要」**150~300 字**；
「前文末段」**60~120 字**；「对齐」只列给出的章节，**不要虚构章节**。只输出 JSON 对象本身，
不要开场白、不要结语、不要用 ```json 代码块包起来。

进度表：
{progress}

正文内容：
{content}
"""


async def align_with_text(nodes: list[ProgressNode], chapters: dict[str, str]) -> dict[str, Any]:
    """正文对齐。chapters = {章节名: 章节内容}。返回对齐结果。

    ★ 这一步的输出也不小（每章一条 + 前情提要），当天实测已经吃到 1884 token，
      离默认的 2000 只差一口气 —— 所以显式给预算并接上重试/抢救。
    
        English:
    Body text alignment. chapters = {chapter name: chapter content}. Returns the alignment result.
        ★ The output of this step is not small either (one entry per chapter + recap); measured that day it already hit 1884 tokens,
          just a hair away from the default 2000 -- so give the budget explicitly and wire up retry/rescue.
    """
    if not chapters:
        return {"对齐": [], "已完成节点": [], "前情提要": "", "前文末段": ""}

    # 进度表文本
    # [EN] Progress table text
    progress_text = "\n".join(f"[{n.id}] {n.name}：{n.summary}（判据：{n.criteria}）" for n in nodes)
    # 正文拼接（截取关键段）
    # ★ 2026-10-10（第 04 类第 2 条）：每章按**句子边界**截，别交半句给模型
    #   —— 判"哪些剧情节点已完成"最怕的就是最后一句是残的。
    # [EN] Body text concatenation (truncate key sections)
    # [EN] ★ 2026-10-10 (category 04 item 2): truncate each chapter by **sentence boundary**, don't hand a
    # [EN] half-sentence to the model
    # [EN] -- the last thing you want when judging "which plot nodes are completed" is the last sentence
    # [EN] being incomplete.
    from util.text import head_sentences, tail_sentences
    content_parts = []
    for ch_name, ch_text in chapters.items():
        content_parts.append(f"【{ch_name}】\n{head_sentences(ch_text, 1500)}")
    # ★★★ 2026-10-28（用户：「导入故事的时候包含一部分之前故事的提要和之前故事的最后部分」）：
    #   上面每章只给**前** 1500 字，一部长篇的**结局**在最后一章的末尾 ——
    #   模型从头到尾没见过它 ⇒ 前情提要停在倒数第二章半中间 ⇒
    #   推演起点跟"故事停下的地方"对不上（用户实测报过的现象）。
    #   ⇒ 把**最后一章的末尾**（句子边界起头）附在最后，明说"后面没了"。
    # [EN] ★★★ 2026-10-28 (user: "when importing a story, include the previous story's recap and
    # [EN] its last part"): each chapter above only feeds its **first** 1500 chars, and the ending of
    # [EN] a long story sits at the **tail** of the last chapter -- the model never sees it, so the
    # [EN] recap stops mid-previous-chapter and the simulation's start point misses where the story
    # [EN] actually stopped. Append the last chapter's **tail** (sentence-boundary start) and say so.
    _items = list(chapters.items())
    _last_name, _last_text = _items[-1]
    _tail = tail_sentences(_last_text, 900)
    if _tail.strip():
        content_parts.append(f"【末章结尾 · {_last_name} · 正文到此为止，后面没了】\n{_tail}")
    content = "\n\n".join(content_parts)
    if len(content) > 9000:
        content = content[:9000] + "\n...(截断)"

    messages = [{"role": "user", "content": fill(
        _ALIGN_PROMPT, progress=progress_text, content=content)}]
    rep = await ask("cheap", messages, purpose="alignment", want=dict,
                    json_mode=True, max_tokens=_ALIGN_MAX_TOKENS, temperature=0.2)
    result = rep.value if isinstance(rep.value, dict) else {}
    for _n in rep.notes:
        _LOG.warning("正文对齐：%s", _n)
    # ★ 末段**原文摘录**在代码里算（确定性，不靠模型转述）：
    #   模型给的是"前文末段"的**情况摘要**；导出侧拼接要的是**原句**。
    #   两个都存 —— 摘要给人读，原文给下一部开头垫底。
    # [EN] The **raw tail excerpt** is computed in code (deterministic, not a model paraphrase):
    # [EN] the model's "前文末段" is a situational summary; stitching wants the **verbatim** tail.
    # [EN] Keep both -- summary for humans, verbatim for the next installment's head.
    result.setdefault("前文末段", "")
    result["前文末段原文"] = _tail

    # 更新节点状态
    # [EN] Update node status
    completed = set(result.get("已完成节点", []))
    for n in nodes:
        if n.id in completed:
            n.status = "已完成"
    return result


# ── 已发生故事线落盘 ─────────────────────────────────────────────────
# [EN] ── Persist occurred storyline ─────────────────────────────────────────────────
def write_story_so_far(path: Path, alignment: dict, nodes: list[ProgressNode]) -> None:
    """写 已发生故事线.md。

    ★ 2026-10-28（用户：导入故事要带上"之前故事的提要 + 最后部分"）：
      多写两节 —— 「前文末段」（模型给的情况摘要）与「前文末段原文」
      （代码摘的原句）。**运行侧的「前情提要.md」才是推演读的那份**（见
      `pipeline._freeze`），这里只是给作者看的档案。
        English:
    Write 已发生故事线.md.
        ★ 2026-10-28: two more sections -- the model's situational summary of the ending and the
        code-extracted verbatim tail. **The recap file the run actually reads is 前情提要.md**
        (see `pipeline._freeze`); this file is the author-facing archive.
    """
    lines = ["# 已发生故事线", "", "## 前情提要", alignment.get("前情提要", "（无）"), ""]
    if str(alignment.get("前文末段") or '').strip():
        lines += ["## 前文末段", str(alignment["前文末段"]).strip(), ""]
    if str(alignment.get("前文末段原文") or '').strip():
        lines += ["## 前文末段原文", str(alignment["前文末段原文"]).strip(), ""]
    lines.append("## 章节对齐")
    for ch in alignment.get("对齐", []):
        lines.append(f"- **{ch.get('章节', '?')}** → {', '.join(ch.get('覆盖节点', []))}：{ch.get('摘要', '')}")
    lines.append("")
    lines.append("## 节点状态")
    for n in nodes:
        mark = "✅" if n.status == "已完成" else ("⏳" if n.status == "进行中" else "⬜")
        lines.append(f"- {mark} {n.id} {n.name}：{n.status}")
    atomic_write_text(path, "\n".join(lines))


# ── 起始点建议 ────────────────────────────────────────────────────────
# [EN] ── Starting point suggestion ────────────────────────────────────────────────────────
def suggest_start_point(nodes: list[ProgressNode], chapters: dict[str, str]) -> str:
    """建议起始点：有正文时接续最后完成节点之后，无正文则第一个节点。
        English:
    Suggest starting point: when body text exists, continue after the last completed node; otherwise
    the first node.
    """
    if not chapters:
        return nodes[0].id if nodes else "N01"
    last_done = None
    for n in nodes:
        if n.status == "已完成":
            last_done = n
    if last_done is None:
        return nodes[0].id if nodes else "N01"
    idx = next((i for i, n in enumerate(nodes) if n.id == last_done.id), -1)
    if idx < len(nodes) - 1:
        return nodes[idx + 1].id
    return last_done.id


# ── 拆正文为章节 ──────────────────────────────────────────────────────
#: 章节标题的正则。
# [EN] ── Split body text into chapters ──────────────────────────────────────────────────────
# [EN] : Regex for chapter titles.
#:
#: ★★★ 2026-10-09 修：**少了开头那个 markdown 井号**，于是
#:   `# 第一章 早了一刻` / `# Chapter 2 Something` 这种**正文最常规的写法一条都拆不出来**。
# [EN] : ★★★ 2026-10-09 fix: **the leading markdown hash was missing**, so [EN] : `# 第一章 早了一刻` / `# Chapter 2 Something` -- the **most common way of writing body text** --
# [EN] could not be split out at all.
#:
#:   坏得很安静：拆不出时函数返回 `{"正文": 全文}`，而**所有**拆不出的文件都返回
#:   同一个键 `"正文"` —— 调用方是 `chapters.update(split_chapters(...))` 逐个文件合并，
#:   于是**后一个文件把前一个整个盖掉**。实测三章正文合并完只剩下**一章**。
# [EN] : It failed silently: when splitting fails the function returns `{"正文": 全文}`, and **all** files
# [EN] that fail to split return
# [EN] : the same key `"正文"` -- the caller does `chapters.update(split_chapters(...))` merging file by
# [EN] file,
# [EN] : so **each later file completely overwrites the previous one**. Measured: after merging three
# [EN] chapters' body text only **one chapter** remained.
#:
#:   后果（用户能直接感觉到的）：`align_with_text` 只拿到一章去判「哪些节点已完成」，
#:   **前情提要因此残缺**；而说明书 §6.4 的黄金档、以及 `samples/` 里给的示例，
#:   正文第一行恰恰全是 `# 第一章 …` —— **示例教人这么写，程序却读不出来**。
# [EN] : Consequence (directly noticeable to users): `align_with_text` only gets one chapter to judge
# [EN] "which nodes are completed",
# [EN] : **so the recap is incomplete**; meanwhile the golden range in spec §6.4, as well as the
# [EN] example given in `samples/`,
# [EN] : have the body text first line as exactly `# 第一章 …` -- **the example teaches people to write it
# [EN] this way, but the program can't read it**.
#:
#:   为什么一直没人发现：`tools/` 里**从来没有一支判据覆盖 `split_chapters`**
#:   （`grep split_chapters tools/` 是空的）。所以这次连同判据一起补。
# [EN] :   Why nobody ever noticed: in `tools/` **no criterion ever covered `split_chapters`**
# [EN] : (`grep split_chapters tools/` is empty). So this time we add the criterion along with the fix.
#: ★★★ 2026-10-27：**章节标题识别搬去 `util/chapters.py`**（全项目唯一实现）。
#:
#:   这里原来有一份自己的正则 `第.{1,5}[章回节]` —— 中间那个 `.{1,5}` **允许任意字符**，
#:   于是正文里单独成行的一句台词「第二回正了。」会被当成**章节标题**，
#:   **把这一行之后的所有正文都切成"第二章"** ⇒ 章节边界整个错位
#:   ⇒ 前情提要按错的章节对齐（症状是"前情提要莫名其妙"）。
#:   而 `booklab/reader.py` 里还有**第二份**正则（它的注释还写着"复用同一套规则" —— 那是假的）。
#:   ⇒ 现在两份都从 `util/chapters.py` 取，规则只有一份。
#:
#:   ⚠ 下游仍可照旧 `from ingest.progress import split_chapters`（这里再导出一次），
#:   免得"改了一处、忘了另一处"。
#:
#:   [EN] ★★★ 2026-10-27: **chapter-heading recognition moved to `util/chapters.py`** (the single
#:   implementation).
#:   This file used to carry its own regex `第.{1,5}[章回节]` -- the `.{1,5}` in the middle **allowed
#:   arbitrary characters**, so a standalone line of prose such as "第二回正了。" was taken for a
#:   chapter heading, **cutting everything after that line into "chapter 2"** => the chapter
#:   boundaries shifted and the recap aligned against the wrong chapters.
#:   And `booklab/reader.py` carried a **second** copy (its comment claimed "the same set of rules"
#:   -- it was not true).
#:   => both now take the rules from `util/chapters.py`.
#:
#:   ⚠ Downstream may still `from ingest.progress import split_chapters` (it is re-exported at the
#:   top of this file).