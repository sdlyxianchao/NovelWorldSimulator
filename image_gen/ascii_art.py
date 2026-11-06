# -*- coding: utf-8 -*-
"""对话插图 · ASCII 字符画（四种方式里最省的一种）。

定位很清楚：**省，但难看**。它不生成图片、不调模型、不占空间，
就是把这一幕的"骨架"用字符摆出来 —— 没有图片模式时的兜底，
也适合放进纯文本的导出稿里。

画面按 `scene.elements_for()` 挑要素（山 / 水 / 桥 / 屋 / 街 / 人物），
所以「渡口」和「堂内」摆出来不一样，不是一张万能图。

English:
Dialogue illustration · ASCII art (the most economical of the four methods).
Positioning is clear: **economical, but ugly**. It doesn't generate images, doesn't call models,
doesn't take up space,
it just lays out the "skeleton" of this scene using characters -- the fallback when there's no
image mode,
and also suitable for inclusion in plain-text exports.
The picture picks elements via `scene.elements_for()` (mountain / water / bridge / house /
street / person),
so "ferry crossing" and "inside the hall" look different when laid out -- it's not a
one-size-fits-all image.
"""
from __future__ import annotations

import random

from image_gen.scene import elements_for, time_segment

WIDTH = 68          # 字符宽（中栏等宽字 11px 时刚好一行放得下）
# [EN] Character width (when the middle column uses 11px monospace font, it just fits on one line)
HEIGHT = 17


def _fit(s: str, w: int, align: str = 'center') -> str:
    """把一行裁/补到固定宽度（画面对齐全靠它）。

    `align='left'` 时必须给：**带边框的行（室内）不能居中** ——
    居中会在左边加空格，把 `|` 推进去，上下边框就错开了（踩过）。
    
        English:
    Trim/pad a line to a fixed width (the whole picture's alignment depends on it).
        Must be provided when `align='left'`: **lines with borders (indoor) cannot be centered** --
        centering adds spaces on the left, pushes the `|` in, and the top and bottom borders become misaligned (been there).
    """
    if len(s) > w:
        return s[:w]
    pad = w - len(s)
    if align == 'left':
        return s + ' ' * pad
    left = pad // 2
    return ' ' * left + s + ' ' * (pad - left)


def _at(s: str, x: int, text: str, w: int) -> str:
    """把 `text` 盖到第 x 列（用于窗、灯、桌这些定点元素）。
        English:
    Overlay `text` starting at column x (used for fixed-position elements like windows, lamps,
    desks).
    """
    s = s.ljust(w)
    x = max(0, min(x, max(0, w - len(text))))
    return (s[:x] + text + s[x + len(text):])[:w]


def _hill_row(w: int, rng: random.Random, scale: float = 1.0) -> str:
    """一排远山：用 /\\ 拼波形，越高越密。
        English:
    A row of distant mountains: build waveforms with /\\, the higher the denser.
    """
    out = []
    while len(out) < w:
        peak = rng.choice(('/\\', ' /\\', '/\\/', '  /\\  ', '/\\\\'))
        if rng.random() < 0.35:
            peak = ' ' * rng.randint(1, 4)
        out.append(peak)
    return ''.join(out)[:w]


def _water_rows(w: int, rng: random.Random, n: int = 2) -> list[str]:
    rows = []
    for i in range(n):
        chars = []
        while len(chars) < w:
            chars.append(rng.choice(['~' * rng.randint(2, 5), ' ' * rng.randint(1, 3),
                                     '~' * rng.randint(1, 2)]))
        rows.append(''.join(chars)[:w])
    return rows


def _house_row(w: int, rng: random.Random, n: int = 4) -> str:
    """屋排：[##] 是屋子，中间留空当巷子。
        English:
    Row of houses: [##] is a house, the gap in between serves as an alley.
    """
    parts, total = [], 0
    while total < w:
        roof = rng.choice(('_', '^', '-'))
        house = f'{roof}[##]'
        parts.append(house)
        total += len(house)
        gap = rng.randint(0, 3)
        parts.append(' ' * gap)
        total += gap
    return ''.join(parts)[:w]


def _figure(rng: random.Random) -> str:
    """一个小人（几种姿态），让"这一幕有人在场"。
        English:
    A little person (several poses), to convey "there's someone present in this scene".
    """
    return rng.choice((' o/', ' \\o', ' o ', 'o/ ', ' /\\o'))


def generate_ascii(place: str, *, weather: str = '', time_label: str = '',
                   cast: int = 0, width: int = WIDTH,
                   seed: str = '') -> str:
    """生成 ASCII 场景画（返回多行字符串，含一行标题）。
        English:
    Generate an ASCII scene drawing (returns a multi-line string, including a title line).
    """
    rng = random.Random(abs(hash(f'{place}|{weather}|{time_label}|{seed}')) % 0xFFFFFF)
    elems = elements_for(place, weather)
    seg = time_segment(time_label)

    head = f'〔{place or "某处"}'
    if time_label:
        head += f' · {time_label}'
    if weather:
        head += f' · {weather}'
    head += '〕'

    lines: list[str] = []
    # 天：夜里用 '  sparse，白天用 ' . '
    # [EN] Sky: use '  sparse at night, use ' . ' during the day
    if elems['weather'] == '雨':
        lines.append(_fit(' ' + ' '.join(rng.choice(('.', "'", '.', ','))
                                         for _ in range(width // 3)), width))
        lines.append(_fit(' '.join(rng.choice(('. ', '.  ', "'", ' . '))
                                   for _ in range(width // 3)), width))
    else:
        lines.append(_fit(' '.join(rng.choice(('`', "'", '.', ' '))
                                   for _ in range(width // 3)), width))

    if elems['indoor']:
        # 室内：**带边框的行必须左对齐**（居中会把 `|` 推进去、边框错开）。
        # 窗与灯按宽度比例定点，别硬编码列号。
        # [EN] Indoor: **lines with borders must be left-aligned** (centering pushes the `|` in and misaligns
        # [EN] the borders).
        # [EN] Windows and lamps are positioned proportionally by width, don't hardcode column numbers.
        bar = '|' + '=' * (width - 2) + '|'
        blank = '|' + ' ' * (width - 2) + '|'
        floor = '|' + '_' * (width - 2) + '|'
        lines.append(bar)
        win = blank
        for k in (0.22, 0.62):
            win = _at(win, int((width - 4) * k), '[==]', width)
        lines.append(win)
        lines.append(blank)
        lamp = _at(blank, int((width - 4) * 0.4), '(o)', width)     # 灯
        # [EN] Lamp
        lamp = _at(lamp, int((width - 4) * 0.08), 'o', width)
        lines.append(lamp)
        lines.append(floor)
        desk = _at(blank, int((width - 4) * 0.30), '[==]', width)    # 桌案
        # [EN] Desk
        lines.append(desk)
    else:
        for _ in range(rng.randint(1, 2)):
            lines.append(_hill_row(width, rng))
        if elems['street'] or elems['yard']:
            lines.append(_house_row(width, rng, n=rng.randint(3, 5)))
        elif elems['bridge']:
            span = width // 2
            lines.append(_fit(' ' * (width // 6) + '_' * 3 + '/' + ' ' * (span - 8)
                              + '\\' + '_' * 3, width))
        if elems['water']:
            lines.extend(_water_rows(width, rng, n=2))
            if elems['boat'] or rng.random() < 0.6:      # 一叶小舟
            # [EN] A small boat
                bx = rng.randint(4, max(5, width - 20))
                lines[-1] = _fit(lines[-1][:bx] + '(=)' + lines[-1][bx + 3:], width)
        else:
            lines.append(_fit('_' * (width - 8), width))
            lines.append(_fit(' ' + '_' * (width - 20), width))

    # 人物剪影
    # [EN] Figure silhouette
    n_fig = max(0, min(3, int(cast or 0)))
    if n_fig:
        figs = '  '.join(_figure(rng) for _ in range(n_fig))
        lines.append(_fit(figs, width))
    # 收尾：地面
    # [EN] Finishing: ground
    if not elems['indoor']:
        lines.append(_fit('.' * (width - 6), width))

    return head + '\n' + '\n'.join(lines[:HEIGHT])


def save_ascii(path, place: str, **kw) -> str:
    """生成并落盘（UTF-8 文本），返回路径字符串。
        English:
    Generate and write to disk (UTF-8 text), return the path string.
    """
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(generate_ascii(place, **kw), encoding='utf-8')
    return str(p)
