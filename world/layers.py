# -*- coding: utf-8 -*-
"""设定分层：把「作者导进来的一大堆设定」按**作用范围**分成五层，各自决定
「什么时候出现、在哪个场合出现、影响谁、说多重」。

用户 2026-10-07
--------------
「我导入的设定文件夹的内容可能包含很多地方 包括很大的设定 也包括很细节的设定
  你要自己分层管理 有些很大的背景只在后台特定的时候发挥作用 具体每天的故事
  可能是由很小的设定影响的 你要分层管理……

  而且有些时候需要导演 和 小说作者 以及剧作家 讨论生成一些新的设定
  这些都要进行推演 以便方便故事推进 同时不能够影响总体设定

  （你自己在项目里分层次 设置设定文件集合，同时自己管理好不同层级
    不同内容设定发挥的时间 场合 权重 影响谁等等 你心里要清楚）」

问题出在哪（改之前先看这一条）
--------------------------------
在此之前所有设定是**一坨**：`sim/setup._worldview_text()` 把世界观、剧情参考线、
地点、关系、伏笔拼成一段 `worldview_text`，而 `world_prefix()` 每拍都给模型
发这坨东西的**前 500 字**。于是：

* **大背景挤掉了小细节**：书名里那句最重要的世界铁律排在最前面、吃掉额度，
  而"东家那把紫砂壶缺个角"这种真正会影响今天这场戏的东西，连出场机会都没有；
* **每拍都发一遍**：人物在第 9 天做决定时，还在读第 1 页的世界观全文；
* **细节根本没被保存**：开卷时模型把细节都概括进 120 字的《世界观》里了，
  原文只剩在引用文件夹里，推演时够不着。

所以这里做三件事：

1. **分层**（`LAYERS`）：世界 / 主线 / 场景 / 细节 四层进索引（人物层由人物卡承载）。
   每层记 `生效时机（when）· 生效场合（where）· 影响谁（who）· 权重（weight）`
   —— 这正是用户要求"你心里要清楚"的那张表，而它落盘成
   `分层设定.yaml` / `分层设定.md`，**看得见**。
2. **按需渲染**（`render`）：大背景平时只给一句"气候"（`CANON_BRIEF`），
   只在**特定时机**展开全文 —— 开篇、高潮日、每 N 天一次（`should_expand`）。
   而细节层**每天都出现**，只要它的场合对得上。这就是"很大的背景只在后台
   特定的时候发挥作用，具体每天的故事由很小的设定影响"。
3. **写入权限**（`admit_new`）：剧组（导演+小说作家+剧作者）讨论出来的新设定
   只能进**场景层 / 细节层**，而且**必须有作用范围**（限地点 / 限人 / 限时间），
   否则拒收。它们存在 `world.local_settings` 里，与 `worldview_text` /
   `rules_text` **物理隔离** —— "不能够影响总体设定"是靠结构保证的，不是靠约定。

四条设计约束（改之前先读）
--------------------------
1. **标签兼容**。`world_prefix()` 里那一行仍叫 `[世界观]` —— 五支验证脚本
   （`verify_world_rules` / `verify_sim_prompt` / `verify_film_style` / …）
   靠它做断言。分层改的是**内容与额度**，不是标签。
2. **索引为空就退回老行为**。`world_prefix()` 只在 `world.layer_index` 非空时
   走分层渲染 —— 直接 `WorldState()` 造出来的测试夹具不受影响。
3. **不做 LLM 概括**。分层只搬原文（`build_index` 从设定集的结构化字段取），
   概括会把"谁不能死""哪条规矩不许破"这类判据改花 —— 与 `collect_rules`
   原文照录同一条道理。
4. **认不出就当生效**（`_when_ok` 解析不了时间就返回 True）。宁可多给一条，
   也别让作者写的一句话**悄悄不生效** —— "写了没用"是最难查的一类。

English:
Setting layering: split "the big pile of settings the author imported" into five layers by
**scope of effect**, each deciding
"when it appears, on what occasion it appears, whom it affects, and how strongly it is said".
User 2026-10-07
--------------
"The content of the setting folder I import may contain many places, including very large
settings and also very detailed settings
  you must layer and manage them yourself. Some very large backgrounds only take effect at specific times in the background. The concrete daily story
  may be influenced by very small settings. You must layer and manage……
  And sometimes the director and the novel author and the playwright need to discuss and generate some new settings
  these all need deduction to facilitate story advancement, while not being able to affect the overall setting
  (You layer it yourself in the project, set up the set of settings files, and manage the different layers well
    the timing, occasion, weight, whom it affects, etc. of the different content settings — you must be clear in your mind)
Where the problem lies (read this one before modifying)
--------------------------------
Before this, all settings were **one lump**: `sim/setup._worldview_text()` concatenates
worldview, plot reference line,
locations, relationships, foreshadowing into one `worldview_text`, and `world_prefix()` sends
the model
the **first 500 characters** of this lump every beat. So:
* **The big backdrop crowds out the small details**: that most important world iron law in the book title is placed at the very front, eating the quota,
  while things like "the master's purple clay teapot is missing a corner" that would actually affect today's scene don't even get a chance to appear;
* **Sent every beat**: when the characters make decisions on day 9, they are still reading the full worldview from page 1;
* **Details are not saved at all**: at the start, the model summarized all the details into the 120-character "Worldview",
  leaving only the original text in the reference folder, out of reach during inference.
So three things are done here:
1. **Layering** (`LAYERS`): world / mainline / scene / detail, four layers go into the index (the character layer is carried by character cards).
   Each layer records `when it takes effect (when) · occasion it takes effect (where) · whom it affects (who) · weight (weight)`
   -- this is exactly the table the user asked you to "be clear in your mind", and it is persisted to disk as
2. **Render on demand** (`render`): the big backdrop normally only gives one line of "climate" (`CANON_BRIEF`),
   and only expands the full text at **specific timings** -- opening, climax day, once every N days (`should_expand`).
   And the detail layer **appears every day**, as long as its occasion matches. This is "a very large backdrop only takes effect in the background
   at specific times, and the specific story each day is influenced by very small settings".
3. **Write permission** (`admit_new`): new settings discussed by the crew (director + novelist + playwright)
   can only enter the **scene layer / detail layer**, and **must have a scope of effect** (limited to location / limited to person / limited to time),
   otherwise rejected. They are stored in `world.local_settings`, **physically isolated** from `worldview_text` /
   `rules_text` -- "cannot affect the overall setting" is guaranteed by structure, not by convention.
Four design constraints (read before modifying)
--------------------------
1. **Tag compatibility**. That line in `world_prefix()` is still called `[世界观]` -- five verification scripts
   (`verify_world_rules` / `verify_sim_prompt` / `verify_film_style` / ...)
   rely on it for assertions. Layering changes **content and quota**, not the tag.
2. **Fall back to old behavior when the index is empty**. `world_prefix()` only takes layered rendering
   when `world.layer_index` is non-empty -- test fixtures created directly via `WorldState()` are unaffected.
3. **No LLM summarization**. Layering only moves the original text (`build_index` takes from the structured fields of the settings collection);
   summarization would blur criteria like "who cannot die" and "which rule must not be broken" -- same principle as `collect_rules`
   copying the original text verbatim.
4. **When unrecognizable, treat as effective** (`_when_ok` returns True if it cannot parse the
time). Better to give one extra
   than let a sentence written by the author **silently fail to take effect** -- "wrote it but it's useless" is the hardest class to trace.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from logger import get_logger

from util.chapters import NUM_CHARS as _NUM_CHARS, cn_to_int

_LOG = get_logger('nws.layers')

# ══════════════════════════════════════════════════════════════════════
#  层定义
# [EN] Layer definition
# ══════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class LayerDef:
    """一层设定：它是什么、什么时候出现、谁有权写。
        English:
    One layer of settings: what it is, when it appears, who has the right to write it.
    """

    key: str
    name: str
    duty: str              # 一句话说明（写进分层设定.md，给人看）
    weight: int            # 同层内排序的默认权重（越大越靠前）
    in_prefix: bool        # 进不进 `world_prefix()`（人物层由人物卡承载，不进）
    brief: int             # 常态字符额度
    full: int              # 升权后的字符额度
    expand: str            # 什么时候升权（人话）
    writer: str            # 谁有权写：'作者' / '作者+剧组'
    # [EN] One-line description (written into 分层设定.md, for humans to read)
    # [EN] Default weight for ordering within the same layer (larger means further forward)
    # [EN] Whether it enters `world_prefix()` (the character layer is carried by character cards, so it
    # [EN] does not enter)
    # [EN] Normal character quota
    # [EN] Character quota after weight boost
    # [EN] When to boost weight (in plain words)
    # [EN] Who has write permission: 'author' / 'author + crew'


LAYERS: tuple[LayerDef, ...] = (
    LayerDef(
        key='canon', name='世界层', weight=5, in_prefix=True,
        duty='整本书的大背景：世界是什么样子、时代与规矩、故事从哪儿起头。'
             '**平时只当"气候"**，不逐字进提示词。',
        brief=140, full=900,
        expand='开篇第 1 天 · 高潮日 · 每 3 天一次 · 每换一个新地方',
        writer='作者',
    ),
    LayerDef(
        key='arc', name='主线层', weight=4, in_prefix=True,
        duty='这本书要往哪走：剧情参考线、故事进度节点、伏笔与悬线。',
        brief=260, full=600,
        expand='每章（节点切换）与开篇',
        writer='作者',
    ),
    LayerDef(
        key='scene', name='场景层', weight=3, in_prefix=True,
        duty='眼前这个地方、以及它牵到的人：地点说明、人物关系。',
        brief=220, full=220,
        expand='只要这场戏发生在这个地点',
        writer='作者+剧组',
    ),
    LayerDef(
        key='detail', name='细节层', weight=2, in_prefix=True,
        duty='每天用得上的小设定：器物、习俗、口头禅、小规矩、本地风物、'
             '谁欠谁一句话 —— **每天的故事多半由它推动**。',
        # ⚠ 额度与"条数上限 / 每条上限"要**一起看**：4 条 × 70 字 = 280 > 260，
        #   所以**额度才是真正的约束**（第四条会被整条丢掉）。把 quota 定成
        #   "刚好装下 4 条"的话，那条"额度不够就整条丢"的规矩永远不会被触发 ——
        #   也就永远测不出来（反例法当场证明了这一点）。
        # [EN] ⚠ Quota and "max item count / per-item limit" must be looked at **together**: 4 items × 70 chars
        # [EN] = 280 > 260,
        # [EN] so **the quota is the real constraint** (the 4th item gets dropped entirely). If quota is set to
        # [EN] "just fits 4 items", then the rule "drop the whole item if quota is insufficient" will never be
        # [EN] triggered ——
        # [EN] and thus can never be tested (the counterexample method proved this on the spot).
        brief=260, full=260,
        expand='当天这场戏用得上时才出现（按场合 / 在場的人筛）',
        writer='作者+剧组',
    ),
    LayerDef(
        key='person', name='人物层', weight=3, in_prefix=False,
        duty='一个人自己的设定（身份 / 性格 / 口癖 / 秘密 / 目标 / 红线）。'
             '**由人物卡承载**（`agent.core.Agent._persona_prompt`），'
             '不重复进世界前缀 —— 同一件事进两处只会让 prompt 变贵。',
        brief=0, full=0,
        expand='这个人出场时',
        writer='作者',
    ),
)

BY_KEY: dict[str, LayerDef] = {l.key: l for l in LAYERS}
LAYER_KEYS: tuple[str, ...] = tuple(l.key for l in LAYERS)

#: **剧组能新建的层**。就这两层 —— 世界层与主线层是作者的"总体设定"，
#: 剧组连"新增一条"都不行（用户明确要求「不能够影响总体设定」）。
#: 人物层不进前缀（由人物卡承载），剧组往那儿塞东西等于塞进黑洞，所以也不给。
# [EN] : **Layers the crew can create**. Just these two layers —— the world layer and the mainline
# [EN] layer are the author's "overall setting",
# [EN] : the crew cannot even "add one item" (the user explicitly requested "must not affect the
# [EN] overall setting").
# [EN] : the character layer does not enter the prefix (carried by character cards), and having the
# [EN] crew stuff things there is like stuffing into a black hole, so it is not allowed either.
CREW_WRITABLE: tuple[str, ...] = ('scene', 'detail')

#: 每层的内容来自设定集里的哪几个文件。
#: ★ 这张表就是用户说的"设定文件集合" —— 写进 `分层设定.md` 的头部，
#:   作者一眼能看到"想改哪一层，去动哪个文件"。
# [EN] : which files in the setting collection each layer's content comes from.
# [EN] : ★ This table is exactly the "setting file set" the user mentioned —— written into the head of [EN] `分层设定.md`,
# [EN] :   so the author can see at a glance "to change which layer, go touch which file".
LAYER_SOURCES: dict[str, tuple[str, ...]] = {
    'canon': ('世界观.md', '顶级规则.md', '类型卡.yaml', '风格卡.yaml'),
    'arc': ('剧情走向.md', '故事进度.yaml', '伏笔与悬线.yaml'),
    'scene': ('地点.yaml', '关系.yaml'),
    'detail': ('细节设定.yaml',),
    'person': ('人物.yaml',),
}

# ── 额度与节流（**常量不是旋钮**：它们是叙事手感，不是成本开关）──
#: 大背景平时只给这么多字（一句"气候"）
# [EN] ── Quota and throttling (**constants are not knobs**: they are narrative feel, not cost
# [EN] switches) ──
# [EN] : the big background normally only gets this many characters (a single line of "climate")
CANON_BRIEF = 140
#: 大背景升权后的额度
# [EN] : the quota for the big background after weight boost
CANON_FULL = 900
#: 主线层 / 场景层每次给的额度
# [EN] : the quota given each time for the mainline layer / scene layer
ARC_LINE = 300
SCENE_LINE = 240
#: 细节层每次最多给几条、每条多少字（"每天的故事由小设定推动"，
#: 但一次塞二十条就又变成一坨了）
# [EN] : the max number of items and chars per item for the detail layer each time ("each day's story
# [EN] is driven by small settings",
# [EN] : but stuffing twenty items at once turns it into one lump again)
DETAIL_MAX_ITEMS = 4
DETAIL_EACH = 70
#: 每几天把大背景展开一次（用户说的"后台特定的时候"）
# [EN] : expand the big background once every few days (the "specific times in the background" the user
# [EN] mentioned)
EXPAND_EVERY_DAYS = 3
#: 张力到多少算高潮日（那天也把大背景展开）
# [EN] : what tension counts as a climax day (also expand the big background that day)
EXPAND_TENSION = 0.70

# ── 落盘文件名（都在运行文件夹里；**项目文件夹只读**）──
# [EN] ── Persisted filenames (all inside the run folder; **the project folder is read-only**) ──
FILE_PROFILE_YAML = '分层设定.yaml'
FILE_PROFILE_MD = '分层设定.md'
FILE_LOCAL_JSON = '临时设定.json'
FILE_LOCAL_MD = '临时设定.md'


def layer_name(key: str) -> str:
    """层 key → 人话名（认不出就原样返回，**不返回空白**）。
        English:
    Layer key -> human-readable name (return as-is if unrecognizable, **do not return blank**).
    """
    ld = BY_KEY.get(str(key or '').strip())
    return ld.name if ld else str(key or '').strip()


#: 层名的**别名表**（中文全称 / 简称 / 英文 key 都认）。
#: ⚠ 必须认中文：剧组那位是模型，提示词里给的是"世界层/细节层"这样的中文名，
#:   它照着写回来就是中文。只认英文 key 的话，**每一条都会被静默丢掉**
#:   （表现成"剧组讨论了半天什么都没发生"）。
# [EN] : the **alias table** for layer names (full Chinese name / abbreviation / English key are all
# [EN] recognized).
# [EN] : ⚠ Must recognize Chinese: the crew member is a model, and the prompt gives it Chinese names
# [EN] like "world layer/detail layer",
# [EN] : so it writes them back in Chinese. If only English keys are recognized, **every single item
# [EN] will be silently dropped**
# [EN] :   (manifesting as "the crew discussed for ages and nothing happened").
_LAYER_ALIAS: dict[str, str] = {}
for _ld in LAYERS:
    for _nm in (_ld.key, _ld.name, _ld.name[:-1] if _ld.name.endswith('层') else _ld.name):
        _LAYER_ALIAS[str(_nm).strip().lower()] = _ld.key
_LAYER_ALIAS.update({'world': 'canon', 'setting': 'canon', 'worldview': 'canon',
                     'story': 'arc', 'plot': 'arc', 'local': 'scene',
                     'place': 'scene', 'detail layer': 'detail',
                     '支线': 'arc', '小设定': 'detail', '微设定': 'detail'})


def normalize_layer(key: str) -> str:
    """把"层"的各种写法归一成层 key（认不出返回空串）。

    认不出**返回空串**而不是猜一个：猜错会把"它想改世界层"变成"它加了一条细节"，
    那正是用户要求拦住的事。调用方（`admit_new`）拿空串会当场拒收。
    
        English:
    Normalize the various spellings of "layer" into a layer key (return empty string if
    unrecognizable).
        **Return an empty string** instead of guessing when unrecognizable: a wrong guess turns "it wants to change the world layer" into "it added a detail",
        which is exactly what the user asked to block. The caller (`admit_new`) receiving an empty string will reject on the spot.
    """
    return _LAYER_ALIAS.get(str(key or '').strip().lower(), '')


def crew_writable_names() -> str:
    return '、'.join(f'「{layer_name(k)}」' for k in CREW_WRITABLE)


# ══════════════════════════════════════════════════════════════════════
#  一条设定
# [EN] One setting
# ══════════════════════════════════════════════════════════════════════
_WHEN_RE = re.compile(r'^第\s*(\d+)\s*(?:[~\-—－到至]\s*(\d+)\s*)?天?\s*(起)?$')


def _cn2int(s: str) -> int | None:
    """把「三」「十五」这种中文数字换成 3 / 15（认不出返回 None）。

    ★ 2026-10-27：转调 `util/chapters.py::cn_to_int`（**全项目唯一**的中文数字实现）。
      原来这里自己写了一份 `_CN_NUM`，**只认单个字** ——
      于是「第十五章」被**静默丢掉**（而「第100章」是好的）：
      差别藏在"几个字"里，作者根本看不出来，只会觉得"写了没反应"。
      这就是"同一件事两处实现"必然漂移的那一刀。
    [EN] ★ 2026-10-27: delegate to `util/chapters.py::cn_to_int` (the **single** Chinese-numeral
    [EN] implementation for the whole project). This module used to carry its own `_CN_NUM`, which
    [EN] accepted **single characters only** -- so "chapter fifteen" was **silently dropped** (while
    [EN] "chapter 100" worked): the difference hides in "how many characters", the author cannot see
    [EN] it, they just think "I wrote it and nothing happened". That is the knife of "the same thing
    [EN] implemented twice always drifts".
    """
    return cn_to_int(s)


#: 「必出日」那一栏接受的各种写法：`3` / `"3"` / `"3,7"` / `"第3天"` / `"第3、7章"`
#: / `"3 7"` / `[3, 7]`。**认不出来就当没有**（不许猜一个）。
# [EN] : The spellings accepted in the "must appear" field: `3` / `"3"` / `"3,7"` / `"第3天"` /
# [EN] `"第3、7章"` / `"3 7"` / `[3, 7]`. **Unrecognizable means "none"** (never guess one).
_MUST_KEYS = ('必出日', '必出章', '必出', '指定章次', 'must_on', 'must_on_days')

#: 区间写法：`3-5` / `第3到5章` / `三到五`。
#: ⚠ 数字部分是**共享闭集**（`util/chapters.py::NUM_CHARS`）—— 不是各写各的。
#: [EN] The range form: `3-5` / `第3到5章` / `三到五`.
#: ⚠ The numeral part is the **shared closed set** (`util/chapters.py::NUM_CHARS`).
_MUST_RANGE_RE = re.compile(
    r'^第?\s*([' + _NUM_CHARS + r']+)\s*[-~—－到至]\s*([' + _NUM_CHARS + r']+)\s*[天日章]?.*$')

#: 单个写法：`3` / `第3章` / `第三天` / `第十五章` / `第3章必出`（模型常多写两个字）。
#: [EN] The single form: `3` / `第3章` / `第三天` / `第十五章` / `第3章必出` (the model often adds
#: [EN] two extra characters).
_MUST_ONE_RE = re.compile(r'^第?\s*([' + _NUM_CHARS + r']+)\s*[天日章]?.*$')


def parse_must_on(raw) -> tuple[int, ...]:
    """把「必出日」那一栏解析成 `(3, 7, 8)` 这样的章号集合。

    ★ 解析不出来**一律当没有**（返回空元组）—— 猜一个章号会让一条细节
      在错误的章节里冒出来，而作者完全不知道自己写过这个数。
      （与 `when_ok` 那条"认不出就当全程生效"是**反的**：那边认不出是
      "别让作者写的一句话悄悄失效"，这边认不出是"别让作者没写的东西生效"。）

    ★ 2026-10-27 修的真 bug：中文数字**只认单个字**（「三」认得，「十五」不认），
      而模型与作者写的偏偏常是「第十五章」 ⇒ 那一条**静默丢掉**，
      表现成"程序照跑、就是没出"。⇒ 现在走**共享闭集**（`util/chapters.py::cn_to_int`）。
      顺带补上**区间**（`第3-5章` ⇒ 3,4,5 —— 旧口径只给出 3，是**静默的半个答案**）。

        English:
    Parse the "must appear" field into a set of chapter numbers like `(3, 7, 8)`.
        ★ **Unrecognizable always means "none"** (returns an empty tuple) -- guessing a chapter
        [EN] number makes a detail pop up in the wrong chapter while the author has no idea they ever
[EN] wrote that number. (This is the **opposite** of `when_ok`'s "unrecognized = effective
    [EN] throughout": there it's "don't let a sentence the author wrote silently fail", here it's
    [EN] "don't let something the author never wrote take effect".)

    ★ The real bug fixed on 2026-10-27: Chinese numerals were accepted for **single characters
    [EN] only** ("三" yes, "十五" no), while models and authors typically write "第十五章" => that
    [EN] entry was **silently dropped**, manifesting as "the program runs fine, it just never shows
    [EN] up". => now it goes through the **shared closed set** (`util/chapters.py::cn_to_int`).
    [EN] A **range** was added too (`第3-5章` => 3,4,5 -- the old behaviour gave just 3, a
    [EN] **silently halved answer**).
    """
    if raw is None:
        return ()
    if isinstance(raw, bool):
        return ()
    if isinstance(raw, int):
        return (int(raw),) if int(raw) > 0 else ()
    if isinstance(raw, (list, tuple, set)):
        out: list[int] = []
        for x in raw:
            out.extend(parse_must_on(x))
        return tuple(sorted(set(out)))
    s = str(raw).strip()
    if not s:
        return ()
    out = []
    for part in re.split(r'[、,，;；\s/和跟及]+', s):
        part = part.strip()
        if not part:
            continue
        # ① 区间：`3-5` / `第3到5章` / `三到五` ⇒ 展开成每个章号
        # [EN] ① Range: `3-5` / `第3到5章` / `三到五` => expand into every chapter number
        mr = _MUST_RANGE_RE.match(part)
        if mr:
            a = _cn2int(mr.group(1))
            b = _cn2int(mr.group(2))
            if a and b and a > 0 and b >= a:
                out.extend(range(a, b + 1))
            continue
        # ② 单个：`第3天」「第三天」「第 3 章」「第十五章」「第3章必出」
        # [EN] ② Single: `第3天` `第三天` `第 3 章` `第十五章` `第3章必出`
        m2 = _MUST_ONE_RE.match(part)
        if m2:
            cn = _cn2int(m2.group(1))
            if cn and cn > 0:
                out.append(cn)
            continue
        # ③ 数字在别处（模型写成了「章节3」这种）⇒ 取那个数
        # [EN] ③ The number sits elsewhere (the model wrote something like "章节3") => take it
        m = re.search(r'(\d+)', part)
        if m:
            n = int(m.group(1))
            if n > 0:
                out.append(n)
            continue
        # ④ 纯中文数字（`十五`）
        # [EN] ④ A plain Chinese numeral (`十五`)
        cn = _cn2int(part)
        if cn and cn > 0:
            out.append(cn)
    return tuple(sorted(set(out)))


@dataclass
class SettingItem:
    """一条设定，以及**它什么时候该出场**。

    | 字段 | 意思 |
    |---|---|
    | `layer`  | 属于哪一层（见 `LAYERS`） |
    | `name`   | 一句话是什么（地点名 / 器物名 / 规矩名…） |
    | `text`   | 内容（**要短** —— 长的是设定文档，不是这里该写的） |
    | `when`   | 生效时机：`''`=全程 · `首日` · `第3天` · `第3-5天` · `第3天起` |
    | `where`  | 生效场合：地点名；`''`=哪儿都算 |
    | `who`    | 影响谁：人名；空 = 所有人 |
    | `weight` | 权重 1~5（越大越靠前，也越不容易被额度挤掉） |
    | `source` | `设定集` / `剧组`（剧组那条是**推演中讨论出来的**） |
    | `note`   | 剧组为什么加它（给人看的一行字） |
    
        English:
    One setting, and **when it should appear**.
        | Field | Meaning |
        |---|---|
        | `layer`  | Which layer it belongs to (see `LAYERS`) |
        | `name`   | One-line description (location name / object name / rule name...) |
        | `text`   | Content (**keep it short** -- long ones are setting documents, not what should be written here) |
        | `where`  | Effective occasion: location name; `''`=anywhere counts |
        | `who`    | Whom it affects: person name; empty = everyone |
        | `weight` | Weight 1~5 (larger = further forward, and less likely to be squeezed out by quota) |
        | `note`   | Why the crew added it (a line for humans to read) |
    """

    layer: str
    name: str
    text: str
    when: str = ''
    where: str = ''
    who: tuple[str, ...] = ()
    weight: int = 3
    source: str = '设定集'
    note: str = ''
    # ★★★ 2026-10-27：**「第 N 章必出」**（用户点名）。
    #   起因：细节层是"每天按场合随机抽 4 条"，所以「第 3 章埋的那只壶、
    #   第 8 章才用得上」这种结构在架构上**没法保证** —— 而笑点/伏笔的
    #   "埋—逼—揭"三步恰恰靠这个（见 `MEMORY.md`「幽默不是处境好笑，
    #   是一件私物被情节撞了一下」）。
    #   ⚠ 语义是**保证出场**，不是**限制出场**：
    #     写进 `must_on` 的那一天，这条**绕过场合/在场两道闸**一定出现；
    #     别的日子它照旧按 `when`/`where`/`who` 走（可能被抽到、可能不）。
    #   （写成"限制出场"会让"埋过之后还要再用"变成不可能。）
    # [EN] ★★★ 2026-10-27: **"must appear on chapter N"**. The detail layer samples 4 items per day
    # [EN] by occasion, so "the pot planted in chapter 3 and cashed in chapter 8" was structurally
    # [EN] impossible -- and that is exactly what a joke/foreshadowing needs (plant - force - expose).
    # [EN] ⚠ The semantics are **guaranteed appearance**, not **restricted appearance**: on a day listed in
    # [EN] `must_on` the item **bypasses the occasion/presence gates** and always appears; on other days
    # [EN] it still follows `when`/`where`/`who` (may be sampled, may not).
    must_on: tuple[int, ...] = ()

    # ── 判定 ──
    # [EN] ── Judgment ──
    def when_ok(self, day: int, *, first: bool = False) -> bool:
        """今天该不该出场。（认不出的一律**当生效** —— 见模块头第 4 条。）
                English:
        Whether it should appear today. (Anything unrecognizable is **treated as active** — see item 4
        in the module header.)
        """
        raw = str(self.when or '').strip()
        if not raw:
            return True
        if '首' in raw or '开篇' in raw or '第一天' in raw:
            return bool(first) or int(day) <= 1
        m = _WHEN_RE.match(raw)
        if m:
            a = int(m.group(1))
            b = int(m.group(2)) if m.group(2) else None
            if m.group(3):                      # 「第3天起」
            # [EN] "from day 3 onward"
                return int(day) >= a
            if b is not None:
                return a <= int(day) <= b
            return int(day) == a
        # 认不出 → 当生效（别让作者写的一句话悄悄失效）
        # [EN] Unrecognized → treat as effective (don't let a sentence the author wrote silently fail)
        _LOG.debug('「%s」的生效时机认不出（%r），按"全程生效"处理', self.name, raw)
        return True

    def where_ok(self, scene: str) -> bool:
        """这个场合对不对得上。（任一边为空 = 算对得上，规则**从宽**。）
                English:
        Whether this occasion matches. (Either side empty = counts as matching, rule is **lenient**.)
        """
        w = str(self.where or '').strip()
        s = str(scene or '').strip()
        if not w or not s:
            return True
        return w in s or s in w

    def who_ok(self, people: Iterable[str]) -> bool:
        """场上有没有它影响的人。（`who` 空 = 所有人；`people` 空 = 不筛。）
                English:
        Whether there is anyone it affects on the scene. (`who` empty = everyone; `people` empty = no
        filtering.)
        """
        if not self.who:
            return True
        names = {str(x).strip() for x in (people or []) if str(x).strip()}
        if not names:
            return True
        return bool(set(self.who) & names)

    def active(self, *, day: int, scene: str, people: Iterable[str] = (),
               first: bool = False) -> bool:
        # ★ 2026-10-27：**「必出日」优先于其它闸**。
        #   场合/在场两道闸是"今天用得上吗"，而「必出」是作者写死的"这天一定要有"
        #   —— 后者等级更高（不然"第 3 章必出"的东西在第 3 章没这场戏就被筛掉了，
        #   而那正是它要存在的理由）。
        # [EN] ★ 2026-10-27: **"must appear" outranks the other gates.** The occasion/presence gates ask
        # [EN] "is it useful today", while "must appear" is the author's "it must be here on that day" --
        # [EN] the latter outranks (otherwise the "must appear on chapter 3" item gets filtered out on
        # [EN] chapter 3 precisely because it was needed there).
        if self.must_hit(day):
            return True
        return (self.when_ok(day, first=first)
                and self.where_ok(scene)
                and self.who_ok(people))

    def must_hit(self, day: int) -> bool:
        """今天是不是它的「必出日」。
                English:
        Whether today is one of its "must appear" days.
        """
        if not self.must_on:
            return False
        try:
            return int(day) in self.must_on
        except Exception:                                   # noqa: BLE001
            return False

    # ── 序列化 ──
    # [EN] ── Serialization ──
    def to_dict(self) -> dict:
        return {'层': self.layer, '名称': self.name, '内容': self.text,
                '生效时机': self.when, '场合': self.where,
                '影响谁': list(self.who), '权重': int(self.weight),
                '来源': self.source, '说明': self.note,
                '必出日': list(self.must_on)}

    @classmethod
    def from_dict(cls, d) -> 'SettingItem | None':
        if not isinstance(d, dict):
            return None
        layer = normalize_layer(d.get('层') or d.get('layer') or '')
        if layer not in BY_KEY:
            return None
        name = str(d.get('名称') or d.get('name') or '').strip()
        text = str(d.get('内容') or d.get('text') or '').strip()
        if not (name or text):
            return None
        who = d.get('影响谁') if d.get('影响谁') is not None else d.get('who')
        if isinstance(who, str):
            who = [x for x in re.split(r'[、,，;；\s]+', who) if x]
        try:
            weight = int(d.get('权重') or d.get('weight') or 3)
        except (TypeError, ValueError):
            weight = 3
        _must_raw = None
        for _k in _MUST_KEYS:
            if d.get(_k) is not None:
                _must_raw = d.get(_k)
                break
        return cls(layer=layer, name=name, text=text,
                   when=str(d.get('生效时机') or d.get('when') or '').strip(),
                   where=str(d.get('场合') or d.get('where') or '').strip(),
                   who=tuple(str(x).strip() for x in (who or []) if str(x).strip()),
                   weight=max(1, min(5, weight)),
                   source=str(d.get('来源') or d.get('source') or '设定集'),
                   note=str(d.get('说明') or d.get('note') or '').strip()[:120],
                   must_on=parse_must_on(_must_raw))

    def scope_line(self) -> str:
        """作用范围的一行话（分层设定.md 里那一列）。
                English:
        The one-line description of the scope (that column in 分层设定.md).
        """
        bits = []
        if self.must_on:
            bits.append('第 ' + '、'.join(str(x) for x in self.must_on) + ' 章必出')
        if self.when:
            bits.append(self.when)
        if self.where:
            bits.append(f'限「{self.where}」')
        if self.who:
            bits.append('涉及 ' + '、'.join(self.who[:4]))
        return ' · '.join(bits) if bits else '全程 · 处处'


# ══════════════════════════════════════════════════════════════════════
#  建索引：设定集 → 分层条目
# [EN] Build index: setting collection → layered entries
# ══════════════════════════════════════════════════════════════════════
def _as_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def _text_of(d, *keys) -> str:
    if not isinstance(d, dict):
        return ''
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ''


def _strip_marker(text: str, *names: str) -> str:
    """去掉开头那个 `【世界观】` 之类的标记。

    `sim/setup._worldview_text()` 拼出来的 `worldview_text` 里带 `【世界观】`；
    而 `load_settings` 返回的原文没有。分层渲染自己会加 `[世界观]` 标签 ——
    不去掉的话屏幕上就是 `[世界观] 【世界观】…`，一眼看得出是拼接没收拾干净。
    
        English:
    Remove the leading marker like `【世界观】`.
        The `worldview_text` assembled by `sim/setup._worldview_text()` carries `【世界观】`;
        while the original text returned by `load_settings` does not. Layered rendering adds the `[世界观]` tag itself --
        if not removed, the screen would show `[世界观] 【世界观】…`, and it is obvious at a glance that the concatenation was not cleaned up.
    """
    t = str(text or '').strip()
    for n in names:
        for mark in (f'【{n}】', f'[{n}]', f'# {n}', f'## {n}'):
            if t.startswith(mark):
                return t[len(mark):].strip()
    return t


def _pick(d, *keys, default=None):
    """从一个 dict 里按若干别名取值（**两套键名都要认**）。

    设定有两种形态，键名不一样：

    | 形态 | 谁产出的 | 键名 |
    |---|---|---|
    | **归一后的**（正式输入） | `sim.setup.load_settings()` | `worldview` / `plot` / `places` … |
    | **提取原始件** | `ingest.extractor.extract_settings()` | `世界观` / `剧情参考线` / `地点` … |

    `build_index` 的正式输入是前者（`build_world` 传的就是它）。但把后者也认下来
    几乎不要钱，而**不认的代价是静默的**：整份索引会是空的，表现成
    "分层没生效"，却没有任何报错（第一版给演示页生成样例时就撞上了）。
    
        English:
    Fetch values from a dict by several aliases (**both sets of key names must be recognized**).
        The settings have two forms, with different key names:
        | Form | Who produces it | Key names |
        |---|---|---|
        | **Normalized** (official input) | `sim.setup.load_settings()` | `worldview` / `plot` / `places` ... |
        `build_index`'s official input is the former (`build_world` passes it). But also accepting the latter
        costs almost nothing, and **the cost of not accepting it is silent**: the whole index would be empty,
        manifesting as "layerization not taking effect" with no error at all (hit this in the first version when generating samples for the demo page).
    """
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def build_index(settings: dict, *, local: Iterable[SettingItem] | None = None
                ) -> list[SettingItem]:
    """把设定集（`sim.setup.load_settings` 的那份 dict）编成分层索引。

    **只搬原文、不做概括**（模块头第 3 条）：每个条目的 `text` 要么直接来自
    设定集的结构化字段，要么是它的原话拼接。所以"作者写的那句"能一路走到
    提示词里，中间不会被谁改写一遍。

    人物层不进索引 —— 它由人物卡承载（`Agent._persona_prompt`），
    重复进世界前缀只会让 prompt 变贵。

    键名两套都认（见 `_pick`）：归一后的 `worldview`，以及提取原始件的 `世界观`。
    
        English:
    Compile the settings set (the dict from `sim.setup.load_settings`) into a layered index.
        **Only move the original text, no summarization** (module header rule 3): each entry's `text` either comes directly from
        the settings set's structured fields, or is a concatenation of its original wording. So "the sentence the author wrote" can travel all the way into
        the prompt without being rewritten by anyone in between.
        The character layer does not enter the index -- it is carried by character cards (`Agent._persona_prompt`),
        duplicating it into the world prefix would only make the prompt more expensive.
        Recognize both sets of key names (see `_pick`): the normalized `worldview`, and the extractor raw artifact's `世界观`.
    """
    items: list[SettingItem] = []

    # ── 世界层 ──
    # [EN] ── World layer ──
    wv = str(_pick(settings, 'worldview', '世界观', default='') or '').strip()
    if wv:
        items.append(SettingItem(
            layer='canon', name='世界观', text=_strip_marker(wv, '世界观'),
            weight=5, note='作者写的整体背景'))

    # ── 主线层 ──
    # [EN] ── Mainline layer ──
    plot = _strip_marker(str(_pick(settings, 'plot', '剧情参考线',
                                   '剧情走向', default='') or '').strip(),
                         '剧情参考线', '剧情走向')
    if plot:
        items.append(SettingItem(layer='arc', name='剧情参考线', text=plot,
                                 weight=5, note='起承转合的大纲梗概'))
    for i, nd in enumerate(_as_list(_pick(settings, 'nodes', '故事进度',
                                          default=[]))):
        if not isinstance(nd, dict):
            continue
        nm = _text_of(nd, '名称') or _text_of(nd, 'id')
        if not nm:
            continue
        body = '；'.join(x for x in (_text_of(nd, '概要'),
                                     _text_of(nd, '完成判据')) if x)
        items.append(SettingItem(layer='arc', name=nm, text=body or nm,
                                 weight=max(1, 4 - i // 3),
                                 note='故事进度节点'))
    for i, f in enumerate(_as_list(_pick(settings, 'foreshadows', '伏笔',
                                         default=[]))):
        if not isinstance(f, dict):
            continue
        body = _text_of(f, '内容')
        if not body:
            continue
        items.append(SettingItem(
            layer='arc', name=_text_of(f, '编号') or f'伏笔{i + 1}',
            text=body, weight=2, note='伏笔与悬线'))

    # ── 场景层 ──
    # [EN] ── Scene layer ──
    for p in _as_list(_pick(settings, 'places', '地点', default=[])):
        if not isinstance(p, dict):
            continue
        nm = _text_of(p, '名称')
        if not nm:
            continue
        items.append(SettingItem(
            layer='scene', name=nm, text=_text_of(p, '说明') or nm,
            where=nm, weight=4, note='地点'))
    for r in _as_list(_pick(settings, 'relations', '关系', default=[])):
        if not isinstance(r, dict):
            continue
        a, b = _text_of(r, '甲'), _text_of(r, '乙')
        rel = _text_of(r, '关系')
        if not (a or b):
            continue
        tension = _text_of(r, '张力')
        items.append(SettingItem(
            layer='scene', name=f'{a}—{b}', text=rel or f'{a}与{b}',
            who=tuple(x for x in (a, b) if x), weight=3,
            note='人物关系' + (f'（张力：{tension}）' if tension else '')))

    # ── 细节层 ──
    # [EN] ── Detail layer ──
    for d in _as_list(_pick(settings, 'detail', '细节', default=[])):
        if isinstance(d, str):
            d = {'名称': d, '内容': d}
        if not isinstance(d, dict):
            continue
        nm = _text_of(d, '名称') or _text_of(d, '内容')[:20]
        body = _text_of(d, '内容') or nm
        if not nm and not body:
            continue
        who = _text_of(d, '涉及') or _text_of(d, '人物')
        _must_raw = None
        for _k in _MUST_KEYS:
            if d.get(_k) is not None:
                _must_raw = d.get(_k)
                break
        items.append(SettingItem(
            layer='detail', name=nm, text=body,
            where=_text_of(d, '场合') or _text_of(d, '地点'),
            who=tuple(x for x in re.split(r'[、,，;；\s]+', who) if x),
            weight=3, note='生活细节',
            must_on=parse_must_on(_must_raw)))

    for it in (local or []):
        if isinstance(it, SettingItem):
            items.append(it)
        else:
            got = SettingItem.from_dict(it)
            if got is not None:
                items.append(got)

    # 同层内按权重降序（稳定排序：权重相同的保持原顺序，也就是设定集的顺序）
    # [EN] Within the same layer, sort by weight descending (stable sort: items with the same weight keep
    # [EN] their original order, i.e. the order of the setting collection)
    items.sort(key=lambda x: -int(x.weight))
    return items


# ══════════════════════════════════════════════════════════════════════
#  选：今天这一刻，哪些条目该出场
# [EN] Select: at this moment today, which entries should appear
# ══════════════════════════════════════════════════════════════════════
class LayerView:
    """这一刻生效的条目，按层分好。`render()` 只认它。
        English:
    The entries in effect at this moment, grouped by layer. `render()` only recognizes this.
    """

    def __init__(self, buckets: dict[str, list[SettingItem]] | None = None,
                 *, expand: bool = False, day: int = 1):
        self.buckets: dict[str, list[SettingItem]] = buckets or {}
        self.expand = bool(expand)
        self.day = int(day or 1)

    def get(self, key: str) -> list[SettingItem]:
        return self.buckets.get(str(key)) or []

    def count(self, key: str) -> int:
        return len(self.get(key))

    def total(self) -> int:
        return sum(len(v) for v in self.buckets.values())

    def to_dict(self) -> dict:
        return {'展开大背景': self.expand, '第几天': self.day,
                '各层': {k: [i.to_dict() for i in v]
                        for k, v in self.buckets.items() if v}}


def should_expand(*, day: int, tension: float = 0.0,
                  every: int = EXPAND_EVERY_DAYS) -> bool:
    """这一刻要不要把**大背景展开**（平时只给一句"气候"）。

    三个时机，都是"后台特定的时候"（用户的话）：
      ① **开篇**（第 1 天）—— 故事刚起头，读者/人物得先知道世界什么样；
      ② **高潮日**（张力 ≥ `EXPAND_TENSION`）—— 大事件往往要动到世界级的设定；
      ③ **每 N 天一次**（`EXPAND_EVERY_DAYS`）—— 定期给一次全貌，免得人物
         跑到第十天已经完全忘了自己在哪个世界。

    ★ 做成**纯函数**（只看当天状态，不看"上一次是什么时候"）：`world_prefix()`
      的结果要能缓存，带历史状态的判定会让缓存与调用顺序纠缠在一起
      （同一个世界状态调两次拿到不同结果，那种 bug 最难查）。
    
        English:
    Whether to expand the **big background** at this moment (normally only one line is given,
    "climate").
        Three occasions, all "specific times in the background" (the user's words):
          ① **Opening** (day 1) -- the story is just starting, the reader/character must first know what the world is like;
          ② **Climax day** (tension >= `EXPAND_TENSION`) -- big events often need to touch world-level settings;
          ③ **Once every N days** (`EXPAND_EVERY_DAYS`) -- periodically give a full picture, lest characters
             run to day ten and have completely forgotten which world they are in.
        ★ Make it a **pure function** (only looks at the current day's state, not at "when was the last time"): the result of `world_prefix()`
          must be cacheable; a decision carrying historical state entangles caching with call order
          (calling twice with the same world state gets different results -- that kind of bug is the hardest to track down).
    """
    d = max(1, int(day or 1))
    try:
        t = float(tension or 0.0)
    except (TypeError, ValueError):
        t = 0.0
    n = max(1, int(every or EXPAND_EVERY_DAYS))
    return d <= 1 or t >= EXPAND_TENSION or (d % n == 0)


def select(index: Iterable[SettingItem], *, day: int = 1, scene: str = '',
           people: Iterable[str] = (), tension: float = 0.0,
           expand: bool | None = None, first: bool = False) -> LayerView:
    """按"今天 + 这个场合 + 场上这些人"挑出该出场的条目。
        English:
    Pick the entries that should appear based on "today + this occasion + these people present".
    """
    d = max(1, int(day or 1))
    names = [str(x).strip() for x in (people or []) if str(x).strip()]
    buckets: dict[str, list[SettingItem]] = {}
    for it in (index or []):
        ld = BY_KEY.get(it.layer)
        if ld is None or not ld.in_prefix:
            continue
        # 大背景（世界层）**不受场合限制**（它是整本书的气候），
        # 其余三层都要过场合/人物/时间这三道闸。
        # [EN] The big background (world layer) is **not restricted by occasion** (it is the climate of the
        # [EN] whole book),
        # [EN] the other three layers must pass all three gates of occasion/character/time.
        if it.layer != 'canon' and not it.active(
                day=d, scene=scene, people=names, first=first):
            continue
        if it.layer == 'canon' and not it.when_ok(d, first=first):
            continue
        buckets.setdefault(it.layer, []).append(it)
    if expand is None:
        expand = should_expand(day=d, tension=tension)
    return LayerView(buckets, expand=bool(expand), day=d)


# ══════════════════════════════════════════════════════════════════════
#  渲染：把选出来的条目拼成提示词里的那几段
# [EN] Render: stitch the selected entries into those paragraphs in the prompt
# ══════════════════════════════════════════════════════════════════════
def _clip(text: str, limit: int) -> str:
    t = ' '.join(str(text or '').split())
    if len(t) <= limit:
        return t
    return t[:max(1, limit - 1)].rstrip('，。；、 ') + '…'


def _join(items: list[SettingItem], limit: int, *, each: int = 0) -> str:
    """把条目拼成一段，按额度收口。

    ★ 收口是**整条丢**（不是把最后一条截半句）—— 半句话进提示词比少一条更坏
      （模型会当它是个完整的信息）。这条与 `display/dividers` 的"整段丢弃"同源。
    
        English:
    Assemble the entries into a paragraph, cut off by quota.
        ★ The cutoff is **dropping the whole entry** (not truncating the last entry mid-sentence) -- half a sentence in the prompt is worse than one fewer entry
          (the model treats it as complete information). This is the same origin as `display/dividers`'s "drop the whole paragraph".
    """
    out: list[str] = []
    used = 0
    for it in items:
        body = _clip(it.text, each) if each else _clip(it.text, limit)
        if not body:
            continue
        # 名字已经在正文开头了就不重复一遍（"临河茶肆：临河茶肆是…"读起来像结巴）
        # [EN] If the name is already at the start of the body text, don't repeat it ("临河茶肆: 临河茶肆是…" reads like
        # [EN] a stutter)
        if not it.name or body.startswith(it.name):
            piece = body
        else:
            piece = f'{it.name}：{body}'
        add = len(piece) + (1 if out else 0)
        if out and used + add > limit:
            break
        out.append(piece)
        used += add
    return '；'.join(out)


def render(view: LayerView, *, include: Iterable[str] = ('canon', 'arc',
                                                         'scene', 'detail')
           ) -> str:
    """把这一刻的分层视图渲染成提示词的几行。

    ⚠ **`[世界观]` 这个标签不许改** —— 五支验证脚本与几处解析都靠它
      （`verify_world_rules` / `verify_sim_prompt` / `verify_film_style`）。
      分层改的是"给它多少字"，不是"它叫什么"。
    
        English:
    Render this moment's layered view into a few lines of the prompt.
        ⚠ **The `[世界观]` tag must not be changed** -- five verification scripts and several parsers rely on it
          (`verify_world_rules` / `verify_sim_prompt` / `verify_film_style`).
          Layerization changes "how many characters it is given", not "what it is called".
    """
    keep = set(include)
    parts: list[str] = []
    for ld in LAYERS:
        if ld.key not in keep or not ld.in_prefix:
            continue
        items = view.get(ld.key)
        if not items:
            continue
        if ld.key == 'canon':
            cap = ld.full if view.expand else ld.brief
            parts.append(f'[世界观] {_clip("".join(i.text for i in items), cap)}')
        elif ld.key == 'arc':
            parts.append(f'[主线] {_join(items, ld.full)}')
        elif ld.key == 'scene':
            parts.append(f'[此处] {_join(items, ld.full)}')
        elif ld.key == 'detail':
            # ★★★ 2026-10-27：「必出日」的那几条**排最前**。
            #   为什么不能放在原来的位置（按权重）：细节层的**条数上限 4** 与
            #   **字符额度 260** 是两道闸（4×70=280 > 260 ⇒ 第四条本来就被挤掉）。
            #   一条"第 3 章必出的那只壶"若排在第 5 位，它会被额度挤掉 ——
            #   而这一章正是要埋它的那一章 ⇒ 埋了，后文就再也收不回来。
            # [EN] ★★★ 2026-10-27: **the "must appear" items go first**. They cannot stay in their
            # [EN] original (weight-ordered) position: the detail layer has **two** gates (max 4 items
            # [EN] AND a 260-char quota; 4x70=280 > 260 so the 4th item was already being dropped).
            # [EN] A "the pot that must appear on chapter 3" sitting in 5th place gets squeezed out --
            # [EN] and that is precisely the chapter where it was meant to be planted, so it would never
            # [EN] be cashed in later.
            _must = [i for i in items if i.must_hit(view.day)]
            _rest = [i for i in items if not i.must_hit(view.day)]
            _ordered = (_must + _rest)[:DETAIL_MAX_ITEMS]
            parts.append('[小事] ' + _join(_ordered, ld.full, each=DETAIL_EACH))
    return '\n'.join(p for p in parts if p.strip())


def prefix_block(index: Iterable[SettingItem], *, day: int = 1, scene: str = '',
                 people: Iterable[str] = (), tension: float = 0.0,
                 first: bool = False) -> tuple[str, LayerView]:
    """一处搞定：选 + 渲染。返回 `(提示词那几行, 这一刻的视图)`。

    `sim/setup` 与 `WorldState.world_prefix()` 共用它 —— 免得两处各选一遍、
    选法不一致（那会表现成"界面上写的和模型看到的不是一回事"）。
    
        English:
    All in one place: select + render. Returns `(the prompt lines, this moment's view)`.
        `sim/setup` and `WorldState.world_prefix()` share it -- to avoid both places selecting separately
        with inconsistent selection (which would manifest as "what's written in the UI and what the model sees are not the same thing").
    """
    view = select(index, day=day, scene=scene, people=people,
                  tension=tension, first=first)
    return render(view), view


# ══════════════════════════════════════════════════════════════════════
#  剧组写入闸门：新设定**不许碰总体设定**
# [EN] Crew write gate: new settings **must not touch the overall setting**
# ══════════════════════════════════════════════════════════════════════
#: 局部设定的内容上限。写长了就不是"一句话的小设定"，而是一篇设定文档 ——
#: 那属于作者的活（改引用文件夹），不该由推演过程塞进来。
# [EN] : content limit for local settings. If written too long, it is no longer a "one-sentence small
# [EN] setting" but a setting document ——
# [EN] : that is the author's job (edit the reference folder), and should not be stuffed in by the
# [EN] deduction process.
DETAIL_MAX_CHARS = DETAIL_EACH * 3
#: 一次会审最多收几条（多了就成了"剧组在替作者写设定集"）
# [EN] : max number of items accepted per review session (more than that becomes "the crew writing the
# [EN] setting collection for the author")
MAX_NEW_PER_ROUND = 4


def why_reject(it: SettingItem, existing: Iterable[tuple[str, str]] | None = None
               ) -> str:
    """这条新设定为什么不能收（空串 = 能收）。

    四道闸，每一道都对应一句用户的话：

    ① **层**：`CREW_WRITABLE` 之外一律拒 —— 用户说「不能够影响总体设定」。
       世界层/主线层是作者的"总体设定"，剧组连新增都不行。
    ② **内容**：空的、或者长得像设定文档的，拒。
    ③ **作用范围**：既不限地点、也不限人、也不限时间的，等于"处处时时生效"
       —— 那就是在改总体设定，只是换了个写法的说法。**必须至少有一样**。
    ④ **重名**：作者（或前几天的会审）已经写过同名同层的东西，不收。
       ⚠ 这一条不做的话，界面上会写"新增 2 条"，而其中一条只是把作者写过的话
         又说了一遍 —— **台账在说假话**（比不补更坏）。
    
        English:
    Why this new setting cannot be accepted (empty string = can be accepted).
        Four gates, each corresponding to a sentence from the user:
        ① **Layer**: anything outside `CREW_WRITABLE` is rejected outright -- the user said "must not be able to affect the overall setting".
           The world layer / mainline layer are the author's "overall setting", the crew cannot even add to them.
        ② **Content**: empty, or something that looks like a settings document, reject.
        ③ **Scope**: something that limits neither place, nor person, nor time equals "in effect everywhere and always"
           -- that is changing the overall setting, just phrased differently. **At least one must be present**.
        ④ **Duplicate name**: the author (or an earlier day's review) has already written something with the same name and same layer, do not accept.
           ⚠ If this rule is not implemented, the UI will say "2 new entries added", while one of them is just repeating what the author already wrote
             -- **the ledger is lying** (worse than not adding it at all).
    """
    if not isinstance(it, SettingItem):
        return '不是一条设定'
    if it.layer not in BY_KEY:
        return f'认不出是哪一层（{it.layer!r}）—— 只能新增 {crew_writable_names()}'
    if it.layer not in CREW_WRITABLE:
        return (f'「{layer_name(it.layer)}」是作者的总体设定，剧组不能动 '
                f'—— 只能新增 {crew_writable_names()}')
    if not str(it.text or '').strip():
        return '内容是空的'
    if len(str(it.text)) > DETAIL_MAX_CHARS:
        return f'太长（超过 {DETAIL_MAX_CHARS} 字）—— 局部设定要短'
    if not (str(it.when or '').strip() or str(it.where or '').strip() or it.who):
        return '没有作用范围（既不限地点、也不限人、也不限时间）—— 那就等于改总体设定'
    if existing and (it.layer, it.name) in set(existing):
        return '已经写过这一条了（与现有设定重名同层）'
    return ''


def admit_new(raw_items: Iterable[Any], *, day: int = 1,
              existing: Iterable[tuple[str, str]] | None = None
              ) -> tuple[list[SettingItem], list[tuple[SettingItem, str]]]:
    """把剧组讨论出来的新设定过一遍闸门。

    返回 `(收下的, [(被拒的, 原因)])`。**被拒的要带上原因** —— 界面/日志里
    静默丢掉的话，表现成"剧组说了半天什么都没发生"，而真正的原因
    （比如"它想改世界层"）就永远查不出来。

    `existing` = 现在已经有的 `(层, 名)` 集合（设定集 + 前几天收下的）。
    
        English:
    Run the new settings discussed by the crew through the gates.
        Return `(accepted, [(rejected, reason)])`. **Rejected items must carry a reason** — in the UI/log
        if silently dropped, it looks like "the crew talked for ages and nothing happened", while the real reason
        (e.g. "it wanted to modify the world layer") can never be traced.
        `existing` = the set of `(layer, name)` that currently exist (setting collection + those accepted in previous days).
    """
    accepted: list[SettingItem] = []
    rejected: list[tuple[SettingItem, str]] = []
    have = set(existing or ())
    for raw in (raw_items or []):
        if isinstance(raw, SettingItem):
            it = raw
        else:
            it = SettingItem.from_dict(raw)
            if it is None:
                # ★ **读不出来的也要报一声**。第一版这里是 `continue`（静默丢），
                #   而模型写错一个字段名（"层"写成"层级"）就会整条消失 ——
                #   表现成"剧组讨论了半天什么都没发生"，原因却查不到。
                # [EN] ★ **Unreadable items must also be reported**. In the first version this was `continue` here
                # [EN] (silent drop),
                # [EN] and if the model writes a field name wrong ("层" written as "层级") the whole item disappears ——
                # [EN] manifesting as "the crew discussed for ages and nothing happened", and the cause cannot be
                # [EN] found.
                if isinstance(raw, dict) and raw:
                    ghost = SettingItem(
                        layer=str(raw.get('层') or raw.get('层级')
                                  or raw.get('layer') or ''),
                        name=str(raw.get('名称') or raw.get('name') or '（没名字）'),
                        text=str(raw.get('内容') or raw.get('text') or ''))
                    rejected.append((ghost, why_reject(ghost) or '这一条读不出来'))
                continue
        it.source = '剧组'
        why = why_reject(it, existing=have)
        if why:
            rejected.append((it, why))
            continue
        if len(accepted) >= MAX_NEW_PER_ROUND:
            rejected.append((it, f'这一轮最多收 {MAX_NEW_PER_ROUND} 条'))
            continue
        accepted.append(it)
        have.add((it.layer, it.name))       # 同一轮里也不许重复
        # [EN] No duplicates within the same round either
    return accepted, rejected


def add_local(world, items: Iterable[SettingItem]) -> int:
    """把收下的新设定挂到世界上（**只进 `local_settings`，绝不并进设定集**）。

    这是"不能够影响总体设定"的结构保证：`worldview_text` / `rules_text` /
    `people` 一个字都不动，新设定活在另一个列表里，只在渲染时按层拼进来。
    
        English:
    Attach the accepted new settings to the world (**only into `local_settings`, never merge into
    the setting collection**).
        This is the structural guarantee of "cannot affect the overall settings": `worldview_text` / `rules_text` /
        `people` are not touched at all; new settings live in a separate list and are only assembled in by layer at render time.
    """
    bucket = getattr(world, 'local_settings', None)
    if bucket is None:
        bucket = []
        try:
            world.local_settings = bucket
        except Exception:                                        # noqa: BLE001
            return 0
    have = {(i.layer, i.name) for i in bucket if isinstance(i, SettingItem)}
    n = 0
    for it in (items or []):
        if not isinstance(it, SettingItem):
            continue
        if (it.layer, it.name) in have:              # 同名同层只留一条
        # [EN] Same name and same layer keeps only one
            continue
        bucket.append(it)
        have.add((it.layer, it.name))
        n += 1
    if n:
        # 索引要重建（`world_prefix` 读的就是它）—— 并让缓存失效
        # [EN] The index must be rebuilt (that's what `world_prefix` reads) —— and invalidate the cache
        try:
            world.rebuild_layers()
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('重建分层索引失败（新设定这一拍可能还没生效）：%r', e)
    return n


# ══════════════════════════════════════════════════════════════════════
#  落盘 / 读回（**只写运行文件夹**）
# [EN] Persist / read back (**only write to the run folder**)
# ══════════════════════════════════════════════════════════════════════
def profile_md(index: Iterable[SettingItem], *, day: int = 1,
               extra_header: str = '') -> str:
    """`分层设定.md`：把"每一层有哪些设定、什么时候出场、影响谁"摊开给人看。

    ★ 这就是用户要的"你心里要清楚"的**可见版本** —— 作者翻这一页就知道
      程序把哪句话安排在什么时候用、权重多高。以及"想改哪一层去动哪个文件"。
    
        English:
    `分层设定.md`: lay out "what settings each layer has, when they appear, whom they affect" for humans
    to see.
        ★ This is the **visible version** of the "you must be clear in your head" the user asked for — the author flipping through this page knows
          at what time the program schedules which line for use, and how high the weight is. And "to change which layer, edit which file".
    """
    lines = ['# 分层设定', '',
             '> 设定按**作用范围**分成五层。大背景平时只当"气候"，'
             '只在开篇 / 高潮日 / 每 3 天这些**特定的时候**展开；'
             '每天的故事多半由「细节层」里的小设定推动。', '']
    if extra_header:
        lines += [extra_header, '']
    lines += ['| 层 | 是什么 | 什么时候出场 | 谁有权写 | 设定文件 |',
              '|---|---|---|---|---|']
    for ld in LAYERS:
        src = '、'.join(f'`{x}`' for x in LAYER_SOURCES.get(ld.key, ()))
        lines.append(f'| **{ld.name}** | {ld.duty} | {ld.expand} | '
                     f'{ld.writer} | {src} |')
    lines += ['', f'> 当前第 {int(day or 1)} 天。'
                  f'下面按层列出**已经编进索引**的每一条。', '']

    for ld in LAYERS:
        rows = [i for i in (index or []) if i.layer == ld.key]
        lines.append(f'## {ld.name}（{len(rows)} 条）')
        if not rows:
            lines += ['（这一层还没有内容）', '']
            continue
        lines += ['| 名称 | 内容 | 作用范围 | 权重 | 来源 |',
                  '|---|---|---|---|---|']
        for it in rows:
            body = ' '.join(str(it.text or '').split()).replace('|', '/')
            lines.append(f'| {it.name} | {body[:70]} | {it.scope_line()} | '
                         f'{int(it.weight)} | {it.source} |')
        lines.append('')
    return '\n'.join(lines) + '\n'


def save_profile(run_dir, index: Iterable[SettingItem], *, day: int = 1,
                 extra_header: str = '') -> None:
    """把分层索引落进运行文件夹（`.yaml` 给程序读、`.md` 给人看）。
        English:
    Write the layered index into the run folder (`.yaml` for the program to read, `.md` for humans
    to read).
    """
    if run_dir is None:
        return
    try:
        root = Path(run_dir)
        items = [i.to_dict() for i in (index or [])]
        data = {'第几天': int(day or 1),
                '层': [{'键': l.key, '名': l.name, '说明': l.duty,
                        '何时出场': l.expand, '谁有权写': l.writer,
                        '常态额度': l.brief, '展开额度': l.full,
                        '设定文件': list(LAYER_SOURCES.get(l.key, ()))}
                       for l in LAYERS],
                '条目': items}
        import yaml
        (root / FILE_PROFILE_YAML).write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False,
                      sort_keys=False), encoding='utf-8')
        (root / FILE_PROFILE_MD).write_text(
            profile_md(index, day=day, extra_header=extra_header),
            encoding='utf-8')
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('分层设定落盘失败（不影响推演）：%r', e)


def save_local(run_dir, world) -> None:
    """把剧组新增的局部设定落一份（**只写运行文件夹**）。
        English:
    Write a copy of the crew's newly added local settings (**only into the run folder**).
    """
    if run_dir is None:
        return
    try:
        root = Path(run_dir)
        items = [i for i in (getattr(world, 'local_settings', None) or [])
                 if isinstance(i, SettingItem)]
        (root / FILE_LOCAL_JSON).write_text(
            json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2),
            encoding='utf-8')
        lines = ['# 临时设定（剧组会审新增）', '',
                 '> 这些是**推演过程中**导演 / 小说作家 / 剧作者讨论出来的**局部**设定，',
                 '> 只在它们各自的作用范围里生效。**它们没有写进你的设定集** ——',
                 '> 想让某一条变成正式设定，照着它改你的引用文件夹就行。', '']
        if not items:
            lines.append('（还没有新增过 —— 作者原本的设定已经够了）')
        else:
            lines += ['| 名称 | 层 | 内容 | 作用范围 | 为什么加 |',
                      '|---|---|---|---|---|']
            for it in items:
                body = ' '.join(str(it.text or '').split()).replace('|', '/')
                why = ' '.join(str(it.note or '').split()).replace('|', '/')
                lines.append(f'| {it.name} | {layer_name(it.layer)} | '
                             f'{body[:60]} | {it.scope_line()} | {why[:40]} |')
        (root / FILE_LOCAL_MD).write_text('\n'.join(lines) + '\n',
                                          encoding='utf-8')
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('临时设定落盘失败（不影响推演）：%r', e)


def load_local(run_dir) -> list[SettingItem]:
    """读回上一次推演留下的局部设定（同一轮续跑时用）。坏文件当没有。
        English:
    Read back the local settings left by the previous inference (used when continuing the same
    round). Treat bad files as absent.
    """
    if run_dir is None:
        return []
    try:
        f = Path(run_dir) / FILE_LOCAL_JSON
        if not f.exists():
            return []
        data = json.loads(f.read_text(encoding='utf-8'))
    except Exception:                                            # noqa: BLE001
        return []
    out: list[SettingItem] = []
    for d in (data if isinstance(data, list) else []):
        it = SettingItem.from_dict(d)
        if it is not None:
            it.source = '剧组'
            out.append(it)
    return out
