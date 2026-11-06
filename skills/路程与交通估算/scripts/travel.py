#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行程估算（技能附带的计算工具，由「路程与交通估算」技能调用）。

用法
    python travel.py 1200 --mode 快马
    python travel.py 300 --mode 步行 --rain --load
    python travel.py 800 --mode 步行 --mode 快马      # 多方案对比
    python travel.py --table                           # 全部方式速查表
    python travel.py 500 --km                          # 输入按公里算

设计原则
    给的是**区间**而不是单一数字 —— 古代行程本来就有一倍上下的浮动，
    报一个精确到小数点的天数反而假。

English:
Travel estimation (calculation tool bundled with the skill, invoked by the "Route and
Transportation Estimation" skill).
Usage
    python travel.py 1200 --mode 快马
    python travel.py 300 --mode 步行 --rain --load
    python travel.py 800 --mode 步行 --mode 快马      # multi-plan comparison
    python travel.py --table                           # quick reference table for all modes
    python travel.py 500 --km                          # input is calculated in kilometers
Design principles
    Give a **range** rather than a single number — ancient travel inherently fluctuates by about a factor of two,
    reporting a day count precise to the decimal point would instead be fake.
"""
from __future__ import annotations

import sys

# 方式 → (慢值, 快值) 里/日
# [EN] mode → (slow value, fast value) li/day
MODES = {
    '步行': (30, 50),
    '急行': (60, 80),
    '骑驴': (40, 60),
    '马车': (40, 60),
    '商队': (30, 40),
    '快马': (150, 250),
    '急递': (300, 600),
    '漕船顺流': (100, 200),
    '漕船逆流': (30, 50),
    '海船': (200, 300),
}

KM_PER_LI = 0.5          # 近似
# [EN] approximate
LOSS_NOTE = {
    'rain': ('雨天泥泞', 0.7),
    'load': ('负重/载货', 0.85),
    'mountain': ('山路', 0.6),
    'escort': ('随行辎重/家眷', 0.8),
}


def fmt(days: float) -> str:
    if days < 1:
        hours = days * 24
        return f'{hours:.1f} 小时（不足一日）'
    if days < 3:
        return f'{days:.1f} 天'
    return f'{days:.1f} 天（约 {round(days)} 日）'


def evaluate(li: float, mode: str, factors: list[tuple[str, float]]) -> None:
    if mode not in MODES:
        print(f'不认识的方式：{mode}。可用：{"、".join(MODES)}', file=sys.stderr)
        return
    slow, fast = MODES[mode]
    mult = 1.0
    for _, m in factors:
        mult *= m

    # 速度被限制后整体下降 → 耗时上升
    # [EN] after speed is limited, overall decreases → time cost increases
    eff_fast = fast * mult
    eff_slow = slow * mult
    best = li / eff_fast          # 最快情况：天数最少
    worst = li / eff_slow         # 最慢情况：天数最多
    # [EN] fastest case: fewest days
    # [EN] slowest case: most days

    bits = '、'.join(name for name, _ in factors)
    print(f'{li:g} 里（≈ {li * KM_PER_LI:g} 公里）  方式：{mode}'
          + (f'  限制：{bits}' if bits else ''))
    print(f'  理论：{fmt(best)} ~ {fmt(worst)}')
    # 现实损耗：渡河、关卡、补给、采买，经验值最快也要加一成、最慢可到五成
    # [EN] realistic losses: river crossings, checkpoints, resupply, purchasing; even the fastest
    # [EN] experience value must add 10%, the slowest can reach 50%
    print(f'  实际：{fmt(best * 1.1)} ~ {fmt(worst * 1.5)}'
          f'  ← 已含渡河、关卡、补给的常规损耗')
    if mode == '快马':
        print('  ⚠ 快马不能连日持久：这是"换马"后的数字。一人一马请按 急行 估。')
    if mode == '急递':
        print('  ⚠ 急递是**制度性**速度（驿站接力换马），平民用不上。')
    if mode == '步行' and li > 1000:
        print(f'  ⚠ {li:g} 里步行超过一个月，途中必有病、雨、盘缠三关，'
              f'建议再乘 1.5 以上。')
    print()


def table() -> None:
    print(f'{"方式":12s} {"慢(里/日)":>10s} {"快(里/日)":>10s} '
          f'{"走 500 里需":>14s}')
    for m, (s, f) in MODES.items():
        span = f'{500 / f:.1f}–{500 / s:.1f} 天'
        print(f'{m:12s} {s:>10d} {f:>10d} {span:>14s}')
    print('\n注：实际请再乘 1.2~1.5（渡河、关卡、雨天、补给）。')


def main() -> None:
    args = sys.argv[1:]
    if not args or '--table' in args:
        table()
        return

    # 距离
    # [EN] distance
    try:
        raw = float(args[0])
    except ValueError:
        print(f'距离必须是数字，收到 {args[0]!r}', file=sys.stderr)
        sys.exit(2)
    li = raw * 2 if '--km' in args else raw      # --km：输入按公里
    # [EN] --km: input is in kilometers

    modes: list[str] = []
    factors: list[tuple[str, float]] = []
    skip = False
    for i, a in enumerate(args[1:], 1):
        if skip:
            skip = False
            continue
        if a == '--mode':
            if i + 1 < len(args):
                modes.append(args[i + 1])
                skip = True
        elif a.lstrip('-') in LOSS_NOTE:
            factors.append(LOSS_NOTE[a.lstrip('-')])

    for m in (modes or ['步行']):
        evaluate(li, m, factors)


if __name__ == '__main__':
    main()
