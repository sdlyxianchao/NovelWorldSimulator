# -*- coding: utf-8 -*-
"""影视镜头卡（设计稿 §10.8，`FILM_MODE` / `DISPLAY_FILM_CARDS`）。

设计稿原文：
    为「以后拿去拍剧」准备：叙事整理时每小节附带**镜头卡**——

        【镜头】机位：中景·侧45°｜拍法：缓推（slow push-in）｜视角：客观
                出场：人物甲（账台后）、人物乙（门口入画）｜灯光：暖黄·单烛

    · 机位库：远/全/中/近/特 × 正/侧/背/俯/仰；拍法库：固定/推/拉/摇/移/跟/升降；
      由整理模型顺带产出，**不额外调用**（token 增幅约 10–20%）。
    · 显示：TUI 叙事区段首可显/隐（`DISPLAY_FILM_CARDS=true`）。
    · 落盘：写进「每天的生活」段首，并汇总成独立 **`分镜表.md`**。

★ 与设计稿的一处**有意的偏离**（要说清楚，不能悄悄改）
------------------------------------------------------
设计稿说镜头卡"由整理模型顺带产出"。本项目**没有独立的"整理模型"那一步**
（叙事整理走的是 `display/script_render` 的规则渲染 + 落盘），
所以要真按原文做，就得**多开一次 LLM 调用**——那正好是设计稿想避免的
（"不额外调用"是这条设计的卖点）。

于是这里用**规则推导**：机位看**有几个人在画面里**、拍法看**这一场有没有
推进/事件**、视角看**有没有心声**、灯光看**时辰与天气**。它不花一分钱、
可复现、可断言，代价是不如模型写得细。要反悔随时可以换成 LLM 版，
接口（`shot_card(...) -> str`）不用动。

★ 2026-10-10：按外部调研升级（第 02 类第 2、4、6 条）
-----------------------------------------------------
原来的镜头卡有三个"看着齐、其实没约束"的地方，这次按三份 MIT/Apache 源码补上：

1. **景别/运镜原来是自由字符串**（"中景·侧45°" 是硬编码的两三个字面量），
   于是它**不可校验**：写错一个字没人知道，也没法判"相邻镜头是不是撞景别了"。
   借鉴 **PenShot** `shot_segmenter_prompt.yaml`（MIT）的做法立**闭集**：
   景别 8 档 × 角度 5 档 × 运镜 8 档 × 转场 4 档，**取值只能在表内**。
   ⚠ 表是**本项目自己定的**（照明清题材的拍法），不是抄它的词表。

2. **缺两条硬规则**（PenShot 明文写着的）：**相邻镜头景别不得相同**、
   **同一景别连续不得超过 3 次**。没有它们，"分镜"就是把同一句话换个说法
   重复一遍 —— 而且**只有把它们写成可判定的话，才谈得上"校验"**。

3. **分镜不是有界对象**，所以不能 diff、不能说"这场戏镜头太多"。
   借鉴 **Pixelle-Video** `storyboard.py`（Apache-2.0）：每场的镜头数、
   单镜头描述长度、台词逐字保留，都**在代码里定界**。

另外补一张**「节拍 → 镜头配方」表**：借鉴 **StoryMind**
`cinematography-director.md` 的思想（**AGPL ⇒ 只借结构，内容全部自己重写**）。
它解决的是"模型给每场戏都配一个中景"这个最典型的坏味道：
**情绪到哪一档，镜头就该到哪一档**（发现→大特写推近；孤独→大远景静置；
决心→特写仰角边缘光）。

English:
Film shot card (design doc §10.8, `FILM_MODE` / `DISPLAY_FILM_CARDS`).
Original design doc text:
    Prepare for "later used to shoot a drama": each subsection during narrative organization comes with a **shot card** —
        [Shot] Camera: medium shot · side 45° | Shot method: slow push-in | Perspective: objective
                Appearances: Character A (behind the counter), Character B (enters frame at the door) | Lighting: warm yellow · single candle
    · Camera library: far/full/medium/near/close-up × front/side/back/high/low; shot method library: fixed/push/pull/pan/track/follow/crane;
      produced incidentally by the organization model, **no extra call** (token increase about 10–20%).
    · Display: can be shown/hidden at the start of a narrative section in the TUI (`DISPLAY_FILM_CARDS=true`).
    · Persistence: written to the start of the "daily life" section, and aggregated into a standalone **`分镜表.md`**.
★ One **intentional deviation** from the design doc (must be stated clearly, cannot be changed
silently)
------------------------------------------------------
The design doc says shot cards are "produced incidentally by the organization model". This
project **does not have that separate "organization model" step**
(narrative organization goes through the rule-based rendering of `display/script_render` +
persistence),
so to truly follow the original text, we'd have to **make one extra LLM call** — which is
exactly what the design doc wanted to avoid
("no extra call" is the selling point of this design).
So here we use **rule-based derivation**: camera looks at **how many people are in frame**, shot
method looks at **whether this scene has
progression/events**, perspective looks at **whether there's an inner voice**, lighting looks at
**time of day and weather**. It costs nothing,
is reproducible, and assertable; the cost is it's less detailed than what a model would write.
If we want to reverse course, we can switch to the LLM version anytime,
the interface (`shot_card(...) -> str`) doesn't need to change.
★ 2026-10-10: upgraded per external research (category 02, items 2, 4, 6)
-----------------------------------------------------
The original shot card had three places that "look complete but actually have no constraints";
this time we added them based on three MIT/Apache source codes:
1. **Shot size/camera movement were originally free strings** ("medium shot · side 45°" was two or three hardcoded literals),
   so it was **unverifiable**: a typo in one character goes unnoticed, and you can't judge "whether adjacent shots collide in shot size".
   Borrowing from **PenShot** `shot_segmenter_prompt.yaml` (MIT), we establish a **closed set**:
   shot size 8 tiers × angle 5 tiers × camera movement 8 tiers × transition 4 tiers, **values can only be within the table**.
   ⚠ The table is **defined by this project itself** (shot methods suited to Ming-Qing themes), not copied from its vocabulary.
2. **Missing two hard rules** (explicitly stated in PenShot): **adjacent shots must not have the same shot size**,
   **the same shot size must not be consecutive more than 3 times**. Without them, a "storyboard" is just repeating the same sentence in different words
   — and **only by writing them as decidable statements can we even talk about "validation"**.
3. **A storyboard is not a bounded object**, so it can't be diffed, and you can't say "this scene has too many shots".
   Borrowing from **Pixelle-Video** `storyboard.py` (Apache-2.0): the number of shots per scene,
   single-shot description length, verbatim dialogue retention, are all **bounded in code**.
Also add a **"beat → shot recipe" table**: borrowing from **StoryMind**
`cinematography-director.md`'s ideas (**AGPL ⇒ borrow only the structure, rewrite all content
ourselves**).
It solves the most typical bad smell of "the model gives every scene a medium shot":
"""
from __future__ import annotations

# ══════════════════════════════════════════════════════════════════
#  闭集（取值只能在表内 —— 这是整套校验的地基）
# [EN] Closed set (values can only be within the table — this is the foundation of the entire
# [EN] validation)
# ══════════════════════════════════════════════════════════════════
#: 景别 8 档，从远到近。**顺序有意义**：校验"跳跃过大"时按序号算距离。
# [EN] : 8 levels of shot size, from far to near. **Order matters**: when validating "jump too large",
# [EN] distance is computed by index.
SHOT_SIZES: tuple[str, ...] = (
    "大远景", "远景", "全景", "中景", "中近景", "近景", "特写", "大特写",
)
#: 角度 5 档（正/侧/背/俯/仰）
# [EN] : 5 levels of angle (front/side/back/high/low)
SHOT_ANGLES: tuple[str, ...] = ("正", "侧45°", "背", "俯", "仰")
#: 运镜 8 档
# [EN] : 8 levels of camera movement
MOVES: tuple[str, ...] = (
    "固定", "缓推", "快推", "缓拉", "横摇", "横移", "跟移", "升降",
)
#: 转场 4 档（相邻镜头之间怎么接）
# [EN] : 4 levels of transition (how adjacent shots connect)
TRANSITIONS: tuple[str, ...] = ("切", "叠化", "淡入", "淡出")
#: 视角 2 档
# [EN] : 2 levels of perspective
POVS: tuple[str, ...] = ("客观", "主观")

#: 时长分档（秒）—— 景别越远，观众需要的时间越长，这是剪辑的常识。
# [EN] : Duration tiers (seconds) — the farther the shot size, the longer the audience needs, this is
# [EN] editing common sense.
DURATION_BY_SIZE: dict[str, tuple[int, int]] = {
    "大特写": (2, 3), "特写": (2, 4), "近景": (3, 5), "中近景": (3, 6),
    "中景": (4, 8), "全景": (6, 10), "远景": (8, 12), "大远景": (8, 15),
}

#: 机位：按"画面里有几个人"选（人多就得退后）—— 原表保留，但值改成**闭集内的写法**
# [EN] : Camera position: chosen by "how many people are in frame" (more people means pull back) —
# [EN] original table retained, but values changed to **notation within the closed set**
_SHOT_BY_COUNT: dict[int, str] = {
    0: "全景·正",
    1: "近景·正",
    2: "中景·侧45°",
    3: "全景·正",
}
_SHOT_CROWD = "大远景·俯"
# 拍法：看这一场"动没动"
# [EN] Shot method: look at whether this scene "moved or not"
_MOVE_HINTS = ("走去", "进了", "出了", "推开", "跑", "赶", "上马", "离开", "回到")
_STILL_HINTS = ("坐着", "站着", "看着", "听着", "等着", "守在")
# 灯光：按《时辰 × 天气》
# [EN] Lighting: by "time of day × weather"
_LIGHT_BY_SEGMENT: dict[str, str] = {
    "清晨": "冷青·薄雾", "上午": "自然光·亮", "晌午": "顶光·硬",
    "午后": "暖白·斜光", "傍晚": "橙红·逆光", "入夜": "暖黄·单烛",
    "深夜": "冷蓝·月", "凌晨": "灰蓝·将明",
}

# ══════════════════════════════════════════════════════════════════
#  节拍 → 镜头配方（StoryMind 的思想，内容全部自己重写）
# [EN] Beat → shot recipe (the idea of StoryMind, all content rewritten ourselves)
# ══════════════════════════════════════════════════════════════════
#: 键是**节拍**（这出戏此刻想让观众感到什么），值是 `(景别, 运镜, 角度, 灯光)`。
#: 为什么要有这张表：没有它，每场戏都会默认给"中景·正" —— 一部戏全部中景，
#: 这不是分镜，是监控录像。有了它，"发现"和"孤独"在同一套代码里就长不一样。
# [EN] : key is the **beat** (what this play wants the audience to feel right now), value is `(shot
# [EN] size, camera movement, angle, lighting)`.
# [EN] : Why this table exists: without it, every scene would default to "medium shot · front" — an
# [EN] entire play all medium shots,
# [EN] : that's not a storyboard, that's surveillance footage. With it, "discovery" and "loneliness"
# [EN] look different within the same codebase.
BEAT_RECIPE: dict[str, tuple[str, str, str, str]] = {
    "发现":   ("大特写", "快推", "正", "硬光·高对比"),
    "孤独":   ("大远景", "固定", "俯", "冷调·漫射"),
    "决心":   ("特写",   "缓推", "仰", "边缘光·暗背景"),
    "告别":   ("远景",   "缓拉", "背", "逆光·暖残照"),
    "冲突":   ("中近景", "横摇", "侧45°", "硬光·投影"),
    "温情":   ("近景",   "固定", "正", "暖黄·柔"),
    "恐惧":   ("中景",   "升降", "仰", "冷蓝·低位光"),
    "赶路":   ("全景",   "跟移", "侧45°", "自然光·流动"),
    "等待":   ("中景",   "固定", "侧45°", "半明半暗"),
    "揭示":   ("特写",   "缓推", "正", "单点光·压暗四周"),
}
#: 认不出节拍时用的兜底（**不做"猜一个"** —— 猜出来的比默认值更糟：
#: 它会让人以为"模型读懂了这场的情绪"）。
# [EN] : fallback used when the beat can't be recognized (**do not "guess one"** — a guess is worse
# [EN] than the default:
# [EN] : it makes people think "the model understood this scene's emotion").
BEAT_FALLBACK = ("中景", "固定", "侧45°", "自然光")


def _norm_beat(beat: str) -> str:
    """把自由写法的节拍对上表。对不上返回空串（由调用方走兜底）。
        English:
    Match free-form beats against the table. If no match, return an empty string (the caller handles
    the fallback).
    """
    s = str(beat or "").strip()
    if not s:
        return ""
    if s in BEAT_RECIPE:
        return s
    for k in BEAT_RECIPE:
        if k in s:
            return k
    return ""


def recipe_for_beat(beat: str) -> tuple[str, str, str, str]:
    """节拍 → `(景别, 运镜, 角度, 灯光)`。**认不出就返回兜底**（并已注明不猜）。
        English:
    Beat → `(shot size, camera movement, angle, lighting)`. **If unrecognized, return the fallback**
    (and it's noted that no guessing is done).
    """
    k = _norm_beat(beat)
    return BEAT_RECIPE[k] if k else BEAT_FALLBACK


def size_of(kind: str) -> str:
    """从 `"中景·侧45°"` 里取出**景别**（认不出返回空串）。
        English:
    Extract the **shot size** from `"中景·侧45°"` (return an empty string if unrecognized).
    """
    head = str(kind or "").strip().split("·", 1)[0].strip()
    return head if head in SHOT_SIZES else ""


def angle_of(kind: str) -> str:
    """从 `"中景·侧45°"` 里取出**角度**（认不出返回空串）。
        English:
    Extract the **angle** from `"中景·侧45°"` (return an empty string if unrecognized).
    """
    parts = str(kind or "").strip().split("·")
    for p in parts[1:]:
        if p.strip() in SHOT_ANGLES:
            return p.strip()
    return ""


def kind_of(size: str, angle: str) -> str:
    """景别 + 角度 → 机位那一栏的规范写法。
        English:
    Shot size + angle → the canonical form for the camera position column.
    """
    s = size if size in SHOT_SIZES else SHOT_SIZES[3]
    a = angle if angle in SHOT_ANGLES else SHOT_ANGLES[0]
    return f"{s}·{a}"


def duration_hint(size: str) -> str:
    """景别 → 时长提示（`"4–8 秒"`）。
        English:
    Shot size → duration hint (`"4–8 秒"`).
    """
    lo, hi = DURATION_BY_SIZE.get(size, (4, 8))
    return f"{lo}–{hi} 秒"


def _people_in_frame(entries, world) -> list[str]:
    """这一场**画面里出现过谁**（按出场顺序去重）。
        English:
    Who **appeared in the frame** in this scene (deduplicated in order of appearance).
    """
    names: list[str] = []
    for e in entries or []:
        for attr in ("who", "speaker", "name"):
            n = str(getattr(e, attr, "") or "").strip()
            if n and n not in names:
                names.append(n)
    if not names:
        try:
            names = [str(x) for x in (world.on_stage_names() or [])]
        except Exception:                                       # noqa: BLE001
            names = []
    return names


def shot_card(entries, world, place: str = "", *, beat: str = "",
              transition: str = "", prev_kind: str = "") -> str:
    """一幕的镜头卡（一行）。`entries` 是这一幕的词条列表（`display.script`）。

    2026-10-10 新增三个**可选**参数（不传时行为与旧版兼容）：
      `beat`  —— 这一场的节拍；给了就按 `BEAT_RECIPE` 选镜头（不再是"永远中景"）；
      `transition` —— 与上一镜头的接法（不在闭集里就退回 `切`）；
      `prev_kind` —— 上一镜头的机位；给了才可能避开"相邻同景别"（见 `_avoid_same`）。
    
        English:
    The shot card for one act (one line). `entries` is the list of entries for this act
    (`display.script`).
        2026-10-10 added three **optional** parameters (behavior is compatible with the old version when not passed):
          `beat` — the beat for this scene; if given, select the shot per `BEAT_RECIPE` (no longer "always medium shot");
          `transition` — the transition from the previous shot (if not in the closed set, fall back to `切`);
          `prev_kind` — the camera position of the previous shot; only if given can "adjacent same shot size" be avoided (see `_avoid_same`).
    """
    names = _people_in_frame(entries, world)
    n = len(names)

    k = _norm_beat(beat)
    if k:
        size, move, angle, light_key = BEAT_RECIPE[k]
    else:
        # 旧路径：按"画面里几个人"选（保留原行为，别让没给节拍的调用点退化）
        # [EN] Legacy path: chosen by "how many people are in frame" (retain original behavior, don't let call
        # [EN] sites without a beat regress)
        kind0 = _SHOT_BY_COUNT.get(n, _SHOT_CROWD) if n <= 3 else _SHOT_CROWD
        size, angle = size_of(kind0), angle_of(kind0)
        light_key = ""
        text0 = " ".join(str(getattr(e, "text", "") or "") for e in (entries or []))
        if any(h in text0 for h in _MOVE_HINTS) or any(
                str(getattr(e, "kind", "")) == "event" for e in (entries or [])):
            move = "缓推"
        elif any(h in text0 for h in _STILL_HINTS):
            move = "固定"
        else:
            move = "横摇"

    # ★ 硬规则 ①：**相邻镜头景别不得相同**。撞了就退一档（近的往近里退、远的往远里退），
    #   退到闭集边界还撞，就换角度 —— 总之**不许出现两张一模一样的机位**。
    # [EN] ★ Hard rule ①: **adjacent shots must not have the same shot size**. On collision, step back one
    # [EN] tier (near ones step nearer, far ones step farther),
    # [EN] if it still collides at the closed-set boundary, change the angle — in short, **two identical
    # [EN] camera positions must never appear**.
    size, angle = _avoid_same(size, angle, prev_kind)

    shot = kind_of(size, angle)
    tr = transition if transition in TRANSITIONS else "切"

    # 灯光：节拍表给了就用它（节拍本来就该决定光），否则按时辰/天气推
    # [EN] Lighting: if the beat table provides it, use it (the beat should decide the light anyway),
    # [EN] otherwise infer from time of day/weather
    if light_key:
        light = light_key
    else:
        try:
            seg = str(world.clock.segment())
        except Exception:                                       # noqa: BLE001
            seg = ""
        light = _LIGHT_BY_SEGMENT.get(seg, "自然光")
        weather = str(getattr(world, "weather", "") or "")
        if "雨" in weather:
            light += "·雨天反光"
        elif "雪" in weather:
            light += "·雪地高反"
        elif "阴" in weather or "雾" in weather:
            light += "·漫射"

    # 视角：有心声/回想 → 主观；否则客观
    # [EN] Perspective: inner voice/recollection → subjective; otherwise objective
    kinds = {str(getattr(e, "kind", "")) for e in (entries or [])}
    pov = "主观" if kinds & {"aside", "inner", "recall"} else "客观"

    where = (place or str(getattr(world, "scene", "") or "")).strip()
    who = "、".join(names[:6]) or "（空镜）"
    beat_bit = f"节拍：{k}｜" if k else ""
    return (f"【镜头】{where + '｜' if where else ''}{beat_bit}机位：{shot}｜拍法：{move}"
            f"｜视角：{pov}｜时长：{duration_hint(size)}｜转场：{tr}"
            f"｜出场：{who}｜灯光：{light}")


def _avoid_same(size: str, angle: str, prev_kind: str) -> tuple[str, str]:
    """硬规则 ① 的实现：这一镜与上一镜**别撞景别**。

    ★ 为什么退一档而不是"永远改角度"：观众分辨"换了镜头"**主要靠景别差**，
      同一个景别只换角度看着还是没切。所以先动景别，动不了才动角度。
    
        English:
    Implementation of hard rule ①: this shot and the previous shot **must not clash in shot size**.
        ★ Why step down one level instead of "always changing the angle": viewers tell "the shot changed" **mainly by the shot size difference**,
          the same shot size with only a different angle still looks like no cut. So change the shot size first, and only change the angle if that's not possible.
    """
    prev = size_of(prev_kind)
    if not prev or prev != size:
        return size, angle
    i = SHOT_SIZES.index(size)
    # 交替退：近的往远处退一格，远的往近处进一格（中景则往近退，更常用）
    # [EN] Alternating retreat: near ones retreat one step farther, far ones advance one step nearer
    # [EN] (medium shots retreat nearer, more commonly used)
    step = -1 if i >= 3 else 1
    j = i + step
    if 0 <= j < len(SHOT_SIZES):
        return SHOT_SIZES[j], angle
    # 退不动（已经在两端）→ 换角度
    # [EN] Can't retreat (already at both ends) → change angle
    others = [a for a in SHOT_ANGLES if a != angle]
    return size, (others[0] if others else angle)


def storyboard_md(cards: list[dict]) -> str:
    """`分镜表.md`：场景 × 镜头列表（直接可当分镜脚本的底）。

    `cards` = `[{'day':1,'clock':'第1天·辰时','place':'临河茶肆',
                'people':[...], 'kind':'中景·侧45°','move':'缓推',
                'pov':'客观','light':'暖黄·单烛','line':'一句内容'}]`

    2026-10-10：表格补**时长 / 转场**两列，并在末尾附上**校验结论**
    —— 一份"看着齐但没人核过"的分镜表，和没有分镜表是一样的。
    
        English:
    `分镜表.md`: scene × shot list (can be used directly as the basis for the storyboard script).
    2026-10-10: the table adds two columns **duration / transition**, and appends a **validation
    conclusion** at the end
        —— a storyboard table that "looks complete but nobody has checked" is the same as having no storyboard table.
        Validate a storyboard table **as an object** (returns `crew.gate.Report`).
    """
    lines = ["# 分镜表", "",
             "> 由「影视镜头卡」汇总（`FILM_MODE=true` 时产出）。",
             "> 每条 = 一场戏的镜头。**不是拍摄脚本**，是拿去做分镜的底。",
             "", 
             "| # | 场次（天） | 时间 | 地点 | 出场 | 景别 | 角度 | 运镜 | 视角 | 时长 | 转场 | 灯光 | 内容一句 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    if not cards:
        lines.append("| — | — | — | — | — | — | — | — | — | — | — | — | （还没分幕） |")
    for i, c in enumerate(cards, 1):
        kind = str(c.get("kind", ""))
        lines.append("| {} | 第{}天 | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            i, c.get("day", "?"), c.get("clock", ""), c.get("place", ""),
            "、".join(c.get("people") or []) or "（空镜）",
            size_of(kind) or kind, angle_of(kind) or "—",
            c.get("move", ""), c.get("pov", ""),
            c.get("duration", "") or duration_hint(size_of(kind)),
            c.get("transition", "") or "—",
            c.get("light", ""), str(c.get("line") or "")[:40]))
    rep = validate_cards(cards)
    lines += ["", "---", "", rep.render(title="分镜表校验（`crew/gate`）")]
    return "\n".join(lines) + "\n"


def storyboard_plan_md(shots: list[dict]) -> str:
    """`分镜脚本.md`：分镜师把分拍拆出的**镜头清单**（ds.shots），直接可当拍摄说明书。

    与 `storyboard_md`（影视镜头卡 `FILM_MODE` 那条，schema 是 day/clock/place/…
    另一套）是两回事：这里渲染的是分镜师按分拍拆出的
    `[{镜, 拍, 景别, 画面, 台词, 镜头运动}, …]`（P2，2026-10-15）。

        English:
    `分镜脚本.md`: the shot list the storyboard artist broke beats into (ds.shots).
    Distinct from `storyboard_md` (film-card schema).     Renders
    `[{shot, beat, size, frame, line, move, intent, tell, button}, ...]` (P2, 2026-10-15).
    """
    lines = ["# 分镜脚本", "",
             "> 由「分镜师」角色产出（P2，2026-10-15）。每一镜 = 景别 / 画面 / 台词 / 镜头运动 / 意图 / 叙事点 / 收尾。",
             "> 它是「拍摄说明书」，不是剧本正文。",
             ""]
    if not shots:
        lines.append("（这一天没有分镜）")
        return "\n".join(lines) + "\n"
    lines += ["| 镜 | 拍 | 景别 | 画面 | 台词 | 镜头运动 | 意图 | 叙事点 | 收尾 |",
              "|---|---|---|---|---|---|---|---|---|"]
    for s in shots[:48]:
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            str(s.get('镜', '') or ''), str(s.get('拍', '') or ''),
            str(s.get('景别', '') or ''), str(s.get('画面', '') or ''),
            str(s.get('台词', '') or ''), str(s.get('镜头运动', '') or ''),
            str(s.get('意图', '') or ''), str(s.get('叙事点', '') or ''),
            str(s.get('收尾', '') or '')))
    return "\n".join(lines) + "\n"


#: 每场（同一天同一地点的一组镜头）**镜头数**的界（Pixelle-Video 的量级，自行定）
# [EN] : bounds on **shot count** per scene (a group of shots in the same day and location) (at the
# [EN] scale of Pixelle-Video, decide it yourself)
SHOTS_PER_SCENE = (3, 8)
#: 单镜头描述（`line`）的**字数**界
# [EN] : bounds on **character count** of a single shot description (`line`)
LINE_CHARS = (0, 60)


def validate_cards(cards: list[dict]) -> "object":
    """把一张分镜表**当对象校验**（返回 `crew.gate.Report`）。

    硬规则（P0/P1，违反就必须改）：
      · 景别 / 运镜 / 转场取值**必须在闭集内**（原来写错了没人知道）；
      · **相邻镜头景别不得相同**（PenShot 明文规则）；
      · 台词/内容一句**逐字保留**（不许为空 —— 空的那是空镜，要写明"（空镜）"）。
    软规则（P2/P3，提示但可接受）：
      · 同一景别**连续超过 3 次**；
      · 单场镜头数不在 `SHOTS_PER_SCENE` 之内；
      · 单镜头描述超过 `LINE_CHARS` 上限。
    
        English:
    Hard rules (P0/P1, must be fixed if violated):
        · shot size / camera movement / transition values **must be within the closed set** (previously errors went unnoticed);
          · **adjacent shots must not have the same shot size** (explicit PenShot rule);
          · dialogue/content must be **preserved verbatim line by line** (must not be empty —— an empty one is an empty shot, write "(空镜)").
          Soft rules (P2/P3, warn but acceptable):
        · the same shot size **appears more than 3 times in a row**;
          · the number of shots in a single scene is not within `SHOTS_PER_SCENE`;
          · a single shot's description exceeds the `LINE_CHARS` limit.
        Split the `shot_card()` line back into structured form (needed for the summary storyboard table).
    """
    from crew import gate                                     # noqa: PLC0415
    rep = gate.Report(target="分镜表")
    prev_size = ""
    run_size, run_len = "", 0
    for i, c in enumerate(cards or [], 1):
        where = f'第{i}条（第{c.get("day", "?")}天·{c.get("place", "") or "未标地点"}）'
        kind = str(c.get("kind", ""))
        size, ang = size_of(kind), angle_of(kind)
        if not size:
            rep.p0(where, f'景别不在闭集内：{kind!r}', f'改成 {" / ".join(SHOT_SIZES)} 之一')
        if kind and not ang:
            rep.p1(where, f'角度不在闭集内：{kind!r}', f'补一个：{" / ".join(SHOT_ANGLES)}')
        mv = str(c.get("move", ""))
        if mv and mv not in MOVES:
            rep.p1(where, f'运镜不在闭集内：{mv!r}', f'改成 {" / ".join(MOVES)} 之一')
        tr = str(c.get("transition", "") or "")
        if tr and tr not in TRANSITIONS:
            rep.p2(where, f'转场不在闭集内：{tr!r}', f'改成 {" / ".join(TRANSITIONS)} 之一')
        line = str(c.get("line") or "")
        if not line.strip():
            rep.p1(where, '内容一句是空的', '空镜要明写「（空镜）」，别留白')
        elif len(line) > LINE_CHARS[1]:
            rep.p3(where, f'内容一句 {len(line)} 字，超过 {LINE_CHARS[1]} 字',
                   '砍到一句话能说完，细节留给剧本')
        # 相邻景别（硬规则）
        # [EN] Adjacent shot sizes (hard rule)
        if size and prev_size and size == prev_size:
            rep.p0(where, f'与上一镜**景别相同**（都是{size}）—— 这不叫切镜头',
                   '换一个景别（近的退一格 / 远的进一格）')
        # 同景别连续（软规则）
        # [EN] Same shot size consecutive (soft rule)
        run_len = run_len + 1 if size and size == run_size else 1
        run_size = size or run_size
        if run_len == 4:
            rep.p2(where, f'{size} 已连续 {run_len} 个镜头',
                   '插一个别的景别，否则观众感觉镜头没动')
        prev_size = size or prev_size
    # 单场镜头数
    # [EN] Shot count per scene
    groups: dict[tuple, int] = {}
    for c in cards or []:
        key = (c.get("day"), str(c.get("place") or ""))
        groups[key] = groups.get(key, 0) + 1
    lo, hi = SHOTS_PER_SCENE
    for (day, place), cnt in groups.items():
        if cnt < lo:
            rep.p3(f'第{day}天·{place or "未标地点"}', f'只有 {cnt} 个镜头（少于 {lo}）',
                   '一场戏至少给几个角度，否则没法剪')
        elif cnt > hi:
            rep.p2(f'第{day}天·{place or "未标地点"}', f'有 {cnt} 个镜头（多于 {hi}）',
                   '把不推进剧情的镜头删掉')
    return rep


def parse_card(card: str) -> dict:
    """把 `shot_card()` 那一行拆回结构化（汇总分镜表要用）。
        English:
    Whether to display the shot card on screen (`FILM_MODE` and `DISPLAY_FILM_CARDS`).
    """
    out: dict = {}
    body = str(card or "").replace("【镜头】", "")
    for part in body.split("｜"):
        part = part.strip()
        if part.startswith("机位："):
            out["kind"] = part[3:]
        elif part.startswith("拍法："):
            out["move"] = part[3:]
        elif part.startswith("视角："):
            out["pov"] = part[3:]
        elif part.startswith("时长："):
            out["duration"] = part[3:]
        elif part.startswith("转场："):
            out["transition"] = part[3:]
        elif part.startswith("节拍："):
            out["beat"] = part[3:]
        elif part.startswith("出场："):
            out["people"] = [x for x in part[3:].split("、") if x and x != "（空镜）"]
        elif part.startswith("灯光："):
            out["light"] = part[3:]
        elif "：" not in part and part:
            out["place"] = part
    return out


def should_show() -> bool:
    """屏幕上要不要显示镜头卡（`FILM_MODE` 且 `DISPLAY_FILM_CARDS`）。
        English:
    Whether to display film cards on screen (`FILM_MODE` and `DISPLAY_FILM_CARDS`).
    """
    from config import CFG
    return bool(CFG.b("FILM_MODE")) and bool(CFG.b("DISPLAY_FILM_CARDS"))
