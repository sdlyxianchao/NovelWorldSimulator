# -*- coding: utf-8 -*-
"""给开始界面 Logo（assets/images/start_logo.png）加圆角。

为什么单独一个脚本、不塞进图标管线
------------------------------------
开始界面那块 76px 的展示图是**独立**的 `start_logo.png`（保留内部流线版，
与窗口/任务栏走 `icon_source.png` 管线的简化剪影**故意不是同一张**）。
它不走 `image_gen/icon.py` 的五份产物生成，所以圆角也要单独处理 —— 否则
`make_art.py` 一跑、背景/图标重生成，这块展示图的圆角就被"漏掉"又变回方角。

圆角比例取 0.20，与 `icon.py` 的 `SRC_RADIUS`(0.22) 观感协调（略小一点，
因为展示图是方底实心图，太大反而会显得空）。

做法：RGB → RGBA，四角按圆角矩形蒙版**裁透明**（不重绘内容）。
源图本身没有透明区，所以 `alpha = min(原 alpha, 圆角蒙版)` 等价、且幂等 ——
重复跑不会把圆角越裁越小，也不破坏任何已有透明区。

English:
Round the corners of the start-screen logo (assets/images/start_logo.png).
Why a standalone script, not in the icon pipeline
------------------------------------
The 76px display image on the start screen is the **standalone** `start_logo.png`
(the version with interior streamlines, intentionally NOT the same as the simplified
silhouette that window/taskbar get through the `icon_source.png` pipeline).
It doesn't go through `image_gen/icon.py`'s five-artifact generation, so its corners
must be rounded separately -- otherwise one run of `make_art.py` (which regenerates the
background/icons) would "miss" this display image and turn it back into a square.
Corner radius is 0.20, coordinated with `icon.py`'s `SRC_RADIUS` (0.22) for a consistent
look (a touch smaller, since the display image is a solid square and too much would look empty).
Method: RGB -> RGBA, cut the four corners transparent by a rounded-rectangle mask (no redraw).
The source has no transparency, so `alpha = min(src alpha, rounded mask)` is equivalent and
idempotent -- rerunning won't shrink the corners further, nor destroy any existing transparency.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

APP_DIR = Path(__file__).resolve().parent.parent
IMG = APP_DIR / 'assets' / 'images'

#: 圆角半径占短边的比例（与 `icon.py` 的 `SRC_RADIUS` 协调，见文件头）。
# [EN] Corner radius as a ratio of the shorter side (coordinated with `icon.py`'s `SRC_RADIUS`; see header).
ROUND_RATIO = 0.20


def round_start_logo(path: 'Path | str' = None, ratio: float = ROUND_RATIO,
                     *, backup: bool = True) -> Path:
    """给 `start_logo.png` 四角裁透明；返回处理后的文件路径。

    **始终从方角原图重新生成**（参数驱动、幂等）：第一次跑把当前的 `start_logo.png`
    备份成方角原图（`logo_drafts/start_logo_pre-rounded.png`）；之后每次都从这份
    方角原图 apply 当前半径。这样改半径（包括反例法把半径改 0）能**真正**落到位图上 ——
    若改成"在已圆角的图上增量 min"，旧透明会被保留，关掉圆角也看不出来。

    `backup=True` 时仅首次备份方角原图，之后不覆盖（留作可恢复的原始方角图）。

        English:
    Cut the four corners of `start_logo.png` transparent; return the processed path.
    **Always regenerate from the square original** (parameter-driven, idempotent): the first run
    backs up the current `start_logo.png` as a square original
    (`logo_drafts/start_logo_pre-rounded.png`); every later run applies the current radius to that
    square original. This way changing the radius (including the counter-example setting it to 0)
    **actually** lands on the bitmap -- if we instead did an incremental min on an already-rounded
    image, the old transparency would persist and turning rounding off would be invisible.
    With `backup=True`, the square original is backed up only on the first run, not overwritten
    afterwards (kept as a recoverable original square image).
    """
    path = Path(path) if path else IMG / 'start_logo.png'
    bak = APP_DIR / 'logo_drafts' / 'start_logo_pre-rounded.png'

    if bak.exists():
        # 之后的每次：从方角原图 apply 当前半径（不受 start_logo 当前状态影响）。
        # [EN] Every later run: apply the current radius to the square original (independent of
        # [EN] start_logo's current state).
        src = Image.open(bak)
    else:
        if not path.exists():
            raise FileNotFoundError(f'找不到开始界面 Logo：{path}')
        src = Image.open(path)
        if backup:
            # 仅首次备份方角原图（此时 path 还是方角）。
            # [EN] Back up the square original only on the first run (path is still square here).
            bak.parent.mkdir(parents=True, exist_ok=True)
            bak.write_bytes(path.read_bytes())

    im = src.convert('RGBA')
    W, H = im.size
    # ★ 半径按短边比例算（方图即边长比例）。改成 0 就是方角 —— 反例法就是打这个。
    # [EN] ★ Radius from the shorter side ratio (square image ⇒ edge ratio). 0 means square corners --
    # [EN] the counter-example method targets exactly this line.
    radius = int(min(W, H) * ratio)
    # 圆角矩形蒙版：圆角内不透明、四角透明。
    # [EN] Rounded-rect mask: opaque inside the rounded rect, transparent at the four corners.
    mask = Image.new('L', (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, W - 1, H - 1], radius=radius, fill=255)
    # 源是方角实心图（无透明），直接把蒙版当作 alpha —— 半径即形状，参数驱动。
    # [EN] The source is a square solid image (no transparency); use the mask directly as alpha --
    # [EN] the radius is the shape, parameter-driven.
    im.putalpha(mask)
    im.save(path)
    return path


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else None
    out = round_start_logo(target)
    print(f'已加圆角：{out}')
