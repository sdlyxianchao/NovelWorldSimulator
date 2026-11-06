# -*- coding: utf-8 -*-
"""对话插图 · 场景画（PNG 矢量风）。

为什么新写一个
--------------
原来对话里的图只有两种来源：
  · `background.generate_scene_background()` —— 把**同一幅**江南全景缩到
    1200×600 再淡化。所有场景长得一模一样，而且又小又淡，看着就是
    "随便贴了张背景"（用户："Png矢量图再好看一些，现在的太丑了，画的太简单了"）。
  · 人物头像 `portrait.generate_portrait()` —— 圆底 + 几个椭圆。

这个模块按 **地点 / 天气 / 时段** 真正画一张场景：
    ┌ 天空（按时段换色：晨青 / 昼白 / 暮橙 / 夜深蓝）
    ├ 远山 2~3 层（越远越淡、越模糊 —— 空气透视）
    ├ 中景：水面 / 屋群 / 石桥 / 乌篷船（按地点关键词挑）
    ├ 近景：柳 / 桃枝 / 竹（垂到画面里，撑出层次）
    └ 天气：雨丝 / 雪点 / 雾 + 纸纹 + 暗角
外加 1~3 个**人物剪影**（这一幕有人在场，画面才不空）。

笔法与调色直接复用 `image_gen/background.py` 的原语与常量，
所以对话插图跟界面背景是**同一套墨色**，不会串味。

English:
Dialogue illustration · scene illustration (PNG vector style).
Why write a new one
--------------
Originally images in dialogue had only two sources:
  · `background.generate_scene_background()` —— scales the **same** Jiangnan panorama to
    1200×600 and fades it. All scenes look identical, and are small and faint, it looks like
    "a background pasted at random" (user: "make the PNG vector art nicer, the current one is too ugly, drawn too simply").
  · Character portrait `portrait.generate_portrait()` —— a circular base + a few ellipses.
This module actually draws a scene based on **location / weather / time-of-day**:
    ┌ sky (color shifts by time-of-day: dawn cyan / day white / dusk orange / night deep blue)
    ├ distant mountains 2~3 layers (farther is paler and blurrier —— aerial perspective)
    ├ midground: water surface / house cluster / stone bridge / wupeng boat (chosen by location keyword)
    ├ foreground: willow / peach branch / bamboo (drooping into frame, propping up layering)
    └ weather: rain streaks / snow dots / fog + paper texture + vignette
Plus 1~3 **human silhouettes** (there are people present in this scene, so it doesn't feel
empty).
Brushwork and palette directly reuse the primitives and constants of `image_gen/background.py`,
so the dialogue illustration and the UI background share **the same ink tones**, no flavor
clash.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from image_gen.background import (
    BRANCH, HILL_FAR, HILL_FRONT, HILL_MID, HILL_NEAR, INK, INK_DEEP,
    LANTERN, PAPER, PAPER_WALL, ROOF_RIDGE, ROOF_TILE, SKY_LOW, SKY_MID,
    SKY_TOP, WATER, WATER_DEEP, WATER_LIT, WILLOW, WILLOW_LIT,
    _add_rain, _add_vignette, _arch_bridge, _birds, _hill_layer, _house_row,
    _lantern, _make_paper, _peach_branch, _steps, _tree, _willow, _wu_boat,
)

W, H = 960, 540          # 16:9，卡片里放到 ~190px 宽也看得清
HORIZON = 0.575          # 地平线位置（画面高度比例）
# [EN] 16:9, still legible when placed in a card at ~190px wide
# [EN] Horizon position (as a ratio of image height)

# ── 时段配色（十二时辰粗分成四段）──
# [EN] ── Time-of-day palette (twelve shichen roughly split into four bands) ──
TIME_SKY = {
    'dawn':  ((150, 176, 208), (236, 214, 214), (252, 244, 226)),   # 卯辰：青紫→暖白
    'day':   ((SKY_TOP), (SKY_MID), (SKY_LOW)),                     # 巳午未：天青→暖白
    'dusk':  ((226, 168, 132), (240, 196, 160), (250, 236, 210)),   # 申酉戌：橙金
    'night': ((36, 52, 84), (58, 74, 104), (96, 108, 128)),         # 亥子丑寅：深青蓝
    # [EN] 卯辰: cyan-purple → warm white
    # [EN] 巳午未: sky cyan → warm white
    # [EN] 申酉戌: orange gold
}
TIME_TINT = {'dawn': 0.10, 'day': 0.0, 'dusk': 0.16, 'night': 0.34}  # 压暗程度
# [EN] Darkening amount

# ── 地点关键词 → 画面要素 ──
# [EN] ── Location keywords → scene elements ──
_KEY_ELEMS = (
    (('室内', '内', '堂', '房', '屋', '室', '厢', '厅', '斋', '铺', '店', '阁',
      '楼', '榭', '廊'), 'indoor'),
    (('桥', '渡', '码头', '津', '埠'), 'bridge'),
    (('江', '河', '湖', '溪', '水', '塘', '池', '岸', '浦', '汊'), 'water'),
    (('街', '市', '巷', '集', '坊', '门', '城'), 'street'),
    (('山', '岭', '峰', '崖', '林', '坡', '坞'), 'hill'),
    (('院', '庭', '园', '花', '圃'), 'yard'),
    (('船', '舟', '舫', '篷'), 'boat'),
)
_WEATHER = ('雨', '雪', '雾', '风', '晴', '阴')


def time_segment(time_label: str) -> str:
    """把「戌时 19:30」这类时段串粗分成 dawn/day/dusk/night。
        English:
    Roughly splits a time-of-day string like "戌时 19:30" into dawn/day/dusk/night.
    """
    t = str(time_label or '')
    night = ('子', '丑', '寅', '亥')
    dawn = ('卯', '辰')
    dusk = ('申', '酉', '戌')
    for ch in t:
        if ch in night:
            return 'night'
        if ch in dawn:
            return 'dawn'
        if ch in dusk:
            return 'dusk'
    if '午' in t or '巳' in t or '未' in t:
        return 'day'
    # 抓得到 "19:30" 就按钟点判（比时辰更准）
    # [EN] If "19:30" can be captured, judge by clock hour (more accurate than shichen)
    for token in t.replace('：', ':').split():
        if ':' in token:
            try:
                hour = int(token.split(':')[0])
            except ValueError:
                continue
            if hour >= 19 or hour < 5:
                return 'night'
            if hour < 9:
                return 'dawn'
            if hour >= 16:
                return 'dusk'
            return 'day'
    return 'day'


def elements_for(place: str, weather: str = '', props=()) -> dict:
    """按地点/天气/**道具**挑要素（同类关键词取第一个命中的）。

    ★ `props`（2026-10-07 加）：剧组里**道具**那一职位的产出 ——
      这一场有哪些具体物件。它们也参与关键词匹配，于是
      "这一场有一盏油灯、一口接水缸"和"这一场什么都没有"画出来**不一样**。

    ⚠ 老实说清这一档能做到什么、做不到什么（别把它说成"道具画出来了"）：
      · **做得到**：道具名里的河、船、灯、院、铺……会点亮对应的画面要素
        （同一张关键词表，见 `_KEY_ELEMS`）—— 这是本地画法能给的**真实**影响。
      · **做不到**：把"接水缸""铜钱匣"这种具体器物逐件画出来。
        本地画法是**要素拼装**，不是通用渲染；要画具体器物得走文生图
        （`SCRIPT_IMAGES=ai`），那条路上道具是**直接进提示词**的。
      所以这里不假装：认不出的道具名就是没有影响，而不是随便画个方块充数。
    
        English:
    Pick elements by location/weather/**prop** (for same-category keywords, take the first hit).
        ★ `props` (added 2026-10-07): the output of the **props** role in the crew ——
          which specific objects are in this scene. They also participate in keyword matching, so
          "this scene has an oil lamp and a water vat" and "this scene has nothing" are drawn **differently**.
        ⚠ Be honest about what this tier can and cannot do (don't describe it as "the props are drawn"):
          · **Can do**: rivers, boats, lamps, courtyards, shops... in prop names will light up the corresponding visual elements
            (same keyword table, see `_KEY_ELEMS`) —— this is the **real** effect the local drawing method can give.
          · **Cannot do**: draw specific objects like "water vat" or "copper coin box" one by one.
            The local drawing method is **element assembly**, not general-purpose rendering; to draw specific objects you must use text-to-image
            (`SCRIPT_IMAGES=ai`), on that path props **go directly into the prompt**.
          So no pretending here: an unrecognized prop name simply has no effect, rather than drawing a random square to fill the gap.
    """
    p, w = str(place or ''), str(weather or '')
    # 道具名拼进同一个匹配串：它们本来就是"这一场的东西"
    # [EN] Prop names are concatenated into the same match string: they are inherently "the things of this
    # [EN] scene"
    extra = '、'.join(str(x) for x in (props or []) if str(x).strip())
    blob = f'{p}、{extra}' if extra else p
    elems = {'indoor': False, 'bridge': False, 'water': False, 'street': False,
             'hill': False, 'yard': False, 'boat': False, 'weather': ''}
    for keys, name in _KEY_ELEMS:
        if any(k in blob for k in keys):
            elems[name] = True
    for k in _WEATHER:
        if k in w:
            elems['weather'] = k
            break
    # 有桥/渡口通常也有水；室内不画山水
    # [EN] A bridge/ferry crossing usually implies water too; interiors don't draw mountains and water
    if elems['bridge'] or elems['boat']:
        elems['water'] = True
    if elems['indoor']:
        for k in ('water', 'hill', 'street', 'bridge', 'boat'):
            elems[k] = False
    if not any(elems[k] for k in ('water', 'hill', 'street', 'bridge', 'yard')):
        elems['yard'] = True            # 兜底：给点树和院墙，别空着
        # [EN] Fallback: give some trees and a courtyard wall, don't leave it empty
    return elems


# ══════════════════════════════════════════════════════════════
#  室内（堂/房/斋……）
# [EN] Interior (hall/room/study...)
# ══════════════════════════════════════════════════════════════
def _indoor(d: ImageDraw.ImageDraw, w: int, h: int, rng: random.Random,
            *, night: bool) -> None:
    """一间屋子：木板地 + 后墙 + 窗棂 + 灯笼 + 桌案 + 屏风。

    室内不画天空，所以这一步是**整幅重铺**，在天空/山之后调用。
    
        English:
    A room: wooden floor + back wall + window lattice + lantern + desk + screen.
        Indoors we don't draw sky, so this step is a **full repaint**, called after sky/mountains.
    """
    floor_y = int(h * 0.66)
    wall = (238, 230, 210) if not night else (96, 92, 86)

    # 后墙 + 木地板
    # [EN] Back wall + wooden floor
    d.rectangle([0, 0, w, floor_y], fill=wall)
    d.rectangle([0, floor_y, w, h], fill=tuple(int(c * 0.86) for c in wall))
    for i in range(0, w, 46):                      # 地板缝
    # [EN] Floor seams
        d.line([(i, floor_y), (i - 20, h)], fill=(198, 178, 146), width=1)
    d.line([(0, floor_y), (w, floor_y)], fill=(178, 158, 128), width=2)

    # 窗（两扇）+ 窗棂 + 窗外天光
    # [EN] Windows (two) + window lattice + daylight outside the window
    win_w, win_h = int(w * 0.20), int(h * 0.30)
    for cx in (int(w * 0.30), int(w * 0.70)):
        x0, y0 = cx - win_w // 2, int(h * 0.20)
        sky = TIME_SKY['night' if night else 'day']
        d.rectangle([x0, y0, x0 + win_w, y0 + win_h], fill=sky[0])
        d.rectangle([x0, y0, x0 + win_w, y0 + win_h], outline=BRANCH, width=3)
        for k in (1, 2, 3):                        # 竖棂
        # [EN] Vertical lattice
            gx = x0 + win_w * k // 4
            d.line([(gx, y0), (gx, y0 + win_h)], fill=BRANCH, width=2)
        for k in (1, 2):                           # 横棂
        # [EN] Horizontal lattice
            gy = y0 + win_h * k // 3
            d.line([(x0, gy), (x0 + win_w, gy)], fill=BRANCH, width=2)
        # 窗台木框
        # [EN] Window sill wooden frame
        d.rectangle([x0 - 4, y0 + win_h, x0 + win_w + 4, y0 + win_h + 7],
                    fill=(150, 116, 84))

    # 灯笼（吊在梁上，夜里更亮）
    # [EN] Lantern (hung from the beam, brighter at night)
    _lantern(d, w * 0.5, h * 0.10, 1.15, alpha=235 if night else 205)
    for x in (w * 0.14, w * 0.86):
        _lantern(d, x, h * 0.12, 0.85, alpha=210 if night else 180)

    # 桌案 + 桌上的册子与笔筒
    # [EN] Desk + booklet and brush holder on the desk
    tx0, tx1 = int(w * 0.30), int(w * 0.70)
    ty = int(h * 0.70)
    d.rectangle([tx0, ty, tx1, ty + 10], fill=(146, 108, 74))
    d.rectangle([tx0 + 8, ty + 10, tx0 + 18, h], fill=(126, 92, 62))
    d.rectangle([tx1 - 18, ty + 10, tx1 - 8, h], fill=(126, 92, 62))
    d.rectangle([tx0 + 40, ty - 12, tx0 + 118, ty], fill=PAPER_WALL)   # 摊开的册子
    # [EN] Open booklet
    d.line([(tx0 + 79, ty - 12), (tx0 + 79, ty)], fill=(170, 150, 120), width=1)
    d.rectangle([tx1 - 66, ty - 26, tx1 - 44, ty], fill=(120, 88, 60))  # 笔筒
    # [EN] Brush holder
    for k in range(3):
        d.line([(tx1 - 62 + k * 7, ty - 26), (tx1 - 58 + k * 6, ty - 40)],
               fill=INK, width=2)

    # 屏风（右侧一角，撑纵深）
    # [EN] Screen (right corner, to prop up depth)
    sx = int(w * 0.86)
    d.polygon([(sx, int(h * 0.34)), (w, int(h * 0.40)),
               (w, h), (sx, int(h * 0.72))], fill=(226, 216, 196))
    for k in range(1, 4):
        y = int(h * (0.34 + 0.095 * k))
        d.line([(sx, y), (w, y + int(h * 0.016))], fill=(196, 180, 152), width=1)


# ══════════════════════════════════════════════════════════════
#  人物剪影（"这一幕有人"）
# [EN] Human silhouette ("there are people in this scene")
# ══════════════════════════════════════════════════════════════
def _figure(d: ImageDraw.ImageDraw, x: float, ground_y: float, hgt: float,
            *, color=INK, flip: bool = False) -> None:
    """一个简笔立姿人影：头 + 肩 + 身 + 腿（两三笔，够认出"是人"）。
        English:
    A simple standing figure: head + shoulders + body + legs (two or three strokes, enough to
    recognize "it's a person").
    """
    head_r = hgt * 0.13
    d.ellipse([x - head_r, ground_y - hgt, x + head_r, ground_y - hgt + head_r * 2],
              fill=color)
    body_top = ground_y - hgt + head_r * 2
    shoulder = hgt * 0.20
    d.polygon([(x - shoulder, body_top + hgt * 0.06),
               (x + shoulder, body_top + hgt * 0.06),
               (x + shoulder * 0.72, ground_y - hgt * 0.32),
               (x - shoulder * 0.72, ground_y - hgt * 0.32)], fill=color)
    # 袖
    # [EN] Sleeve
    arm = hgt * 0.30
    d.line([(x - shoulder * 0.9, body_top + hgt * 0.12),
            (x - shoulder * 0.9 - (arm * 0.5 if flip else arm), 
             body_top + hgt * 0.12 + arm * 0.7)], fill=color, width=max(2, int(hgt * 0.05)))
    d.line([(x + shoulder * 0.9, body_top + hgt * 0.12),
            (x + shoulder * 0.9 + (arm if flip else arm * 0.5),
             body_top + hgt * 0.12 + arm * 0.7)], fill=color, width=max(2, int(hgt * 0.05)))
    # 腿（长衫下摆简化成梯形）
    # [EN] Legs (long robe hem simplified into a trapezoid)
    d.polygon([(x - shoulder * 0.8, ground_y - hgt * 0.34),
               (x + shoulder * 0.8, ground_y - hgt * 0.34),
               (x + shoulder * 0.6, ground_y), (x - shoulder * 0.6, ground_y)],
              fill=color)


# ══════════════════════════════════════════════════════════════
#  场景画
# [EN] Scene illustration
# ══════════════════════════════════════════════════════════════
def generate_scene(place: str, *, weather: str = '', time_label: str = '',
                   cast: int = 0, width: int = W, height: int = H,
                   seed: str = '', props=()) -> Image.Image:
    """画一张对话场景图（返回 RGB 图，调用方自己存盘）。

    `props` = 这一场的道具名（剧组里「道具」的产出）。它们参与两件事：
      · 要素匹配（见 `elements_for`）—— 河/船/灯/院 这些词会真的改变画面构成；
      · 随机种子 —— 换一批道具就是另一张图，同一天重跑仍然一样（可复现）。
    
        English:
    Draw a dialogue scene image (returns an RGB image, caller saves it themselves).
        `props` = the prop names for this scene (the output of "props" in the crew). They participate in two things:
          · element matching (see `elements_for`) —— words like river/boat/lamp/courtyard will really change the scene composition;
          · random seed —— a different set of props means another image, and rerunning on the same day still gives the same result (reproducible).
    """
    prop_key = '、'.join(str(x) for x in (props or []) if str(x).strip())
    rng = random.Random(
        abs(hash(f'{place}|{weather}|{time_label}|{seed}|{prop_key}')) % 0xFFFFFF)
    seg = time_segment(time_label)
    elems = elements_for(place, weather, props)
    night = seg == 'night'
    w, h = width, height
    horizon = int(h * HORIZON)

    # ── 底：纸纹 + 天空 ──
    # [EN] ── Base: paper texture + sky ──
    paper = _make_paper(w, h, seed=rng.randint(1, 9999)).convert('RGB')
    if elems['indoor']:
        img = paper.convert('RGBA')
        layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        _indoor(d, w, h, rng, night=night)
        img = Image.alpha_composite(img, layer).convert('RGB')
    else:
        top, mid, low = TIME_SKY[seg]
        sky = Image.new('RGB', (w, h), low)
        ds = ImageDraw.Draw(sky)
        for y in range(horizon + 20):             # 三段竖直渐变
        # [EN] Three-stop vertical gradient
            k = y / max(1, horizon)
            if k < 0.55:
                c = tuple(int(top[i] + (mid[i] - top[i]) * (k / 0.55)) for i in range(3))
            else:
                c = tuple(int(mid[i] + (low[i] - mid[i]) * ((k - 0.55) / 0.45))
                          for i in range(3))
            ds.line([(0, y), (w, y)], fill=c)
        img = Image.blend(paper, sky, 0.88).convert('RGBA')   # 天空铺底，留一点纸纹
        # [EN] Sky fills the base, leave a bit of paper texture

        layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        # ── 远山：越远越淡越模糊 ──
        # [EN] ── Distant mountains: farther is paler and blurrier ──
        # `_hill_layer(width, height, base_y, amp, wavelen, alpha, blur)`
        # —— alpha 是 0~255 的**整数**，blur 才是浮点半径（两者别写反，
        #    写反会以 "float cannot be interpreted as an integer" 报在 PIL 里）。
        # [EN] —— alpha is an **integer** from 0~255, blur is the float radius (don't swap the two,
        # [EN] swapping them reports "float cannot be interpreted as an integer" inside PIL).
        if elems['hill'] or rng.random() < 0.8:
            layers = [(HILL_FAR, 0.42, 110, 168, 2.2),
                      (HILL_MID, 0.30, 150, 200, 1.4),
                      (HILL_NEAR, 0.20, 190, 224, 0.8)]
            if rng.random() < 0.4:
                layers.append((HILL_FRONT, 0.14, 240, 236, 0.4))
            for color, base, amp, alpha, blur in layers:
                band = _hill_layer(w, h, base, amp, 320 + rng.randint(-60, 60),
                                   alpha, blur, color=color, seed=rng.randint(0, 9999))
                layer.alpha_composite(band)

        # ── 水面 / 街面 ──
        # [EN] ── Water surface / street surface ──
        if elems['water']:
            d.rectangle([0, horizon, w, h], fill=WATER)
            for k in range(26):                    # 横向水纹
            # [EN] Horizontal water ripples
                y = horizon + rng.randint(6, h - horizon - 4)
                x0 = rng.randint(0, w - 120)
                ln = rng.randint(40, 170)
                d.line([(x0, y), (x0 + ln, y)],
                       fill=WATER_LIT if rng.random() < 0.6 else WATER_DEEP,
                       width=2 if rng.random() < 0.4 else 1)
        else:
            ground = (196, 186, 160) if not night else (92, 96, 92)
            d.rectangle([0, horizon, w, h], fill=ground)
            for k in range(16):                    # 地砖/土路
            # [EN] Floor tiles/dirt road
                y = horizon + rng.randint(10, h - horizon - 6)
                d.line([(rng.randint(0, w // 2), y), (rng.randint(w // 2, w), y)],
                       fill=tuple(int(c * 0.92) for c in ground), width=1)

        # ── 中景建筑：屋群 / 桥 / 船 ──
        # 各笔法的 alpha 都是 0~255 的整数（墙 236 / 瓦 232：屋子要实一点，
        # 不然在天空上"浮"着）。别把"透明度比例"当 alpha 传进去。
        # [EN] ── Midground buildings: house clusters / bridge / boat ──
        # [EN] The alpha of each brushstroke is an integer from 0~255 (wall 236 / tile 232: houses need to be
        # [EN] more solid,
        # [EN] otherwise they "float" on the sky). Don't pass a "transparency ratio" as alpha.
        base_y = horizon + int(h * (0.02 if elems['water'] else 0.03))
        if elems['street'] or elems['yard'] or not (elems['water'] and not elems['street']):
            _house_row(d, -20, w * 0.62, base_y, 0.62, 236, 232,
                       seed=rng.randint(0, 9999))
        if elems['bridge']:
            _arch_bridge(d, w * 0.66, base_y + int(h * 0.03), int(w * 0.40),
                         int(h * 0.13))
            _steps(d, w * 0.50, base_y + int(h * 0.05), n=4)
        if elems['water'] and (elems['boat'] or rng.random() < 0.7):
            _wu_boat(d, w * rng.uniform(0.14, 0.42),
                     horizon + int(h * rng.uniform(0.16, 0.30)),
                     rng.uniform(0.55, 0.8))
        if elems['hill']:
            _tree(d, w * rng.uniform(0.06, 0.2), base_y + int(h * 0.02),
                  0.5, seed=rng.randint(0, 9999))
            _birds(d, w * rng.uniform(0.3, 0.6), h * rng.uniform(0.12, 0.2),
                   n=rng.randint(3, 6), alpha=150)

        # ── 近景：柳 / 桃枝（垂进画面，撑层次）──
        # [EN] ── Foreground: willow / peach branch (drooping into frame, propping up layering) ──
        if elems['water'] or elems['yard'] or rng.random() < 0.5:
            _willow(d, w * rng.uniform(0.02, 0.16), h * rng.uniform(0.06, 0.16),
                    h * rng.uniform(0.30, 0.46), count=12,
                    scale=rng.uniform(0.9, 1.2), alpha=190,
                    seed=rng.randint(0, 9999))
        if rng.random() < 0.45:
            _willow(d, w * rng.uniform(0.84, 0.98), h * rng.uniform(0.04, 0.12),
                    h * rng.uniform(0.24, 0.38), count=10, scale=0.9,
                    alpha=176, seed=rng.randint(0, 9999))
        if elems['yard'] or rng.random() < 0.3:      # 院内：一枝桃花探进画面
        # [EN] Inside the courtyard: a peach branch reaches into frame
            _peach_branch(d, w * rng.uniform(0.70, 0.92), h * rng.uniform(0.06, 0.14),
                          w * rng.uniform(0.22, 0.34), rng.uniform(150, 200),
                          scale=1.0, alpha=214, seed=rng.randint(0, 9999))

        # ── 人物剪影 ──
        # [EN] ── Human silhouette ──
        n_fig = max(0, min(3, int(cast or 0)))
        if n_fig:
            fy = horizon + int(h * (0.12 if elems['water'] else 0.16))
            for k in range(n_fig):
                x = w * (0.34 + 0.14 * k)
                _figure(d, x, fy + rng.randint(-4, 6),
                        h * rng.uniform(0.20, 0.26),
                        color=INK_DEEP if night else INK,
                        flip=(k == n_fig - 1))

        img = Image.alpha_composite(img, layer)

    img = img.convert('RGB')

    # ── 天气与光 ──
    # [EN] ── Weather and light ──
    if elems['weather'] == '雨':
        img = _add_rain(img, seed=rng.randint(1, 99), density=0.00022)
    elif elems['weather'] == '雪':
        d = ImageDraw.Draw(img)
        for _ in range(240):
            x, y = rng.randint(0, w), rng.randint(0, h)
            r = rng.choice((1, 1, 2))
            d.ellipse([x, y, x + r, y + r], fill=(255, 255, 255))
    elif elems['weather'] == '雾':
        img = img.filter(ImageFilter.GaussianBlur(1.1))
        fog = Image.new('RGB', (w, h), (236, 238, 236))
        img = Image.blend(img, fog, 0.18)
    # `_add_rain` 返回的是 **RGBA**，而下面的合成/混合都按 RGB 走 ——
    # 不统一就会 `ValueError: images do not match`（模式不同也算不匹配）。
    # [EN] `_add_rain` returns **RGBA**, while the compositing/blending below all work in RGB ——
    # [EN] if not unified you get `ValueError: images do not match` (different modes also count as a
    # [EN] mismatch).
    img = img.convert('RGB')

    tint = TIME_TINT[seg]
    if tint:
        sh = Image.new('RGB', (w, h), (28, 40, 68) if night else (120, 82, 56))
        img = Image.blend(img, sh, tint * 0.5)
    img = _add_vignette(img, strength=0.045)

    # 提鲜（和背景图同一套口径，画面够亮才不"灰"）
    # [EN] Brighten (same convention as the background image, only bright enough images avoid looking
    # [EN] "gray")
    img = ImageEnhance.Color(img).enhance(1.28 if not night else 1.10)
    img = ImageEnhance.Brightness(img).enhance(1.05 if not night else 1.02)
    img = ImageEnhance.Contrast(img).enhance(1.03)
    return img.filter(ImageFilter.GaussianBlur(0.25))


def save_scene(path, place: str, **kw) -> str:
    """画一张场景图并存盘，返回路径字符串。
        English:
    Draw a scene image and save it, return the path string.
    """
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    generate_scene(place, **kw).save(p)
    return str(p)
