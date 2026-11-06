# -*- coding: utf-8 -*-
"""小地图的**布局规格**：按"当前故事发生在哪几处"把这一小块地方摆出来。

用户 2026-10-06 的要求
----------------------
「小地图是否可以用矢量图的形式每次都重新画一下（切换场景的时候绘制），
  而且要是根据故事里的设计尽可能的反应其布局（可以稍微简略但是不能够
  一点都不像），要求使用AI动态绘制」

★★ 取景范围只能来自**当前发生的故事**（2026-10-08 用户第二次点名）
------------------------------------------------------------------
用户原话：「小地图上主角所在的那一处旁边，画着一串**世界层级**的名字（各界、各域）；用户说「这些不是真实的地名」
 你让美术画图的时候**只根据当前发生的故事所在的地点画图** 而不是根据
 **整本小说设定**画图」。

查到底：项目 `地点.yaml` 里有 7 条，其中 6 条是**世界层级**的名字
（各界、各域这类**世界层级**的名字），只有一条是主角真正待着的地方
是主角真正待着的地方。而老链路 `ai_layout()` 会把这 7 条**一次全摆上屏** ——
日志里那句 `小地图布局：AI 排好 7 处地点（设定里共 7 处）` 就是它。
用户进运行界面时（当天剧本还没写）看到的就是这张**全书总图**。

所以现在：

| 用途 | 函数 | 范围从哪来 |
|---|---|---|
| **上屏的那张图** | `places_in_day()` + 剧组美术 | **当天剧本**里真的出现过、且设定里真实存在的地点 |
| 图还没出来时的兜底 | `here_only()` | **当前场景**一处（宁可小，不画错） |
| 历史做法（**已不上屏**） | `ai_layout()` / `local_view()` | 整本设定的地点表 / 设定里 AI 编的通路 |

拆成三件事，各归各处
--------------------
1. **AI 干什么** —— 读**今天要拍的戏**（分拍里的场/发生/推进），把今天这几处
   的**相对位置**摆出来。范围由剧情定，不由设定定。
2. **矢量渲染** 在 `minimap.py` —— 布局规格 → `ft.canvas` 的形状。
3. **每次切场景重画**：布局一天画一次（美术出工一次），
   每次切场景变的是"现在在哪"。切开成「美术画一次/天」+「重画（切场景，零成本）」。

⚠ **AI 拿不到时不能没有图**：`simple_layout()` 给一份确定性排布，
界面上明说这是简化版（不许假装是 AI 画的）。

English:
The minimap's **layout spec**: lay out this small area according to "which places the current
story takes place in".
User's request on 2026-10-06
----------------------
"Can the minimap be redrawn in vector form every time (drawn when switching scenes),
  and as much as possible reflect the layout according to the design in the story (can be a bit simplified but cannot
  not resemble it at all), require using AI to draw dynamically"
★★ The framing range can only come from **the currently occurring story** (2026-10-08, the user
called this out a second time)
------------------------------------------------------------------
User's exact words: "On the minimap, next to the place where the protagonist is, a string of
**world-level** names is drawn (each realm, each domain); the user said "these are not real
place names"
 when you have the artist draw the picture, **draw it only based on the locations of the currently occurring story**, not based on
 **the whole novel's setting**."
Trace it to the bottom: the project's `地点.yaml` has 7 entries, 6 of which are **world-level**
names
(names at the **world level** such as each realm, each domain), and only one is the place where
the protagonist actually stays
is the place where the protagonist actually stays. And the old code path `ai_layout()` puts all
7 of these **on screen at once** ——
When the user enters the runtime UI (the day's script isn't written yet), what they see is this
**whole-book overview map**.
So now:
| Purpose | Function | Where does the range come from |
|---|---|---|
| **The map that goes on screen** | `places_in_day()` + the crew artist | Locations that actually appeared in **the day's script** and truly exist in the setting |
| Fallback when the map isn't out yet | `here_only()` | **current scene** only one place (rather small than wrong) |
| Historical approach (**no longer on screen**) | `ai_layout()` / `local_view()` | the location table of the whole setting / AI-invented paths in the setting |
Split into three things, each in its own place
--------------------
1. **What AI does** —— read **today's scenes to shoot** (scene/occurrence/advance in the shot breakdown), and lay out today's several
   **relative positions**. The scope is decided by the plot, not by the setting.
2. **Vector rendering** in `minimap.py` —— layout spec → shapes for `ft.canvas`.
3. **Redraw on every scene switch**: the layout is drawn once a day (artwork produces once),
   what changes on every scene switch is "where we are now". Split into "artwork draws once/day" + "redraw (scene switch, zero cost)".
⚠ **When AI is unavailable, the map must not be missing**: `simple_layout()` gives a
deterministic arrangement,
and the UI explicitly says this is a simplified version (not allowed to pretend it was drawn by
AI).
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from logger import get_logger

_LOG = get_logger('nws.map')

# ── AI 能用的字形（**白名单**，别的字一律退回「屋」）────────────────────
# [EN] ── Glyphs the AI can use (**whitelist**, anything else falls back to "house")
# [EN] ────────────────────
# 为什么不放开：渲染器要按字形决定怎么画（三角形/弧线/圆）。
# 放任模型自由发明（"牌楼""水榭""戏台"…），渲染器只能给个方块，
# 那还不如老老实实归到最接近的一类里。
# [EN] Why not open it up: the renderer must decide how to draw based on the glyph
# [EN] (triangle/arc/circle).
# [EN] If the model freely invents things ("archway", "water pavilion", "stage"...), the renderer can
# [EN] only give a box,
# [EN] so it's better to honestly map it to the closest category.
SHAPES = ('屋', '院', '亭', '门', '桥', '渡', '树', '山', '塔', '台', '市')
SIZES = ('小', '中', '大')
LINKS = ('路', '桥', '巷', '廊')

#: 一份布局最多几个地点。太多了 200×126 的小画布上就是一团墨。
# [EN] : Max number of locations per layout. Too many and it's just a blob of ink on a 200×126 small
# [EN] canvas.
MAX_PLACES = 24

#: `purpose` 名（LLM 路由用）。同时也是 `NO_THINK_PURPOSES` 的键 ——
#: 这是**结论型**产出（一份小 JSON），让模型"想"只会把额度烧在思考上。
# [EN] : The `purpose` name (used for LLM routing). Also the key for `NO_THINK_PURPOSES` ——
# [EN] : This is a **conclusion-type** output (a small JSON); letting the model "think" only burns
# [EN] quota on thinking.
PURPOSE = 'minimap_layout'


# ══════════════════════════════════════════════════════════════════════
#  数据结构
# [EN] Data structures
# ══════════════════════════════════════════════════════════════════════
@dataclass
class Place:
    """一个地点在图上怎么放。`x` / `y` 是 **0~1 的相对坐标**（左上原点）。
        English:
    How a location is placed on the map. `x` / `y` are **relative coordinates in 0~1** (top-left
    origin).
    """
    name: str
    x: float = 0.5
    y: float = 0.5
    shape: str = '屋'
    size: str = '中'
    short: str = ''            # 图上显示的简称（≤3 字）
    # [EN] Short label shown on the map (≤3 chars)
    # ★ 2026-10-12（用户：「柜台跑到墙外面了」）：**这件陈设归哪间房**。
    #   ⚠ 从前没有这个字段，于是陈设的方块是用它自己的 x/y **独立定位**的 ——
    #     与房间矩形（另一套算法）各画各的，柜台上墙外是迟早的事。
    #   现在填了就用它；**留空则由几何最近的一间兜底**（见 `plan_audit.solve`）。
    #   所以它是**可选**的：AI 不填也不会出错，只是少一层语义。
    # [EN] ★ 2026-10-12 (the user: "the counter ran outside the wall"): **which room this fixture
    # [EN] belongs to**.
    # [EN] ⚠ This field did not exist before, so a fixture's block was **positioned independently**
    # [EN] by its own x/y -- a separate algorithm from the room rectangles -- and a counter outside
    # [EN] the wall was only a matter of time.
    # [EN] When filled in it is used; **when empty the geometrically nearest room is the fallback**
    # [EN] (see `plan_audit.solve`). So it is **optional**: the AI not filling it in causes no error,
    # [EN] it just loses one layer of meaning.
    room: str = ''
    note: str = ''

    def label(self) -> str:
        """图上要写的字：优先简称，没有就截名字。

        ★ 2026-10-12 补一条：名字里带 `·` 的（`临河茶肆·院子`、`临河茶肆·前厅`）
          **取后半截**再说 —— 不然图上写出来的是"临河茶肆"，跟整座楼的标题
          （画在框上）**一模一样**，看的人分不清哪个是院子、哪个是整栋。
        [EN] Text to draw on the map: prefer the short name, otherwise truncate the name.
        [EN] ★ Added 2026-10-12: a name containing `·` (`临河茶肆·院子`, `临河茶肆·前厅`) **takes the part
        [EN] after the dot** first -- otherwise the map writes "临河茶肆", identical to the whole building's
        [EN] title (drawn on the frame), and the viewer cannot tell the yard from the whole house.
        """
        if self.short:
            return self.short[:3]
        n = str(self.name or '')
        if '·' in n:
            n = n.split('·')[-1]
        return n[:3]


@dataclass
class Layout:
    """一整套布局。`to_dict()` / `from_dict()` 走 JSON，方便缓存。
        English:
    A whole layout. `to_dict()` / `from_dict()` go through JSON, convenient for caching.
    """
    places: list[Place] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)      # {a, b, kind}
    water: list[list[float]] = field(default_factory=list)   # [[x,y], …] 折线
    walls: list[list[float]] = field(default_factory=list)   # [[x,y], …] 闭合
    #: ★★★ 2026-10-27：这条 `water` **是什么水** —— `'river'` / `'lake'` / `'coast'`。
    #:
    #: 为什么必须有这个字段：`water` 只是一条折线，"一条线"能表达的东西**不止一种**，
    #: 而三种画法完全不同：
    #:   · **河**：一条带（两岸之间是水），线**居中加粗**是对的；
    #:   · **海**：折线是**陆与海的分界**，一侧全是水 —— 居中加粗会把海往陆地推半个带宽，
    #:     而且海那一面根本没有填充，读者只看到"沿着海岸有一条蓝色的河"（这是老实现的实际效果）；
    #:   · **湖**：闭合轮廓，内部填充。
    #: 空串 = 上游没说 ⇒ 由 `scalemap.water_kind()` **从数据推断**（闭合→湖；两端贴图廓
    #: 且一侧几乎没有地点→海；否则河）。推断有明确纪律：**判不准就当河**，
    #: 因为把河画成海会平白填蓝半张图，比把海画成河更错。
    # [EN] ★★★ 2026-10-27: **what kind of water** this `water` polyline is -- `'river'` /
    # [EN] `'lake'` / `'coast'`. A single polyline can mean more than one thing and the three are drawn
    # [EN] completely differently: a **river** is a band (thickening the line is right); a **coast**
    # [EN] separates land from sea with water on one side (thickening pushes the sea half a bandwidth
    # [EN] inland and leaves the sea unfilled, so the old code drew "a blue river running along the
    # [EN] shore"); a **lake** is a closed outline filled inside. Empty = the caller did not say, and
    # [EN] `scalemap.water_kind()` infers it (closed -> lake; both ends on the frame and one side nearly
    # [EN] empty of places -> coast; else river). The inference has a hard rule: **when unsure, call it a
    # [EN] river**, because painting half the map blue is a worse error than a drawn-out river.
    water_kind: str = ''
    caption: str = ''                                    # 角落题记（河名/地名）
    #: 这份布局是从哪来的：`ai` / `simple`。
    #: **界面要照实说**（兜底版不能冒充 AI 画的）。
    # [EN] [[x,y], …] polyline
    # [EN] [[x,y], …] closed
    # [EN] Corner caption (river name / place name)
    # [EN] : Where this layout came from: `ai` / `simple`.
    # [EN] : **The UI must say it honestly** (the fallback version must not masquerade as AI-drawn).
    source: str = 'simple'
    #: 这一层是**哪一层**：`整体` / `局部` / `室内`（见 `world/atlas.py` 的三级底图）。
    #: 空串 = 不知道（老缓存），渲染时按"没有室内语义"处理。
    # [EN] Which layer this is: `whole` / `local` / `indoor` (see the three-level base map in
    # [EN] `world/atlas.py`).
    # [EN] Empty = unknown (old cache); rendering then treats it as "no indoor semantics".
    kind: str = ''
    #: ★★ **整座建筑的名字**（室内图上要"框住 + 当标题"的那个）。
    #: 用户 2026-10-12：「小地图如果是**室内地图** 就用**一个框把相关内容括起来
    #: 作为这个建筑的名字** 现在是**中间一个红点**作为建筑名字 不但挡住了内容
    #: 还不合理」。
    #: 所以：室内图上**不再**给"整座楼"画一个点，改为把这一层整个**框起来**，
    #: 建筑名写在框上（`image_gen/minimap.py` 的 `build_shapes`）。
    #: 空串 = 不是室内图（或不知道叫什么）。
    # [EN] ★★ **The name of the whole building** (the one to "frame and use as the title" on an indoor
    # [EN] map).
    # [EN] User 2026-10-12: "if the minimap is an **indoor map**, use **a frame to enclose the relevant
    # [EN] content as this building's name**. Right now there is **a red dot in the middle** acting as
    # [EN] the building's name, which not only covers the content but is unreasonable."
    # [EN] So: on an indoor map the "whole building" **no longer** gets a point; instead the entire layer
    # [EN] is **framed**, with the building name written on the frame (`image_gen/minimap.py`'s
    # [EN] `build_shapes`).
    # [EN] Empty = not an indoor map (or its name is unknown).
    frame: str = ''
    #: ★★★ 2026-10-26 新增：**房间任务书**（`image_gen/roomplan.py` 的 `Program.to_dict()`）。
    #:
    #: 它取代了"把地点坐标存下来"的老做法。为什么：
    #:   · 坐标是**这一次的构图**，存下来只会把当时的布局永久固化 ——
    #:     实测旧 `锚定.json` 锁住的正是 9 个错坐标（门楼外、井当屋、二楼叠后院）；
    #:   · 任务书是**这处地方长什么样**，由它**确定性解算**出几何 ⇒
    #:     同一份任务书永远同一张图（延续性免费），改一处整张图跟着修好。
    #:
    #: 非空时，渲染层会走 `roomplan` 那条路（见 `floorplan.build_detail_shapes`）；
    #: 空 ⇒ **原样走老路**（老缓存、没设置、解算失败都落在这一格）。
    # [EN] ★★★ Added 2026-10-26: the **room program** (`roomplan.Program.to_dict()`). It replaces
    # [EN] "store the place coordinates". Why: coordinates are **this composition**, and storing them
    # [EN] only fossilises the layout of that moment -- measured, the old `锚定.json` locks exactly
    # [EN] nine wrong coordinates (door outside, well as a room, floor 2 on the courtyard). The
    # [EN] program is **what this place looks like**, solved deterministically into geometry, so one
    # [EN] program always yields one plan (continuity for free) and one change fixes the whole plan.
    # [EN] When non-empty the renderer takes the `roomplan` path; when empty **the old path runs
    # [EN] unchanged** (old cache / not configured / solve failed all land here).
    program: dict = field(default_factory=dict)

    def by_name(self) -> dict[str, Place]:
        return {p.name: p for p in self.places}

    def to_dict(self) -> dict:
        return {
            'source': self.source,
            'caption': self.caption,
            'kind': self.kind,
            'frame': self.frame,
            'places': [{'name': p.name, 'x': p.x, 'y': p.y, 'shape': p.shape,
                        'size': p.size, 'short': p.short, 'room': p.room,
                        'note': p.note}
                       for p in self.places],
            'links': list(self.links),
            'water': list(self.water),
            '水系类型': self.water_kind,
            'walls': list(self.walls),
            '程序': dict(self.program or {}),
        }

    @classmethod
    def from_dict(cls, data: Any) -> 'Layout | None':
        """从 JSON 读回（**宽容**：坏字段丢单个，不整体失败）。

        ⚠ `places` 必须是**列表**。给它一个字符串会被当成可迭代对象、
        逐个字符变成"地点"（`'abc'` → 三个叫 a/b/c 的地点）——
        缓存文件被写坏、或者人手改成 `"places": "茶肆"` 时就是这个下场。
        
                English:
        Read back from JSON (**lenient**: bad fields drop individually, no whole failure).
                ⚠ `places` must be a **list**. Giving it a string makes it treated as an iterable,
                turning each character into a "place" (`'abc'` → three places named a/b/c) --
                this is what happens when the cache file gets corrupted or someone hand-edits it to `"places": "茶肆"`.
        """
        if not isinstance(data, dict):
            return None
        lay = cls(source=str(data.get('source') or 'simple'),
                  caption=str(data.get('caption') or '')[:12],
                  # ★ `kind` / `frame` 也要读回来：老缓存里没有这两个键 → 空串，
                  #   渲染时按"不是室内图"处理（与从前的行为一致）。
                  # [EN] ★ `kind` / `frame` must be read back too: an old cache has neither key -> empty
                  # [EN] string, and rendering treats it as "not an indoor map" (same as before).
                  kind=str(data.get('kind') or '')[:8],
                  frame=str(data.get('frame') or '')[:16])
        raw_places = data.get('places')
        if isinstance(raw_places, (list, tuple)):
            for p in raw_places:
                pl = _as_place(p)
                if pl is not None:
                    lay.places.append(pl)
        raw_links = data.get('links')
        if isinstance(raw_links, (list, tuple)):
            lay.links = [x for x in (_as_link(l) for l in raw_links) if x]
        lay.water = _as_polyline(data.get('water'))
        # ★ 2026-10-27：水系类型（`river`/`lake`/`coast`，也认中文 河/湖/海）。
        #   ⚠ 这里**不做合法性校验**：判"这个值认不认"只许在 `scalemap.water_kind()` 里做一处
        #     （两处各判一套，规则一改就漂）。读进来什么就存什么。
        # [EN] ★ 2026-10-27: the water kind (`river`/`lake`/`coast`, Chinese 河/湖/海 also accepted).
        # [EN] ⚠ No validation here: deciding "is this value acceptable" lives **only** in
        # [EN] `scalemap.water_kind()`; two places judging it would drift the moment the rule changes.
        lay.water_kind = str(data.get('水系类型') or data.get('water_kind') or '').strip()
        lay.walls = _as_polyline(data.get('walls'))
        # ★ 2026-10-26：任务书（有就走新解算；没有就老路）
        _prog = data.get('程序')
        lay.program = dict(_prog) if isinstance(_prog, dict) else {}
        # ⚠ 有任务书时**允许 places 为空**：任务书本身就够解出整张图，
        #   不再要求"必须先有一份点表"（那正是老模型的产物）。
        # [EN] With a program, **empty places is allowed**: the program alone is enough to solve the
        # [EN] whole plan, so a point table (the old model's output) is no longer a precondition.
        return lay if (lay.places or lay.program) else None

    def signature(self) -> str:
        """地点与摆位的指纹 —— 用来判断"这份缓存还作不作数"。
                English:
        Fingerprint of places and placement -- used to decide "is this cache still valid".
        """
        return '|'.join(f'{p.name}@{p.x:.3f},{p.y:.3f}' for p in self.places)


# ══════════════════════════════════════════════════════════════════════
#  归一化 / 校验（AI 给的东西**一律不可信**，全部要过一遍）
# [EN] Normalization / validation (anything the AI gives is **never trustworthy**, all of it must be
# [EN] run through)
# ══════════════════════════════════════════════════════════════════════
def _num(v: Any, default: float = 0.5) -> float:
    """把任意东西变成 0~1 的浮点。夹取（AI 经常给 1.2、-3 或者 "0.7"）。
        English:
    Turn anything into a 0~1 float. Clamp (AI often gives 1.2, -3, or "0.7").
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return min(1.0, max(0.0, f))


def _pick(v: Any, allowed: tuple, default: str) -> str:
    s = str(v or '').strip()
    for a in allowed:
        if a and a in s:                 # "小屋" → 屋；"中等" → 中
        # [EN] "hut" → 屋; "medium" → 中
            return a
    return default


def _as_place(p: Any) -> Place | None:
    """一条地点规格 → `Place`；连名字都没有就丢掉。
        English:
    One location spec → `Place`; discard it if it doesn't even have a name.
    """
    if isinstance(p, str):
        return Place(name=p.strip()[:12]) if p.strip() else None
    if not isinstance(p, dict):
        return None
    name = str(p.get('名称') or p.get('name') or '').strip()[:12]
    if not name:
        return None
    return Place(
        name=name,
        x=_num(p.get('x')),
        y=_num(p.get('y')),
        shape=_pick(p.get('形') or p.get('shape'), SHAPES, '屋'),
        size=_pick(p.get('大小') or p.get('size'), SIZES, '中'),
        short=str(p.get('简称') or p.get('short') or '').strip()[:3],
        # ★ 2026-10-12：陈设归哪间房（AI 可填、可空 —— 空的由 `plan_audit.solve` 几何兜底）
        # ⚠ `房间` 的名字**不在**地点白名单里（它是房间名），所以这里**不做 `_pick` 过滤**。
        # [EN] ★ 2026-10-12: which room a fixture belongs to (the AI may fill it or leave it --
        # [EN] `plan_audit.solve` falls back to geometry).
        # [EN] ⚠ The `房间` value is **not** in the location whitelist (it is a room name), so it is
        # [EN] **not** passed through `_pick`.
        room=str(p.get('房间') or p.get('room') or '').strip()[:12],
        note=str(p.get('说明') or p.get('note') or '').strip()[:20],
    )


def _as_link(l: Any) -> dict | None:
    """一条通路。**两种形状都要认**（2026-10-07 补的第二种）：

      · `{"从": "甲", "到": "乙", "形": "路"}`  —— `ai_layout` 那个提示词给的；
      · `["甲", "乙"]`                          —— 「美术 · 当天地图」给的。

    ⚠ 只认字典形状时，第二种会被**静默丢掉** —— 表现是"地图上地点画出来了，
      但一条路都没有"（连线没了，几处地方看着彼此无关）。实测就是这么发现的：
      当天地图那版提示词写的是 `[["甲","乙"]]`，`通路` 恒为空。
      **提示词换了形状，解析这边就得跟着认** —— 不然是悄悄少东西。
    
        English:
    One path. **Both shapes must be recognized** (the second kind added 2026-10-07):
          · `["甲", "乙"]`                          —— given by "artwork · day map".
        ⚠ When only the dict shape is recognized, the second kind gets **silently dropped** —— the symptom is "locations on the map are drawn,
          but there isn't a single path" (connections gone, several places look unrelated to each other). This is how it was found in practice:
          the day-map version of the prompt wrote `[["甲","乙"]]`, and `通路` was always empty.
          **When the prompt changes shape, the parsing side must recognize it too** —— otherwise things go quietly missing.
    """
    if isinstance(l, (list, tuple)) and len(l) >= 2:
        a = str(l[0] or '').strip()[:12]
        b = str(l[1] or '').strip()[:12]
        kind = _pick(l[2] if len(l) > 2 else None, LINKS, '路')
        return {'a': a, 'b': b, 'kind': kind} if (a and b) else None
    if not isinstance(l, dict):
        return None
    a = str(l.get('从') or l.get('a') or '').strip()[:12]
    b = str(l.get('到') or l.get('b') or '').strip()[:12]
    if not (a and b):
        return None
    return {'a': a, 'b': b,
            'kind': _pick(l.get('形') or l.get('kind'), LINKS, '路')}


def _as_polyline(v: Any, *, max_pts: int = 16) -> list[list[float]]:
    """一串点（河/墙）：[[x,y], …]。不到 2 个点的丢掉（画不出来）。
        English:
    A string of points (river/wall): [[x,y], …]. Discard those with fewer than 2 points (can't be
    drawn).
    """
    if not isinstance(v, (list, tuple)):
        return []
    out: list[list[float]] = []
    for pt in v[:max_pts]:
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            out.append([_num(pt[0]), _num(pt[1])])
        elif isinstance(pt, dict):
            out.append([_num(pt.get('x')), _num(pt.get('y'))])
    return out if len(out) >= 2 else []


def normalize(raw: Any, names: list[str], *, source: str = 'ai',
              pad_missing: bool = True) -> Layout:
    """把 AI 的原始答复归一化成 `Layout`。

    三件事，缺一不可：
      ① **夹取坐标**（AI 会给 1.2 / -3 / 字符串）；
      ② **只留设定里真的有的地点** —— 模型很爱顺手编几个"隔壁的客栈"，
         那些名字在设定里不存在，画上去就是**编的**（这个项目最忌讳）；
      ③ **补齐漏掉的地点**：模型经常只画它觉得重要的那几个。
         漏掉的用确定性位置**补在空白处**，宁可不精确也不能少。

    ⚠ `pad_missing=False` 是给**当天地图**用的（2026-10-07）：那种图上
      "少"是对的 —— 今天这场戏就发生在三处，画三处才对；一旦补齐，
      全书地点全回来了，又变回用户说的"周围都是小说"。
    
        English:
    Normalize AI's raw reply into a `Layout`.
        Three things, none can be missing:
          ① **Clamp coordinates** (AI will give 1.2 / -3 / strings);
          ② **Keep only locations that actually exist in the setting** —— the model loves to casually invent a few "neighboring inns",
             whose names don't exist in the setting, and drawing them is **fabrication** (the biggest taboo in this project);
          ③ **Fill in missing locations**: the model often only draws the few it considers important.
             Fill the missing ones with deterministic positions **in blank areas**; better imprecise than missing.
        ⚠ `pad_missing=False` is for the **day map** (2026-10-07): on that kind of map
          "fewer" is correct —— today's scene takes place in three places, so drawing three is right; once you pad,
          all the book's locations come back, and it turns back into what the user called "surrounded by novel".
    """
    names = [str(n).strip() for n in (names or []) if str(n).strip()]
    allowed = set(names)
    lay = Layout(source=source)

    got: list[Place] = []
    if isinstance(raw, dict):
        for p in (raw.get('地点') or raw.get('places') or []):
            pl = _as_place(p)
            if pl is None:
                continue
            if allowed and pl.name not in allowed:
                continue                    # ② 模型编出来的地点，丢掉
                # [EN] ② Locations the model made up, drop them
            got.append(pl)
    elif isinstance(raw, list):             # 有的模型直接给数组
    # [EN] Some models just give an array
        for p in raw:
            pl = _as_place(p)
            if pl is not None and (not allowed or pl.name in allowed):
                got.append(pl)

    seen = {p.name for p in got}
    lay.places = got[:MAX_PLACES]

    # ③ 补齐 + 去重（重名只留第一个）
    # [EN] ③ Fill in + dedupe (for duplicates keep only the first)
    missing = [n for n in names if n not in seen] if pad_missing else []
    if missing and len(lay.places) + len(missing) <= MAX_PLACES:
        for i, n in enumerate(missing):
            lay.places.append(Place(name=n, **_spare_slot(lay.places, i)))

    if isinstance(raw, dict):
        lay.caption = str(raw.get('题记') or raw.get('caption') or '').strip()[:12]
        links = [_as_link(l) for l in (raw.get('通路') or raw.get('links') or [])]
        keep = {p.name for p in lay.places}
        lay.links = [l for l in links
                     if l and l['a'] in keep and l['b'] in keep]
        lay.water = _as_polyline(raw.get('水系') or raw.get('water'))
        # 水系类型：与 `from_dict` 同一套键名（**不在这里校验**，见那里的注释）
        # [EN] Water kind: same keys as `from_dict` (no validation here; see the note there)
        lay.water_kind = str(raw.get('水系类型') or raw.get('water_kind') or '').strip()
        lay.walls = _as_polyline(raw.get('院墙') or raw.get('walls'))
        # ★★★ **`kind` / `frame` 要一起读回来**（2026-10-12 用户报"中间还是有红点"的根因）。
        #   用户原话：「现在的小地图中间都有一个红点 这个去掉 看不见其他元素了」。
        #   查到底：上一轮加的室内语义**每次回读都会丢** —— `world.atlas.Atlas.from_dict()`
        #   读局部/室内层走的是**这个函数**，而这里以前压根没读 `kind` / `frame`。
        #   于是文件里明明写着 `kind: 室内`，读回内存却成了空串 ⇒ 渲染层按
        #   "不是室内图"处理 ⇒ 整座楼又变回**中间一个红点**（正是用户看到的现象）。
        #   ⚠ 这类失效**不报错**：文件的键都在、`to_dict()` 也写得对，
        #     只有"读回来之后"是错的。判据 `verify_map_detail` 的 C 组钉住往返一致。
        # [EN] ★★★ **`kind` / `frame` must be read back too** (the root cause of the user's
        # [EN] 2026-10-12 report "there is still a red dot in the middle").
        # [EN]   User's exact words: "every minimap now has a red dot in the middle; remove it, it
        # [EN]   hides the other elements."
        # [EN]   Traced to the bottom: the indoor semantics added last round were **lost on every
        # [EN]   read-back** -- `world.atlas.Atlas.from_dict()` reads the local/indoor layers through
        # [EN]   **this function**, and it never read `kind` / `frame`.
        # [EN]   So although the file clearly said `kind: 室内`, reading it back into memory gave an
        # [EN]   empty string ⇒ the renderer treated it as "not an indoor map" ⇒ the whole building
        # [EN]   turned back into **a red dot in the middle** (exactly what the user saw).
        # [EN]   ⚠ This kind of failure **does not error**: the file's keys are all there and
        # [EN]   `to_dict()` writes them correctly; only "after reading back" is wrong. Group C of
        # [EN]   `verify_map_detail` pins round-trip consistency.
        lay.kind = str(raw.get('kind') or '')[:8]
        lay.frame = str(raw.get('frame') or '')[:16]
    return lay


def day_layout(raw: Any, day_names: list[str], *, here: str = '',
               allow_extra: list[str] | None = None,
               kind_hint: str = '') -> Layout:
    """**当天的那张小地图**：把「美术」给的当天地图归一化成 `Layout`。

    用户 2026-10-07：
    「这个小地图还是不对 周围都是小说 而不是实际地图 请把绘制地图改到
      **导演写完当前的小说之后** 有剧组**美术**根据**当天剧情涉及到的地点**
      进行绘制」

    与 `normalize()` 的两点不同（都是刻意的）：

      ① **不补齐**（`pad_missing=False`）—— 今天涉及三处就画三处。
         补齐会把全书地点拉回来，正好是用户报的那个毛病。
      ② **确保"这里"在图里** —— 人在哪儿必须看得见。模型偶尔会漏掉当前地点，
         那就用确定性位置补在中心偏下（图上那个朱砂点画不出来最丢人）。

    `day_names` = 今天涉及的地点（取自当天剧本的「场」）。**空的话返回 None**：
    没有范围就无从取景，调用方该退回原来的做法（宁可不画当天的图）。

    ★ `allow_extra`（2026-10-08 加）＝ **底图那一层里的名字**（`world/atlas.py`）。
      为什么必须有它：选中**室内**层时，上屏的名字是「堂屋」「后院」这种**房间名**，
      它们**本来就不在 `地点.yaml` 里**。只按 `day_names` 过滤的话，
      模型老老实实照底图抄回来的房间会被**全部滤掉** → 室内图永远是空的。
      （这与"拦编造"不矛盾：编造的名字既不在 `day_names`、也不在底图里。）
    
        English:
    **That small map of the day**: normalize the day map given by "artwork" into a `Layout`.
        User 2026-10-07:
        "This minimap is still wrong, surrounded by novel rather than an actual map. Please change map drawing to
          **after the director finishes writing the current novel**, have the crew's **artwork** draw it based on **the locations involved in today's plot**"
    Two differences from `normalize()` (both intentional):
    ① **No padding** (`pad_missing=False`) —— three places involved today, draw three.
          Padding would pull back all the book's locations, which is exactly the problem the user reported.
             ② **Ensure "here" is on the map** —— where the person is must be visible. The model occasionally misses the current location,
          so fill it with a deterministic position slightly below center (the most embarrassing thing is that cinnabar dot on the map not being drawable).
    `day_names` = locations involved today (taken from the "场" column of today's script). **Return
    None if empty**:
        without a scope there's no way to frame the shot, and the caller should fall back to the original approach (rather not draw the day's map).
    ★ `allow_extra` (added 2026-10-08) = **names in the base map layer** (`world/atlas.py`).
        Why it's necessary: when the **indoor** layer is selected, the names on screen are **room names** like "堂屋", "后院",
          which **are simply not in `地点.yaml`**. If you filter only by `day_names`,
          the rooms the model faithfully copies back from the base map will be **all filtered out** → the indoor map is forever empty.
          (This doesn't contradict "block fabrication": fabricated names are neither in `day_names` nor in the base map.)
        Extract "locations involved today" from **today's script shot breakdown** (the `场` column).
    """
    names = [str(n).strip() for n in (day_names or []) if str(n).strip()]
    if not names:
        return None
    extra = [str(n).strip() for n in (allow_extra or []) if str(n).strip()]
    allow = names + [n for n in extra if n not in names]
    lay = normalize(raw, allow, source='day', pad_missing=False)
    if not lay or not lay.places:
        return None
    h = str(here or '').strip()
    if h and h not in lay.by_name():
        # ★★★ **先想办法把名字对上，别急着补一个点**（2026-10-12）。
        #   当前场景常常是**子地点**（`临河茶肆·堂屋`），布局里写的是**房间名**
        #   （`堂屋`）。以前这里一看"不在图上"就补一个 `Place(h, 0.5, 0.62,
        #   shape='楼', size='大')` —— 于是图上**正中间长出一个又大又红的点**
        #   （渲染那边还会给"当前地点"垫朱砂），把房间全压住。
        #   用户报的「中间都有一个红点 这个去掉 看不见其他元素了」就是它。
        #   对上了就**什么都不用补**：那个房间本来就在图上，朱砂圈会落在它身上。
        # [EN] ★★★ **Try to match the name first; do not rush to add a point** (2026-10-12).
        # [EN]   The current scene is often a **sub-location** (`临河茶肆·堂屋`) while the layout
        # [EN]   writes the **room name** (`堂屋`). Previously, on seeing "not on the map", this
        # [EN]   appended `Place(h, 0.5, 0.62, shape='楼', size='大')` -- so **a large red dot grew
        # [EN]   right in the middle of the map** (the renderer also pads "the current place" with
        # [EN]   cinnabar), pressing onto every room. That is exactly the user's report: "every minimap
        # [EN]   has a red dot in the middle; remove it, it hides the other elements".
        # [EN]   Once matched, **nothing needs adding**: that room is already on the map, and the
        # [EN]   cinnabar ring lands on it.
        matched = resolve_place(lay, h)
        if not matched:
            # 实在对不上（模型漏了这一处房子的名）才补 —— 而且**不补成"楼"**
            # （楼是"整座建筑"，补在中间就是那个红点）；补成"屋"、中号、靠下。
            # [EN] Only when it truly cannot be matched (the model missed this building's name) do we
            # [EN] add one -- and **not as a "building"** (a building in the middle is that red dot);
            # [EN] add it as a "house", medium size, lower down.
            lay.places.append(Place(name=h, x=0.5, y=0.72, shape='屋', size='中',
                                    note='（这里）'))
    _ = h
    lay.caption = lay.caption or '今日'
    # ★★★ 2026-10-26：**档位只有一个来源**（用户：「每次生成的感觉都有一些区别」）。
    #   病根之一是"同一件事两处实现"：存档的档位取**底图那一层的名字**
    #   （`layers[0][0]`，`整体/局部/室内`），而这里按**内容**推（`_looks_indoor`）。
    #   真数据里就有一份 `整体_望江楼.json` 而 `kind` 写着 `室内` ——
    #   存档名与内容打架，下次按名字读回来、渲染按 `kind` 画，两天的图自然不像。
    #   ⇒ 有 `kind_hint`（取景层名）时**一律用它**，没有才按内容推。
    #   ⚠ 这也让 `mapanchor` 的锚定键与存档键一致 —— 锚定分层的意义就是
    #     "室内图与整体图本来就该不一样"，两处档位不同源时锚定会串层。
    # [EN] ★★★ 2026-10-26: **one source for the tier** (the user: "it feels a bit different every
    # [EN] time"). One root cause was the same thing implemented twice: the archive tier came from
    # [EN] **the base-map layer name** while this function derived it from **content**
    # [EN] (`_looks_indoor`). A real file is named `整体_望江楼.json` with `kind` saying `室内` --
    # [EN] the name and the content disagree, so reading it back by name and rendering by `kind`
    # [EN] yields two maps that do not look alike.
    # [EN] => When `kind_hint` (the framing layer name) is given it **always wins**; only without it
    # [EN] do we derive from content.
    # [EN] ⚠ This also aligns `mapanchor`'s anchor keys with the archive keys. Anchors are keyed by
    # [EN] layer precisely because an interior plan and an overall map legitimately differ; two
    # [EN] different tier sources would leak one into the other.
    _hinted = str(kind_hint or '').strip()
    if _hinted:
        lay.kind = _hinted
    # ★★ **空间常识也过一遍**（2026-10-12）：当天的图同样要"有井就有院"。
    #   跟底图用的是**同一份实现**（`apply_space_rules`），不另写一套 ——
    #   两处口径一旦分开，底图上画了院子、当天的图上又没了，那就更糊涂。
    # [EN] ★★ **Spatial common sense runs here too** (2026-10-12): the day's map must satisfy "a well
    # [EN] implies a courtyard" as well.
    # [EN] It shares **one implementation** with the base map (`apply_space_rules`) rather than a second
    # [EN] copy: once the two conventions diverge, the base map draws a courtyard while the day's map
    # [EN] drops it again -- even more confusing.
    apply_space_rules(lay, kind=(lay.kind or ('室内' if _looks_indoor(lay, h) else '局部')),
                      building=_building_of(h) or _building_of(lay.caption))

    # ★★★ 2026-10-26：**同时推一份房间任务书**，跟着这份布局一起存/一起读。
    #
    #   任务书是"这处地方长什么样"的**唯一事实来源**；坐标由 `roomplan.solve()` 现算。
    #   这样：
    #     · 延续性不靠锁坐标 ⇒ 不会像旧 `锚定.json` 那样把错的布局永久固化；
    #     · 美术/模型要改的是任务书（加一间、说清谁挨着谁），**不是坐标**。
    #   ⚠ 已经有了就不覆盖：任务书比"这一次的构图"更权威（与锚定的道理一致）。
    #   ⚠ 失败**不许影响这张图**：任务书是增强项。
    # [EN] ★★★ 2026-10-26: **derive a room program too**, stored and read back with this layout.
    # [EN] The program is the single source of truth for "what this place looks like"; coordinates
    # [EN] are computed by `roomplan.solve()`. So continuity does not rely on freezing coordinates
    # [EN] (which fossilised the wrong layout in the old `锚定.json`), and art/model revisions change
    # [EN] the program, **not** coordinates. ⚠ Do not overwrite an existing one (the program is more
    # [EN] authoritative than this composition). ⚠ Failure must not affect the map.
    try:
        if not lay.program:
            from image_gen import roomplan as _RP
            _names = [p.name for p in lay.places]
            _notes = [p.note for p in lay.places]
            # ⚠ 2026-10-26 实测的真 bug：这里原本写成 `frame or here` —— **`here` 是
            #   "现在人在哪间房"**，不是建筑名。于是 `place` 被填成"堂屋"，而
            #   `program_from_places` 里有一条"名字等于 place ⇒ 这是整栋楼自己、不是房间"，
            #   结果 **当前所在的那间房从图上整个消失**（实测：9 处地点解出来的任务书里
            #   没有堂屋，而堂屋正是那天的开场房间）。用户看到的就是"屋子少了一半"。
            #   ⇒ `place` 只能来自**真的建筑名**：`frame`（美术给的框）或
            #     `caption` 里 `地点·空间` 的 `·` 前半截。取不到就是空 —— 空是安全的
            #     （那条规则只在 place 非空时生效）。
            # [EN] ⚠ Real bug measured 2026-10-26: this read `frame or here`, and **`here` is
            # [EN] "which room the person is in"**, not a building name. So `place` became "堂屋"
            # [EN] and `program_from_places` has the rule "the name equals place => that is the
            # [EN] building itself, not a room", which made **the current room vanish from the map**
            # [EN] (measured: nine places solved into a program with no 堂屋, and 堂屋 was the opening
            # [EN] room). => `place` may only come from a **real building name**: `frame`, or the
            # [EN] part before `·` in `caption`. Empty is safe (that rule needs a non-empty place).
            _bname = str(getattr(lay, 'frame', '') or '') or _building_of(
                str(getattr(lay, 'caption', '') or ''))
            _prog = _RP.program_from_places(_names, _notes, place=_bname)
            if _prog.spaces:
                lay.program = _prog.to_dict()
    except Exception:                                         # noqa: BLE001
        pass
    # ★★★ **Reflection：画完先自审，有问题就修，再审，直到没问题**（2026-10-12 用户点名）──
    #   用户原话：「美术Agent绘制地图的时候要用 **Reflection** 的机制
    #   **绘制之后去审核 如果有问题则修复问题重新绘制 直到没问题**」。
    #   这里做的是**布局层**那一半（数据自洽）：
    #     · 陈设没有可放进去的房间 → 给它补一间（**只加不减**）；
    #     · 有井却没有院子 → 补院子（复用 `apply_space_rules` 背后那同一份空间常识）；
    #     · 房子与院子在布局上就必然相撞 → 把院里的点挪开。
    #   另一半（**画出来对不对**：家具在不在墙内、院子框与房子框重不重叠）归**渲染层**的
    #   `plan_audit.solve()` —— 它按真实画布算，比这里精确。
    #   ⚠ 两层**都要做**：前两轮就是只做了数据层、没做绘制层，用户才会看到
    #     "柜台跑到墙外面"（那是绘制层的事）。
    #   ★ **不调模型**：修复全是确定性的，所以每一轮零成本。
    #   ★ 审核结论写进日志（谁想知道"这轮修了什么"都能查到）。
    # [EN] ★★★ **Reflection: self-audit right after drawing, fix if needed, audit again, until
    # [EN] clean** (named by the user on 2026-10-12) --
    # [EN] The user's exact words: "when the art Agent draws the map it should use **Reflection**:
    # [EN] **after drawing, go and audit it; if there is a problem, fix it, redraw, until there is no
    # [EN] problem**".
    # [EN] What happens here is the **layout-level** half (data self-consistency):
    # [EN] · a fixture with no room to go in -> add one (**only add, never remove**);
    # [EN] · a well without a courtyard -> add the courtyard (reusing the same spatial common sense
    # [EN]   behind `apply_space_rules`);
    # [EN] · the house and courtyard bound to collide in the layout -> move the courtyard points aside.
    # [EN] The other half (**is the drawing right**: is the furniture inside the wall, do the courtyard
    # [EN] and house rectangles overlap) belongs to the **render layer**'s `plan_audit.solve()`, which
    # [EN] computes from the real canvas and is more precise.
    # [EN] ⚠ **Both layers are required**: the previous two rounds did only the data layer and not the
    # [EN] drawing layer, which is why the user saw "the counter ran outside the wall" (a drawing-layer
    # [EN] matter).
    # [EN] ★ **No model call**: every repair is deterministic, so each round is free.
    # [EN] ★ The audit result goes into the log (anyone wondering "what got fixed this round" can look).
    try:
        from image_gen import plan_audit as _PA
        _fixed, _issues = _PA.reflect_layout(lay)
        if _issues:
            _LOG.info('当天地图 · Reflection 修完：%s', _PA.summary(_issues))
    except Exception as e:                                       # noqa: BLE001
        # ⚠ 审核/修复**不许**把地图弄没：它是个增强项，出错就照原样返回
        # [EN] ⚠ Auditing/repairing **must not** lose the map: it is an enhancement; on error return
        # [EN] the map as-is
        _LOG.warning('当天地图 · 几何审核失败（图照原样用）：%r', e)
    return lay


def _building_of(name: str) -> str:
    """从「地点·空间」这种写法里取出**整座建筑的名**（`临河茶肆·前厅` → `临河茶肆`）。

    没写 `·` 就返回空串 —— **不猜**（猜出来的建筑名会变成图上一个凭空多出来的框）。
    [EN] Take the **whole building's name** out of the "place·space" style (`临河茶肆·前厅` -> `临河茶肆`).
    [EN] Return an empty string when there is no `·` -- **do not guess** (a guessed building name turns
    [EN] into a frame appearing out of nowhere on the map).
    """
    s = str(name or '').strip()
    if '·' not in s:
        return ''
    head = s.split('·')[0].strip()
    return head if 1 <= len(head) <= 8 else ''


#: **只用来认"整栋楼叫什么"的后缀字**（`临河楼` / `藏经阁` / `兰若寺`）。
#:
#: ★★★ 2026-10-27（重绘现有地图时抓到的真 bug）：室内图上"这栋楼叫什么"原来是
#:   `frame or caption` —— 而 `caption` 是**河边题记**（实测是"壶在"，一个不成词的碎片），
#:   两个语义完全不同的字段互相兜底，于是图上楼名位置写着"壶在"，真正的楼名一个字都没有。
#:   ⚠ 两处渲染器（大地图 `floorplan`、小地图 `minimap`）**都犯过这个错**，
#:     所以判法放在这里（数据层）**只有一份**，谁画都调它。
#:
#: ⚠ 这张表刻意很短，且**不收** `院/屋/房/厅/室/间/门/店`：那些正是房间自己的字，
#:   收进来会让"后院"变成楼名。
# [EN] Suffix characters for recognising **the whole building's name** (`临河楼`, `藏经阁`,
# [EN] `兰若寺`). ★★★ 2026-10-27 (a real bug found while re-drawing the live maps): the indoor plan's
# [EN] "what is this building called" used to be `frame or caption` -- but `caption` is a **riverside
# [EN] inscription** (measured: "壶在", a meaningless fragment), so two fields with entirely different
# [EN] meanings stood in for each other and the name band read "壶在" while the real name appeared
# [EN] nowhere. ⚠ **Both** renderers (`floorplan` and `minimap`) made this mistake, so the rule lives
# [EN] here (data layer) as a **single copy** and both call it.
# [EN] ⚠ The table is deliberately short and **excludes** 院/屋/房/厅/室/间/门/店: those belong to rooms,
# [EN] and including them turns 后院 into a building name.
BLDG_SUFFIX = ('楼', '阁', '塔', '寺', '观', '庵', '庙', '祠', '邸', '墅',
               '苑', '舫', '榭', '轩', '斋', '庄', '馆', '殿', '宫', '府')


def bldg_name(lay, places=None) -> str:
    """这张图**画的是哪一栋楼**（判不出就返回空串 —— 空是安全的）。

    ★ 三处来源，按可靠性排序，一处命中就返回：
      ① `frame` —— 上层明确给的"框上的建筑名"，最硬；
      ② 任务书里的 `地点` —— 那份任务书就是按这个名字解算的；
      ③ 地点里**以后缀字结尾**的那一处，且**只命中一处**时才用
         （两处都像楼 = 判断不了，宁可不写）。
    ★ 绝不回落到 `caption`：那是河边题记，不是楼名（2026-10-27 的 bug 就是这么来的）。
    [EN] Which building this map depicts (empty when unknown -- empty is safe). ★ Three sources by
    [EN] reliability: `frame`, the program's `地点`, and the single place ending with a building suffix
    [EN] (only when **exactly one** matches -- two candidates means "cannot tell", so write nothing).
    [EN] ★ Never fall back to `caption`: that is a riverside inscription, not a building name (exactly
    [EN] how the 2026-10-27 bug happened).
    """
    nm = str(getattr(lay, 'frame', '') or '').strip()
    if nm:
        return nm
    prog = getattr(lay, 'program', None) or {}
    if isinstance(prog, dict):
        nm = str(prog.get('地点') or '').strip()
        if nm:
            return nm
    ps = list(places if places is not None else (getattr(lay, 'places', None) or []))
    hits = []
    for p in ps:
        n = str(getattr(p, 'name', '') or '').strip()
        if len(n) >= 2 and n.endswith(BLDG_SUFFIX):
            hits.append(n)
    return hits[0] if len(hits) == 1 else ''


def _looks_indoor(lay: 'Layout', here: str = '') -> bool:
    """这一天是不是**在屋里演**（决定要不要把整座楼框起来）。

    判据只用两件事，都**确定**、不花 token：① 有哪一处的名字是屋里空间；
    ② "现在人在哪儿"落在屋里。有一条成立就算。
    [EN] Whether today plays **indoors** (decides whether to frame the whole building).
    [EN] Only two things are used, both **deterministic** and free of tokens: ① some place's name is an
    [EN] indoor space; ② "where the person is now" lands indoors. Either one suffices.
    """
    try:
        from world import spatial as _SP
    except Exception:                                            # noqa: BLE001
        return False
    if _SP.space_of(here) == _SP.SPACE_IN:
        return True
    return any(_SP.space_of(p.name) == _SP.SPACE_IN
               for p in (getattr(lay, 'places', None) or []))


def apply_space_rules(lay, *, kind: str = '室内', building: str = '') -> list[str]:
    """把**空间常识**落到一份 `Layout` 上（用户 2026-10-12 点名的那件事）。

    做三件事，**只加不减**：

    1. **打标记**：`lay.kind` = 这一层是哪一层；`lay.frame` = 整座建筑的名字
       （室内层才有 —— 小地图据此把整座楼**框起来**，而不是在中间点一个红点）。
    2. **补院子**：有井（或别的屋外器物）却没有院子 → 补一个院子，
       并把院子摆在**井的旁边**（图上挨着才看得出"井在院里"）。
    3. **报违规**：修完还剩下的（`重名`/`器物入屋`/`房间出屋`）作为说明返回，
       由调用方记进日志 —— **不悄悄改名字，也不假装没这回事**。

    ⚠ 放在**这一层**（`image_gen`）而不是 `world/`：底图（`world.atlas`）与当天的图
      （`day_layout`）都要用，而 `world.atlas` 反过来要 import 本模块的 `Layout` ——
      放这边才不成环。`world.atlas.apply_space_rules` 是它的**同名转发**。

        English:
    Apply **spatial common sense** to one `Layout` (the matter the user named on 2026-10-12).
        Three things, all **additive**: tag `kind`/`frame`; add the missing courtyard; report the
        remaining violations instead of hiding them.
        ⚠ It lives **here** (`image_gen`) rather than in `world/` because both the base map
        (`world.atlas`) and the day's map (`day_layout`) need it, while `world.atlas` in turn imports
        this module's `Layout` -- only this side avoids a cycle. `world.atlas.apply_space_rules` is a
        **same-named forwarder** to it.
    """
    notes: list[str] = []
    if lay is None:
        return notes
    try:
        from world import spatial as SP
    except Exception:                                            # noqa: BLE001
        return notes

    lay.kind = str(kind or '')
    if str(kind) == '室内':
        lay.frame = str(building or '')[:16]

    names = [str(getattr(p, 'name', '') or '') for p in (getattr(lay, 'places', None) or [])]
    fixed, how = SP.repair(names, kind=kind, building=building)
    notes += how
    if fixed != names:
        by_name = {p.name: p for p in lay.places}
        outdoor = [p for p in lay.places if SP.is_outdoor_object(p.name)]
        base = outdoor[0] if outdoor else None
        bx = float(getattr(base, 'x', 0.5) or 0.5) if base is not None else 0.5
        by = float(getattr(base, 'y', 0.5) or 0.5) if base is not None else 0.6
        nx = bx - 0.16 if bx > 0.55 else bx + 0.16
        rebuilt: list[Place] = []
        for nm in fixed:
            p = by_name.get(nm)
            if p is None:
                p = Place(name=nm, x=min(0.9, max(0.1, nx)),
                          y=min(0.88, max(0.12, by)), shape='院', size='大',
                          note='有井就有院（空间常识补的）')
            rebuilt.append(p)
        lay.places = rebuilt
        for p in lay.places:
            if SP.is_yard(p.name) and not p.short:
                p.short = '院子'

    for v in SP.audit([p.name for p in (lay.places or [])], kind=kind):
        notes.append(v.line())
    return notes


def resolve_place(lay: 'Layout', name: str) -> str:
    """把「现在人在哪儿」落到**这份布局里真的有的那个名字**上（落不到就返回空串）。

    ★★★ 为什么必须有这一步（2026-10-12，用户报的"中间一个红点"的**第二个**根因）：
      当前场景经常写成**子地点**（`临河茶肆·堂屋`、`云来客栈·前厅`），
      而布局里的名字是**房间名**（`堂屋`）。以前两边各写各的：

        · `day_layout` 发现 `here` 不在图上 → **补一个 `Place('临河茶肆·堂屋')`
          摆在正中间（`x=0.5, y=0.62`）、字形 `楼`、大小 `大`**；
        · 渲染那边又给"当前地点"垫一圈**朱砂**。

      两件事叠在一起，屏幕上就是**正中间一个又大又红的点**，
      把周围的房间全压住了 —— 用户的原话「现在的小地图中间都有一个红点
      这个去掉 **看不见其他元素了**」。

      ⚠ 而且它还是个**假地点**：`堂屋` 已经在图上了，再画一个"临河茶肆·堂屋"
        等于同一个房间画了两遍。所以正确做法不是"补一个点"，而是
        **把名字对上**（对上之后朱砂圈自然落在那一间上）。

    匹配三步（越来越松，都**不编名字**）：完全相等 → 取 `·` 后半截 →
    互相包含。都落不到才返回空串，由调用方决定怎么办。
    
        English:
    Map "where the person is now" onto **the name that really exists in this layout** (returns an
    empty string when it cannot).
        ★★★ Why this step is indispensable (2026-10-12, the **second** root cause of the user's
        reported "a red dot in the middle"):
          the current scene is often written as a **sub-location** (`临河茶肆·堂屋`, `云来客栈·前厅`),
          while the layout's names are **room names** (`堂屋`). The two sides used to disagree:
        · `day_layout` found `here` missing from the map -> **appended a
          `Place('临河茶肆·堂屋')` dead centre (`x=0.5, y=0.62`), glyph `楼`, size `大`**;
        · the renderer then padded "the current place" with a **cinnabar** ring.
          Stacked together, the screen shows **a large red dot right in the middle**, pressing onto
          every surrounding room -- the user's exact words: "every minimap now has a red dot in the
          middle; remove it, **it hides the other elements**".
        ⚠ It was also a **fake place**: `堂屋` was already on the map, so drawing another
          "临河茶肆·堂屋" drew the same room twice. The right move is therefore not "add a dot" but
          **match the name** (once matched, the cinnabar ring lands on that very room).
        Three matching steps (progressively looser, none **inventing a name**): exact equality ->
        the part after `·` -> mutual containment. Only when all fail does it return an empty string,
        leaving the caller to decide.
    """
    h = str(name or '').strip()
    if not h or lay is None:
        return ''
    by = {str(getattr(p, 'name', '') or ''): p for p in (getattr(lay, 'places', None) or [])}
    if not by:
        return ''
    if h in by:
        return h
    tail = h.split('·')[-1].strip()
    if tail and tail in by:
        return tail
    # 互相包含（"云来客栈堂内" ↔ "堂屋" 落不到；"堂内" ↔ "茶堂檐下" 落得到）
    # [EN] Mutual containment ("云来客栈堂内" <-> "堂屋" fails; "堂内" <-> "茶堂檐下" works)
    for cand in (h, tail):
        if not cand or len(cand) < 2:
            continue
        hits = [n for n in by if n and (n in cand or cand in n)]
        if hits:
            return max(hits, key=len)
    return ''


def day_names_from_beats(beats: list[dict], *, extra: str = '') -> list[str]:
    """从**当天剧本的分拍**里取出"今天涉及的地点"（`场` 那一栏）。

    ⚠ **2026-10-08 起界面不再用它** —— 换成 `places_in_day()`。原因很实在：
      分拍的「场」根本不是干净的地名，而是**场景短语**。真实数据长这样：
      `临河茶肆堂内·雨夜·柜台前`（12 字，被下面那条长度上限丢掉）、
      `同夜·侧案旁` / `茶堂檐下`（楼内位置，不是地图上的地点）。
      于是"今天涉及的地点"要么丢了、要么混进一堆不是地点的东西。
      它现在只留着给旧判据用，**别再拿它当选景来源**。

    去重但**保持出现顺序**（第一拍先到的排前面 —— 那正是图上的"先后"）。
    空白的、超过 8 个字的（那是句话不是地名）都不要。
    `extra`（通常是"现在人在哪儿"）总是排在最前。
    
        English:
    ⚠ **As of 2026-10-08 the UI no longer uses it** —— replaced by `places_in_day()`. The reason is
    quite concrete:
        the shot breakdown's "场" is not a clean place name at all, but a **scene phrase**. Real data looks like this:
          So "the locations involved today" either got dropped or got mixed in with a bunch of things that aren't locations.
          It is now kept only for the old criteria; **do not use it as a source for scene selection again**.
        Deduplicate but **preserve order of appearance** (the one that arrives first in the first beat comes first — that is exactly the "order" on the map).
        Drop blank ones and ones longer than 8 characters (that's a sentence, not a place name).
        `extra` (usually "where the person is now") is always placed first.
    """
    out: list[str] = []
    for x in [extra] + [str((b or {}).get('场') or '') for b in (beats or [])]:
        n = str(x or '').strip()
        if not n or len(n) > 8 or n in out:
            continue
        out.append(n)
    return out


#: 一份剧本片段里最多看多少字（防着某天分拍写成长文时匹配变慢）
# [EN] : Max characters to read from one script fragment (to guard against matching getting slow if
# [EN] someone writes a long text when splitting scenes one day)
_MATCH_CHARS = 4000


def places_in_day(beats: list[dict], known: list[str], *,
                  extra: str = '') -> list[str]:
    """**今天的故事到底发生在哪几处** —— 拿设定里的地点名去当天剧本里找。

    用户 2026-10-08：
    「小地图上主角所在的那一处旁边，画着一串**世界层级**的名字（各界、各域）；用户说「这些不是真实的地名」，要求美术画图
      **只根据当前发生的故事所在的地点**画图 而不是根据整本小说设定画图」

    ★★ 这一条是本模块取景的**唯一正确姿势**，与旧做法有本质区别：

    | | 旧做法 | 这里 |
    |---|---|---|
    | 范围来自 | **整本设定的地点表**（`地点.yaml` 里 7 个"界"全上） | **当天剧本的正文**，拿设定名去**匹配** |
    | 「场」怎么用 | 直接当地名（`临河茶肆堂内·雨夜·柜台前` 太长被丢；`侧案旁` 不是地点也被当成地点） | 只当**文本**，从中找出真的出现过的设定地名 |
    | 结果 | 进运行界面时画出一张全书总图 | 今天戏在哪几处就画哪几处 |

    匹配范围**只看「场 / 发生 / 推进」三栏**，刻意**不看当天故事全文**：
    故事正文里会出现"他想起雾泽的事"这类**提及**，那不是"戏发生在那儿"。

    `extra`（当前场景）永远排最前 —— "人在哪儿"是"当前故事所在地点"里最硬的一个。
    **一处都没有**时返回 `[extra]`（如果有），否则空。
    
        English:
    **Which places does today's story actually take place in** — take the place names from the
    settings and search today's script for them.
        User 2026-10-08:
        "Next to the spot where the protagonist is on the minimap, a string of **world-tier** names is drawn (each realm, each domain); the user said "these are not real place names" and asked the artist to draw
12.       **only based on the locations where the currently occurring story takes place** rather than based on the entire novel's settings."
          **only based on the locations where the currently occurring story takes place** rather than based on the entire novel's settings."
        ★★ This one is the **only correct posture** for scene selection in this module, and is fundamentally different from the old approach:
        | | Old approach | Here |
        |---|---|---|
        | Scope comes from | **The location table of the entire settings** (all 7 "realms" in `地点.yaml`) | **The body text of today's script**, matched against the setting names |
        | How "scene" is used | Treated directly as place names (`临河茶肆堂内·雨夜·柜台前` is too long and gets dropped; `侧案旁` is not a location but is treated as one) | Treated only as **text**, from which the setting place names that actually appear are found |
        | Result | When entering the run UI, a full-book overview map is drawn | Draw only the places today's drama takes place in |
        Matching scope **only looks at the three columns "场 / 发生 / 推进"**, deliberately **not looking at the full text of today's story**:
        The story body will contain **mentions** like "he recalled the matter of 雾泽", which is not "the drama happens there".
        `extra` (current scene) is always placed first — "where the person is" is the hardest one among "the locations of the current story".
        When **there is not a single place**, return `[extra]` (if present), otherwise empty.
    """
    names = [str(n).strip() for n in (known or []) if str(n).strip()]
    here = str(extra or '').strip()
    if not names:
        return [here] if here else []
    blobs: list[str] = []
    for b in (beats or []):
        if not isinstance(b, dict):
            continue
        for k in ('场', '发生', '推进'):
            blobs.append(str(b.get(k) or ''))
    text = '\n'.join(blobs)[:_MATCH_CHARS]
    hits: list[tuple[int, str]] = []
    for n in names:
        i = text.find(n)
        if i >= 0:
            hits.append((i, n))
    hits.sort(key=lambda x: x[0])           # 按**剧情里出现的先后**排（那就是图上的先后）
    # [EN] Order by **order of appearance in the story** (that is the order on the map)
    out = [n for _i, n in hits]
    if here:
        if here in out:
            out.remove(here)
        out.insert(0, here)                 # 「这里」永远第一
        # [EN] "here" is always first
    return out


def here_only(name: str, *, note: str = '') -> 'Layout | None':
    """**只画当前这一处** —— 小地图最后的兜底（当天地图还没画出来时用它）。

    为什么兜底是"一处"而不是"全书总图"（2026-10-08 用户第二次点名这个毛病）：

      · `local_view()` 按**设定里的通路**取景，可那通路是 AI 摆位时**编的关系**
        （`{"从": "临河茶肆", "到": "雾泽"}`）—— 于是"附近"又成了"界"；
      · 全书总图更糟：把 `地点.yaml` 里 7 个世界层级名一次全摆上屏。

    用户要的是「**只根据当前发生的故事所在的地点**画图」。图还没画出来的时候，
    唯一能确定"当前故事所在地点"的就是**当前场景**。所以画它一处，并让小字
    照实说"今天这张图还没出来"。**宁可一张小图，也不画一张错的图。**

    返回 `None`（`name` 为空）时，调用方按"还不知道你在哪"处理。
    
        English:
    **Draw only the current place** — the final fallback of the minimap (used when today's map has
    not been drawn yet).
        Why the fallback is "one place" rather than "a full-book overview map" (2026-10-08, the second time the user called out this problem):
          · `local_view()` selects the scene by the **paths in the settings**, but those paths are **relations made up** by the AI when placing positions
33.     (`{"从": "临河茶肆", "到": "雾泽"}`) — so "nearby" again becomes a "realm";
          · A full-book overview map is even worse: it puts all 7 world-tier names from `地点.yaml` on screen at once.
        What the user wants is "**draw only based on the locations where the currently occurring story takes place**". When the map has not been drawn yet,
        the only thing that can determine "the location of the current story" is **the current scene**. So draw that one place, and let the small text
        truthfully say "today's map is not out yet". **Better a small map than a wrong map.**
        When returning `None` (`name` is empty), the caller handles it as "don't know where you are yet".
    """
    n = str(name or '').strip()
    if not n:
        return None
    return Layout(source='here', places=[
        Place(name=n, x=0.5, y=0.55, shape='屋', size='大',
              note=str(note or '')[:20])])



def _spare_slot(existing: list[Place], i: int) -> dict:
    """给"补进来的地点"找一个**不压住别人**的位置（沿边排一圈）。
        English:
    Find a position for "newly added locations" that **does not cover others** (arrange them in a
    ring along the edge).
    """
    n = max(1, len(existing) + 1)
    ang = (i / max(1, n)) * math.tau
    cx = 0.5 + 0.34 * math.cos(ang)
    cy = 0.5 + 0.32 * math.sin(ang)

    def _far(x: float, y: float) -> bool:
        return all((p.x - x) ** 2 + (p.y - y) ** 2 > 0.012 for p in existing)

    for k in range(12):                     # 撞了就转一点再试
    # [EN] If it collides, rotate a bit and try again
        x = min(0.92, max(0.08, cx + 0.05 * math.cos(ang + k * 0.5)))
        y = min(0.88, max(0.12, cy + 0.05 * math.sin(ang + k * 0.5)))
        if _far(x, y):
            return {'x': round(x, 3), 'y': round(y, 3)}
    return {'x': round(min(0.92, max(0.08, cx)), 3),
            'y': round(min(0.88, max(0.12, cy)), 3)}


# ══════════════════════════════════════════════════════════════════════
#  兜底：不靠 AI 的确定性布局
# [EN] Fallback: deterministic layout without relying on AI
# ══════════════════════════════════════════════════════════════════════
def simple_layout(names: list[str], *, notes: list[str] | None = None) -> Layout:
    """没有 AI（或 AI 失败）时的排布：**沿一条"主路"铺开**。

    为什么不是网格：网格看着像表格，完全不像一张地图；
    沿一条略弯的主路排开，至少**有"这是一条街/一条河"的样子**，
    而且顺序跟设定里写的顺序一致（`地点.yaml` 通常按场景出场顺序写）。

    ⚠ 这是**兜底**，不是"AI 画得不好时的近似" —— 界面上会照实说明。
    
        English:
    Layout when there is no AI (or the AI fails): **spread out along a single "main road"**.
        Why not a grid: a grid looks like a table, not like a map at all;
        spreading along a slightly curved main road at least **looks like "this is a street / a river"**,
        and the order matches the order written in the settings (`地点.yaml` is usually written in scene appearance order).
        ⚠ This is a **fallback**, not an "approximation for when the AI draws poorly" — the UI will truthfully state this.
    """
    names = [str(n).strip() for n in (names or []) if str(n).strip()]
    notes = list(notes or [])
    n = len(names)
    lay = Layout(source='simple')
    if n == 0:
        return lay
    for i, nm in enumerate(names[:MAX_PLACES]):
        # 单数时居中；多数时从左上往右下沿一条弧铺开
        # [EN] When singular, center it; when plural, spread from top-left to bottom-right along an arc
        t = 0.5 if n == 1 else i / (n - 1)
        x = 0.12 + 0.76 * t
        y = 0.5 + 0.26 * math.sin(t * math.pi * 1.6 - 0.6)
        note = notes[i] if i < len(notes) else ''
        # 说明里带"河/渡/水/桥"的，放到下半（河在下方）—— 便宜但有效的推断
        # [EN] Those whose description contains "river/ferry/water/bridge" go in the lower half (river is at
        # [EN] the bottom) —— a cheap but effective inference
        if re.search(r'河|渡|水|桥|湖|江', note):
            y = min(0.86, y + 0.18)
        lay.places.append(Place(name=nm, x=round(x, 3), y=round(y, 3),
                                note=note[:20]))
        if i:
            lay.links.append({'a': names[i - 1], 'b': nm, 'kind': '路'})
    return lay


# ══════════════════════════════════════════════════════════════════════
#  局部取景：小地图画的是"当前地点附近"，不是全书总图
# [EN] Local framing: the minimap draws "near the current location", not a full-book overview map
# ══════════════════════════════════════════════════════════════════════
#: 局部视图里最多画几处（含当前地点）。
# [EN] : Max number of places to draw in the local view (including the current location).
LOCAL_MAX = 6
#: 至少要凑够几处，否则"附近"就一处、不成画面 —— 不够时按距离补。
# [EN] : Must gather at least this many places, otherwise "nearby" is just one place and it's not a
# [EN] picture —— when not enough, fill in by distance.
LOCAL_MIN = 3
#: 取景后四周留的边距（0~1）。不留的话地点贴着画布边、标签会被裁掉。
# [EN] : Margin left around the edges after framing (0~1). If none is left, places hug the canvas edge
# [EN] and labels get clipped.
LOCAL_PAD = 0.10


def local_view(layout: 'Layout | None', current: str, *,
               max_places: int = LOCAL_MAX,
               min_places: int = LOCAL_MIN) -> 'Layout | None':
    """从整张布局里**只取出当前地点附近那一小块**，并重新铺满画布。

    ⚠⚠ **2026-10-08 起界面不再调用它**（那条接线由 `verify_minimap` 的新判据
       钉住）。用户第二次点名同一个毛病：
       「小地图上主角所在的那一处旁边，画着一串**世界层级**的名字（各界、各域）；用户说「这些不是真实的地名」，要求美术画图
         **只根据当前发生的故事所在的地点**画图 而不是根据整本小说设定画图」

       病根在于它取的是**设定里的通路邻居**，而那份通路是 AI 摆位时**编的关系**
       （`{"从": "临河茶肆", "到": "雾泽"}`）—— 于是"附近"照样是「界」。
       现在改由「**当天剧本匹配出的地点**」（`places_in_day`）决定范围；
       拿不到就当天的图还没出来，退回 `here_only()` 只画当前一处。
       函数留着是因为它的**取景与缩放**那一套仍然是对的（也还有判据在测）——
       只是"范围从哪儿来"这件事它做错了，所以不再上屏。

    用户 2026-10-07
    --------------
    「小地图不对，各界各域那些大名字都出来了，小地图应该是当前这个
      场景下面 主人公所在地方附近的小地图 不是小说的总地图」

    ★ 这是**取景**，不是筛选：不只要挑出附近几处，还要**重新缩放**让它们铺满画布。
      只筛不缩，取出的那一小块会缩在画布一角（外面那圈留白本来是留给"没被选中的
      地点"的），看着像"图没画完"—— 那就等于没修。

    ★★ 挑邻居**以"通路"为准，不是以坐标距离为准**。理由很实在：
      刚做出来时是"按距离补满 6 处"，拿真实数据一试（`临河茶肆` 共 7 处地点）
      仍然画出 6 处 —— 几乎等于总图，用户报的问题**没解决**。
      而按通路取，`临河茶肆` 只连着「里巷」「东馆」，于是图上就是
      "你在临河茶肆，旁边是里巷和东馆" —— 这才叫"附近"。
      坐标距离只在**连出来的地方太少**（< `min_places`）时用来补足。

    返回 `None` 的情形（**调用方保持原样，绝不比现在更差**）：
      · `layout` 是空的；
      · `current` 为空，或在这份布局里找不到（名字对不上时，宁可不取景，
        也不要随便拿一处当地标 —— 那会把用户带到错误的地方）；
      · 布局里本来就只有一处地点（没得取）。
    
        English:
    From the entire layout, **take out only the small chunk near the current location**, and re-fill
    the canvas with it.
        ⚠⚠ **As of 2026-10-08 the UI no longer calls it** (that wiring is
           pinned by the new criteria of `verify_minimap`). The second time the user called out the same problem:
           "Next to the spot where the protagonist is on the minimap, a string of **world-tier** names is drawn (each realm, each domain); the user said "these are not real place names" and asked the artist to draw
56.       **only based on the locations where the currently occurring story takes place** rather than based on the entire novel's settings."
             **only based on the locations where the currently occurring story takes place** rather than based on the entire novel's settings."
           The root cause is that it takes the **path neighbors in the settings**, and that path set is **relations made up** by the AI when placing positions
           Now the scope is determined instead by "**the locations matched from today's script**" (`places_in_day`);
           if that is unavailable, treat today's map as not out yet and fall back to `here_only()` to draw only the current place.
           The function is kept because its **scene selection and scaling** are still correct (and criteria are still testing it) —
           it is only that "where the scope comes from" is done wrong, so it is no longer shown on screen.
        User 2026-10-07
        --------------
        "The minimap is wrong, the big names of each realm and domain all show up; the minimap should be the current
          scene's minimap near where the protagonist is, not the novel's overall map."
        ★ This is **framing**, not filtering: not only pick out a few nearby places, but also **rescale** them so they fill the canvas.
          Filtering without scaling means the extracted small patch will huddle in one corner of the canvas (the outer margin was originally reserved for "unselected
          places"), looking like "the map wasn't finished" -- which is as good as not fixing it.
        ★★ Pick neighbors **based on "paths", not coordinate distance**. The reasoning is concrete:
          When first built, it was "fill up to 6 places by distance"; tried with real data (`临河茶肆` has 7 places total)
          still drew 6 places -- almost the whole map, and the user-reported problem was **not solved**.
          Coordinate distance is only used to top up when **too few connected places** (< `min_places`).
        Cases that return `None` (**caller keeps the original, never worse than now**):
          · `layout` is empty;
          · `current` is empty, or not found in this layout (when names don't match, rather not frame
            than casually use some place as a landmark -- that would take the user to the wrong place);
          · the layout has only one place to begin with (nothing to frame).
    """
    if layout is None or not getattr(layout, 'places', None):
        return None
    cur = str(current or '').strip()
    if not cur:
        return None
    by = layout.by_name()
    if cur not in by:
        return None
    if len(layout.places) <= 1:
        return None

    # ── ① 与当前地点**有通路直连**的（设定里明写的"挨着"，最可信）──
    # [EN] ── ① Those **directly connected by a path** to the current location (the "adjacent" explicitly
    # [EN] stated in the setting, most trustworthy) ──
    picked: list[str] = [cur]
    for lk in (layout.links or []):
        if len(picked) >= max_places:
            break
        a, b = str(lk.get('a') or ''), str(lk.get('b') or '')
        for x, y in ((a, b), (b, a)):
            if x == cur and y in by and y not in picked:
                picked.append(y)
                break
    # ── ② 太少才按坐标距离补（补到 min_places 为止，不是补到 max）──
    # [EN] ── ② Only when too few, fill in by coordinate distance (fill up to min_places, not up to max) ──
    if len(picked) < min_places:
        c = by[cur]
        rest = sorted((p for p in layout.places if p.name not in picked),
                      key=lambda p: (p.x - c.x) ** 2 + (p.y - c.y) ** 2)
        for p in rest:
            if len(picked) >= min_places:
                break
            picked.append(p.name)

    sub = [by[n] for n in picked if n in by]
    if len(sub) <= 1:
        return None                     # 只取到自己 → 不叫"附近"，不如画总图
        # [EN] Only getting to itself → not "nearby", better to draw the overview map

    # ── 重新铺满（等比，别把地图拉变形）──
    # [EN] ── Re-spread to fill (uniform scale, don't distort the map) ──
    xs = [p.x for p in sub]
    ys = [p.y for p in sub]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    span = max(x1 - x0, y1 - y0)
    if span < 1e-6:
        return None                     # 全挤在一个点上，缩放没意义
        # [EN] All crammed onto one point, zooming is meaningless
    keep = 1.0 - 2 * LOCAL_PAD

    def _fit(v: float, lo: float) -> float:
        return round(LOCAL_PAD + (v - lo) / span * keep, 4)

    out = Layout(caption=layout.caption, source=layout.source)
    for p in sub:
        out.places.append(Place(name=p.name, x=_fit(p.x, x0), y=_fit(p.y, y0),
                                shape=p.shape, size=p.size,
                                short=p.short, note=p.note))
    # 通路：两端都在取景范围内的才留（不然会画一条伸到画布外的线）
    # [EN] Paths: keep only those whose both ends are within the framed range (otherwise it draws a line
    # [EN] reaching off the canvas)
    names = {p.name for p in out.places}
    out.links = [lk for lk in (layout.links or [])
                 if str(lk.get('a') or '') in names and str(lk.get('b') or '') in names]
    # 水系 / 院墙：同样缩放。**整条留着**（不裁）——
    # 局部图上"有条河从旁边过"正是想看的信息，裁掉反而丢线索；
    # 伸到画布外的部分由画布自然裁切，不影响别的元素。
    # [EN] Water systems / courtyard walls: same scaling. **Keep the whole thing** (no clipping) ——
    # [EN] On the local map, "a river passing by" is exactly the information you want to see; clipping it
    # [EN] loses the clue instead;
    # [EN] the part reaching off the canvas is naturally clipped by the canvas and doesn't affect other
    # [EN] elements.
    out.water = [[_fit(pt[0], x0), _fit(pt[1], y0)]
                 for pt in (layout.water or []) if len(pt) >= 2][:64]
    # ★ 2026-10-27：**类型要跟着几何一起搬**。只搬折线不搬类型，局部图上的海又会被
    #   按"河"画成一条带 —— 这类"字段漏搬"比"没写"更难发现（值恰好等于默认时零症状）。
    # [EN] ★ 2026-10-27: **the kind travels with the geometry**. Moving the polyline without it makes
    # [EN] the zoomed map draw the sea as a river band again -- a missed field is harder to notice than
    # [EN] a missing one (zero symptoms when the value happens to equal the default).
    out.water_kind = str(getattr(layout, 'water_kind', '') or '')
    out.walls = [[_fit(pt[0], x0), _fit(pt[1], y0)]
                 for pt in (layout.walls or []) if len(pt) >= 2][:64]
    return out


def places_from_settings(settings: dict) -> tuple[list[str], list[str]]:
    """从设定里取 `(地点名列表, 说明列表)`。

    `地点.yaml` 的形状是 `[{"名称": …, "说明": …}]`（见 `ingest/extractor.py`），
    但也见过纯字符串数组，两种都认。
    
        English:
    Get `(place name list, description list)` from the settings.
        but plain string arrays have also been seen; both are recognized.
    """
    names: list[str] = []
    notes: list[str] = []
    for p in (settings.get('places') or []):
        if isinstance(p, dict):
            nm = str(p.get('名称') or '').strip()
            nt = str(p.get('说明') or '').strip()
        else:
            nm, nt = str(p or '').strip(), ''
        if nm and nm not in names:
            names.append(nm)
            notes.append(nt)
    return names, notes


# ══════════════════════════════════════════════════════════════════════
#  AI：把设定读成布局
# [EN] AI: read the setting into a layout
# ══════════════════════════════════════════════════════════════════════
_PROMPT = """你在给一本小说画一张**简化的小地图**。根据下面这份设定，把这个世界的
地点按**相对位置**摆出来 —— 不是列表，是一张图：谁在东边、谁挨着河、
谁在院子里面。

硬要求：
1. **只许用下面给出的地点**，一个都不许新增（编出来的名字会被丢掉）。
2. `x` / `y` 是 0~1 的相对坐标（左上角是 0,0；右下角是 1,1）。
   尽量**摊开**，不要挤成一团；宁可位置粗略，也要看得出相对关系。
3. `形` 只能取这几个字之一：{shapes}
   （看不出是什么就用「屋」）
4. `大小` 只能取：{sizes}
5. `简称` **不超过 3 个字**（图上位置很小），比如「临河茶肆」→「茶肆」。
6. `说明` 不超过 12 字，是你**为什么把它放在那儿**，不是抄设定原文。
7. 只输出 JSON，不要任何解释文字、不要 ``` 围栏。

JSON 形状：
{{"地点": [{{"名称": "…", "简称": "…", "x": 0.3, "y": 0.6,
            "形": "屋", "大小": "中", "说明": "靠着河"}}],
 "通路": [{{"从": "…", "到": "…", "形": "路"}}],
 "水系": [[0.0, 0.4], [0.5, 0.5], [1.0, 0.7]],
 "水系类型": "河",
 "院墙": [],
 "题记": "四个字以内"}}

说明：
- `通路` 只写**看得出来的连接**（沿着同一条街、隔一道桥）。
  不确定就少写几条 —— 乱连线比少连线更像错。
- `水系` / `院墙` **没有就给空数组**。`院墙` 是一个闭合轮廓。
- `水系` 是一条折线，**必须用 `水系类型` 说明它是哪一种**（这个字段决定画法，
  写错了图就错，所以要自己判断一次）：
  · `"河"` —— 河道中线，**两岸都是陆地**（城里穿过去的那种）；
  · `"湖"` —— **闭合**的岸线（首尾点接上），中间是水；
  · `"海"` —— **陆地与海的分界**：两端都**画到图外**（坐标可以写 0 或 1），
    水只在**一侧**（没有人住的那一侧）。
  ⚠ 分不清就写 `"河"`。宁可少画一片海，也不要把一条河写成海 ——
    那样图上会凭空多出半张蓝色的水，比画错形状严重。
  ⚠ 没有水系时 `水系` 给空数组，`水系类型` 给空字符串。
- `题记` 是这张图的地名（比如「临河镇」），没有就空字符串。

── 设定 ──
地点（名称 ｜ 说明）：
{places}
{world}
{map_hint}"""


def _build_prompt(names: list[str], notes: list[str], worldview: str,
                  map_yaml: Any) -> str:
    lines = [f'- {nm}｜{(notes[i] if i < len(notes) else "")[:40]}'
             for i, nm in enumerate(names[:MAX_PLACES])]
    world = ''
    if worldview.strip():
        world = '\n世界观（决定"哪边是水、哪边是市"）：\n' + worldview.strip()[:600]
    hint = ''
    if isinstance(map_yaml, dict):
        w, h, locs = map_yaml.get('宽'), map_yaml.get('高'), map_yaml.get('地点')
        if locs or w or h:
            hint = ('\n设定里已经给过一份粗略地图（可以采纳，也可以按上面的说明修正）：'
                    f'\n宽={w} 高={h} 地点={locs}')
    return _PROMPT.format(shapes='／'.join(SHAPES), sizes='／'.join(SIZES),
                          places='\n'.join(lines) or '（没有地点）',
                          world=world, map_hint=hint)


async def ai_layout(names: list[str], notes: list[str] | None = None, *,
                    worldview: str = '', map_yaml: Any = None,
                    title: str = '') -> Layout:
    """让 AI 摆一次布局。**任何失败都退回 `simple_layout()`**（绝不抛给调用方）。

    为什么在这里兜住所有异常：调用方是画图的界面 —— 一张图算不出来，
    不该让整个运行界面挂掉。而且"没图"比"丑图"糟糕得多。
    
        English:
    Let the AI do one layout pass. **Any failure falls back to `simple_layout()`** (never throw to
    the caller).
        Why catch all exceptions here: the caller is the drawing UI -- one map failing to compute
        should not crash the entire run UI. Also "no map" is far worse than "ugly map".
    """
    names = [str(n).strip() for n in (names or []) if str(n).strip()]
    notes = list(notes or [])
    if not names:
        return Layout(source='simple')

    from llm import replies                                   # 局部 import
    # [EN] Local import

    try:
        rep = await replies.ask(
            'cheap',                                              # 便宜档就够
            # [EN] The cheap tier is enough
            [{'role': 'user',
              'content': _build_prompt(names, notes, worldview, map_yaml)}],
            purpose=PURPOSE,
            want=dict,
            max_tokens=1400,          # 24 个地点 × 6 个字段，还要留 JSON 余量
            # [EN] 24 locations × 6 fields, plus room to spare for JSON
            temperature=0.3,
            default=None,
        )
    except Exception as e:                                    # noqa: BLE001
        _LOG.warning('小地图布局：调用失败，改用简化排布（%r）', e)
        return simple_layout(names, notes=notes)

    if not (rep.ok and isinstance(rep.value, dict)):
        _LOG.warning('小地图布局：没拿到可用 JSON，改用简化排布（%s）',
                     getattr(rep, 'why', ''))
        return simple_layout(names, notes=notes)

    lay = normalize(rep.value, names, source='ai')
    if not lay.places:
        _LOG.warning('小地图布局：AI 给的地点一个都没对上设定，改用简化排布')
        return simple_layout(names, notes=notes)
    _LOG.info('小地图布局：AI 排好 %d 处地点（设定里共 %d 处）',
              len(lay.places), len(names))
    return lay


# ══════════════════════════════════════════════════════════════════════
#  缓存（一份布局只算一次；存在**运行文件夹**里，绝不碰项目文件夹）
# [EN] Caching (a layout is computed only once; stored in the **runtime folder**, never touch the
# [EN] project folder)
# ══════════════════════════════════════════════════════════════════════
CACHE_NAME = '地图布局.json'


def load_cached(run_dir) -> Layout | None:
    """从运行文件夹读回上次算好的布局（读不到就 None，不抛）。
        English:
    Read back the last computed layout from the run folder (None if unreadable, no throw).
    """
    if run_dir is None:
        return None
    try:
        p = run_dir / CACHE_NAME
        if not p.exists():
            return None
        return Layout.from_dict(json.loads(p.read_text(encoding='utf-8')))
    except Exception:                                         # noqa: BLE001
        return None


def save_cached(run_dir, layout: Layout, *, name: str = '') -> None:
    """把布局写进运行文件夹。

    `name` 非空时用这个文件名（**当天地图**写 `当天地图.json`，别覆盖全书布局缓存）。

    ⚠ **只写运行文件夹**（它是产出目录）；项目文件夹一直只读 ——
    这是这个项目的铁律（`cli/` 之外任何地方都不许反写项目文件夹）。
    
        English:
    Write the layout into the run folder.
        When `name` is non-empty use this filename (**当天地图** writes `当天地图.json`, don't overwrite the whole-book layout cache).
        ⚠ **Only write the run folder** (it's the output directory); the project folder is always read-only --
        this is the project's iron rule (nothing outside `cli/` may write back to the project folder).
    """
    if run_dir is None or layout is None or not layout.places:
        return
    try:
        from util.io import atomic_write_text
        atomic_write_text(run_dir / (name or CACHE_NAME),
                          json.dumps(layout.to_dict(), ensure_ascii=False,
                                     indent=2))
    except Exception as e:                                    # noqa: BLE001
        _LOG.debug('小地图布局缓存写入失败（不影响出图）：%r', e)
