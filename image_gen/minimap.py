# -*- coding: utf-8 -*-
"""小地图的**矢量绘制**：布局规格 → `ft.canvas` 形状。

用户 2026-10-06
--------------
「小地图是否可以用矢量图的形式每次都重新画一下（切换场景的时候绘制），
  而且要是根据故事里的设计尽可能的反应其布局（可以稍微简略但是不能够
  一点都不像），要求使用AI动态绘制」

这个模块负责两件事里的一件：
  · **摆位**（谁在东边、谁挨着河）在 `map_layout.py`，由 AI 读设定得出；
  · **画**（把摆位变成图形）在这里，纯矢量、零 LLM、瞬时。

为什么是矢量而不是位图
----------------------
老实现是 `PIL` 画一张 PNG 存盘（`map_zh.png`），于是：
  · 只在**第一次**生成，之后永远长一个样（"地点待生成"那行字挂了很久）；
  · 换一个地点要重存一张图、还要处理缓存与语言两套；
  · 缩放就糊。
`ft.canvas` 是客户端**按形状即时绘制**的（线/圆/路径/文字），没有像素缓存问题，
所以"每次切场景重画"就是重建一个形状列表 —— 便宜到可以随便画。

⚠ 两个坑（都实测过）
--------------------
1. `ft.canvas` 在模块级 `__getattr__` 里**取不到** —— 必须
   `import flet.canvas as fcv`，写 `ft.canvas.Line` 会 AttributeError。
2. 画布只有 200×132，**字必须小、坐标必须夹在画布内**：
   出界的形状不会报错，只是**看不见**（这个项目栽过好几次"树里有、屏幕上没有"）。

English:
**Vector drawing** of the minimap: layout spec → `ft.canvas` shapes.
User 2026-10-06
--------------
"Can the minimap be redrawn each time in vector form (drawn when switching scenes),
  and reflect the layout as much as possible according to the design in the story (it can be a bit simplified but must not
  look nothing like it), requiring the use of AI dynamic drawing"
This module handles one of two things:
  · **Placement** (who is to the east, who is next to the river) is in `map_layout.py`, derived by AI reading the settings;
  · **Drawing** (turning placement into graphics) is here, pure vector, zero LLM, instantaneous.
Why vector instead of bitmap
----------------------
The old implementation drew a PNG with `PIL` and saved it to disk (`map_zh.png`), so:
  · it was only generated the **first time**, and afterward always looked the same (the line "locations pending generation" hung around for a long time);
  · changing a location meant re-saving an image, plus handling two sets of caches and languages;
  · and it got blurry when zoomed.
`ft.canvas` is drawn client-side **instantly by shape** (lines/circles/paths/text), with no
pixel cache issues,
so "redraw on every scene switch" just means rebuilding a shape list — cheap enough to draw
freely.
⚠ Two pitfalls (both actually tested)
--------------------
1. `ft.canvas` is **not reachable** via the module-level `__getattr__` — you must
   `import flet.canvas as fcv`, writing `ft.canvas.Line` will raise AttributeError.
2. The canvas is only 200×132, **text must be small and coordinates must be clamped inside the canvas**:
   out-of-bounds shapes won't error, they just **won't be visible** (this project has been burned several times by "it's in the tree but not on screen").
"""
from __future__ import annotations

import math

import flet as ft
import flet.canvas as fcv

from image_gen.map_layout import Place, Layout
from image_gen import label_place as LP
# ★★ 2026-10-27：小地图的路要**按与大地图同一份分级**画（用户："小图和大图不像同一张地图"）。
#   `scale` / `worldstyle` 都是**零依赖**模块，所以从 `minimap` 引它们不会成环
#   （反方向不行：`scalemap` 依赖 `minimap`，所以等级判定的实现在 `worldstyle`）。
# [EN] ★★ 2026-10-27: the minimap's roads must use **the same grading as the big map** (the user:
# [EN] "the minimap and the big map do not look like the same map"). Both `scale` and `worldstyle`
# [EN] are **dependency-free**, so importing them from `minimap` creates no cycle (the reverse is not
# [EN] possible: `scalemap` depends on `minimap`, which is why the rank judgement lives in
# [EN] `worldstyle`).
from image_gen import scale as SC
from image_gen import worldstyle as WS
# ★ 2026-10-27：小地图的城市档要用**同一张街网**（`scalemap.streetnet`）。
#   依赖方向是 `minimap -> scalemap`，与 `floorplan -> scalemap` 一致 ——
#   `scalemap` **不许**反过来 import `minimap`（那会成环）。
# [EN] ★ 2026-10-27: the minimap's city tier uses the **same network** (`scalemap.streetnet`). The
# [EN] dependency runs `minimap -> scalemap` (same as `floorplan -> scalemap`); `scalemap` must **not**
# [EN] import `minimap` back (that would be a cycle).
from image_gen import scalemap as SM

# ── 配色：默认跟水墨主题一套（调用方可以传自己的 `palette` 覆盖）────────
# 为什么默认值写在这里而不是从 `gui.app_flet` 导入：`image_gen` 是**下层**模块，
# 反过来依赖界面层会成环。界面那边把自己的 `C` 传进来即可（一处真相）。
# [EN] ── Color scheme: defaults to the same set as the ink-wash theme (callers can pass their own
# [EN] `palette` to override) ────────
# [EN] Why the default value is written here instead of imported from `gui.app_flet`: `image_gen` is a
# [EN] **lower-layer** module,
# [EN] depending on the UI layer in the other direction would create a cycle. The UI side just passes
# [EN] its own `C` in (single source of truth).
PALETTE = {
    'paper': '#f8f4ea',      # 纸底
    'ink': '#4a4f57',        # 普通地点的墨线
    'muted': '#8a9099',      # 次要的字
    'water': '#8fb0c4',      # 水系
    'wall': '#b9b1a0',       # 院墙
    'link': '#c5bda9',       # 通路
    'here': '#b23028',       # 当前地点（朱砂）
    'cast_a': '#8a6d3b',     # 人物点（赭石）
    'on_paper': '#fffdf8',   # 压在朱砂上的字
    # ★★ 室内图的两样（2026-10-12）：
    #   `frame` —— **整座建筑的那一圈框**（建筑名写在框上，替代从前"中间一个红点"）；
    #   `yard`  —— 院子的浅底（屋里见顶、院里见天，一眼分得开）。
    # [EN] ★★ Two things for indoor maps (2026-10-12):
    # [EN]   `frame` -- **the ring around the whole building** (the building name is written on it,
    # [EN]   replacing the old "a red dot in the middle");
    # [EN]   `yard`  -- a light wash for the courtyard (indoors has a roof, the yard has open sky;
    # [EN]   distinguishable at a glance).
    'frame': '#6f5b45',
    'yard': '#efe9dc',
    # ★★ 2026-10-16：跨城市档小图的**城市轮廓**浅填充（"把城市本身画好"）。
    #   比 `yard` 略冷一点，让人一眼分出"城区"与"院子"。
    # [EN] ★★ 2026-10-16: the light fill for the **city outline** in the cross-city minimap
    # [EN] ("draw the city itself"). Slightly cooler than `yard` so the urban block reads apart from
    # [EN] a courtyard.
    'city': '#e6ebe8',
    # [EN] Paper base
    # [EN] Ink lines of ordinary locations
    # [EN] Secondary text
    # [EN] Water system
    # [EN] Courtyard walls
    # [EN] Paths
    # [EN] Current location (cinnabar)
    # [EN] Character dots (ochre)
    # [EN] Text pressed on top of cinnabar
}

#: 字形 → 一档大小（相对 `r` 的倍数）。太大的会互相压住。
# [EN] : glyph → one size tier (multiple of `r`). Too large and they press onto each other.
_SHAPE_SCALE = {'院': 1.35, '山': 1.2, '院': 1.35, '市': 1.15, '塔': 1.05}
_SIZE_SCALE = {'小': 0.78, '中': 1.0, '大': 1.28}

#: 在场人物那个小点的半径（像素）。
# [EN] : radius of the small dot for a present character (in pixels).
dot_r = 2.4
#: 在场人物的小点**离地点名字多远**（往上抬多少像素）。
#   为什么是"抬一行"而不是"绕一圈"：地点现在只有一行字（用户 2026-10-12：
#   地点不要用点标记，用小字），中心被字占着 —— 小点排到字的上方，谁也不压谁。
# [EN] : how far the character dot sits from the location label (**how many pixels it is lifted**).
# [EN] Why "lifted one line" rather than "orbiting": a location is now just one line of text (the user
# [EN] on 2026-10-12: do not mark locations with dots, use small text), and its centre is taken by the
# [EN] text -- the dots go above the text so neither presses on the other.
CAST_LIFT = 9.0


def _cjk_w(text: str, size: float) -> float:
    """估一段文字的宽度。汉字=1em、其余约 0.55em —— 只用来居中，不用精确。
        English:
    Estimate the width of a run of text. CJK = 1em, the rest about 0.55em — used only for centering,
    not precise.
    """
    w = 0.0
    for ch in str(text or ''):
        w += size * (1.0 if ord(ch) > 0x2E80 else 0.55)
    return w


def _spatial():
    """拿到 `world.spatial`（**懒加载**，拿不到就返回 None）。

    ⚠ 为什么懒加载、还带兜底：`image_gen` 与 `world` 在依赖方向上**互为上游**
      （`world.atlas` 要用 `image_gen.map_layout` 的 `Layout`）。顶层 import 现在
      不会成环（`world/__init__.py` 是空的），但**将来有人往那两个 `__init__`
      里加一句就成环了**。所以这里按"能拿就拿、拿不到就用本地那一份小判据"办，
      渲染绝不因此失败（画一张图失败 = 整个运行界面少一块，代价太大）。

        English:
    Get `world.spatial` (**lazy**, returns None if unavailable).
        ⚠ Why lazy, and with a fallback: `image_gen` and `world` are **upstream of each other** in the
        dependency direction (`world.atlas` needs `Layout` from `image_gen.map_layout`). A top-level
        import does not cycle today (`world/__init__.py` is empty), but **the day someone adds a line to
        either `__init__` it will**. So this does "use it if you can get it, otherwise fall back to the
        local mini-classifier", and rendering never fails because of it (a failed draw = a missing panel
        in the run screen, far too expensive).
    """
    global _SP
    if _SP is None:
        try:
            from world import spatial as _mod
            _SP = _mod
        except Exception:                                        # noqa: BLE001
            _SP = False
    return _SP or None


#: `world.spatial` 的缓存（`False` = 试过了、拿不到）。
# [EN] : Cache of `world.spatial` (`False` = tried and unavailable).
_SP = None

#: 拿不到 `world.spatial` 时的**本地小判据**（与那份保持同一口径）。
# [EN] : The **local mini-classifier** used when `world.spatial` is unavailable (same conventions).
_GATES = ('大门', '后门', '角门', '侧门', '门楼', '院墙', '围墙', '门口', '门槛', '门', '墙')
_OUTDOOR = ('井', '泉', '池塘', '水缸', '树', '竹', '花坛', '菜畦', '假山', '石桌',
            '石凳', '影壁', '照壁', '旗杆', '院', '庭', '园', '场', '坪')


def _is_gate(name: str) -> bool:
    """是不是**边界**上的东西（门 / 墙）—— 室内图上它归框，不归屋里。
        English:
    Is this something on the **boundary** (gate / wall) -- on an indoor map it belongs to the frame,
    not the room.
    """
    sp = _spatial()
    if sp is not None:
        return bool(sp.is_boundary(name))
    s = str(name or '')
    return any(w in s for w in _GATES)


def _is_outdoor(name: str) -> bool:
    """是不是**屋外**的（院子里 / 露天的）。
        English:
    Is this **outdoors** (in the courtyard / under open sky).
    """
    sp = _spatial()
    if sp is not None:
        return sp.space_of(name) == '室外'
    s = str(name or '')
    return any(w in s for w in _OUTDOOR)


def _is_room(name: str) -> bool:
    """是不是**屋里的一间**（房间 / 厅堂）—— 图上要给它画墙的那一类。
        English:
    Is this **a room indoors** (chamber / hall) -- the kind that gets walls drawn on the map.
    """
    sp = _spatial()
    if sp is not None:
        return bool(sp.is_room(name))
    return False


def _is_fixture(name: str) -> bool:
    """是不是**屋里的陈设**（柜台 / 条案 / 灶）—— 归屋里，但它是"家具"不是"房间"。
        English:
    Is this an **indoor fixture** (counter / side table / stove) -- it belongs indoors, but it is
    "furniture", not "a room".
    """
    sp = _spatial()
    if sp is not None:
        return bool(sp.is_indoor_fixture(name))
    return False


# ══════════════════════════════════════════════════════════════════════
#  地图的**细致程度**（用户 2026-10-12 点名的那件事）
# [EN] The map's **level of detail** (the matter the user named on 2026-10-12)
# ══════════════════════════════════════════════════════════════════════
#  用户原话（这一整段就是规格）：
#    「如果是室内地图 则请把墙画出来
#      如果是室内和室外结合的地图 且需要画到室内布置的程度 比如一个茶馆
#      把室内布置和院子内容刚好画到一张图里 则把室内墙和室外墙都画出来
#      如果是很大的地图 比如街道图 那其实是不需要画室内的
#      只需要把建筑标记出来就行 你根据地图的细致程度来判断」
#  翻成四种程度，**判据只看数据、不看画布大小**（同一份 Layout 判断结果恒定）：
#  | 程度 | 什么时候 | 怎么画 |
#  | `室内` | 这一层只有屋里空间（没有院子） | **房间画矩形墙** + 整座楼外框 |
#  | `室内外` | 屋里 + 院子**同时**出现在一张图上（茶馆那种） | **室内墙 + 室外墙都画** |
#  | `局部` | 一处地方周边（河、桥、邻舍） | 照旧：点 + 字形，不画室内墙 |
#  | `整体` | 街道 / 城镇那种大图 | **不画室内**，只把建筑标记出来 |
#  ⚠ `室内外` 与 `局部` 的分界是"**有没有屋里空间**"：茶馆那张图里有堂屋、
#    所以它要画室内墙；渡口那张图里全是屋外的东西，画室内墙就成了无中生有。
# [EN] The user's exact words (this whole block is the spec):
# [EN] "if it is an indoor map, then please draw the walls;
# [EN]  if it is a map combining indoors and outdoors and needs to go as far as interior layout, e.g. a
# [EN]  teahouse, putting the interior layout and the courtyard contents into exactly one image, then draw
# [EN]  both the indoor walls and the outdoor walls;
# [EN]  if it is a very large map, e.g. a street map, then indoor drawing is not needed at all, you only
# [EN]  need to mark out the buildings; you judge by the map's level of detail."
# [EN] Turned into four levels, and the criterion looks **only at the data, not the canvas size** (the
# [EN] same `Layout` always yields the same answer):
# [EN] | level | when | how it is drawn |
# [EN] |---|---|---|
# [EN] | `室内` | this layer only has indoor space (no courtyard) | **rooms get rectangular walls** + the whole building's outer frame |
# [EN] | `室内外` | indoors + courtyard appear **on the same map** (the teahouse case) | **both indoor walls and outdoor walls** |
# [EN] | `局部` | the surroundings of one place (river, bridge, neighboring houses) | as before: point + glyph, no indoor walls |
# [EN] | `整体` | a large street / town map | **no indoor drawing**, only building markers |
# [EN] ⚠ The boundary between `室内外` and `局部` is "**is there any indoor space**": the teahouse map
# [EN]   contains the main hall, so it draws indoor walls; the ferry map is all outdoor things, and
# [EN]   drawing indoor walls there would be inventing something from nothing.
DETAIL_IN = '室内'
DETAIL_IN_OUT = '室内外'
DETAIL_LOCAL = '局部'
DETAIL_WHOLE = '整体'

#: 一张图上最多画几间的墙。再多小画布就糊了（超出的照旧只写名字）。
# [EN] : max number of rooms to draw walls for on one map. More and the small canvas turns to mush
# [EN] (the rest just get their names as before).
MAX_ROOM_WALLS = 6

#: 房间墙的**最小**像素尺寸（宽 / 高）。
# [EN] : the **minimum** pixel size of a room's wall (width / height).
#  ★ 这两个数不是随便定的，它们同时管着两件事：
#    ① 太小的话房间墙会退化成一个小方块，跟"陈设"分不出来；
#    ② 判据 `verify_space_rules` D5 用**几何窗口**认"院子里那层浅底"
#       （宽 24~50 且高 16~40）。房间墙一旦落进那个窗口，就会被误认成浅底
#       —— 那条判据是钉"屋里见顶、院里见天"的，被误认就等于这条保障没了。
#       所以最小宽取 **54**（> 50）刻意避开它。
# [EN] ★ These two numbers are not arbitrary; they govern two things at once:
# [EN]   ① too small and the room wall degenerates into a small block, indistinguishable from a
# [EN]      "fixture";
# [EN]   ② criterion D5 in `verify_space_rules` recognises "the wash behind courtyard things" by a
# [EN]      **geometric window** (width 24~50 and height 16~40). Once a room wall falls into that
# [EN]      window it is mistaken for a wash -- and that criterion pins "rooms have a roof, the yard has
# [EN]      open sky", so a misread means that guarantee is gone. Hence the minimum width of **54**
# [EN]      (> 50) deliberately avoids it.
ROOM_MIN_W = 54.0
ROOM_MIN_H = 42.0

#: 陈设小方块的最大尺寸（**要小于浅底窗口**，同理）。
#   ★ 2026-10-15：22×13 → 16×10 —— 小地图只有 196×132，22 宽的方块把 54 宽的房间塞得
#     几乎只剩墙；用户报「家具过大」。缩小后家具与房间比例协调（判据 N5 钉上限）。
# [EN] : the maximum size of a fixture's small block (**must be smaller than the wash window**, same
# [EN] reasoning).
# [EN] ★ 2026-10-15: 22x13 -> 16x10 -- the minimap is only 196x132; a 22px block crowded a 54px room
# [EN] down to almost only walls. The user reported "furniture too large". Smaller blocks keep the
# [EN] furniture/room ratio sane (criterion N5 pins the upper bound).
FIXTURE_W = 16.0
FIXTURE_H = 10.0

#: 小地图房间矩形的初始"胖度"占绘图区比例（传给 `plan_audit.solve`）。
#   比大地图的 `PLAN_GROW=0.17` 略小，因为小地图画布窄，房间不必撑那么胖。
# [EN] The minimap room rectangle's initial "fatness" as a fraction of the drawing area (passed to
# [EN] `plan_audit.solve`). Slightly smaller than the big map's `PLAN_GROW=0.17` because the minimap
# [EN] canvas is narrow and rooms should not swell as much.
MINIMAP_GROW = 0.16

#: 院墙（室外墙）的**最小**尺寸 —— 同样避开浅底窗口。
# [EN] : the **minimum** size of the courtyard wall (the outdoor wall) -- likewise avoiding the wash
# [EN] window.
YARD_MIN_W = 62.0
YARD_MIN_H = 46.0


def _rank_int(name, places, style) -> int:
    """按地点名（连同作者给的 `size`）判聚落等级 —— **与大地图同一份实现**。

    ★ 为什么不在这里自己写一套：小地图上"州府与村子一样大"就是这么来的
      （它原来根本没有等级概念）。判法只在 `worldstyle.settlement_rank` 一处。
    [EN] Rank a settlement by name plus the author's `size` -- **the same implementation as the big
    [EN] map**. ★ Why not a local copy: "a prefecture and a hamlet at the same size on the minimap"
    [EN] is exactly what a local (absent) notion of rank produced. The judgement exists only in
    [EN] `worldstyle.settlement_rank`.
    """
    from image_gen import worldstyle as _WS
    nm = str(name or '')
    size = ''
    for p in (places or []):
        if str(getattr(p, 'name', '') or '') == nm:
            size = str(getattr(p, 'size', '') or '')
            break
    return _WS.settlement_rank(nm, size=size, style=style)


def detail_of(layout) -> str:
    """这份布局该按**哪个细致程度**画（见上面那张表）。

    判据只用**数据**（`kind` + 地点名），不读画布大小 —— 所以同一份 Layout
    在小地图和大地图上得到同一个结论（两处画法不同、分档必须一致）。
    [EN] Which **level of detail** this layout should be drawn at (see the table above).
    [EN] The criterion uses **data only** (`kind` + place names) and never reads the canvas size --
    [EN] so one `Layout` yields the same answer on the minimap and the big map (the drawing differs,
    [EN] the tiering must not).
    """
    places = list(getattr(layout, 'places', None) or [])
    if not places:
        return DETAIL_LOCAL
    kind = str(getattr(layout, 'kind', '') or '')
    names = [str(getattr(p, 'name', '') or '') for p in places]
    has_room = any(_is_room(n) for n in names)
    has_out = any(_is_outdoor(n) for n in names)
    if kind == '整体':
        # 街道 / 城镇那种大图：不画室内，只标记建筑（用户点名的第三种）
        # [EN] The large street / town map: no indoor drawing, just building markers (the user's third
        # [EN] case)
        return DETAIL_WHOLE
    if kind == '室内':
        # 茶馆那种"屋里 + 院子"在同一张图上 → 两种墙都画
        # [EN] The teahouse case, "indoors + courtyard" on one map -> draw both kinds of wall
        return DETAIL_IN_OUT if has_out else DETAIL_IN
    if kind == '局部':
        return DETAIL_LOCAL
    # ── 不知道 `kind`（老缓存 / here_only / simple_layout）→ **看名字自己判** ──
    #   ⚠ 这一段是给老档案用的：用户手上那份底图在"室内语义"之前生成，
    #     `kind` 是空的。不自己判的话，他打开老项目看到的还是老样子
    #     （而这正是他报的那件事）。
    # [EN] ── `kind` unknown (old cache / here_only / simple_layout) -> **infer from the names** ──
    # [EN]   ⚠ This branch is for old archives: the base map in the user's hands was generated before
    # [EN]   the "indoor semantics" existed, so `kind` is empty. Without inferring, opening an old
    # [EN]   project still looks the old way (which is exactly what he reported).
    if has_room:
        return DETAIL_IN_OUT if has_out else DETAIL_IN
    if len(names) >= 5:
        return DETAIL_WHOLE          # 一堆地点铺开 = 城镇/街道那种大图
        # [EN] A spread of many places = the large town/street kind of map
    return DETAIL_LOCAL


def minimap_lod(layout) -> str:
    """小图相对大图**简略一个级别**的渲染档（用户 2026-10-16：
    "小地图可以比大地图画的内容简略一个级别"）。

    大图档位（见 `detail_of`）→ 小图档位：
      · 室内 / 室内外 → `'building'`：只画**整座建筑**（框 + 门 + 建筑名 + 院子），
        不画房间墙、不画屋里陈设 —— "小地图就把房子或者房子以上的东西画好就可以"。
      · 局部 → `'area'`：街区聚合（沿用现状：地点小字 + 通路 + 水系）。
      · 整体 → `'city'`：画**城市轮廓 + 周围**，不画街道网
        （"如果是更大的地图 比如城市 那小地图就把城市本身和周围的东西画好就行
          大地图才会画城市里的街道"）。

    ⚠ 这是**纯函数**（只看数据），与 `detail_of` 同一套判据纪律：
      同一份 Layout 永远同一个答案（本地复用的前提）。
    [EN] The minimap's level of detail, one tier coarser than the big map (user 2026-10-16:
    "the minimap can be drawn one level simpler than the big map").
    Big-map tier (see `detail_of`) -> minimap tier: ...
    [EN] ⚠ This is a **pure function** (data only), the same discipline as `detail_of`:
    [EN] one `Layout` always yields the same answer (the premise for local reuse).
    """
    big = detail_of(layout)
    if big in (DETAIL_IN, DETAIL_IN_OUT):
        return 'building'
    if big == DETAIL_WHOLE:
        return 'city'
    return 'area'


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew 单调链凸包（逆时针）。少于 3 个点原样返回（画不出围合）。

    ★★★ 2026-10-27：**图上已经不用它了**。原来用它给小地图画"城市轮廓"，
      而那个轮廓就是用户说的"不规则图形"（见 ③b 段那整段说明）。
      现在保留下来的唯一理由是**反例法**（`developers/mutate_mapscale.py` ㉔ 刀
      要把凸包画回去，证明 O4 判据抓得住）与 `verify_minimap_lod` L2a
      （断言"图上**没有**这种多边形"，需要算出期望的凸包点集来比对）。
    ⚠ 别拿它再画图：一个"包住所有地点的多边形"在任何真实地图上都没有对应物。
    [EN] Andrew's monotone-chain convex hull (counter-clockwise). Fewer than 3 points returned as-is.
    ★★★ 2026-10-27: **no longer used for drawing**. It used to draw the minimap's "city outline",
    [EN] which is exactly the "irregular shapes" the user reported (see the ③b block). It survives
    [EN] only for the counterexample suite (`developers/mutate_mapscale.py` cut ㉔ draws the hull back
    [EN] to prove criterion O4 catches it) and for `verify_minimap_lod` L2a (which asserts that **no**
    [EN] such polygon is drawn and therefore needs the expected vertex set). ⚠ Do not use it to draw
    [EN] again: a polygon "wrapping all locations" has no counterpart on any real map.
    """
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) <= 2:
        return list(pts)
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo = []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    lo.pop(); up.pop()
    return lo + up


def room_walls(places: list, *, W: int, H: int, pad_x: float, pad_y: float,
               frame: tuple) -> dict:
    """给**屋里空间**算出互不重叠的矩形（单位：像素）。

    ★★ 2026-10-15：**兼容壳** —— 小地图的房间矩形不再各算一套，直接复用
      `plan_audit.solve()`（与大地图同一份几何）。房间互不重叠、与院子互斥都由它保证，
      这样小地图与大地图永远一致，也修掉了小地图"块重叠"那条 bug。
      公开签名不变，判据 `verify_map_detail` 仍按原方式问"这一层算出来几面墙"。
    [EN] ★★ 2026-10-15: **compatible shell** -- the minimap's room rectangles no longer have their
    [EN] own implementation; they reuse `plan_audit.solve()` (the same geometry as the big map). Room
    [EN] non-overlap and courtyard/house mutual exclusion are guaranteed by it, so the minimap and big
    [EN] map never diverge, and the minimap's "blocks overlapping" bug is fixed. The public signature is
    [EN] unchanged; `verify_map_detail` still asks "how many walls does this layer compute" the same way.
    """
    rooms = [p for p in places if _is_room(p.name)][:MAX_ROOM_WALLS]
    if not rooms:
        return {}
    fx0, fy0, fx1, fy1 = frame
    from image_gen import plan_audit as PA

    def px(p):
        return (pad_x + p.x * (W - 2 * pad_x),
                pad_y + p.y * (H - 2 * pad_y - 8))
    span = (fx0 + 3, fy0 + 3, fx1 - 3, fy1 - 3)
    lay = Layout(places=list(places))
    sol = PA.solve(lay, px=px, span=span, detail=DETAIL_IN_OUT, grow=MINIMAP_GROW)
    return {n: r.box for n, r in sol.rooms.items()}


def _outdoor_extent(places: list, *, W: int, H: int, pad_x: float,
                    pad_y: float) -> tuple | None:
    """所有**屋外**点聚出来的那一片（院子的范围），像素坐标 `(x0, y0, x1, y1)`。

    ★★ 2026-10-15：**兼容壳** —— 复用 `plan_audit.solve()` 的院子结果（与大地图
      同一份几何）。没有屋外的点 → `None`（那就没有院子，不画室外墙）。
    [EN] The patch gathered by all **outdoor** points (the courtyard's extent), in pixels
    [EN] `(x0, y0, x1, y1)`.
    [EN] ★★ 2026-10-15: **compatible shell** -- reuses `plan_audit.solve()`'s courtyard
    [EN] (same geometry as the big map). No outdoor points -> `None` (no courtyard, no outdoor wall).
    """
    outs = [p for p in places if _is_outdoor(p.name)]
    if not outs:
        return None
    from image_gen import plan_audit as PA

    def px(p):
        return (pad_x + p.x * (W - 2 * pad_x),
                pad_y + p.y * (H - 2 * pad_y - 8))
    lay = Layout(places=list(places))
    span = (pad_x, pad_y, W - pad_x, H - pad_y - 8)
    sol = PA.solve(lay, px=px, span=span, detail=DETAIL_IN_OUT, grow=MINIMAP_GROW)
    return sol.yard



def build_shapes(layout: Layout | None, *, current: str = '',
                 cast: list[str] | None = None,
                 cast_place: dict[str, str] | None = None,
                 width: int = 196, height: int = 132,
                 title: str = '', palette: dict | None = None,
                 font: str | None = None) -> list:
    """把一份布局画成形状列表（交给 `fcv.Canvas(shapes=…)`）。

    Args:
        layout: `map_layout.Layout`；None 或没有地点 → 返回一张空图提示。
        current: 当前地点名（画成朱砂 + 全职标签）。
        cast: 在场人名（画成小点；`cast_place` 给出他们各自在哪）。
        cast_place: {人名: 地点名}；没有的话人物点都画在 `current` 上。
        font: 图上用哪个字体（界面把自己的 `UI_FONT` 传进来）。

    为什么 `width/height` 默认 196×132：左栏宽 220、面板左右内边距各 12，
    内容区正好 196 —— 图比内容区宽会被裁掉（而且**不报错**）。
    
        English:
    Draw a layout into a shape list (handed to `fcv.Canvas(shapes=…)`).
        Args:
            layout: `map_layout.Layout`; None or no locations -> return an empty map hint.
            current: current location name (drawn in vermilion + full-time label).
            cast: names of people present (drawn as small dots; `cast_place` gives where each of them is).
            cast_place: {person name: location name}; if absent, all person dots are drawn on `current`.
            font: which font to use on the map (the UI passes in its own `UI_FONT`).
        Why `width/height` default to 196x132: left column width 220, panel left/right padding 12 each,
        content area is exactly 196 -- a map wider than the content area gets clipped (and **does not error**).
    """
    pal = dict(PALETTE)
    pal.update(palette or {})
    W, H = int(width), int(height)
    shapes: list = []

    # 纸底（一块底色，免得透出面板的半透明底显得脏）
    # [EN] Paper base (a patch of base color, so the panel's semi-transparent base doesn't show through and
    # [EN] look dirty)
    shapes.append(fcv.Rect(0, 0, W, H,
                           paint=ft.Paint(color=pal['paper'],
                                          style=ft.PaintingStyle.FILL)))

    places = list((layout.places if layout else []) or [])
    if not places:
        shapes.append(_text(W / 2, H / 2 - 7, '（还没有地点设定）',
                            size=11, color=pal['muted'], font=font, center=True))
        return shapes

    # ★★★ **把"现在人在哪儿"对上图里的名字**（2026-10-12）。
    #   用户报的「中间都有一个红点 这个去掉 看不见其他元素了」，根因之一就在这里：
    #   当前场景常写成**子地点**（`临河茶肆·堂屋`），而图上的名字是**房间名**
    #   （`堂屋`）—— 对不上时，那个"当前地点"的朱砂圈就落到一个**根本不在图上
    #   的位置**（或者 `day_layout` 补出来的那个假地点上），屏幕上就是正中间
    #   一个红点。
    #   ⚠ 只在**真的对得上**时才替换：对不上宁可维持原样（不要瞎认一间屋，
    #    那会把"我在哪"指错）。
    # [EN] ★★★ **Match "where the person is now" to a name on the map** (2026-10-12).
    # [EN]   One root cause of the user's "every minimap has a red dot in the middle; remove it, it
    # [EN]   hides the other elements" is right here: the current scene is often a **sub-location**
    # [EN]   (`临河茶肆·堂屋`) while the map's names are **room names** (`堂屋`) -- when they don't
    # [EN]   match, the "current place" cinnabar ring lands on a spot **that isn't on the map at all**
    # [EN]   (or on the fake place `day_layout` appended), which reads as a red dot in the middle.
    # [EN]   ⚠ Substitute only when it **really matches**: when it doesn't, keep the original (do not
    # [EN]   guess a room -- that would point "where I am" at the wrong place).
    from image_gen.map_layout import resolve_place as _resolve
    _hit = _resolve(layout, current)
    if _hit:
        current = _hit

    # 画布内边距：给标签留出空间（不然贴边的地点标签会被裁）
    # [EN] Canvas padding: leave space for labels (otherwise location labels at the edges get clipped)
    pad_x, pad_y = 16, 15

    # ★★★ 2026-10-27：**城市档也走紧凑取景**（与大地图同一份 `scale.frame_px`）。
    #
    #   原来这里是"整块画布 = 归一化 0~1"，而真实数据里地点常挤在中间 ——
    #   实测那份当天地图的 6 处地点只占 34%×37%，小图上就是"中间一小撮"，
    #   而大地图（改过之后）是铺开的 ⇒ **同一份数据、两张图点位不一致**，
    #   用户说的"小图和大图不像"就有这一份。
    #   ⚠ **只有 `city` 档改**：室内/室内外的 `pos` 与 `plan` 解算共用同一个 `px`
    #     （房间必须落在它自己的位置上），动它会让房间矩形偏移。
    #   ⚠ `lod` 在这里先算一次并复用（下面不再重算）—— 纯函数，但算两遍毫无意义。
    # [EN] ★★★ 2026-10-27: **the city tier also gets tight framing** (the same `scale.frame_px` as the
    # [EN] big map). It used to be "the whole canvas = normalised 0..1" while real coordinates huddle
    # [EN] in the middle (measured: 34% x 37%), so the minimap showed "a small clump in the centre"
    # [EN] while the (now fixed) big map spread out -- the same data giving two different point
    # [EN] layouts, which is part of the user's "the minimap and the big map do not look alike".
    # [EN] ⚠ **Only the `city` tier changes**: for indoor tiers `pos` shares `px` with the `plan`
    # [EN] solver (rooms must sit where they belong), and moving it would offset the room rectangles.
    # [EN] ⚠ `lod` is computed here once and reused below.
    lod = minimap_lod(layout)
    if lod == 'city':
        # 与大地图**同一个** `layout_extra()`（否则小图有海、大图没有）
        # [EN] The **same** `layout_extra()` as the big map (or the small map has the sea and the big
        # [EN] one does not)
        px = SC.frame_px(places, (pad_x, pad_y, W - pad_x, H - pad_y - 8),
                         also=SC.layout_extra(layout))
    else:
        def px(p: Place) -> tuple[float, float]:
            x = pad_x + p.x * (W - 2 * pad_x)
            y = pad_y + p.y * (H - 2 * pad_y - 8)      # 底下多留一点给题记
            # [EN] Leave a bit extra at the bottom for the inscription
            return x, y

    pos = {p.name: px(p) for p in places}

    # ── ⓪ ★★ 室内图：整座建筑**框住 + 建筑名写在框上**（用户 2026-10-12）──
    #  用户原话：「小地图如果是**室内地图** 就用**一个框把相关内容括起来作为这个建筑
    #  的名字** 现在是**中间一个红点作为建筑名字** 不但**挡住了内容** 还不合理」。
    #  所以室内图上：
    #    · 整座楼**不再画成一个点**（那个红点压住了屋里的房间与字）；
    #    · 改画**一圈框**把这一层整个括起来，建筑名写在框的上边（下面垫一块纸色，
    #      免得被框线穿过去）；
    #    · ★ **门画在框上**（`边界`）：门本来就是内外之分，它不是屋里的一件东西 ——
    #      画在框的下沿正中，一眼看出"门开在这一面"。
    #  ⚠ 判据 `tools/verify_space_rules.py` 按形状数量钉住它（有框、且没有那个点）。
    # [EN] ── ⓪ ★★ Indoor map: **frame the whole building + write its name on the frame** (user
    # 2026-10-12) ──
    # [EN]   The user's exact words: "if the minimap is an **indoor map**, use **a frame to enclose the
    # [EN]   relevant content as this building's name**. Right now there is **a red dot in the middle
    # [EN]   acting as the building's name**, which not only **covers the content** but is unreasonable."
    # [EN]   So on an indoor map:
    # [EN]     · the whole building **is no longer drawn as a point** (that red dot pressed onto the
    # [EN]     rooms and their labels);
    # [EN]     · instead **a frame** encloses the entire layer, with the building name written on the
    # [EN]     frame's top edge (on a paper-coloured patch, so the frame line does not run through it);
    # [EN]     · ★ **the gate is drawn on the frame** (a `boundary`): a gate is by nature the
    # [EN]     inside/outside divide, not a thing in the room -- drawn at the middle of the frame's bottom
    # [EN]     edge, showing at a glance "the gate opens on this side".
    # [EN] ⚠ The criterion `tools/verify_space_rules.py` pins it by shape count (there is a frame, and
    # [EN] that dot is gone).
    bldg = str(getattr(layout, 'frame', '') or '').strip() if layout else ''
    indoor = bool(bldg) or str(getattr(layout, 'kind', '') or '') == '室内'
    fx0, fy0, fx1, fy1 = 6.0, 6.0, W - 6.0, H - 15.0
    # ★★ 这一份图该按**哪个细致程度**画（用户 2026-10-12 点名的第二件事）：
    #   室内 / 室内外 / 局部 / 整体 —— 见 `detail_of()` 上面那张表。
    # [EN] ★★ Which **level of detail** this map should use (the second thing the user named on
    # [EN] 2026-10-12): indoor / indoor+outdoor / local / whole -- see the table above `detail_of()`.
    detail = detail_of(layout)
    # ★★ 2026-10-16（用户）：小图比大图**简略一个级别** —— 见 `minimap_lod()`。
    #   'building'：室内/室内外 → 只画整座建筑（不画房间墙、不画家具）；
    #   'city'：整体 → 画城市轮廓 + 周围（不画街道网）；
    #   'area'：局部 → 沿用现状。
    # ⚠ 2026-10-27：`lod` 已在上面（算 `pos` 的地方）算过一次，这里**复用**不再调用 ——
    #   纯函数算两遍不算错，但"同一个值两处算"正是漂移的入口（本项目老坑）。
    # [EN] ★★ 2026-10-16 (the user): the minimap is **one tier simpler** than the big map -- see
    # [EN] `minimap_lod()`. ⚠ 2026-10-27: `lod` was already computed above (where `pos` is built) and
    # [EN] is **reused** here; a second call would be a second source for one value (a classic pit).
    # ★★ 室内 / 室内外 两档**改走 `plan_audit.solve`**（与大地图同一份几何）：
    #   房间互不重叠、陈设落进所属房间、院子与房子互斥，都由一个函数负责，
    #   不再各写一套（2026-10-15：小地图"块重叠"正是各写一套时留下的 bug）。
    #   `px` 与 `span` 都按小地图自己的画布算（与绘制共用，避免两套坐标）。
    # [EN] ★★ The indoor / indoor+outdoor tiers now go through `plan_audit.solve` (same geometry as
    # [EN] the big map): room non-overlap, fixtures-in-room, courtyard/house mutual exclusion are all
    # [EN] owned by one function instead of two (2026-10-15: the minimap's "blocks overlapping" was a
    # [EN] bug left by the two separate implementations). `px` and `span` use the minimap's own canvas
    # [EN] (shared with drawing, no two coordinate systems).
    plan = None
    if detail in (DETAIL_IN, DETAIL_IN_OUT):
        from image_gen import plan_audit as PA

        def _px(p: Place) -> tuple[float, float]:
            return (pad_x + p.x * (W - 2 * pad_x),
                    pad_y + p.y * (H - 2 * pad_y - 8))
        _span = (fx0 + 3, fy0 + 3, fx1 - 3, fy1 - 3)
        # ★★★ 2026-10-26：**优先用"房间任务书"解出来的平面**（与大地图同一个来源）。
        #
        #   为什么必须改（用户两次点到同一件事：「小地图也不对」＋「布局也不合理」）：
        #   `PA.solve` 是从"一堆点"反推房间（气泡图 + 互相推开），
        #   所以"叠、房间不拼满、门悬在外面"在小地图上是**换了尺寸重复发生**。
        #   大地图已经换成 `roomplan`（确定性切分、拼满外轮廓），
        #   这里如果不跟着换，就变成**同一份数据、两张图两种布局** ——
        #   本项目《两处实现必然漂》的老坑，而且用户会先看到小地图、再打开大地图发现对不上。
        #
        #   ⚠ 拿不到任务书（老缓存 / 没设置 / 解算失败）⇒ **原样走老路**。
        #     新解算是"更好"，不是"必需"：小地图不能因为解算失败就空着。
        # [EN] ★★★ 2026-10-26: **prefer the plan solved from the room program** (same source as the
        # [EN] big map). Why it must change (the user pointed at this twice: "the minimap is wrong
        # [EN] too" and "the layout is unreasonable"): `PA.solve` infers rooms from a pile of points
        # [EN] (bubble diagram + push apart), so overlap / rooms not tiling / doors floating outside
        # [EN] **recur at minimap scale**. The big map now uses `roomplan` (deterministic slicing that
        # [EN] tiles the envelope); not switching here would mean **one dataset, two layouts** -- this
        # [EN] project's classic "two implementations drift" pit, and the user sees the minimap first
        # [EN] and then finds the big map disagrees. ⚠ No program (old cache / unset / solve failed)
        # [EN] => **the old path runs unchanged**; the new solver is "better", not "required", and the
        # [EN] minimap must never go blank because solving failed.
        try:
            from image_gen import roomplan as _RP
            _pd = getattr(layout, 'program', None) if layout is not None else None
            _prog = _RP.Program.from_dict(_pd) if _pd else None
            if _prog is not None:
                _fps = _RP.solve(_prog, span=_span)
                if _fps:
                    _fl = next((f for f, fp in _fps.items()
                                if current and current in fp.rooms), 1)
                    _fp = _fps.get(_fl) or _fps[min(_fps)]
                    plan = _RP.to_plan(_fp, detail=detail, current=current, place='')
        except Exception:                                     # noqa: BLE001
            plan = None
        if plan is None:
            plan = PA.solve(layout, px=_px, span=_span, detail=detail,
                             current=current, grow=MINIMAP_GROW)
    room_boxes = {n: r.box for n, r in plan.rooms.items()} if plan else {}
    if indoor:
        shapes.append(fcv.Rect(fx0, fy0, fx1 - fx0, fy1 - fy0, border_radius=3.0,
                               paint=ft.Paint(color=pal['frame'], stroke_width=1.2,
                                              style=ft.PaintingStyle.STROKE)))
        gate = next((p for p in places if _is_gate(p.name)), None)
        if gate is not None:
            gx = fx0 + (fx1 - fx0) * 0.5
            shapes.append(fcv.Line(gx - 7, fy1, gx + 7, fy1,
                                   paint=ft.Paint(color=pal['paper'],
                                                  stroke_width=2.4,
                                                  style=ft.PaintingStyle.STROKE)))
            shapes.append(_text(gx, fy1 - 1, '门', size=8, color=pal['frame'],
                                font=font, center=True))
        name = bldg or (getattr(layout, 'caption', '') or '')
        if name:
            # ★★ 2026-10-12（用户）：「**建筑的名字标记都放到墙的旁边**
            #   **不要放到别的东西的上面**」。
            #   原来它画在框的**上方外面**（`fy0 - 5.5`）—— 那是"飘在图上"，
            #   不是"在墙上"，而且会跟图上的其它元素抢位置。
            #   现在用 `_on_wall()` 写进**框的内侧上沿**（= 贴着这面墙），
            #   底下垫一块纸色挡住墙线与房间上沿（平面图的标注框就是这么做）。
            # [EN] ★★ 2026-10-12 (the user): "**put the building's name label beside the wall**,
            # [EN] **not on top of other things**".
            # [EN] It used to be drawn **outside, above the frame** (`fy0 - 5.5`) -- that is
            # [EN] "floating on the map", not "on the wall", and it competed for room with the other
            # [EN] elements.
            # [EN] Now `_on_wall()` writes it onto the **inside of the frame's top edge** (= hugging
            # [EN] that wall), on a paper-coloured patch that hides the wall line and the room's top
            # [EN] edge (exactly how a floor plan annotates).
            _on_wall(shapes, fx0 + 8, fy0, fy1 - fy0, name, pal=pal,
                     color=pal['frame'], font=font, size=10, bold=True)

    # ── ① 水系（最底层，压在通路与地点下面）──
    # [EN] ── ① Water system (bottommost layer, pressed under paths and locations) ──
    if len(layout.water if layout else []) >= 2:
        shapes.append(fcv.Path(
            [fcv.Path.MoveTo(pad_x + x * (W - 2 * pad_x),
                             pad_y + y * (H - 2 * pad_y - 8))
             for x, y in layout.water],
            paint=ft.Paint(color=pal['water'], stroke_width=3.0,
                           stroke_cap=ft.StrokeCap.ROUND,
                           style=ft.PaintingStyle.STROKE)))

    # ── ② 墙：**室外墙（院墙）** ──
    # [EN] ── ② Walls: the **outdoor wall (courtyard wall)** ──
    #  ★★ 用户 2026-10-12：「如果是**室内和室外结合**的地图 … **则把室内墙和室外墙
    #    都画出来**」。所以室内外这种图上，室外墙由**院子里的那些点**自己聚出来
    #    （`_outdoor_extent`），画成一条**实线**（院墙是砌出来的，不是虚线）；
    #    `室内` 那种图没有院子，就没有室外墙。
    #  ⚠ **局部 / 整体**两类**不据此画** —— 老行为一点没变（`layout.walls` 照旧）。
    # [EN] ★★ The user on 2026-10-12: "if it is a map **combining indoors and outdoors** ... **then
    # [EN] draw both the indoor walls and the outdoor walls**". So on an indoor+outdoor map, the
    # [EN] outdoor wall is gathered from **the points in the courtyard** (`_outdoor_extent`) and drawn
    # [EN] as a **solid line** (a courtyard wall is built, not dashed); the `室内` kind has no
    # [EN] courtyard, hence no outdoor wall.
    # [EN] ⚠ **local / whole** maps are **not** drawn this way -- the old behaviour is untouched
    # [EN] (`layout.walls` as before).
    yard_box = (plan.yard if plan and plan.yard is not None else None) \
        if detail == DETAIL_IN_OUT else None
    if yard_box is not None:
        yx0, yy0, yx1, yy1 = yard_box
        shapes.append(fcv.Rect(yx0, yy0, yx1 - yx0, yy1 - yy0, border_radius=2.0,
                               paint=ft.Paint(color=pal['wall'], stroke_width=1.4,
                                              style=ft.PaintingStyle.STROKE)))
        # 院墙写个"院"字（不然一圈框看不出是院墙还是第二层楼）
        # [EN] Write a small mark on the courtyard wall (otherwise a ring is indistinguishable from a
        # [EN] second storey)
        shapes.append(_text(yx0 + 3, yy0 + 1.5, '院', size=8, color=pal['wall'],
                            font=font))

    # ★★ 2026-10-16（用户）：跨城市这一档小图**不画街道网**——街道网留给大地图
    #   （"大地图才会画城市里的街道"）。小图只围出城市轮廓（见 ③b）。所以这一段的
    #   街道/院墙外框线在 'city' 档跳过。
    # [EN] ★★ 2026-10-16 (the user): the cross-city minimap **does not draw the street network** --
    # [EN] the streets belong to the big map ("the big map is what draws the city's streets"). The
    # [EN] minimap only encloses the city outline (see ③b). So this street/courtyard frame line is
    # [EN] skipped for the 'city' tier.
    if lod != 'city' and len(layout.walls if layout else []) >= 3:
        els = [fcv.Path.MoveTo(pad_x + layout.walls[0][0] * (W - 2 * pad_x),
                              pad_y + layout.walls[0][1] * (H - 2 * pad_y - 8))]
        els += [fcv.Path.LineTo(pad_x + x * (W - 2 * pad_x),
                                pad_y + y * (H - 2 * pad_y - 8))
                for x, y in layout.walls[1:]]
        els.append(fcv.Path.Close())
        shapes.append(fcv.Path(
            els, paint=ft.Paint(color=pal['wall'], stroke_width=1.0,
                                stroke_dash_pattern=[3, 3],
                                style=ft.PaintingStyle.STROKE)))

    # ── ③ 通路 ──
    # [EN] ── ③ Paths ──
    #
    # ★★★ 2026-10-27（用户）：「小地图效果是一些不规则图形」——
    #   一是下面 ③b 那个**凸包**（已删，见那一段的说明），
    #   二是**路**：原来一律 1.0px 虚线，与大地图的三档分级双线毫无关系，
    #   于是"小图和大图不像同一张地图"。
    #   ⇒ 城市/城际档改走**与大地图同一份分级**（`scale.road_class` + `ROAD_SPEC`），
    #     按画布比例缩到小图能看的粗细（`_mini_road_k`）。
    #   ⚠ 室内外的"桥"记号照旧：那是通路的一种**性质**（过河），不是等级。
    # [EN] ★★★ 2026-10-27 (the user): "the minimap shows some irregular shapes" -- one cause is the
    # [EN] **convex hull** in ③b (removed; see that block), the other is the **roads**: they used to
    # [EN] be a flat 1.0px dashed line unrelated to the big map's three-tier graded double lines, so
    # [EN] "the minimap and the big map do not look like the same map". => On the city/region tiers the
    # [EN] minimap now uses **the same classification as the big map** (`scale.road_class` +
    # [EN] `ROAD_SPEC`), scaled down by `_mini_road_k` to a width that reads on a small canvas.
    # [EN] ⚠ The in/outdoor "bridge" mark stays as it was: it is a **property** of the path (crosses
    # [EN] water), not a rank.
    # ★★★ 2026-10-27（用户：「道路正常画 而不是直接连接几个目标建筑」）：
    #   小地图也必须用**同一张街网**。原来它画的是 `layout.links` 的直线 ——
    #   于是小图上是"A 到 B"的斜线，大地图上是街网，两张图说的不是同一座城。
    #   现在：城市档直接取 `scalemap.streetnet` 的骨架（只画主干道与次干道，
    #   不画巷 —— 小图表达"城市形状"，细节交给大地图）。
    # [EN] ★★★ 2026-10-27 (the user: "draw the roads normally, not as direct links between a few
    # [EN] buildings"): the minimap must use the **same network**. It used to draw `layout.links`
    # [EN] straight lines, so the small map showed "A to B" diagonals while the big map showed a street
    # [EN] grid -- two different towns. Now the city tier takes `scalemap.streetnet`'s skeleton
    # [EN] (trunk and secondary only, no alleys): the minimap conveys the town's shape, detail belongs
    # [EN] to the big map.
    _mini_k = None
    _style = None
    if lod == 'city':
        # 缩放系数 = 小图画布 / 大地图画布（大地图基准 940，见 `floorplan.W`）。
        # ⚠ 不按地点数或内容多少调，只按画布比例 —— 否则同一条路在两天之间会变粗细。
        # [EN] Scale = minimap canvas / big map canvas (the big map's base is 940, see
        # [EN] `floorplan.W`). ⚠ It depends on the canvas ratio only, never on the number of places,
        # [EN] or one road would change width from one day to the next.
        _mini_k = (float(W) / 940.0) if W else 0.21
        try:
            # 风格决定"等级词表"（西幻的 keep 与中式的关不是一回事）
            # [EN] The profile selects the rank vocabulary (a Western keep is not a Chinese pass)
            _style = WS.for_layout(layout, places).style
        except Exception:                                     # noqa: BLE001
            _style = None
    if lod == 'city':
        # 街网骨架：与大地图**同一次调用的同一种算法**（街距按小图比例缩）
        # [EN] Network skeleton: the same algorithm as the big map (spacing scaled to the small canvas)
        try:
            _sx = float(W) / 940.0
            _net = SM.net_of(_style)
            _doc = SM.streetnet((pad_x, pad_y, W - pad_x, H - pad_y - 8),
                                net=_net, target=max(34.0, SM.SN_TARGET * _sx))
            for _pts, _cls in _doc['roads']:
                if _cls == SC.RC_LOCAL:
                    continue
                _outer, _inner, _c = SC.ROAD_SPEC[_cls]
                _outer *= max(0.30, _sx) * 0.9
                _inner *= max(0.30, _sx) * 0.9
                _el = [fcv.Path.MoveTo(_pts[0][0], _pts[0][1])]
                _el += [fcv.Path.LineTo(x, y) for x, y in _pts[1:]]
                shapes.append(fcv.Path(list(_el), paint=ft.Paint(
                    color=pal['link'], stroke_width=_outer,
                    stroke_cap=ft.StrokeCap.ROUND, style=ft.PaintingStyle.STROKE)))
                shapes.append(fcv.Path(list(_el), paint=ft.Paint(
                    color=pal['paper'], stroke_width=_inner,
                    stroke_cap=ft.StrokeCap.ROUND, style=ft.PaintingStyle.STROKE)))
        except Exception:                                     # noqa: BLE001
            pass
    for lk in (layout.links if layout else []):
        a, b = pos.get(lk.get('a')), pos.get(lk.get('b'))
        if not (a and b):
            continue
        is_bridge = lk.get('kind') == '桥'
        if is_bridge:
            shapes.append(fcv.Line(a[0], a[1], b[0], b[1],
                                   paint=ft.Paint(color=pal['water'], stroke_width=1.6,
                                                  style=ft.PaintingStyle.STROKE)))
            continue
        if _mini_k is not None:
            # 城市档的路已经由街网画过了；`links` 在这里**不再画**（它就是"两地点连线"，
            # 正是用户否掉的那种画法）。只有"桥"这种**属性**还留在 links 上，上面已单独处理。
            # [EN] The city tier's roads were drawn above from the network; `links` draws **nothing**
            # here -- it is exactly the "two places joined by a line" idiom the user rejected. Only the
            # "bridge" **property** still lives on links, handled separately above.
            continue
        shapes.append(fcv.Line(a[0], a[1], b[0], b[1],
                               paint=ft.Paint(
                                   color=pal['link'],
                                   stroke_width=1.0,
                                   stroke_dash_pattern=[2, 2],
                                   style=ft.PaintingStyle.STROKE)))

    # ── ③b ★★★ 2026-10-27：**删掉"城市轮廓"那个凸包** ──
    #
    #   用户原话：「小地图效果是**一些不规则图形**」—— 主因就是这一段：它画的是
    #   **所有地点点的凸包**（`_convex_hull`），而那既不是城墙也不是城市边界：
    #     · 它随地点个数与位置变形（三个点就是三角，五个点是五边形）；
    #     · 它没有任何数据依据 —— **我们不知道这座城的边界在哪**；
    #     · 它还会连成一条"包住所有点"的边，让读者以为那是一条城墙或环路。
    #   2026-10-16 加它时的诉求是"小图把城市这一摊画出来就行"，但**凸包实现错了**：
    #   要的是"别画街道"，不是"画一个假的边界"。
    #   ⇒ 现在小图只画**真有的东西**：路（按等级）、地点名、水系、以及作者真给了的
    #     `layout.walls`（② 段，虚线）。没有边界数据就不画边界 —— 这与"不编造"同一条纪律。
    #   ⚠ `verify_space_rules` 有一条按"城市档不画大矩形框"判过的判据，删掉它只会更绿。
    # [EN] ── ③b ★★★ 2026-10-27: **the "city outline" convex hull is gone** ──
    # [EN] The user: "the minimap shows **some irregular shapes**" -- this block was the main cause:
    # [EN] it drew the **convex hull of the location points**, which is neither a city wall nor a city
    # [EN] boundary: it warps with the number and positions of the points; it has **no data behind it**
    # [EN] (we do not know where this city ends); and it draws an edge "wrapping all the points", which
    # [EN] reads as a wall or a ring road. The 2026-10-16 request behind it was "the minimap only needs
    # [EN] the city blob", but the implementation was wrong: the point was "do not draw streets", not
    # [EN] "draw a fake boundary". => The minimap now draws **only what exists**: roads (by rank),
    # [EN] place names, water, and `layout.walls` when the author really provided them (section ②,
    # [EN] dashed). No boundary data, no boundary -- the same "never fabricate" rule.

    # ── ④ 地点：**只写小字，不画点** ──
    # [EN] ── ④ Locations: **small labels only, no dots** ──
    #  ★★★ 用户 2026-10-12（这是他**第三次**报红点）：
    #    「小地图里标记〔某座楼〕和**旁边的红点**还是存在 去掉它
    #      如果想要**标记地点** **用小字标记**就行了 **不要用点**」。
    #    前两轮去掉的是"整座楼那个红点"（室内图改画框）与"假地点那个红点"
    #    （子地点名字对不上时补出来的大楼）。但**地点自己的图形记号**有两处还留着：
    #      · `_glyph()` 给每个地点画的字形（圆/方/三角/坡…）；
    #      · 当前地点垫的那层**朱砂实心圆**。
    #    在**局部**图上这两样叠在一起，屏幕上就是"名字旁边一个红点" ——
    #    用户这次说得最明白：**地点不要用点标，用小字标**。
    #  ⇒ 这一轮把**地点的图形记号全部去掉**：
    #      · 小地图**不再调用 `_glyph()`**（大地图照旧 —— 那是标准平面图，
    #        符号是地图语言的一部分，用户上一轮明确要求的"按标准室内装修或
    #        室外普通地图的绘制方法绘制"）；
    #      · 当前地点**不再垫朱砂圆**，改用**朱砂色 + 加粗**的字（见下面那行 `bold`）。
    #    "这是哪儿"由**文字**承担；"我现在在哪"由**字色与字重**承担 —— 都不靠圈。
    #  ⚠ 不动的两样，各有理由：
    #      · **墙**（建筑外框 / 房间矩形 / 院墙）：用户明确要求画，而且那是**结构**
    #        不是"地点标记"；
    #      · **陈设的小方块**（柜台/条案/灶）：那是室内平面图的家具画法，
    #        它标的是**物件**不是地点，颜色也是墨色不是朱砂。
    # [EN] ★★★ The user on 2026-10-12 (his **third** report of a red dot):
    # [EN] "the label for [a building] and **the red dot next to it** are still there; remove it. If
    # [EN] you want to **mark a location**, **just mark it with small text** -- **do not use dots**."
    # [EN] The previous two rounds removed "the red dot for the whole building" (indoor maps now draw a
    # [EN] frame) and "the red dot for a fake place" (the big building appended when a sub-location
    # [EN] name failed to match). But **two graphical marks for the locations themselves** remained:
    # [EN] · the glyph `_glyph()` drew for every location (circle / square / triangle / slope ...);
    # [EN] · the **cinnabar filled circle** padded under the current location.
    # [EN] On a **local** map the two stack up, and on screen that is "a red dot next to the name" --
    # [EN] the user put it most plainly this time: **do not mark locations with dots, use small text**.
    # [EN] ⇒ This round removes **all graphical marks for locations**:
    # [EN] · the minimap **no longer calls `_glyph()`** (the big map still does -- that is a standard
    # [EN]   floor plan, where symbols are part of the map's language, as the user asked last round:
    # [EN]   "draw it following the standard interior-decoration or ordinary outdoor map method");
    # [EN] · the current location **no longer gets a cinnabar circle**; it is shown by a **cinnabar,
    # [EN]   bold** label instead (see the `bold` in the line below).
    # [EN] "Where is this" is carried by **text**; "where am I now" by **colour and weight** -- neither
    # [EN] by a circle.
    # [EN] ⚠ Two things are deliberately left alone, each for a reason:
    # [EN] · the **walls** (building frame / room rectangles / courtyard wall): the user explicitly
    # [EN]   asked for them, and they are **structure**, not a "location marker";
    # [EN] · the **small fixture blocks** (counter / side table / stove): that is the standard floor
    # [EN]   plan way of drawing furniture; they mark **objects**, not locations, and they are in ink,
    # [EN]   not cinnabar.
    name_font = 9
    # ★★ 2026-10-16（用户）：小地图**也**用碰撞避让（"小地图也是这个设计"）。
    #   每个"其余地点"的名字，避开房间墙、陈设块、建筑框、以及已经写下的别的名字，
    #   在 8 个候选位里挑首个不重叠的（都重叠则取重叠最小者）。名字始终贴着它的点。
    # [EN] ★★ 2026-10-16 (the user): the minimap **also** uses collision avoidance
    # [EN] ("the minimap uses the same design"). Each "other location" name avoids room walls,
    # [EN] fixture blocks, the building frame, and other names already written, picking the first
    # [EN] non-overlapping among 8 candidates (least-overlapping if all overlap). The name stays by
    # [EN] its point.
    _drawn_labels: list = []
    _frame_box = (fx0, fy0, fx1, fy1)
    _fixture_rects = [
        (fxc - FIXTURE_W / 2, fyc - FIXTURE_H / 2,
         fxc + FIXTURE_W / 2, fyc + FIXTURE_H / 2)
        for (_owner, (fxc, fyc)) in (plan.fixtures.values() if plan else [])
    ]
    for p in places:
        # ★ 室内图上，**整座楼**与**门**都已经画在框上了（见 ⓪）—— 这里跳过，
        #   不然那两样会在框里再长出一个点，把房间挤掉（正是用户报的那个毛病）。
        # [EN] ★ On an indoor map, **the whole building** and **the gate** are already drawn on the
        # [EN] frame (see ⓪) -- skip them here, otherwise both sprout another dot inside the frame and
        # [EN] squeeze the rooms out (exactly the defect the user reported).
        if indoor and (p.name == bldg or _is_gate(p.name)):
            continue
        cx, cy = pos[p.name]
        r = 6.0 * _SIZE_SCALE.get(p.size, 1.0) * _SHAPE_SCALE.get(p.shape, 1.0)
        here = bool(current) and p.name == current
        ink = pal['here'] if here else pal['ink']

        # ★★ 房间里见顶、院子里见天：室内图上给**屋外的**垫一层浅底，
        #   不用读字就能看出哪块在墙外（用户点名"严格区分室内室外"）。
        # [EN] ★★ Rooms have a roof, the yard has open sky: on an indoor map give **outdoor** places a
        # [EN] light wash so you can tell what is beyond the wall without reading a word (the user
        # [EN] named this: "strictly distinguish indoors and outdoors").
        if indoor and _is_outdoor(p.name):
            shapes.append(fcv.Rect(cx - r * 1.7, cy - r * 1.35, r * 3.4, r * 2.7,
                                   border_radius=3.0,
                                   paint=ft.Paint(color=pal['yard'],
                                                  style=ft.PaintingStyle.FILL)))

        # ★★★ 房间：**画墙**（用户 2026-10-12「如果是室内地图 则请把墙画出来」）──
        #   房间不再画成一个点，而是**一个矩形**（`room_walls` 算出来的，相邻两间
        #   共边 ⇒ 看着就是共用一堵墙）。名字写在**房间里**（平面图就是这么标的）。
        #   ⚠ 当前那一间**不再垫朱砂圈**（用户第三次报红点：地点不要用点）——
        #     改用**朱砂色的字 + 加粗**；墙线本身也跟着转朱砂，一眼看得出是哪一间。
        # [EN] ★★★ Rooms: **draw the walls** (the user on 2026-10-12: "if it is an indoor map, then
        # [EN] please draw the walls") --
        # [EN]   a room is no longer a point but **a rectangle** (computed by `room_walls`; two
        # [EN]   adjacent rooms share an edge, which reads as a shared wall). The name goes **inside the
        # [EN]   room** (that is how a floor plan labels them).
        # [EN]   ⚠ The current room **no longer gets a cinnabar circle** (the user's third red-dot
        # [EN]   report: do not mark locations with dots) -- it is shown by a **cinnabar, bold** label;
        # [EN]   the wall line turns cinnabar too, so which room it is reads at a glance.
        box = room_boxes.get(p.name)
        if box is not None:
            bx0, by0, bx1, by1 = box
            shapes.append(fcv.Rect(bx0, by0, bx1 - bx0, by1 - by0, border_radius=1.5,
                                   paint=ft.Paint(color=ink if here else pal['frame'],
                                                  stroke_width=1.1,
                                                  style=ft.PaintingStyle.STROKE)))
            # ★ 房间名**贴房间的上墙内侧**（2026-10-12 用户：「名字标记都放到墙的旁边
            #   不要放到别的东西的上面」）—— 原来写在房间正中，会压住房间里的东西。
            # [EN] ★ The room name **hugs the inside of the room's top wall** (the user on
            # [EN] 2026-10-12: "put the name labels beside the wall, not on top of other things") --
            # [EN] it used to be dead centre, pressing onto whatever was in the room.
            _on_wall(shapes, (bx0 + bx1) / 2, by0 + 1, by1 - by0,
                     p.name if here else p.label(), pal=pal,
                     color=pal['here'] if here else pal['ink'],
                     font=font, size=name_font, center=True, bold=here)
            continue

        # ★ 陈设（柜台 / 侧案 / 柜格 / 灶）：归屋里，但它是**家具**不是房间 ——
        #   画一个小方块（`FIXTURE_*` 刻意小于判据的浅底窗口，理由见那个常量）。
        #   位置用 `plan.fixtures`（由 `plan_audit.solve` 落进所属房间），
        #   不再画在原位 —— 原位是"没有墙"的地方，正是用户报的"家具在墙外"。
        # ★★ 2026-10-16（用户）：小图比大图**简略一级**，室内小图省略屋里小家具
        #   （"内部夹具太小了可以不带 小地图就把房子或者房子以上的东西画好就可以"）。
        #   家具是"房子以下"的细节，大图照画，小图可省 —— 房间墙/院子仍按地图标准画。
        # [EN] ★ Fixtures (counter / side table / cabinet / stove): they belong indoors but are
        # [EN] **furniture**, not rooms -- drawn as a small block (`FIXTURE_*` is deliberately smaller
        # [EN] than the criterion's wash window, see that constant). The position comes from
        # [EN] `plan.fixtures` (landed inside its room by `plan_audit.solve`), not the original spot --
        # [EN] the original spot is "where there is no wall", exactly the user's "furniture outside the
        # [EN] wall".
        # [EN] ★★ 2026-10-16 (the user): the minimap is one tier simpler than the big map, so the
        # [EN] indoor minimap omits small indoor fixtures ("tiny fixtures may be left out; the minimap
        # [EN] only needs to show the building or above"). Furniture is sub-building detail: the big map
        # [EN] draws it, the minimap may skip it -- room walls / courtyard still follow map standards.
        if detail in (DETAIL_IN, DETAIL_IN_OUT) and _is_fixture(p.name) and lod != 'building':
            fp = plan.fixtures.get(p.name) if plan else None
            if fp is not None:
                cx, cy = fp[1]            # 在所属房间里（solve 算的）
            else:
                cx, cy = pos[p.name]      # 没有房间可放时退回原位
            fw, fh = FIXTURE_W, FIXTURE_H
            shapes.append(fcv.Rect(cx - fw / 2, cy - fh / 2, fw, fh,
                                   border_radius=1.0,
                                   paint=ft.Paint(color=ink,
                                                  style=ft.PaintingStyle.FILL)))
            shapes.append(_text(cx, cy + fh / 2 + 2.5,
                                p.name if here else p.label(), size=8,
                                color=pal['here'] if here else pal['muted'],
                                font=font, center=True, bold=here))
            continue

        # ★★★ 其余地点：**只有一行小字**（用户：「用小字标记就行了 不要用点」）。
        #   原来这里有三样东西 —— 朱砂圈、`_glyph` 画的字形、点下方的名字；
        #   现在只剩最后一样，而且**居中写在原来的位置**（原来在点下方，因为上面有点）。
        #   ⚠ 字色/字重就是全部的层级信息了：当前地点朱砂 + 加粗 + 大一号。
        # [EN] ★★★ All other locations: **just a line of small text** (the user: "just mark it with
        # [EN] small text -- do not use dots").
        # [EN]   There used to be three things here -- the cinnabar circle, the glyph drawn by `_glyph`,
        # [EN]   and the name below the dot; now only the last remains, **centred at the original spot**
        # [EN]   (it used to sit below the dot, because the dot was above it).
        # [EN]   ⚠ Colour and weight are now the entire hierarchy: the current location is cinnabar,
        # [EN]   bold, one size larger.
        # ★★ 名字**贴着它的点**、但避开房间墙 / 陈设块 / 建筑框 / 别的名字
        #   （用户：「放到外面的时候也要注意不要跟现有的东西覆盖」「小地图也是这个设计」）。
        #   参考框取这一地点那个小点（半径约 r），8 个候选位里挑首个不重叠者；
        #   都重叠则取重叠最小者。`bounds` 限制在画布可见区内，免得被裁掉。
        # [EN] ★★ The name **hugs its point** but avoids room walls / fixture blocks / the building
        # [EN] frame / other names (the user: "when outside, also take care not to cover existing things"
        # [EN] and "the minimap uses the same design"). The reference box is this location's small dot
        # [EN] (radius ~r); among 8 candidates pick the first non-overlapping; least-overlapping if all
        # [EN] overlap. `bounds` keeps it inside the visible canvas so it is not clipped.
        _disp = p.name if here else p.label()
        _lsz = name_font + (1 if here else 0)
        _lw, _lh = LP.est_text_size(_disp, _lsz)
        _ptbox = (cx - r, cy - r, cx + r, cy + r)
        _occ = ([v for v in room_boxes.values()]
                + _fixture_rects + [_frame_box] + _drawn_labels)
        _lx, _ly = LP.place_label(_ptbox, _lw, _lh, _occ,
                                  bounds=(8.0, 8.0, W - 8.0, H - 14.0),
                                  prefer='bottom')
        _drawn_labels.append((_lx, _ly, _lw, _lh))
        shapes.append(_text(_lx, _ly, _disp, size=_lsz,
                            color=pal['here'] if here else pal['ink'],
                            font=font, center=True, bold=here))

    # ── ⑤ 在场人物（小点）──
    # [EN] ── ⑤ Present characters (small dots) ──
    #  ★ 2026-10-12：地点改成"只有一行字"之后，人物点不能再按"绕着地点字形转"来摆
    #    （那个字形已经没有了）—— 改成**排在地点名字的上一行**，多人横向排开。
    #  ⚠ 顺带修掉一个**既有 bug**：原来那两行用的是 `r`，而 `r` 是**上面那个
    #    地点循环里最后一次赋的值**（循环变量泄漏到外面）—— 于是"人物点离地点的
    #    距离"取决于**最后一个地点**的大小，与本人所在的地点无关。现在人物点不再用 `r`。
    # [EN] ★ 2026-10-12: now that a location is just one line of text, the character dots cannot be
    # [EN] placed "orbiting the location's glyph" any more (that glyph is gone) -- they go **on the line
    # [EN] above the location's name**, spread out horizontally for several people.
    # [EN] ⚠ Also fixes a **pre-existing bug**: those two lines used `r`, and `r` was **whatever the
    # [EN] location loop assigned last** (the loop variable leaked outside) -- so "how far the character
    # [EN] dots sit from the location" depended on the size of the **last** location, not the one the
    # [EN] person was actually in. The character dots no longer use `r`.
    cast = [c for c in (cast or []) if c]
    if cast:
        shown = cast[:4]
        spread = 6.0
        for i, who in enumerate(shown):
            dst = (cast_place or {}).get(who) or current
            base = pos.get(dst) or pos.get(current)
            if base is None:
                continue
            dx = base[0] + (i - (len(shown) - 1) / 2) * spread
            dy = base[1] - CAST_LIFT
            shapes.append(fcv.Circle(dx, dy, dot_r,
                                     paint=ft.Paint(color=pal['cast_a'],
                                                    style=ft.PaintingStyle.FILL)))

    # ── ⑥ 题记 / 标题 ──
    # [EN] ── ⑥ Inscription / title ──
    # ★★★ 2026-10-27：「题记」的语义是**地名或河名**，但上游给的是模型自由填的字符串。
    #   实测某份室内图的题记是 **"壶在"** —— 一个不成词的碎片（模型把提示词里的
    #   "两个字的题记"当成指令去凑了两个字）。图上多这么一块字，读者只会以为画错了。
    #   ⇒ 只在它**确实是这一图上的名字**时才画：等于某个地点名、或含在某个地点名/
    #     图名里、或是某处名字的一部分。否则**不画**（少一行题记，好过多一行错字）。
    #   ⚠ 判据放在**画的时候**，而不是清洗上游 —— 老缓存里已经有"壶在"这种值，
    #     清洗上游只对以后的数据有效。
    # [EN] ★★★ 2026-10-27: a "题记" means **a place name or a river name**, but upstream passes
    # [EN] whatever string the model filled in. Measured, one indoor plan's inscription was **"壶在"**
    # [EN] -- a meaningless fragment (the model read "a two-character inscription" in the prompt as an
    # [EN] instruction to produce two characters). A stray block of text like that just looks like a
    # [EN] drawing error. => Draw it only when it **really is a name on this map**: equal to a place
    # [EN] name, contained in one, or a substring of one. Otherwise **draw nothing** (better one line
    # [EN] missing than one wrong line). ⚠ The check lives **at drawing time**, not as an upstream
    # [EN] cleanup: old caches already contain values like "壶在", and cleaning upstream would only help
    # [EN] future data.
    cap = (layout.caption if layout else '') or ''
    if cap and not _caption_ok(cap, layout):
        cap = ''
    if cap:
        shapes.append(_text(3, H - 13, cap, size=9, color=pal['muted'],
                            font=font))
    if title:
        shapes.append(_text(W - 3, 2, title, size=9, color=pal['muted'],
                            font=font, right=True))
    return shapes


def _caption_ok(cap: str, layout) -> bool:
    """这条"题记"**配不配画在图上**（它是地名/河名吗）。

    ★ 判法：与某个地点名互为子串，或与框上的建筑名互为子串 ⇒ 算。
      含"·"的（`地点·空间` 写法）取前半截再判 —— 上游确实会这么写。
    ★ 为什么用"互为子串"而不是完全相等：题记常是"清河"而地点叫"清河渡"，
      或题记"南门市集"而地点叫"市集"。互为子串能同时容下这两种。
    ★ 为什么不做"字数上限"之类的启发式：`壶在` 只有两字，长度判据完全抓不住它
      （那正是它混进来的方式）。**语义判据才抓得住**。
    [EN] Should this inscription be drawn at all (is it a place or river name)? ★ Rule: it counts
    [EN] when it and some place name (or the framed building name) are substrings of each other -- a
    [EN] "place·space" form is cut at the middle dot first, since upstream writes it that way.
    [EN] ★ Why mutual substring rather than equality: the inscription is often 清河 while the place is
    [EN] 清河渡, or the inscription is 南门市集 while the place is 市集. ★ Why no length heuristic:
    [EN] `壶在` is only two characters, so a length rule cannot catch it -- which is exactly how it got
    [EN] in. Only a semantic rule can.
    """
    s = str(cap or '').strip()
    if not s:
        return False
    if '·' in s:
        s = s.split('·')[0].strip()
    if not s:
        return False
    cands = [str(getattr(p, 'name', '') or '') for p in
             (getattr(layout, 'places', None) or [])]
    cands.append(str(getattr(layout, 'frame', '') or ''))
    for n in cands:
        n = n.strip()
        if not n:
            continue
        if s == n or s in n or n in s:
            return True
    # 水系是一条折线，没有名字；只要题记里有"河/江/湖/溪/海"且不短于两字，算（河名本来就没处可查）
    # [EN] Water is an unnamed polyline, so accept a water-ish word of two or more characters (there is
    # [EN] nowhere to look a river name up)
    if len(s) >= 2 and any(c in s for c in '河江湖溪海川渡港'):
        return True
    return False


def _glyph(shape: str, cx: float, cy: float, r: float, ink: str,
           *, paper: str) -> list:
    """一个地点的**字形**。

    十一款字形全在这里（`map_layout.SHAPES` 是白名单，渲染这一侧一一对应）。
    线条一律细（1.2px）：200px 宽的画布上，粗线会让整张图糊成一块。

    ⚠⚠ **小地图不再调用它**（2026-10-12，用户第三次报红点）：
      用户原话是「如果想要**标记地点** **用小字标记**就行了 **不要用点**」——
      小地图上地点现在**只有一行小字**（见 `build_shapes` 的 ④ 段）。
      它现在唯一的调用者是**大地图**（`image_gen/floorplan.py` 的 `_symbol`）：
      那儿画的是**标准平面图**，符号是地图语言的一部分（用户上一轮明确要求
      "按标准室内装修或者室外普通地图的绘制方法绘制"）。
      ⇒ 所以这个函数**不是死代码**，但它的读者只有一处；改它之前先确认
         `grep -rn "_glyph" --include=*.py .` 的结果。

        English:
    A location's **glyph**.
        All eleven glyphs are here (`map_layout.SHAPES` is the whitelist, rendering side corresponds one-to-one).
        Lines are uniformly thin (1.2px): on a 200px-wide canvas, thick lines smear the whole map into one blob.
        ⚠⚠ **The minimap no longer calls it** (2026-10-12, the user's third red-dot report): the user's
        exact words were "if you want to **mark a location**, **just mark it with small text** -- **do
        not use dots**" -- on the minimap a location is now **just one line of small text** (see section
        ④ of `build_shapes`).
        Its only caller now is the **big map** (`_symbol` in `image_gen/floorplan.py`): that draws a
        **standard floor plan**, where symbols are part of the map's language (the user asked last round
        for "drawing it following the standard interior-decoration or ordinary outdoor map method").
        ⇒ So this function is **not dead code**, but it has only one reader; before changing it, check
          what `grep -rn "_glyph" --include=*.py .` says.
    """
    line = ft.Paint(color=ink, stroke_width=1.2,
                    stroke_cap=ft.StrokeCap.ROUND, style=ft.PaintingStyle.STROKE)
    fill = ft.Paint(color=ink, style=ft.PaintingStyle.FILL)
    hollow = ft.Paint(color=paper, style=ft.PaintingStyle.FILL)
    out: list = []

    def rect(x, y, w, h, *, filled=True, radius=1.0):
        out.append(fcv.Rect(x, y, w, h, border_radius=radius,
                            paint=fill if filled else hollow))

    if shape == '院':                       # 院：大方框，里面空着
    # [EN] Courtyard: large square frame, empty inside
        out.append(fcv.Rect(cx - r, cy - r * 0.75, 2 * r, 1.5 * r,
                            border_radius=1.5, paint=hollow))
        out.append(fcv.Rect(cx - r, cy - r * 0.75, 2 * r, 1.5 * r,
                            border_radius=1.5, paint=line))
    elif shape == '亭':                     # 亭：屋顶 + 两根柱子
    # [EN] Pavilion: roof + two pillars
        out.append(fcv.Path([fcv.Path.MoveTo(cx - r, cy),
                             fcv.Path.LineTo(cx, cy - r),
                             fcv.Path.LineTo(cx + r, cy)], paint=line))
        out.append(fcv.Line(cx - r * 0.6, cy, cx - r * 0.6, cy + r * 0.8, paint=line))
        out.append(fcv.Line(cx + r * 0.6, cy, cx + r * 0.6, cy + r * 0.8, paint=line))
    elif shape == '门':                     # 门：门框两柱 + 门楣
    # [EN] Gate: two door-frame pillars + lintel
        out.append(fcv.Line(cx - r, cy + r * 0.7, cx - r, cy - r * 0.7, paint=line))
        out.append(fcv.Line(cx + r, cy + r * 0.7, cx + r, cy - r * 0.7, paint=line))
        out.append(fcv.Line(cx - r, cy - r * 0.7, cx + r, cy - r * 0.7, paint=line))
    elif shape == '桥':                     # 桥：一道拱
        # ⚠ `fcv.Arc(x, y, w, h, start, sweep)` 的 `x/y` 是**外接矩形左上角**、
        #   角度是**弧度**，且 0 = 正右方、**顺时针为正**（屏幕坐标 y 向下）。
        #   所以"上半拱" = 从 π（左）扫 π（经过 3π/2 = 正上方）到 2π（右）。
    # [EN] Bridge: one arch
    # [EN] ⚠ In `fcv.Arc(x, y, w, h, start, sweep)`, `x/y` is the **top-left corner of the bounding
    # [EN] rectangle**,
    # [EN] angles are in **radians**, and 0 = due right, **clockwise is positive** (screen coordinates have
    # [EN] y pointing down).
    # [EN] So "upper half arch" = sweep from π (left) through π (passing 3π/2 = straight up) to 2π (right).
        out.append(fcv.Arc(cx - r, cy - r * 0.5, 2 * r, 1.8 * r,
                           start_angle=math.pi, sweep_angle=math.pi, paint=line))
        out.append(fcv.Line(cx - r, cy + r * 0.4, cx + r, cy + r * 0.4, paint=line))
    elif shape == '渡':                     # 渡：岸线 + 一条小船
    # [EN] Ferry: shoreline + one small boat
        out.append(fcv.Line(cx - r, cy + r * 0.75, cx + r, cy + r * 0.75, paint=line))
        out.append(fcv.Path([fcv.Path.MoveTo(cx - r * 0.5, cy + r * 0.4),
                             fcv.Path.LineTo(cx + r * 0.5, cy + r * 0.4),
                             fcv.Path.LineTo(cx + r * 0.3, cy + r * 0.72),
                             fcv.Path.LineTo(cx - r * 0.3, cy + r * 0.72),
                             fcv.Path.Close()], paint=fill))
    elif shape == '树':                     # 树：一截树干 + 一团树冠
    # [EN] Tree: a trunk segment + a canopy blob
        out.append(fcv.Line(cx, cy + r * 0.8, cx, cy - r * 0.1, paint=line))
        out.append(fcv.Circle(cx, cy - r * 0.45, r * 0.55,
                              paint=ft.Paint(color=ink,
                                             style=ft.PaintingStyle.FILL)))
    elif shape == '山':                     # 山：三角
    # [EN] Mountain: triangle
        out.append(fcv.Path([fcv.Path.MoveTo(cx - r, cy + r * 0.7),
                             fcv.Path.LineTo(cx, cy - r * 0.8),
                             fcv.Path.LineTo(cx + r, cy + r * 0.7),
                             fcv.Path.Close()], paint=fill))
    elif shape == '塔':                     # 塔：细身 + 尖顶
    # [EN] Pagoda: slender body + pointed top
        rect(cx - r * 0.42, cy - r * 0.2, r * 0.84, r * 1.3, radius=0.5)
        out.append(fcv.Path([fcv.Path.MoveTo(cx - r * 0.68, cy - r * 0.2),
                             fcv.Path.LineTo(cx, cy - r * 1.1),
                             fcv.Path.LineTo(cx + r * 0.68, cy - r * 0.2)],
                            paint=line))
    elif shape == '台':                     # 台：双层方台
    # [EN] Platform: two-tier square platform
        rect(cx - r, cy - r * 0.5, 2 * r, r * 1.1, radius=0.5)
        out.append(fcv.Rect(cx - r * 0.55, cy - r * 0.25, r * 1.1, r * 0.6,
                            border_radius=0.4, paint=hollow))
    elif shape == '市':                     # 市：一长排（三个摊位的竖线）
    # [EN] Market: one long row (vertical lines of three stalls)
        rect(cx - r, cy - r * 0.6, 2 * r, r * 1.2, radius=0.5)
        for k in (-1, 0, 1):
            out.append(fcv.Line(cx + k * r * 0.5, cy - r * 0.35,
                                cx + k * r * 0.5, cy + r * 0.35,
                                paint=ft.Paint(color=paper, stroke_width=1.0,
                                               style=ft.PaintingStyle.STROKE)))
    else:                                   # 屋（默认）：正方块 + 屋顶两条斜线
    # [EN] House (default): square block + two slanted roof lines
        rect(cx - r * 0.85, cy - r * 0.35, r * 1.7, r * 1.1, radius=0.8)
        out.append(fcv.Path([fcv.Path.MoveTo(cx - r, cy - r * 0.35),
                             fcv.Path.LineTo(cx, cy - r * 1.05),
                             fcv.Path.LineTo(cx + r, cy - r * 0.35)], paint=line))
    return out





def _on_wall(shapes: list, x: float, y_wall: float, span_h: float, text: str, *,
             pal: dict, color: str, font: str | None,
             size: int = 12, center: bool = False, bold: bool = False) -> None:
    """把一个名字**贴在墙上**（用户 2026-10-12：「建筑的名字标记都放到墙的旁边
    **不要放到别的东西的上面**」）。

    做法三件事：
      ① 写在墙线**内侧**一个字号的高度（`y_wall + size + 1`）—— 不是压着墙线，
         也不是飘到墙外面；
      ② 名字底下垫一块**纸色**（免得墙里的家具斜线/铺点从字缝里透过来）；
      ③ `center=True` 时按 `x` 居中（房间名），否则左对齐（建筑名 / 院子名）。

    ★ 为什么要有"垫一块纸色"：文字是**透明底**画的，落在密集的铺点或斜线上就糊了。
      垫一块同色底是平面图的常规做法（标注框），也最省事。
    [EN] Put a name **on the wall** (the user on 2026-10-12: "put the building's name label beside
    [EN] the wall, **not on top of other things**").
    [EN] Three things:
    [EN] 1) written one font-size **inside** the wall line (`y_wall + size + 1`) -- neither pressing on
    [EN]    the wall line nor floating outside it;
    [EN] 2) a **paper-coloured** patch behind the name (so the furniture hatching / stippling inside
    [EN]    the wall does not show through the letters);
    [EN] 3) with `center=True` it centres on `x` (room names), otherwise it is left-aligned (building /
    [EN]    courtyard names).
    [EN] ★ Why the paper patch: text is drawn on a **transparent** background and smears over dense
    [EN] stippling or hatching. A same-colour patch is the standard floor-plan annotation convention
    [EN] and the cheapest fix.
    """
    tw = _cjk_w(str(text or ''), size)
    tx = (x - tw / 2) if center else x
    ty = y_wall + size + 1
    # ① 垫一块纸色（比字略大一圈）
    # [EN] 1) pad with a paper-coloured patch (a ring bigger than the text)
    shapes.append(fcv.Rect(tx - 3, y_wall + 1, tw + 6, size + 5,
                           paint=ft.Paint(color=pal['paper'],
                                          style=ft.PaintingStyle.FILL)))
    shapes.append(_text(tx, ty, text, size=size, color=color, font=font,
                           bold=bold))


def _text(x: float, y: float, value: str, *, size: int, color: str,
          font: str | None = None, center: bool = False,
          right: bool = False, bold: bool = False) -> fcv.Text:
    """一行字。**坐标要先算好**（`fcv.Text` 的 x/y 是文字左上角）。
        English:
    A line of text. **Coordinates must be computed first** (`fcv.Text`'s x/y is the text's top-left
    corner).
    """
    v = str(value or '')
    if center:
        x -= _cjk_w(v, size) / 2
    elif right:
        x -= _cjk_w(v, size)
    return fcv.Text(x, y, value=v,
                    style=ft.TextStyle(size=size, color=color,
                                       font_family=font,
                                       weight=(ft.FontWeight.BOLD if bold
                                               else ft.FontWeight.NORMAL)))


def build_canvas(layout: Layout | None, **kw) -> fcv.Canvas:
    """`build_shapes()` 的便利包装：直接给一个能挂上去的 `Canvas`。
        English:
    Convenience wrapper for `build_shapes()`: directly gives a `Canvas` that can be attached.
    """
    width = int(kw.get('width', 196))
    height = int(kw.get('height', 132))
    return fcv.Canvas(build_shapes(layout, **kw), width=width, height=height)


def shape_counts(shapes: list) -> dict:
    """形状清单里各有多少条 —— 验证脚本用它核对"该画的都画了"。
        English:
    How many of each are in the shape list -- the verification script uses this to check "everything
    that should be drawn was drawn".
    """
    out: dict[str, int] = {}
    for s in shapes:
        k = type(s).__name__
        out[k] = out.get(k, 0) + 1
    return out


def known_shapes() -> tuple:
    """渲染器**真的有专门画法**的字形。

    ⚠ 这个函数的存在意义：`map_layout.SHAPES` 是交给模型的**白名单**，
    渲染这边要一一对应。加了一个新字形、渲染忘了写，它会静默掉进
    "屋"那个默认分支 —— 图上全是方块，而**不报错**。
    所以让判据能断言"两边的集合**完全相等**"，这里必须**手写**，
    不许 `return SHAPES`（那就成了自证）。
    
        English:
    Glyphs for which the renderer **truly has a dedicated drawing method**.
        ⚠ The reason this function exists: `map_layout.SHAPES` is the **whitelist** given to the model,
        and the rendering side must correspond one-to-one. If a new glyph is added and rendering forgets to implement it, it silently falls into
        the "house" default branch -- the map is all squares, and **does not error**.
        So to let the criterion assert that "the two sets are **exactly equal**", this must be **hand-written**,
        `return SHAPES` is not allowed (that would be self-proving).
    """
    return ('屋', '院', '亭', '门', '桥', '渡', '树', '山', '塔', '台', '市')
