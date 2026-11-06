# -*- coding: utf-8 -*-
"""淡彩水彩「鼋头渚」—— 纯 Pillow 本地绘制（不联网、零成本）。

为什么有这个模块
----------------
界面背景的正常来源是**文生图**（`assets/images/bg/` 放原图 → `make_art.py` 处理成
`title_bg.webp` / `title_bg_soft.webp`）。但出图服务会**整段 429 限流**
（v1 写实版、v2 淡彩版、这次第三次，连「一个红苹果」这种提示词也出不来），
这时界面就只能一直挂着旧图。

这个模块是**兜底**：一条命令出一张淡彩水彩版，不用等出图服务。
出图恢复后照样 `make_art.py --from <AI 原图>` 覆盖掉它。

它是什么、不是什么
------------------
**是写意的**：用「大块晕染 + 湿边 + 纸纹」逼近水彩的观感，构图按**界面需求**走。
**不是**写实照片，也不是真水彩扫描件 —— 细节靠不了它，靠它撑"气韵"。

画的时候踩过两个坑（记在这儿免得重犯）
--------------------------------------
1. **别拿 `background._hill_layer()` 当"半岛"用** —— 它会把多边形一直填到画底，
   结果是下半张图糊成一整块绿色。岸线要用本模块的 `_landmass()`（有明确的下沿）。
2. **"淡彩"不等于"淡到看不见"** —— 第一版 `paper_blend=0.30` + 各种 alpha 30~90，
   出来平均饱和度只有 **0.038**、亮度 236，就是一张白纸。
   现在把色板整体加重、纸色回混收到 0.16，实测平均饱和 ~0.11、亮度 ~222。

三条硬规矩（跟文生图那版一致）
------------------------------
1. **画面中部必须留空** —— 开始界面的标题就在正中，中部太满会跟文字打架。
2. **色要淡、留白多** —— 面板是半透明的，背景一浓就抢字。
3. **无文字、无水印、无边框**。

跑法：
    python make_art.py --watercolor          # 用它重建两张背景
    python tools/verify_background.py        # 验证

English:
Light-color watercolor "Yuantouzhu" — pure local Pillow drawing (no network, zero cost).
Why this module exists
----------------
The normal source of the UI background is **text-to-image** (`assets/images/bg/` holds originals
→ `make_art.py` processes them into
`title_bg.webp` / `title_bg_soft.webp`). But the image service can be **rate-limited with 429
across the board**
(v1 realistic version, v2 light-color version, this third time — even prompts like "a red apple"
can't come out),
at which point the UI can only keep showing the old image.
This module is a **fallback**: one command produces a light-color watercolor version, no need to
wait for the image service.
Once image generation recovers, `make_art.py --from <AI original>` will still overwrite it.
What it is, what it isn't
------------------
**It is impressionistic**: uses "large washes + wet edges + paper texture" to approach the look
of watercolor, composition follows **UI needs**.
**It is not** a realistic photo, nor a real watercolor scan — fine detail can't rely on it, it
carries the "spirit" instead.
Two pitfalls hit during drawing (noted here to avoid repeating)
--------------------------------------
1. **Don't use `background._hill_layer()` as a "peninsula"** — it fills the polygon all the way to the bottom of the canvas,
   resulting in the lower half of the image blurring into a single green mass. Shorelines should use this module's `_landmass()` (has a clear lower edge).
2. **"Light color" doesn't mean "so light it becomes invisible"** — the first version's `paper_blend=0.30` + various alphas 30~90,
   produced average saturation of only **0.038**, brightness 236 — just a sheet of white paper.
   Now the palette is overall heavier, paper-color remix reduced to 0.16, measured average saturation ~0.11, brightness ~222.
Three hard rules (same as the text-to-image version)
------------------------------
1. **The middle of the image must be kept empty** — the start screen's title is right in the center, too full in the middle will fight the text.
2. **Colors light, plenty of whitespace** — the panel is semi-transparent, if the background is too strong it steals from the text.
3. **No text, no watermark, no border**.
How to run:
    python make_art.py --watercolor          # Use it to rebuild the two backgrounds
    python tools/verify_background.py        # Verify
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

from image_gen.background import _make_paper, make_soft           # noqa: F401

# ── 色板（"淡彩"区间：高明度、中低饱和 —— **但不能淡到看不见**）──
C_SKY_TOP = (150, 182, 202)     # 天青灰蓝
# [EN] ── Palette ("light color" range: high brightness, medium-low saturation — **but not so light it
# [EN] becomes invisible**) ──
# [EN] Sky blue-gray
C_SKY_MID = (198, 216, 224)
C_SKY_LOW = (240, 238, 228)     # 暖白
C_LAKE_FAR = (198, 220, 222)    # 远处水面（近天光）
C_LAKE_NEAR = (140, 190, 188)   # 近处水面（淡湖碧）
C_HILL_FAR = (162, 184, 198)    # 太湖仙岛：最远、最淡
C_HILL_MID = (136, 162, 174)    # 鹿顶山
C_SHORE = (148, 172, 148)       # 鼋头渚半岛（带青绿）
# [EN] Warm white
# [EN] Distant water surface (near sky light)
# [EN] Near water surface (light lake green)
# [EN] Taihu Immortal Island: farthest, lightest
# [EN] Luding Mountain
# [EN] Yuantouzhu Peninsula (with blue-green)
C_SHORE_NEAR = (126, 152, 128)
C_BLOSSOM = (250, 214, 222)     # 染井吉野樱（粉白）
# [EN] Somei Yoshino cherry (pink-white)
C_BLOSSOM_HI = (255, 240, 242)
C_BLOSSOM_DEEP = (234, 170, 190)
C_WILLOW = (176, 202, 152)      # 柳芽嫩绿
# [EN] Willow sprout tender green
C_WILLOW_DEEP = (146, 178, 124)
C_STONE = (168, 172, 166)       # 长春桥青石
# [EN] Changchun Bridge bluestone
C_SAIL = (253, 251, 246)
C_TRUNK = (146, 134, 124)

# ── 构图锚点（比例，改这里就能挪画面）──
HORIZON = 0.500        # 地平线 / 水线
LAKE_BOTTOM = 0.985    # 湖面下沿。**要铺到接近画底** —— 只铺到 0.84 的话，
                       # 最下面一条是「没画东西的纸」，还带一圈旧纸暗边，
                       # 看着像脏了（第一版就是这样）。
# [EN] ── Composition anchors (ratios, change these to move the image) ──
# [EN] Horizon / waterline
# [EN] Lower edge of lake surface. **Must extend near the bottom of the canvas** — if it only extends
# [EN] to 0.84,
# [EN] the bottommost strip is "paper with nothing drawn on it", plus a ring of old-paper dark edge,
# [EN] looking dirty (that's how the first version was).


# ══════════════════════════════════════════════
#  基础笔法
# [EN] Base brushwork
# ══════════════════════════════════════════════
def _wash(size, color, alpha: int, blur: float, draw_fn=None) -> Image.Image:
    """一笔"晕染"：把 `draw_fn` 画在遮罩上 → 模糊成柔边 → 乘上颜色与不透明度。

    水彩的观感**主要来自这里**：形状是软的，不是描出来的线。
    
        English:
    One "wash" stroke: draw `draw_fn` onto the mask → blur into soft edges → multiply by color and
    opacity.
        The watercolor look **mainly comes from here**: shapes are soft, not drawn lines.
    """
    mask = Image.new('L', size, 0)
    if draw_fn is not None:
        draw_fn(ImageDraw.Draw(mask))
    if blur > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    if alpha < 255:
        mask = mask.point(lambda v: int(v * alpha / 255))
    layer = Image.new('RGBA', size, color + (0,))
    layer.putalpha(mask)
    return layer


def _wet_edge(mask: Image.Image, r_in: float, r_out: float,
              strength: float = 0.55) -> Image.Image:
    """水彩的**湿边**（颜料往边缘堆积形成的一圈深色）。

    做法：同一个形状做两次不同半径的模糊再相减 → 得到一圈"环"，
    把这一环单独加深，形状就有了"水渍感"，不再是均匀的一块。
    
        English:
    Watercolor's **wet edge** (a ring of darker pigment that accumulates toward the edge).
        Method: blur the same shape twice at different radii then subtract → get a "ring",
        darken this ring separately, and the shape gains a "water stain feel", no longer a uniform block.
    """
    inner = mask.filter(ImageFilter.GaussianBlur(max(0.5, r_in)))
    outer = mask.filter(ImageFilter.GaussianBlur(r_out))
    ring = ImageChops.subtract(outer, inner)
    return ring.point(lambda v: int(v * strength))


def _paper_grain(size, seed: int = 7, strength: int = 14) -> Image.Image:
    """细纸纹（低对比噪点）—— 叠在最后，让整张图"有纸感"。
        English:
    Fine paper texture (low-contrast noise) — overlaid last, to give the whole image a "paper feel".
    """
    w, h = size
    rnd = random.Random(seed)
    small = Image.new('L', (max(1, w // 3), max(1, h // 3)))
    small.putdata([128 + rnd.randint(-strength, strength)
                   for _ in range(small.width * small.height)])
    return small.resize(size, Image.Resampling.BILINEAR)


# ══════════════════════════════════════════════
#  景物
# [EN] Scenery
# ══════════════════════════════════════════════
def _sky(w: int, h: int, horizon: float) -> Image.Image:
    """天：上青下暖白的竖向渐变 + 极淡的水彩横向扫痕。
        English:
    Sky: vertical gradient from cyan at top to warm white at bottom + very faint horizontal
    watercolor sweeps.
    """
    sky = Image.new('RGB', (1, h))
    px = sky.load()
    hz = max(1, int(h * horizon))
    for y in range(h):
        t = min(1.0, y / hz)
        if t < 0.6:
            u = t / 0.6
            c = tuple(int(C_SKY_TOP[i] + (C_SKY_MID[i] - C_SKY_TOP[i]) * u)
                      for i in range(3))
        else:
            u = (t - 0.6) / 0.4
            c = tuple(int(C_SKY_MID[i] + (C_SKY_LOW[i] - C_SKY_MID[i]) * u)
                      for i in range(3))
        px[0, y] = c
    sky = sky.resize((w, h), Image.Resampling.BILINEAR).convert('RGBA')

    # 横向扫痕：水彩铺天空时留下的笔路（很淡，只做质感）
    # [EN] Horizontal sweep marks: brush paths left when watercolor washes the sky (very light, texture
    # [EN] only)
    rnd = random.Random(3)
    for _ in range(16):
        y = rnd.uniform(0, horizon * h * 0.92)
        thick = rnd.uniform(h * 0.004, h * 0.020)
        a = int(rnd.uniform(10, 24))
        sky = Image.alpha_composite(sky, _wash(
            (w, h), (255, 255, 255), a, h * 0.010,
            lambda d, y=y, thick=thick:
                d.rectangle([-10, y - thick, w + 10, y + thick], fill=255)))
    return sky.convert('RGB')


def _hilI(w, h, base_y, amp, wavelen, color, alpha, blur, seed,
          x0=-0.05, x1=1.05) -> Image.Image:
    """一层远山（**画在水面之前**，下半部分会被水盖住，所以可以填到画底）。
        English:
    A layer of distant mountains (**painted before the water surface**, the lower part will be
    covered by water, so it can be filled down to the canvas bottom).
    """
    rnd = random.Random(seed)

    def shape(d: ImageDraw.ImageDraw):
        ph1, ph2 = rnd.uniform(0, math.tau), rnd.uniform(0, math.tau)
        pts = []
        step = max(2, w // 240)
        for x in range(int(x0 * w), int(x1 * w) + step, step):
            y = (base_y * h
                 + math.sin(x / (wavelen * w) * math.tau + ph1) * amp * h
                 + math.sin(x / (wavelen * w * 0.37) * math.tau + ph2)
                 * amp * h * 0.34)
            pts.append((x, y))
        if len(pts) >= 2:
            d.polygon(pts + [(pts[-1][0], h + 10), (pts[0][0], h + 10)], fill=255)

    layer = _wash((w, h), color, alpha, blur, shape)
    mask = Image.new('L', (w, h), 0)
    shape(ImageDraw.Draw(mask))
    ring = _wet_edge(mask, blur * 0.7, blur * 2.8, 0.45)
    edge = Image.new('RGBA', (w, h), tuple(max(0, c - 26) for c in color) + (0,))
    edge.putalpha(ring.point(lambda v: int(v * alpha / 255)))
    return Image.alpha_composite(layer, edge)


# 名字里那个大写 I 是历史笔误，保留以免外部引用失效
# [EN] The capital I in the name is a historical typo, kept to avoid breaking external references
_hill = _hilI


def _landmass(w: int, h: int, x0: float, x1: float, top: float, amp: float,
              wavelen: float, water: float, color, alpha: int, blur: float,
              seed: int, refl: bool = True) -> Image.Image:
    """一块**有下沿**的陆地（半岛 / 岛）：起伏的上缘 + 水线处的下沿。

    ⚠ **不要拿 `background._hill_layer()` 当半岛用** —— 它会一直填到画底，
    下半张图会糊成一整块颜色（第一版就是这么翻车的）。
    
        English:
    A landmass **with a lower edge** (peninsula / island): undulating upper edge + lower edge at the
    waterline.
        ⚠ **Do not use `background._hill_layer()` as a peninsula** — it fills all the way to the canvas bottom,
        and the lower half of the image turns into one smeared block of color (that's exactly how the first version failed).
    """
    rnd = random.Random(seed)

    def top_pts():
        ph1, ph2 = rnd.uniform(0, math.tau), rnd.uniform(0, math.tau)
        pts = []
        step = max(2, w // 260)
        for x in range(int(x0 * w), int(x1 * w) + step, step):
            y = (top * h
                 + math.sin(x / (wavelen * w) * math.tau + ph1) * amp * h
                 + math.sin(x / (wavelen * w * 0.41) * math.tau + ph2)
                 * amp * h * 0.38)
            pts.append((max(x0 * w - step, min(x, x1 * w + step)), y))
        return pts

    def shape(d: ImageDraw.ImageDraw):
        pts = top_pts()
        if len(pts) < 2:
            return
        d.polygon(pts + [(pts[-1][0], water * h), (pts[0][0], water * h)],
                  fill=255)

    layer = _wash((w, h), color, alpha, blur, shape)
    mask = Image.new('L', (w, h), 0)
    shape(ImageDraw.Draw(mask))
    ring = _wet_edge(mask, blur * 0.7, blur * 2.6, 0.42)
    edge = Image.new('RGBA', (w, h), tuple(max(0, c - 28) for c in color) + (0,))
    edge.putalpha(ring.point(lambda v: int(v * alpha / 255)))
    out = Image.alpha_composite(layer, edge)

    if refl:
        # 水里的倒影：把岸形翻到水线以下，压淡 + 打散
        # [EN] Reflections in water: flip shore shapes below the waterline, lighten + break apart
        r = Image.new('L', (w, h), 0)
        shape(ImageDraw.Draw(r))
        flipped = r.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        shift = Image.new('L', (w, h), 0)
        shift.paste(flipped, (0, int(2 * water * h) - h))
        refl_layer = Image.new('RGBA', (w, h), color + (0,))
        refl_layer.putalpha(shift.filter(ImageFilter.GaussianBlur(h * 0.012))
                            .point(lambda v: int(v * alpha * 0.26 / 255)))
        out = Image.alpha_composite(out, refl_layer)
    return out


def _lake(w: int, h: int, horizon: float, bottom: float) -> Image.Image:
    """太湖：远白近碧的铺色 + 几道更亮的湖光。
        English:
    Taihu: base wash from white in the distance to jade-green up close + a few brighter lake glints.
    """
    y0, y1 = h * horizon, h * bottom
    lake = _wash((w, h), C_LAKE_NEAR, 214, h * 0.010,
                 lambda d: d.rectangle([-10, y0, w + 10, y1], fill=255))

    # 纵向渐变：远处（上）更淡，近处（下）更碧
    # [EN] Vertical gradient: distant (top) lighter, near (bottom) more green
    grad = Image.new('L', (w, h), 0)
    gpx = grad.load()
    for y in range(max(0, int(y0) - 4), min(h, int(y1) + 6)):
        t = (y - y0) / max(1.0, y1 - y0)
        v = int(96 + 159 * t)
        for x in range(0, w, 2):
            gpx[x, y] = v
            gpx[min(w - 1, x + 1), y] = v
    lake.putalpha(ImageChops.multiply(lake.getchannel('A'), grad))

    # 湖光：几道更亮的横线，越近越长
    # [EN] Lake sparkle: several brighter horizontal lines, longer the nearer they are
    rnd = random.Random(21)
    for _ in range(30):
        t = rnd.random() ** 0.7
        y = y0 + (y1 - y0) * t
        x = rnd.uniform(-0.1, 0.95) * w
        ln = w * rnd.uniform(0.03, 0.16) * (0.4 + t)
        thick = max(1.0, h * 0.0018 * (1 + t * 2))
        a = int(rnd.uniform(30, 74))
        lake = Image.alpha_composite(lake, _wash(
            (w, h), (255, 255, 255), a, thick * 1.5,
            lambda d, x=x, y=y, ln=ln, thick=thick:
                d.rounded_rectangle([x, y, x + ln, y + thick],
                                    radius=thick, fill=255)))
    return lake


def _blossom_mass(w: int, h: int, cx: float, cy: float, rx: float, ry: float,
                  seed: int, density: int = 170,
                  colour=C_BLOSSOM) -> Image.Image:
    """一丛樱花：许多小圆点聚成云，再整体柔化 —— 远看是"淡粉云霞"。
        English:
    A cluster of cherry blossoms: many small dots gathered into a cloud, then softened overall —
    from afar it reads as "pale pink haze".
    """
    rnd = random.Random(seed)
    mask = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(mask)
    for _ in range(density):
        a = rnd.uniform(0, math.tau)
        r = rnd.random() ** 0.55
        x = cx * w + math.cos(a) * rx * w * r
        y = cy * h + math.sin(a) * ry * h * r
        rr = rnd.uniform(0.005, 0.016) * h * (1.15 - r * 0.5)
        d.ellipse([x - rr, y - rr * 0.86, x + rr, y + rr * 0.86], fill=255)
    blur = h * 0.0075
    sm = mask.filter(ImageFilter.GaussianBlur(blur))

    layer = Image.new('RGBA', (w, h), colour + (0,))
    layer.putalpha(sm.point(lambda v: int(v * 0.92)))
    # 花团里更深的粉：不然整团糊成一片白
    # [EN] Deeper pink within flower clusters: otherwise the whole cluster blurs into a patch of white
    deep = Image.new('RGBA', (w, h), C_BLOSSOM_DEEP + (0,))
    deep.putalpha(_wet_edge(mask, blur * 0.7, blur * 2.8, 0.55)
                  .point(lambda v: int(v * 0.60)))
    out = Image.alpha_composite(layer, deep)
    hi = Image.new('RGBA', (w, h), C_BLOSSOM_HI + (0,))
    hi.putalpha(mask.filter(ImageFilter.GaussianBlur(blur * 0.42))
                .point(lambda v: int(v * 0.34)))
    return Image.alpha_composite(out, hi)


def _branch(d: ImageDraw.ImageDraw, x: float, y: float, length: float,
            angle_deg: float, seed: int, depth: int = 3) -> None:
    """褐墨枝干（只做结构提示，不勾硬线）。
        English:
    Brown ink branches (only for structural hints, no hard lines drawn).
    """
    rnd = random.Random(seed)
    ang = math.radians(angle_deg)
    px_, py_ = x, y
    for _ in range(7):
        nx = px_ + math.cos(ang) * length / 7
        ny = py_ + math.sin(ang) * length / 7
        d.line([px_, py_, nx, ny], fill=255, width=max(1, int(length * 0.032)))
        ang += rnd.uniform(-0.30, 0.30)
        px_, py_ = nx, ny
    if depth > 0:
        for side in (-1, 1):
            _branch(d, px_, py_, length * 0.52,
                    math.degrees(ang) + side * rnd.uniform(24, 46),
                    seed + side + 11, depth - 1)


def _willow(w: int, h: int, x: float, y_top: float, length: float,
            seed: int, count: int = 15) -> Image.Image:
    """垂柳：从上方垂下的柳条 + 嫩绿叶簇。
        English:
    Weeping willow: willow strands hanging from above + fresh green leaf clusters.
    """
    rnd = random.Random(seed)

    def shape(d: ImageDraw.ImageDraw):
        for i in range(count):
            sx = x * w + rnd.uniform(-0.030, 0.030) * w
            ln = length * h * rnd.uniform(0.65, 1.15)
            py_ = y_top * h
            px_ = sx
            for j in range(12):
                ny = py_ + ln / 12
                nx = px_ + math.sin(j * 0.7 + i) * w * 0.0035
                d.line([px_, py_, nx, ny], fill=255, width=1)
                px_, py_ = nx, ny
            for _ in range(10):
                fy = py_ - ln * rnd.random()
                fr = rnd.uniform(0.004, 0.009) * h
                d.ellipse([px_ - fr, fy - fr, px_ + fr, fy + fr], fill=255)

    layer = _wash((w, h), C_WILLOW, 190, h * 0.004, shape)
    m = Image.new('L', (w, h), 0)
    shape(ImageDraw.Draw(m))
    deep = Image.new('RGBA', (w, h), C_WILLOW_DEEP + (0,))
    deep.putalpha(m.filter(ImageFilter.GaussianBlur(h * 0.003))
                  .point(lambda v: int(v * 0.50)))
    return Image.alpha_composite(layer, deep)


def _bridge(w: int, h: int, cx: float, base_y: float, span: float,
            rise: float) -> Image.Image:
    """长春桥：江南石拱桥，拱洞透水。
        English:
    Changchun Bridge: a Jiangnan stone arch bridge, with the arch opening letting water through.
    """
    def shape(d: ImageDraw.ImageDraw):
        x0, x1 = (cx - span / 2) * w, (cx + span / 2) * w
        y = base_y * h
        ry_ = rise * h
        rx_ = span * 0.30 * w
        top = []
        n = 48
        for i in range(n + 1):
            a = math.pi * i / n
            top.append((cx * w - (span / 2) * w * math.cos(a),
                        y - ry_ * math.sin(a) * 0.55))
        d.polygon(top + [(x1, y + ry_ * 0.95), (x0, y + ry_ * 0.95)], fill=255)
        d.ellipse([cx * w - rx_, y - ry_ * 0.95, cx * w + rx_, y + ry_ * 1.05],
                  fill=0)
        d.rectangle([x0, y - ry_ * 0.62, x1, y - ry_ * 0.50], fill=255)

    layer = _wash((w, h), C_STONE, 168, h * 0.003, shape)
    m = Image.new('L', (w, h), 0)
    shape(ImageDraw.Draw(m))
    edge = Image.new('RGBA', (w, h), (118, 124, 122, 0))
    edge.putalpha(_wet_edge(m, h * 0.002, h * 0.006, 0.5)
                  .point(lambda v: int(v * 0.40)))
    return Image.alpha_composite(layer, edge)


def _sails(w: int, h: int, boats: list[tuple[float, float, float]]) -> Image.Image:
    """太湖帆影：白帆 + 极简船身，越远越小越淡。
        English:
    Taihu sail silhouettes: white sails + minimal hulls, smaller and fainter with distance.
    """
    def shape(d: ImageDraw.ImageDraw):
        for (bx, by, sc) in boats:
            x, y = bx * w, by * h
            sw = 0.020 * w * sc
            sh = 0.055 * h * sc
            d.polygon([(x - sw * 0.15, y - sh), (x + sw * 0.75, y - sh * 0.18),
                       (x + sw * 0.72, y + sh * 0.02),
                       (x - sw * 0.15, y + sh * 0.02)], fill=255)
            d.polygon([(x - sw * 0.28, y - sh * 0.86),
                       (x - sw * 0.95, y - sh * 0.05),
                       (x - sw * 0.28, y + sh * 0.02)], fill=255)
            d.polygon([(x - sw * 1.15, y + sh * 0.04),
                       (x + sw * 1.05, y + sh * 0.04),
                       (x + sw * 0.80, y + sh * 0.18),
                       (x - sw * 0.90, y + sh * 0.18)], fill=255)

    layer = _wash((w, h), C_SAIL, 236, h * 0.0018, shape)
    ring = Image.new('L', (w, h), 0)
    shape(ImageDraw.Draw(ring))
    edge = Image.new('RGBA', (w, h), (140, 152, 162, 0))
    edge.putalpha(_wet_edge(ring, h * 0.0014, h * 0.005, 0.5)
                  .point(lambda v: int(v * 0.36)))
    return Image.alpha_composite(layer, edge)


def _petals(w: int, h: int, seed: int = 99, n: int = 46) -> Image.Image:
    """飘落的花瓣：极小的粉点，给画面一点动感。
        English:
    Falling petals: tiny pink dots, adding a bit of motion to the scene.
    """
    rnd = random.Random(seed)

    def shape(d: ImageDraw.ImageDraw):
        for _ in range(n):
            x = rnd.uniform(0.42, 1.02) * w
            y = rnd.uniform(0.10, 0.86) * h
            r = rnd.uniform(0.0016, 0.0034) * h
            d.ellipse([x - r, y - r * 0.62, x + r, y + r * 0.62], fill=255)

    layer = _wash((w, h), C_BLOSSOM_DEEP, 150, h * 0.0012, shape)
    return layer


# ══════════════════════════════════════════════
#  总装
# [EN] Assembly
# ══════════════════════════════════════════════
def paint_yuantouzhu(width: int = 3840, height: int = 2160,
                     seed: int = 20261005) -> Image.Image:
    """画一张「太湖鼋头渚 · 春季淡彩水彩」（16:9）。

    构图（按界面需求定）：**右侧**是鼋头渚半岛 —— 崖岸上成片樱花与垂柳；
    **左中**是开阔湖面、帆影与远山；**下方**是长春桥横跨湖湾；
    **画面正中刻意留空**（开始界面标题在那儿）。
    
        English:
    Paint a "Taihu Yuantouzhu · Spring pale-color watercolor" (16:9).
        Composition (per UI requirements): **right side** is the Yuantouzhu peninsula — cliffs lined with cherry blossoms and weeping willows;
        **center-left** is the open lake, sail silhouettes, and distant mountains; **bottom** is Changchun Bridge spanning the lake bay;
        **the exact center of the image is deliberately left empty** (where the start-screen title goes).
    """
    # 先在 1920×1080 上画 —— 水彩本来就是软的，放大不会糊，还快一倍
    # [EN] First draw at 1920×1080 — watercolor is inherently soft, upscaling won't blur it, and it's twice
    # [EN] as fast
    w, h = 1920, 1080
    random.seed(seed)

    paper = _make_paper(w, h).convert('RGB')
    sky = _sky(w, h, HORIZON)
    img = Image.blend(paper, sky, 0.86).convert('RGBA')

    # 远山（太湖仙岛 / 鹿顶山）—— 画在水之前，下半会被水盖住
    # [EN] Distant mountains (Taihu Immortal Island / Luding Mountain) — draw before the water, lower
    # [EN] halves will be covered by water
    img = Image.alpha_composite(img, _hilI(w, h, HORIZON - 0.010, 0.019, 0.50,
                                           C_HILL_FAR, 120, h * 0.006, 3,
                                           x0=0.01, x1=0.60))
    img = Image.alpha_composite(img, _hilI(w, h, HORIZON - 0.002, 0.015, 0.36,
                                           C_HILL_MID, 150, h * 0.005, 5,
                                           x0=0.12, x1=0.74))

    # 湖面
    # [EN] Lake surface
    img = Image.alpha_composite(img, _lake(w, h, HORIZON, LAKE_BOTTOM))

    # 右侧：鼋头渚半岛（**有下沿的陆地**，不是一直填到底的山）
    # [EN] Right side: Yuantouzhu Peninsula (**land with a lower edge**, not a mountain filled all the way
    # [EN] down)
    img = Image.alpha_composite(img, _landmass(
        w, h, 0.640, 1.06, HORIZON - 0.052, 0.026, 0.26, HORIZON,
        C_SHORE, 170, h * 0.007, 9))
    img = Image.alpha_composite(img, _landmass(
        w, h, 0.780, 1.06, HORIZON - 0.012, 0.020, 0.20, HORIZON,
        C_SHORE_NEAR, 190, h * 0.005, 15))

    # 帆影（湖面偏左，别压标题）
    # [EN] Sail shadows (lake surface toward the left, don't cover the title)
    img = Image.alpha_composite(img, _sails(w, h, [
        (0.132, 0.600, 0.60), (0.238, 0.642, 0.76), (0.070, 0.660, 0.50),
        (0.372, 0.618, 0.44),
    ]))

    # 长春桥（左下方，横跨湖湾）
    # [EN] Changchun Bridge (lower left, spanning the lake bay)
    img = Image.alpha_composite(img, _bridge(w, h, 0.220, 0.742, 0.30, 0.070))

    # 樱花：右半岛成片 + 上缘斜探进来两簇（框住中间的标题）
    # [EN] Cherry blossoms: right peninsula in patches + two clusters slanting in from the upper edge
    # [EN] (framing the central title)
    img = Image.alpha_composite(img, _blossom_mass(
        w, h, 0.848, 0.352, 0.180, 0.140, 31, 210))
    img = Image.alpha_composite(img, _blossom_mass(
        w, h, 0.968, 0.548, 0.120, 0.170, 37, 160))
    img = Image.alpha_composite(img, _blossom_mass(
        w, h, 0.098, 0.062, 0.170, 0.075, 41, 180))
    img = Image.alpha_composite(img, _blossom_mass(
        w, h, 0.335, 0.038, 0.120, 0.055, 43, 130))

    # 枝干（在花后面，只作结构）
    # [EN] Branches (behind the flowers, structural only)
    def trunk_shape(d: ImageDraw.ImageDraw):
        _branch(d, w * 0.99, h * 0.30, w * 0.30, 168, 61)
        _branch(d, w * 0.19, h * 0.015, w * 0.23, 28, 67)
    trunk = Image.new('RGBA', (w, h), C_TRUNK + (0,))
    trunk.putalpha(_wash((w, h), C_TRUNK, 110, h * 0.0022,
                         trunk_shape).getchannel('A'))
    img = Image.alpha_composite(img, trunk)

    # 垂柳（半岛前缘 + 左下角各一丛）
    # [EN] Weeping willow (one clump at the peninsula front edge + one at the lower-left corner)
    img = Image.alpha_composite(img, _willow(w, h, 0.905, 0.430, 0.28, 71))
    img = Image.alpha_composite(img, _willow(w, h, 0.045, 0.280, 0.24, 73, 12))

    # 飘落的花瓣
    # [EN] Falling petals
    img = Image.alpha_composite(img, _petals(w, h))

    # ── 水彩收尾 ──
    # 1) 湿气：地平线一带再糊一层极淡的白，远景更"远"
    # [EN] ── Watercolor finishing ──
    # [EN] 1) Moisture: wash another extremely light layer of white around the horizon, distant scenery
    # [EN] feels more "distant"
    img = Image.alpha_composite(img, _wash(
        (w, h), (255, 255, 255), 70, h * 0.028,
        lambda d: d.rectangle([-10, HORIZON * h - h * 0.070,
                               w + 10, HORIZON * h + h * 0.070], fill=255)))

    out = img.convert('RGB')

    # 2) 淡彩化：**轻微**往纸色退（第一版退 0.30 直接退成白纸）
    # [EN] 2) Light-color treatment: **slightly** recede toward paper color (first version receded 0.30 and
    # [EN] went straight to white paper)
    out = Image.blend(out, Image.new('RGB', (w, h), (250, 246, 236)), 0.16)
    out = ImageEnhance.Contrast(out).enhance(0.98)
    out = ImageEnhance.Color(out).enhance(1.24)

    # 3) 放大到目标分辨率（先放大再加纸纹 —— 纸纹才够细）
    # [EN] 3) Upscale to target resolution (upscale first, then add paper texture — only then is the paper
    # [EN] texture fine enough)
    if (width, height) != (w, h):
        out = out.resize((width, height), Image.Resampling.LANCZOS)

    # 4) 纸纹：叠一层低对比噪点，整张图就有"纸"的质感
    # [EN] 4) Paper texture: overlay a layer of low-contrast noise, and the whole image has a "paper" feel
    grain = _paper_grain((width, height), seed=17, strength=13)
    out = Image.composite(Image.new('RGB', (width, height), (255, 255, 255)),
                          out, grain.point(lambda v: max(0, min(255, v - 118))))

    # 5) 极轻的柔化，抹掉残余硬边；再压一点点对比让整体"退远"
    # [EN] 5) Very light softening, erase remaining hard edges; then reduce contrast a bit to make the
    # [EN] whole thing "recede"
    out = out.filter(ImageFilter.GaussianBlur(max(0.4, width / 5400)))
    out = ImageEnhance.Contrast(out).enhance(0.96)
    return ImageEnhance.Brightness(out).enhance(1.01)


def build(out_dir, width: int = 3840, height: int = 2160,
          progress=None) -> dict:
    """出母版 + 柔化版（与 `save_backgrounds()` 同名同规格）。
        English:
    Produce a master version + a softened version (same name and spec as `save_backgrounds()`).
    """
    from pathlib import Path
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(f'本地绘制淡彩水彩母稿（{width}×{height}）…')
    master = paint_yuantouzhu(width, height)
    p1 = out / 'title_bg.webp'
    master.save(p1, 'WEBP', quality=92, method=6)
    if progress:
        progress('柔化版（运行界面用）…')
    p2 = out / 'title_bg_soft.webp'
    make_soft(master).save(p2, 'WEBP', quality=90, method=6)
    return {'master': p1, 'soft': p2}


if __name__ == '__main__':
    from pathlib import Path
    app = Path(__file__).resolve().parent.parent
    res = build(app / 'assets' / 'images', progress=print)
    for k, v in res.items():
        print(f'  {k}: {v}  ({v.stat().st_size / 1024:.0f} KB)')
