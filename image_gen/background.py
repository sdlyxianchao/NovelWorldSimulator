# -*- coding: utf-8 -*-
"""背景图生成：春和景明 · 彩墨江南。

配色定位：**明丽鲜艳的彩墨中国画**（不是灰调水墨）——
青绿远山、柳绿桃粉、暖阳灯笼、天青水色，整体明亮通透；
但笔法、留白、层次仍走中国画语言，不落俗艳。

画面要素（全部程序化绘制，画面上**不含任何文字、题款、印章**）：
- 天光：天青→暖白的竖向渐变（春日晴空）+ 右上暖阳光晕
- 宣纸底：米色 + 纤维颗粒 + 旧纸暗边
- 远山：四层青绿丘陵，越远越淡、越青
- 白墙青瓦民居群：沿河而立，带马头墙、瓦垄、暖色木窗与檐下灯笼
- 石拱桥：跨水而立，带桥栏
- 河道：天青水色 + 民居倒影 + 粼粼受光横线
- 近岸：埠头石阶、垂柳（春柳嫩绿）、乌篷船
- 点景：桃花枝（粉白花簇）、远处渔舟、飞鸟
- 烟雨：极淡的斜细雨丝（春日细雨）

输出规格：
- 母版分辨率 2560×1440（绘制分辨率），默认导出 3840×2160 高清图
- PNG（optimize 无损）+ WebP（quality 92）
- 后处理版本：柔焦版 soft / 线稿版 line / 淡彩版 pale，可直接作界面背景

用法：
    from image_gen.background import generate_title_background, save_backgrounds
    save_backgrounds('assets/images')

English:
Background image generation: Spring Radiance · Color-Ink Jiangnan.
Color positioning: **bright, vivid color-ink Chinese painting** (not gray-toned ink wash) —
blue-green distant hills, willow green and peach pink, warm sun and lanterns, sky-blue water,
overall bright and translucent;
but brushwork, negative space and layering still follow the language of Chinese painting,
without falling into gaudiness.
Scene elements (all drawn programmatically, the image contains **no text, inscriptions or seals
whatsoever**):
- Sky light: vertical gradient from sky blue → warm white (spring clear sky) + warm sun halo in the upper right
- Xuan paper base: beige + fiber grain + darkened old-paper edges
- Distant hills: four layers of blue-green hills, the farther the paler and bluer
- White-walled, blue-tiled dwellings: standing along the river, with horse-head gables, tile ridges, warm wooden windows and lanterns under the eaves
- Stone arch bridge: spanning the water, with railings
- River: sky-blue water + reflections of the dwellings + shimmering lit horizontal lines
- Near shore: stone steps of a landing, weeping willows (fresh green spring willows), black-awning boat
- Accents: peach blossom branches (pink-white clusters), distant fishing boat, flying birds
- Misty rain: very faint slanted fine rain streaks (spring drizzle)
Output specs:
- Master resolution 2560×1440 (drawing resolution), default export 3840×2160 HD image
- PNG (optimize, lossless) + WebP (quality 92)
- Post-processed versions: soft-focus soft / line-art line / light-color pale, usable directly as UI backgrounds
Usage:
    from image_gen.background import generate_title_background, save_backgrounds
    save_backgrounds('assets/images')
"""
from __future__ import annotations

import math
import os
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# ══════════════════════════════════════════════
#  春和景明 · 彩墨配色
# [EN] Spring warmth and bright scenery · color ink palette
# ══════════════════════════════════════════════
PAPER = (250, 245, 232)          # 宣纸（提亮）
PAPER_WALL = (253, 251, 246)     # 白墙
PAPER_EDGE = (231, 220, 198)     # 旧纸暗边
# [EN] Xuan paper (brightened)
# [EN] White wall
# [EN] Old paper dark edges

SKY_TOP = (188, 224, 236)        # 天青（画面上端）
SKY_MID = (222, 238, 238)        # 中段过渡
SKY_LOW = (252, 243, 224)        # 近地平线暖白
# [EN] Sky blue (top of image)
# [EN] Mid-section transition
# [EN] Warm white near horizon

INK = (48, 54, 60)               # 墨（略暖）
INK_DEEP = (34, 44, 54)          # 深墨（船篷）
INK_SOFT = (132, 154, 162)       # 淡墨·带青（雨丝）
# [EN] Ink (slightly warm)
# [EN] Deep ink (boat awning)
# [EN] Light ink · with blue (rain threads)

ROOF_TILE = (94, 110, 126)       # 青瓦
ROOF_RIDGE = (56, 68, 84)        # 脊线
# [EN] Blue tiles
# [EN] Ridge line

HILL_FAR = (176, 204, 210)       # 最远山 · 雾青
HILL_MID = (132, 176, 172)       # 中山 · 青绿
HILL_NEAR = (86, 130, 114)       # 近山 · 墨青绿
HILL_FRONT = (56, 96, 82)        # 前景丘 · 深青绿
# [EN] Farthest mountains · misty blue
# [EN] Mid mountains · blue-green
# [EN] Near mountains · ink blue-green
# [EN] Foreground hills · deep blue-green

WATER = (172, 210, 218)          # 水面 · 天青（提亮）
WATER_DEEP = (128, 172, 186)     # 深水
WATER_LIT = (206, 232, 230)      # 受光水面
# [EN] Water surface · sky blue (brightened)
# [EN] Deep water
# [EN] Lit water surface

WILLOW = (128, 170, 100)         # 柳绿
WILLOW_LIT = (186, 212, 120)     # 受光柳叶（嫩黄绿）
# [EN] Willow green
# [EN] Lit willow leaves (tender yellow-green)

PEACH = (238, 168, 180)          # 桃花粉
PEACH_LIT = (252, 216, 220)      # 受光花瓣（近白粉）
PEACH_DEEP = (224, 132, 154)     # 花心深粉
BRANCH = (122, 88, 68)           # 桃枝（褐墨）
# [EN] Peach blossom pink
# [EN] Lit petals (near-white pink)
# [EN] Deep pink flower center
# [EN] Peach branch (brown ink)

LANTERN = (228, 126, 66)         # 灯笼橙
LANTERN_DEEP = (198, 72, 58)     # 灯笼朱穗
WINDOW = (216, 170, 110)         # 木窗暖光
STONE = (154, 162, 158)          # 石桥 / 石阶
STONE_DARK = (108, 118, 118)     # 石阴面
# [EN] Lantern orange
# [EN] Lantern vermilion tassel
# [EN] Wooden window warm light
# [EN] Stone bridge / stone steps
# [EN] Stone shadow side

# 绘制分辨率（先在此分辨率作画，再放大到目标尺寸）
# [EN] Drawing resolution (draw at this resolution first, then upscale to target size)
BASE_W = 2560
BASE_H = 1440
BASE_SEED = 20261005


# ══════════════════════════════════════════════
#  天光 + 宣纸底
# [EN] Sky light + xuan paper base
# ══════════════════════════════════════════════
def _sky_gradient(width: int, height: int) -> Image.Image:
    """天青 → 暖白的竖向渐变（春日晴空）。
        English:
    Vertical gradient from sky blue → warm white (spring clear sky).
    """
    sky = Image.new('RGB', (1, height))
    px = sky.load()
    for y in range(height):
        t = y / max(1, height - 1)
        if t < 0.55:                      # 上段：天青 → 中段过渡
        # [EN] Upper section: sky blue → mid-section transition
            u = t / 0.55
            c = tuple(int(SKY_TOP[i] + (SKY_MID[i] - SKY_TOP[i]) * u) for i in range(3))
        else:                             # 下段：中段 → 暖白
        # [EN] Lower section: mid-section → warm white
            u = (t - 0.55) / 0.45
            c = tuple(int(SKY_MID[i] + (SKY_LOW[i] - SKY_MID[i]) * u) for i in range(3))
        px[0, y] = c
    return sky.resize((width, height), Image.Resampling.BILINEAR)


def _make_paper(width: int, height: int, seed: int = 11) -> Image.Image:
    """宣纸质感底：米色 + 纤维噪点 + 旧纸暗边。
        English:
    Xuan paper texture base: beige + fiber noise + darkened old-paper edges.
    """
    rnd = random.Random(seed)
    img = Image.new('RGB', (width, height), PAPER)

    sw, sh = max(2, width // 4), max(2, height // 4)
    noise = Image.new('L', (sw, sh))
    px = noise.load()
    for y in range(sh):
        for x in range(sw):
            px[x, y] = 128 + rnd.randint(-13, 13)
    noise = noise.resize((width, height), Image.Resampling.BICUBIC)
    noise = noise.filter(ImageFilter.GaussianBlur(max(0.6, width / 2400.0)))

    mono = Image.new('L', (width, height), 245)
    noise = ImageChops.blend(mono, noise, 0.07)
    img = ImageChops.blend(img, Image.merge('RGB', (noise, noise, noise)), 0.09)

    steps = max(24, int(min(width, height) * 0.05))
    edge = Image.new('L', (width, height), 0)
    ed = ImageDraw.Draw(edge)
    for i in range(steps):
        ed.rectangle([i, i, width - 1 - i, height - 1 - i],
                     outline=int(26 * (1 - i / steps)))
    edge = edge.filter(ImageFilter.GaussianBlur(max(1.0, width / 1200.0)))
    img = Image.composite(Image.new('RGB', (width, height), PAPER_EDGE), img, edge)
    return img


def _warm_glow(width: int, height: int) -> Image.Image:
    """右上角暖阳光晕（让画面透气、有春意）。

    返回 **L 通道遮罩**，由调用方用 `Image.composite` 混入暖白。
    注意别返回整张 RGB——非光晕区会是纯黑，alpha 合成后会把整幅画面压黑。
    
        English:
    Warm sun halo in the upper right (lets the image breathe, gives a feel of spring).
        Returns an **L-channel mask**, to be blended with warm white by the caller via `Image.composite`.
        Note: do not return a full RGB image — non-halo areas would be pure black, and alpha compositing would darken the entire image.
    """
    glow = Image.new('L', (width, height), 0)
    d = ImageDraw.Draw(glow)
    cx, cy = int(width * 0.80), int(height * 0.13)
    r = int(min(width, height) * 0.50)
    steps = 46
    for i in range(steps, 0, -1):
        rr = int(r * i / steps)
        d.ellipse([cx - rr, cy - int(rr * 0.80), cx + rr, cy + int(rr * 0.80)],
                  fill=int(74 * (1 - i / steps) ** 1.5))
    return glow.filter(ImageFilter.GaussianBlur(min(width, height) * 0.055))


# ══════════════════════════════════════════════
#  远山
# [EN] Distant mountains
# ══════════════════════════════════════════════
def _hill_layer(width: int, height: int, base_y: float, amp: float,
                wavelen: float, alpha: int, blur: float,
                color: tuple = INK, seed: int = 0) -> Image.Image:
    """一层江南丘陵（平缓起伏，非尖峰）。color 决定青绿层次。
        English:
    One layer of Jiangnan hills (gentle undulation, not sharp peaks). color determines the
    blue-green layering.
    """
    rnd = random.Random(seed)
    layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    phase = rnd.uniform(0, math.tau)
    phase2 = rnd.uniform(0, math.tau)
    pts = []
    step = max(4, width // 420)
    for x in range(-step, width + step * 2, step):
        y = (base_y
             + math.sin(x / wavelen * math.tau + phase) * amp
             + math.sin(x / (wavelen * 0.37) * math.tau + phase2) * amp * 0.34)
        pts.append((x, y))
    d.polygon([(0, height)] + pts + [(width, height)], fill=color + (alpha,))

    if blur > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
    return layer


# ══════════════════════════════════════════════
#  民居（白墙青瓦 + 马头墙 + 暖窗灯笼）
# [EN] Dwellings (white walls blue tiles + horse-head walls + warm-lit windows and lanterns)
# ══════════════════════════════════════════════
def _lantern(d: ImageDraw.ImageDraw, x: float, y: float, scale: float,
             alpha: int = 235) -> None:
    """檐下挂的一盏灯笼（暖橙，带朱穗）。
        English:
    A lantern hung under the eaves (warm orange, with red tassel).
    """
    r = max(2.0, 4.4 * scale)
    x, y = float(x), float(y)
    d.line([(x, y - r * 1.5), (x, y - r * 0.4)], fill=INK + (alpha,),
           width=max(1, int(scale)))
    d.ellipse([x - r, y - r * 0.4, x + r, y + r * 1.5], fill=LANTERN + (alpha,))
    d.ellipse([x - r * 0.45, y - r * 0.2, x + r * 0.45, y + r * 1.15],
              fill=(244, 176, 116, alpha))
    d.line([(x, y + r * 1.5), (x, y + r * 2.6)], fill=LANTERN_DEEP + (alpha,),
           width=max(1, int(scale)))


def _house(d: ImageDraw.ImageDraw, x: float, ground_y: float, w: float, h: float,
           scale: float, wall_alpha: int, roof_alpha: int, seed: int = 0) -> None:
    """一间江南民居（白墙 · 青瓦 · 暖窗 · 檐下灯笼）。
        English:
    A Jiangnan dwelling (white wall · blue tiles · warm window · lantern under the eaves).
    """
    rnd = random.Random(seed)
    x, w, h = int(x), int(w), int(h)
    gy = int(ground_y)

    # 白墙
    # [EN] White wall
    d.rectangle([x, gy - h, x + w, gy], fill=PAPER_WALL + (wall_alpha,))
    d.rectangle([x, gy - h, x + w, gy],
                outline=STONE_DARK + (int(wall_alpha * 0.55),),
                width=max(1, int(1.8 * scale)))
    # 墙脚潮痕
    # [EN] Damp stains at wall base
    d.rectangle([x, gy - int(7 * scale), x + w, gy],
                fill=(168, 176, 172, wall_alpha))

    # 屋顶（青瓦，两面坡）
    # [EN] Roof (blue tiles, two-slope)
    eave = int(7 * scale)
    ridge_y = gy - h - int(h * 0.40)
    inset = int(w * 0.17)
    d.polygon([(x - eave, gy - h), (x + w + eave, gy - h),
               (x + w - inset, ridge_y), (x + inset, ridge_y)],
              fill=ROOF_TILE + (roof_alpha,))
    # 瓦垄
    # [EN] Tile ridges
    for k in range(1, 6):
        t = k / 6.0
        d.line([(x - eave + (w + eave * 2) * t, gy - h),
                (x + inset + (w - inset * 2) * t, ridge_y)],
               fill=(70, 86, 104, int(roof_alpha * 0.55)), width=1)
    # 屋脊
    # [EN] Roof ridge
    d.line([(x + inset, ridge_y), (x + w - inset, ridge_y)],
           fill=ROOF_RIDGE + (min(255, roof_alpha + 20),),
           width=max(1, int(2.4 * scale)))

    # 马头墙
    # [EN] Horse-head wall
    base = gy - h
    top_y = base - int(h * 0.55)
    levels = 3
    for sx in (x - eave, x + w - int(6 * scale)):
        for k in range(levels):
            y0 = int(base - (base - top_y) * (k + 1) / levels)
            y1 = y0 + max(3, int(7 * scale))
            half_l = int(10 * scale + k * 5 * scale)
            half_r = int(9 * scale + k * 4 * scale)
            d.rectangle([sx - half_l, y0, sx + half_r, y1],
                        fill=PAPER_WALL + (wall_alpha,))
            d.rectangle([sx - half_l, y0, sx + half_r, y0 + max(2, int(3 * scale))],
                        fill=ROOF_TILE + (roof_alpha,))

    # 木窗（暖光）
    # [EN] Wooden window (warm light)
    win_y = gy - int(h * 0.78)
    ww, wh = int(13 * scale), int(15 * scale)
    for k in range(rnd.randint(1, 2)):
        wx = x + int(w * (0.20 + 0.34 * k))
        d.rectangle([wx, win_y, wx + ww, win_y + wh],
                    fill=WINDOW + (int(wall_alpha * 0.92),))
        d.rectangle([wx, win_y, wx + ww, win_y + wh],
                    outline=ROOF_RIDGE + (int(wall_alpha * 0.7),),
                    width=max(1, int(scale)))
        d.line([(wx + ww // 2, win_y), (wx + ww // 2, win_y + wh)],
               fill=PAPER_WALL + (wall_alpha,), width=1)

    # 门
    # [EN] Door
    dw = int(16 * scale)
    dx = x + int(w * 0.42)
    d.rectangle([dx, gy - int(h * 0.40), dx + dw, gy],
                fill=(126, 96, 74, int(wall_alpha * 0.9)))
    d.rectangle([dx, gy - int(h * 0.40), dx + dw, gy],
                outline=ROOF_RIDGE + (int(wall_alpha * 0.6),), width=1)

    # 檐下灯笼（约半数民居挂一盏）
    # [EN] Eave lanterns (about half of dwellings hang one)
    if rnd.random() < 0.55:
        lx = x + w * rnd.uniform(0.24, 0.76)
        _lantern(d, lx, gy - h + int(3 * scale), scale,
                 alpha=int(wall_alpha * 0.95))


def _house_row(d: ImageDraw.ImageDraw, x0: float, x1: float, ground_y: float,
               scale: float, wall_alpha: int, roof_alpha: int, seed: int = 0) -> None:
    """沿途铺一排民居。
        English:
    Lay out a row of dwellings along the way.
    """
    rnd = random.Random(seed)
    x = x0
    i = 0
    while x < x1 - 20 * scale:
        hw = rnd.uniform(78, 138) * scale
        hh = rnd.uniform(54, 96) * scale
        if x + hw > x1:
            hw = x1 - x
        if hw < 34 * scale:
            break
        _house(d, x, ground_y + rnd.uniform(-5, 5) * scale, hw, hh, scale,
               wall_alpha, roof_alpha, seed * 31 + i)
        x += hw + rnd.uniform(5, 18) * scale
        i += 1


# ══════════════════════════════════════════════
#  点景：桥 / 船 / 柳 / 桃 / 树 / 石阶 / 鸟
# [EN] Accent elements: bridge / boat / willow / peach / tree / stone steps / birds
# ══════════════════════════════════════════════
def _arch_bridge(d: ImageDraw.ImageDraw, cx: float, base_y: float,
                 span: float, rise: float, alpha: int = 226) -> None:
    """石拱桥（青石）。
        English:
    Stone arch bridge (bluestone).
    """
    top, inner = [], []
    n = 56
    for i in range(n + 1):
        a = math.pi * i / n
        top.append((cx - span * math.cos(a), base_y - rise * math.sin(a)))
    ispan, irise = span * 0.66, rise * 0.74
    for i in range(n + 1):
        a = math.pi * i / n
        inner.append((cx - ispan * math.cos(a), base_y - irise * math.sin(a)))
    d.polygon(top + inner[::-1], fill=STONE + (alpha,))
    d.line(top, fill=(200, 208, 202, min(255, alpha + 20)),
           width=max(2, int(span * 0.035)))
    deck_y = base_y - rise * 0.88
    for t in range(1, 8):
        px_ = cx - span * 0.82 + span * 1.64 * t / 8
        d.line([(px_, deck_y - int(rise * 0.34)), (px_, deck_y)],
               fill=STONE_DARK + (alpha,), width=max(1, int(span * 0.020)))
    for sgn in (-1, 1):
        bx = cx + sgn * span * 0.97
        d.rectangle([bx - span * 0.055, base_y - rise * 0.12,
                     bx + span * 0.055, base_y + span * 0.10],
                    fill=STONE_DARK + (alpha,))


def _wu_boat(d: ImageDraw.ImageDraw, x: float, y: float, scale: float = 1.0,
             alpha: int = 214) -> None:
    """乌篷船（篷顶一点暖光）。
        English:
    Black-awning boat (a touch of warm light on the awning top).
    """
    w = 36 * scale
    d.polygon([(x - w, y), (x + w, y),
               (x + w * 0.68, y + 8 * scale), (x - w * 0.68, y + 8 * scale)],
              fill=(58, 74, 88, alpha))
    d.chord([(x - w * 0.42, y - 15 * scale), (x + w * 0.42, y + 4 * scale)],
            180, 360, fill=INK_DEEP + (min(255, alpha + 20),))
    d.chord([(x - w * 0.30, y - 13 * scale), (x + w * 0.30, y + 2 * scale)],
            195, 345, fill=(198, 178, 130, int(alpha * 0.5)))
    d.line([(x + w * 0.96, y - 17 * scale), (x + w * 0.60, y + 3 * scale)],
           fill=(102, 82, 64, alpha), width=max(1, int(1.4 * scale)))


def _willow(d: ImageDraw.ImageDraw, x: float, y_top: float, length: float,
            count: int = 10, scale: float = 1.0, alpha: int = 168,
            seed: int = 0) -> None:
    """垂柳：从画面上缘垂下，柳条 + 嫩绿叶簇（春柳）。
        English:
    Weeping willow: hanging down from the top edge of the image, willow branches + fresh green leaf
    clusters (spring willow).
    """
    rnd = random.Random(seed)
    for _ in range(count):
        sx = x + rnd.uniform(-34, 34) * scale * 2
        py_ = y_top
        px_ = sx
        pts = [(px_, py_)]
        segs = rnd.randint(7, 11)
        vx = rnd.uniform(-0.5, 0.5)
        vy = length / segs
        for _s in range(segs):
            vx += rnd.uniform(-0.30, 0.30)
            px_ += vx * scale * 7
            py_ += vy
            pts.append((px_, py_))
        d.line(pts, fill=(150, 170, 106, min(255, alpha + 30)),
               width=max(2, int(scale * 1.8)))
        for (ax, ay) in pts[1:]:
            if rnd.random() < 0.86:
                ll = rnd.uniform(3.5, 8.5) * scale
                ang = rnd.uniform(1.5, 4.6)
                col = WILLOW_LIT if rnd.random() < 0.42 else WILLOW
                d.line([(ax, ay), (ax + math.cos(ang) * ll, ay + math.sin(ang) * ll)],
                       fill=col + (min(255, alpha + 46),),
                       width=max(1, int(scale * 1.5)))


def _peach_branch(d: ImageDraw.ImageDraw, x: float, y: float, length: float,
                  angle_deg: float, scale: float = 1.0,
                  alpha: int = 212, seed: int = 0) -> None:
    """桃花枝：褐墨枝干 + 粉白花簇。
        English:
    Peach blossom branch: brown-ink branches + pink-white flower clusters.
    """
    rnd = random.Random(seed)
    ang = math.radians(angle_deg)
    px_, py_ = x, y
    pts = [(px_, py_)]
    segs = 9
    for _ in range(segs):
        ang += math.radians(rnd.uniform(-16, 16))
        px_ += math.cos(ang) * length / segs
        py_ += math.sin(ang) * length / segs
        pts.append((px_, py_))
    d.line(pts, fill=BRANCH + (alpha,), width=max(2, int(2.6 * scale)))
    # 侧枝
    # [EN] Side branches
    for i in range(2, len(pts) - 1, 2):
        bx, by = pts[i]
        a2 = ang + math.radians(rnd.choice([-46, -38, 40, 48]))
        ex = bx + math.cos(a2) * length * 0.24
        ey = by + math.sin(a2) * length * 0.24
        d.line([(bx, by), (ex, ey)], fill=BRANCH + (int(alpha * 0.85),),
               width=max(1, int(1.6 * scale)))
        pts.append((ex, ey))
    # 花簇
    # [EN] Flower clusters
    for (bx, by) in pts:
        for _k in range(rnd.randint(2, 5)):
            cx = bx + rnd.uniform(-11, 11) * scale
            cy = by + rnd.uniform(-11, 11) * scale
            r = rnd.uniform(3.2, 7.4) * scale
            base = PEACH_LIT if rnd.random() < 0.45 else PEACH
            d.ellipse([cx - r, cy - r * 0.86, cx + r, cy + r * 0.86],
                      fill=base + (min(255, alpha + 38),))
            if rnd.random() < 0.5:
                d.ellipse([cx - r * 0.38, cy - r * 0.34,
                           cx + r * 0.38, cy + r * 0.34],
                          fill=PEACH_DEEP + (min(255, alpha + 22),))


def _tree(d: ImageDraw.ImageDraw, x: float, y: float, scale: float = 1.0,
          alpha: int = 170, seed: int = 0) -> None:
    """岸边远树（青绿团块）。
        English:
    Distant trees on the bank (blue-green clumps).
    """
    rnd = random.Random(seed)
    h = 70 * scale
    d.line([(x, y), (x + 2 * scale, y - h * 0.55)], fill=BRANCH + (alpha,),
           width=max(1, int(2 * scale)))
    for _i in range(9):
        cx = x + rnd.uniform(-26, 26) * scale
        cy = y - h * 0.55 + rnd.uniform(-24, 16) * scale
        r = rnd.uniform(9, 20) * scale
        col = WILLOW_LIT if rnd.random() < 0.3 else HILL_NEAR
        d.ellipse([cx - r, cy - r * 0.82, cx + r, cy + r * 0.82],
                  fill=col + (max(30, int(alpha * 0.7)),))


def _steps(d: ImageDraw.ImageDraw, x: float, y: float, n: int = 5,
           step_w: float = 46, step_h: float = 6, alpha: int = 200) -> None:
    """埠头石阶。
        English:
    Stone steps of a landing.
    """
    for i in range(n):
        w = step_w - i * 5
        d.line([(x, y + i * step_h), (x + w, y + i * step_h)],
               fill=STONE + (alpha,), width=2)
        d.line([(x + w, y + i * step_h), (x + w, y + (i + 1) * step_h)],
               fill=STONE_DARK + (alpha,), width=1)


def _birds(d: ImageDraw.ImageDraw, x: float, y: float, n: int = 5,
           alpha: int = 170, seed: int = 0) -> None:
    """飞鸟（寥寥数笔）。
        English:
    Flying birds (just a few strokes).
    """
    rnd = random.Random(seed)
    for _i in range(n):
        bx = x + rnd.uniform(-60, 120)
        by = y + rnd.uniform(-40, 40)
        s = rnd.uniform(6, 11)
        ink = INK + (alpha,)
        d.arc([bx - s, by - s * 0.5, bx, by + s * 0.5], 200, 340, fill=ink, width=2)
        d.arc([bx, by - s * 0.5, bx + s, by + s * 0.5], 200, 340, fill=ink, width=2)


# ══════════════════════════════════════════════
#  彩墨稿（透明底，便于放大后与高清纸底合成）
# [EN] Color ink draft (transparent background, for compositing with the high-res paper base after
# [EN] upscaling)
# ══════════════════════════════════════════════
def _paint_ink(width: int, height: int, seed: int = BASE_SEED) -> Image.Image:
    """在给定分辨率绘制春和景明·彩墨江南（RGBA，透明底）。
        English:
    Draw Spring Radiance · Color-Ink Jiangnan at the given resolution (RGBA, transparent
    background).
    """
    w, h = width, height
    random.seed(seed)

    water_y = h * 0.615
    gy_right = h * 0.590     # 右岸（中景）
    gy_left = h * 0.665      # 左岸（近景）
    # [EN] Right bank (midground)
    # [EN] Left bank (foreground)

    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))

    # ── 1. 远山四层（越远越淡、越青）──
    # [EN] ── 1. Distant mountains in four layers (farther = lighter and bluer) ──
    layer = Image.alpha_composite(
        layer, _hill_layer(w, h, h * 0.352, h * 0.030, w * 0.66, 78, h * 0.014,
                           HILL_FAR, seed=1))
    layer = Image.alpha_composite(
        layer, _hill_layer(w, h, h * 0.404, h * 0.034, w * 0.50, 112, h * 0.010,
                           HILL_MID, seed=2))
    layer = Image.alpha_composite(
        layer, _hill_layer(w, h, h * 0.456, h * 0.032, w * 0.36, 138, h * 0.006,
                           HILL_NEAR, seed=3))
    layer = Image.alpha_composite(
        layer, _hill_layer(w, h, h * 0.505, h * 0.022, w * 0.24, 158, h * 0.003,
                           HILL_FRONT, seed=4))

    # ── 2. 右岸民居（中景）──
    # [EN] ── 2. Right bank dwellings (midground) ──
    right = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    rd = ImageDraw.Draw(right)
    _house_row(rd, w * 0.605, w * 0.995, gy_right, 0.60, 236, 240, seed=7)
    _tree(rd, w * 0.985, gy_right + h * 0.004, 0.9, 196, seed=17)
    _tree(rd, w * 0.60, gy_right + h * 0.004, 0.8, 186, seed=19)
    layer = Image.alpha_composite(layer, right)

    # ── 3. 水面（天青底 + 渐深 + 粼粼受光横线）──
    # [EN] ── 3. Water surface (sky blue base + deepening gradient + shimmering lit horizontal lines) ──
    water = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    wd = ImageDraw.Draw(water)
    wd.rectangle([0, int(water_y), w, h], fill=WATER + (168,))
    deep = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    dd2 = ImageDraw.Draw(deep)
    for y in range(int(water_y), h, max(2, int(h / 240))):
        depth = (y - water_y) / max(1.0, h - water_y)
        dd2.line([(0, y), (w, y)], fill=WATER_DEEP + (int(6 + depth * 40),))
    deep = deep.filter(ImageFilter.GaussianBlur(max(2.0, h / 300.0)))
    water = Image.alpha_composite(water, deep)
    lit = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ld2 = ImageDraw.Draw(lit)
    for _ in range(130):
        ry = random.uniform(water_y + h * 0.01, h * 0.995)
        rx = random.uniform(0, w)
        rw = random.uniform(w * 0.02, w * 0.12)
        ld2.line([(rx, ry), (rx + rw, ry)],
                 fill=WATER_LIT + (random.randint(48, 120),),
                 width=max(1, int(h / 900)))
    lit = lit.filter(ImageFilter.GaussianBlur(max(1.0, h / 1400.0)))
    water = Image.alpha_composite(water, lit)
    layer = Image.alpha_composite(layer, water)

    # ── 4. 右岸倒影 ──
    # [EN] ── 4. Right bank reflection ──
    ref_h = int(h * 0.14)
    src = right.crop((0, int(water_y - ref_h), w, int(water_y)))
    mir = src.transpose(Image.FLIP_TOP_BOTTOM)
    mir.putalpha(mir.getchannel('A').point(lambda v: int(v * 0.42)))
    mir = mir.filter(ImageFilter.GaussianBlur(max(1.5, h / 420.0)))
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    out.paste(mir, (0, int(water_y)), mir)
    layer = Image.alpha_composite(layer, out)

    # ── 5. 石拱桥 ──
    # [EN] ── 5. Stone arch bridge ──
    bridge = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bridge)
    _arch_bridge(bd, cx=w * 0.735, base_y=water_y + h * 0.028,
                 span=w * 0.072, rise=h * 0.052)
    layer = Image.alpha_composite(layer, bridge)

    # ── 6. 船 ──
    # [EN] ── 6. Boat ──
    boats = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    btd = ImageDraw.Draw(boats)
    _wu_boat(btd, w * 0.315, h * 0.740, 1.15)
    _wu_boat(btd, w * 0.470, h * 0.845, 1.45)
    _wu_boat(btd, w * 0.905, h * 0.705, 0.75, alpha=186)
    layer = Image.alpha_composite(layer, boats)

    # ── 7. 左岸民居（近景）──
    # [EN] ── 7. Left bank dwellings (foreground) ──
    left = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(left)
    _house_row(ld, w * 0.012, w * 0.335, gy_left, 1.05, 246, 252, seed=23)
    _tree(ld, w * 0.348, gy_left + h * 0.004, 1.15, 204, seed=29)
    layer = Image.alpha_composite(layer, left)

    # ── 8. 埠头石阶 ──
    # [EN] ── 8. Wharf stone steps ──
    steps = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(steps)
    _steps(sd, w * 0.185, gy_left + h * 0.004, n=5,
           step_w=w * 0.028, step_h=h * 0.012)
    _steps(sd, w * 0.845, gy_right + h * 0.004, n=4,
           step_w=w * 0.022, step_h=h * 0.010)
    layer = Image.alpha_composite(layer, steps)

    # ── 9. 近景水纹 ──
    # [EN] ── 9. Foreground water ripples ──
    ripples = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    rpd = ImageDraw.Draw(ripples)
    rr = random.Random(97)
    for _ in range(46):
        ry = rr.uniform(h * 0.66, h * 0.99)
        rx = rr.uniform(0, w)
        rw = rr.uniform(w * 0.03, w * 0.14)
        rpd.arc([rx, ry, rx + rw, ry + rr.uniform(5, 14)],
                5, 175, fill=WATER_LIT + (rr.randint(60, 130),), width=1)
    ripples = ripples.filter(ImageFilter.GaussianBlur(max(1.0, w / 2200.0)))
    layer = Image.alpha_composite(layer, ripples)

    # ── 10. 水边苔点（浓墨点睛）──
    # [EN] ── 10. Waterside moss dots (dark ink accents) ──
    moss = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    msd = ImageDraw.Draw(moss)
    mr = random.Random(131)
    for _ in range(34):
        if mr.random() < 0.55:
            mx = mr.uniform(w * 0.015, w * 0.36)
            my = mr.uniform(gy_left - h * 0.006, gy_left + h * 0.012)
        else:
            mx = mr.uniform(w * 0.60, w * 0.99)
            my = mr.uniform(gy_right - h * 0.006, gy_right + h * 0.010)
        for _k in range(mr.randint(3, 9)):
            dx = mr.uniform(-7, 7)
            dy = mr.uniform(-4, 4)
            rr_ = mr.uniform(1.6, 4.2)
            col = HILL_NEAR if mr.random() < 0.5 else INK
            msd.ellipse([mx + dx - rr_, my + dy - rr_ * 0.8,
                         mx + dx + rr_, my + dy + rr_ * 0.8],
                        fill=col + (mr.randint(130, 214),))
    layer = Image.alpha_composite(layer, moss)

    # ── 11. 垂柳（春柳，画面上缘垂下）──
    # [EN] ── 11. Weeping willow (spring willow, hanging from the top of the image) ──
    willow = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    wld = ImageDraw.Draw(willow)
    _willow(wld, w * 0.055, -h * 0.02, h * 0.44, count=13, scale=1.35, seed=41)
    _willow(wld, w * 0.135, -h * 0.03, h * 0.30, count=8, scale=1.05,
            alpha=160, seed=43)
    _willow(wld, w * 0.955, -h * 0.02, h * 0.47, count=14, scale=1.45, seed=47)
    _willow(wld, w * 0.875, -h * 0.03, h * 0.26, count=7, scale=1.0,
            alpha=154, seed=53)
    _willow(wld, w * 0.465, -h * 0.04, h * 0.20, count=6, scale=0.95,
            alpha=132, seed=59)
    layer = Image.alpha_composite(layer, willow)

    # ── 12. 桃花枝（前景点彩：右上 + 左上，画面"靓"主要靠它）──
    # [EN] ── 12. Peach blossom branches (foreground pointillism color: upper right + upper left, the
    # [EN] image's "prettiness" mainly relies on them) ──
    peach = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    pd = ImageDraw.Draw(peach)
    _peach_branch(pd, w * 0.995, -h * 0.01, h * 0.30, 158, 1.30, 216, seed=71)
    _peach_branch(pd, w * 0.900, -h * 0.02, h * 0.22, 150, 1.00, 200, seed=73)
    _peach_branch(pd, w * 0.005, -h * 0.01, h * 0.26, 22, 1.18, 210, seed=77)
    _peach_branch(pd, w * 0.075, -h * 0.02, h * 0.18, 30, 0.92, 194, seed=79)
    layer = Image.alpha_composite(layer, peach)

    # ── 13. 飞鸟 ──
    # [EN] ── 13. Flying birds ──
    birds = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    _birds(ImageDraw.Draw(birds), w * 0.435, h * 0.215, n=6, seed=61)
    layer = Image.alpha_composite(layer, birds)

    # ── 14. 薄雾（减弱版，不压色彩）──
    # [EN] ── 14. Light mist (weakened, does not dull colors) ──
    layer = _apply_mist(layer, w, h)

    return layer


def _apply_mist(layer: Image.Image, w: int, h: int) -> Image.Image:
    """用 alpha 衰减模拟雾气留白（越远越淡 + 数条雾带）。

    比水墨版轻很多：彩墨画若雾太重会把青绿压成灰。
    
        English:
    Use alpha falloff to simulate mist and negative space (the farther the paler + several mist
    bands).
        Much lighter than the ink-wash version: if the mist in a color-ink painting is too heavy it crushes the blue-green into gray.
    """
    mask = Image.new('L', (w, h), 255)
    md = ImageDraw.Draw(mask)

    top_h = int(h * 0.40)
    for i in range(top_h):
        t = i / max(1, top_h)
        md.line([(0, i), (w, i)], fill=int(208 + 47 * t))

    for cy, half, val in ((0.345, 0.070, 214), (0.500, 0.045, 228)):
        y0, y1 = int((cy - half) * h), int((cy + half) * h)
        md.rectangle([0, y0, w, y1], fill=val)

    mask = mask.filter(ImageFilter.GaussianBlur(max(4.0, h * 0.026)))
    a = ImageChops.multiply(layer.getchannel('A'), mask)
    out = layer.copy()
    out.putalpha(a)
    return out


# ══════════════════════════════════════════════
#  雨丝 / 暗角（在最终高清尺寸上叠加，保证锐度）
# [EN] Rain threads / vignette (overlay at final high-res size to ensure sharpness)
# ══════════════════════════════════════════════
def _add_rain(img: Image.Image, seed: int = 5, density: float = 0.00016) -> Image.Image:
    """极淡的斜细雨丝（春日细雨，不压亮度）。
        English:
    Very faint slanted fine rain streaks (spring drizzle, does not suppress brightness).
    """
    rnd = random.Random(seed)
    w, h = img.size
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    count = int(w * h * density)
    for _ in range(count):
        x = rnd.uniform(-0.05 * w, 1.05 * w)
        y = rnd.uniform(-0.05 * h, 1.0 * h)
        length = rnd.uniform(0.010, 0.042) * h
        ang = math.radians(rnd.uniform(76, 84))
        x2 = x + math.cos(ang) * length * 0.30
        y2 = y + length
        d.line([(x, y), (x2, y2)],
               fill=(214, 232, 236, rnd.randint(14, 40)), width=1)
    return Image.alpha_composite(img.convert('RGBA'), layer)


def _add_vignette(img: Image.Image, strength: float = 0.035) -> Image.Image:
    """四边极轻暗角（彩墨画要亮，暗角只用来收边）。
        English:
    Very light vignette on all four sides (a color-ink painting must stay bright; the vignette is
    only for framing the edges).
    """
    w, h = img.size
    v = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(v)
    band = max(8, int(min(w, h) * 0.09))
    for i in range(band):
        d.rectangle([i, i, w - 1 - i, h - 1 - i],
                    outline=int(strength * 255 * (1 - i / band)))
    v = v.filter(ImageFilter.GaussianBlur(band * 0.30))
    return Image.composite(Image.new('RGB', (w, h), (212, 218, 212)), img, v)


# ══════════════════════════════════════════════
#  后处理版本（供界面背景使用）
# [EN] Post-processing version (for UI background use)
# ══════════════════════════════════════════════
def soften(img: Image.Image, radius_ratio: float = 0.010) -> Image.Image:
    """柔焦版：整体虚化，适合做运行界面背景（不抢文字），但保住色彩。
        English:
    Soft-focus version: overall blur, suitable as the run screen background (does not compete with
    text), but preserves color.
    """
    r = max(2.0, min(img.size) * radius_ratio)
    out = img.filter(ImageFilter.GaussianBlur(r))
    out = ImageEnhance.Color(out).enhance(1.10)
    return ImageEnhance.Brightness(out).enhance(1.05)


def to_sketch(img: Image.Image, radius_ratio: float = 0.006,
              edge_gain: float = 2.6, base_keep: float = 0.58) -> Image.Image:
    """线稿版：**保留底色的淡彩线稿**（不是黑白照）。

    1. 轮廓：亮度图的高通响应 → 映射成「乘法因子」（255~72，不压到 0），
       线条为深墨、空白处为纯白，乘法后底色不受损；
    2. 底子：原图往白里退到 base_keep，保住青绿粉的色相；
    相乘 → 有色线稿。最后再加一点饱和，避免发灰。
    
        English:
    Line-art version: **light-color line art that keeps the base colors** (not a black-and-white
    photo).
        1. Contour: high-pass response of the luminance map -> mapped into a "multiplication factor" (255~72, not crushed to 0),
           lines become deep ink, blank areas pure white; after multiplication the base color is not damaged;
        2. Base: the original image fades toward white down to base_keep, preserving the hues of cyan, green and pink;
        multiply -> a colored line art. Finally add a bit of saturation to avoid looking gray.
    """
    r = max(3.0, min(img.size) * radius_ratio)
    g = img.convert('L')

    high = ImageChops.difference(g, g.filter(ImageFilter.GaussianBlur(r)))
    high = high.point(lambda v: min(255, int(v * edge_gain)))
    ink = high.point(lambda v: 255 - int(v * 0.72)).convert('RGB')

    keep = max(0.05, min(1.0, base_keep))
    base = Image.blend(img.convert('RGB'),
                       Image.new('RGB', img.size, (255, 255, 255)), 1.0 - keep)

    out = ImageChops.multiply(ink, base)
    return ImageEnhance.Color(out).enhance(1.32)


def to_pale(img: Image.Image, paper_blend: float = 0.32,
            contrast: float = 0.95, sat: float = 1.34) -> Image.Image:
    """淡彩版：往纸色里退一点（保住彩），最适合当界面底色。
        English:
    Light color version: fade a little toward the paper color (keeping the colors), best suited as a
    UI background.
    """
    faded = Image.blend(img, Image.new('RGB', img.size, PAPER), paper_blend)
    faded = ImageEnhance.Contrast(faded).enhance(contrast)
    faded = ImageEnhance.Color(faded).enhance(sat)
    return ImageEnhance.Brightness(faded).enhance(1.06)


# ══════════════════════════════════════════════
#  对外接口
# [EN] Public interface
# ══════════════════════════════════════════════
def generate_title_background(width: int = 3840, height: int = 2160) -> Image.Image:
    """生成春和景明·彩墨江南背景（无文字、无印章）。
        English:
    Generate the "Spring Harmony, Bright Scenery - Colored Ink Jiangnan" background (no text, no
    seal).
    """
    ink = _paint_ink(BASE_W, BASE_H)
    if (width, height) != (BASE_W, BASE_H):
        ink = ink.resize((width, height), Image.Resampling.LANCZOS)

    paper = _make_paper(width, height).convert('RGB')
    sky = _sky_gradient(width, height)
    # 纸底 + 天光（天光占比高一点，画面才亮）
    # [EN] Paper base + sky light (sky light proportion slightly higher, so the image is bright)
    base = Image.blend(paper, sky, 0.72).convert('RGBA')
    img = Image.alpha_composite(base, ink).convert('RGB')
    # 暖阳光晕：用遮罩把暖白混进去（不做 alpha 合成，避免压黑）
    # [EN] Warm sunlight halo: blend warm white in with a mask (no alpha compositing, to avoid darkening)
    img = Image.composite(Image.new('RGB', (width, height), (255, 246, 214)),
                          img, _warm_glow(width, height))
    img = _add_rain(img)
    img = _add_vignette(img).convert('RGB')

    # 提鲜：这一步决定「灰暗」还是「明丽」
    # [EN] Enhance: this step decides whether it's "dull" or "bright and vivid"
    img = ImageEnhance.Color(img).enhance(1.42)
    img = ImageEnhance.Brightness(img).enhance(1.13)
    img = ImageEnhance.Contrast(img).enhance(1.04)
    return img.filter(ImageFilter.GaussianBlur(0.3))


def generate_scene_background(scene_name: str, width: int = 1200,
                              height: int = 600) -> Image.Image:
    """按场景名生成小幅彩墨过场图（复用同一套笔法）。
        English:
    Generate small colored-ink transition images by scene name (reusing the same brushwork).
    """
    random.seed(abs(hash(scene_name)) % 0xFFFF)
    ink = _paint_ink(BASE_W, BASE_H).resize((width, height), Image.Resampling.LANCZOS)
    paper = _make_paper(width, height).convert('RGB')
    sky = _sky_gradient(width, height)
    base = Image.blend(paper, sky, 0.68).convert('RGBA')
    img = Image.alpha_composite(base, ink).convert('RGB')
    img = ImageEnhance.Color(img).enhance(1.35)
    return to_pale(img, paper_blend=0.30, contrast=0.96, sat=1.10)


def save_backgrounds(out_dir, width: int = 3840, height: int = 2160,
                     with_variants: bool = True, progress=None) -> dict:
    """导出全套背景资源。

    Returns:
        {名称: Path}
    
        English:
    Export the full set of background assets.
        Returns:
            {name: Path}
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    res: dict[str, Path] = {}

    def _say(msg: str):
        if progress:
            progress(msg)

    _say(f'绘制母稿（{BASE_W}×{BASE_H}）…')
    img = generate_title_background(width, height)
    _say(f'母稿完成（{width}×{height}）')

    variants: list = [('', img, 92)]
    if with_variants:
        _say('生成柔焦版 / 线稿版 / 淡彩版…')
        variants.append(('_soft', soften(img), 90))
        variants.append(('_line', to_sketch(img), 92))
        variants.append(('_pale', to_pale(img), 92))

    for suffix, im, q in variants:
        png = out / f'title_bg{suffix}.png'
        im.save(png, optimize=True)
        res[f'png{suffix or "_master"}'] = png
        _say(f'{png.name}  ({png.stat().st_size / 1048576:.1f} MB)')

        webp = out / f'title_bg{suffix}.webp'
        im.save(webp, format='WEBP', quality=q, method=6)
        res[f'webp{suffix or "_master"}'] = webp
        _say(f'{webp.name}  ({webp.stat().st_size / 1048576:.2f} MB)')

    return res


# ══════════════════════════════════════════════
#  AI 背景（文生图原图 → 界面用图）
# [EN] AI backgrounds (text-to-image originals → images for the UI)
#
#  界面背景现在走**文生图**（实景：无锡鼋头渚春季），不再用这里程序化画的图。
#  下面这组函数负责把文生图原图处理成界面能用的两张：
#    title_bg.webp       母版（16:9、3840×2160）→ 开始界面
#    title_bg_soft.webp  柔化版 → 运行界面（面板半透明，背景不能抢字）
#  原图留在 assets/images/bg/ 作为**存档**，随时可以重新处理（换尺寸、改柔化参数）。
#  下面那套程序化绘制（generate_title_background）退居**兜底**：
#  只有连原图都没有时才用，保证缺图时界面不至于白屏。
# [EN] The UI background now uses **text-to-image** (real scene: Wuxi Yuantouzhu in spring), no longer
# [EN] the programmatically drawn images here.
# [EN] The set of functions below handles converting the text-to-image originals into the two images
# [EN] the UI can use:
# [EN] title_bg.webp       master (16:9, 3840×2160) → title screen
# [EN] title_bg_soft.webp → run screen (clear image; dimming is done at runtime by the 天机 BG_DIM
# [EN] paper-colored scrim so the semi-transparent panels' text stays readable)
# [EN] Originals are kept in assets/images/bg/ as an **archive**, so they can be reprocessed at any
# [EN] time (change size, adjust softening parameters).
# [EN] The programmatic drawing below (generate_title_background) is now relegated to **fallback**:
# [EN] Only used when even the original is missing, so the UI does not go blank when images are absent.
# ══════════════════════════════════════════════
BG_SRC_DIR = Path(__file__).resolve().parent.parent / 'assets' / 'images' / 'bg'
TARGET_W, TARGET_H = 3840, 2160
MASTER_NAME = 'title_bg.webp'
SOFT_NAME = 'title_bg_soft.webp'
_SRC_EXTS = ('.png', '.jpg', '.jpeg', '.webp')
# 两张背景都出「清晰」原图：模糊**不再烤进图片**。运行时由天机 BG_DIM 控制纸色滤镜
# 不透明度（默认 35%）来压暗背景、保证文字可读；开始界面与运行界面都只加运行时滤镜，
# 图片本身始终保持高清。
# [EN] Both backgrounds are emitted CLEAR: blur is **no longer baked into the image**. At runtime the 天机
# [EN] `BG_DIM` controls a paper-colored scrim opacity (default 35%) to dim the background and keep text
# [EN] readable; both the start screen and the run screen only get a runtime scrim, the image itself stays HD.
# 无篆书字体，用楷体作落款（白文朱印）
# [EN] no seal-script font available; use Kai (楷体) for the vermilion name seal
SEAL_FONT = r'C:\Windows\Fonts\simkai.ttf'
# ★ 2026-10-14（用户：「用华文行楷」）—— 本机**没有**华文行楷（STXingkai.ttf，商业字体），
# 用**霞鹜文楷**（LXGWWenKai-Regular.ttf，SIL OFL 开源）替代——笔触自然流畅、接近行楷。
# [EN] ★ 2026-10-14 (user: "use 华文行楷 (XingKai)") -- this machine has **no** STXingkai.ttf
# [EN] (commercial); we use LXGW WenKai (SIL OFL open-source) instead -- its strokes are natural
# [EN] and flowing, close to running-regular.
TITLE_FONT = str(Path(__file__).resolve().parent.parent / 'assets' / 'fonts' / 'LXGWWenKai-Regular.ttf')


def find_ai_source() -> Path | None:
    """在 assets/images/bg/ 里找文生图原图（有多张时取体积最大的）。
        English:
    Find the text-to-image source images in assets/images/bg/ (when there are several, take the
    largest by file size).
    """
    if not BG_SRC_DIR.exists():
        return None
    cands = [p for p in BG_SRC_DIR.iterdir()
             if p.is_file() and p.suffix.lower() in _SRC_EXTS]
    return max(cands, key=lambda p: p.stat().st_size) if cands else None


def crop_to_16_9(im: Image.Image, top_bias: float = 0.42) -> Image.Image:
    """裁成 16:9。

    `top_bias` = 纵向富余里**从上方**裁掉的比例。默认 0.42（略小于一半），
    意思是多留一点天空/花枝、多裁一点前景水面 —— 风景照的构图重心通常偏上。
    
        English:
    Crop to 16:9.
        `top_bias` = the proportion cropped **from the top** of the vertical excess. Default 0.42 (slightly less than half),
        meaning keep a bit more sky/flower branches and crop a bit more of the foreground water — landscape photos usually have their compositional center of gravity toward the top.
    """
    w, h = im.size
    want_h = int(round(w * 9 / 16))
    if want_h <= h:
        extra = h - want_h
        top = int(round(extra * top_bias))
        return im.crop((0, top, w, top + want_h))
    want_w = int(round(h * 16 / 9))          # 原图比 16:9 还扁：改裁宽
    # [EN] Original is even wider than 16:9: crop the width
    left = int(round((w - want_w) * 0.5))
    return im.crop((left, 0, left + want_w, h))


def make_master(src, size: tuple[int, int] = (TARGET_W, TARGET_H),
                sharpen: float = 0.55) -> Image.Image:
    """原图 → 界面用母版：裁 16:9 → 放大到目标尺寸 → 轻锐化补回放大损失的细节。

    文生图一次只有 1536×1024 这种尺寸，要到 4K 必须放大。
    放大后用 UnsharpMask 找补一点锐度 —— 不能重，重了会有镶边。
    
        English:
    Source image -> UI master: crop 16:9 -> upscale to the target size -> light sharpening to
    recover detail lost to upscaling.
        Text-to-image only produces sizes like 1536x1024; to reach 4K it must be upscaled.
        After upscaling use UnsharpMask to recover some sharpness — it must not be heavy, or halos will appear.
    """
    im = Image.open(src).convert('RGB')
    im = crop_to_16_9(im)
    if im.size != tuple(size):
        im = im.resize(tuple(size), Image.Resampling.LANCZOS)
    if sharpen > 0:
        im = im.filter(ImageFilter.UnsharpMask(
            radius=2.2, percent=int(sharpen * 100), threshold=3))
    return im


def make_soft(master: Image.Image, blur_ratio: float = 0.0045,
              paper_blend: float = 0.10, bright: float = 1.06,
              sat: float = 0.92, contrast: float = 0.97) -> Image.Image:
    """运行界面用：柔化 + 提亮 + 略降饱和。

    这不是审美处理，是**可读性要求**：运行界面的面板是半透明的，
    背景的高频细节会直接跑到文字后面去。柔化把细节压平、
    纸色混入把对比降下来，文字才能压得住。
    
        English:
    For the running UI: soften + brighten + slightly reduce saturation.
        This is not an aesthetic choice but a **readability requirement**: the running UI panels are semi-transparent,
        and high-frequency background detail runs straight behind the text. Softening flattens the detail,
        and mixing in the paper color lowers the contrast, so the text can hold its own.
    """
    out = master.filter(ImageFilter.GaussianBlur(max(2.0, master.size[0] * blur_ratio)))
    if paper_blend > 0:
        out = Image.blend(out, Image.new('RGB', out.size, PAPER), paper_blend)
    out = ImageEnhance.Color(out).enhance(sat)
    out = ImageEnhance.Contrast(out).enhance(contrast)
    return ImageEnhance.Brightness(out).enhance(bright)


def _add_name_seal(img: Image.Image, blur_r: float = 0.0) -> Image.Image:
    """在左上角留白处盖一枚「婴宁」朱文印章（2026-10-14 用户：「把字去掉 只留一个章」）。

    只保留引首章（"婴宁"印章），去掉题字「笑矣乎」和名号章。
    位置由亮度决定：取四角里平均亮度最高（= 最空）的一角，避免盖到人物或风景上；
    两处用同一函数，落点一致。
    [EN] Stamp a single "婴宁" vermilion seal in the top-left negative space
    [EN] (2026-10-14 user: "remove the text, keep only one seal").
    [EN] Only the leading seal ("婴宁") is kept; the title "笑矣乎" and name seals are removed.
    [EN] Position is decided by luminance: the emptiest corner (highest mean brightness) is picked,
    [EN] keeping the seal off the figure and scenery; both images use the same function.
    """
    W, H = img.size
    S = max(48, int(W * 0.026))                   # 4K 下 ≈ 100px
    corners = {
        'tl': (0, 0, W // 2, H // 2),
        'tr': (W // 2, 0, W, H // 2),
        'bl': (0, H // 2, W // 2, H),
        'br': (W // 2, H // 2, W, H),
    }
    best, best_v = None, -1
    for k, (x0, y0, x1, y1) in corners.items():
        crop = img.crop((x0, y0, x1, y1)).convert('L')
        cs = list(crop.get_flattened_data())
        v = sum(cs) / len(cs)
        if v > best_v:
            best_v, best = v, k
    x0, y0, x1, y1 = corners[best]
    # ★ 2026-10-14（用户：「设置之后图章贴到窗口边框」）—— 边距从 2% → 3.5%
    #   （4K 下 3840*0.035=134px，1080p 下 1920*0.035=67px —— 不再贴边）
    # [EN] ★ 2026-10-14 (user: "the seal is stuck to the window border") -- margin 2% -> 3.5%
    # [EN] (4K 3840*0.035=134px, 1080p 1920*0.035=67px -- no longer flush with the edge)
    m = int(W * 0.035)
    sx = (x0 + m) if best in ('tl', 'bl') else (x1 - S - m)
    sy = (y0 + m) if best in ('tl', 'tr') else (y1 - S - m)

    seal = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(seal)
    VERM = (200, 25, 20)
    PAPER = (250, 245, 232)
    SEAL_ALPHA = 160
    d.rectangle([0, 0, S, S], fill=VERM + (SEAL_ALPHA,))
    d.rectangle([int(S * 0.07), int(S * 0.07), int(S * 0.93), int(S * 0.93)],
                outline=PAPER + (SEAL_ALPHA,), width=max(2, int(S * 0.02)))
    seal_font = ImageFont.truetype(SEAL_FONT, int(S * 0.34)) if os.path.exists(SEAL_FONT) \
        else ImageFont.load_default()
    cell = S / 2.0
    for i, ch in enumerate(('婴', '宁')):
        bb = d.textbbox((0, 0), ch, font=seal_font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        cx = S / 2 - tw / 2 - bb[0]
        cy = cell * i + cell / 2 - th / 2 - bb[1]
        d.text((cx, cy), ch, font=seal_font, fill=PAPER + (SEAL_ALPHA,))
    if blur_r > 0:
        seal = seal.filter(ImageFilter.GaussianBlur(blur_r))
    out = img.convert('RGBA')
    out.alpha_composite(seal, (int(sx), int(sy)))
    return out.convert('RGB')



# 文件名里带这些词的 = 这张原图**已经处理过**（已放大 + 已锐化），不要再锐化一次。
# [EN] Filenames containing these words = this original has **already been processed** (already
# [EN] upscaled + already sharpened), do not sharpen again.
#
# 为什么需要：真原图丢了的时候（本机就发生过一次），可以从成品
# `title_bg.webp` 倒出一份"存档原图"救急。但那份图**已经锐化过**，
# 再走一遍 `make_master()` 就是二次锐化 —— 实测边缘 stddev 从 30.6 涨到 32.6，
# 会在高对比边缘加出白边。所以按文件名认出来，跳过锐化。
# [EN] Why this is needed: when the real original is lost (this happened once on this machine), you can
# [EN] recover from the finished
# [EN] `title_bg.webp` by exporting an "archive original" as an emergency measure. But that image has
# [EN] **already been sharpened**,
# [EN] and running `make_master()` again means double sharpening — measured edge stddev rose from 30.6
# [EN] to 32.6,
# [EN] which adds white halos on high-contrast edges. So recognize it by filename and skip sharpening.
_PROCESSED_HINTS = ('_archive', '_processed', '_已处理')


def is_processed_source(src) -> bool:
    """这张原图是不是"已处理过的存档"（见 `_PROCESSED_HINTS`）。
        English:
    Whether this source image is an "already-processed archive" (see `_PROCESSED_HINTS`).
    """
    name = Path(src).name.lower()
    return any(h in name for h in _PROCESSED_HINTS)


def build_from_source(src=None, out_dir=None, size: tuple[int, int] = (TARGET_W, TARGET_H),
                      progress=None) -> dict:
    """把文生图原图构建成界面用背景。找不到原图就返回空 dict（调用方自行兜底）。
        English:
    Build the text-to-image source image into a UI background. If no source image is found, return
    an empty dict (the caller handles the fallback itself).
    """
    src = Path(src) if src else find_ai_source()
    if src is None or not Path(src).exists():
        return {}
    out = Path(out_dir) if out_dir else \
        Path(__file__).resolve().parent.parent / 'assets' / 'images'
    out.mkdir(parents=True, exist_ok=True)
    say = progress or (lambda m: None)

    with Image.open(src) as probe:
        say(f'读取文生图原图：{src.name}（{probe.size[0]}×{probe.size[1]}）')
    # 存档原图已经锐化过了 —— 再锐化一次会加白边（`is_processed_source` 的注释）
    # [EN] The archive original has already been sharpened — sharpening again adds white halos (see the
    # [EN] comment in `is_processed_source`)
    already = is_processed_source(src)
    if already:
        say('这是一张"已处理过的存档原图"，跳过锐化（避免二次锐化加白边）')
    base = make_master(src, size, sharpen=0 if already else 0.40)
    # 两张背景都「清晰」：模糊**不再烤进图片**（用户要求背景高清、不模糊）。
    # 运行时的压暗交给天机 BG_DIM 纸色滤镜层，这里只负责出高清原图 + 盖章。
    # [EN] Both backgrounds are CLEAR: blur is no longer baked in (user wants a crisp, non-blurry background).
    # [EN] The runtime dimming is handled by the 天机 BG_DIM paper-colored scrim; here we only emit the HD
    # [EN] image and stamp the seal.
    master = _add_name_seal(base, 0.0)
    soft = _add_name_seal(base, 0.0)

    res: dict = {'source': Path(src)}
    res['master'] = out / MASTER_NAME
    master.save(res['master'], format='WEBP', quality=92, method=6)
    say(f'{MASTER_NAME}  {res["master"].stat().st_size / 1048576:.1f} MB')
    res['soft'] = out / SOFT_NAME
    soft.save(res['soft'], format='WEBP', quality=90, method=6)
    say(f'{SOFT_NAME}  {res["soft"].stat().st_size / 1048576:.2f} MB')
    return res


if __name__ == '__main__':
    import sys
    _root = Path(__file__).resolve().parent.parent
    _out = _root / 'assets' / 'images'
    if len(sys.argv) > 1 and sys.argv[1] not in ('--procedural',):
        r = build_from_source(sys.argv[1], _out, progress=lambda m: print(' ', m))
        print('完成 →', r.get('master'))
    else:
        _w = int(sys.argv[2]) if len(sys.argv) > 2 else 3840
        _h = int(sys.argv[3]) if len(sys.argv) > 3 else 2160
        r = save_backgrounds(_out, _w, _h, progress=lambda m: print(' ', m))
        print(f'\n共导出 {len(r)} 个文件 → {_out}')

