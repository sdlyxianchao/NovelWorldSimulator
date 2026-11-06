# -*- coding: utf-8 -*-
"""人物头像生成：宣纸墨线风（与水墨主题一致）。

⚠️ **本模块已不作为"对话里的肖像"使用**（2026-10-05 起）。

用户的原话："你画的人物肖像太难看了，人物肖像全部用文生图。"
所以对话肖像改走 `image_gen/portraits.py`（文生图 + 项目级复用 + 文字兜底），
本地画的这条链**不再接入对话**。

保留这个文件是因为：
  · `image_gen/__init__.py` 仍导出 `generate_portrait`（离线预览/美术演示还在用）；
  · 万一以后要做"没有网时的占位头像"，这里是现成的。
**接手时不要把它接回 `hook.py`** —— 那是用户明确否掉的做法。

原实现说明：
- 宣纸圆底 + 淡墨圈边
- 按性格取淡彩衣色与点缀色（低饱和，不抢画面）
- 底部纸色名签 + 墨字（使用中文字体，避免方块）

English:
Character avatar generation: Xuan paper ink-line style (consistent with the ink-wash theme).
⚠️ **This module is no longer used as the "portrait in conversation"** (as of 2026-10-05).
User's exact words: "The character portraits you draw are too ugly, use text-to-image for all
character portraits."
So conversation portraits now go through `image_gen/portraits.py` (text-to-image + project-level
reuse + text fallback),
this locally-drawn chain is **no longer wired into the conversation**.
This file is kept because:
  · `image_gen/__init__.py` still exports `generate_portrait` (offline preview / art demos still use it);
  · in case a "placeholder avatar when there's no network" is needed later, this is ready-made.
**When taking over, do not wire it back into `hook.py`** —— that is an approach the user
explicitly rejected.
Original implementation notes:
- Xuan paper round base + light ink ring border
- Pick light-color clothing and accent colors by personality (low saturation, not stealing the scene)
- Paper-color name tag at the bottom + ink text (use a Chinese font to avoid tofu boxes)
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

# ── 宣纸底色 ──
# [EN] ── Xuan paper base color ──
PAPER = '#f8f4ea'
PAPER_LINE = '#d8cfb8'
INK = '#2b2e33'
INK_SOFT = '#6b7076'

# ── 性格配色（淡彩：衣色 / 点缀色 / 发色 / 肤色）──
# [EN] ── Personality colors (light colors: clothing / accent / hair / skin) ──
PALETTES = {
    '沉稳': {'cloth': '#6b7076', 'accent': '#8a6d3b', 'hair': '#2a2c30', 'skin': '#f2dcc0'},
    '活泼': {'cloth': '#c0705a', 'accent': '#b23028', 'hair': '#3a2c22', 'skin': '#f7e0c8'},
    '冷傲': {'cloth': '#5a7a94', 'accent': '#3a6ea5', 'hair': '#1e2024', 'skin': '#f0dcc4'},
    '温柔': {'cloth': '#d4a574', 'accent': '#b08a5a', 'hair': '#4a3a2c', 'skin': '#f7e0c8'},
    '神秘': {'cloth': '#7a6a9a', 'accent': '#6a5a8a', 'hair': '#2a2434', 'skin': '#f2dcc0'},
    '豪爽': {'cloth': '#9a6a4a', 'accent': '#8a5a3a', 'hair': '#33261a', 'skin': '#eed2ae'},
    'default': {'cloth': '#6b7076', 'accent': '#8a6d3b', 'hair': '#2a2c30', 'skin': '#f2dcc0'},
}

_FONT_CANDIDATES = [
    r'C:\Windows\Fonts\simkai.ttf',
    r'C:\Windows\Fonts\simsun.ttc',
    r'C:\Windows\Fonts\simhei.ttf',
    r'C:\Windows\Fonts\msyh.ttc',
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc',
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    """中文字体（避免中文名变方块）。
        English:
    Chinese font (to avoid Chinese names turning into tofu boxes).
    """
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _pick_palette(personality: str) -> dict:
    for key, val in PALETTES.items():
        if key != 'default' and key in personality:
            return val
    return PALETTES['default']


def _radial(w: int, h: int, cx: float, cy: float, inner, outer) -> Image.Image:
    """径向渐变（椭圆），用来给头像铺"纸上一团淡彩"。
        English:
    Radial gradient (ellipse), used to lay a "blob of light color on paper" for the avatar.
    """
    img = Image.new('RGB', (w, h), outer)
    px = img.load()
    rmax = max(w, h) * 0.72 or 1
    for y in range(h):
        for x in range(w):
            d = math.hypot((x - cx) / 1.0, (y - cy) / 1.28)
            k = max(0.0, min(1.0, d / rmax))
            px[x, y] = tuple(int(inner[i] + (outer[i] - inner[i]) * k)
                             for i in range(3))
    return img


def _hex(c: str) -> tuple:
    c = c.lstrip('#')
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def generate_portrait(name: str, personality: str = '', gender: str = 'male',
                      size: int = 128) -> Image.Image:
    """生成宣纸墨线风人物头像。

    比第一版多了四件事（原来就是"圆底 + 几个椭圆"，看着太简单）：
      · 底：**径向淡彩晕染**（不是一块死白），像纸上一团化开的颜色
      · 头发：加几缕**发丝线**，不再是一个黑半球
      · 衣：领口交叠两笔 + 衣纹，看得出是一件衣服
      · 脸：眼白 + 高光、腮红
    
        English:
    Generate a Xuan paper ink-line style character avatar.
        Four things added compared to the first version (originally just "round base + a few ellipses", looked too simple):
          · Base: **radial light-color wash** (not a flat dead white), like a blob of color spreading on paper
          · Hair: add a few **hair strand lines**, no longer a single black hemisphere
          · Clothing: two overlapping collar strokes + clothing folds, so it reads as a garment
          · Face: eye white + highlight, blush
    """
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pal = _pick_palette(personality)
    accent = _hex(pal['accent'])
    cloth = _hex(pal['cloth'])

    # ── 底：径向淡彩 + 双圈描边 ──
    # [EN] ── Base: radial light color + double-ring outline ──
    inner = tuple(min(255, int(c + (255 - c) * 0.45)) for c in cloth)
    plate = _radial(size, size, size * 0.62, size * 0.34,
                    inner, (250, 246, 238)).convert('RGBA')
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    img.paste(plate, (0, 0), mask)

    bw = max(2, size // 44)
    draw.ellipse([(bw, bw), (size - bw - 1, size - bw - 1)],
                 outline=accent, width=bw)
    draw.ellipse([(bw * 2, bw * 2), (size - bw * 2 - 1, size - bw * 2 - 1)],
                 outline=tuple(min(255, c + 30) for c in accent), width=1)

    # ── 脸 ──
    # [EN] ── Face ──
    face_x, face_y = size // 2, int(size * 0.47)
    face_rx, face_ry = int(size * 0.235), int(size * 0.30)
    draw.ellipse([(face_x - face_rx, face_y - face_ry),
                  (face_x + face_rx, face_y + face_ry)], fill=pal['skin'])

    # 头发（上半圈）+ 发丝 + 发髻
    # [EN] Hair (upper half circle) + hair strands + bun
    hair = []
    for angle in range(180, 361, 8):
        rad = math.radians(angle)
        hair.append((face_x + int(face_rx * 1.26 * math.cos(rad)),
                     face_y + int(face_ry * 1.22 * math.sin(rad))))
    if hair:
        draw.polygon(hair, fill=pal['hair'])
    for k in range(5):                                  # 发丝
    # [EN] Hair strands
        rad = math.radians(196 + k * 32)
        x0 = face_x + int(face_rx * 0.35 * math.cos(rad))
        y0 = face_y - int(face_ry * 0.55)
        x1 = face_x + int(face_rx * 1.30 * math.cos(rad))
        y1 = face_y + int(face_ry * 0.30 * math.sin(rad))
        draw.line([(x0, y0), (x1, y1)],
                  fill=tuple(min(255, c + 46) for c in _hex(pal['hair'])),
                  width=max(1, size // 120))
    draw.ellipse([(face_x - int(size * 0.09), face_y - face_ry - int(size * 0.16)),
                  (face_x + int(size * 0.09), face_y - face_ry + int(size * 0.02))],
                 fill=pal['hair'])

    # ── 眉眼嘴 ──
    # [EN] ── Brows, eyes, mouth ──
    eye_y = face_y - int(face_ry * 0.22)
    eye_dx = int(face_rx * 0.48)
    for sgn in (-1, 1):
        draw.line([(face_x + sgn * eye_dx - int(size * 0.05), eye_y - int(size * 0.055)),
                   (face_x + sgn * eye_dx + int(size * 0.045), eye_y - int(size * 0.075))],
                  fill=pal['hair'], width=max(1, size // 90))
    eye_r = max(2, int(size * 0.040))
    for sgn in (-1, 1):                                 # 眼白 + 瞳 + 高光
    # [EN] Eye white + pupil + highlight
        cx = face_x + sgn * eye_dx
        draw.ellipse([(cx - eye_r, eye_y - int(eye_r * 0.72)),
                      (cx + eye_r, eye_y + int(eye_r * 0.72))], fill='#fbfaf6')
        draw.ellipse([(cx - int(eye_r * 0.55), eye_y - int(eye_r * 0.62)),
                      (cx + int(eye_r * 0.55), eye_y + int(eye_r * 0.62))], fill=INK)
        draw.ellipse([(cx - int(eye_r * 0.2), eye_y - int(eye_r * 0.45)),
                      (cx + int(eye_r * 0.25), eye_y - int(eye_r * 0.1))],
                     fill='#ffffff')
    mouth_y = face_y + int(face_ry * 0.52)
    draw.arc([(face_x - int(face_rx * 0.30), mouth_y - int(size * 0.018)),
              (face_x + int(face_rx * 0.30), mouth_y + int(size * 0.042))],
             0, 180, fill=pal['accent'], width=max(1, size // 80))
    for sgn in (-1, 1):                                 # 腮红（很淡）
    # [EN] Blush (very light)
        bx = face_x + sgn * int(face_rx * 0.62)
        draw.ellipse([(bx - int(size * 0.045), mouth_y - int(size * 0.055)),
                      (bx + int(size * 0.045), mouth_y + int(size * 0.01))],
                     fill=tuple(int(c * 0.92 + 255 * 0.08) for c in accent))

    # ── 衣领（交叠两笔 + 衣纹）──
    # [EN] ── Collar (two overlapping strokes + clothing folds) ──
    collar_y = face_y + face_ry + int(size * 0.02)
    draw.polygon([(face_x - int(face_rx * 1.05), collar_y),
                  (face_x, collar_y + int(size * 0.20)),
                  (face_x + int(face_rx * 1.05), collar_y)], fill=pal['cloth'])
    draw.line([(face_x - int(face_rx * 0.55), collar_y + int(size * 0.02)),
               (face_x, collar_y + int(size * 0.17))],
              fill=tuple(min(255, c + 34) for c in cloth), width=max(1, size // 70))
    draw.line([(face_x + int(face_rx * 0.55), collar_y + int(size * 0.02)),
               (face_x, collar_y + int(size * 0.17))],
              fill=tuple(min(255, c + 34) for c in cloth), width=max(1, size // 70))
    draw.line([(face_x, collar_y + int(size * 0.17)),
               (face_x, size - int(size * 0.17))],
              fill=tuple(int(c * 0.86) for c in cloth), width=max(1, size // 90))

    # ── 名签（纸色底 + 墨字 + 细线）──
    # [EN] ── Name tag (paper-color base + ink text + thin line) ──
    tag_h = max(16, int(size * 0.17))
    tag_y = size - tag_h
    draw.rectangle([(0, tag_y), (size, size)], fill=PAPER)
    draw.line([(0, tag_y), (size, tag_y)], fill=PAPER_LINE,
              width=max(1, size // 100))

    font = _font(max(9, int(size * 0.105)))
    bbox = draw.textbbox((0, 0), name, font=font)
    draw.text(((size - (bbox[2] - bbox[0])) // 2, tag_y + max(1, (tag_h - (bbox[3] - bbox[1])) // 2 - 1)),
              name, fill=INK, font=font)

    return img


def generate_portrait_simple(name: str, color: str = '#8a6d3b',
                             size: int = 64) -> Image.Image:
    """简单圆形头像（宣纸底 + 墨字），用于列表等小尺寸场景。
        English:
    Simple circular avatar (Xuan paper base + ink text), for small-size scenarios like lists.
    """
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([(1, 1), (size - 2, size - 2)], fill=PAPER, outline=color, width=2)

    char = name[0] if name else '?'
    font = _font(max(10, int(size * 0.48)))
    bbox = draw.textbbox((0, 0), char, font=font)
    draw.text(((size - (bbox[2] - bbox[0])) // 2,
               (size - (bbox[3] - bbox[1])) // 2 - bbox[1] // 4),
              char, fill=INK, font=font)
    return img
