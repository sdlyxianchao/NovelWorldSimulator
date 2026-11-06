# -*- coding: utf-8 -*-
"""故事时间：软时钟下的虚拟时刻、时辰、历法显示。
English:
Story time: virtual moments under the soft clock, shichen, calendar display.
"""
from __future__ import annotations

from dataclasses import dataclass

SHICHEN = [
    ("子时", 23), ("丑时", 1), ("寅时", 3), ("卯时", 5), ("辰时", 7), ("巳时", 9),
    ("午时", 11), ("未时", 13), ("申时", 15), ("酉时", 17), ("戌时", 19), ("亥时", 21),
]


@dataclass
class GameTime:
    day: int = 1
    minutes: int = 8 * 60          # 从 08:00 起
    # [EN] From 08:00 onward

    def add(self, minutes: int) -> "GameTime":
        total = self.minutes + minutes
        d = self.day
        while total >= 1440:
            total -= 1440
            d += 1
        while total < 0:
            total += 1440
            d -= 1
        return GameTime(d, total)

    @property
    def hour(self) -> int:
        return self.minutes // 60

    @property
    def minute(self) -> int:
        return self.minutes % 60

    @property
    def shichen(self) -> str:
        h = self.hour
        if h >= 23 or h < 1:
            return "子时"
        if h < 3:
            return "丑时"
        if h < 5:
            return "寅时"
        if h < 7:
            return "卯时"
        if h < 9:
            return "辰时"
        if h < 11:
            return "巳时"
        if h < 13:
            return "午时"
        if h < 15:
            return "未时"
        if h < 17:
            return "申时"
        if h < 19:
            return "酉时"
        if h < 21:
            return "戌时"
        return "亥时"

    @property
    def is_night(self) -> bool:
        return self.hour >= 22 or self.hour < 5

    def segment(self) -> str:
        h = self.hour
        for start, end, name in (
            (5, 8, "清晨"), (8, 11, "上午"), (11, 13, "晌午"), (13, 17, "午后"),
            (17, 19, "傍晚"), (19, 22, "入夜"), (22, 24, "深夜"), (0, 5, "凌晨"),
        ):
            if start <= h < end:
                return name
        return "凌晨"

    def hhmm(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d}"

    def __str__(self) -> str:
        return f"第{self.day}天 {self.shichen}({self.hhmm()})"


def shichen_span(name: str) -> tuple[int, int] | None:
    """某个时辰覆盖现代的哪两个小时 `(起始小时, 结束小时)`；叫不出这个名字就 None。

    ★ 2026-10-24：用户要求时间面板悬停时"解释这个时间是几点到几点"。这个换算
      **只能有一处** —— 时辰表就在上面 `SHICHEN`，界面不该再抄一份数字
      （抄了就会出现"表里写 19、界面写 18"这种没人发现的对不上）。

    ⚠ **子时跨午夜**：23:00 – 次日 01:00 ⇒ 返回 `(23, 1)`，结束小时比开始小。
      调用方拿到的就是这两个原始数，怎么讲（"次日 01:00"）由文案决定。
    [EN] Which two modern hours a shichen covers, `(start hour, end hour)`; None if the name is
    [EN] unknown.
    [EN] ★ 2026-10-24: the user asked the time panel to explain, on hover, "which hours this is".
    [EN] That conversion **may only exist in one place** -- the shichen table is `SHICHEN` above, and
    [EN] the UI must not copy those numbers (a copy produces mismatches like the table saying 19 while
    [EN] the UI says 18, which nobody notices).
    [EN] ⚠ **The zi hour straddles midnight**: 23:00 - 01:00 next day => returns `(23, 1)`, end before
    [EN] start. Callers get the two raw numbers; how to word it ("01:00 next day") is the copy's job.
    """
    for nm, start in SHICHEN:
        if nm == str(name or '').strip():
            return start, (start + 2) % 24
    return None


def format_game_clock(gt: GameTime, calendar: str = "auto", regnal: str = "",
                      *, with_day: bool = True) -> str:
    """游戏时钟 → 显示文本。

    `with_day=False` 只回**时段**部分（"子时" / "23:00"）——
    给"标题里已经写了第 N 天"的地方用，否则会出现
    `第 1 天 · 第1天·子时` 这种双份日期（2026-10-18 实测）。
    [EN] Game clock -> display text. `with_day=False` returns **only the time of day** ("zi hour" /
    [EN] "23:00") for headings that already carry "day N"; otherwise the date appears twice
    [EN] (`day 1 · day 1, zi hour`), measured on 2026-10-18.
    """
    if calendar == "modern":
        return (f"第{gt.day}日 {gt.hour:02d}:{gt.minute:02d}" if with_day
                else f"{gt.hour:02d}:{gt.minute:02d}")
    if calendar == "daycount":
        return f"第{gt.day}天 {gt.shichen}" if with_day else gt.shichen
    if calendar == "regnal" and regnal:
        return f"{regnal} {gt.day}日 {gt.shichen}" if with_day else gt.shichen
    if calendar == "ganzhi":
        gz = ["甲子", "乙丑", "丙寅", "丁卯", "戊辰", "己巳", "庚午", "辛未",
              "壬申", "癸酉", "甲戌", "乙亥", "丙子", "丁丑", "戊寅", "己卯"][gt.day % 16]
        return f"{gz}日 {gt.shichen}" if with_day else gt.shichen
    return f"第{gt.day}天·{gt.shichen}" if with_day else gt.shichen