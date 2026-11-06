# -*- coding: utf-8 -*-
"""图片生成模块。

两条路线：
- **背景图走文生图**：原图放 `assets/images/bg/`，由 `build_from_source()` 处理成
  界面用的 `title_bg.webp`（开始界面）与 `title_bg_soft.webp`（运行界面）。
- **图标仍用 Pillow 生成**（水墨丹青风），缓存到 `assets/images/`。
- **小地图是矢量**（2026-10-06 改的）：`FT.canvas` 形状即时绘制，不再存 PNG。
  布局由 AI 读设定摆位（`map_layout.py`），画在 `minimap.py`。

`background.py` 里那套程序化绘制（烟雨江南彩墨）已退居**兜底**：
只有连文生图原图都没有时才用，避免缺图时白屏。

English:
Image generation module.
Two routes:
- **Background images use text-to-image**: original images go in `assets/images/bg/`, processed by `build_from_source()` into
  the `title_bg.webp` (start screen) and `title_bg_soft.webp` (running screen) used by the UI.
- **Icons are still generated with Pillow** (ink-wash style), cached to `assets/images/`.
- **The minimap is vector-based** (changed 2026-10-06): `FT.canvas` shapes are drawn on the fly, no longer stored as PNG.
  Layout positions are set by AI reading the settings (`map_layout.py`), drawn in `minimap.py`.
The procedural drawing set (misty Jiangnan color ink) in `background.py` has been demoted to
**fallback**:
Only used when even the text-to-image originals are missing, to avoid a white screen when images
are absent.
"""
from .background import (generate_title_background, generate_scene_background,
                         soften, to_pale, to_sketch, save_backgrounds,
                         find_ai_source, crop_to_16_9, make_master, make_soft,
                         build_from_source, MASTER_NAME, SOFT_NAME, BG_SRC_DIR)
from .icon import generate_icon, save_icons
from .portrait import generate_portrait
from .minimap import build_canvas, build_shapes, known_shapes
from .map_layout import (Layout, Place, ai_layout, load_cached,
                         normalize, places_from_settings, save_cached,
                         simple_layout)
from .ui_elements import generate_button_bg, generate_panel_bg, generate_divider

__all__ = [
    'generate_title_background',
    'generate_scene_background',
    'soften',
    'to_pale',
    'to_sketch',
    'save_backgrounds',
    'find_ai_source',
    'crop_to_16_9',
    'make_master',
    'make_soft',
    'build_from_source',
    'MASTER_NAME',
    'SOFT_NAME',
    'BG_SRC_DIR',
    'generate_icon',
    'save_icons',
    'generate_portrait',
    # 小地图（矢量）
    # [EN] Minimap (vector)
    'build_canvas', 'build_shapes', 'known_shapes',
    'Layout', 'Place', 'ai_layout', 'simple_layout', 'normalize',
    'places_from_settings', 'load_cached', 'save_cached',
    'generate_button_bg',
    'generate_panel_bg',
    'generate_divider',
]
