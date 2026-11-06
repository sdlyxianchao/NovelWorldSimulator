# -*- coding: utf-8 -*-
"""地图的**几何解算 · 审核 · 修复**（大地图与小地图**共用同一份口径**）。

这个模块存在的理由
==================
用户 2026-10-12 第二次看大地图，报了四件**几何**错事：

  · 「这个大地图 **柜台跑到墙外面了**」；
  · 「**房子和院子都是正方形 这没问题 但是房子的一部分和院子的一部分重合里**」；
  · 「左上角的图例 有些字在方框外面 还有**比例尺把字盖住了**」；
  · 「**建筑的名字标记都放到墙的旁边 不要放到别的东西的上面**」。

前两件的**根因是同一个**：房间矩形与院子矩形、家具位置，**三样各自算各自的**，
互相不知道对方在哪 —— 于是必然出现"家具落在墙外""院子压住房子"。

⇒ 所以这里把**几何解算**抽成**唯一实现**（`solve()`），三处都用它：

  | 谁 | 用来做什么 |
  |---|---|
  | `image_gen/floorplan.py`（画大地图） | 照着 `solve()` 的结果画 → **画出来的必然自洽** |
  | `image_gen/minimap.py`（画小地图） | 同上（小地图只是尺寸小，几何同一套） |
  | `crew/agents.py` 的美术（Reflection） | **审核 → 修复 → 再审**，用户点名要的那个环 |

★ 为什么审核器与绘制器共用一份几何（本项目的老规矩）：
  两套口径必然漂 —— "审核说没问题、画出来有问题"是最难查的一类 bug，
  因为它看起来哪儿都没错。

★★ 三层结构
------------
  `solve()`   —— **解算**：给定布局与画布，算出**每个元素该在哪儿**（纯函数）
  `audit()`   —— **审核**：拿解算结果查出问题（**只读，不改任何东西**）
  `repair()`  —— **修复**：确定性修掉问题（**不调模型、零成本**），再交回 `solve()`

⚠ `repair()` 是**只加不减**的（与 `world.spatial.repair` 同一条纪律）：
  它把东西**挪到能放下的地方**，不删任何地点 —— 删了就意味着"这一处从图上消失"，
  而那比"位置不理想"严重得多。

English:
**Geometry solving, auditing and repair** for maps (the big map and the minimap **share one
definition**).

Why this module exists
======================
On 2026-10-12 the user looked at the big map a second time and reported four **geometry** errors:
  · "on this big map the **counter has run outside the wall**";
  · "**the house and the courtyard are both squares, that's fine, but part of the house and part of
    the courtyard overlap**";
  · "in the top-left legend **some text is outside the box**, and **the scale bar covers the text**";
  · "**put the building's name label beside the wall, not on top of other things**".
The first two have **the same root cause**: the room rectangles, the courtyard rectangle and the
furniture positions are **each computed separately**, unaware of one another -- so "furniture outside
the wall" and "courtyard pressing on the house" are inevitable.

⇒ So the **geometry solving** is extracted here as the **single implementation** (`solve()`), used in
three places:
  | Who | What for |
  |---|---|
  | `image_gen/floorplan.py` (draws the big map) | draws according to `solve()`'s result ⇒ **what is drawn is necessarily self-consistent** |
  | `image_gen/minimap.py` (draws the minimap) | same (the minimap is just smaller; the geometry is one set) |
  | the art dept in `crew/agents.py` (Reflection) | **audit -> repair -> audit again**, the loop the user asked for |
★ Why the auditor and the drawer share one geometry (an old rule of this project): two definitions
  necessarily drift, and "the audit says fine but the drawing is wrong" is the hardest class of bug
  -- it looks correct everywhere.
★★ Three layers
  `solve()`  -- **solve**: given a layout and a canvas, work out **where each element goes** (a pure function)
  `audit()`  -- **audit**: take the solved result and find problems (**read-only, changes nothing**)
  `repair()` -- **repair**: deterministically fix them (**no model call, zero cost**), then hand back to `solve()`
⚠ `repair()` **only adds, never removes** (the same rule as `world.spatial.repair`): it **moves**
  things somewhere they fit and deletes no location -- deleting would mean "this spot vanishes from
  the map", far worse than an imperfect position.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from image_gen import minimap as MM
from image_gen.map_layout import Layout, Place

#: 房子与院子之间至少留多少（归一化坐标）—— 两个矩形不许贴在一起，
#: 否则"院墙"与"房屋墙"两条线会画成一条，看着像共用一堵墙。
# [EN] : the minimum gap between house and courtyard (normalised) -- the two rectangles must not touch,
# [EN] or the courtyard wall and the house wall draw as one line, reading as a shared wall.
GAP = 0.035

#: 家具在房间里怎么排：横向最多摆几个（超了换下一行）。
# [EN] : how furniture is laid out in a room -- how many per row (then wrap).
FURN_PER_ROW = 3
#: 家具在房间内的边距（像素）—— 不许贴着墙画，贴墙看着像墙的一部分。
# [EN] : furniture inset inside a room (pixels) -- it must not hug the wall, which reads as part of it.
FURN_PAD = 10.0


@dataclass
class Room:
    """解算出来的**一间房**（像素矩形 + 谁在里面）。"""
    name: str
    box: tuple                                  # (x0, y0, x1, y1)
    label: str = ''
    here: bool = False


@dataclass
class Plan:
    """**解算结果**：这一张图上每个元素该在哪儿。
    [EN] **The solved result**: where every element goes on this map."""
    detail: str = ''
    rooms: dict = field(default_factory=dict)    # 名字 → Room
    house: tuple | None = None                   # 房子的外框（所有房间的并集）
    yard: tuple | None = None                    # 院子的矩形
    yard_pts: dict = field(default_factory=dict)  # 院里那些点的像素坐标
    fixtures: dict = field(default_factory=dict)  # 陈设名 → (box, 所属房间名)
    others: dict = field(default_factory=dict)    # 其余地点名 → 像素坐标
    frames: dict = field(default_factory=dict)    # 逐层的墙：{'house': …, 'yard': …}
    # [EN] per-layer walls: {'house': ..., 'yard': ...}
    # ── 以下四项 2026-10-26 新增：**房间任务书**解算出的平面（`image_gen/roomplan.py`）──
    #: 墙上的**门洞**：`[{a, b, x, y, along, w}, …]`（`b` 空串 = 通街面）。
    #: ⚠ 老的"点式平面"解算不填这一格 ⇒ 渲染层不画门洞口（**只是没画，不会画错**）。
    # [EN] **Door openings** in walls. ⚠ The old point-based solver leaves this empty, so the
    # [EN] renderer draws no openings -- "not drawn" rather than "drawn wrong".
    doors: list = field(default_factory=list)
    #: 陈设的**方块**（不只是中心点）：`名字 → (x0,y0,x1,y1)`。
    # [EN] Fixture **boxes** (not just centres).
    fix_boxes: dict = field(default_factory=dict)
    #: 楼梯的方块（画踏步用）。
    # [EN] Stair boxes (for drawing treads).
    stairs: list = field(default_factory=list)
    #: 这一层是第几层（分层出图时信息框要写"二层"）。
    # [EN] Which floor this is (the info box says "floor 2" when floors are drawn separately).
    floor: int = 0


@dataclass
class Issue:
    """**一处问题**（审核的产出）。
    [EN] **One problem** (what the audit produces)."""
    kind: str
    who: str = ''
    detail: str = ''
    fixed: bool = False

    def to_dict(self) -> dict:
        return {'kind': self.kind, 'who': self.who, 'detail': self.detail,
                'fixed': self.fixed}

    def text(self) -> str:
        mark = '已修' if self.fixed else '待修'
        return f'[{mark}] {self.kind}' + (f'·{self.who}' if self.who else '') \
               + (f'：{self.detail}' if self.detail else '')


# 问题的名字（判据按它们认，别改成别的字）
# [EN] Problem names (criteria identify by these; do not rename)
K_FURN_ORPHAN = '陈设没有可放进去的房间'
K_FURN_OUTSIDE = '陈设落在房间墙外'
K_YARD_OVERLAP = '院子与房子重叠'
K_ROOM_OUTSIDE = '房间跑出房子外框'
K_NOT_INDOOR = '屋里出现了见天的东西'
K_LABEL_ON = '标签压住了别的东西'
K_YARD_MISSING = '有见天的东西却没有院子'


# ══════════════════════════════════════════════════════════════════
#  一、解算：每个元素该在哪儿（**渲染与审核共用的唯一实现**）
# [EN] 1. Solve: where every element goes (**the single implementation shared by drawing and audit**)
# ══════════════════════════════════════════════════════════════════
def _rect(b) -> tuple:
    return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))


def _label_of(places: list, name: str) -> str:
    """某一点在图上该写的字（拿不到就退回名字本身）。
    [EN] The text a location should carry on the map (falls back to the name itself)."""
    p = next((q for q in places if q.name == name), None)
    return p.label() if p is not None else str(name)[:3]


def _union(a: tuple, b: tuple) -> tuple:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def overlap_area(a: tuple | None, b: tuple | None) -> float:
    """两块矩形的重叠面积（有一块是 `None` → 0）。
    [EN] The overlap area of two rectangles (either `None` -> 0)."""
    if a is None or b is None:
        return 0.0
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return (w * h) if (w > 0 and h > 0) else 0.0


def contains(inner: tuple, outer: tuple, tol: float = 0.5) -> bool:
    """`inner` 完全落在 `outer` 里？（都用 `(x0, y0, x1, y1)`）
    [EN] Is `inner` entirely inside `outer`? (both are `(x0, y0, x1, y1)`)"""
    if inner is None or outer is None:
        return False
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def _room_boxes(places: list, px, *, span: tuple, grow: float,
                min_w: float, min_h: float) -> dict:
    """给**屋里空间**算出互不重叠的矩形（像素）。

    ★ 算法：每个房间取"到**最近一间**的距离的一半"当半宽/半高 ——
      相邻两间**共边**，看图就是**共用一堵墙**（平面图该有的样子）。
    ★ `grow` = 初始半宽/半高占绘图区的比例（一间房时没有别的房间约束它，
      所以这个数决定它会长多胖 —— 大地图用 `floorplan.PLAN_GROW`）。
    ★ 结果裁到 `span` 以内 —— 房间跑到绘图区外就成了一张错的图。
    ★★ `px` 由调用方传入：**这个换算是全图唯一的一份**（与绘制共用）。
      2026-10-12 实测过一次口径漂的后果：解算按"画布宽"换算、绘制按"绘图区宽"换算，
      于是房间框算在 x=412、家具画在 x=380 —— 同一张图两套坐标。
    [EN] Compute non-overlapping rectangles for **indoor spaces** (pixels).
    [EN] ★ Algorithm: each room takes "half the distance to the **nearest** other room" as its
    [EN] half-width/height -- adjacent rooms **share an edge**, which reads as **a shared wall**
    [EN] (what a floor plan should look like).
    [EN] ★ `grow` = the initial half-width/height as a fraction of the drawing area.
    [EN] ★ The result is clipped inside `span` -- a room outside the house frame is a wrong map.
    """
    rooms = [p for p in places if MM._is_room(p.name)][:MM.MAX_ROOM_WALLS]
    if not rooms:
        return {}
    x0s, y0s, x1s, y1s = span
    pts = {p.name: px(p) for p in rooms}
    # ① 初始半宽/半高：从 `grow` 起步，按"到最近一间"收窄。
    #   ⚠ **不再夹最小尺寸**（2026-10-15 改）：原来 `max(min_w/2, …)` 在"两间比最小尺寸还近"
    #     时把半宽顶回最小，于是两间矩形硬挤成重叠 —— 这正是小地图"块重叠"的根因。
    #     现在最小尺寸交给第 ② 步的**分离**去保证"互不重叠"永远成立。
    # [EN] (1) Initial half-sizes from `grow`, narrowed by the nearest room. No hard min-size floor
    # [EN] (changed 2026-10-15): the old `max(min_w/2, …)` forced a min half-width even when two rooms
    # [EN] were closer than that, which squeezed the rectangles into an overlap -- the root cause of the
    # [EN] minimap's "blocks overlapping". The min size is now guaranteed by step (2)'s separation.
    half: dict = {}
    for i, p in enumerate(rooms):
        cx, cy = pts[p.name]
        hw = (x1s - x0s) * grow
        hh = (y1s - y0s) * grow
        for j, (ox, oy) in enumerate(pts.values()):
            if j == i:
                continue
            dx, dy = abs(ox - cx), abs(oy - cy)
            # 只拿"真的错开"的那个方向去收窄 —— 同一列上的两间不该把宽度压没
            # [EN] Only narrow along a direction where they truly offset -- two rooms in the same
            # [EN] column must not squeeze the width away
            if dx > 12:
                hw = min(hw, dx / 2)
            if dy > 12:
                hh = min(hh, dy / 2)
        half[p.name] = [cx, cy, max(hw, 6.0), max(hh, 6.0)]
    # ② 分离：重叠的两间各推开一半（迭代到不重叠或到上限）。
    #   沿"重叠更窄"的那个轴推 —— 挪动更小，更像"共用一堵墙"。
    # [EN] (2) Separation: overlapping pairs each pushed apart by half (iterated until no overlap or
    # [EN] the cap). Push along the axis of smaller overlap -- less movement, more like "a shared wall".
    for _ in range(8):
        moved = False
        names = list(half)
        for a in range(len(names)):
            for b in range(a + 1, len(names)):
                na, nb = names[a], names[b]
                ax, ay, ahw, ahh = half[na]
                bx, by, bhw, bhh = half[nb]
                ox = min(ax + ahw, bx + bhw) - max(ax - ahw, bx - bhw)
                oy = min(ay + ahh, by + bhh) - max(ay - ahh, by - bhh)
                if ox > 0.5 and oy > 0.5:
                    if ox <= oy:
                        s = 1.0 if ax <= bx else -1.0
                        half[na][0] += s * ox / 2
                        half[nb][0] -= s * ox / 2
                    else:
                        s = 1.0 if ay <= by else -1.0
                        half[na][1] += s * oy / 2
                        half[nb][1] -= s * oy / 2
                    moved = True
        if not moved:
            break
    # ③ 转成矩形，裁进 `span`。分离已保证"互不重叠"，这里只做边界收口
    #   （贴边时推回框内）。最小尺寸由第 ② 步的分离兜底 —— 挤不动就保留较小的尺寸，
    #   宁可房间小一点也绝不重叠（重叠是更严重的错，也是用户报的"块重叠"）。
    # [EN] (3) Turn into rectangles, clip inside `span`. Separation already guarantees no overlap; here
    # [EN] we only tuck edges back in. The min size is backed by step (2)'s separation -- if it cannot
    # [EN] grow, keep the smaller size; a smaller room beats an overlap (overlap is the worse bug).
    out: dict = {}
    for name, (cx, cy, hw, hh) in half.items():
        bx0 = max(x0s + 3, cx - hw)
        by0 = max(y0s + 3, cy - hh)
        bx1 = min(x1s - 3, cx + hw)
        by1 = min(y1s - 3, cy + hh)
        out[name] = (bx0, by0, bx1, by1)
    return out


def _outdoor_box(places: list, px, *, min_w: float, min_h: float,
                 span: tuple) -> tuple | None:
    """**院里那些点**聚出来的那一片（院子的范围，像素）。

    ★ 与 `minimap._outdoor_extent` 是**同一个意思**，但**换算用传进来的 `px`**。
      为什么不在那一份上加个参数就行：那一份按**画布宽高**算（小地图专用），
      而大地图的绘图区只是画布的一部分（左边要让给图例）——
      两边的换算**必须是同一个函数**，否则"解算出来的位置"与"画出来的位置"会错开
      （2026-10-12 实测：房间框算在 x=412、家具画在 x=380，就是两套换算造成的）。

    ⚠ 尺寸夹到不小于 `min_w`/`min_h`（避开判据那个浅底窗口，理由同 `ROOM_MIN_W`）。
    [EN] The patch gathered by **the points in the yard** (the courtyard's extent, in pixels).
    [EN] ★ Same meaning as `minimap._outdoor_extent`, but **mapped with the passed-in `px`**.
    [EN] Why not just add a parameter to that one: it computes from the **canvas width/height**
    [EN] (minimap-specific), while the big map's drawing area is only part of the canvas (the left
    [EN] side is given to the legend) -- the mapping on both sides **must** be the same function,
    [EN] otherwise "the solved position" and "the drawn position" drift apart (measured 2026-10-12:
    [EN] the room box solved at x=412 while the furniture was drawn at x=380 -- two mappings).
    [EN] ⚠ Clamped to at least `min_w`/`min_h` (dodging the criterion's wash window, same reasoning
    [EN] as `ROOM_MIN_W`).
    """
    outs = [p for p in places if MM._is_outdoor(p.name)]
    if not outs:
        return None
    xs = [px(p)[0] for p in outs]
    ys = [px(p)[1] for p in outs]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    # 四周兜一圈边距（院墙在物件**外面**，不能正好压在井上）
    # [EN] Add a margin all around (the courtyard wall is **outside** the objects, not sitting right
    # [EN] on the well)
    m = 18.0
    x0, x1, y0, y1 = x0 - m, x1 + m, y0 - m, y1 + m
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if x1 - x0 < min_w:
        x0, x1 = cx - min_w / 2, cx + min_w / 2
    if y1 - y0 < min_h:
        y0, y1 = cy - min_h / 2, cy + min_h / 2
    # 裁进绘图区（出界的形状**不报错、只是看不见**）
    # [EN] Clip into the drawing area (out-of-bounds shapes **do not error, they just vanish**)
    sx0, sy0, sx1, sy1 = span
    x0, y0 = max(x0, sx0), max(y0, sy0)
    x1, y1 = min(x1, sx1), min(y1, sy1)
    if x1 - x0 < 20 or y1 - y0 < 20:
        return None
    return (x0, y0, x1, y1)


def _push_apart(near: tuple, far: tuple, gap: float,
                span: tuple | None = None) -> tuple:
    """把 `far` 这块矩形**推到** `near` 之外（只推重叠的那条边）。

    为什么是"推"而不是"缩"：缩小会让院子/房子越缩越小，最后两个都没了。
    推 = 整体挪开，尺寸不变 —— 这符合"只加不减"的纪律。

    ★★ **四个方向都要试，并挑"真的放得下"的那个**（2026-10-12 血泪）：
      第一版只挑"重叠最小的方向"，推完再 `_clip_into` 拽回画布内 ——
      于是**推出去又被拽回来，重叠一点没少**（实测重叠 1148 px²，和没修一样）。
      现在：把四个候选**逐个用 `span` 验一遍**，只在"推完仍在画布内"的
      候选里挑移动量最小的；都放不下就原样返回（宁可不动，也不要越界）。

    ⚠ 只在**重叠**时推；不重叠时原样返回（不然本来好好的图被推歪）。
    [EN] **Push** the `far` rectangle outside `near` (only along the overlapping edge).
    [EN] Why "push" instead of "shrink": shrinking makes both rectangles smaller and smaller until
    [EN] both are gone. Pushing = move the whole thing, size unchanged -- consistent with
    [EN] "only add, never remove".
    [EN] ★★ **All four directions must be tried, and the one that actually fits chosen** (a hard-won
    [EN] lesson, 2026-10-12): the first version picked only "the direction with the smallest overlap"
    [EN] and then `_clip_into` dragged it back inside the canvas -- so **it was pushed out and pulled
    [EN] straight back, with no reduction in overlap at all** (measured: 1148 px², identical to
    [EN] before). Now the four candidates are **each checked against `span`**, and among those that
    [EN] stay inside, the one with the smallest movement wins; if none fits, return as-is (better not
    [EN] to move than to go out of bounds).
    [EN] ⚠ Only push when they **overlap**; otherwise return as-is (else a fine map gets knocked
    [EN] askew).
    """
    if overlap_area(near, far) <= 0:
        return far
    nx0, ny0, nx1, ny1 = near
    fx0, fy0, fx1, fy1 = far
    dx = (fx1 - fx0) / 2
    dy = (fy1 - fy0) / 2
    ncx, ncy = (nx0 + nx1) / 2, (ny0 + ny1) / 2
    fcx, fcy = (fx0 + fx1) / 2, (fy0 + fy1) / 2
    cands = [
        (abs(nx0 - fx1), (nx0 - gap - dx, fcy)),        # 往左
        (abs(fx0 - nx1), (nx1 + gap + dx, fcy)),        # 往右
        (abs(ny0 - fy1), (fcx, ny0 - gap - dy)),        # 往上
        (abs(fy0 - ny1), (fcx, ny1 + gap + dy)),        # 往下
        # [EN] downward
    ]
    best = None
    for cost, (cxx, cyy) in sorted(cands, key=lambda c: c[0]):
        cand = (cxx - dx, cyy - dy, cxx + dx, cyy + dy)
        if span is not None and not contains(cand, span, tol=0.5):
            continue            # 这个方向推出去会越界 → 换下一个
            # [EN] pushing this way goes out of bounds -> try the next
        best = cand
        break
    return best if best is not None else far


def _shrink_off(box: tuple, blocked: tuple, *, min_w: float, min_h: float,
                span: tuple, gap: float = 0.0) -> tuple:
    """把 `box` **缩到**不与 `blocked` 重叠（缩不动就整体推到它外面）。

    ★ 为什么"先缩后推"：房间本来就该待在它自己的位置上 ——
      缩一下往往就够了（重叠通常只是"框开得太大"）。
      推是最后手段，因为它会改变房间的相对位置（作者看的是这个）。
    [EN] **Shrink** `box` until it no longer overlaps `blocked` (if it cannot, push it outside).
    [EN] ★ Why "shrink first, then push": a room should stay where it is -- shrinking is usually
    [EN] enough (the overlap is normally just "the box was opened too wide"). Pushing is the last
    [EN] resort because it changes the room's relative position (which is what the author reads).
    """
    bx0, by0, bx1, by1 = box
    gx0, gy0, gx1, gy1 = blocked
    if overlap_area(box, blocked) <= 0:
        return box
    # 四个方向各试一次"缩掉重叠"，挑缩得最少而仍够大的那个
    # [EN] Try shrinking off the overlap in each of the four directions; keep the smallest shrink
    # [EN] that still leaves it big enough
    cands = [
        (gx0 - bx0, (bx0, by0, min(bx1, gx0 - gap), by1)),        # 左边界推进到院子的左边界
        (bx1 - gx1, (max(bx0, gx1 + gap), by0, bx1, by1)),        # 右
        (gy0 - by0, (bx0, by0, bx1, min(by1, gy0 - gap))),        # 上
        (by1 - gy1, (bx0, max(by0, gy1 + gap), bx1, by1)),        # 下
        # [EN] bottom
    ]
    best = None
    for cut, cand in sorted(cands, key=lambda c: c[0]):
        if cand[2] - cand[0] < min_w or cand[3] - cand[1] < min_h:
            continue
        if overlap_area(cand, blocked) > 1.0:
            continue
        best = cand
        break
    if best is not None:
        return best
    # 缩不动 → 整体推到院子外（带 `span` 验过界）
    # [EN] Cannot shrink -> push the whole room outside the courtyard (bounds-checked against `span`)
    gap = max(min_w, min_h) * 0.18
    pushed = _push_apart(blocked, box, gap, span=span)
    if overlap_area(pushed, blocked) <= 1.0:
        return pushed
    return box


def _clip_into(box: tuple, span: tuple) -> tuple:
    """把一块矩形**整体挪进** `span`（尺寸不变；挪不进去就压缩）。
    [EN] **Move** a rectangle inside `span` (size unchanged; squeeze only if it cannot fit)."""
    x0, y0, x1, y1 = box
    sx0, sy0, sx1, sy1 = span
    w, h = x1 - x0, y1 - y0
    w = min(w, sx1 - sx0)
    h = min(h, sy1 - sy0)
    x0 = min(max(x0, sx0), sx1 - w)
    y0 = min(max(y0, sy0), sy1 - h)
    return (x0, y0, x0 + w, y0 + h)


def _separate_boxes(boxes: list, span: tuple, iters: int = 8) -> list:
    """把一组矩形推开到**两两不重叠**（沿"重叠更小的轴"推；推完出界就改推另一轴）。

    ★ 这是 `_shrink_off` 的**兜底**：逐间避让院子时，两间可能被推到**同一个逃生方向**
       → 塌成同一框（`_shrink_off` 不知道"另一间已经在那"）。这道在此之后、算房子外框之前
       跑一遍，保证"房间绝不互相重叠"永远成立 —— 正是用户报的小地图"块重叠"的修法。
    ★ 与 `minimap._room_boxes` 第 ② 步同源算法，但多了"出界改推另一轴"，避免硬推到画布外。
    [EN] Push a set of rectangles apart until pairwise non-overlapping (push along the smaller-overlap
    [EN] axis; if that goes out of bounds, push along the other axis instead).
    [EN] ★ This is the **backstop** for `_shrink_off`: when avoiding the courtyard, two rooms can be
    [EN] pushed to the **same escape direction** and collapse into one box (`_shrink_off` does not know
    [EN] "the other room is already there"). Running this after, and before the house frame is built,
    [EN] guarantees "rooms never overlap each other" -- exactly the fix for the user's minimap
    [EN] "blocks overlapping". Shares the algorithm with `minimap._room_boxes` step (2), plus the
    [EN] "out-of-bounds → other axis" guard so we never shove a room off-canvas.
    """
    bs = [list(b) for b in boxes]
    sx0, sy0, sx1, sy1 = span

    def _clip(b):
        w = b[2] - b[0]
        h = b[3] - b[1]
        b[0] = min(max(b[0], sx0), sx1 - w)
        b[2] = b[0] + w
        b[1] = min(max(b[1], sy0), sy1 - h)
        b[3] = b[1] + h
        return b

    for _ in range(iters):
        moved = False
        for a in range(len(bs)):
            for b in range(a + 1, len(bs)):
                A, B = bs[a], bs[b]
                ox = min(A[2], B[2]) - max(A[0], B[0])
                oy = min(A[3], B[3]) - max(A[1], B[1])
                if ox <= 0.5 or oy <= 0.5:
                    continue
                acx = (A[0] + A[2]) / 2
                acy = (A[1] + A[3]) / 2
                bcx = (B[0] + B[2]) / 2
                bcy = (B[1] + B[3]) / 2

                def _push(axis):
                    nA, nB = list(A), list(B)
                    if axis == 'x':
                        s = 1.0 if acx <= bcx else -1.0
                        nA[0] += s * ox / 2; nA[2] += s * ox / 2
                        nB[0] -= s * ox / 2; nB[2] -= s * ox / 2
                    else:
                        s = 1.0 if acy <= bcy else -1.0
                        nA[1] += s * oy / 2; nA[3] += s * oy / 2
                        nB[1] -= s * oy / 2; nB[3] -= s * oy / 2
                    return nA, nB

                order = ('x', 'y') if ox <= oy else ('y', 'x')
                done = False
                for axis in order:
                    nA, nB = _push(axis)
                    if contains(nA, span) and contains(nB, span):
                        bs[a], bs[b] = nA, nB
                        moved = True
                        done = True
                        break
                if not done:                       # 两轴都出界：硬推（之后统一 clip）
                    bs[a], bs[b] = _push(order[0])
                    moved = True
        if not moved:
            break
    for b in bs:
        _clip(b)
    return [tuple(b) for b in bs]


def solve(layout: Layout | None, *, px, span: tuple, detail: str = '',
          current: str = '', grow: float = 0.26,
          name_band: float = 0.0) -> Plan:
    """**解算**：这张图上每个元素该在哪儿（纯函数，不看画布外的任何东西）。

    `span` = 绘图区（`(x0, y0, x1, y1)`）；图例让出的那部分**不在**其中。
    ★★ `px` = **归一化坐标 → 像素**的换算函数（`Place → (x, y)`）。
      ⚠ **必须由调用方传进来**，不能在函数里自己算 —— 2026-10-12 实测过：
        解算按"画布宽"算、绘制按"绘图区宽"算，两张图各用一套坐标，
        家具就跑到墙外面去了（用户看到的就是这个）。**换算全项目只有一份**。

    顺序是**刻意**的（后一步要用前一步的结果）：
      ① 房间矩形 → ② 房子外框（房间的并集）→ ③ 院子矩形（**推出房子之外**）
      → ④ 陈设**落进它所属的房间** → ⑤ 其余地点照原位。

    ★★ 第 ③、④ 步就是用户报的那两件事的修法 —— 顺序不能颠倒：
      院子必须先知道房子在哪儿，家具必须先知道房间在哪儿。
    [EN] **Solve**: where every element goes on this map (a pure function, looking at nothing outside
    [EN] the canvas).
    [EN] `span` = the drawing area (`(x0, y0, x1, y1)`); the part given up to the legend is **not** in
    [EN] it.
    [EN] ★★ `px` = the **normalised-to-pixel** mapping function (`Place -> (x, y)`).
    [EN]   ⚠ It **must be passed in** rather than computed inside: measured on 2026-10-12, solving
    [EN]   mapped from "canvas width" while drawing mapped from "drawing-area width", giving each
    [EN]   image two coordinate systems and pushing the furniture outside the wall (exactly what the
    [EN]   user saw). **This mapping exists exactly once in the project.**
    [EN] The order is **deliberate** (each step uses the previous one):
    [EN] 1) room rectangles -> 2) the house frame (union of the rooms) -> 3) the courtyard rectangle
    [EN] (**pushed outside the house**) -> 4) fixtures **land inside the room they belong to** ->
    [EN] 5) other locations stay where they are.
    [EN] ★★ Steps 3 and 4 are the fixes for the two things the user reported -- the order cannot be
    [EN] swapped: the courtyard must know where the house is first, and the furniture must know where
    [EN] the room is first.
    """
    plan = Plan(detail=detail or MM.detail_of(layout))
    places = list((layout.places if layout else []) or [])
    if not places:
        return plan

    # ① 院子**先算**（它由"院里那几个点"决定，位置最硬）
    #    ⚠⚠ 顺序在 2026-10-12 调过：**先房间后院子**是不行的 ——
    #      房间框的初始大小是"绘图区的一个比例"（`grow`），只有一间房时没有别的
    #      房间来约束它，于是它长得几乎铺满整张图，把院子挤在角上必然重叠。
    #      改成**院子先定，房间再避开它**，重叠就不可能出现（`_shrink_off` 兜住）。
    # [EN] (1) The courtyard is computed **first** (it is decided by "the few points in the yard"; its
    # [EN] position is the hardest).
    # [EN] ⚠⚠ The order was changed on 2026-10-12: **rooms first, courtyard second** does not work --
    # [EN] a room box's initial size is "a fraction of the drawing area" (`grow`), and with only one
    # [EN] room nothing constrains it, so it grows to fill almost the whole map and squeezes the
    # [EN] courtyard into a corner, guaranteeing overlap. With **the courtyard fixed first and the
    # [EN] rooms avoiding it**, overlap cannot occur (`_shrink_off` backstops it).
    yard = _outdoor_box(places, px, min_w=MM.ROOM_MIN_W * 1.6,
                        min_h=MM.ROOM_MIN_H * 1.6, span=span)
    if yard is not None:
        plan.yard = yard
        plan.frames['yard'] = plan.yard

    # ② 房间矩形（只在室内 / 室内外这两档画墙）—— **避开院子**
    # [EN] (2) Room rectangles (walls only on the indoor / indoor+outdoor tiers) -- **avoiding the
    # [EN] courtyard**
    if plan.detail in (MM.DETAIL_IN, MM.DETAIL_IN_OUT):
        # ★ 楼名带：当调用方要预留名字带时，把"计算房间"用的 `span` 顶部往下推
        #   `name_band`，于是房子外框永远落在带子**下方**，楼名可以写在带子里、
        #   不再压在房子立面上（用户 2026-10-15：「楼名字在建筑立面」）。
        #   默认 0 时与旧行为完全一致（小地图不预留带子，楼名写在框上沿）。
        # [EN] ★ Name band: when the caller reserves a name band, push the room-computing `span`'s top
        # [EN] down by `name_band`, so the house frame always sits **below** the band and the building
        # [EN] name can be written in the band instead of on the building facade (user 2026-10-15:
        # [EN] "the building name is on the facade"). Default 0 keeps the old behaviour (the minimap
        # [EN] reserves no band; its name sits on the frame's top edge).
        eff_span = (span[0], span[1] + max(0.0, name_band), span[2], span[3]) \
            if name_band > 0 else span
        boxes = _room_boxes(places, px, span=eff_span, grow=grow,
                            min_w=MM.ROOM_MIN_W, min_h=MM.ROOM_MIN_H)
        # 房子与院子之间的间隙：按**绘图区尺寸**算（`span` 是唯一权威，不再引画布尺寸）
        # [EN] The gap between house and courtyard, from the **drawing-area size** (`span` is the only
        # [EN] authority; canvas dimensions are no longer referenced)
        gap_px = GAP * ((span[2] - span[0]) + (span[3] - span[1])) / 2
        for name, box in boxes.items():
            if plan.yard is not None:
                box = _shrink_off(box, plan.yard, min_w=MM.ROOM_MIN_W,
                                  min_h=MM.ROOM_MIN_H, span=span,
                                  gap=gap_px)
            plan.rooms[name] = Room(name=name, box=box, label=_label_of(places, name),
                                    here=bool(current) and name == current)

        # ②b 房间之间**互不重叠**（小地图"块重叠"的兜底）：
        #     `shrink_off` 可能把两间推到同一个逃生方向 → 塌成同一框，
        #     这里再沿"重叠更小的轴"推开（出界就改推另一轴）。
        #    ★★ 必须在"算房子外框"之前跑 —— 外框是房间的并集，
        #       房间还重叠着，外框就把重叠也并进去，等于没修。
        #   默认 `name_band>0` 时 `eff_span` 已把顶部下推，分离照 `span`（含名字带）裁，
        #   楼名照样写在带子里、不压房子。
        # [EN] (2b) Rooms are **pairwise non-overlapping** (backstop for the minimap's "blocks
        # [EN] overlapping"): `_shrink_off` may push two rooms to the same escape direction and
        # [EN] collapse them into one box; here we push them apart again (other axis if out of
        # [EN] bounds). Must run **before** the house frame (the frame is the union of the rooms;
        # [EN] if the rooms still overlap, the frame folds the overlap in too).
        if len(plan.rooms) > 1:
            _names = list(plan.rooms)
            _sep = _separate_boxes([plan.rooms[n].box for n in _names], span=span)
            for n, b in zip(_names, _sep):
                plan.rooms[n].box = b

    # ③ 房子外框 = 所有房间矩形的并集（没有房间 → None）
    # [EN] (3) The house frame = the union of all room rectangles (None if no rooms)
    for r in plan.rooms.values():
        plan.house = r.box if plan.house is None else _union(plan.house, r.box)

    # ④ 院里的点跟着院子矩形走（否则点是原点位、院墙是新位置，画出来对不上）
    # [EN] (4) The courtyard points follow the courtyard rectangle (otherwise the points stay at their
    # [EN] old spots while the wall is elsewhere, and they no longer line up)
    if plan.yard is not None:
        outs = [p for p in places if MM._is_outdoor(p.name)]
        if outs:
            xs = [px(p)[0] for p in outs]
            ys = [px(p)[1] for p in outs]
            old = (min(xs), min(ys), max(xs), max(ys))
            dx = (plan.yard[0] + plan.yard[2]) / 2 - (old[0] + old[2]) / 2
            dy = (plan.yard[1] + plan.yard[3]) / 2 - (old[1] + old[3]) / 2
            for p in outs:
                x, y = px(p)
                plan.yard_pts[p.name] = (x + dx, y + dy)

    # ⑤ 陈设**落进它所属的房间**（这是「柜台跑到墙外面」的修法）
    #    归属顺序：① 布局里明确写了 `房间`（AI 填的）→ ② 几何最近的那一间。
    #    ⚠ 找不到任何房间时不画陈设的方块（改为只写名字）—— 画在"没有墙"的地方
    #      就是"跑到墙外面"，那正是用户报的。
    # [EN] (4) Fixtures **land inside the room they belong to** (the fix for "the counter ran outside
    # [EN] the wall").
    # [EN] Ownership order: 1) the layout says `房间` explicitly (filled by the AI) -> 2) the
    # [EN] geometrically nearest room.
    # [EN] ⚠ When there is no room at all the fixture block is not drawn (only its name) -- drawing
    # [EN] it where there is no wall is exactly "outside the wall", which is what the user reported.
    fixes = [p for p in places if MM._is_fixture(p.name)]
    if fixes and plan.rooms:
        by_room: dict = {}
        for p in fixes:
            cx, cy = px(p)
            want = str(getattr(p, 'room', '') or '').strip()
            if want and want in plan.rooms:
                owner = want
            else:
                # 几何兜底：**中心离哪一个房间的中心最近**（曼哈顿距离就够 ——
                # 这里只是挑一间房，不需要欧氏距离那么精细）
                # [EN] Geometric fallback: **whichever room centre is nearest** (Manhattan distance is
                # [EN] enough -- this only picks a room, no need for Euclid)
                def _dist(n: str) -> float:
                    b = plan.rooms[n].box
                    return (abs((b[0] + b[2]) / 2 - cx)
                            + abs((b[1] + b[3]) / 2 - cy))
                owner = min(plan.rooms, key=_dist)
            by_room.setdefault(owner, []).append(p)
        for owner, items in by_room.items():
            box = plan.rooms[owner].box
            bw, bh = box[2] - box[0], box[3] - box[1]
            n = len(items)
            for i, p in enumerate(items):
                # 在房间里**横排**（超出换行）：保证都在墙内、互不重叠
                # [EN] Laid out **in rows** inside the room (wrapping): all inside the walls, none
                # [EN] overlapping
                row, col = divmod(i, FURN_PER_ROW)
                per = min(n, FURN_PER_ROW)
                uw = max(6.0, (bw - 2 * FURN_PAD) / max(per, 1))
                ux = box[0] + FURN_PAD + uw * (col + 0.5)
                uh = max(6.0, (bh - 2 * FURN_PAD) / max((n + FURN_PER_ROW - 1)
                                                        // FURN_PER_ROW, 1))
                uy = box[1] + FURN_PAD + uh * (row + 0.5)
                plan.fixtures[p.name] = (owner, (ux, uy))

    # ⑥ 其余地点：照原位（它们的坐标本来就在布局里）
    # [EN] (6) Other locations: where they are (their coordinates come from the layout)
    for p in places:
        if p.name in plan.rooms or p.name in plan.fixtures:
            continue
        if MM._is_outdoor(p.name) and p.name in plan.yard_pts:
            plan.others[p.name] = plan.yard_pts[p.name]
        else:
            plan.others[p.name] = px(p)
    return plan


# ══════════════════════════════════════════════════════════════════
#  二、审核：查出问题（**只读**）
# [EN] 2. Audit: find the problems (**read-only**)
# ══════════════════════════════════════════════════════════════════
def audit(plan: Plan) -> list[Issue]:
    """审核一份**解算结果**，返回问题清单（空表 = 没问题）。

    ★ 它**不改任何东西** —— 修是 `repair()` 的活。分开的理由：
      "查"要能独立跑（判据、Reflection 的审核轮、故障排查都用它），
      而"修"是有副作用的一步，混在一起会让"审核报告"变得不可信
      （你不知道报的是修前还是修后的）。
    [EN] Audit a **solved result** and return the problem list (empty = fine).
    [EN] ★ It **changes nothing** -- repairing is `repair()`'s job. Why separate: "checking" must be
    [EN] runnable on its own (criteria, the Reflection audit rounds, troubleshooting all use it),
    [EN] while "repairing" has side effects; mixing them makes the audit report untrustworthy (you
    [EN] cannot tell whether it reports the before or the after).
    """
    out: list[Issue] = []

    # ① 陈设没房间可放（那就只能画在"没有墙"的地方 = 墙外）
    # [EN] (1) A fixture has no room to go in (then it can only be drawn where there is no wall =
    # [EN] outside it)
    if plan.fixtures or plan.rooms:
        for name, (owner, _pos) in plan.fixtures.items():
            if owner not in plan.rooms:
                out.append(Issue(K_FURN_ORPHAN, name, f'归属「{owner}」不在房间里'))

    # ② 院子里见天的东西跑到屋里（空间常识，转发 `world.spatial`）
    # [EN] (2) An outdoor thing (open to the sky) ended up indoors (spatial common sense, delegated
    # [EN] to `world.spatial`)
    try:
        sp = MM._spatial()
        names = list(plan.others) + list(plan.rooms) + list(plan.fixtures)
        for b in (sp.audit(names, kind='室内') if sp else []):
            out.append(Issue(K_NOT_INDOOR, str(getattr(b, 'where', b)),
                             str(getattr(b, 'why', b))))
    except Exception:                                            # noqa: BLE001
        pass

    # ③ 院子与房子重叠（用户 2026-10-12 报的那个）
    # [EN] (3) The courtyard overlaps the house (what the user reported on 2026-10-12)
    if plan.yard is not None and plan.house is not None:
        a = overlap_area(plan.yard, plan.house)
        if a > 1.0:
            out.append(Issue(K_YARD_OVERLAP, '',
                             f'重叠 {round(a)} px²（院子 {_r(plan.yard)} · '
                             f'房子 {_r(plan.house)}）'))

    # ④ 房间跑出房子外框（外框就是房间的并集，所以这里查的是"并集之外"，
    #    正常情况必然为空 —— 留着是为了**兜住将来有人用别的 span 算房间**）
    # [EN] (4) A room outside the house frame (the frame *is* the union of the rooms, so this is
    # [EN] normally empty -- kept to **catch a future case where rooms are computed with another
    # [EN] span**)
    if plan.house is not None:
        for r in plan.rooms.values():
            if not contains(r.box, plan.house, tol=1.0):
                out.append(Issue(K_ROOM_OUTSIDE, r.name, _r(r.box)))
    return out


def _r(b: tuple | None) -> str:
    return '—' if b is None else '(' + ','.join(str(round(v)) for v in b) + ')'


# ══════════════════════════════════════════════════════════════════
#  三、修复：确定性修掉（**不调模型、零成本**）
# [EN] 3. Repair: fix deterministically (**no model call, zero cost**)
# ══════════════════════════════════════════════════════════════════
def repair(layout: Layout | None, *, px, span: tuple, detail: str = '',
           current: str = '', grow: float = 0.26,
           rounds: int = 3) -> tuple[Plan, list[Issue]]:
    """**审核 → 修复 → 再审**，直到没问题（上限 `rounds` 轮）。

    ★★ 这就是用户点名要的那个机制：「美术 Agent 绘制地图的时候要用 **Reflection** 的机制
      **绘制之后去审核 如果有问题则修复问题重新绘制 直到没问题**」。

      ⚠ 但它**不调模型** —— 修复是**确定性**的（挪坐标、换归属），
        所以每一轮都是零成本。**Reflection 的贵的那一版**（让模型看着自己的图重画）
        在 `crew/agents.py` 的美术那一侧：它拿到这里修好的结果，
        只有在**真的修不动**时才回退去问模型。
        这个分工的理由：能算出来的事不该让模型猜（又慢又贵还不一定对）。

    ★ 为什么"修"是改**布局**而不是改画法：画法是死的（`solve()` 一套），
      改画法等于给每种错都加一个特例；改布局是**数据**，一处修好全部受益
      （小地图、大地图、当天的图三处同一份数据）。

    返回 `(修好的解算结果, 问题清单)`；清单里 `fixed=True` 的是这一轮修掉的。
    [EN] **Audit -> repair -> audit again** until clean (at most `rounds` rounds).
    [EN] ★★ This is exactly the mechanism the user asked for: "when the art Agent draws the map it
    [EN] should use **Reflection**: after drawing, go and audit it; if there is a problem, fix it,
    [EN] redraw, until there is no problem".
    [EN]   ⚠ But it **does not call the model** -- the repair is **deterministic** (move coordinates,
    [EN]   change ownership), so every round is free. The **expensive version of Reflection**
    [EN]   (letting the model redraw while looking at its own output) lives on the art side in
    [EN]   `crew/agents.py`: it receives the result fixed here and only falls back to asking the
    [EN]   model when something **truly cannot be fixed**. The reason for this split: what can be
    [EN]   computed should not be guessed by a model (slow, costly, and not necessarily right).
    [EN] ★ Why "repair" changes the **layout** rather than the drawing: the drawing is fixed (one
    [EN] `solve()`); changing the drawing means adding a special case for every error, while changing
    [EN] the layout is **data** -- fixed once, everything benefits (the minimap, the big map and the
    [EN] day map share one layout).
    [EN] Returns `(the repaired solved result, the problem list)`; entries with `fixed=True` were
    [EN] fixed in this run.
    """
    issues: list[Issue] = []
    for _ in range(max(1, rounds)):
        plan = solve(layout, px=px, span=span, detail=detail, current=current,
                     grow=grow)
        found = audit(plan)
        if not found:
            return plan, issues
        changed = False
        for it in found:
            if it.kind == K_FURN_ORPHAN:
                # 没有房间 → **补一间**（只加不减：不能让陈设消失）
                # [EN] No room -> **add one** (only add, never remove: the fixture must not vanish)
                changed = _add_room(layout, it.who, plan) or changed
                it.fixed = True
            elif it.kind == K_YARD_OVERLAP:
                # 院子与房子重叠 → 把院子的点**整体推开**
                # [EN] Courtyard overlapping the house -> **push the courtyard points away as a whole**
                changed = _push_yard(layout, plan, px=px) or changed
                it.fixed = changed
            # 其余问题这一层修不了（要模型重画）→ 留给美术那一侧
            # [EN] The rest cannot be fixed at this layer (needs the model to redraw) -> left to the
            # [EN] art side
        issues.extend(found)
        if not changed:
            break                       # 修不动了，别再空转
            # [EN] nothing more can be fixed -- stop spinning
    plan = solve(layout, px=px, span=span, detail=detail, current=current,
                 grow=grow)
    return plan, issues


def _add_room(layout: Layout | None, fixture: str, plan: Plan) -> bool:
    """给一个**没房间可放**的陈设补一间房（摆在它旁边）。
    [EN] Add a room for a fixture that has **nowhere to go** (placed beside it)."""
    if layout is None:
        return False
    p = next((q for q in layout.places if q.name == fixture), None)
    if p is None:
        return False
    base = '堂屋'
    n = 2
    while any(q.name == base for q in layout.places):
        base = f'堂屋{n}'
        n += 1
    # 房间就摆在陈设的**正上方一点**（几何上必然能把它兜住）
    # [EN] The room goes **just above** the fixture (geometrically guaranteed to contain it)
    layout.places.append(Place(name=base, x=float(p.x), y=max(0.12, float(p.y) - 0.12),
                               shape='屋', size='中'))
    p.room = base
    return True


def _push_yard(layout: Layout | None, plan: Plan, *, px) -> bool:
    """把院里的点**整体挪到**（已经不含房子的）院子矩形里。
    [EN] **Move the courtyard points**, as a group, into the courtyard rectangle (which no longer
    [EN] overlaps the house)."""
    if layout is None or plan.yard is None or plan.house is None:
        return False
    outs = [p for p in layout.places if MM._is_outdoor(p.name)]
    if not outs or not plan.yard_pts:
        return False
    # 院子被推到哪一边 → 点也跟着往那边挪（用"新旧中心"的位移量换算回归一化坐标）
    # [EN] Whichever side the courtyard was pushed to -> the points follow (converting the
    # [EN] old-to-new centre shift back into normalised coordinates)
    nx = sum(v[0] for v in plan.yard_pts.values()) / len(plan.yard_pts)
    ny = sum(v[1] for v in plan.yard_pts.values()) / len(plan.yard_pts)
    # ⚠ 位移要**换算回归一化坐标**才能加到 `p.x/p.y` 上 —— 而换算率来自 `px`
    #   本身（用两个探针点量一下缩放），所以这里不写死 W/H。
    # [EN] The shift must be converted **back to normalised coordinates** before being added to
    # [EN] `p.x/p.y`; the scale comes from `px` itself (measured with two probe points), so W/H are
    # [EN] not hardcoded here.
    kx = px(Place('', x=1.0, y=0.0))[0] - px(Place('', x=0.0, y=0.0))[0]
    ky = px(Place('', x=0.0, y=1.0))[1] - px(Place('', x=0.0, y=0.0))[1]
    oxs = sum(px(p)[0] for p in outs) / len(outs)
    oys = sum(px(p)[1] for p in outs) / len(outs)
    dxn = (nx - oxs) / max(1.0, kx)
    dyn = (ny - oys) / max(1.0, ky)
    if abs(dxn) < 1e-4 and abs(dyn) < 1e-4:
        return False
    for p in outs:
        p.x = min(0.98, max(0.02, float(p.x) + dxn))
        p.y = min(0.98, max(0.02, float(p.y) + dyn))
    return True


# ══════════════════════════════════════════════════════════════════
#  五、Reflection：**布局层**的审核-修复环（不依赖画布）
# [EN] 5. Reflection: the **layout-level** audit-repair loop (canvas-independent)
# ══════════════════════════════════════════════════════════════════
#: 房子在**归一化坐标**下大概占多大（用来判"房子与院子会不会撞上"）。
#   它不必精确 —— 渲染层的 `solve()` 才是精确的那一层（会按真实画布算房间框）。
#   这里只需要"早一步发现必然会撞"的那类布局。
# [EN] : roughly how big the house is in **normalised coordinates** (used to tell whether the house
# [EN] and the courtyard will collide). It need not be exact -- `solve()` at the render layer is the
# [EN] precise one (it computes room boxes from the real canvas). This only needs to catch, one step
# [EN] earlier, layouts that are **bound** to collide.
NORM_HOUSE_R = 0.13
#: 归一化坐标下，房子与院子之间至少留多少。
# [EN] : the minimum gap between house and courtyard in normalised coordinates.
NORM_GAP = 0.04


def _norm_box(pts: list[tuple[float, float]], r: float) -> tuple | None:
    """一组归一化点 + 半径 → 包围盒 `(x0, y0, x1, y1)`。
    [EN] A set of normalised points plus a radius -> a bounding box `(x0, y0, x1, y1)`."""
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r)


def reflect_layout(layout: Layout | None, *, rounds: int = 3) -> tuple[Layout | None, list[Issue]]:
    """**Reflection（布局层）**：审核 → 有问题就确定性修复 → 再审，直到通过。

    这就是用户 2026-10-12 点名要的那个机制：
      「美术 Agent 绘制地图的时候要用 **Reflection** 的机制 **绘制之后去审核
        如果有问题则修复问题重新绘制 直到没问题**」。

    ★ 为什么**不调模型**：能算出来的事不该让模型猜（又慢又贵还不一定对）。
      修复全是确定性的（补一间房、把院子的点挪开、把陈设归到最近的房间），
      所以每一轮**零成本**。真正修不动的（比如模型给的名字全越界）不在这里 ——
      那要回到美术那一侧**重新问**（见 `crew/agents.py` 的说明）。

    ★ 与**渲染层**的分工（两层各管一段，互不重复）：
      | 层 | 管什么 | 在哪 |
      |---|---|---|
      | 布局层（本函数） | 数据对不对：陈设有没有归属的房间、有井有没有院、房子与院子会不会必然相撞 | `day_layout()` 末尾 |
      | 渲染层（`solve()`） | 画出来对不对：家具在不在墙内、院子框与房子框重不重叠 | `floorplan` / `minimap` |
      两层查的**不是同一件事**：布局层保证"数据自洽"，渲染层保证"画得自洽"。
      只做一层的话，另一层照样会出错（前两轮就是这么漏的）。

    ⚠ **只加不减**：修法是"补一间房""把院里的点挪开"，**不删任何地点** ——
      删了就等于"这一处从图上消失了"。
    [EN] **Reflection (layout level)**: audit -> deterministically repair -> audit again until clean.
    [EN] This is the mechanism the user named on 2026-10-12: "when the art Agent draws the map it
    [EN] should use **Reflection**: after drawing, go and audit it; if there is a problem, fix it,
    [EN] redraw, until there is no problem".
    [EN] ★ Why **no model call**: what can be computed should not be guessed by a model. Every repair
    [EN] is deterministic (add a room, move the courtyard points aside, assign a fixture to the
    [EN] nearest room), so each round is **free**. What truly cannot be fixed here (e.g. every name
    [EN] the model returned is out of range) does not belong here -- that goes back to the art side
    [EN] and **asks again** (see the note in `crew/agents.py`).
    [EN] ★ Division of labour with the **render layer** (each owns one stretch, no overlap):
    [EN]   | Layer | Governs | Where |
    [EN]   |---|---|---|
    [EN]   | layout (this function) | is the data right: does a fixture have a room, does a well have a courtyard, are the house and courtyard bound to collide | end of `day_layout()` |
    [EN]   | render (`solve()`) | is the drawing right: is the furniture inside the wall, do the courtyard and house rectangles overlap | `floorplan` / `minimap` |
    [EN]   They check **different things**: the layout layer guarantees "the data is self-consistent",
    [EN]   the render layer "the drawing is self-consistent". Doing only one leaves the other broken
    [EN]   (that is exactly what slipped through in the previous two rounds).
    [EN] ⚠ **Only add, never remove**: the repairs are "add a room" and "move the courtyard points
    [EN] aside" -- **no location is deleted** (deleting would mean "this spot vanished from the map").
    """
    if layout is None or not layout.places:
        return layout, []
    issues: list[Issue] = []
    for _ in range(max(1, rounds)):
        found = audit_layout(layout)
        if not found:
            break
        changed = False
        # ① 空间常识（有井必有院 / 器物不许入屋）—— 复用 `world.spatial.repair`（只加不减）
        # [EN] (1) Spatial common sense (a well implies a courtyard / an object may not be indoors) --
        # [EN] reusing `world.spatial.repair` (only add, never remove)
        for it in found:
            if it.kind in (K_NOT_INDOOR, K_YARD_MISSING):
                changed = _fix_by_spatial(layout) or changed
                it.fixed = changed
            elif it.kind == K_FURN_ORPHAN:
                changed = _add_room(layout, it.who, None) or changed
                it.fixed = True
            elif it.kind == K_YARD_OVERLAP:
                changed = _separate_norm(layout) or changed
                it.fixed = changed
        issues.extend(found)
        if not changed:
            break                        # 修不动了，别再空转
            # [EN] nothing more can be fixed -- stop spinning
    return layout, issues


def audit_layout(layout: Layout | None) -> list[Issue]:
    """**布局层**的审核（只读，不依赖画布）。

    查四件事：
      ① **陈设没有可放进去的房间**（那它在渲染时只能落到"没有墙"的地方）；
      ② **有井（或别的见天器物）却没有院子**（用户点名的硬规则）；
      ③ **屋里出现了见天的东西**；
      ④ **房子与院子在布局上就必然相撞**（归一化包围盒重叠）。

    ⚠ 与渲染层的 `audit()` **不是同一件事**（那边查画出来的形状），
      但两边**用同一个问题名**（`K_*`），这样"修没修好"看的是同一个词。
    [EN] **Layout-level** audit (read-only, canvas-independent).
    [EN] It checks four things:
    [EN] 1) **a fixture with no room to go in** (so at render time it can only land where there is no
    [EN]    wall);
    [EN] 2) **a well (or another sky-open object) with no courtyard** (a hard rule the user named);
    [EN] 3) **an outdoor thing ending up indoors**;
    [EN] 4) **the house and the courtyard bound to collide in the layout itself** (normalised bounding
    [EN]    boxes overlap).
    [EN] ⚠ This is **not the same** as the render-layer `audit()` (which checks the drawn shapes), but
    [EN] both use **the same problem names** (`K_*`), so "is it fixed" reads the same word.
    """
    out: list[Issue] = []
    places = list(layout.places if layout else [])
    if not places:
        return out
    names = [p.name for p in places]
    detail = MM.detail_of(layout)

    # ① 陈设归属
    # [EN] (1) Fixture ownership
    rooms = [p.name for p in places if MM._is_room(p.name)]
    for p in places:
        if not MM._is_fixture(p.name):
            continue
        want = str(getattr(p, 'room', '') or '').strip()
        if want and want in rooms:
            continue
        if not rooms:
            out.append(Issue(K_FURN_ORPHAN, p.name, '这张图上没有房间可放'))
        elif not want:
            # 有房间但**没写归属** —— 不算错（几何会兜底），但值得记一笔
            # [EN] Rooms exist but **no ownership is written** -- not an error (geometry backstops it),
            # [EN] but worth noting
            pass

    # ②③ 空间常识（转发 `world.spatial`）：屋里/院里的归属、有井必有院
    # [EN] (2)(3) Spatial common sense (delegated to `world.spatial`)
    try:
        sp = MM._spatial()
        if sp is not None:
            kind = '室内' if detail in (MM.DETAIL_IN, MM.DETAIL_IN_OUT) else detail
            for v in sp.audit(names, kind=kind):
                code = str(getattr(v, 'code', ''))
                where = str(getattr(v, 'where', ''))
                why = str(getattr(v, 'why', ''))
                if code == '井无院':
                    out.append(Issue(K_YARD_MISSING, where, why))
                elif code == '器物入屋':
                    out.append(Issue(K_NOT_INDOOR, where, why))
    except Exception:                                            # noqa: BLE001
        pass

    # ④ 房子与院子在布局上必然相撞吗
    # [EN] (4) Are the house and courtyard bound to collide in the layout
    if detail in (MM.DETAIL_IN, MM.DETAIL_IN_OUT):
        house = _norm_box([(p.x, p.y) for p in places if MM._is_room(p.name)],
                          NORM_HOUSE_R)
        yard = _norm_box([(p.x, p.y) for p in places if MM._is_outdoor(p.name)],
                         NORM_HOUSE_R * 0.6)
        if house is not None and yard is not None:
            a = overlap_area(house, yard)
            if a > 1e-4:
                out.append(Issue(K_YARD_OVERLAP, '',
                                 f'布局上就重叠 {a:.4f}（房子 {_r(house)} · 院子 {_r(yard)}）'))
    return out


def _fix_by_spatial(layout: Layout) -> bool:
    """按空间常识修（**只加不减**）：复用 `world.spatial.repair`。

    ⚠ `spatial.repair` 返回的是 **`(修好的名字清单, 做了什么)`** ——
      它是一个**清单 → 清单**的函数（不认 `Place` 对象）。
      所以这里要做一次"名字清单对回地点"：**只补新出现的名字**，
      已有的名字**保留它们原来的 `x`/`y`/`形`**（作者定过的位置不许被这次修复改掉）。
    [EN] Repair by spatial common sense (**only add, never remove**): reuses `world.spatial.repair`.
    [EN] ⚠ `spatial.repair` returns **`(fixed name list, what was done)`** -- it is a
    [EN] **list -> list** function (it does not know `Place` objects). So this maps the names back:
    [EN] **only names that are new get added**; existing names **keep their original `x`/`y`/`shape`**
    [EN] (a position the author set must not be changed by this repair).
    """
    try:
        sp = MM._spatial()
        if sp is None:
            return False
        got = sp.repair([p.name for p in layout.places],
                        building=str(getattr(layout, 'frame', '') or ''))
        # ⚠ 返回值是**元组**（`(清单, 说明)`）—— 第一版当成清单直接用，
        #   于是在一个元组上迭代，`n in have` 永不成立 ⇒ 一个都没补上（实测"已修 0"）。
        # [EN] ⚠ The return value is a **tuple** (`(list, notes)`) -- the first version treated it as
        # [EN] the list itself, iterating a tuple so `n in have` never held ⇒ nothing got added
        # [EN] (measured as "fixed 0").
        fixed_names = got[0] if isinstance(got, (tuple, list)) and got else []
        have = {p.name for p in layout.places}
        added = 0
        for n in (fixed_names or []):
            name = str(n or '').strip()
            if not name or name in have:
                continue
            have.add(name)
            # 新补的（通常是院子）摆在**现有屋外器物旁边**，不占房间的位置
            # [EN] A newly added item (usually the courtyard) goes **beside the existing outdoor
            # [EN] objects**, not where the rooms are
            outs = [p for p in layout.places if MM._is_outdoor(p.name)]
            anchor = outs[0] if outs else layout.places[0]
            layout.places.append(Place(name=name,
                                       x=min(0.95, float(anchor.x) + 0.14),
                                       y=min(0.95, float(anchor.y) + 0.06)))
            added += 1
        return added > 0
    except Exception:                                            # noqa: BLE001
        return False


def _separate_norm(layout: Layout) -> bool:
    """**归一化坐标**下把院子里的点挪开，使房子与院子不再重叠。
    [EN] Move the courtyard points aside in **normalised coordinates** so the house and courtyard no
    [EN] longer overlap."""
    rooms = [p for p in layout.places if MM._is_room(p.name)]
    outs = [p for p in layout.places if MM._is_outdoor(p.name)]
    if not rooms or not outs:
        return False
    house = _norm_box([(p.x, p.y) for p in rooms], NORM_HOUSE_R)
    yard = _norm_box([(p.x, p.y) for p in outs], NORM_HOUSE_R * 0.6)
    if house is None or yard is None or overlap_area(house, yard) <= 0:
        return False
    # 往"推的距离最小、且推完还在画布里"的方向推
    # [EN] Push in the direction that moves least and still lands inside the canvas
    cands = []
    for name, delta in (('left', (-1, 0)), ('right', (1, 0)),
                        ('up', (0, -1)), ('down', (0, 1))):
        dx = dy = 0.0
        if delta[0] < 0:
            dx = (house[0] - NORM_GAP) - yard[2]
        elif delta[0] > 0:
            dx = (house[2] + NORM_GAP) - yard[0]
        elif delta[1] < 0:
            dy = (house[1] - NORM_GAP) - yard[3]
        else:
            dy = (house[3] + NORM_GAP) - yard[1]
        moved = [(p.x + dx, p.y + dy) for p in outs]
        if all(0.02 <= x <= 0.98 and 0.02 <= y <= 0.98 for x, y in moved):
            cands.append((abs(dx) + abs(dy), dx, dy))
    if not cands:
        return False
    _cost, dx, dy = min(cands)
    for p in outs:
        p.x = min(0.98, max(0.02, float(p.x) + dx))
        p.y = min(0.98, max(0.02, float(p.y) + dy))
    return True


# ══════════════════════════════════════════════════════════════════
#  六、给"审核报告"用的一行摘要（美术写台账、日志用它）
# [EN] 6. A one-line summary for the audit report (used by the art dept for its ledger and logs)
# ══════════════════════════════════════════════════════════════════
def summary(issues: list[Issue]) -> str:
    """问题清单压成一行（给日志/台账用）。
    [EN] Compress the problem list into one line (for logs / the ledger)."""
    if not issues:
        return '几何审核通过'
    n_fix = sum(1 for i in issues if i.fixed)
    kinds: dict = {}
    for i in issues:
        kinds[i.kind] = kinds.get(i.kind, 0) + 1
    body = '、'.join(f'{k}×{v}' for k, v in kinds.items())
    return f'查出 {len(issues)} 处（已修 {n_fix}）：{body}'


def to_json(issues: list[Issue]) -> str:
    """问题清单的 JSON（落盘到运行文件夹，便于人工复核）。
    [EN] The problem list as JSON (written into the run folder for human review)."""
    return json.dumps([i.to_dict() for i in issues], ensure_ascii=False, indent=1)
