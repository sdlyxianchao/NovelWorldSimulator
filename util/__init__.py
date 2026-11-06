# -*- coding: utf-8 -*-
"""通用小工具：JSON 兜底解析、文本处理、时间格式、文件原子写。
English:
Common utilities: JSON fallback parsing, text processing, time formatting, atomic file write.
"""
from .jsonio import extract_json, extract_json_list, safe_json_loads
from .text import (
    clip, now_str, slugify, dedent, truncate_mid, contains_any,
    similarity, strip_html_tags, hash_file,
)
from .timefmt import GameTime, format_game_clock
from .io import atomic_write_text, ensure_dir, safe_name

__all__ = [
    "extract_json", "extract_json_list", "safe_json_loads",
    "clip", "now_str", "slugify", "dedent", "truncate_mid", "contains_any",
    "similarity", "strip_html_tags", "hash_file",
    "GameTime", "format_game_clock",
    "atomic_write_text", "ensure_dir", "safe_name",
]