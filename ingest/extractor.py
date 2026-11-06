# -*- coding: utf-8 -*-
"""设定提取：把扫描到的文档交给 LLM，输出结构化设定集（设计稿 §3.1）。

输出 JSON：
{
  "人物": [{"姓名", "身份", "简介", "性格", "口癖", "说话指纹", "秘密", "目标", "红线"}],
  "世界观": "...",
  "地点": [{"名称", "说明"}],
  "关系": [{"甲", "乙", "关系", "张力"}],
  "伏笔": [{"编号", "内容", "埋设", "预计回收"}],
  "剧情参考线": "起...承...转...合...",
  "顶级规则": ["作者写死的硬规则，每条一句话"],
  "细节": [{"名称", "内容", "场合", "涉及", "必出日"}]      ← 细节层素材（2026-10-07 加；「必出日」2026-10-27 加）
}

English:
Setting extraction: hand the scanned documents to the LLM, output a structured setting
collection (design doc §3.1).
Output JSON:
{
  "世界观": "...",
  "顶级规则": ["hard rules written by the author, one sentence each"],
}
"""
from __future__ import annotations

import json
import re
from typing import Any

from llm.router import llm
from ingest.scanner import FileItem
from util.jsonio import extract_json, repair_json
from util.text import fill

_LOG = __import__("logging").getLogger("nws.ingest")

# 提示词外置前，先内联（prompts/ 热重载留 M4）
# [EN] Before externalizing prompts, inline them first (prompts/ hot reload is deferred to M4)
_PROMPT = """你是一位小说设定提取专家。下面是一份小说项目的全部文档文本。请从中提取以下结构化信息：

1. **人物**（数组）：每个角色包含字段 ——
   - 姓名、身份、简介（一句话）、性格、口癖（可空）、说话指纹（可空）、
     秘密（可空）、目标（可空）、红线（行为边界，可空）
   - `说话指纹`（★★ 2026-10-28 新增）：这个人**一开口就躲不掉的四件事**，
     用「；」隔开写成四条，每条都要**能照着做**：
     ① 句子多长（"一句不超过十个字"／"一急就连着三十个字"）；
     ② 嘴上的抓手（爱用反问／爱让人先坐／爱把话说一半）；
     ③ 心虚时手上干什么（摸烟袋／擦桌子／把碗推远）；
     ④ 对谁换称呼（叫她"阿六"、叫他"东家"、对陌生人只喊"客官"）。
     ⚠ **不许写形容词**（"说话冷淡""语气温和"）—— 形容词没法执行，
       模型只会把它翻译成"客气、完整、有礼貌"，那正是要治的病。
     ⚠ 同一本书里，两个人物的这四条**至少要有一条互不相同**，
       否则遮住名字就分不出谁在说。文档里没写就留空字符串，**不要编**。
   - 若文档未明确说明某字段，根据上下文合理推断，但把「可空」字段留空字符串，不要编造。
2. **世界观**（字符串）：整体背景描述，2~4 句话。
3. **地点**（数组）：每个地点 {名称, 说明, 方位, 内里}。
   - `说明` ≤20 字，写**能用的信息**（几层、有什么、什么时候热闹）；
   - `方位`（可空，≤30 字）：它在**哪一带、挨着什么**（如"临着河，在渡口西边"）。
     文档里没说就留空 —— **不要编**；
   - `内里`（可空，字符串数组）：这处**里面的房间与器物**
     （如 ["堂屋", "后院", "井"]）。同样只在文档提到时才写。
   这两个字段是给**地图底图**用的（开卷时照着它画整体/局部/室内三级底图）。
4. **关系**（数组）：每条 {甲, 乙, 关系, 张力}。**最多 16 条**（2026-10-27 从 8 放宽：
   实测设定集写了 15 条，只吐 8 条 ⇒ 反派单独写的那 4 条只剩下 1 条）。
5. **伏笔**（数组）：每条 {编号, 内容, 埋设, 预计回收}。若文档无伏笔，留空数组。
6. **剧情参考线**（字符串）：用「起...承...转...合...」格式给出大纲梗概。
7. **顶级规则**（数组）：**作者明确写出来的**、约束整个世界或整本书的硬规则 ——
   世界观铁律（什么绝不会发生）、禁忌（谁都不能碰的事）、写作守则（视角 / 章法 / 不允许的写法）。
   每条一句话、**≤ 30 字**，最多 6 条；用作者的原话，不要改写、不要归纳成抽象原则。
   ⚠ **只提取文档里明说的**。文档没写就留空数组 —— **绝对不要自己发明规则**
   （编出来的规则会变成推演时不可违背的约束，比漏掉更糟）。
8. **细节**（数组）：文档里那些**小的、具体的、能落到某场戏上的**设定 ——
   器物（那把缺角的紫砂壶）、习俗与规矩（更漏只许校一次）、口头禅、称呼、
   本地风物（河上几更过船）、某个人的小习惯。每条 {名称, 内容, 场合, 涉及, 必出日}：
   - `名称` ≤ 20 字（"缺角的紫砂壶"），`内容` ≤ 70 字，说清它**是什么、有什么用**；
   - `场合` ≤ 20 字：这条设定在**哪儿**才用得上（地点名；说不清就留空字符串）；
   - `涉及` ≤ 40 字：牵到谁（人名，多个用「、」隔开；没有就留空字符串）；
   - `必出日`：可选，**章号数字或数字串**（如 `3` 或 `"3,7,12"`）——
     写清楚"这条**第几章一定要出现**"。文档里明说了"第 3 章他才把那把壶拿出来"
     就填 `3`；文档没说明白就**留空字符串**（不许自己推）。
     ⚠ 这一栏是**"埋—逼—揭"那种跨章结构唯一的程序保证**：细节层平时是
       "每天按场合抽几条"，不写这一栏，一个"第 3 章埋、第 8 章才用上"的东西
       在架构上**没法保证**（今天抽到这条、明天抽到别的）。填了就一定在那天出现。
   ★ 这一项**不是**概括——它要的是**原文里写过的具体东西**。文档里没有就留空数组。
   ★★ **最多 20 条，而且必须按类别铺开**（2026-10-27 改）。
      ⚠ 以前要求"挑最具体的 8 条"，结果是**整类消失**：实测一份写了 30 条
      （器物 7 / 规矩 6 / 口癖 5 / 客人讲究 6 / 忌讳 6）的设定集，进来的 8 条里
      "客人讲究"与"忌讳"两整类**一条都没有** —— 而那两类正是日常戏最用得上的。
      所以现在：**先分类，每类都挑几条**，再在类内挑最具体的；
      宁可 12 条分在五类，也不要 8 条全挤在一类里。
   ⚠ 与「世界观」的分工：世界观是**背景**（这世道是什么样），细节是**能演的东西**
   （戏里真的会出现的那件东西 / 那条规矩）。同一句话两边都写没有意义。

★ **每个字段都要短**（这是硬要求，不是风格偏好）—— 这份 JSON 有输出长度上限，
写太长会被**截断在半句话里**，整份设定就废了。所以：
   - 简介、性格、身份：**各 ≤ 30 字**，提炼要点，不要成段转述原文；
   - 说话指纹：**≤ 40 字**（四条，每条不超过十个字）；
   - 秘密、目标、红线：**各 ≤ 40 字**；
   - 世界观 ≤ 120 字；地点说明 ≤ 20 字；
   - 关系**最多 16 条**、伏笔**最多 8 条**，每条 ≤ 25 字；
   - 顶级规则最多 6 条，每条 ≤ 30 字；细节**最多 20 条**，内容 ≤ 70 字。
   - 不要复述原文句子，不要写"（原文第 N 章提到…）"这类出处。

请严格以 JSON 对象回答，不要包含解释或其他文字。JSON 的顶层 key 必须是：
{"人物": [...], "世界观": "...", "地点": [...], "关系": [...], "伏笔": [...], "剧情参考线": "...", "顶级规则": [...], "细节": [...]}

下面是文档内容：
---
{content}
---
"""

# 上一次被截断之后的"重来一次"提示：**明确要求更短**。
# [EN] The "try again" prompt after the previous truncation: **explicitly require it to be shorter**.
_SHORTER_HINT = (
    "上一次的回答因为太长被截断了。请**重新输出完整的 JSON**，并大幅压缩："
    "每个人物只保留 姓名 / 身份 / 简介 / 性格 四个字段（其余可空字符串），"
    "每个字段不超过 20 字；世界观不超过 80 字；地点最多 5 条"
    "（地点只留 名称 与 说明，方位 留空、内里 给空数组即可）；"
    "关系最多 5 条；伏笔最多 5 条；顶级规则最多 3 条；细节最多 4 条。"
    "务必保证 JSON **完整闭合、可被解析**。")

# 最大注入内容（字），防止超上下文
# [EN] Max injected content (characters), to prevent exceeding context
#
# ★★ 2026-10-27 从 12000 提到 20000 —— 12000 是**按"一份设定集只有几份文档"定的**，
#    而真到素材齐全的项目（设定 + 人物 + 伏笔 + 规则 + 素材 ≈ 2 万字）就装不下：
#    实测 36 个文件 94,118 字挤进 12000 字窗口，`truncate_mid` 掐头留尾之后
#    **世界观 / 七张人物卡 / 伏笔 / 地点 一份都没剩下**（留下的只有根目录的
#    说明书和地图册末尾两页）。那不是"少看了一点"，是**设定集整个做残了**。
#    配套的三件事（都在本文件里）：`pick_for_extract` 把**另有专门用途**的内容
#    挡在窗口外、`_build_content` 按重要性**整份取舍**而不是切半截、
#    装不下时 `_note` 说清跳过了哪几份（作者能在界面日志里看见）。
#    20000 字约 1.5 万 token，仍在各家模型的安全区；真正要防的是**输出**超上限
#    （`_MAX_OUT_TOKENS`），那个没动。
# [EN] ★★ Raised from 12000 to 20000 on 2026-10-27 -- 12000 was **set assuming a setting collection
# [EN] is only a few documents**,
# [EN] and it no longer fits a project with the full set of material (settings + characters +
# [EN] + material ≈ 20,000 chars):
# [EN] measured 36 files / 94,118 chars squeezed into a 12,000-char window, and after
# [EN] `truncate_mid` cut head-and-kept-tail,
# [EN] **not one of the worldview / seven character cards / foreshadowing / locations survived** (only
# [EN] the root readme and the last two map-book pages remained).
# [EN] That is not "seeing a bit less", it is the **whole setting collection being crippled**.
# [EN] The three things that go with it (all in this file): `pick_for_extract` keeps content that
# [EN] **has its own dedicated path** out of the window,
# [EN] `_build_content` drops **whole files** by importance instead of cutting one in half,
# [EN] and when it doesn't fit, `_note` says which files were skipped (visible to the author in the UI log).
# [EN] 20,000 chars ≈ 15k tokens, still in the safe zone for every model; what really needs guarding
# [EN] is **output** exceeding the limit (`_MAX_OUT_TOKENS`), which is untouched.
_MAX_CONTENT = 20000

# ★ 输出的 token 上限（2026-10-06 从 3000 提上来）。
#   原来 3000 是**真的不够**：这份 JSON 要装下所有人物 + 世界观 + 地点 + 关系 + 伏笔，
#   而用户那份设定里单个人物的"身份/秘密/目标"就是上百字。实测那次正好撞到 3000
#   被截在半句话里（`finish_reason=length`），整份设定降级成空骨架。
#   配合提示词里的"字段要短"，8000 留了足够的余量；真再撞上也有截断检测 + 抢救兜底。
# [EN] ★ Output token limit (raised from 3000 on 2026-10-06).
# [EN] 3000 was originally **really not enough**: this JSON has to hold all characters + worldview +
# [EN] locations + relationships + foreshadowing,
# [EN] and in the user's setting, a single character's "identity/secret/goal" alone is hundreds of
# [EN] characters. In that measured run it hit exactly 3000
# [EN] and got cut off mid-sentence (`finish_reason=length`), degrading the entire setting to an empty
# [EN] skeleton.
# [EN] Together with the "keep fields short" in the prompt, 8000 leaves ample margin; if it really hits
# [EN] the limit again there's truncation detection + salvage fallback.
#
# ★ 2026-10-27 从 8000 提到 12000：细节 8→20 条、关系 8→16 条之后，
#   满配（7 人物 + 12 地点 + 20 细节 × 每条约 150 字 + 16 关系）按中文估
#   **6000~8000 token**，正好压在 8000 这条线上 —— 一撞线就走"重来一次，
#   大幅压缩"那条路（细节只剩 4 条、关系只剩 5 条），**等于这次放宽白做**，
#   而且症状看起来是"模型不肯多写"，很难怀疑到上限。
#   12000 仍在各家模型的安全区（真正要防的是**输出**超上限，这条就是）。
# [EN] ★ Raised 8000 -> 12000 on 2026-10-27: after details 8->20 and relations 8->16, a full load
# [EN] (7 characters + 12 places + 20 details x ~150 chars + 16 relations) estimates at
# [EN] **6000-8000 tokens** for Chinese -- right on the 8000 line. Hitting it triggers "try again,
# [EN] compress hard" (details down to 4, relations down to 5), which **cancels this very change**,
# [EN] and the symptom reads as "the model won't write more", so the cap is the last thing suspected.
# [EN] 12000 is still in every model's safe zone (what must be guarded is **output** exceeding the
# [EN] cap -- this is that cap).
_MAX_OUT_TOKENS = 12000

# 截断时重试用几倍的上限
# [EN] How many times the limit to use on retry when truncated
_RETRY_FACTOR = 2

# 这次提取攒下的提示（截断/抢救之类）。**用完取走**（`take_notes()`），
# 由 `ingest.pipeline` 折进 `extract_done` 那行日志，用户才看得见。
# [EN] Prompts accumulated during this extraction (truncation/salvage, etc.). **Take them once used**
# [EN] (`take_notes()`),
# [EN] folded into the `extract_done` log line by `ingest.pipeline`, so the user can see them.
#
# ⚠ 为什么不做进返回的设定 dict：那份 dict 会被逐字冻结进项目、被校验、被推演逐字段读，
#   **多一个 key 就多一份要维护的契约**。这些提示只跟"这一次调用"有关，不该进档案。
# [EN] ⚠ Why not put them into the returned setting dict: that dict gets frozen verbatim into the
# [EN] project, validated, and read field-by-field by inference,
# [EN] **every extra key is one more contract to maintain**. These notes only relate to "this one call"
# [EN] and should not go into the archive.
_NOTES: list[str] = []


def take_notes() -> list[str]:
    """取走并清空这次提取攒下的提示。
        English:
    Take and clear the notes accumulated during this extraction.
    """
    out = list(_NOTES)
    _NOTES.clear()
    return out


def _note(msg: str) -> None:
    _NOTES.append(msg)
    _LOG.warning("%s", msg)


#: 进「设定提取窗口」的类别。**正文 / 大纲 不进** ——
#: 它们各有专门去处（正文 → `novel_text` 走文风样本，大纲 → `outline_text` 走
#: `ingest/progress` 拆节点），来这儿只是挤掉真正要提取的东西。
#: 「杂项」**不排除**：文件名没有类别词不等于不重要（作者那份 `写作底料_明清山东.md`
#: 就是靠 `.nws_classify.json` 标成设定的），排除它会静默丢东西。
# [EN] : Categories allowed into the "setting extraction window". **Body text / outline are excluded** --
# [EN] each has its own destination (body -> `novel_text` for style samples, outline -> `outline_text`
# [EN] for `ingest/progress` node splitting);
# [EN] coming here only squeezes out what actually needs extracting.
# [EN] "Misc" is **not excluded**: a filename without a category word does not mean unimportant (the
# [EN] author's `写作底料_明清山东.md` is marked as a setting via `.nws_classify.json`), excluding it
# [EN] would silently lose things.
_EXTRACT_KEEP_CATS: tuple[str, ...] = ("规则", "人物", "伏笔", "设定", "杂项")

#: 只服务别的环节、**不进**设定提取窗口的目录名（按目录名判，不看类别 ——
#: 地图册里的文件名都带「设定」，按类别分不开）。
# [EN] : Directory names that serve other stages only and do **not** enter the setting extraction
# [EN] window (judged by directory name, not category --
# [EN] every filename in the map book contains "setting", so categories cannot separate them).
_EXTRACT_SKIP_PARTS: frozenset[str] = frozenset({"06_地图", "写作参考"})

#: 类别内部的先后顺序：规则最要紧，说明书/记录/素材垫后
#: （超限时先砍垫后的，不砍人物卡和世界观）。
# [EN] : Order within a category: rules matter most, readme/logs/material last
# [EN] (when over the limit, cut the last ones first, not character cards and the worldview).
_CAT_ORDER: dict[str, int] = {"规则": 0, "人物": 1, "伏笔": 2, "设定": 3, "杂项": 4}

#: 同类里排后面的名字特征（给人看的说明、程序写的记录、背景素材）
# [EN] : Name traits that sort last within a category (readme for humans, program-written logs,
# [EN] background material)
_LAST_IN_CAT: tuple[str, ...] = ("说明", "记录", "底料", "样章")


def pick_for_extract(items: list[FileItem]) -> list[FileItem]:
    """挑出进「设定提取窗口」的文件，**按重要性排序**（装不下时砍最后面的）。

    ★ 2026-10-27 加。以前是 `extract_settings(items)` 拿全量文件去拼，
    于是 `06_地图`（3.6 万字，只服务画图）和 `写作参考`（1.8 万字，只给人看）
    跟世界观抢同一份窗口，而裁剪又是**按位置**掐头留尾的 ——
    拼在最前面的根目录说明、拼在最后面的地图册留下来了，**中间的人物卡全没了**。
    现在：先按用途挡掉一批，剩下的按「规则 → 人物 → 伏笔 → 设定 → 杂项」排好，
    再由 `_build_content` 从尾部**整份**取舍。

        English:
    Pick the files that enter the "setting extraction window", **sorted by importance** (when it
    doesn't fit, the last ones are dropped).

    ★ Added 2026-10-27. Previously `extract_settings(items)` concatenated **all** files,
    so `06_地图` (36k chars, serves map drawing only) and `写作参考` (18k chars, for humans only)
    competed with the worldview for the same window,
    while trimming **by position** kept the head and tail --
    the root readme at the front and the map book at the back survived, **the character cards in the
    middle were all gone**.
    Now: first block a batch by purpose, then sort the rest  rules -> characters -> foreshadowing ->
    settings -> misc, and
    let `_build_content` drop **whole files** from the tail.
    """
    keep: list[FileItem] = []
    for it in items:
        if not it.content:
            continue
        # ⚠ `path` 用 `getattr` 取：判据里有不走 `scan_project` 的鸭子类型夹具
        # （`tools/verify_llm_truncation.py` 的 `Item` 只有 content/category），
        # 直接 `it.path.parts` 会 `AttributeError`。没有 path 就只按类别过滤。
        # [EN] ⚠ `path` is read with `getattr`: some verifiers use duck-typed fixtures that don't go
        # [EN] through `scan_project` (`Item` in `tools/verify_llm_truncation.py` only has
        # [EN] content/category), and `it.path.parts` would raise `AttributeError`. Without a path,
        # filter by category only.
        _path = getattr(it, 'path', None)
        if _path is not None and any(str(p) in _EXTRACT_SKIP_PARTS
                                     for p in getattr(_path, 'parts', ())):
            continue
        if it.category not in _EXTRACT_KEEP_CATS:
            continue
        keep.append(it)

    if not keep:
        # ★ 挑完了是空的 ⇒ **退回"所有有内容的文件"**，不许把窗口交成空的：
        #   作者很可能只丢了一本小说进来（全是「正文」类，或者文件名一个类别词都没有），
        #   这时按用途的排除会把窗口清空 → 提取返回空骨架 → 界面上只剩一句"无法解析"，
        #   而作者根本不知道是"材料不合适"还是"程序坏了"。宁可多读，不可读空。
        # [EN] ★ If nothing was picked, **fall back to "all files with content"** -- never hand over
        # [EN] an empty window:
        # [EN] the author may well have dropped in just a novel (all `body` category, or filenames
        # [EN] without any category word), and then filtering by purpose empties the window ->
        # [EN] extraction returns an empty skeleton -> the UI only says "unable to parse", and the
        # [EN] author cannot tell whether "the material doesn't fit" or "the program broke".
        # [EN] Better to read too much than to read nothing.
        keep = [it for it in items if it.content]
        if keep:
            _note('这份材料里没有可直接提取的设定 / 人物 / 伏笔类文档，'
                  '已退回用全部文件提取（人物与世界观可能不准，最好补一份设定文档）')

    def _rank(it: FileItem) -> tuple[int, int, str]:
        last = 1 if any(k in it.name for k in _LAST_IN_CAT) else 0
        return (_CAT_ORDER.get(it.category, 9), last, it.name)

    keep.sort(key=_rank)
    return keep


def _build_content(items: list[FileItem]) -> str:
    """把挑出来的文件内容拼接，超上限时**整份跳过**垫后的文件。

    ★ 为什么不再用 `truncate_mid`：它是**掐头留尾**的，砍掉的是"拼在中间的那段"，
    而中间恰好是人物卡和世界观。现在是按 `pick_for_extract` 的顺序从尾部整份取舍，
    并且**跳过了哪几份要说出来**（`_note` → 界面日志）—— 装不下可以，静默装不下不行。

        English:
    Concatenate the picked file contents; when over the limit, **skip whole files** from the tail.

    ★ Why `truncate_mid` is no longer used: it **cuts the head and keeps the tail**, removing
    "whatever was concatenated in the middle" -- and the middle is exactly the character cards and
    the worldview. Now files are dropped whole from the tail in `pick_for_extract` order,
    and **which ones were skipped is stated** (`_note` -> UI log) --
    not fitting is acceptable, silently not fitting is not.
    """
    parts: list[str] = []
    dropped: list[str] = []
    used = 0
    for it in pick_for_extract(items):
        block = f"【{it.category}】{it.name}\n{it.content}"
        if used + len(block) > _MAX_CONTENT:
            dropped.append(it.name)
            continue
        parts.append(block)
        used += len(block) + 2
    if dropped:
        _note(f"提取窗口装不下，整份跳过了 {len(dropped)} 份（垫后的先砍）："
              f"{'、'.join(dropped[:6])}{'…' if len(dropped) > 6 else ''}")
    return "\n\n".join(parts)


async def extract_settings(items: list[FileItem], project_name: str = "") -> dict[str, Any]:
    """从扫描到的文档提取结构化设定。失败返回空骨架。

    ★ **被截断时不许静默降级**（2026-10-06 的事故）：输出撞上 `max_tokens` 会**截在半句话里**，
    `json.loads` 报 `Unterminated string`，老代码于是把整份设定换成空骨架（人物 0 位），
    界面上只留一句"无法解析" —— 用户那份设定里已经写完的人物**全丢了**。
    现在的三级处理：
      ① 正常解析；
      ② 解析不了且**确实是截断** → 加一次重试（更大上限 + 明确要求写短）；
      ③ 重试还不行 → `repair_json` 按"最长可闭合前缀"**抢救**，能救回多少算多少，
         并在 `take_notes()` 里留一条说明（调用方会把它写进界面日志）。
    
        English:
    Extract structured settings from the scanned documents. Return an empty skeleton on failure.
        ★ **No silent degradation on truncation** (the 2026-10-06 incident): output hitting `max_tokens` gets **cut off mid-sentence**,
        `json.loads` reports `Unterminated string`, and the old code then replaced the entire setting with an empty skeleton (0 characters),
        leaving only "unable to parse" on the UI -- the characters the user had already finished writing in their setting were **all lost**.
        The current three-level handling:
          ① Normal parse;
          ② Can't parse and **it really is truncation** -> add one retry (larger limit + explicitly require shorter writing);
          ③ Retry still fails -> `repair_json` **salvages** by "longest closable prefix", recovering as much as possible,
             and leaves a note in `take_notes()` (the caller writes it to the UI log).
    """
    content = _build_content(items)
    if not content.strip():
        _LOG.warning("无可读内容，返回空骨架")
        return _empty_skeleton()

    _LOG.info("开始提取设定：%d 文件，共 %d 字", len([i for i in items if i.content]), len(content))
    messages = [{"role": "user", "content": fill(_PROMPT, content=content)}]
    raw, meta = "", {}
    try:
        raw, meta = await llm.chat("cheap", messages, purpose="extract", json_mode=True,
                                   max_tokens=_MAX_OUT_TOKENS, temperature=0.2,
                                   return_meta=True)
    except Exception as e:
        _LOG.error("LLM 提取失败: %s", e)
        return _empty_skeleton()

    result = extract_json(raw, {})
    if not result and meta.get("truncated"):
        # ② 撞上限了 → 说清楚 + 重来一次（上限翻倍 + 要求写短）
        # [EN] ② Hit the limit → state it clearly + try again (double the limit + require shorter writing)
        bigger = int(_MAX_OUT_TOKENS * _RETRY_FACTOR)
        _note(f"提取输出被 {meta.get('max_tokens', _MAX_OUT_TOKENS)} token 上限截断"
              f"（已输出 {meta.get('tout')} token"
              + ("，含思考内容" if meta.get("has_reasoning") else "")
              + f"）→ 已按 {bigger} token 上限重试一次")
        try:
            raw2, meta2 = await llm.chat(
                "cheap", messages + [{"role": "user", "content": _SHORTER_HINT}],
                purpose="extract", json_mode=True, max_tokens=bigger,
                temperature=0.2, return_meta=True)
        except Exception as e:                              # noqa: BLE001
            _LOG.error("截断后的重试也失败: %s", e)
            raw2, meta2 = "", {}
        if raw2:
            r2 = extract_json(raw2, {})
            if r2:
                return _finish(r2, retried=True)
            raw, meta = raw2, meta2          # 拿重试那次的原文去抢救（更长）
            # [EN] Use the raw output from the retry to salvage (longer)
            if meta2.get("truncated") is False:
                _note("重试仍解析不了（这次没被截断，可能是格式不对）")

    if not result:
        # ③ 抢救：只补结构，不改内容
        # [EN] ③ Salvage: only patch the structure, don't change the content
        salv = repair_json(raw, {})
        if salv:
            n = len(salv.get("人物") or [])
            _note(f"输出不完整，已按「最长可闭合前缀」抢救：救回 {n} 位人物"
                  f"（**末尾字段可能只写了一半，请核对设定集再开卷**）")
            return _finish(salv, salvaged=True)
        _LOG.warning("LLM 返回无法解析，原始文本: %s", raw[:300])
        _note("LLM 返回无法解析，设定集为空 —— 原始文本已写进对话日志，"
              "可到「天机 · 日志」里查看")
        return _empty_skeleton()

    return _finish(result)


def _finish(raw: dict, *, retried: bool = False, salvaged: bool = False) -> dict:
    """校验 + 填默认值 + 记一行统计（三个成功分支共用）。
        English:
    Validate + fill defaults + log one stats line (shared by the three success branches).
    """
    result = _validate(raw)
    n_chars = len(result.get("人物", []))
    tail = "（重试后）" if retried else ("（抢救）" if salvaged else "")
    _LOG.info("提取完成%s：人物 %d 位，世界观 %d 字",
              tail, n_chars, len(result.get("世界观", "")))
    return result


def _must_on_text(d: dict) -> str:
    """把「必出日」那一栏收成**一串数字**（`"3,7"`）；收不出来就空串。

    ★ 为什么要自己收一遍（不直接透传模型给的东西）：
      模型可能给 `"3"`、`3`、`["3","7"]`、`"第3、7章"`、`"第三天"`……
      这些**形状差别**若照原样透传，下游解析器一个都认不出 ⇒
      「必出」这条唯一保证就**静默失效**（表现成"程序照跑、就是没出"）。
      所以这里统一收成 `"3,7"`，下游 `world/layers.py::parse_must_on` 只认这一种。
      收不出来就**空串**（不许猜一个章号出来）。

        English:
    Normalize the "must appear" field into **a string of digits** (`"3,7"`); empty string if it can't be
    read.
        ★ Why normalize here (instead of passing the model's value through):
        [EN] The model may give `"3"`, `3`, `["3","7"]`, `"第3、7章"`, `"第三天"`... If those **shape
        [EN] differences** are passed through as-is, the downstream parser recognizes **none** of them ->
        [EN] the one guarantee ("must appear") **silently fails** (manifesting as "the program runs fine,
        [EN] it just never shows up"). So normalize to `"3,7"` here; downstream
        [EN] `world/layers.py::parse_must_on` recognizes only that one form. Unreadable -> empty string
        [EN] (never guess a chapter number).
    """
    raw = None
    for k in ('必出日', '必出章', '必出', '指定章次', 'must_on'):
        if isinstance(d, dict) and d.get(k) is not None:
            raw = d.get(k)
            break
    if raw is None:
        return ''
    try:
        from world.layers import parse_must_on as _pm
    except Exception:                                        # noqa: BLE001
        _pm = None
    if _pm is not None:
        try:
            days = _pm(raw)
            return ','.join(str(x) for x in days)
        except Exception:                                    # noqa: BLE001
            pass
    # 兜底：自己扫一遍数字（`world.layers` 不可导入时用）
    import re as _re
    out: list[int] = []
    for part in _re.split(r'[、,，;；\s/和跟及]+', str(raw)):
        m = _re.search(r'(\d+)', part)
        if m:
            n = int(m.group(1))
            if n > 0 and n not in out:
                out.append(n)
    return ','.join(str(x) for x in sorted(out))


def _validate(raw: dict) -> dict:
    """确保输出结构完整，缺失字段补默认值。
        English:
    Ensure the output structure is complete, fill defaults for missing fields.
    """
    out = {
        "人物": [],
        "世界观": str(raw.get("世界观", "") or ""),
        "地点": [],
        "关系": [],
        "伏笔": [],
        "剧情参考线": str(raw.get("剧情参考线", "") or ""),
        # ★ 顶级规则（2026-10-06）：作者写死的硬约束。
        #   这一项只是**兜底** —— 规则散写在普通设定文档里时靠它捞回来；
        #   如果用户专门建了「规则类文档」（文件名含"规则/铁律/守则"…），
        #   `ingest/pipeline` 会用**原文照录**，比这里的归纳更保真。
        # [EN] ★ Top-level rules (2026-10-06): hard constraints written by the author.
        # [EN] This item is only a **fallback** -- it recovers rules when they're scattered in ordinary setting
        # [EN] documents;
        # [EN] `ingest/pipeline` will use **verbatim transcription**, which is more faithful than the
        # [EN] summarization here.
        "顶级规则": [],
        # ★ 细节（2026-10-07）：**细节层**的素材（器物 / 习俗 / 口头禅 / 小规矩）。
        #   以前这些全被概括进 120 字的《世界观》里了 —— 而用户要的正是
        #   「具体每天的故事可能是由很小的设定影响的」（见 `world/layers.py`）。
        # [EN] ★ Details (2026-10-07): **detail-layer** material (objects / customs / catchphrases / small
        # [EN] rules).
        # [EN] These were previously all summarized into the 120-character "Worldview" -- yet what the user
        # [EN] wanted was exactly
        # [EN] "the specific daily story may be influenced by very small settings" (see `world/layers.py`).
        "细节": [],
    }
    # 人物
    # [EN] Characters
    for p in (raw.get("人物") or []):
        if isinstance(p, dict):
            out["人物"].append({
                "姓名": p.get("姓名") or p.get("name") or "未知",
                "身份": p.get("身份") or "",
                "简介": p.get("简介") or "",
                "性格": p.get("性格") or "",
                "口癖": p.get("口癖") or "",
                # ★★★ 2026-10-28：说话指纹（句长 / 抓手 / 心虚动作 / 称呼差）。
                #   宁可空着，也不要从"性格"里替作者编一条 —— 编出来的会跟别人撞味。
                # [EN] ★★★ 2026-10-28: speech fingerprint. Empty beats invented: an invented one
                # [EN] collides with everyone else's, which is the defect being fixed.
                "说话指纹": p.get("说话指纹") or "",
                "秘密": p.get("秘密") or "",
                "目标": p.get("目标") or "",
                "红线": p.get("红线") or "",
            })
    # 地点
    # ★ `方位` / `内里`（2026-10-08 加）：开卷时照地点表画**三级底图**要用它们
    #   （见 `world/atlas.py`）。**作者写了才留**，没写就是空 ——
    #   空不是错：底图会按 `说明` 与这类建筑的常识推（"两层，后院有口井" → 有院有井）。
    #   ⚠ 不加这两个字段的话，作者在设定里写的东西**根本到不了底图那一步**，
    #     表现是"我明明写了柴房，图上怎么没有"。
    # [EN] Locations
    # [EN] ★ `方位` / `内里` (added 2026-10-08): used to draw the **three-level base map** from the location
    # [EN] table at the start of a book
    # [EN] (see `world/atlas.py`). **Keep only if the author wrote it**; if not written it's empty --
    # [EN] empty isn't an error: the base map infers from `说明` and common knowledge of such buildings ("two
    # [EN] floors, a well in the backyard" -> has a yard and a well).
    # [EN] ⚠ Without these two fields, what the author wrote in the setting **can't reach the base map step
    # [EN] at all**,
    # [EN] manifesting as "I clearly wrote a woodshed, why isn't it on the map".
    for l in (raw.get("地点") or []):
        if isinstance(l, dict):
            inner = l.get("内里") or l.get("房间") or []
            if isinstance(inner, str):
                inner = [x.strip() for x in re.split(r'[、,，/\s]+', inner) if x.strip()]
            if not isinstance(inner, list):
                inner = []
            out["地点"].append({"名称": l.get("名称") or l.get("name") or "未知",
                               "说明": l.get("说明") or "",
                               "方位": str(l.get("方位") or "").strip()[:30],
                               "内里": [str(x).strip()[:8] for x in inner[:8]
                                        if str(x).strip()]})
    # 关系
    # [EN] Relationships
    for r in (raw.get("关系") or []):
        if isinstance(r, dict):
            out["关系"].append({"甲": r.get("甲") or "", "乙": r.get("乙") or "",
                               "关系": r.get("关系") or "", "张力": r.get("张力") or ""})
    # 伏笔
    # [EN] Foreshadowing
    for f in (raw.get("伏笔") or []):
        if isinstance(f, dict):
            out["伏笔"].append({"编号": f.get("编号") or "F?",
                               "内容": f.get("内容") or "",
                               "埋设": f.get("埋设") or "",
                               "预计回收": f.get("预计回收") or ""})
    # 顶级规则：字符串数组。模型偶尔给成 `[{"规则": "..."}]` 或单个字符串，
    # 两种都要认（别因为格式小差异把用户写死的规则整条丢掉）。
    # [EN] Top-level rules: string array. The model occasionally gives `[{"规则": "..."}]` or a single
    # [EN] string,
    # [EN] both must be accepted (don't drop an entire hard-written rule just because of a small format
    # [EN] difference).
    rules = raw.get("顶级规则")
    if isinstance(rules, str):
        rules = [rules]
    for r in (rules or []):
        if isinstance(r, dict):
            r = next((v for v in r.values() if isinstance(v, str) and v.strip()), "")
        s = str(r or "").strip().strip("-·•").strip()
        if s:
            out["顶级规则"].append(s)
    # 细节（细节层素材）：形状最杂的一项，模型爱给成字符串 / `{"细节": "..."}`
    # 两种都要认 —— 形状小差异把整条丢掉是最容易发生的静默损失。
    # [EN] Details (detail-layer material): the item with the most varied shapes, the model loves giving a
    # [EN] string / `{"细节": "..."}`
    # [EN] both must be accepted -- dropping an entire entry due to a small shape difference is the most
    # [EN] common silent loss.
    details = raw.get("细节") if raw.get("细节") is not None else raw.get("detail")
    if isinstance(details, str):
        details = [details]
    for d in (details or []):
        if isinstance(d, str):
            d = {"名称": str(d)[:12], "内容": str(d)}
        if not isinstance(d, dict):
            continue
        name = str(d.get("名称") or d.get("name") or "").strip()[:20]
        body = str(d.get("内容") or d.get("text") or d.get("说明") or "").strip()[:80]
        if not (name or body):
            continue
        who = d.get("涉及") or d.get("人物") or ""
        if isinstance(who, (list, tuple)):
            who = "、".join(str(x).strip() for x in who if str(x).strip())
        out["细节"].append({
            "名称": name or body[:12],
            "内容": body or name,
            "场合": str(d.get("场合") or d.get("地点") or "").strip()[:20],
            "涉及": str(who or "").strip()[:40],
            # ★ 2026-10-27：「必出日」（第 N 章必出）—— 跨章埋/收的唯一程序保证。
            #   解析不出来就留空串（**不许猜**），下游 `world/layers.py` 会当"没有"。
            # [EN] ★ 2026-10-27: "must appear on day N" -- the only programmatic guarantee for a
            # [EN] cross-chapter plant/cash-in. Unparseable stays an empty string (**never guess**);
            # [EN] `world/layers.py` treats that as "none".
            "必出日": _must_on_text(d),
        })
    return out


def _empty_skeleton() -> dict:
    return {"人物": [], "世界观": "", "地点": [], "关系": [], "伏笔": [],
            "剧情参考线": "", "顶级规则": [], "细节": []}


# 公开别名：供 AI 优化器等外部模块复用同一套结构校验
# [EN] Public alias: for external modules like the AI optimizer to reuse the same structural validation
validate_settings = _validate
empty_skeleton = _empty_skeleton