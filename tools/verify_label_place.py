# -*- coding: utf-8 -*-
"""真机无关的纯逻辑验证：`image_gen/label_place.py` 的标签碰撞避让。

为什么是纯逻辑（不开窗口）
--------------------------
`label_place` 不 import flet、不画任何东西，只做几何解算（给定参考框 + 已占用
矩形，返回一个不重叠的标签位置）。所以它能用最便宜的方式被证明：
一组断言，全过 = 绿，有一条不过 = 红。

它要守住的行为（对应用户 2026-10-16「放到外面 + 不要跟现有的东西覆盖」）
----------------------------------------------------------------------
  A1 首选方位空闲时，名字落在**首选方位、参考框之外**（不在框里）。
  A2 首选方位被占时，**换到另一个不重叠的方位**（不硬塞在首选）。
  A3 某个特定空闲方位能被稳定选中（确定性）。
  A4 8 个候选**全被占**时，返回**重叠面积最小**的那个（兜底，不是胡乱挑）。
  A5 `bounds` 裁剪：首选出界、但有界内空闲方位 → 落在界内。
  A6 不变量：只要存在不重叠的方位，返回的位置就**真的**不与任何 occupied 重叠。

跑法：.venv\\Scripts\\python.exe tools/verify_label_place.py
产出：终端 "标签避让验证：X/Y" + 每条 ✓/✗

English:
Window-less pure-logic verification of `image_gen/label_place.py`'s label collision avoidance.
Why window-less: `label_place` imports no flet and draws nothing; it only does geometry
(given a reference box + occupied rects, return a non-overlapping label position). So the
cheapest proof suffices: a set of assertions, all pass = green, one fails = red.
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from image_gen import label_place as LP                    # noqa: E402


checks: list = []


def ok(name: str, cond, detail='') -> bool:
    checks.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:160]})
    return bool(cond)


def cjk(s: dict) -> None:
    print(('  ✓ ' if s['ok'] else '  ✗ ') + s['name'] +
          (f"   [{s['detail']}]" if not s['ok'] else ''))


def _rect(x, y, lw, lh):
    """由 `place_label` 返回的左上角 + 尺寸，得到标签矩形。"""
    return (x, y, x + lw, y + lh)


def _overlap(r, occ):
    a = LP._overlap_area(r, occ)
    return a


def main() -> int:
    # ── A1：首选方位空闲 → 落在首选、框外 ──
    # [EN] A1: preferred anchor free -> lands on preferred, outside the box
    box = (100, 100, 200, 160)
    lw, lh = 40.0, 15.0
    x, y = LP.place_label(box, lw, lh, [], prefer='bottom')
    r = _rect(x, y, lw, lh)
    ok('A1 首选 bottom 空闲时落在框下方、不压框',
       y >= box[3] and LP._overlap_area(r, [box]) <= 0.0,
       f'label_rect={r} box={box}')

    # ── A2：首选被占 → 换到另一个不重叠方位 ──
    # [EN] A2: preferred occupied -> switches to another non-overlapping anchor
    # 在 box 正下方放一个占位（把 bottom 方位堵死）
    blocker = (box[0], box[3] + 1, box[1] + 60, box[3] + 1 + lh + 4)
    x2, y2 = LP.place_label(box, lw, lh, [blocker], prefer='bottom')
    r2 = _rect(x2, y2, lw, lh)
    ok('A2 首选 bottom 被占时不硬塞（换到不重叠的方位）',
       LP._overlap_area(r2, [blocker]) <= 0.0,
       f'label_rect={r2} blocker={blocker}')

    # ── A3：特定空闲方位稳定选中（确定性）──
    # [EN] A3: a specific free anchor is stably chosen (determinism)
    # 把除了 'right' 之外的方位都堵死：在 box 四周放占位，**留右边一条空**。
    # ⚠ right 标签矩形约 x∈[x1+2, x1+2+lw]、y∈[cy-lh/2, cy+lh/2]，
    #   四个角只占 corner 区域、不压到右边中部，所以 right 是真正空闲的。
    # [EN] Block every anchor except 'right': blockers around the box, **leave the right strip empty**.
    # [EN] ⚠ The right label rect is x in [x1+2, x1+2+lw], y in [cy-lh/2, cy+lh/2]; the four corners
    # [EN] only occupy corner regions and do not press the right-middle, so right is genuinely free.
    occ_all = [
        (box[0] - 60, box[1], box[0], box[3]),     # left
        (box[0], box[3], box[2], box[3] + 40),     # bottom
        (box[0], box[0] - 40, box[2], box[0]),     # top
        # right 留空（不加占位）
        # [EN] right left empty (no blocker)
        (box[0] - 60, box[0] - 40, box[0], box[0]),# top-left
        (box[2], box[0] - 40, box[2] + 60, box[0]),# top-right
        (box[0] - 60, box[3], box[0], box[3] + 40),# bottom-left
        (box[2], box[3], box[2] + 60, box[3] + 40),# bottom-right
    ]
    x3, y3 = LP.place_label(box, lw, lh, occ_all, prefer='bottom')
    r3 = _rect(x3, y3, lw, lh)
    ok('A3 只剩 right 空闲时稳定选中 right（不压任何占位）',
       x3 >= box[2] and LP._overlap_area(r3, occ_all) <= 0.0,
       f'label_rect={r3}')

    # ── A4：8 个候选全被占 → 返回重叠最小者（兜底）──
    # [EN] A4: all 8 occupied -> returns the least-overlapping (backstop)
    # 在 box 八个方位外侧都铺一层，但给 'right' 那层留最薄、
    # 'bottom' 那层留最厚 → 期望返回重叠更小的 right 一侧
    tight = [
        (box[0] - 50, box[1], box[0], box[3]),     # left 厚
        (box[0], box[3], box[2], box[3] + 50),     # bottom 厚
        (box[0], box[0] - 50, box[2], box[0]),     # top 厚
        (box[2], box[1], box[2] + 6, box[3]),      # right 薄（期望）
        (box[0] - 50, box[0] - 50, box[0], box[0]),# top-left 厚
        (box[2], box[0] - 50, box[2] + 50, box[0]),# top-right 厚
        (box[0] - 50, box[3], box[0], box[3] + 50),# bottom-left 厚
        (box[2], box[3], box[2] + 50, box[3] + 50),# bottom-right 厚
    ]
    x4, y4 = LP.place_label(box, lw, lh, tight, prefer='bottom')
    r4 = _rect(x4, y4, lw, lh)
    area4 = LP._overlap_area(r4, tight)
    # 右薄那层重叠 = 只有 right 一侧部分压住（约 lh * 6）；bottom 厚那层会压 lh*50
    ok('A4 全占时返回重叠最小者（落在最薄的 right 一侧）',
       area4 > 0.0 and area4 <= lh * 8.0,
       f'area={area4:.1f}')

    # ── A5：bounds 裁剪 —— 首选出界、界内有空闲 → 落在界内 ──
    # [EN] A5: bounds clip -- preferred out of bounds, an in-bounds free anchor exists -> in bounds
    small_canvas = (0, 0, 240, 220)
    # box5 贴近画布下沿：bottom 方位会落到 y>220（出界），top 方位在界内且空闲
    # [EN] box5 hugs the canvas bottom: the bottom anchor falls y>220 (out of bounds), top is in-bounds
    # [EN] and free
    box5 = (20, 170, 120, 205)
    x5, y5 = LP.place_label(box5, lw, lh, [], bounds=small_canvas, prefer='bottom')
    r5 = _rect(x5, y5, lw, lh)
    inb = (r5[0] >= -0.5 and r5[1] >= -0.5 and r5[2] <= small_canvas[2] + 0.5
           and r5[3] <= small_canvas[3] + 0.5)
    ok('A5 首选出界时改落界内空闲方位（不画出画布）',
       inb and y5 < box5[3], f'label_rect={r5} canvas={small_canvas}')

    # ── A6：不变量 —— 只要存在不重叠方位，返回就不压任何 occupied ──
    # [EN] A6: invariant -- whenever a free anchor exists, the return overlaps no occupied rect
    occ6 = [(box[0] - 40, box[1], box[0], box[3]),   # left 占
            (box[0], box[3], box[2], box[3] + 40)]   # bottom 占
    x6, y6 = LP.place_label(box, lw, lh, occ6, prefer='bottom')
    r6 = _rect(x6, y6, lw, lh)
    ok('A6 存在空闲方位时返回真的不压任何 occupied',
       LP._overlap_area(r6, occ6) <= 0.0,
       f'label_rect={r6}')

    print('标签避让验证：')
    for c in checks:
        cjk(c)
    n_ok = sum(1 for c in checks if c['ok'])
    print(f'\n标签避让验证：{n_ok}/{len(checks)}')
    return 0 if n_ok == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
