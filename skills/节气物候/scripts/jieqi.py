#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""节气查询（技能附带的读写工具，由「节气物候」技能调用）。

用法
    python jieqi.py 2026-04-05        查某天属于哪个节气、处于第几候
    python jieqi.py --month 4         查某月的两个节气
    python jieqi.py --list            二十四节气全表
    python jieqi.py                   查今天

算法说明（重要）
    用的是流传较广的**近似公式**（[Y×D+C]−L 型），在 20 世纪初至 21 世纪
    范围内误差通常 ±1 天，个别年份会差 2 天。**写小说够用，做天文历算不够用。**
    真要精确值请查紫金山天文台发布的历书。

English:
Solar term query (read/write tool bundled with the skill, called by the "节气物候" skill).
Usage
    python jieqi.py 2026-04-05        Query which solar term a given day falls in and which pentad it is in
    python jieqi.py --month 4         Query the two solar terms of a month
    python jieqi.py --list            Full table of the twenty-four solar terms
    python jieqi.py                   Query today
Algorithm notes (important)
    Uses the widely circulated **approximate formula** ([Y×D+C]−L type), from the early 20th century to the 21st
    The error within the range is usually ±1 day, and in some years it can be off by 2 days. **Good enough for writing novels, not good enough for astronomical calendar computation.**
    For truly precise values, consult the almanac published by the Purple Mountain Observatory.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta

# 节气次序（按公历年内顺序）
# [EN] Solar term order (in order within the Gregorian year)
NAMES = [
    '小寒', '大寒', '立春', '雨水', '惊蛰', '春分',
    '清明', '谷雨', '立夏', '小满', '芒种', '夏至',
    '小暑', '大暑', '立秋', '处暑', '白露', '秋分',
    '寒露', '霜降', '立冬', '小雪', '大雪', '冬至',
]

# 近似公式用的 C 值（20–21 世纪通用的一套经验值）
# [EN] C values used by the approximate formula (a set of empirical values common to the 20th-21st
# [EN] centuries)
C_VALUE = {
    '小寒': 5.4055, '大寒': 20.12, '立春': 3.87, '雨水': 18.73,
    '惊蛰': 5.63, '春分': 20.646, '清明': 4.81, '谷雨': 20.1,
    '立夏': 5.52, '小满': 21.04, '芒种': 5.678, '夏至': 21.37,
    '小暑': 7.108, '大暑': 22.83, '立秋': 7.5, '处暑': 23.13,
    '白露': 7.646, '秋分': 23.042, '寒露': 8.318, '霜降': 23.438,
    '立冬': 7.438, '小雪': 22.36, '大雪': 7.18, '冬至': 22.6,
}

# 三候（出自《月令七十二候集解》）
# [EN] Third pentad (from "Yueling Qishier Hou Jijie")
HOU = {
    '立春': ['东风解冻', '蛰虫始振', '鱼陟负冰'],
    '雨水': ['獭祭鱼', '候雁北', '草木萌动'],
    '惊蛰': ['桃始华', '仓庚鸣', '鹰化为鸠'],
    '春分': ['玄鸟至', '雷乃发声', '始电'],
    '清明': ['桐始华', '田鼠化为鴽', '虹始见'],
    '谷雨': ['萍始生', '鸣鸠拂其羽', '戴胜降于桑'],
    '立夏': ['蝼蝈鸣', '蚯蚓出', '王瓜生'],
    '小满': ['苦菜秀', '靡草死', '麦秋至'],
    '芒种': ['螳螂生', '鵙始鸣', '反舌无声'],
    '夏至': ['鹿角解', '蜩始鸣', '半夏生'],
    '小暑': ['温风至', '蟋蟀居宇', '鹰始鸷'],
    '大暑': ['腐草为萤', '土润溽暑', '大雨时行'],
    '立秋': ['凉风至', '白露降', '寒蝉鸣'],
    '处暑': ['鹰乃祭鸟', '天地始肃', '禾乃登'],
    '白露': ['鸿雁来', '玄鸟归', '群鸟养羞'],
    '秋分': ['雷始收声', '蛰虫坯户', '水始涸'],
    '寒露': ['鸿雁来宾', '雀入大水为蛤', '菊有黄华'],
    '霜降': ['豺乃祭兽', '草木黄落', '蛰虫咸俯'],
    '立冬': ['水始冰', '地始冻', '雉入大水为蜃'],
    '小雪': ['虹藏不见', '天气上升地气下降', '闭塞而成冬'],
    '大雪': ['鹖鴠不鸣', '虎始交', '荔挺出'],
    '冬至': ['蚯蚓结', '麋角解', '水泉动'],
    '小寒': ['雁北乡', '鹊始巢', '雉始雊'],
    '大寒': ['鸡始乳', '征鸟厉疾', '水泽腹坚'],
}

# 意象与农事（给写作直接取用）
# [EN] Imagery and farming activities (for direct use in writing)
IMAGE = {
    '立春': '柳芽未吐，风里已有暖意；咬春吃萝卜春饼',
    '雨水': '冰化泥软，草木悄悄萌动；备耕修农具',
    '惊蛰': '第一声雷，虫醒；桃始开花',
    '春分': '昼夜平分，燕子归来；育秧下种',
    '清明': '桐花、细雨、扫墓、踏青；采明前茶',
    '谷雨': '雨生百谷，浮萍初生；插秧种豆',
    '立夏': '暑气初起，蛙声密；麦子灌浆',
    '小满': '麦粒渐满未熟，苦菜可食',
    '芒种': '一年最忙，收麦插秧两头赶；梅雨将至',
    '夏至': '日最长，蝉始鸣；吃面',
    '小暑': '温风至，蟋蟀上阶，暑气蒸人',
    '大暑': '最热，萤火虫、雷阵雨、井水浸瓜',
    '立秋': '凉风至，寒蝉鸣（仍热，秋老虎）',
    '处暑': '暑气止，禾熟待收',
    '白露': '露凝白，雁南飞，早晚凉',
    '秋分': '昼夜再平，雷声收，秋收种冬麦',
    '寒露': '露寒将霜，菊花黄，雁南来',
    '霜降': '初霜降，草木黄落，收薯腌菜',
    '立冬': '水始冰，地始冻，冬藏腌腊',
    '小雪': '初雪，虹不见，天地闭塞',
    '大雪': '雪盛，虎始交，荔挺出，农闲水利',
    '冬至': '日最短，祭祖数九；饺子或汤圆',
    '小寒': '三九最冷，鹊始筑巢',
    '大寒': '一年最冷，冰坚；备春耕积肥',
}


def jieqi_date(name: str, year: int) -> date:
    """近似算某个节气在某年的公历日期。
        English:
    Approximately compute the Gregorian date of a solar term in a given year.
    """
    y = year % 100
    c = C_VALUE[name]
    # 闰年修正：L = 闰年数
    # [EN] Leap year correction: L = number of leap years
    leap = y // 4
    day = int(y * 0.2422 + c) - leap
    month = (NAMES.index(name) // 2) + 1
    try:
        return date(year, month, day)
    except ValueError:            # 公式偶有溢出到相邻月（如 0 日、32 日）
    # [EN] The formula occasionally overflows into an adjacent month (e.g. day 0, day 32)
        base = date(year, month, 1) + timedelta(days=day - 1)
        return base


def year_table(year: int) -> list[tuple[str, date]]:
    return [(n, jieqi_date(n, year)) for n in NAMES]


def find(d: date) -> tuple[str, date, int, list[str]]:
    """返回 (当前节气, 该节气起始日, 第几候(1-3), 三候列表)。
        English:
    Return (current solar term, start day of that solar term, which pentad (1-3), list of three
    pentads).
    """
    table = year_table(d.year)
    # 冬至/小寒跨年：把上一年的冬至也算进来
    # [EN] Winter solstice/Minor Cold cross-year: include the previous year's winter solstice as well
    prev = year_table(d.year - 1)
    pool = sorted(prev[-1:] + table, key=lambda t: t[1])
    current = pool[0]
    for name, dt in pool:
        if dt <= d:
            current = (name, dt)
        else:
            break
    name, start = current
    offset = (d - start).days
    hou = min(3, offset // 5 + 1)
    return name, start, hou, HOU[name]


def cmd_query(d: date) -> None:
    name, start, hou, hlist = find(d)
    print(f'{d.isoformat()}（{d.strftime("%Y年%m月%d日")}）')
    print(f'  节气：{name}（自 {start.isoformat()} 起第 {hou} 候）')
    print(f'  三候：{hlist[0]} · {hlist[1]} · {hlist[2]}')
    print(f'  本候：{hlist[hou - 1]}')
    print(f'  意象：{IMAGE[name]}')


def cmd_month(m: int) -> None:
    y = date.today().year
    hits = [(n, jieqi_date(n, y)) for n in NAMES
            if ((NAMES.index(n) // 2) + 1) == m]
    print(f'{y} 年 {m} 月：')
    for n, dt in hits:
        print(f'  {dt.day:2d} 日  {n}   三候：{" · ".join(HOU[n])}')
        print(f'           意象：{IMAGE[n]}')


def cmd_list() -> None:
    print('二十四节气（按年内顺序）：')
    for i, n in enumerate(NAMES):
        m = (i // 2) + 1
        print(f'  {i + 1:2d}. {n}（约 {m} 月）  三候：{" · ".join(HOU[n])}')


def main() -> None:
    args = sys.argv[1:]
    if not args:
        cmd_query(date.today())
    elif args[0] == '--list':
        cmd_list()
    elif args[0] == '--month':
        try:
            cmd_month(int(args[1]))
        except (IndexError, ValueError):
            print('用法：--month <1-12>', file=sys.stderr)
            sys.exit(2)
    else:
        for raw in args:
            try:
                cmd_query(datetime.strptime(raw, '%Y-%m-%d').date())
            except ValueError:
                print(f'无法解析日期：{raw}（应为 YYYY-MM-DD）', file=sys.stderr)
                sys.exit(2)


if __name__ == '__main__':
    main()
