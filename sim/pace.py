# -*- coding: utf-8 -*-
"""演出节奏的档位表：**详细程度 →（一拍故事秒, 时间倍率）**。

★★★ 2026-10-30（用户：「在天机 运行 时间系统里 事件倍率上面加一个详细程度吧
   包含很详细 详细 中间 简略 带过 选了之后对应的时间倍率和一拍（故事秒）
   跟着变化」）。

为什么要有这张表：时间系统原来只有两个裸数字（`TIME_RATIO` / `BEAT_SECONDS`），
  而"该填多少"没有任何参照 —— 用户能做的只有反复试。档位把这两个数**绑成一组**，
  选一个词就同时定下来。

⚠ **这里只放数字，不放文案**：档位名与解释是界面的事（要过 `t()` 翻译），
  放在 `gui/app_flet.py` 那一边；本模块只回答"这一档对应哪两个数"。
⚠ 档位是**闭集**（与 `ingest.progress.WEIGHTS` 同一个理由：自由文本没法算）。
  `自定义` 不是档位 —— 它是"下面两个数跟任何一档都对不上"时的**显示值**，
  用户选它不会改任何数字。

每档的选取口径（每拍真实秒 = 一拍 ÷ 倍率）：
  · 越细 → 一拍推的故事越少、每拍等得越久（看得慢，一句一句看）；
  · 越粗 → 一拍推的故事越多、每拍等得越短（像交代过去）。

| 档 | 一拍(故事秒) | 时间倍率 | 每拍真实秒 |
|---|---|---|---|
| 很详细 |   60 | 1  |  60 |
| 详细   |  120 | 1  | 120 |
| 中间   |  240 | 2  | 120 |
| 简略   |  600 | 6  | 100 |
| 带过   | 1800 | 20 |  90 |

English:
The pacing ladder: **detail level -> (story seconds per beat, time ratio)**.
Why a table: the time system used to expose two bare numbers with no reference for
"what should I type". A level binds them into one group, so one word decides both.
⚠ Numbers only, no wording (the UI builds the sentences through `t()`); the ladder is a
closed set. `自定义` is not a level -- it is the display value when the two numbers match
no preset, and picking it changes nothing.
"""
from __future__ import annotations

#: 档位，**从最细到最粗**（顺序＝界面里的顺序，也是"越往后越粗"的语义）。
# [EN] Levels, finest to coarsest (also the UI order).
DETAIL_LEVELS: tuple[str, ...] = ('很详细', '详细', '中间', '简略', '带过')

#: "跟哪一档都对不上"时显示的那一项。**不是档位**，选了不改任何数。
# [EN] Shown when the two numbers match no preset. Not a level; picking it changes nothing.
DETAIL_CUSTOM = '自定义'

#: 档位 → `(一拍故事秒 BEAT_SECONDS, 时间倍率 TIME_RATIO)`。
#:
#: ⚠ 两列都必须是**闭集里的整数**：`config.SPEC` 里 `BEAT_SECONDS` / `TIME_RATIO`
#:   都是 int（min=1、max=3600），写小数会被 `coerce` 悄悄变成 0。
#: ⚠ 改这里的数就是改"一天看多久"——`BEAT_SECONDS ÷ TIME_RATIO` 才是**每拍真实秒**，
#:   只改一个会同时改掉观看速度与故事粒度，别只盯一列。
# [EN] Level -> (story seconds per beat, time ratio). Both are ints inside the closed set
# [EN] (`BEAT_SECONDS` / `TIME_RATIO` are ints 1..3600 in `config.SPEC`). `BEAT_SECONDS /
# [EN] TIME_RATIO` is the real seconds per beat -- edit one column and you move both the
# [EN] watch speed and the story granularity.
DETAIL_PRESETS: dict[str, tuple[int, int]] = {
    '很详细': (60, 1),
    '详细': (120, 1),
    '中间': (240, 2),
    '简略': (600, 6),
    '带过': (1800, 20),
}


def preset_of(level: str) -> tuple[int, int] | None:
    """档位 → `(一拍故事秒, 时间倍率)`；不是档位（含 `自定义` / 空）就 `None`。

    ⚠ 返回 `None` 是**正常情况**，不是错误：选了「自定义」那一项本来就什么都不该改。
    [EN] Level -> (beat seconds, ratio); `None` when it is not a level (including `自定义`).
    [EN] `None` is normal, not an error: picking the custom entry must change nothing.
    """
    return DETAIL_PRESETS.get(str(level or '').strip())


def level_of(beat_seconds: int, time_ratio: int) -> str:
    """反查：当前这两个数属于哪一档；对不上就是 `自定义`。

    ⚠ 只认**逐值相等**，不做"最接近"—— 界面上一旦显示"详细"，用户就有权认为
      下面那两个数正是这一档的数；显示一个近似值等于撒谎。
    [EN] Reverse lookup: which level these two numbers are; `自定义` when none matches.
    [EN] Exact equality only -- never "nearest": showing a level implies the two numbers
    [EN] below are exactly that level's numbers.
    """
    try:
        b = int(beat_seconds)
        r = int(time_ratio)
    except (TypeError, ValueError):
        return DETAIL_CUSTOM
    for lv, (pb, pr) in DETAIL_PRESETS.items():
        if pb == b and pr == r:
            return lv
    return DETAIL_CUSTOM


def real_seconds_of(beat_seconds: int, time_ratio: int) -> float:
    """每拍要等多少**真实秒**（`一拍 ÷ 倍率`，两个都夹到 ≥1）。

    ⚠ 与 `sim/loop.py::_advance_clock` 逐字同一条式子：那边是
      `_beat_acc += dt × TIME_RATIO`、攒够 `BEAT_SECONDS` 起一拍 ⇒ 一拍等
      `BEAT_SECONDS ÷ TIME_RATIO` 真实秒。这里只是把它算给界面看。
    [EN] Real seconds per beat (`beat / ratio`, both clamped to >=1) -- literally the same
    [EN] formula as `sim/loop.py::_advance_clock`.
    """
    try:
        b = max(1, int(beat_seconds))
    except (TypeError, ValueError):
        b = 1
    try:
        r = max(1, int(time_ratio))
    except (TypeError, ValueError):
        r = 1
    return b / float(r)


def apply_to(level: str) -> dict[str, int]:
    """档位 → 要写进配置的那两项（`{键: 值}`）；不是档位就返回空字典。

    调用方拿它去 `CFG.set` / `CFG.set_override`，**不要**在别处再抄一份数字。
    [EN] Level -> the two config entries to write; empty dict when it is not a level.
    """
    pr = preset_of(level)
    if not pr:
        return {}
    beat, ratio = pr
    return {'BEAT_SECONDS': int(beat), 'TIME_RATIO': int(ratio)}
