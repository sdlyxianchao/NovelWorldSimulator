# -*- coding: utf-8 -*-
"""UI 元素图片生成。
English:
UI element image generation.
"""
from __future__ import annotations

from PIL import Image, ImageDraw


def generate_button_bg(
    text: str,
    width: int = 200,
    height: int = 40,
    bg_color: str = '#2a1f14',
    text_color: str = '#f0e68c',
    border_color: str = '#8b7355',
) -> Image.Image:
    """生成按钮背景图。
        English:
    Generate button background image.
    """
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角矩形背景
    # [EN] Rounded rectangle background
    draw.rounded_rectangle(
        [(0, 0), (width, height)],
        radius=5,
        fill=bg_color,
        outline=border_color,
        width=2,
    )

    return img


def generate_panel_bg(
    width: int = 300,
    height: int = 400,
    bg_color: str = '#1a1a2e',
    border_color: str = '#4a3f34',
) -> Image.Image:
    """生成面板背景图。
        English:
    Generate panel background image.
    """
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 半透明背景
    # [EN] Semi-transparent background
    draw.rectangle([(0, 0), (width, height)], fill=bg_color)

    # 边框
    # [EN] Border
    draw.rectangle([(0, 0), (width - 1, height - 1)], outline=border_color, width=2)

    # 装饰角
    # [EN] Decorative corner
    corner_size = 10
    for x, y in [(0, 0), (width - corner_size, 0), (0, height - corner_size), (width - corner_size, height - corner_size)]:
        draw.rectangle([(x, y), (x + corner_size, y + corner_size)], fill=border_color)

    return img


def generate_divider(
    width: int = 400,
    height: int = 2,
    color: str = '#4a3f34',
) -> Image.Image:
    """生成分隔线图片。
        English:
    Generate divider line image.
    """
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 中间渐变线
    # [EN] Center gradient line
    for x in range(width):
        # 中间最亮，两边渐暗
        # [EN] Brightest in the middle, fading toward both sides
        alpha = int(255 * (1 - abs(x - width // 2) / (width // 2)))
        draw.point((x, 0), fill=(*_hex_to_rgb(color), alpha))
        if height > 1:
            draw.point((x, 1), fill=(*_hex_to_rgb(color), alpha // 2))

    return img


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """将十六进制颜色转换为 RGB 元组。
        English:
    Convert hexadecimal color to RGB tuple.
    """
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))