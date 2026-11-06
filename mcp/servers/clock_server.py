# -*- coding: utf-8 -*-
"""MCP 服务器：虚拟时钟（十二时辰换算）。

这是设计稿 §8.6 预置模板里 `time` 那一项的落地版——但它不是通用时间服务，
而是为**中文小说**定制的：十二时辰、雅称、按节奏倍率估算真实耗时。

为什么值得单独做一个服务器？
  这类换算「LLM 自己能做，但经常做错」——尤其是跨日进位（戌时 + 4 小时是哪天哪个时辰）
  和 23:00 之后归入子时这种边界。给它一个确定的计算工具，比让 LLM 硬猜可靠。

工具
    shichen          给小时查时辰（含雅称与时段）
    shichen_table    十二时辰全表
    advance          从某天某时辰推进 N 小时，返回新的故事日与时辰
    real_cost        按 TIME_RATIO 估算 N 个故事日大约要跑多久

运行
    python mcp/servers/clock_server.py
自检
    python mcp/servers/clock_server.py --call shichen '{"hour":19}'

English:
MCP server: virtual clock (twelve shichen conversion).
This is the landed version of the `time` item in the preset templates of design doc §8.6 — but
it is not a general-purpose time service,
it is customized for **Chinese novels**: twelve shichen, elegant names, and estimating real
elapsed time by pacing multiplier.
Why is it worth making a separate server?
  This kind of conversion "an LLM can do itself, but often gets wrong" — especially cross-day carry (xushi + 4 hours is which day and which shichen)
  and the boundary case where after 23:00 it falls into zishi. Giving it a deterministic calculation tool is more reliable than making the LLM guess.
Tools
    shichen          look up shichen by hour (including elegant name and time range)
    shichen_table    full table of the twelve shichen
    advance          advance N hours from a given day and shichen, returning the new story day and shichen
    real_cost        estimate roughly how long N story days take to run by TIME_RATIO
Run
    python mcp/servers/clock_server.py
Self-check
    python mcp/servers/clock_server.py --call shichen '{"hour":19}'
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mcpkit import Server, text_result, json_result, error_result, serve  # noqa: E402

srv = Server(
    'nws-clock', '1.0.0',
    instructions=(
        '十二时辰换算与故事时间推演。\n'
        '**跨日进位和 23 点后的子时边界很容易算错**，涉及"过几个时辰是哪天"时请用本工具，'
        '不要自己推。'))

# (地支, 起始小时, 雅称)。起始小时指该时辰的起点；子时跨 23:00→01:00 属特例。
# [EN] (Earthly branch, start hour, elegant name). Start hour is the starting point of that shichen;
# [EN] zishi spans 23:00→01:00 and is a special case.
SHICHEN = [
    ('子', 23, '夜半'), ('丑', 1, '鸡鸣'), ('寅', 3, '平旦'), ('卯', 5, '日出'),
    ('辰', 7, '食时'), ('巳', 9, '隅中'), ('午', 11, '日中'), ('未', 13, '日昳'),
    ('申', 15, '晡时'), ('酉', 17, '日入'), ('戌', 19, '黄昏'), ('亥', 21, '人定'),
]
# 便于按名字查：地支 → (起始小时, 雅称)
# [EN] Easy lookup by name: earthly branch → (start hour, elegant name)
BY_NAME = {name: (start, alias) for name, start, alias in SHICHEN}


def _fmt_range(start: int) -> str:
    end = (start + 2) % 24
    return f'{start:02d}:00–{end:02d}:00'


def _shichen_of(hour: int) -> tuple[str, int, str]:
    """小时 → (地支, 起始小时, 雅称)。23 点与 0 点都算子时。
        English:
    Hour → (earthly branch, start hour, elegant name). Both 23 o'clock and 0 o'clock count as zishi.
    """
    hour = hour % 24
    if hour == 23 or hour == 0:
        return '子', 23, '夜半'
    for name, start, alias in SHICHEN:
        if start <= hour < start + 2:
            return name, start, alias
    return '子', 23, '夜半'      # 兜底（理论到不了）
    # [EN] Fallback (theoretically unreachable)


def _parse_int(args: dict, key: str, default: int | None = None) -> int:
    raw = args.get(key, default)
    if raw is None or raw == '':
        raise ValueError(f'缺少参数 {key}')
    try:
        return int(float(raw))          # 容忍 "3" / 3.0 / "3.0"
        # [EN] Tolerate "3" / 3.0 / "3.0"
    except (TypeError, ValueError):
        raise ValueError(f'{key} 必须是数字，收到 {raw!r}') from None


@srv.tool('shichen', '给一个 0–23 的小时，查它属于哪个时辰（含时段与雅称）',
          {'hour': {'type': 'integer', 'description': '0–23 的整点小时'},
           'minute': {'type': 'integer', 'description': '分钟，默认 0'}},
          required=['hour'])
def shichen(args):
    try:
        hour = _parse_int(args, 'hour')
        minute = _parse_int(args, 'minute', 0)
    except ValueError as e:
        return error_result(str(e))

    name, start, alias = _shichen_of(hour % 24)
    stamp = f'{hour % 24:02d}:{minute % 60:02d}'
    return text_result(
        f'{stamp} → {name}时（{alias}）\n'
        f'时段：{_fmt_range(start)}\n'
        f'说明：{name}时是十二时辰的第 '
        f'{[n for n, _, _ in SHICHEN].index(name) + 1} 个')


@srv.tool('shichen_table', '十二时辰全表（地支 / 时段 / 雅称）')
def shichen_table(args):
    rows = [{'时辰': f'{n}时', '地支': n, '时段': _fmt_range(s), '雅称': a,
             '现代时间': f'{s:02d}:00'}
            for n, s, a in SHICHEN]
    return json_result({'共': 12, '表': rows})


@srv.tool('advance', '从第 X 天的某时辰推进 N 小时，返回新的故事日与时辰',
          {'day': {'type': 'integer', 'description': '起始故事日，如 3'},
           'shichen': {'type': 'string', 'description': '起始时辰，如 戌'},
           'hours': {'type': 'integer', 'description': '推进的小时数，可为负'}},
          required=['day', 'shichen', 'hours'])
def advance(args):
    try:
        day = _parse_int(args, 'day')
        hours = _parse_int(args, 'hours')
    except ValueError as e:
        return error_result(str(e))

    raw_name = str(args.get('shichen', '')).strip().rstrip('时')
    if raw_name not in BY_NAME:
        return error_result(
            f'不认识的时辰「{args.get("shichen")}」。可用：'
            + '、'.join(f'{n}时' for n, _, _ in SHICHEN))
    start_hour, _ = BY_NAME[raw_name]

    total = start_hour + hours
    day_shift, hour = divmod(total, 24)          # divmod 正确处理负数进位
    # [EN] divmod correctly handles negative carry
    name, new_start, alias = _shichen_of(hour)

    sign = '+' if hours >= 0 else ''
    return text_result(
        f'第 {day} 天 {raw_name}时（{start_hour:02d}:00）{sign}{hours} 小时\n'
        f'→ 第 {day + day_shift} 天 {name}时（{alias}）{hour:02d}:00\n'
        f'跨日：{"是，跨了 %d 天" % day_shift if day_shift else "否"}')


@srv.tool('real_cost', '按 TIME_RATIO 估算跑 N 个故事日大约要多少真实时间',
          {'days': {'type': 'integer', 'description': '故事日数'},
           'time_ratio': {'type': 'number',
                          'description': '秒/故事分钟，默认 60（即 1 故事小时≈1 真实分钟）'}},
          required=['days'])
def real_cost(args):
    try:
        days = _parse_int(args, 'days')
    except ValueError as e:
        return error_result(str(e))
    try:
        ratio = float(args.get('time_ratio') or 60.0)
    except (TypeError, ValueError):
        return error_result('time_ratio 必须是数字。')
    if ratio <= 0:
        return error_result('time_ratio 必须为正数。')

    story_minutes = days * 24 * 60
    real_seconds = story_minutes * ratio
    real_min = real_seconds / 60
    lines = [
        f'{days} 个故事日 = {story_minutes} 故事分钟',
        (f'按 TIME_RATIO={ratio:g} 估算：约 {real_seconds:,.0f} 秒 '
         f'= {real_min:,.1f} 分钟 = {real_min / 60:,.2f} 小时'),
    ]
    if ratio == 60:
        lines.append('（ratio=60 即 1 故事小时 ≈ 1 真实分钟；'
                     'TIME_RATIO 是节奏上限，不是保证）')
    lines.append('注意：实际耗时还取决于决策与 LLM 调用，时钟让位于决策完成。')
    return text_result('\n'.join(lines))


@srv.tool('now', '真实当前时间 + 它对应的时辰（方便给情节标注时辰）')
def now(args):
    dt = datetime.now()
    name, start, alias = _shichen_of(dt.hour)
    return text_result(
        f'真实时间：{dt.strftime("%Y-%m-%d %H:%M:%S")}\n'
        f'对应：{name}时（{alias}）· {_fmt_range(start)}')


if __name__ == '__main__':
    serve(srv)
