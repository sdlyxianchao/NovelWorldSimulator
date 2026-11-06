# -*- coding: utf-8 -*-
"""**房间任务书 → 平面图**：确定性的建筑解算（不再让模型直接给坐标）。

为什么要有这个模块（用户 2026-10-26 报的一整串问题）
----------------------------------------------------
用户原话：

    「现在生成的地图 完全不合理了 …… 后厨 堂屋区分开 而且很多东西叠在了一起
      房子和很小 布局也不合理 而且门放在了房子外面 小地图也不对
      还有一个问题就是地图没有延续性 同一个场景地图不同推演次数会变
      还要给就是美术不能够只是根据描述绘制地图 如果绘制之后检查发现地图不合理
      应该反馈给对应Agent修改地图设计（而且要根据剧本和小说修改）
      让其合理之后重新绘制才对
      还有地图绘制要参考标准地图学 建筑学 室内设计等专业的内容来绘制」

实测根因（读的是真项目里生成的 `地图/锚定.json`，不是推测）
------------------------------------------------------------
九处地点长这样：`{"x":0.5,"y":0.93,"shape":"门","size":"中","room":""}`，
而 `walls` 是**空数组**。于是：

| 用户看到 | 数据层的真因 |
|---|---|
| 房子很小 | 整栋楼只是一个 `size:中` 的点，与一口井同级 |
| 后厨、堂屋隔开 | 各自按 `x/y` 独立落点，**没有"谁在谁的房里"** |
| 很多东西叠在一起 | 二楼 y=0.08 与后院 y=0.192 只差 0.11 —— 同一层 |
| 门在房子外面 | `walls: []`，**根本没有墙**，门只是一个点 |
| 小地图也不对 | 小地图与大地图共用同一份 `plan_audit.solve()`，同一份错数据 |

而 `plan_audit._room_boxes()` 的算法是「每间取到最近一间距离的一半，重叠的互相推开」——
那是**气泡图（bubble diagram）**，不是平面图。气泡图里没有墙、没有房间归属、没有楼层，
所以"审核修补"修不出来：它要修的东西根本不在数据里。

★★★ 所以把方向倒过来：**模型不再给坐标，只给"房间任务书"**
----------------------------------------------------------
    ① 任务书（美术 + 剧本/小说）
       有哪些空间 · 谁在谁里面 · 必须挨着谁 · 哪间见天 · 几层 · 各自多大
            ↓ 本模块（纯函数，零 LLM、零成本）
    ② 平面解算
       外轮廓 → 按"从街面往里"分带 → 带内按面积切 → 门开在共用墙上 → 陈设塞进所属房间
            ↓
    ③ 审核（可数、可解释）
    ④ 有问题 ⇒ 把审核意见原文回给美术改任务书 ⇒ 回 ②（最多 `MAX_ROUNDS` 轮）

这样四件事在 ② 就是**结构上不可能发生**，而不是靠事后修补：
  · 房间**拼满**外轮廓 ⇒ 不可能有空隙、不可能叠；
  · 整栋楼 = 外轮廓 ⇒ 不可能"房子很小"；
  · 门只开在**共用墙 / 外墙**上 ⇒ 不可能悬在房子外面；
  · 楼层分组 ⇒ 二楼不可能压在后院上。

★ 延续性为什么免费：② 是**纯函数**。同一份任务书永远算出同一张图，
  所以**不需要锚定坐标**（坐标锚定只会把错的布局永久固化 ——
  实测现在的 `锚定.json` 锁住的正是那 9 个错坐标）。
  要改就改任务书，改一处整张图跟着修好。

参考（用户要求"参考专业内容"，这里落到了具体算法上）
----------------------------------------------------
  · **建筑学流程**：房间任务书(program) → 邻接图(adjacency) → 分区(zoning: 前场/后场)
    → 平面布局 → 门开在墙上 → 家具在房内 → 疏散连通检查。本模块 ①~③ 就是这条流程。
  · **squarified treemap**（Bruls/Huizing/van Wijk, 2000）：把矩形按权重切满，
    天然不重叠、无空隙。我们按"带"切（带内再切），所以还额外得到"从街到后"的次序。
  · **GSDiff**（AAAI 2025）把「错位、重叠、缝隙」当靶子，用对齐损失逼墙端点共线；
    我们的确定性版本更直接：墙就是相邻房间的公共边，**必然**共线且拼满。
  · **nobuyuki83/floor_plan**（Pacific Graphics 2024，MIT）把"房间面积"和"房间连通性"
    当优化约束 —— 我们把它降级成**硬约束**（面积当权重、连通当分带次序），
    因为这里要的是确定性、可复现、不依赖 GPU。
  · **中式店宅原型**：沿街门面 → 堂屋（前厅）→ 院（见天）→ 院侧后厨/杂役 → 楼上。
    这条原型写进了 `_BAND_HINT`，是"从街面往里"分带的依据。

English
-------
**Room program -> floor plan**: deterministic architectural solving (the model no longer hands
over coordinates).

Why this module exists (the user's report on 2026-10-26)
-------------------------------------------------------
The user's words: "the generated map is completely unreasonable now ... kitchen and hall are
separated, lots of things are stacked together, the house is very small, the layout is
unreasonable, and the door is placed outside the house; the minimap is wrong too; and the map has
no continuity -- the same scene differs between runs; also art must not just draw from a
description: if the drawn map turns out unreasonable it should feed the problem back to the
relevant agent to fix the map design (based on the script and the novel) and only redraw once it
is reasonable; and map drawing should reference standard cartography, architecture and interior
design rather than being drawn arbitrarily."

Measured root cause (read from the real `地图/锚定.json`, not guessed): nine places look like
`{"x":0.5,"y":0.93,"shape":"门","size":"中","room":""}` and `walls` is an **empty array**. So:
the whole building is itself a `中`-sized point (same as a well); kitchen and hall are placed
independently by their own x/y with **no "who is inside whom"**; the second floor at y=0.08 and
the courtyard at y=0.192 are 0.11 apart, i.e. **the same floor**; there are **no walls at all**,
so the door is just a point; and the minimap shares the same broken data.
`plan_audit._room_boxes()` is "half the distance to the nearest room, then push overlaps apart" --
a **bubble diagram**, not a floor plan. Auditing cannot repair it: what needs repairing is not in
the data.

★★★ So the direction is inverted: **the model no longer emits coordinates, only a room program**
    (1) program (art + script/novel): which spaces, who is inside whom, who must touch whom,
        which are open to the sky, how many floors, relative sizes
    (2) this module (pure functions, zero LLM, zero cost): envelope -> bands from the street
        inward -> slice by area -> doors on shared walls -> fixtures inside their owner
    (3) audit (countable, explainable)
    (4) on problems, feed the audit text back to art to revise the program -> back to (2),
        at most `MAX_ROUNDS` rounds
Four complaints become **structurally impossible** at (2) instead of being patched afterwards:
rooms tile the envelope (no gaps, no overlap), the building *is* the envelope (cannot be small),
doors only on shared/envelope walls (cannot float outside), floors are grouped (floor 2 cannot sit
on the courtyard).

★ Why continuity comes free: (2) is a **pure function**, so one program always yields one plan and
  **anchoring coordinates is unnecessary** -- anchoring only fossilises a wrong layout (measured:
  the current `锚定.json` locks exactly those nine wrong coordinates). Change the program and the
  whole plan follows.

References (the user asked to follow professional practice; here it is on concrete algorithms):
architecture workflow (program -> adjacency -> zoning -> layout -> doors on walls -> fixtures
inside -> egress check); squarified treemap (Bruls et al. 2000; tiles a rectangle by weights with
no overlap or gap -- slicing by bands also yields the street-to-back order); GSDiff (AAAI 2025)
targets misalignment/overlap/gaps with an alignment loss, whose deterministic analogue here is
"walls are the shared edges of adjacent rooms", so they are necessarily collinear and complete;
nobuyuki83/floor_plan (Pacific Graphics 2024, MIT) treats room area and connectivity as
optimisation constraints -- downgraded here to **hard constraints** (area as weight, connectivity
as band order) because we need determinism, reproducibility and no GPU; and the Chinese
shop-house typology (street frontage -> hall -> courtyard -> kitchen at the courtyard's side ->
upper floor), encoded in `_BAND_HINT`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from image_gen import worldstyle as WS
# 家具的**唯一一份**表（尺寸 + 靠不靠墙），绘制层也用它
# [EN] The **single** furniture table (size + wall habit); the renderer uses it too
from image_gen import furniture as FR

# ══════════════════════════════════════════════════════════════════════
#  规模与阈值（都写成常量，判据直接引用，不许在各处再写字面量）
# [EN] Sizes and thresholds (constants; criteria reference them, never re-type literals)
# ══════════════════════════════════════════════════════════════════════
#: 解算用的最小房间边长（像素）。小于这个数的"房间"在图上认不出来，
#: 会退化成一个点 —— 那时宁可让它退成**陈设**画在所属房间里。
#: ⚠ 不是"越小越好"：`verify_space_rules` 的几何窗口会把过小的方块认成别的东西。
# [EN] Minimum room edge in pixels during solving. Anything smaller cannot be recognized on the
# [EN] map and degenerates into a point -- better to demote it to a fixture inside its owner.
MIN_ROOM_PX = 26.0

#: 门的开口宽度（像素）。平面图惯例：门洞约 0.9m，按图上房间尺度取一个视觉合适值。
# [EN] Door opening width in pixels (a real door is ~0.9 m; this is a visually sensible value at
# [EN] the room scale we draw).
DOOR_PX = 26.0

#: 陈设方块的默认尺寸（像素）。
# [EN] Default fixture block size in pixels.
#: ⚠ 2026-10-27：**不再用作家具尺寸**（一律 15×15 就是"家具全一样大"的根源）。
#: 家具尺寸现在只由 `image_gen.furniture.spec_of()` 回答。这里留着是因为判据与老代码还在引用它。
# [EN] ⚠ 2026-10-27: **no longer a furniture size** (one 15x15 for everything is why all furniture
# [EN] looked the same). Sizes are answered only by `image_gen.furniture.spec_of()`; kept because
# [EN] criteria and older code still reference it.
FIX_PX = 15.0

#: 互锁轮数上限（审核→打回→改任务书→重解算）。
# [EN] Max interlock rounds (audit -> send back -> revise program -> re-solve).
MAX_ROUNDS = 2

#: **默认风格档案**：中式店宅。
#:
#: ★ 2026-10-26：这一整组常量原来是**代码本身**（`FIX_KEYS = ('柜','台',…)` 直接写在
#:   函数外面，谁用谁引用）。换一本书（西式庄园 / 赛博都市）时它们不会报错，
#:   只会**悄悄给出错误答案** —— 把宅邸画成四合院。现在它们只是"某一国的数据"，
#:   由 `worldstyle` 提供，函数一律收 `style=` 参数。
#:
#: 「室外/远处场所」的**兜底**词：这些名字出现了，就说明这一层不是"一栋房子里面"。
#:
#: ★★★ 2026-10-27（用户报的真 bug）：`day_layout` 现在**给每一档都推一份任务书**
#:   （`整体` 也推），而渲染层原来"有任务书就是室内" ⇒ 一份 6 个地点的**街区级**
#:   任务书被当成一栋房子，`roomplan` 把「石桥/渡口/兰若寺」切成横条房间，
#:   大地图上就是"一摞方框挤在右下角"，而小地图画的是另一套（不规则多边形）。
#:   用户原话：「我看到有石桥等因素 应该是街道或者城市地图 为何小地图效果是一些
#:   不规则图形 大地图则是多层方框合起来而不是正常地图」。
#:
#: ⚠ 但判"是不是一栋房子"的主判据**不是这张表**，而是 `style.房间词/见天词/陈设词`
#:   （复用建筑传统档案，见 `is_one_building`）。这张表只兜住"三个词表都不认"的
#:   室外写实地点，避免漏判。**表越短越好**：每加一个词就多一次误判机会。
# [EN] Fallback words for "outdoor / far-off places": if these appears, this layer is not "inside one
# [EN] building". ★★★ 2026-10-27 (a real bug the user reported): `day_layout` now derives a program
# [EN] for **every tier** (including `整体`), while the renderer used to treat "has a program" as
# [EN] "indoors" -- so a **street-level** program with six places was treated as one house,
# [EN] `roomplan` cut 石桥/渡口/兰若寺 into strip-shaped rooms, and the big map became "a stack of
# [EN] boxes squeezed into the bottom-right" while the minimap drew a different thing entirely.
# [EN] ⚠ The **primary** test is not this table but `style.房间词/见天词/陈设词` (reusing the
# [EN] architectural profiles; see `is_one_building`). This table only catches realistic outdoor
# [EN] places that all three word lists miss. **Shorter is better**: every word is a chance to misjudge.
OUTDOOR_WORDS = ('桥', '渡口', '渡头', '码头', '街', '巷', '市', '集市', '广场', '广场',
                 '山', '岭', '峰', '湖', '河', '江', '溪', '林', '野', '坡', '谷',
                 '城门', '关隘', '驿站', '官道', '路口', '田', '滩', '礁',
                 'bridge', 'street', 'lane', 'market', 'plaza', 'wharf', 'harbor',
                 'harbour', 'pier', 'road', 'field')


def is_one_building(prog: 'Program | None') -> bool:
    """这份任务书是**一栋建筑的里面**，还是"一片地方"？

    Returns:
        True = 一栋房子里的一层（该按室内平面画）；
        False = 一片地方（该按城市/城际画）。

    ## 判法（复用已有词表，不新建一套）

    1. **作者说了建筑名**（`prog.place` 非空）⇒ 就是这一栋 ⇒ True。
       这条最硬：`program_from_places` 只在**真的知道**建筑名时才填它。
    2. 否则数一数"**不是房间的空间**"：名字不在该风格的 `房间词`、不在 `见天词`
       （院子/天井本来就不是房间）、也不是 `陈设词`（柜台/井是陈设）。
       · 0~1 个 ⇒ 仍当一栋房子（"门脸""牌坊"这类边缘物常有）；
       · ≥2 个 ⇒ **不是一栋房子**（一栋房子里不会有"石桥"和"渡口"两个房间）。
    3. 室外兜底词（`OUTDOOR_WORDS`）命中 ≥2 个 ⇒ 直接 False（第 2 条可能因为
       词表太宽而漏）。

    ## 为什么阈值是 2

    实测（2026-10-27 一份真实当天地图的 6 地点任务书）：石桥、渡口一处、
    兰若寺 **3 个**不是房间；而真正的室内图（客来楼 9 处）是 **0 个**（柜台/井算陈设）。
    取 1 会把"房子带一个牌坊"判成一片地方，取 3 会漏掉只有两处室外物的图。2 在中间。
    ★ 判错的方向也考虑过：**判成"一片地方"的安全代价低于判成一栋房子** ——
      前者画出 6 个地点当街区（与 `kind='整体'` 的声明一致），后者会把桥和渡口
      画成两间房。
    [EN] Is this program **inside one building**, or "a stretch of country"? Returns True for
    [EN] one building's floor (draw an indoor plan), False for an area (draw a city/region map).
    [EN] ## Rules (reusing existing word lists, no new vocabulary): (1) **the author named the
    [EN] building** (`prog.place` non-empty) => True; that is the hardest signal, filled only when the
    [EN] building's name is genuinely known. (2) Otherwise count "**spaces that are not rooms**":
    [EN] names in neither `房间词` nor `见天词` (a courtyard is legitimately not a room) nor
    [EN] `陈设词` (a counter or a well is a fixture). 0~1 => still one building (edges like a gate
    [EN] facade happen); >=2 => **not one building** (one house has no "stone bridge" and "ferry"
    [EN] rooms). (3) >=2 hits on `OUTDOOR_WORDS` => False outright. ## Why the threshold is 2:
    [EN] measured 2026-10-27 on the real six-place program (bridge, ferry, temple = 3 non-rooms) and
    [EN] on a true indoor plan (9 places, 0 non-rooms). 1 would call "a house with one archway" an
    [EN] area; 3 would miss a map with two outdoor places. ★ The cost of each error was considered:
    [EN] calling an area "one building" is worse than the reverse -- the former draws a bridge and a
    [EN] ferry as two rooms, the latter draws six places as blocks, consistent with `kind='整体'`.
    """
    if prog is None:
        return False
    if str(getattr(prog, 'place', '') or '').strip():
        return True
    st = prog.style() if hasattr(prog, 'style') else DEFAULT_STYLE
    rooms = tuple(st.房间词) + tuple(st.见天词)
    fixt = tuple(st.陈设词)
    spaces = [s for s in (getattr(prog, 'spaces', None) or [])
              if not (hasattr(s, 'is_fixture') and s.is_fixture())]
    weird = 0
    outdoor = 0
    for s in spaces:
        n = str(getattr(s, 'name', '') or '')
        if not n:
            continue
        if any(w and w in n for w in OUTDOOR_WORDS):
            outdoor += 1
        if any(w and w in n for w in rooms) or any(w and w in n for w in fixt):
            continue
        weird += 1
    if outdoor >= 2 or weird >= 2:
        return False
    return True

#:
#: ⚠ 保留这些名字是为了**兼容**（`verify_*` 与外部脚本里有引用）。
#:   新代码请直接用 `style.字段`，别再引用这里的模块级常量 —— 那等于又把某一国写死。
# [EN] **Default style profile**: the Chinese shop-house. ★ 2026-10-26: this whole group used to
# [EN] *be the code* (constants at module level, referenced everywhere). Swapping in another book
# [EN] (a Western manor, a cyber city) raised no error -- it just **silently produced wrong
# [EN] answers**, drawing a manor as a courtyard house. They are now "one country's data", supplied
# [EN] by `worldstyle`, and every function takes `style=`. ⚠ The names are kept for compatibility;
# [EN] new code should use `style.field` -- referencing these again re-hard-codes one country.
DEFAULT_STYLE = WS.CN_SHOP_HOUSE

SKY_KEYS = DEFAULT_STYLE.见天词
FIX_KEYS = DEFAULT_STYLE.陈设词
GATE_KEYS = DEFAULT_STYLE.门洞词
UP_KEYS = DEFAULT_STYLE.楼上词
STAIR_KEYS = DEFAULT_STYLE.楼梯词
_BAND_HINT = DEFAULT_STYLE.分带次序


# ══════════════════════════════════════════════════════════════════════
#  一、数据结构
# [EN] 1. Data structures
# ══════════════════════════════════════════════════════════════════════
@dataclass
class Space:
    """任务书里的**一个空间**（房间 / 院子 / 陈设）。
        English: **One space** in the program (room / courtyard / fixture).
    """
    name: str
    floor: int = 1
    #: 见天（没有屋顶）。院子、天井、晒场是这一类。
    # [EN] Open to the sky (no roof): courtyards, light wells, drying yards.
    sky: bool = False
    #: 面积权重（**相对值**，不用平方米）。
    #: ⚠ 绝不能写"3.2 米"这种绝对尺寸 —— 我们没有真实尺寸，编一个就是**编**（本项目的禁忌）。
    #: 所以这里只有权重：2.0 表示"约是权重 1.0 那间的两倍大"。
    # [EN] Area **weight** (relative, not square metres). Never invent absolute dimensions --
    # [EN] we have none. 2.0 means "about twice the size of a 1.0 space".
    area: float = 1.0
    #: 陈设归属：非空表示"这不是房间，是摆在这个空间里的东西"。
    #: ⚠ 归属**读不出来**时这里就是空 —— 但那样它仍然是一陈设（见 `fix`）。
    # [EN] Owner for a fixture: non-empty means "not a room, a thing placed in this space".
    # [EN] ⚠ When the owner cannot be read this stays empty -- yet it is still a fixture (see `fix`).
    of: str = ''
    #: ★★★ 2026-10-26：**它是陈设这件事本身**（与"能不能读出售归属"无关）。
    #:
    #: 原来 `is_fixture()` 只看 `bool(of)`，于是：
    #:   · 备注里写清"堂屋左手边的柜台" ⇒ 读得出归属 ⇒ 是陈设 ✓
    #:   · 备注只写"前台接待" ⇒ 读不出归属 ⇒ **被当成一间房** ✗
    #: 后者会自己占一条带、而且没有任何邻接 ⇒ 审核报"从大门走不到这间"。
    #: 实测就是这么来的（现代办公楼的「前台」、科幻的「控制台」）。
    #: ⇒ 陈设身份由**判定结果**决定，不由"归属读没读出来"决定。
    # [EN] ★★★ 2026-10-26: **that it is a fixture**, independent of whether an owner could be
    # [EN] read. `is_fixture()` used to be just `bool(of)`, so a note like "柜台在堂屋左手边"
    # [EN] yielded an owner (fixture, correct) while a note like "前台接待" yielded none and the
    # [EN] thing **became a room** -- taking a band of its own with no adjacency, so the audit said
    # [EN] "cannot reach from the front door" (measured: the modern 「前台」 and the SF 「控制台」).
    # [EN] => Fixture identity comes from the classification, not from whether an owner was read.
    fix: bool = False
    note: str = ''

    def is_fixture(self) -> bool:
        return bool(self.fix or self.of)


@dataclass
class Program:
    """**房间任务书**：解算的全部输入（也是**延续性的事实来源**）。

    ★ 为什么任务书里**没有坐标**：坐标是解算的产物。让模型给坐标，等于让它
      同时当建筑师和制图员 —— 实测它制图很差（点乱摆、尺寸全填「中」），
      而它描述"有哪些房、谁挨着谁"很在行。**各干各擅长的**。
    [EN] **The room program**: the entire input to solving (and **the source of truth for
    [EN] continuity**). ★ Why there are no coordinates: coordinates are the output of solving.
    [EN] Letting the model give coordinates makes it both architect and draughtsman; measured, it
    [EN] draws badly (scattered points, every size "medium") while describing "which rooms, who
    [EN] touches whom" well. Each side does what it is good at.
    """
    place: str = ''
    spaces: list[Space] = field(default_factory=list)
    #: 必须**共用一道墙**的两两（任务书的"邻接图"）。
    # [EN] Pairs that must **share one wall** (the program's adjacency graph).
    adjacent: list[tuple[str, str]] = field(default_factory=list)
    #: 必须**并排**（同一个"带"里左右相邻）的组。
    #: 用途：`后院`/`后厨` 这种"院的一侧有灶间"的关系，靠它才排得对
    #: （只写邻接的话，后厨会被排到院子**后面**去，成了"第三进"）。
    # [EN] Groups that must sit **side by side** (same band). Needed for the
    # [EN] "kitchen on the courtyard's side" relation; adjacency alone would push the kitchen
    # [EN] *behind* the courtyard, i.e. a third courtyard-house depth.
    side_by_side: list[list[str]] = field(default_factory=list)
    #: 通向街面的那间（门开在它的外墙上）。
    # [EN] The room facing the street (the entrance door sits on its outer wall).
    entry: str = ''
    #: 街面在外轮廓的哪一边：`south` / `north`。
    #: 只有两个值：中式店宅沿街开门，图上一般画在下边或上边；左右开门会让
    #: "从街往里"的次序和画布长边打架。
    # [EN] Which side of the envelope the street is on: `south` / `north`. Only two values:
    # [EN] a shop-house opens onto the street along the long side, and left/right would fight the
    # [EN] "street inward" ordering against the canvas' long edge.
    street: str = 'south'
    #: 有没有临街门洞（名字里带"门"的那一处）。它**不是房间**，是外墙上的一个开口。
    # [EN] Whether there is a street door opening (the place whose name contains 门). It is **not
    # [EN] a room**, it is an opening in the outer wall.
    has_gate: bool = False
    #: ★ 2026-10-26：这份任务书是按**哪种建筑传统**推出来的（`worldstyle.Style.key`）。
    #: 存进盘里、随图一起走 —— 否则下次重解时默认回到中式店宅，
    #: 同一本书的图会**换一种建筑传统重画**，而界面上看不出为什么变了。
    # [EN] ★ 2026-10-26: which **architectural tradition** produced this program
    # [EN] (`worldstyle.Style.key`). Stored on disk and travels with the map; otherwise a re-solve
    # [EN] defaults back to the Chinese shop-house and the same book gets **redrawn in another
    # [EN] tradition**, with nothing on screen explaining why.
    风格: str = DEFAULT_STYLE.key
    #: 当初为什么判成这一种（判定的理由原文，进打回意见与日志）
    # [EN] Why it was judged this style (kept verbatim for revision notes and logs)
    风格依据: str = ''

    def style(self):
        """这份任务书对应的风格档案（认不出的 key 退回默认）。
            English: The style profile for this program (unknown key falls back to the default).
        """
        return WS.BY_KEY.get(str(self.风格 or ''), DEFAULT_STYLE)

    # ── 查询助手 ──
    def by_name(self) -> dict[str, Space]:
        return {s.name: s for s in self.spaces}

    def floors(self) -> list[int]:
        return sorted({s.floor for s in self.spaces if not s.is_fixture()})

    def rooms_of(self, floor: int) -> list[Space]:
        return [s for s in self.spaces
                if s.floor == floor and not s.is_fixture()]

    def fixtures_of(self, floor: int) -> list[Space]:
        return [s for s in self.spaces if s.floor == floor and s.is_fixture()]

    def to_dict(self) -> dict:
        return {
            '地点': self.place,
            '空间': [{'名称': s.name, '层': s.floor, '见天': s.sky,
                      '面积': s.area, '归属': s.of, '说明': s.note,
                      # ★ 2026-10-26：陈设身份要存。不存的话读回来又变成"看归属"，
                      #   读不出归属的那些会重新变回房间（老 bug 复活）。
                      # [EN] Store fixture identity; otherwise reading back reverts to "look at
                      # [EN] the owner" and fixtures without one become rooms again.
                      '陈设': bool(s.fix)}
                     for s in self.spaces],
            '邻接': [list(p) for p in self.adjacent],
            '并排': [list(g) for g in self.side_by_side],
            '入口': self.entry,
            '街面': self.street,
            '临街门': self.has_gate,
            # ★ 2026-10-26：**风格要跟图一起走**。不存的话下次重解退回默认中式店宅，
            #   同一本书的平面图会换一种建筑传统重画（而界面上没有任何提示）。
            # [EN] ★ Store the style with the map. Without it a re-solve reverts to the default
            # [EN] Chinese shop-house and the same book is redrawn in another tradition, silently.
            '风格': self.风格,
            '风格依据': self.风格依据,
        }

    @classmethod
    def from_dict(cls, d) -> 'Program | None':
        """从 JSON 读回（**宽容**：坏一条丢一条，不整体失败）。"""
        if not isinstance(d, dict):
            return None
        out = cls(place=str(d.get('地点') or ''),
                  风格=str(d.get('风格') or DEFAULT_STYLE.key),
                  风格依据=str(d.get('风格依据') or '')[:120])
        for it in (d.get('空间') or []):
            if not isinstance(it, dict):
                continue
            nm = str(it.get('名称') or '').strip()
            if not nm:
                continue
            try:
                fl = int(it.get('层') or 1)
            except (TypeError, ValueError):
                fl = 1
            try:
                ar = float(it.get('面积') or 1.0)
            except (TypeError, ValueError):
                ar = 1.0
            # ⚠ 层号**允许负数**（地下）。原来 `max(1, fl)` 会把 B1 硬拉回 1 层，
            #   地下车库就又回到了一楼。
            # [EN] Floor numbers **may be negative** (underground). `max(1, fl)` used to force B1
            # [EN] back to the ground floor, putting the garage upstairs again.
            _of = str(it.get('归属') or '').strip()
            out.spaces.append(Space(
                name=nm, floor=(fl if fl != 0 else 1), sky=bool(it.get('见天')),
                area=max(0.0, min(12.0, ar)), of=_of,
                fix=bool(it.get('陈设')) or (not _of and max(0.0, ar) <= 0.0),
                note=str(it.get('说明') or '').strip()[:80]))
        for p in (d.get('邻接') or []):
            if isinstance(p, (list, tuple)) and len(p) == 2:
                a, b = str(p[0]).strip(), str(p[1]).strip()
                if a and b and a != b:
                    out.adjacent.append((a, b))
        for g in (d.get('并排') or []):
            if isinstance(g, (list, tuple)) and len(g) >= 2:
                names = [str(x).strip() for x in g if str(x).strip()]
                if len(names) >= 2:
                    out.side_by_side.append(names)
        out.entry = str(d.get('入口') or '').strip()
        out.street = 'north' if str(d.get('街面') or '').strip() == 'north' else 'south'
        out.has_gate = bool(d.get('临街门'))
        return out


@dataclass
class Opening:
    """**一处门洞**：开在谁的墙上、开在哪。
        English: **One door opening**: on whose wall, and where.
    """
    a: str                 # 这一侧的空间
    b: str                 # 另一侧的空间（空串 = 室外/街面）
    x: float
    y: float
    along: str = 'h'       # 'h' = 开在横墙上（左右方向通行），'v' = 竖墙
    w: float = DOOR_PX

    def to_dict(self) -> dict:
        return {'a': self.a, 'b': self.b, 'x': round(self.x, 2),
                'y': round(self.y, 2), 'along': self.along, 'w': self.w}


@dataclass
class FloorPlan:
    """**一层的解算结果**。
        English: **The solved result of one floor**.
    """
    floor: int = 1
    envelope: tuple = (0.0, 0.0, 0.0, 0.0)      # (x0, y0, x1, y1)
    rooms: dict = field(default_factory=dict)   # 名字 → (x0, y0, x1, y1)
    doors: list = field(default_factory=list)   # [Opening]
    fixtures: dict = field(default_factory=dict)  # 名字 → (所属, (x0,y0,x1,y1))
    stairs: list = field(default_factory=list)  # [(x0, y0, x1, y1)]
    sky: set = field(default_factory=set)       # 见天的房间名
    #: **放不下的陈设**：`名字 → 它声称的归属`。
    #:
    #: ★★★ 2026-10-26（判据 F2 抓出来的）：这些陈设在解算时被 `continue` 跳过，
    #:   于是**既没画出来、也没人知道** —— 用户看到的是"这口井不见了"，而日志里一片安静。
    #:   ⇒ 现在记在这里，`audit()` 据此报「陈设没说归哪间房/归属那间不存在」。
    #:   **宁可报一条问题，也不要让它静静消失**（本项目的规矩：
    #:   "看不见的东西"是最严重的故障）。
    # [EN] **Fixtures that could not be placed**: `name -> the owner it claims`.
    # [EN] ★★★ 2026-10-26 (caught by criterion F2): these were `continue`d over during solving,
    # [EN] so they were **neither drawn nor noticed** -- the user sees "the well is gone" and the log
    # [EN] is silent. => Recorded here so `audit()` can report "fixture has no owner / that room does
    # [EN] not exist". **Better one reported problem than a silent disappearance** (this project's
    # [EN] rule: "the invisible" is the worst failure).
    orphans: dict = field(default_factory=dict)
    #: 每件陈设**实际**的摆放方式：`名字 → 'float'（离墙浮置）/ 'wall'（贴墙）`。
    #:
    #: ★★★ 2026-10-27（用户）：「不是所有家具都靠墙 比如柜台 要有留空站人」。
    #:   浮置族（柜台/井/桌）优先浮置；房间太小浮置不下时**退化**成贴墙（front 仍留空）。
    #:   判据 H8 要据此区分："声明浮置且真的浮置"的家具，离墙必须 ≥ 它的净空；
    #:   退化成贴墙的那件不算浮置，H8 不冤它，但 H1（≥pad）仍必须守。
    #: [EN] How each fixture was actually placed: 'float' (off-wall) / 'wall' (against wall).
    #: [EN] Float classes (counter/well/table) float first; a too-small room degrades them to the wall
    #: [EN] (front still clear). Criterion H8 reads this to tell "declared-float AND really floated"
    # [EN] pieces apart from degraded ones.
    anchor_of: dict = field(default_factory=dict)
    #: **净空不足**的陈设：`名字 → 它声称的归属`。
    #:
    #: ★★★ 2026-10-27（用户：「柜台 是要有留空站人才对」）：家具**摆上去了**，
    #:   但它要求留白的那块地方被别人占了 —— 房间就那么大，站人的地方没了。
    #:   这种"摆上了但不对"最难被发现（图上看着有家具），所以**单独记一份、报出来**。
    #: [EN] **Fixtures whose clearance is insufficient**: `name -> the owner it claims`.
    #: ★★★ 2026-10-27 (the user: "a counter needs standing room"): the piece **is** on the map, but
    #: [EN] the space it needs is taken. That "placed but wrong" state is the hardest to notice (the
    #: [EN] map looks furnished), so it gets **its own record and its own report**.
    tight: dict = field(default_factory=dict)

    def yard(self) -> tuple | None:
        """院子的矩形（见天的那一间里**最大的**）—— 渲染层要它画底纹。
            English: The courtyard rect (the largest sky space) -- the renderer needs it.
        """
        best, area = None, 0.0
        for nm in self.sky:
            b = self.rooms.get(nm)
            if not b:
                continue
            a = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
            if a > area:
                best, area = b, a
        return best


# ══════════════════════════════════════════════════════════════════════
#  二、从"设定里的地点表"推出任务书（**不调模型**的确定性兜底）
# [EN] 2. Derive a program from the setting's place list (**deterministic fallback**, no LLM)
# ══════════════════════════════════════════════════════════════════════
#: 名字里带这些字，说明它是**屋子里的一个空间**，不可能是"整栋建筑"。
#: 用来给"名字等于地点名 ⇒ 这是整栋楼"那条规则装一道安全阀。
# [EN] If a name contains these, it is **a space inside a building**, never "the whole building".
# [EN] A safety valve for the rule "\"name equals the place\" => this is the building itself".
_ROOM_WORDS = ('屋', '房', '厅', '室', '间', '厨', '灶', '仓', '廊', '厢', '院', '门')


def _looks_like_building(name: str, style=None) -> bool:
    """这个名字像不像**整栋建筑**（而不是里面的一间）。

    ★ 为什么需要它（2026-10-26 实测）：`program_from_places` 有一条"名字等于地点名 ⇒
      这就是整栋楼、不是房间"，靠它把"整栋楼那个名字"从房间里摘出来。但上游一旦把
      **房间名**当成地点名传进来（`day_layout` 曾经把 `here` 传成 place），
      这条规则就会把**当前所在的那间房整间删掉** —— 而这种错"看起来完全合理"：
      图上只是少了一间，没有任何报错。加一道判据：含屋/房/厅/院/门… 的一律**不算**建筑名。
    ★ 不追求准，只要求**宁可少摘也不误摘**：误摘的后果是"整栋楼变成一间房"（看得见、
      审核会报），误删的后果是"屋子凭空少了"（看不见）。两者不等价。
    [EN] Does this name look like **a whole building** rather than a room inside one?
    [EN] ★ Why needed (measured 2026-10-26): there is a rule "the name equals the place => this is
    [EN] the envelope, not a room", which lifts the building's own name out of the room list. But
    [EN] passes a **room name** as the place (`day_layout` used to pass `here`), that same rule
    [EN] **deletes the very room the person is in** -- and the failure looks perfectly plausible:
    [EN] the map is merely missing a room, with no error anywhere. Hence this check: anything
    [EN] containing 屋/房/厅/院/门... is **not** a building name. It need not be accurate; it must
    [EN] prefer under-matching: under-matching gives "the whole building became one room" (visible,
    [EN] and the audit reports it), while over-matching gives "a room silently vanished" (invisible).
    [EN] Those two are not equally bad.
    """
    n = str(name or '').strip()
    if not n:
        return False
    # 中文按"屋子/房间/院子/门"这类字认；外文按 `style.房间词`（hall/room/kitchen…）认。
    # ⚠ 两套都要看：设定里中英混写很常见（"great hall 大厅"）。
    # [EN] Chinese is detected by 屋/房/院/门 etc.; Latin by `style.房间词`
    # [EN] (hall/room/kitchen...). Check **both**: mixed Chinese/English is common.
    words = tuple(_ROOM_WORDS) + tuple((style or DEFAULT_STYLE).房间词)
    return not _hit(n, words)


def _hit(name: str, keys) -> bool:
    return any(k in str(name) for k in keys)


def floor_of(name: str, style=None) -> int:
    """这个名字在几层。**先判楼上**（`二楼后院` 两样都像，楼上是次要的层）。

    ★ 2026-10-26：词表来自**风格档案**（`worldstyle.Style.楼上词`），不再写死。
      中式用「二楼/阁楼」，西式还会认 `upper` / `first floor`，
      现代认「顶层/地下」，未来认「甲板/deck」。
    [EN] Which floor this name belongs to. ★ 2026-10-26: the word list comes from the **style
    [EN] profile** (`楼上词`), no longer hard-coded -- so Western `upper`/`first floor`, modern
    [EN] 「顶层/地下」 and futuristic `deck` are recognised too.
    """
    st = style or DEFAULT_STYLE
    n = str(name or '')
    # ★ 2026-10-26：**先判地下**。原来 `地下车库` 命中的是 `'地下'`（那时它在楼上词里）
    #   ⇒ 层号给成 **2**，于是车库画在二层图上、一层图上没有 —— 而"地下"和"楼上"
    #   在建筑上是相反的两件事。现在地下返回**负数**（`-1`、`-2`…），
    #   `floors()` 排序后自然排在 1 层之前，渲染层按层号显示成「B1」。
    # [EN] ★ 2026-10-26: **check underground first.** `地下车库` used to match `'地下'` (then in
    # [EN] 楼上词) and get floor **2**, so the garage appeared on the second-floor plan and was
    # [EN] missing from the ground plan -- while "underground" and "upstairs" are opposites. It now
    # [EN] returns a **negative** number, so `floors()` sorts it before floor 1 and the renderer
    # [EN] labels it "B1".
    for k in st.地下词:
        if k in n:
            # ⚠ 要认两种写法：`负二` / `B2`。只认中文数字的话 `B2` 会被当成 B1。
            # [EN] Recognise both styles (`负二` and `B2`); Chinese-only would read B2 as B1.
            m = (re.search(r'([一二三四五])', k) or re.search(r'([1-5])', k))
            base = {'一': -1, '二': -2, '三': -3, '四': -4, '五': -5,
                    '1': -1, '2': -2, '3': -3, '4': -4, '5': -5}.get(
                        m.group(1) if m else '一', -1)
            return base
    for k in st.楼上词:
        if k in n:
            # 「二层」→ 2、「三层」→ 3；拿不到数字就按 2
            m = re.search(r'([二三四五六七八九])', k)
            base = {'二': 2, '三': 3, '四': 4, '五': 5,
                    '六': 6, '七': 7, '八': 8, '九': 9}.get(m.group(1) if m else '二', 2)
            return base
    return 1


def is_gate(name: str, style=None) -> bool:
    """这个名字是不是**临街门洞**（外墙上的一个开口，不是房间）。

    ★★★ 2026-10-26 修（实测踩到的坑）：原来只判「名字里带『门』」——
      `二楼三间封门` 于是被当成了门洞 ⇒ **整层楼从图上消失**（它是那间房的名字，
      "封门"是说三间都封着，不是一道门）。
      ⇒ 收紧成三条，**全部满足**才算门洞：
        ① 名字里带 `GATE_KEYS` 之一；
        ② **不带楼层词**（`UP_KEYS`）—— 楼上的一律是房间；
        ③ 名字**短**（≤4 字）且**不带房间后缀**（房/厅/间/屋/楼/室）。
      这样 `门` / `大门` / `临街大门` / `街门` 是门洞，
      `二楼三间封门` / `门房` / `门厅` / `门楼` 是房间。
    ★ 2026-10-26 再改：词表来自风格档案。西式的 `front door` / `portal`
      与中式的「街门」是同一件事，不该只在中文世界生效。
    [EN] Is this name a **street door opening** (an aperture in the outer wall, not a room)?
    [EN] ★★★ Fixed 2026-10-26 (a pit hit in measurement): the old rule was just "contains 门", so
    [EN] `二楼三间封门` ("three sealed rooms upstairs") was taken for a door and **the whole upper
    [EN] floor vanished from the map**. Now three conditions, all required: (1) hits `GATE_KEYS`;
    [EN] (2) carries **no floor word** (`UP_KEYS`); (3) is **short** (<= 4 chars) and has **no room
    [EN] suffix** (房/厅/间/屋/楼/室). ★ The word lists now come from the style profile, so Western
    [EN] `front door`/`portal` work exactly like the Chinese 「街门」.
    """
    st = style or DEFAULT_STYLE
    n = str(name or '').strip()
    if not n or not _hit(n, st.门洞词):
        return False
    if _hit(n, st.楼上词):
        return False
    # ⚠ 长度门槛只对**中文**成立（4 个汉字≈一个短名）；英文名用词数判，别拿字符数卡。
    # [EN] The length gate only makes sense for Chinese (4 chars ≈ a short name); for Latin names
    # [EN] count words instead of characters.
    if _is_cjk(n):
        if len(n) > 4:
            return False
    elif len(n.split()) > 3:
        return False
    if _hit(n, ('房', '厅', '间', '屋', '楼', '室')):
        return False
    return True


def _is_cjk(s: str) -> bool:
    """字符串里有没有汉字（决定按字还是按词判长度）。
        English: Whether the string contains CJK (decides char vs word length checks).
    """
    return any('\u4e00' <= ch <= '\u9fff' for ch in str(s or ''))


def _owner_from_note(name: str, note: str, rooms: list[str]) -> str:
    """从**说明文字**里认出这件东西属于哪间房。

    ★★★ 这是本模块最要紧的一条"不编造"规则：
      我们**不知道**井在哪间房里，但设定原文写着「院子西北角的井」——
      所以答案**就在数据里**，读得出来就不该编。

      判法：逐个房间名去比说明文字，**按命中的字数**取最高分；
      门槛是 `max(1, len(屋名)-1)` ——「后院」与「院子西北角」只共用一个「院」，
      所以两字屋名允许命中 1 字；四字屋名要求命中 3 字（防"后院"这种大意命中）。
      ⚠ 拿不准就返回空串（**留给审核报"陈设没有归属"**），绝不猜。

    [EN] Read the owning room for a fixture out of its **note text**. This is the module's most
    [EN] important "never invent" rule: we do not know where the well is, but the setting says
    [EN] "the well in the courtyard's north-west corner" -- so the answer is **in the data**.
    [EN] Score each room name by how many of its characters appear in the note; the bar is
    [EN] `max(1, len(name)-1)`, so a two-character room name may match on one character and a
    [EN] four-character one needs three. When unsure, return '' (the audit then reports "fixture has
    [EN] no owner") -- never guess.
    """
    txt = str(note or '')
    if not txt:
        return ''
    best, best_n = '', 0
    for rn in rooms:
        if not rn:
            continue
        n = sum(1 for ch in rn if ch in txt)
        if n > best_n:
            best, best_n = rn, n
    if not best:
        return ''
    need = max(1, len(best) - 1)
    return best if best_n >= need else ''


def program_from_places(names, notes=None, *, place: str = '',
                        style=None, genre: str = '') -> Program:
    """把「地点名 + 说明」推成一份任务书（**确定性**，同样的输入永远同样的输出）。

    ## 规则（全部可解释，没有一条靠"感觉"）

    1. 名字带 `style.楼上词` → 归楼上（`floor>=2`），**不进**一层；
    2. `is_gate()` 说是门洞 → 记成**临街门洞**，不当房间；
    3. 名字带 `style.陈设词` → 陈设；归属从说明文字里读（`_owner_from_note`）；
    4. 名字带 `style.见天词` → 见天（院子/露台/中庭，看风格）；
    5. 其余是房间；
    6. 楼梯（`style.楼梯词`）单独一类，画在本层墙上；
    7. 面积权重 = `style.weight_of()`（**相对值**，不是平方米）；
    8. 入口：名字命中 `style.主厅词` 的第一间；没有就取一层第一间；
    9. 邻接：一层里按"从入口往后"串成一条链；
       `并排`：见天的院子 + 贴院的厨房（`style.厨房词`）。

    ## `style` 从哪来（2026-10-26 起）

    - 传了就用传的（渲染层从 `layout.program['风格']` 读回来时会传）；
    - 没传就**自己判**（`worldstyle.detect`，看名字+说明+题材）；
    - 判不出来 → 兜底档案，并且 `prog.风格依据` 里**照实写"判不出来"**。

    ★★ 这一层是本次改造的要点：原来这里的 9 条规则**全是中式店宅**（「堂/厅/店/铺」
      是入口、院 3.0、厨 1.6、带「堂」的是主厅）。换一本书不会报错，
      只会把西式宅邸**画成四合院**。现在规则通用，具体词与比例在 `worldstyle` 里。

    [EN] Turn "place names + notes" into a program (deterministic; same input, same output).
    [EN] ## Rules: 1) `style.楼上词` -> upper floor; 2) `is_gate()` -> street opening, not a room;
    [EN] 3) `style.陈设词` -> fixture, owner read from the note; 4) `style.见天词` -> open to the sky;
    [EN] 5) the rest are rooms; 6) stairs are their own class; 7) area weight = `style.weight_of()`
    [EN] (relative, not square metres); 8) entry = first room hitting `style.主厅词`; 9) adjacency: a
    [EN] chain inward, plus courtyard/kitchen side by side.
    [EN] ## Where `style` comes from: an argument when given (the renderer passes the one stored with
    [EN] the map), otherwise `worldstyle.detect` on names+notes+genre, otherwise the fallback profile
    [EN] -- and `prog.风格依据` says **plainly** that it could not be told.
    [EN] ★★ This is the point of the rework: the nine rules used to be **all Chinese shop-house**
    [EN] (「堂/厅/店/铺」 as entry, 院 3.0, 厨 1.6, 「堂」 = main hall). Another book raised no error,
    [EN] it just drew a Western manor **as a courtyard house**. Words and ratios now live in
    [EN] `worldstyle`; the rules here are generic.
    """
    names = [str(n).strip() for n in (names or []) if str(n).strip()]
    notes = list(notes or [])
    if not names:
        return Program(place=place)

    note_of = {n: (notes[i] if i < len(notes) else '') for i, n in enumerate(names)}

    # ── 风格：传进来的 > 自己判的 > 兜底 ──
    # ★ `理由` 必须一路带到盘上：判错了要能查出"当时凭什么判的"，不然只能靠猜。
    # [EN] Style: given > detected > fallback. ★ The reason travels to disk, so a wrong guess can be
    # [EN] traced to "what it was judged on" instead of guesswork.
    if style is None:
        _m = WS.detect(*names, *notes, genre=genre)
        style = _m.style
        _why = _m.why()
    else:
        _why = f'随图存档带来：{style.名}'

    prog = Program(place=place, 风格=style.key, 风格依据=_why)
    room_names_f1: list[str] = []
    gate_names: list[str] = []
    up_names: list[str] = []
    fix_raw: list[str] = []
    sky_f1: list[str] = []

    for n in names:
        fl = floor_of(n, style)
        # ⓪ **整栋楼自己不是房间**：它就是外轮廓。
        #   ★ 实测（2026-10-26）：整栋楼的名字被当成一间房，于是它在外轮廓**里面**又占了一条带，
        #     把后院与后厨挤成它的邻居 —— 而这栋楼本来就是那一圈墙。
        #     判法：名字等于任务书的地点名，或说明就是「（这里）」这种"你在这儿"的标记。
        # [EN] ⓪ **The building itself is not a room**: it *is* the envelope. Measured 2026-10-26:
        # [EN] The building name became a room and took a whole band *inside* its own envelope, pushing
        # [EN] courtyard and kitchen aside as its neighbours. Detected by "the name equals the
        # [EN] program's place" or "the note is a you-are-here marker".
        if (place and n == place and _looks_like_building(n, style)) \
                or note_of.get(n, '').strip() in ('（这里）', '(这里)'):
            continue
        # ② 临街门洞
        if is_gate(n, style):
            gate_names.append(n)
            prog.has_gate = True
            continue
        # ⑥ 楼梯
        if _hit(n, style.楼梯词):
            prog.spaces.append(Space(name=n, floor=fl, area=0.6,
                                     note=note_of.get(n, '')))
            # ★★★ 2026-10-26（实测西式/现代/科幻才暴露的）：**楼梯/电梯/通道必须进
            #   一层的房间链**。原来它们只进 `spaces` 不进 `room_names_f1`，于是
            #   不参与邻接 ⇒ 图上是一块**孤岛** ⇒ 审核报"从大门走不到这间"。
            #   中文场景很少把"楼梯"当地点写，所以这个坑一直没露头；换成
            #   `电梯`/`通道`/`corridor` 之后，它们本来就是常见地点。
            # [EN] ★★★ Measured 2026-10-26 (only surfaced with Western/modern/SF): **stairs,
            # [EN] lifts and corridors must join the ground-floor room chain.** They used to go
            # [EN] into `spaces` but not `room_names_f1`, so they took part in no adjacency and
            # [EN] became **islands** -- the audit then reported "cannot reach from the front door".
            # [EN] Chinese settings rarely list "stairs" as a place, so the pit stayed hidden;
            # [EN] `电梯`/`通道`/`corridor` are ordinary places.
            if fl == 1:
                room_names_f1.append(n)
            else:
                up_names.append(n)
            continue
        # ③ 陈设
        # ⚠ 陈设判定要**排除房间词**：西式的 `kitchen` 含 `kitchen`（本档案厨房词），
        #   但它是一间房；中式的「厨房」同理。只认"名字里带陈设词 **且** 不带房间词"。
        # [EN] Fixture detection must **exclude room words**: a `kitchen` is a room even though
        # [EN] "kitchen" sits in the fixture-ish list path; only names with a fixture word **and no
        # [EN] room word** count as fixtures.
        if _hit(n, style.陈设词) and not _hit(n, style.房间词):
            fix_raw.append(n)
            continue
        sk = _hit(n, style.见天词)
        prog.spaces.append(Space(name=n, floor=fl, sky=sk,
                                 area=_weight_of(n, sk, style), note=note_of.get(n, '')))
        if fl == 1:
            room_names_f1.append(n)
            if sk:
                sky_f1.append(n)
        else:
            up_names.append(n)

    # ③ 陈设的归属：从说明里读；读不出来再按"名字里带屋名"兜一次；仍不行就留空（交给审核）
    for n in fix_raw:
        nt = note_of.get(n, '')
        own = _owner_from_note(n, nt, room_names_f1)
        if not own:
            own = next((r for r in room_names_f1 if r in n or n in r), '')
        prog.spaces.append(Space(name=n, floor=floor_of(n, style), area=0.0,
                                 of=own, note=nt, fix=True))

    # ⑧ 入口
    prog.entry = next((r for r in room_names_f1 if _hit(r, style.主厅词)), '')
    if not prog.entry and room_names_f1:
        prog.entry = room_names_f1[0]

    # ⑨ 邻接：从入口向后串成链（中式店宅是"一进一进"往里走的）
    chain = [r for r in (_ordered_rooms(room_names_f1, prog.entry, style)) if r]
    for i in range(len(chain) - 1):
        prog.adjacent.append((chain[i], chain[i + 1]))
    # 并排：院子 + 贴院的灶间
    cook = [r for r in room_names_f1 if _hit(r, style.厨房词)]
    for yard in sky_f1:
        group = [yard] + [c for c in cook if c != yard]
        if len(group) >= 2:
            prog.side_by_side.append(group)
    return prog


def _weight_of(name: str, sky: bool, style=None) -> float:
    """面积**权重**（相对值，不是平方米）。比例来自**风格档案**，代码里不留任何一国默认。

    ★ 2026-10-26：原来写死"堂/厅 2.4、院 3.0、厨 1.6" —— 那是中式店宅的比例。
      换成西式宅邸之后，`great hall` 完全不命中，于是**主厅和储藏室一样大**，
      图上看着就是"这栋房子没有主次"。现在全部走 `Style.weight_of`。
    [EN] Area **weight** (relative, not square metres). Proportions come from the **style profile**;
    [EN] no single country's defaults remain in code. ★ Measured 2026-10-26: the old hard-coded
    [EN] "堂/厅 2.4, 院 3.0, 厨 1.6" is Chinese shop-house proportions -- under a Western manor
    [EN] `great hall` matched nothing, so **the main hall came out the same size as a pantry**.
    """
    st = style or DEFAULT_STYLE
    return st.weight_of(name, sky)


def _ordered_rooms(rooms: list[str], entry: str, style=None) -> list[str]:
    """按"从街面往里"排一遍：入口在最前，其余按 `_BAND_HINT` 的次序。

    ⚠ 这是**启发式排序**，不是建筑推理：真正常用的次序由任务书的 `并排/邻接` 表达。
      它只负责"两间都不挨着入口时，谁在前面"。
    [EN] Order rooms "from the street inward": the entry first, the rest by `_BAND_HINT`. This is a
    [EN] **heuristic** ordering, not architectural reasoning -- the real relations come from the
    [EN] program's `side_by_side`/`adjacent`. It only decides "who is in front" when neither touches
    [EN] the entry.
    """
    rest = [r for r in rooms if r != entry]
    order = (style or DEFAULT_STYLE).分带次序

    def rank(r: str) -> tuple:
        for i, k in enumerate(order):
            if k in r:
                return (i, r)
        return (len(order), r)

    out = ([entry] if entry else []) + sorted(rest, key=rank)
    return out


# ══════════════════════════════════════════════════════════════════════
#  三、切分原语：把一段长度按权重分成 n 份，**恰好用完**
# [EN] 3. Slicing primitive: split a length into n parts by weight, **exactly consuming it**
# ══════════════════════════════════════════════════════════════════════
def _split(total: float, weights: list[float], min_px: float) -> list[float]:
    """把 `total` 按 `weights` 分成 `len(weights)` 份，**和恰好等于 `total`**。

    ★ 这一条是"拼满"的全部秘密：不做取整、不留余量 ⇒ 相邻两间的边界**同一条线**，
      于是 i) 不可能有空隙 ii) 不可能有重叠 iii) 墙天然共线（GSDiff 用对齐损失去逼的那件事，
      我们直接让它不可能发生）。
    ★ 每份至少 `min_px`：先垫底再按权重分剩下的。装不下时（`n*min_px > total`）
      **退化成均分** —— 宁可房间小到认不出，也绝不超出外轮廓。
    [EN] Split `total` by `weights` into `len(weights)` parts whose **sum is exactly `total`**.
    [EN] ★ This is the whole secret of "tiles completely": no rounding, no remainder, so adjacent
    [EN] rooms share the very same boundary line -- therefore no gap, no overlap, and walls are
    [EN] collinear by construction (what GSDiff needs an alignment loss for, we make impossible).
    [EN] ★ Every part gets at least `min_px`: floor first, then split the rest by weight. If it does
    [EN] not fit (`n*min_px > total`), **degrade to equal parts** -- a room too small to recognise
    [EN] beats a room outside the envelope.
    """
    n = len(weights)
    if n <= 0:
        return []
    if n * min_px > total:
        return [total / n] * n
    rest = total - n * min_px
    ws = sum(w for w in weights if w > 0) or float(n)
    out = []
    for w in weights:
        out.append(min_px + rest * ((w if w > 0 else 0.0) / ws))
    # ⚠ 浮点累加会有 1e-13 的残差；把差值补到**最后一份**上，保证 sum(out) == total
    #   （判"拼满"用的就是面积和，差一点点就会被判成有空隙）
    # [EN] Floating point leaves a ~1e-13 residue; push it into the **last** part so sum(out) ==
    # [EN] total -- "tiles completely" is judged on the area sum, and a tiny residue reads as a gap.
    drift = total - sum(out)
    out[-1] += drift
    return out


def _bands(prog: Program, floor: int):
    """把这一层的房间分成**带**（从街面往里一进一进）。

    返回 `[[房间名, …], …]`，下标 0 = **最靠街**的那一带。

    分带规则（三条，都可解释）：
      ① 邻接图 BFS：离入口几跳就是第几带（一跳=前厅之后，两跳=再往里）；
      ② `并排` 组**强制同带**（取组内最小跳数）—— 这是"院的一侧有灶间"能被排对的唯一办法，
         否则灶间会排到院子**后面**，成了第三进；
      ③ 走不到入口的房间（孤岛）排到最后一带（**不丢**：审核会报"走不到"）。
    [EN] Group this floor's rooms into **bands** (one courtyard-house depth each), index 0 = the
    [EN] band nearest the street. Rules: (1) BFS over adjacency (hops from the entry = band index);
    [EN] (2) `side_by_side` groups are **forced into one band** (min hops) -- the only way "kitchen at
    [EN] the courtyard's side" comes out right, otherwise it lands *behind* the courtyard;
    [EN] (3) unreachable rooms go to the last band (**not dropped**: the audit reports them).
    """
    rooms = [s.name for s in prog.rooms_of(floor)]
    if not rooms:
        return []
    adj: dict[str, set] = {r: set() for r in rooms}
    for a, b in prog.adjacent:
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    # ① BFS
    entry = prog.entry if prog.entry in adj else rooms[0]
    depth = {r: 99 for r in rooms}
    depth[entry] = 0
    queue = [entry]
    while queue:
        cur = queue.pop(0)
        for nb in sorted(adj[cur]):
            if depth[nb] > depth[cur] + 1:
                depth[nb] = depth[cur] + 1
                queue.append(nb)
    # ② 并排组强制同带
    for grp in prog.side_by_side:
        members = [m for m in grp if m in depth]
        if len(members) >= 2:
            d = min(depth[m] for m in members)
            for m in members:
                depth[m] = d
    # ③ 成带（孤岛进最后一带）
    _ord = prog.style().分带次序
    order = sorted(rooms, key=lambda r: (depth[r], _tie_key(r, _ord)))
    out: list[list[str]] = []
    for r in order:
        d = depth[r]
        if out and depth[out[-1][0]] == d and d < 99:
            out[-1].append(r)
        else:
            out.append([r])
    return out


def _tie_key(name: str, order=None) -> tuple:
    """同深度时的次序：按风格档案的分带次序（前场在前），再按名字（保证确定性）。

    ★ 2026-10-26：次序来自档案（`Style.分带次序`）。中式是「门堂厅店铺院厨…」，
      西式是「门厅廊室房厨后楼」—— 同一份代码，两种建筑都能排对。
    [EN] Tie-break order comes from the profile (`Style.分带次序`): Chinese goes
    [EN] 「门堂厅店铺院厨…」, Western goes 「门厅廊室房厨后楼」 -- one code path, both right.
    """
    ord_ = tuple(order or DEFAULT_STYLE.分带次序)
    for i, k in enumerate(ord_):
        if k in name:
            return (i, name)
    return (len(ord_), name)


# ══════════════════════════════════════════════════════════════════════
#  四、解算：任务书 → 每层一张平面（**纯函数**）
# [EN] 4. Solve: program -> one plan per floor (**pure function**)
# ══════════════════════════════════════════════════════════════════════
def solve(prog: Program | None, *, span: tuple,
          street: str = '') -> dict[int, FloorPlan]:
    """把任务书解成**每层一张平面图**。同一份输入 ⇒ 逐位相同的输出。

    Args:
        prog:   房间任务书。
        span:   画布上留给平面的矩形 `(x0, y0, x1, y1)`（像素，左上原点）。
        street: 覆盖任务书里的街面方向（渲染层想按当前图的方向画时用）。

    ★★ 为什么是"每层一张"（用户 2026-10-26 选"分层出图"）：
      以前二楼和后院是同一份点表里的两个点，于是**必然**画在同一张图上、
      而且在数据层看来"二楼就在后院旁边"。分层是唯一能根治这件事的做法。
    ★ `span` 由调用方给：**像素换算是全图唯一的一份**（与绘制共用，老规矩）。
    [EN] Solve the program into **one plan per floor**. Same input => bit-identical output.
    [EN] ★★ Why "one per floor" (the user chose "one plan per floor" on 2026-10-26): the second
    [EN] floor and the courtyard used to be two points in one table, so they were **necessarily**
    [EN] drawn on the same plan and looked adjacent in the data. Splitting floors is the only real
    [EN] cure. ★ `span` comes from the caller: pixel conversion has **one implementation**.
    """
    out: dict[int, FloorPlan] = {}
    if prog is None:
        return out
    x0, y0, x1, y1 = (float(v) for v in span)
    W, H = max(1.0, x1 - x0), max(1.0, y1 - y0)
    side = 'north' if str(street or prog.street).strip() == 'north' else 'south'

    for fl in (prog.floors() or [1]):
        fp = FloorPlan(floor=fl, envelope=(x0, y0, x1, y1))
        bands = _bands(prog, fl)
        if not bands:
            out[fl] = fp
            continue
        w_of = {s.name: s for s in prog.rooms_of(fl)}
        sky = {s.name for s in prog.rooms_of(fl) if s.sky}
        fp.sky = set(sky)

        # ── ① 带高按面积权重切（和恰好 = H）──
        band_w = [sum(max(0.2, w_of[r].area) for r in b) for b in bands]
        heights = _split(H, band_w, MIN_ROOM_PX)
        # `street=south` ⇒ 第 0 带贴底边；`north` ⇒ 贴顶边
        y_cur = (y1 if side == 'south' else y0)
        for bi, band in enumerate(bands):
            hgt = heights[bi]
            by0 = (y_cur - hgt) if side == 'south' else y_cur
            by1 = (y_cur if side == 'south' else y_cur + hgt)
            # ── ② 带内按面积权重切宽（和恰好 = W）──
            widths = _split(W, [max(0.2, w_of[r].area) for r in band], MIN_ROOM_PX)
            bx = x0
            for ri, name in enumerate(band):
                fp.rooms[name] = (bx, by0, bx + widths[ri], by1)
                bx += widths[ri]
            y_cur = by0 if side == 'south' else by1

        # ── ③ 门：邻接的两间，开在**它们共用的那道墙**上 ──
        done: set = set()
        for a, b in prog.adjacent:
            if a not in fp.rooms or b not in fp.rooms:
                continue
            key = tuple(sorted((a, b)))
            if key in done:
                continue
            done.add(key)
            wall = shared_wall(fp.rooms[a], fp.rooms[b])
            if wall is None:
                continue        # 没共用墙 ⇒ 审核会报"这两间没挨上"
            along, cx, cy = wall
            fp.doors.append(Opening(a=a, b=b, x=cx, y=cy, along=along))

        # ── ④ 临街门洞：开在**外墙上**（不是屋里的某个点）──
        #
        # ⚠ 2026-10-26 修：临街门**只开在入口那一层**。
        #   原来 `has_gate` 是全局的，于是二楼也被开了一道"通街面"的门 ——
        #   而二楼在物理上不可能临街（那是悬空的）。实测第一次跑就出现了。
        #   判法：只有"入口房间在本层"的那一层才开街门。
        # [EN] ⚠ Fixed 2026-10-26: the street door is **only on the entry's floor**. `has_gate` was
        # [EN] global, so the second floor also got a "to the street" door, which is physically
        # [EN] impossible (it would hang in the air). Measured on the very first run. Rule: only the
        # [EN] floor that contains the entry room gets the street door.
        if prog.has_gate and prog.entry in fp.rooms:
            eb = fp.rooms.get(prog.entry)
            cx = (eb[0] + eb[2]) / 2.0
            gy = (y1 if side == 'south' else y0)
            # 门洞不能比那间房宽
            w = min(DOOR_PX, max(6.0, (eb[2] - eb[0]) * 0.8))
            fp.doors.append(Opening(a=prog.entry, b='', x=cx, y=gy,
                                    along='h', w=w))

        # ── ⑤ 楼梯：给它自己的格子（它本来就是"楼梯间"），另记一份给渲染层画踏步 ──
        for nm, box in fp.rooms.items():
            if _hit(nm, STAIR_KEYS):
                fp.stairs.append(box)

        # ── ⑥ 陈设：塞进**所属房间**里（贴着上墙排，放不下就换行）──
        fx_w: dict[str, float] = {}
        by_owner: dict[str, list] = {}
        for s in prog.fixtures_of(fl):
            by_owner.setdefault(s.of, []).append(s)
        for owner, items in by_owner.items():
            ob = fp.rooms.get(owner)
            if ob is None:
                # ★ 放不下就要**留下证据**（见 `FloorPlan.orphans` 的说明）：不能静静丢掉。
                # [EN] Cannot place it, so **leave evidence** (see `FloorPlan.orphans`).
                for s in items:
                    fp.orphans[s.name] = owner or ''
                continue
            # ★ 2026-10-27：`_pack_fixtures` 现在返回 `(放好的, 放不下的, 净空不足的)`，
            #   并**避开这一层已开的门洞**（`fp.doors` 在 ⑤ 段之前就填好了）。
            #   放不下的照旧记 `orphans` —— 不许静静消失（2026-10-26 报过"井不见了"）。
            #   **净空不足**的记 `tight`：家具摆上去了，但站人的地方被别人占了 ——
            #   也要报出来（否则用户看到的是"柜台前头堵着个柜子"，却没人提过）。
            # [EN] ★ 2026-10-27: `_pack_fixtures` now returns `(placed, dropped, tight)` and
            # [EN] **clears the doorways already opened on this floor** (`fp.doors` is filled before
            # [EN] step 5). The rest go to `orphans` -- nothing may vanish silently (the 2026-10-26
            # [EN] report). Pieces whose **clearance** is insufficient go to `tight`: they are on the
            # [EN] map, but someone's standing room is occupied -- also reported.
            _placed, _dropped, _tight = _pack_fixtures(ob, items, doors=fp.doors)
            for nm, box, how in _placed:
                fp.fixtures[nm] = (owner, box)
                fp.anchor_of[nm] = how
                fx_w[nm] = box[2] - box[0]
            for s_ in _dropped:
                fp.orphans[str(getattr(s_, 'name', '') or '')] = owner or ''
            for _t in _tight:
                fp.tight[str(_t)] = owner
        out[fl] = fp
    return out


def shared_wall(a: tuple, b: tuple, tol: float = 0.6):
    """两间房**共用的那道墙**：返回 `(along, 门心x, 门心y)`，没有共用墙返回 `None`。

    `along='h'` = 横墙（上下两家共用），`'v'` = 竖墙（左右两家共用）。
    ⚠ 要求**重叠长度 ≥ 一道门的宽度** —— 只挨着一个角不算共用墙（门开不下）。
    [EN] The wall two rooms **share**: `(along, door_x, door_y)`, or `None` when they share none.
    [EN] ⚠ The overlap must be at least one door wide; touching at a corner is not a shared wall.
    """
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    # 横墙：a 在下、b 在上（或反过来）
    for (up, dn) in ((a, b), (b, a)):
        if abs(dn[3] - up[1]) <= tol:
            lo, hi = max(dn[0], up[0]), min(dn[2], up[2])
            if hi - lo >= DOOR_PX:
                return ('h', (lo + hi) / 2.0, dn[3])
    # 竖墙：a 在左、b 在右（或反过来）
    for (lf, rt) in ((a, b), (b, a)):
        if abs(rt[0] - lf[2]) <= tol:
            lo, hi = max(lf[1], rt[1]), min(lf[3], rt[3])
            if hi - lo >= DOOR_PX:
                return ('v', rt[0], (lo + hi) / 2.0)
    return None


def _pack_fixtures(box: tuple, items: list, *, doors=None) -> tuple[list, list, list]:
    """把陈设排进一间房：**贴墙族靠墙、浮置族离墙留净空、都避门洞、不压墙、按真实尺寸**。

    ★★★ 2026-10-27（用户）：「不是所有家具都靠墙 比如柜台 是要有留空站人才对
      别的家具你也要重新检查下怎么放」。

    ⇒ 每件家具在 `furniture.FSpec` 里有一组**摆放习性**（`anchor` / `clear` / `clear_px`）：
      · 浮置族（柜台/井/桌，anchor ∈ float/center）：离墙一段（净空）摆放；
      · 贴墙族（灶/床/柜/架/椅凳/箱/筐篓，anchor ∈ wall/corner）：背靠墙，净空面朝室内。

    ## 净空怎么算（`clear` / `clear_px`）
      每件家具有一个**净空区**（zone）：它要求留白的那几侧往外扩 `clear_px`。
      两件家具打架的判据是**矩形相交**（zone ∩ 对方矩形），**不是中心距** ——
      中心距会把"并排贴墙的两口柜"误判成挤，而它们其实各留各的净空、互不妨碍。
      ★ 也因此**不能用一个全局间隙**：全局一刀切 ⇒ 同一面墙上只能放一件
        （实测：六口柜只放进三件，其余报"放不下"，而墙上明明还有位置）。

    ## 放不下怎么办（不许静静消失）
      ① **严格档**：守净空；② **宽松档**：只避重叠（净空不够也摆进去）；
      ③ 还放不下 ⇒ 进 `dropped`（报出来）。宽松档摆进去、或事后查出净空被占的
      ⇒ 进 `tight`（**净空不足**，也报出来）。

    老实现的三个错（一律 15×15、压墙 1.35px、不避门）照旧修掉。

    Returns:
        `(放好的, 放不下的, 净空不足的)`。
    [EN] Pack fixtures: wall classes hug walls, float classes sit off-wall with clearance, both clear
    [EN] doorways, never inside a wall, at real sizes. ★★★ 2026-10-27 (the user): "not every piece
    [EN] hugs a wall; a counter needs standing room -- re-check how the rest are placed." => each class
    [EN] carries a **placing habit** (`anchor` / `clear` / `clear_px`). ## How clearance is computed:
    [EN] every piece has a **clearance zone** (the sides it needs, grown by `clear_px`); two pieces
    [EN] clash when their rectangles **intersect** (zone vs the other rectangle), **not** by centre
    [EN] distance -- a centre distance would call "two cabinets side by side on one wall" jammed,
    [EN] though each keeps its own clearance. ★ Hence **no single global gap**: one flat gap means
    [EN] only one piece per wall (measured: six cabinets, three placed, the rest reported missing
    [EN] while the wall still had room). ## When it does not fit (nothing may vanish silently):
    [EN] (1) **strict** pass -- honour clearance; (2) **loose** pass -- avoid overlap only; (3) still
    [EN] no room => `dropped` (reported). Pieces placed in the loose pass, or found to violate a
    [EN] clearance afterwards, go to `tight` (**clearance insufficient** -- also reported).
    """
    x0, y0, x1, y1 = (float(v) for v in box)
    pad = FR.WALL_IN + FR.WALL_GAP
    ix0, iy0, ix1, iy1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
    placed: list[tuple[str, tuple, str]] = []     # (名字, 矩形, 'float'|'wall')
    zones: list[tuple] = []                      # 与 placed 同序：每件的**净空区**
    dropped: list = []
    if ix1 - ix0 < 10.0 or iy1 - iy0 < 10.0:
        return placed, list(items), []

    room = (x0, y0, x1, y1)

    # ── 每面墙"被门占掉的区间"（沿墙坐标）──
    # 门是 `Opening(along='h'|'v', x, y, w)`：`along='h'` 表示门**沿水平方向**开（在上下墙上）。
    # [EN] Openings occupied per wall.
    blocked: dict[str, list] = {'top': [], 'bottom': [], 'left': [], 'right': []}
    for dr in (doors or []):
        try:
            dx, dy = float(dr.x), float(dr.y)
            dw = float(getattr(dr, 'w', DOOR_PX) or DOOR_PX)
            along = str(getattr(dr, 'along', 'h') or 'h')
        except (TypeError, ValueError):
            continue
        half = dw / 2.0 + 4.0
        if along == 'h':
            if abs(dy - y0) <= pad + 3.0:
                blocked['top'].append((dx - half, dx + half))
            elif abs(dy - y1) <= pad + 3.0:
                blocked['bottom'].append((dx - half, dx + half))
        else:
            if abs(dx - x0) <= pad + 3.0:
                blocked['left'].append((dy - half, dy + half))
            elif abs(dx - x1) <= pad + 3.0:
                blocked['right'].append((dy - half, dy + half))

    # 已放家具：**矩形 + 它的净空区**（两者一起判"挤不挤"）
    occupied: list[tuple[tuple, tuple]] = []
    # 沿墙已占区间（供贴墙族沿墙排开）
    used: dict[str, list] = {'top': [], 'bottom': [], 'left': [], 'right': []}

    def _blocks(rect: tuple) -> bool:
        """这件家具是不是堵在某个门口（通用，不限于贴墙）。"""
        r0, r1, r2, r3 = rect
        for dr in (doors or []):
            try:
                dx, dy = float(dr.x), float(dr.y)
                dw = float(getattr(dr, 'w', DOOR_PX) or DOOR_PX)
                along = str(getattr(dr, 'along', 'h') or 'h')
            except (TypeError, ValueError):
                continue
            if along == 'h':
                if room is not None:
                    upper = abs(dy - room[1]) <= abs(dy - room[3])
                    near = abs(r1 - room[1]) if upper else abs(r3 - room[3])
                    if near > 18.0:
                        continue
                if r2 <= dx - dw / 2.0 + 0.5 or r0 >= dx + dw / 2.0 - 0.5:
                    continue
                return True
            else:
                if room is not None:
                    left = abs(dx - room[0]) <= abs(dx - room[2])
                    near = abs(r0 - room[0]) if left else abs(r2 - room[2])
                    if near > 18.0:
                        continue
                if r3 <= dy - dw / 2.0 + 0.5 or r1 >= dy + dw / 2.0 - 0.5:
                    continue
                return True
        return False

    def _ovl(a: tuple, b: tuple) -> bool:
        """两个矩形是否**相交**（贴边不算相交）。
        [EN] Whether two rectangles intersect (touching does not count)."""
        return (min(a[2], b[2]) - max(a[0], b[0]) > 0.5
                and min(a[3], b[3]) - max(a[1], b[1]) > 0.5)

    def _sides(sp, kind: str, wall: str | None, along: tuple) -> tuple:
        """这件家具**哪几侧**要留净空（'x0'/'x1'/'y0'/'y1'）。

        ★ 贴墙族的 `front` 指的是**朝室内**那一面（背靠墙那面不需要留白）；
          `sides` 指的是**长边的两侧**（床：长边贴墙、两侧留出上下床的地方）。
        [EN] Which sides need clearance. ★ For wall classes `front` is the side **into the room**
        [EN] (the wall side needs nothing); `sides` are the two sides along the long edge (a bed:
        [EN] long edge to the wall, both sides free to get in).
        """
        c = str(getattr(sp, 'clear', 'front') or 'front')
        if c == 'none':
            return ()
        if c == 'all':
            return ('x0', 'x1', 'y0', 'y1')
        if kind == 'float':
            if c == 'both':
                return ('y0', 'y1')
            if c == 'sides':
                return ('x0', 'x1')
            if c == 'front':
                return ('y1',)
            if c == 'back':
                return ('y0',)
            return ()
        # ── 贴墙族 ──
        if c == 'both':
            return ('y0', 'y1')
        if c == 'sides':
            # 长边沿 x ⇒ 两侧是上下；长边沿 y ⇒ 两侧是左右
            return ('y0', 'y1') if float(along[0]) >= float(along[1]) else ('x0', 'x1')
        if c == 'front':
            return {'top': ('y1',), 'bottom': ('y0',),
                    'left': ('x1',), 'right': ('x0',)}.get(wall, ())
        if c == 'back':
            return {'top': ('y0',), 'bottom': ('y1',),
                    'left': ('x0',), 'right': ('x1',)}.get(wall, ())
        return ()

    def _zone(rect: tuple, sp, kind: str, *, wall=None,
              along=(0.0, 0.0)) -> tuple:
        """这件家具的**净空区**：要求留白的那几侧往外扩 `clear_px`。
        [EN] This piece's **clearance zone**: the sides it needs, grown by `clear_px`."""
        need = float(getattr(sp, 'clear_px', 0.0) or 0.0)
        if need <= 0.0:
            return rect
        zx0, zy0, zx1, zy1 = rect
        for s in _sides(sp, kind, wall, along):
            if s == 'x0':
                zx0 -= need
            elif s == 'x1':
                zx1 += need
            elif s == 'y0':
                zy0 -= need
            elif s == 'y1':
                zy1 += need
        return (zx0, zy0, zx1, zy1)

    def _clear_of_others(rect: tuple, zone: tuple, *, strict: bool = True) -> bool:
        """这件家具跟已放的那些挤不挤。

        ★ 判据是**矩形相交**，不是中心距：并排贴墙的两口柜中心距很近，
          但它们各留各的净空、互不妨碍 —— 用中心距会把它们误判成"挤"。
        ★ `strict=False` 是**宽松档**：只避重叠，不查净空（净空不够也先摆上，
          事后报"净空不足"）。
        [EN] Whether this piece clashes with the ones already placed. ★ The test is **rectangle
        [EN] intersection**, not centre distance: two cabinets side by side on one wall are close but
        [EN] each keeps its own clearance. ★ `strict=False` is the **loose pass**: avoid overlap only.
        """
        for o_rect, o_zone in occupied:
            if _ovl(rect, o_rect):
                return False
            if strict and (_ovl(zone, o_rect) or _ovl(o_zone, rect)):
                return False
        return True

    def _inside(rect: tuple, zone: tuple | None = None, *,
                strict: bool = True) -> bool:
        """在退 pad 的内部区、不堵门、不与已放家具挤在一起。"""
        if (rect[0] < ix0 - 0.01 or rect[1] < iy0 - 0.01
                or rect[2] > ix1 + 0.01 or rect[3] > iy1 + 0.01):
            return False
        if _blocks(rect):
            return False
        return _clear_of_others(rect, zone if zone is not None else rect,
                                strict=strict)

    def _float_spot(w: float, h: float, standoff: float, sp, *,
                    strict: bool = True) -> tuple | None:
        """在离墙 ≥ standoff 的内部区域里找一个位置（中心 + 网格，必要时旋转）。

        Returns:
            `(矩形, 净空区)` 或 `None`（放不下）。
        """
        fx0, fy0, fx1, fy1 = ix0 + standoff, iy0 + standoff, ix1 - standoff, iy1 - standoff
        if w > fx1 - fx0 + 0.5 or h > fy1 - fy0 + 0.5:
            # 横放不下 ⇒ 试旋转（竖放）
            if h <= fx1 - fx0 + 0.5 and w <= fy1 - fy0 + 0.5:
                w, h = h, w
            else:
                return None
        cands: list[tuple] = []
        cands.append(((fx0 + fx1 - w) / 2.0, (fy0 + fy1 - h) / 2.0,
                      (fx0 + fx1 - w) / 2.0 + w, (fy0 + fy1 - h) / 2.0 + h))   # 中心
        for i in range(5):
            for j in range(4):
                xx = fx0 + (fx1 - fx0 - w) * i / 4.0
                yy = fy0 + (fy1 - fy0 - h) * j / 3.0
                cands.append((xx, yy, xx + w, yy + h))
        for c in cands:
            z = _zone(c, sp, 'float')
            if _inside(c, z, strict=strict):
                return c, z
        return None

    def _free_spots(wall: str, along_len: float, *, depth: float) -> list[float]:
        """这面墙上**所有**够长的空档起点（沿墙坐标）。

        ★ 原来只返回**第一个**空档：这件家具若在那个空档里撞了别的东西，
          整面墙就被判"没位置"，家具被赶到别的墙 —— 而同一面墙上明明还有位置
          （实测：六口柜只放进三件，门口那一段反而空着）。
        [EN] **Every** long-enough gap on this wall. ★ The old version returned only the **first**
        [EN] gap: if the piece collided there, the whole wall was judged "no room" and the piece was
        [EN] pushed to another wall while that wall still had space (measured: six cabinets, three
        [EN] placed, the stretch by the doorway left empty).
        """
        lo, hi = (ix0, ix1) if wall in ('top', 'bottom') else (iy0, iy1)
        room_depth = (iy1 - iy0) if wall in ('top', 'bottom') else (ix1 - ix0)
        if depth > room_depth - 1.0:
            return []
        busy = sorted(list(used[wall]) + list(blocked[wall]))
        out: list[float] = []
        pos = lo
        for a, b in busy:
            if pos + along_len <= a:
                out.append(pos)
            pos = max(pos, b + FR.ITEM_GAP)
        if pos + along_len <= hi:
            out.append(pos)
        return out

    def _rect_on(wall: str, pos: float, along_len: float, depth: float) -> tuple:
        if wall == 'top':
            return (pos, iy0, pos + along_len, iy0 + depth)
        if wall == 'bottom':
            return (pos, iy1 - depth, pos + along_len, iy1)
        if wall == 'left':
            return (ix0, pos, ix0 + depth, pos + along_len)
        return (ix1 - depth, pos, ix1, pos + along_len)

    # ── 摆放：① 浮置族先浮置（离墙留净空）② 贴墙族靠墙（含退化来的浮置件）──
    def _try_float(q, *, strict: bool) -> bool:
        """把这件浮置族家具浮起来（离墙 standoff，前后留净空）。"""
        nm = str(getattr(q, 'name', '') or '')
        sp = FR.spec_of(nm)
        w, h = FR.size_of(nm)
        standoff = min(max(sp.clear_px, pad), min(iy1 - iy0, ix1 - ix0) / 2.0)
        spot = _float_spot(w, h, standoff, sp, strict=strict)
        if spot is None:
            return False
        rect, zone = spot
        placed.append((nm, rect, 'float'))
        zones.append(zone)
        occupied.append((rect, zone))
        return True

    def _try_wall(q, *, strict: bool) -> bool:
        """把这件贴墙族家具靠墙放（上 → 下 → 左 → 右；corner 类先占角）。"""
        nm = str(getattr(q, 'name', '') or '')
        sp = FR.spec_of(nm)
        w, h = FR.size_of(nm)
        if sp.anchor == 'corner':
            for cx0, cy0 in ((ix0, iy0), (ix1 - w, iy0), (ix0, iy1 - h), (ix1 - w, iy1 - h)):
                rect = (cx0, cy0, cx0 + w, cy0 + h)
                zone = _zone(rect, sp, 'wall', wall='corner', along=(w, h))
                if _inside(rect, zone, strict=strict):
                    placed.append((nm, rect, 'wall'))
                    zones.append(zone)
                    occupied.append((rect, zone))
                    return True
        for wall in ('top', 'bottom', 'left', 'right'):
            aw, ad = FR.size_of(nm, vertical=(wall in ('left', 'right')))
            for pos in _free_spots(wall, aw, depth=ad):
                rect = _rect_on(wall, pos, aw, ad)
                zone = _zone(rect, sp, 'wall', wall=wall, along=(aw, ad))
                if not _inside(rect, zone, strict=strict):
                    continue
                placed.append((nm, rect, 'wall'))
                zones.append(zone)
                occupied.append((rect, zone))
                used[wall].append((pos, pos + aw))
                return True
        return False

    # 浮置族（按面积从大到小）与贴墙族
    float_ids: set[int] = set()
    fl: list = []
    wl: list = []
    for q in items:
        nm = str(getattr(q, 'name', '') or '')
        sp = FR.spec_of(nm)
        if FR.is_float(sp):
            float_ids.add(id(q))
            fl.append(q)
        elif FR.against_wall(sp):
            wl.append(q)
    fl.sort(key=lambda q: -float(_area_of(FR.size_of(getattr(q, 'name', '')))))

    # ★ 两档：严格（守净空）→ 宽松（只避重叠）。宽松档摆进去的**报"净空不足"**，
    #   不许悄悄把家具塞进去。
    todo: list = list(items)
    for strict in (True, False):
        if not todo:
            break
        still_float: list = []
        for q in todo:
            if id(q) in float_ids and _try_float(q, strict=strict):
                continue
            still_float.append(q)
        # 贴墙族先排；浮置不下、退化成贴墙的排在后面
        wall_first = [q for q in still_float if id(q) not in float_ids]
        degraded = [q for q in still_float if id(q) in float_ids]
        nxt: list = []
        for q in wall_first + degraded:
            if not _try_wall(q, strict=strict):
                nxt.append(q)
        todo = nxt
    dropped.extend(todo)

    # ── 净空够不够：**事后**再核一遍（宽松档摆进去的、或者被后来者挤掉的）──
    tight: list[str] = []
    for i in range(len(placed)):
        ri, zi = placed[i][1], zones[i]
        for j in range(i + 1, len(placed)):
            rj, zj = placed[j][1], zones[j]
            if _ovl(zi, rj) or _ovl(zj, ri):
                for k in (i, j):
                    if placed[k][0] not in tight:
                        tight.append(placed[k][0])

    return placed, dropped, tight


def _area_of(sz: tuple) -> float:
    return float(sz[0]) * float(sz[1])



def _overlaps(a: tuple, b: tuple, tol: float = 1.0) -> bool:
    """两个矩形是否重叠（留 `tol` 容差，贴着边不算重叠）。
        English: whether two rectangles overlap (with a `tol` tolerance; touching edges do not count).
    """
    return (min(a[2], b[2]) - max(a[0], b[0]) > tol
            and min(a[3], b[3]) - max(a[1], b[1]) > tol)


# ══════════════════════════════════════════════════════════════════════
#  五、审核：这份解算**合不合理**（只读，不改任何东西）
# [EN] 5. Audit: is this solved plan reasonable (read-only, changes nothing)
# ══════════════════════════════════════════════════════════════════════
# 问题的名字（判据按它们认，别改成别的字）
# [EN] Problem names (criteria identify by these; do not rename)
K_NOT_TILED = '房间没拼满外轮廓'
K_OVERLAP = '两间房叠在一起'
K_DOOR_OFF_WALL = '门没开在墙上'
K_FIXTURE_OUTSIDE = '陈设跑到所属房间外面'
K_FIXTURE_NO_OWNER = '陈设没说归哪间房'
K_DISCONNECTED = '从大门走不到这间'
K_NOT_ADJACENT = '要求相邻却没挨上'
K_NO_ENTRY = '没有通向街面的门'
K_WRONG_FLOOR = '楼上的空间混进了本层'
K_TINY = '这间小到认不出来'
K_TIGHT = '陈设净空不足'


def _area(b: tuple) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _overlap(a: tuple, b: tuple) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if (w > 0 and h > 0) else 0.0


def _inside(inner: tuple, outer: tuple, tol: float = 0.6) -> bool:
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def audit(fp: FloorPlan, prog: Program | None = None) -> list[str]:
    """审核一层平面，返回**问题清单**（空表 = 没问题）。每条都是可数、可解释的。

    十类问题，每一类都对应一条"用户看得见"的毛病：

    | 问题 | 用户看到的是 |
    |---|---|
    | 没拼满 | 房间之间有空隙（图上出现不属于任何房间的白块） |
    | 两间叠加 | 两个房间压在一起 |
    | 门没开在墙上 | 门悬在空中 / 在房子外面 |
    | 陈设跑出去 | 家具画到墙外 |
    | 陈设没说归谁 | 家具不知道放哪，只能乱摆 |
    | 走不到 | 有间房没有门（进不去） |
    | 要求相邻却没挨上 | 该连的两间（堂屋—院）中间隔着别的 |
    | 没有街门 | 房子没有入口 |
    | 楼上混进本层 | 二楼出现在一层图上 |
    | 小到认不出 | 那间缩成一个点 |

    [EN] Audit one floor, returning a **problem list** (empty = fine). Ten kinds, each matching a
    [EN] visible defect: gaps, overlap, door not on a wall, fixture outside its room, fixture without
    [EN] an owner, unreachable room, required adjacency not met, no street door, upper-floor space
    [EN] leaked onto this floor, room too small to recognise.
    """
    out: list[str] = []
    if not fp.rooms:
        return out
    env = fp.envelope

    # ① 拼满：所有房间面积和 == 外轮廓面积
    tot = sum(_area(b) for b in fp.rooms.values())
    if abs(tot - _area(env)) > 0.5:
        out.append(f'{K_NOT_TILED}：房间合计 {tot:.0f}、外轮廓 {_area(env):.0f}'
                   f'（差 {tot - _area(env):+.0f} px²）')

    # ② 两两不叠
    names = list(fp.rooms)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a = _overlap(fp.rooms[names[i]], fp.rooms[names[j]])
            if a > 0.5:
                out.append(f'{K_OVERLAP}：「{names[i]}」与「{names[j]}」'
                           f'重叠 {a:.0f} px²')

    # ③ 太小的房间
    for nm, b in fp.rooms.items():
        if min(b[2] - b[0], b[3] - b[1]) < MIN_ROOM_PX * 0.65:
            out.append(f'{K_TINY}：「{nm}」只有 '
                       f'{b[2] - b[0]:.0f}×{b[3] - b[1]:.0f} px')

    # ④ 门必须开在墙上
    walls = _wall_segments(fp)
    for d in fp.doors:
        if not _on_wall(d, walls):
            out.append(f'{K_DOOR_OFF_WALL}：「{d.a}」的门在 '
                       f'({d.x:.0f},{d.y:.0f}) 不落在任何一道墙上')

    # ⑤ 陈设在所属房间里
    for nm, (owner, box) in fp.fixtures.items():
        ob = fp.rooms.get(owner)
        if ob is None:
            out.append(f'{K_FIXTURE_NO_OWNER}：「{nm}」说属于「{owner}」，'
                       f'但这一层没有这间房')
        elif not _inside(box, ob):
            out.append(f'{K_FIXTURE_OUTSIDE}：「{nm}」不在「{owner}」里')

    # ⑤b **放不下的陈设**也要报（它们没进 `fixtures`，不查这一格就永远看不见）
    # [EN] (5b) **Unplaced fixtures** must be reported too: they never reach `fixtures`, so without
    # [EN] this check they are invisible forever.
    for nm, owner in fp.orphans.items():
        if owner:
            out.append(f'{K_FIXTURE_NO_OWNER}：「{nm}」说属于「{owner}」，'
                       f'但这一层没有这间房')
        else:
            out.append(f'{K_FIXTURE_NO_OWNER}：「{nm}」没写归属哪间房，放不进去')

    # ⑤c **净空不足**的陈设也要报：它**在图上**（所以 ⑤ 查不出来），
    #   但它要求留白的那块地方被占了 —— 用户看到的是"柜台前头堵着个柜子"。
    # [EN] (5c) **Fixtures with insufficient clearance** must be reported too: they **are** on the
    # [EN] map (so check 5 cannot see them), but the space they need is occupied -- the user sees a
    # [EN] cabinet jammed in front of the counter.
    for nm, owner in (fp.tight or {}).items():
        out.append(f'{K_TIGHT}：「{nm}」在「{owner}」里站人的地方被占了')

    # ⑥ 连通：从入口按门走，能不能到每一间
    unreachable = _unreachable(fp, prog)
    for nm in unreachable:
        out.append(f'{K_DISCONNECTED}：「{nm}」（从大门按门走不进来）')

    # ⑦ 要求相邻的两间，必须真有共用墙
    if prog is not None:
        for a, b in prog.adjacent:
            if a in fp.rooms and b in fp.rooms:
                if shared_wall(fp.rooms[a], fp.rooms[b]) is None:
                    out.append(f'{K_NOT_ADJACENT}：「{a}」与「{b}」')
        # ⑧ 有临街门就必须真开出来 —— **只查入口那一层**。
        #    ⚠ 二楼不许有临街门（悬空）；所以这条判据也必须按层问，
        #      否则二楼会被报"没有通向街面的门"（假红，实测出现过）。
        # [EN] (8) if the program says there is a street door, it must be cut -- **only on the
        # [EN] entry's floor**. ⚠ An upper floor cannot have one (it would hang in the air), so the
        # [EN] criterion must be floor-aware; otherwise floor 2 is reported as "no street door"
        # [EN] (a false red, measured).
        if (prog.has_gate and prog.entry in fp.rooms
                and not any(not d.b for d in fp.doors)):
            out.append(f'{K_NO_ENTRY}：任务书说临街有门，但没有开在外墙上')
        # ⑨ 楼层不许串
        for s in prog.spaces:
            if not s.is_fixture() and s.floor != fp.floor and s.name in fp.rooms:
                out.append(f'{K_WRONG_FLOOR}：「{s.name}」属于 {s.floor} 层')
    return out


def _wall_segments(fp: FloorPlan) -> list[tuple]:
    """这一层所有的墙段（`(along, 位置, 起, 止)`，像素）。

    ★ 墙段**从房间矩形的边推出来**，不另存一份 —— 这就是"审核与绘制同一份几何"。
      另存一份必然漂（本项目的老坑）。
    [EN] Every wall segment on this floor: `(along, coord, start, end)` in pixels.
    [EN] ★ Segments are **derived from the room rects**, never stored separately -- that is the
    [EN] "audit and drawing share one geometry" rule (a second copy always drifts).
    """
    horiz: set = set()
    vert: set = set()
    for b in fp.rooms.values():
        horiz.add((round(b[1], 3), round(b[0], 3), round(b[2], 3)))
        horiz.add((round(b[3], 3), round(b[0], 3), round(b[2], 3)))
        vert.add((round(b[0], 3), round(b[1], 3), round(b[3], 3)))
        vert.add((round(b[2], 3), round(b[1], 3), round(b[3], 3)))
    return ([('h',) + s for s in horiz] + [('v',) + s for s in vert])


def _on_wall(d: Opening, walls: list, tol: float = 1.2) -> bool:
    """门心是否落在某道墙上（且门洞宽度装得下）。"""
    for along, coord, lo, hi in walls:
        if along != d.along:
            continue
        pos, lo2, hi2 = (d.y, d.x - d.w / 2, d.x + d.w / 2) if along == 'h' \
            else (d.x, d.y - d.w / 2, d.y + d.w / 2)
        if abs(pos - coord) <= tol and lo2 >= lo - tol and hi2 <= hi + tol:
            return True
    return False


def _unreachable(fp: FloorPlan, prog: Program | None) -> list[str]:
    """从入口按**门**走一遍，返回走不到的房间。
        English: Walk from the entry **through doors**, returning unreachable rooms.
    """
    if not fp.rooms:
        return []
    ent = ''
    if prog is not None and prog.entry in fp.rooms:
        ent = prog.entry
    if not ent:
        # 没有入口（不该发生）：以门最多的那间当起点，免得整层都被报成"走不到"
        ent = next(iter(fp.rooms))
    graph: dict[str, set] = {r: set() for r in fp.rooms}
    for d in fp.doors:
        if d.b and d.a in graph and d.b in graph:
            graph[d.a].add(d.b)
            graph[d.b].add(d.a)
    seen = {ent}
    queue = [ent]
    while queue:
        cur = queue.pop(0)
        for nb in sorted(graph[cur]):
            if nb not in seen:
                seen.add(nb)
                queue.append(nb)
    return [r for r in fp.rooms if r not in seen]


def feedback(prog: Program, issues_by_floor: dict) -> str:
    """把审核结果写成**给美术看的整改意见**（纯文本，回给模型让它改任务书）。

    ★ 为什么不是把坐标回给它：美术**不该**改坐标（上一轮它改坐标的后果就是那 9 个错点）。
      它该改的是**任务书** —— 加一间、删一间、说清谁挨着谁、哪间见天、几层。
      所以这里的每一条都写成**对它那种输入**的要求。
    ★ 为什么要把"现在是什么"也写进去：模型看不到图，只看到任务书；
      不告诉它现状，它会把已经对的部分一起改坏。
    [EN] Turn the audit into **revision notes for art** (plain text, sent back for a program
    [EN] revision). ★ Why not send coordinates back: art must **not** touch coordinates (that is how
    [EN] those nine wrong points appeared); it should change the **program**. So every line is phrased
    [EN] as a requirement on that input. ★ Why repeat the current state: the model cannot see the map,
    [EN] only the program; without the current state it would break the parts that are already right.
    """
    cur = prog.to_dict()
    lines = ['── 现在的任务书 ──',
             f"地点：{cur['地点'] or '（未命名）'}",
             '空间：' + '；'.join(
                 f"{s['名称']}（{s['层']}层"
                 + ('·见天' if s['见天'] else '')
                 + (f"·在{s['归属']}里" if s['归属'] else '')
                 + f"·面积{s['面积']:.1f}）"
                 for s in cur['空间']),
             '邻接：' + ('；'.join(f"{a}—{b}" for a, b in cur['邻接']) or '（无）'),
             '并排：' + ('；'.join('+'.join(g) for g in cur['并排']) or '（无）'),
             f"入口：{cur['入口'] or '（未定）'}｜街面：{cur['街面']}｜临街门："
             + ('有' if cur['临街门'] else '无'),
             '', '── 上一版平面解算后的不合格处 ──']
    n = 0
    for fl, issues in sorted((issues_by_floor or {}).items()):
        if not issues:
            continue
        lines.append(f'第 {fl} 层：')
        for it in issues:
            n += 1
            lines.append(f'  · {it}')
    if not n:
        lines.append('（无）')
    lines += ['', '── 请只改任务书，别写坐标 ──',
              '按上面每一条修：该加的加、该并排的并排、该说清归属的说清。'
              '仍然只输出同一份 JSON 形状。']
    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════
#  六、适配层：解算结果 → 渲染层已经在用的 `plan_audit.Plan`
# [EN] 6. Adapter: solved result -> the `plan_audit.Plan` the renderers already consume
# ══════════════════════════════════════════════════════════════════════
def to_plan(fp: FloorPlan, *, detail: str = '', current: str = '',
            place: str = ''):
    """把一层解算结果包成 `plan_audit.Plan`，**渲染层一行都不用改**。

    ★ 这是这次改造里最省事的一步：`floorplan._draw_plan` 与 `minimap.build_shapes`
      本来就是"照 `Plan` 画"。只要给出同一个 `Plan` 形状，两个渲染器直接受益 ——
      不需要在绘制代码里再写第二套房间算法（那正是本项目反复栽的坑）。
    ⚠ 唯一新增的是 `Plan.doors`（墙上的门洞）。渲染层不认识它时**只是不画门**
      （门不会画错，只是没画）—— 降级是安全的。
    [EN] Wrap one floor into a `plan_audit.Plan` so **the renderers need no changes**: both
    [EN] `floorplan._draw_plan` and `minimap.build_shapes` already draw from a `Plan`; giving them the
    [EN] same shape avoids a second room algorithm in the drawing code (this project's recurring pit).
    [EN] ⚠ The only new field is `Plan.doors`; a renderer that ignores it simply draws no doors --
    [EN] a safe degradation.
    """
    from image_gen import plan_audit as PA
    plan = PA.Plan(detail=detail)
    plan.house = fp.envelope
    for nm, b in fp.rooms.items():
        plan.rooms[nm] = PA.Room(name=nm, box=b, label=nm[:3],
                                 here=(nm == current))
    yard = fp.yard()
    if yard is not None:
        plan.yard = yard
        # 院子里的东西（井这类）也要给渲染层：它按 `yard_pts` 画符号
        for nm, (owner, box) in fp.fixtures.items():
            if owner in fp.sky:
                plan.yard_pts[nm] = ((box[0] + box[2]) / 2.0,
                                    (box[1] + box[3]) / 2.0)
    for nm, (owner, box) in fp.fixtures.items():
        plan.fixtures[nm] = (owner, ((box[0] + box[2]) / 2.0,
                                     (box[1] + box[3]) / 2.0))
        plan.fix_boxes[nm] = box
    plan.frames = {'house': [(fp.envelope[0], fp.envelope[1]),
                             (fp.envelope[2], fp.envelope[1]),
                             (fp.envelope[2], fp.envelope[3]),
                             (fp.envelope[0], fp.envelope[3])]}
    plan.doors = [d.to_dict() for d in fp.doors]
    plan.stairs = list(fp.stairs)
    plan.place = place
    plan.floor = fp.floor
    return plan
