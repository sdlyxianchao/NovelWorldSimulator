# -*- coding: utf-8 -*-
"""叙事工艺库的**运行时**（设计稿 §8.4）。

`craft/` 里的素材（3 架 playbook + 6 类型档案 + 案例库）从 10-04 就摆在那儿了，
但**一行代码都没读它** —— `CRAFT_LIBRARY` / `CRAFT_CASES_ENABLED` 两个旋钮
在 `SPEC` 里是死的（全项目零读取）。这个模块就是把它接到导演身上。

§8.4 的原文要求，逐条对照实现：

    导演挑事前读类型卡取 **冲突偏好 + 钩子 + 爽点**
    （playbook 片段 **≤2 条、每条 ≤80 token** 限流）；
    叙事整理读风格卡；
    **张力目标 = 类型节奏模板 × 用户旋钮**；
    类型档案摘要做固定前缀进缓存。

## ⚠ 三条纪律

1. **只喂方法论，不喂作品。** 类型卡里的 `案例参照`（聊斋志异 / 深夜书屋…）
   是给人看的导航，**绝不进提示词** —— 那是版权红线，而且会把模型带成模仿腔
   （"照着某部片子写"正是本项目最不想要的）。`brief()` 里显式剔掉它。
2. **token 限流是硬要求，不是建议。** 这段会附在**每一次挑事**提示词上，
   而挑事是"每拍都可能调"的用途 —— 多一个字，成本就乘上运行时长。
   所以 `≤2 条 / 每条 ≤80 token` 是**代码里截断**，不是靠人自觉。
3. **用户旋钮优先于类型卡。** 类型卡只补"用户没表态"的地方
   （`TENSION_CURVE=auto` 才去看类型卡的张力曲线）。别拿类型卡盖掉用户的显式选择 ——
   他在书斋里选了"过山车"，就不该因为小说的类型卡写着 `medium` 而变平。

English:
**Runtime** of the narrative craft library (design doc §8.4).
The materials in `craft/` (3 playbook shelves + 6 type files + case library) have been sitting
there since 10-04,
but **not a single line of code read them** -- the two knobs `CRAFT_LIBRARY` /
`CRAFT_CASES_ENABLED`
are dead in `SPEC` (zero reads project-wide). This module is about wiring it to the director.
The original requirements of §8.4, checked item by item against the implementation:
    Before picking events, the director reads the type card to get **conflict preferences + hooks + payoff points**
    (playbook fragments **≤2 items, each ≤80 tokens** rate-limited);
    narrative organization reads the style card;
    **tension target = genre rhythm template × user knobs**;
    the type file summary becomes a fixed prefix into the cache.
## ⚠ Three disciplines
   are navigation for humans, **never into the prompt** -- that is a copyright red line, and it will lead the model into an imitative tone
   ("write it like some film" is exactly what this project least wants). `brief()` explicitly strips it out.
2. **Token rate limiting is a hard requirement, not a suggestion.** This段 will be attached to **every event-picking** prompt,
   and event-picking is a use case that "may be called every beat" -- one more word multiplies the cost by the runtime length.
   So `≤2 items / each ≤80 tokens` is **truncated in code**, not left to human discipline.
3. **User knobs take priority over the type card.** The type card only fills in what "the user has not expressed"
   (only when `TENSION_CURVE=auto` does it look at the type card's tension curve). Don't let the type card override the user's explicit choice --
   if he chose "roller coaster" in the study, it should not flatten just because the novel's type card says `medium`.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from config import CFG
from llm.tokens import estimate_tokens

_LOG = logging.getLogger("nws.craft")

CRAFT_DIR = Path(__file__).resolve().parent

# §8.4 的硬限流。**改这两个数之前先想清楚成本**（见模块头第 2 条）。
MAX_ENTRIES = 2          # 一次最多喂几条 playbook 片段
MAX_ENTRY_TOKENS = 80    # 每条的 token 上限（超了就截）
BRIEF_TOKEN_CAP = 400    # 整块的兜底上限（防上面两条同时放宽后失控）
# [EN] Hard rate limiting for §8.4. **Think through the cost before changing these two numbers** (see
# [EN] item 2 in the module header).
# [EN] Max number of playbook fragments to feed at once
# [EN] Token cap per fragment (truncate if exceeded)
# [EN] Fallback cap for the whole block (prevents runaway when both above are loosened simultaneously)

# 类型卡里**不许进提示词**的字段（见模块头第 1 条）。
# [EN] Fields in the type card that are **not allowed into the prompt** (see item 1 in the module
# [EN] header).
_NO_PROMPT_KEYS = ("案例参照",)


# ══════════════════════════════════════════════════════════════════
#  装载（含 `CRAFT_LIBRARY`：内置 + 用户增补目录）
# [EN] Loading (includes `CRAFT_LIBRARY`: builtin + user supplement directory)
# ══════════════════════════════════════════════════════════════════
_cache: dict[str, dict] = {"key": None, "genres": {}, "entries": {}, "cases": {}}


def _extra_dir() -> Path | None:
    """`CRAFT_LIBRARY` 指向的用户增补目录（留空 / `builtin` = 只用内置）。

    ⚠ 用户的增补目录是**叠加**在内置之上的，不是替换 —— 设计稿 §8.1 的原文是
    「craft/ 随程序发行，只读、离线……设置里可指向自己的增补目录」。
    同名时**用户目录优先**（他写的就是他要的）。
    
        English:
    The user supplement directory that `CRAFT_LIBRARY` points to (empty / `builtin` = builtin only).
        ⚠ The user's supplement directory is **layered on top of** the builtin, not a replacement -- the original text of design doc §8.1 is
        "craft/ ships with the program, read-only, offline... settings can point to your own supplement directory".
        On name collision, **the user directory takes priority** (what he wrote is what he wants).
    """
    raw = (CFG.s("CRAFT_LIBRARY") or "").strip()
    if not raw or raw.lower() in ("builtin", "内置"):
        return None
    p = Path(raw)
    return p if p.is_dir() else None


def _read_yaml_dir(d: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning("工艺库读不了 %s: %s", f.name, e)
            continue
        if isinstance(data, dict):
            out[f.stem] = data
    return out


def load(force: bool = False) -> dict:
    """装载（带缓存）。返回 `{'genres', 'entries', 'cases'}`。

    `entries` 是**跨三架 playbook 的条目索引**：条目名 → `{原理, 适用, 提示词, 来源}`。
    类型卡的 `playbook映射` 用的是**条目名**（`草蛇灰线` / `悬念引擎`…），
    所以要在这里摊平，而不是按文件名找。
    
        English:
    Load (with cache). Returns `{'genres', 'entries', 'cases'}`.
        so it must be flattened here, rather than looked up by filename.
    """
    key = (str(_extra_dir() or ""), str(CRAFT_DIR))
    if _cache["key"] == key and not force:
        return _cache

    genres: dict[str, dict] = {}
    entries: dict[str, dict] = {}
    cases: dict[str, dict] = {}

    sources = [CRAFT_DIR] + ([_extra_dir()] if _extra_dir() else [])
    for root in sources:
        genres.update(_read_yaml_dir(root / "genres"))
        cases.update(_read_yaml_dir(root / "cases"))
        for shelf, data in _read_yaml_dir(root / "playbooks").items():
            for name, val in data.items():
                if not isinstance(val, dict):
                    continue            # 名称 / 来源 / 适用类型 这些是标量，不是条目
                    # [EN] Name / source / applicable type are scalars, not entries
                if "原理" not in val and "提示词" not in val:
                    continue            # 15节拍 / 英雄之旅 这类"阶段清单"不算条目
                    # [EN] "Stage lists" like 15 beats / Hero's Journey do not count as entries
                e = dict(val)
                e.setdefault("来源", shelf)
                e["_货架"] = shelf
                entries[name] = e

    _cache.update({"key": key, "genres": genres, "entries": entries, "cases": cases})
    _LOG.info("工艺库装载：%d 类型档案 / %d playbook 条目 / %d 案例组",
              len(genres), len(entries), len(cases))
    return _cache


# ══════════════════════════════════════════════════════════════════
#  查类型卡
# [EN] Look up type card
# ══════════════════════════════════════════════════════════════════
#: **界面上的题材名 → 工艺库类型卡名**。
# [EN] : **UI genre name -> craft library type card name**.
#:
#: 为什么需要这张表（2026-10-07 审计查出来的真问题）：
#: 开卷向导的题材下拉（`gui/app_flet.GENRE_CHOICES`）里有一项叫 **`悬疑·单元`**
#: （显示成「悬疑 · 单元剧」），而 `craft/genres/` 里那张卡叫 **`悬疑灵异`** ——
#: 两个名字**不共享任何子串**，`card()` 的"精确 → 包含"两级都命不中，
#: 于是它返回 `None`。
# [EN] : Why this table is needed (real problem found in the 2026-10-07 audit):
# [EN] : The genre dropdown in the opening wizard (`gui/app_flet.GENRE_CHOICES`) has an item called [EN] **`悬疑·单元`**
# [EN] : the two names **share no substring**, and both levels of `card()`'s "exact -> contains"
# [EN] matching miss,
# [EN] : so it returns `None`.
#:
#: 后果比"少一张卡"严重得多：一旦返回 None，
#:   · `card_curve()` / `card_climax_days()` 全部拿不到 → 张力曲线与高潮间隔
#:     悄悄退回默认值；
#:   · `brief()` 里那份"类型简报"（冲突偏好 / 钩子库 / 爽点）整段消失；
#:   · `crew/agents._craft_for` 的"先取类型卡映射"那一步永远为空，
#:     于是每个职位读到的都是**货架里文件顺序前三条** —— 手艺还在，
#:     但**跟这本书的类型没关系**了。
# [EN] : The consequence is far worse than "missing one card": once it returns None,
# [EN] :   · `card_curve()` / `card_climax_days()` all get nothing -> tension curve and climax interval
# [EN] :     silently fall back to defaults;
# [EN] : · the "genre brief" in `brief()` (conflict preferences / hook library / payoff points)
# [EN] disappears entirely;
# [EN] :   · the "first look up type card mapping" step in `crew/agents._craft_for` is always empty,
# [EN] :     so every role reads the **first three files in shelf order** -- the craft is still there,
# [EN] :     but it is **no longer related to this book's genre**.
#:
#: 而且它只在你**手动选**那一项时发作：自动判定走的是 AI 回的类型名
#: （「悬疑」这类能被 `name in g` 兜住），所以这条一直没被发现。
# [EN] : And it only triggers when you **manually select** that item: automatic determination uses the
# [EN] genre name returned by the AI
# [EN] : (things like "悬疑" can be caught by `name in g`), so this has gone unnoticed.
#:
#: ⚠ 这张表是"界面名 → 库名"的**唯一**映射处。加题材选项时，
#:   要么把卡名写成一样，要么往这里加一行 —— 判据
#:   （`tools/verify_crew_flow.py` 的 A 组）会遍历 `GENRE_CHOICES`
#:   逐个查 `card()` 是不是 `None`，漏了当场报红。
# [EN] : ⚠ This table is the **only** place mapping "UI name -> library name". When adding genre
# [EN] options,
# [EN] :   either write the card name the same, or add a line here -- the check
# [EN] :   (group A of `tools/verify_crew_flow.py`) iterates over `GENRE_CHOICES`
# [EN] :   and checks one by one whether `card()` is `None`, flagging red immediately if missed.
GENRE_ALIAS: dict[str, str] = {
    '悬疑·单元': '悬疑灵异',
    '悬疑·单元剧': '悬疑灵异',
    '悬疑': '悬疑灵异',
    '历史·架空': '历史架空',
    '古代': '历史架空',
}


def resolve_genre(genre: str) -> str:
    """把界面题材名归一到工艺库里的类型卡名（认不出就原样返回）。
        English:
    Normalize the UI genre name to the type card name in the craft library (return as-is if
    unrecognized).
    """
    g = str(genre or '').strip()
    return GENRE_ALIAS.get(g, g)


def card(genre: str, structure: str = "") -> dict | None:
    """按类型名（可带结构轴）找类型卡；找不到返回 `None`（**别瞎猜一张给它**）。

    匹配顺序：**别名 → 精确 → 包含 → 结构轴兜底**。
    最后那一步是有用的：`玄幻修仙 + 单元剧` 时，主题材卡与"结构轴卡"都可能命中，
    而设计稿 §8.2 说结构轴（单元剧/升级流/公路/…）是**和题材正交**的一维。
    
        English:
    Find the type card by type name (may include structure axis); return `None` if not found
    (**don't just guess one for it**).
        Match order: **alias → exact → contains → structure axis fallback**.
        The last step is useful: for `玄幻修仙 + 单元剧`, both the theme card and the "structure axis card" may hit,
    """
    genres = load()["genres"]
    g = resolve_genre(genre)
    if g:
        if g in genres:
            return genres[g]
        for name, data in genres.items():
            if name in g or g in name:
                return data
    s = (structure or "").strip()
    if s:
        for name, data in genres.items():
            if s in str(data.get("结构轴", "")) or s in name:
                return data
    return None


def _misses() -> list[str]:
    """类型卡里指向了、但 playbook 里查不到的条目名（**数据缺口的自查**）。

    为什么要有这个：类型卡的 `playbook映射` 是人手写的名字，而 playbook 条目
    也是人手写的 —— 两边会漂。2026-10-06 第一次接线就发现 **6 张卡里有 10 个
    映射名对不上**（`权谋布局` / `悬念引擎` / `感情曲线`…）。这种"映射指向空气"
    在运行时的表现是**静默少喂一条**，不查就永远发现不了。
    
        English:
    Entry names that are referenced in type cards but not found in playbook (**self-check for data
    gaps**).
        Why this exists: the `playbook映射` in type cards is hand-written names, and playbook entries
        are also hand-written —— the two sides drift. On 2026-10-06, the first wiring found **10
        manifests at runtime as **silently feeding one item less**, undetectable unless checked.
    """
    entries = load()["entries"]
    out: list[str] = []
    for data in load()["genres"].values():
        for name in (data.get("playbook映射") or []):
            if not resolve_entry(str(name)):
                out.append(str(name))
    return sorted(set(out))


def resolve_entry(name: str) -> dict | None:
    """条目名 → 条目。**模糊匹配**：精确 → 双向子串。

    子串这一步是必需的，不是宽容：设计稿里类型卡写的是**技法概念**
    （`换地图节奏`、`权谋布局`），而 playbook 里的条目名是**更短的原名**
    （`换地图`）。两边都是人手写的，要求逐字相同等于要求人不出错。
    
        English:
    Entry name → entry. **Fuzzy matching**: exact → bidirectional substring.
        The substring step is necessary, not lenient: type cards in the design doc write **technique concepts**
        (`换地图`). Both sides are hand-written; requiring character-for-character equality is requiring humans to never err.
    """
    entries = load()["entries"]
    n = (name or "").strip()
    if not n:
        return None
    if n in entries:
        return entries[n]
    for key, val in entries.items():
        if key and (key in n or n in key):
            return val
    return None


def entry_names() -> list[str]:
    return sorted(load()["entries"])


# ══════════════════════════════════════════════════════════════════
#  张力目标 = 类型节奏模板 × 用户旋钮
# [EN] Tension target = genre rhythm template × user knobs
# ══════════════════════════════════════════════════════════════════
def card_curve(genre: str, structure: str = "") -> str:
    """类型卡给的张力曲线名（`flat` / `medium` / `roller`）；没有则空串。

    ⚠ **只在用户选了 `auto` 时才该用它**（见模块头第 3 条）。
    
        English:
    The tension curve name given by the type card (`flat` / `medium` / `roller`); empty string if
    absent.
        ⚠ **Only use this when the user has selected `auto`** (see module header item 3).
    """
    c = card(genre, structure) or {}
    v = str((c.get("节奏模板") or {}).get("张力曲线") or "").strip()
    # 言情那张卡写的是 `flat → medium → roller`（三段式），取最后一档当目标 ——
    # 前面几档是"故事内部的演变"，不是"整个故事的基调"。
    # [EN] The romance card says `flat -> medium -> roller` (three stages); take the last stage as the
    # [EN] target --
    # [EN] the earlier stages are "evolution within the story", not "the tone of the whole story".
    if "→" in v:
        v = v.split("→")[-1].strip()
    return v


def card_climax_days(genre: str, structure: str = "") -> int:
    """类型卡给的高潮间隔（天）；没有则 0（= 不表态，交给用户旋钮）。
        English:
    The climax interval given by the type card (days); 0 if absent (= no opinion, defer to user
    knob).
    """
    c = card(genre, structure) or {}
    try:
        return int((c.get("节奏模板") or {}).get("高潮间隔") or 0)
    except (TypeError, ValueError):
        return 0


# ══════════════════════════════════════════════════════════════════
#  提示词片段（§8.4 的核心；token 硬限流在这里）
# [EN] Prompt fragment (core of §8.4; hard token rate limiting is here)
# ══════════════════════════════════════════════════════════════════
def _clip_tokens(text: str, cap: int) -> str:
    """按 token 截断（不是按字数）。超了就在句读处收尾，别留半句话。
        English:
    Truncate by token (not by character count). If over, end at a sentence break, don't leave a half
    sentence.
    """
    s = " ".join(str(text or "").split())
    if estimate_tokens(s) <= cap:
        return s
    # 二分找最长可接受前缀，收在标点处（比逐字裁好看，也不会把句子劈成两半）
    # [EN] Binary-search the longest acceptable prefix, cutting at punctuation (looks better than
    # [EN] char-by-char truncation, and won't split a sentence in half)
    lo, hi = 0, len(s)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate_tokens(s[:mid]) <= cap:
            lo = mid
        else:
            hi = mid - 1
    cut = s[:lo]
    for p in ("。", "；", "，", ".", ";", ","):
        i = cut.rfind(p)
        if i > len(cut) * 0.6:
            return cut[:i + 1]
    return cut + "…"


def entries_for(genre: str, structure: str = "",
                limit: int = MAX_ENTRIES, *, offset: int = 0) -> list[tuple[str, str]]:
    """这个类型该读哪几条 playbook 的**提示词**。返回 `[(名字, 提示词片段)]`。

    `≤ limit 条、每条 ≤ MAX_ENTRY_TOKENS` —— 两条限流都在这里落实。

    ★★★ 2026-10-18：`offset` 让它**环形轮换**，而不是永远只取前 2 条。
      为什么必须改：`MAX_ENTRIES = 2` 是成本约束（本身合理），但老实现
      **永远取映射列表的前 2 条** ⇒ 列表里第 3、4 条**一辈子进不了提示词**。
      实测（6 张类型卡）：映射 3–4 条、只喂 2 条，被永久淘汰的有
      `草蛇灰线` / `悬念引擎` / `突转与发现` / `换地图节奏` / `黄金三章` /
      `伦理探讨` / `甜蜜暴击` / `期望鸿沟` —— 8 条手艺写在库里却从没到过任何人眼前。
      ⇒ 现在按 `offset` 环形取，调用方传一个随拍数变化的数（零成本、可复现）。
    ⚠ 不要改成"一次全喂"：每条 ≤80 token，全喂一份类型卡的映射就是 300+ token，
      每拍都付 —— 那是另一个坑（本项目记过"提示词 7000 字，模型记不住"）。
    [EN] ★★★ 2026-10-18: `offset` makes it **rotate**, instead of always taking the first 2.
    [EN] Why it must change: `MAX_ENTRIES = 2` is a cost constraint (reasonable), but the old
    [EN] implementation **always took the first 2 of the mapping list** => item 3 and 4 could
    [EN] **never** reach a prompt. Measured on 6 genre cards: 3-4 mapped, 2 fed, permanently
    [EN] eliminated: eight techniques were written in the library and never reached anyone.
    [EN] => rotate by `offset`; the caller passes a per-beat number (free and reproducible).
    [EN] ⚠ Do not "feed them all": each is <= 80 tokens, so one card's mapping is 300+, paid every
    [EN] beat -- that is a different trap (recorded: "a 7000-character prompt, the model can't hold it").
    """
    c = card(genre, structure) or {}
    names = list(c.get("playbook映射") or [])
    if not names:
        return []
    # 环形：从 offset 处开始，绕回开头
    # [EN] Ring: start at `offset` and wrap around.
    off = int(offset or 0) % len(names)
    names = names[off:] + names[:off]
    out: list[tuple[str, str]] = []
    for n in names:
        if len(out) >= max(0, limit):
            break
        e = resolve_entry(str(n))
        if not e:
            continue
        tip = str(e.get("提示词") or e.get("原理") or "").strip()
        if not tip:
            continue
        out.append((str(n), _clip_tokens(tip, MAX_ENTRY_TOKENS)))
    return out


def brief(genre: str, structure: str = "", *, with_entries: bool = True,
          offset: int = 0) -> str:
    """给导演挑事用的**紧凑类型简报**（没有类型卡就返回空串）。

    顺序按"对这一次挑事有多有用"排：冲突偏好 → 钩子 → 爽点 → playbook 提示词 → 毒点红线。
    **不含 `案例参照`**（版权红线 + 防模仿腔，见模块头第 1 条）。
    
        English:
    A **compact type brief** for the director to pick fights with (returns empty string if no type
    card).
        Ordered by "how useful for this fight-picking": conflict preference → hooks → satisfaction points → playbook prompts → poison-point red lines.
        **Excludes `案例参照`** (copyright red line + anti-mimicry voice, see module header item 1).
    """
    c = card(genre, structure)
    if not c:
        return ""
    lines: list[str] = []

    conflict = c.get("冲突偏好") or {}
    if isinstance(conflict, dict) and conflict:
        main = str(conflict.get("主引擎") or "").strip()
        sub = str(conflict.get("副引擎") or "").strip()
        ban = str(conflict.get("禁用引擎") or "").strip()
        if main:
            seg = f"冲突主引擎：{main}"
            if sub:
                seg += f"（副：{sub}）"
            if ban:
                seg += f"｜禁用：{ban}"
            lines.append(seg)

    hooks = [str(x) for x in (c.get("钩子库") or [])[:3]]
    if hooks:
        lines.append("可用钩子：" + "、".join(hooks))
    joys = [str(x) for x in (c.get("爽点模式") or [])[:3]]
    if joys:
        lines.append("可兑现的爽点：" + "、".join(joys))

    if with_entries:
        # ★ `offset` 透传：让"这一场读哪 2 条"随拍数轮换（见 `entries_for` 的说明）。
        # [EN] Pass `offset` through so "which 2 to read this beat" rotates (see `entries_for`).
        picked = entries_for(genre, structure, offset=offset)
        for name, tip in picked:
            lines.append(f"〔{name}〕{tip}")

    taboos = [str(x) for x in (c.get("毒点红线") or [])[:3]]
    if taboos:
        lines.append("本类型毒点（**必须避开**）：" + "、".join(taboos))

    if not lines:
        return ""
    head = f"【本作类型参考 · {c.get('类型') or genre}】"
    body = "\n".join(f"- {x}" for x in lines)
    return _clip_tokens(head + "\n" + body, BRIEF_TOKEN_CAP)


def style_of(genre: str, structure: str = "") -> dict:
    """风格卡（§8.4 说"叙事整理读风格卡"）。返回类型卡里的 `风格建议`。
        English:
    Style card (§8.4 says "narrative organization reads the style card"). Returns the `风格建议` from
    the type card.
    """
    c = card(genre, structure) or {}
    v = c.get("风格建议")
    return dict(v) if isinstance(v, dict) else {}


def cases(genre: str, structure: str = "") -> list[dict]:
    """案例参照（**只给人看 / 只写进运行摘要，绝不进提示词**）。

    `CRAFT_CASES_ENABLED=false` 时一律返回空 —— 这个旋钮就是干这个的。
    
        English:
    Case references (**human eyes only / written into run summary only, never into prompts**).
        Always returns empty when `CRAFT_CASES_ENABLED=false` —— that's exactly what this knob is for.
    """
    if not CFG.b("CRAFT_CASES_ENABLED"):
        return []
    c = card(genre, structure) or {}
    return [{"名称": str(x)} for x in (c.get("案例参照") or [])]


def summary(genre: str, structure: str = "") -> str:
    """一行人类可读的工艺库状态（给「天机」和运行摘要看）。
        English:
    A single human-readable line of craft library status (for 「天机」 and the run summary).
    """
    c = card(genre, structure)
    if not c:
        return f"工艺库：没有「{genre or '（未指定）'}」的类型档案"
    picked = entries_for(genre, structure)
    miss = _misses()
    s = (f"工艺库：{c.get('类型')}｜playbook "
         f"{'、'.join(n for n, _ in picked) or '（无）'}"
         f"｜张力基线 {card_curve(genre, structure) or '—'}")
    if miss:
        s += f"｜⚠ {len(miss)} 个映射名在 playbook 里找不到"
    return s
