# -*- coding: utf-8 -*-
"""标签碰撞避让（纯逻辑，**不依赖渲染**）。

大地图 / 小地图共用的"一个名字该放在哪儿"的解算。

用户 2026-10-16 的原话
======================
「大地图建筑名字放到建筑外面 不然会跟里面的东西覆盖
  而且放到外面的时候也要注意不要跟现有的东西覆盖
  小地图也是这个设计」

⇒ 一个名字一旦决定"放在某个元素（建筑 / 房间 / 符号）的旁边"，就要**避开已经
  画在图上的其它东西**（别的建筑块、别的名字、墙、水系、通路…），不能压上去。

设计
====
给一个"参考框"`box`（建筑框 / 房间框 / 符号 bbox）和这个名字自己的像素尺寸
`(lw, lh)`，在参考框**外侧**的 8 个候选位里挑**第一个不与 `occupied` 任何矩形
重叠**的；若 8 个都重叠，则取"重叠面积最小"的那个（兜底，至少离得最开）。

★ 为什么是**纯逻辑**（不 import flet、不 import minimap）：
  这样它能被 `tools/verify_label_place.py` 独立证明（绿），再被
  `developers/mutate_label_place.py` 独立打红 —— 不开窗口、不依赖画布、
  不依赖字体度量，几何是确定的。

★ 跟 `plan_audit.solve` 一个道理：**名字的位置也只有一份解算**，
  大地图与小地图都来问它，两边才不会一个压一个、一个不压。

English:
Label collision avoidance (pure logic, **no rendering dependency**).
The shared "where should a name go" solver for the big map and the minimap.

The user's exact words on 2026-10-16
====================================
"Put the big-map building name **outside the building**, otherwise it covers the
things inside; and when it is outside, also take care not to cover the **existing
things**. The minimap uses the same design."

⇒ Once a name is decided to sit beside some element (a building / room / symbol),
it must **avoid the other things already drawn on the map** (other building blocks,
other names, walls, water, paths ...) and not press onto them.

Design
======
Given a reference `box` (building / room / symbol bbox) and the name's own pixel
size `(lw, lh)`, pick among **8 candidate positions outside** the box the **first
one that overlaps none** of the `occupied` rectangles; if all 8 overlap, take the
**least-overlapping** one (backstop, at least the most spread out).

★ Why **pure logic** (no flet, no minimap import): so it can be proven independently
by `tools/verify_label_place.py` (green) and broken independently by
`developers/mutate_label_place.py` (red) -- no window, no canvas, no font metrics,
the geometry is deterministic.

★ Same idea as `plan_audit.solve`: **name placement has exactly one solver**; both
the big map and the minimap ask it, so they cannot disagree (one pressing, one not).
"""
from __future__ import annotations


# 8 个候选方位（相对参考框）。顺序无关紧要，调用方用 `prefer` 决定首选。
# [EN] The 8 candidate anchors (relative to the reference box). Order does not matter;
# [EN] the caller decides the first choice via `prefer`.
ANCHORS = (
    'top', 'bottom', 'left', 'right',
    'top-left', 'top-right', 'bottom-left', 'bottom-right',
)


def est_text_size(text: str, size: float) -> tuple[float, float]:
    """估一段文字的像素尺寸（与 `minimap._cjk_w` 同一套口径：汉字 1em、其余 0.55em）。

    ★ 这里**复刻**而不是 import `minimap._cjk_w`，是为了让本模块保持纯逻辑
      （`minimap` 在模块顶部 import 了 flet，会拖累"不开窗口"的单元测试）。
      两者是同一个简单启发式（不是权威几何），各留一份可以接受。
    [EN] Estimate a run of text's pixel size (same convention as `minimap._cjk_w`:
    [EN] CJK = 1em, the rest = 0.55em). Copied rather than imported so this module
    [EN] stays pure (minimap imports flet at the top, which would weigh down the
    [EN] window-less unit tests). Both are the same simple heuristic, not authoritative
    [EN] geometry, so a local copy is fine.
    """
    s = str(text or '')
    w = 0.0
    for ch in s:
        w += size * (1.0 if ord(ch) > 0x2E80 else 0.55)
    # 字高：字号 + 上下一点留白（基线上下各有余量，避免竖直方向贴字）。
    # [EN] Height: font size plus a little vertical padding (baseline has head/descent room).
    return w, size + 3.0


def _rect_of(box: tuple, anchor: str, lw: float, lh: float, gap: float) -> tuple:
    """参考框 `box` 在 `anchor` 方位、`gap` 像素外、尺寸 `lw×lh` 的标签矩形
    `(x0, y0, x1, y1)`。
    [EN] The label rectangle `(x0, y0, x1, y1)` for `anchor`, `gap` px outside `box`,
    [EN] sized `lw`x`lh`."""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    if anchor == 'top':
        lx0 = cx - lw / 2.0
        ly0 = y0 - lh - gap
    elif anchor == 'bottom':
        lx0 = cx - lw / 2.0
        ly0 = y1 + gap
    elif anchor == 'left':
        lx0 = x0 - lw - gap
        ly0 = cy - lh / 2.0
    elif anchor == 'right':
        lx0 = x1 + gap
        ly0 = cy - lh / 2.0
    elif anchor == 'top-left':
        lx0 = x0 - lw - gap
        ly0 = y0 - lh - gap
    elif anchor == 'top-right':
        lx0 = x1 + gap
        ly0 = y0 - lh - gap
    elif anchor == 'bottom-left':
        lx0 = x0 - lw - gap
        ly0 = y1 + gap
    else:  # 'bottom-right'
        lx0 = x1 + gap
        ly0 = y1 + gap
    return (lx0, ly0, lx0 + lw, ly0 + lh)


def _overlap_area(rect: tuple, occupied: list) -> float:
    """`rect` 与 `occupied` 所有矩形的重叠总面积（像素）。0 = 完全不重叠。
    [EN] Total overlap area (px) of `rect` with every rectangle in `occupied`.
    [EN] 0 = no overlap at all."""
    ax0, ay0, ax1, ay1 = rect
    total = 0.0
    for ox in occupied:
        ox0, oy0, ox1, oy1 = ox
        ix0 = ax0 if ax0 > ox0 else ox0
        ix1 = ax1 if ax1 < ox1 else ox1
        iy0 = ay0 if ay0 > oy0 else oy0
        iy1 = ay1 if ay1 < oy1 else oy1
        if ix1 > ix0 and iy1 > iy0:
            total += (ix1 - ix0) * (iy1 - iy0)
    return total


def _in_bounds(rect: tuple, bounds: tuple) -> bool:
    """`rect` 是否整体落在 `bounds` 内（含 0.5px 容差，免得浮点边界抖动判错）。
    [EN] Whether `rect` lies entirely within `bounds` (0.5px tolerance for float jitter)."""
    x0, y0, x1, y1 = rect
    bx0, by0, bx1, by1 = bounds
    return (x0 >= bx0 - 0.5 and y0 >= by0 - 0.5
            and x1 <= bx1 + 0.5 and y1 <= by1 + 0.5)


def place_label(box, lw, lh, occupied, *, bounds=None, gap=2.0,
                prefer='bottom', order=None) -> tuple:
    """给一个名字找**不压东西**的位置。

    Args:
        box: 参考框（建筑 / 房间 / 符号），像素 `(x0, y0, x1, y1)`。
        lw, lh: 名字自身的像素宽 / 高（用 `est_text_size` 估）。
        occupied: 已有东西的矩形列表 `(x0, y0, x1, y1)`
                 （别的块、别的名字、墙…）。**不要**把 `box` 自己放进来。
        bounds: 画布范围 `(x0, y0, x1, y1)`，标签必须整体落在里面
               （None = 不限）。
        gap: 与参考框的最小间距（像素）。
        prefer: 首选方位（默认 `bottom`，即建筑正下方）。
        order: 自定义方位优先级（覆盖 `prefer` + 默认顺序）。

    Returns:
        `(x, y)` 标签**左上角**坐标（直接交给 `fcv.Text`，它的 x/y 就是左上角）。
        找不到完全不重叠的 → 返回重叠面积最小的那一个（兜底）。
        ⚠ 若 8 个候选**全不在 `bounds` 内**（画布太小），仍返回
          `prefer` 方位算出来的那个（至少位置确定），由调用方决定是否裁剪。

        English:
    Find a position for a name that **presses on nothing**.

    Args:
        box: the reference box (building / room / symbol), pixels `(x0, y0, x1, y1)`.
        lw, lh: the name's own pixel width / height (estimate with `est_text_size`).
        occupied: list of rectangles `(x0, y0, x1, y1)` already taken (other blocks,
                 other names, walls ...). Do **not** include `box` itself.
        bounds: the canvas extent `(x0, y0, x1, y1)` the label must lie within
               (None = unbounded).
        gap: the minimum gap from the reference box (pixels).
        prefer: preferred anchor (default `bottom`, i.e. directly below the building).
        order: custom anchor priority (overrides `prefer` + the default order).

    Returns:
        `(x, y)` the label's **top-left** coordinate (hand straight to `fcv.Text`, whose
        x/y is the top-left). If no fully free position exists, returns the least-overlapping
        one (backstop). If all 8 candidates fall outside `bounds` (canvas too small), still
        returns the `prefer` anchor's position (at least deterministic); the caller decides
        whether to clip.
    """
    seq = list(order) if order else ([prefer] + [a for a in ANCHORS if a != prefer])
    best = None
    best_area = float('inf')
    for a in seq:
        r = _rect_of(box, a, lw, lh, gap)
        if bounds is not None and not _in_bounds(r, bounds):
            continue
        area = _overlap_area(r, occupied)
        if area <= 0.0:
            return (r[0], r[1])          # 首个完全不重叠的方位
        if area < best_area:
            best_area = area
            best = (r[0], r[1])
    # 兜底：要么有"重叠最小"的，要么（全出界）退回 prefer 方位
    # [EN] Backstop: either the least-overlapping, or (all out of bounds) the prefer anchor
    if best is not None:
        return best
    r = _rect_of(box, prefer, lw, lh, gap)
    return (r[0], r[1])
