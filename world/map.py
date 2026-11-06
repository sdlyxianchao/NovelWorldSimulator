# -*- coding: utf-8 -*-
"""⚠ **已停用**（2026-10-08）—— 这里的东西**没有任何地方在用**。

被谁取代：`world/atlas.py` 的 `Atlas`（**三级底图**：整体 / 局部 / 室内）。

为什么留着而不删：这个项目**没有版本控制**，删掉就找不回来了；
而这一段（设计稿 §11.2 的 ASCII 网格渲染）是"早期怎么想过画地图"的记录。
**但不要照它写新代码** —— 它曾经是一条完整的死链路：

  · `GameMap.from_yaml()` 读 `设定集/小世界地图.yaml`；
  · `sim/setup.py` 的 `build_map()` 调它、把结果挂到 `RunLoop(game_map=…)`；
  · 而那份 yaml 从来只写过一个空占位（`{"名称":"待生成","地点":[]}`）→
    `build_map()` 永远返回 `None`；
  · 挂上去的那个 `game_map` 字段，**从头到尾没有任何地方读它**。

也就是说：有类、有调用、有落盘文件、有字段 —— 唯独没有"用"。
现在的 `Atlas` 是**开卷时真的生成**（`ingest/atlas.py`）、运行时真的读来取景的。

**ASCII 小地图（设计稿 §11.2）：用 YAML 地图数据渲染字符网格。**
English:
⚠ **Deprecated** (2026-10-08) —— nothing here is **used anywhere**.
Replaced by: `Atlas` in `world/atlas.py` (**three-level basemap**: overall / local / indoor).
Why keep it instead of deleting: this project has **no version control**, once deleted it cannot
be recovered;
and this section (the ASCII grid rendering from design doc §11.2) is a record of "how map
drawing was once envisioned early on".
**But do not write new code based on it** —— it used to be a complete dead chain:
  · `build_map()` in `sim/setup.py` calls it and attaches the result to `RunLoop(game_map=…)`;
    `build_map()` always returns `None`;
  · that attached `game_map` field, **is never read anywhere from start to finish**.
In other words: there is a class, there are calls, there is a persisted file, there is a field
—— only "usage" is missing.
The current `Atlas` is **actually generated when opening the book** (`ingest/atlas.py`), and
actually read at runtime for framing.
**ASCII minimap (design doc §11.2): render a character grid using YAML map data.**
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MapCell:
    terrain: str = "."     # . / # / ~ / ▤ 等
    label: str = ""        # 地点名（4字以内）
    # [EN] . / # / ~ / ▤ etc.
    # [EN] Place name (within 4 characters)
    people: list[str] = field(default_factory=list)
    highlight: bool = False

    def render(self, width: int = 4) -> str:
        if self.people:
            marker = "@" if self.highlight else "●"
            return marker.center(width)
        if self.label:
            return self.label[:width].center(width)
        return self.terrain * width


@dataclass
class GameMap:
    """小世界地图（§小世界地图.yaml 驱动）。
        English:
    Small world map (driven by §小世界地图.yaml).
    """
    name: str = "默认地图"
    width: int = 12
    height: int = 8
    locations: list[dict] = field(default_factory=list)
    grid: list[list[MapCell]] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, data: dict) -> "GameMap":
        """从 小世界地图.yaml 构建。
                English:
        Build from 小世界地图.yaml.
        """
        gm = cls(name=data.get("名称", "未知"))
        locs = data.get("地点", [])
        gm.locations = locs
        # 简单网格：把地点排成矩形
        # [EN] Simple grid: arrange places into a rectangle
        import math
        n = max(len(locs), 1)
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        gm.width = cols
        gm.height = rows
        grid: list[list[MapCell]] = []
        for r in range(rows):
            row: list[MapCell] = []
            for c in range(cols):
                idx = r * cols + c
                if idx < len(locs):
                    loc = locs[idx]
                    cell = MapCell(terrain="#", label=loc.get("名称", "")[:4])
                else:
                    cell = MapCell(terrain=".")
                row.append(cell)
            grid.append(row)
        gm.grid = grid
        return gm

    def render(self) -> str:
        lines = []
        lines.append(f"┌{'─' * (self.width * 5 + 1)}┐")
        for row in self.grid:
            line = "│" + "".join(c.render(5) for c in row) + "│"
            lines.append(line)
        lines.append(f"└{'─' * (self.width * 5 + 1)}┘")
        return "\n".join(lines)

    def place_person(self, name: str, location: str) -> None:
        for row in self.grid:
            for cell in row:
                if cell.label and location in cell.label:
                    if name not in cell.people:
                        cell.people.append(name)
                elif name in cell.people:
                    cell.people.remove(name)